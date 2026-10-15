from __future__ import annotations

from decimal import Decimal

from app_module.personal_data_paths import PersonalDataPaths
from app_module.portfolio_research_scenario_repository import (
    PortfolioResearchScenarioRepository,
)
from app_module.portfolio_research_stock_projection import (
    PortfolioScenarioStockReference,
    project_saved_scenario_stock,
)
from app_module.research_session.session_dtos import ResearchStockContextDTO
from test_portfolio_research_scenario_repository import (
    HASH,
    SAVED,
    _comparison,
    _route,
)

import pytest


@pytest.fixture
def repo(tmp_path):
    paths = PersonalDataPaths(
        market_root=tmp_path / "market",
        legacy_output_root=tmp_path / "legacy",
        personal_root=tmp_path / "market" / "personal",
    )
    return PortfolioResearchScenarioRepository(
        route=_route(paths), personal_paths=paths
    )


def _reference(saved):
    account = saved.comparison.account
    return PortfolioScenarioStockReference(
        account_kind=account.account_kind,
        portfolio_id=account.portfolio_id,
        artifact_id=saved.artifact_id,
    )


def test_saved_projection_is_exact_account_bound_and_preserves_decimal_facts(repo):
    # 使用原 producer fixture 並實際寫入、精確讀回三種帳種的封存。
    saved_items = tuple(
        repo.append(_comparison(kind), saved_at=SAVED)
        for kind in ("manual", "user_declared", "paper")
    )
    assert len({item.artifact_id for item in saved_items}) == 3

    for saved in saved_items:
        account = saved.comparison.account
        readback = repo.get_exact(
            saved.artifact_id,
            account_kind=account.account_kind,
            portfolio_id=account.portfolio_id,
        )
        assert readback is not None
        assert readback == saved

        reference = _reference(readback)
        projection = project_saved_scenario_stock(
            readback,
            reference=reference,
            stock_code="2330",
            expected_account_source_hash=HASH,
        )
        comparison = readback.comparison
        context = next(
            item for item in comparison.request.contexts
            if item.context.stock_code == "2330"
        )
        valued_position = next(
            item for item in comparison.account.valuation.positions
            if item.stock_code == "2330"
        )

        assert projection.reference == reference
        assert projection.snapshot_id == comparison.account.snapshot_id
        assert projection.account_source_hash == comparison.account.source_hash
        assert projection.cash_amount == comparison.account.valuation.cash_amount
        assert projection.total_value == comparison.account.valuation.total_value
        assert isinstance(projection.cash_amount, type(comparison.account.valuation.cash_amount))
        assert isinstance(projection.total_value, type(comparison.account.valuation.total_value))
        assert projection.quantity == valued_position.quantity
        assert projection.mark_price == valued_position.mark_price
        assert projection.market_value == valued_position.market_value
        assert isinstance(projection.mark_price, Decimal)
        assert isinstance(projection.market_value, Decimal)
        assert projection.current_weight_bp == comparison.account.current_weights.weight_for("2330")
        assert projection.health_state == context.context.health_state
        assert projection.health_known is context.health_known
        assert len(projection.targets) == len(comparison.scenarios)

        for target, scenario in zip(projection.targets, comparison.scenarios):
            rows = [
                row for row in scenario.result.projection.rows
                if row.stock_code == "2330"
            ]
            assert len(rows) == 1
            row = rows[0]
            assert target.scenario_kind == scenario.scenario_kind
            assert target.rule_requested_weight_bp == row.rule_requested_weight_bp
            assert target.target_weight_bp == row.target_weight_bp
            assert target.current_weight_bp == row.current_weight_bp
            assert target.gap_weight_bp == row.gap_weight_bp
            assert target.executable_shares == row.executable_shares
            assert target.executable_amount == row.executable_amount
            assert target.estimated_cost == row.estimated_cost
            if row.executable_amount is not None:
                assert isinstance(target.executable_amount, Decimal)
            if row.estimated_cost is not None:
                assert isinstance(target.estimated_cost, Decimal)
            assert target.diagnostics == row.diagnostics

    paper_saved = saved_items[-1]
    paper_reference = _reference(paper_saved)
    with pytest.raises(ValueError, match="another selected account"):
        repo.get_exact(
            paper_saved.artifact_id,
            account_kind="paper",
            portfolio_id="other-account",
        )
    with pytest.raises(ValueError, match="another selected account"):
        repo.get_exact(
            paper_saved.artifact_id,
            account_kind="manual",
            portfolio_id="account-a",
        )

    wrong_account = PortfolioScenarioStockReference(
        account_kind="paper",
        portfolio_id="other-account",
        artifact_id=paper_saved.artifact_id,
    )
    with pytest.raises(ValueError, match="封存參照與原帳本來源不符"):
        project_saved_scenario_stock(
            paper_saved,
            reference=wrong_account,
            stock_code="2330",
            expected_account_source_hash=HASH,
        )
    with pytest.raises(ValueError, match="封存參照與原帳本來源不符"):
        project_saved_scenario_stock(
            paper_saved,
            reference=paper_reference,
            stock_code="2330",
            expected_account_source_hash="sha256:" + "b" * 64,
        )
    with pytest.raises(ValueError, match="股票不在原候選及完整持倉範圍"):
        project_saved_scenario_stock(
            paper_saved,
            reference=paper_reference,
            stock_code="9999",
            expected_account_source_hash=HASH,
        )


