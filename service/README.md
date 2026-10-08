# Receiver services

Two background services, managed by launchd, that keep the receiver recording with no Terminal windows.

- `com.radio.dump1090`: runs dump1090 with the network feeds on, restarted automatically if it exits.
- `com.radio.recorder`: `recorder.py`, writes `raw_t_YYYYMMDD.txt` and `sbs_t_YYYYMMDD.txt` into `data/`,
  one line per message, prefixed with arrival time. Reconnects after 10 minutes of silence; after 20,
  restarts dump1090. Everything it does goes to `data/recorder.log`.

- `com.radio.snapshot`: `snapshot.sh`, four times a day (07:45, 12:15, 17:30, 21:30) stops dump1090, records
  60 s of raw I/Q samples with `rtl_sdr` (2.4 M samples/s, 288 MB per file) into `data/raw_iq/`, and starts
  dump1090 again, whatever happened in between. Keeps the newest 8 files. Skips a run, and says why in
  `data/snapshot.log`, if the folder is missing or its disk has under 20 GB free.

## Install (once, on the receiver)
1. Stop dump1090 and the recording loops in any Terminal windows (Ctrl-C, close the windows).
2. From `adsb/service`: `bash install.sh`

## Raw snapshots (`install_snapshot.sh`)
- Needs `rtl_sdr`: `brew install librtlsdr`. Then from `adsb/service`: `bash install_snapshot.sh`.
- Storage lives in one variable, `SNAP_DIR` (default `~/Projects/radio_transmission/data/raw_iq`). To use an
  external drive: `SNAP_DIR=/Volumes/<drive>/raw_iq bash install_snapshot.sh` (the path is written into the plist).
- Try one by hand: `bash snapshot.sh && tail -5 ~/Projects/radio_transmission/data/snapshot.log`.
- Why it does not upset the recorder: while dump1090 is down the recorder's sockets close and it retries every
  10 s (the `OSError` branch in `recorder.py`); its silence watchdog only counts a connection that stays open
  with no data, and its threshold is 600 s, ten times the 60 s pause. After a snapshot the log shows
  "port 30002: [Errno 61] Connection refused" a few times, then "connected"; that is normal.
- What the files are for: the raw samples let the project's own demodulator (`decode.py`) be run on real
  traffic, including the moments dump1090 accepts corrupt messages, which its text output cannot show.
  The files hold radio samples only, no positions.

## Everyday
- Status: `launchctl list | grep com.radio` (a number in the first column = running, with that process id)
- What happened: `tail -20 ~/Projects/radio_transmission/data/recorder.log`
- Restart dump1090 by hand: `launchctl kickstart -k gui/$(id -u)/com.radio.dump1090`
- Watch aircraft live: open http://localhost:8080 in a browser on the receiver

## Remove
```
launchctl bootout gui/$(id -u)/com.radio.snapshot
launchctl bootout gui/$(id -u)/com.radio.recorder
launchctl bootout gui/$(id -u)/com.radio.dump1090
rm ~/Library/LaunchAgents/com.radio.*.plist
```

Note: these run while you are logged in (locked screen is fine). After a restart of the receiver, log in once.
