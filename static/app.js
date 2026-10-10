// Frontend logic. OWNER: Person 2. API shapes are in CLAUDE.md.
// User text is always inserted with textContent, never innerHTML.

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || 'Something went wrong. Please try again.');
    error.status = response.status;
    error.data = data;
    throw error;
  }
  return data;
}

function $(id) { return document.getElementById(id); }

function listItems(list, items, render) {
  list.replaceChildren(...items.map(item => {
    const li = document.createElement('li');
    render(li, item);
    return li;
  }));
}

// ---- Shared helpers ----

const relative = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });

function timeAgo(iso) {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (!Number.isFinite(seconds) || seconds < 45) return 'just now';
  if (seconds < 3600) return relative.format(-Math.round(seconds / 60), 'minute');
  if (seconds < 86400) return relative.format(-Math.round(seconds / 3600), 'hour');
  return relative.format(-Math.round(seconds / 86400), 'day');
}

function clockTime(totalSeconds) {
  const m = Math.floor(totalSeconds / 60);
  const s = String(totalSeconds % 60).padStart(2, '0');
  return `${m}:${s}`;
}

// Screen-reader announcement for events (status changes, report sent), so live
// regions don't re-read the page on every poll or countdown tick.
function announce(text) {
  const region = $('announcer');
  if (!region) return;
  region.textContent = '';
  setTimeout(() => { region.textContent = text; }, 50);
}

function showNotice(el, text, tone) {
  el.hidden = !text;
  el.textContent = text || '';
  if (tone) el.dataset.tone = tone; else delete el.dataset.tone;
}

// ---- Status page ----

const LEVEL_DESC = {
  not_full: 'Easy to find a seat right now.',
  busy: 'Seats are getting hard to find.',
  full: 'Expect to search for a seat or wait.',
};

const statusPage = { user: null, lastLevel: null, updatedAt: null, cooldownTimer: null };

function trendText(perMin, count) {
  if (!count) return '–';
  if (perMin > 0.003) return 'Filling up';
  if (perMin < -0.003) return 'Emptying';
  return 'Steady';
}

function renderStatus(s) {
  const card = $('status-card');
  const known = s.report_count > 0;
  const level = known ? s.level : 'unknown';
  card.dataset.level = level;
  card.setAttribute('aria-busy', 'false');
  $('status-label').textContent = s.label;
  $('status-desc').textContent = known
    ? LEVEL_DESC[s.level]
    : 'Nobody has reported in the last 45 minutes. Be the first.';
  card.querySelectorAll('.scale li').forEach(li => {
    li.setAttribute('aria-current', String(known && li.dataset.step === s.level));
  });
  $('status-count').textContent = String(s.report_count);
  $('status-confidence').textContent = known ? s.confidence[0].toUpperCase() + s.confidence.slice(1) : '–';
  $('status-trend').textContent = trendText(s.trend_per_min, s.report_count);
  statusPage.updatedAt = s.updated_at;
  renderUpdated();
  if (statusPage.lastLevel && statusPage.lastLevel !== level) announce(`Status changed: ${s.label}.`);
  statusPage.lastLevel = level;
}

function renderUpdated() {
  if (statusPage.updatedAt) $('status-updated').textContent = `Updated ${timeAgo(statusPage.updatedAt)}`;
}

async function refreshStatus() {
  try {
    renderStatus(await api('/api/status'));
  } catch (e) {
    $('status-card').setAttribute('aria-busy', 'false');
    if (!statusPage.lastLevel) $('status-label').textContent = 'Unavailable';
    $('status-desc').textContent = "Couldn't load the latest status. Retrying automatically.";
  }
}

async function refreshSummary() {
  const text = $('summary');
  const meta = $('summary-meta');
  try {
    const s = await api('/api/summary');
    const hasSummary = (s.status === 'ok' || s.status === 'stale') && s.summary;
    if (hasSummary) {
      text.textContent = s.summary;
      const stale = s.status === 'stale' ? ' May be out of date.' : '';
      meta.textContent = `From ${s.comment_count} comments · ${timeAgo(s.generated_at)}. AI can make mistakes.${stale}`;
    } else {
      text.textContent = s.status === 'not_enough'
        ? 'Not enough recent comments to summarise yet. A summary appears once a few more people comment.'
        : 'The summary is unavailable right now.';
      meta.textContent = '';
    }
    listItems($('themes'), hasSummary ? s.themes : [], (li, t) => {
      li.dataset.sentiment = t.sentiment;
      li.setAttribute('aria-label', `${t.label}: ${t.count} mentions, ${t.sentiment}`);
      li.append(document.createTextNode(t.label));
      const count = document.createElement('span');
      count.className = 'chip__count';
      count.textContent = String(t.count);
      li.append(count);
    });
  } catch (e) {
    text.textContent = 'The summary is unavailable right now.';
    meta.textContent = '';
  }
}

