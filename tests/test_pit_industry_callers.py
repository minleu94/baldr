from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app_module.decision_desk_service import DecisionDeskSnapshotBuilder
from app_module.decision_service_composition import build_decision_service_composition
from app_module.industry_strength_service import IndustryStrengthData, IndustryStrengthService
from app_module.recommendation_service import RecommendationService
from data_module.config import TWStockConfig
from data_module.pit_sector_membership_reader import PITSectorMembershipReader

from tests.pit_test_support import (
    DECISION_AT,
    EFFECTIVE_FROM,
    _sha256_json,
    build_pit_fixture,
    load_json,
    write_json,
)


class _IndustryProvider:
    def __init__(self, data: IndustryStrengthData, latest: date) -> None:
        self.data = data
        self.latest = latest

    def latest_available_date(self) -> date:
        return self.latest

    def fetch(self, _as_of_date: date, *, session_limit: int = 25) -> IndustryStrengthData:
        del session_limit
        return self.data


def _industry_data() -> IndustryStrengthData:
    dates = [date(2026, 7, 26) + timedelta(days=index) for index in range(31)]
    industry_rows = [
        {
            "日期": current.isoformat(),
            "指數名稱": "半導體類指數",
            "收盤指數": str(1000 + index * 3),
        }
        for index, current in enumerate(dates)
    ]
    market_rows = [
        {
            "日期": current.isoformat(),
            "指數名稱": "TAIEX",
            "收盤指數": str(1000 + index),
        }
        for index, current in enumerate(dates)
    ]
    price_rows = [
        {
            "日期": current.isoformat(),
            "證券代號": symbol,
            "證券名稱": symbol,
            "收盤價": str(base + index),
        }
        for index, current in enumerate(dates)
        for symbol, base in (("2330", 100), ("1101", 200))
    ]
    # deliberately reverse the current registry mapping; PIT must win.
    companies = pd.DataFrame(
        [
            {"stock_id": "2330", "industry_category": "水泥工業", "type": "twse"},
            {"stock_id": "1101", "industry_category": "半導體業", "type": "twse"},
        ]
    )
    return IndustryStrengthData(
        industry_indices=pd.DataFrame(industry_rows),
        market_indices=pd.DataFrame(market_rows),
        daily_prices=pd.DataFrame(price_rows),
        companies=companies,
    )


def _recommendation_frame() -> pd.DataFrame:
    dates = [date(2026, 8, 5) + timedelta(days=index) for index in range(21)]
    rows = []
    for index, current in enumerate(dates):
        for symbol, base in (("2330", 100), ("1101", 200)):
            rows.append(
                {
                    "日期": current.isoformat(),
                    "證券代號": symbol,
                    "證券名稱": symbol,
                    "收盤價": str(base + index),
                    "成交股數": str(1000 + index),
                }
            )
    return pd.DataFrame(rows)


def _fake_recommendation_output(calls: list[str]) -> MagicMock:
    strategy = MagicMock()

    def generate(stock_frame: pd.DataFrame, _config: dict[str, object]) -> pd.DataFrame:
        code = str(stock_frame.iloc[-1]["證券代號"])
        calls.append(code)
        latest = stock_frame.iloc[-1]
        return pd.DataFrame(
            [
                {
                    "證券代號": code,
                    "證券名稱": code,
                    "收盤價": latest["收盤價"],
                    "漲幅%": latest.get("漲幅%", Decimal("0")),
                    "成交量變化率%": latest.get("成交量變化率%", Decimal("0")),
                    "FinalScore": Decimal("80"),
                    "TotalScore": Decimal("80"),
                    "IndicatorScore": Decimal("80"),
                    "PatternScore": Decimal("0"),
                    "VolumeScore": Decimal("0"),
                }
            ]
        )

    strategy.generate_recommendations.side_effect = generate
    return strategy


def test_industry_strength_uses_verified_pit_taxonomy_over_current_registry(
    tmp_path: Path,
) -> None:
    fixture = build_pit_fixture(tmp_path, symbols=("2330",))
    reader = PITSectorMembershipReader([fixture.artifact_path])
    data = _industry_data()
    service = IndustryStrengthService(
        provider=_IndustryProvider(data, EFFECTIVE_FROM),
        pit_membership_reader=reader,
        pit_market_scope="twse_listed",
    )

    summary = service.build_industry_strength(EFFECTIVE_FROM, decision_at=DECISION_AT)
    semiconductor = next(row for row in summary.rows if row.industry_name == "半導體業")

    assert semiconductor.constituent_count == 1
    assert semiconductor.representative_stocks[0].stock_code == "2330"
    assert summary.coverage["mapping_mode"] == "pit_accepted_prospective"
    assert summary.coverage["coverage_denominator"] == "accepted_pit_membership_rows"
    assert summary.coverage["pit_membership"]["taxonomy_verified"] is True
    assert "industry_mapping_current_research_only" not in summary.warnings


