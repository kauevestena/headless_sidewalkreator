"""Tests for the new GeoDataFrame-based API (generate_sidewalks_gdf)."""

import geopandas as gpd
import pytest
from unittest.mock import patch
from shapely.geometry import Polygon
from headless_sidewalkreator import generate_sidewalks_gdf
from headless_sidewalkreator import parameters as params


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
    expected_keys = ['sidewalks', 'crossings', 'kerbs', 'protoblocks', 'intersection_points', 'pois', 'input_area', 'parameters']
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


@pytest.mark.skip(reason="This test requires live OSM data and can be slow. Enable manually for integration testing.")
def test_generate_sidewalks_gdf_with_parameters():
    """Test generate_sidewalks_gdf with custom parameters and real data."""
    # Use the bbox provided by the user to avoid coordinate confusion
    bbox = {
        "min_lon": -49.289753,
        "min_lat": -25.466447,
        "max_lon": -49.284410,
        "max_lat": -25.462165
    }

    polygon = Polygon([
        (bbox["min_lon"], bbox["min_lat"]),
        (bbox["min_lon"], bbox["max_lat"]),
        (bbox["max_lon"], bbox["max_lat"]),
        (bbox["max_lon"], bbox["min_lat"]),
        (bbox["min_lon"], bbox["min_lat"])
    ])
    input_polygon_gdf = gpd.GeoDataFrame(geometry=[polygon], crs="EPSG:4326")
    
    custom_params = {
        "timeout": 60,  # Reasonable timeout for the smaller area
        "buffer_dist": 1.5,
        "split_max_len": 10.0,
        "min_d_to_building": 0.5,
        "dead_end_removal_iterations": 1,  # Reduce iterations to prevent infinite loops
    }
    
    result = generate_sidewalks_gdf(
        input_polygon_gdf=input_polygon_gdf,
        parameters=custom_params,
        ignore_existing=True
    )
    
    assert isinstance(result, dict)
    assert 'sidewalks' in result


def test_generate_sidewalks_gdf_with_parameters_mock_osm():
    """Test generate_sidewalks_gdf with custom parameters using mock OSM data."""
    # This test uses the same parameters as the problematic test but with controlled data
    polygon = Polygon([(-1, -1), (-1, 2), (2, 2), (2, -1), (-1, -1)])
    input_polygon_gdf = gpd.GeoDataFrame(geometry=[polygon], crs="EPSG:4326")
    
    # Create more realistic test OSM data to catch parameter-related issues
    from shapely.geometry import LineString, Point
    
    # Create a simple street network
    line1 = LineString([(0, 0), (1, 0)])
    line2 = LineString([(1, 0), (1, 1)])
    line3 = LineString([(1, 1), (0, 1)])
    line4 = LineString([(0, 1), (0, 0)])
    
    # Create some building points
    building1 = Point(0.5, 0.5)
    
    mock_osm_gdf = gpd.GeoDataFrame({
        'geometry': [line1, line2, line3, line4, building1],
        'highway': ['primary', 'primary', 'primary', 'primary', None],
        'building': [None, None, None, None, 'yes'],
        'amenity': [None, None, None, None, None],
        'shop': [None, None, None, None, None]
    }, crs="EPSG:4326")
    
    custom_params = {
        "timeout": 60,
        "buffer_dist": 1.5,
        "split_max_len": 10.0,
        "min_d_to_building": 0.5,
        "dead_end_removal_iterations": 2,
    }
    
    result = generate_sidewalks_gdf(
        input_polygon_gdf=input_polygon_gdf,
        osm_gdf=mock_osm_gdf,
        parameters=custom_params,
        ignore_existing=True
    )
    
    assert isinstance(result, dict)
    assert 'sidewalks' in result
    assert 'parameters' in result
    
    # Verify that our custom parameters were used
    assert result['parameters']['buffer_dist'] == 1.5
    assert result['parameters']['split_max_len'] == 10.0
    assert result['parameters']['dead_end_removal_iterations'] == 2


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
    
    with pytest.raises(ValueError, match="NaN or None values are not allowed."):
        generate_sidewalks_gdf(
            input_polygon_gdf=input_polygon_gdf,
            osm_gdf=empty_osm_gdf,
            parameters=None,
            ignore_existing=False
        )


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
    param_keys = [
        'timeout', 'default_widths', 'fallback_default_width',
        'default_curve_radius', 'buffer_dist', 'split_max_len',
        'split_num_segments', 'min_d_to_building', 'perc_draw_kerbs',
        'perc_tol_crossings', 'increment_inward', 'max_crossings_iterations',
        'cutoff_percent_protoblock', 'min_stretch_size', 'abs_max_crossing_len',
        'dead_end_removal_iterations'
    ]
    for key in param_keys:
        assert key in result['parameters'], f"Parameter key '{key}' missing"


