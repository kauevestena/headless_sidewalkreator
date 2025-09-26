#!/usr/bin/env python3
"""
Detailed debugging script with intersection analysis.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from headless_sidewalkreator.generic_functions import grid_lines, draw_crossings_gdf
import geopandas as gpd

def analyze_intersections(gdf, title=""):
    """Analyze intersection points in detail."""
    print(f"\n--- {title} ---")
    
    intersections = gdf.sindex.query(gdf.geometry, predicate="intersects")
    intersection_points = {}
    
    for i in range(len(intersections[0])):
        idx1 = intersections[0][i]
        idx2 = intersections[1][i]
        if idx1 >= idx2:
            continue
            
        line1 = gdf.geometry.iloc[idx1]
        line2 = gdf.geometry.iloc[idx2]
        intersection = line1.intersection(line2)
        
        if intersection.geom_type == "Point":
            point_key = (round(intersection.x, 6), round(intersection.y, 6))
            if point_key not in intersection_points:
                intersection_points[point_key] = {"point": intersection, "roads": []}
            intersection_points[point_key]["roads"].extend([idx1, idx2])
    
    print(f"Total intersections: {len(intersection_points)}")
    
    # Count intersections by road count
    road_count_stats = {}
    for point_key, data in intersection_points.items():
        road_count = len(set(data["roads"]))
        if road_count not in road_count_stats:
            road_count_stats[road_count] = 0
        road_count_stats[road_count] += 1
        print(f"  {point_key}: {road_count} roads")
    
    print(f"Road count statistics:")
    for road_count, count in sorted(road_count_stats.items()):
        print(f"  {road_count} roads: {count} intersections")
    
    # Check which intersections are valid for ABCDE (2+ roads)
    valid_intersections = {
        k: v for k, v in intersection_points.items() 
        if len(set(v["roads"])) >= 2
    }
    print(f"Valid intersections for ABCDE: {len(valid_intersections)}")
    
    return intersection_points, valid_intersections

def debug_abcde_behavior():
    """Debug ABCDE algorithm behavior in detail."""
    print("🔍 DETAILED ABCDE DEBUGGING")
    print("=" * 40)
    
    # Setup grid
    width, height = 2, 2
    lines = grid_lines(width, height)
    osm_gdf = gpd.GeoDataFrame({'geometry': lines}).set_crs('EPSG:4326')
    
    print(f"Grid setup: {width}×{height}")
    print(f"Lines generated: {len(lines)}")
    for i, line in enumerate(lines):
        coords = list(line.coords)
        print(f"  Line {i}: {coords[0]} -> {coords[1]}")
    
    # Analyze intersections
    intersection_points, valid_intersections = analyze_intersections(osm_gdf, "Intersection Analysis")
    
    # Test crossing generation
    print(f"\n--- Crossing Generation Test ---")
    crossings = draw_crossings_gdf(osm_gdf, sidewalks_gdf=None)
    expected = 4*width*height - 2*width - 2*height
    
    print(f"Crossings generated: {len(crossings)}")
    print(f"Expected crossings: {expected}")
    print(f"Difference: {len(crossings) - expected}")
    
    # Try to understand why we get 9 instead of 8
    print(f"\n--- Analysis ---")
    print(f"Formula: C = 4wh - 2w - 2h = 4×{width}×{height} - 2×{width} - 2×{height} = {expected}")
    print(f"Actual intersections: {len(intersection_points)}")
    print(f"Valid for ABCDE: {len(valid_intersections)}")
    
    if len(crossings) > expected:
        print(f"\n🔍 INVESTIGATION: Why {len(crossings)} instead of {expected}?")
        print("Possible causes:")
        print("1. ABCDE generates multiple crossings per intersection")
        print("2. Fallback generates additional crossings")  
        print("3. Algorithm logic doesn't match mathematical formula")
        print("4. Formula doesn't apply to this crossing generation method")
        
        # Let's check what the fallback does
        print(f"\nIf fallback generates 1 crossing per intersection:")
        print(f"  Would generate: {len(intersection_points)} crossings")
        print(f"  Actual result: {len(crossings)} crossings")
        
        if len(crossings) == len(intersection_points):
            print("✅ CONCLUSION: Algorithm generates 1 crossing per intersection")
            print("❌ PROBLEM: This doesn't match the mathematical formula")
        else:
            print("❓ CONCLUSION: More complex behavior")

if __name__ == "__main__":
    debug_abcde_behavior()