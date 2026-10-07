#!/usr/bin/env python3
import sqlite3
import os

db_path = "run_latest_artifacts/scraper-output/data/price/price.db"

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            p.price,
            i.name,
            i.url
        FROM price_history p
        JOIN items i ON p.item_id = i.id
        WHERE i.name LIKE '%メガルカリオ%' AND i.name LIKE '%MUR%' AND i.name LIKE '%メガブレイブ%'
        ORDER BY p.price ASC
        LIMIT 3;
    """)

    results = cursor.fetchall()
    if results:
        print("=== TOP3 最安値（メガルカリオex MUR メガブレイブ） ===\n")
        for rank, (price, name, url) in enumerate(results, 1):
            print(f"{rank}位: ¥{price:,}")
            print(f"名前: {name[:70]}")
            print(f"URL: {url}")
            print()
    else:
        print("❌ No results found for メガルカリオex MUR メガブレイブ")

    conn.close()
else:
    print(f"Database not found at {db_path}")
