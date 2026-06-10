# 🎤 Interview Guide — Talking About מצאן

> Goal: by the end you can say, truthfully, *"I built this system, I understand how it works, and I can explain the major engineering decisions behind it."*

This guide gives you the pitch, the story, the likely questions, and — importantly — the **honest weaknesses** to volunteer. Admitting tradeoffs is what separates a junior who memorized buzzwords from an engineer who understands them.

---

## 1. The 30-second pitch

> *"מצאן is an apartment-hunting agent I built for my own move. It monitors Yad2 and Facebook groups, classifies each listing with a rule-based engine to filter out spam, roommates, and sales, and pushes only relevant matches to Telegram in real time — with a web dashboard for triage. It's deployed 24/7 in Docker. I built it to be simple enough that one person can own and explain every part."*

## 2. The 2-minute version (STAR)

- **Situation:** My girlfriend and I were searching for a rental in a specific Beer Sheva neighborhood. The good listings vanish in hours and 90% of group posts are irrelevant.
- **Task:** Get notified of *only* relevant apartments, instantly, without manually scanning Facebook all day.
- **Action:** I built a small distributed system — independent scraper processes feeding a deterministic classifier, a JSON store, a Telegram bot, and a Flask dashboard, all kept alive by a supervisor and deployed in Docker.
- **Result:** Real-time alerts with a match score and the reasons each listing matched, plus a dashboard to triage. I went from a local script to a deployed product, and I can explain every architectural decision and its alternatives.

---

## 3. The questions you'll likely get (with strong answers)

**"Why not just use a database?"**
> *"At tens of listings a week with one user, a database is over-engineering. JSON files are zero-setup, debuggable, and trivially backed up. I know the limitation — read-modify-write on a file isn't concurrency-safe — and my migration path is SQLite, which only touches the persistence functions because I isolated reads/writes."* (ADR-003)

**"Why rules instead of machine learning / an LLM?"**
> *"No labeled training data — that's the cold-start problem. And I wanted explainability: the classifier returns the exact reasons it kept or rejected each post, which I show in the UI. An LLM would add cost, latency, and non-determinism for a narrow domain that rules handle well. I tuned thresholds toward precision because spam costs the user more than a marginal miss."* (ADR-004)

**"How do you avoid sending the same alert twice?"**
> *"Idempotency via 'seen' sets. Each post gets a deterministic ID by hashing its content, and a `sent_telegram.json` set records what's been sent. Sending is guarded by a membership check, so it's effectively exactly-once."* (ADR-011)

**"What happens when the scraper crashes?"**
> *"It's isolated in its own process, so it can't take down the website or bot. A supervisor restarts it with exponential backoff. In production that's wrapped in Docker `restart: unless-stopped` too — two layers of resilience."* (ADR-007, ADR-008)

**"How is it deployed?"**
> *"Docker, with Chromium baked into the image so the environment is reproducible — the browser is the tricky dependency. Data and the Facebook session are volumes so rebuilds don't wipe state. Secrets are in environment variables, never in git. I also wrote a systemd path for a plain VPS."* (ADR-009, ADR-010)

**"What was the hardest bug?"**
> *"A Unicode one. Hebrew output crashed only under deployment, because the supervisor redirected logs to a file using Windows' legacy cp1255 encoding, while my terminal used UTF-8. Forcing UTF-8 fixed it — the lesson was that 'works in my terminal' and 'works when redirected' are different environments."* (ADR-013)

**"How would you scale it to thousands of users / cities?"**
> *"Several changes: move JSON → a real database (SQLite then Postgres) for concurrent writes and queries; introduce a task queue (e.g. Celery/Redis) so scraping jobs are distributed and retried; add per-user preference storage; and put the dashboard behind proper auth. The current design deliberately stops short of that because it's a single-user tool — but the process/store separation means each piece can be swapped independently."*

**"What's the system's biggest weakness?"** (see §4 — answer honestly)

---

## 4. Honest weaknesses to volunteer (this builds credibility)

1. **JSON concurrency:** read-modify-write of whole files can race under concurrent writers. Fine at this scale; SQLite is the fix.
2. **Scraping fragility & ToS:** the scrapers break when sites change their HTML, and automated scraping is against these platforms' terms. I mitigate breakage with fallback strategies and self-diagnostics, but an official API would be the right long-term answer.
3. **No dashboard authentication:** it's a personal tool; the URL is treated as private (and I recommend Tailscale/Caddy-auth in the deploy doc). I'd add real auth before exposing it.
4. **Single-file front-end:** `dashboard.py` is getting large; the clean refactor is to split static assets or move to templates.
5. **Classifier doesn't generalize:** rules are tuned for Hebrew + this domain. Porting to another market means re-tuning.

> Saying these *before* you're asked shows you understand your own system's limits — exactly what interviewers look for.

---

## 5. Concept → "where do I point on the whiteboard"

| If they ask about… | Point to… | Say… |
|--------------------|-----------|------|
| Concurrency | `run_all.py`, JSON store | "Separate processes; coordination via a shared store; I know the write-race limitation." |
| Data modeling | `all_listings.json` schema | "Each listing carries classification, score, reasons, timestamp — designed for the UI." |
| Algorithms | `classify_post`, `stable_id` | "Scoring pipeline + content hashing for identity." |
| Systems design | the whole diagram | "Writers and readers decoupled through a store — the same shape as services sharing a DB." |
| Testing | `test_classifier.py` | "Pure function → 46 unit tests, no browser needed." |
| DevOps | `Dockerfile`, compose, systemd | "Reproducible env, restart policies, secrets in env." |

---

## 6. A learning path to truly own this code

Work through it in this order; after each step you'll understand one more subsystem deeply:

1. **Read `test_classifier.py`, then `classify_post`.** Change a rule, watch a test fail. This is the brain.
2. **Trace one listing** through `scrape_group` → `save_to_all_listings` → `send_telegram`. Add a `print` and follow it.
3. **Read the dashboard's API routes** (`/api/listings`, `/api/dismiss`) and the JS `render()`/`card()` to see request → response → DOM.
4. **Read `run_all.py`.** Kill a child process manually and watch it restart.
5. **Do one deploy** (Docker locally). Break it on purpose (wrong token) and read the logs.
6. **Write one new ADR** for a change you make. That habit is the whole point.

When you can do all six unaided, you own it.

---

## 7. The five goals, and how this project serves each

| Goal | How it's served |
|------|-----------------|
| **Find an apartment** | Real-time relevant alerts + triage dashboard; precision-tuned filtering. |
| **Deployability** | Docker + systemd paths, supervisor, env secrets, deploy checklist (`DEPLOY.md`). |
| **Product quality** | Polished RTL dashboard with match scores, reasons, freshness, filters; clean Telegram alerts. |
| **Learning value** | This docs set: architecture, ADRs, and a learning path mapping every part to a CS concept. |
| **Resume value** | A deployed distributed system you can whiteboard and defend, with documented tradeoffs and honest limits. |
