"""Tests for standalone protoblocks generation functionality."""

import geopandas as gpd
import pytest
from unittest.mock import patch
from headless_sidewalkreator import generate_protoblocks
from headless_sidewalkreator.full_sidewalkreator_algorithm import _get_polygonize_clip_geom
from shapely.geometry import Polygon


@pytest.fixture
def test_polygon_gdf():
    """Create a simple test polygon GeoDataFrame."""
    polygon = [Polygon([(-72.53, 42.37), (-72.52, 42.37), (-72.52, 42.38), (-72.53, 42.38)])]
    gdf = gpd.GeoDataFrame(geometry=polygon, crs="EPSG:4326")
    return gdf


@pytest.fixture
def osm_sample_gdf():
    """Create a mock OSM GeoDataFrame with street data."""
    from shapely.geometry import LineString
    
    # Create simple street network that should form blocks
    streets = [
        LineString([(-72.530, 42.370), (-72.520, 42.370)]),  # horizontal bottom
        LineString([(-72.530, 42.380), (-72.520, 42.380)]),  # horizontal top
        LineString([(-72.530, 42.370), (-72.530, 42.380)]),  # vertical left
        LineString([(-72.520, 42.370), (-72.520, 42.380)]),  # vertical right
    ]
    
    gdf = gpd.GeoDataFrame(
        {
            'highway': ['residential', 'residential', 'residential', 'residential'],
            'geometry': streets,
        },
        crs="EPSG:4326"
    )
    return gdf


def test_generate_protoblocks_with_polygon_gdf(test_polygon_gdf, osm_sample_gdf):
    """Test protoblocks generation with polygon GeoDataFrame input."""
    protoblocks_gdf = generate_protoblocks(
        input_polygon_gdf=test_polygon_gdf,
        osm_gdf=osm_sample_gdf
    )
    
    assert isinstance(protoblocks_gdf, gpd.GeoDataFrame)
    assert not protoblocks_gdf.empty
    assert protoblocks_gdf.crs is not None
    # Check that we have polygon geometries
    assert all(geom.geom_type in ['Polygon', 'MultiPolygon'] for geom in protoblocks_gdf.geometry)


def test_generate_protoblocks_with_bbox(osm_sample_gdf):
    """Test protoblocks generation with bounding box input."""
    bbox = (-72.53, 42.37, -72.52, 42.38)
    
    protoblocks_gdf = generate_protoblocks(
        bbox=bbox,
        osm_gdf=osm_sample_gdf
    )
    
    assert isinstance(protoblocks_gdf, gpd.GeoDataFrame)
    assert not protoblocks_gdf.empty
    assert protoblocks_gdf.crs is not None


def test_polygonize_clip_geom_uses_target_crs_bounds():
    """The polygonization closure boundary must be built in the line-network CRS."""
    bbox = (-49.28, -25.44, -49.26, -25.42)
    polygon = Polygon([
        (bbox[0], bbox[1]),
        (bbox[0], bbox[3]),
        (bbox[2], bbox[3]),
        (bbox[2], bbox[1]),
        (bbox[0], bbox[1]),
    ])
    input_gdf = gpd.GeoDataFrame(geometry=[polygon], crs="EPSG:4326")
    target_crs = input_gdf.estimate_utm_crs()

    clip_geom = _get_polygonize_clip_geom(input_gdf, target_crs=target_crs)
    expected_bounds = input_gdf.to_crs(target_crs).total_bounds
    minx, miny, maxx, maxy = expected_bounds

    assert clip_geom.crs == target_crs
    assert clip_geom.total_bounds == pytest.approx(expected_bounds)
    assert clip_geom.geometry.area.iloc[0] == pytest.approx(
        (maxx - minx) * (maxy - miny)
    )


@patch('headless_sidewalkreator.full_sidewalkreator_algorithm.fetch_street_network_for_bbox')
def test_generate_protoblocks_with_place_name(mock_fetch, osm_sample_gdf):
    """Test protoblocks generation with place name input."""
    mock_fetch.return_value = osm_sample_gdf
    
    protoblocks_gdf = generate_protoblocks(
        place_name="Amherst, MA"
    )
    
    assert isinstance(protoblocks_gdf, gpd.GeoDataFrame)
    mock_fetch.assert_called_once()


def test_generate_protoblocks_input_validation():
    """Test that input validation works correctly."""
    # Test no input provided
    with pytest.raises(ValueError, match="Provide exactly one"):
        generate_protoblocks()
    
    # Test multiple inputs provided
    with pytest.raises(ValueError, match="Provide exactly one"):
        generate_protoblocks(
            place_name="Test",
            bbox=(0, 0, 1, 1)
        )


def test_generate_protoblocks_with_parameters(test_polygon_gdf, osm_sample_gdf):
    """Test protoblocks generation with custom parameters."""
    custom_params = {
        "timeout": 30,
        "fallback_default_width": 8.0,
    }
    
    protoblocks_gdf = generate_protoblocks(
        input_polygon_gdf=test_polygon_gdf,
        osm_gdf=osm_sample_gdf,
        parameters=custom_params
    )
    
    assert isinstance(protoblocks_gdf, gpd.GeoDataFrame)
    assert not protoblocks_gdf.empty


def test_generate_protoblocks_empty_osm(test_polygon_gdf):
    """Test protoblocks generation with empty OSM data."""
    # Create empty OSM data with required columns
    empty_osm_gdf = gpd.GeoDataFrame(
        {
            'highway': [],
            'building': [],
            'geometry': []
        },
        crs="EPSG:4326"
    )
    
    protoblocks_gdf = generate_protoblocks(
        input_polygon_gdf=test_polygon_gdf,
        osm_gdf=empty_osm_gdf
    )
    
    # Should return empty GeoDataFrame for empty OSM input
    assert isinstance(protoblocks_gdf, gpd.GeoDataFrame)
    assert protoblocks_gdf.crs is not None
