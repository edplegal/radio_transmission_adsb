from synth import synth_capture, MSGS
from decode import decode, mag_from_raw
import matplotlib.pyplot as plt

if __name__ == "__main__":
    result = []
    for k in (8, 4):
        for snrdb in range(0, 21, 2):
            raw, truth = synth_capture(MSGS * 30,       
                                    snr_db=snrdb, 
                                    seed = snrdb)
            found = decode(mag_from_raw(raw), k=k)

            count = 0
            for m in truth:
                if m not in found:
                    count += 1
            print(f"{snrdb:02d} dB: {len(found)} found, {count} missing")
            result.append((k, 
                          snrdb, 
                          (len(truth) - count) / len(truth)))

    plt.figure()
    for k in (8, 4):
        x = [snrdb for (k2, snrdb, _) in result if k2 == k]
        y = [frac for (k2, _, frac) in result if k2 == k]
        plt.plot(x, y, label=f"k={k}")
    plt.xlabel("SNR (dB)")
    plt.ylabel("Fraction of messages found")
    plt.title("ADSB message recovery vs SNR")
    plt.legend()
    plt.grid()
    plt.savefig("captures/snr.png")
