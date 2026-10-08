#!/bin/bash
# Take a 60-second raw I/Q snapshot from the dongle, then hand the dongle back to dump1090.
#
# Only one program can own the dongle, so dump1090 is stopped for the duration and restarted
# afterwards no matter what happened in between. Run by launchd (com.radio.snapshot) four times
# a day; can also be run by hand:   bash snapshot.sh
#
# Storage: SNAP_DIR (one place to change, e.g. to an external drive). A run is skipped, with the
# reason logged, when SNAP_DIR is missing or its disk has under MIN_FREE_GB free. Only the newest
# KEEP files are kept. Each file is 60 s x 2.4 M samples/s x 2 bytes = 288 MB.
#
# Privacy (CLAUDE.md): the recording holds radio samples only, no position; it stays in data/,
# which is not in the repository.

SNAP_DIR="${SNAP_DIR:-$HOME/Projects/radio_transmission/data/raw_iq}"
LOG="${LOG:-$HOME/Projects/radio_transmission/data/snapshot.log}"
KEEP="${KEEP:-8}"
MIN_FREE_GB="${MIN_FREE_GB:-20}"
SECONDS_TO_RECORD=60
RATE=2400000                                        # samples per second
FREQ=1090000000
GAIN=40
DUMP1090_LABEL="gui/$(id -u)/com.radio.dump1090"
DUMP1090_PLIST="$HOME/Library/LaunchAgents/com.radio.dump1090.plist"
RTL_SDR="${RTL_SDR:-/opt/homebrew/bin/rtl_sdr}"     # overridable for testing without a dongle
LAUNCHCTL="${LAUNCHCTL:-launchctl}"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

mkdir -p "$(dirname "$LOG")"

# --- preconditions: never stop dump1090 for a run that cannot record -------------------------
if [ ! -d "$SNAP_DIR" ]; then
  log "skip: SNAP_DIR $SNAP_DIR does not exist"
  exit 0
fi
free_kb=$(df -k "$SNAP_DIR" | awk 'NR == 2 { print $4 }')
if [ -z "$free_kb" ] || [ "$free_kb" -lt $((MIN_FREE_GB * 1024 * 1024)) ]; then
  log "skip: only $((free_kb / 1024 / 1024)) GB free on $SNAP_DIR's disk (need $MIN_FREE_GB)"
  exit 0
fi
if [ ! -x "$RTL_SDR" ]; then
  log "skip: $RTL_SDR not found or not executable"
  exit 0
fi

# --- record, with dump1090 stopped, and restart dump1090 whatever happens --------------------
stamp=$(date '+%Y%m%d_%H%M')
out="$SNAP_DIR/iq_${RATE%000}k_${stamp}.bin"
restart_dump1090() {
  if "$LAUNCHCTL" bootstrap "gui/$(id -u)" "$DUMP1090_PLIST" 2>>"$LOG"; then
    log "dump1090 started"
  else
    log "ERROR: could not start dump1090 (launchctl bootstrap failed); try: launchctl bootstrap gui/$(id -u) $DUMP1090_PLIST"
  fi
}
trap restart_dump1090 EXIT                         # runs on normal exit, on error, and on kill

log "snapshot start -> $out"
if "$LAUNCHCTL" bootout "$DUMP1090_LABEL" 2>>"$LOG"; then
  log "dump1090 stopped"
else
  log "dump1090 was not running (bootout failed); recording anyway"
fi
sleep 2                                             # let the dongle be released

"$RTL_SDR" -f "$FREQ" -s "$RATE" -g "$GAIN" -n $((SECONDS_TO_RECORD * RATE)) "$out" >>"$LOG" 2>&1
rc=$?
if [ "$rc" -eq 0 ]; then
  log "recorded $(du -h "$out" | cut -f1) to $out"
else
  log "ERROR: rtl_sdr failed (exit $rc); removing partial file"
  rm -f "$out"
fi

# --- retention: newest KEEP files stay, the rest go --------------------------------------------
old=$(ls -t "$SNAP_DIR"/iq_*.bin 2>/dev/null | tail -n +$((KEEP + 1)))
if [ -n "$old" ]; then
  echo "$old" | xargs rm -f
  log "retention: removed $(echo "$old" | wc -l | tr -d ' ') old snapshot(s), keeping newest $KEEP"
fi
log "snapshot done; $(ls "$SNAP_DIR"/iq_*.bin 2>/dev/null | wc -l | tr -d ' ') file(s) in $SNAP_DIR"
