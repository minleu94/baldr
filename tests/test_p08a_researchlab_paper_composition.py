"""Paper composition 的 exact input 與唯讀兩階段資料契約。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
import os
import stat

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QListWidgetItem

import app_module.application_bootstrap as bootstrap_module
import data_module.config as config_module
import app_module.strategy_paper_account_availability as availability_module
from app_module.application_bootstrap import resolve_application_settings
from data_module.config import (
    TWStockConfig,
    _paper_contract_artifacts_root_error_from_environment,
    _paper_contract_artifacts_root_from_environment,
)
from app_module.paper_checkpoint_ui_composition import PaperCheckpointAccountInputs
from app_module.personal_store_routes import PersonalStoreMode
from app_module.strategy_paper_account_availability import (
    list_strategy_paper_account_checkpoint_candidates,
)
from app_module.strategy_performance_read_service import (
    PaperCheckpointSelector,
    QualificationStatus,
    ReadStatus,
    StrategyPerformanceReadService,
)
from test_strategy_paper_account_daily import (
    _create_account,
    _seed_account,
    _writer,
    _zero_fill_call,
)
from ui_qt.widgets.paper_checkpoint_catalogue_lookup import (
    PaperCheckpointCatalogueLookupWidget,
    build_exact_selector,
    parse_explicit_aware_cutoff,
)


_CONFIG = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}
_CUTOFF = datetime(2026, 8, 5, 9, 0, tzinfo=timezone.utc)


def _composed_account(tmp_path, monkeypatch):
    original_service, personal_paths, manifest = _create_account(tmp_path)
    selection = SimpleNamespace(
        mode=PersonalStoreMode.PERSONAL,
        paths=personal_paths,
    )
    inputs, reason = PaperCheckpointAccountInputs.from_selection(
        selection,
        contract_artifacts_root=original_service.contract_artifacts_root,
    )
    assert reason is None
    assert inputs is not None
    shared_version_service = SimpleNamespace(
        versions_dir=original_service.strategy_versions_root
    )
    account_service = inputs.build_account_service(shared_version_service)
    prior, store_paths, binding = _seed_account(
        account_service, personal_paths, manifest, monkeypatch
    )
    monkeypatch.setattr(availability_module, "_utc_now", lambda: _CUTOFF)
    result_id = "research-lab-paper-composition-checkpoint"
    result = _zero_fill_call(
        _writer(account_service, personal_paths, result_id, _CONFIG),
        binding,
        prior,
        result_id=result_id,
    )
    return inputs, shared_version_service, account_service, store_paths, binding, result


def test_personal_external_root_is_explicit_and_versions_root_is_shared(tmp_path):
    original_service, paths, _manifest = _create_account(tmp_path)
    personal = SimpleNamespace(mode=PersonalStoreMode.PERSONAL, paths=paths)
    missing, missing_reason = PaperCheckpointAccountInputs.from_selection(
        personal,
        contract_artifacts_root=None,
    )
    assert missing is None
    assert missing_reason == "請明示 PAPER_CONTRACT_ARTIFACTS_ROOT 外部絕對路徑。"

    legacy = SimpleNamespace(mode=PersonalStoreMode.LEGACY_COMPAT, paths=paths)
    disabled, disabled_reason = PaperCheckpointAccountInputs.from_selection(
        legacy,
        contract_artifacts_root=original_service.contract_artifacts_root,
    )
    assert disabled is None
    assert disabled_reason == "Paper 策略帳戶只在 PERSONAL store 模式提供。"

    relative, relative_reason = PaperCheckpointAccountInputs.from_selection(
        personal,
        contract_artifacts_root="contracts",
    )
    assert relative is None
    assert relative_reason == "PAPER_CONTRACT_ARTIFACTS_ROOT 必須是明示絕對路徑。"

    package_root, package_reason = PaperCheckpointAccountInputs.from_selection(
        personal,
        contract_artifacts_root=Path(__file__).resolve().parents[1],
    )
    assert package_root is None
    assert package_reason == "PAPER_CONTRACT_ARTIFACTS_ROOT 必須位於應用程式套件外部。"

    inputs, reason = PaperCheckpointAccountInputs.from_selection(
        personal,
        contract_artifacts_root=original_service.contract_artifacts_root,
    )
    assert reason is None
    assert inputs is not None
    shared = SimpleNamespace(versions_dir=original_service.strategy_versions_root)
    composed = inputs.build_account_service(shared)
    assert composed.personal_paths is paths
    assert composed.strategy_versions_root == shared.versions_dir
    assert composed.contract_artifacts_root == inputs.contract_artifacts_root


def test_cutoff_requires_user_supplied_timezone_offset():
    assert parse_explicit_aware_cutoff("2026-08-05T09:00:00+00:00") == _CUTOFF
    with pytest.raises(ValueError, match="明示時區感知"):
        parse_explicit_aware_cutoff("")
    with pytest.raises(ValueError, match="明示時區偏移"):
        parse_explicit_aware_cutoff("2026-08-05T09:00:00")


def test_real_writer_catalogue_then_explicit_exact_reader_is_read_only(
    tmp_path, monkeypatch
):
    (
        _inputs,
        _shared_version_service,
        account_service,
        store_paths,
        binding,
        result,
    ) = _composed_account(tmp_path, monkeypatch)
    before = {
        store_paths.state_db: store_paths.state_db.read_bytes(),
        store_paths.cost_ledger_db: store_paths.cost_ledger_db.read_bytes(),
    }

    catalogue = list_strategy_paper_account_checkpoint_candidates(
        account_service,
        strategy_id=binding.strategy_id,
        strategy_version_id=binding.strategy_version_id,
        account_namespace=binding.account_namespace,
        decision_cutoff=_CUTOFF,
    )
    assert len(catalogue.rows) == 1
    candidate = catalogue.rows[0]
    assert candidate.operation_id == result.operation_id
    assert candidate.snapshot_id == result.snapshot_id
    assert candidate.row_state == "candidate_pending_exact_reader"
    assert candidate.checkpoint_verified is False
    assert candidate.performance_eligible is False

    selector = build_exact_selector(
        strategy_id=binding.strategy_id,
        strategy_version_id=binding.strategy_version_id,
        account_namespace=binding.account_namespace,
        decision_cutoff=_CUTOFF,
        catalogue=catalogue,
        candidate=candidate,
    )
    assert type(selector) is PaperCheckpointSelector
    reader = StrategyPerformanceReadService(account_service=account_service)
    card = reader.read_paper_checkpoint(selector)
    assert card.read_status is ReadStatus.VERIFIED
    assert card.qualification is QualificationStatus.NOT_QUALIFIED
    assert card.operation_id == result.operation_id
    assert card.snapshot_id == result.snapshot_id
    assert card.source_availability_status.value == "unverified"
    assert card.period_curve_status == "unavailable"
    assert all(metric.value is None for _name, metric in card.metrics)
    assert all(path.read_bytes() == raw for path, raw in before.items())


def test_candidate_cannot_be_rebound_to_another_query_or_catalogue():
    from app_module.strategy_paper_account_availability import (
        StrategyPaperAccountCheckpointCandidate,
        StrategyPaperAccountCheckpointCatalogue,
    )

    candidate = StrategyPaperAccountCheckpointCandidate(
        operation_id="operation-1",
        snapshot_id="snapshot-1",
        observed_schema_version="strategy-paper-account-availability.v1",
        observed_portfolio_id="portfolio-1",
        observed_account_namespace="namespace-1",
        observed_binding_sha256="sha256:" + "a" * 64,
        observed_snapshot_sha256="sha256:" + "b" * 64,
        observed_base_receipt_sha256="sha256:" + "c" * 64,
        observed_availability_receipt_sha256="sha256:" + "d" * 64,
        persisted_at_text="2026-08-04T00:00:00+00:00",
        available_at_text="2026-08-04T00:00:00+00:00",
        persisted_at=_CUTOFF,
        available_at=_CUTOFF,
        row_state="candidate_pending_exact_reader",
        blockers=(),
    )
    catalogue = StrategyPaperAccountCheckpointCatalogue(
        schema_version="strategy-paper-account-checkpoint-catalogue.v1",
        strategy_id="strategy-1",
        strategy_version_id="version-1",
        account_namespace="namespace-1",
        portfolio_id="portfolio-1",
        binding_sha256="sha256:" + "a" * 64,
        decision_cutoff=_CUTOFF,
        rows=(candidate,),
        truncated=False,
        complete=True,
    )
    exact = build_exact_selector(
        strategy_id="strategy-1",
        strategy_version_id="version-1",
        account_namespace="namespace-1",
        decision_cutoff=_CUTOFF,
        catalogue=catalogue,
        candidate=candidate,
    )
    assert exact.operation_id == "operation-1"
    with pytest.raises(ValueError, match="not_bound"):
        build_exact_selector(
            strategy_id="strategy-1",
            strategy_version_id="version-other",
            account_namespace="namespace-1",
            decision_cutoff=_CUTOFF,
            catalogue=catalogue,
            candidate=candidate,
        )

    detached_copy = replace(candidate)
    with pytest.raises(ValueError, match="not_bound"):
        build_exact_selector(
            strategy_id="strategy-1",
            strategy_version_id="version-1",
            account_namespace="namespace-1",
            decision_cutoff=_CUTOFF,
            catalogue=catalogue,
            candidate=detached_copy,
        )


def test_optional_paper_root_keeps_bootstrap_config_and_picker_available(
    tmp_path, monkeypatch
):
    base = {
        "DATA_ROOT": str(tmp_path / "market"),
        "OUTPUT_ROOT": str(tmp_path / "output"),
        "LOCALAPPDATA": str(tmp_path / "local"),
    }
    missing = resolve_application_settings(environ=base)
    assert "PAPER_CONTRACT_ARTIFACTS_ROOT" not in missing.environment
    assert "未提供 PAPER_CONTRACT_ARTIFACTS_ROOT" in (
        missing.paper_contract_artifacts_root_error
    )

    blank = resolve_application_settings(
        environ={**base, "PAPER_CONTRACT_ARTIFACTS_ROOT": "  "}
    )
    assert "PAPER_CONTRACT_ARTIFACTS_ROOT" not in blank.environment
    assert "未設定或為空" in blank.paper_contract_artifacts_root_error

    relative = resolve_application_settings(
        environ={**base, "PAPER_CONTRACT_ARTIFACTS_ROOT": "contracts"}
    )
    assert "PAPER_CONTRACT_ARTIFACTS_ROOT" not in relative.environment
    assert "明示絕對路徑" in relative.paper_contract_artifacts_root_error

    portable = tmp_path / "portable-config.json"
    portable.write_text(
        '{"PAPER_CONTRACT_ARTIFACTS_ROOT":"contracts"}',
        encoding="utf-8",
    )
    from_file = resolve_application_settings(
        environ={**base, "BALDR_CONFIG": str(portable)}
    )
    assert "PAPER_CONTRACT_ARTIFACTS_ROOT" not in from_file.environment
    assert "明示絕對路徑" in from_file.paper_contract_artifacts_root_error

    bundle = tmp_path / "frozen-bundle"
    bundled = resolve_application_settings(
        environ={**base, "PAPER_CONTRACT_ARTIFACTS_ROOT": str(bundle / "contracts")},
        resource_root=bundle,
        frozen=True,
    )
    assert "PAPER_CONTRACT_ARTIFACTS_ROOT" not in bundled.environment
    assert "frozen 程式包內" in bundled.paper_contract_artifacts_root_error
    with pytest.raises(ValueError, match="DATA_ROOT"):
        resolve_application_settings(environ={**base, "DATA_ROOT": "relative-data"})

    monkeypatch.delenv("_BALDR_PAPER_CONTRACT_ARTIFACTS_ROOT_BLOCKER", raising=False)
    monkeypatch.delenv("PAPER_CONTRACT_ARTIFACTS_ROOT", raising=False)
    assert _paper_contract_artifacts_root_from_environment() is None
    assert "未提供 PAPER_CONTRACT_ARTIFACTS_ROOT" in (
        _paper_contract_artifacts_root_error_from_environment()
    )
    monkeypatch.setenv("PAPER_CONTRACT_ARTIFACTS_ROOT", "contracts")
    assert _paper_contract_artifacts_root_from_environment() is None
    assert "明示絕對路徑" in _paper_contract_artifacts_root_error_from_environment()
    for name in (
        "PERSONAL_DATA_ROOT",
        "PERSONAL_WATCHLIST_SOURCE",
        "PERSONAL_JOURNAL_ROOT",
        "PERSONAL_JOURNAL_MODE",
        "PERSONAL_STORE_ROOT",
        "PERSONAL_STORE_MODE",
        "PERSONAL_MODEL_POLICY_PATH",
    ):
        monkeypatch.delenv(name, raising=False)
    config = TWStockConfig(
        data_root=tmp_path / "config-market",
        output_root=tmp_path / "config-output",
        profile="prod",
    )
    assert config.paper_contract_artifacts_root is None
    assert "明示絕對路徑" in config.paper_contract_artifacts_root_error

    original_service, paths, _manifest = _create_account(tmp_path)
    selection = SimpleNamespace(mode=PersonalStoreMode.PERSONAL, paths=paths)
    disabled, reason = PaperCheckpointAccountInputs.from_selection(
        selection,
        contract_artifacts_root=config.paper_contract_artifacts_root,
        disabled_reason=config.paper_contract_artifacts_root_error,
    )
    assert disabled is None
    assert reason == config.paper_contract_artifacts_root_error

    app = QApplication.instance() or QApplication([])
    picker = PaperCheckpointCatalogueLookupWidget(
        account_service=None,
        performance_reader=None,
        performance_card=None,
        disabled_reason=reason,
    )
    assert picker.discover_button.isEnabled() is False
    assert reason in picker.status.text()
    picker.close()
    assert QApplication.instance() is not None


class _DeferredSignal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self, *args):
        for callback in tuple(self.callbacks):
            callback(*args)


class _DeferredWorker:
    def __init__(self, task):
        self.task = task
        self.finished = _DeferredSignal()
        self.error = _DeferredSignal()
        self.native_thread_finished = _DeferredSignal()
        self.cancel_calls = []
        self.deleted = 0

    def start(self):
        return None

    def cancel(self, **kwargs):
        self.cancel_calls.append(kwargs)

    def deleteLater(self):
        self.deleted += 1


class _ClearCountingCard:
    def __init__(self):
        self.clear_count = 0

    def clear_selection(self):
        self.clear_count += 1


def test_stale_paper_error_and_cleanup_leave_new_selection_worker_untouched(
    monkeypatch,
):
    app = QApplication.instance() or QApplication([])
    from ui_qt.workers import task_worker

    workers = []

    def make_worker(task):
        worker = _DeferredWorker(task)
        workers.append(worker)
        return worker

    monkeypatch.setattr(task_worker, "TaskWorker", make_worker)
    from app_module.strategy_paper_account_availability import (
        StrategyPaperAccountCheckpointCandidate,
        StrategyPaperAccountCheckpointCatalogue,
    )

    cutoff = _CUTOFF
    candidate = StrategyPaperAccountCheckpointCandidate(
        operation_id="operation-1",
        snapshot_id="snapshot-1",
        observed_schema_version="strategy-paper-account-availability.v1",
        observed_portfolio_id="portfolio-1",
        observed_account_namespace="namespace-1",
        observed_binding_sha256="sha256:" + "a" * 64,
        observed_snapshot_sha256="sha256:" + "b" * 64,
        observed_base_receipt_sha256="sha256:" + "c" * 64,
        observed_availability_receipt_sha256="sha256:" + "d" * 64,
        persisted_at_text="2026-08-04T00:00:00+00:00",
        available_at_text="2026-08-04T00:00:00+00:00",
        persisted_at=cutoff,
        available_at=cutoff,
        row_state="candidate_pending_exact_reader",
        blockers=(),
    )
    catalogue = StrategyPaperAccountCheckpointCatalogue(
        schema_version="strategy-paper-account-checkpoint-catalogue.v1",
        strategy_id="strategy-1",
        strategy_version_id="version-1",
        account_namespace="namespace-1",
        portfolio_id="portfolio-1",
        binding_sha256="sha256:" + "a" * 64,
        decision_cutoff=cutoff,
        rows=(candidate,),
        truncated=False,
        complete=True,
    )
    card = _ClearCountingCard()
    picker = PaperCheckpointCatalogueLookupWidget(
        account_service=object(),
        performance_reader=object(),
        performance_card=card,
        disabled_reason=None,
    )
    picker._catalogue = catalogue
    old_token = picker._request_id
    picker._start_worker(lambda _cancel: None, lambda _value: None, token=old_token)
    old_worker = picker.worker
    selected_item = QListWidgetItem("目前明示選取")
    selected_item.setData(Qt.ItemDataRole.UserRole, candidate)
    picker._candidate_changed(selected_item)
    assert picker._selected_row is candidate
    assert picker._request_id == old_token + 1
    assert old_worker.cancel_calls

    old_worker.native_thread_finished.emit()
    new_token = picker._request_id
    picker._start_worker(lambda _cancel: None, lambda _value: None, token=new_token)
    new_worker = picker.worker
    assert new_worker is not old_worker
    assert picker.discover_button.isEnabled() is False
    picker.status.setText("新選取的工作仍在執行")
    clear_count = card.clear_count

    old_worker.error.emit("已過期的讀取錯誤")
    old_worker.native_thread_finished.emit()
    assert picker.worker is new_worker
    assert picker.status.text() == "新選取的工作仍在執行"
    assert picker.discover_button.isEnabled() is False
    assert card.clear_count == clear_count

    picker.close()
    assert picker._closed is True
    assert new_worker.cancel_calls
    assert picker.worker is new_worker
    assert QApplication.instance() is not None


def test_standalone_picker_close_invalidates_late_reply_and_keeps_worker_until_native_finish(
    monkeypatch,
):
    app = QApplication.instance() or QApplication([])
    from ui_qt.workers import task_worker

    worker_box = []

    def make_worker(task):
        worker = _DeferredWorker(task)
        worker_box.append(worker)
        return worker

    monkeypatch.setattr(task_worker, "TaskWorker", make_worker)
    picker = PaperCheckpointCatalogueLookupWidget(
        account_service=object(),
        performance_reader=object(),
        performance_card=_ClearCountingCard(),
        disabled_reason=None,
    )
    token = picker._request_id
    picker._start_worker(lambda _cancel: None, lambda _value: None, token=token)
    worker = picker.worker
    event = QCloseEvent()
    picker.closeEvent(event)
    assert event.isAccepted()
    assert picker._closed is True
    assert picker.worker is worker
    assert worker.cancel_calls

    status_after_close = picker.status.text()
    worker.finished.emit(object())
    assert picker.status.text() == status_after_close
    assert picker.worker is worker
    worker.native_thread_finished.emit()
    assert picker.worker is None
    assert picker.discover_button.isEnabled() is False
    assert QApplication.instance() is not None

def test_paper_root_reparse_ancestor_is_rejected_before_bootstrap_normalization(
    tmp_path, monkeypatch
):
    paper_root = tmp_path / "paper-junction" / "contracts"
    reparse_parent = paper_root.parent
    real_lstat = config_module._paper_path_lstat
    seen = []

    def fake_lstat(path):
        candidate = Path(path)
        seen.append(candidate)
        if candidate == reparse_parent:
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        return real_lstat(candidate)

    monkeypatch.setattr(config_module, "_paper_path_lstat", fake_lstat)
    original_canonical = bootstrap_module._canonical_path

    def reject_paper_canonicalization(path):
        if Path(path) == paper_root:
            pytest.fail("Paper 根在 reparse guard 之前被 canonicalize")
        return original_canonical(path)

    monkeypatch.setattr(
        bootstrap_module, "_canonical_path", reject_paper_canonicalization
    )
    base = {
        "DATA_ROOT": str(tmp_path / "market"),
        "OUTPUT_ROOT": str(tmp_path / "output"),
        "LOCALAPPDATA": str(tmp_path / "local"),
        "PAPER_CONTRACT_ARTIFACTS_ROOT": str(paper_root),
    }

    settings = bootstrap_module.resolve_application_settings(environ=base)

    assert "PAPER_CONTRACT_ARTIFACTS_ROOT" not in settings.environment
    assert "Windows reparse point" in settings.paper_contract_artifacts_root_error
    assert reparse_parent in seen
    assert paper_root not in seen


def test_paper_root_symlink_is_rejected_before_input_resolution_or_service(
    tmp_path, monkeypatch
):
    original_service, personal_paths, _manifest = _create_account(tmp_path)
    paper_root = Path(original_service.contract_artifacts_root)
    real_lstat = config_module._paper_path_lstat
    seen = []

    def fake_lstat(path):
        candidate = Path(path)
        seen.append(candidate)
        if candidate == paper_root:
            return SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0x400)
        return real_lstat(candidate)

    monkeypatch.setattr(config_module, "_paper_path_lstat", fake_lstat)
    path_type = type(paper_root)
    original_resolve = path_type.resolve
    resolve_calls = []

    def track_resolve(self, *args, **kwargs):
        resolve_calls.append(Path(self))
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(path_type, "resolve", track_resolve)
    selection = SimpleNamespace(
        mode=PersonalStoreMode.PERSONAL,
        paths=personal_paths,
    )

    inputs, reason = PaperCheckpointAccountInputs.from_selection(
        selection,
        contract_artifacts_root=paper_root,
    )

    assert inputs is None
    assert "符號連結" in reason
    assert paper_root in seen
    assert resolve_calls == []
    with pytest.raises(ValueError, match="符號連結"):
        PaperCheckpointAccountInputs(personal_paths, paper_root)
    assert resolve_calls == []


def test_paper_tilde_root_is_not_expanded_and_stays_disabled(
    tmp_path, monkeypatch
):
    _original_service, personal_paths, _manifest = _create_account(tmp_path)
    path_type = type(Path())
    original_expanduser = path_type.expanduser
    expanded_tilde = []

    def track_expanduser(self):
        if str(self).startswith("~"):
            expanded_tilde.append(str(self))
            pytest.fail("Paper 選用路徑不應呼叫 expanduser")
        return original_expanduser(self)

    monkeypatch.setattr(path_type, "expanduser", track_expanduser)
    monkeypatch.setattr(
        config_module,
        "_paper_path_lstat",
        lambda _path: pytest.fail("相對 Paper 根不應進入 lstat"),
    )
    base = {
        "DATA_ROOT": str(tmp_path / "market"),
        "OUTPUT_ROOT": str(tmp_path / "output"),
        "LOCALAPPDATA": str(tmp_path / "local"),
        "PAPER_CONTRACT_ARTIFACTS_ROOT": "~/contracts",
    }

    settings = bootstrap_module.resolve_application_settings(environ=base)
    assert "PAPER_CONTRACT_ARTIFACTS_ROOT" not in settings.environment
    assert "明示絕對路徑" in settings.paper_contract_artifacts_root_error

    monkeypatch.setenv("PAPER_CONTRACT_ARTIFACTS_ROOT", "~/contracts")
    assert _paper_contract_artifacts_root_from_environment() is None
    assert "明示絕對路徑" in _paper_contract_artifacts_root_error_from_environment()
    selection = SimpleNamespace(
        mode=PersonalStoreMode.PERSONAL,
        paths=personal_paths,
    )
    inputs, reason = PaperCheckpointAccountInputs.from_selection(
        selection,
        contract_artifacts_root="~/contracts",
    )
    assert inputs is None
    assert "明示絕對路徑" in reason
    assert expanded_tilde == []


def test_paper_parent_component_with_missing_then_reparse_is_rejected_before_path_ops(
    tmp_path, monkeypatch
):
    _, personal_paths, _manifest = _create_account(tmp_path)
    raw_root = str(tmp_path / "missing" / ".." / "junction" / "contracts")
    assert ".." in Path(raw_root).parts

    missing_parent = tmp_path / "missing"
    reparse_parent = tmp_path / "junction"
    lstat_paths = []
    real_lstat = config_module._paper_path_lstat

    def fake_lstat(path):
        candidate = Path(path)
        lstat_paths.append(candidate)
        if candidate == missing_parent:
            raise FileNotFoundError
        if candidate == reparse_parent:
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        return real_lstat(candidate)

    monkeypatch.setattr(config_module, "_paper_path_lstat", fake_lstat)
    path_type = type(Path(raw_root))
    original_resolve = path_type.resolve
    resolve_paths = []

    def track_resolve(self, *args, **kwargs):
        candidate = Path(self)
        if ".." in candidate.parts:
            resolve_paths.append(candidate)
            pytest.fail("含 .. 的 Paper 根不應進入 resolve")
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(path_type, "resolve", track_resolve)
    original_expanduser = path_type.expanduser
    expanduser_paths = []

    def track_expanduser(self):
        candidate = Path(self)
        if ".." in candidate.parts:
            expanduser_paths.append(candidate)
            pytest.fail("含 .. 的 Paper 根不應進入 expanduser")
        return original_expanduser(self)

    monkeypatch.setattr(path_type, "expanduser", track_expanduser)
    original_canonical = bootstrap_module._canonical_path
    canonical_paths = []

    def track_canonical(path):
        candidate = Path(path)
        if ".." in candidate.parts:
            canonical_paths.append(candidate)
            pytest.fail("含 .. 的 Paper 根不應進入 bootstrap canonicalizer")
        return original_canonical(path)

    monkeypatch.setattr(bootstrap_module, "_canonical_path", track_canonical)
    base = {
        "DATA_ROOT": str(tmp_path / "market"),
        "OUTPUT_ROOT": str(tmp_path / "output"),
        "LOCALAPPDATA": str(tmp_path / "local"),
        "PAPER_CONTRACT_ARTIFACTS_ROOT": raw_root,
    }

    settings = bootstrap_module.resolve_application_settings(environ=base)

    assert "PAPER_CONTRACT_ARTIFACTS_ROOT" not in settings.environment
    assert "不得包含 '..'" in settings.paper_contract_artifacts_root_error
    assert lstat_paths == []
    assert resolve_paths == []
    assert expanduser_paths == []
    assert canonical_paths == []

    selection = SimpleNamespace(mode=PersonalStoreMode.PERSONAL, paths=personal_paths)
    inputs, reason = PaperCheckpointAccountInputs.from_selection(
        selection,
        contract_artifacts_root=raw_root,
    )
    assert inputs is None
    assert "不得包含 '..'" in reason
    assert lstat_paths == []
    assert resolve_paths == []
    assert expanduser_paths == []
    assert canonical_paths == []


def test_portable_json_nul_paper_root_disables_only_paper_before_path_ops(
    tmp_path, monkeypatch
):
    portable = tmp_path / "nul-paper-root.json"
    portable.write_text(
        r'{"PAPER_CONTRACT_ARTIFACTS_ROOT":"C:/parent/missing/\u0000/contracts"}',
        encoding="utf-8",
    )
    lstat_paths = []

    def forbidden_lstat(path):
        lstat_paths.append(Path(path))
        pytest.fail("含 NUL 的 Paper 根不應進入 lstat")

    monkeypatch.setattr(config_module, "_paper_path_lstat", forbidden_lstat)
    path_type = type(Path())
    original_resolve = path_type.resolve
    resolve_paths = []

    def track_resolve(self, *args, **kwargs):
        candidate = Path(self)
        if "\x00" in str(candidate):
            resolve_paths.append(candidate)
            pytest.fail("含 NUL 的 Paper 根不應進入 resolve")
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(path_type, "resolve", track_resolve)
    original_expanduser = path_type.expanduser
    expanduser_paths = []

    def track_expanduser(self):
        candidate = Path(self)
        if "\x00" in str(candidate):
            expanduser_paths.append(candidate)
            pytest.fail("含 NUL 的 Paper 根不應進入 expanduser")
        return original_expanduser(self)

    monkeypatch.setattr(path_type, "expanduser", track_expanduser)
    original_canonical = bootstrap_module._canonical_path
    canonical_paths = []

    def track_canonical(path):
        candidate = Path(path)
        if "\x00" in str(candidate):
            canonical_paths.append(candidate)
            pytest.fail("含 NUL 的 Paper 根不應進入 bootstrap canonicalizer")
        return original_canonical(path)

    monkeypatch.setattr(bootstrap_module, "_canonical_path", track_canonical)
    base = {
        "DATA_ROOT": str(tmp_path / "market"),
        "OUTPUT_ROOT": str(tmp_path / "output"),
        "LOCALAPPDATA": str(tmp_path / "local"),
        "BALDR_CONFIG": str(portable),
    }

    settings = bootstrap_module.resolve_application_settings(environ=base)

    assert Path(settings.environment["DATA_ROOT"]) == tmp_path / "market"
    assert Path(settings.environment["OUTPUT_ROOT"]) == tmp_path / "output"
    assert "PAPER_CONTRACT_ARTIFACTS_ROOT" not in settings.environment
    assert "NUL" in settings.paper_contract_artifacts_root_error
    assert lstat_paths == []
    assert resolve_paths == []
    assert expanduser_paths == []
    assert canonical_paths == []


def test_backtest_view_paper_picker_clicks_catalogue_then_reads_exact_card_read_only(
    tmp_path, monkeypatch
):
    import time

    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest

    from ui_qt.views.backtest_view import BacktestView

    app = QApplication.instance() or QApplication([])
    (
        _inputs,
        shared_version_service,
        account_service,
        store_paths,
        binding,
        written_result,
    ) = _composed_account(tmp_path, monkeypatch)
    assert account_service.strategy_versions_root == shared_version_service.versions_dir
    assert store_paths.state_db.is_file()
    assert store_paths.cost_ledger_db.is_file()

    def inventory_bytes():
        return {
            path.relative_to(tmp_path).as_posix(): path.read_bytes()
            for path in sorted(tmp_path.rglob("*"))
            if path.is_file()
        }

    def wait_for(predicate, timeout_seconds=10.0):
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return True
            QTest.qWait(10)
            # Windows 的 qWait pump 需讓背景 Python worker 取得 GIL；期限保持10秒。
            time.sleep(0.001)
        app.processEvents()
        return bool(predicate())

    before_inventory = inventory_bytes()
    view = None
    try:
        view = BacktestView(
            backtest_service=None,
            config=None,
            strategy_version_service=shared_version_service,
            paper_checkpoint_account_service=account_service,
            paper_checkpoint_disabled_reason=None,
        )
        view.resize(1440, 1000)
        view.show()
        app.processEvents()
        QTest.qWait(50)

        paper_group = view.result_panel.paper_checkpoint_group
        assert paper_group.isVisible()
        QTest.mouseClick(
            paper_group,
            Qt.MouseButton.LeftButton,
            pos=QPoint(14, 10),
        )
        app.processEvents()
        assert paper_group.isChecked()

        lookup = view.result_panel.paper_checkpoint_lookup
        paper_card = view.result_panel.paper_performance_card
        history_card = view.result_panel.history_performance_card
        history_before = (
            history_card.generation,
            history_card._selected_entry,
            history_card._selection_label.text(),
            history_card._status_label.text(),
            history_card._identity_label.text(),
            history_card._metrics_label.text(),
            history_card._details_label.text(),
        )
        assert lookup.isVisible()
        assert lookup.discover_button.isVisible()
        assert lookup.discover_button.isEnabled()
        lookup.strategy_id.setText(binding.strategy_id)
        lookup.strategy_version_id.setText(binding.strategy_version_id)
        lookup.account_namespace.setText(binding.account_namespace)
        lookup.decision_cutoff.setText(_CUTOFF.isoformat())

        QTest.mouseClick(
            lookup.discover_button,
            Qt.MouseButton.LeftButton,
        )
        assert wait_for(
            lambda: lookup.worker is None and lookup._catalogue is not None
        )
        assert lookup.rows.count() == 1
        item = lookup.rows.item(0)
        row_rect = lookup.rows.visualItemRect(item)
        assert row_rect.isValid()
        QTest.mouseClick(
            lookup.rows.viewport(),
            Qt.MouseButton.LeftButton,
            pos=row_rect.center(),
        )
        app.processEvents()
        assert lookup._selected_row is lookup._catalogue.rows[0]
        assert lookup.read_button.isEnabled()

        actual_cards = []
        exact_reader = lookup.performance_reader
        read_exact = exact_reader.read_paper_checkpoint

        def observe_exact_reader(selector):
            card = read_exact(selector)
            actual_cards.append(card)
            return card

        monkeypatch.setattr(
            exact_reader,
            "read_paper_checkpoint",
            observe_exact_reader,
        )
        assert lookup.read_button.isVisible()
        QTest.mouseClick(
            lookup.read_button,
            Qt.MouseButton.LeftButton,
        )
        assert wait_for(
            lambda: lookup.worker is None and len(actual_cards) == 1
        )

        actual_card = actual_cards[0]
        assert actual_card.read_status is ReadStatus.VERIFIED
        assert actual_card.qualification is QualificationStatus.NOT_QUALIFIED
        assert actual_card.source_availability_status.value == "unverified"
        assert actual_card.period_curve_status == "unavailable"
        assert all(
            metric.value is None
            for _name, metric in actual_card.metrics
        )
        assert actual_card.operation_id == written_result.operation_id
        assert actual_card.snapshot_id == written_result.snapshot_id
        assert lookup._selector is not None
        assert lookup._selector.operation_id == written_result.operation_id
        assert lookup._selector.snapshot_id == written_result.snapshot_id
        assert paper_card._selector == lookup._selector
        assert paper_card.summary_group.isVisible()
        assert paper_card.status_label.text() == (
            "研究帳戶快照已讀回；績效資格尚未合格。"
        )
        assert "來源可得性：未驗證" in paper_card.details_label.text()
        assert "完整期間曲線：不可用" in paper_card.details_label.text()
        assert "績效資格：未合格" in paper_card.details_label.text()
        assert history_card._selected_entry is None
        assert history_before == (
            history_card.generation,
            history_card._selected_entry,
            history_card._selection_label.text(),
            history_card._status_label.text(),
            history_card._identity_label.text(),
            history_card._metrics_label.text(),
            history_card._details_label.text(),
        )
        assert inventory_bytes() == before_inventory
    finally:
        if view is not None:
            view.close()
            paper_lookup = view.result_panel.paper_checkpoint_lookup
            deadline = time.monotonic() + 10.0
            while paper_lookup.worker is not None and time.monotonic() < deadline:
                app.processEvents()
                QTest.qWait(10)
                time.sleep(0.001)
            if view.isVisible():
                view.close()
            app.processEvents()

    assert inventory_bytes() == before_inventory


def test_backtest_view_parent_close_invalidates_pending_paper_read_until_native_finish(
    tmp_path, monkeypatch
):
    import time
    from threading import Event

    from PySide6.QtTest import QTest

    from ui_qt.views.backtest_view import BacktestView

    app = QApplication.instance() or QApplication([])
    (
        _inputs,
        shared_version_service,
        account_service,
        store_paths,
        binding,
        written_result,
    ) = _composed_account(tmp_path, monkeypatch)
    assert account_service.strategy_versions_root == shared_version_service.versions_dir

    def inventory_bytes():
        return {
            path.relative_to(tmp_path).as_posix(): path.read_bytes()
            for path in sorted(tmp_path.rglob("*"))
            if path.is_file()
        }

    def wait_for(predicate, timeout_seconds=10.0):
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return True
            QTest.qWait(10)
            # 保留原10秒期限，僅讓 Python worker 在 Qt pump 間合作式執行。
            time.sleep(0.001)
        app.processEvents()
        return bool(predicate())

    before_inventory = inventory_bytes()
    read_entered = Event()
    release_read = Event()
    actual_cards = []
    view = None
    lookup = None
    worker_finished = True
    try:
        view = BacktestView(
            backtest_service=None,
            config=None,
            strategy_version_service=shared_version_service,
            paper_checkpoint_account_service=account_service,
            paper_checkpoint_disabled_reason=None,
        )
        view.resize(1440, 1000)
        view.show()
        app.processEvents()
        QTest.qWait(50)

        paper_group = view.result_panel.paper_checkpoint_group
        assert paper_group.isVisible()
        from PySide6.QtCore import QPoint

        QTest.mouseClick(
            paper_group,
            Qt.MouseButton.LeftButton,
            pos=QPoint(14, 10),
        )
        app.processEvents()
        assert paper_group.isChecked()

        lookup = view.result_panel.paper_checkpoint_lookup
        paper_card = view.result_panel.paper_performance_card
        history_card = view.result_panel.history_performance_card
        history_before = (
            history_card._selected_entry,
            history_card._selection_label.text(),
            history_card._status_label.text(),
            history_card._identity_label.text(),
            history_card._metrics_label.text(),
            history_card._details_label.text(),
        )
        lookup.strategy_id.setText(binding.strategy_id)
        lookup.strategy_version_id.setText(binding.strategy_version_id)
        lookup.account_namespace.setText(binding.account_namespace)
        lookup.decision_cutoff.setText(_CUTOFF.isoformat())

        QTest.mouseClick(
            lookup.discover_button,
            Qt.MouseButton.LeftButton,
        )
        assert wait_for(
            lambda: lookup.worker is None and lookup._catalogue is not None
        )
        assert lookup.rows.count() == 1
        item = lookup.rows.item(0)
        row_rect = lookup.rows.visualItemRect(item)
        assert row_rect.isValid()
        QTest.mouseClick(
            lookup.rows.viewport(),
            Qt.MouseButton.LeftButton,
            pos=row_rect.center(),
        )
        app.processEvents()
        assert lookup.read_button.isEnabled()

        exact_reader = lookup.performance_reader
        read_exact = exact_reader.read_paper_checkpoint

        def gated_exact_reader(selector):
            read_entered.set()
            if not release_read.wait(5.0):
                raise TimeoutError("exact Paper read gate was not released")
            card = read_exact(selector)
            actual_cards.append(card)
            return card

        monkeypatch.setattr(
            exact_reader,
            "read_paper_checkpoint",
            gated_exact_reader,
        )
        QTest.mouseClick(
            lookup.read_button,
            Qt.MouseButton.LeftButton,
        )
        assert wait_for(read_entered.is_set)
        worker = lookup.worker
        assert worker is not None
        assert worker.isRunning()

        close_event = QCloseEvent()
        view.closeEvent(close_event)
        assert close_event.isAccepted() is False
        assert lookup._closed is True
        assert lookup.worker is worker
        assert worker.isRunning()
        assert paper_card._selector is None
        assert paper_card.summary_group.isVisible() is False
        assert history_card._selected_entry is None
        assert history_before == (
            history_card._selected_entry,
            history_card._selection_label.text(),
            history_card._status_label.text(),
            history_card._identity_label.text(),
            history_card._metrics_label.text(),
            history_card._details_label.text(),
        )
        assert inventory_bytes() == before_inventory
    finally:
        release_read.set()
        if view is not None and lookup is not None and lookup.worker is not None:
            worker_finished = wait_for(
                lambda: lookup.worker is None, timeout_seconds=10.0
            )
        if view is not None:
            view.close()
            app.processEvents()

    assert worker_finished
    assert len(actual_cards) == 1
    actual_card = actual_cards[0]
    assert actual_card.read_status is ReadStatus.VERIFIED
    assert actual_card.qualification is QualificationStatus.NOT_QUALIFIED
    assert actual_card.operation_id == written_result.operation_id
    assert actual_card.snapshot_id == written_result.snapshot_id
    assert lookup is not None
    assert lookup._closed is True
    assert lookup.worker is None
    assert paper_card._selector is None
    assert paper_card.summary_group.isVisible() is False
    assert paper_card.status_label.text() == "尚未選取研究帳戶快照。"
    assert history_card._selected_entry is None
    assert inventory_bytes() == before_inventory
