# 📐 Architecture Decision Records (ADRs)

> Each record captures **one** significant decision: the context, what we chose, what we rejected, the tradeoffs, the engineering concept it teaches, and how to talk about it in an interview.

---

## ADR-000 — Use ADRs to record decisions

- **Context:** This is a learning/portfolio project. Six months from now (or in an interview) you need to remember *why* things are the way they are.
- **Decision:** Keep a lightweight decision log in this file.
- **Alternatives:** Comments scattered in code; nothing at all; a wiki.
- **Tradeoffs:** A few minutes of writing per decision, in exchange for durable understanding.
- **Concept it teaches:** **Architecture Decision Records** are a real industry practice (popularized by ThoughtWorks). Knowing the term itself signals maturity.
- **Interview angle:** *"I documented decisions as ADRs so the reasoning outlives my memory — it's the same practice many engineering teams use."*

---

## ADR-001 — Pure Python with a minimal dependency set

- **Context:** A solo student project that must stay understandable and deployable.
- **Decision:** Python + a handful of well-known libraries (Flask, Selenium, requests, schedule, python-telegram-bot). No framework sprawl.
- **Alternatives considered:** A JS/TypeScript full-stack (Node + React); Go for the scrapers; a heavyweight framework (Django).
- **Tradeoffs:** Python is slower than Go and less "modern-frontend" than React, **but** it's the best glue language for scraping + scripting, has the richest scraping/bot ecosystem, and one language across the whole stack means less context-switching.
- **Concept it teaches:** Choosing technology for **fit and maintainability**, not novelty.
- **Interview angle:** *"I optimized for one maintainer's cognitive load. One language, small dependency surface, every library is boring and battle-tested."*

---

## ADR-002 — Selenium for scraping (with a requests fast-path)

- **Context:** Yad2 and Facebook render content with JavaScript and actively resist scraping.
- **Decision:** Use Selenium (a real headless browser) for Facebook and for the deep Yad2 scan; use plain `requests` for the lightweight Yad2 "scan now" path in the dashboard.
- **Alternatives considered:** (a) `requests` + BeautifulSoup only — fails on JS-rendered pages; (b) official APIs — Yad2/Facebook don't offer suitable public ones; (c) Playwright — newer, similar, smaller community at the time.
- **Tradeoffs:** Selenium is heavy (a whole browser, ~hundreds of MB RAM) and slower, **but** it's the only thing that reliably sees what a human sees. The dashboard's `requests` path shows I use the cheap tool when it's enough.
- **Concept it teaches:** Client-side rendering vs server-side HTML; **the right tool for the constraint**; resource cost of automation.
- **Interview angle:** *"I used a browser only where I had to. For the simple Yad2 feed I parse the embedded `__NEXT_DATA__` JSON with plain HTTP — much cheaper. Knowing when NOT to use the heavy tool is the point."*
- **Honest caveat to volunteer:** scraping is brittle and ToS-gray; if an official API existed I'd prefer it.

---

## ADR-003 — Flat JSON files instead of a database

- **Context:** Tens of listings per week, one user, simple read/write needs.
- **Decision:** Store everything in flat JSON files (`all_listings.json`, `seen_*.json`, etc.).
- **Alternatives considered:** SQLite (file-based SQL), PostgreSQL, a NoSQL store.
- **Tradeoffs:** JSON is trivial to read, debug (just open the file), back up, and requires zero setup. **Cost:** no queries, no indexes, no transactions, and **concurrent writes can race** (read-modify-write of the whole file).
- **Concept it teaches:** Knowing **when you do NOT need a database** is as important as knowing how to use one. Also: serialization, and concurrency hazards.
- **Interview angle:** *"For this scale, a database would be over-engineering. I used JSON files as a simple store. I can clearly state the limitation — read-modify-write isn't concurrency-safe — and my migration path is SQLite the moment I have concurrent writers or need queries. SQLite is one `import sqlite3` away and changes only the persistence layer because reads/writes are already isolated in small functions."*
- **This is one of your strongest interview moments** — it shows judgment *and* self-awareness.

---

## ADR-004 — A deterministic rule-based classifier (not ML / not an LLM)

- **Context:** Must separate "couple rental in שכונה ב" from roommates, sales, food ads, and seekers — in Hebrew.
- **Decision:** A transparent pipeline of keyword rules + a scoring function returning a category, a score, and a **`reasons` list** explaining the decision.
- **Alternatives considered:** (a) Train an ML classifier — needs labeled data we don't have (cold start); (b) Call an LLM per post — costs money, adds latency/API dependency, non-deterministic, and is a "black box" for a problem solvable with rules; (c) a single regex — too crude.
- **Tradeoffs:** Rules need manual tuning and won't generalize beyond this domain. **But** they're free, instant, fully explainable, and testable. For a known, narrow domain, rules beat ML.
- **Concept it teaches:** **Determinism & explainability vs model complexity**; precision/recall; the cold-start problem; that the best solution is often the simplest one that works.
- **Interview angle:** *"Everyone reaches for an LLM now. I argued against it: no training data, and I wanted every decision auditable. The classifier returns the exact reasons it kept or rejected a post, which I surface in the UI. I tuned thresholds toward precision because a false positive (spam) costs the user more than a marginal miss."*

