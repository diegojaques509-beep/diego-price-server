from flask import Flask, jsonify, make_response, render_template, request
import yfinance as yf
from datetime import datetime
import pytz
import os
import sqlite3

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'portfolio.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            name TEXT,
            shares REAL NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            total_value REAL NOT NULL,
            recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Seed existing holdings if table is empty
    count = conn.execute("SELECT COUNT(*) FROM holdings").fetchone()[0]
    if count == 0:
        conn.execute("INSERT INTO holdings (ticker, name, shares) VALUES (?, ?, ?)",
                     ('TAAIX', 'Thrivent Aggressive Allocation Fund S', 414.198))
        conn.execute("INSERT INTO holdings (ticker, name, shares) VALUES (?, ?, ?)",
                     ('AALXX', 'Thrivent Money Market Fund S', 2046.790))
    conn.commit()
    conn.close()


def cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


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


def pt_time():
    pt = pytz.timezone("America/Los_Angeles")
    return datetime.now(pt).strftime("%b %d, %Y %I:%M %p PT")


# ── Pages ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── API: Holdings ─────────────────────────────────────────────────────────────

@app.route("/api/holdings", methods=["GET", "OPTIONS"])
def get_holdings():
    if request.method == "OPTIONS":
        return cors(make_response("", 200))

    conn = get_db()
    rows = conn.execute("SELECT * FROM holdings ORDER BY id").fetchall()
    conn.close()

    result = []
    total_value = 0.0

    for h in rows:
        price = fetch_price(h["ticker"])
        value = round(price * h["shares"], 2) if price else None
        if value:
            total_value += value
        result.append({
            "id": h["id"],
            "ticker": h["ticker"],
            "name": h["name"] or h["ticker"],
            "shares": h["shares"],
            "price": price,
            "value": value,
            "status": "live" if price else "unavailable",
        })

    if total_value > 0:
        conn = get_db()
        conn.execute("INSERT INTO price_history (total_value) VALUES (?)", (total_value,))
        conn.commit()
        conn.close()

    return cors(make_response(jsonify({
        "holdings": result,
        "total_value": round(total_value, 2),
        "updated": pt_time(),
    })))


@app.route("/api/holdings", methods=["POST"])
def add_holding():
    data = request.get_json()
    ticker = (data.get("ticker") or "").upper().strip()
    name = (data.get("name") or ticker).strip()
    try:
        shares = float(data.get("shares", 0))
    except (ValueError, TypeError):
        shares = 0

    if not ticker or shares <= 0:
        return cors(make_response(jsonify({"error": "Invalid ticker or shares"}), 400))

    conn = get_db()
    conn.execute("INSERT INTO holdings (ticker, name, shares) VALUES (?, ?, ?)", (ticker, name, shares))
    conn.commit()
    conn.close()
    return cors(make_response(jsonify({"success": True}), 201))


@app.route("/api/holdings/<int:hid>", methods=["PUT", "OPTIONS"])
def update_holding(hid):
    if request.method == "OPTIONS":
        return cors(make_response("", 200))
    data = request.get_json()
    name = (data.get("name") or "").strip()
    try:
        shares = float(data.get("shares", 0))
    except (ValueError, TypeError):
        shares = 0
    if shares <= 0:
        return cors(make_response(jsonify({"error": "Shares must be > 0"}), 400))
    conn = get_db()
    conn.execute("UPDATE holdings SET shares = ?, name = ? WHERE id = ?", (shares, name, hid))
    conn.commit()
    conn.close()
    return cors(make_response(jsonify({"success": True})))


@app.route("/api/holdings/<int:hid>", methods=["DELETE", "OPTIONS"])
def delete_holding(hid):
    if request.method == "OPTIONS":
        return cors(make_response("", 200))
    conn = get_db()
    conn.execute("DELETE FROM holdings WHERE id = ?", (hid,))
    conn.commit()
    conn.close()
    return cors(make_response(jsonify({"success": True})))


# ── API: Ticker search ────────────────────────────────────────────────────────

@app.route("/api/search")
def search_ticker():
    q = request.args.get("q", "").strip()
    if not q:
        return cors(make_response(jsonify([]), 200))
    try:
        search = yf.Search(q, max_results=8)
        results = []
        for item in (search.quotes or []):
            symbol = item.get("symbol", "")
            name = item.get("longname") or item.get("shortname") or symbol
            results.append({
                "ticker": symbol,
                "name": name,
                "type": item.get("quoteType", ""),
                "exchange": item.get("exchange", ""),
            })
        return cors(make_response(jsonify(results)))
    except Exception as e:
        print(f"Search error: {e}")
        return cors(make_response(jsonify([]), 200))


# ── API: History ──────────────────────────────────────────────────────────────

@app.route("/api/history")
def get_history():
    conn = get_db()
    rows = conn.execute('''
        SELECT DATE(recorded_at) AS date,
               ROUND(AVG(total_value), 2) AS value
        FROM price_history
        WHERE recorded_at >= DATE('now', '-30 days')
        GROUP BY DATE(recorded_at)
        ORDER BY date ASC
    ''').fetchall()
    conn.close()
    return cors(make_response(jsonify([{"date": r["date"], "value": r["value"]} for r in rows])))


@app.route("/health")
def health():
    return cors(make_response(jsonify({"status": "ok"})))


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=True)
