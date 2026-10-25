# Command reference

## Select apps

The listener reads all apps by default.
To select one app, supply its package name.

```bash
uv run listener.py listen --package com.example.app --format text
```

To select more apps, repeat `--package`.

```bash
uv run listener.py listen --package com.example.app --package com.example.other
```

Package names must match exactly.
Replace the example names with installed app package names.

## Select a device

1. Get the device serial number.

   ```bash
   adb devices
   ```

2. Replace `YOUR_DEVICE_SERIAL` in this command.

   ```bash
   uv run listener.py listen --serial YOUR_DEVICE_SERIAL
   ```

## Set a time limit

To stop after 30 seconds, use this command:

```bash
uv run listener.py listen --duration 30
```

The default read interval is 0.5 seconds.
To change the interval, use `--interval`.

```bash
uv run listener.py listen --interval 1
```

## Check the connection

```bash
uv run listener.py doctor
```

This command checks ADB, notification access, and the listener heartbeat.
The heartbeat check takes approximately six seconds.

## Event types

| Event | Meaning |
| --- | --- |
| `snapshot` | A notification exists when the computer first reads the state. |
| `posted` | An app posts a new notification. |
| `updated` | An app changes an existing notification. |
| `removed` | Android removes a notification. |

Use `notification.key` to connect updates to the same notification.
A notification ID alone is not unique across apps.

## JSON example

The following example is fictional. It omits some fields.

```json
{"event":"updated","seq":2,"session":"example-session","timestamp":1700000000000,"notification":{"key":"example-key","package":"com.example.app","id":7,"title":null,"text":null,"view_text":["Download in progress"],"progress":{"value":55,"max":100,"indeterminate":false}}}
```

Each line in a JSON Lines file contains one event.
Timestamps use Unix milliseconds.

| Notification field | Content |
| --- | --- |
| `title`, `text`, `big_text`, `sub_text`, `lines` | Standard notification text |
| `view_text` | Text and labels from custom views |
| `views` | Text with resource IDs and view sources |
| `progress`, `view_progress` | Standard and custom progress values |
| `channel`, `ongoing`, `group_summary` | Notification properties |
| `custom_view` | An indicator for custom views |
| `extraction_errors` | Custom views that the listener could not read |

A removed event contains the last available content and Android's numeric `removal_reason`.

## Limits

- Android controls which notifications and text the listener can receive.
- The listener cannot recover text that Android hides.
- The listener does not read text from images.
- Animation frames and clock changes do not create notification events by themselves.
- The phone stores the latest 256 events and the current notifications.
- Short ADB interruptions can recover events from this stored data.
- If stored events are missing, the computer reports the gap and reads the current state.
- A service restart starts a new session with current-state events.
- The listener does not guarantee permanent event storage during phone restarts.

## Solve connection problems

| Condition | Action |
| --- | --- |
| The command stays open. | This is normal for `listen`. Press Ctrl-C to stop it. |
| No lines appear with `--output`. | Read the output file with `tail -f`. |
| The ready message shows zero notifications. | Wait for a new notification. |
| ADB shows `unauthorized`. | Accept the USB debugging request on the phone. |
| Notification access is disabled. | Run `setup` again. |
| The heartbeat stops. | Check background activity settings for Notification Bridge. |

To remove the Android app, use this command:

```bash
adb uninstall dev.local.notificationbridge
```
