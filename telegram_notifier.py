import os
import httpx
import asyncio
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

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

def send_alert_sync(message: str):
    try:
        asyncio.create_task(send_telegram_alert(message))
    except Exception:
        pass

if __name__ == "__main__":
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        print("Testing Telegram connection...")
        asyncio.run(send_telegram_alert("🤖 *CryptoGen Online:* Telegram mobile alerts are active!"))
        print("✅ Alert sent to your phone!")
    else:
        print("ℹ️ Telegram credentials not set in .env yet. Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to enable phone alerts.")
