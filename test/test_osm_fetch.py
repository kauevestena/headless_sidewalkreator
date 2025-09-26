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


@pytest.fixture
def mock_ox():
    """Fixture to provide a configured MagicMock for osmnx."""
    ox_mock = MagicMock()
    # Mock the settings attributes that are accessed in the function under test
    ox_mock.settings.requests_timeout = 60
    ox_mock.settings.max_query_area_size = 50000 * 50000  # Default value
    yield ox_mock


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


def test_get_osm_data_features_from_bbox(mock_ox):
    """Test get_osm_data with ox.features_from_bbox."""
    mock_gdf = gpd.GeoDataFrame({"geometry": [Point(1, 1)]}, crs="EPSG:4326")
    mock_ox.features_from_bbox.return_value = mock_gdf

    with patch('headless_sidewalkreator.osm_fetch.ox', mock_ox):
        gdf = get_osm_data((0,0,1,1))
        assert gdf.equals(mock_gdf)
        mock_ox.features_from_bbox.assert_called_once()


def test_get_osm_data_features_module(mock_ox):
    """Test get_osm_data with ox.features.features_from_bbox."""
    mock_gdf = gpd.GeoDataFrame({"geometry": [Point(1, 1)]}, crs="EPSG:4326")
    # Simulate features_from_bbox being in a submodule
    del mock_ox.features_from_bbox
    mock_ox.features.features_from_bbox.return_value = mock_gdf

    with patch('headless_sidewalkreator.osm_fetch.ox', mock_ox):
        gdf = get_osm_data((0,0,1,1))
        assert gdf.equals(mock_gdf)
        mock_ox.features.features_from_bbox.assert_called_once()


def test_get_osm_data_no_fetch_func(mock_ox):
    """Test get_osm_data when no fetch function is found."""
    # Remove all possible fetch functions from the mock
    del mock_ox.features_from_bbox
    del mock_ox.features.features_from_bbox

    with patch('headless_sidewalkreator.osm_fetch.ox', mock_ox):
        with pytest.raises(RuntimeError, match="No suitable OSMnx bbox fetch function found"):
            get_osm_data((0, 0, 1, 1))


@patch("time.sleep", return_value=None)
def test_get_osm_data_retry(mock_sleep, mock_ox):
    """Test the retry mechanism in get_osm_data."""
    mock_gdf = gpd.GeoDataFrame({"geometry": [Point(1, 1)]}, crs="EPSG:4326")
    mock_ox.features_from_bbox.side_effect = [Exception("Failed to fetch"), mock_gdf]

    with patch('headless_sidewalkreator.osm_fetch.ox', mock_ox):
        gdf = get_osm_data((0,0,1,1), max_retries=1)
        assert gdf.equals(mock_gdf)
        assert mock_ox.features_from_bbox.call_count == 2
        mock_sleep.assert_called_once()


def test_get_osm_data_non_gdf_result(mock_ox):
    """Test get_osm_data with a non-GeoDataFrame result that can be converted."""
    data = {'osmid': [1, 2], 'geometry': [Point(0, 0), Point(1, 1)]}
    df = pd.DataFrame(data)

    mock_ox.features_from_bbox.return_value = df
    mock_ox.utils_graph.graph_to_gdfs.return_value = gpd.GeoDataFrame(df, crs="EPSG:4326")

    with patch('headless_sidewalkreator.osm_fetch.ox', mock_ox):
        gdf = get_osm_data((0,0,1,1))
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert 'geometry' in gdf.columns
        assert gdf.crs is not None


def test_get_osm_data_missing_crs(mock_ox):
    """Test get_osm_data when the returned GeoDataFrame has no CRS."""
    mock_gdf = gpd.GeoDataFrame({'geometry': [Point(0, 0)]})
    assert mock_gdf.crs is None

    mock_ox.features_from_bbox.return_value = mock_gdf

    with patch('headless_sidewalkreator.osm_fetch.ox', mock_ox):
        gdf = get_osm_data((0,0,1,1))
        assert gdf.crs.to_string() == "EPSG:4326"


def test_get_osm_data_with_graph_result_conversion_failure(mock_ox):
    """Test get_osm_data with a graph result that fails to convert."""
    mock_graph = MagicMock()
    mock_graph.nodes = [1, 2]
    mock_graph.edges = [(1, 2)]

    mock_ox.features_from_bbox.return_value = mock_graph
    mock_ox.utils_graph.graph_to_gdfs.side_effect = Exception("Conversion Failed")

    with patch('headless_sidewalkreator.osm_fetch.ox', mock_ox):
        gdf = get_osm_data((0, 0, 1, 1))
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert gdf.crs is not None # Should be an empty GDF with CRS

@patch('time.sleep', return_value=None)
def test_get_osm_data_max_retries_exceeded(mock_sleep, mock_ox, caplog):
    """Test that an empty GDF is returned after max_retries."""
    mock_ox.features_from_bbox.side_effect = Exception("Failed")

    with patch('headless_sidewalkreator.osm_fetch.ox', mock_ox):
        # The function should now return an empty GDF, not raise an error
        result_gdf = get_osm_data((0, 0, 1, 1), max_retries=2)

        # Verify that an empty GeoDataFrame is returned
        assert isinstance(result_gdf, gpd.GeoDataFrame)
        assert result_gdf.empty
        assert 'geometry' in result_gdf.columns

        # Check that the fetch was attempted 3 times (1 initial + 2 retries)
        assert mock_ox.features_from_bbox.call_count == 3

        # Check that the appropriate error was logged
        assert "Failed to fetch OSM data after 3 attempts" in caplog.text