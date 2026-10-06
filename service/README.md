# Receiver services

Two background services, managed by launchd, that keep the receiver recording with no Terminal windows.

- `com.radio.dump1090`: runs dump1090 with the network feeds on, restarted automatically if it exits.
- `com.radio.recorder`: `recorder.py`, writes `raw_t_YYYYMMDD.txt` and `sbs_t_YYYYMMDD.txt` into `data/`,
  one line per message, prefixed with arrival time. Reconnects after 10 minutes of silence; after 20,
  restarts dump1090. Everything it does goes to `data/recorder.log`.

## Install (once, on the receiver)
1. Stop dump1090 and the recording loops in any Terminal windows (Ctrl-C, close the windows).
2. From `adsb/service`: `bash install.sh`

## Everyday
- Status: `launchctl list | grep com.radio` (a number in the first column = running, with that process id)
- What happened: `tail -20 ~/Projects/radio_transmission/data/recorder.log`
- Restart dump1090 by hand: `launchctl kickstart -k gui/$(id -u)/com.radio.dump1090`
- Watch aircraft live: open http://localhost:8080 in a browser on the receiver

## Remove
```
launchctl bootout gui/$(id -u)/com.radio.recorder
launchctl bootout gui/$(id -u)/com.radio.dump1090
rm ~/Library/LaunchAgents/com.radio.*.plist
```

Note: these run while you are logged in (locked screen is fine). After a restart of the receiver, log in once.
