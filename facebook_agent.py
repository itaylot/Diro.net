"""
Facebook Groups Apartment Agent — שכונה ב', באר שבע

Usage:
    python facebook_agent.py            # run normally
    python facebook_agent.py --login    # first-time Facebook login
    python facebook_agent.py --debug    # visible Chrome + full filter stats (one cycle)
"""

import hashlib
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import schedule
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

import storage

# Force UTF-8 output so Hebrew prints never crash on Windows (cp1252 console/file).
# Without this, printing a Hebrew post title raises UnicodeEncodeError and can
# abort the scan loop mid-way, silently dropping posts.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ─── Paths ───────────────────────────────────────────────────────────────────

ROOT        = Path(__file__).parent
SETTINGS_F  = ROOT / "settings.json"
SEEN_FB_F   = ROOT / "seen_fb_posts.json"
ALL_F       = ROOT / "all_listings.json"
DISMISSED_F = ROOT / "dismissed.json"
PROFILE_DIR = ROOT / "fb_chrome_profile"

DEBUG = "--debug" in sys.argv   # global flag

# ─── Settings ────────────────────────────────────────────────────────────────

def load_settings() -> dict:
    if SETTINGS_F.exists():
        return json.loads(SETTINGS_F.read_text(encoding="utf-8"))
    return {}

def cfg() -> dict:
    return load_settings()

# ─── Facebook groups ──────────────────────────────────────────────────────────
# dedicated=True → all posts are already in שכונה ב → skip location filter
# dedicated=False → general Beer Sheva groups → require שכונה ב mention

GROUPS = {
    "דירות בשכונה ב + הבלוק":         {"id": "227042837307326",  "dedicated": True},
    "דירות הוגנות בשכונה ב":          {"id": "989159401625656",  "dedicated": True},
    "שכונה ב באר שבע":                {"id": "501446271648548",  "dedicated": True},
    "מפה לאוזן שכונה ב":              {"id": "170744879507",     "dedicated": True},
    "מפה לאוזן 2 שכונה ב":           {"id": "321355873210119",  "dedicated": True},
    "דירות הוגנות":                   {"id": "1730789290457027", "dedicated": True},
    "דירות להשכרה באר שבע ללא תיווך": {"id": "1664792386922491", "dedicated": False},
    "דירות להשכרה באר שבע ללא ספאם":  {"id": "954866583054461",  "dedicated": False},
}

# ─── Stable post ID ───────────────────────────────────────────────────────────
# IMPORTANT: do NOT use Python's built-in hash() — it changes seed every run.
# Use hashlib.md5 for stable, reproducible IDs.

