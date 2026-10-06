"""V4 有效性證據的唯讀 read model。

V3 的事件分組介面仍保留給既有 UI 與相容 caller。V4 read model 使用較
嚴格的 cohort 契約，將決策日、持有期間、策略／股票池、成本模型與
benchmark 分開，避免不同實驗或不同成熟度被混在同一個統計量內。
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping

from app_module.v4_effectiveness_evaluator import (
    V4EffectivenessReport,
    evaluate_v4_effectiveness,
)


DEFAULT_RETURN_BASIS = "close_to_close_event_date"


class V4EffectivenessReadModel:
    """從已保存證據建立 V4 唯讀報告，不產生交易或 lifecycle 動作。"""

    def __init__(
        self,
        *,
        k: int = 10,
        minimum_decision_days: int = 3,
        minimum_mature_outcomes: int = 20,
    ) -> None:
        if k <= 0 or minimum_decision_days <= 0 or minimum_mature_outcomes <= 0:
            raise ValueError("V4 effectiveness thresholds must be positive")
        self._k = int(k)
        self._minimum_decision_days = int(minimum_decision_days)
        self._minimum_mature_outcomes = int(minimum_mature_outcomes)

    def build_report(
        self,
        *,
        rows: Iterable[Mapping[str, Any]],
    ) -> V4EffectivenessReport:
        """建立 strict cohort report；輸入可來自 SQLite read model 或 JSONL。"""

        return evaluate_v4_effectiveness(
            rows,
            k=self._k,
            minimum_decision_days=self._minimum_decision_days,
            minimum_mature_outcomes=self._minimum_mature_outcomes,
        )

    def build_report_from_evidence_db(
        self,
        *,
        db_path: str | Path,
        decision_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        window_days: int | None = None,
        limit: int | None = None,
        return_basis: str = DEFAULT_RETURN_BASIS,
    ) -> V4EffectivenessReport:
        """從正式 evidence SQLite 建立唯讀報告。

        這個入口只用 SQLite ``mode=ro`` 與 ``query_only``；缺表、缺檔或
        缺少 cohort identity 會留在報告 warning，不能藉由建立 schema、
        補寫資料或猜測 universe 來讓樣本通過。
        """

        rows, source_warnings = load_v4_effectiveness_rows_from_evidence_db(
            db_path,
            decision_date=decision_date,
            start_date=start_date,
            end_date=end_date,
            window_days=window_days,
            limit=limit,
            return_basis=return_basis,
        )
        report = self.build_report(rows=rows)
        return replace(
            report,
            warnings=tuple(sorted(set(report.warnings).union(source_warnings))),
        )


def load_v4_effectiveness_rows_from_evidence_db(
    db_path: str | Path,
    *,
    decision_date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    window_days: int | None = None,
    limit: int | None = None,
    return_basis: str = DEFAULT_RETURN_BASIS,
) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
    """以 query-only 連線把 Evidence events/outcomes 映射成 V4 rows。

    Evidence event schema 沒有強制的 cohort 欄位；新版事件必須在 metadata
    同時保存 ``universe_policy_id`` 與 ``universe_snapshot_id``。舊資料只有
    ``universe_id`` 時保留相容讀取，但不替新版缺件猜值。沒有 outcome 的 event
    也保留為 missing，讓成熟分母不會因為 SQL inner join 而被悄悄縮小。查詢
    固定一個 canonical return basis，避免同一事件的不同計算口徑被重複計入。
    """

    path = Path(db_path)
    if not path.exists():
        return [], ("evidence_db_missing",)
    if limit is not None and (isinstance(limit, bool) or int(limit) <= 0):
        raise ValueError("limit must be positive when provided")
    if window_days is not None and (
        isinstance(window_days, bool) or int(window_days) <= 0
    ):
        raise ValueError("window_days must be positive when provided")
    normalized_return_basis = str(return_basis).strip()
    if not normalized_return_basis:
        raise ValueError("return_basis must not be empty")

    where: list[str] = []
    # Keep outcome filters in the JOIN condition.  A predicate in WHERE would
    # turn this LEFT JOIN into an inner join and silently erase events whose
    # requested horizon is not mature yet.
    join_params: list[Any] = [normalized_return_basis]
    outcome_join = "o.event_id = e.event_id AND o.return_basis = ?"
    if window_days is not None:
        outcome_join += " AND o.window_days = ?"
        join_params.append(int(window_days))
    params: list[Any] = []
    if decision_date:
        where.append("e.decision_date = ?")
        params.append(str(decision_date))
    if start_date:
        where.append("e.decision_date >= ?")
        params.append(str(start_date))
    if end_date:
        where.append("e.decision_date <= ?")
        params.append(str(end_date))
    sql = """
        SELECT
            e.event_id,
            e.decision_date,
            e.strategy_version_id,
            e.cost_model_id,
            e.benchmark_id,
            e.industry_benchmark_id,
            e.score_bp,
            e.metadata_json,
            e.event_type,
            e.symbol,
            e.available_date,
            o.outcome_id,
            o.window_days,
            o.return_basis,
            o.forward_return_bp,
            o.benchmark_excess_bp,
            o.industry_excess_bp,
            o.outcome_status,
            o.data_quality
        FROM evidence_events AS e
        LEFT JOIN evidence_outcomes AS o ON """ + outcome_join
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY e.decision_date ASC, e.event_id ASC, o.window_days ASC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))

    warnings: set[str] = set()
    rows: list[dict[str, Any]] = []
    try:
        uri_path = path.resolve().as_posix()
        with closing(sqlite3.connect(f"file:{uri_path}?mode=ro", uri=True)) as conn:
            conn.execute("PRAGMA query_only = ON")
            tables = {
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if not {"evidence_events", "evidence_outcomes"}.issubset(tables):
                return [], ("evidence_db_tables_missing",)
            conn.row_factory = sqlite3.Row
            raw_rows = conn.execute(
                sql,
                tuple(join_params + params),
            ).fetchall()
            for raw in raw_rows:
                row = dict(raw)
                metadata = _metadata_object(row.get("metadata_json"))
                identity_schema = _metadata_text(metadata, "universe_identity_schema")
                universe_id_legacy = _metadata_text(metadata, "universe_id")
                universe_policy_id = _metadata_text(metadata, "universe_policy_id")
                universe_policy_hash = _metadata_text(metadata, "universe_policy_hash")
                universe_policy_schema = _metadata_text(metadata, "universe_policy_schema")
                universe_snapshot_id = _metadata_text(metadata, "universe_snapshot_id")
                universe_snapshot_hash = _metadata_text(metadata, "universe_snapshot_hash")
                universe_snapshot_schema = _metadata_text(metadata, "universe_snapshot_schema")
                universe_snapshot_source_provider_id = _metadata_text(
                    metadata, "universe_snapshot_source_provider_id"
                )
                universe_snapshot_selected_codes_hash = _metadata_text(
                    metadata, "universe_snapshot_selected_codes_hash"
                )
                if universe_policy_id:
                    if not universe_snapshot_id:
                        warnings.add("evidence_rows_missing_universe_snapshot_id")
                    if not universe_policy_hash:
                        warnings.add("evidence_rows_missing_universe_policy_hash")
                    if not universe_snapshot_hash:
                        warnings.add("evidence_rows_missing_universe_snapshot_hash")
                elif identity_schema in {
                    "recommendation-universe.v1",
                    "recommendation-universe-snapshot.v1",
                } or universe_snapshot_schema:
                    # 舊版每日 identity 含日期與 selected codes，不能升格成政策身份。
                    warnings.add("evidence_rows_missing_universe_policy_id")
                elif not universe_id_legacy:
                    warnings.add("evidence_rows_missing_universe_id")
                else:
                    # 只有沒有新版 schema 標記的舊 row 才使用相容 alias。
                    universe_policy_id = universe_id_legacy
                    universe_policy_hash = universe_policy_hash or _metadata_text(
                        metadata, "universe_hash"
                    ) or "legacy-universe-hash"
                strategy_config_id = _metadata_text(metadata, "strategy_config_id")
                strategy_config_hash = _metadata_text(metadata, "strategy_config_hash")
                strategy_config_schema = _metadata_text(metadata, "strategy_config_schema")
                evidence_tier = _metadata_text(metadata, "evidence_tier")
                if not evidence_tier:
                    lineage = metadata.get("evidence_lineage")
                    if isinstance(lineage, Mapping):
                        evidence_tier = _metadata_text(lineage, "declared_tier")
                evidence_tier = evidence_tier or "unclassified"
                event_id = str(row.get("event_id") or "").strip()
                outcome_id = str(row.get("outcome_id") or "").strip()
                if not outcome_id:
                    outcome_id = f"{event_id}:missing"
                horizon = row.get("window_days")
                if horizon is None and window_days is not None:
                    horizon = int(window_days)
                if horizon is None:
                    horizon = _metadata_horizon_days(metadata)
                if horizon is None:
                    warnings.add(f"evidence_rows_missing_horizon:{event_id}")
                rows.append(
                    {
                        "decision_date": row.get("decision_date"),
                        "outcome_id": outcome_id,
                        "horizon_days": horizon or 0,
                        "strategy_version": row.get("strategy_version_id") or "",
                        # 舊欄位保留為每日 snapshot alias；新版 evaluator 使用
                        # universe_policy_id 作為跨日 key。
                        "universe_id": universe_snapshot_id or universe_id_legacy or universe_policy_id,
                        "universe_policy_id": universe_policy_id,
                        "universe_policy_hash": universe_policy_hash,
                        "universe_policy_schema": universe_policy_schema,
                        "universe_identity_schema": identity_schema,
                        "universe_snapshot_id": universe_snapshot_id,
                        "universe_snapshot_hash": universe_snapshot_hash,
                        "universe_snapshot_schema": universe_snapshot_schema,
                        "universe_snapshot_source_provider_id": universe_snapshot_source_provider_id,
                        "universe_snapshot_selected_codes_hash": universe_snapshot_selected_codes_hash,
                        "strategy_config_id": strategy_config_id or strategy_config_hash,
                        "strategy_config_hash": strategy_config_hash,
                        "strategy_config_schema": strategy_config_schema,
                        "cost_model": row.get("cost_model_id") or "",
                        "benchmark_id": row.get("benchmark_id") or "",
                        "evidence_tier": evidence_tier,
                        "status": row.get("outcome_status") or "missing",
                        "score_bp": row.get("score_bp"),
                        "return_bp": row.get("forward_return_bp"),
                        "benchmark_excess_bp": row.get("benchmark_excess_bp"),
                        "industry_excess_bp": row.get("industry_excess_bp"),
                        "event_id": event_id,
                        "event_type": row.get("event_type") or "",
                        "symbol": row.get("symbol") or "",
                        "available_date": row.get("available_date") or "",
                        "data_quality": row.get("data_quality") or "",
                        "return_basis": row.get("return_basis") or normalized_return_basis,
                    }
                )
    except sqlite3.Error as exc:
        return [], (f"evidence_db_unavailable:{type(exc).__name__}",)
    return rows, tuple(sorted(warnings))


def _metadata_object(value: object) -> dict[str, Any]:
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return dict(decoded) if isinstance(decoded, Mapping) else {}


def _metadata_text(metadata: Mapping[str, Any], key: str) -> str:
    value = metadata.get(key)
    if value is None or isinstance(value, (dict, list, tuple, bool)):
        return ""
    return str(value).strip()


def _metadata_horizon_days(metadata: Mapping[str, Any]) -> int | None:
    """Read an explicitly declared event horizon without guessing defaults."""

    for key in ("horizon_days", "expected_horizon_days"):
        value = metadata.get(key)
        if isinstance(value, bool):
            continue
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return None


__all__ = [
    "DEFAULT_RETURN_BASIS",
    "V4EffectivenessReadModel",
    "load_v4_effectiveness_rows_from_evidence_db",
]
