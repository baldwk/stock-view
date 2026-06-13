# @(#)app.py, June 3, 2026.
# <p/>
# Copyright 2026 fenbi.com. All rights reserved.
# FENBI.COM PROPRIETARY/CONFIDENTIAL. Use is subject to license terms.
#
# @Author: wukeyu
# @Date: 2026/6/3 12:47

import logging
import math
import os
import re
from datetime import date, datetime, timedelta

from flask import Flask, jsonify, request, send_from_directory

from data_source import get_data_source
from database import (
    get_latest_zxt_reversal_screen_run,
    get_last_trade_date,
    get_prices,
    init_db,
    list_zxt_reversal_screen_results,
    list_stock_price_rows,
    list_stocks,
    upsert_market_caps,
    upsert_prices,
    upsert_stock,
)
from zxt_reversal_service import (
    RUN_TYPE_CLOSE_1600,
    RUN_TYPE_INTRADAY_1430,
    run_close_screen,
    run_intraday_screen,
    select_stocks as select_zxt_stocks,
)


SYMBOL_PATTERN = re.compile(r"^\d{6}$")
DEFAULT_ON_DEMAND_YEARS = int(os.environ.get("STOCK_VIEW_ON_DEMAND_YEARS", "5"))

app = Flask(__name__, static_folder="static", static_url_path="")
init_db()


def parse_date_arg(name):
    value = request.args.get(name)
    if not value:
        return None

    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"{name} must use yyyy-mm-dd format") from None
    return value


def parse_positive_int_arg(name, default_value):
    value = request.args.get(name)
    if not value:
        return default_value

    try:
        parsed_value = int(value)
    except ValueError:
        raise ValueError(f"{name} must be a positive integer") from None

    if parsed_value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return parsed_value


def parse_positive_float_arg(name):
    value = request.args.get(name)
    if not value:
        return 0.0

    try:
        parsed_value = float(value)
    except ValueError:
        raise ValueError(f"{name} must be a positive number") from None

    if parsed_value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return parsed_value


def parse_bool_arg(name, default_value=False):
    value = request.args.get(name)
    if value is None:
        return default_value
    return value.lower() in ("1", "true", "yes", "y")


def resolve_on_demand_range(start_date, end_date):
    today = date.today()
    fetch_start_date = date.fromisoformat(start_date) if start_date else today - timedelta(days=DEFAULT_ON_DEMAND_YEARS * 365)
    fetch_end_date = date.fromisoformat(end_date) if end_date else today
    return fetch_start_date, fetch_end_date


def resolve_stock_name(data_source, symbol):
    try:
        for stock in data_source.list_stocks():
            if stock["symbol"] == symbol:
                return stock["name"]
    except Exception:
        logging.exception("Failed to resolve stock name for %s", symbol)
    return symbol


def ensure_prices(symbol, start_date, end_date):
    if get_last_trade_date(symbol):
        return False

    data_source = get_data_source()
    fetch_start_date, fetch_end_date = resolve_on_demand_range(start_date, end_date)
    logging.info(
        "No local prices for %s, fetching from %s between %s and %s",
        symbol,
        data_source.name,
        fetch_start_date,
        fetch_end_date,
    )
    stock_name = resolve_stock_name(data_source, symbol)
    upsert_stock(symbol, stock_name)
    prices = data_source.fetch_daily_closes(symbol, fetch_start_date, fetch_end_date)
    upsert_prices(symbol, prices)
    logging.info("Saved %s on-demand close prices for %s", len(prices), symbol)
    return True


def round_brick_size(value):
    if value <= 0:
        return 0.0

    power = 10 ** math.floor(math.log10(value))
    normalized = value / power
    step = 1
    if normalized >= 5:
        step = 5
    elif normalized >= 2:
        step = 2
    return round(step * power, 4)


def resolve_brick_size(prices, configured_brick_size):
    if configured_brick_size > 0:
        return configured_brick_size

    closes = [item["close_price"] for item in prices]
    high = max(closes)
    low = min(closes)
    latest = closes[-1]
    raw_size = (high - low) / 40 if high > low else latest * 0.01
    return round_brick_size(max(raw_size, 0.01))


def build_renko_bricks(prices, brick_size):
    if not prices or brick_size <= 0:
        return []

    last_brick_close = prices[0]["close_price"]
    bricks = []
    for price in prices[1:]:
        close_price = price["close_price"]
        diff = close_price - last_brick_close

        while abs(diff) >= brick_size:
            direction = 1 if diff > 0 else -1
            brick_close = last_brick_close + direction * brick_size
            bricks.append(
                {
                    "date": price["trade_date"],
                    "close": brick_close,
                    "direction": direction,
                }
            )
            last_brick_close = brick_close
            diff = close_price - last_brick_close
    return bricks


def count_latest_up_bricks(bricks):
    count = 0
    for brick in reversed(bricks):
        if brick["direction"] <= 0:
            break
        count += 1
    return count


def group_price_rows(rows, start_date, end_date):
    stocks = {}
    for row in rows:
        trade_date = row["trade_date"]
        if start_date and trade_date < start_date:
            continue
        if end_date and trade_date > end_date:
            continue

        symbol = row["symbol"]
        stock = stocks.setdefault(
            symbol,
            {
                "symbol": symbol,
                "name": row["name"],
                "market_cap": row["market_cap"],
                "prices": [],
            },
        )
        stock["prices"].append({"trade_date": trade_date, "close_price": row["close_price"]})
    return stocks.values()


