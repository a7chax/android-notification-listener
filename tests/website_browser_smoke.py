"""Opt-in browser QA. Install Playwright separately; --device also runs the phone demo."""

import argparse
import base64
import json
import struct
import sys
import zlib
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import listener

KEY = "notificationBridge.history.v1"


def demo_event(seq, kind, text, key="fictional-download", package="example.downloads"):
    return {"seq": seq, "event": kind, "session": "fictional-session",
            "timestamp": 1793900000000 + seq * 1000,
            "notification": {"key": key, "package": package, "title": "Offline map download",
                             "text": None, "view_text": [text],
                             "progress": {"value": seq * 25, "max": 100}}}


def fixture_icon():
    """A fictional local icon, used only by browser fixtures."""
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))
    pixels = bytearray()
    for y in range(64):
        pixels.append(0)
        for x in range(64):
            arrow = (29 <= x <= 34 and 15 <= y <= 38) or (30 <= y <= 42 and abs(x - 32) <= 42 - y)
            tray = (44 <= y <= 48 and 18 <= x <= 46)
            pixels.extend((255, 255, 255, 255) if arrow or tray else (59, 100, 224, 255))
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', 64, 64, 8, 6, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(bytes(pixels))) + chunk(b'IEND', b'')
    return 'data:image/png;base64,' + base64.b64encode(png).decode()


def fictional_checks(browser, url, screenshot):
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    records = [demo_event(1, "posted", "Preparing download"),
               demo_event(2, "updated", "Downloading files"),
               demo_event(3, "updated", "Download complete"),
               demo_event(4, "removed", "Download complete"),
               demo_event(5, "posted", "Meet at the east entrance", "fictional-message", "example.chat")]
    records[-1]["notification"]["title"] = "New message"
    payload = {"version": 1, "epoch": "fictional-server", "cursor": 5,
               "source": "fictional-device", "events": records,
               "apps": {"example.downloads": {"label": "Downloads", "icon": fixture_icon()},
                        "example.chat": {"label": "Messages", "icon": None}},
               "active": [records[-1]["notification"]], "session": "fictional-session",
               "replay_gap": False, "status": {"state": "connected", "message": "Phone capture is connected.",
               "last_success": 1793900000000, "history_gap": False}}
    page.route("**/api/events?*", lambda route: route.fulfill(json=payload))
    page.goto(url)
    page.wait_for_load_state("networkidle")
    rows = page.get_by_test_id("notification-row")
    expect(rows).to_have_count(2)
    expect(page.get_by_test_id("connection-status")).to_contain_text("Phone connected")
    page.locator("#package-filter").select_option("example.downloads")
    expect(rows).to_have_count(1)
    expect(rows).to_contain_text("Removed from phone")
    expect(rows).to_contain_text("Downloads")
    expect(rows.get_by_test_id("app-icon")).to_be_visible()
    assert rows.get_by_test_id("app-icon").evaluate("image => image.complete && image.naturalWidth > 0")
    rows.first.click()
    detail = page.get_by_test_id("notification-detail")
    expect(detail).to_contain_text("4 observed events")
    expect(detail).to_contain_text("Preparing download")
    expect(detail).to_contain_text("Downloading files")
    expect(detail).to_contain_text("Download complete")
    page.locator("#search-input").fill("Preparing download")
    expect(rows).to_have_count(1)
    page.locator("#search-input").fill("unmatched query")
    expect(rows).to_have_count(0)
    page.locator("#search-input").fill("")
    expect(rows).to_have_count(1)
    page.wait_for_function("key => JSON.parse(localStorage.getItem(key) || '{}').events?.length === 5", arg=KEY)
    page.reload()
    expect(rows).to_have_count(2)
    page.locator("#package-filter").select_option("example.downloads")
    expect(detail).to_contain_text("4 observed events")
    expect(rows.get_by_test_id("app-icon")).to_be_visible()
    page.screenshot(path=screenshot, full_page=True)
    with page.expect_download() as download:
        page.locator("#export-button").click()
    assert download.value.suggested_filename.endswith(".json")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile layout overflows"
    page.screenshot(path=screenshot.replace(".png", "-mobile.png"), full_page=True)
    payload["replay_gap"] = True
    expect(page.locator("#gap-notice")).to_be_visible(timeout=5000)
    page.wait_for_function("key => JSON.parse(localStorage.getItem(key)).incomplete === true", arg=KEY)
    payload["replay_gap"] = False
    page.reload()
    expect(page.locator("#gap-notice")).to_be_visible()
    # A failed server fetch must keep previously saved history readable.
    page.unroute("**/api/events?*")
    page.route("**/api/events?*", lambda route: route.abort())
    page.reload()
    expect(rows).to_have_count(2)
    expect(page.get_by_test_id("connection-status")).to_contain_text("Local server unavailable")
    expect(rows.filter(has_text="Downloads").get_by_test_id("app-icon")).to_be_visible()
    page.unroute("**/api/events?*")
    page.route("**/api/events?*", lambda route: route.fulfill(json=payload))
    expect(page.get_by_test_id("connection-status")).to_contain_text("Phone connected", timeout=5000)
    expect(rows).to_have_count(2)
    assert page.evaluate("key => JSON.parse(localStorage.getItem(key)).events.length", KEY) == 5
    assert not errors, errors
    context.close()

    # Corrupt storage must remain untouched while live records stay available.
    context = browser.new_context()
    page = context.new_page()
    page.add_init_script(f"localStorage.setItem({json.dumps(KEY)}, 'unreadable original')")
    page.route("**/api/events?*", lambda route: route.fulfill(json=payload))
    page.goto(url)
    expect(page.get_by_test_id("storage-status")).to_contain_text("original is untouched")
    expect(page.get_by_test_id("notification-row")).to_have_count(2)
    assert page.evaluate("key => localStorage.getItem(key)", KEY) == "unreadable original"
    context.close()
    # A second open tab must respect an explicit clear instead of saving old records again.
    context = browser.new_context()
    payload["events"] = records
    context.route("**/api/events?*", lambda route: route.fulfill(json=payload))
    first = context.new_page()
    first.goto(url)
    first.wait_for_function("key => JSON.parse(localStorage.getItem(key) || '{}').events?.length === 5", arg=KEY)
    payload["events"] = []
    second = context.new_page()
    second.goto(url)
    expect(second.get_by_test_id("notification-row")).to_have_count(2)
    first.on("dialog", lambda dialog: dialog.accept())
    first.locator("#clear-history").click()
    expect(second.get_by_test_id("notification-row")).to_have_count(0)
    unsafe = demo_event(6, "posted", "<img src=x onerror=alert('unsafe')>", "text-safety")
    payload["events"] = [unsafe]
    payload["cursor"] = 6
    expect(second.get_by_test_id("notification-row")).to_contain_text("<img src=x onerror=alert('unsafe')>", timeout=5000)
    assert second.locator("img[src='x']").count() == 0, "Notification text was interpreted as HTML"
    context.close()
    print("Fictional browser QA: search/filter, timeline, refresh, export, mobile, offline/reconnect, corrupt storage, persistent gap, cross-tab clear and text safety passed.")


