"""
Apartment Dashboard — web interface for managing found listings.
Run:  python dashboard.py
Open: http://localhost:5050
"""

import app_env  # noqa: F401 — forces UTF-8 stdout + loads .env (must be first)
import app_auth
import app_tracking
import storage
import json, re, socket, threading, time as _time
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string, session, redirect
import requests as req_lib

app = Flask(__name__)
app.secret_key = app_auth.get_secret_key()
app.permanent_session_lifetime = timedelta(days=30)  # stay logged in for a month
LISTINGS_FILE  = Path(__file__).parent / "all_listings.json"
DISMISSED_FILE = Path(__file__).parent / "dismissed.json"
SETTINGS_FILE  = Path(__file__).parent / "settings.json"
TIPS_FILE      = Path(__file__).parent / "tips.json"

def load_listings():
    return storage.read_json(LISTINGS_FILE, [])
def load_dismissed():
    return set(storage.read_json(DISMISSED_FILE, []))
def load_settings():
    return storage.read_json(SETTINGS_FILE, {})
def save_settings(s):
    storage.write_json(SETTINGS_FILE, s)
def load_tips():
    return storage.read_json(TIPS_FILE, [])

SEEN_FILE = Path(__file__).parent / "seen_listings.json"
_scan_status = {"running": False, "last": "", "found": 0}

def load_seen():
    return set(storage.read_json(SEEN_FILE, []))
def save_seen(s):
    storage.write_json(SEEN_FILE, list(s))

