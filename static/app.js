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

// ---- Status page ----

async function refreshStatus() {
  try {
    const s = await api('/api/status');
    $('status-label').textContent = s.label;
    $('status-label').dataset.level = s.level;
    $('status-meta').textContent = `Based on ${s.report_count} recent reports · confidence ${s.confidence}`;
  } catch (e) { $('status-label').textContent = e.message; }
}

async function refreshSummary() {
  try {
    const s = await api('/api/summary');
    $('summary').textContent = s.status === 'not_enough'
      ? 'Not enough recent comments for a summary yet.'
      : (s.summary || 'Summary unavailable right now.');
    listItems($('themes'), s.themes, (li, t) => { li.textContent = `${t.label} (${t.count})`; li.dataset.sentiment = t.sentiment; });
  } catch (e) { $('summary').textContent = e.message; }
}

async function refreshComments() {
  try {
    const data = await api('/api/comments');
    listItems($('comments'), data.comments, (li, c) => { li.textContent = `${c.name}: ${c.text}`; });
  } catch (e) { $('comment-msg').textContent = e.message; }
}

function initStatusPage() {
  document.querySelectorAll('[data-level]').forEach(button => {
    button.addEventListener('click', async () => {
      $('report-msg').textContent = 'Sending…';
      try {
        await api('/api/reports', { method: 'POST', body: { level: button.dataset.level } });
        $('report-msg').textContent = 'Thanks! Your report counts.';
        refreshStatus();
      } catch (e) {
        $('report-msg').textContent = e.status === 401 ? 'Log in on the Account page first.' : e.message;
      }
    });
  });
  $('comment-form').addEventListener('submit', async event => {
    event.preventDefault();
    try {
      await api('/api/comments', { method: 'POST', body: { text: $('comment').value } });
      $('comment-form').reset();
      $('comment-msg').textContent = 'Posted.';
      refreshComments();
    } catch (e) {
      $('comment-msg').textContent = e.status === 401 ? 'Log in on the Account page first.' : e.message;
    }
  });
  refreshStatus(); refreshSummary(); refreshComments();
  setInterval(refreshStatus, 10000);
  setInterval(() => { refreshSummary(); refreshComments(); }, 30000);
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
