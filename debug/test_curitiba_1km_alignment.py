import json
import math
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import geopandas as gpd
import osmnx as ox
import pandas as pd
from shapely.geometry import MultiPolygon, Point, Polygon, box

from headless_sidewalkreator import generate_protoblocks
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


@dataclass
class ProviderAnalysis:
    box_id: int
    provider: str
    roads: gpd.GeoDataFrame
    protoblocks: gpd.GeoDataFrame
    road_count: int
    protoblock_count: int
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
    if gdf.crs is None:
        gdf = gdf.set_crs(WGS84_CRS)
    if str(gdf.crs) == str(crs):
        return gdf.copy()
    return gdf.to_crs(crs)


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


def _fetch_roads_for_box(
    box_wgs84: gpd.GeoDataFrame,
    provider: str,
    timeout: int,
) -> gpd.GeoDataFrame:
    bbox = tuple(box_wgs84.total_bounds)
    if provider == "osmnx":
        raw_gdf = get_osm_data(bbox, timeout=timeout, max_retries=2)
    else:
        raw_gdf = get_osm_data(bbox, provider=provider, timeout=timeout)
    return _extract_road_lines(raw_gdf, box_wgs84)


def _analyze_provider_for_box(
    box_id: int,
    box_wgs84: gpd.GeoDataFrame,
    provider: str,
    timeout: int = 300,
    min_road_features: int = MIN_ROAD_FEATURES,
) -> ProviderAnalysis:
    fetch_start = time.time()
    try:
        roads_gdf = _fetch_roads_for_box(box_wgs84, provider, timeout)
    except Exception as exc:
        return ProviderAnalysis(
            box_id,
            provider,
            _empty_gdf(WGS84_CRS),
            _empty_gdf(PROJECTED_CRS),
            0,
            0,
            time.time() - fetch_start,
            0.0,
            error=f"fetch failed: {exc}",
        )

    duration_fetch = time.time() - fetch_start
    if len(roads_gdf) < min_road_features:
        return ProviderAnalysis(
            box_id,
            provider,
            roads_gdf,
            _empty_gdf(PROJECTED_CRS),
            len(roads_gdf),
            0,
            duration_fetch,
            0.0,
            error=f"only {len(roads_gdf)} road features",
        )

    generate_start = time.time()
    try:
        protoblocks_gdf = generate_protoblocks(
            input_polygon_gdf=box_wgs84,
            osm_gdf=roads_gdf,
            parameters={"timeout": timeout},
        )
        error = None
    except Exception as exc:
        protoblocks_gdf = _empty_gdf(PROJECTED_CRS)
        error = f"generation failed: {exc}"

    duration_generate = time.time() - generate_start
    if protoblocks_gdf.empty and error is None:
        error = "generated no protoblocks"

    return ProviderAnalysis(
        box_id,
        provider,
        roads_gdf,
        protoblocks_gdf,
        len(roads_gdf),
        len(protoblocks_gdf),
        duration_fetch,
        duration_generate,
        error=error,
    )


def _iter_polygon_boundary_coords(geom) -> Iterable[Tuple[float, float]]:
    if geom is None or geom.is_empty:
        return
    if isinstance(geom, Polygon):
        yield from geom.exterior.coords
        for interior in geom.interiors:
            yield from interior.coords
    elif isinstance(geom, MultiPolygon):
        for poly in geom.geoms:
            yield from _iter_polygon_boundary_coords(poly)
    elif geom.geom_type == "GeometryCollection":
        for part in geom.geoms:
            yield from _iter_polygon_boundary_coords(part)


def _percentile(values: Sequence[float], percent: float) -> float:
    if not values:
        return math.nan
    sorted_values = sorted(values)
    position = (len(sorted_values) - 1) * percent / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[int(position)]
    lower_value = sorted_values[lower]
    upper_value = sorted_values[upper]
    return lower_value * (upper - position) + upper_value * (position - lower)


