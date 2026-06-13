# @(#)update_daily_prices.py, June 3, 2026.
# <p/>
# Copyright 2026 fenbi.com. All rights reserved.
# FENBI.COM PROPRIETARY/CONFIDENTIAL. Use is subject to license terms.
#
# @Author: wukeyu
# @Date: 2026/6/3 13:01

import argparse
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from data_source import get_data_source
from database import DB_PATH, get_last_trade_date, init_db, upsert_market_caps, upsert_prices, upsert_stocks


def parse_args():
    parser = argparse.ArgumentParser(description="Incrementally update A-share close prices.")
    parser.add_argument(
        "--fallback-years",
        type=int,
        default=5,
        help="Years to fetch when a stock has no stored prices.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Limit stock count for testing.")
    parser.add_argument("--sleep", type=float, default=1.0, help="Seconds to sleep between stocks.")
    parser.add_argument("--retries", type=int, default=5, help="Retry count for each stock request.")
    parser.add_argument("--retry-wait", type=float, default=2.0, help="Base seconds before retrying.")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout seconds for data source.")
    parser.add_argument("--symbols", default="", help="Comma separated stock symbols for testing.")
    parser.add_argument("--workers", type=int, default=16, help="Concurrent stock update workers.")
    parser.add_argument("--metadata-only", action="store_true", help="Only update stock names and market caps.")
    parser.add_argument(
        "--refresh-history",
        action="store_true",
        help="Refresh fallback-years history even when the stock is already up to date.",
    )
    return parser.parse_args()


def select_stocks(stocks, symbols, limit):
    if symbols:
        symbol_set = {item.strip() for item in symbols.split(",") if item.strip()}
        stocks = [item for item in stocks if item["symbol"] in symbol_set]

    if limit > 0:
        stocks = stocks[:limit]
    return stocks


def select_market_caps(market_caps, stocks):
    symbol_set = {stock["symbol"] for stock in stocks}
    return [item for item in market_caps if item["symbol"] in symbol_set]


def save_stock_metadata(data_source, stocks, retries, retry_wait):
    saved_stock_count = upsert_stocks(stocks)
    logging.info("Saved %s stock base records", saved_stock_count)

    market_caps = select_market_caps(
        data_source.fetch_market_caps(stocks=stocks, retries=retries, retry_wait=retry_wait),
        stocks,
    )
    saved_market_cap_count = upsert_market_caps(market_caps)
    logging.info("Saved %s current market cap records", saved_market_cap_count)


def resolve_start_date(symbol, today, fallback_years, refresh_history):
    if refresh_history:
        return today - timedelta(days=fallback_years * 365)

    last_trade_date = get_last_trade_date(symbol)
    if not last_trade_date:
        return today - timedelta(days=fallback_years * 365)

    return date.fromisoformat(last_trade_date) + timedelta(days=1)


def update_stock_prices(index, total, stock, data_source, today, args):
    symbol = stock["symbol"]
    name = stock["name"]

    try:
        start_date = resolve_start_date(symbol, today, args.fallback_years, args.refresh_history)
        if start_date > today:
            logging.info("Skipping %s/%s %s %s, already up to date", index, total, symbol, name)
            return {"skipped": True, "failed": False}

        logging.info(
            "Updating %s/%s %s %s from %s to %s",
            index,
            total,
            symbol,
            name,
            start_date,
            today,
        )
        prices = data_source.fetch_daily_closes(
            symbol,
            start_date,
            today,
            retries=args.retries,
            retry_wait=args.retry_wait,
            timeout=args.timeout,
        )
        saved_count = upsert_prices(symbol, prices)
        logging.info("Saved %s incremental close prices for %s", saved_count, symbol)
        return {"skipped": False, "failed": False}
    except Exception:
        logging.exception("Failed to update prices for %s", symbol)
        return {"skipped": False, "failed": True}
    finally:
        if args.sleep > 0:
            time.sleep(args.sleep)


def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    today = date.today()
    logging.info("Initializing sqlite database at %s", DB_PATH)
    init_db()

    data_source = get_data_source()
    stocks = select_stocks(data_source.list_stocks(), args.symbols, args.limit)
    logging.info("Selected %s SSE/SZSE stocks from %s", len(stocks), data_source.name)

    failed = False
    try:
        save_stock_metadata(data_source, stocks, args.retries, args.retry_wait)
    except Exception:
        if args.metadata_only:
            failed = True
            logging.exception("Failed to fetch or save stock metadata")
        else:
            logging.warning("Failed to fetch or save stock metadata, continuing price update", exc_info=True)

    if args.metadata_only:
        return 1 if failed else 0

    skipped_count = 0
    worker_count = max(1, args.workers)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(update_stock_prices, index, len(stocks), stock, data_source, today, args)
            for index, stock in enumerate(stocks, start=1)
        ]
        for future in as_completed(futures):
            result = future.result()
            if result["skipped"]:
                skipped_count += 1
            if result["failed"]:
                failed = True

    logging.info("Skipped %s up-to-date stocks", skipped_count)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
