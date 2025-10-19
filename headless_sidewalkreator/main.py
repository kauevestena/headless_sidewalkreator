"""Main CLI entry point for headless_sidewalkreator.

This module provides the command-line interface using the modern GeoDataFrame-based API.
"""

import json
import os
import geopandas as gpd

from .full_sidewalkreator_algorithm import sidewalkreator
from .generic_functions import read_input_polygon
from .logging_config import get_logger


logger = get_logger(__name__)


def save_results_to_directory(result, output_directory):
    """Save GeoDataFrame results to files for CLI compatibility.
    
    Args:
        result: Dictionary containing GeoDataFrames from sidewalkreator()
        output_directory: Directory where the output files will be saved
    """
    # Create output directory if it doesn't exist
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    # Extract results
    splitted_sidewalks_gdf = result['sidewalks']
    crossings_gdf = result['crossings']
    kerbs_gdf = result['kerbs']
    protoblocks_gdf = result['protoblocks']
    intersection_points_gdf = result['intersection_points']
    unified_pois_gdf = result['pois']
    run_params = result['parameters']
    actual_input_gdf = result['input_area']

    # Save auxiliary files
    auxiliary_output_directory = os.path.join(output_directory, "auxiliary")
    if not os.path.exists(auxiliary_output_directory):
        os.makedirs(auxiliary_output_directory)

    input_polygon_output_path = os.path.join(auxiliary_output_directory, "input_polygon.geojson")
    actual_input_gdf.to_crs("EPSG:4326").to_file(input_polygon_output_path, driver="GeoJSON")

    intersection_points_output_path = os.path.join(auxiliary_output_directory, "intersection_points.geojson")
    if not intersection_points_gdf.empty:
        intersection_points_gdf.to_crs("EPSG:4326").to_file(
            intersection_points_output_path, driver="GeoJSON"
        )

    # Save POI data
    pois_output_path = os.path.join(auxiliary_output_directory, "pois.geojson")
    if not unified_pois_gdf.empty:
        unified_pois_gdf.to_crs("EPSG:4326").to_file(pois_output_path, driver="GeoJSON")

    # Save main output files
    output_path = os.path.join(output_directory, "protoblocks_output.geojson")
    if not protoblocks_gdf.empty:
        protoblocks_gdf.to_crs("EPSG:4326").to_file(output_path, driver="GeoJSON")

    sidewalks_output_path = os.path.join(output_directory, "sidewalks_output.geojson")
    if not splitted_sidewalks_gdf.empty:
        splitted_sidewalks_gdf.to_crs("EPSG:4326").to_file(sidewalks_output_path, driver="GeoJSON")
    else:
        # Create empty file for consistency
        empty_geojson = {"type": "FeatureCollection", "features": []}
        with open(sidewalks_output_path, "w") as f:
            json.dump(empty_geojson, f)

    crossings_output_path = os.path.join(output_directory, "crossings_output.geojson")
    if not crossings_gdf.empty:
        crossings_gdf.to_crs("EPSG:4326").to_file(crossings_output_path, driver="GeoJSON")
    else:
        # Create empty file for consistency
        empty_geojson = {"type": "FeatureCollection", "features": []}
        with open(crossings_output_path, "w") as f:
            json.dump(empty_geojson, f)

    kerbs_output_path = os.path.join(output_directory, "kerbs_output.geojson")
    if not kerbs_gdf.empty:
        kerbs_gdf.to_crs("EPSG:4326").to_file(kerbs_output_path, driver="GeoJSON")

    # Create merged output file (following QGIS plugin behavior)
    create_merged_output(
        output_directory,
        splitted_sidewalks_gdf if not splitted_sidewalks_gdf.empty else None,
        crossings_gdf if not crossings_gdf.empty else None,
        kerbs_gdf if not kerbs_gdf.empty else None,
    )

    # Save parameters to a file
    params_output_path = os.path.join(output_directory, "parameters.json")
    with open(params_output_path, "w") as f:
        json.dump(run_params, f, indent=4)

    logger.info("Process complete. Output saved to %s", output_directory)


