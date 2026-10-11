import math

import folium
from folium.plugins import HeatMap
import matplotlib.pyplot as plt
try:
    from receiver import RECEIVER          # (lat, lon) of the antenna; git-ignored, stays on this machine
except ImportError:
    RECEIVER = None

EARTH_KM = 6371.0
from paths import data_files

def distance_km(lat1, lon1, lat2, lon2):
    """Great-circle distance (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2):
    """Compass direction from point 1 to point 2: 0 = north, 90 = east."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.atan2(x, y)) % 360



def positions(path):
    """Yield (address, altitude, lat, lon) from every position line in one decoded file."""
    with open(path) as f:
        for line in f:
            if not line.startswith("MSG"):            # timestamped files start "1759612345.123,MSG,..."
                line = line.split(",", 1)[-1]
            fields = line.strip().split(",")
            if len(fields) < 16 or fields[0] != "MSG" or fields[1] != "3":
                continue
            if fields[14] and fields[15]:
                alt = float(fields[11]) if fields[11] else math.nan
                yield fields[4], alt, float(fields[14]), float(fields[15])


if __name__ == "__main__":
    rows = [r for path in data_files("sbs_*.txt") for r in positions(path)]

    import statistics
    clat = statistics.median(r[2] for r in rows)
    clon = statistics.median(r[3] for r in rows)
    good = [r for r in rows if abs(r[2] - clat) < 3 and abs(r[3] - clon) < 3]
    print(f"kept {len(good)} of {len(rows)} positions; dropped {len(rows) - len(good)} outliers")
    rows = good

    aircraft = {r[0] for r in rows}
    print(f"{len(rows)} positions from {len(aircraft)} aircraft")

    lats = [r[2] for r in rows]
    lons = [r[3] for r in rows]
    alts = [r[1] for r in rows]

    # Static map: every position, colored by altitude
    fig, ax = plt.subplots(figsize=(8, 8))
    sc = ax.scatter(lons, lats, c=alts, s=2, cmap="viridis")
    ax.set_aspect(1 / math.cos(math.radians(sum(lats) / len(lats))))   # degrees of longitude shrink with latitude
    fig.colorbar(sc, label="altitude (ft)")
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    ax.set_title("Every position heard")
    fig.savefig("results/coverage.png", dpi=150)

    # Interactive map: density of positions on real streets
    m = folium.Map(location=[sum(lats) / len(lats), sum(lons) / len(lons)], zoom_start=9)
    HeatMap(list(zip(lats, lons)), radius=6).add_to(m)
    m.save("results/coverage.html")

    rlat, rlon = RECEIVER
    dist = [distance_km(rlat, rlon, la, lo) for la, lo in zip(lats, lons)]
    bear = [bearing_deg(rlat, rlon, la, lo) for la, lo in zip(lats, lons)]

    # Mark the receiver on the existing map
    ax.plot(rlon, rlat, marker="*", color="red", markersize=15)
    fig.savefig("results/coverage.png", dpi=150)

    # Polar view: direction around the circle, distance outward
    fig2 = plt.figure(figsize=(8, 8))
    pax = fig2.add_subplot(projection="polar")
    pax.set_theta_zero_location("N")        # north at the top
    pax.set_theta_direction(-1)             # clockwise, like a compass
    sc2 = pax.scatter([math.radians(b) for b in bear], dist, c=alts, s=2, cmap="viridis")
    fig2.colorbar(sc2, label="altitude (ft)", pad=0.1)
    pax.set_title("Distance (km) by compass direction")
    fig2.savefig("results/range_polar.png", dpi=150)
    print(f"farthest position: {max(dist):.0f} km")