def stable_id(group_id: str, post_url: str, text: str) -> str:
    key = post_url if "/posts/" in post_url or "/permalink/" in post_url else text[:150]
    h = hashlib.md5(key.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"fb_{group_id}_{h}"

# ─── Text cleaning ────────────────────────────────────────────────────────────

def clean(text: str) -> str:
    return text.replace('"', '').replace("'", '').replace('״', '').replace('׳', '').lower().strip()

def normalize_text(text: str) -> str:
    """Collapse whitespace, strip, and remove Facebook UI noise appended by JS extraction."""
    for noise in FB_UI_NOISE:
        text = re.sub(re.escape(noise), ' ', text, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', text).strip()

# ─── Classification word lists ────────────────────────────────────────────────

# Strong signals that a post is offering a full apartment for rent
RENTAL_STRONG = [
    "דירה להשכרה", "דירה מתפנה", "דירה פנויה",
    "להשכרה", "לשכירות", "להשכיר",
    "שכ\"ד", "שכד", "שכ'ד",
    "בעל דירה", "בעלת דירה", "בעל/ת דירה",  # all owner variants
    "יחידת דיור",
    "דירת", "דירות",
    "מפנה דירה", "מפנים דירה",               # "אנחנו מפנים דירה"
]

# Signals that the apartment is currently available
AVAILABILITY_WORDS = [
    "כניסה מיידית", "כניסה גמישה",
    "מתפנה", "מתפנות", "מתפנים",   # singular + plural
    "פנויה", "פנוי", "פנויות", "פנויים",
    "זמינה", "זמין", "זמינות",
    "כניסה ב",
    "מפנה",                          # "מפנה דירה" / "מפנים"
]

# Seeker intent — poster is LOOKING for an apartment (not offering)
# Only match full phrases, not just "מחפש" alone
SEEKER_PATTERNS = [
    # Direct search phrases
    "מחפש דירה", "מחפשת דירה",
    "מחפשים דירה", "מחפשות דירה",
    "מחפשים דירת", "מחפשת דירת",   # "מחפשים דירת 3 חדרים"
    "מחפש בית", "מחפשת בית",
    # Who is searching
    "זוג מחפש", "זוג צעיר מחפש",
    "סטודנט מחפש", "סטודנטית מחפשת",
    # Wants to rent
    "מחפש להשכיר", "מחפשת להשכיר",
    "מחפשים להשכיר", "מחפשות להשכיר",
    # "I'd love offers"
    "אשמח להצעות", "נשמח להצעות",
    "אשמח לשמוע", "נשמח לשמוע",
    "מחפש/ת דירה",
    "looking for apartment", "wanted apartment",
]

# Roommate / shared apartment — single room or joining existing roommates
ROOMMATE_PATTERNS = [
    # Room vacancy
    "חדר פנוי", "חדר מתפנה", "מתפנה חדר",
    # Looking for roommate (all verb forms)
    "מחפשים שותף", "מחפשות שותפה", "מחפשים שותפה",
    "מחפש שותפ",   # covers: שותף / שותפה / שותפ/ה / שותפות
    "מחפשת שותפ",
    "מחפשות שותפ",
    # Replacement / sublet
    "מחפשת מחליפ",   # covers: מחליפה / מחליפ/ה
    "מחפש מחליפ",
    "מסבלט",          # covers: מסבלט / מסבלטת (subletting their room)
    "סאבלט",
    # Shared apartment structure
    "דירת שותפים",
    "שותף שלישי", "שותפה שלישית",
    "חדר בדירת שותפים",
    "נכנס במקומי", "נכנסת במקומי",
    "להחליף חדר",
    # Looking for people to join
    "מחפש את השותפים",
    "מחפשות שותפ",
]

# Exception: these override ROOMMATE_PATTERNS — it's a full apartment, not a room
FULL_APT_OVERRIDE = [
    "דירה מתפנה", "דירה להשכרה",
    "דירת 2", "דירת 3", "דירת 4",
    "2 חדרים", "2.5 חדרים", "3 חדרים", "3.5 חדרים",
]

# Sale posts
SALE_PATTERNS = [
    "למכירה", "מכירה דחופה",
    "דירה למכירה", "נכס למכירה",
    "נכס להשקעה", "משקיעים",
    "מחיר מכירה",
]

# Service / off-topic posts — not apartments at all
SERVICE_PATTERNS = [
    # Tradespeople
    "שיפוצניק", "שיפוצנית", "חברת שיפוץ",
    "אינסטלטור", "חשמלאי", "מזגן",
    "חברת ניקיון", "ניקיון דירה",
    "עורך דין", "עו\"ד",
    # Furniture / items (not apartment rental)
    "מסירה חינם", "מסירה בחינם", "מוסר חינם",
    "ריהוט למסירה", "ריהוט חינם",
    # Group announcements
    "הודעה לחברי הקבוצה", "שימו לב חברים",
    "הודעה חשובה לחברי",
    # Food / catering ads (these cross-post into apartment groups)
    "סושי", "מגש פירות", "מגשי פירות", "מגשי אירוח",
    "קייטרינג", "קינוח", "פלטות", "מארזי",
    "מבית פרי פרימיום",
]

# Facebook UI noise — strip these from post text before any analysis
# (they appear appended to post content in JS-extracted text)
FB_UI_NOISE = [
    "like reply share",
    "לייק הוספת תגובה שיתוף",
    "like • reply • share",
    "הוספת תגובה",
]

# Beer Sheva / שכונה ב location signals
LOCATION_BS = [
    "שכונה ב", "שכונה ב'", "שכ' ב", "שכ ב",
    "ביאליק", "וינגייט", "סורוקה",
    "אוניברסיטה", "בן גוריון",
    "רגר", "ביג",
    "באר שבע", "ב\"ש",
]

# Explicit "שכונה ב" mention — strong proof the post IS שכונה ב
SHCHUNA_BET = ["שכונה ב", "שכ' ב", "שכ ב"]

# Named Beer Sheva neighborhoods that are NOT שכונה ב (safe as substrings —
# multi-word, won't false-match). If mentioned without שכונה ב → filter out.
OTHER_NEIGHBORHOODS_NAMED = [
    "נווה זאב", "נווה נוי", "נווה מנחם", "נווה עופר", "נווה נוי",
    "נחל עשן", "כלניות", "סיגליות", "נאות הדרים", "נאות לון",
    "המרכז הישן",
]

# "שכונה <letter>" where letter is any neighborhood letter except ב.
# Word-boundary: the letter must NOT be followed by another Hebrew letter,
# so "בשכונה זו" / "שכונה ותיקה" do NOT false-match "שכונה ז" / "שכונה ו".
OTHER_HOOD_LETTER_RE = re.compile(
    r"שכונה\s+([אגדהוזחט])(?![א-ת])"
)

def mentions_other_neighborhood(text: str) -> bool:
    """True if the post explicitly names a Beer Sheva neighborhood other than ב."""
    if OTHER_HOOD_LETTER_RE.search(text):
        return True
    return _contains(text, OTHER_NEIGHBORHOODS_NAMED)

# Signals for another city (should not appear without Beer Sheva context)
OTHER_CITY = [
    "תל אביב", "ירושלים", "חיפה", "ראשון לציון",
    "פתח תקווה", "נתניה", "אשדוד", "אשקלון",
    "רמת גן", "בני ברק", "הרצליה", "כפר סבא",
    "רחובות", "מודיעין",
]

# ─── Extraction helpers ───────────────────────────────────────────────────────

def _contains(text: str, phrases: list) -> bool:
    """Case-insensitive: does text contain any of the phrases?"""
    tl = text.lower()
    return any(p.lower() in tl for p in phrases)

def extract_price(text: str) -> int:
    """Extract lowest plausible rent price. Returns 0 if not found."""
    patterns = [
        r"(\d[\d,.]+)\s*(?:₪|ש\"ח|שח|שקל)",
        r"(?:מחיר|שכד|שכ\"ד|שכ'ד|שכירות)[^\d]{0,5}(\d[\d,.]+)",
        r"(\d[\d,.]+)\s*(?:לחודש|לחד|ל'חודש)",
        r"(?:לחודש|לחד)\s*(\d[\d,.]+)",
        r"(\d[\d,.]+)\s*(?:כולל|לא כולל)",
    ]
    prices = []
    for p in patterns:
        for m in re.findall(p, text, re.IGNORECASE):
            raw = re.sub(r"[,.]", "", str(m).rstrip(".,"))
            if raw.isdigit():
                v = int(raw)
                # Range: plausible rent (not room count / floor / date)
                if 1500 < v < 15_000:
                    prices.append(v)
    return min(prices) if prices else 0

def extract_rooms(text: str) -> float:
    """Extract room count. Returns 0.0 if not found."""
    patterns = [
        r"(\d(?:[.,]\d)?)\s*(?:חד'|חדרים|חדר)",
        r"דירת\s+(\d(?:[.,]\d)?)",
        r"(\d(?:[.,]\d)?)\s*room",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1).replace(",", "."))
            except Exception:
                pass
    # Fallback: "2חד" / "3.5חד" without space
    m = re.search(r"(\d(?:[.,]\d)?)\s*חד", text)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except Exception:
            pass
    return 0.0

def extract_location(text: str) -> str:
    """Return the first Beer Sheva location signal found, or empty string."""
    for loc in LOCATION_BS:
        if loc.lower() in text.lower():
            return loc
    return ""

# ─── Intent detection ─────────────────────────────────────────────────────────

def _is_seeker_post(text: str) -> bool:
    """
    Return True only if the main intent is the poster LOOKING for an apartment.
    Does NOT reject every post containing "מחפש" — only clear seeker phrases.
    """
    if not _contains(text, SEEKER_PATTERNS):
        return False
    # Only override seeker detection if the post has clear OFFER signals:
    # owner/landlord words or "we are vacating" type phrases.
    # Do NOT override just because "דירה" + "להשכרה" appear — seekers use those too.
    OFFER_SIGNALS = [
        "בעל דירה", "בעלת דירה", "בעל/ת דירה",
        "אני משכיר", "אנחנו משכירים", "אני מפנה", "אנחנו מפנים",
        "הדירה שלי", "הדירה שלנו",
    ]
    if _contains(text, OFFER_SIGNALS):
        return False
    return True

def _is_roommate_post(text: str) -> bool:
    """
    Return True if this is a single-room or join-roommates listing.
    Exception: if the post also advertises a FULL apartment, keep it.

    Logic:
    - Strong roommate signals (sublet, seeking roommate, etc.) override
      full-apartment keywords — because "דירת 4 חדרים" often appears in
      shared-apartment posts as context, not as an offer.
    - Weak roommate signals (e.g., "חדר פנוי" only) can be overridden
      by clear full-apartment offer phrases.
    """
    if not _contains(text, ROOMMATE_PATTERNS):
        return False

    # These signals mean it's DEFINITELY a roommate/sublet post —
    # even if "דירת X חדרים" also appears.
    STRONG_ROOMMATE = [
        "מסבלט", "סאבלט",
        "מחפש את השותפים", "מחפשת את השותפות",
        "מחפשות שותפ", "מחפש שותפ", "מחפשת שותפ",
        "נכנס במקומי", "נכנסת במקומי",
        "מחליפ",   # מחליפה / מחליפ/ה
    ]
    if _contains(text, STRONG_ROOMMATE):
        return True  # Strong signal — don't let apartment keywords override

    # For weaker roommate signals, allow override only if the post
    # clearly advertises a full apartment for rent.
    if _contains(text, FULL_APT_OVERRIDE):
        return False

    return True

# ─── Scoring ──────────────────────────────────────────────────────────────────

def score_rental_apartment(text: str, dedicated: bool) -> tuple[int, list[str]]:
    """
    Return (score, reasons). Higher score = more likely a relevant rental.
    Score >= 4 → relevant_rental_apartment
    Score 2-3  → maybe_relevant_rental_apartment
    Score < 2  → irrelevant
    """
    score = 0
    reasons = []

    if _contains(text, RENTAL_STRONG):
        score += 4
        reasons.append("rental_keyword")

    if _contains(text, AVAILABILITY_WORDS):
        score += 2
        reasons.append("availability_keyword")

    location = extract_location(text)
    if location:
        score += 3
        reasons.append(f"location:{location}")
    elif dedicated:
        # Dedicated group → assume Beer Sheva even without explicit mention
        score += 2
        reasons.append("dedicated_group")

    price = extract_price(text)
    if price:
        score += 2
        reasons.append(f"price:{price}")

    rooms = extract_rooms(text)
    if 1.0 <= rooms <= 4.5:
        score += 2
        reasons.append(f"rooms:{rooms}")

    # Entry date detected (dd/mm or dd.mm style)
    if re.search(r"\b\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?\b", text):
        score += 1
        reasons.append("date_found")

    # Couple-suitable phrase — explicitly marketed to a couple
    couple_phrases = [
        "לזוג", "מתאים לזוג", "מתאימה לזוג",
        "לזוג צעיר", "דירת זוג", "לזוג ללא ילדים",
        "לזוג/משפחה", "לשני אנשים",
    ]
    if _contains(text, couple_phrases):
        score += 4
        reasons.append("suitable_for_couple")

    # Studio / unit counts as full apartment
    if _contains(text, ["סטודיו", "יחידת דיור"]):
        score += 3
        reasons.append("studio_or_unit")

    # Negative: another city mentioned without Beer Sheva context
    if _contains(text, OTHER_CITY) and not location:
        score -= 5
        reasons.append("other_city")

    return score, reasons

# ─── Main classifier ──────────────────────────────────────────────────────────

def classify_post(
    text: str,
    dedicated: bool,
    max_price: int = 0,
    min_rooms: float = 0.0,
    max_rooms: float = 0.0,
) -> tuple[str, int, float, int, list[str]]:
    """
    Classify a Facebook post into one category.

    Returns (classification, score, rooms, price, reasons).

    Pass max_price/min_rooms/max_rooms from the caller (read settings once per scan,
    not on every post) — if omitted, falls back to settings.json defaults.

    Categories:
      relevant_rental_apartment      → send to Telegram
      maybe_relevant_rental_apartment → save but don't send
      room_or_roommate_listing       → save but don't send
      seeker_post                    → discard
      sale_post                      → discard
      over_budget                    → save but don't send
      irrelevant                     → discard
    """
    if not max_price or not min_rooms or not max_rooms:
        s = cfg()
        max_price = max_price or s.get("max_price", 4100)
        min_rooms = min_rooms or s.get("min_rooms", 1.5)
        max_rooms = max_rooms or s.get("max_rooms", 3.5)

    # Hard rejections (order matters)
    if _contains(text, SALE_PATTERNS):
        return "sale_post", 0, 0.0, 0, ["sale_keyword"]

    if _contains(text, SERVICE_PATTERNS):
        return "irrelevant", 0, 0.0, 0, ["service_or_offtopic"]

    # Fast seeker check: if the first 15 words start with first-person apartment search,
    # reject early — but skip if it's actually about finding roommates (not an apartment).
    first_words = " ".join(text.split()[:15])
    FIRST_PERSON_SEEKER = ["אני מחפש", "אנחנו מחפשים", "אני מחפשת",
                           "אנחנו זוג", "זוג מחפש", "זוגות מחפש"]
    if _contains(first_words, FIRST_PERSON_SEEKER) and not _is_roommate_post(text):
        return "seeker_post", 0, 0.0, 0, ["seeker_first_words"]

    if _is_seeker_post(text):
        return "seeker_post", 0, 0.0, 0, ["seeker_intent"]

    if _is_roommate_post(text):
        return "room_or_roommate_listing", 0, 0.0, 0, ["roommate_keyword"]

    # שכונה ב ONLY: if the post explicitly names another neighborhood and does
    # NOT mention שכונה ב, it's not what the user wants → discard.
    # (Dedicated groups cross-post other neighborhoods like א/ה/ו, נווה זאב...)
    if mentions_other_neighborhood(text) and not _contains(text, SHCHUNA_BET):
        return "irrelevant", 0, 0.0, 0, ["other_neighborhood"]

    # Extract fields
    price = extract_price(text)
    rooms = extract_rooms(text)

    # Over budget (price detected AND above threshold)
    if price > 0 and price > max_price:
        return "over_budget", 0, rooms, price, [f"price_too_high:{price}"]

    # Score the post
    score, reasons = score_rental_apartment(text, dedicated)

    # Require a real apartment signal. An availability word ALONE ("זמין",
    # "פנוי") is not enough — a food ad can be "זמין למשלוח". Accept availability
    # only when it's backed by a room count, so we don't flag non-apartments.
    has_rental_signal = (
        "rental_keyword" in reasons
        or "studio_or_unit" in reasons
        or ("availability_keyword" in reasons and rooms > 0)
    )
    if not has_rental_signal:
        return "irrelevant", score, rooms, price, reasons + ["no_rental_signal"]

    # Room count check — use settings min/max, not hardcoded values.
    # If room count is unknown (0.0) → don't penalize, keep scoring as-is.
    if rooms > 0.0 and not (min_rooms <= rooms <= max_rooms + 0.5):
        # Outside desired range → downgrade to maybe so user can review
        return "maybe_relevant_rental_apartment", score, rooms, price, reasons + ["rooms_outside_range"]

    if score >= 4:
        return "relevant_rental_apartment", score, rooms, price, reasons
    elif score >= 2:
        return "maybe_relevant_rental_apartment", score, rooms, price, reasons
    else:
        return "irrelevant", score, rooms, price, reasons

# ─── Persistence ─────────────────────────────────────────────────────────────

def load_seen() -> set:
    return set(storage.read_json(SEEN_FB_F, []))

def save_seen(seen: set):
    storage.write_json(SEEN_FB_F, list(seen))

def load_dismissed() -> set:
    return set(storage.read_json(DISMISSED_F, []))

def save_to_all_listings(listings: list[dict]):
    def _mut(existing_list):
        existing = {}
        for item in (existing_list or []):
            existing[item["id"]] = item
        for lst in listings:
            existing[lst["id"]] = lst
        return list(reversed(list(existing.values())))
    storage.update_json(ALL_F, _mut, [])


def push_to_server(listings: list[dict]):
    """
    Push found listings to the cloud dashboard (so it shows them even though the
    Facebook agent runs here on the home PC). No-op unless INGEST_URL +
    INGEST_TOKEN are set in .env. Token-authenticated.
    """
    import os
    url = os.getenv("INGEST_URL")
    token = os.getenv("INGEST_TOKEN")
    if not url or not token or not listings:
        return
    try:
        import requests
        r = requests.post(url, json=listings,
                          headers={"X-Ingest-Token": token}, timeout=25)
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        print(f"  [שרת] נשלחו {len(listings)} דירות → {r.status_code} "
              f"(חדשות: {data.get('added', '?')})")
    except Exception as e:
        print(f"  [שרת] שגיאה בשליחה: {e}")

# ─── Chrome driver ────────────────────────────────────────────────────────────

def make_driver(headless: bool = True) -> webdriver.Chrome:
    opts = Options()
    opts.add_argument(f"--user-data-dir={PROFILE_DIR}")
    opts.add_argument("--profile-directory=Default")
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("--window-size=1400,900")
    opts.add_argument("--lang=he-IL")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )
    # In Docker/Linux, point Selenium at the system Chromium (env set by Dockerfile).
    import os as _os
    chrome_bin = _os.getenv("CHROME_BIN")
    if chrome_bin:
        opts.binary_location = chrome_bin
    driver_path = _os.getenv("CHROMEDRIVER_PATH")
    if driver_path:
        from selenium.webdriver.chrome.service import Service
        driver = webdriver.Chrome(service=Service(driver_path), options=opts)
    else:
        driver = webdriver.Chrome(options=opts)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver

