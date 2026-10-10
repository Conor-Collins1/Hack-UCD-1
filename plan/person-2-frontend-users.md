# Person 2: Frontend, users and pitch

**Name:** _______________

**Your job:** make the app *clear and good-looking*, and prove that real students want it.
Two of the five judging criteria are mostly yours: **Users first** and **Craft and beauty**.
You also lead the pitch.

**Your files:** `templates/`, `static/`, `library/pages.py`, plus the survey, slides and
demo script (put notes in `plan/users-and-pitch.md`).

**Already in the skeleton:** four working but plain pages (status, leaderboard, premium,
account), `static/app.js` wired to every endpoint, placeholder CSS. All API shapes are in
`CLAUDE.md`, so you can build against them before the backend is finished.

---

## Timeline

### 0:00–0:20 · Setup (whole team together)
- [ ] Clone, create `.venv`, `pytest`, `uvicorn app.main:app --reload`, open http://127.0.0.1:8000
- [ ] Write the survey (5 questions max, Google Form). Suggested:
  1. How often do you go to the library to study?
  2. How often is it too full when you arrive? (never / sometimes / often / always)
  3. What do you do now to check? (just go / ask friends / group chat / other)
  4. Would you tap a button to report how full it is? Why or why not?
  5. Would you pay €1.99/month for an alert before it fills up? What would make it worth it?

### 0:20–1:30 · Status page
- [ ] Big, obvious status card: colour + label + "Based on N reports · updated 2 min ago"
- [ ] Three large report buttons that work on a phone with one thumb
- [ ] After reporting: thank-you message, and a countdown when on cooldown (429 → `retry_after_seconds`)
- [ ] "Not logged in" handled nicely (inline name/email form or a clear link, not a dead end)
- [ ] AI summary card styled like Google Maps review chips (themes coloured by sentiment)
- [ ] Comment box + list
- [ ] **Send the survey link** around your hackathon room and to friends at UCD (aim for 15+ replies)

### 1:30–2:45 · Other pages + user evidence
- [ ] Leaderboard page: top 3 highlighted with a "wins free premium" badge
- [ ] Premium page: price, what you get, Subscribe button, "you're premium" state after paying
      (handle `?session_id=` coming back from Stripe by calling `/api/checkout/confirm`; agree with Person 3)
- [ ] Account page: points, trust, premium status, ntfy topic with simple setup instructions
- [ ] If time: go to the library, count free seats at one moment, compare with what the app says
- [ ] Collect survey results: key numbers + 3 good quotes

### 2:45–3:30 · Integration (whole team)
- [ ] Run the full replay and watch every page update. Note anything confusing
- [ ] **Feature freeze at 3:30**

### 3:30–4:15 · Polish and evidence
- [ ] Mobile layout at phone width (judges might open it on a phone)
- [ ] Loading states, empty states ("No reports yet"), and error messages for every fetch
- [ ] Turn survey results into one slide: who the users are, the problem, the current workaround,
      why they'd switch, how we'd reach them (society channels, library posters, UCD Reddit/Discord)
- [ ] Mark what is **evidence** (survey numbers) and what is an **assumption**

### 4:15–5:00 · Demo prep (whole team)
- [ ] Slides (≤6): problem + evidence → demo → how it works → AI + its limits → payments → what we learned
- [ ] You present; practise twice with the replay running

---

## If you're behind, cut in this order
1. Account page polish (keep login + ntfy topic working)
2. Leaderboard styling (a plain list is fine)
3. The library seat-count check

**Never cut:** the status page looking great on a phone, the survey evidence, the pitch.

## Watch out for
- Always use `textContent` for anything a user typed (comments, names)
- Don't change API shapes yourself; ask Person 1 or 3 if you need a new field
- Keep it to vanilla JS + CSS. No React or build step at this point
