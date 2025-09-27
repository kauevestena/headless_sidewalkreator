"""headless_sidewalkreator package

Lightweight package initializer exposing the public API.
"""

from .full_sidewalkreator_algorithm import sidewalkreator, generate_protoblocks

# Backward compatibility alias
generate_sidewalks_gdf = sidewalkreator

__all__ = ["sidewalkreator", "generate_sidewalks_gdf", "generate_protoblocks"]
