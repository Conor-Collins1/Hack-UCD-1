"""Name/email demo login with a signed Starlette session. OWNER: Person 1.
This does not verify email ownership; use synthetic identities until verified login is added.
"""
from fastapi import HTTPException, Request
from sqlalchemy import select
from library.db import engine, users


def current_user(conn, request):
    identity = request.session.get('user_id')
    if identity is None:
        return None
    return conn.execute(select(users).where(users.c.id == identity)).mappings().first()


def require_user(request: Request):
    with engine.connect() as conn:
        user = current_user(conn, request)
    if user is None:
        request.session.clear()
        raise HTTPException(401, 'Log in first.')
    return user['id']


def user_json(user, conn=None):
    """Public shape of a user, used by GET /api/me (see CLAUDE.md)."""
    from library.trust import rank_for_user
    return {
        'rank': rank_for_user(conn, user['id']) if conn is not None else None,
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
