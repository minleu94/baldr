from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd

from app_module.regime_service import RegimeService
from decision_module.market_regime_detector import MarketRegimeDetector


def test_detect_regime_uses_injected_market_frame_provider(tmp_path) -> None:
    provider = MagicMock(
        return_value=pd.DataFrame(
            {"日期": ["2026-07-10"], "收盤價": [100], "最高價": [101], "最低價": [99]}
        )
    )
    service = RegimeService(
        SimpleNamespace(),
        regime_detector=MarketRegimeDetector(),
        use_persistent_history=False,
        market_frame_provider=provider,
    )

    result = service.detect_regime()

    provider.assert_called_once_with()
    assert result.regime == "Trend"
    assert result.confidence == 0.5
    assert result.details == {"error": "數據不足"}


def test_detect_regime_normalizes_raw_sqlite_market_index_schema(tmp_path) -> None:
    dates = pd.date_range("2026-01-01", periods=80, freq="D").strftime("%Y%m%d")
    provider = MagicMock(
        return_value=pd.DataFrame(
            {
                "日期": dates,
                "收盤指數": range(100, 180),
            }
        )
    )
    service = RegimeService(
        SimpleNamespace(),
        regime_detector=MarketRegimeDetector(),
        use_persistent_history=False,
        market_frame_provider=provider,
    )

    result = service.detect_regime()

    assert result.details.get("error") != "找不到收盤價欄位"
    assert result.details.get("error") != "數據不足"


def test_detect_regime_keeps_decision_date_separate_from_last_observed_row() -> None:
    dates = pd.bdate_range(end="2026-10-02", periods=80)
    provider = MagicMock(
        return_value=pd.DataFrame(
            {
                "date": dates.strftime("%Y-%m-%d"),
                "close": [100.0 + index for index in range(len(dates))],
            }
        )
    )
    service = RegimeService(
        SimpleNamespace(),
        regime_detector=MarketRegimeDetector(),
        use_persistent_history=False,
        market_frame_provider=provider,
    )

    result = service.detect_regime(date="2026-10-05")

    assert result.details["date"] == "2026-10-05"
    assert result.details["source_data_date"] == "2026-10-02"


def test_detect_regime_source_date_excludes_future_rows() -> None:
    dates = pd.bdate_range(end="2026-10-05", periods=80)
    closes = [100.0 + index for index in range(len(dates))]
    provider = MagicMock(
        return_value=pd.DataFrame(
            {"date": dates.strftime("%Y-%m-%d"), "close": closes}
        )
    )
    service = RegimeService(
        SimpleNamespace(),
        regime_detector=MarketRegimeDetector(),
        use_persistent_history=False,
        market_frame_provider=provider,
    )

    result = service.detect_regime(date="2026-10-04")

    assert result.details["date"] == "2026-10-04"
    assert result.details["source_data_date"] == "2026-10-02"


def test_detect_regime_source_date_uses_last_finite_close_when_tail_is_invalid() -> None:
    dates = pd.bdate_range(end="2026-10-02", periods=80)
    closes = [100.0 + index for index in range(len(dates))]
    closes[-1] = float("nan")
    provider = MagicMock(
        return_value=pd.DataFrame(
            {"date": dates.strftime("%Y-%m-%d"), "close": closes}
        )
    )
    service = RegimeService(
        SimpleNamespace(),
        regime_detector=MarketRegimeDetector(),
        use_persistent_history=False,
        market_frame_provider=provider,
    )

    result = service.detect_regime(date="2026-10-05")

    assert result.details["date"] == "2026-10-05"
    assert result.details["source_data_date"] == dates[-2].strftime("%Y-%m-%d")


def test_detect_regime_does_not_invent_source_date_without_finite_closes() -> None:
    dates = pd.bdate_range(end="2026-10-02", periods=80)
    provider = MagicMock(
        return_value=pd.DataFrame(
            {
                "date": dates.strftime("%Y-%m-%d"),
                "close": [float("nan")] * len(dates),
            }
        )
    )
    service = RegimeService(
        SimpleNamespace(),
        regime_detector=MarketRegimeDetector(),
        use_persistent_history=False,
        market_frame_provider=provider,
    )

    result = service.detect_regime(date="2026-10-05")

    assert "source_data_date" not in result.details
