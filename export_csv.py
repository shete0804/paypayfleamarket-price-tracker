#!/usr/bin/env python3
"""最新の上位3件（top3_history の最新分）を results/paypay.csv に書き出す.

スプレッドシートの IMPORTDATA で読むためのファイル。対象のカードを全部並べ、結果がないカードは「該当なし」。
"""

from __future__ import annotations

import csv
import pathlib
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

DB_PATH = pathlib.Path("./data/price/price.db")
OUT_PATH = pathlib.Path("./results/paypay.csv")
JST = timezone(timedelta(hours=9))

# メルカリ版と同じ名前で並べられるように、共通の短い名前に直す（同じカードを同じ行に並べるため）
LABELS = {
    "メガリザードンYex スタートデッキ100": "メガリザードンYex MUR",
    "メガリザードンXex SAR インフェルノX": "メガリザードンXex SAR",
    "ギラティナV SA ロストアビス": "ギラティナV SA",
    "メガレックウザex MUR ストームエメラルダ": "メガレックウザex MUR",
    "ピカチュウex スタートデッキ100": "ピカチュウex",
}


def main() -> int:
    if not DB_PATH.exists():
        print(f"DB が見つかりません: {DB_PATH}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(DB_PATH)
    try:
        items = conn.execute("SELECT id, name FROM items ORDER BY id").fetchall()
        rows = conn.execute(
            """
            SELECT t.item_id, t.rank, t.price, t.url, t.thumb_url
            FROM top3_history t
            WHERE t.time = (SELECT MAX(t2.time) FROM top3_history t2 WHERE t2.item_id = t.item_id)
            ORDER BY t.item_id, t.rank
            """
        ).fetchall()
    finally:
        conn.close()

    latest: dict[int, list[tuple[int, int, str, str]]] = {}
    for item_id, rank, price, url, thumb in rows:
        latest.setdefault(item_id, []).append((rank, price, url, thumb or ""))

    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["カード", "順位", "価格", "URL", "更新", "写真"])
        for item_id, name in items:
            label = LABELS.get(name, name)
            found = latest.get(item_id, [])
            if not found:
                writer.writerow([label, "", "該当なし", "", now, ""])
                continue
            for rank, price, url, thumb in found:
                writer.writerow([label, rank, price, url, now, thumb])

    print(f"書き出しました: {OUT_PATH}（{len(items)} カード）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
