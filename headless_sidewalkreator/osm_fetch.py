# -*- coding: utf-8 -*-
"""
Lightweight replacement for previous `osm_fetch` helpers implemented using OSMnx.

Provides:
- osm_query_string_by_bbox(bbox, tags)
- get_osm_data(bbox, tags=None, timeout=60, max_retries=2)

The bbox expected shape is (minx, miny, maxx, maxy) (same as GeoDataFrame.total_bounds).
"""

from typing import Dict, Tuple, Optional
import time
import logging

import osmnx as ox
import geopandas as gpd

logger = logging.getLogger(__name__)


def _normalize_bbox(
    bbox: Tuple[float, float, float, float]
) -> Tuple[float, float, float, float]:
    """Converts a (minx, miny, maxx, maxy) bbox to (north, south, east, west).

    Args:
        bbox: A tuple representing the bounding box as (minx, miny, maxx, maxy).

    Returns:
        A tuple representing the bounding box as (north, south, east, west).
    """
    minx, miny, maxx, maxy = bbox
    south = miny
    west = minx
    north = maxy
    east = maxx
    return north, south, east, west


def osm_query_string_by_bbox(bbox: Tuple[float, float, float, float], tags: Optional[Dict[str, object]] = None) -> str:
    """Return a simple Overpass QL query string for the bbox and tags.

    This is a convenience helper: it does not attempt to be exhaustive but
    produces a readable query usable with Overpass API if needed.

    Args:
        bbox: (minx, miny, maxx, maxy)
        tags: dict of tag -> value. If value is True it means any value for that key.

    Returns:
        Overpass QL query string (text).
    """
    north, south, east, west = _normalize_bbox(bbox)
    if tags is None:
        tags = {"highway": True, "building": True, "amenity": True, "shop": True}

    filters = []
    for k, v in tags.items():
        if v is True:
            filters.append(f'[{k}]')
        else:
            # assume simple equality
            filters.append(f'[{k}="{v}"]')

    bbox_str = f"{south},{west},{north},{east}"

    # basic query fetching nodes/ways/relations with the tags
    filters_str = ";".join(filters)
    query = f"(node{filters_str}({bbox_str});way{filters_str}({bbox_str});rel{filters_str}({bbox_str}););out geom;"
    return query


def get_osm_data(bbox: Tuple[float, float, float, float], tags: Optional[Dict[str, object]] = None, timeout: int = 60, max_retries: int = 2) -> gpd.GeoDataFrame:
    """Fetch OSM data for a bbox using OSMnx `geometries_from_bbox`.

    Args:
        bbox: (minx, miny, maxx, maxy)
        tags: mapping of tag -> value (see OSMnx docs). If None a default set is used.
        timeout: request timeout in seconds (passed to OSMnx internals where supported).
        max_retries: number of retries on error.

    Returns:
        GeoDataFrame with OSM features (may be empty on failures).
    """
    north, south, east, west = _normalize_bbox(bbox)
    if tags is None:
        tags = {"highway": True, "building": True, "amenity": True, "shop": True}

    # Prefer the new OSMnx features API when available; fall back to
    # older geometries_* names for backward compatibility. The
    # functions accept (north, south, east, west, tags).
    fetch_func = None
    # Newer OSMnx may expose a top-level helper `features_from_bbox`.
    if hasattr(ox, "features_from_bbox"):
        fetch_func = getattr(ox, "features_from_bbox")
    # Older API used `geometries_from_bbox` at top-level
    elif hasattr(ox, "geometries_from_bbox"):
        fetch_func = getattr(ox, "geometries_from_bbox")
    # Or OSMnx may expose a `features` module with the function
    elif hasattr(ox, "features") and hasattr(ox.features, "features_from_bbox"):
        fetch_func = getattr(ox.features, "features_from_bbox")
    elif hasattr(ox, "features") and hasattr(ox.features, "geometries_from_bbox"):
        fetch_func = getattr(ox.features, "geometries_from_bbox")

    if fetch_func is None:
        raise RuntimeError("No suitable OSMnx bbox fetch function found (features_from_bbox or geometries_from_bbox)")

    attempt = 0
    last_exc = None
    while attempt <= max_retries:
        try:
            result = fetch_func(north, south, east, west, tags)

            # OSMnx may return a GeoDataFrame, a Pandas DataFrame-like, or in
            # some calls a NetworkX graph (if other ox functions are used).
            # Normalize to a GeoDataFrame of features:
            if isinstance(result, gpd.GeoDataFrame):
                gdf = result
            else:
                # If it's a graph-like object (duck-typed), convert to an
                # edge GeoDataFrame using OSMnx helper. We avoid importing
                # networkx here to keep this module lightweight and to
                # prevent static import errors in environments without it.
                if hasattr(result, 'nodes') and hasattr(result, 'edges'):
                    try:
                        gdf = ox.utils_graph.graph_to_gdfs(result, nodes=False, fill_edge_geometry=True)
                    except Exception:
                        # conversion failed; fall back to coercion
                        gdf = gpd.GeoDataFrame(result)
                else:
                    # fallback: coerce to GeoDataFrame directly
                    gdf = gpd.GeoDataFrame(result)

            # Ensure there's a geometry column and a CRS; if missing, try to infer
            if 'geometry' not in gdf.columns and hasattr(gdf, 'geom_type') is False:
                # nothing we can do; create an empty GeoDataFrame
                gdf = gpd.GeoDataFrame(columns=['geometry'])

            # If CRS is missing, set to WGS84 (OSM default)
            if gdf.crs is None:
                try:
                    gdf.set_crs(epsg=4326, inplace=True)
                except Exception:
                    # as a last resort, copy with crs
                    gdf = gdf.copy()
                    gdf.crs = 'EPSG:4326'

            return gdf
        except Exception as e:
            last_exc = e
            logger.warning("OSM data fetch failed on attempt %d: %s", attempt + 1, e)
            attempt += 1
            time.sleep(1 + attempt)

    # if we reached here, raise the last exception for visibility
    logger.error("Failed to fetch OSM data after %d attempts: %s", max_retries + 1, last_exc)
    raise RuntimeError(f"Failed to fetch OSM data: {last_exc}")
