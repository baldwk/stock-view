# @(#)zxt_reversal_service.py, June 13, 2026.
# <p/>
# Copyright 2026 fenbi.com. All rights reserved.
# FENBI.COM PROPRIETARY/CONFIDENTIAL. Use is subject to license terms.
#
# @Author: wukeyu
# @Date: 2026/6/13 20:01

from database import (
    get_prices,
    list_stocks,
    save_zxt_reversal_screen_run,
    upsert_zxt_reversal_results,
)
from scripts.screen_zxt_reversal import calculate_signal


RUN_TYPE_INTRADAY_1430 = "intraday_1430"
RUN_TYPE_CLOSE_1600 = "close_1600"
SOURCE_TENCENT_DAILY = "tencent_daily"
SOURCE_TENCENT_REALTIME = "tencent_realtime"


def select_stocks(symbols="", limit=0):
    stocks = list_stocks()
    if symbols:
        symbol_set = {item.strip() for item in symbols.split(",") if item.strip()}
        stocks = [stock for stock in stocks if stock["symbol"] in symbol_set]

    if limit > 0:
        stocks = stocks[:limit]
    return stocks


def append_intraday_quote(prices, quote):
    if not quote:
        return prices

    trade_date = quote["trade_date"]
    historical_prices = [item for item in prices if item["trade_date"] != trade_date]
    historical_prices.append(
        {
            "trade_date": trade_date,
            "open_price": quote.get("open_price"),
            "close_price": quote["close_price"],
            "high_price": quote["high_price"],
            "low_price": quote["low_price"],
            "volume": quote.get("volume"),
        }
    )
    historical_prices.sort(key=lambda item: item["trade_date"])
    return historical_prices


def build_zxt_results(stocks, quote_by_symbol=None, show_all=False):
    results = []
    quote_by_symbol = quote_by_symbol or {}
    for stock in stocks:
        prices = get_prices(stock["symbol"])
        prices = append_intraday_quote(prices, quote_by_symbol.get(stock["symbol"]))
        signal = calculate_signal(stock, prices)
        if signal is None:
            continue
        if show_all or signal["xg"]:
            results.append(signal)

    results.sort(key=lambda item: (not item["xg"], item["symbol"]))
    return results


def save_zxt_results(results, run_type, source, trade_date=None):
    if results:
        upsert_zxt_reversal_results(results)
    return save_zxt_reversal_screen_run(results, run_type=run_type, trade_date=trade_date, source=source)


def run_intraday_screen(data_source, stocks, retries=5, retry_wait=2.0, show_all=False):
    quotes = data_source.fetch_realtime_quotes(stocks=stocks, retries=retries, retry_wait=retry_wait)
    quote_by_symbol = {item["symbol"]: item for item in quotes}
    results = build_zxt_results(stocks, quote_by_symbol=quote_by_symbol, show_all=show_all)
    trade_date = max((item["trade_date"] for item in quotes), default=None)
    run_id = save_zxt_results(results, RUN_TYPE_INTRADAY_1430, SOURCE_TENCENT_REALTIME, trade_date=trade_date)
    return {
        "run_id": run_id,
        "quote_count": len(quotes),
        "item_count": len(results),
        "items": results,
    }


def run_close_screen(stocks, show_all=False):
    results = build_zxt_results(stocks, show_all=show_all)
    trade_date = max((item["trade_date"] for item in results), default=None)
    run_id = save_zxt_results(results, RUN_TYPE_CLOSE_1600, SOURCE_TENCENT_DAILY, trade_date=trade_date)
    return {
        "run_id": run_id,
        "item_count": len(results),
        "items": results,
    }
