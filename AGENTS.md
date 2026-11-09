# AGENTS.md: everything a coding agent needs to change Dose

Read this file first. It is meant to be enough to make most changes **without exploring the codebase**: it says what every file does, the data model, the rules that must not break, the commands, and recipes for the common changes. Open only the files a recipe names. Visual rules are in `docs/DESIGN_SYSTEM.md`; user-facing docs are in `README.md`.

## 1. What Dose is

A self-hosted visual encyclopedia and flashcard app, owned by John (GitHub `jray222`). One **deck** per domain of knowledge (midwestern trees, the solar system, backyard birds...). Each **card** is one subject shown as a few photos, one per **facet** (view): a tree's overall look, bark, leaf, fruit. A card has a name, a subtitle (scientific name, symbol), a one-line summary, a few facts, and a "cue" per facet saying what to notice in that photo. Images are the point; text stays short to build visual memory.

You **sail** through a deck (full screen, swipe or timer), **quiz** yourself (photo with the name hidden, spaced repetition), and the home screen features a different **deck of the day**. Pictures are gathered automatically from Wikimedia Commons, Wikipedia and iNaturalist (open licences only, always credited). The owner can fix pictures card by card. With an Anthropic key, Claude drafts new decks from a topic.

Sibling apps with the same stack and layout: `jray222/staple` (recipes, port 5732, the cleanest base) and `jray222/glance` (finance, 5731). Dose is port **5733**. Auth, households, invites, 2FA, server keys and the Settings screens are copied from Staple; keep them in that style.

## 2. John's product decisions (do not reverse without asking him)

1. The knowledge database (decks, cards, pictures) is **shared by every household on the server**. Only review progress is per person.
2. Changing decks or pictures is for the **instance owner** only (the first account, `is_superuser`). Everyone signed in can read and learn.
3. Cards can be swiped away or auto-advance on a timer ("sail"). A different deck is featured each day.
4. Only openly licensed pictures, credited on screen (author, licence, source link). CC BY-NC is allowed by default because Dose is personal (`ALLOW_NONCOMMERCIAL_IMAGES=true`); ND and unlicensed are never used.
5. Some auto-picked photos are wrong, so the owner fixes them per card (picture sheet: pick a view, use any photo found for the card, own Commons search, look again for one card). Improve automatic picking by tuning `score()` and pack queries, not by adding manual steps.
6. Docker image must run on **arm64 and amd64**. A daily job republishes when the `python:3.12-slim` base image changes (copied from Glance).
7. **No Dependabot** for now ("we'll talk later"). Do not add it unasked.
8. No demo mode, no bundled LLM. Everything except drafting decks works with no API key.
9. Mobile first: check 390px wide and desktop. Runs behind Cloudflare.
10. **Security audits (`cloudflare/security-audit-skill`)**: Reference https://github.com/cloudflare/security-audit-skill (`skills/security-audit/SKILL.md`, installed globally at `~/.gemini/config/skills/security-audit/SKILL.md`). Before running an audit, sync the latest upstream changes from GitHub (`git -C ~/.gemini/config/skills/.security-audit-repo pull --ff-only origin main && cp -r ~/.gemini/config/skills/.security-audit-repo/skills/security-audit/* ~/.gemini/config/skills/security-audit/`). Proactively recommend running a `security-audit` pass (with `flash` subagents, writing to `~/security-audit-skill/dose/run-<N>/`) after any major feature update or changes to auth/2FA/sessions/keys (`routers/auth.py`, `security.py`, `deps.py`), owner-only deck/card/picture write guards (`routers/decks.py`), pack JSON imports (`services/packs.py`), outbound image fetching/downloading (`services/sources.py`, `collector.py`), or AI deck drafting (`services/llm.py`).

## 3. Stack

- Backend: Python 3.12 (3.13 works locally), FastAPI, SQLAlchemy 2 (classic `Column` style), Pydantic 2, pydantic-settings, httpx, Pillow, anthropic SDK. SQLite. No Alembic.
- Frontend: React 19, Vite 8, Tailwind 3, plain JSX (no TypeScript), axios, lucide-react icons, Fraunces + Nunito Sans fonts. No router library, no state library, no frontend tests.
- One Docker image: Vite builds the UI, FastAPI serves API and UI on port 5733, one uvicorn worker.

## 4. File map

