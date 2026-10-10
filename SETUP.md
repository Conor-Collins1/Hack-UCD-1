# Run the FastAPI app

## Windows

Create a Python 3.12 environment (`python -m venv .venv`), then:

```
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. Log in with a synthetic name/email on /account before reporting.
API docs: /docs. Tests: `.venv\Scripts\python -m pytest -q`.

Copy .env.example to .env for local settings; the app loads it automatically.
Set a stable random SESSION_SECRET so sessions survive restarts.
Tables are created automatically at startup. Local data lives in instance/library.db.

## Database commands

`python -m library.cli init-db` creates missing tables.
`python -m library.cli reset-db --confirm-reset` deletes all data; use only a disposable demo database.
`python -m library.cli reward-top` is reserved for Person 1's future reward implementation.

## Free online deployment

Use Render Free for the web app and Neon Free for PostgreSQL. Follow README.md for exact settings.
Do not deploy local SQLite to Render Free: local files disappear on restarts and redeploys.
Choose a Python runtime, build `pip install -r requirements.txt`, start
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health check /health.
Set APP_ENV=production, SESSION_SECRET (random, 32+ characters), PUBLIC_URL (HTTPS origin),
DATABASE_URL (hosted PostgreSQL URL), DEMO_MODE=0 and DEMO_SPEED=1.

## Migration for teammates

Pull main, reinstall requirements, and use Uvicorn. App entry point is app.main:app;
routes use APIRouter, templates use Starlette's Jinja2 integration, tests use TestClient.
The string level values, table schema, endpoint URLs and documented JSON formats are retained.
Person 2 owns templates/static; Person 3 owns AI/payments/notifications. Those services remain TODOs.
No real user data or secrets were migrated from the anonymous prototype.
