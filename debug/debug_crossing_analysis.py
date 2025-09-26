#!/usr/bin/env python3
"""
Comprehensive debugging script for crossing generation analysis.
This script investigates why the full workflow generates 9 crossings 
for a 2×2 grid instead of the expected 8.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from headless_sidewalkreator.generic_functions import grid_lines, draw_crossings_gdf
from headless_sidewalkreator import sidewalkreator
import geopandas as gpd
from shapely.geometry import Polygon, Point, LineString
import matplotlib.pyplot as plt
import numpy as np

def analyze_intersections(gdf, title=""):
    """Analyze intersection points in a GeoDataFrame."""
    print(f"\n--- {title} Intersection Analysis ---")
    
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
    for i, (point_key, data) in enumerate(intersection_points.items()):
        road_count = len(set(data["roads"]))
        print(f"  Intersection {i}: {road_count} roads at {point_key}")
    
    return intersection_points


def create_grid_visualization():
    """Create visualization of the 2x2 grid layout."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    
    # Original grid layout
    lines = grid_lines(2, 2)
    gdf = gpd.GeoDataFrame({'geometry': lines}).set_crs('EPSG:4326')
    
    ax1.set_title("2×2 Grid Layout\n(Expected: 8 crossings)", fontsize=14, fontweight='bold')
    gdf.plot(ax=ax1, color='blue', linewidth=2)
    
    # Mark intersection points
    intersections = analyze_intersections(gdf, "Original Grid")
    for i, (point_key, data) in enumerate(intersections.items()):
        ax1.plot(point_key[0], point_key[1], 'ro', markersize=8)
        ax1.annotate(f'{i+1}', (point_key[0], point_key[1]), 
                    xytext=(5, 5), textcoords='offset points', fontsize=10)
    
    ax1.set_xlabel("X (longitude)")
    ax1.set_ylabel("Y (latitude)")
    ax1.grid(True, alpha=0.3)
    ax1.set_aspect('equal')
    
    # Mathematical explanation
    ax2.text(0.1, 0.9, "Mathematical Formula:", fontsize=14, fontweight='bold', transform=ax2.transAxes)
    ax2.text(0.1, 0.8, "C = 4wh - 2w - 2h", fontsize=12, family='monospace', transform=ax2.transAxes)
    ax2.text(0.1, 0.7, "For 2×2 grid:", fontsize=12, transform=ax2.transAxes)
    ax2.text(0.1, 0.6, "C = 4×2×2 - 2×2 - 2×2", fontsize=12, family='monospace', transform=ax2.transAxes)
    ax2.text(0.1, 0.5, "C = 16 - 4 - 4 = 8", fontsize=12, family='monospace', transform=ax2.transAxes)
    
    ax2.text(0.1, 0.35, "Grid Analysis:", fontsize=14, fontweight='bold', transform=ax2.transAxes)
    ax2.text(0.1, 0.25, f"• Grid lines: {len(lines)}", fontsize=12, transform=ax2.transAxes)
    ax2.text(0.1, 0.2, f"• Intersections: {len(intersections)}", fontsize=12, transform=ax2.transAxes)
    ax2.text(0.1, 0.15, "• Roads per intersection: 2", fontsize=12, transform=ax2.transAxes)
    
    ax2.text(0.1, 0.05, "Issue: Full workflow generates 9 crossings", 
             fontsize=12, color='red', transform=ax2.transAxes)
    
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)
    ax2.axis('off')
    
    plt.tight_layout()
    plt.savefig('grid_layout_analysis.png', dpi=150, bbox_inches='tight')
    print("\n📊 Grid visualization saved as 'grid_layout_analysis.png'")
    return fig


def debug_coordinate_transformations():
    """Debug the effects of coordinate transformations."""
    print("\n=== COORDINATE TRANSFORMATION ANALYSIS ===")
    
    # Setup grid
    width, height = 2, 2
    lines = grid_lines(width, height)
    osm_gdf = gpd.GeoDataFrame({'geometry': lines}).set_crs('EPSG:4326')
    
    print(f"Original coordinate range:")
    bounds = osm_gdf.total_bounds
    print(f"  X: {bounds[0]:.6f} to {bounds[2]:.6f}")
    print(f"  Y: {bounds[1]:.6f} to {bounds[3]:.6f}")
    
    # Reproject like the full workflow does
    central_meridian = (bounds[0] + bounds[2]) / 2
    reproj_crs = f'+proj=tmerc +lat_0=0 +lon_0={central_meridian} +k=1 +x_0=500000 +y_0=0 +datum=WGS84 +units=m +no_defs'
    osm_reproj = osm_gdf.to_crs(reproj_crs)
    
    print(f"\nReprojected coordinate range:")
    bounds_reproj = osm_reproj.total_bounds
    print(f"  X: {bounds_reproj[0]:.1f} to {bounds_reproj[2]:.1f} meters")
    print(f"  Y: {bounds_reproj[1]:.1f} to {bounds_reproj[3]:.1f} meters")
    
    # Test crossing generation on both
    crossings_orig = draw_crossings_gdf(osm_gdf, sidewalks_gdf=None)
    crossings_reproj = draw_crossings_gdf(osm_reproj, sidewalks_gdf=None)
    
    print(f"\nCrossing generation results:")
    print(f"  Original coordinates: {len(crossings_orig)} crossings")
    print(f"  Reprojected coordinates: {len(crossings_reproj)} crossings") 
    
    # Analyze intersections in both coordinate systems
    analyze_intersections(osm_gdf, "Original Coordinates")
    analyze_intersections(osm_reproj, "Reprojected Coordinates")
    
    return len(crossings_orig), len(crossings_reproj)


