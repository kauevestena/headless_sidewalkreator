import logging
import os
from typing import Tuple, Dict, Optional, Any, List
import geopandas as gpd
import pandas as pd
from shapely import wkb
import json

from .base import PlanetDownloader

logger = logging.getLogger(__name__)

class OvertureDownloader(PlanetDownloader):
    """Downloader for Overture Maps data using DuckDB."""

    DEFAULT_RELEASE = "2026-06-17.0"
    DEFAULT_BASE_URL = "https://overturemapswestus2.blob.core.windows.net/release"

    def __init__(self, release: str = None, base_url: str = None):
        self.release = release or self.DEFAULT_RELEASE
        self.base_url = base_url or self.DEFAULT_BASE_URL
        self._con = None

    @property
    def provider_name(self) -> str:
        return "overture"

    def _get_con(self):
        if self._con is None:
            try:
                import duckdb
                self._con = duckdb.connect(database=":memory:")
                self._con.execute("INSTALL httpfs;")
                self._con.execute("LOAD httpfs;")
                self._con.execute("INSTALL spatial;")
                self._con.execute("LOAD spatial;")
                self._con.execute("SET allow_asterisks_in_http_paths = true;")
            except ImportError:
                logger.error("DuckDB not installed. Please install it with 'pip install duckdb'")
                raise
        return self._con

    def get_data(
        self,
        bbox: Tuple[float, float, float, float],
        tags: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> gpd.GeoDataFrame:
        """Fetch Overture data for a given bounding box."""
        minx, miny, maxx, maxy = bbox

        # We'll focus on transportation theme for now as it's the most critical
        # If buildings are needed, we'd need another query.

        url = f"{self.base_url}/{self.release}/theme=transportation/type=segment/*"

        query = f"""
        SELECT
            id,
            subtype,
            class,
            names.primary as name,
            level_rules,
            ST_AsWKB(geometry) as geometry_wkb
        FROM
            read_parquet('{url}', filename=true, hive_partitioning=1)
        WHERE
            bbox.xmin >= {minx} AND bbox.xmax <= {maxx}
            AND bbox.ymin >= {miny} AND bbox.ymax <= {maxy}
        """

        con = self._get_con()
        logger.info(f"Querying Overture Transportation at {bbox}")

        try:
            # Execute and convert to pandas
            df = con.execute(query).df()

            if df.empty:
                logger.warning("No Overture data found for the given bbox")
                return gpd.GeoDataFrame(columns=['geometry'], crs="EPSG:4326")

            # Convert WKB to shapely geometries
            df['geometry'] = df['geometry_wkb'].apply(lambda x: wkb.loads(bytes(x)))
            df = df.drop(columns=['geometry_wkb'])

            # Map Overture schema to OSM-like tags
            # class -> highway
            df['highway'] = df['class']

            # Create GeoDataFrame
            gdf = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326")

            # Fetch buildings if requested in tags or by default
            if tags is None or 'building' in tags:
                buildings_gdf = self._get_buildings(bbox)
                if not buildings_gdf.empty:
                    gdf = pd.concat([gdf, buildings_gdf], ignore_index=True)

            return gdf

        except Exception as e:
            logger.error(f"Error fetching Overture data: {e}")
            return gpd.GeoDataFrame(columns=['geometry'], crs="EPSG:4326")

    def _get_buildings(self, bbox: Tuple[float, float, float, float]) -> gpd.GeoDataFrame:
        minx, miny, maxx, maxy = bbox
        url = f"{self.base_url}/{self.release}/theme=buildings/type=building/*"

        query = f"""
        SELECT
            id,
            names.primary as name,
            ST_AsWKB(geometry) as geometry_wkb
        FROM
            read_parquet('{url}', filename=true, hive_partitioning=1)
        WHERE
            bbox.xmin >= {minx} AND bbox.xmax <= {maxx}
            AND bbox.ymin >= {miny} AND bbox.ymax <= {maxy}
        """

        con = self._get_con()
        logger.info(f"Querying Overture Buildings at {bbox}")

        try:
            df = con.execute(query).df()
            if df.empty:
                return gpd.GeoDataFrame(columns=['geometry'], crs="EPSG:4326")

            df['geometry'] = df['geometry_wkb'].apply(lambda x: wkb.loads(bytes(x)))
            df = df.drop(columns=['geometry_wkb'])
            df['building'] = 'yes'

            return gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326")
        except Exception as e:
            logger.warning(f"Error fetching Overture buildings: {e}")
            return gpd.GeoDataFrame(columns=['geometry'], crs="EPSG:4326")
