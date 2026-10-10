"""Opaque F17-issued view over one verified three-member projection group.

The private reader issuer binds this view to the exact verified bundle, P01
read, prepared member candidates, cancellation state, and poison lifecycle.
This is a publication boundary; it does not implement the composite query,
page, UI, or saved-recipe layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import TYPE_CHECKING, cast

from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DailyMarketTechnicalOfficialDispositionBundleReferenceV1,
    DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
)
from app_module.daily_market_technical_official_disposition_query_v1 import (
    DailyMarketTechnicalOfficialDispositionQueryV1,
)
from app_module.daily_market_technical_universe_ma_alignment_query_v1 import (
    DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_ID_V1,
    DAILY_MARKET_TECHNICAL_MA_ALIGNMENT_METHOD_VERSION_V1,
    DAILY_MARKET_TECHNICAL_UNIVERSE_MA_ALIGNMENT_INDEX_V1_SCHEMA,
    DailyMarketTechnicalMaAlignmentCompactIndexV1,
)
from app_module.daily_market_technical_universe_kdj_alignment_query_v1 import (
    DailyMarketTechnicalUniverseKDJCompactEntryV1,
)
from app_module.daily_market_technical_universe_projection_group_prepare_v2 import (
    _PreparedProjectionGroupV2,
    _prepare_projection_group_v2,
)
from app_module.daily_market_technical_universe_projection_group_v2 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MAX_TOTAL_BYTES,
    DailyMarketTechnicalUniverseProjectionGroupV2,
    _fail,
    _strict_cancel_check,
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
    DailyMarketTechnicalUniverseVolatilityCompactEntryV1,
)

if TYPE_CHECKING:
    from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
        DailyMarketTechnicalOfficialDispositionReadSessionV1,
    )


_GROUP_SESSION_ISSUER_CAPABILITY_V2 = object()
_GROUP_SESSION_SEAL_V2 = object()
_GROUP_SESSION_SCHEMA_V2 = "daily-market-technical-projection-group-session.v2"


@dataclass(frozen=True, slots=True)
class _ProjectionGroupSessionAnchorV2:
    """Exact identities plus immutable prepared views; group is lifecycle-only."""

    capability: object = field(repr=False, compare=False)
    identity_sha256: str
    canonical_payload_bytes: int
    prepared: _PreparedProjectionGroupV2 = field(repr=False, compare=False)
    group: DailyMarketTechnicalUniverseProjectionGroupV2 = field(repr=False, compare=False)
    bundle_state: DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1 = field(
        repr=False, compare=False,
    )
    bundle_reference: DailyMarketTechnicalOfficialDispositionBundleReferenceV1 = field(
        repr=False, compare=False,
    )
    p01_session: DailyMarketTechnicalUniverseV4ReadSession = field(repr=False, compare=False)
    base_query: DailyMarketTechnicalUniverseV4Query = field(repr=False, compare=False)
    selection: DailyMarketTechnicalUniverseV4ReadSelection = field(repr=False, compare=False)
    outer_query: DailyMarketTechnicalOfficialDispositionQueryV1 = field(
        repr=False, compare=False,
    )


@dataclass(frozen=True, slots=True, init=False)
class DailyMarketTechnicalUniverseProjectionGroupSessionV2:
    """One opaque reader-issued view over all three prepared full-population members.

    There is intentionally no public initializer, transport decoder, or member
    session constructor. The sole issuer is the private helper below.
    """

    _anchor: _ProjectionGroupSessionAnchorV2 = field(repr=False, compare=False)
    _issuer_capability: object = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    @property
    def reader_issued(self) -> bool:
        self._require_active()
        return True

    @property
    def identity_sha256(self) -> str:
        self._require_active()
        return self._anchor.identity_sha256

    @property
    def canonical_payload_bytes(self) -> int:
        self._require_active()
        return self._anchor.canonical_payload_bytes

    @property
    def availability_status(self) -> str:
        self._require_active()
        return "unknown"

    @property
    def source_available_at(self) -> None:
        self._require_active()
        return None

    @property
    def historical_pit_eligible(self) -> bool:
        self._require_active()
        return False

    @property
    def ma_index(self) -> DailyMarketTechnicalMaAlignmentCompactIndexV1:
        self._require_active()
        return self._anchor.prepared.ma.index

    @property
    def kdj_entries(self) -> tuple[DailyMarketTechnicalUniverseKDJCompactEntryV1, ...]:
        self._require_active()
        return cast(
            tuple[DailyMarketTechnicalUniverseKDJCompactEntryV1, ...],
            self._anchor.prepared.kdj.entries,
        )

    @property
    def volatility_entries(self) -> tuple[DailyMarketTechnicalUniverseVolatilityCompactEntryV1, ...]:
        self._require_active()
        return cast(
            tuple[DailyMarketTechnicalUniverseVolatilityCompactEntryV1, ...],
            self._anchor.prepared.volatility.entries,
        )

    def _require_active(self) -> _ProjectionGroupSessionAnchorV2:
        anchor = getattr(self, "_anchor", None)
        if (
            getattr(self, "_seal", None) is not _GROUP_SESSION_SEAL_V2
            or getattr(self, "_issuer_capability", None)
            is not _GROUP_SESSION_ISSUER_CAPABILITY_V2
            or type(anchor) is not _ProjectionGroupSessionAnchorV2
            or anchor.capability is not _GROUP_SESSION_ISSUER_CAPABILITY_V2
            or anchor.prepared.group is not anchor.group
            or anchor.group._failed
        ):
            _fail("technical_projection_group_session_poisoned_or_not_reader_issued")
        return anchor

    def _validate_f17_binding(
        self,
        *,
        bundle_state: DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
        bundle_reference: DailyMarketTechnicalOfficialDispositionBundleReferenceV1,
        technical_session: DailyMarketTechnicalUniverseV4ReadSession,
        base_query: DailyMarketTechnicalUniverseV4Query,
        selection: DailyMarketTechnicalUniverseV4ReadSelection,
        query: DailyMarketTechnicalOfficialDispositionQueryV1,
    ) -> None:
        anchor = self._require_active()
        prepared = anchor.prepared
        if (
            bundle_state is not anchor.bundle_state
            or bundle_reference is not anchor.bundle_reference
            or bundle_state.reference is not bundle_reference
            or technical_session is not anchor.p01_session
            or base_query is not anchor.base_query
            or selection is not anchor.selection
            or query is not anchor.outer_query
            or prepared.ma.bundle_state is not bundle_state
            or prepared.ma.p01_session is not technical_session
            or prepared.ma.base_query is not base_query
            or prepared.ma.selection is not selection
            or not technical_session.matches_source(query.technical_query)
        ):
            _fail("technical_projection_group_session_f17_binding_mismatch")


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _validate_parent_references(
    prepared: _PreparedProjectionGroupV2,
    p01_session: DailyMarketTechnicalUniverseV4ReadSession,
) -> None:
    state = p01_session._state
    if type(state) is not DailyMarketTechnicalUniverseV4VerifiedState:
        _fail("technical_projection_group_session_p01_state_invalid")
    references = state.segment_parent_references
    observations = prepared.ma.parent_observations
    expected_indexes = tuple(range(len(references)))
    if (
        len(references) != len(state.plan.segments)
        or tuple(index for index, _ in references) != expected_indexes
        or tuple(item.segment_index for item in observations) != expected_indexes
    ):
        _fail("technical_projection_group_session_parent_coverage_mismatch")
    for observation, (segment_index, reference) in zip(observations, references, strict=True):
        if type(reference) is not DailyMarketTechnicalUniverseV4ParentReceiptReference:
            _fail("technical_projection_group_session_parent_reference_invalid")
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
            _fail("technical_projection_group_session_parent_reference_mismatch")


def _build_issue_payload(
    prepared: _PreparedProjectionGroupV2,
    outer_query: DailyMarketTechnicalOfficialDispositionQueryV1,
) -> dict[str, object]:
    ma = prepared.ma
    index = ma.index
    request = ma.request
    bundle_state = cast(DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1, ma.bundle_state)
    p01_session = cast(DailyMarketTechnicalUniverseV4ReadSession, ma.p01_session)
    base_query = cast(DailyMarketTechnicalUniverseV4Query, ma.base_query)
    selection = cast(DailyMarketTechnicalUniverseV4ReadSelection, ma.selection)
    return {
        "schema_version": _GROUP_SESSION_SCHEMA_V2,
        "source_request": request.to_dict(),
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
        },
        "prepared_total_canonical_payload_bytes": prepared.total_canonical_payload_bytes,
        "availability_status": "unknown",
        "historical_pit_eligible": False,
    }


def _prepare_and_issue_projection_group_session_v2(
    group: DailyMarketTechnicalUniverseProjectionGroupV2,
    builder: DailyMarketTechnicalUniverseV4ReadSessionBuilder,
    bundle_state: DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
    base_query: DailyMarketTechnicalUniverseV4Query,
    selection: DailyMarketTechnicalUniverseV4ReadSelection,
    *,
    outer_query: DailyMarketTechnicalOfficialDispositionQueryV1,
) -> DailyMarketTechnicalUniverseProjectionGroupSessionV2:
    """The only issuer: prepare internally, bind all parents, poll, issue once."""
    if not (
        type(group) is DailyMarketTechnicalUniverseProjectionGroupV2
        and type(builder) is DailyMarketTechnicalUniverseV4ReadSessionBuilder
        and type(bundle_state) is DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1
        and type(base_query) is DailyMarketTechnicalUniverseV4Query
        and type(selection) is DailyMarketTechnicalUniverseV4ReadSelection
        and type(outer_query) is DailyMarketTechnicalOfficialDispositionQueryV1
    ):
        _fail("technical_projection_group_session_issue_inputs_invalid")
    if group._failed:
        _fail("technical_projection_group_session_group_failed")
    # A successful issue consumes this existing MA collector lifecycle flag.
    # Check before the poisoning try-block so a duplicate private call rejects
    # cleanly and cannot poison a previously returned group session.
    if group._ma_collector._finished:
        _fail("technical_projection_group_session_already_issued")
    try:
        if (
            group._failed
            or group._bound_builder is not builder
            or builder._verified_projection is not group
            or builder.verified_session is None
        ):
            _fail("technical_projection_group_session_builder_binding_invalid")

        # The callback is already anchored to the group. Passing None avoids
        # polling that same callback twice at every prepare checkpoint.
        prepared = _prepare_projection_group_v2(
            group, builder, bundle_state, base_query, selection,
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
            _fail("technical_projection_group_session_source_binding_mismatch")
        state = p01_session._state
        if type(state) is not DailyMarketTechnicalUniverseV4VerifiedState:
            _fail("technical_projection_group_session_p01_state_invalid")
        full_included_codes = tuple(
            code
            for segment_index in range(len(state.plan.segments))
            for code in state.plan.segment_cohort(segment_index).included_stock_codes
        )
        if full_included_codes != tuple(sorted(set(full_included_codes))):
            _fail("technical_projection_group_session_p01_population_invalid")
        if (
            counts.included_count != counts.processed_count
            or counts.pending_count != 0
            or len(full_included_codes) != counts.included_count
            or prepared.ma.index.counts.processed_count != counts.processed_count
            or len(prepared.kdj.entries) != counts.processed_count
            or len(prepared.volatility.entries) != counts.processed_count
            or tuple(item.stock_code for item in prepared.ma.index.entries) != full_included_codes
            or tuple(item.stock_code for item in prepared.kdj.entries) != full_included_codes
            or tuple(item.stock_code for item in prepared.volatility.entries) != full_included_codes
        ):
            _fail("technical_projection_group_session_full_population_mismatch")

        _validate_parent_references(prepared, p01_session)
        payload = _build_issue_payload(prepared, outer_query)
        body = _canonical_bytes(payload)
        identity = hashlib.sha256(body).hexdigest()
        sealed_payload = {**payload, "group_session_identity_sha256": identity}
        envelope_bytes = len(_canonical_bytes(sealed_payload))
        if (
            prepared.total_canonical_payload_bytes + envelope_bytes
            > min(group._max_total_bytes, DAILY_MARKET_TECHNICAL_UNIVERSE_PROJECTION_GROUP_V2_MAX_TOTAL_BYTES)
        ):
            _fail("technical_projection_group_session_payload_limit")

        # This is the final cancellation point. No callback or member issue is
        # run between this poll, the opaque group seal, and F17 outer return.
        _strict_cancel_check(group._cancel_callback)
        group._ma_collector._finished = True
        group._ma_collector._issued_session = None
        anchor = _ProjectionGroupSessionAnchorV2(
            capability=_GROUP_SESSION_ISSUER_CAPABILITY_V2,
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
        session = object.__new__(DailyMarketTechnicalUniverseProjectionGroupSessionV2)
        object.__setattr__(session, "_anchor", anchor)
        object.__setattr__(session, "_issuer_capability", _GROUP_SESSION_ISSUER_CAPABILITY_V2)
        object.__setattr__(session, "_seal", _GROUP_SESSION_SEAL_V2)
        return session
    except BaseException:
        group._poison()
        raise


__all__ = ("DailyMarketTechnicalUniverseProjectionGroupSessionV2",)
