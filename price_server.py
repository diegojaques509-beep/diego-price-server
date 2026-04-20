from flask import Flask, jsonify
from flask_cors import CORS
import yfinance as yf
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)

HOLDINGS = {
    "TAAIX": {"name": "Thrivent Aggressive Allocation Fund S", "shares": 414.198},
    "AALXX": {"name": "Thrivent Money Market Fund S",          "shares": 2046.790},
}

def fetch_price(ticker):
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        price = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
        if price and price > 0:
            return round(float(price), 4)
    except Exception as e:
        print(f"Could not fetch {ticker}: {e}")
    return None

@app.route("/")
def home():
    return jsonify({"status": "ok", "server": "Diego Portfolio Price Server"})

@app.route("/prices")
def prices():
    result = {}
    for ticker, meta in HOLDINGS.items():
        price = fetch_price(ticker)
        result[ticker] = {
            "ticker": ticker,
            "name":   meta["name"],
            "shares": meta["shares"],
            "price":  price,
            "value":  round(price * meta["shares"], 2) if price else None,
            "status": "live" if price else "unavailable",
        }
        print(f"  {ticker}: {'$' + str(price) if price else 'unavailable'}")
    result["_meta"] = {
        "updated": datetime.now().strftime("%I:%M %p"),
        "source":  "yfinance",
    }
    return jsonify(result)

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)
