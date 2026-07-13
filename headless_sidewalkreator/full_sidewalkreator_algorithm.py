"""Main algorithm for headless_sidewalkreator.

This module exposes the sidewalkreator function - the modern GeoDataFrame-based API.
"""

import time

import geopandas as gpd
import osmnx as ox
from shapely.geometry import Polygon
from tqdm import tqdm
from .generic_functions import (
    get_bbox_from_gdf,
    bbox_to_gdf,
    fetch_street_network_for_bbox,
    clip_gdf,
    reproject_gdf,
    polygonize_lines_gdf,
    data_clean_gdf,
    split_lines_at_intersections,
    normalize_protomaps_topology,
    _validate_protomaps_topology_options,
    handle_sidewalk_tags,
    draw_sidewalks_gdf,
    remove_lines_from_no_block_gdf,
    draw_crossings_gdf,
    split_sidewalks_gdf,
    generate_kerbs_gdf,
    save_debug_layer,
)
from . import parameters as params
from .logging_config import get_logger


logger = get_logger(__name__)


def _save_debug_layer_if_enabled(enabled: bool, gdf, layer_name: str):
    if enabled:
        save_debug_layer(gdf, layer_name)


def _run_timed_stage(
    label: str,
    progress_enabled: bool,
    func,
    *args,
    _overall_progress=None,
    **kwargs,
):
    if progress_enabled:
        print(f"   {label}...")
        if _overall_progress is not None:
            _overall_progress.set_postfix_str(label, refresh=True)
    start = time.perf_counter()
    try:
        result = func(*args, **kwargs)
    except Exception:
        if _overall_progress is not None:
            _overall_progress.close()
        raise
    duration = time.perf_counter() - start
    if _overall_progress is not None:
        _overall_progress.update(1)
        _overall_progress.set_postfix_str(
            f"completed in {duration:.2f}s",
            refresh=True,
        )
    if progress_enabled:
        print(f"   {label} complete in {duration:.2f} seconds.")
    return result


def _resolve_input_area(
    place_name: str = None,
    input_polygon_gdf: gpd.GeoDataFrame = None,
    bbox: tuple = None,
) -> gpd.GeoDataFrame:
    """Determine input area from either place_name, input_polygon_gdf, or bbox."""
    input_sources = [place_name, input_polygon_gdf, bbox]
    provided_sources = [src for src in input_sources if src is not None]

    if len(provided_sources) != 1:
        raise ValueError(
            "Provide exactly one of 'place_name', 'input_polygon_gdf', or 'bbox'."
        )

    if place_name:
        # Geocode the place name to a GeoDataFrame
        logger.info("Geocoding place_name '%s'", place_name)
        input_gdf = ox.geocode_to_gdf(place_name)
    elif input_polygon_gdf is not None:
        # Use the provided GeoDataFrame
        input_gdf = input_polygon_gdf.copy()
    elif bbox is not None:
        # Convert bounding box to GeoDataFrame
        logger.info("Converting bbox %s to GeoDataFrame", bbox)
        input_gdf = bbox_to_gdf(bbox)
    else:
        raise ValueError(
            "Either 'place_name', 'input_polygon_gdf', or 'bbox' must be provided."
        )
    return input_gdf


def _fetch_and_clip_osm(
    input_gdf: gpd.GeoDataFrame,
    osm_gdf: gpd.GeoDataFrame = None,
    timeout: int = 60,
    provider: str = None,
    **kwargs
) -> gpd.GeoDataFrame:
    """Fetch OSM data for the input area and clip it."""
    # 2. Get bounding box
    bbox = get_bbox_from_gdf(input_gdf)

    # 3. Fetch OSM Data (allow injection via `osm_gdf`)
    if osm_gdf is None:
        osm_gdf = fetch_street_network_for_bbox(bbox, timeout=timeout, provider=provider, **kwargs)
    logger.info("Step 3 complete")

    # 4. Clip data
    source_attrs = dict(osm_gdf.attrs)
    clipped_gdf = clip_gdf(osm_gdf, input_gdf)
    clipped_gdf.attrs.update(source_attrs)
    logger.info("Step 4 complete")
    return clipped_gdf


