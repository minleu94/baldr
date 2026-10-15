from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo

import pytest

from data_module.daily_monthly_revenue_cohort import (
    DailyMonthlyRevenueCohortError,
    DailyMonthlyRevenueCohortPin,
    DailyMonthlyRevenueCohortReader,
    build_daily_monthly_revenue_cohort_pin,
    read_daily_monthly_revenue_cohort_pin,
    write_daily_monthly_revenue_cohort_pin_create_only,
)
from data_module.daily_source_snapshot import (
    DAILY_SOURCE_TIME_BASIS_POLICY,
    DailySourceBatchValidation,
    DailySourceSnapshotError,
    DailySourceSnapshotFileReader,
    DailySourceSnapshotRecord,
    DailySourceTransportCapture,
    DailySourceUseAcceptance,
    DailySourceUseScope,
    DailySourceValidationCheck,
    write_daily_source_snapshot,
)


TAIPEI = ZoneInfo("Asia/Taipei")
PERIOD = "2026-04"
INTENDED_USE = "recommendation_current_fundamental"
ENDPOINT = "https://mops.twse.com.tw/mops/web/t05st10_ifrs"


def _scope(
    market: str,
    *,
    unit: str = "TWD",
    intended_use: str = INTENDED_USE,
) -> DailySourceUseScope:
    return DailySourceUseScope(
        dataset_id="fundamental_current_observations.monthly_revenue",
        source_id="mops.monthly_revenue_static_snapshot",
        market=market,
        parser_version="mops-current-revenue-normalizer.v2",
        source_schema_version="mops-static-snapshot.v2",
        unit=unit,
        intended_use=intended_use,
    )


def _acceptance(
    scope: DailySourceUseScope,
    *,
    acceptance_id: str | None = None,
) -> DailySourceUseAcceptance:
    return DailySourceUseAcceptance(
        scope=scope,
        acceptance_id=acceptance_id or f"synthetic-{scope.market}-{scope.intended_use}",
        accepted_at=datetime(2026, 10, 2, 8, 0, tzinfo=TAIPEI),
        official_source_endpoint=ENDPOINT,
        document_chain=("synthetic-mops-monthly-revenue", ENDPOINT),
        acceptance_evidence_ref="test-fixture:explicit-trusted-acceptance",
        authorization_scope=f"{scope.intended_use} only",
        time_basis_policy=DAILY_SOURCE_TIME_BASIS_POLICY,
    )


def _validation(
    market: str,
    *,
    count: int = 1,
    official_timestamp_present: bool = True,
) -> DailySourceBatchValidation:
    def passed(check_id: str) -> DailySourceValidationCheck:
        return DailySourceValidationCheck(check_id, "pass", f"{check_id}_verified")

    return DailySourceBatchValidation(
        validation_id=f"synthetic-{market}-validation",
        expected_partition_ids=(f"{market}-monthly-revenue",),
        successful_partition_ids=(f"{market}-monthly-revenue",),
        failed_partition_ids=(),
        expected_record_count=count,
        actual_record_count=count,
        source_status_check=passed("source_status"),
        raw_source_hash_check=passed("raw_source_hash"),
        schema_check=passed("schema"),
        unit_check=passed("unit"),
        finite_values_check=passed("finite_values"),
        missing_values_check=passed("missing_values"),
        prior_period_required_check=DailySourceValidationCheck(
            "prior_period_required", "not_required", "prior_period_not_required"
        ),
        official_timestamp_parse_check=(
            DailySourceValidationCheck(
                "official_timestamp_parse",
                "pass",
                "official_timestamp_parsed_by:mops-current-revenue-normalizer.v2",
            )
            if official_timestamp_present
            else DailySourceValidationCheck(
                "official_timestamp_parse",
                "not_required",
                "official_timestamp_not_provided",
            )
        ),
    )


