from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from app_module.update_service import UpdateService
from data_module.config import TWStockConfig
from data_module.data_loader import DataLoader
from data_module.db_manager import DBManager
from data_module.twse_industry_index_capture import (
    CSV_COLUMNS,
    TwseIndustryIndexCaptureError,
    assess_industry_name_completeness,
    atomic_write_csv_projection,
    canonical_rowset,
    industry_capture_artifact_dates,
    parse_twse_industry_rows,
    persist_twse_industry_capture,
    recover_industry_capture_receipts_for_csv,
    rowset_sha256,
    verify_capture_receipt,
    verify_csv_date_projection,
    verified_industry_projection_dates,
)


def _payload(*, response_date: str = "115年09月03日", table_title: str | None = None) -> dict:
    return {
        "stat": "OK",
        "date": response_date,
        "tables": [{
            "title": table_title or f"{response_date} 類股指數",
            "rows": [
                ["電子工業類指數", "100.25", "<p style='color:red'>+</p>", "1.00", "0.50"],
                ["觀光餐旅類指數", "200.75", "<p style='color:green'>-</p>", "2.00", "1.25"],
            ],
        }],
    }


def test_industry_parser_accepts_roc_and_gregorian_response_dates():
    roc = _payload()
    rows = parse_twse_industry_rows(roc, "2026-09-03")
    assert len(rows) == 2
    electronic = next(row for row in rows if row["指數名稱"] == "電子工業類指數")
    assert electronic["日期"] == "2026-09-03"
    assert electronic["收盤指數"] == "100.25"

    gregorian = _payload(response_date="2026/09/03", table_title="2026-09-03 類股指數")
    assert parse_twse_industry_rows(gregorian, "2026-09-03")[0]["日期"] == "2026-09-03"


def test_industry_parser_preserves_exact_twse_missing_change_row_as_nulls():
    payload = {
        "stat": "OK",
        "date": "115年09月16日",
        "tables": [{
            "title": "115年09月16日 價格指數(臺灣證券交易所)",
            "fields": [
                "指數", "收盤指數", "漲跌(+/-)", "漲跌點數",
                "漲跌百分比(%)", "特殊處理註記",
            ],
            "data": [["觀光餐旅類指數", "100.95", "", "--", "--", ""]],
        }],
    }

    rows = parse_twse_industry_rows(payload, "2026-09-16")

    assert rows == [{
        "指數名稱": "觀光餐旅類指數",
        "收盤指數": "100.95",
        "漲跌": None,
        "漲跌點數": None,
        "漲跌百分比": None,
        "日期": "2026-09-16",
    }]


def test_industry_parser_treats_html_whitespace_as_blank_direction_only_when_changes_missing():
    payload = _payload()
    payload["tables"][0]["rows"][0][2] = "<p>&nbsp;<br> </p>"
    payload["tables"][0]["rows"][0][3] = "--"
    payload["tables"][0]["rows"][0][4] = "--"

    rows = parse_twse_industry_rows(payload, "2026-09-03")

    row = next(row for row in rows if row["指數名稱"] == "電子工業類指數")
    assert row["漲跌"] is None
    assert row["漲跌點數"] is None
    assert row["漲跌百分比"] is None


@pytest.mark.parametrize(
    ("direction", "change_points", "change_percent"),
    [
        ("", "1.00", "--"),
        ("", "0", "0.00"),
        ("<p>&nbsp;</p>", "--", "0.10"),
        ("X", "--", "--"),
    ],
)
def test_industry_parser_rejects_missing_or_unknown_direction_with_numeric_changes(
    direction, change_points, change_percent,
):
    payload = _payload()
    payload["tables"][0]["rows"][0][2] = direction
    payload["tables"][0]["rows"][0][3] = change_points
    payload["tables"][0]["rows"][0][4] = change_percent

    with pytest.raises(TwseIndustryIndexCaptureError, match="漲跌欄缺少明確方向"):
        parse_twse_industry_rows(payload, "2026-09-03")


@pytest.mark.parametrize(
    ("close", "response_date", "requested_date", "error"),
    [
        ("--", "115年09月16日", "2026-09-16", "收盤指數 缺少數值"),
        ("100.95", "115年09月16日", "2026-09-17", "日期與請求日期不一致"),
    ],
)
def test_industry_parser_still_rejects_missing_close_and_mismatched_date(
    close, response_date, requested_date, error,
):
    payload = {
        "stat": "OK",
        "date": response_date,
        "tables": [{
            "title": f"{response_date} 價格指數(臺灣證券交易所)",
            "data": [["觀光餐旅類指數", close, "", "--", "--", ""]],
        }],
    }

    with pytest.raises(TwseIndustryIndexCaptureError, match=error):
        parse_twse_industry_rows(payload, requested_date)


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({**_payload(), "date": None, "title": None, "tables": [{**_payload()["tables"][0], "title": "類股指數"}]}, "date evidence missing"),
        (_payload(response_date="115年09月02日", table_title="115年09月03日 類股指數"), "response date mismatch"),
        (_payload(response_date="115年02月30日"), "invalid response date"),
    ],
)
def test_industry_parser_rejects_unverified_or_conflicting_response_dates(payload, reason):
    with pytest.raises(TwseIndustryIndexCaptureError):
        parse_twse_industry_rows(payload, "2026-09-03")


def test_industry_name_set_change_degrades_instead_of_carrying_old_rows(tmp_path):
    csv_path = tmp_path / "industry_index.csv"
    pd.DataFrame([
        {"指數名稱": "電子工業類指數", "收盤指數": "90", "漲跌": "+", "漲跌點數": "1", "漲跌百分比": "1", "日期": "2026-09-02"},
        {"指數名稱": "觀光餐旅類指數", "收盤指數": "90", "漲跌": "+", "漲跌點數": "1", "漲跌百分比": "1", "日期": "2026-09-02"},
    ]).to_csv(csv_path, index=False, encoding="utf-8-sig")
    rows = parse_twse_industry_rows(_payload(), "2026-09-03")[:1]

    status, reason = assess_industry_name_completeness(csv_path, "2026-09-03", rows)

    assert status == "degraded"
    assert reason == "industry_name_set_changed_manual_review_required"


def test_missing_same_day_name_degrades_even_when_previous_day_matches(tmp_path):
    csv_path = tmp_path / "industry_index.csv"
    same_day_extra = {
        "指數名稱": "金融保險類指數", "收盤指數": "91", "漲跌": "+",
        "漲跌點數": "1", "漲跌百分比": "1", "日期": "2026-09-03",
    }
    prior_rows = [
        {"指數名稱": "電子工業類指數", "收盤指數": "90", "漲跌": "+", "漲跌點數": "1", "漲跌百分比": "1", "日期": "2026-09-02"},
        {"指數名稱": "觀光餐旅類指數", "收盤指數": "90", "漲跌": "+", "漲跌點數": "1", "漲跌百分比": "1", "日期": "2026-09-02"},
        same_day_extra,
    ]
    pd.DataFrame(prior_rows, columns=CSV_COLUMNS).to_csv(
        csv_path, index=False, encoding="utf-8-sig",
    )
    rows = parse_twse_industry_rows(_payload(), "2026-09-03")

    status, reason = assess_industry_name_completeness(csv_path, "2026-09-03", rows)

    assert status == "degraded"
    assert reason == "same_day_industry_name_set_changed_manual_review_required"


def _config(tmp_path: Path) -> TWStockConfig:
    return TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output")


def _make_capture(config: TWStockConfig) -> Path:
    payload = _payload()
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    rows = parse_twse_industry_rows(payload, "2026-09-03")
    capture = persist_twse_industry_capture(
        output_root=config.output_root,
        source_date="2026-09-03",
        requested_url="https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX",
        final_url="https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20260903&type=IND&response=json",
        request_parameters={"date": "20260903", "type": "IND", "response": "json"},
        http_status=200,
        response_headers={"content-type": "application/json"},
        raw_response=raw,
        captured_at=datetime(2026, 9, 3, 8, 0, tzinfo=timezone.utc),
        parse_status="accepted",
        parse_reason=None,
        response_date_status="verified",
        completeness_status="accepted",
        completeness_reason=None,
        selected_table_titles=["115年09月03日 類股指數"],
        rows=rows,
    )
    return Path(str(capture["path"]))


