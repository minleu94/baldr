"""唯讀每日營運收據轉接器的契約測試。"""

from copy import deepcopy
from typing import Any, Callable

from app_module.daily_operations_receipts import adapt_receipt


def test_quick_legacy_contract_maps_only_explicit_run_clocks() -> None:
    """Quick 舊 producer 有固定 task、run_id 與兩個明確時間欄位。"""
    result = adapt_receipt(
        {
            "task": "baldr-data-update-quick-daily",
            "status": "passed_with_warnings",
            "run_id": "quick-20261021-01",
            "started_at": "2026-10-21T08:00:00+08:00",
            "completed_at": "2026-10-21T08:03:00+08:00",
            "checked_at": "2026-10-21T08:03:00+08:00",
        }
    )
    assert result["supported"] is True
    assert result["schema"] is None
    assert result["kind"] == "producer"
    assert result["run_id"] == "quick-20261021-01"
    assert result["started_at"].startswith("2026-10-21T08:00")
    assert result["completed_at"].startswith("2026-10-21T08:03")
    assert result["producer_status"] == "passed_with_warnings"
    assert result["producer_status_semantic"] == "degraded"


def _paper_retry_terminal() -> dict[str, object]:
    started = "2026-10-22T09:00:00Z"
    completed = "2026-10-22T09:00:01Z"
    run_id = "1" * 32
    nested: dict[str, object] = {
        "schema_version": "paper-execution-retry-terminal-status.v1",
        "task": "baldr-paper-execution-eod-replay-daily",
        "run_id": run_id,
        "started_at": started,
        "completed_at": completed,
        "status": "blocked",
        "exit_code": 2,
        "financial_qualification_status": "unknown",
        "dependency_readiness_status": "blocked",
        "terminal_blocker_code": "paper_execution_blocked",
        "gate_attempts": [
            {
                "attempt": 1,
                "target_date": "2026-10-21",
                "status": "blocked",
                "ready": False,
                "blocker_count": 1970,
                "receipt_ref": {"path": "dependency_gate/attempt-1.json", "sha256": "a" * 64},
            }
        ],
        "gate_blocker_count": 1970,
        "gate_blockers_validation": "not_copied_or_validated",
    }
    return {
        "schema_version": "paper-execution-retry-terminal-receipt.v1",
        "task": "baldr-paper-execution-eod-replay-daily",
        "run_id": run_id,
        "started_at": started,
        "completed_at": completed,
        "code_version": "sha256:" + "b" * 64,
        "exit_code": 2,
        "failure_code": "paper_execution_blocked",
        "status": "blocked",
        "blockers": ["paper_execution_blocked"],
        "financial_qualification_status": "unknown",
        "dependency_readiness_status": "blocked",
        "status_payload": nested,
    }


def test_paper_retry_terminal_is_exact_and_keeps_finance_unknown() -> None:
    result = adapt_receipt(_paper_retry_terminal())
    assert result["supported"] is True
    assert result["kind"] == "producer"
    assert result["producer_task"] == "baldr-paper-execution-eod-replay-daily"
    assert result["run_id"] == "1" * 32
    assert result["producer_status"] == "blocked"
    assert result["dependency_readiness"]["semantic"] == "blocked"
    assert result["financial_qualification"]["semantic"] == "unknown"
    assert result["failure_code"] == "paper_execution_blocked"


def test_paper_retry_terminal_accepts_success_with_dependency_passed() -> None:
    payload = _paper_retry_terminal()
    nested = payload["status_payload"]
    assert isinstance(nested, dict)
    payload.update(
        status="machine_verified_candidate",
        exit_code=0,
        failure_code=None,
        blockers=[],
        dependency_readiness_status="passed",
    )
    nested.update(
        status="machine_verified_candidate",
        exit_code=0,
        terminal_blocker_code=None,
        dependency_readiness_status="passed",
    )
    attempts = nested["gate_attempts"]
    assert isinstance(attempts, list) and isinstance(attempts[0], dict)
    attempts[0].update(status="ready", ready=True, blocker_count=0)
    nested["gate_blocker_count"] = 0
    result = adapt_receipt(payload)
    assert result["supported"] is True
    assert result["producer_status"] == "machine_verified_candidate"
    assert result["dependency_readiness"]["semantic"] == "passed"
    assert result["financial_qualification"]["semantic"] == "unknown"


