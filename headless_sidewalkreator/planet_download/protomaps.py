import logging
from typing import Tuple, Dict, Optional, Any, List
import geopandas as gpd
import pandas as pd
from shapely.geometry import shape, box
import requests
import io
import math

try:
    from pmtiles.reader import Reader
    from pmtiles.tile import TileType
    import mapbox_vector_tile
except ImportError:
    Reader = None
    mapbox_vector_tile = None

from .base import PlanetDownloader

logger = logging.getLogger(__name__)

class ProtomapsDownloader(PlanetDownloader):
    """Downloader for Protomaps data using PMTiles."""

    def __init__(self, url: str = None):
        self.url = url or "https://data.source.coop/protomaps/openstreetmap/tiles/v3.pmtiles"

    @property
    def provider_name(self) -> str:
        return "protomaps"

    def _deg2num(self, lat_deg, lon_deg, zoom):
        lat_rad = math.radians(lat_deg)
        n = 2.0 ** zoom
        xtile = int((lon_deg + 180.0) / 360.0 * n)
        ytile = int((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
        return (xtile, ytile)

    def _tile_nw(self, x, y, z):
        n = 2.0 ** z
        lon_deg = x / n * 360.0 - 180.0
        lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
        lat_deg = math.degrees(lat_rad)
        return (lat_deg, lon_deg)

    def get_data(
        self,
        bbox: Tuple[float, float, float, float],
        tags: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> gpd.GeoDataFrame:
        """Fetch Protomaps data for a given bounding box."""
        if Reader is None or mapbox_vector_tile is None:
            logger.error("pmtiles or mapbox-vector-tile not installed.")
            return gpd.GeoDataFrame(columns=['geometry'], crs="EPSG:4326")

        minx, miny, maxx, maxy = bbox
        zoom = kwargs.get('zoom', 14)

        xtile_min, ytile_max = self._deg2num(miny, minx, zoom)
        xtile_max, ytile_min = self._deg2num(maxy, maxx, zoom)

        logger.info(f"Fetching tiles for zoom {zoom}, x: {xtile_min}-{xtile_max}, y: {ytile_min}-{ytile_max}")

        all_features = []
        session = requests.Session()

        def remote_get(offset, length):
            headers = {"Range": f"bytes={offset}-{offset + length - 1}"}
            resp = session.get(self.url, headers=headers)
            return resp.content

        reader = Reader(remote_get)

        for x in range(xtile_min, xtile_max + 1):
            for y in range(ytile_min, ytile_max + 1):
                try:
                    tile_data = reader.get(zoom, x, y)
                except Exception as e:
                    logger.warning(f"Failed to fetch tile {zoom}/{x}/{y}: {e}")
                    continue

                if tile_data:
                    decoded = mapbox_vector_tile.decode(tile_data)
                    for layer_name in ['roads', 'buildings']:
                        if layer_name in decoded:
                            layer = decoded[layer_name]
                            for feature in layer['features']:
                                properties = feature['properties']
                                if layer_name == 'roads':
                                    properties['highway'] = properties.get('kind', 'residential')
                                elif layer_name == 'buildings':
                                    properties['building'] = 'yes'

                                all_features.append({
                                    'geometry': shape(feature['geometry']),
                                    'properties': properties
                                })

        if not all_features:
            return gpd.GeoDataFrame(columns=['geometry'], crs="EPSG:4326")

        gdf = gpd.GeoDataFrame.from_features(all_features, crs="EPSG:4326")
        return gdf
