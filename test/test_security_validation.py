import os
import pytest
from unittest.mock import patch
from headless_sidewalkreator.planet_download.base import is_safe_url, is_safe_release
from headless_sidewalkreator.planet_download.overture import OvertureDownloader
from headless_sidewalkreator.planet_download.protomaps import ProtomapsDownloader

def test_is_safe_url():
    # Valid default domains
    assert is_safe_url("https://overturemapswestus2.blob.core.windows.net/release/v1") is True
    assert is_safe_url("https://data.source.coop/protomaps/tiles.pmtiles") is True
    assert is_safe_url("http://example.com/map") is True

    # Valid allowed suffixes
    assert is_safe_url("https://subdomain.blob.core.windows.net/release") is True
    assert is_safe_url("https://overture.s3.us-west-2.amazonaws.com/data") is True
    assert is_safe_url("https://test.cloudfront.net/dataset") is True

    # Insecure/Local/Loopback
    assert is_safe_url("https://localhost/secrets") is False
    assert is_safe_url("https://127.0.0.1/malicious") is False
    assert is_safe_url("http://192.168.1.1/internal") is False
    assert is_safe_url("http://10.0.0.1/") is False
    assert is_safe_url("http://172.16.0.1/") is False
    assert is_safe_url("https://169.254.169.254/latest/meta-data/") is False

    # Invalid schemes
    assert is_safe_url("file:///etc/passwd") is False
    assert is_safe_url("gopher://localhost") is False
    assert is_safe_url("s3://bucket-name/key") is False
    assert is_safe_url("") is False
    assert is_safe_url("not-a-url") is False

def test_is_safe_url_env_override():
    with patch.dict(os.environ, {"ALLOWED_PLANET_DOMAINS": "trusted.internal, *.mycorp.com"}):
        # Default ones are no longer allowed since env_allowed is set
        assert is_safe_url("https://data.source.coop/protomaps/tiles.pmtiles") is False

        # New ones are allowed
        assert is_safe_url("https://trusted.internal/data") is True
        assert is_safe_url("https://sub.mycorp.com/tiles") is True
        assert is_safe_url("https://mycorp.com/tiles") is True
        assert is_safe_url("https://malicious.com") is False

def test_is_safe_release():
    assert is_safe_release("2026-06-17.0") is True
    assert is_safe_release("latest-v1") is True
    assert is_safe_release("v1.2.3") is True

    # Insecure
    assert is_safe_release("../path/traversal") is False
    assert is_safe_release("..") is False
    assert is_safe_release("release/dir") is False
    assert is_safe_release("release\\dir") is False
    assert is_safe_release("release; rm -rf /") is False

def test_overture_downloader_rejects_insecure_inputs():
    # Insecure base URL
    with pytest.raises(ValueError, match="Insecure Overture base URL"):
        OvertureDownloader(base_url="https://localhost")

    with pytest.raises(ValueError, match="Insecure Overture base URL"):
        OvertureDownloader(base_url="file:///etc/passwd")

    # Insecure release
    with pytest.raises(ValueError, match="Invalid Overture release"):
        OvertureDownloader(release="../traversal")

def test_protomaps_downloader_rejects_insecure_inputs():
    with pytest.raises(ValueError, match="Insecure Protomaps URL"):
        ProtomapsDownloader(url="https://localhost/map.pmtiles")

    with pytest.raises(ValueError, match="Insecure Protomaps URL"):
        ProtomapsDownloader(url="file:///etc/passwd")
