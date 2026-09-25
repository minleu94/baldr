"""R016 legacy original-payload query projection，僅用合成 tmp_path fixtures。"""

from __future__ import annotations

from dataclasses import replace
import ctypes
import errno
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import stat
from types import SimpleNamespace
from typing import Mapping

import pytest

from app_module.recommendation.codec import decode_execution_envelope
from app_module.decision_outcome_journey import DecisionOutcomeJourneyService
from app_module.recommendation.persistence import (
    ExecutionArtifactIntegrityError,
    ExecutionIndexReadError,
    RecommendationExecutionPersistence,
)
from app_module.recommendation.contracts import MLAvailability
from app_module.recommendation.queries import (
    LegacyRecommendationBytes,
    RecommendationExecutionQueries,
    SQLiteLegacyRecommendationRawByteReader,
)
from data_module.result_artifact_store import ArtifactIndexMetadata, ResultArtifactStore


def _stack(tmp_path: Path) -> tuple[Path, ResultArtifactStore, RecommendationExecutionQueries]:
    runs_dir = tmp_path / "recommendation" / "runs"
    store = ResultArtifactStore(
        artifact_root=runs_dir / "execution_artifacts",
        database_path=runs_dir / "recommendation_runs.db",
    )
    persistence = RecommendationExecutionPersistence(store)
    return runs_dir, store, RecommendationExecutionQueries(persistence)


def _legacy_payload(result_id: str) -> dict[str, object]:
    snapshot_hash = "sha256:" + "b" * 64
    source_id = "synthetic-source-42"
    snapshot_id = "synthetic-snapshot-20260922"
    return {
        "result_id": result_id,
        "result_name": "synthetic legacy result",
        "created_at": "2026-09-22T12:00:00+00:00",
        "source_id": source_id,
        "source_snapshot_id": snapshot_id,
        "source_snapshot_hash": snapshot_hash,
        "config": {
            "decision_date": "2026-09-22",
            "source_id": source_id,
            "source_snapshot_id": snapshot_id,
            "source_snapshot_hash": snapshot_hash,
            "opaque_config": {"vendor_mode": "legacy", "values": ["x", 2]},
        },
        "run_context": {
            "as_of_date": "2026-09-22",
            "source_id": source_id,
            "source_snapshot_id": snapshot_id,
            "source_snapshot_hash": snapshot_hash,
            "opaque_context": {"nested": [{"raw": True}, ["keep", "all"]]},
        },
        "recommendations": [
            {
                "證券代號": "2330",
                "證券名稱": "台積電",
                "收盤價": "600.50",
                "漲幅%": 1.25,
                "總分": 82.5,
                "指標分": 80.0,
                "圖形分": 85.0,
                "成交量分": 82.0,
                "推薦理由": "合成歷史推薦",
                "產業": "半導體",
                "Regime匹配": "是",
                "recommendation_rank": 7,
                "opaque_candidate": {
                    "rank_source": "saved-row",
                    "nested": [{"provider_field": "preserved"}],
                },
            }
        ],
        "opaque_root": {"extension": {"items": [1, {"tag": "retained"}]}},
    }


def _raw_payload(result_id: str) -> bytes:
    return json.dumps(
        _legacy_payload(result_id),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _register_legacy(
    runs_dir: Path,
    result_id: str,
    raw: bytes,
    *,
    data_path: Path | None = None,
) -> Path:
    runs_dir.mkdir(parents=True, exist_ok=True)
    exact_path = runs_dir / f"{result_id}.json"
    exact_path.write_bytes(raw)
    with sqlite3.connect(runs_dir / "recommendation_runs.db") as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                result_id TEXT PRIMARY KEY,
                result_name TEXT,
                notes TEXT,
                created_at TEXT,
                data_path TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO runs (result_id, result_name, notes, created_at, data_path)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                result_id,
                "synthetic label",
                "synthetic notes",
                "2026-09-22T12:00:00+00:00",
                str(data_path or exact_path),
            ),
        )
    return exact_path


def _fake_windows_kernel32(
    *,
    file_type: int | None = None,
    expose_get_file_type: bool = True,
) -> tuple[SimpleNamespace, list[int], list[int], list[int]]:
    created_handles: list[int] = []
    file_type_handles: list[int] = []
    closed_handles: list[int] = []

    def create_file(*_args: object) -> int:
        handle = 12345
        created_handles.append(handle)
        return handle

    def close_handle(handle: int) -> int:
        closed_handles.append(handle)
        return 1

    def get_info(
        _handle: int,
        _info_class: int,
        buffer: object,
        _size: int,
    ) -> int:
        attributes = ctypes.cast(
            buffer, ctypes.POINTER(ctypes.c_uint32)
        ).contents
        attributes.value = 0
        return 1

    api = SimpleNamespace(
        CreateFileW=create_file,
        CloseHandle=close_handle,
        GetFileInformationByHandleEx=get_info,
    )
    if expose_get_file_type:
        def get_file_type(handle: int) -> int:
            file_type_handles.append(handle)
            return 1 if file_type is None else file_type

        api.GetFileType = get_file_type
    return api, created_handles, file_type_handles, closed_handles