def _prepare_csv(config: TWStockConfig, *, existing_target: bool) -> tuple[bytes, str]:
    prior_rows = [
        {"指數名稱": "電子工業類指數", "收盤指數": "90", "漲跌": "+", "漲跌點數": "1", "漲跌百分比": "1", "日期": "2026-09-02"},
        {"指數名稱": "觀光餐旅類指數", "收盤指數": "90", "漲跌": "+", "漲跌點數": "1", "漲跌百分比": "1", "日期": "2026-09-02"},
    ]
    if existing_target:
        prior_rows.append({
            "指數名稱": "電子工業類指數", "收盤指數": "1", "漲跌": "-",
            "漲跌點數": "99", "漲跌百分比": "99", "日期": "2026-09-03",
        })
    config.industry_index_file.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(prior_rows, columns=CSV_COLUMNS).to_csv(
        config.industry_index_file,
        index=False,
        encoding="utf-8-sig",
    )
    before = config.industry_index_file.read_bytes()
    rows = parse_twse_industry_rows(_payload(), "2026-09-03")
    _, after_sha = atomic_write_csv_projection(
        config.industry_index_file,
        "2026-09-03",
        rows,
        skip_backup=True,
        config=config,
    )
    return before, after_sha


def _database_snapshot(database_path: Path) -> tuple[list[tuple], dict[str, list[tuple]]]:
    with sqlite3.connect(database_path) as connection:
        schema = connection.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE type IN ('table', 'index', 'view', 'trigger') ORDER BY type, name"
        ).fetchall()
        table_names = [row[1] for row in schema if row[0] == "table"]
        rows = {
            name: sorted(
                connection.execute(f'SELECT * FROM "{name}"').fetchall(),
                key=repr,
            )
            for name in table_names
        }
    return schema, rows


def _service_with_prior_industry_row(config: TWStockConfig) -> UpdateService:
    DBManager(config)
    with sqlite3.connect(config.db_file) as connection:
        connection.execute("DROP TABLE industry_indices")
        connection.execute(
            '''CREATE TABLE industry_indices (
                日期 TEXT,
                指數名稱 TEXT,
                收盤指數 REAL,
                漲跌 TEXT,
                漲跌點數 REAL,
                漲跌百分比 REAL
            )'''
        )
        connection.executemany(
            'INSERT INTO industry_indices VALUES (?, ?, ?, ?, ?, ?)',
            [
                ("20260903", "電子工業類指數", 1, "-", 99, 99),
                ("20260902", "電子工業類指數", 90, "+", 1, 1),
            ],
        )
    return UpdateService(config)


def test_scoped_industry_sync_reads_back_exact_dates_and_writes_marker_last(tmp_path):
    config = _config(tmp_path)
    capture = _make_capture(config)
    service = _service_with_prior_industry_row(config)
    before_csv, after_sha = _prepare_csv(config, existing_target=True)
    service._pending_industry_capture_manifests = [capture]
    service._pending_industry_csv_before = before_csv
    service._pending_industry_csv_after_sha256 = after_sha
    service._industry_update_block_legacy_sync = True
    service._pending_industry_batch_partial = True
    service._pending_industry_failed_dates = ["2026-09-04"]

    result = service.sync_source_to_sqlite("industry_index")

    assert result["success"] is True
    assert result["partial"] is True
    assert result["batch_partial"] is True
    assert result["failed_dates"] == ["2026-09-04"]
    assert Path(result["projection_commit_marker"]).is_file()
    marker_payload = json.loads(Path(result["projection_commit_marker"]).read_text(encoding="utf-8"))
    assert marker_payload["batch_scope_status"] == "partial"
    assert marker_payload["failed_dates"] == ["2026-09-04"]
    assert service._industry_update_block_legacy_sync is True
    with sqlite3.connect(config.db_file) as connection:
        current_rows = connection.execute(
            'SELECT "日期", "指數名稱", "收盤指數" FROM industry_indices ORDER BY "日期", "指數名稱"'
        ).fetchall()
    assert current_rows == [
        ("20260902", "電子工業類指數", 90.0),
        ("20260903", "觀光餐旅類指數", 200.75),
        ("20260903", "電子工業類指數", 100.25),
    ]
    with sqlite3.connect(config.db_file) as connection:
        info = connection.execute("PRAGMA table_info(industry_indices)").fetchall()
    assert [row[1] for row in info] == list(CSV_COLUMNS[-1:]) + list(CSV_COLUMNS[:5])
    assert all(row[5] == 0 for row in info)


