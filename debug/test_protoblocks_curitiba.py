import time
import pandas as pd
from headless_sidewalkreator import generate_protoblocks
from headless_sidewalkreator.generic_functions import (
    bbox_to_gdf,
    clip_gdf,
    fetch_street_network_for_bbox,
)

try:
    import matplotlib.pyplot as plt
except ModuleNotFoundError:
    plt = None


def main():
    print("Large-scale test: Curitiba, Brazil")

    # Coordinates for a central area in Curitiba
    # -25.4284, -49.2733 is roughly city center
    bbox = (-49.28, -25.44, -49.26, -25.42)
    timeout = 300

    print(f"  Bounding box: {bbox}")
    input_gdf = bbox_to_gdf(bbox)

    start_time = time.time()
    try:
        osm_gdf = fetch_street_network_for_bbox(bbox, timeout=timeout)
        protoblocks_gdf = generate_protoblocks(
            input_polygon_gdf=input_gdf,
            osm_gdf=osm_gdf,
            parameters={
                "timeout": timeout,
            }
        )
        end_time = time.time()

        duration = end_time - start_time
        count = len(protoblocks_gdf)

        print(f"  Generated {count} protoblocks in {duration:.4f} seconds")
        print(f"  Protoblocks CRS: {protoblocks_gdf.crs}")

        # Save web/map friendly results in lon/lat. GeoJSON consumers often
        # assume EPSG:4326 and ignore projected CRS metadata.
        protoblocks_wgs84 = protoblocks_gdf.to_crs("EPSG:4326")
        protoblocks_wgs84.to_file(
            "debug/curitiba_protoblocks.geojson",
            driver="GeoJSON",
        )
        protoblocks_gdf.to_file(
            "debug/curitiba_protoblocks_projected.gpkg",
            driver="GPKG",
        )
        print("  Saved WGS84 GeoJSON to debug/curitiba_protoblocks.geojson")
        print("  Saved projected layer to debug/curitiba_protoblocks_projected.gpkg")

        if plt is not None:
            clipped_osm_gdf = clip_gdf(osm_gdf, input_gdf)
            if "highway" in clipped_osm_gdf.columns:
                streets_gdf = clipped_osm_gdf[
                    clipped_osm_gdf["highway"].notna()
                ].copy()
            else:
                streets_gdf = clipped_osm_gdf.iloc[0:0].copy()
            streets_gdf = streets_gdf[
                streets_gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])
            ].copy()
            if (
                streets_gdf.crs is not None
                and streets_gdf.crs.to_string() != "EPSG:4326"
            ):
                streets_gdf = streets_gdf.to_crs("EPSG:4326")

            fig, ax = plt.subplots(figsize=(10, 10))
            protoblocks_wgs84.plot(
                ax=ax,
                alpha=0.35,
                edgecolor="black",
                facecolor="green",
                linewidth=0.5,
            )
            if not streets_gdf.empty:
                streets_gdf.plot(ax=ax, color="red", linewidth=0.7)
            input_gdf.boundary.plot(ax=ax, color="blue", linewidth=1.2)
            ax.set_title(f"Protoblocks and streets Curitiba (Found {count} blocks)")
            plt.savefig("debug/curitiba_illustration.png", dpi=160)
            plt.close()
        else:
            print("  Skipping plot because matplotlib is not installed.")

        # Statistics
        if not protoblocks_gdf.empty:
            # We need to project to a local CRS for accurate area measurement
            # Curitiba uses SIRGAS 2000 / UTM zone 22S (EPSG:31982)
            proj_gdf = protoblocks_gdf.to_crs("EPSG:31982")
            areas = proj_gdf.geometry.area

            stats = {
                'count': count,
                'duration': duration,
                'total_area_km2': areas.sum() / 1e6,
                'mean_area_m2': areas.mean(),
                'median_area_m2': areas.median(),
                'min_area_m2': areas.min(),
                'max_area_m2': areas.max()
            }
            pd.Series(stats).to_csv("debug/curitiba_stats.csv")
            print("  Statistics saved to debug/curitiba_stats.csv")
            print(pd.Series(stats))

    except Exception as e:
        print(f"  Error during Curitiba test: {e}")


if __name__ == "__main__":
    main()
