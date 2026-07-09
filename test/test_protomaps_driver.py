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
    with patch('headless_sidewalkreator.planet_download.protomaps.Reader') as mock_reader:
        mock_reader.return_value.get.return_value = None
        gdf = dl.get_data((0, 0, 1, 1))
        assert gdf.empty

@patch('requests.Session')
@patch('mapbox_vector_tile.decode')
@patch('gzip.decompress')
def test_protomaps_get_data_gzipped_and_mapped(mock_decompress, mock_decode, mock_session):
    """Test that gzipped PMTiles MVTs are decompressed and tag mapping maps pmap:kind_detail to highway."""
    dl = ProtomapsDownloader()

    # Dummy gzipped tile data starts with gzip magic header
    dummy_gzipped_data = b'\x1f\x8b\x08dummydata'
    dummy_decompressed_data = b'dummydecompressed'

    mock_decompress.return_value = dummy_decompressed_data

    # Mock decoded layer structure
    mock_decode.return_value = {
        'roads': {
            'extent': 4096,
            'features': [
                {
                    'geometry': {
                        'type': 'LineString',
                        'coordinates': [[0, 0], [1024, 1024]]
                    },
                    'properties': {
                        'pmap:kind_detail': 'residential',
                        'name': 'Test Road'
                    }
                }
            ]
        }
    }

    with patch('headless_sidewalkreator.planet_download.protomaps.Reader') as mock_reader:
        # Mock tile range calculations to only loop over one tile (0, 0, 1, 1 at zoom 14)
        # Mock reader.get to return dummy gzipped bytes
        mock_reader_instance = mock_reader.return_value
        mock_reader_instance.get.return_value = dummy_gzipped_data

        gdf = dl.get_data((0, 0, 0.01, 0.01), zoom=14)

        # Check decompression was called on the dummy gzipped data
        mock_decompress.assert_called_with(dummy_gzipped_data)

        # Check mapbox_vector_tile.decode was called on the decompressed bytes
        mock_decode.assert_called_with(dummy_decompressed_data)

        # Assert returned GeoDataFrame has correctly mapped highway column
        assert not gdf.empty
        assert 'highway' in gdf.columns
        assert gdf.iloc[0]['highway'] == 'residential'
