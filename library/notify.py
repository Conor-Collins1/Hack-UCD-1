"""Record simulated Premium alert triggers. No delivery service is called."""
from datetime import timedelta
from sqlalchemy import func, insert, or_, select, update
from library import clock
from library.db import notification_events, notification_state, users

MESSAGES = {
    'filling_up': ('The library is getting busy', 'The library has reached ~80% full. Head over soon if you need a seat.'),
    'space_opening': ('Seats may be opening up', 'The library has dropped from Full to ~80% full. It may be a good time to check for a seat.'),
}


def capture_status(conn):
    """Compute and observe under a database lock, in the caller's transaction.

    The first observation is a baseline, never an invented historical transition.
    Missing/stale report windows break the chain so expiry cannot look like freed seats.
    Each real re-entry into busy is recorded, without a cooldown or duplicate polls.
    """
    from library.status import compute_status, WINDOW_MINUTES
    conn.execute(update(notification_state).where(notification_state.c.id == 1).values(id=1))
    state = conn.execute(select(notification_state).where(notification_state.c.id == 1)).mappings().one()
    current = compute_status(conn)
    now = clock.now()
    level = current['level'] if current['report_count'] else None
    previous = state['level']
    observed = clock.as_utc(state['observed_at']) if state['observed_at'] else None
    fresh = observed is not None and now - timedelta(minutes=WINDOW_MINUTES) <= observed <= now
    kind = None
    if fresh and level == 'busy':
        if previous == 'not_full':
            kind = 'filling_up'
        elif previous == 'full':
            kind = 'space_opening'
    if kind:
        eligible = conn.scalar(select(func.count()).select_from(users).where(
            users.c.is_premium.is_(True),
            or_(users.c.premium_until.is_(None), users.c.premium_until > now)))
        conn.execute(insert(notification_events).values(kind=kind, from_level=previous,
            to_level=level, eligible_users=eligible, created_at=now))
    conn.execute(update(notification_state).where(notification_state.c.id == 1).values(level=level, observed_at=now))
    return current


def history(conn, before=0):
    query = select(notification_events)
    if before > 0:
        query = query.where(notification_events.c.id < before)
    rows = conn.execute(query.order_by(notification_events.c.id.desc()).limit(51)).mappings().all()
    events = [{**row, 'created_at': clock.as_utc(row['created_at']).isoformat(),
               'title': MESSAGES[row['kind']][0], 'message': MESSAGES[row['kind']][1],
               'delivery': 'simulated'} for row in rows[:50]]
    return {'notifications': events, 'next_before': events[-1]['id'] if len(rows) > 50 else None}
