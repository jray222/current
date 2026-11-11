"""URL canonicalization, hash generation, title tokenization, and story clustering.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import re
import urllib.parse
import uuid
from typing import Optional
from sqlalchemy.orm import Session
from app.models.news import Article

# Tracking parameters to strip during URL canonicalization
TRACKING_PARAMS = frozenset({
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "fbclid",
    "gclid",
    "gbraid",
    "wbraid",
    "mc_eid",
    "mc_cid",
    "ref",
    "ref_src",
    "source",
    "yclid",
    "_hsenc",
    "_hsmi",
    "igshid",
    "mkt_tok",
    "msclkid",
    "twclid",
})

STOPWORDS = frozenset({
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "aren't", "as", "at", "be", "because", "been", "before", "being", "below", "between", "both",
    "but", "by", "can't", "cannot", "could", "couldn't", "did", "didn't", "do", "does", "doesn't",
    "doing", "don't", "down", "during", "each", "few", "for", "from", "further", "had", "hadn't",
    "has", "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i", "i'd", "i'll",
    "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself", "let's",
    "me", "more", "most", "mustn't", "my", "myself", "no", "nor", "not", "of", "off", "on",
    "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own",
    "same", "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some",
    "such", "than", "that", "that's", "the", "their", "theirs", "them", "themselves", "then",
    "there", "there's", "these", "they", "they'd", "they'll", "they're", "they've", "this",
    "those", "through", "to", "too", "under", "until", "up", "very", "was", "wasn't", "we",
    "we'd", "we'll", "we're", "we've", "were", "weren't", "what", "what's", "when", "when's",
    "where", "where's", "which", "while", "who", "who's", "whom", "why", "why's", "with",
    "won't", "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your",
    "yours", "yourself", "yourselves",
})


def canonical_url(url: str) -> str:
    """Normalizes a URL by stripping tracking parameters, lowercasing host, removing
    fragments, and normalizing trailing slashes.
    """
    if not url:
        return ""

    parsed = urllib.parse.urlsplit(url.strip())
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()

    # Strip default ports
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    path = parsed.path or "/"
    # Normalize trailing slash: keep root '/', strip trailing slash on sub-paths
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # Filter out tracking query params and sort remainder
    query_params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    filtered_params = [
        (k, v) for k, v in query_params if k.lower() not in TRACKING_PARAMS
    ]
    filtered_params.sort(key=lambda kv: kv[0])
    query = urllib.parse.urlencode(filtered_params)

    # Omit fragment completely
    return urllib.parse.urlunsplit((scheme, netloc, path, query, ""))


def url_hash(url: str) -> str:
    """Returns SHA256 hex digest of the canonicalized URL."""
    c_url = canonical_url(url)
    return hashlib.sha256(c_url.encode("utf-8")).hexdigest()


def tokenize_title(title: str) -> set[str]:
    """Splits a title into a set of lowercased, non-stopword tokens."""
    if not title:
        return set()
    cleaned = re.sub(r"[^\w\s]", " ", title.lower())
    tokens = {
        word for word in cleaned.split()
        if len(word) >= 2 and word not in STOPWORDS
    }
    return tokens


def jaccard_similarity(tokens_a: set[str], tokens_b: set[str]) -> float:
    """Calculates Jaccard index between two token sets."""
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union if union > 0 else 0.0


def find_or_create_story_id(
    db: Session,
    household_id: int,
    title: str,
    reference_time: Optional[datetime] = None,
    threshold: float = 0.6,
    window_hours: int = 48,
) -> str:
    """Finds an existing story_id within window_hours if title similarity >= threshold,
    or generates a new unique story_id.
    """
    if reference_time is None:
        reference_time = datetime.now(timezone.utc).replace(tzinfo=None)
    elif reference_time.tzinfo is not None:
        reference_time = reference_time.astimezone(timezone.utc).replace(tzinfo=None)

    tokens = tokenize_title(title)
    if not tokens:
        return uuid.uuid4().hex[:16]

    since = reference_time - timedelta(hours=window_hours)
    until = reference_time + timedelta(hours=window_hours)

    candidates = (
        db.query(Article.story_id, Article.title)
        .filter(
            Article.household_id == household_id,
            Article.discovered_at >= since,
            Article.discovered_at <= until,
        )
        .order_by(Article.id.desc())
        .limit(200)
        .all()
    )

    best_score = 0.0
    best_story_id = None

    for s_id, cand_title in candidates:
        cand_tokens = tokenize_title(cand_title)
        score = jaccard_similarity(tokens, cand_tokens)
        if score >= threshold and score > best_score:
            best_score = score
            best_story_id = s_id

    if best_story_id:
        return best_story_id

    return uuid.uuid4().hex[:16]
