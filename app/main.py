import math
import os
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

ROOT = Path(__file__).resolve().parent
DATABASE = os.environ.get('DATABASE_PATH', str(ROOT.parent / 'library.db'))
SESSION_SECRET = os.environ.get('SESSION_SECRET')
if os.environ.get('APP_ENV') == 'production' and not SESSION_SECRET:
    raise RuntimeError('Set SESSION_SECRET before running in production')
SESSION_SECRET = SESSION_SECRET or secrets.token_urlsafe(48)

@contextmanager
def database():
    connection = sqlite3.connect(DATABASE, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()

@asynccontextmanager
async def lifespan(app):
    with database() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS reports (
          id INTEGER PRIMARY KEY, visitor TEXT NOT NULL,
          level INTEGER NOT NULL CHECK(level IN (0,1,2)), created REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS reports_created ON reports(created);
        CREATE INDEX IF NOT EXISTS reports_visitor ON reports(visitor, created);
        CREATE TABLE IF NOT EXISTS comments (
          id INTEGER PRIMARY KEY, visitor TEXT NOT NULL,
          body TEXT NOT NULL, created REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS comments_created ON comments(created);
        ''')
    yield

app = FastAPI(title='Library Status API', lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET,
                   same_site='lax', https_only=os.environ.get('APP_ENV') == 'production')

class Report(BaseModel):
    level: int = Field(strict=True, ge=0, le=2)

class Comment(BaseModel):
    body: str = Field(min_length=1, max_length=500)

def visitor(request):
    if 'visitor' not in request.session:
        request.session['visitor'] = secrets.token_urlsafe(24)
    return request.session['visitor']

def check_origin(request):
    origin = request.headers.get('origin')
    expected = os.environ.get('PUBLIC_URL', str(request.base_url).rstrip('/'))
    if origin and origin.rstrip('/') != expected.rstrip('/'):
        raise HTTPException(403, 'Please submit from the app website.')

def calculate_status(rows, now):
    if not rows:
        return dict(level=None, label='No recent reports', score=None, report_count=0,
                    confidence='Be the first to report', latest_report_at=None)
    weights = [math.pow(0.5, max(0, now-r['created'])/900) for r in rows]
    score = sum((0, .8, 1)[r['level']]*w for r,w in zip(rows,weights))/sum(weights)
    level = 2 if score >= .9 else 1 if score >= .5 else 0
    recent = sum(r['created'] >= now-1200 for r in rows)
    return dict(level=level, label=('Not full','Around 80% full','Full')[level],
                score=round(score,3), report_count=len(rows),
                confidence=f'Based on {recent} reports in the last 20 minutes',
                latest_report_at=max(r['created'] for r in rows))

@app.get('/', include_in_schema=False)
def home():
    return FileResponse(ROOT / 'index.html')

@app.get('/health')
def health():
    with database() as db:
        db.execute('SELECT 1')
    return {'status':'ok'}

@app.get('/api/status')
def status(request: Request):
    visitor(request)
    now = time.time()
    with database() as db:
        rows = db.execute('SELECT level, created FROM reports WHERE created >= ?', (now-2700,)).fetchall()
    return calculate_status(rows, now)

@app.post('/api/reports', status_code=201)
def report(payload: Report, request: Request):
    check_origin(request)
    identity = visitor(request)
    now = time.time()
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        latest = db.execute('SELECT MAX(created) FROM reports WHERE visitor=?',(identity,)).fetchone()[0]
        if latest is not None and now-latest < 600:
            raise HTTPException(429, 'Thanks! You can report again in 10 minutes.')
        db.execute('INSERT INTO reports(visitor,level,created) VALUES(?,?,?)',(identity,payload.level,now))
    return {'message':'Report saved. Thank you!'}

@app.get('/api/comments')
def comments():
    with database() as db:
        rows = db.execute('SELECT id,body,created FROM comments WHERE created>=? ORDER BY created DESC LIMIT 50', (time.time()-7200,)).fetchall()
    return {'comments':[dict(r) for r in rows]}

@app.post('/api/comments', status_code=201)
def comment(payload: Comment, request: Request):
    check_origin(request)
    body = payload.body.strip()
    if not body:
        raise HTTPException(422, 'Please write a comment first.')
    identity = visitor(request)
    now = time.time()
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        latest = db.execute('SELECT MAX(created) FROM comments WHERE visitor=?',(identity,)).fetchone()[0]
        if latest is not None and now-latest < 60:
            raise HTTPException(429, 'Please wait a minute before commenting again.')
        db.execute('INSERT INTO comments(visitor,body,created) VALUES(?,?,?)',(identity,body,now))
    return {'message':'Comment saved.'}
