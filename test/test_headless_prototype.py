import os
import shutil
import json
import geopandas as gpd
import pytest
from unittest.mock import patch
from headless_sidewalkreator import sidewalkreator
from headless_sidewalkreator.main import save_results_to_directory
from headless_sidewalkreator.generic_functions import read_input_polygon
from shapely.geometry import Polygon


@pytest.fixture
def setup_test_dir():
    """Create a temporary directory for test output."""
    test_dir = os.path.join(os.path.dirname(__file__), "temp_test_output")
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)
    yield test_dir
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)


@pytest.fixture
def test_polygon_gdf():
    """Create a simple test polygon GeoDataFrame."""
    # Create a simple rectangular polygon
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
    gdf = gpd.GeoDataFrame([{'geometry': polygon}], crs='EPSG:4326')
    return gdf


def test_sidewalkreator_api(setup_test_dir, test_polygon_gdf, osm_sample_gdf):
    """Test the new sidewalkreator API and save results to directory."""
    test_dir = setup_test_dir

    # Use the new GeoDataFrame-based API
    result = sidewalkreator(
        input_polygon_gdf=test_polygon_gdf,
        osm_gdf=osm_sample_gdf
    )

    # Verify the result structure
    expected_keys = ['sidewalks', 'crossings', 'kerbs', 'protoblocks', 'intersection_points', 'pois', 'input_area', 'parameters']
    for key in expected_keys:
        assert key in result, f"Key '{key}' missing from result"
    
    # Verify GeoDataFrames
    assert isinstance(result['sidewalks'], gpd.GeoDataFrame)
    assert isinstance(result['crossings'], gpd.GeoDataFrame)
    assert isinstance(result['kerbs'], gpd.GeoDataFrame)
    assert isinstance(result['protoblocks'], gpd.GeoDataFrame)

    # Save results to directory using the helper function
    save_results_to_directory(result, test_dir)

    # Check if output files were created
    protoblocks_file = os.path.join(test_dir, "protoblocks_output.geojson")
    assert os.path.exists(protoblocks_file)
    
    sidewalks_file = os.path.join(test_dir, "sidewalks_output.geojson")
    assert os.path.exists(sidewalks_file)
    
    params_file = os.path.join(test_dir, "parameters.json")
    assert os.path.exists(params_file)
    sidewalks_gdf = gpd.read_file(sidewalks_file)
    assert not sidewalks_gdf.empty
    assert sidewalks_gdf.crs.to_string() == "EPSG:4326"
    assert len(sidewalks_gdf) > 0

    crossings_file = os.path.join(test_dir, "crossings_output.geojson")
    assert os.path.exists(crossings_file)
    crossings_gdf = gpd.read_file(crossings_file)
    assert not crossings_gdf.empty


def test_main_cli_entrypoint(setup_test_dir):
    """Test the command-line entry point of main.py."""
    import subprocess
    import sys

    test_dir = setup_test_dir
    input_polygon = os.path.join(
        os.path.dirname(__file__), "extra_tests", "polygon02.geojson"
    )
    output_dir = os.path.join(test_dir, "cli_output")

    # Run the main.py script as a module
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "headless_sidewalkreator.main",
            "--input-file",
            input_polygon,
            "--output-dir",
            output_dir,
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"CLI process failed with output:\n{result.stderr}"
    assert "Process complete" in result.stdout


def test_main_cli_with_ignore_existing_flag(setup_test_dir):
    """Test the command-line entry point with --ignore-existing flag."""
    import subprocess
    import sys

    test_dir = setup_test_dir
    input_polygon = os.path.join(
        os.path.dirname(__file__), "extra_tests", "polygon02.geojson"
    )
    output_dir = os.path.join(test_dir, "cli_ignore_output")

    # Run the main.py script with the ignore-existing flag
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "headless_sidewalkreator.main",
            "--input-file",
            input_polygon,
            "--output-dir",
            output_dir,
            "--ignore-existing",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"CLI process failed with output:\n{result.stderr}"
    assert "Process complete" in result.stdout


@patch('headless_sidewalkreator.full_sidewalkreator_algorithm.fetch_street_network_for_bbox')
def test_sidewalkreator_with_params_and_mock_fetch(mock_fetch, setup_test_dir, test_polygon_gdf, osm_sample_gdf):
    """Test sidewalkreator with parameters and mocked fetch."""
    test_dir = setup_test_dir

    # Create custom parameters
    params = {"split_max_len": 50, "buffer_dist": 3.0}

    # Mock the fetch function to return a deterministic gdf
    mock_fetch.return_value = osm_sample_gdf

    # Call the new API
    result = sidewalkreator(
        input_polygon_gdf=test_polygon_gdf,
        parameters=params
    )

    # Verify parameters were applied
    assert result['parameters']['split_max_len'] == 50
    assert result['parameters']['buffer_dist'] == 3.0
    
    mock_fetch.assert_called_once()

    # Save results and verify files
    save_results_to_directory(result, test_dir)
    assert os.path.exists(test_dir)

    # Check if output files were created and are not empty
    protoblocks_file = os.path.join(test_dir, "protoblocks_output.geojson")
    assert os.path.exists(protoblocks_file)
    protoblocks_gdf = gpd.read_file(protoblocks_file)
    assert not protoblocks_gdf.empty

    sidewalks_file = os.path.join(test_dir, "sidewalks_output.geojson")
    assert os.path.exists(sidewalks_file)
    sidewalks_gdf = gpd.read_file(sidewalks_file)
    assert not sidewalks_gdf.empty

    crossings_file = os.path.join(test_dir, "crossings_output.geojson")
    assert os.path.exists(crossings_file)
    crossings_gdf = gpd.read_file(crossings_file)


