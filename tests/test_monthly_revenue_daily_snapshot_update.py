from __future__ import annotations

import base64
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Callable
from zoneinfo import ZoneInfo

import pytest

from app_module.monthly_revenue_daily_snapshot_update import (
    DailyMonthlyRevenueSnapshotUpdateResult,
    publish_daily_monthly_revenue_snapshot,
    read_daily_monthly_revenue_snapshot_status,
)
from app_module.update_service import UpdateService
from data_module.config import TWStockConfig
from data_module.current_fundamental_snapshots import (
    ensure_current_observation_schema,
    insert_observations,
    monthly_snapshot_rows,
)
from data_module.daily_source_snapshot import (
    DAILY_SOURCE_TIME_BASIS_POLICY,
    DAILY_SOURCE_SNAPSHOT_DATASET_ID,
    DAILY_SOURCE_SNAPSHOT_SOURCE_ID,
    DailySourceSnapshotFileReader,
    DailySourceTransportCapture,
    DailySourceUseAcceptance,
    DailySourceUseScope,
)
from data_module.monthly_revenue_daily_snapshot_preparation import (
    prepare_daily_monthly_revenue_capture,
)
from data_module.monthly_revenue_snapshot_harvester import write_mops_snapshot_csv
from data_module.recommendation_current_fundamental_provider import (
    RecommendationCurrentFundamentalProvider,
)


TAIPEI = ZoneInfo("Asia/Taipei")
OFFICIAL_REPORT_URL = (
    "https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_115_9_0.html"
)
REPORT_HEADERS = (
    "公司代號",
    "公司名稱",
    "當月營收",
    "上月營收",
    "去年當月營收",
    "當月累計營收",
    "去年累計營收",
)
_CLOCK_VALUES = (
    datetime(2026, 10, 2, 10, 8, tzinfo=TAIPEI),
    datetime(2026, 10, 2, 10, 10, tzinfo=TAIPEI),
    datetime(2026, 10, 2, 10, 20, tzinfo=TAIPEI),
    datetime(2026, 10, 2, 10, 25, tzinfo=TAIPEI),
    datetime(2026, 10, 2, 10, 30, tzinfo=TAIPEI),
)


def _html(*, current_amount: str = "1,000") -> str:
    header = "<tr>" + "".join(f"<th>{item}</th>" for item in REPORT_HEADERS) + "</tr>"
    rows = "".join(
        "<tr>" + "".join(f"<td>{item}</td>" for item in cells) + "</tr>"
        for cells in (
            ("2330", "台積電", current_amount, "900", "800", "9,000", "8,000"),
            ("2317", "鴻海", "2,000", "1,800", "1,600", "18,000", "16,000"),
        )
    )
    return (
        "<html><head></head><body>上市公司115年9月份 單位：新臺幣千元"
        f"<table>{header}{rows}</table></body></html>"
    )


def _scope(*, unit: str = "TWD") -> DailySourceUseScope:
    return DailySourceUseScope(
        dataset_id=DAILY_SOURCE_SNAPSHOT_DATASET_ID,
        source_id=DAILY_SOURCE_SNAPSHOT_SOURCE_ID,
        market="twse",
        parser_version="mops-current-revenue-normalizer.v2",
        source_schema_version="mops-static-snapshot.v2",
        unit=unit,
        intended_use="recommendation_current_fundamental",
    )


def _acceptance(scope: DailySourceUseScope) -> DailySourceUseAcceptance:
    return DailySourceUseAcceptance(
        scope=scope,
        acceptance_id="synthetic-mops-monthly-use-acceptance",
        accepted_at=datetime(2026, 10, 2, 8, 0, tzinfo=TAIPEI),
        official_source_endpoint=OFFICIAL_REPORT_URL,
        document_chain=(
            "synthetic-source-evidence:monthly-report-contract",
            OFFICIAL_REPORT_URL,
        ),
        acceptance_evidence_ref="synthetic-test-fixture:trusted-use-acceptance",
        authorization_scope="recommendation_current_fundamental",
        time_basis_policy=DAILY_SOURCE_TIME_BASIS_POLICY,
    )


