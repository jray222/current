# AGENTS.md: everything a coding agent needs to build and change Current

Read this file first. It is meant to be enough to make changes **without exploring the codebase**: it describes the architecture, product decisions, data model, safe-fetch constraints, learning model, frontend layout, invariants, and build phases. Visual rules are in `docs/DESIGN_SYSTEM.md`; user docs are in `README.md`.

---

## 1. What Current is

A self-hosted personal news aggregator and distraction-free reader that learns what you like, owned by John (GitHub `jray222`). Port **5734**, Docker image `ghcr.io/jray222/current`, repo `jray222/current`. Sibling apps: `jray222/staple` (5732, the cleanest base), `jray222/glance` (5731), and `jray222/dose` (5733). Auth, households, invites, 2FA, server keys, and Settings screens match this stack.

Current crawls news sites via RSS/Atom feeds, plain HTML parsing, or headless Playwright rendering. It presents articles in an **editorial digital newspaper layout** (Front Page with Top Stories lead hero and category sections: World, Tech, Politics, Business, etc.). Every article row in the list can be triaged like an email inbox on mobile:
- **Swipe right:** Keep (saves to your Kept reading list, trains the model positively).
- **Swipe left:** Skip / Dismiss (collapses and removes the row from the unread feed, trains the model negatively).
- **Tap:** Opens the distraction-free, ad-free in-app reader.

Full article text is retrieved **on demand** through an intelligent fetch ladder (HTTP $\rightarrow$ AMP $\rightarrow$ Playwright with ad blocking) without ever bypassing logins or paywalls.

---

## 2. John's product decisions (do not reverse without asking him)

1. **Sources, categories, and articles belong to a household** and are crawled once for everyone in it. **Votes, the interest model, read states, and the Kept list belong to each person.**
2. **Editorial news layout with email-style list swiping:** Front page mirrors a respected news site layout with categorized sections. Swiping operates per-row like mobile email, not as a single-card Tinder stack.
3. Fetching order per source is **rss $\rightarrow$ html $\rightarrow$ browser**. The mode is detected when a source is added and stored on it. The owner can override it.
4. **Crawling is light; full text is on demand.** Crawling stores metadata only (title, summary, image, date, author). Full text is grabbed when requested (on open, on keep, or on crawl for sites configured that way).
5. **The reader never bypasses paywalls or logins.** No cookies, no logged-in sessions, no paywall tricks. If only part of an article is free, Current shows that part, marks it "Only part of this article is free", and links to the source.
6. **Everything works with zero API keys.** The interest model is pure Python AdaGrad running locally. Claude is used for one thing only: categorizing articles from mixed-topic sources into categories when enabled.
7. **Be polite to sites:** respect `robots.txt` (`RESPECT_ROBOTS=true`), send a clear User-Agent (`Current/0.1`), wait at least 1 second between requests to the same host (`CRAWL_DELAY_SECONDS=1.0`), use conditional GET for feeds, and cap crawls at `MAX_NEW_PER_SOURCE` (25) article pages per crawl.
8. **Fetching user-supplied URLs is the primary security risk.** Every outbound request, including every request Playwright makes, goes through the SSRF guard in `services/safe_fetch.py`. Nothing else may fetch a URL. `feedparser` and `trafilatura` are only ever given **bytes or strings, never a URL**.
9. Retain unkept articles for `RETENTION_DAYS` (14). Kept articles and their full text stay until removed. Each vote stores a snapshot of its features, so retention pruning never degrades the interest model.
10. Docker image runs on **arm64 and amd64**, with one uvicorn worker and an in-process priority job queue. Daily base-image check republishes when `python:3.12-slim` updates. No Dependabot.
11. Mobile first (verify at 390px wide and desktop). Runs behind Cloudflare.
12. **Security audits (`cloudflare/security-audit-skill`):**
    - Local global skill path: `~/.gemini/config/skills/security-audit/SKILL.md` (backed by repo at `~/.gemini/config/skills/.security-audit-repo`).
    - Sync skill before starting an audit:
      `git -C ~/.gemini/config/skills/.security-audit-repo pull --ff-only origin main && cp -r ~/.gemini/config/skills/.security-audit-repo/skills/security-audit/* ~/.gemini/config/skills/security-audit/`
    - Proactively recommend a security audit after major updates or changes to `safe_fetch.py`, `browser.py`, `crawler.py`, `fulltext.py`, auth, `deps.py`, `_scoping.py`, or `llm.py`.
    - Run subagents on **Gemini Flash** (`Model: "flash"`).
    - Store audit runs outside the repo at `~/security-audit-skill/current/run-<N>/`.