```
AGENTS.md                this file (CLAUDE.md just points here)
README.md                user docs: features, config table, pack format, Docker
docs/DESIGN_SYSTEM.md    colours, type, components, stage rules
Dockerfile               node:22-slim builds frontend -> python:3.12-slim runtime, user dose (uid 1000), /health check
docker-compose.yml       pulls ghcr.io/jray222/dose:latest, volume dose-data -> /app/backend/data, port 5733
docker-compose.build.yml override: build from this checkout instead of pulling
run.sh                   local dev: backend :5733 (--reload) + Vite :5173 (proxies /api)
.github/workflows/docker-image.yml       CI: tests, lint, build, multi-arch image (see section 10)
.github/workflows/base-image-update.yml  daily base-image check (see section 10)

backend/
  requirements.txt / requirements-dev.txt (dev adds pytest)
  pytest.ini             testpaths=tests, pythonpath=.
  .env.example           every setting, commented
  app/main.py            FastAPI app; lifespan: create_all -> migrations -> keys.load -> packs.seed_shipped -> collector.resume
  app/config.py          Settings (env / backend/.env); SECRET_KEY auto-generated into data/secret_key; settings.images_dir
  app/database.py        engine, SessionLocal, Base, get_db (SQLite busy_timeout 30s)
  app/migrations.py      _REQUIRED_COLUMNS: ALTER TABLE ADD COLUMN for columns added after release (empty today)
  app/deps.py            get_current_user, get_current_admin_user, get_current_superuser, get_client_ip (Cloudflare-aware)
  app/frontend.py        serves frontend-dist: index.html no-cache, /assets immutable, SPA fallback, /api/* 404
  app/security.py        bcrypt, JWT, Fernet encrypt_secret/decrypt_secret, key_state
  app/rate_limit.py      in-memory auth rate limiter
  app/schemas_auth.py    Pydantic models for auth routes
  app/cli.py             python -m app.cli collect <slug> [--force] | clear-lock <user> | reset-password <user> [--link]
  app/pack_template.json the downloadable example pack (has a "_how_to" list, ignored on import)
  app/packs/*.json       shipped decks: midwest-trees (39 cards; overall, bark, leaf, fruit),
                         solar-system (18; overall, surface), backyard-birds (26; overall, female)
  app/models/knowledge.py  Deck, Card, CardImage, CardProgress   <- the domain
  app/models/user.py       User, BackupCode, RefreshToken, PasswordResetLink, LoginAuditLog
  app/models/household.py  Household;  invite.py Invite;  runtime_config.py RuntimeConfig (key/value)
  app/routers/decks.py     every deck/card/picture/progress endpoint (prefix /api/v1)
  app/routers/auth.py      sign-up, sign-in, 2FA, users, invites, resets (prefix /api/v1/auth)
  app/routers/settings.py  owner-only: AI key/model, registration mode, server keys (prefix /api/v1/settings)
  app/services/packs.py      PackSpec validation, apply_pack, seed_shipped, export_pack, facet_queries, slugify
  app/services/collector.py  gathering pictures: score, gather, choose, assign, collect_card, run_deck, enqueue, resume
  app/services/sources.py    HTTP to Commons / Wikipedia / iNaturalist; normalize_license; download; SourceError
  app/services/job_queue.py  one in-process worker thread; JOB_QUEUE=manual for tests (drain())
  app/services/progress.py   Leitner boxes, quiz_order, deck_of_the_day, local_today
  app/services/llm.py        Claude drafts a pack (tool "save_deck"); LlmError
  app/services/ai.py         effective Anthropic key/model: stored (encrypted) first, else env
  app/services/keys.py, lockout.py, invites.py, households.py, password_resets.py   auth plumbing from Staple
  tests/conftest.py        temp SQLite, JOB_QUEUE=manual, AUTO_COLLECT=False, fixtures make_user, anon_client
  tests/test_decks.py      packs, collector (fake_sources fixture), pictures, progress, quiz, deck of the day, draft, CLI
  tests/test_auth.py, test_invites.py, test_signin_and_keys.py, test_frontend_serving.py

frontend/
  package.json           scripts: dev, build, lint (oxlint), preview
  vite.config.js         dev port 5173, proxies /api to DOSE_API_URL or http://localhost:5733
  tailwind.config.js     tokens (see DESIGN_SYSTEM.md);  .oxlintrc.json lint rules
  index.html             head tags: favicon, apple-touch-icon, manifest, theme-color, iOS web-app meta
  public/                served at the site root. App icon: icon.svg is the square master; favicon.svg is it
                         with rounded corners; apple-touch-icon.png (180, no transparency, iOS Home Screen),
                         icon-192.png, icon-512.png (also the maskable icon; artwork sits in the safe zone),
                         favicon-32.png; manifest.json. To change the icon, edit icon.svg and re-render every
                         PNG from it at its size with no alpha. iOS caches Home Screen icons: remove and
                         re-add the shortcut to see a new one.
  src/main.jsx           mounts App in ErrorBoundary + AuthProvider; theme watcher; reload-on-update
  src/App.jsx            routing (see section 7); full-screen routes skip the Shell
  src/api.js             axios instance (baseURL /api/v1, in-memory access token, one silent refresh on 401) + one function per endpoint
  src/appUpdate.js       lazyPage(): reloads once if a lazy chunk is gone after an update
  src/index.css          CSS variables (light/dark) and component classes (.card .btn-primary .chip .input .banner-*)
  src/context/AuthContext.jsx   useAuth(): user, isAuthenticated, initializing, login/logout...
  src/lib/router.js      navigate(), useLocation(), matchPath(), onLinkClick()
  src/lib/useSwipe.js    swipe/tap gestures;  useDeckPolling.js reload every 4s while collecting;  theme.js
  src/components/Shell.jsx       side nav (desktop) / bottom tabs Today, Decks, More (phone)
  src/components/AuthImage.jsx   <AuthImage path=...>: loads pictures with the token as blob URLs; loadImage, preloadImages
  src/components/ui.jsx          errorOf, ErrorBanner, SuccessBanner, Spinner, EmptyState, PageHeader
  src/components/Modal.jsx       Modal (bottom sheet on phones), Field, FormActions
  src/components/AuthGateway.jsx sign-in / sign-up / 2FA / invite / reset screens
  src/components/deck/DeckBits.jsx     ProgressBar, progressLine, DeckCover, CollectStatus, isCollecting
  src/components/deck/DeckIcon.jsx     ICONS map: allowed deck icon names (unknown -> Layers)
  src/components/deck/PictureChooser.jsx  owner picture sheet for one card
  src/components/settings/        HouseholdSection, SecuritySection, AISection, Section
  src/pages/  TodayPage, DecksPage, DeckPage, SailPage, QuizPage, NewDeckPage, MorePage, SettingsPage
```

