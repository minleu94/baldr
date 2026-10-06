"""既有保存 Trade／accepted revision 的唯讀標記 consumer；不建立 store。"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import Enum
from hashlib import sha256
import json
from typing import Any
from zoneinfo import ZoneInfo

from app_module.stock_research_chart_markers import (
    StockChartMarkerDTO, StockChartMarkerIdentityDTO, StockChartMarkerKind,
    stock_chart_marker_fingerprint, verified_stock_chart_markers,
)
from app_module.stock_research_report_dtos import StockPricePointDTO


class StockChartMarkerRecordSource(str, Enum):
    ACTUAL_TRADES = "actual_trades"
    RECOMMENDATION_CONFIRMATIONS = "recommendation_confirmations"


@dataclass(frozen=True)
class StockChartMarkerReadRequest:
    record_source: StockChartMarkerRecordSource
    stock_code: str
    cutoff_date: str
    account_id: str
    source_id: str
    result_id: str
    decision_date: str
    source_snapshot_id: str
    source_snapshot_hash: str
    source_context: tuple[tuple[str, str], ...]
    # 此 pin 必須來自既有保存來源 custody／獨立讀取邊界，不能由 candidate 填。
    expected_record_hashes: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class StockChartMarkerReadResult:
    candidates: tuple[StockChartMarkerDTO, ...] = ()
    identities: tuple[StockChartMarkerIdentityDTO, ...] = ()
    diagnostics: tuple[str, ...] = ()
    historical_pit_eligible: bool = False


def stock_chart_saved_record_sha256(record: Mapping[str, Any]) -> str:
    """原 JSONL row canonical hash（與既有 writer canonical JSON 相同格式）。

    本函式只供 custody pin 邊界使用；不是 marker content hash。
    只接受 JSON reader 原值，不轉寫 DTO 或重新計算價格。
    """
    return sha256(json.dumps(dict(record), ensure_ascii=False, sort_keys=True,
                            allow_nan=False).encode("utf-8")).hexdigest()


class StockResearchChartMarkerReader:
    """注入既有只讀 record callback；不呼叫 writer/store load 的 lock 路徑。"""
    def __init__(
        self, *,
        trade_records: Callable[[], Sequence[Mapping[str, Any]]] | None = None,
        confirmation_records: Callable[[], Sequence[Mapping[str, Any]]] | None = None,
    ) -> None:
        self._trade_records = trade_records
        self._confirmation_records = confirmation_records

    def read(
        self, request: StockChartMarkerReadRequest, *,
        price_points: Sequence[StockPricePointDTO],
        cancelled: Callable[[], bool] | None = None,
    ) -> StockChartMarkerReadResult:
        """只投影原保存已存在時鐘；日期篩選不授歷史 PIT／成交資格。"""
        if cancelled is not None and cancelled():
            return StockChartMarkerReadResult(diagnostics=("cancelled",))
        try:
            self._validate_request(request)
        except (ValueError, TypeError):
            return StockChartMarkerReadResult(diagnostics=("request_identity_missing_or_conflicting",))
        callback = (self._trade_records if request.record_source == StockChartMarkerRecordSource.ACTUAL_TRADES
                    else self._confirmation_records)
        if callback is None:
            return StockChartMarkerReadResult(diagnostics=("readonly_source_unconfigured",))
        try:
            # 原 row 先封成 JSON reader 值，隔離 callback 的可變 mapping。
            source_records = callback()
            if len(source_records) > 5000:
                return StockChartMarkerReadResult(diagnostics=("record_source_over_limit",))
            records = tuple(json.loads(json.dumps(dict(row), ensure_ascii=False, allow_nan=False))
                            for row in source_records)
        except (OSError, ValueError, TypeError, RuntimeError):
            return StockChartMarkerReadResult(diagnostics=("readonly_source_unavailable",))
        if cancelled is not None and cancelled():
            return StockChartMarkerReadResult(diagnostics=("cancelled",))
        if len(records) > 5000:
            return StockChartMarkerReadResult(diagnostics=("record_source_over_limit",))
        key = "trade_id" if request.record_source == StockChartMarkerRecordSource.ACTUAL_TRADES else "revision_id"
        selected: dict[str, Mapping[str, Any]] = {}
        expected_hashes = dict(request.expected_record_hashes)
        for row in records:
            record_id = row.get(key)
            if not isinstance(record_id, str) or record_id not in expected_hashes:
                continue
            if record_id in selected:
                return StockChartMarkerReadResult(diagnostics=("record_identity_ambiguous",))
            selected[record_id] = row
        candidates: list[StockChartMarkerDTO] = []
        identities: list[StockChartMarkerIdentityDTO] = []
        diagnostics: list[str] = []
        for record_id, expected_hash in request.expected_record_hashes:
            row = selected.get(record_id)
            if row is None:
                diagnostics.append("pinned_record_missing:" + record_id)
                continue
            if stock_chart_saved_record_sha256(row) != expected_hash:
                diagnostics.append("saved_record_hash_mismatch:" + record_id)
                continue
            try:
                identity = self._identity_from_saved_row(row, request, expected_hash)
            except (ValueError, TypeError, KeyError) as exc:
                diagnostics.append(str(exc) + ":" + record_id)
                continue
            # pin 先由核過的原 row 形成，candidate 再只按此 pin 做展示投影。
            candidate = StockChartMarkerDTO(
                identity.record_id, identity.kind, identity.stock_code, identity.event_date,
                identity.source_id, identity.source_row_hash, identity.account_id,
                identity.account_kind, identity.available_at, identity.source_context,
            )
            candidate = replace(candidate, content_sha256=stock_chart_marker_fingerprint(candidate))
            accepted = verified_stock_chart_markers((candidate,), (identity,),
                stock_code=request.stock_code, cutoff_date=request.cutoff_date,
                source_context=request.source_context, price_points=price_points)
            if not accepted:
                diagnostics.append("marker_outside_verified_chart:" + record_id)
                continue
            identities.append(identity)
            candidates.append(candidate)
        return StockChartMarkerReadResult(tuple(candidates), tuple(identities), tuple(diagnostics))

    @staticmethod
    def _validate_request(request: StockChartMarkerReadRequest) -> None:
        if not isinstance(request.record_source, StockChartMarkerRecordSource):
            raise ValueError("record_source_unknown")
        if not all((request.stock_code, request.account_id, request.source_id, request.result_id,
                    request.source_snapshot_id, request.source_snapshot_hash, request.source_context)):
            raise ValueError("request_incomplete")
        cutoff = date.fromisoformat(request.cutoff_date)
        decision = date.fromisoformat(request.decision_date)
        if cutoff.isoformat() != request.cutoff_date or decision.isoformat() != request.decision_date or decision > cutoff:
            raise ValueError("request_date_invalid")
        context = dict(request.source_context)
        if len(context) != len(request.source_context):
            raise ValueError("request_context_ambiguous")
        for field in ("stock_code", "result_id", "decision_date", "source_snapshot_id", "source_snapshot_hash"):
            if context.get(field) != getattr(request, field):
                raise ValueError("request_context_mismatch")
        if not 1 <= len(request.expected_record_hashes) <= 128:
            raise ValueError("record_pin_missing_or_over_limit")
        hashes = dict(request.expected_record_hashes)
        if len(hashes) != len(request.expected_record_hashes):
            raise ValueError("record_pin_ambiguous")
        if any(not key or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value)
               for key, value in hashes.items()):
            raise ValueError("record_pin_invalid")

    @staticmethod
    def _identity_from_saved_row(
        row: Mapping[str, Any], request: StockChartMarkerReadRequest, raw_hash: str,
    ) -> StockChartMarkerIdentityDTO:
        clock_text = row.get("created_at")
        if not isinstance(clock_text, str) or not clock_text:
            raise ValueError("saved_record_clock_unknown")
        try:
            clock = datetime.fromisoformat(clock_text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("saved_record_clock_unknown") from exc
        if clock.tzinfo is None:
            raise ValueError("saved_record_clock_unknown")
        record_day = clock.astimezone(ZoneInfo("Asia/Taipei")).date().isoformat()
        if record_day > request.cutoff_date:
            raise ValueError("saved_record_after_cutoff")
        if request.record_source == StockChartMarkerRecordSource.ACTUAL_TRADES:
            if row.get("schema_version") != "4.1" or row.get("side") not in {"buy", "sell"}:
                raise ValueError("unsupported_actual_trade")
            if "paper" in str(row.get("source_type", "")).lower():
                raise ValueError("paper_trade_rejected")
            lineage = row.get("source_summary")
            if not isinstance(lineage, Mapping):
                raise ValueError("trade_lineage_missing")
            if lineage.get("account_kind", "actual") != "actual":
                raise ValueError("paper_or_declared_trade_rejected")
            record_id = row["trade_id"]
            event_date = row.get("trade_date")
            account_id = row.get("portfolio_id")
            source_id = row.get("source_id")
            snapshot_hash = row.get("source_snapshot_hash")
            kind = StockChartMarkerKind.RECORDED_BUY if row["side"] == "buy" else StockChartMarkerKind.RECORDED_SELL
            account_kind = "actual"
            if row.get("stock_code") != request.stock_code:
                raise ValueError("saved_stock_mismatch")
        else:
            if (row.get("record_type") != "decision_continuity_revision"
                    or row.get("schema_version") not in {"decision-continuity.v1", "4.1"}
                    or row.get("action") != "accepted" or row.get("entity_type") != "decision"):
                raise ValueError("not_recommendation_confirmation")
            lineage = row.get("decision_identity")
            payload = row.get("payload")
            if not isinstance(lineage, Mapping) or not isinstance(payload, Mapping):
                raise ValueError("confirmation_identity_missing")
            if lineage.get("identity_status") != "linked":
                raise ValueError("confirmation_identity_unknown")
            record_id = row["revision_id"]
            # 確認日是原記錄已存在日，不能把後來確認移回推薦訊號日。
            event_date = record_day
            account_id = row.get("portfolio_id")
            source_id = row.get("source_id")
            snapshot_hash = row.get("source_snapshot_hash")
            kind = StockChartMarkerKind.RECOMMENDATION_CONFIRMED
            account_kind = "research"
            for field in ("stock_code", "result_id", "decision_date", "source_snapshot_id", "source_snapshot_hash"):
                if row.get(field) != lineage.get(field):
                    raise ValueError("confirmation_envelope_mismatch")
            for field in ("portfolio_id", "source_id", "source_snapshot_id", "source_snapshot_hash", "created_at", "stock_code"):
                if payload.get(field) != row.get(field):
                    raise ValueError("confirmation_payload_mismatch")
        if account_id != request.account_id:
            raise ValueError("saved_account_mismatch")
        if source_id != request.source_id or snapshot_hash != request.source_snapshot_hash:
            raise ValueError("saved_source_mismatch")
        for field in ("stock_code", "result_id", "decision_date", "source_snapshot_id", "source_snapshot_hash"):
            if lineage.get(field) != getattr(request, field):
                raise ValueError("saved_lineage_mismatch")
        if not isinstance(event_date, str) or date.fromisoformat(event_date).isoformat() != event_date:
            raise ValueError("saved_event_date_invalid")
        if event_date < request.decision_date or event_date > record_day:
            raise ValueError("saved_event_clock_conflict")
        return StockChartMarkerIdentityDTO(record_id, kind, request.stock_code, event_date,
            source_id, raw_hash, account_id, account_kind, request.source_context, clock_text)
