# 🔬 Engineering Due-Diligence Audit — דירונט / DiroNet
Date: 2026-06-11 · Method: 3 parallel specialist sub-agents (backend, security+data, frontend) + lead synthesis.
Scope: architecture, code quality, tech debt, security, data model, reliability, scalability, deployment, testing, observability, UX/UI, mobile, performance, maintainability.

> **Context for severity:** personal project, single active user, no uptime/SLA, downtime acceptable. So "Critical" here means *data-loss / account-compromise / silently-wrong-results*, not "site down". Severity is weighted toward **correctness, security, and learning value**.

Each finding: **Severity · Impact · Risk · Solution · Effort** (S = hours, M = ½–1 day, L = multi-day).

---

## 🟥 CRITICAL

### F1 — Stored XSS: scraped/ingested text rendered unescaped into the DOM
- **Where:** `dashboard.py` `card()` (~l.651), `loadTipWidget`/`loadTips`, `renderArchive`, `renderG`. Fields `address/title/contact/preview/source/url/image` interpolated raw into `innerHTML`. (`trkCard` correctly uses `esc()` — proof the fix is trivial and just not applied.)
- **Impact:** A Facebook post (or anyone with the ingest token) embeds `<img onerror=…>` / `javascript:` URLs → JS runs in itay/neta's authenticated session: read favorites/tracking/settings, change config, force logout.
- **Risk:** **High likelihood** — the app's whole job is rendering attacker-controlled scraped Hebrew text. Blast radius: full account compromise of both users.
- **Solution:** Route every dynamic value through a hardened `esc()` (also escape `'` `` ` ``); validate `url`/`image` scheme (`^https?:`) before emitting; sanitize on ingest as defense-in-depth. Ideally build nodes via `textContent`.
- **Effort:** S–M

### F2 — Concurrent, non-atomic JSON writes → silent data loss + corruption + 500s
- **Where:** `all_listings.json` written by `quick_yad2_scan` thread, `/api/ingest`, `/api/add_listing`, `apartment_agent.save_all_listings`, `facebook_agent.save_to_all_listings`; also `favorites.json`, `tracking.json`, `seen_*`, `dismissed`, `sent_telegram`. All do read→mutate→`write_text(whole file)` with **no lock, no temp+rename**.
- **Impact:** Overlapping writes interleave (last-writer-wins drops listings). A reader can catch a half-written file → `json.JSONDecodeError` → `load_listings()` (uncaught) 500s the dashboard / crashes agents.
- **Risk:** **High** under the deployed multi-writer topology (server agents + dashboard scan + home-PC ingest). The correct atomic pattern already exists in exactly one place (`agent_status.set_status`: temp + `os.replace`).
- **Solution:** One shared storage helper: `threading.Lock` (in-process) + OS file lock (`filelock`/`fcntl`) + write-temp-then-`os.replace`. Wrap all loaders in try/except.
- **Effort:** M

### F3 — Selenium/Chrome leak → the 200+ zombie processes
- **Where:** `facebook_agent.main` creates one driver for the process lifetime (`run_once` reuses it); `finally: driver.quit()` only runs on clean exit. Compounded by: **supervisor backoff bug (F4)** and **expiry `SystemExit` restart loop (see F18)**.
- **Impact:** On any crash/restart (the designed path for flaky FB Selenium), Chrome + chromedriver children are orphaned. Each restart spawns a fresh Chrome → hundreds of zombies → RAM/PID exhaustion → OOM kills the dashboard/bot too.
- **Risk:** **High** — observed live (200+ zombies).
- **Solution:** Create+quit the driver **per scan cycle** in try/finally; `atexit`/SIGTERM handler; on startup `pkill -f chromedriver`. Fix F4.
- **Effort:** M

---

## 🟧 HIGH

### F4 — Supervisor backoff resets every loop → crash-loop protection defeated
- **Where:** `run_all.py` `supervise()` — `if ran > 60: backoff = 2`.
- **Impact:** A service that boots Chrome (>60s) then dies mid-scan resets backoff to 2s every time → restarts every ~2s forever, never escalating → drives F3's zombie explosion.
- **Risk:** High (Selenium startup > 60s is normal).
- **Solution:** Track consecutive failures separately; only reset backoff after a *sustained* healthy run (>300s + N good cycles); cap restarts per window then alert; add jitter.
- **Effort:** S–M

### F5 — `/api/ingest`: public, no schema validation, non-constant-time token
- **Where:** `dashboard.py` `api_ingest` (~l.840). Stores each posted dict verbatim into `all_listings.json`; token check uses `!=` (timing oracle); no size cap.
- **Impact:** Token holder/guesser can inject unlimited listings, overwrite by id, plant XSS (F1). A mistyped `rooms` string later crashes `listing_caption` (`:.1f`).
- **Risk:** Medium likelihood (single static shared secret, sent on every push), High blast radius (poisons the primary datastore).
- **Solution:** `hmac.compare_digest`; whitelist+coerce fields (price→int, rooms→float, cap lengths); bound list size; consider IP-allowlist the home PC.
- **Effort:** S–M

### F6 — Session cookie not hardened; 30-day sessions, no revocation
- **Where:** `dashboard.py` app init — no `SESSION_COOKIE_SECURE/SAMESITE`; `permanent_session_lifetime=30d`; `session.permanent=True`.
- **Impact:** Cookie can traverse plain HTTP (port 80 open, app binds 0.0.0.0). No way to invalidate a stolen cookie for a month; password change doesn't log out existing sessions.
- **Risk:** Medium; session hijack = full access.
- **Solution:** `SESSION_COOKIE_SECURE=True, HTTPONLY=True, SAMESITE="Lax"`; HSTS + 80→443 in Caddy; add a per-user session-version to enable global logout; shorten lifetime.
- **Effort:** S

### F7 — No CSRF protection on any state-changing endpoint
- **Where:** all POST/DELETE routes (`/api/favorite`, `/api/tracking`, `/api/settings`, `/api/dismiss`, `/api/scan_now`, `/api/settings/toggle`). No CSRF token anywhere.
- **Impact:** A hostile page visited while logged in can change settings, disable the agent, wipe tracking, trigger scans.
- **Risk:** Medium (30-day session widens the window).
- **Solution:** `Flask-WTF` CSRF or double-submit token / required custom header; drop the `request.form` fallback for JSON APIs; combine with `SameSite`.
- **Effort:** M

### F8 — No login rate-limiting / brute-force protection
- **Where:** `dashboard.py` `/login`; no limiter anywhere.
- **Impact:** Two human-chosen passwords, public login, unlimited attempts, no lockout/CAPTCHA.
- **Risk:** Medium-high for a public site.
- **Solution:** `flask-limiter` (e.g. 5/min/IP on `/login`), per-username backoff/lockout, enforce strong passwords in `set_password`; optionally an outer Caddy basic-auth/IP gate.
- **Effort:** M

### F9 — Flask dev server in production, binds 0.0.0.0, blocking in-request scan thread
- **Where:** `dashboard.py` `app.run(...)`; `quick_yad2_scan` does blocking network I/O + whole-file write in a thread.
- **Impact:** Dev server isn't robust/concurrent; a slow scan or large-file write blocks request handling.
- **Risk:** Medium.
- **Solution:** Run under `gunicorn`/`waitress` (Windows-friendly) with fixed workers; move scanning out of the request path. (Multi-worker makes F2 locking mandatory.)
- **Effort:** M

### F10 — Container runs as root; whole repo bind-mounted RW with secrets inside
- **Where:** `Dockerfile` (no `USER`); `docker-compose.yml` `.:/app`. Renders hostile content + runs Selenium on hostile pages as root, with `.env`/`users.json`/`.flask_secret` writable.
- **Impact:** A Chromium/Python RCE → root-in-container with write access to all secrets + code (can rewrite host files via the mount).
- **Risk:** Low-medium likelihood, very high blast radius.
- **Solution:** non-root `USER`; mount only data dirs (RW) and code RO; `cap_drop:[ALL]`, `no-new-privileges`, `read_only` where feasible; isolate Chromium.
- **Effort:** M

### F11 — `KeyError: 'id'` on a malformed listing aborts whole merge/send loops
- **Where:** `apartment_agent.save_all_listings`, `facebook_agent.save_to_all_listings`, `telegram_bot.load_all` consumers index `item["id"]` directly (ingest/scan guard, these don't).
- **Impact:** One id-less record (from a race or manual edit) drops the entire batch.
- **Risk:** Medium (rises with F2).
- **Solution:** `.get("id")` + skip falsy everywhere; one validated `load_listings()` that filters non-dict/id-less rows.
- **Effort:** S

### F12 — Broad `except Exception: pass` hides failures across the codebase
- **Where:** ~12 sites in `facebook_agent`, `apartment_agent`, `agent_status.set_status`, `app_tracking`, `app_auth`, dashboard scan loop.
- **Impact:** Selector drift, JSON corruption, disk-full status writes, network errors all silent → "0 results" or stale "scanning…" forever with no signal.
- **Risk:** High likelihood of masking a future regression.
- **Solution:** Log a one-line `logging.warning/exception` instead of silent pass; reserve true silence for cosmetic paths (UTF-8 reconfigure, dialog dismiss); add a "N consecutive failures" counter that surfaces.
- **Effort:** M

### F13 — Frontend: no error/offline/401 handling — silent stale data
- **Where:** `loadData` (no try/catch); `loadTracking`/`loadAgentStatus`/`toggleFav` swallow errors; 401 JSON parsed as data instead of redirecting.
- **Impact:** Dropped connectivity or expired session → frozen skeletons / stale board, user misses new apartments with no indication.
- **Risk:** Medium; the user *trusts* a stale screen.
- **Solution:** try/catch in `loadData`; on 401 → `/login`; offline banner retaining last-good data; distinct error empty-state.
- **Effort:** S

### F14 — Accessibility: missing alt text, emoji-only semantics, no focus/keyboard
- **Where:** card `<img alt="">`; price/source/match-badge are visual-only; clickable `<div>` stats/tip-widget not focusable; `outline:none`; star rating not keyboard-operable; badge meaning carried by color.
- **Impact:** Unusable with a screen reader; marginal contrast hurts the couple in sunlight.
- **Risk:** Medium (learning value high — accessibility is core engineering).
- **Solution:** real `alt` (address+price); `aria-hidden` on decorative emoji + `aria-label`/`aria-pressed` on toggles; convert clickable divs to `<button>`; `:focus-visible` rings; text alongside color on badges.
- **Effort:** M

---

## 🟨 MEDIUM

### F15 — Frontend polling: full refetch + full re-render every 60s (agent-status every 3s)
- **Impact:** Rebuilds the whole grid via `innerHTML` (kills scroll/selection, re-runs animations, re-creates observers) → mobile flicker/jank, battery/data drain; `me`/`settings` polled needlessly; 1200 status hits/hour/tab.
- **Risk:** Medium — the most visible daily annoyance.
- **Solution:** Poll only `listings`(+`tracking`); fetch `me`/`settings` once; diff-and-patch changed cards; pause on `document.hidden`; relax status to 5–10s.
- **Effort:** M

### F16 — No canonical listing schema across 4 producers
- **Impact:** Yad2/manual/FB/ingest emit different field sets; score/why/freshness silently vanish for some; ingest accepts any shape (feeds F1/F5).
- **Solution:** One `TypedDict`/dataclass + `normalize(listing)` applied by every producer and ingest; type-validate on write.
- **Effort:** M

### F17 — Duplicated Yad2 logic + divergent defaults; manual scan never marks "seen"
- **Where:** `dashboard.quick_yad2_scan` ≈ `apartment_agent.fetch_yad2` copy; defaults 1.5/3.5/4100 vs 2/3/3500; doesn't write `seen_listings.json`.
- **Impact:** Two sources of truth drift; "manual scan found N" recounts the same as new each time.
- **Solution:** Extract shared Yad2 parse fn + one constants dict.
- **Effort:** M

### F18 — Expiry `SystemExit` fights the supervisor → post-expiry restart churn
- **Where:** `run_once` raises `SystemExit` on expiry; supervisor restarts it (doesn't know "expired = stay down") → re-check → exit → loop, each booting Chrome.
- **Impact:** Guaranteed at expiry (2026-06-23) — zombie/restart churn.
- **Solution:** Supervisor treats a sentinel exit code / flag file as "do not restart"; or agents idle-sleep on expiry.
- **Effort:** S

### F19 — Classifier fragility: price `min()` bug, substring matching, duplicated phrase lists
- **Impact:** "פיקדון 1500, שכ\"ד 4000" → extracts 1500 → wrong over_budget gate + wrong Telegram alerts; short tokens (`דירת`) match inside words; phrase lists duplicated/overlapping.
- **Solution:** Prefer price nearest a rent keyword; word boundaries for short tokens; dedupe lists; grow the labeled test set.
- **Effort:** M

### F20 — Telegram send not idempotent; new Bot+event loop per scan
- **Impact:** Partial send (some `sent.add()` before a failure, `save_sent` never reached) → duplicate alerts next cycle or silently dropped sends.
- **Solution:** Persist `sent` in `finally`/incrementally; reuse one Bot/loop; make send idempotent.
- **Effort:** M

### F21 — Unbounded growth: `all_listings`, `seen_*`, `sent_telegram`, `dismissed`, `favorites`
- **Impact:** Never pruned; every scan loads+rewrites the whole (growing) file → slower writes, larger race windows; `/api/listings` ships the entire array to the browser each 60s poll.
- **Solution:** Retention policy (drop > N days unless tracked/favorited); paginate `/api/listings`; cap seen sets.
- **Effort:** S–M

### F22 — `dashboard.py` is a ~1020-line monolith; frontend is a 600-line string; no build/lint/test/cache
- **Impact:** No JS linting/testing/highlighting; full uncompressed payload re-sent every visit (no `Cache-Control`/ETag); render-blocking Google font; one typo breaks the whole template.
- **Solution:** Split `static/app.css` + `static/app.js` (Flask gives ETags free); later componentize; gzip; `font-display:swap` (already set).
- **Effort:** M (L for full componentization)

### F23 — Fake match `%` is misleading; `cmd_status` default mismatch
- **Impact:** "87%" is `clamp(40,99, score/18)` — decorative, not a real probability; erodes trust. Bot status shows 3700/3 defaults vs real 4100/3.5.
- **Solution:** Drop the % (keep the qualitative tier + reasons) or define a real scale; centralize defaults.
- **Effort:** S

### F24 — Inline `onclick`/`oninput` everywhere blocks a CSP (the best XSS defense)
- **Impact:** Can't apply a strict Content-Security-Policy without `unsafe-inline`; ids from untrusted `l.id` passed into handlers (compounds F1).
- **Solution:** Delegated `addEventListener` on the grid using `data-id`; then add a strict CSP header.
- **Effort:** L

### F25 — No backups; all state in one bind mount
- **Impact:** A bad write / `down -v` / disk failure loses passwords + the couple's tracking board, unrecoverable.
- **Solution:** Dedicated named volume + periodic off-box backup of data files and `caddy_data` (TLS certs).
- **Effort:** S

### F26 — Observability gaps (lead finding)
- **Impact:** `print()`-only logging, no structured logs, no `/healthz`, no uptime/metrics; status writes can silently fail (F12); no alert when a scraper returns 0 for N runs or when the bot dies.
- **Solution:** `logging` with levels to file; `/healthz` returning component freshness; a Telegram "scraper stuck / bot down" self-alert; surface scrape-health in the status board.
- **Effort:** M

### F27 — Testing gaps (lead finding)
- **Impact:** Only the classifier is tested (46 cases). No tests for `app_auth` (login/hash/favorites), `app_tracking` CRUD, `/api/ingest`, extraction (`extract_price/rooms`), or route auth. No integration tests, no CI.
- **Solution:** pytest suite for the pure/easily-testable units + a Flask test-client for routes (auth required, ingest token, XSS-escape regression); GitHub Actions CI running tests on push.
- **Effort:** M

### F28 — ToS/legal + FB-credential exposure (lead + sec)
- **Impact:** Yad2/Facebook prohibit automated scraping; FB may ban the account; the logged-in `fb_chrome_profile/` is a high-value secret sitting in a root-owned bind mount.
- **Solution:** Treat scraping as best-effort/decoupled; throttle; isolate+protect the FB profile; document the legal posture; prefer official feeds where possible.
- **Effort:** L (policy)

---

## 🟩 LOW (hygiene)

- **F29** `<path:lid>` converter allows arbitrary keys (no disk traversal, but a smell + junk-key growth) → use `<lid>` + validate id prefix. **S**
- **F30** Favorites reference deleted listings, never GC'd (invisible but persist) → snapshot data into the record or GC. **S**
- **F31** Brand/doc leftovers: `CLAUDE.md` still "מצאן"/old arch; JS `yad2_interval||40` vs settings `400` mismatch. **S**
- **F32** `.env` `$`-in-value footgun for Werkzeug hashes (`method$salt$hash`) under compose interpolation; remove unused `ITAY/NETA_HASH`. **S**
- **F33** `tips_agent`: `import re` inside loop, no `raise_for_status()`, no RSS dedup. **S**
- **F34** Manual listings render a dead "פתח" button when `url==""`; image host allow-list too narrow (rely on `onerror`). **S**
- **F35** No loading state on view switches; skeletons only on first load. **S**
- **F36** RTL/bidi: phone/URL/address mixing without `<bdi>`/`dir="auto"` can reorder digits → wrong call/navigation. **S**
- **F37** Toast renders behind the bottom nav on mobile; hamburger + bottom-nav duplicate the same 4 nav targets. **S**
- **F38** Requirements use `>=` (unpinned) → non-reproducible builds; no lint/format/type config. **S**

---

## 📊 Severity tally
Critical 3 · High 11 · Medium 14 · Low 10  =  **38 findings**

## 🧭 Cross-cutting themes (the real story)
1. **Trust boundary is unguarded.** The app ingests attacker-controlled text (FB posts, ingest) and renders it unescaped (F1, F5, F16, F24). This is the #1 theme.
2. **The flat-JSON datastore has no concurrency control** (F2, F11, F21) — fine for a single-process toy, wrong for the now-multi-writer deployment.
3. **Selenium lifecycle isn't guaranteed** (F3, F4, F18) — fully explains the zombies.
4. **Web-app security basics are absent** (F6, F7, F8, F9, F10) — expected for a prototype, essential now that it's public.
5. **No safety net** — thin tests (F27), swallowed errors + no observability (F12, F26), no backups (F25), no CI (F38).

---

# 🗺️ Prioritized Roadmap

**Phase 0 — Stop the bleeding (½–1 day)**
F1 escape XSS · F3+F4 driver-per-cycle + backoff fix · F2 atomic+locked writes · F11 id-safe loaders · F12 log instead of swallow (the worst sites).

**Phase 1 — Lock the doors (1–2 days)**
F6 cookie flags · F8 login rate-limit · F5 ingest hmac+validate · F7 CSRF · F10 non-root container + RO code mount · F13 frontend 401/offline handling.

**Phase 2 — Foundations & safety net (2–3 days)**
F27 tests (auth/tracking/ingest/extraction + route tests) · F38 CI + pinned deps · F26 logging + `/healthz` + stuck-scraper alert · F25 backups · F9 waitress/gunicorn.

**Phase 3 — Architecture & data model (2–4 days)**
F16 canonical listing schema + `normalize()` · F17 dedupe Yad2 logic · F21 retention/pruning + pagination · F2→ consider SQLite migration (resolves F2/F11/F21 structurally).

**Phase 4 — Frontend craftsmanship (3–5 days)**
F22 split static assets + cache · F15 smart polling + diff-render · F14 accessibility · F24 delegated handlers + CSP · F23 honest match score · F11/F37 mobile/RTL polish.

**Phase 5 — Domain quality (ongoing)**
F19 classifier robustness + bigger labeled set · F20 idempotent Telegram · F18 expiry handling · the Low-severity hygiene batch.

---

# 🎯 The 20% that delivers 80% of the value

If you only do six things, do these — they kill the three critical themes plus the worst security gaps, and each teaches a core concept:

1. **F1 — Escape all rendered scraped text** (XSS). *S–M.* Teaches: trust boundaries, output encoding, why the same data is safe in one function and lethal in another.
2. **F2 — One locked, atomic storage helper** (temp+`os.replace`+lock) for every JSON file. *M.* Teaches: atomicity, race conditions, the read-modify-write trap — your single biggest data-integrity win.
3. **F3+F4 — Per-cycle Selenium lifecycle + real backoff.** *M.* Teaches: resource lifecycle, supervision/backoff — eliminates the zombie storm.
4. **F6+F8 — Cookie hardening + login rate-limit.** *S–M.* Teaches: web-auth fundamentals; closes the cheapest real attack.
5. **F27+F38 — A real test suite + CI on push.** *M.* Teaches: the safety net that makes *all* future refactors safe — the highest *learning* leverage item.
6. **F26+F12 — Logging + `/healthz` + stop swallowing errors.** *M.* Teaches: observability; turns "silently broken" into "visibly broken," which makes everything else debuggable.

> Notably, **F1, F2, F3, F27** alone resolve or de-risk ~20 of the 38 findings (the XSS family, the concurrency family, the Selenium family, and the no-tests family). Start there.

---

*No code has been changed for this audit. Implementation begins only on your go — recommended order: the six 80/20 items, top-to-bottom.*