## 5. Data model (`backend/app/models/knowledge.py`)

Models are the schema source of truth. `Base.metadata.create_all` makes new tables at startup; columns added later need an entry in `migrations._REQUIRED_COLUMNS`.

**Deck** `decks`: `id`, `slug` (unique), `title`, `subtitle`, `description`, `icon` (a key of `DeckIcon.ICONS`), `facets` JSON `[{key, label, queries[], must[], inat}]`, `source` (`pack` shipped / `ai` drafted / `import` pasted), `pack_version`, collection state `collect_status` (`idle|queued|running|done|error`), `collect_done`, `collect_total`, `collect_message`, `collected_at`, timestamps. `cards` relationship ordered by `sort_order`, cascade delete.

**Card** `cards`: `deck_id`, `slug` (unique per deck, = `slugify(name)`), `name`, `subtitle`, `group`, `summary`, `facts` JSON `[{label, value}]`, `cues` JSON `{facet_key: text, "_queries": {facet_key: [query...]}}`, `search_name`, `wiki_title`, `wiki_url`, `wiki_extract` (Wikipedia first paragraph), `sort_order`. `images` ordered by `rank`.

**CardImage** `card_images`: `card_id`, `facet`, `status` (`candidate|chosen|hidden`; at most one `chosen` per card+facet), `picked_by_person` (0/1 int), `score`, `rank`, `provider` (`commons|inaturalist`), `source_id` (Commons `File:...` title or iNat photo id), `page_url`, `remote_url`, `preview_url`, `width`, `height`, `title`, `author`, `license`, `license_url`, `local_path`, `thumb_path` (relative to `IMAGES_DIR`). Unique (`card_id`, `facet`, `provider`, `source_id`). Files: `<IMAGES_DIR>/<deck slug>/<card slug>/<facet>-<image id>.jpg` and `...-thumb.jpg` (max 1600px / 480px).

**CardProgress** `card_progress`: unique (`user_id`, `card_id`), `box` 0-5, `seen`, `knew`, `last_seen_at`, `due_at`.

Auth tables (from Staple): `users` (`household_id`, `is_admin` household admin, `is_superuser` instance owner, TOTP and lockout fields), `households`, `invites`, `refresh_tokens`, `backup_codes`, `password_reset_links`, `login_audit_log`, `runtime_config` (keys `anthropic_api_key` encrypted, `anthropic_model`, `registration_mode`, `public_url`, `data_key_check`...).