def _capture(*, current_amount: str = "1,000") -> DailySourceTransportCapture:
    raw_response = _html(current_amount=current_amount).encode("big5")
    return DailySourceTransportCapture(
        raw_response_bytes=raw_response,
        official_source_url=OFFICIAL_REPORT_URL,
        response_status=200,
        content_type="text/html; charset=big5",
        declared_decoding_encoding="big5",
        decoding_basis="http_content_type_charset",
        body_completed_at=datetime(2026, 10, 2, 10, 5, tzinfo=TAIPEI),
        transport_sha256=hashlib.sha256(raw_response).hexdigest(),
        response_body_complete=True,
        received_body_bytes=len(raw_response),
        content_length_original_text=str(len(raw_response)),
        body_completion_evidence_ref="eof:synthetic-complete-mops-report",
    )


def _publish_clock() -> Callable[[], datetime]:
    values = iter(_CLOCK_VALUES)
    return lambda: next(values)


def _publish(
    root: Path,
    *,
    capture: DailySourceTransportCapture | None = None,
    scope: DailySourceUseScope | None = None,
    acceptance: DailySourceUseAcceptance | None = None,
    period: str = "2026-09",
    batch_id: str = "monthly-update-20261002",
    clock: Callable[[], datetime] | None = None,
    check_cancel: Callable[[], bool] | None = None,
) -> DailyMonthlyRevenueSnapshotUpdateResult:
    selected_scope = scope or _scope()
    return publish_daily_monthly_revenue_snapshot(
        root=root,
        capture=capture or _capture(),
        period=period,
        batch_id=batch_id,
        source_batch_started_at=datetime(2026, 10, 2, 9, 55, tzinfo=TAIPEI),
        use_acceptance=acceptance or _acceptance(selected_scope),
        scope=selected_scope,
        clock=clock or _publish_clock(),
        check_cancel=check_cancel or (lambda: False),
    )


