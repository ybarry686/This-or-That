# This or That - Gamifying Decision-Making

## Project Overview
This or That is a real-time multiplayer website where a group settles a decision through a single-elimination tournament. People join a private room, submit options, vote head-to-head one matchup at a time on their own devices, and crown a champion. It has a retro arcade look. v1 is the core loop; tiebreaker mini-games, images, public rooms, and a presenter view are planned for v2.

## Working Principles
- Discover before building. Use the grill-me skill to interview the project owner about product goals, user flows, edge cases, and trade-offs before making new consequential decisions.
- Ask one focused question at a time. Explain important trade-offs briefly, and do not silently make consequential product decisions.
- Distinguish confirmed requirements (SPEC.md) from suggestions. Record new unresolved questions.
- Do not begin a milestone until the owner has approved it.
- Prefer the simplest design that meets the agreed requirements. Do not introduce infrastructure, dependencies, or abstractions without a clear reason.
- Keep changes scoped, readable, and maintainable. Follow the repository's existing conventions once established.
- Add or update tests for meaningful behavior and run relevant checks before declaring work complete.
- Keep documentation current as decisions and implementation evolve. Update PLAN.md as milestones are completed or priorities change.
- Never claim a feature or test is complete unless it has actually been implemented or run. Call out checks that could not be run.

## Current Status
- Product discovery completed (grill-me session); decisions are recorded in SPEC.md v0.2 §15.
- Build plan in PLAN.md (M0–M4, v2). See PLAN.md for detailed status.
- v1 complete: M0 (scaffold), M1 (tournament engine), M2 (rooms, identity, lobby), M3 (live voting), M4 (arcade polish & results) done and on `main`.
- Next: v2 (tiebreaker mini-games, images, public rooms, presenter view, hosting) — needs planning and owner approval.

## Stack (decided)
- **Backend** (`backend/`): Python, FastAPI (REST + native WebSockets), SQLAlchemy 2, Alembic, PostgreSQL, Pydantic. Managed with `uv`; tests with pytest.
- **Frontend** (`frontend/`): Vite + React + TypeScript, React Router, TanStack Query, Zustand (WS-driven state), Tailwind, Motion. Managed with `pnpm`; tests with vitest (Playwright later).
- **Local env:** Docker Compose (`api`, `postgres`, `web`). Single instance; hosting chosen later.

## Commands
Run from the repo root unless noted.

| Task | Command |
|---|---|
| Whole stack (web :5173, api :8000, postgres :5432) | `docker compose up --build` |
| Backend deps | `cd backend && uv sync` |
| Backend dev server | `cd backend && uv run uvicorn app.main:app --reload` |
| Backend tests | `docker compose up -d postgres` then `cd backend && uv run pytest` |
| Backend lint / format | `cd backend && uv run ruff check . && uv run ruff format .` |
| DB migrations | `cd backend && uv run alembic upgrade head` (new: `uv run alembic revision --autogenerate -m "msg"`) |
| Frontend deps | `cd frontend && pnpm install` |
| Frontend dev server | `cd frontend && pnpm dev` (proxies `/api/*` → `http://localhost:8000`) |
| Frontend tests / lint / types / build | `cd frontend && pnpm test`, `pnpm lint`, `pnpm typecheck`, `pnpm build` |
| End-to-end (needs the stack running) | `docker compose up --build -d` then `cd frontend && pnpm e2e` (first time: `pnpm exec playwright install chromium`); screenshots land in `frontend/test-results/screens/` |
| Regenerate API types after backend API changes | `cd frontend && pnpm gen:api` (commit `src/api/schema.d.ts`) |

Backend config comes from env vars / `backend/.env` (see `backend/.env.example`).

## Git Workflow
- Never commit directly to `main`.
- Per milestone or feature: branch `feature/<name>` off `main` (e.g. `feature/m0-scaffold`).
- Per component: branch `<milestone>/<component>` off the feature branch (e.g. `m0/backend`). Test it and merge it into the feature branch with `--no-ff` — locally.
- Merge the feature branch into `main` only when every component is merged and all checks are green.
- Push to the remote (`origin`) only when a milestone/major feature is complete, not after each component.
- After the milestone is merged into `main` and pushed, delete all of its branches (component and feature, local and remote). Only `main` should remain between milestones.

