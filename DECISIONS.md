# Decisions

Format for every entry: **Requirements → Choice → Alternatives rejected → What would change my mind.**
Keep adding entries as the build evolves. This file is the interview.

## 1. One repository (monorepo)

- **Requirements:** one developer; frontend and backend change together
  (an API change and its consumer land in the same commit); employers should
  grasp the whole project from a single README.
- **Choice:** single repo with `backend/` and `frontend/`.
- **Rejected:** two repos — buys independent deploy cadence and access control,
  neither of which exists for a solo project; costs atomic commits and splits
  the portfolio story in half.
- **Would change my mind:** separate teams, or the frontend gaining a second
  backend consumer.

## 2. PostgreSQL over SQLite

- **Requirements:** single user, tiny write volume — but the weekly rollover
  (freeze weights + open new week) must be atomic or money math corrupts;
  hosting is managed; multi-user is a plausible future.
- **Choice:** Postgres.
- **Rejected:** SQLite — honestly sufficient for a single-user app and the
  simpler ops story if self-hosting. Chose Postgres because managed hosting
  makes its marginal cost ~zero, and a future multi-user version means no
  migration.
- **Would change my mind:** if this stayed forever single-user on a box I
  administer myself.

## 3. FastAPI over Flask/Django

- **Requirements:** payloads are money calculations — malformed data must fail
  loudly at the boundary; the reward logic needs to be trivially testable;
  backend familiarity = velocity (the frontend is the learning surface, per
  "choose boring technology" — spend innovation tokens in one place).
- **Choice:** FastAPI with Pydantic schemas.
- **Rejected:** Flask (no typed contracts without bolt-ons), Django (batteries
  I don't need — admin, auth — for a single-user API).
- **Would change my mind:** if the app grew real auth/admin needs, Django's
  batteries start paying rent.

## 4. React + TypeScript PWA over native Android / React Native

- **Requirements:** installable on Android, offline-tolerant (habits complete
  in a bathroom), push notifications, one codebase reaching phone + desktop,
  zero app-store overhead; learning React/TS is an explicit goal.
- **Choice:** Vite + React + TS with `vite-plugin-pwa`; typed contracts end to
  end (TS on the client, Pydantic on the server).
- **Rejected:** React Native/Expo — device builds and config overhead for zero
  feature gain at this scope; native Kotlin — abandons the learning goal.
- **Would change my mind:** needing widgets, background sensors, or
  iOS-quality notifications.

## 5. Weekly weight freeze (snapshot over compute-on-read)

- **Requirements:** the unlocked percentage must never change for reasons the
  user didn't cause; historical weeks must be stable for the review screen.
- **Choice:** compute each habit's share once at week rollover, freeze it in a
  `habit_weeks` row. Classic denormalization trade: storage + staleness for
  read consistency and trust in the numbers.
- **Rejected:** computing weights on every read — simpler code, but shares
  would jitter mid-week as trailing completion rates move.

## 6. Money in integer cents

- **Requirements:** percentages of dollar amounts, summed repeatedly, must be
  exact.
- **Choice:** integer cents everywhere; formatting is the frontend's job.
- **Rejected:** floats (rounding drift), Decimal columns (correct but heavier
  than needed when cents suffice).

## 7. Idempotent check-offs

- **Requirements:** offline queue retries and double-taps must not unlock money
  twice.
- **Choice:** unique constraint on `(habit_id, date)`; the check-off endpoint
  is an upsert that returns success either way.
- **Rejected:** client-side dedup only — the server is the source of truth;
  never trust the network to deliver exactly once.

## 8. Week boundary & timezone

- **Requirements:** "Sunday 11:58pm floss" must count for the week the user
  experienced, regardless of server timezone or DST.
- **Choice:** all week math in a single configured IANA timezone
  (`America/New_York`); weeks start Monday 00:00 local; check-off dates are
  local dates, not UTC timestamps.
- **Rejected:** UTC everywhere — correct for servers, wrong for humans whose
  habits happen at local bedtime.
