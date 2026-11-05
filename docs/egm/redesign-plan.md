# Clean light inbox and Android app identity

The user chose a clean light inbox: white/slate surfaces, compact navigation,
clear app names, app icons, and a simple notification feed. The website serves
notifications from all apps; delivery apps are only examples.

## Implementation

1. Update Notification Bridge to include optional `apps` metadata in protocol
   version 1 state: a package-keyed object of `{label, icon}`, where `icon` is
   a bounded 64px PNG data URL rendered using Android PackageManager's app
   drawable. Cache once per package/service session; failures use label/package
   fallback and do not interrupt notification collection.
2. Add optional `apps` to the website API, keeping old APK compatibility. Store
   one metadata entry per source/package alongside browser history, so icons
   are not repeated in every event and remain visible offline. Validate PNG
   data URLs and metadata size. Account for metadata in existing storage limits.
3. Restyle `website/` as a clean light inbox, with local font fallbacks,
   accessible controls, app names/icons in rows and details, and neutral copy.
   Preserve existing real-time polling, history, search, filters and recovery.
4. Run regression tests and browser QA, build and verify the updated APK, then
   install it as an in-place update on the connected phone. Never uninstall
   the existing app to resolve a signing mismatch. Verify actual app metadata
   and the Notification Bridge lifecycle demo through the website.

## Shared file ownership

- Android agent: `android/src/dev/local/notificationbridge/NotificationBridge.java`.
- Backend/history agent: `website/server.py`, `website/history.js`, and their tests.
- Interface agent: `website/index.html`, `website/styles.css`, `website/app.js`.
- Primary agent: builds, device/browser integration, documentation and review.

Keep metadata additive and Python runtime dependency-free. Do not download
app icons from unrelated websites or use a delivery-app brand as the website
identity. No notification content should appear in logs or committed fixtures.

## Validation

The APK built and signature verification passed. The installed APK's signing
certificate matched the rebuild, and the phone accepted an in-place update.
The updated listener supplied three real 64px app PNG icons and labels.
The bundled APK and checksum were updated for subsequent setup commands.

All 44 Python tests and 27 browser-history JavaScript tests passed. Headless
Chrome checks passed for the redesigned desktop/mobile layout, app names,
decoded PNG icons, icon restoration after refresh and offline, existing
search/filter/history/recovery, and notification text safety. The actual-phone
website demo passed again, including a real decoded 64px Notification Bridge
icon, post/two updates/removal, progress, and saved history after refresh.

Screenshots under `/tmp` use fictional download and messaging notifications;
actual app names/icons are obtained locally from the phone.
