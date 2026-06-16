import geopandas as gpd
from shapely.geometry import Polygon, LineString
from shapely.ops import polygonize_full
import numpy as np

test_polygon = Polygon([(-72.53, 42.37), (-72.52, 42.37), (-72.52, 42.38), (-72.53, 42.38)])
test_polygon_gdf = gpd.GeoDataFrame(geometry=[test_polygon], crs="EPSG:4326")

streets = [
    LineString([(-72.530, 42.370), (-72.520, 42.370)]),  # horizontal bottom
    LineString([(-72.530, 42.380), (-72.520, 42.380)]),  # horizontal top
    LineString([(-72.530, 42.370), (-72.530, 42.380)]),  # vertical left
    LineString([(-72.520, 42.370), (-72.520, 42.380)]),  # vertical right
]

clip_geom_union = test_polygon_gdf.geometry.union_all()
lines = streets.copy()
lines.append(clip_geom_union.exterior)

merged_lines = gpd.GeoSeries(lines, crs="EPSG:4326").union_all()
polys, _, _, _ = polygonize_full(merged_lines)
polygons = list(polys.geoms)

print("Pre-filtered polygons:", len(polygons))
for p in polygons:
    if len(polygons) == 1 and p.area >= clip_geom_union.area * 0.99:
        print("This is the exact same bounding box! KEEP")
    elif p.area >= clip_geom_union.area * 0.5:
        print("This is the outer shell! DROP")
    else:
        print("This is an inner block! KEEP")
