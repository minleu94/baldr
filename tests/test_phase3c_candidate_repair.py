from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from data_module import phase3c_candidate_repair as repair


def _row(stock_code: str, *, foreign_buy: int, custody: str) -> dict[str, object]:
    return {
        "stock_code": stock_code,
        "decision_date": repair.TARGET_DATE,
        "source_version": "twse-official-T86",
        "publication_at": None,
        "first_observed_at": custody,
        "available_at": custody,
        "available_date": None,
        "quality": "degraded",
        "foreign_investor_buy": foreign_buy,
        "foreign_investor_sell": 100,
        "foreign_investor_net": foreign_buy - 100,
        "investment_trust_buy": 20,
        "investment_trust_sell": 10,
        "investment_trust_net": 10,
        "dealer_buy": 5,
        "dealer_sell": 5,
        "dealer_net": 0,
    }


def _capture_item(row: dict[str, object], endpoint: str, available_at: str) -> dict[str, object]:
    values = dict(row)
    values["source_version"] = "twse-T86.v1" if endpoint == "twse:T86" else "tpex-3insti-web.v1"
    values["observed_at"] = available_at
    values["first_observed_at"] = None
    values["available_at"] = None
    return {
        "table": repair.TABLE_NAME,
        "values": values,
        "provenance": {"endpoint_id": endpoint, "payload_sha256": "sha256:test"},
        "available_at": available_at,
        "availability_evidence": "first_observed_only",
    }


