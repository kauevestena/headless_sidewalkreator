import json
import math
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import geopandas as gpd
import osmnx as ox
import pandas as pd
from shapely.geometry import MultiPolygon, Point, Polygon, box

from headless_sidewalkreator import sidewalkreator
from headless_sidewalkreator.generic_functions import clip_gdf
from headless_sidewalkreator.osm_fetch import get_osm_data

try:
    import matplotlib.pyplot as plt
except ModuleNotFoundError:
    plt = None


CENTER_LON_LAT = (-49.2733, -25.4284)
PROJECTED_CRS = "EPSG:32722"
WGS84_CRS = "EPSG:4326"
BOX_SIZE_M = 1000.0
URBAN_CORE_RADIUS_M = 5000.0
TARGET_BOX_COUNT = 1
MIN_ROAD_FEATURES = 5
MAX_RANDOM_ATTEMPTS = 250
PROVIDERS = ("protomaps", "osmnx")
OPTIONAL_OSM_COLUMNS = (
    "highway",
    "building",
    "amenity",
    "shop",
    "addr:housenumber",
    "footway",
    "sidewalk",
)


@dataclass
class ProviderSidewalkAnalysis:
    box_id: int
    provider: str
    raw: gpd.GeoDataFrame
    roads: gpd.GeoDataFrame
    result: Optional[dict]
    raw_count: int
    road_count: int
    sidewalk_count: int
    crossing_count: int
    kerb_count: int
    protoblock_count: int
    poi_count: int
    duration_fetch: float
    duration_generate: float
    error: Optional[str] = None


def _empty_gdf(crs=WGS84_CRS) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(geometry=[], crs=crs)


def _geometry_union(geometries):
    if hasattr(geometries, "union_all"):
        return geometries.union_all()
    return geometries.unary_union


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


def _ensure_optional_osm_columns(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    normalized = gdf.copy()
    for column in OPTIONAL_OSM_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = None
    return normalized


def _result_gdf(result: Optional[dict], key: str, crs=PROJECTED_CRS) -> gpd.GeoDataFrame:
    if result is None:
        return _empty_gdf(crs)
    gdf = result.get(key)
    if gdf is None:
        return _empty_gdf(crs)
    return gdf


def _make_square_box(center_x: float, center_y: float, size_m: float = BOX_SIZE_M):
    half = size_m / 2.0
    return box(center_x - half, center_y - half, center_x + half, center_y + half)


def _center_point_projected(
    center_lon_lat: Tuple[float, float] = CENTER_LON_LAT,
    projected_crs=PROJECTED_CRS,
) -> Point:
    lon, lat = center_lon_lat
    center_gdf = gpd.GeoDataFrame(geometry=[Point(lon, lat)], crs=WGS84_CRS)
    return center_gdf.to_crs(projected_crs).geometry.iloc[0]


def _urban_core_geometry(
    municipality_gdf: gpd.GeoDataFrame,
    center_lon_lat: Tuple[float, float] = CENTER_LON_LAT,
    projected_crs=PROJECTED_CRS,
    radius_m: float = URBAN_CORE_RADIUS_M,
):
    municipality_projected = _safe_to_crs(municipality_gdf, projected_crs)
    municipality_union = _geometry_union(municipality_projected.geometry)
    center = _center_point_projected(center_lon_lat, projected_crs)
    return municipality_union.intersection(center.buffer(radius_m))


def _sample_random_boxes_in_projected_area(
    area_geom,
    count: int,
    rng,
    size_m: float = BOX_SIZE_M,
    max_attempts: int = 5000,
) -> List:
    minx, miny, maxx, maxy = area_geom.bounds
    boxes = []
    attempts = 0
    while len(boxes) < count and attempts < max_attempts:
        attempts += 1
        center_x = rng.uniform(minx, maxx)
        center_y = rng.uniform(miny, maxy)
        candidate = _make_square_box(center_x, center_y, size_m)
        if area_geom.covers(candidate):
            boxes.append(candidate)

    if len(boxes) < count:
        raise RuntimeError(
            f"Only sampled {len(boxes)} valid boxes after {max_attempts} attempts."
        )
    return boxes


def _box_gdf(box_id: int, geometry, crs) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"box_id": [box_id]}, geometry=[geometry], crs=crs)


