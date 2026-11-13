"""Adaptive user interest learning using AdaGrad logistic regression with sparse features,
online updates, recency decay, and transparent explanations.
"""
from datetime import datetime, timezone
import math
from typing import Optional, Any
from sqlalchemy.orm import Session

from app.models.news import Article, Category, InterestModel, Source, Vote
from app.services.dedupe import tokenize_title

FEATURE_VERSION = 2
LEARNING_RATE = 0.1
DISLIKE_LEARNING_RATE = 0.3
EPSILON = 1e-4
L2_REG = 1e-4
HIDE_DISLIKE_THRESHOLD = 0.20

TRIAGED_VERDICTS = ("keep", "skip", "dislike")


def _verdict_spec(verdict: str, weight: float = 1.0) -> Optional[tuple[float, float, float]]:
    """Maps a vote verdict to (target y, sample_weight, learning_rate), or None if neutral."""
    if verdict == "keep":
        return (1.0, 1.0 * weight, LEARNING_RATE)
    if verdict == "open":
        return (1.0, 0.5 * weight, LEARNING_RATE)
    if verdict == "dislike":
        return (0.0, 1.0 * weight, DISLIKE_LEARNING_RATE)
    # "skip" (dismiss) and unknown verdicts do not alter ranking
    return None


def _is_muted(features: dict[str, float], muted: Optional[list[str]]) -> bool:
    """Returns True if any extracted feature matches a user-muted term."""
    if not muted:
        return False
    muted_set = {m.lower().strip() for m in muted if m.strip()}
    if not muted_set:
        return False
    for f in features:
        f_lower = f.lower()
        for m in muted_set:
            if m in f_lower:
                return True
    return False


def extract_features(
    article: Article,
    source_host: Optional[str] = None,
    category_key: Optional[str] = None,
) -> dict[str, float]:
    """Extracts sparse binary features from an article (source, category, tags, author, title tokens, time)."""
    features: dict[str, float] = {}

    # 1. Source host feature
    if source_host:
        clean_host = source_host.lower().removeprefix("www.")
        features[f"src:{clean_host}"] = 1.0

    # 2. Category feature
    if category_key:
        features[f"cat:{category_key.lower()}"] = 1.0

    # 3. Author feature
    if article.author:
        clean_author = article.author.strip().lower()[:50]
        if clean_author:
            features[f"author:{clean_author}"] = 1.0

    # 4. Feed tags
    for tag in article.feed_tags:
        clean_tag = tag.strip().lower()[:40]
        if clean_tag:
            features[f"tag:{clean_tag}"] = 1.0

    # 5. Informative title tokens
    tokens = tokenize_title(article.title)
    for tok in tokens:
        features[f"tok:{tok}"] = 1.0

    # 6. Temporal features
    ref_time = article.published_at or article.discovered_at or datetime.now(timezone.utc)
    hour = ref_time.hour
    features[f"tod:{hour // 4}"] = 1.0  # 6 time-of-day buckets (4 hours each)

    if ref_time.weekday() >= 5:
        features["time:weekend"] = 1.0

    return features


def predict_proba(
    weights: dict[str, float],
    bias: float,
    features: dict[str, float],
    muted: Optional[list[str]] = None,
) -> float:
    """Calculates predicted probability of interest in [0.0, 1.0] using logistic sigmoid."""
    if _is_muted(features, muted):
        return 0.0

    # Linear combination
    z = bias
    for k, v in features.items():
        w = weights.get(k, 0.0)
        z += w * v

    # Sigmoid with overflow clamping
    if z < -15.0:
        return 0.0
    if z > 15.0:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def get_or_create_model(db: Session, user_id: int, household_id: int) -> InterestModel:
    """Fetches the user's InterestModel or creates an initial prior."""
    model = db.get(InterestModel, user_id)
    if model is None:
        model = InterestModel(
            user_id=user_id,
            household_id=household_id,
            weights_raw="{}",
            g2_raw="{}",
            bias=0.0,
            bias_g2=1.0,
            n_votes=0,
            feature_version=FEATURE_VERSION,
            muted_raw="[]",
        )
        db.add(model)
        db.commit()
        db.refresh(model)
    return model


def _apply_adagrad_step(
    weights: dict[str, float],
    g2: dict[str, float],
    bias: float,
    features: dict[str, float],
    y: float,
    sample_weight: float,
    lr: float,
) -> None:
    """Applies a single AdaGrad logistic regression step to feature weights in place.

    Bias is kept anchored (0.0) so positive-only keep/read feedback boosts matching
    topics relative to neutral articles without saturating unseen articles near 1.0.
    """
    p = predict_proba(weights, bias, features)
    err = (p - y) * sample_weight

    for k, v in features.items():
        w_curr = weights.get(k, 0.0)
        g_i = err * v + L2_REG * w_curr
        g2_curr = g2.get(k, 1.0) + g_i * g_i
        g2[k] = g2_curr
        weights[k] = round(w_curr - (lr / (math.sqrt(g2_curr) + EPSILON)) * g_i, 6)


