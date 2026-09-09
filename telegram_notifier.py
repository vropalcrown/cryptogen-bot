"""
CryptoGen Interactive Telegram Command Center

Provides 2-way communication with your bot:
  1. Push notifications (buys, sells, stop-losses, TP, milestones)
  2. Remote control commands from your phone:
     - /status   : View real-time portfolio, positions, cycle & regime
     - /pause    : Temporarily pause autonomous buying
     - /resume   : Unpause autonomous buying
     - /closeall : Emergency panic button (sells all positions to SOL and refunds rent)
     - /harvest  : Manually trigger profit sweep
     - /help     : List available commands
"""

import os
import httpx
import asyncio
from dotenv import load_dotenv
from typing import List, Dict

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Global offset to track read messages
_LAST_UPDATE_ID = 0

async def send_telegram_alert(message: str):
    """
    Sends an instant notification message to your Telegram phone app.
    Free, non-blocking, and safely skipped if tokens aren't configured yet.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            res = await client.post(url, json=payload)
            if res.status_code != 200:
                print(f"⚠️ [Telegram Alert Error] {res.text}")
        except Exception:
            pass

async def poll_telegram_commands() -> List[str]:
    """
    Polls the Telegram Bot API for incoming user commands.
    Returns a list of commands sent by the authorized user (e.g., ['/status', '/pause']).
    """
    global _LAST_UPDATE_ID
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return []

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"offset": _LAST_UPDATE_ID + 1, "timeout": 2}
    commands = []

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            res = await client.get(url, params=params)
            if res.status_code == 200:
                data = res.json()
                updates = data.get("result", [])
                for update in updates:
                    update_id = update.get("update_id", 0)
                    if update_id > _LAST_UPDATE_ID:
                        _LAST_UPDATE_ID = update_id

                    message = update.get("message", {})
                    from_id = str(message.get("from", {}).get("id", ""))
                    text = message.get("text", "").strip()

                    # Security: Only accept commands from the paired user chat ID
                    if from_id == str(TELEGRAM_CHAT_ID) and text.startswith("/"):
                        commands.append(text.lower().split()[0])
    except Exception:
        pass

    return commands

def send_alert_sync(message: str):
    try:
        asyncio.create_task(send_telegram_alert(message))
    except Exception:
        pass

if __name__ == "__main__":
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        print("Testing Telegram connection...")
        asyncio.run(send_telegram_alert("🤖 *CryptoGen Online:* Interactive command center active!\nType /help in chat."))
        print("✅ Alert sent to your phone!")
    else:
        print("ℹ️ Telegram credentials not set in .env yet.")
