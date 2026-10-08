"""個人 H20 同次來源價格旁路的合成驗證。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import pickle
from pathlib import Path
from typing import Any, Mapping

import pytest


def _install_observed_public_ports(
    saved: Mapping[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    *,
    fail_after_observe: bool = False,
) -> tuple[list[tuple[Mapping[str, object], Mapping[str, object]]], list[str]]:
    import scripts.scheduled.run_personal_current_observed_h20_daily as runner

    actual_source_port = runner._source_port
    contract_verifier = saved["contract_fixture"]["verifier"]
    observations: list[tuple[Mapping[str, object], Mapping[str, object]]] = []
    observation_errors: list[str] = []

    class ObservedPort:
        def __init__(self, observer: object) -> None:
            self._observer = observer

        def observe(self, binding: Mapping[str, object], raw: object, result: Mapping[str, object]) -> None:
            observations.append((deepcopy(dict(binding)), deepcopy(dict(result))))
            from app_module.recommendation.personal_h20_price_chart import _freeze_observation

            try:
                _freeze_observation(binding, raw, result)
            except Exception as exc:
                observation_errors.append(f"{type(exc).__name__}:{exc}")
            if self._observer is None:
                return
            self._observer.observe(binding, raw, result)
            if fail_after_observe:
                raise RuntimeError("synthetic_chart_observer_failure")

        def reject(self, reason_code: str) -> None:
            if self._observer is not None:
                self._observer.reject(reason_code)

    def public_ports(*, read_session_resolver=None, raw_snapshot_observer=None):
        observer = ObservedPort(raw_snapshot_observer)

        def source_verifier(binding: Mapping[str, Any]) -> Mapping[str, Any]:
            return actual_source_port(
                binding,
                read_session_resolver=read_session_resolver,
                raw_snapshot_observer=observer,
            )

        return {
            "source_verifier": source_verifier,
            "contract_verifier": contract_verifier,
        }

    monkeypatch.setattr(runner, "personal_current_observed_h20_read_ports", public_ports)
    return observations, observation_errors


def test_price_chart_uses_two_public_source_observations_and_exact_saved_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_module.recommendation.personal_h20_price_chart import (
        PersonalH20PriceChartError,
        PersonalH20VerifiedPriceChartV1,
        assert_personal_h20_price_chart_projection,
        assert_personal_h20_price_chart_projection_binding,
        project_personal_h20_verified_cohort_price_chart,
    )
    from app_module.recommendation.personal_h20_verified_cohort_view import (
        project_personal_h20_verified_cohort_selection,
    )
    from app_module.stock_research_product_summary import build_stock_research_product_summary
    from app_module.recommendation.personal_h20_verified_cohort_view import (
        PersonalH20VerifiedCohortView,
    )
    import scripts.scheduled.personal_h20_daily_hook as hook
    from tests.test_personal_h20_verified_cohort_view import _saved_store, _selection

    saved, private_root = _saved_store(tmp_path, monkeypatch)
    observations, observation_errors = _install_observed_public_ports(saved, monkeypatch)

    view = hook.read_personal_h20_verified_cohort_view(
        saved["activation"].config_path,
        market_root=Path(saved["market_root"]),
        sqlite_read_root=private_root,
    )

    assert type(view) is PersonalH20VerifiedCohortView
    assert view.price_chart is not None
    assert type(view.price_chart) is PersonalH20VerifiedPriceChartV1
    assert len(observations) == 2  # 一個共用 binding：初讀一次、終態重驗一次。
    for binding, result in observations:
        assert dict(result) == dict(binding)
        assert set(result["feature_rows_by_symbol"]) == set(binding["symbols"])
    row = view.cohort.rows[0]
    assert (row.symbol, row.status, row.gross_return_bp) == ("2382", "available", 1234)
    selection = _selection(view.cohort, row)
    projection = project_personal_h20_verified_cohort_price_chart(view, selection)
    assert projection.status == "available", observation_errors
    assert projection.stock_code == row.symbol
    assert projection.capture_sha256 == row.capture_sha256
    assert projection.source_date == row.source_date
    assert projection.feature_as_of_date == row.feature_as_of_date
    assert projection.points
    assert len(projection.points) <= 120
    assert all(point.trading_date <= row.feature_as_of_date for point in projection.points)
    with pytest.raises(TypeError, match="cannot_be_serialized"):
        pickle.dumps(view.price_chart)
    with pytest.raises(TypeError, match="cannot_be_serialized"):
        pickle.dumps(projection)

    evidence = project_personal_h20_verified_cohort_selection(view, selection)
    from tests.test_stock_research_product_summary import _saved_h20_report

    context = dict(_saved_h20_report().research_context)
    context.update({
        "source_kind": "personal_h20_saved_cohort",
        "stock_code": row.symbol,
        "source_id": row.prediction_id,
        "source_version": view.cohort.contract_hash,
        "decision_date": row.decision_date,
        "data_date": row.source_date,
        "profile_id": view.cohort.candidate_id,
        "source_snapshot_id": view.cohort.cycle_id,
        "source_snapshot_hash": view.cohort.manifest_sha256,
    })
    report = replace(_saved_h20_report(), research_context=context)
    summary = build_stock_research_product_summary(
        report,
        evidence,
        h20_price_chart=projection,
    )
    assert any("同次原快照 OHLCV 已核驗" in line for line in summary.status_lines)

    unrelated = dict(context)
    unrelated["source_kind"] = "explicit_latest_stock_research"
    with pytest.raises(ValueError, match="不可用於一般或目前行情報告"):
        build_stock_research_product_summary(
            replace(report, research_context=unrelated),
            evidence,
            h20_price_chart=projection,
        )

    wrong_date = replace(evidence, source_date="2026-10-04")
    with pytest.raises(ValueError):
        build_stock_research_product_summary(report, wrong_date, h20_price_chart=projection)

    kwargs = {
        "stock_code": row.symbol,
        "source_kind": "personal_h20_saved_cohort",
        "manifest_sha256": view.cohort.manifest_sha256,
        "decision_date": view.cohort.decision_date,
        "candidate_id": view.cohort.candidate_id,
        "contract_hash": view.cohort.contract_hash,
        "cycle_id": view.cohort.cycle_id,
        "sample_id": row.sample_id,
        "prediction_id": row.prediction_id,
        "source_date": row.source_date,
        "feature_as_of_date": row.feature_as_of_date,
        "capture_sha256": row.capture_sha256,
    }
    assert_personal_h20_price_chart_projection_binding(projection, **kwargs)
    with pytest.raises(PersonalH20PriceChartError, match="context_mismatch"):
        assert_personal_h20_price_chart_projection_binding(
            projection,
            **{**kwargs, "stock_code": "2330"},
        )
    with pytest.raises(PersonalH20PriceChartError, match="context_mismatch"):
        assert_personal_h20_price_chart_projection_binding(
            projection,
            **{**kwargs, "capture_sha256": "sha256:" + "0" * 64},
        )
    with pytest.raises(PersonalH20PriceChartError, match="context_mismatch"):
        assert_personal_h20_price_chart_projection_binding(
            projection,
            **{**kwargs, "decision_date": "2026-10-08"},
        )

    original_capture = projection.capture_sha256
    object.__setattr__(projection, "capture_sha256", "sha256:" + "0" * 64)
    try:
        with pytest.raises(PersonalH20PriceChartError, match="seal_mismatch"):
            assert_personal_h20_price_chart_projection(projection)
    finally:
        object.__setattr__(projection, "capture_sha256", original_capture)


def test_chart_observer_failure_keeps_valid_h20_row_and_marks_chart_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_module.recommendation.personal_h20_verified_cohort_view import (
        PersonalH20VerifiedCohortView,
    )
    import scripts.scheduled.personal_h20_daily_hook as hook
    from tests.test_personal_h20_verified_cohort_view import _saved_store

    saved, private_root = _saved_store(tmp_path, monkeypatch)
    _observations, _errors = _install_observed_public_ports(
        saved, monkeypatch, fail_after_observe=True
    )

    view = hook.read_personal_h20_verified_cohort_view(
        saved["activation"].config_path,
        market_root=Path(saved["market_root"]),
        sqlite_read_root=private_root,
    )

    assert type(view) is PersonalH20VerifiedCohortView
    row = view.cohort.rows[0]
    assert row.status == "available"
    assert row.gross_return_bp == 1234
    assert view.price_chart is not None
    assert view.price_chart.status == "unknown"
    assert view.price_chart.reason_code == "source_rows_unknown"
    assert view.price_chart.series[0].reason_code == "chart_observer_failed"


def test_chart_capacity_limit_marks_only_chart_unknown_and_preserves_h20_estimate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_module.recommendation.personal_h20_price_chart as chart_module
    import scripts.scheduled.personal_h20_daily_hook as hook
    from app_module.recommendation.personal_h20_price_chart import (
        project_personal_h20_verified_cohort_price_chart,
    )
    from app_module.recommendation.personal_h20_verified_cohort_view import (
        project_personal_h20_verified_cohort_selection,
    )
    from tests.test_personal_h20_verified_cohort_view import _saved_store, _selection

    saved, private_root = _saved_store(tmp_path, monkeypatch)
    _install_observed_public_ports(saved, monkeypatch)
    monkeypatch.setattr(chart_module, "MAX_PERSONAL_H20_PRICE_SERIES_BYTES", 1)

    view = hook.read_personal_h20_verified_cohort_view(
        saved["activation"].config_path,
        market_root=Path(saved["market_root"]),
        sqlite_read_root=private_root,
    )

    row = view.cohort.rows[0]
    assert row.status == "available"
    assert row.gross_return_bp == 1234
    assert view.price_chart is not None
    assert view.price_chart.status == "unknown"
    assert view.price_chart.reason_code == "chart_capacity_exceeded"
    assert view.price_chart.series[0].status == "unknown"
    assert view.price_chart.series[0].reason_code == "chart_capacity_exceeded"

    selection = _selection(view.cohort, row)
    evidence = project_personal_h20_verified_cohort_selection(view, selection)
    projection = project_personal_h20_verified_cohort_price_chart(view, selection)
    assert evidence.gross_return_bp == 1234
    assert projection is not None
    assert projection.status == "unknown"
    assert projection.reason_code == "chart_capacity_exceeded"
