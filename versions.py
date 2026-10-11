"""Replay every version of the decoder on modes1.bin against the same answer key, for the report's table."""
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

from compare import DUMP1090_READ_LIMIT, RECORDING, TRUTH, is_adsb, load_key
from decode import load_mag

VERSIONS = [                       # commit, label, keyword arguments the version accepts
    ("06548b6", "Sep 28: strict preamble, k=4, skip 240 after a pass", {}),
    ("e8b6618", "Oct 5: any preamble, k=3, dedupe same hex", {}),
    ("HEAD", "Oct 7: keep stronger preamble of overlapping reads", {}),
    ("HEAD", "Oct 7: same, with repair_bits", {"repair_bits": True}),
]


def load_version(commit, tmp):
    src = subprocess.run(["git", "show", f"{commit}:decode.py"], capture_output=True, text=True, check=True).stdout
    path = Path(tmp) / f"decode_{commit}.py"
    path.write_text(src)
    spec = importlib.util.spec_from_file_location(f"decode_{commit}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


if __name__ == "__main__":
    key = load_key(TRUTH)
    mag = load_mag(RECORDING)
    print(f"answer key: {len(key)} ADS-B messages from dump1090 (first {DUMP1090_READ_LIMIT} samples)\n")
    print(f"{'commit':8} {'version':58} {'found':>5} {'missed':>6} {'extra':>5} {'recovery':>8}  all reads")
    with tempfile.TemporaryDirectory() as tmp:
        for commit, label, kwargs in VERSIONS:
            mod = load_version(commit, tmp)
            found = mod.decode(mag, **kwargs)
            mine = {m for start, m in found if is_adsb(m) and start < DUMP1090_READ_LIMIT}
            ghosts = sum(1 for _, m in found if m.startswith(("46", "47")))
            print(f"{commit:8} {label:58} {len(key & mine):5d} {len(key - mine):6d} {len(mine - key):5d}"
                  f" {len(key & mine) / len(key):7.0%}  {len(found)} reads, {ghosts} format-8 ghosts")
