"""R020 replay scalar 的 legacy NumPy comparison-domain 投影。

本模組是 app numeric compatibility boundary。既有
`project_legacy_comparison_pair` 呼叫者必須傳入舊流程已算好的 metric scalar，
以及已完成舊 `float()`／成交量正規化的 Python float threshold；
`project_legacy_post_score_comparison_pair` 則只接受已表徵的原生 numeric
metric／effective threshold 組合。兩條路徑都只投影 operand，不重算 metric、不正規化
threshold，也不作大小比較。

NumPy 弱 scalar promotion 依目前 Windows runtime 的 NumPy 2 行為驗證；一般
runtime requirements 仍允許 NumPy 1.x，因此這個模組不宣稱跨 NumPy 主版本等價。
接線前必須另行決定 NumPy 1.x 支援政策與測試矩陣。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
import math
from typing import Any, Final, cast

import numpy as np
import pandas as pd

from decision_module.recommendation.evaluate import (
    ReplayPostScoreMetricLegacyKindV1,
    ReplayPostScoreRuleV1,
    ReplayPostScoreThresholdInputHintV1,
    ReplayPostScoreThresholdInputKindV1,
)
from decision_module.recommendation.replay_prefilter import (
    ReplayComparisonComponent,
    ReplayComparisonDomain,
    ReplayComparisonDomainKind,
    ReplayComparisonOperand,
    ReplayNumericOrigin,
    ReplayNumericOriginKind,
)


class ReplayThresholdUnit(str, Enum):
    """projector 接受的舊 threshold 單位。"""

    PRICE_CHANGE_PERCENT = "price_change_percent"
    VOLUME_EFFECTIVE_CHANGE_PERCENT = "volume_effective_change_percent"


class UnsupportedReplayNumericScalarError(TypeError):
    """metric scalar 不在已驗證的 legacy comparison domain。"""


def classify_legacy_post_score_metric_scalar(
    value: object,
    *,
    series_dtype: object,
) -> ReplayPostScoreMetricLegacyKindV1 | None:
    """只分類 legacy oracle 已凍結的 object-dtype scalar 組合。

    呼叫端必須傳入來源 Series 的 dtype，避免把相同缺值 scalar 的 nullable
    extension dtype 行為誤稱為 object-dtype 行為。
    """

    if series_dtype != object:
        return None
    if type(value) is Decimal:
        return ReplayPostScoreMetricLegacyKindV1.PYTHON_DECIMAL_OBJECT
    if value is pd.NA:
        return ReplayPostScoreMetricLegacyKindV1.PANDAS_OBJECT_NA
    return None


def project_legacy_post_score_threshold_input_hint(
    raw_value: object,
    *,
    filter_id: ReplayPostScoreRuleV1,
) -> ReplayPostScoreThresholdInputHintV1 | None:
    """保留 legacy 原始 Python 字串／None 型別與診斷顯示文字。"""

    if type(filter_id) is not ReplayPostScoreRuleV1:
        raise TypeError("filter_id 必須是 ReplayPostScoreRuleV1")
    if raw_value is None:
        return ReplayPostScoreThresholdInputHintV1(
            filter_id=filter_id,
            input_kind=ReplayPostScoreThresholdInputKindV1.PYTHON_NONE,
            display_text="None",
        )
    if type(raw_value) is not str:
        return None
    return ReplayPostScoreThresholdInputHintV1(
        filter_id=filter_id,
        input_kind=ReplayPostScoreThresholdInputKindV1.PYTHON_STRING,
        display_text=raw_value,
    )


@dataclass(frozen=True, slots=True)
class ReplayLegacyComparisonPair:
    """一對由 legacy promotion 投影出的、相同 effective domain operands。"""

    metric: ReplayComparisonOperand
    threshold: ReplayComparisonOperand
    unit: ReplayThresholdUnit

    def __post_init__(self) -> None:
        if type(self.metric) is not ReplayComparisonOperand:
            raise TypeError("metric 必須是 ReplayComparisonOperand")
        if type(self.threshold) is not ReplayComparisonOperand:
            raise TypeError("threshold 必須是 ReplayComparisonOperand")
        if type(self.unit) is not ReplayThresholdUnit:
            raise TypeError("unit 必須是 ReplayThresholdUnit")
        if self.metric.domain != self.threshold.domain:
            raise ValueError("metric 與 threshold 必須使用相同 effective domain")


def _component_from_python_float(value: float) -> ReplayComparisonComponent:
    if math.isnan(value):
        return ReplayComparisonComponent.unordered()
    if math.isinf(value):
        if value.hex().startswith("-"):
            return ReplayComparisonComponent.negative_infinity()
        return ReplayComparisonComponent.positive_infinity()
    numerator, denominator = value.as_integer_ratio()
    return ReplayComparisonComponent.finite(numerator, denominator)


def _component_from_numpy_float(value: Any) -> ReplayComparisonComponent:
    if bool(np.isnan(value)):
        return ReplayComparisonComponent.unordered()
    if bool(np.isposinf(value)):
        return ReplayComparisonComponent.positive_infinity()
    if bool(np.isneginf(value)):
        return ReplayComparisonComponent.negative_infinity()
    # NumPy floating scalar 的 as_integer_ratio 保留實際 dtype 的精確值；不可轉 Python
    # float，否則 float128/longdouble 可能在此邊界先失去有效位元。
    ratio = value.as_integer_ratio()
    return ReplayComparisonComponent.finite(int(ratio[0]), int(ratio[1]))


def _component_from_scalar(value: object) -> ReplayComparisonComponent:
    if type(value) is float:
        return _component_from_python_float(value)
    if isinstance(value, np.floating):
        return _component_from_numpy_float(value)
    if type(value) is int:
        return ReplayComparisonComponent.finite(value)
    raise UnsupportedReplayNumericScalarError(
        f"不支援的 replay comparison component：{type(value).__module__}."
        f"{type(value).__qualname__}"
    )


def _python_real_operand(
    value: int | float,
    *,
    origin_kind: ReplayNumericOriginKind,
) -> ReplayComparisonOperand:
    component = _component_from_scalar(value)
    return ReplayComparisonOperand(
        origin=ReplayNumericOrigin(origin_kind),
        domain=ReplayComparisonDomain.exact_rational(),
        real=component,
    )


def _python_complex_pair(
    metric_scalar: complex,
    effective_threshold: float,
    unit: ReplayThresholdUnit,
) -> ReplayLegacyComparisonPair:
    """保留 Python complex 不支援 ordering 的 evaluator error path。"""

    domain = ReplayComparisonDomain.python_complex()
    metric = ReplayComparisonOperand(
        origin=ReplayNumericOrigin(ReplayNumericOriginKind.PYTHON_COMPLEX),
        domain=domain,
        real=_component_from_python_float(metric_scalar.real),
        imaginary=_component_from_python_float(metric_scalar.imag),
    )
    threshold = ReplayComparisonOperand(
        origin=ReplayNumericOrigin(ReplayNumericOriginKind.PYTHON_FLOAT),
        domain=domain,
        real=_component_from_python_float(effective_threshold),
        imaginary=ReplayComparisonComponent.finite(0),
    )
    return ReplayLegacyComparisonPair(metric=metric, threshold=threshold, unit=unit)


def _numpy_origin(metric_scalar: np.generic[object]) -> ReplayNumericOrigin:
    metric_dtype = np.dtype(metric_scalar.dtype)
    kind_by_dtype = {
        "i": ReplayNumericOriginKind.NUMPY_INTEGER,
        "u": ReplayNumericOriginKind.NUMPY_INTEGER,
        "f": ReplayNumericOriginKind.NUMPY_FLOAT,
        "c": ReplayNumericOriginKind.NUMPY_COMPLEX,
    }
    origin_kind = kind_by_dtype.get(metric_dtype.kind)
    if origin_kind is None:
        raise UnsupportedReplayNumericScalarError(
            f"不支援的 NumPy replay metric dtype：{metric_dtype.name}"
        )
    return ReplayNumericOrigin(origin_kind, dtype_name=metric_dtype.name)


def _numpy_domain(dtype: Any) -> ReplayComparisonDomain:
    if dtype.kind == "f":
        finfo = np.finfo(dtype)
        return ReplayComparisonDomain.binary_real(
            dtype.name,
            precision_bits=int(finfo.nmant) + 1,
            min_exponent=int(finfo.minexp),
            max_exponent=int(finfo.maxexp),
        )
    if dtype.kind == "c":
        component_dtype = np.empty((), dtype=dtype).real.dtype
        finfo = np.finfo(component_dtype)
        return ReplayComparisonDomain.numpy_complex(
            dtype.name,
            precision_bits=int(finfo.nmant) + 1,
            min_exponent=int(finfo.minexp),
            max_exponent=int(finfo.maxexp),
        )
    raise UnsupportedReplayNumericScalarError(
        f"NumPy weak promotion 未產生浮點 comparison domain：{dtype.name}"
    )


def _numpy_operand(
    value: Any,
    *,
    origin: ReplayNumericOrigin,
    domain: ReplayComparisonDomain,
) -> ReplayComparisonOperand:
    if domain.kind is ReplayComparisonDomainKind.NUMPY_COMPLEX:
        if not isinstance(value, np.complexfloating):
            raise UnsupportedReplayNumericScalarError(
                "NumPy complex effective domain 必須使用 complex scalar"
            )
        return ReplayComparisonOperand(
            origin=origin,
            domain=domain,
            real=_component_from_numpy_float(value.real),
            imaginary=_component_from_numpy_float(value.imag),
        )
    if domain.kind is not ReplayComparisonDomainKind.BINARY_REAL:
        raise UnsupportedReplayNumericScalarError(
            "NumPy scalar 必須投影至 binary-real 或 NumPy-complex domain"
        )
    if not isinstance(value, np.floating):
        raise UnsupportedReplayNumericScalarError(
            "NumPy binary-real effective domain 必須使用 floating scalar"
        )
    return ReplayComparisonOperand(
        origin=origin,
        domain=domain,
        real=_component_from_numpy_float(value),
    )


def project_legacy_comparison_pair(
    metric_scalar: object,
    effective_threshold: float,
    *,
    unit: ReplayThresholdUnit,
) -> ReplayLegacyComparisonPair:
    """把舊比較的 metric 與已轉換門檻投影成同域 operand pair。

    `effective_threshold` 必須已在 legacy lazy stage 完成 `float(raw)`；成交量門檻
    還必須已由既有 Python normalization 轉為 effective change percent。此函式不做
    任何門檻算術，也不比較兩個 operand。NumPy scalar 使用目前 NumPy 2 runtime 的
    weak scalar promotion，並以 runtime dtype metadata 描述 Windows longdouble alias
    或其他平台的 extended precision。
    """

    if type(effective_threshold) is not float:
        raise TypeError("effective_threshold 必須是呼叫者已轉換的 Python float")
    if type(unit) is not ReplayThresholdUnit:
        raise TypeError("unit 必須是 ReplayThresholdUnit")

    if type(metric_scalar) is complex:
        return _python_complex_pair(metric_scalar, effective_threshold, unit)

    if type(metric_scalar) is int or type(metric_scalar) is float:
        origin_kind = (
            ReplayNumericOriginKind.PYTHON_INT
            if type(metric_scalar) is int
            else ReplayNumericOriginKind.PYTHON_FLOAT
        )
        metric = _python_real_operand(metric_scalar, origin_kind=origin_kind)
        threshold = _python_real_operand(
            effective_threshold,
            origin_kind=ReplayNumericOriginKind.PYTHON_FLOAT,
        )
        return ReplayLegacyComparisonPair(metric=metric, threshold=threshold, unit=unit)

    if not isinstance(metric_scalar, np.generic):
        raise UnsupportedReplayNumericScalarError(
            f"不支援的 replay metric scalar：{type(metric_scalar).__module__}."
            f"{type(metric_scalar).__qualname__}"
        )

    origin = _numpy_origin(metric_scalar)
    # 必須傳 scalar 值而非 dtype；NumPy 2 會把 Python float 當 weak scalar，
    # 這正是舊 `numpy_scalar < python_float` 所使用的 promotion 規則。
    effective_dtype = np.dtype(np.result_type(metric_scalar, effective_threshold))
    domain = _numpy_domain(effective_dtype)

    # 這兩次 cast 位於呼叫者已完成 threshold parsing/normalization 之後，保留 NumPy
    # overflow warning、np.seterr 與低精度 weak-cast 行為；不可抑制或改包例外。
    effective_metric: Any = np.asarray(metric_scalar, dtype=effective_dtype)[()]
    effective_threshold_scalar: Any = np.asarray(
        effective_threshold, dtype=effective_dtype
    )[()]

    metric_operand = _numpy_operand(effective_metric, origin=origin, domain=domain)
    threshold_operand = _numpy_operand(
        effective_threshold_scalar,
        origin=ReplayNumericOrigin(ReplayNumericOriginKind.PYTHON_FLOAT),
        domain=domain,
    )
    return ReplayLegacyComparisonPair(
        metric=metric_operand,
        threshold=threshold_operand,
        unit=unit,
    )


def _exact_real_component(value: object) -> ReplayComparisonComponent:
    if type(value) is bool:
        return ReplayComparisonComponent.finite(int(value))
    if type(value) is int:
        return ReplayComparisonComponent.finite(value)
    if type(value) is float:
        return _component_from_python_float(value)
    if type(value) is Decimal:
        if not value.is_finite():
            raise UnsupportedReplayNumericScalarError(
                "Decimal replay scalar 必須是有限值"
            )
        numerator, denominator = value.as_integer_ratio()
        return ReplayComparisonComponent.finite(numerator, denominator)
    if isinstance(value, np.integer):
        return ReplayComparisonComponent.finite(int(value))
    if isinstance(value, np.floating):
        return _component_from_numpy_float(value)
    raise UnsupportedReplayNumericScalarError(
        f"不支援的 replay real scalar：{type(value).__module__}."
        f"{type(value).__qualname__}"
    )


def _numeric_origin(value: object) -> ReplayNumericOrigin:
    if type(value) is bool:
        return ReplayNumericOrigin(ReplayNumericOriginKind.PYTHON_INT)
    if type(value) is int:
        return ReplayNumericOrigin(ReplayNumericOriginKind.PYTHON_INT)
    if type(value) is float:
        return ReplayNumericOrigin(ReplayNumericOriginKind.PYTHON_FLOAT)
    if type(value) is Decimal:
        return ReplayNumericOrigin(ReplayNumericOriginKind.LEGACY_DECIMAL)
    if isinstance(value, np.generic):
        return _numpy_origin(value)
    raise UnsupportedReplayNumericScalarError(
        f"不支援的 replay numeric origin：{type(value).__module__}."
        f"{type(value).__qualname__}"
    )


def _exact_real_operand(value: object) -> ReplayComparisonOperand:
    return ReplayComparisonOperand(
        origin=_numeric_origin(value),
        domain=ReplayComparisonDomain.exact_rational(),
        real=_exact_real_component(value),
    )


def project_legacy_post_score_comparison_pair(
    metric_scalar: object,
    effective_threshold: object,
    *,
    unit: ReplayThresholdUnit,
) -> ReplayLegacyComparisonPair:
    """投影 scored-row 原生 numeric operands；不轉 float、不正規化、不比較。

    成交量 threshold 必須已由 legacy alias normalization 產生；其他 threshold
    保留原 Python／NumPy scalar。NumPy metric 依同一 native promotion 域投影，
    object scalar 則保留 exact-rational/Python-complex provenance。尚未表徵的
    scalar 組合 fail closed，由呼叫端保留 v1-only 或原生例外路徑。
    """

    if type(unit) is not ReplayThresholdUnit:
        raise TypeError("unit 必須是 ReplayThresholdUnit")

    if type(metric_scalar) is complex:
        if type(effective_threshold) not in (int, float):
            raise UnsupportedReplayNumericScalarError(
                "Python complex post-score threshold 只接受 Python int/float"
            )
        domain = ReplayComparisonDomain.python_complex()
        metric = ReplayComparisonOperand(
            origin=ReplayNumericOrigin(ReplayNumericOriginKind.PYTHON_COMPLEX),
            domain=domain,
            real=_component_from_python_float(metric_scalar.real),
            imaginary=_component_from_python_float(metric_scalar.imag),
        )
        threshold = ReplayComparisonOperand(
            origin=_numeric_origin(effective_threshold),
            domain=domain,
            real=_exact_real_component(effective_threshold),
            imaginary=ReplayComparisonComponent.finite(0),
        )
        return ReplayLegacyComparisonPair(metric=metric, threshold=threshold, unit=unit)

    numeric_types = (int, float, Decimal)
    if type(metric_scalar) in numeric_types:
        if type(effective_threshold) not in numeric_types:
            raise UnsupportedReplayNumericScalarError(
                "Python/object metric 與非 Python numeric threshold 組合尚未表徵"
            )
        return ReplayLegacyComparisonPair(
            metric=_exact_real_operand(metric_scalar),
            threshold=_exact_real_operand(effective_threshold),
            unit=unit,
        )

    if isinstance(metric_scalar, np.generic):
        if not isinstance(effective_threshold, (*numeric_types, np.integer, np.floating, np.complexfloating)):
            raise UnsupportedReplayNumericScalarError(
                "NumPy metric 與非 numeric threshold 組合尚未表徵"
            )
        origin = _numpy_origin(metric_scalar)
        effective_dtype = np.dtype(
            np.result_type(metric_scalar, cast(Any, effective_threshold))
        )
        if effective_dtype.kind not in {"i", "u", "f", "c"}:
            raise UnsupportedReplayNumericScalarError(
                f"NumPy post-score effective dtype 尚未表徵：{effective_dtype.name}"
            )
        # 保留 NumPy cast 的原生 warning/np.seterr 時點；不能抑制或重包例外。
        effective_metric: Any = np.asarray(metric_scalar, dtype=effective_dtype)[()]
        effective_threshold_scalar: Any = np.asarray(
            effective_threshold, dtype=effective_dtype
        )[()]
        if effective_dtype.kind in {"i", "u"}:
            metric = ReplayComparisonOperand(
                origin=origin,
                domain=ReplayComparisonDomain.exact_rational(),
                real=ReplayComparisonComponent.finite(int(effective_metric)),
            )
            threshold = ReplayComparisonOperand(
                origin=_numeric_origin(effective_threshold),
                domain=ReplayComparisonDomain.exact_rational(),
                real=ReplayComparisonComponent.finite(int(effective_threshold_scalar)),
            )
        else:
            domain = _numpy_domain(effective_dtype)
            metric = _numpy_operand(effective_metric, origin=origin, domain=domain)
            threshold = _numpy_operand(
                effective_threshold_scalar,
                origin=_numeric_origin(effective_threshold),
                domain=domain,
            )
        return ReplayLegacyComparisonPair(metric=metric, threshold=threshold, unit=unit)

    raise UnsupportedReplayNumericScalarError(
        f"不支援的 post-score metric scalar：{type(metric_scalar).__module__}."
        f"{type(metric_scalar).__qualname__}"
    )


__all__: Final[tuple[str, ...]] = (
    "classify_legacy_post_score_metric_scalar",
    "project_legacy_post_score_threshold_input_hint",
    "ReplayLegacyComparisonPair",
    "ReplayThresholdUnit",
    "UnsupportedReplayNumericScalarError",
    "project_legacy_comparison_pair",
    "project_legacy_post_score_comparison_pair",
)
