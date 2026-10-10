"""Premium alerts via ntfy.sh. OWNER: Person 3.

Called by core_routes.py after every new report, with the status before and after.
- 'filling_up': new status not full, and score + trend_per_min * LOOKAHEAD_MINUTES >= 0.9.
- 'space_opening': previous level was 'full' and the new level is 'busy' or 'not_full'.
- Send each kind to each premium user (with an ntfy_topic) at most once per COOLDOWN_MINUTES;
  record every send in notifications_sent.
- Never raise: a failed send must not break report submission. Log and carry on.
"""
import os

NTFY_SERVER = os.environ.get('NTFY_SERVER', 'https://ntfy.sh')
LOOKAHEAD_MINUTES = 15
COOLDOWN_MINUTES = 60


def check_and_send(conn, previous_status, new_status):
    """Decide whether to alert, and send. Return a list of kinds sent (for logs/tests).

    TODO(Person 3)
    """
    return []


def send(topic, title, message):
    """POST one alert to ntfy. TODO(Person 3): requests.post(f'{NTFY_SERVER}/{topic}', ...)"""
