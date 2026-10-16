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
- M0 (scaffold) done and on `main`.
- M1 (tournament engine) implemented and tested on `feature/m1-engine`; pending merge to `main` and push.
- Next: M2 (rooms, identity, lobby), once approved.

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
| Backend tests | `cd backend && uv run pytest` |
| Backend lint / format | `cd backend && uv run ruff check . && uv run ruff format .` |
| DB migrations | `cd backend && uv run alembic upgrade head` (new: `uv run alembic revision --autogenerate -m "msg"`) |
| Frontend deps | `cd frontend && pnpm install` |
| Frontend dev server | `cd frontend && pnpm dev` (proxies `/api/*` → `http://localhost:8000`) |
| Frontend tests / lint / types / build | `cd frontend && pnpm test`, `pnpm lint`, `pnpm typecheck`, `pnpm build` |
| Regenerate API types after backend API changes | `cd frontend && pnpm gen:api` (commit `src/api/schema.d.ts`) |

Backend config comes from env vars / `backend/.env` (see `backend/.env.example`).

## Git Workflow
- Never commit directly to `main`.
- Per milestone or feature: branch `feature/<name>` off `main` (e.g. `feature/m0-scaffold`).
- Per component: branch `<milestone>/<component>` off the feature branch (e.g. `m0/backend`). Test it and merge it into the feature branch with `--no-ff` — locally.
- Merge the feature branch into `main` only when every component is merged and all checks are green.
- Push to the remote (`origin`) only when a milestone/major feature is complete (feature branch + `main`), not after each component.

## Test-First
- Define the test cases before implementing any code: write the failing tests for a component first, then implement until they pass (see the `tdd` skill).

## Code Layout
- `backend/src/app/main.py` — FastAPI app factory and routes; `config.py` settings; `db.py` SQLAlchemy base/session.
- `backend/src/app/engine/` — pure tournament engine (`normalize`, `bracket`, `tally`); tests in `backend/tests/engine/`.
- `backend/migrations/` — Alembic revisions.
- `frontend/src/api/` — API client and generated `schema.d.ts`.

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
