# Local notification website

* **Author:** a7chax
* **Date:** 2026-11-06
* **Status:** Six-lens brainstorm completed; subsequently implemented at the user's request with shared agents. See [validation](validation.md).

## Overview

Build a website in `website/` for one person to read notifications from one Android phone through the existing ADB listener. A local Python server supplies live events. The browser saves received history in local storage and restores it after refresh, including earlier text and observed removals.

The main risks are duplicate or lost history during reconnects, a page that looks connected while phone capture has stopped, and browser storage that fills or becomes unreadable. The design must make these conditions visible while preserving previously saved history.

## Analysis

### Confirmed requirements and observed foundation

The anchored hypothesis covers a local server, live notifications, search, app filters, browser local storage, restoration on refresh, and visible connection or storage failures. The user explicitly confirmed retaining notification updates and removals. The user also requested validation on their actual phone using the Notification Bridge demo, with website validation included.

`listener.py` already supplies `Adb`, `EventCursor`, retries, heartbeat checks, package filtering, and notification formatting. Android publishes protocol version 1, a current active set, and a journal bounded to 256 events. First connection and a changed Android session return current snapshots rather than earlier journal history. Existing CLI diagnostics go to stderr; forwarding notification JSON alone would hide failures and resynchronization.

Root-reported baseline validation on 2026-11-06: the Python suite passed 25 tests; `tests/device_smoke.py` exited 0 on the actual phone and observed `posted`, `updated`, `updated`, `removed` on one notification key, background changes, and custom text/progress. This validates the existing bridge. Website behavior remains untested because it has not been implemented. No private capture files were read for this brainstorm.

### Proposed defaults for the first version

These are reviewer and synthesizer recommendations, not additional user decisions.

| Area | Proposed default |
| --- | --- |
| Runtime | Standard-library Python server and plain HTML/CSS/JavaScript; one selected phone and one primary browser tab. |
| Startup | `uv run server.py`, with the existing optional `--serial` convention. Serve the UI even when ADB is unavailable; retry phone collection in the background. |
| Address | `http://127.0.0.1:8765`; bind only to loopback. Fail clearly on a port conflict instead of changing the origin automatically. |
| Delivery | Browser requests updates once per second; one server-owned collector polls ADB at the existing 0.5-second default. Supply structured status and snapshot boundaries with events. |
| Temporary replay | A server buffer capped at 512 envelopes or 2 MiB, whichever comes first. A client outside that buffer receives an explicit gap and current snapshot. Server restarts have a distinct transport epoch. This buffer is not durable history. |
| History display | One entry per notification occurrence, latest observed content first, with an expandable chronological timeline. A later post after an observed removal starts another occurrence. |
| Search and filters | Search package names and all retained readable history; exact-package app filter defaults to all apps. Filters change display, not capture or saved data. |
| Browser persistence | One versioned JSON value under `notificationBridge.history.v1`; restore and validate before connecting. Batch writes within 250 ms and distinguish pending/failed writes from saved data. |
| Capacity | Stop accepting further persistent history at an estimated 2 MiB of serialized UTF-16 data; actual browser failures may occur earlier. Do not evict old events automatically. |
| Storage failure | Preserve the last saved value, keep newly received events in memory with a persistent unsaved warning, and offer retry, JSON export, and clear-history with confirmation. Cap unsaved memory at 1 MiB or 1,000 events; pause intake with a visible potential-loss notice when full. |

The buffer and capacity values are conservative starting points, not measured guarantees. Validate fictional bursts and quota failures before considering larger limits. JSON export is a proposed recovery action, not a confirmed product request.

### History and reconnect rules

Keep each observed `posted`, `updated`, and `removed` event, including its original content and removal reason. Group by source device, notification key, and observed occurrence. Deduplicate journal events by source, Android session, and sequence number. Snapshot identity additionally includes notification key and snapshot kind: every notification in one snapshot shares the same session and sequence number.

Snapshots mean “observed current at this read.” Repeated identical snapshots must not add duplicate lifecycle events. An empty successful snapshot needs an explicit boundary. A changed snapshot can add an observation without pretending an unseen update was captured. A missing key can mark an entry “not in the current snapshot,” but must never invent a removal event. Retain previous history across browser refreshes, transport reconnects, Android session changes, and server restarts.

Label an actual removal “Removed from phone”; Android removal alone does not establish that a person dismissed it. Show event time and last-observed time; distinguish a snapshot observation from original notification post time. After an interruption, mark old current-state claims stale until reconciliation. Persist gap/session-change markers with a notice that intermediate changes may be missing.

