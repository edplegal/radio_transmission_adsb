#!/bin/bash
# Run dump1090 for launchd (com.radio.dump1090) with every line of its diagnostic output timestamped.
#
# dump1090 writes device messages and errors to stderr with no time on them, so a log of a day's hangs
# cannot say when they happened. This wrapper stamps each stderr line and appends it to data/dump1090.log,
# and records its own start and dump1090's exit. stdout (the decoded-message stream) goes to /dev/null;
# the network feeds carry it. launchd's KeepAlive restarts this script when dump1090 exits.
PROJ="$HOME/Projects/radio_transmission"
LOG="$PROJ/data/dump1090.log"
DUMP1090="${DUMP1090:-$PROJ/dump1090/dump1090}"      # overridable for testing

stamp() { while IFS= read -r line; do printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$line"; done; }

cd "$(dirname "$DUMP1090")"
echo "$(date '+%Y-%m-%d %H:%M:%S') starting dump1090 --net --gain 40" >> "$LOG"
/usr/bin/caffeinate -i "$DUMP1090" --net --gain 40 2>&1 >/dev/null | stamp >> "$LOG"
echo "$(date '+%Y-%m-%d %H:%M:%S') dump1090 exited with status ${PIPESTATUS[0]}" >> "$LOG"
