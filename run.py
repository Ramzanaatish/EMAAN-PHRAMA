#!/usr/bin/env python3
"""Launch Pharma Purchase Assistant.

Run from the project folder:
    python run.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import main

if __name__ == "__main__":
    raise SystemExit(main())
