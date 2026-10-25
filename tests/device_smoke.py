"""Opt-in real-device check. Installs nothing; requires `listener.py setup` first."""

import argparse
import json
import select
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import listener


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial")
    args = parser.parse_args()
    adb = listener.Adb(args.serial)
    adb.select_device()
    state = adb.read_state()
    assert state["connected"], "Notification listener is disconnected"
    gojek = [n for n in state["active"] if n["package"] == "com.gojek.app" and n["custom_view"]]
    for n in gojek:
        assert n["view_text"], f"Gojek custom view extraction failed: {n['extraction_errors']}"
        assert not n["extraction_errors"], n["extraction_errors"]
    command = [sys.executable, str(listener.ROOT / "listener.py"), "listen",
               "--serial", adb.serial, "--duration", "13"]
    with tempfile.TemporaryFile(mode="w+") as diagnostics:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=diagnostics, text=True)
        try:
            # An initial snapshot proves the subscriber has consumed its baseline.
            assert select.select([process.stdout], [], [], 5)[0], "No initial snapshot in five seconds"
            first = process.stdout.readline()
            assert json.loads(first)["event"] == "snapshot"
            subprocess.run([sys.executable, str(listener.ROOT / "listener.py"), "demo",
                            "--serial", adb.serial], check=True, capture_output=True, text=True)
            # The subsequent demo updates must work while the activity is in background.
            adb.run("shell", "input", "keyevent", "KEYCODE_HOME")
            output, _ = process.communicate(timeout=20)
            diagnostics.seek(0)
            assert process.returncode == 0, diagnostics.read()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    events = [json.loads(line) for line in (first + output).splitlines()]
    packages = {e["notification"]["package"] for e in events}
    assert len(packages) >= 2, f"Default stream must include multiple apps: {packages}"
    demo = [e for e in events if e["notification"]["package"] == listener.APP
            and e["notification"]["id"] == 7001]
    assert demo, "The demo did not post any notification events"
    kinds = [e["event"] for e in demo]
    assert kinds[0] == "posted" and kinds[-1] == "removed", kinds
    assert kinds.count("updated") >= 2, kinds
    assert len({e["notification"]["key"] for e in demo}) == 1, "Notification key changed"
    expected = ["Finding your driver", "Driver is on the way", "Driver has arrived"]
    posted = [e for e in demo if e["event"] != "removed"]
    for status, progress in zip(expected, (10, 55, 100)):
        matched = [e for e in posted if status in e["notification"]["view_text"]]
        assert matched, f"Missing custom-view update: {status}"
        assert matched[0]["notification"]["progress"]["value"] == progress
        assert matched[0]["notification"]["title"] is None
        assert matched[0]["notification"]["text"] is None
        assert not matched[0]["notification"]["extraction_errors"]
    print(json.dumps({"device": adb.serial, "gojek_custom_views_verified": len(gojek),
                      "default_stream_app_count": len(packages),
                      "demo_lifecycle": kinds, "same_notification_key": True,
                      "background_updates": True, "custom_text_and_progress": "verified"}, indent=2))


if __name__ == "__main__":
    main()
