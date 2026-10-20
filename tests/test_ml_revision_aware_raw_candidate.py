"""Unit and integration tests for Revision-Aware Research Raw Candidate builder."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import gzip
import json
from pathlib import Path
import sqlite3
from typing import Any, Literal, Sequence
from zoneinfo import ZoneInfo
import pytest

from data_module.ml_revision_aware_raw_candidate import (
    REVISION_AWARE_RAW_SCHEMA_VERSION,
    RevisionAwareCandidateError,
    RevisionAwareRawCandidateBuilder,
    RevisionAwareRawRequest,
    _assert_no_float,
    _check_isolation,
)
import data_module.ml_revision_aware_raw_candidate as raw_module
from data_module.ml_research_output_boundary import resolve_ml_research_output_path
from scripts.build_ml_revision_aware_raw_candidate import main as cli_main
from tests.ml_research_test_support import install_test_revision_gate, write_snapshot_context_receipt


def _create_test_sqlite_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE daily_prices (
            證券代號 TEXT NOT NULL,
            日期 TEXT NOT NULL,
            開盤價 TEXT,
            最高價 TEXT,
            最低價 TEXT,
            收盤價 TEXT,
            成交股數 INTEGER,
            成交金額 INTEGER,
            成交筆數 INTEGER,
            PRIMARY KEY (證券代號, 日期)
        )
    """)
    rows = [
        ("2330", "2026-09-28", "980.00", "985.00", "975.00", "982.00", 25000000, 24500000000, 35000),
        ("2330", "2026-09-29", "982.00", "990.00", "980.00", "988.00", 28000000, 27600000000, 40000),
        ("2317", "2026-09-29", "180.00", "185.00", "179.00", "183.50", 15000000, 2750000000, 18000),
    ]
    cur.executemany("INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()


def _create_daily_projection_fixture(custody_dir: Path, *, available_at: str = "2026-09-30T08:07:47.132399Z") -> Path:
    custody_dir.mkdir(parents=True, exist_ok=True)
    obs_path = custody_dir / "observations.jsonl"
    records = [
        {
            "symbol": "2330",
            "source_date": "2026-09-30",
            "source_available_at": available_at,
            "exact_numeric_values": {
                "開盤價": {"value_int": 99000, "scale": 100, "source_token": "990.00"},
                "最高價": {"value_int": 100000, "scale": 100, "source_token": "1000.00"},
                "最低價": {"value_int": 98800, "scale": 100, "source_token": "988.00"},
                "收盤價": {"value_int": 99500, "scale": 100, "source_token": "995.00"},
                "成交股數": {"value_int": 32000000, "scale": 1, "source_token": "32000000"},
            },
            "source_raw_response_sha256": "sha256:" + "a" * 64,
            "source_receipt_sha256": "sha256:" + "b" * 64,
            "source_row_index": 0,
            "venue": "twse",
            "source_values": {"證券代號": "2330", "收盤價": "995.00"},
        }
    ]
    with obs_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    import hashlib
    raw_path = custody_dir / "raw_response.bin"
    receipt_path = custody_dir / "source_receipt.json"
    raw_path.write_bytes(b"official raw source fixture")
    receipt_path.write_bytes(b"official source receipt fixture")
    raw_sha = "sha256:" + hashlib.sha256(raw_path.read_bytes()).hexdigest()
    receipt_sha = "sha256:" + hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    records[0]["source_raw_response_sha256"] = raw_sha
    records[0]["source_receipt_sha256"] = receipt_sha
    with obs_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    obs_sha = hashlib.sha256(obs_path.read_bytes()).hexdigest()
    input_files = {
        name: {"bytes": path.stat().st_size, "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()}
        for name, path in (("raw_response.bin", raw_path), ("source_receipt.json", receipt_path))
    }

    manifest_payload = {
        "schema_version": "ml-daily-source-row-research-projection.v1",
        "source_date": "2026-09-30",
        "observations_file": {"path": "observations.jsonl", "sha256": "sha256:" + obs_sha, "bytes": obs_path.stat().st_size, "row_count": 1},
        "input_files": input_files,
        "research_only": True,
        "formal_credit": False,
        "formal_dataset": False,
    }
    manifest_path = custody_dir / "manifest.json"
    manifest_payload["content_sha256"] = "sha256:" + hashlib.sha256(json.dumps(manifest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    manifest_raw = json.dumps(manifest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest_path.write_bytes(manifest_raw)
    manifest_sha = "sha256:" + hashlib.sha256(manifest_raw).hexdigest()
    (custody_dir / "completion_receipt.json").write_text(json.dumps({
        "schema_version": "ml-daily-source-row-research-completion.v1",
        "completion_status": "awaiting_terminal_revision_validation",
        "manifest_sha256": manifest_sha,
        "observations_sha256": "sha256:" + obs_sha,
    }), encoding="utf-8")
    (custody_dir / "runner_terminal_verification_receipt.json").write_text(json.dumps({
        "schema_version": "ml-daily-source-row-runner-terminal-receipt.v1",
        "terminal_status": "completed_research_only",
        "features_included": False,
        "labels_included": False,
        "historical_pit_eligible": False,
        "projection": {"manifest_sha256": manifest_sha, "observations_sha256": "sha256:" + obs_sha},
    }), encoding="utf-8")
    return manifest_path


def _research_output(tmp_path: Path, *parts: str) -> Path:
    return tmp_path / "output" / "ml_research" / Path(*parts)


def _snapshot_context(db_path: Path, root: Path, *, completed_at: str = "2026-09-30T09:00:00+00:00") -> tuple[Path, str]:
    return write_snapshot_context_receipt(db_path, root, completed_at=completed_at)


def test_snapshot_context_root_level_consistency_shape_is_verified(tmp_path: Path) -> None:
    db_path = tmp_path / "snapshot_shape.sqlite"
    _create_test_sqlite_db(db_path)
    receipt_path, receipt_sha = _snapshot_context(db_path, tmp_path)
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert payload["snapshot_quick_check"] == "ok"
    assert payload["source_and_revision_bytes_unchanged"] is True
    assert "snapshot_quick_check" not in payload["snapshot"]
    assert len(payload["source_observation"]["revision_namespace_files"]) == 4
    assert payload["source_generation_before"] == payload["source_generation_after"] == 2
    req = RevisionAwareRawRequest(
        snapshot_db=db_path,
        output_dir=_research_output(tmp_path, "root_shape_out"),
        custody_dir=_research_output(tmp_path, "root_shape_custody"),
        decision_at="2026-09-30T10:00:00Z",
        years=(2026,),
        snapshot_context_receipt_path=receipt_path,
        expected_snapshot_context_receipt_sha256=receipt_sha,
        now_provider=lambda: datetime.fromisoformat("2026-09-30T10:05:00+00:00"),
    )
    result = RevisionAwareRawCandidateBuilder(req).build()
    assert result.row_count == 3
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_revision_qualification"] == "verified_current_restated_source_context"
    assert manifest["input_pins"]["market_revision"]["cutoff_evaluated"] is True
    assert manifest["data_temporal_semantics"]["historical_pit_eligible"] is False


def test_snapshot_context_rejects_changed_original_namespace_bytes(tmp_path: Path) -> None:
    db_path = tmp_path / "snapshot_namespace.sqlite"
    _create_test_sqlite_db(db_path)
    receipt_path, receipt_sha = _snapshot_context(db_path, tmp_path)
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    namespace_path = Path(
        payload["source_observation"]["revision_namespace_files"][2]["path"]
    )
    namespace_path.write_bytes(b"changed after snapshot pins")
    req = RevisionAwareRawRequest(
        snapshot_db=db_path,
        output_dir=_research_output(tmp_path, "namespace_mismatch_out"),
        custody_dir=_research_output(tmp_path, "namespace_mismatch_custody"),
        decision_at="2026-09-30T10:00:00Z",
        years=(2026,),
        snapshot_context_receipt_path=receipt_path,
        expected_snapshot_context_receipt_sha256=receipt_sha,
        now_provider=lambda: datetime.fromisoformat("2026-09-30T10:05:00+00:00"),
    )
    with pytest.raises(RevisionAwareCandidateError, match="source_context_not_verified"):
        RevisionAwareRawCandidateBuilder(req).build()
    assert not req.output_dir.exists()


@pytest.fixture(autouse=True)
def _research_path_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def resolver(
        path: Path,
        *,
        repository_root: Path | None = None,
        extra_forbidden_roots: Sequence[Path] = (),
        access: Literal["read", "write"] = "read",
    ) -> Path:
        (tmp_path / "output" / "ml_research").mkdir(parents=True, exist_ok=True)
        return resolve_ml_research_output_path(
            path,
            repository_root=repository_root or tmp_path,
            extra_forbidden_roots=extra_forbidden_roots,
            access=access,
        )
    monkeypatch.setattr(raw_module, "resolve_ml_research_output_path", resolver)
    install_test_revision_gate(monkeypatch)


def test_revision_aware_raw_candidate_build_success(tmp_path: Path) -> None:
    db_path = tmp_path / "test_snapshot.sqlite"
    _create_test_sqlite_db(db_path)
    receipt_path, receipt_sha = _snapshot_context(db_path, tmp_path)
    out_dir = _research_output(tmp_path, "research_candidate_out")
    custody_dir = _research_output(tmp_path, "research_candidate_custody")

    req = RevisionAwareRawRequest(
        snapshot_db=db_path,
        output_dir=out_dir,
        custody_dir=custody_dir,
        decision_at="2026-09-30T10:00:00Z",
        history_start_date="2026-01-01",
        years=(2026,),
        snapshot_context_receipt_path=receipt_path,
        expected_snapshot_context_receipt_sha256=receipt_sha,
        now_provider=lambda: datetime.fromisoformat("2026-09-30T10:05:00+00:00"),
    )
    builder = RevisionAwareRawCandidateBuilder(req)
    result = builder.build()

    assert result.status == "completed_research_only"
    assert result.manifest_path.exists()
    assert result.completion_receipt_path is not None
    assert result.completion_receipt_path.exists()
    assert result.row_count == 3
    assert result.shard_count == 1

    # 檢視 manifest 內容
    manifest = json.loads(result.manifest_path.read_bytes().decode("utf-8"))
    assert manifest["schema_version"] == REVISION_AWARE_RAW_SCHEMA_VERSION
    assert manifest["stage"] == "research_raw_candidate"
    assert manifest["safety"]["research_only"] is True
    assert manifest["safety"]["formal_dataset"] is False
    assert manifest["safety"]["formal_credit"] is False
    assert manifest["safety"]["formal_historical_PIT"] is False
    assert manifest["safety"]["formal_oos"] is False
    assert manifest["safety"]["market_revision_cutoff_policy_evaluated"] is True
    assert manifest["safety"]["no_naked_float_persistence"] is True

    # 檢視 shard 內容
    shard_path = out_dir / manifest["shards"][0]["path"]
    assert shard_path.exists()
    with gzip.open(shard_path, "rb") as gz:
        lines = [json.loads(line.decode("utf-8")) for line in gz.readlines()]
    assert len(lines) == 3
    for record in lines:
        assert record["table_name"] == "daily_prices"
        assert record["symbol"] in ("2330", "2317")
        for val in record["values"]:
            assert isinstance(val["value_int"], int)
            assert isinstance(val["scale"], int)


def test_revision_aware_raw_candidate_with_custody_projection(tmp_path: Path) -> None:
    db_path = tmp_path / "test_snapshot.sqlite"
    _create_test_sqlite_db(db_path)

    custody_src_dir = tmp_path / "daily_projection"
    custody_manifest = _create_daily_projection_fixture(custody_src_dir)
    receipt_path, receipt_sha = _snapshot_context(db_path, tmp_path)

    out_dir = _research_output(tmp_path, "merged_candidate_out")
    custody_dir = _research_output(tmp_path, "merged_candidate_custody")

    req = RevisionAwareRawRequest(
        snapshot_db=db_path,
        output_dir=out_dir,
        custody_dir=custody_dir,
        decision_at="2026-09-30T10:00:00Z",
        history_start_date="2026-01-01",
        years=(2026,),
        source_custody_manifests=(custody_manifest,),
        expected_source_manifest_hashes={str(custody_manifest.resolve()): "sha256:" + __import__("hashlib").sha256(custody_manifest.read_bytes()).hexdigest()},
        snapshot_context_receipt_path=receipt_path,
        expected_snapshot_context_receipt_sha256=receipt_sha,
        now_provider=lambda: datetime.fromisoformat("2026-09-30T10:05:00+00:00"),
    )
    builder = RevisionAwareRawCandidateBuilder(req)
    result = builder.build()

    assert result.status == "completed_research_only"
    # 3 from SQLite + 1 from custody projection = 4 rows
    assert result.row_count == 4

    manifest = json.loads(result.manifest_path.read_bytes().decode("utf-8"))
    shard_path = out_dir / manifest["shards"][0]["path"]
    with gzip.open(shard_path, "rb") as gz:
        lines = [json.loads(line.decode("utf-8")) for line in gz.readlines()]
    assert len(lines) == 4
    custody_rows = [r for r in lines if r.get("source_version", {}).get("provider") == "daily_source_row_projection"]
    assert len(custody_rows) == 1
    assert custody_rows[0]["symbol"] == "2330"
    assert custody_rows[0]["available_at"] == "2026-09-30T08:07:47.132399+00:00"


def test_snapshot_sha256_mismatch_fails_closed(tmp_path: Path) -> None:
    db_path = tmp_path / "test_snapshot.sqlite"
    _create_test_sqlite_db(db_path)

    out_dir = _research_output(tmp_path, "mismatch_out")
    custody_dir = _research_output(tmp_path, "mismatch_custody")

    req = RevisionAwareRawRequest(
        snapshot_db=db_path,
        output_dir=out_dir,
        custody_dir=custody_dir,
        decision_at="2026-09-30T10:00:00Z",
        expected_snapshot_sha256="sha256:0000000000000000000000000000000000000000000000000000000000000000",
    )
    builder = RevisionAwareRawCandidateBuilder(req)
    with pytest.raises(RevisionAwareCandidateError, match="snapshot_db sha256 mismatch"):
        builder.build()


def test_lookahead_violation_in_custody_fails_closed(tmp_path: Path) -> None:
    db_path = tmp_path / "test_snapshot.sqlite"
    _create_test_sqlite_db(db_path)

    custody_src_dir = tmp_path / "future_projection"
    manifest_path = _create_daily_projection_fixture(custody_src_dir, available_at="2026-10-02T08:00:00Z")
    receipt_path, receipt_sha = _snapshot_context(db_path, tmp_path)

    req = RevisionAwareRawRequest(
        snapshot_db=db_path,
        output_dir=_research_output(tmp_path, "lookahead_out"),
        custody_dir=_research_output(tmp_path, "lookahead_custody"),
        decision_at="2026-09-30T10:00:00Z",
        source_custody_manifests=(manifest_path,),
        expected_source_manifest_hashes={str(manifest_path.resolve()): "sha256:" + __import__("hashlib").sha256(manifest_path.read_bytes()).hexdigest()},
        snapshot_context_receipt_path=receipt_path,
        expected_snapshot_context_receipt_sha256=receipt_sha,
        now_provider=lambda: datetime.fromisoformat("2026-09-30T10:05:00+00:00"),
    )
    builder = RevisionAwareRawCandidateBuilder(req)
    with pytest.raises(RevisionAwareCandidateError, match="Lookahead violation"):
        builder.build()


def test_isolation_guard_rejects_formal_roots() -> None:
    with pytest.raises(RevisionAwareCandidateError, match="cannot target formal data root"):
        _check_isolation(Path("F:/Min/Python/Project/FA_Data/output"), "test_formal_d")

    with pytest.raises(RevisionAwareCandidateError, match="prohibited formal path"):
        _check_isolation(Path("output/release_v4/target_candidate"), "test_release_v4")


def test_preview_only_mode_does_not_write_shards(tmp_path: Path) -> None:
    db_path = tmp_path / "test_snapshot.sqlite"
    _create_test_sqlite_db(db_path)

    receipt_path, receipt_sha = _snapshot_context(db_path, tmp_path)
    out_dir = _research_output(tmp_path, "preview_out")
    custody_dir = _research_output(tmp_path, "preview_custody")

    req = RevisionAwareRawRequest(
        snapshot_db=db_path,
        output_dir=out_dir,
        custody_dir=custody_dir,
        decision_at="2026-09-30T10:00:00Z",
        preview_only=True,
        snapshot_context_receipt_path=receipt_path,
        expected_snapshot_context_receipt_sha256=receipt_sha,
        now_provider=lambda: datetime.fromisoformat("2026-09-30T10:05:00+00:00"),
    )
    builder = RevisionAwareRawCandidateBuilder(req)
    result = builder.build()

    assert result.status == "preview_only"
    assert not out_dir.exists()


def test_naked_float_rejection() -> None:
    with pytest.raises(RevisionAwareCandidateError, match="naked float detected"):
        _assert_no_float({"price": 12.34}, "test_dict")


def test_cli_execution_success(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = tmp_path / "cli_snapshot.sqlite"
    _create_test_sqlite_db(db_path)

    import hashlib
    from datetime import datetime
    now = datetime.now(timezone.utc)
    context_path, context_sha = _snapshot_context(db_path, tmp_path, completed_at=(now.replace(microsecond=0)).isoformat())
    out_dir = _research_output(tmp_path, "cli_out")
    custody_dir = _research_output(tmp_path, "cli_custody")

    argv = [
        "--snapshot-db", str(db_path),
        "--expected-snapshot-sha256", "sha256:" + hashlib.sha256(db_path.read_bytes()).hexdigest(),
        "--snapshot-context-receipt", str(context_path),
        "--expected-snapshot-context-receipt-sha256", context_sha,
        "--output-dir", str(out_dir),
        "--custody-dir", str(custody_dir),
        "--decision-at", (now.replace(microsecond=0)).isoformat(),
        "--years", "2026",
    ]
    exit_code = cli_main(argv)
    assert exit_code == 0

    captured = capsys.readouterr()
    res = json.loads(captured.out)
    assert res["status"] == "completed_research_only"
    assert res["research_only"] is True
    assert res["candidate_only"] is True
    assert res["formal_credit"] is False
