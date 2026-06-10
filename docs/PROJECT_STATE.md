# Project State — דירונט / DiroNet
Last updated: 2026-06-10

## Status
🟢🚀 **DEPLOYED & LIVE 24/7** — public site with HTTPS + login
- Live at **https://dironet.duckdns.org** (Hetzner CX22, Docker, Caddy)
- Runs 24/7 via `run_all.py` supervisor (auto-restart on crash/reboot)
- Per-user login (itay / neta), personal favorites, shared tracking board
- Mobile-first UI (bottom nav + hamburger), fully rebranded to דירונט

## What Works
### Scraping & classification
- ✅ Facebook scraping with **"ראה עוד" expansion** → relevant detections jumped from ~2 to 14+ per scan
- ✅ Yad2 (requests + Selenium) + Homely (NameError bug fixed)
- ✅ Classifier: 7 categories, **46/46 unit tests** (`test_classifier.py`)
- ✅ **שכונה ב only** filter — rejects other neighborhoods (א/ה/ו, נווה זאב…)
- ✅ **Food/service ad rejection** (סושי, קייטרינג…) + availability-needs-rooms guard
- ✅ Room range uses settings min/max (1.5–3.5), not hardcoded
- ✅ Cross-group + intra-group MD5 dedup; per-group low-post warnings
- ✅ Self-healing scrape (5 strategies) + explicit 45s page-load timeout

### Product / UI
- ✅ **In-app login** (`app_auth.py`, werkzeug-hashed `users.json`, Flask sessions)
- ✅ **Per-user favorites** ❤️ (`favorites.json`) — personal area per user
- ✅ **Shared tracking board** 📋 (`app_tracking.py`, `tracking.json`): status pipeline,
  contact + call button, viewing date, 1–5 rating, notes, Google-Maps navigate
- ✅ Tracking cards are **read-only with a dedicated edit modal**
- ✅ **Add apartment manually** (➕) — listings you found yourselves
- ✅ "Add to tracking" button shows **✓ במעקב** once added (no double-add)
- ✅ **Match score badge**, "why matched" chips, freshness, source badge on cards
- ✅ **Live agent-status widget** (`agent_status.py`) — what each scanner is doing now
- ✅ Filters: search + sort + source; 4 stat widgets (new / hot / review)
- ✅ **Mobile-first**: bottom nav bar + hamburger side menu, single-column grids,
  44px tap targets, RTL-correct

### Telegram
- ✅ Clean alerts: match level + %, why-matched, freshness, contact, price
- ✅ `/סרוק` only pushes truly relevant listings (no spam)
- ✅ Dedup via `sent_telegram.json`

### Infra / deployment
- ✅ **Docker + docker-compose** (Chromium baked in), whole-dir mount for persistence
- ✅ **Caddy** reverse proxy: automatic HTTPS (Let's Encrypt) + private dashboard
- ✅ Secrets in `.env` (git-ignored); UTF-8 stdout fix for Windows logs
- ✅ `run_all.py` supervisor; firewall 22/80/443 only; dashboard 5050 internal
- ✅ Portfolio docs: ARCHITECTURE, DECISIONS (ADRs), INTERVIEW_GUIDE

## Known Problems
- ⚠️ Facebook login (`fb_chrome_profile`) **not yet seeded on the server** — FB scanning
  won't run until the profile is created locally (`--login`) and `scp`'d up.
- ⚠️ Yad2 returns Captcha intermittently from the datacenter IP (Facebook is primary).
- ⚠️ Facebook may flag the server's datacenter IP → occasional re-login needed.
- ⚠️ Manual + agent listings can duplicate (intentional for now; dedupe later).
- ⚠️ JSON read-modify-write isn't concurrency-safe (fine at this scale; SQLite later).
- ⚠️ Old data-file `rm -rf` cleanup needed once on the server (bind-mount artifacts).
- ⚠️ Expiry date still 2026-06-23 — extend in settings.json before then.

## Architecture
```
Internet ──HTTPS+login──► Caddy ──private──► dironet container (run_all.py)
                                               ├ dashboard.py  (Flask UI + auth + favorites + tracking)
                                               ├ telegram_bot.py
                                               ├ facebook_agent.py / apartment_agent.py
                                               └ tips_agent.py
   JSON store (host volume): all_listings, favorites, users, tracking, seen_*, sent_*, agent_status
   app_env.py (.env + UTF-8) · app_auth.py (login+favorites) · app_tracking.py (board)
```

## Useful Commands
```bash
# Local
python dashboard.py                 # http://localhost:5050
python test_classifier.py           # 46 unit tests
python app_auth.py set itay         # set a login password
python run_all.py                   # run everything (supervisor)

# Server (in ~/AGENTS)
git pull && docker compose up -d --build      # normal update
docker compose down && docker compose up -d --build   # after a rename
docker compose exec dironet python app_auth.py set neta   # change a password
docker compose logs dironet --tail 40         # app logs
docker compose logs caddy --tail 40           # HTTPS / proxy logs
```

## Current Priority
**Seed Facebook login on the server** so the primary source works:
run `python facebook_agent.py --login` locally, then `scp -r fb_chrome_profile root@167.233.103.201:/root/AGENTS/`.

## Next Recommended Step
1. Seed `fb_chrome_profile/` on the server (above) → confirm FB scanning runs.
2. Extend `expiry_date` in settings.json (currently 2026-06-23).
3. Optional polish: dedupe manual vs agent listings; viewing-date reminders;
   filter the tracking board by status.
