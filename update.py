"""Bring every result up to date with the recordings. Run nightly by launchd (com.radio.update, see
service/install_update.sh) after midnight has closed the day's files, or by hand:  python update.py

Each step redoes only what new data or changed code calls for:
  - raw I/Q snapshots: compare24.py decodes each file once and keeps the result in results/compare24/,
    so results outlive snapshot.sh's rotation (it keeps only the newest 8 files);
  - the test recording and synthetic sweeps (versions, compare, sweep_rates and the figures of
    sittings 5-6): rerun only when the code changed, judged by a hash of adsb/*.py;
  - summarize.py: rebuilt from every recording each run (a few minutes); its per-day flight videos
    are reused while that day's files are unchanged.
What ran, how long it took and anything that failed goes to data/update.log.
"""
import glob
import hashlib
import logging
import os
import subprocess
import sys
import time

from paths import ADSB, DATA, RESULTS

PY = sys.executable
CODE_HASH = os.path.join(RESULTS, ".code_hash")
# scripts that depend only on the code and the bundled test recording: (script, file for its output)
CODE_ONLY = [("versions.py", "versions.txt"), ("compare.py", "compare.txt"), ("sweep_rates.py", "sweep_rates.txt"),
             ("bitplot.py", "bitplot.txt"), ("interfere.py", "interfere.txt"), ("timing.py", "timing.txt")]


def code_hash():
    h = hashlib.sha256()
    for p in sorted(glob.glob(os.path.join(ADSB, "*.py"))):
        with open(p, "rb") as f:
            h.update(os.path.basename(p).encode() + f.read())
    return h.hexdigest()


def step(script, *args, out=None):
    """Run one script from adsb/; log its duration and, on failure, the end of its output."""
    t0 = time.time()
    r = subprocess.run([PY, script, *args], cwd=ADSB, capture_output=True, text=True)
    if out:
        with open(os.path.join(RESULTS, out), "w") as f:
            f.write(r.stdout)
    status = "ok" if r.returncode == 0 else f"FAILED (exit {r.returncode}): {(r.stderr or r.stdout)[-400:].strip()}"
    logging.info("%s %s: %s in %.0f s", script, " ".join(args), status, time.time() - t0)
    return r.returncode == 0


def main():
    os.makedirs(os.path.join(RESULTS, "compare24"), exist_ok=True)
    os.makedirs(os.path.join(ADSB, "captures"), exist_ok=True)
    logging.info("update start")
    ok = step("compare24.py")
    h = code_hash()
    old = open(CODE_HASH).read() if os.path.exists(CODE_HASH) else None
    if h != old or "--all" in sys.argv:
        good = all([step(s, out=o) for s, o in CODE_ONLY])
        if good:
            with open(CODE_HASH, "w") as f:
                f.write(h)
        ok &= good
    else:
        logging.info("code unchanged since the last run: synthetic and test-recording results kept")
    ok &= step("summarize.py")
    logging.info("update done%s", "" if ok else " WITH FAILURES (see above)")
    return 0 if ok else 1


if __name__ == "__main__":
    handlers = [logging.FileHandler(os.path.join(DATA, "update.log"))]
    if sys.stderr.isatty():                         # by hand: also show progress; under launchd: log only
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", handlers=handlers)
    sys.exit(main())
