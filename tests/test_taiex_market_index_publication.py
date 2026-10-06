"""TAIEX 專用前瞻發布列證據的合成契約測試。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from app_module.update_service import UpdateService
from data_module.config import TWStockConfig
from data_module.data_loader import DataLoader
from data_module.db_manager import DBManager
from data_module.official_market_daily import OfficialMarketDailyError
from data_module.official_trading_calendar import OfficialTradingCalendar
from data_module.taiex_market_index_publication import (
    _normal_date_key,
    read_taiex_market_index_evidence,
)
from scripts.scheduled import run_daily_data_update_quick as quick_runner


_REPORTS = ("FMTQIK", "MI_5MINS_HIST")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-05-28", "20260528"),
        ("2026/05/28", "20260528"),
        ("115/05/28", "20260528"),
        ("20260528.0", "20260528"),
    ],
)
def test_data_layer_date_normalization_preserves_legacy_market_forms(raw: str, expected: str) -> None:
    assert _normal_date_key(raw) == expected


def test_data_layer_date_normalization_rejects_impossible_dates() -> None:
    with pytest.raises(ValueError, match="日期格式無效"):
        _normal_date_key("2026-02-30")


def _payload(report: str, month: str = "202605", *, close: str = "20,000.50") -> dict[str, object]:
    if report == "FMTQIK":
        return {
            "stat": "OK",
            "date": month + "01",
            "fields": ["日期", "成交股數", "成交金額", "成交筆數", "發行量加權股價指數", "漲跌點數"],
            "data": [["115/05/28", "1,234", "5,000", "6", close, "-10.25"]],
        }
    return {
        "stat": "OK",
        "date": month + "01",
        "fields": ["日期", "開盤指數", "最高指數", "最低指數", "收盤指數"],
        "data": [["115/05/28", "19,990.00", "20,010.00", "19,900.00", close]],
    }


class _Response:
    def __init__(self, payload: dict[str, object], *, raw_payload: dict[str, object] | None = None) -> None:
        self._payload = payload
        self.content = json.dumps(
            raw_payload if raw_payload is not None else payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

    def json(self) -> dict[str, object]:
        return self._payload


def _config(tmp_path: Path, *, use_sqlite: bool = True) -> TWStockConfig:
    return TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        profile="test",
        use_sqlite=use_sqlite,
    )


def _loader(
    config: TWStockConfig,
    *,
    fmtqik: dict[str, object] | None = None,
    prices: dict[str, object] | None = None,
    mismatch_raw: bool = False,
) -> DataLoader:
    loader = DataLoader(config)
    payloads = {
        "FMTQIK": fmtqik or _payload("FMTQIK"),
        "MI_5MINS_HIST": prices or _payload("MI_5MINS_HIST"),
    }

    def request(url: str, _params: dict[str, str]):
        report = "FMTQIK" if url.endswith("/FMTQIK") else "MI_5MINS_HIST"
        payload = payloads[report]
        raw = _payload(report, close="20,000.49") if mismatch_raw and report == "FMTQIK" else payload
        return _Response(payload, raw_payload=raw)

    loader._make_request = request  # type: ignore[method-assign]
    return loader


def _read_rows(config: TWStockConfig) -> list[tuple[object, ...]]:
    connection = sqlite3.connect(config.db_file)
    try:
        return connection.execute(
            'SELECT "日期", "指數名稱", "收盤指數", "開盤價", "最高價", "最低價", "成交量" '
            'FROM market_indices ORDER BY "日期", "指數名稱"'
        ).fetchall()
    finally:
        connection.close()


def _read_evidence(config: TWStockConfig, result: dict[str, object], source_date: str):
    descriptor = result.get("row_evidence")
    return read_taiex_market_index_evidence(
        output_root=config.output_root,
        data_root=config.data_root,
        database_path=config.db_file,
        descriptor=descriptor if isinstance(descriptor, dict) else None,
        source_date=source_date,
    )


def test_explicit_capture_publishes_taiex_row_and_preserves_siblings_and_history(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    config.market_index_file.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"日期": "2026-05-27", "收盤價": Decimal("19800.25"), "開盤價": Decimal("19700.00"),
         "最高價": Decimal("19900.00"), "最低價": Decimal("19600.00"), "成交量": 900},
    ]).to_csv(config.market_index_file, index=False, encoding="utf-8-sig")
    db = DBManager(config)
    db.write_dataframe("market_indices", pd.DataFrame([
        {"日期": "20260528", "指數名稱": "半導體", "收盤指數": 1234.5},
        {"日期": "20260527", "指數名稱": "TAIEX", "收盤指數": 1.0},
    ]), if_exists="append")

    captures: list[Path] = []
    assert _loader(config).update_market_index("2026-05-28", capture_manifests=captures) is True
    assert len(captures) == 1
    assert captures[0].name == "manifest.json"
    assert captures[0].is_file()

    result = UpdateService(config).publish_taiex_market_index(
        capture_manifests=captures,
        market_update_result={"success": True},
    )

    assert result["success"] is True
    assert result["synced_records"] == 2  # 完整 CSV 的兩個 TAIEX 日期
    rows = _read_rows(config)
    assert rows == [
        ("20260527", "TAIEX", 19800.25, 19700.0, 19900.0, 19600.0, 900.0),
        ("20260528", "TAIEX", 20000.5, 19990.0, 20010.0, 19900.0, 1234.0),
        ("20260528", "半導體", 1234.5, None, None, None, None),
    ]

    attested = _read_evidence(config, result, "2026-05-28")
    assert attested.status == "attested"
    assert attested.row is not None
    assert attested.row.source_date == "20260528"
    assert attested.row.source_published_at is None
    assert attested.row.historical_pit is False
    assert datetime.fromisoformat(attested.row.first_observed_at).tzinfo is not None
    assert attested.row.volume == 1234
    assert attested.row.sqlite_storage_types["收盤指數"] == "real"
    historical = _read_evidence(config, result, "2026-05-27")
    assert historical.status == "unknown"
    assert historical.reason_code == "key_not_observed_in_capture"


def test_full_month_raw_reports_keep_later_days_out_of_requested_row(tmp_path: Path) -> None:
    config = _config(tmp_path)
    fmt = _payload("FMTQIK")
    prices = _payload("MI_5MINS_HIST")
    fmt["data"] = [
        *fmt["data"],
        ["115/05/29", "2,000", "8,000", "12", "20,100.50", "10.00"],
    ]
    prices["data"] = [
        *prices["data"],
        ["115/05/29", "20,050.00", "20,150.00", "20,000.00", "20,100.50"],
    ]
    captures: list[Path] = []

    assert _loader(config, fmtqik=fmt, prices=prices).update_market_index(
        "2026-05-28", capture_manifests=captures,
    ) is True
    manifest = json.loads(captures[0].read_text(encoding="utf-8"))
    raw_fmt = json.loads((captures[0].parent / "202605-FMTQIK.json").read_text(encoding="utf-8"))
    assert manifest["row_count"] == 1
    assert len(raw_fmt["data"]) == 2

    result = UpdateService(config).publish_taiex_market_index(
        capture_manifests=captures,
        market_update_result={"success": True},
    )
    assert result["row_evidence"]["status"] == "captured"
    assert [row[0] for row in _read_rows(config)] == ["20260528"]
    evidence = _read_evidence(config, result, "2026-05-28")
    assert evidence.status == "attested"
    assert evidence.row is not None and evidence.row.close == Decimal("20000.50")


def test_quick_runner_real_update_service_captures_and_publishes_taiex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    captures: list[Path] = []
    service = UpdateService(config)

    def _one_synthetic_trading_day(self, start_date, end_date, *, allow_online_probe=True):
        return [{
            "date": start_date,
            "date_str": start_date.isoformat(),
            "is_trading_day": True,
            "reason_code": "synthetic_test_day",
        }]

    def _synthetic_request(self, url, _params=None, _retries=None):
        report = "FMTQIK" if url.endswith("/FMTQIK") else "MI_5MINS_HIST"
        return _Response(_payload(report))

    def _no_calendar_io(self, *_args, **_kwargs):
        return None

    monkeypatch.setattr(OfficialTradingCalendar, "__init__", _no_calendar_io)
    monkeypatch.setattr(
        OfficialTradingCalendar,
        "require_trading_days_in_range",
        _one_synthetic_trading_day,
    )
    monkeypatch.setattr(DataLoader, "_make_request", _synthetic_request)
    updated = service.update_market(
        "2026-05-28", "2026-05-28", capture_manifests=captures,
    )
    assert updated["success"] is True
    assert updated["updated_dates"] == []
    assert len(captures) == 1

    result = quick_runner._sync_market_index_for_run(
        service,
        capture_manifests=captures,
        market_update_result=updated,
    )

    assert result["success"] is True
    assert result["row_evidence"]["status"] == "captured"
    evidence = _read_evidence(config, result, "2026-05-28")
    assert evidence.status == "attested"


def test_capture_reference_is_not_returned_when_csv_commit_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import data_module.data_loader as data_loader_module

    config = _config(tmp_path)
    captures: list[Path] = []
    monkeypatch.setattr(data_loader_module, "update_market_index_csv", lambda *_args, **_kwargs: False)

    assert _loader(config).update_market_index("2026-05-28", capture_manifests=captures) is False
    assert captures == []
    assert not config.market_index_file.exists()


@pytest.mark.parametrize("fault", ["raw_json", "close_mismatch", "date_mismatch", "missing_report", "no_data"])
def test_invalid_or_absent_reports_never_export_capture_reference(
    tmp_path: Path, fault: str,
) -> None:
    config = _config(tmp_path)
    fmt = _payload("FMTQIK")
    prices = _payload("MI_5MINS_HIST")
    if fault == "close_mismatch":
        prices = _payload("MI_5MINS_HIST", close="20,000.51")
    elif fault == "date_mismatch":
        prices = {
            **prices,
            "data": [["115/05/29", "19,990.00", "20,010.00", "19,900.00", "20,000.50"]],
        }
    elif fault == "missing_report":
        loader = DataLoader(config)
        loader._make_request = lambda url, _params: (
            None if url.endswith("/MI_5MINS_HIST") else _Response(fmt)
        )  # type: ignore[method-assign]
    elif fault == "no_data":
        fmt = {**fmt, "data": []}
        prices = {**prices, "data": []}
    if fault != "missing_report":
        loader = _loader(config, fmtqik=fmt, prices=prices, mismatch_raw=(fault == "raw_json"))

    captures: list[Path] = []
    assert loader.update_market_index("2026-05-28", capture_manifests=captures) is False
    assert captures == []
    assert not config.market_index_file.exists()


def test_csv_overwrite_after_capture_prevents_attestation_but_syncs_legacy_history(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    config.market_index_file.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"日期": "2026-05-27", "收盤價": Decimal("19800.25"), "開盤價": Decimal("19700.00"),
         "最高價": Decimal("19900.00"), "最低價": Decimal("19600.00"), "成交量": 900},
    ]).to_csv(config.market_index_file, index=False, encoding="utf-8-sig")
    captures: list[Path] = []
    assert _loader(config).update_market_index("2026-05-28", capture_manifests=captures) is True
    frame = pd.read_csv(config.market_index_file, encoding="utf-8-sig")
    frame.loc[frame["日期"] == "2026-05-28", "收盤價"] = 19999.0
    frame.to_csv(config.market_index_file, index=False, encoding="utf-8-sig")

    result = UpdateService(config).publish_taiex_market_index(
        capture_manifests=captures,
        market_update_result={"success": True},
    )

    assert result["success"] is True
    assert result["row_evidence"]["status"] == "unknown"
    assert result["row_evidence"]["reason_code"] == "csv_capture_mismatch"
    assert _read_evidence(config, result, "2026-05-28").status == "unknown"
    assert _read_rows(config)[0][0] == "20260527"  # 舊 CSV 歷史列仍同步


def test_duplicate_capture_for_same_date_fails_closed(tmp_path: Path) -> None:
    config = _config(tmp_path)
    captures: list[Path] = []
    loader = _loader(config)
    assert loader.update_market_index("2026-05-28", capture_manifests=captures) is True
    assert loader.update_market_index("2026-05-28", capture_manifests=captures) is True
    assert len(captures) == 2

    result = UpdateService(config).publish_taiex_market_index(
        capture_manifests=captures,
        market_update_result={"success": True},
    )

    assert result["success"] is True
    assert result["row_evidence"]["status"] == "unknown"
    assert result["row_evidence"]["reason_code"] == "duplicate_capture_date"
    assert _read_evidence(config, result, "2026-05-28").status == "unknown"


def test_unproven_partial_update_never_syncs_or_publishes_evidence(tmp_path: Path) -> None:
    config = _config(tmp_path)
    captures: list[Path] = []
    assert _loader(config).update_market_index("2026-05-28", capture_manifests=captures) is True

    result = UpdateService(config).publish_taiex_market_index(
        capture_manifests=captures,
        market_update_result={"success": False, "failed_dates": ["2026-05-29"]},
    )

    assert result["success"] is False
    assert result["synced_records"] == 0
    assert result["row_evidence"]["status"] == "unknown"
    assert _read_rows(config) == []


def test_sqlite_disabled_preserves_skip_semantics_and_no_evidence(tmp_path: Path) -> None:
    config = _config(tmp_path, use_sqlite=False)
    result = UpdateService(config).publish_taiex_market_index(
        capture_manifests=[],
        market_update_result={"success": True},
    )
    assert result["success"] is True
    assert result["skipped"] is True
    assert result["synced_records"] == 0
    assert result["row_evidence"]["status"] == "unknown"


def test_sidecar_reader_detects_sqlite_row_drift(tmp_path: Path) -> None:
    config = _config(tmp_path)
    captures: list[Path] = []
    assert _loader(config).update_market_index("2026-05-28", capture_manifests=captures) is True
    result = UpdateService(config).publish_taiex_market_index(
        capture_manifests=captures,
        market_update_result={"success": True},
    )
    assert result["row_evidence"]["status"] == "captured"
    with DBManager(config).connect() as connection:
        connection.execute(
            'UPDATE market_indices SET "收盤指數" = ? WHERE "日期" = ? AND "指數名稱" = ?',
            (19999.0, "20260528", "TAIEX"),
        )
    readback = _read_evidence(config, result, "2026-05-28")
    assert readback.status == "unknown"
    assert readback.reason_code == "sqlite_row_drift"


def test_missing_capture_date_keeps_legacy_sync_success_but_evidence_unknown(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.market_index_file.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"日期": "2026-05-27", "收盤價": Decimal("19800.25"), "開盤價": Decimal("19700.00"),
         "最高價": Decimal("19900.00"), "最低價": Decimal("19600.00"), "成交量": 900},
    ]).to_csv(config.market_index_file, index=False, encoding="utf-8-sig")
    captures: list[Path] = []
    assert _loader(config).update_market_index("2026-05-28", capture_manifests=captures) is True

    # 模擬另一個合法 CSV publisher 在本次讀取前移除了指定日；舊列仍要同步，
    # 但此次 capture 不能被用來證明一個不存在於 CSV/SQLite 的列。
    pd.DataFrame([
        {"日期": "2026-05-27", "收盤價": Decimal("19800.25"), "開盤價": Decimal("19700.00"),
         "最高價": Decimal("19900.00"), "最低價": Decimal("19600.00"), "成交量": 900},
    ]).to_csv(config.market_index_file, index=False, encoding="utf-8-sig")

    result = UpdateService(config).publish_taiex_market_index(
        capture_manifests=captures,
        market_update_result={"success": True},
    )
    assert result["success"] is True
    assert result["synced_records"] == 1
    assert result["row_evidence"]["status"] == "unknown"
    assert result["row_evidence"]["reason_code"] == "csv_capture_mismatch"
    assert len(_read_rows(config)) == 1


def test_sqlite_trigger_drift_does_not_turn_successful_sync_into_failure(tmp_path: Path) -> None:
    config = _config(tmp_path)
    captures: list[Path] = []
    assert _loader(config).update_market_index("2026-05-28", capture_manifests=captures) is True
    db = DBManager(config)
    with db.connect() as connection:
        connection.execute(
            'CREATE TRIGGER "taiex_test_corruption" AFTER INSERT ON "market_indices" '
            "WHEN NEW.\"指數名稱\"='TAIEX' BEGIN "
            'UPDATE "market_indices" SET "收盤指數"=19999 WHERE "指數名稱"=NEW."指數名稱" '
            'AND "日期"=NEW."日期"; END'
        )

    result = UpdateService(config).publish_taiex_market_index(
        capture_manifests=captures,
        market_update_result={"success": True},
    )
    assert result["success"] is True
    assert result["synced_records"] == 1
    assert result["row_evidence"]["status"] == "unknown"
    assert result["row_evidence"]["reason_code"] == "sqlite_row_readback_mismatch"
    assert _read_rows(config)[0][2] == 19999.0


def test_sidecar_write_failure_keeps_committed_csv_sync_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import data_module.taiex_market_index_publication as publication

    config = _config(tmp_path)
    captures: list[Path] = []
    assert _loader(config).update_market_index("2026-05-28", capture_manifests=captures) is True
    monkeypatch.setattr(
        publication, "_write_sidecar",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("synthetic sidecar failure")),
    )

    result = UpdateService(config).publish_taiex_market_index(
        capture_manifests=captures,
        market_update_result={"success": True},
    )
    assert result["success"] is True
    assert result["synced_records"] == 1
    assert result["row_evidence"]["status"] == "unknown"
    assert result["row_evidence"]["reason_code"] == "sidecar_publication_failed"
    assert _read_rows(config)[0][0] == "20260528"


def test_reader_rejects_rehashed_sidecar_with_false_sqlite_type_map(tmp_path: Path) -> None:
    import data_module.taiex_market_index_publication as publication

    config = _config(tmp_path)
    captures: list[Path] = []
    assert _loader(config).update_market_index("2026-05-28", capture_manifests=captures) is True
    result = UpdateService(config).publish_taiex_market_index(
        capture_manifests=captures,
        market_update_result={"success": True},
    )
    descriptor = dict(result["row_evidence"])
    original_path = config.output_root / descriptor["relative_path"]
    payload = json.loads(original_path.read_text(encoding="utf-8"))
    payload["captures"][0]["sqlite_storage_types"]["收盤指數"] = "text"
    body = publication._canonical_json(payload)
    digest = publication._sha256(body)
    relative = Path("scheduled") / "taiex_market_index_evidence" / f"{digest}.json"
    tampered_path = config.output_root / relative
    tampered_path.parent.mkdir(parents=True, exist_ok=True)
    tampered_path.write_bytes(body)
    descriptor["relative_path"] = relative.as_posix()
    descriptor["sha256"] = digest

    evidence = read_taiex_market_index_evidence(
        output_root=config.output_root,
        data_root=config.data_root,
        database_path=config.db_file,
        descriptor=descriptor,
        source_date="2026-05-28",
    )
    assert evidence.status == "unknown"
    assert evidence.reason_code == "sqlite_row_drift"


@pytest.mark.parametrize("duplicate_kind", ["identical", "different"])
def test_reader_rejects_duplicate_sqlite_taiex_key_without_unique_constraint(
    tmp_path: Path, duplicate_kind: str,
) -> None:
    config = _config(tmp_path)
    captures: list[Path] = []
    assert _loader(config).update_market_index("2026-05-28", capture_manifests=captures) is True
    result = UpdateService(config).publish_taiex_market_index(
        capture_manifests=captures,
        market_update_result={"success": True},
    )
    assert result["row_evidence"]["status"] == "captured"

    connection = sqlite3.connect(config.db_file)
    try:
        # CTAS 用來移除來源資料表的鍵約束，同時保留欄位與已驗證的列值。
        connection.execute(
            'CREATE TABLE "market_indices_without_unique" AS '
            'SELECT * FROM "market_indices" WHERE 0'
        )
        connection.execute(
            'INSERT INTO "market_indices_without_unique" '
            'SELECT * FROM "market_indices" WHERE "指數名稱"=? AND "日期"=?',
            ("TAIEX", "20260528"),
        )
        connection.execute(
            'INSERT INTO "market_indices_without_unique" '
            'SELECT * FROM "market_indices" WHERE "指數名稱"=? AND "日期"=?',
            ("TAIEX", "20260528"),
        )
        if duplicate_kind == "different":
            connection.execute(
                'UPDATE "market_indices_without_unique" SET "收盤指數"="收盤指數" + 1 '
                'WHERE rowid=(SELECT MAX(rowid) FROM "market_indices_without_unique")'
            )
        connection.execute('DROP TABLE "market_indices"')
        connection.execute(
            'ALTER TABLE "market_indices_without_unique" RENAME TO "market_indices"'
        )
        connection.commit()
    finally:
        connection.close()

    evidence = _read_evidence(config, result, "2026-05-28")
    assert evidence.status == "unknown"
    assert evidence.reason_code == "evidence_validation_failed"


def test_reader_does_not_create_missing_sqlite_database(tmp_path: Path) -> None:
    config = _config(tmp_path)
    captures: list[Path] = []
    assert _loader(config).update_market_index("2026-05-28", capture_manifests=captures) is True
    result = UpdateService(config).publish_taiex_market_index(
        capture_manifests=captures,
        market_update_result={"success": True},
    )
    assert result["row_evidence"]["status"] == "captured"

    database_path = config.db_file
    moved_path = database_path.with_name(database_path.name + ".moved")
    database_path.rename(moved_path)
    try:
        evidence = _read_evidence(config, result, "2026-05-28")
        assert evidence.status == "unknown"
        assert not database_path.exists()
    finally:
        if database_path.exists():
            database_path.unlink()
        moved_path.rename(database_path)


def test_incompatible_market_indices_schema_fails_closed(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.market_index_file.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"日期": "2026-05-28", "收盤價": 1}]).to_csv(
        config.market_index_file, index=False, encoding="utf-8-sig",
    )
    config.db_file.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(config.db_file)
    try:
        connection.execute('CREATE TABLE market_indices ("日期" TEXT, "收盤指數" REAL)')
        connection.commit()
    finally:
        connection.close()

    result = UpdateService(config).publish_taiex_market_index(
        capture_manifests=[],
        market_update_result={"success": True},
    )
    assert result["success"] is False
    assert result["row_evidence"]["reason_code"] == "sqlite_schema_unsupported"
    assert "缺少 TAIEX 複合鍵欄位" in result["message"]


def test_keyed_replacement_clears_stale_dynamic_columns_and_preserves_sibling(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.market_index_file.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"日期": "2026-05-28", "收盤價": Decimal("20000.50"), "開盤價": Decimal("19990.00"),
         "最高價": Decimal("20010.00"), "最低價": Decimal("19900.00"), "成交量": 1234},
    ]).to_csv(config.market_index_file, index=False, encoding="utf-8-sig")
    connection = sqlite3.connect(config.db_file)
    try:
        connection.execute(
            'CREATE TABLE market_indices ('
            '"日期" TEXT, "指數名稱" TEXT, "收盤指數" REAL, "開盤價" REAL, '
            '"最高價" REAL, "最低價" REAL, "收盤價" REAL, "成交量" REAL, '
            '"legacy_dynamic" TEXT, PRIMARY KEY ("指數名稱", "日期"))'
        )
        connection.executemany(
            'INSERT INTO market_indices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            [
                ("20260528", "TAIEX", 1.0, 1.0, 1.0, 1.0, 1.0, 2.0, "stale"),
                ("20260528", "半導體", 1234.5, None, None, None, None, None, "keep"),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    result = UpdateService(config).publish_taiex_market_index(
        capture_manifests=[],
        market_update_result={"success": True},
    )
    assert result["success"] is True
    connection = sqlite3.connect(config.db_file)
    try:
        assert connection.execute(
            'SELECT "legacy_dynamic" FROM market_indices WHERE "指數名稱"="TAIEX" AND "日期"="20260528"'
        ).fetchone() == (None,)
        assert connection.execute(
            'SELECT "legacy_dynamic" FROM market_indices WHERE "指數名稱"="半導體" AND "日期"="20260528"'
        ).fetchone() == ("keep",)
    finally:
        connection.close()
