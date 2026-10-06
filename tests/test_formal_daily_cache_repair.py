from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from types import ModuleType
from typing import Any, Mapping

import pandas as pd
import pytest

from data_module.daily_price_source_guard import (
    AGGREGATE_SOURCE_VERSION,
    validate_aggregate_receipt_payload,
)
from data_module.ml_daily_price_revision_gate import REPAIR_SCHEMA
from scripts import repair_formal_daily_cache as cache


DB_COLUMNS = (
    "日期",
    "證券代號",
    "證券名稱",
    "成交股數",
    "成交筆數",
    "成交金額",
    "開盤價",
    "最高價",
    "最低價",
    "收盤價",
    "漲跌",
    "漲跌價差",
    "最後揭示買價",
    "最後揭示買量",
    "最後揭示賣價",
    "最後揭示賣量",
    "本益比",
)
SESSION_DATES = (
    "20141227",
    "20160130",
    "20160604",
    "20160910",
    "20170218",
    "20170603",
    "20170930",
    "20180331",
    "20181222",
)


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _write_json(path: Path, value: object) -> bytes:
    body = _json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return body


def _row(day: str, code: str, close: float, *, name: str = "測試標的") -> dict[str, object]:
    return {
        "日期": day,
        "證券代號": code,
        "證券名稱": name,
        "成交股數": 1_250,
        "成交筆數": 17,
        "成交金額": 125_000,
        "開盤價": close - 1,
        "最高價": close + 1,
        "最低價": close - 2,
        "收盤價": close,
        "漲跌": "+",
        "漲跌價差": 0.5,
        "最後揭示買價": close - 0.5,
        "最後揭示買量": 2_000,
        "最後揭示賣價": close + 0.5,
        "最後揭示賣量": 1_800,
        "本益比": None,
    }


def _receipt_hash(payload: dict[str, object]) -> dict[str, object]:
    body = dict(payload)
    body["receipt_sha256"] = "sha256:" + hashlib.sha256(_json_bytes(payload)).hexdigest()
    return body


def _exclusion_item(
    root: Path,
    *,
    keys: list[tuple[str, str]],
    closed_dates: list[str],
) -> dict[str, object]:
    receipt_path = root / "output" / "scheduled" / "excluded_daily_price_repair_receipts" / "test" / "receipt.json"
    _write_json(receipt_path, {"fixture": "verified exclusion receipt"})
    return {
        "keys": keys,
        "closed_dates": closed_dates,
        "plan_sha256": "sha256:" + "d" * 64,
        "receipt_sha256": cache.file_hash(receipt_path),
        "receipt_path": str(receipt_path.resolve()),
        "acquired_at": datetime.now(timezone.utc).isoformat(),
        "source_start_date": min(closed_dates or [day for day, _ in keys]),
        "evidence_archive_relative": "output/scheduled/excluded_daily_price_repair_sources/test",
        "market_plan_sha256": "sha256:" + "e" * 64,
    }


