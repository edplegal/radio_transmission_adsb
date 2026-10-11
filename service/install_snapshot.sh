#!/bin/bash
# Install the raw I/Q snapshot job (com.radio.snapshot) as a launchd service for the current user.
# Run once on the receiver machine, from adsb/service:   bash install_snapshot.sh
# Needs rtl_sdr (brew install librtlsdr) and the dump1090 service from install.sh.
set -e

PROJ="$HOME/Projects/radio_transmission"
DATA="$PROJ/data"
SNAP_DIR="${SNAP_DIR:-$DATA/raw_iq}"
AGENTS="$HOME/Library/LaunchAgents"
UID_NUM=$(id -u)
mkdir -p "$AGENTS" "$SNAP_DIR"

[ -x /opt/homebrew/bin/rtl_sdr ] || { echo "rtl_sdr not found; brew install librtlsdr"; exit 1; }
[ -f "$AGENTS/com.radio.dump1090.plist" ] || { echo "dump1090 service not installed; run install.sh first"; exit 1; }

# 10:00, 13:30, 15:30, 17:00 local time: the busiest quarter-hours in the Oct 6-11 recordings (median
# 26-31 aircraft heard per 15 minutes; traffic is roughly flat 10:00-20:00 and thin after 22:00).
cat > "$AGENTS/com.radio.snapshot.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.radio.snapshot</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string>
    <string>$PROJ/adsb/service/snapshot.sh</string>
  </array>
  <key>EnvironmentVariables</key><dict>
    <key>SNAP_DIR</key><string>$SNAP_DIR</string>
  </dict>
  <key>StartCalendarInterval</key><array>
    <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>13</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>15</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>17</integer><key>Minute</key><integer>0</integer></dict>
  </array>
  <key>RunAtLoad</key><false/>
  <key>StandardErrorPath</key><string>$DATA/snapshot.err</string>
</dict></plist>
PLIST

launchctl bootout "gui/$UID_NUM/com.radio.snapshot" 2>/dev/null || true
launchctl bootstrap "gui/$UID_NUM" "$AGENTS/com.radio.snapshot.plist"

echo "Installed. Snapshots go to $SNAP_DIR at 10:00, 13:30, 15:30 and 17:00."
echo "  try one now:   bash $PROJ/adsb/service/snapshot.sh && tail -5 $DATA/snapshot.log"
echo "  status:        launchctl list | grep com.radio.snapshot"
