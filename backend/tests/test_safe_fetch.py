import pytest
from app.services.safe_fetch import (
    is_ip_allowed,
    validate_url_and_dns,
    SSRFBlockedError,
    ContentTooLargeError,
    HostThrottle,
    RobotsCache,
)


def test_ip_filtering():
    # Disallowed IPs
    assert not is_ip_allowed("127.0.0.1")
    assert not is_ip_allowed("127.0.1.1")
    assert not is_ip_allowed("::1")
    assert not is_ip_allowed("10.0.0.1")
    assert not is_ip_allowed("172.16.0.5")
    assert not is_ip_allowed("172.31.255.255")
    assert not is_ip_allowed("192.168.1.1")
    assert not is_ip_allowed("169.254.169.254")  # AWS/GCP metadata
    assert not is_ip_allowed("169.254.1.1")
    assert not is_ip_allowed("100.64.0.1")       # Carrier-grade NAT
    assert not is_ip_allowed("0.0.0.0")
    assert not is_ip_allowed("224.0.0.1")       # Multicast
    assert not is_ip_allowed("::ffff:127.0.0.1") # IPv4-mapped IPv6

    # Allowed public IPs
    assert is_ip_allowed("8.8.8.8")
    assert is_ip_allowed("1.1.1.1")
    assert is_ip_allowed("140.82.121.3")


def test_url_validation_schemes_and_ports():
    # Only http and https
    with pytest.raises(SSRFBlockedError, match="Unsupported URL scheme"):
        validate_url_and_dns("file:///etc/passwd")

    with pytest.raises(SSRFBlockedError, match="Unsupported URL scheme"):
        validate_url_and_dns("ftp://example.com/file")

    with pytest.raises(SSRFBlockedError, match="Disallowed destination port"):
        validate_url_and_dns("http://example.com:22/test")

    # Direct private IP access is blocked
    with pytest.raises(SSRFBlockedError, match="Direct IP access"):
        validate_url_and_dns("http://127.0.0.1/admin")

    with pytest.raises(SSRFBlockedError, match="Direct IP access"):
        validate_url_and_dns("http://169.254.169.254/latest/meta-data/")


def test_host_throttle():
    throttle = HostThrottle(default_interval_seconds=0.05)
    # Should run smoothly without errors
    throttle.wait_for_host("example.com")
    throttle.reset()


def test_robots_cache_parsing():
    cache = RobotsCache()
    # When robots.txt allows all
    assert cache.is_allowed("https://public-site.com/news/1")
    cache.clear()
