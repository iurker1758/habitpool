# HabitPool

HabitPool *(working name — rename freely)* is a habit-formation PWA where
completing daily habits unlocks a percentage of your
paycheck's "fun money" pool. Grounded in behavioral psychology: temptation
bundling, immediate reward feedback, streaks with slack, and reinforcement-schedule
thinning that automatically shifts reward weight toward the habits that still
need it.

> **Screenshot / GIF goes here** — this is the first thing anyone sees. Keep it current.

## How it works

- Each pay period you set a fun-money pool (e.g. $100). It starts locked.
- Every habit check-off unlocks a slice of the pool, visible instantly.
- Full-week streaks add a bonus; one "skip token" per habit per week keeps a
  single miss from nuking the streak (avoids the what-the-hell effect).
- As a habit becomes ingrained (weeks of ≥80% completion), its reward weight
  tapers toward a floor and the freed-up share flows to newer habits —
  reinforcement thinning, so extrinsic rewards fade as automaticity takes over.

## Stack

FastAPI + async SQLAlchemy + PostgreSQL · React + TypeScript + Vite PWA ·
pytest on the reward math (the code that actually deserves tests).

See [DECISIONS.md](DECISIONS.md) for why each of these — every choice is written
up as requirements → choice → rejected alternatives.

## Interesting problems

- **Idempotent check-offs**: offline retries and double-taps must never unlock
  money twice. Unique constraint on (habit, date); the API upserts.
- **Week boundaries**: weeks roll over at a fixed local timezone, and habit
  weights are computed once at rollover and frozen (`habit_weeks` snapshot) so
  unlocked percentages never jitter mid-week.
- **Reward math as pure functions**: all money logic lives in
  `backend/app/rewards.py` with no I/O, property-tested independently of the API.

## Quickstart

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then edit DATABASE_URL if yours differs
alembic upgrade head
uvicorn app.main:app --reload

# frontend (second terminal)
cd frontend
npm install
npm run dev   # proxies /api to the backend
```

Run the tests: `cd backend && pytest`

## How this was built

Scaffolded and pair-programmed with Claude. The reward-allocation design,
maturity curve, and edge-case handling are mine; see DECISIONS.md for the
reasoning trail.
