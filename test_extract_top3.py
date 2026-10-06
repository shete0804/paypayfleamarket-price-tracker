#!/usr/bin/env python3
"""extract_top3スクリプトのテスト実行."""

import sys
import sqlite3
from pathlib import Path

def extract_top3_test():
    """データベースから最安値TOP3を抽出してテスト実行."""

    db_path = Path(__file__).parent / 'run52_artifacts' / 'scraper-output' / 'data' / 'price' / 'price.db'

    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        return False

    print(f"Using database: {db_path}")
    print()

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # メガルカリオex MUR メガブレイブ の商品を価格でソート
        query = """
            SELECT price, name, url FROM price
            WHERE name LIKE '%メガルカリオex%' AND name LIKE '%MUR%' AND name LIKE '%メガブレイブ%'
            ORDER BY price ASC LIMIT 3
        """

        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            print("WARNING: No items found matching the criteria")
            return False

        print(f"=== 最安値TOP3: メガルカリオex MUR メガブレイブ ===\n")

        for i, (price, name, url) in enumerate(rows, 1):
            print(f"{i}位: ¥{price:,}")
            print(f"  名前: {name[:80]}")
            print(f"  URL: {url}")
            print()

        return True

    except sqlite3.Error as e:
        print(f"ERROR: Database error: {e}")
        return False


if __name__ == '__main__':
    success = extract_top3_test()
    sys.exit(0 if success else 1)