---

## ADR-005 — Telegram as the primary notification channel

- **Context:** The user wants instant, mobile, actionable alerts.
- **Decision:** Telegram bot, with inline keep/dismiss buttons and an on-demand `/סרוק` scan.
- **Alternatives considered:** Email (slow, easy to ignore, spam folders); SMS (costs money, no rich content); a custom mobile app (huge effort); web push (requires the site open).
- **Tradeoffs:** Telegram requires the user to have Telegram. **But** it's free, has a first-class bot API, supports buttons/images, and delivers instantly to a phone.
- **Concept it teaches:** Bot platforms, **push vs pull** notification models, and interactive callbacks.
- **Interview angle:** *"Telegram gave me push notifications and interactivity for free. Under the hood the library uses long-polling against Telegram's servers; I can contrast that with a webhook design, which I'd use if I wanted to avoid a persistent polling loop."*

---

## ADR-006 — Single-file Flask dashboard with inline HTML/CSS/JS

- **Context:** Need a polished web UI, built and maintained by one person.
- **Decision:** One `dashboard.py` that serves server-rendered HTML with vanilla JS talking to a small JSON API.
- **Alternatives considered:** A React/Vue SPA with a separate build step; Flask with Jinja templates in separate files.
- **Tradeoffs:** Everything-in-one-file hurts as it grows (it's already ~580 lines). **But** there's no build step, no `node_modules`, no framework to learn, and it deploys as plain Python. Vanilla JS keeps me close to the platform.
- **Concept it teaches:** Client-server split, REST endpoints, the **cost/benefit of frontend frameworks**, and recognizing technical debt.
- **Interview angle:** *"I deliberately avoided a SPA — no build pipeline for a two-page app. I can clearly name the tradeoff: the single file is getting large, and the refactor path is to split CSS/JS into static files or move to templates. I chose simplicity now and know exactly when I'd pay that debt down."*

---

## ADR-007 — Multiple independent processes, not one monolith or threads

- **Context:** Scraping (Selenium), a web server, and a bot have very different lifecycles and failure modes.
- **Decision:** Run them as **separate OS processes**.
- **Alternatives considered:** One process with threads; one giant async event loop.
- **Tradeoffs:** Processes use more memory and can't share objects directly (they coordinate through JSON files). **But** they give true **fault isolation** (a Selenium segfault can't kill the bot), sidestep Python's GIL for CPU work, and can be restarted independently.
- **Concept it teaches:** Processes vs threads, the **GIL**, fault isolation, and inter-process coordination via a shared store.
- **Interview angle:** *"I split by failure domain. Selenium is the flaky part, so I isolated it — if it dies, the website and bot keep serving. They don't share memory; they integrate through the JSON store, like services sharing a database."*

---

## ADR-008 — A subprocess supervisor (`run_all.py`) with auto-restart + backoff

- **Context:** Those processes must run forever; crashes are expected, not exceptional.
- **Decision:** A small Python supervisor that launches each child, watches it, and restarts it on exit with **exponential backoff**.
- **Alternatives considered:** (a) systemd only — great on Linux, but not cross-platform and needs one unit per process; (b) Celery/Redis — a task-queue, wrong abstraction for "keep daemons alive"; (c) `supervisord` — solid, but an extra dependency to learn; (d) Kubernetes — absurd overkill.
- **Tradeoffs:** I reimplemented a slice of what process managers do. **But** it's ~100 readable lines, cross-platform, dependency-free, and teaches the concept directly. In production it runs *under* Docker/systemd too (defense in depth).
- **Concept it teaches:** **Supervision trees** (the Erlang/OTP and Kubernetes "restart the pod" idea), backoff strategies, the difference between "process died" and "process is wedged".
- **Interview angle:** *"It's a tiny supervisor: spawn, monitor, restart with backoff so a crash-looping child doesn't hammer the CPU. It's the same principle as a Kubernetes ReplicaSet or Erlang's supervisor — keep the desired processes alive. For real production I also wrap it in systemd/Docker `restart: always`, so there are two layers."*

---

## ADR-009 — Docker + docker-compose for deployment

- **Context:** Needs to run on a cheap server, reliably, including a headless browser.
- **Decision:** A `Dockerfile` with Chromium baked in, orchestrated by `docker-compose.yml` with `restart: unless-stopped` and volume-mounted data.
- **Alternatives considered:** Bare-metal `pip install` + systemd (also provided as an option); a PaaS like Heroku/Render (awkward for a long-running browser + multiple processes).
- **Tradeoffs:** Docker adds an image build and some indirection. **But** it makes the environment **reproducible** ("works on my machine" → "works everywhere"), bundles the exact Chromium version, isolates dependencies, and restarts on reboot.
- **Concept it teaches:** **Containerization**, image layers, environment reproducibility, volumes for persistence, the build-vs-run distinction.
- **Interview angle:** *"The hard part of deploying a scraper is the browser. Docker lets me pin Chromium + the driver into the image so the environment is identical everywhere. Data and the Facebook session are volumes, so rebuilds don't wipe state. I also documented a no-Docker systemd path for a plain VPS."*

