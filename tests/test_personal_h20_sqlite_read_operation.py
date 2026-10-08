"""個人 H20 多來源唯讀 SQLite operation 的合成生命週期測試。"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sqlite3
from typing import Any, Callable, cast

import pytest

from data_module.pinned_sqlite_read_session import PinnedSQLiteReadSession
from scripts.scheduled.personal_h20_sqlite_read_operation import (
    PersonalH20SQLiteReadOperation,
)


def _create_database(path: Path, value: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE saved_values (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO saved_values VALUES ('only', ?)", (value,))
    return sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def roots(tmp_path: Path) -> tuple[Path, Path]:
    source_root = tmp_path / "source"
    private_root = tmp_path.parent / f"{tmp_path.name}-private-reader"
    source_root.mkdir()
    private_root.mkdir()
    return source_root, private_root


def test_same_source_binding_reuses_one_active_copy_and_finishes_once(
    roots: tuple[Path, Path],
) -> None:
    source_root, private_root = roots
    database = source_root / "snapshot.sqlite"
    expected_sha = _create_database(database, "fixed")
    original_bytes = database.read_bytes()

    with PersonalH20SQLiteReadOperation(private_root=private_root) as operation:
        first = operation.session_for(database, expected_sha)
        second = operation.session_for(database, expected_sha)
        assert first is second
        assert type(first) is PinnedSQLiteReadSession
        assert first.connection.in_transaction
        assert first.connection.execute("SELECT value FROM saved_values").fetchone() == ("fixed",)
        bindings = operation.finish()

    assert len(bindings) == 1
    assert bindings[0].original_main_sha256 == expected_sha
    assert not list(private_root.iterdir())
    assert database.read_bytes() == original_bytes


def test_distinct_source_bindings_get_distinct_copies_under_one_operation(
    roots: tuple[Path, Path],
) -> None:
    source_root, private_root = roots
    first_database = source_root / "first.sqlite"
    second_database = source_root / "second.sqlite"
    first_sha = _create_database(first_database, "first")
    second_sha = _create_database(second_database, "second")

    with PersonalH20SQLiteReadOperation(private_root=private_root) as operation:
        first = operation.session_for(first_database, first_sha)
        second = operation.session_for(second_database, second_sha)
        assert first is not second
        assert first.reader_database_path != second.reader_database_path
        assert first.connection.execute("SELECT value FROM saved_values").fetchone() == ("first",)
        assert second.connection.execute("SELECT value FROM saved_values").fetchone() == ("second",)
        bindings = operation.finish()

    assert {binding.original_database_path for binding in bindings} == {
        str(first_database.resolve()),
        str(second_database.resolve()),
    }
    assert not list(private_root.iterdir())


def test_cached_source_uses_canonical_case_and_rejects_closed_connection(
    roots: tuple[Path, Path],
) -> None:
    source_root, private_root = roots
    database = source_root / "Snapshot.sqlite"
    expected_sha = _create_database(database, "fixed")

    operation = PersonalH20SQLiteReadOperation(private_root=private_root)
    operation.__enter__()
    first = operation.session_for(database, expected_sha)
    # Windows 路徑比對不分大小寫；同一實體檔案不可因此複製第二份。
    same_path_different_case = Path(str(database).upper())
    second = operation.session_for(same_path_different_case, expected_sha)
    assert first is second
    first.connection.close()
    with pytest.raises(ValueError, match="session|transaction|active"):
        operation.session_for(database, expected_sha)
    operation.close()
    assert not list(private_root.iterdir())


def test_changed_later_source_fails_without_returning_partial_bindings_and_cleans_all_copies(
    roots: tuple[Path, Path],
) -> None:
    source_root, private_root = roots
    first_database = source_root / "first.sqlite"
    second_database = source_root / "second.sqlite"
    first_sha = _create_database(first_database, "first")
    second_sha = _create_database(second_database, "second")

    operation = PersonalH20SQLiteReadOperation(private_root=private_root)
    operation.__enter__()
    operation.session_for(first_database, first_sha)
    operation.session_for(second_database, second_sha)
    with sqlite3.connect(second_database) as connection:
        connection.execute("UPDATE saved_values SET value='changed' WHERE key='only'")

    with pytest.raises(ValueError, match="source_changed"):
        operation.finish()
    assert not list(private_root.iterdir())
    operation.close()


def test_wrong_hash_and_invalid_cancel_callback_fail_before_new_copy(
    roots: tuple[Path, Path],
) -> None:
    source_root, private_root = roots
    database = source_root / "snapshot.sqlite"
    expected_sha = _create_database(database, "fixed")

    operation = PersonalH20SQLiteReadOperation(
        private_root=private_root,
        cancel_callback=cast(Callable[[], bool], lambda: 1),
    )
    operation.__enter__()
    with pytest.raises(TypeError, match="bool"):
        operation.session_for(database, expected_sha)
    operation.close()
    assert not list(private_root.iterdir())

    with PersonalH20SQLiteReadOperation(private_root=private_root) as clean_operation:
        with pytest.raises(ValueError, match="source_changed|hash|sha_mismatch"):
            clean_operation.session_for(database, "0" * 64)
    assert not list(private_root.iterdir())


def test_empty_operation_polls_cancellation_before_publishing_empty_bindings(
    roots: tuple[Path, Path],
) -> None:
    _, private_root = roots
    cancelled = [False]
    operation = PersonalH20SQLiteReadOperation(
        private_root=private_root,
        cancel_callback=lambda: cancelled[0],
    )
    operation.__enter__()
    cancelled[0] = True
    with pytest.raises(InterruptedError, match="cancelled"):
        operation.finish()
    assert not list(private_root.iterdir())


def test_pinned_context_loader_uses_operation_copy_after_file_pin_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.test_current_observed_learning_capture import _write_pinned_context_fixture
    import ml_module.recommendation_calibration_evidence as evidence

    fixture = _write_pinned_context_fixture(tmp_path, monkeypatch)
    database = fixture["frozen_snapshot_database"]
    assert isinstance(database, Path)
    private_root = tmp_path.parent / f"{tmp_path.name}-private-reader"
    private_root.mkdir()
    original_hash_reader = evidence._sha256_file
    original_connect = sqlite3.connect
    opened_targets: list[str] = []

    def no_original_hash(path: str | Path) -> str:
        assert Path(path).resolve() != database.resolve()
        return original_hash_reader(Path(path))

    def guarded_connect(database_value: object, *args: object, **kwargs: object) -> sqlite3.Connection:
        target = str(database_value)
        opened_targets.append(target)
        assert str(database.resolve()) not in target
        assert "pinned-sqlite-" in target
        connector = cast(Callable[..., sqlite3.Connection], original_connect)
        return connector(database_value, *args, **kwargs)

    monkeypatch.setattr(evidence, "_sha256_file", no_original_hash)
    monkeypatch.setattr(sqlite3, "connect", guarded_connect)
    operation = PersonalH20SQLiteReadOperation(private_root=private_root)
    with operation:
        context = evidence.load_current_observed_context_from_pinned_snapshot(
            fixture,
            read_session_resolver=operation.session_for,
        )
        session = operation.session_for(
            context.snapshot_database_path,
            context.snapshot_database_sha256,
        )
        assert session.connection.in_transaction
        assert session.connection.execute("SELECT COUNT(*) FROM source_observation").fetchone() == (1,)
        assert len(opened_targets) == 1
        bindings = operation.finish()

    assert len(bindings) == 1
    assert not list(private_root.iterdir())


def test_entry_observation_revalidation_uses_the_same_readonly_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.test_current_observed_learning_capture import (
        _create_entry_db,
        _file_sha256,
        _open_session_evidence,
        _pins,
        _read_current_observed_entry_prices,
    )
    from datetime import date

    import ml_module.recommendation_calibration_evidence as evidence

    database = tmp_path / "snapshot.sqlite"
    _create_entry_db(database)
    source_pins = _pins(database)
    observation = _read_current_observed_entry_prices(
        snapshot_database=database,
        expected_database_sha256=_file_sha256(database),
        decision_date=date(2026, 10, 5),
        cycle_source_date="2026-10-05",
        decision_session_evidence=_open_session_evidence(date(2026, 10, 5), tmp_path),
        symbols=("1477",),
        source_pins=source_pins,
    )
    assert observation["status"] == "captured"
    snapshot = {
        "decision_date": "2026-10-05",
        "cycle_source_date": "2026-10-05",
        "cycle_id": source_pins["cycle_id"],
        "raw_run_id": source_pins["raw_run_id"],
        "cycle_terminal_path": source_pins["cycle_terminal_path"],
        "cycle_terminal_sha256": source_pins["cycle_terminal_sha256"],
        "snapshot_database_path": str(database.resolve()),
        "snapshot_database_sha256": _file_sha256(database),
        "snapshot_receipt_path": source_pins["snapshot_receipt_path"],
        "snapshot_receipt_sha256": source_pins["snapshot_receipt_sha256"],
        "source_context_envelope_path": source_pins["source_context_envelope_path"],
        "source_context_envelope_sha256": source_pins["source_context_envelope_sha256"],
        "symbols": ["1477"],
    }
    private_root = tmp_path.parent / f"{tmp_path.name}-private-reader"
    private_root.mkdir()
    real_connect = sqlite3.connect
    opened_targets: list[str] = []

    def guarded_connect(database_value: object, *args: object, **kwargs: object) -> sqlite3.Connection:
        target = str(database_value)
        opened_targets.append(target)
        assert str(database.resolve()) not in target
        assert "pinned-sqlite-" in target
        connector = cast(Callable[..., sqlite3.Connection], real_connect)
        return connector(database_value, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", guarded_connect)
    operation = PersonalH20SQLiteReadOperation(private_root=private_root)
    with operation:
        session = operation.session_for(database, _file_sha256(database))
        evidence._verify_current_observed_entry_observation(
            snapshot,
            observation,
            read_session=session,
        )
        assert len(opened_targets) == 1
        operation.finish()
    assert not list(private_root.iterdir())


def test_public_input_capture_api_forwards_the_operation_resolver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    import ml_module.recommendation_calibration_evidence as evidence
    from ml_module.recommendation_calibration_training import (
        recommendation_cost_contract_hash,
        recommendation_label_registry_hash,
    )
    from ml_module.recommendation_cost_scenario import build_legacy_cost_scenario

    scenario = build_legacy_cost_scenario(80)
    entry_pin = {"symbol": "1477", "source_row_sha256": "a" * 64}
    benchmark_pin = {"symbol": "TAIEX", "source_row_sha256": "b" * 64}
    snapshot = {
        "schema_version": "recommendation-current-observed-feature-snapshot.v1",
        "entry_observation": {
            "status": "captured",
            "entry_price_pin_by_symbol": {"1477": entry_pin},
            "benchmark_entry_price_pin": benchmark_pin,
        },
    }
    binding = {
        "schema_version": "recommendation-calibration-capture-source-binding.v2",
        "current_observed_feature_snapshot": snapshot,
    }
    decision = "2026-10-05"
    body: dict[str, object] = {
        "schema_version": "recommendation-current-observed-input-capture.v1",
        "status": "captured",
        "current_restated": True,
        "research_only": True,
        "historical_pit_eligible": False,
        "formal_training_allowed": False,
        "natural_outcome_only": True,
        "decision_date": decision,
        "cycle_id": "cycle-1",
        "captured_at": datetime(2026, 10, 5, 16, 0, tzinfo=ZoneInfo("Asia/Taipei")).isoformat(),
        "source_contract_binding": binding,
        "rows": [{"symbol": "1477"}],
        "entry_price_pin_by_symbol": {"1477": entry_pin},
        "benchmark_entry_price_pin": benchmark_pin,
        "fixed_round_trip_cost_bp": 80,
        "cost_scenario": scenario.metadata(),
        "cost_status": "verified",
        "cost_scenario_id": scenario.scenario_id,
        "cost_scenario_version": scenario.scenario_version,
        "cost_scenario_hash": scenario.scenario_hash,
        "cost_scenario_basis": scenario.cost_basis,
        "cost_basis": scenario.cost_basis,
        "cost_contract_hash": recommendation_cost_contract_hash(80),
        "label_registry_hash": recommendation_label_registry_hash(),
    }
    content_hash = evidence._hash_payload(body)
    payload = {
        **body,
        "content_sha256": content_hash,
        "capture_id": f"current-observed:{decision}:cycle-1:{content_hash[7:]}",
    }
    def resolver(_path: Path, _sha: str) -> PinnedSQLiteReadSession:
        raise AssertionError("測試只確認公開 API 會傳遞 resolver")

    received: dict[str, object] = {}

    def source_contract_spy(
        _binding: object,
        **kwargs: object,
    ) -> dict[str, object]:
        received.update(kwargs)
        return {}

    monkeypatch.setattr(evidence, "_verify_source_contract_binding", source_contract_spy)
    result = evidence.verify_current_observed_input_capture(
        payload,
        read_session_resolver=resolver,
    )

    assert result["capture_id"] == payload["capture_id"]
    assert received["read_session_resolver"] is resolver


def test_scheduled_outcome_port_forwards_operation_resolver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ml_module import recommendation_natural_outcome_service as outcome_service
    from scripts.scheduled.run_personal_current_observed_h20_daily import _outcome_port

    received: dict[str, object] = {}

    def resolver(_path: Path, _sha256: str) -> PinnedSQLiteReadSession:
        raise AssertionError("transport test must not create a database session")

    def verify_spy(path: object, **kwargs: object) -> dict[str, object]:
        received["path"] = path
        received.update(kwargs)
        return {"verification_status": "verified"}

    monkeypatch.setattr(outcome_service, "verify_current_observed_outcome_receipt", verify_spy)
    result = _outcome_port(Path("receipt.json"), "pin", read_session_resolver=resolver)

    assert result["verification_status"] == "verified"
    assert received["read_session_resolver"] is resolver
    assert "source_binding_verifier" in received


def test_saved_outcome_receipt_reverifies_source_through_same_private_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import datetime, timezone

    from ml_module import recommendation_calibration_evidence as evidence
    from ml_module import recommendation_natural_outcome_service as outcome_module
    from ml_module.recommendation_natural_outcome_service import (
        RecommendationNaturalOutcomeService,
        _sha256_file,
        verify_current_observed_outcome_receipt,
    )
    from tests import test_recommendation_natural_outcomes_current_observed_batches as fixtures

    database_path = tmp_path / "pinned-current.sqlite"
    original_write_bytes = Path.write_bytes

    def write_sqlite_fixture(path: Path, data: bytes) -> int:
        if path.resolve() == database_path.resolve():
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "CREATE TABLE saved_values (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )
                connection.execute("INSERT INTO saved_values VALUES ('only', 'fixture')")
            return path.stat().st_size
        return original_write_bytes(path, data)

    monkeypatch.setattr(Path, "write_bytes", write_sqlite_fixture)
    capture = fixtures._v2_capture(17)
    capture_path = fixtures._write_capture(tmp_path, capture)
    monkeypatch.setattr(evidence, "verify_current_observed_input_capture", lambda *_args, **_kwargs: dict(capture))
    source, _calls, values, contract = fixtures._run_loader(
        monkeypatch,
        tmp_path,
        capture,
    )

    output_path = (
        tmp_path
        / "recommendation_learning"
        / "current_observed_outcomes"
        / fixtures.CAPTURE_DATE.isoformat()
        / "later-cycle"
        / "2026-10-07"
        / "operation-copy.json"
    )
    builder = RecommendationNaturalOutcomeService.__new__(RecommendationNaturalOutcomeService)
    monkeypatch.setattr(builder, "_load_current_observed_outcome_source", lambda **_kwargs: source)
    receipt = builder.build_current_observed_outcomes_for_capture(
        capture_path,
        required_source_contract=contract,
        evaluation_at=datetime.now(timezone.utc),
        output_path=output_path,
    )
    assert receipt["status"] == "matured"

    database_sha256 = _sha256_file(database_path)
    assert values["snapshot"]["snapshot_database_path"] == str(database_path.resolve())
    assert values["snapshot"]["snapshot_database_sha256"] == database_sha256
    original_source_bytes = database_path.read_bytes()
    private_root = tmp_path.parent / f"{tmp_path.name}-outcome-private"
    private_root.mkdir()
    session_ids: list[int] = []
    opened_sqlite_targets: list[str] = []
    original_connect = sqlite3.connect

    def guarded_connect(database: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        target = str(database)
        if str(database_path.resolve()).casefold() in target.casefold():
            raise AssertionError("outcome reader attempted to open the original source database")
        opened_sqlite_targets.append(target)
        return original_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", guarded_connect)

    def input_capture_spy(
        _path: object,
        *,
        expected_sha256: str | None = None,
        read_session_resolver: Callable[[Path, str], PinnedSQLiteReadSession] | None = None,
        **_kwargs: object,
    ) -> dict[str, object]:
        assert expected_sha256 == _sha256_file(capture_path)
        assert read_session_resolver is not None
        session = read_session_resolver(database_path, database_sha256)
        session_ids.append(id(session))
        assert session.connection.execute(
            "SELECT value FROM saved_values WHERE key = 'only'"
        ).fetchone() == ("fixture",)
        return dict(capture)

    def context_spy(
        _snapshot: object,
        *,
        read_session_resolver: Callable[[Path, str], PinnedSQLiteReadSession] | None = None,
    ) -> object:
        assert read_session_resolver is not None
        session = read_session_resolver(database_path, database_sha256)
        session_ids.append(id(session))
        return values["context"]

    class SessionCheckingProvider(outcome_module.MLHistoricalSnapshotProvider):
        def load_current_observed(self, **kwargs: Any) -> Any:
            session = kwargs.get("read_session")
            assert type(session) is PinnedSQLiteReadSession
            pinned_session = cast(PinnedSQLiteReadSession, session)
            session_ids.append(id(session))
            assert pinned_session.connection.execute(
                "SELECT value FROM saved_values WHERE key = 'only'"
            ).fetchone() == ("fixture",)
            return super().load_current_observed(**kwargs)

    monkeypatch.setattr(evidence, "verify_current_observed_input_capture", input_capture_spy)
    monkeypatch.setattr(evidence, "load_current_observed_context_from_pinned_snapshot", context_spy)
    monkeypatch.setattr(outcome_module, "MLHistoricalSnapshotProvider", SessionCheckingProvider)

    with PersonalH20SQLiteReadOperation(private_root=private_root) as operation:
        verified = verify_current_observed_outcome_receipt(
            output_path,
            expected_sha256=receipt["receipt_file_sha256"],
            capture_path=capture_path,
            read_session_resolver=operation.session_for,
        )
        assert verified["verification_status"] == "verified"
        assert verified["outcomes"] == receipt["outcomes"]
        assert session_ids and len(set(session_ids)) == 1
        bindings = operation.finish()

    assert len(bindings) == 1
    assert bindings[0].original_main_sha256 == database_sha256.removeprefix("sha256:")
    assert opened_sqlite_targets
    assert all("pinned-sqlite" in target.casefold() for target in opened_sqlite_targets)
    assert database_path.read_bytes() == original_source_bytes
    assert not list(private_root.iterdir())


def test_public_capture_replay_uses_copy_only_session_with_real_cycle_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ml_module.recommendation_calibration_evidence import (
        verify_current_observed_input_capture,
    )
    import test_current_observed_capacity_replay as cycle_fixtures

    capture_path, capture_sha256, _contract_path, _capture, _status_path, _terminal_path = (
        cycle_fixtures._fixture(tmp_path, monkeypatch, reuse=False)
    )
    verified_before = verify_current_observed_input_capture(
        capture_path,
        expected_sha256=capture_sha256,
    )
    feature_snapshot = verified_before["source_contract_binding"][
        "current_observed_feature_snapshot"
    ]
    source_database = Path(str(feature_snapshot["snapshot_database_path"])).resolve(strict=True)
    other_source_database = tmp_path / "mutable" / "canonical.db"
    source_bytes_before = source_database.read_bytes()
    source_stat_before = source_database.stat()
    source_identity_before = (
        source_stat_before.st_size,
        source_stat_before.st_mtime_ns,
        source_stat_before.st_ctime_ns,
        source_stat_before.st_nlink,
    )
    private_root = tmp_path.parent / f"{tmp_path.name}-full-capture-private"
    private_root.mkdir()
    opened_targets: list[str] = []
    original_connect = sqlite3.connect

    def guarded_connect(database: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        target = str(database)
        opened_targets.append(target)
        normalized = target.casefold()
        if str(source_database).casefold() in normalized or str(other_source_database).casefold() in normalized:
            raise AssertionError("public capture replay attempted to open an original source database")
        return original_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", guarded_connect)
    with PersonalH20SQLiteReadOperation(private_root=private_root) as operation:
        verified = verify_current_observed_input_capture(
            capture_path,
            expected_sha256=capture_sha256,
            read_session_resolver=operation.session_for,
        )
        assert verified["capture_id"] == verified_before["capture_id"]
        assert verified["source_contract_binding"]["current_observed_feature_snapshot"][
            "snapshot_database_sha256"
        ] == feature_snapshot["snapshot_database_sha256"]
        bindings = operation.finish()

    source_stat_after = source_database.stat()
    assert len(bindings) == 1
    assert bindings[0].original_main_sha256 == str(
        feature_snapshot["snapshot_database_sha256"]
    ).removeprefix("sha256:")
    assert opened_targets
    private_root_text = str(private_root).replace("\\", "/").casefold()
    assert all(
        private_root_text in target.replace("\\", "/").casefold()
        for target in opened_targets
    ), opened_targets
    assert source_database.read_bytes() == source_bytes_before
    assert (
        source_stat_after.st_size,
        source_stat_after.st_mtime_ns,
        source_stat_after.st_ctime_ns,
        source_stat_after.st_nlink,
    ) == source_identity_before
    assert not list(private_root.iterdir())
