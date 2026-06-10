# 🚀 מצאן — Deployment Guide

Turn this from a local prototype into a 24/7 product you and your girlfriend open from your phones.

---

## TL;DR — the recommended path (public site, HTTPS, login)

1. Create a **Hetzner CX22** server (~€4.5/mo, Ubuntu).
2. Point a free **DuckDNS** subdomain at the server's IP.
3. Open the firewall to **ports 22, 80, 443 only** (the dashboard's 5050 stays private).
4. Install Docker, clone the repo, create `.env`, generate two login passwords.
5. `docker compose up -d --build` — **Caddy** auto-gets an HTTPS certificate and puts a login in front.
6. Open `https://your-name.duckdns.org` from any phone → login → done.

Everything (dashboard + bot + scanners + daily tips) runs from one command, behind HTTPS + a password, and self-heals on crash or reboot. **Full step-by-step in section 4 below.**

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

## 4. Public deployment: Hetzner + DuckDNS + Caddy (HTTPS + login)

This is the full beginner walkthrough. Goal: `https://your-name.duckdns.org`, reachable from any phone, protected by a username + password. Expect ~30–45 minutes the first time.

**How the pieces fit:** the internet only ever talks to **Caddy** (ports 80/443). Caddy checks your password, gets a free HTTPS certificate, and forwards you to the **dashboard**, which is *not* reachable from the internet directly. The Telegram bot and scanners run alongside, no public port needed.

```
phone ──HTTPS+login──► Caddy ──private──► dashboard (:5050) + bot + scanners
```

### Step 1 — Create the server (Easy)
1. Sign up at [hetzner.com/cloud](https://www.hetzner.com/cloud) → **New Project** → **Add Server**.
2. Choose: **Ubuntu 24.04**, type **CX22** (2 vCPU / 4 GB — enough for Chromium), a datacenter near you (Nuremberg/Falkenstein).
3. Under **SSH keys**, add your public key (recommended) — or you'll get a root password by email.
4. Create the server and note its **public IPv4** (e.g. `91.99.12.34`).

### Step 2 — Free domain with DuckDNS (Easy)
1. Go to [duckdns.org](https://www.duckdns.org), sign in (Google/GitHub).
2. Pick a subdomain, e.g. `diro` → you get **`diro.duckdns.org`**.
3. In the **current ip** box, paste your server's IPv4 and click **update ip**.
4. (Check it: `ping diro.duckdns.org` should show your server IP.)

> Why a domain at all? HTTPS certificates can't be issued for a bare IP — you need a name. DuckDNS gives you one for free.

### Step 3 — Open only the right ports (Easy)
In the Hetzner console → your server → **Firewall** → create a firewall that **allows inbound only**:
- **22** (SSH), **80** (HTTP), **443** (HTTPS).

Everything else (including the dashboard's 5050) stays blocked from the internet. The dashboard is reachable *only* through Caddy.

### Step 4 — Connect and install Docker (Easy)
```bash
ssh root@YOUR_SERVER_IP

# install Docker + compose
curl -fsSL https://get.docker.com | sh
```

### Step 5 — Get the code (Easy)
```bash
git clone https://github.com/itaylot/Diro.net.git AGENTS
cd AGENTS
```

### Step 6 — Create your secrets file `.env` (Medium)
```bash
cp .env.example .env
nano .env
```
Fill in:
```ini
TELEGRAM_TOKEN=123456:ABC...          # from @BotFather
TELEGRAM_CHAT_ID=6300931023           # the bot tells you on /start
SITE_ADDRESS=diro.duckdns.org         # your DuckDNS domain
ITAY_HASH=                            # fill in step 7
NETA_HASH=                            # fill in step 7
```

### Step 7 — Generate the two login passwords (Medium)
Run this **on the server**, once per user, and paste each result into `.env`:
```bash
docker run --rm caddy caddy hash-password --plaintext 'itays-password-here'
docker run --rm caddy caddy hash-password --plaintext 'netas-password-here'
```
Each prints a bcrypt hash like `$2a$14$Xy...`. Put them in `.env`:
```ini
ITAY_HASH=$2a$14$....the itay hash....
NETA_HASH=$2a$14$....the neta hash....
```
> **Where do the real passwords live?** Only in `.env` on the server. `.env` is git-ignored, so it never goes to GitHub. The committed `Caddyfile` only references `{$ITAY_HASH}` — no real hash is ever in version control. Don't wrap the hashes in quotes.

### Step 8 — Seed the Facebook login (Medium — the fiddly part)
The server has no screen, so log in to Facebook on your **laptop** first:
```bash
# on your laptop, in the project folder:
python facebook_agent.py --login      # a Chrome window opens — log in, then close it
```
Then copy the saved session up to the server:
```bash
scp -r fb_chrome_profile root@YOUR_SERVER_IP:/root/AGENTS/
```

### Step 9 — Launch everything (Easy)
```bash
docker compose up -d --build
docker compose logs -f                 # watch it boot; Ctrl+C to stop watching
```
Caddy will fetch an HTTPS certificate automatically (takes ~30 seconds the first time).

### Step 10 — Open it 🎉
Visit **`https://diro.duckdns.org`** from any device → you'll get a login box → enter `itay` / your password. The padlock 🔒 means HTTPS is working.

**Updating later** (after you push code changes):
```bash
cd ~/AGENTS && git pull && docker compose up -d --build
```

## 4-ALT. Deploy with systemd (no Docker, no HTTPS/login)

> Use this only if you don't want Docker. Note: it does **not** include Caddy, so you get no HTTPS or login — keep it on a private network if you use this path. The Docker path above is recommended.

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

## 6. Security basics (how this setup protects you)

- ✅ **Login on every visit** — Caddy Basic Auth (`itay` / `neta`), passwords stored only as bcrypt hashes in `.env` on the server.
- ✅ **HTTPS everywhere** — Caddy auto-issues and renews a Let's Encrypt certificate; the login is never sent in plaintext.
- ✅ **Dashboard is private** — port 5050 is `expose`d (container-internal) but **never published** to the host, and the firewall blocks everything except 22/80/443. The only way in is through Caddy's login.
- ✅ **Secrets never in git** — `.env`, `fb_chrome_profile/`, and password hashes are all git-ignored. The committed `Caddyfile` only references `{$ITAY_HASH}` etc.
- 🔒 **Harden SSH** (recommended): use a key (not a password) and disable root password login (`PasswordAuthentication no` in `/etc/ssh/sshd_config`).
- 🔁 **Rotate a password** anytime: regenerate a hash (step 7), update `.env`, then `docker compose up -d` to reload.

---

## 7. Monitoring & health

- **Scraper health** is visible in `logs/facebook.log` — the agent prints a per-group summary and a `⚠️ רק N פוסטים` warning when a group returns too little (a sign Facebook changed something or login expired).
- **Supervisor restarts** are logged in `logs/supervisor.log`.
- Telegram itself is your uptime monitor: if alerts stop, check the logs.

---

## 8. Deployment checklist & verification

**Setup**
- [ ] Hetzner CX22 (≥2 GB RAM), Ubuntu 24.04
- [ ] DuckDNS subdomain pointing at the server IP (`ping` confirms)
- [ ] Firewall allows **only** 22 / 80 / 443
- [ ] Docker installed, repo cloned
- [ ] `.env` filled: `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `SITE_ADDRESS`, `ITAY_HASH`, `NETA_HASH`
- [ ] `fb_chrome_profile/` seeded via `--login` and `scp`'d to the server
- [ ] `docker compose up -d --build`

**Verify after deployment**
- [ ] `docker compose ps` — both `matzan` and `caddy` are **Up**
- [ ] `https://your-name.duckdns.org` shows a **login box** (not an error)
- [ ] Login with `itay` works; the browser shows a valid 🔒 (HTTPS)
- [ ] From your **phone, on mobile data** (not home wifi) — the site loads + logs in
- [ ] `curl http://YOUR_SERVER_IP:5050` from your laptop **fails/times out** (proves 5050 is private)
- [ ] Dashboard cards load; the live agent-status strip shows the scanners
- [ ] Send `/start` to the Telegram bot — it replies
- [ ] Trigger a scan (refresh button or `/סרוק`) — a Telegram alert arrives
- [ ] `sudo reboot` the server — after ~1 min, the site comes back on its own
- [ ] `docker compose logs caddy` shows a certificate was obtained (no TLS errors)

---

## 9. Keeping scrapers alive 24/7 — how it works

- Each scanner has its **own internal schedule** (`fb_interval_minutes`, `yad2_interval_minutes` in settings) and loops forever.
- `run_all.py` / Docker `restart:` / systemd `Restart=always` guarantee the **process** comes back if it ever dies.
- The Facebook **session** can expire (Facebook logs you out occasionally). When the log shows the login warning, re-run `--login` locally and re-copy `fb_chrome_profile/`. This is the only routine manual step.