---

## ADR-010 — Secrets in `.env`, config in `settings.json` (12-Factor)

- **Context:** The Telegram token must not be committed; preferences must be editable without redeploying.
- **Decision:** Secrets come from environment variables (loaded from a git-ignored `.env`); behavior lives in `settings.json` (editable live from the dashboard). A tiny `app_env.secret()` helper reads env first, then falls back to settings.
- **Alternatives considered:** Hardcoding (insecure); a cloud secrets manager (overkill for one server).
- **Tradeoffs:** Two places to look (env vs settings). **But** it cleanly separates *secret* from *config* from *code*.
- **Concept it teaches:** The **12-Factor App** "config in the environment" rule; why secrets never go in source control; precedence/override patterns.
- **Interview angle:** *"Following 12-Factor, secrets live in the environment and never in git. The token can be rotated by changing one env var — no code change, no redeploy."*

---

## ADR-011 — MD5 content hashing for stable IDs and deduplication

- **Context:** The same post appears across runs and across multiple groups; Facebook gives no stable post ID we can read.
- **Decision:** Derive a deterministic ID by hashing the post URL or its text (`stable_id`), and dedupe with MD5 fingerprints of normalized text (intra-group, cross-group, and "seen" sets).
- **Alternatives considered:** Python's built-in `hash()` — **rejected**, because it's randomized per process run (we even left a comment warning about this); storing full text as the key (wasteful, fragile).
- **Tradeoffs:** MD5 is cryptographically broken — irrelevant here; we use it as a fast, stable *content fingerprint*, not for security.
- **Concept it teaches:** **Hashing for identity/dedup**, determinism across runs, idempotency, and that "cryptographically weak" ≠ "useless for fingerprinting".
- **Interview angle:** *"I needed stable IDs without a real primary key. Hashing the content gives a deterministic fingerprint, so the same post maps to the same ID every run — that's what makes 'don't alert twice' work. I specifically avoided Python's `hash()` because it's salted per process."*

---

## ADR-012 — Polling on a schedule (not event-driven)

- **Context:** New listings appear unpredictably; the sources don't push to us.
- **Decision:** Each agent polls its sources on a configurable interval using the `schedule` library in a loop.
- **Alternatives considered:** Event-driven/webhooks (the sources don't offer them); a message queue (nothing to queue from).
- **Tradeoffs:** Polling has latency (you find a listing up to one interval late) and does redundant work. **But** it's the only option when the source can't notify you, and it's dead simple.
- **Concept it teaches:** **Polling vs event-driven** architectures, latency/cost tradeoffs, and respectful scraping cadence (don't hammer the site).
- **Interview angle:** *"Polling is a deliberate choice forced by the sources — they can't push to me. I tuned intervals to balance freshness against being a good citizen and avoiding bot-detection. If a source offered webhooks, I'd switch that source to event-driven."*

---

## ADR-013 — Force UTF-8 output (a real bug I found and fixed)

- **Context:** On Windows, when the supervisor redirects a child's output to a log file, the default encoding is cp1255. Printing Hebrew (or a `→`) raised `UnicodeEncodeError` and **crashed the process on startup** — which the supervisor would then restart-loop forever.
- **Decision:** Reconfigure `stdout`/`stderr` to UTF-8 at startup (centralized in `app_env.py`), and pass `PYTHONUTF8=1` to child processes from the supervisor (defense in depth).
- **Alternatives considered:** Stripping non-ASCII from logs (loses information); ignoring it (the deployment literally doesn't run).
- **Tradeoffs:** None meaningful — UTF-8 everywhere is the correct modern default.
- **Concept it teaches:** **Text encoding & Unicode**, the difference between a terminal and a redirected file, and platform-specific defaults — a classic real-world bug.
- **Interview angle:** *"My favorite bug in this project. It only appeared under deployment, not in the terminal, because a redirected file used Windows' legacy cp1255 encoding while the console didn't. The fix was forcing UTF-8 — but the lesson is that 'works in my terminal' and 'works when output is redirected' are different environments. That's the kind of thing that teaches you to test the real deployment path."*

---

## How to add a new ADR
When you make a real decision, copy the template:

```
## ADR-0XX — <short title>
- **Context:** what situation forced a choice?
- **Decision:** what did you choose?
- **Alternatives considered:** what else, and why not?
- **Tradeoffs:** what did you give up?
- **Concept it teaches:** the CS/engineering idea.
- **Interview angle:** the sentence you'd actually say.
```