def _is_protomaps_source(gdf: gpd.GeoDataFrame, provider: str = None) -> bool:
    """Detect Protomaps data without requiring serialized DataFrame metadata."""
    if provider == "protomaps" or gdf.attrs.get("provider") == "protomaps":
        return True
    pmap_columns = [
        column
        for column in gdf.columns
        if isinstance(column, str) and column.startswith("pmap:")
    ]
    return any(gdf[column].notna().any() for column in pmap_columns)


def _preprocess_osm_data(
    clipped_gdf: gpd.GeoDataFrame,
    input_gdf: gpd.GeoDataFrame,
    default_widths: dict,
    fallback_default_width: float,
    provider: str = None,
    repair_protomaps_topology: bool = True,
    protomaps_endpoint_snap_tolerance: float = 0.5,
    protomaps_endpoint_snap_max_angle: float = 45.0,
    show_progress: bool = False,
) -> tuple:
    """Reproject, clean, and split OSM lines at intersections."""
    (
        protomaps_endpoint_snap_tolerance,
        protomaps_endpoint_snap_max_angle,
    ) = _validate_protomaps_topology_options(
        protomaps_endpoint_snap_tolerance,
        protomaps_endpoint_snap_max_angle,
    )

    normalize_protomaps = repair_protomaps_topology and _is_protomaps_source(
        clipped_gdf,
        provider,
    )

    # 5. Reproject to a local TM
    utm_crs = input_gdf.estimate_utm_crs()
    clipped_reproj_gdf = reproject_gdf(clipped_gdf, utm_crs)
    logger.info("Step 5 complete")

    # 6. Clean data
    cleaned_gdf, _, _ = data_clean_gdf(
        clipped_reproj_gdf,
        default_widths,
        fallback_default_width,
        show_progress=show_progress,
    )
    logger.info("Step 6 complete")

    # 7. Split lines at intersections
    linework_gdf = cleaned_gdf[
        cleaned_gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])
    ].copy()
    lines_gdf = linework_gdf.explode(index_parts=False, ignore_index=True)
    lines_gdf = lines_gdf[lines_gdf.geometry.type == "LineString"].copy()
    if normalize_protomaps:
        splitted_gdf = normalize_protomaps_topology(
            lines_gdf,
            endpoint_snap_tolerance=protomaps_endpoint_snap_tolerance,
            endpoint_snap_max_angle=protomaps_endpoint_snap_max_angle,
            show_progress=show_progress,
        )
    else:
        splitted_gdf = split_lines_at_intersections(lines_gdf)
    logger.info("Step 7 complete")

    return splitted_gdf, cleaned_gdf, clipped_reproj_gdf


def _get_polygonize_clip_geom(
    input_gdf: gpd.GeoDataFrame,
    target_crs=None,
) -> gpd.GeoDataFrame:
    """Create a bounding box polygon for polygonization."""
    if input_gdf is not None and not input_gdf.empty:
        clip_source_gdf = input_gdf
        if target_crs is not None and clip_source_gdf.crs != target_crs:
            clip_source_gdf = clip_source_gdf.to_crs(target_crs)

        # Create a bounding box polygon using the bounds of the input geometry
        bbox_bounds = clip_source_gdf.total_bounds
        bbox_poly = Polygon([
            (bbox_bounds[0], bbox_bounds[1]),
            (bbox_bounds[2], bbox_bounds[1]),
            (bbox_bounds[2], bbox_bounds[3]),
            (bbox_bounds[0], bbox_bounds[3]),
            (bbox_bounds[0], bbox_bounds[1])
        ])
        return gpd.GeoDataFrame(geometry=[bbox_poly], crs=clip_source_gdf.crs)
    return None


