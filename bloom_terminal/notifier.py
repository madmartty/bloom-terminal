import sys
import json
import os
import subprocess
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    TELEGRAM_ENABLED, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    IMESSAGE_ENABLED, IMESSAGE_RECIPIENT,
)


def maybe_send(alerts: list[dict], asof: str | None = None):
    if not alerts:
        return

    run_date = asof or date.today().isoformat()
    high = [a for a in alerts if a["severity"] == "high"]
    warn = [a for a in alerts if a["severity"] == "warn"]

    if TELEGRAM_ENABLED and TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        _send_telegram(alerts, run_date)
    if IMESSAGE_ENABLED and IMESSAGE_RECIPIENT:
        _send_imessage(alerts, run_date)


def _send_telegram(alerts: list[dict], run_date: str):
    try:
        import requests
        high = [a for a in alerts if a["severity"] == "high"]
        warn = [a for a in alerts if a["severity"] == "warn"]
        info = [a for a in alerts if a["severity"] == "info"]

        msg = f"<b>Bloom Terminal — {run_date}</b>\n"
        if high:
            msg += f"\n🔴 <b>{len(high)} High</b>\n" + "\n".join(f"• {a['message']}" for a in high)
        if warn:
            msg += f"\n🟡 <b>{len(warn)} Warning</b>\n" + "\n".join(f"• {a['message']}" for a in warn)
        if info:
            msg += f"\nℹ️ <b>{len(info)} Info</b>\n" + "\n".join(f"• {a['message']}" for a in info)

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"})
    except Exception:
        pass


def _send_imessage(alerts: list[dict], run_date: str):
    if not IMESSAGE_RECIPIENT:
        return
    high = [a for a in alerts if a["severity"] == "high"]
    msg = f"Bloom Terminal — {run_date}\n"
    if high:
        msg += f"\n⚠️ {len(high)} alerts"
    try:
        script = f'display notification "{msg}" with title "Bloom Terminal"'
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
    except Exception:
        pass
