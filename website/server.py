# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Serve the local notification inbox and collect phone events over ADB."""

import argparse
import base64
import binascii
import copy
import hashlib
import json
import re
import sys
import threading
import time
import uuid
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

# Direct execution places website/, rather than the project root, on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from listener import Adb, BridgeError, EventCursor, HistoryGap

ASSETS = {"index.html": "text/html; charset=utf-8",
          "styles.css": "text/css; charset=utf-8",
          "app.js": "text/javascript; charset=utf-8",
          "history.js": "text/javascript; charset=utf-8",
          "favicon.svg": "image/svg+xml"}
MAX_EVENTS = 512
MAX_BYTES = 2 * 1024 * 1024


def app_metadata(value):
    """Keep bounded app identity data; unsafe icons fall back to labels."""
    if not isinstance(value, dict):
        return {}
    apps = {}
    size = 2
    for package, entry in value.items():
        if len(apps) >= 128:
            break
        if (not isinstance(package, str) or len(package) > 255 or
                not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*", package) or
                package in ("__proto__", "prototype", "constructor") or not isinstance(entry, dict)):
            continue
        label = entry.get("label")
        label = label[:256] if isinstance(label, str) else package
        icon = entry.get("icon")
        if isinstance(icon, str) and len(icon) <= 90000 and icon.startswith("data:image/png;base64,"):
            try:
                png = base64.b64decode(icon.split(",", 1)[1], validate=True)
                if not png.startswith(b"\x89PNG\r\n\x1a\n"):
                    icon = None
            except (ValueError, binascii.Error):
                icon = None
        else:
            icon = None
        metadata = {"label": label, "icon": icon}
        entry_size = len(json.dumps({package: metadata}, ensure_ascii=False).encode("utf-8"))
        if size + entry_size > MAX_BYTES:
            break
        apps[package] = metadata
        size += entry_size
    return apps


