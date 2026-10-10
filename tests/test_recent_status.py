"""Fresh reports must replace older occupancy estimates without deleting history."""
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import insert, select, func
from library import clock, db, status
from tests.test_api import client


@pytest.fixture
def scenario(client, monkeypatch):
    now = datetime(2026,10,10,12,tzinfo=timezone.utc)
    monkeypatch.setattr(clock, 'now', lambda: now)
    identity = 0
    def add(level, age=0, user_id=None, trust=0.5, flagged=False):
        nonlocal identity
        with db.engine.begin() as conn:
            if user_id is None:
                identity += 1
                user_id = conn.execute(insert(db.users).values(name='Demo', email=f'user{identity}@example.test',
                    trust_score=trust, flagged=flagged, created_at=now)).inserted_primary_key[0]
            conn.execute(insert(db.reports).values(user_id=user_id, level=level, created_at=now-timedelta(minutes=age)))
        return user_id
    def compute():
        with db.engine.connect() as conn:
            return status.compute_status(conn)
    return now, add, compute


def test_three_fresh_full_reports_replace_many_old_busy_votes(scenario):
    now, add, compute = scenario
    for _ in range(40): add('busy', 15)
    for _ in range(3): add('full')
    result = compute()
    assert result['level'] == 'full'
    assert result['score'] == 1
    assert result['report_count'] == 3
    assert result['confidence'] == 'medium'
    with db.engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(db.reports)) == 43


def test_three_newest_full_outvote_two_recent_busy(scenario):
    now, add, compute = scenario
    for _ in range(20): add('busy', 4)
    for _ in range(3): add('full')
    result = compute()
    assert result['level'] == 'full'
    assert result['report_count'] == 5
    assert result['confidence'] == 'high'


def test_fresh_busy_reports_clear_old_full_hysteresis(scenario):
    now, add, compute = scenario
    for _ in range(15): add('full', 10)
    with db.engine.begin() as conn:
        conn.execute(insert(db.status_snapshots).values(level='full',score=1,report_count=15,created_at=now-timedelta(minutes=1)))
    for _ in range(3): add('busy')
    assert compute()['level'] == 'busy'
    assert compute()['score'] == pytest.approx(.8)


def test_discarded_reports_never_reappear_when_fresh_votes_age(scenario, monkeypatch):
    now, add, compute = scenario
    for _ in range(30): add('busy', 10)
    for _ in range(3): add('full')
    assert compute()['report_count'] == 3
    monkeypatch.setattr(clock, 'now', lambda: now+timedelta(minutes=6))
    result = compute()
    assert result['level'] == 'full'
    assert result['report_count'] == 3
    assert result['confidence'] == 'low'


def test_latest_vote_per_person_and_no_fake_fresh_consensus(scenario):
    now, add, compute = scenario
    one = add('not_full', 10)
    add('busy', 9)
    for i in range(6): add('full', age=i / 60, user_id=one)
    result = compute()
    assert result['report_count'] == 2
    assert result['confidence'] == 'low'
    assert result['level'] == 'full'  # old busy has only one-eighth the current vote's weight


def test_half_life_is_three_minutes_in_sparse_fallback(scenario):
    now, add, compute = scenario
    add('full', 3)
    add('not_full')
    assert compute()['score'] == pytest.approx(1/3, abs=.0001)
    assert compute()['confidence'] == 'low'


def test_five_minute_boundary_is_inclusive(scenario, monkeypatch):
    now, add, compute = scenario
    add('full', 5)
    add('full')
    add('full')
    assert compute()['confidence'] == 'medium'
    monkeypatch.setattr(clock, 'now', lambda: now+timedelta(seconds=1))
    assert compute()['confidence'] == 'low'
    assert compute()['report_count'] == 3


def test_flagged_zero_trust_future_and_expired_votes_cannot_force_consensus(scenario):
    now, add, compute = scenario
    add('busy')
    add('full', flagged=True)
    add('full', trust=0)
    add('full', age=-1)
    add('full', age=46)
    result = compute()
    assert result['report_count'] == 1
    assert result['confidence'] == 'low'
    assert result['level'] == 'busy'


def test_new_report_after_quiet_gap_does_not_resurrect_discarded_votes(scenario, monkeypatch):
    now, add, compute = scenario
    for _ in range(20): add('busy', 15)
    for _ in range(3): add('full', 6)
    add('not_full')
    assert compute()['report_count'] == 4
    monkeypatch.setattr(clock, 'now', lambda: now+timedelta(minutes=46))
    result = compute()
    assert result['report_count'] == 0
    assert result['label'] == 'No recent reports'


def test_equal_timestamps_use_newest_ids_deterministically(scenario):
    now, add, compute = scenario
    for _ in range(10): add('busy')
    for _ in range(5): add('full')
    assert compute()['score'] == 1
    assert compute()['report_count'] == 5


def test_live_submissions_switch_to_full_after_three_new_full_reports(client, scenario):
    from tests.test_api import login
    now, add, compute = scenario
    for _ in range(30): add('busy', 1)
    assert client.get('/api/status').json()['level'] == 'busy'
    for i in range(3):
        login(client, f'fresh-full{i}@example.test')
        result = client.post('/api/reports', json={'level': 'full'})
        assert result.status_code == 201
        assert result.json()['points_awarded'] == 5
        assert result.json()['status']['level'] == ('full' if i == 2 else 'busy')
    live = client.get('/api/status').json()
    assert live['level'] == 'full' and live['report_count'] == 5
