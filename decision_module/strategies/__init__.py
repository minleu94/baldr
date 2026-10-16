"""策略契約、唯一註冊表與內建策略執行器。"""

from decision_module.strategies.registry import StrategyRegistry
from decision_module.strategies.baseline_score_executor import BaselineScoreExecutor
from decision_module.strategies.momentum_aggressive_executor import MomentumAggressiveExecutor
from decision_module.strategies.stable_conservative_executor import StableConservativeExecutor
from decision_module.strategies.baldr_bollinger_executor import BaldrBollingerExecutor
from decision_module.strategies.baldr_w_bottom_executor import BaldrWBottomExecutor

# 保留既有註冊順序與 duplicate 拒絕語意；此套件是唯一註冊入口。
StrategyRegistry.register('baseline_score_threshold', BaselineScoreExecutor)
StrategyRegistry.register('momentum_aggressive_v1', MomentumAggressiveExecutor)
StrategyRegistry.register('stable_conservative_v1', StableConservativeExecutor)
StrategyRegistry.register('baldr_bollinger_basic_v1', BaldrBollingerExecutor)
StrategyRegistry.register('baldr_w_bottom_basic_v1', BaldrWBottomExecutor)

__all__ = [
    'BaselineScoreExecutor',
    'MomentumAggressiveExecutor',
    'StableConservativeExecutor',
    'BaldrBollingerExecutor',
    'BaldrWBottomExecutor',
]