def test_big5_capture_is_published_read_by_fresh_reader_and_consumed_by_provider(
    tmp_path: Path,
) -> None:
    capture = _capture()
    scope = _scope()
    acceptance = _acceptance(scope)
    prepared = prepare_daily_monthly_revenue_capture(
        capture=capture,
        scope=scope,
        period="2026-09",
        validation_id="synthetic-prepared-source-report",
    )
    snapshot_root = tmp_path / "daily-snapshots"

    result = _publish(
        snapshot_root,
        capture=capture,
        scope=scope,
        acceptance=acceptance,
    )

    assert result.success
    assert result.status == "ready"
    assert result.batch_id == "monthly-update-20261002"
    assert result.period == "2026-09"
    assert result.scope == scope
    assert result.normalized_observation_count == 4
    assert result.raw_source_sha256 == hashlib.sha256(
        prepared.canonical_source_bytes
    ).hexdigest()
    assert result.transport_sha256 == capture.transport_sha256
    assert result.raw_source_sha256 != result.transport_sha256
    assert result.snapshot_status is not None
    assert result.snapshot_status.available
    assert result.snapshot_status.record_count == 2
    assert result.snapshot_status.record_availability[0].available_hour == datetime(
        2026, 10, 2, 11, 0, tzinfo=TAIPEI
    )
    assert (
        result.snapshot_status.record_availability[0].basis
        == "successful_batch_completion_fallback"
    )

    # 這次 status 呼叫會建立另一個 FileReader，僅讀 caller 釘選的 batch。
    fresh_status = read_daily_monthly_revenue_snapshot_status(
        snapshot_root,
        batch_id="monthly-update-20261002",
        period="2026-09",
        expected_scope=scope,
        trusted_acceptance=acceptance,
    )
    assert fresh_status.available
    assert fresh_status.raw_source_sha256 == result.raw_source_sha256
    assert fresh_status.transport_sha256 == capture.transport_sha256

    # 測試 DB 僅位於 tmp_path。既有 normalizer 把報表千元列轉成 TWD，
    # provider 再以原始版本、SHA 與 pinned immutable receipt 核對。
    csv_path = tmp_path / "synthetic-monthly.csv"
    write_mops_snapshot_csv(csv_path, prepared.rows)
    observations = monthly_snapshot_rows(
        csv_path,
        verified_source_versions=frozenset({prepared.source_version}),
    )
    for observation in observations:
        observation["observed_at"] = datetime(
            2026, 10, 2, 10, 8, tzinfo=TAIPEI
        ).isoformat()
    database = tmp_path / "isolated-current-observations.sqlite3"
    with sqlite3.connect(database) as connection:
        ensure_current_observation_schema(connection)
        assert insert_observations(connection, observations) == len(observations)

    provider = RecommendationCurrentFundamentalProvider(
        db_file=database,
        output_root=tmp_path / "unused-output",
        daily_source_snapshot_reader=DailySourceSnapshotFileReader(
            snapshot_root,
            trusted_acceptance=acceptance,
        ),
    )
    too_early = provider.load_monthly_revenues(
        stock_code="2330",
        cutoff_at=datetime(2026, 10, 2, 10, 59, tzinfo=TAIPEI),
        pinned_daily_batch_id="monthly-update-20261002",
    )
    available = provider.load_monthly_revenues(
        stock_code="2330",
        cutoff_at=datetime(2026, 10, 2, 11, 0, tzinfo=TAIPEI),
        pinned_daily_batch_id="monthly-update-20261002",
    )

    assert too_early.status == "missing"
    assert any(
        "daily_source_snapshot_not_available_at_cutoff:2026-09" in item
        for item in too_early.diagnostics
    )
    assert available.status == "ready"
    assert tuple(item.period for item in available.observations) == ("2026-09",)
    row = available.observations[0]
    assert row.stock_code == "2330"
    assert row.revenue == Decimal("1000000")
    assert row.unit == "TWD"
    assert row.raw_source_version == prepared.source_version
    assert row.raw_source_sha256 == result.raw_source_sha256
    assert row.available_at == datetime(2026, 10, 2, 11, 0, tzinfo=TAIPEI)
    assert row.availability_basis == "successful_batch_completion_fallback"
    assert row.availability_snapshot_batch_id == "monthly-update-20261002"
    assert available.comparison_baseline is not None
    assert available.comparison_baseline.revenue == Decimal("800000")
    assert not available.comparison_baseline.formal_pit_eligible


@pytest.mark.parametrize(
    ("case", "period", "unit", "reason"),
    (
        ("wrong_unit", "2026-09", "USD", "monthly_preparation_scope_mismatch"),
        (
            "wrong_period",
            "2026-10",
            "TWD",
            "monthly_preparation_period_not_completed",
        ),
    ),
)
def test_preparation_rejections_preserve_transport_and_canonical_originals_in_quarantine(
    tmp_path: Path,
    case: str,
    period: str,
    unit: str,
    reason: str,
) -> None:
    capture = _capture()
    scope = _scope(unit=unit)
    batch_id = f"rejected-{case}"

    result = _publish(
        tmp_path / "rejected-snapshots",
        capture=capture,
        scope=scope,
        acceptance=_acceptance(scope),
        period=period,
        batch_id=batch_id,
    )

    assert not result.success
    assert result.status == "quarantined"
    assert result.quarantine_path is not None
    assert reason in result.diagnostics[0]
    quarantine = json.loads(Path(result.quarantine_path).read_text(encoding="utf-8"))
    assert quarantine["failure_reason_code"] == result.diagnostics[0]
    assert base64.b64decode(quarantine["raw_source_bytes_base64"]) == (
        capture.canonical_source_bytes
    )
    transport = quarantine["transport_capture"]
    assert base64.b64decode(transport["raw_response_bytes_base64"]) == (
        capture.raw_response_bytes
    )
    assert transport["transport_sha256"] == capture.transport_sha256
    assert quarantine["canonical_payload_matches_transport"] is True
    assert not (tmp_path / "rejected-snapshots" / batch_id).exists()


