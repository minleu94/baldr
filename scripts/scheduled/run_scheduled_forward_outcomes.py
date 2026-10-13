from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_CALENDAR_CACHE_PATH = (
    ROOT / "output" / "paper_execution_eod_replay" / "calendar_cache"
)

from app_module.scheduled_forward_outcome_service import (  # noqa: E402
    DEFAULT_LOOKBACK_CALENDAR_DAYS,
    DEFAULT_MAX_EVENTS,
    DEFAULT_WINDOWS,
    SCHEDULED_WRITER_RESERVATION_TIMEOUT_SECONDS,
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
    parser.add_argument("--reservation-wait-seconds", type=int, default=SCHEDULED_WRITER_RESERVATION_TIMEOUT_SECONDS,
                        help="手動重跑的共用鎖等待秒數，1..10500；不跳過鎖或寫入資格。")
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
    parser.add_argument(
        "--calendar-cache-path",
        type=Path,
        default=DEFAULT_CALENDAR_CACHE_PATH,
        help="唯讀官方 TWSE 年度 calendar cache 根目錄或檔案。",
    )
    parser.add_argument(
        "--temporary-closure-path",
        type=Path,
        default=None,
        help="可選的唯讀官方臨時休市 cache 根目錄或檔案。",
    )
    parser.add_argument(
        "--require-cohort-identity",
        action="store_true",
        help="Skip events without explicit V4 strategy/cost/benchmark/universe/horizon identity.",
    )
    return parser


def _parse_windows(value: str) -> tuple[int, ...]:
    return tuple(int(item.strip()) for item in value.split(",") if item.strip())


def main(argv: list[str] | None = None) -> int:
    _configure_utf8()
    args = build_parser().parse_args(argv)
    config_kwargs = {}
    if args.data_root is not None:
        config_kwargs["data_root"] = args.data_root
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
        require_cohort_identity=args.require_cohort_identity,
        calendar_cache_path=args.calendar_cache_path,
        temporary_closure_path=args.temporary_closure_path,
        reservation_wait_seconds=args.reservation_wait_seconds,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return int(result.get("exit_code", 2))


def _configure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (OSError, ValueError):
                pass


if __name__ == "__main__":
    raise SystemExit(main())
