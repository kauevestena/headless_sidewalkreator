# Learnings from Protoblocks Bug Fix and Testing

- **Polygonization Heuristics**: Filtering the "background" polygon in a clipping operation is tricky. A simple area-based check (`area >= 50%`) fails when internal blocks are large or when precision issues cause edge blocks to merge.
- **Robust Noding**: Spatial operations like `union_all` and `polygonize` are highly sensitive to floating point precision. Using `shapely.set_precision` (e.g., `1e-4`) is critical for ensuring that lines that are "meant" to touch actually node together, especially after coordinate transformations (like UTM projection).
- **Overlap Ratio**: Combining area checks with boundary overlap (`overlap_ratio > 0.95`) provides a much more robust way to identify the "outer shell" of a polygonization result.
- **Grid Testing**: Using simple grids with known properties is an extremely effective way to catch subtle geometric bugs that might be hidden in complex real-world data.
