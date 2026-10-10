"""API tests. Each person adds tests for their own features (see plan/).
Run: pytest"""
import os
import tempfile

import pytest

os.environ['DATABASE_URL'] = ''  # never touch the real database from tests


@pytest.fixture
def client(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from fastapi.testclient import TestClient
    from library import db
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    for module in ('library.db', 'library.auth', 'library.core_routes', 'library.integration_routes'):
        monkeypatch.setattr(f'{module}.engine', engine)
    from app.main import app
    with TestClient(app) as client:
        yield client
    engine.dispose()


def login(client, email='test@demo.ie'):
    return client.post('/api/login', json={'name': 'Test', 'email': email})


def test_health(client):
    assert client.get('/health').status_code == 200


def test_status_shape(client):
    s = client.get('/api/status').json()
    assert set(s) >= {'level', 'label', 'score', 'confidence', 'report_count', 'trend_per_min', 'updated_at'}


def test_report_requires_login(client):
    assert client.post('/api/reports', json={'level': 'full'}).status_code == 401


def test_report_rejects_bad_level(client):
    login(client)
    assert client.post('/api/reports', json={'level': 'packed'}).status_code == 400


def test_report_then_cooldown(client):
    login(client)
    assert client.post('/api/reports', json={'level': 'full'}).status_code == 201
    assert client.post('/api/reports', json={'level': 'full'}).status_code == 429


def test_comment_too_long(client):
    login(client)
    assert client.post('/api/comments', json={'text': 'x' * 281}).status_code == 400

@pytest.mark.parametrize('path', ['/', '/account', '/premium', '/leaderboard', '/docs', '/openapi.json', '/static/style.css', '/static/app.js'])
def test_pages_and_assets(client, path):
    assert client.get(path).status_code == 200


def test_login_session_and_logout(client):
    assert login(client).status_code == 200
    assert client.get('/api/me').json()['user']['email'] == 'test@demo.ie'
    assert client.post('/api/logout').status_code == 200
    assert client.get('/api/me').status_code == 401


def test_saved_report_updates_live_status(client):
    login(client)
    result = client.post('/api/reports', json={'level': 'full'})
    assert result.status_code == 201
    assert result.json()['status']['level'] == 'full'
    status = client.get('/api/status').json()
    assert status['report_count'] == 1
    assert status['level'] == 'full'


def test_comments_persist_and_validate(client):
    login(client)
    assert client.post('/api/comments', json={'text': 'Quiet upstairs'}).status_code == 201
    assert client.get('/api/comments').json()['comments'][0]['text'] == 'Quiet upstairs'
    assert client.post('/api/comments', json={'text': '  '}).status_code == 400


def test_json_errors_and_csrf(client):
    result = client.post('/api/login', content='{broken', headers={'Content-Type': 'application/json'})
    assert result.status_code == 400
    assert 'error' in result.json()
    assert client.post('/api/login', json={'name': 'Test', 'email':'test@demo.ie'}, headers={'Origin':'https://other.example'}).status_code == 403
    assert client.get('/missing').json() == {'error':'Not Found'}
    assert client.post('/api/login', json=['wrong shape']).status_code == 400


def test_request_limit(client):
    result = client.post('/api/login', content=b'x' * 65537)
    assert result.status_code == 413


def test_demo_and_integrations_not_falsely_available(client, monkeypatch):
    monkeypatch.setenv('DEMO_MODE','0')
    assert client.post('/api/demo/reports',json={'email':'demo@demo.ie','level':'full'}).status_code == 404
    assert client.get('/api/summary').json()['status'] == 'not_enough'
    login(client)
    assert client.post('/api/checkout').status_code == 503
    assert client.post('/webhooks/stripe',content=b'raw payload').status_code == 503
    assert client.post('/api/me/ntfy',json={'topic':'library-demo-topic'}).status_code == 200
    assert client.get('/api/me').json()['user']['ntfy_topic'] == 'library-demo-topic'


def test_status_decay_exclusion_and_hysteresis(client, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import insert
    from library import clock, db, status
    fixed = datetime(2026,10,10,12,tzinfo=timezone.utc)
    monkeypatch.setattr(clock,'now',lambda:fixed)
    with db.engine.begin() as conn:
        one = conn.execute(insert(db.users).values(name='One',email='one@demo.ie',created_at=fixed)).inserted_primary_key[0]
        two = conn.execute(insert(db.users).values(name='Two',email='two@demo.ie',created_at=fixed)).inserted_primary_key[0]
        conn.execute(insert(db.reports),[
            {'user_id':one,'level':'full','created_at':fixed-timedelta(minutes=15)},
            {'user_id':two,'level':'not_full','created_at':fixed},
        ])
        result=status.compute_status(conn)
        assert result['score'] == pytest.approx(1/3,abs=.0001)
        conn.execute(db.reports.delete())
        conn.execute(insert(db.reports).values(user_id=one,level='busy',created_at=fixed))
        conn.execute(insert(db.status_snapshots).values(level='full',score=1,report_count=1,created_at=fixed-timedelta(minutes=1)))
        assert status.compute_status(conn)['level'] == 'full'  # at 0.8, remain full
        conn.execute(db.users.update().where(db.users.c.id==one).values(flagged=True))
        assert status.compute_status(conn)['report_count'] == 0
        conn.execute(db.users.update().where(db.users.c.id==one).values(flagged=False))
        conn.execute(db.reports.update().values(created_at=fixed-timedelta(minutes=46)))
        assert status.compute_status(conn)['label'] == 'No recent reports'


def test_demo_report_uses_same_contract(client, monkeypatch):
    monkeypatch.setenv('DEMO_MODE','1')
    response=client.post('/api/demo/reports',json={'email':'demo@demo.ie','level':'busy'})
    assert response.status_code == 201
    assert response.json()['status']['level'] == 'busy'
