"""三角形趨勢線的退化數值輸入必須安全略過。"""

import numpy as np
import pandas as pd
import pytest

from analysis_module.pattern_analysis import pattern_analyzer


def _prepare_candidate(
    monkeypatch,
    *,
    upper_line=(np.float64(0), np.float64(110)),
    lower_line=(np.float64(2), np.float64(90)),
    r_squared=(np.float64(1), np.float64(1)),
    prices=None,
):
    analyzer = pattern_analyzer.PatternAnalyzer()
    events = [
        {"type": "peak", "idx": 0},
        {"type": "trough", "idx": 2},
        {"type": "peak", "idx": 4},
        {"type": "trough", "idx": 6},
        {"type": "peak", "idx": 8},
    ]
    monkeypatch.setattr(
        analyzer,
        "find_peaks_and_troughs",
        lambda *args, **kwargs: events,
    )

    def fit(x_values, _y_values, _degree):
        indices = tuple(x_values)
        if indices == (0, 4, 8):
            return upper_line
        if indices == (2, 6):
            return lower_line
        raise AssertionError(f"unexpected fit indices: {indices}")

    monkeypatch.setattr(pattern_analyzer, "_safe_polyfit", fit)
    quality = iter(r_squared)
    monkeypatch.setattr(
        pattern_analyzer,
        "_safe_r_squared",
        lambda *_args, **_kwargs: next(quality),
    )
    prices = prices if prices is not None else [110, 105, 94, 104, 110, 100, 102, 105, 110]
    return analyzer, pd.DataFrame({"Close": prices})


@pytest.mark.parametrize("lower_intercept", [110.0, 90.0])
def test_parallel_triangle_lines_are_skipped_without_divide_warnings(
    monkeypatch, lower_intercept
):
    analyzer, frame = _prepare_candidate(
        monkeypatch,
        upper_line=(np.float64(0), np.float64(110)),
        lower_line=(np.float64(0), np.float64(lower_intercept)),
    )

    with np.errstate(divide="raise", invalid="raise", over="raise"):
        assert analyzer.identify_triangle(frame, price_col="Close") == []


def test_nonfinite_fit_quality_is_not_accepted_as_a_triangle(monkeypatch):
    analyzer, frame = _prepare_candidate(
        monkeypatch,
        r_squared=(np.float64(np.nan), np.float64(1)),
    )

    with np.errstate(divide="raise", invalid="raise", over="raise"):
        assert analyzer.identify_triangle(frame, price_col="Close") == []


def test_zero_price_range_is_skipped_without_ratio_division(monkeypatch):
    analyzer, frame = _prepare_candidate(monkeypatch, prices=[100] * 9)

    with np.errstate(divide="raise", invalid="raise", over="raise"):
        assert analyzer.identify_triangle(frame, price_col="Close") == []


def test_finite_converging_triangle_keeps_existing_result(monkeypatch):
    analyzer, frame = _prepare_candidate(monkeypatch)

    with np.errstate(divide="raise", invalid="raise", over="raise"):
        result = analyzer.identify_triangle(frame, price_col="Close")

    assert len(result) == 1
    triangle = result[0]
    assert triangle["type"] == "上升三角形"
    assert triangle["intersection_x"] == pytest.approx(10)
    assert triangle["start_height"] == pytest.approx(20)
    assert triangle["end_height"] == pytest.approx(4)
    assert triangle["height_ratio"] == pytest.approx(1.25)
    assert triangle["convergence_ratio"] == pytest.approx(0.2)
