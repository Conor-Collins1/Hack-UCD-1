"""Core API: login, reports, status, comments, leaderboard. OWNER: Person 1.
Request/response shapes are fixed by CLAUDE.md."""
import os

from flask import Blueprint, jsonify, request, session
from sqlalchemy import insert, select

from library import notify, status, trust
from library.auth import current_user, login_required, user_json
from library.db import LEVELS, comments, engine, reports, users

bp = Blueprint('core', __name__, url_prefix='/api')


def _json_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@bp.post('/login')
def login():
    data = _json_body()
    name = str(data.get('name', '')).strip()
    email = str(data.get('email', '')).strip().lower()
    if not 1 <= len(name) <= 60 or '@' not in email or len(email) > 200:
        return jsonify(error='Enter your name and a valid email.'), 400
    with engine.begin() as conn:
        user = conn.execute(select(users).where(users.c.email == email)).mappings().first()
        if user is None:
            conn.execute(insert(users).values(name=name, email=email))
            user = conn.execute(select(users).where(users.c.email == email)).mappings().first()
        session['user_id'] = user['id']
        return jsonify(user=user_json(user))


@bp.post('/logout')
def logout():
    session.clear()
    return jsonify(ok=True)


@bp.get('/me')
@login_required
def me():
    with engine.connect() as conn:
        user = current_user(conn)
        if user is None:
            session.clear()
            return jsonify(error='Log in first.'), 401
        return jsonify(user=user_json(user), seconds_until_can_report=trust.seconds_until_can_report(conn, user['id']))


@bp.get('/status')
def get_status():
    with engine.connect() as conn:
        return jsonify(status.compute_status(conn))


def _submit_report(conn, user_id, level):
    """Shared by the real endpoint and the demo endpoint."""
    previous = status.compute_status(conn)
    conn.execute(insert(reports).values(user_id=user_id, level=level))
    trust.judge_pending_reports(conn)
    new = status.compute_status(conn)
    status.save_snapshot(conn, new)
    notify.check_and_send(conn, previous, new)
    return new


@bp.post('/reports')
@login_required
def create_report():
    level = _json_body().get('level')
    if level not in LEVELS:
        return jsonify(error=f'level must be one of {", ".join(LEVELS)}.'), 400
    with engine.begin() as conn:
        user = current_user(conn)
        wait = trust.seconds_until_can_report(conn, user['id'])
        if wait > 0:
            return jsonify(error='You reported recently. Try again soon.', retry_after_seconds=wait), 429
        new = _submit_report(conn, user['id'], level)
    return jsonify(status=new), 201


@bp.get('/comments')
def list_comments():
    with engine.connect() as conn:
        rows = conn.execute(
            select(comments.c.id, comments.c.text, comments.c.created_at, users.c.name)
            .join(users, users.c.id == comments.c.user_id)
            .where(comments.c.hidden.is_(False))
            .order_by(comments.c.id.desc()).limit(30)
        ).mappings()
        return jsonify(comments=[
            {'id': r['id'], 'text': r['text'], 'name': r['name'], 'created_at': r['created_at'].isoformat()}
            for r in rows
        ])


@bp.post('/comments')
@login_required
def create_comment():
    text = str(_json_body().get('text', '')).strip()
    if not 1 <= len(text) <= 280:
        return jsonify(error='Comments must be 1-280 characters.'), 400
    with engine.begin() as conn:
        result = conn.execute(insert(comments).values(user_id=session['user_id'], text=text))
        return jsonify(id=result.inserted_primary_key[0], text=text), 201


@bp.get('/leaderboard')
def get_leaderboard():
    with engine.begin() as conn:
        trust.judge_pending_reports(conn)
        return jsonify(leaderboard=trust.leaderboard(conn))


# ---- Demo-only endpoints, used by scripts/replay.py. Disabled unless DEMO_MODE=1. ----

@bp.post('/demo/reports')
def demo_report():
    if os.environ.get('DEMO_MODE') != '1':
        return jsonify(error='Not found.'), 404
    data = _json_body()
    if data.get('level') not in LEVELS or not data.get('email'):
        return jsonify(error='Need email and level.'), 400
    with engine.begin() as conn:
        user_id = _demo_user(conn, data['email'], data.get('name') or data['email'].split('@')[0])
        new = _submit_report(conn, user_id, data['level'])
    return jsonify(status=new), 201


@bp.post('/demo/comments')
def demo_comment():
    if os.environ.get('DEMO_MODE') != '1':
        return jsonify(error='Not found.'), 404
    data = _json_body()
    text = str(data.get('text', '')).strip()[:280]
    if not text or not data.get('email'):
        return jsonify(error='Need email and text.'), 400
    with engine.begin() as conn:
        user_id = _demo_user(conn, data['email'], data.get('name') or data['email'].split('@')[0])
        conn.execute(insert(comments).values(user_id=user_id, text=text))
    return jsonify(ok=True), 201


def _demo_user(conn, email, name):
    user_id = conn.execute(select(users.c.id).where(users.c.email == email)).scalar()
    if user_id is None:
        user_id = conn.execute(insert(users).values(name=name, email=email)).inserted_primary_key[0]
    return user_id
