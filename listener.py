# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Stream Android notification lifecycle events over ADB. No Python dependencies."""

import argparse
import json
import math
import subprocess
import sys
import time
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path

APP = "dev.local.notificationbridge"
COMPONENT = APP + "/.NotificationBridge"
ROOT = Path(__file__).resolve().parent
APK = ROOT / "build" / "notification-bridge.apk"


class BridgeError(RuntimeError):
    pass


class HistoryGap(BridgeError):
    pass


class EventCursor:
    """Read each journal event once; never turn a failed read into a removal."""

    def __init__(self):
        self.session = None
        self.seq = 0

    def consume(self, state):
        if not state["connected"]:
            raise BridgeError("Android listener is disconnected. Run: uv run listener.py setup")
        session, seq = state["session"], state["seq"]
        if self.session != session:
            self.session, self.seq = session, seq
            return [{"event": "snapshot", "seq": seq, "session": session,
                     "timestamp": state["heartbeat"], "notification": n}
                    for n in state["active"]]
        events = [e for e in state["events"] if e["seq"] > self.seq]
        if [e["seq"] for e in events] != list(range(self.seq + 1, seq + 1)):
            raise HistoryGap("Notification journal overflow or gap; resynchronizing current notifications.")
        self.seq = seq
        return [dict(e, session=session) for e in events]


def matches(notification, packages):
    return "*" in packages or notification["package"] in packages


def format_event(event, output_format):
    if output_format == "json":
        return json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    n = event["notification"]
    pieces = [n.get("title"), n.get("text"), n.get("big_text"), n.get("sub_text")]
    pieces += n.get("lines", []) + n.get("view_text", [])
    texts = list(dict.fromkeys(" ".join(str(s).split()) for s in pieces if s))
    body = " | ".join(texts) or "[no readable text]"
    progress = n.get("progress", {})
    if progress.get("max", 0):
        body += f" [progress {progress['value']}/{progress['max']}]"
    if n.get("extraction_errors"):
        body += " [custom view extraction incomplete]"
    stamp = datetime.fromtimestamp(event["timestamp"] / 1000, timezone.utc).isoformat(timespec="seconds")
    return f"{stamp} {event['event'].upper()} {n['package']} id={n['id']} {body}"


class Adb:
    def __init__(self, serial=None):
        self.serial = serial

    def run(self, *args, timeout=20):
        command = ["adb"] + (["-s", self.serial] if self.serial else []) + list(args)
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError as exc:
            raise BridgeError("adb is missing. Install Android platform-tools and add adb to PATH.") from exc
        except subprocess.TimeoutExpired as exc:
            raise BridgeError(f"ADB timed out after {timeout}s; check the USB connection.") from exc
        if result.returncode:
            message = result.stderr.strip() or result.stdout.strip() or "unknown ADB error"
            raise BridgeError(message)
        return result.stdout

    def select_device(self):
        output = self.run("devices")
        devices = [line.split() for line in output.splitlines()[1:] if line.strip()]
        ready = [fields[0] for fields in devices if len(fields) >= 2 and fields[1] == "device"]
        if self.serial:
            if self.serial not in ready:
                raise BridgeError(f"Device {self.serial} is unavailable or unauthorized. Check adb devices.")
        elif not ready:
            raise BridgeError("No authorized Android device. Connect USB and accept USB debugging on the phone.")
        elif len(ready) > 1:
            raise BridgeError("Multiple devices connected. Select one with --serial SERIAL.")
        else:
            self.serial = ready[0]

    def read_state(self):
        raw = self.run("exec-out", "run-as", APP, "cat", "files/state.json")
        try:
            state = json.loads(raw)
            if state["version"] != 1:
                raise BridgeError("Unsupported companion protocol. Run setup to update the APK.")
            for key in ("session", "seq", "heartbeat", "connected", "active", "events"):
                state[key]
            return state
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise BridgeError("Invalid companion state; run setup to reinstall the listener.") from exc


def log(message):
    print(message, file=sys.stderr, flush=True)


def setup(adb, rebuild=False):
    if rebuild or not APK.exists():
        result = subprocess.run([sys.executable, str(ROOT / "build_android.py")])
        if result.returncode:
            raise BridgeError("APK build failed. See the build output above.")
    log(adb.run("install", "-r", str(APK), timeout=90).strip())
    sdk = int(adb.run("shell", "getprop", "ro.build.version.sdk").strip())
    manual_access = sdk < 27
    if not manual_access:
        try:
            # ADB shell can grant this special access on Android 8.1+.
            adb.run("shell", "cmd", "notification", "allow_listener", COMPONENT)
        except BridgeError as exc:
            log(f"Automatic notification access unavailable: {exc}")
            manual_access = True
    if manual_access:
        adb.run("shell", "am", "start", "-a", "android.settings.ACTION_NOTIFICATION_LISTENER_SETTINGS")
        log("Enable Notification Bridge in the phone's notification access settings.")
    if sdk >= 33:
        adb.run("shell", "pm", "grant", APP, "android.permission.POST_NOTIFICATIONS")
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            state = adb.read_state()
            if state["connected"]:
                log(f"Listener connected on {adb.serial}; {len(state['active'])} notifications active.")
                return
        except BridgeError:
            pass
        time.sleep(0.5)
    adb.run("shell", "am", "start", "-a", "android.settings.ACTION_NOTIFICATION_LISTENER_SETTINGS")
    raise BridgeError("Enable Notification Bridge in the phone's notification access settings, then run doctor.")


