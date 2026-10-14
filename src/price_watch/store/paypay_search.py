#!/usr/bin/env python3
"""PayPayフリマ検索（安い順固定・複数除外対応）."""

from __future__ import annotations

import contextlib
import logging
import re
import time
import urllib.parse

import my_lib.browser
import my_lib.store.flea_market
from my_lib.browser import Xpath
from my_lib.browser.protocol import Element, Page

_CONDITION_PARAM_MAP: dict[my_lib.store.flea_market.ItemCondition, str] = {
    my_lib.store.flea_market.ItemCondition.NEW: "NEW",
    my_lib.store.flea_market.ItemCondition.LIKE_NEW: "USED10",
    my_lib.store.flea_market.ItemCondition.GOOD: "USED20",
    my_lib.store.flea_market.ItemCondition.FAIR: "USED40",
    my_lib.store.flea_market.ItemCondition.POOR: "USED60",
    my_lib.store.flea_market.ItemCondition.BAD: "USED60",
}

_SEARCH_BASE_URL: str = "https://paypayfleamarket.yahoo.co.jp/search"
_ITEM_LIST_XPATH: str = '//div[@id="itm"]//a[contains(@href, "/item/")]'
_NO_RESULT_XPATH: str = '//p[contains(., "見つかりませんでした")] | //p[contains(., "0件")]'
_NEAR_MATCH_NOTICE_XPATH: str = '//p[contains(., "一致する商品が見つからなかったため")]'


def split_exclude_keywords(exclude_keyword: str | None) -> list[str]:
    """除外キーワード（カンマ区切り）を語のリストにする."""
    if not exclude_keyword:
        return []
    return [kw.strip() for kw in exclude_keyword.split(",") if kw.strip()]


def build_search_url(condition: my_lib.store.flea_market.SearchCondition) -> str:
    """検索条件から安い順の検索URLを生成する."""
    keyword = condition.keyword
    # 除外語は検索URLに入れない（PayPayは説明文の言葉でも外すため、正しい出品まで消える）。除外は取得後に商品名だけで判定する

    url = f"{_SEARCH_BASE_URL}/{urllib.parse.quote(keyword)}"

    params: dict[str, str] = {"sort": "price", "order": "asc", "withSpeller": "0"}

    if condition.sale_status == my_lib.store.flea_market.SaleStatus.ON_SALE:
        params["open"] = "1"
    elif condition.sale_status == my_lib.store.flea_market.SaleStatus.SOLD_OUT:
        params["sold"] = "1"

    if condition.price_min is not None:
        params["minPrice"] = str(condition.price_min)

    if condition.price_max is not None:
        params["maxPrice"] = str(condition.price_max)

    query = "&".join(f"{urllib.parse.quote(k)}={urllib.parse.quote(v)}" for k, v in params.items())
    return f"{url}?{query}"


def _wait_for_search_results(page: Page) -> bool:
    try:
        page.wait_visible(Xpath("//main | //div[@id='root']//ul"))
    except my_lib.browser.WaitTimeoutError:
        logging.warning("[PayPay] 読み込みタイムアウト")
        raise

    time.sleep(2)

    if page.exists(Xpath(_NO_RESULT_XPATH), visible=False):
        logging.info("[PayPay] 該当なし")
        return False

    if page.exists(Xpath(_NEAR_MATCH_NOTICE_XPATH), visible=False):
        logging.info("[PayPay] 該当なし（一致する商品が無く、近い商品のみ表示）")
        return False

    return True


