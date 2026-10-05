"""歷史分頁的研究觀測投影；不建立歷程事件或改寫當期來源。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Sequence

from app_module.daily_market_snapshot_repository import VerifiedDailyMarketSnapshot
from app_module.daily_market_research_screener import evaluate_daily_market_conditions


@dataclass(frozen=True, slots=True)
class MembershipHistoryBrowseRow:
    decision_date: str
    stock_code: str
    state: str
    reason: str
    published_at: str
    cutoff_at: str
    manifest_sha256: str
    manifest_identity_sha256: str
    artifact_sha256: str

    def to_dict(self) -> dict[str, str]:
        return {name: str(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class MembershipHistoryBrowsePage:
    current_manifest_sha256: str
    current_manifest_identity_sha256: str
    cohort_id: str
    condition_keys: tuple[str, ...]
    combine_mode: str
    stock_code: str
    generation_id: str
    source_fingerprint: str
    next_cursor: str | None
    has_more: bool
    rows: tuple[MembershipHistoryBrowseRow, ...]
    research_only: bool = True
    historical_pit_eligible: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {**{name: getattr(self, name) for name in self.__dataclass_fields__ if name != "rows"},
                "rows": [row.to_dict() for row in self.rows]}


def project_membership_history_rows(
    snapshots: Sequence[VerifiedDailyMarketSnapshot],
    *, stock_code: str, condition_keys: tuple[str, ...], combine_mode: str,
) -> tuple[MembershipHistoryBrowseRow, ...]:
    """每個 revision 各列；晚發布、partial 或缺件不當未命中。"""
    rows: list[MembershipHistoryBrowseRow] = []
    for snapshot in snapshots:
        manifest = snapshot.manifest
        payload = snapshot.stock_snapshots.get(stock_code)
        raw = payload.get("conditions") if payload is not None else None
        conditions = raw if isinstance(raw, dict) else {}
        result = evaluate_daily_market_conditions(
            conditions, condition_keys, combine_mode,
            expected_decision_date=snapshot.decision_date,
        )
        published = str(manifest["published_at"])
        cutoff = str(manifest["decision_cutoff"])
        state = result.combined_state
        reason = "；".join(f"{item.key}：{item.reason}" for item in result.conditions)
        if payload is None or snapshot.completeness != "complete_declared_cohort":
            state, reason = "unknown", "該觀測缺件或僅部分母體；不能當作未命中。"
        elif datetime.fromisoformat(published).astimezone(datetime.fromisoformat(cutoff).tzinfo).date() > datetime.fromisoformat(cutoff).date():
            state, reason = "unknown", "快照於決策日後發布；當時可得性未獲證明。"
        records = manifest.get("stocks", ())
        artifact = next((str(item.get("artifact_sha256", "")) for item in records
                         if isinstance(item, dict) and item.get("stock_code") == stock_code), "")
        rows.append(MembershipHistoryBrowseRow(
            snapshot.decision_date.isoformat(), stock_code, state, reason,
            published, cutoff, snapshot.manifest_sha256,
            snapshot.manifest_identity_sha256, artifact,
        ))
    return tuple(rows)
