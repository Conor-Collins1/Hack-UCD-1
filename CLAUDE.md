# CLAUDE.md: shared contract for every AI assistant on this repo

You are helping one of three people build **Library Status** for HackUCD 2026 (5-hour build).
Students tap a button to report whether the UCD library is Not full / ~80% full / Full. The app
combines reports into a live status, flags people who keep giving false reports, summarises
comments with AI (OpenRouter), alerts premium subscribers, and has a leaderboard.

Use the person identified in the conversation (Conor is Person 1); ask only if unknown, then read their plan
file in `plan/`. The full plan and algorithms are in `README.md`.

## Rules (read these first)

1. **Only edit files your person owns** (table below). If you need something changed in
   someone else's file, stop and tell your human what to ask for. Do not "quickly fix" it.
2. **Do not change anything in the Contract section** (tables, endpoints, JSON shapes,
   shared functions) unless your human confirms the team agreed. If it changes, update
   this file in the same commit.
3. **Keep it simple.** This is a 5-hour hackathon. No new frameworks, no build step,
   no extra services. Use what is in `requirements.txt`; ask before adding a package.
4. **Always use `clock.now()`**, never `datetime.now()`/`utcnow()`. Wrap datetimes read
   from the DB in `clock.as_utc()` (SQLite drops timezones).
5. **Every error returns JSON** `{"error": "<message a student can understand>"}` with a
   sensible HTTP status. Never let an exception from OpenRouter, Stripe or ntfy break a request.
6. **Insert user text with `textContent`**, never `innerHTML`. Comments are untrusted input,
   including when sent to the AI.
7. **Never commit secrets.** Keys live in `.env` (gitignored). Stripe keys must be `sk_test_`.
8. **Run `pytest` before every commit**, and add tests for what you build (ordinary,
   boundary and failure inputs; the judges score this).
9. Commit small and often; `git pull` before you start and before you push.
10. Don't claim something works until you have run it. Say what you tested.

## Agreed migration

Person 1 confirmed the team changed to FastAPI. The migration may update all affected routing,
frontend wiring, configuration, tests and documentation. New work follows the ownership table.
Use APIRouter (`router`), FastAPI Request/Depends and JSONResponse; no WSGI entry point.
The string levels and existing table/API contracts below remain in place.

## Stack

FastAPI + Uvicorn + SQLAlchemy Core (no ORM) · SQLite locally, hosted Postgres via `DATABASE_URL` on
Render (free tier) · Jinja templates + vanilla JS (no build step) · `openai` SDK pointed at OpenRouter ·
`stripe` (sandbox) · ntfy.sh via `requests` · pytest.

## File ownership

| Path | Owner |
|---|---|
| `app/main.py`, `library/cli.py`, `library/http.py`, `library/db.py`, `library/auth.py`, `library/clock.py` | Person 1 |
| `library/status.py`, `library/trust.py`, `library/core_routes.py`, `scripts/replay.py` | Person 1 |
| `templates/`, `static/`, `library/pages.py` | Person 2 |
| `library/ai.py`, `library/notify.py`, `library/payments.py`, `library/integration_routes.py` | Person 3 |
| `tests/` | Everyone: add your own test file, e.g. `tests/test_ai.py` |
| `CLAUDE.md`, `README.md` | Everyone, only after agreeing as a team |

## Contract

### Levels

`level` is always one of `"not_full"`, `"busy"`, `"full"` (in the API, DB and frontend).
Display labels and scores live in `library/db.py`: `LEVEL_LABEL`, `LEVEL_SCORE` (0, 0.8, 1.0).

### Tables (`library/db.py`)

- **users**: id, name, email (unique), trust_score (0.5), reports_total, reports_agreed, points,
  flagged, is_premium, premium_until, premium_source ('stripe'|'leaderboard'),
  stripe_customer_id, ntfy_topic, created_at
- **reports**: id, user_id, level, created_at, agreed (NULL until judged)
- **comments**: id, user_id, text (≤280), created_at, hidden
- **status_snapshots**: id, level, score, report_count, created_at
- **notifications_sent**: id, user_id, kind ('filling_up'|'space_opening'), created_at
- **payments**: id, user_id, stripe_session_id (unique), stripe_subscription_id, amount (cents), currency, status, created_at
- **ai_summaries**: id, summary_json, comment_count, created_at