def _write_market_batch(
    root: Path,
    market: str,
    *,
    batch_id: str,
    period: str = PERIOD,
    unit: str = "TWD",
    intended_use: str = INTENDED_USE,
    body_hour: int = 10,
    official_timestamp_present: bool = True,
) -> tuple[DailySourceSnapshotFileReader, DailySourceUseAcceptance]:
    scope = _scope(market, unit=unit, intended_use=intended_use)
    acceptance = _acceptance(scope)
    body_completed_at = datetime(2026, 10, 2, body_hour, 5, tzinfo=TAIPEI)
    html = '<meta charset="big5"><html><body>月營收</body></html>'
    response_bytes = html.encode("big5")
    canonical_bytes = html.encode("utf-8")
    canonical_sha256 = hashlib.sha256(canonical_bytes).hexdigest()
    stock_code = "2330" if market == "twse" else "6488"
    record = DailySourceSnapshotRecord(
        stock_code=stock_code,
        market=market,
        period=period,
        source_version=(
            f"mops-static-snapshot.v2:{market}:{period}:body_completed_at:"
            f"{body_completed_at.isoformat()}:sha256:{canonical_sha256}"
        ),
        raw_source_sha256=canonical_sha256,
        unit=unit,
        official_timestamp=body_completed_at if official_timestamp_present else None,
        official_timestamp_original_text=(
            body_completed_at.isoformat() if official_timestamp_present else ""
        ),
        official_timestamp_original_timezone=("+08:00" if official_timestamp_present else ""),
    )
    capture = DailySourceTransportCapture(
        raw_response_bytes=response_bytes,
        official_source_url=ENDPOINT,
        response_status=200,
        content_type="text/html",
        declared_decoding_encoding="big5",
        decoding_basis="html_meta_charset",
        body_completed_at=body_completed_at,
        transport_sha256=hashlib.sha256(response_bytes).hexdigest(),
        response_body_complete=True,
        received_body_bytes=len(response_bytes),
        content_length_original_text=None,
        body_completion_evidence_ref=f"eof:synthetic-{market}-complete-body",
    )
    clock_values = iter(
        (
            body_completed_at + timedelta(minutes=5),
            body_completed_at + timedelta(minutes=15),
            body_completed_at + timedelta(minutes=20),
            body_completed_at + timedelta(minutes=25),
        )
    )
    write_daily_source_snapshot(
        root,
        batch_id=batch_id,
        scope=scope,
        use_acceptance=acceptance,
        source_batch_started_at=body_completed_at - timedelta(minutes=10),
        raw_source_bytes=canonical_bytes,
        records=(record,),
        validation=_validation(
            market, official_timestamp_present=official_timestamp_present
        ),
        transport_capture=capture,
        clock=lambda: next(clock_values),
    )
    return (
        DailySourceSnapshotFileReader(root, trusted_acceptance=acceptance),
        acceptance,
    )


def _pair(tmp_path: Path) -> tuple[
    Mapping[str, DailySourceSnapshotFileReader],
    Mapping[str, DailySourceUseAcceptance],
    dict[str, str],
]:
    readers: dict[str, DailySourceSnapshotFileReader] = {}
    acceptances: dict[str, DailySourceUseAcceptance] = {}
    batch_ids = {"twse": "cohort-twse-20261002", "tpex": "cohort-tpex-20261002"}
    for market, hour in (("twse", 10), ("tpex", 11)):
        market_root = tmp_path / f"{market}-snapshots"
        reader, acceptance = _write_market_batch(
            market_root,
            market,
            batch_id=batch_ids[market],
            body_hour=hour,
            official_timestamp_present=market == "twse",
        )
        readers[market] = reader
        acceptances[market] = acceptance
    return readers, acceptances, batch_ids


def _build_pair(
    readers: Mapping[str, DailySourceSnapshotFileReader],
    batch_ids: Mapping[str, str],
) -> DailyMonthlyRevenueCohortPin:
    return build_daily_monthly_revenue_cohort_pin(
        period=PERIOD,
        required_markets=("twse", "tpex"),
        batch_ids=batch_ids,
        readers=readers,
    )


