import numpy as np
from synth import synth_capture, MSGS
from decode import load_mag, PRE

_, truth = synth_capture(MSGS, snr_db=20)          # same seed, so the same starts
mag = load_mag("captures/synth_20db.bin")
corr = np.correlate(mag, PRE, mode="valid")
for k in (8, 4):
    print(f"threshold at k={k}:", k * np.median(corr))
for start, m in truth:
    print(start, m, corr[start])
