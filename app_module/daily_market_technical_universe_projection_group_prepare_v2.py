"""同次 exact read 的三路私有候選準備；不發行 reader 資格。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields
import hashlib
import json
from typing import Literal, cast

from app_module.daily_market_technical_universe_kdj_alignment_query_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_ENTRY_BYTES_V1,
    DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_INDEX_BYTES_V1,
    DailyMarketTechnicalUniverseKDJCompactEntryV1,
)
from app_module.daily_market_technical_universe_ma_alignment_query_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_INDEX_BYTES_V1,
    DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_INDEX_V1_SCHEMA,
    DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_VERIFICATION_V1,
    DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1,
    DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1,
    DailyMarketTechnicalMaAlignmentCompactEntryV1,
    DailyMarketTechnicalMaAlignmentCompactIndexV1,
    _MaPreparedPublicationV1,
    _ParentProjectionObservationV1,
)
from app_module.daily_market_technical_universe_projection_group_v2 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MAX_STOCKS,
    DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MAX_TOTAL_BYTES,
    DailyMarketTechnicalUniverseProjectionGroupV2,
    _CallbackRowProvenanceV2,
    _fail,
    _strict_cancel_check,
)
from app_module.daily_market_technical_universe_v4_query import (
    DailyMarketTechnicalUniverseV4Query,
    DailyMarketTechnicalUniverseV4ReadSelection,
    DailyMarketTechnicalUniverseV4ReadSession,
)
from app_module.daily_market_technical_universe_volatility_alignment_query_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_ENTRY_BYTES_V1,
    DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_INDEX_BYTES_V1,
    DailyMarketTechnicalUniverseVolatilityCompactEntryV1,
)

_MemberEntry = (
    DailyMarketTechnicalUniverseKDJCompactEntryV1
    | DailyMarketTechnicalUniverseVolatilityCompactEntryV1
)


class _EntryEncoder(json.JSONEncoder):
    def default(self, value: object) -> object:
        if type(value) in (
            DailyMarketTechnicalMaAlignmentCompactEntryV1,
            DailyMarketTechnicalUniverseKDJCompactEntryV1,
            DailyMarketTechnicalUniverseVolatilityCompactEntryV1,
        ):
            return cast(_MemberEntry | DailyMarketTechnicalMaAlignmentCompactEntryV1, value).to_dict()
        if type(value) is _ParentProjectionObservationV1:
            return {item.name: getattr(value, item.name) for item in fields(value)}
        return super().default(value)


def _ma_index_payload_references(
    index: DailyMarketTechnicalMaAlignmentCompactIndexV1,
) -> dict[str, object]:
    """保留原 transport 欄位，entries 逐列編碼，不先呼叫全量 to_dict。"""
    payload: dict[str, object] = {item.name: getattr(index, item.name) for item in fields(index)}
    payload.update({
        "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_INDEX_V1_SCHEMA,
        "verification_status": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_VERIFICATION_V1,
        "method_id": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1,
        "method_version": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1,
        "decision_date": index.decision_date.isoformat(),
        "counts": index.counts.to_dict(),
        "ma_state_counts": tuple({"state": state, "count": count} for state, count in index.ma_state_counts),
        "source_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
    })
    return payload


def _digest_payload(
    payload: object, limit: int, cancel: Callable[[], object] | None,
) -> tuple[str, int]:
    """逐片編碼有界 payload；不建立完整 entries JSON 複本。"""
    encoder = _EntryEncoder(
        sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    )
    digest = hashlib.sha256()
    total = 0
    _strict_cancel_check(cancel)
    for position, chunk in enumerate(encoder.iterencode(payload)):
        if position % 256 == 0:
            _strict_cancel_check(cancel)
        encoded = chunk.encode("utf-8")
        total += len(encoded)
        if total > limit:
            _fail("technical_projection_group_v2_prepared_payload_limit")
        digest.update(encoded)
    _strict_cancel_check(cancel)
    return digest.hexdigest(), total


def _identified_payload_size(body_bytes: int, field_name: str) -> int:
    # 非空 canonical object 增加逗號、key、冒號及 64-char SHA 字串。
    return body_bytes + 1 + len(json.dumps(field_name).encode("utf-8")) + 1 + 2 + 64


@dataclass(frozen=True, slots=True)
class _PreparedProjectionMemberV2:
    entries: tuple[_MemberEntry, ...]
    source_request_json: str
    body_identity_sha256: str
    canonical_payload_bytes: int

    @property
    def reader_issued(self) -> Literal[False]:
        return False


@dataclass(frozen=True, slots=True)
class _PreparedProjectionGroupV2:
    group: DailyMarketTechnicalUniverseProjectionGroupV2
    ma: _MaPreparedPublicationV1
    kdj: _PreparedProjectionMemberV2
    volatility: _PreparedProjectionMemberV2
    parent_ledger_identity_sha256: str
    preparation_identity_sha256: str
    total_canonical_payload_bytes: int

    @property
    def reader_issued(self) -> Literal[False]:
        return False


def _terminal_is_exact(
    group: DailyMarketTechnicalUniverseProjectionGroupV2, builder: object,
) -> bool:
    kdj = group._kdj_collector
    volatility = group._volatility_collector
    return (
        type(group._max_stocks) is int
        and 1 <= group._max_stocks <= DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MAX_STOCKS
        and group.processed_snapshot_count <= group._max_stocks
        and type(group._max_total_bytes) is int
        and 1 <= group._max_total_bytes <= DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MAX_TOTAL_BYTES
        and group.status == "between_parents"
        and group._bound_builder is builder
        and getattr(builder, "_verified_projection", None) is group
        and group._ma_collector.source_request is group._source_request
        and kdj.source_request.ma_source_request is group._source_request
        and volatility.source_request.ma_source_request is group._source_request
        and kdj._bound_builder is builder
        and group._kdj_membership_group is not None
        and group._kdj_membership_group.contains_exact_member(kdj)
        and kdj._projection_group is group._kdj_membership_group
        and not kdj._failed and kdj._active_parent is None
        and not volatility._failed and volatility._active_segment is None
        and kdj._next_segment_index == group.completed_parent_count
        and volatility._next_segment_index == group.completed_parent_count
        and len(kdj._entries) == group.processed_snapshot_count
        and len(volatility._entries) == group.processed_snapshot_count
        and len(group._ma_collector._entries) == group.processed_snapshot_count
        and len(group._row_provenance) == group.processed_snapshot_count
    )


def _validate_callback_provenance(
    group: DailyMarketTechnicalUniverseProjectionGroupV2,
    cancel: Callable[[], object] | None,
) -> None:
    if not (
        len(group._row_provenance) == len(group._ma_collector._entries)
        == len(group._kdj_collector._entries) == len(group._volatility_collector._entries)
    ):
        _fail("technical_projection_group_v2_callback_provenance_mismatch")
    for position, (saved, ma, kdj, volatility) in enumerate(zip(
        group._row_provenance, group._ma_collector._entries,
        group._kdj_collector._entries, group._volatility_collector._entries, strict=True,
    )):
        if position % 256 == 0:
            _strict_cancel_check(cancel)
        if (
            type(saved) is not _CallbackRowProvenanceV2
            or saved.ma_entry is not ma
            or saved.kdj_entry is not kdj
            or saved.volatility_entry is not volatility
            or not (saved.snapshot_identity_sha256 == ma.snapshot_identity_sha256 == kdj.snapshot_identity_sha256 == volatility.snapshot_identity_sha256)
            or not (saved.source_pin_sha256 == kdj.source_pin_sha256 == volatility.source_pin_sha256)
            or not (saved.raw_source_window_fingerprint_sha256 == ma.raw_source_window_fingerprint_sha256 == kdj.raw_source_window_fingerprint_sha256 == volatility.raw_source_window_fingerprint_sha256)
            or not (saved.source_clock_sha256 == ma.source_clock_identity_sha256 == kdj.source_clock_sha256 == volatility.source_clock_sha256)
        ):
            _fail("technical_projection_group_v2_callback_provenance_mismatch")
    _strict_cancel_check(cancel)


def _prepare_member(
    entries: tuple[_MemberEntry, ...], request: dict[str, object],
    completed_parent_count: int, limit: int,
    cancel: Callable[[], object] | None,
) -> _PreparedProjectionMemberV2:
    request_json = json.dumps(
        request, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    )
    body: dict[str, object] = {
        "schema_version": "daily-market-technical-projection-member-preparation.v2",
        "source_request": request,
        "completed_parent_count": completed_parent_count,
        "collected_count": len(entries),
        "entries": entries,
        "reader_issued": False,
        "source_available_at": None,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
    }
    identity, body_bytes = _digest_payload(body, limit, cancel)
    # Canonical transport 的 identity 欄位也納入上限；逗號、key、引號皆計數。
    payload_bytes = _identified_payload_size(body_bytes, "body_identity_sha256")
    if payload_bytes > limit:
        _fail("technical_projection_group_v2_prepared_payload_limit")
    return _PreparedProjectionMemberV2(entries, request_json, identity, payload_bytes)


def _prepare_projection_group_v2(
    group: object, builder: object, bundle_state: object, base_query: object,
    selection: object, *, cancel_callback: Callable[[], object] | None = None,
) -> _PreparedProjectionGroupV2:
    """僅由後續共同 reader 發行層使用；目前回傳永遠未授資格的材料。"""
    if type(group) is not DailyMarketTechnicalUniverseProjectionGroupV2:
        _fail("technical_projection_group_v2_prepare_group_invalid")
    try:
        budgets = (
            group._max_stocks, group._max_total_bytes,
            group._kdj_collector.max_index_bytes, group._volatility_collector.max_index_bytes,
        )
        if not _terminal_is_exact(group, builder):
            _fail("technical_projection_group_v2_prepare_terminal_invalid")

        def check_cancel() -> bool:
            _strict_cancel_check(group._cancel_callback)
            _strict_cancel_check(cancel_callback)
            return False

        _validate_callback_provenance(group, check_cancel)
        ma = group._ma_collector._prepare_for_projection_group(
            group, builder, bundle_state, base_query, selection,
            cancel_callback=check_cancel,
        )
        kdj_entries = tuple(group._kdj_collector._entries)
        volatility_entries = tuple(group._volatility_collector._entries)
        if not (
            len(ma.index.entries) == len(kdj_entries) == len(volatility_entries)
            == ma.request.included_count == group.processed_snapshot_count
            and len(ma.parent_observations) == group.completed_parent_count
        ):
            _fail("technical_projection_group_v2_prepare_population_mismatch")
        for position, (ma_row, kdj, volatility) in enumerate(
            zip(ma.index.entries, kdj_entries, volatility_entries, strict=True)
        ):
            if position % 256 == 0:
                check_cancel()
            if (
                type(kdj) is not DailyMarketTechnicalUniverseKDJCompactEntryV1
                or type(volatility) is not DailyMarketTechnicalUniverseVolatilityCompactEntryV1
                or not (ma_row.stock_code == kdj.stock_code == volatility.stock_code)
                or not (ma_row.segment_index == kdj.segment_index == volatility.segment_index)
                or not (ma_row.decision_date == kdj.decision_date == volatility.decision_date)
                or not (ma_row.source_identity == kdj.source_identity == volatility.source_identity)
                or not (
                    ma_row.snapshot_identity_sha256 == kdj.snapshot_identity_sha256
                    == volatility.snapshot_identity_sha256
                )
                or not (
                    ma_row.raw_source_window_fingerprint_sha256
                    == kdj.raw_source_window_fingerprint_sha256
                    == volatility.raw_source_window_fingerprint_sha256
                )
                or not (
                    ma_row.source_clock_identity_sha256 == kdj.source_clock_sha256
                    == volatility.source_clock_sha256
                )
                or kdj.source_pin_sha256 != volatility.source_pin_sha256
                or kdj.decision_cutoff != volatility.decision_cutoff
                or kdj.decision_cutoff.isoformat() != ma.request.decision_cutoff
            ):
                _fail("technical_projection_group_v2_prepare_row_source_mismatch")
            _digest_payload(kdj.to_dict(), DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_ENTRY_BYTES_V1, check_cancel)
            _digest_payload(volatility.to_dict(), DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_ENTRY_BYTES_V1, check_cancel)
        kdj_candidate = _prepare_member(
            kdj_entries, group._kdj_collector.source_request.to_dict(),
            group.completed_parent_count, min(DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_INDEX_BYTES_V1, budgets[2]),
            check_cancel,
        )
        volatility_candidate = _prepare_member(
            volatility_entries, group._volatility_collector.source_request.to_dict(),
            group.completed_parent_count, min(DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_INDEX_BYTES_V1, budgets[3]),
            check_cancel,
        )
        ma_digest, ma_bytes = _digest_payload(
            _ma_index_payload_references(ma.index), DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_INDEX_BYTES_V1,
            check_cancel,
        )
        ledger_digest, ledger_bytes = _digest_payload(
            ma.parent_observations, group._max_total_bytes,
            check_cancel,
        )
        envelope = {
            "schema_version": "daily-market-technical-projection-group-preparation.v2",
            "source_request": ma.request.to_dict(),
            "read_session_identity_sha256": cast(DailyMarketTechnicalUniverseV4ReadSession, ma.p01_session).read_session_identity_sha256,
            "query_identity_sha256": cast(DailyMarketTechnicalUniverseV4Query, ma.base_query).query_identity_sha256,
            "selection_identity_sha256": cast(DailyMarketTechnicalUniverseV4ReadSelection, ma.selection).selection_identity_sha256,
            "parent_ledger_identity_sha256": ledger_digest,
            "member_payload_sha256": (ma_digest, kdj_candidate.body_identity_sha256, volatility_candidate.body_identity_sha256),
            "member_payload_bytes": (ma_bytes, kdj_candidate.canonical_payload_bytes, volatility_candidate.canonical_payload_bytes),
            "reader_issued": False,
            "historical_pit_eligible": False,
        }
        identity, envelope_bytes = _digest_payload(envelope, group._max_total_bytes, check_cancel)
        envelope_bytes = _identified_payload_size(envelope_bytes, "preparation_identity_sha256")
        total = ma_bytes + kdj_candidate.canonical_payload_bytes + volatility_candidate.canonical_payload_bytes + ledger_bytes + envelope_bytes
        if total > group._max_total_bytes:
            _fail("technical_projection_group_v2_prepared_payload_limit")
        check_cancel()
        _validate_callback_provenance(group, check_cancel)
        if (
            not _terminal_is_exact(group, builder)
            or group._ma_collector._finished
            or ma.request is not group._source_request
            or budgets != (
                group._max_stocks, group._max_total_bytes,
                group._kdj_collector.max_index_bytes, group._volatility_collector.max_index_bytes,
            )
            or not all(current is pinned for current, pinned in zip(group._kdj_collector._entries, kdj_entries, strict=True))
            or not all(current is pinned for current, pinned in zip(group._volatility_collector._entries, volatility_entries, strict=True))
        ):
            _fail("technical_projection_group_v2_prepare_changed")
        return _PreparedProjectionGroupV2(
            group, ma, kdj_candidate, volatility_candidate, ledger_digest, identity, total,
        )
    except BaseException:
        group._poison()
        raise
