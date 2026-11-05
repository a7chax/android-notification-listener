# Goldfish Brainstorm Report

**Target:** `docs/egm/notification-website-plan.md`, entire working hypothesis.

**Mode:** BRAINSTORM; no document standards supplied.

**Date:** 2026-11-06.
**Result:** All six requested lenses completed. Deduplicated outcome: 0 Blockers, 9 Major findings, 3 Nits. These are concept safeguards and proposed defaults, not implemented fixes.

## Reviewer Status

| Reviewer | Persona | Status | Required reads |
| --- | --- | --- | --- |
| `egm-design` | `agents/design_critic.md` | completed | Persona, target, all five sources confirmed |
| `egm-codebase-details` | `agents/codebase_details.md` | completed | Persona, target, all five sources confirmed |
| `egm-zoom-out` | `agents/zoom_out.md` | completed | Persona, target, all five sources confirmed; reuse search reported |
| `egm-comprehension` | `agents/comprehension.md` | completed | Persona, target, all five sources confirmed |
| `egm-implementation-readiness` | `agents/implementation_readiness.md` | completed | Persona, target, all five sources confirmed |
| `egm-structural` | `agents/structural.md` | completed | Persona, target, all five sources confirmed |

Personas came from the installed `/home/nevermind/.codex/plugins/cache/egm/egm/0.1.0` bundle. Each was a fresh general-purpose native subagent with `fork_turns: "none"`, given its absolute persona/target/source paths and no conversation transcript. Reviewers ran as three parallel pairs; synthesis began after actual final results from all six. No retry or failed reviewer occurred. Host instruction-file exclusion is unverified; fresh conversation context does not establish that exclusion.

Every reviewer reported reading `listener.py`, `README.md`, `android/src/dev/local/notificationbridge/NotificationBridge.java`, `tests/test_listener.py`, and `pyproject.toml`. All explicitly reported read-only work and no capture/private-device reads. Review completion is evidenced by the native child final results, not inferred from launch status. The synthesizer read the installed synthesizer persona and Codex integration instructions before dispatch.

## Prioritized Findings

### 1. Separate lifecycle, snapshot, and notification identities — Major

* **Lenses:** Design, zoom-out, implementation-readiness, structural.
* **Scope:** Target “Confirmed history behavior”; `listener.py:EventCursor.consume`; Android source lines 50–75 and 90–99.
* **Finding:** Saving only the latest record by notification key destroys earlier updates. `(session, seq)` identifies journal events but collides across all notifications in a snapshot. Repeated reconnect snapshots can duplicate history, and keys can be reused after removal.
* **Recommendation:** Retain lifecycle events and deduplicate by source/session/seq. Include notification key for snapshot identities; keep snapshots as observations, reconcile repeat delivery idempotently, and start a new occurrence after an observed removal followed by a post. Put this logic in a small reducer.

### 2. Expose real collection health, not only browser connectivity — Major

* **Lenses:** Design, codebase-details, zoom-out, comprehension, structural.
* **Scope:** Target visible-failure requirement; `listener.py:stream` and `Adb.run`.
* **Finding:** JSON notification output omits ADB errors, reconnects, and the stale-heartbeat condition, all currently written to stderr. A browser connection can be healthy while capture has stopped; a quiet phone is not a failure.
* **Recommendation:** Send structured capture status, last successful read, and actionable recovery guidance. Show server reachability separately. Reuse existing messages and heartbeat rules; do not parse human-readable logs. No external observability system is warranted.

### 3. Identify missing history and complete snapshots explicitly — Major

* **Lenses:** All six.
* **Scope:** Target history promise; `listener.py:EventCursor.consume` and `stream`; Android lines 50–60 and 90–99.
* **Finding:** Android retains only 256 journal entries and resets its session on reconnection. The cursor begins from current state and the stream resynchronizes after gaps. Empty snapshots emit no notification JSON. None of these prove that missing notifications were observed being removed.
* **Recommendation:** Supply explicit snapshot start/end or a complete snapshot envelope, including empty sets. Persist session/gap markers, label stale/unknown current state, and never synthesize historical removals from absence. Bound transport replay and report its overflow too. Explain that closed-page capture and a complete archive are outside the promise.

### 4. Define capacity and distinguish received from saved data — Major

* **Lenses:** All six.
* **Scope:** Target local-storage persistence; Android lines 134–185.
* **Finding:** Repeated full custom-view payloads grow indefinitely; synchronous local-storage serialization can stall the UI, and quota/access failures are inevitable possibilities. A generic warning does not establish which events survive refresh.
* **Recommendation:** Batch writes; set a modest size limit; preserve the last successful value on failure; visibly mark pending/unsaved events and keep them in bounded memory. Do not silently trim old history. Offer explicit retry/export/clear recovery and stop intake visibly at the memory limit. Proposed starting caps: 2 MiB saved, 1 MiB or 1,000 unsaved events.

### 5. Protect corrupt or newer browser data — Major

