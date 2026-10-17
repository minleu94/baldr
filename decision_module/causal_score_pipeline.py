"""因果缺值版只在連續有報價區段分析；原無價零量列保留未知、不補價。"""
from typing import Any

import pandas as pd


def calculate_causal_score_frame(frame: pd.DataFrame, config: dict[str, Any],
                                 configurator: Any, scoring_engine: Any) -> pd.DataFrame:
    result = frame.copy(deep=True)
    known = result["_causal_quote_available"]
    if any(type(value) is not bool for value in known.tolist()):
        raise ValueError("因果計分缺可核報價狀態")
    for column in ("TotalScore", "FinalScore", "IndicatorScore", "PatternScore", "VolumeScore"):
        result[column] = pd.Series(None, index=result.index, dtype=object)
    result["RegimeMatch"] = False
    boundaries = known.ne(known.shift()).cumsum()
    for _, segment in frame.loc[known].groupby(boundaries.loc[known], sort=False):
        prepared = segment.drop(columns=["_atr_cum_mean"], errors="ignore").copy(deep=True)
        prepared = configurator.configure_technical_indicators(
            prepared, config.get("technical", {}), full_config={"input_preparation_policy": "causal-score-input.v1"})
        scored = scoring_engine.calculate_total_score(prepared, config, regime=config.get("regime"))
        for column in scored:
            if column not in result:
                result[column] = pd.Series(None, index=result.index, dtype=object)
            result.loc[scored.index, column] = scored[column]
    return result
