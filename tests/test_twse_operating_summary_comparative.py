"""比較版本的時鐘、精度、來源與報告綁定；真PDF另由Root具名核對。"""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal, localcontext
from hashlib import sha256
from types import SimpleNamespace

import pytest

from app_module import twse_operating_summary_snapshot as base
from app_module import twse_operating_summary_reviewed as reviewed
from app_module.twse_operating_summary_report_provider import OperatingSummaryReportProvider
from app_module.stock_research_report_dtos import StockResearchReportDTO
from test_twse_operating_summary_reviewed import snapshot, NOW


@pytest.fixture
def comparative(snapshot, tmp_path, monkeypatch):
    # 沿原fixture假定已核base；此處不宣稱合成bytes具有真來源資格。
    amounts = {
        "2317": ("1000", ["4645427824", "285513881", "170451721", "168897620", "127012192"],
            ["3437783609", "214077423", "103096179", "124269767", "95370317"]),
        "2330": ("1000000", ["2404484", "1611606", "1425569", "1550230", "1279582"],
            ["1773046", "1040764", "870504", "923931", "758226"]),
        "2454": ("1000", ["301333121", "139362969", "45758626", "54981079", "48981437"],
            ["303680808", "147687142", "59432264", "67780766", "57593358"]),
    }
    facts = {"schema_version": "issuer-half-year-comparative-facts.2026h1.v1", "period": "2026-H1", "prior_period": "2025-H1",
        "metrics": ["net_revenue", "gross_profit", "operating_profit", "pretax_profit", "net_profit"],
        "pdf_redistributed": False, "historical_pit_eligible": False, "issuers": {}}
    for code, (unit, current, prior) in amounts.items():
        facts["issuers"][code] = {"stock_name": reviewed.REVIEWED_COMPANIES[code], "unit_twd": unit,
            "current_amounts": current, "prior_amounts": prior, "official_url": reviewed._REVIEWS[code]["url"],
            "pdf_sha256": reviewed._REVIEWS[code]["pdf_sha256"], "profit_basis": "consolidated_total_profit_not_parent_attributable",
            "official_announcement_time_verified": False}
    raw = base._bytes(facts)
    monkeypatch.setattr(reviewed, "COMPARATIVE_FACTS_SHA256", sha256(raw).hexdigest())
    monkeypatch.setattr(reviewed, "COMPARATIVE_NOT_BEFORE", NOW + timedelta(hours=1))
    source = tmp_path / "facts.json"
    source.write_bytes(raw)
    clock = NOW + timedelta(hours=2)
    pin = reviewed.seal_comparative_operating_summary_snapshot(snapshot.pin, facts_path=source,
        output_directory=tmp_path / "comparison", clock=lambda: clock)
    return SimpleNamespace(pin=pin, source=source, raw=raw, facts=facts, parent=snapshot,
        waiting=clock, available=clock.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))


@pytest.mark.parametrize("code,revenue,gross,change", [
    ("2317", "3437783609000", "6.23", "35.13"),
    ("2330", "1773046000000", "58.70", "35.61"),
    ("2454", "303680808000", "48.63", "-0.77"),
])
def test_same_half_year_precision_and_independent_expected_values(comparative, code, revenue, gross, change):
    provider = OperatingSummaryReportProvider(comparative.pin)
    rows, current_sources = provider.read(code, observed_at=comparative.available)
    pairs, sources = provider.read_comparisons(code, observed_at=comparative.available)
    assert len(rows) == len(pairs) == 5
    assert pairs[0].prior_value == Decimal(revenue) and pairs[1].prior_value == Decimal(gross)
    assert pairs[0].change_value == Decimal(change)
    assert pairs[0].change_unit == "percent" and all(pair.change_unit == "percentage_point" for pair in pairs[1:])
    assert all(pair.current_period == "2026-H1" and pair.prior_period == "2025-H1" for pair in pairs)
    assert all(pair.current_observed_only and not pair.historical_pit_eligible and not pair.aggregate_feature_eligible for pair in pairs)
    report = StockResearchReportDTO(stock_code=code, fundamentals=rows, sources=current_sources + sources, fundamental_comparisons=pairs)
    assert report.to_dict()["fundamental_comparisons"][0]["change_value"] == change
    assert comparative.source.read_bytes() == comparative.raw
    assert (comparative.pin.directory / "comparative_facts.json").read_bytes() == comparative.raw
    assert all((comparative.pin.directory / "current/base" / name).read_bytes() == raw for name, raw in comparative.parent.files.items())