def _extract_road_lines(
    raw_gdf: gpd.GeoDataFrame,
    clip_geom: Optional[gpd.GeoDataFrame] = None,
) -> gpd.GeoDataFrame:
    if raw_gdf is None or raw_gdf.empty or "geometry" not in raw_gdf.columns:
        crs = clip_geom.crs if clip_geom is not None else WGS84_CRS
        return _empty_gdf(crs)

    roads_gdf = raw_gdf.copy()
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

    if clip_geom is not None and not clip_geom.empty:
        try:
            roads_gdf = clip_gdf(roads_gdf, clip_geom)
        except Exception:
            pass

    return roads_gdf[roads_gdf.geometry.notna() & ~roads_gdf.geometry.is_empty].copy()


def _fetch_raw_for_box(
    box_wgs84: gpd.GeoDataFrame,
    provider: str,
    timeout: int,
) -> gpd.GeoDataFrame:
    bbox = tuple(box_wgs84.total_bounds)
    if provider == "osmnx":
        raw_gdf = get_osm_data(bbox, timeout=timeout, max_retries=2)
    else:
        raw_gdf = get_osm_data(bbox, provider=provider, timeout=timeout)
    if raw_gdf is None:
        return _empty_gdf(WGS84_CRS)
    if raw_gdf.crs is None:
        raw_gdf = raw_gdf.set_crs(WGS84_CRS)
    return _ensure_optional_osm_columns(raw_gdf)


def _count_result(result: Optional[dict], key: str) -> int:
    gdf = _result_gdf(result, key)
    return 0 if gdf is None or gdf.empty else len(gdf)


def _analyze_provider_for_box(
    box_id: int,
    box_wgs84: gpd.GeoDataFrame,
    provider: str,
    timeout: int = 300,
    min_road_features: int = MIN_ROAD_FEATURES,
    show_progress: bool = True,
) -> ProviderSidewalkAnalysis:
    fetch_start = time.time()
    try:
        raw_gdf = _fetch_raw_for_box(box_wgs84, provider, timeout)
        roads_gdf = _extract_road_lines(raw_gdf, box_wgs84)
    except Exception as exc:
        return ProviderSidewalkAnalysis(
            box_id,
            provider,
            _empty_gdf(WGS84_CRS),
            _empty_gdf(WGS84_CRS),
            None,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            time.time() - fetch_start,
            0.0,
            error=f"fetch failed: {exc}",
        )

    duration_fetch = time.time() - fetch_start
    if len(roads_gdf) < min_road_features:
        return ProviderSidewalkAnalysis(
            box_id,
            provider,
            raw_gdf,
            roads_gdf,
            None,
            len(raw_gdf),
            len(roads_gdf),
            0,
            0,
            0,
            0,
            0,
            duration_fetch,
            0.0,
            error=f"only {len(roads_gdf)} road features",
        )

    generate_start = time.time()
    try:
        result = sidewalkreator(
            input_polygon_gdf=box_wgs84,
            osm_gdf=raw_gdf,
            parameters={"timeout": timeout, "show_progress": show_progress},
            ignore_existing=False,
        )
        error = None
    except Exception as exc:
        result = None
        error = f"generation failed: {exc}"

    duration_generate = time.time() - generate_start
    if result is not None and _count_result(result, "sidewalks") == 0 and error is None:
        error = "generated no sidewalks"

    return ProviderSidewalkAnalysis(
        box_id,
        provider,
        raw_gdf,
        roads_gdf,
        result,
        len(raw_gdf),
        len(roads_gdf),
        _count_result(result, "sidewalks"),
        _count_result(result, "crossings"),
        _count_result(result, "kerbs"),
        _count_result(result, "protoblocks"),
        _count_result(result, "pois"),
        duration_fetch,
        duration_generate,
        error=error,
    )


def _length_km(gdf: gpd.GeoDataFrame, crs=PROJECTED_CRS) -> float:
    if gdf is None or gdf.empty:
        return 0.0
    return _safe_to_crs(gdf, crs).geometry.length.sum() / 1000.0


def _area_km2(gdf: gpd.GeoDataFrame, crs=PROJECTED_CRS) -> float:
    if gdf is None or gdf.empty:
        return 0.0
    return _safe_to_crs(gdf, crs).geometry.area.sum() / 1e6


