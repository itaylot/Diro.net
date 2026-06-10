# Project State — דירונט
Last updated: 2026-06-09

## Status
🟢 **Functional locally — Facebook classifier fully rebuilt, scraping stable**
- Dashboard runs locally on port 5050
- Agents run manually per session
- Telegram bot working
- Facebook scraping returns 2-5 real posts per group, classifier working well

## What Works
- ✅ Yad2 scraping (Selenium headless + requests fallback in dashboard)
- ✅ Facebook group scraping — all 8 groups active, login confirmed working
- ✅ Telegram notifications with inline buttons (keep/dismiss) + `/סרוק` command
- ✅ Dashboard with apartment cards, archive panel, settings drawer, tips page
- ✅ Daily tips widget (15 evergreen tips seeded)
- ✅ Expiry date — agents auto-stop after `expiry_date` (2026-06-23)
- ✅ `scan_now` API endpoint scans Yad2 via requests (fast, no Selenium)
- ✅ Street filter skipped for Yad2 (neighborhood=39 already guarantees שכונה ב)
- ✅ Stable post IDs using `hashlib.md5`
- ✅ `--debug` mode shows per-group stats with full classification breakdown
- ✅ **Multi-stage classification pipeline** with 7 categories
- ✅ **Seeker posts** correctly rejected (מחפש דירה, זוג מחפש, נשמח לשמוע...)
- ✅ **Roommate/sublet posts** correctly rejected (שותפים, סאבלט, מחליפה...)
- ✅ **Sale posts** correctly rejected
- ✅ **Service/off-topic posts** correctly rejected (שיפוצניק, ניקיון, הודעות קבוצה...)
- ✅ **Room range filter** — only 2-4 rooms sent to Telegram; 1/5+ rooms → maybe
- ✅ **Cross-group dedup** — same post from multiple groups counted once
- ✅ **Intra-group dedup** — MD5 hash dedup catches near-duplicate text
- ✅ **Dedicated שכונה ב groups** get 18 scrolls; general groups get 10
- ✅ `test_classifier.py` — 30/30 unit tests passing (no Selenium needed)

## Known Problems
- ⚠️ Facebook post URLs not extractable — links in DOM are only `/user/` profile links.
  Dashboard and Telegram link to the group page, not the specific post.
- ⚠️ Some groups still return only 2-5 posts per run (Facebook DOM limitation).
  Strategy 1 (role=article) catches comments/nav as short articles (filtered by 60-char min).
- ⚠️ All agents need to be started manually each time (no auto-start / hosting)
- ⚠️ Yad2 may return captcha occasionally
- ⚠️ Expiry date: 2026-06-23 (2 weeks away — need VPS or extension soon)

## Architecture
```
settings.json ──── all agents read this
     │
     ├── apartment_agent.py   →  all_listings.json + Telegram
     ├── facebook_agent.py    →  all_listings.json + Telegram
     │     classify_post()    →  7-category pipeline
     │     test_classifier.py →  30 unit tests
     ├── telegram_bot.py      →  reads all_listings.json
     ├── tips_agent.py        →  tips.json
     └── dashboard.py         →  Flask API serving all JSON files
```

## Useful Commands
```bash
python facebook_agent.py --login   # first-time / re-login
python facebook_agent.py --debug   # visible Chrome + full classification stats
python test_classifier.py          # unit tests — no Selenium needed
python dashboard.py                # http://localhost:5050
python facebook_agent.py
python apartment_agent.py
python telegram_bot.py
python tips_agent.py
```

## Current Priority
**Deploy to always-on hosting** — expiry date is 2026-06-23, agents still run manually.
VPS (~$6/month on Hetzner/DigitalOcean/Oracle Free) would keep agents running 24/7.

## Next Recommended Step
1. Set up VPS or extend expiry date in settings.json
2. Deploy all agents with `screen` or `systemd` for always-on operation
3. Optional: add `maybe_relevant_rental_apartment` tab to dashboard for manual review
