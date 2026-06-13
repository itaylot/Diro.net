# 🎯 GOAL — Engineering Hardening Plan (CV-Ready)

> **North star:** bring דירונט from "a real product that works" to "a project I can
> study end-to-end, defend line-by-line in an interview, and be proud to put on my CV."
>
> This is the **engineering** plan (correctness, structure, tests, learnability).
> For the **product** vision see [`ROADMAP.md`](ROADMAP.md). For the rolling backlog
> see [`CODE_HEALTH.md`](CODE_HEALTH.md) — this document supersedes it as the ordered plan.
>
> **Rules of engagement** (unchanged, non-negotiable — it's a live deployment):
> 1. Every change: `py_compile` → run the test suites → **small** commit.
> 2. Add a test whenever you fix a bug or touch the classifier.
> 3. Never change classifier scoring, Telegram UX, or deploy without a stated reason.
> 4. Prefer many small safe commits over one big refactor.
>
> **Status key:** ⬜ todo · 🔧 in progress · ✅ done · 🅿️ parked (needs a decision)
>
> _Created 2026-06-13 from a full code review. Update the checkboxes + the session
> log at the bottom as you go._

---

## Where we are (baseline, 2026-06-13)

- ✅ Stored-XSS in the dashboard hardened (scraped text escaped; 25 regression tests).
- ✅ `storage.py` written — atomic writes + cross-process file locks (8 tests).
- ✅ Migrated to `storage.py`: `app_auth`, `app_tracking`, `facebook_agent`,
  `apartment_agent`, `dashboard`.
- ✅ Facebook agent auto-start on Windows (`run_facebook_agent.ps1` + scheduled task)
  with zombie-Chrome cleanup as a stop-gap.
- **Tests at baseline:** classifier 46/46 · storage 8/8 · security 25/25.

The four phases below close every gap found in the review, in dependency order.
Each item has: **what · why · where · acceptance**.

---

## ▸ Phase 1 — Correctness & Safety (finish what's started)

> Goal: zero known data-races, zero known XSS, no silent crash loops. Small, surgical.

### 1.1 ✅ Finish the `storage.py` migration — `telegram_bot.py` (done 2026-06-13, `2428902`)
- **What:** route `load_settings/save_settings`, `load_all`, `load_dismissed/save_dismissed`,
  `load_sent/save_sent` through `storage.read_json` / `write_json`.
- **Why:** the bot still does raw `open()/json.dump` (no lock, non-atomic). The dashboard
  writes the **same** `dismissed.json` through the locked path — the bot bypasses it, so a
  concurrent dismiss can clobber or read a half-written file. This is the last gap from the
  F2 migration.
- **Where:** `telegram_bot.py:41-73`.
- **Acceptance:** no raw `json.load/dump` left in `telegram_bot.py`; bot still sends/dismisses;
  all suites green.
- **Done:** also went a layer deeper than planned — switched all 5 read-modify-write sites
  (`dismissed.json`, `sent_telegram.json`) to `storage.update_json` so concurrent writers
  can't lose updates. **Discovered a third `sent_telegram.json` writer in `facebook_agent`**
  that the original review missed; fixed it too. Removed dead `save_dismissed`/`save_sent`.
  Proven with a 2-thread/200-id race test (0 lost updates).

### 1.2 ⬜ Close the `trkCard` XSS gap
- **What:** wrap the tracking-card link in `safeUrl()` like every other link.
- **Why:** `dashboard.py:690` injects `href="${t.url}"` raw. Scraped listing URLs flow into
  tracking via `addCardToTrack` (`dashboard.py:694`), so a `javascript:` URL would execute on
  click. Behind login → low severity, but it's exactly what the XSS pass missed.
- **Where:** `dashboard.py:690`.
- **Acceptance:** add a regression assertion to `test_dashboard_security.py` (no raw `t.url`
  href); security suite green.

### 1.3 ⬜ Selenium driver lifecycle — recreate on death (F3/F4)
- **What:** wrap each scan in `try/finally`; if a scan raises, quit the dead driver and build a
  fresh one before the next cycle. Guarantee `driver.quit()` always runs.
- **Why:** today the driver is created once in `main()` and reused; if Chrome crashes, the
  `except` swallows it and **every** subsequent scan fails until a manual restart. This is the
  root cause of the zombie-Chrome incident we patched in PowerShell — fix it in the code so the
  stop-gap becomes a backstop, not the cure.
- **Where:** `apartment_agent.py:391-414`, `facebook_agent.py:1183-1221`.
- **Acceptance:** kill Chrome mid-run → the agent logs it, rebuilds the driver, and the next
  scan succeeds without manual intervention.

### 1.4 ⬜ Harden raw settings reads
- **What:** use `storage.read_json(SETTINGS_F, {})` for settings loads.
- **Why:** `facebook_agent.py:47-50` and `telegram_bot.py:41-43` do bare `json.load` — a
  half-written `settings.json` crashes the process on read.
- **Where:** `facebook_agent.py:47-50`, `telegram_bot.py:41-43` (folds into 1.1).
- **Acceptance:** corrupt `settings.json` → process falls back to defaults, doesn't crash.

### 1.5 ⬜ Make `agent_status.py` consistent
- **What:** either route through `storage.write_json` or document why its lock-free atomic
  write is acceptable (it's fire-and-forget status, last-writer-wins is fine).
- **Why:** consistency + one obvious "why" comment instead of a second bespoke writer.
- **Where:** `agent_status.py:53-58`.
- **Acceptance:** one code path or one clear comment; behavior unchanged.

---

## ▸ Phase 2 — Test Coverage (the learnability multiplier)

> Goal: the modules you'd be asked about in an interview all have tests. Writing the tests is
> what forces you to *understand* the code — that's the real payoff for the CV goal.

### 2.1 ⬜ `test_auth.py`
- **What:** unit-test `set_password`/`check_login` (hash round-trip, wrong password, unknown
  user, case-insensitive username) and `toggle_favorite` (add → remove → empty).
- **Why:** auth + favorites are zero-covered and touch security. Tests prove you understand
  hashing and the favorites data model.
- **Acceptance:** ≥6 cases pass against a temp dir (pattern already in `test_storage.py`).

### 2.2 ⬜ `test_tracking.py`
- **What:** `add_item` → `update_item` (valid + invalid status, rating coercion) → `delete_item`
  (present + absent). Assert the `_EDITABLE` whitelist actually blocks non-whitelisted keys.
- **Why:** CRUD + input-whitelisting is a clean, demonstrable story; currently zero-covered.
- **Acceptance:** ≥6 cases; covers the whitelist-rejection path.

### 2.3 ⬜ Grow `test_classifier.py` with real false-positives
- **What:** add the actual mis-classified posts you've seen in `logs/facebook.log` as labeled
  cases (food ads, roommate-vs-full-apartment, other-neighborhood cross-posts).
- **Why:** turns production noise into a regression net; the classifier is your centerpiece.
- **Acceptance:** new cases pass; total count noted in README.

### 2.4 ⬜ One smoke test for `/api/ingest`
- **What:** a tiny test that posts a fake listing with the token and asserts it lands in the
  store (and that a bad token → 401).
- **Why:** the home-PC → server ingest path is load-bearing and untested.
- **Acceptance:** 2 cases (authorized merge, unauthorized reject).

### 2.5 ⬜ A single `tests/` entry point
- **What:** a `run_tests.py` (or `tasks.py`) that runs all suites and prints one summary.
- **Why:** "how do I run the tests" should be one command in the README.
- **Acceptance:** `python run_tests.py` runs classifier + storage + security + auth + tracking.

---

## ▸ Phase 3 — Structure & Readability (so you can study it)

> Goal: no single file is a wall. The codebase reads top-to-bottom in an afternoon.

### 3.1 ⬜ Split `dashboard.py` (biggest structural win)
- **What:** extract the inline HTML/CSS/JS into `static/app.css`, `static/app.js`, and a
  `templates/` (or string-loaded) HTML file; keep `dashboard.py` as routes + glue.
- **Why:** 1024 lines with a giant embedded front-end is the hardest thing to learn and the
  least impressive thing to open in an interview. Splitting it shows you understand separation
  of concerns. **Do it carefully — it's the live UI.** Move in slices (CSS first, then JS),
  compile + eyeball the dashboard after each slice.
- **Where:** `dashboard.py`.
- **Acceptance:** `dashboard.py` < ~400 lines; the page renders identically; security tests
  still find the escaping (update test paths if the HTML moves).

### 3.2 ⬜ Decide the email feature's fate
- **What:** delete `email_template.py`, `preview_email.py`, `send_email`, and the hardcoded
  `EMAIL_RECIPIENT` — **or** document it as an opt-in fallback channel in the README.
- **Why:** it's dead weight (Telegram replaced it). Dead code you can't explain is a liability
  in a review; a deliberate, documented optional channel is fine.
- **Where:** `apartment_agent.py` (`send_email`, `EMAIL_*`), `email_template.py`, `preview_email.py`.
- **Acceptance:** either gone (and imports clean) or one README paragraph + an env flag.

### 3.3 ⬜ Consolidate text helpers in `facebook_agent.py`
- **What:** merge the overlapping `clean()` and `normalize_text()` into one documented helper.
- **Why:** two near-duplicate normalizers invite drift; the classifier deserves one clear path.
- **Where:** `facebook_agent.py:81-88`.
- **Acceptance:** one helper; classifier suite still 46/46 (or higher).

### 3.4 ⬜ Error-handling audit — replace silent `except Exception: pass`
- **What:** in the scrapers, log a one-line warning instead of swallowing exceptions silently.
- **Why:** silent failures hide DOM breakage for days. A visible log line is the cheapest
  reliability upgrade and shows good operational instincts.
- **Where:** grep `except Exception:` in `facebook_agent.py`, `apartment_agent.py`, `dashboard.py`.
- **Acceptance:** no bare swallow on a scrape/parse path without at least a logged warning.

### 3.5 ⬜ Delete confirmed dead CSS
- **What:** remove `.hdr-nav`, `.nav-tab`, `.arch-pill`, `.icon-btn`, `.logout-btn`, `.btn-undo`
  after verifying they're unused (do this **as part of 3.1**, not before).
- **Acceptance:** classes gone; UI unchanged.

---

## ▸ Phase 4 — Polish & Interview-Readiness (the CV layer)

> Goal: the repo *presents* like a senior project and you can talk about it fluently.

### 4.1 ⬜ Finish `docs/INTERVIEW_GUIDE.md` with three bug stories
- **What:** write up the three real bugs we fixed as STAR-style stories: the **stored XSS**,
  the **JSON race condition** (→ `storage.py`), and the **zombie-Chrome crash loop** (→ driver
  lifecycle + supervisor). Each: symptom → root cause → fix → how you'd prevent it.
- **Why:** "tell me about a hard bug" is the question. You have three great answers — write them
  down so they're crisp.
- **Acceptance:** three stories, each ≤150 words, each pointing at the commit that fixed it.

### 4.2 ⬜ Update `CODE_HEALTH.md` to reflect reality
- **What:** mark "concurrent JSON writes" as ✅ (storage.py shipped), note the telegram_bot gap
  as the remaining slice, and point the backlog at this GOAL doc.
- **Why:** the backlog currently predates `storage.py` and reads as if nothing's done.
- **Acceptance:** CODE_HEALTH reflects the 2026-06-13 baseline.

### 4.3 ⬜ Add `ruff` lint + a `/healthz` endpoint
- **What:** a minimal `ruff` config and a `GET /healthz` returning `{"ok": true}` for uptime
  monitoring.
- **Why:** both are tiny, both signal production maturity, both are easy interview talking points.
- **Acceptance:** `ruff check` runs clean(ish); `/healthz` returns 200 without auth.

### 4.4 ⬜ Type hints + docstrings pass on the agents
- **What:** finish type hints and one-line docstrings on the public functions in the agents.
- **Why:** the small utils are already well-typed; bringing the agents up to the same bar makes
  the whole repo read consistently.
- **Acceptance:** public functions in `apartment_agent.py` / `facebook_agent.py` typed + 1-line doc.

### 4.5 ⬜ A drawable architecture diagram
- **What:** one diagram (in `ARCHITECTURE.md`) simple enough to reproduce on a whiteboard in 30s:
  sources → scrapers → classifier → JSON store → {dashboard, bot}, with `run_all` supervising.
- **Why:** you'll be asked to draw it. Practice until it's muscle memory.
- **Acceptance:** diagram present; you can draw it from memory.

---

## Suggested order (the 80/20)

If time is short, this sequence delivers the most CV value per hour:

1. **Phase 1.1 + 1.2 + 1.3** — finish migration, close XSS, fix driver lifecycle. *(half a day)*
2. **Phase 2.1 + 2.2** — auth + tracking tests. *(half a day)*
3. **Phase 4.1 + 4.2** — bug stories + honest backlog. *(an hour)*
4. **Phase 3.1** — split `dashboard.py`. *(the big one — a focused afternoon)*
5. Everything else as polish.

After step 3 you can already walk into an interview and defend the project. Step 4 makes it shine.

---

## Session log
- **2026-06-13** — GOAL plan created from a full code review. Baseline recorded
  (storage.py migration done except telegram_bot; XSS + race + zombie-Chrome fixed earlier).
- **2026-06-13** — **Phase 1.1 ✅** (`2428902`). telegram_bot migrated to storage.py; all 5
  read-modify-write sites for dismissed/sent moved to `update_json`; found+fixed a third
  sent-writer in facebook_agent; removed dead save_* helpers. Partially advances **1.4**
  (telegram_bot settings read now safe via `read_json`; facebook_agent's raw read still TODO).
