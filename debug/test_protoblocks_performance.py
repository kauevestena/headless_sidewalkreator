import time
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import box
from headless_sidewalkreator import generate_protoblocks
from headless_sidewalkreator.generic_functions import grid_lines

def run_grid_test(w, h):
    print(f"Testing {w}x{h} grid...")
    lines = grid_lines(w, h)

    osm_gdf = gpd.GeoDataFrame(
        {'highway': ['residential'] * len(lines)},
        geometry=lines,
        crs="EPSG:3857"
    )

    # Grid inner squares are (1,1) to (w+1, h+1)
    # By using a slightly smaller box (1.001 to w+0.999), we exclude all the edge slivers.
    # This should leave exactly w*h blocks.
    input_polygon = box(1.001, 1.001, w + 0.999, h + 0.999)
    input_gdf = gpd.GeoDataFrame(geometry=[input_polygon], crs="EPSG:3857")

    start_time = time.time()
    protoblocks_gdf = generate_protoblocks(
        input_polygon_gdf=input_gdf,
        osm_gdf=osm_gdf
    )
    end_time = time.time()

    duration = end_time - start_time
    count = len(protoblocks_gdf)

    # Save a plot for the 5x5 case
    if w == 5 and h == 5:
        fig, ax = plt.subplots(figsize=(8, 8))
        protoblocks_gdf.plot(ax=ax, alpha=0.5, edgecolor='black', facecolor='cyan')
        osm_gdf.plot(ax=ax, color='red', linewidth=1)
        ax.set_title(f"Protoblocks Grid {w}x{h} (Found {count} blocks)")
        plt.savefig("debug/grid_5x5_illustration.png")
        plt.close()

    print(f"  Generated {count} protoblocks in {duration:.4f} seconds")
    return {
        'width': w,
        'height': h,
        'expected_count': w * h,
        'actual_count': count,
        'duration': duration
    }

def main():
    results = []
    grid_sizes = range(2, 11)

    for size in grid_sizes:
        res = run_grid_test(size, size)
        results.append(res)

    df = pd.DataFrame(results)
    df.to_csv("debug/grid_performance_results.csv", index=False)

    plt.figure(figsize=(10, 6))
    plt.plot(df['width'] * df['height'], df['duration'], marker='o')
    plt.xlabel('Number of blocks (Expected)')
    plt.ylabel('Duration (seconds)')
    plt.title('Protoblocks Generation Performance')
    plt.grid(True)
    plt.savefig("debug/performance_plot.png")
    plt.close()

    print("\nResults saved to debug/grid_performance_results.csv")
    print(df)

if __name__ == "__main__":
    main()
