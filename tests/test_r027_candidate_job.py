"""R027 隔離候選 job 的 ports 與比較摘要契約。"""

from __future__ import annotations

import ast
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import pytest

from data_module.config import TWStockConfig
from scripts.experiments.r027.candidate_technical_indicator_job import (
    CandidateTechnicalIndicatorJob,
    TechnicalIndicatorJobPorts,
)
from scripts.experiments.r027.project_receipt import (
    project as project_r027_receipt,
    require_complete_worker_process_records,
    require_isolated_worker_roots,
    summarize_recorded_worker_processes,
    summarize_root_placement,
)
from scripts.experiments.r027 import project_receipt as project_receipt_module
from scripts.experiments.r027.run_experiment import (
    CASES,
    _comparable_sqlite_snapshot_reader_lifecycle,
    collect_exact_differences,
    extract_candidate_method,
    flatten_comparable,
    same_path_repeat_control,
    strict_gate_verdict,
)
from scripts.experiments.r027 import run_experiment as strict_experiment
from scripts.experiments.r027.worker import (
    _logical_sqlite_snapshot_evidence,
    _mutate_temporary_sqlite_user_version,
    _snapshot_outputs,
)
from scripts.experiments.r027.run_logical_time_revision import (
    _make_phase_mutation,
    _mutate_receipt_field,
)
from scripts.experiments.r027.logical_publication_phase_port import (
    LogicalPublicationPhasePort,
)
from scripts.experiments.r027 import logical_publication_phase_port as phase_port_module


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
R027_FROZEN_PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "experiments"
    / "r028"
    / "frozen_baseline"
)
R027_FROZEN_UPDATE_SERVICE = (
    R027_FROZEN_PACKAGE_ROOT / "app_module" / "update_service.py"
)
R027_FROZEN_UPDATE_SERVICE_SHA256 = (
    "697c3bd89aa256867f964e3cd01c253a28284f75a1c6d2d963354223e6daedec"
)