def test_paper_retry_terminal_rejects_nested_identity_exit_and_gate_tampering() -> None:
    mutations: tuple[Callable[[dict[str, Any]], None], ...] = (
        lambda payload: payload.update(task="other-task"),
        lambda payload: payload["status_payload"].update(exit_code=0),
        lambda payload: payload["status_payload"].update(run_id="2" * 32),
        lambda payload: payload["status_payload"]["gate_attempts"][0]["receipt_ref"].update(sha256="0" * 63),
        lambda payload: payload["status_payload"].update(dependency_readiness_status="passed"),
        lambda payload: payload["status_payload"].update(gate_blocker_count=1969),
        lambda payload: payload.update(financial_qualification_status="qualified"),
    )
    for mutate in mutations:
        payload = deepcopy(_paper_retry_terminal())
        mutate(payload)
        adapted = adapt_receipt(payload)
        assert adapted["supported"] is False
        assert adapted["kind"] is None


def test_paper_retry_adapter_labels_gate_reference_as_asserted_not_content_verified() -> None:
    payload = _paper_retry_terminal()
    nested = payload["status_payload"]
    assert isinstance(nested, dict)
    attempts = nested["gate_attempts"]
    assert isinstance(attempts, list) and isinstance(attempts[0], dict)
    reference = attempts[0]["receipt_ref"]
    assert isinstance(reference, dict)
    reference["sha256"] = "0" * 64

    result = adapt_receipt(payload)
    assert result["supported"] is True
    assert result["gate_reference_verification"] == "shape_only_producer_asserted"
    assert result["financial_qualification"]["semantic"] == "unknown"


def test_freshness_legacy_contract_preserves_source_vocabulary_and_no_start_time() -> None:
    """Freshness 僅提供檢查時鐘，來源狀態按原詞保留。"""
    vocabulary = ["current", "expected_wait", "stale", "failed", "partial", "not_applicable", "unknown"]
    result = adapt_receipt(
        {
            "task": "baldr-data-freshness-check-daily",
            "status": "degraded",
            "checked_at": "2026-10-21T08:00:00+08:00",
            "source_statuses": [{"freshness_status": "expected_wait"}, {"freshness_status": "stale"}],
            "status_vocabulary": vocabulary,
        }
    )
    assert result["supported"] is True
    assert result["run_id"] is None
    assert result["started_at"] is None
    assert result["completed_at"] is None
    assert result["source_freshness"]["raw_status"] == ["expected_wait", "stale"]
    assert result["source_freshness"]["semantic"] == "degraded"


def test_official_market_pointer_never_becomes_a_producer_result() -> None:
    """可解析的 pointer 只代表定位資料，不能借用 bundle 的成功狀態。"""
    result = adapt_receipt(
        {
            "schema_version": "scheduled-official-market-events-wrapper-pointer.v1",
            "status": "passed",
            "wrapper_run_id": "run-1",
            "status_path": "bundle.json",
        }
    )
    assert result["supported"] is True
    assert result["kind"] == "pointer"
    assert result["producer_status"] == "passed"
    assert result["producer_status_semantic"] == "pointer_only"
    assert result["observability"]["semantic"] == "pointer_only"
    assert result["started_at"] is None


