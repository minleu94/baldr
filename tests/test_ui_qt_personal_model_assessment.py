from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog

from ui_qt.views.recommendation_view import RecommendationView


RESULT_ID = "rec_03ae4c2c3e0344a7ae26d8646107c851"
M11_OUTPUT_ROOT = (
    Path("output/qa/personal_daily_product_20261006/personal_research_ui/m11/output/_test")
)
M11_CAPTURE = (
    M11_OUTPUT_ROOT
    / "personal_prediction/captures/"
    "ad981904a1717affda64c1a787aa95c7602156344a67a6521dd0ff3c23b8ac28.json"
)
M11_SUMMARY = (
    Path("output/qa/s11/m11_20260928T1713Z/personal_natural_outcomes/runs/")
    / "6fbe8be50f7bf20490a040a279d9265f09ccfef071c69e3defee21278d27b667.json"
)


class _ReadOnlyOutputConfig:
    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root

    def resolve_output_path(self, subfolder: str) -> Path:
        return self.output_root / subfolder


@pytest.fixture(scope="module")
def qt_app():
    application = QApplication.instance() or QApplication([])
    yield application


def _make_view(output_root: Path, journal_path: Path) -> RecommendationView:
    view = RecommendationView(
        recommendation_service=MagicMock(),
        regime_service=SimpleNamespace(
            detect_regime=lambda: SimpleNamespace(regime="Unknown"),
            get_strategy_config=lambda _regime: {},
        ),
        personal_policy_path=journal_path.parent / "unused-policy.json",
    )
    view.config = _ReadOnlyOutputConfig(output_root)
    view.journal_service = SimpleNamespace(
        store=SimpleNamespace(journal_file=journal_path)
    )
    view.load_saved_result_button.setEnabled(True)
    return view


def _wait_for(qt_app: QApplication, predicate, timeout_ms: int = 30_000) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        qt_app.processEvents()
        if predicate():
            return
        QTest.qWait(10)
    qt_app.processEvents()
    assert predicate()


def _load_exact_result(view: RecommendationView, qt_app: QApplication) -> None:
    view.saved_result_id_input.setText(RESULT_ID)
    view.load_saved_result_button.click()
    _wait_for(qt_app, lambda: view._verified_saved_result_id() == RESULT_ID)


def _select_sources(
    view: RecommendationView,
    monkeypatch: pytest.MonkeyPatch,
    capture_path: Path,
    summary_path: Path,
) -> None:
    def choose_file(_parent, caption, *_args, **_kwargs):
        if "capture" in str(caption).lower():
            return str(capture_path), "JSON 檔案 (*.json)"
        return str(summary_path), "JSON 檔案 (*.json)"

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        staticmethod(choose_file),
    )
    view.personal_model_assessment_capture_button.click()
    view.personal_model_assessment_summary_button.click()


def _read_assessment(view: RecommendationView, qt_app: QApplication) -> None:
    view.personal_model_assessment_read_button.click()
    worker = view._personal_model_assessment_worker
    assert worker is not None
    assert worker.wait(30_000)
    _wait_for(
        qt_app,
        lambda: not view.personal_model_assessment_status_label.text().startswith(
            "正在唯讀核驗"
        ),
    )
    _wait_for(qt_app, lambda: view._personal_model_assessment_worker is None)


