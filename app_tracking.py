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

from datetime import datetime
from pathlib import Path

import storage

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
    return storage.read_json(TRACK_F, [])


def save_tracking(items: list):
    storage.write_json(TRACK_F, items)


def add_item(data: dict, added_by: str) -> dict:
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
    storage.update_json(TRACK_F, lambda items: [item] + (items or []), [])  # newest first
    return item


def update_item(item_id: str, data: dict) -> dict | None:
    state = {"item": None}
    def _mut(items):
        items = items or []
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
                state["item"] = it
        return items
    storage.update_json(TRACK_F, _mut, [])
    return state["item"]


def delete_item(item_id: str) -> bool:
    state = {"removed": False}
    def _mut(items):
        items = items or []
        new = [it for it in items if it["id"] != item_id]
        state["removed"] = len(new) != len(items)
        return new
    storage.update_json(TRACK_F, _mut, [])
    return state["removed"]
