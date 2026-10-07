#!/usr/bin/env python3
"""検索結果のキーワードフィルタリング."""

from __future__ import annotations


def matches_all_keywords(product_name: str, search_keyword: str) -> bool:
    """検索キーワードの全断片が商品名に含まれているか判定.

    キーワードをスペースで分割し、全ての断片が商品名に含まれているかを
    大文字小文字を無視して判定する。

    Args:
        product_name: 商品名
        search_keyword: 検索キーワード（スペース区切り）

    Returns:
        全断片が含まれていれば True
    """
    fragments = search_keyword.split()
    if not fragments:
        return True
    name_lower = product_name.lower()
    return all(f.lower() in name_lower for f in fragments)


def has_excluded_keywords(product_name: str, exclude_keywords: list[str] | None) -> bool:
    """除外キーワードが商品名に含まれているか判定.

    除外キーワードのいずれかが商品名に含まれていれば True を返す。

    Args:
        product_name: 商品名
        exclude_keywords: 除外キーワードリスト

    Returns:
        除外キーワードが含まれていれば True
    """
    if not exclude_keywords:
        return False
    name_lower = product_name.lower()
    return any(keyword.lower() in name_lower for keyword in exclude_keywords)