def test_waiting_new_comparison_keeps_already_available_current_five(comparative):
    provider = OperatingSummaryReportProvider(comparative.pin)
    current, _ = provider.read("2330", observed_at=comparative.waiting)
    prior, sources = provider.read_comparisons("2330", observed_at=comparative.waiting)
    assert len(current) == 5 and current[0].value == Decimal("2404483690000.00")
    assert not prior and sources[0].status == "unavailable" and "可用小時" in sources[0].limitations[0]
    assert current[0].available_at != comparative.available.isoformat()


def test_base_v1_does_not_silently_gain_comparison_and_quanta_stays_unavailable(comparative):
    old = OperatingSummaryReportProvider(comparative.parent.pin)
    assert old.read_comparisons("2330", observed_at=comparative.available) == ((), ())
    new = OperatingSummaryReportProvider(comparative.pin)
    assert new.read("2382", observed_at=comparative.available)[0] == ()
    assert new.read_comparisons("2382", observed_at=comparative.available)[0] == ()
    assert new.read_comparisons("1101", observed_at=comparative.available) == ((), ())


def test_financial_context_precision_is_local(comparative):
    with localcontext() as context:
        context.prec = 6
        values = reviewed.read_comparative_operating_summary_snapshot(comparative.pin, stock_code="2317", cutoff_at=comparative.available).values
        assert values[0].change_value == Decimal("35.13") and values[0].prior_value == Decimal("3437783609000")


def test_rounding_boundary_and_nonpositive_base_are_not_filled_with_zero():
    with localcontext() as context:
        context.prec = 80
        assert reviewed._stable_ratio(Decimal(100), Decimal(1), Decimal(100), Decimal(1), growth=True) is None
        assert reviewed._stable_ratio(Decimal(100), Decimal(1), Decimal(0), Decimal(1), growth=True) is None
        assert reviewed._stable_ratio(Decimal(100), Decimal(1), Decimal(-100), Decimal(1), growth=True) is None
        assert reviewed._stable_ratio(Decimal(90), Decimal(".00001"), Decimal(100), Decimal(".00001"), growth=True) == Decimal("-10.00")


def repin(comparative, manifest=None, receipt=None):
    import json
    if manifest is None:
        manifest = json.loads((comparative.pin.directory / "manifest.json").read_bytes())
    if receipt is None:
        receipt = json.loads((comparative.pin.directory / "receipt.json").read_bytes())
    (comparative.pin.directory / "manifest.json").write_bytes(base._bytes(manifest))
    digest = sha256(base._bytes(manifest)).hexdigest()
    receipt["manifest_sha256"] = digest
    (comparative.pin.directory / "receipt.json").write_bytes(base._bytes(receipt))
    return reviewed.ComparativeOperatingSummaryPin(comparative.pin.directory, digest, sha256(base._bytes(receipt)).hexdigest())


@pytest.mark.parametrize("change", ["source_use", "period", "child", "clock", "facts"])
def test_rehashing_does_not_expand_issuer_purpose_or_rebind_time(comparative, change):
    import json
    manifest = json.loads((comparative.pin.directory / "manifest.json").read_bytes())
    receipt = json.loads((comparative.pin.directory / "receipt.json").read_bytes())
    if change == "source_use":
        manifest["source_uses"]["2330"]["scope"]["intended_use"] = "strategy"
    elif change == "period":
        manifest["evidence"]["prior_period"] = "2026-Q1"
    elif change == "child":
        manifest["current_snapshot"]["directory"] = "../original"
    elif change == "clock":
        receipt["available_hour"] = comparative.waiting.isoformat()
    else:
        (comparative.pin.directory / "comparative_facts.json").write_bytes(b'{}')
        manifest["facts"]["sha256"] = sha256(b'{}').hexdigest()
    pin = repin(comparative, manifest, receipt)
    with pytest.raises((ValueError, KeyError)):
        reviewed.read_comparative_operating_summary_snapshot(pin, stock_code="2330", cutoff_at=comparative.available)


