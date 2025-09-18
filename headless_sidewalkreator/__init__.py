"""headless_sidewalkreator package

Lightweight package initializer exposing the public API.
"""

from .main import run_headless  # re-export for convenience
from .full_sidewalkreator_algorithm import generate_sidewalks_gdf

__all__ = ["run_headless", "generate_sidewalks_gdf"]
