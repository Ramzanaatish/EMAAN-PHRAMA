#!/usr/bin/env python3
"""Run the Pharma Purchase Assistant live-data server.

Serves the dashboard HTML at http://localhost:5000/ and a JSON API the
page uses for live POS_DB data. Run it on the same PC that runs SmilePOS
(the server and SmilePOS share localhost\\SQLEXPRESS, read-only).

The standalone HTML file (Pharma-Purchase-Assistant.html, opened with a
double-click as file://) calls this server at http://127.0.0.1:5000 —
that is why the default port is 5000 and the server answers CORS.

    python server.py            (port 5000)
    python server.py --port 8090
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.web import create_app


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5000


def build_parser() -> argparse.ArgumentParser:
    """CLI parser (kept separate so tests can check the defaults)."""
    parser = argparse.ArgumentParser(
        description="Pharma Purchase Assistant live-data server."
    )
    parser.add_argument(
        "--host", default=DEFAULT_HOST, help="Bind address (default 127.0.0.1)."
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help="Port (default 5000)."
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    app = create_app()
    print("Pharma Purchase Assistant — live-data server")
    print(f"Dashboard: http://{args.host}:{args.port}/")
    print("Press Ctrl+C to stop.")
    app.run(host=args.host, port=args.port, debug=False, use_reloader=False, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
