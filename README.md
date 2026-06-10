# 🏠 דירונט — Apartment-Hunting Agent for Beer Sheva

An always-on agent that monitors apartment sources (Yad2, Homely, Facebook groups), filters out the noise with a deterministic classifier, and pushes **only relevant matches** to Telegram in real time — with a polished web dashboard for triage.

Built for a real apartment search (a couple looking in שכונה ב׳, Beer Sheva), and as a portfolio project I can fully explain.

---

## ✨ What it does

- **Monitors multiple sources** continuously (Yad2 + Homely via HTTP/Selenium, Facebook groups via Selenium).
- **Classifies every listing** with a transparent rule engine — rejects roommates, sales, food ads, seekers, wrong neighborhoods, and over-budget posts. Each decision comes with the **reasons** it was kept or rejected.
- **Alerts instantly on Telegram** with a match score, why-it-matched, freshness, and price — never the same listing twice.
- **Web dashboard** with match-score badges, "why this matched", freshness, filters, a live "what is the agent doing now" indicator, and an archive.
- **Runs 24/7** under a supervisor that auto-restarts any crashed component.

---

## 🏗️ Architecture (in one breath)

> Independent worker processes scrape sources → a deterministic classifier filters them → results land in a JSON store → a web dashboard and a Telegram bot read from it → a supervisor keeps it all alive.

```
 sources ──► scrapers ──► classifier ──► JSON store ──► dashboard + Telegram bot
                                              ▲
                                   run_all.py supervises everything
```

Full write-up, with diagrams and decision records, in [`docs/`](docs/README.md).

---

## 🚀 Quick start

```bash
pip install -r requirements.txt
cp .env.example .env            # add your Telegram token
python run_all.py               # runs everything (dashboard + bot + scanners)
# dashboard → http://localhost:5050
```

Run the classifier test suite (no browser needed):

```bash
python test_classifier.py       # 46 labeled cases
```

Deploy 24/7 (Docker or systemd): see [`DEPLOY.md`](DEPLOY.md).

---

## 🧠 Engineering highlights (the interesting decisions)

| Decision | Why | Read more |
|----------|-----|-----------|
| Rule-based classifier, **not** an LLM | No training data; full explainability; zero cost/latency | [ADR-004](docs/DECISIONS.md) |
| Flat JSON store, **not** a database | Right-sized for the scale; I can state the limits & migration path | [ADR-003](docs/DECISIONS.md) |
| Separate processes + supervisor | Fault isolation — a Selenium crash can't kill the website | [ADR-007/008](docs/DECISIONS.md) |
| Docker with Chromium baked in | Reproducible environment; the browser is the hard dependency | [ADR-009](docs/DECISIONS.md) |
| Secrets in `.env` (12-Factor) | Token never in source control | [ADR-010](docs/DECISIONS.md) |

The full set of Architecture Decision Records, a system walkthrough, and an interview guide are in [`docs/`](docs/README.md).

---

## 📂 Project layout

```
facebook_agent.py    Facebook group scraper + the classifier (classify_post)
apartment_agent.py   Yad2 + Homely scraper
telegram_bot.py      Telegram bot (alerts + commands + buttons)
dashboard.py         Flask web dashboard (single file, vanilla JS)
run_all.py           Supervisor — runs & auto-restarts everything
agent_status.py      Cross-process "what is the agent doing now" board
app_env.py           Loads .env secrets + forces UTF-8
test_classifier.py   46 unit tests for the classifier
settings.json        Live config (price, rooms, intervals, groups)
docs/                Architecture, decisions (ADRs), interview guide, roadmap
```

---

## 🛠️ Tech

Python · Flask · Selenium · python-telegram-bot · Docker · vanilla JS (no build step)

---

## 📜 Note on scraping

This project scrapes public listing pages for personal use. It is read-only — it never posts, comments, likes, or messages. Respect each platform's Terms of Service.
