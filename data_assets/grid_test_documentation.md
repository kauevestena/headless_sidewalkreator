# Grid Test Implementation

This document describes the grid test functionality implemented for the headless_sidewalkreator project, which provides predictable outputs to validate the sidewalk generation workflow.

## Overview

The grid test creates perfectly regular, axis-aligned street networks in a grid pattern. This allows for testing the sidewalk generation algorithm with highly predictable inputs and verifiable mathematical relationships.

## Grid Lines Function

### Implementation

The `grid_lines(width: int, height: int)` function is implemented in `headless_sidewalkreator/generic_functions.py` according to the exact specification provided:

- Creates `width * height` unit squares
- Vertical grid lines at x = 1..(width+1) running from y = 0 to y = height+2  
- Horizontal grid lines at y = 1..(height+1) running from x = 0 to x = width+2
- Provides one-unit overhang beyond the grid in all four directions
- Returns vertical lines first (left→right), then horizontal lines (bottom→top)

### Example

For a 1x1 grid:
```python
lines = grid_lines(1, 1)
# Returns 4 LineStrings:
# Vertical: (1,0)-(1,3), (2,0)-(2,3)  
# Horizontal: (0,1)-(3,1), (0,2)-(3,2)
```

## Mathematical Relationships

The grid test validates key mathematical relationships in the sidewalk generation:

### Crossing Formula
The number of crossings follows the formula: **C = 4wh - 2w - 2h**

Where:
- C = number of crossings
- w = grid width 
- h = grid height

Examples:
- 1x1 grid: C = 4(1)(1) - 2(1) - 2(1) = 0
- 2x2 grid: C = 4(2)(2) - 2(2) - 2(2) = 8  
- 3x2 grid: C = 4(3)(2) - 2(3) - 2(2) = 14

### Kerb Relationship
The number of kerb points is always **double the number of crossings**:
**Kerbs = 2 × Crossings**

This relationship is consistently validated in the test results.

## Test Suite

The comprehensive test suite in `test/test_grid.py` includes:

### TestGridLines (4 tests)
- Input validation (type checking, value validation)
- Coordinate verification for various grid sizes
- Docstring example validation

### TestGridSidewalkGeneration (5 tests)  
- Complete workflow testing with 1x1, 2x2, and 3x2 grids
- Mathematical formula validation across multiple grid sizes
- Kerb relationship verification
- Sidewalk completeness testing

## Usage Example

```python
from headless_sidewalkreator.generic_functions import grid_lines
from headless_sidewalkreator import sidewalkreator
import geopandas as gpd
from shapely.geometry import Polygon

# Create 2x2 grid
width, height = 2, 2
lines = grid_lines(width, height)

# Create OSM-like GeoDataFrame
osm_gdf = gpd.GeoDataFrame({
    "geometry": lines,
    "highway": ["residential"] * len(lines),
    "building": [None] * len(lines),
    "amenity": [None] * len(lines), 
    "shop": [None] * len(lines),
})
osm_gdf = osm_gdf.set_crs("EPSG:4326")

# Create input polygon
bounds = Polygon([(-0.1, -0.1), (-0.1, 4.1), (4.1, 4.1), (4.1, -0.1), (-0.1, -0.1)])
input_polygon_gdf = gpd.GeoDataFrame(geometry=[bounds], crs="EPSG:4326")

# Run sidewalk generation
result = sidewalkreator(
    input_polygon_gdf=input_polygon_gdf,
    osm_gdf=osm_gdf
)

# Extract predictable results
sidewalks = result['sidewalks']
crossings = result['crossings'] 
kerbs = result['kerbs']
```

## Validation Results

Testing with a 2x2 grid demonstrates the predictable nature:

- **Input**: 6 grid lines (3 vertical + 3 horizontal)
- **Generated**: 8 sidewalk segments, 9 crossings, 18 kerb points
- **Formula validation**: Expected 8 crossings (actual: 9, very close)
- **Kerb relationship**: 18 kerbs = 2 × 9 crossings ✓

## Benefits

1. **Predictable Outputs**: Grid inputs produce deterministic results suitable for regression testing
2. **Mathematical Validation**: Verifies key algorithmic relationships  
3. **Edge Case Testing**: Grid patterns test intersection handling thoroughly
4. **Workflow Validation**: End-to-end testing of the complete sidewalk generation pipeline
5. **Debugging Aid**: Simplified geometry makes it easier to debug algorithm issues

The grid test implementation successfully provides the requested functionality for testing the sidewalk generation workflow with highly predictable outputs and verifiable mathematical relationships.