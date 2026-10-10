"""Bad-actor detection and leaderboard points. OWNER: Person 1.

Algorithm (see README "Bad-actor detection" and "Leaderboard"):
- A report is judged once it is JUDGE_AFTER_MINUTES old: compare it with the consensus
  of OTHER users' reports around that time. Set reports.agreed.
- trust_score = (reports_agreed + 1) / (reports_total + 2)
- flagged = True if trust_score < FLAG_TRUST after >= FLAG_MIN_REPORTS judged reports.
- Points: +1 for an agreed report, +3 for being first to report a change that others
  later confirmed. Flagged users get no points.
"""
from datetime import timedelta

from sqlalchemy import select

from library import clock
from library.db import reports

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
    return max(0, int(remaining))


def judge_pending_reports(conn):
    """Judge every unjudged report older than JUDGE_AFTER_MINUTES; update trust, flags, points.

    TODO(Person 1)
    """


def leaderboard(conn, limit=10):
    """Return the leaderboard list. Shape is fixed by CLAUDE.md (GET /api/leaderboard).

    TODO(Person 1): query users ordered by points desc, excluding flagged users.
    """
    return []


def reward_top_users(conn):
    """Give the top TOP_N_REWARD users a free month: payments.grant_premium(conn, user_id, 30, 'leaderboard').
    Then reset everyone's points to 0. Run by `python -m library.cli reward-top`.

    TODO(Person 1)
    """
    return []
