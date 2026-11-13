from datetime import datetime, timezone
from app.database import SessionLocal
from app.models.news import Article, InterestModel, Source, Vote
from app.services.interest import (
    FEATURE_VERSION,
    extract_features,
    migrate_models,
    predict_proba,
    rank_articles_for_user,
    retrain_user_model,
    update_model_online,
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

        # Reading (open) increases weight
        read_features = {"cat:science": 1.0, "src:nature.com": 1.0}
        model = update_model_online(db, user["id"], user["household_id"], read_features, verdict="open")
        assert model.weights.get("cat:science", 0.0) > 0.0
        assert model.n_votes == 3

        # Dismiss (skip) must NOT penalize sports or change n_votes
        sports_features = {"cat:sports": 1.0}
        model = update_model_online(db, user["id"], user["household_id"], sports_features, verdict="skip")
        assert model.weights.get("cat:sports", 0.0) == 0.0
        assert model.n_votes == 3

        # Dislike ("do not show articles like this") penalizes sports
        model = update_model_online(db, user["id"], user["household_id"], sports_features, verdict="dislike")
        assert model.weights.get("cat:sports", 0.0) < 0.0
        assert model.n_votes == 4
        assert model.bias == 0.0


def test_rank_dismiss_neutral_and_dislike_lowers_or_hides(make_user):
    client, user = make_user("ranker1")
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    with SessionLocal() as db:
        src = Source(
            household_id=user["household_id"],
            url="https://news.example.com",
            name="Example News",
            site_host="news.example.com",
        )
        db.add(src)
        db.flush()

        art_keep = Article(
            household_id=user["household_id"],
            source_id=src.id,
            url="https://news.example.com/ai-1",
            canonical_url="https://news.example.com/ai-1",
            url_hash="r-ai-1",
            story_id="s-ai-1",
            title="Quantum Photonics Breakthrough Announced",
            discovered_at=now,
        )
        art_neutral = Article(
            household_id=user["household_id"],
            source_id=src.id,
            url="https://news.example.com/neutral",
            canonical_url="https://news.example.com/neutral",
            url_hash="r-neutral",
            story_id="s-neutral",
            title="City Council Approves Park Budget",
            discovered_at=now,
        )
        art_dislike = Article(
            household_id=user["household_id"],
            source_id=src.id,
            url="https://news.example.com/crypto-1",
            canonical_url="https://news.example.com/crypto-1",
            url_hash="r-crypto-1",
            story_id="s-crypto-1",
            title="Celebrity Crypto Token Surges Overnight",
            discovered_at=now,
        )
        db.add_all([art_keep, art_neutral, art_dislike])
        db.commit()

        # Dismiss (skip) a crypto article many times: must not hurt ranking of art_dislike vs art_neutral
        dislike_feats = extract_features(art_dislike, source_host="news.example.com")
        for _ in range(5):
            update_model_online(db, user["id"], user["household_id"], dislike_feats, verdict="skip")

        ranked_after_skip = rank_articles_for_user(
            db, user["id"], user["household_id"], [art_neutral, art_dislike], {src.id: src}, {}
        )
        scores_after_skip = {a.id: s for a, s in ranked_after_skip}
        assert scores_after_skip[art_dislike.id] == scores_after_skip[art_neutral.id]

        # Keep & read quantum photonics articles -> boosts art_keep above art_neutral
        keep_feats = extract_features(art_keep, source_host="news.example.com")
        update_model_online(db, user["id"], user["household_id"], keep_feats, verdict="keep")
        update_model_online(db, user["id"], user["household_id"], keep_feats, verdict="open")

        # Dislike celebrity crypto once -> lowers art_dislike below art_neutral
        update_model_online(db, user["id"], user["household_id"], dislike_feats, verdict="dislike")
        ranked = rank_articles_for_user(
            db,
            user["id"],
            user["household_id"],
            [art_dislike, art_neutral, art_keep],
            {src.id: src},
            {},
        )
        assert [a.id for a, _ in ranked] == [art_keep.id, art_neutral.id, art_dislike.id]

        # Repeated dislikes on similar articles eventually hide unliked articles
        for _ in range(4):
            update_model_online(db, user["id"], user["household_id"], dislike_feats, verdict="dislike")
        ranked_hidden = rank_articles_for_user(
            db,
            user["id"],
            user["household_id"],
            [art_dislike, art_neutral, art_keep],
            {src.id: src},
            {},
        )
        ids_remaining = [a.id for a, _ in ranked_hidden]
        assert art_dislike.id not in ids_remaining
        assert art_keep.id in ids_remaining
        assert art_neutral.id in ids_remaining


def test_migrate_models_retrains_without_skip(make_user):
    client, user = make_user("migrator")
    with SessionLocal() as db:
        src = Source(
            household_id=user["household_id"],
            url="https://mig.example.com",
            name="Mig",
            site_host="mig.example.com",
        )
        db.add(src)
        db.flush()
        art = Article(
            household_id=user["household_id"],
            source_id=src.id,
            url="https://mig.example.com/1",
            canonical_url="https://mig.example.com/1",
            url_hash="mig-1",
            story_id="mig-s-1",
            title="Robotics Breakthrough",
            discovered_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.add(art)
        db.flush()
        v = Vote(
            user_id=user["id"],
            household_id=user["household_id"],
            article_id=art.id,
            story_id=art.story_id,
            verdict="skip",
            weight=1.0,
            features_raw='{"tok:robotics": 1.0}',
            feature_version=1,
            kept_state="removed",
        )
        m = InterestModel(
            user_id=user["id"],
            household_id=user["household_id"],
            weights_raw='{"tok:robotics": -0.5}',
            g2_raw='{"tok:robotics": 2.0}',
            bias=-0.2,
            bias_g2=2.0,
            n_votes=1,
            feature_version=1,
            muted_raw="[]",
        )
        db.add_all([v, m])
        db.commit()

        migrated = migrate_models(db)
        assert migrated >= 1
        refreshed = db.get(InterestModel, user["id"])
        assert refreshed.feature_version == FEATURE_VERSION
        assert refreshed.weights == {}
        assert refreshed.bias == 0.0
        assert refreshed.n_votes == 0