def is_logged_in(driver: webdriver.Chrome) -> bool:
    driver.get("https://www.facebook.com/")
    time.sleep(4)
    url  = driver.current_url
    src  = driver.page_source.lower()[:1000]
    logged = "login" not in url and "log_in" not in src and "password" not in src
    if DEBUG:
        print(f"  [login-check] url={url} | logged_in={logged}")
    return logged

# ─── Dialog dismissal ────────────────────────────────────────────────────────

def _dismiss_dialogs(driver: webdriver.Chrome):
    """Close any Facebook popups/overlays that block feed content."""
    dismiss_xpaths = [
        # "Not now" / close buttons on dialogs
        '//div[@role="dialog"]//div[@role="button" and contains(.,"לא עכשיו")]',
        '//div[@role="dialog"]//div[@role="button" and contains(.,"Not Now")]',
        '//div[@role="dialog"]//div[@role="button" and contains(.,"סגור")]',
        '//div[@role="dialog"]//div[@role="button" and contains(.,"Close")]',
        # Cookie consent
        '//button[contains(.,"הסכם")]',
        '//button[contains(.,"Accept")]',
        '//button[contains(.,"Allow")]',
        # "Download app" prompt
        '//div[@aria-label="סגור"]',
        '//div[@aria-label="Close"]',
        # Generic ✕ close buttons in dialogs
        '//div[@role="dialog"]//*[@aria-label="סגור"]',
    ]
    for xpath in dismiss_xpaths:
        try:
            btns = driver.find_elements(By.XPATH, xpath)
            for btn in btns[:1]:
                btn.click()
                time.sleep(0.4)
        except Exception:
            pass

    # Also press Escape to close any overlay
    try:
        from selenium.webdriver.common.keys import Keys
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(0.3)
    except Exception:
        pass


