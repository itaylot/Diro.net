"""
Tips Agent — מביא טיפ יומי לחיפוש דירה מהאינטרנט
מריץ פעם ביום ושומר ב-tips.json
"""

import app_env  # noqa: F401 — UTF-8 stdout + .env (must be first)
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests
import schedule

TIPS_FILE    = Path(__file__).parent / "tips.json"
SETTINGS_FILE = Path(__file__).parent / "settings.json"

# ── RSS sources ────────────────────────────────────────────────────────────────
RSS_FEEDS = [
    # Google News Hebrew — שכירות דירה טיפים
    "https://news.google.com/rss/search?q=%D7%98%D7%99%D7%A4%D7%99%D7%9D+%D7%A9%D7%9B%D7%99%D7%A8%D7%95%D7%AA+%D7%93%D7%99%D7%A8%D7%94&hl=iw&gl=IL&ceid=IL:iw",
    # Google News Hebrew — חיפוש דירה שוכר
    "https://news.google.com/rss/search?q=%D7%97%D7%99%D7%A4%D7%95%D7%A9+%D7%93%D7%99%D7%A8%D7%94+%D7%A9%D7%95%D7%9B%D7%A8&hl=iw&gl=IL&ceid=IL:iw",
    # Google News Hebrew — שוק השכירות ישראל
    "https://news.google.com/rss/search?q=%D7%A9%D7%95%D7%A7+%D7%94%D7%A9%D7%9B%D7%99%D7%A8%D7%95%D7%AA+%D7%99%D7%A9%D7%A8%D7%90%D7%9C&hl=iw&gl=IL&ceid=IL:iw",
]

# ── Evergreen tips bank (fallback) ────────────────────────────────────────────
EVERGREEN_TIPS = [
    {
        "title": "בדוק את חוזה השכירות לפני שחותמים",
        "summary": "קרא את כל סעיפי החוזה בעיון — שים לב במיוחד לתנאי יציאה מוקדמת, אחריות על תיקונים, ואפשרות להכניס שותפים. אם משהו לא ברור — תבקש הבהרה בכתב לפני החתימה.",
        "url": "https://www.yad2.co.il/blog",
        "source": "טיפ אוצר",
        "category": "חוזה וחוק",
    },
    {
        "title": "צלם את הדירה לפני הכניסה",
        "summary": "לפני שנכנסים לגור, צלם כל פגם קיים בדירה — קירות, ריצפה, ברזים, מכשירים. שלח את התמונות לבעל הדירה בוואטסאפ כדי שיהיה תיעוד תאריך. זה יחסוך ויכוחים על הפיקדון בסוף השכירות.",
        "url": "https://www.yad2.co.il/blog",
        "source": "טיפ אוצר",
        "category": "כניסה לדירה",
    },
    {
        "title": "בדוק עלויות חשמל לפני שחותמים",
        "summary": "שאל את בעל הדירה על ממוצע חשבון החשמל. דירה עם מזגן ישן, חלונות דולפים, או מפסקי חשמל ישנים יכולה לעלות הרבה יותר ממה שנראה. בחורף — שאל גם על חימום ועלויות גז.",
        "url": "https://www.nevo.co.il",
        "source": "טיפ אוצר",
        "category": "עלויות",
    },
    {
        "title": "הסכם שכירות — מה חייב להיות בו?",
        "summary": "חוזה שכירות חייב לכלול: שמות הצדדים, כתובת המושכר, גובה השכירות ומועד תשלום, תקופת השכירות, גובה הפיקדון, ותנאים לביטול. בלי אלה — החוזה עלול להיות חסר תוקף.",
        "url": "https://www.gov.il/he/departments/guides/renting-an-apartment",
        "source": "ממשלת ישראל",
        "category": "חוזה וחוק",
    },
    {
        "title": "שנת שכירות — מתי הזמן הטוב לחפש?",
        "summary": "השוק הכי חם הוא בקיץ (יולי-אוגוסט) — הרבה תחרות ומחירים גבוהים יותר. אם אפשר, חפש בחורף (ינואר-פברואר) — פחות מתחרים, בעלי דירות מוכנים יותר למו\"מ.",
        "url": "https://www.madlan.co.il",
        "source": "טיפ אוצר",
        "category": "אסטרטגיה",
    },
    {
        "title": "פיקדון — מה מותר ומה אסור?",
        "summary": "על פי החוק, בעל דירה יכול לדרוש פיקדון — בדרך כלל 1-3 חודשי שכירות. הפיקדון חייב להיות מוחזר בתוך 30-60 יום מסיום השכירות, בניכוי נזקים מוכחים בלבד. בקש תמיד קבלה על הפיקדון.",
        "url": "https://www.gov.il/he/departments/guides/renting-an-apartment",
        "source": "ממשלת ישראל",
        "category": "חוזה וחוק",
    },
    {
        "title": "איך לדעת אם המחיר הוגן?",
        "summary": "השתמש ב-Madlan.co.il כדי לראות מחירי שכירות בשכונה. השווה לפחות 5-10 דירות דומות באותו אזור. אם מחיר גבוה ב-15%+ — יש מקום למשא ומתן, במיוחד אם הדירה ריקה כבר כמה שבועות.",
        "url": "https://www.madlan.co.il",
        "source": "טיפ אוצר",
        "category": "מחיר ומשא ומתן",
    },
    {
        "title": "שאלות שחובה לשאול לפני השכירות",
        "summary": "לפני שמסכימים: מי אחראי על תיקונים? מה מצב הדוד שמש / מזגנים? האם מותר לגדל חיות מחמד? האם יש חניה? מה מצב הוועד בית? כמה שכנים יש? האם הגג דולף?",
        "url": "https://www.yad2.co.il/blog",
        "source": "טיפ אוצר",
        "category": "לפני החתימה",
    },
    {
        "title": "בדיקת שוכר — מה בעל הדירה יבדוק עליך?",
        "summary": "בעלי דירות בודקים לרוב: תלושי שכר, חוזה עבודה, המלצות משוכרים קודמים, לעיתים גם דוח אשראי. הכן אותם מראש כדי להגיב מהר ולהתקדם על דירות טובות לפני האחרים.",
        "url": "https://www.yad2.co.il/blog",
        "source": "טיפ אוצר",
        "category": "תהליך השכירות",
    },
    {
        "title": "ועד בית — למה זה חשוב?",
        "summary": "וועד בית פעיל = בניין מתוחזק. שאל כמה עולה ועד הבית ומה כולל. וועד גבוה מאוד (400+ ₪) לפעמים מכסה חימום מרכזי/מעלית — שאל פירוט. וועד נמוך מאוד עלול להצביע על בניין מוזנח.",
        "url": "https://www.nevo.co.il",
        "source": "טיפ אוצר",
        "category": "הבניין והשכנים",
    },
    {
        "title": "אזור שכונה ב' — מה כדאי לדעת?",
        "summary": "שכונה ב' בבאר שבע היא שכונה ותיקה ועם אופי קהילתי. קרובה לאוניברסיטת בן גוריון — זה מעלה את הביקוש. מחירי שכירות נוטים לעלות לקראת ספטמבר. כדאי לחפש באפריל-מאי לפני שהביקוש מזנק.",
        "url": "https://www.madlan.co.il",
        "source": "טיפ מקומי",
        "category": "שכונה ב׳",
    },
    {
        "title": "משא ומתן על שכירות — איך עושים את זה?",
        "summary": "הדירה ריקה יותר מחודש? — בעל הדירה מעוניין למלא אותה. הצע מחיר נמוך ב-5-8%, או בקש שהוא ישלם חלק מחינוך תשתיות (צביעה, תיקונים). עסקאות טובות נסגרות כשמציעים ערך — כמו חוזה ל-2 שנים.",
        "url": "https://www.yad2.co.il/blog",
        "source": "טיפ אוצר",
        "category": "מחיר ומשא ומתן",
    },
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_tips() -> list[dict]:
    if TIPS_FILE.exists():
        return json.loads(TIPS_FILE.read_text(encoding="utf-8"))
    return []

def save_tips(tips: list[dict]):
    TIPS_FILE.write_text(json.dumps(tips, ensure_ascii=False, indent=2), encoding="utf-8")

def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def already_added_today(tips: list[dict]) -> bool:
    return any(t.get("date", "")[:10] == today_str() for t in tips)

# ── Fetch from RSS ─────────────────────────────────────────────────────────────

def fetch_rss_tips() -> list[dict]:
    results = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ApartmentAgent/1.0)"}
    for feed_url in RSS_FEEDS:
        try:
            r = requests.get(feed_url, headers=headers, timeout=10)
            root = ET.fromstring(r.content)
            for item in root.iter("item"):
                title = item.findtext("title", "").strip()
                desc  = item.findtext("description", "").strip()
                link  = item.findtext("link", "").strip()
                # Clean HTML tags from description
                import re
                desc = re.sub(r"<[^>]+>", "", desc)[:300].strip()
                if title and len(title) > 10:
                    results.append({
                        "title":   title,
                        "summary": desc or title,
                        "url":     link,
                        "source":  "Google News",
                        "category": "עדכון שוק",
                    })
                if len(results) >= 5:
                    break
        except Exception as e:
            print(f"  [RSS] שגיאה: {e}")
        if len(results) >= 5:
            break
    return results

