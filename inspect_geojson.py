import geopandas as gpd

def inspect_geojson(filepath):
    """Reads a GeoJSON file and prints information about its geometries."""
    try:
        gdf = gpd.read_file(filepath)
        print(f"Successfully read {filepath}")
        print(f"Number of geometries: {len(gdf)}")
        if not gdf.empty:
            print(f"Geometry types: {gdf.geometry.type.unique()}")
            print(f"Are all geometries valid: {gdf.geometry.is_valid.all()}")
            print("Areas of geometries:")
            for i, geom in enumerate(gdf.geometry):
                print(f"  Geometry {i}: {geom.area}")
    except Exception as e:
        print(f"Could not read or inspect {filepath}. Error: {e}")

if __name__ == "__main__":
    inspect_geojson("test/temp_test_output_persistent/sidewalk_areas.geojson")
    inspect_geojson("test/temp_test_output_persistent/smooth_roads.geojson")
