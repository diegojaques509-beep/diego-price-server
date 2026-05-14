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
    conn.execute('''CREATE TABLE IF NOT EXISTS holdings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        name TEXT,
        shares REAL NOT NULL,
        manual_price REAL DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        total_value REAL NOT NULL,
        recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS cash_balance (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        value REAL DEFAULT 0
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        amount REAL NOT NULL,
        category TEXT DEFAULT 'Other',
        date_str TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS budget (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        monthly_limit REAL DEFAULT 0
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS budget_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        monthly_limit REAL DEFAULT 0,
        color TEXT DEFAULT '#e8254a'
    )''')

    # Seed defaults
    count = conn.execute("SELECT COUNT(*) FROM holdings").fetchone()[0]
    if count == 0:
        conn.execute("INSERT INTO holdings (ticker, name, shares, manual_price) VALUES (?,?,?,?)",
                     ('TAAIX', 'Thrivent Aggressive Allocation Fund S', 414.198, 0))
        conn.execute("INSERT INTO holdings (ticker, name, shares, manual_price) VALUES (?,?,?,?)",
                     ('AALXX', 'Thrivent Money Market Fund S', 2046.790, 1.00))
    conn.execute("INSERT OR IGNORE INTO cash_balance (id, value) VALUES (1, 0)")
    conn.execute("INSERT OR IGNORE INTO budget (id, monthly_limit) VALUES (1, 0)")
    conn.commit()
    conn.close()


def cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


