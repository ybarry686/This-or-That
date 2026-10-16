# Product Specification — Decision Tournament

**Status:** Draft  
**Product name:** This or That  
**Specification version:** 0.2

## 1. Product Overview

Build a polished, real-time multiplayer web application that helps groups make decisions through a competitive, single-elimination tournament. Gamifying Decision-Making

A user creates a room around a question or decision. Other participants join, submit possible answers, and vote on head-to-head matchups. Winning options advance through a bracket until one final winner is determined.

Examples include:
- Where should our friends go on vacation?
- Which movie should we watch tonight?
- What should our group name its next project?
- Which restaurant should we try?

The product should combine the functionality of a collaborative decision-making tool with the excitement and presentation of a party game.

### Play model
- **Remote-first.** Every participant plays on their own device, which renders the full experience (matchups, bracket, reveals). This also works when the group is in the same physical room. There is no shared "TV"/presenter screen in v1.
- **One matchup at a time.** The whole room votes on the same matchup together, the result is revealed, then the next matchup begins.

## 2. Product Principles

1. **The game is the experience.** Tournament progression, matchups, voting, and winner reveals should feel engaging rather than like filling out a survey.
2. **The backend is authoritative.** Clients may request actions but cannot independently determine tournament outcomes.
3. **Everyone shares the same game state.** Room members should see consistent matchups, voting status, and round progression.
4. **Correctness precedes spectacle.** Animations and sound effects must not compromise voting integrity or tournament state.
5. **The architecture should be modular.** Room management, submissions, tournament logic, voting, and tiebreakers should have clear boundaries.
6. **Features ship incrementally.** Each version must be usable, testable, and documented before the next layer of complexity is added.

## 3. Users and Permissions

### Room host
- Create a room and define its settings.
- Share an invite link or room code.
- See all submissions during the lobby and curate them (merge or remove).
- Start the tournament when the room satisfies its requirements.
- Force-close voting on the current matchup.
- Transfer the host role to another participant.
- View room progress and final results.

The host is also a normal player: they submit options and vote like everyone else.

