import time
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiPoint
from shapely.ops import split
import sys
import os

# Add the project root to sys.path to import the module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from headless_sidewalkreator.generic_functions import split_sidewalks_by_protoblock_corners

def create_dummy_data(num_polygons=1000):
    polygons = []
    for i in range(num_polygons):
        # Create a simple square polygon
        poly = Polygon([(i, i), (i+1, i), (i+1, i+1), (i, i+1)])
        polygons.append(poly)

    protoblocks_gdf = gpd.GeoDataFrame(geometry=polygons, crs="EPSG:3857")

    # Create some sidewalk lines that cross these polygons
    lines = []
    for i in range(0, num_polygons, 10):
        line = LineString([(i, i+0.5), (i+10, i+0.5)])
        lines.append(line)

    sidewalks_gdf = gpd.GeoDataFrame(geometry=lines, crs="EPSG:3857")

    return sidewalks_gdf, protoblocks_gdf

def benchmark():
    print("Creating dummy data...")
    sidewalks_gdf, protoblocks_gdf = create_dummy_data(5000)

    print(f"Running split_sidewalks_by_protoblock_corners with {len(protoblocks_gdf)} protoblocks and {len(sidewalks_gdf)} sidewalks...")

    start_time = time.time()
    result = split_sidewalks_by_protoblock_corners(sidewalks_gdf, protoblocks_gdf)
    end_time = time.time()

    duration = end_time - start_time
    print(f"Time taken: {duration:.4f} seconds")
    print(f"Resulting segments: {len(result)}")

    return duration

if __name__ == "__main__":
    benchmark()
