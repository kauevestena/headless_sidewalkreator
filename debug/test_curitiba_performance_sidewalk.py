import json
import os
import time
from pathlib import Path

import geopandas as gpd
import osmnx as ox

from headless_sidewalkreator import sidewalkreator
from headless_sidewalkreator.generic_functions import clip_gdf
from headless_sidewalkreator.osm_fetch import get_osm_data

try:
    import matplotlib.pyplot as plt
except ModuleNotFoundError:
    plt = None


PERFORMANCE_EXTRAS_HINT = "Install with: pip install -e '.[performance]'"
PROJECTED_CURITIBA_CRS = "EPSG:31982"
WGS84_CRS = "EPSG:4326"


def _empty_gdf(crs=WGS84_CRS) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(geometry=[], crs=crs)


def _safe_to_crs(gdf: gpd.GeoDataFrame, crs) -> gpd.GeoDataFrame:
    if gdf is None:
        return _empty_gdf(crs)
    if gdf.empty:
        return _empty_gdf(gdf.crs or crs)
    if gdf.crs is None:
        gdf = gdf.set_crs(WGS84_CRS)
    if str(gdf.crs) == str(crs):
        return gdf.copy()
    return gdf.to_crs(crs)


def _extract_road_lines(
    osm_gdf: gpd.GeoDataFrame,
    clip_geom: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    if osm_gdf is None or osm_gdf.empty or "geometry" not in osm_gdf.columns:
        return _empty_gdf(clip_geom.crs)

    roads_gdf = osm_gdf.copy()
    if roads_gdf.crs is None:
        roads_gdf = roads_gdf.set_crs(WGS84_CRS)

    if "highway" in roads_gdf.columns:
        roads_gdf = roads_gdf[
            roads_gdf["highway"].notna() & (roads_gdf["highway"] != "")
        ].copy()

    roads_gdf = roads_gdf[
        roads_gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])
    ].copy()
    roads_gdf = roads_gdf[roads_gdf.geometry.notna() & ~roads_gdf.geometry.is_empty]

    if roads_gdf.empty:
        return _empty_gdf(roads_gdf.crs)

    try:
        return clip_gdf(roads_gdf, clip_geom)
    except Exception:
        return roads_gdf


