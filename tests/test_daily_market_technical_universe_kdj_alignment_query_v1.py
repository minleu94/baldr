"""F03 KDJ collector skeleton 的純合約測試；不代表來源資格或 full-N 接線。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import hashlib
from pathlib import Path
from typing import Literal, cast
from zoneinfo import ZoneInfo

import pytest

import app_module.daily_market_technical_universe_kdj_alignment_query_v1 as kdj_query_module
from app_module.daily_market_technical_kdj_evidence_v1 import (
    KDJ_METHOD_IDENTITY_SHA256_V1,
    KDJ_METHOD_ID_V1,
    KDJ_METHOD_VERSION_V1,
    DailyMarketTechnicalKDJDayV1,
    DailyMarketTechnicalKDJEvidenceV1,
)
from app_module.daily_market_technical_universe_kdj_alignment_query_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_INDEX_BYTES_V1,
    DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_SOURCE_REQUEST_BYTES_V1,
    DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_STOCKS_V1,
    DailyMarketTechnicalKDJProjectionCollectorV1,
    DailyMarketTechnicalUniverseKDJCompactEntryV1,
    DailyMarketTechnicalUniverseKDJQueryV1Error,
    DailyMarketTechnicalUniverseKDJSourceRequestV1,
    DailyMarketTechnicalVerifiedProjectionGroupV1,
)
from app_module.daily_market_technical_universe_ma_alignment_query_v1 import (
    DailyMarketTechnicalMaAlignmentSourceRequestV1,
    DailyMarketTechnicalMaAlignmentVerifiedCollectorV1,
    DailyMarketTechnicalUniverseMaAlignmentQueryV1Error,
)
from app_module.daily_market_technical_universe_v4_query import (
    DailyMarketTechnicalUniverseV4ReadSessionBuilder,
)
from app_module.daily_market_technical_feature_snapshot_v4 import (
    DailyMarketTechnicalFeatureSnapshotV4,
)
from app_module.daily_market_technical_parent_v4_query import DailyMarketTechnicalParentV4Row
from app_module.rule_research_technical_parent_capture_v4 import (
    DailyMarketTechnicalParentCaptureV4VerifiedRead,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_DECISION_DATE = date(2026, 10, 8)
_CUTOFF = datetime.combine(_DECISION_DATE, time(16, 0), tzinfo=_TAIPEI)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _ma_request(root: Path, *, included: int = 2, declared: int = 2) -> DailyMarketTechnicalMaAlignmentSourceRequestV1:
    bundle_identity = _sha("bundle")
    return DailyMarketTechnicalMaAlignmentSourceRequestV1(
        bundle_output_root=str(root),
        bundle_identity_sha256=bundle_identity,
        manifest_relative_path=f"manifests/{bundle_identity}.json",
        expected_manifest_sha256=_sha("manifest"),
        technical_store_output_root=str(root),
        generation_identity_sha256=_sha("generation"),
        plan_identity_sha256=_sha("plan-identity"),
        plan_sha256=_sha("plan-bytes"),
        receipt_identity_sha256=_sha("receipt-identity"),
        receipt_sha256=_sha("receipt-bytes"),
        cohort_identity_sha256=_sha("cohort"),
        source_clock_identity_sha256=_sha("source-clock"),
        method_contracts_sha256=_sha("method-contracts"),
        market_assignment_pin_identity_sha256=_sha("market-pin"),
        official_disposal_pin_identity_sha256=_sha("disposal-pin"),
        decision_date=_DECISION_DATE,
        decision_cutoff=_CUTOFF.isoformat(),
        declared_count=declared,
        included_count=included,
        excluded_count=declared - included,
        source_coverage_status="complete",
        source_coverage_incomplete_reason_count=0,
        technical_receipt_status="complete",
    )


def _source_request(root: Path) -> DailyMarketTechnicalUniverseKDJSourceRequestV1:
    return DailyMarketTechnicalUniverseKDJSourceRequestV1.from_ma_source_request(
        _ma_request(root),
    )


def _evidence(
    *,
    stock_code: str = "2382",
    source_identity: str = "synthetic-source",
    input_count: int = 14,
) -> DailyMarketTechnicalKDJEvidenceV1:
    previous_date = _DECISION_DATE - timedelta(days=1)
    previous = DailyMarketTechnicalKDJDayV1(
        feature_date=previous_date,
        source_row_fingerprint_sha256=_sha("row-previous"),
        rsv=Decimal("40"),
        k=Decimal("30"),
        d=Decimal("20"),
        j=Decimal("50"),
    )
    current = DailyMarketTechnicalKDJDayV1(
        feature_date=_DECISION_DATE,
        source_row_fingerprint_sha256=_sha("row-current"),
        rsv=Decimal("60"),
        k=Decimal("45"),
        d=Decimal("35"),
        j=Decimal("65"),
    )
    dates = tuple(
        _DECISION_DATE - timedelta(days=input_count - index - 1)
        for index in range(input_count)
    )
    return DailyMarketTechnicalKDJEvidenceV1(
        stock_code=stock_code,
        decision_date=_DECISION_DATE,
        decision_cutoff=_CUTOFF,
        source_id="synthetic-kdj-source",
        source_identity=source_identity,
        source_clock_sha256=_sha("source-clock"),
        source_pin_sha256=_sha("source-pin"),
        raw_source_window_fingerprint_sha256=_sha("raw-window"),
        snapshot_identity_sha256=_sha("snapshot"),
        state="match",
        reason_codes=(),
        previous=previous,
        current=current,
        input_feature_dates=dates,
        input_row_fingerprints_sha256=tuple(_sha(f"input-{index}") for index in range(input_count)),
        warmup_required_sessions=14,
        warmup_observed_sessions=input_count,
        warmup_contiguous=input_count == 14,
        observed_prefix_contiguous=True,
        method_id=KDJ_METHOD_ID_V1,
        method_version=KDJ_METHOD_VERSION_V1,
        decimal_precision=34,
        decimal_rounding="ROUND_HALF_EVEN",
    )


def _expect_code(expected: str, operation: object) -> None:
    assert callable(operation)
    with pytest.raises(DailyMarketTechnicalUniverseKDJQueryV1Error) as raised:
        operation()  # type: ignore[operator]
    assert raised.value.code == expected


def test_request_is_metadata_unverified_and_identity_checked(tmp_path: Path) -> None:
    request = _source_request(tmp_path)
    payload = request.to_dict()

    assert payload["verification_status"] == "metadata_unverified"
    assert payload["source_available_at"] is None
    assert payload["availability_status"] == "unknown"
    assert payload["historical_pit_eligible"] is False
    assert payload["kdj_method_id"] == KDJ_METHOD_ID_V1
    assert payload["kdj_method_version"] == KDJ_METHOD_VERSION_V1
    assert payload["kdj_method_identity_sha256"] == KDJ_METHOD_IDENTITY_SHA256_V1

    _expect_code(
        "technical_kdj_source_request_identity_mismatch",
        lambda: replace(request, request_identity_sha256="0" * 64),
    )


def test_source_request_byte_limit_and_collector_budget_are_hard_bounds(tmp_path: Path) -> None:
    request = _source_request(tmp_path)
    long_ma_request = replace(
        request.ma_source_request,
        bundle_output_root="C:\\" + ("x" * DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_SOURCE_REQUEST_BYTES_V1),
    )
    _expect_code(
        "technical_kdj_source_request_byte_limit",
        lambda: DailyMarketTechnicalUniverseKDJSourceRequestV1.from_ma_source_request(
            long_ma_request,
        ),
    )

    _expect_code(
        "technical_kdj_collector_budget_invalid",
        lambda: DailyMarketTechnicalKDJProjectionCollectorV1(request, max_stocks=0),
    )
    _expect_code(
        "technical_kdj_collector_budget_invalid",
        lambda: DailyMarketTechnicalKDJProjectionCollectorV1(
            request,
            max_stocks=DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_STOCKS_V1 + 1,
        ),
    )
    _expect_code(
        "technical_kdj_collector_budget_invalid",
        lambda: DailyMarketTechnicalKDJProjectionCollectorV1(
            request,
            max_index_bytes=DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_INDEX_BYTES_V1 + 1,
        ),
    )


def test_compact_entry_keeps_only_bounded_unqualified_facts(tmp_path: Path) -> None:
    entry = DailyMarketTechnicalUniverseKDJCompactEntryV1.from_unqualified_evidence(
        0,
        _evidence(),
    )
    payload = entry.to_dict()

    assert payload["verification_status"] == "projection_unqualified"
    assert payload["source_available_at"] is None
    assert payload["availability_status"] == "unknown"
    assert payload["historical_pit_eligible"] is False
    assert payload["input_row_count"] == 14
    assert "input_row_fingerprints_sha256" not in payload
    assert len(entry.compact_identity_sha256) == 64

    _expect_code(
        "technical_kdj_compact_window_invalid",
        lambda: DailyMarketTechnicalUniverseKDJCompactEntryV1.from_unqualified_evidence(
            0,
            _evidence(input_count=15),
        ),
    )
    _expect_code(
        "technical_kdj_compact_evidence_bounds_invalid",
        lambda: DailyMarketTechnicalUniverseKDJCompactEntryV1.from_unqualified_evidence(
            0,
            _evidence(source_identity="x" * 257),
        ),
    )
    _expect_code(
        "technical_kdj_compact_evidence_invalid",
        lambda: DailyMarketTechnicalUniverseKDJCompactEntryV1.from_unqualified_evidence(
            0,
            replace(_evidence(), reader_qualified=cast(Literal[False], True)),
        ),
    )


def test_compact_entry_budget_counts_final_identity_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = DailyMarketTechnicalUniverseKDJCompactEntryV1.from_unqualified_evidence(
        0,
        _evidence(),
    )
    body_size = len(kdj_query_module._canonical_json_bytes(entry._body()))
    final_size = len(kdj_query_module._canonical_json_bytes(entry.to_dict()))
    assert body_size < final_size

    # 以較小的測試預算製造 body 可容納、附加 identity 後超限的邊界。
    monkeypatch.setattr(
        kdj_query_module,
        "DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_ENTRY_BYTES_V1",
        body_size + 1,
    )
    assert body_size <= kdj_query_module.DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_ENTRY_BYTES_V1
    assert final_size > kdj_query_module.DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_ENTRY_BYTES_V1
    with pytest.raises(DailyMarketTechnicalUniverseKDJQueryV1Error) as raised:
        replace(entry)
    assert raised.value.code == "technical_kdj_compact_entry_byte_limit"


def test_source_request_budget_counts_final_identity_payload(tmp_path: Path) -> None:
    limit = DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_MAX_SOURCE_REQUEST_BYTES_V1

    def sizes(extra_chars: int) -> tuple[int, int, DailyMarketTechnicalMaAlignmentSourceRequestV1]:
        long_root = Path(f"{tmp_path}\\{'x' * extra_chars}")
        ma_request = _ma_request(long_root)
        body: dict[str, object] = {
            "schema_version": kdj_query_module.DAILY_MARKET_TECHNICAL_UNIVERSE_KDJ_SOURCE_REQUEST_V1_SCHEMA,
            "verification_status": "metadata_unverified",
            "ma_source_request": ma_request.to_dict(),
            "kdj_method_id": KDJ_METHOD_ID_V1,
            "kdj_method_version": KDJ_METHOD_VERSION_V1,
            "kdj_method_identity_sha256": KDJ_METHOD_IDENTITY_SHA256_V1,
            "source_available_at": None,
            "availability_status": "unknown",
            "historical_pit_eligible": False,
        }
        body_bytes = kdj_query_module._canonical_json_bytes(body)
        identity = hashlib.sha256(body_bytes).hexdigest()
        final_payload = {**body, "request_identity_sha256": identity}
        return (
            len(body_bytes),
            len(kdj_query_module._canonical_json_bytes(final_payload)),
            ma_request,
        )

    low = 0
    high = limit
    candidate: tuple[int, int, DailyMarketTechnicalMaAlignmentSourceRequestV1] | None = None
    while low <= high:
        middle = (low + high) // 2
        measured = sizes(middle)
        body_size, final_size, _ = measured
        if body_size <= limit and final_size > limit:
            candidate = measured
            break
        if final_size <= limit:
            low = middle + 1
        else:
            high = middle - 1
    assert candidate is not None
    body_size, final_size, ma_request = candidate
    assert body_size <= limit < final_size
    with pytest.raises(DailyMarketTechnicalUniverseKDJQueryV1Error) as raised:
        DailyMarketTechnicalUniverseKDJSourceRequestV1.from_ma_source_request(ma_request)
    assert raised.value.code == "technical_kdj_source_request_byte_limit"


@pytest.mark.parametrize(
    ("callback", "expected_code"),
    [
        (lambda: True, "technical_kdj_projection_cancelled"),
        (lambda: 1, "technical_kdj_projection_cancel_callback_invalid"),
        (lambda: (_ for _ in ()).throw(RuntimeError("cancel probe")), "technical_kdj_projection_cancel_check_failed"),
    ],
)
def test_cancel_contract_is_strict_before_collector_creation(
    tmp_path: Path,
    callback: object,
    expected_code: str,
) -> None:
    request = _source_request(tmp_path)
    _expect_code(
        expected_code,
        lambda: DailyMarketTechnicalKDJProjectionCollectorV1(
            request,
            cancel_callback=callback,  # type: ignore[arg-type]
        ),
    )


def test_projection_group_has_fixed_exact_membership_and_no_qualification_api(
    tmp_path: Path,
) -> None:
    ma_request = _ma_request(tmp_path)
    source_request = DailyMarketTechnicalUniverseKDJSourceRequestV1.from_ma_source_request(
        ma_request,
    )
    ma_collector = DailyMarketTechnicalMaAlignmentVerifiedCollectorV1(ma_request)
    kdj_collector = DailyMarketTechnicalKDJProjectionCollectorV1(source_request)
    group = DailyMarketTechnicalVerifiedProjectionGroupV1(ma_collector, kdj_collector)

    assert group.members == (ma_collector, kdj_collector)
    assert group.contains_exact_member(ma_collector)
    assert group.contains_exact_member(kdj_collector)
    replacement = DailyMarketTechnicalKDJProjectionCollectorV1(source_request)
    assert not group.contains_exact_member(replacement)
    assert not hasattr(group, "add_member")
    assert not hasattr(group, "finalize")
    assert not hasattr(group, "issued_session")
    assert kdj_collector.unqualified_entries == ()

    with pytest.raises(AttributeError):
        group.members = (kdj_collector, ma_collector)  # type: ignore[assignment,misc]
    _expect_code(
        "technical_kdj_projection_group_members_immutable",
        lambda: setattr(group, "_members", (kdj_collector, ma_collector)),
    )
    _expect_code(
        "technical_kdj_projection_group_members_invalid",
        lambda: DailyMarketTechnicalVerifiedProjectionGroupV1(
            # 反向／替換的 member 型別不能重新宣告群組秩序。
            kdj_collector,  # type: ignore[arg-type]
            ma_collector,  # type: ignore[arg-type]
        ),
    )


def test_group_binds_once_to_real_builder_but_still_issues_no_session(tmp_path: Path) -> None:
    ma_request = _ma_request(tmp_path)
    source_request = DailyMarketTechnicalUniverseKDJSourceRequestV1.from_ma_source_request(
        ma_request,
    )
    ma_collector = DailyMarketTechnicalMaAlignmentVerifiedCollectorV1(ma_request)
    kdj_collector = DailyMarketTechnicalKDJProjectionCollectorV1(source_request)
    group = DailyMarketTechnicalVerifiedProjectionGroupV1(ma_collector, kdj_collector)
    builder = DailyMarketTechnicalUniverseV4ReadSessionBuilder(
        store_output_root=tmp_path,
        generation_identity_sha256=ma_request.generation_identity_sha256,
        plan_identity_sha256=ma_request.plan_identity_sha256,
        plan_sha256=ma_request.plan_sha256,
        receipt_identity_sha256=ma_request.receipt_identity_sha256,
        receipt_sha256=ma_request.receipt_sha256,
    )

    group.bind_to_builder(builder)
    assert builder._verified_projection is group
    assert builder.verified_session is None
    assert kdj_collector.unqualified_entries == ()
    with pytest.raises(DailyMarketTechnicalUniverseMaAlignmentQueryV1Error) as partial_ma:
        ma_collector.finalize_verified_publication(
            builder,
            object(),
            object(),
            object(),
        )
    assert partial_ma.value.code == "technical_ma_alignment_collector_publication_input_invalid"

    _expect_code(
        "technical_kdj_projection_group_bind_invalid",
        lambda: group.bind_to_builder(builder),
    )
    _expect_code(
        "technical_kdj_projection_group_parent_order_invalid",
        lambda: group.begin_verified_parent(
            1,
            cast(DailyMarketTechnicalParentCaptureV4VerifiedRead, object()),
        ),
    )
    _expect_code(
        "technical_kdj_projection_group_bind_invalid",
        lambda: group.bind_to_builder(builder),
    )
    _expect_code(
        "technical_kdj_collector_failed",
        lambda: kdj_collector.unqualified_entries,
    )


def test_cancelled_projection_group_cannot_resume_when_flag_turns_false(tmp_path: Path) -> None:
    ma_request = _ma_request(tmp_path)
    source_request = DailyMarketTechnicalUniverseKDJSourceRequestV1.from_ma_source_request(
        ma_request,
    )
    ma_collector = DailyMarketTechnicalMaAlignmentVerifiedCollectorV1(ma_request)
    kdj_collector = DailyMarketTechnicalKDJProjectionCollectorV1(source_request)
    cancellation = {"cancelled": False}
    group = DailyMarketTechnicalVerifiedProjectionGroupV1(
        ma_collector,
        kdj_collector,
        cancel_callback=lambda: cancellation["cancelled"],
    )
    builder = DailyMarketTechnicalUniverseV4ReadSessionBuilder(
        store_output_root=tmp_path,
        generation_identity_sha256=ma_request.generation_identity_sha256,
        plan_identity_sha256=ma_request.plan_identity_sha256,
        plan_sha256=ma_request.plan_sha256,
        receipt_identity_sha256=ma_request.receipt_identity_sha256,
        receipt_sha256=ma_request.receipt_sha256,
    )
    group.bind_to_builder(builder)

    cancellation["cancelled"] = True
    _expect_code(
        "technical_kdj_projection_cancelled",
        lambda: group.begin_verified_parent(
            0,
            cast(DailyMarketTechnicalParentCaptureV4VerifiedRead, object()),
        ),
    )
    cancellation["cancelled"] = False
    _expect_code(
        "technical_kdj_projection_group_parent_order_invalid",
        lambda: group.begin_verified_parent(
            0,
            cast(DailyMarketTechnicalParentCaptureV4VerifiedRead, object()),
        ),
    )
    _expect_code(
        "technical_kdj_collector_failed",
        lambda: kdj_collector.unqualified_entries,
    )


def test_unbound_collector_cannot_consume_arbitrary_objects(tmp_path: Path) -> None:
    collector = DailyMarketTechnicalKDJProjectionCollectorV1(_source_request(tmp_path))
    _expect_code(
        "technical_kdj_collector_snapshot_order_invalid",
        lambda: collector.consume_verified_snapshot(
            0,
            cast(DailyMarketTechnicalFeatureSnapshotV4, object()),
            cast(DailyMarketTechnicalParentV4Row, object()),
        ),
    )
    _expect_code(
        "technical_kdj_collector_failed",
        lambda: collector.unqualified_entries,
    )