def _generate_protoblocks_from_splitted_lines(
    input_gdf: gpd.GeoDataFrame,
    splitted_gdf: gpd.GeoDataFrame,
    renode_before_polygonize: bool = False,
    show_progress: bool = False,
) -> gpd.GeoDataFrame:
    """Generate protoblocks from an already preprocessed line network."""
    clip_geom = _get_polygonize_clip_geom(input_gdf, target_crs=splitted_gdf.crs)
    return polygonize_lines_gdf(
        splitted_gdf,
        clip_geom=clip_geom,
        node_lines=renode_before_polygonize,
        show_progress=show_progress,
    )


def _extract_poi_data(
    cleaned_gdf: gpd.GeoDataFrame,
    clipped_reproj_gdf: gpd.GeoDataFrame,
) -> tuple:
    """Extract POIs (buildings, addresses, amenities, shops) from OSM data."""
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
    logger.info("Step 9 complete")

    return unified_pois_gdf, buildings_gdf


def _draw_sidewalks(
    splitted_gdf: gpd.GeoDataFrame,
    buildings_gdf: gpd.GeoDataFrame,
    cleaned_gdf: gpd.GeoDataFrame,
    run_params: dict,
) -> gpd.GeoDataFrame:
    """Draw sidewalks from processed street and building data."""
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
        show_progress=run_params.get("show_progress", False),
    )

    # Handle sidewalk tags
    sidewalks_gdf = handle_sidewalk_tags(sidewalks_gdf, cleaned_gdf)
    logger.info("Step 10 complete")
    return sidewalks_gdf


def _apply_dead_end_removal(
    sidewalks_gdf: gpd.GeoDataFrame,
    ignore_existing: bool,
    dead_end_removal_iterations: int,
    show_progress: bool = False,
) -> gpd.GeoDataFrame:
    """Remove lines from no-block zones (dead ends)."""
    # 11. Remove lines from no-block zones if ignore_existing is False
    if not ignore_existing:
        sidewalks_gdf = remove_lines_from_no_block_gdf(
            sidewalks_gdf,
            iterations=dead_end_removal_iterations,
            show_progress=show_progress,
        )
    logger.info("Step 11 complete")
    return sidewalks_gdf


def _generate_crossings(
    splitted_gdf: gpd.GeoDataFrame,
    sidewalks_gdf: gpd.GeoDataFrame,
    protoblocks_gdf: gpd.GeoDataFrame,
    run_params: dict,
    ignore_existing: bool,
) -> gpd.GeoDataFrame:
    """Filter protoblocks and generate crossings."""
    # draw_crossings_gdf currently keeps this argument for API compatibility but
    # does not consume it. Avoid an expensive spatial join and dissolve whose
    # result cannot affect the generated crossings.
    filtered_protoblocks_gdf = protoblocks_gdf
    logger.info("Step 12 complete")

    # 13. Draw crossings using ABCDE algorithm
    crossings_gdf = draw_crossings_gdf(
        splitted_gdf,
        sidewalks_gdf,
        filtered_protoblocks_gdf,
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
        show_progress=run_params.get("show_progress", False),
        assume_noded=True,
    )
    logger.info("Step 13 complete")
    return crossings_gdf


