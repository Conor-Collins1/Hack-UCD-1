# Library Status (HackUCD 2026)

A web app where students tap one button to report whether the library is **Not full**, **~80% full** or **Full**. The backend combines those reports into a live status, catches people who keep sending false reports, summarises comments with AI, alerts premium subscribers before the library fills up, and rewards the most useful reporters.

**Theme:** Everyday Frustrations. Students waste time walking to a library that turns out to be full.

---

## Current implementation

FastAPI routes, signed demo login, database tables, occupancy calculation (time decay, trust weights,
hysteresis and trend), report cooldown, comments, pages and PostgreSQL configuration are implemented.
Trust judgement, leaderboard rewards, AI summaries, payments and notifications remain team TODOs.
The integration routes return placeholders or explicit unavailable errors until Person 3 implements them.
Name/email login does not verify email ownership: use synthetic data until verified authentication is added.
The prior anonymous prototype database is separate and is not migrated; the app now uses the team's schema.

## Planned features

| Feature | What it does |
|---|---|
| Status buttons | One tap to report Not full / 80% / Full |
| Live status | Weighted, time-decayed vote with a confidence label ("Based on 7 reports in the last 20 min") |
| AI summary | OpenRouter turns recent comments into a Google Maps style summary with theme chips ("Quiet upstairs", "Few sockets") |
| Bad-actor detection | Trust score per user; repeat false reporters get flagged and their reports stop counting |
| Notifications (premium) | "Filling up" alert just before it's full, and "Space opening" when it drops from Full to 80% |
| Leaderboard | Points for useful reports; top 3 each month get a free month of premium |
| Premium subscription | Stripe sandbox Checkout; payment unlocks notifications automatically |

---

## Tech stack

| Layer | Choice |
|---|---|
| Backend | FastAPI + Uvicorn + SQLAlchemy Core (Python) |
| Database | SQLite locally; hosted Postgres on Render via `DATABASE_URL` |
| Frontend | Jinja2 templates + vanilla JS + CSS (no build step), polling every 10s |
| AI | `openai` Python SDK pointed at OpenRouter (`https://openrouter.ai/api/v1`) |
| Payments | `stripe` Python library (sandbox) + Stripe CLI for local webhooks |
| Notifications | ntfy.sh via `requests` |
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
  integration_routes.py        # /api/summary, checkout, webhook, ntfy       (Person 3)
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

### Notifications (premium)
- **Filling up:** if the status is rising fast enough to reach 0.9 within 15 minutes, send an alert.
- **Space opening:** status moves from Full back to 80%.
- At most one alert of each type per hour. Delivered via ntfy.sh (one POST request). Checked after every new report, so no background job is needed.

### AI summary (OpenRouter)
- Send comments from the last 2 hours; ask for JSON: a one-line summary plus 3–5 theme tags, each with sentiment and count.
- Cache; only regenerate after 5 new comments or 10 minutes.
- Fewer than 3 comments: show "Not enough recent comments" and skip the API call.
- If the JSON doesn't parse, keep the last good summary.
- The same call filters out abusive or spam comments.

### Leaderboard
- +1 point when a report matches the consensus.
- +3 for being first to report a change that others later confirm.
- 0 points for flagged users.
- Monthly reset (`python -m library.cli reward-top`): top 3 get `premium_until = now + 30 days` (no Stripe charge needed).

### Stripe (bonus +5 points)
- Sandbox Checkout Session for a subscription, e.g. €1.99/month.
- Webhook on `checkout.session.completed` sets `is_premium`; `/api/checkout/confirm` is a backup that asks Stripe directly.
- Account page shows the subscription as active.
- Test card: `4242 4242 4242 4242`, any future expiry, any CVC.

---

## The 5-hour plan

Details and checklists: [`plan/person-1-core-backend.md`](plan/person-1-core-backend.md),
[`plan/person-2-frontend-users.md`](plan/person-2-frontend-users.md),
[`plan/person-3-integrations.md`](plan/person-3-integrations.md).

| Time | Person 1: core backend | Person 2: frontend, users, pitch | Person 3: AI, Stripe, alerts |
|---|---|---|---|
| 0:00–0:20 | **All:** clone, run tests, read `CLAUDE.md`, agree any contract changes, get API keys | | |
| 0:20–1:30 | Status calculation (weighting, hysteresis, confidence, trend) | Status page, report buttons, summary chips, comments; send out survey | OpenRouter summary: prompt, JSON validation, caching, fallbacks |
| 1:30–2:45 | Trust scores, flags, leaderboard, top-3 reward; realistic `replay.py` | Leaderboard, premium and account pages; collect survey evidence | Stripe Checkout + webhook + confirm fallback; ntfy alerts |
| 2:45–3:30 | **All:** reset DB, run the replay, fix what breaks. **Feature freeze at 3:30.** | | |
| 3:30–4:15 | Tests: no reports, boundaries, spammer, sudden jump | Mobile layout, loading/empty/error states; survey slide | AI limit tests (empty, junk, prompt injection); full payment run |
| 4:15–5:00 | **All:** slides, demo script, two run-throughs, backup screen recording | | |

**If behind, cut in this order:** the "filling up" prediction (keep Full→80% alert), then the +3 first-reporter bonus, then the Stripe webhook (keep the confirm fallback).
**Never cut:** the OpenRouter feature, the full Stripe purchase flow, the replay script.

### Demo story (~3 min)
1. A student checks the status.
2. `replay.py` runs a busy day; the status climbs.
3. A premium user's phone buzzes "Filling up".
4. A spammer gets flagged and the status doesn't move.
5. The AI summary updates as comments arrive.
6. Leaderboard.
7. Buy premium live with the Stripe test card.

---

## Judging checklist

- [ ] **Users first:** survey results, quotes, current workaround (walking over / asking friends), how we reach students (society channels, library posters)
- [ ] **Craft:** clear UI, correct status, useful error messages, clean API (`/docs`)
- [ ] **Urgency and focus:** feature freeze held, cut list followed
- [ ] **Stay curious:** tested ordinary / boundary / failure inputs; tested an assumption from the survey and changed something
- [ ] **AI usage:** OpenRouter summary demonstrated, plus its limitations (few comments, junk input, prompt injection)
- [ ] **Stripe bonus:** sandbox payment completes, webhook unlocks premium, shown to judges

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


## Git basics for the team

```bash
git clone https://github.com/Conor-Collins1/Hack-UCD-1.git   # first time only
git pull                           # get everyone's latest changes before you start
git checkout -b my-feature         # optional: work on your own branch
git add <files>                    # stage your changes
git commit -m "Add status endpoint"
git push                           # upload (first push of a branch: git push -u origin my-feature)
```

Pull often, commit small, and don't commit `.env`.
