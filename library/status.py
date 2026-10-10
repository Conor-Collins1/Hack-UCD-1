"""Turns recent reports into the library's status. OWNER: Person 1.

Algorithm (see README "Status calculation"):
- Reports from the last WINDOW_MINUTES count.
- Each report's weight = 0.5 ** (age_minutes / HALF_LIFE_MINUTES) * reporter's trust_score
  (flagged users count for 0).
- score = weighted average of LEVEL_SCORE values.
- Hysteresis: become 'full' when score > 0.9; leave 'full' only when score < 0.8.
  Use the latest status_snapshots row as the previous level.
- confidence: 'low' (<3 reports), 'medium' (3-6), 'high' (7+).
"""
from library import clock
from library.db import LEVEL_LABEL

WINDOW_MINUTES = 45
HALF_LIFE_MINUTES = 15
FULL_ENTER = 0.9
FULL_EXIT = 0.8


def compute_status(conn):
    """Return the current status dict. Shape is fixed by CLAUDE.md (GET /api/status).

    TODO(Person 1): replace the placeholder with the real calculation.
    """
    level = 'not_full'
    return {
        'level': level,
        'label': LEVEL_LABEL[level],
        'score': 0.0,
        'confidence': 'low',
        'report_count': 0,
        'trend_per_min': 0.0,  # change in score per minute over the last ~20 min; used by notify.py
        'updated_at': clock.now().isoformat(),
    }


def save_snapshot(conn, status):
    """Insert a status_snapshots row. Call after each new report.

    TODO(Person 1): insert into status_snapshots.
    """
