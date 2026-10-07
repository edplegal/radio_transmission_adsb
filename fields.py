"""Decode the meaning of one ADS-B message (downlink format 17)."""
import math

import numpy as np

from synth import hex_to_bits

CHARS = "#ABCDEFGHIJKLMNOPQRSTUVWXYZ##### ###############0123456789######"


def val(bits, a, b):
    """Bits a up to (not including) b, read as one binary number."""
    return int("".join(map(str, bits[a:b])), 2)


def fields(msg_hex):
    """Message hex -> dict of what it says."""
    bits = hex_to_bits(msg_hex)
    f = {"df": val(bits, 0, 5),                  # format: 17 = ADS-B broadcast
         "icao": f"{val(bits, 8, 32):06X}",     # aircraft address
         "tc": val(bits, 32, 37)}               # type code: how to read the rest

    if 1 <= f["tc"] <= 4:                                       # identification
        cs = "".join(CHARS[val(bits, 40 + 6 * i, 46 + 6 * i)] for i in range(8))
        f["callsign"] = cs.replace("#", "").strip()

    elif 9 <= f["tc"] <= 18:                                    # airborne position
        if bits[47] == 1:                                       # flag: simple altitude encoding
            n = val(np.concatenate([bits[40:47], bits[48:52]]), 0, 11)
            f["altitude"] = 25 * n - 1000
        f["odd"] = int(bits[53])                                # even (0) or odd (1) half of a pair
        f["lat_cpr"] = val(bits, 54, 71)                        # compressed latitude, for sitting 8
        f["lon_cpr"] = val(bits, 71, 88)                        # compressed longitude

    return f


def nl(lat):
    """Number of longitude zones at this latitude: 59 at the equator, fewer toward the poles."""
    if lat == 0:
        return 59
    if abs(lat) >= 87:
        return 2 if abs(lat) == 87 else 1
    a = 1 - math.cos(math.pi / 30)
    return math.floor(2 * math.pi / math.acos(1 - a / math.cos(math.radians(lat)) ** 2))


def position(even, odd, odd_newer):
    """One even and one odd fields() dict from the same aircraft -> (lat, lon) at the newer one.

    None if the two latitudes sit in different longitude-zone bands (unusable pair).
    """
    fe, fo = even["lat_cpr"] / 2**17, odd["lat_cpr"] / 2**17
    j = math.floor(59 * fe - 60 * fo + 0.5)             # latitude zone: the vernier
    lat_e = 360 / 60 * (j % 60 + fe)
    lat_o = 360 / 59 * (j % 59 + fo)
    lat_e -= 360 if lat_e >= 270 else 0                 # southern hemisphere
    lat_o -= 360 if lat_o >= 270 else 0
    if nl(lat_e) != nl(lat_o):
        return None                                     # encoded with different zone counts

    lat = lat_o if odd_newer else lat_e
    zones = nl(lat)
    fe, fo = even["lon_cpr"] / 2**17, odd["lon_cpr"] / 2**17
    m = math.floor(fe * (zones - 1) - fo * zones + 0.5)  # longitude zone: same trick
    n = max(zones - 1 if odd_newer else zones, 1)       # odd messages use one zone fewer
    lon = 360 / n * (m % n + (fo if odd_newer else fe))
    lon -= 360 if lon > 180 else 0                      # west
    return lat, lon


def local_position(f, ref_lat, ref_lon):
    """One position fields() dict plus a reference point within half a zone -> (lat, lon).

    The 17-bit fraction says how far through its zone the aircraft is; the zone itself
    is the one that puts the aircraft nearest the reference (here: the receiver).
    """
    odd = f["odd"]
    d_lat = 360 / (59 if odd else 60)
    frac = f["lat_cpr"] / 2**17
    j = ref_lat // d_lat + math.floor(0.5 + (ref_lat % d_lat) / d_lat - frac)
    lat = d_lat * (j + frac)

    d_lon = 360 / max(nl(lat) - odd, 1)                 # odd messages use one zone fewer
    frac = f["lon_cpr"] / 2**17
    m = ref_lon // d_lon + math.floor(0.5 + (ref_lon % d_lon) / d_lon - frac)
    return lat, d_lon * (m + frac)


if __name__ == "__main__":
    print(fields("8D4840D6202CC371C32CE0576098"))
    print(fields("8D40621D58C382D690C8AC2863A7"))

    even = fields("8D40621D58C382D690C8AC2863A7")
    odd = fields("8D40621D58C386435CC412692AD6")
    print("even newer:", position(even, odd, odd_newer=False))
    print("odd newer: ", position(even, odd, odd_newer=True))
    print("even alone:", local_position(even, 52.258, 3.918))
    print("odd alone: ", local_position(odd, 52.258, 3.918))
