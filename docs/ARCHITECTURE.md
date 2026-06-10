# 🏗️ מצאן — Architecture & How It Works

> Purpose of this doc: so you can sit in an interview, draw the system on a whiteboard, and explain every box and arrow with confidence.

---

## 1. One-paragraph summary

מצאן is a small **distributed system of independent worker processes** that monitor apartment sources (Yad2, Homely, Facebook groups), run each listing through a **deterministic classifier**, store results in **flat JSON files**, and surface them through two **read interfaces**: a Flask **web dashboard** and a **Telegram bot**. A **supervisor process** keeps everything running 24/7. It is intentionally built from simple, industry-standard parts so it can be understood and owned by one person.

---

## 2. The architecture (whiteboard version)

```
                          settings.json  (config)        .env  (secrets)
                                │                           │
        ┌───────────────────────┼───────────────────────────┼───────────────┐
        │                       ▼                           ▼               │
   SOURCES              ┌──────────────────┐         ┌──────────────────┐    │
   (the web)            │ apartment_agent  │         │  facebook_agent  │    │
   Yad2 / Homely  ────► │  (Yad2+Homely)   │   ...   │ (FB groups, Sel.)│    │
   Facebook groups      └────────┬─────────┘         └────────┬─────────┘    │
                                 │ extract + classify          │             │
                                 ▼                             ▼             │
                        ┌─────────────────────────────────────────────┐     │
                        │              JSON "datastore"               │     │
                        │  all_listings.json  seen_*.json             │     │
                        │  dismissed.json     sent_telegram.json       │     │
                        └───────────┬───────────────────┬─────────────┘     │
                                    │ read              │ read              │
                          ┌─────────▼────────┐  ┌────────▼─────────┐         │
                          │   dashboard.py   │  │  telegram_bot.py │         │
                          │  (Flask web UI)  │  │  (bot + alerts)  │         │
                          └──────────────────┘  └──────────────────┘         │
                                                                             │
        run_all.py  ── supervises & auto-restarts all of the above ──────────┘
```

**Key property: the writers (agents) and readers (dashboard, bot) are decoupled through the JSON files.** They never call each other directly. This is the same idea as a database sitting between services — just simpler.

---

## 3. Data flow — the journey of one apartment

Follow a single Facebook post through the system. This is the story to tell in an interview:

1. **Detect** — `facebook_agent.py` opens a group (chronological sort), scrolls, and clicks "ראה עוד" to load full text (`_expand_see_more`).
2. **Extract** — pulls raw text from post containers (`scrape_group`), normalizes it (`normalize_text`).
3. **Deduplicate** — an MD5 hash of the text decides if we've seen this exact post (`stable_id`, `seen_texts`).
4. **Classify** — `classify_post()` runs a rule pipeline → returns `(classification, score, rooms, price, reasons)`.
5. **Persist** — kept listings are merged into `all_listings.json` (`save_to_all_listings`), with a `found_at` timestamp.
6. **Notify** — only `relevant_rental_apartment` items the user hasn't seen go to Telegram (`send_telegram`), and `sent_telegram.json` guarantees we never alert twice.
7. **Read** — `dashboard.py` and the bot read the JSON and present cards with score, reasons, and freshness.

> One sentence version: *"A post is detected, deduplicated, classified by rules, written to a JSON store, and read by two front-ends — with a 'seen' set ensuring each alert fires exactly once."*

---

## 4. Subsystem cards

Each card answers: **Why does it exist? What problem does it solve? What breaks if removed? What should I learn?**

### 4.1 The Scrapers (`facebook_agent.py`, `apartment_agent.py`)
- **Why it exists:** apartment listings live on third-party sites with no unified API. We must collect them ourselves.
- **Problem it solves:** turns messy, human-written web pages into structured records.
- **What breaks if removed:** no data enters the system — everything downstream is empty.
- **What to learn:** web scraping with Selenium, the DOM, dealing with dynamic/JS-rendered pages, and *defensive parsing* (the page can change shape any time, so we have 5 fallback strategies and self-diagnostics).

### 4.2 The Classifier (`classify_post` in `facebook_agent.py`)
- **Why it exists:** 90% of posts in these groups are NOT a couple's rental (roommates, sales, food ads, seekers).
- **Problem it solves:** decides relevance and *explains its reasoning* via a `reasons` list.
- **What breaks if removed:** the user drowns in spam; the product's core promise dies.
- **What to learn:** **deterministic rule-based classification**, building a scoring function, precision vs recall, and why explainability matters. This is the most interview-rich part of the project (see ADR-004).

