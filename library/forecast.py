"""Premium one-hour occupancy forecast.

Method (explainable, no ML library):
    forecast = typical score for (weekday, time in 1 hour)
             + LIVE_WEIGHT * (live score now - typical score for now)
"Typical" is a recency-weighted average of the SYNTHETIC history in data/occupancy_history.csv
(recent weeks count more, so an exam-season rise is picked up). If nobody has reported in the
last 45 minutes, the forecast uses the typical pattern alone. LIVE_WEIGHT = 0.5 was the best
weight in backtest() when live readings are noisy like real reports (perfect readings favour 1.0).
"""
import csv
import logging
import math
import random
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from library import clock
from library.db import LEVEL_LABEL

HISTORY_PATH = Path(__file__).resolve().parent.parent / 'data' / 'occupancy_history.csv'
LOCAL_TZ = ZoneInfo('Europe/Dublin')
SLOT_MINUTES = 15
HORIZON_MINUTES = 60
LIVE_WEIGHT = 0.5
RECENCY_DECAY = 0.7  # each week further back counts 0.7x as much
OPEN_HOURS = {0: (8, 22), 1: (8, 22), 2: (8, 22), 3: (8, 22), 4: (8, 22), 5: (10, 18), 6: (10, 18)}
DATA_NOTE = ('Forecast based on 5 weeks of synthetic history plus live reports. '
             'With real reports collected over time, the same method learns the real pattern.')
logger = logging.getLogger(__name__)


class ForecastUnavailable(Exception):
    pass


def level_for(score):
    """Same thresholds as the live status (without hysteresis)."""
    return 'full' if score > 0.9 else 'busy' if score >= 0.5 else 'not_full'


def slot_key(local_dt):
    return local_dt.weekday(), (local_dt.hour * 60 + local_dt.minute) // SLOT_MINUTES


def is_open(local_dt):
    opens, closes = OPEN_HOURS[local_dt.weekday()]
    return opens <= local_dt.hour < closes


def read_history(path):
    rows = []
    try:
        with open(path, newline='') as f:
            lines = (line for line in f if not line.startswith('#'))
            for row in csv.DictReader(lines):
                score = float(row['score'])
                if not 0 <= score <= 1:
                    raise ValueError('score out of range')
                rows.append((datetime.fromisoformat(row['local_time']), score))
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ForecastUnavailable(f'History unreadable: {type(error).__name__}') from error
    if not rows:
        raise ForecastUnavailable('History is empty')
    return rows


