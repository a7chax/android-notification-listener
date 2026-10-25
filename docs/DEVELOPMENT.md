# Build and test

## Use the included APK

The ready-to-install APK is `artifacts/notification-bridge-debug.apk`.
It includes the notification listener and the simulated live notification.
`setup` selects this APK by default.

```bash
uv run listener.py setup
```

To check the file checksum, run this command from the project directory:

```bash
sha256sum -c artifacts/SHA256SUMS
```

## Prepare the build tools

1. Install a JDK. JDK 17 or later is recommended.

2. Install Android SDK platform 35 or later.

3. Install Android SDK build-tools 35 or later.

4. Set `ANDROID_HOME` to your Android SDK directory.

The build uses `aapt2`, `javac`, `d8`, `zipalign`, and `apksigner`.
It does not use Gradle or Maven downloads.

## Build the Android app

```bash
uv run build_android.py
```

The APK is `build/notification-bridge.apk`.
The build command also checks its signature.

Keep `build/debug.keystore` for later builds.
Android requires the same signing key for an app update.
Do not publish this key.

To build and install an update, use this command:

```bash
uv run listener.py setup --rebuild
```

This command uses the source build instead of the included APK.
A new signing key cannot update an app signed with another key.
If Android rejects the update, remove the existing debug app before installation.

## Update the included APK

1. Build the source with `uv run build_android.py`.

2. Copy the verified APK.

   ```bash
   cp build/notification-bridge.apk artifacts/notification-bridge-debug.apk
   ```

3. Update the checksum.

   ```bash
   sha256sum artifacts/notification-bridge-debug.apk > artifacts/SHA256SUMS
   ```

4. Test the included APK before publication.

Keep the signing key and runtime notification data outside Git.

## Run unit tests

```bash
uv run python -m unittest discover -s tests -v
```

These tests do not need a connected phone.

## Test a live notification

1. Connect a phone with notification access enabled.

2. Start the listener in one terminal.

   ```bash
   uv run listener.py listen --package dev.local.notificationbridge --format text
   ```

3. Start the test notification in another terminal.

   ```bash
   uv run listener.py demo
   ```

The test changes text and progress twice under one notification key.
It removes the notification after nine seconds.
The standard title and text fields are empty by design.

## Run the device test

```bash
uv run tests/device_smoke.py
```

This test needs an existing notification to confirm the initial read.
It opens the test app and then moves it to the background.
It checks custom text, progress, updates, and removal.
The test has no dependency on a delivery app or another third-party app.

## Main files

| File | Purpose |
| --- | --- |
| `listener.py` | Read Android events and produce JSON or text. |
| `build_android.py` | Build and sign the Android app. |
| `android/src/.../NotificationBridge.java` | Receive Android notification events and extract content. |
| `android/src/.../MainActivity.java` | Show access settings and create test notifications. |
| `tests/` | Check computer behavior and connected-device behavior. |
| `listen.sh` | Start the listener through a generic shell shortcut. |

The Android app has no internet permission.
Its debug mode lets authorized ADB connections read its private state with `run-as`.
This app is a local development tool.

## Source references

- [Android notification listener](https://developer.android.com/reference/android/service/notification/NotificationListenerService)
- [Android custom notification views](https://developer.android.com/reference/android/widget/RemoteViews)
