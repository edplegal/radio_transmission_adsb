"""Receiver for 2.4 million samples per second: timing from the preamble, energy per half-bit.

At 2.0 MHz a half-bit (0.5 us) is exactly one sample, so decode.py can compare sample 2b with
sample 2b+1. At 2.4 MHz a half-bit is 1.2 samples: the sample grid drifts through the bit grid by
0.2 sample per half-bit and comes back into step every 5 half-bits, so no fixed pair of samples
represents a bit. This decoder instead (1) finds the message start to a fraction of a sample from
the preamble, then (2) integrates the magnitude over each half-bit's exact time window, using
linear interpolation between samples, and compares the two integrals. Checksum, overlap (ghost)
rule and soft-decision repair are the same ideas as in decode.py.
"""
import sys

import numpy as np

from decode import bits_to_hex, crc24, mag_from_raw
from synth import sampled_envelope

FS = 2_400_000
SPU = FS / 1e6                                   # samples per microsecond: 2.4
PRE_US = (0.0, 1.0, 3.5, 4.5)                    # preamble blinks, each 0.5 us
MSG_US = 8 + 112                                 # preamble + 112 bits
SUBSTEPS = 16                                    # timing resolution: 1/16 sample = 26 ns
CENTRE_PTS = (-0.12, 0.12)                       # where in a half-bit window to read the magnitude:
                                                 # samples either side of the window centre (+-0.05 us)
SPAN = int(MSG_US * SPU) + 4                     # samples a message occupies, with slack


SMOOTH_US = 0.6                                  # the dongle rounds pulses by about this much (timing.py)


def preamble_samples(offset, n=13):
    """Expected magnitude in n consecutive samples when the preamble begins `offset` samples after
    the first one: the ideal blinks, rounded by the receiver's bandwidth, sampled at instants."""
    return sampled_envelope(np.zeros(0, dtype=np.uint8), FS, offset, SMOOTH_US)[:n].astype(np.float64)


TEMPLATES = np.array([preamble_samples(k / SUBSTEPS) for k in range(SUBSTEPS)])     # 16 x 13
TEMPLATES /= np.linalg.norm(TEMPLATES, axis=1, keepdims=True)
PRE = np.zeros(12)                                # detection template: one sample per blink, at the
PRE[[0, 2, 8, 11]] = 1.0                          # blink starts 0, 1.0, 3.5, 4.5 us -> 0, 2.4, 8.4, 10.8.
# A sparse template beats the rounded one for *detection* in noise (synthetic 14 dB: a candidate
# within one sample of 41 of 90 planted messages against 8); the rounded TEMPLATES above are
# still what the sub-sample *timing* is fitted with.


def load_mag(path):
    if path.endswith(".f32"):
        return np.fromfile(path, dtype=np.float32)
    return mag_from_raw(np.fromfile(path, dtype=np.uint8))


def candidates(mag, k=3.0):
    """Sample indices where the preamble correlation is a local peak above k times its median."""
    corr = np.correlate(mag, PRE, mode="valid")
    thresh = k * np.median(corr)
    above = corr > thresh
    peak = above.copy()
    peak[1:] &= corr[1:] >= corr[:-1]
    peak[:-1] &= corr[:-1] > corr[1:]              # keep one of a run of equal values
    idx = np.flatnonzero(peak)
    return idx[idx < len(mag) - SPAN], corr


def timing(mag, start):
    """Where exactly the preamble begins, near the correlation peak at `start`.

    The 16 templates (preamble shifted by 0, 1/16, ... 15/16 of a sample) are tried at start-1,
    start and start+1, 48 placements 26 ns apart, and the best match wins. Returns the integer
    sample, the fractional offset in [0, 1), and the match score, which also ranks overlapping
    reads (a ghost read two samples early matches the preamble worse than the real one).
    """
    best = (start, 0.0, -1.0)
    for s in (start - 1, start, start + 1):
        if s < 0:
            continue
        scores = TEMPLATES @ mag[s:s + 13]
        k = int(np.argmax(scores))
        if scores[k] > best[2]:
            best = (s, k / SUBSTEPS, float(scores[k]))
    return best


def half_bit_energy(mag, start, offset):
    """Magnitude at the centre of each of the 224 half-bit windows, by linear interpolation.

    Half-bit h covers microseconds [8 + h/2, 8.5 + h/2) after the message start, i.e. samples
    [t0 + 2.4(8 + h/2), t0 + 2.4(8.5 + h/2)) with t0 = start + offset. A pulse rounded by the
    receiver's bandwidth peaks at its window's centre and spills into the neighbours' windows, so
    the centre is read (mean of two points 0.05 us either side) rather than the whole window:
    on synthetic data at 14 dB the window mean made 7 bit errors per message, the centre 4.
    """
    local = mag[start:start + SPAN].astype(np.float64)
    centre = offset + 8 * SPU + 0.5 * SPU * np.arange(224) + 0.25 * SPU
    pos = centre[:, None] + np.array(CENTRE_PTS)[None, :]
    vals = np.interp(pos.ravel(), np.arange(len(local)), local).reshape(224, -1)
    return vals.mean(axis=1)


def slice_bits(energy):
    first, second = energy[0::2], energy[1::2]
    return (first > second).astype(np.uint8)


def confidence(energy):
    first, second = energy[0::2], energy[1::2]
    return np.abs(first - second) / (first + second + 1e-9)


def repair(energy, bits):
    """Flip the least confident bit, then the second, then both; first checksum pass wins."""
    a, b = np.argsort(confidence(energy))[:2]
    for flips in ((a,), (b,), (a, b)):
        trial = bits.copy()
        trial[list(flips)] ^= 1
        if crc24(trial) == 0:
            return trial
    return None


def decode(mag, k=3.0, repair_bits=False):
    """All intact 112-bit messages as (start sample, hex), each physical message once."""
    passes = []
    for start in candidates(mag, k)[0]:
        start, offset, score = timing(mag, start)
        energy = half_bit_energy(mag, start, offset)
        bits = slice_bits(energy)
        if crc24(bits) == 0:
            passes.append((int(start), bits_to_hex(bits), score))
        elif repair_bits:
            fixed = repair(energy, bits)
            if fixed is not None:
                passes.append((int(start), bits_to_hex(fixed), score))

    # Reads less than a message apart cannot both be real: keep the stronger preamble
    found = []
    for start, m, score in passes:
        if found and start - found[-1][0] < SPAN:
            if score > found[-1][2]:
                found[-1] = (start, m, score)
            continue
        found.append((start, m, score))
    return [(start, m) for start, m, _ in found]


if __name__ == "__main__":
    mag = load_mag(sys.argv[1])
    for start, m in decode(mag, repair_bits="--repair" in sys.argv):
        print(start, m)
