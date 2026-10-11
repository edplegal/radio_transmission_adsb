# Receiver services

Two background services, managed by launchd, that keep the receiver recording with no Terminal windows.

- `com.radio.dump1090`: runs dump1090 with the network feeds on (through `run_dump1090.sh`, which timestamps
  every line of dump1090's diagnostic output into `data/dump1090.log`, plus its own start and dump1090's exit),
  restarted automatically if it exits.
- `com.radio.recorder`: `recorder.py`, writes `raw_t_YYYYMMDD.txt` and `sbs_t_YYYYMMDD.txt` into `data/`,
  one line per message, prefixed with arrival time. Reconnects after 10 minutes of silence; after 20,
  restarts dump1090. Everything it does goes to `data/recorder.log`.

- `com.radio.snapshot`: `snapshot.sh`, four times a day at the busiest hours (10:00, 13:30, 15:30, 17:00) stops dump1090, records
  60 s of raw I/Q samples with `rtl_sdr` (2.4 M samples/s, 288 MB per file) into `data/raw_iq/`, and starts
  dump1090 again, whatever happened in between. Keeps the newest 8 files. Skips a run, and says why in
  `data/snapshot.log`, if the folder is missing or its disk has under 20 GB free.

- `com.radio.update`: `adsb/update.py`, every night at 00:30 (after midnight has closed the day's files),
  brings the analysis up to date with whatever was recorded: decodes new raw snapshots once each (results
  kept in `adsb/results/compare24/`, so they survive the 8-file rotation), reruns the synthetic and
  test-recording results only when the code changed, and rebuilds `adsb/results/summary_alldata.md` from
  every recording in `data/` and `backupData/`. Log: `data/update.log`.

## Install (once, on the receiver machine)
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

## Nightly analysis (`install_update.sh`)
- Needs the project's `.venv` and `ffmpeg` (`brew install ffmpeg`, for the flight videos). Then from
  `adsb/service`: `bash install_update.sh`.
- Run it now instead of waiting: `launchctl kickstart gui/$(id -u)/com.radio.update`, or by hand from `adsb/`:
  `../.venv/bin/python update.py` (`--all` also forces the code-only results).
- Positions, coverage and flights need `adsb/receiver.py` (`RECEIVER = (lat, lon)`, git-ignored); without it
  the summary says those sections are pending and everything else is still computed.

## Everyday
- Status: `launchctl list | grep com.radio` (a number in the first column = running, with that process id)
- What happened: `tail -20 ~/Projects/radio_transmission/data/recorder.log` and `... /data/dump1090.log`
  (a hang shows as a recorder restart in the first and a `starting dump1090` line in the second)
- Restart dump1090 by hand: `launchctl kickstart -k gui/$(id -u)/com.radio.dump1090`
- Watch aircraft live: open http://localhost:8080 in a browser on the receiver machine

## Remove
```
launchctl bootout gui/$(id -u)/com.radio.update
launchctl bootout gui/$(id -u)/com.radio.snapshot
launchctl bootout gui/$(id -u)/com.radio.recorder
launchctl bootout gui/$(id -u)/com.radio.dump1090
rm ~/Library/LaunchAgents/com.radio.*.plist
```

Note: these run while you are logged in (locked screen is fine). After a restart of the receiver machine, log in once.
