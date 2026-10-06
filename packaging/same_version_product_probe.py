"""固定來源與 exe 共用的隔離產品 probe；不修改正式資料或訓練模型。"""
from __future__ import annotations

from dataclasses import asdict, replace
from decimal import Decimal
import json
import os
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace


def _deny_network(event, _args):
    if event in {"socket.connect", "socket.getaddrinfo"}:
        raise PermissionError("same-version fixture 禁止 provider 網路")


def h20_summary(case: Path) -> dict:
    from PySide6.QtWidgets import QApplication
    from app_module.recommendation.personal_h20_product_evidence import PersonalH20ProductEvidence
    from app_module.research_session import ResearchStockContextDTO
    from app_module.stock_research_report_dtos import StockPricePointDTO, StockResearchReportDTO
    from ui_qt.main import apply_app_theme
    from ui_qt.views.stock_research_report_view import StockResearchReportView

    # 日期固定在過去，沿既有 cutoff guard；不 monkeypatch 時鐘或來源校驗。
    evidence = PersonalH20ProductEvidence(
        "2382", "available", "synthetic isolated presentation fixture", 684,
        "2026-10-02", "2026-10-01", "2026-09-30", "2026-10-01T16:42:07+00:00",
        "fixture-model", "fixture-sample", "fixture-prediction",
    )
    saved = case / "h20-presentation-input.json"
    if not saved.exists():
        saved.write_text(json.dumps(asdict(evidence)), encoding="utf-8")
    loaded = PersonalH20ProductEvidence(**json.loads(saved.read_text(encoding="utf-8")))
    assert loaded == evidence
    identity = dict(stock_code="2382", profile_id="fixture-model", source_id="fixture-prediction",
                    decision_date="2026-10-02", data_date="2026-10-01",
                    source_kind="personal_h20_saved_cohort", source_label="隔離 H20 呈現測試",
                    identity_status="personal_research_only", source_workspace="recommendation")
    context = ResearchStockContextDTO(**identity)
    report = StockResearchReportDTO(
        stock_code="2382", as_of="2026-10-02", research_context=identity,
        price_points=(StockPricePointDTO(data_date="2026-10-01", close_price=Decimal("330")),),
    )
    app = QApplication.instance() or QApplication([])
    apply_app_theme(app)
    view = StockResearchReportView(SimpleNamespace(read_report=lambda *args, **kwargs: report), context)
    try:
        journey = runpy.run_path(str(Path(__file__).with_name("portable_journey_probe.py")),
                                 run_name="baldr_h20_worker_wait")
        journey["_wait_for"](app, lambda: view._loaded_report is not None)
        view.set_personal_h20_evidence(loaded)
        assert "+6.84%" in view.summary_focus.conclusion_label.text()
        state_label = view._find_widget("stockResearchLimitations")
        states = state_label.text()
        assert all(text in states for text in ("資料完整度", "資料時效", "模型可用性", "估計日期", "自然結果", "用途"))
        assert "不產生 Advice、權重、勝率或買賣指令" in states
        accepted = {"conclusion": view.summary_focus.conclusion_label.text(),
                    "next_step": view.summary_focus.next_step_label.text(), "states": states}
        view.resize(1400, 800)
        view.show()
        app.processEvents()
        assert state_label.isVisible() and not view.summary_source_group.isVisible()
        screenshot = case / ("h20-exe.png" if getattr(sys, "frozen", False) else "h20-python.png")
        assert view.grab().save(str(screenshot))
        # 錯 cohort 顯示拒絕；合法 unavailable 清除舊值，切股晚到不能回填。
        view._render_report(replace(report, research_context=dict(identity, profile_id="wrong")))
        view.set_personal_h20_evidence(loaded)
        assert view._personal_h20_evidence is None
        rejected = view._find_widget("stockResearchLimitations").text()
        assert "來源不一致" in rejected and "+6.84%" not in view.summary_focus.conclusion_label.text()
        view._render_report(report)
        view.set_personal_h20_evidence(loaded)
        view.set_personal_h20_evidence(replace(loaded, status="unavailable", gross_return_bp=None,
                                             reason="synthetic missing source"))
        unavailable = view.summary_focus.conclusion_label.text()
        assert "+6.84%" not in unavailable
        view._clear_loaded_report()
        view.context = ResearchStockContextDTO(stock_code="2330")
        view.set_personal_h20_evidence(loaded)
        assert "+6.84%" not in view.summary_focus.conclusion_label.text()
        return {"status": "passed", "fixture_kind": "presentation_only_not_canonical_h20_reader",
                "accepted": accepted, "wrong_cohort": rejected, "unavailable": unavailable,
                "late_stock_result_rejected": True, "screenshot": str(screenshot)}
    finally:
        view.close()
        app.processEvents()


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[2] not in {"journey", "model", "h20"}:
        raise ValueError("usage: same_version_product_probe.py <isolated-case> journey|model|h20")
    case = Path(sys.argv[1]).resolve(strict=True)
    if not case.is_dir():
        raise ValueError("隔離 fixture 目錄不存在")
    for name in ("DATA_ROOT", "OUTPUT_ROOT", "RESEARCH_STATE_ROOT", "LOCALAPPDATA"):
        if not Path(os.environ[name]).resolve().is_relative_to(case):
            raise ValueError(f"{name} 必須在隔離 fixture 中")
    sys.addaudithook(_deny_network)
    mode = sys.argv[2]
    scripts = Path(__file__).resolve().parent
    if mode == "journey":
        sys.argv = [str(scripts / "portable_journey_probe.py"), str(case)]
        namespace = runpy.run_path(sys.argv[0], run_name="baldr_isolated_journey")
        result = namespace["_run"](allow_python=True)
    elif mode == "model":
        # 兩個程序讀同一 artifact；spawn 使用各自 PID，避免覆寫前一次證據。
        sys.argv = [str(scripts / "portable_probe.py"), str(case)]
        runpy.run_path(sys.argv[0], run_name="__main__")
        result = json.loads((case / "probe.json").read_text(encoding="utf-8"))
    else:
        result = h20_summary(case)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
