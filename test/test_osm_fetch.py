import pytest
from unittest.mock import patch, MagicMock
import geopandas as gpd
from shapely.geometry import Point
import pandas as pd

from headless_sidewalkreator.osm_fetch import (
    _normalize_bbox,
    osm_query_string_by_bbox,
    get_osm_data,
)


def test_normalize_bbox():
    """Test the _normalize_bbox function."""
    bbox = (10, 20, 30, 40)  # minx, miny, maxx, maxy
    expected = (40, 20, 30, 10)  # north, south, east, west
    assert _normalize_bbox(bbox) == expected


def test_osm_query_string_by_bbox():
    """Test the osm_query_string_by_bbox function."""
    bbox = (10, 20, 30, 40)
    tags = {"highway": "residential", "building": True}
    query = osm_query_string_by_bbox(bbox, tags)
    assert '[highway="residential"]' in query
    assert "[building]" in query
    assert "20,10,40,30" in query


def test_get_osm_data_features_from_bbox():
    """Test get_osm_data with ox.features_from_bbox."""
    mock_gdf = gpd.GeoDataFrame({"geometry": [Point(1, 1)]}, crs="EPSG:4326")
    ox_mock = MagicMock(spec=['features_from_bbox'])
    ox_mock.features_from_bbox.return_value = mock_gdf

    with patch('headless_sidewalkreator.osm_fetch.ox', ox_mock):
        gdf = get_osm_data((0,0,1,1))
        assert not gdf.empty
        ox_mock.features_from_bbox.assert_called_once()


def test_get_osm_data_geometries_from_bbox():
    """Test get_osm_data with ox.geometries_from_bbox."""
    mock_gdf = gpd.GeoDataFrame({"geometry": [Point(1, 1)]}, crs="EPSG:4326")
    ox_mock = MagicMock(spec=['geometries_from_bbox', 'utils_graph'])
    ox_mock.geometries_from_bbox.return_value = mock_gdf

    with patch('headless_sidewalkreator.osm_fetch.ox', ox_mock):
        gdf = get_osm_data((0,0,1,1))
        assert not gdf.empty
        ox_mock.geometries_from_bbox.assert_called_once()


def test_get_osm_data_features_module():
    """Test get_osm_data with ox.features.features_from_bbox."""
    mock_gdf = gpd.GeoDataFrame({"geometry": [Point(1, 1)]}, crs="EPSG:4326")
    ox_mock = MagicMock(spec=['features', 'utils_graph'])
    ox_mock.features.features_from_bbox.return_value = mock_gdf

    with patch('headless_sidewalkreator.osm_fetch.ox', ox_mock):
        gdf = get_osm_data((0,0,1,1))
        assert not gdf.empty
        ox_mock.features.features_from_bbox.assert_called_once()


def test_get_osm_data_no_fetch_func():
    """Test get_osm_data when no fetch function is found."""
    ox_mock = MagicMock(spec=[])
    with patch('headless_sidewalkreator.osm_fetch.ox', ox_mock):
        with pytest.raises(RuntimeError, match="No suitable OSMnx bbox fetch function found"):
            get_osm_data((0, 0, 1, 1))


@patch("time.sleep", return_value=None)
def test_get_osm_data_retry(mock_sleep):
    """Test the retry mechanism in get_osm_data."""
    mock_gdf = gpd.GeoDataFrame({"geometry": [Point(1, 1)]}, crs="EPSG:4326")
    ox_mock = MagicMock(spec=['features_from_bbox'])
    ox_mock.features_from_bbox.side_effect = [Exception("Failed to fetch"), mock_gdf]

    with patch('headless_sidewalkreator.osm_fetch.ox', ox_mock):
        gdf = get_osm_data((0,0,1,1), max_retries=1)
        assert not gdf.empty
        assert ox_mock.features_from_bbox.call_count == 2


def test_get_osm_data_non_gdf_result():
    """Test get_osm_data with a non-GeoDataFrame result that can be converted."""
    data = {'osmid': [1, 2], 'geometry': [Point(0, 0), Point(1, 1)]}
    df = pd.DataFrame(data)

    ox_mock = MagicMock(spec=['features_from_bbox', 'utils_graph'])
    ox_mock.features_from_bbox.return_value = df
    ox_mock.utils_graph.graph_to_gdfs.return_value = gpd.GeoDataFrame(df, crs="EPSG:4326")

    with patch('headless_sidewalkreator.osm_fetch.ox', ox_mock):
        gdf = get_osm_data((0,0,1,1))
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert 'geometry' in gdf.columns
        assert gdf.crs is not None


def test_get_osm_data_missing_crs():
    """Test get_osm_data when the returned GeoDataFrame has no CRS."""
    mock_gdf = gpd.GeoDataFrame({'geometry': [Point(0, 0)]})
    assert mock_gdf.crs is None

    ox_mock = MagicMock(spec=['features_from_bbox'])
    ox_mock.features_from_bbox.return_value = mock_gdf

    with patch('headless_sidewalkreator.osm_fetch.ox', ox_mock):
        gdf = get_osm_data((0,0,1,1))
        assert gdf.crs.to_string() == "EPSG:4326"
