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
  const list = $('summary');
  const empty = $('summary-empty');
  const meta = $('summary-meta');
  try {
    const s = await api('/api/summary');
    const hasSummary = (s.status === 'ok' || s.status === 'stale') && Array.isArray(s.summary) && s.summary.length > 0;
    listItems(list, hasSummary ? s.summary : [], (li, point) => { li.textContent = point; });
    list.hidden = !hasSummary;
    empty.hidden = !!hasSummary;
    if (hasSummary) {
      const stale = s.status === 'stale' ? ' May be out of date.' : '';
      meta.textContent = `From ${s.comment_count} comments in the past hour · ${timeAgo(s.generated_at)}. AI can make mistakes.${stale}`;
    } else {
      empty.textContent = s.status === 'not_enough'
        ? 'Not enough comments in the past hour. Add a few more updates to see the key points.'
        : 'The summary is unavailable right now.';
      meta.textContent = '';
    }
  } catch (e) {
    list.replaceChildren();
    list.hidden = true;
    empty.hidden = false;
    empty.textContent = 'The summary is unavailable right now.';
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
  if (user) { $('reporter-name').textContent = user.name; $('reporter-score').textContent = scoreText(user); }
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
      reportButtons().forEach(b => { b.disabled = false; b.removeAttribute('aria-pressed'); b.classList.remove('is-sent', 'is-sending'); });
      showCooldownBar(0);
      if (message) showNotice(notice, `${message} You can report again now.`, tone);
      return;
    }
    reportButtons().forEach(b => { b.disabled = true; });
    showNotice(notice, `${message ? message + ' ' : ''}You can report again in ${clockTime(left)}.`, tone);
    left -= 1;
  };
  tick();
  if (seconds > 0) statusPage.cooldownTimer = setInterval(tick, 1000);
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
      reportButtons().forEach(b => { b.disabled = true; b.removeAttribute('aria-pressed'); b.classList.remove('is-sent', 'is-sending'); });
      button.classList.add('is-sending');
      button.setAttribute('aria-pressed', 'true');
      showNotice(notice, 'Sending your report…', 'info');
      try {
        const data = await api('/api/reports', { method: 'POST', body: { level: button.dataset.level } });
        renderStatus(data.status);
        button.classList.replace('is-sending', 'is-sent');
        announce('Thanks, your report is in.');
        const me = await api('/api/me').catch(() => ({ seconds_until_can_report: 0 }));
        if (me.user) setSignedIn(me.user);
        startCooldown(me.seconds_until_can_report, `Thanks, your report is in. +${data.points_awarded || 0} points.`, 'success');
      } catch (e) {
        button.removeAttribute('aria-pressed');
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
      const result = await api('/api/comments', { method: 'POST', body: { text } });
      commentForm.reset();
      updateCounter();
      announce(`Comment posted. +${result.points_awarded || 0} points.`);
      const me = await api('/api/me').catch(() => null);
      if (me) setSignedIn(me.user);
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
  setInterval(() => {
    if (visible()) {
      refreshStatus();
      if (statusPage.user) api('/api/me').then(me => setSignedIn(me.user)).catch(e => { if (e.status === 401) setSignedIn(null); });
    }
  }, 10000);
  setInterval(() => { if (visible()) { refreshSummary(); refreshComments(); } }, 30000);
  setInterval(renderUpdated, 15000);
  document.addEventListener('visibilitychange', () => {
    if (visible()) { refreshStatus(); refreshSummary(); refreshComments(); }
  });
}

function scoreText(user) {
  if (user.flagged) return `${user.points} points · Currently unranked`;
  return `${user.points} points · ${user.rank ? 'Your rank: #' + user.rank : 'Submit an update to earn your first rank'}`;
}

// ---- Leaderboard page ----

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function plural(n, word) { return `${n} ${word}${n === 1 ? '' : 's'}`; }

