import geopandas as gpd
from shapely.geometry import box
import matplotlib.pyplot as plt
from headless_sidewalkreator.generic_functions import grid_lines, clip_gdf, polygonize_lines_gdf
from headless_sidewalkreator.full_sidewalkreator_algorithm import _preprocess_osm_data

def diagnose_full_pipeline(w, h):
    print(f"\n--- Diagnosing Full Pipeline {w}x{h} grid ---")
    lines = grid_lines(w, h)
    osm_gdf = gpd.GeoDataFrame({'highway': ['residential'] * len(lines)}, geometry=lines, crs="EPSG:3857")
    input_box = box(1, 1, w + 1, h + 1)
    input_gdf = gpd.GeoDataFrame(geometry=[input_box], crs="EPSG:3857")
    clipped_gdf = clip_gdf(osm_gdf, input_gdf)
    splitted_gdf, _, _ = _preprocess_osm_data(clipped_gdf, input_gdf, {}, 6.0)

    from shapely.ops import polygonize
    lines_to_poly = list(splitted_gdf.geometry)
    clip_reproj = input_gdf.to_crs(splitted_gdf.crs)
    clip_union = clip_reproj.geometry.union_all()
    # ADD CLIP EXTERIOR
    lines_to_poly.append(clip_union.exterior)

    merged = gpd.GeoSeries(lines_to_poly, crs=splitted_gdf.crs).union_all()
    polygons = list(polygonize(merged))

    print(f"Total polygons found: {len(polygons)}")
    for i, poly in enumerate(polygons):
        print(f"  Poly {i}: area={poly.area:.4f}")

if __name__ == "__main__":
    diagnose_full_pipeline(4, 4)
