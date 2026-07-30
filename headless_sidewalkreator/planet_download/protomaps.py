import logging
from numbers import Integral
from typing import Tuple, Dict, Optional, Any
import geopandas as gpd
from shapely.geometry import MultiLineString, box, shape
from shapely.affinity import affine_transform
import requests
import gzip
import mercantile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, local
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

DEFAULT_AUTO_ZOOM_TILE_BUDGET = 16
DEFAULT_DETAIL_ZOOM = 15
DEFAULT_LARGE_AREA_ZOOM = 14
DEFAULT_TILE_WORKERS = 8


class ProtomapsDownloader(PlanetDownloader):
    """Downloader for Protomaps data using PMTiles."""

    def __init__(self, url: str = None):
        self.url = url or "https://data.source.coop/protomaps/openstreetmap/tiles/v3.pmtiles"
        from .base import is_safe_url
        if not is_safe_url(self.url):
            raise ValueError(
                f"Insecure Protomaps URL: '{self.url}'. Only allowed remote HTTP(S) domains are permitted."
            )

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

    def _select_zoom(self, bbox, requested_zoom, header, tile_budget):
        """Select and validate an explicit or adaptive archive zoom."""
        if (
            isinstance(tile_budget, bool)
            or not isinstance(tile_budget, Integral)
            or tile_budget <= 0
        ):
            raise ValueError("auto_zoom_tile_budget must be a positive integer")

        min_zoom = int(header.get("min_zoom", 0)) if isinstance(header, dict) else 0
        max_zoom = (
            int(header.get("max_zoom", DEFAULT_DETAIL_ZOOM))
            if isinstance(header, dict)
            else DEFAULT_DETAIL_ZOOM
        )

        if requested_zoom in (None, "auto"):
            detail_zoom = min(DEFAULT_DETAIL_ZOOM, max_zoom)
            large_area_zoom = min(DEFAULT_LARGE_AREA_ZOOM, max_zoom)
            if detail_zoom < min_zoom:
                raise ValueError(
                    f"Archive zoom range {min_zoom}-{max_zoom} is not usable"
                )
            detail_tile_count = len(self._tiles_for_bbox(bbox, detail_zoom))
            if detail_tile_count <= tile_budget:
                return detail_zoom
            return max(min_zoom, large_area_zoom)

        if isinstance(requested_zoom, bool) or not isinstance(
            requested_zoom,
            Integral,
        ):
            raise ValueError("zoom must be 'auto' or an integer")
        requested_zoom = int(requested_zoom)
        if requested_zoom < min_zoom or requested_zoom > max_zoom:
            raise ValueError(
                f"Requested zoom {requested_zoom} is outside archive range "
                f"{min_zoom}-{max_zoom}"
            )
        return requested_zoom

    @staticmethod
    def _clip_road_to_tile_core(geom, tile_bounds):
        """Remove MVT buffer overlap while preserving line components."""
        tile_core = box(
            tile_bounds.west,
            tile_bounds.south,
            tile_bounds.east,
            tile_bounds.north,
        )
        clipped = geom.intersection(tile_core)
        if clipped.is_empty:
            return None
        if clipped.geom_type in ("LineString", "MultiLineString"):
            return clipped
        if clipped.geom_type != "GeometryCollection":
            return None

        line_parts = []
        for part in clipped.geoms:
            if part.geom_type == "LineString":
                line_parts.append(part)
            elif part.geom_type == "MultiLineString":
                line_parts.extend(part.geoms)
        if not line_parts:
            return None
        if len(line_parts) == 1:
            return line_parts[0]
        return MultiLineString(line_parts)

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

    def _decode_tile_features(self, tile, tile_data, tile_compression):
        x, y, z = tile
        tile_data = self._decompress_tile(tile_data, tile_compression)
        # Keep native MVT tile coordinates. The affine transform below maps the
        # tile's Y-down coordinate space to lon/lat.
        decoded = mapbox_vector_tile.decode(
            tile_data,
            default_options={"y_coord_down": True},
        )

        tile_features = []
        for layer_name in ['roads', 'buildings']:
            if layer_name not in decoded:
                continue

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
                if layer_name == 'roads':
                    geom_transformed = self._clip_road_to_tile_core(
                        geom_transformed,
                        tile_bounds,
                    )
                    if geom_transformed is None:
                        continue
                tile_features.append({
                    'geometry': geom_transformed,
                    'properties': properties
                })

        return tile_features

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

        requested_zoom = kwargs.get('zoom', 'auto')
        auto_zoom_tile_budget = kwargs.get(
            'auto_zoom_tile_budget',
            DEFAULT_AUTO_ZOOM_TILE_BUDGET,
        )
        request_timeout = kwargs.get('timeout', 60)
        max_retries = kwargs.get('max_retries', 2)
        show_progress = kwargs.get('show_progress', True)

        all_features = []
        thread_state = local()
        range_cache = {}
        range_cache_lock = Lock()

        def get_session():
            if not hasattr(thread_state, "session"):
                thread_state.session = requests.Session()
            return thread_state.session

        def remote_get(offset, length):
            cache_key = (offset, length)
            with range_cache_lock:
                if cache_key in range_cache:
                    return range_cache[cache_key]

            headers = {
                "Range": f"bytes={offset}-{offset + length - 1}",
                "Accept-Encoding": "identity",
            }
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    resp = get_session().get(
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
                    with range_cache_lock:
                        range_cache.setdefault(cache_key, resp.content)
                        return range_cache[cache_key]
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
            if (
                isinstance(header, dict)
                and "root_offset" in header
                and "root_length" in header
            ):
                remote_get(header["root_offset"], header["root_length"])
        except Exception as e:
            logger.error(f"Failed to read Protomaps PMTiles header: {e}")
            return gpd.GeoDataFrame(columns=['geometry'], crs="EPSG:4326")

        zoom = self._select_zoom(
            bbox,
            requested_zoom,
            header,
            auto_zoom_tile_budget,
        )
        tiles = self._tiles_for_bbox(bbox, zoom)
        requested_workers = kwargs.get('tile_workers', kwargs.get('max_workers'))
        if requested_workers is None:
            tile_workers = min(DEFAULT_TILE_WORKERS, max(1, len(tiles)))
        else:
            if (
                isinstance(requested_workers, bool)
                or not isinstance(requested_workers, Integral)
                or requested_workers <= 0
            ):
                raise ValueError("tile_workers must be a positive integer")
            tile_workers = int(requested_workers)
            tile_workers = min(tile_workers, max(1, len(tiles)))

        logger.info(
            "Fetching %s tiles for bbox %s at zoom %s with %s worker(s)",
            len(tiles),
            bbox,
            zoom,
            tile_workers,
        )

        def fetch_tile(tile):
            x, y, z = tile
            try:
                tile_data = reader.get(z, x, y)
            except Exception as e:
                logger.warning(f"Failed to fetch tile {z}/{x}/{y}: {e}")
                return []

            if tile_data:
                try:
                    return self._decode_tile_features(
                        tile,
                        tile_data,
                        tile_compression,
                    )
                except Exception as e:
                    logger.warning(f"Failed to decode tile {z}/{x}/{y}: {e}")

            return []

        fetch_started = time.perf_counter()
        with ThreadPoolExecutor(
            max_workers=min(tile_workers, len(tiles) or 1)
        ) as executor:
            futures = [executor.submit(fetch_tile, tile) for tile in tiles]
            tile_iter = tqdm(
                as_completed(futures),
                total=len(futures),
                desc="Fetching Protomaps tiles",
                unit="tile",
                disable=not show_progress,
                position=1,
                leave=False,
                dynamic_ncols=True,
            )
            for future in tile_iter:
                all_features.extend(future.result())
        fetch_duration = time.perf_counter() - fetch_started
        logger.info(
            "Fetched and decoded %s Protomaps tiles in %.3fs",
            len(tiles),
            fetch_duration,
        )
        if show_progress:
            print(
                f"Fetched and decoded {len(tiles)} Protomaps tiles at zoom "
                f"{zoom} in {fetch_duration:.2f} seconds."
            )

        if all_features:
            gdf = gpd.GeoDataFrame.from_features(all_features, crs="EPSG:4326")
        else:
            gdf = gpd.GeoDataFrame(columns=['geometry'], crs="EPSG:4326")
        gdf.attrs.update(
            {
                "provider": self.provider_name,
                "zoom": zoom,
                "tile_count": len(tiles),
                "tile_workers": tile_workers,
            }
        )
        return gdf