function renderPodium(rows, currentUserId) {
  const slots = [...rows];
  while (slots.length < 3) slots.push(null);
  $('podium').replaceChildren(...slots.map((row, index) => {
    const rank = row ? row.rank : index + 1;
    const li = el('li', row ? 'spine' : 'spine spine--open');
    li.dataset.rank = String(rank);
    li.dataset.you = String(!!row && row.id === currentUserId);
    li.value = rank;
    li.append(el('span', 'spine__rank', String(rank)));
    if (row) {
      li.append(el('span', 'spine__name', row.name + (row.id === currentUserId ? ' (you)' : '')));
      const points = el('span', 'spine__points');
      points.append(el('strong', '', String(row.points)), document.createTextNode(row.points === 1 ? 'point' : 'points'));
      li.append(points, el('span', 'spine__badge', '1 month Premium free'));
    } else {
      li.append(el('span', 'spine__name', 'Open spot'), el('span', 'spine__points', 'Could be you'));
    }
    return li;
  }));
}

function renderCatalogue(rest, leaderPoints, currentUserId) {
  listItems($('leaderboard'), rest, (li, row) => {
    li.value = row.rank;
    li.dataset.you = String(row.id === currentUserId);
    const who = el('span', 'catalogue__who');
    who.append(el('span', 'catalogue__name', row.name + (row.id === currentUserId ? ' (you)' : '')), el('span', 'catalogue__meta', plural(row.reports_total, 'report')));
    const bar = el('span', 'catalogue__bar');
    const fill = el('span');
    fill.style.width = `${leaderPoints ? Math.max(4, Math.round(row.points / leaderPoints * 100)) : 0}%`;
    bar.append(fill);
    bar.setAttribute('aria-hidden', 'true');
    who.append(bar);
    if (row.rank <= 3) who.append(el('span', 'catalogue__prize', 'Top 3 · 1 month Premium free'));
    const pts = el('span', 'catalogue__points', String(row.points));
    pts.append(el('small', '', row.points === 1 ? 'point' : 'points'));
    const rank = el('span', 'catalogue__rank', String(row.rank));
    rank.setAttribute('aria-hidden', 'true');   // the <ol> already announces the position
    li.append(rank, who, pts);
  });
}

async function initLeaderboardPage() {
  let renderedRows = null;
  async function refresh() {
    try {
      const [data, me] = await Promise.all([
        api('/api/leaderboard'), api('/api/me').catch(() => null)
      ]);
      const current = data.current_user;
      const rows = data.leaderboard;
      $('leaderboard-error').textContent = '';
      $('leaderboard-position').textContent = current ? scoreText(current) : 'Sign in to see your points and rank.';
      $('leaderboard-meta').textContent = `Top ${rows.length} of ${data.total_contributors} contributors · refreshes every 10 seconds`;
      $('you-signed-in').hidden = !current;
      $('you-signed-out').hidden = !!current;
      if (current) {
        $('you-points').textContent = String(current.points);
        $('you-rank').textContent = current.rank ? '#' + current.rank : 'Unranked';
        $('you-plan').textContent = me ? (me.user.is_premium ? 'Premium' : 'Free') : 'Unavailable';
      }
      const signature = JSON.stringify([rows, current && current.id]);
      if (signature !== renderedRows) {
        renderPodium(rows.slice(0, 3), current && current.id);
        renderCatalogue(rows.slice(3), rows.length ? rows[0].points : 0, current && current.id);
        renderedRows = signature;
      }
      $('podium-empty').hidden = rows.length > 0;
      $('podium-empty').textContent = 'No points yet. Be the first to contribute!';
      $('rest-empty').hidden = rows.length > 3;
      $('rest-empty').textContent = 'More contributors will appear here as they earn points.';
    } catch (e) {
      $('leaderboard-error').textContent = 'Could not refresh the leaderboard. Retrying automatically.';
    }
  }
  await refresh();
  setInterval(() => { if (document.visibilityState === 'visible') refresh(); }, 10000);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') refresh(); });
}

// ---- Premium page ----