def _finalize_results(
    sidewalks_gdf: gpd.GeoDataFrame,
    crossings_gdf: gpd.GeoDataFrame,
    protoblocks_gdf: gpd.GeoDataFrame,
    unified_pois_gdf: gpd.GeoDataFrame,
    run_params: dict,
) -> tuple:
    """Split sidewalks at crossings/POIs and generate kerbs."""
    # 14. Split sidewalks (now with POI integration)
    intersection_points_gdf = gpd.GeoDataFrame(
        geometry=crossings_gdf.centroid, crs=crossings_gdf.crs
    )
    splitted_sidewalks_gdf = split_sidewalks_gdf(
        sidewalks_gdf,
        intersection_points_gdf,
        protoblocks_gdf,
        unified_pois_gdf,
        max_length=run_params["split_max_len"],
        num_segments=run_params["split_num_segments"],
        min_stretch_size=run_params["min_stretch_size"],
        show_progress=run_params.get("show_progress", False),
    )
    logger.info("Step 14 complete")

    # 15. Generate kerbs
    kerbs_gdf = generate_kerbs_gdf(
        crossings_gdf,
        show_progress=run_params.get("show_progress", False),
    )
    logger.info("Step 15 complete")
    return splitted_sidewalks_gdf, kerbs_gdf, intersection_points_gdf


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
    logger.info("generate_protoblocks called")

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
        "renode_before_polygonize": False,
        "repair_protomaps_topology": params.repair_protomaps_topology,
        "protomaps_endpoint_snap_tolerance": params.protomaps_endpoint_snap_tolerance,
        "protomaps_endpoint_snap_max_angle": params.protomaps_endpoint_snap_max_angle,
        "show_progress": False,
        "save_debug_layers": False,
    }

    if parameters:
        run_params.update(parameters)

    input_gdf = _resolve_input_area(place_name, input_polygon_gdf, bbox)
    provider_kwargs = dict(run_params.get("provider_kwargs", {}))
    provider_kwargs.setdefault("show_progress", run_params["show_progress"])
    clipped_gdf = _fetch_and_clip_osm(
        input_gdf,
        osm_gdf,
        run_params["timeout"],
        provider=run_params.get("provider"),
        **provider_kwargs,
    )
    splitted_gdf, _, _ = _preprocess_osm_data(
        clipped_gdf,
        input_gdf,
        run_params["default_widths"],
        run_params["fallback_default_width"],
        provider=run_params.get("provider"),
        repair_protomaps_topology=run_params["repair_protomaps_topology"],
        protomaps_endpoint_snap_tolerance=run_params[
            "protomaps_endpoint_snap_tolerance"
        ],
        protomaps_endpoint_snap_max_angle=run_params[
            "protomaps_endpoint_snap_max_angle"
        ],
        show_progress=run_params["show_progress"],
    )

    protoblocks_gdf = _generate_protoblocks_from_splitted_lines(
        input_gdf,
        splitted_gdf,
        renode_before_polygonize=run_params["renode_before_polygonize"],
        show_progress=run_params["show_progress"],
    )

    logger.info("Step 8 complete")
    logger.info("Protoblocks generation complete")
    return protoblocks_gdf


