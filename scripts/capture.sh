#!/bin/bash

set -e

OUTPUT_DIR="gojek-notification"
mkdir -p "$OUTPUT_DIR"

echo "Capturing Android UI hierarchy..."

# Dump currently visible Android UI
adb shell uiautomator dump /sdcard/window.xml

# Copy XML to computer
adb pull /sdcard/window.xml "$OUTPUT_DIR/window.xml"

echo "Capturing screenshot..."

# Take screenshot of current screen
adb exec-out screencap -p > "$OUTPUT_DIR/screenshot.png"

echo "Capturing Gojek notification metadata..."

# Capture all notification information
adb shell dumpsys notification --noredact \
  > "$OUTPUT_DIR/notifications.txt"

echo "Extracting Gojek-related entries..."

grep -i -C 15 "com.gojek.app" \
  "$OUTPUT_DIR/notifications.txt" \
  > "$OUTPUT_DIR/gojek.txt" || true

echo "Done!"
echo "Files saved to: $OUTPUT_DIR"
