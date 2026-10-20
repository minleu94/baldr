from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, localcontext

import pytest

from decision_module.theme_momentum_filter import (
    ThemeMomentumDecision,
    ThemeMomentumInput,
    evaluate_theme_momentum,
)


def _qualified_input(**changes: object) -> ThemeMomentumInput:
    base = ThemeMomentumInput(
        stock_code="2330",
        decision_at=datetime(2026, 10, 20, 10, 0, tzinfo=timezone(timedelta(hours=8))),
        data_date=date(2026, 10, 20),
        available_at=datetime(2026, 10, 20, 1, 59, tzinfo=timezone.utc),
        mapping_available_at=datetime(2026, 10, 20, 9, 30, tzinfo=timezone(timedelta(hours=8))),
        historical_mapping_eligible=True,
        stock_in_theme=True,
        institutional_buy_count=8,
        member_count=10,
        institutional_coverage_complete=True,
        net_inflow_twd=Decimal("1200000"),
        inflow_rank=2,
        ranked_theme_count=10,
        inflow_universe_complete=True,
    )
    return replace(base, **changes)


def test_valid_complete_evidence_passes_only_the_research_filter() -> None:
    result = evaluate_theme_momentum(_qualified_input())

    assert result.state == "qualified"
    assert len(result.reasons) == 3
    assert "研究濾網通過" in result.reasons[-1]
    assert "買進" not in result.reasons[-1]


def test_buyers_must_strictly_exceed_seventy_percent() -> None:
    exactly_seventy = evaluate_theme_momentum(
        _qualified_input(institutional_buy_count=7, member_count=10)
    )
    above_seventy = evaluate_theme_momentum(
        _qualified_input(institutional_buy_count=8, member_count=10)
    )

    assert exactly_seventy.state == "not_qualified"
    assert exactly_seventy.reasons == ("法人買超家數比例未嚴格超過70%",)
    assert above_seventy.state == "qualified"


def test_inflow_rank_uses_exact_twenty_percent_boundary_without_rounding_up() -> None:
    boundary = evaluate_theme_momentum(
        _qualified_input(inflow_rank=2, ranked_theme_count=10)
    )
    outside = evaluate_theme_momentum(
        _qualified_input(inflow_rank=3, ranked_theme_count=10)
    )
    small_universe = evaluate_theme_momentum(
        _qualified_input(inflow_rank=1, ranked_theme_count=4)
    )

    assert boundary.state == "qualified"
    assert outside.state == "not_qualified"
    assert "前20%" in outside.reasons[0]
    assert small_universe.state == "not_qualified"
    assert "前20%" in small_universe.reasons[0]


@pytest.mark.parametrize("amount", [Decimal("0"), Decimal("-0.01")])
def test_zero_or_negative_net_inflow_does_not_pass(amount: Decimal) -> None:
    result = evaluate_theme_momentum(_qualified_input(net_inflow_twd=amount))

    assert result.state == "not_qualified"
    assert result.reasons == ("法人淨流入金額未大於零",)


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"historical_mapping_eligible": False}, "歷史題材映射資格"),
        ({"stock_in_theme": False}, "股票題材成員資格"),
        ({"institutional_coverage_complete": False}, "法人家數覆蓋"),
        ({"inflow_universe_complete": False}, "資金排名母體完整性"),
        ({"available_at": None}, "資料可得時間缺失"),
        ({"mapping_available_at": None}, "題材映射可得時間缺失"),
        ({"institutional_buy_count": None}, "法人買超家數"),
        ({"member_count": None}, "題材成員數"),
        ({"net_inflow_twd": None}, "法人淨流入金額缺失"),
        ({"inflow_rank": None}, "資金流入序位"),
        ({"ranked_theme_count": None}, "排序母體題材數"),
    ],
)
def test_missing_required_evidence_fails_closed(changes: dict[str, object], reason: str) -> None:
    result = evaluate_theme_momentum(_qualified_input(**changes))

    assert result.state == "unavailable"
    assert any(reason in item for item in result.reasons)


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"institutional_buy_count": True}, "法人買超家數"),
        ({"member_count": True}, "題材成員數"),
        ({"member_count": 0}, "題材成員數須大於零"),
        ({"institutional_buy_count": -1}, "法人買超家數不可為負數"),
        ({"institutional_buy_count": 11}, "法人買超家數不可大於題材成員數"),
        ({"inflow_rank": True}, "資金流入序位"),
        ({"inflow_rank": 0}, "資金流入序位須大於零"),
        ({"inflow_rank": 11}, "資金流入序位超出排序母體"),
        ({"ranked_theme_count": False}, "排序母體題材數"),
        ({"ranked_theme_count": 0}, "排序母體題材數須大於零"),
        ({"inflow_metric": "institutional_net_shares"}, "不接受股數或其他單位"),
        ({"net_inflow_twd": 1.0}, "法人淨流入金額須為Decimal"),
        ({"net_inflow_twd": Decimal("NaN")}, "有限Decimal"),
        ({"net_inflow_twd": Decimal("Infinity")}, "有限Decimal"),
        ({"institutional_coverage_complete": 1}, "旗標型別須為bool"),
        ({"inflow_universe_complete": 1}, "旗標型別須為bool"),
        ({"stock_code": "  "}, "股票代碼缺失"),
        ({"data_date": datetime(2026, 10, 20, 0, 0)}, "資料日須為date"),
    ],
)
def test_invalid_types_values_and_units_are_unavailable(
    changes: dict[str, object], reason: str,
) -> None:
    result = evaluate_theme_momentum(_qualified_input(**changes))

    assert result.state == "unavailable"
    assert any(reason in item for item in result.reasons)


