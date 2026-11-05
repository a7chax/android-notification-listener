# Notification website validation

Date: 2026-11-06

## Delivered

The website runtime is in `website/`. Run `uv run website/server.py` from
the project root and open `http://127.0.0.1:8765`. It uses the existing
Notification Bridge APK and Python listener classes without changing them.

Shared agents implemented the local server and interface in parallel.
The primary agent implemented browser history, integration and device QA.
A separate read-only agent reviewed the implementation.

## Evidence

- `python3 -m unittest discover -s tests -v`: 41 tests passed, including
  all 25 existing listener tests and 16 collector/HTTP tests.
- `node website/history.test.mjs`: 16 tests passed, covering replay IDs,
  snapshots, device/session identity, retained removals and earlier text,
  restoration, corrupt/blocked/quota-limited storage, capacity pause,
  cross-tab merging/clearing, and durable gap warnings.
- `node --check website/app.js` and `node --check website/history.js` passed.
- Python compilation and `git diff --check` passed.
- Headless Chrome browser QA verified historical search, app filters,
  chronological timelines, browser refresh, JSON export, desktop/mobile
  layout, offline history, corrupt storage recovery, gap notice restoration,
  clearing history in another open tab, replay after reconnection without
  duplicates, and rendering notification HTML as text.
- Actual-phone baseline: `python3 tests/device_smoke.py` passed with
  `posted`, `updated`, `updated`, `removed`, custom-view text/progress and
  background app updates.
- Actual-phone website QA: `tests/website_browser_smoke.py --device` passed
  against the running server. Notification Bridge's new post, two updates
  and removal appeared in the retained timeline. Progress reached 100/100.
  All four lifecycle records remained after refresh with no duplicate IDs.

Browser QA uses a temporary Chrome profile. Screenshots under `/tmp` contain
fictional notification records only. No private notification bodies or
device identifiers are included in this report or test fixtures.

## Review fixes

The code reviewer identified two material issues, both fixed with failing
regressions before implementation and rechecked by the reviewer:

1. A delayed second tab could restore history after a clear. A persisted
   reset generation now prevents older saved records from returning.
2. A history-gap notice disappeared after refresh. Gap state and observed
   Android sessions now persist alongside notification history.

## Limits

This is a local first version with browser storage, not a permanent archive.
History belongs to one browser profile and origin. Persistent data is capped
at 2 MiB, and intake pauses visibly when unsaved memory reaches its limit.
Phone and server replay buffers are bounded. The UI retains known history
and reports unavailable intermediate changes.

Physical USB unplug/replug was not performed. Disconnect, heartbeat failure,
device reselection and replay gaps are covered by collector tests; browser
server unavailability is exercised with fictional HTTP responses. Live
notification delivery and refresh restoration were verified on the phone.

The server was left running on the documented loopback address for review.

## Clean light redesign and app identity

The user subsequently chose a clean light interface and requested actual app
icons. [The redesign record](redesign-plan.md) documents the change. Optional
Android `apps` metadata keeps protocol version 1 and old APK support. Labels
and PNG icons are saved once per app/source within the existing storage limits.

Latest checks: 44 Python tests and 27 JavaScript tests passed, Android build
and APK signature verification passed, and browser/actual-phone website QA
passed with the new app labels and decoded 64px icons. The updated APK was
installed in place after matching its signing certificate. The bundled APK
and SHA256SUMS were refreshed. The website remains available at the same URL.

## Accessible editorial styling

The user supplied an Officevibe reference and requested larger text. The
[accessibility style record](accessibility-style-plan.md) documents the
resulting warm cream, navy and serif treatment, 18px reading text, larger
controls, relative font units, and measured browser checks. The page passed
320–1440px reflow and 200% enlarged-text checks, keyboard navigation, and
the existing browser smoke flow. Live updates retain keyboard focus, and
unchanged connection status no longer triggers repeated live-region writes.
