"""
Scanner 2: Options Premium Spike Scanner
------------------------------------------
Logic:
1. Market open (9:16 AM) ஆனதும் ஒரு தடவை run ஆகி, ஒவ்வொரு index/commodity-க்கும்
   ATM strike கண்டுபிடிச்சு, அதுக்கு மேல 10 OTM CE + 10 OTM PE strikes-ன்
   OPENING premium-ஐ baseline-ஆ JSON file-ல save பண்ணும். (baseline_capture.py)

2. அதுக்கு அப்புறம் ஒவ்வொரு run-லயும் (cron every N mins), current premium-ஐ
   baseline-ஓட compare பண்ணி, spike threshold தாண்டினா Telegram alert அனுப்பும்.
   (இந்த file - scanner.py)

3. ஒரு strike ஒரு தடவை alert ஆனா, அதே day-க்கு திரும்ப alert வராம
   alerted_strikes.json-ல track பண்ணும்.
"""

import os
import json
import requests
from datetime import datetime
import pytz

from config import INDICES, MCX_COMMODITIES, BASELINE_FILE, ALERTED_FILE

UPSTOX_ACCESS_TOKEN = os.environ["UPSTOX_ACCESS_TOKEN"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

IST = pytz.timezone("Asia/Kolkata")
HEADERS = {
    "Authorization": f"Bearer {UPSTOX_ACCESS_TOKEN}",
    "Accept": "application/json",
}


# -----------------------------------------------------------
# Step 1: Option chain fetch பண்றது (Upstox Option Chain API)
# -----------------------------------------------------------
def fetch_option_chain(underlying_key, expiry_date):
    """
    Upstox /option/chain endpoint - ஒரு underlying + expiry-க்கு
    எல்லா strikes-ன் CE/PE data (LTP உட்பட) கொடுக்கும்.
    """
    url = "https://api.upstox.com/v2/option/chain"
    params = {"instrument_key": underlying_key, "expiry_date": expiry_date}
    resp = requests.get(url, headers=HEADERS, params=params)
    resp.raise_for_status()
    return resp.json()["data"]


# -----------------------------------------------------------
# Step 2: ATM கண்டுபிடிச்சு, அதுக்கு மேல N OTM strikes select பண்றது
# -----------------------------------------------------------
def select_otm_strikes(chain_data, spot_price, num_strikes):
    """
    chain_data ல ஒவ்வொரு entry-லயும் strike_price இருக்கும்.
    ATM = spot price-க்கு மிக அருகான strike.
    அதுக்கு மேல (higher) இருக்கிற num_strikes எடுக்கறோம்
    (CE-க்கு OTM = ATM-க்கு மேல, PE-க்கு OTM = ATM-க்கு கீழ் — ஆனா
    உங்க requirement படி 'ATM-க்கு மேல இருக்கிற 10' எடுக்கறோம், CE & PE ரெண்டுக்கும்).
    """
    strikes = sorted(chain_data, key=lambda x: x["strike_price"])
    atm_index = min(
        range(len(strikes)),
        key=lambda i: abs(strikes[i]["strike_price"] - spot_price),
    )
    selected = strikes[atm_index: atm_index + num_strikes]
    return selected


# -----------------------------------------------------------
# Step 3: Baseline load பண்றது (market open-ல capture பண்ணி வெச்சது)
# -----------------------------------------------------------
def load_baseline():
    if not os.path.exists(BASELINE_FILE):
        raise FileNotFoundError(
            f"{BASELINE_FILE} கிடைக்கல. Market open-ல baseline_capture.py "
            "run ஆகி இருக்கணும் — அது இல்லாம spike detect பண்ண முடியாது."
        )
    with open(BASELINE_FILE, "r") as f:
        return json.load(f)


def load_alerted():
    if os.path.exists(ALERTED_FILE):
        with open(ALERTED_FILE, "r") as f:
            return json.load(f)
    return {}


def save_alerted(alerted):
    with open(ALERTED_FILE, "w") as f:
        json.dump(alerted, f, indent=2)


# -----------------------------------------------------------
# Step 4: Telegram alert அனுப்றது
# -----------------------------------------------------------
def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # parse_mode Markdown எடுத்துடுறோம் - strike symbols-ல '_' '|' போன்ற
    # characters இருக்கும், அது Markdown-ஐ confuse பண்ணி 400 error தரும்.
    # Plain text-ஆ அனுப்பினா எந்த character வந்தாலும் problem வராது.
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    resp = requests.post(url, json=payload)
    resp.raise_for_status()


# -----------------------------------------------------------
# Step 5: ஒவ்வொரு index/commodity-க்கும் spike check பண்றது
# -----------------------------------------------------------
def check_spikes_for_symbol(symbol_name, symbol_config, contract_type, baseline, alerted):
    """
    contract_type = "WEEKLY" or "MONTHLY" (indices-க்கு), or "MONTHLY" (MCX-க்கு)
    """
    key = f"{symbol_name}_{contract_type}"
    if key not in baseline:
        print(f"[SKIP] {key} - baseline இல்ல")
        return

    threshold = symbol_config["spike_threshold"]
    strikes_baseline = baseline[key]  # { "NSE_FO|12345": 120.5, ... } - key is instrument_key

    # Current premiums fetch பண்ணு (option chain call)
    chain_data = fetch_option_chain(
        symbol_config["underlying_key"], baseline[key + "_expiry"]
    )

    # chain_data-ல இருந்து instrument_key -> current LTP dictionary build பண்ணு
    # (baseline-ல instrument_key வெச்சு தான் save பண்ணோம், trading_symbol இல்ல -
    #  இது தான் முன்ன alert வராம இருந்ததுக்கு காரணம்)
    current_ltp_by_key = {}
    for c in chain_data:
        for opt_type in ["call_options", "put_options"]:
            if opt_type in c and c[opt_type]:
                ik = c[opt_type].get("instrument_key")
                ltp = c[opt_type].get("market_data", {}).get("ltp")
                if ik is not None:
                    current_ltp_by_key[ik] = ltp

    for strike_symbol, open_premium in strikes_baseline.items():
        if strike_symbol.endswith("_expiry"):
            continue

        current_premium = current_ltp_by_key.get(strike_symbol)
        if current_premium is None:
            print(f"[NO MATCH] {strike_symbol} - current chain data-ல இந்த instrument_key கிடைக்கல")
            continue

        spike = current_premium - open_premium
        print(
            f"[CHECK] {key} | {strike_symbol} | open=₹{open_premium} "
            f"current=₹{current_premium} spike=₹{round(spike,2)} threshold=₹{threshold}"
        )

        alert_key = f"{key}_{strike_symbol}"
        if spike >= threshold and alert_key not in alerted:
            msg = (
                f"🚨 Premium Spike Alert\n"
                f"Symbol: {strike_symbol}\n"
                f"Contract: {contract_type}\n"
                f"Opening Premium: ₹{open_premium}\n"
                f"Current Premium: ₹{current_premium}\n"
                f"Spike: ₹{round(spike, 2)} (Threshold: ₹{threshold})"
            )
            send_telegram_alert(msg)
            alerted[alert_key] = True
            print(f"[ALERT SENT] {strike_symbol} - spike ₹{spike}")


# -----------------------------------------------------------
# Main
# -----------------------------------------------------------
def main():
    now = datetime.now(IST)
    print(f"Scanner run started: {now}")

    baseline = load_baseline()
    alerted = load_alerted()

    for name, cfg in INDICES.items():
        if cfg["has_weekly"]:
            check_spikes_for_symbol(name, cfg, "WEEKLY", baseline, alerted)
        if cfg["has_monthly"]:
            check_spikes_for_symbol(name, cfg, "MONTHLY", baseline, alerted)

    # MCX commodities - Upstox option chain API MCX-க்கு support இல்லாததால DISABLE
    # for name, cfg in MCX_COMMODITIES.items():
    #     check_spikes_for_symbol(name, cfg, "MONTHLY", baseline, alerted)

    save_alerted(alerted)
    print("Scanner run முடிந்தது.")


if __name__ == "__main__":
    main()
