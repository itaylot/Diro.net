"""
Apartment Searching Agent - Beer Sheva, שכונה ב'
Reads all config from settings.json. Sends via Telegram + email.
"""

import app_env  # noqa: F401 — UTF-8 stdout + .env (must be first)
import asyncio
import json
import re
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import schedule
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from email_template import build_email_html

# ─── Configuration (overridden by settings.json at runtime) ──────────────────
EMAIL_RECIPIENT = "itayl1998@gmail.com"
EMAIL_SENDER    = ""
EMAIL_PASSWORD  = ""

SETTINGS_FILE  = Path(__file__).parent / "settings.json"
ALL_FILE       = Path(__file__).parent / "all_listings.json"
DISMISSED_FILE = Path(__file__).parent / "dismissed.json"
SENT_FILE      = Path(__file__).parent / "sent_telegram.json"

def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"enabled": True, "max_price": 3500, "min_rooms": 2, "max_rooms": 3,
            "run_times": ["10:00", "20:00"], "sources": {"yad2": True}}

SEEN_FILE = Path(__file__).parent / "seen_listings.json"

def is_allowed_street(address: str, cfg: dict, skip_filter: bool = False) -> bool:
    """Return True if address is on one of the allowed streets (or no filter set).
    skip_filter=True for Yad2/sources that already have neighborhood filter applied.
    """
    if skip_filter:
        return True  # neighborhood=39 already guarantees שכונה ב — no need for street filter
    streets = cfg.get("allowed_streets", [])
    if not streets:
        return True   # no filter — allow all
    addr_lower = address.replace('"', '').replace("'", '').lower()
    for street in streets:
        s = street.replace('"', '').replace("'", '').lower()
        if s in addr_lower:
            return True
    return False


def yad2_params(cfg: dict) -> dict:
    mn, mx, mp = cfg.get("min_rooms",2), cfg.get("max_rooms",3), cfg.get("max_price",3500)
    return {
        "topArea": 43, "area": 22, "city": 9000, "neighborhood": 39,
        "property": 1, "rooms": f"{mn}-{mx}", "price": f"0-{mp}",
    }

# ─── Browser driver ──────────────────────────────────────────────────────────

def make_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--lang=he-IL")
    options.add_argument("--window-size=1280,900")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )
    # In Docker/Linux, point Selenium at the system Chromium (env set by Dockerfile).
    import os as _os
    chrome_bin = _os.getenv("CHROME_BIN")
    if chrome_bin:
        options.binary_location = chrome_bin
    driver_path = _os.getenv("CHROMEDRIVER_PATH")
    if driver_path:
        from selenium.webdriver.chrome.service import Service
        driver = webdriver.Chrome(service=Service(driver_path), options=options)
    else:
        driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver


def get_page_html(driver: webdriver.Chrome, url: str, wait: float = 4.0) -> str:
    driver.get(url)
    time.sleep(wait)
    return driver.page_source

# ─── Seen listings persistence ───────────────────────────────────────────────

def load_seen() -> set:
    if SEEN_FILE.exists():
        with open(SEEN_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f)


