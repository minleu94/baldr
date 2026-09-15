from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3

from data_module.official_daily_price_custody import (
    persist_official_daily_price_response,
)
from data_module.recommendation_calibration_source_contract import (
    _cost_lanes,
    _hash_file,
    _hash_payload,
    build_technical_computation_evidence,
    capture_technical_input_snapshot,
    inspect_source_contract,
    publish_technical_indicator_receipt,
)


def _source_db(path, symbols=("1101", "2330")):
    connection = sqlite3.connect(path)
    connection.execute(
        'CREATE TABLE daily_prices ("日期" TEXT, "證券代號" TEXT, "收盤價" REAL)'
    )
    connection.execute(
        'CREATE TABLE technical_indicators ("日期" TEXT, "證券代號" TEXT, "RSI" TEXT, "MACD" TEXT, "ADX" TEXT)'
    )
    for symbol in symbols:
        connection.execute(
            'INSERT INTO daily_prices VALUES (?, ?, ?)',
            ("2026-09-14", symbol, 100.0),
        )
        connection.execute(
            'INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?)',
            ("2026-09-14", symbol, "55", "1.5", "20"),
        )
    connection.commit()
    connection.close()


def test_technical_computation_evidence_binds_precalculation_input_and_output(tmp_path):
    source_db = tmp_path / "source.db"
    _source_db(source_db, symbols=("1101",))

    input_snapshot = capture_technical_input_snapshot(source_db)
    assert input_snapshot["verified"] is True
    assert input_snapshot["row_count"] == 1

    evidence = build_technical_computation_evidence(
        source_db=source_db,
        calculation_result={"success": True, "updated_stocks": ["1101"]},
        source_date_start="2026-09-14",
        source_date_end="2026-09-14",
        started_at="2026-09-14T05:00:00+00:00",
        completed_at="2026-09-14T05:01:00+00:00",
        input_snapshot=input_snapshot,
    )

    evidence_hash = evidence["evidence_sha256"]
    assert isinstance(evidence_hash, str)
    assert evidence_hash == _hash_payload(
        {key: value for key, value in evidence.items() if key != "evidence_sha256"}
    )
    assert evidence["output_snapshot"]["row_count"] == 1
    assert evidence["output_snapshot"]["symbols"] == ["1101"]


def test_passed_technical_step_without_recomputation_witness_is_blocked(tmp_path):
    source_db = tmp_path / "source.db"
    _source_db(source_db, symbols=("1101",))
    root = tmp_path / "output"
    receipt = _daily_capture(
        root,
        captured_at=datetime(2026, 9, 14, 5, 0, tzinfo=timezone.utc),
        symbols=("1101",),
    )

    publication = publish_technical_indicator_receipt(
        output_root=root,
        source_db=source_db,
        update_status={
            "status": "passed",
            "run_id": "missing-witness",
            "completed_at": "2026-09-14T05:05:00+00:00",
            "steps": [
                {
                    "name": "calculate_technical_indicators",
                    "status": "passed",
                    "result": {"success": True, "source_custody": receipt},
                }
            ],
        },
    )

    assert publication == {
        "status": "blocked",
        "reason": "technical_computation_evidence_missing",
        "technical_output": publication["technical_output"],
        "source_receipt_count": 1,
    }


def test_technical_value_replacement_after_calculation_is_blocked(tmp_path):
    source_db = tmp_path / "source.db"
    _source_db(source_db, symbols=("1101", "2330"))
    root = tmp_path / "output"
    receipt = _daily_capture(
        root,
        captured_at=datetime(2026, 9, 14, 5, 0, tzinfo=timezone.utc),
        symbols=("1101", "2330"),
    )
    computation = build_technical_computation_evidence(
        source_db=source_db,
        calculation_result={"success": True, "updated_stocks": ["1101", "2330"]},
        source_date_start="2026-09-14",
        source_date_end="2026-09-14",
        started_at="2026-09-14T05:00:00+00:00",
        completed_at="2026-09-14T05:01:00+00:00",
        input_snapshot=capture_technical_input_snapshot(source_db),
    )
    with sqlite3.connect(source_db) as connection:
        connection.execute(
            'UPDATE technical_indicators SET "RSI" = ? WHERE "日期" = ? AND "證券代號" = ?',
            (99, "2026-09-14", "1101"),
        )
        connection.commit()

    publication = publish_technical_indicator_receipt(
        output_root=root,
        source_db=source_db,
        update_status={
            "status": "passed",
            "run_id": "tampered-output",
            "completed_at": "2026-09-14T05:05:00+00:00",
            "steps": [
                {
                    "name": "calculate_technical_indicators",
                    "status": "passed",
                    "result": {
                        "success": True,
                        "source_custody": receipt,
                        "technical_computation": computation,
                    },
                }
            ],
        },
    )

    assert publication["status"] == "blocked"
    assert publication["reason"] in {
        "technical_output_content_binding_invalid",
        "technical_output_value_binding_invalid",
    }


