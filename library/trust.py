"""Bad-actor detection and leaderboard points. OWNER: Person 1.

Algorithm (see README "Bad-actor detection" and "Leaderboard"):
- A report is judged once it is JUDGE_AFTER_MINUTES old: compare it with the consensus
  of OTHER users' reports around that time. Set reports.agreed.
- trust_score = (reports_agreed + 1) / (reports_total + 2)
- flagged = True if trust_score < FLAG_TRUST after >= FLAG_MIN_REPORTS judged reports.
- Participation points: +5 per accepted report and +2 per accepted comment.
  Failed/cooldown/duplicate submissions earn nothing. Flagged users get no points.
  Trust judgement does not award extra points; historical content is not backfilled.
"""
from datetime import timedelta
from math import ceil

from sqlalchemy import func, select, update

from library import clock
from library.db import comments, reports, users

JUDGE_AFTER_MINUTES = 15
FLAG_TRUST = 0.3
FLAG_MIN_REPORTS = 5
REPORT_COOLDOWN_MINUTES = 10
TOP_N_REWARD = 3
REWARD_DAYS = 30


def seconds_until_can_report(conn, user_id):
    """0 if the user may report now, otherwise seconds (real time) left on the cooldown."""
    last = conn.execute(
        select(reports.c.created_at).where(reports.c.user_id == user_id)
        .order_by(reports.c.created_at.desc()).limit(1)
    ).scalar()
    if last is None:
        return 0
    ready_at = clock.as_utc(last) + timedelta(minutes=REPORT_COOLDOWN_MINUTES)
    remaining = (ready_at - clock.now()).total_seconds() / clock.speed()
    return max(0, ceil(remaining))


def judge_pending_reports(conn):
    """Judge every unjudged report older than JUDGE_AFTER_MINUTES; update trust, flags, points.

    TODO(Person 1)
    """


REPORT_POINTS = 5
COMMENT_POINTS = 2
COMMENT_COOLDOWN_SECONDS = 60


def lock_user(conn, user_id):
    """Serialize submissions per user on both PostgreSQL and SQLite."""
    conn.execute(update(users).where(users.c.id == user_id).values(points=users.c.points))


def award_points(conn, user_id, amount):
    """Award in the same transaction as the accepted contribution. Flagged users earn zero."""
    result = conn.execute(update(users).where(users.c.id == user_id, users.c.flagged.is_(False))
                          .values(points=users.c.points + amount))
    return amount if result.rowcount else 0


def seconds_until_can_comment(conn, user_id):
    last = conn.execute(select(func.max(comments.c.created_at)).where(comments.c.user_id == user_id)).scalar()
    if last is None:
        return 0
    remaining = (clock.as_utc(last) + timedelta(seconds=COMMENT_COOLDOWN_SECONDS) - clock.now()).total_seconds()
    return max(0, ceil(remaining / clock.speed()))


def rank_for_user(conn, user_id):
    user = conn.execute(select(users.c.points, users.c.flagged).where(users.c.id == user_id)).mappings().first()
    if not user or user['flagged'] or user['points'] <= 0:
        return None
    above = conn.execute(select(func.count()).select_from(users).where(
        users.c.flagged.is_(False), users.c.points > user['points'])).scalar_one()
    return above + 1


def leaderboard(conn, limit=10):
    """Top contributors with competition ranks: equal scores share rank (1, 1, 3)."""
    counts = select(reports.c.user_id, func.count().label('total')).group_by(reports.c.user_id).subquery()
    query = select(users.c.id, users.c.name, users.c.points,
                   func.coalesce(counts.c.total, 0).label('reports_total'),
                   func.rank().over(order_by=users.c.points.desc()).label('rank')).outerjoin(
                       counts, counts.c.user_id == users.c.id).where(
                           users.c.flagged.is_(False), users.c.points > 0).order_by(
                               users.c.points.desc(), users.c.id).limit(limit)
    return [dict(row) for row in conn.execute(query).mappings()]


def reward_top_users(conn):
    """Give the top TOP_N_REWARD users a free month: payments.grant_premium(conn, user_id, 30, 'leaderboard').
    Then reset everyone's points to 0. Run by `python -m library.cli reward-top`.

    TODO(Person 1)
    """
    return []
