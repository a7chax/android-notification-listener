# Notification Bridge website

A local inbox for Android notifications, with live updates and browser-saved
history. Updated and removed notifications stay in the inbox. Select a row
to see its chronological history, custom-view text and progress.

The clean light interface shows notifications from all apps. App names and
icons come directly from Android through Notification Bridge. If an icon is
unavailable, the website shows an initial tile. No app-store lookup or
third-party image service is used.

## Run

From the project root, with your Android phone connected over USB:

```sh
uv run listener.py setup
uv run website/server.py
```

Open **http://127.0.0.1:8765**. If Notification Bridge is already installed
and connected, only the server command is needed. Python 3.10 or later can
also run it directly with `python3 website/server.py`.

The phone screen can be off. Keep USB debugging authorized and Notification
Bridge notification access enabled. scrcpy can stay open or be closed.

If you installed an earlier Notification Bridge APK, run setup again to
install the bundled update for app names/icons. Older bridge versions still
provide notifications with package-name and initial-tile fallbacks.

For several connected devices, select one explicitly:

```sh
uv run website/server.py --serial YOUR_DEVICE_SERIAL
```

The server binds only to the local computer. It serves the website even if
the phone is unavailable and retries the phone connection automatically.
Use `uv run listener.py doctor` to diagnose Notification Bridge.

## History

- Search covers earlier notification text as well as the latest version.
- The app filter changes the display; collection still includes all apps.
- “Removed from phone” records an Android removal, without deleting history.
- History is saved in local storage for this browser profile and address.
  Keep using `127.0.0.1:8765`; `localhost` and other ports have separate storage.
- App labels and icons are stored once per app and phone alongside history,
  including for offline viewing, and count toward the same storage limit.
- Keep the page open to collect and save events. The server's temporary
  replay buffer is not a permanent archive. Intermediate changes during a
  long interruption may be unavailable; the page shows a warning.
- Persistent history is limited to an estimated 2 MiB. It never silently
  deletes old entries to make room. If saving fails, new events remain
  unsaved in the tab; use **Export history** or **Retry save**.
- Unsaved data is bounded to 1 MiB or 1,000 events. Intake pauses visibly
  when that limit is reached. Export, then clear history to make room.
- **Clear history** requires confirmation. Export first if you want a copy.
  Clearing browser data also deletes saved history.

Notification content stays on this computer and in the browser. No external
assets, accounts, cloud services or Python runtime dependencies are used.

## Verify

From the project root:

```sh
python3 -m unittest discover -s tests -v
node website/history.test.mjs
```

The browser smoke check needs Playwright and installed Google Chrome. Run
the website server first. To use a temporary QA environment:

```sh
uv venv /tmp/notification-website-qa
uv pip install --python /tmp/notification-website-qa/bin/python playwright
/tmp/notification-website-qa/bin/python tests/website_browser_smoke.py
```

Add `--device` to also run the Notification Bridge demo on the connected
phone and verify that its post, two updates and removal survive a page
refresh. That option opens the bridge activity and returns to the home
screen. Browser checks use a temporary profile; screenshots contain only
fictional data and are saved under `/tmp`.
