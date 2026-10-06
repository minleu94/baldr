"""R004 tmp_path-only characterization for legacy recommendation persistence."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
from threading import Barrier
from typing import Any

import pytest

import app_module.recommendation_repository as repository_module
from app_module.dtos import RecommendationDTO, RecommendationResultDTO
from app_module.recommendation_repository import (
    RecommendationRepository,
    _make_json_serializable,
)


class _TmpConfig:
    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root

    def resolve_output_path(self, subfolder: str) -> Path:
        path = self.output_root / subfolder
        path.mkdir(parents=True, exist_ok=True)
        return path


def _assert_under_tmp(tmp_path: Path, *paths: Path) -> None:
    root = tmp_path.resolve()
    for path in paths:
        assert path.resolve().is_relative_to(root), path


def _recommendation(price: Decimal = Decimal("123.40")) -> RecommendationDTO:
    return RecommendationDTO(
        stock_code="2330",
        stock_name="台積電",
        close_price=price,
        price_change=Decimal("1.25"),
        total_score=82.5,
        indicator_score=80.0,
        pattern_score=85.0,
        volume_score=82.0,
        recommendation_reasons="R004 fixture",
        industry="半導體",
        regime_match=True,
        score_percentile_bp=8100,
        eligible_universe_size=100,
        eligible_universe_date="2026-09-21",
        ranking_method="nearest_rank",
        threshold_mode="quantile",
    )


def _result(
    result_id: str,
    *,
    result_name: str = "R004 fixture",
    price: Decimal = Decimal("123.40"),
    notes: str = "baseline",
) -> RecommendationResultDTO:
    return RecommendationResultDTO(
        result_id=result_id,
        result_name=result_name,
        config={"profile": "fixture", "threshold_mode": "quantile"},
        recommendations=[_recommendation(price)],
        regime="Trend",
        created_at="2026-09-22T12:00:00+00:00",
        notes=notes,
        excluded_candidates_json=[{"stock_code": "0050", "reason": "fixture"}],
        screening_matrix_json=[{"stock_code": "2330", "passed": True}],
        why_not_payload_json=[{"stock_code": "0050", "reason": "below_threshold"}],
        liquidity_gate_payload_json=[{"stock_code": "2330", "status": "pass"}],
        exclusion_quality="observed",
        exclusion_warnings_json=["fixture_warning"],
        run_context={"result_id": result_id, "source": "R004 fixture"},
    )


def _serialized_result(result: RecommendationResultDTO) -> bytes:
    normalized = _make_json_serializable(result.to_dict())
    text = json.dumps(normalized, ensure_ascii=False, indent=2)
    # Path.write_text()/open(..., "x") use platform text newline translation.
    return text.replace("\n", os.linesep).encode("utf-8")


def _runs_row(
    result_id: str,
    result_name: str,
    data_path: Path,
    *,
    created_at: str = "2026-09-22T12:00:00+00:00",
) -> tuple[Any, ...]:
    return (
        result_id,
        result_name,
        "Trend",
        1,
        json.dumps({"profile": "legacy"}, ensure_ascii=False),
        "copied fixture",
        created_at,
        str(data_path),
    )


def test_r004_copied_legacy_json_sqlite_load_and_list_hash_raw_first(
    tmp_path: Path,
) -> None:
    repository = RecommendationRepository(_TmpConfig(tmp_path / "output"))
    fixture_dir = tmp_path / "fixture_source"
    fixture_dir.mkdir()
    fixture_id = "legacy_r004_001"
    source_json = fixture_dir / f"{fixture_id}.json"
    source_db = fixture_dir / "recommendation_runs.db"
    result_path = repository.runs_dir / source_json.name

    # This is the minimal pre-new-schema shape: the result envelope uses its
    # historical English fields and the recommendation row uses Chinese keys.
    old_payload = {
        "result_id": fixture_id,
        "result_name": "舊格式 R004",
        "config": {"profile": "legacy"},
        "recommendations": [
            {
                "證券代號": "2330",
                "證券名稱": "台積電",
                "收盤價": "600.10",
                "漲幅%": 2.5,
                "總分": 90.0,
                "指標分": 85.0,
                "圖形分": 95.0,
                "成交量分": 90.0,
                "推薦理由": "歷史 fixture",
                "產業": "半導體業",
                "Regime匹配": "是",
            }
        ],
        "regime": "Trend",
        "created_at": "2024-01-02T03:04:05+00:00",
        "notes": "old fixture",
        "screening_matrix_json": [{"stock_code": "2330", "passed": True}],
        "why_not_payload_json": [{"stock_code": "2317", "reason": "excluded"}],
        "liquidity_gate_payload_json": [{"stock_code": "2330", "status": "pass"}],
    }
    source_json.write_bytes(
        json.dumps(old_payload, ensure_ascii=False, indent=2).encode("utf-8")
    )
    result_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_json, result_path)

    with sqlite3.connect(source_db) as connection:
        connection.execute(
            """
            CREATE TABLE runs (
                result_id TEXT PRIMARY KEY,
                result_name TEXT NOT NULL,
                regime TEXT,
                stock_count INTEGER,
                config TEXT,
                notes TEXT,
                created_at TEXT,
                data_path TEXT
            )
            """
        )
        connection.execute("CREATE INDEX idx_created_at ON runs(created_at)")
        connection.execute("CREATE INDEX idx_regime ON runs(regime)")
        connection.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            _runs_row(fixture_id, "舊格式 R004", result_path),
        )
    shutil.copyfile(source_db, repository.db_path)

    _assert_under_tmp(
        tmp_path,
        repository.runs_dir,
        repository.db_path,
        source_json,
        source_db,
        result_path,
    )
    original_bytes = result_path.read_bytes()
    original_hash = hashlib.sha256(original_bytes).hexdigest()
    # Hash the source bytes before asking the legacy DTO decoder to interpret them.
    loaded = repository.load_result(fixture_id)

    assert loaded is not None
    assert loaded.recommendations[0].close_price == Decimal("600.10")
    assert loaded.recommendations[0].stock_name == "台積電"
    assert loaded.screening_matrix_json == [{"stock_code": "2330", "passed": True}]
    assert loaded.why_not_payload_json == [{"stock_code": "2317", "reason": "excluded"}]
    assert loaded.liquidity_gate_payload_json == [{"stock_code": "2330", "status": "pass"}]
    assert result_path.read_bytes() == original_bytes
    assert hashlib.sha256(result_path.read_bytes()).hexdigest() == original_hash
    assert repository.list_results() == [
        {
            "result_id": fixture_id,
            "result_name": "舊格式 R004",
            "regime": "Trend",
            "stock_count": 1,
            "created_at": "2026-09-22T12:00:00+00:00",
            "notes": "copied fixture",
        }
    ]


def test_r004_writer_keeps_english_chinese_keys_decimal_and_evidence_payloads(
    tmp_path: Path,
) -> None:
    repository = RecommendationRepository(_TmpConfig(tmp_path / "output"))
    result = _result("r004_roundtrip")
    expected_bytes = _serialized_result(result)
    result_path = repository.runs_dir / f"{result.result_id}.json"
    _assert_under_tmp(tmp_path, repository.db_path, result_path)

    assert repository.save_result(result, result_name=result.result_name) == result.result_id
    original_bytes = result_path.read_bytes()
    original_hash = hashlib.sha256(original_bytes).hexdigest()
    assert original_bytes == expected_bytes
    wire = json.loads(original_bytes)
    row = wire["recommendations"][0]
    assert wire["result_id"] == "r004_roundtrip"
    assert row["證券代號"] == "2330"
    assert row["證券名稱"] == "台積電"
    assert row["收盤價"] == "123.40"
    assert "stock_code" not in row
    english_input = RecommendationDTO.from_dict(
        {
            "stock_code": "2330",
            "stock_name": "台積電",
            "close_price": "123.40",
            "price_change": 1.25,
            "total_score": 82.5,
            "indicator_score": 80.0,
            "pattern_score": 85.0,
            "volume_score": 82.0,
            "recommendation_reasons": "R004 fixture",
            "industry": "半導體",
            "regime_match": True,
        }
    )
    assert english_input.close_price == Decimal("123.40")
    assert english_input.to_dict()["證券代號"] == "2330"
    assert wire["screening_matrix_json"] == result.screening_matrix_json
    assert wire["why_not_payload_json"] == result.why_not_payload_json
    assert wire["liquidity_gate_payload_json"] == result.liquidity_gate_payload_json

    loaded = repository.load_result(result.result_id)
    assert loaded is not None
    assert loaded.recommendations[0].close_price == Decimal("123.40")
    assert type(loaded.recommendations[0].close_price) is Decimal
    assert loaded.screening_matrix_json == result.screening_matrix_json
    assert loaded.why_not_payload_json == result.why_not_payload_json
    assert loaded.liquidity_gate_payload_json == result.liquidity_gate_payload_json
    assert result_path.read_bytes() == original_bytes
    assert hashlib.sha256(result_path.read_bytes()).hexdigest() == original_hash


def test_r004_replace_and_create_only_have_distinct_existing_id_semantics(
    tmp_path: Path,
) -> None:
    repository = RecommendationRepository(_TmpConfig(tmp_path / "output"))
    result_id = "r004_replace_vs_create_only"
    initial = _result(result_id, result_name="Initial label", notes="initial")
    path = repository.runs_dir / f"{result_id}.json"
    _assert_under_tmp(tmp_path, repository.db_path, path)

    assert repository.save_result_create_only(initial) == result_id
    initial_bytes = path.read_bytes()
    initial_hash = hashlib.sha256(initial_bytes).hexdigest()

    identical_retry = _result(
        result_id,
        result_name="Initial label",
        notes="initial",
    )
    assert _serialized_result(identical_retry) == initial_bytes
    assert repository.save_result_create_only(identical_retry) == result_id
    assert path.read_bytes() == initial_bytes
    assert hashlib.sha256(path.read_bytes()).hexdigest() == initial_hash

    # Current legacy create-only returns early for an indexed ID without
    # comparing candidate bytes. Record this as a gap for the future store.
    changed_create_only = _result(
        result_id,
        result_name="Changed label",
        price=Decimal("124.00"),
        notes="different payload",
    )
    assert _serialized_result(changed_create_only) != initial_bytes
    assert repository.save_result_create_only(changed_create_only) == result_id
    assert path.read_bytes() == initial_bytes
    existing = repository.load_result(result_id)
    assert existing is not None
    assert existing.result_name == "Initial label"
    assert existing.recommendations[0].close_price == Decimal("123.40")
    assert repository.list_results()[0]["result_name"] == "Initial label"

    # The legacy replace API writes new JSON bytes and replaces index metadata.
    replacement = _result(
        result_id,
        result_name="Replace label",
        price=Decimal("124.00"),
        notes="replacement payload",
    )
    assert repository.save_result(replacement, result_name="Replace label") == result_id
    replaced_bytes = path.read_bytes()
    assert replaced_bytes != initial_bytes
    assert hashlib.sha256(replaced_bytes).hexdigest() != initial_hash
    replaced = repository.load_result(result_id)
    assert replaced is not None
    assert replaced.result_name == "Replace label"
    assert replaced.notes == "replacement payload"
    assert replaced.recommendations[0].close_price == Decimal("124.00")
    assert repository.list_results()[0]["result_name"] == "Replace label"


def test_r004_artifact_only_orphan_recovery_and_unknown_bytes_preservation(
    tmp_path: Path,
) -> None:
    repository = RecommendationRepository(_TmpConfig(tmp_path / "output"))
    result = _result("r004_orphan")
    result_path = repository.runs_dir / f"{result.result_id}.json"
    _assert_under_tmp(tmp_path, repository.db_path, result_path)

    orphan_bytes = _serialized_result(result)
    result_path.write_bytes(orphan_bytes)
    orphan_hash = hashlib.sha256(result_path.read_bytes()).hexdigest()
    assert repository.load_result(result.result_id) is None
    assert repository.save_result_create_only(result) == result.result_id
    assert result_path.read_bytes() == orphan_bytes
    assert hashlib.sha256(result_path.read_bytes()).hexdigest() == orphan_hash
    assert repository.load_result(result.result_id) is not None

    unknown = _result("r004_unknown")
    unknown_path = repository.runs_dir / f"{unknown.result_id}.json"
    unknown_bytes = b"\x00legacy-unknown-format\xff\n"
    unknown_path.write_bytes(unknown_bytes)
    unknown_hash = hashlib.sha256(unknown_path.read_bytes()).hexdigest()
    # Persisting an unknown file must reject by byte identity without rewriting it.
    with pytest.raises(RuntimeError, match="cannot be inspected"):
        repository.save_result_create_only(unknown)
    assert unknown_path.read_bytes() == unknown_bytes
    assert hashlib.sha256(unknown_path.read_bytes()).hexdigest() == unknown_hash
    assert repository.load_result(unknown.result_id) is None

    indexed = _result("r004_unknown_indexed")
    indexed_path = repository.runs_dir / f"{indexed.result_id}.json"
    repository.save_result(indexed)
    indexed_bytes = b"{not-json and must stay byte-identical"
    indexed_path.write_bytes(indexed_bytes)
    indexed_hash = hashlib.sha256(indexed_path.read_bytes()).hexdigest()
    with pytest.raises(RuntimeError, match="cannot classify"):
        repository.save_result(indexed)
    assert indexed_path.read_bytes() == indexed_bytes
    assert hashlib.sha256(indexed_path.read_bytes()).hexdigest() == indexed_hash


def test_r004_index_only_row_lists_but_does_not_load_missing_artifact(
    tmp_path: Path,
) -> None:
    repository = RecommendationRepository(_TmpConfig(tmp_path / "output"))
    result_id = "r004_index_only"
    missing_path = repository.runs_dir / f"{result_id}.json"
    _assert_under_tmp(tmp_path, repository.db_path, missing_path)
    assert not missing_path.exists()

    with sqlite3.connect(repository.db_path) as connection:
        connection.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            _runs_row(result_id, "index only", missing_path),
        )

    assert repository.load_result(result_id) is None
    assert repository.list_results()[0]["result_id"] == result_id
    assert not missing_path.exists()


def test_r004_file_create_failure_leaves_no_artifact_or_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = RecommendationRepository(_TmpConfig(tmp_path / "output"))
    result = _result("r004_file_failure")
    result_path = repository.runs_dir / f"{result.result_id}.json"
    _assert_under_tmp(tmp_path, repository.db_path, result_path)
    real_open = Path.open

    def fail_artifact_create(
        path: Path,
        mode: str = "r",
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        if path == result_path and mode == "x":
            raise OSError("injected artifact create failure")
        return real_open(path, mode, *args, **kwargs)

    with monkeypatch.context() as injected:
        injected.setattr(Path, "open", fail_artifact_create)
        with pytest.raises(OSError, match="injected artifact create failure"):
            repository.save_result_create_only(result)

    assert not result_path.exists()
    assert repository.load_result(result.result_id) is None
    assert repository.list_results() == []
    expected_bytes = _serialized_result(result)
    expected_hash = hashlib.sha256(expected_bytes).hexdigest()
    assert repository.save_result_create_only(result) == result.result_id
    recovered_bytes = result_path.read_bytes()
    assert recovered_bytes == expected_bytes
    assert hashlib.sha256(recovered_bytes).hexdigest() == expected_hash


def test_r004_replace_file_write_failure_preserves_previous_bytes_and_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = RecommendationRepository(_TmpConfig(tmp_path / "output"))
    result_id = "r004_replace_file_failure"
    initial = _result(result_id, result_name="before", notes="before")
    replacement = _result(
        result_id,
        result_name="after",
        price=Decimal("124.00"),
        notes="after",
    )
    result_path = repository.runs_dir / f"{result_id}.json"
    _assert_under_tmp(tmp_path, repository.db_path, result_path)
    repository.save_result(initial, result_name=initial.result_name)
    before_bytes = result_path.read_bytes()
    before_hash = hashlib.sha256(before_bytes).hexdigest()
    real_write_text = Path.write_text

    def fail_target_write(
        path: Path,
        data: str,
        *args: Any,
        **kwargs: Any,
    ) -> int:
        if path == result_path:
            raise OSError("injected replace artifact write failure")
        return real_write_text(path, data, *args, **kwargs)

    with monkeypatch.context() as injected:
        injected.setattr(Path, "write_text", fail_target_write)
        with pytest.raises(OSError, match="injected replace artifact write failure"):
            repository.save_result(replacement, result_name=replacement.result_name)

    assert result_path.read_bytes() == before_bytes
    assert hashlib.sha256(result_path.read_bytes()).hexdigest() == before_hash
    assert repository.load_result(result_id).result_name == "before"
    assert repository.list_results()[0]["result_name"] == "before"

    assert repository.save_result(replacement, result_name=replacement.result_name) == result_id
    recovered_bytes = result_path.read_bytes()
    assert hashlib.sha256(recovered_bytes).hexdigest() != before_hash
    assert repository.load_result(result_id).result_name == "after"
    assert repository.list_results()[0]["result_name"] == "after"


class _FailingInsertCursor:
    def __init__(self, cursor: sqlite3.Cursor) -> None:
        self._cursor = cursor

    def execute(self, sql: str, parameters: Any = ()) -> Any:
        normalized = " ".join(sql.lower().split())
        if normalized.startswith("insert into runs") or normalized.startswith(
            "insert or replace into runs"
        ):
            raise sqlite3.OperationalError("injected index insert failure")
        return self._cursor.execute(sql, parameters)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)


class _FailingInsertConnection:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def cursor(self) -> _FailingInsertCursor:
        return _FailingInsertCursor(self._connection.cursor())

    def execute(self, sql: str, parameters: Any = ()) -> Any:
        return self._connection.execute(sql, parameters)

    @property
    def in_transaction(self) -> bool:
        return self._connection.in_transaction

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


class _FailingInsertSqlite:
    def connect(self, path: Path, **kwargs: Any) -> _FailingInsertConnection:
        return _FailingInsertConnection(sqlite3.connect(path, **kwargs))


def test_r004_index_insert_failure_keeps_artifact_hash_and_identical_retry_recovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = RecommendationRepository(_TmpConfig(tmp_path / "output"))
    result = _result("r004_index_failure")
    result_path = repository.runs_dir / f"{result.result_id}.json"
    expected_bytes = _serialized_result(result)
    expected_hash = hashlib.sha256(expected_bytes).hexdigest()
    _assert_under_tmp(tmp_path, repository.db_path, result_path)

    with monkeypatch.context() as injected:
        injected.setattr(repository_module, "sqlite3", _FailingInsertSqlite())
        with pytest.raises(
            RuntimeError,
            match="metadata write failed; retained data file",
        ):
            repository.save_result_create_only(result)

    retained_bytes = result_path.read_bytes()
    assert retained_bytes == expected_bytes
    assert hashlib.sha256(retained_bytes).hexdigest() == expected_hash
    assert repository.load_result(result.result_id) is None
    assert repository.list_results() == []

    assert repository.save_result_create_only(result) == result.result_id
    assert result_path.read_bytes() == retained_bytes
    assert hashlib.sha256(result_path.read_bytes()).hexdigest() == expected_hash
    assert repository.load_result(result.result_id) is not None


def test_r004_replace_index_failure_leaves_new_artifact_and_old_index_until_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = RecommendationRepository(_TmpConfig(tmp_path / "output"))
    result_id = "r004_replace_index_failure"
    initial = _result(result_id, result_name="indexed before", notes="before")
    replacement = _result(
        result_id,
        result_name="payload after",
        price=Decimal("124.00"),
        notes="after",
    )
    result_path = repository.runs_dir / f"{result_id}.json"
    _assert_under_tmp(tmp_path, repository.db_path, result_path)
    repository.save_result(initial, result_name=initial.result_name)
    before_hash = hashlib.sha256(result_path.read_bytes()).hexdigest()
    expected_replacement_bytes = _serialized_result(replacement)
    expected_replacement_hash = hashlib.sha256(expected_replacement_bytes).hexdigest()

    with monkeypatch.context() as injected:
        injected.setattr(repository_module, "sqlite3", _FailingInsertSqlite())
        with pytest.raises(sqlite3.OperationalError, match="injected index insert failure"):
            repository.save_result(replacement, result_name=replacement.result_name)

    after_failure = result_path.read_bytes()
    assert after_failure == expected_replacement_bytes
    assert hashlib.sha256(after_failure).hexdigest() == expected_replacement_hash
    assert hashlib.sha256(after_failure).hexdigest() != before_hash
    # SQLite rollback keeps the old metadata row while its path resolves to the
    # replacement DTO, exposing the non-atomic failure window.
    assert repository.list_results()[0]["result_name"] == "indexed before"
    loaded = repository.load_result(result_id)
    assert loaded is not None
    assert loaded.result_name == "payload after"
    assert loaded.notes == "after"

    assert repository.save_result(replacement, result_name=replacement.result_name) == result_id
    assert result_path.read_bytes() == after_failure
    assert hashlib.sha256(result_path.read_bytes()).hexdigest() == expected_replacement_hash
    assert repository.list_results()[0]["result_name"] == "payload after"


def test_r004_concurrent_first_writer_retains_one_payload_and_one_index_row(
    tmp_path: Path,
) -> None:
    repository = RecommendationRepository(_TmpConfig(tmp_path / "output"))
    result_id = "r004_concurrent_first_writer"
    candidates = (
        _result(result_id, result_name="writer A", price=Decimal("123.40")),
        _result(result_id, result_name="writer B", price=Decimal("456.70")),
    )
    candidate_bytes = {_serialized_result(item) for item in candidates}
    result_path = repository.runs_dir / f"{result_id}.json"
    _assert_under_tmp(tmp_path, repository.db_path, result_path)
    start = Barrier(2)

    def save_first(result: RecommendationResultDTO) -> str:
        start.wait(timeout=10)
        return repository.save_result_create_only(result)

    with ThreadPoolExecutor(max_workers=2) as executor:
        saved_ids = list(executor.map(save_first, candidates))

    assert saved_ids == [result_id, result_id]
    retained_bytes = result_path.read_bytes()
    assert retained_bytes in candidate_bytes
    retained_hash = hashlib.sha256(retained_bytes).hexdigest()
    loaded = repository.load_result(result_id)
    assert loaded is not None
    winning_candidate = next(
        item for item in candidates if _serialized_result(item) == retained_bytes
    )
    assert loaded.result_name == winning_candidate.result_name
    assert loaded.recommendations[0].close_price == winning_candidate.recommendations[0].close_price
    assert loaded.notes == winning_candidate.notes
    assert hashlib.sha256(result_path.read_bytes()).hexdigest() == retained_hash
    assert len(repository.list_results()) == 1

