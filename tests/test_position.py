import pyModeS as pms
import pytest

from fields import fields, local_position, nl, position

EVEN = "8D40621D58C382D690C8AC2863A7"
ODD = "8D40621D58C386435CC412692AD6"


@pytest.mark.parametrize("odd_newer", [False, True])
def test_position_matches_pymodes(odd_newer):
    t_even, t_odd = (0, 1) if odd_newer else (1, 0)
    ours = position(fields(EVEN), fields(ODD), odd_newer)
    assert ours == pytest.approx(pms.adsb.position(EVEN, ODD, t_even, t_odd), abs=1e-5)


@pytest.mark.parametrize("lat, zones", [(0, 59), (52.2572, 36), (-52.2572, 36), (87, 2), (89, 1)])
def test_nl_known_latitudes(lat, zones):
    assert nl(lat) == zones


def test_position_latitudes_in_different_bands_returns_none():
    # 53.085 N (36 zones) and 53.105 N (35 zones): the band edge is near 53.095 N
    even = {"lat_cpr": 111084, "lon_cpr": 0}
    odd = {"lat_cpr": 92185, "lon_cpr": 0}
    assert position(even, odd, odd_newer=True) is None


@pytest.mark.parametrize("msg, expected", [(EVEN, (52.2572, 3.91937)), (ODD, (52.26578, 3.93891))])
def test_local_position_matches_pair_method(msg, expected):
    assert local_position(fields(msg), 52.258, 3.918) == pytest.approx(expected, abs=1e-5)


def test_local_position_reference_in_neighbouring_zone_still_decodes():
    # reference 4.9 degrees west of the aircraft, across the 10-degree-zone edge at 0 E
    assert local_position(fields(EVEN), 52.258, -1.0) == pytest.approx((52.2572, 3.91937), abs=1e-5)
