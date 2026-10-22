import json
import csv
import hashlib
import sqlite3
from pathlib import Path

import pandas as pd
import pytest
import requests

from data_module.tpex_daily_price_backfill import (
    _SOURCE_ROW_ORDINAL_KEY,
    _SOURCE_ROW_SHA256_KEY,
    normalize_tpex_daily_price_rows,
)
from data_module.tpex_daily_price_source import TPEX_AFTER_TRADING_OTC_URL, TpexDailyPriceSource
from data_module.tpex_daily_price_publication import (
    DOWNLOAD_SCHEMA,
    PUBLICATION_SCHEMA,
    publish_sqlite_row_evidence,
    _payload_bytes,
    _row_hash,
    _COLUMNS,
)


def test_normalizer_keeps_the_surviving_duplicate_source_ordinal() -> None:
    rows = [
        {
            "Date": "1150616",
            "SecuritiesCompanyCode": "3207",
            "CompanyName": "舊列",
            "Close": "42.50",
            _SOURCE_ROW_ORDINAL_KEY: 3,
            _SOURCE_ROW_SHA256_KEY: "sha256:first",
        },
        {
            "Date": "1150616",
            "SecuritiesCompanyCode": "3207",
            "CompanyName": "存活列",
            "Close": "43.00",
            _SOURCE_ROW_ORDINAL_KEY: 8,
            _SOURCE_ROW_SHA256_KEY: "sha256:last",
        },
    ]

    normalized = normalize_tpex_daily_price_rows(rows, fallback_date="2026-06-16")

    assert len(normalized.rows) == 1
    assert normalized.rows[0]["證券名稱"] == "存活列"
    assert normalized.source_row_ordinals == (8,)
    assert normalized.source_row_sha256s == ("sha256:last",)


