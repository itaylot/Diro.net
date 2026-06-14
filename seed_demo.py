"""
seed_demo.py — populate the read-only "demo" account for portfolio viewing.

WHY THIS EXISTS
  users.json / favorites.json / tracking.json are git-ignored (real data), so a
  demo account can't be shipped via `git pull`. This script rebuilds it from
  scratch on any machine — run it on the server after deploying:

      docker compose exec dironet python seed_demo.py

  Idempotent: safe to run repeatedly. It (re)sets the demo password, favorites
  the current top-scored listings, and ensures three sample tracking entries.

WHAT IT CREATES
  • user "demo" / password "demo1234"
  • demo's favorites = the 3 highest-scored listings currently in the store
    (chosen dynamically so the IDs are always valid on this machine)
  • 3 tracking-board entries with realistic statuses + notes
"""

import app_env  # noqa: F401 — forces UTF-8 stdout (✓ + Hebrew prints)
import storage
from pathlib import Path

ROOT = Path(__file__).parent

DEMO_USER = "demo"
DEMO_PASS = "demo1234"


def seed_user():
    import app_auth
    app_auth.set_password(DEMO_USER, DEMO_PASS)
    print(f"✓ user '{DEMO_USER}' set (password: {DEMO_PASS})")


def seed_favorites():
    """Favorite the 3 highest-scored real listings (dynamic — IDs differ per machine)."""
    listings = storage.read_json(ROOT / "all_listings.json", [])
    top = sorted(listings, key=lambda l: l.get("score", 0), reverse=True)[:3]
    ids = [l["id"] for l in top]

    def _mut(favs):
        favs = favs or {}
        favs[DEMO_USER] = ids
        return favs

    storage.update_json(ROOT / "favorites.json", _mut, {})
    print(f"✓ {len(ids)} favorites set for '{DEMO_USER}'")


def seed_tracking():
    """Ensure three sample tracking entries exist (idempotent by id)."""
    entries = [
        {
            "id": "trk_demo_001",
            "address": "רחוב ויצמן 12, שכונה ב׳",
            "price": "3300", "rooms": "3",
            "contact": "יוסי כהן, 050-1234567",
            "url": "",
            "status": "visited", "viewing_date": "2026-06-13", "rating": 4,
            "notes": "דירה מוארת, קומה 3. הבניין טיפה ישן אבל השכנים נחמדים. "
                     "המטבח קטן מדי. שווה לחזור אליה אם לא נמצא משהו טוב יותר.",
            "source_id": "", "added_by": DEMO_USER, "added_at": "2026-06-13 09:00",
        },
        {
            "id": "trk_demo_002",
            "address": "שדרות רגר 48, שכונה ב׳",
            "price": "3100", "rooms": "4",
            "contact": "מירי לוי (בעלת הדירה)",
            "url": "",
            "status": "scheduled", "viewing_date": "2026-06-16", "rating": 5,
            "notes": "נראה מצוין! 4 חדרים ב-3100 זה מחיר מעולה לשכונה ב׳. "
                     "צפייה ביום ראשון 10:00. לזכור לשאול על ועד בית ומיזוג.",
            "source_id": "", "added_by": DEMO_USER, "added_at": "2026-06-14 08:30",
        },
        {
            "id": "trk_demo_003",
            "address": "רחוב ביאליק 7, שכונה ב׳",
            "price": "3700", "rooms": "3.5",
            "contact": "054-9876543",
            "url": "",
            "status": "to_contact", "viewing_date": "", "rating": 3,
            "notes": "מחיר גבוה יחסית אבל הדירה משופצת. לנסות להתמקח ל-3500.",
            "source_id": "", "added_by": DEMO_USER, "added_at": "2026-06-14 11:00",
        },
    ]

    def _mut(items):
        items = items or []
        existing = {t["id"] for t in items}
        added = [e for e in entries if e["id"] not in existing]
        return added + items  # newest first

    storage.update_json(ROOT / "tracking.json", _mut, [])
    print(f"✓ tracking entries ensured ({len(entries)} sample apartments)")


if __name__ == "__main__":
    seed_user()
    seed_favorites()
    seed_tracking()
    print("\nDemo account ready. Log in with demo / demo1234")
