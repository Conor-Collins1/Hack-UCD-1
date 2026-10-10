"""Verified Stripe sandbox one-time purchases; no live payments."""
import os
from datetime import timedelta

import stripe
from sqlalchemy import insert, select, update

from library import clock
from library.db import payments, users
from library.trust import lock_user


class PaymentError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def stripe_client():
    key = os.environ.get('STRIPE_SECRET_KEY', '')
    if not key.startswith('sk_test_'):
        raise PaymentError('Sandbox payments are not configured yet.', 503)
    return stripe.StripeClient(key, max_network_retries=1,
                               http_client=stripe.RequestsClient(timeout=10))


def price_id():
    value = os.environ.get('STRIPE_PRICE_ID', '')
    if not value.startswith('price_'):
        raise PaymentError('The sandbox price is not configured yet.', 503)
    return value


def grant_premium(conn, user_id, days, source):
    """days=None means permanent; preserve permanent access for later reward calls."""
    existing = conn.execute(select(users).where(users.c.id == user_id)).mappings().first()
    if existing and existing['is_premium'] and existing['premium_until'] is None and days is not None:
        return
    conn.execute(update(users).where(users.c.id == user_id).values(
        is_premium=True,
        premium_until=None if days is None else clock.now() + timedelta(days=days),
        premium_source=source,
    ))


def create_checkout_session(user, base_url):
    if user['is_premium'] and (user['premium_until'] is None or clock.as_utc(user['premium_until']) > clock.now()):
        raise PaymentError('Your account already has Premium.', 409)
    client = stripe_client()
    price = client.v1.prices.retrieve(price_id()).to_dict()
    if price.get('livemode') is not False or price.get('type') != 'one_time' or not price.get('active') or price.get('unit_amount') != 199 or price.get('currency') != 'eur':
        raise PaymentError('Configure an active sandbox one-time price of EUR 1.99.', 503)
    session = client.v1.checkout.sessions.create({
        'mode': 'payment', 'payment_method_types': ['card'],
        'line_items': [{'price': price_id(), 'quantity': 1}],
        'client_reference_id': str(user['id']),
        'metadata': {'purpose': 'library_premium', 'price_id': price_id()},
        'customer_email': user['email'],
        'success_url': base_url + 'premium?session_id={CHECKOUT_SESSION_ID}',
        'cancel_url': base_url + 'premium?cancelled=1',
    })
    return session.url


def fulfill_checkout(conn, session_id, expected_user_id=None):
    if not isinstance(session_id, str) or not session_id.startswith('cs_test_') or len(session_id) > 200:
        raise PaymentError('That sandbox checkout reference is invalid.')
    session = stripe_client().v1.checkout.sessions.retrieve(session_id, {'expand': ['line_items']}).to_dict()
    try:
        user_id = int(session.get('client_reference_id', ''))
    except (ValueError, TypeError):
        raise PaymentError('This checkout is not linked to an account.')
    if expected_user_id is not None and user_id != expected_user_id:
        raise PaymentError('This checkout belongs to a different account.', 403)
    if session.get('livemode') is not False or session.get('mode') != 'payment' or session.get('metadata', {}).get('purpose') != 'library_premium':
        raise PaymentError('This is not a Library Premium sandbox purchase.')
    if session.get('status') != 'complete' or session.get('payment_status') != 'paid':
        raise PaymentError('Payment has not completed. Your account has not been charged by this demo.', 409)
    items = session.get('line_items', {})
    rows = items.get('data', [])
    if (items.get('has_more') or len(rows) != 1 or rows[0].get('quantity') != 1
            or rows[0].get('price', {}).get('id') != price_id()
            or session.get('amount_total') != 199 or session.get('currency') != 'eur'):
        raise PaymentError('This checkout does not match the Premium price.')
    lock_user(conn, user_id)
    user = conn.execute(select(users).where(users.c.id == user_id)).mappings().first()
    if user is None:
        raise PaymentError('The account for this checkout no longer exists.', 404)
    existing = conn.execute(select(payments).where(payments.c.stripe_session_id == session_id)).mappings().first()
    if existing is None:
        conn.execute(insert(payments).values(user_id=user_id, stripe_session_id=session_id,
            amount=session['amount_total'], currency=session['currency'], status='paid'))
        grant_premium(conn, user_id, None, 'stripe')
        conn.execute(update(users).where(users.c.id == user_id).values(stripe_customer_id=session.get('customer')))
    elif existing['user_id'] != user_id:
        raise PaymentError('This checkout is already linked to another account.', 409)
    return conn.execute(select(users).where(users.c.id == user_id)).mappings().one()


def handle_webhook(conn, payload, signature):
    secret = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
    if not secret.startswith('whsec_'):
        raise PaymentError('The sandbox webhook is not configured yet.', 503)
    try:
        event = stripe.Webhook.construct_event(payload, signature, secret).to_dict()
    except (ValueError, stripe.SignatureVerificationError):
        raise PaymentError('Invalid Stripe webhook signature.')
    if event.get('livemode') is not False:
        raise PaymentError('Only sandbox events are accepted.')
    if event.get('type') in ('checkout.session.completed', 'checkout.session.async_payment_succeeded'):
        session = event['data']['object']
        if session.get('metadata', {}).get('purpose') == 'library_premium' and session.get('payment_status') == 'paid':
            fulfill_checkout(conn, session['id'])
    return {'received': True}, 200
