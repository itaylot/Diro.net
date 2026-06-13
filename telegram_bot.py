"""
Telegram Bot — Apartment Notifications
Sends new listings with inline buttons. Supports /סרוק for on-demand scan.

Commands:
  /start   — connect chat
  /סרוק    — scan NOW and send any new listings
  /list    — show active listings
  /stop    — pause agent
  /resume  — resume agent
  /status  — agent status
"""

import app_env  # noqa: F401 — UTF-8 stdout + .env (must be first)
import asyncio
import logging
from pathlib import Path

import storage

from telegram import (
    Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update,
)
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes,
    MessageHandler, filters,
)
from telegram.error import TelegramError
from telegram.constants import ParseMode

logging.basicConfig(level=logging.WARNING)

ROOT           = Path(__file__).parent
SETTINGS_FILE  = ROOT / "settings.json"
ALL_FILE       = ROOT / "all_listings.json"
DISMISSED_FILE = ROOT / "dismissed.json"
SENT_FILE      = ROOT / "sent_telegram.json"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def load_settings() -> dict:
    return storage.read_json(SETTINGS_FILE, {})

def save_settings(s: dict):
    storage.write_json(SETTINGS_FILE, s)

def load_all() -> list[dict]:
    return storage.read_json(ALL_FILE, [])

def load_dismissed() -> set:
    return set(storage.read_json(DISMISSED_FILE, []))

def load_sent() -> set:
    return set(storage.read_json(SENT_FILE, []))


# ─── Match score + reasons + freshness helpers ────────────────────────────────

def match_level(score: int) -> tuple[str, str, int]:
    """Map the raw classifier score to (emoji, label, 0-100 percentage)."""
    pct = max(40, min(99, round((score / 18) * 100)))
    if score >= 12:
        return "🔥", "התאמה מצוינת", pct
    if score >= 8:
        return "✅", "התאמה טובה", pct
    return "🟡", "שווה בדיקה", pct


# Translate machine reason tags into short human Hebrew phrases.
_REASON_HE = {
    "rental_keyword": "מודעת השכרה",
    "availability_keyword": "כניסה/זמינה",
    "dedicated_group": "קבוצת שכונה ב׳",
    "date_found": "תאריך כניסה",
    "suitable_for_couple": "מתאים לזוג",
    "studio_or_unit": "יחידת דיור",
}

def reasons_he(reasons: list) -> str:
    """Build a short 'why it matched' line from the reason tags."""
    out = []
    for r in reasons or []:
        if r.startswith("location:"):
            out.append(f"מיקום: {r.split(':',1)[1]}")
        elif r.startswith("price:"):
            continue  # price already shown prominently
        elif r.startswith("rooms:"):
            continue  # rooms already shown in details
        elif r in _REASON_HE:
            out.append(_REASON_HE[r])
    # de-dup, keep order, cap to 4
    seen, uniq = set(), []
    for x in out:
        if x not in seen:
            seen.add(x); uniq.append(x)
    return " · ".join(uniq[:4])


def freshness_he(found_at: str) -> str:
    """Human 'how fresh' label from a 'YYYY-MM-DD HH:MM' timestamp."""
    if not found_at:
        return ""
    try:
        from datetime import datetime
        dt = datetime.strptime(found_at, "%Y-%m-%d %H:%M")
        mins = (datetime.now() - dt).total_seconds() / 60
        if mins < 60:
            return f"לפני {int(mins)} דק׳"
        if mins < 24 * 60:
            return f"לפני {int(mins // 60)} שעות"
        return f"לפני {int(mins // 1440)} ימים"
    except Exception:
        return ""


# ─── Message formatting ───────────────────────────────────────────────────────

