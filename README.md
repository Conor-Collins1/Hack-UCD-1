# Library Status (HackUCD 2026)

A web app where students tap one button to report whether the library is **Not full**, **~80% full** or **Full**. The backend combines those reports into a live status, catches people who keep sending false reports, summarises comments with AI, retains a sandbox payments page, and rewards the most useful reporters.

**Theme:** Everyday Frustrations. Students waste time walking to a library that turns out to be full.

---

## Current implementation

FastAPI routes, signed demo login, database tables, occupancy calculation (time decay, trust weights,
hysteresis and trend), report cooldown, comments, pages and PostgreSQL configuration are implemented.
Trust judgement, automatic leaderboard rewards and payments remain team TODOs. Participation points, live ranks and OpenRouter AI summaries are implemented. Notifications are deferred as a future idea.
The integration routes return placeholders or explicit unavailable errors until Person 3 implements them.
Name/email login does not verify email ownership: use synthetic data until verified authentication is added.
The prior anonymous prototype database is separate and is not migrated; the app now uses the team's schema.

## Planned features

| Feature | What it does |
|---|---|
| Status buttons | One tap to report Not full / 80% / Full |
| Live status | Weighted, time-decayed vote with a confidence label ("Based on 7 reports in the last 20 min") |
| AI summary | OpenRouter turns recent comments into a brief bullet points from comments in the past hour |
| Bad-actor detection | Trust score per user; repeat false reporters get flagged and their reports stop counting |
| Leaderboard | Points for useful reports; top 3 each month get a free month of premium |
| One-time Premium purchase | Stripe sandbox Checkout; payment records demo premium status |

---

## Tech stack

| Layer | Choice |
|---|---|
| Backend | FastAPI + Uvicorn + SQLAlchemy Core (Python) |
| Database | SQLite locally; hosted Postgres on Render via `DATABASE_URL` |
| Frontend | Jinja2 templates + vanilla JS + CSS (no build step), polling every 10s |
| AI | `openai` Python SDK pointed at OpenRouter (`https://openrouter.ai/api/v1`) |
| Payments | `stripe` Python library (sandbox) + Stripe CLI for local webhooks |
| Login | Name + email, Starlette signed session cookie (no passwords) |
| Hosting | Render (Uvicorn) |
| Tests | `pytest` + FastAPI TestClient |

**Team docs:** [`CLAUDE.md`](CLAUDE.md) is the shared contract (tables, endpoints, file ownership,
rules for AI assistants). Each person's tasks are in [`plan/`](plan/).

### Project layout

```
app/main.py                    # FastAPI app, startup, /health            (Person 1)
library/
  db.py  auth.py  clock.py     # tables, login, app clock                    (Person 1)
  status.py  trust.py          # status calculation, bad actors, leaderboard (Person 1)
  core_routes.py               # /api/login, reports, status, comments...    (Person 1)
  pages.py                     # HTML pages                                  (Person 2)
  ai.py  payments.py  notify.py
  integration_routes.py        # /api/summary, checkout, webhook       (Person 3)
templates/  static/            # frontend                                    (Person 2)
scripts/replay.py              # replays a busy afternoon for the demo      (Person 1)
tests/
plan/                          # one task file per person
```

---

## Getting started

```bash
git clone https://github.com/Conor-Collins1/Hack-UCD-1.git
cd Hack-UCD-1
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then fill in the keys
python -m library.cli init-db
uvicorn app.main:app --reload        # http://127.0.0.1:8000
pytest
```

Stripe webhooks locally (second terminal):

```bash
stripe listen --forward-to 127.0.0.1:8000/webhooks/stripe
```

Demo run: set `DEMO_MODE=1` and `DEMO_SPEED=60` in `.env` (time runs 60x faster), then

```bash
python -m library.cli reset-db --confirm-reset
uvicorn app.main:app
python scripts/replay.py            # third terminal
```

---

## How the logic works

### Database tables
`users`, `reports` (string levels: not_full / busy / full), `comments`, `status_snapshots`, `payments`, `ai_summaries`, `notifications_sent`. Full schema: CLAUDE.md.

### Status calculation
- Each report becomes a number: Not full = 0, 80% = 0.8, Full = 1.
- Average reports from the last 45 minutes. Each report's weight halves every 15 minutes and is multiplied by the reporter's trust score.
- Hysteresis to stop flicker: switch to Full above 0.9, back down below 0.8.
- Confidence label from how many reports came in recently.

### Bad-actor detection
- Compare each report with the consensus at that time, leaving out the reporter's own report.
- Trust score = (agreed + 1) / (total + 2). New users start at 0.5.
- Flag users below 0.3 trust after 5+ reports, or who send repeated reports within 10 minutes.
- Flagged users see the app normally, but their reports carry zero weight.

### Future idea: notifications
Notifications may eventually warn students when the library fills or space opens. They are outside the current demo and require no setup or keys.

### AI summary (OpenRouter)
- Reads up to 50 latest visible comments from the past hour. Names and emails are not sent;
  comment text is sent to OpenRouter, so students should avoid personal details in comments.