def test_missing_change_fields_round_trip_to_sqlite_null_with_exact_marker(tmp_path):
    config = _config(tmp_path)
    service = _service_with_prior_industry_row(config)
    before_csv, _ = _prepare_csv(config, existing_target=True)
    payload = {
        "stat": "OK",
        "date": "115年09月03日",
        "tables": [{
            "title": "115年09月03日 價格指數(臺灣證券交易所)",
            "fields": [
                "指數", "收盤指數", "漲跌(+/-)", "漲跌點數",
                "漲跌百分比(%)", "特殊處理註記",
            ],
            "data": [
                ["電子工業類指數", "100.25", "<p>+</p>", "1.00", "0.50", ""],
                ["觀光餐旅類指數", "100.95", "", "--", "--", ""],
            ],
        }],
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    rows = parse_twse_industry_rows(payload, "2026-09-03")
    capture = persist_twse_industry_capture(
        output_root=config.output_root,
        source_date="2026-09-03",
        requested_url="https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX",
        final_url=(
            "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
            "?date=20260903&type=IND&response=json"
        ),
        request_parameters={"date": "20260903", "type": "IND", "response": "json"},
        http_status=200,
        response_headers={"content-type": "application/json"},
        raw_response=raw,
        captured_at=datetime(2026, 9, 3, 8, 0, tzinfo=timezone.utc),
        parse_status="accepted",
        parse_reason=None,
        response_date_status="verified",
        completeness_status="accepted",
        completeness_reason=None,
        selected_table_titles=["115年09月03日 價格指數(臺灣證券交易所)"],
        rows=rows,
    )
    _, after_csv_sha = atomic_write_csv_projection(
        config.industry_index_file,
        "2026-09-03",
        rows,
        skip_backup=True,
        config=config,
    )
    service._pending_industry_capture_manifests = [Path(str(capture["path"]))]
    service._pending_industry_csv_before = before_csv
    service._pending_industry_csv_after_sha256 = after_csv_sha

    result = service.sync_industry_index_captures_to_sqlite(
        [Path(str(capture["path"]))],
    )

    assert result["success"] is True
    assert result["projection_status"] == "committed_after_exact_csv_sqlite_readback"
    receipt = verify_capture_receipt(capture["path"], config.output_root)
    csv_rows, _csv_sha = verify_csv_date_projection(
        config.industry_index_file,
        [receipt],
    )
    null_csv_row = next(row for row in csv_rows if row["指數名稱"] == "觀光餐旅類指數")
    assert null_csv_row["漲跌"] is None
    assert null_csv_row["漲跌點數"] is None
    assert null_csv_row["漲跌百分比"] is None

    with sqlite3.connect(config.db_file) as connection:
        null_sqlite_row = connection.execute(
            '''SELECT "收盤指數", "漲跌", "漲跌點數", "漲跌百分比"
               FROM industry_indices
               WHERE "日期" = ? AND "指數名稱" = ?''',
            ("20260903", "觀光餐旅類指數"),
        ).fetchone()
    assert null_sqlite_row == (100.95, None, None, None)

    marker_path = Path(result["projection_commit_marker"])
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    assert marker["rowset_sha256"] == marker["sqlite_rowset_sha256"]
    assert marker["rowset_sha256"] == rowset_sha256(rows)
    assert canonical_rowset(csv_rows) == canonical_rowset(rows)


def test_failed_final_marker_restores_csv_and_entire_qa_database(tmp_path, monkeypatch):
    import data_module.twse_industry_index_capture as capture_module

    config = _config(tmp_path)
    capture = _make_capture(config)
    service = _service_with_prior_industry_row(config)
    database_before = _database_snapshot(config.db_file)
    csv_before, after_sha = _prepare_csv(config, existing_target=True)
    service._pending_industry_capture_manifests = [capture]
    service._pending_industry_csv_before = csv_before
    service._pending_industry_csv_after_sha256 = after_sha

    def fail_marker(**_kwargs):
        raise OSError("simulated final marker failure")

    monkeypatch.setattr(capture_module, "create_industry_projection_commit_manifest", fail_marker)
    result = service.sync_industry_index_captures_to_sqlite([capture])

    assert result["success"] is False
    assert result["partial"] is False
    assert config.industry_index_file.read_bytes() == csv_before
    assert _database_snapshot(config.db_file) == database_before
    assert not list((config.output_root / "industry_capture" / "twse" / "projection_commits").rglob("*.json"))


@pytest.mark.parametrize("concurrent_change", ["raw_bytes", "date_rowset"])
def test_csv_concurrent_rewrite_after_sqlite_commit_never_writes_marker(
    tmp_path, monkeypatch, concurrent_change,
):
    import data_module.twse_industry_index_capture as capture_module

    config = _config(tmp_path)
    capture = _make_capture(config)
    service = _service_with_prior_industry_row(config)
    database_before = _database_snapshot(config.db_file)
    before_csv, after_sha = _prepare_csv(config, existing_target=True)
    service._pending_industry_capture_manifests = [capture]
    service._pending_industry_csv_before = before_csv
    service._pending_industry_csv_after_sha256 = after_sha

    verify_csv = capture_module.verify_csv_date_projection
    calls = 0
    external_csv_bytes = b""

    def rewrite_after_sqlite_commit(path, captures):
        nonlocal calls, external_csv_bytes
        calls += 1
        if calls == 2:
            if concurrent_change == "raw_bytes":
                Path(path).write_bytes(Path(path).read_bytes() + b"\n")
            else:
                frame = pd.read_csv(
                    path, encoding="utf-8-sig", dtype=str, keep_default_na=False,
                )
                target = frame["日期"] == "2026-09-03"
                frame.loc[target, "收盤指數"] = "999.25"
                frame.to_csv(path, index=False, encoding="utf-8-sig")
            external_csv_bytes = Path(path).read_bytes()
        return verify_csv(path, captures)

    monkeypatch.setattr(capture_module, "verify_csv_date_projection", rewrite_after_sqlite_commit)
    result = service.sync_industry_index_captures_to_sqlite([capture])

    assert calls == 2
    assert result["success"] is False
    assert result["partial"] is True
    assert "projection_commit_marker" not in result
    assert Path(config.industry_index_file).read_bytes() == external_csv_bytes
    assert _database_snapshot(config.db_file) == database_before
    assert not list(
        (config.output_root / "industry_capture" / "twse" / "projection_commits")
        .rglob("*.json")
    )


def test_capture_receipt_hashes_raw_bytes_and_keeps_official_time_unknown(tmp_path):
    config = _config(tmp_path)
    manifest = _make_capture(config)
    receipt = verify_capture_receipt(manifest, config.output_root)
    raw_path = manifest.parent.parent / receipt["raw_response_file"]

    assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == receipt["raw_response_sha256"]
    assert receipt["available_at"] is None
    assert receipt["published_at"] is None
    assert receipt["historical_pit_eligible"] is False


def test_capture_receipt_rejects_raw_path_escape_even_with_rehashed_receipt(tmp_path):
    config = _config(tmp_path)
    manifest = _make_capture(config)
    path = Path(manifest)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["raw_response_file"] = "../outside.bin"
    body = {key: value for key, value in payload.items() if key != "content_sha256"}
    canonical = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    payload["content_sha256"] = hashlib.sha256(canonical).hexdigest()
    receipt_bytes = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    escaped_manifest = path.with_name(
        f"{hashlib.sha256(receipt_bytes).hexdigest()[:20]}.json"
    )
    path.unlink()
    escaped_manifest.write_bytes(receipt_bytes)

    with pytest.raises(TwseIndustryIndexCaptureError, match="固定契約"):
        verify_capture_receipt(escaped_manifest, config.output_root)


def test_update_industry_failure_blocks_legacy_sync_and_keeps_partial_status(tmp_path, monkeypatch):
    import importlib.util

    config = _config(tmp_path)
    capture = _make_capture(config)
    service = UpdateService(config)
    service.scripts_dir = tmp_path / "scripts"
    service.scripts_dir.mkdir()
    (service.scripts_dir / "batch_update_market_and_industry_index.py").write_text(
        "# fake batch entrypoint\n", encoding="utf-8",
    )

    class FakeLoader:
        def create_module(self, _spec):
            return None

        def exec_module(self, module):
            def fake_batch_update(
                *, start_date, end_date, config, capture_manifests, batch_outcome,
            ):
                capture_manifests.append(capture)
                batch_outcome.update({
                    "success": False,
                    "updated_dates": [start_date],
                    "failed_dates": [end_date],
                })
                return False

            module.batch_update_industry_index = fake_batch_update

    monkeypatch.setattr(
        importlib.util,
        "spec_from_file_location",
        lambda name, _path: importlib.util.spec_from_loader(name, FakeLoader()),
    )
    update_result = service.update_industry("2026-09-03", "2026-09-04")

    assert update_result["success"] is False
    assert update_result["partial"] is True
    assert update_result["updated_dates"] == ["2026-09-03"]
    assert update_result["failed_dates"] == ["2026-09-04"]
    assert service._industry_update_block_legacy_sync is True
    assert service._pending_industry_capture_manifests == [capture]

    def forbid_legacy_csv_load(*_args, **_kwargs):
        pytest.fail("industry capture failure must not fall through to whole-CSV sync")

    monkeypatch.setattr(service, "_load_csv_for_sqlite", forbid_legacy_csv_load)
    sync_result = service.sync_source_to_sqlite("industry_index")

    assert sync_result["success"] is False
    assert service._industry_update_block_legacy_sync is True


def test_batch_update_reports_partial_dates_with_fake_loader(tmp_path, monkeypatch):
    from scripts import batch_update_market_and_industry_index as batch_module

    config = _config(tmp_path)
    manifest_path = tmp_path / "fake-capture.json"
    monkeypatch.setattr(
        batch_module, "get_trading_days",
        lambda *_args, **_kwargs: ["2026-09-03", "2026-09-04"],
    )
    monkeypatch.setattr(batch_module, "get_existing_dates", lambda _path: set())
    monkeypatch.setattr(batch_module.time, "sleep", lambda _seconds: None)

    class FakeLoader:
        def __init__(self, _config):
            pass

        def update_industry_index(self, date, *, skip_backup, capture_manifests):
            if date == "2026-09-03":
                capture_manifests.append(manifest_path)
                return True
            return False

    monkeypatch.setattr(batch_module, "DataLoader", FakeLoader)
    captures = []
    outcome = {"stale": "must be cleared"}
    success = batch_module.batch_update_industry_index(
        "2026-09-03",
        "2026-09-04",
        delay_min=0,
        delay_max=0,
        config=config,
        capture_manifests=captures,
        batch_outcome=outcome,
    )

    assert success is False
    assert outcome["success"] is False
    assert outcome["updated_dates"] == ["2026-09-03"]
    assert outcome["failed_dates"] == ["2026-09-04"]
    assert outcome["capture_manifests"] == [str(manifest_path)]
    assert "stale" not in outcome


def test_batch_only_skips_dates_with_verified_current_projection_marker(tmp_path, monkeypatch):
    from scripts import batch_update_market_and_industry_index as batch_module

    config = _config(tmp_path)
    capture = _make_capture(config)
    service = _service_with_prior_industry_row(config)
    before_csv, after_sha = _prepare_csv(config, existing_target=True)
    service._pending_industry_csv_before = before_csv
    service._pending_industry_csv_after_sha256 = after_sha
    sync_result = service.sync_industry_index_captures_to_sqlite([capture])
    assert sync_result["success"] is True
    assert verified_industry_projection_dates(
        output_root=config.output_root,
        csv_path=config.industry_index_file,
        database_path=config.db_file,
        candidate_dates=["2026-09-03"],
    ) == {"2026-09-03"}

    monkeypatch.setattr(
        batch_module, "get_trading_days",
        lambda *_args, **_kwargs: ["2026-09-03"],
    )
    monkeypatch.setattr(
        batch_module, "get_existing_dates", lambda _path: {"2026-09-03"},
    )

    class NeverCalledLoader:
        def __init__(self, _config):
            pass

        def update_industry_index(self, *_args, **_kwargs):
            pytest.fail("verified current projection marker should allow this date to skip")

    monkeypatch.setattr(batch_module, "DataLoader", NeverCalledLoader)
    outcome = {}
    success = batch_module.batch_update_industry_index(
        "2026-09-03", "2026-09-03", config=config, batch_outcome=outcome,
    )

    assert success is True
    assert outcome["verified_skipped_dates"] == ["2026-09-03"]
    assert outcome["unverified_legacy_dates"] == []
    assert outcome["updated_dates"] == []

    with sqlite3.connect(config.db_file) as connection:
        connection.execute(
            'UPDATE industry_indices SET "收盤指數" = 999 WHERE "日期" = ? AND "指數名稱" = ?',
            ("20260903", "電子工業類指數"),
        )
    assert verified_industry_projection_dates(
        output_root=config.output_root,
        csv_path=config.industry_index_file,
        database_path=config.db_file,
        candidate_dates=["2026-09-03"],
    ) == set()


def test_projection_marker_stales_when_captured_csv_row_changes(tmp_path):
    config = _config(tmp_path)
    capture = _make_capture(config)
    service = _service_with_prior_industry_row(config)
    before_csv, after_sha = _prepare_csv(config, existing_target=True)
    service._pending_industry_csv_before = before_csv
    service._pending_industry_csv_after_sha256 = after_sha
    assert service.sync_industry_index_captures_to_sqlite([capture])["success"] is True
    assert verified_industry_projection_dates(
        output_root=config.output_root,
        csv_path=config.industry_index_file,
        database_path=config.db_file,
        candidate_dates=["2026-09-03"],
    ) == {"2026-09-03"}

    frame = pd.read_csv(config.industry_index_file, dtype=str, keep_default_na=False)
    frame.loc[
        (frame["日期"] == "2026-09-03") & (frame["指數名稱"] == "電子工業類指數"),
        "收盤指數",
    ] = "999.25"
    frame.to_csv(config.industry_index_file, index=False, encoding="utf-8-sig")

    assert verified_industry_projection_dates(
        output_root=config.output_root,
        csv_path=config.industry_index_file,
        database_path=config.db_file,
        candidate_dates=["2026-09-03"],
    ) == set()


def test_batch_keeps_precontract_legacy_date_unknown_without_refetch(tmp_path, monkeypatch):
    from scripts import batch_update_market_and_industry_index as batch_module

    config = _config(tmp_path)
    pd.DataFrame([{
        "指數名稱": "電子工業類指數", "收盤指數": "90", "漲跌": "+",
        "漲跌點數": "1", "漲跌百分比": "1", "日期": "2026-09-03",
    }], columns=CSV_COLUMNS).to_csv(
        config.industry_index_file, index=False, encoding="utf-8-sig",
    )
    monkeypatch.setattr(
        batch_module, "get_trading_days",
        lambda *_args, **_kwargs: ["2026-09-03"],
    )
    monkeypatch.setattr(
        batch_module, "get_existing_dates", lambda _path: {"2026-09-03"},
    )

    class NeverCalledLoader:
        def __init__(self, _config):
            pass

        def update_industry_index(self, *_args, **_kwargs):
            pytest.fail("unverified legacy date should remain an unknown skip")

    monkeypatch.setattr(batch_module, "DataLoader", NeverCalledLoader)
    outcome = {}
    success = batch_module.batch_update_industry_index(
        "2026-09-03", "2026-09-03", config=config, batch_outcome=outcome,
    )

    assert success is False
    assert outcome["source_status"] == "unknown_legacy_rows_skipped"
    assert outcome["unverified_legacy_dates"] == ["2026-09-03"]
    assert outcome["verified_skipped_dates"] == []
    assert outcome["updated_dates"] == []
    assert outcome["success"] is False


def test_batch_reverifies_only_unknown_requested_dates_when_enabled(tmp_path, monkeypatch):
    from scripts import batch_update_market_and_industry_index as batch_module
    from data_module import twse_industry_index_capture as capture_module

    config = _config(tmp_path)
    requested = ["2026-09-03", "2026-09-04", "2026-09-05"]
    monkeypatch.setattr(batch_module, "get_trading_days", lambda *_args, **_kwargs: requested)
    monkeypatch.setattr(
        batch_module,
        "get_existing_dates",
        lambda _path: {"2026-09-03", "2026-09-04", "2014-01-02"},
    )

    def verified_dates(*, candidate_dates, **_kwargs):
        assert candidate_dates == ["2026-09-03", "2026-09-04"]
        return {"2026-09-03"}

    def attempted_dates(*, candidate_dates, **_kwargs):
        assert candidate_dates == ["2026-09-04"]
        return set()

    monkeypatch.setattr(capture_module, "verified_industry_projection_dates", verified_dates)
    monkeypatch.setattr(capture_module, "industry_capture_artifact_dates", attempted_dates)
    monkeypatch.setattr(batch_module.time, "sleep", lambda _seconds: None)

    calls: list[str] = []
    captures: list[Path] = []

    class FakeLoader:
        def __init__(self, _config):
            pass

        def update_industry_index(self, source_date, *, skip_backup, capture_manifests):
            calls.append(source_date)
            assert skip_backup is True
            capture_manifests.append(tmp_path / f"{source_date}.capture.json")
            return True

    monkeypatch.setattr(batch_module, "DataLoader", FakeLoader)
    outcome = {}
    assert batch_module.batch_update_industry_index(
        "2026-09-03",
        "2026-09-05",
        delay_min=0,
        delay_max=0,
        config=config,
        capture_manifests=captures,
        batch_outcome=outcome,
        reverify_unknown_legacy_dates=True,
    ) is True

    assert calls == ["2026-09-04", "2026-09-05"]
    assert outcome["updated_dates"] == calls
    assert outcome["verified_skipped_dates"] == ["2026-09-03"]
    assert outcome["pending_projection_dates"] == ["2026-09-04"]
    assert outcome["unverified_legacy_dates"] == []
    assert outcome["source_status"] == "legacy_capture_accepted_pending_projection"
    assert "2014-01-02" not in outcome["updated_dates"]


def test_batch_reverification_keeps_failed_legacy_date_unknown(tmp_path, monkeypatch):
    from scripts import batch_update_market_and_industry_index as batch_module
    from data_module import twse_industry_index_capture as capture_module

    config = _config(tmp_path)
    day = "2026-09-03"
    monkeypatch.setattr(batch_module, "get_trading_days", lambda *_args, **_kwargs: [day])
    monkeypatch.setattr(batch_module, "get_existing_dates", lambda _path: {day})
    monkeypatch.setattr(
        capture_module,
        "verified_industry_projection_dates",
        lambda **_kwargs: set(),
    )
    monkeypatch.setattr(
        capture_module,
        "industry_capture_artifact_dates",
        lambda **_kwargs: set(),
    )

    class FailingLoader:
        def __init__(self, _config):
            pass

        def update_industry_index(self, *_args, **_kwargs):
            return False

    monkeypatch.setattr(batch_module, "DataLoader", FailingLoader)
    captures: list[Path] = []
    outcome = {}
    assert batch_module.batch_update_industry_index(
        day,
        day,
        config=config,
        capture_manifests=captures,
        batch_outcome=outcome,
        reverify_unknown_legacy_dates=True,
    ) is False
    assert captures == []
    assert outcome["failed_dates"] == [day]
    assert outcome["unverified_legacy_dates"] == [day]
    assert outcome["pending_projection_dates"] == []


def test_batch_ignores_unknown_legacy_dates_outside_requested_window(
    tmp_path, monkeypatch,
):
    from scripts import batch_update_market_and_industry_index as batch_module
    from data_module import twse_industry_index_capture as capture_module

    config = _config(tmp_path)
    current_day = "2026-09-29"
    historical_day = "2014-01-02"
    monkeypatch.setattr(batch_module, "get_trading_days", lambda *_args, **_kwargs: [current_day])
    monkeypatch.setattr(
        batch_module, "get_existing_dates", lambda _path: {historical_day, current_day},
    )

    def verified_dates(*, candidate_dates, **_kwargs):
        assert candidate_dates == [current_day]
        return {current_day}

    monkeypatch.setattr(capture_module, "verified_industry_projection_dates", verified_dates)

    def no_capture_attempts(*, candidate_dates, **_kwargs):
        assert candidate_dates == []
        return set()

    monkeypatch.setattr(capture_module, "industry_capture_artifact_dates", no_capture_attempts)

    class NeverCalledLoader:
        def __init__(self, _config):
            pass

        def update_industry_index(self, *_args, **_kwargs):
            pytest.fail("verified requested date must not be refetched")

    monkeypatch.setattr(batch_module, "DataLoader", NeverCalledLoader)
    outcome = {}
    assert batch_module.batch_update_industry_index(
        current_day, current_day, config=config, batch_outcome=outcome,
    ) is True
    assert outcome["source_status"] == "verified_projection_noop"
    assert outcome["verified_skipped_dates"] == [current_day]
    assert outcome["unverified_legacy_dates"] == []


def test_legacy_only_batch_fails_through_update_service_and_scheduled_step(tmp_path, monkeypatch):
    import importlib.util

    from scripts import batch_update_market_and_industry_index as batch_module
    from scripts.scheduled import run_daily_data_update_quick as scheduled_module

    config = _config(tmp_path)
    pd.DataFrame([{
        "指數名稱": "電子工業類指數", "收盤指數": "90", "漲跌": "+",
        "漲跌點數": "1", "漲跌百分比": "1", "日期": "2026-09-03",
    }], columns=CSV_COLUMNS).to_csv(
        config.industry_index_file, index=False, encoding="utf-8-sig",
    )
    monkeypatch.setattr(
        batch_module, "get_trading_days",
        lambda *_args, **_kwargs: ["2026-09-03"],
    )
    monkeypatch.setattr(
        batch_module, "get_existing_dates", lambda _path: {"2026-09-03"},
    )

    class NeverCalledLoader:
        def __init__(self, _config):
            pass

        def update_industry_index(self, *_args, **_kwargs):
            pytest.fail("legacy-only row must not be reported as freshly updated")

    monkeypatch.setattr(batch_module, "DataLoader", NeverCalledLoader)
    service = UpdateService(config)
    service.scripts_dir = tmp_path / "service_scripts"
    service.scripts_dir.mkdir()
    (service.scripts_dir / "batch_update_market_and_industry_index.py").write_text(
        "# intercepted fake import\n", encoding="utf-8",
    )

    class FakeBatchLoader:
        def create_module(self, _spec):
            return None

        def exec_module(self, module):
            def run_batch(*, start_date, end_date, config, capture_manifests, batch_outcome):
                return batch_module.batch_update_industry_index(
                    start_date,
                    end_date,
                    config=config,
                    capture_manifests=capture_manifests,
                    batch_outcome=batch_outcome,
                )

            module.batch_update_industry_index = run_batch

    monkeypatch.setattr(
        importlib.util,
        "spec_from_file_location",
        lambda name, _path: importlib.util.spec_from_loader(name, FakeBatchLoader()),
    )
    steps = []
    terminal = scheduled_module._run_step(
        steps=steps,
        name="update_industry_index",
        action=lambda: service.update_industry("2026-09-03", "2026-09-03"),
    )

    assert terminal is not None
    assert terminal["success"] is False
    assert terminal["source_status"] == "unknown_legacy_rows_skipped"
    assert terminal["updated_dates"] == []
    assert steps[0]["status"] == "failed"
    assert steps[0]["result"]["source_status"] == "unknown_legacy_rows_skipped"
    assert service._industry_update_succeeded_without_capture is False

    def forbid_legacy_csv_sync(*_args, **_kwargs):
        pytest.fail("legacy-only update must never sync the old whole CSV")

    monkeypatch.setattr(service, "_load_csv_for_sqlite", forbid_legacy_csv_sync)
    sync_result = service.sync_source_to_sqlite("industry_index")
    assert sync_result["success"] is False
    assert sync_result["skipped"] is False


def test_update_service_fails_closed_when_batch_lacks_named_reverify_option(
    tmp_path, monkeypatch,
):
    import importlib.util

    config = _config(tmp_path)
    service = UpdateService(config)
    service.scripts_dir = tmp_path / "service_scripts"
    service.scripts_dir.mkdir()
    (service.scripts_dir / "batch_update_market_and_industry_index.py").write_text(
        "# intercepted legacy batch updater\n", encoding="utf-8",
    )
    observed = {"called": False}

    class LegacyBatchLoader:
        def create_module(self, _spec):
            return None

        def exec_module(self, module):
            def old_batch(*, start_date, end_date, config, capture_manifests, batch_outcome):
                observed["called"] = True
                return True

            module.batch_update_industry_index = old_batch

    monkeypatch.setattr(
        importlib.util,
        "spec_from_file_location",
        lambda name, _path: importlib.util.spec_from_loader(name, LegacyBatchLoader()),
    )

    result = service.update_industry(
        "2026-09-03",
        "2026-09-03",
        reverify_unknown_legacy_dates=True,
    )

    assert result["success"] is False
    assert result["source_status"] == "legacy_reverification_contract_unsupported"
    assert "未明確支援" in result["message"]
    assert observed["called"] is False
    assert service._industry_update_block_legacy_sync is True


def test_update_service_passes_explicit_reverification_to_named_batch_option(
    tmp_path, monkeypatch,
):
    import importlib.util

    config = _config(tmp_path)
    service = UpdateService(config)
    service.scripts_dir = tmp_path / "service_scripts"
    service.scripts_dir.mkdir()
    (service.scripts_dir / "batch_update_market_and_industry_index.py").write_text(
        "# intercepted re-verification batch updater\n", encoding="utf-8",
    )
    observed: dict[str, object] = {}
    manifest = tmp_path / "accepted-capture.json"

    class ReverificationBatchLoader:
        def create_module(self, _spec):
            return None

        def exec_module(self, module):
            def run_batch(
                *,
                start_date,
                end_date,
                config,
                capture_manifests,
                batch_outcome,
                reverify_unknown_legacy_dates=False,
            ):
                observed["reverify_unknown_legacy_dates"] = reverify_unknown_legacy_dates
                capture_manifests.append(manifest)
                batch_outcome.update({
                    "success": True,
                    "updated_dates": [start_date],
                    "recovered_dates": [],
                    "failed_dates": [],
                    "verified_skipped_dates": [],
                    "unverified_legacy_dates": [],
                    "pending_projection_dates": [start_date],
                    "source_status": "legacy_capture_accepted_pending_projection",
                })
                return True

            module.batch_update_industry_index = run_batch

    monkeypatch.setattr(
        importlib.util,
        "spec_from_file_location",
        lambda name, _path: importlib.util.spec_from_loader(
            name, ReverificationBatchLoader(),
        ),
    )

    result = service.update_industry(
        "2026-09-03",
        "2026-09-03",
        reverify_unknown_legacy_dates=True,
    )

    assert observed["reverify_unknown_legacy_dates"] is True
    assert result["success"] is True
    assert result["pending_projection_dates"] == ["2026-09-03"]
    assert result["projection_status"] == "pending_csv_sqlite_readback"
    assert result["capture_manifests"] == [str(manifest)]


def test_update_service_does_not_treat_generic_kwargs_as_reverification_support(
    tmp_path, monkeypatch,
):
    import importlib.util

    config = _config(tmp_path)
    service = UpdateService(config)
    service.scripts_dir = tmp_path / "service_scripts"
    service.scripts_dir.mkdir()
    (service.scripts_dir / "batch_update_market_and_industry_index.py").write_text(
        "# intercepted permissive batch updater\n", encoding="utf-8",
    )
    observed = {"called": False, "kwargs": None}

    class PermissiveBatchLoader:
        def create_module(self, _spec):
            return None

        def exec_module(self, module):
            def old_batch(
                *, start_date, end_date, config, capture_manifests, batch_outcome,
                **kwargs,
            ):
                observed["called"] = True
                observed["kwargs"] = kwargs
                return True

            module.batch_update_industry_index = old_batch

    monkeypatch.setattr(
        importlib.util,
        "spec_from_file_location",
        lambda name, _path: importlib.util.spec_from_loader(
            name, PermissiveBatchLoader(),
        ),
    )

    result = service.update_industry(
        "2026-09-03",
        "2026-09-03",
        reverify_unknown_legacy_dates=True,
    )

    assert result["success"] is False
    assert result["source_status"] == "legacy_reverification_contract_unsupported"
    assert observed == {"called": False, "kwargs": None}


def test_optin_legacy_reverification_commits_real_capture_and_same_day_rerun_is_noop(
    tmp_path, monkeypatch,
):
    import importlib.util
    from types import SimpleNamespace

    from scripts import batch_update_market_and_industry_index as batch_module
    from data_module.twse_industry_index_capture import verify_capture_receipt

    config = _config(tmp_path)
    service = _service_with_prior_industry_row(config)
    _prepare_csv(config, existing_target=True)
    source_date = "2026-09-03"
    payload = _payload()
    response_body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    requests = {"count": 0}

    def official_response(_loader, _url, _parameters):
        requests["count"] += 1
        return SimpleNamespace(
            content=response_body,
            status_code=200,
            url=(
                "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
                "?date=20260903&type=IND&response=json"
            ),
            headers={"content-type": "application/json"},
        )

    monkeypatch.setattr(DataLoader, "_make_request", official_response)
    monkeypatch.setattr(
        batch_module,
        "get_trading_days",
        lambda *_args, **_kwargs: [source_date],
    )
    monkeypatch.setattr(batch_module.time, "sleep", lambda _seconds: None)

    class ExistingBatchLoader:
        def create_module(self, _spec):
            return None

        def exec_module(self, module):
            module.batch_update_industry_index = batch_module.batch_update_industry_index

    monkeypatch.setattr(
        importlib.util,
        "spec_from_file_location",
        lambda name, _path: importlib.util.spec_from_loader(
            name, ExistingBatchLoader(),
        ),
    )

    first = service.update_industry(
        source_date,
        source_date,
        reverify_unknown_legacy_dates=True,
    )

    assert first["success"] is True
    assert first["pending_projection_dates"] == [source_date]
    assert first["projection_status"] == "pending_csv_sqlite_readback"
    assert len(first["capture_manifests"]) == 1
    first_receipt = verify_capture_receipt(
        first["capture_manifests"][0], config.output_root,
    )
    assert first_receipt["source_date"] == source_date
    assert first_receipt["available_at"] is None
    assert first_receipt["published_at"] is None
    assert first_receipt["historical_pit_eligible"] is False

    committed = service.sync_source_to_sqlite("industry_index")
    assert committed["success"] is True
    assert committed["projection_status"] == "committed_after_exact_csv_sqlite_readback"
    marker_path = Path(committed["projection_commit_marker"])
    assert marker_path.is_file()
    marker_payload = json.loads(marker_path.read_text(encoding="utf-8"))
    assert marker_payload["available_at"] is None
    assert marker_payload["published_at"] is None
    assert marker_payload["historical_pit_eligible"] is False
    assert verified_industry_projection_dates(
        output_root=config.output_root,
        csv_path=config.industry_index_file,
        database_path=config.db_file,
        candidate_dates=[source_date],
    ) == {source_date}

    second = service.update_industry(
        source_date,
        source_date,
        reverify_unknown_legacy_dates=True,
    )
    assert second["success"] is True
    assert second["source_status"] == "verified_projection_noop"
    assert second["verified_skipped_dates"] == [source_date]
    assert second["unverified_legacy_dates"] == []
    assert second["pending_projection_dates"] == []
    assert second["capture_manifests"] == []

    second_sync = service.sync_source_to_sqlite("industry_index")
    assert second_sync["success"] is True
    assert second_sync["skipped"] is True
    assert requests["count"] == 1


def test_batch_retries_existing_date_with_degraded_capture_artifact(tmp_path, monkeypatch):
    from scripts import batch_update_market_and_industry_index as batch_module

    config = _config(tmp_path)
    payload = _payload()
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    rows = parse_twse_industry_rows(payload, "2026-09-03")
    persist_twse_industry_capture(
        output_root=config.output_root,
        source_date="2026-09-03",
        requested_url="https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX",
        final_url="https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20260903&type=IND&response=json",
        request_parameters={"date": "20260903", "type": "IND", "response": "json"},
        http_status=200,
        response_headers={"content-type": "application/json"},
        raw_response=raw,
        captured_at=datetime(2026, 9, 3, 8, 0, tzinfo=timezone.utc),
        parse_status="accepted",
        parse_reason=None,
        response_date_status="verified",
        completeness_status="degraded",
        completeness_reason="industry_name_set_changed_manual_review_required",
        selected_table_titles=["115年09月03日 類股指數"],
        rows=rows,
    )
    config.industry_index_file.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{
        "指數名稱": "電子工業類指數", "收盤指數": "90", "漲跌": "+",
        "漲跌點數": "1", "漲跌百分比": "1", "日期": "2026-09-03",
    }], columns=CSV_COLUMNS).to_csv(
        config.industry_index_file, index=False, encoding="utf-8-sig",
    )
    monkeypatch.setattr(
        batch_module, "get_trading_days",
        lambda *_args, **_kwargs: ["2026-09-03"],
    )
    monkeypatch.setattr(
        batch_module, "get_existing_dates", lambda _path: {"2026-09-03"},
    )
    called_dates = []

    class RetryLoader:
        def __init__(self, _config):
            pass

        def update_industry_index(self, date, *, skip_backup, capture_manifests):
            called_dates.append(date)
            return False

    monkeypatch.setattr(batch_module, "DataLoader", RetryLoader)
    monkeypatch.setattr(batch_module.time, "sleep", lambda _seconds: None)
    outcome = {}
    success = batch_module.batch_update_industry_index(
        "2026-09-03", "2026-09-03", delay_min=0, delay_max=0,
        config=config, batch_outcome=outcome,
    )

    assert success is False
    assert called_dates == ["2026-09-03"]
    assert outcome["failed_dates"] == ["2026-09-03"]
    assert outcome["unverified_legacy_dates"] == []

    retry_outcome = {}
    second_success = batch_module.batch_update_industry_index(
        "2026-09-03", "2026-09-03", delay_min=0, delay_max=0,
        config=config, batch_outcome=retry_outcome,
    )
    assert second_success is False
    assert called_dates == ["2026-09-03", "2026-09-03"]
    assert retry_outcome["failed_dates"] == ["2026-09-03"]


