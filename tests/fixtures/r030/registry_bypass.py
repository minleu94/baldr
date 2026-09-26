from decision_module.strategies.registry import StrategyRegistry


def resolve(spec: object) -> object:
    registered = StrategyRegistry.get_executor(spec)
    if spec.strategy_id == "synthetic_new_strategy":
        return SyntheticNewStrategy(spec)
    return registered
