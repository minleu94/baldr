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

from app_module.v4_evidence_identity import (
    DEFAULT_RETURN_BASIS,
    UNMODELED_COST_MODEL_IDS,
)


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
    strategy_config_id: str = ""
    universe_policy_hash: str = ""
    return_basis: str = DEFAULT_RETURN_BASIS
    evidence_tier: str = "unclassified"
    universe_snapshot_count: int = 0
    universe_snapshot_ids: tuple[str, ...] = ()
    universe_component_change_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "cohort_id": self.cohort_id,
            "horizon_days": self.horizon_days,
            "strategy_version": self.strategy_version,
            "universe_id": self.universe_id,
            "universe_policy_id": self.universe_id,
            "universe_policy_hash": self.universe_policy_hash,
            "strategy_config_id": self.strategy_config_id,
            "return_basis": self.return_basis,
            "evidence_tier": self.evidence_tier,
            "universe_snapshot_count": self.universe_snapshot_count,
            "universe_snapshot_ids": list(self.universe_snapshot_ids),
            "universe_component_change_count": self.universe_component_change_count,
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
            "snapshot_ids": set(),
            "snapshot_component_hashes": set(),
        }
    )
    report_warnings: set[str] = set()
    row_warning_counts: dict[str, int] = defaultdict(int)

    for index, raw in enumerate(rows):
        row = dict(raw)
        horizon_days = _integer_or_none(row.get("horizon_days"))
        if horizon_days is None or horizon_days <= 0:
            row_warning_counts["invalid_horizon_days"] += 1
            continue

        decision_date = _normalise_date(row.get("decision_date"))
        if decision_date is None:
            row_warning_counts["missing_decision_date"] += 1
            continue

        identity = _cohort_identity(row)
        if identity is None:
            row_warning_counts["incomplete_cohort_identity"] += 1
            continue
        (
            strategy_version,
            strategy_config_id,
            universe_policy_id,
            universe_policy_hash,
            cost_model,
            benchmark_id,
            return_basis,
            evidence_tier,
            identity_warnings,
        ) = identity
        key = (
            horizon_days,
            strategy_version,
            strategy_config_id,
            universe_policy_id,
            universe_policy_hash,
            cost_model,
            benchmark_id,
            return_basis,
            evidence_tier,
        )
        bucket = grouped[key]
        bucket["warnings"].update(identity_warnings)
        if cost_model in UNMODELED_COST_MODEL_IDS:
            bucket["warnings"].add("cost_model_not_cost_adjusted")

        snapshot_id = _required_group_value(row, "universe_snapshot_id")
        if snapshot_id:
            bucket["snapshot_ids"].add(snapshot_id)
        component_hash = _required_group_value(
            row, "universe_snapshot_selected_codes_hash"
        )
        if component_hash:
            bucket["snapshot_component_hashes"].add(component_hash)

        outcome_identity = str(
            row.get("outcome_id")
            or row.get("event_id")
            or f"row-{index}"
        ).strip()
        previous = bucket["seen"].get((decision_date, outcome_identity))
        if previous is not None:
            if _stable_row_signature(previous) != _stable_row_signature(row):
                bucket["warnings"].add("conflicting_duplicate_outcome")
            continue
        bucket["seen"][(decision_date, outcome_identity)] = row

        status = str(row.get("status", "")).strip().lower()
        if status in {"pending", "not_matured", "incomplete"}:
            bucket["pending"] += 1
            continue
        if status in {
            "missing",
            "unavailable",
            "failed",
            "missing_price",
            "insufficient_future_data",
        }:
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
                "identity": outcome_identity,
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
        (
            horizon_days,
            strategy_version,
            strategy_config_id,
            universe_policy_id,
            universe_policy_hash,
            cost_model,
            benchmark_id,
            return_basis,
            evidence_tier,
        ) = key
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
                str(strategy_config_id),
                str(universe_policy_id),
                str(cost_model),
                str(benchmark_id),
                str(return_basis),
                str(evidence_tier),
            )
        )
        slices.append(
            V4EffectivenessSlice(
                cohort_id=cohort_id,
                horizon_days=int(horizon_days),
                strategy_version=str(strategy_version),
                universe_id=str(universe_policy_id),
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
                strategy_config_id=str(strategy_config_id),
                universe_policy_hash=str(universe_policy_hash),
                return_basis=str(return_basis),
                evidence_tier=str(evidence_tier),
                universe_snapshot_count=len(bucket["snapshot_ids"]),
                universe_snapshot_ids=tuple(sorted(bucket["snapshot_ids"])),
                universe_component_change_count=max(
                    0, len(bucket["snapshot_component_hashes"]) - 1
                ),
            )
        )

    if not slices:
        report_warnings.add("no_valid_cohort_rows")
    report_warnings.update(
        f"rows_{code}:{count}"
        for code, count in row_warning_counts.items()
    )
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
    value = row.get(field_name, "")
    if value is None or isinstance(value, (bool, Mapping, list, tuple)):
        return ""
    return str(value).strip()


