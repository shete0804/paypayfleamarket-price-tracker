"""Stop フック: docs/todo.md の「未了」に（ユーザー）以外の未チェック項目が残っていたら、停止を止めて続行させる。

- 未了にある `- [ ]` のうち、行に「(ユーザー)」「（ユーザー）」を含むものは無視（ユーザーにしか決められない項目）。
- 連続でブロックできる回数に上限（無限ループ防止）。上限に達したら通す。
"""
import json
import re
import sys
import tempfile
from pathlib import Path

TODO = Path(r"C:\Users\dobap\paypayfleamarket-price-tracker\docs\todo.md")
MAX_BLOCKS = 15


def open_items(text: str) -> list[str]:
    # ファイル全体の未チェック項目を拾う（「済」節に置いた未チェックも漏らさない）
    out = [
        ln.strip()
        for ln in text.splitlines()
        if re.match(r"\s*- \[ \]", ln) and not re.search(r"[(（]ユーザー[)）]", ln)
    ]
    return out


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        data = {}
    sid = str(data.get("session_id", "x"))
    counter = Path(tempfile.gettempdir()) / f"stop_guard_{sid}.txt"
    try:
        items = open_items(TODO.read_text(encoding="utf-8"))
    except Exception:
        return 0
    if not items:
        counter.unlink(missing_ok=True)
        return 0
    n = int(counter.read_text()) if counter.exists() else 0
    if n >= MAX_BLOCKS:
        return 0
    counter.write_text(str(n + 1))
    reason = (
        "docs/todo.md に未了が残っています。返信せず、次の項目を実行してください"
        "（待ちが必要なら run_in_background で待ち、その間に別項目を進める）。\n"
        + "\n".join(items[:5])
    )
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
