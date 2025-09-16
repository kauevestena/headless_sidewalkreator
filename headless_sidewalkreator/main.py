"""Main API for headless_sidewalkreator.

This module exposes the run_headless function used by the tests and CLI.
"""

import os
import json
import geopandas as gpd
from .generic_functions import (
    read_input_polygon,
    get_bbox_from_gdf,
    fetch_street_network_for_bbox,
    clip_gdf,
    reproject_gdf,
    polygonize_lines_gdf,
    data_clean_gdf,
    split_lines_at_intersections,
    draw_sidewalks_gdf,
    remove_lines_from_no_block_gdf,
    filter_and_buffer_protoblocks_gdf,
    draw_crossings_gdf,
    split_sidewalks_gdf,
    generate_kerbs_gdf,
)
from .parameters import *


def run_headless(
    input_polygon_path: str,
    output_directory: str,
    parameters_path: str = None,
    osm_gdf: gpd.GeoDataFrame = None,
):
    """Main function for the headless execution of the sidewalk generation process.

    This function orchestrates the entire sidewalk generation process, from
    reading the input polygon to generating the final output files.

    Args:
        input_polygon_path: Path to the GeoJSON file containing the input polygon.
        output_directory: Directory where the output files will be saved.
        parameters_path: Optional path to a JSON file with parameters.
        osm_gdf: Optional GeoDataFrame with OSM data to be used instead of fetching.
    """

    # Load parameters or use defaults
    if parameters_path and os.path.exists(parameters_path):
        with open(parameters_path, "r") as f:
            params = json.load(f)
    else:
        params = {
            "timeout": 60,
        }

    # Create output directory if it doesn't exist
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    # 1. Load input polygon
    input_gdf = read_input_polygon(input_polygon_path)

    # 2. Get bounding box
    bbox = get_bbox_from_gdf(input_gdf)

    # 3. Fetch OSM Data (allow injection for tests via `osm_gdf`)
    if osm_gdf is None:
        osm_gdf = fetch_street_network_for_bbox(bbox)

    print(f"Number of features in osm_gdf: {len(osm_gdf)}")
    print(f"Columns in osm_gdf: {osm_gdf.columns}")
    print(f"CRS of osm_gdf: {osm_gdf.crs}")
    print(f"Bbox of osm_gdf: {osm_gdf.total_bounds}")
    print(f"CRS of input_gdf: {input_gdf.crs}")
    print(f"Bbox of input_gdf: {input_gdf.total_bounds}")

    # 4. Clip data
    clipped_gdf = clip_gdf(osm_gdf, input_gdf)

    # 5. Reproject to a local TM
    utm_crs = input_gdf.estimate_utm_crs()
    clipped_reproj_gdf = reproject_gdf(clipped_gdf, utm_crs)

    print(f"Number of features in clipped_reproj_gdf: {len(clipped_reproj_gdf)}")
    # 6. Clean data
    cleaned_gdf, existing_sidewalks, existing_crossings = data_clean_gdf(
        clipped_reproj_gdf, default_widths, fallback_default_width
    )

    # 7. Split lines at intersections
    lines_gdf = cleaned_gdf[cleaned_gdf.geometry.type == "LineString"].copy()
    splitted_gdf = split_lines_at_intersections(lines_gdf)

    # 8. Remove lines that do not form a block
    cleaned_splitted_gdf = remove_lines_from_no_block_gdf(splitted_gdf)

    # 9. Polygonize to create protoblocks
    protoblocks_gdf = polygonize_lines_gdf(cleaned_splitted_gdf)

    # 10. Filter and buffer protoblocks
    filtered_protoblocks_gdf = filter_and_buffer_protoblocks_gdf(
        protoblocks_gdf, existing_sidewalks
    )

    # 11. Separate buildings
    buildings_gdf = osm_gdf[osm_gdf["building"].notna()].copy()

    # 11. Separate POIs
    pois_gdf = osm_gdf[osm_gdf["amenity"].notna() | osm_gdf["shop"].notna()].copy()

    # 12. Draw sidewalks
    sidewalks_gdf = draw_sidewalks_gdf(
        cleaned_splitted_gdf, buildings_gdf, cleaned_gdf, 2
    )

    # 13. Draw crossings
    crossings_gdf = draw_crossings_gdf(splitted_gdf)

    # 14. Split sidewalks
    intersection_points_gdf = gpd.GeoDataFrame(
        geometry=crossings_gdf.centroid, crs=crossings_gdf.crs
    )
    splitted_sidewalks_gdf = split_sidewalks_gdf(
        sidewalks_gdf,
        intersection_points_gdf,
        protoblocks_gdf,
        pois_gdf,
        max_length=params.get("split_max_len"),
        num_segments=params.get("split_num_segments"),
    )

    # 14. Output results
    output_path = os.path.join(output_directory, "protoblocks_output.geojson")
    if not protoblocks_gdf.empty:
        protoblocks_gdf.to_crs("EPSG:4326").to_file(output_path, driver="GeoJSON")

    sidewalks_output_path = os.path.join(output_directory, "sidewalks_output.geojson")
    if not splitted_sidewalks_gdf.empty:
        splitted_sidewalks_gdf.to_crs("EPSG:4326").to_file(
            sidewalks_output_path, driver="GeoJSON"
        )

    crossings_output_path = os.path.join(output_directory, "crossings_output.geojson")
    if not crossings_gdf.empty:
        crossings_gdf.to_crs("EPSG:4326").to_file(
            crossings_output_path, driver="GeoJSON"
        )

    # 15. Generate kerbs
    kerbs_gdf = generate_kerbs_gdf(crossings_gdf)
    kerbs_output_path = os.path.join(output_directory, "kerbs_output.geojson")
    if not kerbs_gdf.empty:
        kerbs_gdf.to_crs("EPSG:4326").to_file(kerbs_output_path, driver="GeoJSON")

    print(f"Process complete. Output saved to {output_path}")


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
