# AI Coding Agent Context (Claude Code / Cursor / others)

Dose is a self-hosted visual encyclopedia and flashcard app: one domain of knowledge per deck (midwestern trees, the solar system, backyard birds...), each card shown as a few photos (a tree's overall look, bark, leaf, fruit) with its name, a one-line summary and what to notice. You sail through a deck (swipe, or a timer), quiz yourself, and a different deck is featured each day. It mirrors the architecture of the sibling apps Staple and Glance. Visual rules are in `docs/DESIGN_SYSTEM.md`.

## Architecture

- Backend: Python 3.12, FastAPI, SQLAlchemy 2. Models in `backend/app/models/` are the schema source of truth; `Base.metadata.create_all` runs at startup and `app/migrations.py` adds columns to existing databases. `routers/` hold HTTP, `services/` hold logic.
- DB: SQLite at `backend/data/dose.db` (override with `DATABASE_URL`). Pictures in `backend/data/images/<deck>/<card>/` (`IMAGES_DIR`).
- Frontend: React 19, Vite, Tailwind 3 (CSS-variable tokens, `.dark` class), plain JSX, a small history router in `src/lib/router.js`. Built into the image and served by FastAPI (`app/frontend.py`) on one port, 5733.
- Auth: the same as Staple (bcrypt, 15-minute JWT in memory plus a rotating httpOnly refresh cookie, TOTP 2FA, known-device lockout, rate limits, invites, reset links, households).
- AI: Anthropic key stored encrypted in `runtime_config` (Settings > AI) with env fallback. Only used to draft new decks; everything else works with no key.

## Core rules

1. **Decks are shared by the whole server.** `decks`, `cards` and `card_images` have no household; anyone signed in can read them. Changing them (collecting, choosing or hiding pictures, importing, drafting, deleting) is for the instance owner (`get_current_superuser`).
2. **Progress is per person.** `card_progress` (user + card): a Leitner box 0-5 (`services/progress.py`). Sailing past a card records `seen`; the quiz records `knew` or `again`.
3. **Packs describe decks.** `services/packs.py`: a JSON pack names the deck, its facets (views, each with Commons search templates using `{search}`/`{name}`, `must` words and `inat`) and its cards (name, subtitle, group, wiki title, search name, summary, facts, cues per facet, extra queries per facet). Shipped packs live in `backend/app/packs/*.json` and are seeded at startup; bump `version` to update a shipped deck. Re-applying a pack updates card text and never touches pictures or progress. Card-specific queries are stored in `cards.cues["_queries"]` (never sent to the UI).
4. **Only openly licensed pictures, always credited.** `services/sources.py` talks to Wikimedia Commons, Wikipedia (summary + lead image) and iNaturalist; `normalize_license` keeps CC0/public domain/CC BY/CC BY-SA (and CC BY-NC unless `ALLOW_NONCOMMERCIAL_IMAGES=false`), never ND or unlicensed. Author, licence and source page are stored with every picture and shown on the stage.
5. **Collection** (`services/collector.py`, job kind `collect` on `services/job_queue.py`): per card, the Wikipedia extract, then per facet up to 3 Commons searches plus the article's lead picture (first facet) and iNaturalist taxon photos (`inat` facets). `score` favours titles with the facet's `must` words and the card's name, Quality/Featured images and large files, and penalises herbarium sheets, maps and drawings. The best `CANDIDATES_PER_FACET` are kept; the best that downloads is chosen and saved as a resized JPEG plus thumbnail. A picture the owner picked (`picked_by_person`) is never replaced; a hidden one never returns. Three unreachable cards in a row stop the job with a message naming the hosts.
6. **Deck of the day** cycles through decks that have pictures, by date ordinal in `TZ` (`progress.deck_of_the_day`).
7. **No network in tests.** Fake `sources.*` functions or use `httpx.MockTransport`; `JOB_QUEUE=manual` and `job_queue.drain()` run jobs in the test.
8. Schema changes: edit the model, add a lightweight migration in `migrations.py` for existing databases, add a test.

## Frontend

- `/` Today (deck of the day + other decks), `/decks`, `/decks/:slug` (photo grid, group filter, owner tools), `/decks/:slug/sail` and `/decks/:slug/quiz` (full screen, outside the Shell), `/decks/new` (owner: draft with Claude or import a pack), `/settings`.
- Pictures need the sign-in: `components/AuthImage.jsx` loads them as blob URLs (`loadImage`, `preloadImages` for the next cards).
- Sail: ←/→ or swipe sideways for cards, ↑/↓ or tap for views, space plays (seconds per view saved in localStorage), `i` for more, Esc closes. Quiz: space shows the answer, →/2 knew it, ←/1 not yet, swipe right/left.

## Commands

- Backend tests: `cd backend && python -m pytest`
- Run everything locally: `./run.sh` (backend on 5733, Vite dev server proxying to it)
- Frontend: `cd frontend && npm ci && npm run build && npx oxlint`
- Docker: `docker compose up -d` (published image) or `docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build`
- Collect a deck from the command line: `python -m app.cli collect <slug> [--force]`

## Conventions

- Mobile-first; check 390px and desktop widths.
- No demo mode, no bundled LLM.
- Commits end with the Co-Authored-By and Claude-Session trailers.
