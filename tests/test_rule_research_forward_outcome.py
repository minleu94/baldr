"""UX21 以 synthetic capture/price/calendar 驗證研究 forward outcomes。"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, ROUND_DOWN, localcontext
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app_module.rule_research_forward_outcome import (
    Calendar,
    BenchmarkSpec,
    CostPolicy,
    ForwardOutcomeError,
    ForwardOutcomeProjection,
    PricePoint,
    build_parent_rule_research_forward_outcome,
    build_rule_research_forward_outcome,
)
from app_module.rule_research_parent_capture import (
    BoundedRuleResearchParentWriter,
    RuleResearchParentCapture,
    _parent_identity,
)
from app_module.rule_research_sample_capture import (
    BoundedRuleResearchCaptureWriter,
    SAFETY_RESERVE_BYTES,
)
from tests.test_rule_research_parent_capture import _fixture as parent_fixture
from tests.test_rule_research_sample_capture import _fixture as child_fixture


def _sessions(start: date, count: int) -> tuple[str, ...]:
    dates = [start]
    current = start
    while len(dates) < count + 1:
        current += timedelta(days=1)
        if current.weekday() < 5:
            dates.append(current)
    return tuple(item.isoformat() for item in dates)


def _calendar(decision: date, *, sessions: int = 20, available_date: str | None = None) -> Calendar:
    dates = _sessions(decision, sessions)
    return Calendar(
        trading_dates=dates,
        known=True,
        complete=True,
        coverage_start=dates[0],
        coverage_end=dates[-1],
        source_identity="synthetic-weekdays-calendar.v1",
        available_date=available_date,
    )


def _unknown_calendar() -> Calendar:
    return Calendar(
        trading_dates=(),
        known=False,
        complete=False,
        coverage_start=None,
        coverage_end=None,
        source_identity=None,
        available_date=None,
    )


def _point(
    instrument: str,
    day: str,
    price: Decimal | None,
    *,
    state: str = "available",
    currency: str = "TWD",
    unit: str = "TWD/share",
    price_basis: str = "raw_close.v1",
    corporate_action_basis: str = "unadjusted.v1",
    available_date: str | None = None,
    source_identity: str = "synthetic-price-source.v1",
) -> PricePoint:
    return PricePoint(
        instrument_id=instrument,
        trade_date=day,
        state=state,
        price=price,
        source_identity=source_identity,
        currency=currency,
        unit=unit,
        price_basis=price_basis,
        corporate_action_basis=corporate_action_basis,
        available_date=available_date,
    )


def _market(
    decision: date,
    codes: tuple[str, ...],
    *,
    benchmark_id: str | None = "TAIEX",
    end_overrides: dict[tuple[str, int], tuple[Decimal | None, str, str | None]] | None = None,
    benchmark_basis: str = "raw_close.v1",
    target_currency: str = "TWD",
    target_basis: str = "raw_close.v1",
    benchmark_currency: str = "TWD",
) -> tuple[Calendar, list[PricePoint], BenchmarkSpec | None]:
    dates = _sessions(decision, 20)
    points: list[PricePoint] = []
    overrides = end_overrides or {}
    for code in codes:
        points.append(
            _point(code, dates[0], Decimal("100.00"), currency=target_currency, price_basis=target_basis)
        )
        for index, day in enumerate(dates[1:], start=1):
            override = overrides.get((code, index))
            if override is None:
                points.append(
                    _point(
                        code,
                        day,
                        Decimal("100.00") + Decimal(index),
                        currency=target_currency,
                        price_basis=target_basis,
                    )
                )
            else:
                value, state, available_date = override
                points.append(
                    _point(
                        code,
                        day,
                        value,
                        state=state,
                        available_date=available_date,
                        currency=target_currency,
                        price_basis=target_basis,
                    )
                )
    benchmark = None
    if benchmark_id is not None:
        benchmark = BenchmarkSpec(
            instrument_id=benchmark_id,
            currency=benchmark_currency,
            unit="index_points",
            price_basis=benchmark_basis,
            corporate_action_basis="unadjusted.v1",
            source_identity="synthetic-benchmark-source.v1",
        )
        points.append(
            _point(
                benchmark_id,
                dates[0],
                Decimal("20000"),
                unit="index_points",
                price_basis=benchmark_basis,
                currency=benchmark_currency,
                source_identity="synthetic-benchmark-source.v1",
            )
        )
        for index, day in enumerate(dates[1:], start=1):
            override = overrides.get((benchmark_id, index))
            if override is None:
                value, state, available = Decimal("20000") + Decimal(index * 10), "available", None
            else:
                value, state, available = override
            points.append(
                _point(
                    benchmark_id,
                    day,
                    value,
                state=state,
                unit="index_points",
                currency=benchmark_currency,
                    price_basis=benchmark_basis,
                    available_date=available,
                    source_identity="synthetic-benchmark-source.v1",
                )
            )
    calendar = Calendar(
        trading_dates=dates,
        known=True,
        complete=True,
        coverage_start=dates[0],
        coverage_end=dates[-1],
        source_identity="synthetic-weekdays-calendar.v1",
        available_date=None,
    )
    return calendar, points, benchmark


def _costs(
    *,
    target_entry: int | None = 0,
    target_exit: int | None = 0,
    benchmark_entry: int | None = 0,
    benchmark_exit: int | None = 0,
) -> CostPolicy:
    return CostPolicy(
        version="synthetic-costs.v1",
        formula_id="proportional_entry_add_exit_deduct.v1",
        target_entry_bp=target_entry,
        target_exit_bp=target_exit,
        benchmark_entry_bp=benchmark_entry,
        benchmark_exit_bp=benchmark_exit,
    )


def _saved_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _, _, capture = child_fixture(tmp_path)
    writer = BoundedRuleResearchCaptureWriter(tmp_path / "child-receipts")
    monkeypatch.setattr(writer, "_free_bytes", lambda: SAFETY_RESERVE_BYTES + 1024**3)
    saved = writer.write(capture, revalidate=lambda: capture)
    package = writer.read(saved["receipt"]["capture_identity_sha256"])
    return capture, package


def _ready_member(result: dict, stock_code: str = "2382") -> dict:
    return next(
        member
        for member in result["members"]
        if member["stock_code"] == stock_code and member["method_id"] == "daily_market.close_above_ma20"
    )


def test_matured_decimal_returns_costs_sign_and_population_are_explicit(tmp_path, monkeypatch):
    capture, package = _saved_child(tmp_path, monkeypatch)
    decision = date.fromisoformat(capture.to_dict()["decision_date"])
    calendar, points, benchmark = _market(
        decision,
        ("2382", "3034", "1477"),
        end_overrides={
            ("2382", 5): (Decimal("100.005"), "available", None),
            ("2382", 10): (Decimal("100.015"), "available", None),
            ("2382", 20): (Decimal("99.00"), "available", None),
        },
    )
    as_of = calendar.trading_dates[-1]
    policy = _costs()
    normal = build_rule_research_forward_outcome(
        package,
        decision_date=decision.isoformat(),
        calendar=calendar,
        prices=points,
        benchmark=benchmark,
        cost_policy=policy,
        as_of_date=as_of,
    ).to_dict()
    with localcontext() as context:
        context.prec = 3
        context.rounding = ROUND_DOWN
        constrained = build_rule_research_forward_outcome(
            package,
            decision_date=decision.isoformat(),
            calendar=calendar,
            prices=points,
            benchmark=benchmark,
            cost_policy=policy,
            as_of_date=as_of,
        ).to_dict()
    assert normal == constrained
    member = _ready_member(normal)
    h5, h10, h20 = member["horizons"]
    assert h5["calculation_status"] == "ready_research"
    assert h5["target"]["net_return"]["decimal"] == "0.00005"
    assert h5["target"]["net_return"]["integer_bp_half_even"] == 0
    assert h5["target"]["net_sign_label"] == "positive"
    assert h10["target"]["net_return"]["integer_bp_half_even"] == 2
    assert h10["target"]["net_sign_label"] == "positive"
    assert h20["target"]["net_sign_label"] == "negative"
    assert h5["comparison"]["net_excess_sign_label"] == "negative"
    assert h5["qualification"]["historical_pit_eligible"] is False
    assert h5["qualification"]["status"] == "ineligible"
    assert h5["input_availability"]["as_of_status"] == "unknown"
    assert h5["input_availability"]["aggregate_available_date"] is None
    assert h5["measurement_scope"] == "endpoint_close_to_close_only"
    assert h5["path_metrics_available"] is False
    assert normal["population"]["population_count"] == 3
    assert normal["population"]["selection_status"] == "unknown"
    assert normal["population"]["selected_count"] is None
    assert all(item["selection_status"] == "unknown" for item in normal["members"])
    assert all(item["capture_selected_marker"] is False for item in normal["members"])


def test_pending_unknown_calendar_missing_suspension_and_late_price(tmp_path, monkeypatch):
    capture, package = _saved_child(tmp_path, monkeypatch)
    decision = date.fromisoformat(capture.to_dict()["decision_date"])
    calendar, points, benchmark = _market(decision, ("2382", "3034", "1477"))
    early_as_of = calendar.trading_dates[3]
    pending = build_rule_research_forward_outcome(
        package,
        decision_date=decision.isoformat(),
        calendar=calendar,
        prices=points,
        benchmark=benchmark,
        cost_policy=_costs(),
        as_of_date=early_as_of,
    ).to_dict()
    h5 = _ready_member(pending)["horizons"][0]
    assert h5["calculation_status"] == "pending"
    assert h5["target"]["gross_return"]["decimal"] is None
    assert h5["expected_end_date"] == calendar.trading_dates[5]

    missing_points = [
        point
        for point in points
        if not (point.instrument_id == "2382" and point.trade_date == calendar.trading_dates[5])
    ]
    missing = build_rule_research_forward_outcome(
        package,
        decision_date=decision.isoformat(),
        calendar=calendar,
        prices=missing_points,
        benchmark=benchmark,
        cost_policy=_costs(),
        as_of_date=calendar.trading_dates[-1],
    ).to_dict()
    missing_h5 = _ready_member(missing)["horizons"][0]
    assert missing_h5["calculation_status"] == "unavailable"
    assert missing_h5["target"]["gross_return"]["decimal"] is None
    assert "target_end_price_missing" in missing_h5["reason_codes"]

    halted_points = [
        point
        for point in points
        if not (point.instrument_id == "2382" and point.trade_date == calendar.trading_dates[5])
    ]
    halted_points.append(
        _point("2382", calendar.trading_dates[5], None, state="suspended")
    )
    halted = build_rule_research_forward_outcome(
        package,
        decision_date=decision.isoformat(),
        calendar=calendar,
        prices=halted_points,
        benchmark=benchmark,
        cost_policy=_costs(),
        as_of_date=calendar.trading_dates[-1],
    ).to_dict()
    halted_h5 = _ready_member(halted)["horizons"][0]
    assert halted_h5["calculation_status"] == "unavailable"
    assert "target_end_price_suspended" in halted_h5["reason_codes"]

    unknown_calendar = build_rule_research_forward_outcome(
        package,
        decision_date=decision.isoformat(),
        calendar=_unknown_calendar(),
        prices=points,
        benchmark=benchmark,
        cost_policy=_costs(),
        as_of_date=calendar.trading_dates[-1],
    ).to_dict()
    assert all(
        horizon["calculation_status"] == "unknown"
        and horizon["expected_end_date"] is None
        for horizon in _ready_member(unknown_calendar)["horizons"]
    )

    late_points = [
        point
        for point in points
        if not (point.instrument_id == "2382" and point.trade_date == calendar.trading_dates[5])
    ]
    late_points.append(
        _point(
            "2382",
            calendar.trading_dates[5],
            Decimal("105"),
            available_date=calendar.trading_dates[6],
        )
    )
    late = build_rule_research_forward_outcome(
        package,
        decision_date=decision.isoformat(),
        calendar=calendar,
        prices=late_points,
        benchmark=benchmark,
        cost_policy=_costs(),
        as_of_date=calendar.trading_dates[5],
    ).to_dict()
    late_h5 = _ready_member(late)["horizons"][0]
    assert late_h5["calculation_status"] == "unknown"
    assert late_h5["target"]["gross_return"]["decimal"] is None
    assert "target_end_price_not_available_as_of" in late_h5["reason_codes"]


def test_missing_cost_and_benchmark_basis_do_not_invent_net_or_excess(tmp_path, monkeypatch):
    capture, package = _saved_child(tmp_path, monkeypatch)
    decision = date.fromisoformat(capture.to_dict()["decision_date"])
    calendar, points, benchmark = _market(decision, ("2382", "3034", "1477"))
    unknown_benchmark_cost = _costs(benchmark_entry=None, benchmark_exit=None)
    result = build_rule_research_forward_outcome(
        package,
        decision_date=decision.isoformat(),
        calendar=calendar,
        prices=points,
        benchmark=benchmark,
        cost_policy=unknown_benchmark_cost,
        as_of_date=calendar.trading_dates[-1],
    ).to_dict()
    h5 = _ready_member(result)["horizons"][0]
    assert h5["target"]["net_return"]["decimal"] is not None
    assert h5["target"]["net_sign_label"] is not None
    assert h5["benchmark"]["gross_return"]["decimal"] is not None
    assert h5["benchmark"]["net_return"]["decimal"] is None
    assert h5["comparison"]["gross_excess_return"]["decimal"] is not None
    assert h5["comparison"]["net_excess_return"]["decimal"] is None
    assert h5["comparison"]["net_excess_sign_label"] is None

    mismatch_calendar, mismatch_points, mismatch_benchmark = _market(
        decision,
        ("2382", "3034", "1477"),
        benchmark_basis="adjusted_close.v1",
    )
    mismatch = build_rule_research_forward_outcome(
        package,
        decision_date=decision.isoformat(),
        calendar=mismatch_calendar,
        prices=mismatch_points,
        benchmark=mismatch_benchmark,
        cost_policy=_costs(),
        as_of_date=mismatch_calendar.trading_dates[-1],
    ).to_dict()
    mismatch_h5 = _ready_member(mismatch)["horizons"][0]
    assert mismatch_h5["benchmark"]["gross_return"]["decimal"] is not None
    assert mismatch_h5["comparison"]["status"] == "incompatible_basis"
    assert mismatch_h5["comparison"]["basis_comparable"] is False
    assert mismatch_h5["comparison"]["gross_excess_return"]["decimal"] is None
    assert mismatch_h5["comparison"]["net_excess_return"]["decimal"] is None

    target_cost_unknown = build_rule_research_forward_outcome(
        package,
        decision_date=decision.isoformat(),
        calendar=calendar,
        prices=points,
        benchmark=benchmark,
        cost_policy=_costs(target_entry=None),
        as_of_date=calendar.trading_dates[-1],
    ).to_dict()
    target_h5 = _ready_member(target_cost_unknown)["horizons"][0]
    assert target_h5["target"]["gross_return"]["decimal"] is not None
    assert target_h5["target"]["net_return"]["decimal"] is None
    assert target_h5["target"]["net_sign_label"] is None
    assert target_h5["comparison"]["net_excess_return"]["decimal"] is None

    unknown_calendar, unknown_points, unknown_benchmark = _market(
        decision,
        ("2382", "3034", "1477"),
        target_basis="unknown",
        benchmark_basis="unknown",
    )
    assert unknown_benchmark is not None
    unknown_benchmark = BenchmarkSpec(
        instrument_id=unknown_benchmark.instrument_id,
        currency=unknown_benchmark.currency,
        unit=unknown_benchmark.unit,
        price_basis="unknown",
        corporate_action_basis=unknown_benchmark.corporate_action_basis,
        source_identity=unknown_benchmark.source_identity,
    )
    unknown_basis = build_rule_research_forward_outcome(
        package,
        decision_date=decision.isoformat(),
        calendar=unknown_calendar,
        prices=unknown_points,
        benchmark=unknown_benchmark,
        cost_policy=_costs(),
        as_of_date=unknown_calendar.trading_dates[-1],
    ).to_dict()
    unknown_basis_h5 = _ready_member(unknown_basis)["horizons"][0]
    assert unknown_basis_h5["comparison"]["status"] == "basis_unknown"
    assert unknown_basis_h5["comparison"]["gross_excess_return"]["decimal"] is None

    mismatched_source_points = [
        _point(
            point.instrument_id,
            point.trade_date,
            point.price,
            state=point.state,
            currency=point.currency,
            unit=point.unit,
            price_basis=point.price_basis,
            corporate_action_basis=point.corporate_action_basis,
            available_date=point.available_date,
            source_identity="different-benchmark-source.v1" if point.instrument_id == "TAIEX" else point.source_identity,
        )
        for point in points
    ]
    with pytest.raises(ForwardOutcomeError, match="benchmark_point_source_mismatch"):
        build_rule_research_forward_outcome(
            package,
            decision_date=decision.isoformat(),
            calendar=calendar,
            prices=mismatched_source_points,
            benchmark=benchmark,
            cost_policy=_costs(),
            as_of_date=calendar.trading_dates[-1],
        )

    with pytest.raises(ForwardOutcomeError, match="benchmark_type_invalid"):
        build_rule_research_forward_outcome(
            package,
            decision_date=decision.isoformat(),
            calendar=calendar,
            prices=points,
            benchmark={"instrument_id": "TAIEX"},  # type: ignore[arg-type]
            cost_policy=_costs(),
            as_of_date=calendar.trading_dates[-1],
        )
    with pytest.raises(ForwardOutcomeError, match="cost_policy_type_invalid"):
        build_rule_research_forward_outcome(
            package,
            decision_date=decision.isoformat(),
            calendar=calendar,
            prices=points,
            benchmark=benchmark,
            cost_policy={"target_entry_bp": 0},  # type: ignore[arg-type]
            as_of_date=calendar.trading_dates[-1],
        )


def test_calendar_coverage_source_revisions_duplicate_points_and_numeric_types(tmp_path, monkeypatch):
    capture, package = _saved_child(tmp_path, monkeypatch)
    decision = date.fromisoformat(capture.to_dict()["decision_date"])
    calendar, points, benchmark = _market(decision, ("2382", "3034", "1477"))
    short_dates = _sessions(decision, 19)
    short_calendar = Calendar(
        trading_dates=short_dates,
        known=True,
        complete=True,
        coverage_start=short_dates[0],
        coverage_end=short_dates[-1],
        source_identity="synthetic-short-calendar.v1",
        available_date=None,
    )
    partial = build_rule_research_forward_outcome(
        package,
        decision_date=decision.isoformat(),
        calendar=short_calendar,
        prices=points,
        benchmark=benchmark,
        cost_policy=_costs(),
        as_of_date=calendar.trading_dates[-1],
    ).to_dict()
    assert _ready_member(partial)["horizons"][2]["calculation_status"] == "unknown"
    assert "calendar_horizon_coverage_insufficient" in _ready_member(partial)["horizons"][2]["reason_codes"]

    duplicate_points = list(points)
    duplicate_points.pop(1)
    with pytest.raises(ForwardOutcomeError, match="duplicate_price_point"):
        build_rule_research_forward_outcome(
            package,
            decision_date=decision.isoformat(),
            calendar=calendar,
            prices=[*duplicate_points, points[0]],
            benchmark=benchmark,
            cost_policy=_costs(),
            as_of_date=calendar.trading_dates[-1],
        )
    with pytest.raises(ForwardOutcomeError, match="price_must_be_decimal"):
        _point("2382", calendar.trading_dates[0], 100.0)  # type: ignore[arg-type]
    with pytest.raises(ForwardOutcomeError, match="target_entry_bp_invalid"):
        _costs(target_entry=True)  # type: ignore[arg-type]
    with pytest.raises(ForwardOutcomeError, match="price_available_before_trade_date"):
        _point(
            "2382",
            calendar.trading_dates[0],
            Decimal("100"),
            available_date="2026-01-01",
        )

    alternate_scale_points = [
        _point(
            point.instrument_id,
            point.trade_date,
            None if point.price is None else Decimal(_decimal_scale_variant(point.price)),
            state=point.state,
            currency=point.currency,
            unit=point.unit,
            price_basis=point.price_basis,
            corporate_action_basis=point.corporate_action_basis,
            available_date=point.available_date,
            source_identity=point.source_identity,
        )
        for point in points
    ]
    base_result = build_rule_research_forward_outcome(
        package,
        decision_date=decision.isoformat(),
        calendar=calendar,
        prices=points,
        benchmark=benchmark,
        cost_policy=_costs(),
        as_of_date=calendar.trading_dates[-1],
    )
    scale_result = build_rule_research_forward_outcome(
        package,
        decision_date=decision.isoformat(),
        calendar=calendar,
        prices=alternate_scale_points,
        benchmark=benchmark,
        cost_policy=_costs(),
        as_of_date=calendar.trading_dates[-1],
    )
    assert base_result.result_identity_sha256 == scale_result.result_identity_sha256
    revised = list(points)
    old = next(item for item in revised if item.instrument_id == "2382" and item.trade_date == calendar.trading_dates[5])
    revised.remove(old)
    revised.append(_point("2382", old.trade_date, Decimal("123.45")))
    revised_result = build_rule_research_forward_outcome(
        package,
        decision_date=decision.isoformat(),
        calendar=calendar,
        prices=revised,
        benchmark=benchmark,
        cost_policy=_costs(),
        as_of_date=calendar.trading_dates[-1],
    )
    assert revised_result.result_identity_sha256 != base_result.result_identity_sha256
    assert base_result.to_dict()["result_identity_sha256"] == base_result.result_identity_sha256

    maximum = Decimal("9" * 64 + "E+64")
    minimum = Decimal("1E-64")
    extreme_points = list(points)
    entry = next(item for item in extreme_points if item.instrument_id == "2382" and item.trade_date == calendar.trading_dates[0])
    end = next(item for item in extreme_points if item.instrument_id == "2382" and item.trade_date == calendar.trading_dates[5])
    extreme_points.remove(entry)
    extreme_points.remove(end)
    extreme_points.extend(
        [
            _point("2382", entry.trade_date, minimum),
            _point("2382", end.trade_date, maximum),
        ]
    )
    extreme = build_rule_research_forward_outcome(
        package,
        decision_date=decision.isoformat(),
        calendar=calendar,
        prices=extreme_points,
        benchmark=benchmark,
        cost_policy=_costs(),
        as_of_date=calendar.trading_dates[-1],
    ).to_dict()
    assert abs(_ready_member(extreme)["horizons"][0]["target"]["gross_return"]["integer_bp_half_even"]) > 10**195


def test_missing_benchmark_endpoint_makes_aggregate_availability_unknown_without_hiding_target(tmp_path, monkeypatch):
    capture, package = _saved_child(tmp_path, monkeypatch)
    decision = date.fromisoformat(capture.to_dict()["decision_date"])
    calendar, points, benchmark = _market(decision, ("2382", "3034", "1477"))
    declared_available = decision.isoformat()
    calendar = Calendar(
        trading_dates=calendar.trading_dates,
        known=True,
        complete=True,
        coverage_start=calendar.coverage_start,
        coverage_end=calendar.coverage_end,
        source_identity=calendar.source_identity,
        available_date=declared_available,
    )
    points = [
        PricePoint(
            instrument_id=point.instrument_id,
            trade_date=point.trade_date,
            state=point.state,
            price=point.price,
            source_identity=point.source_identity,
            currency=point.currency,
            unit=point.unit,
            price_basis=point.price_basis,
            corporate_action_basis=point.corporate_action_basis,
            available_date=max(declared_available, point.trade_date),
        )
        for point in points
        if not (point.instrument_id == "TAIEX" and point.trade_date == calendar.trading_dates[5])
    ]
    result = build_rule_research_forward_outcome(
        package,
        decision_date=decision.isoformat(),
        calendar=calendar,
        prices=points,
        benchmark=benchmark,
        cost_policy=_costs(),
        as_of_date=calendar.trading_dates[-1],
    ).to_dict()
    h5 = _ready_member(result)["horizons"][0]
    assert h5["target"]["gross_return"]["decimal"] is not None
    assert h5["benchmark"]["gross_return"]["decimal"] is None
    assert h5["input_availability"]["target"]["as_of_status"] == "known_by_as_of"
    assert h5["input_availability"]["benchmark"]["as_of_status"] == "unknown"
    assert h5["input_availability"]["aggregate_available_date"] is None


def _decimal_scale_variant(value: Decimal) -> str:
    text = format(value, "f")
    return text if "." in text else text + ".00"


@pytest.mark.parametrize("failed_batch_index", [0, 1])
def test_parent_exact_children_full_denominator_and_uncaptured_are_preserved(tmp_path, monkeypatch, failed_batch_index):
    args, _ = parent_fixture(tmp_path, monkeypatch, included=17, excluded=2)
    produced = __import__("app_module.rule_research_parent_capture", fromlist=["produce_parent_rule_samples"]).produce_parent_rule_samples(**args)
    assert produced["status"] == "complete", produced
    parent_identity = produced["parent_capture"]["receipt"]["capture_identity_sha256"]
    parent_writer = BoundedRuleResearchParentWriter(Path(args["capture_root"]) / "parents")
    parent_package = parent_writer.read(parent_identity)
    parent_body = parent_package["capture"]
    child_writer = BoundedRuleResearchCaptureWriter(
        Path(args["capture_root"]) / "samples" / parent_body["plan_sha256"]
    )
    children = [
        child_writer.read(batch["capture_identity_sha256"])
        for batch in parent_body["batches"]
        if batch["status"] == "captured"
    ]
    decision = date.fromisoformat(parent_body["universe"]["value"]["as_of_date"])
    codes = tuple(parent_body["universe"]["value"]["included_stock_codes"] + [
        item["stock_code"] for item in parent_body["universe"]["value"]["excluded_stock_codes"]
    ])
    calendar, points, benchmark = _market(decision, codes)
    parent_as_of = max(calendar.trading_dates[-1], parent_body["observed_at"][:10])
    result = build_parent_rule_research_forward_outcome(
        parent_package,
        children,
        decision_date=decision.isoformat(),
        calendar=calendar,
        prices=points,
        benchmark=benchmark,
        cost_policy=_costs(),
        as_of_date=parent_as_of,
    ).to_dict()
    assert result["population"]["population_count"] == 19
    assert result["population"]["included_denominator"] == 17
    assert result["population"]["represented_denominator"] == 19
    assert all(sum(counts.values()) == 19 for counts in result["population"]["method_state_counts"].values())
    assert all(result["population"]["method_state_counts"][method]["excluded"] == 2 for method in result["population"]["method_state_counts"])
    assert result["population"]["selection_status"] == "unknown"
    assert result["population"]["selected_count"] is None

    partial_body = deepcopy(parent_body)
    failed = partial_body["batches"][failed_batch_index]
    failed.update(
        {
            "status": "failed",
            "manifest_sha256": None,
            "capture_identity_sha256": None,
            "production_status": "interrupted_unknown",
            "sample_capture_status": "not_started",
            "error_code": "synthetic_batch_not_captured",
        }
    )
    partial_body["status"] = "incomplete"
    partial_body["source_status"] = "validated_transaction"
    partial_body["capture_identity_sha256"] = _parent_identity(partial_body)
    partial_model = RuleResearchParentCapture(json.dumps(partial_body, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    partial_model.to_dict()
    partial_raw = partial_model.body_json.encode("utf-8")
    partial_receipt = parent_writer._make_receipt(partial_body, partial_raw)
    partial_parent_package = {"capture": partial_model.to_dict(), "receipt": partial_receipt}
    partial_children = [child for child in children if child["capture"]["capture_identity_sha256"] != parent_body["batches"][failed_batch_index]["capture_identity_sha256"]]
    partial_result = build_parent_rule_research_forward_outcome(
        partial_parent_package,
        partial_children,
        decision_date=decision.isoformat(),
        calendar=calendar,
        prices=points,
        benchmark=benchmark,
        cost_policy=_costs(),
        as_of_date=parent_as_of,
    ).to_dict()
    assert partial_result["population"]["population_count"] == 19
    assert all(sum(counts.values()) == 19 for counts in partial_result["population"]["method_state_counts"].values())
    for counts in partial_result["population"]["method_state_counts"].values():
        assert counts["uncaptured"] > 0
    uncaptured_exclusions = [
        member for member in partial_result["members"]
        if member["declared_excluded"] and member["capture_status"] == "uncaptured"
    ]
    assert {member["stock_code"] for member in uncaptured_exclusions} == {
        item["stock_code"] for item in failed["excluded_stock_codes"]
    }
    assert len(uncaptured_exclusions) == 2 * len(failed["excluded_stock_codes"])
    assert all(
        member["member_state"] == "uncaptured"
        and member["declared_excluded"] is True
        and member["declared_exclusion_reason"]
        for member in uncaptured_exclusions
    )
    assert all(
        member["selection_status"] == "unknown"
        for member in partial_result["members"]
    )

    with pytest.raises(ForwardOutcomeError, match="parent_exact_child_count_mismatch"):
        build_parent_rule_research_forward_outcome(
            parent_package,
            children[:-1],
            decision_date=decision.isoformat(),
            calendar=calendar,
            prices=points,
            benchmark=benchmark,
            cost_policy=_costs(),
            as_of_date=parent_as_of,
        )


def test_receipt_tampering_is_rejected_and_new_process_identity_reproduces(tmp_path, monkeypatch):
    capture, package = _saved_child(tmp_path, monkeypatch)
    decision = date.fromisoformat(capture.to_dict()["decision_date"])
    calendar, points, benchmark = _market(decision, ("2382", "3034", "1477"))
    arguments = {
        "decision_date": decision.isoformat(),
        "calendar": calendar,
        "prices": points,
        "benchmark": benchmark,
        "cost_policy": _costs(),
        "as_of_date": calendar.trading_dates[-1],
    }
    expected = build_rule_research_forward_outcome(package, **arguments)
    broken = deepcopy(package)
    broken["receipt"]["capture_sha256"] = "0" * 64
    with pytest.raises(ForwardOutcomeError, match="child_receipt_mismatch"):
        build_rule_research_forward_outcome(broken, **arguments)

    forged = expected.to_dict()
    forged["training_eligible"] = True
    stable = {key: value for key, value in forged.items() if key != "result_identity_sha256"}
    forged["result_identity_sha256"] = hashlib.sha256(
        json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    with pytest.raises(ForwardOutcomeError, match="outcome_research_policy_invalid"):
        ForwardOutcomeProjection(
            json.dumps(forged, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        ).to_dict()

    serialized = {
        "package": package,
        "decision_date": decision.isoformat(),
        "calendar": calendar.to_payload(),
        "prices": [point.to_payload() for point in points],
        "benchmark": benchmark.to_payload() if benchmark else None,
        "cost_policy": _costs().to_payload(),
        "as_of_date": calendar.trading_dates[-1],
    }
    input_path = tmp_path / "new_process_input.json"
    input_path.write_text(json.dumps(serialized, ensure_ascii=False), encoding="utf-8")
    script = """
import json, sys
from pathlib import Path
from app_module.rule_research_forward_outcome import Calendar, BenchmarkSpec, CostPolicy, PricePoint, build_rule_research_forward_outcome
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
calendar = Calendar(**{**payload['calendar'], 'trading_dates': tuple(payload['calendar']['trading_dates'])})
prices = [PricePoint(**{**point, 'price': None if point['price'] is None else __import__('decimal').Decimal(point['price'])}) for point in payload['prices']]
benchmark = BenchmarkSpec(**payload['benchmark']) if payload['benchmark'] else None
cost_policy = CostPolicy(**payload['cost_policy']) if payload['cost_policy'] else None
result = build_rule_research_forward_outcome(payload['package'], decision_date=payload['decision_date'], calendar=calendar, prices=prices, benchmark=benchmark, cost_policy=cost_policy, as_of_date=payload['as_of_date'])
print(result.body_json)
"""
    process = subprocess.run(
        [sys.executable, "-c", script, str(input_path)],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=30,
    )
    assert process.stdout.strip() == expected.body_json
