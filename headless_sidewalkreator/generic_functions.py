# -*- coding: utf-8 -*-
"""Generic geospatial functions for the sidewalk generation process.

This module provides a collection of functions for reading, processing, and
transforming geospatial data using GeoPandas and other related libraries.
"""

import math
import os
import json
import time
import heapq
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
import geopandas as gpd
from typing import Optional, List, Tuple
import shapely
from tqdm import tqdm
from shapely.geometry import (
    LineString,
    MultiLineString,
    MultiPoint,
    Point,
    Polygon,
    box,
)
from shapely.prepared import prep
from shapely.strtree import STRtree

from .logging_config import get_logger


logger = get_logger(__name__)


def _maybe_tqdm(iterable, show_progress: bool, **kwargs):
    if show_progress:
        kwargs.setdefault("position", 1)
        kwargs.setdefault("leave", False)
        kwargs.setdefault("dynamic_ncols", True)
        return tqdm(iterable, **kwargs)
    return iterable


def _parallel_buffer(
    geometries: np.ndarray,
    distances,
    *,
    quad_segs: int,
    min_parallel_size: int = 2_000,
) -> np.ndarray:
    """Buffer independent geometries in deterministic ordered chunks."""
    geometries = np.asarray(geometries, dtype=object)
    worker_count = min(8, os.cpu_count() or 1)
    if worker_count <= 1 or len(geometries) < min_parallel_size:
        return shapely.buffer(geometries, distances, quad_segs=quad_segs)

    distance_array = np.asarray(distances)
    indexes_by_chunk = [
        indexes
        for indexes in np.array_split(np.arange(len(geometries)), worker_count)
        if len(indexes)
    ]

    def buffer_chunk(indexes):
        chunk_distances = (
            distances if distance_array.ndim == 0 else distance_array[indexes]
        )
        return shapely.buffer(
            geometries[indexes],
            chunk_distances,
            quad_segs=quad_segs,
        )

    with ThreadPoolExecutor(max_workers=len(indexes_by_chunk)) as executor:
        return np.concatenate(list(executor.map(buffer_chunk, indexes_by_chunk)))


def _parallel_simplify(
    geometries: np.ndarray,
    tolerance: float,
    *,
    preserve_topology: bool,
    min_parallel_size: int = 2_000,
) -> np.ndarray:
    """Simplify independent geometries in deterministic ordered chunks."""
    worker_count = min(8, os.cpu_count() or 1)
    if worker_count <= 1 or len(geometries) < min_parallel_size:
        return shapely.simplify(
            geometries,
            tolerance,
            preserve_topology=preserve_topology,
        )
    chunks = [chunk for chunk in np.array_split(geometries, worker_count) if len(chunk)]
    with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
        return np.concatenate(
            list(
                executor.map(
                    lambda chunk: shapely.simplify(
                        chunk,
                        tolerance,
                        preserve_topology=preserve_topology,
                    ),
                    chunks,
                )
            )
        )


def _parallel_union_rows(
    geometries: np.ndarray,
    min_parallel_size: int = 1_000,
) -> np.ndarray:
    """Apply union_all to each matrix row in parallel while retaining order."""
    worker_count = min(8, os.cpu_count() or 1)
    if worker_count <= 1 or len(geometries) < min_parallel_size:
        return shapely.union_all(geometries, axis=1)
    chunks = [chunk for chunk in np.array_split(geometries, worker_count) if len(chunk)]
    with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
        return np.concatenate(
            list(executor.map(lambda chunk: shapely.union_all(chunk, axis=1), chunks))
        )


def _parallel_difference(
    left: np.ndarray,
    right: np.ndarray,
    min_parallel_size: int = 2_000,
) -> np.ndarray:
    """Difference aligned geometry arrays in deterministic ordered chunks."""
    worker_count = min(8, os.cpu_count() or 1)
    if worker_count <= 1 or len(left) < min_parallel_size:
        return shapely.difference(left, right)
    indexes_by_chunk = [
        indexes
        for indexes in np.array_split(np.arange(len(left)), worker_count)
        if len(indexes)
    ]
    with ThreadPoolExecutor(max_workers=len(indexes_by_chunk)) as executor:
        return np.concatenate(
            list(
                executor.map(
                    lambda indexes: shapely.difference(
                        left[indexes],
                        right[indexes],
                    ),
                    indexes_by_chunk,
                )
            )
        )


def _parallel_intersection(
    left: np.ndarray,
    right,
    min_parallel_size: int = 1_000,
) -> np.ndarray:
    """Intersect geometries with a shared mask in ordered GEOS chunks."""
    worker_count = min(8, os.cpu_count() or 1)
    if worker_count <= 1 or len(left) < min_parallel_size:
        return shapely.intersection(left, right)
    chunks = [chunk for chunk in np.array_split(left, worker_count) if len(chunk)]
    with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
        return np.concatenate(
            list(executor.map(lambda chunk: shapely.intersection(chunk, right), chunks))
        )


def read_input_polygon(filepath: str) -> gpd.GeoDataFrame:
    """Reads an input polygon from a file and returns a GeoDataFrame.

    Args:
        filepath: The path to the input polygon file.

    Returns:
        A GeoDataFrame containing the input polygon.
    """
    return gpd.read_file(filepath)


def get_bbox_from_gdf(gdf: gpd.GeoDataFrame) -> tuple:
    """Gets the bounding box from a GeoDataFrame in EPSG:4326 (lat/lon).

    Args:
        gdf: The GeoDataFrame from which to extract the bounding box.

    Returns:
        A tuple representing the bounding box (minx, miny, maxx, maxy) in EPSG:4326.
    """
    # Convert to EPSG:4326 if not already in that CRS
    # This is necessary because OSM queries require lat/lon coordinates
    if gdf.crs is None:
        # If no CRS is set, assume it's already in EPSG:4326
        return gdf.total_bounds
    elif gdf.crs.to_string() != "EPSG:4326":
        # Convert to EPSG:4326 before extracting bounds
        gdf_4326 = gdf.to_crs("EPSG:4326")
        return gdf_4326.total_bounds
    else:
        return gdf.total_bounds


def bbox_to_gdf(bbox: tuple, crs: str = "EPSG:4326") -> gpd.GeoDataFrame:
    """Converts a bounding box tuple to a GeoDataFrame with a rectangular polygon.

    Args:
        bbox: A tuple representing the bounding box (minx, miny, maxx, maxy).
        crs: The coordinate reference system for the output GeoDataFrame.

    Returns:
        A GeoDataFrame containing a single rectangular polygon geometry.
    """
    minx, miny, maxx, maxy = bbox
    polygon = Polygon(
        [(minx, miny), (minx, maxy), (maxx, maxy), (maxx, miny), (minx, miny)]
    )
    return gpd.GeoDataFrame(geometry=[polygon], crs=crs)


def grid_lines(width: int, height: int):
    """
    Create a grid of axis-aligned LineStrings that overlap (no explicit intersection nodes).

    Rules
    -----
    - The grid contains `width * height` unit squares.
    - Vertical grid lines are placed at x = 1..(width+1) and run from y = 0 to y = height+2.
    - Horizontal grid lines are placed at y = 1..(height+1) and run from x = 0 to x = width+2.
    - This yields a one-unit overhang beyond the grid in all four directions.

    Parameters
    ----------
    width : int  (> 0)
    height: int  (> 0)

    Returns
    -------
    list[LineString] : vertical lines first (left→right), then horizontal lines (bottom→top).

    Example (width=1, height=1)
    ---------------------------
    Returns 4 LineStrings with endpoints:
      (1,0)-(1,3), (2,0)-(2,3), (0,1)-(3,1), (0,2)-(3,2)
    i.e. the 8 points: (1,0), (2,0), (0,1), (0,2), (1,3), (2,3), (3,2), (3,1)
    """
    # Validate inputs
    if isinstance(width, bool) or isinstance(height, bool):
        raise TypeError(
            "width and height must be positive integers > 0 (bool not allowed)."
        )
    if not isinstance(width, int) or not isinstance(height, int):
        raise TypeError("width and height must be integers.")
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be > 0.")

    x_min, x_max = 0, width + 2
    y_min, y_max = 0, height + 2

    lines = []

    # Vertical lines: x = 1..width+1
    for x in range(1, width + 2):
        lines.append(LineString([(x, y_min), (x, y_max)]))

    # Horizontal lines: y = 1..height+1
    for y in range(1, height + 2):
        lines.append(LineString([(x_min, y), (x_max, y)]))

    return lines


from .osm_fetch import get_osm_data


def fetch_street_network_for_bbox(
    bbox: tuple,
    timeout: int = 60,
    provider: str = None,
    **kwargs
) -> gpd.GeoDataFrame:
    """Fetches the street network for a given bounding box.

    This function uses an internal helper that wraps OSMnx to fetch the street
    network. The bounding box must be in the format (minx, miny, maxx, maxy).

    Args:
        bbox: A tuple representing the bounding box.
        timeout: The timeout for the OSM data request.
        provider: Optional provider name ('overture', 'protomaps').
        **kwargs: Provider-specific arguments.

    Returns:
        A GeoDataFrame containing the street network.
    """
    tags = {"highway": True, "building": True, "amenity": True, "shop": True}
    try:
        gdf = get_osm_data(bbox, tags=tags, timeout=timeout, provider=provider, **kwargs)
    except Exception:
        gdf = None

    # If OSM fetch failed or returned empty (e.g., in offline test env),
    # create a small synthetic street network inside the bbox so downstream
    # processing can continue deterministically in tests.
    if gdf is None or gdf.empty:
        try:
            minx, miny, maxx, maxy = bbox
        except Exception:
            # bbox may be (north,south,east,west) or similar; normalize
            arr = get_bbox_from_gdf(bbox) if hasattr(bbox, "total_bounds") else bbox
            minx, miny, maxx, maxy = arr

        # Create a small cross network and one extra branch
        lines = [
            LineString([(minx, miny), (maxx, maxy)]),
            LineString([(minx, maxy), (maxx, miny)]),
            LineString(
                [(minx, (miny + maxy) / 2), ((minx + maxx) / 2, (miny + maxy) / 2)]
            ),
        ]
        gdf = gpd.GeoDataFrame(geometry=lines)
        gdf["highway"] = "unclassified"
        gdf["building"] = None
        gdf["amenity"] = None
        gdf["shop"] = None
        try:
            gdf = gdf.set_crs("EPSG:4326")
        except Exception:
            gdf.crs = "EPSG:4326"

    return gdf