def _freeze(value: object) -> object:
    if isinstance(value, dict):
        return {key: _freeze(item) for key, item in value.items()}
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _mock_posix_dirfd_io(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fail_open_path: str,
    fail_open_error: int = errno.ELOOP,
) -> tuple[list[tuple[object, int, int | None]], list[int]]:
    from app_module.recommendation import queries as queries_module

    opened: list[tuple[object, int, int | None]] = []
    closed: list[int] = []
    next_fd = 900
    nofollow = getattr(os, "O_NOFOLLOW", 0) or 0x20000
    directory_flag = getattr(os, "O_DIRECTORY", 0) or 0x10000

    def fake_open(
        path: object,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal next_fd
        opened.append((path, flags, dir_fd))
        if path == fail_open_path:
            raise OSError(fail_open_error, "simulated no-follow swap/disappearance")
        descriptor = next_fd
        next_fd += 1
        return descriptor

    def fake_fstat(_descriptor: int) -> SimpleNamespace:
        return SimpleNamespace(st_mode=stat.S_IFDIR | 0o755)

    monkeypatch.setattr(queries_module.os, "open", fake_open)
    monkeypatch.setattr(
        queries_module.os,
        "supports_dir_fd",
        {fake_open},
        raising=False,
    )
    monkeypatch.setattr(
        queries_module.os,
        "O_NOFOLLOW",
        nofollow,
        raising=False,
    )
    monkeypatch.setattr(
        queries_module.os,
        "O_DIRECTORY",
        directory_flag,
        raising=False,
    )
    monkeypatch.setattr(queries_module.os, "fstat", fake_fstat)
    monkeypatch.setattr(queries_module.os, "close", closed.append)
    return opened, closed


def test_registered_legacy_projection_preserves_journey_identity_rank_and_opaque_payload(
    tmp_path: Path,
) -> None:
    result_id = "r016-legacy-projection"
    runs_dir, _store, queries = _stack(tmp_path)
    raw = _raw_payload(result_id)
    legacy_path = _register_legacy(runs_dir, result_id, raw)

    projection = queries.get_legacy_original_payload(result_id)

    assert projection is not None
    expected = _legacy_payload(result_id)
    assert projection.source == "registered_legacy_run"
    assert projection.data_path == str(legacy_path.resolve())
    assert projection.integrity_basis == "legacy_read_time_hash_only"
    assert projection.raw_artifact_sha256 == "sha256:" + hashlib.sha256(raw).hexdigest()
    assert projection.payload == _freeze(expected)
    assert projection.payload["source_id"] == "synthetic-source-42"
    assert projection.payload["source_snapshot_id"] == "synthetic-snapshot-20260922"
    candidate = projection.payload["recommendations"][0]  # type: ignore[index]
    assert candidate["recommendation_rank"] == 7
    assert candidate["opaque_candidate"]["nested"][0]["provider_field"] == "preserved"
    with pytest.raises(TypeError):
        projection.payload["opaque_root"] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        projection.payload["opaque_root"]["extension"] = {}  # type: ignore[index]
    nested_items = (
        projection.payload["opaque_root"]["extension"]["items"]  # type: ignore[index]
    )
    with pytest.raises(AttributeError):
        nested_items.append("mutate")  # type: ignore[union-attr]
    assert legacy_path.read_bytes() == raw

    class _ProjectionReader:
        def read_result(self, requested_id: str) -> Mapping[str, object] | None:
            assert requested_id == result_id
            return projection.payload

        def path_for(self, requested_id: str) -> str:
            assert requested_id == result_id
            return projection.data_path

    journey = DecisionOutcomeJourneyService(
        recommendation_reader=_ProjectionReader()
    ).build(result_id)
    assert journey.recommendation_result.source_identity.source_provider_id == (
        "synthetic-source-42"
    )
    assert journey.recommendation_result.source_identity.source_snapshot_id == (
        "synthetic-snapshot-20260922"
    )
    assert journey.recommendation_result.source_identity.source_snapshot_hash == (
        "sha256:" + "b" * 64
    )
    assert journey.recommendation_result.candidates[0].recommendation_rank == 7
    assert journey.recommendation_result.original_payload == _freeze(expected)
    assert journey.recommendation_result.candidates[0].original_payload == _freeze(
        expected["recommendations"][0]
    )
    with sqlite3.connect(runs_dir / "recommendation_runs.db") as connection:
        assert tuple(
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ) == ("runs",)


def test_registered_projection_rejects_reparse_runs_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_id = "r016-registered-reparse-root"
    runs_dir, _store, queries = _stack(tmp_path)
    raw = _raw_payload(result_id)
    legacy_path = _register_legacy(runs_dir, result_id, raw)
    from app_module.recommendation import queries as queries_module
    reader = queries._legacy_reader
    assert isinstance(reader, SQLiteLegacyRecommendationRawByteReader)

    original_guard = queries_module._is_symlink_or_reparse
    absolute_runs_dir = Path(os.path.abspath(runs_dir))

    def mark_runs_root_reparse(path: Path) -> bool:
        if Path(os.path.abspath(path)) == absolute_runs_dir:
            return True
        return original_guard(path)

    monkeypatch.setattr(
        queries_module,
        "_is_symlink_or_reparse",
        mark_runs_root_reparse,
    )
    with pytest.raises(
        ExecutionArtifactIntegrityError,
        match="runs 目錄不可為 symlink/reparse",
    ):
        reader._read_scoped_path(result_id, str(legacy_path))
    assert legacy_path.read_bytes() == raw


def test_registered_projection_rejects_runs_root_resolve_retarget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_id = "r016-registered-root-retarget"
    runs_dir, _store, queries = _stack(tmp_path)
    raw = _raw_payload(result_id)
    legacy_path = _register_legacy(runs_dir, result_id, raw)
    redirected_root = tmp_path / "redirected-runs-root"
    redirected_root.mkdir()
    redirected_payload = _legacy_payload(result_id)
    redirected_payload["source_id"] = "synthetic-retargeted-root"
    redirected_path = redirected_root / f"{result_id}.json"
    redirected_path.write_bytes(
        json.dumps(redirected_payload, ensure_ascii=False).encode("utf-8")
    )
    reader = queries._legacy_reader
    assert isinstance(reader, SQLiteLegacyRecommendationRawByteReader)

    original_resolve = Path.resolve
    absolute_runs_dir = Path(os.path.abspath(runs_dir))

    def retarget_runs_root(path: Path, *, strict: bool = False) -> Path:
        if Path(os.path.abspath(path)) == absolute_runs_dir:
            return redirected_root
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", retarget_runs_root)
    with pytest.raises(
        ExecutionArtifactIntegrityError,
        match="runs root resolve 與 configured absolute path 不一致",
    ):
        reader._read_scoped_path(result_id, str(legacy_path))
    assert legacy_path.read_bytes() == raw
    assert json.loads(redirected_path.read_text(encoding="utf-8"))["source_id"] == (
        "synthetic-retargeted-root"
    )


def test_registered_legacy_projection_marks_explicit_trusted_digest_and_rejects_mismatch(
    tmp_path: Path,
) -> None:
    result_id = "r016-legacy-trusted"
    runs_dir, store, _queries = _stack(tmp_path)
    raw = _raw_payload(result_id)
    raw_path = _register_legacy(runs_dir, result_id, raw)
    expected_hash = "sha256:" + hashlib.sha256(raw).hexdigest()
    reader = SQLiteLegacyRecommendationRawByteReader(
        runs_dir,
        store.database_path,
        trusted_expected_hashes={result_id: expected_hash},
    )
    query = RecommendationExecutionQueries(
        RecommendationExecutionPersistence(store), reader
    )

    loaded = query.get_legacy_original_payload(result_id)

    assert loaded is not None
    assert loaded.integrity_basis == "legacy_trusted_hash_verified"
    assert loaded.raw_artifact_sha256 == expected_hash
    mismatch_reader = SQLiteLegacyRecommendationRawByteReader(
        runs_dir,
        store.database_path,
        trusted_expected_hashes={result_id: "sha256:" + "0" * 64},
    )
    mismatch_query = RecommendationExecutionQueries(
        RecommendationExecutionPersistence(store), mismatch_reader
    )
    with pytest.raises(ExecutionArtifactIntegrityError, match="獨立可信 expected hash"):
        mismatch_query.get_legacy_original_payload(result_id)
    assert raw_path.read_bytes() == raw


def test_unindexed_exact_id_projection_is_opt_in_and_never_claims_index_trust(
    tmp_path: Path,
) -> None:
    result_id = "r016-unindexed-legacy"
    runs_dir, _store, queries = _stack(tmp_path)
    runs_dir.mkdir(parents=True)
    raw = _raw_payload(result_id)
    raw_path = runs_dir / f"{result_id}.json"
    raw_path.write_bytes(raw)

    assert queries.get_legacy_original_payload(result_id) is None
    projection = queries.get_legacy_original_payload(
        result_id,
        allow_unindexed_legacy=True,
    )

    assert projection is not None
    assert projection.source == "unindexed_legacy_file"
    assert projection.integrity_basis == "legacy_read_time_hash_only"
    assert projection.raw_artifact_sha256 == "sha256:" + hashlib.sha256(raw).hexdigest()
    assert projection.payload == _freeze(_legacy_payload(result_id))
    assert raw_path.read_bytes() == raw
    assert not (runs_dir / "recommendation_runs.db").exists()


def test_unindexed_projection_rejects_unsafe_id_symlink_scope_and_readback_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_id = "r016-unindexed-guard"
    runs_dir, _store, queries = _stack(tmp_path)
    runs_dir.mkdir(parents=True)
    raw = _raw_payload(result_id)
    raw_path = runs_dir / f"{result_id}.json"
    raw_path.write_bytes(raw)

    with pytest.raises(ValueError, match="安全的單一檔名"):
        queries.get_legacy_original_payload(
            "../outside",
            allow_unindexed_legacy=True,
        )

    original_read = queries._read_unindexed_legacy_file
    reads = 0

    def changed_bytes(candidate_id: str) -> LegacyRecommendationBytes | None:
        nonlocal reads
        result = original_read(candidate_id)
        reads += 1
        if result is not None and reads == 2:
            return replace(result, raw_payload=result.raw_payload + b" ")
        return result

    monkeypatch.setattr(queries, "_read_unindexed_legacy_file", changed_bytes)
    with pytest.raises(ExecutionArtifactIntegrityError, match="bytes/path.*改變"):
        queries.get_legacy_original_payload(
            result_id,
            allow_unindexed_legacy=True,
        )
    assert raw_path.read_bytes() == raw


@pytest.mark.parametrize(
    "result_id",
    [
        "r016:stream",
        "NUL",
        "CON",
        "PRN",
        "AUX",
        "COM1",
        "COM9",
        "LPT1",
        "LPT9",
        "NUL.json",
        "CON.json",
        "result.",
        "result ",
        "id<bad",
        "id>bad",
        "id|bad",
        "id?bad",
        "id*bad",
        'id"bad',
    ],
)
def test_registered_and_unindexed_paths_reject_win32_ambiguous_ids(
    tmp_path: Path,
    result_id: str,
) -> None:
    if os.name != "nt":
        pytest.skip("Win32 filename ambiguity rules")
    runs_dir, _store, queries = _stack(tmp_path)
    runs_dir.mkdir(parents=True)
    database_path = runs_dir / "recommendation_runs.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE runs (
                result_id TEXT PRIMARY KEY,
                result_name TEXT,
                notes TEXT,
                created_at TEXT,
                data_path TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO runs (result_id, result_name, notes, created_at, data_path)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                result_id,
                "synthetic invalid-name registration",
                "",
                None,
                str(runs_dir / f"{result_id}.json"),
            ),
        )

    reader = queries._legacy_reader
    assert isinstance(reader, SQLiteLegacyRecommendationRawByteReader)
    expected_error = "安全的單一檔名"
    with pytest.raises(ValueError, match=expected_error):
        reader.get(result_id)
    with pytest.raises(ValueError, match=expected_error):
        reader._read_scoped_path(
            result_id,
            str(runs_dir / f"{result_id}.json"),
        )
    with pytest.raises(ValueError, match=expected_error):
        queries.get_legacy_original_payload(
            result_id,
            allow_unindexed_legacy=True,
        )
    with pytest.raises(ExecutionArtifactIntegrityError, match="Win32 不安全"):
        queries.list()


