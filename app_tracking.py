"""
app_tracking.py — the shared "apartments we're actively checking" board.

WHY THIS EXISTS
  Favorites (app_auth) are a per-person "I like this" list. Tracking is the
  shared workspace for the couple: the apartments you're actually pursuing,
  with status, contact, viewing time, rating and notes. Both partners see and
  edit the same board (it's a joint decision).

STORAGE
  tracking.json — a list of items. Simple, debuggable, same pattern as the
  rest of the system.
"""

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
TRACK_F = ROOT / "tracking.json"

# Pipeline statuses (value -> Hebrew label). The UI colours them.
STATUSES = {
    "to_contact": "ליצור קשר",
    "scheduled":  "נקבעה צפייה",
    "visited":    "ראינו",
    "candidate":  "מועמדת מובילה",
    "rejected":   "נפסל",
}

# Fields a client is allowed to set/update (whitelist — never trust the client blindly)
_EDITABLE = {"address", "price", "rooms", "contact", "url",
             "status", "viewing_date", "rating", "notes"}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def load_tracking() -> list:
    if TRACK_F.exists():
        try:
            return json.loads(TRACK_F.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_tracking(items: list):
    TRACK_F.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def add_item(data: dict, added_by: str) -> dict:
    items = load_tracking()
    item = {
        "id": "trk_" + datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "address": data.get("address", "").strip(),
        "price": data.get("price", "") or "",
        "rooms": data.get("rooms", "") or "",
        "contact": data.get("contact", "").strip(),
        "url": data.get("url", "").strip(),
        "status": data.get("status") if data.get("status") in STATUSES else "to_contact",
        "viewing_date": data.get("viewing_date", "").strip(),
        "rating": int(data.get("rating") or 0),
        "notes": data.get("notes", "").strip(),
        "source_id": data.get("source_id", ""),
        "added_by": added_by,
        "added_at": _now(),
    }
    items.insert(0, item)  # newest first
    save_tracking(items)
    return item


def update_item(item_id: str, data: dict) -> dict | None:
    items = load_tracking()
    for it in items:
        if it["id"] == item_id:
            for k, v in data.items():
                if k in _EDITABLE:
                    if k == "rating":
                        it[k] = int(v or 0)
                    elif k == "status":
                        it[k] = v if v in STATUSES else it.get("status", "to_contact")
                    else:
                        it[k] = v
            save_tracking(items)
            return it
    return None


def delete_item(item_id: str) -> bool:
    items = load_tracking()
    new = [it for it in items if it["id"] != item_id]
    if len(new) != len(items):
        save_tracking(new)
        return True
    return False
