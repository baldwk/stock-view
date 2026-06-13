# @(#)akshare_client.py, June 3, 2026.
# <p/>
# Copyright 2026 fenbi.com. All rights reserved.
# FENBI.COM PROPRIETARY/CONFIDENTIAL. Use is subject to license terms.
#
# @Author: wukeyu
# @Date: 2026/6/3 12:47

import logging
import random
import time
from datetime import date, datetime

import akshare as ak
import pandas as pd
import requests


SSE_PREFIXES = ("600", "601", "603", "605", "688", "689")
SZSE_PREFIXES = ("000", "001", "002", "003", "300", "301")


def is_sse_or_szse_symbol(symbol):
    return symbol.startswith(SSE_PREFIXES) or symbol.startswith(SZSE_PREFIXES)


def normalize_exchange_symbol(symbol):
    normalized_symbol = str(symbol).split(".")[0].strip().lower()
    if normalized_symbol.startswith(("sh", "sz", "bj")):
        normalized_symbol = normalized_symbol[2:]
    return normalized_symbol.zfill(6)


def fetch_sse_szse_stocks():
    logging.info("Fetching SSE/SZSE stock list from AkShare spot API")
    df = ak.stock_zh_a_spot()
    if df.empty:
        return []

    columns = list(df.columns)
    code_col = "code" if "code" in df.columns else "代码" if "代码" in df.columns else columns[0]
    name_col = "name" if "name" in df.columns else "名称" if "名称" in df.columns else columns[1]

    stocks = []
    for _, row in df.iterrows():
        symbol = normalize_exchange_symbol(row[code_col])
        if is_sse_or_szse_symbol(symbol):
            stocks.append({"symbol": symbol, "name": str(row[name_col])})

    logging.info("Fetched %s spot rows, selected %s SSE/SZSE stocks", len(df), len(stocks))
    return stocks


def fetch_tencent_market_cap_batch(stocks, retries, retry_wait):
    query_symbols = ",".join(to_tencent_symbol(stock["symbol"]) for stock in stocks)
    retry_count = max(1, retries)
    for attempt in range(1, retry_count + 1):
        try:
            response = requests.get(f"https://qt.gtimg.cn/q={query_symbols}", timeout=15)
            response.raise_for_status()
            return response.content.decode("gbk", errors="ignore")
        except Exception:
            if attempt >= retry_count:
                raise

            wait_seconds = retry_wait * attempt + random.uniform(0, 1)
            logging.warning(
                "Fetch Tencent market cap batch failed, retrying in %.1fs (%s/%s)",
                wait_seconds,
                attempt,
                retry_count,
            )
            time.sleep(wait_seconds)


def parse_float(value):
    parsed_value = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed_value):
        return None
    return float(parsed_value)


def parse_tencent_market_caps(text, stock_names):
    market_caps = []
    for line in text.splitlines():
        if '="' not in line:
            continue

        fields = line.split('="', 1)[1].rsplit('"', 1)[0].split("~")
        if len(fields) <= 45:
            continue

        symbol = str(fields[2]).zfill(6)
        if not is_sse_or_szse_symbol(symbol):
            continue

        market_cap_yi = pd.to_numeric(fields[45], errors="coerce")
        if pd.isna(market_cap_yi) or float(market_cap_yi) <= 0:
            continue

        market_caps.append(
            {
                "symbol": symbol,
                "name": stock_names.get(symbol, fields[1]),
                "market_cap": float(market_cap_yi) * 100000000,
            }
        )
    return market_caps


def parse_tencent_realtime_quotes(text, stock_names):
    quotes = []
    for line in text.splitlines():
        if '="' not in line:
            continue

        fields = line.split('="', 1)[1].rsplit('"', 1)[0].split("~")
        if len(fields) <= 37:
            continue

        symbol = str(fields[2]).zfill(6)
        if not is_sse_or_szse_symbol(symbol):
            continue

        close_price = parse_float(fields[3])
        open_price = parse_float(fields[5])
        high_price = parse_float(fields[33])
        low_price = parse_float(fields[34])
        volume = parse_float(fields[36])
        if volume is None:
            volume = parse_float(fields[6])
        if close_price is None or high_price is None or low_price is None:
            continue

        trade_date = date.today().isoformat()
        if len(fields) > 30 and len(fields[30]) >= 8 and fields[30][:8].isdigit():
            trade_date = datetime.strptime(fields[30][:8], "%Y%m%d").date().isoformat()

        quotes.append(
            {
                "symbol": symbol,
                "name": stock_names.get(symbol, fields[1]),
                "trade_date": trade_date,
                "open_price": open_price if open_price is not None else close_price,
                "close_price": close_price,
                "high_price": high_price,
                "low_price": low_price,
                "volume": volume,
            }
        )
    return quotes