def test_capture_writer_rejects_symlink_parent_escape(tmp_path):
    output_root = tmp_path / "output"
    output_root.mkdir()
    external_dir = tmp_path / "external"
    external_dir.mkdir()
    try:
        (output_root / "industry_capture").symlink_to(external_dir, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"this Windows environment cannot create a directory symlink: {exc}")

    with pytest.raises(TwseIndustryIndexCaptureError, match="symlink/junction"):
        _make_capture(_config(tmp_path))

    assert list(external_dir.rglob("*")) == []


def test_capture_receipt_verifier_rejects_reparse_point_parent(tmp_path, monkeypatch):
    import data_module.twse_industry_index_capture as capture_module

    config = _config(tmp_path)
    manifest = _make_capture(config)
    date_directory = Path(manifest).parents[2]
    monkeypatch.setattr(
        capture_module,
        "_is_reparse_point",
        lambda candidate: candidate == date_directory,
    )

    with pytest.raises(TwseIndustryIndexCaptureError, match="symlink/junction"):
        verify_capture_receipt(manifest, config.output_root)


def test_batch_closed_day_remains_successful_noop(tmp_path, monkeypatch):
    from scripts import batch_update_market_and_industry_index as batch_module

    config = _config(tmp_path)
    monkeypatch.setattr(batch_module, "get_trading_days", lambda *_args, **_kwargs: [])

    class NeverCalledLoader:
        def __init__(self, _config):
            pass

        def update_industry_index(self, *_args, **_kwargs):
            pytest.fail("official non-trading day must remain a no-op")

    monkeypatch.setattr(batch_module, "DataLoader", NeverCalledLoader)
    outcome = {}
    success = batch_module.batch_update_industry_index(
        "2026-09-06", "2026-09-06", config=config, batch_outcome=outcome,
    )

    assert success is True
    assert outcome["source_status"] == "no_official_trading_days"
    assert outcome["updated_dates"] == []


