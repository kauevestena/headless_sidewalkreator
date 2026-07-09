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
- **Capabilities**: Fetches only the tiles covering the bounding box.
- **Usage**:
  ```bash
  sidewalkreator --bbox -72.53 42.37 -72.52 42.38 --output-dir ./output --planet-download --provider protomaps
  ```

## Advanced Usage

You can specify a specific release version for Overture:
```bash
sidewalkreator --bbox ... --planet-download --provider overture --release 2026-06-17.0
```

## Limitations
- **Overture**: Data schema differs from native OSM. While `sidewalkreator` attempts to map common tags, some advanced OSM tags might be missing.
- **Protomaps**: Vector tiles are optimized for rendering and may have simplified geometries or stripped tags depending on the zoom level and tile configuration.
