"""Immutable DTOs for research-session context."""

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Any, ClassVar, Literal, Mapping, Optional


RESEARCH_WORKFLOW_PATH = (
    "市場總覽",
    "產業／市場探索",
    "關鍵股研究",
    "觀察清單",
    "持倉覆盤",
)


def format_research_workflow_path() -> str:
    """回傳跨頁共用的唯讀研究路徑；不代表任何交易流程。"""

    return " → ".join(RESEARCH_WORKFLOW_PATH)


@dataclass(frozen=True, slots=True)
class ResearchRankContextDTO:
    """由已驗證原始排名建立的唯讀來源脈絡；不含可供重算的分數。"""

    rank_kind: Literal["original_stock_ranking"]
    period: Literal["day", "week"]
    direction: Literal["strong", "weak"]
    rank_snapshot_id: str
    source_hash: str
    ranking_root: str
    snapshot_root: str
    decision_date: str
    parent_snapshot_id: str
    parent_snapshot_hash: str
    parent_cohort_id: str
    selected_stock_code: str
    selected_rank: int
    comparison_date: str
    latest_date: str
    comparison_window_dates: tuple[str, ...]
    comparison_window_rule: str
    volume_reference_point_count: int
    declared_stock_codes: tuple[str, ...]
    eligible_stock_codes: tuple[str, ...]
    missing_rank_stock_codes: tuple[str, ...]
    research_universe_json: str
    research_universe_sha256: str
    method_name: str
    method_version: str
    method_contract_sha256: str
    engine_file_sha256: str
    engine_parameters_json: str
    engine_parameters_sha256: str
    source_schema_sha256: str
    selected_input_fingerprint_sha256: str
    filter_state: Literal["all", "match", "no_match", "unknown"] = "all"
    sort_key: str = "rank"
    descending: bool = False
    numeric_score_status: Literal["not_exposed_by_legacy_engine"] = (
        "not_exposed_by_legacy_engine"
    )

    _FIELD_NAMES: ClassVar[frozenset[str]] = frozenset(
        {
            "rank_kind", "period", "direction", "rank_snapshot_id", "source_hash",
            "ranking_root", "snapshot_root", "decision_date", "parent_snapshot_id",
            "parent_snapshot_hash", "parent_cohort_id", "selected_stock_code",
            "selected_rank", "comparison_date", "latest_date",
            "comparison_window_dates", "comparison_window_rule",
            "volume_reference_point_count", "declared_stock_codes",
            "eligible_stock_codes", "missing_rank_stock_codes",
            "research_universe_json", "research_universe_sha256", "method_name",
            "method_version", "method_contract_sha256", "engine_file_sha256",
            "engine_parameters_json", "engine_parameters_sha256",
            "source_schema_sha256", "selected_input_fingerprint_sha256",
            "filter_state", "sort_key", "descending", "numeric_score_status",
        }
    )
    _HASH_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "rank_snapshot_id", "source_hash", "parent_snapshot_id",
            "parent_snapshot_hash", "research_universe_sha256",
            "method_contract_sha256", "engine_file_sha256",
            "engine_parameters_sha256", "source_schema_sha256",
            "selected_input_fingerprint_sha256",
        }
    )

    def __post_init__(self) -> None:
        """在建立 DTO 時拒絕缺欄、錯型別、錯日期或股票脈絡。"""

        string_fields = (
            "rank_kind", "period", "direction", "rank_snapshot_id", "source_hash",
            "ranking_root", "snapshot_root", "decision_date", "parent_snapshot_id",
            "parent_snapshot_hash", "parent_cohort_id", "selected_stock_code",
            "comparison_date", "latest_date", "comparison_window_rule",
            "research_universe_json", "research_universe_sha256", "method_name",
            "method_version", "method_contract_sha256", "engine_file_sha256",
            "engine_parameters_json", "engine_parameters_sha256",
            "source_schema_sha256", "selected_input_fingerprint_sha256",
            "filter_state", "sort_key", "numeric_score_status",
        )
        for name in string_fields:
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"rank_context.{name} 必須是非空文字")
            object.__setattr__(self, name, value.strip())
        if self.rank_kind != "original_stock_ranking":
            raise ValueError("rank_context.rank_kind 不支援")
        if self.period not in {"day", "week"} or self.direction not in {"strong", "weak"}:
            raise ValueError("rank_context period/direction 不支援")
        for name in self._HASH_FIELDS:
            value = getattr(self, name)
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"rank_context.{name} 必須是小寫 SHA-256")
        if self.filter_state not in {"all", "match", "no_match", "unknown"}:
            raise ValueError("rank_context.filter_state 不支援")
        if self.numeric_score_status != "not_exposed_by_legacy_engine":
            raise ValueError("rank_context 不可推導或保存 legacy numeric score")
        for name in ("selected_rank", "volume_reference_point_count"):
            value = getattr(self, name)
            if type(value) is not int or value < (1 if name == "selected_rank" else 0):
                raise ValueError(f"rank_context.{name} 必須是非負整數")
        if not isinstance(self.descending, bool):
            raise ValueError("rank_context.descending 必須是布林值")
        for name in ("decision_date", "comparison_date", "latest_date"):
            value = getattr(self, name)
            try:
                parsed = date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(f"rank_context.{name} 必須是 ISO 日期") from exc
            if parsed.isoformat() != value:
                raise ValueError(f"rank_context.{name} 必須是 canonical ISO 日期")
        if self.comparison_date > self.latest_date or self.latest_date != self.decision_date:
            raise ValueError("rank_context comparison/latest 日期不符合決策日")
        for name in ("ranking_root", "snapshot_root"):
            value = getattr(self, name)
            resolved = str(Path(value).expanduser().resolve())
            object.__setattr__(self, name, resolved)
        for name in ("comparison_window_dates", "declared_stock_codes", "eligible_stock_codes", "missing_rank_stock_codes"):
            value = getattr(self, name)
            if not isinstance(value, tuple) or any(not isinstance(item, str) or not item.strip() for item in value):
                raise ValueError(f"rank_context.{name} 必須是非空文字 tuple")
            normalized = tuple(item.strip() for item in value)
            if len(normalized) != len(set(normalized)):
                raise ValueError(f"rank_context.{name} 不可重複")
            object.__setattr__(self, name, normalized)
        if (
            len(self.comparison_window_dates) < 2
            or self.comparison_window_dates[0] != self.comparison_date
            or self.comparison_window_dates[-1] != self.latest_date
        ):
            raise ValueError("rank_context comparison window 必須保留實際首末日期")
        for value in self.comparison_window_dates:
            try:
                parsed = date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("rank_context comparison window 含錯誤日期") from exc
            if parsed.isoformat() != value:
                raise ValueError("rank_context comparison window 必須使用 canonical ISO 日期")
        if any(
            left >= right
            for left, right in zip(
                self.comparison_window_dates, self.comparison_window_dates[1:]
            )
        ):
            raise ValueError("rank_context comparison window 日期必須嚴格遞增")
        if (
            not self.declared_stock_codes
            or self.selected_stock_code not in self.declared_stock_codes
            or self.selected_stock_code not in self.eligible_stock_codes
            or not self.eligible_stock_codes
            or len(self.declared_stock_codes) > 16
            or any(code not in self.declared_stock_codes for code in self.eligible_stock_codes)
            or tuple(code for code in self.declared_stock_codes if code not in self.eligible_stock_codes)
            != self.missing_rank_stock_codes
            or self.selected_rank > len(self.eligible_stock_codes)
            or self.eligible_stock_codes[self.selected_rank - 1] != self.selected_stock_code
        ):
            raise ValueError("rank_context selected stock/rank 與原始排名順序不一致")
        self._validate_canonical_hash_payload(
            self.research_universe_json, self.research_universe_sha256, "research_universe"
        )
        self._validate_canonical_hash_payload(
            self.engine_parameters_json, self.engine_parameters_sha256, "engine_parameters"
        )

    @staticmethod
    def _validate_canonical_hash_payload(payload: str, expected_hash: str, field_name: str) -> None:
        try:
            decoded = json.loads(payload)
            canonical = json.dumps(decoded, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"rank_context.{field_name} 必須是 canonical JSON") from exc
        if not isinstance(decoded, Mapping) or canonical != payload:
            raise ValueError(f"rank_context.{field_name} 必須是 canonical object JSON")
        if hashlib.sha256(payload.encode("utf-8")).hexdigest() != expected_hash:
            raise ValueError(f"rank_context.{field_name} SHA-256 不符")

    def to_dict(self) -> dict[str, Any]:
        """回傳固定欄位的 JSON-safe rank extension。"""

        payload: dict[str, Any] = {}
        for name in self._FIELD_NAMES:
            value = getattr(self, name)
            payload[name] = list(value) if isinstance(value, tuple) else value
        return {name: payload[name] for name in sorted(payload)}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ResearchRankContextDTO":
        """只接受完整、無未知欄位的 rank extension mapping。"""

        if not isinstance(value, Mapping) or set(value) != cls._FIELD_NAMES:
            raise ValueError("rank_context 欄位必須完全符合固定 schema")
        list_fields = {
            "comparison_window_dates", "declared_stock_codes", "eligible_stock_codes",
            "missing_rank_stock_codes",
        }
        for name in list_fields:
            if not isinstance(value[name], list) or any(not isinstance(item, str) for item in value[name]):
                raise ValueError(f"rank_context.{name} 必須是文字陣列")
        kwargs = dict(value)
        for name in list_fields:
            kwargs[name] = tuple(kwargs[name])
        return cls(**kwargs)


