#!/usr/bin/env python3
"""フリマ検索（メルカリ・ラクマ・PayPayフリマ）による価格チェック."""

from __future__ import annotations

import dataclasses
import json
import logging
import re
from typing import TYPE_CHECKING, Any

import my_lib.store.flea_market
import my_lib.store.mercari.search
import my_lib.store.paypay.search
import my_lib.store.rakuma.search

import price_watch.affiliate
import price_watch.history
import price_watch.models
import price_watch.store.paypay_search
import price_watch.store.search_filter
import price_watch.target

if TYPE_CHECKING:
    from collections.abc import Callable

    from my_lib.browser import Page

    from price_watch.config import AppConfig
    from price_watch.target import ResolvedItem

# 検索結果の最大取得件数
MAX_SEARCH_RESULTS = 40
# 2つ目以降の検索語で読む件数（SA と HR の別々の検索を、どちらも同じ件数で読むため 40 件）
NAME_ONLY_SEARCH_RESULTS = 40
# 新着順の検索の件数（新しく出た出品を取りこぼさないため）
NEW_ARRIVAL_RESULTS = 10

# ストアごとの検索関数とログ表示名
_STORE_SEARCH_FUNCS: dict[
    price_watch.target.CheckMethod,
    tuple[
        Callable[..., list[my_lib.store.flea_market.SearchResult]],
        str,
    ],
] = {
    price_watch.target.CheckMethod.MERCARI_SEARCH: (my_lib.store.mercari.search.search, "メルカリ検索"),
    price_watch.target.CheckMethod.RAKUMA_SEARCH: (my_lib.store.rakuma.search.search, "ラクマ検索"),
    price_watch.target.CheckMethod.PAYPAY_SEARCH: (price_watch.store.paypay_search.search, "PayPay検索"),
}

# ストアごとのウォームアップ関数
_STORE_WARMUP_FUNCS: dict[
    price_watch.target.CheckMethod,
    Callable[..., bool],
] = {
    price_watch.target.CheckMethod.MERCARI_SEARCH: my_lib.store.mercari.search.warmup,
    price_watch.target.CheckMethod.RAKUMA_SEARCH: my_lib.store.rakuma.search.warmup,
    price_watch.target.CheckMethod.PAYPAY_SEARCH: my_lib.store.paypay.search.warmup,
}


def warmup(
    page: Page,
    check_method: price_watch.target.CheckMethod,
) -> bool:
    """指定されたフリマストアのウォームアップを実行.

    Google検索経由でフリマサイトにアクセスし、bot検出を回避する。

    Args:
        page: ブラウザページ
        check_method: チェックメソッド（フリマストア種別）

    Returns:
        ウォームアップが成功した場合 True
    """
    warmup_func = _STORE_WARMUP_FUNCS.get(check_method)
    if warmup_func is None:
        logging.warning("ウォームアップ関数が見つかりません: %s", check_method)
        return False

    return warmup_func(page)


def _parse_cond(cond_str: str | None) -> list[my_lib.store.flea_market.ItemCondition] | None:
    """商品状態文字列をパース.

    "NEW|LIKE_NEW" 形式から ItemCondition のリストに変換。

    Args:
        cond_str: 商品状態文字列（"NEW|LIKE_NEW" 形式）

    Returns:
        ItemCondition のリスト、または None
    """
    if not cond_str:
        return [
            my_lib.store.flea_market.ItemCondition.NEW,
            my_lib.store.flea_market.ItemCondition.LIKE_NEW,
        ]

    cond_map = {
        "NEW": my_lib.store.flea_market.ItemCondition.NEW,
        "LIKE_NEW": my_lib.store.flea_market.ItemCondition.LIKE_NEW,
        "GOOD": my_lib.store.flea_market.ItemCondition.GOOD,
        "FAIR": my_lib.store.flea_market.ItemCondition.FAIR,
        "POOR": my_lib.store.flea_market.ItemCondition.POOR,
        "BAD": my_lib.store.flea_market.ItemCondition.BAD,
    }

    result = []
    for cond_name in cond_str.split("|"):
        cond_name = cond_name.strip().upper()
        if cond_name in cond_map:
            result.append(cond_map[cond_name])
        else:
            logging.warning("Unknown condition: %s", cond_name)

    return result if result else None


