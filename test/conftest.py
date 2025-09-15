import os
import shutil
import sys
import pytest

# Add repository root to sys.path so tests can import top-level modules during collection.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(scope="session")
def assets_dir():
    """Return the absolute path to the assets/test_data directory."""
    here = os.path.dirname(os.path.dirname(__file__))
    assets = os.path.join(here, "data_assets", "test_data")
    if not os.path.exists(assets):
        # fallback to repository root data_assets
        assets = os.path.join(os.path.dirname(here), "data_assets", "test_data")
    return assets


@pytest.fixture
def temp_test_output(tmp_path):
    """Provide a temporary directory for tests that need to write files."""
    d = tmp_path / "test_output"
    d.mkdir()
    yield str(d)
    # cleanup handled by tmp_path


@pytest.fixture
def osm_sample_gdf():
    """Return a small deterministic OSM-like GeoDataFrame for tests."""
    import geopandas as gpd
    from shapely.geometry import LineString, Point, Polygon

    # Create a small square network (closed loop) so polygonization yields a protoblock
    lines = [
        LineString([(0, 0), (0, 1)]),
        LineString([(0, 1), (1, 1)]),
        LineString([(1, 1), (1, 0)]),
        LineString([(1, 0), (0, 0)]),
    ]

    gdf = gpd.GeoDataFrame(
        {
            "geometry": lines,
            "highway": ["residential"] * len(lines),
            "building": [None] * len(lines),
            "amenity": [None] * len(lines),
            "shop": [None] * len(lines),
        }
    )
    gdf = gdf.set_crs("EPSG:4326")
    return gdf


# (sys.path already modified at import time)
