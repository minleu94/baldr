"""V4 證據評估器：明確區分 cohort 與決策日。

既有 V3 read model 仍是唯讀相容介面。V4 使用更嚴格的契約：結果依凍結的
策略／資料／政策 cohort 分組，top-k 對每個決策日獨立計算，pending 或
missing 結果絕不增加成熟樣本。所有比例使用整數 basis points；本模組不會
產生交易動作，也不會提升模型版本。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class V4EffectivenessSlice:
    """一個可供人工覆盤的不可變證據 cohort。"""

    cohort_id: str
    horizon_days: int
    strategy_version: str
    universe_id: str
    cost_model: str
    benchmark_id: str
    decision_date_start: str | None
    decision_date_end: str | None
    decision_day_count: int
    mature_outcome_count: int
    pending_outcome_count: int
    missing_outcome_count: int
    benchmark_coverage_bp: int | None
    industry_coverage_bp: int | None
    precision_at_k_bp: int | None
    hit_rate_bp: int | None
    average_return_bp: int | None
    average_benchmark_excess_bp: int | None
    evaluation_status: str
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "cohort_id": self.cohort_id,
            "horizon_days": self.horizon_days,
            "strategy_version": self.strategy_version,
            "universe_id": self.universe_id,
            "cost_model": self.cost_model,
            "benchmark_id": self.benchmark_id,
            "decision_date_start": self.decision_date_start,
            "decision_date_end": self.decision_date_end,
            "decision_day_count": self.decision_day_count,
            "mature_outcome_count": self.mature_outcome_count,
            "pending_outcome_count": self.pending_outcome_count,
            "missing_outcome_count": self.missing_outcome_count,
            "benchmark_coverage_bp": self.benchmark_coverage_bp,
            "industry_coverage_bp": self.industry_coverage_bp,
            "precision_at_k_bp": self.precision_at_k_bp,
            "hit_rate_bp": self.hit_rate_bp,
            "average_return_bp": self.average_return_bp,
            "average_benchmark_excess_bp": self.average_benchmark_excess_bp,
            "evaluation_status": self.evaluation_status,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class V4EffectivenessReport:
    """V4 slice 的唯讀集合。"""

    slices: tuple[V4EffectivenessSlice, ...]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "v4-effectiveness-report.v1",
            "slices": [item.to_dict() for item in self.slices],
            "warnings": list(self.warnings),
            "access_boundary": {
                "read_only": True,
                "manual_review_required": True,
                "production_scheduler_allowed": False,
                "auto_trading": False,
            },
        }


_GROUP_FIELDS = (
    "horizon_days",
    "strategy_version",
    "universe_id",
    "cost_model",
    "benchmark_id",
)


def evaluate_v4_effectiveness(
    rows: Iterable[Mapping[str, Any]],
    *,
    k: int = 10,
    minimum_decision_days: int = 3,
    minimum_mature_outcomes: int = 20,
) -> V4EffectivenessReport:
    """評估凍結證據，不混合日期、持有期間或版本。

    輸入刻意採用一般 mapping，讓 evaluator 可以讀 SQLite read model、JSONL
    證據或隔離研究執行。ready row 必須有 ``decision_date``、``score_bp`` 與
    ``return_bp``。benchmark 與產業超額值可缺省，但 coverage 會以成熟列數
    為分母揭露。
    """

    if k <= 0 or minimum_decision_days <= 0 or minimum_mature_outcomes <= 0:
        raise ValueError("k and maturity thresholds must be positive")

    grouped: dict[tuple[Any, ...], dict[str, Any]] = defaultdict(
        lambda: {
            "ready_by_date": defaultdict(list),
            "pending": 0,
            "missing": 0,
            "warnings": set(),
            "seen": {},
        }
    )
    report_warnings: set[str] = set()

    for index, raw in enumerate(rows):
        row = dict(raw)
        horizon_days = _integer_or_none(row.get("horizon_days"))
        if horizon_days is None or horizon_days <= 0:
            report_warnings.add(f"row_{index}:invalid_horizon_days")
            continue

        decision_date = _normalise_date(row.get("decision_date"))
        if decision_date is None:
            report_warnings.add(f"row_{index}:missing_decision_date")
            continue

        values = tuple(_required_group_value(row, field) for field in _GROUP_FIELDS[1:])
        if any(value == "" for value in values):
            report_warnings.add(f"row_{index}:incomplete_cohort_identity")
            continue
        strategy_version, universe_id, cost_model, benchmark_id = values
        key = (horizon_days, strategy_version, universe_id, cost_model, benchmark_id)
        bucket = grouped[key]

        identity = str(
            row.get("outcome_id")
            or row.get("event_id")
            or f"row-{index}"
        ).strip()
        previous = bucket["seen"].get((decision_date, identity))
        if previous is not None:
            if _stable_row_signature(previous) != _stable_row_signature(row):
                bucket["warnings"].add("conflicting_duplicate_outcome")
            continue
        bucket["seen"][(decision_date, identity)] = row

        status = str(row.get("status", "")).strip().lower()
        if status in {"pending", "not_matured", "incomplete"}:
            bucket["pending"] += 1
            continue
        if status in {"missing", "unavailable", "failed"}:
            bucket["missing"] += 1
            continue
        if status != "ready":
            # 未知狀態不可靜默丟掉；列入 missing 使成熟度分母保持保守。
            bucket["missing"] += 1
            bucket["warnings"].add(f"unknown_status:{status or 'empty'}")
            continue

        score_bp = _integer_or_none(row.get("score_bp"))
        return_bp = _integer_or_none(row.get("return_bp"))
        if score_bp is None or return_bp is None:
            bucket["missing"] += 1
            bucket["warnings"].add("ready_row_missing_score_or_return")
            continue
        bucket["ready_by_date"][decision_date].append(
            {
                "identity": identity,
                "score_bp": score_bp,
                "return_bp": return_bp,
                "benchmark_excess_bp": _integer_or_none(
                    row.get("benchmark_excess_bp")
                ),
                "industry_excess_bp": _integer_or_none(
                    row.get("industry_excess_bp")
                ),
            }
        )

    slices: list[V4EffectivenessSlice] = []
    for key, bucket in sorted(grouped.items(), key=lambda item: item[0]):
        horizon_days, strategy_version, universe_id, cost_model, benchmark_id = key
        ready_by_date = bucket["ready_by_date"]
        dates = sorted(ready_by_date)
        ready_rows = [row for day in dates for row in ready_by_date[day]]
        daily_precision: list[int] = []
        for day in dates:
            ranked = sorted(
                ready_by_date[day],
                key=lambda row: (-int(row["score_bp"]), str(row["identity"])),
            )
            top_rows = ranked[: min(k, len(ranked))]
            daily_precision.append(
                sum(int(row["return_bp"]) > 0 for row in top_rows)
                * 10000
                // len(top_rows)
            )

        mature_count = len(ready_rows)
        benchmark_count = sum(
            row["benchmark_excess_bp"] is not None for row in ready_rows
        )
        industry_count = sum(
            row["industry_excess_bp"] is not None for row in ready_rows
        )
        benchmark_values = [
            int(row["benchmark_excess_bp"])
            for row in ready_rows
            if row["benchmark_excess_bp"] is not None
        ]
        return_values = [int(row["return_bp"]) for row in ready_rows]
        warnings = set(bucket["warnings"])
        if benchmark_count < mature_count:
            warnings.add("benchmark_coverage_incomplete")
        if industry_count < mature_count:
            warnings.add("industry_coverage_incomplete")
        if len(dates) < minimum_decision_days:
            status = "insufficient_decision_days"
        elif mature_count < minimum_mature_outcomes:
            status = "insufficient_mature_outcomes"
        elif warnings:
            status = "ready_for_manual_review_with_warnings"
        else:
            status = "ready_for_manual_review"

        cohort_id = ":".join(
            (
                str(horizon_days),
                str(strategy_version),
                str(universe_id),
                str(cost_model),
                str(benchmark_id),
            )
        )
        slices.append(
            V4EffectivenessSlice(
                cohort_id=cohort_id,
                horizon_days=int(horizon_days),
                strategy_version=str(strategy_version),
                universe_id=str(universe_id),
                cost_model=str(cost_model),
                benchmark_id=str(benchmark_id),
                decision_date_start=dates[0].isoformat() if dates else None,
                decision_date_end=dates[-1].isoformat() if dates else None,
                decision_day_count=len(dates),
                mature_outcome_count=mature_count,
                pending_outcome_count=int(bucket["pending"]),
                missing_outcome_count=int(bucket["missing"]),
                benchmark_coverage_bp=(
                    benchmark_count * 10000 // mature_count if mature_count else None
                ),
                industry_coverage_bp=(
                    industry_count * 10000 // mature_count if mature_count else None
                ),
                precision_at_k_bp=(
                    sum(daily_precision) // len(daily_precision)
                    if daily_precision
                    else None
                ),
                hit_rate_bp=(
                    sum(int(row["return_bp"]) > 0 for row in ready_rows)
                    * 10000
                    // mature_count
                    if mature_count
                    else None
                ),
                average_return_bp=(
                    sum(return_values) // mature_count if mature_count else None
                ),
                average_benchmark_excess_bp=(
                    sum(benchmark_values) // len(benchmark_values)
                    if benchmark_values
                    else None
                ),
                evaluation_status=status,
                warnings=tuple(sorted(warnings)),
            )
        )

    if not slices:
        report_warnings.add("no_valid_cohort_rows")
    report_warnings.update(
        warning
        for item in slices
        for warning in item.warnings
    )
    return V4EffectivenessReport(
        slices=tuple(slices),
        warnings=tuple(sorted(report_warnings)),
    )


def _required_group_value(row: Mapping[str, Any], field_name: str) -> str:
    return str(row.get(field_name, "")).strip()


def _normalise_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except (TypeError, ValueError):
        return None


def _integer_or_none(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        text = str(value).strip()
        if not text:
            return None
        return int(text)
    except (TypeError, ValueError):
        return None


def _stable_row_signature(row: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(row.get(field, ""))
        for field in (
            "status",
            "score_bp",
            "return_bp",
            "benchmark_excess_bp",
            "industry_excess_bp",
        )
    )


__all__ = [
    "V4EffectivenessReport",
    "V4EffectivenessSlice",
    "evaluate_v4_effectiveness",
]