def _expand_see_more(driver: webdriver.Chrome) -> int:
    """
    Click every "See more"/"ראה עוד" button to reveal full post text.
    Facebook truncates long posts — without expanding, .text returns only
    2-3 lines (often < 60 chars), so real listings get dropped as "too short".

    This is a read-only UI action (expanding text), NOT a like/comment/share.
    Returns the number of buttons clicked (for debug visibility).
    """
    # Span/div role=button whose visible text is exactly the "see more" label.
    xpaths = [
        '//div[@role="button" and (text()="ראה עוד" or text()="See more")]',
        '//span[@role="button" and (text()="ראה עוד" or text()="See more")]',
    ]
    clicked = 0
    for xpath in xpaths:
        try:
            for btn in driver.find_elements(By.XPATH, xpath):
                try:
                    # Click via JS — avoids scrolling/interception issues
                    driver.execute_script("arguments[0].click()", btn)
                    clicked += 1
                    time.sleep(0.15)
                except Exception:
                    pass
        except Exception:
            pass
    return clicked


def _js_extract_posts(driver: webdriver.Chrome) -> list:
    """
    Use JavaScript to extract text blocks + post URLs from Facebook posts.
    Returns a list of fake elements with .text and .post_url attributes.
    """
    try:
        items = driver.execute_script("""
            const results = [];
            const seen = new Set();

            // Find post URL: look for a timestamp/date link inside a post container.
            // Facebook wraps the "X hours ago" text in an <a> pointing to the post.
            function findPostUrl(el) {
                // Try links that contain /posts/ or /permalink/
                const links = el.querySelectorAll('a[href]');
                for (const a of links) {
                    const href = a.href || '';
                    if ((href.includes('/posts/') || href.includes('/permalink/'))
                        && !href.includes('comment_id')
                        && !href.includes('/photo')
                        && !href.includes('/user/')) {
                        return href.split('?')[0];
                    }
                }
                // Fallback: any link with a long numeric path segment (post ID)
                for (const a of links) {
                    const href = a.href || '';
                    if (href.includes('facebook.com/groups/') && /\\/\\d{10,}\\//.test(href)) {
                        return href.split('?')[0];
                    }
                }
                return '';
            }

            document.querySelectorAll('div[dir="rtl"], div[dir="auto"]').forEach(el => {
                const t = (el.innerText || '').trim();
                if (t.length > 80 && !seen.has(t.slice(0, 100))) {
                    seen.add(t.slice(0, 100));
                    results.push({ text: t, url: findPostUrl(el) });
                }
            });
            return results.slice(0, 60);
        """)

        class _FakeEl:
            def __init__(self, t, url):
                self.text = t
                self.post_url = url          # NEW: direct post URL if found
            def find_element(self, *a, **kw):
                raise Exception("no element")
            def find_elements(self, *a, **kw):
                return []

        return [_FakeEl(item["text"], item.get("url", "")) for item in (items or [])]
    except Exception:
        return []


