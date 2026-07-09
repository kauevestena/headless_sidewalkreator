import time
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from headless_sidewalkreator import generate_protoblocks

def main():
    print("Large-scale test: Curitiba, Brazil")

    # Coordinates for a central area in Curitiba
    # -25.4284, -49.2733 is roughly city center
    bbox = (-49.28, -25.44, -49.26, -25.42)

    print(f"  Bounding box: {bbox}")

    start_time = time.time()
    try:
        protoblocks_gdf = generate_protoblocks(
            bbox=bbox,
            parameters={
                "timeout": 300,  # 5 minutes
            }
        )
        end_time = time.time()

        duration = end_time - start_time
        count = len(protoblocks_gdf)

        print(f"  Generated {count} protoblocks in {duration:.4f} seconds")

        # Save results
        protoblocks_gdf.to_file("debug/curitiba_protoblocks.geojson", driver="GeoJSON")

        # Plot
        fig, ax = plt.subplots(figsize=(10, 10))
        protoblocks_gdf.plot(ax=ax, alpha=0.5, edgecolor='black', facecolor='green')
        ax.set_title(f"Protoblocks Curitiba (Found {count} blocks)")
        plt.savefig("debug/curitiba_illustration.png")
        plt.close()

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
