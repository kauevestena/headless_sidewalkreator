# Performance Optimization Rationale: Vectorization in `handle_sidewalk_tags`

## 💡 What
The optimization replaces iterative loops (`for street in side_streets.itertuples()`) with vectorized GeoPandas operations. Specifically, it uses `GeoSeries.parallel_offset()` and `GeoSeries.buffer()` directly on the filtered GeoDataFrames.

## 🎯 Why
### 1. Vectorization vs. Iteration
Iterating over rows in a GeoDataFrame using `itertuples()` or `iterrows()` is a well-known bottleneck in Python-based geospatial analysis. Each iteration incurs significant overhead due to Python's object creation and function call mechanisms.

By contrast, vectorized operations in GeoPandas:
- **Leverage underlying C/C++ libraries**: Operations like `buffer` and `parallel_offset` are implemented in GEOS (via Shapely). Vectorized calls allow these libraries to process entire arrays of geometries efficiently.
- **Reduce Python Overhead**: Instead of calling `buffer` $N$ times from Python, we call it once, passing $N$ geometries.
- **Improved Memory Locality**: Vectorized operations can better utilize CPU caches by processing contiguous blocks of memory.

### 2. Specific Improvements
- **`sidewalk=no`**: Road buffering is now a single vectorized call.
- **`sidewalk=left/right`**: The `parallel_offset` followed by a `buffer(1.0)` is now fully vectorized. This is particularly impactful as `parallel_offset` is a relatively expensive geometric operation.
- **`sidewalk=yes/both`**: Similar to the `no` case, this is now a single vectorized operation.

## 📊 Measured Improvement
Direct benchmarking in this environment was **impractical** due to the inability to install required geospatial dependencies (e.g., `geopandas`, `shapely`) without internet access.

However, the theoretical performance gain for vectorization in GeoPandas is typically **one to two orders of magnitude** (10x-100x speedup) depending on the number of features. For large urban datasets that this tool is designed for, this change will result in a measurably faster execution of the sidewalk generation process.
