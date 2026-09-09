"""
CryptoGen Interactive Telegram Command Center

Provides 2-way communication with your bot:
  1. Push notifications (buys, sells, stop-losses, TP, milestones)
  2. Mobile Interactive Inline Buttons (1-tap status, scorecard, auto-tune, pause/resume)
  3. Remote control commands from your phone:
     - /status   : View real-time portfolio, positions, cycle & regime
     - /scorecard: Instant 24h Daily PnL scorecard
     - /tune     : Trigger automated self-tuning engine
     - /pause    : Temporarily pause autonomous buying
     - /resume   : Unpause autonomous buying
     - /closeall : Emergency panic button (sells all positions to SOL and refunds rent)
     - /harvest  : Manually trigger profit sweep
     - /help     : List available commands
"""

import os
import sys
import httpx
import asyncio
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "https://cryptogen-bot.onrender.com").rstrip("/")

# Global offset to track read messages
_LAST_UPDATE_ID = 0

# Persistent Interactive Mobile Buttons
DEFAULT_INLINE_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "📊 Status", "callback_data": "/status"},
            {"text": "🏆 Scorecard", "callback_data": "/scorecard"}
        ],
        [
            {"text": "🧬 Auto-Tune", "callback_data": "/tune"},
            {"text": "💰 Harvest", "callback_data": "/harvest"}
        ],
        [
            {"text": "⏸️ Pause", "callback_data": "/pause"},
            {"text": "▶️ Resume", "callback_data": "/resume"}
        ],
        [
            {"text": "🌐 Web Terminal", "url": RENDER_EXTERNAL_URL},
            {"text": "🚨 Close All", "callback_data": "/closeall"}
        ]
    ]
}

async def answer_callback_query(callback_id: str, text: str = "⚡ Command Received!"):
    """
    Acknowledges Telegram button tap to dismiss mobile spinning wheel immediately.
    """
    if not TELEGRAM_BOT_TOKEN or not callback_id:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    payload = {
        "callback_query_id": str(callback_id),
        "text": text
    }
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            await client.post(url, json=payload)
    except Exception:
        pass

async def send_telegram_alert(message: str, reply_markup: Optional[Dict[str, Any]] = None, show_buttons: bool = True):
    """
    Sends an instant notification message to your Telegram phone app.
    Attaches interactive inline buttons by default for single-tap remote control.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    elif show_buttons:
        payload["reply_markup"] = DEFAULT_INLINE_KEYBOARD

    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            res = await client.post(url, json=payload)
            if res.status_code != 200:
                print(f"⚠️ [Telegram Alert Error] {res.text}")
                # Fallback without parse_mode if markdown entities caused a 400 Bad Request
                if "can't parse entities" in res.text or res.status_code == 400:
                    payload.pop("parse_mode", None)
                    await client.post(url, json=payload)
        except Exception as e:
            print(f"⚠️ [Telegram Network Error] {e}")

async def poll_telegram_commands() -> List[str]:
    """
    Polls the Telegram Bot API for incoming user commands & inline button taps.
    Returns a list of commands sent by the authorized user (e.g., ['/status', '/tune']).
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

                    # 1. Text Message Commands (/status, /pause, etc.)
                    message = update.get("message", {})
                    from_id = str(message.get("from", {}).get("id", ""))
                    text = message.get("text", "").strip()

                    if from_id == str(TELEGRAM_CHAT_ID) and text.startswith("/"):
                        commands.append(text.lower().split()[0])

                    # 2. Interactive Inline Button Callbacks
                    cb = update.get("callback_query", {})
                    if cb:
                        cb_id = cb.get("id")
                        cb_from = str(cb.get("from", {}).get("id", ""))
                        cb_data = cb.get("data", "").strip()

                        if cb_from == str(TELEGRAM_CHAT_ID) and cb_data:
                            # Acknowledge callback query to stop mobile loading spinner
                            await answer_callback_query(cb_id, text="⚡ Executing...")
                            if cb_data.startswith("/"):
                                commands.append(cb_data.lower().split()[0])
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
        print("Testing Telegram connection with Interactive Buttons...")
        asyncio.run(send_telegram_alert("🤖 *CryptoGen Command Center Active:*\nTap buttons below to control bot!"))
        print("✅ Alert with inline buttons sent to your phone!")
    else:
        print("ℹ️ Telegram credentials not set in .env yet.")
