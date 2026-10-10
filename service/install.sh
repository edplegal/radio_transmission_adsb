#!/bin/bash
# Install dump1090 and the recorder as launchd services for the current user.
# Run once on the receiver machine, from adsb/service:   bash install.sh
# Stop any dump1090 and recording loops running in Terminal windows first.
set -e

PROJ="$HOME/Projects/radio_transmission"
DATA="$PROJ/data"
AGENTS="$HOME/Library/LaunchAgents"
UID_NUM=$(id -u)
mkdir -p "$AGENTS" "$DATA"

[ -x "$PROJ/dump1090/dump1090" ] || { echo "dump1090 not found at $PROJ/dump1090/dump1090"; exit 1; }

cat > "$AGENTS/com.radio.dump1090.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.radio.dump1090</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string>
    <string>$PROJ/adsb/service/run_dump1090.sh</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>/dev/null</string>
  <key>StandardErrorPath</key><string>$DATA/dump1090.err</string>
</dict></plist>
PLIST

cat > "$AGENTS/com.radio.recorder.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.radio.recorder</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/python3</string>
    <string>$PROJ/adsb/service/recorder.py</string>
    <string>$DATA</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardErrorPath</key><string>$DATA/recorder.err</string>
</dict></plist>
PLIST

for name in dump1090 recorder; do
  launchctl bootout "gui/$UID_NUM/com.radio.$name" 2>/dev/null || true
  launchctl bootstrap "gui/$UID_NUM" "$AGENTS/com.radio.$name.plist"
done

echo "Installed. Check in a minute with:"
echo "  launchctl list | grep com.radio"
echo "  tail $DATA/recorder.log $DATA/dump1090.log"