### Participant
- Join an eligible room.
- Submit options within the configured limit (lobby only).
- See their own submissions and the total option count during the lobby (not others' submissions).
- Vote in eligible matchups, including matchups that contain their own option.
- View the bracket, the champion, and the results page.

### Players and names
- A nickname is required: 1–20 characters, unique within the room. On a clash the server auto-suffixes it (e.g. `Sam` → `Sam 2`).
- Each participant is auto-assigned a retro avatar and color.

### Guest identity
No accounts in v1.

- **Establishment:** when someone creates or joins a room, the server issues a random, unguessable **participant token** scoped to that room. The client stores it in `localStorage` and sends it on every REST request and when opening the WebSocket. Tokens are stored hashed server-side.
- **Reconnect:** a client holding a valid token is reattached to the same participant record (nickname, submissions, votes).
- **Host protection:** host-only actions are authorized server-side by checking that the token belongs to the room's current host.
- **Host recovery:** at room creation the host is shown a private **host-recovery link** exactly once (`/r/<code>/recover#<token>`; the token stays in the URL fragment so it never reaches server logs). Opening it on any device issues a fresh token for the room creator's participant (revoking the old one) and makes them host again, even if the role had been transferred. The link stays valid for reuse.
- **Lost storage:** a participant who loses their token rejoins as a new participant. Their old record stays (and counts as disconnected).

### Host absence
- **During the tournament** the game runs itself: timers keep advancing matchups, so no host is required. Host controls resume when the host reconnects.
- **In the lobby**, if the host has been disconnected for **2 minutes**, the host role transfers automatically to the longest-present connected participant.
- The host can manually transfer the role at any time.

## 4. Room Configuration

Rooms are **private only** in v1: they are reachable solely via a 6-character room code or the invite URL. There is no public room browser.

| Setting | Default | Allowed range | Editable |
|---|---|---|---|
| Title / question | — (required) | 1–120 chars | Lobby only |
| Description | empty | 0–500 chars | Lobby only |
| Max participants | 20 | 2–50 | Lobby only |
| Max submissions per participant | 3 | 1–10 | Lobby only |
| Vote timer | 30 s | 10–120 s | Lobby only |
| Tie revote timer | 15 s | fixed in v1 | — |
| Visibility | private | private only in v1 | — |

All settings lock when the tournament starts. The host can still force-close the current matchup's voting.

### Lifecycle
`lobby` → `in_progress` → `finished` (or `expired`).

- Unstarted lobbies idle for **24 hours** expire.
- A finished room becomes a **read-only results page** (bracket and vote tallies) at a shareable URL, retained for **30 days**.
- **Play again** creates a new room with the same settings and invites the same participants.

## 5. Submission Collection

Participants submit options during the lobby phase.

- Options are **text-only** in v1: 1–80 characters after trimming.
- Validation happens on the backend; per-participant limits are enforced server-side.
- Submissions are **hidden** from participants during the lobby: each sees their own submissions and the total count. The host sees all submissions for curation. The full field is revealed with a "bracket drop" animation when the tournament starts.
- Participants may delete their own submissions during the lobby.
- Submissions are rejected once the tournament starts.
- The host can start the tournament only when there are **2–64 unique options**. Below 2 the start action is disabled with an explanation. Above 64, further submissions are rejected.

### Duplicate normalization
A submission's normalized key is computed by:
1. Trimming leading/trailing whitespace.
2. Collapsing internal whitespace runs to a single space.
3. Case-folding.
4. Stripping trailing punctuation.

Submissions with the same normalized key **auto-merge** into one contender. The contender keeps the display text of the first submission and records **every submitter** (attribution is never lost). The host can also manually merge or remove contenders in the lobby. A manual merge is sticky: a later submission whose text matches a merged-away option joins the merged contender.

## 6. Tournament Engine

The tournament uses a single-elimination bracket. The engine is a pure module with no I/O so it can be fully unit-tested.

- **Seeding:** at start the server shuffles the unique contenders using a random seed that is stored with the room, so the bracket is reproducible.
- **Byes:** the field is padded to the next power of two. Byes occur only in round 1, are spread evenly across the bracket (placed in bit-reversed matchup order, so the two halves differ by at most one bye), and auto-advance their contender. No contender receives more than one bye.
- Matchups are played **one at a time**, in bracket order (round by round, top to bottom).
- A winner advances only after its matchup is resolved; a contender cannot advance twice from the same matchup.
- Round and matchup outcomes are persisted.
- Resolving a matchup is idempotent: duplicate or concurrent resolve requests resolve it at most once (enforced with transactions and unique constraints).
- Progress survives reloads, reconnects, and server restarts.

## 7. Voting

During a matchup, eligible participants vote for one of the two options.

- **One vote per participant per matchup.** A participant may **change their vote** until voting closes; the last vote counts.
- Votes are bound to the room, round, and matchup.
- Merged duplicate submissions do not grant extra votes; votes are per participant, not per submission.
- **Eligibility:** any participant present when the matchup opens. Late joiners become eligible from the next matchup that opens.
- **Voting closes** when the first of these happens:
  1. Every *connected* eligible participant has voted.
  2. The vote timer expires (default 30 s).
  3. The host force-closes it.
- Eligible participants who did not vote **abstain**; abstentions are not counted.
- The winner is the option with more votes. Ties go to §8.
- **Live display:** during voting, clients see only progress ("7/10 voted", with avatars lighting up) — not the split. The tally is revealed at close.
- **Disconnects:** disconnected participants are excluded from the "everyone voted" check until they reconnect; the timer guarantees the matchup always closes.

## 8. Tiebreakers

### v1 fallback
1. A tied matchup (including zero votes cast) triggers one **sudden-death revote** with a 15 s timer and the same close rules as §7.
2. If the revote is still tied, the server performs a **random coin flip** and the result is shown with an animated reveal.

The bracket can never get stuck.

### v2 tiebreaker modes (out of scope for v1)
Tiebreakers will become separate, modular game modes, each specifying inputs, eligibility, duration, success condition, failure handling, and output, and each falling back to the coin flip.

- **Persuasion challenge:** advocates for each option present arguments; a defined vote decides.
- **Reaction-time challenge:** selected participants respond to a shared start signal; the backend decides using validated timestamps and a documented fairness policy.

## 9. Real-Time Synchronization

- **Authoritative source:** the backend. State lives in PostgreSQL; a single API process holds the live WebSocket connections.
- **Snapshot:** `GET` a room snapshot endpoint returns the full current state the caller is allowed to see, including a room `version`.
- **Events:** WebSocket messages carry an event type, payload, and the room `version`, which increases monotonically with every state change.
- **Recovery:** on connect, reconnect, or a detected version gap, the client refetches the snapshot. Clients never depend on receiving every event. (v1 client: refetches on every event.)
- **Connection:** `ws(s)://<host>/rooms/<code>/ws?token=<participant token>` (browsers cannot set auth headers on WebSockets). Invalid tokens close with code `4401`, unknown rooms with `4404`. The first message is `welcome` with the current version. Lobby events never include option texts, only the option count.
- **Timers:** owned by the server and sent as absolute deadlines (`ends_at`). Clients only render countdowns.

Events include: participant joined/left/connected/disconnected, host changed, settings changed, submission count changed, tournament started (bracket drop), matchup opened, vote progress changed, matchup closed (with tally), revote started, coin flip, round advanced, champion announced.

## 10. User Experience and Visual Design

### Visual identity: retro arcade
- Pixel/arcade font for headings; a readable font for body text.
- CRT glow and scanline effects (can be turned off).
- Fighting-game framing: "ROUND 1 — FIGHT!", VS slam transitions, KO-style tally reveals, a champion reveal with confetti and fanfare.
- 8-bit sound effects and optional chiptune background music.

### Core screens
1. Landing page and room creation.
2. Join-room flow (code entry / invite link, nickname).
3. Lobby and submission collection.
4. Head-to-head matchup screen.
5. Interactive bracket view.
6. Tie revote / coin-flip screen.
7. Champion reveal and read-only results page.

### Accessibility and audio
- Audio is **muted by default**; the user enables it.
- `prefers-reduced-motion` is honored: slams, shakes, and flicker become simple fades.
- Full keyboard support for voting and host actions.
- Usable mobile layouts.
- The interface stays functional if an animation, font, or sound fails to load.

Animations stay in sync with authoritative game state.

## 11. Technical Architecture

- **Backend:** Python, FastAPI (REST + native WebSockets), SQLAlchemy 2, Alembic migrations, PostgreSQL, Pydantic schemas. Single process.
- **Frontend:** Vite + React + TypeScript, React Router, TanStack Query for REST, a WebSocket client feeding a Zustand store, Tailwind CSS, Motion for animations. TypeScript API types are generated from the FastAPI OpenAPI schema.
- **Repo layout:** monorepo with `backend/` and `frontend/`.
- **Tooling:** `uv` (Python), `pnpm` (JS), pytest, vitest, Playwright later for end-to-end tests.
- **Local development and deploy:** Docker Compose (api + postgres + web). v1 assumes a single instance; a hosting provider is chosen later.

## 12. Nonfunctional Requirements

- Validate all client inputs on the backend.
- Enforce host permissions and participant eligibility server-side.
- Protect against duplicate votes and duplicate state transitions.
- Handle disconnects, reconnects, and stale client state.
- Use database transactions where needed to preserve tournament invariants.
- Provide actionable errors rather than silently failing.
- Include automated tests for tournament rules and critical API behavior.
- Keep secrets and environment-specific configuration out of source control.
- Provide reproducible local development instructions.

Performance targets and maximum supported concurrent rooms should be established before performance claims are made.

## 13. Out of Scope for the Initial Release

Unless explicitly approved during planning:
- Required user accounts or social login.
- Payments or subscriptions.
- Multiple backend services or microservices.
- Distributed event infrastructure.
- AI-generated submissions or automated judging.
- Complex custom image generation.
- Advanced analytics and recommendation systems.
- Image options (uploads or URLs) — v2.
- Public rooms and room discovery — v2.
- Tiebreaker mini-games — v2.
- Shared presenter / "TV" view — v2.

## 14. Definition of Done

A feature is complete only when:
- Its acceptance criteria are satisfied.
- Relevant automated tests pass.
- Error and edge cases are handled.
- Existing tests remain green.
- API and frontend contracts agree.
- Relevant documentation and development status are updated.
- The feature can be exercised locally using documented steps.
- No unrelated scope has been introduced without approval.

## 15. Resolved Decisions

Settled during planning (v0.2):

| Topic | Decision | Section |
|---|---|---|
| Play context | Remote-first, own devices; no presenter view in v1 | §1 |
| Pacing | One matchup at a time | §1, §6 |
| Room visibility | Private only (code + invite URL) | §4 |
| Guest identity & host recovery | Per-room token in localStorage; one-time host-recovery link | §3 |
| Host absence | Game self-runs; lobby auto-transfer after 2 min | §3 |
| Settings | Defaults/ranges table; lobby-editable, locked at start | §4 |
| Duplicate normalization | Trim, collapse whitespace, case-fold, strip trailing punctuation; auto-merge with full attribution | §5 |
| Lobby visibility | Hidden until start; host sees all | §5 |
| Seeding & byes | Stored-seed shuffle; round-1 byes spread evenly | §6 |
| Vote close | All connected voted / timer / host force | §7 |
| Vote changes | Allowed until close | §7 |
| Abstentions & late joins | Non-voters abstain; late joiners vote from next matchup, can't submit | §7 |
| Live tally | Hidden; progress only; reveal at close | §7 |
| Tie fallback (v1) | One 15 s revote, then server coin flip | §8 |
| Images | Text-only in v1 | §5, §13 |
| Visual identity | Retro arcade | §10 |
| Sound & motion | Muted by default; reduced motion honored; CRT toggle | §10 |
| Results & retention | Read-only results 30 days; idle lobbies expire after 24 h | §4 |
| Stack & deploy | FastAPI + Postgres; Vite React TS; Docker Compose | §11 |
