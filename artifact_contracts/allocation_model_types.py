"""Serializable allocation fallback predictors with legacy ML class paths."""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray


class _ConstantProbabilityModel:
    """可序列化且明確標記 classifier 的單一 class fallback。"""

    classifier = True

    def __init__(self, probability_class: int) -> None:
        if probability_class not in {0, 1}:
            raise ValueError("probability class must be 0 or 1")
        self.probability_class = probability_class

    def predict_proba(self, matrix: NDArray[Any]) -> NDArray[np.float64]:
        count = len(matrix)
        result = np.zeros((count, 2), dtype=np.float64)
        result[:, self.probability_class] = 1.0
        return result


class _ConstantRegressionModel:
    """只供 schema-compatible neutral Meta；不代表已識別的配置器。"""

    classifier = False

    def __init__(self, value: int) -> None:
        self.value = int(value)

    def predict(self, matrix: NDArray[Any]) -> NDArray[np.float64]:
        return np.full(len(matrix), self.value, dtype=np.float64)


_LEGACY_CLASS_MODULE = "ml_module.allocation_v3_linear_release"

# Pickle/joblib resolve globals through these original qualified names. Keep
# both class and method metadata stable while this leaf owns their definitions.
_ConstantProbabilityModel.__module__ = _LEGACY_CLASS_MODULE
_ConstantProbabilityModel.__init__.__module__ = _LEGACY_CLASS_MODULE
_ConstantProbabilityModel.predict_proba.__module__ = _LEGACY_CLASS_MODULE
_ConstantRegressionModel.__module__ = _LEGACY_CLASS_MODULE
_ConstantRegressionModel.__init__.__module__ = _LEGACY_CLASS_MODULE
_ConstantRegressionModel.predict.__module__ = _LEGACY_CLASS_MODULE