def load_dismissed() -> set:
    if DISMISSED_FILE.exists():
        with open(DISMISSED_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_all_listings(listings: list[dict]):
    """Merge new listings into the master list shown by the dashboard."""
    existing = {}
    if ALL_FILE.exists():
        with open(ALL_FILE, encoding="utf-8") as f:
            for item in json.load(f):
                existing[item["id"]] = item
    for lst in listings:
        existing[lst["id"]] = lst
    with open(ALL_FILE, "w", encoding="utf-8") as f:
        # newest first
        json.dump(list(reversed(list(existing.values()))), f, ensure_ascii=False, indent=2)


# ─── Yad2 ────────────────────────────────────────────────────────────────────

def fetch_yad2(driver: webdriver.Chrome, cfg: dict = None) -> list[dict]:
    params = "&".join(f"{k}={v}" for k, v in yad2_params(cfg or {}).items())
    url = f"https://www.yad2.co.il/realestate/rent?{params}"
    try:
        html = get_page_html(driver, url, wait=5.0)
    except Exception as e:
        print(f"[Yad2] שגיאה: {e}")
        return []

    if "ShieldSquare" in html or "Captcha" in html:
        print("[Yad2] חסום ע\"י Captcha — ננסה בסיבוב הבא")
        return []

    m = re.search(
        r'<script\s+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    if not m:
        print("[Yad2] לא נמצא __NEXT_DATA__ בדף")
        return []

    try:
        data = json.loads(m.group(1))
        feed = data["props"]["pageProps"]["feed"]
    except (json.JSONDecodeError, KeyError) as e:
        print(f"[Yad2] שגיאה בפירוש הדף: {e}")
        return []

    listings = []
    for section in ("private", "agency", "yad1", "platinum"):
        raw_items = feed.get(section, [])
        if not isinstance(raw_items, list):
            continue
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            try:
                _cfg  = cfg or {}
                _maxp = _cfg.get("max_price", 3500)
                _minr = _cfg.get("min_rooms", 2)
                _maxr = _cfg.get("max_rooms", 3)
                price = item.get("price", 0) or 0
                rooms = float(item.get("additionalDetails", {}).get("roomsCount", 0) or 0)
                if price <= 0 or price > _maxp or rooms < _minr or rooms > _maxr + 0.5:
                    continue
                token = item.get("token", "")
                addr  = item.get("address", {})
                street = addr.get("street", {}).get("text", "")
                house  = addr.get("house", {})
                floor  = house.get("floor", "")
                size   = item.get("additionalDetails", {}).get("squareMeter", "")
                image  = (item.get("metaData") or {}).get("coverImage", "")
                full_address = f"{street} {house.get('number', '')}".strip()
                # Yad2 already filtered by neighborhood=39 (שכונה ב) — skip street filter
                if not is_allowed_street(full_address, _cfg, skip_filter=True):
                    continue
                listings.append({
                    "id":      f"yad2_{token}",
                    "source":  "Yad2",
                    "title":   f"דירת {rooms:.0f} חדרים, שכונה ב'",
                    "address": full_address,
                    "price":   int(price),
                    "rooms":   rooms,
                    "floor":   str(floor),
                    "size":    str(size),
                    "image":   image,
                    "url":     f"https://www.yad2.co.il/item/{token}",
                    "contact": (item.get("customer", {}) or {}).get("name", ""),
                })
            except Exception:
                continue
    # deduplicate by token (same listing can appear in multiple sections)
    seen_tokens: set = set()
    unique = []
    for lst in listings:
        if lst["id"] not in seen_tokens:
            seen_tokens.add(lst["id"])
            unique.append(lst)
    return unique


# ─── Homely ──────────────────────────────────────────────────────────────────

def fetch_homely(driver: webdriver.Chrome, cfg: dict = None) -> list[dict]:
    _cfg = cfg or {}
    min_rooms = _cfg.get("min_rooms", 2)
    max_rooms = _cfg.get("max_rooms", 3)
    max_price = _cfg.get("max_price", 3500)
    url = (
        "https://www.homely.co.il/s"
        "?dealType=rent&city=%D7%91%D7%90%D7%A8+%D7%A9%D7%91%D7%A2"
        f"&neighborhood=%D7%A9%D7%9B%D7%95%D7%A0%D7%94+%D7%91"
        f"&minRooms={min_rooms}&maxRooms={max_rooms}&maxPrice={max_price}"
    )
    try:
        html = get_page_html(driver, url, wait=4.0)
    except Exception as e:
        print(f"[Homely] שגיאה: {e}")
        return []

    m = re.search(
        r'<script\s+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    if not m:
        return []

    try:
        data = json.loads(m.group(1))
        # Try to find listings in the page data
        txt = json.dumps(data)
        page_props = data.get("props", {}).get("pageProps", {})
        raw = (page_props.get("listings") or page_props.get("results") or
               page_props.get("properties") or [])
    except Exception:
        return []

    listings = []
    for item in raw:
        try:
            price = item.get("price", 0) or 0
            rooms = float(item.get("rooms", 0) or 0)
            if price > max_price or rooms < min_rooms or rooms > max_rooms + 0.5:
                continue
            listings.append({
                "id":      f"homely_{item.get('id', '')}",
                "source":  "Homely",
                "title":   item.get("title", f"דירת {rooms:.0f} חדרים"),
                "address": item.get("address", ""),
                "price":   int(price),
                "rooms":   rooms,
                "floor":   str(item.get("floor", "")),
                "size":    str(item.get("size", "")),
                "url":     item.get("url", "https://www.homely.co.il"),
                "contact": item.get("contactName", ""),
            })
        except Exception:
            continue
    return listings


# ─── Email ───────────────────────────────────────────────────────────────────

def send_email(new_listings: list[dict]):
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        print(f"[התראה] נמצאו {len(new_listings)} דירות חדשות (הגדר EMAIL_SENDER/EMAIL_PASSWORD לשליחת מייל):")
        for lst in new_listings:
            print(f"  [{lst['source']}] {lst['address']} | {lst['rooms']:.0f} חד' | ₪{lst['price']:,} → {lst['url']}")
        return

    html = build_email_html(new_listings, title=f"{len(new_listings)} דירות חדשות — שכונה ב׳, באר שבע")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🏠 {len(new_listings)} דירות חדשות בשכונה ב' — באר שבע"
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = EMAIL_RECIPIENT
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
        print(f"[Email] ✓ נשלח — {len(new_listings)} דירות חדשות")
    except Exception as e:
        print(f"[Email] שגיאה: {e}")


# ─── Main loop ───────────────────────────────────────────────────────────────

async def send_telegram(new_listings: list[dict]):
    """Send new listings via Telegram bot."""
    from telegram_bot import send_listing, load_sent, save_sent
    from telegram import Bot
    from app_env import secret
    cfg   = load_settings()
    token = secret("TELEGRAM_TOKEN", cfg.get("telegram_token", ""))
    cid   = secret("TELEGRAM_CHAT_ID", cfg.get("telegram_chat_id", ""))
    if not token or not cid:
        return
    sent = load_sent()
    bot  = Bot(token=token)
    for lst in new_listings:
        if lst["id"] not in sent:
            await send_listing(bot, cid, lst)
            sent.add(lst["id"])
            await asyncio.sleep(0.5)
    save_sent(sent)


def is_expired(cfg: dict) -> bool:
    expiry = cfg.get("expiry_date", "")
    if not expiry:
        return False
    try:
        from datetime import date
        return date.today() > date.fromisoformat(expiry)
    except Exception:
        return False


def run_once(driver: webdriver.Chrome):
    from agent_status import set_status
    cfg = load_settings()
    if is_expired(cfg):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] פג תוקף הסוכן ({cfg.get('expiry_date')}) — מפסיק.")
        set_status("yad2", "disabled", "פג תוקף הסוכן")
        raise SystemExit(0)
    if not cfg.get("enabled", True):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] סוכן מושהה (enabled=false)")
        set_status("yad2", "disabled", "הסוכן מושהה")
        return

    print(f"[{datetime.now().strftime('%H:%M:%S')}] בודק דירות חדשות...")
    set_status("yad2", "scanning", "סורק את Yad2 + Homely…")
    seen      = load_seen()
    dismissed = load_dismissed()
    sources   = cfg.get("sources", {})

    yad2_results   = fetch_yad2(driver, cfg) if sources.get("yad2", True) else []
    homely_results = fetch_homely(driver, cfg) if sources.get("homely", True) else []
    all_listings   = yad2_results + homely_results

    print(f"  Yad2: {len(yad2_results)} | Homely: {len(homely_results)}")

    save_all_listings(all_listings)

    new_listings = [
        lst for lst in all_listings
        if lst["id"] not in seen and lst["id"] not in dismissed
    ]
    print(f"  חדשות: {len(new_listings)}")

    interval = cfg.get("yad2_interval_minutes", 40)
    from datetime import timedelta
    next_run = (datetime.now() + timedelta(minutes=interval)).strftime("%H:%M")
    set_status("yad2", "idle",
               f"הסתיים — {len(new_listings)} חדשות (Yad2: {len(yad2_results)}, Homely: {len(homely_results)})",
               found=len(new_listings), last_run=datetime.now().strftime("%H:%M"), next_run=next_run)

    if new_listings:
        # Telegram (primary)
        try:
            asyncio.run(send_telegram(new_listings))
            print(f"  [Telegram] OK - נשלחו {len(new_listings)} דירות")
        except Exception as e:
            print(f"  [Telegram] שגיאה: {e}")
        # Email (fallback if configured)
        send_email(new_listings)
        seen.update(lst["id"] for lst in new_listings)
        save_seen(seen)


def main():
    cfg = load_settings()
    interval = cfg.get("yad2_interval_minutes", 40)
    print("=" * 50)
    print(f" סוכן Yad2 | שכונה ב', באר שבע")
    print(f" סריקה כל {interval} דקות")
    print(" הגדרות: settings.json | עצור: /stop בטלגרם")
    print("=" * 50)

    driver = make_driver()
    try:
        run_once(driver)   # run immediately on start
        schedule.every(interval).minutes.do(run_once, driver)

        print(f"ממתין... (סריקה כל {interval} דקות) Ctrl+C להפסקה")
        while True:
            try:
                # Check if interval changed in settings
                new_interval = load_settings().get("yad2_interval_minutes", 40)
                if new_interval != interval:
                    schedule.clear()
                    schedule.every(new_interval).minutes.do(run_once, driver)
                    interval = new_interval
                    print(f"  עודכן לסריקה כל {interval} דקות")
                schedule.run_pending()
                time.sleep(30)
            except KeyboardInterrupt:
                print("\nהסוכן הופסק.")
                break
            except Exception as e:
                print(f"[שגיאה] {e}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
