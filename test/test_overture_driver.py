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
    gdf = dl.get_data((0, 0, 1, 1))

    assert len(gdf) == 2
    assert 'highway' in gdf.columns
    assert 'building' in gdf.columns
    assert gdf.crs == "EPSG:4326"