def _make_fixture(tmp_path: Path) -> tuple[Path, Path, Path, repair.RepairContract, dict[str, object], dict[str, object]]:
    capture = tmp_path / "capture"
    (capture / "candidate" / "institutional_flows").mkdir(parents=True)
    (capture / "raw" / repair.TARGET_DATE).mkdir(parents=True)
    custody = "2026-09-24T21:38:04.625233+00:00"
    incoming_rows = [
        _capture_item(_row("0001", foreign_buy=200, custody=custody), "twse:T86", custody),
        _capture_item(_row("0002", foreign_buy=300, custody=custody), "tpex:3itrade", custody),
    ]
    candidate_path = capture / "candidate" / "institutional_flows" / f"{repair.TARGET_DATE}.json"
    candidate_path.write_text(json.dumps(incoming_rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    raw_hashes: dict[str, str] = {}
    raw_artifacts: list[dict[str, str]] = []
    for endpoint, filename in (("twse:T86", "twse.json"), ("tpex:3itrade", "tpex.json")):
        raw_path = capture / "raw" / repair.TARGET_DATE / filename
        raw_path.write_bytes(endpoint.encode("ascii"))
        raw_hash = repair._sha256_file(raw_path)
        raw_hashes[endpoint] = raw_hash
        metadata_path = raw_path.with_name(raw_path.name + ".metadata.json")
        metadata_path.write_text(
            json.dumps(
                {
                    "source_id": repair.TABLE_NAME,
                    "endpoint_id": endpoint,
                    "payload_sha256": raw_hash,
                    "requested_date": repair.TARGET_DATE,
                    "http_status": 200,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        raw_artifacts.append(
            {
                "path": str(raw_path.relative_to(capture)),
                "metadata_path": str(metadata_path.relative_to(capture)),
                "sha256": raw_hash,
            }
        )
    manifest = {
        "schema_version": "institutional-credit-flows-candidate-bundle.v1",
        "as_of_date": repair.TARGET_DATE,
        "discovered_sessions": [repair.TARGET_DATE],
        "candidate_only": True,
        "formal_apply_allowed": False,
        "production_scheduler_allowed": False,
        "downstream_eligibility": "none",
        "run_id": "synthetic-repair-test",
        "created_at": custody,
        "sources": [
            {
                "source_id": repair.TABLE_NAME,
                "decision_date": repair.TARGET_DATE,
                "accepted_row_count": 2,
                "availability_evidence": "first_observed_only",
                "candidate_rows_path": str(candidate_path.relative_to(capture)),
                "candidate_rows_sha256": repair._sha256_file(candidate_path),
                "raw_artifacts": raw_artifacts,
            }
        ],
    }
    manifest_path = capture / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    canonical_rows = [repair._canonical_row_from_capture(item) for item in incoming_rows]
    contract = repair.RepairContract(
        manifest_sha256=repair._sha256_file(manifest_path),
        candidate_rows_sha256=repair._sha256_file(candidate_path),
        raw_hashes=raw_hashes,
        semantic_hash=repair._semantic_hash(canonical_rows),
        expected_source_rows=2,
        update_keys=("0001",),
        insert_keys=("0002",),
    )

    candidate_db = tmp_path / "candidate.db"
    formal_db = tmp_path / "formal.db"
    prod_root = tmp_path / "formal-root"
    prod_root.mkdir()
    sqlite = sqlite3.connect(candidate_db)
    sqlite.executescript(
        """
        CREATE TABLE institutional_flows (
          stock_code TEXT NOT NULL, decision_date TEXT NOT NULL, source_version TEXT,
          publication_at TEXT, first_observed_at TEXT, available_at TEXT, available_date TEXT,
          quality TEXT, foreign_investor_buy INTEGER, foreign_investor_sell INTEGER,
          foreign_investor_net INTEGER, investment_trust_buy INTEGER, investment_trust_sell INTEGER,
          investment_trust_net INTEGER, dealer_buy INTEGER, dealer_sell INTEGER, dealer_net INTEGER,
          PRIMARY KEY (stock_code, decision_date)
        );
        CREATE TABLE phase3c_backfill_checkpoints (
          decision_date TEXT NOT NULL, source TEXT NOT NULL, status TEXT, row_count INTEGER,
          fetched_at TEXT, error_message TEXT, PRIMARY KEY (decision_date, source)
        );
        CREATE TABLE phase3c_source_observations (
          source TEXT NOT NULL, decision_date TEXT NOT NULL, observation_hash TEXT NOT NULL,
          observed_at TEXT, row_count INTEGER, observation_mode TEXT, source_versions TEXT,
          first_observed_at_min TEXT, available_at_max TEXT, canonical_payload_json TEXT,
          diagnostic_json TEXT, PRIMARY KEY (source, decision_date, observation_hash)
        );
        CREATE TABLE other_scope (value TEXT NOT NULL);
        """
    )
    old = _row("0001", foreign_buy=100, custody="2026-09-11T11:00:00+00:00")
    sqlite.executemany(
        f"INSERT INTO institutional_flows ({','.join(repair.TABLE_COLUMNS)}) VALUES ({','.join('?' for _ in repair.TABLE_COLUMNS)})",
        [[old[column] for column in repair.TABLE_COLUMNS]],
    )
    sqlite.execute(
        "INSERT INTO phase3c_backfill_checkpoints VALUES (?, ?, ?, ?, ?, ?)",
        (repair.TARGET_DATE, "institutional", "FAILED_RETRYABLE", 0, custody, "conflict"),
    )
    sqlite.execute("INSERT INTO other_scope VALUES ('preserve-me')")
    sqlite.execute(
        "INSERT INTO phase3c_source_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "institutional",
            repair.TARGET_DATE,
            "sha256:observation",
            custody,
            2,
            "canonical",
            "[]",
            custody,
            custody,
            json.dumps({"rows": canonical_rows}, sort_keys=True),
            "{}",
        ),
    )
    sqlite.commit()
    sqlite.close()
    formal_db.write_bytes(b"formal sentinel")
    return manifest_path, candidate_db, prod_root, contract, old, canonical_rows[0]


def test_plan_is_read_only_and_rejects_formal_path(tmp_path: Path) -> None:
    manifest, candidate, prod_root, contract, _old, _new = _make_fixture(tmp_path)
    formal = tmp_path / "formal.db"
    before = candidate.read_bytes()
    result = repair.build_plan(
        capture_manifest=manifest,
        candidate_db=candidate,
        production_data_root=prod_root,
        formal_db=formal,
        receipt_dir=tmp_path / "receipt",
        contract=contract,
    )
    assert result["expected_operations"]["total_count"] == 2
    assert candidate.read_bytes() == before
    with pytest.raises(repair.CandidateRepairError):
        repair.build_plan(
            capture_manifest=manifest,
            candidate_db=formal,
            production_data_root=prod_root,
            formal_db=formal,
            receipt_dir=tmp_path / "bad-receipt",
            contract=contract,
        )


def test_apply_stages_then_rollback_preserves_other_scope(tmp_path: Path) -> None:
    manifest, candidate, prod_root, contract, old, new = _make_fixture(tmp_path)
    formal = tmp_path / "formal.db"
    plan = repair.build_plan(
        capture_manifest=manifest,
        candidate_db=candidate,
        production_data_root=prod_root,
        formal_db=formal,
        receipt_dir=tmp_path / "receipt",
        contract=contract,
    )
    receipt = repair.apply_plan(
        plan_path=Path(plan["plan_path"]),
        confirm=repair.APPLY_CONFIRM_TOKEN,
        production_data_root=prod_root,
        formal_db=formal,
        contract=contract,
    )
    assert receipt["history_rows_count"] == 3
    assert receipt["formal_db_written"] is False
    conn = sqlite3.connect(candidate)
    assert conn.execute("SELECT COUNT(*) FROM institutional_flows").fetchone()[0] == 2
    assert conn.execute("SELECT value FROM other_scope").fetchone()[0] == "preserve-me"
    assert conn.execute("SELECT status FROM phase3c_backfill_checkpoints").fetchone()[0] == "SUCCESS"
    conn.close()
    history_before_capture = repair.read_history_as_of(
        candidate_db=candidate,
        as_of="2026-09-24T05:38:04+08:00",
        stock_code="0001",
    )
    assert history_before_capture[0]["foreign_investor_buy"] == old["foreign_investor_buy"]
    history_after_capture = repair.read_history_as_of(
        candidate_db=candidate,
        as_of="2026-09-25T05:38:05+08:00",
        stock_code="0001",
    )
    assert history_after_capture[0]["foreign_investor_buy"] == new["foreign_investor_buy"]
    repair.rollback_receipt(
        receipt_path=Path(receipt["receipt_path"]),
        confirm=repair.ROLLBACK_CONFIRM_TOKEN,
        production_data_root=prod_root,
        formal_db=formal,
    )
    conn = sqlite3.connect(candidate)
    restored = conn.execute(
        "SELECT foreign_investor_buy, available_at FROM institutional_flows WHERE stock_code='0001'"
    ).fetchone()
    assert restored == (old["foreign_investor_buy"], old["available_at"])
    assert conn.execute("SELECT COUNT(*) FROM institutional_flows WHERE stock_code='0002'").fetchone()[0] == 0
    assert conn.execute("SELECT status FROM phase3c_backfill_checkpoints").fetchone()[0] == "FAILED_RETRYABLE"
    assert conn.execute("SELECT value FROM other_scope").fetchone()[0] == "preserve-me"
    assert conn.execute(
        f"SELECT COUNT(*) FROM {repair.HISTORY_TABLE_NAME}"
    ).fetchone()[0] == 0
    conn.close()
