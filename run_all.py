"""
run_all.py — דירונט process supervisor.

Runs ALL parts of the system as child processes and keeps them alive 24/7:
  • dashboard.py        — the web UI
  • telegram_bot.py     — the bot (commands + buttons)
  • facebook_agent.py   — Facebook group scanner (own internal schedule)
  • apartment_agent.py  — Yad2 + Homely scanner (own internal schedule)
  • tips_agent.py       — refreshed once a day

If any child crashes, it is automatically restarted (with backoff), so a single
Selenium hiccup never takes down the bot or the website.

Run:
    python run_all.py

Stop:  Ctrl+C  (gracefully stops all children)

Logs:  each process writes to logs/<name>.log
"""

import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
LOGS = ROOT / "logs"
LOGS.mkdir(exist_ok=True)

PY = sys.executable

# Children inherit this env. Force UTF-8 so Hebrew prints never crash a child
# when its stdout is redirected to a log file (Windows defaults to cp1255).
CHILD_ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}

# Long-running services — supervised and auto-restarted on crash.
SERVICES = {
    "dashboard": [PY, "dashboard.py"],
    "telegram":  [PY, "telegram_bot.py"],
    "facebook":  [PY, "facebook_agent.py"],
    "yad2":      [PY, "apartment_agent.py"],
}

_stop = threading.Event()


def _log(name: str, msg: str):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{name}] {msg}"
    print(line, flush=True)
    try:
        with open(LOGS / "supervisor.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def supervise(name: str, cmd: list):
    """Run one service forever, restarting it if it exits. Backoff on rapid crashes."""
    backoff = 2
    while not _stop.is_set():
        _log(name, "starting…")
        logf = open(LOGS / f"{name}.log", "a", encoding="utf-8", buffering=1)
        logf.write(f"\n===== started {datetime.now().isoformat()} =====\n")
        start = time.time()
        try:
            proc = subprocess.Popen(
                cmd, cwd=ROOT, stdout=logf, stderr=subprocess.STDOUT, env=CHILD_ENV
            )
            while not _stop.is_set():
                if proc.poll() is not None:
                    break
                time.sleep(1)
            if _stop.is_set():
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except Exception:
                    proc.kill()
                _log(name, "stopped.")
                return
        except Exception as e:
            _log(name, f"failed to launch: {e}")
        finally:
            try:
                logf.close()
            except Exception:
                pass

        # If it ran for a while, reset backoff; if it crashed instantly, slow down.
        ran = time.time() - start
        if ran > 60:
            backoff = 2
        _log(name, f"exited after {ran:.0f}s — restarting in {backoff}s")
        if _stop.wait(backoff):
            return
        backoff = min(backoff * 2, 120)


def daily_tips():
    """Refresh tips once at startup, then once every 24h."""
    while not _stop.is_set():
        try:
            _log("tips", "refreshing daily tips…")
            subprocess.run([PY, "tips_agent.py"], cwd=ROOT, timeout=300, env=CHILD_ENV)
        except Exception as e:
            _log("tips", f"error: {e}")
        # sleep 24h (checking the stop flag every minute)
        for _ in range(24 * 60):
            if _stop.wait(60):
                return


def main():
    print("=" * 60)
    print("  דירונט — מפעיל את כל המערכת (Ctrl+C לעצירה)")
    print(f"  לוגים: {LOGS}")
    print("=" * 60)

    threads = []
    for name, cmd in SERVICES.items():
        t = threading.Thread(target=supervise, args=(name, cmd), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(1.5)  # stagger startups (avoid 4 Chromes booting at once)

    threading.Thread(target=daily_tips, daemon=True).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nעוצר את כל התהליכים…")
        _stop.set()
        for t in threads:
            t.join(timeout=15)
        print("הכל נעצר. להתראות!")


if __name__ == "__main__":
    main()
