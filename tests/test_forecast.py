"""Premium 1-hour forecast: access control, ordinary/boundary/failure inputs, and accuracy."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import insert, select, update

from library import clock, db, forecast
from scripts import generate_history
from tests.test_api import client, login  # noqa: F401  (fixture)

DUBLIN = forecast.LOCAL_TZ
TUESDAY_1PM = datetime(2026, 10, 13, 13, 0, tzinfo=DUBLIN)   # open now and in an hour
TUESDAY_930PM = datetime(2026, 10, 13, 21, 30, tzinfo=DUBLIN)  # closes at 22:00


@pytest.fixture
def at(monkeypatch):
    def set_time(local_dt):
        fixed = local_dt.astimezone(timezone.utc)
        monkeypatch.setattr(clock, 'now', lambda: fixed)
    return set_time


@pytest.fixture(autouse=True)
def fresh_profile():
    forecast._cached_profile.cache_clear()
    yield
    forecast._cached_profile.cache_clear()


def make_premium(premium_until=None):
    with db.engine.begin() as conn:
        conn.execute(update(db.users).values(is_premium=True, premium_until=premium_until, premium_source='stripe'))


# ---- Access control ----

def test_logged_out_gets_401(client):
    assert client.get('/api/forecast').status_code == 401


def test_free_user_gets_403_with_premium_flag(client):
    login(client)
    response = client.get('/api/forecast')
    assert response.status_code == 403
    assert response.json() == {'error': 'The 1-hour forecast is a Premium feature.', 'premium_required': True}


def test_expired_premium_is_refused(client, at):
    at(TUESDAY_1PM)
    login(client)
    make_premium(premium_until=clock.now() - timedelta(minutes=1))
    assert client.get('/api/forecast').status_code == 403


# ---- Ordinary use ----

def test_premium_forecast_shape(client, at):
    at(TUESDAY_1PM)
    login(client)
    make_premium()
    f = client.get('/api/forecast').json()
    assert f['open'] is True
    assert f['level'] in db.LEVELS and f['label'] == db.LEVEL_LABEL[f['level']]
    assert 0 <= f['range'][0] <= f['score'] <= f['range'][1] <= 1
    assert f['used_live_data'] is False and f['confidence'] in ('medium', 'low')
    assert f['forecast_for'] == (TUESDAY_1PM + timedelta(hours=1)).astimezone(timezone.utc).isoformat()
    assert 'synthetic' in f['data_note']


def test_live_reports_move_the_forecast(client, at):
    at(TUESDAY_1PM)
    login(client)
    make_premium()
    without_live = client.get('/api/forecast').json()
    with db.engine.begin() as conn:
        user_id = conn.execute(select(db.users.c.id)).scalar()
        conn.execute(insert(db.reports).values(user_id=user_id, level='not_full', created_at=clock.now()))
    with_live = client.get('/api/forecast').json()
    assert with_live['used_live_data'] is True
    assert with_live['score'] < without_live['score']  # quieter than typical now -> quieter in an hour
    assert 'quieter than' in with_live['explanation']


# ---- Boundaries ----

def test_closed_in_an_hour(client, at):
    at(TUESDAY_930PM)
    login(client)
    make_premium()
    f = client.get('/api/forecast').json()
    assert f['open'] is False and f['label'] == 'Closed' and f['level'] is None


def test_level_thresholds_match_live_status():
    assert forecast.level_for(0.0) == 'not_full'
    assert forecast.level_for(0.499) == 'not_full'
    assert forecast.level_for(0.5) == 'busy'
    assert forecast.level_for(0.9) == 'busy'
    assert forecast.level_for(0.901) == 'full'


def test_forecast_is_clamped_to_0_1():
    profile = {forecast.slot_key(TUESDAY_1PM): (0.95, 0.02),
               forecast.slot_key(TUESDAY_1PM + timedelta(hours=1)): (0.98, 0.02)}
    assert forecast.predict(profile, TUESDAY_1PM, live_score=1.0, live_weight=5)['score'] == 1.0
    assert forecast.predict(profile, TUESDAY_1PM, live_score=0.0, live_weight=5)['score'] == 0.0


def test_live_ignored_when_library_closed_now():
    early = datetime(2026, 10, 13, 7, 30, tzinfo=DUBLIN)  # opens 08:00; forecast for 08:30
    profile = {forecast.slot_key(early + timedelta(hours=1)): (0.2, 0.05)}
    result = forecast.predict(profile, early, live_score=1.0)
    assert result['open'] and not result['used_live'] and result['score'] == 0.2


# ---- Failure inputs ----

@pytest.mark.parametrize('content', ['', 'local_time,score\n', 'local_time,score\n2026-10-01T10:00,1.7\n',
                                     'local_time,score\nnot-a-date,0.5\n', 'wrong,headers\n1,2\n'])
def test_bad_history_returns_503(client, at, tmp_path, monkeypatch, content):
    path = tmp_path / 'history.csv'
    path.write_text(content)
    monkeypatch.setattr(forecast, 'HISTORY_PATH', path)
    at(TUESDAY_1PM)
    login(client)
    make_premium()
    response = client.get('/api/forecast')
    assert response.status_code == 503
    assert response.json() == {'error': 'The forecast is temporarily unavailable. Please try again later.'}


def test_missing_history_returns_503(client, at, tmp_path, monkeypatch):
    monkeypatch.setattr(forecast, 'HISTORY_PATH', tmp_path / 'missing.csv')
    at(TUESDAY_1PM)
    login(client)
    make_premium()
    assert client.get('/api/forecast').status_code == 503


# ---- Data and accuracy ----

def test_generator_is_reproducible_and_plausible():
    rows = generate_history.generate()
    assert rows == generate_history.generate()
    assert all(0 <= score <= 1 and forecast.is_open(t) for t, score in rows)
    assert len({t.date() for t, _ in rows}) == 35


def test_committed_csv_matches_generator():
    assert forecast.read_history(forecast.HISTORY_PATH) == [
        (datetime.fromisoformat(t.isoformat(timespec='minutes')), s) for t, s in generate_history.generate()]


def test_backtest_beats_baselines_with_noisy_live_reports():
    result = forecast.backtest(generate_history.generate(), live_noise=0.15)
    mae = result['mae']
    chosen = mae[f'typical + {forecast.LIVE_WEIGHT:.2f} x live gap']
    assert chosen < mae['same as now (baseline)']
    assert chosen < mae['typical pattern only']
    assert chosen == min(mae.values())  # LIVE_WEIGHT is the best tested weight
