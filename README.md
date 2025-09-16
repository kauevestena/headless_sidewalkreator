# headless_sidewalkreator

A lightweight prototype for generating sidewalks from OSM data.

This repository contains a headless (CLI / library) prototype and helper
functions. The package has been reorganized into a Python package layout
(`headless_sidewalkreator/`) and includes runtime and development
requirements files.

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

