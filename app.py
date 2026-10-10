"""Flask entry point. OWNER: Person 1. Others: register your blueprint here once, then leave it."""
import os

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, jsonify  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402

from library import core_routes, db, integration_routes, pages, trust  # noqa: E402

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024
app.secret_key = os.environ.get('SECRET_KEY', 'dev-only-change-me')

app.register_blueprint(core_routes.bp)
app.register_blueprint(integration_routes.bp)
app.register_blueprint(pages.bp)


@app.cli.command('init-db')
def init_db():
    """Create missing tables without removing data."""
    db.init_db()
    print('Database initialised.')


@app.cli.command('reset-db')
def reset_db():
    """Drop and recreate every table. Use before a demo run."""
    db.reset_db()
    print('Database reset.')


@app.cli.command('reward-top')
def reward_top():
    """Give the leaderboard's top 3 a free month of premium and reset points."""
    with db.engine.begin() as conn:
        print('Rewarded:', trust.reward_top_users(conn))


@app.get('/health')
def health():
    try:
        with db.engine.connect() as conn:
            conn.execute(select(db.users.c.id).limit(1))
    except SQLAlchemyError:
        app.logger.error('Database readiness check failed; verify connectivity and run init-db.')
        return jsonify(status='unavailable', database='unavailable'), 503
    return jsonify(status='ok', database='connected')


@app.errorhandler(SQLAlchemyError)
def database_error(error):
    app.logger.exception('Database request failed.')
    return jsonify(error='Database unavailable. Please try again later.'), 503
