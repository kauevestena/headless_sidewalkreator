import os
import re
from urllib.parse import urlparse
from abc import ABC, abstractmethod
from typing import Tuple, Dict, Optional, Any
import geopandas as gpd

DEFAULT_ALLOWED_DOMAINS = {
    "overturemapswestus2.blob.core.windows.net",
    "data.source.coop",
    "example.com",
}

DEFAULT_ALLOWED_SUFFIXES = (
    ".blob.core.windows.net",
    ".amazonaws.com",
    ".source.coop",
    ".cloudfront.net",
    ".protomaps.com",
    ".example.com",
)

def is_safe_url(url: str) -> bool:
    """Validate that the URL is a safe, remote HTTP(S) URL belonging to allowed domains."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        hostname = hostname.lower()

        # Prevent local read / SSRF (localhost, 127.0.0.1, etc.)
        local_patterns = (
            "localhost", "127.0.0.1", "0.0.0.0", "::1", "::",
            "169.254.169.254", # Link-local
        )
        if any(lp in hostname for lp in local_patterns):
            return False

        # Private/local IP range check
        if (
            hostname.startswith("127.") or
            hostname.startswith("10.") or
            hostname.startswith("192.168.") or
            hostname.startswith("172.")
        ):
            return False

        # Get allowed domains from environment if present
        env_allowed = os.getenv("ALLOWED_PLANET_DOMAINS")
        if env_allowed:
            allowed_list = [d.strip().lower() for d in env_allowed.split(",") if d.strip()]
            for allowed in allowed_list:
                if allowed.startswith("*."):
                    suffix = allowed[1:]
                    if hostname == suffix[1:] or hostname.endswith(suffix):
                        return True
                elif hostname == allowed:
                    return True
            return False

        # Default safety checks
        if hostname in DEFAULT_ALLOWED_DOMAINS:
            return True
        if hostname.endswith(DEFAULT_ALLOWED_SUFFIXES):
            return True

        return False
    except Exception:
        return False


def is_safe_release(release: str) -> bool:
    """Validate that the release version string is safe from path traversal or injection."""
    if not release:
        return False
    if ".." in release or "/" in release or "\\" in release:
        return False
    pattern = re.compile(r"^[a-zA-Z0-9_\-\.]+$")
    return bool(pattern.match(release))


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
