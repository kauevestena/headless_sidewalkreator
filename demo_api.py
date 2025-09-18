"""Simple demonstration of the new GeoDataFrame-based API.

This script shows how the new API allows users to handle I/O themselves.
"""

import geopandas as gpd
from shapely.geometry import Polygon, LineString
from headless_sidewalkreator import generate_sidewalks_gdf

def demo_new_api():
    """Demonstrate the new GeoDataFrame-based API with a simple example."""
    print("=== GeoDataFrame-based API Demo ===\n")
    
    # 1. Create sample input data (user would load from their own sources)
    print("1. Creating sample input data...")
    
    # Input polygon - area of interest  
    polygon = Polygon([(-1, -1), (-1, 2), (2, 2), (2, -1), (-1, -1)])
    input_polygon_gdf = gpd.GeoDataFrame(geometry=[polygon], crs="EPSG:4326")
    print(f"   Input polygon created: {input_polygon_gdf.geometry[0].area:.2f} square degrees")
    
    # Sample OSM data (street network)
    streets = [
        LineString([(0, 0), (0, 1)]),      # Vertical street
        LineString([(0, 1), (1, 1)]),      # Horizontal street  
        LineString([(1, 1), (1, 0)]),      # Vertical street
        LineString([(1, 0), (0, 0)]),      # Horizontal street
        LineString([(-0.5, 0.5), (1.5, 0.5)]),  # Crossing street
    ]
    
    osm_gdf = gpd.GeoDataFrame({
        'geometry': streets,
        'highway': ['residential'] * len(streets),
        'building': [None] * len(streets),
        'amenity': [None] * len(streets),
        'shop': [None] * len(streets),
    })
    osm_gdf = osm_gdf.set_crs("EPSG:4326")
    print(f"   Sample street network created: {len(osm_gdf)} street segments")
    
    # 2. Set custom parameters
    print("\n2. Setting custom parameters...")
    custom_params = {
        "buffer_dist": 1.5,
        "timeout": 30,
    }
    print(f"   Custom buffer distance: {custom_params['buffer_dist']}m")
    
    # 3. Call the new API
    print("\n3. Calling generate_sidewalks_gdf()...")
    try:
        result = generate_sidewalks_gdf(
            input_polygon_gdf=input_polygon_gdf,
            osm_gdf=osm_gdf,
            parameters=custom_params,
            ignore_existing=False
        )
        print("   ✅ API call successful!")
    except Exception as e:
        print(f"   ❌ API call failed: {e}")
        return
    
    # 4. Examine results
    print("\n4. Examining results...")
    print(f"   Result type: {type(result)}")
    print(f"   Result keys: {list(result.keys())}")
    
    for key, value in result.items():
        if key == 'parameters':
            print(f"   {key}: {type(value)} with {len(value)} parameters")
        else:
            print(f"   {key}: {type(value)} with {len(value)} features")
    
    # 5. Show flexibility - user can process results as needed
    print("\n5. Demonstrating flexibility...")
    
    sidewalks_gdf = result['sidewalks']
    crossings_gdf = result['crossings']
    protoblocks_gdf = result['protoblocks']
    
    print(f"   Protoblocks generated: {len(protoblocks_gdf)}")
    if not protoblocks_gdf.empty:
        total_area = protoblocks_gdf.geometry.area.sum()
        print(f"   Total protoblock area: {total_area:.2f} square meters")
    
    print(f"   Sidewalks generated: {len(sidewalks_gdf)}")
    if not sidewalks_gdf.empty:
        total_length = sidewalks_gdf.geometry.length.sum() 
        print(f"   Total sidewalk length: {total_length:.2f} meters")
    
    print(f"   Crossings generated: {len(crossings_gdf)}")
    
    # 6. User could save in any format they want
    print("\n6. Users can save results in any format:")
    print("   - sidewalks_gdf.to_file('sidewalks.geojson', driver='GeoJSON')")
    print("   - crossings_gdf.to_file('crossings.gpkg', driver='GPKG')")
    print("   - sidewalks_gdf.to_parquet('sidewalks.parquet')")
    print("   - Or use directly in web applications, further processing, etc.")
    
    print("\n=== Demo Complete ===")
    return result

if __name__ == "__main__":
    demo_new_api()