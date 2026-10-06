"""B01：實際 repo H6/H7 裁決後保留六條待修違例，不能把 synthetic AST 成功當 repo pass。"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ml_module.shadow_boundary_guard import MLShadowBoundaryGuard
from scripts.check_ml_shadow_boundary import ROOT, main


LEGACY_VIOLATIONS = (
    "ml_imports_production_path:ml_module/current_observed_feature_snapshot_composer.py:app_module.recommendation.queries",
    "ml_imports_production_path:ml_module/current_observed_feature_snapshot_composer.py:app_module.saved_recommendation_queries",
    "ml_imports_production_path:ml_module/current_observed_feature_snapshot_composer.py:app_module.saved_recommendation_queries",
    "production_imports_ml_module:app_module/personalization_read_service.py:ml_module.recommendation_calibration_evidence:verify_natural_maturity_session_proof",
    "production_imports_ml_module:app_module/recommendation_calibration_consumer.py:ml_module.recommendation_calibration_training:InvalidCalibrationOutputError",
    "production_imports_ml_module:app_module/stock_research_report_provider_adapters.py:ml_module.current_restated_research_bridge:load_current_restated_outcome_model",
)


def test_shadow_boundary_cli_reports_clean_repository(capsys) -> None:
    assert main([]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["inspected_files"] >= 659
    assert report["shadow_only"] is True
    assert report["violations"] == []
    assert MLShadowBoundaryGuard(ROOT).inspect().violations == ()


def _inspect_import(tmp_path: Path, source: str, caller: str = "model_registry_readonly.py"):
    app = tmp_path / "app_module"
    app.mkdir()
    (app / caller).write_text(source + "\n", encoding="utf-8")
    return MLShadowBoundaryGuard(tmp_path).inspect()


def test_registry_reader_allows_exact_reviewed_symbols_in_ast(tmp_path: Path) -> None:
    report = _inspect_import(tmp_path, (
        "from ml_module.model_lifecycle_registry import ModelLifecycleEvent as Event, _ALLOWED_TRANSITIONS\n"
        "from ml_module.model_prediction_registries import MLModelRecord as Model"
    ))
    assert report.inspected_files == 1
    assert report.violations == ()


@pytest.mark.parametrize("source", [
    "from ml_module.model_lifecycle_registry import ModelLifecycleRegistry",
    "from ml_module.model_lifecycle_registry import initialize_model_lifecycle_registry",
    "from ml_module.model_prediction_registries import MLModelRegistry",
    "from ml_module.model_prediction_registries import MLShadowPredictionRegistry",
    "from ml_module.model_prediction_registries import initialize_shadow_registry",
    "from ml_module.model_prediction_registries import register_model",
    "from ml_module.model_lifecycle_registry import append",
    "from ml_module.boosted_challengers import BoostedShadowChallengerTrainer",
    "from ml_module.model_lifecycle_registry import *",
    "from ml_module.model_prediction_registries import *",
    "import ml_module.model_lifecycle_registry as registry",
    "from ml_module import model_prediction_registries",
    "from ml_module.model_lifecycle_registry import ModelLifecycleEvent, ModelLifecycleRegistry as EventWriter",
])
def test_registry_reader_rejects_writer_trainer_and_namespace_in_ast(tmp_path: Path, source: str) -> None:
    report = _inspect_import(tmp_path, source)
    assert report.inspected_files == 1
    assert len(report.violations) == 1
    assert report.violations[0].startswith("production_imports_ml_module:")


def test_registry_exact_exception_does_not_allow_another_caller(tmp_path: Path) -> None:
    report = _inspect_import(
        tmp_path, "from ml_module.model_prediction_registries import MLModelRecord", "unreviewed_reader.py",
    )
    assert len(report.violations) == 1
    assert "unreviewed_reader.py" in report.violations[0]


@pytest.mark.parametrize("source", [
    "from ml_module.historical_contracts import HistoricalLabelRow",
    "from ml_module.historical_contracts import HistoricalLabelSpec",
    "from ml_module.historical_contracts import HistoricalLabelRow as Row, HistoricalLabelSpec as Spec",
])
def test_label_reader_allows_only_reviewed_contract_symbols(tmp_path: Path, source: str) -> None:
    report = _inspect_import(tmp_path, source, "rule_research_label_readiness.py")
    assert report.inspected_files == 1
    assert report.violations == ()


@pytest.mark.parametrize("source", [
    "import ml_module.historical_contracts as contracts",
    "from ml_module import historical_contracts",
    "from ml_module.historical_contracts import *",
    "from ml_module.historical_contracts import HistoricalFeatureRow",
    "from ml_module.historical_contracts import HistoricalLabelRow, HistoricalDatasetRow",
    "from ml_module.historical_contracts import HistoricalLabelSpec, append",
    "from ml_module.model_prediction_registries import MLModelRegistry",
    "from ml_module.model_lifecycle_registry import initialize_model_lifecycle_registry",
    "from ml_module.boosted_challengers import BoostedShadowChallengerTrainer",
])
def test_label_reader_rejects_unreviewed_symbols_writer_trainer_and_namespace(
    tmp_path: Path, source: str,
) -> None:
    report = _inspect_import(tmp_path, source, "rule_research_label_readiness.py")
    assert len(report.violations) == 1
    assert report.violations[0].startswith("production_imports_ml_module:")


@pytest.mark.parametrize("caller", ["unreviewed_reader.py", "rule_research_label_readiness_copy.py"])
@pytest.mark.parametrize("symbol", ["HistoricalLabelRow", "HistoricalLabelSpec"])
def test_label_contract_exception_requires_exact_caller(
    tmp_path: Path, caller: str, symbol: str,
) -> None:
    report = _inspect_import(tmp_path, f"from ml_module.historical_contracts import {symbol}", caller)
    assert len(report.violations) == 1
    assert caller in report.violations[0]


def test_historical_label_contracts_cold_import_and_dtos_have_no_data_io() -> None:
    """新程序只准 Python 原碼／bytecode loader；其他資料、DB、網路與 registry I/O 皆拒。"""
    probe = r'''
import __future__, builtins, dataclasses, datetime, importlib.util, json, os, pathlib, socket, sqlite3, sys, typing
from unittest.mock import patch
assert not any(name == "ml_module" or name.startswith("ml_module.") for name in sys.modules)
root = pathlib.Path.cwd()
source_paths = [root / "ml_module" / name for name in ("__init__.py", "historical_contracts.py")]
allowed_code = {os.path.normcase(str(path)) for path in source_paths}
allowed_code.update(os.path.normcase(importlib.util.cache_from_source(str(path))) for path in source_paths)
code_opens = []
def audit(event, args):
    if event == "open":
        path, mode, flags = args
        if not isinstance(path, str) or os.path.normcase(path) not in allowed_code or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
            raise AssertionError("unexpected file I/O: " + repr(args))
        code_opens.append(path)
    elif event.startswith(("sqlite3.", "socket.", "winreg.", "subprocess.")) or event in {
        "os.mkdir", "os.remove", "os.rename", "os.rmdir", "os.system", "os.truncate", "os.link", "os.symlink"
    }:
        raise AssertionError("unexpected side effect: " + event)
def forbidden(*args, **kwargs):
    raise AssertionError("DTO path performed data I/O")
sys.addaudithook(audit)
with patch.object(builtins, "open", forbidden), patch.object(os, "open", forbidden), \
     patch.object(pathlib.Path, "open", forbidden), patch.object(pathlib.Path, "read_bytes", forbidden), \
     patch.object(pathlib.Path, "read_text", forbidden), patch.object(pathlib.Path, "mkdir", forbidden), \
     patch.object(sqlite3, "connect", forbidden), patch.object(socket, "create_connection", forbidden):
    from ml_module.historical_contracts import HistoricalLabelRow, HistoricalLabelSpec
    spec = HistoricalLabelSpec("gross_h5_bp", "int", "bp", 5, "missing_is_not_zero_and_excluded", "sealed_point_available_date_when_declared")
    row = HistoricalLabelRow("2330", "2026-10-01", spec.label_id, 125, "2026-10-08", "2026-10-09", "ready", "research_only")
    assert dataclasses.asdict(spec)["horizon_trading_days"] == 5
    assert dataclasses.asdict(row)["value"] == 125
    assert not row.is_fit_eligible(training_as_of="2026-10-08")
    assert row.is_fit_eligible(training_as_of="2026-10-09")
    pending = dataclasses.replace(row, value=None, maturity_status="pending")
    assert not pending.is_fit_eligible(training_as_of="2026-10-10")
    for changes, error in [({"available_date": "2026-10-07"}, ValueError), ({"value": True}, TypeError), ({"value": None}, ValueError)]:
        try:
            dataclasses.replace(row, **changes)
        except error:
            pass
        else:
            raise AssertionError("invalid label accepted")
    try:
        dataclasses.replace(spec, horizon_trading_days=0)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid horizon accepted")
    try:
        row.value = 0
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("DTO is mutable")
assert {name for name in sys.modules if name == "ml_module" or name.startswith("ml_module.")} == {"ml_module", "ml_module.historical_contracts"}
print(json.dumps({"data_io": 0, "loaded_ml_modules": ["ml_module", "ml_module.historical_contracts"], "code_opens": len(code_opens)}))
'''
    result = subprocess.run(
        [sys.executable, "-B", "-c", probe], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["data_io"] == 0
    assert report["code_opens"] >= 2


@pytest.mark.parametrize("availability", ["known_by_as_of", "unknown"])
def test_exact_label_caller_projection_uses_original_dtos_without_indirect_io(monkeypatch, availability) -> None:
    """兩個 exact import 的使用路徑維持純投影；sealed receipt I/O 屬 app orchestration。"""
    import builtins
    import socket
    import sqlite3
    from app_module import rule_research_label_readiness as reader
    from ml_module.historical_contracts import HistoricalLabelRow, HistoricalLabelSpec

    assert reader.HistoricalLabelRow is HistoricalLabelRow
    assert reader.HistoricalLabelSpec is HistoricalLabelSpec

    def forbidden(*args, **kwargs):
        raise AssertionError("label DTO projection performed I/O")

    with monkeypatch.context() as blocked:
        for owner, name in [(builtins, "open"), (Path, "open"), (Path, "read_bytes"),
                            (Path, "read_text"), (Path, "mkdir"), (sqlite3, "connect"),
                            (socket, "create_connection"), (reader, "read_forward_receipt")]:
            blocked.setattr(owner, name, forbidden)
        spec = reader.HistoricalLabelSpec("gross_h5_bp", "int", "bp", 5,
                                         "missing_is_not_zero_and_excluded",
                                         "sealed_point_available_date_when_declared")
        result = reader._make_label_row(
            receipt_index=0,
            source={"outcome_identity_sha256": "a" * 64, "result_identity_sha256": "b" * 64},
            member={"stock_code": "2330", "method_id": "synthetic", "member_state": "matched"},
            horizon={"calculation_status": "ready_research", "maturity_status": "ready",
                     "expected_end_date": "2026-10-08",
                     "target": {"gross_return": {"integer_bp_half_even": 125}},
                     "input_availability": {"target": {"aggregate_available_date": "2026-10-09",
                                                        "as_of_status": availability}}},
            measure="gross", label_spec=spec, policy_hash="c" * 64, split_hash="d" * 64,
            split={"train_start": "2026-10-01", "train_end": "2026-10-01",
                   "training_as_of": "2026-10-09", "evaluation_start": "2026-10-10",
                   "evaluation_end": "2026-10-20"},
            source_contract={"source_mode": "current_observed", "source_availability": "unknown"},
            projection={"decision_date": "2026-10-01"},
        )
    if availability == "known_by_as_of":
        assert result["historical_label"]["value"] == 125
        assert result["historical_label"]["quality"] == "research_only"
    else:
        assert result["historical_label"] is None
    assert result["value_bp"] == 125
    assert result["temporal_train_candidate"] is False
    assert result["selection_status"] == "unknown"
    assert "source_availability_unknown" in result["reason_codes"]
