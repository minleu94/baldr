import json
import hashlib
import sqlite3

from scripts.backfill_tpex_daily_prices import TPEX_AFTER_TRADING_OTC_URL, main


def _create_daily_prices_db(db_file, *, existing=None):
    db_file.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            'CREATE TABLE daily_prices ("日期" TEXT, "證券代號" TEXT, "證券名稱" TEXT, "開盤價" REAL, "最高價" REAL, "最低價" REAL, "收盤價" REAL, "成交股數" INTEGER, PRIMARY KEY ("證券代號", "日期"))'
        )
        if existing is not None:
            conn.execute(
                'INSERT INTO daily_prices ("日期", "證券代號", "證券名稱", "收盤價") VALUES (?, ?, ?, ?)',
                existing,
            )


def _write_after_trading_fixture(
    tmp_path,
    *,
    table_date="115/09/18",
    url=TPEX_AFTER_TRADING_OTC_URL,
    extra_table=False,
    duplicate_quote_table=False,
):
    raw_path = tmp_path / "source.raw.json"
    metadata_path = tmp_path / "capture.json"
    target_table = {
                "date": table_date,
                "fields": [
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
                ],
                "data": [
                    [
                        "1569",
                        "濱川",
                        "52.00",
                        "+1.00",
                        "51.00",
                        "53.00",
                        "50.40",
                        "1000",
                        "52000",
                        "10",
                        "51.90",
                        "3",
                        "52.10",
                        "2",
                        "100000",
                    ],
                    [
                        "00720B",
                        "測試 ETF",
                        "100.00",
                        "0.00",
                        "100.00",
                        "100.00",
                        "100.00",
                        "100",
                        "10000",
                        "1",
                        "100.00",
                        "1",
                        "100.00",
                        "1",
                        "100000",
                    ],
                ],
            }
    tables = [target_table]
    if extra_table:
        tables.insert(0, {"date": table_date, "fields": ["分類"], "data": [["其他"]]})
    if duplicate_quote_table:
        tables.append(target_table)
    payload = {"tables": tables}
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    raw_path.write_bytes(raw)
    metadata_path.write_text(
        json.dumps(
            {
                "source_authority": "tpex",
                "source_id": "tpex.daily_close_quotes",
                "requested_date": "2026-09-18",
                "requested_url": url,
                "final_url": url,
                "request_parameters": {
                    "date": "2026/09/18",
                    "type": "EW",
                    "response": "json",
                },
                "response_headers": {"content-type": "application/json"},
                "http_status": 200,
                "captured_at": "2026-09-18T00:00:00+00:00",
                "raw_response_path": str(raw_path.resolve()),
                "raw_response_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
                "raw_response_bytes": len(raw),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return raw_path, metadata_path


def _precaptured_args(tmp_path, raw_path, metadata_path, *extra):
    data_root = tmp_path / "data"
    output_root = tmp_path / "output"
    db_file = data_root / "sqlite" / "twstock.db"
    backup_dir = data_root / "meta_data" / "backup"
    return [
        "--source-raw",
        str(raw_path),
        "--capture-metadata",
        str(metadata_path),
        "--date",
        "2026-09-18",
        "--required-symbol",
        "1569",
        "--data-root",
        str(data_root),
        "--output-root",
        str(output_root),
        "--db-file",
        str(db_file),
        "--backup-dir",
        str(backup_dir),
        *extra,
    ]


def test_tpex_daily_price_cli_dry_run_does_not_write(tmp_path, capsys):
    db_file = tmp_path / "twstock.db"
    source_json = tmp_path / "tpex.json"
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            'CREATE TABLE daily_prices ("日期" TEXT, "證券代號" TEXT, "證券名稱" TEXT, "收盤價" REAL, PRIMARY KEY ("證券代號", "日期"))'
        )
    source_json.write_text(
        json.dumps(
            [
                {
                    "Date": "1150616",
                    "SecuritiesCompanyCode": "3207",
                    "CompanyName": "耀勝",
                    "Close": "42.50",
                }
            ]
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--db-file",
            str(db_file),
            "--source-json",
            str(source_json),
            "--date",
            "2026-06-16",
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert "ready_for_apply: true" in capsys.readouterr().out
    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT count(*) FROM daily_prices").fetchone()[0] == 0


def test_tpex_daily_price_cli_apply_requires_confirm(tmp_path):
    db_file = tmp_path / "twstock.db"
    source_json = tmp_path / "tpex.json"
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            'CREATE TABLE daily_prices ("日期" TEXT, "證券代號" TEXT, "證券名稱" TEXT, "收盤價" REAL, PRIMARY KEY ("證券代號", "日期"))'
        )
    source_json.write_text(
        json.dumps(
            [
                {
                    "Date": "1150616",
                    "SecuritiesCompanyCode": "3207",
                    "CompanyName": "耀勝",
                    "Close": "42.50",
                }
            ]
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "--db-file",
                str(db_file),
                "--source-json",
                str(source_json),
                "--date",
                "2026-06-16",
                "--apply",
            ]
        )
        == 2
    )


def test_precaptured_after_trading_dry_run_keeps_all_formal_outputs_untouched(
    tmp_path, capsys
):
    raw_path, metadata_path = _write_after_trading_fixture(tmp_path)
    db_file = tmp_path / "data" / "sqlite" / "twstock.db"
    _create_daily_prices_db(db_file)

    exit_code = main(_precaptured_args(tmp_path, raw_path, metadata_path))

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "ready_for_apply: true" in output
    assert "historical_pit_status: not_proven_by_after_close_capture" in output
    assert "strict_diagnostic_count: 1" in output
    assert not (tmp_path / "output" / "scheduled").exists()
    assert not (tmp_path / "data" / "daily_price_tpex" / "20260918.csv").exists()
    assert not (tmp_path / "data" / "meta_data" / "backup").exists()
    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT count(*) FROM daily_prices").fetchone()[0] == 0


def test_precaptured_after_trading_selects_target_quote_table_among_multiple_tables(
    tmp_path, capsys
):
    raw_path, metadata_path = _write_after_trading_fixture(tmp_path, extra_table=True)
    db_file = tmp_path / "data" / "sqlite" / "twstock.db"
    _create_daily_prices_db(db_file)

    assert main(_precaptured_args(tmp_path, raw_path, metadata_path)) == 0
    assert "normalized_row_count: 1" in capsys.readouterr().out


def test_precaptured_after_trading_rejects_ambiguous_quote_tables(tmp_path):
    raw_path, metadata_path = _write_after_trading_fixture(
        tmp_path,
        duplicate_quote_table=True,
    )
    db_file = tmp_path / "data" / "sqlite" / "twstock.db"
    _create_daily_prices_db(db_file)

    assert main(_precaptured_args(tmp_path, raw_path, metadata_path)) == 1
    assert not (tmp_path / "output" / "scheduled").exists()


def test_precaptured_after_trading_apply_captures_csv_and_only_missing_db_rows(tmp_path):
    raw_path, metadata_path = _write_after_trading_fixture(tmp_path)
    db_file = tmp_path / "data" / "sqlite" / "twstock.db"
    _create_daily_prices_db(db_file)

    exit_code = main(
        _precaptured_args(
            tmp_path,
            raw_path,
            metadata_path,
            "--apply",
            "--confirm",
            "apply-tpex-daily-price-backfill",
        )
    )

    assert exit_code == 0
    csv_path = tmp_path / "data" / "daily_price_tpex" / "20260918.csv"
    assert csv_path.exists()
    custody_root = tmp_path / "output" / "scheduled" / "daily_price_source_custody" / "tpex" / "20260918"
    receipts = list(custody_root.glob("*/receipt.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert receipt["historical_pit_status"] == "not_proven_by_after_close_capture"
    assert receipt["formal_source_contract_eligible"] is False
    assert receipt["captured_at"] == "2026-09-18T00:00:00+00:00"
    assert list((tmp_path / "data" / "meta_data" / "backup").glob("*.db"))
    with sqlite3.connect(db_file) as conn:
        assert conn.execute(
            'SELECT "日期", "證券代號", "收盤價" FROM daily_prices'
        ).fetchall() == [("20260918", "1569", 52.0)]


def test_precaptured_after_trading_rejects_different_existing_csv_before_custody(
    tmp_path
):
    raw_path, metadata_path = _write_after_trading_fixture(tmp_path)
    db_file = tmp_path / "data" / "sqlite" / "twstock.db"
    _create_daily_prices_db(db_file)
    csv_path = tmp_path / "data" / "daily_price_tpex" / "20260918.csv"
    csv_path.parent.mkdir(parents=True)
    csv_path.write_text("different\n", encoding="utf-8")

    exit_code = main(
        _precaptured_args(
            tmp_path,
            raw_path,
            metadata_path,
            "--apply",
            "--confirm",
            "apply-tpex-daily-price-backfill",
        )
    )

    assert exit_code == 1
    assert csv_path.read_text(encoding="utf-8") == "different\n"
    assert not (tmp_path / "output" / "scheduled").exists()


def test_precaptured_after_trading_rejects_different_existing_db_row_before_writes(tmp_path):
    raw_path, metadata_path = _write_after_trading_fixture(tmp_path)
    db_file = tmp_path / "data" / "sqlite" / "twstock.db"
    _create_daily_prices_db(
        db_file,
        existing=("20260918", "1569", "濱川", 51.0),
    )

    exit_code = main(
        _precaptured_args(
            tmp_path,
            raw_path,
            metadata_path,
            "--apply",
            "--confirm",
            "apply-tpex-daily-price-backfill",
        )
    )

    assert exit_code == 1
    assert not (tmp_path / "output" / "scheduled").exists()
    assert not (tmp_path / "data" / "daily_price_tpex" / "20260918.csv").exists()
    with sqlite3.connect(db_file) as conn:
        assert conn.execute(
            'SELECT "收盤價" FROM daily_prices WHERE "證券代號" = "1569"'
        ).fetchone() == (51.0,)


def test_precaptured_after_trading_rejects_non_official_provenance_before_writes(tmp_path):
    raw_path, metadata_path = _write_after_trading_fixture(
        tmp_path,
        url="https://example.invalid/www/zh-tw/afterTrading/otc",
    )
    db_file = tmp_path / "data" / "sqlite" / "twstock.db"
    _create_daily_prices_db(db_file)

    assert main(_precaptured_args(tmp_path, raw_path, metadata_path)) == 1
    assert not (tmp_path / "output" / "scheduled").exists()
    assert not (tmp_path / "data" / "daily_price_tpex" / "20260918.csv").exists()


def test_precaptured_after_trading_rejects_payload_date_mismatch_before_writes(tmp_path):
    raw_path, metadata_path = _write_after_trading_fixture(
        tmp_path,
        table_date="115/09/17",
    )
    db_file = tmp_path / "data" / "sqlite" / "twstock.db"
    _create_daily_prices_db(db_file)

    assert main(_precaptured_args(tmp_path, raw_path, metadata_path)) == 1
    assert not (tmp_path / "output" / "scheduled").exists()