---

## 3. Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2 (classic `Column` style), Pydantic 2, pydantic-settings, httpx, Pillow, anthropic SDK, SQLite, no Alembic.
  - New libraries: `feedparser` (RSS/Atom), `selectolax` (HTML parser), `trafilatura` (article extraction), `playwright` (sync Chromium runner).
- **Frontend:** React 19, Vite, Tailwind 3, plain JSX, axios, lucide-react, Fraunces + Nunito Sans. No router library, no state library.
- **Build:** Single multi-arch Docker container on port **5734**.

---

## 4. File map

```
AGENTS.md, CLAUDE.md, README.md, docs/DESIGN_SYSTEM.md
Dockerfile                    node:22-slim frontend build -> python:3.12-slim runtime with Playwright Chromium
docker-compose.yml / .build.yml, run.sh, .github/workflows/*

backend/app/
  main.py                     lifespan: create_all -> migrations -> keys.load -> categories.seed_all -> crawler.resume -> fulltext.resume -> crawl_schedule.start
  config.py, database.py, migrations.py, deps.py, frontend.py, security.py, rate_limit.py, schemas_auth.py
  cli.py                      crawl <source-id|all> [--force] | fulltext <article-id> [--browser] | prune | retrain <user> | clear-lock | reset-password
  models/user.py, household.py, invite.py, runtime_config.py
  models/news.py              Category, Source, Article, CrawlRun, Vote, InterestModel
  routers/auth.py, settings.py
  routers/_scoping.py         household ownership isolation helper: get_owned_or_404
  routers/sources.py          sources, categories, crawl endpoints
  routers/feed.py             frontpage edition, category feeds, votes, undo, kept, reader, full text, thumbs
  services/keys.py, lockout.py, invites.py, households.py, password_resets.py, ai.py
  services/job_queue.py       in-process priority queue: HIGH=0 (reader fetch), NORMAL=5 (crawls), LOW=9 (pruning, ai)
  services/safe_fetch.py      outbound network doorway: SSRF guard, redirect validator, robots.txt, host throttle
  services/feeds.py           feed discovery & parsing (feedparser on bytes)
  services/pages.py           article link discovery & metadata extraction (JSON-LD, OpenGraph, fallback heuristics)
  services/browser.py         Playwright Chromium runner with ad/tracker blocklist and cookie overlay cleaner
  services/adblock.py         built-in ad host blocklist (~150 domains) & boilerplate phrase regexes
  services/fulltext.py        on-demand full article extraction ladder: HTTP -> AMP -> Playwright
  services/crawler.py         source checker & crawler worker
  services/dedupe.py          canonical URL normalizer & story clustering (title token Jaccard similarity)
  services/categories.py      household categories seeder & keyword categorizer
  services/interest.py        personal interest features, AdaGrad logistic regression model, ranking
  services/crawl_schedule.py  daily scheduled crawler thread
  services/images.py          thumbnail processing (Pillow, JPEG q80, max 720px)
  services/prune.py           retention pruner for unkept articles & thumbs
  services/llm.py             optional batch categorization with Claude
  tests/                      test_auth, test_invites, test_signin_and_keys, test_safe_fetch, test_feeds, test_pages,
                              test_crawler, test_dedupe, test_fulltext, test_interest, test_feed_api, test_sources_api,
                              test_schedule, test_prune, test_job_queue

frontend/src/
  main.jsx, App.jsx, api.js, appUpdate.js, index.css, context/
  lib/router.js, lib/theme.js, lib/useSwipeRow.js (touch gesture physics for email-style row swiping)
  components/Shell.jsx        mobile bottom tabs (Today, Kept, Sources, More), desktop side nav
  components/Brand.jsx        newspaper logo with electric current bolt & Fraunces wordmark
  components/ui.jsx, Modal.jsx, AuthGateway.jsx, AuthImage.jsx, ErrorBoundary.jsx, ThemeToggle.jsx, settings/*
  components/news/LeadStoryCard.jsx      prominent editorial lead hero card for #1 ranked story
  components/news/ArticleRow.jsx         email-style swipeable list item (Keep on right swipe, Skip on left swipe)
  components/news/CategorySection.jsx    section container for category groups
  components/news/CategoryNav.jsx        sticky category filter & jump bar
  components/news/SourceSheet.jsx        add/edit source modal with auto-detection & full-text grab mode
  components/news/CrawlStatus.jsx        live crawl progress line with volt pulse
  components/news/TextStatus.jsx         full-text status chip (Ready, Getting it…, Partial, Couldn't get it)
  components/news/ArticleBody.jsx        safe React element renderer for article blocks (never raw HTML)
  components/news/UndoToast.jsx          floating bottom toast for 1-tap undo of keeps/skips
  pages/TodayPage.jsx, KeptPage.jsx, ReaderPage.jsx, SourcesPage.jsx, MorePage.jsx, SettingsPage.jsx
```

