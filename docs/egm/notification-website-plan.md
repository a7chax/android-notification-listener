# Notification website: working hypothesis

* **Author:** a7chax
* **Date:** 2026-11-06
* **Status:** Reviewed by six Goldfish lenses; implemented in `website/`.

## Request

Build a website in `website/` that lists Android notifications and saves
them in browser local storage for now.

## Existing project

`listener.py` already reads Android notification events through ADB. Its
events include snapshots, new notifications, updates, and removals. A stable
notification key connects changes to the same notification. The project
currently has no website or HTTP server and uses Python without external
dependencies.

## Proposed starting point

Run a local Python server that serves the files in `website/` and passes
notification events from the existing bridge to the browser. The browser
shows notifications and saves its received data in local storage. Reloading
the page restores saved data. The page remains useful for reading saved
notifications when the phone is disconnected, with a visible connection
status.

The initial interface should show the app package, readable notification
text, and timestamps, with search and app filtering. Custom-view text must
remain visible because some delivery notifications do not have standard
title and text fields.

Local storage belongs to one browser and website address. It cannot capture
events while the page is closed; the listener's phone-side journal is also
bounded. This first version should not promise a complete permanent archive.

## Approaches to evaluate

1. A local server and browser local storage: connects to the existing ADB
   listener and supports live viewing without adding a database.
2. A static page with manual JSON event import: simpler to serve, but needs
   a manual capture/import step and does not provide live notifications.
3. A local server with a database: can retain events while the browser is
   closed, but introduces storage beyond the requested first version.

The proposed starting point is option 1. No alternatives have been rejected
by the user.

## Confirmed history behavior

The user confirmed that history should be kept when notifications change
or disappear. Preserve notification updates and removals in the browser's
saved history. A removal on the phone must not delete its saved record on
the website. Restore saved history after a page refresh.

## Anchored working hypothesis for review

Build a local notification website in `website/`, connected to the existing
ADB listener through a local Python server. Show live notifications, search
and app filters, and preserve their updates and dismissals as history in
browser local storage. Restore saved history on refresh and make connection
or storage failures visible rather than silently discarding data.

## Implementation

The user confirmed the hypothesis and review, then requested shared-agent
implementation. See [the reviewed brief](concepts_brief.md),
[implementation plan](implementation-plan.md), and [validation](validation.md).
