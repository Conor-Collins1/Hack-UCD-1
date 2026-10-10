"""AI summary and Stripe API. OWNER: Person 3.
Request/response shapes are fixed by CLAUDE.md."""
from fastapi import APIRouter, Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from library.http import response
import os


from library import ai, payments
from library.auth import current_user, require_user
from library.db import engine

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