def test_capture_recovery_requires_exact_single_receipt_and_current_date_rowset(tmp_path):
    config = _config(tmp_path)
    manifest = _make_capture(config)
    _prepare_csv(config, existing_target=True)

    recovered = recover_industry_capture_receipts_for_csv(
        output_root=config.output_root,
        csv_path=config.industry_index_file,
        candidate_dates=["2026-09-03"],
    )

    assert list(recovered) == ["2026-09-03"]
    assert Path(recovered["2026-09-03"]["path"]) == manifest

    frame = pd.read_csv(config.industry_index_file, dtype=str, keep_default_na=False)
    frame.loc[frame["日期"] == "2026-09-03", "收盤指數"] = "999.25"
    frame.to_csv(config.industry_index_file, index=False, encoding="utf-8-sig")
    assert recover_industry_capture_receipts_for_csv(
        output_root=config.output_root,
        csv_path=config.industry_index_file,
        candidate_dates=["2026-09-03"],
    ) == {}


def test_capture_recovery_rejects_tampered_receipt(tmp_path):
    config = _config(tmp_path)
    manifest = _make_capture(config)
    _prepare_csv(config, existing_target=True)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["rows"][0][1] = "999.25"
    body = {key: value for key, value in payload.items() if key != "content_sha256"}
    canonical = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    payload["content_sha256"] = hashlib.sha256(canonical).hexdigest()
    manifest.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

    with pytest.raises(TwseIndustryIndexCaptureError, match="identity hash"):
        recover_industry_capture_receipts_for_csv(
            output_root=config.output_root,
            csv_path=config.industry_index_file,
            candidate_dates=["2026-09-03"],
        )


