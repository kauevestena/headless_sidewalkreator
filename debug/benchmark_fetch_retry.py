import time
import logging
from unittest.mock import MagicMock, patch
import geopandas as gpd

from headless_sidewalkreator.osm_fetch import get_osm_data

logging.basicConfig(level=logging.INFO)

def benchmark_retry_blocking():
    print("--- Establishing Performance Baseline for OSM Fetch Retry Sleeps ---")

    # 1. Baseline: default blocking retry sleep
    start_time = time.perf_counter()

    mock_ox = MagicMock()
    mock_ox.settings.requests_timeout = 60
    mock_ox.settings.max_query_area_size = 50000 * 50000

    # Simulate failures on all attempts to force full retry sleep (with max_retries=1)
    mock_ox.features_from_bbox.side_effect = Exception("OSM Overpass API Timeout")

    with patch('headless_sidewalkreator.osm_fetch.ox', mock_ox):
        _ = get_osm_data((0, 0, 1, 1), max_retries=1)

    baseline_duration = time.perf_counter() - start_time
    print(f"Baseline (blocking time.sleep, 1 retry): {baseline_duration:.4f} seconds")

    # 2. Optimized: non-blocking / bypassed custom sleep_fn
    start_time = time.perf_counter()

    mock_ox_opt = MagicMock()
    mock_ox_opt.settings.requests_timeout = 60
    mock_ox_opt.settings.max_query_area_size = 50000 * 50000
    mock_ox_opt.features_from_bbox.side_effect = Exception("OSM Overpass API Timeout")

    with patch('headless_sidewalkreator.osm_fetch.ox', mock_ox_opt):
        # We pass a custom sleep_fn that executes instantly (non-blocking)
        _ = get_osm_data((0, 0, 1, 1), max_retries=1, sleep_fn=lambda seconds: None)

    optimized_duration = time.perf_counter() - start_time
    print(f"Optimized (custom non-blocking sleep_fn, 1 retry): {optimized_duration:.4f} seconds")

    improvement_factor = baseline_duration / max(optimized_duration, 1e-9)
    print(f"Speed boost / reduction in blocking delay: {improvement_factor:.1f}x faster")
    print(f"Time saved: {baseline_duration - optimized_duration:.4f} seconds")

if __name__ == "__main__":
    benchmark_retry_blocking()
