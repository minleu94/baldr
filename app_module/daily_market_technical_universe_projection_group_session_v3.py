"""完整 exact read 後發行的四路 projection group V3 session。"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Callable
from dataclasses import dataclass, field
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
)
from app_module.daily_market_technical_universe_price_query_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_METHOD_VERSION,
    DailyMarketTechnicalUniversePriceFactV1,
    digest_daily_market_technical_universe_price_facts_v1,
)
from app_module.daily_market_technical_universe_projection_group_prepare_v2 import (
    _PreparedProjectionMemberV2,
    _digest_payload,
    _identified_payload_size,
    _ma_index_payload_references,
    _prepare_member,
    _terminal_is_exact,
    _validate_callback_provenance,
)
from app_module.daily_market_technical_universe_projection_group_v2 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MAX_TOTAL_BYTES,
    _strict_cancel_check,
)
from app_module.daily_market_technical_universe_projection_group_v3 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V3_SCHEMA,
    DailyMarketTechnicalUniverseProjectionGroupV3,
    DailyMarketTechnicalUniverseProjectionGroupV3Error,
)
from app_module.daily_market_technical_universe_v4_query import (
    DailyMarketTechnicalUniverseV4Query,
    DailyMarketTechnicalUniverseV4ReadSelection,
    DailyMarketTechnicalUniverseV4ReadSession,
    DailyMarketTechnicalUniverseV4ReadSessionBuilder,
)
from app_module.daily_market_technical_universe_v4_store import (
    DailyMarketTechnicalUniverseV4ParentReceiptReference,
    DailyMarketTechnicalUniverseV4VerifiedState,
)
from app_module.daily_market_technical_universe_volatility_alignment_query_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_ENTRY_BYTES_V1,
    DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_INDEX_BYTES_V1,
    DailyMarketTechnicalUniverseVolatilityCompactEntryV1,
)
from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DailyMarketTechnicalOfficialDispositionBundleReferenceV1,
    DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DailyMarketTechnicalOfficialDispositionQueryV1,
)


_GROUP_SESSION_ISSUER_CAPABILITY_V3 = object()
_GROUP_SESSION_SEAL_V3 = object()


def _canonical_bytes_v3(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _parent_references_match_v3(
    prepared: _PreparedProjectionGroupV3,
    p01_session: DailyMarketTechnicalUniverseV4ReadSession,
) -> None:
    state = p01_session._state
    if type(state) is not DailyMarketTechnicalUniverseV4VerifiedState:
        raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
            "technical_projection_group_v3_p01_state_invalid"
        )
    references = state.segment_parent_references
    observations = prepared.ma.parent_observations
    expected = tuple(range(len(references)))
    if (
        len(references) != len(state.plan.segments)
        or tuple(index for index, _ in references) != expected
        or tuple(item.segment_index for item in observations) != expected
    ):
        raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
            "technical_projection_group_v3_parent_coverage_mismatch"
        )
    for observation, (segment_index, reference) in zip(observations, references, strict=True):
        if type(reference) is not DailyMarketTechnicalUniverseV4ParentReceiptReference:
            raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                "technical_projection_group_v3_parent_reference_invalid"
            )
        segment = state.plan.segment_cohort(segment_index)
        if (
            observation.segment_index != segment_index
            or observation.parent_root != reference.parent_root
            or observation.parent_plan_identity_sha256 != reference.parent_plan_identity_sha256
            or observation.parent_plan_sha256 != reference.parent_plan_sha256
            or observation.parent_receipt_identity_sha256 != reference.parent_receipt_identity_sha256
            or observation.parent_receipt_sha256 != reference.parent_receipt_sha256
            or observation.cohort_identity_sha256 != segment.cohort_identity_sha256
            or observation.included_stock_codes != segment.included_stock_codes
        ):
            raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                "technical_projection_group_v3_parent_reference_mismatch"
            )


@dataclass(frozen=True, slots=True)
class _PreparedProjectionGroupV3:
    group: DailyMarketTechnicalUniverseProjectionGroupV3
    ma: _MaPreparedPublicationV1
    kdj: _PreparedProjectionMemberV2
    volatility: _PreparedProjectionMemberV2
    price_facts: tuple[DailyMarketTechnicalUniversePriceFactV1, ...]
    price_index_identity_sha256: str
    price_index_bytes: int
    parent_ledger_identity_sha256: str
    preparation_identity_sha256: str
    total_canonical_payload_bytes: int

    @property
    def reader_issued(self) -> Literal[False]:
        return False


def _validate_price_fact_members_v3(
    group: DailyMarketTechnicalUniverseProjectionGroupV3,
    ma_entries: tuple[DailyMarketTechnicalMaAlignmentCompactEntryV1, ...],
    kdj_entries: tuple[DailyMarketTechnicalUniverseKDJCompactEntryV1, ...],
    volatility_entries: tuple[DailyMarketTechnicalUniverseVolatilityCompactEntryV1, ...],
    cancel: Callable[[], object] | None,
) -> tuple[DailyMarketTechnicalUniversePriceFactV1, ...]:
    facts = group.price_facts
    if not (
        len(facts) == len(ma_entries) == len(kdj_entries) == len(volatility_entries)
        and tuple(fact.stock_code for fact in facts)
        == tuple(entry.stock_code for entry in ma_entries)
    ):
        raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
            "technical_projection_group_v3_price_population_mismatch"
        )
    for position, (fact, ma, kdj, volatility) in enumerate(
        zip(facts, ma_entries, kdj_entries, volatility_entries, strict=True)
    ):
        if position % 256 == 0:
            _strict_cancel_check(cancel)
        if (
            type(fact) is not DailyMarketTechnicalUniversePriceFactV1
            or not (
                fact.stock_code == ma.stock_code == kdj.stock_code == volatility.stock_code
            )
            or not (
                fact.snapshot_identity_sha256
                == ma.snapshot_identity_sha256
                == kdj.snapshot_identity_sha256
                == volatility.snapshot_identity_sha256
            )
            or not (
                fact.source_identity == ma.source_identity == kdj.source_identity
                == volatility.source_identity
            )
            or fact.observation_date is not None and fact.observation_date > ma.decision_date
        ):
            raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                "technical_projection_group_v3_price_row_identity_mismatch"
            )
        if fact.status == "unknown" and not fact.reason_codes:
            raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                "technical_projection_group_v3_price_unknown_reason_missing"
            )
    _strict_cancel_check(cancel)
    return facts


def _prepare_projection_group_v3(
    group: object,
    builder: object,
    bundle_state: object,
    base_query: object,
    selection: object,
    *,
    cancel_callback: Callable[[], object] | None = None,
) -> _PreparedProjectionGroupV3:
    """建立未授資格的四路候選材料；只接受 V3 exact observer。"""

    if type(group) is not DailyMarketTechnicalUniverseProjectionGroupV3:
        raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
            "technical_projection_group_v3_prepare_group_invalid"
        )
    try:
        budgets = (
            group._max_stocks,
            group._max_total_bytes,
            group._kdj_collector.max_index_bytes,
            group._volatility_collector.max_index_bytes,
            group._max_price_index_bytes,
        )
        if not _terminal_is_exact(group, builder):
            raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                "technical_projection_group_v3_prepare_terminal_invalid"
            )

        def check_cancel() -> bool:
            _strict_cancel_check(group._cancel_callback)
            _strict_cancel_check(cancel_callback)
            return False

        _validate_callback_provenance(group, check_cancel)
        # V2 的 wrapper 限定 exact V2 type；V3 直接沿用其相同的 MA 驗證器，
        # registered_projection 仍是本次唯一綁定的 V3 observer。
        ma = group._ma_collector._prepare_verified_publication(
            builder,
            bundle_state,
            base_query,
            selection,
            registered_projection=group,
            cancel_callback=check_cancel,
        )
        kdj_entries = tuple(group._kdj_collector._entries)
        volatility_entries = tuple(group._volatility_collector._entries)
        ma_entries = tuple(ma.index.entries)
        price_facts = _validate_price_fact_members_v3(
            group, ma_entries, kdj_entries, volatility_entries, check_cancel,
        )
        if not (
            len(ma_entries) == len(kdj_entries) == len(volatility_entries)
            == ma.request.included_count == group.processed_snapshot_count
            and len(ma.parent_observations) == group.completed_parent_count
        ):
            raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                "technical_projection_group_v3_prepare_population_mismatch"
            )
        for position, (ma_row, kdj, volatility) in enumerate(
            zip(ma_entries, kdj_entries, volatility_entries, strict=True)
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
                raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                    "technical_projection_group_v3_member_source_mismatch"
                )
            _digest_payload(
                kdj.to_dict(), DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_ENTRY_BYTES_V1,
                check_cancel,
            )
            _digest_payload(
                volatility.to_dict(),
                DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_ENTRY_BYTES_V1,
                check_cancel,
            )

        price_index_identity, price_index_bytes = digest_daily_market_technical_universe_price_facts_v1(
            price_facts,
            maximum_bytes=min(group._max_price_index_bytes, group._max_total_bytes),
            cancel_callback=check_cancel,
        )
        if price_index_bytes != group.price_fact_bytes:
            raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                "technical_projection_group_v3_price_index_byte_accounting_mismatch"
            )

        kdj_candidate = _prepare_member(
            kdj_entries,
            group._kdj_collector.source_request.to_dict(),
            group.completed_parent_count,
            min(DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_INDEX_BYTES_V1, budgets[2]),
            check_cancel,
        )
        volatility_candidate = _prepare_member(
            volatility_entries,
            group._volatility_collector.source_request.to_dict(),
            group.completed_parent_count,
            min(DAILY_MARKET_TECHNICAL_UNIVERSE_VOLATILITY_MAX_INDEX_BYTES_V1, budgets[3]),
            check_cancel,
        )
        ma_digest, ma_bytes = _digest_payload(
            _ma_index_payload_references(ma.index),
            DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_MAX_INDEX_BYTES_V1,
            check_cancel,
        )
        ledger_digest, ledger_bytes = _digest_payload(
            ma.parent_observations, group._max_total_bytes, check_cancel,
        )
        envelope = {
            "schema_version": "daily-market-technical-projection-group-preparation.v3",
            "source_request": ma.request.to_dict(),
            "read_session_identity_sha256": cast(
                DailyMarketTechnicalUniverseV4ReadSession, ma.p01_session,
            ).read_session_identity_sha256,
            "query_identity_sha256": cast(
                DailyMarketTechnicalUniverseV4Query, ma.base_query,
            ).query_identity_sha256,
            "selection_identity_sha256": cast(
                DailyMarketTechnicalUniverseV4ReadSelection, ma.selection,
            ).selection_identity_sha256,
            "parent_ledger_identity_sha256": ledger_digest,
            "member_payload_sha256": (
                ma_digest,
                kdj_candidate.body_identity_sha256,
                volatility_candidate.body_identity_sha256,
                price_index_identity,
            ),
            "member_payload_bytes": (
                ma_bytes,
                kdj_candidate.canonical_payload_bytes,
                volatility_candidate.canonical_payload_bytes,
                price_index_bytes,
            ),
            "price_method_version": DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_METHOD_VERSION,
            "reader_issued": False,
            "historical_pit_eligible": False,
        }
        identity, envelope_bytes = _digest_payload(
            envelope, group._max_total_bytes, check_cancel,
        )
        envelope_bytes = _identified_payload_size(envelope_bytes, "preparation_identity_sha256")
        total = (
            ma_bytes
            + kdj_candidate.canonical_payload_bytes
            + volatility_candidate.canonical_payload_bytes
            + price_index_bytes
            + ledger_bytes
            + envelope_bytes
        )
        if total > group._max_total_bytes:
            raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                "technical_projection_group_v3_prepared_payload_limit"
            )
        check_cancel()
        _validate_callback_provenance(group, check_cancel)
        if (
            not _terminal_is_exact(group, builder)
            or group._ma_collector._finished
            or ma.request is not group._source_request
            or budgets != (
                group._max_stocks,
                group._max_total_bytes,
                group._kdj_collector.max_index_bytes,
                group._volatility_collector.max_index_bytes,
                group._max_price_index_bytes,
            )
            or tuple(group.price_facts) != price_facts
            or not all(
                current is pinned
                for current, pinned in zip(group._kdj_collector._entries, kdj_entries, strict=True)
            )
            or not all(
                current is pinned
                for current, pinned in zip(group._volatility_collector._entries, volatility_entries, strict=True)
            )
        ):
            raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                "technical_projection_group_v3_prepare_changed"
            )
        return _PreparedProjectionGroupV3(
            group=group,
            ma=ma,
            kdj=kdj_candidate,
            volatility=volatility_candidate,
            price_facts=price_facts,
            price_index_identity_sha256=price_index_identity,
            price_index_bytes=price_index_bytes,
            parent_ledger_identity_sha256=ledger_digest,
            preparation_identity_sha256=identity,
            total_canonical_payload_bytes=total,
        )
    except BaseException:
        group._poison()
        raise


def _build_issue_payload_v3(
    prepared: _PreparedProjectionGroupV3,
    outer_query: DailyMarketTechnicalOfficialDispositionQueryV1,
) -> dict[str, object]:
    ma = prepared.ma
    index = ma.index
    bundle_state = cast(DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1, ma.bundle_state)
    p01_session = cast(DailyMarketTechnicalUniverseV4ReadSession, ma.p01_session)
    base_query = cast(DailyMarketTechnicalUniverseV4Query, ma.base_query)
    selection = cast(DailyMarketTechnicalUniverseV4ReadSelection, ma.selection)
    price_known_count = sum(fact.status == "known" for fact in prepared.price_facts)
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V3_SCHEMA,
        "source_request": ma.request.to_dict(),
        "bundle_reference": {
            "output_root": bundle_state.reference.output_root,
            "bundle_identity_sha256": bundle_state.reference.bundle_identity_sha256,
            "manifest_sha256": bundle_state.reference.manifest_sha256,
        },
        "p01_read_session_identity_sha256": p01_session.read_session_identity_sha256,
        "base_query_identity_sha256": base_query.query_identity_sha256,
        "selection_identity_sha256": selection.selection_identity_sha256,
        "outer_query_identity_sha256": outer_query.query_identity_sha256,
        "parent_ledger_identity_sha256": prepared.parent_ledger_identity_sha256,
        "preparation_identity_sha256": prepared.preparation_identity_sha256,
        "member_views": {
            "ma": {
                "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_INDEX_V1_SCHEMA,
                "method_id": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1,
                "method_version": DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1,
                "index_identity_sha256": index.index_identity_sha256,
                "population_counts": index.counts.to_dict(),
            },
            "kdj": {
                "source_request": json.loads(prepared.kdj.source_request_json),
                "body_identity_sha256": prepared.kdj.body_identity_sha256,
                "canonical_payload_bytes": prepared.kdj.canonical_payload_bytes,
                "entry_count": len(prepared.kdj.entries),
            },
            "volatility": {
                "source_request": json.loads(prepared.volatility.source_request_json),
                "body_identity_sha256": prepared.volatility.body_identity_sha256,
                "canonical_payload_bytes": prepared.volatility.canonical_payload_bytes,
                "entry_count": len(prepared.volatility.entries),
            },
            "price": {
                "method_version": DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_METHOD_VERSION,
                "index_identity_sha256": prepared.price_index_identity_sha256,
                "canonical_payload_bytes": prepared.price_index_bytes,
                "entry_count": len(prepared.price_facts),
                "known_count": price_known_count,
                "unknown_count": len(prepared.price_facts) - price_known_count,
            },
        },
        "prepared_total_canonical_payload_bytes": prepared.total_canonical_payload_bytes,
        "availability_status": "unknown",
        "source_available_at": None,
        "historical_pit_eligible": False,
    }


@dataclass(frozen=True, slots=True)
class _ProjectionGroupSessionAnchorV3:
    capability: object
    identity_sha256: str
    canonical_payload_bytes: int
    prepared: _PreparedProjectionGroupV3 = field(repr=False, compare=False)
    group: DailyMarketTechnicalUniverseProjectionGroupV3 = field(repr=False, compare=False)
    bundle_state: DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1 = field(repr=False, compare=False)
    bundle_reference: DailyMarketTechnicalOfficialDispositionBundleReferenceV1 = field(repr=False, compare=False)
    p01_session: DailyMarketTechnicalUniverseV4ReadSession = field(repr=False, compare=False)
    base_query: DailyMarketTechnicalUniverseV4Query = field(repr=False, compare=False)
    selection: DailyMarketTechnicalUniverseV4ReadSelection = field(repr=False, compare=False)
    outer_query: DailyMarketTechnicalOfficialDispositionQueryV1 = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True, init=False)
class DailyMarketTechnicalUniverseProjectionGroupSessionV3:
    """只能由 V3 exact reader 發行的同 callback 四路唯讀 projection。"""

    _anchor: _ProjectionGroupSessionAnchorV3 = field(repr=False, compare=False)
    _issuer_capability: object = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        self._require_active()

    def _require_active(self) -> _ProjectionGroupSessionAnchorV3:
        anchor = getattr(self, "_anchor", None)
        if (
            getattr(self, "_seal", None) is not _GROUP_SESSION_SEAL_V3
            or getattr(self, "_issuer_capability", None) is not _GROUP_SESSION_ISSUER_CAPABILITY_V3
            or type(anchor) is not _ProjectionGroupSessionAnchorV3
            or anchor.capability is not _GROUP_SESSION_ISSUER_CAPABILITY_V3
            or anchor.group._failed
            or anchor.prepared.group is not anchor.group
            or tuple(anchor.group.price_facts) != anchor.prepared.price_facts
        ):
            raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                "technical_projection_group_session_v3_poisoned_or_not_reader_issued"
            )
        payload = _build_issue_payload_v3(anchor.prepared, anchor.outer_query)
        if (
            hashlib.sha256(_canonical_bytes_v3(payload)).hexdigest() != anchor.identity_sha256
            or anchor.canonical_payload_bytes
            != len(_canonical_bytes_v3({**payload, "group_session_identity_sha256": anchor.identity_sha256}))
        ):
            raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                "technical_projection_group_session_v3_identity_mismatch"
            )
        return anchor

    @property
    def reader_issued(self) -> Literal[True]:
        self._require_active()
        return True

    @property
    def identity_sha256(self) -> str:
        return self._require_active().identity_sha256

    @property
    def canonical_payload_bytes(self) -> int:
        return self._require_active().canonical_payload_bytes

    @property
    def source_available_at(self) -> None:
        self._require_active()
        return None

    @property
    def availability_status(self) -> str:
        self._require_active()
        return "unknown"

    @property
    def historical_pit_eligible(self) -> bool:
        self._require_active()
        return False

    @property
    def p01_read_session_identity_sha256(self) -> str:
        return self._require_active().p01_session.read_session_identity_sha256

    @property
    def bundle_identity_sha256(self) -> str:
        return self._require_active().bundle_reference.bundle_identity_sha256

    @property
    def outer_query_identity_sha256(self) -> str:
        return self._require_active().outer_query.query_identity_sha256

    @property
    def exact_f17_query(self) -> DailyMarketTechnicalOfficialDispositionQueryV1:
        """回傳本次 sealed group 已核的原查詢，不重新開來源。"""
        return self._require_active().outer_query

    @property
    def ma_index(self) -> DailyMarketTechnicalMaAlignmentCompactIndexV1:
        return self._require_active().prepared.ma.index

    @property
    def kdj_entries(self) -> tuple[DailyMarketTechnicalUniverseKDJCompactEntryV1, ...]:
        return cast(
            tuple[DailyMarketTechnicalUniverseKDJCompactEntryV1, ...],
            self._require_active().prepared.kdj.entries,
        )

    @property
    def volatility_entries(self) -> tuple[DailyMarketTechnicalUniverseVolatilityCompactEntryV1, ...]:
        return cast(
            tuple[DailyMarketTechnicalUniverseVolatilityCompactEntryV1, ...],
            self._require_active().prepared.volatility.entries,
        )

    @property
    def price_facts(self) -> tuple[DailyMarketTechnicalUniversePriceFactV1, ...]:
        return self._require_active().prepared.price_facts

    @property
    def price_index_identity_sha256(self) -> str:
        return self._require_active().prepared.price_index_identity_sha256

    @property
    def price_index_bytes(self) -> int:
        return self._require_active().prepared.price_index_bytes

    @property
    def parent_segment_indexes(self) -> tuple[int, ...]:
        return tuple(
            item.segment_index
            for item in self._require_active().prepared.ma.parent_observations
        )

    def price_fact_for_code(self, stock_code: str) -> DailyMarketTechnicalUniversePriceFactV1 | None:
        facts = self.price_facts
        codes = tuple(fact.stock_code for fact in facts)
        position = bisect_left(codes, stock_code)
        if position < len(facts) and facts[position].stock_code == stock_code:
            return facts[position]
        return None

    def to_dict(self) -> dict[str, object]:
        anchor = self._require_active()
        payload = _build_issue_payload_v3(anchor.prepared, anchor.outer_query)
        return {**payload, "group_session_identity_sha256": anchor.identity_sha256}


def _prepare_and_issue_projection_group_session_v3(
    group: DailyMarketTechnicalUniverseProjectionGroupV3,
    builder: DailyMarketTechnicalUniverseV4ReadSessionBuilder,
    bundle_state: DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
    base_query: DailyMarketTechnicalUniverseV4Query,
    selection: DailyMarketTechnicalUniverseV4ReadSelection,
    *,
    outer_query: DailyMarketTechnicalOfficialDispositionQueryV1,
    cancel_callback: Callable[[], object] | None = None,
) -> DailyMarketTechnicalUniverseProjectionGroupSessionV3:
    """全 cohort exact 回讀完成後才建立 V3 reader-issued seal。"""

    if not (
        type(group) is DailyMarketTechnicalUniverseProjectionGroupV3
        and type(builder) is DailyMarketTechnicalUniverseV4ReadSessionBuilder
        and type(bundle_state) is DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1
        and type(base_query) is DailyMarketTechnicalUniverseV4Query
        and type(selection) is DailyMarketTechnicalUniverseV4ReadSelection
        and type(outer_query) is DailyMarketTechnicalOfficialDispositionQueryV1
    ):
        raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
            "technical_projection_group_session_v3_issue_inputs_invalid"
        )
    if group._failed or group._ma_collector._finished:
        raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
            "technical_projection_group_session_v3_group_failed_or_already_issued"
        )
    try:
        if (
            group._bound_builder is not builder
            or builder._verified_projection is not group
            or builder.verified_session is None
            or group._cancel_callback is not cancel_callback
        ):
            raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                "technical_projection_group_session_v3_builder_binding_invalid"
            )
        _strict_cancel_check(cancel_callback)
        prepared = _prepare_projection_group_v3(
            group, builder, bundle_state, base_query, selection,
            cancel_callback=cancel_callback,
        )
        p01_session = cast(DailyMarketTechnicalUniverseV4ReadSession, prepared.ma.p01_session)
        counts = p01_session.source_counts
        if (
            prepared.group is not group
            or prepared.ma.builder is not builder
            or prepared.ma.bundle_state is not bundle_state
            or prepared.ma.p01_session is not builder.verified_session
            or prepared.ma.base_query is not base_query
            or prepared.ma.selection is not selection
            or prepared.ma.request is not group._source_request
            or bundle_state.reference != prepared.ma.bundle_state.reference
            or prepared.ma.request.bundle_output_root != bundle_state.reference.output_root
            or prepared.ma.request.bundle_identity_sha256 != bundle_state.reference.bundle_identity_sha256
            or prepared.ma.request.expected_manifest_sha256 != bundle_state.reference.manifest_sha256
            or outer_query.bundle_output_root != bundle_state.reference.output_root
            or outer_query.bundle_identity_sha256 != bundle_state.reference.bundle_identity_sha256
            or outer_query.expected_manifest_sha256 != bundle_state.reference.manifest_sha256
            or not p01_session.matches_source(outer_query.technical_query)
        ):
            raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                "technical_projection_group_session_v3_source_binding_mismatch"
            )
        state = p01_session._state
        if type(state) is not DailyMarketTechnicalUniverseV4VerifiedState:
            raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                "technical_projection_group_session_v3_p01_state_invalid"
            )
        full_codes = tuple(
            code
            for segment_index in range(len(state.plan.segments))
            for code in state.plan.segment_cohort(segment_index).included_stock_codes
        )
        if full_codes != tuple(sorted(set(full_codes))):
            raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                "technical_projection_group_session_v3_population_order_invalid"
            )
        if (
            counts.included_count != counts.processed_count
            or counts.pending_count != 0
            or len(full_codes) != counts.included_count
            or len(prepared.ma.index.entries) != counts.processed_count
            or len(prepared.kdj.entries) != counts.processed_count
            or len(prepared.volatility.entries) != counts.processed_count
            or len(prepared.price_facts) != counts.processed_count
            or tuple(item.stock_code for item in prepared.ma.index.entries) != full_codes
            or tuple(item.stock_code for item in prepared.kdj.entries) != full_codes
            or tuple(item.stock_code for item in prepared.volatility.entries) != full_codes
            or tuple(item.stock_code for item in prepared.price_facts) != full_codes
        ):
            raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                "technical_projection_group_session_v3_full_population_mismatch"
            )
        _parent_references_match_v3(prepared, p01_session)
        _strict_cancel_check(group._cancel_callback)
        _strict_cancel_check(cancel_callback)
        payload = _build_issue_payload_v3(prepared, outer_query)
        body = _canonical_bytes_v3(payload)
        identity = hashlib.sha256(body).hexdigest()
        envelope_bytes = len(_canonical_bytes_v3({**payload, "group_session_identity_sha256": identity}))
        if (
            prepared.total_canonical_payload_bytes + envelope_bytes
            > min(group._max_total_bytes, DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MAX_TOTAL_BYTES)
        ):
            raise DailyMarketTechnicalUniverseProjectionGroupV3Error(
                "technical_projection_group_session_v3_payload_limit"
            )

        _strict_cancel_check(group._cancel_callback)
        _strict_cancel_check(cancel_callback)
        group._ma_collector._finished = True
        group._ma_collector._issued_session = None
        anchor = _ProjectionGroupSessionAnchorV3(
            capability=_GROUP_SESSION_ISSUER_CAPABILITY_V3,
            identity_sha256=identity,
            canonical_payload_bytes=envelope_bytes,
            prepared=prepared,
            group=group,
            bundle_state=bundle_state,
            bundle_reference=bundle_state.reference,
            p01_session=p01_session,
            base_query=base_query,
            selection=selection,
            outer_query=outer_query,
        )
        session = object.__new__(DailyMarketTechnicalUniverseProjectionGroupSessionV3)
        object.__setattr__(session, "_anchor", anchor)
        object.__setattr__(session, "_issuer_capability", _GROUP_SESSION_ISSUER_CAPABILITY_V3)
        object.__setattr__(session, "_seal", _GROUP_SESSION_SEAL_V3)
        session.__post_init__()
        return session
    except BaseException:
        group._poison()
        raise


__all__ = ("DailyMarketTechnicalUniverseProjectionGroupSessionV3",)
