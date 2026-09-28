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


def synth_capture(msgs, snr_db, seconds=1.0, seed=0, amp=40.0):
    """Plant msgs in a noisy recording; return dongle-format bytes and (start, msg) answer key."""
    rng = np.random.default_rng(seed)
    n = int(FS * seconds)
    iq = np.zeros(n, dtype=np.complex64)                 # one second of silence
    truth = []
    for m in msgs:
        env = ppm_envelope(hex_to_bits(m))
        start = int(rng.integers(0, n - len(env)))       # random moment
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