def fetch_sse_szse_market_caps_from_tencent(stocks=None, retries=5, retry_wait=2.0, batch_size=60):
    target_stocks = stocks if stocks is not None else fetch_sse_szse_stocks()
    stock_names = {stock["symbol"]: stock["name"] for stock in target_stocks}
    market_caps = []
    for start in range(0, len(target_stocks), batch_size):
        batch = target_stocks[start : start + batch_size]
        try:
            text = fetch_tencent_market_cap_batch(batch, retries, retry_wait)
            market_caps.extend(parse_tencent_market_caps(text, stock_names))
        except Exception:
            logging.warning("Failed to fetch Tencent market cap batch, skipped", exc_info=True)
    return market_caps


def fetch_realtime_quotes_from_tencent(stocks, retries=5, retry_wait=2.0, batch_size=60):
    stock_names = {stock["symbol"]: stock["name"] for stock in stocks}
    quotes = []
    for start in range(0, len(stocks), batch_size):
        batch = stocks[start : start + batch_size]
        try:
            text = fetch_tencent_market_cap_batch(batch, retries, retry_wait)
            quotes.extend(parse_tencent_realtime_quotes(text, stock_names))
        except Exception:
            logging.warning("Failed to fetch Tencent realtime quote batch, skipped", exc_info=True)
    return quotes


def fetch_sse_szse_market_caps(stocks=None, retries=5, retry_wait=2.0):
    return fetch_sse_szse_market_caps_from_tencent(stocks=stocks, retries=retries, retry_wait=retry_wait)


def to_tencent_symbol(symbol):
    if symbol.startswith(SSE_PREFIXES):
        return f"sh{symbol}"
    if symbol.startswith(SZSE_PREFIXES):
        return f"sz{symbol}"
    raise ValueError(f"Unsupported SSE/SZSE stock symbol for Tencent source: {symbol}")


def resolve_column(df, candidates, symbol):
    for column in candidates:
        if column in df.columns:
            return column
    raise ValueError(f"AkShare response missing required columns for {symbol}: {candidates}")


def resolve_optional_column(df, candidates):
    for column in candidates:
        if column in df.columns:
            return column
    return None


def normalize_price_rows(df, symbol):
    if df.empty:
        return []

    date_col = resolve_column(df, ("date", "日期"), symbol)
    open_col = resolve_optional_column(df, ("open", "开盘"))
    close_col = resolve_column(df, ("close", "收盘"), symbol)
    high_col = resolve_column(df, ("high", "最高"), symbol)
    low_col = resolve_column(df, ("low", "最低"), symbol)
    volume_col = resolve_optional_column(df, ("amount", "volume", "成交量"))

    selected_columns = [date_col, close_col, high_col, low_col]
    if open_col:
        selected_columns.append(open_col)
    if volume_col:
        selected_columns.append(volume_col)

    df = df[selected_columns].dropna(subset=[date_col, close_col, high_col, low_col])
    df[date_col] = pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d")

    prices = []
    for _, row in df.iterrows():
        close_price = float(row[close_col])
        open_price = float(row[open_col]) if open_col else close_price
        prices.append(
            {
                "trade_date": row[date_col],
                "open_price": open_price,
                "close_price": close_price,
                "high_price": float(row[high_col]),
                "low_price": float(row[low_col]),
                "volume": float(row[volume_col]) if volume_col else None,
            }
        )
    return prices


def fetch_daily_closes_from_tencent(symbol, start_date, end_date, timeout):
    return ak.stock_zh_a_hist_tx(
        symbol=to_tencent_symbol(symbol),
        start_date=start_date.strftime("%Y%m%d"),
        end_date=end_date.strftime("%Y%m%d"),
        adjust="",
        timeout=timeout,
    )


def fetch_daily_closes(symbol, start_date, end_date, retries=5, retry_wait=2.0, timeout=15):
    df = None
    retry_count = max(1, retries)
    for attempt in range(1, retry_count + 1):
        try:
            df = fetch_daily_closes_from_tencent(symbol, start_date, end_date, timeout)
            break
        except Exception:
            if attempt >= retry_count:
                raise

            wait_seconds = retry_wait * attempt + random.uniform(0, 1)
            logging.warning(
                "Fetch %s from Tencent failed, retrying in %.1fs (%s/%s)",
                symbol,
                wait_seconds,
                attempt,
                retry_count,
            )
            time.sleep(wait_seconds)

    return normalize_price_rows(df, symbol)
