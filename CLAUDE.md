# מצאן — Apartment Search Agent

## Product Goal
Automatically find rental apartments in **שכונה ב׳, Beer Sheva** and notify the user instantly via Telegram and a local web dashboard.

## Main Components

| File | Role |
|------|------|
| `apartment_agent.py` | Scans Yad2 + Homely via Selenium, sends Telegram alerts |
| `facebook_agent.py` | Scans Facebook groups every 30 min via Selenium |
| `telegram_bot.py` | Telegram bot — alerts + commands (`/סרוק`, `/stop`, `/status`) |
| `tips_agent.py` | Fetches daily apartment-search tips, saves to `tips.json` |
| `dashboard.py` | Flask web dashboard on port 5050 |
| `settings.json` | Single config file for all agents |

## Data Files
- `all_listings.json` — all found listings (shown in dashboard)
- `dismissed.json` — user-dismissed listing IDs
- `seen_listings.json` — Yad2 seen IDs (prevent re-alerting)
- `seen_fb_posts.json` — Facebook seen post IDs
- `tips.json` — daily tips
- `fb_chrome_profile/` — saved Chrome login for Facebook

## Key Settings (settings.json)
- `fb_interval_minutes: 30` — Facebook scan frequency
- `yad2_interval_minutes: 400` — Yad2 scan frequency (user preference)
- `max_price: 4100`, `min_rooms: 1.5`, `max_rooms: 3.5`
- `expiry_date: 2026-06-23` — agent auto-stops after this date
- `allowed_streets` — used only for Facebook general groups (NOT for Yad2 — Yad2 already uses neighborhood=39)

## Architecture Decision: Street Filter
Yad2 uses `neighborhood=39` which IS שכונה ב, so `is_allowed_street()` uses `skip_filter=True` for Yad2. Street filter only applies to general Beer Sheva Facebook groups.

## Working Style
- All Python, no frameworks beyond Flask + Selenium
- Config-driven via settings.json
- Dashboard is a single Flask file with inline HTML/CSS/JS
- No database — flat JSON files
- Telegram is the primary notification channel

## Run Order
```
python tips_agent.py       # once daily
python facebook_agent.py   # every 30 min
python apartment_agent.py  # every 400 min (user-set)
python telegram_bot.py     # always on
python dashboard.py        # always on (port 5050)
```

## Slash Commands (type these in chat)

| Command | Usage |
|---------|-------|
| `/start-session` | טוען הקשר, מסכם מצב — תמיד תתחיל כאן אחרי /clear |
| `/wrapup` | מעדכן PROJECT_STATE + SESSION_LOG בסוף session |
| `/next-step` | מציע את הצעד הבא, מחכה לאישור |
| `/fix-bug <תיאור>` | מתקן באג ספציפי, שינוי מינימלי |
| `/ui-polish <מה>` | משפר UI בלבד, לא נוגע בלוגיקה |
| `/safe-commit` | בודק diff ומציע commit message |

> הפקודות נמצאות ב- `.claude/commands/`

## Rules for Future Sessions
1. Don't change the street filter behavior for Yad2
2. Don't add npm/React/databases — keep it pure Python + vanilla JS
3. The user wants Telegram notifications to be fast and clear
4. Design direction: warm earthy (dark green header, beige dot-grid background, white cards)
5. The user is learning — keep code readable and well-commented
