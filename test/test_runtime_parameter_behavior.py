"""Regression coverage for user-visible runtime option behavior."""

import importlib
import json
import sys

import geopandas as gpd
from geopandas.testing import assert_geodataframe_equal
import pytest
from shapely.geometry import LineString, MultiLineString, box

from headless_sidewalkreator import generate_protoblocks, sidewalkreator
from headless_sidewalkreator.generic_functions import (
    fetch_street_network_for_bbox,
    filter_protoblocks_by_sidewalks,
    normalize_protomaps_topology,
    split_lines_at_intersections,
    split_sidewalks_gdf,
)
from headless_sidewalkreator.parameters import default_widths


@pytest.fixture
def metric_block():
    """A 100 m block in its locally estimated UTM zone, with no network calls."""
    polygon = box(500000, 2300000, 500100, 2300100)
    coordinates = list(polygon.exterior.coords)
    roads = gpd.GeoDataFrame(
        {"highway": ["residential"] * 4},
        geometry=[LineString(coordinates[i:i + 2]) for i in range(4)],
        crs=32648,
    )
    area = gpd.GeoDataFrame(geometry=[polygon], crs=roads.crs)
    return area, roads


@pytest.mark.parametrize("width, inset", [(6.0, 4.0), (14.0, 8.0)])
def test_custom_width_reaches_generated_geometry(metric_block, width, inset):
    area, roads = metric_block
    result = sidewalkreator(
        input_polygon_gdf=area, osm_gdf=roads,
        parameters={"default_widths": {**default_widths, "residential": width},
                    "buffer_dist": 2.0, "default_curve_radius": 0,
                    "min_stretch_size": None},
    )
    assert result["sidewalks"].total_bounds == pytest.approx(
        [500000 + inset, 2300000 + inset, 500100 - inset, 2300100 - inset]
    )


@pytest.mark.parametrize("ignore, cutoff, expected_empty", [
    (False, 40, True), (True, 40, False), (False, 100, False),
])
def test_existing_sidewalk_policy_changes_full_pipeline(metric_block, ignore, cutoff, expected_empty):
    area, roads = metric_block
    existing = gpd.GeoDataFrame(
        {"highway": ["footway"], "footway": ["sidewalk"]},
        geometry=[box(500005, 2300005, 500095, 2300095).boundary], crs=roads.crs,
    )
    osm = gpd.GeoDataFrame(gpd.pd.concat([roads, existing], ignore_index=True), crs=roads.crs)
    original = osm.copy()
    result = sidewalkreator(
        input_polygon_gdf=area, osm_gdf=osm, ignore_existing=ignore,
        parameters={"cutoff_percent_protoblock": cutoff},
    )
    assert result["sidewalks"].empty == expected_empty
    assert not result["protoblocks"].empty  # Diagnostic output retains all blocks.
    if expected_empty:
        assert result["crossings"].empty
        assert result["kerbs"].empty
    assert_geodataframe_equal(osm, original)


def test_coverage_clips_deduplicates_and_keeps_uncovered_blocks():
    blocks = gpd.GeoDataFrame(geometry=[box(0, 0, 10, 10), box(10, 0, 20, 10)], crs=3857)
    existing = gpd.GeoDataFrame(
        geometry=[LineString([(-100, 1), (10, 1)])] * 2, crs=blocks.crs
    )
    original = blocks.copy()
    assert len(filter_protoblocks_by_sidewalks(blocks, existing, 26)) == 2
    kept = filter_protoblocks_by_sidewalks(blocks, existing, 24)
    assert kept.index.tolist() == [1]
    assert len(filter_protoblocks_by_sidewalks(blocks, existing, 0, ignore_existing=True)) == 2
    assert_geodataframe_equal(blocks, original)


@pytest.mark.parametrize("cutoff", [-1, 101, float("nan"), True])
def test_invalid_coverage_threshold_is_rejected(metric_block, cutoff):
    area, roads = metric_block
    with pytest.raises(ValueError, match="cutoff_percent_protoblock"):
        sidewalkreator(input_polygon_gdf=area, osm_gdf=roads,
                      parameters={"cutoff_percent_protoblock": cutoff})


def test_noding_preserves_distinct_widths_tags_and_multiline_sources():
    roads = gpd.GeoDataFrame(
        {"width": [6.0, 20.0], "sidewalk": ["left", "no"]},
        geometry=[MultiLineString([[(-10, 0), (10, 0)]]), LineString([(0, -10), (0, 10)])],
        crs=3857,
    )
    result = split_lines_at_intersections(roads)
    assert len(result) == 4
    for row in result.itertuples():
        if row.geometry.bounds[1] == row.geometry.bounds[3]:
            assert (row.width, row.sidewalk) == (6.0, "left")
        else:
            assert (row.width, row.sidewalk) == (20.0, "no")