def _metrics_row(result: ProviderSidewalkAnalysis, box_wgs84: gpd.GeoDataFrame):
    sidewalks = _result_gdf(result.result, "sidewalks")
    crossings = _result_gdf(result.result, "crossings")
    protoblocks = _result_gdf(result.result, "protoblocks")
    box_area_km2 = _area_km2(box_wgs84)
    sidewalk_length_km = _length_km(sidewalks)
    return {
        "box_id": result.box_id,
        "provider": result.provider,
        "raw_feature_count": result.raw_count,
        "road_count": result.road_count,
        "road_length_km": _length_km(result.roads),
        "sidewalk_count": result.sidewalk_count,
        "sidewalk_length_km": sidewalk_length_km,
        "sidewalk_density_km_per_km2": (
            sidewalk_length_km / box_area_km2 if box_area_km2 else math.nan
        ),
        "crossing_count": result.crossing_count,
        "crossing_length_km": _length_km(crossings),
        "kerb_count": result.kerb_count,
        "protoblock_count": result.protoblock_count,
        "protoblock_area_km2": _area_km2(protoblocks),
        "poi_count": result.poi_count,
        "duration_fetch_s": result.duration_fetch,
        "duration_generate_s": result.duration_generate,
        "duration_total_s": result.duration_fetch + result.duration_generate,
        "error": result.error,
    }


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


def _concat_gdfs(gdfs: Sequence[gpd.GeoDataFrame], crs=WGS84_CRS) -> gpd.GeoDataFrame:
    frames = [gdf for gdf in gdfs if gdf is not None and not gdf.empty]
    if not frames:
        return _empty_gdf(crs)
    frames = [_safe_to_crs(frame, crs) for frame in frames]
    return gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True),
        geometry="geometry",
        crs=crs,
    )


def _tag_layer(gdf: gpd.GeoDataFrame, box_id: int, provider: str) -> gpd.GeoDataFrame:
    tagged = gdf.copy()
    tagged["box_id"] = box_id
    tagged["provider"] = provider
    return tagged


def _plot_sidewalk_alignment(
    boxes_wgs84: Sequence[gpd.GeoDataFrame],
    provider_results_by_box: Sequence[Dict[str, ProviderSidewalkAnalysis]],
    providers: Sequence[str],
    output_path: Path,
) -> None:
    if plt is None:
        print("   Skipping sidewalk plot because matplotlib is not installed.")
        return

    row_count = len(provider_results_by_box)
    col_count = len(providers)
    fig, axes = plt.subplots(
        row_count,
        col_count,
        figsize=(5.5 * col_count, 4.2 * row_count),
        squeeze=False,
    )

    for row_idx, (box_wgs84, result_by_provider) in enumerate(
        zip(boxes_wgs84, provider_results_by_box)
    ):
        for col_idx, provider in enumerate(providers):
            ax = axes[row_idx][col_idx]
            result = result_by_provider[provider]
            box_wgs84.boundary.plot(ax=ax, color="black", linewidth=1.0)
            roads = _safe_to_crs(result.roads, WGS84_CRS)
            protoblocks = _safe_to_crs(_result_gdf(result.result, "protoblocks"), WGS84_CRS)
            sidewalks = _safe_to_crs(_result_gdf(result.result, "sidewalks"), WGS84_CRS)
            crossings = _safe_to_crs(_result_gdf(result.result, "crossings"), WGS84_CRS)
            kerbs = _safe_to_crs(_result_gdf(result.result, "kerbs"), WGS84_CRS)

            if not protoblocks.empty:
                protoblocks.plot(
                    ax=ax,
                    facecolor="#d5eef7",
                    edgecolor="#74a9cf",
                    alpha=0.35,
                    linewidth=0.35,
                )
            if not roads.empty:
                roads.plot(ax=ax, color="#333333", linewidth=0.55, alpha=0.5)
            if not sidewalks.empty:
                sidewalks.plot(ax=ax, color="#008060", linewidth=0.8, alpha=0.9)
            if not crossings.empty:
                crossings.plot(ax=ax, color="#d62728", linewidth=1.0, alpha=0.9)
            if not kerbs.empty:
                kerbs.plot(ax=ax, color="#ff9900", markersize=4, alpha=0.9)

            title = (
                f"Box {row_idx + 1} - {provider}\n"
                f"sidewalks={result.sidewalk_count}, crossings={result.crossing_count}, "
                f"gen={result.duration_generate:.2f}s"
            )
            if result.error:
                title += f"\n{result.error}"
            ax.set_title(title, fontsize=9)
            ax.set_axis_off()

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=160)
    plt.close()


