import random

import geopandas as gpd
import pytest
from shapely.geometry import LineString, box

import debug.test_curitiba_1km_alignment as diagnostic


def _grid_roads_for_bbox(bbox, crs="EPSG:4326"):
    minx, miny, maxx, maxy = bbox
    midx = (minx + maxx) / 2.0
    midy = (miny + maxy) / 2.0
    lines = [
        LineString([(minx, miny), (maxx, miny)]),
        LineString([(minx, maxy), (maxx, maxy)]),
        LineString([(minx, miny), (minx, maxy)]),
        LineString([(maxx, miny), (maxx, maxy)]),
        LineString([(midx, miny), (midx, maxy)]),
        LineString([(minx, midy), (maxx, midy)]),
    ]
    return gpd.GeoDataFrame(
        {"highway": ["residential"] * len(lines)},
        geometry=lines,
        crs=crs,
    )


def test_make_square_box_is_1km():
    geom = diagnostic._make_square_box(2000.0, 3000.0, size_m=1000.0)
    minx, miny, maxx, maxy = geom.bounds

    assert maxx - minx == pytest.approx(1000.0)
    assert maxy - miny == pytest.approx(1000.0)
    assert geom.centroid.x == pytest.approx(2000.0)
    assert geom.centroid.y == pytest.approx(3000.0)


def test_sample_random_boxes_with_seeded_rng_stays_inside_area():
    rng = random.Random(7)
    area = box(0, 0, 4000, 4000)

    boxes = diagnostic._sample_random_boxes_in_projected_area(
        area,
        count=5,
        rng=rng,
        size_m=1000.0,
        max_attempts=1000,
    )

    assert len(boxes) == 5
    for sampled_box in boxes:
        minx, miny, maxx, maxy = sampled_box.bounds
        assert maxx - minx == pytest.approx(1000.0)
        assert maxy - miny == pytest.approx(1000.0)
        assert area.covers(sampled_box)


def test_provider_analysis_and_metrics_with_mocked_grid_roads(monkeypatch):
    box_projected = gpd.GeoDataFrame(
        {"box_id": [1]},
        geometry=[diagnostic._make_square_box(674000.0, 7186000.0, size_m=1000.0)],
        crs=diagnostic.PROJECTED_CRS,
    )
    box_wgs84 = box_projected.to_crs("EPSG:4326")
    roads_projected = _grid_roads_for_bbox(
        tuple(box_projected.total_bounds),
        crs=diagnostic.PROJECTED_CRS,
    )
    roads_wgs84 = roads_projected.to_crs("EPSG:4326")

    monkeypatch.setattr(
        diagnostic,
        "get_osm_data",
        lambda bbox, *args, **kwargs: roads_wgs84,
    )

    result = diagnostic._analyze_provider_for_box(
        1,
        box_wgs84,
        provider="protomaps",
        timeout=1,
        min_road_features=1,
    )
    metrics = diagnostic._alignment_metrics(
        result.protoblocks,
        result.roads,
        box_wgs84,
        road_provider="protomaps",
        protoblock_provider="protomaps",
    )

    assert result.error is None
    assert result.road_count == 6
    assert result.protoblock_count > 0
    assert metrics["sample_count"] > 0
    assert metrics["mean_distance_m"] < 0.5
    assert metrics["p95_distance_m"] < 0.5
    assert metrics["max_distance_m"] < 0.5


def test_write_wgs84_exports_lon_lat_geojson(tmp_path):
    projected = gpd.GeoDataFrame(
        {"name": ["sample"]},
        geometry=[diagnostic._make_square_box(674000, 7186000, size_m=1000.0)],
        crs=diagnostic.PROJECTED_CRS,
    )
    output_path = tmp_path / "sample.geojson"

    diagnostic._write_wgs84(projected, output_path)
    reloaded = gpd.read_file(output_path)

    assert reloaded.crs.to_epsg() == 4326
    minx, miny, maxx, maxy = reloaded.total_bounds
    assert -50.0 < minx < -48.0
    assert -50.0 < maxx < -48.0
    assert -26.0 < miny < -25.0
    assert -26.0 < maxy < -25.0
