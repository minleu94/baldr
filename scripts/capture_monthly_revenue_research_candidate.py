"""Create a bounded candidate-only monthly revenue snapshot from official APIs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_module.monthly_revenue_research_candidate import (
    capture_monthly_revenue_research_candidate,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Capture one bounded full-market TWSE/TPEx monthly revenue research "
            "candidate under the repository output root. This command never "
            "writes formal availability data or the formal SQLite database."
        )
    )
    parser.parse_args(argv)
    try:
        result = capture_monthly_revenue_research_candidate()
    except (OSError, RuntimeError, ValueError) as exc:
        result = {
            "status": "rejected",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "writes_formal_data": False,
            "writes_formal_database": False,
            "formal_apply_authorized": False,
        }
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return 0 if result.get("status") == "captured" else 2


if __name__ == "__main__":
    raise SystemExit(main())
