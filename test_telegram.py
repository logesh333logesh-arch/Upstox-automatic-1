"""
Telegram Connectivity Test
----------------------------
இது run ஆனா, Telegram Bot Token & Chat ID சரியா இருக்கான்னு உடனே தெரியும்.
Scanner logic எதுவும் இதுல இல்ல - வெறும் "connection working" test message மட்டும்.
"""

import os
import requests
from datetime import datetime
import pytz

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

IST = pytz.timezone("Asia/Kolkata")


def send_test_message():
    now = datetime.now(IST).strftime("%d-%b-%Y %I:%M %p")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"✅ Scanner2 Telegram Test\nConnection working fine!\nTime: {now} IST",
        "parse_mode": "Markdown",
    }
    resp = requests.post(url, json=payload)
    print(f"Status code: {resp.status_code}")
    print(f"Response: {resp.text}")
    resp.raise_for_status()
    print("Test message அனுப்பப்பட்டது - Telegram check பண்ணுங்க!")


if __name__ == "__main__":
    send_test_message()