def test_recommendation_view_exact_m11_pending_readback_cold_restart_and_mismatch(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真 RecommendationView 以明選檔讀回 m11；只讀、跨冷啟動且錯配拒絕。"""

    capture = (Path.cwd() / M11_CAPTURE).resolve()
    summary = (Path.cwd() / M11_SUMMARY).resolve()
    output_root = (Path.cwd() / M11_OUTPUT_ROOT).resolve()
    if not capture.is_file() or not summary.is_file():
        pytest.skip("本機 m11 Stage C 唯讀驗收來源未提供")

    before_inputs = {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (capture, summary)
    }
    journal_path = tmp_path / "readonly-journal.jsonl"
    first_view = _make_view(output_root, journal_path)
    cold_view: RecommendationView | None = None
    try:
        _load_exact_result(first_view, qt_app)
        assert first_view.personal_model_assessment_capture_path.text() == ""
        assert first_view.personal_model_assessment_summary_path.text() == ""
        assert "尚未執行評估" in first_view.personal_model_assessment_status_label.text()
        assert first_view.personal_model_assessment_details.toPlainText() == ""

        _select_sources(first_view, monkeypatch, capture, summary)
        assert str(capture) in first_view.personal_model_assessment_capture_path.text()
        assert str(summary) in first_view.personal_model_assessment_summary_path.text()
        _read_assessment(first_view, qt_app)
        first_status = first_view.personal_model_assessment_status_label.text()
        first_details = first_view.personal_model_assessment_details.toPlainText()
        assert "已成熟 0 筆／待觀察 19 筆" in first_status
        payload = json.loads(first_details)
        assert payload["result_id"] == RESULT_ID
        assert payload["evidence_status"] == "pending"
        assert payload["matured_sample_count"] == 0
        assert payload["pending_sample_count"] == 19
        assert payload["metrics"]["model_brier_bp"] is None
        assert payload["metrics"]["fixed_null_benchmark_brier_bp"] is None
        assert payload["after_cost"]["status"] == "unavailable"
        assert payload["scope"]["is_execution_pnl"] is False
        assert payload["identity"]["source_time_trust"]["research_only"] is True
        assert payload["identity"]["source_time_trust"][
            "official_historical_pit_verified"
        ] is False
        assert first_view.personal_model_assessment_read_button.isEnabled()
    finally:
        first_view.close()
        qt_app.processEvents()

    # A new RecommendationView re-loads only the caller-named canonical result;
    # no previous summary selection or in-memory assessment is reused.
    cold_view = _make_view(output_root, journal_path)
    try:
        _load_exact_result(cold_view, qt_app)
        assert "尚未執行評估" in cold_view.personal_model_assessment_status_label.text()
        assert cold_view.personal_model_assessment_capture_path.text() == ""
        assert cold_view.personal_model_assessment_summary_path.text() == ""
        _select_sources(cold_view, monkeypatch, capture, summary)
        _read_assessment(cold_view, qt_app)
        assert cold_view.personal_model_assessment_details.toPlainText() == first_details

        from app_module.personalization_read_service import _stage_c_payload_hash

        forged = json.loads(summary.read_text(encoding="utf-8"))
        matching_rows = [
            row
            for row in forged["captures"]
            if row.get("result_id") == RESULT_ID
            and Path(row.get("capture_path", "")).resolve() == capture
        ]
        assert len(matching_rows) == 1
        matching_rows[0]["capture_id"] = "sha256:" + ("0" * 64)
        forged.pop("payload_sha256")
        forged["payload_sha256"] = _stage_c_payload_hash(forged)
        forged_path = (
            tmp_path
            / "personal_natural_outcomes"
            / "runs"
            / f"{forged['payload_sha256'][7:]}.json"
        )
        forged_path.parent.mkdir(parents=True, exist_ok=True)
        forged_path.write_text(
            json.dumps(
                forged,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        cold_view.personal_model_assessment_summary_path.clear()
        cold_view.personal_model_assessment_summary_path.setText(str(forged_path))
        assert cold_view.personal_model_assessment_details.toPlainText() == ""
        _read_assessment(cold_view, qt_app)
        assert cold_view.personal_model_assessment_details.toPlainText() == ""
        assert "拒絕顯示" in cold_view.personal_model_assessment_status_label.text()
        assert "沒有唯一一筆對應" in (
            cold_view.personal_model_assessment_status_label.text()
        )
    finally:
        cold_view.close()
        qt_app.processEvents()

    assert {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (capture, summary)
    } == before_inputs
    assert not journal_path.exists()


def test_recommendation_view_assessment_ui_state_guards_are_self_contained(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """隔離 Qt UI 邊界測試；stub 投影不代表自然資料或 Stage C 讀回。"""

    active_result = {"id": "ui-boundary-saved-result-1"}
    entered_read = threading.Event()
    release_read = threading.Event()
    read_calls: list[tuple[str, str, str, str]] = []

    class Assessment:
        def __init__(self, result_id: str) -> None:
            self.result_id = result_id
            self.capture_id = "ui-boundary-capture-1"
            self.assessment_status = "insufficient_data"
            self.evidence_status = "pending"
            self.recommendation = "insufficient_data"
            self.reason = "fixture_pending"
            self.identity = {
                "result_id": result_id,
                "capture_id": self.capture_id,
                "daily_summary_payload_sha256": "sha256:" + ("1" * 64),
                "source_time_trust": {
                    "research_only": True,
                    "official_historical_pit_verified": False,
                },
            }
            self.scope = {"is_execution_pnl": False}
            self.matured_sample_count = 0
            self.pending_sample_count = 19
            self.metrics = {"model_brier_bp": None}
            self.after_cost = {"status": "unavailable"}
            self.missing_evidence = ("fixture_missing",)
            self.next_steps = ("fixture_next_step",)
            self.diagnostics = ()
            self.read_only = True
            self.writes_allowed = False
            self.auto_switch = False

        def to_dict(self) -> dict[str, object]:
            return {
                "result_id": self.result_id,
                "capture_id": self.capture_id,
                "evidence_status": self.evidence_status,
                "matured_sample_count": self.matured_sample_count,
                "pending_sample_count": self.pending_sample_count,
                "identity": self.identity,
                "scope": self.scope,
                "metrics": self.metrics,
                "after_cost": self.after_cost,
            }

    class ReadService:
        def read_personal_model_assessment(
            self,
            result_id: str,
            capture_path: str,
            personal_root: Path,
            summary_path: str,
        ):
            read_calls.append(
                (result_id, capture_path, str(personal_root), summary_path)
            )
            if summary_path.endswith("mismatch.json"):
                raise ValueError("Stage C summary must contain exactly one matching capture")
            if summary_path.endswith("slow.json"):
                entered_read.set()
                release_read.wait(timeout=10)
            return Assessment(result_id)

    journal_path = tmp_path / "nonexistent-journal.jsonl"
    view = _make_view(tmp_path / "output", journal_path)
    monkeypatch.setattr(
        view,
        "_verified_saved_result_id",
        lambda: active_result["id"],
    )
    monkeypatch.setattr(view, "_personalization_read_service", lambda: ReadService())
    try:
        view._refresh_personal_model_assessment_controls()
        capture_path = tmp_path / "capture.json"
        summary_path = tmp_path / "summary.json"
        view.personal_model_assessment_capture_path.setText(str(capture_path))
        view.personal_model_assessment_summary_path.setText(str(summary_path))
        view._read_personal_model_assessment()
        worker = view._personal_model_assessment_worker
        assert worker is not None and worker.wait(10_000)
        _wait_for(qt_app, lambda: view._personal_model_assessment_worker is None)
        assert "已成熟 0 筆／待觀察 19 筆" in (
            view.personal_model_assessment_status_label.text()
        )
        assert json.loads(view.personal_model_assessment_details.toPlainText())[
            "result_id"
        ] == active_result["id"]
        assert read_calls[-1] == (
            active_result["id"],
            str(capture_path),
            str((tmp_path / "output" / "personal_prediction").resolve()),
            str(summary_path),
        )

        mismatch_path = tmp_path / "mismatch.json"
        view.personal_model_assessment_summary_path.setText(str(mismatch_path))
        assert view.personal_model_assessment_details.toPlainText() == ""
        view._read_personal_model_assessment()
        worker = view._personal_model_assessment_worker
        assert worker is not None and worker.wait(10_000)
        _wait_for(qt_app, lambda: view._personal_model_assessment_worker is None)
        assert "拒絕顯示" in view.personal_model_assessment_status_label.text()
        assert "沒有唯一一筆對應" in view.personal_model_assessment_status_label.text()
        assert view.personal_model_assessment_details.toPlainText() == ""

        slow_path = tmp_path / "slow.json"
        view.personal_model_assessment_summary_path.setText(str(slow_path))
        view._read_personal_model_assessment()
        worker = view._personal_model_assessment_worker
        assert worker is not None
        assert entered_read.wait(timeout=5)
        active_result["id"] = "ui-boundary-saved-result-2"
        view._refresh_personal_model_assessment_controls()
        assert view.personal_model_assessment_capture_path.text() == ""
        assert view.personal_model_assessment_summary_path.text() == ""
        assert "ui-boundary-saved-result-2" in (
            view.personal_model_assessment_status_label.text()
        )
        release_read.set()
        assert worker.wait(10_000)
        _wait_for(qt_app, lambda: view._personal_model_assessment_worker is None)
        assert view.personal_model_assessment_details.toPlainText() == ""
        assert "尚未執行評估" in view.personal_model_assessment_status_label.text()
        assert "ui-boundary-saved-result-2" in (
            view.personal_model_assessment_status_label.text()
        )
    finally:
        release_read.set()
        view.close()
        qt_app.processEvents()
