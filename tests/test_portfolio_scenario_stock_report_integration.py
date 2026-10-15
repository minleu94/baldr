"""真封存→個股read service的帳本隔離；禁止查現在同股持倉。"""
from dataclasses import asdict, replace
from datetime import date, datetime, timezone
from hashlib import sha256

import pytest

from app_module.personal_data_paths import PersonalDataPaths
from app_module.portfolio_research_scenario_repository import PortfolioResearchScenarioRepository
from app_module.portfolio_research_scenario_workspace import PortfolioResearchScenarioWorkspace
from app_module.portfolio_research_stock_projection import PortfolioScenarioStockReference
from app_module.research_session import ResearchStockContextDTO
from app_module.stock_research_report_service import StockResearchReportReadService, StockResearchReportCancelled
from app_module.stock_research_product_summary import build_stock_research_product_summary
from test_portfolio_research_scenario_repository import _comparison, _route
from test_stock_research_report_service import _config


class ForeignCurrentPortfolio:
    def get_position_detail(self, *_):
        raise AssertionError('封存研究禁止讀當前同股手動帳')

    def get_portfolio(self, *_):
        raise AssertionError('封存研究禁止讀當前帳戶總額')


@pytest.fixture
def scenario_report(tmp_path):
    paths = PersonalDataPaths(market_root=tmp_path/'market', legacy_output_root=tmp_path/'legacy',
                             personal_root=tmp_path/'market/personal')
    repo = PortfolioResearchScenarioRepository(route=_route(paths), personal_paths=paths)
    saved = repo.append(_comparison(), saved_at=datetime(2026, 10, 9, 2, tzinfo=timezone.utc))
    config = _config(tmp_path)
    service = StockResearchReportReadService(config, portfolio_service=ForeignCurrentPortfolio(),
        portfolio_research_workspace=PortfolioResearchScenarioWorkspace(repo),
        clock=lambda: datetime(2026, 10, 15, 4, tzinfo=timezone.utc))
    context = ResearchStockContextDTO(stock_code='2330', decision_date='2026-10-09',
        data_date='2026-10-08', source_kind='portfolio_research_scenario', source_workspace='portfolio',
        source_snapshot_id=saved.artifact_id, source_snapshot_hash=saved.comparison.account.source_hash,
        portfolio_scenario_ref=PortfolioScenarioStockReference('paper', 'account-a', saved.artifact_id))
    return service, saved, context, repo


def test_public_report_keeps_saved_account_facts_and_no_current_account(scenario_report):
    service, saved, context, repo = scenario_report
    before = sha256(repo.db_path.read_bytes()).hexdigest()
    report = service.read_report('2330', context=context)
    projection = report.portfolio_scenario
    assert projection is not None and report.position is None
    assert report.as_of == '2026-10-09'
    assert projection.quantity == 1000
    assert projection.cash_amount == saved.comparison.account.valuation.cash_amount
    assert projection.total_value == saved.comparison.account.valuation.total_value
    assert projection.reference.artifact_id == saved.artifact_id
    assert projection.health_state == saved.comparison.request.contexts[0].context.health_state
    assert not any('禁止讀當前' in limitation for limitation in report.limitations)
    assert sha256(repo.db_path.read_bytes()).hexdigest() == before
    summary = build_stock_research_product_summary(report)
    assert 'paper／account-a' in summary.holding_relation and '1000 股' in summary.holding_relation
    assert '不是今日帳本' in summary.holding_relation
    assert report.to_dict()['portfolio_scenario']['reference']['artifact_id'] == saved.artifact_id


@pytest.mark.parametrize('change', [
    {'portfolio_scenario_ref': None},
    {'source_snapshot_hash': 'sha256:'+'b'*64},
    {'portfolio_scenario_ref': PortfolioScenarioStockReference('manual', 'account-a', 'sha256:'+'a'*64),
     'source_snapshot_id': 'sha256:'+'a'*64},
])
def test_missing_or_wrong_source_never_falls_back_to_foreign_current(scenario_report, change):
    service, saved, context, repo = scenario_report
    before = sha256(repo.db_path.read_bytes()).hexdigest()
    report = service.read_report('2330', context=replace(context, **change))
    assert report.portfolio_scenario is None and report.position is None
    assert any(section.section_id == 'position' and section.status == 'error' for section in report.sections)
    assert sha256(repo.db_path.read_bytes()).hexdigest() == before


def test_explicit_wrong_cutoff_refuses_saved_projection(scenario_report):
    service, _, context, _ = scenario_report
    report = service.read_report('2330', context=context, as_of_date=date(2026, 10, 10))
    assert report.portfolio_scenario is None and report.position is None


def test_frozen_candidate_without_holding_remains_known_zero(scenario_report):
    service, _, context, _ = scenario_report
    report = service.read_report('2382', context=replace(context, stock_code='2382'))
    assert report.portfolio_scenario is not None
    assert report.portfolio_scenario.quantity == 0
    assert report.portfolio_scenario.mark_price is None
    assert '未持有此股' in build_stock_research_product_summary(report).holding_relation


def test_cancel_in_exact_read_does_not_publish_partial_projection(scenario_report):
    service, _, context, _ = scenario_report
    with pytest.raises(StockResearchReportCancelled):
        service.read_report('2330', context=context, cancel_callback=lambda: True)


@pytest.mark.parametrize('change', [
    {'source_kind': 'recommendation'},
    {'source_snapshot_id': 'sha256:'+'0'*64},
    {'portfolio_scenario_ref': {}},
])
def test_mapping_reference_cannot_bypass_account_guard(scenario_report, change):
    service, _, context, _ = scenario_report
    mapping = asdict(context)
    mapping.update(change)
    with pytest.raises(ValueError):
        service.read_report('2330', context=mapping)
