# Current

The news, as it happens, as you like it.

**Current** is a self-hosted personal news aggregator and distraction-free reader that learns your interests as you read. It structures articles into a personal digital newspaper—highlighting Top Stories and categorized sections—with fast, mobile email-style swipe actions on every story.

- **Your own front page**: An editorial digital newspaper layout. The #1 ranked story across the edition is elevated as the lead visual hero, followed by category sections (World, Tech, Politics, Business, Science, Culture, etc.).
- **Email-style swipe triage**: Articles appear in clean, compact lists. Swipe right to Keep (save to your Kept reading list), swipe left to Skip/Dismiss (removes it from the unread feed).
- **Learns locally**: Every swipe trains an in-process AdaGrad logistic regression model. Articles are scored and ranked based on learned interest, recency, and source diversity—all running locally with zero API keys required.
- **Polite & robust crawling**: Discovers and crawls news via RSS/Atom feeds, plain HTML extraction, or headless Playwright rendering for JavaScript-heavy sites. Respects `robots.txt`, enforces per-host rate limiting, and guards every outbound request with strict SSRF protection.
- **On-demand clean reader**: Strips clutter, ads, and tracking scripts. Follows multi-page articles, falls back to AMP or browser rendering with ad blocking when needed, and presents clean typography without ever bypassing paywalls or logins.
- **Household tenancy**: Sources and categories belong to your household and crawl once; reading votes, personal models, and kept lists belong to each person.

Sibling apps with the same stack: Staple (recipes, port 5732), Glance (finance, 5731) and Dose (encyclopedia, 5733). Current runs on port **5734**.

## Quick start (Docker)

```bash
docker compose up -d
```

Open http://localhost:5734 and create the first account (which becomes the instance owner). Articles and full text survive in the `current-data` volume. The Docker image runs on `amd64` and `arm64`.

To trigger a crawl manually from the container:

```bash
docker exec -it current python -m app.cli crawl all
```

## Local development

```bash
cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt -r requirements-dev.txt
cd ../frontend && npm ci
cd .. && ./run.sh
```

Backend tests: `cd backend && python -m pytest backend/tests -q` (no network access required).
Frontend lint & build: `cd frontend && npm run lint && npm run build`.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | generated once, stored in data dir | Signs authentication tokens (JWTs and device cookies) |
| `DATA_KEYS` | derived from `SECRET_KEY` | Fernet keys for encrypting 2FA secrets and API keys |
| `DATABASE_URL` | SQLite in `backend/data/current.db` | Database connection string |
| `CRAWLER_CONTACT` | `https://github.com/jray222/current` | URL/email sent in Crawler User-Agent |
| `RESPECT_ROBOTS` | `true` | Comply with `robots.txt` disallow rules |
| `CRAWL_DELAY_SECONDS` | `1.0` | Minimum polite delay between requests to the same host |
| `MAX_NEW_PER_SOURCE` | `25` | Maximum new article pages fetched per source per crawl |
| `MAX_ARTICLE_PAGES` | `5` | Maximum pages followed for multi-page articles |
| `RETENTION_DAYS` | `14` | Days unkept articles are retained before pruning |
| `BROWSER_FETCH` | `true` | Allow Playwright headless Chromium for JS crawling and full text |
| `ALLOW_REGISTRATION` | `false` (compose: `true`) | Open registration vs invite-only |
| `PUBLIC_URL` | unset | Base URL for invite and password reset links |
| `TRUST_PROXY_HEADERS` | `false` | Trust proxy headers (`X-Forwarded-For`, `CF-Connecting-IP`) |
| `ANTHROPIC_API_KEY` | unset | Optional; used only for batch category sorting from mixed sources |
| `TZ` | `America/Indiana/Indianapolis` | Server time zone for daily scheduled crawls |