### Shared Python functions (signatures are fixed)

| Function | Owner | Called by |
|---|---|---|
| `status.compute_status(conn) -> dict` (shape = GET /api/status) | P1 | core_routes |
| `status.save_snapshot(conn, status)` | P1 | core_routes |
| `trust.judge_pending_reports(conn)` | P1 | core_routes |
| `trust.leaderboard(conn, limit=10) -> list` | P1 | core_routes |
| `trust.reward_top_users(conn) -> list` | P1 | `python -m library.cli reward-top` |
| `notify.check_and_send(conn, previous_status, new_status) -> list[str]` | P3 | core_routes, after every report |
| `ai.get_summary(conn) -> dict` (shape = GET /api/summary) | P3 | integration_routes |
| `payments.grant_premium(conn, user_id, days, source)` | P3 | payments, trust.reward_top_users |

### Endpoints

All JSON. Errors: `{"error": "..."}`. Auth is a Starlette signed session cookie (`request.session`) set by `/api/login`;
endpoints marked 🔒 return 401 when logged out.

| Method + path | Owner | Request | Success response |
|---|---|---|---|
| `POST /api/login` | P1 | `{"name", "email"}` | `{"user": User}` |
| `POST /api/logout` | P1 | | `{"ok": true}` |
| `GET /api/me` 🔒 | P1 | | `{"user": User, "seconds_until_can_report": int}` |
| `GET /api/status` | P1 | | `Status` |
| `POST /api/reports` 🔒 | P1 | `{"level"}` | 201 `{"status": Status}` · 429 `{"error", "retry_after_seconds"}` |
| `GET /api/comments` | P1 | | `{"comments": [{"id", "text", "name", "created_at"}]}` (latest 30, not hidden) |
| `POST /api/comments` 🔒 | P1 | `{"text"}` (1–280 chars) | 201 `{"id", "text"}` |
| `GET /api/leaderboard` | P1 | | `{"leaderboard": [{"rank", "name", "points", "reports_total"}]}` |
| `GET /api/summary` | P3 | | `Summary` |
| `POST /api/checkout` 🔒 | P3 | | `{"url"}` (Stripe Checkout URL) |
| `GET /api/checkout/confirm?session_id=` 🔒 | P3 | | `{"user": User}` once paid |
| `POST /webhooks/stripe` | P3 | Stripe event | `{"received": true}` |
| `POST /api/me/ntfy` 🔒 | P3 | `{"topic"}` | `{"ok": true, "topic"}` |
| `POST /api/demo/reports` | P1 | `{"email", "level", "name"?}` | only when `DEMO_MODE=1`, else 404 |
| `POST /api/demo/comments` | P1 | `{"email", "text", "name"?}` | only when `DEMO_MODE=1`, else 404 |
| `GET /health` | P1 | | `{"status": "ok", "database": "connected"}` |
| Pages: `/`, `/leaderboard`, `/premium`, `/account` | P2 | | HTML |

```
User    = {"id", "name", "email", "trust_score", "points", "flagged", "is_premium",
           "premium_until", "premium_source", "ntfy_topic"}
Status  = {"level", "label", "score", "confidence": "low"|"medium"|"high",
           "report_count", "trend_per_min", "updated_at"}
Summary = {"status": "ok"|"not_enough"|"stale"|"error", "summary": str|null,
           "themes": [{"label", "sentiment": "positive"|"neutral"|"negative", "count"}],
           "comment_count", "generated_at"}
```

## Running

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then fill in keys
python -m library.cli init-db
uvicorn app.main:app --reload     # http://127.0.0.1:8000
pytest
```

Demo: set `DEMO_MODE=1` and `DEMO_SPEED=60` in `.env`, run `python -m library.cli reset-db --confirm-reset`, start
the app, then `python scripts/replay.py` in another terminal.
Stripe webhooks locally: `stripe listen --forward-to 127.0.0.1:8000/webhooks/stripe`.
