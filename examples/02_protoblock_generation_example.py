#!/home/kaue/headless_sidewalkreator/.venv/bin/python
"""
Protoblock Generation Example

This example demonstrates how to use the standalone protoblock generation
functionality. Protoblocks are the enclosed polygon areas formed by the
road network - essentially "city blocks" or "parcels" that are bounded by streets.

Protoblocks are useful for:
- Urban analysis and planning
- Understanding block-level structure
- Generating other geographic features based on city blocks
- Input to other spatial algorithms

This example uses three different input methods to show the flexibility
of the API:
1. Input polygon file (GeoJSON)
2. Place name (geocoded automatically)
3. Bounding box (coordinate rectangle)

Output files are saved to: examples/outputs/protoblocks/
"""

import os
import sys
from pathlib import Path
import geopandas as gpd

# Add the parent directory to the path to import the library
sys.path.insert(0, str(Path(__file__).parent.parent))

from headless_sidewalkreator import generate_protoblocks


def example_1_from_polygon_file():
    """Example 1: Generate protoblocks from a polygon file."""

    print("\n" + "=" * 70)
    print("Example 1: Generate Protoblocks from Polygon File")
    print("=" * 70)

    # Define paths
    project_root = Path(__file__).parent.parent
    # Use the EPSG:4326 version for better compatibility with OSM queries
    input_polygon_path = (
        project_root / "data_assets" / "test_data" / "polygon_4326.geojson"
    )
    output_dir = Path(__file__).parent / "outputs" / "protoblocks" / "example_1_polygon"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nInput: {input_polygon_path}")
    print(f"Output: {output_dir}")
    print("Note: Using carefully selected test area in Curitiba, Brazil")

    # Load the input polygon
    print("\n[1/3] Loading input polygon...")
    input_polygon_gdf = gpd.read_file(input_polygon_path)
    print(f"      Loaded polygon with CRS: {input_polygon_gdf.crs}")

    # Generate protoblocks
    print("\n[2/3] Generating protoblocks...")
    print("      (Downloading OSM data and processing...)")

    protoblocks_gdf = generate_protoblocks(
        input_polygon_gdf=input_polygon_gdf,
        parameters={
            "timeout": 180,  # Increased timeout for OSM download (3 minutes)
        },
    )

    print(f"\n      ✓ Generated {len(protoblocks_gdf)} protoblocks")

    # Save results
    print("\n[3/3] Saving results...")
    output_path = output_dir / "protoblocks.geojson"
    protoblocks_gdf.to_crs("EPSG:4326").to_file(output_path, driver="GeoJSON")
    print(f"      ✓ Saved to: {output_path}")

    # Save some statistics
    stats_path = output_dir / "statistics.txt"
    with open(stats_path, "w") as f:
        f.write(f"Protoblock Generation Statistics\n")
        f.write(f"=" * 50 + "\n\n")
        f.write(f"Total protoblocks: {len(protoblocks_gdf)}\n")
        f.write(f"CRS: {protoblocks_gdf.crs}\n")
        if not protoblocks_gdf.empty:
            areas = protoblocks_gdf.geometry.area
            f.write(f"\nArea Statistics (square meters):\n")
            f.write(f"  - Total area: {areas.sum():.2f}\n")
            f.write(f"  - Mean area: {areas.mean():.2f}\n")
            f.write(f"  - Median area: {areas.median():.2f}\n")
            f.write(f"  - Min area: {areas.min():.2f}\n")
            f.write(f"  - Max area: {areas.max():.2f}\n")

    print(f"      ✓ Saved statistics to: {stats_path}")
    print("\n" + "-" * 70)

    return protoblocks_gdf


