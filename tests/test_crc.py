from pathlib import Path
import pyModeS as pms
from synth import hex_to_bits
from decode import crc24

TRUTH = Path(__file__).resolve().parents[2] / "dump1090" / "truth_modes1.txt"   # adsb/tests -> adsb -> project folder


def test_crc_matches_pymodes():
    msgs = [l.strip()[1:-1] for l in open(TRUTH) if l.startswith("*")]
    long_msgs = [m for m in msgs if len(m) == 28][:50]
    assert long_msgs, "no 112-bit messages in the answer key"
    for m in long_msgs:
        assert crc24(hex_to_bits(m)) == pms.crc(m), m
