# Project State — דירונט / DiroNet
Last updated: 2026-06-11

## Status
🟢🚀 **DEPLOYED & LIVE 24/7** — code quality initiative underway
- Live at **https://dironet.duckdns.org** (Hetzner CX22, Docker, Caddy, HTTPS)
- Facebook runs on home PC, pushes via /api/ingest; Yad2 runs 24/7 on server
- 38-finding engineering audit completed; Phase 0 (critical fixes) in progress

## What Works
### Scraping & classification
- ✅ Facebook scraping from home PC (IP ביתי) → pushes to server via token-auth /api/ingest
- ✅ Yad2 (requests + Selenium) + Homely (NameError bug fixed)
- ✅ Classifier: 7 categories, **46/46 unit tests**
- ✅ שכונה ב-only filter, food-ad rejection, neighborhood cross-filter
- ✅ "ראה עוד" expansion, 5-strategy DOM fallback, per-group low-post warnings

### Product / UI
- ✅ In-app login (`app_auth.py`) — itay / neta, 30-day sessions
- ✅ Per-user favorites ❤️, shared tracking board 📋 with status/rating/notes/call/navigate
- ✅ Read-only tracking cards with dedicated edit modal
- ✅ Add apartment manually (➕)
- ✅ Match score badge, "why matched" chips, freshness, source badge on cards
- ✅ Live agent-status widget (`agent_status.py`)
- ✅ Filters: search + sort + source; 4 stat widgets; hamburger + bottom-nav mobile UI
- ✅ Telegram bot (Yad2 alerts only; /scan; keep/dismiss)

### Infra / deployment
- ✅ Docker + docker-compose, Caddy HTTPS, DISABLE_FACEBOOK=1 on server
- ✅ `run_all.py` supervisor; firewall 22/80/443; dashboard 5050 internal
- ✅ `/api/ingest` token-authenticated endpoint for home-PC FB push
- ✅ `telegram_bot.py` bot crash fixed (Hebrew /סרוק → MessageHandler)
- ✅ Portfolio docs: ARCHITECTURE, DECISIONS (ADRs), INTERVIEW_GUIDE, AUDIT

### Security / code quality (Phase 0, in progress)
- ✅ **Stored XSS fixed** — all scraped fields escaped via `esc()`/`safeUrl()`/`safeId()` in dashboard rendering (commit `8fedab6`)
- ✅ **`storage.py`** — atomic (`os.replace`) + cross-process locked (`filelock`) JSON helper; 8/8 tests including 20-thread race test (commit `3fb3902`)
- ✅ Security audit documented in `docs/AUDIT.md` (38 findings, 80/20 roadmap)
- ✅ `fb_profile.zip`, `*.lock`, `*.tmp`, `tracking.json` git-ignored
- ✅ Dead functions (`mentions_hood`, `mentions_street`) removed
- ⚠️ **UNCOMMITTED**: Step 2 Commit 2 migration in progress — `app_auth.py`, `app_tracking.py`, `facebook_agent.py` have been edited to use `storage.py` but not yet committed or tested

## Known Problems
- ⚠️ **Step 2 Commit 2 incomplete** — storage migration to `app_auth`, `app_tracking`, `facebook_agent` is half-done (local edits, uncommitted). Also pending: `apartment_agent.py` and `dashboard.py` risky writers.
- ⚠️ **Phase 0 Step 3 not started** — Selenium lifecycle / zombie Chrome fix (F3+F4) still needed.
- ⚠️ Facebook blocks the server's Hetzner IP (datacenter) — FB must run on home PC. Works, but not autonomous.
- ⚠️ Yad2 returns Captcha intermittently from the server IP.
- ⚠️ Expiry date `2026-06-23` approaching — extend in settings.json.
- ⚠️ No login rate-limiting / CSRF / cookie hardening (F5–F8 in audit — Phase 1).
- ⚠️ JSON writes in `apartment_agent.py` and `dashboard.py` still not atomic (remainder of F2).
- ⚠️ 204 zombie processes observed — Selenium lifecycle bug (F3+F4).

## Architecture
```
Internet ──HTTPS──► Caddy ──► dironet container (run_all.py: yad2 + bot + dashboard)
Home PC ──────────────────────────────────────────► /api/ingest (token-auth) → all_listings.json
JSON store: all_listings, favorites, users, tracking, seen_*, sent_*, agent_status
app_env.py (.env) · app_auth.py (login+favorites) · app_tracking.py (board) · storage.py (safe I/O)
```

## Useful Commands
```bash
# Local
python facebook_agent.py          # FB scan from home PC (runs every 30min)
python facebook_agent.py --debug  # one cycle, visible Chrome
python test_classifier.py         # 46 classifier tests
python test_storage.py            # 8 storage/concurrency tests
python test_dashboard_security.py # 25 XSS regression tests
python dashboard.py               # http://localhost:5050

# Server
cd ~/AGENTS && git pull && docker compose up -d --build
docker compose logs dironet --tail 30
```

## Current Priority
**Complete Phase 0 of the code-health initiative (see `docs/AUDIT.md`):**
1. Finish + commit Step 2 Commit 2 (storage migration for remaining writers)
2. Fix Selenium lifecycle + supervisor backoff (Step 3, F3+F4)
3. Then Phase 1: cookie hardening + login rate-limit (F6+F8)

## Next Recommended Step
Finish the storage migration: run full test suite, commit Step 2 Commit 2, then push to the server and do `docker compose up -d --build` (new `filelock` dep needs a rebuild).
