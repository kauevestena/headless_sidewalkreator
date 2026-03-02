#!/home/kaue/headless_sidewalkreator/.venv/bin/python
"""
Full Pipeline Example - Generate Complete Sidewalk Network

This example demonstrates the full sidewalk generation pipeline using the
headless_sidewalkreator library. It processes a real polygon area, downloads
OSM data, and generates sidewalks, crossings, and kerbs.

The example uses the test polygon from data_assets/test_data/polygon_3857.geojson
as the area of interest. The OSM street network data is automatically downloaded
using the built-in OSMnx capabilities.

Output files are saved to: examples/outputs/full_pipeline/
"""

import os
import sys
from pathlib import Path

import geopandas as gpd

# Add the parent directory to the path to import the library
sys.path.insert(0, str(Path(__file__).parent.parent))

from headless_sidewalkreator import sidewalkreator


def main():
    """Run the full sidewalk generation pipeline."""

    # Define paths
    project_root = Path(__file__).parent.parent
    # Use the carefully selected test polygon in EPSG:4326 for better compatibility
    input_polygon_path = (
        project_root / "data_assets" / "test_data" / "polygon_4326.geojson"
    )
    output_dir = Path(__file__).parent / "outputs" / "full_pipeline"

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("Full Sidewalk Generation Pipeline Example")
    print("=" * 70)
    print(f"\nInput polygon: {input_polygon_path}")
    print(f"Output directory: {output_dir}")
    print("\nNote: This example uses a carefully selected test area (~1.2 km²)")
    print("      in Curitiba, Brazil with good OSM data coverage.")
    print("      Downloading OSM data may take a few minutes...")
    print("\n" + "-" * 70)

    # Load the input polygon
    print("\n[1/5] Loading input polygon...")
    input_polygon_gdf = gpd.read_file(input_polygon_path)
    print(f"      Loaded polygon with CRS: {input_polygon_gdf.crs}")
    print(f"      Polygon bounds: {input_polygon_gdf.total_bounds}")

    # Run the sidewalkreator algorithm
    # This will:
    # - Download OSM data for the polygon's bounding box
    # - Generate protoblocks (enclosed areas formed by roads)
    # - Create sidewalk geometries along roads
    # - Generate crossings between sidewalks
    # - Place kerb points at crossing endpoints
    print("\n[2/5] Running sidewalk generation algorithm...")
    print("      (This may take a few minutes to download OSM data and process)")

    result = sidewalkreator(
        input_polygon_gdf=input_polygon_gdf,
        parameters={
            "timeout": 180,  # Increase timeout for OSM download (3 minutes)
            "buffer_dist": 2.0,  # Buffer distance for sidewalk placement
            "default_curve_radius": 3.0,  # Radius for curved corners
            "min_d_to_building": 1.0,  # Minimum distance from buildings
            "dead_end_removal_iterations": 1,  # Remove disconnected segments
        },
        ignore_existing=False,  # Filter out areas with existing sidewalks
    )

    # Extract results
    sidewalks_gdf = result["sidewalks"]
    crossings_gdf = result["crossings"]
    kerbs_gdf = result["kerbs"]
    protoblocks_gdf = result["protoblocks"]
    pois_gdf = result["pois"]
    parameters_used = result["parameters"]

    print("\n[3/5] Algorithm complete! Generated features:")
    print(f"      - {len(sidewalks_gdf)} sidewalk segments")
    print(f"      - {len(crossings_gdf)} crossing segments")
    print(f"      - {len(kerbs_gdf)} kerb points")
    print(f"      - {len(protoblocks_gdf)} protoblocks (for reference)")
    print(f"      - {len(pois_gdf)} POIs extracted")

    # Save results to files
    print("\n[4/5] Saving results to GeoJSON files...")

    # Save main outputs
    if not sidewalks_gdf.empty:
        sidewalks_path = output_dir / "sidewalks.geojson"
        sidewalks_gdf.to_crs("EPSG:4326").to_file(sidewalks_path, driver="GeoJSON")
        print(f"      ✓ Saved sidewalks to: {sidewalks_path}")

    if not crossings_gdf.empty:
        crossings_path = output_dir / "crossings.geojson"
        crossings_gdf.to_crs("EPSG:4326").to_file(crossings_path, driver="GeoJSON")
        print(f"      ✓ Saved crossings to: {crossings_path}")

    if not kerbs_gdf.empty:
        kerbs_path = output_dir / "kerbs.geojson"
        kerbs_gdf.to_crs("EPSG:4326").to_file(kerbs_path, driver="GeoJSON")
        print(f"      ✓ Saved kerbs to: {kerbs_path}")

    # Save auxiliary outputs
    auxiliary_dir = output_dir / "auxiliary"
    auxiliary_dir.mkdir(exist_ok=True)

    if not protoblocks_gdf.empty:
        protoblocks_path = auxiliary_dir / "protoblocks.geojson"
        protoblocks_gdf.to_crs("EPSG:4326").to_file(protoblocks_path, driver="GeoJSON")
        print(f"      ✓ Saved protoblocks to: {protoblocks_path}")

    if not pois_gdf.empty:
        pois_path = auxiliary_dir / "pois.geojson"
        pois_gdf.to_crs("EPSG:4326").to_file(pois_path, driver="GeoJSON")
        print(f"      ✓ Saved POIs to: {pois_path}")

    # Save the input polygon for reference
    input_copy_path = auxiliary_dir / "input_polygon.geojson"
    input_polygon_gdf.to_crs("EPSG:4326").to_file(input_copy_path, driver="GeoJSON")
    print(f"      ✓ Saved input polygon to: {input_copy_path}")

    # Create a merged output file suitable for JOSM/OSM upload
    print("\n[5/5] Creating merged output for OSM upload...")
    create_merged_josm_output(sidewalks_gdf, crossings_gdf, kerbs_gdf, output_dir)

    # Print summary
    print("\n" + "=" * 70)
    print("Pipeline Complete!")
    print("=" * 70)
    print(f"\nAll outputs saved to: {output_dir}")
    print("\nFiles generated:")
    print("  Main outputs:")
    print("    - sidewalks.geojson     (sidewalk line geometries)")
    print("    - crossings.geojson     (crossing line geometries)")
    print("    - kerbs.geojson         (kerb point geometries)")
    print("    - merged_for_josm.geojson (combined file for OSM editors)")
    print("  Auxiliary outputs:")
    print("    - auxiliary/protoblocks.geojson (intermediate protoblocks)")
    print("    - auxiliary/pois.geojson        (extracted points of interest)")
    print("    - auxiliary/input_polygon.geojson (input area)")
    print("\nYou can now:")
    print("  1. View these files in QGIS or any GIS software")
    print("  2. Open merged_for_josm.geojson in JOSM to upload to OpenStreetMap")
    print("  3. Use the individual GeoJSON files for further analysis")
    print()


