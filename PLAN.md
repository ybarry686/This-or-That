# Development Plan — This or That

Product requirements live in [SPEC.md](SPEC.md). This file tracks delivery order and status. Each milestone must meet the Definition of Done (SPEC §14) before the next one starts.

**Current milestone:** M4 — not started (M0–M3 done)

## M0 — Scaffold
**Goal:** an empty but runnable monorepo.

- [x] `backend/`: FastAPI app managed with `uv`, `/health` endpoint, pytest set up.
- [x] `frontend/`: Vite + React + TS app managed with `pnpm`, Tailwind, vitest set up.
- [x] `docker-compose.yml` with `api`, `postgres`, `web`; `.env.example` (no secrets committed).
- [x] SQLAlchemy + Alembic wired to Postgres with an initial empty migration.
- [x] OpenAPI → TypeScript type generation script.
- [x] CI runs backend and frontend tests and lint.
- [x] CLAUDE.md "Commands" section filled in.

**Acceptance:** `docker compose up` serves the web app, which calls `/health` successfully; CI is green.

**Status:** ✅ Done — verified 2026-10-16 (Compose: api `/health` OK direct and via web proxy, migration `0001` applied to Postgres; CI green).

## M1 — Tournament engine
**Goal:** pure, fully tested bracket logic with no I/O (SPEC §5 normalization, §6, §7 tallying, §8 fallback).

- [x] Option normalization and duplicate merging, keeping attribution.
- [x] Bracket generation from N contenders (2–64) using a seeded shuffle.
- [x] Bye placement: round 1 only, spread evenly, at most one per contender.
- [x] Matchup order (one at a time) and winner advancement; reject double advancement.
- [x] Tally resolution: winner, tie → revote, tie again → coin flip (injectable RNG).
- [x] Champion detection.

**Acceptance:** unit and property tests cover every N from 2 to 64, reproducible brackets for the same seed, and no invalid state transitions.

**Status:** ✅ Done (merged 2026-10-16) — 187 engine tests passing (188 backend total), ruff clean. Modules in `backend/src/app/engine/`:
- `normalize.py` — `validate_option_text`, `normalize_option`, `merge_submissions` (→ `Contender` with all submitter ids).
- `bracket.py` — `generate_bracket(ids, seed)` → `Bracket` with `current_matchup()`, `record_winner()`, `champion`. Byes are placed in bit-reversed matchup order so they spread across both halves (per-half counts differ by ≤ 1). Errors: `BracketError`, `MatchupNotPlayable`.
- `tally.py` — `resolve_matchup(a, b, votes, is_revote, rng)` → `Resolution` with `Outcome.WINNER` / `REVOTE` / `COIN_FLIP`.

Exhaustive parametrized tests over N = 2–64 stand in for property-based tests (no Hypothesis dependency added).

## M2 — Rooms, identity, lobby
**Goal:** people can create/join rooms and submit options in real time (SPEC §3, §4, §5, §9).

- [x] DB models and migrations: rooms, participants, submissions (contenders are derived from submission merge keys).
- [x] Create room (returns participant token and one-time host-recovery link); join by code/URL with nickname rules.
- [x] Token auth on REST and WS; hashed tokens; host-only authorization.
- [x] Settings CRUD with validated ranges; locked after start.
- [x] Submissions with limits, normalization/auto-merge, and hidden-until-start visibility; host merge/remove.
- [x] Snapshot endpoint and WS events with monotonic room `version`; client resync on gap/reconnect.
- [x] Host transfer (manual, plus lobby auto-transfer after 2 min disconnected).
- [x] Frontend: landing/create, join, lobby screens (functional styling).

**Acceptance:** two browsers can create/join, submit, and see consistent lobby state through reloads and reconnects; API tests cover permissions and validation.

**Status:** ✅ Done (2026-10-16) — 270 backend tests (API, WebSocket, models, migration, concurrency) and 30 frontend tests passing. Verified end to end on Docker Compose through the web proxy (create, join, two WebSocket clients, presence, submission event, snapshot version matches event version). Not yet clicked through by hand in two real browsers.
- Backend: `app/models.py`, migration `0002`; `app/rooms/` (`schemas`, `service`, `routes`); `app/realtime/` (`hub`, `routes`); `app/security.py`, `app/errors.py`.
- Frontend: `pages/` (`Landing`, `RoomPage`, `Recover`), `components/` (`Lobby`, `HostPanel`, `ui`), `realtime.ts` (WS + reconnect), `session.ts` (localStorage), `api/client.ts`.
- Choices made during build (also in SPEC): participants may delete their own submissions in the lobby; the host-recovery link stays valid and rotates the host token on each use; host merges are sticky (later submissions of a merged text join the merged option); clients refetch the snapshot on every WS event; Zustand not added yet (TanStack Query state was enough).

## M3 — Live voting & matchup flow
**Goal:** play a full tournament from start to champion (SPEC §6–§8).

- [x] Start tournament: freeze contenders, generate the bracket from the stored seed, bracket-drop event.
- [x] Matchup lifecycle with server-owned `ends_at` timers.
- [x] Voting: one per participant, changeable until close, eligibility and late joins.
- [x] Close rules: all connected voted / timer / host force — idempotent resolution.
- [x] Tie revote (15 s) and coin flip.
- [x] Round advancement and champion; room → `finished`.
- [x] Timer recovery after a server restart.
- [x] Frontend: matchup screen with voted-progress, bracket view, revote/coin-flip, champion screen.

**Acceptance:** a tournament with byes, ties, disconnects, and late joiners completes correctly; concurrency tests show no double votes or double resolutions.

**Status:** ✅ Done (2026-10-17) — 312 backend tests and 47 frontend tests passing. Verified end to end on Docker Compose: a two-player, 4-submission game (one merged duplicate → 3 contenders, one bye) played through the web proxy over WebSockets, closing each matchup early once both had voted, to a champion with events in order. Not yet clicked through by hand in two real browsers.
- Backend: models `Contender`, `Matchup`, `Vote` (migration `0003`); `app/tournament/` — `service` (start, vote, close phase, advance via the engine), `snapshot` (per-viewer tournament section), `timers` (deadlines, disconnect re-check, startup recovery), `routes`.
- Frontend: `components/Tournament.tsx` (matchup card, countdown on server clock, keyboard voting, revote banner, last result, bracket, champion); start button in `HostPanel`.
- Choices made during build (also in SPEC): a 5 s reveal pause before each voting window (`reveal_seconds`); eligibility is fixed when a matchup first opens and carries over to its revote; the host may close the open phase at any time.

## M4 — Arcade polish & results
**Goal:** the retro arcade experience (SPEC §10) and post-game features (SPEC §4 lifecycle).

- [ ] Visual system: arcade heading font, body font, palette, CRT effect with toggle.
- [ ] Animations: ROUND/FIGHT intros, VS slam, KO tally reveal, bracket progression, champion confetti.
- [ ] 8-bit SFX and chiptune, muted by default, with an audio toggle.
- [ ] Reduced-motion variants, keyboard voting, mobile layouts, graceful asset failure.
- [ ] Read-only results page (30-day retention); idle lobby expiry (24 h); Play again.
- [ ] Playwright end-to-end test of a full game.

**Acceptance:** a full game is playable on mobile and desktop with the motion/audio settings honored; the results link works after the game ends.

## v2 — Later
- Tiebreaker mini-games: reaction-time, persuasion (SPEC §8).
- Image options.
- Public rooms and discovery.
- Shared presenter / "TV" view.
- Hosting provider selection and production deploy.