def listing_caption(lst: dict) -> str:
    src   = lst.get("source", "")
    lines = []

    # ── Header: match level + freshness ──
    score = lst.get("score", 0) or 0
    if score:
        emoji, label, pct = match_level(score)
        fresh = freshness_he(lst.get("found_at", ""))
        head = f"{emoji} *{label} · {pct}%*"
        if fresh:
            head += f"   🕒 {fresh}"
        lines.append(head)

    # Source line
    icon = "📘" if "Facebook" in src else "🏠"
    src_short = src.split("—")[0].strip()
    lines.append(f"{icon} *{src_short}*")

    # Address
    addr = lst.get("address", "")
    if addr:
        lines.append(f"📍 {addr}")

    # Why it matched
    why = reasons_he(lst.get("reasons", []))
    if why:
        lines.append(f"🎯 {why}")

    # Preview
    preview = lst.get("preview", "")
    if preview:
        safe = preview[:280].replace("*","").replace("_","").replace("`","")
        lines.append(f"\n_{safe}_")

    # Details
    details = []
    if lst.get("rooms"): details.append(f"🛏 {lst['rooms']:.1f} חדרים".replace(".0 ","  "))
    if lst.get("size"):  details.append(f"📐 {lst['size']} מ\"ר")
    if lst.get("floor"): details.append(f"🏢 קומה {lst['floor']}")
    if details:
        lines.append("  ".join(details))

    # Contact (if extracted)
    if lst.get("contact"):
        lines.append(f"👤 {lst['contact']}")

    # Price — big and clear
    price = lst.get("price", 0)
    lines.append("")
    if price:
        lines.append(f"💰 *₪{price:,} לחודש*")
    else:
        lines.append("💰 _מחיר לא צוין_")

    return "\n".join(lines)


def listing_keyboard(lst: dict) -> InlineKeyboardMarkup:
    url = lst.get("url", "")
    lid = lst["id"]
    buttons = []

    # Row 1: open link (if available)
    if url:
        buttons.append([InlineKeyboardButton("🔗 פתח מודעה", url=url)])

    # Row 2: keep / dismiss
    buttons.append([
        InlineKeyboardButton("✅ מעניין",  callback_data=f"keep_{lid}"),
        InlineKeyboardButton("❌ לא רלוונטי", callback_data=f"dismiss_{lid}"),
    ])

    return InlineKeyboardMarkup(buttons)


# ─── Send one listing ─────────────────────────────────────────────────────────

async def send_listing(bot: Bot, chat_id: str, lst: dict):
    caption  = listing_caption(lst)
    keyboard = listing_keyboard(lst)
    image    = lst.get("image", "")

    try:
        if image and ("img.yad2.co.il/Pic/" in image or "scontent" in image):
            await bot.send_photo(
                chat_id=chat_id,
                photo=image,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard,
            )
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
    except TelegramError:
        # fallback without image / without markdown
        try:
            plain = caption.replace("*", "").replace("_", "")
            await bot.send_message(
                chat_id=chat_id,
                text=plain,
                reply_markup=keyboard,
            )
        except Exception:
            pass


async def push_new_listings(bot: Bot, chat_id: str) -> int:
    """Send all unsent, non-dismissed listings. Returns count sent."""
    dismissed = load_dismissed()
    sent      = load_sent()
    listings  = load_all()

    # Only push clearly relevant apartments — don't spam maybe/over_budget via /סרוק
    new = [
        l for l in listings
        if l["id"] not in dismissed
        and l["id"] not in sent
        and l.get("classification", "relevant_rental_apartment") == "relevant_rental_apartment"
    ]
    if not new:
        return 0

    for lst in new:
        await send_listing(bot, chat_id, lst)
        await asyncio.sleep(0.5)

    # apartment_agent also writes sent_telegram.json — union under a lock so
    # neither process clobbers the other's newly-sent IDs.
    new_ids = {lst["id"] for lst in new}
    storage.update_json(SENT_FILE, lambda ids: list(set(ids) | new_ids), [])
    return len(new)