def run_sidewalk_diagnostic(
    municipality_gdf: gpd.GeoDataFrame,
    output_dir: str = "debug",
    target_count: int = TARGET_BOX_COUNT,
    providers: Sequence[str] = PROVIDERS,
    timeout: int = 300,
    min_road_features: int = MIN_ROAD_FEATURES,
    rng=None,
    show_progress: bool = True,
) -> pd.DataFrame:
    rng = rng or random.Random()
    output_path = Path(output_dir)
    core_geom = _urban_core_geometry(municipality_gdf)

    boxes_wgs84 = []
    provider_results_by_box = []
    metrics_rows = []
    attempts = 0

    while len(boxes_wgs84) < target_count and attempts < MAX_RANDOM_ATTEMPTS:
        attempts += 1
        candidate = _sample_random_boxes_in_projected_area(core_geom, 1, rng)[0]
        box_id = len(boxes_wgs84) + 1
        candidate_projected = _box_gdf(box_id, candidate, PROJECTED_CRS)
        candidate_wgs84 = candidate_projected.to_crs(WGS84_CRS)

        print(f"   Candidate {attempts}: testing sidewalk box {box_id}...")
        result_by_provider = {}
        valid = True
        for provider in providers:
            print(f"      Provider: {provider}")
            result = _analyze_provider_for_box(
                box_id,
                candidate_wgs84,
                provider,
                timeout=timeout,
                min_road_features=min_road_features,
                show_progress=show_progress,
            )
            result_by_provider[provider] = result
            print(
                f"         fetch={result.duration_fetch:.2f}s, "
                f"generate={result.duration_generate:.2f}s, "
                f"sidewalks={result.sidewalk_count}, "
                f"crossings={result.crossing_count}, "
                f"kerbs={result.kerb_count}"
            )
            if result.error:
                print(f"      Rejecting candidate for {provider}: {result.error}")
                valid = False
                break

        if not valid:
            continue

        boxes_wgs84.append(candidate_wgs84)
        provider_results_by_box.append(result_by_provider)
        print(f"      Accepted as random 1km sidewalk box {box_id}.")

        for result in result_by_provider.values():
            metrics_rows.append(_metrics_row(result, candidate_wgs84))

    if len(boxes_wgs84) < target_count:
        raise RuntimeError(
            f"Only found {len(boxes_wgs84)} valid boxes after {attempts} attempts."
        )

    boxes_gdf = _concat_gdfs(boxes_wgs84, WGS84_CRS)
    _write_wgs84(boxes_gdf, output_path / "curitiba_1km_sidewalk_random_boxes.geojson")

    for provider in providers:
        provider_results = [
            result_by_provider[provider]
            for result_by_provider in provider_results_by_box
        ]
        layers = {
            "roads": [result.roads for result in provider_results],
            "sidewalks": [
                _result_gdf(result.result, "sidewalks") for result in provider_results
            ],
            "crossings": [
                _result_gdf(result.result, "crossings") for result in provider_results
            ],
            "kerbs": [
                _result_gdf(result.result, "kerbs") for result in provider_results
            ],
            "protoblocks": [
                _result_gdf(result.result, "protoblocks") for result in provider_results
            ],
        }

        for layer_name, gdfs in layers.items():
            tagged_layers = [
                _tag_layer(gdf, provider_results[idx].box_id, provider)
                for idx, gdf in enumerate(gdfs)
            ]
            merged = _concat_gdfs(tagged_layers, WGS84_CRS)
            _write_wgs84(
                merged,
                output_path / f"curitiba_1km_{provider}_sidewalk_{layer_name}.geojson",
            )

    metrics_df = pd.DataFrame(metrics_rows)
    metrics_df.to_csv(output_path / "curitiba_1km_sidewalk_metrics.csv", index=False)
    _plot_sidewalk_alignment(
        boxes_wgs84,
        provider_results_by_box,
        providers,
        output_path / "curitiba_1km_sidewalk_alignment.png",
    )
    return metrics_df


def main():
    print("======================================================================")
    print("Curitiba 1km Random Sidewalk Diagnostic")
    print("======================================================================")
    print("1. Geocoding 'Curitiba, Brazil'...")
    curitiba_gdf = ox.geocode_to_gdf("Curitiba, Brazil")

    print("\n2. Sampling and evaluating a fresh random urban-core 1km box...")
    start = time.time()
    metrics_df = run_sidewalk_diagnostic(curitiba_gdf)
    duration = time.time() - start

    print("\n3. Sidewalk metrics summary:")
    print(metrics_df)
    print(f"\nCompleted in {duration:.2f} seconds.")
    print("Outputs:")
    print("  debug/curitiba_1km_sidewalk_random_boxes.geojson")
    print("  debug/curitiba_1km_sidewalk_metrics.csv")
    print("  debug/curitiba_1km_sidewalk_alignment.png")
    print("  debug/curitiba_1km_{provider}_sidewalk_{layer}.geojson")
    print("======================================================================")


if __name__ == "__main__":
    main()
