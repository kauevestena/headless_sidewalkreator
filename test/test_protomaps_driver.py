import pytest
from unittest.mock import MagicMock, patch
from headless_sidewalkreator.planet_download.protomaps import ProtomapsDownloader

def test_protomaps_downloader_init():
    dl = ProtomapsDownloader(url="https://example.com/map.pmtiles")
    assert dl.url == "https://example.com/map.pmtiles"
    assert dl.provider_name == "protomaps"

@patch('requests.Session')
def test_protomaps_get_data_mocked(mock_session):
    # Mocking PMTiles and MVT decoding is complex,
    # but we can check if it calls the right methods.
    dl = ProtomapsDownloader()

    # Just a smoke test to ensure no immediate crash
    with patch('pmtiles.reader.Reader') as mock_reader:
        mock_reader.return_value.get.return_value = None
        gdf = dl.get_data((0, 0, 1, 1))
        assert gdf.empty