def quick_yad2_scan():
    """Scan Yad2 directly via requests (no Selenium). Fast, lightweight."""
    global _scan_status
    from agent_status import set_status
    _scan_status = {"running": True, "last": "", "found": 0}
    set_status("yad2", "scanning", "סריקה ידנית מהאתר (Yad2)…")
    cfg = load_settings()
    mn  = cfg.get("min_rooms", 1.5)
    mx  = cfg.get("max_rooms", 3.5)
    mp  = cfg.get("max_price", 4100)

    url = (f"https://www.yad2.co.il/realestate/rent"
           f"?topArea=43&area=22&city=9000&neighborhood=39"
           f"&property=1&rooms={mn}-{mx}&price=0-{mp}")
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"),
        "Accept-Language": "he-IL,he;q=0.9",
    }
    try:
        r = req_lib.get(url, headers=headers, timeout=12)
        m = re.search(r'<script\s+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', r.text, re.DOTALL)
        if not m:
            _scan_status = {"running": False, "last": "לא נמצאו נתונים מ-Yad2", "found": 0}
            set_status("yad2", "error", "לא נמצאו נתונים מ-Yad2 (ייתכן Captcha)")
            return
        data = json.loads(m.group(1))
        feed = data["props"]["pageProps"]["feed"]
    except Exception as e:
        _scan_status = {"running": False, "last": f"שגיאה: {e}", "found": 0}
        set_status("yad2", "error", f"שגיאה בסריקה: {e}")
        return

    seen      = load_seen()
    dismissed = load_dismissed()

    # Parse the feed into a {id: listing} map first; merge into the on-disk
    # master list atomically below so concurrent writers don't lose updates.
    parsed = {}
    new_count = 0
    for section in ("private", "agency", "yad1", "platinum"):
        for item in feed.get(section, []):
            if not isinstance(item, dict): continue
            try:
                price = item.get("price", 0) or 0
                rooms = float(item.get("additionalDetails", {}).get("roomsCount", 0) or 0)
                if price <= 0 or price > mp or rooms < mn or rooms > mx + 0.5: continue
                token   = item.get("token", "")
                addr    = item.get("address", {})
                street  = addr.get("street", {}).get("text", "")
                house   = addr.get("house", {})
                full_addr = f"{street} {house.get('number', '')}".strip()
                lid = f"yad2_{token}"
                lst = {
                    "id":      lid,
                    "source":  "Yad2",
                    "title":   f"דירת {rooms:.0f} חדרים, שכונה ב'",
                    "address": full_addr,
                    "price":   int(price),
                    "rooms":   rooms,
                    "floor":   str(house.get("floor", "")),
                    "size":    str(item.get("additionalDetails", {}).get("squareMeter", "")),
                    "image":   (item.get("metaData") or {}).get("coverImage", ""),
                    "url":     f"https://www.yad2.co.il/item/{token}",
                    "contact": (item.get("customer", {}) or {}).get("name", ""),
                    "found_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                }
                parsed[lid] = lst
                if lid not in seen and lid not in dismissed:
                    new_count += 1
            except Exception:
                continue

    # Save updated listings — merge atomically into whatever is on disk now.
    state = {"total": 0}
    def _mut(existing_list):
        existing = {item["id"]: item for item in (existing_list or []) if isinstance(item, dict) and "id" in item}
        for lid, lst in parsed.items():
            # Don't overwrite an earlier found_at if we've seen this listing before
            if lid in existing and existing[lid].get("found_at"):
                lst["found_at"] = existing[lid]["found_at"]
            existing[lid] = lst
        state["total"] = len(existing)
        return list(reversed(list(existing.values())))
    storage.update_json(LISTINGS_FILE, _mut, [])
    _scan_status = {
        "running": False,
        "last":    datetime.now().strftime("%H:%M:%S"),
        "found":   new_count,
        "total":   state["total"],
    }
    set_status("yad2", "idle",
               f"סריקה ידנית הסתיימה — {new_count} חדשות",
               found=new_count, last_run=datetime.now().strftime("%H:%M"))

# ─────────────────────────────────────────────────────────────────────────────

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>דירונט — שכונה ב׳</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{
  font-family:'Plus Jakarta Sans',system-ui,sans-serif;
  direction:rtl;color:#1a1a1a;
  -webkit-font-smoothing:antialiased;min-height:100vh;
  background-color:#F2EDE4;
  background-image:radial-gradient(circle,#C8BDB0 1px,transparent 1px);
  background-size:26px 26px;
}
.hdr{background:linear-gradient(160deg,#0D2B1A 0%,#1A4A2E 55%,#163D24 100%);padding:0 40px;height:64px;display:flex;align-items:center;position:sticky;top:0;z-index:300;box-shadow:0 1px 0 rgba(255,255,255,.06),0 4px 24px rgba(0,0,0,.4)}
.hdr-in{width:100%;max-width:1320px;margin:0 auto;display:flex;align-items:center;justify-content:space-between}
.logo{display:flex;align-items:center;gap:12px;cursor:pointer}
.logo-mark{width:38px;height:38px;border-radius:11px;flex-shrink:0;background:linear-gradient(135deg,#4ade80,#16a34a);display:flex;align-items:center;justify-content:center;font-size:18px;box-shadow:0 2px 12px rgba(74,222,128,.35),inset 0 1px 0 rgba(255,255,255,.25)}
.logo-name{font-size:18px;font-weight:800;color:#fff;letter-spacing:-.5px;line-height:1}
.logo-tagline{font-size:11px;color:rgba(255,255,255,.4);margin-top:2px;font-style:italic}
.hdr-nav{display:flex;align-items:center;gap:2px}
.nav-tab{padding:8px 18px;border-radius:9px;font-size:13px;font-weight:600;border:none;background:none;cursor:pointer;font-family:inherit;color:rgba(255,255,255,.45);transition:all .2s}
.nav-tab:hover{color:rgba(255,255,255,.8);background:rgba(255,255,255,.08)}
.nav-tab.on{color:#fff;background:rgba(255,255,255,.13);box-shadow:inset 0 0 0 1px rgba(255,255,255,.14)}
.hdr-right{display:flex;align-items:center;gap:8px}
.live-pill{display:flex;align-items:center;gap:7px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);border-radius:100px;padding:6px 14px 6px 10px;font-size:11.5px;font-weight:500;color:rgba(255,255,255,.7)}
.dot{width:7px;height:7px;border-radius:50%;background:#4ade80;box-shadow:0 0 0 0 rgba(74,222,128,.5);animation:lp 2.2s infinite}
.dot.off{background:#f87171;animation:none;box-shadow:none}
@keyframes lp{0%{box-shadow:0 0 0 0 rgba(74,222,128,.5)}70%{box-shadow:0 0 0 8px rgba(74,222,128,0)}100%{box-shadow:0 0 0 0 rgba(74,222,128,0)}}
.icon-btn{width:36px;height:36px;border-radius:9px;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.12);display:flex;align-items:center;justify-content:center;cursor:pointer;transition:background .15s;flex-shrink:0}
.icon-btn:hover{background:rgba(255,255,255,.18)}
.icon-btn svg{color:rgba(255,255,255,.8)}
.arch-pill{display:flex;align-items:center;gap:7px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);border-radius:100px;padding:6px 14px 6px 10px;font-size:12px;font-weight:500;color:rgba(255,255,255,.65);cursor:pointer;transition:background .15s}
.arch-pill:hover{background:rgba(255,255,255,.15);color:#fff}
.arch-pill .n{background:rgba(255,255,255,.15);color:#fff;font-size:10px;font-weight:700;padding:1px 7px;border-radius:100px}
.meta{max-width:1320px;margin:0 auto;padding:10px 40px 4px;display:flex;align-items:center;gap:8px;font-size:12px;color:#9a8f84;flex-wrap:wrap}
.meta b{color:#6b5d54;font-weight:600}
.meta-sep{color:#d4c9be}
.scan-bar{max-width:1320px;margin:0 auto;padding:0 40px;display:none}
.scan-bar.show{display:block}
.scan-inner{background:linear-gradient(135deg,#ecfdf5,#d1fae5);border:1px solid #6ee7b7;border-radius:12px;padding:12px 18px;margin-bottom:14px;display:flex;align-items:center;gap:10px;font-size:13px;font-weight:500;color:#065f46}
.scan-spinner{width:16px;height:16px;border:2px solid #a7f3d0;border-top-color:#10b981;border-radius:50%;animation:sp .7s linear infinite;flex-shrink:0}
@keyframes sp{to{transform:rotate(360deg)}}
.spin{animation:sp .7s linear infinite}
.page{max-width:1320px;margin:0 auto;padding:20px 40px 72px}

/* TIP WIDGET */
.tip-widget{background:linear-gradient(135deg,#1A4A2E 0%,#2D7A50 50%,#1E5C38 100%);border-radius:20px;padding:28px 32px;margin-bottom:28px;display:flex;align-items:center;gap:24px;cursor:pointer;position:relative;overflow:hidden;box-shadow:0 4px 20px rgba(13,43,26,.25),0 1px 0 rgba(255,255,255,.06) inset;transition:transform .2s cubic-bezier(.34,1.4,.64,1),box-shadow .2s}
.tip-widget:hover{transform:translateY(-3px);box-shadow:0 12px 40px rgba(13,43,26,.35)}
.tip-widget::before{content:'';position:absolute;width:280px;height:280px;border-radius:50%;background:rgba(255,255,255,.05);top:-100px;left:-60px;pointer-events:none}
.tip-widget::after{content:'';position:absolute;width:180px;height:180px;border-radius:50%;background:rgba(74,222,128,.08);bottom:-80px;left:120px;pointer-events:none}
.tip-ico{width:56px;height:56px;border-radius:16px;flex-shrink:0;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.15);display:flex;align-items:center;justify-content:center;font-size:26px;position:relative;z-index:1}
.tip-content{flex:1;min-width:0;position:relative;z-index:1}
.tip-label{font-size:10px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;color:rgba(74,222,128,.9);margin-bottom:7px;display:flex;align-items:center;gap:6px}
.tip-label::before{content:'';width:16px;height:1px;background:rgba(74,222,128,.5)}
.tip-title{font-size:17px;font-weight:700;color:#fff;line-height:1.35;letter-spacing:-.3px;margin-bottom:6px}
.tip-body{font-size:13px;color:rgba(255,255,255,.6);line-height:1.65;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.tip-cta{position:relative;z-index:1;flex-shrink:0;display:flex;flex-direction:column;align-items:flex-start;gap:6px;padding-right:24px;border-right:1px solid rgba(255,255,255,.1)}
.tip-cta-text{font-size:12px;color:rgba(255,255,255,.5)}
.tip-cta-link{display:inline-flex;align-items:center;gap:5px;background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.2);color:#fff;padding:7px 14px;border-radius:9px;font-size:12.5px;font-weight:600;white-space:nowrap;transition:background .15s}
.tip-cta-link:hover{background:rgba(255,255,255,.22)}

/* CARDS */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:22px}
@keyframes cIn{from{opacity:0;transform:translateY(24px) scale(.97)}to{opacity:1;transform:translateY(0) scale(1)}}
.card{background:#fff;border-radius:20px;overflow:hidden;display:flex;flex-direction:column;border:1px solid rgba(255,255,255,.9);box-shadow:0 2px 8px rgba(90,60,20,.07),0 8px 32px rgba(90,60,20,.05);opacity:0;transition:transform .3s cubic-bezier(.34,1.4,.64,1),box-shadow .3s}
.card.vis{animation:cIn .5s cubic-bezier(.22,1,.36,1) both}
.card:hover{transform:translateY(-8px) rotate(.4deg);box-shadow:0 16px 48px rgba(90,60,20,.15),0 4px 12px rgba(90,60,20,.08)}
.card.dismissed{opacity:.2!important;filter:grayscale(1);pointer-events:none}
.card:nth-child(1){animation-delay:.04s}.card:nth-child(2){animation-delay:.09s}.card:nth-child(3){animation-delay:.14s}.card:nth-child(4){animation-delay:.18s}.card:nth-child(5){animation-delay:.22s}.card:nth-child(n+6){animation-delay:.26s}
.card-img-wrap{position:relative;overflow:hidden;height:215px;flex-shrink:0}
.card-img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .65s cubic-bezier(.25,.46,.45,.94)}
.card:hover .card-img{transform:scale(1.08)}
.img-over{position:absolute;inset:0;background:linear-gradient(to bottom,transparent 45%,rgba(0,0,0,.72)100%),linear-gradient(to top,transparent 85%,rgba(0,0,0,.2)100%)}
.card-banner{height:215px;display:flex;align-items:center;justify-content:center;font-size:52px;position:relative;flex-shrink:0}
.src-tag{position:absolute;top:14px;right:14px;z-index:2;font-size:10px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;padding:5px 12px;border-radius:100px;backdrop-filter:blur(16px) saturate(180%)}
.src-yad2{background:rgba(255,255,255,.92);color:#0D2B1A;border:1px solid rgba(255,255,255,.5)}
.src-fb  {background:rgba(29,78,216,.86);color:#fff}
.src-hom {background:rgba(0,0,0,.72);color:#fff}
.img-price{position:absolute;bottom:14px;right:16px;z-index:2}
.ip-num{font-size:24px;font-weight:800;color:#fff;letter-spacing:-.6px;line-height:1;text-shadow:0 2px 12px rgba(0,0,0,.6)}
.ip-sub{font-size:11px;color:rgba(255,255,255,.55);margin-top:3px}
.card-body{padding:20px 22px 22px;flex:1;display:flex;flex-direction:column;gap:13px}
.addr{font-size:16px;font-weight:700;color:#111;letter-spacing:-.3px;line-height:1.35}
.by  {font-size:11.5px;color:#aaa;margin-top:3px}
.prev{font-size:12.5px;color:#666;line-height:1.7;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{font-size:11.5px;font-weight:500;padding:5px 13px;border-radius:100px;white-space:nowrap}
.c-r{background:#f0fdf4;color:#16a34a;border:1px solid #bbf7d0}
.c-s{background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe}
.c-f{background:#fffbeb;color:#b45309;border:1px solid #fde68a}
.card-foot{display:flex;align-items:center;justify-content:space-between;padding-top:14px;border-top:1px solid #f5f4f1;gap:8px;flex-wrap:wrap;margin-top:auto}
.price-big{font-size:22px;font-weight:800;color:#0D2B1A;letter-spacing:-.5px;line-height:1}
.price-mo{font-size:11px;color:#aaa;margin-top:2px}
.price-unk{font-size:13px;color:#aaa}
.btns{display:flex;gap:7px}
.btn-open{display:inline-flex;align-items:center;gap:5px;background:linear-gradient(135deg,#1A4A2E,#0D2B1A);color:#fff;padding:10px 18px;border-radius:11px;font-size:12.5px;font-weight:600;font-family:inherit;text-decoration:none;border:none;cursor:pointer;box-shadow:0 2px 8px rgba(13,43,26,.3);transition:transform .15s,box-shadow .15s;white-space:nowrap}
.btn-open:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(13,43,26,.4)}
.btn-x{width:40px;height:40px;display:inline-flex;align-items:center;justify-content:center;background:transparent;border:1px solid #e8e5e0;color:#ccc;border-radius:11px;cursor:pointer;font-size:15px;transition:all .15s}
.btn-x:hover{background:#fef2f2;color:#dc2626;border-color:#fecaca}
.btn-undo{display:inline-flex;align-items:center;gap:5px;background:#f7f6f3;color:#555;border:1px solid #e8e5e0;padding:10px 14px;border-radius:11px;font-size:12.5px;font-weight:500;cursor:pointer;font-family:inherit}

/* EMPTY */
@keyframes bob{0%,100%{transform:translateY(0) rotate(-2deg)}50%{transform:translateY(-14px) rotate(2deg)}}
@keyframes fup{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
.empty{display:flex;flex-direction:column;align-items:center;text-align:center;padding:80px 24px}
.empty-visual{position:relative;margin-bottom:30px;animation:bob 5s ease-in-out infinite}
.empty-house{font-size:80px;line-height:1;filter:drop-shadow(0 12px 24px rgba(0,0,0,.12))}
.empty-badge{position:absolute;bottom:-6px;right:-12px;background:linear-gradient(135deg,#4ade80,#16a34a);color:#fff;font-size:10px;font-weight:700;padding:3px 10px;border-radius:100px;white-space:nowrap;box-shadow:0 4px 12px rgba(22,163,74,.4)}
.empty h3{font-size:22px;font-weight:800;color:#1a1a1a;letter-spacing:-.4px;margin-bottom:10px;animation:fup .4s .1s both}
.empty p {font-size:14.5px;color:#888;line-height:1.75;max-width:320px;animation:fup .4s .2s both}

/* TIPS */
.tips-header{margin-bottom:28px}
.tips-header h2{font-size:26px;font-weight:800;letter-spacing:-.5px}
.tips-header p{font-size:14px;color:#888;margin-top:6px}
.tips-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:22px}
.tip-card{background:#fff;border-radius:18px;border:1px solid rgba(255,255,255,.9);padding:24px 26px;display:flex;flex-direction:column;gap:13px;box-shadow:0 2px 8px rgba(90,60,20,.06),0 8px 28px rgba(90,60,20,.04);animation:cIn .45s cubic-bezier(.22,1,.36,1) both;transition:transform .25s cubic-bezier(.34,1.4,.64,1),box-shadow .25s}
.tip-card:hover{transform:translateY(-5px);box-shadow:0 12px 40px rgba(90,60,20,.1)}
.tc-cat{display:inline-flex;align-items:center;gap:6px;font-size:10.5px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;padding:5px 12px;border-radius:100px;align-self:flex-start}
.tc-local{background:#f0fdf4;color:#16a34a;border:1px solid #bbf7d0}
.tc-legal{background:#fff7ed;color:#c2410c;border:1px solid #fed7aa}
.tc-money{background:#fefce8;color:#a16207;border:1px solid #fde68a}
.tc-news {background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe}
.tc-strat{background:#fdf4ff;color:#9333ea;border:1px solid #e9d5ff}
.tc-other{background:#f5f5f5;color:#555;border:1px solid #e5e5e5}
.tc-title{font-size:16px;font-weight:700;color:#111;line-height:1.4;letter-spacing:-.2px}
.tc-body {font-size:13px;color:#555;line-height:1.75;flex:1}
.tc-foot{display:flex;align-items:center;justify-content:space-between;padding-top:12px;border-top:1px solid #f5f4f1;font-size:11.5px;color:#aaa}
.tc-link{color:#1d4ed8;text-decoration:none;font-weight:600;display:flex;align-items:center;gap:4px;font-size:11.5px}
.tc-link:hover{text-decoration:underline}

/* PANELS */
.ov{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:400;opacity:0;pointer-events:none;transition:opacity .25s;backdrop-filter:blur(3px)}
.ov.open{opacity:1;pointer-events:all}
.panel{position:fixed;top:0;left:0;height:100%;width:min(520px,100%);background:#fff;z-index:401;transform:translateX(-100%);transition:transform .32s cubic-bezier(.4,0,.2,1);overflow-y:auto;display:flex;flex-direction:column}
.panel.open{transform:translateX(0)}
.drawer{position:fixed;top:0;right:0;height:100%;width:min(440px,100%);background:#fff;z-index:401;transform:translateX(100%);transition:transform .32s cubic-bezier(.4,0,.2,1);overflow-y:auto;display:flex;flex-direction:column}
.drawer.open{transform:translateX(0)}
.ph{display:flex;align-items:center;justify-content:space-between;padding:20px 26px;border-bottom:1px solid #e8e5e0;position:sticky;top:0;background:#fff;z-index:2}
.ph-title{font-size:17px;font-weight:700;letter-spacing:-.3px}
.ph-close{width:32px;height:32px;border-radius:8px;border:1px solid #e8e5e0;background:none;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:16px;color:#888;transition:background .15s}
.ph-close:hover{background:#f5f4f1}
.pb{padding:22px 26px;flex:1}
.arc{background:#fafaf8;border:1px solid #e8e5e0;border-radius:12px;padding:14px 16px;margin-bottom:10px;display:flex;align-items:center;gap:12px}
.arc-info{flex:1;min-width:0}
.arc-addr{font-size:14px;font-weight:700;color:#111;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.arc-meta{font-size:11.5px;color:#aaa;margin-top:3px}
.arc-price{font-size:15px;font-weight:800;color:#0D2B1A;white-space:nowrap}
.arc-btn{padding:7px 13px;border-radius:9px;background:#fff;border:1px solid #e8e5e0;font-size:12px;font-weight:500;cursor:pointer;font-family:inherit;transition:all .15s}
.arc-btn:hover{background:#f0fdf4;border-color:#bbf7d0;color:#16a34a}

/* SETTINGS */
.s-blk{background:#fafaf8;border:1px solid #e8e5e0;border-radius:13px;padding:20px 22px;margin-bottom:12px}
.s-ttl{font-size:10px;font-weight:700;letter-spacing:1.1px;text-transform:uppercase;color:#bbb;margin-bottom:15px;padding-bottom:12px;border-bottom:1px solid #f0ede8}
.f-row{display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap}
.f-lbl{font-size:13px;font-weight:500;color:#444;min-width:120px}
.f-in{border:1px solid #e8e5e0;border-radius:8px;padding:8px 12px;font-size:13px;width:130px;direction:ltr;text-align:center;background:#fff;font-family:inherit;color:#111;transition:border .15s,box-shadow .15s}
.f-in:focus{outline:none;border-color:#16a34a;box-shadow:0 0 0 3px rgba(22,163,74,.1)}
.tog-on{padding:8px 18px;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;border:1px solid #bbf7d0;font-family:inherit;background:#f0fdf4;color:#16a34a}
.tog-off{padding:8px 18px;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;border:1px solid #fecaca;font-family:inherit;background:#fef2f2;color:#dc2626}
.s-btn{background:linear-gradient(135deg,#1A4A2E,#0D2B1A);color:#fff;padding:11px 20px;border-radius:10px;font-size:13.5px;font-weight:600;cursor:pointer;border:none;width:100%;margin-top:8px;transition:opacity .15s;font-family:inherit;box-shadow:0 2px 8px rgba(13,43,26,.25)}
.s-btn:hover{opacity:.88}
.cb-row{display:flex;align-items:center;gap:9px;margin-bottom:10px;font-size:13px;font-weight:500;color:#444}
.cb-row input{width:15px;height:15px;cursor:pointer;accent-color:#16a34a}
.t-pill{display:inline-flex;align-items:center;gap:6px;background:#f5f4f1;color:#444;border:1px solid #e8e5e0;padding:4px 11px;border-radius:100px;font-size:12px;font-weight:600;margin-left:6px;margin-bottom:6px}
.t-pill button{background:none;border:none;color:#ccc;cursor:pointer;font-size:14px;line-height:1;transition:color .15s}
.t-pill button:hover{color:#dc2626}
.g-row{display:flex;align-items:center;gap:8px;margin-bottom:9px}
.g-nm{font-size:12.5px;font-weight:500;color:#444;flex:1}
.g-id{font-size:11px;color:#bbb;direction:ltr;font-family:monospace}
.btn-rm{background:none;border:none;color:#ccc;cursor:pointer;font-size:14px;padding:2px 5px;border-radius:5px;transition:all .15s}
.btn-rm:hover{color:#dc2626;background:#fef2f2}
.add-row{display:flex;gap:7px;margin-top:10px}
.add-row input{flex:1;border:1px solid #e8e5e0;border-radius:8px;padding:8px 11px;font-size:12.5px;background:#fff;font-family:inherit;color:#111}
.add-row input:focus{outline:none;border-color:#16a34a;box-shadow:0 0 0 3px rgba(22,163,74,.1)}
.btn-add{background:linear-gradient(135deg,#1A4A2E,#0D2B1A);color:#fff;border:none;border-radius:8px;padding:8px 14px;font-size:12.5px;font-weight:600;cursor:pointer;white-space:nowrap;font-family:inherit;box-shadow:0 2px 6px rgba(13,43,26,.2)}
.btn-add:hover{opacity:.88}

/* SKELETONS */
@keyframes sk{0%{background-position:200% 0}100%{background-position:-200% 0}}
.sk-card{background:#fff;border-radius:20px;border:1px solid rgba(255,255,255,.8);box-shadow:0 2px 8px rgba(90,60,20,.06);overflow:hidden}
.sk-img{height:215px;background:linear-gradient(90deg,#ede8e2 25%,#e3ddd6 50%,#ede8e2 75%);background-size:200% 100%;animation:sk 1.7s ease infinite}
.sk-body{padding:20px 22px;display:flex;flex-direction:column;gap:10px}
.sk-ln{border-radius:6px;background:linear-gradient(90deg,#ede8e2 25%,#e3ddd6 50%,#ede8e2 75%);background-size:200% 100%;animation:sk 1.7s ease infinite}

/* TOAST */
@keyframes tin{from{opacity:0;transform:translateX(-50%) translateY(16px) scale(.95)}to{opacity:1;transform:translateX(-50%) translateY(0) scale(1)}}
.toast{position:fixed;bottom:28px;left:50%;transform:translateX(-50%);background:#0D2B1A;color:#fff;padding:13px 26px;border-radius:100px;font-size:13.5px;font-weight:500;font-family:inherit;pointer-events:none;z-index:9999;white-space:nowrap;display:none;box-shadow:0 8px 40px rgba(13,43,26,.4)}
.toast.show{display:block;animation:tin .3s cubic-bezier(.34,1.56,.64,1) forwards}

/* MATCH BADGE + FRESHNESS + WHY (premium card intel) */
.match-badge{position:absolute;top:14px;left:14px;z-index:3;display:flex;align-items:center;gap:6px;padding:5px 12px 5px 9px;border-radius:100px;font-size:11px;font-weight:700;backdrop-filter:blur(16px) saturate(180%);box-shadow:0 4px 14px rgba(0,0,0,.25)}
.match-badge .mb-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.mb-hot {background:rgba(254,242,242,.94);color:#b91c1c}.mb-hot  .mb-dot{background:#ef4444;box-shadow:0 0 0 3px rgba(239,68,68,.25)}
.mb-good{background:rgba(240,253,244,.94);color:#15803d}.mb-good .mb-dot{background:#22c55e;box-shadow:0 0 0 3px rgba(34,197,94,.25)}
.mb-rev {background:rgba(255,251,235,.94);color:#a16207}.mb-rev  .mb-dot{background:#f59e0b;box-shadow:0 0 0 3px rgba(245,158,11,.25)}
.fresh{position:absolute;bottom:14px;left:16px;z-index:2;display:inline-flex;align-items:center;gap:5px;font-size:10.5px;font-weight:600;color:#fff;background:rgba(0,0,0,.45);backdrop-filter:blur(10px);padding:4px 10px;border-radius:100px}
.fresh.new{background:rgba(22,163,74,.85)}
.why{display:flex;flex-wrap:wrap;gap:5px}
.why-lbl{font-size:9.5px;font-weight:700;letter-spacing:.7px;text-transform:uppercase;color:#bbb;width:100%;margin-bottom:1px}
.why-chip{font-size:10.5px;font-weight:600;padding:3px 9px;border-radius:7px;background:#f0fdf4;color:#16803d;border:1px solid #d6f5e0}

/* AGENT STATUS (live "what is it doing now") */
.agent-status{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px}
.ag-card{flex:1;min-width:240px;background:#fff;border:1px solid rgba(255,255,255,.9);border-radius:14px;padding:13px 16px;display:flex;align-items:center;gap:12px;box-shadow:0 2px 8px rgba(90,60,20,.05);position:relative;overflow:hidden;transition:border .2s,box-shadow .2s}
.ag-card.scanning{border-color:#6ee7b7;box-shadow:0 0 0 2px rgba(16,185,129,.14)}
.ag-card.error{border-color:#fecaca;box-shadow:0 0 0 2px rgba(239,68,68,.1)}
.ag-led{width:11px;height:11px;border-radius:50%;flex-shrink:0;background:#cbd5e1}
.ag-led.scanning{background:#10b981;animation:agpulse 1.3s infinite}
.ag-led.idle{background:#94a3b8}.ag-led.error{background:#ef4444}.ag-led.disabled{background:#cbd5e1}
@keyframes agpulse{0%{box-shadow:0 0 0 0 rgba(16,185,129,.5)}70%{box-shadow:0 0 0 7px rgba(16,185,129,0)}100%{box-shadow:0 0 0 0 rgba(16,185,129,0)}}
.ag-main{flex:1;min-width:0}
.ag-name{font-size:13px;font-weight:700;color:#1a1a1a;display:flex;align-items:center;gap:7px}
.ag-now{color:#10b981;font-size:10.5px;font-weight:700}
.ag-detail{font-size:12px;color:#6b5d54;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ag-meta{font-size:10.5px;color:#b0a89e;margin-top:3px}
.ag-prog{position:absolute;bottom:0;right:0;height:3px;width:35%;background:linear-gradient(90deg,#34d399,#10b981);border-radius:3px;animation:agbar 1.25s ease-in-out infinite}
@keyframes agbar{0%{transform:translateX(120%)}100%{transform:translateX(-320%)}}

/* CONTROLS BAR */
.controls{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:20px}
.search-wrap{position:relative;flex:1;min-width:200px}
.search-wrap svg{position:absolute;right:13px;top:50%;transform:translateY(-50%);color:#c2b8ac;pointer-events:none}
.search-in{width:100%;border:1px solid #e3ddd4;border-radius:12px;padding:11px 40px 11px 14px;font-size:13.5px;background:#fff;font-family:inherit;color:#111;transition:border .15s,box-shadow .15s}
.search-in:focus{outline:none;border-color:#16a34a;box-shadow:0 0 0 3px rgba(22,163,74,.1)}
.ctrl-sel{border:1px solid #e3ddd4;border-radius:12px;padding:11px 14px;font-size:13px;font-weight:600;background:#fff;font-family:inherit;color:#444;cursor:pointer;transition:border .15s}
.ctrl-sel:focus{outline:none;border-color:#16a34a}

/* STATS STRIP (widgets) */
.stats-strip{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:22px}
.stat{background:#fff;border:1px solid rgba(255,255,255,.9);border-radius:16px;padding:16px 18px;cursor:pointer;transition:transform .2s cubic-bezier(.34,1.4,.64,1),box-shadow .2s;box-shadow:0 2px 8px rgba(90,60,20,.05);position:relative;overflow:hidden}
.stat:hover{transform:translateY(-3px);box-shadow:0 10px 28px rgba(90,60,20,.1)}
.stat.on{border-color:#16a34a;box-shadow:0 0 0 2px rgba(22,163,74,.18)}
.stat-num{font-size:26px;font-weight:800;letter-spacing:-1px;line-height:1;color:#0D2B1A}
.stat-lbl{font-size:11.5px;font-weight:600;color:#9a8f84;margin-top:6px}
.stat-ico{position:absolute;top:14px;left:14px;font-size:18px;opacity:.5}
.stat.s-hot .stat-num{color:#dc2626}.stat.s-new .stat-num{color:#16a34a}.stat.s-rev .stat-num{color:#d97706}
.stat.s-fav .stat-num{color:#e11d48}
@media(max-width:640px){.stats-strip{grid-template-columns:repeat(2,1fr)}}

/* USER + LOGOUT (header) */
.user-pill{display:flex;align-items:center;gap:7px;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.14);border-radius:100px;padding:5px 8px 5px 13px;font-size:12.5px;font-weight:600;color:#fff}
.user-av{width:24px;height:24px;border-radius:50%;background:linear-gradient(135deg,#4ade80,#16a34a);display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:800;color:#06281a;text-transform:uppercase}
.logout-btn{background:none;border:none;color:rgba(255,255,255,.5);cursor:pointer;font-size:11.5px;font-weight:600;padding:6px 8px;border-radius:7px;font-family:inherit;transition:all .15s}
.logout-btn:hover{color:#fff;background:rgba(255,255,255,.1)}
/* HAMBURGER + SIDE MENU */
.menu-btn{width:42px;height:42px;border-radius:11px;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.18);color:#fff;display:flex;align-items:center;justify-content:center;cursor:pointer;flex-shrink:0;transition:background .15s}
.menu-btn:hover{background:rgba(255,255,255,.22)}
.menu-drawer{width:min(330px,86vw)}
.menu-pb{padding:12px 12px 28px}
.menu-sec{font-size:10px;font-weight:700;letter-spacing:1.1px;text-transform:uppercase;color:#bbb;margin:16px 12px 6px}
.menu-item{display:flex;align-items:center;gap:11px;width:100%;text-align:right;background:none;border:none;font-family:inherit;font-size:15.5px;font-weight:600;color:#333;padding:14px 14px;border-radius:12px;cursor:pointer;transition:background .12s}
.menu-item:hover,.menu-item:active{background:#f5f4f1}
.menu-item.on{background:#f0fdf4;color:#16a34a}
.menu-item.danger{color:#dc2626}.menu-item.danger:hover{background:#fef2f2}
.menu-count{margin-inline-start:auto;background:#eee;color:#888;font-size:11px;font-weight:700;padding:1px 9px;border-radius:100px}
/* tracked-state for the card "add to tracking" button */
.btn-track.is-tracked{width:auto;padding:0 12px;gap:4px;background:#f0fdf4;border-color:#bbf7d0;color:#16a34a;font-size:12.5px;font-weight:700;cursor:default}
/* MOBILE BOTTOM NAV (thumb-reachable primary navigation) */
.botnav{display:none}
@media(max-width:640px){
  .botnav{display:flex;position:fixed;bottom:0;left:0;right:0;z-index:350;background:rgba(255,255,255,.97);backdrop-filter:blur(14px) saturate(180%);border-top:1px solid #e8e2d8;padding:7px 4px calc(7px + env(safe-area-inset-bottom));box-shadow:0 -3px 18px rgba(90,60,20,.09)}
  .botnav button{flex:1;display:flex;flex-direction:column;align-items:center;gap:3px;background:none;border:none;font-family:inherit;font-size:10.5px;font-weight:700;color:#a99f93;padding:6px 2px;cursor:pointer;border-radius:12px;transition:color .15s,transform .12s}
  .botnav button:active{transform:scale(.92)}
  .botnav button.on{color:#16a34a}
  .botnav .bn-ico{font-size:21px;line-height:1;filter:grayscale(.4)}
  .botnav button.on .bn-ico{filter:grayscale(0)}
  .page{padding-bottom:92px}            /* clear the bottom bar */
}

/* HEART (favorite) button */
.btn-fav{width:40px;height:40px;display:inline-flex;align-items:center;justify-content:center;background:#fff;border:1px solid #e8e5e0;border-radius:11px;cursor:pointer;font-size:17px;line-height:1;transition:all .15s;padding:0}
.btn-fav:hover{border-color:#fbcfe8;background:#fdf2f8}
.btn-fav.on{background:#fff1f2;border-color:#fecdd3}
.btn-fav .h-empty{display:inline}.btn-fav .h-full{display:none}
.btn-fav.on .h-empty{display:none}.btn-fav.on .h-full{display:inline;animation:hpop .35s cubic-bezier(.34,1.56,.64,1)}
@keyframes hpop{0%{transform:scale(.6)}60%{transform:scale(1.25)}100%{transform:scale(1)}}

/* ADD-APARTMENT button (header) */
.add-btn{display:inline-flex;align-items:center;gap:5px;background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.2);color:#fff;padding:8px 15px;border-radius:10px;font-size:12.5px;font-weight:700;font-family:inherit;cursor:pointer;white-space:nowrap;transition:background .15s}
.add-btn:hover{background:rgba(255,255,255,.24)}

/* CENTERED MODAL (add apartment) */
.modal-ov{position:fixed;inset:0;background:rgba(0,0,0,.5);backdrop-filter:blur(3px);z-index:500;display:none;align-items:center;justify-content:center;padding:20px}
.modal-ov.open{display:flex}
.modal{background:#fff;border-radius:20px;width:100%;max-width:480px;max-height:90vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,.3);animation:min .25s cubic-bezier(.34,1.4,.64,1)}
@keyframes min{from{opacity:0;transform:translateY(20px) scale(.97)}to{opacity:1;transform:translateY(0) scale(1)}}
.modal-head{display:flex;align-items:center;justify-content:space-between;padding:20px 24px;border-bottom:1px solid #eee}
.modal-head h3{font-size:17px;font-weight:800}
.modal-body{padding:22px 24px}
.mf{margin-bottom:14px}
.mf label{display:block;font-size:12px;font-weight:600;color:#6b5d54;margin-bottom:6px}
.mf input,.mf textarea,.mf select{width:100%;border:1px solid #e3ddd4;border-radius:10px;padding:11px 13px;font-size:14px;font-family:inherit;color:#111;background:#fff}
.mf textarea{resize:vertical;min-height:70px}
.mf input:focus,.mf textarea:focus,.mf select:focus{outline:none;border-color:#16a34a;box-shadow:0 0 0 3px rgba(22,163,74,.1)}
.mf-row{display:flex;gap:10px}.mf-row .mf{flex:1}

/* TRACKING BOARD */
.trk-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:22px;flex-wrap:wrap;gap:12px}
.trk-head h2{font-size:26px;font-weight:800;letter-spacing:-.5px}
.trk-head p{font-size:14px;color:#888;margin-top:4px}
.trk-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:18px}
.trk-card{background:#fff;border-radius:18px;border:1px solid rgba(255,255,255,.9);box-shadow:0 2px 8px rgba(90,60,20,.06),0 8px 28px rgba(90,60,20,.04);padding:18px 20px;display:flex;flex-direction:column;gap:12px;border-top:4px solid #cbd5e1}
.trk-card.st-to_contact{border-top-color:#3b82f6}.trk-card.st-scheduled{border-top-color:#a855f7}.trk-card.st-visited{border-top-color:#f59e0b}.trk-card.st-candidate{border-top-color:#22c55e}.trk-card.st-rejected{border-top-color:#ef4444;opacity:.7}
.trk-top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}
.trk-addr{font-size:16px;font-weight:800;color:#111;line-height:1.3}
.trk-sub{font-size:12px;color:#9a8f84;margin-top:3px}
.trk-status-sel{border:1px solid #e3ddd4;border-radius:8px;padding:6px 8px;font-size:12px;font-weight:700;font-family:inherit;cursor:pointer;background:#fafaf8;color:#444}
.trk-meta{display:flex;flex-wrap:wrap;gap:7px}
.trk-chip{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:600;background:#f5f4f1;color:#555;border:1px solid #e8e5e0;padding:5px 11px;border-radius:100px}
.trk-field{display:flex;flex-direction:column;gap:5px}
.trk-field label{font-size:10.5px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:#bbb}
.trk-field input,.trk-field textarea{border:1px solid #ece8e2;border-radius:9px;padding:9px 11px;font-size:13px;font-family:inherit;color:#222;background:#fcfbf9;width:100%}
.trk-field textarea{resize:vertical;min-height:54px}
.trk-field input:focus,.trk-field textarea:focus{outline:none;border-color:#16a34a;background:#fff;box-shadow:0 0 0 3px rgba(22,163,74,.08)}
.stars{display:flex;gap:3px;font-size:20px;cursor:pointer;user-select:none}
.star{color:#e0d9cf;transition:transform .1s}.star.on{color:#f59e0b}.star:hover{transform:scale(1.15)}
.trk-actions{display:flex;gap:7px;flex-wrap:wrap;border-top:1px solid #f5f4f1;padding-top:12px}
.trk-act{flex:1;min-width:0;display:inline-flex;align-items:center;justify-content:center;gap:5px;border:1px solid #e8e5e0;background:#fff;border-radius:9px;padding:9px;font-size:12px;font-weight:600;font-family:inherit;cursor:pointer;color:#444;text-decoration:none;transition:all .15s}
.trk-act:hover{background:#f7f6f3}
.trk-act.call:hover{background:#f0fdf4;border-color:#bbf7d0;color:#16a34a}
.trk-act.nav:hover{background:#eff6ff;border-color:#bfdbfe;color:#1d4ed8}
.trk-act.del:hover{background:#fef2f2;border-color:#fecaca;color:#dc2626}
.btn-track{width:40px;height:40px;display:inline-flex;align-items:center;justify-content:center;background:#fff;border:1px solid #e8e5e0;border-radius:11px;cursor:pointer;font-size:15px;line-height:1;padding:0;transition:all .15s}
.btn-track:hover{background:#f5f3ff;border-color:#ddd6fe}
/* read-only status badge on tracking cards */
.trk-badge{font-size:11px;font-weight:700;padding:5px 12px;border-radius:100px;white-space:nowrap;flex-shrink:0}
.tb-to_contact{background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe}
.tb-scheduled{background:#faf5ff;color:#9333ea;border:1px solid #e9d5ff}
.tb-visited{background:#fffbeb;color:#b45309;border:1px solid #fde68a}
.tb-candidate{background:#f0fdf4;color:#16a34a;border:1px solid #bbf7d0}
.tb-rejected{background:#fef2f2;color:#dc2626;border:1px solid #fecaca}
.trk-notes{font-size:13px;color:#555;line-height:1.65;background:#fafaf8;border:1px solid #f0ede8;border-radius:10px;padding:11px 13px;white-space:pre-wrap}
.trk-act.edit:hover{background:#f5f3ff;border-color:#ddd6fe;color:#7c3aed}

@media(max-width:640px){
  .hdr{padding:0 14px;height:58px}
  .logo-tagline{display:none}
  .hdr-right{gap:8px}
  .lp-lbl{display:none}                 /* keep the live dot, drop its label */
  .live-pill{padding:7px}
  .up-name{display:none}                 /* avatar identifies the user */
  .user-pill{padding:5px}
  .meta,.scan-bar,.page{padding-inline:16px}
  .grid,.tips-grid,.trk-grid,.fav-grid{grid-template-columns:1fr!important;gap:16px}
  #fav-grid{grid-template-columns:1fr}
  .controls{gap:8px}
  .search-wrap{flex-basis:100%}
  .ctrl-sel{flex:1}
  .tip-widget{flex-direction:column;gap:16px}
  .tip-cta{padding-right:0;border-right:none;border-top:1px solid rgba(255,255,255,.1);padding-top:14px;width:100%}
  .panel,.drawer{width:100%}
  .menu-drawer{width:min(330px,86vw)}    /* menu stays a drawer, not full-screen */
  .trk-head h2{font-size:22px}
  .modal{border-radius:18px}
  /* comfier tap targets on phones */
  .btn-x,.btn-fav,.btn-track{width:44px;height:44px}
  .trk-act{padding:11px 9px}
}
@media(min-width:481px){.fav-grid{grid-template-columns:repeat(auto-fill,minmax(310px,1fr))}}
</style>
</head>
<body>
<header class="hdr">
  <div class="hdr-in">
    <!-- menu button is first in DOM → appears on the RIGHT in RTL (closest to the drawer that opens from the right) -->
    <button class="menu-btn" onclick="openMenu()" aria-label="תפריט">
      <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
    </button>
    <div class="logo" onclick="showView('listings')">
      <div class="logo-mark">🏠</div>
      <div><div class="logo-name">דירונט</div><div class="logo-tagline">מוצא את הדירה שלך</div></div>
    </div>
    <div class="hdr-right">
      <div class="live-pill"><span class="dot" id="ag-dot"></span><span id="ag-lbl" class="lp-lbl">טוען</span></div>
      <div class="user-pill"><span class="user-av" id="user-av">?</span><span class="up-name" id="user-name">…</span></div>
    </div>
  </div>
</header>
<div class="ov" id="menu-ov" onclick="closeMenu()"></div>
<nav class="drawer menu-drawer" id="menu-drawer">
  <div class="ph"><span class="ph-title">תפריט</span><button class="ph-close" onclick="closeMenu()">✕</button></div>
  <div class="menu-pb">
    <div class="menu-sec">ניווט</div>
    <button class="menu-item" id="mn-listings" onclick="menuGo('listings')">🏠 דירות</button>
    <button class="menu-item" id="mn-favorites" onclick="menuGo('favorites')">❤️ המועדפים שלי</button>
    <button class="menu-item" id="mn-tracking" onclick="menuGo('tracking')">📋 מעקב</button>
    <button class="menu-item" id="mn-tips" onclick="menuGo('tips')">💡 טיפים</button>
    <div class="menu-sec">פעולות</div>
    <button class="menu-item" onclick="closeMenu();openAdd()">➕ הוסף דירה</button>
    <button class="menu-item" onclick="closeMenu();scanNow()">🔄 סרוק עכשיו</button>
    <button class="menu-item" onclick="closeMenu();openArchive()">🗄 ארכיון <span class="menu-count" id="menu-arch-n"></span></button>
    <button class="menu-item" onclick="closeMenu();openSettings()">⚙️ הגדרות</button>
    <div class="menu-sec">חשבון</div>
    <button class="menu-item danger" onclick="location.href='/logout'">🚪 יציאה</button>
  </div>
</nav>
<div class="meta" id="meta-bar"><b id="m-cnt">טוען...</b><span class="meta-sep">·</span><span id="m-src"></span><span class="meta-sep">·</span><span id="m-time"></span></div>
<div class="scan-bar" id="scan-bar"><div class="scan-inner"><div class="scan-spinner"></div><span id="scan-msg">סורק...</span></div></div>
<div class="page" id="view-listings">
  <div id="tip-wrap"></div>
  <div class="agent-status" id="agent-status"></div>
  <div class="stats-strip" id="stats-strip"></div>
  <div class="controls" id="controls">
    <div class="search-wrap">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <input class="search-in" id="q" placeholder="חיפוש לפי כתובת, רחוב, טקסט..." oninput="render()">
    </div>
    <select class="ctrl-sel" id="sort" onchange="render()">
      <option value="fresh">החדשות ביותר</option>
      <option value="score">התאמה גבוהה</option>
      <option value="price_asc">מחיר: נמוך לגבוה</option>
      <option value="price_desc">מחיר: גבוה לנמוך</option>
    </select>
    <select class="ctrl-sel" id="src" onchange="render()">
      <option value="all">כל המקורות</option>
      <option value="Facebook">Facebook</option>
      <option value="Yad2">Yad2</option>
      <option value="Homely">Homely</option>
    </select>
  </div>
  <div class="grid" id="grid">
    <div class="sk-card"><div class="sk-img"></div><div class="sk-body"><div class="sk-ln" style="height:17px;width:54%"></div><div class="sk-ln" style="height:12px;width:36%"></div><div class="sk-ln" style="height:11px;width:70%;margin-top:4px"></div></div></div>
    <div class="sk-card"><div class="sk-img"></div><div class="sk-body"><div class="sk-ln" style="height:17px;width:62%"></div><div class="sk-ln" style="height:12px;width:41%"></div><div class="sk-ln" style="height:11px;width:65%;margin-top:4px"></div></div></div>
    <div class="sk-card"><div class="sk-img"></div><div class="sk-body"><div class="sk-ln" style="height:17px;width:47%"></div><div class="sk-ln" style="height:12px;width:43%"></div><div class="sk-ln" style="height:11px;width:74%;margin-top:4px"></div></div></div>
  </div>
</div>
<div class="page" id="view-favorites" style="display:none">
  <div class="tips-header"><h2>❤️ המועדפים של <span id="fav-who">…</span></h2><p>הדירות שסימנת בלב — אזור אישי שרק שלך</p></div>
  <div class="grid" id="fav-grid"></div>
</div>
<div class="page" id="view-tracking" style="display:none">
  <div class="trk-head">
    <div><h2>📋 מעקב דירות</h2><p>הדירות שאתם בודקים כרגע — לוח משותף לשניכם</p></div>
    <button class="btn-add" onclick="openTrackAdd()">➕ הוסף למעקב ידנית</button>
  </div>
  <div class="trk-grid" id="trk-grid"></div>
</div>
<div class="page" id="view-tips" style="display:none">
  <div class="tips-header"><h2>💡 טיפים לחיפוש דירה</h2><p>עצות ומידע שיעזרו לך למצוא ולשכור דירה טובה</p></div>
  <div class="tips-grid" id="tips-grid">
    <div class="sk-card"><div class="sk-body" style="padding:24px 26px"><div class="sk-ln" style="height:10px;width:30%;margin-bottom:14px"></div><div class="sk-ln" style="height:18px;width:70%"></div><div class="sk-ln" style="height:13px;width:90%;margin-top:10px"></div></div></div>
    <div class="sk-card"><div class="sk-body" style="padding:24px 26px"><div class="sk-ln" style="height:10px;width:24%;margin-bottom:14px"></div><div class="sk-ln" style="height:18px;width:65%"></div><div class="sk-ln" style="height:13px;width:85%;margin-top:10px"></div></div></div>
    <div class="sk-card"><div class="sk-body" style="padding:24px 26px"><div class="sk-ln" style="height:10px;width:36%;margin-bottom:14px"></div><div class="sk-ln" style="height:18px;width:72%"></div><div class="sk-ln" style="height:13px;width:88%;margin-top:10px"></div></div></div>
  </div>
</div>
<div class="ov" id="arch-ov" onclick="closeArchive()"></div>
<div class="panel" id="arch-panel">
  <div class="ph"><span class="ph-title">ארכיון דירות</span><button class="ph-close" onclick="closeArchive()">✕</button></div>
  <div class="pb" id="arch-body"></div>
</div>
<div class="ov" id="set-ov" onclick="closeSettings()"></div>
<div class="drawer" id="set-drawer">
  <div class="ph"><span class="ph-title">הגדרות</span><button class="ph-close" onclick="closeSettings()">✕</button></div>
  <div class="pb">
    <div class="s-blk"><div class="s-ttl">סטטוס סוכן</div><div class="f-row"><span class="f-lbl">מצב פעולה</span><button id="ag-toggle" onclick="toggleAgent()">טוען...</button></div><div class="f-row"><span class="f-lbl">פעיל עד</span><input type="date" id="expiry" class="f-in" style="width:150px;text-align:right"><button class="btn-add" onclick="saveExpiry()">שמור</button></div><div id="expiry-note" style="font-size:12px;color:#aaa;margin-top:4px;padding-right:130px"></div></div>
    <div class="s-blk"><div class="s-ttl">תדירות סריקה</div><div class="f-row"><span class="f-lbl">פייסבוק (דקות)</span><input type="number" id="fb-iv" class="f-in" placeholder="30"></div><div class="f-row"><span class="f-lbl">Yad2 (דקות)</span><input type="number" id="y2-iv" class="f-in" placeholder="40"></div><button class="s-btn" onclick="saveIv()">שמור תדירות</button></div>
    <div class="s-blk"><div class="s-ttl">פילטרים</div><div class="f-row"><span class="f-lbl">מחיר מקסימלי</span><input type="number" id="max-p" class="f-in" placeholder="4100"><span style="font-size:12px;color:#bbb">₪</span></div><div class="f-row"><span class="f-lbl">חדרים מינימום</span><input type="number" id="min-r" class="f-in" min="1" max="10" step="0.5"></div><div class="f-row"><span class="f-lbl">חדרים מקסימום</span><input type="number" id="max-r" class="f-in" min="1" max="10" step="0.5"></div><button class="s-btn" onclick="saveFilters()">שמור פילטרים</button></div>
    <div class="s-blk"><div class="s-ttl">מקורות חיפוש</div><div class="cb-row"><input type="checkbox" id="src-y2"><label for="src-y2">Yad2</label></div><div class="cb-row"><input type="checkbox" id="src-fb"><label for="src-fb">Facebook Groups</label></div><div class="cb-row"><input type="checkbox" id="src-hm"><label for="src-hm">Homely</label></div><button class="s-btn" onclick="saveSrc()">שמור מקורות</button></div>
    <div class="s-blk"><div class="s-ttl">קבוצות פייסבוק</div><div id="grps"></div><div style="margin-top:12px;background:#fff;border-radius:11px;padding:16px;border:1px solid #e8e5e0"><div style="font-size:10px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;color:#bbb;margin-bottom:12px">הוסף קבוצה</div><div class="add-row"><input type="text" id="g-s" placeholder="חפש שם קבוצה..."><button class="btn-add" onclick="fbS()">פתח</button></div><div style="font-size:12.5px;font-weight:500;color:#888;margin:10px 0 5px">הדבק URL:</div><div class="add-row"><input type="text" id="g-u" placeholder="facebook.com/groups/..." style="direction:ltr;text-align:left" oninput="prevG(this.value)"></div><div id="g-prev" style="font-size:12px;min-height:18px;margin-top:5px;font-weight:500"></div><div style="font-size:12.5px;font-weight:500;color:#888;margin:10px 0 5px">שם לקבוצה:</div><div class="add-row"><input type="text" id="g-n" placeholder="שם לתצוגה"><button class="btn-add" onclick="addG()">+ הוסף</button></div></div><button class="s-btn" style="margin-top:12px" onclick="saveG()">שמור קבוצות</button></div>
  </div>
</div>
<div class="modal-ov" id="add-ov" onclick="if(event.target===this)closeAdd()">
  <div class="modal">
    <div class="modal-head"><h3 id="add-title">➕ הוסף דירה</h3><button class="ph-close" onclick="closeAdd()">✕</button></div>
    <div class="modal-body">
      <div class="mf"><label>כתובת / תיאור הדירה</label><input id="a-addr" placeholder="רחוב מצדה 5, שכונה ב׳"></div>
      <div class="mf-row">
        <div class="mf"><label>מחיר לחודש (₪)</label><input id="a-price" type="number" placeholder="3500"></div>
        <div class="mf"><label>חדרים</label><input id="a-rooms" type="number" step="0.5" placeholder="3"></div>
      </div>
      <div class="mf"><label>איש קשר / טלפון</label><input id="a-contact" placeholder="דנה · 050-1234567"></div>
      <div class="mf"><label>קישור למודעה (אופציונלי)</label><input id="a-url" placeholder="https://..." dir="ltr"></div>
      <div class="mf trk-only" style="display:none"><label>סטטוס</label><select id="a-status"></select></div>
      <div class="mf trk-only" style="display:none"><label>מתי מראים את הבית</label><input id="a-viewing" placeholder="לדוגמה: ראשון 18:00"></div>
      <div class="mf trk-only" style="display:none"><label>דירוג</label><div class="stars" id="a-stars"></div></div>
      <div class="mf"><label>הערות / מה חשבנו</label><textarea id="a-notes" placeholder="התרשמות, יתרונות, חסרונות, שאלות לבעל הבית..."></textarea></div>
      <button class="s-btn" id="a-save" onclick="submitAdd()">שמור</button>
    </div>
  </div>
</div>
<nav class="botnav" id="botnav">
  <button id="bn-listings" class="on" onclick="showView('listings')"><span class="bn-ico">🏠</span>דירות</button>
  <button id="bn-favorites" onclick="showView('favorites')"><span class="bn-ico">❤️</span>מועדפים</button>
  <button id="bn-tracking" onclick="showView('tracking')"><span class="bn-ico">📋</span>מעקב</button>
  <button id="bn-tips" onclick="showView('tips')"><span class="bn-ico">💡</span>טיפים</button>
</nav>
<div class="toast" id="toast"></div>
<script>
let all=[],dim=new Set(),curView='listings',fav=new Set(),me='',tracked=new Set();
const SK=s=>s.split('—')[0].trim();
const heartSVG='<svg class="h-empty" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#d1597f" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1.1 1L12 21l7.7-7.6 1.1-1a5.5 5.5 0 0 0 0-7.8z"/></svg><svg class="h-full" width="17" height="17" viewBox="0 0 24 24" fill="#e11d48" stroke="#e11d48" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1.1 1L12 21l7.7-7.6 1.1-1a5.5 5.5 0 0 0 0-7.8z"/></svg>';
const BANS={Yad2:'linear-gradient(155deg,#1a365d,#1e40af)',Homely:'linear-gradient(155deg,#052e16,#15803d)',Facebook:'linear-gradient(155deg,#1e3a8a,#1d4ed8)'};
const ban=s=>BANS[SK(s)]||'linear-gradient(155deg,#111,#333)';
const sc=s=>SK(s)==='Yad2'?'src-yad2':SK(s).includes('Facebook')?'src-fb':'src-hom';
const ri=u=>u&&(u.includes('img.yad2.co.il/Pic/')||u.includes('scontent')||u.includes('fbcdn.net'));
const io=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting)e.target.classList.add('vis')})},{threshold:.05});
let fcls='all';
function mLevel(sc){sc=sc||0;const pct=Math.max(40,Math.min(99,Math.round(sc/18*100)));if(sc>=12)return{c:'mb-hot',t:'התאמה מצוינת',pct};if(sc>=8)return{c:'mb-good',t:'התאמה טובה',pct};return{c:'mb-rev',t:'שווה בדיקה',pct}}
const RHE={rental_keyword:'מודעת השכרה',availability_keyword:'כניסה/זמינה',dedicated_group:'שכונה ב׳',date_found:'תאריך כניסה',suitable_for_couple:'מתאים לזוג',studio_or_unit:'יחידת דיור'};
function whyHe(rs){if(!rs)return[];const out=[];rs.forEach(r=>{if(r.indexOf('location:')===0)out.push('מיקום: '+r.split(':')[1]);else if(RHE[r])out.push(RHE[r])});return[...new Set(out)].slice(0,4)}
function fresh(ts){if(!ts)return null;const d=new Date(ts.replace(' ','T'));if(isNaN(d))return null;const m=(Date.now()-d)/60000;let txt;if(m<60)txt='לפני '+Math.max(0,Math.round(m))+' דק׳';else if(m<1440)txt='לפני '+Math.floor(m/60)+' שעות';else txt='לפני '+Math.floor(m/1440)+' ימים';return{txt,isNew:m<720}}
function showView(v){curView=v;['listings','favorites','tracking','tips'].forEach(n=>document.getElementById('view-'+n).style.display=v===n?'':'none');document.getElementById('meta-bar').style.display=v==='listings'?'':'none';document.getElementById('scan-bar').className='scan-bar';['listings','favorites','tracking','tips'].forEach(n=>{const e=document.getElementById('mn-'+n);if(e)e.className='menu-item'+(n===v?' on':'');const b=document.getElementById('bn-'+n);if(b)b.className=(n===v?'on':'')});if(v==='tips')loadTips();else if(v==='favorites')renderFavorites();else if(v==='tracking')loadTracking();else render()}
function openMenu(){document.getElementById('menu-ov').classList.add('open');document.getElementById('menu-drawer').classList.add('open')}
function closeMenu(){document.getElementById('menu-ov').classList.remove('open');document.getElementById('menu-drawer').classList.remove('open')}
function menuGo(v){closeMenu();showView(v)}
function card(l){const d=dim.has(l.id),sk=SK(l.source),id=safeId(l.id);const ml=l.score?mLevel(l.score):null;const badge=ml?`<span class="match-badge ${ml.c}"><span class="mb-dot"></span>${ml.pct}% · ${ml.t}</span>`:'';const fr=fresh(l.found_at);const freshPill=fr?`<span class="fresh${fr.isNew?' new':''}">🕒 ${fr.txt}</span>`:'';const srcTag=`<span class="src-tag ${sc(l.source)}">${esc(sk)}</span>`;const priceTag=l.price?`<div class="img-price"><div class="ip-num">₪${l.price.toLocaleString()}</div><div class="ip-sub">לחודש</div></div>`:'';const inner=`${badge}<div class="img-over"></div>${srcTag}${freshPill}${priceTag}`;const med=ri(l.image)?`<div class="card-img-wrap"><img class="card-img" src="${esc(l.image)}" alt="" loading="lazy" onerror="this.outerHTML='<div class=card-banner style=background:${ban(l.source)}>🏠</div>'">${inner}</div>`:`<div class="card-img-wrap"><div class="card-banner" style="background:${ban(l.source)}">🏠</div>${inner}</div>`;const chips=[l.rooms?`<span class="chip c-r">🛏 ${esc(l.rooms)} חד'</span>`:'',l.size?`<span class="chip c-s">📐 ${esc(l.size)} מ"ר</span>`:'',l.floor?`<span class="chip c-f">קומה ${esc(l.floor)}</span>`:''].filter(Boolean).join('');const wl=whyHe(l.reasons);const why=wl.length?`<div class="why"><span class="why-lbl">למה התאים</span>${wl.map(w=>`<span class="why-chip">${esc(w)}</span>`).join('')}</div>`:'';const pf=l.price?`<div><div class="price-big">₪${l.price.toLocaleString()}</div><div class="price-mo">לחודש</div></div>`:`<span class="price-unk">מחיר לא צוין</span>`;return`<div class="card${d?' dismissed':''}" id="c-${id}">${med}<div class="card-body"><div><div class="addr">${esc(l.address||l.title||'שכונה ב׳')}</div>${l.contact?`<div class="by">${esc(l.contact)}</div>`:''}</div>${l.preview?`<div class="prev">${esc(l.preview)}</div>`:''}${why}${chips?`<div class="chips">${chips}</div>`:''}<div class="card-foot">${pf}<div class="btns"><button class="btn-fav${fav.has(l.id)?' on':''}" title="הוסף למועדפים" onclick="toggleFav('${id}',this)">${heartSVG}</button>${tracked.has(l.id)?`<button class="btn-track is-tracked" disabled title="כבר במעקב">✓ במעקב</button>`:`<button class="btn-track" title="הוסף למעקב" onclick="addCardToTrack('${id}')">📋</button>`}<a class="btn-open" href="${safeUrl(l.url)}" target="_blank" rel="noopener"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>פתח</a><button class="btn-x" onclick="dis('${id}')">✕</button></div></div></div></div>`}
function applyFilters(list){const qel=document.getElementById('q');const q=(qel?qel.value:'').trim().toLowerCase();const srcEl=document.getElementById('src');const src=srcEl?srcEl.value:'all';let r=list.filter(l=>!dim.has(l.id));if(fcls==='new')r=r.filter(l=>{const f=fresh(l.found_at);return f&&f.isNew});else if(fcls==='hot')r=r.filter(l=>(l.score||0)>=12);else if(fcls==='review')r=r.filter(l=>l.classification==='maybe_relevant_rental_apartment'||l.classification==='over_budget');if(src!=='all')r=r.filter(l=>(l.source||'').includes(src));if(q)r=r.filter(l=>((l.address||'')+(l.preview||'')+(l.title||'')+(l.source||'')).toLowerCase().includes(q));const sortEl=document.getElementById('sort');const sort=sortEl?sortEl.value:'fresh';const t=l=>l.found_at?new Date(l.found_at.replace(' ','T')).getTime():0;if(sort==='fresh')r.sort((a,b)=>t(b)-t(a));else if(sort==='score')r.sort((a,b)=>(b.score||0)-(a.score||0));else if(sort==='price_asc')r.sort((a,b)=>(a.price||1e9)-(b.price||1e9));else if(sort==='price_desc')r.sort((a,b)=>(b.price||0)-(a.price||0));return r}
function renderStats(){const act=all.filter(l=>!dim.has(l.id));const nNew=act.filter(l=>{const f=fresh(l.found_at);return f&&f.isNew}).length;const nHot=act.filter(l=>(l.score||0)>=12).length;const nRev=act.filter(l=>l.classification==='maybe_relevant_rental_apartment'||l.classification==='over_budget').length;const cards=[{k:'all',ico:'🏠',num:act.length,lbl:'דירות פעילות',cls:''},{k:'new',ico:'✨',num:nNew,lbl:'חדש (12 שעות)',cls:'s-new'},{k:'hot',ico:'🔥',num:nHot,lbl:'התאמות מצוינות',cls:'s-hot'},{k:'review',ico:'🔍',num:nRev,lbl:'לבדיקה',cls:'s-rev'}];document.getElementById('stats-strip').innerHTML=cards.map(c=>`<div class="stat ${c.cls}${fcls===c.k?' on':''}" onclick="setFilter('${c.k}')"><div class="stat-ico">${c.ico}</div><div class="stat-num">${c.num}</div><div class="stat-lbl">${c.lbl}</div></div>`).join('')}
function setFilter(k){fcls=(fcls===k&&k!=='all')?'all':k;render()}
function render(){renderStats();const g=document.getElementById('grid');const ac=applyFilters(all);if(!ac.length){const qel=document.getElementById('q');const filtered=fcls!=='all'||(qel&&qel.value);const msg=filtered?'נסה לשנות את הסינון או החיפוש.':'לחץ על כפתור הרענן לסרוק עכשיו, או המתן לסריקה האוטומטית.';g.innerHTML=`<div class="empty"><div class="empty-visual"><div class="empty-house">🏡</div><div class="empty-badge">מחפש...</div></div><h3>אין דירות להצגה</h3><p>${msg}</p></div>`;}else{g.innerHTML=ac.map(card).join('');g.querySelectorAll('.card').forEach(c=>io.observe(c))}const an=document.getElementById('menu-arch-n');if(an)an.textContent=dim.size||'';const srcs={};all.filter(l=>!dim.has(l.id)).forEach(l=>{const k=SK(l.source);srcs[k]=(srcs[k]||0)+1});document.getElementById('m-cnt').textContent=`${ac.length} מוצגות`;document.getElementById('m-src').textContent=Object.entries(srcs).map(([k,v])=>`${k} ${v}`).join(' · ');document.getElementById('m-time').textContent=`עודכן ${new Date().toLocaleTimeString('he-IL')}`}
async function dis(id){await fetch(`/api/dismiss/${encodeURIComponent(id)}`,{method:'POST'});dim.add(id);render();toast('הועבר לארכיון')}
async function loadData(){const[lR,dR,sR,mR,fR,tR]=await Promise.all([fetch('/api/listings'),fetch('/api/dismissed'),fetch('/api/settings'),fetch('/api/me'),fetch('/api/favorites'),fetch('/api/tracking')]);all=await lR.json();dim=new Set(await dR.json());const cfg=await sR.json();me=(await mR.json()).user||'';fav=new Set(await fR.json());try{const tr=await tR.json();tracked=new Set(tr.filter(x=>x.source_id).map(x=>x.source_id));}catch(_){}const av=document.getElementById('user-av'),nm=document.getElementById('user-name');if(av){av.textContent=(me[0]||'?');}if(nm){nm.textContent=me;}const fw=document.getElementById('fav-who');if(fw)fw.textContent=me;const on=cfg.enabled!==false;document.getElementById('ag-dot').className='dot'+(on?'':' off');document.getElementById('ag-lbl').textContent=on?'סוכן פעיל':'מושהה';if(curView==='listings')render();else if(curView==='favorites')renderFavorites()}
loadData();setInterval(loadData,60000);
// ── Favorites (personal area) ──
async function toggleFav(id,btn){try{const r=await fetch('/api/favorite/'+encodeURIComponent(id),{method:'POST'});const d=await r.json();if(d.favorited){fav.add(id);if(btn)btn.classList.add('on');toast('נוסף למועדפים ❤️');}else{fav.delete(id);if(btn)btn.classList.remove('on');toast('הוסר מהמועדפים');}if(curView==='favorites')renderFavorites();}catch(_){toast('שגיאה')}}
function renderFavorites(){const g=document.getElementById('fav-grid');const list=all.filter(l=>fav.has(l.id));if(!list.length){g.innerHTML=`<div class="empty"><div class="empty-visual"><div class="empty-house">❤️</div><div class="empty-badge">ריק</div></div><h3>אין עדיין מועדפים</h3><p>לחץ על הלב על דירה כדי לשמור אותה כאן, באזור האישי שלך.</p></div>`;return}g.innerHTML=list.map(card).join('');g.querySelectorAll('.card').forEach(c=>io.observe(c))}
// ── Add apartment (manual) + tracking board ──
const TRK_ST={to_contact:'ליצור קשר',scheduled:'נקבעה צפייה',visited:'ראינו',candidate:'מועמדת מובילה',rejected:'נפסל'};
const val=id=>document.getElementById(id).value.trim();
let addMode='listing',addRating=0,editId=null;
function clearAddForm(){['a-addr','a-price','a-rooms','a-contact','a-url','a-viewing','a-notes'].forEach(id=>document.getElementById(id).value='');addRating=0}
function fillStatus(v){document.getElementById('a-status').innerHTML=Object.entries(TRK_ST).map(([k,l])=>`<option value="${k}"${k===v?' selected':''}>${l}</option>`).join('')}
function renderAddStars(){document.getElementById('a-stars').innerHTML=[1,2,3,4,5].map(i=>`<span class="star${i<=addRating?' on':''}" onclick="setAddRating(${i})">★</span>`).join('')}
function setAddRating(r){addRating=(addRating===r?0:r);renderAddStars()}
function openAdd(){addMode='listing';editId=null;document.getElementById('add-title').textContent='➕ הוסף דירה שמצאתם';document.querySelectorAll('.trk-only').forEach(e=>e.style.display='none');clearAddForm();document.getElementById('a-save').textContent='שמור';document.getElementById('add-ov').classList.add('open')}
function openTrackAdd(){addMode='tracking';editId=null;document.getElementById('add-title').textContent='➕ הוסף דירה למעקב';clearAddForm();fillStatus('to_contact');renderAddStars();document.querySelectorAll('.trk-only').forEach(e=>e.style.display='');document.getElementById('a-save').textContent='הוסף למעקב';document.getElementById('add-ov').classList.add('open')}
function openTrackEdit(id){const t=trk.find(x=>x.id===id);if(!t)return;addMode='edit';editId=id;document.getElementById('add-title').textContent='✏️ עריכת דירה במעקב';document.getElementById('a-addr').value=t.address||'';document.getElementById('a-price').value=t.price||'';document.getElementById('a-rooms').value=t.rooms||'';document.getElementById('a-contact').value=t.contact||'';document.getElementById('a-url').value=t.url||'';document.getElementById('a-viewing').value=t.viewing_date||'';document.getElementById('a-notes').value=t.notes||'';addRating=t.rating||0;fillStatus(t.status);renderAddStars();document.querySelectorAll('.trk-only').forEach(e=>e.style.display='');document.getElementById('a-save').textContent='שמור שינויים';document.getElementById('add-ov').classList.add('open')}
function closeAdd(){document.getElementById('add-ov').classList.remove('open')}
async function submitAdd(){const p={address:val('a-addr'),price:val('a-price'),rooms:val('a-rooms'),contact:val('a-contact'),url:val('a-url'),notes:val('a-notes')};const b=document.getElementById('a-save');b.disabled=true;
  try{
    if(addMode==='edit'){p.status=val('a-status');p.viewing_date=val('a-viewing');p.rating=addRating;const d=await(await fetch('/api/tracking/'+editId,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)})).json();if(d.ok){closeAdd();toast('עודכן ✓');loadTracking();}else toast('שגיאה');}
    else if(addMode==='tracking'){p.status=val('a-status');p.viewing_date=val('a-viewing');p.rating=addRating;const d=await(await fetch('/api/tracking',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)})).json();if(d.ok){closeAdd();toast('נוסף למעקב 📋');loadTracking();}else toast('שגיאה');}
    else{if(!p.address&&!p.url){toast('צריך כתובת או קישור');b.disabled=false;return;}const d=await(await fetch('/api/add_listing',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)})).json();if(d.ok){closeAdd();toast('הדירה נוספה ✓');await loadData();showView('listings');}else toast(d.error||'שגיאה');}
  }finally{b.disabled=false}}
let trk=[];
async function loadTracking(){try{trk=await(await fetch('/api/tracking')).json();renderTracking();}catch(_){}}
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;')}
function safeUrl(u){return /^https?:\/\//i.test(u||'')?esc(u):'#'}
function safeId(x){return String(x==null?'':x).replace(/[^\w-]/g,'')}
function starsView(r){let h='';for(let i=1;i<=5;i++)h+=`<span class="star${i<=r?' on':''}" style="cursor:default">★</span>`;return h}
function trkCard(t){const phone=(t.contact||'').replace(/[^0-9+]/g,'');const callBtn=phone.length>=7?`<a class="trk-act call" href="tel:${phone}">📞 התקשר</a>`:'';const navBtn=t.address?`<a class="trk-act nav" href="https://www.google.com/maps/search/${encodeURIComponent(t.address+' באר שבע')}" target="_blank" rel="noopener">🗺 ניווט</a>`:'';const openBtn=t.url?`<a class="trk-act" href="${t.url}" target="_blank" rel="noopener">🔗 מודעה</a>`:'';const sub=[t.price?'₪'+t.price:'',t.rooms?t.rooms+' חד׳':'',t.added_by?'הוסיף: '+t.added_by:''].filter(Boolean).join(' · ');const chips=[t.contact?`<span class="trk-chip">👤 ${esc(t.contact)}</span>`:'',t.viewing_date?`<span class="trk-chip">📅 ${esc(t.viewing_date)}</span>`:''].filter(Boolean).join('');
  return `<div class="trk-card st-${t.status}" id="t-${t.id}"><div class="trk-top"><div><div class="trk-addr">${esc(t.address)||'דירה'}</div><div class="trk-sub">${sub}</div></div><span class="trk-badge tb-${t.status}">${TRK_ST[t.status]||''}</span></div>${chips?`<div class="trk-meta">${chips}</div>`:''}${t.rating?`<div class="stars">${starsView(t.rating)}</div>`:''}${t.notes?`<div class="trk-notes">${esc(t.notes)}</div>`:''}<div class="trk-actions">${callBtn}${navBtn}${openBtn}<button class="trk-act edit" onclick="openTrackEdit('${t.id}')">✏️ עריכה</button><button class="trk-act del" onclick="delTrk('${t.id}')">🗑 הסר</button></div></div>`}
function renderTracking(){const g=document.getElementById('trk-grid');if(!trk.length){g.innerHTML=`<div class="empty"><div class="empty-visual"><div class="empty-house">📋</div><div class="empty-badge">ריק</div></div><h3>אין דירות במעקב</h3><p>לחץ "➕ הוסף למעקב", או על 📋 בכרטיס דירה כדי להעביר אותה לכאן.</p></div>`;return}g.innerHTML=trk.map(trkCard).join('')}
async function delTrk(id){if(!confirm('להסיר את הדירה מהמעקב?'))return;await fetch('/api/tracking/'+id,{method:'DELETE'});trk=trk.filter(x=>x.id!==id);renderTracking();toast('הוסר מהמעקב')}
async function addCardToTrack(id){const l=(all.find(x=>x.id===id)||{});const p={address:l.address||l.title||'',price:l.price||'',rooms:l.rooms||'',contact:l.contact||'',url:l.url||'',source_id:id,status:'to_contact'};const d=await(await fetch('/api/tracking',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)})).json();if(d.ok){tracked.add(id);toast('נוסף למעקב 📋 — ראה בטאב "מעקב"');if(curView==='favorites')renderFavorites();else render();}else toast('שגיאה')}
// ── Live agent activity widget ──
const AGENTS={facebook:{ico:'📘',name:'Facebook'},yad2:{ico:'🏠',name:'Yad2 + Homely'}};
const ST_HE={idle:'ממתין לסריקה הבאה',disabled:'מושבת',error:'שגיאה',scanning:'עובד עכשיו…',starting:'מתחיל…'};
function staleMin(u){if(!u)return 999;const d=new Date(u.replace(' ','T'));return isNaN(d)?999:(Date.now()-d)/60000}
function agCard(k,s){const a=AGENTS[k];if(!s)return `<div class="ag-card"><span class="ag-led"></span><div class="ag-main"><div class="ag-name">${a.ico} ${a.name}</div><div class="ag-detail">עדיין לא רץ בסשן הזה</div></div></div>`;let state=s.state||'idle';if(state==='scanning'&&staleMin(s.updated)>10)state='idle';const det=s.detail||ST_HE[state]||'';const meta=[s.last_run?'ריצה אחרונה: '+s.last_run:'',(s.next_run&&state!=='scanning')?'הבאה: '+s.next_run:'',(typeof s.found==='number'&&state!=='scanning')?s.found+' חדשות':''].filter(Boolean).join(' · ');const now=state==='scanning'?'<span class="ag-now">● '+ST_HE.scanning+'</span>':'';const prog=state==='scanning'?'<div class="ag-prog"></div>':'';return `<div class="ag-card ${state}"><span class="ag-led ${state}"></span><div class="ag-main"><div class="ag-name">${a.ico} ${a.name} ${now}</div><div class="ag-detail">${esc(det)}</div>${meta?`<div class="ag-meta">${esc(meta)}</div>`:''}</div>${prog}</div>`}
async function loadAgentStatus(){try{const st=await(await fetch('/api/agent_status')).json();document.getElementById('agent-status').innerHTML=['facebook','yad2'].map(k=>agCard(k,st[k])).join('')}catch(e){}}
loadAgentStatus();setInterval(loadAgentStatus,3000);
async function loadTipWidget(){const tips=await(await fetch('/api/tips')).json();const w=document.getElementById('tip-wrap');if(!tips||!tips.length){w.innerHTML='';return}const t=tips[0];const cat=t.category||t.source||'טיפ יומי';w.innerHTML=`<div class="tip-widget" onclick="showView('tips')"><div class="tip-ico">💡</div><div class="tip-content"><div class="tip-label">${esc(cat)}</div><div class="tip-title">${esc(t.title)}</div><div class="tip-body">${esc(t.summary||'')}</div></div><div class="tip-cta"><span class="tip-cta-text">טיפ יומי</span><span class="tip-cta-link">לכל הטיפים <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg></span></div></div>`}
loadTipWidget();
async function loadTips(){const tips=await(await fetch('/api/tips')).json();const g=document.getElementById('tips-grid');if(!tips||!tips.length){g.innerHTML=`<div class="empty"><div class="empty-house" style="font-size:56px;animation:none">💡</div><h3>אין טיפים עדיין</h3></div>`;return}const cm={'חוזה וחוק':'tc-legal','עלויות':'tc-money','מחיר ומשא ומתן':'tc-money','כניסה לדירה':'tc-legal','אסטרטגיה':'tc-strat','תהליך השכירות':'tc-strat','הבניין והשכנים':'tc-local','לפני החתימה':'tc-legal','שכונה ב׳':'tc-local','עדכון שוק':'tc-news'};g.innerHTML=tips.map((t,i)=>`<div class="tip-card" style="animation-delay:${Math.min(i*.05,.45)}s"><span class="tc-cat ${cm[t.category]||'tc-other'}">${esc(t.category||t.source||'טיפ')}</span><div class="tc-title">${esc(t.title)}</div><div class="tc-body">${esc(t.summary||'')}</div><div class="tc-foot"><span style="font-weight:500">${esc(t.source||'')}</span>${t.url?`<a class="tc-link" href="${safeUrl(t.url)}" target="_blank" rel="noopener">קרא עוד<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></a>`:''}</div></div>`).join('');g.querySelectorAll('.tip-card').forEach(c=>io.observe(c))}
function openArchive(){renderArchive();document.getElementById('arch-ov').classList.add('open');document.getElementById('arch-panel').classList.add('open')}
function closeArchive(){document.getElementById('arch-ov').classList.remove('open');document.getElementById('arch-panel').classList.remove('open')}
function renderArchive(){const ar=all.filter(l=>dim.has(l.id));const b=document.getElementById('arch-body');if(!ar.length){b.innerHTML=`<div class="empty" style="padding:48px 0"><div class="empty-house" style="font-size:48px;animation:none">🗂</div><h3 style="font-size:16px">הארכיון ריק</h3></div>`;return}b.innerHTML=ar.map(l=>`<div class="arc"><div class="arc-info"><div class="arc-addr">${esc(l.address||l.title||'שכונה ב׳')}</div><div class="arc-meta">${esc(SK(l.source))}${l.rooms?' · '+l.rooms+' חד\'':''}</div></div>${l.price?`<div class="arc-price">₪${l.price.toLocaleString()}</div>`:''}<button class="arc-btn" onclick="restore('${safeId(l.id)}')">שחזר</button></div>`).join('')}
async function restore(id){await fetch(`/api/restore/${encodeURIComponent(id)}`,{method:'POST'});dim.delete(id);renderArchive();render();const an=document.getElementById('menu-arch-n');if(an)an.textContent=dim.size||'';toast('שוחזר לרשימה')}
let _sc=false,_sp=null;
async function scanNow(){if(_sc)return;_sc=true;const icon=document.getElementById('refresh-icon');const bar=document.getElementById('scan-bar');const msg=document.getElementById('scan-msg');if(icon)icon.classList.add('spin');bar.classList.add('show');msg.textContent='סורק דירות ב-Yad2...';await fetch('/api/scan_now',{method:'POST'});_sp=setInterval(async()=>{const st=await(await fetch('/api/scan_status')).json();if(!st.running){clearInterval(_sp);_sc=false;if(icon)icon.classList.remove('spin');if(st.found>0){msg.textContent=`נמצאו ${st.found} דירות חדשות!`;setTimeout(()=>bar.classList.remove('show'),4000);}else{msg.textContent=st.last?`עודכן ב-${st.last} — אין חדש כרגע`:'אין דירות חדשות כרגע';setTimeout(()=>bar.classList.remove('show'),3000);}loadData();}},800)}
let cfg={};
function openSettings(){loadSets();document.getElementById('set-ov').classList.add('open');document.getElementById('set-drawer').classList.add('open')}
function closeSettings(){document.getElementById('set-ov').classList.remove('open');document.getElementById('set-drawer').classList.remove('open')}
async function loadSets(){cfg=await(await fetch('/api/settings')).json();const b=document.getElementById('ag-toggle');b.textContent=cfg.enabled?'פעיל — לחץ להשהות':'מושהה — לחץ להפעיל';b.className=cfg.enabled?'tog-on':'tog-off';const ef=document.getElementById('expiry'),en=document.getElementById('expiry-note');if(cfg.expiry_date){ef.value=cfg.expiry_date;const d=Math.ceil((new Date(cfg.expiry_date)-new Date())/86400000);en.innerHTML=d<0?`<span style="color:#dc2626">פג תוקף לפני ${Math.abs(d)} ימים</span>`:d===0?`<span style="color:#dc2626">פג תוקף היום</span>`:`<span style="color:#16a34a">פעיל עוד ${d} ימים</span>`;}else{ef.value='';en.textContent='ללא תאריך תפוגה'}document.getElementById('fb-iv').value=cfg.fb_interval_minutes||30;document.getElementById('y2-iv').value=cfg.yad2_interval_minutes||40;document.getElementById('max-p').value=cfg.max_price||4100;document.getElementById('min-r').value=cfg.min_rooms||1.5;document.getElementById('max-r').value=cfg.max_rooms||3.5;const s=cfg.sources||{};document.getElementById('src-y2').checked=s.yad2!==false;document.getElementById('src-fb').checked=s.facebook!==false;document.getElementById('src-hm').checked=s.homely!==false;renderG(cfg.facebook_groups||{})}
function renderG(g){document.getElementById('grps').innerHTML=Object.entries(g).map(([n,id])=>`<div class="g-row"><span class="g-nm">${esc(n)}</span><span class="g-id">${esc(id)}</span><button class="btn-rm" onclick="rmG('${esc(n)}')">✕</button></div>`).join('')||'<p style="font-size:13px;color:#bbb;margin-bottom:8px">אין קבוצות מוגדרות</p>'}
async function post(d){await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)})}
async function toggleAgent(){const r=await(await fetch('/api/settings/toggle',{method:'POST'})).json();cfg.enabled=r.enabled;loadSets();toast(r.enabled?'הסוכן הופעל':'הסוכן הושהה')}
async function saveExpiry(){const v=document.getElementById('expiry').value;await post({expiry_date:v||null});toast(v?`פעיל עד ${v}`:'תאריך תפוגה הוסר');loadSets()}
async function saveIv(){await post({fb_interval_minutes:+document.getElementById('fb-iv').value,yad2_interval_minutes:+document.getElementById('y2-iv').value});toast('תדירות עודכנה')}
async function saveFilters(){await post({max_price:+document.getElementById('max-p').value,min_rooms:+document.getElementById('min-r').value,max_rooms:+document.getElementById('max-r').value});toast('פילטרים נשמרו')}
async function saveSrc(){await post({sources:{yad2:document.getElementById('src-y2').checked,facebook:document.getElementById('src-fb').checked,homely:document.getElementById('src-hm').checked}});toast('מקורות נשמרו')}
function fbS(){const q=document.getElementById('g-s').value.trim();if(q)window.open(`https://www.facebook.com/search/groups/?q=${encodeURIComponent(q)}`)}
function prevG(v){const el=document.getElementById('g-prev');if(!v.trim()){el.textContent='';return}const m=v.match(/facebook\.com\/groups\/([^/?&\s]+)/);const id=m?m[1]:(v.trim().match(/^[\w.\-]+$/)?v.trim():null);el.textContent=id?`Group ID: ${id}`:'קישור לא תקין';el.style.color=id?'#16a34a':'#dc2626'}
function addG(){const raw=document.getElementById('g-u').value.trim(),name=document.getElementById('g-n').value.trim();if(!raw||!name){toast('נא למלא שם וקישור');return}const m=raw.match(/facebook\.com\/groups\/([^/?&\s]+)/);const id=m?m[1]:(raw.match(/^[\w.\-]+$/)?raw:null);if(!id){toast('קישור לא תקין');return}cfg.facebook_groups={...(cfg.facebook_groups||{}),[name]:id};renderG(cfg.facebook_groups);document.getElementById('g-u').value='';document.getElementById('g-n').value='';document.getElementById('g-prev').textContent='';toast('נוסף — לחץ שמור קבוצות')}
function rmG(n){const g={...(cfg.facebook_groups||{})};delete g[n];cfg.facebook_groups=g;renderG(g)}
async function saveG(){await post({facebook_groups:cfg.facebook_groups});toast('קבוצות נשמרו')}
let _tt;
function toast(msg){const el=document.getElementById('toast');clearTimeout(_tt);el.textContent=msg;el.className='toast show';_tt=setTimeout(()=>el.className='toast',2700)}
</script>
</body>
</html>"""


# ─── Login page ───────────────────────────────────────────────────────────────

LOGIN_HTML = r"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>דירונט — כניסה</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Plus Jakarta Sans',system-ui,sans-serif;direction:rtl;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;
  background-color:#F2EDE4;background-image:radial-gradient(circle,#C8BDB0 1px,transparent 1px);background-size:26px 26px;-webkit-font-smoothing:antialiased}
.box{background:#fff;border-radius:24px;box-shadow:0 12px 48px rgba(90,60,20,.16),0 2px 8px rgba(90,60,20,.06);width:100%;max-width:380px;overflow:hidden}
.box-head{background:linear-gradient(160deg,#0D2B1A 0%,#1A4A2E 55%,#163D24 100%);padding:36px 32px 30px;text-align:center;color:#fff}
.logo-mark{width:54px;height:54px;border-radius:15px;margin:0 auto 14px;background:linear-gradient(135deg,#4ade80,#16a34a);display:flex;align-items:center;justify-content:center;font-size:27px;box-shadow:0 4px 16px rgba(74,222,128,.4)}
.box-head h1{font-size:22px;font-weight:800;letter-spacing:-.5px}
.box-head p{font-size:13px;color:rgba(255,255,255,.55);margin-top:5px}
.box-body{padding:30px 32px 34px}
.fld{margin-bottom:16px}
.fld label{display:block;font-size:12.5px;font-weight:600;color:#6b5d54;margin-bottom:7px}
.fld input{width:100%;border:1px solid #e3ddd4;border-radius:12px;padding:13px 15px;font-size:15px;font-family:inherit;color:#111;transition:border .15s,box-shadow .15s}
.fld input:focus{outline:none;border-color:#16a34a;box-shadow:0 0 0 3px rgba(22,163,74,.12)}
.btn{width:100%;background:linear-gradient(135deg,#1A4A2E,#0D2B1A);color:#fff;border:none;border-radius:12px;padding:14px;font-size:15px;font-weight:700;font-family:inherit;cursor:pointer;margin-top:6px;transition:opacity .15s,transform .1s;box-shadow:0 4px 14px rgba(13,43,26,.3)}
.btn:hover{opacity:.92}.btn:active{transform:translateY(1px)}.btn:disabled{opacity:.6;cursor:default}
.err{background:#fef2f2;color:#b91c1c;border:1px solid #fecaca;border-radius:10px;padding:10px 13px;font-size:13px;font-weight:500;margin-bottom:16px;display:none}
.err.show{display:block}
.foot{text-align:center;font-size:11.5px;color:#bbb;margin-top:18px;font-style:italic}
</style>
</head>
<body>
<form class="box" id="f" onsubmit="return doLogin(event)">
  <div class="box-head">
    <div class="logo-mark">🏠</div>
    <h1>דירונט</h1>
    <p>הכניסה לאזור האישי</p>
  </div>
  <div class="box-body">
    <div class="err" id="err"></div>
    <div class="fld"><label>שם משתמש</label><input id="u" autocomplete="username" autofocus placeholder="itay / neta"></div>
    <div class="fld"><label>סיסמה</label><input id="p" type="password" autocomplete="current-password" placeholder="••••••••"></div>
    <button class="btn" id="b" type="submit">כניסה</button>
    <div class="foot">מוצא את הדירה שלכם — יחד 💚</div>
  </div>
</form>
<script>
async function doLogin(e){
  e.preventDefault();
  const b=document.getElementById('b'),err=document.getElementById('err');
  b.disabled=true;b.textContent='מתחבר...';err.className='err';
  try{
    const r=await fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({username:document.getElementById('u').value,password:document.getElementById('p').value})});
    const d=await r.json();
    if(d.ok){location.href='/';}
    else{err.textContent=d.error||'שגיאה';err.className='err show';b.disabled=false;b.textContent='כניסה';}
  }catch(_){err.textContent='שגיאת תקשורת';err.className='err show';b.disabled=false;b.textContent='כניסה';}
  return false;
}
</script>
</body>
</html>"""


# ─── Auth: every page/API requires login except /login itself ─────────────────

@app.before_request
def _require_login():
    # /login and /api/ingest are exempt: ingest uses a token header, not a session
    # (it's how the home Facebook agent pushes listings to the server).
    if request.path in ("/login", "/api/ingest") or request.path.startswith("/static"):
        return
    if not session.get("user"):
        if request.path.startswith("/api/"):
            return jsonify({"error": "auth_required"}), 401
        return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form
        user = (data.get("username") or "").strip().lower()
        pw   = data.get("password") or ""
        if app_auth.check_login(user, pw):
            session.permanent = True
            session["user"] = user
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "שם משתמש או סיסמה שגויים"}), 401
    return render_template_string(LOGIN_HTML)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/api/me")
def api_me():
    return jsonify({"user": session.get("user", "")})

@app.route("/api/favorites")
def api_favorites():
    return jsonify(app_auth.get_user_favorites(session["user"]))

@app.route("/api/favorite/<path:lid>", methods=["POST"])
def api_favorite(lid):
    now_fav = app_auth.toggle_favorite(session["user"], lid)
    return jsonify({"favorited": now_fav})


# ─── Ingest from the home Facebook agent (token-authenticated) ────────────────

@app.route("/api/ingest", methods=["POST"])
def api_ingest():
    import os
    token = os.getenv("INGEST_TOKEN", "")
    if not token or request.headers.get("X-Ingest-Token") != token:
        return jsonify({"error": "unauthorized"}), 401
    items = request.get_json(silent=True) or []
    if not isinstance(items, list):
        return jsonify({"error": "expected a list"}), 400
    state = {"added": 0}
    def _mut(existing_list):
        existing = {x["id"]: x for x in (existing_list or []) if isinstance(x, dict) and "id" in x}
        for it in items:
            if not isinstance(it, dict) or "id" not in it:
                continue
            if it["id"] not in existing:
                state["added"] += 1
            existing[it["id"]] = it
        return list(reversed(list(existing.values())))
    storage.update_json(LISTINGS_FILE, _mut, [])
    return jsonify({"ok": True, "received": len(items), "added": state["added"]})


# ─── Manually-added listings ("apartments we found ourselves") ────────────────

@app.route("/api/add_listing", methods=["POST"])
def api_add_listing():
    d = request.get_json(silent=True) or {}
    addr = (d.get("address") or "").strip()
    if not addr and not (d.get("url") or "").strip():
        return jsonify({"ok": False, "error": "צריך לפחות כתובת או קישור"}), 400
    try:
        price = int(d.get("price") or 0)
    except Exception:
        price = 0
    try:
        rooms = float(d.get("rooms") or 0)
    except Exception:
        rooms = 0
    notes = (d.get("notes") or "").strip()
    lst = {
        "id": "manual_" + datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "source": "ידני — נמצא על ידינו",
        "title": addr or "דירה שנמצאה",
        "address": addr or "דירה שנמצאה",
        "price": price,
        "rooms": rooms,
        "floor": (d.get("floor") or "").strip(),
        "size": (d.get("size") or "").strip(),
        "image": "",
        "url": (d.get("url") or "").strip(),
        "preview": notes,
        "contact": (d.get("contact") or "").strip(),
        "classification": "relevant_rental_apartment",
        "score": 0,
        "reasons": ["נוסף ידנית"],
        "found_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "manual": True,
    }
    def _mut(existing_list):
        existing = {item["id"]: item for item in (existing_list or []) if isinstance(item, dict) and "id" in item}
        existing[lst["id"]] = lst
        return list(reversed(list(existing.values())))
    storage.update_json(LISTINGS_FILE, _mut, [])
    return jsonify({"ok": True, "listing": lst})


# ─── Tracking board (shared) ──────────────────────────────────────────────────

@app.route("/api/tracking", methods=["GET"])
def api_tracking_list():
    return jsonify(app_tracking.load_tracking())

@app.route("/api/tracking", methods=["POST"])
def api_tracking_add():
    item = app_tracking.add_item(request.get_json(silent=True) or {}, session["user"])
    return jsonify({"ok": True, "item": item})

@app.route("/api/tracking/<item_id>", methods=["POST"])
def api_tracking_update(item_id):
    item = app_tracking.update_item(item_id, request.get_json(silent=True) or {})
    return jsonify({"ok": bool(item), "item": item})

@app.route("/api/tracking/<item_id>", methods=["DELETE"])
def api_tracking_delete(item_id):
    return jsonify({"ok": app_tracking.delete_item(item_id)})


# ─── API ──────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)

@app.route("/api/listings")
def api_listings():
    return jsonify(load_listings())

@app.route("/api/dismissed")
def api_dismissed():
    return jsonify(list(load_dismissed()))

@app.route("/api/tips")
def api_tips():
    return jsonify(load_tips())

@app.route("/api/scan_now", methods=["POST"])
def api_scan_now():
    if _scan_status.get("running"):
        return jsonify({"ok": False, "message": "סריקה כבר רצה"})
    t = threading.Thread(target=quick_yad2_scan, daemon=True)
    t.start()
    return jsonify({"ok": True})

@app.route("/api/scan_status")
def api_scan_status():
    return jsonify(_scan_status)

@app.route("/api/agent_status")
def api_agent_status():
    from agent_status import read_status
    return jsonify(read_status())

@app.route("/api/dismiss/<path:lid>", methods=["POST"])
def api_dismiss(lid):
    # Locked read-modify-write (the Telegram bot writes this file too).
    storage.update_json(DISMISSED_FILE, lambda ids: list(set(ids) | {lid}), [])
    return jsonify({"ok":True})

@app.route("/api/restore/<path:lid>", methods=["POST"])
def api_restore(lid):
    storage.update_json(DISMISSED_FILE, lambda ids: [i for i in ids if i != lid], [])
    return jsonify({"ok":True})

@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    return jsonify(load_settings())

@app.route("/api/settings", methods=["POST"])
def api_save_settings():
    s=load_settings(); data=request.get_json() or {}
    for k in ("enabled","run_times","max_price","min_rooms","max_rooms","sources",
              "facebook_groups","expiry_date","fb_interval_minutes","yad2_interval_minutes"):
        if k in data: s[k]=data[k]
    save_settings(s); return jsonify({"ok":True})

@app.route("/api/settings/toggle", methods=["POST"])
def api_toggle():
    s=load_settings(); s["enabled"]=not s.get("enabled",True); save_settings(s)
    return jsonify({"enabled":s["enabled"]})

@app.route("/api/extract_group_id")
def api_gid():
    raw=request.args.get("url","").strip()
    if not raw: return jsonify({"error":"empty"})
    if raw.isdigit(): return jsonify({"id":raw})
    m=re.search(r'facebook\.com/groups/([^/?&\s]+)',raw)
    return jsonify({"id":m.group(1)} if m else {"error":"לא ניתן לחלץ"})

@app.route("/api/search_group")
def api_sg():
    q=request.args.get("q","").strip()
    return jsonify({"search_url":f"https://www.facebook.com/search/groups/?q={req_lib.utils.quote(q)}"} if q else {"error":"empty"})

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def get_ip():
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(("8.8.8.8",80)); ip=s.getsockname()[0]; s.close(); return ip
    except Exception: return "localhost"

if __name__=="__main__":
    import os
    try:
        from dotenv import load_dotenv; load_dotenv()
    except Exception:
        pass
    port=int(os.getenv("PORT","5050"))
    ip=get_ip()
    print(f"\n  דירונט  →  http://localhost:{port}   |   רשת: http://{ip}:{port}\n")
    app.run(host="0.0.0.0",port=port,debug=False)

