from __future__ import annotations

from collections import Counter
from pathlib import Path
import sqlite3
from typing import Any

from app_module.signal_decay_dashboard_dtos import (
    SignalDecayDashboardCards,
    SignalDecayDashboardRequest,
    SignalDecayDashboardResult,
    SignalDecayDashboardRow,
)
from app_module.signal_decay_service import SignalDecayService
from app_module.evidence_event_repository import EvidenceEventRepository
from app_module.live_research_gap_repository import LiveResearchGapRepository
from app_module.signal_decay_repository import SignalDecayRepository


SIGNAL_DECAY_LIMITATIONS = (
    "Signal Decay Dashboard 只呈現 research evidence，不會自動套用 demote 或 retire。",
    "短窗弱化、live gap 與 benchmark 缺口需要人工判讀，不能單獨證明訊號失效。",
    "樣本不足或 data quality degraded 時，只能作為資料品質與覆盤提醒。",
)


class SignalDecayDashboardService:
    """Read-only dashboard adapter over saved signal decay observations."""

    def __init__(self, backend: Any) -> None:
        self.backend = backend

    def load_dashboard(self, request: SignalDecayDashboardRequest) -> SignalDecayDashboardResult:
        try:
            rows = tuple(
                _row_from_observation(row)
                for row in self.backend.list_decay_observations(
                    observation_date=_blank_to_none(request.observation_date),
                    signal_scope_type=_blank_to_none(request.scope_type),
                    signal_scope_id=_blank_to_none(request.scope_id),
                )
                if _observation_matches(row, request)
            )
        except (FileNotFoundError, sqlite3.OperationalError) as exc:
            diagnostic = _readonly_source_diagnostic(exc)
            if diagnostic is None:
                raise
            return SignalDecayDashboardResult(
                request=request,
                cards=_build_cards(()),
                rows=(),
                empty_state_message=(
                    "SQLite 證據資料庫或資料表目前不可用；本頁以唯讀方式檢查，不會建立資料庫或初始化 schema。"
                ),
                limitations=SIGNAL_DECAY_LIMITATIONS,
                diagnostics=(diagnostic,),
            )
        return SignalDecayDashboardResult(
            request=request,
            cards=_build_cards(rows),
            rows=rows,
            empty_state_message=_empty_state_message(rows, request),
            limitations=SIGNAL_DECAY_LIMITATIONS,
            quality_counts=dict(Counter(row.quality for row in rows)),
            warning_counts=_warning_counts(rows),
        )


def create_signal_decay_dashboard_service(
    config: Any,
    *,
    db_path: str | Path | None = None,
) -> SignalDecayDashboardService:
    source_path = Path(db_path) if db_path is not None else Path(config.db_file)
    backend = SignalDecayService(
        config,
        db_path=source_path,
        evidence_repository=EvidenceEventRepository(config, db_path=source_path, read_only=True),
        gap_repository=LiveResearchGapRepository(config, db_path=source_path, read_only=True),
        decay_repository=SignalDecayRepository(config, db_path=source_path, read_only=True),
    )
    return SignalDecayDashboardService(backend)


def _readonly_source_diagnostic(error: BaseException) -> str | None:
    if isinstance(error, FileNotFoundError):
        return "sqlite_database_missing"
    if isinstance(error, sqlite3.OperationalError) and "no such table" in str(error).casefold():
        return "sqlite_evidence_table_missing"
    return None


def _row_from_observation(row: Any) -> SignalDecayDashboardRow:
    return SignalDecayDashboardRow(
        signal_scope_type=str(row.signal_scope_type or ""),
        signal_scope_id=str(row.signal_scope_id or ""),
        sample_size_short=int(row.sample_size_short or 0),
        sample_size_long=int(row.sample_size_long or 0),
        forward_excess_short_bp=row.forward_excess_short_bp,
        forward_excess_long_bp=row.forward_excess_long_bp,
        win_rate_short_bp=row.win_rate_short_bp,
        win_rate_long_bp=row.win_rate_long_bp,
        mae_short_bp=row.mae_short_bp,
        mae_long_bp=row.mae_long_bp,
        live_gap_short_bp=row.live_gap_short_bp,
        live_gap_long_bp=row.live_gap_long_bp,
        decay_score_bp=int(row.decay_score_bp or 0),
        decay_status=str(row.decay_status or ""),
        suggested_lifecycle_action=str(row.suggested_lifecycle_action or ""),
        confidence=str(row.confidence or ""),
        quality=str(row.quality or "missing"),
        warnings=tuple(str(value) for value in row.warnings_json),
    )


def _observation_matches(row: Any, request: SignalDecayDashboardRequest) -> bool:
    return all(
        (
            _matches(row.event_type, request.event_type),
            _matches(row.event_family, request.event_family),
            _matches(row.strategy_version_id, request.strategy_version_id),
            _matches(row.profile_id, request.profile_id),
            _matches(row.decay_status, request.decay_status),
            _matches(row.suggested_lifecycle_action, request.suggested_lifecycle_action),
            _matches(row.confidence, request.confidence),
        )
    )


def _build_cards(rows: tuple[SignalDecayDashboardRow, ...]) -> SignalDecayDashboardCards:
    statuses = Counter(row.decay_status for row in rows)
    suggestions = Counter(row.suggested_lifecycle_action for row in rows)
    return SignalDecayDashboardCards(
        scopes_evaluated=len(rows),
        stable_count=statuses["stable"],
        watch_count=statuses["watch"],
        decaying_count=statuses["decaying"],
        severe_decay_count=statuses["severe_decay"],
        demote_candidate_count=suggestions["demote_candidate"],
        retire_candidate_count=suggestions["retire_candidate"],
        insufficient_sample_count=statuses["insufficient_sample"],
        low_confidence_count=sum(1 for row in rows if row.confidence == "low"),
        warnings_count=sum(len(row.warnings) for row in rows),
    )


def _empty_state_message(rows: tuple[SignalDecayDashboardRow, ...], request: SignalDecayDashboardRequest) -> str:
    if not rows:
        return "尚無 signal decay evidence。請先建立 evidence outcome、live gap，並執行 signal decay dry-run。"
    if any(
        row.decay_status == "insufficient_sample"
        or row.sample_size_short < int(request.min_sample_size)
        or row.sample_size_long < int(request.min_sample_size)
        for row in rows
    ):
        return "樣本不足，只能作資料品質檢查，不可作訊號有效性判斷。"
    return ""


def _warning_counts(rows: tuple[SignalDecayDashboardRow, ...]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        counter.update(row.warnings)
    return dict(counter)


def _matches(actual: str | None, expected: str | None) -> bool:
    expected_text = _blank_to_none(expected)
    return expected_text is None or str(actual or "") == expected_text


def _blank_to_none(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None