def _write_empty_geojson(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump({"type": "FeatureCollection", "features": []}, f)


def _write_wgs84(gdf: gpd.GeoDataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if gdf is None or gdf.empty:
        _write_empty_geojson(path)
        return
    _safe_to_crs(gdf, WGS84_CRS).to_file(path, driver="GeoJSON")


def _count(gdf: gpd.GeoDataFrame) -> int:
    if gdf is None or gdf.empty:
        return 0
    return len(gdf)


def _ensure_optional_osm_columns(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Keep provider payloads compatible with the full Sidewalkreator pipeline."""
    required_columns = [
        "highway",
        "building",
        "amenity",
        "shop",
        "addr:housenumber",
        "footway",
        "sidewalk",
    ]
    normalized = gdf.copy()
    for column in required_columns:
        if column not in normalized.columns:
            normalized[column] = None
    return normalized


def _length_km(gdf: gpd.GeoDataFrame, crs=PROJECTED_CURITIBA_CRS) -> float:
    if gdf is None or gdf.empty:
        return 0.0
    return _safe_to_crs(gdf, crs).geometry.length.sum() / 1000.0


def _area_km2(gdf: gpd.GeoDataFrame, crs=PROJECTED_CURITIBA_CRS) -> float:
    if gdf is None or gdf.empty:
        return 0.0
    return _safe_to_crs(gdf, crs).geometry.area.sum() / 1e6


def _plot_result(
    curitiba_gdf: gpd.GeoDataFrame,
    osm_gdf: gpd.GeoDataFrame,
    result: dict,
    output_path: Path,
) -> None:
    if plt is None:
        print("   Skipping illustration because matplotlib is not installed.")
        print(f"   Optional performance dependency missing? {PERFORMANCE_EXTRAS_HINT}")
        return

    sidewalks_gdf = result["sidewalks"]
    crossings_gdf = result["crossings"]
    kerbs_gdf = result["kerbs"]
    protoblocks_gdf = result["protoblocks"]

    try:
        plot_crs = (
            sidewalks_gdf.crs
            or protoblocks_gdf.crs
            or PROJECTED_CURITIBA_CRS
        )
        plot_curitiba = _safe_to_crs(curitiba_gdf, plot_crs)
        plot_roads = _extract_road_lines(osm_gdf, curitiba_gdf)
        if not plot_roads.empty:
            plot_roads = _safe_to_crs(plot_roads, plot_crs)
        plot_sidewalks = _safe_to_crs(sidewalks_gdf, plot_crs)
        plot_crossings = _safe_to_crs(crossings_gdf, plot_crs)
        plot_kerbs = _safe_to_crs(kerbs_gdf, plot_crs)
        plot_protoblocks = _safe_to_crs(protoblocks_gdf, plot_crs)

        fig, ax = plt.subplots(figsize=(13, 13))
        if not plot_protoblocks.empty:
            plot_protoblocks.plot(
                ax=ax,
                alpha=0.18,
                edgecolor="#81a8d8",
                facecolor="#d5eef7",
                linewidth=0.25,
                label="Protoblocks",
            )
        if not plot_roads.empty:
            plot_roads.plot(
                ax=ax,
                color="#2f2f2f",
                linewidth=0.18,
                alpha=0.35,
                label="Fetched Roads",
            )
        if not plot_sidewalks.empty:
            plot_sidewalks.plot(
                ax=ax,
                color="#008060",
                linewidth=0.28,
                alpha=0.85,
                label="Generated Sidewalks",
            )
        if not plot_crossings.empty:
            plot_crossings.plot(
                ax=ax,
                color="#d62728",
                linewidth=0.45,
                alpha=0.9,
                label="Generated Crossings",
            )
        if not plot_kerbs.empty:
            plot_kerbs.plot(
                ax=ax,
                color="#ff9900",
                markersize=0.4,
                alpha=0.75,
                label="Generated Kerbs",
            )
        plot_curitiba.boundary.plot(
            ax=ax,
            color="#b00020",
            linewidth=1.2,
            label="Municipality Boundary",
        )
        ax.set_aspect("equal")
        ax.set_title(
            "Sidewalkreator Output for Curitiba Municipality "
            f"(Sidewalks: {_count(sidewalks_gdf)}, Crossings: {_count(crossings_gdf)})"
        )
        ax.set_axis_off()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"   Illustration saved to {output_path}.")
    except Exception as e:
        print(f"   Error generating illustration: {e}")


def main():
    benchmark_start = time.time()
    print("======================================================================")
    print("Municipality-Scale Sidewalk Performance Test: Curitiba, Brazil")
    print("======================================================================")

    # 1. Geocode Curitiba
    print("1. Geocoding 'Curitiba, Brazil'...")
    start_geo = time.time()
    try:
        curitiba_gdf = ox.geocode_to_gdf("Curitiba, Brazil")
        duration_geo = time.time() - start_geo
        print(f"   Geocoding complete in {duration_geo:.2f} seconds.")
    except Exception as e:
        print(f"   Error geocoding Curitiba, Brazil: {e}")
        return

    bbox = curitiba_gdf.total_bounds
    print(f"   Bounding Box: {bbox}")

    # 2. Fetch OSM data using the same fallback strategy as the protoblock test
    providers = ["protomaps", "overture", "osmnx"]
    osm_gdf = None
    chosen_provider = None
    duration_fetch = 0.0

    print("\n2. Fetching OSM Data...")
    for provider in providers:
        print(f"   Trying provider: '{provider}'...")
        start_fetch = time.time()
        try:
            if provider == "osmnx":
                osm_gdf = get_osm_data(bbox, timeout=300, max_retries=2)
            else:
                osm_gdf = get_osm_data(bbox, provider=provider, timeout=300)

            if osm_gdf is not None and not osm_gdf.empty:
                osm_gdf = _ensure_optional_osm_columns(osm_gdf)
                duration_fetch = time.time() - start_fetch
                chosen_provider = provider
                print(
                    f"   Successfully fetched {len(osm_gdf)} features in "
                    f"{duration_fetch:.2f} seconds using '{provider}'."
                )
                break
            print(f"   Provider '{provider}' returned empty data.")
        except Exception as e:
            print(f"   Provider '{provider}' failed with error: {e}")

    if osm_gdf is None or osm_gdf.empty:
        print("   [CRITICAL] All providers failed to fetch data. Aborting.")
        return

    roads_gdf = _extract_road_lines(osm_gdf, curitiba_gdf)

    # 3. Full sidewalk generation
    print("\n3. Generating Sidewalks, Crossings, Kerbs, and Protoblocks...")
    start_generate = time.time()
    try:
        result = sidewalkreator(
            input_polygon_gdf=curitiba_gdf,
            osm_gdf=osm_gdf,
            parameters={"timeout": 300},
            ignore_existing=False,
        )
        duration_generate = time.time() - start_generate
        print(
            "   Generated "
            f"{_count(result['sidewalks'])} sidewalks, "
            f"{_count(result['crossings'])} crossings, "
            f"{_count(result['kerbs'])} kerbs, and "
            f"{_count(result['protoblocks'])} protoblocks in "
            f"{duration_generate:.2f} seconds."
        )
    except Exception as e:
        print(f"   [CRITICAL] Failed to generate sidewalk output: {e}")
        return

    sidewalks_gdf = result["sidewalks"]
    crossings_gdf = result["crossings"]
    kerbs_gdf = result["kerbs"]
    protoblocks_gdf = result["protoblocks"]
    pois_gdf = result["pois"]

    # 4. Export results
    print("\n4. Exporting results...")
    output_dir = Path("debug")
    output_dir.mkdir(exist_ok=True)
    parquet_path = output_dir / "curitiba_municipality_sidewalks.parquet"
    sidewalks_path = output_dir / "curitiba_municipality_sidewalks_wgs84.geojson"
    crossings_path = output_dir / "curitiba_municipality_crossings_wgs84.geojson"
    kerbs_path = output_dir / "curitiba_municipality_kerbs_wgs84.geojson"
    protoblocks_path = (
        output_dir / "curitiba_municipality_sidewalk_protoblocks_wgs84.geojson"
    )

    try:
        sidewalks_gdf.to_parquet(parquet_path)
        print(f"   Successfully saved sidewalks to {parquet_path}.")
    except Exception as e:
        print(f"   Error saving GeoParquet: {e}")
        print(f"   Optional performance dependency missing? {PERFORMANCE_EXTRAS_HINT}")

    for label, gdf, path in [
        ("WGS84 sidewalks", sidewalks_gdf, sidewalks_path),
        ("WGS84 crossings", crossings_gdf, crossings_path),
        ("WGS84 kerbs", kerbs_gdf, kerbs_path),
        ("WGS84 sidewalk protoblocks", protoblocks_gdf, protoblocks_path),
    ]:
        try:
            _write_wgs84(gdf, path)
            print(f"   Successfully saved {label} to {path}.")
        except Exception as e:
            print(f"   Error saving {label}: {e}")

    # 5. Correctness & Quality Metrics
    print("\n5. Computing Quality & Performance Metrics...")
    try:
        municipality_area_km2 = _area_km2(curitiba_gdf)
        sidewalk_length_km = _length_km(sidewalks_gdf)
        crossing_length_km = _length_km(crossings_gdf)
        road_length_km = _length_km(roads_gdf)
        sidewalk_density = (
            sidewalk_length_km / municipality_area_km2
            if municipality_area_km2 > 0
            else 0.0
        )
        avg_sidewalk_length_m = (
            (sidewalk_length_km * 1000.0) / len(sidewalks_gdf)
            if not sidewalks_gdf.empty
            else 0.0
        )

        print(f"   Municipality Area: {municipality_area_km2:.2f} km2")
        print(f"   Raw OSM Features: {len(osm_gdf)}")
        print(f"   Road Line Features: {len(roads_gdf)}")
        print(f"   Road Length: {road_length_km:.2f} km")
        print(f"   Sidewalk Segments: {len(sidewalks_gdf)}")
        print(f"   Total Sidewalk Length: {sidewalk_length_km:.2f} km")
        print(f"   Average Sidewalk Segment Length: {avg_sidewalk_length_m:.2f} m")
        print(f"   Sidewalk Density: {sidewalk_density:.2f} km/km2")
        print(f"   Crossings: {len(crossings_gdf)}")
        print(f"   Total Crossing Length: {crossing_length_km:.2f} km")
        print(f"   Kerbs: {len(kerbs_gdf)}")
        print(f"   Protoblocks: {len(protoblocks_gdf)}")
        print(f"   POIs: {len(pois_gdf)}")
    except Exception as e:
        print(f"   Error calculating metrics: {e}")
        municipality_area_km2 = 0.0
        sidewalk_length_km = 0.0
        crossing_length_km = 0.0
        road_length_km = 0.0
        sidewalk_density = 0.0
        avg_sidewalk_length_m = 0.0

    # 6. Plotting
    print("\n6. Plotting and saving illustration...")
    img_path = output_dir / "curitiba_municipality_sidewalk_illustration.png"
    _plot_result(curitiba_gdf, osm_gdf, result, img_path)

    # 7. Generate report
    print("\n7. Generating performance report...")
    report_path = output_dir / "curitiba_performance_sidewalk_report.md"
    processing_time = duration_geo + duration_fetch + duration_generate
    wall_time = time.time() - benchmark_start

    report_content = f"""# Curitiba Municipality-Scale Sidewalk Performance Report

## 1. Executive Summary
This report evaluates the performance of the full `sidewalkreator()` pipeline at city/municipality scale. The test was conducted across the entire municipality area of Curitiba, Brazil.

- **Municipality Area**: {municipality_area_km2:.2f} km²
- **Data Provider**: {chosen_provider}
- **Raw OSM Features**: {len(osm_gdf)}
- **Road Line Features**: {len(roads_gdf)}
- **Generated Sidewalk Segments**: {len(sidewalks_gdf)}
- **Generated Crossings**: {len(crossings_gdf)}
- **Generated Kerbs**: {len(kerbs_gdf)}
- **Generated Protoblocks**: {len(protoblocks_gdf)}
- **POIs Used for Splitting**: {len(pois_gdf)}
- **Total Sidewalk Length**: {sidewalk_length_km:.2f} km
- **Total Crossing Length**: {crossing_length_km:.2f} km
- **Sidewalk Density**: {sidewalk_density:.2f} km/km²
- **Total Processing Time**: {processing_time:.2f} seconds
- **Total Benchmark Wall Time**: {wall_time:.2f} seconds

## 2. Performance Metrics
| Stage | Provider / Operation | Duration (seconds) |
|---|---|---:|
| Geocoding | OSMnx / Nominatim | {duration_geo:.2f} |
| Data Fetching | {chosen_provider} | {duration_fetch:.2f} |
| Full Sidewalk Generation | `sidewalkreator` | {duration_generate:.2f} |
| **Processing Total** | | **{processing_time:.2f}** |
| **Benchmark Wall Time** | includes export, metrics, plot, report | **{wall_time:.2f}** |

## 3. Output Metrics
| Metric | Value |
|---|---:|
| Municipality area | {municipality_area_km2:.2f} km² |
| Road length | {road_length_km:.2f} km |
| Sidewalk length | {sidewalk_length_km:.2f} km |
| Crossing length | {crossing_length_km:.2f} km |
| Average sidewalk segment length | {avg_sidewalk_length_m:.2f} m |
| Sidewalk density | {sidewalk_density:.2f} km/km² |
| Road line features | {len(roads_gdf)} |
| Sidewalk segments | {len(sidewalks_gdf)} |
| Crossings | {len(crossings_gdf)} |
| Kerbs | {len(kerbs_gdf)} |
| Protoblocks | {len(protoblocks_gdf)} |
| POIs | {len(pois_gdf)} |

## 4. Visual Result
![Curitiba Municipality Sidewalk Illustration](curitiba_municipality_sidewalk_illustration.png)

## 5. Generated Artifacts
- `{parquet_path}`
- `{sidewalks_path}`
- `{crossings_path}`
- `{kerbs_path}`
- `{protoblocks_path}`
- `{img_path}`
"""
    try:
        with report_path.open("w") as f:
            f.write(report_content)
        print(f"   Performance report saved to {report_path}.")
    except Exception as e:
        print(f"   Error saving performance report: {e}")

    print("\n======================================================================")
    print("SIDEWALK PERFORMANCE TEST COMPLETE")
    print("======================================================================")
    print(f"Total benchmark wall time: {wall_time:.2f} seconds.")


if __name__ == "__main__":
    main()
