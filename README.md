# This or That

**Settle any group decision with a head-to-head tournament.**

Real-time multiplayer web app: everyone submits options, the bracket fills itself, and the room votes matchup by matchup until one champion is left.

![Status](https://img.shields.io/badge/status-in%20development-orange)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1?logo=postgresql&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-646CFF?logo=vite&logoColor=white)
![Docker](https://img.shields.io/badge/Docker%20Compose-2496ED?logo=docker&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

---

## Overview

Where should we eat? Which movie tonight? What do we name the project? Group chats are bad at these questions. **This or That** turns them into a party game.

A host creates a room around a question and shares a 6-character code. Friends join from their own phones or laptops (no accounts needed) and secretly submit their options. When the tournament starts, the options drop into a single-elimination bracket, and the whole room votes on one matchup at a time — *Pizza vs. Tacos* — until a champion is crowned.

The backend is authoritative: clients only *ask* to do things, and the server decides outcomes, so everyone always sees the same bracket, the same votes, and the same winner.

> **Project status:** milestones **M0–M2** are complete — rooms, guest identity, the lobby, real-time updates, and the full tournament engine. Live voting (M3) and the retro-arcade presentation (M4) are next. See [Roadmap](#roadmap).

## Key Features

**Available now**

- **Rooms without accounts** — create a room, share a code or invite link; guests join with just a nickname (clashes are auto-suffixed: `Sam` → `Sam 2`)
- **Secure guest identity** — each participant gets a random per-room token (stored hashed server-side), so reloading or reconnecting keeps your seat
- **Host recovery link** — shown once at creation; reclaims host controls from any device if you lose your browser data
- **Hidden submissions** — you see only your own options and the total count; the full field stays secret until the bracket drops
- **Smart duplicate merging** — `Pizza`, ` PIZZA ` and `pizza!` become one option while remembering *everyone* who suggested it; the host can also merge near-duplicates (`Pizza Hut` → `Pizza`) or remove options
- **Live lobby** — joins, presence (online/offline), submissions and settings changes stream to every device instantly over WebSockets, with automatic reconnect and catch-up
- **Host hand-off** — if the host disappears from the lobby for 2 minutes, the longest-present connected player takes over
- **Tournament engine** — seeded, reproducible brackets for 2–64 options with evenly spread byes, one-at-a-time play, and a tie rule that can never stall the bracket

**Coming next**

- Live head-to-head voting with server-owned timers, "7/10 voted" progress, and KO-style reveals (M3)
- Retro arcade look — pixel headings, CRT glow, VS slams, 8-bit sound (muted by default), reduced-motion support (M4)
- Shareable read-only results page (M4)

## How a Game Works

```
 LOBBY                          TOURNAMENT                               RESULTS
 ─────                          ──────────                               ───────
 Host creates room ──┐
 Friends join by code│          Bracket drops (seeded shuffle,
 Everyone submits    ├─ start ─▶ byes spread evenly)                ──▶  Champion reveal
 options (hidden)    │          Matchup 1: A vs B ── room votes ──┐       Read-only results
 Host curates        │          Matchup 2: C vs D ── room votes   │       page (30 days)
 duplicates ─────────┘          ...one at a time, round by round ◀┘
```

Voting rules (implemented in M3):

| Rule | Behavior |
|---|---|
| **Voting closes** | when every connected player has voted, the timer expires (default 30 s), or the host ends it |
| **Vote changes** | allowed until voting closes; non-voters abstain |
| **Ties** | one 15 s sudden-death revote, then a server-side coin flip |
| **Late joiners** | can vote from the next matchup; can't submit |
| **Disconnects** | never block a matchup — the timer always resolves it |

The complete rule set lives in [SPEC.md](SPEC.md).

## Architecture

```
                         Browser (one per player)
 ┌───────────────────────────────────────────────────────────────┐
 │  React + TypeScript (Vite)                                    │
 │  pages/  Landing · RoomPage · Recover                         │
 │  components/  Lobby · HostPanel                               │
 │  api/client.ts (typed REST)   realtime.ts (WS + reconnect)    │
 │  session.ts (per-room token in localStorage)                  │
 └───────────────┬──────────────────────────────▲────────────────┘
                 │ REST  /api/*                 │ WebSocket /api/rooms/{code}/ws
                 ▼                              │ {type, version, data}
 ┌───────────────────────────────────────────────────────────────┐
 │  FastAPI (single process, authoritative)                      │
 │                                                               │
 │  rooms/      routes → service ──────────┐  realtime/          │
 │  (REST)      validates, authorizes,     │  hub: sockets,      │
 │              locks room row, bumps      │  presence, timers,  │
 │              version, commits ──────────┼─▶broadcast events   │
 │                                         │                     │
 │  engine/     normalize · bracket · tally   (pure, no I/O)     │
 └─────────────────────────────┬─────────────────────────────────┘
                               │ SQLAlchemy 2 + Alembic
                               ▼
                     ┌───────────────────┐
                     │   PostgreSQL 17   │  rooms · participants · submissions
                     └───────────────────┘
```

### Data Flow

**A change in the lobby (e.g. submitting an option)**

```
Player clicks "Add option"
  → POST /rooms/{code}/submissions  (Authorization: Bearer <token>)
  → service locks the room row, validates text + limits, finds the merge key
  → room.version += 1, commit
  → hub broadcasts {type: "submissions_changed", version, data: {option_count}}
  → every connected client refetches GET /rooms/{code} (its own filtered snapshot)
```

**Staying in sync**

Every state change bumps a monotonically increasing room `version`. Events carry that version, and clients refetch the REST snapshot on every event, on every (re)connect, or when they spot a gap — so a dropped connection can never leave a player with stale state. Snapshots are filtered per viewer: only the host ever receives other players' option texts during the lobby.

## Tournament Engine

`backend/src/app/engine/` is pure Python (no database, no network) and exhaustively tested for every bracket size from 2 to 64.

**Normalization** — duplicate detection key:

```
trim → collapse whitespace → case-fold → strip trailing punctuation
"  Deep   Dish PIZZA!! "  →  "deep dish pizza"
```

**Bracket generation**

1. Shuffle contenders with a stored random seed (same seed ⇒ same bracket)
2. Pad to the next power of two; the difference becomes byes
3. Place byes in bit-reversed matchup order so they spread across the bracket (the two halves never differ by more than one bye)
4. Byes only ever occur in round 1 and auto-advance

**Matchup resolution**

| Votes | First vote | Revote |
|---|---|---|
| One side has more | `WINNER` | `WINNER` |
| Tied (including 0–0) | `REVOTE` | `COIN_FLIP` (injectable RNG) |

## API

All endpoints except create, join and recover require `Authorization: Bearer <participant token>`.

| Method | Endpoint | Who | Purpose |
|---|---|---|---|
| `POST` | `/rooms` | anyone | Create a room → code, token, host recovery token |
| `POST` | `/rooms/{code}/join` | anyone | Join with a nickname → token |
| `GET` | `/rooms/{code}` | participant | Room snapshot (filtered for the viewer) |
| `PATCH` | `/rooms/{code}` | host | Update title, description, or settings (lobby only) |
| `POST` | `/rooms/{code}/submissions` | participant | Submit an option |
| `DELETE` | `/rooms/{code}/submissions/{id}` | owner | Delete your own option |
| `POST` | `/rooms/{code}/contenders/merge` | host | Merge one option into another |
| `POST` | `/rooms/{code}/contenders/remove` | host | Remove an option |
| `POST` | `/rooms/{code}/host/transfer` | host | Hand the host role to another player |
| `POST` | `/rooms/{code}/host/recover` | recovery token | Reclaim the host role |
| `WS` | `/rooms/{code}/ws?token=…` | participant | Real-time events |

Interactive docs are served at **http://localhost:8000/docs** while the API is running.

**WebSocket events:** `welcome`, `participant_joined`, `participant_connected`, `participant_disconnected`, `settings_changed`, `submissions_changed`, `host_changed`. Close codes: `4401` invalid token, `4404` unknown room.

**Room settings**

| Setting | Default | Range |
|---|---|---|
| Max participants | 20 | 2–50 |
| Options per person | 3 | 1–10 |
| Vote timer | 30 s | 10–120 s |
| Options to start | — | 2–64 unique |

## Getting Started

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) — runs the whole stack
- For local development without Docker: Python 3.12+ with [uv](https://docs.astral.sh/uv/), Node.js 24+ with [pnpm](https://pnpm.io/)

### Run with Docker (recommended)

```bash
git clone https://github.com/ybarry686/This-or-That.git
cd This-or-That
docker compose up --build
```

Open **http://localhost:5173**. The API runs on `:8000` and PostgreSQL on `:5432`; database migrations are applied automatically on startup. Stop everything with `docker compose down`.

**Try it with friends on the same Wi-Fi:** open `http://<your-computer's-IP>:5173` on a phone.

**Try multiple players on one computer:** use a normal window plus a private/incognito window (or a second browser) — tabs in the same browser profile share one identity.

### Run for development

```bash
# Database only
docker compose up -d postgres

# Backend (terminal 1)
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload

# Frontend (terminal 2)
cd frontend
pnpm install
pnpm dev          # proxies /api/* (including WebSockets) to localhost:8000
```

Backend configuration comes from environment variables or `backend/.env` — see [`backend/.env.example`](backend/.env.example).

## Testing

```bash
# Backend: engine, REST API, WebSocket, model, migration and concurrency tests
docker compose up -d postgres
cd backend && uv run pytest

# Frontend: component, page and client tests (fetch + WebSocket mocked)
cd frontend && pnpm test

# Quality checks
cd backend  && uv run ruff check . && uv run ruff format --check .
cd frontend && pnpm lint && pnpm typecheck && pnpm build
```

| Suite | Tests | Covers |
|---|---|---|
| Backend | 270 | tournament engine (all sizes 2–64), permissions, validation, snapshots, events, presence, host hand-off, migrations, parallel submissions |
| Frontend | 30 | create/join flows, lobby, host panel, session storage, API client, WebSocket refresh and reconnect |

GitHub Actions runs every suite (with a PostgreSQL service) on each push.

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | React 19 + TypeScript + Vite | UI |
| Frontend | React Router, TanStack Query | Routing, server state |
| Frontend | Tailwind CSS | Styling |
| Backend | FastAPI | REST API + native WebSockets |
| Backend | SQLAlchemy 2 + Alembic | ORM + migrations |
| Backend | Pydantic | Validation, OpenAPI schema |
| Data | PostgreSQL 17 | Source of truth |
| Contracts | openapi-typescript | Frontend types generated from the API schema |
| Tooling | uv, pnpm, Ruff, oxlint, pytest, Vitest | Packages, linting, tests |
| Infra | Docker Compose, GitHub Actions | Local stack, CI |

## Project Structure

```
This-or-That/
├── backend/
│   ├── src/app/
│   │   ├── main.py              # App factory, routers, error handling
│   │   ├── config.py            # Settings (env vars / .env)
│   │   ├── db.py                # SQLAlchemy engine + session
│   │   ├── models.py            # Room, Participant, Submission
│   │   ├── security.py          # Token generation + hashing
│   │   ├── errors.py            # Domain errors → HTTP status codes
│   │   ├── engine/              # Pure tournament logic
│   │   │   ├── normalize.py     #   option validation + duplicate merging
│   │   │   ├── bracket.py       #   seeding, byes, advancement
│   │   │   └── tally.py         #   vote resolution + tie fallback
│   │   ├── rooms/               # Lobby REST API
│   │   │   ├── schemas.py       #   request/response models
│   │   │   ├── service.py       #   business rules
│   │   │   └── routes.py        #   endpoints + event publishing
│   │   └── realtime/            # WebSockets
│   │       ├── hub.py           #   socket registry, broadcast, timers
│   │       └── routes.py        #   room socket, presence, host hand-off
│   ├── migrations/              # Alembic revisions
│   ├── tests/                   # engine/ unit tests, api/ integration tests
│   └── scripts/export_openapi.py
├── frontend/
│   └── src/
│       ├── api/                 # Typed client + generated schema.d.ts
│       ├── pages/               # Landing, RoomPage, Recover
│       ├── components/          # Lobby, HostPanel, shared UI
│       ├── realtime.ts          # WebSocket hook with reconnect
│       ├── session.ts           # Per-room identity in localStorage
│       └── test/                # Fetch/WebSocket fakes, render helpers
├── .github/workflows/ci.yml     # CI
├── docker-compose.yml           # postgres + api + web
├── SPEC.md                      # Product specification + resolved decisions
├── PLAN.md                      # Milestones and status
└── CLAUDE.md                    # Contributor / AI-assistant conventions
```

## Roadmap

| Milestone | Scope | Status |
|---|---|---|
| **M0** | Scaffold: monorepo, Docker Compose, CI | ✅ Done |
| **M1** | Tournament engine: normalization, bracket, tally | ✅ Done |
| **M2** | Rooms, guest identity, lobby, real-time sync | ✅ Done |
| **M3** | Live voting, matchup flow, ties, champion | ⏳ Next |
| **M4** | Retro arcade UI, animations, sound, results page | Planned |
| **v2** | Tiebreaker mini-games, image options, public rooms, presenter view | Later |

Details and acceptance criteria are in [PLAN.md](PLAN.md).

## Development Workflow

- Specs first: product decisions live in [SPEC.md](SPEC.md) before code is written.
- Tests first: each component's test cases are written before its implementation.
- Branching: `main` ← `feature/<milestone>` ← `<milestone>/<component>`. Components are tested and merged into the feature branch; the feature branch merges into `main` only when everything is green.
- API contract: after backend API changes, run `pnpm gen:api` in `frontend/` to regenerate TypeScript types.

## Developer

**Yagouba Barry**

## License

This project is licensed under the [MIT License](LICENSE).
