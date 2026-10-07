"""Where do the pulses sit relative to the sample grid? Fit a sub-sample timing offset per message."""
import numpy as np

from bitplot import SLICING, margins
from decode import decode, load_mag
from synth import hex_to_bits

RECORDING = "../dump1090/testfiles/modes1.bin"
UP = 16                                     # model resolution: 16 points per sample
PULSE_WIDTH = 0.5                           # µs; one sample at 2 MHz


def model_envelope(msg, width_samples=1.0):
    """Ideal on/off pattern of the 112 bits at UP points per sample, smoothed by the receiver's
    roughly one-sample-wide response, so an isolated pulse becomes a rounded bump."""
    bits = hex_to_bits(msg)
    env = np.zeros(224 * UP)
    for k, b in enumerate(bits):
        a = (2 * k + (0 if b else 1)) * UP
        env[a:a + UP] = 1.0
    kernel = np.ones(int(width_samples * UP)) / (width_samples * UP)
    return np.convolve(env, kernel, mode="same")


def fit_offset(mag, start, msg):
    """Sub-sample shift (in samples, 0 to 1) that best matches the measured magnitudes.

    0 or 1 = samples land on pulse centres; 0.5 = samples land on pulse edges."""
    meas = mag[start + 16:start + 240]
    meas = meas - np.sort(meas)[:20].mean()                     # take out the noise floor
    env = model_envelope(msg)
    best = None
    for shift in range(UP):
        model = env[(np.arange(224) * UP + shift + UP // 2) % len(env)]
        c = np.dot(model, meas) / np.linalg.norm(model) / np.linalg.norm(meas)
        if best is None or c > best[1]:
            best = (shift / UP, c)
    return best


def pattern_heights(mag, start, msg):
    """Pulse height by context: pulse that touches the next bit's pulse (a 0 followed by a 1) vs isolated."""
    bits = hex_to_bits(msg)
    idx = start + 16 + 2 * np.arange(112) + (1 - bits)
    h = mag[idx]
    touching = np.zeros(112, bool)
    touching[:-1] |= (bits[:-1] == 0) & (bits[1:] == 1)          # my pulse (2nd half) meets next pulse (1st half)
    touching[1:] |= (bits[:-1] == 0) & (bits[1:] == 1)
    return h[touching].mean(), h[~touching].mean()


if __name__ == "__main__":
    mag = load_mag(RECORDING)
    good = [(m, s, []) for s, m in decode(mag) if len(m) == 28]

    print("message                       start   offset  corr   gaps/pulses   touching  isolated  smallest |margin|")
    rows = []
    for label, group in (("MISREAD", SLICING), ("clean", good[:12])):
        for msg, start, bad in group:
            off, c = fit_offset(mag, start, msg)
            inside = np.sort(mag[start + 16:start + 240])
            ratio = inside[:112].mean() / inside[112:].mean()
            t, iso = pattern_heights(mag, start, msg)
            m = np.abs(margins(mag, start))
            print(f"{msg} {start:7d}   {off:4.2f}   {c:.3f}    {ratio:.2f}         {t:5.1f}     {iso:5.1f}     {m.min():.3f}   {label}")

    # Population: every intact message in the file vs the five misread ones
    ratios = {}
    for msg, start, _ in good:
        inside = np.sort(mag[start + 16:start + 240])
        ratios[msg] = inside[:112].mean() / inside[112:].mean()
    r = np.array(list(ratios.values()))
    print(f"\ngaps/pulses over {len(r)} clean messages: median {np.median(r):.2f}, 90th percentile {np.percentile(r, 90):.2f}, max {r.max():.2f}")
    offs = np.array([fit_offset(mag, s, m)[0] for m, s, _ in good])
    print("timing offsets of clean messages:", np.round(np.sort(offs), 2).tolist())
