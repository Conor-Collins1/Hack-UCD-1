"""Turn recent, trusted reports into occupancy estimates. OWNER: Person 1."""
from collections import Counter
from datetime import timedelta
from sqlalchemy import insert, select
from library import clock
from library.db import LEVEL_LABEL, LEVEL_SCORE, reports, status_snapshots, users

WINDOW_MINUTES = 45
HALF_LIFE_MINUTES = 3
FRESH_MINUTES = 5
MIN_FRESH_REPORTERS = 3
MAX_FRESH_REPORTS = 5
FULL_ENTER = 0.9
FULL_EXIT = 0.8


def select_current_reports(rows):
    """Drop superseded votes and retain the latest established fresh-report cutoff.

    Reconstruct the latest qualifying five-minute group from stored report timestamps.
    This keeps rejected older votes out even after that group ages beyond five minutes;
    otherwise the status could jump backwards with no new reports. No database deletion.
    Rows arrive newest-first with id breaking timestamp ties deterministically.
    """
    latest = {}
    for row in rows:
        latest.setdefault(row['user_id'], row)
    chronological = list(reversed(rows))
    counts = Counter()
    left = 0
    group = None
    for right, row in enumerate(chronological):
        counts[row['user_id']] += 1
        cutoff = clock.as_utc(row['created_at']) - timedelta(minutes=FRESH_MINUTES)
        while clock.as_utc(chronological[left]['created_at']) < cutoff:
            identity = chronological[left]['user_id']
            counts[identity] -= 1
            if not counts[identity]:
                del counts[identity]
            left += 1
        if len(counts) >= MIN_FRESH_REPORTERS:
            group = (left, right)
    selected = list(latest.values())
    if group is not None:
        # Latest five distinct reporters in the newest qualifying group establish the cutoff.
        votes = {}
        for row in reversed(chronological[group[0]:group[1] + 1]):
            votes.setdefault(row['user_id'], row)
            if len(votes) == MAX_FRESH_REPORTS:
                break
        cutoff = min(clock.as_utc(row['created_at']) for row in votes.values())
        selected = [row for row in selected if clock.as_utc(row['created_at']) >= cutoff][:MAX_FRESH_REPORTS]
    return selected


def compute_status(conn):
    now = clock.now()
    rows = conn.execute(
        select(reports.c.id, reports.c.user_id, reports.c.level, reports.c.created_at, users.c.trust_score)
        .join(users, users.c.id == reports.c.user_id)
        .where(reports.c.created_at >= now - timedelta(minutes=WINDOW_MINUTES),
               reports.c.created_at <= now, users.c.flagged.is_(False), users.c.trust_score > 0)
        .order_by(reports.c.created_at.desc(), reports.c.id.desc())
    ).mappings().all()
    rows = select_current_reports(rows)
    fresh_consensus = sum(clock.as_utc(row['created_at']) >= now - timedelta(minutes=FRESH_MINUTES)
                          for row in rows) >= MIN_FRESH_REPORTERS
    weights = [0.5 ** ((now-clock.as_utc(r['created_at'])).total_seconds()/60/HALF_LIFE_MINUTES) * r['trust_score'] for r in rows]
    total = sum(weights)
    score = sum(LEVEL_SCORE[r['level']]*w for r,w in zip(rows,weights))/total if total else 0.0
    previous = conn.execute(select(status_snapshots).where(status_snapshots.c.created_at <= now)
                            .order_by(status_snapshots.c.created_at.desc(), status_snapshots.c.id.desc()).limit(1)).mappings().first()
    # Sparse updates retain hysteresis; a fresh group can replace the previous state immediately.
    was_full = not fresh_consensus and previous and previous['level'] == 'full' and clock.as_utc(previous['created_at']) >= now-timedelta(minutes=WINDOW_MINUTES)
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
            'score':round(score,4), 'confidence':'high' if fresh_consensus and count >= 5 else 'medium' if fresh_consensus else 'low',
            'report_count':count, 'trend_per_min':round(trend,6), 'updated_at':now.isoformat()}


def save_snapshot(conn, status):
    conn.execute(insert(status_snapshots).values(level=status['level'],score=status['score'],report_count=status['report_count']))
