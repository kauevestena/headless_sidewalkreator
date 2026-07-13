import pytest
import geopandas as gpd
import mercantile
import requests
from unittest.mock import MagicMock, patch
from headless_sidewalkreator.generic_functions import normalize_protomaps_topology
from headless_sidewalkreator.planet_download.protomaps import ProtomapsDownloader
from shapely.geometry import LineString


def test_protomaps_downloader_init():
    dl = ProtomapsDownloader(url="https://example.com/map.pmtiles")
    assert dl.url == "https://example.com/map.pmtiles"
    assert dl.provider_name == "protomaps"


def test_protomaps_adaptive_zoom_uses_detail_zoom_within_budget():
    dl = ProtomapsDownloader()
    with patch.object(
        dl,
        "_tiles_for_bbox",
        side_effect=lambda bbox, zoom: [object()] * (16 if zoom == 15 else 4),
    ):
        zoom = dl._select_zoom(
            (0, 0, 1, 1),
            "auto",
            {"min_zoom": 0, "max_zoom": 15},
            tile_budget=16,
        )

    assert zoom == 15


def test_protomaps_adaptive_zoom_falls_back_for_large_requests():
    dl = ProtomapsDownloader()
    with patch.object(
        dl,
        "_tiles_for_bbox",
        side_effect=lambda bbox, zoom: [object()] * (17 if zoom == 15 else 5),
    ):
        zoom = dl._select_zoom(
            (0, 0, 1, 1),
            "auto",
            {"min_zoom": 0, "max_zoom": 15},
            tile_budget=16,
        )

    assert zoom == 14


def test_protomaps_adaptive_tile_budget_can_be_overridden():
    dl = ProtomapsDownloader()
    with patch.object(
        dl,
        "_tiles_for_bbox",
        return_value=[object()] * 17,
    ):
        zoom = dl._select_zoom(
            (0, 0, 1, 1),
            "auto",
            {"min_zoom": 0, "max_zoom": 15},
            tile_budget=17,
        )

    assert zoom == 15


@pytest.mark.parametrize("tile_budget", [0, -1, 1.5, True])
def test_protomaps_adaptive_zoom_rejects_invalid_tile_budget(tile_budget):
    dl = ProtomapsDownloader()

    with pytest.raises(
        ValueError,
        match="auto_zoom_tile_budget must be a positive integer",
    ):
        dl._select_zoom(
            (0, 0, 1, 1),
            "auto",
            {"min_zoom": 0, "max_zoom": 15},
            tile_budget=tile_budget,
        )


def test_protomaps_explicit_zoom_overrides_adaptive_selection():
    dl = ProtomapsDownloader()
    with patch.object(dl, "_tiles_for_bbox") as tiles_for_bbox:
        zoom = dl._select_zoom(
            (0, 0, 1, 1),
            14,
            {"min_zoom": 0, "max_zoom": 15},
            tile_budget=16,
        )

    assert zoom == 14
    tiles_for_bbox.assert_not_called()


@pytest.mark.parametrize("zoom", [16, 18])
def test_protomaps_rejects_zoom_above_archive_maximum(zoom):
    dl = ProtomapsDownloader()

    with pytest.raises(ValueError, match="outside archive range 0-15"):
        dl._select_zoom(
            (0, 0, 1, 1),
            zoom,
            {"min_zoom": 0, "max_zoom": 15},
            tile_budget=16,
        )


