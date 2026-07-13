import geopandas as gpd
import pytest
from shapely.geometry import LineString, box

import debug.test_curitiba_1km_sidewalk_alignment as diagnostic


def _empty_gdf():
    return gpd.GeoDataFrame(geometry=[], crs=diagnostic.PROJECTED_CRS)


def test_topology_gap_segments_exports_only_substantial_unpolygonized_roads():
    origin_x = 674000.0
    origin_y = 7186000.0
    block = box(origin_x, origin_y, origin_x + 10, origin_y + 10)
    roads = gpd.GeoDataFrame(
        geometry=[
            LineString([(origin_x, origin_y), (origin_x + 10, origin_y)]),
            LineString([(origin_x + 5, origin_y), (origin_x + 5, origin_y + 10)]),
            LineString([(origin_x + 8, origin_y + 1), (origin_x + 8, origin_y + 2)]),
        ],
        crs=diagnostic.PROJECTED_CRS,
    )
    protoblocks = gpd.GeoDataFrame(
        geometry=[block],
        crs=diagnostic.PROJECTED_CRS,
    )

    gaps = diagnostic._topology_gap_segments(roads, protoblocks)

    assert len(gaps) == 1
    assert gaps.iloc[0]["gap_length_m"] == pytest.approx(9.0)


def test_sidewalk_metrics_include_fetch_and_topology_diagnostics():
    origin_x = 674000.0
    origin_y = 7186000.0
    block = box(origin_x, origin_y, origin_x + 10, origin_y + 10)
    roads = gpd.GeoDataFrame(
        geometry=[
            LineString([(origin_x, origin_y), (origin_x + 10, origin_y)]),
            LineString([(origin_x + 5, origin_y), (origin_x + 5, origin_y + 10)]),
        ],
        crs=diagnostic.PROJECTED_CRS,
    )
    raw = roads.copy()
    raw.attrs.update({"zoom": 15, "tile_count": 4, "tile_workers": 4})
    protoblocks = gpd.GeoDataFrame(
        geometry=[block],
        crs=diagnostic.PROJECTED_CRS,
    )
    result_payload = {
        "sidewalks": _empty_gdf(),
        "crossings": _empty_gdf(),
        "kerbs": _empty_gdf(),
        "protoblocks": protoblocks,
        "pois": _empty_gdf(),
        "parameters": {
            "protomaps_topology_stats": {
                "undershoots_repaired": 3,
                "overshoots_removed": 2,
                "remaining_eligible_endpoints": 0,
                "duration_s": 0.12,
            }
        },
    }
    analysis = diagnostic.ProviderSidewalkAnalysis(
        box_id=1,
        provider="protomaps",
        raw=raw,
        roads=roads,
        result=result_payload,
        raw_count=2,
        road_count=2,
        sidewalk_count=0,
        crossing_count=0,
        kerb_count=0,
        protoblock_count=1,
        poi_count=0,
        duration_fetch=1.25,
        duration_generate=3.5,
    )
    input_box = gpd.GeoDataFrame(
        geometry=[block],
        crs=diagnostic.PROJECTED_CRS,
    )

    metrics = diagnostic._metrics_row(analysis, input_box)

    assert metrics["selected_zoom"] == 15
    assert metrics["tile_count"] == 4
    assert metrics["tile_workers"] == 4
    assert metrics["topology_undershoots_repaired"] == 3
    assert metrics["topology_overshoots_removed"] == 2
    assert metrics["topology_remaining_eligible_endpoints"] == 0
    assert metrics["duration_topology_normalization_s"] == pytest.approx(0.12)
    assert metrics["topology_generation_pct"] == pytest.approx(12 / 3.5)
    assert metrics["unpolygonized_road_length_km"] == pytest.approx(0.009)
    assert metrics["road_boundary_coverage_pct"] == pytest.approx(55.0)
    assert metrics["duration_total_s"] == pytest.approx(4.75)
