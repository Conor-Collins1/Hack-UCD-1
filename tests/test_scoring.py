"""Participation scoring and live leaderboard behavior."""
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import insert, select
from sqlalchemy.exc import SQLAlchemyError
from test_api import client, login
from library import clock, db, status


def test_points_for_report_and_comment_persist(client):
    login(client)
    assert client.get('/api/me').json()['user']['rank'] is None
    result = client.post('/api/reports', json={'level':'busy'})
    assert result.json()['points_awarded'] == 5
    assert client.post('/api/comments', json={'text':'Seats near the windows'}).json()['points_awarded'] == 2
    user = client.get('/api/me').json()['user']
    assert (user['points'],user['rank']) == (7,1)
    client.post('/api/logout')
    login(client)
    assert client.get('/api/me').json()['user']['points'] == 7
    board = client.get('/api/leaderboard').json()
    assert board['leaderboard'][0]['points'] == 7
    assert board['leaderboard'][0]['reports_total'] == 1
    assert board['current_user']['rank'] == 1
    assert 'email' not in board['leaderboard'][0]


def test_invalid_and_cooldown_submissions_do_not_earn_points(client):
    login(client)
    assert client.post('/api/reports',json={'level':'nonsense'}).status_code == 400
    assert client.post('/api/comments',json={'text':{'invalid':True}}).status_code == 400
    assert client.get('/api/me').json()['user']['points'] == 0
    assert client.post('/api/reports',json={'level':'full'}).status_code == 201
    assert client.post('/api/reports',json={'level':'busy'}).status_code == 429
    assert client.post('/api/comments',json={'text':'Quiet upstairs'}).status_code == 201
    assert client.post('/api/comments',json={'text':'Busy downstairs'}).status_code == 429
    assert client.get('/api/me').json()['user']['points'] == 7


def test_comment_cooldown_boundary_and_duplicates(client,monkeypatch):
    start=clock.now()
    monkeypatch.setattr(clock,'now',lambda:start)
    login(client)
    assert client.post('/api/comments',json={'text':'Quiet upstairs'}).status_code == 201
    monkeypatch.setattr(clock,'now',lambda:start+timedelta(seconds=59.5))
    assert client.post('/api/comments',json={'text':'More seats'}).status_code == 429
    monkeypatch.setattr(clock,'now',lambda:start+timedelta(seconds=60))
    assert client.post('/api/comments',json={'text':'  QUIET   Upstairs '}).status_code == 409
    assert client.get('/api/me').json()['user']['points'] == 2
    assert client.post('/api/comments',json={'text':'More seats'}).status_code == 201
    monkeypatch.setattr(clock,'now',lambda:start+timedelta(hours=2,seconds=1))
    assert client.post('/api/comments',json={'text':'Quiet upstairs'}).status_code == 201
    assert client.get('/api/me').json()['user']['points'] == 6


def test_ranking_ties_exclusion_and_own_position_beyond_top_ten(client):
    login(client)
    identity=client.get('/api/me').json()['user']['id']
    with db.engine.begin() as conn:
        for index in range(12):
            conn.execute(insert(db.users).values(name=f'Contributor {index}',email=f'{index}@demo.ie',points=100-index))
        conn.execute(insert(db.users).values(name='Tied first',email='tie@demo.ie',points=100))
        conn.execute(insert(db.users).values(name='Excluded',email='flagged@demo.ie',points=1000,flagged=True))
        conn.execute(db.users.update().where(db.users.c.id==identity).values(points=2))
    board=client.get('/api/leaderboard').json()
    assert len(board['leaderboard']) == 10
    assert [row['rank'] for row in board['leaderboard'][:3]] == [1,1,3]
    assert board['total_contributors'] == 14
    assert board['current_user']['rank'] == 14
    assert client.get('/api/me').json()['user']['rank'] == 14
    client.post('/api/logout')
    board=client.get('/api/leaderboard').json()
    assert board['current_user'] is None
    assert len(board['leaderboard']) == 10


def test_flagged_user_earns_nothing_and_has_no_rank(client):
    login(client)
    identity=client.get('/api/me').json()['user']['id']
    with db.engine.begin() as conn:
        conn.execute(db.users.update().where(db.users.c.id==identity).values(flagged=True))
    assert client.post('/api/reports',json={'level':'full'}).json()['points_awarded'] == 0
    assert client.post('/api/comments',json={'text':'Update'}).json()['points_awarded'] == 0
    assert client.get('/api/leaderboard').json()['leaderboard'] == []
    assert client.get('/api/me').json()['user']['rank'] is None


def test_failure_rolls_back_report_and_points(client,monkeypatch):
    login(client)
    def fail(*args):
        raise SQLAlchemyError('Synthetic write failure')
    monkeypatch.setattr(status,'save_snapshot',fail)
    assert client.post('/api/reports',json={'level':'full'}).status_code == 503
    assert client.get('/api/me').json()['user']['points'] == 0
    assert client.get('/api/status').json()['report_count'] == 0


def test_parallel_report_requests_award_once(client):
    login(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:client.post('/api/reports',json={'level':'full'}).status_code,range(2)))
    assert sorted(results) == [201,429]
    assert client.get('/api/me').json()['user']['points'] == 5


def test_empty_leaderboard_and_unranked_account(client):
    assert client.get('/api/leaderboard').json() == {'leaderboard':[], 'current_user':None, 'total_contributors':0}
    login(client)
    board=client.get('/api/leaderboard').json()
    assert board['current_user']['rank'] is None
    assert board['total_contributors'] == 0