def _build_search_condition(item: ResolvedItem) -> my_lib.store.flea_market.SearchCondition:
    """アイテム情報から検索条件を構築.

    Args:
        item: 監視対象アイテム

    Returns:
        SearchCondition
    """
    # キーワード: search_keyword がなければ name を使用
    keyword = item.search_keyword or item.name

    # 価格範囲
    price_min = None
    price_max = None
    if item.price_range:
        if len(item.price_range) >= 1:
            price_min = item.price_range[0]
        if len(item.price_range) >= 2:
            price_max = item.price_range[1]

    # 商品状態
    conditions = _parse_cond(item.cond)

    return my_lib.store.flea_market.SearchCondition(
        keyword=keyword,
        exclude_keyword=item.exclude_keyword,
        price_min=price_min,
        price_max=price_max,
        condition=conditions,
    )


def _build_search_cond_json(condition: my_lib.store.flea_market.SearchCondition) -> str:
    """検索条件を JSON 文字列に変換（item_key 生成用）.

    Args:
        condition: 検索条件

    Returns:
        JSON 文字列
    """
    data: dict[str, Any] = {}

    if condition.exclude_keyword:
        data["exclude"] = condition.exclude_keyword
    if condition.price_min is not None:
        data["price_min"] = condition.price_min
    if condition.price_max is not None:
        data["price_max"] = condition.price_max
    if condition.condition:
        data["cond"] = [c.value for c in condition.condition]

    return json.dumps(data, sort_keys=True, ensure_ascii=False) if data else ""


def _required_ok(name: str, req: str) -> bool:
    """必須の言葉が名前にあるか。「R/RGB」などの色の指定は、色の文字（単独）と RGB の両方があれば合格（順番は問わない）。"""
    m = re.fullmatch(r"([A-Za-z])/RGB", req)
    if m:
        letter = m.group(1)
        has_letter = re.search(rf"(?<![A-Za-z]){letter}(?![A-Za-z])", name, re.IGNORECASE) is not None
        return has_letter and re.search(r"RGB", name, re.IGNORECASE) is not None
    return price_watch.store.search_filter.normalize_name(req) in price_watch.store.search_filter.normalize_name(name)


def _is_recent_listing(text: str, days: int = 30) -> bool:
    """商品ページの文から、最終更新が直近 days 日以内かを判定する（「◯日前に更新」「出品日時」）。"""
    import datetime as _dt
    import re as _re

    if _re.search(r"\d+\s*(時間|分)前に更新", text):
        return True
    m = _re.search(r"(\d+)\s*日前に更新", text)
    if m:
        return int(m.group(1)) <= days
    if _re.search(r"\d+\s*(か月|ヶ月)前に更新", text):
        return False
    m = _re.search(r"出品日時[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    if m:
        jst = _dt.timezone(_dt.timedelta(hours=9))
        listed = _dt.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=jst)
        return listed >= _dt.datetime.now(jst) - _dt.timedelta(days=days)
    return False


def _get_store_label(item: ResolvedItem) -> str:
    """ストアのログ表示名を取得."""
    entry = _STORE_SEARCH_FUNCS.get(item.check_method)
    if entry is not None:
        return entry[1]
    return "フリマ検索"


