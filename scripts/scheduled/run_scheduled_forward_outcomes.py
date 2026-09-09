from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.scheduled_forward_outcome_service import (  # noqa: E402
    DEFAULT_LOOKBACK_CALENDAR_DAYS,
    DEFAULT_MAX_EVENTS,
    DEFAULT_WINDOWS,
    run_scheduled_forward_outcomes,
)
from data_module.config import TWStockConfig  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the bounded daily forward research outcome producer."
    )
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument(
        "--allow-production-db-confirm",
        action="store_true",
        help="Required when --confirm targets the resolved TWStockConfig production DB.",
    )
    parser.add_argument("--windows", default=",".join(str(value) for value in DEFAULT_WINDOWS))
    parser.add_argument("--lookback-calendar-days", type=int, default=DEFAULT_LOOKBACK_CALENDAR_DAYS)
    parser.add_argument("--max-events", type=int, default=DEFAULT_MAX_EVENTS)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--data-as-of-date", default=None)
    parser.add_argument("--event-type", default=None)
    parser.add_argument("--symbol", default=None)
    return parser


def _parse_windows(value: str) -> tuple[int, ...]:
    return tuple(int(item.strip()) for item in value.split(",") if item.strip())


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_kwargs = {}
    if args.data_root is not None:
        config_kwargs["data_root"] = args.data_root
    if args.output_root is not None:
        config_kwargs["output_root"] = args.output_root
    config = TWStockConfig(**config_kwargs)
    result = run_scheduled_forward_outcomes(
        config=config,
        db_path=args.db_path,
        output_root=args.output_root,
        confirm=args.confirm,
        allow_production_db_confirm=args.allow_production_db_confirm,
        windows=_parse_windows(args.windows),
        lookback_calendar_days=args.lookback_calendar_days,
        max_events=args.max_events,
        start_date=args.start_date,
        end_date=args.end_date,
        data_as_of_date=args.data_as_of_date,
        event_type=args.event_type,
        symbol=args.symbol,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return int(result.get("exit_code", 2))


if __name__ == "__main__":
    raise SystemExit(main())