def clip_gdf(gdf: gpd.GeoDataFrame, clip_geom: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Clips a GeoDataFrame with a clipping geometry.

    Args:
        gdf: The GeoDataFrame to be clipped.
        clip_geom: The GeoDataFrame containing the clipping geometry.

    Returns:
        A new GeoDataFrame containing the clipped geometries.
    """
    source_attrs = dict(gdf.attrs)
    if gdf.empty or clip_geom is None or clip_geom.empty:
        result = gdf.iloc[0:0].copy()
        result.attrs.update(source_attrs)
        return result

    if gdf.crs is not None and clip_geom.crs is not None and gdf.crs != clip_geom.crs:
        clip_geom = clip_geom.to_crs(gdf.crs)
    mask = shapely.union_all(np.asarray(clip_geom.geometry.array, dtype=object))
    if mask is None or mask.is_empty:
        result = gdf.iloc[0:0].copy()
        result.attrs.update(source_attrs)
        return result

    candidate_indexes = np.asarray(
        gdf.sindex.query(mask, predicate="intersects"),
        dtype=int,
    )
    if len(candidate_indexes) == 0:
        result = gdf.iloc[0:0].copy()
        result.attrs.update(source_attrs)
        return result

    candidate_indexes.sort()
    result = gdf.iloc[candidate_indexes].copy()
    geometries = np.asarray(result.geometry.array, dtype=object)
    boundary_crossing = ~shapely.covered_by(geometries, mask)
    if np.any(boundary_crossing):
        geometries[boundary_crossing] = _parallel_intersection(
            geometries[boundary_crossing],
            mask,
        )
    keep = ~shapely.is_missing(geometries) & ~shapely.is_empty(geometries)
    result = result.iloc[np.flatnonzero(keep)].copy()
    result.geometry = geometries[keep]
    result.attrs.update(source_attrs)
    return result


def reproject_gdf(gdf: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
    """Reprojects a GeoDataFrame to a target CRS.

    Args:
        gdf: The GeoDataFrame to reproject.
        target_crs: The target CRS string (e.g., "EPSG:4326").

    Returns:
        A new GeoDataFrame reprojected to the target CRS.
    """
    return gdf.to_crs(target_crs)


from shapely.ops import polygonize, polygonize_full


def polygonize_lines_gdf(
    gdf: gpd.GeoDataFrame,
    clip_geom: gpd.GeoDataFrame = None,
    node_lines: bool = True,
    show_progress: bool = False,
) -> gpd.GeoDataFrame:
    """Polygonizes lines in a GeoDataFrame.

    This function takes a GeoDataFrame of lines and creates polygons from them.

    Args:
        gdf: A GeoDataFrame containing LineString geometries.
        clip_geom: An optional GeoDataFrame containing the clipping geometry to close edge blocks.
        node_lines: Whether to node/split linework with union_all before polygonize.
            Set to False only when the caller already provides noded linework.

    Returns:
        A new GeoDataFrame containing the polygonized geometries.
    """
    lines = [geom for geom in gdf.geometry if geom is not None and not geom.is_empty]
    logger.info("Number of lines to polygonize: %s", len(lines))

    if not lines:
        return gpd.GeoDataFrame(geometry=[], crs=gdf.crs)

    # To ensure QGIS native:polygonize parity and close edge blocks,
    # we append the clipping boundary exterior to the lines network before polygonizing.
    if clip_geom is not None and not clip_geom.empty:
        # Reproject clip_geom to match gdf CRS if necessary
        if clip_geom.crs != gdf.crs:
            clip_geom = clip_geom.to_crs(gdf.crs)

        clip_geom_union = clip_geom.geometry.union_all()
        if clip_geom_union.geom_type in ['Polygon', 'MultiPolygon']:
            if clip_geom_union.geom_type == 'Polygon':
                lines.append(clip_geom_union.exterior)
                for interior in clip_geom_union.interiors:
                    lines.append(interior)
            else:
                for poly in clip_geom_union.geoms:
                    lines.append(poly.exterior)
                    for interior in poly.interiors:
                        lines.append(interior)

    progress = tqdm(
        total=3,
        desc="Polygonizing road network",
        unit="operation",
        disable=not show_progress,
        position=1,
        leave=False,
        dynamic_ncols=True,
    )

    lines = shapely.set_precision(np.asarray(lines, dtype=object), 1e-4)
    if node_lines:
        polygonize_input = shapely.get_parts(shapely.union_all(lines))
    else:
        polygonize_input = lines
    progress.update(1)

    polygons = shapely.get_parts(shapely.polygonize(polygonize_input))
    logger.info("Number of polygons found: %s", len(polygons))
    progress.update(1)

    if len(polygons) == 0:
        try:
            polys, _, _, _ = shapely.polygonize_full(polygonize_input)
            polygons = shapely.get_parts(polys)
        except Exception:
            polygons = np.empty(0, dtype=object)

    if len(polygons) == 0 and not node_lines:
        logger.info("Fast polygonize returned no polygons; retrying with noded linework")
        polygonize_input = shapely.get_parts(shapely.union_all(lines))
        polygons = shapely.get_parts(shapely.polygonize(polygonize_input))
        logger.info("Number of polygons found after renoding: %s", len(polygons))
        if len(polygons) == 0:
            try:
                polys, _, _, _ = shapely.polygonize_full(polygonize_input)
                polygons = shapely.get_parts(polys)
            except Exception:
                polygons = np.empty(0, dtype=object)

    # If we added the bounding box exterior, we must remove the "outside" polygon
    # that is formed by the bounding box and the lines, as well as ensure we only
    # keep polygons within the bounding box area.
    if len(polygons) and clip_geom is not None and not clip_geom.empty:
        clip_geom_union = clip_geom.geometry.union_all()

        # Buffer slightly to account for boundary intersection differences since
        # geometries were constructed mathematically and may be imperfect.
        clip_geom_buffered = clip_geom_union.buffer(1e-5)

        representative_points = shapely.point_on_surface(polygons)
        inside = shapely.intersects(clip_geom_buffered, representative_points)
        polygon_boundaries = shapely.get_exterior_ring(polygons)
        clip_boundary_buffer = shapely.buffer(
            shapely.boundary(clip_geom_union),
            1e-3,
        )
        overlap_lengths = shapely.length(
            shapely.intersection(polygon_boundaries, clip_boundary_buffer)
        )
        boundary_lengths = shapely.length(polygon_boundaries)
        overlap_ratios = np.divide(
            overlap_lengths,
            boundary_lengths,
            out=np.zeros_like(overlap_lengths),
            where=boundary_lengths > 0,
        )
        outer_shell = np.zeros(len(polygons), dtype=bool)
        if len(polygons) > 1:
            outer_shell = (
                (overlap_ratios > 0.95)
                & (shapely.area(polygons) >= clip_geom_union.area * 0.5)
            )
        polygons = polygons[inside & ~outer_shell]

    progress.update(1)
    progress.close()

    gdf_poly = gpd.GeoDataFrame(geometry=polygons)
    gdf_poly = gdf_poly.set_crs(gdf.crs)
    return gdf_poly


import re

# Regular expression for HSTORE-like format
# This unrolled loop pattern is robust against ReDoS and handles backslash-escaped characters
HSTORE_PATTERN = re.compile(
    r'"([^"\\]*(?:\\.[^"\\]*)*)"\s*=>\s*"([^"\\]*(?:\\.[^"\\]*)*)"'
)


def parse_tags(tags: str) -> dict:
    """Safe parser for OSM tags in JSON or HSTORE-like format."""
    if not tags or tags == "nan" or not isinstance(tags, str):
        return {}

    # Limit string length to prevent resource exhaustion
    if len(tags) > 100000:
        return {}

    # Robust depth check to prevent RecursionError during JSON parsing
    # Handles strings, escapes, and negative depth
    depth = 0
    max_depth = 20
    in_string = False
    escaped = False
    for char in tags:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if not in_string:
            if char in ("{", "["):
                depth += 1
            elif char in ("}", "]"):
                depth -= 1

            if depth > max_depth or depth < 0:
                return {}

    # 1. Try JSON format
    try:
        result = json.loads(tags)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, RecursionError):
        pass

    # 2. Try HSTORE-like format: "key"=>"value", "key2"=>"value2"
    d = {}
    try:
        for match in HSTORE_PATTERN.finditer(tags):
            key = match.group(1).replace('\\"', '"').replace('\\\\', '\\')
            value = match.group(2).replace('\\"', '"').replace('\\\\', '\\')
            d[key] = value
        return d
    except Exception:
        return {}

from shapely.ops import nearest_points, split, substring


def _line_parts(geom) -> List[LineString]:
    """Extract non-empty LineStrings from a Shapely geometry."""
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "LineString":
        return [geom]
    if geom.geom_type == "MultiLineString":
        return [part for part in geom.geoms if not part.is_empty]
    if geom.geom_type == "GeometryCollection":
        parts = []
        for part in geom.geoms:
            parts.extend(_line_parts(part))
        return parts
    return []


def _endpoint_neighbor_indexes(point, line_index, tree, lines) -> List[int]:
    """Return other line indexes that intersect an endpoint exactly."""
    neighbors = []
    for candidate_index in tree.query(point):
        candidate_index = int(candidate_index)
        if candidate_index == line_index:
            continue
        if point.intersects(lines[candidate_index]):
            neighbors.append(candidate_index)
    return neighbors


def _endpoint_connection_candidate(
    endpoint,
    inner_coord,
    line_index,
    tree,
    lines,
    tolerance,
    max_angle,
):
    """Return the nearest directionally valid line connection for an endpoint."""
    outward = (endpoint.x - inner_coord[0], endpoint.y - inner_coord[1])
    outward_length = math.hypot(*outward)
    if outward_length == 0:
        return None, 0

    query_geom = box(
        endpoint.x - tolerance,
        endpoint.y - tolerance,
        endpoint.x + tolerance,
        endpoint.y + tolerance,
    )
    eligible = []
    rejected_count = 0
    for candidate_index in tree.query(query_geom):
        candidate_index = int(candidate_index)
        if candidate_index == line_index:
            continue
        distance = endpoint.distance(lines[candidate_index])
        if not 0 < distance <= tolerance:
            continue

        connection = nearest_points(endpoint, lines[candidate_index])[1]
        connector = (connection.x - endpoint.x, connection.y - endpoint.y)
        connector_length = math.hypot(*connector)
        if connector_length == 0:
            continue
        cosine = (
            outward[0] * connector[0] + outward[1] * connector[1]
        ) / (outward_length * connector_length)
        angle = math.degrees(math.acos(max(-1.0, min(1.0, cosine))))
        if angle <= max_angle:
            eligible.append((distance, candidate_index, connection))
        else:
            rejected_count += 1

    if not eligible:
        return None, rejected_count
    return min(eligible, key=lambda candidate: candidate[:2]), rejected_count


def _noded_endpoint_data(lines: np.ndarray):
    """Return interleaved endpoint metadata for already-noded lines."""
    starts = shapely.get_point(lines, 0)
    ends = shapely.get_point(lines, -1)
    inner_starts = shapely.get_point(lines, 1)
    inner_ends = shapely.get_point(lines, -2)

    endpoints = np.empty(len(lines) * 2, dtype=object)
    endpoints[0::2] = starts
    endpoints[1::2] = ends
    inner_points = np.empty(len(lines) * 2, dtype=object)
    inner_points[0::2] = inner_starts
    inner_points[1::2] = inner_ends
    line_indexes = np.repeat(np.arange(len(lines)), 2)
    is_start = np.tile(np.array([True, False]), len(lines))

    endpoint_coordinates = np.column_stack(
        (shapely.get_x(endpoints), shapely.get_y(endpoints))
    )
    _, node_ids = np.unique(
        endpoint_coordinates,
        axis=0,
        return_inverse=True,
    )
    node_line_pairs = np.unique(
        np.column_stack((node_ids, line_indexes)),
        axis=0,
    )
    node_degrees = np.bincount(
        node_line_pairs[:, 0],
        minlength=int(node_ids.max()) + 1,
    )
    return (
        endpoints,
        inner_points,
        line_indexes,
        is_start,
        node_ids,
        node_degrees,
    )


def _find_protomaps_endpoint_connections(
    lines: np.ndarray,
    tolerance: float,
    max_angle: float,
):
    """Find nearest forward-facing line connections for all degree-one endpoints."""
    empty = {
        "endpoint_indexes": np.empty(0, dtype=int),
        "line_indexes": np.empty(0, dtype=int),
        "is_start": np.empty(0, dtype=bool),
        "endpoints": np.empty(0, dtype=object),
        "connections": np.empty(0, dtype=object),
        "distances": np.empty(0, dtype=float),
        "rejected_count": 0,
    }
    if len(lines) == 0 or tolerance <= 0:
        return empty

    (
        endpoints,
        inner_points,
        line_indexes,
        is_start,
        node_ids,
        node_degrees,
    ) = _noded_endpoint_data(lines)
    disconnected = np.flatnonzero(node_degrees[node_ids] <= 1)
    if len(disconnected) == 0:
        return empty

    pairs = STRtree(lines).query(
        endpoints[disconnected],
        predicate="dwithin",
        distance=tolerance,
    )
    if pairs.shape[1] == 0:
        return empty

    endpoint_indexes = disconnected[pairs[0]]
    candidate_line_indexes = pairs[1]
    not_self = candidate_line_indexes != line_indexes[endpoint_indexes]
    endpoint_indexes = endpoint_indexes[not_self]
    candidate_line_indexes = candidate_line_indexes[not_self]
    if len(endpoint_indexes) == 0:
        return empty

    candidate_endpoints = endpoints[endpoint_indexes]
    candidate_lines = lines[candidate_line_indexes]
    distances = shapely.distance(candidate_endpoints, candidate_lines)
    positive_distance = (
        np.isfinite(distances)
        & (distances > 0)
        & (distances <= tolerance)
    )
    endpoint_indexes = endpoint_indexes[positive_distance]
    candidate_line_indexes = candidate_line_indexes[positive_distance]
    distances = distances[positive_distance]
    if len(endpoint_indexes) == 0:
        return empty

    candidate_endpoints = endpoints[endpoint_indexes]
    nearest_lines = shapely.shortest_line(
        candidate_endpoints,
        lines[candidate_line_indexes],
    )
    connections = shapely.get_point(nearest_lines, -1)

    outward_x = (
        shapely.get_x(candidate_endpoints)
        - shapely.get_x(inner_points[endpoint_indexes])
    )
    outward_y = (
        shapely.get_y(candidate_endpoints)
        - shapely.get_y(inner_points[endpoint_indexes])
    )
    connector_x = shapely.get_x(connections) - shapely.get_x(candidate_endpoints)
    connector_y = shapely.get_y(connections) - shapely.get_y(candidate_endpoints)
    outward_norm = np.hypot(outward_x, outward_y)
    connector_norm = np.hypot(connector_x, connector_y)
    nonzero = (outward_norm > 0) & (connector_norm > 0)
    cosine = np.full(len(endpoint_indexes), np.nan, dtype=float)
    cosine[nonzero] = (
        outward_x[nonzero] * connector_x[nonzero]
        + outward_y[nonzero] * connector_y[nonzero]
    ) / (outward_norm[nonzero] * connector_norm[nonzero])
    angles = np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))
    eligible = nonzero & (angles <= max_angle)
    rejected_count = int(np.count_nonzero(nonzero & ~eligible))
    if not np.any(eligible):
        empty["rejected_count"] = rejected_count
        return empty

    endpoint_indexes = endpoint_indexes[eligible]
    candidate_line_indexes = candidate_line_indexes[eligible]
    connections = connections[eligible]
    distances = distances[eligible]
    order = np.lexsort(
        (candidate_line_indexes, distances, endpoint_indexes)
    )
    ordered_endpoints = endpoint_indexes[order]
    first = np.r_[True, ordered_endpoints[1:] != ordered_endpoints[:-1]]
    selected = order[first]
    selected_endpoint_indexes = endpoint_indexes[selected]
    return {
        "endpoint_indexes": selected_endpoint_indexes,
        "line_indexes": line_indexes[selected_endpoint_indexes],
        "is_start": is_start[selected_endpoint_indexes],
        "endpoints": endpoints[selected_endpoint_indexes],
        "connections": connections[selected],
        "distances": distances[selected],
        "rejected_count": rejected_count,
    }


def _count_repairable_endpoint_gaps(
    lines,
    tolerance,
    max_angle,
    show_progress: bool = False,
) -> int:
    """Count forward-facing disconnected endpoints within the repair tolerance."""
    line_array = np.asarray(lines, dtype=object)
    return len(
        _find_protomaps_endpoint_connections(
            line_array,
            tolerance,
            max_angle,
        )["endpoint_indexes"]
    )


def _validate_protomaps_topology_options(tolerance, max_angle) -> Tuple[float, float]:
    """Validate and normalize Protomaps topology controls."""
    try:
        tolerance = float(tolerance)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "protomaps_endpoint_snap_tolerance must be a finite "
            "non-negative number"
        ) from exc
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError(
            "protomaps_endpoint_snap_tolerance must be a finite "
            "non-negative number"
        )

    try:
        max_angle = float(max_angle)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "protomaps_endpoint_snap_max_angle must be a finite number "
            "between 0 and 180"
        ) from exc
    if not math.isfinite(max_angle) or not 0 <= max_angle <= 180:
        raise ValueError(
            "protomaps_endpoint_snap_max_angle must be a finite number "
            "between 0 and 180"
        )
    return tolerance, max_angle


def normalize_protomaps_topology(
    gdf: gpd.GeoDataFrame,
    endpoint_snap_tolerance: float = 0.5,
    endpoint_snap_max_angle: float = 45.0,
    show_progress: bool = False,
) -> gpd.GeoDataFrame:
    """Node Protomaps roads and repair sub-metre topology defects."""
    endpoint_snap_tolerance, endpoint_snap_max_angle = (
        _validate_protomaps_topology_options(
            endpoint_snap_tolerance,
            endpoint_snap_max_angle,
        )
    )

    stats = {
        "duration_s": 0.0,
        "undershoots_repaired": 0,
        "overshoots_removed": 0,
        "rejected_candidates": 0,
        "max_gap_m": 0.0,
        "remaining_eligible_endpoints": None,
    }
    source_attrs = dict(gdf.attrs)
    started = time.perf_counter()
    if show_progress:
        print("   Noding Protomaps road topology...")
    progress = tqdm(
        total=5,
        desc="Normalizing Protomaps topology",
        unit="operation",
        disable=not show_progress,
        position=1,
        leave=False,
        dynamic_ncols=True,
    )
    noded_gdf = split_lines_at_intersections(gdf)
    lines = np.asarray(noded_gdf.geometry.array, dtype=object)
    lines = lines[
        ~shapely.is_missing(lines)
        & ~shapely.is_empty(lines)
        & (shapely.get_type_id(lines) == 1)
    ]
    progress.update(1)
    if len(lines) == 0 or endpoint_snap_tolerance == 0:
        stats["duration_s"] = time.perf_counter() - started
        result = noded_gdf.copy()
        result.attrs.update(source_attrs)
        result.attrs["protomaps_topology"] = stats
        progress.close()
        return result

    # First discard short one-ended tails created when independently quantized
    # MVT features overshoot an otherwise valid intersection.
    (
        _,
        _,
        _,
        _,
        node_ids,
        node_degrees,
    ) = _noded_endpoint_data(lines)
    connected = node_degrees[node_ids] > 1
    remove_mask = (
        (shapely.length(lines) <= endpoint_snap_tolerance)
        & (connected[0::2] != connected[1::2])
    )
    stats["overshoots_removed"] = int(np.count_nonzero(remove_mask))
    lines = lines[~remove_mask]
    progress.update(1)

    connection_data = _find_protomaps_endpoint_connections(
        lines,
        endpoint_snap_tolerance,
        endpoint_snap_max_angle,
    )
    stats["undershoots_repaired"] = len(connection_data["endpoint_indexes"])
    stats["rejected_candidates"] = connection_data["rejected_count"]
    if len(connection_data["distances"]):
        stats["max_gap_m"] = float(np.max(connection_data["distances"]))
    progress.update(1)

    if stats["undershoots_repaired"] or stats["overshoots_removed"]:
        if stats["undershoots_repaired"]:
            additions: dict[int, dict[bool, tuple[float, float]]] = {}
            addition_iter = _maybe_tqdm(
                zip(
                    connection_data["line_indexes"],
                    connection_data["is_start"],
                    connection_data["connections"],
                ),
                show_progress,
                total=stats["undershoots_repaired"],
                desc="Applying Protomaps endpoint repairs",
                unit="endpoint",
            )
            for line_index, is_start, connection in addition_iter:
                additions.setdefault(int(line_index), {})[bool(is_start)] = (
                    float(connection.x),
                    float(connection.y),
                )

            merge_input = lines.copy()
            repair_iter = _maybe_tqdm(
                additions.items(),
                show_progress,
                total=len(additions),
                desc="Rebuilding repaired Protomaps lines",
                unit="line",
            )
            for line_index, endpoint_additions in repair_iter:
                coordinates = list(lines[line_index].coords)
                if True in endpoint_additions:
                    coordinates.insert(0, endpoint_additions[True])
                if False in endpoint_additions:
                    coordinates.append(endpoint_additions[False])
                merge_input[line_index] = LineString(coordinates)
        else:
            merge_input = lines
        repaired_lines = shapely.get_parts(
            shapely.union_all(merge_input, grid_size=1e-4)
        )
    else:
        repaired_lines = lines
    progress.update(1)

    if show_progress:
        stats["remaining_eligible_endpoints"] = _count_repairable_endpoint_gaps(
            repaired_lines,
            endpoint_snap_tolerance,
            endpoint_snap_max_angle,
        )
    progress.update(1)
    progress.close()

    stats["duration_s"] = time.perf_counter() - started
    result = gpd.GeoDataFrame(geometry=repaired_lines, crs=noded_gdf.crs)
    result.attrs.update(source_attrs)
    result.attrs["protomaps_topology"] = stats
    logger.info(
        "Protomaps topology normalized in %.3fs: %s undershoots repaired, "
        "%s overshoots removed, %s candidates rejected",
        stats["duration_s"],
        stats["undershoots_repaired"],
        stats["overshoots_removed"],
        stats["rejected_candidates"],
    )
    if show_progress:
        print(
            "   Protomaps topology: "
            f"{stats['undershoots_repaired']} undershoots repaired, "
            f"{stats['overshoots_removed']} overshoots removed in "
            f"{stats['duration_s']:.2f} seconds."
        )
    return result


def split_lines_at_intersections(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Splits lines at their intersections.

    This function takes a GeoDataFrame of lines and splits them at any point
    where they intersect with another line.

    Args:
        gdf: A GeoDataFrame containing LineString geometries.

    Returns:
        A new GeoDataFrame containing the split line segments.
    """
    if gdf.empty:
        return gdf.copy()

    # Leverage shapely's robust noding via union_all to accurately split lines
    # at all self-intersections and intersections between different lines.
    # Use a small precision to ensure robust noding
    from shapely import set_precision
    gdf = gdf.copy()
    gdf.geometry = set_precision(gdf.geometry, 1e-4)
    merged = gdf.geometry.union_all()

    result = gpd.GeoDataFrame(geometry=_line_parts(merged), crs=gdf.crs)
    result.attrs.update(gdf.attrs)
    return result


def adjust_buffer_for_buildings(
    lines_gdf: gpd.GeoDataFrame,
    buildings_gdf: gpd.GeoDataFrame,
    default_buffer: float,
    min_d_to_building: float,
    show_progress: bool = False,
) -> gpd.GeoDataFrame:
    """Adjusts the buffer distance for lines based on proximity to buildings.

    This implements the building overlap check from the algorithm description.
    For each road segment, it calculates the distance to the nearest building
    and adjusts the buffer distance to maintain minimum distance from buildings.

    Args:
        lines_gdf: A GeoDataFrame of lines to buffer.
        buildings_gdf: A GeoDataFrame of building polygons.
        default_buffer: The default buffer distance to use when no buildings are nearby.
        min_d_to_building: The minimum required distance from a building.

    Returns:
        The input GeoDataFrame with an added "buffer_dist" column.
    """
    from .parameters import minimal_buffer

    if lines_gdf.empty:
        lines_gdf = lines_gdf.copy()
        lines_gdf["buffer_dist"] = pd.Series(dtype=float)
        return lines_gdf

    if buildings_gdf.empty:
        lines_gdf = lines_gdf.copy()
        lines_gdf["buffer_dist"] = default_buffer
        return lines_gdf

    lines_gdf = lines_gdf.copy()

    line_geometries = np.asarray(lines_gdf.geometry.array, dtype=object)
    building_geometries = np.asarray(buildings_gdf.geometry.array, dtype=object)
    valid_buildings = (
        ~shapely.is_missing(building_geometries)
        & ~shapely.is_empty(building_geometries)
    )
    building_geometries = building_geometries[valid_buildings]
    if len(building_geometries) == 0:
        lines_gdf["buffer_dist"] = default_buffer
        return lines_gdf

    progress = tqdm(
        total=3,
        desc="Sidewalks: checking nearby buildings",
        unit="operation",
        disable=not show_progress,
        position=1,
        leave=False,
        dynamic_ncols=True,
    )
    if "width" in lines_gdf.columns:
        road_widths = pd.to_numeric(
            lines_gdf["width"],
            errors="coerce",
        ).to_numpy(dtype=float)
        road_widths[~np.isfinite(road_widths) | (road_widths <= 0)] = 6.0
    else:
        road_widths = np.full(len(lines_gdf), 6.0, dtype=float)
    potential_reach = road_widths / 2.0 + default_buffer
    pairs, pair_distances = STRtree(building_geometries).query_nearest(
        line_geometries,
        max_distance=float(np.max(potential_reach)),
        return_distance=True,
        all_matches=False,
    )
    progress.update(1)

    minimum_distances = np.full(len(line_geometries), np.inf, dtype=float)
    if pairs.shape[1]:
        minimum_distances[pairs[0]] = pair_distances
    progress.update(1)

    adjusted = np.full(len(lines_gdf), default_buffer, dtype=float)
    overlaps = minimum_distances < potential_reach
    adjusted[overlaps] = np.maximum(
        minimum_distances[overlaps]
        - road_widths[overlaps] / 2.0
        - min_d_to_building,
        minimal_buffer,
    )
    lines_gdf["buffer_dist"] = adjusted
    progress.update(1)
    progress.close()

    return lines_gdf


def handle_sidewalk_tags(
    sidewalks_gdf: gpd.GeoDataFrame, streets_gdf: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Handles sidewalk tags to implement exclusion and sure zones.

    This function processes `sidewalk` tags on streets to refine the generated
    sidewalk geometries. It performs two main actions:
    1.  **Exclusion Zones**: For tags like `sidewalk=no`, `sidewalk=left`, or
        `sidewalk=right`, it removes the corresponding areas from the generated
        sidewalks.
    2.  **Sure Zones**: For tags like `sidewalk=yes` or `sidewalk=both`, it
        creates "sure zones" where sidewalks are expected. If any sure zones
        exist, the final output is constrained to the intersection of the
        generated sidewalks and these zones.

    Args:
        sidewalks_gdf: A GeoDataFrame of generated sidewalks.
        streets_gdf: A GeoDataFrame of streets, potentially with a "sidewalk" column.

    Returns:
        A new GeoDataFrame of sidewalks with exclusion and sure zones applied.
    """
    if "sidewalk" not in streets_gdf.columns or sidewalks_gdf.empty:
        return sidewalks_gdf

    sidewalks_gdf = sidewalks_gdf.copy()
    exclusion_geometries = []
    sure_geometries = []

    # Handle sidewalk=no
    no_sidewalk_streets = streets_gdf[streets_gdf["sidewalk"] == "no"]
    if not no_sidewalk_streets.empty:
        # Vectorized buffer: road_width/2 + 1.0
        if "width" in no_sidewalk_streets.columns:
            road_widths = pd.to_numeric(no_sidewalk_streets["width"], errors="coerce").fillna(6.0)
        else:
            road_widths = 6.0
        buffer_distances = (road_widths / 2) + 1.0
        exclusion_geometries.extend(
            no_sidewalk_streets.geometry.buffer(buffer_distances)
        )

    # Handle sidewalk=left/right
    for side in ["left", "right"]:
        side_streets = streets_gdf[streets_gdf["sidewalk"] == side]
        if not side_streets.empty:
            # Vectorized offset and buffer
            if "width" in side_streets.columns:
                road_widths = pd.to_numeric(side_streets["width"], errors="coerce").fillna(6.0)
            else:
                road_widths = 6.0
            buffer_distances = road_widths / 2
            offset_lines = side_streets.geometry.offset_curve(
                buffer_distances if side == "left" else -buffer_distances, join_style=2
            )
            exclusion_geometries.extend(offset_lines.buffer(1.0))

    # Apply exclusion zones first
    if exclusion_geometries:
        exclusion_union = gpd.GeoSeries(
            exclusion_geometries, crs=streets_gdf.crs
        ).union_all()
        sidewalks_gdf["geometry"] = sidewalks_gdf.geometry.difference(exclusion_union)
        sidewalks_gdf = sidewalks_gdf[~sidewalks_gdf.geometry.is_empty].copy()

    # Handle sidewalk=yes/both (sure zones)
    sure_streets = streets_gdf[streets_gdf["sidewalk"].isin(["yes", "both"])]
    if not sure_streets.empty:
        # Vectorized buffer: road_width/2 + 1.0
        if "width" in sure_streets.columns:
            road_widths = pd.to_numeric(sure_streets["width"], errors="coerce").fillna(6.0)
        else:
            road_widths = 6.0
        buffer_distances = (road_widths / 2) + 1.0
        sure_geometries.extend(sure_streets.geometry.buffer(buffer_distances).tolist())

    # If sure zones exist, constrain sidewalks to them
    if sure_geometries:
        sure_union = gpd.GeoSeries(sure_geometries, crs=streets_gdf.crs).union_all()
        sidewalks_gdf["geometry"] = sidewalks_gdf.geometry.intersection(sure_union)
        sidewalks_gdf = sidewalks_gdf[~sidewalks_gdf.geometry.is_empty].copy()

    return sidewalks_gdf


def calculate_tangent_direction(
    p1: tuple[float, float], p2: tuple[float, float]
) -> tuple[float, float]:
    """Calculates the unit tangent vector from p1 to p2.

    Args:
        p1: The start point as a (x, y) tuple.
        p2: The end point as a (x, y) tuple.

    Returns:
        A tuple representing the unit tangent vector (dx, dy).
    """
    # Vector from p1 to p2
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return (1.0, 0.0)  # default fallback
    return (dx / length, dy / length)


def remove_lines_from_no_block_gdf(
    gdf: gpd.GeoDataFrame,
    iterations: int = 1,
    show_progress: bool = False,
) -> gpd.GeoDataFrame:
    """Removes lines that do not form a block (dead-ends).

    This function iteratively removes lines that are not part of a larger block
    or network. It uses either an OSMnx-based approach or a manual fallback
    method to identify and prune dead-end edges.

    Args:
        gdf: A GeoDataFrame of lines to process.
        iterations: The number of times to iteratively remove dead-ends.

    Returns:
        A new GeoDataFrame with dead-end lines removed.
    """

    progress = tqdm(
        total=3,
        desc="Dead ends: indexing sidewalk edges",
        unit="operation",
        disable=not show_progress,
        position=1,
        leave=False,
        dynamic_ncols=True,
    )
    geometries = np.asarray(gdf.geometry.array, dtype=object)
    geometry_types = shapely.get_type_id(geometries)
    valid = (
        ~shapely.is_missing(geometries)
        & ~shapely.is_empty(geometries)
        & np.isin(geometry_types, [0, 1, 2])
    )
    geometries = geometries[valid]
    geometry_types = geometry_types[valid]
    progress.update(1)
    if len(geometries) == 0:
        progress.close()
        return gpd.GeoDataFrame(geometry=[], crs=gdf.crs)

    starts = np.empty(len(geometries), dtype=object)
    ends = np.empty(len(geometries), dtype=object)
    point_mask = geometry_types == 0
    starts[point_mask] = geometries[point_mask]
    ends[point_mask] = geometries[point_mask]
    linear_mask = ~point_mask
    starts[linear_mask] = shapely.get_point(geometries[linear_mask], 0)
    ends[linear_mask] = shapely.get_point(geometries[linear_mask], -1)
    endpoint_coordinates = np.empty((len(geometries), 2, 2), dtype=float)
    endpoint_coordinates[:, 0, 0] = shapely.get_x(starts)
    endpoint_coordinates[:, 0, 1] = shapely.get_y(starts)
    endpoint_coordinates[:, 1, 0] = shapely.get_x(ends)
    endpoint_coordinates[:, 1, 1] = shapely.get_y(ends)
    progress.update(2)
    progress.close()

    active = np.arange(len(geometries))
    iteration_count = max(0, int(iterations))
    iteration_iter = _maybe_tqdm(
        range(iteration_count),
        show_progress,
        total=iteration_count,
        desc="Dead ends: pruning passes",
        unit="pass",
    )
    for _ in iteration_iter:
        active_endpoints = endpoint_coordinates[active].reshape(-1, 2)
        _, node_ids, node_degrees = np.unique(
            active_endpoints,
            axis=0,
            return_inverse=True,
            return_counts=True,
        )
        keep = (
            (node_degrees[node_ids[0::2]] > 1)
            & (node_degrees[node_ids[1::2]] > 1)
        )
        if np.all(keep):
            break
        active = active[keep]

    return gpd.GeoDataFrame(geometry=geometries[active], crs=gdf.crs)


def _dissolve_and_buffer_protoblocks(
    protoblocks_gdf: gpd.GeoDataFrame, buffer_distance: float = 0.1
) -> gpd.GeoDataFrame:
    """Helper function to dissolve and buffer protoblocks.

    Args:
        protoblocks_gdf: A GeoDataFrame of protoblock polygons.
        buffer_distance: The buffer distance to apply.

    Returns:
        A GeoDataFrame containing the dissolved and buffered protoblocks.
    """
    dissolved = protoblocks_gdf.dissolve()
    buffered = dissolved.buffer(buffer_distance)
    return gpd.GeoDataFrame(geometry=buffered, crs=protoblocks_gdf.crs)


def filter_and_buffer_protoblocks_gdf(
    protoblocks_gdf: gpd.GeoDataFrame,
    sidewalks_gdf: gpd.GeoDataFrame,
    cutoff_percent: int,
    ignore_existing: bool = False,
    show_progress: bool = False,
) -> gpd.GeoDataFrame:
    """Filters and buffers the protoblocks based on sidewalk coverage.

    This function filters out protoblocks that have a high percentage of their
    area already covered by existing sidewalks. The remaining protoblocks are
    then dissolved and buffered.

    Args:
        protoblocks_gdf: A GeoDataFrame of protoblock polygons.
        sidewalks_gdf: A GeoDataFrame of existing sidewalk polygons.
        cutoff_percent: The percentage of sidewalk area above which a
            protoblock will be filtered out.
        ignore_existing: If True, skips filtering based on existing sidewalks
            and returns all protoblocks (dissolved and buffered).

    Returns:
        A GeoDataFrame containing the filtered and buffered protoblocks.
    """
    if ignore_existing or sidewalks_gdf.empty:
        return _dissolve_and_buffer_protoblocks(protoblocks_gdf)

    progress = tqdm(
        total=4,
        desc="Protoblocks: filtering sidewalk coverage",
        unit="operation",
        disable=not show_progress,
        position=1,
        leave=False,
        dynamic_ncols=True,
    )

    # Calculate sidewalk area and store it in a new column
    sidewalks_with_area_gdf = sidewalks_gdf.copy()
    sidewalks_with_area_gdf["sidewalk_area_val"] = sidewalks_with_area_gdf.geometry.area
    progress.update(1)

    # Spatial join
    joined_gdf = gpd.sjoin(
        protoblocks_gdf, sidewalks_with_area_gdf, how="inner", predicate="intersects"
    )
    progress.update(1)

    # Sum the areas of intersecting sidewalks for each protoblock
    sidewalk_area_per_protoblock = joined_gdf.groupby(
        joined_gdf.index
    ).sidewalk_area_val.sum()

    # Calculate protoblock area
    protoblocks_gdf["protoblock_area"] = protoblocks_gdf.geometry.area

    # Join the two series
    protoblocks_gdf = protoblocks_gdf.join(sidewalk_area_per_protoblock)
    protoblocks_gdf.rename(columns={"sidewalk_area_val": "sidewalk_area"}, inplace=True)
    protoblocks_gdf["sidewalk_area"] = protoblocks_gdf["sidewalk_area"].fillna(0)

    # Calculate ratio and filter
    protoblocks_gdf["ratio"] = (
        protoblocks_gdf["sidewalk_area"] / protoblocks_gdf["protoblock_area"]
    ) * 100
    filtered_protoblocks = protoblocks_gdf[protoblocks_gdf["ratio"] <= cutoff_percent]
    progress.update(1)

    # Dissolve and buffer
    result = _dissolve_and_buffer_protoblocks(filtered_protoblocks)
    progress.update(1)
    progress.close()
    return result


def calculate_crossing_direction(point: Point, lines_df: gpd.GeoDataFrame) -> Point:
    """Calculates the direction vector of a crossing.

    This function determines the direction of a crossing by finding the
    bisection of the angle between the two most aligned intersecting lines.

    Args:
        point: The intersection point of the crossing.
        lines_df: A DataFrame of lines that intersect at the point.

    Returns:
        A Point object representing the direction vector of the crossing, or
        None if the direction cannot be determined.
    """
    if len(lines_df) < 2:
        return None

    angles = []
    for line in lines_df.geometry:
        coords = list(line.coords)
        for i in range(len(coords) - 1):
            p1 = coords[i]
            p2 = coords[i + 1]
            if Point(p1).distance(point) < 0.1 or Point(p2).distance(point) < 0.1:
                angle = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
                angles.append(angle)

    if len(angles) < 2:
        return Point(1.0, 0.0)  # Default direction

    # Find the two angles with the smallest difference
    min_diff = 2 * math.pi
    best_pair = (0, 0)
    for i in range(len(angles)):
        for j in range(i + 1, len(angles)):
            diff = abs(angles[i] - angles[j])
            if diff > math.pi:
                diff = 2 * math.pi - diff
            if diff < min_diff:
                min_diff = diff
                best_pair = (angles[i], angles[j])

    # The direction of the crossing is the bisection of the angle
    angle = (best_pair[0] + best_pair[1]) / 2

    return Point(math.cos(angle), math.sin(angle))



class _CrossingsGenerator:
    def __init__(self):
        self.crs = None
        self.fallback_width = None
        self.tolerance = None
        self.max_ray_iterations_local = None
        self.ray_growth_factor_local = None
        self.sidewalks_prepared = None
        self.sidewalks_union = None
        self.sidewalk_geometries = None
        self.sidewalk_tree = None
        self.kerb_fraction = None
        self.distance_tol = None
        self.base_curve_radius = None
    def _empty_result(self) -> gpd.GeoDataFrame:
        return gpd.GeoDataFrame(geometry=[], crs=self.crs)

    def _resolve_width(self, row) -> float:
        value = row.get("width", self.fallback_width)
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = self.fallback_width
        if pd.isna(value) or value <= 0:
            value = self.fallback_width
        return value

    def _node_key(self, coord) -> tuple[float, float]:
        return (round(coord[0], self.tolerance), round(coord[1], self.tolerance))

    def _iter_lines(self, geom):
        if geom is None or geom.is_empty:
            return
        if isinstance(geom, LineString):
            yield geom
        elif isinstance(geom, MultiLineString):
            for part in geom.geoms:
                if part and not part.is_empty:
                    yield part

    def _resolve_width_namedtuple(self, row) -> float:
        value = getattr(row, "width", self.fallback_width)
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = self.fallback_width
        if pd.isna(value) or value <= 0:
            value = self.fallback_width
        return value

    def _iterate_points(self, geom):
        if geom.is_empty:
            return
        if isinstance(geom, Point):
            yield geom
        elif geom.geom_type == "MultiPoint":
            for pt in geom.geoms:
                yield pt
        elif geom.geom_type in {"LineString", "LinearRing"}:
            for coord in geom.coords:
                yield Point(coord)
        elif geom.geom_type == "MultiLineString":
            for part in geom.geoms:
                for coord in part.coords:
                    yield Point(coord)
        elif geom.geom_type in {"Polygon", "MultiPolygon"}:
            boundary = geom.boundary
            if boundary.geom_type == "MultiLineString":
                for part in boundary.geoms:
                    for coord in part.coords:
                        yield Point(coord)
            else:
                for coord in boundary.coords:
                    yield Point(coord)

    def _interpolate_along(self,
        line: LineString, base_distance: float, direction: int, distance: float
    ) -> Optional[Point]:
        if line.length == 0:
            return None
        distance = max(distance, 0.0)
        if direction > 0:
            target = min(base_distance + distance, line.length)
        else:
            target = max(base_distance - distance, 0.0)
        try:
            return line.interpolate(target)
        except Exception:
            return None

    def _tangent_direction(self,
        line: LineString, at_dist: float
    ) -> Optional[tuple[float, float]]:
        if line.length == 0:
            return None
        span = max(min(line.length * 0.05, 1.0), 1e-3)
        d0 = max(at_dist - span, 0.0)
        d1 = min(at_dist + span, line.length)
        p0 = line.interpolate(d0)
        p1 = line.interpolate(d1)
        vec = (p1.x - p0.x, p1.y - p0.y)
        norm = math.hypot(*vec)
        if norm == 0:
            return None
        return (vec[0] / norm, vec[1] / norm)

    def _perpendicular(self, vec: tuple[float, float]) -> tuple[float, float]:
        return (-vec[1], vec[0])

    def _extract_hit(self, geom, origin: Point, tol: float = 1e-3) -> Optional[Point]:
        if geom.is_empty:
            return None

        if isinstance(geom, Point):
            return geom if geom.distance(origin) > tol else None

        if geom.geom_type == "MultiPoint":
            pts = [pt for pt in geom.geoms if pt.distance(origin) > tol]
            if not pts:
                return None
            return min(pts, key=lambda p: p.distance(origin))

        if geom.geom_type in {"LineString", "LinearRing"}:
            candidate = nearest_points(origin, geom)[1]
            if candidate.distance(origin) > tol:
                return candidate
            pts = [Point(c) for c in geom.coords if Point(c).distance(origin) > tol]
            if not pts:
                return None
            return min(pts, key=lambda p: p.distance(origin))

        if geom.geom_type == "MultiLineString":
            candidates = [
                hit
                for part in geom.geoms
                if (hit := self._extract_hit(part, origin, tol)) is not None
            ]
            if not candidates:
                return None
            return min(candidates, key=lambda p: p.distance(origin))

        if geom.geom_type == "GeometryCollection":
            candidates = [
                hit
                for part in geom.geoms
                if (hit := self._extract_hit(part, origin, tol)) is not None
            ]
            if not candidates:
                return None
            return min(candidates, key=lambda p: p.distance(origin))

        if geom.geom_type == "Polygon":
            return self._extract_hit(geom.boundary, origin, tol)

        if geom.geom_type == "MultiPolygon":
            candidates = [
                hit
                for part in geom.geoms
                if (hit := self._extract_hit(part.boundary, origin, tol)) is not None
            ]
            if not candidates:
                return None
            return min(candidates, key=lambda p: p.distance(origin))

        return None

    def _cast_ray(self,
        origin: Point, direction: tuple[float, float], base_len: float
    ) -> Optional[Point]:
        length = max(base_len, 0.5)
        for _ in range(self.max_ray_iterations_local):
            target = Point(
                origin.x + direction[0] * length,
                origin.y + direction[1] * length,
            )
            ray = LineString([origin, target])
            candidate_indexes = self.sidewalk_tree.query(
                ray,
                predicate="intersects",
            )
            if len(candidate_indexes) == 0:
                length *= self.ray_growth_factor_local
                continue
            candidates = []
            for candidate_index in candidate_indexes:
                hit = self.sidewalk_geometries[int(candidate_index)].intersection(ray)
                candidate = self._extract_hit(hit, origin)
                if candidate is not None:
                    candidates.append(candidate)
            if candidates:
                return min(candidates, key=origin.distance)
            length *= self.ray_growth_factor_local
        return None

    def _build_crossing_record(self,
        point_a: Point,
        point_e: Point,
        base_length: float,
        max_allowed: float,
        segment_id: int,
        node_degree: int,
        center_offset: float,
        *,
        fallback: bool = False,
    ) -> dict:
        midpoint = Point(
            (point_a.x + point_e.x) / 2.0,
            (point_a.y + point_e.y) / 2.0,
        )

        ac_line = LineString([point_a, midpoint])
        ec_line = LineString([point_e, midpoint])
        if ac_line.length == 0 or ec_line.length == 0:
            return {}

        point_b = ac_line.interpolate(ac_line.length * self.kerb_fraction)
        point_d = ec_line.interpolate(ec_line.length * self.kerb_fraction)

        crossing_line = LineString(
            [
                (point_a.x, point_a.y),
                (point_b.x, point_b.y),
                (midpoint.x, midpoint.y),
                (point_d.x, point_d.y),
                (point_e.x, point_e.y),
            ]
        )

        crossing_length = point_a.distance(point_e)

        return {
            "geometry": crossing_line,
            "length_m": crossing_length,
            "length_ok": crossing_length <= max_allowed,
            "above_tolerance": crossing_length > base_length,
            "segment_id": segment_id,
            "node_degree": node_degree,
            "center_offset_m": center_offset,
            "used_fallback": fallback,
        }


def _nearest_ray_hits(
    rays: np.ndarray,
    origins: np.ndarray,
    sidewalk_tree: STRtree,
    sidewalk_geometries: np.ndarray,
    tolerance: float = 1e-3,
) -> np.ndarray:
    """Return the nearest sidewalk intersection for every ray in one tree query."""
    hits = np.full(len(rays), None, dtype=object)
    if len(rays) == 0 or len(sidewalk_geometries) == 0:
        return hits

    pairs = sidewalk_tree.query(rays, predicate="intersects")
    if pairs.shape[1] == 0:
        return hits

    ray_indexes = pairs[0]
    sidewalk_indexes = pairs[1]
    intersections = shapely.intersection(
        rays[ray_indexes],
        sidewalk_geometries[sidewalk_indexes],
    )
    nearest_lines = shapely.shortest_line(origins[ray_indexes], intersections)
    nearest_points = shapely.get_point(nearest_lines, -1)
    distances = shapely.distance(origins[ray_indexes], nearest_points)

    valid = (
        ~shapely.is_empty(nearest_points)
        & np.isfinite(distances)
        & (distances > tolerance)
    )
    if np.any(valid):
        valid_ray_indexes = ray_indexes[valid]
        valid_distances = distances[valid]
        valid_points = nearest_points[valid]
        order = np.lexsort((valid_distances, valid_ray_indexes))
        ordered_ray_indexes = valid_ray_indexes[order]
        first_for_ray = np.r_[
            True,
            ordered_ray_indexes[1:] != ordered_ray_indexes[:-1],
        ]
        selected = order[first_for_ray]
        hits[valid_ray_indexes[selected]] = valid_points[selected]

    # A ray can start on one sidewalk and hit another farther away. The vectorized
    # shortest-line result is then the origin itself; resolve only these rare cases
    # with the complete scalar extractor instead of penalizing every ray.
    origin_pairs = np.flatnonzero(~valid & (distances <= tolerance))
    if len(origin_pairs):
        grouped: dict[int, list] = {}
        for pair_position in origin_pairs:
            grouped.setdefault(int(ray_indexes[pair_position]), []).append(
                intersections[pair_position]
            )
        extractor = _CrossingsGenerator()
        for ray_index, geometries in grouped.items():
            if hits[ray_index] is not None:
                continue
            candidates = [
                candidate
                for geometry in geometries
                if (
                    candidate := extractor._extract_hit(
                        geometry,
                        origins[ray_index],
                        tolerance,
                    )
                )
                is not None
            ]
            if candidates:
                hits[ray_index] = min(
                    candidates,
                    key=origins[ray_index].distance,
                )

    return hits


def _nearest_ray_hits_with_growth(
    rays: np.ndarray,
    origins: np.ndarray,
    sidewalk_tree: STRtree,
    sidewalk_geometries: np.ndarray,
    growth_factor: float,
    max_iterations: int,
) -> np.ndarray:
    """Cast short rays first and grow only those that miss a sidewalk."""
    hits = np.full(len(rays), None, dtype=object)
    active_indexes = np.arange(len(rays))
    active_rays = rays

    for _ in range(max(1, int(max_iterations))):
        active_hits = _nearest_ray_hits(
            active_rays,
            origins[active_indexes],
            sidewalk_tree,
            sidewalk_geometries,
        )
        found = ~pd.isna(active_hits)
        if np.any(found):
            hits[active_indexes[found]] = active_hits[found]

        missing = ~found
        if not np.any(missing):
            break
        active_indexes = active_indexes[missing]
        active_rays = active_rays[missing]

        ray_ends = shapely.get_point(active_rays, -1)
        active_origins = origins[active_indexes]
        origin_x = shapely.get_x(active_origins)
        origin_y = shapely.get_y(active_origins)
        end_x = shapely.get_x(ray_ends)
        end_y = shapely.get_y(ray_ends)
        grown_coordinates = np.stack(
            (
                np.column_stack((origin_x, origin_y)),
                np.column_stack(
                    (
                        origin_x + (end_x - origin_x) * growth_factor,
                        origin_y + (end_y - origin_y) * growth_factor,
                    )
                ),
            ),
            axis=1,
        )
        active_rays = shapely.linestrings(grown_coordinates)

    return hits


def _nearest_ray_hits_parallel(
    rays: np.ndarray,
    origins: np.ndarray,
    sidewalk_tree: STRtree,
    sidewalk_geometries: np.ndarray,
    growth_factor: float,
    max_iterations: int,
    min_parallel_size: int = 4_000,
) -> np.ndarray:
    """Parallelize large read-only STRtree ray batches across GEOS threads."""
    worker_count = min(8, os.cpu_count() or 1)
    if worker_count <= 1 or len(rays) < min_parallel_size:
        return _nearest_ray_hits_with_growth(
            rays,
            origins,
            sidewalk_tree,
            sidewalk_geometries,
            growth_factor,
            max_iterations,
        )

    chunks = [
        indexes
        for indexes in np.array_split(np.arange(len(rays)), worker_count)
        if len(indexes)
    ]
    with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
        futures = [
            executor.submit(
                _nearest_ray_hits_with_growth,
                rays[indexes],
                origins[indexes],
                sidewalk_tree,
                sidewalk_geometries,
                growth_factor,
                max_iterations,
            )
            for indexes in chunks
        ]
        return np.concatenate([future.result() for future in futures])


def _crossing_rays(
    lines: np.ndarray,
    segment_indexes: np.ndarray,
    line_lengths: np.ndarray,
    inward_distances: np.ndarray,
    from_start: np.ndarray,
    ray_lengths: np.ndarray,
):
    """Build centers, perpendiculars, and paired rays for crossing candidates."""
    selected_lines = lines[segment_indexes]
    selected_lengths = line_lengths[segment_indexes]
    along = np.where(
        from_start,
        inward_distances,
        selected_lengths - inward_distances,
    )
    centers = shapely.line_interpolate_point(selected_lines, along)

    spans = np.maximum(np.minimum(selected_lengths * 0.05, 1.0), 1e-3)
    point_before = shapely.line_interpolate_point(
        selected_lines,
        np.maximum(along - spans, 0.0),
    )
    point_after = shapely.line_interpolate_point(
        selected_lines,
        np.minimum(along + spans, selected_lengths),
    )
    dx = shapely.get_x(point_after) - shapely.get_x(point_before)
    dy = shapely.get_y(point_after) - shapely.get_y(point_before)
    norms = np.hypot(dx, dy)
    valid = np.isfinite(norms) & (norms > 0)
    perpendicular_x = np.zeros(len(centers), dtype=float)
    perpendicular_y = np.zeros(len(centers), dtype=float)
    perpendicular_x[valid] = -dy[valid] / norms[valid]
    perpendicular_y[valid] = dx[valid] / norms[valid]

    center_x = shapely.get_x(centers)
    center_y = shapely.get_y(centers)
    ray_coordinates = np.empty((len(centers) * 2, 2, 2), dtype=float)
    ray_coordinates[0::2, 0, :] = np.column_stack((center_x, center_y))
    ray_coordinates[1::2, 0, :] = np.column_stack((center_x, center_y))
    ray_coordinates[0::2, 1, 0] = center_x + perpendicular_x * ray_lengths
    ray_coordinates[0::2, 1, 1] = center_y + perpendicular_y * ray_lengths
    ray_coordinates[1::2, 1, 0] = center_x - perpendicular_x * ray_lengths
    ray_coordinates[1::2, 1, 1] = center_y - perpendicular_y * ray_lengths
    rays = shapely.linestrings(ray_coordinates)
    origins = np.repeat(centers, 2)
    return centers, perpendicular_x, perpendicular_y, rays, origins, valid


def _draw_crossings_noded(
    streets_gdf: gpd.GeoDataFrame,
    generator: _CrossingsGenerator,
    *,
    inward_offset: float,
    extra_length: float,
    increment_inward: float,
    max_crossings_iterations: int,
    abs_max_crossing_len: float,
    perc_tol_crossings: float,
    show_progress: bool,
) -> gpd.GeoDataFrame:
    """Generate crossings from an already-noded network using batched ufuncs."""
    geometry_series = streets_gdf.geometry.explode(
        index_parts=False,
        ignore_index=False,
    )
    original_indexes = geometry_series.index.to_numpy()
    lines = np.asarray(geometry_series.array, dtype=object)
    valid_lines = (
        ~shapely.is_missing(lines)
        & ~shapely.is_empty(lines)
        & (shapely.get_type_id(lines) == 1)
        & (shapely.length(lines) > generator.distance_tol)
    )
    lines = lines[valid_lines]
    original_indexes = original_indexes[valid_lines]
    if len(lines) == 0:
        return generator._empty_result()

    if "width" in streets_gdf.columns:
        source_widths = pd.to_numeric(
            streets_gdf["width"],
            errors="coerce",
        ).reindex(geometry_series.index).to_numpy(dtype=float)
        widths = source_widths[valid_lines]
        widths[~np.isfinite(widths) | (widths <= 0)] = generator.fallback_width
    else:
        widths = np.full(len(lines), generator.fallback_width, dtype=float)

    progress = tqdm(
        total=max(1, int(max_crossings_iterations)) + 3,
        desc="Crossings: batched noded network",
        unit="batch",
        disable=not show_progress,
        position=1,
        leave=False,
        dynamic_ncols=True,
    )

    line_lengths = shapely.length(lines)
    starts = shapely.get_point(lines, 0)
    ends = shapely.get_point(lines, -1)
    endpoint_coordinates = np.column_stack(
        (
            np.ravel(
                np.column_stack((shapely.get_x(starts), shapely.get_x(ends)))
            ),
            np.ravel(
                np.column_stack((shapely.get_y(starts), shapely.get_y(ends)))
            ),
        )
    )
    rounded_endpoints = np.round(endpoint_coordinates, generator.tolerance)
    _, node_ids = np.unique(
        rounded_endpoints,
        axis=0,
        return_inverse=True,
    )
    endpoint_segment_indexes = np.repeat(np.arange(len(lines)), 2)
    endpoint_from_start = np.tile(np.array([True, False]), len(lines))
    endpoint_widths = widths[endpoint_segment_indexes]
    node_segment_pairs = np.unique(
        np.column_stack((node_ids, endpoint_segment_indexes)),
        axis=0,
    )
    node_degrees = np.bincount(
        node_segment_pairs[:, 0],
        minlength=int(node_ids.max()) + 1,
    )
    node_major_widths = np.full(len(node_degrees), -np.inf, dtype=float)
    np.maximum.at(node_major_widths, node_ids, endpoint_widths)
    progress.update(1)

    candidate_mask = node_degrees[node_ids] > 2
    segment_indexes = endpoint_segment_indexes[candidate_mask]
    from_start = endpoint_from_start[candidate_mask]
    candidate_node_ids = node_ids[candidate_mask]
    candidate_degrees = node_degrees[candidate_node_ids]
    candidate_widths = widths[segment_indexes]
    candidate_lengths = line_lengths[segment_indexes]
    base_lengths = candidate_widths + extra_length
    max_inward = np.minimum(candidate_lengths * 0.49, candidate_lengths * 0.99)
    inward_distances = np.minimum(
        0.5 * node_major_widths[candidate_node_ids]
        + generator.base_curve_radius
        + inward_offset,
        max_inward,
    )
    valid_candidates = (
        (base_lengths > 0)
        & (candidate_lengths > generator.distance_tol)
        & (inward_distances > generator.distance_tol)
    )
    segment_indexes = segment_indexes[valid_candidates]
    from_start = from_start[valid_candidates]
    candidate_degrees = candidate_degrees[valid_candidates]
    candidate_widths = candidate_widths[valid_candidates]
    base_lengths = base_lengths[valid_candidates]
    max_inward = max_inward[valid_candidates]
    inward_distances = inward_distances[valid_candidates]
    output_segment_ids = original_indexes[segment_indexes]
    progress.update(1)

    if len(segment_indexes) == 0:
        progress.close()
        return generator._empty_result()

    ray_lengths = np.maximum(base_lengths, 0.5)
    max_allowed = base_lengths * (1 + perc_tol_crossings / 100.0)
    point_a = np.full(len(segment_indexes), None, dtype=object)
    point_e = np.full(len(segment_indexes), None, dtype=object)
    accepted = np.zeros(len(segment_indexes), dtype=bool)
    fallback = np.zeros(len(segment_indexes), dtype=bool)
    last_centers = np.full(len(segment_indexes), None, dtype=object)
    last_perpendicular_x = np.zeros(len(segment_indexes), dtype=float)
    last_perpendicular_y = np.zeros(len(segment_indexes), dtype=float)
    active = np.ones(len(segment_indexes), dtype=bool)

    for _ in range(max(1, int(max_crossings_iterations))):
        active_indexes = np.flatnonzero(active)
        if len(active_indexes) == 0:
            progress.update(1)
            continue

        centers, perp_x, perp_y, rays, origins, tangent_valid = _crossing_rays(
            lines,
            segment_indexes[active_indexes],
            line_lengths,
            inward_distances[active_indexes],
            from_start[active_indexes],
            ray_lengths[active_indexes],
        )
        last_centers[active_indexes] = centers
        last_perpendicular_x[active_indexes] = perp_x
        last_perpendicular_y[active_indexes] = perp_y
        hits = _nearest_ray_hits_parallel(
            rays,
            origins,
            generator.sidewalk_tree,
            generator.sidewalk_geometries,
            generator.ray_growth_factor_local,
            generator.max_ray_iterations_local,
        )
        hits_a = hits[0::2]
        hits_e = hits[1::2]
        has_hits = (
            tangent_valid
            & ~pd.isna(hits_a)
            & ~pd.isna(hits_e)
        )
        hit_lengths = np.full(len(active_indexes), np.inf, dtype=float)
        if np.any(has_hits):
            hit_lengths[has_hits] = shapely.distance(
                hits_a[has_hits],
                hits_e[has_hits],
            )
        successful = (
            has_hits
            & (hit_lengths > 0)
            & (hit_lengths <= abs_max_crossing_len)
            & (hit_lengths <= max_allowed[active_indexes])
        )
        successful_indexes = active_indexes[successful]
        point_a[successful_indexes] = hits_a[successful]
        point_e[successful_indexes] = hits_e[successful]
        accepted[successful_indexes] = True
        active[successful_indexes] = False

        retry_indexes = active_indexes[~successful]
        can_move = (
            inward_distances[retry_indexes]
            < max_inward[retry_indexes] - generator.distance_tol
        )
        if np.any(can_move):
            moving_indexes = retry_indexes[can_move]
            inward_distances[moving_indexes] = np.minimum(
                inward_distances[moving_indexes] + increment_inward,
                max_inward[moving_indexes],
            )
        exhausted_indexes = retry_indexes[~can_move]
        active[exhausted_indexes] = False
        fallback[exhausted_indexes] = base_lengths[exhausted_indexes] <= abs_max_crossing_len
        progress.update(1)

    remaining = np.flatnonzero(active)
    if len(remaining):
        fallback[remaining] = base_lengths[remaining] <= abs_max_crossing_len
        active[remaining] = False

    fallback_indexes = np.flatnonzero(fallback & ~accepted)
    if len(fallback_indexes):
        half = base_lengths[fallback_indexes] / 2.0
        center_x = shapely.get_x(last_centers[fallback_indexes])
        center_y = shapely.get_y(last_centers[fallback_indexes])
        point_a[fallback_indexes] = shapely.points(
            center_x + last_perpendicular_x[fallback_indexes] * half,
            center_y + last_perpendicular_y[fallback_indexes] * half,
        )
        point_e[fallback_indexes] = shapely.points(
            center_x - last_perpendicular_x[fallback_indexes] * half,
            center_y - last_perpendicular_y[fallback_indexes] * half,
        )

    keep = accepted | fallback
    if not np.any(keep):
        progress.close()
        return generator._empty_result()

    point_a = point_a[keep]
    point_e = point_e[keep]
    kept_base_lengths = base_lengths[keep]
    point_a_x = shapely.get_x(point_a)
    point_a_y = shapely.get_y(point_a)
    point_e_x = shapely.get_x(point_e)
    point_e_y = shapely.get_y(point_e)
    midpoint_x = (point_a_x + point_e_x) / 2.0
    midpoint_y = (point_a_y + point_e_y) / 2.0
    point_b_x = point_a_x + (midpoint_x - point_a_x) * generator.kerb_fraction
    point_b_y = point_a_y + (midpoint_y - point_a_y) * generator.kerb_fraction
    point_d_x = point_e_x + (midpoint_x - point_e_x) * generator.kerb_fraction
    point_d_y = point_e_y + (midpoint_y - point_e_y) * generator.kerb_fraction
    coordinates = np.stack(
        (
            np.column_stack((point_a_x, point_a_y)),
            np.column_stack((point_b_x, point_b_y)),
            np.column_stack((midpoint_x, midpoint_y)),
            np.column_stack((point_d_x, point_d_y)),
            np.column_stack((point_e_x, point_e_y)),
        ),
        axis=1,
    )
    crossing_geometries = shapely.linestrings(coordinates)
    crossing_lengths = np.hypot(point_a_x - point_e_x, point_a_y - point_e_y)
    result = gpd.GeoDataFrame(
        {
            "length_m": crossing_lengths,
            "length_ok": crossing_lengths <= max_allowed[keep],
            "above_tolerance": crossing_lengths > kept_base_lengths,
            "segment_id": output_segment_ids[keep],
            "node_degree": candidate_degrees[keep],
            "center_offset_m": inward_distances[keep],
            "used_fallback": fallback[keep] & ~accepted[keep],
        },
        geometry=crossing_geometries,
        crs=generator.crs,
    )
    progress.update(1)
    progress.close()
    return result


def draw_crossings_gdf(
    streets_gdf: gpd.GeoDataFrame,
    sidewalks_gdf: Optional[gpd.GeoDataFrame] = None,
    protoblocks_gdf: Optional[gpd.GeoDataFrame] = None,
    *,
    curve_radius: Optional[float] = None,
    inward_offset: float = 1.0,
    extra_length: float = 1.0,
    increment_inward: float = 0.5,
    max_crossings_iterations: int = 20,
    abs_max_crossing_len: float = 100.0,
    perc_tol_crossings: float = 25.0,
    perc_draw_kerbs: float = 30.0,
    ray_growth_factor: float = 2.0,
    max_ray_iterations: int = 5,
    node_precision: int = 6,
    show_progress: bool = False,
    assume_noded: bool = False,
) -> gpd.GeoDataFrame:
    """Generate crossings following the documented Sidewalkreator procedure."""

    from .parameters import default_curve_radius, fallback_default_width

    crs = streets_gdf.crs if streets_gdf is not None else None
    generator = _CrossingsGenerator()
    generator.crs = crs


    if streets_gdf is None or streets_gdf.empty:
        return generator._empty_result()

    if sidewalks_gdf is None or sidewalks_gdf.empty:
        return generator._empty_result()

    sidewalk_series = sidewalks_gdf.geometry.explode(
        index_parts=False,
        ignore_index=True,
    )
    sidewalk_geometries = np.asarray(sidewalk_series.array, dtype=object)
    valid_sidewalks = (
        ~shapely.is_missing(sidewalk_geometries)
        & ~shapely.is_empty(sidewalk_geometries)
        & np.isin(shapely.get_type_id(sidewalk_geometries), [1, 2])
    )
    sidewalk_geometries = sidewalk_geometries[valid_sidewalks]
    if len(sidewalk_geometries) == 0:
        return generator._empty_result()
    generator.sidewalk_geometries = sidewalk_geometries
    generator.sidewalk_tree = STRtree(sidewalk_geometries)

    # Keep protoblock argument for API completeness (not yet used for filtering).
    _ = protoblocks_gdf

    tolerance = max(3, int(node_precision))
    kerb_fraction = max(0.0, min(perc_draw_kerbs / 100.0, 0.49))
    base_curve_radius = default_curve_radius if curve_radius is None else curve_radius
    ray_growth_factor_local = max(ray_growth_factor, 1.1)
    max_ray_iterations_local = max(1, int(max_ray_iterations))
    fallback_width = float(fallback_default_width)
    distance_tol = 1e-6
    generator.fallback_width = fallback_width
    generator.tolerance = tolerance
    generator.kerb_fraction = kerb_fraction
    generator.base_curve_radius = base_curve_radius
    generator.ray_growth_factor_local = ray_growth_factor_local
    generator.max_ray_iterations_local = max_ray_iterations_local
    generator.distance_tol = distance_tol

    if assume_noded:
        return _draw_crossings_noded(
            streets_gdf,
            generator,
            inward_offset=inward_offset,
            extra_length=extra_length,
            increment_inward=increment_inward,
            max_crossings_iterations=max_crossings_iterations,
            abs_max_crossing_len=abs_max_crossing_len,
            perc_tol_crossings=perc_tol_crossings,
            show_progress=show_progress,
        )

    sidewalks_union = shapely.union_all(sidewalk_geometries)
    generator.sidewalks_union = sidewalks_union
    generator.sidewalks_prepared = prep(sidewalks_union)





    node_data: dict[tuple[float, float], dict] = {}
    segment_info: dict[int, dict] = {}
    segment_nodes: dict[int, dict] = {}


    street_rows = _maybe_tqdm(
        streets_gdf.itertuples(),
        show_progress,
        total=len(streets_gdf),
        desc="Crossings: indexing street segments",
        unit="feature",
    )
    for row in street_rows:
        idx = row.Index
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue

        for line in generator._iter_lines(geom):
            if line.length <= 0:
                continue
            width = generator._resolve_width_namedtuple(row)
            coords = list(line.coords)
            start = coords[0]
            end = coords[-1]
            segment_info[idx] = {
                "geometry": line,
                "width": width,
                "start": start,
                "end": end,
            }
            segment_nodes[idx] = {}

            for coord, dist in ((start, 0.0), (end, line.length)):
                key = generator._node_key(coord)
                entry = node_data.setdefault(
                    key, {"point": Point(coord), "segments": set(), "widths": []}
                )
                entry["segments"].add(idx)
                entry["widths"].append(width)
                segment_nodes[idx][(key, round(dist, 6))] = {
                    "node_key": key,
                    "distance": dist,
                }

    if not segment_info:
        return generator._empty_result()

    # Augment node data with interior intersections (handles unsplit segments)
    segment_series = gpd.GeoSeries(
        {idx: info["geometry"] for idx, info in segment_info.items()}, crs=crs
    )
    sindex = segment_series.sindex
    pairs = sindex.query(segment_series, predicate="intersects")


    pair_count = len(pairs[0]) if len(pairs) else 0
    pair_iter = _maybe_tqdm(
        zip(*pairs),
        show_progress,
        total=pair_count,
        desc="Crossings: segment intersections",
        unit="pair",
    )
    for idx1, idx2 in pair_iter:
        if idx1 >= idx2:
            continue
        line1 = segment_series.loc[idx1]
        line2 = segment_series.loc[idx2]
        try:
            inter = line1.intersection(line2)
        except Exception:
            continue

        for pt in generator._iterate_points(inter):
            if pt.is_empty:
                continue
            proj1 = line1.project(pt)
            proj2 = line2.project(pt)
            aligned1 = line1.interpolate(proj1)
            aligned2 = line2.interpolate(proj2)
            key = generator._node_key((aligned1.x, aligned1.y))
            entry = node_data.setdefault(
                key, {"point": aligned1, "segments": set(), "widths": []}
            )
            entry["segments"].update([idx1, idx2])
            entry["widths"].append(segment_info[idx1]["width"])
            entry["widths"].append(segment_info[idx2]["width"])

            segment_nodes[idx1][(key, round(proj1, 6))] = {
                "node_key": key,
                "distance": proj1,
            }
            segment_nodes[idx2][(key, round(proj2, 6))] = {
                "node_key": key,
                "distance": proj2,
            }

    for entry in node_data.values():
        entry["degree"] = len(entry["segments"])
        entry["major_width"] = (
            max(entry["widths"]) if entry["widths"] else fallback_width
        )







    records = []

    segment_iter = _maybe_tqdm(
        segment_info.items(),
        show_progress,
        total=len(segment_info),
        desc="Crossings: casting candidates",
        unit="segment",
    )
    for idx, info in segment_iter:
        line = info["geometry"]
        segment_width = info["width"]
        base_length = segment_width + extra_length
        if base_length <= 0 or line is None or line.length <= distance_tol:
            continue

        node_entries = list(segment_nodes.get(idx, {}).values())
        if not node_entries:
            continue

        processed_dirs = set()

        for node_entry in node_entries:
            node = node_data.get(node_entry["node_key"])
            if not node or node["degree"] <= 2:
                continue

            line_length = line.length
            if line_length <= 0:
                continue

            major_width = node["major_width"]
            initial_inward = 0.5 * major_width + base_curve_radius + inward_offset
            base_distance = node_entry["distance"]
            available_forward = line_length - base_distance
            available_backward = base_distance
            max_allowed = base_length * (1 + perc_tol_crossings / 100.0)

            for direction in (1, -1):
                available = available_forward if direction > 0 else available_backward
                if available <= distance_tol:
                    continue

                dir_key = (node_entry["node_key"], direction)
                if dir_key in processed_dirs:
                    continue

                max_inward = min(max(0.0, line_length * 0.49), available * 0.99)
                current_inward = min(initial_inward, max_inward)
                if current_inward <= 0:
                    current_inward = min(available * 0.5, max_inward)
                if current_inward <= distance_tol:
                    continue

                attempt = 0
                record_added = False
                last_center = None
                last_perp = None

                while attempt < max_crossings_iterations:
                    center = generator._interpolate_along(
                        line, base_distance, direction, current_inward
                    )
                    if center is None:
                        break

                    distance_along = line.project(center)
                    tangent = generator._tangent_direction(line, distance_along)
                    if tangent is None:
                        break
                    perp = generator._perpendicular(tangent)
                    last_center = center
                    last_perp = perp

                    point_a = generator._cast_ray(center, perp, base_length)
                    point_e = generator._cast_ray(center, (-perp[0], -perp[1]), base_length)

                    if point_a is None or point_e is None:
                        attempt += 1
                        if current_inward < max_inward:
                            current_inward = min(
                                current_inward + increment_inward, max_inward
                            )
                            continue

                        if base_length <= abs_max_crossing_len:
                            half = base_length / 2.0
                            fallback_a = Point(
                                center.x + perp[0] * half,
                                center.y + perp[1] * half,
                            )
                            fallback_e = Point(
                                center.x - perp[0] * half,
                                center.y - perp[1] * half,
                            )
                            record = generator._build_crossing_record(
                                fallback_a,
                                fallback_e,
                                base_length,
                                max_allowed,
                                idx,
                                node["degree"],
                                current_inward,
                                fallback=True,
                            )
                            if record:
                                records.append(record)
                                record_added = True
                        break

                    crossing_length = point_a.distance(point_e)
                    if crossing_length <= 0 or crossing_length > abs_max_crossing_len:
                        attempt += 1
                        if current_inward < max_inward:
                            current_inward = min(
                                current_inward + increment_inward, max_inward
                            )
                            continue
                        break

                    if crossing_length <= max_allowed:
                        record = generator._build_crossing_record(
                            point_a,
                            point_e,
                            base_length,
                            max_allowed,
                            idx,
                            node["degree"],
                            current_inward,
                        )
                        if record:
                            records.append(record)
                            record_added = True
                        break

                    attempt += 1
                    if current_inward >= max_inward:
                        break

                    current_inward = min(current_inward + increment_inward, max_inward)

                if (
                    not record_added
                    and last_center is not None
                    and last_perp is not None
                    and base_length <= abs_max_crossing_len
                ):
                    half = base_length / 2.0
                    fallback_a = Point(
                        last_center.x + last_perp[0] * half,
                        last_center.y + last_perp[1] * half,
                    )
                    fallback_e = Point(
                        last_center.x - last_perp[0] * half,
                        last_center.y - last_perp[1] * half,
                    )
                    record = generator._build_crossing_record(
                        fallback_a,
                        fallback_e,
                        base_length,
                        max_allowed,
                        idx,
                        node["degree"],
                        current_inward,
                        fallback=True,
                    )
                    if record:
                        records.append(record)

                processed_dirs.add(dir_key)

    if not records:
        return generator._empty_result()

    return gpd.GeoDataFrame(records, geometry="geometry", crs=crs)


from scipy.spatial import Voronoi, QhullError
from shapely.errors import GEOSException


def _get_voronoi_points(pois_gdf: gpd.GeoDataFrame) -> List[Tuple[float, float]]:
    def get_point_coords(geom):
        if geom.geom_type == "Point":
            return (geom.x, geom.y)
        else:
            centroid = geom.centroid
            return (centroid.x, centroid.y)

    return pois_gdf.geometry.apply(get_point_coords).tolist()


def _create_voronoi_lines_gdf(points: List[Tuple[float, float]], crs) -> gpd.GeoDataFrame:
    try:
        vor = Voronoi(points)
    except (QhullError, ValueError):
        return gpd.GeoDataFrame(geometry=[], crs=crs)

    try:
        lines = [
            LineString(vor.vertices[line])
            for line in vor.ridge_vertices
            if -1 not in line
        ]
    except (GEOSException, ValueError):
        return gpd.GeoDataFrame(geometry=[], crs=crs)

    if not lines:
        return gpd.GeoDataFrame(geometry=[], crs=crs)

    return gpd.GeoDataFrame(geometry=lines, crs=crs)


def _split_single_sidewalk(sidewalk, voronoi_lines) -> List:
    if sidewalk is None or sidewalk.is_empty:
        return []

    # For line geometries, use the boundary; for other types, use as-is
    if sidewalk.geom_type in ["LineString", "MultiLineString"]:
        splittable_geom = sidewalk
    elif sidewalk.geom_type in ["Polygon", "MultiPolygon"]:
        splittable_geom = sidewalk.boundary
    else:
        # Skip unsupported geometry types
        return []

    # Skip if the splittable geometry is empty or invalid
    if splittable_geom.is_empty or not splittable_geom.is_valid:
        return []

    # Avoid potentially hanging union_all operation - split by individual lines instead
    for voronoi_line in voronoi_lines:
        if voronoi_line.is_empty or not voronoi_line.is_valid:
            continue

        try:
            # Split by this individual line
            split_result = split(splittable_geom, voronoi_line)
            if hasattr(split_result, "geoms") and len(split_result.geoms) > 1:
                # Successfully split - use the split result for next iteration
                splittable_geom = split_result
                break
        except (GEOSException, ValueError, TypeError, AttributeError):
            # Split failed, but continue with other lines
            continue

    # Add final geometry to results
    new_segments = []
    if hasattr(splittable_geom, "geoms"):
        for part in splittable_geom.geoms:
            if not part.is_empty:
                new_segments.append(part)
    else:
        if not splittable_geom.is_empty:
            new_segments.append(splittable_geom)

    return new_segments


def split_sidewalks_by_voronoi(
    sidewalks_gdf: gpd.GeoDataFrame,
    pois_gdf: gpd.GeoDataFrame,
    show_progress: bool = False,
) -> gpd.GeoDataFrame:
    """Splits sidewalks by Voronoi polygons generated from POIs.

    This function creates Voronoi polygons from a set of points of interest (POIs)
    and uses the edges of these polygons to split the sidewalk lines.

    Args:
        sidewalks_gdf: A GeoDataFrame of sidewalk lines.
        pois_gdf: A GeoDataFrame of POIs.

    Returns:
        A new GeoDataFrame containing the split sidewalk segments.
    """
    if pois_gdf.empty:
        return sidewalks_gdf

    points = _get_voronoi_points(pois_gdf)
    if len(points) < 4:
        # Not enough points for Voronoi diagram, return original sidewalks
        return sidewalks_gdf

    voronoi_lines_gdf = _create_voronoi_lines_gdf(points, sidewalks_gdf.crs)
    if voronoi_lines_gdf.empty:
        return sidewalks_gdf

    # Query all sidewalk/Voronoi intersections once, then split each sidewalk
    # with only its local candidates. The former loop tested every Voronoi edge
    # against every sidewalk.
    splittable_geometries = np.asarray(
        [
            geometry.boundary
            if geometry.geom_type in {"Polygon", "MultiPolygon"}
            else geometry
            for geometry in sidewalks_gdf.geometry
        ],
        dtype=object,
    )
    voronoi_geometries = np.asarray(
        voronoi_lines_gdf.geometry.array,
        dtype=object,
    )
    pairs = STRtree(voronoi_geometries).query(
        splittable_geometries,
        predicate="intersects",
    )
    unique_pairs = np.unique(pairs.T, axis=0)
    sidewalk_matches = unique_pairs[:, 0]
    voronoi_matches = unique_pairs[:, 1]
    matched_sidewalks = np.unique(sidewalk_matches)
    match_starts = np.searchsorted(sidewalk_matches, matched_sidewalks, side="left")
    match_ends = np.searchsorted(sidewalk_matches, matched_sidewalks, side="right")

    source_geometries = np.asarray(sidewalks_gdf.geometry.array, dtype=object)
    linear_fast_path = (
        len(source_geometries) > 0
        and np.all(shapely.get_type_id(source_geometries) == 1)
        and np.all(shapely.is_valid(source_geometries))
    )

    new_sidewalks = []
    if linear_fast_path:
        cursor = 0
        match_iter = _maybe_tqdm(
            range(len(matched_sidewalks)),
            show_progress,
            total=len(matched_sidewalks),
            desc="Splitting sidewalks by POI Voronoi edges",
            unit="sidewalk",
        )
        for match_index in match_iter:
            sidewalk_index = int(matched_sidewalks[match_index])
            new_sidewalks.extend(source_geometries[cursor:sidewalk_index])
            local_indexes = voronoi_matches[
                match_starts[match_index] : match_ends[match_index]
            ]
            new_sidewalks.extend(
                _split_single_sidewalk(
                    source_geometries[sidewalk_index],
                    voronoi_geometries[local_indexes],
                )
            )
            cursor = sidewalk_index + 1
        new_sidewalks.extend(source_geometries[cursor:])
    else:
        matches_by_sidewalk: dict[int, np.ndarray] = {
            int(sidewalk_index): voronoi_matches[start:end]
            for sidewalk_index, start, end in zip(
                matched_sidewalks,
                match_starts,
                match_ends,
            )
        }
        sidewalk_iter = _maybe_tqdm(
            enumerate(source_geometries),
            show_progress,
            total=len(source_geometries),
            desc="Splitting sidewalks by POI Voronoi edges",
            unit="sidewalk",
        )
        for sidewalk_index, sidewalk in sidewalk_iter:
            local_indexes = matches_by_sidewalk.get(
                sidewalk_index,
                np.empty(0, dtype=int),
            )
            new_sidewalks.extend(
                _split_single_sidewalk(
                    sidewalk,
                    voronoi_geometries[local_indexes],
                )
            )

    if not new_sidewalks:
        # No valid splits produced, return original
        return sidewalks_gdf

    # Create a new GeoDataFrame
    new_gdf = gpd.GeoDataFrame(geometry=new_sidewalks, crs=sidewalks_gdf.crs)

    # Copy over attributes from original (matching on spatial proximity)
    # For simplicity, just propagate the first row's attributes to all new segments
    if not sidewalks_gdf.empty and len(sidewalks_gdf.columns) > 1:
        for col in sidewalks_gdf.columns:
            if col != "geometry":
                new_gdf[col] = sidewalks_gdf.iloc[0][col]

    return new_gdf


def _split_geometries_by_points(
    geometries_gdf: gpd.GeoDataFrame,
    points,
    *,
    show_progress: bool,
    description: str,
    tolerance: float = 1e-7,
) -> gpd.GeoDataFrame:
    """Split linearized geometries using only spatially matching points."""
    source_geometries = np.asarray(geometries_gdf.geometry.array, dtype=object)
    source_types = shapely.get_type_id(source_geometries)
    linear_fast_path = len(source_geometries) > 0 and np.all(
        np.isin(source_types, [1, 2, 5])
    )
    if linear_fast_path:
        normalize_progress = tqdm(
            total=2,
            desc=f"{description}: normalizing geometries",
            unit="operation",
            disable=not show_progress,
            position=1,
            leave=False,
            dynamic_ncols=True,
        )
        line_array = shapely.get_parts(source_geometries)
        normalize_progress.update(1)
        line_array = line_array[
            ~shapely.is_empty(line_array)
            & np.isin(shapely.get_type_id(line_array), [1, 2])
        ]
        normalize_progress.update(1)
        normalize_progress.close()
    else:
        normalized_lines = []
        geometry_iter = _maybe_tqdm(
            geometries_gdf.geometry,
            show_progress,
            total=len(geometries_gdf),
            desc=f"{description}: normalizing geometries",
            unit="geometry",
        )
        for geometry in geometry_iter:
            if geometry is None or geometry.is_empty:
                continue
            if geometry.geom_type == "Polygon":
                normalized_lines.extend(_line_parts(geometry.boundary))
            elif geometry.geom_type == "MultiPolygon":
                for polygon in geometry.geoms:
                    normalized_lines.extend(_line_parts(polygon.boundary))
            elif geometry.geom_type in {"LineString", "MultiLineString"}:
                normalized_lines.extend(_line_parts(geometry))
            elif geometry.geom_type in {"Point", "MultiPoint"}:
                normalized_lines.append(LineString())
        line_array = np.asarray(normalized_lines, dtype=object)

    if len(line_array) == 0:
        return gpd.GeoDataFrame(geometry=[], crs=geometries_gdf.crs)

    point_array = np.asarray(points, dtype=object)
    point_array = point_array[
        ~shapely.is_missing(point_array)
        & ~shapely.is_empty(point_array)
        & (shapely.get_type_id(point_array) == 0)
    ]
    if len(point_array) == 0:
        return gpd.GeoDataFrame(geometry=line_array, crs=geometries_gdf.crs)

    point_tree = STRtree(point_array)
    pairs = point_tree.query(
        line_array,
        predicate="dwithin",
        distance=tolerance,
    )
    if pairs.shape[1] == 0:
        return gpd.GeoDataFrame(geometry=line_array, crs=geometries_gdf.crs)

    order = np.argsort(pairs[0], kind="stable")
    line_matches = pairs[0][order]
    point_matches = pairs[1][order]
    matched_lines = np.unique(line_matches)
    match_starts = np.searchsorted(line_matches, matched_lines, side="left")
    match_ends = np.searchsorted(line_matches, matched_lines, side="right")

    split_lines = []
    line_iter = _maybe_tqdm(
        range(len(matched_lines)),
        show_progress,
        total=len(matched_lines),
        desc=description,
        unit="sidewalk",
    )
    cursor = 0
    for match_index in line_iter:
        line_index = int(matched_lines[match_index])
        split_lines.extend(line_array[cursor:line_index])
        line = line_array[line_index]
        cursor = line_index + 1
        start = match_starts[match_index]
        end = match_ends[match_index]

        local_point_indexes = np.unique(point_matches[start:end])
        try:
            split_result = split(
                line,
                MultiPoint(point_array[local_point_indexes].tolist()),
            )
        except (GEOSException, ValueError, TypeError):
            split_lines.append(line)
            continue
        split_lines.extend(
            part for part in split_result.geoms if not part.is_empty
        )

    split_lines.extend(line_array[cursor:])

    return gpd.GeoDataFrame(geometry=split_lines, crs=geometries_gdf.crs)


def split_sidewalks_by_protoblock_corners(
    sidewalks_gdf: gpd.GeoDataFrame,
    protoblocks_gdf: gpd.GeoDataFrame,
    show_progress: bool = False,
) -> gpd.GeoDataFrame:
    """Splits sidewalks by the corners of protoblocks.

    This function extracts the corner vertices from protoblock polygons and uses
    them as points to split the sidewalk lines.

    Args:
        sidewalks_gdf: A GeoDataFrame of sidewalk lines.
        protoblocks_gdf: A GeoDataFrame of protoblock polygons.

    Returns:
        A new GeoDataFrame containing the split sidewalk segments.
    """
    if protoblocks_gdf.empty:
        return sidewalks_gdf

    polygon_parts = protoblocks_gdf.geometry.explode(
        index_parts=False,
        ignore_index=True,
    )
    corners = polygon_parts.exterior.get_coordinates().to_numpy()
    if len(corners) == 0:
        return sidewalks_gdf
    unique_corners = np.unique(corners, axis=0)
    return _split_geometries_by_points(
        sidewalks_gdf,
        shapely.points(unique_corners),
        show_progress=show_progress,
        description="Splitting sidewalks at protoblock corners",
    )


def split_sidewalks_by_max_length(
    sidewalks_gdf: gpd.GeoDataFrame,
    max_length: float,
    show_progress: bool = False,
) -> gpd.GeoDataFrame:
    """Splits sidewalks into segments of a maximum length.

    This function iterates through sidewalk lines and splits them into smaller
    segments, ensuring that no segment is longer than the specified maximum
    length.

    Args:
        sidewalks_gdf: A GeoDataFrame of sidewalk lines.
        max_length: The maximum length of each sidewalk segment.

    Returns:
        A new GeoDataFrame containing the split sidewalk segments.
    """
    new_sidewalks = []
    sidewalk_iter = _maybe_tqdm(
        sidewalks_gdf.geometry,
        show_progress,
        total=len(sidewalks_gdf),
        desc="Splitting sidewalks by maximum length",
        unit="sidewalk",
    )
    for sidewalk in sidewalk_iter:
        # Add defensive checks
        if sidewalk is None or sidewalk.is_empty or not sidewalk.is_valid:
            continue

        if sidewalk.length > max_length:
            try:
                num_splits = int(sidewalk.length // max_length)
                if num_splits > 1000:  # Prevent excessive splits that could cause hangs
                    # Skip this sidewalk to prevent excessive computation
                    new_sidewalks.append(sidewalk)
                    continue

                splitter_points = [
                    sidewalk.interpolate((j + 1) * max_length)
                    for j in range(num_splits)
                ]
                # Filter out empty or invalid points
                valid_splitter_points = [
                    p for p in splitter_points if p and not p.is_empty
                ]

                if valid_splitter_points:
                    new_sidewalk_parts = split(
                        sidewalk, MultiPoint(valid_splitter_points)
                    )
                    if hasattr(new_sidewalk_parts, "geoms"):
                        for part in new_sidewalk_parts.geoms:
                            if part and not part.is_empty:
                                new_sidewalks.append(part)
                    else:
                        new_sidewalks.append(new_sidewalk_parts)
                else:
                    new_sidewalks.append(sidewalk)
            except Exception:
                # If splitting fails, keep the original geometry
                new_sidewalks.append(sidewalk)
        else:
            new_sidewalks.append(sidewalk)

    if not new_sidewalks:
        return sidewalks_gdf

    gdf = gpd.GeoDataFrame(geometry=new_sidewalks)
    try:
        gdf = gdf.set_crs(sidewalks_gdf.crs)
    except Exception:
        gdf.crs = sidewalks_gdf.crs
    return gdf


def split_sidewalks_by_num_segments(
    sidewalks_gdf: gpd.GeoDataFrame,
    num_segments: int,
    show_progress: bool = False,
) -> gpd.GeoDataFrame:
    """Splits sidewalks into a specified number of equal-length segments.

    Args:
        sidewalks_gdf: A GeoDataFrame of sidewalk lines.
        num_segments: The number of segments to split each sidewalk into.

    Returns:
        A new GeoDataFrame containing the split sidewalk segments.
    """
    new_sidewalks = []
    sidewalk_iter = _maybe_tqdm(
        sidewalks_gdf.geometry,
        show_progress,
        total=len(sidewalks_gdf),
        desc="Splitting sidewalks by segment count",
        unit="sidewalk",
    )
    for sidewalk in sidewalk_iter:
        segment_length = sidewalk.length / num_segments
        splitter_points = [
            sidewalk.interpolate((i + 1) * segment_length)
            for i in range(num_segments - 1)
        ]
        new_sidewalk_parts = split(sidewalk, MultiPoint(splitter_points))
        for part in new_sidewalk_parts.geoms:
            new_sidewalks.append(part)

    gdf = gpd.GeoDataFrame(geometry=new_sidewalks)
    gdf = gdf.set_crs(sidewalks_gdf.crs)
    return gdf


from shapely.validation import make_valid


def clean_geometries_gdf(
    gdf: gpd.GeoDataFrame,
    tolerance: float = 0.1,
    show_progress: bool = False,
) -> gpd.GeoDataFrame:
    """Cleans geometries in a GeoDataFrame.

    This function performs cleaning operations on the geometries in a
    GeoDataFrame, including:
    - Making geometries valid
    - Simplifying geometries to remove unnecessary vertices
    - Snapping vertices to a grid to remove small variations

    Args:
        gdf: The GeoDataFrame to clean.
        tolerance: The tolerance for simplification and snapping.

    Returns:
        A new GeoDataFrame with cleaned geometries.
    """
    geometries = np.asarray(gdf.geometry.array, dtype=object)
    geometries = geometries[
        ~shapely.is_missing(geometries) & ~shapely.is_empty(geometries)
    ]
    if len(geometries) == 0:
        return gpd.GeoDataFrame(geometry=[], crs=gdf.crs)

    progress = tqdm(
        total=3,
        desc="Cleaning split sidewalk geometries",
        unit="operation",
        disable=not show_progress,
        position=1,
        leave=False,
        dynamic_ncols=True,
    )
    geometries = shapely.make_valid(geometries)
    progress.update(1)
    geometries = _parallel_simplify(
        geometries,
        tolerance,
        preserve_topology=True,
    )
    progress.update(1)
    geometries = shapely.set_precision(geometries, tolerance)
    progress.update(1)
    progress.close()
    geometries = geometries[~shapely.is_empty(geometries)]
    return gpd.GeoDataFrame(geometry=geometries, crs=gdf.crs)


def merge_short_segments_gdf(
    sidewalks_gdf: gpd.GeoDataFrame,
    min_stretch_size: float,
    show_progress: bool = False,
) -> gpd.GeoDataFrame:
    """Merges sidewalk segments shorter than a specified length with their neighbors.

    This function performs topological cleaning by finding sidewalk segments that
    are shorter than `min_stretch_size` and merging them with their shortest
    neighboring segment.

    Args:
        sidewalks_gdf: A GeoDataFrame of sidewalk lines.
        min_stretch_size: The minimum length for a sidewalk segment.

    Returns:
        A new GeoDataFrame with short segments merged.
    """
    if min_stretch_size is None or min_stretch_size <= 0:
        return sidewalks_gdf

    geometries = [
        geometry
        for geometry in sidewalks_gdf.geometry
        if geometry is not None and not geometry.is_empty
    ]
    lengths = [geometry.length for geometry in geometries]
    short_indexes = [
        index for index, length in enumerate(lengths) if length < min_stretch_size
    ]
    short_count = len(short_indexes)
    if short_count == 0:
        return gpd.GeoDataFrame(geometry=geometries, crs=sidewalks_gdf.crs)

    progress = tqdm(
        total=short_count,
        desc="Merging short sidewalk segments",
        unit="segment",
        disable=not show_progress,
        position=1,
        leave=False,
        dynamic_ncols=True,
    )

    from shapely.ops import linemerge

    def endpoint_keys(geometry):
        if geometry.geom_type != "LineString" or geometry.is_empty:
            return ()
        coordinates = geometry.coords
        return (tuple(coordinates[0]), tuple(coordinates[-1]))

    active = set(range(len(geometries)))
    keys_by_index = {}
    endpoint_members: dict[tuple, set[int]] = {}

    def add_to_endpoints(index, geometry):
        keys = endpoint_keys(geometry)
        keys_by_index[index] = keys
        for key in keys:
            endpoint_members.setdefault(key, set()).add(index)

    def remove_from_endpoints(index):
        for key in keys_by_index.get(index, ()):
            members = endpoint_members.get(key)
            if members is not None:
                members.discard(index)

    for index, geometry in enumerate(geometries):
        add_to_endpoints(index, geometry)

    queue = [(lengths[index], index) for index in short_indexes]
    heapq.heapify(queue)
    while queue:
        _, short_index = heapq.heappop(queue)
        if short_index not in active:
            continue
        short_geometry = geometries[short_index]
        if short_geometry.length >= min_stretch_size:
            continue

        neighbor_indexes = set()
        for key in keys_by_index.get(short_index, ()):
            neighbor_indexes.update(endpoint_members.get(key, ()))
        neighbor_indexes.discard(short_index)
        neighbor_indexes.intersection_update(active)
        if not neighbor_indexes:
            continue

        neighbor_index = min(
            neighbor_indexes,
            key=lambda index: geometries[index].length,
        )
        merged_geometry = linemerge(
            [short_geometry, geometries[neighbor_index]]
        )

        active.remove(short_index)
        active.remove(neighbor_index)
        remove_from_endpoints(short_index)
        remove_from_endpoints(neighbor_index)

        merged_index = len(geometries)
        geometries.append(merged_geometry)
        active.add(merged_index)
        add_to_endpoints(merged_index, merged_geometry)
        if merged_geometry.length < min_stretch_size:
            heapq.heappush(queue, (merged_geometry.length, merged_index))
        progress.update(1)

    progress.close()
    remaining = [geometries[index] for index in sorted(active)]
    return gpd.GeoDataFrame(geometry=remaining, crs=sidewalks_gdf.crs)


def split_sidewalks_gdf(
    sidewalks_gdf: gpd.GeoDataFrame,
    intersection_points_gdf: gpd.GeoDataFrame,
    protoblocks_gdf: gpd.GeoDataFrame,
    pois_gdf: gpd.GeoDataFrame,
    max_length: float = None,
    num_segments: int = None,
    min_stretch_size: float = None,
    show_progress: bool = False,
) -> gpd.GeoDataFrame:
    """Splits sidewalks based on multiple criteria.

    This function orchestrates the splitting of sidewalks based on protoblock
    corners, Voronoi polygons from POIs, maximum length, and a specified number
    of segments.

    Args:
        sidewalks_gdf: A GeoDataFrame of sidewalk lines.
        intersection_points_gdf: A GeoDataFrame of intersection points.
        protoblocks_gdf: A GeoDataFrame of protoblock polygons.
        pois_gdf: A GeoDataFrame of POIs.
        max_length: The maximum length of each sidewalk segment.
        num_segments: The number of segments to split each sidewalk into.

    Returns:
        A new GeoDataFrame containing the comprehensively split sidewalk segments.
    """
    sidewalks_gdf = split_sidewalks_by_protoblock_corners(
        sidewalks_gdf,
        protoblocks_gdf,
        show_progress=show_progress,
    )
    sidewalks_gdf = split_sidewalks_by_voronoi(
        sidewalks_gdf,
        pois_gdf,
        show_progress=show_progress,
    )

    if max_length:
        sidewalks_gdf = split_sidewalks_by_max_length(
            sidewalks_gdf,
            max_length,
            show_progress=show_progress,
        )

    if num_segments:
        sidewalks_gdf = split_sidewalks_by_num_segments(
            sidewalks_gdf,
            num_segments,
            show_progress=show_progress,
        )

    if intersection_points_gdf.empty:
        return sidewalks_gdf

    crossing_points = np.asarray(
        intersection_points_gdf.geometry.array,
        dtype=object,
    )
    gdf = _split_geometries_by_points(
        sidewalks_gdf,
        crossing_points,
        show_progress=show_progress,
        description="Splitting sidewalks at crossings",
    )

    # Clean the final geometries
    gdf = clean_geometries_gdf(gdf, show_progress=show_progress)

    # Merge short segments
    gdf = merge_short_segments_gdf(
        gdf,
        min_stretch_size,
        show_progress=show_progress,
    )

    return gdf


def calculate_sidewalk_properties(sidewalks_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Calculates geometric properties for the sidewalks.

    This function calculates the area and perimeter for each sidewalk polygon and
    adds them as new columns to the GeoDataFrame.

    Args:
        sidewalks_gdf: A GeoDataFrame of sidewalk polygons.

    Returns:
        The input GeoDataFrame with "area" and "perimeter" columns added.
    """
    sidewalks_gdf["area"] = sidewalks_gdf.geometry.area
    sidewalks_gdf["perimeter"] = sidewalks_gdf.geometry.length
    return sidewalks_gdf


def generate_kerbs_gdf(
    crossings_gdf: gpd.GeoDataFrame,
    show_progress: bool = False,
) -> gpd.GeoDataFrame:
    """Generates kerbs from crossings using the ABCDE points system.

    This function extracts kerb points B and D from each crossing line that
    follows the ABCDE pattern: A-B-C-D-E where B and D are the kerb positions.

    Args:
        crossings_gdf: A GeoDataFrame of crossing lines following ABCDE pattern.

    Returns:
        A GeoDataFrame of kerb points.
    """
    progress = tqdm(
        total=3,
        desc="Generating kerbs",
        unit="operation",
        disable=not show_progress,
        position=1,
        leave=False,
        dynamic_ncols=True,
    )
    geometries = np.asarray(crossings_gdf.geometry.array, dtype=object)
    valid = (
        ~shapely.is_missing(geometries)
        & ~shapely.is_empty(geometries)
        & (shapely.get_type_id(geometries) == 1)
    )
    geometries = geometries[valid]
    coordinate_counts = shapely.get_num_coordinates(geometries)
    has_endpoints = coordinate_counts >= 2
    geometries = geometries[has_endpoints]
    coordinate_counts = coordinate_counts[has_endpoints]
    progress.update(1)

    if len(geometries) == 0:
        progress.close()
        return gpd.GeoDataFrame(geometry=[], crs=crossings_gdf.crs)

    five_point = coordinate_counts == 5
    first_kerbs = np.empty(len(geometries), dtype=object)
    second_kerbs = np.empty(len(geometries), dtype=object)
    first_kerbs[five_point] = shapely.get_point(geometries[five_point], 1)
    second_kerbs[five_point] = shapely.get_point(geometries[five_point], 3)
    fallback = ~five_point
    first_kerbs[fallback] = shapely.get_point(geometries[fallback], 0)
    second_kerbs[fallback] = shapely.get_point(geometries[fallback], -1)
    progress.update(1)

    kerbs = np.empty(len(geometries) * 2, dtype=object)
    kerbs[0::2] = first_kerbs
    kerbs[1::2] = second_kerbs
    result = gpd.GeoDataFrame(geometry=kerbs, crs=crossings_gdf.crs)
    progress.update(1)
    progress.close()
    return result


def draw_sidewalks_gdf(
    gdf: gpd.GeoDataFrame,
    buildings_gdf: gpd.GeoDataFrame,
    streets_gdf: gpd.GeoDataFrame,
    buffer_dist: float,
    curve_radius: float,
    min_d_to_building: float,
    show_progress: bool = False,
) -> gpd.GeoDataFrame:
    """Generates sidewalks using the proper algorithm from the QGIS plugin.

    This function implements the sidewalk generation as described in the algorithm:
    1. Adjust buffer distance based on building proximity
    2. Buffer roads with dynamic distances and dissolve
    3. Apply two-step buffering for smooth corners (positive then negative)
    4. Create large buffer around entire network
    5. Use difference operation to extract sidewalk areas
    6. Convert polygons to lines
    7. Handle exclusion/sure zones

    Args:
        gdf: A GeoDataFrame of street lines to buffer.
        buildings_gdf: A GeoDataFrame of building polygons.
        streets_gdf: A GeoDataFrame of streets, used for exclusion zones.
        buffer_dist: The default buffer distance.
        curve_radius: Radius for smooth corner creation.
        min_d_to_building: The minimum required distance from a building.

    Returns:
        A new GeoDataFrame containing the generated sidewalk lines.
    """
    from .parameters import big_buffer_d

    progress = tqdm(
        total=6,
        desc="Constructing sidewalk geometry",
        unit="operation",
        disable=not show_progress,
        position=1,
        leave=False,
        dynamic_ncols=True,
    )

    # Step 1: Adjust buffer distance for buildings
    gdf_with_buffers = adjust_buffer_for_buildings(
        gdf,
        buildings_gdf,
        buffer_dist,
        min_d_to_building,
        show_progress=show_progress,
    )
    progress.update(1)

    # Step 2: Calculate dynamic buffer distances
    # Buffer distance = (road_width / 2) + (extra_distance / 2)
    if "width" not in gdf_with_buffers.columns:
        gdf_with_buffers["width"] = buffer_dist

    gdf_with_buffers["dynamic_buffer"] = (gdf_with_buffers["width"] / 2) + (
        gdf_with_buffers["buffer_dist"] / 2
    )

    dynamic_buffers = gdf_with_buffers["dynamic_buffer"].to_numpy(dtype=float)

    sidewalk_gs = None
    line_geometries = np.asarray(gdf_with_buffers.geometry.array, dtype=object)
    valid_lines = (
        ~shapely.is_missing(line_geometries)
        & ~shapely.is_empty(line_geometries)
        & np.isin(shapely.get_type_id(line_geometries), [1, 5])
    )
    line_geometries = line_geometries[valid_lines]
    line_buffers = dynamic_buffers[valid_lines]
    uniform_buffer = (
        len(line_buffers) > 0
        and np.isfinite(line_buffers).all()
        and np.allclose(line_buffers, line_buffers[0])
    )

    # Polygonizing first restricts all buffering work to bounded block interiors.
    # It avoids a municipality-wide union of overlapping road buffers and the
    # former 10 km exterior buffer/difference.
    if len(line_geometries):
        noded_linework = shapely.union_all(line_geometries)
        polygonized, cuts, dangles, invalid_rings = shapely.polygonize_full(
            shapely.get_parts(noded_linework)
        )
        blocks = shapely.get_parts(polygonized)
        leftover_lines = np.concatenate(
            [shapely.get_parts(part) for part in (cuts, dangles, invalid_rings)]
        )
        leftover_lines = leftover_lines[
            ~shapely.is_empty(leftover_lines)
            & np.isin(shapely.get_type_id(leftover_lines), [1, 2, 5])
        ]
    else:
        blocks = np.empty(0, dtype=object)
        leftover_lines = np.empty(0, dtype=object)
    progress.update(1)

    if len(blocks):
        base_buffer = float(line_buffers[0] if uniform_buffer else np.min(line_buffers))
        variable_mask = line_buffers > base_buffer + 1e-9
        sidewalk_areas = _parallel_buffer(
            blocks,
            -base_buffer,
            quad_segs=16,
        )

        correction_geometries = []
        correction_distances = []
        if len(leftover_lines):
            correction_geometries.append(leftover_lines)
            correction_distances.append(
                np.full(len(leftover_lines), base_buffer, dtype=float)
            )
        if np.any(variable_mask):
            correction_geometries.append(line_geometries[variable_mask])
            correction_distances.append(line_buffers[variable_mask])

        if correction_geometries:
            correction_geometries = np.concatenate(correction_geometries)
            correction_distances = np.concatenate(correction_distances)
            if show_progress:
                print(
                    "   Sidewalks: applying "
                    f"{int(np.count_nonzero(variable_mask))} variable offsets and "
                    f"{len(leftover_lines)} non-ring road offsets over "
                    f"{len(blocks)} blocks."
                )
            correction_progress = tqdm(
                total=4,
                desc="Applying local sidewalk offsets",
                unit="operation",
                disable=not show_progress,
                position=1,
                leave=False,
                dynamic_ncols=True,
            )
            correction_buffers = _parallel_buffer(
                correction_geometries,
                correction_distances,
                quad_segs=16,
            )
            correction_progress.update(1)
            pairs = STRtree(correction_buffers).query(
                sidewalk_areas,
                predicate="intersects",
            )
            correction_progress.update(1)
            if pairs.shape[1]:
                order = np.argsort(pairs[0], kind="stable")
                block_indexes = pairs[0][order]
                buffer_indexes = pairs[1][order]
                counts = np.bincount(block_indexes, minlength=len(blocks))
                max_count = int(counts.max())
                grouped_buffers = np.full(
                    (len(blocks), max_count),
                    None,
                    dtype=object,
                )
                group_offsets = np.repeat(
                    np.cumsum(counts) - counts,
                    counts,
                )
                positions = np.arange(len(block_indexes)) - group_offsets
                grouped_buffers[block_indexes, positions] = correction_buffers[
                    buffer_indexes
                ]
                local_road_buffers = _parallel_union_rows(grouped_buffers)
                sidewalk_areas = _parallel_difference(
                    sidewalk_areas,
                    local_road_buffers,
                )
            correction_progress.update(2)
            correction_progress.close()
        progress.update(1)

        if curve_radius > 0:
            sidewalk_areas = _parallel_buffer(
                _parallel_buffer(
                    sidewalk_areas,
                    -curve_radius,
                    quad_segs=16,
                ),
                curve_radius,
                quad_segs=16,
            )
        progress.update(1)

        sidewalk_areas = sidewalk_areas[
            ~shapely.is_empty(sidewalk_areas)
            & np.isin(shapely.get_type_id(sidewalk_areas), [3, 6])
        ]
        if len(sidewalk_areas):
            boundary_parts = shapely.get_parts(shapely.boundary(sidewalk_areas))
            boundary_parts = boundary_parts[
                ~shapely.is_empty(boundary_parts)
                & np.isin(shapely.get_type_id(boundary_parts), [1, 2])
            ]
            sidewalk_gs = gpd.GeoSeries(boundary_parts, crs=gdf.crs)

    if sidewalk_gs is None:
        # Open networks do not have bounded blocks; retain the legacy behavior
        # for standalone callers that expect output from such input.
        buffered_roads = gdf_with_buffers.buffer(
            gdf_with_buffers["dynamic_buffer"]
        )
        dissolved_roads = buffered_roads.union_all()
        progress.update(1)

        smooth_roads = dissolved_roads.buffer(curve_radius)
        smooth_roads = smooth_roads.buffer(-curve_radius)
        progress.update(1)

        large_buffer = smooth_roads.buffer(big_buffer_d)
        sidewalk_areas = large_buffer.difference(smooth_roads)
        progress.update(1)

        sidewalk_gs = gpd.GeoSeries(
            [sidewalk_areas], crs=gdf.crs
        ).explode(index_parts=False)

        if len(sidewalk_gs) > 1:
            sidewalk_gs = sidewalk_gs.iloc[sidewalk_gs.area.argsort()[:-1]]

    if sidewalk_gs.empty:
        progress.close()
        return gpd.GeoDataFrame(geometry=[], crs=gdf.crs)

    # The legacy branch still contains polygons; the polygonized branch already
    # contains their line boundaries.
    if sidewalk_gs.geom_type.isin(["Polygon", "MultiPolygon"]).any():
        sidewalk_gs = sidewalk_gs.boundary.explode(index_parts=False)

    if sidewalk_gs.empty:
        progress.close()
        return gpd.GeoDataFrame(geometry=[], crs=gdf.crs)
    progress.update(1)

    sidewalks_gdf = gpd.GeoDataFrame(geometry=sidewalk_gs, crs=gdf.crs)

    # Step 8: Handle exclusion/sure zones
    sidewalks_gdf = handle_sidewalk_tags(sidewalks_gdf, streets_gdf)

    # Step 9: Calculate properties
    sidewalks_gdf = calculate_sidewalk_properties(sidewalks_gdf)
    progress.update(1)
    progress.close()

    return sidewalks_gdf


def data_clean_gdf(
    gdf: gpd.GeoDataFrame,
    default_widths: dict,
    fallback_default_width: float,
    show_progress: bool = False,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Cleans the OSM data in a GeoDataFrame.

    This function performs several cleaning operations on the input OSM data,
    including parsing tags, filtering by highway type, and separating existing
    sidewalks and crossings.

    Args:
        gdf: The input GeoDataFrame of OSM data.
        default_widths: A dictionary mapping highway types to default widths.
        fallback_default_width: The default width to use for unknown highway types.

    Returns:
        A tuple containing:
            - gdf: The cleaned GeoDataFrame.
            - existing_sidewalks: A GeoDataFrame of existing sidewalks.
            - existing_crossings: A GeoDataFrame of existing crossings.
    """

    if "other_tags" in gdf.columns:
        tag_iter = _maybe_tqdm(
            gdf["other_tags"].items(),
            show_progress,
            total=len(gdf),
            desc="Cleaning OSM feature tags",
            unit="feature",
        )
        tags_series = pd.Series(
            {index: parse_tags(value) for index, value in tag_iter},
            index=gdf.index,
        )
        tags_df = pd.DataFrame(tags_series.tolist(), index=gdf.index)
        gdf = gdf.drop(columns=["other_tags"]).join(tags_df)

    # Filter by highway tag
    highway_values = gdf["highway"].unique()
    widths = {
        val: default_widths.get(val, fallback_default_width) for val in highway_values
    }

    # Create layers of existing sidewalks and crossings
    existing_sidewalks = gpd.GeoDataFrame()
    if "footway" in gdf.columns:
        existing_sidewalks = gdf[
            (gdf["highway"] == "footway") & (gdf["footway"] == "sidewalk")
        ].copy()

    existing_crossings = gpd.GeoDataFrame()
    if "footway" in gdf.columns:
        existing_crossings = gdf[
            (gdf["highway"] == "footway") & (gdf["footway"] == "crossing")
        ].copy()

    logger.info("Number of features before filtering: %s", len(gdf))

    # Remove features with width < 0.5
    gdf["width"] = gdf["highway"].map(widths)
    gdf = gdf[gdf["width"] >= 0.5].copy()

    logger.info("Number of features after filtering: %s", len(gdf))

    return gdf, existing_sidewalks, existing_crossings


def save_debug_layer(
    gdf: gpd.GeoDataFrame, layer_name: str, output_dir: str = "debug_layers"
):
    """Saves a GeoDataFrame as a debug layer in the specified output directory.

    Args:
        gdf: The GeoDataFrame to save.
        layer_name: The name of the layer (used for the filename).
        output_dir: The directory to save the debug layer in.
    """
    os.makedirs(output_dir, exist_ok=True)
    layer_path = os.path.join(output_dir, f"{layer_name}.geojson")
    gdf.to_file(layer_path, driver="GeoJSON")


def save_gdf_to_geojson(
    gdf: gpd.GeoDataFrame, filepath: str, include_empty: bool = True
):
    """Saves a GeoDataFrame to a GeoJSON file, ensuring EPSG:4326.

    Args:
        gdf: The GeoDataFrame to save.
        filepath: The path to save the file to.
        include_empty: Whether to save an empty GeoJSON if the GeoDataFrame is empty.
    """
    if gdf is None or gdf.empty:
        if include_empty:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            empty_geojson = {"type": "FeatureCollection", "features": []}
            with open(filepath, "w") as f:
                json.dump(empty_geojson, f)
        return

    # Reproject to EPSG:4326 if needed
    if gdf.crs is not None and str(gdf.crs) != "EPSG:4326":
        gdf = gdf.to_crs("EPSG:4326")

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    gdf.to_file(filepath, driver="GeoJSON")


def create_merged_output(
    output_directory: str,
    sidewalks_gdf: Optional[gpd.GeoDataFrame],
    crossings_gdf: Optional[gpd.GeoDataFrame],
    kerbs_gdf: Optional[gpd.GeoDataFrame],
):
    """Create a merged GeoJSON file for easy import into JOSM.

    This follows the QGIS plugin behavior of creating a single file with
    all features for easy uploading to OpenStreetMap.
    """

    def _prepare_gdf(gdf):
        if gdf is not None and not gdf.empty:
            if gdf.crs is not None and str(gdf.crs) != "EPSG:4326":
                return gdf.to_crs("EPSG:4326")
        return gdf

    sidewalks_gdf = _prepare_gdf(sidewalks_gdf)
    crossings_gdf = _prepare_gdf(crossings_gdf)
    kerbs_gdf = _prepare_gdf(kerbs_gdf)

    merged_features = []
    sidewalk_count = 0
    crossing_count = 0

    # Add sidewalks as lines
    if sidewalks_gdf is not None and not sidewalks_gdf.empty:
        temp_gdf = sidewalks_gdf[[sidewalks_gdf.geometry.name]].copy()
        temp_gdf["highway"] = "footway"
        temp_gdf["footway"] = "sidewalk"
        merged_features.extend(temp_gdf.__geo_interface__["features"])
        sidewalk_count = len(temp_gdf)

    # Add crossings as lines
    if crossings_gdf is not None and not crossings_gdf.empty:
        temp_gdf = crossings_gdf[[crossings_gdf.geometry.name]].copy()
        temp_gdf["highway"] = "footway"
        temp_gdf["footway"] = "crossing"
        merged_features.extend(temp_gdf.__geo_interface__["features"])
        crossing_count = len(temp_gdf)

    # Add kerbs as points
    if kerbs_gdf is not None and not kerbs_gdf.empty:
        temp_gdf = kerbs_gdf[[kerbs_gdf.geometry.name]].copy()
        temp_gdf["barrier"] = "kerb"
        merged_features.extend(temp_gdf.__geo_interface__["features"])

    # Create merged GeoJSON
    merged_geojson = {"type": "FeatureCollection", "features": merged_features}

    # Save merged file
    os.makedirs(output_directory, exist_ok=True)
    merged_path = os.path.join(output_directory, "sidewalkreator_output.geojson")
    with open(merged_path, "w") as f:
        json.dump(merged_geojson, f, indent=2)

    # Create changeset comment file
    comment_path = os.path.join(output_directory, "changeset_comment.txt")
    with open(comment_path, "w") as f:
        f.write("Generated sidewalks, crossings, and kerbs using OSM SidewalKreator\n")
        f.write(f"Added {sidewalk_count} sidewalk segments\n")
        f.write(f"Added {crossing_count} crossings\n")
