# @(#)data_source.py, June 3, 2026.
# <p/>
# Copyright 2026 fenbi.com. All rights reserved.
# FENBI.COM PROPRIETARY/CONFIDENTIAL. Use is subject to license terms.
#
# @Author: wukeyu
# @Date: 2026/6/3 13:19

import os

from akshare_client import (
    fetch_daily_closes,
    fetch_realtime_quotes_from_tencent,
    fetch_sse_szse_market_caps,
    fetch_sse_szse_stocks,
)


class AkShareDataSource:
    name = "akshare"

    def __init__(self):
        self.name = "akshare:tencent"

    def list_stocks(self):
        return fetch_sse_szse_stocks()

    def fetch_market_caps(self, stocks=None, retries=5, retry_wait=2.0):
        return fetch_sse_szse_market_caps(
            stocks=stocks,
            retries=retries,
            retry_wait=retry_wait,
        )

    def fetch_daily_closes(self, symbol, start_date, end_date, retries=5, retry_wait=2.0, timeout=15):
        return fetch_daily_closes(
            symbol,
            start_date,
            end_date,
            retries=retries,
            retry_wait=retry_wait,
            timeout=timeout,
        )

    def fetch_realtime_quotes(self, stocks, retries=5, retry_wait=2.0):
        return fetch_realtime_quotes_from_tencent(stocks, retries=retries, retry_wait=retry_wait)


DATA_SOURCES = {
    AkShareDataSource.name: AkShareDataSource,
}


def get_data_source():
    source_name = os.environ.get("STOCK_VIEW_DATA_SOURCE", AkShareDataSource.name).lower()
    source_cls = DATA_SOURCES.get(source_name)
    if source_cls is None:
        supported_sources = ", ".join(sorted(DATA_SOURCES))
        raise ValueError(f"Unsupported data source {source_name}, supported: {supported_sources}")
    return source_cls()
