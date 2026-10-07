#!/usr/bin/env python3
import sqlite3

db_path = "./run77_artifacts/scraper-output/data/price/price.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# テーブル確認
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("=== テーブル一覧 ===")
for table in tables:
    print(f"  {table[0]}")

# TOP3 取得
print("\n=== TOP3 最安値商品 ===\n")
cursor.execute("""
    SELECT price, name, url FROM price_history
    WHERE name LIKE '%メガルカリオex%'
    AND name LIKE '%MUR%'
    AND name LIKE '%メガブレイブ%'
    ORDER BY price ASC LIMIT 3
""")

results = cursor.fetchall()
for rank, (price, name, url) in enumerate(results, 1):
    print(f"{rank}位: ¥{price:,}")
    print(f"名前: {name}")
    print(f"URL: {url}")
    print()

conn.close()
