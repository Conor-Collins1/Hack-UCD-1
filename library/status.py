"""Turn recent, trusted reports into occupancy estimates. OWNER: Person 1."""
from datetime import timedelta
from sqlalchemy import insert, select
from library import clock
from library.db import LEVEL_LABEL, LEVEL_SCORE, reports, status_snapshots, users

WINDOW_MINUTES = 45
HALF_LIFE_MINUTES = 15
FULL_ENTER = 0.9
FULL_EXIT = 0.8


def compute_status(conn):
    now = clock.now()
    rows = conn.execute(
        select(reports.c.level, reports.c.created_at, users.c.trust_score)
        .join(users, users.c.id == reports.c.user_id)
        .where(reports.c.created_at >= now - timedelta(minutes=WINDOW_MINUTES),
               reports.c.created_at <= now, users.c.flagged.is_(False))
    ).mappings().all()
    weights = [0.5 ** ((now-clock.as_utc(r['created_at'])).total_seconds()/60/HALF_LIFE_MINUTES) * r['trust_score'] for r in rows]
    total = sum(weights)
    score = sum(LEVEL_SCORE[r['level']]*w for r,w in zip(rows,weights))/total if total else 0.0
    previous = conn.execute(select(status_snapshots).order_by(status_snapshots.c.created_at.desc()).limit(1)).mappings().first()
    # Ignore stale hysteresis after the entire reporting window has elapsed.
    was_full = previous and previous['level'] == 'full' and clock.as_utc(previous['created_at']) >= now-timedelta(minutes=WINDOW_MINUTES)
    level = 'full' if (was_full and score >= FULL_EXIT) or score > FULL_ENTER else 'busy' if score >= 0.5 else 'not_full'
    reference = conn.execute(select(status_snapshots).where(
        status_snapshots.c.created_at <= now-timedelta(minutes=20),
        status_snapshots.c.created_at >= now-timedelta(minutes=45)
    ).order_by(status_snapshots.c.created_at.desc()).limit(1)).mappings().first()
    trend = 0.0
    if reference and total:
        minutes = (now-clock.as_utc(reference['created_at'])).total_seconds()/60
        trend = (score-reference['score'])/minutes if minutes else 0.0
    count = sum(w > 0 for w in weights)
    return {'level':level, 'label':LEVEL_LABEL[level] if count else 'No recent reports',
            'score':round(score,4), 'confidence':'high' if count >= 7 else 'medium' if count >= 3 else 'low',
            'report_count':count, 'trend_per_min':round(trend,6), 'updated_at':now.isoformat()}


def save_snapshot(conn, status):
    conn.execute(insert(status_snapshots).values(level=status['level'],score=status['score'],report_count=status['report_count']))