def debug_full_workflow():
    """Debug the full sidewalkreator workflow."""
    print("\n=== FULL WORKFLOW ANALYSIS ===")
    
    # Setup identical to test
    width, height = 2, 2
    lines = grid_lines(width, height)
    osm_gdf = gpd.GeoDataFrame({
        'geometry': lines,
        'highway': ['residential'] * len(lines),
        'building': [None] * len(lines),
        'amenity': [None] * len(lines), 
        'shop': [None] * len(lines),
    })
    osm_gdf = osm_gdf.set_crs('EPSG:4326')
    
    # Create input polygon
    margin = 0.1
    bounds = Polygon([
        (-margin, -margin), 
        (-margin, height + 2 + margin), 
        (width + 2 + margin, height + 2 + margin), 
        (width + 2 + margin, -margin), 
        (-margin, -margin)
    ])
    input_polygon_gdf = gpd.GeoDataFrame(geometry=[bounds], crs='EPSG:4326')
    
    print("Input parameters:")
    print(f"  Grid size: {width}×{height}")
    print(f"  Lines: {len(lines)}")
    print(f"  Input polygon bounds: {input_polygon_gdf.total_bounds}")
    
    # Run full workflow
    result = sidewalkreator(input_polygon_gdf=input_polygon_gdf, osm_gdf=osm_gdf)
    
    print(f"\nFull workflow results:")
    for key, value in result.items():
        if hasattr(value, '__len__'):
            print(f"  {key}: {len(value)} features")
        else:
            print(f"  {key}: {value}")
    
    crossings_full = result['crossings']
    print(f"\n🔍 CRITICAL: Full workflow generated {len(crossings_full)} crossings")
    print(f"Expected: 8 crossings")
    print(f"Difference: +{len(crossings_full) - 8}")
    
    return len(crossings_full)


def comprehensive_debug_analysis():
    """Run comprehensive debugging analysis."""
    print("🔍 COMPREHENSIVE CROSSING GENERATION DEBUG ANALYSIS")
    print("=" * 60)
    
    # Create visualization
    fig = create_grid_visualization()
    
    # Test coordinate transformations
    orig_count, reproj_count = debug_coordinate_transformations()
    
    # Test full workflow
    full_count = debug_full_workflow()
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 SUMMARY OF RESULTS")
    print("=" * 60)
    
    expected = 8
    results = [
        ("Direct API (original coords)", orig_count, orig_count == expected),
        ("Direct API (reprojected)", reproj_count, reproj_count == expected),
        ("Full workflow", full_count, full_count == expected)
    ]
    
    for test_name, count, is_correct in results:
        status = "✅ CORRECT" if is_correct else "❌ INCORRECT"
        print(f"{test_name:.<25} {count:>2} crossings {status}")
    
    # Identify the problem
    print(f"\n🎯 PROBLEM IDENTIFICATION:")
    if orig_count == expected and full_count != expected:
        print("- Direct API works correctly")
        print("- Full workflow has issues")
        print("- Likely causes:")
        print("  1. Different processing steps in full workflow")
        print("  2. Additional coordinate transformations")
        print("  3. Multiple calls to crossing generation")
        print("  4. Different algorithm parameters")
    elif reproj_count != expected:
        print("- Coordinate reprojection affects results")
        print("- This is likely the root cause")
    else:
        print("- All tests match expected results")
    
    print(f"\n📝 RECOMMENDATIONS:")
    print("1. Add debug logging to full workflow")
    print("2. Compare algorithm parameters between direct API and full workflow")
    print("3. Check for multiple crossing generation calls")
    print("4. Verify coordinate transformation effects")
    
    return results


if __name__ == "__main__":
    results = comprehensive_debug_analysis()