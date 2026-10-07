"""Inventory of every recording in data/: what it is, when, how big, and what is wrong with it.

Also builds the deduplicated message streams the other tools should analyse, so nothing is
counted twice when the same message sits in two files (afternoon.txt vs raw_*, or a file
that was moved while the recorder was writing to it).
"""
import glob
import os
import re
from collections import Counter
from datetime import datetime

DATA = "../data"
GAP_S = 600

STAMPED = re.compile(r"^\d{10}\.\d{3},")                 # '1791139612.361,' prefix from stamp.py / recorder.py


def kind(name):
    base = os.path.basename(name)
    if base.startswith("raw") or base.startswith("afternoon"):
        return "raw"
    if base.startswith("sbs"):
        return "decoded"
    return "other"


def payload(line):
    """The message part of a line, without any timestamp prefix: what makes two lines duplicates."""
    if STAMPED.match(line):
        line = line.split(",", 1)[1]
    return line.strip()


def scan(path):
    """One file -> dict of facts for the inventory table."""
    n = stamped = unstamped = 0
    first = last = None
    gaps = []
    prev = None
    lines = []
    with open(path, errors="replace") as f:
        for line in f:
            n += 1
            if STAMPED.match(line):
                stamped += 1
                t = float(line.split(",", 1)[0])
                first = t if first is None else first
                if prev is not None and t - prev > GAP_S:
                    gaps.append((prev, t))
                prev = last = t
            elif line.strip():
                unstamped += 1
            lines.append(payload(line))
    mtime = os.path.getmtime(path)
    m = re.search(r"(\d{8})_(\d{4})", os.path.basename(path))
    if first is None and m:                                # old files: start from the name, end from mtime
        first = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M").timestamp()
        last = mtime
        source = "filename/mtime"
    elif first is None:
        first, last, source = None, mtime, "mtime only"
    else:
        source = "timestamps"
    return {"path": path, "name": os.path.basename(path), "kind": kind(path), "lines": n,
            "stamped": stamped, "unstamped": unstamped, "first": first, "last": last,
            "time_source": source, "gaps": gaps, "size": os.path.getsize(path), "payloads": lines}


def fmt(t):
    return "-" if t is None else datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M")


def inventory():
    files = sorted(glob.glob(f"{DATA}/*.txt"))
    rows = [scan(p) for p in files]
    return rows


SHINGLE = 10            # consecutive lines; the same 10-line run in two files means copied content,
                        # while a single identical line is just a transponder repeating itself
MIN_SHARED = 100        # fewer shared runs than this is coincidence (a parked aircraft repeating itself)


def shingles(payloads):
    """Set of (position, 10-line run) hashes -> position, for overlap detection."""
    return {hash(tuple(payloads[i:i + SHINGLE])): i for i in range(len(payloads) - SHINGLE + 1)}


def overlaps(rows):
    """For each file: lines that repeat a run already present in an earlier file of the same kind.

    Returns name -> (count of shared 10-line runs, first and last repeated line index) so the
    deduplicated stream can drop exactly that range.
    """
    seen = {"raw": {}, "decoded": {}}
    out = {}
    for r in sorted(rows, key=lambda r: (r["first"] or 0)):
        if r["kind"] not in seen:
            continue
        mine = shingles(r["payloads"])
        shared = [i for h, i in mine.items() if h in seen[r["kind"]]]
        if len(shared) >= MIN_SHARED:
            out[r["name"]] = (len(shared), min(shared), max(shared) + SHINGLE - 1)
        else:
            out[r["name"]] = (len(shared), None, None)
        seen[r["kind"]].update(mine)
    return out


def deduplicated(rows, kind_):
    """Yield (time or None, payload, file name) over all files of one kind, oldest first, with any
    line range that repeats an earlier file's content left out."""
    ov = overlaps(rows)
    for r in sorted((r for r in rows if r["kind"] == kind_), key=lambda r: (r["first"] or 0)):
        _, lo, hi = ov[r["name"]]
        with open(r["path"], errors="replace") as f:
            for i, line in enumerate(f):
                if lo is not None and lo <= i <= hi:
                    continue
                p = payload(line)
                if p:
                    t = float(line.split(",", 1)[0]) if STAMPED.match(line) else None
                    yield t, p, r["name"]


def table_markdown(rows):
    """The inventory as a markdown table."""
    ov = overlaps(rows)
    lines = ["| file | type | timing | first | last | lines | size | overlap with earlier files | flags |",
             "|---|---|---|---|---|---:|---:|---|---|"]
    for r in rows:
        flags = []
        if r["lines"] == 0:
            flags.append("EMPTY")
        if r["stamped"] and r["unstamped"]:
            flags.append(f"MIXED: {r['stamped']} stamped, {r['unstamped']} bare")
        for a, b in r["gaps"]:
            flags.append(f"gap {fmt(a)[11:]}-{fmt(b)[11:]} ({(b - a) / 60:.0f} min)")
        timing = "timestamped" if r["stamped"] and not r["unstamped"] else ("mixed" if r["stamped"] else "none")
        n_shared, lo, hi = ov.get(r["name"], (0, None, None))
        overlap = f"lines {lo}-{hi} ({n_shared} shared runs)" if lo is not None else (
            f"none ({n_shared} coincidental runs)" if n_shared else "none")
        lines.append(f"| {r['name']} | {r['kind']} | {timing} | {fmt(r['first'])} | {fmt(r['last'])} | {r['lines']} |"
                     f" {r['size'] / 1e6:.1f} MB | {overlap} | {'; '.join(flags)} |")
    return "\n".join(lines)


if __name__ == "__main__":
    rows = inventory()
    print(table_markdown(rows))
    total_lines = sum(r["lines"] for r in rows)
    kept = {k: sum(1 for _ in deduplicated(rows, k)) for k in ("raw", "decoded")}
    print(f"\n{len(rows)} files, {total_lines} lines; after removing overlapping ranges: {kept['raw']} raw lines, "
          f"{kept['decoded']} decoded lines")
    for r in rows:
        if r["kind"] == "raw" and r["lines"]:
            rep = sum(v - 1 for v in Counter(r["payloads"]).values())
            print(f"  {r['name']}: {rep} lines ({rep / r['lines']:.0%}) are byte-identical repeats within the file"
                  f" (transponders repeat; not duplicates)")
