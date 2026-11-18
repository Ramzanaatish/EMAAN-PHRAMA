#!/usr/bin/env python3
"""Run the Pharma Purchase Assistant live-data server.

Serves the dashboard HTML at http://localhost:8080/ and a JSON API the
page uses for live POS_DB data. Run it on the same PC that runs SmilePOS
(the server and SmilePOS share localhost\\SQLEXPRESS, read-only).

    python server.py            (port 8080)
    python server.py --port 8090
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.web import create_app


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pharma Purchase Assistant live-data server."
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Bind address (default 127.0.0.1)."
    )
    parser.add_argument("--port", type=int, default=8080, help="Port (default 8080).")
    args = parser.parse_args()
    app = create_app()
    print("Pharma Purchase Assistant — live-data server")
    print(f"Dashboard: http://{args.host}:{args.port}/")
    print("Press Ctrl+C to stop.")
    app.run(host=args.host, port=args.port, debug=False, use_reloader=False, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