def test_two_market_cohort_round_trips_and_gates_both_markets(tmp_path: Path) -> None:
    readers, acceptances, batch_ids = _pair(tmp_path)
    pin = _build_pair(readers, batch_ids)

    assert pin.required_markets == ("twse", "tpex")
    assert pin.for_market("twse").batch_id == batch_ids["twse"]
    assert pin.for_market("tpex").batch_id == batch_ids["tpex"]
    assert pin.available_hour == datetime(2026, 10, 2, 12, 0, tzinfo=TAIPEI)
    assert pin.for_market("twse").available_hour == datetime(
        2026, 10, 2, 11, 0, tzinfo=TAIPEI
    )
    assert pin.for_market("tpex").available_hour == pin.available_hour
    assert pin.for_market("twse").availability_basis
    assert pin.for_market("tpex").availability_basis == (
        "successful_batch_completion_fallback",
    )
    assert pin.for_market("twse").raw_source_sha256 != pin.for_market(
        "twse"
    ).transport_sha256
    assert _build_pair(readers, batch_ids) == pin

    pin_root = tmp_path / "cohort-pins"
    saved_path = write_daily_monthly_revenue_cohort_pin_create_only(pin_root, pin)
    reopened = read_daily_monthly_revenue_cohort_pin(
        pin_root,
        pin.cohort_sha256,
        expected_cohort_sha256=pin.cohort_sha256,
    )
    assert reopened == pin
    assert DailyMonthlyRevenueCohortPin.from_json(pin.to_json()) == pin
    with pytest.raises(AttributeError):
        setattr(pin, "available_hour", datetime(2026, 10, 2, 13, 0, tzinfo=TAIPEI))
    with pytest.raises(DailyMonthlyRevenueCohortError, match="create_only_conflict"):
        write_daily_monthly_revenue_cohort_pin_create_only(pin_root, pin)

    cohort_reader = DailyMonthlyRevenueCohortReader(
        pin=reopened,
        market_readers=readers,
        expected_cohort_sha256=pin.cohort_sha256,
    )
    assert cohort_reader.pin is reopened
    assert cohort_reader.available_hour == pin.available_hour
    with pytest.raises(AttributeError):
        setattr(cohort_reader, "pin", pin)
    assert cohort_reader.verify_cohort()[0].batch_id == batch_ids["twse"]
    twse = cohort_reader.read_snapshot(
        batch_ids["twse"], expected_scope=acceptances["twse"].scope
    )
    tpex = cohort_reader.read_snapshot(
        batch_ids["tpex"], expected_scope=acceptances["tpex"].scope
    )
    assert twse.scope.market == "twse"
    assert tpex.scope.market == "tpex"
    assert cohort_reader.verify_cohort()[0] == twse
    assert saved_path.read_bytes() == pin.to_json().encode("utf-8")
    with pytest.raises(DailyMonthlyRevenueCohortError, match="market_not_required"):
        pin.for_market("otc")


def test_builder_rejects_missing_batch_wrong_market_and_mixed_purpose(
    tmp_path: Path,
) -> None:
    readers, _, batch_ids = _pair(tmp_path)
    with pytest.raises(DailyMonthlyRevenueCohortError, match="batch_ids_incomplete"):
        _build_pair(readers, {"twse": batch_ids["twse"]})
    missing_tpex_acceptance = _acceptance(_scope("tpex"))
    missing_tpex_reader = DailySourceSnapshotFileReader(
        tmp_path / "no-tpex-batch",
        trusted_acceptance=missing_tpex_acceptance,
    )
    with pytest.raises(DailySourceSnapshotError, match="manifest 或成功收據不存在"):
        build_daily_monthly_revenue_cohort_pin(
            period=PERIOD,
            required_markets=("twse", "tpex"),
            batch_ids=batch_ids,
            readers={"twse": readers["twse"], "tpex": missing_tpex_reader},
        )
    with pytest.raises(DailyMonthlyRevenueCohortError, match="reader_market_mismatch"):
        _build_pair(
            {"twse": readers["tpex"], "tpex": readers["twse"]},
            batch_ids,
        )

    mixed_root = tmp_path / "mixed-purpose"
    mixed_twse, _ = _write_market_batch(
        mixed_root / "twse",
        "twse",
        batch_id="mixed-twse",
    )
    mixed_tpex, _ = _write_market_batch(
        mixed_root / "tpex",
        "tpex",
        batch_id="mixed-tpex",
        intended_use="synthetic_other_use",
    )
    with pytest.raises(DailyMonthlyRevenueCohortError, match="scopes_not_equivalent"):
        build_daily_monthly_revenue_cohort_pin(
            period=PERIOD,
            required_markets=("twse", "tpex"),
            batch_ids={"twse": "mixed-twse", "tpex": "mixed-tpex"},
            readers={"twse": mixed_twse, "tpex": mixed_tpex},
        )

    unit_twse, _ = _write_market_batch(
        tmp_path / "mixed-unit" / "twse",
        "twse",
        batch_id="unit-twse",
    )
    unit_tpex, _ = _write_market_batch(
        tmp_path / "mixed-unit" / "tpex",
        "tpex",
        batch_id="unit-tpex",
        unit="shares",
    )
    with pytest.raises(DailyMonthlyRevenueCohortError, match="scopes_not_equivalent"):
        build_daily_monthly_revenue_cohort_pin(
            period=PERIOD,
            required_markets=("twse", "tpex"),
            batch_ids={"twse": "unit-twse", "tpex": "unit-tpex"},
            readers={"twse": unit_twse, "tpex": unit_tpex},
        )


