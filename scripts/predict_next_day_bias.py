# @(#)predict_next_day_bias.py, June 3, 2026.
# <p/>
# Copyright 2026 fenbi.com. All rights reserved.
# FENBI.COM PROPRIETARY/CONFIDENTIAL. Use is subject to license terms.
#
# @Author: wukeyu
# @Date: 2026/6/3 23:27

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from database import get_prices, list_stocks


MIN_PRICE_COUNT = 114


def parse_args():
    parser = argparse.ArgumentParser(description="Predict next trading day long/short bias by Zhixing formulas.")
    parser.add_argument("--symbols", default="", help="Comma separated stock symbols. Empty means all stocks.")
    parser.add_argument("--limit", type=int, default=0, help="Limit output count. 0 means no limit.")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text table.")
    return parser.parse_args()


def selected_stocks(symbols, limit):
    stocks = list_stocks()
    if symbols:
        symbol_set = {item.strip() for item in symbols.split(",") if item.strip()}
        stocks = [stock for stock in stocks if stock["symbol"] in symbol_set]

    if limit > 0:
        stocks = stocks[:limit]
    return stocks


def calculate_prediction(stock, prices):
    if len(prices) < MIN_PRICE_COUNT:
        return None

    df = pd.DataFrame(prices).sort_values("trade_date")
    close = pd.to_numeric(df["close_price"], errors="coerce")

    short_trend = close.ewm(span=10, adjust=False).mean().ewm(span=10, adjust=False).mean()
    long_short_line = (
        close.rolling(14).mean()
        + close.rolling(28).mean()
        + close.rolling(57).mean()
        + close.rolling(114).mean()
    ) / 4

    latest_index = len(df) - 1
    latest_short = short_trend.iloc[latest_index]
    latest_line = long_short_line.iloc[latest_index]
    if pd.isna(latest_short) or pd.isna(latest_line):
        return None

    diff = latest_short - latest_line
    bias = "偏多" if diff > 0 else "偏空" if diff < 0 else "中性"
    distance_pct = diff / latest_line * 100 if latest_line != 0 else 0

    return {
        "symbol": stock["symbol"],
        "name": stock["name"],
        "latest_trade_date": df["trade_date"].iloc[latest_index],
        "latest_close": float(close.iloc[latest_index]),
        "short_trend": float(latest_short),
        "long_short_line": float(latest_line),
        "distance_pct": float(distance_pct),
        "next_day_bias": bias,
    }


def build_predictions(stocks):
    predictions = []
    for stock in stocks:
        prediction = calculate_prediction(stock, get_prices(stock["symbol"]))
        if prediction is not None:
            predictions.append(prediction)

    predictions.sort(key=lambda item: item["distance_pct"], reverse=True)
    return predictions


def format_number(value):
    return f"{value:.3f}"


def print_table(predictions):
    if not predictions:
        print("没有可预测的股票数据，请先拉取至少 114 个交易日的收盘价。")
        return

    headers = ["代码", "名称", "最新交易日", "收盘", "短期趋势", "多空线", "偏离%", "预测"]
    print(
        f"{headers[0]:<8}{headers[1]:<12}{headers[2]:<14}"
        f"{headers[3]:>10}{headers[4]:>12}{headers[5]:>12}{headers[6]:>10}{headers[7]:>8}"
    )
    for item in predictions:
        print(
            f"{item['symbol']:<8}{item['name']:<12}{item['latest_trade_date']:<14}"
            f"{format_number(item['latest_close']):>10}"
            f"{format_number(item['short_trend']):>12}"
            f"{format_number(item['long_short_line']):>12}"
            f"{format_number(item['distance_pct']):>10}"
            f"{item['next_day_bias']:>8}"
        )


def main():
    args = parse_args()
    predictions = build_predictions(selected_stocks(args.symbols, args.limit))
    if args.json:
        print(json.dumps(predictions, ensure_ascii=False, indent=2))
    else:
        print_table(predictions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