def test_normalizer_rejection_is_named_and_quarantines_the_original_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_module.monthly_revenue_daily_snapshot_update as update_module

    capture = _capture()

    def reject_normalization(_row: dict[str, str]) -> dict[str, str]:
        raise ValueError("synthetic-normalizer-rejected-value")

    monkeypatch.setattr(
        update_module,
        "normalize_current_observation",
        reject_normalization,
    )
    result = _publish(
        tmp_path / "normalizer-rejected-snapshots",
        capture=capture,
        batch_id="normalizer-rejected-20261002",
    )

    assert not result.success
    assert result.status == "quarantined"
    assert result.quarantine_path is not None
    assert "synthetic-normalizer-rejected-value" in result.diagnostics[0]
    quarantine = json.loads(Path(result.quarantine_path).read_text(encoding="utf-8"))
    assert base64.b64decode(quarantine["raw_source_bytes_base64"]) == (
        capture.canonical_source_bytes
    )
    assert base64.b64decode(
        quarantine["transport_capture"]["raw_response_bytes_base64"]
    ) == capture.raw_response_bytes


def test_reused_batch_id_cannot_replace_the_first_snapshot_and_quarantines_retry(
    tmp_path: Path,
) -> None:
    root = tmp_path / "create-only-snapshots"
    first_capture = _capture(current_amount="1,000")
    first = _publish(root, capture=first_capture)
    retry_capture = _capture(current_amount="1,001")

    retry = _publish(root, capture=retry_capture)

    assert first.success
    assert not retry.success
    assert retry.status == "quarantined"
    assert any("不可變快照 batch_id 已存在" in item for item in retry.diagnostics)
    assert retry.quarantine_path is not None
    quarantine = json.loads(Path(retry.quarantine_path).read_text(encoding="utf-8"))
    assert base64.b64decode(quarantine["raw_source_bytes_base64"]) == (
        retry_capture.canonical_source_bytes
    )
    assert first.raw_source_sha256 != retry.raw_source_sha256

    pinned_status = read_daily_monthly_revenue_snapshot_status(
        root,
        batch_id="monthly-update-20261002",
        period="2026-09",
        expected_scope=_scope(),
        trusted_acceptance=_acceptance(_scope()),
    )
    assert pinned_status.available
    assert pinned_status.raw_source_sha256 == first.raw_source_sha256
    assert pinned_status.transport_sha256 == first_capture.transport_sha256


def test_cancel_after_durable_receipt_quarantines_without_public_success_batch(
    tmp_path: Path,
) -> None:
    root = tmp_path / "cancelled-snapshots"
    values = iter(_CLOCK_VALUES)
    clock_calls = 0
    cancellation_observed = False

    def clock() -> datetime:
        nonlocal clock_calls, cancellation_observed
        clock_calls += 1
        value = next(values)
        # 第四次樣本是 writer 的 receipt 持久化後時鐘；隨後的 pre-rename
        # check_cancel 應阻止 public rename，clock 不承擔取消輪詢。
        if clock_calls == 4:
            cancellation_observed = True
        return value

    result = publish_daily_monthly_revenue_snapshot(
        root=root,
        capture=_capture(),
        period="2026-09",
        batch_id="cancelled-after-receipt-20261002",
        source_batch_started_at=datetime(2026, 10, 2, 9, 55, tzinfo=TAIPEI),
        use_acceptance=_acceptance(_scope()),
        scope=_scope(),
        clock=clock,
        check_cancel=lambda: cancellation_observed,
    )

    assert clock_calls == 4
    assert not result.success
    assert result.status == "cancelled"
    assert result.quarantine_path is not None
    assert "daily_monthly_cancelled_before_publish:snapshot_writer_pre_publish" in (
        result.diagnostics[0]
    )
    assert not (root / "cancelled-after-receipt-20261002").exists()
    quarantine = json.loads(Path(result.quarantine_path).read_text(encoding="utf-8"))
    assert base64.b64decode(quarantine["transport_capture"]["raw_response_bytes_base64"]) == (
        _capture().raw_response_bytes
    )


