import numpy as np
import pytest

import decode24
from synth import MSGS, hex_to_bits, synth_capture


@pytest.fixture(scope="module")
def strong():
    offsets = []
    raw, truth = synth_capture(MSGS * 10, snr_db=20, seed=20, fs=2.4e6, jitter=True, smooth_us=0.6,
                               offsets_out=offsets)
    return decode24.mag_from_raw(raw), truth, dict(offsets)


def test_decode_finds_every_planted_message_and_nothing_else(strong):
    mag, truth, _ = strong
    found = decode24.decode(mag, k=3)
    assert {m for _, m in found} == {m for _, m in truth}
    assert all(any(abs(s - ts) <= 2 and m == tm for ts, tm in truth) for s, m in found)     # no ghosts


def test_timing_recovers_sub_sample_offset(strong):
    mag, truth, offsets = strong
    errs = []
    for s, _ in truth:
        s2, off, _ = decode24.timing(mag, s)
        errs.append(s2 + off - (s + offsets[s]))
    assert np.median(np.abs(errs)) < 0.15 and np.std(errs) < 0.35                           # 1/16-sample steps, 20 dB


def test_half_bit_energy_reads_the_bits_with_true_timing(strong):
    mag, truth, offsets = strong
    perfect = sum(np.array_equal(decode24.slice_bits(decode24.half_bit_energy(mag, s, offsets[s])), hex_to_bits(m))
                  for s, m in truth)
    assert perfect >= 20                                                                   # of 30 at 20 dB


def test_repair_adds_no_false_messages():
    raw, truth = synth_capture(MSGS * 10, snr_db=16, seed=16, fs=2.4e6, jitter=True, smooth_us=0.6)
    mag = decode24.mag_from_raw(raw)
    plain = {m for _, m in decode24.decode(mag, k=3)}
    repaired = {m for _, m in decode24.decode(mag, k=3, repair_bits=True)}
    assert plain <= repaired <= {m for _, m in truth}
