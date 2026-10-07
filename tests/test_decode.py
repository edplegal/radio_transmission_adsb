import numpy as np
import pytest

from decode import decode, load_mag, mag_from_raw, slice_bits
from synth import MSGS, hex_to_bits, synth_capture

RECORDING = "../dump1090/testfiles/modes1.bin"


@pytest.fixture(scope="module")
def mag():
    return load_mag(RECORDING)


@pytest.mark.parametrize("repair_bits", [False, True])
def test_decode_strong_synthetic_signal_finds_only_planted_messages(repair_bits):
    raw, truth = synth_capture(MSGS * 10, snr_db=20, seed=20)
    found = {m for _, m in decode(mag_from_raw(raw), k=4, repair_bits=repair_bits)}
    assert found == {m for _, m in truth}          # no ghosts shifted by one bit, nothing missing


def test_decode_repair_recovers_single_misread_bit(mag):
    msg, start = "8D4D2023586F20AC8B9C81E5A3EA", 229407
    wrong = np.flatnonzero(slice_bits(mag, start) != hex_to_bits(msg))
    assert wrong.tolist() == [99]                   # the premise: exactly one bit is misread
    assert (start, msg) not in decode(mag)
    assert (start, msg) in decode(mag, repair_bits=True)


def test_decode_repair_adds_no_extra_adsb_messages(mag):
    plain = {m for _, m in decode(mag) if m.startswith("8D")}
    repaired = {m for _, m in decode(mag, repair_bits=True) if m.startswith("8D")}
    assert plain <= repaired
    assert len(repaired - plain) == 2
