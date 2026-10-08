import numpy as np

FS = 2_000_000                              # samples per second, same as the dongle
PRE_IDX = [0, 2, 7, 9]                      # preamble blinks at 0, 1.0, 3.5, 4.5 µs


def hex_to_bits(msg_hex):
    """'8D48...' -> array of 0s and 1s, four bits per hex digit."""
    return np.array([int(b) for b in bin(int(msg_hex, 16))[2:].zfill(4 * len(msg_hex))],
                    dtype=np.uint8)


def ppm_envelope(bits):
    """Bits -> blink pattern, one entry per half microsecond."""
    env = np.zeros(16 + 2 * len(bits), dtype=np.float32)
    env[PRE_IDX] = 1.0
    for k, b in enumerate(bits):
        env[16 + 2 * k + (0 if b else 1)] = 1.0   # 1: first half, 0: second half
    return env


HR = 48_000_000                             # fine grid for building pulses: 48 points per microsecond,
                                            # an integer multiple of both 2.0 and 2.4 MHz


def envelope_hr(bits):
    """Ideal on/off pattern of preamble + bits on the fine grid, 48 points per microsecond."""
    env = np.zeros(48 * (8 + len(bits)), dtype=np.float32)
    for t_us in (0.0, 1.0, 3.5, 4.5):                       # preamble blinks, each half a microsecond
        a = int(round(t_us * 48))
        env[a:a + 24] = 1.0
    for k, b in enumerate(bits):
        a = 48 * (8 + k) + (0 if b else 24)
        env[a:a + 24] = 1.0
    return env


def sampled_envelope(bits, fs, offset=0.0, smooth_us=0.0):
    """The envelope as the dongle would sample it at fs: smoothed by a box of smooth_us (the
    receiver's finite bandwidth rounds the pulses), then sampled every 1/fs starting at `offset`
    samples before the first pulse (0 <= offset < 1: where the pulses sit between the samples)."""
    env = np.concatenate([envelope_hr(bits), np.zeros(48, dtype=np.float32)])   # 1 us of silence after
    if smooth_us > 0:
        w = max(int(round(smooth_us * 48)), 1)
        env = np.convolve(env, np.ones(w, dtype=np.float32) / w, mode="same")    # the trailing ramp of
    step = HR / fs                                          # fine points per output sample (24 or 20)
    if abs(step - round(step)) > 1e-9:                      # the last pulse now fits in the padding
        raise ValueError(f"fs must divide {HR}: 2e6 and 2.4e6 do")
    step = int(round(step))
    first = int(round(offset * step)) % step                # sub-sample shift on the fine grid
    n_out = len(env) // step                                # 242 samples at 2 MHz, 290 at 2.4 MHz
    pad = np.zeros(step, dtype=np.float32)
    env = np.concatenate([pad, env, pad])
    return env[step - first::step][:n_out]


def synth_capture(msgs, snr_db, seconds=1.0, seed=0, amp=40.0, fs=FS, jitter=False, smooth_us=0.0,
                  offsets_out=None):
    """Plant msgs in a noisy recording; return dongle-format bytes and (start, msg) answer key.

    Defaults reproduce the original 2 MHz, on-grid, sharp-pulse transmitter. With jitter=True each
    message gets a random sub-sample timing offset, and smooth_us > 0 rounds the pulses the way the
    dongle's bandwidth does (timing.py found about 0.6 us on the real recording).
    """
    rng = np.random.default_rng(seed)
    n = int(fs * seconds)
    iq = np.zeros(n, dtype=np.complex64)                 # one second of silence
    truth = []
    for m in msgs:
        offset = rng.uniform(0, 1) if jitter else 0.0
        env = sampled_envelope(hex_to_bits(m), fs, offset, smooth_us)
        start = int(rng.integers(0, n - len(env)))       # random moment
        if offsets_out is not None:
            offsets_out.append((start, offset))         # where the preamble really begins: start + offset
        phase = rng.uniform(0, 2 * np.pi)                # random carrier angle
        iq[start:start + len(env)] += amp * env * np.exp(1j * phase)
        truth.append((start, m))
    sigma = amp / 10 ** (snr_db / 20)                    # hiss, relative to the blinks
    iq += rng.normal(0, sigma, n) + 1j * rng.normal(0, sigma, n)
    raw = np.empty(2 * n, dtype=np.uint8)                # dongle format: I, Q, I, Q ... as bytes
    raw[0::2] = np.clip(np.rint(iq.real + 127.5), 0, 255)
    raw[1::2] = np.clip(np.rint(iq.imag + 127.5), 0, 255)
    return raw, sorted(truth)


MSGS = ["8D4840D6202CC371C32CE0576098",     # identification: callsign
        "8D40621D58C382D690C8AC2863A7",     # position, even frame
        "8D40621D58C386435CC412692AD6"]     # position, odd frame

if __name__ == "__main__":
    raw, truth = synth_capture(MSGS, snr_db=20)
    raw.tofile("captures/synth_20db.bin")
    for start, m in truth:
        print(start, m)
