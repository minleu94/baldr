"""既有每日市場快照的唯讀名單生命週期 projection。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import itertools
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from app_module.research_membership_history_index import MembershipHistoryPage

from app_module.daily_market_feature_snapshot import DAILY_MARKET_CONDITION_KEYS
from app_module.daily_market_snapshot_repository import (
    DAILY_MARKET_SNAPSHOT_MAX_MANIFEST_BYTES,
    DailyMarketSnapshotRepository,
    DailyMarketSnapshotVerificationError,
    VerifiedDailyMarketSnapshot,
    canonical_snapshot_json_bytes,
    snapshot_manifest_relpath,
)
from app_module.research_membership_lifecycle import (
    ExpectedSession,
    HistoryCoverage,
    LifecycleResult,
    LifecycleStatus,
    MembershipObservation,
    MembershipState,
    MethodIdentity,
    UniverseIdentity,
    classify_membership_lifecycle,
)


MAX_HISTORY_OBSERVATIONS = 32
MAX_HISTORY_DIRECTORY_ENTRIES = 4096
MAX_HISTORY_JSON_BYTES = 32 * 1024 * 1024
MAX_CALENDAR_CACHE_CANDIDATES = MAX_HISTORY_DIRECTORY_ENTRIES
MAX_CALENDAR_CACHE_SCAN_BYTES = 32 * 1024 * 1024
MAX_TEMPORARY_CLOSURE_CACHE_CANDIDATES = 32
_MANIFEST_NAME_RE = re.compile(r"^(?P<sha256>[0-9a-f]{64})\.json$")
_METHOD_WINDOW_POLICY = "daily_close_at_decision_date.v1"
_DEFAULT_CALENDAR_CACHE_RELATIVE_PATH = Path(
    "output/paper_execution_eod_replay/calendar_cache"
)

_STATUS_LABELS: dict[LifecycleStatus, str] = {
    LifecycleStatus.NEWLY_SELECTED: "本次新入選",
    LifecycleStatus.CONTINUING: "持續符合",
    LifecycleStatus.RESELECTED: "重新入選",
    LifecycleStatus.NO_LONGER_SELECTED: "未再符合",
    LifecycleStatus.REMAINS_NOT_SELECTED: "持續未符合",
    LifecycleStatus.FIRST_OBSERVATION: "首次觀測（自可驗證最早快照起）",
    LifecycleStatus.HISTORY_INSUFFICIENT: "歷史不足",
    LifecycleStatus.INCOMPARABLE: "無法比較／來源未知",
}
_STATUS_LABELS[LifecycleStatus.UNKNOWN] = "未知"

_REASON_LABELS = {
    "first_observation_in_verified_archive_scope": "這是目前可驗證快照範圍內的首次觀測，不代表自上市以來首次。",
    "history_boundary_not_complete": "可見歷史範圍不完整，不能判定首次入選或狀態變化。",
    "first_hit_after_consecutive_no_match_history": "可比較的連續未符合觀測後，本次首次符合。",
    "cannot_distinguish_first_hit_from_reselection": "缺少足夠連續歷史，無法區分首次符合與重新入選。",
    "prior_hit_then_consecutive_no_match_to_match": "先前曾符合，之後有連續未符合觀測，本次重新符合。",
    "consecutive_match": "前一個已驗證交易時段也符合。",
    "consecutive_match_to_no_match": "前一個已驗證交易時段符合，本次不符合。",
    "consecutive_no_match": "前一個已驗證交易時段也不符合。",
    "expected_session_gap_or_missing_observation": "前次觀測與本次之間有交易時段缺件，不能推定退出或重新入選。",
    "same_session_multiple_observations_or_revisions": "同一交易日有不同快照修訂，不能任選其中一版比較。",
    "method_identity_changed": "方法、參數或 AND／OR 規則版本改變，兩次觀測不可比較。",
    "universe_identity_changed": "研究母體成員、排除規則或版本改變，兩次觀測不可比較。",
    "current_expected_session_unverified": "本次交易時段沒有可驗證的離線官方日曆邊界。",
    "previous_expected_session_unverified": "前次交易時段沒有可驗證的離線官方日曆邊界。",
    "expected_session_schedule_identity_changed": "兩次觀測的日曆來源版本不同，無法證明時段連續。",
    "current_membership_unknown": "本次方法輸入缺件或無效，符合狀態未知。",
    "previous_membership_unknown": "前次方法輸入缺件或無效，符合狀態未知。",
    "current_source_available_after_as_of": "來源可用時間晚於本次快照發布時間，不能回填為當時已知。",
    "previous_source_available_after_as_of": "前次來源可用時間晚於本次快照發布時間，不能回填為當時已知。",
    "current_retrospective_backfill_after_cutoff": "本次來源資料晚於決策 cutoff，不能視為當時可得。",
    "previous_retrospective_backfill_after_cutoff": "前次來源資料晚於決策 cutoff，不能視為當時可得。",
    "history_stock_identity_mismatch": "歷史觀測的股票身份不一致。",
    "current_publication_after_as_of": "本次快照發布時間晚於指定觀測時間。",
    "current_source_available_after_as_of": "本次來源在快照發布後才可用，不能回填為當時已知。",
    "current_snapshot_partial_completeness_boundary": "本次母體快照不完整；保留觀測值，但不判定入選生命週期。",
    "history_snapshot_partial_completeness_boundary": "歷史母體快照不完整；不把缺件解讀為未符合或退出。",
    "current_stock_artifact_missing": "本次快照沒有此股票的有效 artifact。",
    "history_manifest_directory_missing": "找不到可驗證的歷史快照目錄。",
    "history_manifest_directory_unreadable": "歷史快照目錄無法完整列舉。",
    "history_manifest_directory_entry_limit_exceeded": "歷史目錄超過掃描上限，狀態保留為歷史不足。",
    "history_manifest_observation_limit_exceeded": "歷史快照數超過讀取上限，狀態保留為歷史不足。",
    "history_json_byte_limit_exceeded": "歷史 JSON 總讀取量超過上限，狀態保留為歷史不足。",
    "history_manifest_invalid_or_unverified": "存在無法驗證的歷史 manifest；不能跳過後續快照推定變化。",
    "current_pinned_snapshot_missing_or_changed": "目前固定快照無法重新核驗，保留當前觀測但不比較歷史。",
    "current_snapshot_partial_completeness": "目前母體快照不完整，生命週期狀態未知。",
    "calendar_source_unavailable": "沒有可用的離線已驗證官方交易日曆。",
    "calendar_session_unverified": "官方日曆無法驗證此交易時段及其前一時段。",
    "history_calendar_unverified": "至少一筆歷史觀測缺少已驗證日曆邊界。",
    "source_available_at_unrecorded": "快照未保存來源可用時間；此結果不證明歷史 PIT 資格。",
}

_REASON_LABELS["history_index_page_has_more"] = "本頁以外尚有較早觀測；首次觀測與連續期數只涵蓋本頁，首次命中不推論。"
_REASON_LABELS["history_snapshot_published_after_decision_day"] = (
    "歷史快照在決策日之後發布；當時可得性未獲證明。"
)
_REASON_LABELS["current_snapshot_published_after_decision_day"] = (
    "快照在決策日之後發布；當時可得性未獲證明。"
)
_REASON_LABELS["history_snapshot_stock_scope_changed"] = (
    "歷史快照的股票母體不含本列標的，不能判定進出或首次符合。"
)


class CalendarSessionProvider(Protocol):
    """只提供在指定 publication as-of 已可取得的官方 session 邊界。"""

    def expected_session(
        self, target_date: date, *, as_of: datetime
    ) -> ExpectedSession: ...


class _QuerySessionMemo:
    """同一查詢中依日期與 publication as-of 重用已驗證 session。"""

    def __init__(self, provider: CalendarSessionProvider) -> None:
        self._provider = provider
        self._cache: dict[tuple[date, datetime], ExpectedSession] = {}

    def expected_session(self, target_date: date, *, as_of: datetime) -> ExpectedSession:
        key = (target_date, as_of.astimezone(timezone.utc))
        if key not in self._cache:
            self._cache[key] = self._provider.expected_session(
                target_date, as_of=as_of
            )
        return self._cache[key]


@dataclass(frozen=True, slots=True)
class MembershipLifecycleSourceRef:
    """一筆可回放觀測所需的不可變來源身份。"""

    stock_code: str
    decision_date: date
    observation_id: str
    manifest_id: str
    manifest_sha256: str
    artifact_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "stock_code": self.stock_code,
            "decision_date": self.decision_date.isoformat(),
            "observation_id": self.observation_id,
            "manifest_id": self.manifest_id,
            "manifest_sha256": self.manifest_sha256,
            "artifact_sha256": self.artifact_sha256,
        }


@dataclass(frozen=True, slots=True)
class MembershipLifecycleRow:
    """單一股票的狀態、原因、日期及完整觀測來源。"""

    stock_code: str
    status: LifecycleStatus
    current_state: MembershipState
    previous_state: MembershipState | None
    previous_date: date | None
    first_seen: date | None
    last_hit: date | None
    streak: int
    reason: str
    reason_display: str
    current_observation_id: str | None
    previous_observation_id: str | None
    current_manifest_id: str
    current_manifest_sha256: str
    current_artifact_sha256: str | None
    history_observation_ids: tuple[str, ...]
    source_refs: tuple[MembershipLifecycleSourceRef, ...]
    condition_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    classification_json: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "stock_code": self.stock_code,
            "status": self.status.value,
            "status_display": _STATUS_LABELS[self.status],
            "current_state": self.current_state.value,
            "previous_state": self.previous_state.value if self.previous_state else None,
            "previous_date": self.previous_date.isoformat() if self.previous_date else None,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_hit": self.last_hit.isoformat() if self.last_hit else None,
            "streak": self.streak,
            "reason": self.reason,
            "reason_display": self.reason_display,
            "current_observation_id": self.current_observation_id,
            "previous_observation_id": self.previous_observation_id,
            "current_manifest_id": self.current_manifest_id,
            "current_manifest_sha256": self.current_manifest_sha256,
            "current_artifact_sha256": self.current_artifact_sha256,
            "history_observation_ids": list(self.history_observation_ids),
            "source_refs": [item.to_dict() for item in self.source_refs],
            "condition_reasons": list(self.condition_reasons),
            "warnings": list(self.warnings),
            "classification": (
                json.loads(self.classification_json)
                if self.classification_json
                else None
            ),
        }


@dataclass(frozen=True, slots=True)
class MembershipLifecycleReadModel:
    """同一固定快照與方法設定的 immutable read model。"""

    current_manifest_hash: str
    current_manifest_id: str
    current_decision_date: date
    current_published_at: datetime
    cohort_id: str
    condition_keys: tuple[str, ...]
    combine_mode: str
    rows_by_stock: Mapping[str, MembershipLifecycleRow]
    history_coverage: HistoryCoverage
    history_manifest_ids: tuple[str, ...]
    reason: str
    research_only: bool = True
    historical_pit_eligible: bool = False

    @property
    def current_manifest_sha256(self) -> str:
        """目前固定快照 manifest 的內容雜湊。"""

        return self.current_manifest_hash

    @property
    def current_manifest_identity_sha256(self) -> str:
        """目前固定快照 manifest 的穩定身分雜湊。"""

        return self.current_manifest_id

    @property
    def rows(self) -> tuple[MembershipLifecycleRow, ...]:
        """依股票代碼排序的列，供 UI 直接迭代。"""

        return tuple(self.rows_by_stock[key] for key in sorted(self.rows_by_stock))

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "current_manifest_hash": self.current_manifest_hash,
            "current_manifest_id": self.current_manifest_id,
            "current_decision_date": self.current_decision_date.isoformat(),
            "current_published_at": _datetime_text(self.current_published_at),
            "cohort_id": self.cohort_id,
            "condition_keys": list(self.condition_keys),
            "combine_mode": self.combine_mode,
            "rows_by_stock": {
                key: self.rows_by_stock[key].to_dict()
                for key in sorted(self.rows_by_stock)
            },
            "history_coverage": self.history_coverage.value,
            "history_manifest_ids": list(self.history_manifest_ids),
            "reason": self.reason,
            "research_only": self.research_only,
            "historical_pit_eligible": self.historical_pit_eligible,
        }
        value["result_id"] = hashlib.sha256(
            _canonical_json(value).encode("utf-8")
        ).hexdigest()
        return value


class _HistoryBoundary(RuntimeError):
    def __init__(self, reason: str, coverage: HistoryCoverage) -> None:
        super().__init__(reason)
        self.reason = reason
        self.coverage = coverage


class _BudgetedSnapshotRepository(DailyMarketSnapshotRepository):
    """在原 strict reader 上快取同次查詢的 JSON 並限制總 byte 數。"""

    def __init__(
        self,
        output_root: str | Path,
        *,
        cancel_callback: Callable[[], bool] | None,
    ) -> None:
        super().__init__(output_root)
        self._cancel_callback = cancel_callback
        self._json_cache: dict[str, tuple[bytes, dict[str, Any]]] = {}
        self.bytes_read = 0

    def _read_json_file(
        self,
        relative_path: Path,
        *,
        limit: int,
        missing_code: str,
        invalid_code: str,
    ) -> tuple[bytes, dict[str, Any]]:
        _raise_if_cancelled(self._cancel_callback)
        cache_key = relative_path.as_posix()
        cached = self._json_cache.get(cache_key)
        if cached is not None:
            return cached[0], deepcopy(cached[1])
        raw, value = super()._read_json_file(
            relative_path,
            limit=limit,
            missing_code=missing_code,
            invalid_code=invalid_code,
        )
        next_total = self.bytes_read + len(raw)
        if next_total > MAX_HISTORY_JSON_BYTES:
            raise _HistoryBoundary(
                "history_json_byte_limit_exceeded", HistoryCoverage.TRUNCATED
            )
        self.bytes_read = next_total
        self._json_cache[cache_key] = (raw, deepcopy(value))
        return raw, value


@dataclass(frozen=True, slots=True)
class _HistoryScan:
    snapshots: tuple[VerifiedDailyMarketSnapshot, ...]
    coverage: HistoryCoverage
    manifest_ids: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class OfflineOfficialCalendarSessionProvider:
    """以離線 TWSE cache 驗證前一交易時段，publication 前不可見的 cache 不採用。"""

    calendar_cache_path: Path
    temporary_closure_path: Path | None = None
    max_lookback_days: int = 32

    def expected_session(self, target_date: date, *, as_of: datetime) -> ExpectedSession:
        from data_module.official_trading_calendar_cache import (
            OfficialCalendarCacheError,
            load_verified_twse_calendar_cache,
            load_verified_twse_temporary_closure_cache,
        )

        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of 必須是 timezone-aware datetime")
        if self.max_lookback_days < 1 or self.max_lookback_days > 62:
            raise ValueError("max_lookback_days 必須介於 1 與 62")
        loaded: dict[int, Any] = {}
        temporary: dict[date, tuple[str, str] | None | bool] = {}
        cache_identity_parts: set[str] = set()

        def cache_for(year: int) -> Any | None:
            if year in loaded:
                return loaded[year]
            candidates = _calendar_cache_candidates(self.calendar_cache_path, year)
            if candidates is None:
                loaded[year] = None
                return None
            selected: Any | None = None
            scanned_bytes = 0
            for candidate in candidates:
                _raise_if_cancelled(None)
                try:
                    scanned_bytes += candidate.stat().st_size
                    if scanned_bytes > MAX_CALENDAR_CACHE_SCAN_BYTES:
                        loaded[year] = None
                        return None
                    item = load_verified_twse_calendar_cache(
                        candidate,
                        calendar_year=year,
                        observed_at=as_of,
                    )
                    if selected is None or str(item.evidence.get("captured_at", "")) > str(selected.evidence.get("captured_at", "")):
                        selected = item
                except (OSError, OfficialCalendarCacheError):
                    continue
            loaded[year] = selected
            return selected

        def is_open(day: date) -> bool | None:
            cache = cache_for(day.year)
            if cache is None:
                return None
            evidence = cache.evidence
            cache_file_sha = str(evidence.get("cache_file_sha256", "")).removeprefix("sha256:")
            cache_content_sha = str(evidence.get("cache_content_sha256", "")).removeprefix("sha256:")
            if not _is_sha256(cache_file_sha) or not _is_sha256(cache_content_sha):
                return None
            cache_identity_parts.add(
                f"{day.year}:{cache_content_sha}:{cache_file_sha}"
            )
            # 經 hash 驗證的完整 TWSE annual schedule 明確允許以未列出的
            # 平日表示開市；週末則沿官方 calendar 的固定休市規則處理。
            if day.weekday() >= 5:
                return False
            if day in cache.schedule and cache.schedule[day] is False:
                return False
            closure = temporary_for(day)
            if closure is False:
                return None
            if isinstance(closure, tuple):
                cache_identity_parts.add(f"closure:{day.isoformat()}:{closure[1]}")
                return False
            return True

        def temporary_for(day: date) -> tuple[str, str] | None | bool:
            if day in temporary:
                return temporary[day]
            source = self.temporary_closure_path
            if source is None:
                # 未設定額外停市 overlay 時沿既有已核驗年度「預期交易」計畫；
                # 不把 optional 來源當成必填，也不授予實際開市或歷史 PIT 證明。
                temporary[day] = None
                return None
            candidates = _temporary_closure_cache_candidates(source)
            if candidates is None:
                temporary[day] = False
                return False
            found: list[tuple[str, str, str]] = []
            for candidate in candidates:
                _raise_if_cancelled(None)
                try:
                    item = load_verified_twse_temporary_closure_cache(
                        candidate, observed_at=as_of
                    )
                except (OSError, OfficialCalendarCacheError):
                    temporary[day] = False
                    return False
                if item.closure_date == day:
                    file_sha = _file_sha256(candidate)
                    content_sha = str(item.evidence.get("cache_content_sha256", "")).removeprefix("sha256:")
                    if not _is_sha256(file_sha) or not _is_sha256(content_sha):
                        temporary[day] = False
                        return False
                    found.append((str(item.evidence.get("captured_at", "")), file_sha, content_sha))
            found.sort()
            if not found:
                temporary[day] = None  # type: ignore[assignment]
                return None
            _, file_sha, content_sha = found[-1]
            result = (file_sha, content_sha)
            temporary[day] = result
            return result

        if is_open(target_date) is not True:
            return ExpectedSession(
                calendar_key="TWSE.official_trading_calendar",
                calendar_version="annual_planned_cache.v1",
                expected_previous_date=None,
                verified=False,
            )
        previous: date | None = None
        for offset in range(1, self.max_lookback_days + 1):
            candidate = target_date - timedelta(days=offset)
            candidate_open = is_open(candidate)
            if candidate_open is None:
                return ExpectedSession(
                    calendar_key="TWSE.official_trading_calendar",
                    calendar_version="annual_planned_cache.v1",
                    expected_previous_date=None,
                    verified=False,
                )
            if candidate_open:
                previous = candidate
                break
        if previous is None:
            return ExpectedSession(
                calendar_key="TWSE.official_trading_calendar",
                calendar_version="annual_planned_cache.v1",
                expected_previous_date=None,
                verified=False,
            )
        material = "|".join(sorted(cache_identity_parts)).encode("utf-8")
        combined_sha = hashlib.sha256(material).hexdigest()
        return ExpectedSession(
            calendar_key="TWSE.official_trading_calendar",
            calendar_version="annual_planned_cache.v1",
            expected_previous_date=previous,
            verified=True,
            calendar_manifest_id=combined_sha,
            calendar_manifest_sha256=combined_sha,
        )


def create_offline_official_calendar_session_provider(
    calendar_cache_path: str | Path | None = None,
    *,
    temporary_closure_path: str | Path | None = None,
) -> OfflineOfficialCalendarSessionProvider:
    """建立完全離線的 TWSE 日曆 adapter；不建立 cache 或讀正式 market DB。"""

    calendar_path = (
        Path(calendar_cache_path).expanduser()
        if calendar_cache_path is not None
        else Path(__file__).resolve().parents[1]
        / _DEFAULT_CALENDAR_CACHE_RELATIVE_PATH
    )
    closure_path = (
        Path(temporary_closure_path).expanduser()
        if temporary_closure_path is not None
        else None
    )
    return OfflineOfficialCalendarSessionProvider(calendar_path, closure_path)


def read_membership_lifecycle(
    repository: DailyMarketSnapshotRepository,
    current: VerifiedDailyMarketSnapshot,
    condition_keys: tuple[str, ...],
    combine_mode: str,
    *,
    cancel_callback: Callable[[], bool] | None = None,
    session_provider: CalendarSessionProvider | None = None,
    history_page: MembershipHistoryPage | None = None,
) -> MembershipLifecycleReadModel:
    """讀固定快照並回放可比較生命週期；不寫 ledger、不產生市場資料。"""

    normalized_keys = _normalize_conditions(condition_keys)
    mode = _normalize_combine_mode(combine_mode)
    _raise_if_cancelled(cancel_callback)
    as_of = _manifest_datetime(current.manifest, "published_at")
    scan = (
        _scan_indexed_history(repository, current, history_page, cancel_callback=cancel_callback)
        if history_page is not None
        else _scan_history(repository, current, as_of=as_of, cancel_callback=cancel_callback)
    )
    effective_session_provider = (
        _QuerySessionMemo(session_provider)
        if session_provider is not None
        else None
    )
    all_snapshots = scan.snapshots
    current_snapshot = next(
        (
            item
            for item in all_snapshots
            if item.manifest_sha256 == current.manifest_sha256
        ),
        current,
    )
    current_manifest = current_snapshot.manifest
    current_identity = str(current_manifest.get("manifest_identity_sha256", ""))
    current_records = _manifest_records(current_manifest)
    current_codes = tuple(str(code) for code in current_manifest["declared_stock_codes"])
    current_complete = current_manifest.get("completeness") == "complete_declared_cohort"

    coverage = scan.coverage
    if any(
        item.manifest.get("completeness") != "complete_declared_cohort"
        for item in all_snapshots
        if item.manifest_sha256 != current.manifest_sha256
    ):
        coverage = HistoryCoverage.UNKNOWN
        scan_reason = "history_snapshot_partial_completeness_boundary"
    else:
        scan_reason = scan.reason

    if not current_complete:
        coverage = HistoryCoverage.UNKNOWN
        scan_reason = "current_snapshot_partial_completeness"

    # 當歷史來源／範圍本身不完整時，不把可讀的舊列跨過邊界比較。
    snapshots_for_classification = (
        all_snapshots
        if (coverage is HistoryCoverage.COMPLETE or scan.reason == "history_index_page_has_more") and current_complete
        else (current_snapshot,)
    )

    history_manifest_ids = tuple(
        sorted(
            {
                item.manifest_sha256
                for item in all_snapshots
                if _visible_as_of(item, as_of, current.decision_date)
            }
        )
    )
    rows: dict[str, MembershipLifecycleRow] = {}
    for stock_code in current_codes:
        _raise_if_cancelled(cancel_callback)
        record = current_records.get(stock_code)
        payload = current_snapshot.stock_snapshots.get(stock_code)
        if record is None or payload is None:
            rows[stock_code] = _missing_current_row(
                stock_code,
                current=current_snapshot,
                current_manifest_id=current_identity,
                reason="current_stock_artifact_missing",
                condition_reasons=("current_snapshot_missing_stock_artifact",),
            )
            continue

        current_state, condition_reasons = _evaluate_membership(
            payload,
            normalized_keys,
            mode,
            expected_decision_date=current_snapshot.decision_date,
        )
        current_late_publication = _published_after_cutoff_day(current_manifest)
        if current_late_publication:
            current_state = MembershipState.UNKNOWN
            condition_reasons += ("current_snapshot_published_after_decision_day",)
        method = _method_identity(current_manifest, normalized_keys, mode)
        universe = _universe_identity(current_manifest)
        current_observation = _make_observation(
            stock_code,
            current_state,
            method,
            universe,
            current_snapshot,
            record,
            as_of=as_of,
            session_provider=effective_session_provider,
            session_as_of=as_of,
        )

        history_observations: list[MembershipObservation] = []
        history_condition_reasons: dict[str, tuple[str, ...]] = {}
        history_late_publication = False
        history_stock_scope_boundary = False
        for historical in snapshots_for_classification:
            if historical.manifest_sha256 == current_snapshot.manifest_sha256:
                continue
            if not _visible_as_of(historical, as_of, current_snapshot.decision_date):
                continue
            historical_records = _manifest_records(historical.manifest)
            historical_record = historical_records.get(stock_code)
            historical_payload = historical.stock_snapshots.get(stock_code)
            if historical_record is None or historical_payload is None:
                history_stock_scope_boundary = True
                continue
            historical_state, historical_reasons = _evaluate_membership(
                historical_payload,
                normalized_keys,
                mode,
                expected_decision_date=historical.decision_date,
            )
            if _published_after_cutoff_day(historical.manifest):
                history_late_publication = True
                historical_state = MembershipState.UNKNOWN
                historical_reasons += ("history_snapshot_published_after_decision_day",)
            history_condition_reasons[historical.manifest_sha256] = historical_reasons
            history_observations.append(
                _make_observation(
                    stock_code,
                    historical_state,
                    _method_identity(historical.manifest, normalized_keys, mode),
                    _universe_identity(historical.manifest),
                    historical,
                    historical_record,
                    as_of=as_of,
                    session_provider=effective_session_provider,
                    session_as_of=_manifest_datetime(
                        historical.manifest, "published_at"
                    ),
                )
            )

        lifecycle = classify_membership_lifecycle(
            current_observation,
            tuple(history_observations),
            as_of=as_of,
            history_coverage=coverage,
        )
        if current_late_publication or history_late_publication:
            from dataclasses import replace

            lifecycle = replace(
                lifecycle,
                status=(
                    LifecycleStatus.UNKNOWN
                    if current_late_publication
                    else LifecycleStatus.HISTORY_INSUFFICIENT
                ),
                reason=(
                    "current_snapshot_published_after_decision_day"
                    if current_late_publication
                    else "history_snapshot_published_after_decision_day"
                ),
                first_seen=None,
                last_hit=None,
                streak=0,
                previous_date=None,
                previous_state=None,
            )
        elif history_stock_scope_boundary:
            from dataclasses import replace

            lifecycle = replace(
                lifecycle,
                status=LifecycleStatus.HISTORY_INSUFFICIENT,
                reason="history_snapshot_stock_scope_changed",
                first_seen=None,
                last_hit=None,
                streak=0,
                previous_date=None,
                previous_state=None,
            )
        if not current_complete:
            lifecycle = _override_partial_current(lifecycle)
        reason_display = _reason_display(
            lifecycle.reason,
            boundary_reason=scan_reason if scan_reason != "history_complete" else None,
            pit_unknown=current_observation.source_available_at is None,
        )
        sources = tuple(
            _source_ref(item) for item in lifecycle.source_observations
        )
        previous = next(
            (
                item
                for item in lifecycle.source_observations
                if lifecycle.previous_date is not None
                and item.decision_date == lifecycle.previous_date
            ),
            None,
        )
        current_artifact_sha = current_observation.source_artifact_sha256
        rows[stock_code] = MembershipLifecycleRow(
            stock_code=stock_code,
            status=lifecycle.status,
            current_state=current_observation.state,
            previous_state=lifecycle.previous_state,
            previous_date=lifecycle.previous_date,
            first_seen=lifecycle.first_seen,
            last_hit=lifecycle.last_hit,
            streak=lifecycle.streak,
            reason=lifecycle.reason,
            reason_display=reason_display,
            current_observation_id=current_observation.observation_id,
            previous_observation_id=previous.observation_id if previous else None,
            current_manifest_id=current_observation.source_manifest_id,
            current_manifest_sha256=current_observation.source_manifest_sha256,
            current_artifact_sha256=current_artifact_sha,
            history_observation_ids=tuple(
                sorted(
                    item.observation_id
                    for item in lifecycle.source_observations
                    if item.observation_id != current_observation.observation_id
                )
            ),
            source_refs=sources,
            condition_reasons=condition_reasons
            + tuple(
                reason
                for history_id in sorted(history_condition_reasons)
                for reason in history_condition_reasons[history_id]
            ),
            warnings=tuple(
                warning
                for warning, include in (
                    (
                        "source_available_at_unrecorded",
                        current_observation.source_available_at is None,
                    ),
                    (
                        "current_snapshot_published_after_decision_day",
                        current_late_publication,
                    ),
                    (
                        "history_snapshot_published_after_decision_day",
                        history_late_publication,
                    ),
                    (
                        "history_snapshot_stock_scope_changed",
                        history_stock_scope_boundary,
                    ),
                )
                if include
            ),
            classification_json=_canonical_json(lifecycle.to_dict()),
        )

    return MembershipLifecycleReadModel(
        current_manifest_hash=current_snapshot.manifest_sha256,
        current_manifest_id=current_identity,
        current_decision_date=current_snapshot.decision_date,
        current_published_at=as_of,
        cohort_id=current_snapshot.cohort_id,
        condition_keys=normalized_keys,
        combine_mode=mode,
        rows_by_stock=MappingProxyType(dict(sorted(rows.items()))),
        history_coverage=coverage,
        history_manifest_ids=history_manifest_ids,
        reason=scan_reason,
    )


def load_membership_history_page_snapshots(
    repository: DailyMarketSnapshotRepository,
    current: VerifiedDailyMarketSnapshot,
    page: MembershipHistoryPage,
    *, cancel_callback: Callable[[], bool] | None = None,
) -> tuple[VerifiedDailyMarketSnapshot, ...]:
    """只核驗本頁 artifacts；當期 anchor 與每個 revision 的 refs 不可混源。"""
    from app_module.research_membership_history_index import MembershipHistoryIndexError

    pin = page.current_pin
    if (pin.manifest_sha256 != current.manifest_sha256
            or pin.manifest_identity_sha256 != current.manifest_identity_sha256
            or pin.cohort_id != current.cohort_id or pin.decision_date != current.decision_date
            or len(page.refs) > 32):
        raise MembershipHistoryIndexError("source_changed", "歷史頁與固定當期來源不符")
    bounded = _BudgetedSnapshotRepository(repository.output_root, cancel_callback=cancel_callback)
    verified_current = bounded.load_manifest(current.manifest_sha256, current.cohort_id, current.decision_date)
    if verified_current.manifest_identity_sha256 != current.manifest_identity_sha256:
        raise MembershipHistoryIndexError("source_changed", "當期來源已修改")
    as_of = _manifest_datetime(current.manifest, "published_at")
    snapshots: list[VerifiedDailyMarketSnapshot] = []
    try:
        for ref in page.refs:
            _raise_if_cancelled(cancel_callback)
            item = bounded.load_manifest(ref.manifest_sha256, ref.cohort_id, ref.decision_date)
            if (item.manifest_identity_sha256 != ref.manifest_identity_sha256
                    or item.cohort_id != current.cohort_id
                    or _manifest_datetime(item.manifest, "published_at") != ref.published_at
                    or not _visible_as_of(item, as_of, current.decision_date)):
                raise MembershipHistoryIndexError("source_changed", "本頁觀測與索引來源不符")
            snapshots.append(item)
    except _HistoryBoundary as exc:
        raise MembershipHistoryIndexError("page_budget_exceeded", "本頁來源 JSON 超過 32 MiB；保持未知") from exc
    return tuple(snapshots)


def _scan_indexed_history(
    repository: DailyMarketSnapshotRepository, current: VerifiedDailyMarketSnapshot,
    page: MembershipHistoryPage, *, cancel_callback: Callable[[], bool] | None,
) -> _HistoryScan:
    snapshots = load_membership_history_page_snapshots(repository, current, page, cancel_callback=cancel_callback)
    if not any(item.manifest_sha256 == current.manifest_sha256 for item in snapshots):
        snapshots = (*snapshots, current)
    coverage = HistoryCoverage.TRUNCATED if page.has_more else HistoryCoverage.COMPLETE
    reason = "history_index_page_has_more" if page.has_more else "history_complete"
    if any(item.completeness != "complete_declared_cohort" for item in snapshots):
        coverage, reason = HistoryCoverage.UNKNOWN, "history_snapshot_partial_completeness_boundary"
    return _HistoryScan(snapshots, coverage, tuple(item.manifest_sha256 for item in snapshots), reason)


def _scan_history(
    repository: DailyMarketSnapshotRepository,
    current: VerifiedDailyMarketSnapshot,
    *,
    as_of: datetime,
    cancel_callback: Callable[[], bool] | None,
) -> _HistoryScan:
    root = repository.output_root
    manifest_directory = root / "manifests"
    if manifest_directory.is_symlink() or not manifest_directory.is_dir():
        return _HistoryScan(
            (current,), HistoryCoverage.UNKNOWN, (), "history_manifest_directory_missing"
        )
    try:
        entries = sorted(
            itertools.islice(manifest_directory.iterdir(), MAX_HISTORY_DIRECTORY_ENTRIES + 1),
            key=lambda item: item.name,
        )
    except OSError:
        return _HistoryScan(
            (current,), HistoryCoverage.UNKNOWN, (), "history_manifest_directory_unreadable"
        )
    if len(entries) > MAX_HISTORY_DIRECTORY_ENTRIES:
        return _HistoryScan(
            (current,),
            HistoryCoverage.TRUNCATED,
            (),
            "history_manifest_directory_entry_limit_exceeded",
        )

    manifest_paths: list[tuple[str, Path]] = []
    for entry in entries:
        match = _MANIFEST_NAME_RE.fullmatch(entry.name)
        if entry.is_symlink() or not entry.is_file() or match is None:
            return _HistoryScan(
                (current,),
                HistoryCoverage.UNKNOWN,
                (),
                "history_manifest_invalid_or_unverified",
            )
        manifest_paths.append((match.group("sha256"), entry))
    if len(manifest_paths) > MAX_HISTORY_OBSERVATIONS:
        return _HistoryScan(
            (current,),
            HistoryCoverage.TRUNCATED,
            (),
            "history_manifest_observation_limit_exceeded",
        )

    bounded = _BudgetedSnapshotRepository(
        root, cancel_callback=cancel_callback
    )
    verified: list[VerifiedDailyMarketSnapshot] = []
    try:
        for digest, path in manifest_paths:
            _raise_if_cancelled(cancel_callback)
            raw, manifest = bounded._read_json_file(
                Path(snapshot_manifest_relpath(digest)),
                limit=DAILY_MARKET_SNAPSHOT_MAX_MANIFEST_BYTES,
                missing_code="snapshot_manifest_missing",
                invalid_code="snapshot_manifest_invalid",
            )
            if (
                hashlib.sha256(raw).hexdigest() != digest
                or canonical_snapshot_json_bytes(manifest) != raw
            ):
                raise _HistoryBoundary(
                    "history_manifest_invalid_or_unverified", HistoryCoverage.UNKNOWN
                )
            cohort_id = manifest.get("cohort_id")
            decision_date = _parse_date(manifest.get("decision_date"))
            if not isinstance(cohort_id, str) or not cohort_id.strip():
                raise _HistoryBoundary(
                    "history_manifest_invalid_or_unverified", HistoryCoverage.UNKNOWN
                )
            try:
                item = bounded.load_manifest(
                    digest,
                    cohort_id,
                    decision_date,
                )
            except (DailyMarketSnapshotVerificationError, OSError, TypeError, ValueError) as exc:
                raise _HistoryBoundary(
                    "history_manifest_invalid_or_unverified", HistoryCoverage.UNKNOWN
                ) from exc
            verified.append(item)
    except _HistoryBoundary as boundary:
        return _HistoryScan((current,), boundary.coverage, (), boundary.reason)
    except DailyMarketSnapshotVerificationError:
        return _HistoryScan(
            (current,),
            HistoryCoverage.UNKNOWN,
            (),
            "history_manifest_invalid_or_unverified",
        )

    if not any(item.manifest_sha256 == current.manifest_sha256 for item in verified):
        return _HistoryScan(
            (current,),
            HistoryCoverage.UNKNOWN,
            (),
            "current_pinned_snapshot_missing_or_changed",
        )
    verified_current = next(
        item for item in verified if item.manifest_sha256 == current.manifest_sha256
    )
    if (
        verified_current.manifest_identity_sha256 != current.manifest_identity_sha256
        or verified_current.cohort_id != current.cohort_id
        or verified_current.decision_date != current.decision_date
    ):
        return _HistoryScan(
            (current,),
            HistoryCoverage.UNKNOWN,
            (),
            "current_pinned_snapshot_missing_or_changed",
        )

    visible = tuple(
        item
        for item in verified
        if item.cohort_id == current.cohort_id
        and _visible_as_of(item, as_of, current.decision_date)
    )
    visible = tuple(
        sorted(
            visible,
            key=lambda item: (
                item.decision_date,
                str(item.manifest.get("published_at", "")),
                item.manifest_sha256,
            ),
        )
    )
    if any(item.completeness != "complete_declared_cohort" for item in visible):
        return _HistoryScan(
            visible,
            HistoryCoverage.UNKNOWN,
            tuple(item.manifest_sha256 for item in visible),
            "history_snapshot_partial_completeness_boundary",
        )
    return _HistoryScan(
        visible,
        HistoryCoverage.COMPLETE,
        tuple(item.manifest_sha256 for item in visible),
        "history_complete",
    )


def _make_observation(
    stock_code: str,
    state: MembershipState,
    method: MethodIdentity,
    universe: UniverseIdentity,
    snapshot: VerifiedDailyMarketSnapshot,
    record: Mapping[str, Any],
    *,
    as_of: datetime,
    session_provider: CalendarSessionProvider | None,
    session_as_of: datetime,
) -> MembershipObservation:
    manifest = snapshot.manifest
    session = (
        session_provider.expected_session(snapshot.decision_date, as_of=session_as_of)
        if session_provider is not None
        else _unknown_session()
    )
    cutoff = _manifest_datetime(manifest, "decision_cutoff")
    published_at = _manifest_datetime(manifest, "published_at")
    raw_available = manifest.get("source_available_at")
    source_available_at = (
        _parse_datetime(raw_available)
        if isinstance(raw_available, str) and raw_available.strip()
        else None
    )
    return MembershipObservation(
        stock_id=stock_code,
        state=state,
        method=method,
        universe=universe,
        decision_date=snapshot.decision_date,
        cutoff_at=cutoff,
        published_at=published_at,
        source_available_at=source_available_at,
        schedule=session,
        source_manifest_id=snapshot.manifest_identity_sha256,
        source_manifest_sha256=snapshot.manifest_sha256,
        source_artifact_sha256=str(record["artifact_sha256"]),
    )


def _evaluate_membership(
    payload: Mapping[str, Any],
    condition_keys: tuple[str, ...],
    combine_mode: str,
    *,
    expected_decision_date: date,
) -> tuple[MembershipState, tuple[str, ...]]:
    # 使用現有三態 AND／OR evaluator；本 read model 不重算 MA 公式。
    from app_module.daily_market_research_screener import evaluate_daily_market_conditions

    raw_conditions = payload.get("conditions")
    conditions = raw_conditions if isinstance(raw_conditions, Mapping) else {}
    evaluation = evaluate_daily_market_conditions(
        conditions,
        condition_keys,
        combine_mode,
        expected_decision_date=expected_decision_date,
    )
    try:
        state = MembershipState(evaluation.combined_state)
    except ValueError:
        state = MembershipState.UNKNOWN
    reasons = tuple(
        f"{item.key}:{item.reason}"
        for item in evaluation.conditions
    )
    return state, reasons


def _method_identity(
    manifest: Mapping[str, Any], condition_keys: tuple[str, ...], combine_mode: str
) -> MethodIdentity:
    raw_contracts = manifest.get("method_contracts")
    contracts = raw_contracts if isinstance(raw_contracts, Mapping) else {}
    selected: list[dict[str, Any]] = []
    for key in sorted(condition_keys):
        raw_contract = contracts.get(key)
        if not isinstance(raw_contract, Mapping):
            raise ValueError(f"快照缺少方法契約：{key}")
        selected.append(
            {
                "key": key,
                "method_id": raw_contract.get("method_id"),
                "version": raw_contract.get("version"),
                "parameters": dict(raw_contract.get("parameters", {})),
                "family": raw_contract.get("family"),
                "required_fields": list(raw_contract.get("required_fields", [])),
            }
        )
    primary = selected[0]
    predicate = {
        "combine_mode": combine_mode,
        "condition_keys": sorted(condition_keys),
        "methods": selected,
    }
    return MethodIdentity(
        method_id=str(primary["method_id"]),
        version=str(primary["version"]),
        parameters_json=_canonical_json(primary["parameters"]),
        predicate_semantic_key=_canonical_json(predicate),
        window_policy_key=_METHOD_WINDOW_POLICY,
    )


def _universe_identity(manifest: Mapping[str, Any]) -> UniverseIdentity:
    raw_universe = manifest.get("research_universe")
    universe = raw_universe if isinstance(raw_universe, Mapping) else {}
    cohort_id = str(manifest.get("cohort_id", ""))
    declared = manifest.get("declared_stock_codes")
    members = sorted(str(code) for code in declared) if isinstance(declared, list) else []
    excluded = universe.get("excluded_stock_codes", [])
    stable_exclusions = []
    if isinstance(excluded, list):
        for item in excluded:
            if isinstance(item, Mapping):
                stable_exclusions.append(
                    {
                        "stock_code": item.get("stock_code"),
                        "reason": item.get("reason"),
                    }
                )
    stable_semantics = {
        "cohort_id": cohort_id,
        "cohort_identity": manifest.get("cohort_identity"),
        "members": members,
        "universe_method": universe.get("method"),
        "universe_members": sorted(
            str(code)
            for code in universe.get("included_stock_codes", [])
            if isinstance(code, str)
        ),
        "exclusions": stable_exclusions,
        "population_count": universe.get("population_count"),
        "scope": universe.get("scope", "bounded_research_cohort"),
        "research_only": universe.get("research_only", True),
        "complete_fixed_cohort": universe.get("complete_fixed_cohort", True),
    }
    universe_id = str(universe.get("universe_id") or cohort_id)
    version = str(universe.get("version") or "bounded_cohort.v1")
    return UniverseIdentity(
        universe_id=universe_id,
        version=version,
        semantic_key=hashlib.sha256(_canonical_json(stable_semantics).encode("utf-8")).hexdigest(),
    )


def _missing_current_row(
    stock_code: str,
    *,
    current: VerifiedDailyMarketSnapshot,
    current_manifest_id: str,
    reason: str,
    condition_reasons: tuple[str, ...],
) -> MembershipLifecycleRow:
    return MembershipLifecycleRow(
        stock_code=stock_code,
        status=LifecycleStatus.HISTORY_INSUFFICIENT,
        current_state=MembershipState.UNKNOWN,
        previous_state=None,
        previous_date=None,
        first_seen=None,
        last_hit=None,
        streak=0,
        reason=reason,
        reason_display=_reason_display(reason, boundary_reason=None, pit_unknown=True),
        current_observation_id=None,
        previous_observation_id=None,
        current_manifest_id=current_manifest_id,
        current_manifest_sha256=current.manifest_sha256,
        current_artifact_sha256=None,
        history_observation_ids=(),
        source_refs=(),
        condition_reasons=condition_reasons,
        warnings=("source_available_at_unrecorded",),
    )


def _override_partial_current(result: LifecycleResult) -> LifecycleResult:
    from dataclasses import replace

    return replace(
        result,
        status=LifecycleStatus.HISTORY_INSUFFICIENT,
        reason="current_snapshot_partial_completeness_boundary",
        previous_date=None,
        previous_state=None,
        first_seen=None,
        last_hit=None,
        streak=0,
    )


def _source_ref(item: MembershipObservation) -> MembershipLifecycleSourceRef:
    return MembershipLifecycleSourceRef(
        stock_code=item.stock_id,
        decision_date=item.decision_date,
        observation_id=item.observation_id,
        manifest_id=item.source_manifest_id,
        manifest_sha256=item.source_manifest_sha256,
        artifact_sha256=item.source_artifact_sha256,
    )


def _visible_as_of(
    snapshot: VerifiedDailyMarketSnapshot, as_of: datetime, current_date: date
) -> bool:
    published_at = _manifest_datetime(snapshot.manifest, "published_at")
    return published_at <= as_of and snapshot.decision_date <= current_date


def _manifest_records(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    raw = manifest.get("stocks")
    if not isinstance(raw, list):
        return {}
    return {
        str(item["stock_code"]): item
        for item in raw
        if isinstance(item, Mapping) and isinstance(item.get("stock_code"), str)
    }


def _normalize_conditions(condition_keys: Sequence[str]) -> tuple[str, ...]:
    if isinstance(condition_keys, str):
        raise ValueError("condition_keys 必須是明示 tuple／sequence")
    normalized = tuple(condition_keys)
    if not normalized or len(normalized) > 2:
        raise ValueError("condition_keys 必須包含一至兩個既有 MA 條件")
    if len(set(normalized)) != len(normalized):
        raise ValueError("condition_keys 不可重複")
    if any(key not in DAILY_MARKET_CONDITION_KEYS for key in normalized):
        raise ValueError("只支援既有 close_above_ma20／close_above_ma60 條件")
    return normalized


def _normalize_combine_mode(value: str) -> str:
    mode = str(value).strip().upper()
    if mode not in {"AND", "OR"}:
        raise ValueError("combine_mode 必須是 AND 或 OR")
    return mode


def _unknown_session() -> ExpectedSession:
    return ExpectedSession(
        calendar_key="unavailable",
        calendar_version="unknown",
        expected_previous_date=None,
        verified=False,
    )


def _reason_display(
    reason: str,
    *,
    boundary_reason: str | None,
    pit_unknown: bool,
) -> str:
    parts = [_REASON_LABELS.get(reason, "目前來源或歷史邊界不足，無法安全比較。")]
    if boundary_reason and boundary_reason != "history_complete":
        boundary = _REASON_LABELS.get(boundary_reason)
        if boundary and boundary not in parts:
            parts.append(boundary)
    if pit_unknown:
        pit = _REASON_LABELS["source_available_at_unrecorded"]
        if pit not in parts:
            parts.append(pit)
    return " ".join(parts)


def _manifest_datetime(manifest: Mapping[str, Any], key: str) -> datetime:
    value = manifest.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"manifest {key} 缺少 aware timestamp")
    return _parse_datetime(value)


def _published_after_cutoff_day(manifest: Mapping[str, Any]) -> bool:
    """跨過決策 cutoff 所在日期才發布的快照不可回填為當時已知。"""

    cutoff = _manifest_datetime(manifest, "decision_cutoff")
    published = _manifest_datetime(manifest, "published_at")
    return published.astimezone(cutoff.tzinfo).date() > cutoff.date()


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("manifest timestamp 格式錯誤") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("manifest timestamp 必須是 timezone-aware")
    return parsed


def _parse_date(value: Any) -> date:
    if not isinstance(value, str):
        raise ValueError("manifest decision_date 必須是 ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("manifest decision_date 格式錯誤") from exc


def _datetime_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _raise_if_cancelled(callback: Callable[[], bool] | None) -> None:
    if callback is not None and callback():
        from app_module.daily_market_research_screener import DailyMarketResearchCancelled

        raise DailyMarketResearchCancelled("使用者已取消名單生命週期讀取。")


def _is_sha256(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _calendar_cache_candidates(root: Path, year: int) -> tuple[Path, ...] | None:
    base = root.expanduser()
    if base.is_symlink():
        return None
    if base.is_file() or base.suffix.casefold() == ".json":
        return (base,)
    if not base.is_dir():
        return None
    entries = _bounded_directory_entries(base)
    if entries is None:
        return None
    prefix = f"twse_holiday_schedule_{year}_"
    values = [
        item
        for item in entries
        if item.name.startswith(prefix) and item.name.endswith(".json")
    ]
    exact = base / f"twse_holiday_schedule_{year}.json"
    if exact.exists():
        values.append(exact)
    values = sorted(set(values), key=str)
    if len(values) > MAX_CALENDAR_CACHE_CANDIDATES or any(
        item.is_symlink() for item in values
    ):
        return None
    return tuple(values)


def _temporary_closure_cache_candidates(root: Path) -> tuple[Path, ...] | None:
    base = root.expanduser()
    if base.is_symlink():
        return None
    if base.is_file() or base.suffix.casefold() == ".json":
        return (base,)
    if not base.is_dir():
        return None
    entries = _bounded_directory_entries(base)
    if entries is None:
        return None
    values = [
        item
        for item in entries
        if item.name.startswith("twse_temporary_closure_")
        and item.name.endswith(".json")
    ]
    if len(values) > MAX_TEMPORARY_CLOSURE_CACHE_CANDIDATES or any(
        item.is_symlink() for item in values
    ):
        return None
    return tuple(sorted(values, key=str))


def _bounded_directory_entries(root: Path) -> tuple[Path, ...] | None:
    try:
        entries = tuple(
            itertools.islice(root.iterdir(), MAX_HISTORY_DIRECTORY_ENTRIES + 1)
        )
    except OSError:
        return None
    return None if len(entries) > MAX_HISTORY_DIRECTORY_ENTRIES else entries


def _file_sha256(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(64 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError:
        return ""
