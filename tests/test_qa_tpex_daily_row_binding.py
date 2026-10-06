from __future__ import annotations

from datetime import datetime, timedelta, timezone
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from data_module.official_daily_price_custody import (
    persist_official_daily_price_response,
)
from data_module import qa_tpex_daily_row_binding as row_binding
from data_module.qa_tpex_daily_row_binding import (
    ROW_COLUMNS,
    TpexRowBindingError,
    publish_row_binding_receipt,
    verify_tpex_daily_row_binding,
)
from data_module.tpex_daily_price_backfill import normalize_tpex_daily_price_rows
from data_module.tpex_daily_price_source import _rows_from_after_trading_response
from scripts import qa_validate_tpex_daily_row_binding as cli


SOURCE_DATE = "20260616"
CAPTURED_AT = datetime(2026, 6, 16, 6, 0, tzinfo=timezone.utc)
RUN_ID = "2026-06-16-4321"
FIELDS = [
    "代號",
    "名稱",
    "收盤",
    "漲跌",
    "開盤",
    "最高",
    "最低",
    "成交股數",
    "成交金額",
    "成交筆數",
    "最後買價",
    "最後買量",
    "最後賣價",
    "最後賣量",
    "發行股數",
]


def _sample_payload(symbols: tuple[str, ...] = ("3207",)) -> dict[str, object]:
    values = []
    for index, symbol in enumerate(symbols):
        values.append(
            [
                symbol,
                f"測試{symbol}",
                f"{42 + index}.50",
                "+1.25",
                f"{42 + index}.00",
                f"{43 + index}.00",
                f"{41 + index}.50",
                "1,000",
                "42,500",
                "30",
                "42.45",
                "10",
                "42.55",
                "20",
                "1,000,000",
            ]
        )
    return {
        "tables": [
            {
                "date": "1150616",
                "fields": FIELDS,
                "data": values,
            }
        ]
    }


def _make_fixture(tmp_path: Path, *, symbols: tuple[str, ...] = ("3207",)) -> dict[str, object]:
    qa_root = tmp_path / "qa_run"
    data_root = qa_root / "data"
    output_root = qa_root / "output"
    tpex_dir = data_root / "daily_price_tpex"
    twse_dir = data_root / "daily_price"
    sqlite_dir = data_root / "sqlite"
    for directory in (tpex_dir, twse_dir, sqlite_dir, output_root):
        directory.mkdir(parents=True, exist_ok=True)

    raw_payload = _sample_payload(symbols)
    raw_bytes = json.dumps(raw_payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    source_rows = _rows_from_after_trading_response(raw_payload, fallback_date=SOURCE_DATE)
    normalized_rows = list(
        normalize_tpex_daily_price_rows(
            list(source_rows), fallback_date=SOURCE_DATE, strict=False
        ).rows
    )
    request_url = (
        "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc"
        "?date=2026%2F06%2F16&type=EW&response=json"
    )
    custody = persist_official_daily_price_response(
        output_root=output_root,
        venue="tpex",
        source_id="tpex.daily_close_quotes",
        source_date=SOURCE_DATE,
        requested_url=request_url,
        final_url=request_url,
        request_parameters={
            "date": "2026/06/16",
            "type": "EW",
            "response": "json",
        },
        http_status=200,
        response_headers={"content-type": "application/json"},
        raw_response=raw_bytes,
        captured_at=CAPTURED_AT,
        row_count=len(normalized_rows),
        source_columns=tuple(normalized_rows[0].keys()),
        parser_id="tpex.daily_close_quotes.v1",
        historical_backfill_claimed=False,
    )

    tpex_csv = tpex_dir / f"{SOURCE_DATE}.csv"
    with tpex_csv.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=ROW_COLUMNS)
        writer.writeheader()
        writer.writerows(normalized_rows)
    twse_csv = twse_dir / f"{SOURCE_DATE}.csv"
    with twse_csv.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("日期", "證券代號"))
        writer.writeheader()
        writer.writerow({"日期": SOURCE_DATE, "證券代號": "1101"})

    db_path = sqlite_dir / "twstock.db"
    quoted_columns = ", ".join(f'"{column}" TEXT' for column in ROW_COLUMNS)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            f'CREATE TABLE daily_prices ({quoted_columns}, '
            'PRIMARY KEY ("證券代號", "日期"))'
        )
        insert_columns = ", ".join(f'"{column}"' for column in ROW_COLUMNS)
        placeholders = ", ".join("?" for _ in ROW_COLUMNS)
        connection.executemany(
            f"INSERT INTO daily_prices ({insert_columns}) VALUES ({placeholders})",
            [tuple(row[column] for column in ROW_COLUMNS) for row in normalized_rows],
        )

    terminal_status = {
        "task": "baldr-data-update-quick-daily",
        "status": "passed_with_warnings",
        "run_id": RUN_ID,
        "process_id": 4321,
        "started_at": (CAPTURED_AT - timedelta(minutes=1)).isoformat(),
        "completed_at": (CAPTURED_AT + timedelta(minutes=5)).isoformat(),
        "start_date": "2026-06-16",
        "end_date": "2026-06-16",
        "data_root": str(data_root),
        "output_root": str(output_root),
        "steps": [
            {
                "name": "update_tpex_daily_prices",
                "status": "warning",
                "result": {"success": True, "source_custody": [custody]},
            }
        ],
    }
    status_path = output_root / "scheduled" / "quick" / "terminal_status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps(terminal_status, ensure_ascii=False), encoding="utf-8"
    )
    return {
        "qa_root": qa_root,
        "data_root": data_root,
        "output_root": output_root,
        "db_path": db_path,
        "tpex_csv": tpex_csv,
        "twse_csv": twse_csv,
        "status_path": status_path,
        "status": terminal_status,
        "custody": custody,
        "raw_bytes": raw_bytes,
    }


