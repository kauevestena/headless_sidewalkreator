"""headless_sidewalkreator package

Lightweight package initializer exposing the public API.
"""

from .main import run_headless  # re-export for convenience
from .full_sidewalkreator_algorithm import sidewalkreator

# Backward compatibility alias
generate_sidewalks_gdf = sidewalkreator

__all__ = ["run_headless", "sidewalkreator", "generate_sidewalks_gdf"]
