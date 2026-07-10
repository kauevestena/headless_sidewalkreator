import pytest
from unittest.mock import MagicMock, patch
from headless_sidewalkreator.osm_fetch import get_osm_data

@patch('headless_sidewalkreator.osm_fetch.OvertureDownloader')
def test_get_osm_data_overture_provider(mock_overture):
    mock_instance = mock_overture.return_value
    mock_instance.get_data.return_value = MagicMock()

    bbox = (0, 0, 1, 1)
    get_osm_data(bbox, provider="overture", release="latest")

    mock_overture.assert_called_once_with(release="latest")
    mock_instance.get_data.assert_called_once_with(bbox, None)

@patch('headless_sidewalkreator.osm_fetch.ProtomapsDownloader')
def test_get_osm_data_protomaps_provider(mock_protomaps):
    mock_instance = mock_protomaps.return_value
    mock_instance.get_data.return_value = MagicMock()

    bbox = (0, 0, 1, 1)
    get_osm_data(bbox, provider="protomaps", url="http://custom.pmtiles")

    mock_protomaps.assert_called_once_with(url="http://custom.pmtiles")
    mock_instance.get_data.assert_called_once_with(
        bbox,
        None,
        timeout=60,
        max_retries=2,
    )