---

## 5. Data model (`backend/app/models/news.py`)

- **Category** `categories`: `id`, `household_id`, `key` (slug), `label`, `icon` (lucide name), `keywords` JSON `[str]`, `sort_order`, `hidden` (0/1). Default seed: Top stories, World, U.S., Politics, Business, Tech, Science, Health, Sports, Local, Culture, General (protected).
- **Source** `sources`: `id`, `household_id`, `url`, `name`, `site_host`, `favicon_url`, `fetch_mode` (`rss|html|browser`), `feed_url`, `listing_url`, `link_pattern`, `link_selector`, `category_id` (nullable = Mixed), `fetch_pages` (0/1), `enabled` (0/1), `etag`, `last_modified`, `crawl_status` (`idle|queued|running|done|error`), `last_crawl_at`, `last_new_count`, `last_error`, `fail_streak`, `created_by`, timestamps.
  - Full-text settings: `text_when` (`open|keep|crawl`), `text_method` (`auto|http|browser`), `text_block_ads` (0/1), `text_last_method`, `text_selector`.
- **Article** `articles`: `id`, `household_id`, `source_id`, `category_id`, `url` (canonical), `url_hash`, `amp_url`, `story_id`, `title`, `summary`, `author`, `published_at`, `discovered_at`, `image_remote_url`, `thumb_path`, `feed_tags` JSON, `lang`.
  - Full text fields: `text_blocks` JSON `[{"t": "p|h2|h3|quote|li|pre", "x": "text"}]`, `text_status` (`none|queued|running|ok|partial|failed|blocked`), `text_method`, `text_pages`, `word_count`, `text_error`, `text_fetched_at`.
- **CrawlRun** `crawl_runs`: `id`, `household_id`, `source_id`, `trigger` (`schedule|manual|add`), `mode_used`, `status`, `started_at`, `finished_at`, `found`, `new`, `skipped_robots`, `message`. Last 20 kept per source.
- **Vote** `votes`: unique (`user_id`, `article_id`), `story_id`, `verdict` (`keep|skip|open`), `weight`, `features` JSON (snapshot), `feature_version`, `kept_state` (`unread|read|removed`), `created_at`, `updated_at`.
- **InterestModel** `interest_models`: `user_id` (PK), `weights` JSON, `g2` JSON, `bias`, `bias_g2`, `n_votes`, `feature_version`, `muted` JSON `[str]`, `updated_at`.

---

## 6. Safe Fetch & SSRF Protection (`services/safe_fetch.py`)

