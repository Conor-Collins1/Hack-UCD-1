"""AI summary and Stripe API. OWNER: Person 3.
Request/response shapes are fixed by CLAUDE.md."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from library.http import response
import os


from library import ai, payments
from library.auth import current_user, require_user, user_json
import stripe
from starlette.concurrency import run_in_threadpool
from library.db import engine

router = APIRouter()
@router.get('/api/summary')
def get_summary(request: Request):
    if not ai.summary_lock.acquire(blocking=False):
        with engine.connect() as conn:
            return response(ai.fallback(conn))
    try:
        with engine.begin() as conn:
            return response(ai.get_summary(conn))
    finally:
        ai.summary_lock.release()


def payment_error(exc):
    if isinstance(exc, payments.PaymentError):
        return JSONResponse({'error': str(exc)}, status_code=exc.status)
    return JSONResponse({'error': 'Stripe is unavailable. Please try again shortly.'}, status_code=502)


@router.post('/api/checkout')
def checkout(request: Request, user_id: int = Depends(require_user)):
    with engine.connect() as conn:
        user = current_user(conn, request)
    try:
        url = payments.create_checkout_session(user, os.environ.get('PUBLIC_URL', str(request.base_url)).rstrip('/') + '/')
        return response(url=url)
    except (payments.PaymentError, stripe.StripeError) as exc:
        return payment_error(exc)


@router.get('/api/checkout/confirm')
def confirm_checkout(request: Request, user_id: int = Depends(require_user)):
    try:
        with engine.begin() as conn:
            user = payments.fulfill_checkout(conn, request.query_params.get('session_id'), user_id)
            result = user_json(user, conn)
        return response(user=result)
    except (payments.PaymentError, stripe.StripeError) as exc:
        return payment_error(exc)


def process_webhook(payload, signature):
    try:
        with engine.begin() as conn:
            body, status = payments.handle_webhook(conn, payload, signature)
        return JSONResponse(body, status_code=status)
    except (payments.PaymentError, stripe.StripeError) as exc:
        return payment_error(exc)


@router.post('/webhooks/stripe')
async def stripe_webhook(request: Request):
    return await run_in_threadpool(process_webhook, await request.body(), request.headers.get('stripe-signature', ''))