# ─── Scrape one group ─────────────────────────────────────────────────────────

def scrape_group(
    driver: webdriver.Chrome,
    group_name: str,
    group_info: dict,
    max_price: int = 0,
    min_rooms: float = 0.0,
    max_rooms: float = 0.0,
) -> list[dict]:
    group_id  = group_info["id"]
    dedicated = group_info["dedicated"]
    url = f"https://www.facebook.com/groups/{group_id}/?sorting_setting=CHRONOLOGICAL"

    print(f"\n  [{group_name}]")

    # Explicit page-load timeout so one stuck group can't freeze the whole scan.
    # If the page is slow, stop loading and work with whatever rendered.
    try:
        driver.set_page_load_timeout(45)
    except Exception:
        pass

    try:
        driver.get(url)
        time.sleep(5)
    except Exception as e:
        # Timeout/slow load — stop loading and continue with partial content
        print(f"    [!] טעינה איטית/נכשלה ({type(e).__name__}) — ממשיך עם מה שנטען")
        try:
            driver.execute_script("window.stop()")
        except Exception:
            pass

    if "login" in driver.current_url or "checkpoint" in driver.current_url:
        print(f"    [!] נדרשת כניסה מחדש -- הרץ: python facebook_agent.py --login")
        return []

    # ── Dismiss any dialogs / overlays that block content ──
    _dismiss_dialogs(driver)

    # ── Scroll to load posts ──
    # Dedicated שכונה ב groups get more scrolls — we want fresh posts from them
    scroll_count = 18 if dedicated else 10
    for i in range(scroll_count):
        driver.execute_script("window.scrollBy(0, 1000)")
        time.sleep(1.5)
        # Every 4 scrolls, dismiss dialogs again (they re-appear)
        if i % 4 == 3:
            _dismiss_dialogs(driver)
            # Expand truncated posts as we go so their full text loads
            _expand_see_more(driver)

    # Final pass: expand any remaining "ראה עוד" before extracting text.
    # Without this, long posts return only 2-3 lines and get dropped as "too short".
    expanded = _expand_see_more(driver)
    time.sleep(1.0)
    if DEBUG:
        print(f"    'ראה עוד' נלחץ: {expanded}")

    # ── Collect all post URLs from the page before scraping ──
    # Facebook's post links follow the pattern /groups/ID/posts/POST_ID/
    # We gather them all once here and try to match them to posts by text snippet.
    page_post_urls: list[str] = []
    try:
        page_post_urls = driver.execute_script("""
            const urls = new Set();
            document.querySelectorAll('a[href]').forEach(a => {
                const h = a.href || '';
                // Match any Facebook link that looks like a specific post
                // (has /posts/, /permalink/, or a 10+ digit number in the path)
                if (h.includes('facebook.com') && !h.includes('comment_id')
                    && !h.includes('/photo') && !h.includes('/profile')
                    && !h.includes('/user/')
                    && (h.includes('/posts/') || h.includes('/permalink/')
                        || /\\/groups\\/[^\\/]+\\/\\d{10,}/.test(h))) {
                    urls.add(h.split('?')[0]);
                }
            });
            return Array.from(urls).slice(0, 80);
        """) or []
    except Exception:
        pass

    if DEBUG and page_post_urls:
        print(f"    Post URLs found: {len(page_post_urls)}")

    # ── Try to find post containers — multiple strategies ──

    # Strategy 1: role="article" — most reliable
    posts_raw = driver.find_elements(By.XPATH, '//div[@role="article"]')

    if DEBUG:
        print(f"    Strategy 1 (role=article): {len(posts_raw)}")

    # Strategy 2: feed pagelet divs
    if len(posts_raw) < 3:
        candidates = driver.find_elements(
            By.XPATH, '//div[contains(@data-pagelet,"FeedUnit")]'
        )
        if len(candidates) > len(posts_raw):
            posts_raw = candidates
        if DEBUG:
            print(f"    Strategy 2 (FeedUnit): {len(candidates)}")

    # Strategy 3: comet preview messages
    if len(posts_raw) < 3:
        candidates = driver.find_elements(
            By.CSS_SELECTOR, 'div[data-ad-comet-preview="message"]'
        )
        if len(candidates) > len(posts_raw):
            posts_raw = candidates
        if DEBUG:
            print(f"    Strategy 3 (comet-preview): {len(candidates)}")

    # Strategy 4: RTL divs with substantial text (last resort)
    if len(posts_raw) < 3:
        all_rtl = driver.find_elements(By.XPATH, '//div[@dir="rtl"]')
        candidates = [d for d in all_rtl if len(d.text.strip()) > 80]
        if len(candidates) > len(posts_raw):
            posts_raw = candidates
        if DEBUG:
            print(f"    Strategy 4 (dir=rtl text>80): {len(candidates)}")

    # Strategy 5: JavaScript text extraction — only when DOM strategies find nothing
    if len(posts_raw) < 3:
        posts_raw = _js_extract_posts(driver)
        if DEBUG:
            print(f"    Strategy 5 (JS text extract): {len(posts_raw)}")

    if DEBUG:
        print(f"    DOM סופי: נמצאו {len(posts_raw)} אלמנטים")

    # ── Classification stats ──
    stats = {
        "total": 0, "too_short": 0, "duplicate": 0,
        "relevant_rental_apartment": 0,
        "maybe_relevant_rental_apartment": 0,
        "room_or_roommate_listing": 0,
        "seeker_post": 0,
        "sale_post": 0,
        "over_budget": 0,
        "irrelevant": 0,
    }

    # Categories we keep in storage (send only "relevant" to Telegram)
    KEEP_CATEGORIES = {
        "relevant_rental_apartment",
        "maybe_relevant_rental_apartment",
        "over_budget",
    }

    listings = []
    seen_texts: set[str] = set()

    for post_el in posts_raw[:40]:
        stats["total"] += 1
        try:
            text = post_el.text.strip()
            text = normalize_text(text)

            # Real posts are at least 60 chars.
            # Shorter elements are usually comments, reactions, or nav items.
            if len(text) < 60:
                stats["too_short"] += 1
                continue

            # Deduplicate: hash of normalized text (stripped punctuation, collapsed spaces)
            # Using MD5 of first 300 chars catches near-duplicates from different strategies
            clean_for_dedup = re.sub(r"[^\w֐-׿]", "", text[:300])
            key = hashlib.md5(clean_for_dedup.encode("utf-8", errors="replace")).hexdigest()
            if key in seen_texts:
                stats["duplicate"] += 1
                continue
            seen_texts.add(key)

            # ── Classify the post ──
            classification, score, rooms, price, reasons = classify_post(
                text, dedicated, max_price=max_price, min_rooms=min_rooms, max_rooms=max_rooms
            )
            stats[classification] = stats.get(classification, 0) + 1

            if DEBUG:
                snippet = text[:80].replace('\n', ' ')
                mark = "OK" if classification in KEEP_CATEGORIES else "--"
                print(f"    {mark} [{classification}] score={score} | {snippet}")

            if classification not in KEEP_CATEGORIES:
                continue

            # ── Post URL ──
            # Priority 1: URL from JS extraction (_FakeEl has post_url attribute)
            # Priority 2: XPath inside real Selenium element
            # Priority 3: Match from page_post_urls collected earlier (by index)
            # Fallback: group URL
            group_url = f"https://www.facebook.com/groups/{group_id}"
            post_url = getattr(post_el, "post_url", "") or ""

            if not post_url:
                # Selenium XPath — works for real DOM elements (Strategy 1-4)
                url_xpaths = [
                    './/a[contains(@href,"/posts/") and not(contains(@href,"comment_id"))]',
                    './/a[contains(@href,"/permalink/")]',
                    './/a[contains(@href,"story_fbid")]',
                ]
                for xpath in url_xpaths:
                    try:
                        for link in post_el.find_elements(By.XPATH, xpath):
                            href = link.get_attribute("href") or ""
                            if any(s in href for s in ["/user/", "/photo", "comment_id"]):
                                continue
                            if href and "facebook.com" in href:
                                post_url = href.split("?")[0]
                                break
                        if post_url:
                            break
                    except Exception:
                        pass

            # Fallback: group URL (safer than assigning random page URLs by index)
            if not post_url:
                post_url = group_url

            # Stable ID using md5
            post_id = stable_id(group_id, post_url, text)

            # Image
            image_url = ""
            try:
                img = post_el.find_element(By.XPATH, './/img[contains(@src,"scontent")]')
                image_url = img.get_attribute("src") or ""
            except Exception:
                pass

            preview = text[:350] + ("…" if len(text) > 350 else "")

            location = extract_location(text)
            streets = cfg().get("allowed_streets", [])
            found_street = next(
                (s for s in streets if clean(s) in clean(text)), ""
            )
            address = found_street or location or "באר שבע"

            listings.append({
                "id":             post_id,
                "source":         f"Facebook — {group_name}",
                "title":          preview[:80],
                "address":        address,
                "price":          price,
                "rooms":          rooms,
                "floor":          "",
                "size":           "",
                "image":          image_url,
                "url":            post_url,
                "preview":        preview,
                "contact":        "",
                "classification": classification,
                "score":          score,
                "reasons":        reasons,
                "found_at":       datetime.now().strftime("%Y-%m-%d %H:%M"),
            })

            if DEBUG:
                print(f"      -> {price}  | {rooms}חד | reasons: {reasons}")

        except Exception:
            continue

    # ── Per-group summary ──
    unique_posts = stats["total"] - stats["too_short"] - stats["duplicate"]
    print(
        f"    סה\"כ: {stats['total']} | "
        f"קצר: {stats['too_short']} | "
        f"כפול: {stats['duplicate']} | "
        f"[OK] רלוונטי: {stats['relevant_rental_apartment']} | "
        f"~ אולי: {stats['maybe_relevant_rental_apartment']} | "
        f"שותפים: {stats['room_or_roommate_listing']} | "
        f"מחפש: {stats['seeker_post']} | "
        f"מכירה: {stats['sale_post']} | "
        f"יקר: {stats['over_budget']} | "
        f"לא רלוונטי: {stats['irrelevant']}"
    )

    # Warn if the group returned very few usable posts — likely a scraping failure
    if unique_posts < 5:
        print(f"    ⚠️  רק {unique_posts} פוסטים ייחודיים — ייתכן שהסריקה נכשלה (דיאלוג? DOM?)")

    return listings

