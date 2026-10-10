"""AI summary, Stripe and notification-settings API. OWNER: Person 3.
Request/response shapes are fixed by CLAUDE.md."""
from fastapi import APIRouter, Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from library.http import json_body, response
import os

from sqlalchemy import update

from library import ai, payments
from library.auth import current_user, require_user
from library.db import engine, users

router = APIRouter()
@router.get('/api/summary')
def get_summary(request: Request):
    with engine.begin() as conn:
        return response(ai.get_summary(conn))


@router.post('/api/checkout')
def checkout(request: Request, user_id: int = Depends(require_user)):
    with engine.connect() as conn:
        user = current_user(conn, request)
    try:
        url = payments.create_checkout_session(user, os.environ.get('PUBLIC_URL', str(request.base_url)).rstrip('/') + '/')
    except (NotImplementedError, KeyError, RuntimeError):
        return JSONResponse(jsonable_encoder(response(error='Payments are not set up yet.')), status_code=503)
    return response(url=url)


@router.get('/api/checkout/confirm')
def confirm_checkout(request: Request, user_id: int = Depends(require_user)):
    """TODO(Person 3): fallback that checks ?session_id= with Stripe if the webhook didn't arrive."""
    return JSONResponse(jsonable_encoder(response(error='Not built yet.')), status_code=501)


@router.post('/webhooks/stripe')
async def stripe_webhook(request: Request):
    return JSONResponse({'error': 'Stripe webhook verification is not implemented yet.'}, status_code=503)


@router.post('/api/me/ntfy')
def set_ntfy_topic(request: Request, data: dict = Depends(json_body), user_id: int = Depends(require_user)):
    topic = str(data.get('topic', '')).strip()
    if not 6 <= len(topic) <= 64 or not topic.replace('-', '').replace('_', '').isalnum():
        return JSONResponse(jsonable_encoder(response(error='Topic must be 6-64 letters, numbers, - or _.')), status_code=400)
    with engine.begin() as conn:
        conn.execute(update(users).where(users.c.id == request.session['user_id']).values(ntfy_topic=topic))
    return response(ok=True, topic=topic)