def _parse_search_item(item_element: Element) -> my_lib.store.flea_market.SearchResult | None:
    try:
        url_raw = item_element.attr("href")
        if url_raw is None:
            return None
        url = f"https://paypayfleamarket.yahoo.co.jp{url_raw}" if url_raw.startswith("/") else url_raw

        title: str | None = None
        thumb_url: str | None = None

        for img in item_element.find_all(Xpath(".//img[@alt]")):
            alt = img.attr("alt")
            if alt and alt.strip():
                title = alt.strip()
                src = img.attr("src")
                if src and not src.startswith("data:"):
                    thumb_url = f"https://paypayfleamarket.yahoo.co.jp{src}" if src.startswith("/") else src
                break

        if not title:
            all_text = item_element.text
            if all_text:
                for line in (line.strip() for line in all_text.strip().split("\n")):
                    if line and not re.match(r"^[\d,]+円$", line) and line != "いいね！":
                        title = line
                        break

        if not thumb_url:
            for img in item_element.find_all(Xpath(".//img[@src]")):
                src = img.attr("src")
                if src and not src.startswith("data:"):
                    thumb_url = f"https://paypayfleamarket.yahoo.co.jp{src}" if src.startswith("/") else src
                    break

        price: int | None = None
        for p_elem in item_element.find_all(Xpath(".//p")):
            p_text = p_elem.text
            if p_text:
                price_match = re.match(r"^([\d,]+)円$", p_text.strip())
                if price_match:
                    with contextlib.suppress(ValueError):
                        price = int(price_match.group(1).replace(",", ""))
                    break

        if price is None:
            price_match = re.search(r"([\d,]+)円", item_element.text or "")
            if price_match:
                with contextlib.suppress(ValueError):
                    price = int(price_match.group(1).replace(",", ""))

        if not title or price is None:
            return None

        return my_lib.store.flea_market.SearchResult(name=title, url=url, price=price, thumb_url=thumb_url)

    except Exception:
        logging.exception("[PayPay] パース失敗")
        return None


def search(
    page: Page,
    condition: my_lib.store.flea_market.SearchCondition,
    max_items: int | None = None,
    scroll_to_load: bool = False,
) -> list[my_lib.store.flea_market.SearchResult]:
    """PayPayフリマを安い順で検索する."""
    url = build_search_url(condition)
    logging.info("[PayPay] 検索開始: keyword=%s", condition.keyword)
    logging.debug("[PayPay] 検索URL: %s", url)

    page.goto(url)
    logging.info("[PayPay] 到着URL: %s", page.url)

    if not _wait_for_search_results(page):
        return []

    results: list[my_lib.store.flea_market.SearchResult] = []
    parsed_urls: set[str] = set()

    # 下にスクロールすると続きが読み込まれるが、1回増えなかっただけでは止めない（最大3回まで再試行）
    item_elements = page.find_all(Xpath(_ITEM_LIST_XPATH))
    stalled_count = 0
    while item_elements and len(item_elements) < (max_items or 1000) and stalled_count < 6:
        previous_count = len(item_elements)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        item_elements[-1].scroll_into_view()
        time.sleep(2)
        item_elements = page.find_all(Xpath(_ITEM_LIST_XPATH))
        stalled_count = stalled_count + 1 if len(item_elements) == previous_count else 0
    logging.info("[PayPay] 画面上の商品リンク数: %d", len(item_elements))
    body = page.find(Xpath("//body"))
    body_text = (body.text if body else "") or ""
    logging.info("[PayPay] 本文の冒頭: %s", body_text[:400].replace("\n", " / "))
    count_match = re.search(r"[\d,~〜]+件/[\d,]+件", body_text)
    logging.info("[PayPay] 件数表示: %s", count_match.group(0) if count_match else "見つからない")

    for i, item_element in enumerate(item_elements):
        if max_items is not None and len(results) >= max_items:
            break

        if scroll_to_load or i < 20:
            try:
                item_element.scroll_into_view()
                if i >= 20:
                    time.sleep(0.3)
            except Exception:
                logging.debug("[PayPay] 要素 %d のスクロールに失敗、スキップ", i + 1)
                continue

        result = _parse_search_item(item_element)
        if result is None:
            logging.info("[PayPay] 解析失敗 %d: %s", i + 1, (item_element.text or "")[:60].replace("\n", " "))
        if result is not None and result.url not in parsed_urls:
            results.append(result)
            parsed_urls.add(result.url)

    logging.info("[PayPay] 検索完了: %d 件", len(results))
    logging.info("[PayPay] 取得順の価格: %s", [r.price for r in results])
    return results
