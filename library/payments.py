"""Stripe sandbox subscription. OWNER: Person 3.

Flow (see README "Stripe"):
1. POST /api/checkout creates a Checkout Session (mode='subscription', price=STRIPE_PRICE_ID,
   client_reference_id=str(user_id)) and returns its URL.
2. Stripe redirects back to /premium?session_id=...
3. POST /webhooks/stripe verifies the signature and, on checkout.session.completed,
   records a payments row and calls grant_premium(conn, user_id, 30, 'stripe').
   Must be idempotent: the same session_id twice must not double-grant.
4. Fallback for local demos: GET /api/checkout/confirm?session_id=... retrieves the session
   from Stripe and does the same as the webhook if it is paid.
SANDBOX ONLY: STRIPE_SECRET_KEY must start with sk_test_.
"""
import os
from datetime import timedelta

from sqlalchemy import update

from library import clock
from library.db import users


def stripe_client():
    import stripe
    key = os.environ['STRIPE_SECRET_KEY']
    if not key.startswith('sk_test_'):
        raise RuntimeError('Use a Stripe sandbox key (sk_test_...) only.')
    stripe.api_key = key
    return stripe


def grant_premium(conn, user_id, days, source):
    """Give a user premium for `days` days. Used by Stripe (source='stripe') and the
    leaderboard reward (source='leaderboard'). Shared contract: do not change the signature."""
    conn.execute(update(users).where(users.c.id == user_id).values(
        is_premium=True,
        premium_until=clock.now() + timedelta(days=days),
        premium_source=source,
    ))


def create_checkout_session(user, base_url):
    """Return the Stripe Checkout URL for this user. TODO(Person 3)"""
    raise NotImplementedError('Stripe checkout not built yet')


def handle_webhook(conn, payload, signature):
    """Verify and process a Stripe webhook. Return (body, http_status). TODO(Person 3)"""
    return {'received': True}, 200
