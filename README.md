# headless_sidewalkreator

A lightweight prototype for generating sidewalks from OSM data.

This repository contains a headless (CLI / library) prototype and helper
functions. The package has been reorganized into a Python package layout
(`headless_sidewalkreator/`) and includes runtime and development
requirements files.

## API Overview

The library now provides two ways to use the sidewalk generation algorithm:

### 1. GeoDataFrame-based API (Recommended)

The new `generate_sidewalks_gdf()` function accepts and returns GeoDataFrames, giving users full control over I/O:

```python
from headless_sidewalkreator import generate_sidewalks_gdf
import geopandas as gpd

# User loads their own data
input_polygon_gdf = gpd.read_file("area_of_interest.geojson")
osm_data_gdf = gpd.read_file("osm_streets.geojson")  # Optional

# Generate sidewalks
result = generate_sidewalks_gdf(
    input_polygon_gdf=input_polygon_gdf,
    osm_gdf=osm_data_gdf,  # If None, will fetch from OSM automatically
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

### 2. File-based API (Legacy)

The original `run_headless()` function still works for backward compatibility:

```python
from headless_sidewalkreator import run_headless

# Original file-based interface
run_headless(
    input_polygon_path="input.geojson",
    output_directory="output/",
    parameters_path="params.json"  # Optional
)
```

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

## Documentation

The documentation for this project is built using Sphinx. To build the documentation locally, first install the documentation dependencies:

```bash
pip install -r requirements-docs.txt
```

Then, navigate to the `docs` directory and build the HTML pages:

```bash
cd docs
make html
```

The generated documentation can be found in `docs/build/html/index.html`.

[REPO IN PROGRESS]

This is the headless version of a QGIS Plugin called OSM Sidewalkreator, available at:

https://github.com/kauevestena/osm_sidewalkreator