def fetch_price(ticker, manual_price=0):
    if manual_price and manual_price > 0:
        return round(float(manual_price), 4)
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
    return datetime.now(pt).strftime("%I:%M %p PT")


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── Holdings ──────────────────────────────────────────────────────────────────

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
        price = fetch_price(h["ticker"], h["manual_price"])
        value = round(price * h["shares"], 2) if price else None
        if value:
            total_value += value
        result.append({
            "id": h["id"], "ticker": h["ticker"],
            "name": h["name"] or h["ticker"],
            "shares": h["shares"], "price": price,
            "value": value, "manual": bool(h["manual_price"]),
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
        manual_price = float(data.get("manual_price") or 0)
    except (ValueError, TypeError):
        return cors(make_response(jsonify({"error": "Invalid values"}), 400))
    if not ticker or shares <= 0:
        return cors(make_response(jsonify({"error": "Invalid ticker or shares"}), 400))
    conn = get_db()
    conn.execute("INSERT INTO holdings (ticker, name, shares, manual_price) VALUES (?,?,?,?)",
                 (ticker, name, shares, manual_price))
    conn.commit()
    conn.close()
    return cors(make_response(jsonify({"success": True}), 201))


@app.route("/api/holdings/<int:hid>", methods=["DELETE", "OPTIONS"])
def delete_holding(hid):
    if request.method == "OPTIONS":
        return cors(make_response("", 200))
    conn = get_db()
    conn.execute("DELETE FROM holdings WHERE id = ?", (hid,))
    conn.commit()
    conn.close()
    return cors(make_response(jsonify({"success": True})))


# ── Ticker search ─────────────────────────────────────────────────────────────

@app.route("/api/search")
def search_ticker():
    q = request.args.get("q", "").strip()
    if not q:
        return cors(make_response(jsonify([]), 200))
    try:
        results = []
        for item in (yf.Search(q, max_results=8).quotes or []):
            results.append({
                "ticker": item.get("symbol", ""),
                "name": item.get("longname") or item.get("shortname") or "",
                "type": item.get("quoteType", ""),
            })
        return cors(make_response(jsonify(results)))
    except Exception as e:
        print(f"Search error: {e}")
        return cors(make_response(jsonify([]), 200))


# ── Chart data ────────────────────────────────────────────────────────────────

@app.route("/api/chart/<ticker>/<period>")
def chart_data(ticker, period):
    period_map = {
        '1D':  ('1d',  '30m'),
        '1W':  ('5d',  '1h'),
        '1M':  ('1mo', '1d'),
        '6M':  ('6mo', '1wk'),
        'YTD': ('ytd', '1wk'),
    }
    yf_period, interval = period_map.get(period, ('1mo', '1d'))
    try:
        hist = yf.Ticker(ticker).history(period=yf_period, interval=interval)
        if hist.empty:
            return cors(make_response(jsonify([]), 200))
        data = []
        for idx, row in hist.iterrows():
            if period == '1D':
                label = idx.strftime('%-I:%M')
            elif period in ('1W', '1M'):
                label = idx.strftime('%b %-d')
            else:
                label = idx.strftime('%b')
            data.append({"d": label, "n": round(float(row["Close"]), 4)})
        return cors(make_response(jsonify(data)))
    except Exception as e:
        print(f"Chart error for {ticker}/{period}: {e}")
        return cors(make_response(jsonify([]), 200))


# ── Cash ──────────────────────────────────────────────────────────────────────

@app.route("/api/cash", methods=["GET", "PUT", "OPTIONS"])
def cash():
    if request.method == "OPTIONS":
        return cors(make_response("", 200))
    conn = get_db()
    if request.method == "PUT":
        val = float(request.get_json().get("value", 0))
        conn.execute("UPDATE cash_balance SET value = ? WHERE id = 1", (val,))
        conn.commit()
    row = conn.execute("SELECT value FROM cash_balance WHERE id = 1").fetchone()
    conn.close()
    return cors(make_response(jsonify({"value": row["value"] if row else 0})))


# ── Expenses ──────────────────────────────────────────────────────────────────

@app.route("/api/expenses", methods=["GET", "OPTIONS"])
def get_expenses():
    if request.method == "OPTIONS":
        return cors(make_response("", 200))
    conn = get_db()
    rows = conn.execute("SELECT * FROM expenses ORDER BY created_at DESC").fetchall()
    conn.close()
    return cors(make_response(jsonify([dict(r) for r in rows])))


@app.route("/api/expenses", methods=["POST"])
def add_expense():
    data = request.get_json()
    name = (data.get("name") or "").strip()
    try:
        amount = float(data.get("amount", 0))
    except (ValueError, TypeError):
        amount = 0
    category = data.get("category", "Other")
    date_str = data.get("date_str", datetime.now().strftime("%b %-d"))
    if not name or amount <= 0:
        return cors(make_response(jsonify({"error": "Invalid"}), 400))
    conn = get_db()
    conn.execute("INSERT INTO expenses (name, amount, category, date_str) VALUES (?,?,?,?)",
                 (name, amount, category, date_str))
    conn.commit()
    conn.close()
    return cors(make_response(jsonify({"success": True}), 201))


@app.route("/api/expenses/<int:eid>", methods=["DELETE", "OPTIONS"])
def delete_expense(eid):
    if request.method == "OPTIONS":
        return cors(make_response("", 200))
    conn = get_db()
    conn.execute("DELETE FROM expenses WHERE id = ?", (eid,))
    conn.commit()
    conn.close()
    return cors(make_response(jsonify({"success": True})))


# ── Budget ────────────────────────────────────────────────────────────────────

@app.route("/api/budget", methods=["GET", "PUT", "OPTIONS"])
def budget():
    if request.method == "OPTIONS":
        return cors(make_response("", 200))
    conn = get_db()
    if request.method == "PUT":
        val = float(request.get_json().get("monthly_limit", 0))
        conn.execute("UPDATE budget SET monthly_limit = ? WHERE id = 1", (val,))
        conn.commit()
    row = conn.execute("SELECT monthly_limit FROM budget WHERE id = 1").fetchone()
    conn.close()
    return cors(make_response(jsonify({"monthly_limit": row["monthly_limit"] if row else 0})))


# ── Budget categories ─────────────────────────────────────────────────────────

@app.route("/api/categories", methods=["GET", "OPTIONS"])
def get_categories():
    if request.method == "OPTIONS":
        return cors(make_response("", 200))
    conn = get_db()
    rows = conn.execute("SELECT * FROM budget_categories ORDER BY id").fetchall()
    conn.close()
    return cors(make_response(jsonify([dict(r) for r in rows])))


@app.route("/api/categories", methods=["POST"])
def add_category():
    data = request.get_json()
    name = (data.get("name") or "").strip()
    try:
        limit = float(data.get("monthly_limit", 0))
    except (ValueError, TypeError):
        limit = 0
    color = data.get("color", "#e8254a")
    if not name or limit <= 0:
        return cors(make_response(jsonify({"error": "Invalid"}), 400))
    conn = get_db()
    conn.execute("INSERT INTO budget_categories (name, monthly_limit, color) VALUES (?,?,?)",
                 (name, limit, color))
    conn.commit()
    conn.close()
    return cors(make_response(jsonify({"success": True}), 201))


@app.route("/api/categories/<int:cid>", methods=["DELETE", "OPTIONS"])
def delete_category(cid):
    if request.method == "OPTIONS":
        return cors(make_response("", 200))
    conn = get_db()
    conn.execute("DELETE FROM budget_categories WHERE id = ?", (cid,))
    conn.commit()
    conn.close()
    return cors(make_response(jsonify({"success": True})))


# ── History ───────────────────────────────────────────────────────────────────

@app.route("/api/history")
def get_history():
    conn = get_db()
    rows = conn.execute('''
        SELECT DATE(recorded_at) AS date, ROUND(AVG(total_value),2) AS value
        FROM price_history
        WHERE recorded_at >= DATE('now', '-30 days')
        GROUP BY DATE(recorded_at) ORDER BY date ASC
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