Datetimes are written timezone-aware but SQLite returns them naive; compare with a helper like `progress._aware()`.

## 6. Core business logic

### Packs (`services/packs.py`)
A pack is JSON describing a deck without pictures. Validated by `PackSpec` (extra keys ignored):

```json
{
  "slug": "midwest-trees", "version": 1, "title": "Midwestern trees", "subtitle": "...", "icon": "trees",
  "description": "...",
  "facets": [
    {"key": "overall", "label": "Tree", "queries": ["{search} tree", "{search}"], "must": ["tree"], "inat": true},
    {"key": "bark", "label": "Bark", "queries": ["{search} bark"], "must": ["bark", "trunk"]}
  ],
  "cards": [
    {"name": "White oak", "subtitle": "Quercus alba", "group": "Oaks", "wiki": "Quercus alba",
     "search": "Quercus alba", "summary": "One line.", "facts": [["Height", "60-100 ft"]],
     "cues": {"overall": "Broad crown", "bark": "Pale, flaky plates"},
     "queries": {"bark": ["Quercus alba bark closeup"]}}
  ]
}
```

Limits: title 1-120 chars, 1-8 facets (each up to 6 queries, 30 must words), 1-300 cards, card name 1-160, summary 400, up to 8 facts (pair or `{label, value}`). Only `name` is required per card. In queries `{search}` = card `search` else `subtitle` else `name`; `{name}` = name. `must` = words a good photo title contains. `inat: true` adds iNaturalist taxon photos (needs a scientific name as subtitle/search). Card `queries` are stored in `cues["_queries"]` (max 4 per facet, never sent to the UI) and tried before the facet's templates (`facet_queries`).

`apply_pack(db, spec, source)` creates or updates by slug: updates deck fields and every card's text, adds new cards, sets `sort_order`. It **never deletes cards** missing from the pack, never touches pictures or progress. Card identity is `slugify(name)`: renaming a card makes a new card (the old one stays with its pictures). Changing `wiki` clears `wiki_extract` so it is fetched again.

`seed_shipped(db)` at startup: adds missing shipped decks; re-applies a shipped deck only when its `source == "pack"` and the file's `version` is higher than `pack_version`. So **to change a shipped deck, edit the JSON and bump `version`**.

`export_pack(deck)` returns a pack (round-trips through import). `template()` returns `pack_template.json`.

### Collector (`services/collector.py`, job kind `collect`)
`enqueue(db, deck, force)` sets `queued` and puts `("collect", deck.id, force)` on the job queue. `run_deck` walks every card through `collect_card`, writing `collect_done/total` as it goes, ending `done` (with a summary of problems in `collect_message`) or `error` after 3 cards in a row whose problems start with "Couldn't reach" (message names the hosts).

`collect_card(db, client, deck, card, force, only)`: fetch Wikipedia summary if missing (or forced); then for each facet (or only `only`): skip if it has a downloaded chosen picture unless `force` (and never if `picked_by_person`); `gather` candidates; `_store` them; `choose` the best that downloads. Returns problem strings.

`gather`: first facet only, the Wikipedia article's lead image (scored +4 as `lead`); up to the first 3 `facet_queries` on Commons; iNat photos if `facet.inat` and card has a subtitle. Dedupes by (provider, source_id), keeps the top `CANDIDATES_PER_FACET` (8). With `queries=[...]` (an owner's own search) only those Commons searches run.

`score(candidate, facet, card, lead)`: +5 if title/description has a `must` word, else -2 (when facet has must words); +2 (+0.5 per word) for card-name words (ignoring the, of, and, common, american, eastern, northern); -9 if any `AVOID_WORDS` substring (herbarium, specimen, map, range, drawing, illustration, plate, diagram, stamp, label, sign, section, scan, page, book...); +2 for Quality/Featured/Valued image categories; -4 if the short side < 500px, +1 if >= 1200px; up to +1.5 for search rank; +4 lead; +1.5 iNaturalist on an `inat` facet. **Known issue:** AVOID_WORDS are matched as substrings of the title + description, so "map" hits "maple", "range" hits "orange", "sign" hits "design", "icon" hits "silicon", "chart" hits "charter". Maple and fall-colour photos are penalised for this. `test_score_prefers_the_facet_and_avoids_sheets_and_maps` is the scoring test; add a case to it whenever you change `score()`.

