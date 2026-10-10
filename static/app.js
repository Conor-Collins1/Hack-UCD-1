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

// Restart the cooldown bar's CSS animation so it shrinks over the remaining wait.
function showCooldownBar(seconds) {
  const track = $('cooldown');
  if (!track) return;
  track.hidden = seconds <= 0;
  if (seconds <= 0) return;
  const bar = track.firstElementChild;
  bar.style.setProperty('--duration', `${seconds}s`);
  bar.style.animation = 'none';
  void bar.offsetWidth; // reflow so the animation starts again
  bar.style.animation = '';
}

// Shake the options once when a report is rejected. Reduced-motion users get the message only.
function shakeOptions() {
  const group = document.querySelector('.report-options');
  group.classList.remove('is-shaking');
  void group.offsetWidth;
  group.classList.add('is-shaking');
  group.addEventListener('animationend', () => group.classList.remove('is-shaking'), { once: true });
}

function startCooldown(seconds, message, tone) {
  clearInterval(statusPage.cooldownTimer);
  const notice = $('report-msg');
  let left = Math.max(0, Math.ceil(seconds || 0));
  showCooldownBar(left);
  const tick = () => {
    if (left <= 0) {
      clearInterval(statusPage.cooldownTimer);
      reportButtons().forEach(b => { b.disabled = false; b.classList.remove('is-sent', 'is-sending'); });
      $('cooldown').hidden = true;
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
      reportButtons().forEach(b => { b.disabled = true; b.classList.remove('is-sent', 'is-sending'); });
      button.classList.add('is-sending');
      showNotice(notice, 'Sending your report…', 'info');
      try {
        const data = await api('/api/reports', { method: 'POST', body: { level: button.dataset.level } });
        renderStatus(data.status);
        button.classList.replace('is-sending', 'is-sent');
        announce('Thanks, your report is in.');
        const me = await api('/api/me').catch(() => ({ seconds_until_can_report: 0 }));
        startCooldown(me.seconds_until_can_report, 'Thanks, your report is in.', 'success');
      } catch (e) {
        button.classList.remove('is-sending');
        shakeOptions();
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

// Shown only with ?preview=1, and labelled on the page, so the design can be reviewed
// before scoring is live. Never mixed with real data.
const SAMPLE_LEADERBOARD = [
  ['Aoife', 42, 31], ['Cian', 37, 28], ['Niamh', 29, 25], ['Oisín', 21, 19], ['Saoirse', 17, 15],
  ['Darragh', 12, 11], ['Róisín', 9, 10], ['Conor', 6, 7], ['Méabh', 4, 5], ['Tadhg', 2, 3],
].map(([name, points, reports_total], i) => ({ rank: i + 1, name, points, reports_total }));

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function plural(n, word) { return `${n} ${word}${n === 1 ? '' : 's'}`; }

function renderResetDate() {
  const now = new Date();
  const end = new Date(now.getFullYear(), now.getMonth() + 1, 0);
  const days = Math.max(0, Math.round((end - new Date(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000));
  $('lb-period').textContent = now.toLocaleDateString('en-IE', { month: 'long', year: 'numeric' });
  const date = end.toLocaleDateString('en-IE', { day: 'numeric', month: 'long' });
  $('lb-reset').textContent = days === 0 ? `Winners are picked tonight (${date}).` : `Winners picked on ${date}, ${plural(days, 'day')} to go.`;
}

function renderPodium(top) {
  const podium = $('podium');
  podium.replaceChildren(...[1, 2, 3].map(rank => {
    const row = top.find(r => r.rank === rank);
    const li = el('li', row ? 'spine' : 'spine spine--open');
    li.dataset.rank = String(rank);
    li.append(el('span', 'spine__rank', String(rank)));
    if (row) {
      li.append(el('span', 'spine__name', row.name));
      const pts = el('span', 'spine__points');
      pts.append(el('strong', '', String(row.points)), document.createTextNode(row.points === 1 ? 'point' : 'points'));
      li.append(pts, el('span', 'spine__badge', 'Wins Premium'));
    } else {
      li.append(el('span', 'spine__name', 'Open spot'), el('span', 'spine__points', 'Could be you'));
    }
    return li;
  }));
}

function renderCatalogue(rest, leaderPoints) {
  listItems($('leaderboard'), rest, (li, row) => {
    const who = el('span', 'catalogue__who');
    who.append(el('span', 'catalogue__name', row.name), el('span', 'catalogue__meta', plural(row.reports_total, 'report')));
    const bar = el('span', 'catalogue__bar');
    const fill = el('span');
    fill.style.width = `${leaderPoints ? Math.max(4, Math.round(row.points / leaderPoints * 100)) : 0}%`;
    bar.append(fill);
    bar.setAttribute('aria-hidden', 'true');
    who.append(bar);
    const pts = el('span', 'catalogue__points', String(row.points));
    pts.append(el('small', '', row.points === 1 ? 'point' : 'points'));
    const rank = el('span', 'catalogue__rank', String(row.rank));
    rank.setAttribute('aria-hidden', 'true');   // the <ol> already announces the position
    li.append(rank, who, pts);
  });
}

async function renderYou() {
  try {
    const { user } = await api('/api/me');
    $('you-signed-in').hidden = false;
    $('you-points').textContent = String(user.points);
    $('you-trust').textContent = `${Math.round(user.trust_score * 100)}%`;
    $('you-plan').textContent = user.is_premium ? 'Premium' : 'Free';
  } catch (e) {
    $('you-signed-out').hidden = false;
  }
}

async function initLeaderboardPage() {
  renderResetDate();
  renderYou();
  const preview = new URLSearchParams(location.search).get('preview') === '1';
  let rows = [];
  try {
    rows = preview ? SAMPLE_LEADERBOARD : (await api('/api/leaderboard')).leaderboard;
  } catch (e) {
    renderPodium([]);
    $('podium-empty').textContent = `${e.message} The leaderboard will try again when you reload.`;
    $('podium-empty').hidden = false;
    $('rest-empty').textContent = "Couldn't load the leaderboard.";
    $('rest-empty').hidden = false;
    return;
  }
  $('lb-preview').hidden = !preview;
  renderPodium(rows.slice(0, 3));
  if (!rows.length) {
    $('podium-empty').textContent = 'No points yet this month. Reports earn points once they are checked against other students\' reports, about 15 minutes later.';
    $('podium-empty').hidden = false;
  }
  const rest = rows.slice(3);
  renderCatalogue(rest, rows.length ? rows[0].points : 0);
  $('rest-empty').textContent = rows.length > 3 ? '' : 'Places 4 to 10 will show up here as more students earn points.';
  $('rest-empty').hidden = rest.length > 0;
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
    $('ntfy').value = user.ntfy_topic || '';
  };
  try { show((await api('/api/me')).user); } catch { /* not logged in */ }

  $('login-form').addEventListener('submit', async event => {
    event.preventDefault();
    try {
      show((await api('/api/login', { method: 'POST', body: { name: $('name').value, email: $('email').value } })).user);
    } catch (e) { $('login-msg').textContent = e.message; }
  });
  $('ntfy-form').addEventListener('submit', async event => {
    event.preventDefault();
    try {
      await api('/api/me/ntfy', { method: 'POST', body: { topic: $('ntfy').value } });
      $('ntfy-msg').textContent = 'Saved.';
    } catch (e) { $('ntfy-msg').textContent = e.message; }
  });
  $('logout').addEventListener('click', async () => { await api('/api/logout', { method: 'POST' }); location.reload(); });
}
