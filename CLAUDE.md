# HabitPool

Habit-formation PWA: completing daily habits unlocks slices of a weekly "fun money"
pool. Monorepo: `backend/` (FastAPI + async SQLAlchemy + Postgres) and `frontend/`
(Vite + React + TypeScript PWA). Why-docs live in `DECISIONS.md`.

Deployed (DECISIONS.md #9–10): frontend on Cloudflare Pages under a subdomain
of an owned domain; backend + Postgres on a home mini PC behind Cloudflare
Tunnel, with the SPA reaching the API through a same-origin Pages Function proxy
(`frontend/functions/api/[[path]].ts`); Cloudflare Access gates the frontend and
the backend validates the `Cf-Access-Jwt-Assertion` JWT on every request
(`app/auth.py`), never trusting the bare email header. The sibling app (umalab)
runs on the same platform but uses its own Discord login; that is umalab-only —
HabitPool stays on Access. Backend deploys are a server-side poll that pulls
`main` once the tip's CI is green. Hostnames, AUD tags and `API_ORIGIN` live in
the Cloudflare dashboard and the server's `.env`, never in the repo.

Planned v1.5 (DECISIONS.md #11): one-off task bounties paid from a separate bounty
channel of the pool — tasks must never share machinery with the habit/week snapshot
system, and the habit pool keeps the permanent majority of the money.

This repo is one product on a future multi-app platform (DECISIONS.md #12): apps
share infrastructure (Postgres server, tunnel, Cloudflare zone) but never code,
databases, or processes — no cross-app coupling lands in this repo.

## Commands

Backend (from `backend/`, venv in `.venv/`):

- Install: `pip install -e ".[dev]"`, then `cp .env.example .env`
- Config: `app/config.py` (pydantic-settings) — env vars override `.env` override defaults
- Run: `uvicorn app.main:app --reload` (migrations must be applied first)
- Migrations: `alembic upgrade head` · new: `alembic revision --autogenerate -m "..."`
- Test: `pytest` · Lint: `ruff check .` · Types: `pyright` (strict; run with the
  venv active so it resolves site-packages)

Frontend (from `frontend/`):

- `npm run dev` (proxies `/api` to `:8000`) · `npm run build` (typechecks via
  `tsc -b`) · `npm run lint` (ESLint incl. react-hooks rules) · `npm test`
  (vitest, pure modules only — `src/**/*.test.ts`)

Docs: `npx markdownlint-cli2` from the repo root lints all Markdown (rules in
`.markdownlint.jsonc`; CI runs it as the `docs` job).

## Invariants — do not break

- Money is integer cents; pool shares are integer permille. Never floats in stored money.
- `app/rewards.py` stays pure — no I/O, no ORM imports. All money logic lives there.
- Check-offs are idempotent: unique `(habit_id, day)` constraint, upsert endpoint.
- Weekly shares are frozen in `habit_weeks` at rollover; never recompute mid-week.
- All day/week math uses local dates in `APP_TIMEZONE` (`models.py`); weeks start Monday.
- Schema changes go through Alembic migrations, not `create_all`.

## Conventions

- Commits and PR titles follow Conventional Commits: `type(scope): summary` with
  types `feat|fix|docs|test|refactor|chore|ci` and optional scope `backend|frontend`.
  Squash-merge only — the PR title becomes the commit on `main`. See CONTRIBUTING.md.
- Branches: `<type>/<short-slug>`, e.g. `feat/streak-bonus`.
- Every non-obvious tech/design choice gets a `DECISIONS.md` entry:
  Requirements → Choice → Alternatives rejected → What would change my mind.
- The `test_rewards.py` TDD backlog is complete (`habit_weight` in PR #17,
  `week_streak_result` in PR #18, both implemented on request) — no
  owner-reserved tests remain.
