"""
agent_status.py — a tiny cross-process "what is the agent doing right now" board.

WHY THIS EXISTS
  The scanners (facebook_agent, apartment_agent) run as SEPARATE processes from
  the dashboard. They can't share memory, so they share a small JSON file — the
  same pattern as the rest of the system (the JSON store as an integration point).

  Each agent reports its live state here; the dashboard reads it and shows a
  "agent activity" widget so you can see exactly what's happening and when.

USAGE
  from agent_status import set_status
  set_status("facebook", "scanning", "סורק קבוצה 3/8", found=2)
  set_status("facebook", "idle", "הסתיים", found=5, next_run="14:30")
"""

import json
import os
from datetime import datetime
from pathlib import Path

STATUS_F = Path(__file__).parent / "agent_status.json"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_status() -> dict:
    if STATUS_F.exists():
        try:
            return json.loads(STATUS_F.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def set_status(agent: str, state: str, detail: str = "", **extra):
    """
    Update one agent's status.
      state:  "scanning" | "idle" | "error" | "disabled" | "starting"
      detail: human-readable text shown in the UI
      extra:  any extra fields (found, last_run, next_run, ...)

    Written atomically (temp file + os.replace) so the dashboard never reads a
    half-written file.
    """
    data = read_status()
    entry = data.get(agent, {})
    entry.update({"state": state, "detail": detail, "updated": _now(), **extra})
    data[agent] = entry
    try:
        tmp = STATUS_F.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, STATUS_F)  # atomic on the same filesystem
    except Exception:
        pass  # status reporting must never crash the agent
