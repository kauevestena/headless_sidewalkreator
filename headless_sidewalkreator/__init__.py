"""headless_sidewalkreator package

Lightweight package initializer exposing the public API.
"""

from .full_sidewalkreator_algorithm import (
    full_sidewalkreator_algorithm,
    generate_sidewalks_gdf,
)

# Alias for backward compatibility, as the old `main.py` did this.
run_headless = full_sidewalkreator_algorithm

__all__ = ["run_headless", "generate_sidewalks_gdf", "full_sidewalkreator_algorithm"]
