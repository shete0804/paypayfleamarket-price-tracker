#!/usr/bin/env python3
"""別の商品でシステムテスト."""

import sqlite3
from pathlib import Path

def test_extract_top3(keyword):
    """異なるキーワードで最安値TOP3抽出テスト."""

    db_path = Path(__file__).parent / 'run52_artifacts' / 'scraper-output' / 'data' / 'price' / 'price.db'

    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        return False

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # キーワードをスペース区切りで分割
        keywords = keyword.split()

        # WHERE句の構築
        where_parts = []
        for kw in keywords:
            where_parts.append(f"name LIKE '%{kw}%'")
        where_clause = " AND ".join(where_parts)

        # クエリ実行
        query = f"""
            SELECT price, name, url FROM price
            WHERE {where_clause}
            ORDER BY price ASC LIMIT 3
        """

        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            print(f"No items found for: {keyword}")
            return False

        print(f"=== 最安値TOP3: {keyword} ===\n")

        for i, (price, name, url) in enumerate(rows, 1):
            print(f"{i}位: ¥{price:,}")
            print(f"  名前: {name[:80]}")
            print(f"  URL: {url}")
            print()

        return True

    except sqlite3.Error as e:
        print(f"ERROR: {e}")
        return False


if __name__ == '__main__':
    # テスト1: リーリエの決心
    print("【テスト1】リーリエの決心\n")
    test_extract_top3("リーリエの決心")

    print("\n" + "="*80 + "\n")

    # テスト2: サンダーexの最安値
    print("【テスト2】サンダーex\n")
    test_extract_top3("サンダーex")
