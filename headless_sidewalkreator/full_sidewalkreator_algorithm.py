"""Main algorithm for headless_sidewalkreator.

This module exposes the sidewalkreator function - the modern GeoDataFrame-based API.
"""

import os
import json
import geopandas as gpd
import osmnx as ox
from .generic_functions import (
    read_input_polygon,
    get_bbox_from_gdf,
    bbox_to_gdf,
    fetch_street_network_for_bbox,
    clip_gdf,
    reproject_gdf,
    polygonize_lines_gdf,
    data_clean_gdf,
    split_lines_at_intersections,
    handle_sidewalk_tags,
    draw_sidewalks_gdf,
    remove_lines_from_no_block_gdf,
    filter_and_buffer_protoblocks_gdf,
    draw_crossings_gdf,
    split_sidewalks_gdf,
    generate_kerbs_gdf,
)
from . import parameters as params


def generate_protoblocks(
    input_polygon_gdf: gpd.GeoDataFrame = None,
    place_name: str = None,
    bbox: tuple = None,
    osm_gdf: gpd.GeoDataFrame = None,
    parameters: dict = None,
) -> gpd.GeoDataFrame:
    """Generate protoblocks from input area and OSM data.

    This function generates protoblocks (enclosed areas formed by road networks)
    independently of the full sidewalk generation process. Protoblocks are created
    by fetching street data, cleaning it, splitting at intersections, and polygonizing
    the resulting line network.

    Args:
        input_polygon_gdf: GeoDataFrame containing the input polygon geometry.
        place_name: A string to be geocoded to a polygon boundary for the area of interest.
                    Use this OR input_polygon_gdf OR bbox, not multiple.
        bbox: A tuple (minx, miny, maxx, maxy) defining a rectangular bounding box area of interest.
              Use this OR input_polygon_gdf OR place_name, not multiple.
        osm_gdf: Optional GeoDataFrame with OSM data to be used instead of fetching.
                If None, OSM data will be fetched automatically for the input polygon's bbox.
        parameters: Optional dictionary with runtime parameters to override defaults.

    Returns:
        GeoDataFrame containing the protoblocks (polygon geometries).
    """
    print("--- generate_protoblocks called ---")

    # Consolidate parameters
    run_params = {
        "timeout": 60,
        "default_widths": params.default_widths,
        "fallback_default_width": params.fallback_default_width,
        "crossing_inward_offset": params.crossing_inward_offset,
        "crossing_extra_length": params.crossing_extra_length,
        "crossing_ray_growth_factor": params.crossing_ray_growth_factor,
        "crossing_max_ray_iterations": params.crossing_max_ray_iterations,
        "crossing_node_precision": params.crossing_node_precision,
    }

    if parameters:
        run_params.update(parameters)

    # 1. Determine input area from either place_name, input_polygon_gdf, or bbox
    input_sources = [place_name, input_polygon_gdf, bbox]
    provided_sources = [src for src in input_sources if src is not None]

    if len(provided_sources) != 1:
        raise ValueError(
            "Provide exactly one of 'place_name', 'input_polygon_gdf', or 'bbox'."
        )

    if place_name:
        # Geocode the place name to a GeoDataFrame
        print(f"Geocoding place_name: '{place_name}'")
        input_gdf = ox.geocode_to_gdf(place_name)
    elif input_polygon_gdf is not None:
        # Use the provided GeoDataFrame
        input_gdf = input_polygon_gdf.copy()
    elif bbox is not None:
        # Convert bounding box to GeoDataFrame
        print(f"Converting bbox to GeoDataFrame: {bbox}")
        input_gdf = bbox_to_gdf(bbox)
    else:
        raise ValueError(
            "Either 'place_name', 'input_polygon_gdf', or 'bbox' must be provided."
        )

    # 2. Get bounding box
    bbox = get_bbox_from_gdf(input_gdf)

    # 3. Fetch OSM Data (allow injection via `osm_gdf`)
    if osm_gdf is None:
        osm_gdf = fetch_street_network_for_bbox(bbox, timeout=run_params["timeout"])
    print("Step 3 complete.")

    # 4. Clip data
    clipped_gdf = clip_gdf(osm_gdf, input_gdf)
    print("Step 4 complete.")

    # 5. Reproject to a local TM
    utm_crs = input_gdf.estimate_utm_crs()
    clipped_reproj_gdf = reproject_gdf(clipped_gdf, utm_crs)
    print("Step 5 complete.")

    # 6. Clean data
    cleaned_gdf, existing_sidewalks, existing_crossings = data_clean_gdf(
        clipped_reproj_gdf,
        run_params["default_widths"],
        run_params["fallback_default_width"],
    )
    print("Step 6 complete.")

    # 7. Split lines at intersections
    lines_gdf = cleaned_gdf[cleaned_gdf.geometry.type == "LineString"].copy()
    splitted_gdf = split_lines_at_intersections(lines_gdf)
    print("Step 7 complete.")

    # 8. Create protoblocks from polygonizing
    protoblocks_gdf = polygonize_lines_gdf(splitted_gdf)
    print("Step 8 complete.")

    print("Protoblocks generation complete.")
    return protoblocks_gdf