def refresh_market_caps():
    data_source = get_data_source()
    market_caps = data_source.fetch_market_caps()
    saved_count = upsert_market_caps(market_caps)
    logging.info("Saved %s current market caps from %s", saved_count, data_source.name)
    return saved_count


def screen_renko_up_stocks(min_up_bricks, configured_brick_size, start_date, end_date, limit):
    results = []
    for stock in group_price_rows(list_stock_price_rows(), start_date, end_date):
        prices = stock["prices"]
        if len(prices) < 2:
            continue

        brick_size = resolve_brick_size(prices, configured_brick_size)
        bricks = build_renko_bricks(prices, brick_size)
        latest_up_bricks = count_latest_up_bricks(bricks)
        if latest_up_bricks < min_up_bricks:
            continue

        results.append(
            {
                "symbol": stock["symbol"],
                "name": stock["name"],
                "market_cap": stock["market_cap"],
                "latest_close": prices[-1]["close_price"],
                "latest_trade_date": prices[-1]["trade_date"],
                "latest_brick_date": bricks[-1]["date"] if bricks else "",
                "brick_size": brick_size,
                "brick_count": len(bricks),
                "latest_up_bricks": latest_up_bricks,
            }
        )

    results.sort(key=lambda item: (-item["latest_up_bricks"], -(item["market_cap"] or 0)))
    return results[:limit]


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/recommendations")
def recommendations_page():
    return send_from_directory(app.static_folder, "recommendations.html")


@app.get("/kline")
def kline_page():
    return send_from_directory(app.static_folder, "kline.html")


@app.get("/api/stocks")
def stocks_api():
    return jsonify({"stocks": list_stocks()})


@app.get("/api/stocks/<symbol>/prices")
def prices_api(symbol):
    if not SYMBOL_PATTERN.match(symbol):
        return jsonify({"error": "symbol must be a 6-digit A-share code"}), 400

    try:
        start_date = parse_date_arg("start_date")
        end_date = parse_date_arg("end_date")
    except ValueError as ex:
        return jsonify({"error": str(ex)}), 400

    try:
        fetched = ensure_prices(symbol, start_date, end_date)
    except Exception:
        logging.exception("Failed to fetch on-demand prices for %s", symbol)
        return jsonify({"error": "failed to fetch prices from data source"}), 502

    return jsonify(
        {
            "symbol": symbol,
            "fetched": fetched,
            "prices": get_prices(symbol, start_date=start_date, end_date=end_date),
        }
    )


@app.get("/api/screener/renko-up")
def renko_up_screener_api():
    try:
        min_up_bricks = parse_positive_int_arg("min_up_bricks", 3)
        limit = parse_positive_int_arg("limit", 50)
        brick_size = parse_positive_float_arg("brick_size")
        start_date = parse_date_arg("start_date")
        end_date = parse_date_arg("end_date")
    except ValueError as ex:
        return jsonify({"error": str(ex)}), 400

    refresh_market_cap = request.args.get("refresh_market_cap", "true").lower() != "false"
    if refresh_market_cap:
        try:
            refresh_market_caps()
        except Exception:
            logging.exception("Failed to refresh current market caps")

    return jsonify(
        {
            "items": screen_renko_up_stocks(min_up_bricks, brick_size, start_date, end_date, limit),
        }
    )


@app.get("/api/recommendations/zxt")
def zxt_recommendations_api():
    try:
        limit = parse_positive_int_arg("limit", 50)
        trade_date = parse_date_arg("trade_date")
    except ValueError as ex:
        return jsonify({"error": str(ex)}), 400

    run_type = request.args.get("run_type") or None
    run = get_latest_zxt_reversal_screen_run(run_type=run_type, trade_date=trade_date)
    if run is None:
        return jsonify({"run": None, "items": []})

    return jsonify(
        {
            "run": run,
            "items": list_zxt_reversal_screen_results(run["run_id"], limit=limit),
        }
    )


@app.post("/api/recommendations/zxt/run")
def run_zxt_recommendations_api():
    try:
        limit = parse_positive_int_arg("limit", 0)
        retries = parse_positive_int_arg("retries", 5)
    except ValueError as ex:
        return jsonify({"error": str(ex)}), 400

    run_type = request.args.get("run_type", RUN_TYPE_INTRADAY_1430)
    if run_type not in (RUN_TYPE_INTRADAY_1430, RUN_TYPE_CLOSE_1600):
        return jsonify({"error": "run_type must be intraday_1430 or close_1600"}), 400

    symbols = request.args.get("symbols", "")
    show_all = parse_bool_arg("show_all")
    stocks = select_zxt_stocks(symbols=symbols, limit=limit)
    try:
        if run_type == RUN_TYPE_INTRADAY_1430:
            result = run_intraday_screen(get_data_source(), stocks, retries=retries, show_all=show_all)
        else:
            result = run_close_screen(stocks, show_all=show_all)
    except Exception:
        logging.exception("Failed to run ZXT recommendation screen")
        return jsonify({"error": "failed to run ZXT recommendation screen"}), 502

    return jsonify(result)


if __name__ == "__main__":
    host = os.environ.get("STOCK_VIEW_HOST", "0.0.0.0")
    port = int(os.environ.get("STOCK_VIEW_PORT", "5000"))
    debug = os.environ.get("STOCK_VIEW_DEBUG", "false").lower() in ("1", "true", "yes", "y")
    app.run(host=host, port=port, debug=debug)
