"""Fair comparison on the raw snapshots: the 2.0 MHz decoder on a resampled copy versus the 2.4 MHz
decoder on the original, with repair off and on.

For each snapshot in data/raw_iq: resample the complex samples 2.4 -> 2.0 MHz (polyphase, 5/6),
take the magnitude, run decode.decode; run decode24.decode on the original magnitude. Report
distinct checksum-valid 112-bit messages per decoder and mode, messages only one decoder found,
and whether each decoded aircraft address appears in more than one message of that recording
(an address seen once is the signature of a false message that happened to pass the checksum).
Each snapshot's result is kept in results/compare24/<snapshot>.md and never recomputed (pass --force
to redo), so results outlive snapshot.sh's rotation, which keeps only the newest 8 files.
results/compare24.md (git-ignored) gathers every result kept so far.
"""
import glob
import os
import sys
from collections import Counter

import numpy as np
from scipy.signal import resample_poly

import decode
import decode24
from paths import RAW_IQ

CHUNK = 2_400_000 * 10                            # resample 10 s at a time
EDGE = 2400                                       # overlap to hide the filter's edges


def load_iq(path):
    x = np.fromfile(path, dtype=np.uint8).astype(np.float32)
    return (x[0::2] - 127.5) + 1j * (x[1::2] - 127.5)


def resampled_mag(iq):
    """|iq| after polyphase resampling 2.4 MHz -> 2.0 MHz, done in chunks with overlap."""
    out = []
    n = len(iq)
    for a in range(0, n, CHUNK):
        lo, hi = max(0, a - EDGE), min(n, a + CHUNK + EDGE)
        y = resample_poly(iq[lo:hi], 5, 6)
        cut_lo = (a - lo) * 5 // 6
        cut_hi = cut_lo + (min(n, a + CHUNK) - a) * 5 // 6
        out.append(np.abs(y[cut_lo:cut_hi]).astype(np.float32))
    return np.concatenate(out)


def address(m):
    """Aircraft address of a 112-bit message when the format carries one in the clear (17, 18)."""
    df = int(m[:2], 16) >> 3
    return m[2:8] if df in (17, 18) else None


def run(path, k=3.0):
    name = os.path.basename(path)
    iq = load_iq(path)
    mag24 = np.abs(iq).astype(np.float32)
    level = (float(np.std(iq.real)), float(np.median(mag24)), float(mag24.max()))
    mag20 = resampled_mag(iq)
    del iq
    res = {}
    for label, fn, mag in (("2.0 MHz decode.py", decode.decode, mag20), ("2.4 MHz decode24.py", decode24.decode, mag24)):
        for rep in (False, True):
            found = fn(mag, k, repair_bits=rep) if fn is decode24.decode else fn(mag, k, False, rep)
            res[(label, rep)] = found
    return name, res, level


def report(name, res, level):
    std, med, peak = level
    lines = [f"## {name}", "", f"Signal: I/Q noise std {std:.2f} counts, median magnitude {med:.1f}, peak {peak:.1f} "
             f"(full scale 127)." + (" No messages from any decoder." if not any(res.values()) else ""), "", "| decoder | repair | reads | distinct messages | distinct ADS-B (DF17) | addresses | addresses seen once |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for (label, rep), found in res.items():
        msgs = [m for _, m in found]
        distinct = set(msgs)
        adsb = {m for m in distinct if address(m)}
        addr_count = Counter(address(m) for m in msgs if address(m))
        lines.append(f"| {label} | {'on' if rep else 'off'} | {len(found)} | {len(distinct)} | {len(adsb)} | "
                     f"{len(addr_count)} | {sum(1 for a, c in addr_count.items() if c == 1)} |")
    a = {m for _, m in res[("2.0 MHz decode.py", False)]}
    b = {m for _, m in res[("2.4 MHz decode24.py", False)]}
    lines.append("")
    lines.append(f"Repair off: both {len(a & b)}, only 2.0 MHz {len(a - b)}, only 2.4 MHz {len(b - a)}.")
    a2 = {m for _, m in res[("2.0 MHz decode.py", True)]}
    b2 = {m for _, m in res[("2.4 MHz decode24.py", True)]}
    lines.append(f"Repair on: both {len(a2 & b2)}, only 2.0 MHz {len(a2 - b2)}, only 2.4 MHz {len(b2 - a2)}.")
    # addresses seen once: are they known from the other decoder or the other mode?
    all_addr = Counter()
    for found in res.values():
        for _, m in found:
            if address(m):
                all_addr[address(m)] += 1
    for (label, rep), found in res.items():
        once = [m for _, m in found if address(m) and all_addr[address(m)] == 1]
        if once:
            lines.append(f"- {label}, repair {'on' if rep else 'off'}: {len(once)} message(s) whose address appears nowhere "
                         f"else in any decode of this recording: {', '.join(once[:5])}{'...' if len(once) > 5 else ''}")
    lines.append("")
    return "\n".join(lines)


CACHE = "results/compare24"


if __name__ == "__main__":
    force = "--force" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--force"]
    paths = args or sorted(glob.glob(os.path.join(RAW_IQ, "*.bin")))
    os.makedirs(CACHE, exist_ok=True)
    for p in paths:
        cached = os.path.join(CACHE, os.path.basename(p)[:-4] + ".md")
        if os.path.exists(cached) and not force:
            continue
        name, res, level = run(p)
        text = report(name, res, level)
        print(text)
        with open(cached, "w") as f:
            f.write(text)
    kept = sorted(glob.glob(os.path.join(CACHE, "*.md")))
    out = ["# 2.0 MHz (resampled) vs 2.4 MHz (native) on the raw snapshots", "",
           f"{len(kept)} snapshot(s); a snapshot's result stays here after snapshot.sh deletes the file.", ""]
    out += [open(c).read() for c in kept]
    with open("results/compare24.md", "w") as f:
        f.write("\n".join(out))
