"""Regression tests for behavior inherited from the QGIS GUI implementation."""

import geopandas as gpd
import pytest
from geopandas.testing import assert_geodataframe_equal
from shapely.geometry import LineString, Point, box

from headless_sidewalkreator import sidewalkreator
from headless_sidewalkreator.generic_functions import (
    draw_crossings_gdf,
    handle_sidewalk_tags,
)


def test_positive_sidewalk_tags_do_not_limit_unrelated_generated_sidewalks():
    """GUI sure zones are diagnostic; they do not clip the final sidewalk layer."""
    sidewalks = gpd.GeoDataFrame(
        geometry=[
            LineString([(0, 4), (10, 4)]),
            LineString([(0, 40), (10, 40)]),
        ],
        crs="EPSG:3857",
    )
    streets = gpd.GeoDataFrame(
        {"sidewalk": ["yes"], "width": [6.0]},
        geometry=[LineString([(0, 0), (10, 0)])],
        crs=sidewalks.crs,
    )

    actual = handle_sidewalk_tags(sidewalks, streets)

    assert_geodataframe_equal(actual, sidewalks)


def test_sidewalk_left_excludes_only_the_right_side():
    """Match the GUI interpretation of sidewalk=left for directed OSM ways."""
    sidewalks = gpd.GeoDataFrame(
        {"side": ["left", "right"]},
        geometry=[
            LineString([(0, 3.5), (10, 3.5)]),
            LineString([(0, -3.5), (10, -3.5)]),
        ],
        crs="EPSG:3857",
    )
    streets = gpd.GeoDataFrame(
        {"sidewalk": ["left"], "width": [6.0]},
        geometry=[LineString([(0, 0), (10, 0)])],
        crs=sidewalks.crs,
    )

    actual = handle_sidewalk_tags(sidewalks, streets, added_width=0.0)

    assert actual["side"].tolist() == ["left"]


def test_crossings_are_not_fabricated_when_a_sidewalk_axis_is_missing():
    """The GUI skips candidates unless both sidewalk intersections are found."""
    streets = gpd.GeoDataFrame(
        {"width": [8.0] * 4},
        geometry=[
            LineString([(-20, 0), (0, 0)]),
            LineString([(0, 0), (20, 0)]),
            LineString([(0, -20), (0, 0)]),
            LineString([(0, 0), (0, 20)]),
        ],
        crs="EPSG:3857",
    )
    sidewalks = gpd.GeoDataFrame(
        geometry=[
            LineString([(-25, 4), (25, 4)]),
            LineString([(4, -25), (4, 25)]),
        ],
        crs=streets.crs,
    )

    actual = draw_crossings_gdf(
        streets,
        sidewalks,
        curve_radius=0.0,
        inward_offset=0.0,
        extra_length=0.0,
        max_crossings_iterations=2,
        abs_max_crossing_len=30.0,
        perc_tol_crossings=25.0,
        max_ray_iterations=2,
        assume_noded=True,
    )

    assert actual.empty


def test_gui_minimum_crossing_segment_length_is_respected():
    """The GUI default skips candidates belonging to segments under 20 m."""
    streets = gpd.GeoDataFrame(
        {"width": [6.0] * 4},
        geometry=[
            LineString([(-10, 0), (0, 0)]),
            LineString([(0, 0), (10, 0)]),
            LineString([(0, -10), (0, 0)]),
            LineString([(0, 0), (0, 10)]),
        ],
        crs="EPSG:3857",
    )
    sidewalks = gpd.GeoDataFrame(
        geometry=[
            LineString([(-12, 3), (12, 3)]),
            LineString([(-12, -3), (12, -3)]),
            LineString([(3, -12), (3, 12)]),
            LineString([(-3, -12), (-3, 12)]),
        ],
        crs=streets.crs,
    )

    actual = draw_crossings_gdf(
        streets,
        sidewalks,
        curve_radius=0.0,
        inward_offset=0.0,
        extra_length=0.0,
        assume_noded=True,
    )

    assert actual.empty


