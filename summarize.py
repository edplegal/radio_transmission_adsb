"""Run the whole analysis suite on every recording and write results/summary_alldata.md.

Every number in the summary comes from this run. Nothing from the receiver's location is
printed: positions are reduced to distance and bearing before they reach the text.
"""
import math
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np

from coverage import bearing_deg, distance_km
from fields import fields, local_position, nl
from paths import data_files
from inventory import deduplicated, fmt, inventory, overlaps, table_markdown
try:
    from receiver import RECEIVER          # (lat, lon) of the antenna; git-ignored, stays on this machine
except ImportError:
    RECEIVER = None
from positions import MAX_AGE_LINES, MAX_AGE_S, MAX_KM, compare_methods, decode_positions
from survey import TYPE_NAMES, dump1090_callsigns

OUT = "results/summary_alldata.md"
EARTH_KM = 6371.0
PY = sys.executable


def run(cmd):
    """Run a script, return its stdout without the urllib3 warning noise."""
    r = subprocess.run(cmd, capture_output=True, text=True)
    lines = [ln for ln in (r.stdout + r.stderr).splitlines()
             if "NotOpenSSLWarning" not in ln and "warnings.warn" not in ln]
    return "\n".join(lines).strip()


def flights_output(tag):
    """flights.py's printed summary for one day. Its video takes minutes to render, so a day is only
    redone when one of its files changed after the last run (in practice: today, still recording)."""
    cache = f"results/flights_{tag}.txt"
    newest = max(os.path.getmtime(p) for p in data_files(f"sbs_t_{tag}.txt"))
    if os.path.exists(cache) and os.path.getmtime(cache) > newest:
        with open(cache) as f:
            return f.read()
    out = run([PY, "flights.py", f"sbs_t_{tag}"])
    if re.match(r"\d+ positions, \d+ after the speed cut, \d+ flights", out):
        with open(cache, "w") as f:
            f.write(out)
    return out


def day_of(t, name):
    """Calendar day a line belongs to: its timestamp, else the day its file was started."""
    if t is not None:
        return datetime.fromtimestamp(t).strftime("%Y-%m-%d")
    m = re.search(r"(\d{4})(\d{2})(\d{2})", name)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def elevation_deg(alt_ft, dist_km):
    """Angle above the horizontal from the receiver to the aircraft, with Earth's curvature,
    ignoring the receiver's own height above sea level (under half a degree beyond 30 km)."""
    h = alt_ft * 0.3048 / 1000
    return math.degrees(math.atan2(h - dist_km ** 2 / (2 * EARTH_KM), dist_km))


def corrupt_positions(single):
    """Indices of position messages whose coarse position bits disagree with both neighbouring
    messages of the same parity from the same aircraft, while those two agree with each other.

    The top 6 bits of each 17-bit field move by at most one step in the minute or so between
    neighbours (a step is 1/64 of a zone, about 10 km); a message that jumps several steps and
    comes straight back is a corrupt message that happened to pass the 24-bit checksum.
    Neighbours further apart than two minutes are not used, because the same aircraft flying
    the same approach on another day would otherwise look like a jump.
    """
    by = defaultdict(list)
    for i, p in enumerate(single):
        f = fields(p[6])
        by[(p[1], f["odd"])].append((i, p[0], f["lat_cpr"] >> 11, f["lon_cpr"] >> 11))
    bad = set()
    for lst in by.values():
        for k in range(1, len(lst) - 1):
            (_, k0, la0, lo0), (i, km, la, lo), (_, k1, la1, lo1) = lst[k - 1], lst[k], lst[k + 1]
            # neighbours must be from the same pass, not the same approach flown on another day:
            # within 120 s (timestamped keys) or 500 ADS-B messages (untimestamped keys)
            near = 120 if km > 0 else 500
            if abs(km - k0) > near or abs(k1 - km) > near:
                continue
            if abs(la0 - la1) <= 1 and abs(lo0 - lo1) <= 1 and (abs(la - la0) > 2 or abs(lo - lo0) > 2):
                bad.add(i)
    return bad


