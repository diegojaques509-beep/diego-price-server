from flask import Flask, jsonify, make_response
import yfinance as yf
from datetime import datetime
import os

app = Flask(__name__)

def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = '*'
    return response

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

@app.route("/", methods=["GET","OPTIONS"])
def home():
    return add_cors(make_response(jsonify({"status": "ok"})))

@app.route("/prices", methods=["GET","OPTIONS"])
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
    return add_cors(make_response(jsonify(result)))

@app.route("/health", methods=["GET","OPTIONS"])
def health():
    return add_cors(make_response(jsonify({"status": "ok"})))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)
