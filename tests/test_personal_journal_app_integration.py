"""notes composition 隔離驗證；不讀取正式 Journal 或操控 Native UI。"""
from pathlib import Path
from types import SimpleNamespace
import os
import subprocess
import sys

import pytest

from app_module.continuity_review_projection import ContinuityReviewProjectionService
from app_module.decision_continuity_controller import DecisionContinuityController
from app_module.decision_outcome_journey import DecisionOutcomeJourneyService
from app_module.dtos.decision_continuity_dtos import ACTION_NOTE, DecisionIdentity
from app_module.journal_service import JournalService
from app_module.personal_journal_paths import resolve_journal_storage_selection
from app_module.workbench_source_service import WorkbenchSourceService
from data_module.config import TWStockConfig


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    for name in ("PERSONAL_JOURNAL_ROOT", "PERSONAL_JOURNAL_MODE", "PERSONAL_DATA_ROOT",
                 "PERSONAL_WATCHLIST_SOURCE"):
        monkeypatch.delenv(name, raising=False)


def config(tmp_path, mode="personal"):
    return TWStockConfig(data_root=tmp_path / "market", output_root=tmp_path / "market/output",
                         personal_journal_root=tmp_path / "personal", personal_journal_mode=mode,
                         profile="test")


@pytest.mark.parametrize("kwargs,error", [
    ({"personal_journal_root": "root"}, "selection_incomplete"),
    ({"personal_journal_mode": "personal"}, "selection_incomplete"),
    ({"personal_journal_root": "root", "personal_journal_mode": "wrong"}, "mode_invalid"),
])
def test_incomplete_selection_rejected_before_config_mkdir(tmp_path, kwargs, error):
    if "personal_journal_root" in kwargs:
        kwargs["personal_journal_root"] = tmp_path / "personal"
    with pytest.raises(ValueError, match=error):
        TWStockConfig(data_root=tmp_path / "market", output_root=tmp_path / "output", **kwargs)
    assert list(tmp_path.iterdir()) == []


def test_notes_config_independent_watchlist_and_preserves_market_paths(tmp_path):
    selected = config(tmp_path)
    assert selected.personal_data_root is None and selected.personal_watchlist_source is None
    assert selected.db_file == selected.data_root / "sqlite/twstock.db"
    assert selected.output_root == tmp_path / "market/output/_test"
    assert not selected.personal_journal_root.exists()
    args, _ = TWStockConfig.from_args(["--data-root", str(tmp_path / "market"),
                                   "--output-root", str(tmp_path / "market/output"), "--profile", "test",
                                   "--personal-journal-root", str(tmp_path / "personal"),
                                   "--personal-journal-mode", "legacy_read_only"])
    assert resolve_journal_storage_selection(args).legacy_read_only
    assert not args.personal_journal_root.exists()


