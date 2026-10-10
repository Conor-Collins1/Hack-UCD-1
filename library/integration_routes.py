"""AI summary, Stripe and notification-settings API. OWNER: Person 3.
Request/response shapes are fixed by CLAUDE.md."""
from flask import Blueprint, jsonify, request, session
from sqlalchemy import update

from library import ai, payments
from library.auth import current_user, login_required
from library.db import engine, users

bp = Blueprint('integrations', __name__)


@bp.get('/api/summary')
def get_summary():
    with engine.begin() as conn:
        return jsonify(ai.get_summary(conn))


@bp.post('/api/checkout')
@login_required
def checkout():
    with engine.connect() as conn:
        user = current_user(conn)
    try:
        url = payments.create_checkout_session(user, request.host_url)
    except NotImplementedError:
        return jsonify(error='Payments are not set up yet.'), 503
    return jsonify(url=url)


@bp.get('/api/checkout/confirm')
@login_required
def confirm_checkout():
    """TODO(Person 3): fallback that checks ?session_id= with Stripe if the webhook didn't arrive."""
    return jsonify(error='Not built yet.'), 501


@bp.post('/webhooks/stripe')
def stripe_webhook():
    with engine.begin() as conn:
        body, code = payments.handle_webhook(conn, request.get_data(), request.headers.get('Stripe-Signature', ''))
    return jsonify(body), code


@bp.post('/api/me/ntfy')
@login_required
def set_ntfy_topic():
    data = request.get_json(silent=True) or {}
    topic = str(data.get('topic', '')).strip()
    if not 6 <= len(topic) <= 64 or not topic.replace('-', '').replace('_', '').isalnum():
        return jsonify(error='Topic must be 6-64 letters, numbers, - or _.'), 400
    with engine.begin() as conn:
        conn.execute(update(users).where(users.c.id == session['user_id']).values(ntfy_topic=topic))
    return jsonify(ok=True, topic=topic)