def _verify(fixture: dict[str, object]) -> dict[str, object]:
    return verify_tpex_daily_row_binding(
        fixture["status"],
        qa_root=fixture["qa_root"],
        data_root=fixture["data_root"],
        output_root=fixture["output_root"],
        database_path=fixture["db_path"],
    )


def test_tpex_raw_csv_and_read_only_sqlite_rows_bind_without_publishing(tmp_path):
    fixture = _make_fixture(tmp_path, symbols=("3207", "6488"))

    result = _verify(fixture)

    assert result["status"] == "verified"
    assert result["purpose"] == "qa_row_binding_only"
    assert result["formal_pit_proof"] is False
    assert result["ready_for_daily_pipeline"] is False
    assert result["date_count"] == 1
    assert result["row_count"] == 2
    assert [row["stock_code"] for row in result["dates"][0]["rows"]] == ["3207", "6488"]
    assert not (Path(fixture["output_root"]) / "scheduled" / "tpex_daily_price_row_binding").exists()


def test_missing_current_run_identity_or_capture_time_fails_closed(tmp_path):
    fixture = _make_fixture(tmp_path)
    fixture["status"].pop("run_id")
    with pytest.raises(TpexRowBindingError, match="quick_run_id_missing"):
        _verify(fixture)

    fixture = _make_fixture(tmp_path / "second")
    fixture["status"]["started_at"] = "2026-06-16T06:01:00+00:00"
    with pytest.raises(TpexRowBindingError, match="not_observed_during_current_run"):
        _verify(fixture)


def test_raw_hash_and_csv_row_mismatch_fail_closed(tmp_path):
    fixture = _make_fixture(tmp_path)
    raw_path = Path(fixture["custody"]["raw_response_path"])
    raw_path.write_bytes(fixture["raw_bytes"] + b" ")
    with pytest.raises(TpexRowBindingError, match="raw_response_hash_mismatch"):
        _verify(fixture)

    fixture = _make_fixture(tmp_path / "second")
    with fixture["tpex_csv"].open("a", encoding="utf-8", newline="") as stream:
        stream.write("\n")
    # Trailing blank lines do not change parsed rows; alter a value to exercise row binding.
    text = fixture["tpex_csv"].read_text(encoding="utf-8-sig")
    text = text.replace("42.50", "41.50")
    fixture["tpex_csv"].write_text(text, encoding="utf-8-sig")
    with pytest.raises(TpexRowBindingError, match="tpex_csv_row_differs_from_raw"):
        _verify(fixture)


def test_database_value_mismatch_and_twse_tpex_collision_fail_closed(tmp_path):
    fixture = _make_fixture(tmp_path)
    with sqlite3.connect(fixture["db_path"]) as connection:
        connection.execute(
            'UPDATE daily_prices SET "收盤價" = ? WHERE "證券代號" = ? AND "日期" = ?',
            ("40.00", "3207", SOURCE_DATE),
        )
    with pytest.raises(TpexRowBindingError, match="daily_prices_row_differs_from_raw"):
        _verify(fixture)

    fixture = _make_fixture(tmp_path / "second")
    with fixture["twse_csv"].open("a", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("日期", "證券代號"))
        writer.writerow({"日期": SOURCE_DATE, "證券代號": "3207"})
    with pytest.raises(TpexRowBindingError, match="twse_tpex_natural_key_collision"):
        _verify(fixture)


def test_cli_pins_explicit_run_and_publishes_success_receipt_create_only(
    tmp_path, monkeypatch, capsys
):
    fixture = _make_fixture(tmp_path)
    monkeypatch.setattr(cli, "QA_PARENT", tmp_path)
    monkeypatch.setattr(row_binding, "QA_PARENT", tmp_path)
    argv = [
        "--qa-root",
        str(fixture["qa_root"]),
        "--terminal-status",
        str(fixture["status_path"]),
        "--expected-run-id",
        RUN_ID,
    ]

    wrong_pin = list(argv)
    wrong_pin[-1] = "other-run"
    assert cli.main(wrong_pin) == 2
    capsys.readouterr()
    assert not (
        Path(fixture["output_root"])
        / "scheduled"
        / "tpex_daily_price_row_binding"
    ).exists()

    assert cli.main(argv) == 0
    response = json.loads(capsys.readouterr().out)
    receipt_path = Path(response["receipt_path"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "verified"
    assert receipt["quick_run"]["run_id"] == RUN_ID
    assert receipt["quick_run"]["terminal_status_sha256"] == (
        "sha256:" + hashlib.sha256(Path(fixture["status_path"]).read_bytes()).hexdigest()
    )
    assert receipt["ready_for_daily_pipeline"] is False
    original_receipt = receipt_path.read_bytes()

    assert cli.main(argv) == 2
    capsys.readouterr()
    assert receipt_path.read_bytes() == original_receipt


def test_cli_requires_an_explicit_run_id_pin(tmp_path):
    with pytest.raises(SystemExit) as exc_info:
        cli._build_parser().parse_args(["--qa-root", str(tmp_path), "--terminal-status", "status.json"])
    assert exc_info.value.code == 2


def test_cli_entrypoint_help_runs_from_repository_root():
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "qa_validate_tpex_daily_row_binding.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0
    assert "--expected-run-id" in completed.stdout