# ─── Telegram ─────────────────────────────────────────────────────────────────

async def send_telegram(listings: list[dict]):
    try:
        from telegram import Bot
        from telegram_bot import send_listing, load_sent, SENT_FILE
        from app_env import secret
        import asyncio
        s = cfg()
        token = secret("TELEGRAM_TOKEN", s.get("telegram_token", ""))
        cid   = secret("TELEGRAM_CHAT_ID", s.get("telegram_chat_id", ""))
        if not token or not cid:
            return
        sent = load_sent()           # snapshot, used only to skip already-sent listings
        bot  = Bot(token=token)
        newly_sent = set()
        for lst in listings:
            if lst["id"] not in sent:
                await send_listing(bot, cid, lst)
                newly_sent.add(lst["id"])
                await asyncio.sleep(0.6)
        # Union under a lock — apartment_agent + the bot write this file too.
        if newly_sent:
            storage.update_json(SENT_FILE, lambda ids: list(set(ids) | newly_sent), [])
        print(f"  [Telegram] שלחתי {len(listings)} התראות")
    except Exception as e:
        print(f"  [Telegram] שגיאה: {e}")

# ─── Expiry ───────────────────────────────────────────────────────────────────

def is_expired() -> bool:
    expiry = cfg().get("expiry_date", "")
    if not expiry:
        return False
    try:
        from datetime import date
        return date.today() > date.fromisoformat(expiry)
    except Exception:
        return False

