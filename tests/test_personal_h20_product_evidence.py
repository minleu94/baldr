"""公開store產品投影、元資料指標與Qt stale-result防禦；合成資料限定。"""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import MethodType, SimpleNamespace

import pytest

from app_module.recommendation.personal_h20_activation import publish_personal_h20_activation
from app_module.recommendation.personal_h20_product_evidence import (
    PersonalH20ProductEvidence, personal_h20_product_text, project_personal_h20_product_evidence,
    publish_personal_h20_product_reference, read_personal_h20_product_for_stock,
    save_personal_h20_daily_manifest, read_personal_h20_daily_manifest,
    read_personal_h20_product_reference,
)
from tests.test_personal_h20_activation import _activation


def _capture():
    return {"identity": {"symbol": "2330"}, "source_binding": {"decision_date": "2026-09-08", "cycle_id": "cycle",
        "pins": {"cycle_source_date": "2026-09-07"}}, "contract_binding": {
        "candidate_id": "candidate", "contract_hash": "sha256:" + "b" * 64},
        "prediction": {"status": "h20_gross_available", "predicted_gross_return_bp": 123,
            "request": {"symbol": "2330", "feature_as_of_date": "2026-09-07"}, "prediction_id": "prediction"},
        "research_only": True, "historical_pit_eligible": False, "formal_training_allowed": False,
        "production_action_allowed": False, "promotion_credit_created": False,
        "observed_at": "2026-09-08T10:00:00+00:00", "sample_id": "sample"}


def _project(capture=None):
    return project_personal_h20_product_evidence(capture or _capture(), stock_code="2330",
        expected_candidate_id="candidate", expected_contract_hash="sha256:" + "b" * 64)


def _store(tmp_path):
    activation = _activation(tmp_path)
    publish_personal_h20_activation(activation, expected_revision=0, execute=True)
    root = Path(activation.personal_root)
    prediction = root / "h20_predictions" / "sample.json"
    prediction.parent.mkdir()
    prediction.write_text(json.dumps(_capture()), encoding="utf-8")
    pin = "sha256:" + hashlib.sha256(prediction.read_bytes()).hexdigest()
    result = {"status": "completed", "candidate_id": "candidate",
        "contract_hash": activation.model_contract_hash, "cycle_id": "cycle", "decision_date": "2026-09-08",
        "captures": [{"symbol": "2330", "path": str(prediction), "raw_sha256": pin}]}
    def raw_reader(path, *, root, expected_sha256):
        file = Path(path)
        assert file.is_relative_to(root)
        assert "sha256:" + hashlib.sha256(file.read_bytes()).hexdigest() == expected_sha256
        return json.loads(file.read_bytes())

    daily, raw, body = save_personal_h20_daily_manifest(activation, result,
        expected_symbols=["2330"], prediction_reader=raw_reader)
    publish_personal_h20_product_reference(activation, receipt_path=str(daily), receipt_sha256=raw,
        decision_date="2026-09-08", cycle_id="cycle")
    def pinned_reader(path, *, root, expected_sha256, selected_stock=None):
        if Path(path).parent == root / "h20_daily_receipts":
            return read_personal_h20_daily_manifest(path, root=root, expected_sha256=expected_sha256,
                selected_stock=selected_stock, prediction_reader=raw_reader)
        return raw_reader(path, root=root, expected_sha256=expected_sha256)

    return activation, prediction, daily, pinned_reader


def test_manifest_full_scope_and_create_only_replay_do_not_create_extra_sample(tmp_path):
    activation, prediction, daily, reader = _store(tmp_path)
    before = daily.read_bytes()
    body = json.loads(before)
    result = dict(body)
    path, pin, manifest = save_personal_h20_daily_manifest(activation, result,
        expected_symbols=["2330"], prediction_reader=reader)
    assert path == daily
    assert daily.read_bytes() == before
    assert pin == "sha256:" + hashlib.sha256(before).hexdigest()
    with pytest.raises(ValueError, match="full_scope_required"):
        save_personal_h20_daily_manifest(activation, result,
            expected_symbols=["2330", "1101"], prediction_reader=reader)
    with pytest.raises(ValueError, match="full_scope_required"):
        save_personal_h20_daily_manifest(activation, dict(result, status="cancelled"),
            expected_symbols=["2330"], prediction_reader=reader)
    assert list((Path(activation.personal_root) / "h20_daily_receipts").glob("*.json")) == [daily]
    assert list(prediction.parent.glob("*.json")) == [prediction]