### 4.3 The JSON Datastore (`*.json` files)
- **Why it exists:** the system needs to remember listings, what was seen, what was dismissed, what was sent.
- **Problem it solves:** persistence across restarts, and a shared contract between writers and readers.
- **What breaks if removed:** the system has amnesia — it re-alerts everything every cycle and the dashboard shows nothing.
- **What to learn:** serialization (JSON), the idea of a **datastore as an integration boundary**, idempotency via "seen" sets, and the *honest limitation*: concurrent read-modify-write on a file has race conditions (see ADR-003).

### 4.4 The Telegram Bot (`telegram_bot.py`)
- **Why it exists:** the user wants alerts pushed to their phone instantly, not to check a website.
- **Problem it solves:** real-time, zero-friction notification + lightweight interaction (keep/dismiss buttons, `/סרוק`).
- **What breaks if removed:** the product becomes pull-only; you'd have to remember to open the dashboard.
- **What to learn:** bot APIs, **long-polling vs webhooks**, async I/O (`async/await`), and idempotent sending.

### 4.5 The Web Dashboard (`dashboard.py`)
- **Why it exists:** a rich visual surface to browse, filter, and triage listings — and to show off the product.
- **Problem it solves:** human-friendly review with match scores, "why matched", filters, and archive.
- **What breaks if removed:** you lose the visual triage UI; Telegram alone is linear and limited.
- **What to learn:** HTTP, a tiny REST API (`/api/listings`, `/api/dismiss/...`), server-rendered HTML, and the tradeoff of a single-file front-end (see ADR-006).

### 4.6 The Supervisor (`run_all.py`)
- **Why it exists:** five separate processes must run forever; any one can crash (especially Selenium).
- **Problem it solves:** starts everything with one command and **auto-restarts crashed children** with backoff.
- **What breaks if removed:** you'd manually start 5 terminals and babysit them; one crash = silent data gap.
- **What to learn:** process management, **fault isolation**, supervision trees (the Erlang/Kubernetes idea), and exponential backoff. (See ADR-008.)

### 4.7 Config & Secrets (`settings.json`, `app_env.py`, `.env`)
- **Why it exists:** behavior (price, rooms, intervals, groups) and secrets (token) must change without editing code.
- **Problem it solves:** separates *configuration* from *code* and *secrets* from *source control*.
- **What breaks if removed:** you'd hardcode the token (security risk) and redeploy for every preference change.
- **What to learn:** the **12-Factor App** principle "config in the environment", and why secrets never belong in git.

### 4.8 The Test Suite (`test_classifier.py`)
- **Why it exists:** the classifier is the brain; changing it can silently break relevance.
- **Problem it solves:** locks in correct behavior with 46 labeled examples; catches regressions instantly.
- **What breaks if removed:** every classifier tweak becomes a gamble; you lose the safety net.
- **What to learn:** unit testing, **why pure functions are testable** (no Selenium needed — the classifier takes a string, returns a result), and test-driven safety.

---

## 5. CS concepts this project demonstrates (your talking-points map)

| Concept | Where it lives | One-line interview hook |
|---------|----------------|--------------------------|
| Separation of concerns | 5 single-purpose processes | "Each component does one thing; they integrate through a shared store." |
| Fault isolation & supervision | `run_all.py` | "A Selenium crash can't take down the website — separate processes, auto-restart." |
| Idempotency | `seen_*.json`, `sent_telegram.json` | "A 'seen' set makes notification effectively exactly-once." |
| Hashing for identity/dedup | `stable_id` (MD5) | "Stable content hashes give each post a deterministic ID across runs." |
| Determinism vs ML | `classify_post` | "I chose explainable rules over a black-box model — every decision has a reason." |
| Precision/recall tradeoff | scoring thresholds | "I tuned thresholds to favor precision so the user isn't spammed." |
| Config vs code (12-Factor) | `settings.json` + `.env` | "Behavior and secrets live outside the code." |
| Polling & scheduling | `schedule` loops | "Each agent polls on its own interval; I discussed event-driven as the alternative." |
| Text encoding / Unicode | `app_env` UTF-8 fix | "Hebrew + Windows cp1255 crashed on log redirect — a real Unicode bug I diagnosed and fixed." |
| Containerization | `Dockerfile`, compose | "Reproducible environment with Chromium baked in." |
| Testing pure functions | `test_classifier.py` | "The classifier is pure, so it's trivially unit-testable without a browser." |

See `DECISIONS.md` for the full reasoning behind each, and `INTERVIEW_GUIDE.md` for how to present it.
