"""執行受控的 personal calibration real-source fit。

本命令只以 ``PersonalizationReadService`` 讀取 caller 指定的來源，將既有
evaluator 的 fit/evaluate 結果保存成 hash-bound、create-only artifact。它不
建立 scope、prediction、action 或 outcome，也不改 global pointer、promotion、
scheduler、broker 或正式行情資料。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from app_module.personalization_fit_runner import (  # noqa: E402
    PersonalizationFitArtifactError,
    PersonalizationFitRequest,
    PersonalizationFitRunResult,
    run_personalization_fit,
)
from app_module.personalization_read_service import (  # noqa: E402
    PersonalizationReadService,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="以唯讀 real-source 讀取接既有 personal calibration evaluator。"
    )
    parser.add_argument("--scope-id", required=True)
    parser.add_argument("--fit-as-of", required=True)
    parser.add_argument("--evaluated-as-of", required=True)
    parser.add_argument("--evaluation-cutoff-at", required=True)
    parser.add_argument("--output-path", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--journal-path", type=Path)
    parser.add_argument("--evidence-db", type=Path)
    parser.add_argument("--result-id")
    parser.add_argument("--stock-code")
    parser.add_argument("--artifact-id")
    parser.add_argument("--shrinkage-strength", type=int, default=10)
    parser.add_argument("--embargo-days", type=int)
    parser.add_argument("--min-fit-rows", type=int, default=2)
    parser.add_argument("--min-fit-decision-dates", type=int, default=2)
    parser.add_argument("--max-results", type=int, default=100)
    parser.add_argument("--max-candidates-per-result", type=int, default=100)
    parser.add_argument("--max-evidence-events", type=int, default=500)
    parser.add_argument("--max-journal-rows", type=int, default=50_000)
    return parser


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _print_result(result: PersonalizationFitRunResult) -> None:
    print(
        json.dumps(
            result.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            default=_json_default,
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        read_service = PersonalizationReadService.from_paths(
            output_root=args.output_root,
            journal_path=args.journal_path,
            evidence_db_path=args.evidence_db,
            max_results=args.max_results,
            max_candidates_per_result=args.max_candidates_per_result,
            max_evidence_events=args.max_evidence_events,
            max_journal_rows=args.max_journal_rows,
        )
        request = PersonalizationFitRequest(
            scope_id=args.scope_id,
            fit_as_of=args.fit_as_of,
            evaluated_as_of=args.evaluated_as_of,
            evaluation_cutoff_at=args.evaluation_cutoff_at,
            output_path=args.output_path,
            result_id=args.result_id,
            stock_code=args.stock_code,
            artifact_id=args.artifact_id,
            shrinkage_strength=args.shrinkage_strength,
            embargo_days=args.embargo_days,
            min_fit_rows=args.min_fit_rows,
            min_fit_decision_dates=args.min_fit_decision_dates,
            max_results=args.max_results,
            max_candidates_per_result=args.max_candidates_per_result,
            max_evidence_events=args.max_evidence_events,
            max_journal_rows=args.max_journal_rows,
        )
        result = run_personalization_fit(
            request,
            read_service=read_service,
        )
        _print_result(result)
        return 0 if result.status in {"created", "idempotent_retry"} else 2
    except (OSError, TypeError, ValueError, PersonalizationFitArtifactError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": "personalization-fit-runner.v1",
                    "status": "blocked",
                    "blocked_reason": "request_or_cli_failed",
                    "diagnostics": [
                        f"request_or_cli_failed:{type(exc).__name__}:{exc}"
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
