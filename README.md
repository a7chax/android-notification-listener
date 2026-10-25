# Android Notification Listener

Read Android notifications on your computer through ADB.
The listener receives notifications from **all apps** by default.
It records new notifications, updates, and removals.
It can read text from custom notification views, including some live activities.

## App examples

The following apps are examples to try.
Only Gojek custom-view text extraction was verified during development.
Other apps need a test on your phone.

| Example apps | Notification data to look for |
| --- | --- |
| Gojek | Food delivery status and live activity text |
| Grab, Uber | Ride status, driver arrival, and trip updates |
| Google Maps | Navigation instructions and arrival estimates |
| WhatsApp, Telegram | Message previews and conversation updates |
| Spotify, YouTube Music | Track titles and playback information |
| Chrome and download apps | Download status and progress |
| Clock and timer apps | Timer alerts and ongoing status |

The listener reads the notification content that Android supplies.
Available fields depend on the app, Android version, and privacy settings.
An app must post a notification change for the listener to record an update.

For example, a delivery app can update one notification as an order progresses.
The listener connects these updates through the same notification key.
It does not read the app's private database or control the order.

Android supports ongoing status for rides, deliveries, and navigation.
See [Android live update notifications](https://developer.android.com/develop/ui/views/notifications/live-update).

## Possible uses

- Record notification changes for app tests.
- Show delivery status on a local dashboard.
- Check progress from downloads and ongoing tasks.
- Supply notification events to a local automation tool.

These are possible uses. This project supplies the event stream.

## Requirements

- An Android 8 or later phone with USB debugging enabled.
- ADB, Python 3.10 or later, and `uv` on your computer.
- A JDK and Android SDK tools to build the Android app.

Python uses no external packages.
The Android app has no internet permission.

## Get the project

1. Download the source.

   ```bash
   git clone https://github.com/a7chax/android-notification-listener.git
   ```

2. Open the project directory.

   ```bash
   cd android-notification-listener
   ```

## Start the listener

1. Connect your phone with a USB cable.

2. Check the connection.

   ```bash
   adb devices
   ```

   The device status must be `device`.
   If the phone shows a USB debugging request, select **Allow**.

3. Install the Android listener app.

   ```bash
   uv run listener.py setup
   ```

   This command builds the APK and installs it on your phone.
   It also requests notification access.
   If Android opens the access settings, enable **Notification Bridge**.

4. Start the text output.

   ```bash
   uv run listener.py listen --format text
   ```

   **The command stays running. New lines appear when notifications change.**
   The phone screen can be off.
   You do not need scrcpy or an open notification panel.

5. Press **Ctrl-C** to stop the listener.

## Save JSON events

1. Start the file output.

   ```bash
   uv run listener.py listen --output notifications.jsonl
   ```

   Events go to the file. The terminal shows status messages.
   The command adds new events after existing file content.

2. To view the file, open another terminal in the project directory.

3. Run this command.

   ```bash
   tail -f notifications.jsonl
   ```

For one capture that stops automatically, use this command:

```bash
uv run listener.py snapshot --output notifications.jsonl
```

## Protect your data

Notification text can contain personal data.
The phone stores notification data in the listener app's private directory.
ADB copies this data to your computer.
Package filters limit computer output. They do not limit phone storage.

The Git ignore rules exclude captures, screenshots, local settings, and signing keys.
Sample notification content and device identifiers are fictional.

## More information

- [Command reference and output fields](docs/REFERENCE.md)
- [Tests and build instructions](docs/DEVELOPMENT.md)

This documentation uses short instructions based on
[ASD-STE100 writing rules](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf).
Software names and command names are technical terms.