def test_unheld_candidate_keeps_zero_shares_separate_from_missing_valuation(repo):
    saved = repo.append(_comparison(), saved_at=SAVED)
    readback = repo.get_exact(
        saved.artifact_id,
        account_kind="paper",
        portfolio_id="account-a",
    )
    assert readback is not None

    projection = project_saved_scenario_stock(
        readback,
        reference=_reference(readback),
        stock_code="2382",
        expected_account_source_hash=HASH,
    )

    assert projection.quantity == 0
    assert projection.mark_price is None
    assert projection.market_value is None
    assert projection.current_weight_bp == 0
    assert len(projection.targets) == len(readback.comparison.scenarios)
    for target, scenario in zip(projection.targets, readback.comparison.scenarios):
        source_row = next(
            row for row in scenario.result.projection.rows
            if row.stock_code == "2382"
        )
        assert target.target_weight_bp == source_row.target_weight_bp
        assert target.current_weight_bp == 0
        assert target.diagnostics == source_row.diagnostics


def test_scenario_reference_mapping_accepts_only_its_three_identity_fields():
    reference = PortfolioScenarioStockReference(
        account_kind="paper",
        portfolio_id="account-a",
        artifact_id=HASH,
    )
    assert PortfolioScenarioStockReference.from_mapping(
        {
            "account_kind": "paper",
            "portfolio_id": "account-a",
            "artifact_id": HASH,
        }
    ) == reference

    for invalid in (
        {"account_kind": "paper", "portfolio_id": "account-a"},
        {
            "account_kind": "paper",
            "portfolio_id": "account-a",
            "artifact_id": HASH,
            "source_hash": HASH,
        },
        [("account_kind", "paper")],
    ):
        with pytest.raises(ValueError, match="封存參照欄位不符"):
            PortfolioScenarioStockReference.from_mapping(invalid)


def test_research_context_requires_matching_saved_scenario_source_identity():
    reference = PortfolioScenarioStockReference(
        account_kind="paper",
        portfolio_id="account-a",
        artifact_id=HASH,
    )
    ref_mapping = {
        "account_kind": "paper",
        "portfolio_id": "account-a",
        "artifact_id": HASH,
    }

    context = ResearchStockContextDTO(
        stock_code="2330",
        source_kind="portfolio_research_scenario",
        source_snapshot_id=HASH,
        portfolio_scenario_ref=ref_mapping,
    )
    assert context.portfolio_scenario_ref == reference

    with pytest.raises(ValueError, match="portfolio scenario參照與研究來源不一致"):
        ResearchStockContextDTO(
            stock_code="2330",
            source_kind="recommendation",
            source_snapshot_id=HASH,
            portfolio_scenario_ref=reference,
        )
    with pytest.raises(ValueError, match="portfolio scenario參照與研究來源不一致"):
        ResearchStockContextDTO(
            stock_code="2330",
            source_kind="portfolio_research_scenario",
            source_snapshot_id="sha256:" + "b" * 64,
            portfolio_scenario_ref=reference,
        )
