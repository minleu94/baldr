#!/usr/bin/env python3
"""CLI wrapper for a verified research numeric artifact.

It preserves source clocks and values while leaving Direct/OOC readiness blocked
until verified market context and mature labels are available.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repository root is on sys.path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from data_module.ml_research_direct_ooc_adapter import main

if __name__ == "__main__":
    raise SystemExit(main())
