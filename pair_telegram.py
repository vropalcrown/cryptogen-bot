import httpx
import time
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

TOKEN = "8886782057:AAGQGLMh7Fana0-o2WXL4ez9qpfyIw-A2m0"
ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")

def pair():
    print("=" * 65)
    print("      📲 TELEGRAM PHONE NOTIFICATION PAIRING TOOL")
    print("=" * 65)
    print("Bot Handle : @Let_the_sound_of_profit_come_bot")
    print("Action     : Please open Telegram, search your bot, and tap START (or send 'hi').")
    print("Listening for incoming message from your phone...")
    print("=" * 65)

    offset = None
    for attempt in range(20):
        url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
        params = {"timeout": 10}
        if offset:
            params["offset"] = offset

        try:
            res = httpx.get(url, params=params, timeout=15.0)
            if res.status_code == 200:
                updates = res.json().get("result", [])
                if updates:
                    latest = updates[-1]
                    chat_id = str(latest.get("message", {}).get("chat", {}).get("id"))
                    sender_name = latest.get("message", {}).get("from", {}).get("first_name", "User")
                    
                    if chat_id:
                        print(f"\n🎉 Message detected from {sender_name}! (Chat ID: {chat_id})")
                        # Update .env
                        with open(ENV_PATH, "r") as f:
                            lines = f.readlines()
                        new_lines = []
                        for line in lines:
                            if line.startswith("TELEGRAM_CHAT_ID="):
                                new_lines.append(f"TELEGRAM_CHAT_ID={chat_id}\n")
                            else:
                                new_lines.append(line)
                        with open(ENV_PATH, "w") as f:
                            f.writelines(new_lines)
                        print("✅ TELEGRAM_CHAT_ID saved to .env!")

                        # Send test message
                        send_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
                        msg_text = "🚀 *CryptoGen Activated!*\n\nYour mobile alerts are now live. You will receive notifications here for every buy, stop-loss, and profit exit."
                        httpx.post(send_url, json={"chat_id": chat_id, "text": msg_text, "parse_mode": "Markdown"})
                        print("📱 Test alert sent to your Telegram phone app!")
                        return True
        except Exception as e:
            pass
        time.sleep(2)

    print("\n⚠️ No message detected yet. You can run 'python pair_telegram.py' again after sending /start.")
    return False

if __name__ == "__main__":
    pair()