def _alignment_metrics(
    protoblocks_gdf: gpd.GeoDataFrame,
    roads_gdf: gpd.GeoDataFrame,
    box_wgs84: gpd.GeoDataFrame,
    road_provider: str,
    protoblock_provider: str,
    boundary_exclusion_m: float = 2.0,
    projected_crs=PROJECTED_CRS,
) -> Dict[str, float]:
    box_id = int(box_wgs84["box_id"].iloc[0]) if "box_id" in box_wgs84 else -1
    base = {
        "box_id": box_id,
        "protoblock_provider": protoblock_provider,
        "road_provider": road_provider,
        "protoblock_count": 0 if protoblocks_gdf is None else len(protoblocks_gdf),
        "road_count": 0 if roads_gdf is None else len(roads_gdf),
        "sample_count": 0,
        "mean_distance_m": math.nan,
        "p95_distance_m": math.nan,
        "max_distance_m": math.nan,
    }
    if (
        protoblocks_gdf is None
        or roads_gdf is None
        or protoblocks_gdf.empty
        or roads_gdf.empty
    ):
        return base

    protoblocks_projected = _safe_to_crs(protoblocks_gdf, projected_crs)
    roads_projected = _safe_to_crs(roads_gdf, projected_crs)
    box_projected = _safe_to_crs(box_wgs84, projected_crs)
    box_boundary = box_projected.geometry.iloc[0].boundary
    roads_union = _geometry_union(roads_projected.geometry)

    distances = []
    for geom in protoblocks_projected.geometry:
        for coord in _iter_polygon_boundary_coords(geom):
            point = Point(coord)
            if point.distance(box_boundary) <= boundary_exclusion_m:
                continue
            distances.append(point.distance(roads_union))

    if not distances:
        return base

    base.update(
        {
            "sample_count": len(distances),
            "mean_distance_m": sum(distances) / len(distances),
            "p95_distance_m": _percentile(distances, 95),
            "max_distance_m": max(distances),
        }
    )
    return base


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


def _plot_alignment(
    boxes_wgs84: Sequence[gpd.GeoDataFrame],
    provider_results_by_box: Sequence[Dict[str, ProviderAnalysis]],
    providers: Sequence[str],
    output_path: Path,
) -> None:
    if plt is None:
        print("   Skipping alignment plot because matplotlib is not installed.")
        return

    row_count = len(provider_results_by_box)
    col_count = len(providers)
    fig, axes = plt.subplots(
        row_count,
        col_count,
        figsize=(5 * col_count, 3.8 * row_count),
        squeeze=False,
    )

    for row_idx, (box_wgs84, result_by_provider) in enumerate(
        zip(boxes_wgs84, provider_results_by_box)
    ):
        for col_idx, provider in enumerate(providers):
            ax = axes[row_idx][col_idx]
            result = result_by_provider[provider]
            box_wgs84.boundary.plot(ax=ax, color="black", linewidth=1.0)
            if not result.protoblocks.empty:
                _safe_to_crs(result.protoblocks, WGS84_CRS).plot(
                    ax=ax,
                    facecolor="cyan",
                    edgecolor="blue",
                    alpha=0.35,
                    linewidth=0.4,
                )
            if not result.roads.empty:
                _safe_to_crs(result.roads, WGS84_CRS).plot(
                    ax=ax,
                    color="red",
                    linewidth=0.55,
                    alpha=0.8,
                )
            title = f"Box {row_idx + 1} - {provider}"
            if result.error:
                title += f" ({result.error})"
            ax.set_title(title, fontsize=9)
            ax.set_axis_off()

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=160)
    plt.close()


