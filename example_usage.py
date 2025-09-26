"""Example usage of the new GeoDataFrame-based API."""

import geopandas as gpd
from shapely.geometry import Polygon
from headless_sidewalkreator import sidewalkreator

# Example: User handles their own I/O
def example_usage():
    """Demonstrate the new GeoDataFrame-based API."""
    
    # 1. User loads their own input polygon
    polygon = Polygon([(-1, -1), (-1, 2), (2, 2), (2, -1), (-1, -1)])
    input_polygon_gdf = gpd.GeoDataFrame(geometry=[polygon], crs="EPSG:4326")
    
    # 2. User can optionally load their own OSM data
    # If osm_gdf is None, it will be fetched automatically
    osm_gdf = None  # Let the function fetch OSM data
    
    # 3. User can provide custom parameters
    custom_params = {
        "buffer_dist": 2.5,
        "timeout": 120,
        "split_max_len": 50.0
    }
    
    # 4. Call the new API function
    result = sidewalkreator(
        input_polygon_gdf=input_polygon_gdf,
        osm_gdf=osm_gdf,
        parameters=custom_params,
        ignore_existing=False
    )
    
    # 5. Extract the results - all are GeoDataFrames ready for use
    sidewalks_gdf = result['sidewalks']
    crossings_gdf = result['crossings']
    kerbs_gdf = result['kerbs']
    protoblocks_gdf = result['protoblocks']  # For debugging/analysis
    intersection_points_gdf = result['intersection_points']  # For debugging
    parameters_used = result['parameters']  # Runtime parameters
    
    # 6. User can now handle output as needed:
    # - Save to files in their preferred format
    # - Further process the geometries
    # - Combine with other data
    # - Use in web applications
    # - etc.
    
    print(f"Generated {len(sidewalks_gdf)} sidewalk segments")
    print(f"Generated {len(crossings_gdf)} crossings")
    print(f"Generated {len(kerbs_gdf)} kerbs")
    print(f"Parameters used: {parameters_used}")
    
    # Example: Save results in user's preferred format
    if not sidewalks_gdf.empty:
        sidewalks_gdf.to_file("my_sidewalks.geojson", driver="GeoJSON")
    if not crossings_gdf.empty:
        crossings_gdf.to_file("my_crossings.gpkg", driver="GPKG")
    
    return result

if __name__ == "__main__":
    example_usage()