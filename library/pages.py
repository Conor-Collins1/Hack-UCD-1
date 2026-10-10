"""HTML pages. OWNER: Person 2. Pages fetch their data from the JSON API with static/app.js."""
from flask import Blueprint, render_template

bp = Blueprint('pages', __name__)


@bp.get('/')
def index():
    return render_template('index.html')


@bp.get('/leaderboard')
def leaderboard():
    return render_template('leaderboard.html')


@bp.get('/premium')
def premium():
    return render_template('premium.html')


@bp.get('/account')
def account():
    return render_template('account.html')
