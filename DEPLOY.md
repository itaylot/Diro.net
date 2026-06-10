# 🚀 מצאן — Deployment Guide

Turn this from a local prototype into a 24/7 product you and your girlfriend open from your phones.

---

## TL;DR — the simplest reliable path

1. Rent a **small VPS** (~$5–6/month) or use a spare always-on machine.
2. Copy the project, create a `.env` with your Telegram token.
3. Run **`python run_all.py`** under **Docker** *or* **systemd** so it restarts forever.
4. Open `http://YOUR_SERVER_IP:5050`.

That's it. Everything (dashboard + bot + both scanners + daily tips) runs from one command and self-heals.

---

## 1. What runs

`run_all.py` is a **supervisor**: it launches all 4 long-running parts as child processes and **auto-restarts any that crash** (with backoff). One Selenium hiccup never takes down the website or the bot.

| Process | Role |
|---------|------|
| `dashboard.py` | The website (port 5050) |
| `telegram_bot.py` | Telegram bot (commands + buttons) |
| `facebook_agent.py` | Facebook group scanner (own schedule) |
| `apartment_agent.py` | Yad2 + Homely scanner (own schedule) |
| `tips_agent.py` | Refreshed once a day |

Logs are written to `logs/<name>.log` and `logs/supervisor.log`.

---

## 2. Hosting recommendation

| Option | Cost | Notes |
|--------|------|-------|
| **Hetzner CX22** (recommended) | ~€4/mo | 2 vCPU / 4 GB — plenty for Chromium |
| **Oracle Cloud Free Tier** | Free | ARM Ampere, generous free VM — best value if you tolerate setup |
| **DigitalOcean / Linode** | $6/mo | Simple, reliable |
| **Spare PC / Raspberry Pi 4** | Free | At home; just needs to stay on |

Pick **2 GB RAM minimum** — headless Chromium is the heavy part. 4 GB is comfortable.

> **Database?** None needed. This product uses flat JSON files (`all_listings.json`, etc.). For a 2-person tool with ~tens of listings/week, JSON is the right call — simpler, debuggable, zero ops. Don't add a database.

---

## 3. Configuration & secrets

Copy `.env.example` → `.env` and fill in:

```ini
TELEGRAM_TOKEN=123456:ABC...      # from @BotFather
TELEGRAM_CHAT_ID=6300931023       # the bot tells you on /start
PORT=5050
```

Values in `.env` **override** `settings.json`. The token is no longer required to live in `settings.json` — keep secrets in `.env` (which is git-ignored).

All search preferences (price, rooms, intervals, Facebook groups) are edited live from the **dashboard Settings drawer** — no redeploy needed.

---

## 4A. Deploy with Docker (recommended — Chromium baked in)

```bash
# on the server, inside the project folder
cp .env.example .env && nano .env        # fill in your token

docker compose up -d --build             # build + run in background
docker compose logs -f                   # watch it start
```

- `restart: unless-stopped` survives crashes **and server reboots**.
- Your data files + Facebook login (`fb_chrome_profile/`) are mounted as volumes, so they persist across rebuilds.
- Update after code changes: `docker compose up -d --build`.

**First-time Facebook login** (needed once, to seed `fb_chrome_profile/`):
run `python facebook_agent.py --login` on a machine with a screen, then copy the `fb_chrome_profile/` folder to the server. (Headless servers can't show the login window.)

## 4B. Deploy with systemd (no Docker)

```bash
# install Chrome/Chromium + Python deps
sudo apt update && sudo apt install -y chromium-browser python3-venv
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# install the service (edit User=/WorkingDirectory= inside the file first)
sudo cp deploy/matzan.service /etc/systemd/system/matzan.service
sudo systemctl daemon-reload
sudo systemctl enable --now matzan
```

Watch / control:
```bash
journalctl -u matzan -f          # live logs
sudo systemctl restart matzan    # restart
sudo systemctl status matzan     # health
```

`Restart=always` keeps it alive across crashes and reboots.

---

## 5. Run locally (development)

```bash
pip install -r requirements.txt
python run_all.py          # everything at once
# or individually:
python dashboard.py        # just the website → http://localhost:5050
python test_classifier.py  # classifier tests (46 cases)
```

---

## 6. Security basics

- ✅ Secrets in `.env` (git-ignored), not in code.
- ✅ `fb_chrome_profile/` is git-ignored (it contains your Facebook session).
- 🔒 **Don't expose port 5050 to the open internet unprotected.** Options:
  - Easiest: access over your home network / a VPN (Tailscale is free and 2-minute setup).
  - Or put **Caddy/Nginx** in front with HTTP basic-auth + HTTPS (Caddy gives auto-HTTPS in ~5 lines).
- 🔒 The dashboard has no auth by design (personal tool). Treat its URL as private.

---

## 7. Monitoring & health

- **Scraper health** is visible in `logs/facebook.log` — the agent prints a per-group summary and a `⚠️ רק N פוסטים` warning when a group returns too little (a sign Facebook changed something or login expired).
- **Supervisor restarts** are logged in `logs/supervisor.log`.
- Telegram itself is your uptime monitor: if alerts stop, check the logs.

---

## 8. Deployment checklist

- [ ] Server with ≥2 GB RAM, timezone `Asia/Jerusalem`
- [ ] `.env` created with `TELEGRAM_TOKEN` + `TELEGRAM_CHAT_ID`
- [ ] `fb_chrome_profile/` seeded via `--login` and copied to server
- [ ] `docker compose up -d --build` **or** systemd service enabled
- [ ] Open `http://SERVER:5050` — dashboard loads, cards show
- [ ] Send `/start` to the bot — it replies
- [ ] Trigger a scan (dashboard refresh button or `/סרוק`) — a Telegram alert arrives
- [ ] Restart the server — confirm everything comes back automatically
- [ ] (Recommended) Put Tailscale or Caddy+auth in front before sharing the URL

---

## 9. Keeping scrapers alive 24/7 — how it works

- Each scanner has its **own internal schedule** (`fb_interval_minutes`, `yad2_interval_minutes` in settings) and loops forever.
- `run_all.py` / Docker `restart:` / systemd `Restart=always` guarantee the **process** comes back if it ever dies.
- The Facebook **session** can expire (Facebook logs you out occasionally). When the log shows the login warning, re-run `--login` locally and re-copy `fb_chrome_profile/`. This is the only routine manual step.
