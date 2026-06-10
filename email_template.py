"""
Beautiful RTL HTML email builder for apartment listings.
Used by both apartment_agent.py and facebook_agent.py
"""

from datetime import datetime

MAX_PRICE = 3500
MIN_ROOMS = 2
MAX_ROOMS = 3

SOURCE_COLORS = {
    "Yad2":     ("#2563eb", "#eff6ff"),
    "Homely":   ("#7c3aed", "#f5f3ff"),
    "Facebook": ("#1877f2", "#e7f0fd"),
}

BANNER_GRADIENTS = {
    "Yad2":     ("rgb(37,99,235)",   "rgb(30,58,138)"),
    "Homely":   ("rgb(124,58,237)",  "rgb(76,29,149)"),
    "Facebook": ("rgb(24,119,242)",  "rgb(12,74,158)"),
}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _source_label(source: str) -> str:
    return source.split("—")[0].strip()


def _source_badge(source: str) -> str:
    label = _source_label(source)
    color, bg = SOURCE_COLORS.get(label, ("#374151", "#f3f4f6"))
    return (
        f'<span style="display:inline-block;background:{bg};color:{color};'
        f'font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px;'
        f'letter-spacing:0.3px;margin-bottom:6px;">{source}</span>'
    )


def _chip(text: str, bg: str = "#f1f5f9", color: str = "#334155") -> str:
    return (
        f'<span style="display:inline-block;background:{bg};color:{color};'
        f'font-size:12px;font-weight:500;padding:3px 10px;border-radius:20px;'
        f'margin-left:4px;margin-bottom:4px;white-space:nowrap;">{text}</span>'
    )


def _is_real_apartment_image(url: str) -> bool:
    """Return True only if the URL looks like an actual apartment photo (not a logo)."""
    if not url:
        return False
    # Yad2 apartment photos are under img.yad2.co.il/Pic/
    if "img.yad2.co.il/Pic/" in url:
        return True
    # Facebook CDN images
    if "scontent" in url or "fbcdn.net" in url:
        return True
    # Homely CDN
    if "homely" in url and (".jpg" in url or ".jpeg" in url or ".png" in url):
        return True
    return False


# ─── Card builder ─────────────────────────────────────────────────────────────

def listing_card(lst: dict) -> str:
    raw_img  = lst.get("image", "").strip()
    img_url  = raw_img if _is_real_apartment_image(raw_img) else ""
    price    = lst.get("price", 0) or 0
    rooms    = lst.get("rooms", 0) or 0
    floor_   = str(lst.get("floor", "")).strip()
    size     = str(lst.get("size",  "")).strip()
    address  = lst.get("address", "")
    url      = lst.get("url", "#")
    preview  = lst.get("preview", "")
    source   = lst.get("source", "")
    label    = _source_label(source)

    price_str = f"&#8362;{price:,}&nbsp;/&nbsp;חודש" if price else "מחיר לא צוין"

    # ── Top image / banner ──
    c1, c2 = BANNER_GRADIENTS.get(label, ("rgb(51,65,85)", "rgb(15,23,42)"))
    if img_url:
        top_block = (
            f'<div style="width:100%;height:200px;overflow:hidden;'
            f'border-radius:12px 12px 0 0;background:{c1};">'
            f'<img src="{img_url}" alt="תמונת דירה" '
            f'style="width:100%;height:200px;object-fit:cover;display:block;" /></div>'
        )
    else:
        top_block = (
            f'<div style="width:100%;height:80px;border-radius:12px 12px 0 0;'
            f'background:linear-gradient(135deg,{c1} 0%,{c2} 100%);'
            f'display:flex;align-items:center;justify-content:center;'
            f'font-size:34px;text-align:center;padding:10px 0;">🏠</div>'
        )

    # ── Chips ──
    chips = ""
    if rooms:  chips += _chip(f"🛏 {rooms:.0f} חדרים", "#dbeafe", "#1e40af")
    if size:   chips += _chip(f"📐 {size} מ\"ר",       "#dcfce7", "#166534")
    if floor_: chips += _chip(f"🏢 קומה {floor_}",     "#fef9c3", "#854d0e")

    # ── Main content ──
    if preview:
        body = (
            f'<p style="font-size:13px;color:#374151;line-height:1.7;'
            f'white-space:pre-wrap;margin:4px 0 12px;word-break:break-word;">'
            f'{preview}</p>'
        )
    else:
        body = (
            f'<p style="font-size:17px;font-weight:700;color:#111827;'
            f'margin:4px 0 12px;">{address}</p>'
        )

    return f"""
<!--[card]-->
<div style="background:#fff;border-radius:12px;overflow:hidden;
            border:1px solid #e2e8f0;box-shadow:0 2px 8px rgba(0,0,0,0.06);
            max-width:520px;margin:0 auto 24px auto;">
  {top_block}
  <div style="padding:16px 18px 18px;direction:rtl;text-align:right;">
    {_source_badge(source)}
    {body}
    <div style="margin-bottom:14px;line-height:2.2;">{chips if chips else ""}</div>
    <div style="display:flex;align-items:center;justify-content:space-between;
                flex-wrap:wrap;gap:8px;">
      <span style="font-size:22px;font-weight:800;color:#16a34a;">{price_str}</span>
      <a href="{url}"
         style="display:inline-block;background:#2563eb;color:#ffffff;
                font-size:13px;font-weight:600;padding:8px 22px;
                border-radius:8px;text-decoration:none;white-space:nowrap;">
        לצפייה ←
      </a>
    </div>
  </div>
</div>"""


# ─── Full email ───────────────────────────────────────────────────────────────

def build_email_html(listings: list[dict], title: str = "") -> str:
    if not title:
        title = f"{len(listings)} דירות / פוסטים חדשים — שכונה ב׳, באר שבע"

    cards = "\n".join(listing_card(lst) for lst in listings)
    now   = datetime.now().strftime("%d/%m/%Y %H:%M")

    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title}</title>
  <style>
    body {{ margin:0;padding:0;background:#f1f5f9;
           font-family:Arial,'Segoe UI',Tahoma,sans-serif;direction:rtl; }}
    * {{ box-sizing:border-box; }}
  </style>
</head>
<body>

  <!-- ═══ HEADER ═══ -->
  <div style="background:linear-gradient(135deg,#1e40af 0%,#3b82f6 100%);
              padding:32px 24px 28px;text-align:center;">
    <div style="font-size:36px;margin-bottom:8px;">🏠</div>
    <h1 style="color:#ffffff;font-size:21px;font-weight:700;
               margin:0 0 8px;line-height:1.3;">{title}</h1>
    <p style="color:#bfdbfe;font-size:13px;margin:0;line-height:1.8;">
      {now}
      &nbsp;&bull;&nbsp; שכונה ב׳ בלבד
      &nbsp;&bull;&nbsp; {MIN_ROOMS}–{MAX_ROOMS} חדרים
      &nbsp;&bull;&nbsp; עד &#8362;{MAX_PRICE:,}/חודש
    </p>
  </div>

  <!-- ═══ CARDS ═══ -->
  <div style="padding:28px 16px 8px;">
    {cards}
  </div>

  <!-- ═══ FOOTER ═══ -->
  <div style="background:#e2e8f0;padding:16px;text-align:center;
              font-size:11px;color:#94a3b8;letter-spacing:0.3px;">
    סוכן חיפוש דירות אוטומטי &nbsp;&bull;&nbsp; Yad2 + Facebook Groups
  </div>

</body>
</html>"""
