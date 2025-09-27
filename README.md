# sidewalkreator

A lightweight prototype for generating sidewalks from OSM data.

This repository contains a headless (CLI / library) prototype and helper
functions. The package has been reorganized into a Python package layout
(`headless_sidewalkreator/`) and includes runtime and development
requirements files.

## API Overview

The library provides several APIs for different use cases:

### Full Sidewalk Generation API

The `sidewalkreator()` function accepts and returns GeoDataFrames, giving users full control over I/O.

> **Note**: This function was previously named `generate_sidewalks_gdf()`. The old name is still available for backward compatibility but is deprecated.

**Input options (choose one):**

```python
from headless_sidewalkreator import sidewalkreator
import geopandas as gpd

# Option 1: Use a polygon GeoDataFrame
input_polygon_gdf = gpd.read_file("area_of_interest.geojson")
result = sidewalkreator(input_polygon_gdf=input_polygon_gdf)

# Option 2: Use a place name (geocoded automatically)
result = sidewalkreator(place_name="Amherst, MA")

# Option 3: Use a bounding box (minx, miny, maxx, maxy)
result = sidewalkreator(bbox=(-72.53, 42.37, -72.52, 42.38))

# All options support additional parameters
result = sidewalkreator(
    bbox=(-72.53, 42.37, -72.52, 42.38),
    parameters={"buffer_dist": 2.0},  # Optional custom parameters
    ignore_existing=False
)

# Extract results - all are GeoDataFrames
sidewalks = result['sidewalks']
crossings = result['crossings'] 
kerbs = result['kerbs']
protoblocks = result['protoblocks']  # For analysis/debugging
parameters_used = result['parameters']

# User handles output as needed
sidewalks.to_file("output_sidewalks.geojson")
crossings.to_file("output_crossings.gpkg")
```

### Standalone Protoblocks Generation API

The `generate_protoblocks()` function generates only the protoblocks (enclosed areas formed by street networks) without creating sidewalks. This is useful for urban analysis, block-level studies, or as input for other algorithms.

```python
from headless_sidewalkreator import generate_protoblocks
import geopandas as gpd

# Same input options as sidewalkreator
protoblocks = generate_protoblocks(
    input_polygon_gdf=your_polygon_gdf
    # OR place_name="Your City, State"
    # OR bbox=(minx, miny, maxx, maxy)
)

# Result is a GeoDataFrame of polygon geometries
print(f"Generated {len(protoblocks)} protoblocks")
protoblocks.to_file("protoblocks_output.geojson")
```

## Command-Line Usage

The tool can also be used from the command line with three input options:

```bash
# Option 1: Use a GeoJSON polygon file
sidewalkreator --input-file area.geojson --output-dir ./output

# Option 2: Use a place name (geocoded automatically)  
sidewalkreator --place-name "Amherst, MA" --output-dir ./output

# Option 3: Use a bounding box (minx miny maxx maxy)
sidewalkreator --bbox -72.53 42.37 -72.52 42.38 --output-dir ./output

# All options support additional parameters
sidewalkreator --bbox -72.53 42.37 -72.52 42.38 --output-dir ./output --ignore-existing
```

**Alternative**: The tool can also be invoked using `python -m headless_sidewalkreator` with the same arguments.

## Development setup

Modern versions of geopandas and related geospatial libraries come with
bundled binaries, so no system-level packages are required.

### Quick setup (Python 3.9+ recommended):

1. Create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate

# upgrade pip and build tools
pip install --upgrade pip setuptools wheel
```

2. Install all dependencies:

```bash
# install runtime dependencies
pip install -r requirements-runtime.txt

# install development/test dependencies
pip install -r requirements-dev.txt
```

### Alternative: Conda setup

If you prefer conda:

```bash
conda create -n hs-env python=3.10 -y
conda activate hs-env

# install via conda-forge for potentially faster geospatial package installation
conda install -c conda-forge geopandas osmnx -y

# install remaining dependencies
pip install -r requirements-dev.txt
```

## Running tests

With the virtual environment active and dependencies installed:

```bash
# run tests (uses pytest)
pytest -q
```

## Editable install and quick run

To install the package in editable/development mode:

```bash
pip install -e .

# then you can import the package in Python
python -c "from headless_sidewalkreator import run_headless; print(run_headless.__doc__)"
```

## Notes
- The package uses OSMnx to fetch OpenStreetMap data. OSMnx's `features_`
	helpers return GeoDataFrames and are preferred; the code falls back to
	older `geometries_` names if necessary.
- CI workflow is provided in `.github/workflows/ci.yml` which installs
	dependencies and runs the test suite on GitHub Actions.

If you'd like, I can add a Makefile or small helper scripts to automate
these steps.

[REPO IN PROGRESS]

This is the headless version of a QGIS Plugin called OSM Sidewalkreator, available at:

https://github.com/kauevestena/osm_sidewalkreator

