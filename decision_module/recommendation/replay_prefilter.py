"""R020 replay fast-prefilter 的純 typed contracts 與共用 gate。

此模組提供 count-only minimum-history preflight 與單一候選 fast-filter
disposition，不評分、不排序、不建立批次，也不讀取 DataFrame 或任何來源。
app 必須明示傳入已依 cutoff 裁切的歷史列數／觀測；完整 replay 最終仍由
RecommendationEvaluator 負責。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from math import gcd

from decision_module.recommendation.evaluation_constants import (
    MINIMUM_RECOMMENDATION_HISTORY_ROWS,
)


REPLAY_FAST_FILTER_POLICY_VERSION = "replay-fast-filter.v1"
REPLAY_VOLUME_THRESHOLD_VERSION = "replay-volume-threshold.v1"
_VOLUME_RATIO_NORMALIZATION_LOW = Decimal("-50")
_VOLUME_RATIO_NORMALIZATION_HIGH = Decimal("10")
_ONE = Decimal("1")
_HUNDRED = Decimal("100")


class ReplayThresholdStatus(str, Enum):
    """門檻設定的狀態；解析失敗必須明示 unsupported。"""

    DISABLED = "disabled"
    ENABLED = "enabled"
    PENDING = "pending"
    UNSUPPORTED = "unsupported"


class ReplayMetricStatus(str, Enum):
    """來源量測狀態，不把缺值猜成通過或拒絕。"""

    NOT_REQUESTED = "not_requested"
    AWAITING_THRESHOLD_PROJECTION = "awaiting_threshold_projection"
    AVAILABLE = "available"
    MISSING_COLUMN = "missing_column"
    INSUFFICIENT_WINDOW = "insufficient_window"
    ZERO_DENOMINATOR = "zero_denominator"
    UNSUPPORTED = "unsupported"


class ReplayComparisonKind(str, Enum):
    """可表示舊 float 比較結果、但不把 float 帶進決策核心的標記。"""

    FINITE = "finite"
    POSITIVE_INFINITY = "positive_infinity"
    NEGATIVE_INFINITY = "negative_infinity"
    UNORDERED = "unordered"


class ReplayNumericOriginKind(str, Enum):
    LEGACY_DECIMAL = "legacy_decimal"
    PYTHON_INT = "python_int"
    PYTHON_FLOAT = "python_float"
    NUMPY_INTEGER = "numpy_integer"
    NUMPY_FLOAT = "numpy_float"
    PYTHON_COMPLEX = "python_complex"
    NUMPY_COMPLEX = "numpy_complex"


@dataclass(frozen=True, slots=True)
class ReplayNumericOrigin:
    """adapter 看到的原始 scalar 家族／dtype；純核心不匯入 NumPy。"""

    kind: ReplayNumericOriginKind
    dtype_name: str | None = None

    def __post_init__(self) -> None:
        if type(self.kind) is not ReplayNumericOriginKind:
            raise TypeError("origin kind 必須是 ReplayNumericOriginKind")
        numpy_origin = self.kind in {
            ReplayNumericOriginKind.NUMPY_INTEGER,
            ReplayNumericOriginKind.NUMPY_FLOAT,
            ReplayNumericOriginKind.NUMPY_COMPLEX,
        }
        if numpy_origin:
            if type(self.dtype_name) is not str or not self.dtype_name.strip():
                raise ValueError("NumPy origin 必須明示 dtype_name")
        elif self.dtype_name is not None:
            raise ValueError("非 NumPy origin 不可帶 dtype_name")


class ReplayComparisonDomainKind(str, Enum):
    EXACT_RATIONAL = "exact_rational"
    BINARY_REAL = "binary_real"
    NUMPY_COMPLEX = "numpy_complex"
    PANDAS_COMPLEX_SERIES = "pandas_complex_series"
    PYTHON_COMPLEX = "python_complex"


@dataclass(frozen=True, slots=True)
class ReplayComparisonDomain:
    """adapter 已套用 legacy coercion 後的有效比較域描述。"""

    kind: ReplayComparisonDomainKind
    format_name: str | None = None
    precision_bits: int | None = None
    min_exponent: int | None = None
    max_exponent: int | None = None

    def __post_init__(self) -> None:
        if type(self.kind) is not ReplayComparisonDomainKind:
            raise TypeError("domain kind 必須是 ReplayComparisonDomainKind")
        has_binary_format = self.kind in {
            ReplayComparisonDomainKind.BINARY_REAL,
            ReplayComparisonDomainKind.NUMPY_COMPLEX,
            ReplayComparisonDomainKind.PANDAS_COMPLEX_SERIES,
        }
        metadata = (
            self.format_name,
            self.precision_bits,
            self.min_exponent,
            self.max_exponent,
        )
        if has_binary_format:
            if type(self.format_name) is not str or not self.format_name.strip():
                raise ValueError("binary/complex domain 必須明示 format_name")
            if type(self.precision_bits) is not int or self.precision_bits < 2:
                raise ValueError("precision_bits 必須至少為 2")
            if type(self.min_exponent) is not int or type(self.max_exponent) is not int:
                raise TypeError("binary domain 必須明示 exponent bounds")
            if self.max_exponent <= self.min_exponent:
                raise ValueError("max_exponent 必須大於 min_exponent")
        elif any(value is not None for value in metadata):
            raise ValueError("exact/Python complex domain 不可帶 binary format metadata")

    @classmethod
    def exact_rational(cls) -> ReplayComparisonDomain:
        return cls(ReplayComparisonDomainKind.EXACT_RATIONAL)

    @classmethod
    def binary_real(
        cls,
        format_name: str,
        *,
        precision_bits: int,
        min_exponent: int,
        max_exponent: int,
    ) -> ReplayComparisonDomain:
        return cls(
            ReplayComparisonDomainKind.BINARY_REAL,
            format_name,
            precision_bits,
            min_exponent,
            max_exponent,
        )

    @classmethod
    def numpy_complex(
        cls,
        format_name: str,
        *,
        precision_bits: int,
        min_exponent: int,
        max_exponent: int,
    ) -> ReplayComparisonDomain:
        return cls(
            ReplayComparisonDomainKind.NUMPY_COMPLEX,
            format_name,
            precision_bits,
            min_exponent,
            max_exponent,
        )

    @classmethod
    def pandas_complex_series(
        cls,
        format_name: str,
        *,
        precision_bits: int,
        min_exponent: int,
        max_exponent: int,
    ) -> ReplayComparisonDomain:
        """Pandas Series relational ops 的 complex 比較面與 NumPy scalar 分開標記。"""

        return cls(
            ReplayComparisonDomainKind.PANDAS_COMPLEX_SERIES,
            format_name,
            precision_bits,
            min_exponent,
            max_exponent,
        )

    @classmethod
    def python_complex(cls) -> ReplayComparisonDomain:
        return cls(ReplayComparisonDomainKind.PYTHON_COMPLEX)


@dataclass(frozen=True, slots=True)
class ReplayComparisonComponent:
    """一個有限精確有理數或 NaN／±infinity component。"""

    kind: ReplayComparisonKind
    numerator: int | None = None
    denominator: int | None = None

    def __post_init__(self) -> None:
        if type(self.kind) is not ReplayComparisonKind:
            raise TypeError("component kind 必須是 ReplayComparisonKind")
        if self.kind is ReplayComparisonKind.FINITE:
            if type(self.numerator) is not int or type(self.denominator) is not int:
                raise TypeError("finite component 必須使用整數 numerator/denominator")
            if self.denominator == 0:
                raise ValueError("component denominator 不可為零")
            numerator = self.numerator
            denominator = self.denominator
            if denominator < 0:
                numerator = -numerator
                denominator = -denominator
            divisor = gcd(abs(numerator), denominator)
            numerator //= divisor
            denominator //= divisor
            object.__setattr__(self, "numerator", numerator)
            object.__setattr__(self, "denominator", denominator)
        elif self.numerator is not None or self.denominator is not None:
            raise ValueError("non-finite component 不可帶 rational value")

    @classmethod
    def finite(cls, numerator: int, denominator: int = 1) -> ReplayComparisonComponent:
        return cls(ReplayComparisonKind.FINITE, numerator, denominator)

    @classmethod
    def positive_infinity(cls) -> ReplayComparisonComponent:
        return cls(ReplayComparisonKind.POSITIVE_INFINITY)

    @classmethod
    def negative_infinity(cls) -> ReplayComparisonComponent:
        return cls(ReplayComparisonKind.NEGATIVE_INFINITY)

    @classmethod
    def unordered(cls) -> ReplayComparisonComponent:
        return cls(ReplayComparisonKind.UNORDERED)


@dataclass(frozen=True, slots=True)
class ReplayComparisonOperand:
    """帶來源與 effective domain 的精確 real/complex comparison operand。"""

    origin: ReplayNumericOrigin
    domain: ReplayComparisonDomain
    real: ReplayComparisonComponent
    imaginary: ReplayComparisonComponent | None = None

    def __post_init__(self) -> None:
        if type(self.origin) is not ReplayNumericOrigin:
            raise TypeError("origin 必須是 ReplayNumericOrigin")
        if type(self.domain) is not ReplayComparisonDomain:
            raise TypeError("domain 必須是 ReplayComparisonDomain")
        if type(self.real) is not ReplayComparisonComponent:
            raise TypeError("real 必須是 ReplayComparisonComponent")
        complex_domain = self.domain.kind in {
            ReplayComparisonDomainKind.NUMPY_COMPLEX,
            ReplayComparisonDomainKind.PANDAS_COMPLEX_SERIES,
            ReplayComparisonDomainKind.PYTHON_COMPLEX,
        }
        if complex_domain:
            if type(self.imaginary) is not ReplayComparisonComponent:
                raise TypeError("complex domain 必須明示 imaginary component")
        elif self.imaginary is not None:
            raise ValueError("real domain 不可帶 imaginary component")

        origin_is_complex = self.origin.kind in {
            ReplayNumericOriginKind.PYTHON_COMPLEX,
            ReplayNumericOriginKind.NUMPY_COMPLEX,
        }
        if origin_is_complex and not complex_domain:
            raise ValueError("complex origin 必須保留 complex comparison domain")


@dataclass(frozen=True, slots=True)
class ReplayComparisonValue:
    """有限 Decimal 或舊比較器的特殊數值狀態。"""

    kind: ReplayComparisonKind
    value: Decimal | None = None

    def __post_init__(self) -> None:
        if type(self.kind) is not ReplayComparisonKind:
            raise TypeError("comparison kind 必須是 ReplayComparisonKind")
        if self.kind is ReplayComparisonKind.FINITE:
            if type(self.value) is not Decimal or not self.value.is_finite():
                raise ValueError("finite comparison value 必須是有限 Decimal")
        elif self.value is not None:
            raise ValueError("非有限 comparison value 不可帶 Decimal")

    @classmethod
    def finite(cls, value: Decimal | int) -> ReplayComparisonValue:
        if type(value) is int:
            value = Decimal(value)
        if type(value) is not Decimal or not value.is_finite():
            raise TypeError("finite comparison value 僅接受有限 Decimal 或 int")
        return cls(ReplayComparisonKind.FINITE, value)

    @classmethod
    def positive_infinity(cls) -> ReplayComparisonValue:
        return cls(ReplayComparisonKind.POSITIVE_INFINITY)

    @classmethod
    def negative_infinity(cls) -> ReplayComparisonValue:
        return cls(ReplayComparisonKind.NEGATIVE_INFINITY)

    @classmethod
    def unordered(cls) -> ReplayComparisonValue:
        return cls(ReplayComparisonKind.UNORDERED)


class ReplayPreflightDisposition(str, Enum):
    READY = "ready"
    REJECT = "reject"
    UNSUPPORTED = "unsupported"
    NEED_FACT = "need_fact"


class ReplayHistoryPreflightDisposition(str, Enum):
    """只有歷史列數的終端早期判斷，不代表候選已可評分。"""

    INSUFFICIENT_HISTORY = "insufficient_history"
    CONTINUE_TO_FAST_FILTERS = "continue_to_fast_filters"


@dataclass(frozen=True, slots=True)
class ReplayHistoryPreflightV1:
    """將 replay 最低歷史列數 gate 明示成純 typed preflight。"""

    history_rows: int
    disposition: ReplayHistoryPreflightDisposition
    minimum_history_rows: int = MINIMUM_RECOMMENDATION_HISTORY_ROWS
    policy_version: str = REPLAY_FAST_FILTER_POLICY_VERSION

    def __post_init__(self) -> None:
        if type(self.history_rows) is not int or self.history_rows < 0:
            raise ValueError("history_rows 必須是非負 int")
        if (
            type(self.minimum_history_rows) is not int
            or self.minimum_history_rows != MINIMUM_RECOMMENDATION_HISTORY_ROWS
        ):
            raise ValueError("minimum_history_rows 必須使用共用 replay 門檻")
        if type(self.disposition) is not ReplayHistoryPreflightDisposition:
            raise TypeError("disposition 必須是 ReplayHistoryPreflightDisposition")
        if (
            type(self.policy_version) is not str
            or self.policy_version != REPLAY_FAST_FILTER_POLICY_VERSION
        ):
            raise ValueError("不支援的 replay fast-filter policy version")
        expected = (
            ReplayHistoryPreflightDisposition.INSUFFICIENT_HISTORY
            if self.history_rows < self.minimum_history_rows
            else ReplayHistoryPreflightDisposition.CONTINUE_TO_FAST_FILTERS
        )
        if self.disposition is not expected:
            raise ValueError("disposition 與 history_rows 不一致")


def evaluate_replay_history_preflight(
    history_rows: int,
) -> ReplayHistoryPreflightV1:
    """只判斷最低歷史列數；不檢查日期、指標、門檻或 scorer readiness。"""

    if type(history_rows) is not int or history_rows < 0:
        raise ValueError("history_rows 必須是非負 int")
    disposition = (
        ReplayHistoryPreflightDisposition.INSUFFICIENT_HISTORY
        if history_rows < MINIMUM_RECOMMENDATION_HISTORY_ROWS
        else ReplayHistoryPreflightDisposition.CONTINUE_TO_FAST_FILTERS
    )
    return ReplayHistoryPreflightV1(
        history_rows=history_rows,
        disposition=disposition,
    )


class ReplayPrefilterFactKind(str, Enum):
    """依 legacy lazy-evaluation 順序取得的一個 replay prefilter fact。"""

    PRICE_CHANGE_METRIC = "price_change_metric"
    PRICE_CHANGE_MIN_THRESHOLD = "price_change_min_threshold"
    PRICE_CHANGE_MAX_THRESHOLD = "price_change_max_threshold"
    VOLUME_CHANGE_METRIC = "volume_change_metric"
    VOLUME_CHANGE_MIN_THRESHOLD = "volume_change_min_threshold"


class ReplayPreflightStage(str, Enum):
    MINIMUM_HISTORY = "minimum_history"
    PRICE_CHANGE_MIN = "price_change_min"
    PRICE_CHANGE_MAX = "price_change_max"
    VOLUME_RATIO_MIN = "volume_ratio_min"
    READY = "ready"


ReplayComparable = ReplayComparisonValue | ReplayComparisonOperand
ReplayNumber = Decimal | int | ReplayComparable


def _as_finite_decimal(value: Decimal | int, field_name: str) -> Decimal:
    if type(value) is int:
        return Decimal(value)
    if type(value) is not Decimal:
        raise TypeError(f"{field_name} 僅接受 Decimal 或 int")
    if not value.is_finite():
        raise ValueError(f"{field_name} 必須是有限 Decimal")
    return value


def _comparison_value(
    value: ReplayNumber,
    field_name: str,
) -> ReplayComparable:
    if isinstance(value, (ReplayComparisonValue, ReplayComparisonOperand)):
        return value
    if type(value) not in (Decimal, int):
        raise TypeError(
            f"{field_name} 僅接受 Decimal 或 int，或 typed replay operand"
        )
    return ReplayComparisonValue.finite(_as_finite_decimal(value, field_name))


def _optional_comparison_value(
    value: ReplayNumber | None,
    field_name: str,
) -> ReplayComparable | None:
    if value is None:
        return None
    return _comparison_value(value, field_name)


@dataclass(frozen=True, slots=True)
class ReplayThreshold:
    """一個已正規化、待 lazy 解析或明確停用的 fast-filter threshold。"""

    status: ReplayThresholdStatus = ReplayThresholdStatus.DISABLED
    value: ReplayNumber | None = None
    unsupported_reason: str | None = None

    def __post_init__(self) -> None:
        if type(self.status) is not ReplayThresholdStatus:
            raise TypeError("threshold status 必須是 ReplayThresholdStatus")
        value = _optional_comparison_value(self.value, "threshold value")
        if value is not None:
            object.__setattr__(self, "value", value)

        if self.status is ReplayThresholdStatus.ENABLED:
            if value is None or self.unsupported_reason is not None:
                raise ValueError("enabled threshold 必須有值且不可有 unsupported_reason")
        elif self.status is ReplayThresholdStatus.DISABLED:
            if value is not None or self.unsupported_reason is not None:
                raise ValueError("disabled threshold 不可有值或 unsupported_reason")
        elif self.status is ReplayThresholdStatus.PENDING:
            if value is not None or self.unsupported_reason is not None:
                raise ValueError("pending threshold 不可有值或 unsupported_reason")
        else:
            if value is not None:
                raise ValueError("unsupported threshold 不可帶可比較數值")
            if (
                type(self.unsupported_reason) is not str
                or not self.unsupported_reason.strip()
            ):
                raise ValueError("unsupported threshold 必須有明示原因碼")

    @classmethod
    def disabled(cls) -> ReplayThreshold:
        return cls()

    @classmethod
    def pending(cls) -> ReplayThreshold:
        """待 evaluator 發出對應 request 後才由 adapter 回填的門檻。"""

        return cls(status=ReplayThresholdStatus.PENDING)

    @classmethod
    def enabled(cls, value: ReplayNumber) -> ReplayThreshold:
        return cls(status=ReplayThresholdStatus.ENABLED, value=value)

    @classmethod
    def positive_infinity(cls) -> ReplayThreshold:
        return cls.enabled(ReplayComparisonValue.positive_infinity())

    @classmethod
    def negative_infinity(cls) -> ReplayThreshold:
        return cls.enabled(ReplayComparisonValue.negative_infinity())

    @classmethod
    def unordered(cls) -> ReplayThreshold:
        return cls.enabled(ReplayComparisonValue.unordered())

    @classmethod
    def unsupported(cls, reason_code: str) -> ReplayThreshold:
        return cls(
            status=ReplayThresholdStatus.UNSUPPORTED,
            unsupported_reason=reason_code,
        )


class ReplayVolumeThresholdKind(str, Enum):
    RAW_RATIO = "raw_ratio"
    EFFECTIVE_CHANGE_PERCENT = "effective_change_percent"


@dataclass(frozen=True, slots=True)
class ReplayVolumeThresholdV1:
    """具名 volume 門檻單位；raw Decimal 路徑不代表 legacy float ULP 等價。

    C1b legacy adapter 帶入原轉換結果時必須選 effective percent，避免二次
    normalize；raw ratio 僅保留目前 C0 純 Decimal contract 的相容路徑。
    """

    kind: ReplayVolumeThresholdKind
    threshold: ReplayThreshold
    version: str = REPLAY_VOLUME_THRESHOLD_VERSION

    def __post_init__(self) -> None:
        if self.version != REPLAY_VOLUME_THRESHOLD_VERSION:
            raise ValueError("不支援的 replay volume threshold version")
        if type(self.kind) is not ReplayVolumeThresholdKind:
            raise TypeError("volume threshold kind 必須是 ReplayVolumeThresholdKind")
        if type(self.threshold) is not ReplayThreshold:
            raise TypeError("threshold 必須是 ReplayThreshold")

    @classmethod
    def raw_ratio(cls, threshold: ReplayThreshold) -> ReplayVolumeThresholdV1:
        return cls(ReplayVolumeThresholdKind.RAW_RATIO, threshold)

    @classmethod
    def effective_change_percent(
        cls,
        threshold: ReplayThreshold,
    ) -> ReplayVolumeThresholdV1:
        return cls(ReplayVolumeThresholdKind.EFFECTIVE_CHANGE_PERCENT, threshold)


@dataclass(frozen=True, slots=True)
class ReplayFastFilterPolicyV1:
    """R020 fast-filter 子政策；不是完整 replay policy 或 evaluator。"""

    price_change_min: ReplayThreshold = field(default_factory=ReplayThreshold.disabled)
    price_change_max: ReplayThreshold = field(default_factory=ReplayThreshold.disabled)
    volume_ratio_min: ReplayThreshold = field(default_factory=ReplayThreshold.disabled)
    volume_minimum: ReplayVolumeThresholdV1 | None = None
    version: str = REPLAY_FAST_FILTER_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.version != REPLAY_FAST_FILTER_POLICY_VERSION:
            raise ValueError("不支援的 replay fast-filter policy version")
        for name in ("price_change_min", "price_change_max", "volume_ratio_min"):
            if type(getattr(self, name)) is not ReplayThreshold:
                raise TypeError(f"{name} 必須是 ReplayThreshold")
        if self.volume_minimum is not None:
            if type(self.volume_minimum) is not ReplayVolumeThresholdV1:
                raise TypeError("volume_minimum 必須是 ReplayVolumeThresholdV1 或 None")
            if self.volume_ratio_min.status is not ReplayThresholdStatus.DISABLED:
                raise ValueError("raw ratio 與 versioned volume_minimum 不可同時設定")

    @property
    def normalized_volume_change_min_percent(self) -> ReplayNumber | None:
        """相容 C0 accessor；effective-percent 輸入不會再做 ratio 正規化。"""

        threshold = self._effective_volume_threshold()
        if threshold.status is not ReplayThresholdStatus.ENABLED:
            return None
        value = threshold.value
        if type(value) is ReplayComparisonOperand:
            return value
        if type(value) is not ReplayComparisonValue:
            raise AssertionError("enabled threshold 缺少 Decimal value")
        if value.kind is ReplayComparisonKind.FINITE:
            assert value.value is not None
            return value.value
        return value

    def _effective_volume_threshold(self) -> ReplayThreshold:
        if self.volume_minimum is None:
            return _normalize_raw_volume_threshold(self.volume_ratio_min)
        if self.volume_minimum.kind is ReplayVolumeThresholdKind.RAW_RATIO:
            return _normalize_raw_volume_threshold(self.volume_minimum.threshold)
        return self.volume_minimum.threshold


@dataclass(frozen=True, slots=True)
class ReplayCompatibilityCandidateKeyV1:
    """單次 invocation 內空白代碼候選的暫時相關鍵，不是股票或結果 identity。"""

    invocation_id: str
    candidate_id: str

    def __post_init__(self) -> None:
        for name in ("invocation_id", "candidate_id"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} 不可為空")


def _validate_prefilter_observation(
    observations: object,
    *,
    compatibility_candidate_key: ReplayCompatibilityCandidateKeyV1 | None,
) -> None:
    """驗證共用的純觀測欄位，並由兩種 identity contract 各自限縮。"""

    stock_code = getattr(observations, "stock_code")
    if type(stock_code) is not str:
        raise TypeError("stock_code 必須是 str")
    if compatibility_candidate_key is None:
        if not stock_code.strip():
            raise ValueError("stock_code 不可為空")
    elif type(compatibility_candidate_key) is not ReplayCompatibilityCandidateKeyV1:
        raise TypeError("compatibility_candidate_key 必須是 ReplayCompatibilityCandidateKeyV1")
    elif stock_code.strip():
        raise ValueError("compatibility candidate key 僅適用於原始空白代碼")

    as_of_date = getattr(observations, "as_of_date")
    history_rows = getattr(observations, "history_rows")
    availability_column_present = getattr(observations, "availability_column_present")
    maximum_row_date = getattr(observations, "maximum_row_date")
    maximum_available_date = getattr(observations, "maximum_available_date")
    if type(as_of_date) is not date:
        raise TypeError("as_of_date 必須是 date")
    if type(history_rows) is not int or history_rows < 0:
        raise ValueError("history_rows 必須是非負 int")
    if type(availability_column_present) is not bool:
        raise TypeError("availability_column_present 必須是 bool")
    for name, value in (
        ("maximum_row_date", maximum_row_date),
        ("maximum_available_date", maximum_available_date),
    ):
        if value is not None and type(value) is not date:
            raise TypeError(f"{name} 必須是 date 或 None")

    if history_rows == 0:
        if maximum_row_date is not None or maximum_available_date is not None:
            raise ValueError("空 history 不可帶最大日期")
    elif maximum_row_date is None:
        raise ValueError("非空 history 必須明示 maximum_row_date")

    if maximum_row_date is not None and maximum_row_date > as_of_date:
        raise ValueError("maximum_row_date 超過 replay cutoff")
    if availability_column_present:
        if history_rows > 0 and maximum_available_date is None:
            raise ValueError("有 availability 欄的非空 history 必須明示最大可得日")
        if maximum_available_date is not None and maximum_available_date > as_of_date:
            raise ValueError("maximum_available_date 超過 replay cutoff")
    elif maximum_available_date is not None:
        raise ValueError("未提供 availability 欄時 maximum_available_date 必須為 None")

    for status_name, value_name, metric_name, minimum_rows in (
        (
            "price_change_status",
            "price_change_percent",
            "price_change_percent",
            2,
        ),
        (
            "volume_change_status",
            "volume_change_percent",
            "volume_change_percent",
            MINIMUM_RECOMMENDATION_HISTORY_ROWS + 1,
        ),
    ):
        _validate_prefilter_metric(
            observations,
            status=getattr(observations, status_name),
            value=getattr(observations, value_name),
            metric_name=metric_name,
            minimum_rows=minimum_rows,
        )


@dataclass(frozen=True, slots=True)
class ReplayPrefilterObservations:
    """由 app 從 cutoff 內的單一、具有效 identity 候選 history 投影出的純觀測值。"""

    stock_code: str
    as_of_date: date
    history_rows: int
    maximum_row_date: date | None
    availability_column_present: bool
    maximum_available_date: date | None
    price_change_status: ReplayMetricStatus = ReplayMetricStatus.MISSING_COLUMN
    price_change_percent: ReplayNumber | None = None
    volume_change_status: ReplayMetricStatus = ReplayMetricStatus.MISSING_COLUMN
    volume_change_percent: ReplayNumber | None = None

    def __post_init__(self) -> None:
        _validate_prefilter_observation(self, compatibility_candidate_key=None)

    def _validate_metric(
        self,
        *,
        status: ReplayMetricStatus,
        value: ReplayNumber | None,
        metric_name: str,
        minimum_rows: int,
    ) -> None:
        _validate_prefilter_metric(
            self,
            status=status,
            value=value,
            metric_name=metric_name,
            minimum_rows=minimum_rows,
        )


@dataclass(frozen=True, slots=True)
class ReplayCompatibilityPrefilterObservationsV1:
    """R020 暫用的原始空白 code prefilter observations；不可建 canonical assessment。"""

    stock_code: str
    as_of_date: date
    history_rows: int
    maximum_row_date: date | None
    availability_column_present: bool
    maximum_available_date: date | None
    compatibility_candidate_key: ReplayCompatibilityCandidateKeyV1
    price_change_status: ReplayMetricStatus = ReplayMetricStatus.MISSING_COLUMN
    price_change_percent: ReplayNumber | None = None
    volume_change_status: ReplayMetricStatus = ReplayMetricStatus.MISSING_COLUMN
    volume_change_percent: ReplayNumber | None = None

    def __post_init__(self) -> None:
        if type(self.compatibility_candidate_key) is not ReplayCompatibilityCandidateKeyV1:
            raise TypeError("compatibility_candidate_key 必須是 ReplayCompatibilityCandidateKeyV1")
        _validate_prefilter_observation(
            self,
            compatibility_candidate_key=self.compatibility_candidate_key,
        )

    def _validate_metric(
        self,
        *,
        status: ReplayMetricStatus,
        value: ReplayNumber | None,
        metric_name: str,
        minimum_rows: int,
    ) -> None:
        _validate_prefilter_metric(
            self,
            status=status,
            value=value,
            metric_name=metric_name,
            minimum_rows=minimum_rows,
        )


def _validate_prefilter_metric(
    observations: object,
    *,
    status: ReplayMetricStatus,
    value: ReplayNumber | None,
    metric_name: str,
    minimum_rows: int,
) -> None:
    if type(status) is not ReplayMetricStatus:
        raise TypeError(f"{metric_name} status 必須是 ReplayMetricStatus")
    normalized = _optional_comparison_value(value, metric_name)
    if normalized is not None:
        object.__setattr__(observations, metric_name, normalized)

    history_rows = getattr(observations, "history_rows")
    if status in (ReplayMetricStatus.AVAILABLE, ReplayMetricStatus.ZERO_DENOMINATOR):
        if normalized is None:
            raise ValueError(f"{metric_name} 狀態要求數值")
        if history_rows < minimum_rows:
            raise ValueError(f"{metric_name} 狀態與 history_rows 不相容")
        if status is ReplayMetricStatus.ZERO_DENOMINATOR and not (
            _is_zero_comparison(normalized)
        ):
            raise ValueError("zero_denominator metric 必須是 0")
        return

    if status is ReplayMetricStatus.AWAITING_THRESHOLD_PROJECTION:
        if normalized is not None:
            raise ValueError(f"{metric_name} awaiting threshold projection 不可帶數值")
        if history_rows < minimum_rows:
            raise ValueError(f"{metric_name} awaiting threshold projection 與 history_rows 不相容")
        return

    if normalized is not None:
        raise ValueError(f"{metric_name} 缺值／unsupported 狀態不可帶數值")
    if status is ReplayMetricStatus.NOT_REQUESTED and history_rows < minimum_rows:
        raise ValueError(f"{metric_name} not_requested 與 history_rows 不相容")
    if status is ReplayMetricStatus.INSUFFICIENT_WINDOW and history_rows >= minimum_rows:
        raise ValueError(f"{metric_name} insufficient_window 與 history_rows 不相容")


@dataclass(frozen=True, slots=True)
class ReplayPreflightOutcome:
    """一筆候選 preflight 結果；ready 才允許呼叫既有 scorer。"""

    stock_code: str
    as_of_date: date
    policy_version: str
    disposition: ReplayPreflightDisposition
    stage: ReplayPreflightStage
    reason_code: str
    observed_value: Decimal | ReplayComparable | None = None
    required_value: Decimal | ReplayComparable | None = None
    required_fact: ReplayPrefilterFactKind | None = None

    def __post_init__(self) -> None:
        if type(self.stock_code) is not str:
            raise TypeError("stock_code 必須是 str")
        if not self.stock_code.strip():
            raise ValueError("stock_code 不可為空")
        if type(self.as_of_date) is not date:
            raise TypeError("as_of_date 必須是 date")
        if self.policy_version != REPLAY_FAST_FILTER_POLICY_VERSION:
            raise ValueError("不支援的 replay fast-filter policy version")
        if type(self.disposition) is not ReplayPreflightDisposition:
            raise TypeError("disposition 必須是 ReplayPreflightDisposition")
        if type(self.stage) is not ReplayPreflightStage:
            raise TypeError("stage 必須是 ReplayPreflightStage")
        if type(self.reason_code) is not str or not self.reason_code.strip():
            raise ValueError("reason_code 不可為空")
        for name in ("observed_value", "required_value"):
            value = getattr(self, name)
            if value is not None and type(value) not in (
                Decimal,
                ReplayComparisonValue,
                ReplayComparisonOperand,
            ):
                raise TypeError(
                    f"{name} 必須是 Decimal、ReplayComparisonValue、"
                    "ReplayComparisonOperand 或 None"
                )
            if type(value) is Decimal and not value.is_finite():
                raise ValueError(f"{name} 若為 Decimal 必須有限")
        if self.disposition is ReplayPreflightDisposition.NEED_FACT:
            if type(self.required_fact) is not ReplayPrefilterFactKind:
                raise ValueError("need_fact outcome 必須明示 required_fact")
        elif self.required_fact is not None:
            raise ValueError("非 need_fact outcome 不可帶 required_fact")

    @property
    def may_score(self) -> bool:
        return self.disposition is ReplayPreflightDisposition.READY


@dataclass(frozen=True, slots=True)
class ReplayCompatibilityPreflightOutcomeV1:
    """空白 raw code 的 evaluator 結果；不帶 canonical Assessment。"""

    stock_code: str
    as_of_date: date
    policy_version: str
    disposition: ReplayPreflightDisposition
    stage: ReplayPreflightStage
    reason_code: str
    compatibility_candidate_key: ReplayCompatibilityCandidateKeyV1
    observed_value: Decimal | ReplayComparable | None = None
    required_value: Decimal | ReplayComparable | None = None
    required_fact: ReplayPrefilterFactKind | None = None

    def __post_init__(self) -> None:
        if type(self.stock_code) is not str or self.stock_code.strip():
            raise ValueError("相容 preflight 僅接受原始空白 stock_code")
        if type(self.compatibility_candidate_key) is not ReplayCompatibilityCandidateKeyV1:
            raise TypeError("compatibility_candidate_key 必須是 ReplayCompatibilityCandidateKeyV1")
        if type(self.as_of_date) is not date:
            raise TypeError("as_of_date 必須是 date")
        if self.policy_version != REPLAY_FAST_FILTER_POLICY_VERSION:
            raise ValueError("不支援的 replay fast-filter policy version")
        if type(self.disposition) is not ReplayPreflightDisposition:
            raise TypeError("disposition 必須是 ReplayPreflightDisposition")
        if type(self.stage) is not ReplayPreflightStage:
            raise TypeError("stage 必須是 ReplayPreflightStage")
        if type(self.reason_code) is not str or not self.reason_code.strip():
            raise ValueError("reason_code 不可為空")
        for name in ("observed_value", "required_value"):
            value = getattr(self, name)
            if value is not None and type(value) not in (
                Decimal,
                ReplayComparisonValue,
                ReplayComparisonOperand,
            ):
                raise TypeError(
                    f"{name} 必須是 Decimal、ReplayComparisonValue、"
                    "ReplayComparisonOperand 或 None"
                )
            if type(value) is Decimal and not value.is_finite():
                raise ValueError(f"{name} 若為 Decimal 必須有限")
        if self.disposition is ReplayPreflightDisposition.NEED_FACT:
            if type(self.required_fact) is not ReplayPrefilterFactKind:
                raise ValueError("need_fact outcome 必須明示 required_fact")
        elif self.required_fact is not None:
            raise ValueError("非 need_fact outcome 不可帶 required_fact")

    @property
    def may_score(self) -> bool:
        return self.disposition is ReplayPreflightDisposition.READY


ReplayPrefilterObservationV1 = (
    ReplayPrefilterObservations | ReplayCompatibilityPrefilterObservationsV1
)
ReplayPrefilterOutcomeV1 = ReplayPreflightOutcome | ReplayCompatibilityPreflightOutcomeV1


def _outcome(
    observations: ReplayPrefilterObservationV1,
    *,
    disposition: ReplayPreflightDisposition,
    stage: ReplayPreflightStage,
    reason_code: str,
    observed_value: Decimal | ReplayComparable | None = None,
    required_value: Decimal | ReplayComparable | None = None,
    required_fact: ReplayPrefilterFactKind | None = None,
) -> ReplayPrefilterOutcomeV1:
    if type(observations) is ReplayCompatibilityPrefilterObservationsV1:
        return ReplayCompatibilityPreflightOutcomeV1(
            stock_code=observations.stock_code,
            as_of_date=observations.as_of_date,
            policy_version=REPLAY_FAST_FILTER_POLICY_VERSION,
            disposition=disposition,
            stage=stage,
            reason_code=reason_code,
            compatibility_candidate_key=observations.compatibility_candidate_key,
            observed_value=observed_value,
            required_value=required_value,
            required_fact=required_fact,
        )
    return ReplayPreflightOutcome(
        stock_code=observations.stock_code,
        as_of_date=observations.as_of_date,
        policy_version=REPLAY_FAST_FILTER_POLICY_VERSION,
        disposition=disposition,
        stage=stage,
        reason_code=reason_code,
        observed_value=observed_value,
        required_value=required_value,
        required_fact=required_fact,
    )


def _need_fact(
    observations: ReplayPrefilterObservationV1,
    *,
    stage: ReplayPreflightStage,
    fact: ReplayPrefilterFactKind,
) -> ReplayPrefilterOutcomeV1:
    return _outcome(
        observations,
        disposition=ReplayPreflightDisposition.NEED_FACT,
        stage=stage,
        reason_code=f"need_{fact.value}",
        required_fact=fact,
    )


def _comparison_diagnostic(
    value: ReplayComparable,
) -> Decimal | ReplayComparable:
    if isinstance(value, ReplayComparisonOperand):
        return value
    if value.kind is ReplayComparisonKind.FINITE:
        assert value.value is not None
        return value.value
    return value


def _is_zero_comparison(value: ReplayComparable) -> bool:
    if isinstance(value, ReplayComparisonValue):
        return value.kind is ReplayComparisonKind.FINITE and value.value == 0
    return (
        value.imaginary is None
        and value.real.kind is ReplayComparisonKind.FINITE
        and value.real.numerator == 0
    )


@dataclass(frozen=True, slots=True)
class ReplayThresholdMetricProjection:
    """同一次 metric request 對一個 threshold stage 的有效域投影。"""

    threshold_fact: ReplayPrefilterFactKind
    metric_request_id: str
    metric_status: ReplayMetricStatus
    metric_value: ReplayComparisonOperand

    def __post_init__(self) -> None:
        if type(self.threshold_fact) is not ReplayPrefilterFactKind or self.threshold_fact not in {
            ReplayPrefilterFactKind.PRICE_CHANGE_MIN_THRESHOLD,
            ReplayPrefilterFactKind.PRICE_CHANGE_MAX_THRESHOLD,
            ReplayPrefilterFactKind.VOLUME_CHANGE_MIN_THRESHOLD,
        }:
            raise ValueError("threshold_fact 必須識別一個 fast-filter threshold stage")
        if type(self.metric_request_id) is not str or not self.metric_request_id.strip():
            raise ValueError("metric_request_id 不可為空")
        if type(self.metric_status) is not ReplayMetricStatus or self.metric_status not in {
            ReplayMetricStatus.AVAILABLE,
            ReplayMetricStatus.ZERO_DENOMINATOR,
        }:
            raise ValueError("metric_status 必須是 AVAILABLE 或 ZERO_DENOMINATOR")
        if type(self.metric_value) is not ReplayComparisonOperand:
            raise TypeError("metric_value 必須是 ReplayComparisonOperand")
        if self.metric_status is ReplayMetricStatus.ZERO_DENOMINATOR and not (
            _is_zero_comparison(self.metric_value)
        ):
            raise ValueError("ZERO_DENOMINATOR metric projection 必須是 0")


class ReplayComparisonOperator(str, Enum):
    LESS_THAN = "<"
    GREATER_THAN = ">"
    LESS_THAN_OR_EQUAL = "<="
    GREATER_THAN_OR_EQUAL = ">="


class ReplayComparisonDomainMismatchError(TypeError):
    """metric 與 threshold 未由 adapter 統一到相同 effective domain。"""


def _legacy_comparison_operand(value: ReplayComparisonValue) -> ReplayComparisonOperand:
    if value.kind is ReplayComparisonKind.FINITE:
        assert value.value is not None
        numerator, denominator = value.value.as_integer_ratio()
        component = ReplayComparisonComponent.finite(numerator, denominator)
    elif value.kind is ReplayComparisonKind.POSITIVE_INFINITY:
        component = ReplayComparisonComponent.positive_infinity()
    elif value.kind is ReplayComparisonKind.NEGATIVE_INFINITY:
        component = ReplayComparisonComponent.negative_infinity()
    else:
        component = ReplayComparisonComponent.unordered()
    return ReplayComparisonOperand(
        origin=ReplayNumericOrigin(ReplayNumericOriginKind.LEGACY_DECIMAL),
        domain=ReplayComparisonDomain.exact_rational(),
        real=component,
    )


def _as_comparison_operand(value: ReplayComparable) -> ReplayComparisonOperand:
    if isinstance(value, ReplayComparisonOperand):
        return value
    assert isinstance(value, ReplayComparisonValue)
    return _legacy_comparison_operand(value)


def _compare_components(
    left: ReplayComparisonComponent,
    right: ReplayComparisonComponent,
) -> int | None:
    """回傳 -1/0/1；None 表示舊 NaN/unordered 比較結果。"""

    if (
        left.kind is ReplayComparisonKind.UNORDERED
        or right.kind is ReplayComparisonKind.UNORDERED
    ):
        return None
    if left.kind is ReplayComparisonKind.NEGATIVE_INFINITY:
        return 0 if right.kind is ReplayComparisonKind.NEGATIVE_INFINITY else -1
    if right.kind is ReplayComparisonKind.NEGATIVE_INFINITY:
        return 1
    if left.kind is ReplayComparisonKind.POSITIVE_INFINITY:
        return 0 if right.kind is ReplayComparisonKind.POSITIVE_INFINITY else 1
    if right.kind is ReplayComparisonKind.POSITIVE_INFINITY:
        return -1

    assert left.numerator is not None and left.denominator is not None
    assert right.numerator is not None and right.denominator is not None
    left_scaled = left.numerator * right.denominator
    right_scaled = right.numerator * left.denominator
    return (left_scaled > right_scaled) - (left_scaled < right_scaled)


def _origin_type_name(origin: ReplayNumericOrigin) -> str:
    if origin.kind is ReplayNumericOriginKind.LEGACY_DECIMAL:
        return "Decimal"
    if origin.kind is ReplayNumericOriginKind.PYTHON_INT:
        return "int"
    if origin.kind is ReplayNumericOriginKind.PYTHON_FLOAT:
        return "float"
    if origin.kind is ReplayNumericOriginKind.PYTHON_COMPLEX:
        return "complex"
    assert origin.dtype_name is not None
    dtype_name = origin.dtype_name
    return dtype_name if dtype_name.startswith("numpy.") else f"numpy.{dtype_name}"


@dataclass(frozen=True, slots=True)
class ReplayComparisonResult:
    """唯一 numeric comparator 的布林結果與實際參與比較的 unordered 狀態。"""

    matched: bool
    unordered: bool
    numpy_invalid_effect: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.matched) is not bool
            or type(self.unordered) is not bool
            or type(self.numpy_invalid_effect) is not bool
        ):
            raise TypeError("comparison result 欄位必須是 bool")
        if self.unordered and self.matched:
            raise ValueError("unordered comparison 不可 matched")
        if self.numpy_invalid_effect and (not self.unordered or self.matched):
            raise ValueError("NumPy invalid effect 必須對應 unordered rejection")


def _compare_replay_operands(
    left: ReplayComparable,
    right: ReplayComparable,
    *,
    operator: ReplayComparisonOperator = ReplayComparisonOperator.LESS_THAN,
) -> ReplayComparisonResult:
    """唯一 directional comparator：回傳比較值及實際參與的 unordered 狀態。"""

    if type(operator) is not ReplayComparisonOperator:
        raise TypeError("operator 必須是 ReplayComparisonOperator")
    left_operand = _as_comparison_operand(left)
    right_operand = _as_comparison_operand(right)

    # Python complex 的 ordering 不存在；此處依原 operand 順序與運算子
    # 重建原生 TypeError 語意，尤其不能用反轉 `<` 來模擬 `>`。
    if (
        left_operand.domain.kind is ReplayComparisonDomainKind.PYTHON_COMPLEX
        or right_operand.domain.kind is ReplayComparisonDomainKind.PYTHON_COMPLEX
    ):
        left_type = _origin_type_name(left_operand.origin)
        right_type = _origin_type_name(right_operand.origin)
        raise TypeError(
            f"'{operator.value}' not supported between instances of "
            f"'{left_type}' and '{right_type}'"
        )

    if left_operand.domain != right_operand.domain:
        raise ReplayComparisonDomainMismatchError(
            "replay metric 與 threshold comparison domain 不一致"
        )

    if left_operand.domain.kind in {
        ReplayComparisonDomainKind.NUMPY_COMPLEX,
        ReplayComparisonDomainKind.PANDAS_COMPLEX_SERIES,
    }:
        if left_operand.imaginary is None or right_operand.imaginary is None:
            raise AssertionError("NumPy complex operand 缺少 imaginary component")
        real_order = _compare_components(left_operand.real, right_operand.real)
        if real_order is None:
            return ReplayComparisonResult(
                matched=False,
                unordered=True,
                numpy_invalid_effect=(
                    left_operand.domain.kind
                    is ReplayComparisonDomainKind.PANDAS_COMPLEX_SERIES
                ),
            )
        if left_operand.domain.kind is ReplayComparisonDomainKind.PANDAS_COMPLEX_SERIES:
            imaginary_order = _compare_components(
                left_operand.imaginary,
                right_operand.imaginary,
            )
            if imaginary_order is None:
                return ReplayComparisonResult(
                    matched=False,
                    unordered=True,
                    numpy_invalid_effect=real_order == 0,
                )
        if real_order != 0:
            return ReplayComparisonResult(
                matched=_comparison_order_satisfies(real_order, operator),
                unordered=False,
            )
        order = _compare_components(left_operand.imaginary, right_operand.imaginary)
    else:
        if left_operand.imaginary is not None or right_operand.imaginary is not None:
            raise AssertionError("real comparison domain 不可帶 imaginary component")
        order = _compare_components(left_operand.real, right_operand.real)

    if order is None:
        return ReplayComparisonResult(matched=False, unordered=True)
    return ReplayComparisonResult(
        matched=_comparison_order_satisfies(order, operator),
        unordered=False,
    )


def _comparison_less_than(
    left: ReplayComparable,
    right: ReplayComparable,
    *,
    operator: ReplayComparisonOperator = ReplayComparisonOperator.LESS_THAN,
) -> bool:
    """維持既有 bool API，由唯一 comparator 執行 directional comparison。"""

    return _compare_replay_operands(left, right, operator=operator).matched


def _comparison_order_satisfies(
    order: int,
    operator: ReplayComparisonOperator,
) -> bool:
    if operator is ReplayComparisonOperator.LESS_THAN:
        return order < 0
    if operator is ReplayComparisonOperator.GREATER_THAN:
        return order > 0
    if operator is ReplayComparisonOperator.LESS_THAN_OR_EQUAL:
        return order <= 0
    return order >= 0


def _comparison_greater_than(
    left: ReplayComparable,
    right: ReplayComparable,
) -> bool:
    return _comparison_less_than(
        left,
        right,
        operator=ReplayComparisonOperator.GREATER_THAN,
    )


def compare_replay_operands(
    left: ReplayComparisonOperand,
    right: ReplayComparisonOperand,
    *,
    operator: ReplayComparisonOperator,
) -> bool:
    """公開給同一 decision layer 其他 pure phase 共用的 typed comparator。

    本函式只轉呼叫既有唯一比較核心；不做轉型、正規化、缺值推斷或 NaN
    接受決策。呼叫端需先依各自 policy 明確處理 unordered operand。
    """

    if type(left) is not ReplayComparisonOperand:
        raise TypeError("left 必須是 ReplayComparisonOperand")
    if type(right) is not ReplayComparisonOperand:
        raise TypeError("right 必須是 ReplayComparisonOperand")
    return _comparison_less_than(left, right, operator=operator)


def compare_replay_operands_with_status(
    left: ReplayComparisonOperand,
    right: ReplayComparisonOperand,
    *,
    operator: ReplayComparisonOperator,
) -> ReplayComparisonResult:
    """回傳唯一比較結果及真正參與該次比較的 unordered 狀態。"""

    if type(left) is not ReplayComparisonOperand:
        raise TypeError("left 必須是 ReplayComparisonOperand")
    if type(right) is not ReplayComparisonOperand:
        raise TypeError("right 必須是 ReplayComparisonOperand")
    return _compare_replay_operands(left, right, operator=operator)


def _apply_minimum_filter(
    observations: ReplayPrefilterObservationV1,
    *,
    threshold: ReplayThreshold,
    metric_status: ReplayMetricStatus,
    metric_value: ReplayNumber | None,
    stage: ReplayPreflightStage,
    reason_code: str,
    metric_fact: ReplayPrefilterFactKind,
    threshold_fact: ReplayPrefilterFactKind,
    projection_required: bool = False,
) -> ReplayPrefilterOutcomeV1 | None:
    if threshold.status is ReplayThresholdStatus.DISABLED:
        return None
    if metric_status in (
        ReplayMetricStatus.MISSING_COLUMN,
        ReplayMetricStatus.INSUFFICIENT_WINDOW,
    ):
        return None
    if metric_status is ReplayMetricStatus.NOT_REQUESTED:
        return _need_fact(observations, stage=stage, fact=metric_fact)
    if threshold.status is ReplayThresholdStatus.PENDING:
        return _need_fact(observations, stage=stage, fact=threshold_fact)
    if threshold.status is ReplayThresholdStatus.UNSUPPORTED:
        return _outcome(
            observations,
            disposition=ReplayPreflightDisposition.UNSUPPORTED,
            stage=stage,
            reason_code=f"unsupported_{reason_code}_threshold:{threshold.unsupported_reason}",
        )
    if metric_status is ReplayMetricStatus.UNSUPPORTED:
        return _outcome(
            observations,
            disposition=ReplayPreflightDisposition.UNSUPPORTED,
            stage=stage,
            reason_code=f"unsupported_{reason_code}_observation",
        )
    if projection_required or metric_status is ReplayMetricStatus.AWAITING_THRESHOLD_PROJECTION:
        return _need_fact(observations, stage=stage, fact=threshold_fact)

    required = threshold.value
    if not isinstance(required, (ReplayComparisonValue, ReplayComparisonOperand)) or metric_value is None:
        raise AssertionError("可比較 filter 缺少 threshold 或 metric")
    observed = _comparison_value(metric_value, "metric_value")
    if _comparison_less_than(observed, required):
        return _outcome(
            observations,
            disposition=ReplayPreflightDisposition.REJECT,
            stage=stage,
            reason_code=reason_code,
            observed_value=_comparison_diagnostic(observed),
            required_value=_comparison_diagnostic(required),
        )
    return None


def _apply_maximum_filter(
    observations: ReplayPrefilterObservationV1,
    *,
    threshold: ReplayThreshold,
    metric_status: ReplayMetricStatus,
    metric_value: ReplayNumber | None,
    metric_fact: ReplayPrefilterFactKind,
    threshold_fact: ReplayPrefilterFactKind,
    projection_required: bool = False,
) -> ReplayPrefilterOutcomeV1 | None:
    stage = ReplayPreflightStage.PRICE_CHANGE_MAX
    if threshold.status is ReplayThresholdStatus.DISABLED:
        return None
    if metric_status in (
        ReplayMetricStatus.MISSING_COLUMN,
        ReplayMetricStatus.INSUFFICIENT_WINDOW,
    ):
        return None
    if metric_status is ReplayMetricStatus.NOT_REQUESTED:
        return _need_fact(observations, stage=stage, fact=metric_fact)
    if threshold.status is ReplayThresholdStatus.PENDING:
        return _need_fact(observations, stage=stage, fact=threshold_fact)
    if threshold.status is ReplayThresholdStatus.UNSUPPORTED:
        return _outcome(
            observations,
            disposition=ReplayPreflightDisposition.UNSUPPORTED,
            stage=stage,
            reason_code=f"unsupported_price_change_max_threshold:{threshold.unsupported_reason}",
        )
    if metric_status is ReplayMetricStatus.UNSUPPORTED:
        return _outcome(
            observations,
            disposition=ReplayPreflightDisposition.UNSUPPORTED,
            stage=stage,
            reason_code="unsupported_price_change_max_observation",
        )
    if projection_required or metric_status is ReplayMetricStatus.AWAITING_THRESHOLD_PROJECTION:
        return _need_fact(observations, stage=stage, fact=threshold_fact)

    required = threshold.value
    if not isinstance(required, (ReplayComparisonValue, ReplayComparisonOperand)) or metric_value is None:
        raise AssertionError("可比較 filter 缺少 threshold 或 metric")
    observed = _comparison_value(metric_value, "metric_value")
    if _comparison_greater_than(observed, required):
        return _outcome(
            observations,
            disposition=ReplayPreflightDisposition.REJECT,
            stage=stage,
            reason_code="price_change_above_max",
            observed_value=_comparison_diagnostic(observed),
            required_value=_comparison_diagnostic(required),
        )
    return None


def evaluate_replay_prefilter(
    policy: ReplayFastFilterPolicyV1,
    observations: ReplayPrefilterObservationV1,
    *,
    stage_projections: tuple[ReplayThresholdMetricProjection, ...] = (),
    pending_projection_stages: tuple[ReplayPrefilterFactKind, ...] = (),
) -> ReplayPrefilterOutcomeV1:
    """依 R005 順序產生一筆 preflight 結果，不呼叫 scorer 或 ranking。"""

    if type(policy) is not ReplayFastFilterPolicyV1:
        raise TypeError("policy 必須是 ReplayFastFilterPolicyV1")
    if type(observations) not in {
        ReplayPrefilterObservations,
        ReplayCompatibilityPrefilterObservationsV1,
    }:
        raise TypeError("observations 必須是 replay prefilter observations contract")
    if type(stage_projections) is not tuple or any(
        type(projection) is not ReplayThresholdMetricProjection
        for projection in stage_projections
    ):
        raise TypeError("stage_projections 必須是 ReplayThresholdMetricProjection tuple")
    if type(pending_projection_stages) is not tuple or any(
        type(stage) is not ReplayPrefilterFactKind
        for stage in pending_projection_stages
    ):
        raise TypeError("pending_projection_stages 必須是 ReplayPrefilterFactKind tuple")
    allowed_projection_stages = {
        ReplayPrefilterFactKind.PRICE_CHANGE_MIN_THRESHOLD,
        ReplayPrefilterFactKind.PRICE_CHANGE_MAX_THRESHOLD,
        ReplayPrefilterFactKind.VOLUME_CHANGE_MIN_THRESHOLD,
    }
    if any(stage not in allowed_projection_stages for stage in pending_projection_stages):
        raise ValueError("pending_projection_stages 只能包含 threshold fact kind")
    if len({projection.threshold_fact for projection in stage_projections}) != len(
        stage_projections
    ):
        raise ValueError("stage_projections 不可重複 threshold stage")
    if len(set(pending_projection_stages)) != len(pending_projection_stages):
        raise ValueError("pending_projection_stages 不可重複")
    projection_by_stage = {
        projection.threshold_fact: projection for projection in stage_projections
    }
    if any(stage in projection_by_stage for stage in pending_projection_stages):
        raise ValueError("同一 threshold stage 不可同時已投影又 pending")
    threshold_by_stage = {
        ReplayPrefilterFactKind.PRICE_CHANGE_MIN_THRESHOLD: policy.price_change_min,
        ReplayPrefilterFactKind.PRICE_CHANGE_MAX_THRESHOLD: policy.price_change_max,
        ReplayPrefilterFactKind.VOLUME_CHANGE_MIN_THRESHOLD: policy._effective_volume_threshold(),
    }
    for stage in (*projection_by_stage, *pending_projection_stages):
        threshold = threshold_by_stage[stage]
        if threshold.status in {
            ReplayThresholdStatus.DISABLED,
            ReplayThresholdStatus.UNSUPPORTED,
        }:
            raise ValueError("disabled/unsupported threshold 不可有 projection stage")
        projection = projection_by_stage.get(stage)
        if projection is not None:
            if threshold.status is not ReplayThresholdStatus.ENABLED:
                raise ValueError("已回填 metric projection 的 threshold 必須 enabled")
            if type(threshold.value) is not ReplayComparisonOperand:
                raise ValueError("paired metric 與 threshold 必須使用 typed operand")
            if projection.metric_value.domain != threshold.value.domain:
                raise ValueError("stage metric projection 與 threshold domain 不一致")

    def projected_metric(
        stage: ReplayPrefilterFactKind,
        status: ReplayMetricStatus,
        value: ReplayNumber | None,
    ) -> tuple[ReplayMetricStatus, ReplayNumber | None]:
        projection = projection_by_stage.get(stage)
        if projection is None:
            return status, value
        return projection.metric_status, projection.metric_value

    history_preflight = evaluate_replay_history_preflight(
        observations.history_rows
    )
    if (
        history_preflight.disposition
        is ReplayHistoryPreflightDisposition.INSUFFICIENT_HISTORY
    ):
        return _outcome(
            observations,
            disposition=ReplayPreflightDisposition.REJECT,
            stage=ReplayPreflightStage.MINIMUM_HISTORY,
            reason_code="insufficient_history",
            observed_value=Decimal(history_preflight.history_rows),
            required_value=Decimal(history_preflight.minimum_history_rows),
        )

    price_min_status, price_min_value = projected_metric(
        ReplayPrefilterFactKind.PRICE_CHANGE_MIN_THRESHOLD,
        observations.price_change_status,
        observations.price_change_percent,
    )
    result = _apply_minimum_filter(
        observations,
        threshold=policy.price_change_min,
        metric_status=price_min_status,
        metric_value=price_min_value,
        stage=ReplayPreflightStage.PRICE_CHANGE_MIN,
        reason_code="price_change_below_min",
        metric_fact=ReplayPrefilterFactKind.PRICE_CHANGE_METRIC,
        threshold_fact=ReplayPrefilterFactKind.PRICE_CHANGE_MIN_THRESHOLD,
        projection_required=(
            ReplayPrefilterFactKind.PRICE_CHANGE_MIN_THRESHOLD
            in pending_projection_stages
        ),
    )
    if result is not None:
        return result

    price_max_status, price_max_value = projected_metric(
        ReplayPrefilterFactKind.PRICE_CHANGE_MAX_THRESHOLD,
        observations.price_change_status,
        observations.price_change_percent,
    )
    result = _apply_maximum_filter(
        observations,
        threshold=policy.price_change_max,
        metric_status=price_max_status,
        metric_value=price_max_value,
        metric_fact=ReplayPrefilterFactKind.PRICE_CHANGE_METRIC,
        threshold_fact=ReplayPrefilterFactKind.PRICE_CHANGE_MAX_THRESHOLD,
        projection_required=(
            ReplayPrefilterFactKind.PRICE_CHANGE_MAX_THRESHOLD
            in pending_projection_stages
        ),
    )
    if result is not None:
        return result

    volume_status, volume_value = projected_metric(
        ReplayPrefilterFactKind.VOLUME_CHANGE_MIN_THRESHOLD,
        observations.volume_change_status,
        observations.volume_change_percent,
    )
    result = _apply_minimum_filter(
        observations,
        threshold=policy._effective_volume_threshold(),
        metric_status=volume_status,
        metric_value=volume_value,
        stage=ReplayPreflightStage.VOLUME_RATIO_MIN,
        reason_code="volume_change_below_min",
        metric_fact=ReplayPrefilterFactKind.VOLUME_CHANGE_METRIC,
        threshold_fact=ReplayPrefilterFactKind.VOLUME_CHANGE_MIN_THRESHOLD,
        projection_required=(
            ReplayPrefilterFactKind.VOLUME_CHANGE_MIN_THRESHOLD
            in pending_projection_stages
        ),
    )
    if result is not None:
        return result

    return _outcome(
        observations,
        disposition=ReplayPreflightDisposition.READY,
        stage=ReplayPreflightStage.READY,
        reason_code="ready",
    )


def _normalize_volume_ratio_min(value: Decimal) -> Decimal:
    if _VOLUME_RATIO_NORMALIZATION_LOW <= value <= _VOLUME_RATIO_NORMALIZATION_HIGH:
        return (value - _ONE) * _HUNDRED
    return value


def _normalize_raw_volume_threshold(threshold: ReplayThreshold) -> ReplayThreshold:
    if threshold.status is not ReplayThresholdStatus.ENABLED:
        return threshold
    value = threshold.value
    if type(value) is not ReplayComparisonValue:
        raise TypeError(
            "typed volume threshold 必須使用 effective_change_percent，"
            "不可走 Decimal raw-ratio 正規化路徑"
        )
    if value.kind is not ReplayComparisonKind.FINITE:
        return threshold
    assert value.value is not None
    return ReplayThreshold.enabled(_normalize_volume_ratio_min(value.value))