@dataclass(frozen=True)
class ResearchStockContextDTO:
    """單股研究下鑽所需的唯讀來源脈絡。

    這個 DTO 只攜帶識別、日期與來源／映射版本，不攜帶行情、DataFrame 或重新計算結果。
    `decision_date` 是原研究決策日，`data_date` 是該次研究實際使用的資料日；
    兩者刻意分開，避免跨頁時把目前行情誤認成歷史研究日期。
    """

    stock_code: str
    stock_name: str = ""
    decision_date: str = ""
    data_date: str = ""
    result_id: str = ""
    identity_status: str = ""
    source_snapshot_id: str = ""
    source_snapshot_hash: str = ""
    profile_id: str = ""
    profile_version: str = ""
    source_id: str = ""
    source_version: str = ""
    mapping_source_id: str = ""
    mapping_version: str = ""
    mapping_observed_date: str = ""
    source_kind: str = ""
    source_label: str = ""
    source_workspace: str = ""
    # 個股現況 ML scope 明確分流；不改寫 result_id 或既有 Advice identity。
    ml_scope_mode: str = ""
    # 每日市場研究列固定指向已發布快照，不由路由操作觸發計算。
    daily_snapshot_root: str = ""
    daily_snapshot_cohort_id: str = ""
    daily_snapshot_condition_keys: str = ""
    daily_snapshot_combine_mode: str = ""
    # 原始排名研究內容來自 immutable publisher manifest，不由目前排名或價格回填。
    rank_context: Optional[ResearchRankContextDTO] = None

    def __post_init__(self) -> None:
        for field_name in (
            "stock_code",
            "stock_name",
            "decision_date",
            "data_date",
            "result_id",
            "identity_status",
            "source_snapshot_id",
            "source_snapshot_hash",
            "profile_id",
            "profile_version",
            "source_id",
            "source_version",
            "mapping_source_id",
            "mapping_version",
            "mapping_observed_date",
            "source_kind",
            "source_label",
            "source_workspace",
            "ml_scope_mode",
            "daily_snapshot_root",
            "daily_snapshot_cohort_id",
            "daily_snapshot_condition_keys",
            "daily_snapshot_combine_mode",
        ):
            value = getattr(self, field_name)
            object.__setattr__(self, field_name, "" if value is None else str(value).strip())
        condition_keys = tuple(
            dict.fromkeys(
                part.strip()
                for part in self.daily_snapshot_condition_keys.split(",")
                if part.strip()
            )
        )
        object.__setattr__(
            self, "daily_snapshot_condition_keys", ",".join(condition_keys)
        )
        object.__setattr__(
            self,
            "daily_snapshot_combine_mode",
            self.daily_snapshot_combine_mode.upper(),
        )
        if self.ml_scope_mode not in {
            "",
            "current_stock_research",
            "selected_saved_decision",
        }:
            raise ValueError("ml_scope_mode 僅接受明確支援的個股研究範圍")
        rank_context = self.rank_context
        if rank_context is not None and not isinstance(rank_context, ResearchRankContextDTO):
            if not isinstance(rank_context, Mapping):
                raise ValueError("rank_context 必須是 typed DTO 或完整 mapping")
            rank_context = ResearchRankContextDTO.from_mapping(rank_context)
            object.__setattr__(self, "rank_context", rank_context)
        if rank_context is not None and (
            rank_context.selected_stock_code != self.stock_code
            or rank_context.decision_date != self.decision_date
            or self.source_kind not in {"original_stock_ranking", "original_stock_ranking_bookmark"}
        ):
            raise ValueError("rank_context stock/date/source_kind 與研究 context 不一致")

    @property
    def has_source(self) -> bool:
        """是否有可返回的來源頁面。"""

        return bool(self.source_workspace)