Owner actions: `choose(db, client, card, facet, image=None, by_person=False)`, `assign(db, client, image, facet)` (put a photo on another view of the same card, copying the file if already downloaded), `search_card(db, client, card, facet, query)` (own search: results become candidates; the view's picture only changes if it had none), `remove_files(image)`. Rules: a picture with `picked_by_person=1` is never replaced by collection; `hidden` never comes back.

`resume(db)` at startup re-queues decks that were `queued`/`running`, and with `AUTO_COLLECT` also never-collected `idle` decks.

### Sources (`services/sources.py`)
All functions return plain dicts with keys `provider, source_id, page_url, remote_url, preview_url, width, height, title, author, license, license_url, categories, description, search_rank`. `make_client()` builds the httpx client with User-Agent `Dose/0.1 (...; COLLECTOR_CONTACT)`. Functions: `commons_search(client, query, limit=12)` (adds `filetype:bitmap`, drops SVG/GIF), `commons_files(client, titles)`, `wikipedia_summary(client, title)` -> `{extract, url, title}` or None, `wikipedia_lead_image(client, title)` -> `"File:..."`, `inat_taxon_photos(client, scientific_name)` (exact name match only, large URLs), `download(client, url)` (25 MB cap). Errors raise `SourceError` with a message safe to show. `normalize_license` keeps CC0, public domain, CC BY, CC BY-SA, CC BY-NC(-SA) unless disabled; rejects ND and unknown.

Hosts needed at runtime: `commons.wikimedia.org`, `upload.wikimedia.org`, `en.wikipedia.org`, `api.inaturalist.org`, `inaturalist-open-data.s3.amazonaws.com`. Cloud sandboxes usually cannot reach them, so real collection is verified on John's server, not in CI.

### Job queue (`services/job_queue.py`)
`register(kind, handler)`, `enqueue(kind, *args)` (deduped while pending), a single daemon thread. State is in-process: **run one uvicorn worker** (the Dockerfile does). `JOB_QUEUE=manual` (tests) holds jobs until `job_queue.drain()`.

### Progress (`services/progress.py`)
`record(db, user_id, card_id, result)`: `seen` (sailing) increments seen and makes it due tomorrow if it had no due date; `knew` moves up a box (max 5) and sets due in 1, 3, 7, 16, 35 days for boxes 1-5; `again` sets box 1, due in 10 minutes. Known = box >= 3. `summary` -> `{total, seen, known, due, new}`. `quiz_order`: due (most overdue first), then new in deck order, then the rest by due date. `deck_of_the_day(db, day)`: decks that have at least one downloaded chosen picture, ordered by id, index `day.toordinal() % len`. `local_today()` uses `TZ`.

### Drafting with Claude (`services/llm.py`, `services/ai.py`)
`llm.configured(db)` -> `LlmConfig(api_key, model)` or None. `draft_deck(cfg, topic, count, notes)` forces tool `save_deck` (schema `DECK_TOOL`, 1-4 facets) and returns its input; the router validates it as a `PackSpec` and returns it with `"_source": "ai"` for the owner to review, then the UI posts it to `/decks/import`. Nothing is saved by drafting. Default model `claude-sonnet-5-5`; Settings suggests `claude-haiku-5-5` and `claude-sonnet-5-5`. Tests replace `llm.make_client`.

### Auth (from Staple; change only if asked)
bcrypt passwords; 15-minute JWT access token kept in memory by the frontend; rotating httpOnly refresh cookie `dose_refresh_token` (7 days); TOTP 2FA with backup codes; known-device lockout (`services/lockout.py`); rate limits; invites (owner invite = new household, admin invite = join household); one-hour reset links; "sign everyone out" and data-key rotation (`services/keys.py`). The **first account** becomes instance owner (`is_superuser`) and household admin. `ALLOW_REGISTRATION` / runtime `registration_mode` decides open sign-up vs invite-only. Every router except auth is mounted with `Depends(get_current_user)` in `main.py`.

## 7. HTTP API

All under `/api/v1`, all need a Bearer token except the public auth routes. "Owner" = `Depends(get_current_superuser)` (403 for others).

| Method and path | Who | What |
|---|---|---|
| GET `/decks` | any | deck summaries: slug, title, subtitle, icon, description, source, facets `[{key,label}]`, card_count, cover_image_id, collect `{status,done,total,message,collected_at}`, progress `{total,seen,known,due,new}` |
| GET `/today` | any | `{date, deck: summary or null}` |
| GET `/decks/template` | any | the example pack (declared before `/decks/{slug}` on purpose) |
| GET `/decks/{slug}` | any | summary + `cards[]`: id, slug, name, subtitle, group, summary, facts, cues (no `_` keys), wiki_url, wiki_extract, images `{facet: image}` (chosen and downloaded only), progress `{box,seen,knew}` |
| GET `/decks/{slug}/quiz?limit=20` | any | `{card_ids}` in quiz order (cards with pictures only) |
| GET `/images/{id}/file?size=full\|thumb` | any | the JPEG (cached immutable) |
| POST `/progress` `{card_id, result: seen\|knew\|again}` | any | updated box/seen/knew/due_at |
| GET `/decks/{slug}/export` | any | the deck as a pack |
| GET `/cards/{id}/images?facet=` | owner | every picture found, chosen first then by score, with preview_url |
| POST `/cards/{id}/collect` `{facet?, query?}` | owner | look again now (synchronous); with query, own Commons search for that facet; 409 while the deck collects |
| POST `/images/{id}/choose` `{facet?}` | owner | make it the view's picture (optionally on another view) |
| POST `/images/{id}/hide` | owner | hide forever; next best replaces it if it was chosen |
| POST `/decks/{slug}/collect` `{force}` | owner | queue collection |
| POST `/decks/import` (pack JSON) | owner | create/update deck, queue collection; 400 with the first validation error |
| POST `/decks/draft` `{topic, count 5-80, notes}` | owner | Claude's draft pack (400 without a key, 502 on model errors) |
| DELETE `/decks/{slug}` | owner | deletes deck, cards, pictures, progress and its image folder |
| `/settings/ai`, `/settings/registration`, `/settings/keys...` | owner | AI key/model, sign-up mode and public URL, server keys |
| `/auth/*` | mixed | bootstrap-status, register, login, login/verify-2fa, refresh, logout, me, change-password, 2fa/*, users, invites, reset |
| GET `/health` | public | `{"status": "healthy"}` |

Interactive docs at `http://localhost:5733/docs` when running locally.

## 8. Frontend screens

Routes are matched by hand in `src/App.jsx` (`Routes()` inside the Shell; `FullScreen()` for sail/quiz, detected by regex `^/decks/[^/]+/(sail|quiz)$`). Order matters: `/decks/new` is checked before `/decks/:slug`. Unknown paths show Today. Not signed in: `AuthGateway`.

- `/` **TodayPage**: deck of the day large (cover, Sail and Quiz buttons, progress), other decks below.
- `/decks` **DecksPage**: all decks as tiles.
- `/decks/:slug` **DeckPage**: photo grid of cards, group filter chips, buttons Sail through / Shuffle / Quiz me (shows due count) / Export pack (everyone), progress bar; owner only: Find better pictures (`collect` with force), Delete, the last gathering's notes, and a pictures button per card that opens `PictureChooser`. Tapping a card opens sail at `?start=<card slug>`. Today, Decks and Deck pages poll every 4 s while a deck is collecting.
- `/decks/:slug/sail` **SailPage** (full screen, black stage): query params `group`, `shuffle=1`, `start=<card slug>`. Only cards with pictures. ←/→ or swipe sideways = card, ↑/↓ or tap = view, space = play (3/5/8/12 s per view, saved in localStorage `dose:sail-seconds`), `i` = more info (wiki extract, facts), Esc = close. Moving past a card posts `seen` once. Preloads next pictures. Pauses when the tab is hidden. Owner can open the picture sheet.
- `/decks/:slug/quiz` **QuizPage**: rounds of 20 from `/quiz`. Space/Enter shows the answer, →/2 knew it, ←/1 not yet, ↓/v next view, swipe right/left, Esc back.
- `/decks/new` **NewDeckPage** (owner): tab "Ask Claude" (topic, count, notes, idea chips; review the draft, then import) or "Import a pack" (paste JSON, download template). Without a key it opens on the pack tab.
- `/more` **MorePage** (phone menu), `/settings/:section` **SettingsPage**: household, security, ai (owner only).

Conventions: pictures need the token, so always use `<AuthImage path={imagePath(id, 'thumb'|'full')} />`, never `<img src>`. API calls go through functions in `src/api.js`; show errors with `errorOf(err, 'fallback')` + `<ErrorBanner>`. Navigation: `<a href={to} onClick={onLinkClick(to)}>` or `navigate(path)`. Owner-only UI checks `useAuth().user?.is_superuser`. Use the classes from `index.css` and tokens from Tailwind (`bg-cream`, `bg-surface`, `text-ink`, `text-muted`, `border-line`, `brand-*`, `moss-*`, `amber-*`), which work in light and dark. Copy is plain, warm and short ("Look again", "Not yet"); no exclamation marks, no jargon.

## 9. Commands

```bash
# Backend setup and tests (no network needed; ~45 s, 88 tests)
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
cd backend && python -m pytest -q                  # all
cd backend && python -m pytest -q tests/test_decks.py -k collect   # a subset

# Frontend
cd frontend && npm ci
cd frontend && npm run lint      # oxlint; 3 existing warnings (set-state-in-effect) are fine, errors fail CI
cd frontend && npm run build     # vite build -> frontend/dist

# Run locally (backend :5733 + Vite :5173, open http://localhost:5173)
./run.sh

# Docker
docker compose up -d                                                        # published image
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build   # build this checkout

# Server commands (inside the container)
docker exec -it dose python -m app.cli collect midwest-trees [--force]
docker exec -it dose python -m app.cli clear-lock <username>
docker exec -it dose python -m app.cli reset-password <username> [--link]
```

Before opening a PR, run the backend tests, `npm run lint` and `npm run build`. These are exactly what CI runs.

## 10. CI, release and deploy

`.github/workflows/docker-image.yml` "Test and publish image": runs on every pull request (any base branch), every push to `main`, and manually. Jobs: **backend** (Python 3.12, `pytest backend/tests -q`), **frontend** (Node 22, `npm ci`, `npm run lint`, `npm run build`), then **image** (QEMU + buildx, `linux/amd64,linux/arm64`). On PRs the image is only built, not pushed (the arm64 build under QEMU takes several minutes). On `main` it pushes `ghcr.io/jray222/dose:latest` and `:sha-<short>`, with label `dose.base-digest=<python:3.12-slim digest>`.

`.github/workflows/base-image-update.yml` "Base image update check": daily at 09:00 UTC (and manual). Compares the current `python:3.12-slim` digest to the `dose.base-digest` label on `:latest`; if different (or missing) it runs `gh workflow run docker-image.yml --ref main`, which tests and republishes. Otherwise it does nothing. There is no nightly test run.

Release = merge a PR to `main`. Deploy on John's server, in the folder with `docker-compose.yml`:

```bash
docker compose pull && docker compose up -d
```

Data (SQLite `dose.db`, generated `secret_key`, `images/`) lives in the `dose-data` volume at `/app/backend/data` and survives updates. Schema changes apply at startup via `create_all` + `migrations.py`. Behind Cloudflare set `APP_ENV=production`, `PUBLIC_URL`, `TRUST_PROXY_HEADERS=true`.

## 11. Configuration (env or `backend/.env`; see `.env.example` and README)

`SECRET_KEY`, `DATA_KEYS`, `DATABASE_URL`, `IMAGES_DIR`, `AUTO_COLLECT` (true), `ALLOW_NONCOMMERCIAL_IMAGES` (true), `COLLECTOR_CONTACT`, `IMAGE_MAX_PX` (1600), `THUMB_MAX_PX` (480), `CANDIDATES_PER_FACET` (8), `ALLOW_REGISTRATION` (false; compose true), `PUBLIC_URL`, `TRUST_PROXY_HEADERS`, `TRUSTED_PROXIES`, `APP_ENV`, `FRONTEND_ORIGIN`, `FRONTEND_DIST` (set in the image), `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` (`claude-sonnet-5-5`), `TZ` (compose default `America/Indiana/Indianapolis`), `JOB_QUEUE=manual` (tests only). Add a new setting to `config.Settings` with a comment, to `.env.example`, and to the README table if users need it.

## 12. Rules that must hold

1. Decks, cards and pictures have no household; reads need any sign-in, writes need `get_current_superuser`. Progress is always filtered by `user.id`.
2. Never store or show a picture without author, licence and source page; never relax `normalize_license` to allow ND or unlicensed.
3. Collection never replaces a `picked_by_person` picture and never revives a `hidden` one.
4. **No network in tests.** Use the `fake_sources` fixture in `tests/test_decks.py` (monkeypatches `sources.make_client`, `commons_search`, `commons_files`, `wikipedia_lead_image`, `wikipedia_summary`, `inat_taxon_photos`, `download`) or `httpx.MockTransport` for parser tests. Run queued jobs with `job_queue.drain()`. Fake Claude via `monkeypatch.setattr(llm, "make_client", ...)`.
5. Schema change = edit the model + add `(column, "SQLite DDL")` to `migrations._REQUIRED_COLUMNS` for the existing table + a test. Booleans in migrations are `INTEGER 0/1`. Never drop or rename columns.
6. Pack files must stay valid: `test_shipped_trees_pack_is_valid_and_seeds` and `test_every_shipped_pack_has_unique_cards` load all of them. Card names must be unique within a deck (slug collision).
7. One process, one worker; do not add Celery/Redis or multiple uvicorn workers.
8. Every change gets a test when it touches backend behaviour.
9. Keep `README.md` in step when user-visible behaviour, config or the pack format changes, and update this file when structure or rules change.

## 13. Recipes

**Add or change cards in a shipped deck.** Edit `backend/app/packs/<slug>.json`, bump `"version"`. Existing servers re-apply it at next start. New cards get pictures when the owner presses "Find better pictures" or runs `python -m app.cli collect <slug>` (startup only auto-collects decks never collected). Removing a card from the JSON does not delete it from existing databases.

**Add a shipped deck.** New `backend/app/packs/<slug>.json` with a unique `slug`, `version: 1`, an `icon` that is a key in `frontend/src/components/deck/DeckIcon.jsx` `ICONS` (add the lucide icon there, and to the icon list in `llm.DECK_TOOL` if Claude should use it). Give living things a scientific `subtitle` and `inat: true` on the first facet; give each facet `must` words. Run the tests. Add the deck to the README "Shipped decks" line.

**Pictures for a card are wrong.** Prefer data fixes: add card `queries` for that facet in the pack, set `search`, or adjust the facet's `must` words. For systematic problems tune `score()` / `AVOID_WORDS` in `collector.py` and add a case to `test_score_prefers_the_facet_and_avoids_sheets_and_maps`. You cannot verify against real Commons from a sandbox; say so in the PR and ask John to run `docker exec dose python -m app.cli collect <slug> --force` (owner picks stay).

**Add a field to cards.** Column on `Card` in `models/knowledge.py`; migration entry `"cards": [("field", "VARCHAR(200) NULL")]`; read it in `CardSpec` and `apply_pack`; write it in `export_pack`; return it in `routers/decks._card_json`; show it in the UI; document it in README "Deck packs", `pack_template.json` `_how_to`, and section 6 here; add it to `llm.DECK_TOOL` if Claude should fill it. Test import/export round trip.

**Add an endpoint.** Put it in `routers/decks.py` (or a new router included in `main.py` with `dependencies=_protected`). Use `Depends(get_current_user)` to read, `Depends(get_current_superuser)` to change shared data. Logic goes in `services/`. Fixed paths must be declared before `/{slug}` paths. Add a function in `frontend/src/api.js`. Add a test using `make_user` (the first `make_user` is the owner; a second one is not an owner but is admin of its own new household, since tests use open registration).

**Add a page.** Create `frontend/src/pages/XPage.jsx` (default export), lazy-load it in `App.jsx` with `lazyPage(() => import(...))`, add a branch in `Routes()` before any `:param` pattern that would swallow it, and add a link in `Shell.jsx` (`TABS` or `EXTRA`, `ownerOnly: true` if needed) and `MorePage.jsx` for phones. Use `PageHeader`, `.card`, `Spinner`, `ErrorBanner`.

**Change sail or quiz behaviour.** `SailPage.jsx` (keys in one `keydown` effect, timer effect, `goCard`/`goFacet`) or `QuizPage.jsx` (`ROUND`, `answer`). Spaced-repetition intervals are in `progress.py` `INTERVALS`/`AGAIN` (update the docstring and `test_progress_moves_through_boxes`).

**Add a background job kind.** Write the handler in a service, opening its own `SessionLocal()`; `job_queue.register("kind", handler)` at module import; make sure the module is imported at startup (`main.py` imports `collector`). Test with `JOB_QUEUE=manual` + `job_queue.drain()`.

## 14. Git and PR conventions

- Work on a branch, open a PR against `main`, wait for CI to be green. Never push to `main` directly. Merging publishes the image.
- Commit messages: imperative summary line, then a short body saying why. Claude Code sessions end commits with the Co-Authored-By and Claude-Session trailers they are given.
- Match the surrounding code: short docstrings that say what and why, comments sparse, plain names, f-strings, early returns. User-facing messages are full sentences.
- Do not commit `backend/data/`, `.env`, `frontend/dist`, `node_modules` or `.opencode/` (all gitignored).