# ── Main ──────────────────────────────────────────────────────────────────────

def add_daily_tip():
    tips = load_tips()
    if already_added_today(tips):
        print(f"[{today_str()}] טיפ יומי כבר נוסף היום")
        return

    print(f"[{today_str()}] מחפש טיפ יומי...")

    # Try RSS first
    new_tips = fetch_rss_tips()

    if not new_tips:
        # Fallback: pick next evergreen tip (rotate)
        used = {t.get("title") for t in tips}
        for tip in EVERGREEN_TIPS:
            if tip["title"] not in used:
                new_tips = [tip]
                break
        if not new_tips:
            # All used — restart rotation
            new_tips = [EVERGREEN_TIPS[len(tips) % len(EVERGREEN_TIPS)]]

    # Take best 1-3 items, add date
    for t in new_tips[:3]:
        t["date"] = datetime.now().isoformat()
        tips.insert(0, t)  # newest first

    # Keep last 60 tips max
    save_tips(tips[:60])
    print(f"  נוספו {min(len(new_tips),3)} טיפים")


def main():
    print("=" * 50)
    print(" סוכן טיפים — מוסיף טיפ יומי לחיפוש דירה")
    print("=" * 50)

    # Seed evergreen tips on first run
    tips = load_tips()
    if not tips:
        print("הזרעת טיפי בסיס...")
        seeded = []
        for t in EVERGREEN_TIPS:
            t2 = dict(t)
            t2["date"] = "2026-01-01T00:00:00"
            seeded.append(t2)
        save_tips(seeded)
        print(f"  נוספו {len(seeded)} טיפי בסיס")

    add_daily_tip()

    schedule.every().day.at("09:30").do(add_daily_tip)
    print("ממתין... (פעם ביום ב-09:30) Ctrl+C להפסקה")

    while True:
        try:
            schedule.run_pending()
            time.sleep(60)
        except KeyboardInterrupt:
            print("\nהסוכן הופסק.")
            break


if __name__ == "__main__":
    main()
