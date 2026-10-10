"""Sandbox checkout and verified permanent account upgrades."""
import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import stripe
from sqlalchemy import func, select

from tests.test_api import client, login
from library import db, payments


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv('STRIPE_SECRET_KEY', 'sk_test_example')
    monkeypatch.setenv('STRIPE_PRICE_ID', 'price_premium')
    monkeypatch.setenv('STRIPE_WEBHOOK_SECRET', 'whsec_example')
    fake = Mock()
    fake.v1.prices.retrieve.return_value = stripe.Price.construct_from({'livemode': False, 'type': 'one_time', 'active': True, 'unit_amount': 199, 'currency': 'eur'}, None)
    fake.v1.checkout.sessions.create.return_value = SimpleNamespace(url='https://checkout.stripe.com/test')
    monkeypatch.setattr(stripe, 'StripeClient', Mock(return_value=fake))
    return fake


def paid(user_id):
    return {'id': 'cs_test_paid', 'client_reference_id': str(user_id), 'livemode': False,
        'mode': 'payment', 'status': 'complete', 'payment_status': 'paid',
        'metadata': {'purpose': 'library_premium', 'price_id': 'price_premium'},
        'amount_total': 199, 'currency': 'eur', 'customer': 'cus_test',
        'line_items': {'has_more': False, 'data': [{'quantity': 1, 'price': {'id': 'price_premium'}}]}}


def confirm(client):
    return client.get('/api/checkout/confirm?session_id=cs_test_paid')


def webhook(client, session, secret='whsec_example', **changes):
    event = {'type': 'checkout.session.completed', 'livemode': False, 'data': {'object': session}, **changes}
    body = json.dumps(event).encode()
    timestamp = int(time.time())
    digest = hmac.new(secret.encode(), str(timestamp).encode() + b'.' + body, hashlib.sha256).hexdigest()
    return client.post('/webhooks/stripe', content=body, headers={'stripe-signature': f't={timestamp},v1={digest}'})


def test_one_time_checkout(client, provider):
    identity = login(client).json()['user']['id']
    result = client.post('/api/checkout')
    assert result.status_code == 200
    args = provider.v1.checkout.sessions.create.call_args.args[0]
    assert args['mode'] == 'payment'
    assert args['client_reference_id'] == str(identity)
    assert args['line_items'] == [{'price': 'price_premium', 'quantity': 1}]
    assert '{CHECKOUT_SESSION_ID}' in args['success_url']


def test_paid_confirmation_is_permanent_and_idempotent(client, provider):
    identity = login(client).json()['user']['id']
    provider.v1.checkout.sessions.retrieve.return_value = stripe.checkout.Session.construct_from(paid(identity), None)
    for _ in range(2):
        result = confirm(client)
        assert result.status_code == 200
        assert result.json()['user']['is_premium'] is True
        assert result.json()['user']['premium_until'] is None
    assert webhook(client, paid(identity)).status_code == 200
    assert client.get('/api/me').json()['user']['premium_source'] == 'stripe'
    assert client.post('/api/checkout').status_code == 409
    with db.engine.begin() as conn:
        assert conn.scalar(select(func.count()).select_from(db.payments)) == 1
        payments.grant_premium(conn, identity, 30, 'leaderboard')
    assert client.get('/api/me').json()['user']['premium_until'] is None


def test_signed_webhook_without_login(client, provider):
    identity = login(client).json()['user']['id']
    client.post('/api/logout')
    provider.v1.checkout.sessions.retrieve.return_value = stripe.checkout.Session.construct_from(paid(identity), None)
    assert webhook(client, paid(identity)).status_code == 200
    login(client)
    assert client.get('/api/me').json()['user']['is_premium'] is True


@pytest.mark.parametrize('change', [
    {'payment_status': 'unpaid'}, {'status': 'open'}, {'livemode': True},
    {'mode': 'subscription'}, {'amount_total': 1}, {'currency': 'usd'},
    {'metadata': {}}, {'line_items': {'data': []}},
    {'line_items': {'data': [{'quantity': 1, 'price': {'id': 'price_other'}}]}},
    {'client_reference_id': 'invalid'}, {'client_reference_id': '9999'},
])
def test_invalid_payment_never_upgrades(client, provider, change):
    identity = login(client).json()['user']['id']
    provider.v1.checkout.sessions.retrieve.return_value = stripe.checkout.Session.construct_from({**paid(identity), **change}, None)
    assert confirm(client).status_code in (400, 403, 409)
    assert client.get('/api/me').json()['user']['is_premium'] is False


