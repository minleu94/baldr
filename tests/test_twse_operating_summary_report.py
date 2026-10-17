"""合成單元測試只驗解析／port與隔離；真來源接受另留具名QA。"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import csv

import pytest

import app_module.twse_operating_summary_report_provider as provider_module
from app_module.stock_research_report_service import StockResearchReportReadService
from app_module.twse_operating_summary_report_provider import OperatingSummaryReportProvider
from app_module.twse_operating_summary_snapshot import (
    OperatingSummaryError, OperatingSummaryPin, OperatingSummaryRead, _FIELDS,
    _acceptance, _values,
)

_NOW = datetime(2026, 10, 17, 15, tzinfo=ZoneInfo("Asia/Taipei"))


def _raw(*, code: str = "2330", quarter: str = "2", revenue: str = "2404483.69") -> bytes:
    stream = StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(_FIELDS)
    writer.writerow(("1151017", "115", quarter, code, "台積電", revenue, "67.03", "59.29", "64.47", "53.22"))
    for number in range(1054):
        writer.writerow(("1151017", "115", "2", str(100000 + number), "合成隔離", "", "", "", "", ""))
    return stream.getvalue().encode("utf-8-sig")


def test_exact_decimal_scale_and_all_four_margin_units() -> None:
    values = _values(_raw())
    assert values[0][2:] == (Decimal("2404483690000.00"), "TWD")
    assert tuple(item[2] for item in values[1:]) == tuple(map(Decimal, ("67.03", "59.29", "64.47", "53.22")))
    assert all(item[3] == "percent" for item in values[1:])


@pytest.mark.parametrize("changes", ({"code": "2317"}, {"quarter": "1"}, {"revenue": "NaN"}, {"revenue": "Infinity"}))
def test_unreviewed_identity_basis_or_nonfinite_amount_refused(changes: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        _values(_raw(**changes))


def test_duplicate_issuer_and_changed_unit_schema_refused() -> None:
    raw = _raw()
    duplicate = raw.replace(b'100000', b'2330', 1)
    with pytest.raises(OperatingSummaryError, match="唯一"):
        _values(duplicate)
    with pytest.raises(OperatingSummaryError, match="schema"):
        _values(raw.replace("百萬元".encode(), "千元".encode(), 1))


@pytest.fixture
def provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> OperatingSummaryReportProvider:
    pin = OperatingSummaryPin(tmp_path, "a" * 64, "b" * 64)
    result = OperatingSummaryRead(pin, _acceptance(_NOW), _NOW, _values(_raw()))
    monkeypatch.setattr(provider_module, "read_operating_summary_snapshot", lambda candidate, *, cutoff_at: result)
    return OperatingSummaryReportProvider(pin)


def test_provider_preserves_original_values_source_scope_and_no_pit(provider: OperatingSummaryReportProvider) -> None:
    rows, sources = provider.read("2330", observed_at=_NOW)
    assert len(rows) == 5 and len(sources) == 1
    assert rows[0].value == Decimal("2404483690000.00")
    assert all(row.period == "2026-H1" and row.basis_verified for row in rows)
    assert all(not row.aggregate_feature_eligible and not row.formal_pit_eligible for row in rows)
    assert all(row.announced_date == "" for row in rows)
    assert sources[0].current_observed_only and sources[0].historical_pit_eligible is False
    assert any("政府資料開放" in text for text in sources[0].limitations)
    assert any("前期" in text for text in sources[0].limitations)
    assert provider.read("2317", observed_at=_NOW) == ((), ())


@pytest.mark.parametrize("reason", ("SHA不符", "尚未到可用小時", "批次仍pending"))
def test_bad_source_isolated_without_fabricated_values(
    provider: OperatingSummaryReportProvider, monkeypatch: pytest.MonkeyPatch, reason: str,
) -> None:
    def broken(*args: object, **kwargs: object) -> None:
        raise OperatingSummaryError(reason)
    monkeypatch.setattr(provider_module, "read_operating_summary_snapshot", broken)
    rows, sources = provider.read("2330", observed_at=_NOW)
    assert not rows and sources[0].status == "unavailable"
    assert reason in sources[0].limitations[0]


def test_partial_environment_has_explainable_unavailable_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPERATING_SUMMARY_SNAPSHOT_DIRECTORY", str(tmp_path))
    monkeypatch.delenv("OPERATING_SUMMARY_MANIFEST_SHA256", raising=False)
    monkeypatch.delenv("OPERATING_SUMMARY_RECEIPT_SHA256", raising=False)
    rows, sources = OperatingSummaryReportProvider.from_environment().read("2330", observed_at=_NOW)
    assert not rows and "雙SHA" in sources[0].limitations[0]


def test_original_report_port_current_only_and_reopen(
    provider: OperatingSummaryReportProvider, tmp_path: Path,
) -> None:
    config = SimpleNamespace(output_root=tmp_path / "output")
    for _ in range(2):
        service = StockResearchReportReadService(config, clock=lambda: _NOW, operating_summary_provider=provider)
        rows, sources, _ = service._read_fundamentals("2330", _NOW.date(), include_current=True)
        official = tuple(row for row in rows if row.source_id.startswith("official.twse.operating_summary"))
        assert len(official) == 5 and official[0].value == Decimal("2404483690000.00")
        historical, _, _ = service._read_fundamentals("2330", _NOW.date(), include_current=False)
        assert not any(row.source_id.startswith("official.twse.operating_summary") for row in historical)
    assert not (tmp_path / "output").exists()


def test_original_fundamental_page_shows_values_attribution_and_missing_prior(
    provider: OperatingSummaryReportProvider,
) -> None:
    from PySide6.QtWidgets import QApplication, QLabel, QTableView
    from app_module.stock_research_report_dtos import StockResearchReportDTO
    from ui_qt.views.stock_research_report_view import StockResearchReportView
    app = QApplication.instance() or QApplication([])
    rows, sources = provider.read("2330", observed_at=_NOW)
    view = StockResearchReportView(SimpleNamespace())
    try:
        view._render_fundamental(StockResearchReportDTO(stock_code="2330", fundamentals=rows, sources=sources))
        labels = "\n".join(label.text() for label in view.findChildren(QLabel))
        assert "只接受2330、2026上半年" in labels and "前期比較缺同用途來源" in labels
        assert "政府資料開放授權條款第1版" in labels
        tables = [table for table in view.findChildren(QTableView) if table.model() is not None and table.model().rowCount() == 5]
        assert len(tables) == 1
        model = tables[0].model()
        values = [model.data(model.index(row, 6)) for row in range(5)]
        assert "2,404,483,690,000" in values[0]
        assert "67.03" in values[1]
        app.processEvents()
    finally:
        view.close()