def test_timezone_aware_instants_compare_across_zones_and_date_uses_taipei() -> None:
    equivalent_instant = _qualified_input(
        decision_at=datetime(2026, 10, 19, 18, 0, tzinfo=timezone.utc),
        available_at=datetime(2026, 10, 19, 18, 0, tzinfo=timezone.utc),
        mapping_available_at=datetime(2026, 10, 19, 17, 59, tzinfo=timezone.utc),
    )
    mismatched_taipei_date = replace(equivalent_instant, data_date=date(2026, 10, 19))

    assert evaluate_theme_momentum(equivalent_instant).state == "qualified"
    mismatch = evaluate_theme_momentum(mismatched_taipei_date)
    assert mismatch.state == "unavailable"
    assert "資料日與台北決策日不一致" in mismatch.reasons


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"decision_at": datetime(2026, 10, 20, 10, 0)}, "決策時間必須包含有效時區"),
        ({"available_at": datetime(2026, 10, 20, 1, 59)}, "資料可得時間必須包含有效時區"),
        ({"mapping_available_at": datetime(2026, 10, 20, 9, 30)}, "題材映射可得時間必須包含有效時區"),
        (
            {"available_at": datetime(2026, 10, 20, 2, 0, 1, tzinfo=timezone.utc)},
            "資料可得時間晚於決策時間",
        ),
        (
            {"mapping_available_at": datetime(2026, 10, 20, 10, 0, 1, tzinfo=timezone(timedelta(hours=8)))},
            "題材映射可得時間晚於決策時間",
        ),
    ],
)
def test_naive_or_future_timestamps_are_unavailable(
    changes: dict[str, object], reason: str,
) -> None:
    result = evaluate_theme_momentum(_qualified_input(**changes))

    assert result.state == "unavailable"
    assert any(reason in item for item in result.reasons)


def test_exact_integer_and_decimal_checks_do_not_depend_on_decimal_context() -> None:
    huge_members = 10**60
    high_precision = _qualified_input(
        institutional_buy_count=7 * huge_members // 10 + 1,
        member_count=huge_members,
        net_inflow_twd=Decimal("1E-100"),
        inflow_rank=1,
        ranked_theme_count=5,
    )
    with localcontext() as context:
        context.prec = 2
        result = evaluate_theme_momentum(high_precision)

    assert result.state == "qualified"


def test_invalid_input_object_fails_closed_without_external_reads() -> None:
    result = evaluate_theme_momentum(object())  # type: ignore[arg-type]

    assert result.state == "unavailable"
    assert result.reasons == ("輸入型別須為ThemeMomentumInput",)


def test_decision_is_frozen_and_state_vocabulary_is_closed() -> None:
    result = ThemeMomentumDecision("not_qualified", ("測試",))

    with pytest.raises(FrozenInstanceError):
        result.state = "qualified"  # type: ignore[misc]
    with pytest.raises(ValueError):
        ThemeMomentumDecision("accepted", ())
