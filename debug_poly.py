import geopandas as gpd
from shapely.geometry import Polygon, LineString
from headless_sidewalkreator.generic_functions import polygonize_lines_gdf

# Recreate test_generate_protoblocks_with_polygon_gdf logic
test_polygon = Polygon([(-72.53, 42.37), (-72.52, 42.37), (-72.52, 42.38), (-72.53, 42.38)])
test_polygon_gdf = gpd.GeoDataFrame(geometry=[test_polygon], crs="EPSG:4326")

streets = [
    LineString([(-72.530, 42.370), (-72.520, 42.370)]),  # horizontal bottom
    LineString([(-72.530, 42.380), (-72.520, 42.380)]),  # horizontal top
    LineString([(-72.530, 42.370), (-72.530, 42.380)]),  # vertical left
    LineString([(-72.520, 42.370), (-72.520, 42.380)]),  # vertical right
]
osm_sample_gdf = gpd.GeoDataFrame(
    {
        'highway': ['residential', 'residential', 'residential', 'residential'],
        'geometry': streets,
    },
    crs="EPSG:4326"
)

# Call polygonize_lines_gdf directly to see what it's returning
print("Calling polygonize...")
result = polygonize_lines_gdf(osm_sample_gdf, clip_geom=test_polygon_gdf)
print("Result empty:", result.empty)
print("Result len:", len(result))
if not result.empty:
    for i, p in enumerate(result.geometry):
        print(f"Poly {i} area: {p.area}")

print("Test Polygon area:", test_polygon.area)
