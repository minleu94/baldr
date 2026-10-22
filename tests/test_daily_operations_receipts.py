"""唯讀每日營運收據轉接器的契約測試。"""

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
