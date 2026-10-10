"""Persistent simulated alert history: transition rules, audience and concurrency."""
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import insert, select, func
from tests.test_api import client, login
from library import clock, db, status, notify


@pytest.fixture
def observed(monkeypatch):
    current = {'level': 'not_full', 'report_count': 1}
    monkeypatch.setattr(status, 'compute_status', lambda conn: dict(current))
    return current


def events(client):
    result = client.get('/api/notifications')
    assert result.status_code == 200
    return result.json()['notifications']


def test_first_busy_is_baseline_and_polls_do_not_duplicate(client, observed):
    observed['level'] = 'busy'
    assert events(client) == []
    observed['level'] = 'not_full'
    client.get('/api/status')
    observed['level'] = 'busy'
    for _ in range(4):
        client.get('/api/status')
        assert len(events(client)) == 1
    record = events(client)[0]
    assert record['kind'] == 'filling_up'
    assert record['from_level'] == 'not_full' and record['to_level'] == 'busy'
    assert record['eligible_users'] == 0
    assert record['delivery'] == 'simulated'
    assert record['created_at'].endswith('+00:00')
    assert 'user_id' not in record and 'email' not in record and 'name' not in record
    with db.engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(db.notifications_sent)) == 0


def test_both_alert_types_and_each_future_transition(client, observed):
    client.get('/api/status')
    for level in ['busy', 'full', 'busy', 'not_full', 'busy']:
        observed['level'] = level
        client.get('/api/status')
    assert [r['kind'] for r in events(client)] == ['filling_up', 'space_opening', 'filling_up']
    db.init_db()  # restart/deploy initialization must preserve history and current state
    assert len(events(client)) == 3


@pytest.mark.parametrize('initial,final', [('not_full','full'), ('full','not_full'), ('busy','full'), ('busy','busy')])
def test_only_requested_transitions_trigger(client, observed, initial, final):
    observed['level'] = initial
    client.get('/api/status')
    observed['level'] = final
    assert events(client) == []


def test_report_expiry_and_stale_observations_do_not_fake_space(client, observed, monkeypatch):
    now = clock.now()
    monkeypatch.setattr(clock, 'now', lambda: now)
    observed['level'] = 'full'
    client.get('/api/status')
    observed.update(level='not_full', report_count=0)
    client.get('/api/status')
    observed.update(level='busy', report_count=1)
    assert events(client) == []
    observed['level'] = 'full'
    client.get('/api/status')
    monkeypatch.setattr(clock, 'now', lambda: now + timedelta(minutes=46))
    observed['level'] = 'busy'
    assert events(client) == []


def test_audience_only_active_premium_at_trigger_time(client, observed):
    now = clock.now()
    with db.engine.begin() as conn:
        for i, (premium, expires) in enumerate([
            (True,None), (True,now+timedelta(days=30)), (True,now-timedelta(seconds=1)),
            (True,now), (False,None)
        ]):
            conn.execute(insert(db.users).values(name='Demo', email=f'premium{i}@example.test',
                is_premium=premium, premium_until=expires))
    client.get('/api/status')
    observed['level'] = 'busy'
    assert events(client)[0]['eligible_users'] == 2
    with db.engine.begin() as conn:
        conn.execute(db.users.update().values(is_premium=False))
    assert events(client)[0]['eligible_users'] == 2  # historical audience is a snapshot


def test_simultaneous_polls_save_one_event(client, observed):
    client.get('/api/status')
    observed['level'] = 'busy'
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: client.get('/api/notifications'), range(8)))
    assert all(r.status_code == 200 for r in results)
    assert len(events(client)) == 1


def test_event_and_state_rollback_together(client, observed):
    client.get('/api/status')
    observed['level'] = 'busy'
    with pytest.raises(RuntimeError):
        with db.engine.begin() as conn:
            notify.capture_status(conn)
            raise RuntimeError('abort')
    with db.engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(db.notification_events)) == 0
        assert conn.scalar(select(db.notification_state.c.level)) == 'not_full'
    assert len(events(client)) == 1


def test_real_report_submissions_record_rising_busy(client):
    login(client, 'first@example.test')
    assert client.post('/api/reports', json={'level': 'not_full'}).status_code == 201
    login(client, 'second@example.test')
    assert client.post('/api/reports', json={'level': 'busy'}).json()['status']['level'] == 'not_full'
    login(client, 'third@example.test')
    assert client.post('/api/reports', json={'level': 'busy'}).json()['status']['level'] == 'busy'
    assert [r['kind'] for r in events(client)] == ['filling_up']


def test_real_report_submissions_record_space_opening(client):
    login(client, 'full@example.test')
    client.post('/api/reports', json={'level': 'full'})
    login(client, 'still-full@example.test')
    assert client.post('/api/reports', json={'level': 'busy'}).json()['status']['level'] == 'full'
    login(client, 'space@example.test')
    assert client.post('/api/reports', json={'level': 'not_full'}).json()['status']['level'] == 'busy'
    assert [r['kind'] for r in events(client)] == ['space_opening']


def test_public_history_pagination_and_page(client, observed):
    with db.engine.begin() as conn:
        conn.execute(insert(db.notification_events), [
            {'kind':'filling_up','from_level':'not_full','to_level':'busy','eligible_users':0}
            for _ in range(53)])
    first = client.get('/api/notifications').json()
    assert len(first['notifications']) == 50
    second = client.get('/api/notifications', params={'before':first['next_before']}).json()
    assert len(second['notifications']) == 3 and second['next_before'] is None
    assert not ({r['id'] for r in first['notifications']} & {r['id'] for r in second['notifications']})
    page = client.get('/premium').text
    assert 'Full drops to ~80%' in page
    assert 'Know when it reaches ~80% full' in page
    assert 'not sent yet' in page
    assert 'id="notification-history"' in page
    assert '€1.99 once' in page
