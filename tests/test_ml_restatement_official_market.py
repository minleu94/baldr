"""官方大盤封存核驗：來源、單位、時鐘與不可變性邊界。"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
from typing import Any

import pytest

from data_module.ml_restatement_official_market import (
    REPORT_FIELDS, REPORT_PATHS, file_sha256, load_official_market_capture,
    parse_monthly_report,
)


def _payload(report: str) -> dict[str, Any]:
    row = (
        ["113/01/02", "8,299,689,369", "581,496,914,983", "3,801,445", "28,334.59", "101.24"]
        if report == "FMTQIK" else
        ["113/01/02", "28,253.53", "28,494.99", "28,150.45", "28,334.59"]
    )
    return {"stat": "OK", "date": "20240101", "fields": list(REPORT_FIELDS[report]), "data": [row]}


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _capture(root: Path) -> tuple[Path, dict[str, Any]]:
    receipts = []
    rows = {}
    for report in REPORT_FIELDS:
        payload = _payload(report)
        source = root / f"202401-{report}.json"
        _write(source, payload)
        receipts.append({
            "file": source.name, "report": report, "month": "202401",
            "url": f"https://www.twse.com.tw{REPORT_PATHS[report]}?date=20240101&response=json",
            "captured_at": "2024-02-01T01:00:00+08:00", "historical_pit": False,
            "file_sha256": file_sha256(source), "byte_count": source.stat().st_size,
        })
        for day, values in parse_monthly_report(payload, report=report, month="202401").items():
            rows.setdefault(day.isoformat(), {}).update({key: str(value) for key, value in values.items()})
    manifest = {
        "schema_version": "official-market-source-capture.v1", "historical_pit": False,
        "source_db_write": False, "failures": [], "status": "complete",
        "volume_unit": "TWSE FMTQIK 成交股數（股）", "ohlc_source": "TWSE MI_5MINS_HIST",
        "started_at": "2024-02-01T00:00:00+08:00", "finished_at": "2024-02-01T02:00:00+08:00",
        "cutoff_date": "2024-01-31", "months": ["202401"], "receipts": receipts,
        "rows": rows, "row_count": 1, "original_observed_dates_missing_official": [],
        "official_additional_dates": [],
    }
    path = root / "capture.json"
    _write(path, manifest)
    return path, manifest


def _load(path: Path):
    return load_official_market_capture(
        path, expected_file_sha256=file_sha256(path),
        as_of=datetime.fromisoformat("2024-02-01T03:00:00+08:00"),
    )


def test_exact_units_real_ohlc_and_taipei_capture_clock(tmp_path):
    path, manifest = _capture(tmp_path)
    # UTC 尚在前一日，但臺北已取得 1/31 以前的資料。
    manifest["finished_at"] = "2024-01-31T18:00:00+00:00"
    _write(path, manifest)
    source = _load(path)
    row = source.rows[date(2024, 1, 2)]
    assert row["成交量"] == Decimal("8299689369")
    assert row["開盤價"] == Decimal("28253.53")
    assert row["收盤價"] == Decimal("28334.59")
    assert row["開盤價"] != row["收盤價"]
    assert row["漲跌百分比"] is None
    assert source.available_at == datetime.fromisoformat(manifest["finished_at"])


@pytest.mark.parametrize("value", ["8,29,689,369", "NaN", "--", "-1", "2.5", 8299689369])
def test_invalid_or_fractional_volume_is_rejected(value):
    payload = _payload("FMTQIK")
    payload["data"][0][1] = value
    with pytest.raises(ValueError):
        parse_monthly_report(payload, report="FMTQIK", month="202401")


@pytest.mark.parametrize("kind", ["duplicate", "cross_month", "bad_ohlc", "wrong_fields", "wrong_month"])
def test_report_contract_is_strict(kind):
    payload = _payload("MI_5MINS_HIST")
    if kind == "duplicate":
        payload["data"] *= 2
    elif kind == "cross_month":
        payload["data"][0][0] = "113/02/02"
    elif kind == "bad_ohlc":
        payload["data"][0][2] = "28,000.00"
    elif kind == "wrong_fields":
        payload["fields"][1] = "開盤價"
    else:
        payload["date"] = "20240201"
    with pytest.raises(ValueError):
        parse_monthly_report(payload, report="MI_5MINS_HIST", month="202401")


@pytest.mark.parametrize("kind", ["future", "source_hash", "cached_rows", "url", "missing_report", "duplicate_report", "capture_clock", "failed_response", "manifest_hash"])
def test_manifest_and_response_binding_rejected(tmp_path, kind):
    path, manifest = _capture(tmp_path)
    original_hash = file_sha256(path)
    if kind == "future":
        manifest["finished_at"] = "2024-02-02T02:00:00+08:00"
    elif kind == "source_hash":
        (tmp_path / manifest["receipts"][0]["file"]).write_text("{}", encoding="utf-8")
    elif kind == "cached_rows":
        manifest["rows"]["2024-01-02"]["成交股數"] = "8299689"
    elif kind == "url":
        manifest["receipts"][0]["url"] = "https://example.com/report"
    elif kind == "missing_report":
        manifest["receipts"].pop()
    elif kind == "duplicate_report":
        manifest["receipts"][1] = manifest["receipts"][0]
    elif kind == "capture_clock":
        manifest["receipts"][0]["captured_at"] = "2024-01-30T23:00:00+08:00"
    elif kind == "failed_response":
        manifest["failures"] = [{"month": "202401"}]
    else:
        manifest["status"] = "unknown"
    _write(path, manifest)
    with pytest.raises(ValueError):
        if kind == "manifest_hash":
            load_official_market_capture(path, expected_file_sha256=original_hash, as_of=datetime.fromisoformat("2024-02-01T03:00:00+08:00"))
        else:
            _load(path)


def test_reports_must_agree_on_close_even_with_rehashed_receipt(tmp_path):
    path, manifest = _capture(tmp_path)
    source = tmp_path / "202401-MI_5MINS_HIST.json"
    payload = _payload("MI_5MINS_HIST")
    payload["data"][0][-1] = "28,334.60"
    _write(source, payload)
    manifest["receipts"][1]["file_sha256"] = file_sha256(source)
    manifest["receipts"][1]["byte_count"] = source.stat().st_size
    _write(path, manifest)
    with pytest.raises(ValueError, match="收盤指數不一致"):
        _load(path)


def test_incomplete_only_allowed_for_old_calendar_difference(tmp_path):
    path, manifest = _capture(tmp_path)
    manifest["status"] = "incomplete"
    _write(path, manifest)
    with pytest.raises(ValueError, match="擷取狀態"):
        _load(path)
    manifest["original_observed_dates_missing_official"] = ["2024-01-01"]
    _write(path, manifest)
    assert _load(path).original_calendar_missing == (date(2024, 1, 1),)


def test_capture_may_contain_later_rows_but_never_consumes_them(tmp_path):
    path, manifest = _capture(tmp_path)
    for entry in manifest["receipts"]:
        source = tmp_path / entry["file"]
        payload = _payload(entry["report"])
        later = list(payload["data"][0])
        later[0] = "113/01/03"
        payload["data"].append(later)
        _write(source, payload)
        entry["file_sha256"] = file_sha256(source)
        entry["byte_count"] = source.stat().st_size
    manifest["cutoff_date"] = "2024-01-02"
    _write(path, manifest)
    assert list(_load(path).rows) == [date(2024, 1, 2)]


def _two_month_capture(root: Path) -> tuple[Path, dict[str, Any]]:
    path, manifest = _capture(root)
    manifest.update({
        "months": ["202401", "202402"], "cutoff_date": "2024-02-29",
        "started_at": "2024-03-01T00:00:00+08:00",
        "finished_at": "2024-03-01T02:00:00+08:00", "row_count": 2,
    })
    for report in REPORT_FIELDS:
        payload = _payload(report)
        payload["date"] = "20240201"
        payload["data"][0][0] = "113/02/02"
        source = root / f"202402-{report}.json"
        _write(source, payload)
        manifest["receipts"].append({
            "file": source.name, "report": report, "month": "202402",
            "url": f"https://www.twse.com.tw{REPORT_PATHS[report]}?date=20240201&response=json",
            "captured_at": "2024-03-01T01:00:00+08:00", "historical_pit": False,
            "file_sha256": file_sha256(source), "byte_count": source.stat().st_size,
        })
        for day, values in parse_monthly_report(payload, report=report, month="202402").items():
            manifest["rows"].setdefault(day.isoformat(), {}).update({key: str(value) for key, value in values.items()})
    _write(path, manifest)
    return path, manifest


def test_completed_earlier_month_preserves_its_original_capture_clock(tmp_path):
    path, manifest = _two_month_capture(tmp_path)
    original_clocks = [item["captured_at"] for item in manifest["receipts"]]
    source = load_official_market_capture(
        path, expected_file_sha256=file_sha256(path),
        as_of=datetime.fromisoformat("2024-03-01T03:00:00+08:00"),
    )
    assert list(source.rows) == [date(2024, 1, 2), date(2024, 2, 2)]
    assert original_clocks[:2] == ["2024-02-01T01:00:00+08:00"] * 2
    assert [item["captured_at"] for item in json.loads(path.read_text(encoding="utf-8"))["receipts"]] == original_clocks


@pytest.mark.parametrize("index,clock", [
    (0, "2024-01-31T23:59:00+08:00"),
    (2, "2024-02-29T23:59:00+08:00"),
    (0, "2024-03-01T02:01:00+08:00"),
])
def test_each_month_must_be_available_before_consumption(tmp_path, index, clock):
    path, manifest = _two_month_capture(tmp_path)
    manifest["receipts"][index]["captured_at"] = clock
    _write(path, manifest)
    with pytest.raises(ValueError, match="回應時鐘"):
        load_official_market_capture(
            path, expected_file_sha256=file_sha256(path),
            as_of=datetime.fromisoformat("2024-03-01T03:00:00+08:00"),
        )
