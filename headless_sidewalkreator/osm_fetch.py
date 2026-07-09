# -*- coding: utf-8 -*-
"""
Lightweight replacement for previous `osm_fetch` helpers implemented using OSMnx.

Provides:
- osm_query_string_by_bbox(bbox, tags)
- get_osm_data(bbox, tags=None, timeout=60, max_retries=2, provider=None, **kwargs)

The bbox expected shape is (minx, miny, maxx, maxy) (same as GeoDataFrame.total_bounds).
"""

from typing import Dict, Tuple, Optional, Any
import time
import logging

import osmnx as ox
import geopandas as gpd

from .planet_download import OvertureDownloader, ProtomapsDownloader

logger = logging.getLogger(__name__)


def _normalize_bbox(
    bbox: Tuple[float, float, float, float],
) -> Tuple[float, float, float, float]:
    """Converts a (minx, miny, maxx, maxy) bbox to OSMnx format (west, south, east, north)."""
    minx, miny, maxx, maxy = bbox
    north = maxy
    south = miny
    east = maxx
    west = minx
    return north, south, east, west


def osm_query_string_by_bbox(
    bbox: Tuple[float, float, float, float], tags: Optional[Dict[str, object]] = None
) -> str:
    """Return a simple Overpass QL query string for the bbox and tags."""
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
            filters.append(f'[{k}="{v}"]')

    bbox_str = f"{south},{west},{north},{east}"
    filters_str = ";".join(filters)
    query = f"(node{filters_str}({bbox_str});way{filters_str}({bbox_str});rel{filters_str}({bbox_str}););out geom;"
    return query


def get_osm_data(
    bbox: Tuple[float, float, float, float],
    tags: Optional[Dict[str, object]] = None,
    timeout: int = 60,
    max_retries: int = 2,
    provider: Optional[str] = None,
    **kwargs
) -> gpd.GeoDataFrame:
    """Fetch OSM data for a bbox using either OSMnx or a planet downloader.

    Args:
        bbox: (minx, miny, maxx, maxy)
        tags: mapping of tag -> value.
        timeout: request timeout in seconds.
        max_retries: number of retries on error.
        provider: 'overture', 'protomaps', or None (default to OSMnx/Overpass).
        **kwargs: Provider-specific arguments.

    Returns:
        GeoDataFrame with features.
    """
    if provider == "overture":
        downloader = OvertureDownloader(**kwargs)
        return downloader.get_data(bbox, tags)
    elif provider == "protomaps":
        downloader = ProtomapsDownloader(**kwargs)
        return downloader.get_data(bbox, tags)

    # Default to OSMnx
    north, south, east, west = _normalize_bbox(bbox)
    if tags is None:
        tags = {
            "highway": True,
            "building": True,
            "amenity": True,
            "shop": True,
            "addr:housenumber": True,
        }

    original_timeout = ox.settings.requests_timeout
    original_max_area = ox.settings.max_query_area_size

    try:
        ox.settings.requests_timeout = max(timeout, 60)
        ox.settings.max_query_area_size = max(original_max_area, 50000 * 50000)

        logger.info(f"Fetching OSM data for bbox {bbox} using OSMnx")

        fetch_func = None
        if hasattr(ox, "features_from_bbox"):
            fetch_func = ox.features_from_bbox
        elif hasattr(ox, "features") and hasattr(ox.features, "features_from_bbox"):
            fetch_func = ox.features.features_from_bbox
        else:
            raise RuntimeError("No suitable OSMnx bbox fetch function found")

        attempt = 0
        last_exc = None
        while attempt <= max_retries:
            try:
                result = fetch_func((west, south, east, north), tags)
                if isinstance(result, gpd.GeoDataFrame):
                    gdf = result
                else:
                    if hasattr(result, "nodes") and hasattr(result, "edges"):
                        try:
                            gdf = ox.utils_graph.graph_to_gdfs(result, nodes=False, fill_edge_geometry=True)
                        except Exception:
                            gdf = gpd.GeoDataFrame(result)
                    else:
                        gdf = gpd.GeoDataFrame(result)

                if "geometry" not in gdf.columns and hasattr(gdf, "geom_type") is False:
                    gdf = gpd.GeoDataFrame(columns=["geometry"])

                if gdf.crs is None:
                    try:
                        gdf.set_crs(epsg=4326, inplace=True)
                    except Exception:
                        gdf = gdf.copy()
                        gdf.crs = "EPSG:4326"

                logger.info(f"Successfully fetched {len(gdf)} features")
                return gdf

            except Exception as exc:
                last_exc = exc
                logger.warning("Fetch failed on attempt %d: %s", attempt + 1, exc)
                attempt += 1
                if attempt <= max_retries:
                    time.sleep(min(2**attempt, 10))

        logger.error("Failed to fetch OSM data after %d attempts: %s", max_retries + 1, last_exc)
        return gpd.GeoDataFrame(columns=["geometry"])

    finally:
        ox.settings.requests_timeout = original_timeout
        ox.settings.max_query_area_size = original_max_area
