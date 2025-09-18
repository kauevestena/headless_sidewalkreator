"""Main entry point for command-line usage."""

from .main import *

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3 or len(sys.argv) > 4:
        print(
            "Usage: python -m headless_sidewalkreator <input_geojson_path> <output_directory_path> [--ignore-existing]"
        )
        sys.exit(1)

    input_geojson = sys.argv[1]
    output_dir = sys.argv[2]
    ignore_existing = len(sys.argv) > 3 and sys.argv[3] == "--ignore-existing"

    run_headless(input_geojson, output_dir, ignore_existing=ignore_existing)