import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine, func, select
from sqlalchemy.exc import SQLAlchemyError

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024

database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith(('postgres://', 'postgresql://')):
        database_url = 'postgresql+psycopg://' + database_url.split('://', 1)[1]
else:
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    database_url = f'sqlite:///{app.instance_path}/demo.db'

engine = create_engine(database_url, pool_pre_ping=True)
metadata = MetaData()
notes = Table(
    'demo_notes', metadata,
    Column('id', Integer, primary_key=True),
    Column('text', String(200), nullable=False),
    Column('created_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
)


@app.cli.command('init-db')
def init_db():
    """Create the demo table without removing existing data."""
    metadata.create_all(engine)
    print('Demo database initialized.')


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/click")
def click():
    return jsonify(message="Hello from Flask! Your button works. 🎉")


@app.get("/health")
def health():
    try:
        with engine.connect() as connection:
            connection.execute(select(notes.c.id).limit(1))
    except SQLAlchemyError:
        app.logger.error('Database readiness check failed; verify connectivity and run init-db.')
        return jsonify(status='unavailable', database='unavailable'), 503
    return jsonify(status="ok", database="connected")


@app.get('/api/notes')
def list_notes():
    with engine.connect() as connection:
        rows = connection.execute(select(notes).order_by(notes.c.id.desc()).limit(50)).mappings()
        return jsonify(notes=[{'id': row['id'], 'text': row['text']} for row in rows])


@app.post('/api/notes')
def add_note():
    data = request.get_json(silent=True)
    text = data.get('text') if isinstance(data, dict) else None
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 200:
        return jsonify(error='Enter a note between 1 and 200 characters.'), 400
    with engine.begin() as connection:
        result = connection.execute(notes.insert().values(text=text.strip()))
        note_id = result.inserted_primary_key[0]
    return jsonify(id=note_id, text=text.strip()), 201


@app.errorhandler(SQLAlchemyError)
def database_error(error):
    app.logger.error('Database request failed; check database configuration.')
    return jsonify(error='Database unavailable. Please try again later.'), 503
