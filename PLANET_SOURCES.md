# Planet Data Sources for sidewalkreator

`sidewalkreator` now supports fetching data from cloud-optimized "planet" files. This allows for faster data retrieval for large areas and offline-ready workflows.

## Supported Providers

### 1. Overture Maps (GeoParquet)
- **Provider Name**: `overture`
- **Source**: Overture Maps Foundation (hosted on AWS S3 and Azure Blob Storage).
- **Format**: GeoParquet with Hive partitioning.
- **Capabilities**: Uses DuckDB to perform remote spatial slicing, downloading only the required data for your bounding box.
- **Schema Mapping**: Overture's transportation `class` is mapped to OSM's `highway` tag.
- **Usage**:
  ```bash
  sidewalkreator --bbox -72.53 42.37 -72.52 42.38 --output-dir ./output --planet-download --provider overture
  ```

### 2. Protomaps (PMTiles)
- **Provider Name**: `protomaps`
- **Source**: OpenStreetMap data in Protomaps format (e.g., hosted on Source Cooperative).
- **Format**: PMTiles (Tile-based cloud-optimized format).
- **Capabilities**: Fetches only the tiles covering the bounding box. Automatic
  zoom selection uses zoom 15 for requests of at most 16 tiles and zoom 14 for
  larger requests. Downloaded road features are clipped to tile cores and
  sub-metre Protomaps topology defects are repaired before polygonization.
- **Usage**:
  ```bash
  sidewalkreator --bbox -72.53 42.37 -72.52 42.38 --output-dir ./output --planet-download --provider protomaps
  ```

Library callers can override the Protomaps download policy and topology repair:

```python
from headless_sidewalkreator import sidewalkreator

result = sidewalkreator(
    bbox=(-72.53, 42.37, -72.52, 42.38),
    parameters={
        "provider": "protomaps",
        "provider_kwargs": {
            "zoom": "auto",  # or an explicit archive zoom such as 14 or 15
            "auto_zoom_tile_budget": 16,
            "tile_workers": 8,
        },
        "repair_protomaps_topology": True,
        "protomaps_endpoint_snap_tolerance": 0.5,
        "protomaps_endpoint_snap_max_angle": 45.0,
    },
)
```

Explicit zooms are validated against the PMTiles archive header before any tile
requests are started.

## Advanced Usage

You can specify a specific release version for Overture:
```bash
sidewalkreator --bbox ... --planet-download --provider overture --release 2026-06-17.0
```

## Limitations
- **Overture**: Data schema differs from native OSM. While `sidewalkreator` attempts to map common tags, some advanced OSM tags might be missing.
- **Protomaps**: Vector tiles are optimized for rendering and may have simplified geometries or stripped tags depending on the zoom level and tile configuration.