def test_cohort_reference_preserves_original_pins_and_readonly_bytes(tmp_path):
    activation, prediction, daily, _ = _store(tmp_path)
    root = Path(activation.personal_root)
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}
    selected = read_personal_h20_product_reference(activation.config_path,
        market_root=Path(activation.market_root))
    assert selected.activation == activation
    assert selected.manifest_path == daily
    assert selected.manifest_sha256 == "sha256:" + hashlib.sha256(daily.read_bytes()).hexdigest()
    assert (selected.cycle_id, selected.decision_date) == ("cycle", "2026-09-08")
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}


def test_background_cohort_reads_original_full_manifest_and_rejects_pointer_change(tmp_path, monkeypatch):
    from scripts.scheduled import personal_h20_daily_hook as hook
    activation, _, daily, reader = _store(tmp_path)
    from copy import deepcopy
    monkeypatch.setattr(hook, "_personal_h20_read_ports", lambda: {
        "source_verifier": deepcopy, "contract_verifier": deepcopy,
    })
    monkeypatch.setattr(hook, "_read_personal_h20_prediction_with_verifiers",
        lambda path, *, root, expected_sha256, source_verifier, contract_verifier:
            reader(path, root=root, expected_sha256=expected_sha256))
    reference, cohort = hook.read_personal_h20_product_cohort(activation.config_path,
        market_root=Path(activation.market_root))
    assert cohort.symbols == ("2330",) and cohort.rows[0].gross_return_bp == 123
    assert reference.manifest_path == daily
    def changed_reader(*args, **kwargs):
        result = reader(*args, **kwargs)
        pointer = Path(activation.personal_root) / "h20_product_reference.json"
        body = json.loads(pointer.read_bytes())
        body["cycle_id"] = "changed-cycle"
        pointer.write_text(json.dumps(body), encoding="utf-8")
        return result
    monkeypatch.setattr(hook, "_read_personal_h20_prediction_with_verifiers",
        lambda path, *, root, expected_sha256, source_verifier, contract_verifier:
            changed_reader(path, root=root, expected_sha256=expected_sha256))
    with pytest.raises(ValueError, match="cohort_reference_changed"):
        hook.read_personal_h20_product_cohort(activation.config_path, market_root=Path(activation.market_root))


@pytest.mark.parametrize("field,value", [("candidate_id", "other"), ("activation_revision", 2),
    ("receipt_sha256", "sha256:" + "f" * 64), ("decision_date", "unknown")])
def test_cohort_reference_rejects_cross_model_revision_manifest_or_clock(tmp_path, field, value):
    activation, _, _, _ = _store(tmp_path)
    pointer = Path(activation.personal_root) / "h20_product_reference.json"
    body = json.loads(pointer.read_bytes())
    body[field] = value
    pointer.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(ValueError):
        read_personal_h20_product_reference(activation.config_path, market_root=Path(activation.market_root))


def test_product_reference_reads_original_capture_and_tamper_does_not_surface(tmp_path):
    activation, prediction, daily, reader = _store(tmp_path)
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in Path(activation.personal_root).rglob("*") if p.is_file()}
    kwargs = dict(stock_code="2330", market_root=Path(activation.market_root), daily_reader=reader, prediction_reader=reader)
    evidence = read_personal_h20_product_for_stock(activation.config_path, **kwargs)
    assert evidence == _project()
    assert "+1.23%（123 bp）" in personal_h20_product_text(evidence)
    assert "來源日 2026-09-07" in personal_h20_product_text(evidence)
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in Path(activation.personal_root).rglob("*") if p.is_file()} == before
    changed = json.loads(prediction.read_bytes())
    changed["prediction"]["predicted_gross_return_bp"] = 9999
    prediction.write_text(json.dumps(changed), encoding="utf-8")
    assert read_personal_h20_product_for_stock(activation.config_path, **kwargs).status == "unavailable"