def test_verified_canonical_opaque_windows_id_reads_and_legacy_collision_fails_closed(
    tmp_path: Path,
) -> None:
    if os.name != "nt":
        pytest.skip("canonical opaque-ID regression guard for Windows")
    runs_dir, store, queries = _stack(tmp_path)
    fixture = (
        Path(__file__).parent
        / "fixtures"
        / "c1_consumer_readiness"
        / "r016_execution_rev2.json"
    )
    source_execution = decode_execution_envelope(fixture.read_bytes()).execution
    result_id = f"{source_execution.result_id}:opaque"
    execution = replace(
        source_execution,
        result_id=result_id,
        ml_availability=MLAvailability(),
        ml_projection_refs=(),
        ml_receipt_refs=(),
    )
    persistence = RecommendationExecutionPersistence(store)
    persistence.save(
        execution,
        now=lambda: datetime(2026, 9, 23, tzinfo=timezone.utc),
    )

    read_model = queries.get(result_id)
    assert read_model is not None
    assert read_model.execution is not None
    assert read_model.execution.result_id == result_id
    assert read_model.artifact_location.endswith(".json")
    assert ":" not in read_model.artifact_location

    runs_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                result_id TEXT PRIMARY KEY,
                result_name TEXT,
                notes TEXT,
                created_at TEXT,
                data_path TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO runs (result_id, result_name, notes, created_at, data_path)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                result_id,
                "synthetic legacy identity collision",
                "",
                None,
                str(runs_dir / f"{result_id}.json"),
            ),
        )
    with pytest.raises(ExecutionArtifactIntegrityError, match="同一 result_id"):
        queries.get(result_id)


