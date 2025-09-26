"""Main API for headless_sidewalkreator.

This module exposes the run_headless function used by the tests and CLI.
"""

from .full_sidewalkreator_algorithm import full_sidewalkreator_algorithm


def run_headless(*args, **kwargs):
    """Alias for the full_sidewalkreator_algorithm function."""
    return full_sidewalkreator_algorithm(*args, **kwargs)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate sidewalks from OpenStreetMap data. \n\n"
        "Usage examples: \n"
        "python -m headless_sidewalkreator --place-name 'Amherst, MA' --output-dir ./output \n"
        "python -m headless_sidewalkreator --input-file path/to/area.geojson --output-dir ./output \n"
        "python -m headless_sidewalkreator --bbox -71.5 42.3 -71.4 42.4 --output-dir ./output",
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

    # Call the main function with parsed arguments
    run_headless(
        input_polygon_path=args.input_polygon_path,
        output_directory=args.output_directory,
        place_name=args.place_name,
        bbox=bbox,
        parameters_path=args.parameters_path,
        ignore_existing=args.ignore_existing,
    )
