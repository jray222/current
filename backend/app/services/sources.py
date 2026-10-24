"""Where knowledge and pictures come from: Wikimedia Commons, Wikipedia and iNaturalist.

Every function returns plain dicts, so the collector and the tests never see HTTP.
Only openly licensed pictures are returned (see `normalize_license`), each with
its author, licence and the page where both can be checked.

All three services ask for a User-Agent that says who is calling (COLLECTOR_CONTACT).
"""
import html
import re
from typing import Optional
from urllib.parse import quote

import httpx

from app.config import settings

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_REST = "https://en.wikipedia.org/api/rest_v1"
INAT_API = "https://api.inaturalist.org/v1"

EXTMETA = "LicenseShortName|LicenseUrl|Artist|Credit|Categories|ImageDescription|ObjectName"


class SourceError(RuntimeError):
    """A source could not be reached or answered with something unusable; the message is safe to show."""


def make_client() -> httpx.Client:
    """The HTTP client. A function of its own so tests can swap in a fake (no network in tests)."""
    return httpx.Client(
        timeout=httpx.Timeout(20.0, connect=10.0),
        follow_redirects=True,
        headers={"User-Agent": f"Dose/0.1 (self-hosted knowledge cards; {settings.COLLECTOR_CONTACT})"},
    )


def _get_json(client: httpx.Client, url: str, params: Optional[dict] = None, source: str = "") -> dict:
    try:
        r = client.get(url, params=params)
    except httpx.HTTPError as e:
        raise SourceError(f"Couldn't reach {source} ({type(e).__name__}).") from e
    if r.status_code == 404:
        return {}
    if r.status_code >= 400:
        raise SourceError(f"{source} answered {r.status_code}.")
    try:
        return r.json()
    except ValueError as e:
        raise SourceError(f"{source} sent something that isn't JSON.") from e


# ------------------------------------------------------------------ licences

def normalize_license(short: str, url: str = "") -> Optional[str]:
    """'CC BY-SA 4.0' / 'cc-by-nc' / 'Public domain' -> a display name, or None when the
    licence doesn't allow showing the picture here (no licence, no-derivatives, GFDL only,
    non-commercial when ALLOW_NONCOMMERCIAL_IMAGES is off)."""
    s = (short or "").strip()
    low = s.lower().replace("_", " ")
    if not low:
        return None
    if low in ("cc0", "cc-0", "cc zero") or low.startswith("cc0") or "public domain" in low or low.startswith("pd"):
        return "CC0" if low.startswith("cc0") or low == "cc-0" else "Public domain"
    m = re.match(r"^cc[\s-]+(by(?:[\s-]+(?:sa|nc|nd))*)(?:[\s-]+([\d.]+))?", low)
    if not m:
        return None
    parts = re.split(r"[\s-]+", m.group(1))
    if "nd" in parts:
        return None
    if "nc" in parts and not settings.ALLOW_NONCOMMERCIAL_IMAGES:
        return None
    name = "CC " + "-".join(p.upper() for p in parts)
    version = m.group(2) or ("4.0" if "inaturalist" in url or not url else "")
    return f"{name} {version}".strip()


def license_url(name: str) -> Optional[str]:
    if name == "CC0":
        return "https://creativecommons.org/publicdomain/zero/1.0/"
    m = re.match(r"^CC (BY(?:-SA|-NC|-NC-SA)?) ([\d.]+)$", name or "")
    if m:
        return f"https://creativecommons.org/licenses/{m.group(1).lower()}/{m.group(2)}/"
    return None


def plain_text(value: str, limit: int = 300) -> str:
    """HTML from Commons metadata ('<a href=..>Name</a>') -> 'Name'."""
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = " ".join(html.unescape(text).split())
    return text[:limit]


# ------------------------------------------------------------------ Commons

def _commons_page(page: dict) -> Optional[dict]:
    info = (page.get("imageinfo") or [None])[0]
    if not info:
        return None
    if not str(info.get("mime", "")).startswith("image/") or info.get("mime") in ("image/svg+xml", "image/gif"):
        return None
    meta = info.get("extmetadata") or {}
    val = lambda k: (meta.get(k) or {}).get("value") or ""  # noqa: E731
    lic = normalize_license(plain_text(val("LicenseShortName"), 60), val("LicenseUrl"))
    if not lic:
        return None
    title = page.get("title", "")
    return {
        "provider": "commons",
        "source_id": title,
        "page_url": info.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/{quote(title.replace(' ', '_'))}",
        "remote_url": info.get("thumburl") or info.get("url"),
        "preview_url": _commons_preview(info),
        "width": info.get("width"),
        "height": info.get("height"),
        "title": re.sub(r"^File:|\.\w+$", "", title),
        "author": plain_text(val("Artist")) or plain_text(val("Credit")) or "Unknown",
        "license": lic,
        "license_url": val("LicenseUrl") or license_url(lic),
        "categories": plain_text(val("Categories"), 2000).lower(),
        "description": plain_text(val("ImageDescription"), 500).lower(),
        "search_rank": page.get("index", 99),
    }


def _commons_preview(info: dict) -> Optional[str]:
    """A ~400px copy, from the sized URL Commons gave (…/1600px-Name.jpg -> …/400px-Name.jpg)."""
    thumb = info.get("thumburl") or ""
    if re.search(r"/\d+px-", thumb):
        return re.sub(r"/\d+px-", "/400px-", thumb)
    return thumb or info.get("url")


