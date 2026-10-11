#!/bin/bash
# Install the nightly analysis update (com.radio.update) as a launchd service for the current user.
# Run once on the receiver machine, from adsb/service:   bash install_update.sh
# Uses the project's virtual environment (.venv), which has numpy, scipy, matplotlib and folium.
set -e

PROJ="$HOME/Projects/radio_transmission"
DATA="$PROJ/data"
PY="$PROJ/.venv/bin/python"
AGENTS="$HOME/Library/LaunchAgents"
UID_NUM=$(id -u)
mkdir -p "$AGENTS"

[ -x "$PY" ] || { echo "$PY not found; create the virtual environment first"; exit 1; }
command -v /opt/homebrew/bin/ffmpeg >/dev/null || echo "note: ffmpeg not found (brew install ffmpeg); flight videos will fail"

# 00:30: the recorder has started the new day's files, so yesterday's are complete.
# PATH includes Homebrew so matplotlib finds ffmpeg for the flight videos.
cat > "$AGENTS/com.radio.update.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.radio.update</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/caffeinate</string>
    <string>-i</string>
    <string>$PY</string>
    <string>$PROJ/adsb/update.py</string>
  </array>
  <key>WorkingDirectory</key><string>$PROJ/adsb</string>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/bin:/bin</string>
    <key>MPLBACKEND</key><string>Agg</string>
  </dict>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>0</integer><key>Minute</key><integer>30</integer></dict>
  <key>RunAtLoad</key><false/>
  <key>StandardOutPath</key><string>/dev/null</string>
  <key>StandardErrorPath</key><string>$DATA/update.err</string>
</dict></plist>
PLIST

launchctl bootout "gui/$UID_NUM/com.radio.update" 2>/dev/null || true
launchctl bootstrap "gui/$UID_NUM" "$AGENTS/com.radio.update.plist"

echo "Installed. Results are brought up to date every night at 00:30."
echo "  run it now:    launchctl kickstart gui/$UID_NUM/com.radio.update"
echo "  what happened: tail -20 $DATA/update.log"