def check(
    config: AppConfig,
    page: Page,
    item: ResolvedItem,
) -> price_watch.models.CheckedItem:
    """フリマ検索で最安値商品を取得.

    Args:
        config: アプリケーション設定
        page: ブラウザページ
        item: 監視対象アイテム

    Returns:
        チェック結果（CheckedItem）
    """
    label = _get_store_label(item)

    # 結果を格納する CheckedItem を作成
    result = price_watch.models.CheckedItem.from_resolved_item(item)

    # 検索条件を構築
    condition = _build_search_condition(item)

    logging.info("[%s] %s: キーワード='%s'", label, item.name, condition.keyword)

    # 検索関数を取得
    entry = _STORE_SEARCH_FUNCS.get(item.check_method)
    if entry is None:
        logging.error("[%s] %s: 未対応のチェックメソッド: %s", label, item.name, item.check_method)
        result.crawl_status = price_watch.models.CrawlStatus.FAILURE
        return result

    search_func = entry[0]

    # 検索実行
    # 検索語を「|」で区切ると、それぞれの検索語で検索して結果をまとめる（例：「ミュウVMAX SA|ミュウVMAX 119/100」）
    # 20件以上取得する場合は scroll_to_load=True
    scroll_to_load = MAX_SEARCH_RESULTS > 20
    keywords = [kw.strip() for kw in condition.keyword.split("|") if kw.strip()]
    results = []
    seen_urls: set[str] = set()
    # 「X HR」の検索で取れた出品は、SA の表記がなくても残す（SA の判定から外す）
    hr_urls: set[str] = set()
    # 1つ目の検索語（名前＋レア度）は MAX_SEARCH_RESULTS 件。2つ目以降（名前だけ）は NAME_ONLY_SEARCH_RESULTS 件で、
    # 「下限B:○○」があれば、その値段以上だけを検索する（検索の時点で偽物の安い商品を外す）
    name_only_floors = [int(t[len("下限B:") :]) for t in condition.exclude_keyword.split(",") if t.startswith("下限B:")] if condition.exclude_keyword else []
    # 「下限C:」は2つ目の検索語だけに付ける（ミュウは1つ目は下限なし、2つ目は色ごとの下限）
    extra_floors = [int(t[len("下限C:") :]) for t in condition.exclude_keyword.split(",") if t.startswith("下限C:")] if condition.exclude_keyword else []
    # 「下限A:○○」は1つ目の検索語（名前＋レア度）の下限（買取の5割など）。なければ下限Bを使う
    first_floors = [int(t[len("下限A:") :]) for t in condition.exclude_keyword.split(",") if t.startswith("下限A:")] if condition.exclude_keyword else []
    first_price_min = max(first_floors) if first_floors else max(name_only_floors, default=condition.price_min)
    for index, kw in enumerate(keywords):
        if index == 0:
            kw_condition = dataclasses.replace(
                condition, keyword=kw, price_min=first_price_min
            )
            kw_max = MAX_SEARCH_RESULTS
        else:
            kw_condition = dataclasses.replace(
                condition, keyword=kw, price_min=max(name_only_floors + extra_floors, default=condition.price_min)
            )
            kw_max = NAME_ONLY_SEARCH_RESULTS
        kw_results = search_func(
            page,
            kw_condition,
            max_items=kw_max,
            scroll_to_load=scroll_to_load,
        )
        logging.info("[%s] %s: 検索語「%s」で %d 件取得", label, item.name, kw, len(kw_results))
        for r in kw_results:
            # 検索語ごとに、その検索語の言葉が名前にあるものだけを採用する（別の検索語の混入を防ぐ）
            if price_watch.store.search_filter.matches_all_keywords(r.name, kw) and r.url not in seen_urls:
                seen_urls.add(r.url)
                results.append(r)
                if kw.upper().endswith(" HR"):
                    hr_urls.add(r.url)

    # 新着順の検索（新しく出た出品を取りこぼさないため、NEW_ARRIVAL_RESULTS 件）
    if keywords:
        new_condition = dataclasses.replace(
            condition,
            keyword=keywords[0],
            exclude_keyword=",".join(filter(None, [condition.exclude_keyword, "新着:1"])),
            price_min=first_price_min,
        )
        new_results = search_func(page, new_condition, max_items=NEW_ARRIVAL_RESULTS, scroll_to_load=False)
        logging.info("[%s] %s: 新着順の検索で %d 件取得", label, item.name, len(new_results))
        for r in new_results:
            if price_watch.store.search_filter.matches_all_keywords(r.name, keywords[0]) and r.url not in seen_urls:
                seen_urls.add(r.url)
                results.append(r)

    # item_key 生成用のデータを設定
    result.search_keyword = condition.keyword
    result.search_cond = _build_search_cond_json(condition)

    if not results:
        logging.info("[%s] %s: 検索結果なし", label, item.name)
        result.stock = price_watch.models.StockStatus.OUT_OF_STOCK
        result.crawl_status = price_watch.models.CrawlStatus.SUCCESS
        return result

    # 価格範囲でフィルタリング（ページに表示する「関連商品」等を除外）
    filtered_results = results
    if condition.price_min is not None or condition.price_max is not None:
        original_count = len(results)
        filtered_results = [
            r
            for r in results
            if (condition.price_min is None or r.price >= condition.price_min)
            and (condition.price_max is None or r.price <= condition.price_max)
        ]
        if len(filtered_results) < original_count:
            logging.info(
                "[%s] %s: 価格範囲外の商品を除外 (%d件 -> %d件)",
                label,
                item.name,
                original_count,
                len(filtered_results),
            )

    # 検索で取れた全商品をログに出す（後から手で照合できるように）
    logging.info("[%s] %s: 検索で取れた全商品 %d 件", label, item.name, len(filtered_results))
    for raw in filtered_results:
        logging.info("[%s] %s: 全商品 ¥%s | %s", label, item.name, f"{raw.price:,}", raw.name[:60])

    # キーワード全断片一致フィルタ
    before_keyword_filter = len(filtered_results)
    filtered_results = [
        r
        for r in filtered_results
        if any(price_watch.store.search_filter.matches_all_keywords(r.name, kw) for kw in keywords)
    ]
    if len(filtered_results) < before_keyword_filter:
        logging.info(
            "[%s] %s: キーワード不一致の商品を除外 (%d件 -> %d件)",
            label,
            item.name,
            before_keyword_filter,
            len(filtered_results),
        )

    exclude_terms = price_watch.store.paypay_search.split_exclude_keywords(condition.exclude_keyword)

    # 「説明:SAR」の指定：名前にレア度がない出品は、商品ページの説明文に SAR と書いてあるかを確かめて、あれば合格にする
    # 「必須:○○」：商品名に ○○ が含まれるものだけを残す（スクレイプでは通して、ここで落とす二次フィルター）
    required_terms = [t[len("必須:") :] for t in exclude_terms if t.startswith("必須:")]
    exclude_terms = [t for t in exclude_terms if not t.startswith("必須:")]
    if required_terms:
        before_required = len(filtered_results)
        filtered_results = [r for r in filtered_results if all(_required_ok(r.name, req) for req in required_terms)]
        if len(filtered_results) < before_required:
            logging.info(
                "[%s] %s: 必須の言葉（%s）がない商品を除外 (%d件 -> %d件)",
                label,
                item.name,
                ", ".join(required_terms),
                before_required,
                len(filtered_results),
            )

    description_terms = [t[len("説明:") :] for t in exclude_terms if t.startswith("説明:")]
    exclude_terms = [t for t in exclude_terms if not t.startswith("説明:")]
    # 「下限:40000」：説明文の確認の対象（名前にレア度がない候補）の、値段の下限
    description_floors = [int(t[len("下限:") :]) for t in exclude_terms if t.startswith("下限:")]
    exclude_terms = [t for t in exclude_terms if not t.startswith("下限:")]
    if description_terms:
        name_rarity = re.compile(r"(?<![A-Za-z])(SA|SAR|SR|UR|MUR|RR|RRR|AR|HR|CSR|SSR|BWR|CHR|S|A)(?![A-Za-z])")
        description_floor = max(description_floors, default=0)
        candidates = sorted(
            [r for r in filtered_results if not name_rarity.search(r.name) and r.price >= description_floor],
            key=lambda r: r.price,
        )[:10]
        passed_urls: set[str] = set()
        for cand in candidates:
            page.goto(cand.url)
            description = page.evaluate("document.body.innerText") or ""
            if any(f"[{term}]" in description for term in description_terms):
                passed_urls.add(cand.url)
        before_description = len(filtered_results)
        filtered_results = [
            r for r in filtered_results if any(term in r.name for term in description_terms) or r.url in passed_urls
        ]
        logging.info(
            "[%s] %s: 名前にレア度がない商品 %d 件を商品ページで確認 (%d件 -> %d件)",
            label,
            item.name,
            len(candidates),
            before_description,
            len(filtered_results),
        )

    if "レア度必須" in exclude_terms:
        exclude_terms.remove("レア度必須")
        rarity_pattern = re.compile(r"(?<![A-Za-z])(SA|SAR|SR|UR|MUR|RR|RRR|AR|HR|CSR|SSR|BWR|CHR|S|A)(?![A-Za-z])")
        # 「番号:○○/○○」の番号が名前にあれば、レア度がなくても合格にする（番号かレア度のどちらかがあればよい）
        numbers_for_rarity = [t[len("番号:") :] for t in exclude_terms if t.startswith("番号:")]
        before_rarity = len(filtered_results)
        filtered_results = [
            r
            for r in filtered_results
            if rarity_pattern.search(r.name)
            or any(re.search(rf"(?<!\d){re.escape(n)}(?!\d)", r.name) for n in numbers_for_rarity)
        ]
        if len(filtered_results) < before_rarity:
            logging.info("[%s] %s: レア度の記載がない商品を除外 (%d件 -> %d件)", label, item.name, before_rarity, len(filtered_results))
    # 「番号119」は、カード番号「119/...」の商品も合格にする指定（SA の文字がなくても、同じカードを取れるように）
    card_numbers = [t[2:] for t in exclude_terms if t.startswith("番号") and not t.startswith("番号:")]
    exclude_terms = [t for t in exclude_terms if not t.startswith("番号") or t.startswith("番号:")]
    # 「SA番号:101/095」：SR 系の SA 版。SA の表記がある出品か、SA の番号が名前にある出品だけ残す（通常の SR を外す）
    sa_numbers = [t[len("SA番号:") :] for t in exclude_terms if t.startswith("SA番号:")]
    exclude_terms = [t for t in exclude_terms if not t.startswith("SA番号:")]
    if sa_numbers:
        before_sr = len(filtered_results)
        sa_word = re.compile(r"(?<![A-Za-z])SA(?![A-Za-z])|スペシャルアート", re.IGNORECASE)
        filtered_results = [
            r for r in filtered_results
            if sa_word.search(r.name) or any(n in r.name for n in sa_numbers) or r.url in hr_urls
        ]
        if len(filtered_results) < before_sr:
            logging.info("[%s] %s: SA 版でない商品を除外 (%d件 -> %d件)", label, item.name, before_sr, len(filtered_results))
    # 「SA必須」は 2 段階目では見ない（検索語の「X SA」で、SA の表記は 1 段階目で確かめている）
    if "SA必須" in exclude_terms:
        exclude_terms.remove("SA必須")
    # 「番号:095/069」の指定：その番号が名前にある出品は合格、別の番号（○○/○○）が書いてある出品は外す。
    # 番号が書いていない出品は外さない（番号がなくても取れるように）
    target_numbers = [t[len("番号:") :] for t in exclude_terms if t.startswith("番号:")]
    exclude_terms = [t for t in exclude_terms if not t.startswith("番号:")]
    if target_numbers:

        def _number_ok(name: str) -> bool:
            if any(re.search(rf"(?<!\d){re.escape(n)}(?!\d)", name) for n in target_numbers):
                return True
            return re.search(r"\d{1,3}/\d{2,3}", name) is None

        before_number = len(filtered_results)
        filtered_results = [r for r in filtered_results if _number_ok(r.name)]
        if len(filtered_results) < before_number:
            logging.info(
                "[%s] %s: 別の番号の商品を除外 (%d件 -> %d件)", label, item.name, before_number, len(filtered_results)
            )

    if exclude_terms:
        before_exclude = len(filtered_results)
        filtered_results = [
            r for r in filtered_results if not any(price_watch.store.search_filter.normalize_name(term.removeprefix("名:")) in price_watch.store.search_filter.normalize_name(r.name) for term in exclude_terms)
        ]
        if len(filtered_results) < before_exclude:
            logging.info(
                "[%s] %s: 除外キーワードを含む商品を除外 (%d件 -> %d件)",
                label,
                item.name,
                before_exclude,
                len(filtered_results),
            )

    if not filtered_results:
        logging.info("[%s] %s: 条件に一致する商品なし", label, item.name)
        result.stock = price_watch.models.StockStatus.OUT_OF_STOCK
        result.crawl_status = price_watch.models.CrawlStatus.SUCCESS
        return result

    # 最安値を探す
    cheapest = min(filtered_results, key=lambda r: r.price)

    logging.info(
        "[%s] %s: %d件中最安値 ¥%s - %s",
        label,
        item.name,
        len(filtered_results),
        f"{cheapest.price:,}",
        cheapest.name,
    )

    # 結果を設定（アフィリエイトID付与）
    # 個別ページURLを取得
    detail_url = cheapest.url
    if hasattr(cheapest, 'detail_url') and cheapest.detail_url:
        detail_url = cheapest.detail_url
    elif hasattr(cheapest, 'item_id') and cheapest.item_id:
        if item.check_method == price_watch.target.CheckMethod.PAYPAY_SEARCH:
            detail_url = f"https://paypayfleamarket.yahoo.co.jp/item/{cheapest.item_id}"

    # URL をクリーニング（スペース以降を削除）
    if detail_url and ' ' in detail_url:
        detail_url = detail_url.split(' ')[0]

    # 最終更新日が直近30日以内の出品だけを残す（安い順に商品ページを開いて確かめ、5件そろうまで。最大15件）
    recent_results = []
    for cand in sorted(filtered_results, key=lambda r: r.price)[:15]:
        if len(recent_results) >= 5:
            break
        page.goto(cand.url)
        if _is_recent_listing(page.evaluate("document.body.innerText") or ""):
            recent_results.append(cand)
    logging.info(
        "[%s] %s: 直近30日以内の出品 %d 件（候補 %d 件から）", label, item.name, len(recent_results), len(filtered_results)
    )
    filtered_results = recent_results

    # 最安の上位5件を取得
    top3_results = sorted(filtered_results, key=lambda r: r.price)[:5]

    # TOP3 全件を格納
    result.top3_items = top3_results

    # TOP3 全件をログ出力（デバッグ用）
    logging.info("[進捗] %s: 上位 %d 件を確定（%s）", item.name, len(top3_results), label)
    logging.info("[%s] %s: TOP3全件のデバッグ情報:", label, item.name)
    for rank, top_item in enumerate(top3_results, 1):
        all_attrs = vars(top_item)
        logging.info("  TOP%d attributes: %s", rank, all_attrs)
        url = getattr(top_item, 'url', getattr(top_item, 'detail_url', 'N/A'))
        item_id = getattr(top_item, 'item_id', 'N/A')
        logging.info("  TOP%d: Price=¥%s, Name=%s, URL=%s, ID=%s", rank, f"{top_item.price:,}", top_item.name[:50], url, item_id)

    result.url = price_watch.affiliate.append_affiliate_id(detail_url, item.affiliate_id, item.check_method)
    result.price = cheapest.price
    result.stock = price_watch.models.StockStatus.IN_STOCK
    result.crawl_status = price_watch.models.CrawlStatus.SUCCESS

    return result


def generate_item_key(item: price_watch.models.CheckedItem) -> str:
    """フリマアイテム用の item_key を生成.

    Args:
        item: チェック済みアイテム

    Returns:
        item_key
    """
    return price_watch.history.generate_item_key(
        search_keyword=item.search_keyword,
        search_cond=item.search_cond,
        store_name=item.store,
    )