def geometry(md, adsb, per_day):
    """Sections 5-7: everything that needs the receiver's position. Returns what section 9 uses."""
    # ---------------------------------------------------------------- 5. positions
    md.append("## 5. Positions (`fields.position`, `fields.local_position`)\n")
    stream_all = []                                            # (key, hex) for the single-message method
    for i, (t, h, d) in enumerate(adsb):
        stream_all.append((t if t is not None else -1e9 + i, h))
    single = []                                                # (key, icao, alt, lat, lon, day)
    for (key, h), (_, _, d) in zip(stream_all, adsb):
        f = fields(h)
        if "lat_cpr" in f:
            lat, lon = local_position(f, *RECEIVER)
            single.append((key, f["icao"], f.get("altitude", math.nan), lat, lon, d, h))
    dist = np.array([distance_km(*RECEIVER, p[3], p[4]) for p in single])
    bear = np.array([bearing_deg(*RECEIVER, p[3], p[4]) for p in single])
    corrupt = corrupt_positions(single)
    corrupt_keys = {single[i][0] for i in corrupt}
    for p in single:
        per_day[p[5]]["positions"] += 1
    md.append(f"Single-message method with the receiver as reference, every position message: "
              f"{len(single)} positions from {len({p[1] for p in single})} aircraft. No distance filter. "
              f"Farthest {dist.max():.0f} km; {np.sum(dist > MAX_KM)} beyond {MAX_KM} km. "
              f"{len(corrupt)} messages fail the neighbour-consistency test described under Outliers.\n")

    timed = [(t, h) for t, h, _ in adsb if t is not None]
    pairs, unusable = decode_positions(timed, max_age=MAX_AGE_S)
    single_timed = [p for p in single if p[0] > 0]
    diff = compare_methods([p for p in pairs if distance_km(*RECEIVER, p[3], p[4]) < MAX_KM],
                           [p[:5] for p in single_timed])
    pair_dist = np.array([distance_km(*RECEIVER, p[3], p[4]) for p in pairs]) if pairs else np.array([])
    md.append(f"Pair method on the timestamped data ({len(timed)} messages), partner at most {MAX_AGE_S} s old: "
              f"{len(pairs)} positions ({unusable} pairs unusable because the two latitudes fall in different "
              f"longitude-zone bands); {np.sum(pair_dist > MAX_KM)} beyond {MAX_KM} km. The single-message method "
              f"gives {len(single_timed)} on the same data. Where both have an answer and the pair answer is "
              f"within {MAX_KM} km, the two disagree by at most {1000 * max(diff) if diff else 0:.1f} m.\n")

    untimed = [(k, h) for k, h in stream_all if k < 0]
    pairs_u, unusable_u = decode_positions(untimed, max_age=MAX_AGE_LINES)
    pu_dist = np.array([distance_km(*RECEIVER, p[3], p[4]) for p in pairs_u])
    md.append(f"Pair method on the untimestamped data ({len(untimed)} messages), partner at most {MAX_AGE_LINES} "
              f"messages back: {len(pairs_u)} positions, {np.sum(pu_dist > MAX_KM)} beyond {MAX_KM} km, "
              f"{unusable_u} unusable pairs.\n")

    # outliers, each one explained
    md.append("### Outliers\n")
    by_icao = defaultdict(list)
    for p, d in zip(single, dist):
        by_icao[p[1]].append((p, d))
    far_single = [(p, d) for p, d in zip(single, dist) if d > MAX_KM]
    md.append(f"Corrupt messages: a position message whose coarse position (top 6 bits of each 17-bit field, "
              f"steps of about 10 km) disagrees with both neighbouring same-parity messages from the same "
              f"aircraft while those two agree with each other. {len(corrupt)} found in {len(single)}:")
    for i in sorted(corrupt):
        p, d = single[i], dist[i]
        same = [(q, dq) for q, dq in by_icao[p[1]] if q[0] != p[0]]
        near = min(same, key=lambda x: abs(x[0][0] - p[0]))[0]
        f, nf = fields(p[6]), fields(near[6])
        bits = bin(f["lat_cpr"] ^ nf["lat_cpr"]).count("1") + bin(f["lon_cpr"] ^ nf["lon_cpr"]).count("1")
        md.append(f"- {p[1]} `{p[6]}`: decodes to {d:.0f} km away, "
                  f"altitude {p[2]:.0f} ft; the aircraft's neighbouring messages put it "
                  f"{'within 20 km' if distance_km(*RECEIVER, near[3], near[4]) < 20 else 'between 20 and 60 km'}, "
                  f"altitude {near[2]:.0f} ft; "
                  f"{bits} of the 34 position bits differ from the nearest one"
                  f"{' (same parity)' if f['odd'] == nf['odd'] else ''}.")
    md.append(f"\nSingle-message positions beyond {MAX_KM} km: {len(far_single)}"
              + (" (all of them in the corrupt list above)." if all(i in corrupt for i, d in enumerate(dist) if d > MAX_KM)
                 else ", not all explained by corruption:")
              + "".join(f"\n- {p[1]} `{p[6]}` at {d:.0f} km" for i, (p, d) in enumerate(zip(single, dist))
                        if d > MAX_KM and i not in corrupt))
    md.append("")
    for label, plist, pdist in (("timestamped, 10 s rule", pairs, pair_dist), (f"untimestamped, {MAX_AGE_LINES}-message rule", pairs_u, pu_dist)):
        far = [(p, d) for p, d in zip(plist, pdist) if d > MAX_KM]
        md.append(f"Pair-method positions beyond {MAX_KM} km ({label}): {len(far)}.")
        kinds, others = Counter(), []
        for p, d in far:
            same = [(q, dq) for q, dq in by_icao[p[1]] if dq < MAX_KM]
            if not same:
                kinds["no good position for this aircraft"] += 1
                continue
            q = min(same, key=lambda x: abs(x[0][0] - p[0]))[0]
            dlat = p[3] - q[3]
            zone = 360 / nl(q[3])
            dlon = (p[4] - q[4]) / zone
            partner_key = p[0] - p[5]
            if p[0] in corrupt_keys or any(abs(k - partner_key) < 1e-3 for k in corrupt_keys):
                kinds["corrupt message in the pair (see the corrupt list above)"] += 1
            elif abs(dlat) < 0.3 and abs(abs(dlon) - round(abs(dlon))) < 0.1 and round(abs(dlon)) >= 1:
                kinds["stale pair: longitude off by a whole zone"] += 1
            elif any(abs(dlat - z * round(dlat / z)) < 0.35 and round(abs(dlat) / z) >= 1 for z in (6.0, 360 / 59)):
                kinds["stale pair: latitude off by whole zones (6 deg even, 6.1 deg odd)"] += 1
            else:
                kinds["other"] += 1
                others.append(f"    - {p[1]}: {d:.0f} km away, partner {p[5]:.0f} messages back; latitude differs "
                              f"from the nearest good position by {dlat:+.2f} deg, longitude by {dlon:+.2f} zones "
                              f"of {zone:.2f} deg; the pair's two altitudes: {p[2]} vs {q[2]} ft")
        for k, v in kinds.most_common():
            md.append(f"- {v}: {k}")
            if k == "other":
                md.extend(others)
        md.append("")

    # ---------------------------------------------------------------- 6. coverage and elevation
    md.append("## 6. Coverage and elevation angles\n")
    alt = np.array([p[2] for p in single])
    ok = ~np.isnan(alt) & (dist < MAX_KM)
    ok[list(corrupt)] = False
    elev = np.array([elevation_deg(a, d) for a, d in zip(alt[ok], dist[ok])])
    sector = (bear[ok] // 10).astype(int) * 10
    md.append(f"From {ok.sum()} single-message positions with an altitude, within {MAX_KM} km, corrupt messages "
              f"excluded. Elevation = angle above the horizontal, with Earth's curvature, receiver height ignored. "
              f"Privacy rule: this file carries distances and elevations only; the per-bearing table is written "
              f"to `results/elevation_by_bearing.md`, which is git-ignored and stays on this machine.\n")
    local = ["| bearing | positions | farthest (km) | lowest elevation (deg) | highest elevation (deg) | median altitude (ft) |",
             "|---:|---:|---:|---:|---:|---:|"]
    sec_rows = []
    for s in range(0, 360, 10):
        m = sector == s
        if m.sum() == 0:
            local.append(f"| {s:3d}-{s + 10:3d} | 0 | - | - | - | - |")
            sec_rows.append((s, 0, np.nan, np.nan, np.nan))
            continue
        sec_rows.append((s, m.sum(), dist[ok][m].max(), elev[m].min(), elev[m].max()))
        local.append(f"| {s:3d}-{s + 10:3d} | {m.sum()} | {dist[ok][m].max():.0f} | {elev[m].min():.1f} | "
                     f"{elev[m].max():.1f} | {np.median(alt[ok][m]):.0f} |")
    with open("results/elevation_by_bearing.md", "w") as f:
        f.write("# Elevation and range by bearing (LOCAL ONLY: never commit)\n\n" + "\n".join(local) + "\n")
    lows = np.array([r[3] for r in sec_rows if r[1]])
    md.append("| distance | share of positions |\n|---|---:|")
    for lo_, hi_ in ((0, 20), (20, 40), (40, 60), (60, MAX_KM)):            # coarse on purpose (privacy)
        md.append(f"| {lo_}-{hi_} km | {np.mean((dist[ok] >= lo_) & (dist[ok] < hi_)):.1%} |")
    md.append("")
    md.append(f"Farthest {dist[ok].max():.0f} km. Elevation angle: lowest heard {elev.min():.2f} deg; "
              f"{np.sum(elev < 1)} positions under 1 deg, {np.sum(elev < 2)} under 2 deg, "
              f"{np.sum(elev < 5)} under 5 deg; median {np.median(elev):.1f} deg. "
              f"The lowest elevation heard in each 10-degree sector of bearing ranges from {lows.min():.1f} to "
              f"{lows.max():.1f} deg (median {np.median(lows):.1f}); {int((lows > 5).sum())} of {len(lows)} sectors "
              f"hear nothing below 5 deg.\n")

    # Positions reduced to distance / bearing / altitude, for the report's figures: no coordinates.
    np.savez("results/positions_polar.npz", dist=dist[ok], bear=bear[ok], alt=alt[ok],
             day=np.array([p[5] for p, o in zip(single, ok) if o]))

    fig = plt.figure(figsize=(13, 6))
    ax = fig.add_subplot(1, 2, 1, projection="polar")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    sc = ax.scatter(np.radians(bear[ok]), dist[ok], c=alt[ok], s=1, cmap="viridis", vmin=0, vmax=45000)
    ax.set_rmax(60)
    fig.colorbar(sc, ax=ax, label="altitude (ft)", pad=0.1)
    ax.set_title(f"{ok.sum()} positions: distance (km) by bearing\n({np.sum(dist[ok] > 60)} beyond 60 km not drawn)")
    ax2 = fig.add_subplot(1, 2, 2)
    sx = [r[0] + 5 for r in sec_rows]
    ax2.bar(sx, [r[4] - r[3] if r[1] else 0 for r in sec_rows], bottom=[r[3] if r[1] else 0 for r in sec_rows],
            width=9, color="steelblue", alpha=0.7, label="lowest to highest elevation heard")
    ax2.plot(sx, [r[3] if r[1] else np.nan for r in sec_rows], "k.", label="lowest")
    ax2.set_xlabel("bearing (deg, 0 = north)")
    ax2.set_ylabel("elevation angle (deg)")
    ax2.set_xlim(0, 360)
    ax2.legend(fontsize=8)
    ax2.set_title("elevation range per 10-degree sector")
    fig.tight_layout()
    fig.savefig("results/coverage_elevation.png", dpi=130)
    md.append("Figure (local only, git-ignored): `results/coverage_elevation.png`.\n")
    far_ok = [(p, d) for p, d, o in zip(single, dist, ok) if o and d > 60]
    md.append(f"Positions beyond 60 km (corrupt messages excluded): {len(far_ok)}"
              + (f", from {len({p[1] for p, _ in far_ok})} aircraft:" if far_ok else "."))
    by_far = defaultdict(list)
    for p, d in far_ok:
        by_far[p[1]].append((d, p[2]))
    for a, lst in sorted(by_far.items(), key=lambda kv: -max(x[0] for x in kv[1])):
        dmax = max(lst, key=lambda x: x[0])
        md.append(f"- {a}: {len(lst)} positions, {min(x[0] for x in lst):.0f}-{dmax[0]:.0f} km, "
                  f"altitude {dmax[1]:.0f} ft, elevation at the farthest {elevation_deg(dmax[1], dmax[0]):.2f} deg")
    md.append("")

    # ---------------------------------------------------------------- 7. flights per timestamped day
    md.append("## 7. Flights (`flights.py`, timestamped days)\n")
    md.append("| day | positions read | after speed cut | flights | video |\n|---|---:|---:|---:|---|")
    for tag in sorted({os.path.basename(p)[6:-4] for p in data_files("sbs_t_*.txt")}):
        out = flights_output(tag)
        first = out.splitlines()[0] if out else ""
        m = re.match(r"(\d+) positions, (\d+) after the speed cut, (\d+) flights", first)
        day = f"{tag[:4]}-{tag[4:6]}-{tag[6:]}"
        if m:
            per_day[day]["flights"] = int(m.group(3))
            md.append(f"| {day} | {m.group(1)} | {m.group(2)} | {m.group(3)} | `results/flights_{tag}.mp4` |")
        else:
            md.append(f"| {day} | could not run: `{first[:60]}` | | | |")
    md.append("\n(`flights.py` reads dump1090's decoded positions, skips its repeated stale positions, applies "
              f"the {MAX_KM} km and 0.35 km/s cuts, and splits at 10-minute silences.)\n")
    return {"single": single, "dist": dist, "corrupt": corrupt, "elev": elev, "lows": lows,
            "pairs": pairs, "pairs_u": pairs_u, "unusable": unusable, "unusable_u": unusable_u}


def main():
    md = []
    rows = inventory()
    ov = overlaps(rows)

    # ---------------------------------------------------------------- 1. inventory
    md.append("# Summary of all recordings\n")
    md.append(f"Generated {datetime.now():%Y-%m-%d %H:%M} by `summarize.py` on the data folder as it stands on this "
              f"machine. Latest line in any file: {fmt(max(r['last'] for r in rows))}.\n")
    md.append("## 1. Inventory\n")
    md.append(table_markdown(rows) + "\n")
    empty = [r["name"] for r in rows if r["lines"] == 0]
    mixed = [r["name"] for r in rows if r["stamped"] and r["unstamped"]]
    dropped = {n: v for n, v in ov.items() if v[1] is not None}
    md.append(f"- Empty files: {', '.join(empty) if empty else 'none'}.")
    md.append(f"- Files mixing timestamped and bare lines: {', '.join(mixed) if mixed else 'none'}.")
    md.append(f"- Content repeated from an earlier file (runs of {10} identical consecutive lines, at least 100 of "
              f"them): {', '.join(f'{n} lines {v[1]}-{v[2]}' for n, v in dropped.items()) if dropped else 'none'}. "
              + ("Those line ranges are excluded below. " if dropped else "")
              + f"Single identical lines are not duplicates: a transponder "
              f"repeats its identification message every few seconds, and 53-67% of lines in every raw file "
              f"are byte-identical repeats of an earlier line in the same file.")
    md.append("- 'first'/'last' for files without timestamps come from the filename (start) and the file's "
              "modification time (end).")
    gaps = [(r["name"], a, b) for r in rows for a, b in r["gaps"]]
    md.append(f"- Gaps longer than 10 minutes in timestamped files: {len(gaps)}" +
              ("".join(f"\n    - {n}: {fmt(a)} -> {fmt(b)} ({(b - a) / 60:.0f} min)" for n, a, b in gaps) if gaps else "."))
    md.append("")

    # ---------------------------------------------------------------- 2. messages, deduplicated
    raw = list(deduplicated(rows, "raw"))                      # (t or None, payload, file)
    msgs = []                                                  # (t or running index, hex, day)
    hex_re = re.compile(r"\*([0-9A-Fa-f]+);")
    for i, (t, p, name) in enumerate(raw):
        m = hex_re.search(p)
        if m:
            msgs.append((t, m.group(1).upper(), day_of(t, name)))
    adsb = [(t, h, d) for t, h, d in msgs if len(h) == 28 and int(h[:2], 16) >> 3 == 17]
    md.append("## 2. Message stream\n")
    md.append(f"{len(raw)} raw lines after deduplication, {len(msgs)} parse as hex messages, "
              f"{len(adsb)} are 112-bit ADS-B (downlink format 17). {sum(1 for t, _, _ in adsb if t is not None)} "
              f"of those carry a timestamp.\n")

    # ---------------------------------------------------------------- 3. tests, receiver versions, sweep
    md.append("## 3. Receiver on the test recording and on synthetic data\n")
    md.append("Tests (`pytest tests`):\n```\n" + run([PY, "-m", "pytest", "-q", "tests"]).splitlines()[-1] + "\n```\n")
    md.append("Every decoder version replayed on `modes1.bin` against dump1090's 85 ADS-B messages "
              "(`versions.py`):\n```\n" + run([PY, "versions.py"]) + "\n```\n")
    md.append("`compare.py` (current code; misses classified):\n```\n" + run([PY, "compare.py"]) + "\n```\n")
    sweep = run([PY, "sweep.py"])
    md.append("Synthetic noise sweep (`sweep.py`, 90 planted messages per point):\n```\n" + sweep + "\n```\n")

    # ---------------------------------------------------------------- 4. survey
    md.append("## 4. Field survey (`fields.py` over every ADS-B message)\n")
    by_type = Counter()
    calls = defaultdict(set)
    per_day = defaultdict(lambda: {"msgs": 0, "aircraft": set(), "positions": 0, "flights": "-",
                                   "hours": 0.0, "gaps": 0})
    altitudes = []
    for t, h, d in adsb:
        f = fields(h)
        by_type[f["tc"]] += 1
        per_day[d]["msgs"] += 1
        per_day[d]["aircraft"].add(f["icao"])
        if f.get("callsign"):
            calls[f["icao"]].add(f["callsign"])
        if "altitude" in f:
            altitudes.append(f["altitude"])
    md.append("| type code | meaning | messages | share |\n|---:|---|---:|---:|")
    for tc, c in sorted(by_type.items()):
        md.append(f"| {tc} | {TYPE_NAMES.get(tc, 'other')} | {c} | {c / len(adsb):.1%} |")
    every = sorted({c for cs in calls.values() for c in cs})
    airlines = Counter(c[:3] for c in every if c[:3].isalpha()).most_common(12)
    md.append(f"\n{len({f for _, h, _ in adsb for f in [h[2:8]]})} distinct aircraft addresses; "
              f"{len(calls)} of them sent a callsign; {len(every)} distinct callsigns.")
    md.append("Most common callsign prefixes (airline codes): " +
              ", ".join(f"{a} {n}" for a, n in airlines) + ".")
    theirs = dump1090_callsigns(data_files("sbs*.txt"))
    shared = [a for a in calls if a in theirs]
    agree = [a for a in shared if theirs[a] in calls[a]]
    md.append(f"Callsign check against dump1090: {len(agree)} of {len(shared)} shared aircraft agree"
              + ("." if len(agree) == len(shared) else "; disagreements: " +
                 ", ".join(f"{a} {sorted(calls[a])} vs {theirs[a]}" for a in shared if a not in agree) + "."))
    alts = np.array(altitudes)
    md.append(f"Altitudes in position messages: {len(alts)} values, median {np.median(alts):.0f} ft, "
              f"10th-90th percentile {np.percentile(alts, 10):.0f}-{np.percentile(alts, 90):.0f} ft, "
              f"{np.mean(alts < 10000):.0%} below 10,000 ft.\n")

    # ---------------------------------------------------------------- 5-7. positions, coverage, flights
    if RECEIVER is None:
        g = None
        md.append("## 5-7. Positions, coverage and flights\n")
        md.append("Not computed: the receiver's position (`adsb/receiver.py`, `RECEIVER = (lat, lon)`, git-ignored) "
                  "is not on this machine. Add it and rerun.\n")
    else:
        g = geometry(md, adsb, per_day)

    # ---------------------------------------------------------------- 8. per day
    md.append("## 8. Per day\n")
    for r in rows:
        if r["kind"] != "raw" or r["first"] is None:
            continue
        d = day_of(r["first"] if r["stamped"] else None, r["name"])
        span = (r["last"] - r["first"]) / 3600 - sum(b - a for a, b in r["gaps"]) / 3600
        per_day[d]["hours"] += max(span, 0)
        per_day[d]["gaps"] += len(r["gaps"])
    md.append("Lines without timestamps are assigned to the day their file was started (the old recorder "
              "started a new file each time it was restarted, typically morning and evening, so a file "
              "started at 18:33 and ending at 06:59 counts under its start date). Hours = file spans minus gaps.\n")
    md.append("| day | ADS-B messages | aircraft | positions (single-message) | flights | recording hours | gaps > 10 min | messages/hour |")
    md.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    tot = {"msgs": 0, "positions": 0, "hours": 0.0, "gaps": 0}
    all_aircraft = set()
    for d in sorted(per_day):
        v = per_day[d]
        rate = v["msgs"] / v["hours"] if v["hours"] else float("nan")
        md.append(f"| {d} | {v['msgs']} | {len(v['aircraft'])} | {v['positions']} | {v['flights']} | "
                  f"{v['hours']:.1f} | {v['gaps']} | {rate:.0f} |")
        tot["msgs"] += v["msgs"]; tot["positions"] += v["positions"]; tot["hours"] += v["hours"]; tot["gaps"] += v["gaps"]
        all_aircraft |= v["aircraft"]
    md.append(f"| **total** | {tot['msgs']} | {len(all_aircraft)} | {tot['positions']} | - | {tot['hours']:.1f} | "
              f"{tot['gaps']} | {tot['msgs'] / tot['hours']:.0f} |\n")

    # ---------------------------------------------------------------- 9. surprises
    md.append("## 9. Across days: anything surprising or inconsistent\n")
    rates = {d: v["msgs"] / v["hours"] for d, v in per_day.items() if v["hours"] > 1}
    if rates:
        hi, lo = max(rates, key=rates.get), min(rates, key=rates.get)
        md.append(f"- Message rate ranges from {rates[lo]:.0f}/h ({lo}) to {rates[hi]:.0f}/h ({hi}); days whose "
                  f"files cover mostly night hours sit at the low end.")
    per_h = {d: len(v["aircraft"]) / v["hours"] for d, v in per_day.items() if v["hours"] > 1}
    md.append("- Distinct aircraft per recording hour, by day: " + ", ".join(f"{d} {x:.0f}" for d, x in sorted(per_h.items())) + ".")
    if g:
        single, dist, corrupt, elev, lows = g["single"], g["dist"], g["corrupt"], g["elev"], g["lows"]
        pairs, pairs_u, unusable, unusable_u = g["pairs"], g["pairs_u"], g["unusable"], g["unusable_u"]
        share = {d: v["positions"] / v["msgs"] for d, v in per_day.items() if v["msgs"] > 1000}
        md.append(f"- Share of ADS-B messages that are position messages, by day (days with over 1000 messages): "
                  + ", ".join(f"{d} {s:.1%}" for d, s in sorted(share.items())) + f"; overall {len(single) / len(adsb):.1%}.")
        md.append(f"- Lowest elevation per 10-degree sector ranges {lows.min():.1f}-{lows.max():.1f} deg; "
                  f"{np.sum(elev < 2)} of {len(elev)} positions are below 2 deg elevation. The effective horizon is "
                  f"several degrees up in every direction (indoor antenna).")
        if corrupt:
            md.append(f"- {len(corrupt)} corrupt position message(s) passed the 24-bit checksum in {len(single)} position "
                      f"messages (1 in {len(single) // len(corrupt)}); {sum(1 for i in corrupt if dist[i] < MAX_KM)} of "
                      f"them landed within {MAX_KM} km and would have passed a distance cut.")
        md.append(f"- {unusable} + {unusable_u} even/odd pairs were unusable because the latitudes straddled a "
                  f"longitude-zone band edge (1 in {(len(pairs) + len(pairs_u)) // max(unusable + unusable_u, 1)} pairs).")
    md.append("- Days not on this machine are simply absent from the inventory."
              + ("" if g else " Positions, coverage and flights are pending the receiver's position.") + "\n")

    with open(OUT, "w") as f:
        f.write("\n".join(md))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
