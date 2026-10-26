#!/usr/bin/env python3
"""競合したときに、PayPay の CSV を書き直す。

使い方: python merge_paypay_csv.py <対象ファイル> <自分の結果> <取り込み先の結果>

- 対象ファイル（target_g1.yaml など）に書いてあるカードの行は、自分の結果で置き換える。
- それ以外のカードの行は、取り込み先（相手の変更）のまま残す。
"""

from __future__ import annotations

import csv
import pathlib
import sys

from export_csv import group_labels


def main() -> int:
    target, ours_path, upstream_path = sys.argv[1], sys.argv[2], sys.argv[3]
    labels = group_labels(pathlib.Path(target))

    with open(ours_path, newline="", encoding="utf-8") as f:
        ours = list(csv.reader(f))
    with open(upstream_path, newline="", encoding="utf-8") as f:
        upstream = list(csv.reader(f))

    header = ours[0] if ours else ["カード", "順位", "価格", "URL", "更新", "写真"]
    ours_rows = [r for r in ours[1:] if r and r[0] in labels]
    upstream_rows = [r for r in upstream[1:] if r and r[0] not in labels]

    with open(upstream_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(upstream_rows + ours_rows)

    print(f"書き直しました: 自分の行 {len(ours_rows)} 件 / 取り込んだ行 {len(upstream_rows)} 件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
