"""Is the bad message at 229407 being stepped on by a second transmission? Look at the complex samples."""
import matplotlib.pyplot as plt
import numpy as np

from synth import hex_to_bits

RECORDING = "../dump1090/testfiles/modes1.bin"
FS = 2.0                                    # samples per microsecond
CASES = [("8D4D2023586F20AC8B9C81E5A3EA", 229407, "bad: bit 99 misread"),
         ("8F4D2023587F345E35837E2218B2", 794, "clean")]


def load_complex(path):
    x = np.fromfile(path, dtype=np.uint8).astype(np.float32)
    return (x[0::2] - 127.5) + 1j * (x[1::2] - 127.5)


def pulse_samples(start, msg):
    """Sample index of the pulse in each of the 112 bits (where the carrier is actually on)."""
    bits = hex_to_bits(msg)
    return start + 16 + 2 * np.arange(112) + (1 - bits)       # 1: first half, 0: second half


def main():
    z = load_complex(RECORDING)
    mag = np.abs(z)
    fig, axes = plt.subplots(4, 2, figsize=(15, 14))

    for col, (msg, start, label) in enumerate(CASES):
        title = f"{msg} at {start} ({label})"
        print(f"\n{title}")

        # 1. Is it quiet outside the message?
        lo, hi = start - 100, start + 240 + 100
        ax = axes[0, col]
        ax.plot(np.arange(lo, hi) - start, mag[lo:hi], lw=0.6, color="black")
        ax.axvspan(0, 16, color="gold", alpha=0.3, lw=0, label="preamble")
        ax.axvspan(16, 240, color="0.9", lw=0, label="112 bits")
        ax.set_title(f"{title}\nmagnitude, 100 samples either side", fontsize=9)
        ax.set_xlabel("sample from message start")
        ax.legend(fontsize=8, loc="upper right")
        before, after = mag[start - 100:start], mag[start + 240:start + 340]
        inside = mag[start + 16:start + 240]
        gaps = np.sort(inside)[:112]
        print(f"  magnitude before: mean {before.mean():5.1f} max {before.max():5.1f};"
              f" after: mean {after.mean():5.1f} max {after.max():5.1f};"
              f" gaps inside the message: mean {gaps.mean():5.1f}")

        # 2. Pulse heights along the message: periodic?
        idx = pulse_samples(start, msg)
        heights = mag[idx]
        ax = axes[1, col]
        ax.plot(heights, "o-", ms=3, lw=0.7, color="black")
        ax.set_xlabel("bit")
        ax.set_ylabel("pulse height")
        ax.set_title("height of the pulse in each bit", fontsize=9)
        spec = np.abs(np.fft.rfft(heights - heights.mean(), n=1024))
        freqs = np.fft.rfftfreq(1024, d=1.0)                      # cycles per bit = cycles per µs = MHz
        k = np.argmax(spec[1:]) + 1
        print(f"  pulse heights: mean {heights.mean():5.1f}, min {heights.min():5.1f}, max {heights.max():5.1f};"
              f" strongest ripple at {freqs[k] * 1000:.0f} kHz, period {1 / freqs[k]:.1f} bits")

        # 3. Carrier phase at the pulses: a straight line means one steady carrier
        ph = np.unwrap(np.angle(z[idx]))
        slope, icpt = np.polyfit(idx, ph, 1)
        resid = ph - (slope * idx + icpt)
        ax = axes[2, col]
        ax.plot(idx - start, ph, ".", ms=4, color="black", label="measured")
        ax.plot(idx - start, slope * idx + icpt, color="red", lw=0.8, label=f"fit: {slope * FS / (2 * np.pi) * 1000:+.0f} kHz offset")
        ax.set_xlabel("sample from message start")
        ax.set_ylabel("carrier phase (rad, unwrapped)")
        ax.set_title("phase of the complex sample at each pulse", fontsize=9)
        ax.legend(fontsize=8)
        print(f"  carrier offset from a straight-line phase fit: {slope * FS / (2 * np.pi) * 1000:+.0f} kHz;"
              f" scatter about the line {resid.std():.2f} rad")

        # 4. Spectrum of the message window
        n = 4096
        w = z[start:start + 240] * np.hanning(240)
        spec = np.fft.fftshift(np.abs(np.fft.fft(w, n)))
        f = np.fft.fftshift(np.fft.fftfreq(n, d=1 / FS)) * 1000   # kHz
        ax = axes[3, col]
        ax.plot(f, 20 * np.log10(spec / spec.max()), lw=0.7, color="black")
        ax.set_xlabel("offset from the dongle's tuned frequency (kHz)")
        ax.set_ylabel("dB below peak")
        ax.set_ylim(-50, 2)
        ax.set_title("spectrum of the 240-sample message window", fontsize=9)
        peak = f[np.argmax(spec)]
        print(f"  spectrum peak at {peak:+.0f} kHz")

    fig.tight_layout()
    fig.savefig("results/interference.png", dpi=110)


if __name__ == "__main__":
    main()
