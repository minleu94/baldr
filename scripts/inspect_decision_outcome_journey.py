"""執行 DecisionOutcomeJourney 的本機 bounded、唯讀 smoke。

這個腳本只讀既有 recommendation JSON、Evidence SQLite、Journal JSONL、
legacy Portfolio trades JSONL 與可選的精確 portfolio ledger。它不建立
目錄／schema、不計算 forward outcome、不回填 identity，也不會把研究
return 宣稱成實際損益。
"""

from __future__ import annotations

import argparse
from collections import Counter
import os
from pathlib import Path
import sys
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app_module.decision_outcome_journey import (
    DecisionOutcomeJourney,
    DecisionOutcomeJourneyService,
    JsonRecommendationReadAdapter,
    project_outcome_maturity,
)


DEFAULT_DATA_ROOT = Path(
    os.environ.get("DATA_ROOT", "D:/Min/Python/Project/FA_Data")
)
DEFAULT_OUTPUT_ROOT = Path(
    os.environ.get("OUTPUT_ROOT", "D:/Min/Python/Project/FA_Data/output")
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect one recommendation result as a read-only journey."
    )
    parser.add_argument("--result-id", help="exact recommendation result_id")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--evidence-db",
        type=Path,
        help="Evidence SQLite；預設為 data-root/sqlite/twstock.db",
    )
    parser.add_argument(
        "--journal-path",
        type=Path,
        help="Journal JSONL；預設為 output-root/portfolio/journal_entries.jsonl",
    )
    parser.add_argument(
        "--portfolio-trades-path",
        type=Path,
        help="legacy Portfolio trades JSONL；預設為 output-root/portfolio/trades.jsonl",
    )
    parser.add_argument(
        "--portfolio-ledger-path",
        type=Path,
        help="可選精確 portfolio ledger SQLite；不存在時維持未連結，不建立檔案",
    )
    parser.add_argument(
        "--query-boundary",
        help="ISO date 或帶 timezone 的 datetime；省略表示讀取目前已存在內容",
    )
    parser.add_argument(
        "--max-evidence-events",
        type=int,
        default=5_000,
        help="bounded evidence page 上限；達上限會標示 has_more／partial",
    )
    parser.add_argument(
        "--shadow-output-root",
        type=Path,
        help="可選 shadow output root；使用同一 result_id 做第二次唯讀 smoke",
    )
    parser.add_argument(
        "--shadow-evidence-db",
        type=Path,
        help="可選 shadow Evidence SQLite；省略時使用 shadow-output-root/sqlite/twstock.db",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_stdio()
    args = build_parser().parse_args(argv)
    data_root = args.data_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    evidence_db = (
        args.evidence_db.expanduser().resolve()
        if args.evidence_db is not None
        else data_root / "sqlite" / "twstock.db"
    )
    journal_path = (
        args.journal_path.expanduser().resolve()
        if args.journal_path is not None
        else output_root / "portfolio" / "journal_entries.jsonl"
    )
    trades_path = (
        args.portfolio_trades_path.expanduser().resolve()
        if args.portfolio_trades_path is not None
        else output_root / "portfolio" / "trades.jsonl"
    )
    ledger_path = _existing_optional_path(args.portfolio_ledger_path)
    if args.portfolio_ledger_path is not None and ledger_path is None:
        print(f"PORTFOLIO_LEDGER=missing:{args.portfolio_ledger_path.expanduser().resolve()}")

    result_reader = JsonRecommendationReadAdapter(output_root)
    result_id = args.result_id or _latest_result_id(result_reader)
    print("READ_ONLY=True")
    print("WRITES_ALLOWED=False")
    print("IDENTITY_FILLING=False")
    print(f"OUTPUT_ROOT={output_root}")
    print(f"EVIDENCE_DB={evidence_db}")
    print(f"QUERY_BOUNDARY={args.query_boundary or '<none>'}")
    if result_id is None:
        print("RESULT=missing:no recommendation JSON result was found")
        return 1

    paths = [output_root, evidence_db, journal_path, trades_path]
    before = _path_stat_snapshot(paths)
    service = DecisionOutcomeJourneyService.from_paths(
        output_root=output_root,
        evidence_db_path=evidence_db,
        journal_path=journal_path,
        portfolio_ledger_path=ledger_path,
        portfolio_trades_path=trades_path,
        max_evidence_events=args.max_evidence_events,
    )
    journey = service.build(result_id, query_boundary=args.query_boundary)
    after = _path_stat_snapshot(paths)
    _print_journey("official", journey)
    print(f"SOURCE_STAT_UNCHANGED={before == after}")
    if before != after:
        print("READ_ONLY_ERROR=source file stat changed during smoke")

    if args.shadow_output_root is not None:
        shadow_output = args.shadow_output_root.expanduser().resolve()
        shadow_evidence = (
            args.shadow_evidence_db.expanduser().resolve()
            if args.shadow_evidence_db is not None
            else shadow_output / "sqlite" / "twstock.db"
        )
        shadow_journal = shadow_output / "portfolio" / "journal_entries.jsonl"
        shadow_trades = shadow_output / "portfolio" / "trades.jsonl"
        shadow_before = _path_stat_snapshot(
            [shadow_output, shadow_evidence, shadow_journal, shadow_trades]
        )
        shadow_service = DecisionOutcomeJourneyService.from_paths(
            output_root=shadow_output,
            evidence_db_path=shadow_evidence,
            journal_path=shadow_journal,
            portfolio_trades_path=shadow_trades,
            max_evidence_events=args.max_evidence_events,
        )
        shadow_journey = shadow_service.build(
            result_id,
            query_boundary=args.query_boundary,
        )
        _print_journey("shadow", shadow_journey)
        shadow_after = _path_stat_snapshot(
            [shadow_output, shadow_evidence, shadow_journal, shadow_trades]
        )
        print(f"SHADOW_SOURCE_STAT_UNCHANGED={shadow_before == shadow_after}")

    return 0 if before == after else 2


def _configure_utf8_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def _latest_result_id(reader: JsonRecommendationReadAdapter) -> str | None:
    result_ids = reader.list_result_ids()
    return result_ids[-1] if result_ids else None


def _existing_optional_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    resolved = path.expanduser().resolve()
    return resolved if resolved.is_file() else None


def _path_stat_snapshot(paths: Iterable[Path]) -> tuple[tuple[str, bool, int, int], ...]:
    snapshot: list[tuple[str, bool, int, int]] = []
    for path in paths:
        resolved = path.expanduser().resolve()
        try:
            stat = resolved.stat()
            snapshot.append((str(resolved), True, stat.st_size, stat.st_mtime_ns))
        except FileNotFoundError:
            snapshot.append((str(resolved), False, 0, 0))
    return tuple(snapshot)


def _print_journey(label: str, journey: DecisionOutcomeJourney) -> None:
    coverage = journey.coverage.to_dict()
    maturity = [
        {
            "candidate_key": (
                None
                if item.candidate_key is None
                else list(item.candidate_key)
            ),
            "window_days": item.window_days,
            "link_status": item.status.value,
            "outcome_status": item.outcome_status or "unknown",
        }
        for item in project_outcome_maturity(journey.outcome_maturity)
    ]
    diagnostics = Counter(item.code for item in journey.diagnostics)
    print(f"[{label}] RESULT={journey.recommendation_result.result_id}")
    print(f"[{label}] STATUS={journey.status.value}")
    print(
        f"[{label}] DECISION_DATE={journey.recommendation_result.decision_date} "
        f"CANDIDATES={len(journey.recommendation_result.candidates)}"
    )
    print(
        f"[{label}] SOURCE_PROVIDER="
        f"{journey.recommendation_result.source_identity.source_provider_id or '<unknown>'}"
    )
    print(
        f"[{label}] EVIDENCE_EVENTS={len(journey.evidence_events)} "
        f"OUTCOMES={len(journey.outcomes)} "
        f"MATURITY_BY_WINDOW={maturity}"
    )
    print(
        f"[{label}] JOURNAL={len(journey.journal_entries)} "
        f"PORTFOLIO_LEDGER={len(journey.portfolio_ledger_events)} "
        f"PORTFOLIO_TRADES={len(journey.portfolio_trades)}"
    )
    print(f"[{label}] COVERAGE={coverage}")
    print(f"[{label}] DIAGNOSTICS={dict(sorted(diagnostics.items()))}")
    print(
        f"[{label}] PERSONAL_RECORDS_SEPARATE={journey.actual_personal_records_separate} "
        f"EFFECTIVENESS_CLAIM={journey.investment_effectiveness_claim}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
