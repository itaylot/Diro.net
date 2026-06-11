# 🩺 Code Health — living backlog

> A continuous-improvement tracker. Each session picks a few items, fixes them
> **safely** (compile + tests + small commit), and checks them off. This is how
> the project gets cleaner over time without ever breaking the live deployment.

**Rules of engagement**
- It's a *live, deployed* product. Every change: compile → run tests → commit small.
- Prefer many small safe PRs over one big risky refactor.
- Add a test whenever you fix a bug or touch the classifier.
- Don't change crawler behavior, Telegram, or deployment without a clear reason.

**Status key:** ⬜ todo · 🔧 in progress · ✅ done · 🅿️ parked (needs a decision)

---

## 🔴 Critical (correctness / safety)

- ✅ **`fb_profile.zip` (348 MB, contains FB session) was untracked** — could be
  committed by `git add -A`. Fixed: git-ignored `fb_profile.zip`, `*.zip`. (2026-06-11)
- ✅ **`tracking.json` not git-ignored** — shared board data would be committed.
  Fixed: added to `.gitignore`. (2026-06-11)
- ⬜ **Concurrent JSON writes** — `all_listings.json` is read-modify-write from
  multiple writers (yad2 agent, dashboard scan, /api/ingest). Low collision now,
  but a real race. *Plan:* a tiny file-lock helper, or migrate to SQLite (ADR-003).
- ⬜ **`/api/scan_now` in-memory `_scan_status`** breaks if dashboard ever runs
  under multi-worker gunicorn. Document or move to the file-based status board.

## 🟠 Important (robustness / structure)

- ⬜ **`dashboard.py` is ~1020 lines** with inline HTML/CSS/JS. Split static
  assets (`/static/app.css`, `/static/app.js`) to make it maintainable. (Biggest
  structural win; do it carefully — it's the UI of a live product.)
- ⬜ **No tests for new modules** — `app_auth` (login/hash/favorites),
  `app_tracking` (CRUD), `/api/ingest`. Add unit tests.
- ⬜ **Error handling audit** — many `except Exception: pass` swallow errors
  silently in the scrapers. Log at least a one-line warning so failures are visible.
- ⬜ **Selenium driver lifecycle** — confirm `driver.quit()` always runs (zombie
  Chrome processes were seen on the server). Wrap scans in try/finally.

## 🟡 Cleanup (dead code / clarity)

- ✅ **Dead functions `mentions_hood`, `mentions_street`** in `facebook_agent.py`
  — defined, never called. Removed. (2026-06-11)
- ✅ **Bare `except:`** in `dashboard.get_ip()` → `except Exception:`. (2026-06-11)
- ⬜ **Dead CSS** after the header refactor: `.hdr-nav`, `.nav-tab`, `.arch-pill`,
  `.icon-btn`, `.logout-btn`, `.btn-undo` (elements removed). Verify + delete.
- 🅿️ **Email feature** (`email_template.py`, `preview_email.py`, `send_email`,
  hardcoded `EMAIL_RECIPIENT`) — unused (Telegram replaced it). *Decision needed:*
  delete, or keep as an optional channel? Currently dead weight.
- ⬜ **`clean()` vs `normalize_text()`** in facebook_agent — overlapping text
  helpers; consolidate.

## 🟢 Nice-to-have (learning / quality)

- ⬜ Type hints + docstrings pass on the agents (currently partial).
- ⬜ A `Makefile` / `tasks.py` for common commands (test, run, deploy).
- ⬜ Lint config (`ruff`) + a one-line `ruff check` in the test flow.
- ⬜ Expand `test_classifier.py` with the real false-positives we've seen.
- ⬜ A `/healthz` endpoint for uptime monitoring.

---

## Session log (what each pass did)
- **2026-06-11** — Initiative created. Audited the codebase; fixed the 4 items
  marked ✅ above (gitignore safety ×2, dead funcs, bare except). Backlog seeded.
