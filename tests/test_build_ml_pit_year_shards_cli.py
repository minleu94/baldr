from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from typing import Any

import pytest

from data_module import excluded_daily_price_revision, formal_market_revision, historical_session_revision
from data_module.contracts.source_revision import (
    SOURCE_REVISION_EVIDENCE_SCHEMA_V1,
    SOURCE_EVIDENCE_NAMESPACE_ORDER_V1,
)
from data_module.ml_daily_price_revision_gate import (
    VerifiedCurrentRestatedSourceContext,
    VerifiedRevisionDependencyV1,
    VerifiedRevisionNamespaceFileV1,
)
from data_module import ml_pit_year_shard_exporter as exporter_module
from tests.fixtures.portfolio_ml_ooc_support import run_synthetic_ml_cli


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "build_ml_pit_year_shards.py"


def _database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE daily_prices (
                日期 TEXT,
                證券代號 TEXT,
                成交股數 INTEGER,
                收盤價 TEXT
            );
            INSERT INTO daily_prices VALUES
                ('20240102', '2330', 1000, '100.25'),
                ('20240102', '2317', 2000, '50.50');
            """
        )


def _run(database: Path, output: Path, *universe: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    return run_synthetic_ml_cli(
        [
            sys.executable,
            str(SCRIPT),
            "--database",
            str(database),
            "--output-dir",
            str(output),
            "--decision-at",
            "2024-01-03",
            "--history-start-date",
            "2024-01-01",
            *universe,
            "--years",
            "2024",
            "--batch-size",
            "1",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_cli_supports_bounded_symbols_and_emits_raw_stage_manifest(
    tmp_path: Path,
) -> None:
    database = tmp_path / "source.db"
    _database(database)
    result = _run(database, tmp_path / "out", "--symbols", "2330")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["sqlite_mode"] == "ro"
    assert payload["query_only"] is True
    assert payload["parquet_dependency_added"] is False
    assert payload["dataset_manifest_paths"]
    assert all(
        Path(manifest_path).is_file()
        for manifest_path in payload["dataset_manifest_paths"].values()
    )
    manifest = json.loads(
        Path(payload["manifest_path"]).read_text(encoding="utf-8")
    )
    assert manifest["stage"] == "raw_pit_observations"
    assert manifest["training_adapter"]["direct_training_input"] is False
    assert (
        manifest["training_adapter"]["target_schema_version"]
        == "allocation-training-input-v1"
    )
    assert manifest["scope"]["symbols"] == ["2330"]


def test_cli_requires_explicit_bounded_or_all_universe(tmp_path: Path) -> None:
    database = tmp_path / "source.db"
    _database(database)
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--database",
            str(database),
            "--output-dir",
            str(tmp_path / "out"),
            "--decision-at",
            "2024-01-03",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 2
    assert "--symbols" in result.stderr
    assert "--all-universe" in result.stderr


def test_cli_supports_explicit_all_universe(tmp_path: Path) -> None:
    database = tmp_path / "source.db"
    _database(database)
    result = _run(database, tmp_path / "out", "--all-universe")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    manifest = json.loads(
        Path(payload["manifest_path"]).read_text(encoding="utf-8")
    )
    assert manifest["scope"]["all_universe"] is True
    assert manifest["scope"]["symbols"] is None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pinned_file(path: Path) -> VerifiedRevisionNamespaceFileV1:
    info = path.stat()
    return VerifiedRevisionNamespaceFileV1(
        path=str(path.resolve()),
        bytes=info.st_size,
        mtime_ns=info.st_mtime_ns,
        sha256=_sha256(path),
    )


def _current_restated_test_context(
    root: Path,
    snapshot: Path,
    source: Path,
    *,
    decision_at: datetime,
    data_selection_as_of: datetime,
) -> VerifiedCurrentRestatedSourceContext:
    source_wal = source.with_name(source.name + "-wal")
    source_wal.write_bytes(b"")
    receipt_path = root / "snapshot_receipt.json"
    receipt_path.write_text("{}", encoding="utf-8")
    namespace_roots = {
        "daily_price_repair_receipt": root / "output" / "scheduled" / "daily_price_repair_receipts" / "20260520" / "historical_price_spike_20260921",
        "market_revision": root / formal_market_revision.RECEIPT_DIR,
        "historical_session_revision": root / historical_session_revision.RECEIPT_DIR,
        "excluded_daily_price_revision": root / excluded_daily_price_revision.RECEIPT_DIR,
    }
    namespace_files: list[VerifiedRevisionNamespaceFileV1] = []
    evidence_files: list[tuple[str, str, str]] = []
    for namespace in SOURCE_EVIDENCE_NAMESPACE_ORDER_V1:
        namespace_root = namespace_roots[namespace.value]
        namespace_root.mkdir(parents=True, exist_ok=True)
        evidence_path = namespace_root / "evidence.json"
        evidence_path.write_text(namespace.value, encoding="ascii")
        pin = _pinned_file(evidence_path)
        namespace_files.append(pin)
        evidence_files.append((namespace.value, "evidence", pin.sha256))
    source_observed_at = decision_at - timedelta(minutes=4)
    dependency_verified_at = decision_at - timedelta(minutes=2)
    excluded_path = Path(namespace_files[2].path)
    excluded_info = excluded_path.stat()
    dependency = VerifiedRevisionDependencyV1(
        namespace="excluded_daily_price_revision",
        role_id="evidence",
        path=str(excluded_path),
        bytes=excluded_info.st_size,
        mtime_ns=excluded_info.st_mtime_ns,
        sha256=_sha256(excluded_path),
        captured_at=dependency_verified_at,
    )
    return VerifiedCurrentRestatedSourceContext(
        source_database_path=str(source.resolve()),
        source_database_sha256="sha256:" + _sha256(source),
        source_wal_path=str(source_wal.resolve()),
        source_wal_sha256="sha256:" + _sha256(source_wal),
        snapshot_database_path=str(snapshot.resolve()),
        snapshot_database_sha256="sha256:" + _sha256(snapshot),
        snapshot_receipt_path=str(receipt_path.resolve()),
        snapshot_receipt_sha256="sha256:" + _sha256(receipt_path),
        decision_at=decision_at,
        training_as_of=data_selection_as_of,
        source_observed_at=source_observed_at,
        source_generation=2,
        revision_namespace_files=tuple(namespace_files),
        revision_namespace_bundle_sha256="sha256:" + hashlib.sha256(
            "".join(item.sha256 for item in namespace_files).encode("ascii")
        ).hexdigest(),
        source_revision_evidence_schema_version=SOURCE_REVISION_EVIDENCE_SCHEMA_V1,
        source_revision_evidence_scope_id="current-restated-cli-test",
        source_revision_evidence_cutoff_date=decision_at.date().isoformat(),
        source_revision_evidence_sha256="sha256:" + hashlib.sha256(b"test evidence").hexdigest(),
        source_revision_evidence_namespaces=tuple(
            item.value for item in SOURCE_EVIDENCE_NAMESPACE_ORDER_V1
        ),
        source_revision_evidence_files=tuple(evidence_files),
        revision_dependencies_verified_at=dependency_verified_at,
        revision_dependency_files=(dependency,),
        revision_dependency_bundle_sha256="sha256:" + hashlib.sha256(b"test dependency").hexdigest(),
    )


def _current_restated_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE daily_prices (
                日期 TEXT NOT NULL,
                證券代號 TEXT NOT NULL,
                證券名稱 TEXT,
                成交股數 INTEGER,
                開盤價 TEXT,
                最高價 TEXT,
                最低價 TEXT,
                收盤價 TEXT
            );
            CREATE TABLE technical_indicators (
                日期 TEXT NOT NULL,
                證券代號 TEXT NOT NULL,
                ATR TEXT,
                ADX TEXT
            );
            CREATE TABLE market_indices (
                日期 TEXT NOT NULL,
                指數名稱 TEXT NOT NULL,
                開盤價 TEXT,
                最高價 TEXT,
                最低價 TEXT,
                收盤指數 TEXT
            );
            """
        )
        rows: list[tuple[str, str, str, int, str, str, str, str]] = []
        technical: list[tuple[str, str, str, str]] = []
        market: list[tuple[str, str, str, str, str, str]] = []
        current = date(2024, 1, 1)
        index = 0
        while index < 35:
            if current.weekday() < 5:
                day = current.strftime("%Y%m%d")
                close = 100 + index
                for symbol, name, offset in (("2330", "台積電", 0), ("2317", "鴻海", 20)):
                    open_value = close + offset
                    rows.append(
                        (day, symbol, name, 1_000 + index, str(open_value), str(open_value + 2), str(open_value - 2), str(open_value + 1))
                    )
                    technical.append((day, symbol, "1.25", "22.50"))
                market_open = 20_000 + index
                market.append((day, "TAIEX", str(market_open), str(market_open + 20), str(market_open - 20), str(market_open + 10)))
                index += 1
            current += timedelta(days=1)
        connection.executemany("INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        connection.executemany("INSERT INTO technical_indicators VALUES (?, ?, ?, ?)", technical)
        connection.executemany("INSERT INTO market_indices VALUES (?, ?, ?, ?, ?, ?)", market)


@pytest.mark.usefixtures("synthetic_ml_capacity")
def test_cli_current_restated_context_runs_aware_event_year_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import build_ml_pit_year_shards as cli_module

    source = tmp_path / "source" / "twstock.db"
    source.parent.mkdir(parents=True)
    _current_restated_database(source)
    snapshot = tmp_path / "snapshot" / "twstock.db"
    snapshot.parent.mkdir(parents=True)
    shutil.copyfile(source, snapshot)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    decision_at = now - timedelta(minutes=1)
    selection_as_of = now - timedelta(seconds=30)
    context = _current_restated_test_context(
        tmp_path,
        snapshot,
        source,
        decision_at=decision_at,
        data_selection_as_of=selection_as_of,
    )
    output = tmp_path / "output" / "ml_research" / "current-restated-cli"
    receipt = Path(context.snapshot_receipt_path)
    monkeypatch.setattr(
        cli_module,
        "load_verified_current_restated_source_context",
        lambda *args, **kwargs: context,
    )
    monkeypatch.setattr(
        exporter_module,
        "resolve_ml_research_output_path",
        lambda path: Path(path),
    )
    result = cli_module.main(
        [
            "--database", str(snapshot),
            "--output-dir", str(output),
            "--decision-at", decision_at.isoformat(),
            "--history-start-date", "2024-01-01",
            "--symbols", "2330", "2317",
            "--years", "2024",
            "--current-restated-research",
            "--snapshot-database", str(snapshot),
            "--snapshot-receipt", str(receipt),
            "--expected-snapshot-database-sha256", _sha256(snapshot),
            "--expected-snapshot-receipt-sha256", _sha256(receipt),
            "--original-source-database", str(source),
            "--data-selection-as-of", selection_as_of.isoformat(),
            "--batch-size", "32",
            "--temporary-storage-budget-bytes", str(64 * 1024**2),
            "--persistent-storage-budget-bytes", str(64 * 1024**2),
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    publication = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))
    core_manifest_path = (
        Path(payload["manifest_path"]).parent
        / "core_long_history"
        / "manifest.json"
    )
    dataset = json.loads(core_manifest_path.read_text(encoding="utf-8"))
    assert payload["dataset_manifest_paths"] == {
        "core_long_history": str(core_manifest_path)
    }
    assert all(
        Path(manifest_path).is_file()
        for manifest_path in payload["dataset_manifest_paths"].values()
    )
    assert publication["data_temporality"] == "current_restated_research"
    assert publication["source_context"]["snapshot_database_sha256"] == "sha256:" + _sha256(snapshot)
    assert dataset["partition_basis"] == "event_date_calendar_year"
    assert dataset["requested_years"] == [2024]
    assert dataset["safety"]["formal_training_allowed"] is False
    assert dataset["training_adapter"]["historical_pit_eligible"] is False
