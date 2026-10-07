"""Sitting 6 revisited: look at the samples of the misread bits in the five slicing errors."""
import matplotlib.pyplot as plt
import numpy as np

from decode import decode, load_mag, slice_bits
from synth import hex_to_bits

RECORDING = "../dump1090/testfiles/modes1.bin"

# The five messages compare.py classed as slicing errors: (hex, start sample, misread bits)
SLICING = [
    ("8D4D2023586D74410F89455BE921", 257282, [1]),
    ("8D4D2023586F20AC8B9C81E5A3EA", 229407, [99]),
    ("8D4D20235875544DE586BC3E9C91", 123821, [66, 85, 110]),
    ("8F4D20235875A44EE58689E5416A", 106295, [7, 43, 62, 76, 90, 102, 106]),
    ("8F4D20235875B0B87F9A210CA4D7", 105590, [29, 43, 60, 81, 111]),
]


def margins(mag, start, nbits=112):
    """Per bit: (first - second) / (first + second). Positive reads as 1; near zero = coin toss."""
    s = start + 16
    first = mag[s : s + 2 * nbits : 2]
    second = mag[s + 1 : s + 2 * nbits : 2]
    return (first - second) / (first + second)


def bit_window(ax, mag, start, msg, lo, hi, bad=(), title=""):
    """Magnitude per sample for bits lo..hi of the message starting at `start`."""
    bits = hex_to_bits(msg)
    s0, s1 = start + 16 + 2 * lo, start + 16 + 2 * (hi + 1)
    x = np.arange(s0, s1)
    ax.step(x, mag[s0:s1], where="mid", color="black", lw=1)
    ax.plot(x, mag[s0:s1], "o", color="black", ms=4)
    top = mag[s0:s1].max() * 1.15
    for b in range(lo, hi + 1):
        a = start + 16 + 2 * b
        ax.axvspan(a - 0.5, a + 0.5, color="0.92", lw=0)              # first half: pulse here = 1
        if b in bad:
            ax.axvspan(a - 0.5, a + 1.5, color="red", alpha=0.15, lw=0)
        ax.text(a + 0.5, top, str(bits[b]), ha="center", va="bottom",
                color="red" if b in bad else "black", fontweight="bold" if b in bad else None)
        ax.text(a + 0.5, -0.06 * top, f"b{b}", ha="center", va="top", fontsize=7, color="0.4")
    ax.set_xlim(s0 - 0.5, s1 - 0.5)
    ax.set_ylim(-0.12 * top, 1.25 * top)
    ax.set_xlabel("sample")
    ax.set_ylabel("magnitude")
    ax.ticklabel_format(axis="x", useOffset=False, style="plain")
    ax.set_title(title, fontsize=10)


def whole_message(ax_mag, ax_margin, mag, start, msg, bad=(), title=""):
    """All 112 bits: magnitude trace on top, per-bit margin below, misread bits in red."""
    bits = hex_to_bits(msg)
    s0, s1 = start + 16, start + 16 + 224
    ax_mag.step(np.arange(s0, s1) - s0, mag[s0:s1], where="mid", color="black", lw=0.8)
    for b in bad:
        ax_mag.axvspan(2 * b - 0.5, 2 * b + 1.5, color="red", alpha=0.3, lw=0)
    ax_mag.set_ylabel("magnitude")
    ax_mag.set_title(title, fontsize=10)
    ax_mag.set_xlim(-1, 224)

    m = margins(mag, start)
    signed = m * (2 * bits.astype(int) - 1)       # positive = read correctly, negative = misread
    colors = np.where(signed < 0, "red", np.where(signed < 0.2, "orange", "black"))
    ax_margin.bar(np.arange(112), signed, color=colors, width=0.8)
    ax_margin.axhline(0, color="0.5", lw=0.5)
    ax_margin.set_ylim(-1, 1)
    ax_margin.set_xlim(-0.5, 111.5)
    ax_margin.set_xlabel("bit")
    ax_margin.set_ylabel("margin, signed\n(+ = correct)")


if __name__ == "__main__":
    mag = load_mag(RECORDING)
    good_start, good_msg = next((s, m) for s, m in decode(mag) if len(m) == 28)
    print("clean message", good_msg, "at", good_start)

    # Close-up of bit 99, next to the same bits of the clean message
    bad_msg, bad_start, bad_bit = SLICING[1]
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.5))
    bit_window(axes[0], mag, bad_start, bad_msg, 94, 104, bad=bad_bit,
               title=f"{bad_msg} at {bad_start}: bit 99 misread (shaded = first half of each bit)")
    bit_window(axes[1], mag, good_start, good_msg, 94, 104,
               title=f"{good_msg} at {good_start}: read correctly")
    fig.tight_layout()
    fig.savefig("results/bit99.png", dpi=150)

    # Every slicing error in full, plus the clean message for reference
    rows = SLICING + [(good_msg, good_start, [])]
    fig, axes = plt.subplots(2 * len(rows), 1, figsize=(16, 3.2 * len(rows)),
                             gridspec_kw={"height_ratios": [2, 1] * len(rows)})
    for i, (msg, start, bad) in enumerate(rows):
        read = slice_bits(mag, start)
        wrong = np.flatnonzero(read != hex_to_bits(msg)).tolist()
        assert wrong == bad, (msg, wrong)
        m = margins(mag, start)
        label = f"{msg} at {start}: misread bits {bad}" if bad else f"{msg} at {start}: clean"
        whole_message(axes[2 * i], axes[2 * i + 1], mag, start, msg, bad, title=label)
        floor = np.sort(mag[start + 16 : start + 240])[:112].mean()      # the 112 lower samples
        peak = np.sort(mag[start + 16 : start + 240])[112:].mean()       # the 112 upper samples
        print(f"{msg} at {start}: gaps average {floor:5.1f}, pulses average {peak:5.1f},"
              f" |margin| of misread bits {[round(abs(m[b]), 3) for b in bad]},"
              f" smallest correct |margin| {np.min(np.abs(np.delete(m, bad))):.3f}")
    fig.tight_layout()
    fig.savefig("results/slicing_errors.png", dpi=110)
