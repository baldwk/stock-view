# @(#)scheduler.py, June 13, 2026.
# <p/>
# Copyright 2026 fenbi.com. All rights reserved.
# FENBI.COM PROPRIETARY/CONFIDENTIAL. Use is subject to license terms.
#
# @Author: wukeyu
# @Date: 2026/6/13 20:01

import argparse
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time as day_time, timedelta
from pathlib import Path
from types import SimpleNamespace


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from data_source import get_data_source
from database import DB_PATH, init_db
from scripts.update_daily_prices import save_stock_metadata, select_stocks, update_stock_prices
from zxt_reversal_service import run_close_screen, run_intraday_screen


INTRADAY_TIME = day_time(hour=14, minute=30)
CLOSE_TIME = day_time(hour=16, minute=0)


def parse_args():
    parser = argparse.ArgumentParser(description="Run Stock View scheduled data updates and ZXT screens.")
    parser.add_argument("--symbols", default="", help="Comma separated stock symbols for testing.")
    parser.add_argument("--limit", type=int, default=0, help="Limit stock count for testing.")
    parser.add_argument("--workers", type=int, default=16, help="Concurrent stock update workers.")
    parser.add_argument("--fallback-years", type=int, default=5, help="Years to fetch when a stock has no stored prices.")
    parser.add_argument("--sleep", type=float, default=1.0, help="Seconds to sleep after each stock request.")
    parser.add_argument("--retries", type=int, default=5, help="Retry count for each request.")
    parser.add_argument("--retry-wait", type=float, default=2.0, help="Base seconds before retrying.")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout seconds for data source.")
    parser.add_argument("--refresh-history", action="store_true", help="Refresh fallback-years history at 16:00.")
    parser.add_argument(
        "--run-once",
        choices=("intraday", "close", "both"),
        default="",
        help="Run a task once and exit. Empty means run forever.",
    )
    return parser.parse_args()


def build_update_args(args):
    return SimpleNamespace(
        fallback_years=args.fallback_years,
        refresh_history=args.refresh_history,
        retries=args.retries,
        retry_wait=args.retry_wait,
        timeout=args.timeout,
        sleep=args.sleep,
    )


def load_target_stocks(data_source, args):
    stocks = select_stocks(data_source.list_stocks(), args.symbols, args.limit)
    logging.info("Selected %s SSE/SZSE stocks from %s", len(stocks), data_source.name)
    return stocks


def run_intraday_job(args):
    logging.info("Starting 14:30 intraday ZXT recommendation job")
    init_db()
    data_source = get_data_source()
    stocks = load_target_stocks(data_source, args)
    save_stock_metadata(data_source, stocks, args.retries, args.retry_wait)
    result = run_intraday_screen(data_source, stocks, retries=args.retries, retry_wait=args.retry_wait)
    logging.info(
        "Finished intraday ZXT recommendation job, run_id=%s, quotes=%s, items=%s",
        result["run_id"],
        result["quote_count"],
        result["item_count"],
    )


def run_close_job(args):
    logging.info("Starting 16:00 close update job, sqlite=%s", DB_PATH)
    init_db()
    data_source = get_data_source()
    stocks = load_target_stocks(data_source, args)
    save_stock_metadata(data_source, stocks, args.retries, args.retry_wait)

    failed = False
    skipped_count = 0
    today = datetime.now().date()
    update_args = build_update_args(args)
    worker_count = max(1, args.workers)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(update_stock_prices, index, len(stocks), stock, data_source, today, update_args)
            for index, stock in enumerate(stocks, start=1)
        ]
        for future in as_completed(futures):
            result = future.result()
            if result["skipped"]:
                skipped_count += 1
            if result["failed"]:
                failed = True

    logging.info("Close update skipped %s up-to-date stocks", skipped_count)
    screen_result = run_close_screen(stocks)
    logging.info(
        "Finished close ZXT recommendation job, run_id=%s, items=%s",
        screen_result["run_id"],
        screen_result["item_count"],
    )
    if failed:
        raise RuntimeError("Some stock price updates failed")


def next_run_after(now, target_time):
    target = datetime.combine(now.date(), target_time)
    if target <= now:
        target += timedelta(days=1)
    return target


def next_scheduled_job():
    now = datetime.now()
    intraday_run = next_run_after(now, INTRADAY_TIME)
    close_run = next_run_after(now, CLOSE_TIME)
    if intraday_run <= close_run:
        return intraday_run, "intraday"
    return close_run, "close"


def sleep_until(target):
    while True:
        remaining_seconds = (target - datetime.now()).total_seconds()
        if remaining_seconds <= 0:
            return
        time.sleep(min(remaining_seconds, 60))


def run_once(args, task):
    if task in ("intraday", "both"):
        run_intraday_job(args)
    if task in ("close", "both"):
        run_close_job(args)


def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.run_once:
        run_once(args, args.run_once)
        return 0

    while True:
        target, task = next_scheduled_job()
        logging.info("Next %s job scheduled at %s", task, target)
        sleep_until(target)
        try:
            run_once(args, task)
        except Exception:
            logging.exception("Scheduled %s job failed", task)


if __name__ == "__main__":
    raise SystemExit(main())
