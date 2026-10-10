"""API tests. Each person adds tests for their own features (see plan/).
Run: pytest"""
import os
import tempfile

import pytest

os.environ['DATABASE_URL'] = ''  # never touch the real database from tests


@pytest.fixture
def client(monkeypatch):
    from sqlalchemy import create_engine

    from library import db
    path = tempfile.mktemp(suffix='.db')
    engine = create_engine(f'sqlite:///{path}')
    for module in ('library.db', 'library.core_routes', 'library.integration_routes'):
        monkeypatch.setattr(f'{module}.engine', engine)
    db.metadata.create_all(engine)
    from app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c
    os.remove(path)


def login(client, email='test@demo.ie'):
    return client.post('/api/login', json={'name': 'Test', 'email': email})


def test_health(client):
    assert client.get('/health').status_code == 200


def test_status_shape(client):
    s = client.get('/api/status').get_json()
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
