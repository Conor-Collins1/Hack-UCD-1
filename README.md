# Hack UCD #1

A Flask demo with a hello button and a form that saves and lists public notes.

## Local development

Python 3.12.14 is pinned in `.python-version` for Render and matches the tested environment. Without DATABASE_URL, the app uses an ignored SQLite database in instance/demo.db.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m flask --app app init-db
.venv/bin/python -m flask --app app run --debug
```

## Render and Supabase

Supabase hosts the PostgreSQL database; Render hosts the Flask website.

1. Create a Supabase project. From its Connect dialog, select the PostgreSQL **session pooler** connection string (port 5432), which supports IPv4. Insert your database password using URL encoding for special characters. Use the exact host and username Supabase supplies.
2. In Render's Environment settings, add `DATABASE_URL` with that connection string. Set `sslmode=require` in the query string (use `&` if it already has query parameters). Never commit or share this value in chat.
3. Connect Render to this GitHub repository and deploy the application changes.
4. Set build command: `pip install -r requirements.txt`.
5. Set start command: `python -m flask --app app init-db && gunicorn --bind 0.0.0.0:$PORT app:app`.
6. Set health check path: `/health`.

The initialization command is repeatable and creates only the demo_notes table if missing. It does not delete records. For a larger application, replace this with versioned database migrations.

Without DATABASE_URL, Render will use local SQLite, which is **not durable across redeployments**. Set the Supabase connection before relying on saved data. This is an unauthenticated public demo: anyone can read and add notes. Do not store sensitive data.

## Deployment checks

- Open `/`: the page should show the hello button and note form.
- Click Say hello: a Flask greeting should appear.
- Save a note and refresh: the note should still appear.
- Open `/health`: expect `{"status":"ok","database":"connected"}`. An unavailable database or missing table returns HTTP 503.
- Redeploy and confirm the note remains to verify external database persistence.

The APIs are `POST /api/click`, `GET /api/notes`, and `POST /api/notes` with JSON `{"text":"Hello"}`. Notes must contain 1–200 characters; the list shows the latest 50. User text is rendered as text rather than HTML.
