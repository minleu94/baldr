from __future__ import annotations

import csv
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import sqlite3
from typing import Any

import pytest

from app_module import theme_daily_service, theme_daily_sqlite_reader
from app_module.theme_research_snapshot import read_theme_research_snapshot
from decision_module.industry_theme_map import ThemeMappingRow


TAIPEI = timezone(timedelta(hours=8))
DATA_DATE = "2026-10-16"
COMPLETED_AT = "2026-10-17T06:05:12+00:00"
AVAILABLE_AT = datetime(2026, 10, 17, 15, 0, tzinfo=TAIPEI)
KNOWN_AT = datetime(2026, 10, 18, 12, 0, tzinfo=TAIPEI)
_MAPPING_FIELDS = tuple(field.name for field in fields(ThemeMappingRow))


def _mapping_record(
    chain_name: str,
    theme_name: str,
    stock_id: str,
    snapshot_date: str,
    available_date: str,
) -> dict[str, str]:
    return {
        "snapshot_date": snapshot_date,
        "available_date": available_date,
        "stock_id": stock_id,
        "stock_name": f"fixture-{stock_id}",
        "market_type": "上市",
        "l1_industry_category": "半導體",
        "chain_name": chain_name,
        "chain_tier": "中游",
        "theme_name": theme_name,
        "is_primary": "true",
        "assignment_method": "snapshot-test",
        "source_name": "snapshot-fixture",
        "source_tier": "T1",
        "pit_mode": "quarterly_snapshot",
        "evidence_note": "synthetic test mapping",
    }


def _mapping_csv(
    rows: tuple[tuple[str, str, str, str, str], ...] | None = None,
    *,
    missing_field: str | None = None,
) -> bytes:
    if rows is None:
        rows = (("半導體", "晶圓製造", "2330", DATA_DATE, DATA_DATE),)
    fieldnames = tuple(field for field in _MAPPING_FIELDS if field != missing_field)
    stream = StringIO()
    writer = csv.DictWriter(
        stream, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(_mapping_record(*row) for row in rows)
    return stream.getvalue().encode("utf-8")


def _write_prices(path: Path, *, minimal_schema: bool = True) -> None:
    with sqlite3.connect(path) as connection:
        if minimal_schema:
            connection.execute(
                'CREATE TABLE daily_prices ("證券代號" TEXT, "日期" TEXT)'
            )
            connection.execute(
                'INSERT INTO daily_prices VALUES (?, ?)', ("2330", DATA_DATE),
            )
        else:
            connection.execute(
                'CREATE TABLE daily_prices ('
                '"證券代號" TEXT, "日期" TEXT, "收盤價" TEXT, '
                '"漲跌價差" TEXT, "成交金額" TEXT, "成交股數" TEXT)'
            )
            connection.execute(
                'INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?)',
                ("2330", DATA_DATE, None, None, None, None),
            )


def _write_manifest(
    path: Path,
    *,
    mapping_bytes: bytes,
    prices_path: Path,
    saved_completed_at: str = COMPLETED_AT,
    schema: str = "baldr.theme_research_snapshot.v1",
) -> bytes:
    value = {
        "schema": schema,
        "data_date": DATA_DATE,
        "saved_completed_at": saved_completed_at,
        "mapping": {
            "path": "mapping.csv",
            "sha256": sha256(mapping_bytes).hexdigest(),
        },
        "prices": {
            "path": "prices.sqlite",
            "sha256": sha256(prices_path.read_bytes()).hexdigest(),
        },
    }
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    path.write_bytes(raw)
    return raw


def _snapshot_files(
    tmp_path: Path,
    *,
    rows: tuple[tuple[str, str, str, str, str], ...] | None = None,
    saved_completed_at: str = COMPLETED_AT,
    missing_mapping_field: str | None = None,
) -> tuple[Path, Path, Path, bytes, bytes]:
    root = tmp_path / "saved-theme-version"
    root.mkdir()
    mapping_path = root / "mapping.csv"
    prices_path = root / "prices.sqlite"
    manifest_path = root / "snapshot.json"
    mapping_bytes = _mapping_csv(rows, missing_field=missing_mapping_field)
    mapping_path.write_bytes(mapping_bytes)
    _write_prices(prices_path)
    manifest_bytes = _write_manifest(
        manifest_path,
        mapping_bytes=mapping_bytes,
        prices_path=prices_path,
        saved_completed_at=saved_completed_at,
    )
    return manifest_path, mapping_path, prices_path, manifest_bytes, mapping_bytes


def test_external_identity_anchor_rejects_rewritten_self_consistent_manifest(tmp_path):
    manifest, _, _, original, _ = _snapshot_files(tmp_path)
    anchor = sha256(original).hexdigest()
    first = read_theme_research_snapshot(manifest, known_at=KNOWN_AT, expected_identity_sha256=anchor)
    assert first.identity_sha256 == anchor
    meta = json.loads(original)
    meta["saved_completed_at"] = "2026-10-16T00:00:00+08:00"
    manifest.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ValueError, match="保存身份SHA256"):
        read_theme_research_snapshot(manifest, known_at=KNOWN_AT, expected_identity_sha256=anchor)


