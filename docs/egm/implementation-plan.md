# Notification Website Implementation Plan

**Goal:** Build the live notification inbox in `website/`, retain updates and
removals in browser storage, and validate it with Notification Bridge on the phone.

**Architecture:** One standard-library Python collector owns the ADB connection.
The browser polls a bounded replay API, reconciles history independently of
rendering, and stores a versioned history value. Plain HTML, CSS and JavaScript
keep installation consistent with the existing dependency-free Python project.

**Execution:** Shared agents implement the server and interface in parallel;
the primary agent owns history/persistence, integration and actual-device QA.
The user requested shared-agent implementation after approving the hypothesis
and the Goldfish review. Defaults below resolve the review findings within
that scope; no further feature interview is needed.

## Global constraints

- All website runtime code lives in `website/`.
- Python 3.10+, no Python runtime dependencies, no external browser assets.
- Keep existing CLI and Android APK behavior unchanged.
- Serve `http://127.0.0.1:8765` and only website assets and explicit API routes.
- Preserve updates and actual removals; never infer a removal from a disconnect.
- Keep the last saved browser history intact on quota or validation failure.
- No private notification content in logs, screenshots or committed fixtures.

## Shared API contract

`GET /api/events?after=0&epoch=` returns JSON:

```json
{"version":1,"epoch":"transport-id","cursor":4,"source":"opaque-device-id",
 "events":[],"active":[],"session":null,"replay_gap":false,
 "status":{"state":"connecting","message":"Connecting to phone…",
 "last_success":null,"history_gap":false}}
```

`events` contain the existing event schema: `session`, `seq`, `event`,
`timestamp`, `notification`, optional `removal_reason`. `active` contains the
current notification objects from the last successful read. `session` is the
current Android session. Status states are `connecting`, `connected`,
`disconnected`. `last_success` is Unix milliseconds. `history_gap` remains
true once a phone journal gap has been observed. `replay_gap` reports a
transport cursor outside the retained buffer. A changed epoch resets the
browser's transient cursor, not its saved history.

One collector polls every 0.5 seconds. Retain at most 512 events or 2 MiB of
serialized event data in its transient buffer. Supply snapshots through the
existing `EventCursor`, and always return active state even when it is empty.
Restart collection after ADB failures; a stopped heartbeat becomes a visible
failure after 20 seconds. A new source gets a distinct opaque identity.

## Task 1: Local server (server agent)

**Create:** `website/server.py`, `tests/test_website_server.py`.

- [x] Write focused tests first for empty/disconnected startup, lifecycle
  replay, journal/transport gaps, heartbeat failure and restricted routes.
- [x] Run the new tests and confirm missing behavior fails.
- [x] Implement the collector with `listener.Adb` and `listener.EventCursor`.
- [x] Implement static and API serving with Host/Origin checks and no CORS.
- [x] Support `python3 website/server.py [--serial SERIAL] [--port PORT]`.
- [x] Run server tests and existing CLI regressions.

## Task 2: Browser history (primary agent)

**Create:** `website/history.js`, `website/history.test.mjs`,
`website/package.json` (ES module declaration and dependency-free test script).

Exports: `HistoryStore`, `notificationText(notification)`,
`groupNotifications(events)`. `HistoryStore` constructor takes
`{storage, key}`; default key is `notificationBridge.history.v1`.
`load()`, `ingest(events, source)`, `persist()`, `clear()`, `exportJSON()`
are its interface. Public fields: `events`, `error`, `savedCount`,
`storageBytes`, `paused`. `ingest` returns added count. `persist` returns a
boolean and preserves the old value on failure. Each stored event includes
`id` and `source` alongside the original event fields. Groups expose
`id`, `events`, `latest`, `notification`, `package`, `firstSeen`, `lastSeen`.

- [x] Write and run failing tests for replay deduplication, several snapshot
  keys, removals/occurrences, search text, restoration and storage failures.
- [x] Implement stable lifecycle IDs using source/session/seq; snapshot IDs
  also include notification key. Group by source/session/key and start a new
  occurrence when a post follows an observed removal.
- [x] Store version 1 data; preserve corrupt/unsupported originals. Limit
  persistent serialized UTF-16 data to 2 MiB without automatic eviction.
  Preserve unsaved events in memory; pause intake after 1,000 unsaved events
  or 1 MiB unsaved data. Make retry/export/explicit clear possible.
- [x] Run `node --test website/history.test.mjs`.

## Task 3: Interface (frontend agent)

**Create:** `website/index.html`, `website/styles.css`, `website/app.js`.

- [x] Build a responsive, accessible inbox with a quiet paper-and-green
  visual direction, navigation, search, package filter, history list and
  chronological details. Use inline SVG/CSS and local font fallbacks.
- [x] Integrate the shared API and history module; poll every second with
  one request at a time and an abort timeout. Restore before first fetch.
- [x] Render notification strings through text nodes, including custom-view
  text, progress and extraction warnings. Search all retained history.
- [x] Distinguish browser connection, phone health and saved/unsaved state.
  Retain dismissed notifications and mark actual removal accurately.
- [x] Provide JSON export, save retry and confirmed clear-history recovery.
  React to storage events without silently overwriting another tab's data.

## Task 4: Integration and validation (primary agent)

**Create:** `website/README.md`; **Modify:** root `README.md` website usage.

- [x] Run Python and JavaScript tests and syntax checks.
- [x] Use browser automation with fictional fixtures for search, filters,
  persistence, history details, errors, responsive layout and text safety.
- [x] Run the local server with host ADB access and exercise Notification
  Bridge on the actual connected phone. Verify post, two updates and
  removal remain visible in history and survive refresh.
- [x] Verify unavailable-server history remains readable and reconnects
  do not duplicate records. Review the final diff and record actual results.
- [x] Deliver the launch command and local URL. Leave the server running
  if it is successfully reachable and useful for the user's review.
