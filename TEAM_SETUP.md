# Team setup: shared app, private credentials

## What is shared in GitHub

The Python app, frontend, SQLAlchemy table definitions (library/db.py), .env.example, tests,
and deployment instructions. Everyone can work from the same main branch and use the same live app.
The hosted PostgreSQL database is a separate service; do not commit its data or connection credentials.

## Run a local copy

Clone the repository, create a Python environment, install requirements.txt, and run
`python -m uvicorn app.main:app --reload`. The app uses a separate local SQLite database by default.
Copy .env.example to .env for local credentials. .env is ignored by Git.
For the shared demo, teammates can simply open the public Render URL; they need no database keys.

## Required settings on Render

| Setting | Where to obtain it | Sharing |
| --- | --- | --- |
| PUBLIC_URL | HTTPS .onrender.com address on the Render service | Public; okay to share |
| APP_ENV | production | Public |
| DATABASE_URL | Neon Connect dialog; complete PostgreSQL URL with SSL settings | Secret; enter directly in Render Environment |
| SESSION_SECRET | Generate a random value with at least 32 characters | Secret; keep stable in Render Environment |
| DEMO_MODE | 0 for online deployment | Public |
| DEMO_SPEED | 1 for online deployment | Public |

DATABASE_URL and SESSION_SECRET should already be configured if your live app is working.
Do not post their values in chat, issues, commits, or pull requests. Give teammates access through
Render/Neon project membership if needed. Use separate development credentials for local work.
GitHub Actions secrets are only needed if a future workflow explicitly uses them; this app deploys
through Render's GitHub integration and reads secrets from Render, not from GitHub Actions.

## Optional integration credentials

| Setting | Purpose | Where to enter it |
| --- | --- | --- |
| OPENROUTER_API_KEY | AI comment summaries | Render Environment / ignored local .env |
| OPENROUTER_MODEL | Model identifier; defaults to openrouter/free if unset | Same settings |
| STRIPE_SECRET_KEY | Stripe sandbox server key starting sk_test_ | Render Environment / ignored local .env |
| STRIPE_PRICE_ID | Recurring sandbox price identifier starting price_ | Same settings; not a secret credential |
| STRIPE_WEBHOOK_SECRET | Signature secret for this deployment's webhook endpoint | Render Environment / ignored local .env |

No Stripe publishable key is required for the planned server-created hosted Checkout flow.
Keeping the payments page does not mean checkout is implemented: Person 3 still needs to build it.
No notification service credentials are needed. Demo login requires no authentication provider keys.

## Safe handoff

Share the public app URL, which provider hosts the database, the OpenRouter model name, and whether
the optional credentials have been added. Keep actual secret values in the provider dashboards.
