# headless_sidewalkreator

A lightweight prototype for generating sidewalks from OSM data.

This repository contains a headless (CLI / library) prototype and helper
functions. The package has been reorganized into a Python package layout
(`headless_sidewalkreator/`) and includes runtime and development
requirements files.

## Development setup

These instructions cover two common workflows: using a Python virtualenv or
Conda. The project depends on geospatial libraries (geopandas, osmnx,
shapely, GDAL, PROJ) which may require system-level packages on Linux.

Recommended approach (virtualenv + apt):

1. Create a fresh Python virtual environment (Python 3.9+ recommended):

```bash
# create and activate a venv
python3 -m venv .venv
source .venv/bin/activate

# upgrade pip, wheel, setuptools
pip install --upgrade pip setuptools wheel
```

2. Install OS-level prerequisites (Ubuntu/Debian example):

```bash
# install system packages required by geopandas/osmnx
sudo apt-get update
sudo apt-get install -y build-essential gdal-bin libgdal-dev libproj-dev
```

3. Install runtime and dev Python dependencies:

```bash
# runtime requirements
pip install -r requirements-runtime.txt

# development / test requirements
pip install -r requirements-dev.txt
```

Conda alternative (recommended if you can't install system packages):

```bash
conda create -n hs-env python=3.10 -y
conda activate hs-env

# install geopandas/osmnx via conda-forge
conda install -c conda-forge geopandas osmnx python-graphlib networkx -y

# install the rest of the runtime and dev deps with pip if needed
pip install -r requirements-dev.txt
```

Notes about system packages
- geopandas and osmnx rely on geospatial C libraries (GDAL, PROJ, GEOS).
	If you hit installation errors, prefer the `conda-forge` route.

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

- Install runtime dependencies: geopandas, osmnx
- Install dev dependencies for running tests: pytest, pytest-cov

Usage

Import the main function:

from headless_sidewalkreator import run_headless

run_headless("input_polygon.geojson", "output_dir")

How to install and run tests

Install runtime deps:

python -m pip install -r requirements-runtime.txt

Install dev deps (for testing):

python -m pip install -r requirements-dev.txt

Run tests:

pytest -q

[REPO IN PROGRESS]

This is the headless version of a QGIS Plugin called OSM Sidewalkreator, available at:

https://github.com/kauevestena/osm_sidewalkreator

