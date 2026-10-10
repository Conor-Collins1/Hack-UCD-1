"""Core API: login, reports, status, comments, leaderboard. OWNER: Person 1.
Request/response shapes are fixed by CLAUDE.md."""
import os
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from library.http import json_body, response
from sqlalchemy import func, insert, select

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
        return response(user=user_json(user, conn))


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
        return response(user=user_json(user, conn), seconds_until_can_report=trust.seconds_until_can_report(conn, user['id']))


@router.get('/status')
def get_status(request: Request):
    with engine.connect() as conn:
        return response(status.compute_status(conn))


def _submit_report(conn, user_id, level):
    """Shared by the real endpoint and the demo endpoint."""
    conn.execute(insert(reports).values(user_id=user_id, level=level, created_at=clock.now()))
    points_awarded = trust.award_points(conn, user_id, trust.REPORT_POINTS)
    trust.judge_pending_reports(conn)
    new = status.compute_status(conn)
    status.save_snapshot(conn, new)
    return new, points_awarded


@router.post('/reports')
def create_report(request: Request, data: dict = Depends(json_body), user_id: int = Depends(require_user)):
    level = data.get('level')
    if level not in LEVELS:
        return JSONResponse(jsonable_encoder(response(error=f'level must be one of {", ".join(LEVELS)}.')), status_code=400)
    with engine.begin() as conn:
        trust.lock_user(conn, user_id)
        user = current_user(conn, request)
        wait = trust.seconds_until_can_report(conn, user['id'])
        if wait > 0:
            return JSONResponse(jsonable_encoder(response(error='You reported recently. Try again soon.', retry_after_seconds=wait)), status_code=429)
        new, points_awarded = _submit_report(conn, user['id'], level)
    return JSONResponse(jsonable_encoder(response(status=new, points_awarded=points_awarded)), status_code=201)


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
    raw_text = data.get('text')
    text = raw_text.strip() if isinstance(raw_text, str) else ''
    if not 1 <= len(text) <= 280:
        return JSONResponse(jsonable_encoder(response(error='Comments must be 1-280 characters.')), status_code=400)
    with engine.begin() as conn:
        trust.lock_user(conn, user_id)
        wait = trust.seconds_until_can_comment(conn, user_id)
        if wait:
            return JSONResponse({'error': 'Please wait a minute before commenting again.', 'retry_after_seconds': wait}, status_code=429)
        recent = conn.execute(select(comments.c.text).where(
            comments.c.user_id == user_id, comments.c.created_at >= clock.now()-timedelta(hours=2))).scalars()
        normalised = ' '.join(text.casefold().split())
        if any(' '.join(previous.casefold().split()) == normalised for previous in recent):
            return JSONResponse({'error': 'You already posted this update. Please share something new.'}, status_code=409)
        result = conn.execute(insert(comments).values(user_id=user_id, text=text, created_at=clock.now()))
        points_awarded = trust.award_points(conn, user_id, trust.COMMENT_POINTS)
        return JSONResponse(jsonable_encoder(response(id=result.inserted_primary_key[0], text=text, points_awarded=points_awarded)), status_code=201)


@router.get('/leaderboard')
def get_leaderboard(request: Request):
    with engine.begin() as conn:
        trust.judge_pending_reports(conn)
        user = current_user(conn, request)
        own = None
        if user:
            own = {'id': user['id'], 'name': user['name'], 'points': user['points'],
                   'rank': trust.rank_for_user(conn, user['id']), 'flagged': user['flagged']}
        total = conn.execute(select(func.count()).select_from(users).where(users.c.flagged.is_(False), users.c.points > 0)).scalar_one()
        return response(leaderboard=trust.leaderboard(conn), current_user=own, total_contributors=total)


# ---- Demo-only endpoints, used by scripts/replay.py. Disabled unless DEMO_MODE=1. ----

@router.post('/demo/reports')
def demo_report(request: Request, data: dict = Depends(json_body)):
    if os.environ.get('DEMO_MODE') != '1':
        return JSONResponse(jsonable_encoder(response(error='Not found.')), status_code=404)
    if data.get('level') not in LEVELS or not data.get('email'):
        return JSONResponse(jsonable_encoder(response(error='Need email and level.')), status_code=400)
    with engine.begin() as conn:
        user_id = _demo_user(conn, data['email'], data.get('name') or data['email'].split('@')[0])
        trust.lock_user(conn, user_id)
        new, points_awarded = _submit_report(conn, user_id, data['level'])
    return JSONResponse(jsonable_encoder(response(status=new, points_awarded=points_awarded)), status_code=201)


@router.post('/demo/comments')
def demo_comment(request: Request, data: dict = Depends(json_body)):
    if os.environ.get('DEMO_MODE') != '1':
        return JSONResponse(jsonable_encoder(response(error='Not found.')), status_code=404)
    text = str(data.get('text', '')).strip()[:280]
    if not text or not data.get('email'):
        return JSONResponse(jsonable_encoder(response(error='Need email and text.')), status_code=400)
    with engine.begin() as conn:
        user_id = _demo_user(conn, data['email'], data.get('name') or data['email'].split('@')[0])
        trust.lock_user(conn, user_id)
        conn.execute(insert(comments).values(user_id=user_id, text=text, created_at=clock.now()))
        trust.award_points(conn, user_id, trust.COMMENT_POINTS)
    return JSONResponse(jsonable_encoder(response(ok=True)), status_code=201)
def _demo_user(conn, email, name):
    user_id = conn.execute(select(users.c.id).where(users.c.email == email)).scalar()
    if user_id is None:
        user_id = conn.execute(insert(users).values(name=name, email=email)).inserted_primary_key[0]
    return user_id