def build_profile(rows):
    """{(weekday, slot): (weighted mean, weighted std)} with recent weeks weighted more."""
    latest = max(t for t, _ in rows)
    sums = {}
    for t, score in rows:
        weight = RECENCY_DECAY ** ((latest - t).days // 7)
        w_total, w_score, w_sq = sums.get(slot_key(t), (0.0, 0.0, 0.0))
        sums[slot_key(t)] = (w_total + weight, w_score + weight * score, w_sq + weight * score * score)
    profile = {}
    for key, (w_total, w_score, w_sq) in sums.items():
        mean = w_score / w_total
        profile[key] = (mean, math.sqrt(max(0.0, w_sq / w_total - mean * mean)))
    return profile


@lru_cache(maxsize=1)
def _cached_profile():
    return build_profile(read_history(HISTORY_PATH))


def predict(profile, now_local, live_score=None, live_weight=LIVE_WEIGHT):
    """Pure forecast for HORIZON_MINUTES after now_local (an aware or naive local datetime)."""
    target = now_local + timedelta(minutes=HORIZON_MINUTES)
    if not is_open(target) or slot_key(target) not in profile:
        return {'open': False, 'target': target}
    typical, spread = profile[slot_key(target)]
    now_typical = profile.get(slot_key(now_local)) if is_open(now_local) else None
    used_live = live_score is not None and now_typical is not None
    score = typical + live_weight * (live_score - now_typical[0]) if used_live else typical
    score = min(1.0, max(0.0, score))
    if used_live:
        confidence = 'high' if spread < 0.08 else 'medium' if spread < 0.15 else 'low'
    else:
        confidence = 'medium' if spread < 0.08 else 'low'
    return {'open': True, 'target': target, 'score': score, 'typical': typical, 'spread': spread,
            'used_live': used_live, 'confidence': confidence}


def get_forecast(live_status):
    """API response for GET /api/forecast. live_status is status.compute_status(conn)."""
    profile = _cached_profile()
    now_local = clock.now().astimezone(LOCAL_TZ)
    live = live_status['score'] if live_status.get('report_count') else None
    result = predict(profile, now_local, live)
    target_utc = result['target'].astimezone(clock.now().tzinfo).isoformat()
    base = {'forecast_for': target_utc, 'horizon_minutes': HORIZON_MINUTES, 'data_note': DATA_NOTE}
    if not result['open']:
        return {**base, 'open': False, 'level': None, 'label': 'Closed', 'score': None, 'range': None,
                'typical_score': None, 'used_live_data': False, 'confidence': None,
                'explanation': 'The library is expected to be closed by then.'}
    score, typical = result['score'], result['typical']
    level = level_for(score)
    if result['used_live']:
        gap = score - typical
        mood = 'busier than' if gap > 0.03 else 'quieter than' if gap < -0.03 else 'about the same as'
        explanation = f'Live reports suggest it will be {mood} a typical {result["target"]:%A} at this time.'
    else:
        explanation = f'No live reports right now, so this uses the typical {result["target"]:%A} pattern.'
    low = max(0.0, score - result['spread'])
    high = min(1.0, score + result['spread'])
    return {**base, 'open': True, 'level': level, 'label': LEVEL_LABEL[level], 'score': round(score, 3),
            'range': [round(low, 3), round(high, 3)], 'typical_score': round(typical, 3),
            'used_live_data': result['used_live'], 'confidence': result['confidence'],
            'explanation': explanation}


def backtest(rows, test_days=7, weights=(0.0, 0.25, 0.5, 0.75, 1.0), live_noise=0.0, seed=1):
    """Train on everything before the final test_days; predict 1 hour ahead across the final days,
    using the actual score 'now' (plus optional Gaussian live_noise, to mimic imperfect student
    reports) as the live reading. Compares against two baselines."""
    rng = random.Random(seed)
    cutoff = max(t for t, _ in rows) - timedelta(days=test_days)
    cutoff = cutoff.replace(hour=23, minute=59)
    train = [r for r in rows if r[0] <= cutoff]
    test = {t: s for t, s in rows if t > cutoff}
    profile = build_profile(train)
    errors = {'same as now (baseline)': []}
    errors.update({f'typical + {w:.2f} x live gap' if w else 'typical pattern only': [] for w in weights})
    level_hits = baseline_hits = 0
    points = 0
    for t, now_score in test.items():
        target = t + timedelta(minutes=HORIZON_MINUTES)
        if target not in test:
            continue
        actual = test[target]
        live = min(1.0, max(0.0, now_score + rng.gauss(0, live_noise))) if live_noise else now_score
        points += 1
        errors['same as now (baseline)'].append(abs(live - actual))
        baseline_hits += level_for(live) == level_for(actual)
        for w in weights:
            p = predict(profile, t, live, live_weight=w)
            name = f'typical + {w:.2f} x live gap' if w else 'typical pattern only'
            errors[name].append(abs(p['score'] - actual))
            if w == LIVE_WEIGHT:
                level_hits += level_for(p['score']) == level_for(actual)
    train_days = len({t.date() for t, _ in train})
    return {'train_days': train_days, 'test_days': test_days, 'test_points': points,
            'mae': {name: sum(e) / len(e) for name, e in errors.items()},
            'level_accuracy': level_hits / points, 'baseline_level_accuracy': baseline_hits / points}
