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


def group_labels(target_path: pathlib.Path) -> set[str]:
    """対象ファイル（target_g1.yaml など）に書いてあるカード名を、CSV の表示名にそろえて返す。"""
    names = set()
    for line in target_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("    - name: "):
            name = line[len("    - name: "):].strip()
            if name != "PayPayフリマ":
                names.add(LABELS.get(name, name))
    return names


def read_old_rows() -> list[list[str]]:
    """前回の CSV の行（ヘッダーを除く）。他のグループの行を残すために使う。"""
    if not OUT_PATH.exists():
        return []
    with OUT_PATH.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    return rows[1:]


def main() -> int:
    if not DB_PATH.exists():
        print(f"DB が見つかりません: {DB_PATH}", file=sys.stderr)
        return 1

    # 引数に対象ファイルを渡すと、そのグループのカードだけ書き換え、他は前回の行を残す
    target_arg = sys.argv[1] if len(sys.argv) > 1 else None
    only = group_labels(pathlib.Path(target_arg)) if target_arg else None

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
    old_rows = read_old_rows()
    new_rows: list[list[str]] = []
    for item_id, name in items:
        label = LABELS.get(name, name)
        if only is not None and label not in only:
            continue
        found = latest.get(item_id, [])
        if not found:
            new_rows.append([label, "", "該当なし", "", now, ""])
            continue
        for rank, price, url, thumb in found:
            new_rows.append([label, str(rank), str(price), url, now, thumb])

    if only is None:
        out_rows = new_rows
    else:
        # 他のグループの行は、前回のまま残す
        kept = [r for r in old_rows if r and r[0] not in only]
        out_rows = kept + new_rows

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["カード", "順位", "価格", "URL", "更新", "写真"])
        writer.writerows(out_rows)

    print(f"書き出しました: {OUT_PATH}（{len(out_rows)} 行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
