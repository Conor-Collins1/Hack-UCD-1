"""Simple login: name + email, stored in Flask's signed session cookie. OWNER: Person 1."""
from functools import wraps

from flask import jsonify, session
from sqlalchemy import select

from library.db import users


def current_user(conn):
    """Return the logged-in user's row (as a mapping), or None."""
    user_id = session.get('user_id')
    if user_id is None:
        return None
    return conn.execute(select(users).where(users.c.id == user_id)).mappings().first()


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if session.get('user_id') is None:
            return jsonify(error='Log in first.'), 401
        return view(*args, **kwargs)
    return wrapper


def user_json(user):
    """Public shape of a user, used by GET /api/me (see CLAUDE.md)."""
    return {
        'id': user['id'],
        'name': user['name'],
        'email': user['email'],
        'trust_score': round(user['trust_score'], 2),
        'points': user['points'],
        'flagged': user['flagged'],
        'is_premium': user['is_premium'],
        'premium_until': user['premium_until'].isoformat() if user['premium_until'] else None,
        'premium_source': user['premium_source'],
        'ntfy_topic': user['ntfy_topic'],
    }