# ─── Main scan ────────────────────────────────────────────────────────────────

def run_once(driver: webdriver.Chrome):
    from agent_status import set_status
    s = cfg()
    if is_expired():
        print(f"[{datetime.now().strftime('%H:%M')}] פג תוקף ({s.get('expiry_date')}) — מפסיק.")
        set_status("facebook", "disabled", "פג תוקף הסוכן")
        raise SystemExit(0)
    if not s.get("enabled", True):
        print(f"[{datetime.now().strftime('%H:%M')}] סוכן מושהה")
        set_status("facebook", "disabled", "הסוכן מושהה")
        return
    if not s.get("sources", {}).get("facebook", True):
        print(f"[{datetime.now().strftime('%H:%M')}] פייסבוק מושבת")
        set_status("facebook", "disabled", "פייסבוק מושבת")
        return

    active_groups = dict(GROUPS)
    for name, gid in s.get("facebook_groups", {}).items():
        if name not in active_groups:
            active_groups[name] = {"id": str(gid), "dedicated": False}

    set_status("facebook", "scanning", f"מתחיל סריקה של {len(active_groups)} קבוצות…")

    print(f"\n{'='*55}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] סורק {len(active_groups)} קבוצות")
    print(f"{'='*55}")

    # Read settings once for the whole scan — passed into classifier per post
    max_price = s.get("max_price", 4100)
    min_rooms = s.get("min_rooms", 1.5)
    max_rooms = s.get("max_rooms", 3.5)

    seen      = load_seen()
    dismissed = load_dismissed()
    all_found = []

    # Cross-group dedup: track text fingerprints seen this run.
    # Same post can appear in multiple groups — keep only the first occurrence.
    seen_text_hashes: set[str] = set()

    total_groups = len(active_groups)
    for idx, (gname, ginfo) in enumerate(active_groups.items(), 1):
        set_status("facebook", "scanning", f"סורק: {gname} ({idx}/{total_groups})",
                   found=len(all_found))
        try:
            posts = scrape_group(driver, gname, ginfo,
                                 max_price=max_price, min_rooms=min_rooms, max_rooms=max_rooms)
            for p in posts:
                # Fingerprint = md5 of first 200 chars of preview (normalized)
                fp = hashlib.md5(
                    re.sub(r"\s+", " ", p.get("preview", ""))[:200]
                    .encode("utf-8", errors="replace")
                ).hexdigest()
                if fp not in seen_text_hashes:
                    seen_text_hashes.add(fp)
                    all_found.append(p)
                elif DEBUG:
                    print(f"  [cross-group dup] {p['title'][:60]}")
        except Exception as e:
            print(f"  שגיאה ב-{gname}: {e}")
        time.sleep(2)

    # All unseen posts (relevant + maybe + over_budget)
    new_posts = [
        p for p in all_found
        if p["id"] not in seen and p["id"] not in dismissed
    ]

    # Only send clearly relevant rental apartments to Telegram
    telegram_posts = [
        p for p in new_posts
        if p.get("classification") == "relevant_rental_apartment"
    ]

    print(f"\n{'-'*55}")
    print(
        f"נסרקו: {len(all_found)} | חדשים: {len(new_posts)} | "
        f"לטלגרם: {len(telegram_posts)} | נראו כבר: {len(seen)}"
    )

    if all_found:
        save_to_all_listings(all_found)
        push_to_server(all_found)

    if telegram_posts:
        import asyncio
        try:
            asyncio.run(send_telegram(telegram_posts))
        except Exception as e:
            print(f"  [Telegram] שגיאה: {e}")

    if new_posts:
        seen.update(p["id"] for p in new_posts)
        save_seen(seen)

    # Report final state + when the next scan is due
    interval = cfg().get("fb_interval_minutes", 30)
    from datetime import timedelta
    next_run = (datetime.now() + timedelta(minutes=interval)).strftime("%H:%M")
    set_status(
        "facebook", "idle",
        f"הסתיים — {len(new_posts)} חדשות, {len(telegram_posts)} נשלחו",
        found=len(new_posts), sent=len(telegram_posts),
        last_run=datetime.now().strftime("%H:%M"), next_run=next_run,
    )

    return len(new_posts)