def _load_pinned_r027_update_service():
    raw = R027_FROZEN_UPDATE_SERVICE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == R027_FROZEN_UPDATE_SERVICE_SHA256
    spec = importlib.util.spec_from_file_location(
        "r027_frozen_update_service_for_candidate_test",
        R027_FROZEN_UPDATE_SERVICE,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.UpdateService


def test_candidate_run_is_exact_source_transform_with_explicit_ports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "candidate_technical_indicator_job.py"

    assert hashlib.sha256(
        R027_FROZEN_UPDATE_SERVICE.read_bytes()
    ).hexdigest() == R027_FROZEN_UPDATE_SERVICE_SHA256
    source_root = tmp_path / "r027-source-root"
    frozen_source = source_root / "app_module" / "update_service.py"
    candidate_template = (
        source_root
        / "scripts"
        / "experiments"
        / "r027"
        / "candidate_technical_indicator_job.py"
    )
    frozen_source.parent.mkdir(parents=True)
    candidate_template.parent.mkdir(parents=True)
    frozen_source.write_bytes(R027_FROZEN_UPDATE_SERVICE.read_bytes())
    candidate_template.write_bytes(
        strict_experiment.CANDIDATE_TEMPLATE_PATH.read_bytes()
    )
    monkeypatch.setattr(
        strict_experiment,
        "REPOSITORY_ROOT",
        source_root,
    )
    monkeypatch.setattr(
        strict_experiment,
        "CANDIDATE_TEMPLATE_PATH",
        candidate_template,
    )

    receipt = extract_candidate_method(destination)

    assert receipt["source_path"] == "app_module/update_service.py"
    assert receipt["source_sha256"] == (
        "sha256:" + R027_FROZEN_UPDATE_SERVICE_SHA256
    )

    candidate_tree = ast.parse(destination.read_text(encoding="utf-8"))
    candidate_class = next(
        node
        for node in candidate_tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "CandidateTechnicalIndicatorJob"
    )
    run_method = next(
        node
        for node in candidate_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    direct_self_members = {
        node.attr
        for node in ast.walk(run_method)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    }

    assert receipt["port_names"] == [
        "config",
        "get_indicator_latest_date",
        "run_process_pool",
    ]
    assert receipt["source_self_member_counts"] == {
        "config": 19,
        "_get_indicator_latest_date": 1,
        "_run_technical_indicator_process_pool": 1,
    }
    assert direct_self_members == {"_ports"}
    assert all(
        not (isinstance(node, ast.FunctionDef) and node.name == "__getattr__")
        for node in candidate_class.body
    )
    assert not any(
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
        and node.attr == "_service"
        for node in ast.walk(candidate_class)
    )
    assert destination.read_bytes() == Path(receipt["candidate_template_path"]).read_bytes()


def test_logical_phase_source_controls_change_only_declared_callsites(
    tmp_path: Path,
) -> None:
    candidate_source = Path(
        "scripts/experiments/r027/candidate_technical_indicator_job.py"
    ).resolve()
    original = candidate_source.read_bytes()

    deleted = tmp_path / "delete_aggregate_csv_completed.py"
    deleted_metadata = _make_phase_mutation(
        candidate_source,
        deleted,
        "delete_aggregate_csv_completed",
    )
    deleted_text = deleted.read_text(encoding="utf-8")
    assert 'record_publication_phase("aggregate_csv_write_completed")' not in deleted_text
    assert deleted_metadata["expected_baseline_count"] == 1
    assert deleted_metadata["expected_candidate_count"] == 0

    duplicated = tmp_path / "duplicate_run_started.py"
    duplicated_metadata = _make_phase_mutation(
        candidate_source,
        duplicated,
        "duplicate_run_started",
    )
    assert duplicated.read_text(encoding="utf-8").count(
        'record_publication_phase("run_started")'
    ) == 2
    assert duplicated_metadata["expected_baseline_count"] == 1
    assert duplicated_metadata["expected_candidate_count"] == 2

    reordered = tmp_path / "reorder_run_started_input_loaded.py"
    reordered_metadata = _make_phase_mutation(
        candidate_source,
        reordered,
        "reorder_run_started_input_loaded",
    )
    reordered_phases = [
        line.strip()
        for line in reordered.read_text(encoding="utf-8").splitlines()
        if line.strip()
        in {
            'record_publication_phase("run_started")',
            'record_publication_phase("input_loaded")',
        }
    ]
    assert reordered_phases == [
        'record_publication_phase("input_loaded")',
        'record_publication_phase("run_started")',
    ]
    assert reordered_metadata["expected_order"] == [
        "input_loaded",
        "run_started",
    ]
    assert candidate_source.read_bytes() == original


def test_receipt_field_controls_emit_resolvable_changed_token_paths() -> None:
    fresh_readers = []
    for _ in range(2):
        fresh_readers.append(
            {
                "daily_prices_source": {
                    "table_columns": [
                        {"name": "證券代號"},
                        {"name": "證券名稱"},
                    ],
                    "rows": [
                        [
                            {"type": "text", "value": "1101"},
                            {"type": "text", "value": "fixture-1101"},
                        ]
                    ],
                    "row_keys": [[{"type": "text", "value": "1101"}]],
                    "rows_sha256": "sha256:daily-rows",
                    "row_keys_sha256": "sha256:daily-keys",
                },
                "table_columns": [{"name": "RSI"}],
                "rows": [[{"type": "real", "hex": "0x1.9000000000000p+6"}]],
                "rows_sha256": "sha256:technical-rows",
            }
        )
    receipt = {
        "phases": [
            {
                "label": "clean_full_synthetic_publication",
                "outputs": {
                    "files": {
                        "data/_test/meta_data/all_stocks_data.csv": {
                            "sha256": "sha256:" + "a" * 64,
                        }
                    },
                    "logical_sqlite_snapshot": {"fresh_readers": fresh_readers},
                },
                "result": {"success": True},
            },
            {
                "label": "calculation_failure_recovery",
                "outputs": {},
                "result": {"success": True},
            },
        ]
    }

    def follow_tokens(value: object, tokens: list[str | int]) -> object:
        current = value
        for token in tokens:
            if isinstance(current, dict):
                current = current[token]
            else:
                assert isinstance(current, list)
                current = current[token]
        return current

    for control_id in (
        "artifact_bytes",
        "row_identity",
        "sqlite_visibility",
        "recovery_outcome",
    ):
        mutated, metadata = _mutate_receipt_field(
            control_id=control_id,
            receipt=receipt,
        )
        paths = metadata["mutation_paths"]
        assert paths
        for token_path in paths:
            assert all(type(token) in (str, int) for token in token_path)
            before = follow_tokens(receipt, token_path)
            after = follow_tokens(mutated, token_path)
            assert before != after


def test_candidate_ports_are_required_and_callable(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="TechnicalIndicatorJobPorts"):
        CandidateTechnicalIndicatorJob(object())  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="get_indicator_latest_date"):
        TechnicalIndicatorJobPorts(
            config=object(),
            get_indicator_latest_date=None,  # type: ignore[arg-type]
            run_process_pool=lambda **kwargs: {},
        )

    config = TWStockConfig(
        data_root=tmp_path / "candidate-test-data",
        output_root=tmp_path / "candidate-test-output",
        profile="test",
    )
    ports = TechnicalIndicatorJobPorts(
        config=config,
        get_indicator_latest_date=lambda path: None,
        run_process_pool=lambda **kwargs: {},
    )
    job = CandidateTechnicalIndicatorJob(ports)

    assert job._ports is ports
    assert not hasattr(job, "_service")


def test_logical_phase_port_is_invoked_by_independent_source_call_sites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_update_service = _load_pinned_r027_update_service()
    baseline_service = object.__new__(baseline_update_service)
    baseline_service.config = SimpleNamespace()
    baseline_source_sha256 = (
        "sha256:"
        + hashlib.sha256(R027_FROZEN_UPDATE_SERVICE.read_bytes()).hexdigest()
    )
    monkeypatch.setattr(
        phase_port_module,
        "REPOSITORY_ROOT",
        R027_FROZEN_PACKAGE_ROOT,
    )
    baseline_port = LogicalPublicationPhasePort(
        case="focused_cancel",
        mode="baseline",
        phase="cancel_before_start",
        source_sha256=baseline_source_sha256,
    )

    baseline_result = baseline_service.calculate_technical_indicators(
        cancel_callback=lambda: True,
        publication_phase_port=baseline_port,
    )

    candidate_ports = TechnicalIndicatorJobPorts(
        config=SimpleNamespace(),
        get_indicator_latest_date=lambda path: None,
        run_process_pool=lambda **kwargs: {},
    )
    candidate_job = CandidateTechnicalIndicatorJob(candidate_ports)
    monkeypatch.setattr(
        phase_port_module,
        "REPOSITORY_ROOT",
        REPOSITORY_ROOT,
    )
    candidate_source_sha256 = (
        "sha256:"
        + hashlib.sha256(
            (REPOSITORY_ROOT / "scripts/experiments/r027/candidate_technical_indicator_job.py").read_bytes()
        ).hexdigest()
    )
    candidate_port = LogicalPublicationPhasePort(
        case="focused_cancel",
        mode="candidate",
        phase="cancel_before_start",
        source_sha256=candidate_source_sha256,
    )

    candidate_result = candidate_job.run(
        cancel_callback=lambda: True,
        publication_phase_port=candidate_port,
    )

    assert baseline_result == candidate_result
    baseline_events = baseline_port.receipt()["events"]
    candidate_events = candidate_port.receipt()["events"]
    assert [event["phase"] for event in baseline_events] == [
        "run_started",
        "cancel_before_start",
    ]
    assert [event["logical_token"] for event in baseline_events] == [1, 2]
    assert [
        {"phase": event["phase"], "logical_token": event["logical_token"]}
        for event in baseline_events
    ] == [
        {"phase": event["phase"], "logical_token": event["logical_token"]}
        for event in candidate_events
    ]
    assert [event["source_callsite"]["path"] for event in baseline_events] == [
        "app_module/update_service.py",
        "app_module/update_service.py",
    ]
    assert [event["source_callsite"]["path"] for event in candidate_events] == [
        "scripts/experiments/r027/candidate_technical_indicator_job.py",
        "scripts/experiments/r027/candidate_technical_indicator_job.py",
    ]
    assert all(
        Path(event["source_callsite"]["raw_path"]).is_absolute()
        for event in baseline_events + candidate_events
    )
    assert [event["source_callsite"]["source_sha256"] for event in baseline_events] == [
        baseline_source_sha256,
        baseline_source_sha256,
    ]
    assert [event["source_callsite"]["source_sha256"] for event in candidate_events] == [
        candidate_source_sha256,
        candidate_source_sha256,
    ]
    assert all(
        Path(event["source_callsite"]["raw_path"]).resolve()
        == R027_FROZEN_UPDATE_SERVICE.resolve()
        for event in baseline_events
    )
    assert all(
        event["raw_os_observations"]["wall_time_utc"]
        and event["raw_os_observations"]["perf_counter_ns"] > 0
        for event in baseline_events + candidate_events
    )


def test_partial_r027_comparison_cannot_pass_overall_gate() -> None:
    partial_comparison = {"clean": {"status": "equal"}}
    full_comparison = {
        case: {
            "status": "exact_match",
            "semantic_differences": [],
            "timing_differences": [],
            "all_exact_differences_including_process_clock": [],
        }
        for case in CASES
    }
    negatives = {"all_detected": True}

    assert strict_gate_verdict(("clean",), partial_comparison, negatives) == "INCONCLUSIVE"
    assert strict_gate_verdict(CASES, full_comparison, negatives) == "PASS"
    assert strict_gate_verdict(CASES, {}, negatives) == "INCONCLUSIVE"
    assert strict_gate_verdict(CASES, {"clean": full_comparison["clean"]}, negatives) == "INCONCLUSIVE"
    unknown_status = dict(full_comparison)
    unknown_status[CASES[-1]] = {"status": "unknown"}
    assert strict_gate_verdict(CASES, unknown_status, negatives) == "INCONCLUSIVE"
    assert (
        strict_gate_verdict(tuple(reversed(CASES)), full_comparison, negatives)
        == "INCONCLUSIVE"
    )


def _worker_receipt_metadata(*, duplicate_last_pid: bool = False) -> dict[str, object]:
    workers: dict[str, dict[str, dict[str, object]]] = {}
    pid = 10_000
    first_pid: int | None = None
    for case in CASES:
        workers[case] = {}
        for mode in ("baseline", "candidate"):
            pid += 1
            if first_pid is None:
                first_pid = pid
            recorded_pid = first_pid if duplicate_last_pid and case == CASES[-1] and mode == "candidate" else pid
            workspace = Path("isolated-run") / "workers" / case / mode
            workers[case][mode] = {
                "mode": mode,
                "case": case,
                "pid": recorded_pid,
                "return_code": 0,
                "receipt": {
                    "mode": mode,
                    "case": case,
                    "pid": recorded_pid,
                    "workspace": str(workspace),
                    "resolved_data_root": str(workspace / "data"),
                    "resolved_output_root": str(workspace / "output"),
                },
            }
    return {"cases": list(CASES), "workers": workers}


def test_projector_reports_duplicate_pids_from_receipt_without_overclaim() -> None:
    unique = summarize_recorded_worker_processes(_worker_receipt_metadata())
    duplicate = summarize_recorded_worker_processes(
        _worker_receipt_metadata(duplicate_last_pid=True)
    )

    assert unique["receipt_recorded_distinct_pid"] is True
    assert unique["unique_recorded_pid_count"] == 16
    assert unique["all_worker_return_codes_zero"] is True
    assert unique["process_source_independently_attested"] is False
    require_complete_worker_process_records(unique)
    assert duplicate["all_expected_case_mode_pairs_recorded"] is True
    assert duplicate["receipt_recorded_distinct_pid"] is False
    assert duplicate["unique_recorded_pid_count"] == 15
    with pytest.raises(RuntimeError, match="exact 16 expected case/mode"):
        require_complete_worker_process_records(duplicate)

    reordered_mapping = _worker_receipt_metadata()
    workers = reordered_mapping["workers"]
    assert isinstance(workers, dict)
    reordered_mapping["workers"] = dict(sorted(workers.items()))
    assert (
        summarize_recorded_worker_processes(reordered_mapping)[
            "all_expected_case_mode_pairs_recorded"
        ]
        is True
    )
    assert (
        summarize_recorded_worker_processes(reordered_mapping)[
            "receipt_recorded_distinct_pid"
        ]
        is True
    )

    reordered_cases = _worker_receipt_metadata()
    reordered_cases["cases"] = list(reversed(CASES))
    assert (
        summarize_recorded_worker_processes(reordered_cases)[
            "all_expected_case_mode_pairs_recorded"
        ]
        is False
    )

    reordered_modes = _worker_receipt_metadata()
    mode_workers = reordered_modes["workers"]
    assert isinstance(mode_workers, dict)
    mode_workers[CASES[0]] = dict(reversed(list(mode_workers[CASES[0]].items())))
    assert (
        summarize_recorded_worker_processes(reordered_modes)[
            "all_expected_case_mode_pairs_recorded"
        ]
        is True
    )

    wrong_mode = _worker_receipt_metadata()
    wrong_mode_workers = wrong_mode["workers"]
    assert isinstance(wrong_mode_workers, dict)
    wrong_mode_workers[CASES[0]]["baseline"]["mode"] = "candidate"
    assert (
        summarize_recorded_worker_processes(wrong_mode)[
            "all_expected_case_mode_pairs_recorded"
        ]
        is False
    )
    with pytest.raises(
        RuntimeError,
        match="exact 16 expected case/mode",
    ):
        require_complete_worker_process_records(
            summarize_recorded_worker_processes(wrong_mode)
        )

    for field, value in (
        ("case", "wrong-case"),
        ("mode", "candidate"),
        ("pid", -1),
    ):
        mismatched_receipt = _worker_receipt_metadata()
        mismatched_receipt["workers"][CASES[0]]["baseline"]["receipt"][field] = value
        identity_summary = summarize_recorded_worker_processes(mismatched_receipt)
        assert identity_summary["all_wrapper_and_receipt_identities_match"] is False
        assert identity_summary["all_expected_case_mode_pairs_recorded"] is False
        with pytest.raises(RuntimeError, match="matching wrapper/receipt"):
            require_complete_worker_process_records(identity_summary)

    bool_receipt_pid = _worker_receipt_metadata()
    bool_receipt_pid["workers"][CASES[0]]["baseline"]["pid"] = 1
    bool_receipt_pid["workers"][CASES[0]]["baseline"]["receipt"]["pid"] = True
    bool_pid_summary = summarize_recorded_worker_processes(bool_receipt_pid)
    assert bool_pid_summary["all_receipt_pids_are_positive_integers"] is False
    assert bool_pid_summary["receipt_recorded_distinct_pid"] is False
    with pytest.raises(RuntimeError, match="positive recorded PIDs"):
        require_complete_worker_process_records(bool_pid_summary)

    mismatched_wrapper = _worker_receipt_metadata()
    mismatched_wrapper["workers"][CASES[0]]["baseline"]["case"] = "wrong-case"
    wrapper_summary = summarize_recorded_worker_processes(mismatched_wrapper)
    assert wrapper_summary["all_wrapper_and_receipt_identities_match"] is False
    with pytest.raises(RuntimeError, match="matching wrapper/receipt"):
        require_complete_worker_process_records(wrapper_summary)


def test_projector_distinguishes_custom_isolated_root_from_os_temp() -> None:
    receipt = _worker_receipt_metadata()
    # 只使用不會寫入磁碟的不同磁碟機路徑，避免 pytest --basetemp 改變
    # 系統 TEMP 後，這個純路徑摘要測試意外把合成根放進 repository。
    synthetic_os_temp = Path("R:/r027-synthetic-os-temp")
    run_root = Path("Q:/r027-custom-isolated-parent/r027-run")
    wrappers = []
    workers = receipt["workers"]
    assert isinstance(workers, dict)
    for case in CASES:
        for mode in ("baseline", "candidate"):
            wrapper = workers[case][mode]
            worker_receipt = wrapper["receipt"]
            workspace = run_root / "workers" / case / mode
            worker_receipt["workspace"] = str(workspace)
            worker_receipt["resolved_data_root"] = str(workspace / "data")
            worker_receipt["resolved_output_root"] = str(workspace / "output")
            wrappers.append(wrapper)
    receipt["run_root"] = str(run_root)

    summary = summarize_root_placement(
        receipt,
        wrappers,
        os_temp_root=synthetic_os_temp,
    )

    assert summary["run_root_within_os_temp"] is False
    assert summary["all_data_and_output_roots_temp"] is False
    assert summary["all_data_and_output_roots_isolated_under_run_root"] is True
    assert summary["run_root_disjoint_from_formal_roots"] is True
    assert summary["all_workspaces_pairwise_disjoint"] is True
    require_isolated_worker_roots(summary)

    incomplete_summary = summarize_root_placement(
        receipt,
        wrappers[:-1],
        os_temp_root=synthetic_os_temp,
    )
    assert incomplete_summary["all_data_and_output_roots_temp"] is False
    assert incomplete_summary["all_data_and_output_roots_isolated_under_run_root"] is False
    assert incomplete_summary["all_workspaces_pairwise_disjoint"] is False
    with pytest.raises(RuntimeError, match="not proven isolated"):
        require_isolated_worker_roots(incomplete_summary)

    formal_overlap_summary = summarize_root_placement(
        receipt,
        wrappers,
        os_temp_root=synthetic_os_temp,
        formal_data_root=Path("Q:/r027-custom-isolated-parent"),
        formal_output_root=Path("P:/r027-formal-output"),
    )
    assert formal_overlap_summary["run_root_disjoint_from_formal_roots"] is False
    assert formal_overlap_summary["all_data_and_output_roots_isolated_under_run_root"] is False
    with pytest.raises(RuntimeError, match="formal data/output roots"):
        require_isolated_worker_roots(formal_overlap_summary)

    repository_root = Path(__file__).resolve().parents[1]
    receipt["run_root"] = str(repository_root)
    repository_wrappers = []
    for case in CASES:
        for mode in ("baseline", "candidate"):
            wrapper = workers[case][mode]
            worker_receipt = wrapper["receipt"]
            workspace = repository_root / "synthetic-r027-run" / "workers" / case / mode
            worker_receipt["workspace"] = str(workspace)
            worker_receipt["resolved_data_root"] = str(workspace / "data")
            worker_receipt["resolved_output_root"] = str(workspace / "output")
            repository_wrappers.append(wrapper)
    repository_summary = summarize_root_placement(
        receipt,
        repository_wrappers,
        os_temp_root=synthetic_os_temp,
    )
    assert repository_summary["run_root_disjoint_from_repository"] is False
    assert repository_summary["all_data_and_output_roots_isolated_under_run_root"] is False
    with pytest.raises(RuntimeError, match="not proven isolated"):
        require_isolated_worker_roots(repository_summary)

    overlapping_workspaces = _worker_receipt_metadata()
    overlapping_workers = overlapping_workspaces["workers"]
    assert isinstance(overlapping_workers, dict)
    overlapping_wrappers = []
    overlap_root = Path("Q:/r027-overlap-test")
    overlapping_workspaces["run_root"] = str(overlap_root)
    first_workspace: Path | None = None
    for case in CASES:
        for mode in ("baseline", "candidate"):
            wrapper = overlapping_workers[case][mode]
            worker_receipt = wrapper["receipt"]
            workspace = overlap_root / "workers" / case / mode
            if first_workspace is None:
                first_workspace = workspace
            elif case == CASES[0] and mode == "candidate":
                workspace = first_workspace / "nested"
            worker_receipt["workspace"] = str(workspace)
            worker_receipt["resolved_data_root"] = str(workspace / "data")
            worker_receipt["resolved_output_root"] = str(workspace / "output")
            overlapping_wrappers.append(wrapper)
    overlap_summary = summarize_root_placement(
        overlapping_workspaces,
        overlapping_wrappers,
        os_temp_root=synthetic_os_temp,
    )
    assert overlap_summary["all_workspaces_within_run_root"] is True
    assert overlap_summary["all_workspaces_pairwise_disjoint"] is False
    assert overlap_summary["all_data_and_output_roots_isolated_under_run_root"] is False
    with pytest.raises(RuntimeError, match="not proven isolated"):
        require_isolated_worker_roots(overlap_summary)


def _projector_test_receipt(
    tmp_path: Path,
    *,
    run_root: Path,
    bad_receipt_identity: bool = False,
) -> dict[str, object]:
    receipt = _worker_receipt_metadata()
    workers = receipt["workers"]
    assert isinstance(workers, dict)
    wrappers = []
    for case in CASES:
        for mode in ("baseline", "candidate"):
            wrapper = workers[case][mode]
            worker_receipt = wrapper["receipt"]
            workspace = run_root / "workers" / case / mode
            worker_receipt["workspace"] = str(workspace)
            worker_receipt["resolved_data_root"] = str(workspace / "data")
            worker_receipt["resolved_output_root"] = str(workspace / "output")
            wrappers.append(wrapper)
    if bad_receipt_identity:
        workers[CASES[0]]["baseline"]["receipt"]["pid"] += 1
    return {
        "run_root": str(run_root),
        "cases": list(CASES),
        "workers": workers,
        "formal_data_touched": False,
        "production_source_write_performed": False,
        "strict_verdict": "PASS",
        "r028_unlocked": True,
        "candidate_extraction": {
            "source_sha256": "sha256:" + "0" * 64,
            "candidate_sha256": "sha256:" + "0" * 64,
            "port_names": [
                "config",
                "get_indicator_latest_date",
                "run_process_pool",
            ],
        },
    }


def test_receipt_projector_rejects_worker_receipt_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "update_service.py"
    candidate_path = tmp_path / "candidate.py"
    source_path.write_text("source", encoding="utf-8")
    candidate_path.write_text("candidate", encoding="utf-8")
    monkeypatch.setattr(project_receipt_module, "UPDATE_SERVICE", source_path)
    monkeypatch.setattr(project_receipt_module, "CANDIDATE_TEMPLATE", candidate_path)
    monkeypatch.setattr(project_receipt_module, "current_head", lambda: "test-head")

    receipt = _projector_test_receipt(
        tmp_path,
        run_root=tmp_path / "isolated-run",
        bad_receipt_identity=True,
    )
    extraction = receipt["candidate_extraction"]
    assert isinstance(extraction, dict)
    extraction["source_sha256"] = "sha256:" + hashlib.sha256(
        source_path.read_bytes()
    ).hexdigest()
    extraction["candidate_sha256"] = "sha256:" + hashlib.sha256(
        candidate_path.read_bytes()
    ).hexdigest()
    receipt_path = tmp_path / "mismatched-worker-receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(RuntimeError, match="matching wrapper/receipt"):
        project_r027_receipt(receipt_path, "test-head")


def test_receipt_projector_rejects_repository_root_even_if_receipt_claims_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "update_service.py"
    candidate_path = tmp_path / "candidate.py"
    source_path.write_text("source", encoding="utf-8")
    candidate_path.write_text("candidate", encoding="utf-8")
    monkeypatch.setattr(project_receipt_module, "UPDATE_SERVICE", source_path)
    monkeypatch.setattr(project_receipt_module, "CANDIDATE_TEMPLATE", candidate_path)
    monkeypatch.setattr(project_receipt_module, "current_head", lambda: "test-head")

    repository_root = project_receipt_module.REPOSITORY_ROOT
    receipt = _projector_test_receipt(
        tmp_path,
        run_root=repository_root / "synthetic-r027-receipt-run",
    )
    extraction = receipt["candidate_extraction"]
    assert isinstance(extraction, dict)
    extraction["source_sha256"] = "sha256:" + hashlib.sha256(
        source_path.read_bytes()
    ).hexdigest()
    extraction["candidate_sha256"] = "sha256:" + hashlib.sha256(
        candidate_path.read_bytes()
    ).hexdigest()
    receipt_path = tmp_path / "false-isolation-pass-claim.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(RuntimeError, match="not proven isolated"):
        project_r027_receipt(receipt_path, "test-head")


def test_same_path_receipt_reports_set_mismatch_and_db_snapshots() -> None:
    first_database = {
        "sha256": "sha256:first",
        "size_bytes": 1024,
        "mtime_ns": 10,
    }
    repeat_database = {
        "sha256": "sha256:repeat",
        "size_bytes": 2048,
        "mtime_ns": 20,
    }
    file_record = {
        "sha256": "sha256:stable",
        "size_bytes": 5,
        "mtime_ns": 30,
    }
    worker = {
        "mode": "candidate",
        "receipt": {
            "case": "same_input_rerun",
            "pid": 123,
            "workspace": "TEMP/worker",
            "phases": [
                {
                    "label": "same_input_first_publication",
                    "outputs": {
                        "files": {
                            "same.csv": file_record,
                            "first_only.csv": file_record,
                        },
                        "sqlite_main_db_before_checkpoint": first_database,
                    },
                },
                {
                    "label": "same_input_repeat_publication",
                    "outputs": {
                        "files": {
                            "same.csv": file_record,
                            "repeat_only.csv": file_record,
                        },
                        "sqlite_main_db_before_checkpoint": repeat_database,
                    },
                },
            ],
        },
    }

    summary = same_path_repeat_control(worker)

    assert summary is not None
    assert summary["status"] == "measured"
    assert summary["same_physical_paths"] is False
    assert summary["same_path_set"] is False
    assert summary["first_relative_paths"] == ["first_only.csv", "same.csv"]
    assert summary["repeat_relative_paths"] == ["repeat_only.csv", "same.csv"]
    assert summary["first_only_paths"] == ["first_only.csv"]
    assert summary["repeat_only_paths"] == ["repeat_only.csv"]
    assert summary["same_relative_paths"] == ["same.csv"]
    assert summary["sqlite_main_db_before_checkpoint"] == {
        "first": first_database,
        "repeat": repeat_database,
        "same_sha256": False,
        "same_size_bytes": False,
        "same_mtime_ns": False,
    }


def test_snapshot_reader_is_read_only_and_reports_post_close_files(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "sqlite" / "twstock.db"
    database_path.parent.mkdir(parents=True)
    technical_directory = tmp_path / "data" / "technical_analysis"
    technical_directory.mkdir(parents=True)
    writer = sqlite3.connect(database_path)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute(
            'CREATE TABLE daily_prices '
            '("證券代號" TEXT, "日期" TEXT, "收盤價" INTEGER, '
            'PRIMARY KEY ("證券代號", "日期"))'
        )
        writer.execute(
            'INSERT INTO daily_prices VALUES ("2330", "20260925", 1000)'
        )
        writer.execute(
            'CREATE TABLE technical_indicators '
            '("證券代號" TEXT, "日期" TEXT, "RSI" REAL)'
        )
        writer.execute(
            'INSERT INTO technical_indicators VALUES ("2330", "2026-09-25", 55.0)'
        )
        writer.commit()

        receipt = _snapshot_outputs(
            SimpleNamespace(
                db_file=database_path,
                technical_dir=technical_directory,
                all_stocks_data_file=tmp_path / "data" / "all_stocks_data.csv",
            ),
            tmp_path,
            checkpoint=False,
        )
    finally:
        writer.close()

    lifecycle = receipt["sqlite_snapshot_reader_lifecycle"]
    assert lifecycle["reader_mode"] == "read_only_uri_query_only"
    assert lifecycle["query_only_enabled"] is True
    assert lifecycle["reader_close_returned"] is True
    assert receipt["technical_rows"]["shape"] == [1, 3]
    assert lifecycle["main_db_bytes_unchanged_across_reader_window"] is True
    assert lifecycle["main_db_mtime_unchanged_across_reader_window"] is True
    assert lifecycle["transient_path_set_unchanged_across_reader_window"] is True
    assert set(lifecycle["transient_files_before_reader"]) == set(
        lifecycle["transient_files_after_reader_close"]
    )
    assert isinstance(
        lifecycle["transient_bytes_unchanged_across_reader_window"], bool
    )
    assert isinstance(
        lifecycle["transient_mtimes_unchanged_across_reader_window"], bool
    )
    assert "raw_bytes_base64" not in receipt["sqlite_main_db_before_checkpoint"]
    assert "raw_bytes_base64" not in lifecycle["main_db_after_reader_close"]

    logical_revision_receipt = _snapshot_outputs(
        SimpleNamespace(
            db_file=database_path,
            technical_dir=technical_directory,
            all_stocks_data_file=tmp_path / "data" / "all_stocks_data.csv",
        ),
        tmp_path,
        checkpoint=False,
        include_logical_time_raw_bytes=True,
    )
    assert base64.b64decode(
        logical_revision_receipt["sqlite_main_db_before_checkpoint"]["raw_bytes_base64"]
    ) == database_path.read_bytes()
    assert base64.b64decode(
        logical_revision_receipt["sqlite_snapshot_reader_lifecycle"][
            "main_db_after_reader_close"
        ]["raw_bytes_base64"]
    ) == database_path.read_bytes()


def test_snapshot_reader_raw_after_state_remains_in_strict_timing_diff() -> None:
    baseline = {
        "phases": [
            {
                "label": "snapshot",
                "outputs": {
                    "sqlite_snapshot_reader_lifecycle": {
                        "reader_mode": "read_only_uri_query_only",
                        "main_db_after_reader_close": {"sha256": "sha256:a"},
                    }
                },
            }
        ]
    }
    candidate = {
        "phases": [
            {
                "label": "snapshot",
                "outputs": {
                    "sqlite_snapshot_reader_lifecycle": {
                        "reader_mode": "read_only_uri_query_only",
                        "main_db_after_reader_close": {"sha256": "sha256:b"},
                    }
                },
            }
        ]
    }

    differences = collect_exact_differences(
        flatten_comparable(baseline)["timings"],
        flatten_comparable(candidate)["timings"],
    )

    assert any(
        difference["path"].endswith(
            "sqlite_snapshot_reader_lifecycle.main_db_after_reader_close.sha256"
        )
        for difference in differences
    )


def test_logical_sqlite_snapshot_reads_committed_rows_through_fresh_connections(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "data" / "sqlite" / "twstock.db"
    database_path.parent.mkdir(parents=True)
    writer = sqlite3.connect(database_path)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute(
            'CREATE TABLE daily_prices '
            '("證券代號" TEXT, "日期" TEXT, "收盤價" INTEGER, '
            'PRIMARY KEY ("證券代號", "日期"))'
        )
        writer.execute(
            'INSERT INTO daily_prices VALUES ("2330", "20260925", 1000)'
        )
        writer.execute(
            'CREATE TABLE technical_indicators '
            '("證券代號" TEXT, "日期" TEXT, "RSI" REAL, '
            'PRIMARY KEY ("證券代號", "日期"))'
        )
        writer.execute(
            'INSERT INTO technical_indicators VALUES ("2330", "20260925", 55.0)'
        )
        writer.commit()
    finally:
        writer.close()

    main_database_bytes = database_path.read_bytes()
    initial_fixture_identity = {
        "source_variant": "original",
        "canonical_rows_hash": "sha256:synthetic-source",
        "row_count": 1,
        "symbols": ["2330"],
    }
    evidence = _logical_sqlite_snapshot_evidence(
        database_path,
        tmp_path,
        initial_fixture_identity=initial_fixture_identity,
    )

    assert len(evidence["fresh_readers"]) == 2
    assert evidence["reader_states_match_after_close_reopen"] is True
    assert evidence["main_database_raw_bytes_unchanged_across_readers"] is True
    assert evidence["main_database_before_readers"]["size_bytes"] == len(
        main_database_bytes
    )
    assert base64.b64decode(
        evidence["main_database_before_readers"]["raw_bytes_base64"]
    ) == main_database_bytes
    for reader in evidence["fresh_readers"]:
        assert reader["query_only_enabled"] is True
        assert reader["connection_close_returned"] is True
        assert reader["initial_fixture_identity"] == initial_fixture_identity
        daily_prices = reader["daily_prices_source"]
        assert daily_prices["schema_sql"]
        assert daily_prices["row_count"] == 1
        assert daily_prices["key_columns"] == ["證券代號", "日期"]
        assert daily_prices["row_keys"] == [
            [
                {"type": "text", "value": "2330"},
                {"type": "text", "value": "20260925"},
            ]
        ]
        assert daily_prices["rows_sha256"].startswith("sha256:")
        assert reader["table_schema_sql"]
        assert reader["row_count"] == 1
        assert reader["row_keys"] == [
            [
                {"type": "text", "value": "2330"},
                {"type": "text", "value": "20260925"},
            ]
        ]


def test_sqlite_user_version_control_changes_only_temp_db_header_bytes(
    tmp_path: Path,
) -> None:
    workspace = tmp_path.resolve()
    database_path = workspace / "data" / "sqlite" / "twstock.db"
    database_path.parent.mkdir(parents=True)
    writer = sqlite3.connect(database_path)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute(
            'CREATE TABLE daily_prices '
            '("證券代號" TEXT, "日期" TEXT, "收盤價" INTEGER, '
            'PRIMARY KEY ("證券代號", "日期"))'
        )
        writer.execute(
            'INSERT INTO daily_prices VALUES ("2330", "20260925", 1000)'
        )
        writer.execute(
            'CREATE TABLE technical_indicators '
            '("證券代號" TEXT, "日期" TEXT, "RSI" REAL, '
            'PRIMARY KEY ("證券代號", "日期"))'
        )
        writer.execute(
            'INSERT INTO technical_indicators VALUES ("2330", "20260925", 55.0)'
        )
        writer.commit()
    finally:
        writer.close()

    evidence = _mutate_temporary_sqlite_user_version(database_path, workspace)

    assert evidence["connection_closed"] is True
    assert evidence["old_user_version"] == 0
    assert evidence["mutated_user_version"] == 1
    assert evidence["readback_user_version"] == 1
    assert evidence["raw_database_bytes_changed"] is True
    before = base64.b64decode(evidence["before_main_database"]["raw_bytes_base64"])
    after = base64.b64decode(evidence["after_main_database"]["raw_bytes_base64"])
    assert before != after
    assert evidence["application_tables_unchanged"] is True
    assert evidence["application_tables_before"] == evidence["application_tables_after"]


def test_snapshot_reader_path_comparison_uses_verified_workspace_relative_identity() -> None:
    baseline = {
        "reader_mode": "read_only_uri_query_only",
        "database_file_configured_path": "C:/temp/baseline/data/sqlite/twstock.db",
        "database_file_workspace_relative": "data/sqlite/twstock.db",
        "database_file_identity_validated": True,
        "database_list": [
            {
                "sequence": 0,
                "name": "main",
                "file": "C:/temp/baseline/data/sqlite/twstock.db",
                "workspace_relative_file": "data/sqlite/twstock.db",
            }
        ],
    }
    candidate = {
        **baseline,
        "database_file_configured_path": "C:/temp/candidate/data/sqlite/twstock.db",
        "database_list": [
            {
                "sequence": 0,
                "name": "main",
                "file": "C:/temp/candidate/data/sqlite/twstock.db",
                "workspace_relative_file": "data/sqlite/twstock.db",
            }
        ],
    }

    baseline_comparable = _comparable_sqlite_snapshot_reader_lifecycle(baseline)
    candidate_comparable = _comparable_sqlite_snapshot_reader_lifecycle(candidate)

    assert baseline_comparable == candidate_comparable
    assert baseline_comparable["database_list"][0]["file"] == "data/sqlite/twstock.db"
    assert baseline["database_list"][0]["file"].startswith("C:/temp/baseline")