def update_model_online(
    db: Session,
    user_id: int,
    household_id: int,
    features: dict[str, float],
    verdict: str,
    weight: float = 1.0,
) -> InterestModel:
    """Performs an online AdaGrad gradient step based on a user vote."""
    model = get_or_create_model(db, user_id, household_id)

    spec = _verdict_spec(verdict, weight)
    if spec is None or not features:
        return model
    y, sample_weight, lr = spec

    weights = model.weights
    g2 = model.g2

    _apply_adagrad_step(weights, g2, 0.0, features, y, sample_weight, lr)

    model.weights = weights
    model.g2 = g2
    model.bias = 0.0
    model.bias_g2 = 1.0
    model.feature_version = FEATURE_VERSION
    model.n_votes += 1
    db.commit()
    db.refresh(model)
    return model


def retrain_user_model(db: Session, user_id: int, epochs: int = 5) -> Optional[InterestModel]:
    """Full batch retrain over historical votes for the user."""
    votes = (
        db.query(Vote)
        .filter(Vote.user_id == user_id)
        .order_by(Vote.id.asc())
        .all()
    )

    model = db.get(InterestModel, user_id)
    if not model and votes:
        model = get_or_create_model(db, user_id, votes[0].household_id)
    elif not model:
        return None

    weights: dict[str, float] = {}
    g2: dict[str, float] = {}
    trained_count = 0

    for epoch in range(epochs):
        for v in votes:
            features = v.features
            if not features:
                continue

            spec = _verdict_spec(v.verdict, v.weight)
            if spec is None:
                continue
            y, sw, lr = spec
            if epoch == 0:
                trained_count += 1

            _apply_adagrad_step(weights, g2, 0.0, features, y, sw, lr)

    model.weights = {k: round(v, 6) for k, v in weights.items() if abs(v) > 1e-4}
    model.g2 = g2
    model.bias = 0.0
    model.bias_g2 = 1.0
    model.n_votes = trained_count
    model.feature_version = FEATURE_VERSION
    db.commit()
    db.refresh(model)
    return model


def migrate_models(db: Session) -> int:
    """Retrains models built under older learning rules so legacy skip votes no longer penalize ranking."""
    outdated = (
        db.query(InterestModel)
        .filter(InterestModel.feature_version < FEATURE_VERSION)
        .all()
    )
    for model in outdated:
        retrain_user_model(db, model.user_id)
    return len(outdated)


def explain_prediction(
    weights: dict[str, float],
    bias: float,
    features: dict[str, float],
) -> list[tuple[str, float]]:
    """Returns the top contributing features and their weighted impact."""
    impacts = []
    for k, v in features.items():
        w = weights.get(k, 0.0)
        impact = w * v
        if abs(impact) >= 0.01:
            impacts.append((k, round(impact, 3)))
    impacts.sort(key=lambda item: abs(item[1]), reverse=True)
    return impacts[:5]


def rank_articles_for_user(
    db: Session,
    user_id: int,
    household_id: int,
    articles: list[Article],
    sources_by_id: dict[int, Source],
    categories_by_id: dict[int, Category],
) -> list[tuple[Article, float]]:
    """Scores and ranks candidate articles, hiding muted or strongly disliked stories
    and blending predicted interest with exponential recency decay (48h half-life).
    """
    model = get_or_create_model(db, user_id, household_id)
    weights = model.weights
    bias = model.bias
    muted = model.muted

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ranked: list[tuple[Article, float]] = []

    for art in articles:
        src = sources_by_id.get(art.source_id)
        cat = categories_by_id.get(art.category_id)

        features = extract_features(
            art,
            source_host=src.site_host if src else None,
            category_key=cat.key if cat else None,
        )

        if _is_muted(features, muted):
            continue

        p = predict_proba(weights, bias, features)
        if p < HIDE_DISLIKE_THRESHOLD:
            continue

        # 48-hour half-life exponential decay on age
        age_hours = 0.0
        ref_time = art.published_at or art.discovered_at
        if ref_time:
            age_hours = max(0.0, (now - ref_time).total_seconds() / 3600.0)
        decay = math.pow(0.5, age_hours / 48.0)

        # Combined score: 40% base prediction + 60% fresh prediction
        combined_score = p * (0.4 + 0.6 * decay)
        ranked.append((art, combined_score))

    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked
