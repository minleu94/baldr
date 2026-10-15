from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import app_module.official_attention_report_provider as provider_module
from app_module.official_attention_report_provider import OfficialAttentionReportProvider
from app_module.official_attention_snapshot import (
    OfficialAttentionSnapshotError,
    OfficialAttentionSnapshotPin,
    OfficialAttentionSnapshotRead,
)
from app_module.stock_research_report_service import StockResearchReportReadService
from data_module.selection_official_attention import OfficialAttentionRow


_TAIPEI = ZoneInfo("Asia/Taipei")
_MANIFEST_SHA256 = "a" * 64
_RECEIPT_SHA256 = "b" * 64


def _pin(tmp_path: Path) -> OfficialAttentionSnapshotPin:
    return OfficialAttentionSnapshotPin(
        directory=tmp_path,
        manifest_sha256=_MANIFEST_SHA256,
        receipt_sha256=_RECEIPT_SHA256,
    )


def _row(query_date: date) -> OfficialAttentionRow:
    official_date = f"{query_date.year - 1911}年{query_date.month}月{query_date.day}日"
    return OfficialAttentionRow(
        stock_code="2330",
        stock_name="台積電",
        announcement_date=query_date.isoformat(),
        official_date_original_text=official_date,
        announcement_count_original_text="第 03 次",
        reason_original_text="<font color='red'>營業收入</font>",
        reason_text="營業收入",
        closing_price_original_text="1,234.50",
        pe_original_text="27.80",
        raw_row_sha256="c" * 64,
    )


def _snapshot(
    pin: OfficialAttentionSnapshotPin,
    stock_code: str,
    query_date: date,
    *,
    rows: tuple[OfficialAttentionRow, ...] | None = None,
) -> OfficialAttentionSnapshotRead:
    batch_time = datetime.combine(query_date, time(15, 20), _TAIPEI)
    return OfficialAttentionSnapshotRead(
        pin=pin,
        query_date=query_date.isoformat(),
        stock_code=stock_code,
        rows=(_row(query_date),) if rows is None else rows,
        total_securities=18,
        source_url="https://www.twse.com.tw/attention-report",
        first_persisted_at=batch_time,
        successful_batch_completed_at=batch_time,
        available_hour=datetime.combine(query_date, time(16, 0), _TAIPEI),
        availability_basis="successful_batch_completion_fallback",
    )


@pytest.mark.parametrize(
    ("report_date", "observed_at", "expected_cutoff"),
    (
        (
            date(2026, 10, 15),
            datetime(2026, 10, 15, 9, 30, tzinfo=_TAIPEI),
            datetime(2026, 10, 15, 9, 30, tzinfo=_TAIPEI),
        ),
        (
            date(2026, 10, 14),
            datetime(2026, 10, 15, 9, 30, tzinfo=_TAIPEI),
            datetime(2026, 10, 14, 23, 59, 59, 999999, tzinfo=_TAIPEI),
        ),
    ),
)
def test_provider_bounds_snapshot_cutoff_to_observation_and_report_day(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    report_date: date,
    observed_at: datetime,
    expected_cutoff: datetime,
) -> None:
    pin = _pin(tmp_path)
    calls: list[tuple[OfficialAttentionSnapshotPin, str, datetime, object]] = []

    def read_snapshot(
        received_pin: OfficialAttentionSnapshotPin,
        *,
        stock_code: str,
        decision_cutoff: datetime,
        check_cancel: object,
    ) -> OfficialAttentionSnapshotRead:
        calls.append((received_pin, stock_code, decision_cutoff, check_cancel))
        return _snapshot(received_pin, stock_code, report_date)

    monkeypatch.setattr(provider_module, "read_official_attention_snapshot", read_snapshot)
    report = OfficialAttentionReportProvider(pin).read(
        "2330", as_of_date=report_date, observed_at=observed_at
    )

    assert report.status == "available"
    assert calls == [(pin, "2330", expected_cutoff, None)]


def test_provider_rejects_future_report_date_before_snapshot_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(
        provider_module,
        "read_official_attention_snapshot",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    report = OfficialAttentionReportProvider(_pin(tmp_path)).read(
        "2330",
        as_of_date=date(2026, 10, 16),
        observed_at=datetime(2026, 10, 15, 12, 0, tzinfo=_TAIPEI),
    )

    assert report.status == "unknown"
    assert "未來報告日" in report.limitations[0]
    assert calls == []


def test_provider_preserves_source_strings_and_exact_pin_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pin = _pin(tmp_path)
    observed_at = datetime(2026, 10, 15, 17, 30, tzinfo=_TAIPEI)
    monkeypatch.setattr(
        provider_module,
        "read_official_attention_snapshot",
        lambda received_pin, **kwargs: _snapshot(received_pin, "2330", date(2026, 10, 15)),
    )

    report = OfficialAttentionReportProvider(pin).read(
        "2330", as_of_date=date(2026, 10, 15), observed_at=observed_at
    )

    assert report.status == "available"
    assert report.manifest_sha256 == _MANIFEST_SHA256
    assert report.receipt_sha256 == _RECEIPT_SHA256
    assert report.query_date == "2026-10-15"
    assert report.available_hour == "2026-10-15T16:00:00+08:00"
    assert len(report.rows) == 1
    row = report.rows[0]
    assert row.stock_code == "2330"
    assert row.official_date_original_text == "115年10月15日"
    assert row.announcement_count_original_text == "第 03 次"
    assert row.closing_price_original_text == "1,234.50"
    assert row.pe_original_text == "27.80"
    assert row.reason_text == "營業收入"
    assert all(
        isinstance(value, str)
        for value in (
            row.announcement_count_original_text,
            row.closing_price_original_text,
            row.pe_original_text,
        )
    )


def test_empty_rows_remain_a_dated_twse_only_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pin = _pin(tmp_path)
    monkeypatch.setattr(
        provider_module,
        "read_official_attention_snapshot",
        lambda received_pin, **kwargs: _snapshot(
            received_pin, "2330", date(2026, 10, 15), rows=()
        ),
    )

    report = OfficialAttentionReportProvider(pin).read(
        "2330",
        as_of_date=date(2026, 10, 15),
        observed_at=datetime(2026, 10, 15, 17, 30, tzinfo=_TAIPEI),
    )

    assert report.status == "available"
    assert report.query_date == "2026-10-15"
    assert report.rows == ()
    assert report.source_url.startswith("https://www.twse.com.tw/")
    assert "僅明示TWSE公告日" in report.limitations[0]


def test_missing_or_invalid_environment_pin_is_isolated_as_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory_name = "OFFICIAL_ATTENTION_SNAPSHOT_DIRECTORY"
    manifest_name = "OFFICIAL_ATTENTION_MANIFEST_SHA256"
    receipt_name = "OFFICIAL_ATTENTION_RECEIPT_SHA256"
    for name in (directory_name, manifest_name, receipt_name):
        monkeypatch.delenv(name, raising=False)

    no_pin = OfficialAttentionReportProvider.from_environment().read(
        "2330",
        as_of_date=date(2026, 10, 15),
        observed_at=datetime(2026, 10, 15, 17, 30, tzinfo=_TAIPEI),
    )
    assert no_pin.status == "unknown"

    monkeypatch.setenv(directory_name, str(tmp_path))
    monkeypatch.setenv(manifest_name, _MANIFEST_SHA256)
    partial_pin = OfficialAttentionReportProvider.from_environment().read(
        "2330",
        as_of_date=date(2026, 10, 15),
        observed_at=datetime(2026, 10, 15, 17, 30, tzinfo=_TAIPEI),
    )
    assert partial_pin.status == "unknown"
    assert "雙SHA" in partial_pin.limitations[0]

    monkeypatch.setenv(receipt_name, _RECEIPT_SHA256)
    monkeypatch.setenv(manifest_name, "A" * 64)
    invalid_pin = OfficialAttentionReportProvider.from_environment().read(
        "2330",
        as_of_date=date(2026, 10, 15),
        observed_at=datetime(2026, 10, 15, 17, 30, tzinfo=_TAIPEI),
    )
    assert invalid_pin.status == "unknown"
    assert "SHA256" in invalid_pin.limitations[0]


def test_reader_failure_is_unknown_and_cancel_callback_is_forwarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pin = _pin(tmp_path)
    cancel_callback = lambda: True
    received_callbacks: list[object] = []

    def fail_reader(
        received_pin: OfficialAttentionSnapshotPin,
        *,
        stock_code: str,
        decision_cutoff: datetime,
        check_cancel: object,
    ) -> OfficialAttentionSnapshotRead:
        assert received_pin == pin
        assert stock_code == "2330"
        assert decision_cutoff.tzinfo is not None
        received_callbacks.append(check_cancel)
        if check_cancel is cancel_callback and cancel_callback():
            raise OfficialAttentionSnapshotError("注意公告讀取已取消")
        raise OfficialAttentionSnapshotError("合成讀取失敗")

    monkeypatch.setattr(provider_module, "read_official_attention_snapshot", fail_reader)
    provider = OfficialAttentionReportProvider(pin)
    read_failure = provider.read(
        "2330",
        as_of_date=date(2026, 10, 15),
        observed_at=datetime(2026, 10, 15, 17, 30, tzinfo=_TAIPEI),
    )
    cancelled = provider.read(
        "2330",
        as_of_date=date(2026, 10, 15),
        observed_at=datetime(2026, 10, 15, 17, 30, tzinfo=_TAIPEI),
        cancel_callback=cancel_callback,
    )

    assert received_callbacks == [None, cancel_callback]
    assert read_failure.status == "unknown"
    assert "合成讀取失敗" in read_failure.limitations[0]
    assert cancelled.status == "unknown"
    assert "已取消" in cancelled.limitations[0]


def test_read_report_exposes_pinned_attention_dto_source_and_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pin = _pin(tmp_path)
    observed_at = datetime(2026, 10, 15, 17, 30, tzinfo=_TAIPEI)
    monkeypatch.setattr(
        provider_module,
        "read_official_attention_snapshot",
        lambda received_pin, **kwargs: _snapshot(received_pin, "2330", date(2026, 10, 15)),
    )
    config = SimpleNamespace(db_file=None, sqlite_db_file=None, output_root=None)
    service = StockResearchReportReadService(
        config,
        official_attention_provider=OfficialAttentionReportProvider(pin),
        clock=lambda: observed_at,
    )

    report = service.read_report("2330", as_of_date=date(2026, 10, 15))

    assert report.official_attention.status == "available"
    assert report.official_attention.manifest_sha256 == _MANIFEST_SHA256
    assert report.official_attention.receipt_sha256 == _RECEIPT_SHA256
    assert report.official_attention.rows[0].closing_price_original_text == "1,234.50"
    assert report.official_attention.rows[0].pe_original_text == "27.80"
    assert "official_attention" in report.available_modules
    source = next(source for source in report.sources if source.source_id == "twse.official_attention")
    assert source.data_as_of == "2026-10-15"
    assert source.version == _MANIFEST_SHA256
    assert source.row_count == 1
    assert source.candidate_only is True
    assert source.historical_pit_eligible is False
