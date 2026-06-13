"""
app_auth.py — simple per-user login + favorites for the dashboard.

WHY THIS EXISTS
  We want a real in-app login (a personal area per user), not a browser popup.
  Two users (itay, neta), each with their own password and their own favorites.

DESIGN (kept deliberately simple)
  • Users + hashed passwords live in users.json (git-ignored).
    Passwords are hashed with Werkzeug (ships with Flask — no extra dependency).
  • Favorites live in favorites.json: { "itay": [listing_id, ...], "neta": [...] }.
  • Login state is a signed Flask session cookie (server holds a secret key).

SET A PASSWORD (run once per user; on the server use `docker compose exec`):
    python app_auth.py set itay
    python app_auth.py set neta
"""

import json
import os
import secrets
import sys
from functools import wraps
from pathlib import Path

from werkzeug.security import generate_password_hash, check_password_hash

import storage

ROOT = Path(__file__).parent
USERS_F = ROOT / "users.json"
FAVS_F = ROOT / "favorites.json"
SECRET_F = ROOT / ".flask_secret"


# ─── Session secret key ───────────────────────────────────────────────────────

def get_secret_key() -> str:
    """A stable secret for signing session cookies (env > file > generated)."""
    k = os.getenv("FLASK_SECRET")
    if k:
        return k
    if SECRET_F.exists():
        return SECRET_F.read_text(encoding="utf-8").strip()
    k = secrets.token_hex(32)
    try:
        SECRET_F.write_text(k, encoding="utf-8")
    except Exception:
        pass
    return k


# ─── Users ────────────────────────────────────────────────────────────────────

def load_users() -> dict:
    return storage.read_json(USERS_F, {})


def save_users(u: dict):
    storage.write_json(USERS_F, u)


def set_password(username: str, password: str):
    h = generate_password_hash(password)
    def _mut(u):
        u = u or {}
        u[username] = {"password_hash": h}
        return u
    storage.update_json(USERS_F, _mut, {})


def check_login(username: str, password: str) -> bool:
    rec = load_users().get((username or "").strip().lower())
    if not rec:
        return False
    return check_password_hash(rec.get("password_hash", ""), password)


# ─── Favorites (per user) ─────────────────────────────────────────────────────

def load_favorites() -> dict:
    return storage.read_json(FAVS_F, {})


def save_favorites(f: dict):
    storage.write_json(FAVS_F, f)


def get_user_favorites(username: str) -> list:
    return load_favorites().get(username, [])


def toggle_favorite(username: str, listing_id: str) -> bool:
    """Add/remove a listing from the user's favorites. Returns True if now favorited."""
    state = {}
    def _mut(favs):
        favs = favs or {}
        ids = favs.get(username, [])
        if listing_id in ids:
            ids.remove(listing_id)
            state["fav"] = False
        else:
            ids.append(listing_id)
            state["fav"] = True
        favs[username] = ids
        return favs
    storage.update_json(FAVS_F, _mut, {})
    return state["fav"]


# ─── Route protection ─────────────────────────────────────────────────────────

def login_required(f):
    """Protect a Flask route: APIs get 401 JSON, pages redirect to /login."""
    from flask import session, redirect, request, jsonify

    @wraps(f)
    def wrapper(*a, **kw):
        if not session.get("user"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "auth_required"}), 401
            return redirect("/login")
        return f(*a, **kw)

    return wrapper


# ─── CLI: set a password ──────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "set":
        user = sys.argv[2].strip().lower()
        if len(sys.argv) >= 4:
            pw = sys.argv[3]
        else:
            import getpass
            pw = getpass.getpass(f"New password for '{user}': ")
            if pw != getpass.getpass("Repeat password: "):
                print("Passwords don't match.")
                sys.exit(1)
        if not pw:
            print("Empty password — aborting.")
            sys.exit(1)
        set_password(user, pw)
        print(f"Password set for '{user}'. Users: {list(load_users().keys())}")
    else:
        print("Usage: python app_auth.py set <username> [password]")
