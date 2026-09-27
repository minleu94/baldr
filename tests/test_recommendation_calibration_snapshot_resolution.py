"""Recommendation calibration learner 的同次 saved snapshot 綁定測試。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app_module.recommendation.contracts import (
    Context,
    ExecutionStatus,
    RecommendationConfigSnapshot,
    RecommendationExecution,
    RecommendationResultConfigSnapshot,
    Request,
    SnapshotCohort,
    SnapshotCohortCoverageStatus,
)
from app_module.recommendation.persistence import (
    ExecutionArtifactIntegrityError,
    RecommendationExecutionPersistence,
)
from data_module.result_artifact_store import ResultArtifactStore
from decision_module.recommendation.contracts import DecisionBatch, RecommendationItem
from scripts.scheduled import run_daily_recommendation_learning as learner
from scripts.scheduled import run_daily_recommendation_learning_pipeline as learning_pipeline


TAIPEI = ZoneInfo("Asia/Taipei")
DECISION_DATE = date(2026, 9, 25)
DATA_DATE = date(2026, 9, 24)
SNAPSHOT_TASK = "baldr-recommendation-snapshot-daily"


def _cohort(symbol: str) -> tuple[dict[str, object], SnapshotCohort]:
    body: dict[str, object] = {
        "schema_version": "scheduled-recommendation-snapshot-cohort.v1",
        "requested_symbols": [symbol],
        "eligible_symbols": [symbol],
        "missing_symbols": [],
        "degraded_symbols": [],
        "excluded_symbols": [],
        "requested_count": 1,
        "eligible_count": 1,
        "missing_count": 0,
        "degraded_count": 0,
        "excluded_count": 0,
        "coverage_status": "complete",
        "coverage_by_symbol": {},
        "eligible_definition": "final scheduled recommendation DTO rows",
        "missing_definition": "screening rows with quality=missing; same-day retry candidates",
        "degraded_definition": "screening rows with quality=degraded; visible but not source-missing",
        "excluded_definition": "requested rows not selected and not missing/degraded",
    }
    body["cohort_hash"] = "sha256:" + hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    cohort = SnapshotCohort(
        cohort_hash=str(body["cohort_hash"]),
        requested_symbols=(symbol,),
        eligible_symbols=(symbol,),
        requested_count=1,
        eligible_count=1,
        coverage_status=SnapshotCohortCoverageStatus.COMPLETE,
    )
    return body, cohort


def _read_model(
    result_id: str,
    symbol: str,
    *,
    decision_date: date = DECISION_DATE,
    request_data_date: date = DATA_DATE,
    context_data_date: date = DATA_DATE,
    available_at: datetime | None = datetime(2026, 9, 25, 12, 0, tzinfo=TAIPEI),
) -> SimpleNamespace:
    cohort_payload, cohort = _cohort(symbol)
    config: dict[str, object] = {
        "scheduled_snapshot": True,
        "decision_date": decision_date.isoformat(),
        "data_as_of_date": DATA_DATE.isoformat(),
        "snapshot_cohort": cohort_payload,
    }
    config_bytes = json.dumps(
        config,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    result_config = RecommendationResultConfigSnapshot(
        raw_result_config_json=config_bytes,
        config_sha256="sha256:" + hashlib.sha256(config_bytes.encode("utf-8")).hexdigest(),
    )
    execution = SimpleNamespace(
        result_id=result_id,
        status=ExecutionStatus.COMPLETED,
        request=SimpleNamespace(as_of_date=request_data_date),
        context=SimpleNamespace(
            as_of_date=context_data_date,
            decision_at=datetime(2026, 9, 25, 12, 1, tzinfo=TAIPEI),
            available_at=available_at,
            snapshot_cohort=cohort,
            result_config_snapshot=result_config,
        ),
        decision=SimpleNamespace(items=(SimpleNamespace(stock_code=symbol),)),
    )
    return SimpleNamespace(
        result_id=result_id,
        execution=execution,
        integrity_basis="canonical_payload_and_index_verified",
        schema_version="recommendation-execution.v1",
        schema_revision=2,
        raw_artifact_sha256="sha256:" + "a" * 64,
        payload_hash="sha256:" + "b" * 64,
    )


class _Queries:
    def __init__(self, read_models: dict[str, object]) -> None:
        self.read_models = read_models
        self.requested_ids: list[str] = []

    def get(self, result_id: str):
        self.requested_ids.append(result_id)
        value = self.read_models.get(result_id)
        if isinstance(value, BaseException):
            raise value
        return value


def _install_queries(monkeypatch: pytest.MonkeyPatch, queries: _Queries) -> list[Path]:
    captured_runs_dirs: list[Path] = []

    def build(_config, *, runs_dir: Path):
        captured_runs_dirs.append(Path(runs_dir))
        return queries

    monkeypatch.setattr(learner, "build_recommendation_execution_queries", build)
    return captured_runs_dirs


def _write_invocation_stdout(
    output_root: Path,
    *,
    result_id: str,
    decision_date: date = DECISION_DATE,
    cohort_payload: dict[str, object],
) -> tuple[Path, str]:
    payload = {
        "task": SNAPSHOT_TASK,
        "status": "passed",
        "decision_date": decision_date.isoformat(),
        "result_id": result_id,
        "snapshot_cohort": cohort_payload,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    path = (
        output_root
        / "scheduled"
        / "recommendation_calibration_learning"
        / "runs"
        / f"test-{result_id}"
        / "recommendation_snapshot.stdout.bin"
    )
    path.parent.mkdir(parents=True, exist_ok=False)
    with path.open("xb") as stream:
        stream.write(raw)
    return path, "sha256:" + hashlib.sha256(raw).hexdigest()


def _read_model_cohort_payload(read_model: SimpleNamespace) -> dict[str, object]:
    snapshot = read_model.execution.context.result_config_snapshot
    return json.loads(snapshot.raw_result_config_json)["snapshot_cohort"]


def _save_real_scheduled_execution(
    output_root: Path,
    *,
    result_id: str,
) -> tuple[Path, dict[str, object], SnapshotCohort]:
    helper_path = Path(__file__).with_name("test_c1_forward_consumer_readiness.py")
    spec = importlib.util.spec_from_file_location(
        "snapshot_resolution_canonical_fixture_builder", helper_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("無法載入 scheduled canonical execution 合成 fixture")
    fixture_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture_module)
    fixture, _manifest_entry = fixture_module._fixture()
    execution = fixture_module._execution(fixture)
    original_snapshot = execution.context.result_config_snapshot
    assert original_snapshot is not None
    result_config = json.loads(original_snapshot.raw_result_config_json)
    result_config["data_as_of_date"] = execution.context.as_of_date.isoformat()
    result_config_json = json.dumps(
        result_config, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    result_config_snapshot = RecommendationResultConfigSnapshot(
        raw_result_config_json=result_config_json,
        config_sha256="sha256:" + hashlib.sha256(result_config_json.encode("utf-8")).hexdigest(),
    )
    execution = replace(
        execution,
        result_id=result_id,
        context=replace(
            execution.context,
            result_config_snapshot=result_config_snapshot,
        ),
    )
    cohort_payload: dict[str, object] = result_config["snapshot_cohort"]
    cohort = execution.context.snapshot_cohort
    assert cohort is not None
    assert tuple(item.stock_code for item in execution.decision.items) == cohort.eligible_symbols
    runs_dir = output_root / "recommendation" / "runs"
    store = ResultArtifactStore(
        artifact_root=runs_dir / "execution_artifacts",
        database_path=runs_dir / "recommendation_runs.db",
    )
    receipt = RecommendationExecutionPersistence(store).save(
        execution,
        label="合成 scheduled snapshot",
        now=lambda: datetime(2026, 9, 25, 4, tzinfo=TAIPEI),
    )
    assert receipt.artifact_location is not None
    return store.artifact_root / receipt.artifact_location, cohort_payload, cohort


def test_same_run_snapshot_binds_saved_query_identity_and_separates_decision_data_and_availability(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    read_model = _read_model("snapshot-current-run", "1101")
    queries = _Queries({"snapshot-current-run": read_model})
    captured_runs_dirs = _install_queries(monkeypatch, queries)
    stdout_path, stdout_hash = _write_invocation_stdout(
        tmp_path,
        result_id="snapshot-current-run",
        cohort_payload=_read_model_cohort_payload(read_model),
    )

    symbols, cohort, binding = learner._resolve_same_run_snapshot_input(
        output_root=tmp_path,
        decision_date=DECISION_DATE,
        result_id="snapshot-current-run",
        expected_cohort_hash=read_model.execution.context.snapshot_cohort.cohort_hash,
        expected_invocation_output_sha256=stdout_hash,
        invocation_output_path=str(stdout_path),
    )

    assert symbols == ("1101",)
    assert cohort["eligible_symbols"] == ["1101"]
    assert queries.requested_ids == ["snapshot-current-run"]
    assert captured_runs_dirs == [tmp_path.resolve() / "recommendation" / "runs"]
    assert binding["result_id"] == "snapshot-current-run"
    assert binding["raw_artifact_sha256"] == "sha256:" + "a" * 64
    assert binding["payload_hash"] == "sha256:" + "b" * 64
    assert binding["decision_date"] == "2026-09-25"
    assert binding["data_as_of_date"] == "2026-09-24"
    assert binding["available_at"] == "2026-09-25T12:00:00+08:00"
    assert binding["invocation_output_sha256"] == stdout_hash
    assert binding["invocation_output_path"] == str(stdout_path.resolve())
    assert binding["invocation_output_size"] == stdout_path.stat().st_size


def test_same_day_rerun_uses_exact_child_result_id_not_another_cohort_latest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first = _read_model("snapshot-run-A", "1101")
    second = _read_model("snapshot-run-B", "2330")
    queries = _Queries({"snapshot-run-A": first, "snapshot-run-B": second})
    _install_queries(monkeypatch, queries)
    stdout_path, stdout_hash = _write_invocation_stdout(
        tmp_path,
        result_id="snapshot-run-B",
        cohort_payload=_read_model_cohort_payload(second),
    )

    symbols, _cohort_value, binding = learner._resolve_same_run_snapshot_input(
        output_root=tmp_path,
        decision_date=DECISION_DATE,
        result_id="snapshot-run-B",
        expected_cohort_hash=second.execution.context.snapshot_cohort.cohort_hash,
        expected_invocation_output_sha256=stdout_hash,
        invocation_output_path=str(stdout_path),
    )

    assert symbols == ("2330",)
    assert binding["result_id"] == "snapshot-run-B"
    assert binding["cohort_hash"] == second.execution.context.snapshot_cohort.cohort_hash
    assert queries.requested_ids == ["snapshot-run-B"]


def test_same_run_snapshot_preserves_unknown_available_clock_without_inference(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    read_model = _read_model("snapshot-run-no-clock", "1101", available_at=None)
    _install_queries(monkeypatch, _Queries({"snapshot-run-no-clock": read_model}))
    stdout_path, stdout_hash = _write_invocation_stdout(
        tmp_path,
        result_id="snapshot-run-no-clock",
        cohort_payload=_read_model_cohort_payload(read_model),
    )

    _symbols, _cohort_value, binding = learner._resolve_same_run_snapshot_input(
        output_root=tmp_path,
        decision_date=DECISION_DATE,
        result_id="snapshot-run-no-clock",
        expected_cohort_hash=read_model.execution.context.snapshot_cohort.cohort_hash,
        expected_invocation_output_sha256=stdout_hash,
        invocation_output_path=str(stdout_path),
    )

    assert binding["decision_at"] == "2026-09-25T12:01:00+08:00"
    assert binding["available_at"] is None


def test_same_run_snapshot_rejects_conflicting_cohort_hash_and_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    read_model = _read_model("snapshot-run", "1101")
    queries = _Queries({"snapshot-run": read_model})
    _install_queries(monkeypatch, queries)
    stdout_path, stdout_hash = _write_invocation_stdout(
        tmp_path,
        result_id="snapshot-run",
        cohort_payload=_read_model_cohort_payload(read_model),
    )

    with pytest.raises(ValueError, match="cohort hash"):
        learner._resolve_same_run_snapshot_input(
            output_root=tmp_path,
            decision_date=DECISION_DATE,
            result_id="snapshot-run",
            expected_cohort_hash="sha256:" + "f" * 64,
            expected_invocation_output_sha256=stdout_hash,
            invocation_output_path=str(stdout_path),
        )
    with pytest.raises(ValueError, match="cohort hash 格式"):
        learner._resolve_same_run_snapshot_input(
            output_root=tmp_path,
            decision_date=DECISION_DATE,
            result_id="snapshot-run",
            expected_cohort_hash="not-a-hash",
            expected_invocation_output_sha256=stdout_hash,
            invocation_output_path=str(stdout_path),
        )


@pytest.mark.parametrize(
    ("request_data_date", "context_data_date", "decision_date"),
    (
        (date(2026, 9, 25), DATA_DATE, DECISION_DATE),
        (DATA_DATE, date(2026, 9, 23), DECISION_DATE),
        (DATA_DATE, DATA_DATE, date(2026, 9, 24)),
    ),
)
def test_same_run_snapshot_rejects_date_drift_without_collapsing_clock_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    request_data_date: date,
    context_data_date: date,
    decision_date: date,
) -> None:
    read_model = _read_model(
        "snapshot-run",
        "1101",
        decision_date=decision_date,
        request_data_date=request_data_date,
        context_data_date=context_data_date,
    )
    _install_queries(monkeypatch, _Queries({"snapshot-run": read_model}))
    stdout_path, stdout_hash = _write_invocation_stdout(
        tmp_path,
        result_id="snapshot-run",
        cohort_payload=_read_model_cohort_payload(read_model),
    )

    with pytest.raises(ValueError):
        learner._resolve_same_run_snapshot_input(
            output_root=tmp_path,
            decision_date=DECISION_DATE,
            result_id="snapshot-run",
            expected_cohort_hash=read_model.execution.context.snapshot_cohort.cohort_hash,
            expected_invocation_output_sha256=stdout_hash,
            invocation_output_path=str(stdout_path),
        )


def test_same_run_snapshot_does_not_fallback_after_query_integrity_failure_or_legacy_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    queries = _Queries(
        {"typed-corrupt": ExecutionArtifactIntegrityError("synthetic hash mismatch")}
    )
    _install_queries(monkeypatch, queries)
    corrupted = _read_model("typed-corrupt", "1101")
    stdout_path, stdout_hash = _write_invocation_stdout(
        tmp_path,
        result_id="typed-corrupt",
        cohort_payload=_read_model_cohort_payload(corrupted),
    )
    with pytest.raises(ExecutionArtifactIntegrityError, match="hash mismatch"):
        learner._resolve_same_run_snapshot_input(
            output_root=tmp_path,
            decision_date=DECISION_DATE,
            result_id="typed-corrupt",
            expected_cohort_hash=corrupted.execution.context.snapshot_cohort.cohort_hash,
            expected_invocation_output_sha256=stdout_hash,
            invocation_output_path=str(stdout_path),
        )

    legacy = _read_model("legacy-result", "1101")
    legacy.integrity_basis = "legacy_trusted_hash_verified"
    legacy_queries = _Queries({"legacy-result": legacy})
    _install_queries(monkeypatch, legacy_queries)
    legacy_stdout_path, legacy_stdout_hash = _write_invocation_stdout(
        tmp_path,
        result_id="legacy-result",
        cohort_payload=_read_model_cohort_payload(legacy),
    )
    with pytest.raises(ValueError, match="canonical verified"):
        learner._resolve_same_run_snapshot_input(
            output_root=tmp_path,
            decision_date=DECISION_DATE,
            result_id="legacy-result",
            expected_cohort_hash=legacy.execution.context.snapshot_cohort.cohort_hash,
            expected_invocation_output_sha256=legacy_stdout_hash,
            invocation_output_path=str(legacy_stdout_path),
        )


def test_cli_persists_terminal_fail_closed_status_on_typed_artifact_integrity_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    queries = _Queries(
        {"typed-corrupt": ExecutionArtifactIntegrityError("synthetic raw bytes mismatch")}
    )
    _install_queries(monkeypatch, queries)
    read_model = _read_model("typed-corrupt", "1101")
    stdout_path, stdout_hash = _write_invocation_stdout(
        tmp_path / "snapshot-output",
        result_id="typed-corrupt",
        cohort_payload=_read_model_cohort_payload(read_model),
    )
    monkeypatch.setattr(
        learner,
        "_taipei_now",
        lambda: datetime(2026, 9, 25, 12, 30, tzinfo=TAIPEI),
    )

    exit_code = learner.main(
        [
            "--data-root", str(tmp_path / "data"),
            "--output-root", str(tmp_path / "learning-output"),
            "--snapshot-output-root", str(tmp_path / "snapshot-output"),
            "--source-db", str(tmp_path / "data" / "synthetic.sqlite"),
            "--decision-date", DECISION_DATE.isoformat(),
            "--training-as-of", DECISION_DATE.isoformat(),
            "--snapshot-result-id", "typed-corrupt",
            "--snapshot-cohort-hash", read_model.execution.context.snapshot_cohort.cohort_hash,
            "--snapshot-invocation-output-sha256", stdout_hash,
            "--snapshot-invocation-output-path", str(stdout_path),
        ]
    )

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["symbol_source"] == "unresolved"
    assert payload["symbols"] == []
    assert payload["error"].startswith(
        "ExecutionArtifactIntegrityError: synthetic raw bytes mismatch"
    )
    assert payload["dependencies"]["diagnostics"] == [
        "symbol_cohort_preflight_failed:ExecutionArtifactIntegrityError"
    ]
    assert queries.requested_ids == ["typed-corrupt"]


def test_same_run_snapshot_resolves_a_real_persisted_canonical_artifact(
    tmp_path: Path,
) -> None:
    artifact_path, cohort_payload, cohort = _save_real_scheduled_execution(
        tmp_path,
        result_id="snapshot-persist-query-resolver",
    )
    original_artifact_bytes = artifact_path.read_bytes()
    stdout_path, stdout_hash = _write_invocation_stdout(
        tmp_path,
        result_id="snapshot-persist-query-resolver",
        decision_date=date(2026, 9, 22),
        cohort_payload=cohort_payload,
    )

    symbols, resolved_cohort, binding = learner._resolve_same_run_snapshot_input(
        output_root=tmp_path,
        decision_date=date(2026, 9, 22),
        result_id="snapshot-persist-query-resolver",
        expected_cohort_hash=cohort.cohort_hash,
        expected_invocation_output_sha256=stdout_hash,
        invocation_output_path=str(stdout_path),
    )

    assert symbols == ("AAA", "BET")
    assert resolved_cohort == cohort_payload
    assert binding["integrity_basis"] == "canonical_payload_and_index_verified"
    assert binding["result_id"] == "snapshot-persist-query-resolver"
    assert binding["data_as_of_date"] == "2026-09-21"
    assert binding["decision_date"] == "2026-09-22"
    assert binding["raw_artifact_sha256"] == (
        "sha256:" + hashlib.sha256(original_artifact_bytes).hexdigest()
    )


def test_same_run_snapshot_rejects_corrupt_bytes_from_a_real_persisted_artifact(
    tmp_path: Path,
) -> None:
    artifact_path, cohort_payload, cohort = _save_real_scheduled_execution(
        tmp_path,
        result_id="snapshot-corrupt-canonical-bytes",
    )
    stdout_path, stdout_hash = _write_invocation_stdout(
        tmp_path,
        result_id="snapshot-corrupt-canonical-bytes",
        decision_date=date(2026, 9, 22),
        cohort_payload=cohort_payload,
    )
    artifact_path.write_bytes(b"synthetic corruption")

    with pytest.raises(ExecutionArtifactIntegrityError):
        learner._resolve_same_run_snapshot_input(
            output_root=tmp_path,
            decision_date=date(2026, 9, 22),
            result_id="snapshot-corrupt-canonical-bytes",
            expected_cohort_hash=cohort.cohort_hash,
            expected_invocation_output_sha256=stdout_hash,
            invocation_output_path=str(stdout_path),
        )


def test_same_run_snapshot_rejects_changed_stdout_bytes_before_query(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    read_model = _read_model("snapshot-changed-stdout", "1101")
    queries = _Queries({"snapshot-changed-stdout": read_model})
    _install_queries(monkeypatch, queries)
    stdout_path, stdout_hash = _write_invocation_stdout(
        tmp_path,
        result_id="snapshot-changed-stdout",
        cohort_payload=_read_model_cohort_payload(read_model),
    )
    stdout_path.write_bytes(stdout_path.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="stdout SHA-256 不符"):
        learner._resolve_same_run_snapshot_input(
            output_root=tmp_path,
            decision_date=DECISION_DATE,
            result_id="snapshot-changed-stdout",
            expected_cohort_hash=read_model.execution.context.snapshot_cohort.cohort_hash,
            expected_invocation_output_sha256=stdout_hash,
            invocation_output_path=str(stdout_path),
        )
    assert queries.requested_ids == []


def test_same_run_snapshot_rejects_path_swap_during_bounded_nofollow_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    read_model = _read_model("snapshot-stdout-path-swap", "1101")
    queries = _Queries({"snapshot-stdout-path-swap": read_model})
    _install_queries(monkeypatch, queries)
    stdout_path, stdout_hash = _write_invocation_stdout(
        tmp_path,
        result_id="snapshot-stdout-path-swap",
        cohort_payload=_read_model_cohort_payload(read_model),
    )
    original_reader = learner._read_regular_file_no_follow

    def replace_after_read(path: Path, root: Path, *, max_bytes: int | None = None) -> bytes:
        payload = original_reader(path, root, max_bytes=max_bytes)
        path.write_bytes(payload + b"concurrent replacement")
        return payload

    monkeypatch.setattr(learner, "_read_regular_file_no_follow", replace_after_read)
    with pytest.raises(ValueError, match="在讀取期間改變"):
        learner._resolve_same_run_snapshot_input(
            output_root=tmp_path,
            decision_date=DECISION_DATE,
            result_id="snapshot-stdout-path-swap",
            expected_cohort_hash=read_model.execution.context.snapshot_cohort.cohort_hash,
            expected_invocation_output_sha256=stdout_hash,
            invocation_output_path=str(stdout_path),
        )
    assert queries.requested_ids == []


def test_existing_nofollow_reader_max_bytes_rejects_instead_of_truncating(
    tmp_path: Path,
) -> None:
    from app_module.recommendation.queries import _read_regular_file_no_follow

    root = tmp_path / "bounded-read-root"
    root.mkdir()
    target = root / "stdout.bin"
    target.write_bytes(b"123456")
    assert _read_regular_file_no_follow(target, root) == b"123456"
    with pytest.raises(ExecutionArtifactIntegrityError, match="大小上限"):
        _read_regular_file_no_follow(target, root, max_bytes=5)


def test_pipeline_pins_exact_snapshot_stdout_bytes_create_only_in_run_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cohort_payload, cohort = _cohort("1101")
    raw_stdout = json.dumps(
        {
            "task": SNAPSHOT_TASK,
            "status": "passed",
            "decision_date": DECISION_DATE.isoformat(),
            "result_id": "pipeline-snapshot-run",
            "snapshot_cohort": cohort_payload,
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    runs_root = (
        tmp_path
        / "scheduled"
        / "recommendation_calibration_learning"
        / "runs"
    )
    run_dir = runs_root / "20260925-synthetic-run"
    run_dir.mkdir(parents=True)
    stdout_path = run_dir / "recommendation_snapshot.stdout.bin"
    monkeypatch.setattr(
        learning_pipeline.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            stdout=raw_stdout,
            stderr=b"diagnostic bytes",
            returncode=0,
        ),
    )

    step = learning_pipeline._run_child(
        name="recommendation_snapshot",
        script="scripts/scheduled/run_scheduled_recommendation_snapshot.py",
        arguments=(),
        environment={"RECOMMENDATION_LEARNING_OUTPUT_ROOT": str(tmp_path)},
        log_handle=io.StringIO(),
        snapshot_stdout_artifact_path=stdout_path,
        snapshot_stdout_runs_root=runs_root,
    )

    expected_hash = "sha256:" + hashlib.sha256(raw_stdout).hexdigest()
    assert step["status"] == "passed"
    assert stdout_path.read_bytes() == raw_stdout
    assert step["child_stdout_artifact_path"] == str(stdout_path.resolve())
    assert step["child_stdout_artifact_size"] == len(raw_stdout)
    assert step["child_stdout_sha256"] == expected_hash
    terminal = learning_pipeline._terminal_receipt_projection(
        {"steps": {"recommendation_snapshot": step}}
    )
    terminal_step = terminal["steps"]["recommendation_snapshot"]
    assert terminal_step["child_stdout_artifact_path"] == str(stdout_path.resolve())
    assert terminal_step["child_stdout_artifact_size"] == len(raw_stdout)
    assert terminal_step["child_stdout_sha256"] == expected_hash

    second_attempt = learning_pipeline._run_child(
        name="recommendation_snapshot",
        script="scripts/scheduled/run_scheduled_recommendation_snapshot.py",
        arguments=(),
        environment={"RECOMMENDATION_LEARNING_OUTPUT_ROOT": str(tmp_path)},
        log_handle=io.StringIO(),
        snapshot_stdout_artifact_path=stdout_path,
        snapshot_stdout_runs_root=runs_root,
    )
    assert second_attempt["status"] == "failed"
    assert "snapshot_child_stdout_artifact_invalid:ValueError" in second_attempt[
        "child_blockers"
    ]
    assert stdout_path.read_bytes() == raw_stdout
    assert cohort.cohort_hash == cohort_payload["cohort_hash"]


def test_pipeline_snapshot_stdout_artifact_rejects_escape_and_oversize(
    tmp_path: Path,
) -> None:
    runs_root = (
        tmp_path
        / "scheduled"
        / "recommendation_calibration_learning"
        / "runs"
    )
    runs_root.mkdir(parents=True)
    escaped_dir = tmp_path / "outside"
    escaped_dir.mkdir()
    with pytest.raises(ValueError, match="超出本次 run root"):
        learning_pipeline._write_snapshot_invocation_stdout_artifact(
            path=escaped_dir / "recommendation_snapshot.stdout.bin",
            allowed_runs_root=runs_root,
            raw_stdout=b"x",
        )

    run_dir = runs_root / "oversize-run"
    run_dir.mkdir()
    with pytest.raises(ValueError, match="大小上限"):
        learning_pipeline._write_snapshot_invocation_stdout_artifact(
            path=run_dir / "recommendation_snapshot.stdout.bin",
            allowed_runs_root=runs_root,
            raw_stdout=b"x" * (8 * 1024 * 1024 + 1),
        )
    assert not (run_dir / "recommendation_snapshot.stdout.bin").exists()


def test_pipeline_snapshot_stdout_writer_detects_readback_path_replacement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runs_root = (
        tmp_path
        / "scheduled"
        / "recommendation_calibration_learning"
        / "runs"
    )
    run_dir = runs_root / "race-run"
    run_dir.mkdir(parents=True)
    stdout_path = run_dir / "recommendation_snapshot.stdout.bin"
    original_reader = learning_pipeline._read_regular_file_no_follow

    def replace_after_read(path: Path, root: Path, *, max_bytes: int | None = None) -> bytes:
        payload = original_reader(path, root, max_bytes=max_bytes)
        path.write_bytes(payload + b"concurrent replacement")
        return payload

    monkeypatch.setattr(
        learning_pipeline,
        "_read_regular_file_no_follow",
        replace_after_read,
    )
    with pytest.raises(ValueError, match="readback 時不一致"):
        learning_pipeline._write_snapshot_invocation_stdout_artifact(
            path=stdout_path,
            allowed_runs_root=runs_root,
            raw_stdout=b"frozen child stdout",
        )