def _manifest_value(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_public_snapshot_pins_both_originals_and_rereads_without_mutation(tmp_path):
    manifest_path, mapping_path, prices_path, manifest_raw, mapping_raw = _snapshot_files(tmp_path)
    prices_raw = prices_path.read_bytes()

    first = read_theme_research_snapshot(manifest_path, known_at=KNOWN_AT)
    second = read_theme_research_snapshot(manifest_path, known_at=KNOWN_AT)

    assert first == second
    assert first.identity_sha256 == sha256(manifest_raw).hexdigest()
    assert first.mapping
    assert first.report.data_date.isoformat() == DATA_DATE
    assert first.report.known_at == KNOWN_AT
    assert first.report.status == "current_research"
    assert first.report.historical_pit_eligible is False
    assert mapping_path.read_bytes() == mapping_raw
    assert prices_path.read_bytes() == prices_raw
    assert manifest_path.read_bytes() == manifest_raw


@pytest.mark.parametrize("source", ["mapping", "prices"])
def test_snapshot_rejects_each_original_after_its_pinned_sha_changes(tmp_path, source: str):
    manifest_path, mapping_path, prices_path, _, _ = _snapshot_files(tmp_path)
    target = mapping_path if source == "mapping" else prices_path
    with target.open("ab") as stream:
        stream.write(b"changed-after-save")

    with pytest.raises(ValueError, match="檔案SHA256不符"):
        read_theme_research_snapshot(manifest_path, known_at=KNOWN_AT)


@pytest.mark.parametrize(
    ("schema", "manifest_bytes", "message"),
    [
        pytest.param("unsupported.schema", None, "不支援的題材版本格式", id="schema"),
        pytest.param(None, 32769, "超過32KiB", id="manifest-size"),
    ],
)
def test_snapshot_requires_supported_schema_and_bounded_manifest(
    tmp_path, schema: str | None, manifest_bytes: int | None, message: str,
):
    manifest_path, _, _, _, _ = _snapshot_files(tmp_path)
    if schema is not None:
        value = _manifest_value(manifest_path)
        value["schema"] = schema
        manifest_path.write_text(json.dumps(value), encoding="utf-8")
    else:
        assert manifest_bytes is not None
        manifest_path.write_bytes(b" " * manifest_bytes)

    with pytest.raises(ValueError, match=message):
        read_theme_research_snapshot(manifest_path, known_at=KNOWN_AT)


@pytest.mark.parametrize("source", ["mapping", "prices"])
@pytest.mark.parametrize("external_kind", ["traversal", "absolute"])
def test_snapshot_rejects_source_path_outside_selected_version(
    tmp_path, source: str, external_kind: str,
):
    manifest_path, mapping_path, prices_path, _, _ = _snapshot_files(tmp_path)
    source_path = mapping_path if source == "mapping" else prices_path
    outside = tmp_path / f"outside-{source_path.name}"
    outside.write_bytes(source_path.read_bytes())
    value = _manifest_value(manifest_path)
    value[source]["path"] = (
        f"../{outside.name}" if external_kind == "traversal" else str(outside.resolve())
    )
    manifest_path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match="檔案越界"):
        read_theme_research_snapshot(manifest_path, known_at=KNOWN_AT)


