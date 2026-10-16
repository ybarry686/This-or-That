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
- Build plan drafted in PLAN.md (M0–M4, v2).
- Next step: owner approval of the plan, then M0 (scaffold).

## Stack (decided)
- **Backend** (`backend/`): Python, FastAPI (REST + native WebSockets), SQLAlchemy 2, Alembic, PostgreSQL, Pydantic. Managed with `uv`; tests with pytest.
- **Frontend** (`frontend/`): Vite + React + TypeScript, React Router, TanStack Query, Zustand (WS-driven state), Tailwind, Motion. Managed with `pnpm`; tests with vitest (Playwright later).
- **Local env:** Docker Compose (`api`, `postgres`, `web`). Single instance; hosting chosen later.

## Commands
_To be filled in during M0._

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