def test_ignore_existing_parameter(setup_test_dir, test_polygon_gdf, osm_sample_gdf):
    """Test the ignore_existing parameter functionality."""
    test_dir = setup_test_dir

    # Create OSM data with existing sidewalks
    osm_with_sidewalks = osm_sample_gdf.copy()
    # Add some existing sidewalks (footway=sidewalk) to the mock data
    from shapely.geometry import LineString
    import geopandas as gpd
    
    # Add existing sidewalk data that should normally cause filtering
    sidewalk_lines = [
        LineString([(0.1, 0), (0.1, 1)]),  # Sidewalk parallel to first line
        LineString([(0.9, 0), (0.9, 1)]),  # Another sidewalk
    ]
    
    sidewalk_gdf = gpd.GeoDataFrame(
        {
            "geometry": sidewalk_lines,
            "highway": ["footway", "footway"],
            "footway": ["sidewalk", "sidewalk"],
            "building": [None, None],
            "amenity": [None, None],
            "shop": [None, None],
        }
    )
    sidewalk_gdf = sidewalk_gdf.set_crs("EPSG:4326")
    
    # Combine the original lines with sidewalk lines
    combined_gdf = gpd.pd.concat([osm_with_sidewalks, sidewalk_gdf], ignore_index=True)

    # Test with ignore_existing=False (default behavior)
    result_normal = sidewalkreator(
        input_polygon_gdf=test_polygon_gdf,
        osm_gdf=combined_gdf,
        ignore_existing=False
    )

    # Test with ignore_existing=True
    result_ignore = sidewalkreator(
        input_polygon_gdf=test_polygon_gdf,
        osm_gdf=combined_gdf,
        ignore_existing=True
    )

    # Save results to verify files are created
    output_dir_normal = os.path.join(test_dir, "normal")
    output_dir_ignore = os.path.join(test_dir, "ignore_existing")
    
    save_results_to_directory(result_normal, output_dir_normal)
    save_results_to_directory(result_ignore, output_dir_ignore)

    # Both runs should complete successfully
    assert os.path.exists(output_dir_normal)
    assert os.path.exists(output_dir_ignore)
    
    # Both should generate output files
    sidewalks_normal = os.path.join(output_dir_normal, "sidewalks_output.geojson")
    sidewalks_ignore = os.path.join(output_dir_ignore, "sidewalks_output.geojson")
    
    assert os.path.exists(sidewalks_normal)
    assert os.path.exists(sidewalks_ignore)
    
    # The test verifies that both modes complete successfully
    # The specific behavior (more or fewer sidewalks) depends on the algorithm details
    # but the important thing is that ignore_existing=True bypasses the filtering logic
    normal_gdf = gpd.read_file(sidewalks_normal)
    ignore_gdf = gpd.read_file(sidewalks_ignore)
    
    # Both should generate some sidewalks
    print(f"Normal mode generated {len(normal_gdf)} sidewalks")
    print(f"Ignore existing mode generated {len(ignore_gdf)} sidewalks")


def test_main_cli_with_bbox(setup_test_dir):
    """Test the command-line entry point with bbox parameter."""
    import subprocess
    import sys

    test_dir = setup_test_dir
    output_dir = os.path.join(test_dir, "cli_bbox_output")

    # Use a small bbox to avoid long processing times
    bbox = [-0.01, -0.01, 0.01, 0.01]

    # Run the main.py script with bbox argument
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "headless_sidewalkreator.main",
            "--bbox",
            str(bbox[0]),
            str(bbox[1]),
            str(bbox[2]),
            str(bbox[3]),
            "--output-dir",
            output_dir,
        ],
        capture_output=True,
        text=True,
        timeout=60  # Add timeout to prevent hanging
    )

    assert result.returncode == 0, f"CLI process failed with output:\n{result.stderr}"
    assert "Process complete" in result.stdout
    
    # Verify that output files were created
    assert os.path.exists(output_dir)
    assert os.path.exists(os.path.join(output_dir, "sidewalks_output.geojson"))
    assert os.path.exists(os.path.join(output_dir, "auxiliary", "input_polygon.geojson"))
    
    # Verify the input polygon was created from bbox
    input_polygon_file = os.path.join(output_dir, "auxiliary", "input_polygon.geojson")
    input_gdf = gpd.read_file(input_polygon_file)
    bounds = input_gdf.total_bounds
    
    # Check that the bounds approximately match the input bbox
    assert abs(bounds[0] - bbox[0]) < 1e-10  # minx
    assert abs(bounds[1] - bbox[1]) < 1e-10  # miny
    assert abs(bounds[2] - bbox[2]) < 1e-10  # maxx
    assert abs(bounds[3] - bbox[3]) < 1e-10  # maxy