def test_unindexed_projection_rejects_symlinked_exact_file_without_following_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_id = "r016-unindexed-symlink"
    runs_dir, _store, queries = _stack(tmp_path)
    runs_dir.mkdir(parents=True)
    raw_path = runs_dir / f"{result_id}.json"
    raw_path.write_bytes(_raw_payload(result_id))
    from app_module.recommendation import queries as queries_module

    original_guard = queries_module._is_symlink_or_reparse

    def deny_exact_path(path: Path) -> bool:
        if path == raw_path.resolve():
            return True
        return original_guard(path)

    monkeypatch.setattr(
        "app_module.recommendation.queries._is_symlink_or_reparse",
        deny_exact_path,
    )
    with pytest.raises(ExecutionArtifactIntegrityError, match="symlink/reparse"):
        queries.get_legacy_original_payload(
            result_id,
            allow_unindexed_legacy=True,
        )


def test_registered_windows_reparse_swap_after_preflight_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name != "nt":
        pytest.skip("此 deterministic handle race 模擬只適用 Windows query path")
    result_id = "r016-windows-reparse-race"
    runs_dir, _store, queries = _stack(tmp_path)
    raw = _raw_payload(result_id)
    legacy_path = _register_legacy(runs_dir, result_id, raw)
    from app_module.recommendation import queries as queries_module

    original_guard = queries_module._is_symlink_or_reparse
    preflight_paths: list[Path] = []
    target_open_paths: list[Path] = []

    def pass_preflight(path: Path) -> bool:
        if path == legacy_path.resolve():
            preflight_paths.append(path)
            return False
        return original_guard(path)

    def simulate_swap_then_open(
        path: Path,
        *,
        directory: bool,
    ) -> int:
        if not directory and path == legacy_path.resolve():
            target_open_paths.append(path)
            raise ExecutionArtifactIntegrityError(
                "Windows opened path is a reparse point after clean preflight"
            )
        # Let SQLite DB/root/sidecar probes use real held Win32 handles. Only
        # substitute the legacy JSON target open to model the race after its
        # clean path preflight.
        return original_open(path, directory=directory)

    original_open = queries_module._windows_open_nofollow_handle
    original_close = queries_module._windows_close_handle

    monkeypatch.setattr(
        "app_module.recommendation.queries._is_symlink_or_reparse",
        pass_preflight,
    )
    monkeypatch.setattr(
        "app_module.recommendation.queries._windows_open_nofollow_handle",
        simulate_swap_then_open,
    )
    monkeypatch.setattr(
        "app_module.recommendation.queries._windows_close_handle",
        original_close,
    )

    with pytest.raises(
        ExecutionArtifactIntegrityError,
        match="reparse point after clean preflight",
    ):
        queries.get_legacy_original_payload(result_id)
    assert preflight_paths == [legacy_path.resolve()]
    assert target_open_paths == [legacy_path.resolve()]
    assert legacy_path.read_bytes() == raw