def test_disable_skips_all_reader_ports_and_keeps_saved_prediction(tmp_path):
    activation, prediction, daily, reader = _store(tmp_path)
    before = prediction.read_bytes()
    rollback = replace(activation, revision=2, enabled=False)
    publish_personal_h20_activation(rollback, expected_revision=1, execute=True)
    def forbidden(*a, **k):
        pytest.fail("disabled called producer/public reader")
    evidence = read_personal_h20_product_for_stock(activation.config_path, stock_code="2330",
        market_root=Path(activation.market_root), daily_reader=forbidden, prediction_reader=forbidden)
    assert evidence.status == "disabled"
    assert prediction.read_bytes() == before


def test_product_wrong_stock_model_clock_and_qualification_are_rejected():
    for field, value in [("formal_training_allowed", True), ("observed_at", "2026-09-08T10:00:00")]:
        payload = _capture()
        payload[field] = value
        with pytest.raises(ValueError):
            _project(payload)
    payload = _capture()
    payload["identity"]["symbol"] = "1101"
    with pytest.raises(ValueError):
        _project(payload)
    payload = _capture()
    payload["contract_binding"]["contract_hash"] = "wrong-model"
    with pytest.raises(ValueError):
        _project(payload)


def test_view_shows_exact_bp_and_clears_other_stock_future_and_failed_refresh(tmp_path):
    from tests.test_ui_qt_stock_research_report import _app, _real_service
    from app_module.research_session import ResearchStockContextDTO
    from ui_qt.views.stock_research_report_view import StockResearchReportView
    app = _app()
    service = _real_service(tmp_path)
    report = service.read_report("2330")
    view = StockResearchReportView(service)
    context = ResearchStockContextDTO(stock_code="2330", source_workspace="workbench")
    view.context = context
    view._loaded_request_context = context
    view._render_report(report)
    view.set_personal_h20_evidence(_project())
    assert "+1.23%（123 bp）" in view.personal_h20_label.text()
    before = view.personal_h20_label.text()
    view.set_personal_h20_evidence(replace(_project(), stock_code="1101"))
    assert view.personal_h20_label.text() == before
    view.set_personal_h20_evidence(replace(_project(), decision_date="2026-09-09"))
    assert view.personal_h20_label.text() == before
    view._show_last_good_state(report, conclusion="失敗", reason="來源無法核驗", next_step="重試")
    assert "舊預測" in view.personal_h20_label.text()
    assert "123 bp" not in view.personal_h20_label.text()
    view._clear_loaded_report()
    assert "等待" in view.personal_h20_label.text()
    view.close()
    app.processEvents()


def test_main_background_result_requires_current_report_generation(tmp_path, monkeypatch):
    from tests.test_ui_qt_stock_research_report import _app, _real_service
    from app_module.research_session import ResearchStockContextDTO
    from ui_qt.main import MainWindow
    import ui_qt.workers.task_worker as workers
    app = _app()
    report = _real_service(tmp_path).read_report("2330")
    accepted = []
    view = SimpleNamespace(_loaded_request_context=ResearchStockContextDTO(stock_code="2330"),
        _loaded_report=report, _closing=False, set_personal_h20_evidence=accepted.append,
        personal_h20_label=SimpleNamespace(setText=lambda text: None))
    class Signal:
        def __init__(self): self.callbacks = []
        def connect(self, callback): self.callbacks.append(callback)
        def emit(self, result):
            for callback in self.callbacks: callback(result)
    class Worker:
        def __init__(self, fn, *a, **k):
            self.finished, self.native_thread_finished = Signal(), Signal()
            self.fn, self.args, self.kwargs = fn, a, k
        def start(self): pass
        def isRunning(self): return True
        def cancel(self, **kwargs): pass
        def deleteLater(self): pass
    monkeypatch.setattr(workers, "TaskWorker", Worker)
    window = SimpleNamespace(stock_research_workspace=SimpleNamespace(report_view=view),
        config=SimpleNamespace(data_root=tmp_path), _shutdown_close_requested=False)
    window._clear_personal_h20_product = MethodType(MainWindow._clear_personal_h20_product, window)
    MainWindow._load_personal_h20_product(window, report)
    first = window._personal_h20_worker
    first.finished.emit(_project())
    assert accepted == [_project()]
    MainWindow._clear_personal_h20_product(window)
    first.finished.emit(_project())
    assert accepted == [_project()]
    MainWindow._load_personal_h20_product(window, report)
    window._shutdown_close_requested = True
    window._personal_h20_worker.finished.emit(_project())
    assert accepted == [_project()]
    app.processEvents()
