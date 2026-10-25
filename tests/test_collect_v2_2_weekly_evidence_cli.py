from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "collect_v2_2_weekly_evidence.py"


def _create_source_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TABLE daily_prices (
                日期 TEXT NOT NULL,
                證券代號 TEXT NOT NULL,
                開盤價 REAL,
                最高價 REAL,
                最低價 REAL,
                收盤價 REAL,
                成交股數 INTEGER,
                成交筆數 INTEGER,
                成交金額 INTEGER
            )"""
        )
        connection.executemany(
            """INSERT INTO daily_prices (
                日期, 證券代號, 開盤價, 最高價, 最低價, 收盤價,
                成交股數, 成交筆數, 成交金額
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                ("20260709", "2330", 100, 102, 99, 101, 100, 10, 10000),
                ("20260710", "2330", 101, 103, 100, 102, 100, 10, 10000),
                ("20260710", "2317", None, 205, 199, 204, 900, 15, 180000),
                ("20260710", "2330", 101, 103, 100, 102, 100, 10, 10000),
                ("20260710", "2331", 50, 52, 49, None, 500, 20, 25000),
                ("20260713", "2330", 102, 104, 101, 103, 100, 10, 10000),
            ],
        )


def _create_twse_custody(
    root: Path,
    *,
    date_key: str,
    rows: list[tuple[str, list[str]]],
) -> str:
    capture_root = (
        root
        / "output"
        / "scheduled"
        / "daily_price_source_custody"
        / "twse"
        / date_key
        / "test-capture"
    )
    capture_root.mkdir(parents=True)
    fields = ["證券代號", "開盤價", "最高價", "最低價", "收盤價"]
    payload = {
        "date": date_key,
        "tables": [{"fields": fields, "data": [[symbol, *ohlc] for symbol, ohlc in rows]}],
    }
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    (capture_root / "raw_response.bin").write_bytes(raw)
    receipt = {
        "schema_version": "official-daily-price-response-capture.v1",
        "source_authority": "twse",
        "source_id": "twse.mi_index.daily_price",
        "source_date": f"{date_key[:4]}-{date_key[4:6]}-{date_key[6:]}",
        "response": {"http_status": 200},
        "raw_response_sha256": digest,
        "raw_response_bytes": len(raw),
    }
    receipt["content_sha256"] = "sha256:" + hashlib.sha256(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    (capture_root / "receipt.json").write_text(
        json.dumps(receipt),
        encoding="utf-8",
    )
    return digest
def test_collect_cli_saves_pending_sidecar_record_and_reports(
    tmp_path: Path,
) -> None:
    source_db_path = tmp_path / "twstock.db"
    sidecar_db_path = tmp_path / "weekly-collection-sidecar.sqlite"
    output_root = tmp_path / "output"
    _create_source_database(source_db_path)
    official_hash = _create_twse_custody(
        tmp_path,
        date_key="20260710",
        rows=[
            ("2317", ["--", "205", "199", "204"]),
            ("2331", ["50", "52", "49", "51"]),
        ],
    )
    source_bytes_before = source_db_path.read_bytes()

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source-db-path",
            str(source_db_path),
            "--sidecar-db-path",
            str(sidecar_db_path),
            "--output-root",
            str(output_root),
            "--period-end",
            "2026-07-12",
            "--json-output",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["collection_status"] == "pending_human_review"
    assert payload["storage_status"] == "pending_human_review"
    assert payload["human_approval_required"] is True
    assert payload["automatic_revalidation"] is False
    assert payload["gate_credit_status"] == "pending_human_review"
    assert payload["write_intent"] is False
    assert payload["last_trading_date"] == "2026-07-10"
    coverage = payload["source_coverage"]
    assert coverage["status"] == "degraded"
    assert coverage["trading_day_count"] == 2
    assert coverage["observed_row_count"] == 5
    assert coverage["observed_symbol_count"] == 3
    assert coverage["duplicate_symbol_rows"] == 1
    assert coverage["incomplete_row_count"] == 2
    assert coverage["official_source_missing_value_rows"] == 1
    assert coverage["local_projection_missing_official_value_rows"] == 1
    assert coverage["unverified_missing_value_rows"] == 0
    assert coverage["integrity_examples"][0] == {
        "date": "2026-07-10",
        "symbol": "2317",
        "missing_fields": ["開盤價"],
        "activity": {"成交股數": 900, "成交筆數": 15, "成交金額": 180000},
        "classification": "official_source_reports_missing_values",
        "official_ohlc": {
            "開盤價": "--",
            "最高價": "205",
            "最低價": "199",
            "收盤價": "204",
        },
        "official_receipt_sha256": official_hash,
        "official_receipt_path": str(
            (
                tmp_path
                / "output"
                / "scheduled"
                / "daily_price_source_custody"
                / "twse"
                / "20260710"
                / "test-capture"
                / "receipt.json"
            ).resolve()
        ),
    }
    assert coverage["integrity_examples"][1]["classification"] == (
        "local_projection_missing_official_value"
    )
    assert coverage["expected_universe_count"] is None
    assert coverage["full_coverage_claimed"] is False
    assert source_db_path.read_bytes() == source_bytes_before
    with sqlite3.connect(sidecar_db_path) as connection:
        stored_statuses = connection.execute(
            "SELECT DISTINCT status FROM evidence_weekly_collections"
        ).fetchall()
        schema_version = connection.execute(
            "SELECT version FROM sidecar_schema_version"
        ).fetchall()
    assert stored_statuses == [("pending_human_review",)]
    assert schema_version == [(3,)]

    report_directory = output_root / "scheduled" / "v2_2_weekly_collection"
    json_reports = list(report_directory.glob("*.json"))
    markdown_reports = list(report_directory.glob("*.md"))
    assert len(json_reports) == 1
    assert len(markdown_reports) == 1
    assert (
        json.loads(json_reports[0].read_text(encoding="utf-8"))[
            "collection_status"
        ]
        == "pending_human_review"
    )
    markdown = markdown_reports[0].read_text(encoding="utf-8")
    assert "pending_human_review" in markdown
    assert "Human approval required: `true`" in markdown
    assert "Write intent: `false`" in markdown
    assert "Full coverage claimed: `false`" in markdown
    assert "duplicate_symbol_rows_observed" in markdown
    assert "official_source_reports_missing_values" in markdown
    assert official_hash in markdown


def test_collect_cli_keeps_tampered_official_receipt_unverified(tmp_path: Path) -> None:
    source_db_path = tmp_path / "twstock.db"
    sidecar_db_path = tmp_path / "weekly-collection-sidecar.sqlite"
    _create_source_database(source_db_path)
    _create_twse_custody(
        tmp_path,
        date_key="20260710",
        rows=[("2317", ["--", "205", "199", "204"])],
    )
    raw_path = (
        tmp_path
        / "output"
        / "scheduled"
        / "daily_price_source_custody"
        / "twse"
        / "20260710"
        / "test-capture"
        / "raw_response.bin"
    )
    raw_path.write_bytes(raw_path.read_bytes().replace(b"--", b"XX", 1))

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source-db-path",
            str(source_db_path),
            "--sidecar-db-path",
            str(sidecar_db_path),
            "--output-root",
            str(tmp_path / "output"),
            "--period-end",
            "2026-07-12",
            "--json-output",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    coverage = json.loads(completed.stdout)["source_coverage"]
    assert coverage["official_source_missing_value_rows"] == 0
    assert coverage["local_projection_missing_official_value_rows"] == 0
    assert coverage["unverified_missing_value_rows"] == 2
    assert coverage["integrity_examples"][0]["official_receipt_sha256"] is None
    assert coverage["integrity_examples"][0]["classification"] == (
        "ohlc_missing_with_trade_activity_cause_unverified"
    )


def test_collect_cli_fails_when_only_stale_trading_date_exists_before_period(
    tmp_path: Path,
) -> None:
    source_db_path = tmp_path / "twstock.db"
    sidecar_db_path = tmp_path / "weekly-collection-sidecar.sqlite"
    _create_source_database(source_db_path)

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source-db-path",
            str(source_db_path),
            "--sidecar-db-path",
            str(sidecar_db_path),
            "--output-root",
            str(tmp_path / "output"),
            "--period-end",
            "2026-07-08",
            "--json-output",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["collection_status"] == "collection_failed"
    assert "no daily_prices trading date inside 2026-07-06..2026-07-08" in payload["error"]["message"]


def test_collect_cli_saves_failed_sidecar_record_for_invalid_period_end(tmp_path: Path) -> None:
    source_db_path = tmp_path / "twstock.db"
    sidecar_db_path = tmp_path / "weekly-collection-sidecar.sqlite"
    _create_source_database(source_db_path)

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source-db-path",
            str(source_db_path),
            "--sidecar-db-path",
            str(sidecar_db_path),
            "--output-root",
            str(tmp_path / "output"),
            "--period-end",
            "not-a-date",
            "--json-output",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["collection_status"] == "collection_failed"
    assert payload["error"]["type"] == "ValueError"
    with sqlite3.connect(sidecar_db_path) as connection:
        row = connection.execute(
            "SELECT status, error_type, error_message FROM evidence_weekly_collections"
        ).fetchone()
    assert row == ("collection_failed", "ValueError", "Invalid isoformat string: 'not-a-date'")


def test_collect_cli_replaces_pending_with_failed_record_when_report_output_is_unwritable(tmp_path: Path) -> None:
    source_db_path = tmp_path / "twstock.db"
    sidecar_db_path = tmp_path / "weekly-collection-sidecar.sqlite"
    output_root = tmp_path / "output-root-file"
    _create_source_database(source_db_path)
    output_root.write_text("not a directory", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source-db-path",
            str(source_db_path),
            "--sidecar-db-path",
            str(sidecar_db_path),
            "--output-root",
            str(output_root),
            "--period-end",
            "2026-07-12",
            "--json-output",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["collection_status"] == "collection_failed"
    assert payload["error"]["type"] == "FileExistsError"
    assert payload["error"]["message"]
    with sqlite3.connect(sidecar_db_path) as connection:
        rows = connection.execute(
            "SELECT status, error_type, error_message FROM evidence_weekly_collections"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "collection_failed"
    assert rows[0][1] == "FileExistsError"
    assert rows[0][2]