def test_industry_strength_fails_closed_when_pit_taxonomy_is_not_verified(
    tmp_path: Path,
) -> None:
    fixture = build_pit_fixture(tmp_path, symbols=("2330",), include_taxonomy=False)
    reader = PITSectorMembershipReader([fixture.artifact_path])
    service = IndustryStrengthService(
        provider=_IndustryProvider(_industry_data(), EFFECTIVE_FROM),
        pit_membership_reader=reader,
        pit_market_scope="twse_listed",
    )

    summary = service.build_industry_strength(EFFECTIVE_FROM, decision_at=DECISION_AT)

    assert summary.coverage["mapping_mode"] == "pit_unavailable_fail_closed"
    assert not summary.rows
    assert "industry_mapping_pit_taxonomy_unverified" in summary.warnings


def test_recommendation_cutoff_uses_pit_filter_through_normal_config_composition(
    tmp_path: Path,
) -> None:
    fixture = build_pit_fixture(tmp_path / "positive", symbols=("2330",))
    config = TWStockConfig(
        data_root=tmp_path / "data",
        output_root=tmp_path / "output",
        pit_sector_membership_path=fixture.artifact_path,
        pit_sector_membership_raw_root=fixture.bundle_root,
        pit_sector_membership_clock_manifest_path=fixture.clock_path,
        pit_sector_membership_universe_symbols_path=fixture.universe_symbols_path,
        pit_sector_membership_universe_identity_path=fixture.universe_identity_path,
        pit_sector_membership_taxonomy_identity_path=fixture.taxonomy_identity_path,
        pit_market_scope="twse_listed",
    )
    config.use_sqlite = False
    composition = build_decision_service_composition(config=config)
    service = composition.recommendation_service
    service.market_data_provider = lambda: _recommendation_frame()
    service.calibration_consumer = None
    service.reason_engine = MagicMock()
    service.reason_engine.generate_reasons.return_value = []
    service.reason_engine.format_reason_text.return_value = ""
    calls: list[str] = []
    service.strategy_configurator = _fake_recommendation_output(calls)

    recommendations = service.run_recommendation(
        {"filters": {"industry": "半導體業"}},
        max_stocks=10,
        top_n=1,
        as_of_date=EFFECTIVE_FROM.isoformat(),
    )

    assert [item.stock_code for item in recommendations] == ["2330"]
    assert calls == ["2330"]
    assert service.last_run_context["industry_membership_status"] == "accepted"
    assert service.last_run_context["industry_membership"]["taxonomy_verified"] is True
    assert "industry_membership_pit_verified" in service.last_run_context["warnings"]
    assert "industry_membership_not_point_in_time" not in service.last_run_context["warnings"]


def test_recommendation_cutoff_blocks_missing_unknown_and_partial_taxonomy(
    tmp_path: Path,
) -> None:
    fixtures = [
        build_pit_fixture(
            tmp_path / "missing", symbols=("2330",), include_taxonomy=False
        ),
        build_pit_fixture(tmp_path / "unknown", symbols=("2330",)),
        build_pit_fixture(
            tmp_path / "partial",
            symbols=("2330", "1101"),
            taxonomy_symbols=("2330",),
            security_types={"2330": "common_equity"},
        ),
    ]
    unknown_taxonomy = load_json(fixtures[1].taxonomy_identity_path)
    assert isinstance(unknown_taxonomy, dict)
    unknown_taxonomy["mapping"] = {"01": "水泥工業"}
    unknown_body = dict(unknown_taxonomy)
    unknown_body.pop("mapping_hash", None)
    unknown_taxonomy["mapping_hash"] = _sha256_json(unknown_body)
    write_json(fixtures[1].taxonomy_identity_path, unknown_taxonomy)

    for index, fixture in enumerate(fixtures):
        reader = PITSectorMembershipReader([fixture.artifact_path])
        config = SimpleNamespace(pit_market_scope="twse_listed")
        service = RecommendationService(
            config,
            industry_mapper=MagicMock(),
            market_data_provider=lambda: _recommendation_frame(),
            regime_detector=MagicMock(),
            calibration_consumer=None,
            pit_membership_reader=reader,
        )
        strategy = MagicMock()
        service.strategy_configurator = strategy

        result = service.run_recommendation(
            {"filters": {"industry": "半導體業"}},
            max_stocks=10,
            top_n=1,
            as_of_date=EFFECTIVE_FROM.isoformat(),
        )

        assert result == [], f"case {index} unexpectedly produced a recommendation"
        strategy.generate_recommendations.assert_not_called()
        assert all(
            "industry_membership_pit_unavailable" in row["reason_codes"]
            for row in service.last_screening_matrix
        )


