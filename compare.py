import numpy as np

from decode import decode, load_mag, candidates, slice_bits
from synth import hex_to_bits

TRUTH = "../dump1090/truth_modes1.txt"
RECORDING = "../dump1090/testfiles/modes1.bin"
DUMP1090_READ_LIMIT = 270_000   # dump1090 skips the final partial chunk of the file


def is_adsb(m):
    return len(m) == 28 and int(m[:2], 16) >> 3 == 17


def load_key(path):
    with open(path) as f:
        return {line[1:-1].upper() for line in f.read().splitlines() if is_adsb(line[1:-1])}


def run(mag, key, k, strict, repair_bits=False):
    found = decode(mag, k, strict, repair_bits)
    mine = {m for start, m in found if is_adsb(m) and start < DUMP1090_READ_LIMIT}
    print(f"k={k}, strict={strict}, repair={repair_bits}: both {len(key & mine)}, missed {len(key - mine)}, "
          f"extra {len(mine - key)}, recovery {len(key & mine) / len(key):.0%}")
    return mine


def diagnose(mag, missed, k_search=2.0):
    """For each missed message, find the closest read in the recording and classify it."""
    spots = candidates(mag, k=k_search, strict=False)
    for m in sorted(missed):
        target = hex_to_bits(m)
        best = min(spots, key=lambda s: np.sum(slice_bits(mag, s) != target))
        wrong = [int(b) for b in np.flatnonzero(slice_bits(mag, best) != target)]
        if not wrong:
            group = "detection"      # read perfectly once looked at: below the bar or skipped
        elif len(wrong) <= 7:
            group = "slicing"        # right place, a few bits misread
        else:
            group = "not found"      # closest read is a different message
        print(f"{group:10} {m} at {best} wrong bits: {wrong if group == 'slicing' else len(wrong)}")


if __name__ == "__main__":
    key = load_key(TRUTH)
    mag = load_mag(RECORDING)

    for k, strict in [(4.0, False), (3.0, False), (2.0, False), (1.5, False)]:
        run(mag, key, k, strict)

    mine = run(mag, key, k=3.0, strict=False)
    diagnose(mag, key - mine)

    print("\nwith soft-decision repair:")
    repaired = run(mag, key, k=3.0, strict=False, repair_bits=True)
    print("recovered by repair:", sorted(repaired - mine))
    print("still missed:", sorted(key - repaired))
    all_found = {m for s, m in decode(mag, 3.0, False, True)}
    all_plain = {m for s, m in decode(mag, 3.0, False)}
    print(f"whole file, any length/format: {len(all_plain)} without repair, {len(all_found)} with")