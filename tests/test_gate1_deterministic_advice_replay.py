from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app_module.advice_composer import AdviceComposer
from app_module.advice_dtos import AdviceMode, AdvicePolicyConfig
from app_module.advice_policy import AdvicePolicy
from app_module.dtos import RecommendationResultDTO
from app_module.recommendation_service import RecommendationService
from decision_module.strategy_configurator import StrategyConfigurator
from recommendation_test_support import build_recommendation_test_preparer


class _FrozenMarketFrameProvider:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame.copy(deep=True)

    def __call__(self) -> pd.DataFrame:
        return self._frame.copy(deep=True)


def _frozen_market_frame() -> pd.DataFrame:
    decision_date = date(2026, 10, 28)
    first_date = decision_date - timedelta(days=99)
    rows = []
    for offset in range(100):
        available_date = first_date + timedelta(days=offset)
        close = Decimal("100.00") + Decimal(offset) * Decimal("0.25")
        rows.append(
            {
                "日期": available_date,
                "available_date": available_date,
                "證券代號": "2330",
                "證券名稱": "台積電",
                "開盤價": close - Decimal("0.50"),
                "最高價": close + Decimal("1.00"),
                "最低價": close - Decimal("1.00"),
                "收盤價": close,
                "成交股數": 1_000 + offset * 10,
            }
        )
    return pd.DataFrame(rows)


def _frozen_strategy_config() -> dict[str, object]:
    return {
        "profile_id": "gate1-frozen-replay-v1",
        "profile_version": "1",
        "strategy_version": "test-strategy-v1",
        "strategy_status": "candidate",
        "parameters_locked": False,
        "disclosure_complete": False,
        "execution_feasible": None,
        "strategy_advice_contract_verified": False,
        "weights": {"pattern": 3000, "technical": 5000, "volume": 2000},
        "technical": {
            "momentum": {
                "enabled": True,
                "rsi": {"enabled": True, "timeperiod": 14},
                "macd": {
                    "enabled": True,
                    "fastperiod": 12,
                    "slowperiod": 26,
                    "signalperiod": 9,
                },
                "kd": {"enabled": False},
            }
        },
        "patterns": {"selected": []},
        "filters": {},
        "recommendation_ranking": {"threshold_mode": "fixed"},
        "config_schema_version": 1,
    }


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_payload(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _replay_once(
    *,
    frame: pd.DataFrame,
    strategy_config: dict[str, object],
    policy_config: AdvicePolicyConfig,
    output_root: Path,
) -> tuple[str, str]:
    provider = _FrozenMarketFrameProvider(frame)
    config = SimpleNamespace(
        db_file=output_root.parent / "missing-fundamentals.db",
        use_sqlite=False,
        pit_market_scope="twse_listed",
        output_root=output_root,
    )
    service = RecommendationService(
        config,
        industry_mapper=MagicMock(),
        market_data_provider=provider,
        regime_detector=MagicMock(),
        calibration_consumer=None,
        input_preparer=build_recommendation_test_preparer(
            config,
            market_data_provider=provider,
        ),
    )
    assert type(service.strategy_configurator) is StrategyConfigurator
    recommendations = service.run_recommendation(
        deepcopy(strategy_config),
        max_stocks=1,
        top_n=5,
        as_of_date="2026-10-28",
        universe=["2330"],
        result_id="gate1-frozen-replay-v1",
    )
    assert recommendations

    saved_projection = RecommendationResultDTO(
        result_id="gate1-frozen-replay-v1",
        result_name="Gate 1 frozen replay fixture",
        config=deepcopy(strategy_config),
        recommendations=recommendations,
        regime="unknown",
    )
    advice = AdviceComposer(AdvicePolicy(policy_config)).compose(
        recommendations=saved_projection,
        portfolio_result=None,
        evidence_quality="OBSERVED",
        decision_date="2026-10-28",
        data_as_of_date="2026-10-28",
        mode=AdviceMode.GUIDED,
    )
    recommendation_payload = _canonical_json(
        [item.to_dict() for item in recommendations]
    )
    advice_payload = _canonical_json(advice.to_dict())
    return recommendation_payload, advice_payload


def test_frozen_market_strategy_and_advice_policy_replay_identically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """固定行情、真策略計算與 Advice policy 必須重播成相同 payload。"""

    data_root = tmp_path / "data"
    output_root = tmp_path / "output"
    data_root.mkdir()
    output_root.mkdir()
    monkeypatch.setenv("DATA_ROOT", str(data_root))
    monkeypatch.setenv("OUTPUT_ROOT", str(output_root))

    frame = _frozen_market_frame()
    strategy_config = _frozen_strategy_config()
    policy_config = AdvicePolicyConfig(mode=AdviceMode.GUIDED)
    frozen_inputs = {
        "decision_date": "2026-10-28",
        "market_rows": frame.to_dict(orient="records"),
        "strategy": strategy_config,
        "advice_policy": policy_config.to_dict(),
    }
    assert _sha256_json(frame.to_dict(orient="records")) == (
        "b42ccfd612921014a1072c2a06a5055691215149f84904a1b4b3d6c38501d7d8"
    )
    assert _sha256_json(strategy_config) == (
        "20f40e6c285df72a3612a154d3671fcb487540ddc93e2811f0d97e71efd679a1"
    )
    assert _sha256_json(policy_config.to_dict()) == (
        "c5b4dbfb1b581bbc16fcb33ff15e9a9a60e5bff0979c93174ce02ef2889f1b56"
    )
    assert _sha256_json(frozen_inputs) == (
        "749d766d5e3c97474afde689625933d9f1a51be5f1965ac1082c31986f027edc"
    )

    first = _replay_once(
        frame=frame,
        strategy_config=strategy_config,
        policy_config=policy_config,
        output_root=output_root,
    )
    second = _replay_once(
        frame=frame,
        strategy_config=strategy_config,
        policy_config=policy_config,
        output_root=output_root,
    )

    assert first == second
    assert _sha256_payload(first[0]) == (
        "972304b829ee30d2ecf6d35528032bf9eaf8393571882c87247902e8bebd51b4"
    )
    assert _sha256_payload(first[1]) == (
        "e474fb2de69dddf31f0761ebd82a4ab5f03189e81b3038c57ae1884119e6661b"
    )
