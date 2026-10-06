"""明示 cohort 的每日市場研究快照讀取與三態篩選。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal
from zoneinfo import ZoneInfo

from app_module.daily_market_method_contract import method_contracts_payload
from app_module.original_stock_ranking import (
    OriginalStockRankingRepository,
    VerifiedOriginalStockRanking,
)
from app_module.daily_market_research_universe import (
    ResearchUniverseContractError,
    ResearchUniverseSpec,
    load_research_universe_spec,
    validate_research_universe_manifest_binding,
)
from app_module.daily_market_feature_snapshot import (
    DAILY_MARKET_CONDITION_KEYS,
    daily_market_feature_input_fingerprint,
)
from app_module.daily_market_snapshot_repository import (
    DAILY_MARKET_SNAPSHOT_MAX_STOCKS,
    DAILY_MARKET_SNAPSHOT_MAX_MANIFEST_BYTES,
    DAILY_MARKET_SNAPSHOT_MAX_POINTER_BYTES,
    DAILY_MARKET_SNAPSHOT_POINTER_SCHEMA,
    DailyMarketSnapshotRepository,
    DailyMarketSnapshotVerificationError,
    VerifiedDailyMarketSnapshot,
    snapshot_manifest_relpath,
    validate_research_universe_binding,
)
from app_module.daily_market_snapshot_source import SQLiteDailyMarketSnapshotSource
from app_module.research_session.session_dtos import ResearchStockContextDTO
from app_module.sqlite_read_only import ReadOperationCancelled

if TYPE_CHECKING:
    from app_module.research_membership_history_index import MembershipHistoryIndexBuildResult, MembershipHistoryPage
    from app_module.research_membership_history_view import MembershipHistoryBrowsePage
    from app_module.research_membership_lifecycle_read_model import (
        CalendarSessionProvider, MembershipLifecycleReadModel,
    )
    from app_module.daily_market_snapshot_producer import DailyMarketSnapshotProductionResult


DAILY_MARKET_RESEARCH_SOURCE_KIND = "daily_market_research_snapshot"
DAILY_MARKET_RESEARCH_SOURCE_LABEL = "每日市場研究快照（研究 cohort）"
DAILY_MARKET_RESEARCH_SOURCE_WORKSPACE = "recommendation"
DAILY_MARKET_RESEARCH_SCOPE_LABEL = "明示研究 cohort；非全市場／非正式推薦"
DAILY_MARKET_RESEARCH_MAX_CONDITIONS = 2
_TAIPEI = ZoneInfo("Asia/Taipei")
_REASON_LABELS = {
    "insufficient_valid_ohlc_streak": "有效 OHLC 連續列不足以通過此均線暖機要求",
    "invalid_ohlc_row": "行情列 OHLC 無效，連續暖機資料在此中斷",
    "technical_date_mismatch": "最新技術指標資料日與行情日不一致",
    "technical_metric_date_mismatch": "均線資料日與行情或技術指標日期不一致",
    "technical_missing": "缺少技術指標資料",
    "technical_metric_missing": "缺少所需的均線欄位",
    "technical_metric_invalid": "均線值缺漏或不是有效正值",
    "duplicate_technical_metric": "同日均線欄位有重複值，無法判定",
    "duplicate_market_date": "來源行情同日有重複列，無法確認最新列",
    "invalid_market_date": "來源行情日期無法解析",
    "future_market_date": "來源行情日期晚於決策日",
    "no_price_rows": "找不到不晚於決策日的行情列",
    "latest_close_missing": "最新行情列缺少收盤價",
    "latest_close_invalid": "最新收盤價不是有效正值",
    "price_quality_not_observed": "最新收盤價不是已觀測來源",
    "price_source_identity_missing": "最新行情缺少來源身份",
    "technical_quality_not_observed": "技術指標不是已觀測來源",
    "technical_source_identity_missing": "均線缺少來源身份",
    "condition_inputs_unknown": "收盤價或均線輸入不足",
    "shared_daily_feature_projection_failed": "共用每日特徵驗證失敗",
    "snapshot_input_hash_mismatch": "目前來源已修訂，與快照保存版本不同",
    "snapshot_context_data_date_mismatch": "研究行情日與快照行情日不一致",
    "snapshot_context_decision_date_mismatch": "研究決策日與快照決策日不一致",
    "snapshot_context_incomplete": "研究上下文缺少快照來源身份",
    "decision_date_mismatch": "方法契約決策日與已驗證快照不一致",
    "method_contract_invalid": "方法契約欄位缺漏或不一致",
}

ResearchConditionState = Literal["match", "no_match", "unknown"]
ResearchConditionRelation = Literal["above", "below", "equal", "unknown"]
ResearchEligibility = Literal["eligible", "unknown"]
ResearchCombineMode = Literal["AND", "OR"]


class DailyMarketResearchCancelled(RuntimeError):
    """明示的每日快照產生工作收到取消要求。"""


@dataclass(frozen=True, slots=True)
class DailyMarketResearchConditionResult:
    """單一既有 close／均線關係與其三態理由。"""

    key: str
    state: ResearchConditionState
    relation: ResearchConditionRelation
    reason: str
    method_id: str | None = None
    family: str | None = None
    version: str | None = None
    parameters: Mapping[str, int | str] | None = None
    decision_date: str | None = None
    eligibility: ResearchEligibility | None = None
    unknown_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "key": self.key,
            "state": self.state,
            "relation": self.relation,
            "reason": self.reason,
        }
        if any(
            value is not None
            for value in (
                self.method_id,
                self.family,
                self.version,
                self.parameters,
                self.decision_date,
                self.eligibility,
                self.unknown_reason,
            )
        ):
            result.update(
                {
                    "method_id": self.method_id,
                    "family": self.family,
                    "version": self.version,
                    "parameters": dict(self.parameters or {}),
                    "decision_date": self.decision_date,
                    "eligibility": self.eligibility,
                    "unknown_reason": self.unknown_reason,
                }
            )
        return result


@dataclass(frozen=True, slots=True)
class DailyMarketResearchFilterEvaluation:
    """一列的條件細節、Kleene 組合結果與白話理由。"""

    condition_keys: tuple[str, ...]
    combine_mode: ResearchCombineMode
    conditions: tuple[DailyMarketResearchConditionResult, ...]
    combined_state: ResearchConditionState
    why: tuple[str, ...]
    why_not: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DailyMarketResearchScreenRow:
    """可由選股列表傳至個股研究的不可變列。"""

    stock_code: str
    cohort_id: str
    decision_date: str
    data_date: str
    condition_keys: tuple[str, ...]
    combine_mode: ResearchCombineMode
    conditions: tuple[DailyMarketResearchConditionResult, ...]
    combined_state: ResearchConditionState
    why: tuple[str, ...]
    why_not: tuple[str, ...]
    source_snapshot_id: str
    source_snapshot_hash: str
    snapshot_identity_sha256: str
    input_fingerprint_sha256: str
    snapshot_root: str
    completeness: str
    research_universe: Mapping[str, Any] | None = None
    research_universe_membership: str = "legacy_declared_research_only"
    original_rank: int | None = None
    original_rank_unknown_reason: str = "original_rank_immutable_source_missing"
    research_scope_label: str = DAILY_MARKET_RESEARCH_SCOPE_LABEL
    research_only: bool = True
    historical_pit_eligible: bool = False

    def to_dict(self) -> dict[str, Any]:
        """回傳供列表呈現的唯讀欄位，不另計算金融數值。"""

        return {
            "stock_code": self.stock_code,
            "cohort_id": self.cohort_id,
            "decision_date": self.decision_date,
            "data_date": self.data_date,
            "condition_keys": list(self.condition_keys),
            "combine_mode": self.combine_mode,
            "conditions": [item.to_dict() for item in self.conditions],
            "combined_state": self.combined_state,
            "why": list(self.why),
            "why_not": list(self.why_not),
            "source_snapshot_id": self.source_snapshot_id,
            "source_snapshot_hash": self.source_snapshot_hash,
            "snapshot_identity_sha256": self.snapshot_identity_sha256,
            "input_fingerprint_sha256": self.input_fingerprint_sha256,
            "snapshot_root": self.snapshot_root,
            "completeness": self.completeness,
            "research_universe": (
                dict(self.research_universe)
                if self.research_universe is not None
                else None
            ),
            "research_universe_membership": self.research_universe_membership,
            "original_rank": self.original_rank,
            "original_rank_unknown_reason": self.original_rank_unknown_reason,
            "research_scope_label": self.research_scope_label,
            "research_only": self.research_only,
            "historical_pit_eligible": self.historical_pit_eligible,
        }


def evaluate_daily_market_conditions(
    payload_conditions: Mapping[str, Any],
    condition_keys: Sequence[str],
    combine_mode: str,
    *,
    expected_decision_date: date | None = None,
) -> DailyMarketResearchFilterEvaluation:
    """以三態邏輯組合已發布的既有觀察條件。"""

    keys = _normalize_condition_keys(condition_keys)
    mode = _normalize_combine_mode(combine_mode)
    if expected_decision_date is not None and (
        isinstance(expected_decision_date, datetime)
        or not isinstance(expected_decision_date, date)
    ):
        raise ValueError("expected_decision_date 必須是 date")
    results = tuple(
        _condition_result(
            payload_conditions.get(key), key, expected_decision_date
        )
        for key in keys
    )
    states = tuple(item.state for item in results)
    if mode == "AND":
        combined: ResearchConditionState = (
            "no_match"
            if "no_match" in states
            else "match"
            if states and all(state == "match" for state in states)
            else "unknown"
        )
    else:
        combined = (
            "match"
            if "match" in states
            else "no_match"
            if states and all(state == "no_match" for state in states)
            else "unknown"
        )
    why = tuple(_condition_explanation(item) for item in results if item.state == "match")
    why_not = tuple(
        _condition_explanation(item)
        for item in results
        if item.state in {"no_match", "unknown"}
    )
    return DailyMarketResearchFilterEvaluation(
        condition_keys=keys,
        combine_mode=mode,
        conditions=results,
        combined_state=combined,
        why=why,
        why_not=why_not,
    )


class DailyMarketResearchScreenerService:
    """按需產生、驗證並唯讀篩選明示小型研究 cohort。"""

    def __init__(
        self,
        config: object,
        snapshot_root: str | Path | None = None,
        universe_config_path: str | Path | None = None,
        *,
        original_ranking_root: str | Path | None = None,
        membership_session_provider: CalendarSessionProvider | None = None,
        history_index_root: str | Path | None = None,
    ) -> None:
        raw_db_path = getattr(config, "db_file", None) or getattr(
            config, "sqlite_db_file", None
        )
        if raw_db_path is None or not str(raw_db_path).strip():
            raise ValueError("研究選股器需要明示既有 SQLite db_file")
        self.config = config
        self._membership_session_provider = membership_session_provider
        self._history_index_root = Path(history_index_root).expanduser().resolve() if history_index_root is not None else None
        self.db_path = Path(raw_db_path).expanduser().resolve()
        # 預設使用 repository 隔離的研究輸出，不沿用正式資料根目錄。
        default_root = (
            Path(__file__).resolve().parents[1]
            / "output"
            / "research_snapshots"
            / "daily_market"
        )
        self.snapshot_root = Path(snapshot_root or default_root).expanduser().resolve()
        self.repository = DailyMarketSnapshotRepository(self.snapshot_root)
        self.original_ranking_repository = OriginalStockRankingRepository(
            self.snapshot_root,
            ranking_root=original_ranking_root,
        )
        self.research_universe_spec = (
            load_research_universe_spec(universe_config_path)
            if universe_config_path is not None
            else None
        )

    @property
    def history_index_root(self) -> Path:
        """派生索引預設在來源旁；唯讀查詢不建立任何索引檔。"""
        from app_module.research_membership_history_index import default_membership_history_cache_root
        return self._history_index_root or default_membership_history_cache_root(self.snapshot_root)

    def rebuild_membership_history_index(
        self, *, cancel_callback: Callable[[], bool] | None = None,
    ) -> MembershipHistoryIndexBuildResult:
        """明示重建派生索引；既有源檔和舊 generation 保留。"""
        from app_module.research_membership_history_index import rebuild_membership_history_index, MembershipHistoryIndexError
        try:
            return rebuild_membership_history_index(self.snapshot_root, self.history_index_root, cancel_check=cancel_callback)
        except MembershipHistoryIndexError as exc:
            if exc.reason == "cancelled":
                raise DailyMarketResearchCancelled(str(exc)) from exc
            raise

    def rollback_membership_history_index(self, generation_id: str) -> MembershipHistoryIndexBuildResult:
        """只重新啟用本索引根內已完成、相容且核驗的 generation。"""
        from app_module.research_membership_history_index import rollback_membership_history_index
        return rollback_membership_history_index(self.snapshot_root, self.history_index_root, generation_id=generation_id)

    def _read_membership_index_page(
        self, snapshot: VerifiedDailyMarketSnapshot, *, cursor: str | None,
        page_size: int, cancel_callback: Callable[[], bool] | None,
    ) -> MembershipHistoryPage:
        from app_module.research_membership_history_index import read_membership_history_page, MembershipHistoryIndexError
        try:
            return read_membership_history_page(
                self.snapshot_root, self.history_index_root, cohort=snapshot.cohort_id,
                as_of=datetime.fromisoformat(str(snapshot.manifest["published_at"])),
                current_pin=snapshot.manifest_sha256, date_to=snapshot.decision_date,
                page_size=page_size, cursor=cursor, cancel_check=cancel_callback,
            )
        except MembershipHistoryIndexError as exc:
            if exc.reason == "cancelled":
                raise DailyMarketResearchCancelled(str(exc)) from exc
            raise

    def read_membership_history_page(
        self, snapshot: VerifiedDailyMarketSnapshot, *, cursor: str | None = None,
        page_size: int = 32, condition_keys: tuple[str, ...] = ("close_above_ma20", "close_above_ma60"),
        combine_mode: str = "AND", stock_code: str | None = None,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> MembershipHistoryBrowsePage:
        """有界核驗一頁，固定原 anchor；不改當期名單或原收藏。"""
        from app_module.research_membership_history_view import MembershipHistoryBrowsePage, project_membership_history_rows
        from app_module.research_membership_lifecycle_read_model import load_membership_history_page_snapshots
        candidates = self.filter_rows(snapshot, condition_keys, combine_mode)
        chosen = stock_code or (candidates[0].stock_code if candidates else "")
        if not any(row.stock_code == chosen for row in candidates):
            raise ValueError("歷史股票不在固定當期母體")
        page = self._read_membership_index_page(snapshot, cursor=cursor, page_size=page_size, cancel_callback=cancel_callback)
        snapshots = load_membership_history_page_snapshots(self.repository, snapshot, page, cancel_callback=cancel_callback)
        return MembershipHistoryBrowsePage(
            snapshot.manifest_sha256, snapshot.manifest_identity_sha256, snapshot.cohort_id,
            tuple(sorted(condition_keys)), combine_mode.strip().upper(), chosen,
            page.generation_id, page.source_fingerprint, page.next_cursor, page.has_more,
            project_membership_history_rows(snapshots, stock_code=chosen, condition_keys=condition_keys, combine_mode=combine_mode),
        )

    def read_membership_lifecycle(
        self,
        snapshot: VerifiedDailyMarketSnapshot,
        condition_keys: tuple[str, ...],
        combine_mode: str,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> MembershipLifecycleReadModel:
        """唯讀比較既有快照，沒有 producer 或隱性歷程寫入。"""
        from app_module.research_membership_lifecycle_read_model import (
            create_offline_official_calendar_session_provider,
            read_membership_lifecycle,
        )
        provider = self._membership_session_provider
        if provider is None:
            cache = (getattr(self.config, "official_calendar_cache_path", None)
                     or Path(__file__).resolve().parents[1]
                     / "output/paper_execution_eod_replay/calendar_cache")
            provider = create_offline_official_calendar_session_provider(
                cache, temporary_closure_path=getattr(self.config, "temporary_closure_path", None),
            )
        page = (self._read_membership_index_page(snapshot, cursor=None, page_size=31, cancel_callback=cancel_callback)
                if self.history_index_root.exists() else None)
        return read_membership_lifecycle(
            self.repository, snapshot, condition_keys, combine_mode,
            cancel_callback=cancel_callback, session_provider=provider, history_page=page,
        )

    def read_original_ranking(
        self,
        snapshot: VerifiedDailyMarketSnapshot,
        *,
        period: Literal["day", "week"],
        direction: Literal["strong", "weak"],
    ) -> VerifiedOriginalStockRanking:
        """讀取綁定已核驗 feature snapshot 的不可變原生排名。"""

        return self.original_ranking_repository.read(
            snapshot,
            db_path=self.db_path,
            period=period,
            direction=direction,
        )

    def produce_snapshot(
        self,
        stock_codes: Sequence[str],
        decision_cutoff: datetime,
        cohort_id: str,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> DailyMarketSnapshotProductionResult:
        """只在呼叫端明確要求時讀取來源並啟動有界 producer。"""

        codes = _normalize_stock_codes(stock_codes)
        if not codes:
            raise ValueError("stock_codes 必須明示至少一檔股票")
        if len(codes) > DAILY_MARKET_SNAPSHOT_MAX_STOCKS:
            raise ValueError(
                f"研究 cohort 最多 {_MAX_STOCKS_TEXT} 檔；不會自動截斷母體"
            )
        cutoff = _normalize_cutoff(decision_cutoff)
        logical_cohort = str(cohort_id).strip()
        if not logical_cohort:
            raise ValueError("cohort_id 不可為空")
        # 只有明示產生時才載入 writer 契約；唯讀列表與篩選不載入 producer。
        universe_spec = self.research_universe_spec
        if universe_spec is not None:
            if universe_spec.as_of_date != cutoff.date():
                raise ValueError("research_universe as_of_date must match decision_cutoff")
            if logical_cohort != universe_spec.universe_id:
                raise ValueError("cohort_id must match configured universe_id")
            if tuple(sorted(codes)) != universe_spec.included_stock_codes:
                raise ValueError("stock_codes must exactly match configured included members")
            universe_spec.assert_source_stable()
        from app_module.daily_market_snapshot_producer import (
            DailyMarketSnapshotInput,
            DailyMarketSnapshotProducer,
        )

        cancel_seen = False

        def is_cancelled() -> bool:
            nonlocal cancel_seen
            if cancel_callback is not None and cancel_callback():
                cancel_seen = True
                return True
            return False

        source = SQLiteDailyMarketSnapshotSource(
            self.db_path,
            cutoff.date(),
            cancel_callback=is_cancelled if cancel_callback is not None else None,
        )
        with source:
            def source_loader(
                stock_code: str, requested_date: date
            ) -> DailyMarketSnapshotInput:
                if is_cancelled():
                    raise DailyMarketResearchCancelled("使用者已取消每日快照產生。")
                if requested_date != cutoff.date():
                    raise ValueError("producer 要求的資料日與決策截止日不符")
                return source.load_input(stock_code)

            def before_publish() -> None:
                if is_cancelled():
                    raise DailyMarketResearchCancelled("使用者已取消每日快照產生。")
                source.validate_source_stable()

            result = DailyMarketSnapshotProducer(self.snapshot_root).produce(
                cohort_id=logical_cohort,
                decision_cutoff=cutoff,
                stock_codes=codes,
                source_loader=source_loader,
                before_publish=before_publish,
                research_universe=universe_spec,
            )
        if cancel_seen:
            raise DailyMarketResearchCancelled("使用者已取消每日快照產生；未回報為完成。")
        return result

    def read_snapshot(
        self,
        cohort_id: str,
        decision_date: date,
        manifest_sha256: str | None = None,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> VerifiedDailyMarketSnapshot:
        """讀取 pinned/latest manifest，並確認其來源仍與當前資料一致。"""

        cohort = str(cohort_id).strip()
        if not cohort:
            raise ValueError("cohort_id 不可為空")
        if isinstance(decision_date, datetime) or not isinstance(decision_date, date):
            raise ValueError("decision_date 必須是 date")
        initial = (
            self.repository.load_manifest(
                manifest_sha256,
                cohort,
                decision_date,
            )
            if manifest_sha256
            else self.repository.load_latest(cohort, decision_date)
        )
        if self.research_universe_spec is not None:
            binding = initial.manifest.get("research_universe")
            if not isinstance(binding, Mapping):
                raise DailyMarketSnapshotVerificationError(
                    "snapshot_research_universe_config_mismatch",
                    "configured read requires a manifest with the same research_universe",
                )
            try:
                self.research_universe_spec.assert_source_stable()
                validate_research_universe_manifest_binding(
                    self.research_universe_spec, binding
                )
                validate_research_universe_binding(
                    binding,
                    decision_date=decision_date,
                    cohort_id=cohort,
                    declared_stock_codes=initial.manifest.get(
                        "declared_stock_codes", ()
                    ),
                )
            except ResearchUniverseContractError as exc:
                raise DailyMarketSnapshotVerificationError(
                    "snapshot_research_universe_config_mismatch", str(exc)
                ) from exc
        raw_codes = initial.manifest.get("declared_stock_codes", ())
        if not isinstance(raw_codes, Sequence) or isinstance(raw_codes, (str, bytes)):
            raise DailyMarketSnapshotVerificationError(
                "snapshot_cohort_invalid", "manifest 缺少明示研究股票分母"
            )
        codes = tuple(str(code) for code in raw_codes)
        if not codes or len(codes) > DAILY_MARKET_SNAPSHOT_MAX_STOCKS:
            raise DailyMarketSnapshotVerificationError(
                "snapshot_cohort_invalid", "manifest cohort 筆數不符合有界讀取限制"
            )
        artifact_codes = tuple(sorted(initial.stock_snapshots))
        if not artifact_codes:
            raise DailyMarketSnapshotVerificationError(
                "snapshot_cohort_empty", "快照沒有可供研究的逐股 artifact"
            )

        expected_hashes: dict[str, str] = {}
        cancel_seen = False

        def is_cancelled() -> bool:
            nonlocal cancel_seen
            if cancel_callback is not None and cancel_callback():
                cancel_seen = True
                return True
            return False

        try:
            with SQLiteDailyMarketSnapshotSource(
                self.db_path,
                decision_date,
                cancel_callback=is_cancelled if cancel_callback is not None else None,
            ) as source:
                for code in artifact_codes:
                    if is_cancelled():
                        raise DailyMarketResearchCancelled("使用者已取消快照重讀。")
                    price_points, technical, scope_identity, _source_refs = source.load(code)
                    expected_hashes[code] = daily_market_feature_input_fingerprint(
                        stock_code=code,
                        decision_date=decision_date,
                        scope_identity=scope_identity,
                        price_points=price_points,
                        technical=technical,
                    )
                source.validate_source_stable()
        except (DailyMarketResearchCancelled, ReadOperationCancelled):
            raise DailyMarketResearchCancelled("使用者已取消快照重讀；未回報為完成。")
        except Exception as exc:
            if cancel_seen:
                raise DailyMarketResearchCancelled(
                    "使用者已取消快照重讀；未回報為完成。"
                ) from exc
            raise DailyMarketSnapshotVerificationError(
                "snapshot_current_source_unavailable",
                f"目前唯讀來源無法核對快照版本，請檢查資料來源後重新載入：{type(exc).__name__}: {exc}",
            ) from exc

        if manifest_sha256:
            verified = self.repository.load_manifest(
                manifest_sha256,
                cohort,
                decision_date,
                expected_stock_codes=codes,
                expected_input_hashes=expected_hashes,
            )
        else:
            current = self.repository.load_latest(
                cohort,
                decision_date,
                expected_stock_codes=codes,
                expected_input_hashes=expected_hashes,
            )
            if current.manifest_sha256 != initial.manifest_sha256:
                raise DailyMarketSnapshotVerificationError(
                    "snapshot_pointer_changed_during_read",
                    "讀取期間研究快照已更新，請重新載入後再篩選。",
                )
            verified = current
        if cancel_callback is not None and cancel_callback():
            raise DailyMarketResearchCancelled("使用者已取消快照重讀；未回報為完成。")
        return verified

    def read_latest(
        self,
        cohort_id: str,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> VerifiedDailyMarketSnapshot:
        """由 bounded latest pointer 取得日期後，唯讀重驗當前版本。"""

        if cancel_callback is not None and cancel_callback():
            raise DailyMarketResearchCancelled("使用者已取消快照重讀。")
        _pointer_bytes, pointer = self.repository._read_json_file(
            Path("latest.json"),
            limit=DAILY_MARKET_SNAPSHOT_MAX_POINTER_BYTES,
            missing_code="snapshot_pointer_missing",
            invalid_code="snapshot_pointer_invalid",
        )
        if (
            pointer.get("schema_version") != DAILY_MARKET_SNAPSHOT_POINTER_SCHEMA
            or set(pointer) != {"schema_version", "manifest_sha256"}
        ):
            raise DailyMarketSnapshotVerificationError(
                "snapshot_pointer_schema_mismatch", "latest pointer schema 不相容"
            )
        manifest_sha = str(pointer.get("manifest_sha256") or "")
        _raw_manifest, manifest = self.repository._read_json_file(
            Path(snapshot_manifest_relpath(manifest_sha)),
            limit=DAILY_MARKET_SNAPSHOT_MAX_MANIFEST_BYTES,
            missing_code="snapshot_manifest_missing",
            invalid_code="snapshot_manifest_invalid",
        )
        if hashlib.sha256(_raw_manifest).hexdigest() != manifest_sha:
            raise DailyMarketSnapshotVerificationError(
                "snapshot_manifest_hash_mismatch", "latest manifest 內容與 pin 不符"
            )
        raw_date = manifest.get("decision_date")
        try:
            decision_date = date.fromisoformat(str(raw_date))
        except (TypeError, ValueError) as exc:
            raise DailyMarketSnapshotVerificationError(
                "snapshot_decision_date_invalid", "latest manifest 決策日期無法解析"
            ) from exc
        if decision_date.isoformat() != raw_date:
            raise DailyMarketSnapshotVerificationError(
                "snapshot_decision_date_invalid", "latest manifest 決策日期格式不符"
            )
        return self.read_snapshot(
            cohort_id,
            decision_date,
            cancel_callback=cancel_callback,
        )

    def filter_rows(
        self,
        snapshot: VerifiedDailyMarketSnapshot,
        condition_keys: Sequence[str],
        combine_mode: str = "AND",
    ) -> tuple[DailyMarketResearchScreenRow, ...]:
        """只篩選已驗證快照，不讀來源、不建立或更新快照。"""

        if not isinstance(snapshot, VerifiedDailyMarketSnapshot):
            raise TypeError("snapshot 必須是 read_snapshot 回傳的已驗證快照")
        keys = _normalize_condition_keys(condition_keys)
        mode = _normalize_combine_mode(combine_mode)
        if len(snapshot.stock_snapshots) > DAILY_MARKET_SNAPSHOT_MAX_STOCKS:
            raise ValueError("snapshot cohort 超出最多 16 檔的產品限制")
        rows: list[DailyMarketResearchScreenRow] = []
        raw_universe = snapshot.manifest.get("research_universe")
        research_universe = (
            dict(raw_universe) if isinstance(raw_universe, Mapping) else None
        )
        for code in sorted(snapshot.stock_snapshots):
            payload = snapshot.stock_snapshots[code]
            raw_conditions = payload.get("conditions")
            conditions = raw_conditions if isinstance(raw_conditions, Mapping) else {}
            evaluation = evaluate_daily_market_conditions(
                conditions,
                keys,
                mode,
                expected_decision_date=snapshot.decision_date,
            )
            rows.append(
                DailyMarketResearchScreenRow(
                    stock_code=code,
                    cohort_id=snapshot.cohort_id,
                    decision_date=snapshot.decision_date.isoformat(),
                    data_date=str(payload.get("market_date") or ""),
                    condition_keys=evaluation.condition_keys,
                    combine_mode=evaluation.combine_mode,
                    conditions=evaluation.conditions,
                    combined_state=evaluation.combined_state,
                    why=evaluation.why,
                    why_not=evaluation.why_not,
                    source_snapshot_id=snapshot.manifest_identity_sha256,
                    source_snapshot_hash=snapshot.manifest_sha256,
                    snapshot_identity_sha256=str(
                        payload.get("snapshot_identity_sha256") or ""
                    ),
                    input_fingerprint_sha256=str(
                        payload.get("input_fingerprint_sha256") or ""
                    ),
                    snapshot_root=str(self.snapshot_root),
                    completeness=snapshot.completeness,
                    research_universe=research_universe,
                    research_universe_membership=(
                        "included_for_review"
                        if research_universe is not None
                        else "legacy_declared_research_only"
                    ),
                )
            )
        return tuple(rows)

    def context_for_stock(
        self,
        row: DailyMarketResearchScreenRow,
        *,
        stock_name: str = "",
    ) -> ResearchStockContextDTO:
        """將篩選列轉成同一 pinned 快照的個股研究脈絡。"""

        if not isinstance(row, DailyMarketResearchScreenRow):
            raise TypeError("row 必須是 DailyMarketResearchScreenRow")
        if Path(row.snapshot_root).expanduser().resolve() != self.snapshot_root:
            raise ValueError("研究列的 snapshot root 與目前服務不符")
        return ResearchStockContextDTO(
            stock_code=row.stock_code,
            stock_name=stock_name,
            decision_date=row.decision_date,
            data_date=row.data_date,
            result_id="",
            source_snapshot_id=row.source_snapshot_id,
            source_snapshot_hash=row.source_snapshot_hash,
            source_kind=DAILY_MARKET_RESEARCH_SOURCE_KIND,
            source_label=DAILY_MARKET_RESEARCH_SOURCE_LABEL,
            source_workspace=DAILY_MARKET_RESEARCH_SOURCE_WORKSPACE,
            daily_snapshot_root=str(self.snapshot_root),
            daily_snapshot_cohort_id=row.cohort_id,
            daily_snapshot_condition_keys=",".join(row.condition_keys),
            daily_snapshot_combine_mode=row.combine_mode,
        )


_MAX_STOCKS_TEXT = str(DAILY_MARKET_SNAPSHOT_MAX_STOCKS)


def _normalize_cutoff(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("decision_cutoff 必須是 timezone-aware datetime")
    return value.astimezone(_TAIPEI)


def _normalize_stock_codes(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError("stock_codes 必須是明示股票代碼序列")
    codes: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise TypeError("stock_codes 必須全部是字串")
        code = value.strip()
        if not code or not code.isalnum() or len(code) > 16:
            raise ValueError("股票代碼必須是 1 至 16 個英數字元")
        if code in seen:
            raise ValueError("stock_codes 不可重複；不會靜默去重母體")
        seen.add(code)
        codes.append(code)
    return tuple(codes)


def _normalize_condition_keys(
    values: Sequence[str],
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError("condition_keys 必須是條件代碼序列")
    keys: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise TypeError("condition_keys 必須全部是字串")
        key = value.strip()
        if key not in DAILY_MARKET_CONDITION_KEYS:
            raise ValueError(f"不支援的既有研究條件：{key!r}")
        if key in seen:
            raise ValueError(f"condition_keys 不可重複：{key}")
        seen.add(key)
        keys.append(key)
    if not keys or len(keys) > DAILY_MARKET_RESEARCH_MAX_CONDITIONS:
        raise ValueError("請選擇一至兩項既有 close／均線觀察條件")
    return tuple(keys)


def _normalize_combine_mode(value: str) -> ResearchCombineMode:
    if not isinstance(value, str):
        raise TypeError("combine_mode 必須是 AND 或 OR")
    mode = value.strip().upper()
    if mode not in {"AND", "OR"}:
        raise ValueError("combine_mode 僅接受 AND 或 OR")
    return mode  # type: ignore[return-value]


def _condition_result(
    raw: Any,
    key: str,
    expected_decision_date: date | None = None,
) -> DailyMarketResearchConditionResult:
    expected = {
        "match": "above",
        "no_match": {"below", "equal"},
        "unknown": "unknown",
    }
    label = "MA20" if key.endswith("ma20") else "MA60"
    if not isinstance(raw, Mapping):
        return DailyMarketResearchConditionResult(
            key=key,
            state="unknown",
            relation="unknown",
            reason=f"快照未提供 {label} 的條件觀察。",
        )
    method_metadata = _read_condition_method_metadata(
        raw,
        key,
        expected_decision_date,
    )
    raw_state = str(raw.get("state") or "")
    raw_relation = str(raw.get("relation") or "")
    if raw_state not in {"match", "no_match", "unknown"}:
        raw_state = "unknown"
    if raw_relation not in {"above", "below", "equal", "unknown"}:
        raw_relation = "unknown"
    if raw_state != "unknown":
        expected_relation = expected[raw_state]
        valid = (
            raw_relation == expected_relation
            if isinstance(expected_relation, str)
            else raw_relation in expected_relation
        )
        if not valid:
            return DailyMarketResearchConditionResult(
                key=key,
                state="unknown",
                relation="unknown",
                reason=f"{label} 的狀態與相對位置不一致；拒絕推定符合。",
                **method_metadata,
            )
    if method_metadata.get("eligibility") == "unknown":
        raw_state = "unknown"
        raw_relation = "unknown"
    raw_reason = str(raw.get("reason") or "").strip()
    reason = _localized_reason(raw_reason)
    if method_metadata.get("eligibility") == "unknown":
        binding_reason = str(method_metadata.get("unknown_reason") or "").strip()
        remaining_reasons = [
            code for code in binding_reason.split("|") if code and code != raw_reason
        ]
        binding_label = _localized_reason("|".join(remaining_reasons))
        reason = (
            f"{reason}；{binding_label}"
            if reason and binding_label
            else binding_label or reason
        )
    detail = str(raw.get("detail") or "").strip()
    if detail:
        reason = f"{reason}；{detail}" if reason else detail
    if raw_state == "unknown" and not reason:
        reason = f"{label} 的既有觀察值未知。"
    return DailyMarketResearchConditionResult(
        key=key,
        state=raw_state,  # type: ignore[arg-type]
        relation=raw_relation,  # type: ignore[arg-type]
        reason=reason,
        **method_metadata,
    )


def _read_condition_method_metadata(
    raw: Mapping[str, Any],
    key: str,
    expected_decision_date: date | None,
) -> dict[str, Any]:
    """保留 verified payload 的方法綁定；舊 minimal payload 維持原形。"""

    metadata_keys = (
        "method_id",
        "family",
        "version",
        "parameters",
        "decision_date",
        "eligibility",
        "unknown_reason",
    )
    if not any(name in raw for name in metadata_keys):
        return {}

    expected = method_contracts_payload().get(key)
    raw_parameters = raw.get("parameters")
    parameters = (
        dict(raw_parameters)
        if isinstance(raw_parameters, Mapping)
        and all(
            isinstance(name, str)
            and isinstance(value, (int, str))
            and not isinstance(value, bool)
            for name, value in raw_parameters.items()
        )
        else None
    )
    raw_date = raw.get("decision_date")
    decision_date = raw_date if isinstance(raw_date, str) else None
    raw_eligibility = raw.get("eligibility")
    eligibility: ResearchEligibility | None = (
        "eligible"
        if raw_eligibility == "eligible"
        else "unknown"
        if raw_eligibility == "unknown"
        else None
    )
    raw_unknown_reason = raw.get("unknown_reason")
    unknown_reason = (
        raw_unknown_reason if isinstance(raw_unknown_reason, str) else None
    )
    method_id = raw.get("method_id") if isinstance(raw.get("method_id"), str) else None
    family = raw.get("family") if isinstance(raw.get("family"), str) else None
    version = raw.get("version") if isinstance(raw.get("version"), str) else None

    valid_date = False
    if decision_date is not None:
        try:
            parsed_date = date.fromisoformat(decision_date)
            valid_date = parsed_date.isoformat() == decision_date
        except ValueError:
            valid_date = False
    date_mismatch = (
        expected_decision_date is not None
        and decision_date != expected_decision_date.isoformat()
    )
    valid_contract = (
        isinstance(expected, Mapping)
        and method_id == expected.get("method_id")
        and family == expected.get("family")
        and version == expected.get("version")
        and parameters == expected.get("parameters")
        and valid_date
        and eligibility in {"eligible", "unknown"}
        and unknown_reason is not None
        and (
            (eligibility == "eligible" and unknown_reason == "")
            or (eligibility == "unknown" and bool(unknown_reason))
        )
    )

    metadata_unknown_reason = unknown_reason or ""
    if date_mismatch:
        metadata_unknown_reason = _join_unknown_reasons(
            "decision_date_mismatch",
            metadata_unknown_reason,
        )
        eligibility = "unknown"
    elif not valid_contract:
        metadata_unknown_reason = _join_unknown_reasons(
            "method_contract_invalid",
            metadata_unknown_reason,
        )
        eligibility = "unknown"
    elif eligibility == "unknown" and not unknown_reason:
        metadata_unknown_reason = "condition_inputs_unknown"

    frozen_parameters = (
        MappingProxyType(parameters) if parameters is not None else None
    )
    return {
        "method_id": method_id,
        "family": family,
        "version": version,
        "parameters": frozen_parameters,
        "decision_date": decision_date,
        "eligibility": eligibility,
        "unknown_reason": metadata_unknown_reason,
    }


def _join_unknown_reasons(*values: str) -> str:
    reasons: list[str] = []
    for value in values:
        for reason in value.split("|"):
            normalized = reason.strip()
            if normalized and normalized not in reasons:
                reasons.append(normalized)
    return "|".join(reasons)


def _condition_explanation(item: DailyMarketResearchConditionResult) -> str:
    label = "MA20" if item.key.endswith("ma20") else "MA60"
    if item.state == "match":
        return f"收盤價高於 {label}。"
    if item.state == "no_match":
        return f"收盤價未高於 {label}（{item.relation}）。"
    detail = item.reason or "來源觀察不足。"
    return f"收盤價與 {label} 的關係未知：{detail}"


def _localized_reason(code_or_text: str) -> str:
    if not code_or_text:
        return ""
    if "|" in code_or_text:
        return "；".join(
            _localized_reason(part) for part in code_or_text.split("|") if part
        )
    label = _REASON_LABELS.get(code_or_text)
    return f"{label}（{code_or_text}）" if label else code_or_text