def test_capture_recovery_rejects_reparse_parent_and_bounded_range_overflow(
    tmp_path, monkeypatch,
):
    import data_module.twse_industry_index_capture as capture_module

    config = _config(tmp_path)
    manifest = _make_capture(config)
    _prepare_csv(config, existing_target=True)
    date_directory = manifest.parents[2]
    is_reparse_point = capture_module._is_reparse_point
    monkeypatch.setattr(
        capture_module,
        "_is_reparse_point",
        lambda candidate: candidate == date_directory or is_reparse_point(candidate),
    )

    with pytest.raises(TwseIndustryIndexCaptureError, match="symlink/junction"):
        recover_industry_capture_receipts_for_csv(
            output_root=config.output_root,
            csv_path=config.industry_index_file,
            candidate_dates=["2026-09-03"],
        )

    monkeypatch.setattr(capture_module, "_is_reparse_point", is_reparse_point)
    monkeypatch.setattr(capture_module, "MAX_CAPTURE_RECOVERY_DATES", 1)
    with pytest.raises(TwseIndustryIndexCaptureError, match="bounded scan limit"):
        recover_industry_capture_receipts_for_csv(
            output_root=config.output_root,
            csv_path=config.industry_index_file,
            candidate_dates=["2026-09-03", "2026-09-04"],
        )

    monkeypatch.setattr(capture_module, "MAX_CAPTURE_RECOVERY_DATES", 64)
    monkeypatch.setattr(capture_module, "MAX_CAPTURE_RECOVERY_RAW_DIRS_PER_DATE", 0)
    with pytest.raises(TwseIndustryIndexCaptureError, match="bounded scan limit"):
        recover_industry_capture_receipts_for_csv(
            output_root=config.output_root,
            csv_path=config.industry_index_file,
            candidate_dates=["2026-09-03"],
        )