def test_official_bundle_maps_only_its_declared_wrapper_clocks() -> None:
    """官方 bundle 的 wrapper clocks 依其專用欄位映射。"""
    result = adapt_receipt(
        {
            "schema_version": "scheduled-official-market-status-bundle.v1",
            "overall_status": "blocked",
            "wrapper_run_id": "wrapper-1",
            "started_at": "2026-10-21T08:00:00Z",
            "finished_at": "2026-10-21T08:01:00Z",
        }
    )
    assert result["kind"] == "producer"
    assert result["run_id"] == "wrapper-1"
    assert result["started_at"] == "2026-10-21T08:00:00Z"
    assert result["completed_at"] == "2026-10-21T08:01:00Z"
    assert result["producer_status_semantic"] == "blocked"


def test_weekly_controller_receipt_maps_utc_clocks_but_terminal_is_not_success() -> None:
    result = adapt_receipt(
        {
            "schema_version": "scheduled-weekly-collection-controller-receipt.v2",
            "task": "baldr-v2-2-weekly-collection",
            "run_id": "weekly-run-1",
            "started_at_utc": "2026-10-18T18:00:01Z",
            "completed_at_utc": "2026-10-18T18:02:35Z",
            "status": "terminal",
            "exit_code": 0,
        }
    )
    assert result["producer_task"] == "baldr-v2-2-weekly-collection"
    assert result["run_id"] == "weekly-run-1"
    assert result["started_at"] == "2026-10-18T18:00:01Z"
    assert result["completed_at"] == "2026-10-18T18:02:35Z"
    assert result["producer_status"] == "terminal"
    assert result["producer_status_semantic"] == "unknown"


def test_adapter_preserves_explicit_producer_task_identity() -> None:
    result = adapt_receipt(
        {
            "schema_version": "scheduled-official-market-status-bundle.v1",
            "task": "another-scheduled-producer",
            "overall_status": "succeeded",
            "wrapper_run_id": "wrapper-1",
            "started_at": "2026-10-21T08:00:00Z",
            "finished_at": "2026-10-21T08:01:00Z",
        }
    )
    assert result["producer_task"] == "another-scheduled-producer"


def test_dependency_gate_observation_is_not_a_started_at_clock() -> None:
    """Paper dependency assessment 的 observed_at 不等於執行開始時間。"""
    result = adapt_receipt(
        {
            "schema_version": "paper-execution-dependency-gate.v1",
            "status": "blocked",
            "observed_at": "2026-10-21T08:00:00Z",
            "blockers": ["source_not_ready"],
        }
    )
    assert result["started_at"] is None
    assert result["completed_at"] is None
    assert result["producer_status"] == "blocked"
    assert result["blockers"] == ["source_not_ready"]
    assert "run_id" in result["missing_fields"]


def test_launcher_and_unknown_schema_do_not_claim_producer_success() -> None:
    """Launcher 終端收據與未知 schema 都不能表示 producer 已成功。"""
    launcher = adapt_receipt(
        {
            "schema_version": "scheduled-hidden-launch.v1",
            "status": "passed",
            "run_id": "launcher-1",
        }
    )
    unknown = adapt_receipt({"schema_version": "ml-forward-scheduled-status.v99", "status": "passed"})
    assert launcher["kind"] == "launcher"
    assert launcher["producer_status_semantic"] == "launcher_only"
    assert unknown["supported"] is False
    assert unknown["producer_status_semantic"] == "unknown"
    assert unknown["missing_fields"] == ["schema_version_or_exact_legacy_contract"]


def test_status_prefixes_are_not_guessed() -> None:
    """未列入語意表的狀態完整保留，但分類為 unknown。"""
    result = adapt_receipt(
        {
            "schema_version": "ml-forward-scheduled-status.v1",
            "status": "blocked_future_state",
            "run_id": "run-1",
        }
    )
    assert result["producer_status"] == "blocked_future_state"
    assert result["producer_status_semantic"] == "unknown"


def test_explicit_unknown_schema_cannot_fall_back_to_a_legacy_task() -> None:
    """存在未知 schema 字段時不可改以 task 形狀接受舊契約。"""
    result = adapt_receipt(
        {
            "schema_version": "baldr-data-update-quick-daily.v99",
            "task": "baldr-data-update-quick-daily",
            "status": "passed",
            "run_id": "run-1",
            "started_at": "2026-10-21T08:00:00Z",
            "completed_at": "2026-10-21T08:01:00Z",
        }
    )
    assert result["supported"] is False
    assert result["producer_status_semantic"] == "unknown"