@pytest.mark.parametrize("assume_noded", [False, True])
def test_crossing_centers_must_be_inside_a_protoblock(assume_noded):
    """GUI keeps a candidate only when its 1 m center buffer is contained."""
    streets = gpd.GeoDataFrame(
        {"width": [6.0] * 4},
        geometry=[
            LineString([(-30, 0), (0, 0)]),
            LineString([(0, 0), (30, 0)]),
            LineString([(0, -30), (0, 0)]),
            LineString([(0, 0), (0, 30)]),
        ],
        crs="EPSG:3857",
    )
    sidewalks = gpd.GeoDataFrame(
        geometry=[
            LineString([(-35, 3), (35, 3)]),
            LineString([(-35, -3), (35, -3)]),
            LineString([(3, -35), (3, 35)]),
            LineString([(-3, -35), (-3, 35)]),
        ],
        crs=streets.crs,
    )
    east_only_protoblock = gpd.GeoDataFrame(
        geometry=[box(1.5, -1.5, 15, 1.5)],
        crs=streets.crs,
    )

    actual = draw_crossings_gdf(
        streets,
        sidewalks,
        east_only_protoblock,
        curve_radius=0.0,
        inward_offset=0.0,
        extra_length=0.0,
        min_segment_length=0.0,
        assume_noded=assume_noded,
    )

    assert len(actual) == 1
    assert list(actual.geometry.iloc[0].coords)[2][0] > 0


@pytest.mark.parametrize("assume_noded", [False, True])
def test_default_crossing_direction_is_parallel_to_transversal_street(
    assume_noded,
):
    """The GUI defaults to the incident street making the smallest angle."""
    streets = gpd.GeoDataFrame(
        {"width": [6.0] * 3},
        geometry=[
            LineString([(0, 0), (30, 0)]),
            LineString([(0, 0), (-30, 0)]),
            LineString([(0, 0), (15, 25.980762)]),
        ],
        crs="EPSG:3857",
    )
    sidewalks = gpd.GeoDataFrame(
        geometry=[Point(3, 0).buffer(4).boundary],
        crs=streets.crs,
    )
    east_only_protoblock = gpd.GeoDataFrame(
        geometry=[box(1.5, -1.5, 15, 1.5)],
        crs=streets.crs,
    )

    actual = draw_crossings_gdf(
        streets,
        sidewalks,
        east_only_protoblock,
        curve_radius=0.0,
        inward_offset=0.0,
        extra_length=0.0,
        min_segment_length=0.0,
        perc_tol_crossings=100.0,
        assume_noded=assume_noded,
    )

    assert len(actual) == 1
    start, *_, end = actual.geometry.iloc[0].coords
    dx = abs(end[0] - start[0])
    dy = abs(end[1] - start[1])
    assert dy / dx == pytest.approx(3**0.5, rel=0.05)


@pytest.mark.parametrize("assume_noded", [False, True])
def test_crossing_offset_uses_gui_transversal_width_selection(assume_noded):
    """A wide current street must not override narrower transversal streets."""
    streets = gpd.GeoDataFrame(
        {"width": [12.0, 6.0, 8.0]},
        geometry=[
            LineString([(0, 0), (30, 0)]),
            LineString([(0, 0), (-30, 0)]),
            LineString([(0, 0), (0, 30)]),
        ],
        crs="EPSG:3857",
    )
    sidewalks = gpd.GeoDataFrame(
        geometry=[Point(4, 0).buffer(5).boundary],
        crs=streets.crs,
    )
    east_only_protoblock = gpd.GeoDataFrame(
        geometry=[box(2.5, -1.5, 15, 1.5)],
        crs=streets.crs,
    )

    actual = draw_crossings_gdf(
        streets,
        sidewalks,
        east_only_protoblock,
        curve_radius=0.0,
        inward_offset=0.0,
        extra_length=0.0,
        min_segment_length=0.0,
        assume_noded=assume_noded,
    )

    assert len(actual) == 1
    assert actual.iloc[0]["center_offset_m"] == pytest.approx(4.0)


def test_qgis_preloaded_grid_fixture_has_matching_output_counts():
    """Match the committed QGIS fixture: 6 sidewalks, 14 crossings, 28 kerbs."""
    minx, miny, maxx, maxy = -49.3050, -25.5185, -49.3020, -25.5156
    lines = [
        LineString([(-49.3048, y), (-49.3026, y)])
        for y in (-25.5179, -25.5172, -25.5165, -25.5158)
    ]
    lines.extend(
        LineString([(x, -25.5180), (x, -25.5157)])
        for x in (-49.3046, -49.3036, -49.3028)
    )
    osm = gpd.GeoDataFrame(
        {"highway": ["residential"] * len(lines)},
        geometry=lines,
        crs="EPSG:4326",
    )
    area = gpd.GeoDataFrame(
        geometry=[box(minx, miny, maxx, maxy)],
        crs=osm.crs,
    )

    result = sidewalkreator(
        input_polygon_gdf=area,
        osm_gdf=osm,
        ignore_existing=True,
    )

    assert len(result["sidewalks"]) == 6
    assert len(result["crossings"]) == 14
    assert len(result["kerbs"]) == 28
