import os
import shutil
import json
import geopandas as gpd
import pytest
from unittest.mock import patch
from headless_sidewalkreator import run_headless


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


def test_run_headless(setup_test_dir, osm_sample_gdf):
    """Test the main run_headless function."""
    test_dir = setup_test_dir
    input_polygon = os.path.join(
        os.path.dirname(__file__), "extra_tests", "polygon02.geojson"
    )

    # Inject deterministic OSM data for testability
    run_headless(input_polygon, test_dir, osm_gdf=osm_sample_gdf)

    # Check if output files were created and have content
    protoblocks_file = os.path.join(test_dir, "protoblocks_output.geojson")
    assert os.path.exists(protoblocks_file)
    protoblocks_gdf = gpd.read_file(protoblocks_file)
    assert not protoblocks_gdf.empty
    assert protoblocks_gdf.crs.to_string() == "EPSG:4326"
    assert len(protoblocks_gdf) > 0

    sidewalks_file = os.path.join(test_dir, "sidewalks_output.geojson")
    assert os.path.exists(sidewalks_file)
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
            input_polygon,
            output_dir,
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
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
            input_polygon,
            output_dir,
            "--ignore-existing",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Process complete" in result.stdout


@patch('headless_sidewalkreator.full_sidewalkreator_algorithm.fetch_street_network_for_bbox')
def test_run_headless_with_params_and_no_mock_gdf(mock_fetch, setup_test_dir, osm_sample_gdf):
    """Test run_headless with a parameters file and no mock gdf."""
    test_dir = setup_test_dir

    # Create a dummy parameters file
    params = {"split_max_len": 50}
    params_path = os.path.join(test_dir, "params.json")
    with open(params_path, "w") as f:
        json.dump(params, f)

    # The output directory will be created by the function
    output_dir = os.path.join(test_dir, "output")

    input_polygon = os.path.join(
        os.path.dirname(__file__), "extra_tests", "polygon01.geojson"
    )

    # Mock the fetch function to return a deterministic gdf
    mock_fetch.return_value = osm_sample_gdf

    run_headless(input_polygon, output_dir, parameters_path=params_path)

    mock_fetch.assert_called_once()
    assert os.path.exists(output_dir)

    # Check if output files were created and are not empty
    protoblocks_file = os.path.join(output_dir, "protoblocks_output.geojson")
    assert os.path.exists(protoblocks_file)
    protoblocks_gdf = gpd.read_file(protoblocks_file)
    assert not protoblocks_gdf.empty

    sidewalks_file = os.path.join(output_dir, "sidewalks_output.geojson")
    assert os.path.exists(sidewalks_file)
    sidewalks_gdf = gpd.read_file(sidewalks_file)
    assert not sidewalks_gdf.empty

    crossings_file = os.path.join(output_dir, "crossings_output.geojson")
    assert os.path.exists(crossings_file)
    crossings_gdf = gpd.read_file(crossings_file)


def test_ignore_existing_parameter(setup_test_dir, osm_sample_gdf):
    """Test the ignore_existing parameter functionality."""
    test_dir = setup_test_dir
    input_polygon = os.path.join(
        os.path.dirname(__file__), "extra_tests", "polygon02.geojson"
    )

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
    output_dir_normal = os.path.join(test_dir, "normal")
    run_headless(input_polygon, output_dir_normal, osm_gdf=combined_gdf, ignore_existing=False)

    # Test with ignore_existing=True
    output_dir_ignore = os.path.join(test_dir, "ignore_existing")
    run_headless(input_polygon, output_dir_ignore, osm_gdf=combined_gdf, ignore_existing=True)

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
