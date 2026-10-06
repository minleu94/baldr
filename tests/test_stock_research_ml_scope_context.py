"""個股研究的 ML 範圍切換保留保存來源與日期契約。"""

from types import SimpleNamespace

import pytest

from app_module.research_session import ResearchSessionStore, ResearchStockContextDTO
from ui_qt.views.stock_research_report_view import _read_report_with_context_cutoff


def _saved_context(**updates: str) -> ResearchStockContextDTO:
    values = {
        "stock_code": "1477",
        "stock_name": "聚陽",
        "decision_date": "2026-09-23",
        "data_date": "2026-09-22",
        "result_id": "rec-1477-exact",
        "identity_status": "linked",
        "source_snapshot_id": "snapshot-1477",
        "source_snapshot_hash": "sha256:" + "a" * 64,
        "source_id": "rec-1477-exact",
        "source_kind": "recommendation",
        "source_label": "已保存篩選紀錄／未入選",
        "source_workspace": "recommendation",
        "ml_scope_mode": "selected_saved_decision",
    }
    values.update(updates)
    return ResearchStockContextDTO(**values)


def test_current_research_scope_keeps_saved_identity_in_session_store() -> None:
    store = ResearchSessionStore()
    saved = _saved_context()

    saved_snapshot = store.set_stock_context(saved, source="test")
    assert saved_snapshot.stock_context == saved
    assert saved_snapshot.result_id == saved.result_id
    assert saved_snapshot.ml_scope_mode == "selected_saved_decision"

    current = _saved_context(ml_scope_mode="current_stock_research")
    current_snapshot = store.set_stock_context(current, source="test")
    assert current_snapshot.stock_context == current
    assert current_snapshot.result_id == saved.result_id
    assert current_snapshot.decision_date == saved.decision_date
    assert current_snapshot.source_snapshot_hash == saved.source_snapshot_hash
    assert current_snapshot.ml_scope_mode == "current_stock_research"

    restored = store.set_stock_context(saved, source="test")
    assert restored.stock_context == saved
    assert restored.ml_scope_mode == "selected_saved_decision"


def test_research_context_rejects_unknown_ml_scope() -> None:
    with pytest.raises(ValueError, match="ml_scope_mode"):
        _saved_context(ml_scope_mode="latest")


def test_report_cutoff_is_current_for_explicit_current_scope_and_pit_for_saved_scope() -> None:
    class CaptureService:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        def read_report(self, stock_code: str, **kwargs: object) -> object:
            self.calls.append((stock_code, kwargs))
            return SimpleNamespace(stock_code=stock_code)

    service = CaptureService()
    current = _saved_context(ml_scope_mode="current_stock_research")
    _read_report_with_context_cutoff(service, "1477", context=current)
    assert service.calls[-1][0] == "1477"
    assert service.calls[-1][1]["as_of_date"] is None
    assert service.calls[-1][1]["context"] == current

    saved = _saved_context(ml_scope_mode="selected_saved_decision")
    _read_report_with_context_cutoff(service, "1477", context=saved)
    assert service.calls[-1][1]["as_of_date"] == "2026-09-23"
    assert service.calls[-1][1]["context"] == saved
