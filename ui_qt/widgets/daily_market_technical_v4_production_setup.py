"""為 full-N v4 研究產製建立明示、固定來源的使用者請求。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Literal, NoReturn, Protocol, cast
from zoneinfo import ZoneInfo

from app_module.daily_market_technical_universe_v4_catalog import (
    DailyMarketTechnicalUniverseV4Catalog,
    DailyMarketTechnicalUniverseV4CatalogEntry,
)
from app_module.daily_market_technical_universe_v4_producer import (
    DailyMarketTechnicalUniverseV4ProductionRequest,
)
from app_module.daily_market_technical_universe_v4_store import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_PLAN_BYTES,
    DailyMarketTechnicalUniverseV4Cohort,
)
from app_module.personal_data_paths import to_internal_io_path
from app_module.rule_research_sample_capture import ResearchCaptureWriteScope
from data_module.config import TWStockConfig


DAILY_MARKET_TECHNICAL_V4_POPULATION_SETTINGS_SCHEMA = (
    "daily-market-technical-universe-v4-population-settings.v1"
)
_POPULATION_SETTINGS_KEYS = frozenset({
    "schema_version",
    "universe_id",
    "population_version",
    "decision_date",
    "raw_stock_codes",
    "excluded_stock_codes",
    "exclusion_reasons",
})
_TAIPEI = ZoneInfo("Asia/Taipei")
_MINIMUM_CUTOFF = time(16, 0)


class DailyMarketTechnicalV4ProductionSetupError(ValueError):
    """產製設定的穩定錯誤碼，可安全顯示在每日研究頁。"""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        cause_code: str | None = None,
    ) -> None:
        self.code = code
        self.cause_code = cause_code
        super().__init__(message)


class DailyMarketTechnicalV4ProductionSetupCancelled(
    DailyMarketTechnicalV4ProductionSetupError
):
    """使用者取消設定；尚未將請求送入背景產製。"""

    def __init__(self) -> None:
        super().__init__(
            "technical_universe_v4_setup_cancelled",
            "設定已取消；產製請求尚未送出。",
        )


class ProductionSetupDialogs(Protocol):
    """可由 Qt 對話框或隔離測試提供的同步使用者互動介面。"""

    def choose_population_settings_file(self, parent: object | None) -> Path | None:
        """選擇一份明示的母體設定 JSON。"""

    def request_decision_cutoff(
        self, parent: object | None, *, decision_date: date
    ) -> str | datetime | None:
        """要求使用者明確輸入台北時間的決策截止時間。"""

    def confirm_source_database(
        self, parent: object | None, *, source_database: Path
    ) -> bool:
        """確認本次唯讀來源資料庫路徑。"""

    def confirm_production(
        self, parent: object | None, *, summary: ProductionSetupSummary
    ) -> bool:
        """在顯示完整母體摘要後確認送出請求。"""


@dataclass(frozen=True, slots=True)
class ProductionSetupSummary:
    """送出前顯示的完整分母、排除、重複與固定路徑摘要。"""

    mode: Literal["new", "resume"]
    cohort: DailyMarketTechnicalUniverseV4Cohort | None
    source_database: Path
    configured_output_root: Path
    store_output_root: Path
    decision_cutoff: datetime | None
    selected_entry: DailyMarketTechnicalUniverseV4CatalogEntry | None = None

    def to_text(self) -> str:
        """以純文字呈現已知摘要，並清楚標出尚未 canonical／strict 核驗的路徑。"""

        lines = [
            "模式：新產製" if self.mode == "new" else "模式：續跑所選保存版本",
            f"TWStockConfig.db_file 設定值（待背景來源核驗）：{self.source_database}",
            (
                "TWStockConfig.output_root 設定值（待背景 scope 核驗）："
                f"{self.configured_output_root}"
            ),
            (
                "預計研究 store 路徑（尚未 canonical 核驗）："
                f"{self.store_output_root}"
            ),
        ]
        if self.cohort is not None:
            cohort = self.cohort
            repeated_count = cohort.raw_stock_code_count - len(cohort.declared_stock_codes)
            duplicates = "、".join(
                f"{code}（出現 {occurrences} 次）"
                for code, occurrences in cohort.duplicate_stock_codes
            ) or "無"
            excluded = "\n".join(
                f"{code}：{reason}"
                for code, reason in cohort.exclusion_reasons
            ) or "無"
            denominator = "、".join(cohort.declared_stock_codes) or "（空母體）"
            if self.decision_cutoff is None:
                raise ValueError("new_setup_summary_cutoff_missing")
            lines.extend((
                f"母體：{cohort.universe_id}；版本：{cohort.population_version}",
                f"決策日期：{cohort.decision_date.isoformat()}",
                (
                    f"原始列數：{cohort.raw_stock_code_count}；去重後完整分母："
                    f"{len(cohort.declared_stock_codes)}；重複多列：{repeated_count}"
                ),
                (
                    f"納入：{len(cohort.included_stock_codes)}；明示排除："
                    f"{len(cohort.excluded_stock_codes)}"
                ),
                f"重複代碼：{duplicates}",
                f"排除代碼與理由：\n{excluded}",
                f"完整分母股票代碼：\n{denominator}",
                (
                    "台北決策截止（新設定，背景仍會再核對）："
                    f"{self.decision_cutoff.astimezone(_TAIPEI).isoformat()}"
                ),
            ))
        else:
            entry = self.selected_entry
            if entry is None:
                raise ValueError("resume_setup_summary_entry_missing")
            counts = entry.counts
            counts_text = (
                (
                    f"metadata 分母 {counts.declared_count}、納入 {counts.included_count}、"
                    f"排除 {counts.excluded_count}、已處理 {counts.processed_count}、"
                    f"待處理 {counts.pending_count}"
                )
                if counts is not None
                else "metadata 未提供可解析的分母計數"
            )
            lines.extend((
                "所選項目目前只是一列 metadata_unverified；以下欄位尚未通過來源核驗。",
                f"metadata 狀態／收據狀態：{entry.metadata_state}／{entry.source_status}",
                f"metadata 母體：{entry.universe_id}；版本：{entry.population_version}",
                f"metadata 決策日期：{entry.decision_date}",
                counts_text,
                f"metadata population state：{entry.population_state}",
                f"固定所選收據身份：{entry.receipt_identity_sha256}",
                f"固定所選收據 bytes SHA-256：{entry.receipt_bytes_sha256}",
                (
                    "背景工作會對這一列呼叫 Catalog.read_exact，核對原來源資料庫、"
                    "scope、plan 與 receipt pins；失敗時不會呼叫 producer。"
                ),
            ))
        lines.append("此研究來源不代表可得性、PIT 資格或交易許可。")
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalV4DeferredProductionSetup:
    """GUI 確認後交給 worker 嚴格核驗、再建立 producer request 的固定設定。"""

    mode: Literal["new", "resume"]
    source_database: Path
    configured_output_root: Path
    store_output_root: Path
    summary: ProductionSetupSummary
    cohort: DailyMarketTechnicalUniverseV4Cohort | None = None
    decision_cutoff: datetime | None = None
    selected_entry: DailyMarketTechnicalUniverseV4CatalogEntry | None = None
    selected_receipt_identity_sha256: str | None = None
    selected_receipt_bytes_sha256: str | None = None

    def __post_init__(self) -> None:
        if (
            not self.source_database.is_absolute()
            or not self.configured_output_root.is_absolute()
            or self.store_output_root
            != self.configured_output_root
            / "research_snapshots"
            / "technical_universe"
            or self.summary.mode != self.mode
            or self.summary.source_database != self.source_database
            or self.summary.configured_output_root != self.configured_output_root
            or self.summary.store_output_root != self.store_output_root
        ):
            raise ValueError("production_setup_paths_or_summary_invalid")
        if self.mode == "new":
            if (
                self.cohort is None
                or self.decision_cutoff is None
                or self.summary.cohort != self.cohort
                or self.summary.decision_cutoff != self.decision_cutoff
                or self.selected_entry is not None
                or self.selected_receipt_identity_sha256 is not None
                or self.selected_receipt_bytes_sha256 is not None
            ):
                raise ValueError("new_setup_identity_invalid")
        elif self.mode == "resume":
            if (
                self.cohort is not None
                or self.decision_cutoff is not None
                or self.selected_entry is None
                or not self.selected_entry.is_selectable
                or self.summary.selected_entry != self.selected_entry
                or self.summary.cohort is not None
                or self.summary.decision_cutoff is not None
                or self.selected_receipt_identity_sha256
                != self.selected_entry.receipt_identity_sha256
                or self.selected_receipt_bytes_sha256
                != self.selected_entry.receipt_bytes_sha256
            ):
                raise ValueError("resume_setup_identity_invalid")
        else:
            raise ValueError("production_setup_mode_invalid")

    def prepare_request(
        self,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> DailyMarketTechnicalUniverseV4ProductionRequest:
        """背景嚴格驗證固定輸入；metadata exact read 只在進出前檢查取消。"""

        _check_setup_cancelled(cancel_callback)
        source_database = _canonical_source_database(self.source_database)
        _check_setup_cancelled(cancel_callback)
        scope = _research_scope_from_paths(
            self.configured_output_root,
            source_database,
        )
        _check_setup_cancelled(cancel_callback)
        store_output_root = scope.root / "technical_universe"

        cohort = self.cohort
        decision_cutoff = self.decision_cutoff
        resume_receipt_identity: str | None = None
        resume_receipt_sha256: str | None = None
        if self.mode == "resume":
            entry = self.selected_entry
            if entry is None:
                raise DailyMarketTechnicalV4ProductionSetupError(
                    "technical_universe_v4_resume_entry_missing",
                    "續跑設定沒有固定所選收據。",
                )
            if (
                entry.receipt_identity_sha256
                != self.selected_receipt_identity_sha256
                or entry.receipt_bytes_sha256 != self.selected_receipt_bytes_sha256
            ):
                raise DailyMarketTechnicalV4ProductionSetupError(
                    "technical_universe_v4_resume_selected_pin_changed",
                    "所選收據 pin 與確認時不同，未送出續跑。",
                )
            catalog = DailyMarketTechnicalUniverseV4Catalog(store_output_root)
            _check_setup_cancelled(cancel_callback)
            try:
                saved = catalog.read_exact(entry)
            except Exception as exc:
                raise DailyMarketTechnicalV4ProductionSetupError(
                    "technical_universe_v4_selected_receipt_read_failed",
                    "所選保存收據未通過原 store 嚴格核驗，未呼叫產製器。",
                    cause_code=_exception_code_for_setup(exc),
                ) from exc
            # 目前 catalog exact reader 沒有 callback；讀取中無法中斷，只在返回後丟棄晚到結果。
            _check_setup_cancelled(cancel_callback)
            _verify_selected_entry(saved, entry)
            if Path(saved.plan.source_clock.database_path) != source_database:
                raise DailyMarketTechnicalV4ProductionSetupError(
                    "technical_universe_v4_resume_source_database_mismatch",
                    "目前設定來源與所選計畫的原始資料庫不同，未呼叫產製器。",
                )
            cohort = saved.plan.cohort
            decision_cutoff = saved.plan.source_clock.decision_cutoff
            resume_receipt_identity = self.selected_receipt_identity_sha256
            resume_receipt_sha256 = self.selected_receipt_bytes_sha256

        if cohort is None or decision_cutoff is None:
            raise DailyMarketTechnicalV4ProductionSetupError(
                "technical_universe_v4_setup_identity_missing",
                "背景核驗未能建立完整母體或來源截止時間，未呼叫產製器。",
            )
        _check_setup_cancelled(cancel_callback)
        return DailyMarketTechnicalUniverseV4ProductionRequest(
            source_database=source_database,
            cohort=cohort,
            decision_cutoff=decision_cutoff,
            store_output_root=store_output_root,
            research_scope=scope,
            cancel_callback=cancel_callback,
            resume_receipt_identity_sha256=resume_receipt_identity,
            expected_resume_receipt_sha256=resume_receipt_sha256,
        )


class _DuplicateJsonKey(ValueError):
    """標記 JSON 物件內重複的鍵。"""


def _json_object_without_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey("duplicate_json_key")
        result[key] = value
    return result


def _reject_json_float(value: str) -> NoReturn:
    raise ValueError("float_forbidden")


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError("non_finite_number_forbidden")


def _reject_linked_path(path: Path) -> None:
    """拒絕設定檔路徑中的 symlink、junction 與其他 reparse point。"""

    for component in (path, *path.parents):
        try:
            info = os.lstat(to_internal_io_path(component))
        except OSError as exc:
            raise DailyMarketTechnicalV4ProductionSetupError(
                "technical_universe_v4_settings_path_unavailable",
                "無法安全讀取所選母體設定檔。",
            ) from exc
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise DailyMarketTechnicalV4ProductionSetupError(
                "technical_universe_v4_settings_path_linked",
                "母體設定檔或其路徑包含連結，已拒絕讀取。",
            )


def load_daily_market_technical_v4_population_settings(
    settings_path: str | Path,
) -> DailyMarketTechnicalUniverseV4Cohort:
    """以有界長路徑 I/O 載入固定 schema，並由正式 cohort 契約驗證分母。"""

    try:
        path = Path(settings_path).expanduser()
        if not path.is_absolute() or ".." in path.parts:
            raise DailyMarketTechnicalV4ProductionSetupError(
                "technical_universe_v4_settings_path_absolute_required",
                "母體設定檔必須使用絕對路徑。",
            )
        io_path = to_internal_io_path(path)
        _reject_linked_path(path)
        before = os.lstat(io_path)
        if not stat.S_ISREG(before.st_mode):
            raise DailyMarketTechnicalV4ProductionSetupError(
                "technical_universe_v4_settings_file_invalid",
                "母體設定必須是一般 JSON 檔案。",
            )
        if before.st_size > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_PLAN_BYTES:
            raise DailyMarketTechnicalV4ProductionSetupError(
                "technical_universe_v4_settings_file_too_large",
                "母體設定超過 56 MiB 上限。",
            )

        with open(io_path, "rb") as handle:
            opened = os.fstat(handle.fileno())
            raw = handle.read(DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_PLAN_BYTES + 1)
            after_open = os.fstat(handle.fileno())
        after_path = os.lstat(io_path)
        _reject_linked_path(path)
        expected_signature = _file_signature(before)
        if (
            _file_signature(opened) != expected_signature
            or _file_signature(after_open) != expected_signature
            or _file_signature(after_path) != expected_signature
            or len(raw) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_PLAN_BYTES
        ):
            raise DailyMarketTechnicalV4ProductionSetupError(
                "technical_universe_v4_settings_changed_during_read",
                "讀取期間母體設定檔發生變動，已拒絕使用。",
            )
        payload_text = raw.decode("utf-8", errors="strict")
        payload = json.loads(
            payload_text,
            object_pairs_hook=_json_object_without_duplicate_keys,
            parse_float=_reject_json_float,
            parse_constant=_reject_json_constant,
        )
    except DailyMarketTechnicalV4ProductionSetupError:
        raise
    except _DuplicateJsonKey as exc:
        raise DailyMarketTechnicalV4ProductionSetupError(
            "technical_universe_v4_settings_duplicate_key",
            "母體設定含重複 JSON 欄位，已拒絕讀取。",
        ) from exc
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        code = (
            "technical_universe_v4_settings_float_forbidden"
            if "float_forbidden" in str(exc)
            else "technical_universe_v4_settings_json_invalid"
        )
        message = (
            "母體設定不得包含浮點數、NaN 或 Infinity。"
            if code.endswith("float_forbidden")
            else "母體設定不是有效的 UTF-8 JSON。"
        )
        raise DailyMarketTechnicalV4ProductionSetupError(code, message) from exc

    if not isinstance(payload, dict) or set(payload) != _POPULATION_SETTINGS_KEYS:
        raise DailyMarketTechnicalV4ProductionSetupError(
            "technical_universe_v4_settings_schema_invalid",
            "母體設定欄位與固定 schema 不符。",
        )
    if payload.get("schema_version") != DAILY_MARKET_TECHNICAL_V4_POPULATION_SETTINGS_SCHEMA:
        raise DailyMarketTechnicalV4ProductionSetupError(
            "technical_universe_v4_settings_schema_version_invalid",
            "母體設定 schema 版本不支援。",
        )

    universe_id = payload.get("universe_id")
    population_version = payload.get("population_version")
    decision_date_text = payload.get("decision_date")
    raw_stock_codes = payload.get("raw_stock_codes")
    excluded_stock_codes = payload.get("excluded_stock_codes")
    exclusion_reasons = payload.get("exclusion_reasons")
    if (
        not isinstance(universe_id, str)
        or not isinstance(population_version, str)
        or not isinstance(decision_date_text, str)
        or not isinstance(raw_stock_codes, list)
        or any(not isinstance(code, str) for code in raw_stock_codes)
        or not isinstance(excluded_stock_codes, list)
        or any(not isinstance(code, str) for code in excluded_stock_codes)
        or not isinstance(exclusion_reasons, dict)
        or any(
            not isinstance(code, str) or not isinstance(reason, str)
            for code, reason in exclusion_reasons.items()
        )
    ):
        raise DailyMarketTechnicalV4ProductionSetupError(
            "technical_universe_v4_settings_field_type_invalid",
            "母體設定的欄位型別不符；股票代碼與理由都必須是字串。",
        )
    try:
        decision_date = date.fromisoformat(decision_date_text)
        if decision_date.isoformat() != decision_date_text:
            raise ValueError("date_not_canonical")
        return DailyMarketTechnicalUniverseV4Cohort.create(
            universe_id=universe_id,
            population_version=population_version,
            decision_date=decision_date,
            raw_stock_codes=cast(Sequence[str], raw_stock_codes),
            excluded_stock_codes=cast(Sequence[str], excluded_stock_codes),
            exclusion_reasons=cast(Mapping[str, str], exclusion_reasons),
        )
    except (TypeError, ValueError) as exc:
        raise DailyMarketTechnicalV4ProductionSetupError(
            "technical_universe_v4_settings_cohort_invalid",
            "母體日期、代碼、排除清單或理由未通過完整母體契約。",
        ) from exc


def parse_daily_market_technical_v4_decision_cutoff(
    value: str | datetime,
    *,
    decision_date: date,
) -> datetime:
    """要求明示的 aware cutoff 與母體同日，並符合台北 16:00 guard。"""

    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
        if not isinstance(parsed, datetime) or parsed.utcoffset() != timedelta(hours=8):
            raise ValueError("timezone_must_be_taipei_offset")
        local = parsed.astimezone(_TAIPEI)
        if local.date() != decision_date or local.time() < _MINIMUM_CUTOFF:
            raise ValueError("cutoff_date_or_time_invalid")
        return local
    except (TypeError, ValueError, OverflowError) as exc:
        raise DailyMarketTechnicalV4ProductionSetupError(
            "technical_universe_v4_setup_cutoff_invalid",
            "截止時間須明確使用母體決策日期的台北時間，且不早於 16:00。",
        ) from exc


def make_daily_market_technical_v4_production_request_factory(
    config: TWStockConfig,
    *,
    parent: object | None = None,
    dialogs: ProductionSetupDialogs | None = None,
) -> Callable[
    [DailyMarketTechnicalUniverseV4CatalogEntry | None],
    DailyMarketTechnicalUniverseV4ProductionRequest,
]:
    """相容舊呼叫端；新的 UI 應將 deferred setup 交給背景 worker 核驗。"""

    deferred_factory = make_daily_market_technical_v4_deferred_setup_factory(
        config,
        parent=parent,
        dialogs=dialogs,
    )

    def build_request(
        entry: DailyMarketTechnicalUniverseV4CatalogEntry | None,
    ) -> DailyMarketTechnicalUniverseV4ProductionRequest:
        return deferred_factory(entry).prepare_request()

    return build_request


def make_daily_market_technical_v4_deferred_setup_factory(
    config: TWStockConfig,
    *,
    parent: object | None = None,
    dialogs: ProductionSetupDialogs | None = None,
) -> Callable[
    [DailyMarketTechnicalUniverseV4CatalogEntry | None],
    DailyMarketTechnicalV4DeferredProductionSetup,
]:
    """只在 GUI 收集設定；完整來源與 selected receipt 核驗留給背景 worker。"""

    active_dialogs: ProductionSetupDialogs = dialogs or _QtProductionSetupDialogs()

    def build_setup(
        entry: DailyMarketTechnicalUniverseV4CatalogEntry | None,
    ) -> DailyMarketTechnicalV4DeferredProductionSetup:
        _assert_ui_main_thread()
        if entry is None:
            settings_path = active_dialogs.choose_population_settings_file(parent)
            if settings_path is None:
                raise DailyMarketTechnicalV4ProductionSetupCancelled()
            cohort = load_daily_market_technical_v4_population_settings(settings_path)
            cutoff_value = active_dialogs.request_decision_cutoff(
                parent,
                decision_date=cohort.decision_date,
            )
            if cutoff_value is None:
                raise DailyMarketTechnicalV4ProductionSetupCancelled()
            decision_cutoff = parse_daily_market_technical_v4_decision_cutoff(
                cutoff_value,
                decision_date=cohort.decision_date,
            )
            selected_entry = None
        else:
            if (
                not isinstance(entry, DailyMarketTechnicalUniverseV4CatalogEntry)
                or not entry.is_selectable
            ):
                raise DailyMarketTechnicalV4ProductionSetupError(
                    "technical_universe_v4_catalog_entry_not_selectable",
                    "所選保存版本沒有可核驗的完整收據 pin。",
                )
            selected_entry = entry
            cohort = None
            decision_cutoff = None

        source_database = _configured_source_database_for_gui(config)
        configured_output_root = _configured_output_root_for_gui(config)
        if not active_dialogs.confirm_source_database(
            parent,
            source_database=source_database,
        ):
            raise DailyMarketTechnicalV4ProductionSetupCancelled()
        store_output_root = (
            configured_output_root / "research_snapshots" / "technical_universe"
        )
        summary = ProductionSetupSummary(
            mode="new" if entry is None else "resume",
            cohort=cohort,
            source_database=source_database,
            configured_output_root=configured_output_root,
            store_output_root=store_output_root,
            decision_cutoff=decision_cutoff,
            selected_entry=selected_entry,
        )
        if not active_dialogs.confirm_production(parent, summary=summary):
            raise DailyMarketTechnicalV4ProductionSetupCancelled()

        return DailyMarketTechnicalV4DeferredProductionSetup(
            mode="new" if entry is None else "resume",
            source_database=source_database,
            configured_output_root=configured_output_root,
            store_output_root=store_output_root,
            summary=summary,
            cohort=cohort,
            decision_cutoff=decision_cutoff,
            selected_entry=selected_entry,
            selected_receipt_identity_sha256=(
                selected_entry.receipt_identity_sha256
                if selected_entry is not None
                else None
            ),
            selected_receipt_bytes_sha256=(
                selected_entry.receipt_bytes_sha256
                if selected_entry is not None
                else None
            ),
        )

    return build_setup


def _configured_source_database_for_gui(config: TWStockConfig) -> Path:
    """凍結設定所指的絕對路徑，不在 GUI 查檔或宣稱它已 canonical。"""

    try:
        raw_path = Path(config.db_file).expanduser()
        if not raw_path.is_absolute():
            raw_path = Path(os.path.abspath(raw_path))
        return raw_path
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalV4ProductionSetupError(
            "technical_universe_v4_setup_source_database_path_invalid",
            "TWStockConfig.db_file 不是可用的路徑設定。",
        ) from exc


def _configured_output_root_for_gui(config: TWStockConfig) -> Path:
    """回傳顯示用絕對設定路徑，不在 GUI 建立目錄或執行 scope 核驗。"""

    try:
        configured_output_root = Path(config.output_root).expanduser()
        if not configured_output_root.is_absolute():
            configured_output_root = Path(os.path.abspath(configured_output_root))
        return configured_output_root
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalV4ProductionSetupError(
            "technical_universe_v4_setup_output_path_invalid",
            "TWStockConfig.output_root 不是可用的路徑設定。",
        ) from exc


def _canonical_source_database(source_database: Path) -> Path:
    try:
        canonical = _canonical_path(source_database, strict=True)
        if canonical != source_database or not os.path.isfile(
            to_internal_io_path(canonical)
        ):
            raise OSError("source_database_path_not_canonical_or_regular")
        return canonical
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalV4ProductionSetupError(
            "technical_universe_v4_setup_source_database_unavailable",
            "背景核驗時來源資料庫不存在、路徑非 canonical 或不是一般檔案。",
        ) from exc


def _research_scope_from_paths(
    configured_output_root: Path,
    source_database: Path,
) -> ResearchCaptureWriteScope:
    try:
        scope = ResearchCaptureWriteScope(configured_output_root, source_database)
        scope.validate()
        return scope
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalV4ProductionSetupError(
            "technical_universe_v4_setup_research_scope_invalid",
            "TWStockConfig 的研究保存根或來源隔離設定未通過檢查。",
        ) from exc


def _check_setup_cancelled(
    cancel_callback: Callable[[], bool] | None,
) -> None:
    """在可控邊界檢查 worker 取消；exact catalog read 中間無法中斷。"""

    if cancel_callback is not None and cancel_callback():
        raise DailyMarketTechnicalV4ProductionSetupCancelled()


def _exception_code_for_setup(error: BaseException) -> str:
    """保留 strict reader 的穩定錯誤碼供診斷，不暴露原始例外文字。"""

    current: BaseException | None = error
    while current is not None:
        code = getattr(current, "code", None)
        if isinstance(code, str) and code:
            return code
        current = current.__cause__
    return type(error).__name__


def _verify_selected_entry(
    saved: object,
    entry: DailyMarketTechnicalUniverseV4CatalogEntry,
) -> None:
    """逐欄對照 strict read 與確認時 metadata；不把 metadata 當驗證結果。"""

    plan = getattr(saved, "plan", None)
    receipt = getattr(saved, "receipt", None)
    counts = getattr(saved, "counts", None)
    if plan is None or receipt is None or counts is None:
        raise DailyMarketTechnicalV4ProductionSetupError(
            "technical_universe_v4_selected_receipt_state_invalid",
            "原 store strict reader 未回傳完整計畫、收據與計數。",
        )
    try:
        plan_body = plan.to_dict()
        cohort = plan.cohort
        relative_path = (
            f"generations/{plan.generation_identity_sha256}/receipts/"
            f"{receipt.identity_sha256}.json"
        )
        matches = (
            entry.generation_name == plan.generation_identity_sha256,
            entry.generation_identity_sha256 == plan.generation_identity_sha256,
            entry.relative_path == relative_path,
            entry.plan_identity_sha256 == plan.identity_sha256,
            entry.plan_bytes_sha256
            == hashlib.sha256(plan.to_json().encode("utf-8")).hexdigest(),
            entry.receipt_identity_sha256 == receipt.identity_sha256,
            entry.receipt_bytes_sha256 == receipt.content_sha256,
            entry.source_status == receipt.status,
            entry.source_clock_identity_sha256
            == plan_body["source_clock_identity_sha256"],
            entry.method_contracts_sha256 == plan_body["method_contracts_sha256"],
            entry.decision_date == cohort.decision_date,
            entry.universe_id == cohort.universe_id,
            entry.population_version == cohort.population_version,
            entry.cohort_identity_sha256 == cohort.cohort_identity_sha256,
            entry.counts == counts,
            entry.population_state == cohort.population_state,
        )
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalV4ProductionSetupError(
            "technical_universe_v4_selected_receipt_state_invalid",
            "原 store strict reader 的計畫欄位未通過固定契約。",
            cause_code=_exception_code_for_setup(exc),
        ) from exc
    if not all(matches):
        raise DailyMarketTechnicalV4ProductionSetupError(
            "technical_universe_v4_selected_entry_metadata_mismatch",
            "strict read 與使用者所選 metadata 的固定欄位不符，未呼叫產製器。",
        )


def _file_signature(info: os.stat_result) -> tuple[int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _canonical_path(path: Path, *, strict: bool) -> Path:
    """透過原生長路徑介面解析後移除 Windows 內部 I/O 前綴。"""

    resolved = os.path.realpath(to_internal_io_path(path), strict=strict)
    if os.name == "nt":
        folded = resolved.casefold()
        if folded.startswith("\\\\?\\unc\\"):
            resolved = "\\\\" + resolved[len("\\\\?\\unc\\"):]
        elif resolved.startswith("\\\\?\\"):
            resolved = resolved[4:]
    return Path(resolved)


def _assert_ui_main_thread() -> None:
    """確保設定與所有同步對話框都由 Qt GUI 主執行緒呼叫。"""

    try:
        from PySide6.QtCore import QCoreApplication, QThread
    except ImportError as exc:
        raise DailyMarketTechnicalV4ProductionSetupError(
            "technical_universe_v4_setup_qt_unavailable",
            "無法載入 Qt，未建立產製請求。",
        ) from exc
    application = QCoreApplication.instance()
    if application is None:
        raise DailyMarketTechnicalV4ProductionSetupError(
            "technical_universe_v4_setup_qt_application_missing",
            "每日研究設定需要已啟動的 Qt 應用程式。",
        )
    if QThread.currentThread() != application.thread():
        raise DailyMarketTechnicalV4ProductionSetupError(
            "technical_universe_v4_setup_must_run_on_ui_thread",
            "來源設定對話框只能由 Qt 主執行緒開啟。",
        )


class _QtProductionSetupDialogs:
    """使用同步 Qt 對話框收集設定；不啟動背景工作或改寫全域設定。"""

    def choose_population_settings_file(self, parent: object | None) -> Path | None:
        from PySide6.QtWidgets import QFileDialog, QWidget

        file_name, _selected_filter = QFileDialog.getOpenFileName(
            cast(QWidget | None, parent),
            "選擇完整母體設定",
            "",
            "JSON 設定檔 (*.json);;所有檔案 (*)",
        )
        return Path(file_name) if file_name else None

    def request_decision_cutoff(
        self,
        parent: object | None,
        *,
        decision_date: date,
    ) -> str | None:
        from PySide6.QtWidgets import QInputDialog, QWidget

        value, accepted = QInputDialog.getText(
            cast(QWidget | None, parent),
            "設定台北決策截止",
            "請輸入同一決策日期的台北時間，且不早於 16:00：",
            text=f"{decision_date.isoformat()}T16:00:00+08:00",
        )
        return value if accepted else None

    def confirm_source_database(
        self,
        parent: object | None,
        *,
        source_database: Path,
    ) -> bool:
        from PySide6.QtWidgets import QMessageBox, QWidget

        dialog = QMessageBox(cast(QWidget | None, parent))
        dialog.setWindowTitle("確認唯讀來源資料庫")
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText("本次設定將嘗試使用以下來源資料庫，尚待背景核驗：")
        dialog.setInformativeText(f"{source_database}\n\n核驗前不會建立產製請求。")
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )
        dialog.setDefaultButton(QMessageBox.StandardButton.Cancel)
        dialog.button(QMessageBox.StandardButton.Yes).setText("使用此來源")
        return dialog.exec() == QMessageBox.StandardButton.Yes

    def confirm_production(
        self,
        parent: object | None,
        *,
        summary: ProductionSetupSummary,
    ) -> bool:
        from PySide6.QtWidgets import (
            QDialog,
            QDialogButtonBox,
            QLabel,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )

        dialog = QDialog(cast(QWidget | None, parent))
        dialog.setWindowTitle("確認 full-N v4 研究設定")
        dialog.setMinimumSize(760, 560)
        layout = QVBoxLayout(dialog)
        heading = QLabel("請核對完整分母、排除清單、來源資料庫與截止時間。")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        details = QTextEdit(dialog)
        details.setReadOnly(True)
        details.setPlainText(summary.to_text())
        layout.addWidget(details, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        confirm_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if confirm_button is not None:
            confirm_button.setText("確認送出產製")
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setText("取消")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        return dialog.exec() == QDialog.DialogCode.Accepted


__all__ = [
    "DAILY_MARKET_TECHNICAL_V4_POPULATION_SETTINGS_SCHEMA",
    "DailyMarketTechnicalV4ProductionSetupCancelled",
    "DailyMarketTechnicalV4ProductionSetupError",
    "DailyMarketTechnicalV4DeferredProductionSetup",
    "ProductionSetupDialogs",
    "ProductionSetupSummary",
    "load_daily_market_technical_v4_population_settings",
    "make_daily_market_technical_v4_deferred_setup_factory",
    "make_daily_market_technical_v4_production_request_factory",
    "parse_daily_market_technical_v4_decision_cutoff",
]
