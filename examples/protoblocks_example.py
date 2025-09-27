#!/usr/bin/env python3
"""Example demonstrating standalone protoblocks generation."""

import geopandas as gpd
from shapely.geometry import Polygon, LineString
from headless_sidewalkreator import generate_protoblocks


def create_sample_data():
    """Create sample data for demonstration."""
    # Create a simple bounding box polygon
    polygon = Polygon([(-72.53, 42.37), (-72.52, 42.37), (-72.52, 42.38), (-72.53, 42.38)])
    input_gdf = gpd.GeoDataFrame(geometry=[polygon], crs="EPSG:4326")
    
    # Create a simple street network that forms blocks
    streets = [
        LineString([(-72.530, 42.370), (-72.520, 42.370)]),  # horizontal bottom
        LineString([(-72.530, 42.380), (-72.520, 42.380)]),  # horizontal top
        LineString([(-72.530, 42.370), (-72.530, 42.380)]),  # vertical left
        LineString([(-72.520, 42.370), (-72.520, 42.380)]),  # vertical right
        LineString([(-72.525, 42.370), (-72.525, 42.380)]),  # vertical middle
    ]
    
    osm_gdf = gpd.GeoDataFrame(
        {
            'highway': ['residential'] * len(streets),
            'building': [None] * len(streets),
            'geometry': streets,
        },
        crs="EPSG:4326"
    )
    
    return input_gdf, osm_gdf


def main():
    """Demonstrate protoblocks generation."""
    print("=== Standalone Protoblocks Generation Example ===\n")
    
    # Create sample data
    input_polygon_gdf, osm_data_gdf = create_sample_data()
    
    print("1. Using input polygon GeoDataFrame:")
    protoblocks_gdf = generate_protoblocks(
        input_polygon_gdf=input_polygon_gdf,
        osm_gdf=osm_data_gdf
    )
    print(f"   Generated {len(protoblocks_gdf)} protoblocks")
    print(f"   Protoblocks CRS: {protoblocks_gdf.crs}")
    if not protoblocks_gdf.empty:
        print(f"   Total area: {protoblocks_gdf.geometry.area.sum():.2f} square meters")
    
    print("\n2. Using bounding box:")
    bbox = (-72.53, 42.37, -72.52, 42.38)
    protoblocks_gdf2 = generate_protoblocks(
        bbox=bbox,
        osm_gdf=osm_data_gdf
    )
    print(f"   Generated {len(protoblocks_gdf2)} protoblocks")
    
    print("\n3. With custom parameters:")
    custom_params = {
        "timeout": 30,
        "fallback_default_width": 8.0,
    }
    protoblocks_gdf3 = generate_protoblocks(
        input_polygon_gdf=input_polygon_gdf,
        osm_gdf=osm_data_gdf,
        parameters=custom_params
    )
    print(f"   Generated {len(protoblocks_gdf3)} protoblocks with custom parameters")
    
    print("\n4. Save results to file:")
    if not protoblocks_gdf.empty:
        output_file = "/tmp/sample_protoblocks.geojson"
        protoblocks_gdf.to_file(output_file)
        print(f"   Protoblocks saved to: {output_file}")
    
    print("\n=== Example Complete ===")


if __name__ == "__main__":
    main()