async function refreshComments() {
  const empty = $('comments-empty');
  try {
    const data = await api('/api/comments');
    listItems($('comments'), data.comments, (li, c) => {
      const meta = document.createElement('div');
      meta.className = 'comment__meta';
      const name = document.createElement('span');
      name.className = 'comment__name';
      name.textContent = c.name;
      const time = document.createElement('time');
      time.dateTime = c.created_at;
      time.textContent = timeAgo(c.created_at);
      meta.append(name, time);
      const body = document.createElement('p');
      body.className = 'comment__text';
      body.textContent = c.text;
      li.append(meta, body);
    });
    empty.textContent = "No comments yet. Say what you're seeing.";
    empty.hidden = data.comments.length > 0;
  } catch (e) {
    empty.textContent = "Couldn't load comments. Retrying automatically.";
    empty.hidden = false;
  }
}

function setSignedIn(user) {
  statusPage.user = user;
  $('report-signed-out').hidden = !!user;
  $('report-signed-in').hidden = !user;
  $('comment-form').hidden = !user;
  $('comment-signed-out').hidden = !!user;
  if (user) $('reporter-name').textContent = user.name;
}

function reportButtons() { return document.querySelectorAll('.report-option'); }

function startCooldown(seconds, message, tone) {
  clearInterval(statusPage.cooldownTimer);
  const notice = $('report-msg');
  let left = Math.max(0, Math.ceil(seconds || 0));
  const tick = () => {
    if (left <= 0) {
      clearInterval(statusPage.cooldownTimer);
      reportButtons().forEach(b => { b.disabled = false; b.removeAttribute('aria-pressed'); });
      if (message) showNotice(notice, `${message} You can report again now.`, tone);
      return;
    }
    reportButtons().forEach(b => { b.disabled = true; });
    showNotice(notice, `${message ? message + ' ' : ''}You can report again in ${clockTime(left)}.`, tone);
    left -= 1;
  };
  tick();
  if (left > 0) statusPage.cooldownTimer = setInterval(tick, 1000);
}

async function loadSession() {
  try {
    const me = await api('/api/me');
    setSignedIn(me.user);
    if (me.seconds_until_can_report > 0) startCooldown(me.seconds_until_can_report, 'You reported recently.', 'info');
    return me;
  } catch (e) {
    setSignedIn(null);
    return null;
  }
}

function fieldError(input, errorEl, message) {
  input.setAttribute('aria-invalid', 'true');
  errorEl.textContent = message;
  input.focus();
}

function clearErrors(form, errorEl) {
  form.querySelectorAll('[aria-invalid]').forEach(el => el.removeAttribute('aria-invalid'));
  errorEl.textContent = '';
}

