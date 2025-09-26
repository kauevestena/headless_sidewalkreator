#!/usr/bin/env python3
"""
Simple debugging script for crossing generation analysis.
"""

from headless_sidewalkreator.generic_functions import grid_lines, draw_crossings_gdf
from headless_sidewalkreator import sidewalkreator
import geopandas as gpd
from shapely.geometry import Polygon

def main():
    print("🔍 CROSSING GENERATION DEBUG ANALYSIS")
    print("=" * 50)
    
    # Setup 2x2 grid
    width, height = 2, 2
    lines = grid_lines(width, height)
    osm_gdf = gpd.GeoDataFrame({'geometry': lines}).set_crs('EPSG:4326')
    
    expected = 4*width*height - 2*width - 2*height
    print(f"Grid: {width}×{height}")
    print(f"Lines: {len(lines)}")
    print(f"Expected crossings: {expected}")
    
    # Test 1: Direct API
    print(f"\n--- Test 1: Direct API ---")
    crossings_direct = draw_crossings_gdf(osm_gdf, sidewalks_gdf=None)
    print(f"Result: {len(crossings_direct)} crossings {'✅' if len(crossings_direct) == expected else '❌'}")
    
    # Test 2: After reprojection  
    print(f"\n--- Test 2: After Reprojection ---")
    bbox = osm_gdf.total_bounds
    central_meridian = (bbox[0] + bbox[2]) / 2
    reproj_crs = f'+proj=tmerc +lat_0=0 +lon_0={central_meridian} +k=1 +x_0=500000 +y_0=0 +datum=WGS84 +units=m +no_defs'
    osm_reproj = osm_gdf.to_crs(reproj_crs)
    crossings_reproj = draw_crossings_gdf(osm_reproj, sidewalks_gdf=None)
    print(f"Result: {len(crossings_reproj)} crossings {'✅' if len(crossings_reproj) == expected else '❌'}")
    
    # Test 3: Full workflow
    print(f"\n--- Test 3: Full Workflow ---")
    margin = 0.1
    bounds = Polygon([(-margin, -margin), (-margin, 4+margin), (4+margin, 4+margin), (4+margin, -margin), (-margin, -margin)])
    input_polygon_gdf = gpd.GeoDataFrame(geometry=[bounds], crs='EPSG:4326')
    
    # Add required columns for full workflow
    osm_full = gpd.GeoDataFrame({
        'geometry': lines,
        'highway': ['residential'] * len(lines),
        'building': [None] * len(lines),
        'amenity': [None] * len(lines), 
        'shop': [None] * len(lines),
    }).set_crs('EPSG:4326')
    
    result = sidewalkreator(input_polygon_gdf=input_polygon_gdf, osm_gdf=osm_full)
    crossings_full = result['crossings']
    print(f"Result: {len(crossings_full)} crossings {'✅' if len(crossings_full) == expected else '❌'}")
    
    # Summary
    print(f"\n📊 SUMMARY")
    print(f"Expected: {expected} crossings")
    print(f"Direct API: {len(crossings_direct)} ({'CORRECT' if len(crossings_direct) == expected else 'WRONG'})")
    print(f"Reprojected: {len(crossings_reproj)} ({'CORRECT' if len(crossings_reproj) == expected else 'WRONG'})")
    print(f"Full workflow: {len(crossings_full)} ({'CORRECT' if len(crossings_full) == expected else 'WRONG'})")
    
    if len(crossings_full) != expected:
        print(f"\n🚨 ISSUE: Full workflow generates {len(crossings_full)} instead of {expected}")
        diff = len(crossings_full) - expected
        print(f"Difference: {'+' if diff > 0 else ''}{diff} crossings")

if __name__ == "__main__":
    main()