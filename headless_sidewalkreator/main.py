"""Main API for headless_sidewalkreator.

This module exposes the run_headless function used by the tests and CLI.
"""

from .full_sidewalkreator_algorithm import full_sidewalkreator_algorithm


def run_headless(*args, **kwargs):
    """Alias for the full_sidewalkreator_algorithm function."""
    return full_sidewalkreator_algorithm(*args, **kwargs)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print(
            "Usage: python -m headless_sidewalkreator <input_geojson_path> <output_directory_path>"
        )
        sys.exit(1)

    input_geojson = sys.argv[1]
    output_dir = sys.argv[2]

    run_headless(input_geojson, output_dir)
