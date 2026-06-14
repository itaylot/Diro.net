# 🏠 דירונט — Apartment-Hunting Agent for Beer Sheva

An always-on agent that monitors apartment sources (Yad2, Homely, Facebook groups), filters out the noise with a deterministic classifier, and pushes **only relevant matches** to Telegram in real time — with a polished web dashboard for triage.

Built for a real apartment search (a couple looking in שכונה ב׳, Beer Sheva), deployed and actively running.

---

## 🌐 Live demo

**URL:** `https://diro.duckdns.org`

| Username | Password | Notes |
|----------|----------|-------|
| `demo`   | `demo1234` | Read-only demo account with sample data — favorites, tracking entries with notes |

The demo account shows the product as a real user would experience it: apartments saved as favorites, three tracked apartments with statuses ("scheduled viewing", "visited", "to contact") and notes from the search process.

---

## ✨ What it does

- **Monitors multiple sources** continuously — Yad2 + Homely via HTTP/Selenium, 8 Facebook groups via Selenium.
- **Classifies every listing** with a transparent rule engine: rejects roommates, sales, food ads, seekers, wrong neighborhoods, and over-budget posts. Each kept listing comes with **the reasons it matched** (shown in the dashboard and Telegram alert).
- **Alerts instantly on Telegram** with match score, why-it-matched, freshness, and price — never the same listing twice. Inline buttons to keep or dismiss, right from the chat.
- **Web dashboard** with match-score badges, freshness, filters (hot / new / review), a live agent-activity widget, favorites (per user), and a tracking board for managing viewings.
- **Runs 24/7** under a supervisor (`run_all.py`) that auto-restarts any crashed component with exponential backoff.

---

## 🏗️ Architecture (in one breath)

> Independent worker processes scrape sources → a deterministic classifier filters them → results land in a JSON store → a web dashboard and a Telegram bot read from it → a supervisor keeps it all alive.

```
 Yad2 + Homely ──► apartment_agent.py ──┐
                                         ├──► all_listings.json ──► dashboard (Flask)
 8 FB groups  ──► facebook_agent.py  ──┘                       └──► telegram_bot.py
                        │
                   classify_post()   ← the classifier (rule engine, 46 unit tests)
                        │
                   agent_status.json ← cross-process "what is running now" board

 run_all.py supervises all four processes — auto-restarts with backoff on crash
```

Facebook runs on the home PC (Facebook blocks datacenter IPs) and pushes results to the server via a token-authenticated `/api/ingest` endpoint.

Full write-up, with diagrams and decision records, in [`docs/`](docs/README.md).

---

## 🚀 Quick start (local)

```bash
pip install -r requirements.txt
cp .env.example .env        # add your Telegram token + chat ID
python run_all.py           # starts everything: dashboard + bot + both scanners
# dashboard → http://localhost:5050

# Set a login password (run once per user):
python app_auth.py set itay
```

Run the classifier test suite (no browser, no secrets needed):

```bash
python test_classifier.py   # 46 labeled Hebrew posts
python test_storage.py      # 8 concurrency tests (atomic writes + cross-process locking)
python test_dashboard_security.py  # 25 XSS regression checks
```

Deploy 24/7 (Docker + HTTPS + Caddy): see [`DEPLOY.md`](DEPLOY.md).

---

## 🧠 Engineering highlights

| Decision | Why |
|----------|-----|
| Rule-based classifier, **not** an LLM | No training data; full explainability; every classification comes with human-readable reasons; zero cost and zero latency |
| Flat JSON store, **not** a database | Right-sized for the scale; atomic writes + cross-process file locks (`storage.py`) make it safe under concurrent writers |
| Separate processes + supervisor | Fault isolation — a Selenium crash can't kill the website or the bot |
| Facebook on home PC → server via `/api/ingest` | Facebook blocks datacenter IPs; home PC pushes results over HTTPS with a token |
| Secrets in `.env` (12-Factor) | Tokens never in source control; dashboard reads live config from `settings.json` with no redeploy needed |

The full set of Architecture Decision Records (ADRs) and an interview guide are in [`docs/`](docs/README.md).

---

## 📂 Project layout

```
facebook_agent.py    Facebook group scraper + classify_post() (the classifier)
apartment_agent.py   Yad2 + Homely scraper
telegram_bot.py      Telegram bot — alerts, inline buttons, /סרוק command
dashboard.py         Flask web dashboard (single file, vanilla JS, no build step)
run_all.py           Supervisor — starts & auto-restarts everything with backoff
storage.py           Atomic JSON reads/writes + cross-process file locking
agent_status.py      Cross-process "what is the agent doing right now" board
app_auth.py          Per-user login (bcrypt), favorites, session cookies
app_tracking.py      Tracking board — CRUD for apartments under review
test_classifier.py   46 labeled classifier test cases
settings.json        Live config: price ceiling, room range, scan intervals
docs/                Architecture, ADRs, interview guide, engineering roadmap
```

---

## 🛠️ Tech

Python · Flask · Selenium · python-telegram-bot · filelock · Docker · Caddy · vanilla JS (no build step)

---

## 📜 Note on scraping

This project scrapes public listing pages for personal, non-commercial use. It is read-only — it never posts, comments, likes, or messages on any platform. Respect each platform's Terms of Service.