@dataclass(frozen=True)
class ResearchSessionSnapshotDTO:
    """Current lightweight research workflow context.

    This snapshot is intentionally small. It should describe what the user is
    currently researching, not own market data, DataFrames, widget state, or
    computed business results.
    """

    active_symbol: Optional[str] = None
    active_regime: Optional[str] = None
    active_profile: Optional[str] = None
    selected_watchlist_id: Optional[str] = None
    current_recommendation_run_id: Optional[str] = None
    # 單股研究上下文。保留舊欄位以相容既有頁面與測試。
    stock_context: Optional[ResearchStockContextDTO] = None
    active_stock_code: Optional[str] = None
    decision_date: Optional[str] = None
    data_date: Optional[str] = None
    result_id: Optional[str] = None
    identity_status: Optional[str] = None
    source_snapshot_id: Optional[str] = None
    source_snapshot_hash: Optional[str] = None
    profile_id: Optional[str] = None
    profile_version: Optional[str] = None
    source_id: Optional[str] = None
    source_version: Optional[str] = None
    mapping_source_id: Optional[str] = None
    mapping_version: Optional[str] = None
    mapping_observed_date: Optional[str] = None
    source_kind: Optional[str] = None
    source_label: Optional[str] = None
    source_workspace: Optional[str] = None
    ml_scope_mode: Optional[str] = None
    daily_snapshot_root: Optional[str] = None
    daily_snapshot_cohort_id: Optional[str] = None
    daily_snapshot_condition_keys: Optional[str] = None
    daily_snapshot_combine_mode: Optional[str] = None
