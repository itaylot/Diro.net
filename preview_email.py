"""Run this to generate a preview HTML file and open it in the browser."""
import webbrowser
from pathlib import Path
from email_template import build_email_html

SAMPLE = [
    {
        "source":  "Yad2",
        "address": "מינץ 28",
        "price":   2500,
        "rooms":   3.0,
        "floor":   "2",
        "size":    "58",
        "image":   "https://img.yad2.co.il/Pic/202604/29/2_2/o/y2_1pa_010383_20260429141619.jpeg",
        "url":     "https://www.yad2.co.il/item/dvtexcmx",
    },
    {
        "source":  "Yad2",
        "address": "חיים נחמן ביאליק 15",
        "price":   2400,
        "rooms":   2.0,
        "floor":   "3",
        "size":    "52",
        "image":   "",   # no cover image → shows gradient banner
        "url":     "https://www.yad2.co.il/item/b89zexol",
    },
    {
        "source":  "Facebook — דירות להשכרה באר שבע ללא תיווך",
        "address": "שכונה ב', באר שבע",
        "price":   3000,
        "rooms":   3.0,
        "floor":   "",
        "size":    "",
        "image":   "",
        "url":     "https://www.facebook.com/groups/1664792386922491",
        "preview": "דירת 3 חדרים להשכרה בשכונה ב׳, רחוב מינץ\nקומה ראשונה, משופצת\nמחיר: 3,000 ₪ לחודש כולל ארנונה\nפרטים בפרטי 📞",
    },
    {
        "source":  "Yad2",
        "address": "הנשיא 6",
        "price":   1900,
        "rooms":   2.0,
        "floor":   "1",
        "size":    "45",
        "image":   "",
        "url":     "https://www.yad2.co.il/item/4m1ramxl",
    },
]

out = Path(__file__).parent / "email_preview.html"
out.write_text(build_email_html(SAMPLE), encoding="utf-8")
print(f"נשמר: {out}")
webbrowser.open(str(out))
