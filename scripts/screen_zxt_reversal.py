# @(#)screen_zxt_reversal.py, June 3, 2026.
# <p/>
# Copyright 2026 fenbi.com. All rights reserved.
# FENBI.COM PROPRIETARY/CONFIDENTIAL. Use is subject to license terms.
#
# @Author: wukeyu
# @Date: 2026/6/3 23:39

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from database import get_prices, init_db, list_stocks, save_zxt_reversal_screen_run, upsert_zxt_reversal_results


MIN_PRICE_COUNT = 114


def parse_args():
    parser = argparse.ArgumentParser(description="Screen stocks by ZXT reversal formula.")
    parser.add_argument("--symbols", default="", help="Comma separated stock symbols. Empty means all stocks.")
    parser.add_argument("--limit", type=int, default=0, help="Limit selected stock count before screening.")
    parser.add_argument("--show-all", action="store_true", help="Show stocks even when XG is false.")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text table.")
    parser.add_argument("--no-save", action="store_true", help="Do not save screen results into sqlite.")
    return parser.parse_args()


def selected_stocks(symbols, limit):
    stocks = list_stocks()
    if symbols:
        symbol_set = {item.strip() for item in symbols.split(",") if item.strip()}
        stocks = [stock for stock in stocks if stock["symbol"] in symbol_set]

    if limit > 0:
        stocks = stocks[:limit]
    return stocks


def tdx_sma(series, n, m):
    values = []
    previous = None
    for value in series:
        if pd.isna(value):
            values.append(float("nan"))
            continue

        current = value if previous is None or pd.isna(previous) else (m * value + (n - m) * previous) / n
        values.append(current)
        previous = current
    return pd.Series(values, index=series.index, dtype="float64")


def ref(series, days):
    return series.shift(days)


def build_price_frame(prices):
    prices = [item for item in prices if item.get("high_price") is not None and item.get("low_price") is not None]
    if len(prices) < MIN_PRICE_COUNT:
        return None

    return pd.DataFrame(prices).sort_values("trade_date").reset_index(drop=True)


def calculate_indicators(df):
    close = pd.to_numeric(df["close_price"], errors="coerce")
    high = pd.to_numeric(df["high_price"], errors="coerce")
    low = pd.to_numeric(df["low_price"], errors="coerce")

    hhv_high_4 = high.rolling(4).max()
    llv_low_4 = low.rolling(4).min()
    range_4 = hhv_high_4 - llv_low_4

    var1a = ((hhv_high_4 - close) / range_4.where(range_4 != 0)) * 100 - 90
    var2a = tdx_sma(var1a, 4, 1) + 100
    var3a = ((close - llv_low_4) / range_4.where(range_4 != 0)) * 100
    var4a = tdx_sma(var3a, 6, 1)
    var5a = tdx_sma(var4a, 6, 1) + 100
    var6a = var5a - var2a
    zxt = (var6a - 4).where(var6a > 4, 0)

    today_red = zxt > ref(zxt, 1)
    pre_3_green = (ref(zxt, 1) < ref(zxt, 2)) & (ref(zxt, 2) < ref(zxt, 3)) & (ref(zxt, 3) < ref(zxt, 4))
    red_body = zxt - ref(zxt, 1)
    green_body_yest = ref(zxt, 2) - ref(zxt, 1)
    body_ok = red_body * 3 >= green_body_yest * 2
    pct_ok = ((close - ref(close, 1)) / ref(close, 1) * 100) < 4
    yl = (
        close.rolling(14).mean()
        + close.rolling(28).mean()
        + close.rolling(57).mean()
        + close.rolling(114).mean()
    ) / 4
    on_yl = close > yl
    xg = today_red & pre_3_green & body_ok & pct_ok & on_yl

    return {
        "close": close,
        "zxt": zxt,
        "zxt_prev": ref(zxt, 1),
        "red_body": red_body,
        "green_body_yest": green_body_yest,
        "pct_change": (close - ref(close, 1)) / ref(close, 1) * 100,
        "yl": yl,
        "today_red": today_red,
        "pre_3_green": pre_3_green,
        "body_ok": body_ok,
        "pct_ok": pct_ok,
        "on_yl": on_yl,
        "xg": xg,
    }


def build_signal_result(stock, df, indicators, index):
    if pd.isna(indicators["yl"].iloc[index]) or pd.isna(indicators["zxt"].iloc[index]):
        return None

    return {
        "symbol": stock["symbol"],
        "name": stock["name"],
        "trade_date": df["trade_date"].iloc[index],
        "close": float(indicators["close"].iloc[index]),
        "zxt": float(indicators["zxt"].iloc[index]),
        "zxt_prev": float(indicators["zxt_prev"].iloc[index]),
        "red_body": float(indicators["red_body"].iloc[index]),
        "green_body_yest": float(indicators["green_body_yest"].iloc[index]),
        "pct_change": float(indicators["pct_change"].iloc[index]),
        "yl": float(indicators["yl"].iloc[index]),
        "today_red": bool(indicators["today_red"].iloc[index]),
        "pre_3_green": bool(indicators["pre_3_green"].iloc[index]),
        "body_ok": bool(indicators["body_ok"].iloc[index]),
        "pct_ok": bool(indicators["pct_ok"].iloc[index]),
        "on_yl": bool(indicators["on_yl"].iloc[index]),
        "xg": bool(indicators["xg"].iloc[index]),
    }


def calculate_signal(stock, prices):
    df = build_price_frame(prices)
    if df is None:
        return None

    return build_signal_result(stock, df, calculate_indicators(df), len(df) - 1)


def calculate_historical_signals(stock, prices, xg_only=True):
    df = build_price_frame(prices)
    if df is None:
        return []

    indicators = calculate_indicators(df)
    signals = []
    for index in range(len(df)):
        signal = build_signal_result(stock, df, indicators, index)
        if signal is None:
            continue
        if xg_only and not signal["xg"]:
            continue
        signals.append(signal)
    return signals


def build_results(stocks, show_all):
    results = []
    for stock in stocks:
        signal = calculate_signal(stock, get_prices(stock["symbol"]))
        if signal is None:
            continue
        if show_all or signal["xg"]:
            results.append(signal)

    results.sort(key=lambda item: (not item["xg"], item["symbol"]))
    return results


def yes_no(value):
    return "是" if value else "否"


def format_number(value):
    return f"{value:.3f}"


def print_table(results):
    if not results:
        print("没有符合 XG 条件的股票。若刚升级脚本，请重新拉取价格以补齐 high/low 数据。")
        return

    print(f"{'代码':<8}{'名称':<12}{'日期':<14}{'收盘':>10}{'ZXT':>10}{'涨幅%':>10}{'黄线':>10}{'XG':>6}")
    for item in results:
        print(
            f"{item['symbol']:<8}{item['name']:<12}{item['trade_date']:<14}"
            f"{format_number(item['close']):>10}"
            f"{format_number(item['zxt']):>10}"
            f"{format_number(item['pct_change']):>10}"
            f"{format_number(item['yl']):>10}"
            f"{yes_no(item['xg']):>6}"
        )


def main():
    args = parse_args()
    init_db()
    results = build_results(selected_stocks(args.symbols, args.limit), args.show_all)
    if not args.no_save:
        upsert_zxt_reversal_results(results)
        save_zxt_reversal_screen_run(results, run_type="close_1600", source="tencent_daily")
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print_table(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
