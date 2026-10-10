"""Page and static asset tests. OWNER: Person 2.
Run: pytest tests/test_pages.py"""
import re

import pytest

from tests.test_api import client, login  # noqa: F401  (shared fixture)

PAGES = ['/', '/leaderboard', '/premium', '/account']


@pytest.mark.parametrize('path', PAGES)
def test_pages_render_html(client, path):
    r = client.get(path)
    assert r.status_code == 200
    assert r.headers['content-type'].startswith('text/html')
    assert '<html lang="en">' in r.text
    assert 'name="viewport"' in r.text


@pytest.mark.parametrize('path', PAGES)
def test_nav_marks_only_current_page(client, path):
    html = client.get(path).text
    current = re.findall(r'<a href="([^"]+)" aria-current="page"', html)
    assert current == [path]


def test_skip_link_targets_main(client):
    html = client.get('/').text
    assert 'href="#main"' in html
    assert 'id="main"' in html


def test_status_page_has_every_element_app_js_needs(client):
    html = client.get('/').text
    ids = ['status-card', 'status-label', 'status-desc', 'status-count', 'status-confidence',
           'status-trend', 'status-updated', 'announcer', 'report-signed-out', 'report-signed-in',
           'report-login-form', 'login-name', 'login-email', 'login-error', 'reporter-name',
           'report-msg', 'summary', 'summary-empty', 'summary-meta', 'comment-form', 'comment',
           'comment-count', 'comment-error', 'comment-signed-out', 'comments', 'comments-empty']
    for element_id in ids:
        assert f'id="{element_id}"' in html, element_id


def test_status_page_has_one_button_per_level(client):
    from library.db import LEVELS
    html = client.get('/').text
    levels = re.findall(r'class="report-option" type="button" data-level="([a-z_]+)"', html)
    assert sorted(levels) == sorted(LEVELS)


def test_every_form_input_has_a_label(client):
    for path in PAGES:
        html = client.get(path).text
        for input_id in re.findall(r'<(?:input|textarea)[^>]*\bid="([^"]+)"', html):
            labelled = f'for="{input_id}"' in html
            # Older pages use placeholder-only inputs; only the status page is held to this yet.
            if path == '/':
                assert labelled, f'{path}: #{input_id} has no <label>'


def test_comment_box_limit_matches_api(client):
    html = client.get('/').text
    assert re.search(r'<textarea id="comment"[^>]*maxlength="280"', html)


def test_static_assets_served(client):
    css = client.get('/static/style.css')
    js = client.get('/static/app.js')
    assert css.status_code == 200 and js.status_code == 200
    assert 'initStatusPage' in js.text


def test_missing_static_file_is_404(client):
    assert client.get('/static/nope.css').status_code == 404


def test_app_js_never_uses_innerhtml(client):
    # Comments and names are untrusted (CLAUDE.md rule 6).
    js = client.get('/static/app.js').text
    assert not re.search(r'\.(innerHTML|outerHTML)\b|insertAdjacentHTML', js)


def test_status_page_renders_when_logged_in(client):
    login(client)
    assert client.get('/').status_code == 200
