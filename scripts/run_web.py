# @(#)run_web.py, June 13, 2026.
# <p/>
# Copyright 2026 fenbi.com. All rights reserved.
# FENBI.COM PROPRIETARY/CONFIDENTIAL. Use is subject to license terms.
#
# @Author: wukeyu
# @Date: 2026/6/13 20:01

import os
import sys
from pathlib import Path

from waitress import serve


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app import app


def main():
    host = os.environ.get("STOCK_VIEW_HOST", "0.0.0.0")
    port = int(os.environ.get("STOCK_VIEW_PORT", "5000"))
    threads = int(os.environ.get("STOCK_VIEW_WEB_THREADS", "8"))
    serve(app, host=host, port=port, threads=threads)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