def test_update_service_explicit_capture_port_and_read_status_stay_in_test_roots(
    tmp_path: Path,
) -> None:
    config = TWStockConfig(
        data_root=tmp_path / "configured-formal-data",
        output_root=tmp_path / "configured-output",
        profile="prod",
        personal_data_root=None,
        personal_watchlist_source=None,
        personal_journal_root=None,
        personal_journal_mode=None,
        personal_store_root=None,
        personal_store_mode=None,
    )
    formal_database = config.db_file
    old_availability_csv = config.monthly_revenue_availability_file
    old_availability_bytes = b"legacy availability CSV must remain unchanged\n"
    old_availability_csv.write_bytes(old_availability_bytes)
    old_candidate_csv = (
        config.output_root
        / "monthly_revenue_mops_snapshots"
        / "legacy-monthly-revenue.csv"
    )
    old_candidate_csv.parent.mkdir(parents=True, exist_ok=True)
    old_candidate_bytes = b"legacy monthly revenue candidate must remain unchanged\n"
    old_candidate_csv.write_bytes(old_candidate_bytes)
    assert not formal_database.exists()

    snapshot_root = tmp_path / "explicit-daily-snapshot-root"
    scope = _scope()
    acceptance = _acceptance(scope)
    service = UpdateService(config)
    result = service.save_daily_monthly_revenue_capture(
        snapshot_root=snapshot_root,
        capture=_capture(),
        period="2026-09",
        batch_id="update-service-pinned-batch-20261002",
        source_batch_started_at=datetime(2026, 10, 2, 9, 55, tzinfo=TAIPEI),
        trusted_acceptance=acceptance,
        scope=scope,
        clock=_publish_clock(),
        cancel_callback=lambda: False,
    )
    assert result.success
    assert result.batch_id == "update-service-pinned-batch-20261002"
    manifest_path = snapshot_root / result.batch_id / "manifest.json"
    receipt_path = snapshot_root / result.batch_id / "receipt.json"
    manifest_before = manifest_path.read_bytes()
    receipt_before = receipt_path.read_bytes()

    status = service.read_daily_monthly_revenue_status(
        snapshot_root=snapshot_root,
        batch_id="update-service-pinned-batch-20261002",
        period="2026-09",
        scope=scope,
        trusted_acceptance=acceptance,
    )
    unlisted_status = service.read_daily_monthly_revenue_status(
        snapshot_root=snapshot_root,
        batch_id="unlisted-no-latest-fallback",
        period="2026-09",
        scope=scope,
        trusted_acceptance=acceptance,
    )

    assert status.available
    assert status.batch_id == "update-service-pinned-batch-20261002"
    assert status.scope == scope
    assert status.raw_source_sha256 == result.raw_source_sha256
    assert status.transport_sha256 == _capture().transport_sha256
    assert not unlisted_status.available
    assert unlisted_status.batch_id == "unlisted-no-latest-fallback"
    assert unlisted_status.raw_source_sha256 is None
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == hashlib.sha256(
        manifest_before
    ).hexdigest()
    assert hashlib.sha256(receipt_path.read_bytes()).hexdigest() == hashlib.sha256(
        receipt_before
    ).hexdigest()
    assert not formal_database.exists()
    assert old_availability_csv.read_bytes() == old_availability_bytes
    assert old_candidate_csv.read_bytes() == old_candidate_bytes