def create_merged_output(output_directory, sidewalks_gdf, crossings_gdf, kerbs_gdf):
    """Create a merged GeoJSON file for easy import into JOSM.

    This follows the QGIS plugin behavior of creating a single file with
    all features for easy uploading to OpenStreetMap.
    """
    merged_features = []

    # Add sidewalks as lines
    if sidewalks_gdf is not None and not sidewalks_gdf.empty:
        sidewalks_4326 = sidewalks_gdf.to_crs("EPSG:4326")
        for _, row in sidewalks_4326.iterrows():
            feature = {
                "type": "Feature",
                "properties": {"highway": "footway", "footway": "sidewalk"},
                "geometry": row.geometry.__geo_interface__
            }
            merged_features.append(feature)

    # Add crossings as lines
    if crossings_gdf is not None and not crossings_gdf.empty:
        crossings_4326 = crossings_gdf.to_crs("EPSG:4326")
        for _, row in crossings_4326.iterrows():
            feature = {
                "type": "Feature",
                "properties": {"highway": "footway", "footway": "crossing"},
                "geometry": row.geometry.__geo_interface__
            }
            merged_features.append(feature)

    # Add kerbs as points
    if kerbs_gdf is not None and not kerbs_gdf.empty:
        kerbs_4326 = kerbs_gdf.to_crs("EPSG:4326")
        for _, row in kerbs_4326.iterrows():
            feature = {
                "type": "Feature",
                "properties": {"barrier": "kerb"},
                "geometry": row.geometry.__geo_interface__
            }
            merged_features.append(feature)

    # Create merged GeoJSON
    merged_geojson = {
        "type": "FeatureCollection",
        "features": merged_features
    }

    # Save merged file
    merged_path = os.path.join(output_directory, "sidewalkreator_output.geojson")
    with open(merged_path, 'w') as f:
        json.dump(merged_geojson, f, indent=2)

    # Create changeset comment file
    comment_path = os.path.join(output_directory, "changeset_comment.txt")
    with open(comment_path, 'w') as f:
        f.write("Generated sidewalks, crossings, and kerbs using OSM SidewalKreator\n")
        f.write(f"Added {len([f for f in merged_features if f['properties'].get('footway') == 'sidewalk'])} sidewalk segments\n")
        f.write(f"Added {len([f for f in merged_features if f['properties'].get('footway') == 'crossing'])} crossings\n")


def main():
    """Main CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate sidewalks from OpenStreetMap data. \n\n"
        "Usage examples: \n"
        "sidewalkreator --place-name 'Amherst, MA' --output-dir ./output \n"
        "sidewalkreator --input-file path/to/area.geojson --output-dir ./output \n"
        "sidewalkreator --bbox -71.5 42.3 -71.4 42.4 --output-dir ./output",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    # Input source group - either a file, a place name, or a bounding box
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input-file",
        dest="input_polygon_path",
        help="Path to the GeoJSON file containing the input polygon.",
    )
    input_group.add_argument(
        "--place-name",
        dest="place_name",
        help="Name of the place to geocode for the area of interest (e.g., 'Amherst, MA').",
    )
    input_group.add_argument(
        "--bbox",
        dest="bbox",
        nargs=4,
        type=float,
        metavar=('MINX', 'MINY', 'MAXX', 'MAXY'),
        help="Bounding box coordinates (minx miny maxx maxy) for rectangular area of interest.",
    )

    # Required output directory
    parser.add_argument(
        "--output-dir",
        dest="output_directory",
        required=True,
        help="Directory where the output files will be saved.",
    )

    # Optional parameters
    parser.add_argument(
        "--parameters",
        dest="parameters_path",
        help="Optional path to a JSON file with runtime parameters.",
    )
    parser.add_argument(
        "--ignore-existing",
        action="store_true",
        help="If set, ignores existing sidewalks and generates all possible sidewalks.",
    )

    args = parser.parse_args()

    # Convert bbox list to tuple if provided
    bbox = tuple(args.bbox) if args.bbox else None

    # Load parameters from file if provided
    parameters = {}
    if args.parameters_path and os.path.exists(args.parameters_path):
        with open(args.parameters_path, "r") as f:
            parameters = json.load(f)

    # Load input polygon if path is provided
    input_polygon_gdf = None
    if args.input_polygon_path:
        input_polygon_gdf = read_input_polygon(args.input_polygon_path)

    # Call the new GeoDataFrame-based API
    result = sidewalkreator(
        input_polygon_gdf=input_polygon_gdf,
        place_name=args.place_name,
        bbox=bbox,
        parameters=parameters,
        ignore_existing=args.ignore_existing,
    )

    # Save results to files for CLI compatibility
    save_results_to_directory(result, args.output_directory)


if __name__ == "__main__":
    main()