# ─── Entry points ─────────────────────────────────────────────────────────────

def first_time_login():
    print("=" * 55)
    print(" הגדרה ראשונית — כניסה לפייסבוק")
    print(" Chrome יפתח — התחבר לפייסבוק, ואז סגור את הדפדפן")
    print("=" * 55)
    driver = make_driver(headless=False)
    driver.get("https://www.facebook.com/login")
    print("ממתין לסגירת Chrome...")
    try:
        while True:
            time.sleep(2)
            _ = driver.title
    except Exception:
        pass
    print("פרופיל נשמר!")

def main():
    s        = cfg()
    interval = s.get("fb_interval_minutes", 30)
    headless = not DEBUG

    print("=" * 55)
    print(f" סוכן פייסבוק — שכונה ב', באר שבע")
    print(f" מצב: {'DEBUG (Chrome גלוי)' if DEBUG else f'רגיל, כל {interval} דקות'}")
    print("=" * 55)

    driver = make_driver(headless=headless)
    try:
        if not is_logged_in(driver):
            driver.quit()
            print("\n⚠️  לא מחובר לפייסבוק.")
            print("הרץ קודם:  python facebook_agent.py --login")
            return

        print("מחובר לפייסבוק\n")
        run_once(driver)

        if DEBUG:
            print("\n[DEBUG] סיים ריצה אחת. יוצא.")
            return

        schedule.every(interval).minutes.do(run_once, driver)
        print(f"\nממתין... (סריקה כל {interval} דקות) | Ctrl+C להפסקה")

        while True:
            try:
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
    if "--login" in sys.argv:
        first_time_login()
    else:
        main()
