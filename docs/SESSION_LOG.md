# Session Log

---

## 2026-06-09 — Initial session (itay-lotan)

**What was built in this session:**

- Full apartment search agent stack from scratch
- `apartment_agent.py` — Yad2 + Homely scraper with Selenium
- `facebook_agent.py` — Facebook group scraper (8 dedicated שכונה ב groups)
- `telegram_bot.py` — full bot with commands + inline buttons
- `tips_agent.py` — daily tips from RSS + curated bank of 12 evergreen tips
- `dashboard.py` — Flask dashboard with:
  - Dot-grid beige background, dark green header
  - Live apartment cards with image zoom hover + rotation
  - Daily tip widget (green gradient card)
  - Archive panel (slide-in from left)
  - Settings drawer (slide-in from right)
  - Scan-now button with spinner + status feedback
  - Tips page with color-coded category badges
- `settings.json` — unified config for all agents
- MCP `magic` (21st.dev) installed in Claude config

**Key decisions made:**
- Yad2 skips street filter (neighborhood=39 already guarantees שכונה ב)
- Facebook dedicated groups skip location filter too
- Telegram is primary notification channel
- Flat JSON files instead of database (simpler, learnable)
- Design: warm earthy — dark forest green + beige dot-grid + white cards

**User profile:**
- Student, Beer Sheva
- Looking for 1.5–3.5 room apartment, max ₪4100/month
- Streets: ביאליק, שמעוני, הזז, יעקב כהן, טשרניחובסקי, מצדה, חז"ל, אבן גבירול, נסתר, למדן + surrounding
- Wants instant Telegram alerts
- Expiry: 2026-06-23

**Open at end of session:**
- Agents not yet deployed (run manually)
- User wants always-on hosting (~few dollars/month)
- Facebook login may need refresh

---

## 2026-06-09 — Session 2: Facebook debug + UI overhaul + docs

**Changed files:**
- `facebook_agent.py` — major rewrite
- `dashboard.py` — full UI redesign + scan_now endpoint
- `apartment_agent.py` — skip street filter for Yad2, expiry check
- `telegram_bot.py` — `/סרוק` command, better message format, link button
- `tips_agent.py` — new file, daily tips from RSS + 12 evergreen tips
- `settings.json` — added expiry_date, yad2_interval_minutes, fb_interval_minutes
- `CLAUDE.md` — created
- `docs/PROJECT_STATE.md` — created + updated
- `docs/SESSION_LOG.md` — created
- `.claude/commands/*.md` — 6 command files created

**What changed:**
- Facebook agent: stable IDs with `hashlib.md5` (was using `hash()` which changes every run)
- Facebook agent: `--debug` mode shows filter stats per group
- Facebook agent: `_dismiss_dialogs()` closes Facebook popups that block DOM
- Facebook agent: JS fallback extracts text blocks directly from DOM
- Facebook agent: 12 scrolls × 1.8s (was 6 × 1.2s)
- Dashboard: dot-grid beige background, dark green header, tip widget, archive panel, settings drawer
- Dashboard: `/api/scan_now` triggers live Yad2 scan with spinner feedback
- Yad2 agent: `skip_filter=True` — no street filter (neighborhood=39 = שכונה ב already)
- Tips: 15 seeded tips in tips.json

**What now works:**
- Facebook login confirmed working (`logged_in=True`)
- Filter stats visible per group in debug mode
- Telegram sends on find, `/סרוק` triggers immediate push

**Known issues:**
- Facebook DOM still returning 0-4 elements per group (should be 20-30)
- Dialog fix deployed but not yet confirmed effective — test pending
- Slash commands don't work in Claude Code desktop (use natural language instead)

**Next step:** Run `--debug` again after dialog fix, confirm DOM > 10 elements per group

---

## 2026-06-09 — Session 3: Facebook classifier rebuilt + scraping quality improved

**Changed files:**
- `facebook_agent.py` — major classifier rewrite + scraping improvements
- `test_classifier.py` — new file, 30 unit tests for the classifier

**What changed:**
- Replaced binary `is_relevant()` with 7-category `classify_post()` pipeline:
  `relevant_rental_apartment` / `maybe_relevant` / `room_or_roommate_listing` /
  `seeker_post` / `sale_post` / `over_budget` / `irrelevant`
- Only `relevant_rental_apartment` sent to Telegram; others saved or discarded
- Smarter seeker detection — only rejects specific seeker phrases, not every "מחפש"
- Roommate/sublet detection with STRONG_ROOMMATE override logic (סאבלט, מחליפה...)
- Room range filter: 2-4 rooms → relevant; outside range → maybe
- SERVICE_PATTERNS rejects tradespeople, furniture giveaways, group announcements
- First-15-words fast check for obvious seeker posts
- Cross-group dedup via MD5 of first 200 chars of preview
- Intra-group dedup upgraded to MD5 hash (was: 150-char string key)
- Dedicated שכונה ב groups: 18 scrolls; general groups: 10
- Minimum post length raised 40→60 chars (filters out comment/nav articles)
- Facebook UI noise ("לייק הוספת תגובה שיתוף") stripped in normalize_text()
- `score_rental_apartment()` now includes couple phrases: "דירת זוג", "לשני אנשים"
- Debug output shows all 7 category counts per group

**What now works:**
- "מחפשת דירת 4 חדרים... אשמח להצעות" → seeker_post (was: relevant)
- "מסבלטת את החדר... מחפשת מחליפה" → room_or_roommate (was: relevant)
- "מחפשות שותפה לדירת 4 חדרים" → room_or_roommate (was: relevant)
- "שיפוצניק זמין" → irrelevant (was: could pass)
- "5 חדרים" → maybe_relevant (not sent to Telegram)
- 7 relevant posts found and sent in last debug run, all high quality
- All 8 Facebook groups active and contributing

**Known issues:**
- Facebook post URLs still not extractable (DOM only has /user/ links) — group URL used as fallback
- Some groups return only 2-5 posts per run (Facebook DOM limitation)
- Agents still run manually — no always-on hosting

**Next step:** Set up VPS hosting before expiry date (2026-06-23) to keep agents running 24/7.

---
<!-- Add new entries below this line -->
