# @(#)database.py, June 3, 2026.
# <p/>
# Copyright 2026 fenbi.com. All rights reserved.
# FENBI.COM PROPRIETARY/CONFIDENTIAL. Use is subject to license terms.
#
# @Author: wukeyu
# @Date: 2026/6/3 12:47

import os
import sqlite3
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("STOCK_VIEW_DB", BASE_DIR / "data" / "stock_view.sqlite3"))


SCHEMA = """
CREATE TABLE IF NOT EXISTS stocks (
    symbol TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    market_cap REAL,
    market_cap_updated_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_prices (
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    open_price REAL,
    close_price REAL NOT NULL,
    high_price REAL,
    low_price REAL,
    volume REAL,
    price_updated_at TEXT,
    PRIMARY KEY (symbol, trade_date),
    FOREIGN KEY (symbol) REFERENCES stocks(symbol) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_daily_prices_symbol_date
ON daily_prices(symbol, trade_date);

CREATE TABLE IF NOT EXISTS zxt_reversal_results (
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    close_price REAL NOT NULL,
    zxt REAL NOT NULL,
    zxt_prev REAL NOT NULL,
    red_body REAL NOT NULL,
    green_body_yest REAL NOT NULL,
    pct_change REAL NOT NULL,
    yl REAL NOT NULL,
    today_red INTEGER NOT NULL,
    pre_3_green INTEGER NOT NULL,
    body_ok INTEGER NOT NULL,
    pct_ok INTEGER NOT NULL,
    on_yl INTEGER NOT NULL,
    xg INTEGER NOT NULL,
    screened_at TEXT NOT NULL,
    PRIMARY KEY (symbol, trade_date),
    FOREIGN KEY (symbol) REFERENCES stocks(symbol) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_zxt_reversal_results_trade_date
ON zxt_reversal_results(trade_date);

CREATE TABLE IF NOT EXISTS zxt_reversal_screen_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_type TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    source TEXT NOT NULL,
    item_count INTEGER NOT NULL,
    screened_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_zxt_reversal_screen_runs_type_date
ON zxt_reversal_screen_runs(run_type, trade_date, screened_at);

CREATE TABLE IF NOT EXISTS zxt_reversal_screen_results (
    run_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    close_price REAL NOT NULL,
    zxt REAL NOT NULL,
    zxt_prev REAL NOT NULL,
    red_body REAL NOT NULL,
    green_body_yest REAL NOT NULL,
    pct_change REAL NOT NULL,
    yl REAL NOT NULL,
    today_red INTEGER NOT NULL,
    pre_3_green INTEGER NOT NULL,
    body_ok INTEGER NOT NULL,
    pct_ok INTEGER NOT NULL,
    on_yl INTEGER NOT NULL,
    xg INTEGER NOT NULL,
    PRIMARY KEY (run_id, symbol),
    FOREIGN KEY (run_id) REFERENCES zxt_reversal_screen_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY (symbol) REFERENCES stocks(symbol) ON DELETE CASCADE
);
"""


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        ensure_stock_columns(conn)
        ensure_daily_price_columns(conn)


def ensure_stock_columns(conn):
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(stocks)").fetchall()}
    if "market_cap" not in columns:
        conn.execute("ALTER TABLE stocks ADD COLUMN market_cap REAL")
    if "market_cap_updated_at" not in columns:
        conn.execute("ALTER TABLE stocks ADD COLUMN market_cap_updated_at TEXT")


def ensure_daily_price_columns(conn):
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(daily_prices)").fetchall()}
    if "open_price" not in columns:
        conn.execute("ALTER TABLE daily_prices ADD COLUMN open_price REAL")
    if "high_price" not in columns:
        conn.execute("ALTER TABLE daily_prices ADD COLUMN high_price REAL")
    if "low_price" not in columns:
        conn.execute("ALTER TABLE daily_prices ADD COLUMN low_price REAL")
    if "volume" not in columns:
        conn.execute("ALTER TABLE daily_prices ADD COLUMN volume REAL")
    if "price_updated_at" not in columns:
        conn.execute("ALTER TABLE daily_prices ADD COLUMN price_updated_at TEXT")


