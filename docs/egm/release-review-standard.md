# Release documentation review standard

Review the target README as the public entry point for a general Android
notification listener and local notification website. Linked guides may carry
details; the README does not need to duplicate their implementation internals.

## Accuracy

- Commands, requirements, paths and links exist and match source behavior.
- Capture defaults to all apps. Examples describe notification categories;
  the project has no integration or branding tied to a delivery company.
- Notification updates and removals are retained in browser history, with
  live polling and refresh restoration. Do not claim a permanent archive or
  guaranteed capture while the page is closed.
- Names/icons come from the Android bridge; unavailable metadata falls back
  without blocking notifications. Browser storage and replay have finite limits.
- Separate verified behavior from suggestions or capabilities needing a
  third-party app test. The built-in Notification Bridge demo is fictional.
- Privacy descriptions match the code: local loopback website, no external
  services, no Android internet permission. Keep notification captures,
  private identifiers and signing keys out of published changes.

## Comprehension

- A new user can find prerequisites, setup, website launch, and verification.
- Distinguish continuous listening, snapshots, the demo and browser history.
- State meaningful operational limits directly or link to the exact guide.
- Avoid an implication that delivery notifications are the sole use case.

## Style and scope

- Use plain English, informative headings and actionable commands.
- Preserve useful examples without marketing claims or jargon.
- Do not require internal module documentation, a PRD template, or redundant
  implementation detail in an end-user README.
- Report only concrete discrepancies supported by the supplied files.
  Distinguish Blocker, Major and Nit; stylistic preferences alone are Nits.
