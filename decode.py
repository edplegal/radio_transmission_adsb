import sys
import numpy as np

PRE = np.zeros(16, dtype=np.float32)
PRE[[0, 2, 7, 9]] = 1.0
GEN = 0x1FFF409                                   # the checksum's generator polynomial


def mag_from_raw(raw):
    """Dongle bytes -> signal strength per sample (throws the carrier angle away)."""
    x = raw.astype(np.float32)
    return np.abs((x[0::2] - 127.5) + 1j * (x[1::2] - 127.5)).astype(np.float32)


def load_mag(path):
    if path.endswith(".f32"):                     # already strength, from GNU Radio (sitting 11)
        return np.fromfile(path, dtype=np.float32)
    return mag_from_raw(np.fromfile(path, dtype=np.uint8))


def candidates(mag, k=3.0, strict=False):
    """Places where the four preamble blinks line up above k times the typical level."""
    corr = np.correlate(mag, PRE, mode="valid")
    thresh = k * np.median(corr)
    keep = []
    for i in np.flatnonzero(corr > thresh):
        if i > len(mag) - 240:
            break                                 # too close to the end for a whole message
        p = mag[i:i + 16]
        if not strict or (p[0] > p[1] and p[2] > p[3] and p[7] > p[8] and p[9] > p[10]
                and max(p[4], p[5], p[6]) < p[0] / 2 and p[11:16].max() < p[0] / 2):
            keep.append(i)
    return keep


def preamble_score(mag, start):
    """How well the 16 samples at start match the preamble's four blinks."""
    return float(np.dot(mag[start:start + 16], PRE))


def slice_bits(mag, start, nbits=112):
    s = start + 16
    first = mag[s : s + 2 * nbits : 2]
    second = mag[s + 1 : s + 2 * nbits : 2]
    return (first > second).astype(np.uint8)      # blink in the first half = 1


def confidence(mag, start, nbits=112):
    """How clearly each bit was decided: |first - second| / (first + second), 0 = coin toss."""
    s = start + 16
    first = mag[s : s + 2 * nbits : 2]
    second = mag[s + 1 : s + 2 * nbits : 2]
    return np.abs(first - second) / (first + second + 1e-9)


def repair(mag, start, bits):
    """Flip the least confident bit, then the second least, then both; first checksum pass wins."""
    a, b = np.argsort(confidence(mag, start))[:2]
    for flips in ((a,), (b,), (a, b)):
        trial = bits.copy()
        trial[list(flips)] ^= 1
        if crc24(trial) == 0:
            return trial
    return None


def crc24(bits):
    v = int("".join(map(str, bits)), 2)
    for i in range(len(bits) - 24):
        if v & (1 << (len(bits) - 1 - i)):
            v ^= GEN << (len(bits) - 25 - i)
    return v & 0xFFFFFF                           # zero for an intact ADS-B message


def bits_to_hex(bits):
    return f"{int(''.join(map(str, bits)), 2):0{len(bits) // 4}X}"


def decode(mag, k=3.0, strict=False, repair_bits=False):
    """All intact 112-bit messages as (start, hex), each physical message once.

    With repair_bits, a candidate that fails the checksum gets up to three more tries
    with its one or two least confident bits flipped.
    """
    passes = []
    for start in candidates(mag, k, strict):
        bits = slice_bits(mag, start)
        if crc24(bits) == 0:
            passes.append((start, bits_to_hex(bits)))
        elif repair_bits:
            fixed = repair(mag, start, bits)
            if fixed is not None:
                passes.append((start, bits_to_hex(fixed)))

    # Two reads less than a message apart cannot both be real: the same message caught again
    # a few samples later, or a ghost (a shift by one bit can also pass the checksum when the
    # last bit is 0). Keep whichever has the stronger preamble.
    found = []
    for start, m in passes:                       # already in time order
        score = preamble_score(mag, start)
        if found and start - found[-1][0] < 240:
            if score > found[-1][2]:
                found[-1] = (start, m, score)
            continue
        found.append((start, m, score))
    return [(start, m) for start, m, _ in found]


if __name__ == "__main__":
    found = decode(load_mag(sys.argv[1]))
    for start, m in found:
        print(start, m)
    print(f"{len(found)} intact messages")
