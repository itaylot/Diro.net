"""
app_env.py — tiny shared config/secrets helper.

Loads a .env file (if present) so secrets like the Telegram token can live in
environment variables on a server instead of being committed in settings.json.

Usage:
    from app_env import secret
    token = secret("TELEGRAM_TOKEN", settings.get("telegram_token", ""))
"""

import os
import sys

# Force UTF-8 stdout/stderr so Hebrew prints never crash on Windows (cp1255),
# especially when run_all.py redirects child output to log files. Importing
# this module at the top of any entry point makes that entry point safe.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from dotenv import load_dotenv
    load_dotenv()  # reads .env in the project root if it exists
except Exception:
    # python-dotenv not installed — env vars still work, .env just won't auto-load
    pass


def secret(env_key: str, fallback: str = "") -> str:
    """Return the env var if set, otherwise the fallback (e.g. settings.json value)."""
    return os.getenv(env_key) or fallback
