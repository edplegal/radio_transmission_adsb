"""Sitting 8: positions from our own decoding of the raw messages, graded against dump1090."""
import math
from collections import defaultdict

import matplotlib.pyplot as plt

from coverage import distance_km
from fields import fields, local_position, position
try:
    from receiver import RECEIVER          # (lat, lon) of the antenna; git-ignored, stays on this machine
except ImportError:
    RECEIVER = None

from paths import data_files
MAX_AGE_S = 10       # the standard: partner message at most this old
MATCH_S = 1.0        # the two recording loops stamp the same message slightly apart
MAX_AGE_LINES = 35   # untimestamped files: about 6 s at the average 5.5 messages per second
MAX_KM = 150         # farther than this from the receiver = a bad pairing


def read_raw(path):
    """Yield (time, message hex) from a timestamped raw file ('1791139612.361, *8D...;')."""
    with open(path) as f:
        for line in f:
            stamp, _, rest = line.partition(",")
            rest = rest.strip()
            if rest.startswith("*") and rest.endswith(";"):
                yield float(stamp), rest[1:-1]


def read_raw_untimed(paths):
    """Yield (running message count, message hex) from the old files, which have no times."""
    count = 0
    for path in paths:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("*") and line.endswith(";"):
                    count += 1
                    yield count, line[1:-1]


def decode_positions(msgs, max_age=MAX_AGE_S):
    """(time, hex) stream -> list of (time, address, altitude, lat, lon, partner age).

    Per aircraft, remember the latest even and the latest odd position message;
    each new one is paired with the latest of the other kind if that is fresh enough.
    """
    latest = defaultdict(dict)                       # address -> {0: (t, f), 1: (t, f)}
    out, unusable = [], 0
    for t, msg in msgs:
        if len(msg) != 28:
            continue
        f = fields(msg)
        if f["df"] != 17 or "lat_cpr" not in f:
            continue
        mine = latest[f["icao"]]
        mine[f["odd"]] = (t, f)
        if 1 - f["odd"] not in mine:
            continue
        t_other, _ = mine[1 - f["odd"]]
        if t - t_other > max_age:
            continue
        p = position(mine[0][1], mine[1][1], odd_newer=bool(f["odd"]))
        if p is None:
            unusable += 1                            # latitudes in different zone-count bands
            continue
        out.append((t, f["icao"], f.get("altitude", math.nan), *p, t - t_other))
    return out, unusable


def decode_local(msgs):
    """(time, hex) stream -> list of (time, address, altitude, lat, lon), one per position message."""
    out = []
    for t, msg in msgs:
        if len(msg) != 28:
            continue
        f = fields(msg)
        if f["df"] == 17 and "lat_cpr" in f:
            out.append((t, f["icao"], f.get("altitude", math.nan), *local_position(f, *RECEIVER)))
    return out


def compare_methods(pairs, local):
    """Distance (km) between the pair and single-message answers for the same message."""
    by_key = {(t, addr): (lat, lon) for t, addr, _, lat, lon in local}
    return [distance_km(lat, lon, *by_key[(t, addr)]) for t, addr, _, lat, lon, _ in pairs]


def read_dump1090(path):
    """address -> list of (time, lat, lon) from a timestamped decoded file."""
    theirs = defaultdict(list)
    with open(path) as f:
        for line in f:
            stamp, _, rest = line.partition(",")
            c = rest.strip().split(",")
            if len(c) >= 16 and c[0] == "MSG" and c[1] == "3" and c[14] and c[15]:
                theirs[c[4]].append((float(stamp), float(c[14]), float(c[15])))
    return theirs


def grade(ours, theirs):
    """Distance (km) from each of our positions to dump1090's at the same moment, where there is one."""
    errors = []
    for t, addr, _, lat, lon, _ in ours:
        near = [p for p in theirs.get(addr, []) if abs(p[0] - t) <= MATCH_S]
        if near:
            _, tlat, tlon = min(near, key=lambda p: abs(p[0] - t))
            errors.append(distance_km(lat, lon, tlat, tlon))
    return errors


