"""
Unit tests for the SSRF blocklist logic in app.services.url_preview.
No network or DB required -- these test the pure validation function.
"""
import pytest

from app.services.url_preview import SSRFBlockedError, _validate_url_or_raise


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://127.0.0.1:8000/",
        "http://localhost/",
        "http://10.0.0.5/",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "file:///etc/passwd",
        "ftp://example.com/",
    ],
)
def test_blocked_urls_raise(url):
    with pytest.raises(SSRFBlockedError):
        _validate_url_or_raise(url)


def test_public_url_is_allowed():
    # example.com resolves to public IPs; this should not raise.
    result = _validate_url_or_raise("https://example.com")
    assert result == "https://example.com"
