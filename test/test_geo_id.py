import pytest
from pytest import approx
from future.geo_id import spherical_centroid_lonlat

def test_spherical_centroid_empty():
    assert spherical_centroid_lonlat([]) == (0.0, 0.0)

def test_spherical_centroid_single_point():
    assert spherical_centroid_lonlat([(10.0, 20.0)]) == (approx(10.0), approx(20.0))

def test_spherical_centroid_two_points():
    # Simple case on the equator
    points = [(0.0, 0.0), (10.0, 0.0)]
    lon, lat = spherical_centroid_lonlat(points)
    assert lon == approx(5.0)
    assert lat == approx(0.0)

def test_spherical_centroid_antimeridian():
    # Points on either side of the antimeridian
    points = [(179.0, 0.0), (-179.0, 0.0)]
    lon, lat = spherical_centroid_lonlat(points)
    # The average should be at 180 (or -180)
    assert abs(lon) == approx(180.0)
    assert lat == approx(0.0)

def test_spherical_centroid_poles():
    # North pole
    points = [(0.0, 90.0), (120.0, 90.0)]
    lon, lat = spherical_centroid_lonlat(points)
    assert lat == approx(90.0)

    # South pole
    points = [(45.0, -90.0), (-45.0, -90.0)]
    lon, lat = spherical_centroid_lonlat(points)
    assert lat == approx(-90.0)

def test_spherical_centroid_distributed():
    # Points forming a triangle in the northern hemisphere
    points = [(0.0, 0.0), (10.0, 0.0), (5.0, 10.0)]
    lon, lat = spherical_centroid_lonlat(points)
    assert 0.0 < lon < 10.0
    assert 0.0 < lat < 10.0

def test_spherical_centroid_opposite_points():
    # Points on opposite sides of the earth
    # Result is mathematically undefined on the sphere surface.
    # We just ensure it returns finite numbers and doesn't crash.
    points = [(0.0, 0.0), (180.0, 0.0)]
    lon, lat = spherical_centroid_lonlat(points)
    import math
    assert math.isfinite(lon)
    assert math.isfinite(lat)
