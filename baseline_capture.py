"""
Baseline Capture Script
-------------------------
Market open ஆன உடனே (9:16 AM) ஒரு தடவை run ஆகி, ஒவ்வொரு index/commodity-க்கும்
Weekly + Monthly (applicable-ஆ இருக்கிறதுக்கு) ATM strike கண்டுபிடிச்சு,
அதுக்கு மேல 10 OTM strikes-ன் OPENING premium-ஐ baseline_premiums.json-ல save பண்ணும்.

இதுக்கு அப்புறம் தான் scanner.py ஓடி, spike detect பண்ணும்.
"""

import os
import json
import requests
from config import INDICES, MCX_COMMODITIES, BASELINE_FILE

UPSTOX_ACCESS_TOKEN = os.environ["UPSTOX_ACCESS_TOKEN"]
HEADERS = {
    "Authorization": f"Bearer {UPSTOX_ACCESS_TOKEN}",
    "Accept": "application/json",
}


def get_spot_price(underlying_key):
    url = "https://api.upstox.com/v2/market-quote/ltp"
    params = {"instrument_key": underlying_key}
    resp = requests.get(url, headers=HEADERS, params=params)
    resp.raise_for_status()
    body = resp.json()
    data = body.get("data", {})
    if not data:
        raise Exception(
            f"[SPOT PRICE FAIL] instrument_key='{underlying_key}' க்கு data காலியா "
            f"வந்துச்சு. Full response: {body}. "
            f"இந்த instrument_key தப்பா இருக்கலாம் - Upstox instruments master "
            f"file-ல verify பண்ணு."
        )
    first_key = list(data.keys())[0]
    return data[first_key]["last_price"]


def get_nearest_expiry(underlying_key, weekly=True):
    """
    Upstox /option/contract endpoint எல்லா available expiries கொடுக்கும்.
    Weekly=True na nearest expiry edukkanum, False na (monthly) andha
    month-oda last expiry edukkanum.
    """
    url = "https://api.upstox.com/v2/option/contract"
    params = {"instrument_key": underlying_key}
    resp = requests.get(url, headers=HEADERS, params=params)
    resp.raise_for_status()
    contracts = resp.json()["data"]
    expiries = sorted(set(c["expiry"] for c in contracts))

    if weekly:
        return expiries[0]  # nearest expiry

    # monthly = current month-oda last expiry date
    from datetime import datetime
    current_month = datetime.now().month
    month_expiries = [e for e in expiries if datetime.strptime(e, "%Y-%m-%d").month == current_month]
    return month_expiries[-1] if month_expiries else expiries[-1]


def fetch_option_chain(underlying_key, expiry_date):
    url = "https://api.upstox.com/v2/option/chain"
    params = {"instrument_key": underlying_key, "expiry_date": expiry_date}
    resp = requests.get(url, headers=HEADERS, params=params)
    resp.raise_for_status()
    return resp.json()["data"]


def select_otm_strikes(chain_data, spot_price, num_strikes):
    strikes = sorted(chain_data, key=lambda x: x["strike_price"])
    atm_index = min(
        range(len(strikes)),
        key=lambda i: abs(strikes[i]["strike_price"] - spot_price),
    )
    return strikes[atm_index: atm_index + num_strikes]


def capture_baseline_for_symbol(symbol_name, symbol_config, contract_type, weekly, baseline):
    print(f"[TRY] {symbol_name}_{contract_type} - underlying_key='{symbol_config['underlying_key']}'")
    spot = get_spot_price(symbol_config["underlying_key"])
    expiry = get_nearest_expiry(symbol_config["underlying_key"], weekly=weekly)
    chain_data = fetch_option_chain(symbol_config["underlying_key"], expiry)
    selected = select_otm_strikes(chain_data, spot, symbol_config["otm_strikes"])

    key = f"{symbol_name}_{contract_type}"
    baseline[key] = {}
    for s in selected:
        # CE and PE ரெண்டையும் store பண்ணு
        for opt_type in ["call_options", "put_options"]:
            if opt_type in s:
                sym = s[opt_type]["instrument_key"]
                premium = s[opt_type]["market_data"]["ltp"]
                baseline[key][sym] = premium
    baseline[key + "_expiry"] = expiry
    print(f"[BASELINE SET] {key} - {len(selected)} strikes, expiry {expiry}")


def main():
    baseline = {}

    for name, cfg in INDICES.items():
        if cfg["has_weekly"]:
            capture_baseline_for_symbol(name, cfg, "WEEKLY", True, baseline)
        if cfg["has_monthly"]:
            capture_baseline_for_symbol(name, cfg, "MONTHLY", False, baseline)

    for name, cfg in MCX_COMMODITIES.items():
        capture_baseline_for_symbol(name, cfg, "MONTHLY", False, baseline)

    with open(BASELINE_FILE, "w") as f:
        json.dump(baseline, f, indent=2)

    print(f"Baseline capture முடிந்தது. {BASELINE_FILE} save ஆனது.")


if __name__ == "__main__":
    main()
