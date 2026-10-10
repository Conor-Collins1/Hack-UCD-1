"""The app's clock. Always use clock.now(), never datetime.now().

With DEMO_SPEED=60 in .env, time runs 60x faster (1 real second = 1 app minute),
so decay windows, cooldowns and rate limits all shrink for the live demo.
Only use DEMO_SPEED with a single local process (uvicorn app.main:app), not on Render.
"""
import os
import time
from datetime import datetime, timedelta, timezone

_START_REAL = time.time()
_START_APP = datetime.now(timezone.utc)


def speed():
    return float(os.environ.get('DEMO_SPEED', '1'))


def now():
    elapsed = time.time() - _START_REAL
    return _START_APP + timedelta(seconds=elapsed * speed())


def as_utc(dt):
    """SQLite drops timezones on read. Wrap every datetime you read from the DB in this."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