def sidewalkreator(
    input_polygon_gdf: gpd.GeoDataFrame = None,
    place_name: str = None,
    bbox: tuple = None,
    osm_gdf: gpd.GeoDataFrame = None,
    parameters: dict = None,
    ignore_existing: bool = False,
) -> dict:
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
    logger.info("sidewalkreator called")

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
        "renode_before_polygonize": False,
        "repair_protomaps_topology": params.repair_protomaps_topology,
        "protomaps_endpoint_snap_tolerance": params.protomaps_endpoint_snap_tolerance,
        "protomaps_endpoint_snap_max_angle": params.protomaps_endpoint_snap_max_angle,
        "show_progress": False,
        "save_debug_layers": False,
    }

    if parameters:
        run_params.update(parameters)

    # 1-7. Core preprocessing
    show_progress = run_params.get("show_progress", False)
    overall_progress = tqdm(
        total=10,
        desc="Sidewalkreator pipeline",
        unit="stage",
        disable=not show_progress,
        position=0,
        leave=True,
        dynamic_ncols=True,
    )
    input_gdf = _run_timed_stage(
        "Step 1: resolve input area",
        show_progress,
        _resolve_input_area,
        place_name,
        input_polygon_gdf,
        bbox,
        _overall_progress=overall_progress,
    )
    provider_kwargs = dict(run_params.get("provider_kwargs", {}))
    provider_kwargs.setdefault("show_progress", show_progress)
    clipped_gdf = _run_timed_stage(
        "Steps 2-4: fetch and clip OSM data",
        show_progress,
        _fetch_and_clip_osm,
        input_gdf,
        osm_gdf,
        run_params["timeout"],
        provider=run_params.get("provider"),
        _overall_progress=overall_progress,
        **provider_kwargs,
    )
    splitted_gdf, cleaned_gdf, clipped_reproj_gdf = _run_timed_stage(
        "Steps 5-7: reproject, clean, and split lines",
        show_progress,
        _preprocess_osm_data,
        clipped_gdf,
        input_gdf,
        run_params["default_widths"],
        run_params["fallback_default_width"],
        provider=run_params.get("provider"),
        repair_protomaps_topology=run_params["repair_protomaps_topology"],
        protomaps_endpoint_snap_tolerance=run_params[
            "protomaps_endpoint_snap_tolerance"
        ],
        protomaps_endpoint_snap_max_angle=run_params[
            "protomaps_endpoint_snap_max_angle"
        ],
        show_progress=show_progress,
        _overall_progress=overall_progress,
    )
    topology_stats = splitted_gdf.attrs.get("protomaps_topology")
    if topology_stats is not None:
        run_params["protomaps_topology_stats"] = topology_stats

    _run_timed_stage(
        "Debug: save split-line layer",
        show_progress,
        _save_debug_layer_if_enabled,
        run_params["save_debug_layers"],
        splitted_gdf,
        "sidewalkreator_splitted_lines",
        _overall_progress=overall_progress,
    )

    # 8. Create protoblocks from the line network already prepared above.
    protoblocks_gdf = _run_timed_stage(
        "Step 8: generate protoblocks",
        show_progress,
        _generate_protoblocks_from_splitted_lines,
        input_gdf,
        splitted_gdf,
        renode_before_polygonize=run_params["renode_before_polygonize"],
        show_progress=show_progress,
        _overall_progress=overall_progress,
    )
    original_protoblocks_gdf = protoblocks_gdf.copy()
    logger.info("Step 8 complete")

    # 9. Extract POI data
    unified_pois_gdf, buildings_gdf = _run_timed_stage(
        "Step 9: extract POIs",
        show_progress,
        _extract_poi_data,
        cleaned_gdf,
        clipped_reproj_gdf,
        _overall_progress=overall_progress,
    )

    # 10. Draw sidewalks
    sidewalks_gdf = _run_timed_stage(
        "Step 10: draw sidewalks",
        show_progress,
        _draw_sidewalks,
        splitted_gdf,
        buildings_gdf,
        cleaned_gdf,
        run_params,
        _overall_progress=overall_progress,
    )

    # 11. Apply dead end removal
    sidewalks_gdf = _run_timed_stage(
        "Step 11: remove dead ends",
        show_progress,
        _apply_dead_end_removal,
        sidewalks_gdf,
        ignore_existing,
        run_params["dead_end_removal_iterations"],
        show_progress=show_progress,
        _overall_progress=overall_progress,
    )

    # 12-13. Generate crossings
    crossings_gdf = _run_timed_stage(
        "Steps 12-13: filter protoblocks and generate crossings",
        show_progress,
        _generate_crossings,
        splitted_gdf,
        sidewalks_gdf,
        protoblocks_gdf,
        run_params,
        ignore_existing,
        _overall_progress=overall_progress,
    )

    # 14-15. Finalize results
    splitted_sidewalks_gdf, kerbs_gdf, intersection_points_gdf = _run_timed_stage(
        "Steps 14-15: split sidewalks and generate kerbs",
        show_progress,
        _finalize_results,
        sidewalks_gdf,
        crossings_gdf,
        original_protoblocks_gdf,
        unified_pois_gdf,
        run_params,
        _overall_progress=overall_progress,
    )
    overall_progress.close()

    # Return all results as GeoDataFrames
    result = {
        "sidewalks": splitted_sidewalks_gdf,
        "crossings": crossings_gdf,
        "kerbs": kerbs_gdf,
        "protoblocks": original_protoblocks_gdf,
        "intersection_points": intersection_points_gdf,
        "pois": unified_pois_gdf,
        "input_area": input_gdf,
        "parameters": run_params,
    }

    logger.info("Process complete. Returning GeoDataFrames")
    return result
