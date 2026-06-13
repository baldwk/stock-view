# @(#)backtest_zxt_reversal.py, June 12, 2026.
# <p/>
# Copyright 2026 fenbi.com. All rights reserved.
# FENBI.COM PROPRIETARY/CONFIDENTIAL. Use is subject to license terms.
#
# @Author: wukeyu
# @Date: 2026/6/12 22:30

import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from database import get_prices, init_db
from screen_zxt_reversal import calculate_historical_signals, selected_stocks


def parse_args():
    parser = argparse.ArgumentParser(description="Backtest ZXT reversal signals.")
    parser.add_argument("--symbols", default="", help="Comma separated stock symbols. Empty means all stocks.")
    parser.add_argument("--limit", type=int, default=0, help="Limit selected stock count before backtest.")
    parser.add_argument("--hold-days", type=int, default=1, help="Trading days to hold after signal.")
    parser.add_argument("--success-threshold", type=float, default=0.0, help="Return percent threshold for success.")
    parser.add_argument("--min-date", default="", help="Earliest signal trade date, YYYY-MM-DD.")
    parser.add_argument("--max-date", default="", help="Latest signal trade date, YYYY-MM-DD.")
    parser.add_argument("--show-trades", action="store_true", help="Print every completed backtest trade.")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text summary.")
    return parser.parse_args()


def in_date_range(trade_date, min_date, max_date):
    if min_date and trade_date < min_date:
        return False
    if max_date and trade_date > max_date:
        return False
    return True


def backtest_stock(stock, prices, hold_days, success_threshold, min_date, max_date):
    signals = calculate_historical_signals(stock, prices)
    price_index_by_date = {item["trade_date"]: index for index, item in enumerate(prices)}
    trades = []
    open_count = 0

    for signal in signals:
        if not in_date_range(signal["trade_date"], min_date, max_date):
            continue

        entry_index = price_index_by_date.get(signal["trade_date"])
        if entry_index is None:
            continue

        exit_index = entry_index + hold_days
        if exit_index >= len(prices):
            open_count += 1
            continue

        entry_close = signal["close"]
        exit_price = prices[exit_index]["close_price"]
        return_pct = (exit_price - entry_close) / entry_close * 100 if entry_close != 0 else 0
        trades.append(
            {
                "symbol": signal["symbol"],
                "name": signal["name"],
                "entry_trade_date": signal["trade_date"],
                "exit_trade_date": prices[exit_index]["trade_date"],
                "entry_close": entry_close,
                "exit_close": exit_price,
                "hold_days": hold_days,
                "return_pct": return_pct,
                "success": return_pct > success_threshold,
                "zxt": signal["zxt"],
                "pct_change": signal["pct_change"],
            }
        )

    return trades, open_count


def build_summary(trades, open_count):
    trade_count = len(trades)
    win_count = sum(1 for item in trades if item["success"])
    total_return = sum(item["return_pct"] for item in trades)
    return {
        "completed_count": trade_count,
        "open_count": open_count,
        "signal_count": trade_count + open_count,
        "win_count": win_count,
        "win_rate": win_count / trade_count * 100 if trade_count > 0 else 0,
        "avg_return_pct": total_return / trade_count if trade_count > 0 else 0,
    }


def run_backtest(stocks, hold_days, success_threshold, min_date, max_date):
    trades = []
    open_count = 0
    for stock in stocks:
        stock_trades, stock_open_count = backtest_stock(
            stock,
            get_prices(stock["symbol"]),
            hold_days,
            success_threshold,
            min_date,
            max_date,
        )
        trades.extend(stock_trades)
        open_count += stock_open_count

    trades.sort(key=lambda item: (item["entry_trade_date"], item["symbol"]))
    return {
        "summary": build_summary(trades, open_count),
        "trades": trades,
    }


def format_number(value):
    return f"{value:.3f}"


def yes_no(value):
    return "是" if value else "否"


def print_summary(result):
    summary = result["summary"]
    print(
        "信号数: {signal_count}, 已完成: {completed_count}, 未到持有期: {open_count}, "
        "成功: {win_count}, 胜率: {win_rate:.2f}%, 平均收益: {avg_return_pct:.3f}%".format(**summary)
    )


def print_trades(trades):
    if not trades:
        print("没有可回测的 ZXT 反转信号。")
        return

    print(f"{'代码':<8}{'名称':<12}{'买入日':<14}{'卖出日':<14}{'买入价':>10}{'卖出价':>10}{'收益%':>10}{'成功':>6}")
    for item in trades:
        print(
            f"{item['symbol']:<8}{item['name']:<12}{item['entry_trade_date']:<14}{item['exit_trade_date']:<14}"
            f"{format_number(item['entry_close']):>10}{format_number(item['exit_close']):>10}"
            f"{format_number(item['return_pct']):>10}{yes_no(item['success']):>6}"
        )


def main():
    args = parse_args()
    init_db()
    result = run_backtest(
        selected_stocks(args.symbols, args.limit),
        max(1, args.hold_days),
        args.success_threshold,
        args.min_date,
        args.max_date,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_summary(result)
        if args.show_trades:
            print_trades(result["trades"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
