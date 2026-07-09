# Learnings from Protoblocks Testing Task

- **Environment Setup**: Standard `pytest` in this environment might miss dependencies like `geopandas`. Installing with `pip install -e .[dev]` is the correct way to ensure the package and its dependencies are available.
- **Protoblock Clipping**: The `polygonize_lines_gdf` function uses a heuristic to filter out the "outer background" polygon (area >= 50% of the bounding box). This is effective for urban blocks but requires careful selection of the clipping area in tests to ensure inner blocks are not accidentally merged with the background or excluded.
- **Grid Testing**: `grid_lines` generates lines with specific overhangs. When testing for a specific number of blocks, the clipping polygon should ideally be aligned with the intended block boundaries or slightly inside them to avoid capturing boundary slivers.
- **Large-Scale Validation**: Real-world data from Curitiba provided a robust test case for performance (~285 blocks in ~72s, though cached/subsequent runs are much faster as seen in the final verification).
