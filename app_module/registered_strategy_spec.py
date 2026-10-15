"""將本次登記的策略身分綁到執行請求，不代填或升級歷史版本。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from decision_module.strategies.contracts import StrategyMeta, StrategySpec
from decision_module.strategies.registry import StrategyRegistry


def registered_strategy_spec(
    strategy_id: str, *, config: dict[str, Any],
    name: str | None = None, description: str | None = None,
) -> StrategySpec:
    """只解析公開 metadata；不實例化 executor、不讀資料或更改金融參數。"""
    raw = StrategyRegistry.get_strategy_meta(strategy_id)
    meta = raw.to_dict() if isinstance(raw, StrategyMeta) else raw
    if not isinstance(meta, dict) or meta.get("strategy_id") != strategy_id:
        raise ValueError("策略登記身分不可用；請重新選取已登記的策略")
    versions = [meta[key] for key in ("strategy_version", "version") if key in meta]
    if not versions or any(not isinstance(value, str) or not value or value != value.strip() for value in versions):
        raise ValueError("策略登記缺少明確版本；不能預設為 1.0")
    if len(set(versions)) != 1:
        raise ValueError("策略登記的版本宣告互相衝突")
    return StrategySpec(
        strategy_id=strategy_id, strategy_version=versions[0],
        name=meta.get("name", strategy_id) if name is None else name,
        description=meta.get("description", "") if description is None else description,
        regime=[], risk_level="medium", target_type="stock", config=deepcopy(config),
    )