def upsert_stock(symbol, name):
    updated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO stocks(symbol, name, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                name = excluded.name,
                updated_at = excluded.updated_at
            """,
            (symbol, name, updated_at),
        )


def upsert_stocks(stocks):
    if not stocks:
        return 0

    updated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    rows = [(item["symbol"], item["name"], updated_at) for item in stocks]
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO stocks(symbol, name, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                name = excluded.name,
                updated_at = excluded.updated_at
            """,
            rows,
        )
    return len(rows)


def upsert_market_caps(market_caps):
    if not market_caps:
        return 0

    updated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    rows = [
        (
            item["symbol"],
            item.get("name", item["symbol"]),
            item["market_cap"],
            updated_at,
            updated_at,
        )
        for item in market_caps
    ]
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO stocks(symbol, name, market_cap, market_cap_updated_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                name = excluded.name,
                market_cap = excluded.market_cap,
                market_cap_updated_at = excluded.market_cap_updated_at,
                updated_at = excluded.updated_at
            """,
            rows,
        )
    return len(rows)


def upsert_prices(symbol, prices):
    if not prices:
        return 0

    price_updated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    rows = [
        (
            symbol,
            item["trade_date"],
            item.get("open_price"),
            item["close_price"],
            item.get("high_price"),
            item.get("low_price"),
            item.get("volume"),
            price_updated_at,
        )
        for item in prices
    ]
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO daily_prices(
                symbol,
                trade_date,
                open_price,
                close_price,
                high_price,
                low_price,
                volume,
                price_updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, trade_date) DO UPDATE SET
                open_price = excluded.open_price,
                close_price = excluded.close_price,
                high_price = excluded.high_price,
                low_price = excluded.low_price,
                volume = excluded.volume,
                price_updated_at = excluded.price_updated_at
            """,
            rows,
        )
    return len(rows)


