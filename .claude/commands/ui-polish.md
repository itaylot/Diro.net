# UI Polish

Target: $ARGUMENTS

## Scope — what you may touch
- `dashboard.py` — HTML, CSS, and JavaScript inside `DASHBOARD_HTML`
- Visual design, layout, spacing, typography, colors, animations
- User-facing copy (button labels, empty states, tooltips)

## Scope — what you must NOT touch
- Any agent logic (`apartment_agent.py`, `facebook_agent.py`, `tips_agent.py`)
- Telegram bot logic (`telegram_bot.py`)
- Flask API routes in `dashboard.py` (the Python functions below `DASHBOARD_HTML`)
- `settings.json`
- Any `.json` data files

## Process

1. Read the target description carefully
2. Read the relevant section of `dashboard.py` (HTML/CSS/JS only)
3. Identify the specific elements to improve
4. Describe the planned changes before implementing
5. Make the change
6. Confirm what changed and how to verify it in the browser

## Design principles for this project
- Background: warm beige `#F2EDE4` with dot-grid texture
- Header: dark forest green gradient `#0D2B1A → #1A4A2E`
- Cards: white, `border-radius: 20px`, warm shadow, hover with slight rotation
- Font: Plus Jakarta Sans
- Primary action color: `#1A4A2E` (dark green)
- Keep animations subtle — no flashy effects
- RTL layout (Hebrew) — test that spacing/alignment works in RTL