function initStatusPage() {
  // Sign in inline: reporting is the main task, so don't send people to another page.
  const loginForm = $('report-login-form');
  loginForm.addEventListener('submit', async event => {
    event.preventDefault();
    const name = $('login-name');
    const email = $('login-email');
    const error = $('login-error');
    clearErrors(loginForm, error);
    if (!name.value.trim()) return fieldError(name, error, 'Enter your first name.');
    if (!/^\S+@\S+\.\S+$/.test(email.value.trim())) return fieldError(email, error, 'Enter a valid email, like name@ucdconnect.ie.');
    const submit = loginForm.querySelector('button');
    submit.disabled = true;
    try {
      await api('/api/login', { method: 'POST', body: { name: name.value.trim(), email: email.value.trim() } });
      await loadSession();
      announce('Signed in. You can now report.');
      const first = document.querySelector('.report-option:not(:disabled)');
      if (first) first.focus();
    } catch (e) {
      error.textContent = e.message;
    } finally {
      submit.disabled = false;
    }
  });

  reportButtons().forEach(button => {
    button.addEventListener('click', async () => {
      const notice = $('report-msg');
      reportButtons().forEach(b => { b.disabled = true; b.removeAttribute('aria-pressed'); });
      button.setAttribute('aria-pressed', 'true');
      showNotice(notice, 'Sending your report…', 'info');
      try {
        const data = await api('/api/reports', { method: 'POST', body: { level: button.dataset.level } });
        renderStatus(data.status);
        announce('Thanks, your report is in.');
        const me = await api('/api/me').catch(() => ({ seconds_until_can_report: 0 }));
        startCooldown(me.seconds_until_can_report, 'Thanks, your report is in.', 'success');
      } catch (e) {
        button.removeAttribute('aria-pressed');
        if (e.status === 429) {
          startCooldown(e.data.retry_after_seconds, 'You reported recently.', 'warning');
        } else if (e.status === 401) {
          setSignedIn(null);
          showNotice(notice, 'Your session ended. Sign in again to report.', 'warning');
          $('login-name').focus();
        } else {
          reportButtons().forEach(b => { b.disabled = false; });
          showNotice(notice, e.message, 'error');
        }
      }
    });
  });

  const comment = $('comment');
  const counter = $('comment-count');
  const updateCounter = () => {
    counter.textContent = `${comment.value.length}/280`;
    counter.dataset.over = String(comment.value.length > 280);
  };
  comment.addEventListener('input', updateCounter);

  const commentForm = $('comment-form');
  commentForm.addEventListener('submit', async event => {
    event.preventDefault();
    const error = $('comment-error');
    clearErrors(commentForm, error);
    const text = comment.value.trim();
    if (!text) return fieldError(comment, error, 'Write a comment first.');
    if (text.length > 280) return fieldError(comment, error, 'Keep it under 280 characters.');
    const submit = commentForm.querySelector('button');
    submit.disabled = true;
    try {
      await api('/api/comments', { method: 'POST', body: { text } });
      commentForm.reset();
      updateCounter();
      announce('Comment posted.');
      refreshComments();
    } catch (e) {
      if (e.status === 401) setSignedIn(null);
      error.textContent = e.status === 401 ? 'Your session ended. Sign in again to comment.' : e.message;
    } finally {
      submit.disabled = false;
    }
  });

  loadSession();
  refreshStatus(); refreshSummary(); refreshComments();

  // Poll only while the tab is visible; catch up immediately when it comes back.
  const visible = () => document.visibilityState === 'visible';
  setInterval(() => { if (visible()) refreshStatus(); }, 10000);
  setInterval(() => { if (visible()) { refreshSummary(); refreshComments(); } }, 30000);
  setInterval(renderUpdated, 15000);
  document.addEventListener('visibilitychange', () => {
    if (visible()) { refreshStatus(); refreshSummary(); refreshComments(); }
  });
}

// ---- Leaderboard page ----

async function initLeaderboardPage() {
  try {
    const data = await api('/api/leaderboard');
    if (!data.leaderboard.length) { $('leaderboard').textContent = 'Leaderboard scoring is not implemented yet.'; return; }
    listItems($('leaderboard'), data.leaderboard, (li, row) => { li.textContent = `${row.name} · ${row.points} pts`; });
  } catch (e) { $('leaderboard').textContent = e.message; }
}

// ---- Premium page ----

function initPremiumPage() {
  $('subscribe').addEventListener('click', async () => {
    $('premium-msg').textContent = 'Opening checkout…';
    try {
      const data = await api('/api/checkout', { method: 'POST' });
      window.location = data.url;
    } catch (e) {
      $('premium-msg').textContent = e.status === 401 ? 'Log in on the Account page first.' : e.message;
    }
  });
}

// ---- Account page ----

async function initAccountPage() {
  const show = user => {
    $('login-card').hidden = true;
    $('account-card').hidden = false;
    $('account-name').textContent = user.name;
    $('account-details').textContent =
      `${user.points} points · trust ${user.trust_score} · ${user.is_premium ? 'Premium' : 'Free plan'}`;
  };
  try { show((await api('/api/me')).user); } catch { /* not logged in */ }

  $('login-form').addEventListener('submit', async event => {
    event.preventDefault();
    try {
      show((await api('/api/login', { method: 'POST', body: { name: $('name').value, email: $('email').value } })).user);
    } catch (e) { $('login-msg').textContent = e.message; }
  });
  $('logout').addEventListener('click', async () => { await api('/api/logout', { method: 'POST' }); location.reload(); });
}
