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
    bbox: Tuple[float, float, float, float],
) -> Tuple[float, float, float, float]:
    """Converts a (minx, miny, maxx, maxy) bbox to OSMnx format (west, south, east, north).

    OSMnx features_from_bbox expects (left, bottom, right, top) which corresponds to
    (west, south, east, north) in geographic coordinates.

    Args:
        bbox: A tuple representing the bounding box as (minx, miny, maxx, maxy).
              In EPSG:4326, this is (min_lon, min_lat, max_lon, max_lat).

    Returns:
        A tuple representing the bounding box as (west, south, east, north) for OSMnx.
    """
    minx, miny, maxx, maxy = bbox
    north = maxy
    south = miny
    east = maxx
    west = minx
    return north, south, east, west


def osm_query_string_by_bbox(
    bbox: Tuple[float, float, float, float], tags: Optional[Dict[str, object]] = None
) -> str:
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
        tags = {
            "highway": True,
            "building": True,
            "amenity": True,
            "shop": True,
            "addr:housenumber": True,
        }

    filters = []
    for k, v in tags.items():
        if v is True:
            filters.append(f"[{k}]")
        else:
            # assume simple equality
            filters.append(f'[{k}="{v}"]')

    bbox_str = f"{south},{west},{north},{east}"

    # basic query fetching nodes/ways/relations with the tags
    filters_str = ";".join(filters)
    query = f"(node{filters_str}({bbox_str});way{filters_str}({bbox_str});rel{filters_str}({bbox_str}););out geom;"
    return query


def get_osm_data(
    bbox: Tuple[float, float, float, float],
    tags: Optional[Dict[str, object]] = None,
    timeout: int = 60,
    max_retries: int = 2,
) -> gpd.GeoDataFrame:
    """Fetch OSM data for a bbox using OSMnx `features_from_bbox`.

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
        tags = {
            "highway": True,
            "building": True,
            "amenity": True,
            "shop": True,
            "addr:housenumber": True,
        }

    # Configure OSMnx settings for better timeout handling
    original_timeout = ox.settings.requests_timeout
    original_max_area = ox.settings.max_query_area_size

    try:
        # Temporarily adjust OSMnx settings
        ox.settings.requests_timeout = max(timeout, 60)  # Use at least 60 seconds
        # Increase max query area to reduce subdivisions that cause timeouts
        ox.settings.max_query_area_size = max(original_max_area, 50000 * 50000)

        logger.info(
            f"Fetching OSM data for bbox {bbox} with timeout {ox.settings.requests_timeout}s"
        )

        # Use the modern OSMnx features API.
        # The features_from_bbox function is preferred. It was introduced in
        # OSMnx 1.2.0, and this package requires >=1.4.
        fetch_func = None
        if hasattr(ox, "features_from_bbox"):
            fetch_func = ox.features_from_bbox
        elif hasattr(ox, "features") and hasattr(ox.features, "features_from_bbox"):
            fetch_func = ox.features.features_from_bbox
        else:
            # This path should not be taken with modern OSMnx versions.
            raise RuntimeError(
                "No suitable OSMnx bbox fetch function found (features_from_bbox)"
            )

        attempt = 0
        last_exc = None
        while attempt <= max_retries:
            try:
                logger.info(f"OSM fetch attempt {attempt + 1}/{max_retries + 1}")
                # The modern features_from_bbox API expects (west, south, east, north)
                # which corresponds to (left, bottom, right, top)
                result = fetch_func((west, south, east, north), tags)

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
                    if hasattr(result, "nodes") and hasattr(result, "edges"):
                        try:
                            gdf = ox.utils_graph.graph_to_gdfs(
                                result, nodes=False, fill_edge_geometry=True
                            )
                        except Exception:
                            # conversion failed; fall back to coercion
                            gdf = gpd.GeoDataFrame(result)
                    else:
                        # fallback: coerce to GeoDataFrame directly
                        gdf = gpd.GeoDataFrame(result)

                # Ensure there's a geometry column and a CRS; if missing, try to infer
                if "geometry" not in gdf.columns and hasattr(gdf, "geom_type") is False:
                    # nothing we can do; create an empty GeoDataFrame
                    gdf = gpd.GeoDataFrame(columns=["geometry"])

                # If CRS is missing, set to WGS84 (OSM default)
                if gdf.crs is None:
                    try:
                        gdf.set_crs(epsg=4326, inplace=True)
                    except Exception:
                        # as a last resort, copy with crs
                        gdf = gdf.copy()
                        gdf.crs = "EPSG:4326"

                logger.info(f"Successfully fetched {len(gdf)} OSM features")
                return gdf

            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "OSM data fetch failed on attempt %d: %s", attempt + 1, exc
                )
                attempt += 1
                if attempt <= max_retries:
                    wait_time = min(2**attempt, 10)  # exponential backoff, max 10s
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)

        # All retries failed
        logger.error(
            "Failed to fetch OSM data after %d attempts: %s", max_retries + 1, last_exc
        )
        # Return empty GeoDataFrame instead of raising an error to prevent timeouts from stopping the entire process
        return gpd.GeoDataFrame(columns=["geometry"])

    finally:
        # Always restore original OSMnx settings
        ox.settings.requests_timeout = original_timeout
        ox.settings.max_query_area_size = original_max_area