- `make_client()`: httpx Client with User-Agent `Current/0.1 (+PUBLIC_URL; CRAWLER_CONTACT)`.
- `check_url(url)`: Validates scheme (`http|https`), ports (80, 443, or `ALLOWED_PORTS`), resolves host addresses via `socket.getaddrinfo`, and strictly rejects private, loopback (`127.0.0.1`, `::1`), link-local (`169.254.169.254`), multicast, and CGNAT IP spaces unless `ALLOW_PRIVATE_SOURCES=true`.
- `get()`: Enforces `check_url()` on the destination and on **every redirect hop** (up to 5 redirects). Streams bodies and aborts when exceeding `max_bytes` (5 MB default).
- `robots_allowed()`: Evaluates `robots.txt` per host with a 6-hour TTL cache.
- `HostThrottle`: Enforces `CRAWL_DELAY_SECONDS` (1.0s) spacing between requests to the same origin. Full-text fetches utilize a separate throttle so reading is not delayed behind crawl intervals.
- *Known limitation:* DNS rebinding gap exists between resolution and socket connection. Documented and accepted for personal deployment.

---

## 7. Crawl Ladder & Full Text on Demand (`services/fulltext.py`)

- Crawl order per source: **rss $\rightarrow$ html $\rightarrow$ browser**.
- Full-text grab ladder for on-demand reads:
  1. **HTTP:** Plain HTTP fetch parsed via `selectolax` + `trafilatura`.
  2. **AMP:** If an AMP URL is present on the same origin, fetch and extract the AMP version.
  3. **Playwright Browser:** Headless Chromium rendering with built-in ad/tracker network routing blocks (`adblock.py`) and cookie overlay cleanup.
- Stitched multi-page articles followed up to `MAX_ARTICLE_PAGES` (5) via `next_page_url`.
- Content cleaned into native text blocks (`p`, `h2`, `h3`, `quote`, `li`, `pre`), stripping boilerplate lines ("Advertisement", "Sign up for newsletter"). Never stores or renders raw HTML.
- Priority queue: User reading fetch = `HIGH` (priority 0). Routine crawls = `NORMAL` (priority 5). Background tasks = `LOW` (priority 9).

---

## 8. Local Interest Learning Model (`services/interest.py`)

- **Features (`FEATURE_VERSION = 1`):** Title tokens (1.0), title bigrams (0.7), summary tokens (0.4), source ID (1.0), category (1.0), host (0.5), author (0.5). Features are computed strictly from crawl metadata, never full text.
- **Model:** Online AdaGrad logistic regression:
  - Keep $\rightarrow y = 1$, weight 1.0.
  - Skip $\rightarrow y = 0$, weight 1.0.
  - Reader $\ge 60\%$ scrolled $\rightarrow y = 1$, weight 0.5.
  - Undo $\rightarrow$ `retrain(user)` replaying recorded vote snapshots.
- **Ranking Formula:**
  $\text{score} = 0.65 \times \text{interest} + 0.20 \times \text{freshness} + 0.15 \times \text{source\_rate} - \text{diversity\_penalty}$.
  Exploration: Every 6th story slot features a novel item ("Something different") to avoid echo chambers.
- **Top Stories Lead Hero:** The #1 ranked story across the entire edition is automatically elevated to the lead visual hero position.

---

## 9. Frontend Editorial UI & Mobile Gestures

- **Front Page Layout (`TodayPage.jsx`):**
  - Masthead with Current branding and live volt indicator during crawls.
  - Sticky category jump bar (`CategoryNav.jsx`) with unread counters.
  - Lead story hero card (`LeadStoryCard.jsx`) with prominent Fraunces serif headline, 16:9 thumbnail, and 2-line summary.
  - Editorial category sections (`CategorySection.jsx`) listing compact article rows.