def test_cost_metadata_false_or_prose_does_not_create_observed_fill_lineage(tmp_path):
    source_db = tmp_path / "cost.db"
    with sqlite3.connect(source_db) as connection:
        connection.executescript(
            """
            CREATE TABLE evidence_events (event_id TEXT PRIMARY KEY);
            CREATE TABLE evidence_outcomes (
                outcome_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                liquidity_cost_bp INTEGER,
                outcome_status TEXT NOT NULL,
                metadata_json TEXT
            );
            """
        )
        connection.executemany(
            "INSERT INTO evidence_events(event_id) VALUES (?)",
            [("event-1",), ("event-2",), ("event-3",), ("event-4",)],
        )
        connection.executemany(
            """
            INSERT INTO evidence_outcomes(
                outcome_id, event_id, liquidity_cost_bp, outcome_status, metadata_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("outcome-1", "event-1", 20, "ready", '{"actual_fill": false}'),
                ("outcome-2", "event-2", 20, "ready", 'no actual_fill or broker_execution'),
                ("outcome-3", "event-3", 20, "ready", '{"note":"actual_fill observed"}'),
                (
                    "outcome-4",
                    "event-4",
                    20,
                    "ready",
                    '{"actual_fill_lineage":{"fill_id":"f-4"}}',
                ),
            ],
        )
        connection.commit()

    lanes = _cost_lanes(
        source_db=source_db,
        output_root=tmp_path / "output",
        estimated_cost_bp=50,
    )
    observed = lanes["observed"]
    assert observed["ready_rows"] == 4
    assert observed["actual_fill_lineage_rows"] == 0
    assert observed["unverified_structured_lineage_rows"] == 1
    assert observed["verified"] is False
    assert observed["eligible"] is False


def _daily_capture(root, *, captured_at: datetime, symbols=("1101", "2330")):
    raw = json.dumps(
        {
            "tables": [
                {
                    "fields": ["證券代號", "收盤價"],
                    "data": [[symbol, "100"] for symbol in symbols],
                }
            ]
        },
        ensure_ascii=False,
    ).encode("utf-8")
    return persist_official_daily_price_response(
        output_root=root,
        venue="twse",
        source_id="twse.mi_index.daily_price",
        source_date="2026-09-14",
        requested_url="https://www.twse.com.tw/exchangeReport/MI_INDEX",
        final_url="https://www.twse.com.tw/exchangeReport/MI_INDEX",
        request_parameters={"response": "json", "date": "20260914"},
        http_status=200,
        response_headers={"Content-Type": "application/json"},
        raw_response=raw,
        captured_at=captured_at,
        row_count=len(symbols),
        source_columns=("證券代號", "收盤價"),
        parser_id="test.v1",
    )


def _publish_technical(root, source_db, receipt):
    algorithm_path = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "analysis_module"
        / "technical_analysis"
        / "technical_indicators.py"
    )
    computation = build_technical_computation_evidence(
        source_db=source_db,
        calculation_result={"success": True, "updated_stocks": ["1101", "2330"]},
        source_date_start="2026-09-14",
        source_date_end="2026-09-14",
        started_at="2026-09-14T05:00:00+00:00",
        completed_at="2026-09-14T05:05:00+00:00",
        input_snapshot=capture_technical_input_snapshot(source_db),
    )
    return publish_technical_indicator_receipt(
        output_root=root,
        source_db=source_db,
        update_status={
            "status": "passed",
            "run_id": "test-run",
            "completed_at": "2026-09-14T05:05:00+00:00",
            "steps": [
                {
                    "name": "calculate_technical_indicators",
                    "status": "passed",
                    "result": {
                        "success": True,
                        "source_custody": receipt,
                        "technical_computation": computation,
                    },
                }
            ],
        },
    )


def test_partial_source_coverage_does_not_make_prospective_lane_ready(tmp_path):
    source_db = tmp_path / "source.db"
    _source_db(source_db)
    root = tmp_path / "output"
    receipt = _daily_capture(
        root,
        captured_at=datetime(2026, 9, 14, 5, 0, tzinfo=timezone.utc),
        symbols=("1101",),
    )
    publication = _publish_technical(root, source_db, receipt)
    assert publication["status"] == "published"

    audit = inspect_source_contract(
        data_root=tmp_path / "data",
        output_root=root,
        source_db=source_db,
        decision_date=date(2026, 9, 14),
        symbols=("1101", "2330"),
    )
    assert audit["technical"]["prospective_available"] is False
    assert "daily_source_symbol_coverage_missing:2330" in audit["technical"]["prospective_blockers"]
    assert audit["lanes"]["price_up_calibration"]["prospective_status"] == "blocked"


def test_late_or_tampered_daily_receipt_cannot_satisfy_cutoff(tmp_path):
    source_db = tmp_path / "source.db"
    _source_db(source_db, symbols=("1101",))
    root = tmp_path / "output"
    receipt = _daily_capture(
        root,
        captured_at=datetime(2026, 9, 15, 5, 0, tzinfo=timezone.utc),
        symbols=("1101",),
    )
    _publish_technical(root, source_db, receipt)

    late_audit = inspect_source_contract(
        data_root=tmp_path / "data",
        output_root=root,
        source_db=source_db,
        decision_date=date(2026, 9, 14),
        symbols=("1101",),
        availability_cutoff_at=datetime(2026, 9, 15, 4, 59, tzinfo=timezone.utc),
    )
    assert late_audit["technical"]["prospective_available"] is False
    assert late_audit["technical"]["inventory"]["late_daily_source_receipt_count"] == 1

    raw_path = receipt["raw_response_path"]
    with open(raw_path, "wb") as stream:
        stream.write(b"tampered")
    tampered_audit = inspect_source_contract(
        data_root=tmp_path / "data",
        output_root=root,
        source_db=source_db,
        decision_date=date(2026, 9, 15),
        symbols=("1101",),
        availability_cutoff_at=datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc),
    )
    assert tampered_audit["technical"]["prospective_available"] is False
    assert "technical_source_receipt_lineage_unverified" in tampered_audit["technical"]["prospective_blockers"]


def test_three_consecutive_technical_cache_hits_publish_verifiable_skip_receipts(tmp_path):
    """A currentity skip remains a skip while preserving source lineage for features."""

    source_db = tmp_path / "cache-hit-source.db"
    source_dates = ("2026-09-08", "2026-09-09", "2026-09-10")
    symbols = ("1101", "2330")
    with sqlite3.connect(source_db) as connection:
        connection.executescript(
            """
            CREATE TABLE daily_prices ("日期" TEXT, "證券代號" TEXT, "收盤價" REAL);
            CREATE TABLE technical_indicators (
                "日期" TEXT, "證券代號" TEXT, "RSI" TEXT, "MACD" TEXT, "ADX" TEXT
            );
            """
        )
        for source_date in source_dates:
            for symbol in symbols:
                connection.execute(
                    'INSERT INTO daily_prices VALUES (?, ?, ?)',
                    (source_date, symbol, 100.0),
                )
                connection.execute(
                    'INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?)',
                    (source_date, symbol, "55", "1.5", "20"),
                )

    output_root = tmp_path / "output"
    raw = json.dumps(
        {
            "tables": [
                {
                    "fields": ["證券代號", "收盤價"],
                    "data": [[symbol, "100"] for symbol in symbols],
                }
            ]
        },
        ensure_ascii=False,
    ).encode("utf-8")
    publications = []
    for source_date in source_dates:
        for venue, source_id in (
            ("twse", "twse.mi_index.daily_price"),
            ("tpex", "tpex.daily_close_quotes"),
        ):
            persist_official_daily_price_response(
                output_root=output_root,
                venue=venue,
                source_id=source_id,
                source_date=source_date,
                requested_url=f"https://fixture.invalid/{venue}",
                final_url=f"https://fixture.invalid/{venue}",
                request_parameters={"date": source_date.replace("-", "")},
                http_status=200,
                response_headers={"Content-Type": "application/json"},
                raw_response=raw,
                captured_at=datetime.fromisoformat(source_date + "T06:00:00+00:00"),
                row_count=len(symbols),
                source_columns=("證券代號", "收盤價"),
                parser_id="cache-hit-fixture.v1",
            )
        publication = publish_technical_indicator_receipt(
            output_root=output_root,
            source_db=source_db,
            update_status={
                "status": "passed",
                "run_id": "cache-hit-" + source_date,
                "start_date": source_date,
                "end_date": source_date,
                "completed_at": source_date + "T08:00:00+00:00",
                "steps": [
                    {
                        "name": "calculate_technical_indicators",
                        "status": "skipped",
                        "result": {
                            "success": True,
                            "skipped": True,
                            "skip_reason": "technical_indicators_current",
                        },
                    }
                ],
            },
        )
        assert publication["status"] == "published"
        receipt_path = Path(str(publication["receipt_path"]))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        assert receipt["technical_step_status"] == "skipped"
        assert receipt["availability_basis"] == "technical_currentity_check_completed"
        assert receipt["technical_computation_evidence_status"] == "not_run_currentity_skip"
        assert receipt["technical_computation_evidence"] is None
        technical_output = receipt["technical_output"]
        assert technical_output["verified"] is True
        assert technical_output["actual_date_start"] == source_date
        assert technical_output["actual_date_end"] == source_date
        assert technical_output["row_count"] == len(symbols)
        assert len(receipt["source_receipts"]) == 2
        assert {
            item["source_date"] for item in receipt["source_receipts"]
        } == {source_date}
        for reference in receipt["source_receipts"]:
            reference_path = Path(reference["receipt_path"])
            assert reference_path.is_file()
            assert _hash_file(reference_path) == reference["receipt_sha256"]
        publications.append(receipt_path)

    assert len(publications) == 3
    assert len({path.read_text(encoding="utf-8") for path in publications}) == 3