def test_other_users_session_rejected(client, provider):
    owner = login(client).json()['user']['id']
    client.post('/api/logout')
    login(client, 'other@demo.ie')
    provider.v1.checkout.sessions.retrieve.return_value = stripe.checkout.Session.construct_from(paid(owner), None)
    assert confirm(client).status_code == 403
    assert client.get('/api/me').json()['user']['is_premium'] is False


def test_webhook_signature_and_sandbox_guard(client, provider):
    identity = login(client).json()['user']['id']
    assert webhook(client, paid(identity), secret='whsec_wrong').status_code == 400
    assert webhook(client, paid(identity), livemode=True).status_code == 400
    assert client.get('/api/me').json()['user']['is_premium'] is False
    provider.v1.checkout.sessions.retrieve.assert_not_called()


def test_unpaid_and_unrelated_events_ignored(client, provider):
    identity = login(client).json()['user']['id']
    assert webhook(client, {**paid(identity), 'payment_status': 'unpaid'}).status_code == 200
    assert webhook(client, {}, type='customer.created').status_code == 200
    provider.v1.checkout.sessions.retrieve.assert_not_called()


@pytest.mark.parametrize('path', ['/api/checkout', '/api/checkout/confirm?session_id=cs_test_paid'])
def test_requires_login(client, provider, path):
    result = client.post(path) if path == '/api/checkout' else client.get(path)
    assert result.status_code == 401


def test_bad_session_id(client, provider):
    login(client)
    assert client.get('/api/checkout/confirm').status_code == 400
    assert client.get('/api/checkout/confirm?session_id=cs_live_bad').status_code == 400
    provider.v1.checkout.sessions.retrieve.assert_not_called()


def test_configuration_and_provider_errors(client, provider, monkeypatch):
    login(client)
    monkeypatch.setenv('STRIPE_SECRET_KEY', 'sk_live_disallowed')
    assert client.post('/api/checkout').status_code == 503
    monkeypatch.setenv('STRIPE_SECRET_KEY', 'sk_test_example')
    provider.v1.prices.retrieve.return_value.type = 'recurring'
    assert client.post('/api/checkout').status_code == 503
    provider.v1.prices.retrieve.side_effect = stripe.APIConnectionError('private detail')
    result = client.post('/api/checkout')
    assert result.status_code == 502
    assert 'private detail' not in result.text
    provider.v1.checkout.sessions.retrieve.side_effect = stripe.APIConnectionError('private detail')
    assert confirm(client).status_code == 502
    assert client.get('/api/me').json()['user']['is_premium'] is False


def test_webhook_then_confirmation_and_retry(client, provider):
    identity = login(client).json()['user']['id']
    provider.v1.checkout.sessions.retrieve.return_value = stripe.checkout.Session.construct_from(paid(identity), None)
    assert webhook(client, paid(identity)).status_code == 200
    assert webhook(client, paid(identity)).status_code == 200
    assert confirm(client).status_code == 200
    with db.engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(db.payments)) == 1


def test_webhook_provider_failure_is_retryable(client, provider):
    identity = login(client).json()['user']['id']
    provider.v1.checkout.sessions.retrieve.side_effect = stripe.APIConnectionError('private detail')
    assert webhook(client, paid(identity)).status_code == 502
    assert client.get('/api/me').json()['user']['is_premium'] is False


def test_concurrent_confirmations_create_one_payment(client, provider):
    from concurrent.futures import ThreadPoolExecutor
    identity = login(client).json()['user']['id']
    provider.v1.checkout.sessions.retrieve.return_value = stripe.checkout.Session.construct_from(paid(identity), None)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: confirm(client), range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    with db.engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(db.payments)) == 1


def test_premium_page_describes_one_time_purchase(client):
    page = client.get('/premium').text
    assert '€1.99 once' in page
    assert '/month' not in page
    assert 'permanently' in page
