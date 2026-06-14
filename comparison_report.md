# Comparison Report: QGIS vs Local Headless Version

## Execution & Scope
The Python algorithm was executed locally via `headless_sidewalkreator.main.sidewalkreator` using the provided test Bounding Box `(-49.3, -25.5, -49.29, -25.45)`.
The outputs were compared to the CI test output files from the `osm_sidewalkreator` QGIS plugin repository.

## Findings

**Original Differences:**
Initially, the local python script was crashing due to `parallel_offset` missing from `GeoSeries` (a deprecated and removed attribute in `geopandas`). After updating this to `offset_curve(..., join_style=2)`, the script ran successfully.

**Topology Generation Differences:**
The QGIS plugin uses the QGIS built-in `native:polygonize` tool, which is incredibly robust at snapping intersections, finding loops, and handling boundary constraints.
When comparing the pure output directly:
- **QGIS version:** 29 protoblocks (Area: ~585,265 sqm), 5 sidewalks.
- **Local python version:** 6 protoblocks (Area: ~188,669 sqm), 44 sidewalks.

The reason for the massive fragmentation in the local version is that `split_lines_at_intersections` and `polygonize` rely on basic topological precision and do not automatically close bounding-box edges.

**Improvements Implemented & Tested:**
I thoroughly investigated mimicking the QGIS `native:polygonize` logic via `unary_union` and appending the bounding box geometry into the clip. While these edits bring the protoblock count closer to parity (27 local protoblocks vs 29 QGIS protoblocks, matching 20 exactly), they unfortunately break multiple internal unit tests that explicitly assert the old topology building behaviors.

## Recommended Code Modifications
To stabilize the codebase right now without breaking the existing robust test suite, I recommend at minimum merging the critical bug fix for `parallel_offset`:

1. **Fix offset_curve bug in `headless_sidewalkreator/generic_functions.py`:**
   ```python
   offset_lines = side_streets.geometry.offset_curve(
       buffer_distances if side == "left" else -buffer_distances, join_style=2
   )
   ```

A future PR should consider refactoring the test suite and migrating to the `unary_union` approach for polygonizing lines to perfectly match the QGIS plugin output.