def test_capture_recovery_fails_closed_on_multiple_same_day_receipts(tmp_path):
    config = _config(tmp_path)
    _make_capture(config)
    _prepare_csv(config, existing_target=True)
    payload = _payload()
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    rows = parse_twse_industry_rows(payload, "2026-09-03")
    second = persist_twse_industry_capture(
        output_root=config.output_root,
        source_date="2026-09-03",
        requested_url="https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX",
        final_url="https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20260903&type=IND&response=json",
        request_parameters={"date": "20260903", "type": "IND", "response": "json"},
        http_status=200,
        response_headers={"content-type": "application/json"},
        raw_response=raw,
        captured_at=datetime(2026, 9, 3, 9, 0, tzinfo=timezone.utc),
        parse_status="accepted",
        parse_reason=None,
        response_date_status="verified",
        completeness_status="accepted",
        completeness_reason=None,
        selected_table_titles=["115年09月03日 類股指數"],
        rows=rows,
    )
    assert second["rowset_sha256"] == verify_capture_receipt(
        next((config.output_root / "industry_capture" / "twse" / "2026-09-03").glob("*/*/*.json")),
        config.output_root,
    )["rowset_sha256"]

    with pytest.raises(TwseIndustryIndexCaptureError, match="multiple capture receipts"):
        recover_industry_capture_receipts_for_csv(
            output_root=config.output_root,
            csv_path=config.industry_index_file,
            candidate_dates=["2026-09-03"],
        )


def test_projection_marker_uses_explicit_accepted_receipt_with_rejected_sibling(tmp_path):
    config = _config(tmp_path)
    accepted_manifest = _make_capture(config)
    rejected = persist_twse_industry_capture(
        output_root=config.output_root,
        source_date="2026-09-03",
        requested_url="https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX",
        final_url="https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20260903&type=IND&response=json",
        request_parameters={"date": "20260903", "type": "IND", "response": "json"},
        http_status=200,
        response_headers={"content-type": "application/json"},
        raw_response=b'{"stat":"not ready","date":"2026-09-03","tables":[]}',
        captured_at=datetime(2026, 9, 3, 7, 0, tzinfo=timezone.utc),
        parse_status="rejected",
        parse_reason="test rejected observation",
        response_date_status="unverified",
        completeness_status="rejected",
        completeness_reason="test rejected observation",
        selected_table_titles=[],
        rows=[],
    )
    assert rejected["parse_status"] == "rejected"

    service = _service_with_prior_industry_row(config)
    before_csv, after_sha = _prepare_csv(config, existing_target=True)
    service._pending_industry_csv_before = before_csv
    service._pending_industry_csv_after_sha256 = after_sha
    assert service.sync_industry_index_captures_to_sqlite([accepted_manifest])["success"] is True

    assert verified_industry_projection_dates(
        output_root=config.output_root,
        csv_path=config.industry_index_file,
        database_path=config.db_file,
        candidate_dates=["2026-09-03"],
    ) == {"2026-09-03"}
    with pytest.raises(TwseIndustryIndexCaptureError, match="multiple capture receipts"):
        recover_industry_capture_receipts_for_csv(
            output_root=config.output_root,
            csv_path=config.industry_index_file,
            candidate_dates=["2026-09-03"],
        )


