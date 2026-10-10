# First working version

This branch implements the core demo: a responsive page, anonymous signed browser sessions, SQLite storage, occupancy reports with time decay, comments, input validation, and per-session cooldowns.

## Run locally on Windows

1. Create the environment: `python -m venv .venv`
2. Install: `.venv\Scripts\python -m pip install -r requirements.txt`
3. Start: `.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
4. Open http://127.0.0.1:8000 or http://127.0.0.1:8000/docs.
5. Test: `.venv\Scripts\python -m pytest -q`

The local session secret is temporary, so restarting resets browser identities unless SESSION_SECRET is configured. The app reads environment variables directly; .env.example documents them but .env is not automatically loaded.

## Online deployment requirements

Use one Python app instance, HTTPS, and a persistent disk. Set APP_ENV=production, a random SESSION_SECRET, PUBLIC_URL to the exact website origin, and DATABASE_PATH to a file on that disk. Install requirements and start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Do not deploy SQLite onto an ephemeral filesystem. Multi-instance hosting will require moving to a shared database.

## Scope and next steps

This is a hackathon foundation, not the complete README plan. AI summaries, verified login, trust scoring, hysteresis, leaderboard, Stripe subscriptions, notifications, and replay are not implemented yet. Anonymous cooldowns can be bypassed by clearing cookies; add verified identity and server-side abuse controls before public use. Comments are publicly visible and not moderated yet; use synthetic demo data until moderation is added. No external keys are needed for this version.