def test_official_source_publishes_row_projection_with_raw_ordinal_and_unknown_pit(
    tmp_path: Path, monkeypatch
) -> None:
    raw_payload = {
        "tables": [
            {
                "date": "1150616",
                "fields": ["代號", "名稱", "收盤"],
                "data": [["3207", "耀勝", "42.50"], ["3219", "倚強", "37.00"]],
            }
        ]
    }
    raw_bytes = json.dumps(
        raw_payload, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")

    class Response:
        url = TPEX_AFTER_TRADING_OTC_URL + "?date=2026/06/16&type=EW&response=json"
        status_code = 200
        headers = {"content-type": "application/json"}
        content = raw_bytes

        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return raw_payload

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: Response())
    data_root = tmp_path / "data"
    source = TpexDailyPriceSource(
        output_dir=data_root / "daily_price_tpex",
        source_custody_root=tmp_path / "output",
    )

    result = source.update_for_date("2026-06-16")

    assert result.success is True
    assert result.source_custody is not None
    descriptor = result.source_custody["row_projection_manifest"]
    assert descriptor["status"] == "captured"
    assert descriptor["schema_version"] == DOWNLOAD_SCHEMA
    manifest_path = tmp_path / "output" / Path(*descriptor["relative_path"].split("/"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_id"] == "tpex.daily_close_quotes"
    assert manifest["source_published_at"] is None
    assert manifest["available_at"] is None
    assert manifest["formal_source_contract_eligible"] is False
    assert manifest["pit_eligible"] is False
    assert manifest["training_eligible"] is False
    assert [row["source_row_ordinal"] for row in manifest["rows"]] == [0, 1]
    assert [row["stock_code"] for row in manifest["rows"]] == ["3207", "3219"]

    database = data_root / "sqlite" / "twstock.db"
    database.parent.mkdir(parents=True)
    with result.output_file.open("r", encoding="utf-8-sig", newline="") as stream:
        csv_rows = list(csv.DictReader(stream))
    column_sql = ", ".join(f'"{column}" TEXT' for column in csv_rows[0])
    column_names = tuple(csv_rows[0])
    with sqlite3.connect(database) as connection:
        connection.execute(
            f"CREATE TABLE daily_prices ({column_sql}, PRIMARY KEY (\"證券代號\", \"日期\"))"
        )
        placeholders = ", ".join("?" for _ in column_names)
        insert = (
            "INSERT INTO daily_prices ("
            + ", ".join(f'"{column}"' for column in column_names)
            + f") VALUES ({placeholders})"
        )
        connection.executemany(
            insert,
            [tuple(row[column] or None for column in column_names) for row in csv_rows],
        )
    merged_frame = pd.read_csv(
        result.output_file,
        encoding="utf-8-sig",
        dtype={"日期": str, "證券代號": str},
    )

    publication = publish_sqlite_row_evidence(
        output_root=tmp_path / "output",
        data_root=data_root,
        database_path=database,
        source_diagnostics=[result.source_custody],
        merged_frame=merged_frame,
    )

    assert publication["status"] == "captured"
    assert publication["schema_version"] == PUBLICATION_SCHEMA
    publication_path = tmp_path / "output" / Path(*publication["relative_path"].split("/"))
    publication_payload = json.loads(publication_path.read_text(encoding="utf-8"))
    assert publication_payload["formal_source_contract_eligible"] is False
    assert publication_payload["pit_eligible"] is False
    assert publication_payload["training_eligible"] is False
    assert len(publication_payload["rows"]) == 2
    assert all(row["source_published_at"] is None for row in publication_payload["rows"])

    duplicated_frame = pd.concat([merged_frame, merged_frame.iloc[[0]]], ignore_index=True)
    ambiguous_publication = publish_sqlite_row_evidence(
        output_root=tmp_path / "output",
        data_root=data_root,
        database_path=database,
        source_diagnostics=[result.source_custody],
        merged_frame=duplicated_frame,
    )
    ambiguous_path = (
        tmp_path / "output" / Path(*ambiguous_publication["relative_path"].split("/"))
    )
    ambiguous_payload = json.loads(ambiguous_path.read_text(encoding="utf-8"))
    assert [row["stock_code"] for row in ambiguous_payload["rows"]] == ["3219"]


def _captured_fixture(tmp_path: Path, monkeypatch):
    raw_payload = {
        "tables": [
            {
                "date": "1150616",
                "fields": ["代號", "名稱", "收盤"],
                "data": [["3207", "耀勝", "42.50"], ["3219", "倚強", "37.00"]],
            }
        ]
    }
    raw_bytes = json.dumps(
        raw_payload, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")

    class Response:
        url = TPEX_AFTER_TRADING_OTC_URL + "?date=2026/06/16&type=EW&response=json"
        status_code = 200
        headers = {"content-type": "application/json"}
        content = raw_bytes

        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return raw_payload

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: Response())
    data_root = tmp_path / "data"
    output_root = tmp_path / "output"
    result = TpexDailyPriceSource(
        output_dir=data_root / "daily_price_tpex",
        source_custody_root=output_root,
    ).update_for_date("2026-06-16")
    assert result.success and result.source_custody is not None
    descriptor = result.source_custody["row_projection_manifest"]
    database = data_root / "sqlite" / "twstock.db"
    database.parent.mkdir(parents=True)
    with result.output_file.open("r", encoding="utf-8-sig", newline="") as stream:
        csv_rows = list(csv.DictReader(stream))
    column_names = tuple(csv_rows[0])
    column_sql = ", ".join(f'"{column}" TEXT' for column in column_names)
    with sqlite3.connect(database) as connection:
        connection.execute(
            f"CREATE TABLE daily_prices ({column_sql}, PRIMARY KEY (\"證券代號\", \"日期\"))"
        )
        columns_sql = ", ".join(f'"{column}"' for column in column_names)
        placeholders = ", ".join("?" for _ in column_names)
        connection.executemany(
            f"INSERT INTO daily_prices ({columns_sql}) VALUES ({placeholders})",
            [tuple(row[column] or None for column in column_names) for row in csv_rows],
        )
    frame = pd.read_csv(
        result.output_file,
        encoding="utf-8-sig",
        dtype={"日期": str, "證券代號": str},
    )
    return output_root, data_root, database, result, descriptor, frame


@pytest.mark.parametrize(
    "artifact_key",
    [
        "raw_response_relative_path",
        "custody_receipt_relative_path",
        "observation_receipt_relative_path",
    ],
)
def test_download_manifest_rejects_source_artifact_byte_drift(
    tmp_path: Path, monkeypatch, artifact_key: str
) -> None:
    output, data, _, result, descriptor, _ = _captured_fixture(tmp_path, monkeypatch)
    manifest_path = output / Path(*descriptor["relative_path"].split("/"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact_path = output / Path(*manifest[artifact_key].split("/"))
    artifact_path.write_bytes(artifact_path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        publish_sqlite_row_evidence(
            output_root=output,
            data_root=data,
            database_path=data / "sqlite" / "twstock.db",
            source_diagnostics=[result.source_custody],
            merged_frame=pd.DataFrame(),
        )


def _write_resigned_manifest(output: Path, descriptor: dict, manifest: dict) -> dict:
    payload = _payload_bytes(
        {key: value for key, value in manifest.items() if key != "content_sha256"}
    )
    path = output / "tampered" / f"{len(payload)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {
        **descriptor,
        "relative_path": path.relative_to(output).as_posix(),
        "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
    }


def test_resigned_ordinal_or_row_mapping_cannot_override_raw_parser(
    tmp_path: Path, monkeypatch
) -> None:
    output, data, database, result, descriptor, frame = _captured_fixture(
        tmp_path, monkeypatch
    )
    manifest_path = output / Path(*descriptor["relative_path"].split("/"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["rows"][0]["source_row_ordinal"] = 99
    resigned = _write_resigned_manifest(output, descriptor, manifest)
    diagnostic = {**result.source_custody, "row_projection_manifest": resigned}
    with pytest.raises(ValueError):
        publish_sqlite_row_evidence(
            output_root=output,
            data_root=data,
            database_path=database,
            source_diagnostics=[diagnostic],
            merged_frame=frame,
        )


def test_resigned_csv_and_manifest_value_drift_fails_raw_to_normalized_check(
    tmp_path: Path, monkeypatch
) -> None:
    output, data, database, result, descriptor, frame = _captured_fixture(
        tmp_path, monkeypatch
    )
    manifest_path = output / Path(*descriptor["relative_path"].split("/"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    csv_path = data / Path(*manifest["csv_relative_path"].split("/"))
    rows = list(csv.DictReader(csv_path.read_text(encoding="utf-8-sig").splitlines()))
    rows[0]["收盤價"] = "99.00"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    manifest["csv_sha256"] = "sha256:" + hashlib.sha256(csv_path.read_bytes()).hexdigest()
    manifest["rows"][0]["projection_row_sha256"] = _row_hash(rows[0], _COLUMNS)
    resigned = _write_resigned_manifest(output, descriptor, manifest)
    diagnostic = {**result.source_custody, "row_projection_manifest": resigned}
    with pytest.raises(ValueError):
        publish_sqlite_row_evidence(
            output_root=output,
            data_root=data,
            database_path=database,
            source_diagnostics=[diagnostic],
            merged_frame=frame,
        )


@pytest.mark.parametrize("change", ["value", "delete"])
def test_sqlite_drift_or_missing_row_never_publishes_that_key(
    tmp_path: Path, monkeypatch, change: str
) -> None:
    output, data, database, result, _, frame = _captured_fixture(tmp_path, monkeypatch)
    with sqlite3.connect(database) as connection:
        if change == "value":
            connection.execute(
                'UPDATE daily_prices SET "收盤價" = ? WHERE "證券代號" = ?',
                ("99.00", "3207"),
            )
        else:
            connection.execute(
                'DELETE FROM daily_prices WHERE "證券代號" = ?', ("3207",)
            )
    publication = publish_sqlite_row_evidence(
        output_root=output,
        data_root=data,
        database_path=database,
        source_diagnostics=[result.source_custody],
        merged_frame=frame,
    )
    assert publication["status"] == "captured"
    payload_path = output / Path(*publication["relative_path"].split("/"))
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert [row["stock_code"] for row in payload["rows"]] == ["3219"]


def test_existing_csv_without_same_run_custody_does_not_gain_lineage(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "data" / "daily_price_tpex"
    output_dir.mkdir(parents=True)
    old_csv = output_dir / "20260616.csv"

    def no_current_capture(*_args):
        raise RuntimeError("no current response")

    old_csv.write_text("日期,證券代號\n20260616,3207\n", encoding="utf-8-sig")
    source = TpexDailyPriceSource(
        output_dir=output_dir,
        fetch_rows=no_current_capture,
        source_custody_root=tmp_path / "output",
    )
    result = source.update_for_date("2026-06-16")
    assert result.success is False
    assert result.source_custody is None
    assert old_csv.read_text(encoding="utf-8-sig") == "日期,證券代號\n20260616,3207\n"
    output_root = tmp_path / "output"
    output_root.mkdir()
    data_root = tmp_path / "data"
    database = data_root / "sqlite" / "twstock.db"
    projection = publish_sqlite_row_evidence(
        output_root=output_root,
        data_root=data_root,
        database_path=database,
        source_diagnostics=[],
        merged_frame=pd.read_csv(old_csv, encoding="utf-8-sig"),
    )
    assert projection == {
        "status": "unknown",
        "reason_code": "producer_manifest_missing",
    }
    assert not list(output_root.rglob("*.json"))
