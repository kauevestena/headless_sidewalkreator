import pytest
import mercantile
import requests
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
        gdf = dl.get_data((0, 0, 1, 1), show_progress=False)
        assert gdf.empty


@patch('requests.Session')
@patch('mapbox_vector_tile.decode')
def test_protomaps_get_data_uses_mercantile_tiles_and_bounds(mock_decode, mock_session):
    dl = ProtomapsDownloader()
    tile = mercantile.Tile(x=1, y=2, z=14)
    tile_bounds = mercantile.LngLatBbox(west=10.0, south=20.0, east=11.0, north=21.0)
    mock_decode.return_value = {
        'roads': {
            'extent': 4096,
            'features': [
                {
                    'geometry': {
                        'type': 'LineString',
                        'coordinates': [[0, 0], [4096, 4096]]
                    },
                    'properties': {'pmap:kind': 'major_road'}
                }
            ]
        }
    }

    with (
        patch('headless_sidewalkreator.planet_download.protomaps.Reader') as mock_reader,
        patch(
            'headless_sidewalkreator.planet_download.protomaps.mercantile.tiles',
            return_value=[tile],
        ) as mock_tiles,
        patch(
            'headless_sidewalkreator.planet_download.protomaps.mercantile.bounds',
            return_value=tile_bounds,
        ) as mock_bounds,
    ):
        mock_reader.return_value.get.return_value = b'dummy'
        gdf = dl.get_data((10.1, 20.1, 10.2, 20.2), zoom=14, show_progress=False)

    mock_tiles.assert_called_once_with(10.1, 20.1, 10.2, 20.2, zooms=[14])
    mock_reader.return_value.get.assert_called_once_with(14, 1, 2)
    mock_bounds.assert_called_once_with(tile)
    assert not gdf.empty
    assert tuple(gdf.geometry.iloc[0].coords[0]) == pytest.approx((10.0, 21.0))
    assert tuple(gdf.geometry.iloc[0].coords[-1]) == pytest.approx((11.0, 20.0))
    assert gdf.iloc[0]['highway'] == 'major_road'


@patch('requests.Session')
@patch('mapbox_vector_tile.decode')
def test_protomaps_get_data_filters_roads_by_pmap_kind(mock_decode, mock_session):
    dl = ProtomapsDownloader()
    mock_decode.return_value = {
        'roads': {
            'extent': 4096,
            'features': [
                {
                    'geometry': {
                        'type': 'LineString',
                        'coordinates': [[0, 0], [4096, 4096]]
                    },
                    'properties': {'pmap:kind': 'minor_road'}
                },
                {
                    'geometry': {
                        'type': 'LineString',
                        'coordinates': [[0, 0], [4096, 0]]
                    },
                    'properties': {'pmap:kind': 'path'}
                },
                {
                    'geometry': {
                        'type': 'LineString',
                        'coordinates': [[0, 4096], [4096, 4096]]
                    },
                    'properties': {'kind': 'residential'}
                },
            ]
        }
    }

    with patch('headless_sidewalkreator.planet_download.protomaps.Reader') as mock_reader:
        mock_reader.return_value.get.return_value = b'dummy'
        gdf = dl.get_data((0, 0, 0.01, 0.01), zoom=14, show_progress=False)

    assert len(gdf) == 1
    assert gdf.iloc[0]['pmap:kind'] == 'minor_road'
    assert gdf.iloc[0]['highway'] == 'minor_road'


@patch('requests.Session')
@patch('mapbox_vector_tile.decode')
@patch('gzip.decompress')
def test_protomaps_get_data_gzipped_and_mapped(mock_decompress, mock_decode, mock_session):
    """Gzipped PMTiles MVTs are decompressed and mapped to OSM-like tags."""
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
                        'pmap:kind': 'minor_road',
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

        gdf = dl.get_data((0, 0, 0.01, 0.01), zoom=14, show_progress=False)

        # Check decompression was called on the dummy gzipped data
        mock_decompress.assert_called_with(dummy_gzipped_data)

        # Check mapbox_vector_tile.decode preserved native tile Y-down coordinates.
        mock_decode.assert_called_with(
            dummy_decompressed_data,
            default_options={"y_coord_down": True},
        )

        # Assert returned GeoDataFrame has correctly mapped highway column
        assert not gdf.empty
        assert 'highway' in gdf.columns
        assert gdf.iloc[0]['highway'] == 'minor_road'


@patch('requests.Session')
@patch('mapbox_vector_tile.decode')
def test_protomaps_get_data_uses_tqdm(mock_decode, mock_session):
    dl = ProtomapsDownloader()
    tile = mercantile.Tile(x=1, y=2, z=14)
    mock_decode.return_value = {}

    with (
        patch('headless_sidewalkreator.planet_download.protomaps.Reader') as mock_reader,
        patch(
            'headless_sidewalkreator.planet_download.protomaps.mercantile.tiles',
            return_value=[tile],
        ),
        patch('headless_sidewalkreator.planet_download.protomaps.tqdm') as mock_tqdm,
    ):
        mock_reader.return_value.get.return_value = b'dummy'
        mock_tqdm.side_effect = lambda iterable, **kwargs: iterable
        gdf = dl.get_data((0, 0, 0.01, 0.01), zoom=14)

    assert gdf.empty
    mock_tqdm.assert_called_once()
    _, tqdm_kwargs = mock_tqdm.call_args
    assert tqdm_kwargs["desc"] == "Fetching Protomaps tiles"
    assert tqdm_kwargs["unit"] == "tile"
    assert tqdm_kwargs["disable"] is False


@patch('requests.Session')
@patch('mapbox_vector_tile.decode')
def test_protomaps_range_fetch_retries_http_errors(mock_decode, mock_session):
    class DummyReader:
        def __init__(self, get_bytes):
            self.get_bytes = get_bytes

        def header(self):
            return {"tile_compression": None}

        def get(self, z, x, y):
            return self.get_bytes(10, 5)

    def make_response(status_code, content):
        response = MagicMock()
        response.status_code = status_code
        response.content = content
        if status_code >= 400:
            response.raise_for_status.side_effect = requests.HTTPError(
                f"{status_code} error"
            )
        else:
            response.raise_for_status.return_value = None
        return response

    dl = ProtomapsDownloader()
    mock_session.return_value.get.side_effect = [
        make_response(500, b"error"),
        make_response(206, b"12345"),
    ]
    mock_decode.return_value = {}

    with (
        patch('headless_sidewalkreator.planet_download.protomaps.Reader', DummyReader),
        patch(
            'headless_sidewalkreator.planet_download.protomaps.mercantile.tiles',
            return_value=[mercantile.Tile(x=1, y=2, z=14)],
        ),
    ):
        gdf = dl.get_data(
            (0, 0, 0.01, 0.01),
            zoom=14,
            max_retries=1,
            show_progress=False,
        )

    assert gdf.empty
    assert mock_session.return_value.get.call_count == 2
    mock_decode.assert_called_once_with(
        b"12345",
        default_options={"y_coord_down": True},
    )