if __name__ == "__main__":
    msgs = [m for path in data_files("raw_t_*.txt") for m in read_raw(path)]
    theirs = defaultdict(list)
    for path in data_files("sbs_t_*.txt"):
        for addr, rows in read_dump1090(path).items():
            theirs[addr].extend(rows)
    n_theirs = sum(len(v) for v in theirs.values())

    ours, unusable = decode_positions(msgs)
    errors = grade(ours, theirs)
    print(f"{len(msgs)} messages -> {len(ours)} positions from {len({p[1] for p in ours})} aircraft"
          f" ({unusable} pairs unusable); dump1090 reported {n_theirs}")
    print(f"matched to a dump1090 position: {len(errors)};"
          f" largest disagreement {1000 * max(errors):.1f} m")
    far = [p for p in ours if distance_km(*RECEIVER, p[3], p[4]) > 500]
    print(f"more than 500 km from the receiver: {len(far)}")

    # Loosen the freshness rule and watch bad pairings appear
    print("\nmax partner age   positions   >500 km away")
    for age in (10, 30, 60, 120, 300, 600):
        got, _ = decode_positions(msgs, max_age=age)
        bad = sum(distance_km(*RECEIVER, p[3], p[4]) > 500 for p in got)
        print(f"{age:12d} s   {len(got):9d}   {bad:6d}")

    fig, ax = plt.subplots(figsize=(8, 8))
    sc = ax.scatter([p[4] for p in ours], [p[3] for p in ours], c=[p[2] for p in ours],
                    s=6, cmap="viridis", vmin=0, vmax=45000)
    ax.plot(RECEIVER[1], RECEIVER[0], marker="*", color="red", markersize=15)
    ax.set_aspect(1 / math.cos(math.radians(RECEIVER[0])))
    fig.colorbar(sc, label="altitude (ft)")
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    ax.set_title(f"{len(ours)} positions from our own decoding")
    fig.savefig("results/positions.png", dpi=150)

    # The old recordings have no times, so "fresh" can only mean "few messages ago".
    # At night few messages arrive, a few messages ago can be minutes ago, and stale
    # pairs slip through: the distance cut catches them.
    old = list(read_raw_untimed(data_files("00_raw*.txt") + data_files("raw_2*.txt")))
    got, unusable = decode_positions(old, max_age=MAX_AGE_LINES)
    dist = [distance_km(*RECEIVER, p[3], p[4]) for p in got]
    keep = [p for p, d in zip(got, dist) if d < MAX_KM]
    print(f"\nold recordings: {len(old)} messages -> {len(got)} positions"
          f" ({unusable} pairs unusable), {len(got) - len(keep)} beyond {MAX_KM} km dropped")

    fig, ax = plt.subplots(figsize=(8, 8))
    sc = ax.scatter([p[4] for p in keep], [p[3] for p in keep], c=[p[2] for p in keep],
                    s=2, cmap="viridis", vmin=0, vmax=45000)
    ax.plot(RECEIVER[1], RECEIVER[0], marker="*", color="red", markersize=15)
    ax.set_aspect(1 / math.cos(math.radians(RECEIVER[0])))
    fig.colorbar(sc, label="altitude (ft)")
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    ax.set_title(f"{len(keep)} positions from our own decoding, Sep 28 - Oct 4")
    fig.savefig("results/coverage_own.png", dpi=150)

    # Single-message decoding, with the receiver as the reference point. No pairing, so
    # no stale pairs; what is left is the odd corrupted message that passed the checksum.
    print("\nsingle-message method (reference = receiver):")
    for name, stream, pairs in (("Oct 4 timestamped", msgs, ours), ("old recordings", old, got)):
        local = decode_local(stream)
        dist = [distance_km(*RECEIVER, p[3], p[4]) for p in local]
        plausible = [p for p in pairs if distance_km(*RECEIVER, p[3], p[4]) < MAX_KM]
        diff = compare_methods(plausible, local)
        print(f"  {name}: {len(local)} positions (pair method {len(pairs)}),"
              f" farthest {max(dist):.0f} km with no filter;"
              f" the {len(plausible)} plausible pair positions disagree by at most {1000 * max(diff):.1f} m")
        for p, d in zip(local, dist):
            if d > MAX_KM:
                print(f"    beyond {MAX_KM} km: {p[1]} at {p[3]:.3f}, {p[4]:.3f} ({d:.0f} km), altitude {p[2]}")
        if name == "old recordings":
            fig, ax = plt.subplots(figsize=(8, 8))
            sc = ax.scatter([p[4] for p in local], [p[3] for p in local], c=[p[2] for p in local],
                            s=2, cmap="viridis", vmin=0, vmax=45000)
            ax.plot(RECEIVER[1], RECEIVER[0], marker="*", color="red", markersize=15)
            ax.set_aspect(1 / math.cos(math.radians(RECEIVER[0])))
            fig.colorbar(sc, label="altitude (ft)")
            ax.set_xlabel("longitude")
            ax.set_ylabel("latitude")
            ax.set_title(f"{len(local)} positions, single-message decoding, no distance cut")
            fig.savefig("results/coverage_local.png", dpi=150)
