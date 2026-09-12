"""Tests for is_point_near_route geometry (DOJP-37)

The route check exists because Airlabs ships stale positions - a flight
reported somewhere its route could never take it. The check used to include a
lat/lng bounding-box pre-filter whose date-line branch ran the wrong test and
whose latitude cap rejected polar great circles; it rejected real users under
real flights while catching nothing the geodesic check misses. These cases pin
the geometry so the box cannot quietly return.
"""

import pytest

from app.location_utils import is_point_near_route

AIRPORTS = {
    "SYD": (-33.9461, 151.1772),
    "LAX": (33.9425, -118.4081),
    "JFK": (40.6413, -73.7781),
    "NRT": (35.7647, 140.3864),
    "BNE": (-27.3842, 153.1175),
    "DFW": (32.8998, -97.0403),
    "ANC": (61.1744, -149.9964),
    "NGB": (29.8267, 121.4619),
    "LHR": (51.4700, -0.4543),
    "BOS": (42.3656, -71.0096),
}


def _near(point, origin, dest):
    plat, plng = point
    olat, olng = AIRPORTS[origin]
    dlat, dlng = AIRPORTS[dest]
    return is_point_near_route(plat, plng, olat, olng, dlat, dlng)


@pytest.mark.unit
def test_user_under_a_date_line_route_is_valid():
    """Fiji sits directly beneath SYD->LAX. The old bounding box rejected
    users precisely in the region a date-line route actually crosses."""
    assert _near((-17.7, 178.0), "SYD", "LAX") is True


@pytest.mark.unit
def test_user_under_a_polar_route_is_valid():
    """JFK->NRT passes over Alaska at ~65N - far above both endpoints'
    latitudes. Great circles leave the box their endpoints span."""
    assert _near((64.84, -147.7), "JFK", "NRT") is True


@pytest.mark.unit
def test_wildly_wrong_route_is_rejected():
    """BNE->DFW seen from Connecticut - the case the old bounding box was
    written for. The geodesic check rejects it on its own (2,285 km off)."""
    assert _near((41.22, -73.37), "BNE", "DFW") is False


@pytest.mark.unit
def test_stale_position_far_from_route_is_rejected():
    """ANC->NGB reported over New York - a real rejection observed in
    production logs; 5,400 km from the geodesic."""
    assert _near((40.71, -74.01), "ANC", "NGB") is False


@pytest.mark.unit
def test_point_far_from_a_polar_route_is_still_rejected():
    """Relaxing the box must not have opened the gates: London is 5,400 km
    from the JFK->NRT geodesic and must still fail."""
    assert _near((51.5, -0.13), "JFK", "NRT") is False


@pytest.mark.unit
def test_ordinary_transatlantic_underflight_is_valid():
    """A user in Boston under a JFK->LHR departure - the everyday case."""
    assert _near((42.4, -71.0), "JFK", "LHR") is True


@pytest.mark.unit
def test_endpoint_proximity_still_applies_ratio_check():
    """Near an endpoint but further from it than half the route length is
    still rejected - the short-hop false-positive guard."""
    # 45km FRG->HPN style case: point ~100km from both ends of a ~45km route
    assert is_point_near_route(41.5, -74.5, 40.729, -73.413, 41.067, -73.708) is False
