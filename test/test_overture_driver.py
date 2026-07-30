import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString
from headless_sidewalkreator.planet_download.overture import OvertureDownloader

def test_overture_downloader_init():
    dl = OvertureDownloader(release="test-release")
    assert dl.release == "test-release"
    assert dl.provider_name == "overture"

@patch('duckdb.connect')
def test_overture_get_data_empty(mock_connect):
    mock_con = MagicMock()
    mock_connect.return_value = mock_con
    mock_con.execute.return_value.df.return_value = pd.DataFrame()

    dl = OvertureDownloader()
    gdf = dl.get_data((-72.53, 42.37, -72.52, 42.38))

    assert isinstance(gdf, gpd.GeoDataFrame)
    assert gdf.empty

@patch('duckdb.connect')
def test_overture_get_data_mocked(mock_connect):
    mock_con = MagicMock()
    mock_connect.return_value = mock_con

    # Mock transportation data
    trans_df = pd.DataFrame({
        'id': ['1'],
        'subtype': ['road'],
        'class': ['residential'],
        'name': ['Test St'],
        'geometry_wkb': [LineString([(0, 0), (1, 1)]).wkb]
    })

    # Mock buildings data
    build_df = pd.DataFrame({
        'id': ['2'],
        'name': ['Building A'],
        'geometry_wkb': [LineString([(2, 2), (3, 3)]).wkb] # simplified geometry for test
    })

    # Side effect to return trans_df then build_df
    mock_con.execute.return_value.df.side_effect = [trans_df, build_df]

    dl = OvertureDownloader()
    gdf = dl.get_data((0, 1, 2, 3))

    assert len(gdf) == 2
    assert 'highway' in gdf.columns
    assert 'building' in gdf.columns
    assert gdf.crs == "EPSG:4326"

    # Verify that con.execute was called with parameterized values
    # Filter only execution calls that are parameterized (i.e. have parameter list of length 4)
    param_calls = [
        call for call in mock_con.execute.call_args_list
        if len(call[0]) > 1 and isinstance(call[0][1], list) and len(call[0][1]) == 4
    ]

    assert len(param_calls) == 2

    # First call: transportation query
    call_1_args, call_1_kwargs = param_calls[0]
    query_1 = call_1_args[0]
    params_1 = call_1_args[1]
    assert "bbox.xmin >= ?" in query_1
    assert "bbox.xmax <= ?" in query_1
    assert "bbox.ymin >= ?" in query_1
    assert "bbox.ymax <= ?" in query_1
    assert params_1 == [0, 2, 1, 3] # minx, maxx, miny, maxy

    # Second call: buildings query
    call_2_args, call_2_kwargs = param_calls[1]
    query_2 = call_2_args[0]
    params_2 = call_2_args[1]
    assert "bbox.xmin >= ?" in query_2
    assert "bbox.xmax <= ?" in query_2
    assert "bbox.ymin >= ?" in query_2
    assert "bbox.ymax <= ?" in query_2
    assert params_2 == [0, 2, 1, 3] # minx, maxx, miny, maxy