def example_2_from_place_name():
    """Example 2: Generate protoblocks from a place name (geocoded)."""

    print("\n" + "=" * 70)
    print("Example 2: Generate Protoblocks from Place Name")
    print("=" * 70)

    # Define output path
    output_dir = (
        Path(__file__).parent / "outputs" / "protoblocks" / "example_2_place_name"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    # Use a small area for faster processing
    place_name = "MIT, Cambridge, MA, USA"

    print(f"\nPlace name: {place_name}")
    print(f"Output: {output_dir}")

    # Generate protoblocks
    print("\n[1/2] Geocoding place name and generating protoblocks...")
    print("      (This will download the boundary and OSM data...)")

    try:
        protoblocks_gdf = generate_protoblocks(
            place_name=place_name,
            parameters={
                "timeout": 180,  # Increased timeout for OSM download
            },
        )

        print(f"\n      ✓ Generated {len(protoblocks_gdf)} protoblocks")

        # Save results
        print("\n[2/2] Saving results...")
        output_path = output_dir / "protoblocks.geojson"
        protoblocks_gdf.to_crs("EPSG:4326").to_file(output_path, driver="GeoJSON")
        print(f"      ✓ Saved to: {output_path}")

        print("\n" + "-" * 70)
        return protoblocks_gdf

    except Exception as e:
        print(f"\n      ✗ Error: {e}")
        print("      (This example requires internet access and may fail if the place")
        print("       cannot be geocoded or if the area is too large)")
        print("\n" + "-" * 70)
        return None


def example_3_from_bounding_box():
    """Example 3: Generate protoblocks from a bounding box."""

    print("\n" + "=" * 70)
    print("Example 3: Generate Protoblocks from Bounding Box")
    print("=" * 70)

    # Define output path
    output_dir = Path(__file__).parent / "outputs" / "protoblocks" / "example_3_bbox"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Define a small bounding box (format: minx, miny, maxx, maxy)
    # This example uses a small area in Cambridge, MA
    bbox = (-71.095, 42.360, -71.090, 42.365)

    print(f"\nBounding box: {bbox}")
    print(f"  (minx={bbox[0]}, miny={bbox[1]}, maxx={bbox[2]}, maxy={bbox[3]})")
    print(f"Output: {output_dir}")

    # Generate protoblocks
    print("\n[1/2] Generating protoblocks from bounding box...")
    print("      (Downloading OSM data...)")

    try:
        protoblocks_gdf = generate_protoblocks(
            bbox=bbox,
            parameters={
                "timeout": 180,  # Increased timeout for OSM download
            },
        )

        print(f"\n      ✓ Generated {len(protoblocks_gdf)} protoblocks")

        # Save results
        print("\n[2/2] Saving results...")
        output_path = output_dir / "protoblocks.geojson"
        protoblocks_gdf.to_crs("EPSG:4326").to_file(output_path, driver="GeoJSON")
        print(f"      ✓ Saved to: {output_path}")

        print("\n" + "-" * 70)
        return protoblocks_gdf

    except Exception as e:
        print(f"\n      ✗ Error: {e}")
        print("      (This example requires internet access)")
        print("\n" + "-" * 70)
        return None


def main():
    """Run all protoblock generation examples."""

    print("\n")
    print("*" * 70)
    print("Protoblock Generation Examples")
    print("*" * 70)
    print("\nThis script demonstrates three ways to generate protoblocks:")
    print("  1. From a polygon file (GeoJSON)")
    print("  2. From a place name (geocoded automatically)")
    print("  3. From a bounding box (coordinate rectangle)")
    print()

    # Run example 1 (always works - uses local file)
    result1 = example_1_from_polygon_file()

    # Run example 2 (requires internet)
    print("\nNote: Examples 2 and 3 require internet access to download OSM data.")
    user_input = input("\nRun examples 2 and 3? (y/n): ").strip().lower()

    if user_input == "y":
        result2 = example_2_from_place_name()
        result3 = example_3_from_bounding_box()
    else:
        print("\nSkipping examples 2 and 3.")

    # Print final summary
    print("\n" + "=" * 70)
    print("All Examples Complete!")
    print("=" * 70)
    print("\nOutput files are saved in:")
    print("  examples/outputs/protoblocks/")
    print("\nYou can view these files in QGIS or any GIS software to see")
    print("the generated city blocks/protoblocks.")
    print()


if __name__ == "__main__":
    main()
