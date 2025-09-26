"""
Comprehensive testing of crossing generation across many grid sizes.
This test validates the mathematical formula C = 4wh - 2w - 2h for various grid combinations.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import random
import geopandas as gpd
from shapely.geometry import Polygon
from headless_sidewalkreator.generic_functions import grid_lines, draw_crossings_gdf
from headless_sidewalkreator import sidewalkreator


def test_grid_crossings(width, height, test_reprojection=True):
    """Test crossing generation for a specific grid size."""
    # Create grid
    lines = grid_lines(width, height)
    osm_gdf = gpd.GeoDataFrame({
        'geometry': lines,
        'highway': ['residential'] * len(lines),
        'building': [None] * len(lines),
        'amenity': [None] * len(lines), 
        'shop': [None] * len(lines),
    })
    osm_gdf = osm_gdf.set_crs('EPSG:4326')
    
    # Test in original coordinates
    crossings_original = draw_crossings_gdf(osm_gdf)
    
    # Test with reprojection if requested
    crossings_reprojected = None
    if test_reprojection:
        bbox = osm_gdf.total_bounds
        central_meridian = (bbox[0] + bbox[2]) / 2
        reproj_crs = f'+proj=tmerc +lat_0=0 +lon_0={central_meridian} +k=1 +x_0=500000 +y_0=0 +datum=WGS84 +units=m +no_defs'
        osm_reproj = osm_gdf.to_crs(reproj_crs)
        crossings_reprojected = draw_crossings_gdf(osm_reproj)
    
    # Test with full sidewalkreator workflow
    margin = 0.1
    bounds = Polygon([
        (-margin, -margin),
        (-margin, height + 2 + margin),
        (width + 2 + margin, height + 2 + margin),
        (width + 2 + margin, -margin),
        (-margin, -margin)
    ])
    input_polygon_gdf = gpd.GeoDataFrame(geometry=[bounds], crs='EPSG:4326')
    
    try:
        result = sidewalkreator(
            input_polygon_gdf=input_polygon_gdf,
            osm_gdf=osm_gdf
        )
        crossings_full_workflow = result['crossings']
        full_workflow_count = len(crossings_full_workflow)
    except Exception as e:
        print(f"  Full workflow failed: {e}")
        full_workflow_count = None
    
    # Calculate expected crossings using formula
    expected = 4 * width * height - 2 * width - 2 * height
    
    return {
        'width': width,
        'height': height,
        'expected': expected,
        'original_coords': len(crossings_original),
        'reprojected': len(crossings_reprojected) if crossings_reprojected is not None else None,
        'full_workflow': full_workflow_count,
        'total_intersections': (width + 1) * (height + 1)
    }


def main():
    print("Comprehensive Grid Crossing Test")
    print("=" * 50)
    print("Testing mathematical formula: C = 4wh - 2w - 2h")
    print()
    
    # Test systematic combinations first
    print("1. Systematic Testing (small grids):")
    systematic_cases = [
        (1, 1), (1, 2), (1, 3), (1, 4), (1, 5),
        (2, 1), (2, 2), (2, 3), (2, 4), (2, 5),
        (3, 1), (3, 2), (3, 3), (3, 4), (3, 5),
        (4, 1), (4, 2), (4, 3), (4, 4), (4, 5),
        (5, 1), (5, 2), (5, 3), (5, 4), (5, 5),
    ]
    
    results = []
    for w, h in systematic_cases:
        try:
            result = test_grid_crossings(w, h, test_reprojection=False)  # Skip reprojection for speed
            results.append(result)
            
            expected = result['expected']
            original = result['original_coords']
            full = result['full_workflow']
            
            status_orig = '✓' if expected == original else '✗'
            status_full = '✓' if expected == full else '✗' if full is not None else '?'
            
            print(f"  {w}×{h}: Expected={expected:2d}, Original={original:2d} {status_orig}, Full={full or '?':2} {status_full}")
            
        except Exception as e:
            print(f"  {w}×{h}: ERROR - {e}")
    
    print()
    
    # Test 10 random combinations as requested
    print("2. Random Testing (w,h from 1-10):")
    random.seed(42)  # For reproducible results
    random_cases = [(random.randint(1, 10), random.randint(1, 10)) for _ in range(10)]
    
    for w, h in random_cases:
        try:
            result = test_grid_crossings(w, h, test_reprojection=True)
            results.append(result)
            
            expected = result['expected']
            original = result['original_coords']
            reprojected = result['reprojected']
            full = result['full_workflow']
            
            status_orig = '✓' if expected == original else '✗'
            status_reproj = '✓' if expected == reprojected else '✗' if reprojected is not None else '?'
            status_full = '✓' if expected == full else '✗' if full is not None else '?'
            
            print(f"  {w}×{h}: Expected={expected:2d}, Orig={original:2d} {status_orig}, Reproj={reprojected or '?':2} {status_reproj}, Full={full or '?':2} {status_full}")
            
        except Exception as e:
            print(f"  {w}×{h}: ERROR - {e}")
    
    print()
    
    # Analysis
    print("3. Analysis:")
    correct_original = sum(1 for r in results if r['expected'] == r['original_coords'])
    correct_full = sum(1 for r in results if r['full_workflow'] is not None and r['expected'] == r['full_workflow'])
    total_tests = len(results)
    
    print(f"  Original coordinates: {correct_original}/{total_tests} correct ({correct_original/total_tests*100:.1f}%)")
    print(f"  Full workflow: {correct_full}/{total_tests} correct ({correct_full/total_tests*100:.1f}%)")
    
    # Show which cases are failing
    print()
    print("4. Failing Cases Analysis:")
    failing_cases = [r for r in results if r['expected'] != r['original_coords'] or 
                     (r['full_workflow'] is not None and r['expected'] != r['full_workflow'])]
    
    if failing_cases:
        print("  Grid sizes that don't match formula:")
        for case in failing_cases[:10]:  # Show first 10 failing cases
            w, h = case['width'], case['height']
            expected = case['expected']
            original = case['original_coords']
            full = case['full_workflow']
            intersections = case['total_intersections']
            
            print(f"    {w}×{h}: Expected={expected}, Got={original} (full={full}), Intersections={intersections}")
    else:
        print("  All test cases pass! ✓")
    
    return results


if __name__ == "__main__":
    results = main()