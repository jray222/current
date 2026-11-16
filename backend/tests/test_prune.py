from datetime import datetime, timedelta, timezone
from app.database import SessionLocal
from app.models.news import Article, CrawlRun, Source, Vote
from app.services.prune import prune_retention


def test_prune_retention_rules(make_user):
    client, user = make_user("prune_user")
    hid = user["household_id"]

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    with SessionLocal() as db:
        src = Source(
            household_id=hid,
            url="https://prune.site",
            name="Prune Site",
            site_host="prune.site",
        )
        db.add(src)
        db.flush()

        # 1. Unvoted article 2 days old (SHOULD be pruned)
        art_old_unvoted = Article(
            household_id=hid,
            source_id=src.id,
            url="https://prune.site/old-unvoted",
            canonical_url="https://prune.site/old-unvoted",
            url_hash="h-unvoted",
            story_id="s1",
            title="Old Unvoted Article",
            discovered_at=now - timedelta(days=2),
        )

        # 2. Skipped article 2 days old (SHOULD be pruned)
        art_old_skipped = Article(
            household_id=hid,
            source_id=src.id,
            url="https://prune.site/old-skipped",
            canonical_url="https://prune.site/old-skipped",
            url_hash="h-skipped",
            story_id="s2",
            title="Old Skipped Article",
            discovered_at=now - timedelta(days=2),
        )

        # 3. Opened article 2 days old (SHOULD be pruned)
        art_old_opened = Article(
            household_id=hid,
            source_id=src.id,
            url="https://prune.site/old-opened",
            canonical_url="https://prune.site/old-opened",
            url_hash="h-opened",
            story_id="s2b",
            title="Old Opened Article",
            discovered_at=now - timedelta(days=2),
        )

        # 4. Article discovered now, but published 2 days ago (SHOULD be pruned)
        art_old_pub = Article(
            household_id=hid,
            source_id=src.id,
            url="https://prune.site/old-pub",
            canonical_url="https://prune.site/old-pub",
            url_hash="h-old-pub",
            story_id="s2c",
            title="Old Published Article",
            published_at=now - timedelta(days=2),
            discovered_at=now,
        )

        # 5. Fresh unvoted article 12 hours old (MUST BE PRESERVED)
        art_fresh = Article(
            household_id=hid,
            source_id=src.id,
            url="https://prune.site/fresh",
            canonical_url="https://prune.site/fresh",
            url_hash="h-fresh",
            story_id="s-fresh",
            title="Fresh Article",
            published_at=now - timedelta(hours=12),
            discovered_at=now - timedelta(hours=12),
        )

        # 6. Kept article 50 days old (MUST BE PRESERVED)
        art_old_kept = Article(
            household_id=hid,
            source_id=src.id,
            url="https://prune.site/old-kept",
            canonical_url="https://prune.site/old-kept",
            url_hash="h-kept",
            story_id="s3",
            title="Permanent Kept Article",
            discovered_at=now - timedelta(days=50),
        )

        db.add_all([art_old_unvoted, art_old_skipped, art_old_opened, art_old_pub, art_fresh, art_old_kept])
        db.flush()

        # Add votes
        vote_skip = Vote(
            user_id=user["id"],
            household_id=hid,
            article_id=art_old_skipped.id,
            story_id="s2",
            verdict="skip",
            features_raw="{}",
            kept_state="removed",
            created_at=now - timedelta(days=2),
        )
        vote_open = Vote(
            user_id=user["id"],
            household_id=hid,
            article_id=art_old_opened.id,
            story_id="s2b",
            verdict="open",
            features_raw="{}",
            kept_state="removed",
            created_at=now - timedelta(days=2),
        )
        vote_keep = Vote(
            user_id=user["id"],
            household_id=hid,
            article_id=art_old_kept.id,
            story_id="s3",
            verdict="keep",
            features_raw="{}",
            kept_state="read",
            created_at=now - timedelta(days=50),
        )
        db.add_all([vote_skip, vote_open, vote_keep])

        # 7. Old completed crawl run 35 days old (SHOULD be pruned)
        run_old = CrawlRun(
            household_id=hid,
            source_id=src.id,
            trigger="schedule",
            status="ok",
            started_at=now - timedelta(days=35),
            finished_at=now - timedelta(days=35),
        )
        db.add(run_old)
        db.commit()

        kept_id = art_old_kept.id
        fresh_id = art_fresh.id
        unvoted_id = art_old_unvoted.id
        skipped_id = art_old_skipped.id
        opened_id = art_old_opened.id
        old_pub_id = art_old_pub.id

    # Run prune
    with SessionLocal() as db:
        stats = prune_retention(db)
        assert stats["pruned_articles"] == 4
        assert stats["pruned_crawl_runs"] == 1

        # Check records
        assert db.get(Article, unvoted_id) is None
        assert db.get(Article, skipped_id) is None
        assert db.get(Article, opened_id) is None
        assert db.get(Article, old_pub_id) is None
        assert db.get(Article, fresh_id) is not None  # Fresh preserved!
        assert db.get(Article, kept_id) is not None   # Kept preserved!
