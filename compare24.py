"""Fair comparison on the raw snapshots: the 2.0 MHz decoder on a resampled copy versus the 2.4 MHz
decoder on the original, with repair off and on.

For each snapshot in data/raw_iq: resample the complex samples 2.4 -> 2.0 MHz (polyphase, 5/6),
take the magnitude, run decode.decode; run decode24.decode on the original magnitude. Report
distinct checksum-valid 112-bit messages per decoder and mode, messages only one decoder found,
and whether each decoded aircraft address appears in more than one message of that recording
(an address seen once is the signature of a false message that happened to pass the checksum).
Outputs go to results/compare24.md (git-ignored) and stdout.
"""
import glob
import os
import sys
from collections import Counter

import numpy as np
from scipy.signal import resample_poly

import decode
import decode24

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
    mag20 = resampled_mag(iq)
    del iq
    res = {}
    for label, fn, mag in (("2.0 MHz decode.py", decode.decode, mag20), ("2.4 MHz decode24.py", decode24.decode, mag24)):
        for rep in (False, True):
            found = fn(mag, k, repair_bits=rep) if fn is decode24.decode else fn(mag, k, False, rep)
            res[(label, rep)] = found
    return name, res


def report(name, res):
    lines = [f"## {name}", "", "| decoder | repair | reads | distinct messages | distinct ADS-B (DF17) | addresses | addresses seen once |",
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


if __name__ == "__main__":
    paths = sorted(glob.glob("../data/raw_iq/*.bin")) if len(sys.argv) < 2 else sys.argv[1:]
    out = ["# 2.0 MHz (resampled) vs 2.4 MHz (native) on the raw snapshots", ""]
    for p in paths:
        name, res = run(p)
        text = report(name, res)
        print(text)
        out.append(text)
    os.makedirs("results", exist_ok=True)
    with open("results/compare24.md", "w") as f:
        f.write("\n".join(out))