def commons_search(client: httpx.Client, query: str, limit: int = 12) -> list[dict]:
    data = _get_json(client, COMMONS_API, {
        "action": "query", "format": "json", "formatversion": "2",
        "generator": "search", "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": "6", "gsrlimit": str(limit),
        "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": str(settings.IMAGE_MAX_PX),
        "iiextmetadatafilter": EXTMETA,
    }, source="Wikimedia Commons")
    pages = (data.get("query") or {}).get("pages") or []
    out = [c for c in (_commons_page(p) for p in pages) if c and c["remote_url"]]
    return sorted(out, key=lambda c: c["search_rank"])


def commons_files(client: httpx.Client, titles: list[str]) -> list[dict]:
    """Specific Commons files ('File:Quercus alba bark.jpg')."""
    if not titles:
        return []
    data = _get_json(client, COMMONS_API, {
        "action": "query", "format": "json", "formatversion": "2", "titles": "|".join(titles[:20]),
        "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": str(settings.IMAGE_MAX_PX),
        "iiextmetadatafilter": EXTMETA,
    }, source="Wikimedia Commons")
    pages = (data.get("query") or {}).get("pages") or []
    return [c for c in (_commons_page(p) for p in pages) if c and c["remote_url"]]


# ------------------------------------------------------------------ Wikipedia

def wikipedia_summary(client: httpx.Client, title: str) -> Optional[dict]:
    """{'extract', 'url', 'title'} for an article (following redirects), or None if there is none."""
    data = _get_json(client, f"{WIKIPEDIA_REST}/page/summary/{quote(title.replace(' ', '_'), safe='')}",
                     source="Wikipedia")
    if not data or data.get("type") == "disambiguation" or not data.get("extract"):
        return None
    return {
        "extract": data["extract"][:1500],
        "url": ((data.get("content_urls") or {}).get("desktop") or {}).get("page")
        or f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}",
        "title": data.get("title") or title,
    }


def wikipedia_lead_image(client: httpx.Client, title: str) -> Optional[str]:
    """The Commons file name of an article's lead picture ('File:Quercus alba.jpg'), if any."""
    data = _get_json(client, WIKIPEDIA_API, {
        "action": "query", "format": "json", "formatversion": "2", "redirects": "1",
        "prop": "pageimages", "piprop": "name", "titles": title,
    }, source="Wikipedia")
    pages = (data.get("query") or {}).get("pages") or []
    name = pages[0].get("pageimage") if pages else None
    return f"File:{name}" if name else None


# ------------------------------------------------------------------ iNaturalist

INAT_LICENSES = {"cc0": "CC0", "cc-by": "CC BY 4.0", "cc-by-sa": "CC BY-SA 4.0",
                 "cc-by-nc": "CC BY-NC 4.0", "cc-by-nc-sa": "CC BY-NC-SA 4.0"}


def _inat_author(attribution: str) -> str:
    """'(c) Jane Doe, some rights reserved (CC BY-NC)' -> 'Jane Doe'."""
    text = re.sub(r"^\(c\)\s*", "", attribution or "", flags=re.I)
    text = re.split(r",\s*(some|all|no) rights reserved", text, flags=re.I)[0]
    text = re.sub(r"\s*\(CC[^)]*\)\s*$", "", text)
    return text.strip()[:300] or "Unknown"


def inat_taxon_photos(client: httpx.Client, scientific_name: str, limit: int = 8) -> list[dict]:
    """The photos iNaturalist's community picked for a species, best first."""
    found = _get_json(client, f"{INAT_API}/taxa", {"q": scientific_name, "per_page": "5"}, source="iNaturalist")
    results = found.get("results") or []
    match = next((t for t in results if (t.get("name") or "").lower() == scientific_name.lower()), None)
    if match is None:
        return []
    data = _get_json(client, f"{INAT_API}/taxa/{int(match['id'])}", source="iNaturalist")
    taxon = (data.get("results") or [{}])[0]
    out = []
    for rank, tp in enumerate(taxon.get("taxon_photos") or []):
        photo = tp.get("photo") or {}
        code = (photo.get("license_code") or "").lower()
        lic = normalize_license(INAT_LICENSES.get(code, ""), "inaturalist") if code in INAT_LICENSES else None
        url = photo.get("url") or ""
        if not lic or not url or "/square." not in url:
            continue
        dims = photo.get("original_dimensions") or {}
        out.append({
            "provider": "inaturalist",
            "source_id": str(photo.get("id")),
            "page_url": f"https://www.inaturalist.org/photos/{photo.get('id')}",
            "remote_url": url.replace("/square.", "/large."),
            "preview_url": url.replace("/square.", "/medium."),
            "width": dims.get("width"),
            "height": dims.get("height"),
            "title": f"{taxon.get('preferred_common_name') or scientific_name} ({scientific_name})",
            "author": _inat_author(photo.get("attribution", "")),
            "license": lic,
            "license_url": license_url(lic),
            "categories": "",
            "description": "",
            "search_rank": rank,
        })
        if len(out) >= limit:
            break
    return out


# ------------------------------------------------------------------ downloads

def download(client: httpx.Client, url: str, max_bytes: int = 25 * 1024 * 1024) -> bytes:
    try:
        with client.stream("GET", url) as r:
            if r.status_code >= 400:
                raise SourceError(f"The picture couldn't be downloaded ({r.status_code}).")
            chunks, size = [], 0
            for chunk in r.iter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise SourceError("The picture is too large.")
                chunks.append(chunk)
            return b"".join(chunks)
    except httpx.HTTPError as e:
        raise SourceError(f"The picture couldn't be downloaded ({type(e).__name__}).") from e
