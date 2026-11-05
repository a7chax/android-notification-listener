# Pre-merge EGM review configuration

- TargetFile: `README.md`
- SemanticTarget: full file; re-read and re-count before every round.
- Reviewers: `codebase_details`, `comprehension`, `style`.
- Standards: each reviewer uses `docs/egm/release-review-standard.md`.
- GoldfishContext: `website/README.md`, `website/server.py`,
  `website/history.js`, `website/app.js`, `website/index.html`,
  `website/styles.css`, `listener.py`, `android/AndroidManifest.xml`,
  `android/src/dev/local/notificationbridge/NotificationBridge.java`,
  `tests/test_listener.py`, `tests/test_website_server.py`,
  `tests/website_browser_smoke.py`, `website/history.test.mjs`,
  `docs/REFERENCE.md`, `docs/DEVELOPMENT.md`, and `pyproject.toml`.

The source context lets reviewers check the final release against the public
documentation. Reviewers are read-only, use fresh conversation contexts and
must confirm every assigned read. Each round uses three parallel reviewers.
Convergence requires two consecutive rounds without unresolved Blocker or
Major findings; a failed reviewer prevents a clean round. Cap at five rounds.

User-confirmed execution mode: run the full loop automatically. Run rounds,
apply routine valid fixes within the already requested feature scope, retain
evidence-backed contests, and stop for unresolved substantive decisions or
the loop's cap/churn. Push and merge only after successful review and checks,
as the user has requested.
