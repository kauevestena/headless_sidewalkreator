"""Main CLI entry point for headless_sidewalkreator.

This module provides the command-line interface using the modern GeoDataFrame-based API.
"""

import json
import os
import geopandas as gpd

from .full_sidewalkreator_algorithm import sidewalkreator
from .generic_functions import (
    read_input_polygon,
    save_gdf_to_geojson,
    create_merged_output,
)
from .logging_config import get_logger


logger = get_logger(__name__)


def save_results_to_directory(result, output_directory):
    """Save GeoDataFrame results to files for CLI compatibility.

    Args:
        result: Dictionary containing GeoDataFrames from sidewalkreator()
        output_directory: Directory where the output files will be saved
    """
    os.makedirs(output_directory, exist_ok=True)
    aux_dir = os.path.join(output_directory, "auxiliary")

    # Save auxiliary files
    save_gdf_to_geojson(result["input_area"], os.path.join(aux_dir, "input_polygon.geojson"))
    save_gdf_to_geojson(result["intersection_points"], os.path.join(aux_dir, "intersection_points.geojson"), include_empty=False)
    save_gdf_to_geojson(result["pois"], os.path.join(aux_dir, "pois.geojson"), include_empty=False)

    # Save main output files
    save_gdf_to_geojson(result["protoblocks"], os.path.join(output_directory, "protoblocks_output.geojson"), include_empty=False)
    save_gdf_to_geojson(result["sidewalks"], os.path.join(output_directory, "sidewalks_output.geojson"))
    save_gdf_to_geojson(result["crossings"], os.path.join(output_directory, "crossings_output.geojson"))
    save_gdf_to_geojson(result["kerbs"], os.path.join(output_directory, "kerbs_output.geojson"), include_empty=False)

    # Create merged output file (following QGIS plugin behavior)
    create_merged_output(
        output_directory,
        result["sidewalks"],
        result["crossings"],
        result["kerbs"],
    )

    # Save parameters to a file
    params_output_path = os.path.join(output_directory, "parameters.json")
    with open(params_output_path, "w") as f:
        json.dump(result["parameters"], f, indent=4)

    logger.info("Process complete. Output saved to %s", output_directory)


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
