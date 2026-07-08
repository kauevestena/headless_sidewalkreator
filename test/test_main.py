import os
import json
import pytest
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon
from headless_sidewalkreator.main import save_results_to_directory

def test_save_results_to_directory_all_populated(tmp_path):
    """Test saving results when all GeoDataFrames are populated."""
    output_dir = tmp_path / "output"

    # Create mock data
    poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
    line = LineString([(0, 0), (1, 1)])
    point = Point(0.5, 0.5)

    result = {
        "input_area": gpd.GeoDataFrame(geometry=[poly], crs="EPSG:4326"),
        "intersection_points": gpd.GeoDataFrame(geometry=[point], crs="EPSG:4326"),
        "pois": gpd.GeoDataFrame(geometry=[point], crs="EPSG:4326"),
        "protoblocks": gpd.GeoDataFrame(geometry=[poly], crs="EPSG:4326"),
        "sidewalks": gpd.GeoDataFrame(geometry=[line], crs="EPSG:4326"),
        "crossings": gpd.GeoDataFrame(geometry=[line], crs="EPSG:4326"),
        "kerbs": gpd.GeoDataFrame(geometry=[point], crs="EPSG:4326"),
        "parameters": {"test_param": "test_value"}
    }

    save_results_to_directory(result, str(output_dir))

    # Check main output files
    assert (output_dir / "protoblocks_output.geojson").exists()
    assert (output_dir / "sidewalks_output.geojson").exists()
    assert (output_dir / "crossings_output.geojson").exists()
    assert (output_dir / "kerbs_output.geojson").exists()
    assert (output_dir / "sidewalkreator_output.geojson").exists()
    assert (output_dir / "changeset_comment.txt").exists()
    assert (output_dir / "parameters.json").exists()

    # Check auxiliary files
    aux_dir = output_dir / "auxiliary"
    assert aux_dir.exists()
    assert (aux_dir / "input_polygon.geojson").exists()
    assert (aux_dir / "intersection_points.geojson").exists()
    assert (aux_dir / "pois.geojson").exists()

    # Verify parameters content
    with open(output_dir / "parameters.json", "r") as f:
        params = json.load(f)
        assert params == {"test_param": "test_value"}

def test_save_results_to_directory_empty_optional(tmp_path):
    """Test saving results when some GeoDataFrames are empty (optional ones should be skipped)."""
    output_dir = tmp_path / "output_empty"

    # Create mock data
    poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
    line = LineString([(0, 0), (1, 1)])

    # Empty GDFs
    empty_gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    result = {
        "input_area": gpd.GeoDataFrame(geometry=[poly], crs="EPSG:4326"),
        "intersection_points": empty_gdf,
        "pois": empty_gdf,
        "protoblocks": empty_gdf,
        "sidewalks": gpd.GeoDataFrame(geometry=[line], crs="EPSG:4326"),
        "crossings": empty_gdf,
        "kerbs": empty_gdf,
        "parameters": {}
    }

    save_results_to_directory(result, str(output_dir))

    # Should exist (include_empty=True or default)
    assert (output_dir / "sidewalks_output.geojson").exists()
    assert (output_dir / "crossings_output.geojson").exists()
    assert (output_dir / "auxiliary" / "input_polygon.geojson").exists()
    assert (output_dir / "sidewalkreator_output.geojson").exists()

    # Should NOT exist (include_empty=False)
    assert not (output_dir / "protoblocks_output.geojson").exists()
    assert not (output_dir / "kerbs_output.geojson").exists()
    assert not (output_dir / "auxiliary" / "intersection_points.geojson").exists()
    assert not (output_dir / "auxiliary" / "pois.geojson").exists()

def test_save_results_to_directory_reprojection(tmp_path):
    """Test that save_results_to_directory handles reprojection correctly."""
    output_dir = tmp_path / "output_reproject"

    # Create data in EPSG:3857
    poly = Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000), (0, 0)])

    result = {
        "input_area": gpd.GeoDataFrame(geometry=[poly], crs="EPSG:3857"),
        "intersection_points": gpd.GeoDataFrame(geometry=[], crs="EPSG:3857"),
        "pois": gpd.GeoDataFrame(geometry=[], crs="EPSG:3857"),
        "protoblocks": gpd.GeoDataFrame(geometry=[], crs="EPSG:3857"),
        "sidewalks": gpd.GeoDataFrame(geometry=[], crs="EPSG:3857"),
        "crossings": gpd.GeoDataFrame(geometry=[], crs="EPSG:3857"),
        "kerbs": gpd.GeoDataFrame(geometry=[], crs="EPSG:3857"),
        "parameters": {}
    }

    save_results_to_directory(result, str(output_dir))

    # Read back one file and check CRS
    input_poly_path = output_dir / "auxiliary" / "input_polygon.geojson"
    read_gdf = gpd.read_file(input_poly_path)
    assert read_gdf.crs.to_epsg() == 4326

def test_save_results_to_directory_all_empty(tmp_path):
    """Test saving results when all GeoDataFrames are empty."""
    output_dir = tmp_path / "output_all_empty"

    empty_gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    result = {
        "input_area": empty_gdf,
        "intersection_points": empty_gdf,
        "pois": empty_gdf,
        "protoblocks": empty_gdf,
        "sidewalks": empty_gdf,
        "crossings": empty_gdf,
        "kerbs": empty_gdf,
        "parameters": {}
    }

    save_results_to_directory(result, str(output_dir))

    # These should still exist as empty FeatureCollections
    assert (output_dir / "sidewalks_output.geojson").exists()
    assert (output_dir / "crossings_output.geojson").exists()
    assert (output_dir / "auxiliary" / "input_polygon.geojson").exists()
    assert (output_dir / "sidewalkreator_output.geojson").exists()
    assert (output_dir / "parameters.json").exists()

    # These should NOT exist
    assert not (output_dir / "protoblocks_output.geojson").exists()
    assert not (output_dir / "kerbs_output.geojson").exists()
    assert not (output_dir / "auxiliary" / "intersection_points.geojson").exists()
    assert not (output_dir / "auxiliary" / "pois.geojson").exists()