def test_reader_rejects_wrong_period_purpose_unknown_batch_and_unknown_hash(
    tmp_path: Path,
) -> None:
    twse, acceptance = _write_market_batch(
        tmp_path / "twse",
        "twse",
        batch_id="period-twse",
    )
    pin = build_daily_monthly_revenue_cohort_pin(
        period=PERIOD,
        required_markets=("twse",),
        batch_ids={"twse": "period-twse"},
        readers={"twse": twse},
    )
    reader = DailyMonthlyRevenueCohortReader(
        pin=pin,
        market_readers={"twse": twse},
        expected_cohort_sha256=pin.cohort_sha256,
    )
    with pytest.raises(DailyMonthlyRevenueCohortError, match="period_invalid"):
        build_daily_monthly_revenue_cohort_pin(
            period="2026-13",
            required_markets=("twse",),
            batch_ids={"twse": "period-twse"},
            readers={"twse": twse},
        )
    wrong_period_reader, _ = _write_market_batch(
        tmp_path / "wrong-period",
        "twse",
        batch_id="wrong-period-twse",
        period="2026-05",
    )
    with pytest.raises(DailyMonthlyRevenueCohortError, match="record_identity_mismatch"):
        build_daily_monthly_revenue_cohort_pin(
            period=PERIOD,
            required_markets=("twse",),
            batch_ids={"twse": "wrong-period-twse"},
            readers={"twse": wrong_period_reader},
        )
    with pytest.raises(DailyMonthlyRevenueCohortError, match="expected_scope_mismatch"):
        reader.read_snapshot(
            "period-twse",
            expected_scope=replace(acceptance.scope, intended_use="another_use"),
        )
    with pytest.raises(DailyMonthlyRevenueCohortError, match="batch_id_mismatch"):
        reader.read_snapshot("not-the-pinned-batch", expected_scope=acceptance.scope)
    with pytest.raises(DailyMonthlyRevenueCohortError, match="external_hash_mismatch"):
        DailyMonthlyRevenueCohortReader(
            pin=pin,
            market_readers={"twse": twse},
            expected_cohort_sha256="0" * 64,
        )
    changed_anchor_reader = DailySourceSnapshotFileReader(
        twse.root,
        trusted_acceptance=replace(
            acceptance, acceptance_evidence_ref="different-trusted-evidence"
        ),
    )
    with pytest.raises(DailyMonthlyRevenueCohortError, match="trusted_acceptance_hash_mismatch"):
        DailyMonthlyRevenueCohortReader(
            pin=pin,
            market_readers={"twse": changed_anchor_reader},
            expected_cohort_sha256=pin.cohort_sha256,
        )
    empty_pin_root = tmp_path / "empty-pin-root"
    empty_pin_root.mkdir()
    with pytest.raises(DailyMonthlyRevenueCohortError, match="cohort_pin_not_found"):
        read_daily_monthly_revenue_cohort_pin(
            empty_pin_root,
            "0" * 64,
            expected_cohort_sha256="0" * 64,
        )
    with pytest.raises(DailyMonthlyRevenueCohortError, match="external_hash_mismatch"):
        read_daily_monthly_revenue_cohort_pin(
            tmp_path / "unknown-pins",
            pin.cohort_sha256,
            expected_cohort_sha256="0" * 64,
        )


def test_pin_json_rejects_hash_and_clock_changes_even_when_resealed(tmp_path: Path) -> None:
    readers, _, batch_ids = _pair(tmp_path)
    pin = _build_pair(readers, batch_ids)
    changed_market = replace(
        pin.for_market("tpex"),
        available_hour=pin.for_market("tpex").available_hour + timedelta(hours=1),
    )
    changed_pin = replace(
        pin,
        market_pins=(pin.for_market("twse"), changed_market),
        available_hour=changed_market.available_hour,
    )
    assert changed_pin.cohort_sha256 != pin.cohort_sha256
    with pytest.raises(DailyMonthlyRevenueCohortError, match="before_batch_gate"):
        replace(
            pin.for_market("tpex"),
            available_hour=pin.for_market("tpex").available_hour - timedelta(hours=1),
        )
    forged_payload = json.loads(pin.to_json())
    forged_payload["market_pins"][1]["receipt_sha256"] = "f" * 64
    with pytest.raises(DailyMonthlyRevenueCohortError, match="sha256_mismatch"):
        DailyMonthlyRevenueCohortPin.from_dict(forged_payload)

    with pytest.raises(DailyMonthlyRevenueCohortError, match="external_hash_mismatch"):
        DailyMonthlyRevenueCohortReader(
            pin=changed_pin,
            market_readers=readers,
            expected_cohort_sha256=pin.cohort_sha256,
        )