@pytest.fixture
def prepared_world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    exclusions = ModuleType("data_module.excluded_daily_price_revision")
    exclusions.load_exclusion_evidence = lambda database_path: []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "data_module.excluded_daily_price_revision", exclusions)
    root = tmp_path / "FA_Data"
    database = root / "sqlite" / "twstock.db"
    database.parent.mkdir(parents=True)
    type_map = {
        "日期": "TEXT",
        "證券代號": "TEXT",
        "證券名稱": "TEXT",
        "成交股數": "INTEGER",
        "成交筆數": "INTEGER",
        "成交金額": "INTEGER",
        "開盤價": "REAL",
        "最高價": "REAL",
        "最低價": "REAL",
        "收盤價": "REAL",
        "漲跌": "TEXT",
        "漲跌價差": "REAL",
        "最後揭示買價": "REAL",
        "最後揭示買量": "INTEGER",
        "最後揭示賣價": "REAL",
        "最後揭示賣量": "INTEGER",
        "本益比": "REAL",
    }
    column_sql = ",".join(f'"{column}" {type_map[column]}' for column in DB_COLUMNS)
    session_rows = [_row(day, "0050", 90.0 + index) for index, day in enumerate(SESSION_DATES)]
    may_row = _row("20260520", "2330", 100.5, name="台積電")
    future_row = _row("20260521", "2330", 101.0, name="台積電")
    source_rows = sorted([*session_rows, may_row, future_row], key=lambda row: (row["日期"], row["證券代號"]))

    connection = sqlite3.connect(database)
    connection.execute(f"CREATE TABLE daily_prices ({column_sql})")
    quoted_columns = ",".join(f'"{column}"' for column in DB_COLUMNS)
    connection.executemany(
        f"INSERT INTO daily_prices ({quoted_columns}) "
        f"VALUES ({','.join('?' for _ in DB_COLUMNS)})",
        [[row[column] for column in DB_COLUMNS] for row in source_rows],
    )
    connection.commit()
    connection.close()

    session_dir = root / cache.SESSION_RECEIPT_DIR / "run-test"
    capture_sources: list[dict[str, str]] = []
    for day in SESSION_DATES:
        for venue in ("twse", "tpex"):
            raw_path = session_dir / "sources" / f"{day}-{venue}.json"
            receipt_path = session_dir / "sources" / f"{day}-{venue}.receipt.json"
            raw = _write_json(raw_path, {"fixture": f"{day}-{venue}"})
            capture = {
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "historical_pit": False,
                "date": day,
                "url": (
                    "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date="
                    f"{day[:4]}/{day[4:6]}/{day[6:]}"
                    if venue == "twse"
                    else "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc?date="
                    f"{day[:4]}/{day[4:6]}/{day[6:]}"
                ),
            }
            receipt_bytes = _write_json(receipt_path, capture)
            capture_sources.append(
                {
                    "day": day,
                    "venue": venue,
                    "path": str(raw_path.resolve()),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "receipt": str(receipt_path.resolve()),
                    "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
                }
            )

    plan_path = session_dir / "plan.json"
    plan = {
        "schema_version": "historical-session-repair.v1",
        "database_path": str(database.resolve()),
        "sources": capture_sources,
        "dates": list(SESSION_DATES),
        "source_start_date": "2014-12-27",
        "source_end_date": "2018-12-22",
        "rows": session_rows,
        "columns": list(DB_COLUMNS),
        "existing_universe": ["0050"],
    }
    plan_bytes = _write_json(plan_path, plan)
    plan_sha = hashlib.sha256(plan_bytes).hexdigest()
    session_receipt_path = session_dir / "receipt.json"
    session_receipt = {
        "state": "applied",
        "plan_sha256": plan_sha,
        "dates": list(SESSION_DATES),
        "rows": len(session_rows),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    session_receipt_bytes = _write_json(session_receipt_path, session_receipt)
    marker_path = session_dir / "revision.json"
    _write_json(
        marker_path,
        {
            "schema_version": "historical-session-revision.v1",
            "database_path": str(database.resolve()),
            "plan_sha256": plan_sha,
            "state": "applied",
            "historical_pit": False,
            "receipt_sha256": hashlib.sha256(session_receipt_bytes).hexdigest(),
        },
    )
    monkeypatch.setattr(cache, "verified_rows", lambda sources, allowed_symbols=None: list(session_rows))

    price_receipt_dir = root / cache.REPAIR_RECEIPT_RELATIVE_DIR
    price_payload = {
        "schema_version": REPAIR_SCHEMA,
        "receipt_kind": "historical_price_spike_repair",
        "status": "applied",
        "db_path": str(database.resolve()),
        "source_date": "20260520",
        "source_update_columns": ["收盤價"],
        "allowlist_count": 1,
        "allowlist_hash": "sha256:" + "a" * 64,
        "plan_hash": "sha256:" + "b" * 64,
        "canonical_sha256": "sha256:" + "c" * 64,
        "historical_decision_time_available": False,
        "available_at_backfilled": False,
        "available_at": None,
        "corrected_at": datetime.now(timezone.utc).isoformat(),
        "official_capture_at": datetime.now(timezone.utc).isoformat(),
        "rows": [
            {
                "date": "20260520",
                "symbol": "2330",
                "before": {"日期": "20260520", "證券代號": "2330", "收盤價": 99.5},
                "after": {"日期": "20260520", "證券代號": "2330", "收盤價": 100.5},
                "source": {"close": 100.5},
                "differing_fields": ["收盤價"],
            }
        ],
    }
    _write_json(price_receipt_dir / "receipt.json", _receipt_hash(price_payload))

    technical_dir = root / cache.TECH_RECEIPT_DIR / "technical-run"
    technical_dir.mkdir(parents=True)
    source_path = technical_dir / "source.sqlite"
    shutil.copyfile(database, source_path)
    with sqlite3.connect(source_path) as source_db:
        daily_hash = cache.table_hash(source_db)
    source_hash = cache.file_hash(source_path)
    _write_json(
        technical_dir / "source.json",
        {
            "schema_version": "formal-technical-repair.v1",
            "root": str(root.resolve()),
            "source_db": str(source_path.resolve()),
            "source_sha256": source_hash,
            "daily_before_hash": daily_hash,
        },
    )
    stage_dir = technical_dir / "stage"
    stage_dir.mkdir()
    manifest_path = stage_dir / "manifest.json"
    _write_json(manifest_path, {"source_db": str(source_path.resolve()), "source_sha256": source_hash})
    tech_receipt = {
        "schema_version": "formal-technical-repair.v1",
        "state": "applied",
        "source_db": str(source_path.resolve()),
        "source_sha256": source_hash,
        "daily_before_hash": daily_hash,
        "manifest_sha256": cache.file_hash(manifest_path),
    }
    _write_json(technical_dir / "receipt.json", tech_receipt)
    _write_json(technical_dir / "journal.json", tech_receipt)

    target = root / "meta_data" / "stock_data_whole.csv"
    target.parent.mkdir(parents=True)
    with target.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(cache.CSV_COLUMNS)
        writer.writerow(["20260714", "0050", "舊列", *([""] * 14)])
    source_receipt_path = cache.aggregate_receipt_path(target)
    _write_json(source_receipt_path, {"preexisting": True})
    fixture_exclusion = _exclusion_item(
        root, keys=[("20000102", "9999")], closed_dates=["20000101"]
    )
    monkeypatch.setattr(
        exclusions,
        "load_exclusion_evidence",
        lambda database: [fixture_exclusion],
    )

    receipt_dir = root / cache.RECEIPT_DIR / "daily-cache-test"
    result = cache.prepare(root, technical_dir, receipt_dir)
    cache.stage(receipt_dir)
    return {
        "root": root,
        "database": database,
        "source_path": source_path,
        "source_sha256": source_hash,
        "technical_dir": technical_dir,
        "target": target,
        "source_receipt": source_receipt_path,
        "receipt_dir": receipt_dir,
        "rows": source_rows,
        "session_rows": session_rows,
        "prepare_result": result,
        "before_hashes": {
            "target": cache.file_hash(target),
            "source_receipt": cache.file_hash(source_receipt_path),
        },
    }


def _manifest(receipt_dir: Path) -> dict[str, Any]:
    return json.loads((receipt_dir / "manifest.json").read_text(encoding="utf-8"))


def test_stage_preserves_full_cache_contract_and_revision_evidence(prepared_world: dict[str, Any]) -> None:
    receipt_dir = Path(prepared_world["receipt_dir"])
    manifest = _manifest(receipt_dir)
    staged_csv = Path(manifest["files"][0]["staged_path"])
    staged_sidecar = Path(manifest["files"][1]["staged_path"])

    with staged_csv.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == list(cache.CSV_COLUMNS)
        rows = list(reader)

    assert len(rows) == 11
    assert rows[0]["日期"] == "20141227"
    assert rows[0]["證券代號"] == "0050"
    assert rows[0]["成交股數"] == "1250"
    assert rows[0]["本益比"] == ""
    assert rows[9]["日期"] == "20260520"
    assert rows[9]["收盤價"] == "100.5"
    assert rows[-1]["日期"] == "20260521"
    assert manifest["canonical_checks"]["session_row_count"] == 9
    assert manifest["excluded_keys"] == [["20000102", "9999"]]
    assert manifest["excluded_closed_dates"] == ["20000101"]
    assert len(manifest["exclusion_evidence"]) == 1
    assert manifest["historical_pit"] is False

    sidecar = json.loads(staged_sidecar.read_text(encoding="utf-8"))
    assert sidecar["source_revision_times"][0]["corrected_at"]
    assert sidecar["source_revision_times"][0]["official_capture_at"]
    assert sidecar["historical_pit"] is False
    actual_frame = pd.read_csv(staged_csv, dtype={"證券代號": str}, keep_default_na=False)
    validate_aggregate_receipt_payload(
        sidecar,
        stock_data_file=Path(prepared_world["target"]),
        actual_frame=actual_frame,
        file_sha256="sha256:" + cache.file_hash(staged_csv),
    )
    assert cache.file_hash(Path(prepared_world["source_path"])) == prepared_world["source_sha256"]


def test_price_revision_accepts_other_legal_rows_on_allowlisted_date(
    prepared_world: dict[str, Any],
) -> None:
    source_path = Path(prepared_world["source_path"])
    extra_row = _row("20260520", "1101", 52.3, name="台泥")
    quoted_columns = ",".join('"' + column + '"' for column in DB_COLUMNS)
    placeholders = ",".join("?" for _ in DB_COLUMNS)
    with sqlite3.connect(source_path) as connection:
        connection.execute(
            f"INSERT INTO daily_prices ({quoted_columns}) VALUES ({placeholders})",
            [extra_row[column] for column in DB_COLUMNS],
        )

    with cache._immutable(source_path) as source:
        payload, evidence = cache._price_revision_evidence(
            Path(prepared_world["root"]),
            Path(prepared_world["database"]),
            source,
            DB_COLUMNS,
        )

    assert payload["allowlist_count"] == 1
    assert evidence["row_count"] == 2
    assert evidence["protected_row_count"] == 1


def test_price_revision_rejects_missing_allowlisted_key(
    prepared_world: dict[str, Any],
) -> None:
    source_path = Path(prepared_world["source_path"])
    with sqlite3.connect(source_path) as connection:
        connection.execute(
            "DELETE FROM daily_prices WHERE 日期='20260520' AND 證券代號='2330'"
        )

    with cache._immutable(source_path) as source:
        with pytest.raises(ValueError, match="整表替換缺少已修訂 key"):
            cache._price_revision_evidence(
                Path(prepared_world["root"]),
                Path(prepared_world["database"]),
                source,
                DB_COLUMNS,
            )


def test_apply_interruption_can_resume_and_rollback_pair(
    prepared_world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt_dir = Path(prepared_world["receipt_dir"])
    target = Path(prepared_world["target"])
    source_receipt = Path(prepared_world["source_receipt"])
    manifest_hash = cache.file_hash(receipt_dir / "manifest.json")
    original_copy = cache._copy_atomic

    def interrupt_before_sidecar(source: Path, destination: Path) -> None:
        if destination == source_receipt:
            raise OSError("simulated process interruption after CSV publication")
        original_copy(source, destination)

    monkeypatch.setattr(cache, "_copy_atomic", interrupt_before_sidecar)
    with pytest.raises(OSError, match="simulated process interruption"):
        cache.apply(receipt_dir, manifest_hash)
    assert cache.file_hash(target) != prepared_world["before_hashes"]["target"]
    assert cache.file_hash(source_receipt) == prepared_world["before_hashes"]["source_receipt"]

    monkeypatch.setattr(cache, "_copy_atomic", original_copy)
    assert cache.recover(receipt_dir, rollback=False)["state"] == "applied"
    after_hash = cache.file_hash(target)
    sidecar = json.loads(source_receipt.read_text(encoding="utf-8"))
    assert sidecar["source_sha256"] == "sha256:" + after_hash

    assert cache.recover(receipt_dir, rollback=True)["state"] == "rolled_back"
    assert cache.file_hash(target) == prepared_world["before_hashes"]["target"]
    assert cache.file_hash(source_receipt) == prepared_world["before_hashes"]["source_receipt"]


def test_resume_finishes_if_process_stops_after_receipt_write(
    prepared_world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt_dir = Path(prepared_world["receipt_dir"])
    manifest_hash = cache.file_hash(receipt_dir / "manifest.json")
    original_write = cache._write_journal

    def interrupt_final_journal(path: Path, journal: Mapping[str, Any]) -> dict[str, Any]:
        if journal.get("state") == "applied":
            raise OSError("simulated stop after final receipt")
        return original_write(path, journal)

    monkeypatch.setattr(cache, "_write_journal", interrupt_final_journal)
    with pytest.raises(OSError, match="simulated stop"):
        cache.apply(receipt_dir, manifest_hash)
    assert (receipt_dir / "receipt.json").is_file()
    assert cache._load_journal(receipt_dir)["state"] == "pending"

    monkeypatch.setattr(cache, "_write_journal", original_write)
    assert cache.recover(receipt_dir, rollback=False)["state"] == "applied"
    cache._validate_applied_receipt(receipt_dir, cache._load_journal(receipt_dir))


def test_database_or_target_drift_is_rejected_without_clobbering(
    prepared_world: dict[str, Any],
) -> None:
    receipt_dir = Path(prepared_world["receipt_dir"])
    database = Path(prepared_world["database"])
    target = Path(prepared_world["target"])
    source_receipt = Path(prepared_world["source_receipt"])
    manifest_hash = cache.file_hash(receipt_dir / "manifest.json")

    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE daily_prices SET 收盤價=102 WHERE 日期='20260521'")
        connection.commit()
    with pytest.raises(ValueError, match="daily_prices 與 immutable source.json hash 已漂移"):
        cache.apply(receipt_dir, manifest_hash)
    assert cache.file_hash(target) == prepared_world["before_hashes"]["target"]
    assert cache.file_hash(source_receipt) == prepared_world["before_hashes"]["source_receipt"]


def test_revision_receipt_drift_is_rejected_before_publication(
    prepared_world: dict[str, Any],
) -> None:
    receipt_dir = Path(prepared_world["receipt_dir"])
    target = Path(prepared_world["target"])
    source_receipt = Path(prepared_world["source_receipt"])
    price_receipt = Path(prepared_world["root"]) / cache.REPAIR_RECEIPT_RELATIVE_DIR / "receipt.json"
    price_receipt.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="daily source revision receipt 發生漂移"):
        cache.apply(receipt_dir, cache.file_hash(receipt_dir / "manifest.json"))
    assert cache.file_hash(target) == prepared_world["before_hashes"]["target"]
    assert cache.file_hash(source_receipt) == prepared_world["before_hashes"]["source_receipt"]


def test_rollback_refuses_external_cache_drift(prepared_world: dict[str, Any]) -> None:
    receipt_dir = Path(prepared_world["receipt_dir"])
    target = Path(prepared_world["target"])
    cache.apply(receipt_dir, cache.file_hash(receipt_dir / "manifest.json"))
    with target.open("ab") as stream:
        stream.write(b"external-change")
    drifted_hash = cache.file_hash(target)

    with pytest.raises(ValueError, match="回復目標在發布後發生外部變更"):
        cache.recover(receipt_dir, rollback=True)
    assert cache.file_hash(target) == drifted_hash


@pytest.mark.parametrize(
    ("keys", "closed_dates"),
    [([("20260521", "2330")], []), ([], ["20181222"])],
)
def test_verified_exclusions_reject_source_keys_or_closed_dates(
    prepared_world: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    keys: list[tuple[str, str]],
    closed_dates: list[str],
) -> None:
    exclusion_module = sys.modules["data_module.excluded_daily_price_revision"]
    item = _exclusion_item(Path(prepared_world["root"]), keys=keys, closed_dates=closed_dates)
    monkeypatch.setattr(exclusion_module, "load_exclusion_evidence", lambda database: [item])
    with cache._immutable(Path(prepared_world["source_path"])) as source:
        with pytest.raises(ValueError, match="immutable daily_prices 仍含已核驗排除"):
            cache._exclusion_state(Path(prepared_world["database"]), source)


def test_exclusion_receipt_identity_drift_blocks_apply(
    prepared_world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    exclusion_module = sys.modules["data_module.excluded_daily_price_revision"]
    item = _exclusion_item(
        Path(prepared_world["root"]), keys=[], closed_dates=["19000101"]
    )
    monkeypatch.setattr(exclusion_module, "load_exclusion_evidence", lambda database: [item])
    receipt_dir = Path(prepared_world["receipt_dir"])

    with pytest.raises(ValueError, match="錯日排除來源 evidence 在 prepare 後發生漂移"):
        cache.apply(receipt_dir, cache.file_hash(receipt_dir / "manifest.json"))
    assert cache.file_hash(Path(prepared_world["target"])) == prepared_world["before_hashes"]["target"]