def test_legacy_evidence_shape_preserves_status_but_requires_run_identity() -> None:
    """舊 Evidence 外層缺少 run identity 時保留狀態但分類未知。"""
    result = adapt_receipt(
        {
            "task": "baldr-evidence-pipeline-dry-run-daily",
            "status": "passed",
            "dry_run": True,
            "confirm": False,
            "exit_code": 0,
            "pipeline_execution_started": True,
        }
    )
    assert result["supported"] is True
    assert result["producer_status"] == "passed"
    assert result["producer_status_semantic"] == "unknown"
    assert "run_id" in result["missing_fields"]
    assert "started_at" in result["missing_fields"]


def test_track_statuses_use_track_specific_vocabulary() -> None:
    """資料新鮮度詞彙依其專屬分類表處理。"""
    result = adapt_receipt(
        {
            "task": "baldr-data-freshness-check-daily",
            "status": "partial",
            "checked_at": "2026-10-21T08:00:00Z",
            "source_statuses": [{"freshness_status": "stale"}],
            "status_vocabulary": ["current", "expected_wait", "stale", "failed", "partial", "not_applicable", "unknown"],
        }
    )
    assert result["source_freshness"]["semantic"] == "degraded"


def test_versioned_freshness_and_evidence_receipts_have_exact_run_identity() -> None:
    """新版 Freshness 與 Evidence 收據提供各自明確的終態身份欄位。"""
    freshness = adapt_receipt(
        {
            "schema_version": "baldr-data-freshness-terminal-receipt.v1",
            "task": "baldr-data-freshness-check-daily",
            "run_id": "freshness-run",
            "started_at": "2026-10-21T08:00:00Z",
            "completed_at": "2026-10-21T08:01:00Z",
            "status": "passed",
        }
    )
    evidence = adapt_receipt(
        {
            "schema_version": "baldr-evidence-pipeline-terminal-receipt.v1",
            "task": "baldr-evidence-pipeline-dry-run-daily",
            "run_id": "evidence-run",
            "started_at": "2026-10-21T08:00:00Z",
            "completed_at": "2026-10-21T08:02:00Z",
            "status": "failed",
            "dry_run": True,
            "confirm": False,
            "exit_code": 2,
            "pipeline_execution_started": False,
        }
    )
    assert freshness["supported"] is True
    assert freshness["run_id"] == "freshness-run"
    assert evidence["supported"] is True
    assert evidence["run_id"] == "evidence-run"
    assert evidence["producer_status_semantic"] == "failed"


