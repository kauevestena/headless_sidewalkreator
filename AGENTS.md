# AGENTS.md: Guide for AI Contributors

Welcome, contributors! This file provides guidance for working on the `headless_sidewalkreator` codebase.

## About this Project

This project is a headless (command-line/library) version of the [OSM Sidewalkreator QGIS plugin](https://github.com/kauevestena/osm_sidewalkreator). Its goal is to generate sidewalk geometries from OpenStreetMap (OSM) data without requiring a GUI.

## Getting Started

Before making any changes, it's crucial to set up your development environment correctly. Detailed instructions are in the `README.md` file.

Key setup points:
- Use a Python virtual environment (`venv` or `conda`).
- Install system-level dependencies for geospatial libraries (e.g., GDAL, PROJ). The `README.md` has examples for Debian/Ubuntu.
- Install Python dependencies from `requirements-runtime.txt` and `requirements-dev.txt`.

## Codebase Overview

- **`headless_sidewalkreator/`**: This is the main Python package containing the core application logic.
- **`test/`**: This directory contains all the `pytest` tests. Please add new tests here for any new functionality and ensure all tests pass before submitting.
- **`data_assets/`**: This folder contains important assets for understanding the project.
    - `qgis_algorithm_description.md`: This file describes the high-level logic of the sidewalk generation algorithm. It's a crucial starting point for understanding how the tool works.
    - `icon.png`, `sidewalkreator_logo.png`: Project branding assets.
    - `test_data/`: Sample data for testing purposes.
- **`requirements-*.txt`**: Files defining the project's dependencies.
- **`README.md`**: The primary documentation for setting up and running the project.

## The Algorithm

To understand the core logic of this tool, please read the `data_assets/qgis_algorithm_description.md` file. It provides a step-by-step breakdown of the sidewalk generation process.

## Running Tests

This project uses `pytest` for testing. To run the tests, execute the following command in your terminal from the root directory:

```bash
pytest -q
```

Before submitting your changes, **you must ensure all tests pass**.

## Contribution Guidelines

- **Always write tests** for new features or bug fixes.
- **Follow the existing code style.**
- **Make sure your changes don't break existing tests.**
- **Refer to the `README.md` and `data_assets/qgis_algorithm_description.md`** to understand the project's context and mechanics.
- **Keep your changes focused.** If you are working on multiple features, create separate branches and pull requests for each.