def test_pending_and_source_change_never_produce_comparison(comparative):
    (comparative.pin.directory / ".pending.json").write_text("{}")
    with pytest.raises(ValueError, match="pending"):
        reviewed.read_comparative_operating_summary_snapshot(comparative.pin, stock_code="2330", cutoff_at=comparative.available)


@pytest.mark.parametrize("field,value", [("current_value", Decimal("1")), ("value_unit", "percent"),
    ("stock_code", "2317"), ("current_source_version", "another-version")])
def test_report_refuses_cross_issuer_current_value_unit_and_version(comparative, field, value):
    provider = OperatingSummaryReportProvider(comparative.pin)
    current, _ = provider.read("2330", observed_at=comparative.available)
    pairs, _ = provider.read_comparisons("2330", observed_at=comparative.available)
    with pytest.raises(ValueError):
        broken = replace(pairs[0], **{field: value})
        StockResearchReportDTO(stock_code="2330", fundamentals=current, fundamental_comparisons=(broken, *pairs[1:]))


def test_invalid_dto_or_future_cutoff_cannot_gain_financial_qualification(comparative):
    provider = OperatingSummaryReportProvider(comparative.pin)
    pairs, _ = provider.read_comparisons("2330", observed_at=comparative.available)
    for change in ({"current_value": None}, {"prior_value": Decimal("NaN")}, {"change_value": 1.0},
        {"historical_pit_eligible": True}, {"aggregate_feature_eligible": True}, {"current_period": "2025-H1"}):
        with pytest.raises(ValueError):
            replace(pairs[0], **change)
    from datetime import datetime
    with pytest.raises(ValueError, match="實際現在"):
        reviewed.read_comparative_operating_summary_snapshot(comparative.pin, stock_code="2330", cutoff_at=datetime.now(base._TAIPEI) + timedelta(hours=1))


def test_public_report_keeps_comparison_out_of_historical_queries(comparative, tmp_path):
    from test_stock_research_report_service import _config
    from app_module.stock_research_report_service import StockResearchReportReadService
    config = _config(tmp_path)
    before = sha256(config.db_file.read_bytes()).hexdigest()
    service = StockResearchReportReadService(config, clock=lambda: comparative.available,
        operating_summary_provider=OperatingSummaryReportProvider(comparative.pin))
    current = service.read_report("2330")
    assert len(current.fundamental_comparisons) == 5
    historical = service.read_report("2330", as_of_date="2025-06-30")
    explicit_today = service.read_report("2330", as_of_date=comparative.available.date())
    assert not historical.fundamental_comparisons and not explicit_today.fundamental_comparisons
    assert not any(source.source_id.startswith("official.issuer.financial_comparison") for source in historical.sources)
    assert sha256(config.db_file.read_bytes()).hexdigest() == before


def test_five_row_matrix_shows_periods_and_separates_percent_from_points(comparative):
    from PySide6.QtWidgets import QApplication, QLabel, QTableView
    from ui_qt.views.stock_research_report_view import StockResearchReportView
    app = QApplication.instance() or QApplication([])
    provider = OperatingSummaryReportProvider(comparative.pin)
    current, current_sources = provider.read("2330", observed_at=comparative.available)
    pairs, sources = provider.read_comparisons("2330", observed_at=comparative.available)
    report = StockResearchReportDTO(stock_code="2330", fundamentals=current, sources=current_sources + sources, fundamental_comparisons=pairs)
    view = StockResearchReportView(SimpleNamespace())
    try:
        view._render_fundamental(report)
        tables = [table for table in view.findChildren(QTableView) if table.model() is not None and table.model().rowCount()]
        assert len(tables) == 1
        model = tables[0].model()
        assert (model.rowCount(), model.columnCount()) == (5, 4)
        assert "35.61%" in model.data(model.index(0, 3))
        assert "8.33 百分點" in model.data(model.index(1, 3))
        labels = "\n".join(label.text() for label in view.findChildren(QLabel))
        assert "2026-H1／2025-H1" in labels and "只供目前研究" in labels
        assert "前期由另列的財報比較版本供應" in labels and "前期與其他公司維持不可用" not in labels
        assert "不是額外的元級精度" in model.data(model.index(0, 2), 3)
        app.processEvents()
    finally:
        view.close()