def upsert_zxt_reversal_results(results):
    if not results:
        return 0

    screened_at = datetime.now().astimezone().isoformat(timespec="seconds")
    rows = [
        (
            item["symbol"],
            item["name"],
            item["trade_date"],
            item["close"],
            item["zxt"],
            item["zxt_prev"],
            item["red_body"],
            item["green_body_yest"],
            item["pct_change"],
            item["yl"],
            int(item["today_red"]),
            int(item["pre_3_green"]),
            int(item["body_ok"]),
            int(item["pct_ok"]),
            int(item["on_yl"]),
            int(item["xg"]),
            screened_at,
        )
        for item in results
    ]
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO zxt_reversal_results(
                symbol,
                name,
                trade_date,
                close_price,
                zxt,
                zxt_prev,
                red_body,
                green_body_yest,
                pct_change,
                yl,
                today_red,
                pre_3_green,
                body_ok,
                pct_ok,
                on_yl,
                xg,
                screened_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, trade_date) DO UPDATE SET
                name = excluded.name,
                close_price = excluded.close_price,
                zxt = excluded.zxt,
                zxt_prev = excluded.zxt_prev,
                red_body = excluded.red_body,
                green_body_yest = excluded.green_body_yest,
                pct_change = excluded.pct_change,
                yl = excluded.yl,
                today_red = excluded.today_red,
                pre_3_green = excluded.pre_3_green,
                body_ok = excluded.body_ok,
                pct_ok = excluded.pct_ok,
                on_yl = excluded.on_yl,
                xg = excluded.xg,
                screened_at = excluded.screened_at
            """,
            rows,
        )
    return len(rows)


def save_zxt_reversal_screen_run(results, run_type, trade_date=None, source="daily"):
    screened_at = datetime.now().astimezone().isoformat(timespec="seconds")
    resolved_trade_date = trade_date
    if not resolved_trade_date and results:
        resolved_trade_date = max(item["trade_date"] for item in results)
    if not resolved_trade_date:
        resolved_trade_date = datetime.now().astimezone().date().isoformat()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO zxt_reversal_screen_runs(run_type, trade_date, source, item_count, screened_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_type, resolved_trade_date, source, len(results), screened_at),
        )
        run_id = cursor.lastrowid
        if results:
            rows = [
                (
                    run_id,
                    item["symbol"],
                    item["name"],
                    item["trade_date"],
                    item["close"],
                    item["zxt"],
                    item["zxt_prev"],
                    item["red_body"],
                    item["green_body_yest"],
                    item["pct_change"],
                    item["yl"],
                    int(item["today_red"]),
                    int(item["pre_3_green"]),
                    int(item["body_ok"]),
                    int(item["pct_ok"]),
                    int(item["on_yl"]),
                    int(item["xg"]),
                )
                for item in results
            ]
            conn.executemany(
                """
                INSERT INTO zxt_reversal_screen_results(
                    run_id,
                    symbol,
                    name,
                    trade_date,
                    close_price,
                    zxt,
                    zxt_prev,
                    red_body,
                    green_body_yest,
                    pct_change,
                    yl,
                    today_red,
                    pre_3_green,
                    body_ok,
                    pct_ok,
                    on_yl,
                    xg
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
    return run_id


def get_latest_zxt_reversal_screen_run(run_type=None, trade_date=None):
    params = []
    clauses = []
    if run_type:
        clauses.append("run_type = ?")
        params.append(run_type)
    if trade_date:
        clauses.append("trade_date = ?")
        params.append(trade_date)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_connection() as conn:
        row = conn.execute(
            f"""
            SELECT run_id, run_type, trade_date, source, item_count, screened_at
            FROM zxt_reversal_screen_runs
            {where_sql}
            ORDER BY screened_at DESC, run_id DESC
            LIMIT 1
            """,
            params,
        ).fetchone()

    if row is None:
        return None
    return dict(row)


def list_zxt_reversal_screen_results(run_id, limit=50):
    params = [run_id]
    limit_sql = ""
    if limit > 0:
        limit_sql = "LIMIT ?"
        params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                symbol,
                name,
                trade_date,
                close_price AS close,
                zxt,
                zxt_prev,
                red_body,
                green_body_yest,
                pct_change,
                yl,
                today_red,
                pre_3_green,
                body_ok,
                pct_ok,
                on_yl,
                xg
            FROM zxt_reversal_screen_results
            WHERE run_id = ?
            ORDER BY xg DESC, symbol
            {limit_sql}
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def list_stocks():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                s.symbol,
                s.name,
                s.market_cap,
                s.market_cap_updated_at,
                s.updated_at,
                COUNT(p.trade_date) AS price_count,
                MIN(p.trade_date) AS start_date,
                MAX(p.trade_date) AS end_date,
                MAX(p.price_updated_at) AS price_updated_at
            FROM stocks s
            LEFT JOIN daily_prices p ON p.symbol = s.symbol
            GROUP BY s.symbol, s.name, s.market_cap, s.market_cap_updated_at, s.updated_at
            ORDER BY s.symbol
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_data_pull_status(update_date=None):
    resolved_update_date = update_date or datetime.now().astimezone().date().isoformat()
    with get_connection() as conn:
        summary = conn.execute(
            """
            SELECT
                COUNT(s.symbol) AS total_stocks,
                COALESCE(SUM(CASE WHEN price_stats.price_count > 0 THEN 1 ELSE 0 END), 0) AS stocks_with_prices,
                COALESCE(SUM(CASE WHEN price_stats.price_count IS NULL THEN 1 ELSE 0 END), 0) AS stocks_without_prices,
                COALESCE(SUM(price_stats.price_count), 0) AS daily_price_rows,
                MIN(price_stats.start_date) AS start_date,
                MAX(price_stats.end_date) AS end_date,
                COALESCE(MAX(price_stats.price_count), 0) AS max_price_count
            FROM stocks s
            LEFT JOIN (
                SELECT
                    symbol,
                    COUNT(*) AS price_count,
                    MIN(trade_date) AS start_date,
                    MAX(trade_date) AS end_date
                FROM daily_prices
                GROUP BY symbol
            ) price_stats ON price_stats.symbol = s.symbol
            """
        ).fetchone()
        update_summary = conn.execute(
            """
            SELECT
                COUNT(DISTINCT symbol) AS updated_stocks,
                COUNT(*) AS updated_rows,
                MIN(trade_date) AS updated_start_date,
                MAX(trade_date) AS updated_end_date,
                MIN(price_updated_at) AS first_updated_at,
                MAX(price_updated_at) AS last_updated_at
            FROM daily_prices
            WHERE substr(price_updated_at, 1, 10) = ?
            """,
            (resolved_update_date,),
        ).fetchone()
        buckets = conn.execute(
            """
            SELECT
                SUM(CASE WHEN price_count = 0 THEN 1 ELSE 0 END) AS no_data,
                SUM(CASE WHEN price_count > 0 AND price_count < 100 THEN 1 ELSE 0 END) AS under_100,
                SUM(CASE WHEN price_count >= 100 AND price_count < 1000 THEN 1 ELSE 0 END) AS under_1000,
                SUM(CASE WHEN price_count >= 1000 THEN 1 ELSE 0 END) AS over_1000
            FROM (
                SELECT s.symbol, COUNT(p.trade_date) AS price_count
                FROM stocks s
                LEFT JOIN daily_prices p ON p.symbol = s.symbol
                GROUP BY s.symbol
            )
            """
        ).fetchone()
        loaded_samples = conn.execute(
            """
            SELECT
                s.symbol,
                s.name,
                COUNT(p.trade_date) AS price_count,
                MIN(p.trade_date) AS start_date,
                MAX(p.trade_date) AS end_date
            FROM stocks s
            JOIN daily_prices p ON p.symbol = s.symbol
            GROUP BY s.symbol, s.name
            ORDER BY s.symbol DESC
            LIMIT 12
            """
        ).fetchall()
        pending_samples = conn.execute(
            """
            SELECT s.symbol, s.name
            FROM stocks s
            LEFT JOIN daily_prices p ON p.symbol = s.symbol
            WHERE p.symbol IS NULL
            GROUP BY s.symbol, s.name
            ORDER BY s.symbol
            LIMIT 12
            """
        ).fetchall()
        updated_samples = conn.execute(
            """
            SELECT
                s.symbol,
                s.name,
                COUNT(p.trade_date) AS updated_rows,
                MIN(p.trade_date) AS start_date,
                MAX(p.trade_date) AS end_date,
                MAX(p.price_updated_at) AS last_updated_at
            FROM stocks s
            JOIN daily_prices p ON p.symbol = s.symbol
            WHERE substr(p.price_updated_at, 1, 10) = ?
            GROUP BY s.symbol, s.name
            ORDER BY last_updated_at DESC, s.symbol
            LIMIT 12
            """,
            (resolved_update_date,),
        ).fetchall()

    result = dict(summary)
    result["update_date"] = resolved_update_date
    result["today_update"] = dict(update_summary)
    result["buckets"] = dict(buckets)
    result["loaded_samples"] = [dict(row) for row in loaded_samples]
    result["pending_samples"] = [dict(row) for row in pending_samples]
    result["updated_samples"] = [dict(row) for row in updated_samples]
    return result


def get_prices(symbol, start_date=None, end_date=None):
    params = [symbol]
    clauses = ["symbol = ?"]

    if start_date:
        clauses.append("trade_date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("trade_date <= ?")
        params.append(end_date)

    sql = f"""
        SELECT trade_date, open_price, close_price, high_price, low_price, volume
        FROM daily_prices
        WHERE {' AND '.join(clauses)}
        ORDER BY trade_date
    """

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def list_stock_price_rows():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                s.symbol,
                s.name,
                s.market_cap,
                p.trade_date,
                p.open_price,
                p.close_price,
                p.high_price,
                p.low_price,
                p.volume
            FROM stocks s
            JOIN daily_prices p ON p.symbol = s.symbol
            ORDER BY s.symbol, p.trade_date
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_last_trade_date(symbol):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT MAX(trade_date) AS trade_date
            FROM daily_prices
            WHERE symbol = ?
            """,
            (symbol,),
        ).fetchone()

    if row is None:
        return None
    return row["trade_date"]
