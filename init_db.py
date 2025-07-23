import sqlite3

conn = sqlite3.connect("data.db")
c = conn.cursor()

# テーブル作成
c.execute("""
CREATE TABLE IF NOT EXISTS kakeibo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,         -- 'income' または 'expense'
    amount INTEGER NOT NULL,    -- 金額
    category TEXT NOT NULL,     -- カテゴリ（例: 食費、交通など）
    date TEXT NOT NULL          -- 日付（YYYY-MM-DD）
)
""")

conn.commit()
conn.close()
print("✅ データベースが初期化されました。")
