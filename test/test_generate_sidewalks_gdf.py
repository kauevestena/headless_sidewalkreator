"""Tests for the new GeoDataFrame-based API (generate_sidewalks_gdf)."""

import geopandas as gpd
import pytest
from shapely.geometry import Polygon
from headless_sidewalkreator import generate_sidewalks_gdf


def test_generate_sidewalks_gdf_basic(osm_sample_gdf):
    """Test basic functionality of generate_sidewalks_gdf."""
    # Create a simple input polygon
    polygon = Polygon([(-1, -1), (-1, 2), (2, 2), (2, -1), (-1, -1)])
    input_polygon_gdf = gpd.GeoDataFrame(geometry=[polygon], crs="EPSG:4326")
    
    # Call the new API
    result = generate_sidewalks_gdf(
        input_polygon_gdf=input_polygon_gdf,
        osm_gdf=osm_sample_gdf,
        parameters=None,
        ignore_existing=False
    )
    
    # Check that result is a dictionary
    assert isinstance(result, dict)
    
    # Check that all expected keys are present
    expected_keys = ['sidewalks', 'crossings', 'kerbs', 'protoblocks', 'intersection_points', 'parameters']
    for key in expected_keys:
        assert key in result, f"Key '{key}' missing from result"
    
    # Check that all outputs are GeoDataFrames (except parameters)
    for key in expected_keys[:-1]:  # exclude parameters
        assert isinstance(result[key], gpd.GeoDataFrame), f"{key} should be a GeoDataFrame"
    
    # Check that parameters is a dict
    assert isinstance(result['parameters'], dict)
    
    # Check that protoblocks is not empty (should have at least one from polygonization)
    assert not result['protoblocks'].empty, "Protoblocks should not be empty"
    
    # Check CRS consistency (all should be in the same projected CRS)
    for key in ['sidewalks', 'crossings', 'kerbs', 'protoblocks', 'intersection_points']:
        if not result[key].empty:
            assert result[key].crs is not None, f"{key} should have a CRS"


def test_generate_sidewalks_gdf_with_parameters(osm_sample_gdf):
    """Test generate_sidewalks_gdf with custom parameters."""
    polygon = Polygon([(-1, -1), (-1, 2), (2, 2), (2, -1), (-1, -1)])
    input_polygon_gdf = gpd.GeoDataFrame(geometry=[polygon], crs="EPSG:4326")
    
    custom_params = {
        "timeout": 30,
        "buffer_dist": 1.5,
        "split_max_len": 10.0
    }
    
    result = generate_sidewalks_gdf(
        input_polygon_gdf=input_polygon_gdf,
        osm_gdf=osm_sample_gdf,
        parameters=custom_params,
        ignore_existing=True
    )
    
    # Check that custom parameters were applied
    assert result['parameters']['timeout'] == 30
    assert result['parameters']['buffer_dist'] == 1.5
    assert result['parameters']['split_max_len'] == 10.0


def test_generate_sidewalks_gdf_empty_osm():
    """Test generate_sidewalks_gdf with empty OSM data."""
    polygon = Polygon([(-1, -1), (-1, 2), (2, 2), (2, -1), (-1, -1)])
    input_polygon_gdf = gpd.GeoDataFrame(geometry=[polygon], crs="EPSG:4326")
    
    # Create empty OSM GeoDataFrame with expected columns
    empty_osm_gdf = gpd.GeoDataFrame(columns=['geometry', 'highway', 'building', 'amenity', 'shop'])
    empty_osm_gdf = empty_osm_gdf.set_crs("EPSG:4326")
    
    result = generate_sidewalks_gdf(
        input_polygon_gdf=input_polygon_gdf,
        osm_gdf=empty_osm_gdf,
        parameters=None,
        ignore_existing=False
    )
    
    # Should return valid structure even with empty input
    assert isinstance(result, dict)
    assert 'sidewalks' in result
    assert isinstance(result['sidewalks'], gpd.GeoDataFrame)


def test_generate_sidewalks_gdf_validates_input_polygon():
    """Test that generate_sidewalks_gdf validates input polygon."""
    # Create invalid input (None polygon)
    input_polygon_gdf = gpd.GeoDataFrame(geometry=[None], crs="EPSG:4326")
    empty_osm_gdf = gpd.GeoDataFrame(columns=['geometry', 'highway', 'building', 'amenity', 'shop'])
    empty_osm_gdf = empty_osm_gdf.set_crs("EPSG:4326")
    
    # This should not crash but might return empty results
    result = generate_sidewalks_gdf(
        input_polygon_gdf=input_polygon_gdf,
        osm_gdf=empty_osm_gdf,
        parameters=None,
        ignore_existing=False
    )
    
    assert isinstance(result, dict)


def test_generate_sidewalks_gdf_return_structure():
    """Test that the return structure contains all expected components."""
    polygon = Polygon([(-1, -1), (-1, 2), (2, 2), (2, -1), (-1, -1)])
    input_polygon_gdf = gpd.GeoDataFrame(geometry=[polygon], crs="EPSG:4326")
    
    # Create minimal OSM data
    minimal_osm_gdf = gpd.GeoDataFrame({
        'geometry': [],
        'highway': [], 
        'building': [],
        'amenity': [],
        'shop': []
    })
    minimal_osm_gdf = minimal_osm_gdf.set_crs("EPSG:4326")
    
    result = generate_sidewalks_gdf(
        input_polygon_gdf=input_polygon_gdf,
        osm_gdf=minimal_osm_gdf
    )
    
    # Validate the structure of the result
    assert isinstance(result, dict)
    
    # Check types
    assert isinstance(result['sidewalks'], gpd.GeoDataFrame)
    assert isinstance(result['crossings'], gpd.GeoDataFrame)
    assert isinstance(result['kerbs'], gpd.GeoDataFrame)
    assert isinstance(result['protoblocks'], gpd.GeoDataFrame)
    assert isinstance(result['intersection_points'], gpd.GeoDataFrame)
    assert isinstance(result['parameters'], dict)
    
    # Check parameters contain expected keys
    param_keys = ['timeout', 'default_widths', 'fallback_default_width', 
                  'default_curve_radius', 'buffer_dist', 'split_max_len', 'split_num_segments']
    for key in param_keys:
        assert key in result['parameters'], f"Parameter key '{key}' missing"