def test_windows_missing_nofollow_api_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name != "nt":
        pytest.skip("Windows no-follow API boundary")
    result_id = "r016-windows-no-follow-missing"
    runs_dir, _store, queries = _stack(tmp_path)
    runs_dir.mkdir(parents=True)
    raw = _raw_payload(result_id)
    legacy_path = runs_dir / f"{result_id}.json"
    legacy_path.write_bytes(raw)
    from app_module.recommendation import queries as queries_module

    monkeypatch.setattr(queries_module.ctypes, "WinDLL", None, raising=False)
    with pytest.raises(ExecutionArtifactIntegrityError, match="API 不可用"):
        queries.get_legacy_original_payload(
            result_id,
            allow_unindexed_legacy=True,
        )
    assert legacy_path.read_bytes() == raw


def test_windows_get_file_type_rejects_character_handle_and_closes_same_handle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name != "nt":
        pytest.skip("same-handle GetFileType validation is Windows-specific")
    from app_module.recommendation import queries as queries_module

    fake_kernel32, created, file_type_handles, closed = _fake_windows_kernel32(
        file_type=2
    )
    monkeypatch.setattr(
        queries_module.ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: fake_kernel32,
    )

    with pytest.raises(ExecutionArtifactIntegrityError, match="一般 disk"):
        queries_module._windows_open_nofollow_handle(
            tmp_path / "character-device.json",
            directory=False,
        )

    assert created == [12345]
    assert file_type_handles == created
    assert closed == created


def test_windows_missing_get_file_type_api_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name != "nt":
        pytest.skip("Windows GetFileType API boundary")
    from app_module.recommendation import queries as queries_module

    fake_kernel32, created, file_type_handles, closed = _fake_windows_kernel32(
        expose_get_file_type=False
    )
    monkeypatch.setattr(
        queries_module.ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: fake_kernel32,
    )

    with pytest.raises(
        ExecutionArtifactIntegrityError,
        match="GetFileType API 不可用",
    ):
        queries_module._windows_open_nofollow_handle(
            tmp_path / "missing-get-file-type.json",
            directory=False,
        )

    assert created == []
    assert file_type_handles == []
    assert closed == []