def sidewalkreator(
    input_polygon_gdf: gpd.GeoDataFrame = None,
    place_name: str = None,
    bbox: tuple = None,
    osm_gdf: gpd.GeoDataFrame = None,
    parameters: dict = None,
    ignore_existing: bool = False,
) -> dict:
    print("--- sidewalkreator called ---")
    """Generate sidewalks from input polygon and OSM data, returning GeoDataFrames.
    
    This is the main API function that accepts and returns GeoDataFrames instead of files,
    making the library more flexible by letting users handle I/O.
    
    Args:
        input_polygon_gdf: GeoDataFrame containing the input polygon geometry.
        place_name: A string to be geocoded to a polygon boundary for the area of interest.
                    Use this OR input_polygon_gdf OR bbox, not multiple.
        bbox: A tuple (minx, miny, maxx, maxy) defining a rectangular bounding box area of interest.
              Use this OR input_polygon_gdf OR place_name, not multiple.
        osm_gdf: Optional GeoDataFrame with OSM data to be used instead of fetching.
                If None, OSM data will be fetched automatically for the input polygon's bbox.
        parameters: Optional dictionary with runtime parameters to override defaults.
        ignore_existing: If True, ignores existing sidewalks and generates all
            possible sidewalks without filtering based on pre-existing coverage.
    
    Returns:
        Dictionary containing output GeoDataFrames with keys:
        - 'sidewalks': Main sidewalk line geometries
        - 'crossings': Crossing line geometries  
        - 'kerbs': Kerb point geometries
        - 'protoblocks': Intermediate protoblocks (for debugging)
        - 'intersection_points': Intersection points used in processing
        - 'pois': Points of interest (building centroids, addresses, amenities)
        - 'input_area': The input area geometry used (for compatibility)
        - 'parameters': Runtime parameters that were used
    """

    # Consolidate parameters
    run_params = {
        "timeout": 60,
        "default_widths": params.default_widths,
        "fallback_default_width": params.fallback_default_width,
        "default_curve_radius": params.default_curve_radius,
        "buffer_dist": 2,
        "split_max_len": None,
        "split_num_segments": None,
        "min_d_to_building": params.min_d_to_building,
        "perc_draw_kerbs": params.perc_draw_kerbs,
        "perc_tol_crossings": params.perc_tol_crossings,
        "increment_inward": params.increment_inward,
        "max_crossings_iterations": params.max_crossings_iterations,
        "cutoff_percent_protoblock": params.cutoff_percent_protoblock,
        "min_stretch_size": params.min_stretch_size,
        "abs_max_crossing_len": params.abs_max_crossing_len,
        "dead_end_removal_iterations": 1,  # Default to 1 iteration
        "crossing_inward_offset": params.crossing_inward_offset,
        "crossing_extra_length": params.crossing_extra_length,
        "crossing_ray_growth_factor": params.crossing_ray_growth_factor,
        "crossing_max_ray_iterations": params.crossing_max_ray_iterations,
        "crossing_node_precision": params.crossing_node_precision,
    }

    if parameters:
        run_params.update(parameters)

    # 1. Determine input area from either place_name, input_polygon_gdf, or bbox
    input_sources = [place_name, input_polygon_gdf, bbox]
    provided_sources = [src for src in input_sources if src is not None]

    if len(provided_sources) != 1:
        raise ValueError(
            "Provide exactly one of 'place_name', 'input_polygon_gdf', or 'bbox'."
        )

    if place_name:
        # Geocode the place name to a GeoDataFrame
        print(f"Geocoding place_name: '{place_name}'")
        input_gdf = ox.geocode_to_gdf(place_name)
    elif input_polygon_gdf is not None:
        # Use the provided GeoDataFrame
        input_gdf = input_polygon_gdf.copy()
    elif bbox is not None:
        # Convert bounding box to GeoDataFrame
        print(f"Converting bbox to GeoDataFrame: {bbox}")
        input_gdf = bbox_to_gdf(bbox)
    else:
        raise ValueError(
            "Either 'place_name', 'input_polygon_gdf', or 'bbox' must be provided."
        )

    # 2. Get bounding box
    bbox = get_bbox_from_gdf(input_gdf)

    # 3. Fetch OSM Data (allow injection via `osm_gdf`)
    if osm_gdf is None:
        osm_gdf = fetch_street_network_for_bbox(bbox, timeout=run_params["timeout"])
    print("Step 3 complete.")

    # 4. Clip data
    clipped_gdf = clip_gdf(osm_gdf, input_gdf)
    print("Step 4 complete.")

    # 5. Reproject to a local TM
    utm_crs = input_gdf.estimate_utm_crs()
    clipped_reproj_gdf = reproject_gdf(clipped_gdf, utm_crs)
    print("Step 5 complete.")

    # 6. Clean data
    cleaned_gdf, existing_sidewalks, existing_crossings = data_clean_gdf(
        clipped_reproj_gdf,
        run_params["default_widths"],
        run_params["fallback_default_width"],
    )
    print("Step 6 complete.")

    # 7. Split lines at intersections
    lines_gdf = cleaned_gdf[cleaned_gdf.geometry.type == "LineString"].copy()
    splitted_gdf = split_lines_at_intersections(lines_gdf)
    print("Step 7 complete.")

    # 8. Create protoblocks using the standalone generation logic
    # Use the same implementation as the detached protoblocks generator so
    # behavior is identical between the example and the full pipeline.
    protoblocks_gdf = generate_protoblocks(
        input_polygon_gdf=input_gdf,
        osm_gdf=osm_gdf,
        parameters=parameters,
    )
    print("Step 8 complete.")

    # Store the original protoblocks for output (before filtering/dissolving)
    original_protoblocks_gdf = protoblocks_gdf.copy()

    # 9. Extract POI data (buildings, addresses, other POIs)
    buildings_gdf = cleaned_gdf[
        (cleaned_gdf["building"].notna()) & (cleaned_gdf["building"] != "")
    ].copy()

    # Extract address nodes
    if "addr:housenumber" in clipped_reproj_gdf.columns:
        addresses_gdf = clipped_reproj_gdf[
            clipped_reproj_gdf["addr:housenumber"].notna()
        ].copy()
    else:
        addresses_gdf = gpd.GeoDataFrame(geometry=[], crs=clipped_reproj_gdf.crs)

    # Extract other POIs (amenities and shops)
    other_pois_gdf = clipped_reproj_gdf[
        clipped_reproj_gdf["amenity"].notna() | clipped_reproj_gdf["shop"].notna()
    ].copy()

    # Create unified POI layer for sidewalk splitting
    poi_layers = []
    if not buildings_gdf.empty:
        building_centroids = buildings_gdf.copy()
        building_centroids["geometry"] = building_centroids.geometry.centroid
        poi_layers.append(building_centroids)
    if not addresses_gdf.empty:
        poi_layers.append(addresses_gdf)
    if not other_pois_gdf.empty:
        poi_layers.append(other_pois_gdf)

    if poi_layers:
        unified_pois_gdf = gpd.pd.concat(poi_layers, ignore_index=True)
    else:
        unified_pois_gdf = gpd.GeoDataFrame(geometry=[], crs=clipped_reproj_gdf.crs)
    print("Step 9 complete.")

    # 10. Draw sidewalks
    streets_gdf = cleaned_gdf[
        (cleaned_gdf["highway"].notna()) & (cleaned_gdf["highway"] != "")
    ].copy()

    sidewalks_gdf = draw_sidewalks_gdf(
        splitted_gdf,
        buildings_gdf,
        streets_gdf,
        buffer_dist=run_params["buffer_dist"],
        curve_radius=run_params["default_curve_radius"],
        min_d_to_building=run_params["min_d_to_building"],
    )
    print("Step 10 complete.")

    # Handle sidewalk tags
    sidewalks_gdf = handle_sidewalk_tags(sidewalks_gdf, cleaned_gdf)

    # 11. Remove lines from no-block zones if ignore_existing is False
    if not ignore_existing:
        sidewalks_gdf = remove_lines_from_no_block_gdf(
            sidewalks_gdf, iterations=run_params["dead_end_removal_iterations"]
        )
    print("Step 11 complete.")

    # 12. Filter and buffer protoblocks (for internal processing)
    # Note: This creates a dissolved/buffered version for crossing generation,
    # but we keep the original protoblocks for the output
    filtered_protoblocks_gdf = filter_and_buffer_protoblocks_gdf(
        protoblocks_gdf,
        sidewalks_gdf,
        cutoff_percent=run_params["cutoff_percent_protoblock"],
        ignore_existing=ignore_existing,
    )
    print("Step 12 complete.")

    # 13. Draw crossings using ABCDE algorithm
    # Use the filtered/dissolved protoblocks for crossing generation
    crossings_gdf = draw_crossings_gdf(
        splitted_gdf,
        sidewalks_gdf,
        filtered_protoblocks_gdf,  # Use filtered version here
        curve_radius=run_params["default_curve_radius"],
        inward_offset=run_params["crossing_inward_offset"],
        extra_length=run_params["crossing_extra_length"],
        increment_inward=run_params["increment_inward"],
        max_crossings_iterations=run_params["max_crossings_iterations"],
        abs_max_crossing_len=run_params["abs_max_crossing_len"],
        perc_tol_crossings=run_params["perc_tol_crossings"],
        perc_draw_kerbs=run_params["perc_draw_kerbs"],
        ray_growth_factor=run_params["crossing_ray_growth_factor"],
        max_ray_iterations=run_params["crossing_max_ray_iterations"],
        node_precision=run_params["crossing_node_precision"],
    )
    print("Step 13 complete.")

    # 14. Split sidewalks (now with POI integration)
    intersection_points_gdf = gpd.GeoDataFrame(
        geometry=crossings_gdf.centroid, crs=crossings_gdf.crs
    )
    splitted_sidewalks_gdf = split_sidewalks_gdf(
        sidewalks_gdf,
        intersection_points_gdf,
        original_protoblocks_gdf,  # Use original protoblocks for splitting
        unified_pois_gdf,  # Now using the actual POI layer
        max_length=run_params["split_max_len"],
        num_segments=run_params["split_num_segments"],
        min_stretch_size=run_params["min_stretch_size"],
    )
    print("Step 14 complete.")

    # 15. Generate kerbs
    kerbs_gdf = generate_kerbs_gdf(crossings_gdf)
    print("Step 15 complete.")

    # Return all results as GeoDataFrames
    # Use original_protoblocks_gdf so users get the individual blocks, not dissolved
    result = {
        "sidewalks": splitted_sidewalks_gdf,
        "crossings": crossings_gdf,
        "kerbs": kerbs_gdf,
        "protoblocks": original_protoblocks_gdf,  # Return original protoblocks
        "intersection_points": intersection_points_gdf,
        "pois": unified_pois_gdf,  # Add POI data to output
        "input_area": input_gdf,  # Add input area for legacy file-based function
        "parameters": run_params,
    }

    print("Process complete. Returning GeoDataFrames.")
    return result
