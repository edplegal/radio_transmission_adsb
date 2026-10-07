"""Survey every recorded hex message with our own decoding, and check callsigns against dump1090's."""
import glob
from collections import Counter, defaultdict

import matplotlib.pyplot as plt

from fields import fields

DATA = "../data"

TYPE_NAMES = {**{t: "identification" for t in range(1, 5)},
              **{t: "surface position" for t in range(5, 9)},
              **{t: "airborne position" for t in range(9, 19)},
              19: "velocity",
              **{t: "airborne position (GPS altitude)" for t in range(20, 23)},
              28: "aircraft status", 29: "target state", 31: "operational status"}


def hex_messages(path):
    """Every 112-bit ADS-B message in a raw file, whether or not lines carry a timestamp."""
    with open(path) as f:
        for line in f:
            star, semi = line.find("*"), line.find(";")
            if star < 0 or semi < 0:
                continue
            m = line[star + 1:semi].upper()
            if len(m) == 28 and int(m[:2], 16) >> 3 == 17:
                yield m


def dump1090_callsigns(paths):
    """address -> callsign, from dump1090's decoded files."""
    calls = {}
    for path in paths:
        with open(path) as f:
            for line in f:
                if not line.startswith("MSG"):
                    line = line.split(",", 1)[-1]
                fields_ = line.strip().split(",")
                if len(fields_) > 10 and fields_[0] == "MSG" and fields_[1] == "1" and fields_[10].strip():
                    calls[fields_[4]] = fields_[10].strip()
    return calls


if __name__ == "__main__":
    by_type = Counter()
    ours = defaultdict(set)                 # address -> callsigns we decoded
    altitudes = []
    n = 0
    for path in sorted(glob.glob(f"{DATA}/raw_*.txt")) + sorted(glob.glob(f"{DATA}/afternoon*.txt")):
        for m in hex_messages(path):
            f = fields(m)
            n += 1
            by_type[f["tc"]] += 1
            if "callsign" in f and f["callsign"]:
                ours[f["icao"]].add(f["callsign"])
            if "altitude" in f:
                altitudes.append(f["altitude"])

    print(f"{n} ADS-B messages")
    print("\nby type code:")
    for tc, count in sorted(by_type.items()):
        print(f"  {tc:2}  {TYPE_NAMES.get(tc, 'other'):35} {count}")

    every_callsign = sorted({c for cs in ours.values() for c in cs})
    print(f"\n{len(ours)} aircraft identified, {len(every_callsign)} distinct callsigns")
    print("airlines (first three letters):", Counter(c[:3] for c in every_callsign).most_common(10))

    theirs = dump1090_callsigns(sorted(glob.glob(f"{DATA}/sbs_*.txt")))
    shared = [a for a in ours if a in theirs]
    agree = [a for a in shared if theirs[a] in ours[a]]
    print(f"\ncallsign check vs dump1090: {len(agree)} of {len(shared)} shared aircraft agree")
    for a in shared:
        if a not in agree:
            print("  disagree:", a, sorted(ours[a]), "vs", theirs[a])

    plt.hist(altitudes, bins=90, range=(0, 45000))
    plt.xlabel("altitude (ft)")
    plt.ylabel("position messages")
    plt.title("Altitudes heard, from our own decoding")
    plt.savefig("results/altitudes.png", dpi=150)