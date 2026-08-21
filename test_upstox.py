"""
Upstox Token/API Validity Check
----------------------------------
இது Upstox API-ஐ ஒரு simple call (User Profile) வெச்சு டெஸ்ட் பண்ணி,
Token, API Key correct-ஆ இருக்கானு Telegram-க்கே result அனுப்பும்.

Success ஆனா: Account name/user_id கிடைக்கும் -> token valid.
Fail ஆனா (401): Token expired/wrong -> Telegram-ல அந்த error வரும்.
"""

import os
import requests
from datetime import datetime
import pytz

UPSTOX_ACCESS_TOKEN = os.environ["UPSTOX_ACCESS_TOKEN"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

IST = pytz.timezone("Asia/Kolkata")
HEADERS = {
    "Authorization": f"Bearer {UPSTOX_ACCESS_TOKEN}",
    "Accept": "application/json",
}


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)


def check_upstox_token():
    now = datetime.now(IST).strftime("%d-%b-%Y %I:%M %p")
    url = "https://api.upstox.com/v2/user/profile"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)

        if resp.status_code == 200:
            data = resp.json()["data"]
            name = data.get("user_name", "N/A")
            user_id = data.get("user_id", "N/A")
            msg = (
                f"✅ *Upstox Token Check - VALID*\n"
                f"User: {name}\n"
                f"User ID: {user_id}\n"
                f"Time: {now} IST\n\n"
                f"Token சரியா வேலை செய்யுது - scanner ready!"
            )
            print("[SUCCESS] Token valid.", data)
        else:
            msg = (
                f"❌ *Upstox Token Check - FAILED*\n"
                f"Status Code: {resp.status_code}\n"
                f"Response: {resp.text[:300]}\n"
                f"Time: {now} IST\n\n"
                f"Token expire ஆகி இருக்கலாம் - புதுசா generate பண்ணு."
            )
            print(f"[FAIL] Status {resp.status_code}: {resp.text}")

    except Exception as e:
        msg = (
            f"❌ *Upstox Token Check - ERROR*\n"
            f"Error: {str(e)}\n"
            f"Time: {now} IST"
        )
        print(f"[ERROR] {e}")

    send_telegram(msg)
    print("Result Telegram-க்கு அனுப்பப்பட்டது.")


if __name__ == "__main__":
    check_upstox_token()
