#!/usr/bin/env python3
import sqlite3
import os

db_path = "data/price/price.db"

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # リーリエの決心 SAR の最安値TOP3を取得
    cursor.execute("""
        SELECT
            p.price,
            i.name,
            i.url
        FROM price_history p
        JOIN items i ON p.item_id = i.id
        WHERE i.name LIKE '%リーリエ%' AND i.name LIKE '%決心%' AND i.name LIKE '%SAR%'
        ORDER BY p.price ASC
        LIMIT 3;
    """)

    results = cursor.fetchall()
    if results:
        print("=== TOP3 最安値（リーリエの決心 SAR メガブレイブ） ===\n")
        for rank, (price, name, url) in enumerate(results, 1):
            print(f"{rank}位: ¥{price:,}")
            print(f"名前: {name[:70]}")
            print(f"URL: {url}")
            print()
    else:
        print("No results found for リーリエの決心 SAR")

    conn.close()
else:
    print(f"Database not found at {db_path}")
