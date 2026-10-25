import copy
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import listener


def notification(key="order", package="com.example.delivery", text="Driver arriving"):
    return {"key": key, "package": package, "id": 7, "title": None,
            "text": None, "view_text": [text], "progress": {"value": 40, "max": 100}}


def state(seq=0, events=None, active=None, session="one"):
    return {"version": 1, "session": session, "seq": seq, "connected": True,
            "heartbeat": 123, "events": events or [], "active": active or []}


def event(seq, kind, record=None):
    return {"seq": seq, "event": kind, "timestamp": 123,
            "notification": record or notification()}


class CursorTests(unittest.TestCase):
    def test_first_read_is_current_snapshot_not_historical_posts(self):
        result = listener.EventCursor().consume(state(8, [event(8, "posted")], [notification()]))
        self.assertEqual([e["event"] for e in result], ["snapshot"])
        self.assertEqual(result[0]["notification"]["view_text"], ["Driver arriving"])

    def test_updates_to_same_id_and_removal_between_polls_are_kept(self):
        cursor = listener.EventCursor()
        cursor.consume(state())
        events = [event(1, "posted"), event(2, "updated", notification(text="Arrived")),
                  event(3, "removed", notification(text="Arrived"))]
        self.assertEqual(cursor.consume(state(3, events)),
                         [dict(e, session="one") for e in events])
        self.assertEqual(cursor.consume(state(3, events)), [])

    def test_restart_resynchronizes_current_state(self):
        cursor = listener.EventCursor()
        cursor.consume(state(9))
        result = cursor.consume(state(0, active=[notification()], session="two"))
        self.assertEqual(result[0]["event"], "snapshot")
        self.assertEqual(result[0]["session"], "two")

    def test_overflow_reports_loss_instead_of_silently_skipping(self):
        cursor = listener.EventCursor()
        cursor.consume(state(1))
        with self.assertRaises(listener.HistoryGap):
            cursor.consume(state(300, [event(299, "updated"), event(300, "removed")]))

    def test_missing_tail_or_middle_event_is_also_a_gap(self):
        for events in ([event(1, "posted")], [event(1, "posted"), event(3, "removed")], []):
            cursor = listener.EventCursor()
            cursor.consume(state())
            with self.subTest(events=events), self.assertRaises(listener.HistoryGap):
                cursor.consume(state(3, events))

    def test_disconnected_listener_is_not_an_empty_snapshot(self):
        sample = state(active=[notification()])
        sample["connected"] = False
        with self.assertRaises(listener.BridgeError):
            listener.EventCursor().consume(sample)

    def test_input_state_is_not_mutated(self):
        sample = state(active=[notification()])
        before = copy.deepcopy(sample)
        listener.EventCursor().consume(sample)
        self.assertEqual(sample, before)


class OutputTests(unittest.TestCase):
    def test_exact_package_filter_and_all_apps(self):
        record = notification()
        self.assertTrue(listener.matches(record, ["com.example.delivery"]))
        self.assertFalse(listener.matches(record, ["com.example"]))
        self.assertTrue(listener.matches(record, ["*"]))

    def test_json_is_one_line_and_preserves_unicode(self):
        sample = event(2, "updated", notification(text="Sudah sampai 😋\nLobby"))
        formatted = listener.format_event(sample, "json")
        self.assertEqual(json.loads(formatted), sample)
        self.assertEqual(len(formatted.splitlines()), 1)
        self.assertIn("😋", formatted)

    def test_text_contains_custom_view_status_and_lifecycle(self):
        formatted = listener.format_event(event(2, "updated"), "text")
        self.assertIn("UPDATED", formatted)
        self.assertIn("com.example.delivery", formatted)
        self.assertIn("Driver arriving", formatted)
        self.assertIn("40/100", formatted)

    def test_null_text_is_explicit(self):
        n = notification()
        n["view_text"] = []
        self.assertIn("no readable text", listener.format_event(event(1, "posted", n), "text"))