def test_selected_writer_controller_and_all_readers_share_notes(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from ui_qt.views.recommendation_view import RecommendationView
    cfg = config(tmp_path)
    selection = resolve_journal_storage_selection(cfg)
    paths = selection.paths
    assert paths is not None
    # 來源存在但個人模式不混讀、不 fallback。
    paths.legacy_source.parent.mkdir(parents=True, exist_ok=True)
    paths.legacy_source.write_bytes(b'{"journal_id":"old","body":"legacy fixture"}\n')
    before = paths.legacy_source.read_bytes(), paths.legacy_source.stat().st_mtime_ns
    journal = JournalService(cfg, journal_paths=paths)
    controller = DecisionContinuityController(journal)
    identity = DecisionIdentity(result_id="R", stock_code="2330")
    result = controller.apply(ACTION_NOTE, identity, note="personal fixture", request_id="one")
    assert result.success and result.readback_verified
    workbench = WorkbenchSourceService(cfg, journal_paths=paths)
    continuity = workbench.continuity_review_projection_service
    assert continuity.journal_path == paths.journal_file
    assert continuity.project().stream_status == "ready"
    journey = DecisionOutcomeJourneyService.from_config(cfg, journal_paths=paths)
    assert journey.journal_reader.path == paths.journal_file
    assert journey.journal_reader.list_entries()[0]["body"] == "personal fixture"
    # 呼叫真正 UI reader factory，不啟動主程式。
    reader = RecommendationView._personalization_read_service(
        SimpleNamespace(config=cfg, journal_service=journal))
    assert reader.journal_source.journal_paths is paths
    assert reader.journal_source.path == paths.journal_file
    assert reader.evidence_source.db_path == cfg.output_root.parent / "sqlite/twstock.db"
    assert len(reader.journal_source.list_action_rows("R", "2330")) == 1
    assert (paths.legacy_source.read_bytes(), paths.legacy_source.stat().st_mtime_ns) == before
    assert not paths.personal_paths.watchlist_db.exists()
    assert not paths.legacy_source.with_name(".journal_entries.jsonl.lock").exists()


def test_legacy_readonly_controller_and_readers_never_open_writer(tmp_path):
    cfg = config(tmp_path, "legacy_read_only")
    selection = resolve_journal_storage_selection(cfg)
    paths = selection.paths
    journal = JournalService(cfg, journal_paths=paths, legacy_read_only=True)
    controller = DecisionContinuityController(journal)
    identity = DecisionIdentity(result_id="R", stock_code="2330")
    state = controller.read_state(identity)
    assert not state.can_write and "唯讀" in state.blocked_reason
    result = controller.apply(ACTION_NOTE, identity, note="blocked", request_id="blocked")
    assert not result.success
    workbench = WorkbenchSourceService(cfg, journal_paths=paths, legacy_journal_read_only=True)
    assert workbench.continuity_review_projection_service.journal_path == paths.legacy_source
    assert workbench.continuity_review_projection_service.project().stream_status == "missing"
    journey = DecisionOutcomeJourneyService.from_config(cfg, journal_paths=paths,
                                                       legacy_journal_read_only=True)
    assert journey.journal_reader.list_entries() == []
    assert not paths.personal_paths.personal_root.exists()
    assert not paths.legacy_source.parent.exists()


def test_journey_revalidates_selected_path_and_unknown_record_type(tmp_path):
    cfg = config(tmp_path)
    paths = resolve_journal_storage_selection(cfg).paths
    journey = DecisionOutcomeJourneyService.from_config(cfg, journal_paths=paths)
    paths.journal_file.parent.mkdir(parents=True)
    paths.journal_file.write_bytes(b'{"record_type":"future_unknown"}\n')
    with pytest.raises(ValueError, match="unknown_record_type"):
        journey.journal_reader.list_entries()
    with pytest.raises(ValueError, match="selector_conflict"):
        DecisionOutcomeJourneyService.from_config(cfg, journal_paths=paths,
                                                 journal_path=paths.legacy_source)
    assert not paths.lock_file.exists()


def test_journey_refuses_link_swap_after_construction(tmp_path):
    cfg = config(tmp_path)
    paths = resolve_journal_storage_selection(cfg).paths
    journey = DecisionOutcomeJourneyService.from_config(cfg, journal_paths=paths)
    paths.journal_file.parent.mkdir(parents=True)
    paths.journal_file.write_bytes(b'{"journal_id":"fixture"}\n')
    os.link(paths.journal_file, tmp_path / "alias.jsonl")
    with pytest.raises(ValueError, match="alias_or_type"):
        journey.journal_reader.list_entries()
    assert not paths.lock_file.exists()


def test_notes_config_rejects_application_root_before_side_effects(tmp_path):
    with pytest.raises(ValueError, match="overlaps_application_package"):
        TWStockConfig(data_root=tmp_path / "market", output_root=tmp_path / "output",
                      personal_journal_root=Path(__file__).resolve().parents[1] / "private",
                      personal_journal_mode="personal")
    assert list(tmp_path.iterdir()) == []


def test_unconfigured_selection_explicitly_preserves_compatibility(tmp_path):
    cfg = TWStockConfig(data_root=tmp_path / "market", output_root=tmp_path / "output", profile="test")
    selection = resolve_journal_storage_selection(cfg)
    assert selection.paths is None and not selection.legacy_read_only
    journal = JournalService(cfg, journal_paths=selection.paths)
    journal.add_journal_entry("compatibility fixture")
    assert journal.store.journal_file == cfg.output_root / "portfolio/journal_entries.jsonl"


@pytest.mark.parametrize("caller", ["journal", "workbench", "journey"])
def test_personal_config_cannot_fall_back_through_none_selector(tmp_path, caller):
    cfg = config(tmp_path)
    with pytest.raises(ValueError, match="selector_required"):
        if caller == "journal":
            JournalService(cfg)
        elif caller == "workbench":
            WorkbenchSourceService(cfg)
        else:
            DecisionOutcomeJourneyService.from_config(cfg)
    assert not (cfg.output_root / "portfolio").exists()
    assert not cfg.personal_journal_root.exists()


def test_personal_notes_fresh_process_reopen_preserves_legacy(tmp_path):
    script = r'''
import sys
from pathlib import Path
from data_module.config import TWStockConfig
from app_module.personal_journal_paths import resolve_journal_storage_selection
from app_module.journal_service import JournalService
c=TWStockConfig(data_root=Path(sys.argv[1]),output_root=Path(sys.argv[1])/'output',profile='test')
s=resolve_journal_storage_selection(c)
j=JournalService(c,journal_paths=s.paths,legacy_read_only=s.legacy_read_only)
if sys.argv[2]=='write': j.add_journal_entry('new process fixture',journal_id='one')
assert [n.journal_id for n in j.list_journal_entries()]==['one']
assert not s.paths.legacy_source.exists()
'''
    env = dict(os.environ, PERSONAL_JOURNAL_ROOT=str(tmp_path / "personal"), PERSONAL_JOURNAL_MODE="personal")
    for mode in ("write", "read"):
        result = subprocess.run([sys.executable, "-c", script, str(tmp_path / "market"), mode],
                                env=env, capture_output=True, text=True, timeout=30,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("mode", ["personal", "legacy_read_only"])
def test_mainwindow_notes_composition_in_fresh_offscreen_process(tmp_path, mode):
    script = r'''
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication, QMessageBox
import ui_qt.main as main
# 本驗證只關注 notes composition，不讀正式 ML registry。
main.CurrentRestatedMLRunRegistry = lambda: SimpleNamespace()
QMessageBox.critical = lambda *args, **kwargs: None
QMessageBox.warning = lambda *args, **kwargs: None
QMessageBox.information = lambda *args, **kwargs: None
app = QApplication([])
window = main.MainWindow()
s = window.journal_storage_selection
assert s.paths is not None
expected = s.paths.read_path(legacy_read_only=s.legacy_read_only)
assert window.journal_service.store.journal_file == expected
assert window.decision_continuity_controller.journal_service is window.journal_service
assert window.workbench_source_service.continuity_review_projection_service.journal_path == expected
assert window.decision_outcome_journey_service.journal_reader.path == expected
reader = window.recommendation_view._personalization_read_service()
assert reader.journal_source.path == expected
assert reader.journal_source.journal_paths is s.paths
assert reader.journal_source.legacy_read_only == s.legacy_read_only
assert not s.paths.personal_paths.personal_root.exists()
assert not expected.exists()
assert not s.paths.legacy_source.with_name('.journal_entries.jsonl.lock').exists()
window.close()
app.processEvents()
print('notes-composition-ok')
'''
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PROFILE="test",
               DATA_ROOT=str(tmp_path / "market"), OUTPUT_ROOT=str(tmp_path / "output"),
               PERSONAL_JOURNAL_ROOT=str(tmp_path / "personal"), PERSONAL_JOURNAL_MODE=mode,
               PYTHONIOENCODING="utf-8")
    result = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True,
                            text=True, encoding="utf-8", timeout=45,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    assert "notes-composition-ok" in result.stdout