@pytest.mark.parametrize("source", ["mapping", "prices"])
def test_snapshot_rejects_source_symlink_that_resolves_outside_version(tmp_path, source: str):
    manifest_path, mapping_path, prices_path, _, _ = _snapshot_files(tmp_path)
    source_path = mapping_path if source == "mapping" else prices_path
    outside = tmp_path / f"outside-{source_path.name}"
    outside.write_bytes(source_path.read_bytes())
    link = source_path.parent / f"{source}-link"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"目前環境不能建立測試 symlink：{exc}")
    value = _manifest_value(manifest_path)
    value[source]["path"] = link.name
    manifest_path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match="檔案越界"):
        read_theme_research_snapshot(manifest_path, known_at=KNOWN_AT)


def test_completed_at_rounds_up_in_taipei_and_rejects_before_available_hour(tmp_path):
    manifest_path, _, _, _, _ = _snapshot_files(tmp_path)
    one_microsecond_early = AVAILABLE_AT - timedelta(microseconds=1)

    with pytest.raises(ValueError, match="尚未到可用小時"):
        read_theme_research_snapshot(manifest_path, known_at=one_microsecond_early)

    snapshot = read_theme_research_snapshot(manifest_path, known_at=AVAILABLE_AT)
    assert snapshot.report.known_at == AVAILABLE_AT
    assert snapshot.report.status == "current_research"
    assert snapshot.report.historical_pit_eligible is False


@pytest.mark.parametrize("naive_field", ["saved_completed_at", "known_at"])
def test_snapshot_rejects_naive_batch_or_query_clock(tmp_path, naive_field: str):
    manifest_path, _, _, _, _ = _snapshot_files(
        tmp_path,
        saved_completed_at=("2026-10-17T06:05:12" if naive_field == "saved_completed_at" else COMPLETED_AT),
    )
    known_at = (
        datetime(2026, 10, 18, 12, 0)
        if naive_field == "known_at" else KNOWN_AT
    )

    with pytest.raises(ValueError, match="包含時區"):
        read_theme_research_snapshot(manifest_path, known_at=known_at)


@pytest.mark.parametrize("mapping_case", ["mixed-dates", "future-available-date"])
def test_snapshot_rejects_mixed_or_future_mapping_dates(tmp_path, mapping_case: str):
    rows = (
        ("半導體", "晶圓製造", "2330", DATA_DATE, DATA_DATE),
        (
            "半導體", "封裝測試", "2317",
            "2026-10-15" if mapping_case == "mixed-dates" else DATA_DATE,
            "2026-10-15" if mapping_case == "mixed-dates" else "2026-10-17",
        ),
    )
    manifest_path, _, _, _, _ = _snapshot_files(tmp_path, rows=rows)

    with pytest.raises(ValueError, match="日期與成分對應不一致"):
        read_theme_research_snapshot(manifest_path, known_at=KNOWN_AT)


def test_snapshot_rejects_mapping_missing_a_theme_mapping_field(tmp_path):
    manifest_path, _, _, _, _ = _snapshot_files(
        tmp_path,
        missing_mapping_field="chain_name",
    )

    with pytest.raises(ValueError):
        read_theme_research_snapshot(manifest_path, known_at=KNOWN_AT)