def test_adjacent_zoom_15_tile_cores_remove_overlap_and_leave_repairable_seam():
    dl = ProtomapsDownloader()
    left_bounds = mercantile.LngLatBbox(west=0, south=0, east=1, north=1)
    right_bounds = mercantile.LngLatBbox(west=1, south=0, east=2, north=1)
    # These independently quantized buffered copies overlap in X. Their tile-core
    # fragments differ by about 0.33 m along the shared boundary.
    left_buffered = LineString([(0.8, 0), (1.2, 1)])
    right_buffered = LineString([(0.8, 0.000003), (1.5, 1.750003)])

    left = dl._clip_road_to_tile_core(left_buffered, left_bounds)
    right = dl._clip_road_to_tile_core(right_buffered, right_bounds)

    assert tuple(left.coords[-1]) == pytest.approx((1.0, 0.5))
    assert tuple(right.coords[0]) == pytest.approx((1.0, 0.500003))
    assert left.intersection(right).is_empty

    projected = gpd.GeoSeries([left, right], crs="EPSG:4326").to_crs("EPSG:3857")
    seam_distance = projected.iloc[0].boundary.geoms[-1].distance(
        projected.iloc[1].boundary.geoms[0]
    )
    assert 0 < seam_distance < 0.5

    normalized = normalize_protomaps_topology(
        gpd.GeoDataFrame(geometry=projected, crs=projected.crs)
    )
    assert normalized.attrs["protomaps_topology"]["undershoots_repaired"] == 2
    assert normalized.geometry.union_all().is_valid


def test_protomaps_get_data_records_selected_fetch_metadata():
    dl = ProtomapsDownloader()
    tile = mercantile.Tile(x=1, y=2, z=14)
    with (
        patch('headless_sidewalkreator.planet_download.protomaps.Reader') as reader,
        patch.object(dl, "_tiles_for_bbox", return_value=[tile]),
    ):
        reader.return_value.header.return_value = {
            "min_zoom": 0,
            "max_zoom": 15,
            "tile_compression": None,
        }
        reader.return_value.get.return_value = None
        gdf = dl.get_data(
            (0, 0, 0.01, 0.01),
            zoom=14,
            tile_workers=1,
            show_progress=False,
        )

    assert gdf.attrs == {
        "provider": "protomaps",
        "zoom": 14,
        "tile_count": 1,
        "tile_workers": 1,
    }


@pytest.mark.parametrize("worker_count", [0, -1, 1.5])
def test_protomaps_rejects_invalid_worker_count(worker_count):
    dl = ProtomapsDownloader()
    tile = mercantile.Tile(x=1, y=2, z=14)
    with (
        patch('headless_sidewalkreator.planet_download.protomaps.Reader') as reader,
        patch.object(dl, "_tiles_for_bbox", return_value=[tile]),
    ):
        reader.return_value.header.return_value = {
            "min_zoom": 0,
            "max_zoom": 15,
            "tile_compression": None,
        }
        with pytest.raises(ValueError, match="tile_workers must be a positive integer"):
            dl.get_data(
                (0, 0, 0.01, 0.01),
                zoom=14,
                tile_workers=worker_count,
                show_progress=False,
            )


@pytest.mark.parametrize("zoom", [16, 18])
def test_unsupported_zoom_is_rejected_before_tile_execution(zoom):
    dl = ProtomapsDownloader()
    with patch(
        'headless_sidewalkreator.planet_download.protomaps.Reader'
    ) as reader:
        reader.return_value.header.return_value = {
            "min_zoom": 0,
            "max_zoom": 15,
            "tile_compression": None,
        }
        with pytest.raises(ValueError, match="outside archive range 0-15"):
            dl.get_data(
                (0, 0, 0.01, 0.01),
                zoom=zoom,
                show_progress=False,
            )

    reader.return_value.get.assert_not_called()


def test_protomaps_defaults_to_at_most_eight_tile_workers():
    dl = ProtomapsDownloader()
    tiles = [mercantile.Tile(x=index, y=2, z=14) for index in range(10)]
    with (
        patch('headless_sidewalkreator.planet_download.protomaps.Reader') as reader,
        patch.object(dl, "_tiles_for_bbox", return_value=tiles),
    ):
        reader.return_value.header.return_value = {
            "min_zoom": 0,
            "max_zoom": 15,
            "tile_compression": None,
        }
        reader.return_value.get.return_value = None
        gdf = dl.get_data(
            (0, 0, 0.01, 0.01),
            zoom=14,
            show_progress=False,
        )

    assert gdf.attrs["tile_workers"] == 8

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
