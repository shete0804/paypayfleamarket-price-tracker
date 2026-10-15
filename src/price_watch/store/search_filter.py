#!/usr/bin/env python3
"""検索結果のキーワードフィルタリング."""

from __future__ import annotations

import re


def normalize_name(text: str) -> str:
    """商品名の比較用に、空白を取り、小文字にする（「X ex」「Xex」「X EX」を同じものとして扱う）."""
    return re.sub(r"\s+", "", text).lower()


def matches_all_keywords(product_name: str, search_keyword: str) -> bool:
    """検索キーワードの全断片が商品名に含まれているか判定.

    キーワードをスペースで分割し、全ての断片が商品名に含まれているかを判定する。
    空白と大文字小文字は無視する。

    Args:
        product_name: 商品名
        search_keyword: 検索キーワード（スペース区切り）

    Returns:
        全断片が含まれていれば True
    """
    fragments = search_keyword.split()
    if not fragments:
        return True
    name_norm = normalize_name(product_name)
    return all(normalize_name(f) in name_norm for f in fragments)
