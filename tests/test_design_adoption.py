"""Keep main's working features while adopting the frontend branch's design."""
import re
import pytest
from tests.test_api import client


@pytest.mark.parametrize('path', ['/', '/leaderboard', '/premium', '/account', '/feedback'])
def test_pages_keep_shared_shell(client, path):
    html = client.get(path).text
    assert '<meta name="theme-color" content="#fffdfa">' in html
    assert 'href="#main"' in html


def test_status_keeps_main_features_with_new_design(client):
    html = client.get('/').text
    for element_id in ['reporter-score', 'summary', 'summary-empty', 'feedback-form', 'feedback-message', 'cooldown']:
        assert f'id="{element_id}"' in html
    assert 'class="hero"' in html
    assert html.count('class="report-option__check"') == 3
    assert 'class="card card--soft"' in html
    assert '<ul class="summary-bullets body"' in html
    assert 'initFeedbackForm();' in html
    assert 'id="themes"' not in html


def test_bookshelf_uses_current_scoring_and_live_rank(client):
    html = client.get('/leaderboard').text
    for element_id in ['podium', 'leaderboard', 'you-points', 'you-rank', 'you-plan', 'leaderboard-position', 'leaderboard-meta', 'leaderboard-error']:
        assert f'id="{element_id}"' in html
    assert '+5' in html and '+2' in html
    assert 'free month of Premium' in html
    assert 'Equal scores share a rank' in html
    assert 'end of the month' not in html
    assert 'preview' not in html


def test_permanent_payment_and_private_inbox_remain(client):
    premium = client.get('/premium').text
    assert '€1.99 once' in premium and 'permanently' in premium
    account = client.get('/account').text
    assert 'ntfy-form' not in account
    assert 'feedback-password' in client.get('/feedback').text
    assert client.get('/api/feedback').status_code == 401


def test_photo_and_frontend_safety(client):
    image = client.get('/static/img/library.jpg')
    assert image.status_code == 200
    assert image.headers['content-type'] == 'image/jpeg'
    assert len(image.content) < 400000
    js = client.get('/static/app.js').text
    assert not re.search(r'\.(innerHTML|outerHTML)\b|insertAdjacentHTML', js)
    assert 'SAMPLE_LEADERBOARD' not in js
    assert 'renderResetDate' not in js
    assert '/api/checkout/confirm' in js
    assert '/api/feedback/access' in js