def stream(adb, args, output):
    cursor = EventCursor()
    last_heartbeat = None
    heartbeat_seen = time.monotonic()
    deadline = time.monotonic() + args.duration if args.duration is not None else None
    retrying = False
    announced_ready = False
    while deadline is None or time.monotonic() < deadline:
        try:
            state = adb.read_state()
            if state["heartbeat"] != last_heartbeat:
                last_heartbeat = state["heartbeat"]
                heartbeat_seen = time.monotonic()
            elif time.monotonic() - heartbeat_seen > 20:
                raise BridgeError("Companion heartbeat stopped; check notification access and run setup.")
            try:
                events = cursor.consume(state)
            except HistoryGap as exc:
                log(str(exc))
                cursor = EventCursor()
                events = cursor.consume(state)
            if retrying:
                log("Reconnected; resumed notification events.")
                retrying = False
            written = 0
            for event in events:
                if matches(event["notification"], args.package):
                    print(format_event(event, args.format), file=output, flush=True)
                    written += 1
            if args.command == "listen" and not announced_ready:
                destination = str(args.output.resolve()) if getattr(args, "output", None) else "stdout"
                log(f"Ready. Wrote {written} existing notification(s) to {destination}. "
                    "Listening continuously for changes; Ctrl-C to stop.")
                announced_ready = True
            if args.command == "snapshot":
                return
        except BridgeError as exc:
            if args.command == "snapshot":
                raise
            if not retrying:
                log(f"{exc} Retrying every 2 seconds; Ctrl-C to stop.")
            retrying = True
            time.sleep(min(2, max(0, deadline - time.monotonic())) if deadline else 2)
            continue
        time.sleep(min(args.interval, max(0, deadline - time.monotonic())) if deadline else args.interval)


def positive_number(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a finite number greater than zero")
    return number


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    for command in ("setup", "doctor", "listen", "snapshot", "demo"):
        sub = commands.add_parser(command)
        sub.add_argument("--serial", help="ADB device serial (needed if multiple devices are connected)")
        if command == "setup":
            sub.add_argument("--rebuild", action="store_true", help="Rebuild the companion APK first")
        if command in ("listen", "snapshot"):
            sub.add_argument("--package", action="append", help="Optional exact-package filter; repeat for more (default: all apps)")
            sub.add_argument("--format", choices=("json", "text"), default="json")
            sub.add_argument("--output", type=Path, help="Append events to this file instead of stdout")
            sub.add_argument("--interval", type=positive_number, default=0.5, help="ADB polling seconds (default: 0.5)")
            sub.add_argument("--duration", type=positive_number, help="Stop after this many seconds")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    adb = Adb(args.serial)
    try:
        adb.select_device()
        if args.command == "setup":
            setup(adb, args.rebuild)
        elif args.command == "doctor":
            sample = adb.read_state()
            EventCursor().consume(sample)
            before = sample["heartbeat"]
            time.sleep(5.5)
            sample = adb.read_state()
            if not sample["connected"] or sample["heartbeat"] == before:
                raise BridgeError("Listener heartbeat is stale. Run: uv run listener.py setup")
            print(json.dumps({"device": adb.serial, "listener_connected": True,
                              "active_notifications": len(sample["active"]),
                              "session": sample["session"]}))
        elif args.command == "demo":
            adb.run("shell", "am", "start", "--activity-single-top", "-n", APP + "/.MainActivity", "--ez", "demo", "true")
            log("Demo started: custom notification posts, updates twice, then disappears in 9 seconds.")
            log("Watch it with: uv run listener.py listen --package " + APP + " --format text")
        else:
            args.package = args.package or ["*"]
            target = "all apps" if "*" in args.package else ", ".join(args.package)
            log(f"Reading {target} on {adb.serial}; diagnostics on stderr.")
            context = args.output.open("a", encoding="utf-8") if args.output else nullcontext(sys.stdout)
            with context as output:
                stream(adb, args, output)
        return 0
    except KeyboardInterrupt:
        log("Stopped.")
        return 130
    except BrokenPipeError:
        # Avoid another flush failure when piped into head.
        sys.stdout = open(__import__("os").devnull, "w")
        return 0
    except (BridgeError, OSError) as exc:
        log(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
