#!/usr/bin/env python3
"""最新の検索結果（top3_history の最新分）を Discord に通知する.

対象のカードを全部並べる（結果がないカードは「該当なし」）。カードには管理番号（No.1, No.2…）を付ける。
環境変数 DISCORD_WEBHOOK_URL が無い場合は、送信せずに内容をログに出すだけにする。
"""

from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import sys
import urllib.request

DB_PATH = pathlib.Path("./data/price/price.db")
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()


def load_items_and_latest() -> list[tuple[str, list[tuple[int, int, str, str]]]]:
    """対象カードを items の順（管理番号の順）に並べ、各カードの最新の上位3件を返す."""
    conn = sqlite3.connect(DB_PATH)
    try:
        items = conn.execute("SELECT id, name FROM items ORDER BY id").fetchall()
        rows = conn.execute(
            """
            SELECT t.item_id, t.rank, t.price, t.name, t.url
            FROM top3_history t
            WHERE t.time = (SELECT MAX(t2.time) FROM top3_history t2 WHERE t2.item_id = t.item_id)
            ORDER BY t.item_id, t.rank
            """
        ).fetchall()
    finally:
        conn.close()

    latest: dict[int, list[tuple[int, int, str, str]]] = {}
    for item_id, rank, price, name, url in rows:
        latest.setdefault(item_id, []).append((rank, price, name, url))
    return [(name, latest.get(item_id, [])) for item_id, name in items]


def build_payload(cards: list[tuple[str, list[tuple[int, int, str, str]]]]) -> dict:
    """Discord の Embed を作る（カードごとに 1 フィールド、管理番号つき）。"""
    fields = []
    for number, (card, items) in enumerate(cards, 1):
        if items:
            lines = []
            for rank, price, name, url in items:
                short_name = name if len(name) <= 40 else name[:40] + "…"
                lines.append(f"{rank}. ¥{price:,} {short_name}\n{url}")
            value = "\n".join(lines)
        else:
            value = "該当なし"
        fields.append({"name": f"No.{number} {card}"[:250], "value": value[:1024], "inline": False})

    return {
        "embeds": [
            {
                "title": "PayPayフリマ 最安 TOP3",
                "description": "カードごとに、出品中で安い順の上位3件です。",
                "fields": fields[:25],
            }
        ]
    }


def main() -> int:
    if not DB_PATH.exists():
        print(f"DB が見つかりません: {DB_PATH}", file=sys.stderr)
        return 1

    payload = build_payload(load_items_and_latest())
    if not WEBHOOK_URL:
        print("DISCORD_WEBHOOK_URL 未設定のため送信しません。内容:")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    req = urllib.request.Request(
        WEBHOOK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "paypay-notify"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        print(f"Discord へ送信しました（HTTP {resp.status}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