### Connection, storage, and local exposure

Show browser-to-server connectivity separately from phone capture health. Capture health derives from successful ADB reads, Android `connected`, and the existing stale-heartbeat check, not the absence or presence of notification events. Include last successful phone read and concise recovery guidance using `setup` or `doctor`. Keep history readable when the server or phone is unavailable.

Validate stored data and its schema version. If data is corrupt or from a newer schema, leave the original value untouched, explain the failure, and block automatic replacement until explicit recovery. A failed write must not turn an unsaved event into a saved event or advance its persisted cursor. Loading a blank page must not silently reset saved history.

Serve only `website/` assets and explicit API routes. Validate the expected Host and any supplied Origin, avoid permissive CORS, and render notification strings as text. Use no third-party assets or network services. Keep notification bodies and device identifiers out of routine diagnostics. Authentication and remote hosting are outside this local first version.

Reuse `Adb` and `EventCursor`. Add a narrow structured collection/status boundary where needed; do not parse terminal logs or maintain a second independent implementation of retry and heartbeat rules. Keep CLI JSONL and stderr behavior compatible. One small browser history reducer should own identity/reconciliation separately from rendering and persistence.

## Goals vs. Non-Goals

* **In-Scope Goals:** Live local viewing, retained observed lifecycle history, refresh restoration, all-app capture with display filters, custom-view text, progress and extraction warnings, explicit capture/storage/gap status, and actual-phone demo validation.
* **Out-of-Scope Non-Goals:** A complete permanent archive, background browser capture after the page closes, durable server storage, accounts, remote access, cloud synchronization, notification control, app-specific order parsing, multi-device management, frontend frameworks, or external telemetry services.

Browser storage belongs to one browser profile and origin. Changing hostname or port can make history appear absent; browser clearing can remove it. The bounded Android journal and transient server buffer cannot guarantee recovery while the page is closed. These limits must appear in the UI/help text.

## Alternatives Weighed

1. **Local server and browser storage:** Recommended by all six lenses for this scope. Requires explicit reconnection and persistence behavior, but no database.
2. **Static page with manual JSON import:** Less server work; does not meet live viewing without a separate capture/import workflow. Deferred by reviewers, not rejected by the user.
3. **Local server and database:** Can collect while the browser is closed; adds storage beyond the requested first version. Deferred by reviewers, not rejected by the user.
4. **Persistent push instead of HTTP polling:** Can reduce request overhead but adds connection/replay handling. HTTP polling is the proposed starting point; revisit only if measured behavior warrants it.

No alternative has been recorded as rejected by the user.

## Key Decisions & Staging for Next Steps

**User decisions:** Website in `website/`; preserve updates/removals in browser history and restore on refresh; proceed with Goldfish review of the anchored hypothesis; test the actual-phone demo including website behavior.

**Proposals for alignment:** The table's runtime, port, transport, presentation, storage limits, recovery controls, and single-primary-tab boundary. Capacity behavior and history presentation are the remaining material product choices; the table supplies concrete defaults for review without another broad interview.

After alignment, draft an implementation plan covering: a shared collection/status seam and local server; a replay-safe history reducer and versioned persistence; the live/search/filter interface; and focused verification. Proposed files should be marked Create or Modify. No APK change is expected.

Acceptance should demonstrate:

1. Existing CLI regression tests pass; mocked server tests cover disconnected startup, stale heartbeat, empty snapshots, journal/transport gaps, and safe file serving.
2. Browser tests with fictional data cover several notifications in one snapshot, duplicate replay, key reuse, session/server restarts, retained earlier text, removed entries, filters/search, and refresh restoration.
3. Quota, blocked storage, malformed/unsupported stored data, and failed writes preserve saved data and show unsaved status; capacity pause is explicit.
4. On the actual phone, start the website and run the Notification Bridge demo. Observe post, two updates, and removal; inspect the retained timeline and custom text/progress, then refresh and verify all four lifecycle events remain. Do not record unrelated private notification contents.
5. Disconnect/reconnect the phone and interrupt/restart the server. Saved history remains readable, statuses reflect the affected connection, no duplicate events appear, and any unavailable history is identified rather than fabricated.

See [the six-lens findings report](goldfish_brainstorm_report.md) for reviewer completion and supporting source references. This brief records the review's recommendations; the [implementation plan](implementation-plan.md) and [validation](validation.md) record the subsequent work.