@pytest.mark.skip(reason="This test requires a live API call to OSM and is slow. Enable for integration testing.")
def test_generate_sidewalks_gdf_from_place_name():
    """Test using a place_name to define the area of interest."""

    # Using a small, well-defined place to limit query size
    place_name = "Amherst, Massachusetts, USA"

    result = generate_sidewalks_gdf(
        place_name=place_name,
        ignore_existing=True  # Ignore existing sidewalks for a more predictable test
    )

    # Check that result is a dictionary
    assert isinstance(result, dict)

    # Check that all expected keys are present
    expected_keys = ['sidewalks', 'crossings', 'kerbs', 'protoblocks', 'intersection_points', 'pois', 'input_area', 'parameters']
    for key in expected_keys:
        assert key in result, f"Key '{key}' missing from result"

    # Check that some sidewalks were generated (this is a reasonable expectation for a town)
    assert not result['sidewalks'].empty, "Sidewalks GeoDataFrame should not be empty for a real place"

    # Check that the CRS is a projected CRS, indicating successful reprojection
    assert result['sidewalks'].crs.is_projected

def test_generate_sidewalks_gdf_input_validation():
    """Test input validation for generate_sidewalks_gdf."""

    polygon = Polygon([(-1, -1), (-1, 2), (2, 2), (2, -1), (-1, -1)])
    input_polygon_gdf = gpd.GeoDataFrame(geometry=[polygon], crs="EPSG:4326")
    place_name = "Amherst, MA"
    bbox = (-1, -1, 2, 2)

    # Test providing multiple input sources
    with pytest.raises(ValueError, match="Provide exactly one of 'place_name', 'input_polygon_gdf', or 'bbox'."):
        generate_sidewalks_gdf(
            input_polygon_gdf=input_polygon_gdf,
            place_name=place_name
        )

    with pytest.raises(ValueError, match="Provide exactly one of 'place_name', 'input_polygon_gdf', or 'bbox'."):
        generate_sidewalks_gdf(
            input_polygon_gdf=input_polygon_gdf,
            bbox=bbox
        )

    with pytest.raises(ValueError, match="Provide exactly one of 'place_name', 'input_polygon_gdf', or 'bbox'."):
        generate_sidewalks_gdf(
            place_name=place_name,
            bbox=bbox
        )

    with pytest.raises(ValueError, match="Provide exactly one of 'place_name', 'input_polygon_gdf', or 'bbox'."):
        generate_sidewalks_gdf(
            input_polygon_gdf=input_polygon_gdf,
            place_name=place_name,
            bbox=bbox
        )

    # Test providing no input source
    with pytest.raises(ValueError, match="Provide exactly one of 'place_name', 'input_polygon_gdf', or 'bbox'."):
        generate_sidewalks_gdf()


@patch('headless_sidewalkreator.full_sidewalkreator_algorithm.fetch_street_network_for_bbox')
def test_generate_sidewalks_gdf_with_bbox(mock_fetch, osm_sample_gdf):
    """Test generate_sidewalks_gdf with bbox input."""
    # Mock the OSM data fetch
    mock_fetch.return_value = osm_sample_gdf
    
    # Define a simple bounding box
    bbox = (-1, -1, 2, 2)
    
    # Call the function with bbox
    result = generate_sidewalks_gdf(
        bbox=bbox,
        osm_gdf=osm_sample_gdf,
        parameters={"buffer_dist": 1.0}
    )
    
    # Verify the result structure
    assert isinstance(result, dict)
    expected_keys = {'sidewalks', 'crossings', 'kerbs', 'protoblocks', 'intersection_points', 'pois', 'input_area', 'parameters'}
    assert set(result.keys()) == expected_keys
    
    # Verify that bbox was converted to GeoDataFrame internally by checking we got results
    assert isinstance(result['sidewalks'], gpd.GeoDataFrame)
    assert isinstance(result['parameters'], dict)
    assert result['parameters']['buffer_dist'] == 1.0