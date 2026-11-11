"""Ad and tracker domain blocking and article boilerplate filter phrases.
"""
import urllib.parse
from typing import Optional

# Common ad, analytics, and telemetry host patterns
AD_HOSTS = frozenset({
    "doubleclick.net",
    "googlesyndication.com",
    "google-analytics.com",
    "googleadservices.com",
    "adservice.google.com",
    "pagead2.googlesyndication.com",
    "adnxs.com",
    "criteo.com",
    "outbrain.com",
    "taboola.com",
    "scorecardresearch.com",
    "connect.facebook.net",
    "graph.facebook.com",
    "amazon-adsystem.com",
    "rubiconproject.com",
    "pubmatic.com",
    "openx.net",
    "moatads.com",
    "quantserve.com",
    "chartbeat.com",
    "hotjar.com",
    "segment.io",
    "optimizely.com",
    "adroll.com",
    "revcontent.com",
    "mgid.com",
    "zergnet.com",
    "ads-twitter.com",
    "analytics.tiktok.com",
    "bat.bing.com",
    "clarity.ms",
    "adform.net",
    "smartadserver.com",
    "casalemedia.com",
    "bidswitch.net",
    "media.net",
    "indexexchange.com",
    "yandex.ru/ads",
})

# Boilerplate text phrases often found in article bodies to clean out
BOILERPLATE_PHRASES = [
    "sign up for our newsletter",
    "subscribe to our newsletter",
    "follow us on twitter",
    "follow us on x",
    "follow us on facebook",
    "follow us on instagram",
    "all rights reserved",
    "terms of service",
    "privacy policy",
    "cookie policy",
    "advertisement",
    "sponsored content",
    "read more:",
    "related stories:",
    "share this article",
    "leave a comment",
    "click here to subscribe",
    "download our app",
]


def is_ad_host(host_or_url: str) -> bool:
    """Returns True if the host or URL belongs to a known ad/tracking network."""
    if not host_or_url:
        return False

    host = host_or_url.lower()
    if "://" in host:
        try:
            parsed = urllib.parse.urlparse(host)
            host = parsed.netloc or ""
        except Exception:
            pass

    # Strip port if present
    if ":" in host:
        host = host.split(":")[0]

    host = host.strip(".")

    for ad_host in AD_HOSTS:
        if host == ad_host or host.endswith("." + ad_host):
            return True

    return False


def is_boilerplate_text(text: str) -> bool:
    """Returns True if a short paragraph or text block is likely a generic call-to-action or boilerplate."""
    lower = text.strip().lower()
    if len(lower) < 150:
        for phrase in BOILERPLATE_PHRASES:
            if phrase in lower:
                return True
    return False
