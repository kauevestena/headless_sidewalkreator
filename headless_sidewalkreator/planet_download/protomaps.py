import logging
from typing import Tuple, Dict, Optional, Any
import geopandas as gpd
from shapely.geometry import shape
from shapely.affinity import affine_transform
import requests
import gzip
import mercantile
import time
from tqdm import tqdm

try:
    from pmtiles.reader import Reader
    from pmtiles.tile import Compression
    import mapbox_vector_tile
except ImportError:
    Reader = None
    Compression = None
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

    def _tiles_for_bbox(self, bbox, zoom):
        minx, miny, maxx, maxy = bbox
        return list(mercantile.tiles(minx, miny, maxx, maxy, zooms=[zoom]))

    def _tile_bounds(self, tile):
        return mercantile.bounds(tile)

    def _include_road_feature(self, properties):
        pmap_kind = properties.get("pmap:kind")
        return isinstance(pmap_kind, str) and pmap_kind.endswith("_road")

    def _decompress_tile(self, tile_data, tile_compression):
        if tile_data.startswith(b'\x1f\x8b'):
            return gzip.decompress(tile_data)
        if Compression is not None and tile_compression == Compression.GZIP:
            return gzip.decompress(tile_data)
        if tile_compression is None:
            return tile_data
        if Compression is not None and tile_compression in (
            Compression.NONE,
            Compression.UNKNOWN,
        ):
            return tile_data
        raise ValueError(f"Unsupported Protomaps tile compression: {tile_compression}")

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

        zoom = kwargs.get('zoom', 14)
        request_timeout = kwargs.get('timeout', 60)
        max_retries = kwargs.get('max_retries', 2)
        show_progress = kwargs.get('show_progress', True)
        tiles = self._tiles_for_bbox(bbox, zoom)

        logger.info(
            "Fetching %s tiles for bbox %s at zoom %s",
            len(tiles),
            bbox,
            zoom,
        )

        all_features = []
        session = requests.Session()
        range_cache = {}

        def remote_get(offset, length):
            cache_key = (offset, length)
            if cache_key in range_cache:
                return range_cache[cache_key]

            headers = {
                "Range": f"bytes={offset}-{offset + length - 1}",
                "Accept-Encoding": "identity",
            }
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    resp = session.get(
                        self.url,
                        headers=headers,
                        timeout=request_timeout,
                    )
                    resp.raise_for_status()
                    if resp.status_code != 206:
                        raise requests.HTTPError(
                            f"Expected HTTP 206 Partial Content, got {resp.status_code}",
                            response=resp,
                        )
                    if len(resp.content) != length:
                        raise requests.HTTPError(
                            f"Expected {length} bytes, got {len(resp.content)}",
                            response=resp,
                        )
                    range_cache[cache_key] = resp.content
                    return resp.content
                except requests.RequestException as exc:
                    last_exc = exc
                    if attempt < max_retries:
                        time.sleep(min(2 ** attempt, 5))

            raise last_exc

        reader = Reader(remote_get)
        try:
            header = reader.header()
            tile_compression = (
                header.get("tile_compression") if isinstance(header, dict) else None
            )
        except Exception as e:
            logger.error(f"Failed to read Protomaps PMTiles header: {e}")
            return gpd.GeoDataFrame(columns=['geometry'], crs="EPSG:4326")

        tile_iter = tqdm(
            tiles,
            desc="Fetching Protomaps tiles",
            unit="tile",
            disable=not show_progress,
        )

        for tile in tile_iter:
            x, y, z = tile
            try:
                tile_data = reader.get(z, x, y)
            except Exception as e:
                logger.warning(f"Failed to fetch tile {z}/{x}/{y}: {e}")
                continue

            if tile_data:
                try:
                    tile_data = self._decompress_tile(tile_data, tile_compression)
                    # Keep native MVT tile coordinates. The affine transform
                    # below maps the tile's Y-down coordinate space to lon/lat.
                    decoded = mapbox_vector_tile.decode(
                        tile_data,
                        default_options={"y_coord_down": True},
                    )
                except Exception as e:
                    logger.warning(f"Failed to decode tile {z}/{x}/{y}: {e}")
                    continue

                for layer_name in ['roads', 'buildings']:
                    if layer_name in decoded:
                        layer = decoded[layer_name]
                        extent = layer.get('extent', 4096)
                        tile_bounds = self._tile_bounds(tile)
                        x_scale = (tile_bounds.east - tile_bounds.west) / extent
                        y_scale = (tile_bounds.south - tile_bounds.north) / extent
                        for feature in layer['features']:
                            properties = dict(feature['properties'])
                            if layer_name == 'roads':
                                if not self._include_road_feature(properties):
                                    continue
                                properties['highway'] = properties['pmap:kind']
                            elif layer_name == 'buildings':
                                properties['building'] = 'yes'

                            geom = shape(feature['geometry'])
                            geom_transformed = affine_transform(
                                geom,
                                [
                                    x_scale,
                                    0,
                                    0,
                                    y_scale,
                                    tile_bounds.west,
                                    tile_bounds.north,
                                ],
                            )
                            all_features.append({
                                'geometry': geom_transformed,
                                'properties': properties
                            })

        if not all_features:
            return gpd.GeoDataFrame(columns=['geometry'], crs="EPSG:4326")

        gdf = gpd.GeoDataFrame.from_features(all_features, crs="EPSG:4326")
        return gdf
