from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from collections.abc import Mapping
from dataclasses import replace
from tempfile import TemporaryDirectory
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from app_module.recommendation.personal_use_policy import (
    PersonalCalibrationCandidateV1,
    RecommendationPersonalUseSelectionV1,
    load_personal_use_policy,
    save_personal_use_policy,
)
from test_personal_candidate_inventory import _source_bound_candidate_package
from ui_qt.main import _resolve_personal_policy_config_path
from ui_qt.views.recommendation_view import (
    RecommendationView,
    _load_personal_policy_history,
)


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json(item) for item in value]
    return value


def _signed_company_source_snapshot(snapshot: dict[str, object]) -> dict[str, object]:
    unsigned = _plain_json(snapshot)
    assert isinstance(unsigned, dict)
    unsigned.pop("snapshot_sha256", None)
    canonical = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    unsigned["snapshot_sha256"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    return unsigned


@pytest.fixture(scope="module")
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def workspace_personal_capture_root():
    """在 repo 內建立可通過 SQLite no-follow 路徑錨定的隔離根目錄。"""

    with TemporaryDirectory(
        prefix=".tmp_ui_personal_capture_",
        dir=Path.cwd(),
    ) as temporary_root:
        yield Path(temporary_root).resolve()


def _make_view(
    *,
    personal_policy_path: Path | None = None,
    watchlist_service=None,
    recommendation_service=None,
) -> RecommendationView:
    return RecommendationView(
        recommendation_service=(
            recommendation_service
            if recommendation_service is not None
            else MagicMock()
        ),
        regime_service=SimpleNamespace(
            detect_regime=lambda: SimpleNamespace(regime="Unknown"),
            get_strategy_config=lambda _regime: {},
        ),
        watchlist_service=watchlist_service,
        personal_policy_path=personal_policy_path,
    )


def _real_service_for_source_database(
    source_database: Path,
    *,
    data_root: Path,
    output_root: Path,
):
    from tests.recommendation_test_support import build_recommendation_test_service

    config = SimpleNamespace(
        db_file=source_database,
        data_root=data_root,
        output_root=output_root,
        use_sqlite=True,
        default_start_date="2025-01-01",
        pit_market_scope=None,
    )
    config.resolve_output_path = lambda subfolder: output_root / subfolder
    service = build_recommendation_test_service(
        config,
        industry_mapper=MagicMock(),
        regime_detector=MagicMock(),
    )
    return config, service


class _IsolatedRecommendationConfig:
    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root

    def resolve_output_path(self, subfolder: str) -> Path:
        path = self.output_root / subfolder
        path.mkdir(parents=True, exist_ok=True)
        return path


def _wait_for_saved_result_load(
    view: RecommendationView,
    qt_app: QApplication,
) -> None:
    worker = view._saved_result_load_worker
    assert worker is not None
    assert worker.wait(10_000)
    qt_app.processEvents()
    qt_app.processEvents()


def test_explicit_policy_config_path_must_be_absolute(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="絕對路徑"):
        _resolve_personal_policy_config_path(Path("relative") / "policy.json")

    absolute_path = tmp_path / "personal" / "policy.json"
    assert _resolve_personal_policy_config_path(absolute_path) == absolute_path.resolve()


def test_shared_config_policy_path_is_used_without_creating_policy(tmp_path: Path) -> None:
    configured = tmp_path / "daily-and-ui" / "policy.json"
    assert _resolve_personal_policy_config_path(None, configured_path=configured) == configured.resolve()
    assert not configured.parent.exists()


def test_explicit_policy_path_keeps_precedence_over_daily_config(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit.json"
    configured = tmp_path / "daily.json"
    assert _resolve_personal_policy_config_path(explicit, configured_path=configured) == explicit.resolve()
    assert not explicit.exists() and not configured.exists()


def test_relative_shared_policy_config_is_rejected() -> None:
    with pytest.raises(ValueError, match="絕對路徑"):
        _resolve_personal_policy_config_path(None, configured_path=Path("relative.json"))


def test_relative_config_policy_rejected_before_data_directory_io(tmp_path: Path, monkeypatch) -> None:
    from data_module.config import TWStockConfig

    monkeypatch.setattr(TWStockConfig, "_resolve_paths", lambda self: pytest.fail("invalid policy before data IO"))
    with pytest.raises(ValueError, match="絕對路徑"):
        TWStockConfig(data_root=tmp_path / "market", personal_model_policy_path=Path("relative.json"))


def test_shared_policy_environment_reaches_config_without_creating_policy(tmp_path: Path, monkeypatch) -> None:
    from data_module.config import TWStockConfig

    path = tmp_path / "shared.json"
    monkeypatch.setenv("PERSONAL_MODEL_POLICY_PATH", str(path))
    # 核原 dataclass 環境 factory，不初始化資料／日誌服務。
    factory = TWStockConfig.__dataclass_fields__["personal_model_policy_path"].default_factory
    assert factory() == path
    assert not path.exists()


def test_corrupt_policy_requires_explicit_one_shot_rule_fallback(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    policy_path = tmp_path / "personal_use_policy.json"
    original_bytes = b"{not valid json\n"
    policy_path.write_bytes(original_bytes)

    view = _make_view(personal_policy_path=policy_path)
    try:
        assert view._personal_policy_load_error
        assert view.personal_policy_one_shot_button.isHidden() is False
        assert view.personal_policy_confirm_button.isEnabled() is False

        with pytest.raises(ValueError, match="明確確認"):
            view._personal_policy_for_invocation()

        view._confirm_rule_only_for_next_run()
        policy = view._personal_policy_for_invocation()
        assert policy.revision == 0
        assert policy.mode == "rule_only"
        assert policy.storage_path is None
        assert view.personal_policy_one_shot_button.isEnabled() is False
        assert policy_path.read_bytes() == original_bytes

        view._complete_personal_policy_one_shot()
        assert view.personal_policy_one_shot_button.isEnabled() is True
        with pytest.raises(ValueError, match="明確確認"):
            view._personal_policy_for_invocation()
        assert policy_path.read_bytes() == original_bytes
    finally:
        view.close()


def test_candidate_inventory_ui_uses_explicit_roots_and_does_not_create_them(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "isolated-data"
    output_root = tmp_path / "isolated-output"
    view = _make_view()
    view.config = SimpleNamespace(data_root=data_root, output_root=output_root)
    try:
        view._load_personal_candidate_inventory()
        worker = view._personal_candidate_worker
        assert worker is not None
        assert worker.wait(10_000)
        qt_app.processEvents()

        snapshot = view._personal_candidate_snapshot
        assert snapshot is not None
        assert snapshot.status == "empty"
        assert snapshot.entries == ()
        assert "完整 lineage" in snapshot.next_step
        assert not data_root.exists()
        assert not output_root.exists()
        assert view.personal_candidate_combo.count() == 0
        assert "沒有可列出的候選" in view.personal_candidate_status_label.text()
    finally:
        view.close()


def test_candidate_inventory_uses_learning_shadow_resolver_not_product_output(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "FA_Data"
    product_output_root = data_root / "output"
    learning_shadow_root = tmp_path / "FA_Data_Shadow"
    learning_root = learning_shadow_root / "recommendation_learning"
    candidate_root = (
        learning_root
        / "runs"
        / "2026-09-26"
        / "candidates"
        / "legacy-ui-inventory-fixture"
    )
    candidate_root.mkdir(parents=True)
    (candidate_root / "candidate.json").write_text(
        '{"schema_version":"recommendation-calibration-candidate.v1",'
        '"candidate_id":"legacy-ui-inventory-fixture"}',
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "RECOMMENDATION_LEARNING_OUTPUT_ROOT", str(learning_shadow_root)
    )
    view = _make_view()
    view.config = SimpleNamespace(
        data_root=data_root,
        output_root=product_output_root,
    )
    try:
        assert view._personal_candidate_inventory_roots() == {
            "data_root": str(data_root),
            "explicit_output_root": None,
        }
        view._load_personal_candidate_inventory()
        worker = view._personal_candidate_worker
        assert worker is not None
        assert worker.wait(10_000)
        qt_app.processEvents()

        snapshot = view._personal_candidate_snapshot
        assert snapshot is not None
        assert snapshot.learning_root == str(learning_root.resolve())
        assert snapshot.candidates_scanned == 1
        assert len(snapshot.entries) == 1
        assert snapshot.entries[0].candidate_id == "legacy-ui-inventory-fixture"
        assert snapshot.entries[0].status == "legacy_unproven"
        assert not product_output_root.exists()
        assert view.personal_candidate_combo.currentIndex() == -1

        # Explicitly choosing the only row must trigger the selected-candidate
        # inspection path instead of being lost to QComboBox's auto-selection.
        view.personal_candidate_combo.setCurrentIndex(0)
        inspect_worker = view._personal_candidate_worker
        assert inspect_worker is not None
        assert inspect_worker.wait(10_000)
        qt_app.processEvents()
        assert view._personal_candidate_entry is not None
        assert view._personal_candidate_entry.status == "legacy_unproven"
        assert view._personal_candidate is None
        assert "legacy_unproven" in view.personal_candidate_status_label.text()
    finally:
        view.close()


def _save_rule_revision(path: Path, expected_revision: int):
    return save_personal_use_policy(
        path,
        RecommendationPersonalUseSelectionV1(
            scope_id="technical_analysis_local",
            mode="rule_only",
        ),
        expected_revision=expected_revision,
    )


def _save_calibrated_revision(
    path: Path,
    expected_revision: int,
    tmp_path: Path,
):
    candidate = PersonalCalibrationCandidateV1(
        candidate_id="personal-ui-calibration-fixture",
        candidate_root=str((tmp_path / "candidate").resolve()),
        candidate_json_sha256="sha256:" + "1" * 64,
        candidate_manifest_hash="sha256:" + "2" * 64,
        candidate_artifact_hash="sha256:" + "3" * 64,
        candidate_freeze_hash="sha256:" + "4" * 64,
        dataset_hash="sha256:" + "5" * 64,
    )
    return save_personal_use_policy(
        path,
        RecommendationPersonalUseSelectionV1(
            scope_id="technical_analysis_local",
            mode="personal_calibrated_probability",
            candidate=candidate,
        ),
        expected_revision=expected_revision,
    )


def _wait_for_policy_history(view: RecommendationView, qt_app: QApplication) -> None:
    worker = view._personal_policy_history_worker
    if worker is not None:
        assert worker.wait(10_000)
    qt_app.processEvents()


def test_policy_history_reads_only_valid_bounded_archive_entries(
    tmp_path: Path,
) -> None:
    policy_path = tmp_path / "personal_use_policy.json"
    _save_rule_revision(policy_path, 0)
    current = _save_rule_revision(policy_path, 1)
    archived_path = next((tmp_path / "personal_use_policy.json.revisions").iterdir())
    archived_path.write_bytes(b"{corrupt archive\n")

    result = _load_personal_policy_history(
        policy_path,
        current_revision=current.revision,
    )

    assert result["policies"] == ()
    assert any("無法驗證" in issue for issue in result["issues"])
    assert result["scanned_entries"] == 1
    assert not result["truncated"]


def test_saved_calibrated_mode_can_be_explicitly_disabled_to_rule_only(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    policy_path = tmp_path / "personal_use_policy.json"
    candidate = PersonalCalibrationCandidateV1(
        candidate_id="candidate-1",
        candidate_root=str((tmp_path / "candidate").resolve()),
        candidate_json_sha256="sha256:" + "a" * 64,
        candidate_manifest_hash="sha256:" + "b" * 64,
        candidate_artifact_hash="sha256:" + "c" * 64,
        candidate_freeze_hash="sha256:" + "d" * 64,
        dataset_hash="sha256:" + "e" * 64,
    )
    save_personal_use_policy(
        policy_path,
        RecommendationPersonalUseSelectionV1(
            scope_id="technical_analysis_local",
            mode="personal_calibrated_probability",
            candidate=candidate,
        ),
        expected_revision=0,
    )
    view = _make_view(personal_policy_path=policy_path)
    try:
        assert view.personal_policy_mode_combo.currentData() == (
            "personal_calibrated_probability"
        )
        view.personal_policy_mode_combo.setCurrentIndex(
            view.personal_policy_mode_combo.findData("rule_only")
        )
        assert view.personal_policy_mode_combo.currentData() == "rule_only"
        assert view.personal_policy_confirm_button.text() == "停用校準並保存規則模式"
        assert view.personal_policy_confirm_button.isEnabled()

        view._confirm_personal_use_policy()

        saved = load_personal_use_policy(policy_path)
        assert saved.revision == 2
        assert saved.mode == "rule_only"
        assert saved.candidate is None
        assert saved.rollback_of_revision is None
        assert "規則模式" in view.personal_policy_status_label.text()
    finally:
        view.close()


def test_policy_history_rollback_creates_new_revision_and_preserves_history(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path = tmp_path / "personal_use_policy.json"
    first = _save_rule_revision(policy_path, 0)
    _save_rule_revision(policy_path, first.revision)
    current = _save_rule_revision(policy_path, 2)
    view = _make_view(personal_policy_path=policy_path)
    try:
        _wait_for_policy_history(view, qt_app)
        assert view.personal_policy_history_combo.count() == 2
        assert view.personal_policy_history_combo.itemData(0).revision == 2
        target = view.personal_policy_history_combo.itemData(1)
        assert target.revision == 1

        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
        )
        view.personal_policy_history_combo.setCurrentIndex(1)
        view._rollback_to_selected_personal_policy()
        _wait_for_policy_history(view, qt_app)

        restored = load_personal_use_policy(policy_path)
        assert restored.revision == current.revision + 1
        assert restored.mode == first.mode
        assert restored.rollback_of_revision == first.revision
        assert restored.rollback_of_policy_sha256 == first.policy_sha256
        assert view._personal_use_policy.policy_sha256 == restored.policy_sha256
        assert "保存為新版本" in view.personal_policy_status_label.text()
        assert len(list((tmp_path / "personal_use_policy.json.revisions").iterdir())) == 3
    finally:
        view.close()


def test_policy_history_rollback_detects_cas_conflict_and_reloads_current(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path = tmp_path / "personal_use_policy.json"
    first = _save_rule_revision(policy_path, 0)
    current = _save_rule_revision(policy_path, 1)
    view = _make_view(personal_policy_path=policy_path)
    messages: list[str] = []
    try:
        _wait_for_policy_history(view, qt_app)
        assert view.personal_policy_history_combo.count() == 1
        view.personal_policy_history_combo.setCurrentIndex(0)
        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
        )
        monkeypatch.setattr(
            QMessageBox,
            "information",
            lambda _parent, _title, message: messages.append(message),
        )
        original_rollback = __import__(
            "app_module.recommendation.personal_use_policy",
            fromlist=["rollback_personal_use_policy"],
        ).rollback_personal_use_policy

        def concurrent_update_then_rollback(path, **kwargs):
            _save_rule_revision(path, current.revision)
            return original_rollback(path, **kwargs)

        monkeypatch.setattr(
            "app_module.recommendation.personal_use_policy.rollback_personal_use_policy",
            concurrent_update_then_rollback,
        )
        view._rollback_to_selected_personal_policy()
        _wait_for_policy_history(view, qt_app)

        latest = load_personal_use_policy(policy_path)
        assert latest.revision == current.revision + 1
        assert latest.rollback_of_revision is None
        assert view._personal_use_policy.policy_sha256 == latest.policy_sha256
        assert messages and "沒有套用舊選擇" in messages[-1]
        assert first.revision == 1
    finally:
        view.close()


@pytest.mark.parametrize(
    ("first_mode", "current_mode"),
    (
        ("personal_calibrated_probability", "rule_only"),
        ("rule_only", "personal_calibrated_probability"),
    ),
)
def test_policy_history_rollback_selects_saved_mode_for_next_invocation(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    first_mode: str,
    current_mode: str,
) -> None:
    policy_path = tmp_path / "personal_use_policy.json"
    first = (
        _save_calibrated_revision(policy_path, 0, tmp_path)
        if first_mode == "personal_calibrated_probability"
        else _save_rule_revision(policy_path, 0)
    )
    current = (
        _save_calibrated_revision(policy_path, 1, tmp_path)
        if current_mode == "personal_calibrated_probability"
        else _save_rule_revision(policy_path, 1)
    )
    view = _make_view(personal_policy_path=policy_path)
    try:
        _wait_for_policy_history(view, qt_app)
        target_index = next(
            index
            for index in range(view.personal_policy_history_combo.count())
            if view.personal_policy_history_combo.itemData(index).revision
            == first.revision
        )
        view.personal_policy_history_combo.setCurrentIndex(target_index)
        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
        )
        view._rollback_to_selected_personal_policy()
        _wait_for_policy_history(view, qt_app)

        restored = load_personal_use_policy(policy_path)
        assert restored.revision == current.revision + 1
        assert restored.mode == first_mode
        assert view.personal_policy_mode_combo.currentData() == first_mode
        if first_mode == "personal_calibrated_probability":
            with pytest.raises(ValueError, match="runtime DB 不一致或未重新驗證的 V2"):
                view._personal_policy_for_invocation()
        else:
            invocation_policy = view._personal_policy_for_invocation()
            assert invocation_policy.revision == restored.revision
            assert invocation_policy.mode == first_mode
    finally:
        view.close()


def _wait_for_personal_source_check(
    view: RecommendationView,
    qt_app: QApplication,
) -> None:
    worker = view._personal_candidate_worker
    assert worker is not None
    assert worker.wait(30_000)
    qt_app.processEvents()
    qt_app.processEvents()


def _select_personal_candidate(view: RecommendationView, candidate_root: Path) -> None:
    combo = view.personal_candidate_combo
    combo.blockSignals(True)
    combo.clear()
    combo.addItem(candidate_root.name, str(candidate_root.resolve()))
    combo.setCurrentIndex(0)
    combo.blockSignals(False)


def test_v2_source_trust_requires_explicit_preview_and_fresh_readback(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate_root, _candidate_bytes, data_root, _replay_path = (
        _source_bound_candidate_package(tmp_path)
    )
    source_database = data_root / "sqlite" / "twstock.db"
    learning_output = tmp_path / "shadow-output"
    monkeypatch.setenv("RECOMMENDATION_LEARNING_OUTPUT_ROOT", str(learning_output))
    policy_path = tmp_path / "personal" / "recommendation-policy.json"
    policy_path.parent.mkdir()
    config, service = _real_service_for_source_database(
        source_database.resolve(),
        data_root=data_root,
        output_root=tmp_path / "service-output",
    )

    def configure(view: RecommendationView) -> None:
        view.config = config
        _select_personal_candidate(view, candidate_root)

    view = _make_view(
        personal_policy_path=policy_path,
        recommendation_service=service,
    )
    configure(view)
    try:
        assert view.personal_source_database_input.text() == ""
        calibrated_index = view.personal_policy_mode_combo.findData(
            "personal_calibrated_probability"
        )
        view.personal_policy_mode_combo.setCurrentIndex(calibrated_index)
        assert not view.personal_policy_confirm_button.isEnabled()

        # DATA_ROOT/設定路徑都不能代替使用者明示來源，也不會建立政策檔。
        view._inspect_personal_source_time_binding()
        assert "明確輸入或選擇" in view.personal_source_time_status_label.text()
        assert not policy_path.exists()

        view.personal_source_database_input.setText(str(source_database.resolve()))
        service.model_feature_provider = SimpleNamespace(
            config=SimpleNamespace(db_file=source_database.resolve())
        )
        view._inspect_personal_source_time_binding()
        assert view._personal_candidate_worker is None
        assert "runtime DB 不一致" in view.personal_source_time_status_label.text()
        del service.model_feature_provider

        view._inspect_personal_source_time_binding()
        _wait_for_personal_source_check(view, qt_app)
        proposal = view._personal_source_time_proposal
        assert proposal is not None
        assert proposal.source_database_path == str(source_database.resolve())
        assert proposal.candidate.candidate_root == str(candidate_root.resolve())
        assert proposal.research_only is True
        assert proposal.official_historical_pit_verified is False
        assert not view.personal_source_time_trust_checkbox.isChecked()
        assert not view.personal_policy_confirm_button.isEnabled()
        assert not policy_path.exists()
        preview_text = view.personal_source_time_status_label.text()
        assert str(source_database.resolve()) in preview_text
        assert proposal.source_slice_sha256 in preview_text
        assert "decision_dates=" in preview_text
        assert "symbols=1101,2330" in preview_text
        assert "official_historical_pit_verified=False" in preview_text

        view.personal_source_time_trust_checkbox.setChecked(True)
        assert view.personal_policy_confirm_button.isEnabled()
        view._confirm_personal_use_policy()

        from app_module.recommendation.personal_use_policy import (
            RecommendationPersonalUsePolicyV2,
            load_personal_use_policy_snapshot,
        )

        saved = load_personal_use_policy_snapshot(policy_path)
        assert isinstance(saved, RecommendationPersonalUsePolicyV2)
        assert saved.mode == "personal_calibrated_probability"
        assert saved.candidate == proposal.candidate
        assert saved.source_time_trust is not None
        assert saved.source_time_trust.source_database_path == str(
            source_database.resolve()
        )
        assert saved.source_time_trust.confirmed_at == saved.confirmed_at
        assert saved.source_time_trust.research_only is True
        assert saved.source_time_trust.official_historical_pit_verified is False
        assert view._personal_source_time_verified_policy_identity is None
        _wait_for_personal_source_check(view, qt_app)
        verified = view._personal_source_time_verified_entry
        assert verified is not None
        assert verified.status == "metadata_pinned_pending_runtime_validation"
        assert verified.source_time_basis == "user_declared_source_time"
        assert verified.research_only is True
        assert verified.official_historical_pit_verified is False
        invocation_policy = view._personal_policy_for_invocation()
        assert invocation_policy.policy_sha256 == saved.policy_sha256
        assert view._personal_source_matches_runtime(
            source_database.resolve(),
            saved.source_time_trust.file_identity,
        )
        assert not view._personal_source_matches_runtime(
            source_database.resolve(),
            {
                "device": saved.source_time_trust.file_identity.device + 1,
                "inode": saved.source_time_trust.file_identity.inode + 1,
            },
        )
        assert not view._personal_source_matches_runtime(
            source_database.resolve(),
            {"device": 0, "inode": 0},
        )
        runtime_service = service.with_personal_use_policy(invocation_policy)
        assert runtime_service.config is config
        assert view._personal_policy_source_is_verified(
            invocation_policy,
            service_override=runtime_service,
        )
        from ui_qt.workers.task_worker import ProgressTaskWorker

        alternate_service_db = tmp_path / "changed-service-runtime.db"
        alternate_service_db.write_bytes(b"isolated test placeholder")
        started_workers: list[object] = []
        invocation_errors: list[str] = []
        real_worker_start = ProgressTaskWorker.start
        monkeypatch.setattr(
            ProgressTaskWorker,
            "start",
            lambda worker: started_workers.append(worker),
        )
        monkeypatch.setattr(
            QMessageBox,
            "warning",
            lambda _parent, _title, message, **_kwargs: invocation_errors.append(message),
        )
        original_service_config = service.config
        service.config = SimpleNamespace(db_file=alternate_service_db)
        view._execute_recommendation()
        assert started_workers == []
        assert view.worker is None
        assert invocation_errors and "未啟動" in invocation_errors[-1]
        monkeypatch.setattr(ProgressTaskWorker, "start", real_worker_start)
        service.config = original_service_config

        # Model a DB switch after policy verification and invocation-service
        # creation but immediately before the worker launch gate.
        source_verifier = view._personal_policy_source_is_verified
        verification_calls = 0

        def switch_runtime_db_before_worker(
            policy: object, *, service_override: object | None = None
        ) -> bool:
            nonlocal verification_calls
            verification_calls += 1
            if verification_calls == 3:
                assert service_override is not None
                service_override.config = SimpleNamespace(db_file=alternate_service_db)
            return source_verifier(policy, service_override=service_override)

        monkeypatch.setattr(
            view,
            "_personal_policy_source_is_verified",
            switch_runtime_db_before_worker,
        )
        view._execute_recommendation()
        assert verification_calls == 3
        assert started_workers == []
        assert view.worker is None
        assert invocation_errors and "未啟動" in invocation_errors[-1]

        from app_module.recommendation.composition import (
            build_recommendation_composition,
        )
        from ui_qt.views.recommendation.execution_coordinator import (
            RecommendationExecutionRequest,
        )

        request = RecommendationExecutionRequest(view._collect_config())
        assert request.validation_error() is None
        execution = request.execute(runtime_service, detailed_progress=True)
        assert execution.status.value == "completed"
        composition = build_recommendation_composition(config)
        save_receipt = composition.save_service.save_execution(
            execution,
            label="隔離 runtime DB 綁定正例",
            notes="確認 UI source binding 與真 RecommendationService DB 一致",
        )
        assert save_receipt.result_id == execution.result_id
        readback = build_recommendation_composition(config).queries.get(
            execution.result_id
        )
        assert readback is not None
        assert readback.execution == execution
        policy_event = next(
            event
            for event in readback.execution.events
            if event.event_type == "personal_use_policy_snapshot"
        )
        assert policy_event.details["policy_snapshot"]["policy_sha256"] == (
            saved.policy_sha256
        )

    finally:
        view.close()

    # A restarted view shows the saved DB for review but does not reuse the old
    # in-memory verification; it must re-run the source check before invocation.
    restarted = _make_view(
        personal_policy_path=policy_path,
        recommendation_service=service,
    )
    configure(restarted)
    try:
        assert restarted.personal_source_database_input.text() == str(
            source_database.resolve()
        )
        with pytest.raises(ValueError, match="未重新驗證的 V2"):
            restarted._personal_policy_for_invocation()

        restarted._inspect_personal_source_time_binding()
        _wait_for_personal_source_check(restarted, qt_app)
        assert (
            restarted._personal_source_time_verified_entry.status
            == "metadata_pinned_pending_runtime_validation"
        ), restarted.personal_source_time_status_label.text()
        assert restarted._personal_policy_for_invocation().policy_sha256 == saved.policy_sha256

        # A same-path source edit invalidates the saved slice; the UI must not
        # turn the old user confirmation into a fresh verified candidate.
        with sqlite3.connect(source_database) as connection:
            connection.execute(
                'UPDATE technical_indicators SET RSI = ? WHERE "日期" = ? AND "證券代號" = ?',
                ("99", "20250401", "1101"),
            )
            assert connection.total_changes == 1
        restarted._inspect_personal_source_time_binding()
        _wait_for_personal_source_check(restarted, qt_app)
        assert restarted._personal_candidate is None
        assert restarted._personal_source_time_verified_policy_identity is None
        with pytest.raises(ValueError, match="未重新驗證的 V2"):
            restarted._personal_policy_for_invocation()

        restarted.personal_policy_mode_combo.setCurrentIndex(
            restarted.personal_policy_mode_combo.findData("rule_only")
        )
        assert restarted.personal_policy_confirm_button.isEnabled()
        restarted._confirm_personal_use_policy()
        cleared = load_personal_use_policy_snapshot(policy_path)
        assert isinstance(cleared, RecommendationPersonalUsePolicyV2)
        assert cleared.mode == "rule_only"
        assert cleared.candidate is None
        assert cleared.source_time_trust is None
        assert restarted.personal_source_database_input.text() == ""
    finally:
        restarted.close()


def test_v2_source_trust_for_database_b_cannot_start_recommendation_on_database_a(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil

    from app_module.recommendation.personal_candidate_inventory import (
        inspect_personal_source_time_binding,
    )
    from app_module.recommendation.personal_use_policy import (
        RecommendationPersonalUseSelectionV2,
        save_personal_use_policy_v2,
    )
    from ui_qt.workers.task_worker import ProgressTaskWorker

    candidate_root, _candidate_bytes, data_root, _replay_path = (
        _source_bound_candidate_package(tmp_path)
    )
    source_database_b = (data_root / "sqlite" / "twstock.db").resolve()
    database_a = (tmp_path / "runtime-a" / "twstock.db").resolve()
    database_a.parent.mkdir()
    shutil.copyfile(source_database_b, database_a)
    assert database_a.read_bytes() == source_database_b.read_bytes()
    assert database_a.resolve() != source_database_b.resolve()

    learning_output = tmp_path / "shadow-output"
    monkeypatch.setenv("RECOMMENDATION_LEARNING_OUTPUT_ROOT", str(learning_output))
    proposal = inspect_personal_source_time_binding(
        candidate_root=candidate_root,
        source_database_path=source_database_b,
        explicit_output_root=learning_output,
        data_root=data_root,
    )
    policy_path = tmp_path / "personal" / "recommendation-policy.json"
    policy_path.parent.mkdir()
    save_personal_use_policy_v2(
        policy_path,
        RecommendationPersonalUseSelectionV2(
            scope_id="runtime-source-a-b-test",
            mode="personal_calibrated_probability",
            source_time_binding=proposal,
        ),
        expected_revision=0,
    )

    config, service = _real_service_for_source_database(
        database_a,
        data_root=data_root,
        output_root=tmp_path / "service-output",
    )
    view = _make_view(
        personal_policy_path=policy_path,
        recommendation_service=service,
    )
    started_workers: list[object] = []
    messages: list[str] = []
    monkeypatch.setattr(
        ProgressTaskWorker,
        "start",
        lambda worker: started_workers.append(worker),
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message, **_kwargs: messages.append(message),
    )
    try:
        view.config = config
        _select_personal_candidate(view, candidate_root)
        view.personal_source_database_input.setText(str(source_database_b))
        assert not view._personal_source_matches_runtime(
            source_database_b,
            proposal.file_identity,
        )

        view._inspect_personal_source_time_binding()
        assert view._personal_candidate_worker is None
        assert "runtime DB 不一致" in view.personal_source_time_status_label.text()

        view._collect_config = lambda: {
            "patterns": {"selected": ["baseline-pattern"]},
            "signals": {"technical_indicators": ["RSI"]},
        }
        assert (
            view.personal_policy_mode_combo.currentData()
            == "personal_calibrated_probability"
        )
        view._execute_recommendation()
        assert started_workers == []
        assert view.worker is None
        assert messages and "未啟動" in messages[-1]
    finally:
        view.close()


def test_recommendation_view_close_waits_for_personal_workers(
    qt_app: QApplication,
) -> None:
    class RunningWorker:
        def __init__(self) -> None:
            self.running = True
            self.cancelled = False

        def isRunning(self) -> bool:  # noqa: N802
            return self.running

        def cancel(self, *, cooperative: bool, wait: bool) -> None:
            assert cooperative is True
            assert wait is False
            self.cancelled = True

    view = _make_view()
    candidate_worker = RunningWorker()
    history_worker = RunningWorker()
    view.worker = None
    view._report_export_workers = []
    view._personal_candidate_worker = candidate_worker
    view._personal_policy_history_worker = history_worker
    event = QCloseEvent()
    try:
        view.closeEvent(event)
        assert not event.isAccepted()
        assert candidate_worker.cancelled is True
        assert history_worker.cancelled is True
        assert candidate_worker.running is True
        assert history_worker.running is True
    finally:
        candidate_worker.running = False
        history_worker.running = False
        view.close()


def test_company_source_display_uses_only_the_matching_sealed_event(
    qt_app: QApplication,
) -> None:
    view = _make_view()
    try:
        snapshot = _signed_company_source_snapshot({
            "schema_version": "recommendation-company-registry-source-snapshot.v1",
            "result_id": "result-1",
            "data_as_of_date": "2026-09-25",
            "scope": "current_classification_only",
            "pit_eligible": False,
            "company_registry_source_status": "captured",
            "industry_index_source_status": "unknown",
            "company_registry_source_contract_sha256": "sha256:" + "a" * 64,
            "company_registry_source_contract": {
                "generated_at": "2026-09-26T00:00:00Z",
                "artifact": {"sha256": "sha256:" + "b" * 64},
                "sources": [
                    {"market": "twse", "status": "captured", "available_at": "2026-09-25T08:00:00Z"}
                ],
            },
            "usage": ["current_industry_index_performance_for_reason"],
            "warnings": ["industry_index_source_contract_unavailable_for_current_use"],
        })
        event = SimpleNamespace(
            event_type="company_registry_source_snapshot",
            details={
                "schema_version": "recommendation-company-registry-source-snapshot-event.v1",
                "result_id": "result-1",
                "snapshot": snapshot,
            },
        )
        execution = SimpleNamespace(result_id="result-1", events=(event,))
        view._update_company_source_snapshot_display(execution)
        text = view.company_source_snapshot_label.text()
        assert "當時分析日期 2026-09-25（v1；不代表行情資料日）" in text
        assert "current_classification_only" in text
        assert "PIT eligible=false" in text
        assert "產業指數來源未知" in text
        assert "下一步" in text
        assert "sha256:" + "a" * 64 in text

        mismatched = SimpleNamespace(result_id="another-result", events=(event,))
        view._update_company_source_snapshot_display(mismatched)
        assert "不會改讀目前資料補值" in view.company_source_snapshot_label.text()

        no_event = SimpleNamespace(result_id="legacy-result", events=())
        view._update_company_source_snapshot_display(no_event)
        assert "不會以目前名冊或產業資料補填" in view.company_source_snapshot_label.text()
    finally:
        view.close()


def test_stock_research_context_uses_sealed_v2_market_date_separately_from_universe(
    qt_app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import date, datetime, timezone

    decision_at = datetime(2026, 9, 27, 21, 51, 46, 559791, tzinfo=timezone.utc)
    result_id = "rec_21ab7be231bc4969b3f99d0043a242e0"
    fingerprint = "a" * 64
    source_event = SimpleNamespace(
        event_type="company_registry_source_snapshot",
        occurred_at=decision_at,
        details={
            "schema_version": "recommendation-company-registry-source-snapshot-event.v1",
            "result_id": result_id,
            "decision_at": decision_at.isoformat(),
            "snapshot": _signed_company_source_snapshot(
                {
                    "schema_version": "recommendation-company-registry-source-snapshot.v2",
                    "result_id": result_id,
                    "decision_date": "2026-09-28",
                    "data_as_of_date": "2026-09-25",
                    "decision_at": decision_at.isoformat(),
                    "source_id": "DefaultRecommendationMarketDataProvider",
                    "market_data_fingerprint": fingerprint,
                    "scope": "current_classification_only",
                    "pit_eligible": False,
                    "company_registry_source_status": "unknown",
                    "industry_index_source_status": "unknown",
                }
            ),
        },
    )
    legacy_event = SimpleNamespace(
        event_type="legacy_invocation_context",
        occurred_at=decision_at,
        details={
            "source_id": "DefaultRecommendationMarketDataProvider",
            "market_data_fingerprint": fingerprint,
        },
    )
    universe_id = (
        "recommendation-universe-snapshot-v1:"
        "3af95e50ba9ffd160e3d9d6b493ad7084f94afcbc8f6081eaa5c93f475b524ce"
    )
    universe_hash = (
        "sha256:3af95e50ba9ffd160e3d9d6b493ad7084f94afcbc8f6081eaa5c93f475b524ce"
    )
    execution = SimpleNamespace(
        result_id=result_id,
        items=(),
        context=SimpleNamespace(
            as_of_date=date(2026, 9, 28),
            decision_at=decision_at,
            data_snapshot_refs=(SimpleNamespace(reference_id=fingerprint),),
            universe_identity=SimpleNamespace(
                snapshot=SimpleNamespace(
                    universe_snapshot_id=universe_id,
                    universe_snapshot_hash=universe_hash,
                )
            ),
        ),
        request=SimpleNamespace(profile_ref=None),
        events=(legacy_event, source_event),
    )
    view = _make_view()
    view.current_execution = execution
    view.current_config = {
        "data_date": "2026-09-27",
        "data_as_of_date": "2026-09-27",
    }
    monkeypatch.setattr(view, "_verified_saved_result_id", lambda: result_id)

    try:
        context = view._build_stock_research_context(
            "SYN002",
            "合成標的",
            SimpleNamespace(eligible_universe_date=date(2026, 9, 28)),
        )
        assert context.decision_date == "2026-09-28"
        assert context.data_date == "2026-09-25"
        assert context.source_snapshot_id == universe_id
        assert context.source_snapshot_hash == universe_hash
        view._update_research_context_banner(
            stock_code="SYN002",
            recommendation=SimpleNamespace(
                eligible_universe_date=date(2026, 9, 28)
            ),
        )
        assert "資料日期：2026-09-25" in view.research_context_label.text()

        v1_source_event = SimpleNamespace(
            event_type="company_registry_source_snapshot",
            occurred_at=decision_at,
            details={
                "schema_version": "recommendation-company-registry-source-snapshot-event.v1",
                "result_id": result_id,
                "decision_at": decision_at.isoformat(),
                "snapshot": _signed_company_source_snapshot(
                    {
                        "schema_version": "recommendation-company-registry-source-snapshot.v1",
                        "result_id": result_id,
                        "data_as_of_date": "2026-09-28",
                        "scope": "current_classification_only",
                        "pit_eligible": False,
                        "company_registry_source_status": "unknown",
                        "industry_index_source_status": "unknown",
                    }
                ),
            },
        )
        view.current_execution = SimpleNamespace(
            result_id=result_id,
            items=(),
            context=execution.context,
            request=execution.request,
            events=(legacy_event, v1_source_event),
        )
        v1_context = view._build_stock_research_context(
            "SYN002",
            "合成標的",
            SimpleNamespace(eligible_universe_date=date(2026, 9, 28)),
        )
        assert v1_context.data_date == ""
        view._update_research_context_banner(
            stock_code="SYN002",
            recommendation=SimpleNamespace(
                eligible_universe_date=date(2026, 9, 28)
            ),
        )
        assert "資料日期：未保存可核對的行情資料日" in view.research_context_label.text()

        view.current_execution = SimpleNamespace(
            result_id=result_id,
            items=(),
            context=execution.context,
            request=execution.request,
            events=(legacy_event,),
        )
        missing_event_context = view._build_stock_research_context(
            "SYN002",
            "合成標的",
            SimpleNamespace(eligible_universe_date=date(2026, 9, 28)),
        )
        assert missing_event_context.data_date == ""

        mismatched_snapshot = {
            **source_event.details["snapshot"],
            "market_data_fingerprint": "b" * 64,
        }
        mismatched_event = SimpleNamespace(
            event_type="company_registry_source_snapshot",
            occurred_at=decision_at,
            details={
                **source_event.details,
                "snapshot": mismatched_snapshot,
            },
        )
        view.current_execution = SimpleNamespace(
            result_id=result_id,
            items=(),
            context=execution.context,
            request=execution.request,
            events=(legacy_event, mismatched_event),
        )
        mismatched_context = view._build_stock_research_context(
            "SYN002",
            "合成標的",
            SimpleNamespace(eligible_universe_date=date(2026, 9, 28)),
        )
        assert mismatched_context.decision_date == "2026-09-28"
        assert mismatched_context.data_date == ""
        assert mismatched_context.source_snapshot_id == universe_id
        view._update_research_context_banner(
            stock_code="SYN002",
            recommendation=SimpleNamespace(
                eligible_universe_date=date(2026, 9, 28)
            ),
        )
        assert "資料日期：封存行情來源無法核對" in view.research_context_label.text()
        assert "2026-09-28" not in view.research_context_label.text().split(
            "資料日期：", maxsplit=1
        )[1].splitlines()[0]
    finally:
        view.close()


def test_personal_clock_v2_source_event_survives_real_save_and_exact_reload(
    qt_app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真個人時鐘 execution → canonical save/query → 新 view 單筆讀取。"""

    import app_module.recommendation_service as recommendation_service_module
    from app_module.journal_service import JournalService
    from app_module.recommendation import execute as execute_module
    from app_module.recommendation.composition import build_recommendation_composition
    from data_module.industry_mapper_data_provider import IndustryMapperDataProvider
    from app_module.recommendation.personal_use_policy import (
        RecommendationPersonalUsePolicyV1,
    )
    from tests.test_recommendation_personal_live_clock import (
        _DECISION_DATE,
        _SOURCE_DATE,
        _FrozenClock,
        _LiveFrameProvider,
        _market_frame,
        _runtime_config,
        _service,
    )

    with TemporaryDirectory(
        prefix=".tmp_ui_personal_clock_v2_",
        dir=Path.cwd(),
    ) as isolated_dir:
        isolated_root = Path(isolated_dir).resolve()
        provider = _LiveFrameProvider(
            SimpleNamespace(use_sqlite=False),
            _market_frame(),
        )
        config, service, observed_dates = _service(isolated_root, provider)
        industry_csv = isolated_root / "industry_index.csv"
        industry_csv.write_text(
            "日期,指數名稱,收盤指數,漲跌,漲跌點數,漲跌百分比\n"
            "2026-09-23,半導體類指數,99,+,1,1\n"
            "2026-09-24,半導體類指數,100,+,1,1\n",
            encoding="utf-8-sig",
        )
        industry_frame = IndustryMapperDataProvider(
            SimpleNamespace(
                meta_data_dir=isolated_root,
                industry_index_file=industry_csv,
                use_sqlite=False,
            )
        ).load_industry_index_frame()
        service.industry_mapper.companies_df = SimpleNamespace(attrs={})
        service.industry_mapper.industry_index_df = industry_frame
        service.industry_mapper.get_stock_industries.return_value = ["半導體"]
        service.industry_mapper.get_industry_performance.return_value = None
        service = service.with_personal_use_policy(
            RecommendationPersonalUsePolicyV1.default_rule_only("desktop-user")
        )
        monkeypatch.setattr(recommendation_service_module, "datetime", _FrozenClock)

        result_id = "ui-personal-v2-source-save-reload"
        execution = execute_module.execute_recommendation(
            service,
            _runtime_config(),
            max_stocks=1,
            top_n=1,
            result_id=result_id,
        )
        assert execution.status.value == "completed"
        assert observed_dates == [_SOURCE_DATE]

        composition = build_recommendation_composition(config)
        receipt = composition.save_service.save_execution(
            execution,
            label="個人即時來源 v2 驗證",
            notes="測試使用明確合成行情輸入",
        )
        assert receipt.result_id == result_id
        saved_read_model = composition.queries.get(result_id)
        assert saved_read_model is not None
        assert saved_read_model.execution == execution
        source_event = next(
            event
            for event in saved_read_model.execution.events
            if event.event_type == "company_registry_source_snapshot"
        )
        source_snapshot = source_event.details["snapshot"]
        assert source_snapshot["schema_version"] == (
            "recommendation-company-registry-source-snapshot.v2"
        )
        assert source_snapshot["decision_date"] == _DECISION_DATE
        assert source_snapshot["data_as_of_date"] == _SOURCE_DATE
        assert "current_industry_index_performance_for_reason" in (
            source_snapshot["usage"]
        )
        observation = source_snapshot["industry_index_source_observation"]
        assert observation["date_range"] == {
            "from": "2026-09-23",
            "through": "2026-09-24",
        }
        assert observation["available_at"] is None
        assert observation["published_at"] is None
        assert source_snapshot["industry_index_source_observation_sha256"] == (
            observation["observation_sha256"]
        )

        journal = JournalService(
            config,
            journal_path=config.output_root / "portfolio" / "journal_entries.jsonl",
        )
        view = _make_view(
            personal_policy_path=isolated_root / "personal-policy.json"
        )
        view.config = config
        view.recommendation_composition = composition
        view.journal_service = journal
        view.load_saved_result_button.setEnabled(True)
        try:
            # 執行後、保存前可檢視同次自洽封存列觀察，但明確標成未保存。
            view.current_execution = execution
            view.current_read_model = None
            view._update_company_source_snapshot_display(execution)
            unsaved_display = view.company_source_snapshot_label.text()
            assert "本輪尚未 canonical 保存；以下僅為本機觀測" in unsaved_display
            assert observation["rowset_sha256"] in unsaved_display
            assert observation["observed_at"] in unsaved_display
            assert "available_at／published_at 未知" in unsaved_display
            assert "PIT eligible=false" in unsaved_display

            # 改動 live CSV 後再載入舊結果；UI 必須仍呈現 sealed event 的觀察。
            industry_csv.write_text(
                "日期,指數名稱,收盤指數,漲跌,漲跌點數,漲跌百分比\n"
                "2099-01-01,假資料,999,+,1,1\n",
                encoding="utf-8-sig",
            )
            view.saved_result_id_input.setText(result_id)
            view.load_saved_result_button.click()
            _wait_for_saved_result_load(view, qt_app)

            assert view.current_read_model is not None
            assert view.current_read_model.execution == execution
            assert view.current_save_receipt is None
            displayed = view.company_source_snapshot_label.text()
            assert f"決策日 {_DECISION_DATE}" in displayed
            assert f"行情資料日 {_SOURCE_DATE}" in displayed
            assert f"行情來源 ID：{source_snapshot['source_id']}" in displayed
            assert f"sha256:{source_snapshot['market_data_fingerprint']}" in displayed
            assert "current_classification_only" in displayed
            assert "PIT eligible=false" in displayed
            assert "已 canonical 保存並以同一結果 ID 讀回" in displayed
            assert observation["rowset_sha256"] in displayed
            assert "2026-09-23 至 2026-09-24" in displayed
            assert observation["observed_at"] in displayed
            assert "available_at／published_at 未知" in displayed
            assert "2099-01-01" not in displayed

            def changed_source_snapshot(**changes: object):
                changed_events = []
                for event in execution.events:
                    if event.event_type != "company_registry_source_snapshot":
                        changed_events.append(event)
                        continue
                    details = _plain_json(event.details)
                    assert isinstance(details, dict)
                    snapshot = _plain_json(details["snapshot"])
                    assert isinstance(snapshot, dict)
                    snapshot.update(changes)
                    details["snapshot"] = _signed_company_source_snapshot(snapshot)
                    changed_events.append(replace(event, details=details))
                return replace(execution, events=tuple(changed_events))

            view._update_company_source_snapshot_display(
                changed_source_snapshot(decision_date="2026-09-26")
            )
            assert "決策日、時鐘或行情來源身分不符" in (
                view.company_source_snapshot_label.text()
            )

            # 只有外層重算快照仍不能遮蔽 inner observation echo mismatch。
            view._update_company_source_snapshot_display(
                changed_source_snapshot(
                    industry_index_source_observation_sha256="sha256:" + "c" * 64
                )
            )
            mismatched_observation_display = view.company_source_snapshot_label.text()
            assert "rowset SHA-256" not in mismatched_observation_display
            assert "封存列觀察缺漏、雜湊不符或時間狀態矛盾" in (
                mismatched_observation_display
            )

            # 即使 warning 字串本身包含預期 token，錯誤型別也不可通過。
            view._update_company_source_snapshot_display(
                changed_source_snapshot(
                    warnings=(
                        "industry_index_source_capture_time_unknown_for_current_use"
                    )
                )
            )
            malformed_warning_display = view.company_source_snapshot_label.text()
            assert "rowset SHA-256" not in malformed_warning_display
            assert "封存列觀察缺漏、雜湊不符或時間狀態矛盾" in (
                malformed_warning_display
            )

            # 明示未知行情日仍顯示未知，不以目前 provider 資料補值。
            view._update_company_source_snapshot_display(
                changed_source_snapshot(data_as_of_date=None)
            )
            unknown_display = view.company_source_snapshot_label.text()
            assert f"決策日 {_DECISION_DATE}" in unknown_display
            assert "行情資料日 未知" in unknown_display
            assert "不會改讀目前資料補值" not in unknown_display
        finally:
            view.close()
            qt_app.processEvents()


def test_personal_choice_readback_names_existing_outcome_review_route(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal_path = tmp_path / "journal.jsonl"
    journal_path.write_text("{}\n", encoding="utf-8")
    view = _make_view()
    view.journal_service = SimpleNamespace(
        store=SimpleNamespace(journal_file=journal_path)
    )
    entry = SimpleNamespace(
        choice=SimpleNamespace(
            choice="adopt",
            action_at="2026-09-27T12:00:00Z",
            outcome_link_status="identity_conflict",
        ),
        outcome_link_status="not_requested",
    )
    execution = SimpleNamespace()
    read_service = SimpleNamespace(
        read_canonical_execution_exact=lambda _result_id: SimpleNamespace(
            execution=execution
        ),
        read_personal_recommendation_choices=lambda _result_id, _stock_code: SimpleNamespace(
            source_completeness_status="verified", choices=(entry,)
        ),
    )
    monkeypatch.setattr(view, "_verified_saved_result_id", lambda: "result-1")
    monkeypatch.setattr(view, "_selected_stock_code", lambda: "2330")
    monkeypatch.setattr(view, "_personalization_read_service", lambda: read_service)
    monkeypatch.setattr(
        "app_module.personalization_contract.read_personal_use_policy_snapshot_event",
        lambda *_args, **_kwargs: {},
    )
    try:
        view._refresh_personal_choice_controls()
        status = view.personal_choice_controls.status_label.text()
        assert "最近一次個人決定：個人採用" in status
        assert "尚未查詢後續檢討" in status
        assert "個股研究的「決策 → 結果」" in status
        assert "不代表已核實績效" in status
        assert "後續結果與此推薦身分衝突" not in status
    finally:
        view.close()


def test_exact_saved_result_load_then_selection_and_choice_roundtrip(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真 canonical save → 新 view 單筆 get → 選股 → Journal fresh readback。"""

    from app_module.journal_service import JournalService
    from app_module.recommendation.composition import build_recommendation_composition
    from app_module.watchlist_service import WatchlistService
    from tests.test_personal_recommendation_choice import (
        _canonical_rule_only_query_fixture,
    )

    result_id = "ui-restart-loader-canonical-001"
    source_queries, _ = _canonical_rule_only_query_fixture(result_id)
    source_read_model = source_queries.get(result_id)
    assert source_read_model is not None and source_read_model.execution is not None

    # The production canonical query also anchors its legacy SQLite check with
    # no-follow handles. Keep this real-store integration under the workspace's
    # ignored temporary area so the test never depends on a user-profile TEMP ACL.
    with TemporaryDirectory(
        prefix=".tmp_ui_saved_result_loader_",
        dir=Path.cwd(),
    ) as isolated_dir:
        isolated_root = Path(isolated_dir).resolve()
        assert isolated_root.parent == Path.cwd().resolve()
        config = _IsolatedRecommendationConfig(isolated_root / "output")
        composition = build_recommendation_composition(config)
        save_receipt = composition.save_service.save_execution(
            source_read_model.execution,
            label="UI 單筆讀回測試",
            notes="isolated canonical fixture",
        )
        assert save_receipt.result_id == result_id
        journal = JournalService(
            config,
            journal_path=config.output_root / "portfolio" / "journal_entries.jsonl",
        )
        watchlist_service = WatchlistService(config)
        warning_messages: list[tuple[str, str]] = []
        monkeypatch.setattr(
            QMessageBox,
            "information",
            staticmethod(lambda *_args, **_kwargs: None),
        )
        monkeypatch.setattr(
            QMessageBox,
            "critical",
            staticmethod(lambda *_args, **_kwargs: None),
        )
        monkeypatch.setattr(
            QMessageBox,
            "warning",
            staticmethod(
                lambda _parent, title, message: warning_messages.append(
                    (str(title), str(message))
                )
            ),
        )

        view = _make_view(
            personal_policy_path=tmp_path / "personal-policy.json",
            watchlist_service=watchlist_service,
        )
        view.config = config
        view.recommendation_composition = composition
        view.journal_service = journal
        view.load_saved_result_button.setEnabled(True)
        try:
            view.saved_result_id_input.setText(result_id)
            view.load_saved_result_button.click()
            _wait_for_saved_result_load(view, qt_app)

            assert view.current_read_model is not None, view.result_status_label.text()
            assert view.current_read_model.integrity_basis == (
                "canonical_payload_and_index_verified"
            )
            assert view.current_execution == source_read_model.execution
            assert view.current_save_receipt is None
            assert view._verified_saved_result_id() == result_id
            assert view.add_to_watchlist_btn.isHidden() is False
            assert not view.add_to_watchlist_btn.isEnabled()
            assert view.select_stock("2330", result_id=result_id)
            assert view._selected_stock_code() == "2330"
            assert view.add_to_watchlist_btn.isEnabled()

            # 精確載入的 canonical 結果不需要此 View 內的寫入回條，
            # 但必須有已驗證的單筆讀回身份才可真正寫入 Watchlist。
            view.add_to_watchlist_btn.click()
            persisted_watchlist = WatchlistService(config).get_default_watchlist()
            assert persisted_watchlist is not None
            watchlist_items = [
                item
                for item in persisted_watchlist.items
                if item.decision_identity.result_id == result_id
            ]
            assert len(watchlist_items) == 1
            watchlist_identity = watchlist_items[0].decision_identity
            assert watchlist_identity.stock_code == "2330"
            assert watchlist_identity.decision_date == (
                source_read_model.execution.context.as_of_date.isoformat()
            )
            expected_snapshot_id, expected_snapshot_hash = (
                view._source_snapshot_identity(source_read_model.execution)
            )
            assert watchlist_identity.source_snapshot_id == expected_snapshot_id
            assert watchlist_identity.source_snapshot_hash == expected_snapshot_hash

            view.add_to_watchlist_btn.click()
            assert warning_messages[-1][0] == "未新增觀察項目"
            assert "來源連結未變更" in warning_messages[-1][1]
            fresh_watchlist = WatchlistService(config).get_default_watchlist()
            assert fresh_watchlist is not None
            assert [
                item.decision_identity.to_dict() for item in fresh_watchlist.items
            ].count(watchlist_identity.to_dict()) == 1

            # This uses the public view path and the real Journal/read-service writer;
            # the restored view deliberately has no in-process SaveReceipt.
            view._request_personal_recommendation_choice("adopt")
            report = view._personalization_read_service().read_personal_recommendation_choices(
                result_id, "2330"
            )
            assert report.source_completeness_status == "verified"
            assert len(report.choices) == 1
            assert report.choices[0].choice.choice == "adopt"
            assert report.choices[0].choice.result_id == result_id
            assert report.choices[0].choice.stock_code == "2330"
            assert report.choices[0].outcome_link_status == "not_requested"
            assert len(journal.list_decision_revisions()) == 1
        finally:
            view.close()
            qt_app.processEvents()


@pytest.mark.parametrize("failure_kind", ("missing", "legacy", "id_mismatch", "corrupt"))
def test_exact_saved_result_load_rejects_unverified_result_and_keeps_current_view(
    qt_app: QApplication,
    tmp_path: Path,
    failure_kind: str,
) -> None:
    from dataclasses import replace

    from tests.test_personal_recommendation_choice import (
        _canonical_rule_only_query_fixture,
    )

    requested_id = "ui-restart-loader-requested-001"
    other_id = "ui-restart-loader-other-001"
    valid_queries, _ = _canonical_rule_only_query_fixture(requested_id)
    other_queries, _ = _canonical_rule_only_query_fixture(other_id)
    valid_read_model = valid_queries.get(requested_id)
    other_read_model = other_queries.get(other_id)
    assert valid_read_model is not None and other_read_model is not None
    if failure_kind == "missing":
        read_result = lambda _result_id: None
    elif failure_kind == "legacy":
        read_result = lambda _result_id: replace(
            valid_read_model,
            integrity_basis="legacy_read_time_hash_only",
        )
    elif failure_kind == "id_mismatch":
        read_result = lambda _result_id: other_read_model
    else:
        def read_result(_result_id):
            raise ValueError("canonical artifact integrity failure")

    view = _make_view()
    view.config = _IsolatedRecommendationConfig(tmp_path / "output")
    view.recommendation_composition = SimpleNamespace(
        queries=SimpleNamespace(get=read_result)
    )
    previous_execution = object()
    view.current_execution = previous_execution
    view.result_status_label.setText("原畫面")
    try:
        view.saved_result_id_input.setText(requested_id)
        view._load_saved_recommendation_result()
        _wait_for_saved_result_load(view, qt_app)

        assert view.current_execution is previous_execution
        assert view.current_read_model is None
        assert view.current_save_receipt is None
        assert view._verified_saved_result_id() == ""
        assert requested_id in view.result_status_label.text()
        assert "原畫面保留" in view.result_status_label.text()
    finally:
        view.close()
        qt_app.processEvents()


def test_saved_result_load_late_generation_cannot_replace_current_result(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    from tests.test_personal_recommendation_choice import (
        _canonical_rule_only_query_fixture,
    )

    requested_id = "ui-restart-loader-late-001"
    queries, _ = _canonical_rule_only_query_fixture(requested_id)
    entered = threading.Event()
    release = threading.Event()

    def delayed_get(result_id: str):
        entered.set()
        assert release.wait(5)
        return queries.get(result_id)

    view = _make_view()
    view.config = _IsolatedRecommendationConfig(tmp_path / "output")
    view.recommendation_composition = SimpleNamespace(
        queries=SimpleNamespace(get=delayed_get)
    )
    previous_execution = object()
    view.current_execution = previous_execution
    try:
        view.saved_result_id_input.setText(requested_id)
        view._load_saved_recommendation_result()
        worker = view._saved_result_load_worker
        assert worker is not None
        assert entered.wait(2)
        view._saved_result_load_generation += 1
        release.set()
        assert worker.wait(10_000)
        qt_app.processEvents()
        qt_app.processEvents()

        assert view.current_execution is previous_execution
        assert view.current_read_model is None
        assert view._verified_saved_result_id() == ""
    finally:
        release.set()
        view.close()
        qt_app.processEvents()


def test_saved_result_load_cooperatively_cancels_and_blocks_close_until_worker_stops(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    from tests.test_personal_recommendation_choice import (
        _canonical_rule_only_query_fixture,
    )

    requested_id = "ui-restart-loader-close-001"
    queries, _ = _canonical_rule_only_query_fixture(requested_id)
    entered = threading.Event()
    release = threading.Event()

    def delayed_get(result_id: str):
        entered.set()
        assert release.wait(5)
        return queries.get(result_id)

    view = _make_view()
    view.config = _IsolatedRecommendationConfig(tmp_path / "output")
    view.recommendation_composition = SimpleNamespace(
        queries=SimpleNamespace(get=delayed_get)
    )
    previous_execution = object()
    view.current_execution = previous_execution
    try:
        view.saved_result_id_input.setText(requested_id)
        view._load_saved_recommendation_result()
        worker = view._saved_result_load_worker
        assert worker is not None
        assert entered.wait(2)

        first_close = QCloseEvent()
        view.closeEvent(first_close)
        assert not first_close.isAccepted()
        assert worker.is_cancel_requested()
        assert worker.isRunning()
        assert view.current_execution is previous_execution

        release.set()
        assert worker.wait(10_000)
        qt_app.processEvents()
        qt_app.processEvents()
        second_close = QCloseEvent()
        view.closeEvent(second_close)
        assert second_close.isAccepted()
        assert view.current_execution is previous_execution
    finally:
        release.set()
        view.close()
        qt_app.processEvents()


def _bind_loaded_read_model(view: RecommendationView, read_model: Any) -> None:
    assert read_model.execution is not None
    view.current_execution = read_model.execution
    view.current_read_model = read_model
    view.current_save_receipt = None
    view.current_result_id = read_model.result_id
    view._loaded_saved_result_identity = view._canonical_loaded_result_identity(
        read_model, read_model.result_id
    )


def _wait_for_personal_prediction_capture(
    view: RecommendationView,
    qt_app: QApplication,
) -> None:
    worker = view._personal_prediction_capture_worker
    assert worker is not None
    assert worker.wait(30_000)
    for _ in range(4):
        qt_app.processEvents()


def test_personal_capture_follows_verified_save_and_retries_exact_loaded_result(
    qt_app: QApplication,
    workspace_personal_capture_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真 canonical save 後擷取；失敗不回滾，精確載入後重試保持冪等。"""

    from app_module.recommendation.composition import build_recommendation_composition
    from app_module.recommendation.personal_prediction_capture import (
        PersonalPredictionCaptureError,
        capture_personal_saved_result,
        read_personal_prediction_capture,
    )
    import app_module.recommendation.personal_prediction_capture as capture_module
    from tests.test_recommendation_personal_prediction_capture import _build_case

    execution, _source_receipt, _source_path, _source_persistence, _source_queries, _policy = (
        _build_case(workspace_personal_capture_root / "source")
    )
    config = _IsolatedRecommendationConfig(
        workspace_personal_capture_root / "canonical-output"
    )
    composition = build_recommendation_composition(config)
    view = _make_view()
    view.config = config
    view.recommendation_composition = composition
    view.current_execution = execution

    calls = 0

    def fail_once(result_id: str, queries: Any, personal_root: Any):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PersonalPredictionCaptureError("隔離測試的一次性擷取失敗")
        return capture_personal_saved_result(result_id, queries, personal_root)

    monkeypatch.setattr(capture_module, "capture_personal_saved_result", fail_once)
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *_args, **_kwargs: ("UI 個人模型擷取測試", True),
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *_args, **_kwargs: None)
    dialogs: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, title, message, **_kwargs: dialogs.append(
            (str(title), str(message))
        ),
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda _parent, title, message, **_kwargs: dialogs.append(
            (str(title), str(message))
        ),
    )

    try:
        view._save_recommendation_result()
        assert not dialogs, dialogs
        result_id = execution.result_id
        saved = composition.queries.get(result_id)
        assert saved is not None and saved.execution == execution
        assert saved.integrity_basis == "canonical_payload_and_index_verified"

        _wait_for_personal_prediction_capture(view, qt_app)
        assert view.current_read_model is not None
        assert view._verified_saved_result_id() == result_id
        assert "擷取未完成" in view.personal_prediction_capture_status_label.text()
        assert "推薦結果不受影響" in view.personal_prediction_capture_status_label.text()
        assert view.personal_prediction_capture_retry_button.isEnabled()

        view.personal_prediction_capture_retry_button.click()
        _wait_for_personal_prediction_capture(view, qt_app)
        first_success = view._personal_prediction_capture_receipt
        assert first_success is not None
        assert first_success.idempotent is False
        assert first_success.path.is_file()
        personal_root = config.output_root.resolve() / "personal_prediction"
        payload = read_personal_prediction_capture(
            first_success.path,
            composition.queries,
            personal_root,
            expected_result_id=result_id,
        )
        assert payload["result_id"] == result_id

        view.personal_prediction_capture_retry_button.click()
        _wait_for_personal_prediction_capture(view, qt_app)
        assert view._personal_prediction_capture_receipt.idempotent is True
        assert len(list((personal_root / "captures").glob("*.json"))) == 1
    finally:
        view.close()
        qt_app.processEvents()

    restored_view = _make_view()
    restored_view.config = config
    restored_view.recommendation_composition = composition
    try:
        restored_view.saved_result_id_input.setText(execution.result_id)
        restored_view._load_saved_recommendation_result()
        _wait_for_saved_result_load(restored_view, qt_app)
        assert restored_view._verified_saved_result_id() == execution.result_id
        assert restored_view.current_save_receipt is None
        assert restored_view.personal_prediction_capture_retry_button.isEnabled()

        restored_view.personal_prediction_capture_retry_button.click()
        _wait_for_personal_prediction_capture(restored_view, qt_app)
        assert restored_view._personal_prediction_capture_receipt.idempotent is True
        assert "既有擷取已重新核對" in (
            restored_view.personal_prediction_capture_status_label.text()
        )
    finally:
        restored_view.close()
        qt_app.processEvents()


@pytest.mark.parametrize(
    ("include_policy_event", "expected_status"),
    (
        (True, "本次實際採規則模式"),
        (False, "不會套用目前設定或回補歷史"),
    ),
)
def test_personal_capture_skips_rule_only_and_unknown_history(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    include_policy_event: bool,
    expected_status: str,
) -> None:
    from tests.test_personal_recommendation_choice import (
        _canonical_rule_only_query_fixture,
    )

    queries, _receipt = _canonical_rule_only_query_fixture(
        f"ui-personal-capture-skip-{include_policy_event}",
        include_policy_event=include_policy_event,
    )
    read_model = queries.get(f"ui-personal-capture-skip-{include_policy_event}")
    assert read_model is not None
    view = _make_view()
    view.config = _IsolatedRecommendationConfig(tmp_path / "output")
    view.recommendation_composition = SimpleNamespace(queries=queries)
    _bind_loaded_read_model(view, read_model)
    monkeypatch.setattr(
        "app_module.recommendation.personal_prediction_capture.capture_personal_saved_result",
        lambda *_args, **_kwargs: pytest.fail("規則／歷史結果不得建立模型擷取"),
    )
    try:
        view._refresh_personal_prediction_capture_controls()
        assert expected_status in view.personal_prediction_capture_status_label.text()
        assert not view.personal_prediction_capture_retry_button.isEnabled()
        view.personal_prediction_capture_retry_button.click()
        assert view._personal_prediction_capture_worker is None
    finally:
        view.close()
        qt_app.processEvents()


def test_personal_capture_conflict_keeps_saved_recommendation_unchanged(
    qt_app: QApplication,
    workspace_personal_capture_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_module.recommendation.personal_prediction_capture import (
        PersonalPredictionCaptureConflict,
    )
    from tests.test_recommendation_personal_prediction_capture import _build_case

    execution, _receipt, _receipt_path, _persistence, queries, _policy = _build_case(
        workspace_personal_capture_root
    )
    read_model = queries.get(execution.result_id)
    assert read_model is not None
    view = _make_view()
    view.config = _IsolatedRecommendationConfig(
        workspace_personal_capture_root / "output"
    )
    view.recommendation_composition = SimpleNamespace(queries=queries)
    _bind_loaded_read_model(view, read_model)
    before_hash = read_model.payload_hash
    monkeypatch.setattr(
        "app_module.recommendation.personal_prediction_capture.capture_personal_saved_result",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            PersonalPredictionCaptureConflict("相同身分已有不同內容；拒絕覆寫")
        ),
    )
    try:
        view._refresh_personal_prediction_capture_controls()
        view.personal_prediction_capture_retry_button.click()
        _wait_for_personal_prediction_capture(view, qt_app)
        after = queries.get(execution.result_id)
        assert after is not None and after.payload_hash == before_hash
        assert after.execution == execution
        assert "推薦結果不受影響" in view.personal_prediction_capture_status_label.text()
        assert view.personal_prediction_capture_retry_button.isEnabled()
    finally:
        view.close()
        qt_app.processEvents()


def test_personal_capture_late_worker_cannot_replace_new_result_status(
    qt_app: QApplication,
    workspace_personal_capture_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_module.recommendation.personal_prediction_capture as capture_module
    from tests.test_personal_recommendation_choice import (
        _canonical_rule_only_query_fixture,
    )
    from tests.test_recommendation_personal_prediction_capture import _build_case

    execution, _receipt, _receipt_path, _persistence, queries, _policy = _build_case(
        workspace_personal_capture_root / "model"
    )
    model_read_model = queries.get(execution.result_id)
    assert model_read_model is not None
    entered = threading.Event()
    release = threading.Event()
    from app_module.recommendation.personal_prediction_capture import (
        capture_personal_saved_result,
    )

    def delayed_capture(result_id: str, source_queries: Any, personal_root: Any):
        entered.set()
        assert release.wait(10)
        return capture_personal_saved_result(result_id, source_queries, personal_root)

    monkeypatch.setattr(
        capture_module, "capture_personal_saved_result", delayed_capture
    )
    view = _make_view()
    view.config = _IsolatedRecommendationConfig(
        workspace_personal_capture_root / "output"
    )
    view.recommendation_composition = SimpleNamespace(queries=queries)
    _bind_loaded_read_model(view, model_read_model)
    try:
        view._refresh_personal_prediction_capture_controls()
        view.personal_prediction_capture_retry_button.click()
        assert entered.wait(5)

        rule_id = "ui-personal-capture-new-rule-result"
        rule_queries, _rule_receipt = _canonical_rule_only_query_fixture(rule_id)
        rule_read_model = rule_queries.get(rule_id)
        assert rule_read_model is not None
        _bind_loaded_read_model(view, rule_read_model)
        view.recommendation_composition = SimpleNamespace(queries=rule_queries)
        view._refresh_personal_prediction_capture_controls()
        expected_text = view.personal_prediction_capture_status_label.text()
        assert "本次實際採規則模式" in expected_text

        release.set()
        worker = view._personal_prediction_capture_worker
        assert worker is not None and worker.wait(30_000)
        for _ in range(4):
            qt_app.processEvents()

        assert view._verified_saved_result_id() == rule_id
        assert "本次實際採規則模式" in view.personal_prediction_capture_status_label.text()
        assert "擷取已建立並核對" not in view.personal_prediction_capture_status_label.text()
        assert view._personal_prediction_capture_receipt is None
        assert not view.personal_prediction_capture_retry_button.isEnabled()
    finally:
        release.set()
        view.close()
        qt_app.processEvents()
