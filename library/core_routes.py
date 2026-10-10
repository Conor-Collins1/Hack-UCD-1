"""Core API: login, reports, status, comments, leaderboard. OWNER: Person 1.
Request/response shapes are fixed by CLAUDE.md."""
import os

from fastapi import APIRouter, Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from library.http import json_body, response
from sqlalchemy import insert, select

from library import clock, status, trust
from library.auth import current_user, require_user, user_json
from library.db import LEVELS, comments, engine, reports, users

router = APIRouter(prefix='/api')
@router.post('/login')
def login(request: Request, data: dict = Depends(json_body)):
    name = str(data.get('name', '')).strip()
    email = str(data.get('email', '')).strip().lower()
    if not 1 <= len(name) <= 60 or '@' not in email or len(email) > 200:
        return JSONResponse(jsonable_encoder(response(error='Enter your name and a valid email.')), status_code=400)
    with engine.begin() as conn:
        user = conn.execute(select(users).where(users.c.email == email)).mappings().first()
        if user is None:
            conn.execute(insert(users).values(name=name, email=email))
            user = conn.execute(select(users).where(users.c.email == email)).mappings().first()
        request.session['user_id'] = user['id']
        return response(user=user_json(user))


@router.post('/logout')
def logout(request: Request):
    request.session.clear()
    return response(ok=True)


@router.get('/me')
def me(request: Request, user_id: int = Depends(require_user)):
    with engine.connect() as conn:
        user = current_user(conn, request)
        if user is None:
            request.session.clear()
            return JSONResponse(jsonable_encoder(response(error='Log in first.')), status_code=401)
        return response(user=user_json(user), seconds_until_can_report=trust.seconds_until_can_report(conn, user['id']))


@router.get('/status')
def get_status(request: Request):
    with engine.connect() as conn:
        return response(status.compute_status(conn))


def _submit_report(conn, user_id, level):
    """Shared by the real endpoint and the demo endpoint."""
    conn.execute(insert(reports).values(user_id=user_id, level=level))
    trust.judge_pending_reports(conn)
    new = status.compute_status(conn)
    status.save_snapshot(conn, new)
    return new


@router.post('/reports')
def create_report(request: Request, data: dict = Depends(json_body), user_id: int = Depends(require_user)):
    level = data.get('level')
    if level not in LEVELS:
        return JSONResponse(jsonable_encoder(response(error=f'level must be one of {", ".join(LEVELS)}.')), status_code=400)
    with engine.begin() as conn:
        user = current_user(conn, request)
        wait = trust.seconds_until_can_report(conn, user['id'])
        if wait > 0:
            return JSONResponse(jsonable_encoder(response(error='You reported recently. Try again soon.', retry_after_seconds=wait)), status_code=429)
        new = _submit_report(conn, user['id'], level)
    return JSONResponse(jsonable_encoder(response(status=new)), status_code=201)


@router.get('/comments')
def list_comments(request: Request):
    with engine.connect() as conn:
        rows = conn.execute(
            select(comments.c.id, comments.c.text, comments.c.created_at, users.c.name)
            .join(users, users.c.id == comments.c.user_id)
            .where(comments.c.hidden.is_(False))
            .order_by(comments.c.id.desc()).limit(30)
        ).mappings()
        return response(comments=[
            {'id': r['id'], 'text': r['text'], 'name': r['name'], 'created_at': clock.as_utc(r['created_at']).isoformat()}
            for r in rows
        ])


@router.post('/comments')
def create_comment(request: Request, data: dict = Depends(json_body), user_id: int = Depends(require_user)):
    text = str(data.get('text', '')).strip()
    if not 1 <= len(text) <= 280:
        return JSONResponse(jsonable_encoder(response(error='Comments must be 1-280 characters.')), status_code=400)
    with engine.begin() as conn:
        result = conn.execute(insert(comments).values(user_id=request.session['user_id'], text=text))
        return JSONResponse(jsonable_encoder(response(id=result.inserted_primary_key[0], text=text)), status_code=201)


@router.get('/leaderboard')
def get_leaderboard(request: Request):
    with engine.begin() as conn:
        trust.judge_pending_reports(conn)
        return response(leaderboard=trust.leaderboard(conn))


# ---- Demo-only endpoints, used by scripts/replay.py. Disabled unless DEMO_MODE=1. ----

@router.post('/demo/reports')
def demo_report(request: Request, data: dict = Depends(json_body)):
    if os.environ.get('DEMO_MODE') != '1':
        return JSONResponse(jsonable_encoder(response(error='Not found.')), status_code=404)
    if data.get('level') not in LEVELS or not data.get('email'):
        return JSONResponse(jsonable_encoder(response(error='Need email and level.')), status_code=400)
    with engine.begin() as conn:
        user_id = _demo_user(conn, data['email'], data.get('name') or data['email'].split('@')[0])
        new = _submit_report(conn, user_id, data['level'])
    return JSONResponse(jsonable_encoder(response(status=new)), status_code=201)


@router.post('/demo/comments')
def demo_comment(request: Request, data: dict = Depends(json_body)):
    if os.environ.get('DEMO_MODE') != '1':
        return JSONResponse(jsonable_encoder(response(error='Not found.')), status_code=404)
    text = str(data.get('text', '')).strip()[:280]
    if not text or not data.get('email'):
        return JSONResponse(jsonable_encoder(response(error='Need email and text.')), status_code=400)
    with engine.begin() as conn:
        user_id = _demo_user(conn, data['email'], data.get('name') or data['email'].split('@')[0])
        conn.execute(insert(comments).values(user_id=user_id, text=text))
    return JSONResponse(jsonable_encoder(response(ok=True)), status_code=201)
def _demo_user(conn, email, name):
    user_id = conn.execute(select(users.c.id).where(users.c.email == email)).scalar()
    if user_id is None:
        user_id = conn.execute(insert(users).values(name=name, email=email)).inserted_primary_key[0]
    return user_id
