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
- **Amended 2026-07-19:** self-hosting on a Pi (#9) triggered the clause above.
  Keeping Postgres anyway: it is the more marketable skill to demonstrate, and
  small multi-user access is now planned (#10), which restores the other half of
  the original rationale.

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

## 9. Hosting: Cloudflare frontend + Raspberry Pi backend (planned; local for now)

- **Requirements:** near-zero recurring cost; a real domain I own, with the app on
  a subdomain; PWA assets delivered fast with free TLS; single user for now, so
  backend uptime is a personal concern, not a customer one.
- **Choice:** frontend as a static PWA on Cloudflare under a subdomain of a
  purchased domain; backend + Postgres self-hosted on a Raspberry Pi, exposed via
  Cloudflare Tunnel (origin binds to localhost only — the tunnel is the sole way
  in). Interim: everything runs locally.
- **Rejected:** managed PaaS for the backend (Render/Fly/Railway) — recurring cost
  for a single-user app; serving the frontend from the Pi too — loses edge
  delivery and couples the web app's availability to home internet.
- **Would change my mind:** real multi-user traffic, or the Pi's ops burden
  (updates, backups, SD-card mortality) outweighing the hobby value.
- **Note:** this triggered the mind-changer recorded in #2 — resolved by amending
  #2: keeping Postgres (marketability + planned multi-user, see #10).

## 10. Auth: Cloudflare Access instead of building login

- **Requirements:** restrict the app to me now, later a handful of invited
  friends + demo viewers; identity needed per user once multi-user lands; zero
  password/session/reset code to write, secure by default; fits the #9 topology.
- **Choice:** Cloudflare Access in front of both the frontend and the API.
  The backend treats the `Cf-Access-Jwt-Assertion` JWT as the security boundary:
  verify signature against the team's public keys + the app's AUD tag, take the
  user's email from the verified claims. The bare
  `Cf-Access-Authenticated-User-Email` header is never trusted by itself.
  Multi-user then reduces to a `users` table keyed by email, and the Access
  policy is the invite list. Free Zero Trust plan covers 50 users — far beyond
  friends + demo scale.
- **Rejected:** building auth in FastAPI (passwords/OAuth/sessions) — real attack
  surface and maintenance for a friends-only app; revisiting Django for its auth
  batteries (#3) — still not paying rent when Cloudflare handles login entirely.
- **Would change my mind:** public signup beyond ~50 users, native mobile
  clients that can't ride a browser SSO flow, or deciding that hand-rolled auth
  itself is a skill worth demonstrating in this portfolio.

## 11. One-off task bounties (planned v1.5)

- **Requirements:** reward one-time aversive tasks ("file taxes") without
  corrupting the habit system. Habits and tasks are different machines: habits
  are about consistency (cues, streaks, tapering weights — never "done"), tasks
  are about completion. The overjustification worry doesn't apply to one-offs —
  there's no automaticity to build and no intrinsic motivation to crowd out;
  paying yourself to beat procrastination is extrinsic reward used correctly.
- **Choice:** split the paycheck pool into two channels — the habit pool keeps
  the permanent majority (75–80%; everything already designed, unchanged) and a
  bounty pool (20–25%) funds one-offs. Bounties are sized by aversiveness, not
  importance; unlock instantly on completion; leftover bounty money — unassigned
  budget and bounties on unfinished tasks alike — rolls into the next period's
  habit pool at payday. The deadline still costs you something real (the instant
  unlock is gone; the money must now be earned back through habits), but nothing
  is burned. Rollover lands only at the payday freeze point, so mid-week shares
  never change (#5). Encourage decomposing big tasks into small
  bounties (proximal subgoals beat distant lumps), and reuse the "after I ___"
  cue field as a when-then plan with a deadline. Separate `tasks` table sharing
  no machinery with habits/weeks; the week summary just adds bounty earnings to
  the unlocked total.
- **Rejected:** tasks competing for the habit pool — a busy task week would
  dilute frozen habit shares and a task-free week would inflate them, breaking
  the weekly-snapshot guarantee (#5); letting leftovers lapse entirely — sharper
  loss aversion, but punitive on a bad week and the money vanishes from the
  system for nothing; building it in v1 — it's a clean add-on precisely because
  it's decoupled, and the solo habit loop ships first.
- **Would change my mind:** if bounty money starts dominating in practice, the
  app is quietly becoming a paid todo list — rebalance toward the habit pool or
  cap open bounties. The habit loop is the point. And if deadlines lose their
  teeth because rolled-over money doesn't feel lost, revert failed-task bounties
  to hard lapse while still rolling over unassigned budget.

## 12. Multi-app future: separate products, shared infrastructure

- **Requirements:** more personal apps are coming (recipe tracker, etc.) and will
  live on the same Pi + Cloudflare setup (#9–10); personal projects get
  abandoned, rewritten, and resurrected on independent schedules; each repo
  should stay a clean, self-contained portfolio piece.
- **Choice:** coupling boundaries follow lifecycle boundaries. Each product is
  its own repo, its own process, its own database — a monolith within the
  product (this repo stays as scaffolded, per #1). Infrastructure is shared and
  multi-tenant: one Postgres server with a database per app (`CREATE DATABASE`
  is the whole provisioning step, one backup cron covers all), one cloudflared
  tunnel routing by hostname to per-app ports, one Cloudflare Access identity —
  every app reads the same verified identity, so SSO across the platform costs
  zero shared auth code. A FastAPI backend is a ~50 MB process under systemd;
  five of them is cheap. Planned evolution: extract shared code (e.g. the
  Access-JWT helper) into a tiny internal package only on the third
  copy-paste (rule of three); at 2–3 apps, move shared infra into a small infra
  repo with docker-compose (Postgres, cloudflared, one container per app) so
  "set up the Pi" becomes one command.
- **Rejected:** one shared mega-backend for all apps — unrelated things
  shouldn't fail together; dead projects would block the living ones' upgrades,
  deploys, and test suites, and one sprawling multi-app repo tells a worse
  portfolio story than five self-contained ones. Also rejected: building the
  shared library or compose setup now, before duplication actually exists.
- **Would change my mind:** two apps needing to share domain data (not just
  identity) — that's when the database-per-app boundary gets rethought; or a
  single product genuinely outgrowing one process.

## 13. Static analysis: pyright strict, invariant-mapped ruff rules, ESLint

- **Requirements:** the repo's core invariants are mechanical enough to enforce
  by tooling — integer cents in money paths, local-date math in `APP_TIMEZONE`,
  no blocking calls in async handlers, hooks discipline in a
  learning-the-frontend React codebase. Tooling should be boring (#3's
  innovation-token logic applies here too) and the editor must agree with CI.
- **Choice:** pyright in strict mode over `app/` + `tests/` — viable because
  SQLAlchemy 2.0's ORM and Pydantic v2 are natively typed and the codebase is
  small; pinned exact since pyright releases weekly and new versions add new
  errors. Ruff gains `DTZ` and `ASYNC` (each is an invariant as a lint rule)
  plus low-noise quality sets `SIM`, `C4`, `RUF`, `PT`. Frontend: ESLint flat
  config with typescript-eslint + react-hooks + react-refresh. All three run in
  CI alongside the existing checks.
- **Rejected:** mypy — equally sound, but pyright is what Pylance already runs
  in VS Code, so editor and CI can't drift. pyrefly (Meta) and ty (Astral) —
  promising Rust checkers, still pre-1.0; their differentiator is
  monorepo-scale speed, worth nothing at 500 lines, while maturity and
  ecosystem recognition are worth a lot. pylint — near-fully duplicated by
  ruff. Prettier — deferred until formatting inconsistency actually hurts.
- **Would change my mind:** ty hitting stable with ruff-level polish (one
  Astral toolchain is appealing — revisit then); or strict mode generating
  sustained ignore-comment noise as real app code grows — drop to standard
  mode rather than normalize suppressions.
