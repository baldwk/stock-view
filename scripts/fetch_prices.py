# @(#)fetch_prices.py, June 3, 2026.
# <p/>
# Copyright 2026 fenbi.com. All rights reserved.
# FENBI.COM PROPRIETARY/CONFIDENTIAL. Use is subject to license terms.
#
# @Author: wukeyu
# @Date: 2026/6/3 12:47

import argparse
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from data_source import get_data_source
from database import DB_PATH, init_db, upsert_market_caps, upsert_prices, upsert_stocks


def parse_args():
    parser = argparse.ArgumentParser(description="Fetch A-share close prices into sqlite.")
    parser.add_argument("--years", type=int, default=5, help="How many calendar years to fetch.")
    parser.add_argument("--limit", type=int, default=0, help="Limit stock count for testing.")
    parser.add_argument("--sleep", type=float, default=1.0, help="Seconds to sleep between stocks.")
    parser.add_argument("--retries", type=int, default=5, help="Retry count for each stock request.")
    parser.add_argument("--retry-wait", type=float, default=2.0, help="Base seconds before retrying.")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout seconds for data source.")
    parser.add_argument("--symbols", default="", help="Comma separated stock symbols for testing.")
    parser.add_argument("--metadata-only", action="store_true", help="Only update stock names and market caps.")
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


def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    end_date = date.today()
    start_date = end_date - timedelta(days=args.years * 365)
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

    for index, stock in enumerate(stocks, start=1):
        symbol = stock["symbol"]
        name = stock["name"]
        try:
            logging.info(
                "Fetching %s/%s %s %s from %s to %s",
                index,
                len(stocks),
                symbol,
                name,
                start_date,
                end_date,
            )
            prices = data_source.fetch_daily_closes(
                symbol,
                start_date,
                end_date,
                retries=args.retries,
                retry_wait=args.retry_wait,
                timeout=args.timeout,
            )
            saved_count = upsert_prices(symbol, prices)
            logging.info("Saved %s daily close prices for %s", saved_count, symbol)
        except Exception:
            failed = True
            logging.exception("Failed to fetch or save prices for %s", symbol)

        if args.sleep > 0:
            time.sleep(args.sleep)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