- Fewer than three comments: returns `not_enough` and makes no API call.
- Uses OPENROUTER_API_KEY in Render; OPENROUTER_MODEL selects the model. If blank or unset,
  defaults to `openrouter/free` (https://openrouter.ai/openrouter/free), subject to provider limits.
- Validates 1-5 concise bullet points (180 characters each). Theme metadata is retained internally; the UI shows only the bullet points.
  Treats comment instructions as untrusted data; identified spam/abuse can be hidden, while normal
  criticism remains visible. Model moderation and summaries can still make mistakes.
- Saves summaries in PostgreSQL/SQLite. Reuses them until five new comments arrive, ten minutes
  pass, the model changes, or source comments expire/disappear from the bounded input window.
- A 15-second request timeout and one-minute retry cooldown limit failed calls. Invalid JSON,
  incomplete output, missing credentials, provider errors and timeouts keep the last valid,
  still-relevant summary with `stale`, or return `error` when none exists.
- Concurrent requests share one generation per app process; use one Uvicorn worker for this demo.
  No background job or browser-side API key is required. The page already polls every 30 seconds.

### Leaderboard
- +5 points for each accepted occupancy report; one report every 10 minutes.
- +2 points for each accepted comment; one comment per minute. Duplicate text from the same user
  within two hours is rejected, ignoring case and extra whitespace.
- Invalid, rejected and flagged-user submissions earn no points. Points are saved in the same
  transaction as the submission, so a failed save awards nothing.
- The leaderboard shows the top 10 positive-scoring, unflagged contributors. Ties share ranks
  (1, 1, 3). Your own rank is shown even when outside the top 10.
- Your score and position appear on the status, account and leaderboard pages. The leaderboard
  refreshes every 10 seconds while visible.
- Participation scoring starts with new submissions; historical content is not backfilled.
  Monthly reset and top-three premium rewards are future ideas, not active behavior.

### Stripe (bonus +5 points)
- Sandbox Checkout Session for a one-time EUR 1.99 purchase (mode=payment).
- Webhook on `checkout.session.completed` sets `is_premium`; `/api/checkout/confirm` is a backup that asks Stripe directly.
- Account page shows permanent Premium (premium_until is null).
- Test card: `4242 4242 4242 4242`, any future expiry, any CVC.

---

## Error handling

Every error is returned as JSON, `{"error": "<plain-English message>"}`, with a matching HTTP status,
and the frontend shows that message next to the action that failed.

| Situation | Response |
|---|---|
| Broken JSON or wrong body shape | `400` "Please check your input and try again." |
| Invalid report level | `400` "level must be one of not_full, busy, full." |
| Comment empty or over 280 characters | `400` "Comments must be 1-280 characters." |
| Not logged in | `401` "Log in first." The page prompts the student to sign in again |
| Form posted from another website | `403` "Please submit from the app website." |
| Same comment posted twice within 2 hours | `409` "You already posted this update." |
| Request body over 64 KB | `413` "Request is too large." |
| Reporting again within 10 minutes / commenting within 1 minute | `429` with `retry_after_seconds`; the page shows a countdown |
| Database unavailable | `503` "Database unavailable. Please try again later." (details logged, not shown) |
| Unknown page / wrong HTTP method | `404` / `405` as JSON |

**AI summary.** Fewer than 3 comments returns `not_enough` without calling the AI. Requests time
out after 15 seconds and fall back to up to three models. Every field of the AI's reply is
validated; if the call fails or the reply is invalid, the last good summary is shown marked
"may be out of date" (`stale`), or `error` if there is none, and the app waits a minute before
trying again. Comments are passed as untrusted data so instructions inside them are ignored.

**Payments.** Only Stripe sandbox keys are accepted. Before granting Premium the app checks the
session belongs to the logged-in user, is paid, and matches the EUR 1.99 price. Webhooks must
have a valid signature, and confirming the same payment twice does not create a duplicate.
If Stripe is unreachable the student sees "Stripe is unavailable. Please try again shortly." (`502`).

**Startup checks.** In production the app refuses to start without a strong `SESSION_SECRET`
and an HTTPS `PUBLIC_URL`, or with demo mode switched on.

**Tests.** `pytest` covers ordinary, boundary (e.g. 280 vs 281 characters) and failure inputs
for the API, scoring, AI summary and payments.

---

## Data

All reports, users and comments in the demo are **synthetic**, generated by `scripts/replay.py`. No real student data is stored.

---

## Free hosting: Render + Neon

Render hosts the FastAPI app; Neon hosts PostgreSQL. Use their Free plans. Render free app instances
sleep after 15 idle minutes; the first request can take about a minute. SQLite files on Render are
lost on restart or redeploy, so set DATABASE_URL to a separate hosted PostgreSQL database.
Render's own free PostgreSQL expires after 30 days; Neon is the recommended development database.

1. Create a Neon Free project and copy its PostgreSQL connection string into Render's secret settings.
2. Create a Render Web Service from this GitHub repository, branch main, runtime Python.
3. Build command: `pip install -r requirements.txt`.
4. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
5. Set APP_ENV=production, SESSION_SECRET to a random value (at least 32 characters),
   PUBLIC_URL to the exact HTTPS app origin, DATABASE_URL to the Neon URL,
   DEMO_MODE=0 and DEMO_SPEED=1. Do not put secrets into GitHub or chat.
6. Set the health check path to /health. Tables are created on startup.

Free allowances can change. See https://render.com/docs/free and https://neon.com/pricing.
AI calls are a separate service and are not included in free app hosting.
