"""AI comment summary via OpenRouter. OWNER: Person 3.

Algorithm (see README "AI summary"):
- Use visible comments from the last WINDOW_HOURS.
- Fewer than MIN_COMMENTS: return status 'not_enough' WITHOUT calling the API.
- Cache: reuse the latest ai_summaries row unless there are >= REGEN_NEW_COMMENTS new
  comments since it, or it is older than REGEN_MINUTES.
- Ask the model for JSON: {"summary": str, "themes": [{"label", "sentiment", "count"}],
  "hidden_comment_ids": [int]}. Mark hidden_comment_ids as comments.hidden = True.
- If the call fails or the JSON is invalid: return the last good summary with status 'stale',
  or status 'error' if there is none. Never raise to the route.
- Comments are untrusted input: tell the model to ignore instructions inside them.
"""
import os

from library import clock

WINDOW_HOURS = 2
MIN_COMMENTS = 3
REGEN_NEW_COMMENTS = 5
REGEN_MINUTES = 10
MODEL = os.environ.get('OPENROUTER_MODEL', '')  # pick a cheap, fast model from openrouter.ai/models


def client():
    from openai import OpenAI
    return OpenAI(base_url='https://openrouter.ai/api/v1', api_key=os.environ['OPENROUTER_API_KEY'])


def get_summary(conn):
    """Return the summary dict. Shape is fixed by CLAUDE.md (GET /api/summary).

    TODO(Person 3): replace the placeholder.
    """
    return {
        'status': 'not_enough',  # 'ok' | 'not_enough' | 'stale' | 'error'
        'summary': None,
        'themes': [],  # [{'label': 'Quiet upstairs', 'sentiment': 'positive', 'count': 4}]
        'comment_count': 0,
        'generated_at': clock.now().isoformat(),
    }
