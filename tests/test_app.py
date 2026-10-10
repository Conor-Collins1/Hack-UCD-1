import pytest
from fastapi.testclient import TestClient
from app import main

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DATABASE', str(tmp_path / 'test.db'))
    with TestClient(main.app) as client:
        yield client

def test_no_reports(client):
    assert client.get('/api/status').json()['level'] is None
    assert client.get('/health').status_code == 200

def test_report_persists_and_cooldown(client):
    assert client.post('/api/reports', json={'level':2}).status_code == 201
    assert client.get('/api/status').json()['level'] == 2
    assert client.post('/api/reports', json={'level':0}).status_code == 429
    assert client.get('/api/status').json()['report_count'] == 1

@pytest.mark.parametrize('level', [-1,3,True,0.5,'2'])
def test_invalid_level(client, level):
    assert client.post('/api/reports',json={'level':level}).status_code == 422

def test_comments(client):
    assert client.post('/api/comments', json={'body':'   '}).status_code == 422
    assert client.post('/api/comments', json={'body':'Quiet upstairs'}).status_code == 201
    assert client.get('/api/comments').json()['comments'][0]['body'] == 'Quiet upstairs'
    assert client.post('/api/comments',json={'body':'Second'}).status_code == 429

def test_cross_origin_rejected(client):
    assert client.post('/api/reports',json={'level':1},headers={'Origin':'https://other.example'}).status_code == 403

def test_expired_reports_are_excluded(client):
    with main.database() as db:
        db.execute('INSERT INTO reports(visitor,level,created) VALUES(?,?,?)',('old',2,0))
    assert client.get('/api/status').json()['level'] is None

def test_page(client):
    assert 'Find your space' in client.get('/').text