class AdbTests(unittest.TestCase):
    @patch("listener.log")
    @patch("listener.APK")
    def test_android_8_setup_opens_settings_instead_of_unsupported_shell_grant(self, apk, log):
        adb = Mock(serial="phone")
        adb.run.side_effect = lambda *args, **kwargs: "26\n" if "getprop" in args else "Success"
        adb.read_state.return_value = state()
        listener.setup(adb)
        self.assertFalse(any("allow_listener" in call.args for call in adb.run.call_args_list))
        self.assertTrue(any("android.settings.ACTION_NOTIFICATION_LISTENER_SETTINGS" in call.args
                            for call in adb.run.call_args_list))

    @patch("listener.log")
    @patch("listener.APK")
    def test_vendor_shell_grant_failure_opens_settings(self, apk, log):
        adb = Mock(serial="phone")
        def run(*args, **kwargs):
            if "getprop" in args:
                return "36\n"
            if "allow_listener" in args:
                raise listener.BridgeError("not supported")
            return "Success"
        adb.run.side_effect = run
        adb.read_state.return_value = state()
        listener.setup(adb)
        self.assertTrue(any("android.settings.ACTION_NOTIFICATION_LISTENER_SETTINGS" in call.args
                            for call in adb.run.call_args_list))

    @patch("listener.log")
    @patch("listener.APK")
    def test_setup_android_12_does_not_grant_nonexistent_android_13_permission(self, apk, log):
        adb = Mock(serial="phone")
        adb.run.side_effect = lambda *args, **kwargs: "32\n" if "getprop" in args else "Success"
        adb.read_state.return_value = state()
        listener.setup(adb)
        self.assertFalse(any("grant" in call.args for call in adb.run.call_args_list))

    @patch("listener.subprocess.run")
    def test_no_device_error_has_actionable_message(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "List of devices attached\n", "")
        with self.assertRaisesRegex(listener.BridgeError, "No authorized Android device"):
            listener.Adb().select_device()

    @patch("listener.subprocess.run")
    def test_multiple_devices_require_serial(self, run):
        run.return_value = subprocess.CompletedProcess([], 0,
            "List of devices attached\none\tdevice\ntwo\tdevice\n", "")
        with self.assertRaisesRegex(listener.BridgeError, "--serial"):
            listener.Adb().select_device()

    @patch("listener.subprocess.run")
    def test_failed_adb_does_not_become_empty_state(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, "", "device offline")
        with self.assertRaisesRegex(listener.BridgeError, "device offline"):
            listener.Adb("phone").read_state()

    @patch("listener.subprocess.run")
    def test_state_uses_selected_device_and_app_private_file(self, run):
        sample = state()
        run.return_value = subprocess.CompletedProcess([], 0, json.dumps(sample), "")
        self.assertEqual(listener.Adb("phone").read_state(), sample)
        command = run.call_args.args[0]
        self.assertEqual(command[:3], ["adb", "-s", "phone"])
        self.assertIn("run-as", command)
        self.assertIn("files/state.json", command)


class StreamTests(unittest.TestCase):
    @patch("listener.time.sleep")
    @patch("listener.log")
    def test_short_adb_interruption_replays_buffered_events(self, log, sleep):
        adb = Mock()
        adb.read_state.side_effect = [state(), listener.BridgeError("USB offline"),
            state(2, [event(1, "posted"), event(2, "updated")], [notification()]), KeyboardInterrupt]
        args = SimpleNamespace(duration=None, command="listen", package=["com.example.delivery"],
                               format="json", interval=0.5)
        output = io.StringIO()
        with self.assertRaises(KeyboardInterrupt):
            listener.stream(adb, args, output)
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([e["event"] for e in events], ["posted", "updated"])


class CliTests(unittest.TestCase):
    @patch("listener.time.sleep")
    @patch("listener.log")
    @patch("listener.Adb")
    def test_file_listener_confirms_saved_events_and_explains_continuous_listening(self, adb_class, log, sleep):
        adb_class.return_value.read_state.side_effect = [state(active=[notification()]), KeyboardInterrupt]
        with tempfile.TemporaryDirectory() as folder, patch("listener.sys.stdout", new_callable=io.StringIO) as output:
            path = Path(folder) / "notifications.jsonl"
            self.assertEqual(listener.main(["listen", "--output", str(path)]), 130)
            self.assertEqual(output.getvalue(), "")
            saved = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(len(saved), 1)
            messages = "\n".join(call.args[0] for call in log.call_args_list)
            self.assertIn(str(path), messages)
            self.assertIn("Wrote 1", messages)
            self.assertIn("Ctrl-C", messages)

    @patch("listener.log")
    @patch("listener.Adb")
    def test_snapshot_defaults_to_all_apps_in_json_and_text(self, adb_class, log):
        records = [notification(package="com.example.delivery"),
                   notification(key="chat", package="com.example.chat"),
                   notification(key="usb", package="android")]
        records[1].update(title="Chat", text="New message", view_text=[])
        adb_class.return_value.read_state.return_value = state(active=records)
        for output_format in ("json", "text"):
            with self.subTest(format=output_format), patch("listener.sys.stdout", new_callable=io.StringIO) as output:
                self.assertEqual(listener.main(["snapshot", "--format", output_format]), 0)
                result = output.getvalue()
                if output_format == "json":
                    events = [json.loads(line) for line in result.splitlines()]
                    self.assertEqual({e["notification"]["package"] for e in events},
                                     {n["package"] for n in records})
                else:
                    for record in records:
                        self.assertIn(record["package"], result)
                    self.assertIn("New message", result)

    @patch("listener.time.sleep")
    @patch("listener.log")
    @patch("listener.Adb")
    def test_default_live_stream_includes_other_apps_and_their_updates(self, adb_class, log, sleep):
        chat = notification(key="chat", package="com.example.chat")
        events = [event(1, "posted", chat), event(2, "updated", chat),
                  event(3, "removed", chat), event(4, "posted", notification())]
        adb_class.return_value.read_state.side_effect = [state(), state(4, events), KeyboardInterrupt]
        with patch("listener.sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(listener.main(["listen"]), 130)
            result = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([e["event"] for e in result], [e["event"] for e in events])
        self.assertEqual({e["notification"]["package"] for e in result},
                         {"com.example.chat", "com.example.delivery"})

    @patch("listener.log")
    @patch("listener.Adb")
    def test_explicit_package_filter_still_limits_output(self, adb_class, log):
        adb_class.return_value.read_state.return_value = state(active=[
            notification(), notification(key="chat", package="com.example.chat")])
        with patch("listener.sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(listener.main(["snapshot", "--package", "com.example.chat"]), 0)
            events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([e["notification"]["package"] for e in events], ["com.example.chat"])


if __name__ == "__main__":
    unittest.main()
