"""Synthetic noise sweep at 2.0 and 2.4 million samples per second, on equal terms.

Both recordings get the same messages, random sub-sample timing and 0.6 us pulse rounding; the
2.0 MHz one is decoded by decode.py, the 2.4 MHz one by decode24.py, both at k=3. Two metrics per
point: the fraction of the 90 planted copies decoded (the honest one) and the fraction of the 3
distinct messages found at least once (what sweep.py reports). Half-recovery points by linear
interpolation. Plot: results/sweep_rates.png.
"""
import matplotlib.pyplot as plt
import numpy as np

import decode
import decode24
from synth import MSGS, synth_capture

SNRS = list(range(0, 23, 2))
SMOOTH = 0.6


def half_point(snrs, frac):
    """SNR where the curve first crosses 0.5, by linear interpolation; None if it never does."""
    for i in range(1, len(frac)):
        if frac[i - 1] < 0.5 <= frac[i]:
            return snrs[i - 1] + (0.5 - frac[i - 1]) / (frac[i] - frac[i - 1]) * (snrs[i] - snrs[i - 1])
    return None


def sweep(fs, decoder, repair):
    copies, distinct, false = [], [], []
    for snr in SNRS:
        raw, truth = synth_capture(MSGS * 30, snr, seed=snr, fs=fs, jitter=True, smooth_us=SMOOTH)
        mag = decode.mag_from_raw(raw)
        found = decoder(mag, 3.0, repair_bits=repair) if decoder is decode24.decode else decoder(mag, 3.0, False, repair)
        planted = {m for _, m in truth}
        got = {m for _, m in found}
        hits = sum(1 for s, m in found if any(abs(s - ts) <= 2 and m == tm for ts, tm in truth))
        copies.append(hits / len(truth))
        distinct.append(len(got & planted) / len(planted))
        false.append(len(got - planted))
    return copies, distinct, false


if __name__ == "__main__":
    runs = {}
    for label, fs, dec in (("2.0 MHz decode.py", 2.0e6, decode.decode), ("2.4 MHz decode24.py", 2.4e6, decode24.decode)):
        for rep in (False, True):
            runs[(label, rep)] = sweep(fs, dec, rep)
            c, d, f = runs[(label, rep)]
            print(f"{label}, repair {'on ' if rep else 'off'}: half-recovery of copies at "
                  f"{half_point(SNRS, c) or float('nan'):.1f} dB, of distinct messages at {half_point(SNRS, d) or float('nan'):.1f} dB; "
                  f"false messages {sum(f)}")
            print("   copies:  ", " ".join(f"{x:.2f}" for x in c))
            print("   distinct:", " ".join(f"{x:.2f}" for x in d))

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for ax, idx, title in ((axes[0], 0, "fraction of the 90 planted copies decoded"), (axes[1], 1, "fraction of the 3 distinct messages found")):
        for (label, rep), r in runs.items():
            ax.plot(SNRS, r[idx], ls="--" if rep else "-", marker="o", ms=3,
                    color="C0" if "2.0" in label else "C3", label=f"{label}{', repair' if rep else ''}")
        ax.axhline(0.5, color="0.7", lw=0.8)
        ax.set_xlabel("signal-to-noise ratio (dB)")
        ax.set_ylabel("fraction")
        ax.set_title(title, fontsize=10)
        ax.grid(alpha=0.3)
    axes[0].legend(fontsize=8)
    fig.suptitle(f"synthetic messages with random sub-sample timing and {SMOOTH} us pulse rounding", fontsize=10)
    fig.tight_layout()
    fig.savefig("results/sweep_rates.png", dpi=150)
