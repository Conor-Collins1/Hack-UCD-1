# Library Status (HackUCD 2026)

A web app where students tap one button to report whether the library is **Not full**, **~80% full** or **Full**. The backend combines those reports into a live status, catches people who keep sending false reports, summarises comments with AI, alerts premium subscribers before the library fills up, and rewards the most useful reporters.

**Theme:** Everyday Frustrations. Students waste time walking to a library that turns out to be full.

---

## Features

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
| Backend | FastAPI + Uvicorn (Python) |
| Database | SQLite via SQLModel |
| Frontend | Jinja2 templates / static HTML + Tailwind (CDN) + vanilla JS, polling every 10s |
| AI | `openai` Python SDK pointed at OpenRouter (`https://openrouter.ai/api/v1`) |
| Payments | `stripe` Python library + Stripe CLI for local webhooks |
| Notifications | ntfy.sh via `httpx` |
| Background jobs | `asyncio` task started in FastAPI's `lifespan`, runs every 60s |
| Login | Name + email, signed session cookie (no passwords) |
| Tests | `pytest` + FastAPI `TestClient` |

### Project layout

```
app/
  main.py            # FastAPI app, background loop, routes
  db.py              # SQLModel engine + table models
  status.py          # weighted average, hysteresis, confidence
  trust.py           # consensus agreement, trust score, flags, leaderboard points
  ai.py              # OpenRouter summary + comment filtering, caching, fallback
  payments.py        # Checkout Session + webhook handler
  notify.py          # ntfy alerts with cooldown
  templates/
  static/
scripts/replay.py    # replays a busy day of fake reports for the demo
tests/
requirements.txt
.env                 # secrets, never committed
```

---

## Getting started

```bash
git clone <repo-url>
cd hackucd-library
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install fastapi uvicorn sqlmodel jinja2 openai stripe httpx python-dotenv pytest
```

Create a `.env` file in the project root:

```
OPENROUTER_API_KEY=sk-or-...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PRICE_ID=price_...
STRIPE_WEBHOOK_SECRET=whsec_...    # printed by `stripe listen`
NTFY_TOPIC=hackucd-library-<something-random>
SESSION_SECRET=<any long random string>
```

Run it:

```bash
uvicorn app.main:app --reload
# in a second terminal, forward Stripe sandbox webhooks:
stripe listen --forward-to localhost:8000/webhooks/stripe
# in a third terminal, run the demo replay:
python scripts/replay.py
```

Open http://localhost:8000 for the app and http://localhost:8000/docs for the API docs.

---

## How the logic works

### Database tables
`users` (trust_score, is_premium, premium_until, flagged), `reports` (user_id, level 0/1/2, created_at), `comments`, `status_snapshots`, `subscriptions`, `notifications_sent`.

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
- At most one alert of each type per hour. Delivered via ntfy.sh (one POST request); browser notifications as a fallback.

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
- Monthly reset: top 3 get `premium_until = now + 30 days` (no Stripe charge needed).

### Stripe (bonus +5 points)
- Sandbox Checkout Session for a subscription, e.g. €1.99/month.
- Webhook on `checkout.session.completed` sets `is_premium`.
- Account page shows the subscription as active.
- Test card: `4242 4242 4242 4242`, any future expiry, any CVC.

---

## The 5-hour plan

| Time | A (backend) | B (frontend) | C (AI + Stripe) | D (users + pitch) |
|---|---|---|---|---|
| 0:00–0:20 | **All:** agree tables + API endpoints, get OpenRouter + Stripe test keys, set up `.env` | | | |
| 0:20–1:30 | Status calculation with trust weighting; report / comment / status endpoints | Status buttons, status card with confidence, comment box | OpenRouter summary + filtering, caching, fallbacks | Survey 15+ students (in the room and at the library); write `replay.py` |
| 1:30–2:45 | Bad-actor scoring + flags; leaderboard query | Leaderboard page, flagged badge, premium page | Stripe Checkout, webhook, premium unlock; ntfy alerts | Collect survey results; draft pitch (users, problem, workaround, how we reach them) |
| 2:45–3:30 | **All:** connect everything end to end, run the replay. **Feature freeze at 3:30.** | | | |
| 3:30–4:15 | Tests: no reports, one report, spammer, sudden jump to full | Error messages, mobile layout, loading states | AI tests: empty input, junk comments, prompt-injection comment; record results | Turn the survey into charts / quotes |
| 4:15–5:00 | **All:** demo script, slides, two full run-throughs, backup screen recording | | | |

**If behind, cut in this order:** the "filling up" prediction (keep Full→80% alert), then the +3 first-reporter bonus, then browser notifications.
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

## Git basics for the team

```bash
git clone <repo-url>               # first time only
git pull                           # get everyone's latest changes before you start
git checkout -b my-feature         # optional: work on your own branch
git add <files>                    # stage your changes
git commit -m "Add status endpoint"
git push                           # upload (first push of a branch: git push -u origin my-feature)
```

Pull often, commit small, and don't commit `.env`.