def run_alignment_diagnostic(
    municipality_gdf: gpd.GeoDataFrame,
    output_dir: str = "debug",
    target_count: int = TARGET_BOX_COUNT,
    providers: Sequence[str] = PROVIDERS,
    timeout: int = 300,
    min_road_features: int = MIN_ROAD_FEATURES,
    rng=None,
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

        print(f"   Candidate {attempts}: testing box {box_id}...")
        result_by_provider = {}
        valid = True
        for provider in providers:
            result = _analyze_provider_for_box(
                box_id,
                candidate_wgs84,
                provider,
                timeout=timeout,
                min_road_features=min_road_features,
            )
            result_by_provider[provider] = result
            if result.error:
                print(f"      Rejecting candidate for {provider}: {result.error}")
                valid = False
                break

        if not valid:
            continue

        boxes_wgs84.append(candidate_wgs84)
        provider_results_by_box.append(result_by_provider)
        print(f"      Accepted as random 1km box {box_id}.")

        for provider, result in result_by_provider.items():
            metrics_rows.append(
                _alignment_metrics(
                    result.protoblocks,
                    result.roads,
                    candidate_wgs84,
                    road_provider=provider,
                    protoblock_provider=provider,
                )
            )

        if "protomaps" in result_by_provider and "osmnx" in result_by_provider:
            metrics_rows.append(
                _alignment_metrics(
                    result_by_provider["protomaps"].protoblocks,
                    result_by_provider["osmnx"].roads,
                    candidate_wgs84,
                    road_provider="osmnx",
                    protoblock_provider="protomaps",
                )
            )

    if len(boxes_wgs84) < target_count:
        raise RuntimeError(
            f"Only found {len(boxes_wgs84)} valid boxes after {attempts} attempts."
        )

    boxes_gdf = _concat_gdfs(boxes_wgs84, WGS84_CRS)
    _write_wgs84(boxes_gdf, output_path / "curitiba_1km_random_boxes.geojson")

    for provider in providers:
        roads = _concat_gdfs(
            [
                _tag_layer(result_by_provider[provider].roads, box_id + 1, provider)
                for box_id, result_by_provider in enumerate(provider_results_by_box)
            ],
            WGS84_CRS,
        )
        protoblocks = _concat_gdfs(
            [
                _tag_layer(
                    result_by_provider[provider].protoblocks,
                    box_id + 1,
                    provider,
                )
                for box_id, result_by_provider in enumerate(provider_results_by_box)
            ],
            WGS84_CRS,
        )
        _write_wgs84(roads, output_path / f"curitiba_1km_{provider}_roads.geojson")
        _write_wgs84(
            protoblocks,
            output_path / f"curitiba_1km_{provider}_protoblocks.geojson",
        )

    all_roads = _concat_gdfs(
        [
            _tag_layer(result.roads, result.box_id, result.provider)
            for result_by_provider in provider_results_by_box
            for result in result_by_provider.values()
        ],
        WGS84_CRS,
    )
    all_protoblocks = _concat_gdfs(
        [
            _tag_layer(result.protoblocks, result.box_id, result.provider)
            for result_by_provider in provider_results_by_box
            for result in result_by_provider.values()
        ],
        WGS84_CRS,
    )
    _write_wgs84(all_roads, output_path / "curitiba_1km_all_roads.geojson")
    _write_wgs84(
        all_protoblocks,
        output_path / "curitiba_1km_all_protoblocks.geojson",
    )

    metrics_df = pd.DataFrame(metrics_rows)
    metrics_df.to_csv(output_path / "curitiba_1km_alignment_metrics.csv", index=False)
    _plot_alignment(
        boxes_wgs84,
        provider_results_by_box,
        providers,
        output_path / "curitiba_1km_alignment.png",
    )
    return metrics_df


def main():
    print("======================================================================")
    print("Curitiba 1km Random Alignment Diagnostic")
    print("======================================================================")
    print("1. Geocoding 'Curitiba, Brazil'...")
    curitiba_gdf = ox.geocode_to_gdf("Curitiba, Brazil")

    print("\n2. Sampling and evaluating 10 fresh random urban-core boxes...")
    start = time.time()
    metrics_df = run_alignment_diagnostic(curitiba_gdf)
    duration = time.time() - start

    print("\n3. Alignment metrics summary:")
    print(metrics_df)
    print(f"\nCompleted in {duration:.2f} seconds.")
    print("Outputs:")
    print("  debug/curitiba_1km_random_boxes.geojson")
    print("  debug/curitiba_1km_alignment_metrics.csv")
    print("  debug/curitiba_1km_alignment.png")
    print("======================================================================")


if __name__ == "__main__":
    main()
