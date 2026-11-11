from datetime import datetime, timezone
from app.database import SessionLocal
from app.models.news import Article, InterestModel, Vote
from app.services.interest import (
    extract_features,
    predict_proba,
    update_model_online,
    retrain_user_model,
    explain_prediction,
)


def test_extract_features():
    art = Article(
        title="Revolutionary AI Models Transform Open Source Research",
        author="Ada Lovelace",
        published_at=datetime(2026, 11, 10, 14, 0, 0),
    )
    art.feed_tags = ["AI", "OpenSource"]

    features = extract_features(art, source_host="nature.com", category_key="tech")
    assert "src:nature.com" in features
    assert "cat:tech" in features
    assert "author:ada lovelace" in features
    assert "tag:ai" in features
    assert "tag:opensource" in features
    assert "tok:revolutionary" in features
    assert "tok:models" in features
    assert "tod:3" in features  # 14 // 4 = 3


def test_predict_proba_and_muting():
    weights = {"cat:tech": 1.5, "cat:sports": -1.5}
    bias = 0.0

    p_tech = predict_proba(weights, bias, {"cat:tech": 1.0})
    assert p_tech > 0.7

    p_sports = predict_proba(weights, bias, {"cat:sports": 1.0})
    assert p_sports < 0.3

    # Muting
    p_muted = predict_proba(weights, bias, {"cat:tech": 1.0}, muted=["tech"])
    assert p_muted == 0.0


def test_online_update_adagrad(make_user):
    client, user = make_user("learner1")

    features = {"cat:tech": 1.0, "src:theverge.com": 1.0}

    with SessionLocal() as db:
        # Initial prediction is neutral 0.5
        model = update_model_online(db, user["id"], user["household_id"], features, verdict="keep")
        assert model.weights.get("cat:tech", 0.0) > 0.0
        assert model.weights.get("src:theverge.com", 0.0) > 0.0
        assert model.n_votes == 1

        # Second keep further increases weight
        model = update_model_online(db, user["id"], user["household_id"], features, verdict="keep")
        assert model.weights.get("cat:tech", 0.0) > 0.05
        assert model.n_votes == 2

        # Skip vote penalizes sports
        sports_features = {"cat:sports": 1.0}
        model = update_model_online(db, user["id"], user["household_id"], sports_features, verdict="skip")
        assert model.weights.get("cat:sports", 0.0) < 0.0