- **Full-Swipe Email Triage (`ArticleRow.jsx` & `useSwipeRow.js`):**
  - **Swipe Right:** Reveals volt/green action with bookmark icon. Release past ~35% width triggers Keep action immediately.
  - **Swipe Left:** Reveals neutral action with dismiss icon. Release past ~35% width triggers Skip/Dismiss and animates row height collapse.
  - **Tap:** Opens Reader view (`/read/:id`).
  - **Undo Toast (`UndoToast.jsx`):** Floating bottom toast providing 1-tap undo for the last 10 actions.
  - **Desktop Accessibility:** Hover buttons (Keep, Skip, Read) and keyboard shortcuts (`k` to Keep, `x` to Skip, `Enter` to Read, `z` to Undo).
- **In-App Reader (`ReaderPage.jsx`):**
  - Distraction-free 65ch typography column.
  - Size controls (S/M/L/XL), Serif / Sans font toggle, dark/light theme toggle.
  - On-demand polling while full text is being fetched.
  - Fallback buttons: "Try with browser", "Read alternative from [Other Source]", "Read on site".

---

## 10. Rules that must hold

1. Every database query on Source, Article, Category, or CrawlRun filters by `user.household_id`. Votes, Kept, and InterestModel filter by `user.id`. Cross-household accesses return 404.
2. **No outbound network request ever bypasses `safe_fetch.py`**, including Playwright sub-requests, robots.txt checks, and thumbnail downloads.
3. **Article text is stored as plain-text block JSON and rendered as React text nodes.** No third-party HTML is injected or rendered via `dangerouslySetInnerHTML`.
4. The reader never sends cookies, logs in, or bypasses paywalls or robots.txt.
5. **No network in tests.** Test suites use `fake_web` fixtures for all HTTP interactions.
6. User-requested article reads are always dispatched at `HIGH` priority on the worker thread.

---

## 11. Build phases for Gemini 3.8 Flash

| # | Phase | Deliverables | Done when |
|---|---|---|---|
| 0 | **Scaffold from Dose + brand** | Port 5734, rename checklist, clean out domain code, Current logo & volt tokens, AGENTS.md skeleton | App boots on 5734, auth/2FA works, Docker build succeeds |
| 1 | **Models + sources/categories CRUD** | `models/news.py`, categories seeder, sources CRUD router, household scoping | CRUD tests pass, household isolation (404), protected General category |
| 2 | **Safe fetch + RSS + priority queue** | `safe_fetch.py` (SSRF guard, throttling, robots), `feeds.py`, deduplication, priority job queue | SSRF blocked, feed parsed, priority queue dispatches HIGH ahead of NORMAL |
| 3 | **HTML + Playwright crawling** | `pages.py` link heuristic & metadata extractor, `browser.py` Chromium runner with ad blocker, async check source job | Link precision $\ge 0.8$, ad network requests blocked in browser |
| 4 | **Full text on demand** | `fulltext.py` fetch ladder (HTTP $\rightarrow$ AMP $\rightarrow$ Playwright), boilerplate cleaner, multi-page stitcher, reader endpoints | Clean blocks extracted, paywall partial marking, priority handling verified |
| 5 | **Learning + ranking + feed API** | `interest.py` AdaGrad model, `routers/feed.py` (`/frontpage`, `/feed`, votes, undo, kept) | Ranking updates after swipe votes, undo retraining verified, story grouping |
| 6 | **Schedule + prune** | `crawl_schedule.py`, retention pruning (`prune.py`), crawl settings | Scheduled triggers fire reliably, old unkept articles and thumbs cleanly deleted |
| 7 | **Frontend: News Front Page & Email-Style Swiping** | TodayPage newspaper front page layout (`LeadStoryCard`, `CategorySection`, `CategoryNav`), email-style swipeable `ArticleRow` (`useSwipeRow.js`), `UndoToast`, KeptPage, ReaderPage, SourcesPage | Smooth 60fps swipe-to-Keep and swipe-to-Skip gesture on mobile (390px), responsive desktop layout with keyboard shortcuts, clean reader rendering |
| 8 | **AI categorization + docs + security audit** | Batch LLM categorizer, README, DESIGN_SYSTEM.md, Cloudflare security-audit skill run | Documentation complete, zero high/medium security audit findings |
