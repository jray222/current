# Dose

A self-hosted visual encyclopedia you learn from a little at a time. Each **deck** is one domain of knowledge (midwestern trees, the solar system, backyard birds, or anything you name), and each **card** shows its subject the way you'd recognise it: a tree's overall look, its bark, its leaf and its fruit, with the name, one line to remember it by, and what to notice in each photo.

- **Sail through** a deck full screen: swipe cards away (or use the arrow keys), tap for the next view, or press play and let it advance every 3, 5, 8 or 12 seconds.
- **Quiz me**: a photo with the name hidden. Show the answer, then say whether you knew it; cards you knew come back later and later (spaced repetition), the rest in ten minutes.
- **Deck of the day**: the home screen features a different domain every day.
- **Pictures are gathered for you** from Wikimedia Commons, Wikipedia and iNaturalist, openly licensed only, with the author, licence and source shown on every photo. The instance owner can swap any picture for another candidate or hide a wrong one.
- **New decks from a topic**: with an Anthropic key, Claude drafts the cards (names, summaries, facts, what to look for) and Dose gathers the pictures. Without one, import a deck **pack** (JSON). Every deck exports as a pack you can edit and import again.
- Shipped decks: **Midwestern trees** (39), **The solar system** (18), **Midwestern backyard birds** (26).

Decks are shared by everyone on the server; what each person has seen and knows is their own. Sign-in, households, invites and 2FA work as in Staple and Glance.

## Quick start (Docker)

```bash
docker compose up -d
```

Open http://localhost:5733 and create the first account (it becomes the instance owner). On first start Dose gathers pictures for the shipped decks in the background (a few minutes; the home screen shows progress). Data and pictures live in the `dose-data` volume. The image runs on amd64 and arm64.

The server needs outbound HTTPS to `commons.wikimedia.org`, `upload.wikimedia.org`, `en.wikipedia.org`, `api.inaturalist.org` and `inaturalist-open-data.s3.amazonaws.com`. To gather a deck by hand and see what happened:

```bash
docker exec -it dose python -m app.cli collect midwest-trees
```

## Local development

```bash
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
cd ../frontend && npm ci
cd .. && ./run.sh
```

Tests: `cd backend && python -m pytest` (no network needed). Lint: `cd frontend && npx oxlint`.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | generated once, stored in the data dir | signs sign-ins |
| `DATA_KEYS` | derived from `SECRET_KEY` | Fernet keys for stored secrets (the Anthropic key, 2FA secrets) |
| `DATABASE_URL` | SQLite in `backend/data` | database |
| `IMAGES_DIR` | `backend/data/images` | downloaded pictures |
| `AUTO_COLLECT` | `true` | gather pictures for shipped decks that have none, at startup |
| `ALLOW_NONCOMMERCIAL_IMAGES` | `true` | also use CC BY-NC pictures (personal use); `false` keeps CC0, CC BY, CC BY-SA |
| `COLLECTOR_CONTACT` | the repo URL | a URL or email sent to Wikimedia and iNaturalist with each request |
| `ALLOW_REGISTRATION` | `false` (compose: `true`) | open sign-up after the first user; otherwise invite-only |
| `PUBLIC_URL` | unset | base URL used in invite and reset links |
| `TRUST_PROXY_HEADERS` | `false` | trust `X-Forwarded-For` (behind a reverse proxy) |
| `ANTHROPIC_API_KEY` | unset | optional, for drafting decks; can also be set in Settings |
| `ANTHROPIC_MODEL` | `claude-sonnet-5-5` | model used to draft decks |
| `TZ` | `America/Indiana/Indianapolis` | the deck of the day changes at local midnight |

## Deck packs

A pack is the whole recipe for a deck, minus the pictures:

```json
{
  "slug": "midwest-trees", "version": 1, "title": "Midwestern trees", "icon": "trees",
  "facets": [
    {"key": "overall", "label": "Tree", "queries": ["{search} tree"], "must": ["tree"], "inat": true},
    {"key": "bark", "label": "Bark", "queries": ["{search} bark"], "must": ["bark", "trunk"]}
  ],
  "cards": [
    {"name": "White oak", "subtitle": "Quercus alba", "group": "Oaks", "wiki": "Quercus alba",
     "summary": "The classic oak: rounded lobes with no bristle tips and pale, flaky bark.",
     "facts": [["Height", "60-100 ft"]],
     "cues": {"overall": "Broad, spreading crown", "bark": "Light ash-gray, in loose vertical plates"},
     "queries": {"bark": ["Quercus alba bark closeup"]}}
  ]
}
```

Facets are the views every card has; `queries` are Wikimedia Commons searches where `{search}` is the card's `search` (else `subtitle`, else `name`); `must` lists words a good photo's title tends to contain; `inat` adds iNaturalist's community photos for living things. Shipped packs are in `backend/app/packs/`; raise `version` to update a shipped deck on existing servers.

## Updates

GitHub Actions tests every pull request and publishes `ghcr.io/jray222/dose:latest` (amd64 and arm64) on every merge to main. Like Glance, a daily check rebuilds and publishes when the `python:3.12-slim` base image has a new version, so the server picks up OS security patches without waiting for a merge.

## Behind Cloudflare / a reverse proxy

Set `PUBLIC_URL` to your public address, `APP_ENV=production` and `TRUST_PROXY_HEADERS=true`. Cloudflare Tunnel pointing at `http://dose:5733` works with no further setup.

## Credits

Photos come from Wikimedia Commons and iNaturalist contributors under the licence shown on each one; summaries come from Wikipedia (CC BY-SA). Dose stores the author, licence and source link with every picture and shows them where the picture is shown.