def test_formal_terminal_receipt_preserves_status_but_never_qualifies_finance() -> None:
    run_id = "0123456789abcdef0123456789abcdef"
    status_payload = {
        "schema_version": "formal-input-daily-producer-receipt.v1",
        "task": "baldr-formal-input-producer-daily",
        "run_id": run_id,
        "wrapper_started_at": "2026-10-22T04:25:03+00:00",
        "completed_at": "2026-10-22T04:25:04+00:00",
        "status": "candidate_only",
        "blockers": ["runtime_config_expired"],
        "financial_qualification_status": "qualified",
        "exit_code": 2,
    }
    receipt = {
        "schema_version": "formal-input-producer-terminal-receipt.v1",
        "task": "baldr-formal-input-producer-daily",
        "run_id": run_id,
        "started_at": "2026-10-22T04:25:03+00:00",
        "completed_at": "2026-10-22T04:25:04+00:00",
        "code_version": "sha256:" + "a" * 64,
        "exit_code": 2,
        "failure_code": "runtime_config_expired",
        "status": "candidate_only",
        "blockers": ["runtime_config_expired"],
        "financial_qualification_status": "unknown",
        "dependency_readiness_status": "blocked",
        "status_payload": status_payload,
    }

    result = adapt_receipt(receipt)

    assert result["supported"] is True
    assert result["schema"] == "formal-input-producer-terminal-receipt.v1"
    assert result["producer_task"] == receipt["task"]
    assert result["run_id"] == run_id
    assert result["started_at"] == receipt["started_at"]
    assert result["completed_at"] == receipt["completed_at"]
    assert result["producer_status"] == status_payload["status"]
    assert result["producer_status_semantic"] == "degraded"
    assert result["failure_code"] == "runtime_config_expired"
    assert result["blockers"] == ["runtime_config_expired"]
    assert result["financial_qualification"]["raw_status"] == "unknown"
    assert result["financial_qualification"]["semantic"] == "unknown"
    assert result["dependency_readiness"]["raw_status"] == "blocked"
    assert result["dependency_readiness"]["semantic"] == "blocked"

    extra_top_level_field = {**receipt, "financial_claim": "qualified"}
    rejected = adapt_receipt(extra_top_level_field)
    assert rejected["supported"] is False
    assert rejected["producer_status_semantic"] == "unknown"
    assert rejected["missing_fields"] == ["formal_terminal_contract_invalid"]

    unknown_nested_schema = {
        **receipt,
        "status_payload": {
            **status_payload,
            "schema_version": "formal-input-daily-producer-receipt.v99",
        },
    }
    rejected_nested = adapt_receipt(unknown_nested_schema)
    assert rejected_nested["supported"] is False
    assert rejected_nested["producer_status_semantic"] == "unknown"

    outer_exit_mismatch = {**receipt, "exit_code": 0}
    rejected_exit = adapt_receipt(outer_exit_mismatch)
    assert rejected_exit["supported"] is False

    boolean_nested_exit = {
        **receipt,
        "status_payload": {**status_payload, "exit_code": True},
    }
    rejected_boolean_exit = adapt_receipt(boolean_nested_exit)
    assert rejected_boolean_exit["supported"] is False

    candidate_zero_exit = {
        **receipt,
        "exit_code": 0,
        "status_payload": {**status_payload, "exit_code": 0},
    }
    rejected_candidate_exit = adapt_receipt(candidate_zero_exit)
    assert rejected_candidate_exit["supported"] is False

    formal_pass_with_blocker = {
        **receipt,
        "exit_code": 0,
        "failure_code": "unexpected_blocker",
        "status": "formal_inputs_machine_verified",
        "blockers": ["unexpected_blocker"],
        "dependency_readiness_status": "passed",
        "status_payload": {
            **status_payload,
            "status": "formal_inputs_machine_verified",
            "exit_code": 0,
            "blockers": ["unexpected_blocker"],
        },
    }
    rejected_formal_blocker = adapt_receipt(formal_pass_with_blocker)
    assert rejected_formal_blocker["supported"] is False

    skipped = {
        **receipt,
        "exit_code": 0,
        "failure_code": None,
        "status": "skipped_non_trading_day",
        "blockers": [],
        "dependency_readiness_status": "not_applicable",
        "status_payload": {
            **status_payload,
            "status": "skipped_non_trading_day",
            "exit_code": 0,
            "blockers": [],
        },
    }
    assert adapt_receipt(skipped)["supported"] is True

    skipped_with_log_failure = {
        **skipped,
        "failure_code": "attempt_log_write_failed",
        "blockers": ["attempt_log_write_failed"],
        "dependency_readiness_status": "blocked",
        "status_payload": {
            **skipped["status_payload"],
            "observability_blocker": "attempt_log_write_failed",
        },
    }
    skipped_result = adapt_receipt(skipped_with_log_failure)
    assert skipped_result["supported"] is True
    assert skipped_result["dependency_readiness"]["semantic"] == "blocked"

    skipped_nonzero = {
        **skipped,
        "exit_code": 2,
        "status_payload": {**skipped["status_payload"], "exit_code": 2},
    }
    assert adapt_receipt(skipped_nonzero)["supported"] is False
