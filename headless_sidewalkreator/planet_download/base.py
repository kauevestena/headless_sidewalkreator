from abc import ABC, abstractmethod
from typing import Tuple, Dict, Optional, Any
import geopandas as gpd

class PlanetDownloader(ABC):
    """Base class for planet data downloaders."""

    @abstractmethod
    def get_data(
        self,
        bbox: Tuple[float, float, float, float],
        tags: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> gpd.GeoDataFrame:
        """Fetch data for a given bounding box and tags.

        Args:
            bbox: (minx, miny, maxx, maxy) in EPSG:4326.
            tags: Dictionary of tags to filter by.
            **kwargs: Provider-specific options.

        Returns:
            GeoDataFrame with the requested features.
        """
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Returns the name of the provider."""
        pass
