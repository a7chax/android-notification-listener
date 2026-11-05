import copy
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

import listener

try:
    from website import server
except ImportError:
    server = None


def notification(key="demo", text="Fictional notification"):
    return {"key": key, "package": "example.demo", "id": 1, "text": text}


def event(seq, kind="posted", record=None):
    return {"seq": seq, "event": kind, "timestamp": 123,
            "notification": record or notification()}


def state(seq=0, events=None, active=None, session="session-one", heartbeat=123):
    return {"version": 1, "session": session, "seq": seq, "connected": True,
            "heartbeat": heartbeat, "events": events or [], "active": active or []}


class FakeAdb:
    def __init__(self, samples=(), devices=("fictional-phone",)):
        self.samples = list(samples)
        self.devices = list(devices)
        self.serial = None
        self.selections = 0

    def select_device(self):
        index = min(self.selections, len(self.devices) - 1)
        self.selections += 1
        selected = self.devices[index]
        if isinstance(selected, Exception):
            raise selected
        self.serial = selected

    def read_state(self):
        sample = self.samples.pop(0)
        if isinstance(sample, Exception):
            raise sample
        return copy.deepcopy(sample)


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(server, "The website server must be implemented")
        self.now = 0
        self.clock = lambda: self.now

    def collector(self, adb, **kwargs):
        return server.Collector(adb=adb, monotonic=self.clock,
                                wall_time=lambda: 10, **kwargs)

    def test_startup_is_available_without_a_phone(self):
        collector = self.collector(FakeAdb(devices=[listener.BridgeError("private serial")]))
        initial = collector.snapshot()
        self.assertEqual(initial["status"]["state"], "connecting")
        self.assertIsNone(initial["source"])
        collector.poll_once()
        result = collector.snapshot()
        self.assertEqual(result["status"]["state"], "disconnected")
        self.assertNotIn("private serial", json.dumps(result))
        self.assertEqual(result["active"], [])
        self.assertIsNone(result["session"])
        self.assertIsNone(result["status"]["last_success"])

    def test_old_apk_has_empty_apps_and_metadata_survives_disconnect(self):
        sample = state()
        apps = {"example.demo": {"label": "Example", "icon": None}}
        sample["apps"] = apps
        collector = self.collector(FakeAdb([state(), sample, listener.BridgeError("offline")]))
        self.assertEqual(collector.snapshot()["apps"], {})
        collector.poll_once()
        self.assertEqual(collector.snapshot()["apps"], {})
        collector.poll_once()
        self.assertEqual(collector.snapshot()["apps"], apps)
        collector.poll_once()
        self.assertEqual(collector.snapshot()["apps"], apps)

    def test_metadata_clears_on_source_change_and_invalid_icons_fall_back(self):
        sample = state()
        sample["apps"] = {"example.demo": {"label": "Example", "icon": "javascript:alert(1)"}}
        adb = FakeAdb([sample, listener.BridgeError("offline"), state()],
                      ["fictional-phone", "replacement-phone"])
        collector = self.collector(adb)
        collector.poll_once()
        self.assertEqual(collector.snapshot()["apps"],
                         {"example.demo": {"label": "Example", "icon": None}})
        collector.poll_once()
        collector.poll_once()
        self.assertEqual(collector.snapshot()["apps"], {})

    def test_app_metadata_is_bounded_and_valid_png_is_kept(self):
        icon = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aS1sAAAAASUVORK5CYII="
        sample = state()
        sample["apps"] = {f"example.app{i}": {"label": "x" * 300, "icon": icon}
                          for i in range(140)}
        sample["apps"]["bad/package"] = {"label": "Bad", "icon": None}
        collector = self.collector(FakeAdb([sample]))
        collector.poll_once()
        apps = collector.snapshot()["apps"]
        self.assertEqual(len(apps), 128)
        self.assertEqual(apps["example.app0"]["icon"], icon)
        self.assertEqual(len(apps["example.app0"]["label"]), 256)

    def test_lifecycle_replay_empty_active_and_deduplication(self):
        events = [event(1), event(2, "updated"), event(3, "removed")]
        adb = FakeAdb([state(), state(3, events), state(3, events)])
        collector = self.collector(adb)
        collector.poll_once()
        self.assertEqual(collector.snapshot()["active"], [])
        collector.poll_once()
        result = collector.snapshot()
        self.assertEqual([e["event"] for e in result["events"]],
                         ["posted", "updated", "removed"])
        self.assertEqual(result["cursor"], 3)
        self.assertEqual(result["status"]["last_success"], 10000)
        self.assertEqual(result["status"]["state"], "connected")
        self.assertEqual(collector.snapshot(after=2, epoch=result["epoch"])["events"],
                         [dict(events[-1], session="session-one")])
        collector.poll_once()
        self.assertEqual(collector.snapshot(after=3)["events"], [])
        self.assertEqual(adb.selections, 1)

    def test_retry_preserves_device_cursor_and_last_active(self):
        adb = FakeAdb([state(active=[notification()]), listener.BridgeError("offline"),
                       state(2, [event(1), event(2, "updated")], [notification()])])
        collector = self.collector(adb)
        collector.poll_once()
        before = collector.snapshot()
        collector.poll_once()
        failed = collector.snapshot()
        self.assertEqual(failed["status"]["state"], "disconnected")
        self.assertEqual(failed["active"], before["active"])
        collector.poll_once()
        after = collector.snapshot(after=before["cursor"], epoch=before["epoch"])
        self.assertEqual([e["event"] for e in after["events"]], ["posted", "updated"])
        self.assertEqual(after["source"], before["source"])
        self.assertEqual(after["epoch"], before["epoch"])
        self.assertEqual(adb.selections, 2)

    def test_source_is_opaque_stable_and_distinct_for_new_device(self):
        adb = FakeAdb([state(), listener.BridgeError("offline"), state()],
                      ["fictional-phone", "other-fictional-phone"])
        collector = self.collector(adb)
        collector.poll_once()
        before = collector.snapshot()
        other = self.collector(FakeAdb([state()]))
        other.poll_once()
        self.assertEqual(other.snapshot()["source"], before["source"])
        self.assertNotIn("fictional-phone", before["source"])
        collector.poll_once()
        collector.poll_once()
        after = collector.snapshot()
        self.assertNotEqual(after["source"], before["source"])
        self.assertNotEqual(after["epoch"], before["epoch"])

    def test_journal_gap_is_sticky_and_resynchronizes_snapshot(self):
        adb = FakeAdb([state(), state(300, [event(300)], [notification()]),
                       state(300, [event(300)], [notification()])])
        collector = self.collector(adb)
        collector.poll_once()
        collector.poll_once()
        result = collector.snapshot()
        self.assertTrue(result["status"]["history_gap"])
        self.assertEqual(result["events"][-1]["event"], "snapshot")
        collector.poll_once()
        self.assertTrue(collector.snapshot()["status"]["history_gap"])

    def test_stale_heartbeat_is_not_refreshed_by_reselection_or_wall_clock(self):
        adb = FakeAdb([state(), state(), state(), state(heartbeat=124)])
        collector = self.collector(adb)
        collector.poll_once()
        self.now = 21
        collector.poll_once()
        self.assertEqual(collector.snapshot()["status"]["state"], "disconnected")
        self.assertIn("heartbeat", collector.snapshot()["status"]["message"].lower())
        collector.poll_once()
        self.assertEqual(collector.snapshot()["status"]["state"], "disconnected")
        collector.poll_once()
        self.assertEqual(collector.snapshot()["status"]["state"], "connected")

    def test_disconnected_android_preserves_active_and_session_change_resyncs(self):
        disconnected = state()
        disconnected["connected"] = False
        adb = FakeAdb([state(active=[notification()]), disconnected,
                       state(active=[], session="session-two")])
        collector = self.collector(adb)
        collector.poll_once()
        collector.poll_once()
        self.assertEqual(collector.snapshot()["active"], [notification()])
        collector.poll_once()
        self.assertEqual(collector.snapshot()["session"], "session-two")
        self.assertEqual(collector.snapshot()["active"], [])

    def test_gap_snapshot_keeps_timestamp_of_last_successful_active_read(self):
        disconnected = state(heartbeat=999)
        disconnected["connected"] = False
        collector = self.collector(FakeAdb([state(active=[notification()]), disconnected]))
        collector.poll_once()
        collector.poll_once()
        result = collector.snapshot(epoch="earlier-server")
        self.assertEqual(result["events"][-1]["timestamp"], 123)

    def test_buffer_limits_and_out_of_range_cursors_report_replay_gap(self):
        events = [event(i) for i in range(1, 515)]
        collector = self.collector(FakeAdb([state(), state(514, events, [notification()])]))
        collector.poll_once()
        collector.poll_once()
        result = collector.snapshot(after=0)
        self.assertTrue(result["replay_gap"])
        self.assertLessEqual(len([e for e in result["events"] if e["event"] != "snapshot"]), 512)
        self.assertEqual(result["events"][-1]["event"], "snapshot")
        self.assertFalse(collector.snapshot(after=2, epoch=result["epoch"])["replay_gap"])
        self.assertTrue(collector.snapshot(after=515, epoch=result["epoch"])["replay_gap"])
        self.assertTrue(collector.snapshot(after=514, epoch="old-server")["replay_gap"])

    def test_serialized_buffer_is_bounded_even_for_large_events(self):
        huge = notification(text="x" * (1024 * 1024))
        events = [event(i, record=huge) for i in range(1, 4)]
        collector = self.collector(FakeAdb([state(), state(3, events)]))
        collector.poll_once()
        collector.poll_once()
        result = collector.snapshot()
        self.assertTrue(result["replay_gap"])
        self.assertLessEqual(len(json.dumps(result["events"]).encode()), 2 * 1024 * 1024)

    def test_background_thread_is_single_and_stoppable(self):
        collector = self.collector(FakeAdb([state()] * 20), interval=0.01)
        collector.start()
        first = collector.thread
        collector.start()
        self.assertIs(collector.thread, first)
        collector.stop()
        self.assertFalse(first.is_alive())


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(server, "The website server must be implemented")
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        assets = Path(self.folder.name)
        (assets / "index.html").write_text("<h1>Fictional inbox</h1>")
        (assets / "app.js").write_text("export {};")
        (assets / "private.txt").write_text("must never be served")
        self.collector = server.Collector(adb=FakeAdb(devices=[listener.BridgeError("offline")]))
        self.httpd = server.create_server(self.collector, port=0, asset_dir=assets)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.port = self.httpd.server_port
        self.host = f"127.0.0.1:{self.port}"

    def close_server(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)

    def request(self, target="/", headers=None, method="GET"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        self.addCleanup(conn.close)
        conn.request(method, target, headers=headers or {})
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read()

    def test_static_and_empty_api_available_without_phone(self):
        code, headers, body = self.request()
        self.assertEqual(code, 200)
        self.assertIn(b"Fictional inbox", body)
        self.assertEqual(headers["Cache-Control"], "no-store")
        code, headers, body = self.request("/api/events?after=0&epoch=")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["status"]["state"], "connecting")
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_rejects_foreign_host_or_origin(self):
        for headers in ({"Host": "evil.example"}, {"Origin": "https://evil.example"},
                        {"Origin": "null"}, {"Host": self.host + ".evil.example"},
                        {"Origin": "http://user@" + self.host}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request("/api/events", headers=headers)[0], 403)
        self.assertEqual(self.request(headers={"Origin": "http://" + self.host})[0], 200)

    def test_only_explicit_assets_are_served(self):
        for path in ("/listener.py", "/private.txt", "/../listener.py", "/%2e%2e/listener.py",
                     "/.git/config", "/api/other", "/app.js/extra"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 404)
        code, headers, _ = self.request("/app.js")
        self.assertEqual(code, 200)
        self.assertIn("javascript", headers["Content-Type"])

    def test_invalid_cursor_is_a_client_error(self):
        for query in ("after=-1", "after=nope", "after=1&after=2", "after=1.2"):
            with self.subTest(query=query):
                self.assertEqual(self.request("/api/events?" + query)[0], 400)

    def test_head_and_post_never_expose_unchecked_routes(self):
        self.assertEqual(self.request("/private.txt", method="HEAD")[0], 404)
        self.assertEqual(self.request(method="POST")[0], 405)


if __name__ == "__main__":
    unittest.main()