def test_legacy_corruption_and_existing_sqlite_row_never_fall_back_to_unindexed_file(
    tmp_path: Path,
) -> None:
    result_id = "r016-legacy-no-fallback"
    runs_dir, _store, queries = _stack(tmp_path)
    outside = tmp_path / "outside-legacy.json"
    outside.write_bytes(_raw_payload(result_id))
    exact_path = _register_legacy(
        runs_dir,
        result_id,
        _raw_payload(result_id),
        data_path=outside,
    )

    with pytest.raises(ExecutionArtifactIntegrityError, match="超出 runs 目錄範圍"):
        queries.get_legacy_original_payload(
            result_id,
            allow_unindexed_legacy=True,
        )
    assert exact_path.read_bytes() == _raw_payload(result_id)

    bad_id = "r016-legacy-corrupt"
    bad_raw = b'{"result_id":"r016-legacy-corrupt","recommendations":NaN}'
    corrupt_runs, _corrupt_store, corrupt_query = _stack(tmp_path / "corrupt-root")
    bad_path = _register_legacy(corrupt_runs, bad_id, bad_raw)
    with pytest.raises(ExecutionArtifactIntegrityError, match="decoder 驗證失敗"):
        corrupt_query.get_legacy_original_payload(
            bad_id,
            allow_unindexed_legacy=True,
        )
    assert bad_path.read_bytes() == bad_raw

    duplicate_id = "r016-legacy-duplicate-key"
    duplicate_raw = (
        b'{"result_id":"r016-legacy-duplicate-key",'
        b'"result_id":"r016-legacy-duplicate-key","recommendations":[]}'
    )
    duplicate_path = corrupt_runs / f"{duplicate_id}.json"
    duplicate_path.write_bytes(duplicate_raw)
    # 同一 tmp runs fixture 已有 runs table；加入第二個合成 row。
    with sqlite3.connect(corrupt_runs / "recommendation_runs.db") as connection:
        connection.execute(
            """
            INSERT INTO runs (result_id, result_name, notes, created_at, data_path)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                duplicate_id,
                "synthetic duplicate-key row",
                "",
                None,
                str(duplicate_path),
            ),
        )
    with pytest.raises(ExecutionArtifactIntegrityError, match="decoder 驗證失敗"):
        corrupt_query.get_legacy_original_payload(duplicate_id)
    assert duplicate_path.read_bytes() == duplicate_raw


def test_legacy_original_projection_fails_closed_on_canonical_claim_and_collision(
    tmp_path: Path,
) -> None:
    result_id = "r016-canonical-claim"
    runs_dir, store, queries = _stack(tmp_path)
    runs_dir.mkdir(parents=True)
    raw = _raw_payload(result_id)
    (runs_dir / f"{result_id}.json").write_bytes(raw)
    assert store._ensure_schema(create=True)
    canonical_claim = "sha256:" + "c" * 64
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            """
            INSERT INTO result_artifact_metadata
                (result_id, payload_hash, label, notes, persisted_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (result_id, canonical_claim, "", "", None),
        )

    with pytest.raises(ExecutionArtifactIntegrityError, match="metadata claim"):
        queries.get_legacy_original_payload(
            result_id,
            allow_unindexed_legacy=True,
        )

    canonical_raw = Path(__file__).parent.joinpath(
        "fixtures", "c1_consumer_readiness", "r016_execution_rev2.json"
    ).read_bytes()
    envelope = decode_execution_envelope(canonical_raw)
    assert store.get_index(envelope.execution.result_id) is None
    canonical_metadata = ArtifactIndexMetadata(
        result_id=envelope.execution.result_id,
        payload_hash=envelope.payload_hash,
        artifact_sha256=envelope.raw_payload_sha256,
        schema_version=envelope.schema_version,
        schema_revision=envelope.schema_revision,
        label="synthetic canonical",
        notes="",
        persisted_at="2026-09-23T00:00:00+00:00",
    )
    store.publish_artifact(canonical_raw, canonical_metadata)
    store.index_artifact(canonical_metadata)
    # An exact-ID legacy file must not be selected when the canonical index owns the ID.
    canonical_legacy_path = runs_dir / f"{envelope.execution.result_id}.json"
    canonical_legacy_raw = _raw_payload(envelope.execution.result_id)
    canonical_legacy_path.write_bytes(canonical_legacy_raw)
    with pytest.raises(ExecutionArtifactIntegrityError, match="legacy-only original-payload"):
        queries.get_legacy_original_payload(
            envelope.execution.result_id,
            allow_unindexed_legacy=True,
        )
    assert canonical_legacy_path.read_bytes() == canonical_legacy_raw


def test_registered_legacy_sqlite_uses_delete_mode_in_memory_snapshot(
    tmp_path: Path,
) -> None:
    result_id = "r016-delete-mode-snapshot"
    runs_dir, _store, queries = _stack(tmp_path)
    _register_legacy(runs_dir, result_id, _raw_payload(result_id))
    database_path = runs_dir / "recommendation_runs.db"
    raw_database = database_path.read_bytes()
    assert raw_database[18:20] == b"\x01\x01"

    reader = queries._legacy_reader
    assert isinstance(reader, SQLiteLegacyRecommendationRawByteReader)
    connection = reader._connect_read_only()
    assert connection is not None
    try:
        assert connection.execute("PRAGMA query_only").fetchone() == (1,)
        assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert connection.execute(
            "SELECT result_id FROM runs"
        ).fetchone() == (result_id,)
    finally:
        connection.close()


@pytest.mark.parametrize("suffix", ("-wal", "-shm", "-journal"))
def test_registered_legacy_sqlite_rejects_each_sidecar(
    tmp_path: Path,
    suffix: str,
) -> None:
    result_id = f"r016-sidecar-{suffix[1:]}"
    runs_dir, _store, queries = _stack(tmp_path)
    _register_legacy(runs_dir, result_id, _raw_payload(result_id))
    sidecar = runs_dir / f"recommendation_runs.db{suffix}"
    sidecar.write_bytes(b"synthetic sidecar")

    with pytest.raises(ExecutionArtifactIntegrityError, match="sidecar"):
        queries._legacy_reader._connect_read_only()  # type: ignore[union-attr]
    assert sidecar.read_bytes() == b"synthetic sidecar"


def test_registered_legacy_sqlite_rejects_wal_header_even_without_sidecars(
    tmp_path: Path,
) -> None:
    runs_dir, _store, queries = _stack(tmp_path)
    runs_dir.mkdir(parents=True)
    database_path = runs_dir / "recommendation_runs.db"
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        connection.execute(
            "CREATE TABLE runs "
            "(result_id TEXT, result_name TEXT, notes TEXT, created_at TEXT, data_path TEXT)"
        )
        connection.commit()
    connection.close()
    assert database_path.read_bytes()[18:20] == b"\x02\x02"
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = runs_dir / f"recommendation_runs.db{suffix}"
        sidecar.unlink(missing_ok=True)
        assert not os.path.lexists(runs_dir / f"recommendation_runs.db{suffix}")

    with pytest.raises(ExecutionArtifactIntegrityError, match="WAL"):
        queries._legacy_reader._connect_read_only()  # type: ignore[union-attr]


def test_registered_legacy_sqlite_rejects_incomplete_runs_schema(
    tmp_path: Path,
) -> None:
    runs_dir, _store, queries = _stack(tmp_path)
    runs_dir.mkdir(parents=True)
    with sqlite3.connect(runs_dir / "recommendation_runs.db") as connection:
        connection.execute("CREATE TABLE runs (result_id TEXT PRIMARY KEY)")

    with pytest.raises(ExecutionArtifactIntegrityError, match="schema"):
        queries._legacy_reader._connect_read_only()  # type: ignore[union-attr]


def test_registered_legacy_sqlite_rejects_integrity_check_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_id = "r016-integrity-check-failure"
    runs_dir, _store, queries = _stack(tmp_path)
    _register_legacy(runs_dir, result_id, _raw_payload(result_id))
    from app_module.recommendation import queries as queries_module

    class _FakeCursor:
        def __init__(self, rows: list[tuple[str, ...]]) -> None:
            self._rows = rows

        def fetchall(self) -> list[tuple[str, ...]]:
            return self._rows

    class _CorruptSnapshotConnection:
        closed = False
        deserialized: bytes | None = None

        def deserialize(self, payload: bytes) -> None:
            self.deserialized = payload

        def execute(self, statement: str) -> _FakeCursor:
            assert statement in {
                "PRAGMA query_only = ON",
                "PRAGMA integrity_check",
            }
            if statement == "PRAGMA integrity_check":
                return _FakeCursor([("database disk image is malformed",)])
            return _FakeCursor([])

        def close(self) -> None:
            self.closed = True

    snapshot = _CorruptSnapshotConnection()
    monkeypatch.setattr(
        queries_module.sqlite3,
        "connect",
        lambda *args, **_kwargs: snapshot
        if args == (":memory:",)
        else pytest.fail("query path must never open a pathname SQLite URI"),
    )
    with pytest.raises(ExecutionArtifactIntegrityError, match="integrity_check"):
        queries._legacy_reader._connect_read_only()  # type: ignore[union-attr]
    assert snapshot.deserialized is not None
    assert snapshot.closed


def test_registered_legacy_sqlite_rejects_sidecar_appearing_during_pinned_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_id = "r016-sidecar-appears-during-read"
    runs_dir, _store, queries = _stack(tmp_path)
    _register_legacy(runs_dir, result_id, _raw_payload(result_id))
    from app_module.recommendation import queries as queries_module

    sidecar = runs_dir / "recommendation_runs.db-wal"
    sidecar_checks = 0
    memory_connection_calls: list[tuple[object, ...]] = []
    original_connect = queries_module.sqlite3.connect

    def track_memory_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        memory_connection_calls.append(args)
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(queries_module.sqlite3, "connect", track_memory_connect)
    if os.name == "nt":
        original_sidecar_check = queries_module._windows_assert_no_sqlite_sidecars

        def create_after_read_windows(database_name: str, root: Path) -> None:
            nonlocal sidecar_checks
            sidecar_checks += 1
            if sidecar_checks == 2:
                sidecar.write_bytes(b"appeared during read")
            original_sidecar_check(database_name, root)

        monkeypatch.setattr(
            queries_module,
            "_windows_assert_no_sqlite_sidecars",
            create_after_read_windows,
        )
    else:
        original_sidecar_check = queries_module._posix_assert_no_sqlite_sidecars

        def create_after_read_posix(database_name: str, directory_fd: int) -> None:
            nonlocal sidecar_checks
            sidecar_checks += 1
            if sidecar_checks == 2:
                sidecar.write_bytes(b"appeared during read")
            original_sidecar_check(database_name, directory_fd)

        monkeypatch.setattr(
            queries_module,
            "_posix_assert_no_sqlite_sidecars",
            create_after_read_posix,
        )

    with pytest.raises(ExecutionArtifactIntegrityError, match="sidecar"):
        queries._legacy_reader._connect_read_only()  # type: ignore[union-attr]
    assert sidecar_checks == 2
    assert sidecar.read_bytes() == b"appeared during read"
    assert memory_connection_calls == []


def test_windows_database_leaf_disappearance_after_lstat_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name != "nt":
        pytest.skip("Windows database leaf race 模擬僅適用 Windows query path")
    result_id = "r016-windows-db-leaf-disappears"
    runs_dir, _store, queries = _stack(tmp_path)
    _register_legacy(runs_dir, result_id, _raw_payload(result_id))
    from app_module.recommendation import queries as queries_module

    database_path = runs_dir / "recommendation_runs.db"
    original_lstat = Path.lstat
    original_open = queries_module._windows_open_nofollow_handle

    def report_existing_database(path: Path) -> os.stat_result | SimpleNamespace:
        if path == database_path:
            return SimpleNamespace(st_mode=stat.S_IFREG | 0o600)
        return original_lstat(path)

    def disappear_after_lstat(path: Path, *, directory: bool) -> int:
        if not directory and path == database_path:
            raise FileNotFoundError(2, "database entry disappeared after lstat")
        return original_open(path, directory=directory)

    monkeypatch.setattr(Path, "lstat", report_existing_database)
    monkeypatch.setattr(
        queries_module,
        "_windows_open_nofollow_handle",
        disappear_after_lstat,
    )
    with pytest.raises(ExecutionArtifactIntegrityError, match="Windows no-follow handles"):
        queries._legacy_reader._connect_read_only()  # type: ignore[union-attr]


def test_registered_legacy_sqlite_rejects_missing_deserialize_without_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_id = "r016-no-deserialize"
    runs_dir, _store, queries = _stack(tmp_path)
    _register_legacy(runs_dir, result_id, _raw_payload(result_id))
    from app_module.recommendation import queries as queries_module

    class _UnsupportedConnection:
        closed = False

        def close(self) -> None:
            self.closed = True

    unsupported = _UnsupportedConnection()
    connect_calls: list[tuple[object, ...]] = []

    def memory_only_connect(*args: object, **_kwargs: object) -> _UnsupportedConnection:
        connect_calls.append(args)
        assert args == (":memory:",)
        return unsupported

    monkeypatch.setattr(
        queries_module.sqlite3,
        "connect",
        memory_only_connect,
    )
    with pytest.raises(ExecutionIndexReadError, match="拒絕 pathname fallback"):
        queries._legacy_reader._connect_read_only()  # type: ignore[union-attr]
    assert connect_calls == [(":memory:",)]
    assert unsupported.closed


def test_stable_database_reader_rejects_fstat_change_during_bytes_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_module.recommendation import queries as queries_module

    before = SimpleNamespace(
        st_dev=1,
        st_ino=2,
        st_mode=stat.S_IFREG | 0o600,
        st_size=7,
        st_mtime_ns=10,
        st_ctime_ns=11,
    )
    after = SimpleNamespace(
        st_dev=1,
        st_ino=2,
        st_mode=stat.S_IFREG | 0o600,
        st_size=7,
        st_mtime_ns=12,
        st_ctime_ns=11,
    )
    snapshots = iter((before, after))

    class _ChangingHandle:
        def fileno(self) -> int:
            return 77

        def read(self) -> bytes:
            return b"payload"

    monkeypatch.setattr(
        queries_module.os,
        "fstat",
        lambda _descriptor: next(snapshots),
    )
    with pytest.raises(ExecutionArtifactIntegrityError, match="bytes/stat 改變"):
        queries_module._read_stable_regular_file(
            _ChangingHandle(),  # type: ignore[arg-type]
            "synthetic database",
        )


def test_windows_dangling_sidecar_reparse_fails_closed_deterministically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_module.recommendation import queries as queries_module

    runs_dir = tmp_path / "runs"
    sidecar = runs_dir / "recommendation_runs.db-wal"
    original_lstat = Path.lstat
    opened: list[Path] = []

    def report_dangling_reparse(path: Path) -> os.stat_result | SimpleNamespace:
        if path == sidecar:
            # A dangling symlink still has a directory entry even though its
            # target cannot be opened on the host without symlink privileges.
            return SimpleNamespace(
                st_mode=stat.S_IFLNK | 0o777,
                st_file_attributes=0,
            )
        return original_lstat(path)

    def forbidden_open(path: Path, *, directory: bool) -> int:
        opened.append(path)
        raise AssertionError("reparse metadata must reject before open")

    monkeypatch.setattr(Path, "lstat", report_dangling_reparse)
    monkeypatch.setattr(
        queries_module,
        "_windows_open_nofollow_handle",
        forbidden_open,
    )
    with pytest.raises(ExecutionArtifactIntegrityError, match="symlink/reparse"):
        queries_module._windows_assert_no_sqlite_sidecars(
            "recommendation_runs.db",
            runs_dir,
        )
    assert opened == []


def test_windows_sidecar_disappearance_after_lstat_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_module.recommendation import queries as queries_module

    runs_dir = tmp_path / "runs"
    sidecar = runs_dir / "recommendation_runs.db-wal"
    original_lstat = Path.lstat

    def report_regular_entry(path: Path) -> os.stat_result | SimpleNamespace:
        if path == sidecar:
            return SimpleNamespace(
                st_mode=stat.S_IFREG | 0o600,
                st_file_attributes=0,
            )
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", report_regular_entry)
    monkeypatch.setattr(
        queries_module,
        "_windows_open_nofollow_handle",
        lambda _path, *, directory: (_ for _ in ()).throw(FileNotFoundError(2, "gone")),
    )
    with pytest.raises(ExecutionArtifactIntegrityError, match="前後改變"):
        queries_module._windows_assert_no_sqlite_sidecars(
            "recommendation_runs.db",
            runs_dir,
        )


def test_posix_root_walk_rejects_swapped_ancestor_before_opening_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_module.recommendation import queries as queries_module

    root = PurePosixPath("/fixture/root/runs")
    opened, closed = _mock_posix_dirfd_io(monkeypatch, fail_open_path="root")

    with pytest.raises(OSError, match="simulated no-follow swap"):
        queries_module._posix_open_directory_chain_no_follow(root)  # type: ignore[arg-type]

    assert [entry[0] for entry in opened] == ["/", "fixture", "root"]
    assert opened[0][2] is None
    assert opened[1][2] == 900
    assert opened[2][2] == 901
    nofollow = getattr(os, "O_NOFOLLOW")
    directory_flag = getattr(os, "O_DIRECTORY")
    assert all(flags & nofollow and flags & directory_flag for _, flags, _ in opened)
    assert closed == [901, 900]


def test_posix_database_open_rejects_swapped_db_entry_after_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_module.recommendation import queries as queries_module

    root = PurePosixPath("/fixture/root/runs")
    database = root / "recommendation_runs.db"
    opened, closed = _mock_posix_dirfd_io(
        monkeypatch,
        fail_open_path="recommendation_runs.db",
    )
    monkeypatch.setattr(
        queries_module,
        "_posix_assert_no_sqlite_sidecars",
        lambda _name, _directory_fd: None,
    )
    monkeypatch.setattr(
        queries_module.os,
        "stat",
        lambda path, **_kwargs: SimpleNamespace(
            st_mode=stat.S_IFREG | 0o600,
        )
        if path == database.name
        else pytest.fail(f"unexpected stat path: {path}"),
    )

    with pytest.raises(ExecutionArtifactIntegrityError, match="filesystem-root"):
        queries_module._posix_read_sqlite_database_no_follow(
            database,  # type: ignore[arg-type]
            root,  # type: ignore[arg-type]
        )

    assert [entry[0] for entry in opened] == [
        "/",
        "fixture",
        "root",
        "runs",
        "recommendation_runs.db",
    ]
    assert opened[-1][2] == 903  # pinned runs root fd, not a new path walk
    assert opened[-1][1] & getattr(os, "O_NOFOLLOW")
    assert closed == [903, 902, 901, 900]


def test_posix_database_missing_after_entry_preflight_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_module.recommendation import queries as queries_module

    root = PurePosixPath("/fixture/root/runs")
    database = root / "recommendation_runs.db"
    opened, closed = _mock_posix_dirfd_io(
        monkeypatch,
        fail_open_path="recommendation_runs.db",
        fail_open_error=errno.ENOENT,
    )
    monkeypatch.setattr(
        queries_module,
        "_posix_assert_no_sqlite_sidecars",
        lambda _name, _directory_fd: None,
    )
    monkeypatch.setattr(
        queries_module.os,
        "stat",
        lambda path, **_kwargs: SimpleNamespace(
            st_mode=stat.S_IFREG | 0o600,
        )
        if path == database.name
        else pytest.fail(f"unexpected stat path: {path}"),
    )

    with pytest.raises(ExecutionArtifactIntegrityError, match="filesystem-root"):
        try:
            queries_module._posix_read_sqlite_database_no_follow(
                database,  # type: ignore[arg-type]
                root,  # type: ignore[arg-type]
            )
        except ExecutionArtifactIntegrityError as exc:
            assert isinstance(exc.__cause__, OSError)
            assert exc.__cause__.errno == errno.ENOENT
            raise
    assert opened[-1][0] == "recommendation_runs.db"
    assert closed == [903, 902, 901, 900]