def test_pin_json_rejects_duplicate_and_unrecognized_fields(tmp_path: Path) -> None:
    readers, _, batch_ids = _pair(tmp_path)
    pin = _build_pair(readers, batch_ids)
    with pytest.raises(DailyMonthlyRevenueCohortError, match="duplicate_json_key"):
        DailyMonthlyRevenueCohortPin.from_json(
            '{"schema_version":"daily-monthly-revenue-cohort-pin.v1",'
            '"schema_version":"daily-monthly-revenue-cohort-pin.v1"}'
        )
    expanded = pin.to_dict()
    expanded["unknown_field"] = "not part of the versioned contract"
    with pytest.raises(DailyMonthlyRevenueCohortError, match="fields_invalid"):
        DailyMonthlyRevenueCohortPin.from_dict(expanded)


def test_verify_rechecks_every_market_and_captured_roots_anchors(tmp_path: Path) -> None:
    readers, acceptances, batch_ids = _pair(tmp_path)
    pin = _build_pair(readers, batch_ids)
    cohort_reader = DailyMonthlyRevenueCohortReader(
        pin=pin,
        market_readers=readers,
        expected_cohort_sha256=pin.cohort_sha256,
    )
    original_roots = {market: reader.root for market, reader in readers.items()}
    alternate_root = tmp_path / "different-source"
    alternate_reader, _ = _write_market_batch(
        alternate_root,
        "tpex",
        batch_id="different-tpex-batch",
    )

    # 外部 FileReader 屬性即使改指其他來源，cohort reader 仍固定使用建構時的 root/錨點。
    readers["tpex"].root = alternate_reader.root
    changed_acceptance = replace(
        acceptances["tpex"], acceptance_evidence_ref="changed-anchor-after-construction"
    )
    readers["tpex"].trusted_acceptance = changed_acceptance
    assert readers["tpex"].trusted_acceptance != acceptances["tpex"]
    snapshots = cohort_reader.verify_cohort()
    assert tuple(snapshot.batch_id for snapshot in snapshots) == (
        batch_ids["twse"],
        batch_ids["tpex"],
    )
    assert cohort_reader.read_snapshot(
        batch_ids["twse"], expected_scope=acceptances["twse"].scope
    ).batch_id == batch_ids["twse"]

    # 若任一 required market 原件失效，即使讀取目標為 TWSE 也必須拒絕。
    receipt = original_roots["tpex"] / batch_ids["tpex"] / "receipt.json"
    receipt.write_bytes(receipt.read_bytes() + b"}")
    with pytest.raises(DailySourceSnapshotError, match="receipt JSON 格式錯誤"):
        cohort_reader.read_snapshot(
            batch_ids["twse"], expected_scope=acceptances["twse"].scope
        )


def test_single_market_cohort_is_explicit_and_unknown_market_does_not_fallback(
    tmp_path: Path,
) -> None:
    reader, acceptance = _write_market_batch(
        tmp_path / "twse-only",
        "twse",
        batch_id="only-twse",
    )
    pin = build_daily_monthly_revenue_cohort_pin(
        period=PERIOD,
        required_markets=("twse",),
        batch_ids={"twse": "only-twse"},
        readers={"twse": reader},
    )
    cohort_reader = DailyMonthlyRevenueCohortReader(
        pin=pin,
        market_readers={"twse": reader},
        expected_cohort_sha256=pin.cohort_sha256,
    )
    assert cohort_reader.read_snapshot(
        "only-twse", expected_scope=acceptance.scope
    ).scope.market == "twse"
    with pytest.raises(DailyMonthlyRevenueCohortError, match="market_not_required"):
        cohort_reader.read_snapshot(
            "only-twse",
            expected_scope=replace(acceptance.scope, market="tpex"),
        )
