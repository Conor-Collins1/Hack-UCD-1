"""Database tables. OWNER: Person 1.

These tables are part of the contract in CLAUDE.md. If you change a column,
update CLAUDE.md in the same commit and tell the team.
"""
import os
from pathlib import Path

from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Integer, MetaData, String, Table,
                        Text, create_engine)

from library import clock

database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith(('postgres://', 'postgresql://')):
        database_url = 'postgresql+psycopg://' + database_url.split('://', 1)[1]
else:
    Path('instance').mkdir(exist_ok=True)
    database_url = 'sqlite:///instance/library.db'

engine = create_engine(database_url, pool_pre_ping=True)
metadata = MetaData()

# Report levels, used everywhere (API, DB, frontend).
LEVELS = ('not_full', 'busy', 'full')
LEVEL_SCORE = {'not_full': 0.0, 'busy': 0.8, 'full': 1.0}
LEVEL_LABEL = {'not_full': 'Not full', 'busy': '~80% full', 'full': 'Full'}

users = Table(
    'users', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String(60), nullable=False),
    Column('email', String(200), nullable=False, unique=True),
    Column('trust_score', Float, nullable=False, default=0.5),
    Column('reports_total', Integer, nullable=False, default=0),
    Column('reports_agreed', Integer, nullable=False, default=0),
    Column('points', Integer, nullable=False, default=0),
    Column('flagged', Boolean, nullable=False, default=False),
    Column('is_premium', Boolean, nullable=False, default=False),
    Column('premium_until', DateTime(timezone=True)),
    Column('premium_source', String(20)),  # 'stripe' | 'leaderboard'
    Column('stripe_customer_id', String(100)),
    Column('ntfy_topic', String(100)),
    Column('created_at', DateTime(timezone=True), nullable=False, default=clock.now),
)

reports = Table(
    'reports', metadata,
    Column('id', Integer, primary_key=True),
    Column('user_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('level', String(10), nullable=False),  # one of LEVELS
    Column('created_at', DateTime(timezone=True), nullable=False, default=clock.now),
    Column('agreed', Boolean),  # set later by trust.py; NULL = not judged yet
)

comments = Table(
    'comments', metadata,
    Column('id', Integer, primary_key=True),
    Column('user_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('text', String(280), nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False, default=clock.now),
    Column('hidden', Boolean, nullable=False, default=False),  # set by ai.py for spam/abuse
)

status_snapshots = Table(
    'status_snapshots', metadata,
    Column('id', Integer, primary_key=True),
    Column('level', String(10), nullable=False),
    Column('score', Float, nullable=False),
    Column('report_count', Integer, nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False, default=clock.now),
)

notifications_sent = Table(
    'notifications_sent', metadata,
    Column('id', Integer, primary_key=True),
    Column('user_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('kind', String(20), nullable=False),  # 'filling_up' | 'space_opening'
    Column('created_at', DateTime(timezone=True), nullable=False, default=clock.now),
)

payments = Table(
    'payments', metadata,
    Column('id', Integer, primary_key=True),
    Column('user_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('stripe_session_id', String(200), nullable=False, unique=True),
    Column('stripe_subscription_id', String(200)),
    Column('amount', Integer),  # in cents
    Column('currency', String(3)),
    Column('status', String(20), nullable=False),  # 'paid' | ...
    Column('created_at', DateTime(timezone=True), nullable=False, default=clock.now),
)

ai_summaries = Table(
    'ai_summaries', metadata,
    Column('id', Integer, primary_key=True),
    Column('summary_json', Text, nullable=False),  # the JSON returned by GET /api/summary
    Column('comment_count', Integer, nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False, default=clock.now),
)


feedback = Table(
    'feedback', metadata,
    Column('id', Integer, primary_key=True),
    Column('user_id', Integer, ForeignKey('users.id'), nullable=False),
    Column('message', String(2000), nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False, default=clock.now, index=True),
)


def init_db():
    metadata.create_all(engine)


def reset_db():
    metadata.drop_all(engine)
    metadata.create_all(engine)
