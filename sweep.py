"""Detection rate against signal-to-noise on synthetic recordings, with and without bit repair."""
import matplotlib.pyplot as plt

from decode import decode, mag_from_raw
from synth import MSGS, synth_capture

if __name__ == "__main__":
    result = []
    for k in (8, 4):
        for repair in (False, True):
            for snrdb in range(0, 21, 2):
                raw, truth = synth_capture(MSGS * 30, snr_db=snrdb, seed=snrdb)
                found = decode(mag_from_raw(raw), k=k, repair_bits=repair)
                planted = {m for _, m in truth}
                got = {m for _, m in found}
                false = len(got - planted)
                print(f"k={k} repair={repair!s:5} {snrdb:02d} dB: {len(got & planted)} of {len(planted)} found, "
                      f"{false} false")
                result.append((k, repair, snrdb, len(got & planted) / len(planted), false))

    plt.figure()
    for k in (8, 4):
        for repair in (False, True):
            rows = [r for r in result if r[0] == k and r[1] == repair]
            plt.plot([r[2] for r in rows], [r[3] for r in rows],
                     ls="--" if repair else "-", label=f"k={k}{', repair' if repair else ''}")
    plt.xlabel("SNR (dB)")
    plt.ylabel("Fraction of messages found")
    plt.title("ADS-B message recovery vs SNR")
    plt.legend()
    plt.grid()
    plt.savefig("captures/snr.png")
    print("total false messages across the sweep:", sum(r[4] for r in result))
