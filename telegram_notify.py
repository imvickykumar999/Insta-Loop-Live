"""Send Telegram notifications via Bot API (optional, env-configured)."""

import json
import os

from env_loader import load_env

load_env()
import threading
import urllib.error
import urllib.request


def is_configured() -> bool:
    return bool(
        os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        and os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    )


def send_telegram_sync(message: str) -> tuple[bool, str]:
    """Send a message; returns (ok, detail)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False, "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        if not body.get("ok"):
            return False, body.get("description", "Telegram API error")
        return True, "sent"
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8"))
            return False, err.get("description", str(e))
        except Exception:
            return False, str(e)
    except Exception as e:
        return False, str(e)


def send_telegram(message: str, on_error=None) -> None:
    """Fire-and-forget Telegram message."""

    def _send():
        ok, detail = send_telegram_sync(message)
        if not ok and on_error:
            on_error(detail)

    threading.Thread(target=_send, daemon=True).start()