@pytest.mark.parametrize(
    "empty_field",
    ["chain_name", "theme_name", "snapshot_date", "available_date"],
)
def test_snapshot_rejects_empty_mapping_classification_or_date(tmp_path, empty_field: str):
    row = ["半導體", "晶圓製造", "2330", DATA_DATE, DATA_DATE]
    field_index = {
        "chain_name": 0,
        "theme_name": 1,
        "snapshot_date": 3,
        "available_date": 4,
    }[empty_field]
    row[field_index] = ""
    manifest_path, _, _, _, _ = _snapshot_files(tmp_path, rows=(tuple(row),))

    with pytest.raises(ValueError):
        read_theme_research_snapshot(manifest_path, known_at=KNOWN_AT)


def test_snapshot_rejects_mapping_rows_dropped_during_csv_decode(tmp_path):
    rows = (
        ("半導體", "晶圓製造", "2330", DATA_DATE, DATA_DATE),
        ("半導體", "封裝測試", "", DATA_DATE, DATA_DATE),
    )
    manifest_path, _, _, _, _ = _snapshot_files(tmp_path, rows=rows)

    with pytest.raises(ValueError):
        read_theme_research_snapshot(manifest_path, known_at=KNOWN_AT)


def test_snapshot_keeps_unknown_price_flow_and_five_session_metrics_missing(tmp_path):
    manifest_path, _, _, _, _ = _snapshot_files(tmp_path)

    snapshot = read_theme_research_snapshot(manifest_path, known_at=KNOWN_AT)

    assert len(snapshot.report.rows) == 1
    row = snapshot.report.rows[0]
    assert row.mean_return_pct is None
    assert row.turnover_twd is None
    assert row.volume_multiple_5d is None
    assert row.institutional_net_shares is None
    assert row.institutional_net_turnover_twd is None
    assert row.coverage.returns == 0
    assert row.coverage.turnover == 0
    assert row.coverage.volume_history == 0
    assert row.coverage.institutional_shares == 0
    assert row.coverage.institutional_amount == 0
    assert "five_session_calendar_unavailable" in snapshot.report.warnings
    assert "institutional_flows_schema_unavailable" in snapshot.report.warnings
    assert snapshot.report.historical_pit_eligible is False


@pytest.mark.parametrize("changed_file", ["mapping", "manifest"])
def test_snapshot_rechecks_mapping_and_manifest_after_report_build(
    tmp_path, monkeypatch, changed_file: str,
):
    manifest_path, mapping_path, _, _, _ = _snapshot_files(tmp_path)
    original_build = theme_daily_service.ThemeDailyService.build

    def mutate_mapping_after_build(service, data_date, known_at):
        report = original_build(service, data_date, known_at)
        target = mapping_path if changed_file == "mapping" else manifest_path
        with target.open("ab") as stream:
            stream.write(b"# changed while reading\n")
        return report

    monkeypatch.setattr(theme_daily_service.ThemeDailyService, "build", mutate_mapping_after_build)

    with pytest.raises(ValueError, match="讀取期間變動"):
        read_theme_research_snapshot(manifest_path, known_at=KNOWN_AT)


def test_sqlite_source_sha_change_during_market_read_is_rejected(tmp_path, monkeypatch):
    manifest_path, _, _, _, _ = _snapshot_files(tmp_path)
    original_verify = theme_daily_sqlite_reader.SQLiteThemeMarketReader._verify
    verify_calls = 0

    def mutate_before_final_verify(reader):
        nonlocal verify_calls
        verify_calls += 1
        if verify_calls == 2:
            with reader.database.open("ab") as stream:
                stream.write(b"changed-between-sqlite-checks")
        return original_verify(reader)

    monkeypatch.setattr(
        theme_daily_sqlite_reader.SQLiteThemeMarketReader,
        "_verify",
        mutate_before_final_verify,
    )

    with pytest.raises(ValueError, match="SQLite版本SHA256不符"):
        read_theme_research_snapshot(manifest_path, known_at=KNOWN_AT)
