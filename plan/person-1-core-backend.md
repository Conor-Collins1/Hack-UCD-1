# Person 1: Core backend

**Name:** Conor

**Your job:** make the status *correct and trustworthy*. You own the data, the status
calculation, bad-actor detection, the leaderboard, and the demo replay script that drives
the whole demo.

**Your files:** `app/main.py`, `library/db.py`, `library/auth.py`, `library/clock.py`,
`library/status.py`, `library/trust.py`, `library/core_routes.py`, `scripts/replay.py`,
`tests/test_status.py`, `tests/test_trust.py`.

**Already in the skeleton:** FastAPI app, SQLAlchemy tables, login, the report/comment/status/leaderboard
endpoints with validation, the 10-minute report cooldown, the demo endpoints, and a
basic replay script. Occupancy calculation is implemented; trust scoring and leaderboard rewards remain TODO(Person 1).

---

## Timeline

### 0:00–0:20 · Setup (whole team together)
- [ ] Everyone clones the repo, creates `.venv`, runs `pytest` (the migration API tests should pass)
- [ ] Walk the team through `CLAUDE.md`: tables, endpoints, who owns what
- [ ] Agree any changes to the contract **now**, while it's cheap

### 0:20–1:30 · Status calculation (`status.py`)
- [ ] `compute_status`: reports from the last 45 min; weight = `0.5 ** (age_min / 15) * trust_score`
      (0 for flagged users); score = weighted average of `LEVEL_SCORE`
- [ ] Hysteresis: become `full` above 0.9, leave `full` only below 0.8 (previous level = latest snapshot)
- [ ] `busy` vs `not_full` threshold: pick one (e.g. score ≥ 0.5) and note it in a comment
- [ ] `confidence`: low < 3 reports, medium 3–6, high 7+
- [ ] `trend_per_min`: compare the current score with the snapshot ~20 min ago (Person 3 needs this)
- [ ] `save_snapshot`: insert a `status_snapshots` row
- [ ] Tests: no reports, one report, all agree, a 50/50 split, old reports fading out
- [ ] **Push by 1:30.** Person 2 and Person 3 are waiting on real status data

### 1:30–2:45 · Trust + leaderboard (`trust.py`) and replay
- [ ] `judge_pending_reports`: for each unjudged report older than 15 min, compare it with
      the consensus of *other* users' reports from ±15 min around it; set `reports.agreed`
- [ ] Update `reports_total`, `reports_agreed`, `trust_score = (agreed + 1) / (total + 2)`
- [ ] Flag if trust < 0.3 after ≥ 5 judged reports
- [ ] Points: +1 per agreed report; +3 for the first report of a level change others confirmed;
      flagged users get 0
- [ ] `leaderboard`: shape `[{"rank", "name", "points", "reports_total"}]`, excludes flagged users
- [ ] `reward_top_users`: top 3 → `payments.grant_premium(conn, id, 30, 'leaderboard')`, then reset points
- [ ] `replay.py`: a realistic 2–3 hour afternoon (8–12 users, rise to full, then easing off),
      a spammer who gets flagged partway through, and 10+ comments for the AI summary
- [ ] Tests: honest user's trust rises, spammer gets flagged, flagged reports don't move the status

### 2:45–3:30 · Integration (whole team)
- [ ] `python -m library.cli reset-db --confirm-reset`, run with `DEMO_MODE=1 DEMO_SPEED=60`, run the replay
- [ ] Check: status climbs to Full, spammer gets flagged, leaderboard fills, Person 3's alerts fire
- [ ] **Feature freeze at 3:30**

### 3:30–4:15 · Testing
- [ ] Ordinary, boundary and failure tests: no reports; exactly 5 reports at trust 0.3;
      a sudden jump to full; bad JSON; logged out; cooldown
- [ ] Write down 2–3 things you learned or changed from testing (for the "Stay curious" score)

### 4:15–5:00 · Demo prep (whole team)
- [ ] You run the replay during the demo. Practise the timing twice

---

## If you're behind, cut in this order
1. The +3 "first to report a change" bonus (keep +1 per agreed report)
2. The `trend_per_min` calculation (tell Person 3, who can then cut the "filling up" alert)
3. `reward_top_users` as a command: just explain it in the pitch

**Never cut:** a correct `compute_status`, the spammer getting flagged, `replay.py`.

## Watch out for
- SQLite returns datetimes without timezones: wrap them in `clock.as_utc()`
- Use `clock.now()` everywhere or demo speed-up will break
- `DEMO_SPEED` only works with one local process (`uvicorn app.main:app`), not with multiple workers on Render