# ─── Bot command handlers ─────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    s = load_settings()
    if not s.get("telegram_chat_id"):
        s["telegram_chat_id"] = chat_id
        save_settings(s)
        await update.message.reply_text(
            f"✅ *מחובר!* Chat ID: `{chat_id}`\n\n"
            "הבוט ישלח לך דירות חדשות אוטומטית.\n\n"
            "*פקודות:*\n"
            "/סרוק — סרוק עכשיו ושלח מודעות חדשות\n"
            "/list — רשימת דירות פעילות\n"
            "/stop — עצור סוכן\n"
            "/resume — הפעל מחדש\n"
            "/status — מצב הסוכן",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text(
            f"שלום! הבוט פעיל 🏠\nChat ID: `{chat_id}`",
            parse_mode=ParseMode.MARKDOWN,
        )


async def cmd_scan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Trigger immediate push of any pending listings."""
    s  = load_settings()
    cid = s.get("telegram_chat_id", str(update.effective_chat.id))
    bot = ctx.bot

    await update.message.reply_text("🔍 בודק מודעות חדשות...")

    n = await push_new_listings(bot, cid)
    if n:
        await update.message.reply_text(f"✅ נשלחו {n} מודעות חדשות!")
    else:
        await update.message.reply_text("אין מודעות חדשות כרגע 👀")


async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    dismissed = load_dismissed()
    listings  = load_all()
    active    = [l for l in listings if l["id"] not in dismissed]

    if not active:
        await update.message.reply_text("אין דירות פעילות כרגע 🔍")
        return

    await update.message.reply_text(
        f"🏠 *{len(active)} דירות פעילות — שכונה ב׳*",
        parse_mode=ParseMode.MARKDOWN,
    )
    for lst in active[:8]:
        try:
            await update.message.reply_text(
                listing_caption(lst),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=listing_keyboard(lst),
                disable_web_page_preview=True,
            )
            await asyncio.sleep(0.3)
        except Exception:
            pass

    if len(active) > 8:
        await update.message.reply_text(
            f"_(מוצגות 8 מתוך {len(active)} — פתח את הדשבורד לכולן)_",
            parse_mode=ParseMode.MARKDOWN,
        )


async def cmd_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    s = load_settings()
    s["enabled"] = False
    save_settings(s)
    await update.message.reply_text("⏸ הסוכן הושהה. /resume להפעלה מחדש.")


async def cmd_resume(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    s = load_settings()
    s["enabled"] = True
    save_settings(s)
    await update.message.reply_text("▶️ הסוכן פעיל שוב!")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    s         = load_settings()
    dismissed = load_dismissed()
    listings  = load_all()
    active    = len([l for l in listings if l["id"] not in dismissed])
    enabled   = "▶️ פעיל" if s.get("enabled", True) else "⏸ מושהה"
    fb_int    = s.get("fb_interval_minutes", 30)
    yad2_int  = s.get("yad2_interval_minutes", 40)
    expiry    = s.get("expiry_date", "לא הוגדר")

    await update.message.reply_text(
        f"*מצב הסוכן*\n\n"
        f"סטטוס: {enabled}\n"
        f"פייסבוק: כל {fb_int} דקות\n"
        f"Yad2: כל {yad2_int} דקות\n"
        f"דירות פעילות: {active}\n"
        f"מחיר מקסימלי: ₪{s.get('max_price',3700):,}\n"
        f"חדרים: {s.get('min_rooms',1.5)}–{s.get('max_rooms',3)}\n"
        f"פעיל עד: {expiry}",
        parse_mode=ParseMode.MARKDOWN,
    )


async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data or ""

    if data.startswith("dismiss_"):
        lid = data[len("dismiss_"):]
        # Locked read-modify-write: the dashboard writes this same file, so a
        # plain load→add→save could lose the other process's change.
        storage.update_json(DISMISSED_FILE, lambda ids: list(set(ids) | {lid}), [])
        try:
            await query.edit_message_reply_markup(
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🚫 הוסרה", callback_data="noop"),
                ]])
            )
        except Exception:
            pass

    elif data.startswith("keep_"):
        try:
            await query.edit_message_reply_markup(
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ שמורה", callback_data="noop"),
                ]])
            )
        except Exception:
            pass


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    from app_env import secret
    s = load_settings()
    token = secret("TELEGRAM_TOKEN", s.get("telegram_token", ""))
    if not token:
        print("⚠️  חסר telegram_token בקובץ settings.json")
        return

    print("=" * 50)
    print(" בוט Telegram — דירות שכונה ב׳")
    print(" שלח /start לבוט לחיבור ראשוני")
    print(" /סרוק — בדיקה מיידית")
    print("=" * 50)

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("scan",   cmd_scan))   # /scan
    app.add_handler(CommandHandler("list",   cmd_list))
    app.add_handler(CommandHandler("stop",   cmd_stop))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("status", cmd_status))
    # Telegram only allows ASCII command names, so /סרוק can't be a CommandHandler.
    # Catch it (and a few Hebrew words) as plain text instead.
    app.add_handler(MessageHandler(filters.Regex(r"^/?(סרוק|חפש|חיפוש)\s*$"), cmd_scan))
    app.add_handler(CallbackQueryHandler(on_callback))

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