def create_merged_josm_output(sidewalks_gdf, crossings_gdf, kerbs_gdf, output_dir):
    """Create a single merged GeoJSON file suitable for JOSM import.

    This file contains all features with proper OSM tags for easy upload.
    """
    import json

    merged_features = []

    # Add sidewalks with OSM tags
    if not sidewalks_gdf.empty:
        sidewalks_4326 = sidewalks_gdf.to_crs("EPSG:4326")
        for geom in sidewalks_4326.geometry:
            feature = {
                "type": "Feature",
                "properties": {"highway": "footway", "footway": "sidewalk"},
                "geometry": geom.__geo_interface__,
            }
            merged_features.append(feature)

    # Add crossings with OSM tags
    if not crossings_gdf.empty:
        crossings_4326 = crossings_gdf.to_crs("EPSG:4326")
        for geom in crossings_4326.geometry:
            feature = {
                "type": "Feature",
                "properties": {"highway": "footway", "footway": "crossing"},
                "geometry": geom.__geo_interface__,
            }
            merged_features.append(feature)

    # Add kerbs with OSM tags
    if not kerbs_gdf.empty:
        kerbs_4326 = kerbs_gdf.to_crs("EPSG:4326")
        for geom in kerbs_4326.geometry:
            feature = {
                "type": "Feature",
                "properties": {"barrier": "kerb"},
                "geometry": geom.__geo_interface__,
            }
            merged_features.append(feature)

    # Create GeoJSON structure
    merged_geojson = {"type": "FeatureCollection", "features": merged_features}

    # Save merged file
    merged_path = output_dir / "merged_for_josm.geojson"
    with open(merged_path, "w") as f:
        json.dump(merged_geojson, f, indent=2)

    print(f"      ✓ Saved merged JOSM file to: {merged_path}")
    print(f"        (Contains {len(merged_features)} total features)")


if __name__ == "__main__":
    main()
