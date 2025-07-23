from flask import Flask, render_template, request, redirect, url_for, g
import sqlite3
from datetime import datetime
import calendar as cal
from collections import defaultdict
import io
import base64
import matplotlib
matplotlib.use('Agg') # バックエンドをAggに設定
import matplotlib.pyplot as plt
import os

app = Flask(__name__)

DB_NAME = "data.db"

# データベース接続を取得する関数
def get_db():
    if 'db' not in g: # g.db にデータベース接続がまだない場合
        g.db = sqlite3.connect(DB_NAME, timeout=5, check_same_thread=False)
        g.db.row_factory = sqlite3.Row
        # ★ここから追加
        g.db.execute('PRAGMA journal_mode=WAL')
        # ★ここまで追加
    return g.db

# リクエスト終了時にデータベース接続を閉じる関数
@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None) # g から 'db' を取り出す。なければNone

    if db is not None:
        db.close() # データベース接続を閉じる

# データベースの初期化関数
def init_db():
    with app.app_context(): # init_db自体もコンテキスト内で実行されるように
        with get_db() as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS kakeibo (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    type TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT
                )
            """)
            conn.commit()

@app.context_processor
def inject_calendar():
    return dict(calendar=cal)

@app.route("/", methods=["GET", "POST"])
def index():
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        return redirect("/")

    today = datetime.today()
    year = request.args.get("year", today.year, type=int)
    month = request.args.get("month", today.month, type=int)

    c.execute(
        "SELECT * FROM kakeibo WHERE strftime('%Y-%m', date)=? ORDER BY date",
        (f"{year}-{month:02d}",)
    )
    records = c.fetchall()

    calendar_data = defaultdict(lambda: {"income": 0, "expense": 0})
    for r in records:
        day = int(r["date"][-2:])
        if r["type"] == "収入":
            calendar_data[day]["income"] += r["amount"]
        else:
            calendar_data[day]["expense"] += r["amount"]

    c.execute(
        "SELECT SUM(amount) FROM kakeibo WHERE type='収入' AND strftime('%Y-%m', date)=?",
        (f"{year}-{month:02d}",)
    )
    monthly_income = c.fetchone()[0] or 0

    c.execute(
        "SELECT SUM(amount) FROM kakeibo WHERE type='支出' AND strftime('%Y-%m', date)=?",
        (f"{year}-{month:02d}",)
    )
    monthly_expense = c.fetchone()[0] or 0

    balance = monthly_income - monthly_expense

    first_day_of_month = datetime(year, month, 1)
    total_days = cal.monthrange(year, month)[1]
    first_weekday = first_day_of_month.weekday()
    if first_weekday == 6:
        first_weekday = 0
    else:
        first_weekday += 1

    calendar_days_list = []
    for _ in range(first_weekday):
        calendar_days_list.append(None)

    for day in range(1, total_days + 1):
        calendar_days_list.append({
            "day": day,
            "income": calendar_data[day]["income"],
            "expense": calendar_data[day]["expense"],
            "is_today": (day == today.day and month == today.month and year == today.year)
        })

    return render_template(
        "index.html",
        year=year,
        month=month,
        calendar_days_list=calendar_days_list,
        balance=balance,
        monthly_income=monthly_income,
        monthly_expense=monthly_expense,
        records=records,
        first_weekday=first_weekday,
        total_days=total_days,
        calendar_data=calendar_data
    )

@app.route("/input", methods=["GET", "POST"])
def input_data():
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        date = request.form["date"]
        amount = int(request.form["amount"])
        description = request.form.get("description", "")
        category = request.form["category"]
        type_ = request.form["type"]

        c.execute(
            "INSERT INTO kakeibo (date, amount, description, category, type) VALUES (?, ?, ?, ?, ?)",
            (date, amount, description, category, type_)
        )
        conn.commit()
        return redirect(url_for("index"))
    return render_template("input.html")

@app.route("/edit/<int:record_id>", methods=["GET", "POST"])
def edit_record(record_id):
    conn = get_db()
    c = conn.cursor()
    if request.method == "POST":
        date = request.form["date"]
        amount = int(request.form["amount"])
        description = request.form.get("description", "")
        category = request.form["category"]
        type_ = request.form["type"]

        c.execute(
            "UPDATE kakeibo SET date=?, amount=?, description=?, category=?, type=? WHERE id=?",
            (date, amount, description, category, type_, record_id)
        )
        conn.commit()
        return redirect(url_for("index"))
    else:
        c.execute("SELECT * FROM kakeibo WHERE id = ?", (record_id,))
        record = c.fetchone()
        if record is None:
            return "記録が見つかりません", 404
        return render_template("edit.html", record=record)

@app.route("/delete/<int:record_id>", methods=["POST"])
def delete_record(record_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM kakeibo WHERE id = ?", (record_id,))
    conn.commit()
    return redirect(url_for("index"))

@app.route("/graph", methods=["GET"])
def graph():
    today = datetime.today()
    year = int(request.args.get("year", today.year))
    month = int(request.args.get("month", today.month))

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT category, SUM(amount) FROM kakeibo WHERE type='支出' AND strftime('%Y-%m', date)=? GROUP BY category",
        (f"{year}-{month:02d}",)
    )
    category_data = c.fetchall()

    if not category_data:
        return render_template("graph.html", graph=None, year=year, month=month)

    categories = [row[0] for row in category_data]
    amounts = [row[1] for row in category_data]

    plt.figure(figsize=(10, 7))
    plt.pie(amounts, labels=categories, autopct='%1.1f%%', startangle=90, colors=plt.cm.Paired.colors)
    plt.title(f"{year}年{month}月 カテゴリ別支出")
    plt.axis('equal')

    img = io.BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)
    plt.close()
    graph_url = base64.b64encode(img.getvalue()).decode()

    return render_template("graph.html", graph=graph_url, year=year, month=month)

@app.route("/stats")
def stats():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT
            strftime('%Y-%m', date) AS year_month,
            SUM(CASE WHEN type = '支出' THEN amount ELSE 0 END) AS total_expense,
            SUM(CASE WHEN type = '収入' THEN amount ELSE 0 END) AS total_income,
            AVG(CASE WHEN type = '支出' THEN amount ELSE NULL END) AS avg_expense,
            AVG(CASE WHEN type = '収入' THEN amount ELSE NULL END) AS avg_income
        FROM kakeibo
        GROUP BY year_month
        ORDER BY year_month DESC
    """)
    monthly_stats = c.fetchall()

    stats_for_template = []
    for stat in monthly_stats:
        stats_for_template.append({
            "year_month": stat["year_month"],
            "total_expense": stat["total_expense"] if stat["total_expense"] is not None else 0,
            "total_income": stat["total_income"] if stat["total_income"] is not None else 0,
            "avg_expense": round(stat["avg_expense"], 2) if stat["avg_expense"] is not None else 0,
            "avg_income": round(stat["avg_income"], 2) if stat["avg_income"] is not None else 0,
        })

    return render_template("stats.html", stats=stats_for_template)

if __name__ == "__main__":
    with app.app_context():
        if not os.path.exists(DB_NAME):
            init_db()
        else:
            with get_db() as conn:
                c = conn.cursor()
                try:
                    c.execute("SELECT description FROM kakeibo LIMIT 1")
                except sqlite3.OperationalError:
                    c.execute("ALTER TABLE kakeibo ADD COLUMN description TEXT")
                    conn.commit()
    app.run(debug=True)