def device_check(browser, url):
    bridge = listener.Adb()
    bridge.select_device()
    assert bridge.read_state()["connected"], "Notification Bridge must be connected"
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url)
    expect(page.get_by_test_id("connection-status")).to_contain_text("Phone connected", timeout=15000)
    page.wait_for_timeout(500)
    before = page.evaluate("key => JSON.parse(localStorage.getItem(key) || '{\"events\":[]}').events.filter(e => e.notification.package === 'dev.local.notificationbridge').map(e => e.id)", KEY)
    bridge.run("shell", "am", "start", "--activity-single-top", "-n", listener.APP + "/.MainActivity", "--ez", "demo", "true")
    bridge.run("shell", "input", "keyevent", "KEYCODE_HOME")
    page.wait_for_function("""({key, before}) => {
        const events = JSON.parse(localStorage.getItem(key) || '{"events":[]}').events
          .filter(e => e.notification.package === 'dev.local.notificationbridge'
            && e.notification.id === 7001 && !before.includes(e.id));
        return events.some(e => e.event === 'removed') && events.filter(e => e.event === 'updated').length >= 2;
      }""", arg={"key": KEY, "before": before}, timeout=20000)
    page.locator("#package-filter").select_option(listener.APP)
    rows = page.get_by_test_id("notification-row")
    expect(rows.first).to_contain_text("Removed from phone")
    rows.first.click()
    expect(rows.first).to_contain_text("Notification Bridge")
    icon = rows.first.get_by_test_id("app-icon")
    expect(icon).to_be_visible()
    assert icon.evaluate("image => image.complete && image.naturalWidth === 64"), "Actual Android app icon did not load"
    detail = page.get_by_test_id("notification-detail")
    for text in ("Finding your driver", "Driver is on the way", "Driver has arrived", "Removed from phone", "Progress 100 / 100"):
        expect(detail).to_contain_text(text)
    saved = page.evaluate("""({key, before}) => JSON.parse(localStorage.getItem(key)).events
      .filter(e => e.notification.package === 'dev.local.notificationbridge'
        && e.notification.id === 7001 && !before.includes(e.id)).map(e => e.id)""", {"key": KEY, "before": before})
    page.reload()
    page.locator("#package-filter").select_option(listener.APP)
    expect(page.get_by_test_id("notification-detail")).to_contain_text("Driver is on the way")
    page.wait_for_function("""({key, saved}) => {
      const events = JSON.parse(localStorage.getItem(key)).events;
      return saved.every(id => events.filter(e => e.id === id).length === 1);
    }""", arg={"key": KEY, "saved": saved})
    assert len(saved) >= 4
    assert not errors, errors
    context.close()
    print("Actual-phone website QA: Notification Bridge post, two updates, removal, custom text/progress and refresh persistence passed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--device", action="store_true")
    parser.add_argument("--screenshot", default="/tmp/notification-website.png")
    args = parser.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, args=["--no-sandbox"])
        try:
            fictional_checks(browser, args.url, args.screenshot)
            if args.device:
                device_check(browser, args.url)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