## Test-First
- Define the test cases before implementing any code: write the failing tests for a component first, then implement until they pass (see the `tdd` skill).

## Code Layout
- `backend/src/app/main.py` — FastAPI app factory, router registration, `AppError` → JSON handler; `config.py` settings; `db.py` SQLAlchemy base/session.
- `backend/src/app/models.py` — `Room`, `Participant`, `Submission`, `Contender`, `Matchup`, `Vote`.
- `backend/src/app/rooms/` — lobby REST API: `schemas` (Pydantic), `service` (business rules; every mutation locks the room row, bumps `version`, commits), `routes` (HTTP + event publishing).
- `backend/src/app/realtime/` — `hub` (in-process socket registry, broadcast, timers) and `routes` (room WebSocket, presence, lobby host hand-off).
- `backend/src/app/tournament/` — `service` (start, vote, close phase, advance the bracket via the engine; returns events), `snapshot` (tournament section of the snapshot), `timers` (one deadline timer per room, re-synced from the DB after every change; disconnect re-check; startup recovery), `routes`.
- `backend/src/app/engine/` — pure tournament engine (`normalize`, `bracket`, `tally`).
- `backend/src/app/rooms/cleanup.py` — retention (idle lobbies expire after 24 h; finished/expired rooms deleted after 30 days), run hourly from `main.py`'s lifespan.
- `backend/src/app/security.py` (tokens, hashing), `errors.py` (domain errors → HTTP status).
- `backend/tests/` — `engine/` unit tests; `api/` REST + WebSocket tests (need Postgres: `docker compose up -d postgres`); `conftest.py` creates/truncates the `this_or_that_test` DB.
- `backend/migrations/` — Alembic revisions.
- `frontend/src/api/` — typed fetch client and generated `schema.d.ts`; `session.ts` (localStorage identity); `realtime.ts` (WS hook with reconnect).
- `frontend/src/settings.ts` (per-device sound/music/CRT/motion settings), `audio.ts` (Web Audio synth: cues + chiptune), `announcements.ts` (state-driven call-outs); `index.css` holds the theme tokens and CRT overlay.
- `frontend/src/pages/` — `Landing`, `RoomPage` (join form or room), `Recover`, `Results` (public results); `components/` — `Lobby` (loads the room; lobby view or `Tournament`), `HostPanel` (start, curation, settings), `Tournament` (matchup, bracket, champion, post-game), `Announcer`, `SettingsBar`, `ui`.
- `frontend/e2e/` — Playwright game test (`game.spec.ts`) and warm-up `global-setup.ts`.
- `frontend/src/test/helpers.tsx` — `mockApi` fetch stub, `FakeWebSocket`, `renderRoute`, `makeSnapshot`, `makeTournamentSnapshot`.

## Engineering Conventions
- **The backend is authoritative.** Clients request actions and never decide outcomes. Validate inputs and permissions server-side.
- **The tournament engine is pure.** Keep bracket, seeding, tally, and tie logic free of I/O and DB access, with an injectable RNG, and fully unit-tested.
- **Sync model:** a REST snapshot plus WS events, each carrying a monotonic room `version`. Clients refetch the snapshot on reconnect or a version gap. Timers are server-owned `ends_at` deadlines.
- **Integrity:** use transactions and unique constraints so votes and matchup resolutions are idempotent.
- **API contracts:** frontend types are generated from the FastAPI OpenAPI schema. Don't hand-write duplicate types.
- **Scope:** don't build v2 items without approval.
- **Done** means the SPEC.md §14 Definition of Done is met and the PLAN.md checklist is updated.
- Keep secrets out of git; use `.env` (with a committed `.env.example`).

## Sources of Truth
- CLAUDE.md: persistent instructions and current project context.
- PLAN.md: milestones, progress, and next steps.
- SPEC.md: product requirements and resolved design decisions (§15).
- Update these files when the project state changes. If documents conflict, surface the conflict instead of guessing.
