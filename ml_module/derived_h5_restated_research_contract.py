"""derived-h5 修訂資料的研究專用雙時鐘契約。

本模組只驗證候選資料證據，不建立資料、不執行訓練，也不替代既有 PIT
契約。歷史決策時間與修訂資料觀測時間分開保存；晚到修訂永遠不會因此成為
歷史 PIT 特徵。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
from typing import ClassVar, Literal
from zoneinfo import ZoneInfo


MODEL_FAMILY_ID = "baldr-ml-allocation-derived-h5-v4-rank-v2"
HORIZON_DAYS = 5
FEATURE_ORDER_HASH = (
    "sha256:a2a3a26f457f9901f90b1f08d3e844defe7abe279a22d722d197f56d3eb19611"
)
FEATURE_REGISTRY_HASH = (
    "sha256:8b0f831a94ecd503591a146d36412b2385397928b98fbd607a33fa6073630f27"
)
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1
RUN02_SNAPSHOT_HASH = (
    "sha256:38ab1d1dfd201285ed817c8e94f689f91a50b39dc30cdbb8a90a49b7ce898771"
)
RUN02_REVISION_ID = "price-revision-20260922-run02"
TAIPEI_TIMEZONE = ZoneInfo("Asia/Taipei")

DERIVED_H5_FEATURE_ORDER = (
    "data_quality.market_sector_cross_section.coverage_bp",
    "data_quality.market_sector_cross_section.max_available_lag_days",
    "data_quality.market_sector_cross_section.missing_count",
    "data_quality.market_sector_cross_section.quality_blocked_count",
    "data_quality.market_sector_cross_section.stale_count",
    "data_quality.price_liquidity_technical.coverage_bp",
    "data_quality.price_liquidity_technical.max_available_lag_days",
    "data_quality.price_liquidity_technical.missing_count",
    "data_quality.price_liquidity_technical.quality_blocked_count",
    "data_quality.price_liquidity_technical.stale_count",
    "industry_indices.收盤指數",
    "industry_indices.漲跌百分比",
    "industry_indices.漲跌點數",
    "market_indices.成交量",
    "market_indices.收盤價",
    "market_indices.收盤指數",
    "market_indices.最低價",
    "market_indices.最高價",
    "market_indices.漲跌百分比",
    "market_indices.漲跌點數",
    "market_indices.開盤價",
    "daily_prices.成交筆數",
    "daily_prices.成交股數",
    "daily_prices.成交金額",
    "daily_prices.收盤價",
    "daily_prices.最低價",
    "daily_prices.最後揭示買價",
    "daily_prices.最後揭示買量",
    "daily_prices.最後揭示賣價",
    "daily_prices.最後揭示賣量",
    "daily_prices.最高價",
    "daily_prices.本益比",
    "daily_prices.漲跌價差",
    "daily_prices.開盤價",
    "technical_indicators.ADX",
    "technical_indicators.ATR",
    "technical_indicators.DEMA30",
    "technical_indicators.EMA30",
    "technical_indicators.MA10",
    "technical_indicators.MA20",
    "technical_indicators.MA5",
    "technical_indicators.MA60",
    "technical_indicators.MACD",
    "technical_indicators.MACD_hist",
    "technical_indicators.MACD_signal",
    "technical_indicators.RSI",
    "technical_indicators.SAR",
    "technical_indicators.SMA30",
    "technical_indicators.TSF",
    "technical_indicators.lowerband",
    "technical_indicators.middleband",
    "technical_indicators.slowd",
    "technical_indicators.slowk",
    "technical_indicators.upperband",
    "technical_indicators.最後揭示買價",
    "technical_indicators.最後揭示買量",
    "technical_indicators.最後揭示賣價",
    "technical_indicators.最後揭示賣量",
    "technical_indicators.本益比",
    "technical_indicators.涨跌",
    "technical_indicators.漲跌(+/-)",
    "technical_indicators.漲跌價差",
)

REQUIRED_SOURCE_HASH_KEYS = (
    "run02_snapshot",
    "price_receipt",
    "technical_receipt",
    "recovery_receipt",
    "technical_verification",
    "corporate_action_exclusion_manifest",
    "feature_lineage_manifest",
    "label_lineage_manifest",
    "fold_manifest",
)

if len(DERIVED_H5_FEATURE_ORDER) != 62:
    raise RuntimeError("derived-h5 feature order must contain exactly 62 IDs")


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


if _canonical_hash({"feature_order": list(DERIVED_H5_FEATURE_ORDER)}) != FEATURE_ORDER_HASH:
    raise RuntimeError("embedded derived-h5 order does not match the frozen release hash")


def _require_sha256(value: str, *, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{field_name} must be a lowercase sha256 digest")


def _aware_datetime(value: str, *, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a timezone-aware ISO datetime")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"{field_name} must be a timezone-aware ISO datetime"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed


def _iso_date(value: str, *, field_name: str) -> date:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date") from exc


def feature_values_hash(
    *, values_i64: tuple[int | None, ...], scales: tuple[int, ...]
) -> str:
    """計算固定 derived-h5 順序下的整數特徵內容雜湊。"""

    return _canonical_hash(
        {
            "dtype": "int64",
            "feature_order_hash": FEATURE_ORDER_HASH,
            "scales": list(scales),
            "values_i64": list(values_i64),
        }
    )


def feature_mask_hash(*, observed_mask: tuple[bool, ...]) -> str:
    """計算固定 derived-h5 順序下的明確缺值遮罩雜湊。"""

    return _canonical_hash(
        {
            "dtype": "bool",
            "feature_order_hash": FEATURE_ORDER_HASH,
            "observed_mask": list(observed_mask),
        }
    )


def dataset_identity_hash(
    *,
    dataset_id: str,
    source_revision_id: str,
    source_hashes: tuple[tuple[str, str], ...],
) -> str:
    """計算新 research dataset identity；不使用舊 release identity。"""

    return _canonical_hash(
        {
            "dataset_id": dataset_id,
            "feature_order_hash": FEATURE_ORDER_HASH,
            "feature_registry_hash": FEATURE_REGISTRY_HASH,
            "horizon_days": HORIZON_DAYS,
            "model_family_id": MODEL_FAMILY_ID,
            "source_hashes": {key: value for key, value in source_hashes},
            "source_revision_id": source_revision_id,
        }
    )


@dataclass(frozen=True)
class RestatedH5SourceIdentity:
    """修訂候選所需的來源集合與新資料集 identity。"""

    dataset_id: str
    source_revision_id: str
    source_hashes: tuple[tuple[str, str], ...]
    dataset_identity_sha256: str

    def __post_init__(self) -> None:
        if not self.dataset_id.startswith("restated-derived-h5-"):
            raise ValueError("dataset_id must identify a new restated derived-h5 dataset")
        if self.source_revision_id != RUN02_REVISION_ID:
            raise ValueError("source_revision_id does not match the approved run02 scope")
        keys = tuple(key for key, _ in self.source_hashes)
        if keys != tuple(sorted(REQUIRED_SOURCE_HASH_KEYS)):
            raise ValueError("source_hashes must contain every required source exactly once")
        for key, value in self.source_hashes:
            _require_sha256(value, field_name=f"source_hashes.{key}")
        source_map = dict(self.source_hashes)
        if source_map["run02_snapshot"] != RUN02_SNAPSHOT_HASH:
            raise ValueError("run02_snapshot hash does not match the approved snapshot")
        _require_sha256(
            self.dataset_identity_sha256,
            field_name="dataset_identity_sha256",
        )
        expected_identity = dataset_identity_hash(
            dataset_id=self.dataset_id,
            source_revision_id=self.source_revision_id,
            source_hashes=self.source_hashes,
        )
        if self.dataset_identity_sha256 != expected_identity:
            raise ValueError("dataset_identity_sha256 does not match its source identity")


@dataclass(frozen=True)
class RestatedH5FeatureVector:
    """一列固定 62-feature order 的 int64 值、scale 與明確 mask。

    此處只檢查 scale 為正整數並把它納入 hash；不驗證每個欄位的語意 scale
    或 normalization 是否與 frozen release 相容。
    """

    feature_order: tuple[str, ...]
    feature_order_sha256: str
    feature_registry_sha256: str
    values_i64: tuple[int | None, ...]
    scales: tuple[int, ...]
    observed_mask: tuple[bool, ...]
    values_sha256: str
    mask_sha256: str

    @property
    def dtype(self) -> str:
        return "int64"

    def __post_init__(self) -> None:
        if self.feature_order != DERIVED_H5_FEATURE_ORDER:
            raise ValueError("feature order does not match the frozen derived-h5 family")
        if self.feature_order_sha256 != FEATURE_ORDER_HASH:
            raise ValueError("feature_order_sha256 does not match derived-h5 identity")
        if self.feature_registry_sha256 != FEATURE_REGISTRY_HASH:
            raise ValueError("feature_registry_sha256 does not match derived-h5 identity")
        if not (
            len(self.values_i64)
            == len(self.scales)
            == len(self.observed_mask)
            == len(DERIVED_H5_FEATURE_ORDER)
        ):
            raise ValueError("feature values, scales, and mask must have exactly 62 slots")
        for index, (value, scale, observed) in enumerate(
            zip(self.values_i64, self.scales, self.observed_mask, strict=True)
        ):
            if isinstance(value, bool) or (value is not None and not isinstance(value, int)):
                raise TypeError(f"feature slot {index} must be an int64 value or None")
            if value is not None and not INT64_MIN <= value <= INT64_MAX:
                raise ValueError(f"feature slot {index} is outside signed int64 bounds")
            if isinstance(scale, bool) or not isinstance(scale, int) or scale <= 0:
                raise ValueError(f"feature slot {index} scale must be a positive integer")
            if not isinstance(observed, bool):
                raise TypeError(f"feature slot {index} mask must be boolean")
            if observed != (value is not None):
                raise ValueError(f"feature slot {index} value and mask disagree")
        _require_sha256(self.values_sha256, field_name="values_sha256")
        _require_sha256(self.mask_sha256, field_name="mask_sha256")
        if self.values_sha256 != feature_values_hash(
            values_i64=self.values_i64,
            scales=self.scales,
        ):
            raise ValueError("values_sha256 does not match feature values and scales")
        if self.mask_sha256 != feature_mask_hash(observed_mask=self.observed_mask):
            raise ValueError("mask_sha256 does not match observed_mask")


@dataclass(frozen=True)
class RestatedH5LabelEvidence:
    """h=5 標籤內容、自然成熟日與權威可得時間證據。"""

    horizon_days: int
    horizon_end_date: str
    authoritative_available_at: str
    label_value_sha256: str
    availability_evidence_sha256: str
    corporate_action_affected: bool

    def __post_init__(self) -> None:
        if self.horizon_days != HORIZON_DAYS:
            raise ValueError("derived-h5 research contract requires horizon 5")
        horizon_end = _iso_date(self.horizon_end_date, field_name="horizon_end_date")
        available_at = _aware_datetime(
            self.authoritative_available_at,
            field_name="authoritative_available_at",
        )
        if available_at.astimezone(TAIPEI_TIMEZONE).date() < horizon_end:
            raise ValueError("label available_at must not precede horizon_end_date")
        _require_sha256(self.label_value_sha256, field_name="label_value_sha256")
        _require_sha256(
            self.availability_evidence_sha256,
            field_name="availability_evidence_sha256",
        )
        if not isinstance(self.corporate_action_affected, bool):
            raise TypeError("corporate_action_affected must be boolean")


@dataclass(frozen=True)
class RestatedH5FoldIdentity:
    """新 dataset 所用 fold 的來源 identity 與時間範圍。"""

    fold_id: str
    fold_manifest_sha256: str
    train_start_date: str
    train_end_date: str
    test_start_date: str
    test_end_date: str
    purge_trading_days: int
    embargo_trading_days: int
    row_role: Literal["train", "test"]

    def __post_init__(self) -> None:
        if not self.fold_id.strip():
            raise ValueError("fold_id is required")
        _require_sha256(self.fold_manifest_sha256, field_name="fold_manifest_sha256")
        train_start = _iso_date(self.train_start_date, field_name="train_start_date")
        train_end = _iso_date(self.train_end_date, field_name="train_end_date")
        test_start = _iso_date(self.test_start_date, field_name="test_start_date")
        test_end = _iso_date(self.test_end_date, field_name="test_end_date")
        if not train_start <= train_end < test_start <= test_end:
            raise ValueError("fold dates must be chronological and non-overlapping")
        if self.purge_trading_days < 60 or self.embargo_trading_days < 5:
            raise ValueError("derived-h5 folds require at least a 60-day purge and 5-day embargo")
        if self.row_role not in ("train", "test"):
            raise ValueError("row_role must be train or test")

    def validate_row_date(self, decision_date: date) -> None:
        if self.row_role == "train":
            start = _iso_date(self.train_start_date, field_name="train_start_date")
            end = _iso_date(self.train_end_date, field_name="train_end_date")
        else:
            start = _iso_date(self.test_start_date, field_name="test_start_date")
            end = _iso_date(self.test_end_date, field_name="test_end_date")
        if not start <= decision_date <= end:
            raise ValueError("row decision date is outside its bound fold partition")


@dataclass(frozen=True)
class DerivedH5RestatedResearchRow:
    """一筆可供後續 research pipeline 檢查的修訂列，不是 fit 授權。"""

    row_id: str
    historical_decision_at: str
    revision_observed_at: str
    training_as_of: str
    source_identity: RestatedH5SourceIdentity
    features: RestatedH5FeatureVector
    label: RestatedH5LabelEvidence
    fold: RestatedH5FoldIdentity

    research_only: ClassVar[bool] = True
    historical_pit: ClassVar[bool] = False
    formal_oos: ClassVar[bool] = False
    promotion: ClassVar[bool] = False
    production: ClassVar[bool] = False

    def __post_init__(self) -> None:
        if not self.row_id.strip():
            raise ValueError("row_id is required")
        decision_at = _aware_datetime(
            self.historical_decision_at,
            field_name="historical_decision_at",
        )
        revision_observed_at = _aware_datetime(
            self.revision_observed_at,
            field_name="revision_observed_at",
        )
        training_as_of = _aware_datetime(
            self.training_as_of,
            field_name="training_as_of",
        )
        if revision_observed_at <= decision_at:
            raise ValueError("restated revision must be observed after historical decision")
        if training_as_of < revision_observed_at:
            raise ValueError("training_as_of must not precede revision_observed_at")
        if _iso_date(self.label.horizon_end_date, field_name="horizon_end_date") <= decision_at.date():
            raise ValueError("label horizon_end_date must follow historical_decision_at")
        label_available_at = _aware_datetime(
            self.label.authoritative_available_at,
            field_name="authoritative_available_at",
        )
        if training_as_of < label_available_at:
            raise ValueError("training_as_of must not precede authoritative label available_at")
        if self.label.corporate_action_affected:
            raise ValueError("corporate-action-affected labels must be excluded")
        source_hashes = dict(self.source_identity.source_hashes)
        if source_hashes["fold_manifest"] != self.fold.fold_manifest_sha256:
            raise ValueError("fold identity does not match source identity")
        self.fold.validate_row_date(decision_at.date())


@dataclass(frozen=True)
class DerivedH5ResearchCandidateEvidence:
    """呼叫端申報的資料集證據完整度；不讀回資料，也不授權訓練或 OOS。"""

    source_identity: RestatedH5SourceIdentity
    candidate_row_count: int
    rows_with_complete_62_features: int
    rows_with_feature_lineage: int
    rows_with_authoritative_label_availability: int
    rows_with_mature_labels_at_training_as_of: int
    corporate_action_exclusion_verified: bool
    full_window_lineage_verified: bool
    fold_manifest_verified: bool

    research_only: ClassVar[bool] = True
    historical_pit: ClassVar[bool] = False
    formal_oos: ClassVar[bool] = False
    promotion: ClassVar[bool] = False
    production: ClassVar[bool] = False

    def __post_init__(self) -> None:
        if (
            isinstance(self.candidate_row_count, bool)
            or not isinstance(self.candidate_row_count, int)
            or self.candidate_row_count <= 0
        ):
            raise ValueError("candidate_row_count must be a positive integer")
        for field_name, count in (
            ("rows_with_complete_62_features", self.rows_with_complete_62_features),
            ("rows_with_feature_lineage", self.rows_with_feature_lineage),
            (
                "rows_with_authoritative_label_availability",
                self.rows_with_authoritative_label_availability,
            ),
            (
                "rows_with_mature_labels_at_training_as_of",
                self.rows_with_mature_labels_at_training_as_of,
            ),
        ):
            if isinstance(count, bool) or not isinstance(count, int):
                raise TypeError(f"{field_name} must be an integer")
            if count < 0 or count > self.candidate_row_count:
                raise ValueError(f"{field_name} is outside the candidate row count")
        for field_name, value in (
            ("corporate_action_exclusion_verified", self.corporate_action_exclusion_verified),
            ("full_window_lineage_verified", self.full_window_lineage_verified),
            ("fold_manifest_verified", self.fold_manifest_verified),
        ):
            if not isinstance(value, bool):
                raise TypeError(f"{field_name} must be boolean")

    @property
    def evidence_status(self) -> Literal[
        "pending", "research_candidate_evidence_declared_complete_unverified"
    ]:
        counts_complete = all(
            count == self.candidate_row_count
            for count in (
                self.rows_with_complete_62_features,
                self.rows_with_feature_lineage,
                self.rows_with_authoritative_label_availability,
                self.rows_with_mature_labels_at_training_as_of,
            )
        )
        controls_complete = all(
            (
                self.corporate_action_exclusion_verified,
                self.full_window_lineage_verified,
                self.fold_manifest_verified,
            )
        )
        if counts_complete and controls_complete:
            return "research_candidate_evidence_declared_complete_unverified"
        return "pending"
