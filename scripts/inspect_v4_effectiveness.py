"""唯讀檢查 V4 cohort effectiveness evidence。

輸入可以是 JSON array、含 ``rows`` array 的 JSON object，或一行一筆的
JSONL。命令只讀取輸入並輸出報告，不寫 SQLite、正式 evidence、scheduler
或交易狀態；pending／missing outcome 不會進入成熟樣本分母。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_module.v4_effectiveness_read_model import V4EffectivenessReadModel


def _sample_rows() -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for index, decision_date in enumerate(
        ("2026-09-01", "2026-09-02", "2026-09-03"),
        start=1,
    ):
        rows.append(
            {
                "decision_date": decision_date,
                "outcome_id": f"sample-{index}",
                "horizon_days": 5,
                "strategy_version": "rule-v4-sample",
                "universe_id": "twse-liquid",
                "cost_model": "paper-balanced-v1",
                "benchmark_id": "twse-equal-weight",
                "status": "ready",
                "score_bp": 9000 - index * 100,
                "return_bp": 120 if index != 2 else -80,
                "benchmark_excess_bp": 40 if index != 2 else -30,
                "industry_excess_bp": 20,
            }
        )
    return tuple(rows)


def _load_rows(path: Path) -> list[Mapping[str, Any]]:
    text = Path(path).read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        rows: list[Mapping[str, Any]] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSONL line {line_number} is invalid") from exc
            if not isinstance(item, Mapping):
                raise ValueError(f"JSONL line {line_number} must be an object")
            rows.append(item)
        return rows

    if isinstance(payload, Mapping):
        payload_rows = payload.get("rows")
    else:
        payload_rows = payload
    if not isinstance(payload_rows, list):
        raise ValueError("input must be a JSON array or an object containing rows")
    if not all(isinstance(item, Mapping) for item in payload_rows):
        raise ValueError("every V4 evidence row must be a JSON object")
    return list(payload_rows)


def _render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# V4 Effectiveness Evidence",
        "",
        "> 唯讀 cohort 統計；不是交易建議，不宣稱投資有效性，不啟用 scheduler。",
        "",
        "| Cohort | Horizon | Decision days | Mature | Pending | Missing | Precision@K | Hit rate | Status |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in payload["slices"]:
        lines.append(
            "| {cohort_id} | {horizon_days} | {decision_day_count} | "
            "{mature_outcome_count} | {pending_outcome_count} | "
            "{missing_outcome_count} | {precision_at_k_bp} | "
            "{hit_rate_bp} | {evaluation_status} |".format(**item)
        )
    if payload["warnings"]:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in payload["warnings"])
    return "\n".join(lines) + "\n"


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    sources = [bool(args.sample), bool(args.input), bool(args.db_path)]
    if sum(sources) != 1:
        raise SystemExit("請擇一提供 --sample、--input 或 --db-path")
    read_model = V4EffectivenessReadModel(
        k=args.k,
        minimum_decision_days=args.minimum_decision_days,
        minimum_mature_outcomes=args.minimum_mature_outcomes,
    )
    if args.db_path:
        report = read_model.build_report_from_evidence_db(
            db_path=Path(args.db_path),
            decision_date=args.decision_date,
            start_date=args.start_date,
            end_date=args.end_date,
            window_days=args.window_days,
            limit=args.limit,
        )
    else:
        rows: Iterable[Mapping[str, Any]] = (
            _sample_rows() if args.sample else _load_rows(Path(args.input))
        )
        report = read_model.build_report(rows=rows)
    return report.to_dict()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", action="store_true")
    parser.add_argument("--input", type=Path)
    parser.add_argument(
        "--db-path",
        type=Path,
        help="正式 evidence SQLite；只以 mode=ro/query_only 讀取",
    )
    parser.add_argument("--decision-date")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--window-days", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--minimum-decision-days", type=int, default=3)
    parser.add_argument("--minimum-mature-outcomes", type=int, default=20)
    args = parser.parse_args(argv)
    payload = build_payload(args)
    rendered = (
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        if args.format == "json"
        else _render_markdown(payload)
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        _safe_print(rendered)
    return 0


def _safe_print(value: str) -> None:
    """在 Windows 非 UTF-8 console 仍能輸出完整診斷，不改寫內容。"""

    stream = sys.stdout
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        stream.write(value)
    except UnicodeEncodeError:
        safe_value = value.encode(encoding, errors="backslashreplace").decode(encoding)
        stream.write(safe_value)


if __name__ == "__main__":
    raise SystemExit(main())
