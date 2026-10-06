"""Record dump1090's two network feeds to daily, timestamped files, and keep the chain alive.

Runs as a background service (see install.sh). For each feed it:
  - connects to dump1090 and stamps every line with its arrival time,
  - writes each line into the file for the day that line arrived, so midnight always starts a new file,
  - treats a long silence as a dead link: reconnects, and if the silence continues,
    restarts dump1090 through launchd (which also resets the dongle in most cases).
Everything it does is logged to recorder.log next to the data.
"""
import logging
import os
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime

DATA = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/Projects/radio_transmission/data")
FEEDS = {"raw": 30002, "sbs": 30003}       # file prefix -> dump1090 port
SILENCE_S = 600                            # this long with no lines = the link is considered dead
DUMP1090_LABEL = f"gui/{os.getuid()}/com.radio.dump1090"
RESTART_COOLDOWN_S = 900                   # never restart dump1090 more often than this

os.makedirs(DATA, exist_ok=True)
logging.basicConfig(filename=os.path.join(DATA, "recorder.log"), level=logging.INFO,
                    format="%(asctime)s %(threadName)s %(message)s")
restart_lock = threading.Lock()
last_restart = 0.0


def restart_dump1090(reason):
    global last_restart
    with restart_lock:
        if time.time() - last_restart < RESTART_COOLDOWN_S:
            return
        last_restart = time.time()
    logging.warning("restarting dump1090: %s", reason)
    try:
        subprocess.run(["launchctl", "kickstart", "-k", DUMP1090_LABEL], check=False)
    except OSError as e:
        logging.error("could not restart dump1090: %s", e)


class DailyFile:
    """Append lines to <prefix>_t_<YYYYMMDD>.txt, switching files when the date changes."""

    def __init__(self, prefix):
        self.prefix, self.day, self.f = prefix, None, None

    def write(self, t, line):
        day = datetime.fromtimestamp(t).strftime("%Y%m%d")
        if day != self.day:
            if self.f:
                self.f.close()
            self.day = day
            self.f = open(os.path.join(DATA, f"{self.prefix}_t_{day}.txt"), "a")
            logging.info("writing %s_t_%s.txt", self.prefix, day)
        self.f.write(f"{t:.3f},{line}\n")
        self.f.flush()


def record(prefix, port):
    out = DailyFile(prefix)
    silent_links = 0                        # consecutive connections that went silent
    while True:
        try:
            with socket.create_connection(("localhost", port), timeout=10) as s:
                s.settimeout(SILENCE_S)
                logging.info("connected to port %d", port)
                buf = b""
                while True:
                    chunk = s.recv(65536)
                    if not chunk:
                        raise ConnectionError("dump1090 closed the connection")
                    silent_links = 0
                    buf += chunk
                    *lines, buf = buf.split(b"\n")
                    now = time.time()
                    for line in lines:
                        line = line.decode("ascii", "replace").strip()
                        if line:
                            out.write(now, line)
        except socket.timeout:
            silent_links += 1
            logging.warning("no data for %d s on port %d (silent links in a row: %d)",
                            SILENCE_S, port, silent_links)
            if silent_links >= 2:
                restart_dump1090(f"port {port} silent for {silent_links * SILENCE_S} s")
                silent_links = 0
        except OSError as e:                # refused, closed, reset: dump1090 down or restarting
            logging.warning("port %d: %s", port, e)
            time.sleep(10)


if __name__ == "__main__":
    logging.info("recorder starting, data in %s", DATA)
    threads = [threading.Thread(target=record, args=(p, port), name=p, daemon=True)
               for p, port in FEEDS.items()]
    for th in threads:
        th.start()
    while all(th.is_alive() for th in threads):
        time.sleep(60)
    logging.error("a recorder thread died; exiting so launchd restarts us")
    sys.exit(1)
