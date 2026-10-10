import pytest
from sqlalchemy import insert, select, func
from tests.test_api import client, login
from library import clock, db

PASSWORD = 'team-only-random-password-1234567890'


def unlock(client, monkeypatch):
    monkeypatch.setenv('FEEDBACK_ADMIN_PASSWORD', PASSWORD)
    return client.post('/api/feedback/access', json={'password': PASSWORD})


def test_submission_saved_and_private(client, monkeypatch):
    assert client.post('/api/feedback', json={'message': 'Hi'}).status_code == 401
    login(client)
    assert client.post('/api/feedback', json={'message': '  Make the map clearer  '}).status_code == 201
    assert client.get('/api/feedback').status_code == 401
    assert unlock(client, monkeypatch).status_code == 200
    items = client.get('/api/feedback').json()['feedback']
    assert items[0]['message'] == 'Make the map clearer'
    assert items[0]['name'] == 'Test'
    assert 'email' not in items[0]
    assert client.get('/api/me').json()['user']['points'] == 0
    assert client.post('/api/feedback/lock').status_code == 200
    assert client.get('/api/feedback').status_code == 401


@pytest.mark.parametrize('value', ['', '   ', 'x' * 2001, None, [], 7])
def test_invalid_feedback(client, value):
    login(client)
    assert client.post('/api/feedback', json={'message': value}).status_code == 400


def test_boundary_cooldown_and_safe_text(client, monkeypatch):
    from datetime import timedelta
    now = clock.now()
    monkeypatch.setattr(clock, 'now', lambda: now)
    login(client)
    assert client.post('/api/feedback', json={'message': 'x' * 2000}).status_code == 201
    assert client.post('/api/feedback', json={'message': 'Next'}).status_code == 429
    monkeypatch.setattr(clock, 'now', lambda: now + timedelta(seconds=60))
    assert client.post('/api/feedback', json={'message': '<script>alert(1)</script>'}).status_code == 201
    unlock(client, monkeypatch)
    assert client.get('/api/feedback').json()['feedback'][0]['message'] == '<script>alert(1)</script>'


def test_inbox_access_and_password_rotation(client, monkeypatch):
    monkeypatch.delenv('FEEDBACK_ADMIN_PASSWORD', raising=False)
    assert client.post('/api/feedback/access', json={'password': PASSWORD}).status_code == 503
    monkeypatch.setenv('FEEDBACK_ADMIN_PASSWORD', PASSWORD)
    assert client.post('/api/feedback/access', json={'password': 'wrong'}).status_code == 403
    assert client.post('/api/feedback/access', json={'password': []}).status_code == 403
    assert client.get('/api/feedback').status_code == 401
    unlock(client, monkeypatch)
    assert client.get('/api/feedback').json()['feedback'] == []
    monkeypatch.setenv('FEEDBACK_ADMIN_PASSWORD', PASSWORD + 'rotated')
    assert client.get('/api/feedback').status_code == 401


def test_pagination_and_pages(client, monkeypatch):
    identity = login(client).json()['user']['id']
    with db.engine.begin() as conn:
        conn.execute(insert(db.feedback), [{'user_id': identity, 'message': str(i)} for i in range(53)])
    unlock(client, monkeypatch)
    first = client.get('/api/feedback').json()
    assert len(first['feedback']) == 50
    second = client.get('/api/feedback', params={'before': first['next_before']}).json()
    assert len(second['feedback']) == 3
    assert second['next_before'] is None
    assert not ({x['id'] for x in first['feedback']} & {x['id'] for x in second['feedback']})
    page = client.get('/feedback').text
    assert 'feedback-password' in page
    assert client.get('/').text.count('id="feedback-form"') == 1


def test_schema_creation_preserves_existing_feedback(client):
    identity = login(client).json()['user']['id']
    with db.engine.begin() as conn:
        conn.execute(insert(db.feedback).values(user_id=identity, message='Keep this'))
    db.init_db()
    with db.engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(db.feedback)) == 1