async function initPremiumPage() {
  const button = $('subscribe');
  const message = $('premium-msg');
  const params = new URLSearchParams(window.location.search);
  button.disabled = true;
  try {
    let user;
    if (params.has('session_id')) {
      message.textContent = 'Checking your payment…';
      user = (await api('/api/checkout/confirm?session_id=' + encodeURIComponent(params.get('session_id')))).user;
      history.replaceState(null, '', '/premium');
    } else {
      user = (await api('/api/me')).user;
    }
    const active = user.is_premium && (!user.premium_until || new Date(user.premium_until) > new Date());
    button.disabled = active;
    button.textContent = active ? 'Premium active' : 'Unlock Premium · €1.99';
    message.textContent = active ? 'Your account has Premium. Thank you!' :
      (params.has('cancelled') ? 'Checkout cancelled. You can try again whenever you like.' : 'One payment unlocks Premium permanently.');
  } catch (e) {
    message.textContent = e.status === 401 ? 'Log in on the Account page first, then return here.' : e.message;
    button.disabled = params.has('session_id') || e.status !== 401;
  }
  button.addEventListener('click', async () => {
    button.disabled = true;
    message.textContent = 'Opening sandbox checkout…';
    try {
      const data = await api('/api/checkout', { method: 'POST' });
      window.location = data.url;
    } catch (e) {
      message.textContent = e.status === 401 ? 'Log in on the Account page first.' : e.message;
      button.disabled = false;
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
      `${scoreText(user)} · ${user.is_premium ? 'Premium' : 'Free plan'}`;
  };
  const refreshAccount = async () => {
    try { show((await api('/api/me')).user); }
    catch (e) {
      if (e.status === 401) { $('login-card').hidden = false; $('account-card').hidden = true; }
    }
  };
  await refreshAccount();
  setInterval(() => { if (document.visibilityState === 'visible') refreshAccount(); }, 10000);

  $('login-form').addEventListener('submit', async event => {
    event.preventDefault();
    try {
      show((await api('/api/login', { method: 'POST', body: { name: $('name').value, email: $('email').value } })).user);
    } catch (e) { $('login-msg').textContent = e.message; }
  });
  $('logout').addEventListener('click', async () => { await api('/api/logout', { method: 'POST' }); location.reload(); });
}


function initFeedbackForm() {
  const form = $('feedback-form');
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('button');
    button.disabled = true;
    try {
      await api('/api/feedback', { method: 'POST', body: { message: $('feedback-message').value } });
      form.reset();
      $('feedback-result').textContent = 'Thanks! Your feedback has been sent to the team.';
    } catch (e) {
      $('feedback-result').textContent = e.status === 401 ? 'Please sign in before sending feedback.' : e.message;
    } finally { button.disabled = false; }
  });
}

async function initFeedbackInbox() {
  let before = null;
  async function load(append = false) {
    const data = await api('/api/feedback' + (append && before ? '?before=' + before : ''));
    if (!append) $('feedback-list').replaceChildren();
    data.feedback.forEach(row => {
      const item = document.createElement('li');
      const meta = document.createElement('p');
      meta.className = 'body-muted';
      meta.textContent = row.name + ' · ' + new Date(row.created_at).toLocaleString();
      const text = document.createElement('p');
      text.textContent = row.message;
      text.style.whiteSpace = 'pre-wrap';
      item.append(meta, text);
      $('feedback-list').append(item);
    });
    before = data.next_before;
    $('feedback-more').hidden = !before;
    $('feedback-access').hidden = true;
    $('feedback-inbox').hidden = false;
    $('inbox-message').textContent = $('feedback-list').children.length ? '' : 'No feedback yet.';
  }
  $('feedback-access').addEventListener('submit', async event => {
    event.preventDefault();
    const button = event.target.querySelector('button');
    button.disabled = true;
    try {
      await api('/api/feedback/access', { method: 'POST', body: { password: $('feedback-password').value } });
      $('feedback-password').value = '';
      await load();
    } catch (e) { $('inbox-message').textContent = e.message; }
    finally { button.disabled = false; }
  });
  $('feedback-more').addEventListener('click', async () => {
    $('feedback-more').disabled = true;
    try { await load(true); }
    catch (e) { $('inbox-message').textContent = e.message; }
    finally { $('feedback-more').disabled = false; }
  });
  $('feedback-lock').addEventListener('click', async () => {
    try {
      await api('/api/feedback/lock', { method: 'POST' });
      $('feedback-list').replaceChildren();
      $('feedback-inbox').hidden = true;
      $('feedback-access').hidden = false;
      $('inbox-message').textContent = 'Inbox locked.';
    } catch (e) { $('inbox-message').textContent = e.message; }
  });
  try { await load(); }
  catch (e) { if (e.status !== 401) $('inbox-message').textContent = e.message; }
}