* **Lens:** Implementation-readiness, supported by structural.
* **Scope:** Target refresh restoration and failure handling.
* **Finding:** An unversioned or automatically reset store can overwrite unreadable data or data written by a newer version. There is no existing browser schema to migrate, so a migration framework is unnecessary.
* **Recommendation:** Use schema version 1, validate before consumption, keep invalid/unsupported raw data untouched, and require explicit recovery before replacement. Advance persisted cursors only with successful persistence.

### 6. Start the UI independently of phone availability — Major

* **Lens:** Implementation-readiness.
* **Scope:** Target offline readability; `listener.py:main`.
* **Finding:** Existing CLI startup selects the device before its command and exits on failure. Reusing that startup wholesale would prevent the website from opening when the phone is unavailable, defeating offline history access.
* **Recommendation:** Start serving assets first, perform device selection/collection in a retrying server-owned worker, and report failure in the browser. Preserve the existing CLI behavior.

### 7. Preserve the local data boundary — Major

* **Lenses:** Design, zoom-out.
* **Scope:** Target local Python server; README data-protection guidance.
* **Finding:** Adding HTTP exposes notification data through a new interface. Serving the repository root or interpreting notification text as HTML creates avoidable exposure.
* **Recommendation:** Bind loopback only; serve `website/` and explicit APIs; reject unexpected Host/Origin values; avoid permissive CORS and external assets; render strings as text. No remote deployment, accounts, or cloud services are needed.

### 8. Keep the browser origin stable — Major

* **Lens:** Implementation-readiness; comprehension and zoom-out also identified this risk.
* **Scope:** Target browser storage and startup workflow.
* **Finding:** `localhost`, `127.0.0.1`, and different ports have separate browser histories. Automatically choosing a free port can look like erased data.
* **Recommendation:** Document one launch command and fixed default URL; print an actionable port-conflict error. Proposed default: `uv run server.py`, `http://127.0.0.1:8765`, optional `--serial` consistent with the CLI.

### 9. Make retained history understandable and discoverable — Major

* **Lens:** Comprehension.
* **Scope:** Target “Confirmed history behavior” and search/filter UI.
* **Finding:** A latest-state-only card can hide earlier text despite technically saving it. Calling every removal a dismissal claims an action the bridge has not established. Snapshot time is an observation time, not a historical post/update time.
* **Recommendation:** Latest content plus expandable chronological events; keep removed entries searchable; search earlier retained text too; label actual removal “Removed from phone.” Show last-observed and event timestamps with snapshot semantics. Presentation is a proposal awaiting alignment.

### 10. Reuse one collector and keep delivery bounded — Nit

* **Lenses:** Design, zoom-out, structural.
* **Scope:** `listener.py:Adb`, `EventCursor`, `stream`; proposed server.
* **Finding:** A per-tab ADB loop multiplies whole-state reads. Parsing CLI stderr or duplicating its retry loop creates brittle coupling. Unbounded client queues create memory growth.
* **Recommendation:** One collector for one selected phone; reuse the existing protocol and a small structured status seam. Keep CLI adapters compatible. A bounded transient replay buffer and simple shutdown/disconnect cleanup are enough; no general event framework or database is justified.

### 11. Keep custom text, search, and extraction warnings consistent — Nit

* **Lenses:** Codebase-details, comprehension, structural.
* **Scope:** `listener.py:format_event`; Android lines 134–185.
* **Finding:** Standard title/text may be null while `view_text` holds the useful content. Both `extraction_errors` and singular `extraction_error` can appear. Separate display/search projections can hide searchable content or make missing data look like a rendering defect.
* **Recommendation:** One readable-text projection combines standard fields, lines, and custom-view text with duplicate strings removed. Use it for display and search; retain progress, raw lifecycle payload, and extraction diagnostics. Show empty/incomplete content explicitly.

### 12. Avoid infrastructure without a demonstrated need — Nit

* **Lenses:** Design, zoom-out, codebase-details.
* **Scope:** Target approach alternatives; `pyproject.toml`.
* **Finding:** There is no paid-service or LLM cost here. The material limits are browser storage, serialization work, ADB polling, and bounded replay. Frameworks, distributed tracing, persistent queues, and multi-device orchestration add scope without solving a confirmed need.
* **Recommendation:** Start with dependency-free Python, static frontend files, client-side filters/search, and simple HTTP polling. Measure fictional bursts before increasing limits or introducing push delivery. Treat import and database approaches as deferred recommendations, not user-rejected alternatives.

## Synthesis and Validation Boundary

The companion [concepts brief](concepts_brief.md) incorporates these safeguards as proposals and separates them from confirmed user requirements. All six lenses considered the local-server/browser-storage approach proportionate; none required a database or framework.

The root reports 25 passing Python tests and a passing actual-device baseline (`python3 tests/device_smoke.py`, exit 0), including the demo lifecycle `posted`, `updated`, `updated`, `removed`, one stable key, background updates, and custom text/progress. Reviewers did not run these commands. Website implementation and website tests remain future work. Acceptance must run the demo through the website on the actual phone and verify retained history after refresh, plus disconnect/reconnect and explicit failure behavior. No device serial or unrelated app contents are included here.
