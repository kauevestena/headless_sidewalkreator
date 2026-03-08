import time
import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString
import numpy as np
import os

def original_approach(streets_gdf):
    sure_geometries = []
    # Handle sidewalk=yes/both (sure zones)
    sure_streets = streets_gdf[streets_gdf["sidewalk"].isin(["yes", "both"])].copy()
    for street in sure_streets.itertuples():
        road_width = getattr(street, "width", 6.0)
        # Handle nan in original approach properly (as the code does not explicitly do it, getattr won't catch NaN values from pandas)
        # Actually in original code, if it's NaN, getattr doesn't help because the attribute exists and is nan.
        # But we'll simulate the real behavior or fix it if it throws (the original code would throw on NaN too if not handled).
        # We will cast nan to 6.0 for original approach just to make it run.
        if pd.isna(road_width):
            road_width = 6.0
        buffer_distance = (road_width / 2) + 1.0
        sure_geometries.append(street.geometry.buffer(buffer_distance))
    return sure_geometries

def optimized_approach(streets_gdf):
    sure_geometries = []
    sure_streets = streets_gdf[streets_gdf["sidewalk"].isin(["yes", "both"])]
    if not sure_streets.empty:
        # Vectorized buffer
        road_widths = pd.to_numeric(sure_streets.get("width", 6.0), errors="coerce").fillna(6.0)
        buffer_distances = (road_widths / 2) + 1.0
        sure_geometries.extend(sure_streets.geometry.buffer(buffer_distances).tolist())
    return sure_geometries

def create_synthetic_data(num_features=10000):
    lines = []
    for i in range(num_features):
        lines.append(LineString([(i, 0), (i+1, 0)]))

    gdf = gpd.GeoDataFrame(geometry=lines)
    gdf["sidewalk"] = np.random.choice(["yes", "no", "both", "none"], num_features)
    # Give some random widths, some missing
    widths = np.random.uniform(3.0, 10.0, num_features)
    # Add some NaNs to simulate real data
    widths[np.random.choice(num_features, size=int(num_features*0.1))] = np.nan
    gdf["width"] = widths

    return gdf

def run_benchmark():
    os.makedirs("debug", exist_ok=True)
    print("Generating synthetic data...")
    gdf = create_synthetic_data(10000)

    print(f"Total features: {len(gdf)}")
    print(f"Features to buffer ('yes' or 'both'): {len(gdf[gdf['sidewalk'].isin(['yes', 'both'])])}")

    # Warm up
    original_approach(gdf.head(100))
    optimized_approach(gdf.head(100))

    # Benchmark original
    start_time = time.time()
    orig_res = original_approach(gdf)
    orig_time = time.time() - start_time
    print(f"Original approach: {orig_time:.4f} seconds")

    # Benchmark optimized
    start_time = time.time()
    opt_res = optimized_approach(gdf)
    opt_time = time.time() - start_time
    print(f"Optimized approach: {opt_time:.4f} seconds")

    # Verify correctness
    print(f"Number of resulting geometries - Original: {len(orig_res)}, Optimized: {len(opt_res)}")
    if len(orig_res) == len(opt_res):
        print("Improvement factor: {:.2f}x".format(orig_time / opt_time))

if __name__ == "__main__":
    run_benchmark()