def _cohort_identity(
    row: Mapping[str, Any],
) -> tuple[str, str, str, str, str, str, str, str, tuple[str, ...]] | None:
    """解析跨日 cohort identity，並拒絕新版身份的缺件。

    舊 JSON／fixture 只有 ``universe_id`` 時保留相容讀取；一旦 row 宣告
    新版 policy／snapshot schema，缺少政策身份或每日快照就必須診斷為無效，
    不可把當日 snapshot id 當成跨日政策 id。
    """

    strategy_version = _required_group_value(row, "strategy_version")
    if not strategy_version:
        strategy_version = _required_group_value(row, "strategy_version_id")
    cost_model = _required_group_value(row, "cost_model") or _required_group_value(
        row, "cost_model_id"
    )
    benchmark_id = _required_group_value(row, "benchmark_id")
    if not strategy_version or not cost_model or not benchmark_id:
        return None

    identity_schema = _required_group_value(row, "universe_identity_schema")
    policy_schema = _required_group_value(row, "universe_policy_schema")
    snapshot_schema = _required_group_value(row, "universe_snapshot_schema")
    policy_id = _required_group_value(row, "universe_policy_id")
    snapshot_id = _required_group_value(row, "universe_snapshot_id")
    snapshot_hash = _required_group_value(row, "universe_snapshot_hash")
    warnings: list[str] = []

    # Read-model rows for pre-policy events expose the legacy ``universe_id``
    # through the compatibility ``universe_policy_id`` alias.  Treat that
    # exact, schema-less alias as legacy; an explicitly declared policy (or a
    # policy id that differs from the legacy alias) must carry a snapshot too.
    legacy_alias = _required_group_value(row, "universe_id")
    declared_new_identity = bool(
        policy_schema
        or snapshot_schema
        or identity_schema in {
            "recommendation-universe-policy.v1",
            "recommendation-universe-snapshot.v1",
        }
        or (policy_id and policy_id != legacy_alias)
    )
    if declared_new_identity:
        # 新版 row 必須同時保存穩定政策與每日快照；兩者缺一都不能進成熟分母。
        if not policy_id or not snapshot_id or not snapshot_hash:
            return None
        if identity_schema and identity_schema not in {
            "recommendation-universe-snapshot.v1",
            "recommendation-universe.v1",
        }:
            warnings.append("universe_identity_schema_unrecognized")
    else:
        legacy_id = legacy_alias
        if not legacy_id:
            return None
        # 舊資料沒有 policy/snapshot 分層，僅作相容診斷，不宣稱新版契約。
        policy_id = legacy_id
        snapshot_id = ""

    policy_hash = _required_group_value(row, "universe_policy_hash")
    if not policy_hash:
        policy_hash = _required_group_value(row, "universe_hash") or (
            "legacy-universe-hash" if not policy_schema else ""
        )
    if not policy_hash:
        return None

    strategy_config_id = _required_group_value(row, "strategy_config_id")
    strategy_config_schema = _required_group_value(row, "strategy_config_schema")
    if strategy_config_schema and not strategy_config_id:
        return None
    if not strategy_config_id:
        strategy_config_id = _required_group_value(row, "strategy_config_hash")
    if not strategy_config_id:
        strategy_config_id = "legacy-strategy-config"

    return (
        strategy_version,
        strategy_config_id,
        policy_id,
        policy_hash,
        cost_model,
        benchmark_id,
        _required_group_value(row, "return_basis") or DEFAULT_RETURN_BASIS,
        _required_group_value(row, "evidence_tier") or "unclassified",
        tuple(warnings),
    )


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
