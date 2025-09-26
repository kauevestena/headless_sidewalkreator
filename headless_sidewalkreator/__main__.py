"""Main entry point for command-line usage."""

import sys
from .full_sidewalkreator_algorithm import full_sidewalkreator_algorithm


def main():
    """Command-line entry point."""
    if len(sys.argv) < 3 or len(sys.argv) > 4:
        print(
            "Usage: python -m headless_sidewalkreator <input_geojson_path> <output_directory_path> [--ignore-existing]"
        )
        sys.exit(1)

    input_geojson = sys.argv[1]
    output_dir = sys.argv[2]
    ignore_existing = len(sys.argv) > 3 and sys.argv[3] == "--ignore-existing"

    full_sidewalkreator_algorithm(
        input_geojson, output_dir, ignore_existing=ignore_existing
    )


if __name__ == "__main__":
    main()