def test_protomaps_repair_preserves_source_widths():
    roads = gpd.GeoDataFrame(
        {"width": [6.0, 20.0]},
        geometry=[LineString([(0, 0), (10, 0)]), LineString([(10.2, -10), (10.2, 10)])],
        crs=3857,
    )
    result = normalize_protomaps_topology(roads)
    assert result.attrs["protomaps_topology"]["undershoots_repaired"] == 1
    for row in result.itertuples():
        expected = 6.0 if row.geometry.bounds[1] == row.geometry.bounds[3] else 20.0
        assert row.width == expected


@pytest.mark.parametrize("api", [sidewalkreator, generate_protoblocks])
@pytest.mark.parametrize("parameters, error", [
    ({"buffer_dst": 5}, "Unknown runtime parameter"),
    ({"provider": "typo"}, "provider must be"),
    ({"provider_kwargs": {"timeout": 2}}, "Unknown provider option"),
    ({"provider": "protomaps", "provider_kwargs": {"tile_worker": 2}}, "tile_workers"),
    ({"provider_kwargs": []}, "provider_kwargs must be"),
])
def test_bad_options_fail_before_area_resolution_or_download(api, parameters, error):
    with pytest.raises((TypeError, ValueError), match=error):
        api(parameters=parameters)


def test_standalone_rejects_crossing_only_controls():
    with pytest.raises(ValueError, match="crossing_inward_offset"):
        generate_protoblocks(parameters={"crossing_inward_offset": 2})


def test_standalone_debug_option_writes_requested_layer(metric_block, monkeypatch, tmp_path):
    area, roads = metric_block
    monkeypatch.chdir(tmp_path)
    generate_protoblocks(input_polygon_gdf=area, osm_gdf=roads,
                        parameters={"save_debug_layers": True})
    saved = gpd.read_file(tmp_path / "debug_layers/sidewalkreator_splitted_lines.geojson")
    assert len(saved) == 4
    assert saved["width"].eq(6.0).all()


def test_minimum_stretch_merges_without_crossings():
    sidewalks = gpd.GeoDataFrame(
        geometry=[LineString([(0, 0), (2, 0)]), LineString([(2, 0), (12, 0)])], crs=3857
    )
    empty = gpd.GeoDataFrame(geometry=[], crs=sidewalks.crs)
    result = split_sidewalks_gdf(sidewalks, empty, empty, empty, min_stretch_size=5)
    assert len(result) == 1
    assert result.length.iloc[0] == pytest.approx(12)


def test_empty_acquisition_does_not_fabricate_streets(monkeypatch):
    monkeypatch.setattr("headless_sidewalkreator.generic_functions.get_osm_data",
                        lambda *a, **kw: gpd.GeoDataFrame(geometry=[], crs=4326))
    with pytest.raises(RuntimeError, match="No data was downloaded"):
        fetch_street_network_for_bbox((0, 0, 1, 1))


def test_overture_progress_option_uses_real_constructor(monkeypatch, metric_block):
    area, roads = metric_block
    seen = {}

    def get_data(self, bbox, tags, **kwargs):
        seen.update(kwargs)
        seen["release"] = self.release
        return roads.to_crs(4326)

    monkeypatch.setattr("headless_sidewalkreator.planet_download.overture.OvertureDownloader.get_data", get_data)
    result = generate_protoblocks(
        input_polygon_gdf=area,
        parameters={"provider": "overture", "provider_kwargs": {"release": "test-release"}},
    )
    assert not result.empty
    assert seen == {"release": "test-release", "show_progress": False}


@pytest.mark.parametrize("content", [None, "[1, 2]", "{invalid"])
def test_cli_rejects_missing_or_invalid_parameter_files(monkeypatch, tmp_path, content, capsys):
    cli = importlib.import_module("headless_sidewalkreator.main")
    path = tmp_path / "options.json"
    if content is not None:
        path.write_text(content)
    monkeypatch.setattr(sys, "argv", ["sidewalkreator", "--bbox", "0", "0", "1", "1",
                                     "--output-dir", str(tmp_path / "output"), "--parameters", str(path)])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert "--parameters" in capsys.readouterr().err
    assert not (tmp_path / "output").exists()


def test_cli_provider_flag_preserves_nested_json_options(monkeypatch, tmp_path):
    cli = importlib.import_module("headless_sidewalkreator.main")
    path = tmp_path / "options.json"
    path.write_text(json.dumps({"provider_kwargs": {"zoom": 14, "tile_workers": 2}}))
    seen = {}
    monkeypatch.setattr(cli, "sidewalkreator", lambda **kwargs: seen.update(kwargs))
    monkeypatch.setattr(cli, "save_results_to_directory", lambda *a: None)
    monkeypatch.setattr(sys, "argv", ["sidewalkreator", "--bbox", "0", "0", "1", "1",
                                     "--output-dir", str(tmp_path), "--parameters", str(path),
                                     "--provider", "protomaps"])
    cli.main()
    assert seen["parameters"] == {"provider": "protomaps",
                                  "provider_kwargs": {"zoom": 14, "tile_workers": 2}}