def test_projection_marker_rejects_malformed_historical_csv_sha256(tmp_path):
    config = _config(tmp_path)
    capture = _make_capture(config)
    service = _service_with_prior_industry_row(config)
    before_csv, after_sha = _prepare_csv(config, existing_target=True)
    service._pending_industry_csv_before = before_csv
    service._pending_industry_csv_after_sha256 = after_sha
    assert service.sync_industry_index_captures_to_sqlite([capture])["success"] is True
    marker = next(
        (config.output_root / "industry_capture" / "twse" / "projection_commits")
        .rglob("*.json")
    )
    payload = json.loads(marker.read_text(encoding="utf-8"))
    payload["csv_sha256"] = "not-a-sha256"
    body = {key: value for key, value in payload.items() if key != "content_sha256"}
    payload["content_sha256"] = hashlib.sha256(
        json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    marker.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

    assert verified_industry_projection_dates(
        output_root=config.output_root,
        csv_path=config.industry_index_file,
        database_path=config.db_file,
        candidate_dates=["2026-09-03"],
    ) == set()


def test_restart_recovers_csv_replace_manifest_gap_and_scoped_sqlite_projection(
    tmp_path, monkeypatch,
):
    import importlib.util

    from scripts import batch_update_market_and_industry_index as batch_module
    from scripts.scheduled import run_daily_data_update_quick as scheduled_module

    config = _config(tmp_path)
    _make_capture(config)
    service = _service_with_prior_industry_row(config)
    _prepare_csv(config, existing_target=True)
    rows = parse_twse_industry_rows(_payload(), "2026-09-03")
    with sqlite3.connect(config.db_file) as connection:
        connection.execute('DELETE FROM industry_indices WHERE "日期" = ?', ("20260903",))
        connection.executemany(
            'INSERT INTO industry_indices VALUES (?, ?, ?, ?, ?, ?)',
            [
                (
                    row["日期"].replace("-", ""), row["指數名稱"],
                    float(row["收盤指數"]), row["漲跌"],
                    float(row["漲跌點數"]), float(row["漲跌百分比"]),
                )
                for row in rows
            ],
        )
    assert verified_industry_projection_dates(
        output_root=config.output_root,
        csv_path=config.industry_index_file,
        database_path=config.db_file,
        candidate_dates=["2026-09-03"],
    ) == set()

    monkeypatch.setattr(
        batch_module, "get_trading_days",
        lambda *_args, **_kwargs: ["2026-09-03"],
    )
    monkeypatch.setattr(
        batch_module, "get_existing_dates", lambda _path: {"2026-09-03"},
    )
    monkeypatch.setattr(batch_module.time, "sleep", lambda _seconds: None)

    class NeverCalledLoader:
        def __init__(self, _config):
            pass

        def update_industry_index(self, *_args, **_kwargs):
            pytest.fail("matching persisted receipt should recover without a refetch")

    monkeypatch.setattr(batch_module, "DataLoader", NeverCalledLoader)
    service.scripts_dir = tmp_path / "service_scripts"
    service.scripts_dir.mkdir()
    (service.scripts_dir / "batch_update_market_and_industry_index.py").write_text(
        "# isolated batch entrypoint\n", encoding="utf-8",
    )

    class RealBatchLoader:
        def create_module(self, _spec):
            return None

        def exec_module(self, module):
            module.batch_update_industry_index = batch_module.batch_update_industry_index

    monkeypatch.setattr(
        importlib.util,
        "spec_from_file_location",
        lambda name, _path: importlib.util.spec_from_loader(name, RealBatchLoader()),
    )

    steps = []
    update_terminal = scheduled_module._run_step(
        steps=steps,
        name="update_industry_index",
        action=lambda: service.update_industry("2026-09-03", "2026-09-03"),
    )

    assert update_terminal is None
    update_result = steps[0]["result"]
    assert steps[0]["status"] == "passed"
    assert update_result["success"] is True
    assert update_result["source_status"] == "recovered_capture_projection"
    assert update_result["updated_dates"] == ["2026-09-03"]
    assert update_result["recovered_dates"] == ["2026-09-03"]
    assert len(update_result["capture_manifests"]) == 1

    sync_terminal = scheduled_module._run_step(
        steps=steps,
        name="sync_industry_index_to_sqlite",
        action=lambda: service.sync_source_to_sqlite("industry_index"),
    )

    assert sync_terminal is None
    assert steps[1]["status"] == "passed"
    marker_paths = list(
        (config.output_root / "industry_capture" / "twse" / "projection_commits")
        .rglob("*.json")
    )
    assert len(marker_paths) == 1
    assert verified_industry_projection_dates(
        output_root=config.output_root,
        csv_path=config.industry_index_file,
        database_path=config.db_file,
        candidate_dates=["2026-09-03"],
    ) == {"2026-09-03"}


def test_other_date_append_keeps_marker_scoped_to_its_capture_receipt(tmp_path, monkeypatch):
    from scripts import batch_update_market_and_industry_index as batch_module

    config = _config(tmp_path)
    manifest = _make_capture(config)
    service = _service_with_prior_industry_row(config)
    before_csv, after_sha = _prepare_csv(config, existing_target=True)
    service._pending_industry_csv_before = before_csv
    service._pending_industry_csv_after_sha256 = after_sha
    initial_sync = service.sync_industry_index_captures_to_sqlite([manifest])
    assert initial_sync["success"] is True
    assert verified_industry_projection_dates(
        output_root=config.output_root,
        csv_path=config.industry_index_file,
        database_path=config.db_file,
        candidate_dates=["2026-09-03"],
    ) == {"2026-09-03"}

    frame = pd.read_csv(config.industry_index_file, dtype=str, keep_default_na=False)
    frame = pd.concat(
        [
            frame,
            pd.DataFrame([{
                "指數名稱": "新日期測試類指數",
                "收盤指數": "101",
                "漲跌": "+",
                "漲跌點數": "1",
                "漲跌百分比": "0.5",
                "日期": "2026-09-04",
            }]),
        ],
        ignore_index=True,
    )
    frame.to_csv(config.industry_index_file, index=False, encoding="utf-8-sig")
    with sqlite3.connect(config.db_file) as connection:
        connection.execute(
            'INSERT INTO industry_indices VALUES (?, ?, ?, ?, ?, ?)',
            ("20260904", "新日期測試類指數", 101.0, "+", 1.0, 0.5),
        )
    assert verified_industry_projection_dates(
        output_root=config.output_root,
        csv_path=config.industry_index_file,
        database_path=config.db_file,
        candidate_dates=["2026-09-03", "2026-09-04"],
    ) == {"2026-09-03"}

    monkeypatch.setattr(
        batch_module, "get_trading_days",
        lambda *_args, **_kwargs: ["2026-09-03"],
    )
    monkeypatch.setattr(
        batch_module, "get_existing_dates", lambda _path: {"2026-09-03"},
    )

    class NeverCalledLoader:
        def __init__(self, _config):
            pass

        def update_industry_index(self, *_args, **_kwargs):
            pytest.fail("a verified captured date should skip without refetch")

    monkeypatch.setattr(batch_module, "DataLoader", NeverCalledLoader)
    captures = []
    outcome = {}
    success = batch_module.batch_update_industry_index(
        "2026-09-03", "2026-09-03", config=config,
        capture_manifests=captures, batch_outcome=outcome,
    )

    assert success is True
    assert outcome["verified_skipped_dates"] == ["2026-09-03"]
    assert outcome["recovered_dates"] == []
    assert captures == []


def test_missing_receipt_cannot_verify_marker_or_recover_date(tmp_path, monkeypatch):
    from scripts import batch_update_market_and_industry_index as batch_module

    config = _config(tmp_path)
    manifest = _make_capture(config)
    service = _service_with_prior_industry_row(config)
    before_csv, after_sha = _prepare_csv(config, existing_target=True)
    service._pending_industry_csv_before = before_csv
    service._pending_industry_csv_after_sha256 = after_sha
    assert service.sync_industry_index_captures_to_sqlite([manifest])["success"] is True
    manifest.unlink()

    assert verified_industry_projection_dates(
        output_root=config.output_root,
        csv_path=config.industry_index_file,
        database_path=config.db_file,
        candidate_dates=["2026-09-03"],
    ) == set()
    monkeypatch.setattr(
        batch_module, "get_trading_days",
        lambda *_args, **_kwargs: ["2026-09-03"],
    )
    monkeypatch.setattr(
        batch_module, "get_existing_dates", lambda _path: {"2026-09-03"},
    )
    calls = []

    class RetryLoader:
        def __init__(self, _config):
            pass

        def update_industry_index(self, source_date, *, skip_backup, capture_manifests):
            calls.append(source_date)
            return False

    monkeypatch.setattr(batch_module, "DataLoader", RetryLoader)
    captures = []
    outcome = {}
    success = batch_module.batch_update_industry_index(
        "2026-09-03", "2026-09-03", config=config,
        capture_manifests=captures, batch_outcome=outcome,
    )

    assert success is False
    assert calls == ["2026-09-03"]
    assert captures == []
    assert outcome["failed_dates"] == ["2026-09-03"]


def test_capture_receipt_and_csv_reads_have_explicit_byte_caps(tmp_path, monkeypatch):
    import data_module.twse_industry_index_capture as capture_module

    config = _config(tmp_path)
    manifest = _make_capture(config)
    _prepare_csv(config, existing_target=True)
    monkeypatch.setattr(capture_module, "MAX_CAPTURE_RECEIPT_BYTES", 1)
    with pytest.raises(TwseIndustryIndexCaptureError, match="receipt exceeds byte limit"):
        verify_capture_receipt(manifest, config.output_root)

    monkeypatch.setattr(capture_module, "MAX_CAPTURE_RECEIPT_BYTES", 32 * 1024 * 1024)
    monkeypatch.setattr(capture_module, "MAX_INDUSTRY_CSV_BYTES", 1)
    with pytest.raises(TwseIndustryIndexCaptureError, match="csv exceeds byte limit"):
        capture_module.verify_csv_date_projection(
            config.industry_index_file,
            [verify_capture_receipt(manifest, config.output_root)],
        )


def test_batch_retries_receipt_that_does_not_match_current_csv_rowset(tmp_path, monkeypatch):
    from scripts import batch_update_market_and_industry_index as batch_module

    config = _config(tmp_path)
    _make_capture(config)
    _prepare_csv(config, existing_target=True)
    frame = pd.read_csv(config.industry_index_file, dtype=str, keep_default_na=False)
    frame.loc[frame["日期"] == "2026-09-03", "收盤指數"] = "999.25"
    frame.to_csv(config.industry_index_file, index=False, encoding="utf-8-sig")
    monkeypatch.setattr(
        batch_module, "get_trading_days",
        lambda *_args, **_kwargs: ["2026-09-03"],
    )
    monkeypatch.setattr(
        batch_module, "get_existing_dates", lambda _path: {"2026-09-03"},
    )
    monkeypatch.setattr(batch_module.time, "sleep", lambda _seconds: None)
    calls = []

    class RetryLoader:
        def __init__(self, _config):
            pass

        def update_industry_index(self, source_date, *, skip_backup, capture_manifests):
            calls.append(source_date)
            return False

    monkeypatch.setattr(batch_module, "DataLoader", RetryLoader)
    captures = []
    outcome = {}
    success = batch_module.batch_update_industry_index(
        "2026-09-03", "2026-09-03", delay_min=0, delay_max=0,
        config=config, capture_manifests=captures, batch_outcome=outcome,
    )

    assert success is False
    assert calls == ["2026-09-03"]
    assert captures == []
    assert outcome["failed_dates"] == ["2026-09-03"]
    assert outcome["recovered_dates"] == []


@pytest.mark.parametrize("artifact_mode", ["tampered", "multiple"])
def test_batch_fails_closed_on_tampered_or_ambiguous_recovery_evidence(
    tmp_path, monkeypatch, artifact_mode,
):
    from scripts import batch_update_market_and_industry_index as batch_module

    config = _config(tmp_path)
    manifest = _make_capture(config)
    _prepare_csv(config, existing_target=True)
    if artifact_mode == "tampered":
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["rows"][0][1] = "999.25"
        body = {key: value for key, value in payload.items() if key != "content_sha256"}
        canonical = json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        payload["content_sha256"] = hashlib.sha256(canonical).hexdigest()
        manifest.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        payload = _payload()
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        rows = parse_twse_industry_rows(payload, "2026-09-03")
        persist_twse_industry_capture(
            output_root=config.output_root,
            source_date="2026-09-03",
            requested_url="https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX",
            final_url="https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20260903&type=IND&response=json",
            request_parameters={"date": "20260903", "type": "IND", "response": "json"},
            http_status=200,
            response_headers={"content-type": "application/json"},
            raw_response=raw,
            captured_at=datetime(2026, 9, 3, 9, 0, tzinfo=timezone.utc),
            parse_status="accepted",
            parse_reason=None,
            response_date_status="verified",
            completeness_status="accepted",
            completeness_reason=None,
            selected_table_titles=["115年09月03日 類股指數"],
            rows=rows,
        )
    monkeypatch.setattr(
        batch_module, "get_trading_days",
        lambda *_args, **_kwargs: ["2026-09-03"],
    )
    monkeypatch.setattr(
        batch_module, "get_existing_dates", lambda _path: {"2026-09-03"},
    )
    called = []

    class NeverCalledLoader:
        def __init__(self, _config):
            pass

        def update_industry_index(self, *_args, **_kwargs):
            called.append(True)
            return True

    monkeypatch.setattr(batch_module, "DataLoader", NeverCalledLoader)
    captures = []
    outcome = {}
    success = batch_module.batch_update_industry_index(
        "2026-09-03", "2026-09-03", config=config,
        capture_manifests=captures, batch_outcome=outcome,
    )

    assert success is False
    assert called == []
    assert captures == []
    assert outcome["failed_dates"] == ["2026-09-03"]
    assert outcome["recovered_dates"] == []