def test_decision_desk_preserves_pit_lineage_from_sector_rotation_service(
    tmp_path: Path,
) -> None:
    fixture = build_pit_fixture(tmp_path, symbols=("2330",))
    service = IndustryStrengthService(
        provider=_IndustryProvider(_industry_data(), EFFECTIVE_FROM),
        pit_membership_reader=PITSectorMembershipReader([fixture.artifact_path]),
        pit_market_scope="twse_listed",
    )
    builder = DecisionDeskSnapshotBuilder(
        sector_rotation_service=service,
        clock=lambda: datetime(2026, 8, 25, 8, 30),
    )

    snapshot = builder.build_snapshot(EFFECTIVE_FROM)

    sector_metadata = snapshot.source_lineage["sector_rotation"]["metadata"]
    assert sector_metadata["pit_membership"]["taxonomy_verified"] is True
    assert sector_metadata["pit_membership_status"] == "accepted"
    assert sector_metadata["historical_pit_eligible"] is False


def test_formal_rule_producer_scores_are_reverified_by_shared_reader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """producer 產生 identity；reader 重新以 score vector 重建其 hash。"""

    from data_module import formal_rule_source_producer as producer
    from tests.test_formal_rule_source_producer import (
        PREOPEN,
        _patch_policy_and_calendar_only,
        _real_market_db,
        _write_baseline,
    )

    baseline_root = tmp_path / "baseline"
    _write_baseline(tmp_path)
    _patch_policy_and_calendar_only(monkeypatch)
    market_db = _real_market_db(tmp_path)
    result = producer.produce_current_rule_source_bundle(
        output_root=tmp_path / "publication" / "rule_source",
        market_db=market_db,
        baseline_root=baseline_root,
        calendar_cache_root=tmp_path / "calendar",
        now=PREOPEN,
    )

    identity_path = Path(str(result["universe_identity"]))
    identity = load_json(identity_path)
    symbols = load_json(Path(str(result["universe_symbols"])))
    assert isinstance(identity, dict)
    assert isinstance(symbols, list)
    assert isinstance(identity.get("scores_bp"), list)
    assert isinstance(identity.get("universe_hash_symbols"), list)
    assert len(identity["scores_bp"]) == len(symbols)
    assert set(identity["universe_hash_symbols"]) == set(symbols)
    assert tuple(identity["universe_hash_symbols"]) != tuple(symbols)

    verification = PITSectorMembershipReader([]).verify_universe_identity(
        identity_path,
        universe_hash=str(identity["universe_hash"]),
        row_symbols=tuple(str(item) for item in symbols),
    )

    assert verification.verified is True
    assert verification.symbols == tuple(symbols)
    assert verification.warnings == ()

    tampered_identity = dict(identity)
    tampered_scores = list(identity["scores_bp"])
    tampered_scores[0] = int(tampered_scores[0]) + 1
    tampered_identity["scores_bp"] = tampered_scores
    write_json(identity_path, tampered_identity)
    tampered_verification = PITSectorMembershipReader([]).verify_universe_identity(
        identity_path,
        universe_hash=str(identity["universe_hash"]),
        row_symbols=tuple(str(item) for item in symbols),
    )
    assert tampered_verification.verified is False
    assert "universe_identity_hash_reconstruction_mismatch" in tampered_verification.warnings


def test_formal_rule_producer_tied_scores_keep_canonical_rank_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from data_module import formal_rule_source_producer as producer
    from development_module.manual_rule_only_decision import _universe_hash as real_universe_hash
    from tests.test_formal_rule_source_producer import (
        PREOPEN,
        _patch_real_source_checks,
        _write_baseline,
    )

    baseline_root = tmp_path / "baseline"
    _write_baseline(tmp_path)
    _patch_real_source_checks(
        monkeypatch, symbols=("1101", "2330", "6505")
    )
    # The production ranker is score-desc then symbol-asc.  This tie stub has
    # the real score_bp field and exercises the symbol tie-breaker without
    # changing the existing universe hash implementation.
    monkeypatch.setattr(producer, "_universe_hash", real_universe_hash)
    monkeypatch.setattr(
        producer,
        "rank_rule_only_candidates",
        lambda *_args, **_kwargs: [
            SimpleNamespace(symbol=symbol, score_bp=7000)
            for symbol in ("1101", "2330", "6505")
        ],
    )
    market_db = tmp_path / "readonly-market.sqlite"
    market_db.write_bytes(b"readonly market fixture")
    result = producer.produce_current_rule_source_bundle(
        output_root=tmp_path / "publication" / "rule_source",
        market_db=market_db,
        baseline_root=baseline_root,
        calendar_cache_root=tmp_path / "calendar",
        now=PREOPEN,
    )

    identity_path = Path(str(result["universe_identity"]))
    identity = load_json(identity_path)
    symbols = load_json(Path(str(result["universe_symbols"])))
    assert isinstance(identity, dict)
    assert isinstance(symbols, list)
    assert identity["scores_bp"] == [7000, 7000, 7000]
    assert identity["universe_hash_symbols"] == symbols
    verification = PITSectorMembershipReader([]).verify_universe_identity(
        identity_path,
        universe_hash=str(identity["universe_hash"]),
        row_symbols=tuple(str(item) for item in symbols),
    )
    assert verification.verified is True