class Collector:
    """One ADB reader, with a bounded replay buffer shared by browser clients."""

    def __init__(self, serial=None, *, adb=None, interval=0.5,
                 monotonic=time.monotonic, wall_time=time.time):
        self.adb = adb if adb is not None else Adb(serial)
        self.serial = serial
        self.interval = interval
        self.monotonic = monotonic
        self.wall_time = wall_time
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.thread = None
        self.selected = False
        self.source = None
        self.epoch = uuid.uuid4().hex
        self.cursor = EventCursor()
        self.transport_cursor = 0
        self.buffer = deque()
        self.buffer_bytes = 0
        self.active = []
        self.apps = {}
        self.active_timestamp = None
        self.heartbeat = None
        self.heartbeat_changed = None
        self.last_success = None
        self.history_gap = False
        self.state = "connecting"
        self.message = "Connecting to phone…"

    def start(self):
        if self.thread is not None and self.thread.is_alive():
            return
        self.stopped.clear()
        self.thread = threading.Thread(target=self._run, name="notification-collector", daemon=True)
        self.thread.start()

    def stop(self):
        self.stopped.set()
        if self.thread is not None:
            self.thread.join(timeout=1)

    def _run(self):
        while not self.stopped.is_set():
            self.poll_once()
            self.stopped.wait(self.interval)

    def poll_once(self):
        """Perform a read; failures keep the last valid active set and cursor."""
        try:
            if not self.selected:
                # Clear implicit selection so reconnect can discover a replacement
                # phone; --serial continues to pin selection to the requested one.
                self.adb.serial = self.serial
                self.adb.select_device()
                source = hashlib.sha256(("notification-bridge:" + self.adb.serial).encode()).hexdigest()
                with self.lock:
                    if self.source is not None and source != self.source:
                        self.epoch = uuid.uuid4().hex
                        self.cursor = EventCursor()
                        self.transport_cursor = 0
                        self.buffer.clear()
                        self.buffer_bytes = 0
                        self.active = []
                        self.apps = {}
                        self.active_timestamp = None
                        self.heartbeat = None
                        self.heartbeat_changed = None
                        self.last_success = None
                    self.source = source
                self.selected = True
            sample = self.adb.read_state()
            with self.lock:
                heartbeat = (sample["session"], sample["heartbeat"])
                now = self.monotonic()
                if heartbeat != self.heartbeat:
                    self.heartbeat = heartbeat
                    self.heartbeat_changed = now
                elif now - self.heartbeat_changed > 20:
                    raise BridgeError("heartbeat")
                try:
                    events = self.cursor.consume(sample)
                except HistoryGap:
                    self.history_gap = True
                    self.cursor = EventCursor()
                    events = self.cursor.consume(sample)
                self.active = copy.deepcopy(sample["active"])
                self.apps = app_metadata(sample.get("apps", {}))
                self.active_timestamp = sample["heartbeat"]
                for event in events:
                    size = len(json.dumps(event, ensure_ascii=False,
                                          separators=(",", ":")).encode("utf-8"))
                    self.transport_cursor += 1
                    self.buffer.append((self.transport_cursor, event, size))
                    self.buffer_bytes += size
                    while len(self.buffer) > MAX_EVENTS or self.buffer_bytes > MAX_BYTES:
                        self.buffer_bytes -= self.buffer.popleft()[2]
                self.last_success = int(self.wall_time() * 1000)
                self.state = "connected"
                self.message = "Phone capture is connected."
        except (BridgeError, OSError, ValueError, KeyError, TypeError):
            self.selected = False
            with self.lock:
                self.state = "disconnected"
                # Never forward ADB diagnostics: they can contain serials or data.
                stale = (self.heartbeat_changed is not None and
                         self.monotonic() - self.heartbeat_changed > 20)
                self.message = ("Phone heartbeat stopped. Check notification access and run setup."
                                if stale else
                                "Phone capture unavailable. Check USB authorization and run setup or doctor.")

    def snapshot(self, after=0, epoch=None):
        with self.lock:
            floor = self.transport_cursor - len(self.buffer)
            gap = (after < floor or after > self.transport_cursor or
                   bool(epoch and epoch != self.epoch))
            events = [event for position, event, _ in self.buffer
                      if gap or position > after]
            if gap and self.cursor.session is not None:
                # A replay gap still returns retained lifecycle history, followed
                # by a current observation. Missing keys never imply removals.
                events += [{"event": "snapshot", "session": self.cursor.session,
                            "seq": self.cursor.seq, "timestamp": self.active_timestamp,
                            "notification": n} for n in self.active]
            state, message = self.state, self.message
            if (state == "connected" and self.heartbeat_changed is not None and
                    self.monotonic() - self.heartbeat_changed > 20):
                state = "disconnected"
                message = "Phone heartbeat stopped. Check notification access and run setup."
            return copy.deepcopy({"version": 1, "epoch": self.epoch,
                                  "cursor": self.transport_cursor, "source": self.source,
                                  "events": events, "active": self.active, "apps": self.apps,
                                  "session": self.cursor.session, "replay_gap": gap,
                                  "status": {"state": state, "message": message,
                                             "last_success": self.last_success,
                                             "history_gap": self.history_gap}})


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # No access logs: paths, queries and ADB output are not diagnostics.
        pass

    def _allowed(self):
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if port == 80:
            hosts.update(("127.0.0.1", "localhost"))
        host = self.headers.get_all("Host", [])
        origins = self.headers.get_all("Origin", [])
        return (len(host) == 1 and host[0] in hosts and
                (not origins or (len(origins) == 1 and origins[0] in
                                 {"http://" + h for h in hosts})))

    def _reply(self, code, data=b"", content_type="text/plain; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; "
                         "style-src 'self'; img-src 'self' data:; connect-src 'self'; "
                         "object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def do_GET(self):
        if not self._allowed():
            return self._reply(403, b"Loopback requests only.")
        try:
            target = urlsplit(self.path)
        except ValueError:
            return self._reply(400, b"Invalid request.")
        if target.scheme or target.netloc:
            return self._reply(400, b"Invalid request.")
        if target.path == "/api/events":
            try:
                query = parse_qs(target.query, keep_blank_values=True, max_num_fields=8)
                after_values = query.get("after", ["0"])
                epochs = query.get("epoch", [""])
                if len(after_values) != 1 or len(epochs) != 1:
                    raise ValueError
                raw_after = after_values[0]
                if not raw_after.isascii() or not raw_after.isdecimal() or len(raw_after) > 20:
                    raise ValueError
                after = int(raw_after)
            except ValueError:
                return self._reply(400, b"Invalid replay cursor.")
            data = json.dumps(self.server.collector.snapshot(after, epochs[0]),
                              ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            return self._reply(200, data, "application/json; charset=utf-8")
        asset = "index.html" if target.path == "/" else target.path.removeprefix("/")
        if asset not in ASSETS:
            return self._reply(404, b"Not found.")
        path = self.server.asset_dir / asset
        # An accidentally added symlink must not expose a repository file.
        if path.is_symlink():
            return self._reply(404, b"Not found.")
        try:
            data = path.read_bytes()
        except OSError:
            return self._reply(404, b"Not found.")
        return self._reply(200, data, ASSETS[asset])

    do_HEAD = do_GET

    def do_POST(self):
        if not self._allowed():
            return self._reply(403, b"Loopback requests only.")
        self._reply(405, b"Read-only server.")

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST
    do_OPTIONS = do_POST


def create_server(collector, port=8765, asset_dir=None):
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    httpd.collector = collector
    httpd.asset_dir = Path(asset_dir) if asset_dir else Path(__file__).resolve().parent
    return httpd


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", help="ADB device serial if multiple phones are connected")
    parser.add_argument("--port", type=int, default=8765, help="Loopback port (default: 8765)")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    collector = Collector(args.serial)
    try:
        httpd = create_server(collector, args.port)
    except OSError:
        print("Cannot bind the loopback port. Stop the other server or choose --port.", file=sys.stderr)
        return 1
    collector.start()
    print(f"Notification inbox: http://127.0.0.1:{args.port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        collector.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
