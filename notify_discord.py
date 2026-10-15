#!/usr/bin/env python3
"""最新の検索結果（top3_history の最新分）を Discord に通知する.

カードごとに、安い順の上位 3 件（値段・商品名・URL）を 1 通の Embed にまとめて送る。
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


def load_latest_top3() -> dict[str, list[tuple[int, int, str, str]]]:
    """カード名ごとに、最新の上位3件を返す。値は (順位, 値段, 商品名, URL)."""
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            """
            SELECT i.name, t.rank, t.price, t.name, t.url
            FROM top3_history t
            JOIN items i ON i.id = t.item_id
            WHERE t.time = (SELECT MAX(t2.time) FROM top3_history t2 WHERE t2.item_id = t.item_id)
            ORDER BY i.name, t.rank
            """
        ).fetchall()
    finally:
        conn.close()

    result: dict[str, list[tuple[int, int, str, str]]] = {}
    for card, rank, price, name, url in rows:
        result.setdefault(card, []).append((rank, price, name, url))
    return result


def build_payload(result: dict[str, list[tuple[int, int, str, str]]]) -> dict:
    """Discord の Embed を作る（カードごとに 1 フィールド）。"""
    fields = []
    for card, items in result.items():
        lines = []
        for rank, price, name, url in items:
            short_name = name if len(name) <= 40 else name[:40] + "…"
            lines.append(f"{rank}. ¥{price:,} {short_name}\n{url}")
        fields.append({"name": card[:250], "value": "\n".join(lines)[:1024] or "該当なし", "inline": False})

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

    payload = build_payload(load_latest_top3())
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
