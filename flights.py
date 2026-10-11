import math
import sys
from collections import defaultdict
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

try:
    from receiver import RECEIVER          # (lat, lon) of the antenna; git-ignored, stays on this machine
except ImportError:
    RECEIVER = None
from coverage import distance_km

from paths import data_files
GAP_S = 600          # unheard this long = a new flight
MAX_KM = 150         # farther than this from the receiver = a bad position
MAX_KM_S = 0.35      # faster than any airliner (about 1260 km/h) = a bad position
STEP_S = 60          # video: one frame per minute of real time
TRAIL_S = 300        # each aircraft drags its last five minutes behind it


def load(paths):
    """Positions (time, address, altitude, lat, lon) and callsigns from timestamped decoded files."""
    pos, calls, last = [], {}, {}
    for path in paths:
        with open(path) as f:
            for line in f:
                stamp, _, rest = line.partition(",")
                fields = rest.strip().split(",")
                if len(fields) < 16 or fields[0] != "MSG":
                    continue
                t, addr = float(stamp), fields[4]
                if fields[1] == "1" and fields[10].strip():
                    calls[addr] = fields[10].strip()
                elif fields[1] == "3" and fields[14] and fields[15]:
                    lat, lon = float(fields[14]), float(fields[15])
                    if (lat, lon) == last.get(addr):
                        continue            # dump1090 repeats the last known position under a new time
                    last[addr] = (lat, lon)
                    if distance_km(*RECEIVER, lat, lon) < MAX_KM:      # drop the bad pairings
                        alt = float(fields[11]) if fields[11] else math.nan
                        pos.append((t, addr, alt, lat, lon))
    return pos, calls


def split_flights(pos):
    """Group by address, then split wherever the aircraft went unheard for GAP_S."""
    by_addr = defaultdict(list)
    for p in pos:
        by_addr[p[1]].append(p)
    flights = []
    for track in by_addr.values():
        track.sort()
        current = [track[0]]
        for p in track[1:]:
            last = current[-1]
            if p[0] - last[0] > GAP_S:
                flights.append(current)
                current = [p]
                continue
            dt = max(p[0] - last[0], 1.0)
            if distance_km(last[3], last[4], p[3], p[4]) / dt > MAX_KM_S:
                continue                      # a jump no aircraft can make: skip it
            current.append(p)
        flights.append(current)
    return flights


if __name__ == "__main__":
    pattern = sys.argv[1] if len(sys.argv) > 1 else "sbs_t_*"       # e.g. sbs_t_20261006
    tag = pattern.replace("*", "").replace("sbs_t_", "") or "all"
    pos, calls = load(data_files(f"{pattern}.txt"))
    flights = split_flights(pos)
    clean = sorted(p for fl in flights for p in fl)     # what survived the speed cut
    print(f"{len(pos)} positions, {len(clean)} after the speed cut, {len(flights)} flights")

    # Static: every flight as its own line
    fig, ax = plt.subplots(figsize=(8, 8))
    for fl in flights:
        ax.plot([p[4] for p in fl], [p[3] for p in fl], lw=0.6)
    ax.plot(RECEIVER[1], RECEIVER[0], marker="*", color="red", markersize=15)
    ax.set_title(f"{len(flights)} flights")
    fig.savefig(f"results/flights_{tag}.png", dpi=150)

    # The longest few, by name
    for fl in sorted(flights, key=len, reverse=True)[:10]:
        start = datetime.fromtimestamp(fl[0][0]).strftime("%H:%M")
        print(f"{calls.get(fl[0][1], fl[0][1]):10} {start}  {len(fl)} positions")

    # Video: aircraft moving, trails fading out after five minutes
    t = np.array([p[0] for p in clean])
    lat = np.array([p[3] for p in clean])
    lon = np.array([p[4] for p in clean])
    alt = np.array([p[2] for p in clean])

    vfig, vax = plt.subplots(figsize=(8, 8))
    vax.set_xlim(lon.min(), lon.max())
    vax.set_ylim(lat.min(), lat.max())
    vax.plot(RECEIVER[1], RECEIVER[0], marker="*", color="red", markersize=12)
    dots = vax.scatter([], [], c=[], s=4, cmap="viridis", vmin=0, vmax=45000)
    vfig.colorbar(dots, label="altitude (ft)")
    frames = np.arange(t.min(), t.max(), STEP_S)

    def draw(now):
        m = (t > now - TRAIL_S) & (t <= now)
        dots.set_offsets(np.column_stack([lon[m], lat[m]]))
        dots.set_array(alt[m])
        vax.set_title(datetime.fromtimestamp(now).strftime("%a %H:%M"))
        return dots,

    FuncAnimation(vfig, draw, frames=frames).save(f"results/flights_{tag}.mp4", fps=30)

    top = sorted(flights, key=len, reverse=True)[:9]
    fig, axes = plt.subplots(3, 3, figsize=(12, 12))
    for ax, fl in zip(axes.flat, top):
        sc = ax.scatter([p[4] for p in fl], [p[3] for p in fl], c=[p[2] for p in fl],
                        s=3, cmap="viridis", vmin=0, vmax=45000)
        ax.plot(RECEIVER[1], RECEIVER[0], marker="*", color="red", markersize=10)
        start = datetime.fromtimestamp(fl[0][0]).strftime("%H:%M")
        ax.set_title(f"{calls.get(fl[0][1], fl[0][1])}  {start}", fontsize=9)
        ax.set_xticks([]); ax.set_yticks([])
    fig.savefig(f"results/top_flights_{tag}.png", dpi=150)

    print("receiver:", RECEIVER)
    lats = [p[3] for p in clean]; lons = [p[4] for p in clean]
    print("lat range:", min(lats), max(lats))
    print("lon range:", min(lons), max(lons))
    print("farthest kept:", max(distance_km(*RECEIVER, p[3], p[4]) for p in clean), "km")