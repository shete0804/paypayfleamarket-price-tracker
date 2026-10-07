#!/usr/bin/env python3
"""最安値TOP3抽出スクリプト.

指定された商品キーワードの最安値TOP3をデータベースから抽出します。
"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def extract_top3(
    db_path: str,
    keyword: str,
    exclude_keywords: Optional[str] = None,
    limit: int = 3
) -> list[dict]:
    """データベースから最安値TOP3を抽出.

    Args:
        db_path: データベースファイルパス
        keyword: 検索キーワード（すべての単語を含む）
        exclude_keywords: 除外キーワード（カンマ区切り）
        limit: 取得件数（デフォルト: 3）

    Returns:
        最安値TOP3の商品情報リスト
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # テーブル名を自動検出
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        logger.info(f"Available tables: {tables}")

        # 価格テーブルを探す（price, prices, price_history, etc.）
        price_table = None
        for table_name in ['price', 'prices', 'price_history', 'product_prices']:
            if table_name in tables:
                price_table = table_name
                break

        if not price_table:
            logger.error(f"No price table found. Available tables: {tables}")
            return []

        # キーワードをスペース区切りで分割
        keywords = keyword.split()

        # WHERE句の構築
        where_parts = []
        for kw in keywords:
            where_parts.append(f"name LIKE '%{kw}%'")
        where_clause = " AND ".join(where_parts)

        # 除外キーワードがあれば追加
        if exclude_keywords:
            for exclude_kw in exclude_keywords.split(','):
                exclude_kw = exclude_kw.strip()
                if exclude_kw:
                    where_clause += f" AND name NOT LIKE '%{exclude_kw}%'"

        # クエリ実行
        query = f"""
            SELECT price, name, url FROM {price_table}
            WHERE {where_clause}
            ORDER BY price ASC LIMIT {limit}
        """

        logger.info(f"Using table: {price_table}")
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()

        # 結果を辞書形式に変換
        results = []
        for i, (price, name, url) in enumerate(rows, 1):
            results.append({
                'rank': i,
                'price': price,
                'name': name,
                'url': url
            })

        return results

    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return []


def main():
    """メイン処理."""
    import argparse

    parser = argparse.ArgumentParser(description='最安値TOP3抽出スクリプト')
    parser.add_argument('--db-path', type=str, default='data/price/price.db',
                        help='データベースファイルパス')
    parser.add_argument('--keyword', type=str, default='メガルカリオex MUR メガブレイブ',
                        help='検索キーワード')
    parser.add_argument('--exclude', type=str, default='',
                        help='除外キーワード（カンマ区切り）')
    parser.add_argument('--limit', type=int, default=3,
                        help='取得件数')

    args = parser.parse_args()

    logger.info(f"Extracting top {args.limit} cheapest items for: {args.keyword}")
    results = extract_top3(args.db_path, args.keyword, args.exclude, args.limit)

    if results:
        for result in results:
            print(f"{result['rank']}位: ¥{result['price']:,} - {result['name'][:70]}")
            print(f"   URL: {result['url']}")
            print()
    else:
        logger.warning("No items found")


if __name__ == '__main__':
    main()
