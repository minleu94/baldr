"""
數據更新服務 (Update Service)
提供數據更新的業務邏輯
"""

import subprocess
import os
import sys
import sqlite3
import hashlib
from pathlib import Path
from typing import Dict ,Any ,Optional ,List ,Callable, Sequence, TYPE_CHECKING
from datetime import date, datetime, timedelta, timezone

import app_module.update_data_normalization as update_data_normalization
from app_module.update_service_status_support import (
    compose_sqlite_status_read_model,
    FreshnessReceiptBinding,
)
from app_module.dtos.update_loop_dtos import (
    UpdateStatusSnapshotDTO,
    enrich_status_mapping,
)
from app_module.update_daily_output import parse_daily_update_output
from app_module.sqlite_read_only import ReadOnlySQLiteManager
from data_module.market_data_integrity import (
is_valid_daily_price_frame ,
is_weekend_date_key ,
normalize_market_index_frame ,
official_twse_session_exists ,
)
from data_module.phase3c_backfill_runner import configured_candidate_db_path
from data_module.monthly_revenue_snapshot_selection import (
    inspect_monthly_revenue_snapshot,
    select_latest_monthly_revenue_snapshot,
)
from data_module.monthly_revenue_availability_candidate import (
    inspect_monthly_revenue_availability_candidate,
)
from data_module.daily_price_source_guard import (
    AGGREGATE_SOURCE_VERSION,
    DailyPriceSourceError,
    aggregate_receipt_path,
    configured_daily_price_dirs,
    discover_daily_price_csvs,
    validate_aggregate_receipt_payload,
    validate_daily_price_frame_date,
)
from data_module.daily_price_revision_write_guard import (
    prepare_daily_price_revision_frame,
    validate_excluded_price_frame,
)
from data_module.formal_market_revision import validate_market_replacement
from data_module.official_trading_calendar import (
    OfficialTradingCalendar,
    OfficialTradingCalendarError,
)

if TYPE_CHECKING:
    from data_module.daily_source_snapshot import (
        DailySourceTransportCapture, DailySourceUseAcceptance, DailySourceUseScope,
    )
    from app_module.monthly_revenue_daily_snapshot_update import (
        DailyMonthlyRevenueSnapshotReadStatus, DailyMonthlyRevenueSnapshotUpdateResult,
    )


_TPEX_FAILURE_MESSAGE_MAX_CHARS = 512


def _monthly_revenue_status_today() -> str:
    """回傳月營收可得性狀態使用的台灣市場日期。

    更新頁可能在北美時區執行；使用台灣市場日可避免台灣已進入下一日、
    但 host 仍停留前一日（或反過來）時，把 availability 判定錯一天。
    """
    try:
        from app_module.paper_portfolio_time import taiwan_market_today

        return taiwan_market_today().isoformat()
    except Exception:
        return datetime.now().date().isoformat()


def _expected_latest_monthly_revenue_period(reference_date: str) -> str | None:
    """依 MOPS 通常每月 10 日前後公告節奏推算應檢查的最新期別。

    這只是一個 UI／資料新鮮度提示，不會把推算期別當成官方公告證據，也
    不會讓正式回填跳過 availability mapping。月初（1--9 日）預期前兩個
    月，10 日起預期前一個月；例如 2026-09-03 對應 2026-07。
    """
    try:
        current = date.fromisoformat(str(reference_date).strip()[:10])
    except (TypeError, ValueError):
        return None
    months_back = 2 if current.day < 10 else 1
    month_index = current.year * 12 + (current.month - 1) - months_back
    year, month_zero = divmod(month_index, 12)
    return f"{year:04d}-{month_zero + 1:02d}"


def _emit_update_progress(
    callback: Optional[Callable[[str, int], None]],
    message: str,
    percentage: int,
) -> None:
    """將下載觀測回傳給 UI；callback 失敗不得改變資料更新結果。"""
    if callback is None:
        return
    try:
        callback(message, max(0, min(100, int(percentage))))
    except Exception:
        # 進度是觀測邊界，不應因 UI／Qt callback 例外中止背景更新。
        return


def _is_cancel_requested(callback: Optional[Callable[[], bool]]) -> bool:
    """安全讀取合作式取消旗標；取消觀測失敗不應破壞資料更新。"""
    if callback is None:
        return False
    try:
        return bool(callback())
    except Exception:
        return False


def _write_technical_indicator_publications(
    conn,
    frame,
    *,
    replace_market: bool = False,
    database_path: Optional[Path] = None,
    raw_alias_prevalidated: bool = False,
    raw_alias_context: Any = None,
) -> int:
    """在呼叫端交易中只寫已驗證發布列，選擇性原子替換全市場資料。"""
    import pandas as pd

    if frame is None or frame.empty:
        return 0
    if database_path is None and raw_alias_context is not None:
        database_path = raw_alias_context.database_path
    if database_path is None:
        database_path = next(
            (Path(row[2]) for row in conn.execute("PRAGMA database_list") if row[1] == "main" and row[2]),
            None,
        )
    context_was_supplied = raw_alias_context is not None
    if database_path is not None:
        from data_module.formal_technical_raw_alias_repair import (
            create_raw_alias_writer_context,
            normalize_raw_alias_values_for_storage,
        )

        if raw_alias_context is None:
            raw_alias_context = create_raw_alias_writer_context(database_path)
    raw_alias_active = raw_alias_context is not None
    must_prevalidate = not raw_alias_prevalidated or not context_was_supplied
    if database_path is not None and must_prevalidate:
        from data_module.formal_technical_raw_alias_repair import (
            prepare_raw_alias_upsert_frame,
            validate_raw_alias_replacement,
        )

        if raw_alias_active and replace_market:
            validate_raw_alias_replacement(
                database_path,
                _technical_frame_records(frame),
                replace_all=True,
                writer_context=raw_alias_context,
            )
        elif raw_alias_active:
            frame = prepare_raw_alias_upsert_frame(
                database_path,
                frame,
                writer_context=raw_alias_context,
            )
    if raw_alias_context is not None:
        frame = normalize_raw_alias_values_for_storage(frame)
    required = {"日期", "證券代號"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"SQLite 技術指標發布缺少鍵欄位：{sorted(missing)}")
    if frame.duplicated(subset=["證券代號", "日期"]).any():
        raise ValueError("SQLite 技術指標發布含重複股票／日期鍵")

    columns = list(frame.columns)
    quoted_columns = ", ".join(f'"{str(column).replace(chr(34), chr(34) * 2)}"' for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    mutable_columns = [
        column for column in columns if column not in {"日期", "證券代號"}
    ]
    if mutable_columns:
        update_clause = ", ".join(
            f'"{str(column).replace(chr(34), chr(34) * 2)}" = '
            f'excluded."{str(column).replace(chr(34), chr(34) * 2)}"'
            for column in mutable_columns
        )
        conflict_clause = (
            'ON CONFLICT("證券代號", "日期") DO UPDATE SET ' + update_clause
        )
    else:
        conflict_clause = 'ON CONFLICT("證券代號", "日期") DO NOTHING'
    statement = (
        f'INSERT INTO "technical_indicators" '
        f'({quoted_columns}) VALUES ({placeholders}) {conflict_clause}'
    )
    values = []
    for row in frame.itertuples(index=False, name=None):
        normalized: list[Any] = []
        for value in row:
            if pd.isna(value):
                normalized.append(None)
            elif hasattr(value, "item"):
                normalized.append(value.item())
            else:
                normalized.append(value)
        values.append(tuple(normalized))

    # 逐列轉成 SQLite bind values 可能耗時；metadata bytes 必須在 mutation 前重驗。
    if raw_alias_context is not None:
        raw_alias_context.ensure_current(database_path)

    if replace_market:
        conn.execute('DELETE FROM "technical_indicators"')
    conn.executemany(statement, values)
    return len(values)


def _technical_frame_records(frame):
    columns = [str(column) for column in frame.columns]
    for values in frame.itertuples(index=False, name=None):
        yield dict(zip(columns, values, strict=True))


def _validate_technical_raw_alias_frame(
    database_path: Path,
    frame,
    *,
    replace_all: bool = False,
    replace_dates: bool = False,
    raw_alias_context: Any = None,
) -> None:
    if frame is None or frame.empty:
        return
    validation_frame = frame
    rename_columns = {}
    if "證券代號" not in validation_frame.columns:
        symbol_column = next(
            (
                column
                for column in ("股票代號", "stock_id", "stock_code")
                if column in validation_frame.columns
            ),
            None,
        )
        if symbol_column is not None:
            rename_columns[symbol_column] = "證券代號"
    if "日期" not in validation_frame.columns:
        date_column = next(
            (
                column
                for column in ("date", "trade_date", "trading_date", "Date")
                if column in validation_frame.columns
            ),
            None,
        )
        if date_column is not None:
            rename_columns[date_column] = "日期"
    if rename_columns:
        validation_frame = validation_frame.rename(columns=rename_columns)
    from data_module.formal_technical_raw_alias_repair import (
        validate_raw_alias_replacement,
    )

    validate_raw_alias_replacement(
        database_path,
        _technical_frame_records(validation_frame),
        replace_all=replace_all,
        replace_dates=replace_dates,
        writer_context=raw_alias_context,
    )


def _preflight_and_ensure_technical_indicator_schema(
    db: Any,
    frame: Any,
    *,
    replace_all: bool,
    raw_alias_context: Any = None,
) -> tuple[Any, Any]:
    """先核對最新 raw-alias marker，再允許 technical schema mutation。"""

    from data_module.formal_technical_raw_alias_repair import (
        create_raw_alias_writer_context,
        prepare_raw_alias_upsert_frame,
        validate_raw_alias_replacement,
    )

    database_path = Path(db.db_path)
    if raw_alias_context is None:
        raw_alias_context = create_raw_alias_writer_context(database_path)
    if raw_alias_context is not None:
        if replace_all:
            validate_raw_alias_replacement(
                database_path,
                _technical_frame_records(frame),
                replace_all=True,
                writer_context=raw_alias_context,
            )
        else:
            frame = prepare_raw_alias_upsert_frame(
                database_path,
                frame,
                writer_context=raw_alias_context,
            )

    db.ensure_columns("technical_indicators", list(frame.columns))
    return frame, raw_alias_context


def _assert_technical_raw_aliases_unchanged(original, computed) -> None:
    from data_module.formal_technical_raw_alias_repair import (
        ALIASES,
        RawAliasRepairError,
        _same_numeric,
    )

    missing = [name for name in ALIASES if name not in original.columns or name not in computed.columns]
    if missing:
        raise RawAliasRepairError(f"技術指標計算結果省略受保護六欄：{missing}")
    if len(original) != len(computed):
        raise RawAliasRepairError("技術指標計算結果與已核驗輸入列數不同")
    for name in ALIASES:
        left = original[name].reset_index(drop=True)
        right = computed[name].reset_index(drop=True)
        if any(
            not _same_numeric(a, b, name)
            for a, b in zip(left, right, strict=True)
        ):
            raise RawAliasRepairError(f"技術指標計算結果改動已核准日價欄位：{name}")


def _daily_price_symbol_universe(database_path: Path) -> set[str]:
    """只接受 daily_prices 已有代號，不讓指標 CSV 擴張商品 universe。"""

    import sqlite3

    path = database_path.resolve(strict=True)
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=30)
    try:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "daily_prices" not in tables:
            raise ValueError("raw alias 修訂啟用，但 daily_prices 不存在；停止技術指標重建")
        columns = {
            str(row[1])
            for row in connection.execute('PRAGMA table_info("daily_prices")')
        }
        symbol_column = next(
            (
                name
                for name in ("證券代號", "股票代號", "stock_code", "stock_id")
                if name in columns
            ),
            None,
        )
        if symbol_column is None:
            raise ValueError("daily_prices 缺少證券代號欄；停止技術指標重建")
        symbols = {
            update_data_normalization.stock_code_key(row[0])
            for row in connection.execute(
                f'SELECT DISTINCT "{symbol_column}" FROM daily_prices '
                f'WHERE "{symbol_column}" IS NOT NULL'
            )
        }
    finally:
        connection.close()
    symbols.discard("")
    if not symbols:
        raise ValueError("daily_prices 證券代號 universe 為空；停止技術指標重建")
    return symbols


def _can_replace_full_technical_market(
    *,
    force_all: bool,
    target_stock: Optional[str],
    requested_start_date: Optional[str],
    recompute_currentity: bool,
    cancelled: bool,
    success_count: int,
    fail_count: int,
    insufficient_count: int,
    total_stocks: int,
    updated_stocks: List[str],
) -> bool:
    """只允許完整且未取消的全市場明確重算執行表級替換。"""
    return bool(
        force_all
        and target_stock is None
        and requested_start_date is None
        and not recompute_currentity
        and not cancelled
        and success_count == total_stocks
        and fail_count == 0
        and insufficient_count == 0
        and len(set(updated_stocks)) == total_stocks
    )


def _merge_partial_technical_publications(existing, publication):
    """以股票／日期精確合併局部彙總 CSV，保留未提供欄位與其他 keys。"""
    import pandas as pd

    from analysis_module.technical_analysis.technical_date_support import (
        safe_convert_technical_dates,
    )

    required = ["日期", "證券代號"]
    for label, frame in (("既有彙總", existing), ("本輪發布", publication)):
        missing = [column for column in required if column not in frame.columns]
        if missing:
            raise ValueError(f"{label}缺少技術指標鍵欄位：{missing}")

    old = existing.copy()
    new = publication.copy()
    for frame in (old, new):
        normalized_dates = pd.to_datetime(
            safe_convert_technical_dates(frame["日期"]), errors="coerce"
        )
        if normalized_dates.isna().any():
            raise ValueError("彙總技術指標 CSV 含無效日期")
        frame["日期"] = normalized_dates.dt.strftime("%Y-%m-%d")
        frame["證券代號"] = frame["證券代號"].astype(str).str.strip().str.zfill(4)

    if new.duplicated(subset=required).any():
        raise ValueError("本輪技術指標彙總發布含重複股票／日期鍵")
    old = old.drop_duplicates(subset=required, keep="last")
    old_indexed = old.set_index(required)
    new_indexed = new.set_index(required)
    index = old_indexed.index.union(new_indexed.index)
    combined = old_indexed.reindex(index)
    for column in new_indexed.columns:
        if column not in combined.columns:
            combined[column] = pd.NA
        combined.loc[new_indexed.index, column] = new_indexed[column]
    return (
        combined.reset_index()
        .sort_values(required, kind="stable")
        .reset_index(drop=True)
    )


class UpdateService :
    """數據更新服務類"""

    def __init__ (
        self,
        config,
        *,
        monthly_revenue_snapshot_candidate_path: Optional[str | Path] = None,
        monthly_revenue_availability_candidate_path: Optional[str | Path] = None,
    ):
        """初始化數據更新服務

        Args:
            config: TWStockConfig 實例
        """
        self .config =config
        self .project_root =Path (__file__ ).parent .parent
        self .scripts_dir =self .project_root /'scripts'
        # 最近一次 daily_data 來源選擇的唯讀診斷；不把 mtime 當成 custody 證據。
        self._last_daily_source_selection: Dict[str, Any] = {}
        self._pending_industry_capture_manifests: List[Path] = []
        self._pending_industry_csv_before: Optional[bytes] = None
        self._pending_industry_csv_after_sha256: Optional[str] = None
        self._industry_update_block_legacy_sync = False
        self._industry_update_succeeded_without_capture = False
        self._pending_industry_batch_partial = False
        self._pending_industry_failed_dates: List[str] = []
        self._pending_industry_unknown_legacy_dates: List[str] = []
        self .status_manifest_file =self .config .meta_data_dir /'data_status_manifest.json'
        self .monthly_revenue_source_version ="mops-static-snapshot-monthly-revenue-2026-06-16"
        configured_snapshot_candidate = (
            monthly_revenue_snapshot_candidate_path
            if monthly_revenue_snapshot_candidate_path is not None
            else os.environ.get("MONTHLY_REVENUE_SNAPSHOT_CANDIDATE")
        )
        self.monthly_revenue_snapshot_candidate_path = (
            Path(configured_snapshot_candidate).expanduser().resolve()
            if configured_snapshot_candidate
            else None
        )
        configured_candidate = (
            monthly_revenue_availability_candidate_path
            if monthly_revenue_availability_candidate_path is not None
            else os.environ.get("MONTHLY_REVENUE_AVAILABILITY_CANDIDATE")
        )
        self.monthly_revenue_availability_candidate_path = (
            Path(configured_candidate).expanduser().resolve()
            if configured_candidate
            else None
        )

    def dry_run_mops_monthly_revenue_backfill (
    self ,
    snapshot_file :Optional [Path ]=None ,
    availability_file :Optional [Path ]=None ,
    source_version :Optional [str ]=None ,
    cancel_callback: Optional[Callable[[], bool]] = None,
    )->Dict [str ,Any ]:
        """Plan MOPS snapshot monthly revenue backfill without writing SQLite."""
        if _is_cancel_requested(cancel_callback):
            return {'success':False, 'cancelled':True, 'message':'月營收 dry-run 已在開始前取消'}
        try :
            from data_module .monthly_revenue_backfill import plan_mops_snapshot_monthly_revenue_backfill
            from decision_module .factors .fundamental_adapters import source_diagnostics_to_factor_diagnostics

            snapshot_path =self ._resolve_monthly_revenue_snapshot_file (snapshot_file )
            availability_path =Path (availability_file or self .config .monthly_revenue_availability_file )
            version =source_version or self .monthly_revenue_source_version
            plan =plan_mops_snapshot_monthly_revenue_backfill (
            snapshot_file =snapshot_path ,
            availability_file =availability_path ,
            source_version =version ,
            )
            diagnostic_payloads =[diagnostic .to_dict ()for diagnostic in source_diagnostics_to_factor_diagnostics(plan.diagnostics) ]
            return {
            'success':plan .ready_for_apply ,
            'ready_for_apply':plan .ready_for_apply ,
            'raw_row_count':plan .raw_row_count ,
            'normalized_record_count':len (plan .records ),
            'diagnostic_count':len (plan .diagnostics ),
            'diagnostics':diagnostic_payloads ,
            'snapshot_file':str (snapshot_path ),
            'availability_file':str (availability_path ),
            'source_version':version ,
            'message':(
            f"MOPS 月營收 dry-run 完成：normalized={len(plan.records):,}, diagnostics={len(plan.diagnostics):,}"
            ),
            }
        except Exception as exc :
            return {
            'success':False ,
            'cancelled':False,
            'ready_for_apply':False ,
            'raw_row_count':0 ,
            'normalized_record_count':0 ,
            'diagnostic_count':1 ,
            'diagnostics':[{'code':'monthly_revenue.dry_run_error','message':str (exc )}],
            'message':f"MOPS 月營收 dry-run 失敗: {exc}",
            }

    def apply_mops_monthly_revenue_backfill (
    self ,
    snapshot_file :Optional [Path ]=None ,
    availability_file :Optional [Path ]=None ,
    source_version :Optional [str ]=None ,
    cancel_callback: Optional[Callable[[], bool]] = None,
    )->Dict [str ,Any ]:
        """Apply MOPS snapshot monthly revenue backfill into SQLite."""
        if _is_cancel_requested(cancel_callback):
            return {'success':False, 'cancelled':True, 'message':'月營收正式回填已在交易開始前取消'}
        try :
            from data_module .monthly_revenue_backfill import apply_mops_snapshot_monthly_revenue_backfill

            snapshot_path =self ._resolve_monthly_revenue_snapshot_file (snapshot_file )
            availability_path =Path (availability_file or self .config .monthly_revenue_availability_file )
            version =source_version or self .monthly_revenue_source_version
            result =apply_mops_snapshot_monthly_revenue_backfill (
            db_file =self .config .db_file ,
            backup_dir =self .config .meta_data_dir /'backup',
            snapshot_file =snapshot_path ,
            availability_file =availability_path ,
            source_version =version ,
            )
            return {
            'success':result .applied ,
            'cancelled':False,
            'cancel_requested_after_commit':_is_cancel_requested(cancel_callback),
            'applied':result .applied ,
            'inserted_count':result .inserted_count ,
            'ready_for_apply':result .plan .ready_for_apply ,
            'raw_row_count':result .plan .raw_row_count ,
            'normalized_record_count':len (result .plan .records ),
            'diagnostic_count':len (result .plan .diagnostics ),
            'backup_file':str (result .backup_file )if result .backup_file else None ,
            'snapshot_file':str (snapshot_path ),
            'availability_file':str (availability_path ),
            'source_version':version ,
            'message':(
            f"MOPS 月營收已寫入 SQLite：inserted={result.inserted_count:,}"
            if result .applied
            else f"MOPS 月營收未寫入：diagnostics={len(result.plan.diagnostics):,}"
            ),
            }
        except Exception as exc :
            return {
            'success':False ,
            'cancelled':False,
            'applied':False ,
            'inserted_count':0 ,
            'message':f"MOPS 月營收寫入失敗: {exc}",
            }

    def save_daily_monthly_revenue_capture(
        self,
        *,
        snapshot_root: Path | str,
        capture: "DailySourceTransportCapture",
        period: str,
        batch_id: str,
        source_batch_started_at: datetime,
        trusted_acceptance: "DailySourceUseAcceptance",
        scope: "DailySourceUseScope",
        clock: Callable[[], datetime],
        cancel_callback: Callable[[], bool],
    ) -> "DailyMonthlyRevenueSnapshotUpdateResult":
        """將明確保存的完整 response 交给每日 producer；不選來源或授權用途。

        snapshot root、scope、接受錨點及 batch 均由 caller 固定。此端口
        不沿用文字 harvester、CSV apply 或正式 SQLite／歷史 PIT 流程。
        """
        from app_module.monthly_revenue_daily_snapshot_update import (
            publish_daily_monthly_revenue_snapshot,
        )
        return publish_daily_monthly_revenue_snapshot(
            root=snapshot_root, capture=capture, period=period, batch_id=batch_id,
            source_batch_started_at=source_batch_started_at,
            use_acceptance=trusted_acceptance, scope=scope, clock=clock,
            check_cancel=cancel_callback,
        )

    def read_daily_monthly_revenue_status(
        self,
        *,
        snapshot_root: Path | str,
        batch_id: str,
        period: str,
        scope: "DailySourceUseScope",
        trusted_acceptance: "DailySourceUseAcceptance",
    ) -> "DailyMonthlyRevenueSnapshotReadStatus":
        """唯讀 caller 指定的批次；與 CSV 候選及正式 PIT 狀態分開。"""
        from app_module.monthly_revenue_daily_snapshot_update import (
            read_daily_monthly_revenue_snapshot_status,
        )
        return read_daily_monthly_revenue_snapshot_status(
            snapshot_root, batch_id=batch_id, period=period,
            expected_scope=scope, trusted_acceptance=trusted_acceptance,
        )

    def materialize_current_monthly_revenue(
        self,
        snapshot_file: Optional[Path] = None,
        *,
        apply: bool = False,
        cancel_callback: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """重驗官方原件與Decimal正規化，只供現況研究，不修改正式PIT。"""
        if _is_cancel_requested(cancel_callback):
            return {'success': False, 'cancelled': True, 'message': '現況月營收已在開始前取消'}
        try:
            from data_module.current_monthly_revenue_materialization import plan_current_revenue, apply_current_revenue
            plan = plan_current_revenue(self._resolve_monthly_revenue_snapshot_file(snapshot_file))
            result = dict(plan.custody)
            if _is_cancel_requested(cancel_callback):
                return dict(result, success=False, cancelled=True, applied=False, message='現況月營收已在寫入前取消')
            if apply:
                result = apply_current_revenue(
                    plan, db_file=Path(self.config.db_file),
                    backup_dir=Path(self.config.meta_data_dir) / 'backup',
                    receipt_dir=Path(self.config.output_root) / 'current_monthly_revenue_receipts',
                )
            return dict(result, success=True, cancelled=False, ready_for_current_apply=True,
                        cancel_requested_after_commit=apply and _is_cancel_requested(cancel_callback),
                        message=f"現況月營收{'已更新' if apply else '重驗完成'}：{len(plan.records):,} 筆 TWD；僅供現況研究，正式歷史可得日未改")
        except Exception as exc:
            return {'success': False, 'cancelled': False, 'applied': False, 'formal_pit_eligible': False,
                    'message': f'現況月營收原件／正規化驗證失敗：{exc}'}

    def _resolve_monthly_revenue_snapshot_file (self ,snapshot_file :Optional [Path ])->Path :
        if snapshot_file :
            path =Path (snapshot_file )
            if not path .exists ():
                raise FileNotFoundError (f"MOPS snapshot 不存在: {path}")
            return path

        snapshot_dir =self .config .output_root /'monthly_revenue_mops_snapshots'
        selected = select_latest_monthly_revenue_snapshot(snapshot_dir)
        if selected is None:
            raise FileNotFoundError (f"找不到 MOPS 月營收 snapshot CSV: {snapshot_dir}")
        return selected

    def fetch_mops_monthly_revenue_snapshot_candidate(
        self,
        *,
        start_period: str,
        end_period: str,
        markets: tuple[str, ...] = ("twse", "tpex"),
        fetch_date: str | None = None,
        sleep_seconds: float = 0.5,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        cancel_callback: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """抓取 MOPS 月營收候選 snapshot；只寫候選輸出，不寫 SQLite。

        這個 wrapper 讓桌面更新頁能使用和 CLI 相同的受控命名與來源版本，
        避免使用者只看到舊 snapshot 卻沒有可追蹤的更新入口。正式月營收與
        availability mapping 仍須另行 dry-run／人工確認。
        """
        if _is_cancel_requested(cancel_callback):
            return {
                "success": False, "cancelled": True, "candidate_only": True,
                "output_csv": None, "row_count": 0,
                "diagnostics": [], "message": "MOPS 月營收候選抓取已在開始前取消",
            }
        try:
            from data_module.monthly_revenue_snapshot_harvester import (
                build_mops_monthly_revenue_snapshot,
                create_monthly_revenue_snapshot_capture_directory,
                write_mops_snapshot_csv,
            )

            target_date = date.fromisoformat(fetch_date) if fetch_date else date.today()
            normalized_markets = tuple(
                str(market).strip().lower()
                for market in markets
                if str(market).strip()
            )
            if not normalized_markets:
                raise ValueError("markets 不得為空")
            if progress_callback is not None:
                progress_callback(
                    f"抓取 MOPS 月營收候選（{start_period} ~ {end_period}）…",
                    10,
                )
            output_dir = Path(self.config.output_root) / "monthly_revenue_mops_snapshots"
            capture_dir = create_monthly_revenue_snapshot_capture_directory(
                output_dir, fetch_date=target_date
            )
            raw_html_dir = capture_dir / "raw_html"
            result = build_mops_monthly_revenue_snapshot(
                start_period=start_period,
                end_period=end_period,
                markets=normalized_markets,
                fetch_date=target_date,
                save_html_dir=raw_html_dir,
                sleep_seconds=max(0.0, float(sleep_seconds)),
                cancel_callback=cancel_callback,
                progress_callback=progress_callback,
            )
            output_csv = capture_dir / (
                f"mops_monthly_revenue_snapshot_{start_period}_{end_period}_"
                f"{target_date.isoformat()}.csv"
            )
            if result.rows and not result.cancelled:
                write_mops_snapshot_csv(output_csv, result.rows)
            if progress_callback is not None:
                progress_callback(
                    f"MOPS 候選完成：{len(result.rows):,} 筆",
                    100,
                )
            diagnostics = [
                {
                    "code": diagnostic.code,
                    "message": diagnostic.message,
                }
                for diagnostic in result.diagnostics
            ]
            success = bool(result.rows) and result.valid_candidate
            return {
                "success": success and not result.cancelled,
                "cancelled": result.cancelled,
                "candidate_only": True,
                "output_csv": str(output_csv) if result.rows and not result.cancelled else None,
                "raw_html_dir": str(raw_html_dir),
                "capture_dir": str(capture_dir),
                "start_period": start_period,
                "end_period": end_period,
                "fetch_date": target_date.isoformat(),
                "markets": list(normalized_markets),
                "fetched_periods": list(result.fetched_periods),
                "row_count": len(result.rows),
                "diagnostics": diagnostics,
                "message": (
                    f"MOPS 月營收候選完成：{len(result.rows):,} 筆；"
                    f"期別 {start_period} ~ {end_period}"
                    if success and not result.cancelled
                    else (
                        f"MOPS 月營收候選已安全取消；保留 {len(result.rows):,} 筆已解析資料，"
                        "未發布不完整 CSV"
                        if result.cancelled
                        else "MOPS 月營收候選未產生可用列；請查看 diagnostics"
                    )
                ),
            }
        except Exception as exc:
            return {
                "success": False,
                "cancelled": False,
                "candidate_only": True,
                "output_csv": None,
                "row_count": 0,
                "diagnostics": [
                    {
                        "code": "monthly_revenue.candidate_fetch_error",
                        "message": str(exc),
                    }
                ],
                "message": f"MOPS 月營收候選抓取失敗：{exc}",
            }

    def update_phase3c_candidate_range(
        self,
        *,
        start_date: str,
        end_date: str,
        sources: tuple[str, ...] = ("institutional", "credit"),
        include_latest_tdcc_snapshot: bool = False,
        allow_online_calendar_probe: bool = True,
        calendar: Optional[OfficialTradingCalendar] = None,
        rate_limit_seconds: float = 3.0,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        cancel_callback: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """更新 Phase 3C 候選資料；明確限制為隔離 Candidate DB。

        正式 `twstock.db` 不會被此方法寫入；runner 仍會再次驗證 candidate
        path 與 confirm token。UI 只在使用者確認後呼叫 apply 模式。
        """
        try:
            candidate_path = configured_candidate_db_path()
            if candidate_path is None:
                raise ValueError(
                    "尚未設定 PHASE3C_CANDIDATE_DB_PATH；為避免猜測路徑，未執行候選寫入"
                )
            from scripts.update_phase3c_candidates import (
                update_phase3c_candidates_range,
            )
            from data_module.phase3c_backfill_runner import APPLY_CONFIRM_TOKEN

            result = update_phase3c_candidates_range(
                start_date=start_date,
                end_date=end_date,
                dry_run=False,
                db_path=str(candidate_path),
                sources=sources,
                rate_limit_seconds=max(0.0, float(rate_limit_seconds)),
                allow_online_calendar_probe=allow_online_calendar_probe,
                include_latest_tdcc_snapshot=include_latest_tdcc_snapshot,
                calendar=calendar,
                progress_callback=progress_callback,
                cancel_callback=cancel_callback,
                confirm_token=APPLY_CONFIRM_TOKEN,
            )
            summary = result.get("summary")
            return {
                "success": bool(result.get("success")),
                "cancelled": bool(result.get("cancelled", False)),
                "candidate_only": True,
                "candidate_db_path": str(candidate_path),
                "summary": summary,
                "message": str(result.get("message") or "Phase 3C 候選更新完成"),
            }
        except Exception as exc:
            return {
                "success": False,
                "cancelled": False,
                "candidate_only": True,
                "message": f"Phase 3C 候選更新失敗：{exc}",
                "candidate_db_path": None,
            }

    def sync_source_to_sqlite (
    self ,
    source :str ,
    start_date :Optional [str ]=None ,
    end_date :Optional [str ]=None ,
    cancel_callback :Optional [Callable [[],bool ]]=None ,
    *,
    row_evidence_source_diagnostics: Optional[List[Dict[str, Any]]] = None,
    )->Dict [str ,Any ]:
        """將既有 CSV 更新結果同步到 SQLite，保留日常 CSV 輸出行為。"""
        import logging

        logger =logging .getLogger (__name__ )
        if _is_cancel_requested(cancel_callback):
            return {
            'success':False ,
            'cancelled':True ,
            'message':f'{source} SQLite 同步已取消（尚未開始寫入）',
            'source':source ,
            'synced_records':0 ,
            }
        if (
            source in {'industry', 'industry_index'}
            and self._industry_update_block_legacy_sync
            and not self._pending_industry_capture_manifests
        ):
            return {
                'success': self._industry_update_succeeded_without_capture,
                'skipped': self._industry_update_succeeded_without_capture,
                'message': (
                    '產業更新沒有新 capture；略過整份 CSV 同步'
                    if self._industry_update_succeeded_without_capture
                    else '產業來源更新未通過；拒絕以既有整份 CSV 自動同步 SQLite'
                ),
                'source': source,
                'synced_records': 0,
            }
        if not getattr (self .config ,'use_sqlite',False ):
            if source in {'industry', 'industry_index'} and self._pending_industry_capture_manifests:
                scoped_result = self.sync_industry_index_captures_to_sqlite(
                    list(self._pending_industry_capture_manifests),
                    batch_partial=self._pending_industry_batch_partial,
                    failed_dates=self._pending_industry_failed_dates,
                    unknown_legacy_dates=self._pending_industry_unknown_legacy_dates,
                )
                self._pending_industry_capture_manifests = []
                self._pending_industry_csv_before = None
                self._pending_industry_csv_after_sha256 = None
                self._industry_update_block_legacy_sync = (
                    not bool(scoped_result.get('success'))
                    or self._pending_industry_batch_partial
                    or bool(scoped_result.get('partial'))
                )
                self._pending_industry_batch_partial = False
                self._pending_industry_failed_dates = []
                self._pending_industry_unknown_legacy_dates = []
                self._industry_update_succeeded_without_capture = False
                return scoped_result
            return {
            'success':True ,
            'message':'SQLite 未啟用，略過同步',
            'source':source ,
            'synced_records':0 ,
            'skipped':True ,
            }

        try :
            normalized ={
            'daily':'daily_data',
            'daily_data':'daily_data',
            'daily_price_files':'daily_price_files',
            'market':'market_index',
            'market_index':'market_index',
            'industry':'industry_index',
            'industry_index':'industry_index',
            'broker':'broker_branch',
            'broker_branch':'broker_branch',
            'broker_branch_files':'broker_branch_files',
            }.get (source )
            if normalized is None :
                return {
                'success':False ,
                'message':f'未知 SQLite 同步來源: {source}',
                'source':source ,
                'synced_records':0 ,
                }

            if normalized == 'industry_index' and self._pending_industry_capture_manifests:
                capture_paths = list(self._pending_industry_capture_manifests)
                scoped_result = self.sync_industry_index_captures_to_sqlite(
                    capture_paths,
                    batch_partial=self._pending_industry_batch_partial,
                    failed_dates=self._pending_industry_failed_dates,
                    unknown_legacy_dates=self._pending_industry_unknown_legacy_dates,
                )
                self._pending_industry_capture_manifests = []
                self._pending_industry_csv_before = None
                self._pending_industry_csv_after_sha256 = None
                self._industry_update_block_legacy_sync = (
                    not bool(scoped_result.get('success'))
                    or self._pending_industry_batch_partial
                    or bool(scoped_result.get('partial'))
                )
                self._pending_industry_batch_partial = False
                self._pending_industry_failed_dates = []
                self._pending_industry_unknown_legacy_dates = []
                self._industry_update_succeeded_without_capture = False
                return scoped_result

            if normalized =='daily_price_files':
                df =self ._load_daily_price_files_for_sqlite (start_date ,end_date )
                table_name ='daily_prices'
                replace_table =False
                delete_date_keys =True
            elif normalized =='daily_data':
                df =self ._load_daily_data_for_sqlite ()
                table_name ='daily_prices'
                replace_table =False
                delete_date_keys =True
            elif normalized =='market_index':
                df =self ._load_csv_for_sqlite (self .config .market_index_file ,require_date =True )
                df =normalize_market_index_frame (df )if not df .empty else df
                table_name ='market_indices'
                # The CSV is a historical snapshot, but syncing it must not
                # DELETE the whole SQLite table.  Replace only the date keys
                # represented by the validated source frame so an interrupted
                # or partial source cannot erase older rows.
                replace_table =False
                delete_date_keys =True
            elif normalized =='industry_index':
                df =self ._load_csv_for_sqlite (self .config .industry_index_file ,require_date =True )
                table_name ='industry_indices'
                replace_table =False
                delete_date_keys =True
            elif normalized =='broker_branch_files':
                df =self ._load_broker_branch_files_for_sqlite (start_date ,end_date )
                table_name ='broker_flows'
                replace_table =False
                delete_date_keys =True
            else :
                df =self ._load_broker_branch_csv_for_sqlite ()
                table_name ='broker_flows'
                replace_table =True
                delete_date_keys =False

            if df .empty :
                empty_result = {
                'success':True ,
                'message':f'{source} 沒有可同步的 CSV 資料',
                'source':source ,
                'synced_records':0 ,
                }
                if normalized == 'daily_price_files':
                    empty_result['row_evidence'] = {
                        'status': 'unknown',
                        'reason_code': 'no_rows_to_read_back',
                    }
                return empty_result

            if _is_cancel_requested(cancel_callback):
                return {
                'success':False ,
                'cancelled':True ,
                'message':f'{source} SQLite 同步已取消（尚未開始寫入）',
                'source':source ,
                'table':table_name ,
                'synced_records':0 ,
                }

            from data_module .db_manager import DBManager

            db =DBManager (self .config )
            if table_name =='broker_flows':
                db .ensure_broker_flows_trade_type_primary_key ()
            if normalized =='daily_price_files':
                success =self ._upsert_sqlite_rows (db ,table_name ,df )
            elif replace_table :
                success =self ._replace_sqlite_table (db ,table_name ,df )
            elif delete_date_keys :
                success =self ._replace_sqlite_dates (db ,table_name ,df )
            else :
                success =db .write_dataframe (table_name ,df ,if_exists ='append')

            if not success :
                return {
                'success':False ,
                'message':f'{source} 同步 SQLite 失敗',
                'source':source ,
                'synced_records':0 ,
                }

            logger .info ("[UpdateService] %s 已同步 SQLite table %s，共 %s 筆",source ,table_name ,len (df ))
            result = {
            'success':True ,
            'message':f'{source} 已同步 SQLite',
            'source':source ,
            'table':table_name ,
            'synced_records':int (len (df )),
            }
            if normalized == 'daily_price_files':
                from data_module.twse_daily_price_publication import (
                    publish_sqlite_row_evidence,
                )

                try:
                    result['row_evidence'] = publish_sqlite_row_evidence(
                        output_root=self.config.output_root,
                        data_root=self.config.data_root,
                        database_path=db.db_path,
                        source_diagnostics=row_evidence_source_diagnostics or [],
                        merged_frame=df,
                    )
                except Exception as evidence_error:
                    # SQLite 已提交；新證據失敗不改寫舊同步結果，也不補發空覆蓋。
                    logger.warning(
                        "[UpdateService] SQLite row evidence unavailable after commit: %s",
                        type(evidence_error).__name__,
                    )
                    result['row_evidence'] = {
                        'status': 'unknown',
                        'reason_code': 'publication_failed',
                    }
            return result
        except Exception as e :
            logger .exception ("[UpdateService] 同步 SQLite 失敗: source=%s",source )
            return {
            'success':False ,
            'message':f'{source} 同步 SQLite 時發生錯誤: {e}',
            'source':source ,
            'synced_records':0 ,
            }

    def sync_industry_index_captures_to_sqlite(
        self,
        capture_manifests: Sequence[str | Path],
        *,
        batch_partial: bool = False,
        failed_dates: Sequence[str] = (),
        unknown_legacy_dates: Sequence[str] = (),
    ) -> Dict[str, Any]:
        """Sync only dates bound to verified TWSE industry captures."""
        import logging

        from data_module.twse_industry_index_capture import (
            CSV_COLUMNS,
            TwseIndustryIndexCaptureError,
            canonical_rowset,
            create_industry_projection_commit_manifest,
            restore_csv_before_image,
            verify_capture_receipt,
            verify_csv_date_projection,
        )

        logger = logging.getLogger(__name__)
        csv_path = Path(self.config.industry_index_file)
        before_csv = self._pending_industry_csv_before
        expected_csv_sha256 = self._pending_industry_csv_after_sha256
        captures: List[Dict[str, Any]] = []
        database_path = Path(self.config.db_file)
        table_name = "industry_indices"
        columns_sql = ", ".join(f'"{column}"' for column in CSV_COLUMNS)
        committed = False
        before_rows: List[Dict[str, Any]] = []
        expected_rows: List[Dict[str, Any]] = []
        expected_canonical: List[List[str | None]] = []
        schema_signature: tuple[tuple[Any, ...], ...] = ()

        def outcome(success: bool, message: str, *, partial: bool = False, rows: int = 0) -> Dict[str, Any]:
            return {
                "success": success,
                "partial": partial,
                "message": message,
                "source": "industry_index",
                "table": table_name,
                "synced_records": rows if success else 0,
                "capture_count": len(captures),
                "batch_partial": batch_partial,
                "failed_dates": sorted(set(failed_dates)),
                "unknown_legacy_dates": sorted(set(unknown_legacy_dates)),
                "projection_status": "not_committed",
                "partial": partial or batch_partial,
            }

        def date_clause(dates: List[str]) -> tuple[str, List[str]]:
            compact = [value.replace("-", "") for value in dates]
            expression = "REPLACE(REPLACE(CAST(\"日期\" AS TEXT), '-', ''), '/', '')"
            return f"{expression} IN ({','.join('?' for _ in compact)})", compact

        def read_target(connection: sqlite3.Connection, dates: List[str]) -> List[Dict[str, Any]]:
            clause, parameters = date_clause(dates)
            result = connection.execute(
                f"SELECT {columns_sql} FROM {table_name} WHERE {clause}",
                parameters,
            ).fetchall()
            return [dict(row) for row in result]

        def schema_for(connection: sqlite3.Connection) -> tuple[tuple[Any, ...], ...]:
            rows = connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
            return tuple(
                (row["cid"], row["name"], row["type"], row["notnull"], row["dflt_value"], row["pk"])
                for row in rows
            )

        def compensate_database() -> bool:
            if not committed or not database_path.is_file():
                return True
            dates = sorted({str(item["source_date"]) for item in captures})
            try:
                with sqlite3.connect(database_path, timeout=30) as connection:
                    connection.row_factory = sqlite3.Row
                    connection.execute("BEGIN IMMEDIATE")
                    if schema_for(connection) != schema_signature:
                        connection.rollback()
                        return False
                    current = read_target(connection, dates)
                    if canonical_rowset(current) != expected_canonical:
                        connection.rollback()
                        return False
                    clause, parameters = date_clause(dates)
                    connection.execute(f"DELETE FROM {table_name} WHERE {clause}", parameters)
                    if before_rows:
                        placeholders = ", ".join("?" for _ in CSV_COLUMNS)
                        connection.executemany(
                            f"INSERT INTO {table_name} ({columns_sql}) VALUES ({placeholders})",
                            [tuple(row.get(column) for column in CSV_COLUMNS) for row in before_rows],
                        )
                    restored = read_target(connection, dates)
                    if canonical_rowset(restored) != canonical_rowset(before_rows):
                        connection.rollback()
                        return False
                    connection.commit()
                return True
            except Exception:
                logger.exception("TWSE industry SQLite before-image compensation failed")
                return False

        def compensate_csv() -> bool:
            if expected_csv_sha256 is None:
                return True
            try:
                restore_csv_before_image(
                    csv_path,
                    before_csv,
                    expected_current_sha256=expected_csv_sha256,
                )
                return True
            except Exception:
                logger.exception("TWSE industry CSV before-image compensation failed")
                return False

        try:
            if not getattr(self.config, "use_sqlite", False):
                raise TwseIndustryIndexCaptureError(
                    "SQLite 未啟用；拒絕標記完整並回復本次 CSV projection"
                )
            if not capture_manifests:
                return outcome(False, "沒有 TWSE capture receipt，拒絕執行日期範圍替換")
            for manifest in capture_manifests:
                captures.append(verify_capture_receipt(manifest, self.config.output_root))
            dates = sorted({str(item["source_date"]) for item in captures})
            if len(dates) != len(captures):
                raise TwseIndustryIndexCaptureError("一個批次包含重複 source_date capture")
            expected_rows = [
                {column: row[index] for index, column in enumerate(CSV_COLUMNS)}
                for item in captures
                for row in item["rows"]
            ]
            expected_canonical = canonical_rowset(expected_rows)
            row_keys = [(row["日期"], row["指數名稱"]) for row in expected_rows]
            if len(row_keys) != len(set(row_keys)):
                raise TwseIndustryIndexCaptureError("capture rowset 含重複日期/指數名稱鍵")
            csv_rows, csv_sha256 = verify_csv_date_projection(csv_path, captures)
            if canonical_rowset(csv_rows) != expected_canonical:
                raise TwseIndustryIndexCaptureError("CSV six-column projection 與 captures 不符")
            if expected_csv_sha256 is not None and csv_sha256 != expected_csv_sha256:
                raise TwseIndustryIndexCaptureError("CSV 在更新與 SQLite 同步之間被其他 writer 修改")
            if not database_path.is_file():
                raise TwseIndustryIndexCaptureError("SQLite DB 不存在；不建立新 DB 或 schema")

            with sqlite3.connect(database_path, timeout=30) as connection:
                connection.row_factory = sqlite3.Row
                schema_signature = schema_for(connection)
                schema_columns = [row[1] for row in schema_signature]
                if not all(column in schema_columns for column in CSV_COLUMNS):
                    raise TwseIndustryIndexCaptureError("industry_indices schema 缺少既有六欄；不執行 DDL")
                connection.execute("BEGIN IMMEDIATE")
                before_rows = read_target(connection, dates)
                before_keys = [(str(row.get("日期", "")).replace("-", "").replace("/", ""), str(row.get("指數名稱", "")).strip()) for row in before_rows]
                if len(before_keys) != len(set(before_keys)):
                    connection.rollback()
                    raise TwseIndustryIndexCaptureError(
                        "industry_indices transaction 前 scoped (日期, 指數名稱) 鍵重複"
                    )
                clause, parameters = date_clause(dates)
                connection.execute(f"DELETE FROM {table_name} WHERE {clause}", parameters)
                insert_rows = [
                    tuple(
                        row[column].replace("-", "") if column == "日期" and row[column] else row[column]
                        for column in CSV_COLUMNS
                    )
                    for row in expected_rows
                ]
                placeholders = ", ".join("?" for _ in CSV_COLUMNS)
                connection.executemany(
                    f"INSERT INTO {table_name} ({columns_sql}) VALUES ({placeholders})",
                    insert_rows,
                )
                in_transaction_rows = read_target(connection, dates)
                transaction_keys = [
                    (str(row.get("日期", "")).replace("-", "").replace("/", ""), str(row.get("指數名稱", "")).strip())
                    for row in in_transaction_rows
                ]
                if len(transaction_keys) != len(set(transaction_keys)):
                    connection.rollback()
                    raise TwseIndustryIndexCaptureError(
                        "industry_indices transaction 後 scoped (日期, 指數名稱) 鍵重複"
                    )
                if canonical_rowset(in_transaction_rows) != expected_canonical:
                    connection.rollback()
                    raise TwseIndustryIndexCaptureError("industry_indices transaction 內 rowset readback 不符")
                connection.commit()
                committed = True

            # Read through a new connection after COMMIT; the marker is created only after this succeeds.
            with sqlite3.connect(database_path, timeout=30) as readback_connection:
                readback_connection.row_factory = sqlite3.Row
                if schema_for(readback_connection) != schema_signature:
                    raise TwseIndustryIndexCaptureError("SQLite schema 在同步期間改變")
                sqlite_rows = read_target(readback_connection, dates)
            readback_keys = [
                (str(row.get("日期", "")).replace("-", "").replace("/", ""), str(row.get("指數名稱", "")).strip())
                for row in sqlite_rows
            ]
            if len(readback_keys) != len(set(readback_keys)):
                raise TwseIndustryIndexCaptureError(
                    "獨立 SQLite readback scoped (日期, 指數名稱) 鍵重複"
                )
            if canonical_rowset(sqlite_rows) != expected_canonical:
                raise TwseIndustryIndexCaptureError("獨立 SQLite readback rowset 不符")
            # The CSV may be changed by another process while SQLite is being
            # committed/read back. Re-read exact bytes and the scoped rowset
            # immediately before the marker. This narrows the race window but
            # does not replace a cross-process writer lock.
            final_csv_rows, final_csv_sha256 = verify_csv_date_projection(
                csv_path, captures,
            )
            if canonical_rowset(final_csv_rows) != expected_canonical:
                raise TwseIndustryIndexCaptureError(
                    "CSV marker 前日期範圍 readback 與 capture rowset 不符"
                )
            if (
                expected_csv_sha256 is None
                or final_csv_sha256 != expected_csv_sha256
                or final_csv_sha256 != csv_sha256
            ):
                raise TwseIndustryIndexCaptureError(
                    "CSV 在 SQLite commit 後至 marker 前被其他 writer 修改"
                )
            marker = create_industry_projection_commit_manifest(
                output_root=self.config.output_root,
                captures=captures,
                csv_path=csv_path,
                csv_sha256=final_csv_sha256,
                database_path=database_path,
                sqlite_rows=sqlite_rows,
                batch_partial=batch_partial,
                failed_dates=failed_dates,
                unknown_legacy_dates=unknown_legacy_dates,
            )
            return {
                **outcome(
                    True,
                    (
                        "TWSE industry captured-date sync and exact readback complete; "
                        "batch has failed dates and is partial"
                        if batch_partial
                        else "TWSE industry date-scoped SQLite sync and exact readback complete"
                    ),
                    rows=len(expected_rows),
                ),
                "projection_commit_marker": str(marker),
                "projection_status": "committed_after_exact_csv_sqlite_readback",
                "dates": dates,
            }
        except Exception as exc:
            database_restored = compensate_database()
            csv_restored = compensate_csv()
            partial = not database_restored or not csv_restored
            message = f"TWSE industry scoped sync failed: {exc}"
            if partial:
                message += "; before-image compensation could not be proven, status=partial"
            else:
                message += "; CSV/SQLite before-images restored or unchanged"
            logger.error(message, exc_info=True)
            return outcome(False, message, partial=partial)

    def _create_tpex_daily_price_source (self )->Any :
        from data_module .tpex_daily_price_source import TpexDailyPriceSource

        return TpexDailyPriceSource (
            self .config .tpex_daily_price_dir,
            source_custody_root=self .config .output_root,
        )

    def update_tpex_daily_price (
    self ,
    target_date :Optional [str ]=None ,
    start_date :Optional [str ]=None ,
    end_date :Optional [str ]=None ,
    )->Dict [str ,Any ]:
        """更新 TPEX 官方每日收盤行情 CSV。"""
        import logging

        logger =logging .getLogger (__name__ )
        try :
            effective_target =target_date
            if effective_target is None and start_date and end_date :
                date_keys =self ._iter_weekday_date_keys (start_date ,end_date )
                if not date_keys :
                    return {
                    'success':True ,
                    'message':'TPEX 每日股價區間沒有官方交易日，已略過（非資料失敗）',
                    'updated_dates':[],
                    'fallback_dates':[],
                    'failed_dates':[],
                    'tpex_rows':0 ,
                    'skipped_rows':0 ,
                    'diagnostic_count':0 ,
                    'source_date':None ,
                    'output_file':None ,
                    'no_op':True ,
                    }
                effective_target =date_keys [-1 ]

            if effective_target is None :
                return {
                'success':False ,
                'message':'TPEX daily price requires target_date or start_date/end_date',
                'updated_dates':[],
                'fallback_dates':[],
                'failed_dates':[],
                'tpex_rows':0 ,
                'skipped_rows':0 ,
                'diagnostic_count':1 ,
                'source_date':None ,
                'output_file':None ,
                }

            effective_target =self ._date_key (effective_target )
            source =self ._create_tpex_daily_price_source ()
            result =source .update_for_date (effective_target )
            if result .success :
                logger .info (
                "[UpdateService] TPEX daily price saved: request=%s saved=%s rows=%s skipped=%s file=%s",
                effective_target ,
                result .source_date ,
                result .row_count ,
                result .skipped_count ,
                result .output_file ,
                )
                return {
                'success':True ,
                'message':result .message ,
                'updated_dates':[result .source_date or effective_target ]if result .source_date else [effective_target ],
                'fallback_dates':[result .source_date ]if result .source_date and result .source_date !=effective_target else [],
                'failed_dates':[],
                'tpex_rows':int (result .row_count ),
                'skipped_rows':int (result .skipped_count ),
                'diagnostic_count':int (result .diagnostic_count ),
                'source_date':result .source_date ,
                'output_file':str (result .output_file )if result .output_file else None ,
                'source_custody':dict (getattr (result, 'source_custody', None) or {}) or None ,
                }

            if result .source_date and result .source_date !=effective_target :
                fallback_result =source .update_for_date (result .source_date )
                if fallback_result .success :
                    logger .info (
                    "[UpdateService] TPEX fallback daily price saved: request=%s saved=%s rows=%s skipped=%s file=%s",
                    effective_target ,
                    fallback_result .source_date ,
                    fallback_result .row_count ,
                    fallback_result .skipped_count ,
                    fallback_result .output_file ,
                    )
                    return {
                    'success':True ,
                    'message':(
                    f"TPEX 回應日 {fallback_result.source_date} 已成功寫入，"
                    f"原請求日期 {effective_target} 無對應資料，已回退為回應日期"
                    ),
                    'updated_dates':[fallback_result .source_date ],
                    'fallback_dates':[fallback_result .source_date ],
                    'failed_dates':[],
                    'tpex_rows':int (fallback_result .row_count ),
                    'skipped_rows':int (fallback_result .skipped_count ),
                    'diagnostic_count':int (fallback_result .diagnostic_count ),
                    'source_date':fallback_result .source_date ,
                    'output_file':str (fallback_result .output_file )if fallback_result .output_file else None ,
                    'source_custody':dict (getattr (fallback_result, 'source_custody', None) or {}) or None ,
                    }

            logger .warning ("[UpdateService] TPEX daily price update failed: %s",result .message )
            return {
            'success':False ,
            'message':result .message ,
            'updated_dates':[],
            'fallback_dates':[],
            'failed_dates':[effective_target ],
            'tpex_rows':0 ,
            'skipped_rows':0 ,
            'diagnostic_count':int (result .diagnostic_count ),
            'source_date':result .source_date ,
            'output_file':None ,
            }
        except Exception as exc :
            logger .exception ("[UpdateService] TPEX daily price update raised")
            return {
            'success':False ,
            'message':f'TPEX daily price update failed: {exc}',
            'updated_dates':[],
            'fallback_dates':[],
            'failed_dates':[self ._date_key (target_date )]if target_date else [],
            'tpex_rows':0 ,
            'skipped_rows':0 ,
            'diagnostic_count':1 ,
            'source_date':None ,
            'output_file':None ,
            }

    def update_tpex_daily_price_range(
        self,
        start_date: str,
        end_date: str,
        delay_seconds: float = 0.0,
        force_refresh: bool = False,
        sync_to_sqlite: bool = False,
        break_on_repeated_source_date: bool = True,
        twse_no_data_dates: Optional[list[str]] = None,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        cancel_callback: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """逐日更新 TPEX 官方收盤行情，會記錄實際回應日並可選擇同步到 SQLite。"""
        import logging
        import time

        logger =logging .getLogger (__name__ )
        failure_diagnostics: list[dict[str, Any]] = []
        try :
            if _is_cancel_requested(cancel_callback):
                return {
                'success':False ,
                'cancelled':True ,
                'message':'TPEX 每日股價區間更新已取消（尚未開始）',
                'requested_dates':[],
                'updated_dates':[],
                'fallback_dates':[],
                'skipped_dates':[],
                'failed_dates':[],
                'warnings':[],
                'tpex_rows':0 ,
                'skipped_rows':0 ,
                'diagnostic_count':0 ,
                'source_dates':[],
                'failure_diagnostics':[],
                'sync_summary':None ,
                }
            date_keys =self ._iter_weekday_date_keys (start_date ,end_date )
            if not date_keys :
                return {
                'success':True ,
                'message':'TPEX 每日股價區間沒有官方交易日，已略過（非資料失敗）',
                'updated_dates':[],
                'fallback_dates':[],
                'skipped_dates':[],
                'failed_dates':[],
                'tpex_rows':0 ,
                'skipped_rows':0 ,
                'diagnostic_count':0 ,
                'source_dates':[],
                'failure_diagnostics':[],
                'sync_summary':None ,
                'no_op':True ,
                }

            source =self ._create_tpex_daily_price_source ()
            _emit_update_progress(
                progress_callback,
                f"TPEX API 準備下載 {len(date_keys)} 個工作日",
                0,
            )
            updated_dates :list [str ]=[]
            fallback_dates :list [str ]=[]
            skipped_dates :list [str ]=[]
            failed_dates :list [str ]=[]
            source_date_seen :set [str ]=set ()
            total_rows =0
            total_skipped_rows =0
            last_source_date :Optional [str ]=None
            source_custody_receipts :list [dict [str ,Any ]]=[]

            def append_failure_diagnostic(
                requested_date: str,
                result: Any,
                *,
                phase: str,
            ) -> None:
                """保留單日失敗上下文，避免區間摘要丟失來源診斷。"""
                raw_message = str(getattr(result, 'message', '') or '')
                diagnostic_count_value = getattr(result, 'diagnostic_count', 0)
                try:
                    diagnostic_count = max(0, int(diagnostic_count_value or 0))
                except (TypeError, ValueError):
                    diagnostic_count = 0
                row_count_value = getattr(result, 'row_count', 0)
                try:
                    row_count = max(0, int(row_count_value or 0))
                except (TypeError, ValueError):
                    row_count = 0
                skipped_count_value = getattr(result, 'skipped_count', 0)
                try:
                    skipped_count = max(0, int(skipped_count_value or 0))
                except (TypeError, ValueError):
                    skipped_count = 0
                failure_diagnostics.append(
                    {
                        'requested_date': requested_date,
                        'phase': phase,
                        'success': bool(getattr(result, 'success', False)),
                        'result_requested_date': getattr(result, 'requested_date', None),
                        'source_date': getattr(result, 'source_date', None),
                        'diagnostic_count': diagnostic_count,
                        'row_count': row_count,
                        'skipped_count': skipped_count,
                        'message': raw_message[:_TPEX_FAILURE_MESSAGE_MAX_CHARS],
                        'message_truncated': len(raw_message) > _TPEX_FAILURE_MESSAGE_MAX_CHARS,
                        'source_custody_present': bool(
                            getattr(result, 'source_custody', None)
                        ),
                    }
                )

            def cancelled_result(message: str) -> Dict[str, Any]:
                return {
                'success':False ,
                'cancelled':True ,
                'message':message ,
                'requested_dates':date_keys ,
                'updated_dates':sorted (set (updated_dates )),
                'fallback_dates':sorted (set (fallback_dates )),
                'skipped_dates':sorted (set (skipped_dates )),
                'failed_dates':sorted (set (failed_dates )),
                'warnings':[],
                'tpex_rows':total_rows ,
                'skipped_rows':total_skipped_rows ,
                'diagnostic_count':sum(
                    item['diagnostic_count'] for item in failure_diagnostics
                ),
                'source_dates':sorted (set (updated_dates )),
                'failure_diagnostics':list(failure_diagnostics),
                'sync_summary':None ,
                }

            def sleep_with_cancel(seconds: float) -> bool:
                """以短間隔等待，讓 UI 取消可在日期邊界前被觀察。"""
                if seconds <= 0:
                    return _is_cancel_requested(cancel_callback)
                if cancel_callback is None:
                    time.sleep(seconds)
                    return False
                deadline = time.monotonic() + seconds
                while True:
                    if _is_cancel_requested(cancel_callback):
                        return True
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return _is_cancel_requested(cancel_callback)
                    time.sleep(min(0.1, remaining))

            for idx ,requested_date in enumerate (date_keys ):
                if _is_cancel_requested(cancel_callback):
                    return cancelled_result(f"TPEX 每日股價區間更新已取消（停止於 {requested_date} 前）")
                current_percentage =((idx + 1 ) *100 )//len (date_keys )
                _emit_update_progress(
                    progress_callback,
                    f"TPEX API 下載 {requested_date}（{idx + 1}/{len(date_keys)}）",
                    current_percentage,
                )
                output_file =self .config .tpex_daily_price_dir /f'{requested_date}.csv'
                if not force_refresh and output_file .exists ():
                    skipped_dates .append (requested_date )
                    continue

                result =source .update_for_date (requested_date )
                effective_source_date =result .source_date or requested_date

                if not result.success:
                    append_failure_diagnostic(
                        requested_date,
                        result,
                        phase='requested',
                    )

                if _is_cancel_requested(cancel_callback):
                    return cancelled_result(f"TPEX 每日股價區間更新已取消（已完成 {requested_date}）")

                if result.success:
                    updated_dates.append(effective_source_date)
                    source_date_seen.add(effective_source_date)
                    total_rows += int(result.row_count)
                    if effective_source_date != requested_date:
                        fallback_dates.append(effective_source_date)
                    if getattr(result, 'source_custody', None):
                        source_custody_receipts.append(dict(result.source_custody))
                else:
                    twse_skipped = False
                    if twse_no_data_dates:
                        normalized_twse = [self._date_key(d) for d in twse_no_data_dates]
                        twse_skipped = requested_date in normalized_twse

                    if twse_skipped:
                        logger.info(f"[UpdateService] TPEX 缺少 {requested_date} 資料，但 TWSE 已判定為查無資料（如颱風假），標記為 skipped")
                        skipped_dates.append(requested_date)
                    else:
                        failed_dates.append(requested_date)

                if result.source_date and result.source_date != requested_date:
                    fallback_dates .append (result .source_date )
                    if result .source_date not in source_date_seen :
                        fallback_result =source .update_for_date (result .source_date )
                        if not fallback_result.success:
                            append_failure_diagnostic(
                                requested_date,
                                fallback_result,
                                phase='fallback',
                            )
                        if _is_cancel_requested(cancel_callback):
                            return cancelled_result(
                                f"TPEX 每日股價區間更新已取消（停止於 fallback {result.source_date}）"
                            )
                        if fallback_result .success :
                            fallback_source_date =fallback_result .source_date or result .source_date
                            updated_dates .append (fallback_source_date )
                            source_date_seen .add (fallback_source_date )
                            total_rows +=int (fallback_result .row_count )
                            effective_source_date =fallback_source_date
                            if getattr(fallback_result, 'source_custody', None):
                                source_custody_receipts.append(dict(fallback_result.source_custody))
                        else :
                            logger .warning (
                            "[UpdateService] TPEX fallback request failed: request=%s fallback=%s message=%s",
                            requested_date ,
                            result .source_date ,
                            fallback_result .message ,
                            )
                    else :
                        total_skipped_rows +=int (result .skipped_count )
                else :
                    total_skipped_rows +=int (result .skipped_count )

                    # 若同樣回應日反覆出現，表示 API 僅能回傳近期/最新日，後續日期會是重複資料
                if result .source_date :
                    if (
                    break_on_repeated_source_date
                    and effective_source_date ==last_source_date
                    and idx >0
                    ):
                        remaining =date_keys [idx +1 :]
                        skipped_dates .extend (remaining )
                        logger .info (
                        "[UpdateService] 偵測到 TPEX 重複回應日 %s，停止向前回補以避免重複下載：remaining=%s",
                        effective_source_date ,
                        len (remaining ),
                        )
                        break
                    last_source_date =effective_source_date

                if delay_seconds >0 and idx <len (date_keys )-1 :
                    if sleep_with_cancel(delay_seconds):
                        return cancelled_result("TPEX 每日股價區間更新已取消（等待下一日期前）")

            unique_updated_dates =sorted (set (updated_dates ))
            sync_summary =None
            if _is_cancel_requested(cancel_callback):
                return cancelled_result("TPEX 每日股價區間更新已取消（尚未同步 SQLite）")
            if sync_to_sqlite and unique_updated_dates :
                sync_start =unique_updated_dates [0 ]
                sync_end =unique_updated_dates [-1 ]
                sync_result =self .sync_source_to_sqlite (
                    "daily_price_files",
                    sync_start,
                    sync_end,
                    cancel_callback=cancel_callback,
                )
                sync_summary ={
                'success':sync_result .get ('success',False ),
                'synced_records':int (sync_result .get ('synced_records',0 )),
                'message':sync_result .get ('message',''),
                'source':sync_result .get ('source','daily_price_files'),
                'table':sync_result .get ('table','daily_prices'),
                }
                if sync_result.get('cancelled'):
                    return cancelled_result("TPEX 每日股價區間更新已取消（SQLite 同步前）")

            updated =len (unique_updated_dates )>0
            unique_failed_dates =sorted (set (failed_dates ))
            warnings =(
            [f"TPEX 每日股價缺少日期：{', '.join(unique_failed_dates)}"]
            if unique_failed_dates
            else []
            )
            has_any_local_data =updated or len (skipped_dates )>0
            _emit_update_progress(
                progress_callback,
                "TPEX API 下載完成，正在整理日期結果",
                100,
            )
            return {
            'success':has_any_local_data and not unique_failed_dates ,
            'message':(
            f"TPEX 每日股價區間更新未完整：缺少日期 {', '.join(unique_failed_dates)}"
            if unique_failed_dates
            else
            'TPEX 每日股價區間更新完成'
            if has_any_local_data
            else 'TPEX 每日股價區間更新失敗：無可寫入日期'
            ),
            'requested_dates':date_keys ,
            'updated_dates':unique_updated_dates ,
            'fallback_dates':sorted (set (fallback_dates )),
            'skipped_dates':sorted (set (skipped_dates )),
            'failed_dates':unique_failed_dates ,
            'warnings':warnings ,
            'tpex_rows':total_rows ,
            'skipped_rows':total_skipped_rows ,
            'diagnostic_count':sum(
                item['diagnostic_count'] for item in failure_diagnostics
            ),
            'source_dates':unique_updated_dates ,
            'source_custody':source_custody_receipts,
            'failure_diagnostics':list(failure_diagnostics),
            'sync_summary':sync_summary ,
            }
        except Exception as exc :
            logger .exception ("[UpdateService] TPEX daily price range update failed")
            range_failure_message = f'TPEX daily price range update failed: {exc}'
            failure_diagnostics.append(
                {
                    'requested_date':self._date_key(start_date),
                    'phase':'range',
                    'success':False,
                    'result_requested_date':None,
                    'source_date':None,
                    'diagnostic_count':1,
                    'row_count':0,
                    'skipped_count':0,
                    'message':range_failure_message[:_TPEX_FAILURE_MESSAGE_MAX_CHARS],
                    'message_truncated':len(range_failure_message) > _TPEX_FAILURE_MESSAGE_MAX_CHARS,
                    'source_custody_present':False,
                }
            )
            return {
            'success':False ,
            'message':range_failure_message,
            'requested_dates':[],
            'updated_dates':[],
            'fallback_dates':[],
            'skipped_dates':[],
            'failed_dates':[self ._date_key (start_date )],
            'warnings':[f"TPEX 每日股價缺少日期：{self ._date_key (start_date )}"],
            'tpex_rows':0 ,
            'skipped_rows':0 ,
            'diagnostic_count':sum(
                item['diagnostic_count'] for item in failure_diagnostics
            ),
            'source_dates':[],
            'failure_diagnostics':list(failure_diagnostics),
            'sync_summary':None ,
            }

    def _iter_weekday_date_keys (self ,start_date :str ,end_date :str )->list [str ]:
        """Return official trading dates for an update range.

        The historical method name is retained for callers and UI contracts,
        but production execution is now fail-closed on the shared official
        TWSE calendar.  The small ``__new__`` compatibility path is only for
        legacy unit doubles that intentionally do not carry a config object.
        """

        if not hasattr(self, "config"):
            return update_data_normalization .iter_weekday_date_keys (
                start_date, end_date, date_key_fn=self ._date_key
            )

        start_key = self._date_key(start_date)
        end_key = self._date_key(end_date)
        start_day = date.fromisoformat(
            f"{start_key[:4]}-{start_key[4:6]}-{start_key[6:8]}"
        )
        end_day = date.fromisoformat(
            f"{end_key[:4]}-{end_key[4:6]}-{end_key[6:8]}"
        )
        calendar = OfficialTradingCalendar(
            db_path=getattr(self.config, "db_file", None),
            calendar_cache_path=(
                self.project_root / "output" / "paper_execution_eod_replay" / "calendar_cache"
                if (
                    self.project_root / "output" / "paper_execution_eod_replay" / "calendar_cache"
                ).is_dir()
                else None
            ),
        )
        try:
            records = calendar.require_trading_days_in_range(
                start_day,
                end_day,
                allow_online_probe=True,
            )
        except OfficialTradingCalendarError:
            raise
        return [
            str(record["date_str"]).replace("-", "")
            for record in records
            if record.get("is_trading_day") is True
        ]

    def _load_csv_for_sqlite (self ,path :Path ,require_date :bool =False )->Any :
        import pandas as pd # type: ignore[import-untyped]

        if not path .exists ():
            return pd .DataFrame ()
        df =pd .read_csv (path ,encoding ='utf-8-sig',dtype =self ._sqlite_csv_dtype (),low_memory =False )
        if df .empty :
            return df
        normalized =self ._normalize_sqlite_dates (df )
        if require_date and '日期'not in normalized .columns :
            return pd .DataFrame ()
        return normalized

    def _load_daily_price_files_for_sqlite (
    self ,
    start_date :Optional [str ],
    end_date :Optional [str ],
    *,
    strict_source: bool =False,
    directories: Optional[List[Path]] =None,
    )->Any :
        import pandas as pd # type: ignore[import-untyped]

        daily_dirs :list [Path ]=(
            list(directories)
            if directories is not None
            else list(configured_daily_price_dirs(self.config))
        )
        if not daily_dirs :
            return pd .DataFrame ()

        start_key =self ._date_key (start_date )if start_date else None
        end_key =self ._date_key (end_date )if end_date else None
        frames =[]
        for daily_dir in daily_dirs :
            for path in sorted (daily_dir .glob ('*.csv')):
                try:
                    from data_module.daily_price_source_guard import source_date_from_path

                    date_key =source_date_from_path(path)
                except DailyPriceSourceError:
                    if strict_source:
                        raise
                    import logging
                    logging .getLogger (__name__ ).warning (
                    "[UpdateService] skip daily-price CSV with invalid source name: %s",path
                    )
                    continue
                if start_key and date_key <start_key :
                    continue
                if end_key and date_key >end_key :
                    continue
                try:
                    df =pd .read_csv (path ,encoding ='utf-8-sig',dtype =self ._sqlite_csv_dtype (),low_memory =False )
                except Exception:
                    if strict_source:
                        raise
                    raise
                if df .empty :
                    if strict_source:
                        raise DailyPriceSourceError(
                            f"每日股價來源檔為空：{path.name}"
                        )
                    continue
                df =self ._normalize_sqlite_dates (df )
                try:
                    df =validate_daily_price_frame_date(
                        df,
                        path=path,
                        normalize_date=self._date_key,
                    )
                except DailyPriceSourceError:
                    if strict_source:
                        raise
                    import logging
                    logging .getLogger (__name__ ).warning (
                    "[UpdateService] skip daily-price CSV with inconsistent date: %s",path
                    )
                    continue
                if not is_valid_daily_price_frame (df ):
                    if strict_source:
                        raise DailyPriceSourceError(
                            f"每日股價來源 schema 不完整：{path.name}"
                        )
                    import logging
                    logging .getLogger (__name__ ).warning (
                    "[UpdateService] skip invalid daily-price CSV schema: %s",path
                    )
                    continue
                if is_weekend_date_key (date_key )and not official_twse_session_exists (date_key ):
                    if strict_source:
                        raise DailyPriceSourceError(
                            f"每日股價來源缺少週末官方交易證據：{path.name}"
                        )
                    import logging
                    logging .getLogger (__name__ ).warning (
                    "[UpdateService] daily-price session has no official TWSE evidence; skip file: %s",path
                    )
                    continue
                frames .append (df )

        if not frames :
            return pd .DataFrame ()
        return self ._normalize_sqlite_dates (pd .concat (frames ,ignore_index =True ))

    def _load_aggregate_daily_data_for_sqlite(self)->Any:
        """只在具備內容綁定 receipt 時讀取 aggregate 快照。

        測試／legacy caller 若沒有 ``profile=prod`` 仍保留相容 fallback，
        但診斷會標示為 legacy；正式 profile 沒有 receipt 就 fail closed。
        """

        import hashlib
        import json
        import pandas as pd # type: ignore[import-untyped]

        stock_data_file =Path(self.config.stock_data_file)
        daily_df =self ._load_csv_for_sqlite (stock_data_file ,require_date =True )
        if daily_df .empty :
            return daily_df

        profile =str(getattr(self.config, "profile", "")).strip().lower()
        receipt_path =aggregate_receipt_path(stock_data_file)
        if profile != "prod":
            self._last_daily_source_selection ={
                "source_kind":"aggregate_legacy_compatibility",
                "source_version":"legacy-unbound-aggregate",
                "quality_status":"degraded",
                "path":str(stock_data_file.resolve()),
                "receipt_path":str(receipt_path.resolve()),
            }
            return daily_df

        if not receipt_path.exists():
            raise DailyPriceSourceError(
                "正式 profile 不得讀取沒有 source receipt 的 stock_data_whole.csv"
            )
        try:
            payload =json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise DailyPriceSourceError(
                f"整合快照 source receipt 無法讀取：{receipt_path}"
            ) from exc
        if not isinstance(payload, dict):
            raise DailyPriceSourceError("整合快照 source receipt 必須是 JSON object")
        file_sha256 ="sha256:"+hashlib.sha256(stock_data_file.read_bytes()).hexdigest()
        validate_aggregate_receipt_payload(
            payload,
            stock_data_file=stock_data_file,
            actual_frame=daily_df,
            file_sha256=file_sha256,
        )
        self._last_daily_source_selection ={
            "source_kind":"aggregate_receipt",
            "source_version":AGGREGATE_SOURCE_VERSION,
            "quality_status":"accepted",
            "path":str(stock_data_file.resolve()),
            "receipt_path":str(receipt_path.resolve()),
            "source_sha256":file_sha256,
        }
        return daily_df

    def _load_daily_data_for_sqlite (self )->Any :
        import pandas as pd # type: ignore[import-untyped]

        directories =configured_daily_price_dirs(self.config)
        twse_dir =getattr(self.config, "daily_price_dir", None)
        tpex_dir =getattr(self.config, "tpex_daily_price_dir", None)
        twse_dirs =tuple(
            Path(value) for value in (twse_dir,) if value is not None
        )
        tpex_dirs =tuple(
            Path(value) for value in (tpex_dir,) if value is not None
        )
        twse_files, twse_invalid =discover_daily_price_csvs(twse_dirs)
        tpex_files, tpex_invalid =discover_daily_price_csvs(tpex_dirs)
        invalid_files =twse_invalid +tpex_invalid

        # 有任何日期檔時，日期檔是較新且可按檔案驗證的來源；不能先讀
        # stale aggregate 再以 keep=last 假設其內容是同一版本。
        if invalid_files:
            self._last_daily_source_selection ={
                "source_kind":"blocked",
                "source_version":"unknown",
                "quality_status":"rejected",
                "reason":"invalid_daily_price_filename",
                "paths":[str(path.resolve()) for path in invalid_files],
            }
            return pd.DataFrame()

        if twse_files or tpex_files:
            try:
                date_df =self ._load_daily_price_files_for_sqlite(
                    None,
                    None,
                    strict_source=True,
                    directories=list(directories),
                )
            except (DailyPriceSourceError, OSError, ValueError) as exc:
                self._last_daily_source_selection ={
                    "source_kind":"blocked",
                    "source_version":"unknown",
                    "quality_status":"rejected",
                    "reason":"daily_price_file_contract_failed",
                    "detail":str(exc),
                    "paths":[str(path.resolve()) for path in twse_files + tpex_files],
                }
                return pd.DataFrame()
            if date_df.empty:
                self._last_daily_source_selection ={
                    "source_kind":"blocked",
                    "source_version":"unknown",
                    "quality_status":"rejected",
                    "reason":"daily_price_file_empty",
                    "paths":[str(path.resolve()) for path in twse_files + tpex_files],
                }
                return date_df

            # TWSE 日期檔存在時，完全隔離 aggregate；若只有 TPEX 日期檔，
            # aggregate 僅可作為另一個來源，且正式 profile 必須具 receipt。
            if twse_files:
                combined =date_df
                source_kind ="date_files"
            else:
                try:
                    aggregate_df =self ._load_aggregate_daily_data_for_sqlite()
                except DailyPriceSourceError as exc:
                    self._last_daily_source_selection ={
                        "source_kind":"blocked",
                        "source_version":"unknown",
                        "quality_status":"rejected",
                        "reason":"aggregate_source_contract_failed",
                        "detail":str(exc),
                        "paths":[str(path.resolve()) for path in tpex_files],
                    }
                    return pd.DataFrame()
                combined =pd.concat([aggregate_df, date_df], ignore_index=True)
                source_kind ="aggregate_plus_tpex_date_files"
            self._last_daily_source_selection.update({
                "source_kind":source_kind,
                "source_version":"daily-price-date-file-selection.v1",
                "quality_status":"accepted",
                "date_file_paths":[str(path.resolve()) for path in twse_files + tpex_files],
                "aggregate_is_authoritative":bool(twse_files),
            })
        else:
            try:
                combined =self ._load_aggregate_daily_data_for_sqlite()
            except DailyPriceSourceError as exc:
                self._last_daily_source_selection ={
                    "source_kind":"blocked",
                    "source_version":"unknown",
                    "quality_status":"rejected",
                    "reason":"aggregate_source_contract_failed",
                    "detail":str(exc),
                }
                return pd.DataFrame()

        date_col ='日期'
        code_col ='證券代號'
        combined =self ._normalize_sqlite_dates (combined)
        if date_col in combined .columns and code_col in combined .columns :
            combined =combined .drop_duplicates (subset =[date_col ,code_col ],keep ='last')
        return combined

    def _get_stock_name_to_code_map (self )->Dict [str ,str ]:
        """建立證券名稱到證券代號的對照表，合併 SQLite, CSV 與硬編碼對照"""
        name_to_code ={}

        # 1. Fallback 硬編碼對照表 (兜底)
        fallback_map ={
        '元大台灣50':'0050',
        '元大高股息':'0056',
        '富邦科技':'0052',
        '元大MSCI金融':'0055',
        }
        name_to_code .update (fallback_map )

        # 2. 從 CSV 股票數據中讀取對照
        try :
            stock_data_file =getattr (self .config ,'stock_data_file',None )
            if stock_data_file and stock_data_file .exists ():
                import pandas as pd
                required_cols ={'證券代號','證券名稱'}
                df_csv =pd .read_csv (
                stock_data_file ,
                encoding ='utf-8-sig',
                usecols =lambda col :col in required_cols ,
                dtype ={'證券代號':str ,'證券名稱':str },
                low_memory =False ,
                )
                if '證券代號'in df_csv .columns and '證券名稱'in df_csv .columns :
                    csv_map =df_csv .dropna (subset =['證券代號','證券名稱']).drop_duplicates (subset =['證券名稱'],keep ='last')
                    for _ ,row in csv_map .iterrows ():
                        code =self ._stock_code_key (row ['證券代號'])
                        name =str (row ['證券名稱']).strip ()
                        if code and name and code not in ('ETF','UNKNOWN')and name :
                            name_to_code [name ]=code
        except Exception as e :
            import logging
            logging .getLogger (__name__ ).warning (f"[UpdateService] 從 CSV 建立股票代號映射失敗: {e}")

            # 3. 從 SQLite daily_prices 讀取對照 (最高優先順序，覆蓋前面)
        if getattr (self .config ,'use_sqlite',False ):
            try :
                from data_module .db_manager import DBManager
                db =DBManager (self .config )
                query ="SELECT DISTINCT 證券名稱, 證券代號 FROM daily_prices WHERE 證券名稱 IS NOT NULL AND 證券名稱 != '' AND 證券代號 NOT IN ('ETF', 'UNKNOWN');"
                df_prices =db .execute_query (query )
                for _ ,row in df_prices .iterrows ():
                    name =str (row ['證券名稱']).strip ()
                    code =str (row ['證券代號']).strip ()
                    if name and code :
                        name_to_code [name ]=code
            except Exception as e :
                import logging
                logging .getLogger (__name__ ).warning (f"[UpdateService] 從 SQLite daily_prices 建立股票代號映射失敗: {e}")

        return name_to_code

    def _load_broker_branch_csv_for_sqlite (self )->Any :
        import pandas as pd # type: ignore[import-untyped]

        broker_dir =getattr (self .config ,'broker_flow_dir',None )
        if broker_dir is None or not Path (broker_dir ).exists ():
            return pd .DataFrame ()

        frames =[]
        name_to_code_map =self ._get_stock_name_to_code_map ()
        for path in sorted (Path (broker_dir ).glob ('*/meta/merged.csv')):
            df =pd .read_csv (path ,encoding ='utf-8-sig')
            if df .empty :
                continue
            branch_name =path .parents [1 ].name
            rename_map ={
            'date':'日期',
            'counterparty_broker_code':'證券代號',
            'stock_id':'證券代號',
            'stock_code':'證券代號',
            'counterparty_broker_name':'證券名稱',
            'stock_name':'證券名稱',
            'branch_display_name':'分點名稱',
            'branch_name':'分點名稱',
            'buy_lots':'買進張數',
            'sell_lots':'賣出張數',
            'net_lots':'買賣超張數',
            'buy_amount_k_twd':'買進金額千元',
            'sell_amount_k_twd':'賣出金額千元',
            'net_amount_k_twd':'買賣超金額千元',
            # 2026-06-11 前的 MoneyDJ c=B 資料使用 generic qty 名稱。
            'buy_qty':'買進金額千元',
            'sell_qty':'賣出金額千元',
            'net_qty':'買賣超金額千元',
            }
            df =df .rename (columns ={k :v for k ,v in rename_map .items ()if k in df .columns })
            if '證券代號'in df .columns and '證券名稱'in df .columns :
                df ['證券代號']=df ['證券代號'].astype (str ).str .strip ()
                mask =df ['證券代號'].isin (['ETF','UNKNOWN'])
                if mask .any ():
                    mapped =df .loc [mask ,'證券名稱'].astype (str ).str .strip ().map (name_to_code_map )
                    unmapped =df .loc [mask &mapped .isna (),'證券名稱'].unique ()
                    if len (unmapped )>0 :
                        import logging
                        logging .getLogger (__name__ ).warning (f"[UpdateService] Historical ETF repair found unmapped stock name: {unmapped.tolist()}")
                    df .loc [mask ,'證券代號']=mapped .fillna (df .loc [mask ,'證券代號'])
            if '分點名稱'not in df .columns :
                df ['分點名稱']=branch_name
            frames .append (df )

        if not frames :
            return pd .DataFrame ()
        df_all =pd .concat (frames ,ignore_index =True )
        lot_cols =['買進張數','賣出張數','買賣超張數']
        amount_cols =['買進金額千元','賣出金額千元','買賣超金額千元']

        # 確保 metadata 欄位存在
        metadata_cols =['trade_type','lots_observed','amount_observed','lots_rank','amount_rank']
        for col in metadata_cols :
            if col not in df_all .columns :
                if col =='trade_type':
                    df_all [col ]=None
                elif col =='lots_observed':
                    if 'buy_lots'in df_all .columns :
                        df_all [col ]=df_all ['buy_lots'].notna ()
                    elif '買進張數'in df_all .columns :
                        df_all [col ]=df_all ['買進張數'].notna ()
                    else :
                        df_all [col ]=False
                elif col =='amount_observed':
                    if 'buy_amount_k_twd'in df_all .columns :
                        df_all [col ]=df_all ['buy_amount_k_twd'].notna ()
                    elif '買進金額千元'in df_all .columns :
                        df_all [col ]=df_all ['買進金額千元'].notna ()
                    else :
                        df_all [col ]=False
                else :
                    df_all [col ]=None

                    # 轉換為 Nullable Integer (Int64)
        for col in lot_cols +amount_cols :
            if col in df_all .columns :
                df_all [col ]=pd .to_numeric (df_all [col ],errors ='coerce').astype ('Int64')
            else :
                df_all [col ]=pd .Series ([None ]*len (df_all ),dtype ='Int64')
        df_all =self ._infer_broker_metric_ranks (df_all )

        # 計算股數：只由 observed lots 轉換，非 observed 則保持 <NA>
        df_all ['買進股數']=pd .Series ([None ]*len (df_all ),dtype ='Int64')
        df_all ['賣出股數']=pd .Series ([None ]*len (df_all ),dtype ='Int64')
        df_all ['買賣超股數']=pd .Series ([None ]*len (df_all ),dtype ='Int64')

        lots_mask =df_all ['lots_observed']==True
        df_all .loc [lots_mask ,'買進股數']=df_all .loc [lots_mask ,'買進張數']*1000
        df_all .loc [lots_mask ,'賣出股數']=df_all .loc [lots_mask ,'賣出張數']*1000
        df_all .loc [lots_mask ,'買賣超股數']=df_all .loc [lots_mask ,'買賣超張數']*1000

        # 將非 observed amount 的欄位設為 <NA>
        amount_mask =df_all ['amount_observed']==False
        df_all .loc [amount_mask ,'買進金額千元']=None
        df_all .loc [amount_mask ,'賣出金額千元']=None
        df_all .loc [amount_mask ,'買賣超金額千元']=None

        keep_cols =[
        '日期','分點名稱','證券代號','證券名稱',
        '買進股數','賣出股數','買賣超股數',
        *amount_cols ,
        *metadata_cols
        ]
        for col in keep_cols :
            if col not in df_all .columns :
                df_all [col ]=None
        df_all =df_all [keep_cols ]

        normalized =self ._normalize_sqlite_dates (df_all )
        return self ._deduplicate_and_merge_broker_flows (normalized )

    def _load_broker_branch_files_for_sqlite (
    self ,
    start_date :Optional [str ],
    end_date :Optional [str ]
    )->Any :
        import pandas as pd # type: ignore[import-untyped]

        broker_dir =getattr (self .config ,'broker_flow_dir',None )
        if broker_dir is None or not Path (broker_dir ).exists ():
            return pd .DataFrame ()

        start_key =self ._date_key (start_date )if start_date else None
        end_key =self ._date_key (end_date )if end_date else None
        frames =[]
        name_to_code_map =self ._get_stock_name_to_code_map ()

        # 遍歷所有券商分點的目錄
        for branch_dir in sorted (Path (broker_dir ).glob ('*')):
            if not branch_dir .is_dir ()or branch_dir .name in {'meta','logs'}:
                continue
            daily_dir =branch_dir /'daily'
            if not daily_dir .exists ():
                continue

                # 遍歷該分點的每日 CSV 檔
            for path in sorted (daily_dir .glob ('*.csv')):
                date_key =self ._date_key (path .stem )
                if start_key and date_key <start_key :
                    continue
                if end_key and date_key >end_key :
                    continue

                try :
                    df =pd .read_csv (path ,encoding ='utf-8-sig')
                    if df .empty :
                         continue
                    branch_name =branch_dir .name
                    rename_map ={
                    'date':'日期',
                    'counterparty_broker_code':'證券代號',
                    'stock_id':'證券代號',
                    'stock_code':'證券代號',
                    'counterparty_broker_name':'證券名稱',
                    'stock_name':'證券名稱',
                    'branch_display_name':'分點名稱',
                    'branch_name':'分點名稱',
                    'buy_lots':'買進張數',
                    'sell_lots':'賣出張數',
                    'net_lots':'買賣超張數',
                    'buy_amount_k_twd':'買進金額千元',
                    'sell_amount_k_twd':'賣出金額千元',
                    'net_amount_k_twd':'買賣超金額千元',
                    'buy_qty':'買進金額千元',
                    'sell_qty':'賣出金額千元',
                    'net_qty':'買賣超金額千元',
                    }
                    df =df .rename (columns ={k :v for k ,v in rename_map .items ()if k in df .columns })
                    if '證券代號'in df .columns and '證券名稱'in df .columns :
                        df ['證券代號']=df ['證券代號'].astype (str ).str .strip ()
                        mask =df ['證券代號'].isin (['ETF','UNKNOWN'])
                        if mask .any ():
                            mapped =df .loc [mask ,'證券名稱'].astype (str ).str .strip ().map (name_to_code_map )
                            unmapped =df .loc [mask &mapped .isna (),'證券名稱'].unique ()
                            if len (unmapped )>0 :
                                import logging
                                logging .getLogger (__name__ ).warning (f"[UpdateService] Historical ETF repair found unmapped stock name: {unmapped.tolist()}")
                            df .loc [mask ,'證券代號']=mapped .fillna (df .loc [mask ,'證券代號'])
                    if '分點名稱'not in df .columns :
                        df ['分點名稱']=branch_name
                    if '日期'not in df .columns :
                        df ['日期']=date_key
                    frames .append (df )
                except Exception :
                    continue

        if not frames :
            return pd .DataFrame ()
        df_all =pd .concat (frames ,ignore_index =True )
        lot_cols =['買進張數','賣出張數','買賣超張數']
        amount_cols =['買進金額千元','賣出金額千元','買賣超金額千元']

        # 確保 metadata 欄位存在
        metadata_cols =['trade_type','lots_observed','amount_observed','lots_rank','amount_rank']
        for col in metadata_cols :
            if col not in df_all .columns :
                if col =='trade_type':
                    df_all [col ]=None
                elif col =='lots_observed':
                    if 'buy_lots'in df_all .columns :
                        df_all [col ]=df_all ['buy_lots'].notna ()
                    elif '買進張數'in df_all .columns :
                        df_all [col ]=df_all ['買進張數'].notna ()
                    else :
                        df_all [col ]=False
                elif col =='amount_observed':
                    if 'buy_amount_k_twd'in df_all .columns :
                        df_all [col ]=df_all ['buy_amount_k_twd'].notna ()
                    elif '買進金額千元'in df_all .columns :
                        df_all [col ]=df_all ['買進金額千元'].notna ()
                    else :
                        df_all [col ]=False
                else :
                    df_all [col ]=None

                    # 轉換為 Nullable Integer (Int64)
        for col in lot_cols +amount_cols :
            if col in df_all .columns :
                df_all [col ]=pd .to_numeric (df_all [col ],errors ='coerce').astype ('Int64')
            else :
                df_all [col ]=pd .Series ([None ]*len (df_all ),dtype ='Int64')
        df_all =self ._infer_broker_metric_ranks (df_all )

        # 計算股數：只由 observed lots 轉換，非 observed 則保持 <NA>
        df_all ['買進股數']=pd .Series ([None ]*len (df_all ),dtype ='Int64')
        df_all ['賣出股數']=pd .Series ([None ]*len (df_all ),dtype ='Int64')
        df_all ['買賣超股數']=pd .Series ([None ]*len (df_all ),dtype ='Int64')

        lots_mask =df_all ['lots_observed']==True
        df_all .loc [lots_mask ,'買進股數']=df_all .loc [lots_mask ,'買進張數']*1000
        df_all .loc [lots_mask ,'賣出股數']=df_all .loc [lots_mask ,'賣出張數']*1000
        df_all .loc [lots_mask ,'買賣超股數']=df_all .loc [lots_mask ,'買賣超張數']*1000

        # 將非 observed amount 的欄位設為 <NA>
        amount_mask =df_all ['amount_observed']==False
        df_all .loc [amount_mask ,'買進金額千元']=None
        df_all .loc [amount_mask ,'賣出金額千元']=None
        df_all .loc [amount_mask ,'買賣超金額千元']=None

        keep_cols =[
        '日期','分點名稱','證券代號','證券名稱',
        '買進股數','賣出股數','買賣超股數',
        *amount_cols ,
        *metadata_cols
        ]
        for col in keep_cols :
            if col not in df_all .columns :
                df_all [col ]=None
        df_all =df_all [keep_cols ]

        normalized =self ._normalize_sqlite_dates (df_all )
        return self ._deduplicate_and_merge_broker_flows (normalized )

    @staticmethod
    def _infer_broker_metric_ranks (df :Any )->Any :
        """由 MoneyDJ 榜單方向與淨值補齊缺失 rank，不覆蓋已觀測排名。"""
        import pandas as pd # type: ignore[import-untyped]

        required ={'日期','分點名稱','trade_type'}
        if df .empty or not required .issubset (df .columns ):
            return df

        result =df .copy ()
        metric_specs =(
        ('lots_observed','lots_rank','買賣超張數'),
        ('amount_observed','amount_rank','買賣超金額千元'),
        )
        group_cols =['日期','分點名稱','trade_type']

        for observed_col ,rank_col ,value_col in metric_specs :
            if observed_col not in result .columns or value_col not in result .columns :
                continue
            if rank_col not in result .columns :
                result [rank_col ]=pd .Series ([None ]*len (result ),dtype ='Int64')

            observed_mask =result [observed_col ].fillna (False ).astype (bool )
            missing_rank_mask =pd .to_numeric (result [rank_col ],errors ='coerce').isna ()
            eligible =result [observed_mask &missing_rank_mask &result [value_col ].notna ()]

            for group_key ,group in eligible .groupby (group_cols ,dropna =False ,sort =False ):
                trade_type =str (group_key [2 ])
                if trade_type not in {'買超','賣超'}:
                    continue
                ascending =trade_type =='賣超'
                ordered_indexes =group .sort_values (
                value_col ,
                ascending =ascending ,
                kind ='stable',
                ).index
                for rank ,index in enumerate (ordered_indexes ,start =1 ):
                    result .at [index ,rank_col ]=rank

            result [rank_col ]=pd .to_numeric (result [rank_col ],errors ='coerce').astype ('Int64')

        return result

    def _normalize_sqlite_dates (self ,df :Any )->Any :
        return update_data_normalization .normalize_sqlite_dates (
        df ,date_key_fn =self ._date_key ,stock_code_key_fn =self ._stock_code_key
        )

    @staticmethod
    def _sqlite_csv_dtype ()->Dict [str ,Any ]:
        return update_data_normalization .sqlite_csv_dtype ()

    @staticmethod
    def _stock_code_key (value :Any )->str :
        return update_data_normalization .stock_code_key (value )

    def _deduplicate_and_merge_broker_flows (self ,df :Any )->Any :
        import pandas as pd # type: ignore[import-untyped]

        if df .empty :
            return df

        key_cols =['分點名稱','證券代號','日期']
        if 'trade_type'in df .columns :
            key_cols .append ('trade_type')
        dup_mask =df .duplicated (subset =key_cols ,keep =False )
        if not dup_mask .any ():
            return df

            # 如果 df 中缺少 lots_observed/amount_observed 欄位，自動為其動態推導
        df =df .copy ()
        if 'lots_observed'not in df .columns :
            if 'buy_lots'in df .columns :
                df ['lots_observed']=df ['buy_lots'].notna ()
            elif '買進張數'in df .columns :
                has_amt ='買進金額千元'in df .columns
                amt_zero_or_nan =(df ['買進金額千元'].isna ()|(df ['買進金額千元']==0 ))if has_amt else True
                df ['lots_observed']=df ['買進張數'].notna ()&((df ['買進張數']!=0 )|(df .get ('賣出張數',0 )!=0 )|amt_zero_or_nan )
            elif '買進股數'in df .columns :
                has_amt ='買進金額千元'in df .columns
                amt_zero_or_nan =(df ['買進金額千元'].isna ()|(df ['買進金額千元']==0 ))if has_amt else True
                df ['lots_observed']=df ['買進股數'].notna ()&((df ['買進股數']!=0 )|(df .get ('賣出股數',0 )!=0 )|amt_zero_or_nan )
            else :
                df ['lots_observed']=False

        if 'amount_observed'not in df .columns :
            if 'buy_amount_k_twd'in df .columns :
                df ['amount_observed']=df ['buy_amount_k_twd'].notna ()
            elif '買進金額千元'in df .columns :
                has_lots ='買進張數'in df .columns
                lots_zero_or_nan =(df ['買進張數'].isna ()|(df ['買進張數']==0 ))if has_lots else True
                has_vol ='買進股數'in df .columns
                vol_zero_or_nan =(df ['買進股數'].isna ()|(df ['買進股數']==0 ))if has_vol else True
                df ['amount_observed']=df ['買進金額千元'].notna ()&((df ['買進金額千元']!=0 )|(df .get ('賣出金額千元',0 )!=0 )|(lots_zero_or_nan &vol_zero_or_nan ))
            else :
                df ['amount_observed']=False

        df_clean =df [~dup_mask ]
        df_dup =df [dup_mask ]

        resolved_rows =[]
        numeric_cols =[
        '買進股數','賣出股數','買賣超股數',
        '買進金額千元','賣出金額千元','買賣超金額千元'
        ]

        grouped =df_dup .groupby (key_cols ,as_index =False )
        for key_vals ,group in grouped :
            name_series =group ['證券名稱'].dropna ()
            name_series =name_series [name_series .astype (str ).str .strip ()!='']
            stock_name =name_series .iloc [0 ]if not name_series .empty else ''

            resolved_row ={
            '分點名稱':key_vals [0 ],
            '證券代號':key_vals [1 ],
            '日期':key_vals [2 ],
            '證券名稱':stock_name
            }
            if 'trade_type'in key_cols :
                resolved_row ['trade_type']=key_vals [3 ]

                # 1. 識別與合併 metadata 欄位
            metadata_cols =['lots_observed','amount_observed','lots_rank','amount_rank']
            if 'trade_type'not in key_cols :
                metadata_cols .insert (0 ,'trade_type')
            for m_col in metadata_cols :
                if m_col in group .columns :
                    vals =group [m_col ].dropna ()
                    if not vals .empty :
                        if m_col in ['lots_observed','amount_observed']:
                            resolved_row [m_col ]=bool (vals .any ())
                        elif m_col =='trade_type':
                            unique_values =vals .astype (str ).unique ()
                            if len (unique_values )>1 :
                                raise ValueError (
                                f"唯一鍵衝突於 {key_cols}={key_vals}, trade_type 存在衝突: {unique_values.tolist()}"
                                )
                            resolved_row [m_col ]=unique_values [0 ]
                        else :
                            resolved_row [m_col ]=vals .iloc [0 ]
                    else :
                        resolved_row [m_col ]=False if m_col in ['lots_observed','amount_observed']else None
                else :
                    resolved_row [m_col ]=False if m_col in ['lots_observed','amount_observed']else None

                    # 2. 根據 observed 狀態合併數值
            for col in numeric_cols :
                if col in group .columns :
                    is_lots_col =col in ['買進股數','賣出股數','買賣超股數']
                    is_observed =resolved_row ['lots_observed']if is_lots_col else resolved_row ['amount_observed']

                    if not is_observed :
                        resolved_row [col ]=None
                    else :
                        vals =group [col ].dropna ()
                        non_zeros =vals [vals !=0 ].unique ()
                        if len (non_zeros )>1 :
                            raise ValueError (
                            f"唯一鍵衝突於 {key_cols}={key_vals}, 欄位 '{col}' 存在衝突的非零數值: {non_zeros.tolist()}"
                            )
                        elif len (non_zeros )==1 :
                            resolved_row [col ]=int (non_zeros [0 ])
                        else :
                            resolved_row [col ]=0
                else :
                    resolved_row [col ]=None

            resolved_rows .append (resolved_row )

        df_resolved =pd .DataFrame (resolved_rows )
        # 確保 df_resolved 擁有正確的 columns 及 Nullable Int64 型態
        for col in numeric_cols :
            if col in df .columns :
                df_resolved [col ]=pd .to_numeric (df_resolved [col ],errors ='coerce').astype ('Int64')
        for col in metadata_cols :
            if col in df .columns :
                if col in ['lots_observed','amount_observed']:
                    df_resolved [col ]=df_resolved [col ].astype (bool )
                elif col =='trade_type':
                    df_resolved [col ]=df_resolved [col ].astype ('string')
                else :
                    df_resolved [col ]=pd .to_numeric (df_resolved [col ],errors ='coerce').astype ('Int64')

        df_resolved =df_resolved .reindex (columns =df .columns )
        return pd .concat ([df_clean ,df_resolved ],ignore_index =True )

    def _date_key (self ,value :Any )->str :
        return update_data_normalization .date_key (value )

    def _replace_sqlite_dates (self ,db :Any ,table_name :str ,df :Any )->bool :
        if df .empty :
            return True
        df =self ._normalize_sqlite_dates (df )
        date_col ='日期'if '日期'in df .columns else None
        if date_col is None :
            raise ValueError (f"無法從 DataFrame 提取有效日期進行替換: table={table_name}")
        dates =sorted ({str (v )for v in df [date_col ].dropna ().tolist ()if str (v )})
        if not dates :
            raise ValueError (f"無法從 DataFrame 提取有效日期進行替換: table={table_name}")

        try :
            database_path = Path(db.db_path)
            if table_name == 'technical_indicators':
                validate_excluded_price_frame(database_path, df)
                from data_module.formal_technical_raw_alias_repair import (
                    validate_raw_alias_replacement,
                )

                validate_raw_alias_replacement(
                    database_path,
                    _technical_frame_records(df),
                    replace_dates=True,
                )
            if table_name == 'daily_prices':
                df = prepare_daily_price_revision_frame(
                    database_path,
                    df,
                    replace_dates=dates,
                )
            elif table_name == 'market_indices':
                validate_market_replacement(
                    database_path,
                    df.to_dict(orient='records'),
                    replace_dates=True,
                )

            db .ensure_columns (table_name ,list (df .columns ))
            placeholders =','.join ('?'for _ in dates )
            with db .connect ()as conn :
                conn .execute (f'DELETE FROM {table_name} WHERE "{date_col}" IN ({placeholders});',dates )
                df .to_sql (table_name ,conn ,if_exists ='append',index =False )
            return True
        except Exception as e :
            import logging
            logger =logging .getLogger (__name__ )
            logger .error (f"[UpdateService] _replace_sqlite_dates 失敗: table={table_name}, 錯誤={e}")
            raise

    def _upsert_sqlite_rows (self ,db :Any ,table_name :str ,df :Any )->bool :
        if df .empty :
            return True
        df =self ._normalize_sqlite_dates (df )
        code_col ='證券代號'if '證券代號'in df .columns else None
        date_col ='日期'if '日期'in df .columns else None
        if code_col and date_col :
            df =df .drop_duplicates (subset =[code_col ,date_col ],keep ='last')

        try :
            if table_name == 'technical_indicators':
                validate_excluded_price_frame(Path(db.db_path), df)
                from data_module.formal_technical_raw_alias_repair import (
                    prepare_raw_alias_upsert_frame,
                )

                df = prepare_raw_alias_upsert_frame(Path(db.db_path), df)
            if table_name == 'daily_prices':
                df = prepare_daily_price_revision_frame(
                    Path(db.db_path),
                    df,
                )

            db .ensure_columns (table_name ,list (df .columns ))
            with db .connect ()as conn :
                table_columns =tuple (row ["name"]for row in conn .execute (f"PRAGMA table_info({table_name});").fetchall ())
                columns =tuple (column for column in df .columns if column in table_columns )
                required_columns =("證券代號","日期")
                missing =[column for column in required_columns if column not in columns ]
                if missing :
                    raise ValueError (f"{table_name} upsert 缺少必要欄位: {missing}")

                quoted_columns =", ".join (f'"{column}"'for column in columns )
                placeholders =", ".join ("?"for _ in columns )
                update_columns =tuple (column for column in columns if column not in required_columns )
                conflict_clause ='ON CONFLICT("證券代號", "日期") DO NOTHING'
                if update_columns :
                    update_clause =", ".join (f'"{column}" = excluded."{column}"'for column in update_columns )
                    conflict_clause =f'ON CONFLICT("證券代號", "日期") DO UPDATE SET {update_clause}'
                sql =f"INSERT INTO {table_name} ({quoted_columns}) VALUES ({placeholders}) {conflict_clause}"
                values =[tuple (row [column ]for column in columns )for row in df [list (columns )].to_dict (orient ='records')]
                conn .executemany (sql ,values )
            return True
        except Exception as e :
            import logging
            logger =logging .getLogger (__name__ )
            logger .error (f"[UpdateService] _upsert_sqlite_rows 失敗: table={table_name}, 錯誤={e}")
            return False

    def _replace_sqlite_table (self ,db :Any ,table_name :str ,df :Any )->bool :
        if df .empty :
            return True

        try :
            database_path = Path(db.db_path)
            if table_name == 'technical_indicators':
                validate_excluded_price_frame(database_path, df)
                from data_module.formal_technical_raw_alias_repair import (
                    validate_raw_alias_replacement,
                )

                validate_raw_alias_replacement(
                    database_path,
                    _technical_frame_records(df),
                    replace_all=True,
                )
            if table_name == 'daily_prices':
                df = prepare_daily_price_revision_frame(
                    database_path,
                    df,
                    replace_all=True,
                )
            elif table_name == 'market_indices':
                validate_market_replacement(
                    database_path,
                    df.to_dict(orient='records'),
                    replace_all=True,
                )

            db .ensure_columns (table_name ,list (df .columns ))
            with db .connect ()as conn :
                conn .execute (f'DELETE FROM {table_name};')
                df .to_sql (table_name ,conn ,if_exists ='append',index =False )
            return True
        except Exception as e :
            import logging
            logger =logging .getLogger (__name__ )
            logger .error (f"[UpdateService] _replace_sqlite_table 失敗: table={table_name}, 錯誤={e}")
            raise

    def update_daily (
    self ,
    start_date :str ,
    end_date :str ,
    delay_seconds :float =4.0 ,
    progress_callback :Optional [Callable[[str ,int ],None ]]=None ,
    cancel_callback :Optional [Callable[[],bool ]]=None
    )->Dict [str ,Any ]:
        """更新每日股票數據

        在指定日期範圍內查找缺失的日期並下載

        Args:
            start_date: 開始日期（YYYY-MM-DD）- 用於查找缺失日期的範圍
            end_date: 結束日期（YYYY-MM-DD）- 用於查找缺失日期的範圍
            delay_seconds: 每次請求間隔（秒）

        Returns:
            dict: {
                'success': bool,
                'message': str,
                'updated_dates': list[str],
            'failed_dates': list[str],
            'progress_callback': optional callback receiving (message, percentage)
            'cancelled': optional bool indicating a cooperative cancellation
            }
        """
        import subprocess
        import os
        import sys
        import logging
        import re
        from datetime import datetime ,timedelta
        from data_module .data_loader import DataLoader

        logger =logging .getLogger (__name__ )

        def cancelled_result(message: str) -> Dict [str ,Any ]:
            _emit_update_progress(progress_callback, message, 100)
            return {
            'success':False ,
            'cancelled':True ,
            'message':message ,
            'updated_dates':[] ,
            'failed_dates':[] ,
            }

        if _is_cancel_requested(cancel_callback):
            return cancelled_result("TWSE 每日股價更新已取消（尚未開始）")

        # ✅ 記錄輸入參數
        logger .info (
        f"[UpdateService] 開始更新每日股票數據: "
        f"start_date={start_date}, end_date={end_date}, delay_seconds={delay_seconds}"
        )

        # 調用 batch_update_daily_data.py
        script_path =self .scripts_dir /'batch_update_daily_data.py'
        logger .debug (f"[UpdateService] 更新腳本路徑: {script_path}")
        if not script_path .exists ():
            logger .error (f"[UpdateService] 找不到更新腳本: {script_path}")
            return {
            'success':False ,
            'message':f'找不到更新腳本: {script_path}',
            'updated_dates':[],
            'failed_dates':[]
            }

        try :
        # 先做本地缺漏檢查：若指定區間已完整且檔案皆已存在，直接回報完成，避免重複跑大量日期檢查
            missing_dates :list [str ]=[]
            _emit_update_progress(progress_callback, "檢查 TWSE 每日股價缺漏", 0)
            loader =DataLoader (self .config )
            official_date_keys = self._iter_weekday_date_keys(start_date, end_date)
            for trade_date_key in official_date_keys:
                if _is_cancel_requested(cancel_callback):
                    return cancelled_result("TWSE 每日股價更新已取消（檢查日期缺漏時）")
                trade_date = (
                    f"{trade_date_key[:4]}-{trade_date_key[4:6]}-{trade_date_key[6:8]}"
                )
                if not loader .get_daily_price_file (trade_date ).exists ():
                    missing_dates .append (trade_date )

            if not missing_dates :
                logger .info ("[UpdateService] 目標區間每日股價檔案皆已存在，跳過 batch 更新")
                _emit_update_progress(
                    progress_callback,
                    "TWSE 每日股價檔案皆已存在，無需 API 下載",
                    100,
                )
                return {
                'success':True ,
                'message':'每日股價檔案已是最新，無需更新',
                'updated_dates':[],
                'failed_dates':[]
                }

                # 僅針對缺漏區段做更新（避免每次都掃整段 2014~現在）
            start_date =missing_dates [0 ]

            # 執行腳本（腳本內部會檢查文件是否已存在，只下載缺失的）
            import tempfile
            from pathlib import Path as _Path

            command =[
            sys .executable ,str (script_path ),
            '--start-date',start_date ,
            '--end-date',end_date ,
            '--delay-min',str (delay_seconds ),
            '--delay-max',str (delay_seconds )]
            configured_data_root =getattr(self .config ,'data_root',None )
            configured_output_root =getattr(self .config ,'output_root',None )
            if configured_data_root is not None:
                command[4:4] =['--data-root',str (configured_data_root )]
            if configured_output_root is not None:
                command[4:4] =['--output-root',str (configured_output_root )]
            cancellation_requested =False
            if progress_callback is None and cancel_callback is None:
                # 無 UI callback 時保留既有 run() 路徑，讓外部 service double／CLI
                # 可以繼續攔截 subprocess.run；有 callback 才啟用逐行進度。
                with tempfile .NamedTemporaryFile (mode ='w+',delete =False ,suffix ='.log',encoding ='utf-8')as output_file :
                    output_path =output_file .name
                    result =subprocess .run (
                    command ,
                    stdout =output_file ,
                    stderr =subprocess .STDOUT ,
                    text =True ,
                    encoding ='utf-8'
                    )
                output_path_obj =_Path (output_path )
                try :
                    output =output_path_obj .read_text (encoding ='utf-8',errors ='ignore')
                except Exception :
                    output =''
                finally :
                    output_path_obj .unlink (missing_ok =True )
                return_code =result .returncode
            else:
                output_path_obj =None
                output_lines :list [str ]=[]
                try :
                    with tempfile .NamedTemporaryFile (mode ='w+',delete =False ,suffix ='.log',encoding ='utf-8')as output_file :
                        output_path =output_file .name
                        output_path_obj =_Path (output_path )
                        process =subprocess .Popen (
                        command ,
                        stdout =subprocess .PIPE ,
                        stderr =subprocess .STDOUT ,
                        text =True ,
                        encoding ='utf-8',
                        errors ='replace',
                        bufsize =1 ,
                        )
                        if process .stdout is not None :
                            for line in iter (process .stdout .readline ,''):
                                output_file .write (line )
                                output_file .flush ()
                                output_lines .append (line )
                                if _is_cancel_requested(cancel_callback):
                                    # batch 腳本可能正在直接寫入 CSV；不強制終止子程序，
                                    # 先完整收尾目前請求，再把結果明確標示為已取消。
                                    cancellation_requested =True
                                match =re .search (
                                r'\[(\d+)/(\d+)\].*?(\d{4}-\d{2}-\d{2})',
                                line ,
                                )
                                if match :
                                    index =int (match .group (1))
                                    total =int (match .group (2))
                                    percentage =(index *100 )//total if total else 0
                                    _emit_update_progress (
                                    progress_callback ,
                                    f"TWSE API 下載 {match .group (3)}（{index}/{total}）",
                                    percentage ,
                                    )
                        return_code =process .wait ()
                        output_file .flush ()
                finally :
                    if output_path_obj is not None :
                        output_path_obj .unlink (missing_ok =True )
                output =''.join (output_lines )

            if cancellation_requested or _is_cancel_requested(cancel_callback):
                return cancelled_result(
                    "TWSE 每日股價更新已取消；目前 API 請求已安全收尾，請重新檢查資料狀態"
                )

            if return_code ==0 :
                parsed_result =parse_daily_update_output (output ,missing_dates )
                _emit_update_progress (
                    progress_callback ,
                    "TWSE API 下載完成，正在解析日期結果",
                    100,
                )
                if parsed_result ["success"]:
                    logger .info ("[UpdateService] 每日股價更新完成: %s",parsed_result ["message"])
                else :
                    logger .warning ("[UpdateService] 每日股價更新失敗: %s",parsed_result ["message"])
                return parsed_result

            logger .error (f"[UpdateService] 更新失敗: {output}")
            _emit_update_progress(progress_callback, "TWSE API 下載程序失敗", 100)
            return {
            'success':False ,
            'message':f'更新失敗：{output}',
            'updated_dates':[],
            'failed_dates':[]
            }
        except Exception as e :
            import traceback
            logger .error (f"[UpdateService] 執行更新時發生異常: {str(e)}")
            logger .error (traceback .format_exc ())
            return {
            'success':False ,
            'message':f'執行更新時發生錯誤：{str(e)}\n{traceback.format_exc()}',
            'updated_dates':[],
            'failed_dates':[]
            }

    def update_market (
    self ,
    start_date :str ,
    end_date :str,
    *,
    capture_manifests: Optional[List[Path]] = None,
    )->Dict [str ,Any ]:
        """更新大盤指數數據

        Args:
            start_date: 開始日期（YYYY-MM-DD）
            end_date: 結束日期（YYYY-MM-DD）

        Returns:
            dict: {
                'success': bool,
                'message': str,
                'updated_dates': list[str],
                'failed_dates': list[str]
            }
        """
        import subprocess
        import os
        import sys
        import logging
        import traceback
        import re

        logger =logging .getLogger (__name__ )
        # ✅ 記錄輸入參數
        logger .info (
        f"[UpdateService] 開始更新大盤指數數據: "
        f"start_date={start_date}, end_date={end_date}"
        )

        try :
        # 動態導入並調用 batch_update_market_index 函數
            import importlib .util

            script_path =self .scripts_dir /'batch_update_market_and_industry_index.py'
            logger .debug (f"[UpdateService] 更新腳本路徑: {script_path}")

            if not script_path .exists ():
                error_msg =f'找不到更新腳本: {script_path}'
                logger .error (f"[UpdateService] {error_msg}")
                return {
                'success':False ,
                'message':error_msg ,
                'updated_dates':[],
                'failed_dates':[]
                }

                # 動態導入模組
            try :
                spec =importlib .util .spec_from_file_location ("batch_update_market_and_industry_index",script_path )
                if spec is None or spec .loader is None :
                    raise ImportError (f"無法創建模組規格: {script_path}")

                update_module =importlib .util .module_from_spec (spec )
                spec .loader .exec_module (update_module )
                logger .debug (f"[UpdateService] 模組導入成功")
            except Exception as e :
                error_msg =f"導入更新模組時發生錯誤: {str(e)}"
                logger .error (f"[UpdateService] {error_msg}")
                logger .error (traceback .format_exc ())
                return {
                'success':False ,
                'message':error_msg ,
                'updated_dates':[],
                'failed_dates':[]
                }

                # 檢查函數是否存在
            if not hasattr (update_module ,'batch_update_market_index'):
                error_msg =f"更新模組中找不到 batch_update_market_index 函數"
                logger .error (f"[UpdateService] {error_msg}")
                return {
                'success':False ,
                'message':error_msg ,
                'updated_dates':[],
                'failed_dates':[]
                }

                # 執行更新函數
            logger .info (f"[UpdateService] 開始執行大盤指數更新函數")
            try :
            # ✅ 傳遞 config 給更新函數（如果它支持的話）
                import inspect
                update_func =update_module .batch_update_market_index
                sig =inspect .signature (update_func )
                params =list (sig .parameters .keys ())

                update_kwargs: Dict[str, Any] = {
                    "start_date": start_date,
                    "end_date": end_date,
                }
                if 'config' in params:
                    logger.debug("更新函數支持 config 參數，傳遞配置")
                    update_kwargs["config"] = self.config
                if capture_manifests is not None and 'capture_manifests' in params:
                    update_kwargs["capture_manifests"] = capture_manifests
                result = update_func(**update_kwargs)
                logger .info (f"[UpdateService] 大盤指數更新函數執行完成")

                # 解析結果（函數可能沒有返回值）
                if result is None :
                # 函數沒有返回值，假設成功
                    return {
                    'success':True ,
                    'message':'大盤指數更新完成',
                    'updated_dates':[],
                    'failed_dates':[]
                    }
                elif isinstance (result ,dict ):
                    return {
                    'success':result .get ('success',True ),
                    'message':result .get ('message','更新完成'),
                    'updated_dates':result .get ('updated_dates',[]),
                    'failed_dates':result .get ('failed_dates',[])
                    }
                elif isinstance (result ,bool ):
                    return {
                    'success':result ,
                    'message':'大盤指數更新完成' if result else '大盤指數更新失敗（批次更新回傳失敗）',
                    'updated_dates':[],
                    'failed_dates':[] if result else [start_date]
                    }
                else :
                # 不認得的回傳型別不能假設成功，避免吞掉批次失敗
                    return {
                    'success':False ,
                    'message':f'大盤指數更新失敗（批次回傳型別無法辨識: {type(result).__name__}）',
                    'updated_dates':[],
                    'failed_dates':[start_date]
                    }
            except Exception as e :
                error_msg =f"執行大盤指數更新函數時發生錯誤: {str(e)}"
                logger .error (f"[UpdateService] {error_msg}")
                logger .error (traceback .format_exc ())
                return {
                'success':False ,
                'message':error_msg ,
                'updated_dates':[],
                'failed_dates':[]
                }

        except Exception as e :
            error_msg =f"更新大盤指數數據時發生異常: {str(e)}"
            logger .error (f"[UpdateService] {error_msg}")
            logger .error (traceback .format_exc ())
            return {
            'success':False ,
            'message':error_msg ,
            'updated_dates':[],
            'failed_dates':[]
            }

    def publish_taiex_market_index(
        self,
        *,
        capture_manifests: List[Path],
        market_update_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """以 TAIEX 複合鍵同步完整 CSV，保留其他同日指數列。"""
        from data_module.taiex_market_index_publication import publish_taiex_market_index

        return publish_taiex_market_index(
            config=self.config,
            capture_manifests=capture_manifests,
            market_update_result=market_update_result,
        )

    def update_industry (
    self ,
    start_date :str ,
    end_date :str ,
    *,
    reverify_unknown_legacy_dates: bool = False,
    )->Dict [str ,Any ]:
        """更新產業指數數據

        Args:
            start_date: 開始日期（YYYY-MM-DD）
            end_date: 結束日期（YYYY-MM-DD）

        Returns:
            dict: {
                'success': bool,
                'message': str,
                'updated_dates': list[str],
                'failed_dates': list[str]
            }
        """
        import subprocess
        import os
        import sys
        import logging
        import traceback
        import re

        logger =logging .getLogger (__name__ )
        # Block legacy whole-CSV synchronization before any industry update
        # work; only a verified capture projection may clear this guard.
        self._industry_update_block_legacy_sync = True
        self._industry_update_succeeded_without_capture = False
        self._pending_industry_batch_partial = False
        self._pending_industry_failed_dates = []
        self._pending_industry_unknown_legacy_dates = []
        self._pending_industry_capture_manifests = []
        self._pending_industry_csv_before = None
        self._pending_industry_csv_after_sha256 = None

        # ✅ 記錄輸入參數
        logger .info (
        f"[UpdateService] 開始更新產業指數數據: "
        f"start_date={start_date}, end_date={end_date}"
        )

        try :
        # 動態導入並調用 batch_update_industry_index 函數
            import importlib .util

            script_path =self .scripts_dir /'batch_update_market_and_industry_index.py'
            logger .debug (f"[UpdateService] 更新腳本路徑: {script_path}")

            if not script_path .exists ():
                error_msg =f'找不到更新腳本: {script_path}'
                logger .error (f"[UpdateService] {error_msg}")
                return {
                'success':False ,
                'message':error_msg ,
                'updated_dates':[],
                'failed_dates':[]
                }

                # 動態導入模組
            try :
                spec =importlib .util .spec_from_file_location ("batch_update_market_and_industry_index",script_path )
                if spec is None or spec .loader is None :
                    raise ImportError (f"無法創建模組規格: {script_path}")

                update_module =importlib .util .module_from_spec (spec )
                spec .loader .exec_module (update_module )
                logger .debug (f"[UpdateService] 模組導入成功")
            except Exception as e :
                error_msg =f"導入更新模組時發生錯誤: {str(e)}"
                logger .error (f"[UpdateService] {error_msg}")
                logger .error (traceback .format_exc ())
                return {
                'success':False ,
                'message':error_msg ,
                'updated_dates':[],
                'failed_dates':[]
                }

                # 檢查函數是否存在
            if not hasattr (update_module ,'batch_update_industry_index'):
                error_msg =f"更新模組中找不到 batch_update_industry_index 函數"
                logger .error (f"[UpdateService] {error_msg}")
                return {
                'success':False ,
                'message':error_msg ,
                'updated_dates':[],
                'failed_dates':[]
                }

            # 執行更新函數
            logger .info (f"[UpdateService] 開始執行產業指數更新函數")
            capture_manifests: List[Path] = []
            batch_outcome: Dict[str, Any] = {}
            before_csv: bytes | None = None
            try :
            # ✅ 傳遞 config 給更新函數（如果它支持的話）
                import inspect
                update_func =update_module .batch_update_industry_index
                sig =inspect .signature (update_func )
                signature_parameters = list(sig.parameters.values())
                params = [parameter.name for parameter in signature_parameters]
                csv_path = Path(self.config.industry_index_file)
                before_csv = csv_path.read_bytes() if csv_path.is_file() else None

                update_kwargs: Dict[str, Any] = {
                    'start_date': start_date,
                    'end_date': end_date,
                }
                if 'config' in params:
                    logger.debug("更新函數支持 config 參數，傳遞配置")
                    update_kwargs['config'] = self.config
                if 'capture_manifests' in params:
                    update_kwargs['capture_manifests'] = capture_manifests
                if 'batch_outcome' in params:
                    update_kwargs['batch_outcome'] = batch_outcome
                supports_legacy_reverification = (
                    'reverify_unknown_legacy_dates' in params
                )
                if reverify_unknown_legacy_dates and not supports_legacy_reverification:
                    message = (
                        '已要求重新擷取未知 legacy 產業日期，但載入的批次更新器未明確支援此選項'
                    )
                    logger.error(message)
                    return {
                        'success': False,
                        'partial': False,
                        'message': message,
                        'updated_dates': [],
                        'recovered_dates': [],
                        'failed_dates': [],
                        'verified_skipped_dates': [],
                        'unverified_legacy_dates': [],
                        'pending_projection_dates': [],
                        'capture_manifests': [],
                        'source_status': 'legacy_reverification_contract_unsupported',
                        'projection_status': 'not_started',
                    }
                if reverify_unknown_legacy_dates:
                    update_kwargs['reverify_unknown_legacy_dates'] = True
                result = update_func(**update_kwargs)
                if capture_manifests:
                    self._pending_industry_capture_manifests = list(capture_manifests)
                    self._pending_industry_csv_before = before_csv
                    if csv_path.is_file():
                        self._pending_industry_csv_after_sha256 = hashlib.sha256(
                            csv_path.read_bytes()
                        ).hexdigest()
                logger .info (f"[UpdateService] 產業指數更新函數執行完成")

                # Keep successful captures date-scoped while preserving the
                # batch failure signal if any requested dates were rejected.
                if isinstance(result, dict):
                    result_success = bool(result.get('success', True))
                    updated_dates = list(result.get('updated_dates', []))
                    recovered_dates = list(result.get('recovered_dates', []))
                    failed_dates = list(result.get('failed_dates', []))
                    result_message = str(result.get('message', '更新完成'))
                elif result is None:
                    result_success = True
                    updated_dates = []
                    recovered_dates = []
                    failed_dates = []
                    result_message = '產業指數更新完成'
                elif isinstance(result, bool):
                    result_success = result
                    updated_dates = []
                    recovered_dates = []
                    failed_dates = [] if result else [start_date]
                    result_message = (
                        '產業指數更新完成'
                        if result
                        else '產業指數更新失敗（批次更新回傳失敗）'
                    )
                else:
                    result_success = False
                    updated_dates = []
                    recovered_dates = []
                    failed_dates = [start_date]
                    result_message = (
                        f'產業指數更新失敗（批次回傳型別無法辨識: {type(result).__name__}）'
                    )

                if batch_outcome:
                    result_success = result_success and bool(
                        batch_outcome.get('success', result_success)
                    )
                    updated_dates = list(batch_outcome.get('updated_dates', updated_dates))
                    recovered_dates = list(batch_outcome.get('recovered_dates', recovered_dates))
                    failed_dates = list(batch_outcome.get('failed_dates', failed_dates))
                    source_status = batch_outcome.get('source_status')
                    verified_skipped_dates = list(batch_outcome.get('verified_skipped_dates', []))
                    unverified_legacy_dates = list(batch_outcome.get('unverified_legacy_dates', []))
                    pending_projection_dates = list(
                        batch_outcome.get('pending_projection_dates', [])
                    )
                else:
                    source_status = None
                    recovered_dates = []
                    verified_skipped_dates = []
                    unverified_legacy_dates = []
                    pending_projection_dates = []
                if not result_success and not failed_dates:
                    if not unverified_legacy_dates:
                        failed_dates = [start_date]
                failed_dates = sorted(set(str(value) for value in failed_dates))
                unverified_legacy_dates = sorted(set(str(value) for value in unverified_legacy_dates))
                if unverified_legacy_dates and not capture_manifests:
                    result_success = False
                    result_message = (
                        '保留既有 legacy CSV 日期為 unknown；本次沒有新的 TWSE capture 或更新證據'
                    )
                self._pending_industry_unknown_legacy_dates = unverified_legacy_dates
                self._pending_industry_failed_dates = failed_dates
                self._pending_industry_batch_partial = bool(
                    capture_manifests
                    and (failed_dates or not result_success or unverified_legacy_dates)
                )
                self._industry_update_succeeded_without_capture = bool(
                    result_success and not failed_dates and not capture_manifests
                )
                result_message = (
                    f'{result_message}；已有 capture 僅涵蓋成功日期，整批狀態為 partial'
                    if self._pending_industry_batch_partial
                    else result_message
                )
                return {
                    'success': result_success and not failed_dates,
                    'partial': self._pending_industry_batch_partial,
                    'message': result_message,
                    'updated_dates': updated_dates,
                    'recovered_dates': recovered_dates,
                    'failed_dates': failed_dates,
                    'verified_skipped_dates': verified_skipped_dates,
                    'unverified_legacy_dates': unverified_legacy_dates,
                    'pending_projection_dates': pending_projection_dates,
                    'source_status': source_status,
                    'projection_status': (
                        'pending_csv_sqlite_readback'
                        if capture_manifests
                        else 'not_started'
                    ),
                    'capture_manifests':[str(path) for path in capture_manifests],
                }
            except Exception as e :
                error_msg =f"執行產業指數更新函數時發生錯誤: {str(e)}"
                logger .error (f"[UpdateService] {error_msg}")
                logger .error (traceback .format_exc ())
                captured_dates: List[str] = []
                if capture_manifests:
                    self._pending_industry_capture_manifests = list(capture_manifests)
                    self._pending_industry_csv_before = before_csv
                    csv_path = Path(self.config.industry_index_file)
                    if csv_path.is_file():
                        self._pending_industry_csv_after_sha256 = hashlib.sha256(
                            csv_path.read_bytes()
                        ).hexdigest()
                    self._pending_industry_batch_partial = True
                try:
                    from data_module.twse_industry_index_capture import verify_capture_receipt
                except Exception:
                    logger.exception(
                        "無法驗證 batch exception 前已保存的 TWSE capture receipts"
                    )
                else:
                    for manifest in capture_manifests:
                        try:
                            receipt = verify_capture_receipt(
                                manifest, self.config.output_root,
                            )
                            captured_dates.append(str(receipt["source_date"]))
                        except Exception:
                            logger.exception(
                                "跳過無法驗證的 exception 前 capture date: %s",
                                manifest,
                            )

                failure_code = (
                    "batch_exception_after_capture"
                    if capture_manifests
                    else "batch_exception_without_capture"
                )
                partial_reason = (
                    f"{failure_code}; exact failed date unknown within requested range "
                    f"{start_date}..{end_date}"
                )
                self._pending_industry_failed_dates = []
                self._pending_industry_unknown_legacy_dates = []
                self._industry_update_succeeded_without_capture = False
                return {
                'success':False ,
                'partial':bool(capture_manifests),
                'message':f'{error_msg}；{partial_reason}' ,
                'updated_dates':sorted(set(captured_dates)),
                'failed_dates':[],
                'capture_manifests':[str(path) for path in capture_manifests],
                'failure_date_unknown':True,
                'failure_date_range':{
                    'start_date':start_date,
                    'end_date':end_date,
                },
                'partial_reason':partial_reason,
                'failure_reason_code':failure_code,
                }

        except Exception as e :
            error_msg =f"更新產業指數數據時發生異常: {str(e)}"
            logger .error (f"[UpdateService] {error_msg}")
            logger .error (traceback .format_exc ())
            return {
            'success':False ,
            'message':error_msg ,
            'updated_dates':[],
            'failed_dates':[]
            }

    def _quote_sql_identifier (self ,identifier :str )->str :
        return '"'+str (identifier ).replace ('"','""')+'"'

    def _sqlite_status_db_exists(self) -> bool:
        """確認狀態讀取的 SQLite 已存在；不可為了查狀態建立空 DB。"""
        db_file = getattr(self.config, "db_file", None)
        if not db_file:
            return False
        return Path(str(db_file)).is_file()

    def _read_freshness_receipt(self) -> Dict[str, Any] | None:
        """唯讀載入 scheduled freshness receipt，供既有更新頁 status projection 使用。"""

        output_root = getattr(self.config, "output_root", None)
        if output_root is None:
            return None
        path = Path(str(output_root)) / "scheduled" / "data_freshness" / "latest_status.json"
        if not path.is_file():
            return None
        try:
            import json

            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _freshness_receipt_binding(self) -> FreshnessReceiptBinding:
        """建立 receipt 必須符合的目前路徑、日曆政策與查詢時鐘。"""
        candidate_path = configured_candidate_db_path()
        return FreshnessReceiptBinding(
            data_root=str(getattr(self.config, "data_root", "")),
            db_path=str(getattr(self.config, "db_file", "")),
            output_root=str(getattr(self.config, "output_root", "")),
            candidate_db_path=str(candidate_path) if candidate_path is not None else None,
            evaluated_at=datetime.now(timezone.utc),
        )

    def _sqlite_unavailable_status(self) -> Dict[str, Any]:
        """回傳明確 unavailable payload，讓 UI／一鍵更新不會假裝成功。"""
        db_file = getattr(self.config, "db_file", "")
        return {
            "latest_date": None,
            "total_records": 0,
            "status": "unavailable",
            "message": f"SQLite 資料庫不存在：{db_file}",
        }

    def _sqlite_status_manager(self) -> ReadOnlySQLiteManager:
        """建立狀態查詢專用的 query-only SQLite adapter。"""
        return ReadOnlySQLiteManager(self.config.db_file)

    @staticmethod
    def _annotate_sqlite_read_mode(
        payload: Dict[str, Any],
        db: ReadOnlySQLiteManager,
    ) -> Dict[str, Any]:
        """揭露 Windows lock 下的 immutable snapshot fallback，避免假裝即時。"""
        if db.last_read_mode != "immutable_fallback":
            return payload
        annotated = dict(payload)
        warnings = list(annotated.get("warnings") or annotated.get("quality_warnings") or [])
        warnings.append(
            "SQLite 目前使用 immutable 唯讀快照；可能只反映最後已提交內容，請停止其他寫入後重查"
        )
        annotated["warnings"] = list(dict.fromkeys(str(item) for item in warnings if str(item).strip()))
        annotated["read_mode"] = "immutable_fallback"
        return annotated

    def _first_existing_column (self ,columns :Any ,candidates :list [str ])->Optional [str ]:
        column_set ={str (col )for col in columns }
        for candidate in candidates :
            if candidate in column_set :
                return candidate
        return None

    def _status_from_sqlite (self ,table_name :str )->Dict [str ,Any ]:
        """從 SQLite 資料庫極速獲取指定資料表的狀態"""
        if not self._sqlite_status_db_exists():
            return self._sqlite_unavailable_status()
        try :
            db =self ._sqlite_status_manager ()
            columns =db .get_table_columns (table_name )
            date_column =self ._first_existing_column (
            columns ,
            ['日期','日期','date','Date','trade_date','trading_date'],
            )
            table_sql =self ._quote_sql_identifier (table_name )
            if date_column :
                date_sql =self ._quote_sql_identifier (date_column )
                query =f"SELECT COUNT(*) as count, MAX({date_sql}) as max_date FROM {table_sql};"
            else :
                query =f"SELECT COUNT(*) as count, NULL as max_date FROM {table_sql};"
            df =db .execute_query (query )
            if not df .empty :
                cnt =int (df .iloc [0 ]['count'])
                max_d =df .iloc [0 ]['max_date']

                max_date_str =None
                if max_d :
                    max_d_str =str (max_d )
                    if len (max_d_str )==8 :
                        max_date_str =f"{max_d_str[:4]}-{max_d_str[4:6]}-{max_d_str[6:]}"
                    else :
                        max_date_str =max_d_str

                return self._annotate_sqlite_read_mode({
                'latest_date':max_date_str ,
                'total_records':cnt ,
                'status':'ok'if cnt >0 else 'empty'
                }, db)
            return self._annotate_sqlite_read_mode(
                {'latest_date':None ,'total_records':0 ,'status':'empty'}, db
            )
        except Exception as e :
            import logging
            logging .getLogger (__name__ ).warning (f"[UpdateService] 從 SQLite 獲取表 {table_name} 狀態失敗: {e}")
            return {'latest_date':None ,'total_records':0 ,'status':f'error: {e}'}

    def _monthly_revenue_status_from_sqlite (self )->Dict [str ,Any ]:
        """Read monthly revenue status from the fundamental SQLite table."""
        if not self._sqlite_status_db_exists():
            return self._sqlite_unavailable_status()
        try :
            db =self ._sqlite_status_manager ()
            today =_monthly_revenue_status_today ()
            df =db .execute_query (
            """
                WITH period_availability AS (
                    SELECT
                        period,
                        MAX(available_date) AS fully_available_date
                    FROM fundamental_monthly_revenues
                    GROUP BY period
                )
                SELECT
                    COUNT(*) AS count,
                    MIN(period) AS min_period,
                    MAX(period) AS max_period,
                    MAX(as_of_date) AS max_as_of_date,
                    COUNT(DISTINCT stock_code) AS stock_count,
                    COUNT(DISTINCT period) AS period_count,
                    (SELECT MAX(period) FROM period_availability WHERE fully_available_date <= ?) AS latest_available_period,
                    (SELECT MAX(fully_available_date) FROM period_availability WHERE fully_available_date <= ?) AS latest_available_date,
                    (SELECT MIN(fully_available_date) FROM period_availability WHERE fully_available_date > ?) AS next_available_date,
                    (SELECT COUNT(*) FROM period_availability WHERE fully_available_date > ?) AS pending_period_count
                FROM fundamental_monthly_revenues;
                """,
                (today ,today ,today ,today ),
            )
            if df .empty :
                return {'latest_date':None ,'total_records':0 ,'status':'empty'}

            row =df .iloc [0 ]
            count =int (row ['count']or 0 )
            payload = {
            'latest_date':row ['max_as_of_date']if count else None ,
            'latest_period':row ['max_period']if count else None ,
            'earliest_date':row ['min_period']if count else None ,
            'total_records':count ,
            'stock_count':int (row ['stock_count']or 0 ),
            'period_count':int (row ['period_count']or 0 ),
            'latest_available_period':row ['latest_available_period']if count else None ,
            'latest_available_date':row ['latest_available_date']if count else None ,
            'next_available_date':row ['next_available_date']if count else None ,
            'pending_period_count':int (row ['pending_period_count']or 0 ),
            'status':'ok'if count >0 else 'empty',
            }
            expected_period = _expected_latest_monthly_revenue_period(today)
            if expected_period:
                payload['expected_latest_period'] = expected_period
            # Snapshot 是數值候選，不是正式 availability 證據；只在唯讀狀態
            # 中揭露較新的候選期別，避免使用者把「已抓到」誤認成「已套用」。
            candidate_path = (
                self.monthly_revenue_snapshot_candidate_path
                if self.monthly_revenue_snapshot_candidate_path is not None
                else select_latest_monthly_revenue_snapshot(
                    self.config.output_root / 'monthly_revenue_mops_snapshots'
                )
            )
            if candidate_path is not None:
                payload['candidate_snapshot_file'] = str(candidate_path)
                try:
                    candidate_exists = candidate_path.is_file() and not candidate_path.is_symlink()
                except OSError:
                    candidate_exists = False
                if not candidate_exists:
                    if self.monthly_revenue_snapshot_candidate_path is not None:
                        payload['candidate_snapshot_status'] = 'missing'
                        payload['candidate_snapshot_diagnostic'] = (
                            f'明確月營收 snapshot 候選不存在：{candidate_path}'
                        )
                        payload['warnings'] = [
                            '明確月營收 snapshot 候選不存在；未改用其他 snapshot'
                        ]
                else:
                    candidate = inspect_monthly_revenue_snapshot(candidate_path)
                    payload['candidate_snapshot_status'] = (
                        'ready' if candidate.is_named_snapshot else 'invalid'
                    )
                    if candidate.latest_period:
                        payload['candidate_latest_period'] = candidate.latest_period
                        payload['candidate_fetch_date'] = candidate.fetch_date
                        imported_period = str(payload.get('latest_period') or '')
                        if not imported_period or candidate.latest_period > imported_period:
                            payload['status'] = 'candidate_available'
                            payload['warnings'] = [
                                '已有較新的 MOPS 月營收數值候選；尚未完成 availability dry-run／正式套用'
                            ]
                    elif self.monthly_revenue_snapshot_candidate_path is not None:
                        payload['candidate_snapshot_diagnostic'] = (
                            '明確月營收 snapshot 候選檔名不符合受控命名規則'
                        )
                        payload['warnings'] = [
                            '明確月營收 snapshot 候選無法解析；未改用其他 snapshot'
                        ]
            availability_candidate_path = self.monthly_revenue_availability_candidate_path
            if availability_candidate_path is not None:
                availability_candidate = inspect_monthly_revenue_availability_candidate(
                    availability_candidate_path,
                    target_file=self.config.monthly_revenue_availability_file,
                )
                payload.update(
                    {
                        'availability_candidate_file': str(availability_candidate.path),
                        'availability_candidate_status': availability_candidate.status,
                        'availability_candidate_row_count': availability_candidate.row_count,
                        'availability_candidate_latest_period': availability_candidate.latest_period,
                        'availability_candidate_latest_available_date': (
                            availability_candidate.latest_available_date
                        ),
                        'availability_candidate_source_versions': list(
                            availability_candidate.source_versions
                        ),
                        'availability_candidate_diagnostic_count': (
                            availability_candidate.diagnostic_count
                        ),
                        'availability_candidate_added_count': availability_candidate.added_count,
                        'availability_candidate_unchanged_count': (
                            availability_candidate.unchanged_count
                        ),
                        'availability_candidate_conflict_count': (
                            availability_candidate.conflict_count
                        ),
                    }
                )
                if availability_candidate.diagnostics:
                    payload['availability_candidate_diagnostics'] = list(
                        availability_candidate.diagnostics
                    )
                candidate_period = availability_candidate.latest_period
                imported_period = str(payload.get('latest_period') or '')
                if candidate_period and (
                    not imported_period or candidate_period > imported_period
                ):
                    payload['status'] = 'candidate_available'
                    raw_warnings = payload.get('warnings')
                    warnings = list(raw_warnings) if isinstance(raw_warnings, list) else []
                    if availability_candidate.status == 'ready_for_merge':
                        warnings.append(
                            '已有較新的公告日／可得日 mapping 候選；尚未合併到正式 mapping'
                        )
                    elif availability_candidate.status == 'conflict':
                        warnings.append(
                            '公告日／可得日 mapping 候選與正式 mapping 有衝突；未自動覆蓋'
                        )
                    elif availability_candidate.status == 'merge_blocked':
                        warnings.append(
                            '公告日／可得日 mapping 候選的 merge preview 受阻；未自動套用'
                        )
                    elif availability_candidate.status in {'invalid', 'error'}:
                        warnings.append(
                            '公告日／可得日 mapping 候選驗證未完成；未自動套用'
                        )
                    payload['warnings'] = list(
                        dict.fromkeys(str(item) for item in warnings if str(item).strip())
                    )
            imported_period = str(payload.get('latest_period') or '').strip()
            expected_period = str(payload.get('expected_latest_period') or '').strip()
            if (
                expected_period
                and imported_period
                and imported_period < expected_period
                and payload.get('status') != 'candidate_available'
            ):
                payload['freshness_status'] = 'lagging'
                raw_warnings = payload.get('warnings')
                warnings = list(raw_warnings) if isinstance(raw_warnings, list) else []
                warnings.append(
                    f'正式月營收落後通常公告節奏：目前 {imported_period}，預期至少 {expected_period}'
                )
                payload['warnings'] = list(
                    dict.fromkeys(str(item) for item in warnings if str(item).strip())
                )
            from contextlib import closing
            import sqlite3
            formal_path = getattr(self.config, "db_file", None)
            if formal_path and Path(formal_path).is_file():
                with closing(sqlite3.connect(Path(formal_path).resolve().as_uri() + "?mode=ro", uri=True)) as conn:
                    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='fundamental_current_observations'").fetchone()
                    if exists:
                        current = conn.execute("SELECT MAX(period), MAX(as_of_date), COUNT(*), MAX(observed_at) FROM fundamental_current_observations WHERE kind='monthly_revenue' AND julianday(observed_at)<=julianday('now')").fetchone()
                        if current and current[0]:
                            payload.update(
                                pit_latest_period=payload.get('latest_period'),
                                current_observed_period=current[0], latest_period=current[0], latest_date=current[1],
                                current_observed_records=int(current[2]), current_observed_at=current[3],
                                status='partial',
                            )
                            payload['warnings'] = [
                                f"目前可查月營收已到 {current[0]}；此期公告中／覆蓋待核對，沒有公告的公司不補零。",
                                f"歷史 PIT 證據仍到 {payload['pit_latest_period']}；現況快照不冒充歷史公告。",
                            ]
            return self._annotate_sqlite_read_mode(payload, db)
        except Exception as e :
            import logging
            logging .getLogger (__name__ ).warning (f"[UpdateService] 從 SQLite 取得月營收狀態失敗: {e}")
            return {'latest_date':None ,'total_records':0 ,'status':f'error: {e}'}

    def _broker_status_from_sqlite (self )->Dict [str ,Any ]:
        """從 SQLite 資料庫極速獲取券商分點的狀態"""
        if not self._sqlite_status_db_exists():
            return self._sqlite_unavailable_status()
        try :
            db =self ._sqlite_status_manager ()

            columns =db .get_table_columns ("broker_flows")
            has_observed_cols ="lots_observed"in columns and "amount_observed"in columns
            date_column =self ._first_existing_column (columns ,['日期','日期','date','Date'])
            broker_column =self ._first_existing_column (
            columns ,
            ['分點名稱','分點名稱','branch_display_name','branch_name'],
            )
            date_sql =self ._quote_sql_identifier (date_column )if date_column else "NULL"
            broker_sql =self ._quote_sql_identifier (broker_column )if broker_column else "NULL"

            if has_observed_cols :
                query =f"""
                    SELECT
                        COUNT(*) as count,
                        MAX({date_sql}) as max_date,
                        COUNT(DISTINCT {broker_sql}) as broker_count,
                        MIN({date_sql}) as min_date,
                        COUNT(DISTINCT {date_sql}) as date_count,
                        SUM(CASE WHEN lots_observed = 1 AND amount_observed = 1 THEN 1 ELSE 0 END) as dual_cnt,
                        SUM(CASE WHEN lots_observed = 1 AND (amount_observed = 0 OR amount_observed IS NULL) THEN 1 ELSE 0 END) as e_only_cnt,
                        SUM(CASE WHEN (lots_observed = 0 OR lots_observed IS NULL) AND amount_observed = 1 THEN 1 ELSE 0 END) as b_only_cnt
                    FROM broker_flows;
                """
            else :
                query =f"""
                    SELECT
                        COUNT(*) as count,
                        MAX({date_sql}) as max_date,
                        COUNT(DISTINCT {broker_sql}) as broker_count,
                        MIN({date_sql}) as min_date,
                        COUNT(DISTINCT {date_sql}) as date_count
                    FROM broker_flows;
                """

            df =db .execute_query (query )
            if not df .empty :
                cnt =int (df .iloc [0 ]['count']or 0 )
                max_d =df .iloc [0 ]['max_date']
                min_d =df .iloc [0 ]['min_date']
                broker_cnt =int (df .iloc [0 ]['broker_count']or 0 )
                date_cnt =int (df .iloc [0 ]['date_count']or 0 )

                if has_observed_cols :
                    dual_cnt =int (df .iloc [0 ]['dual_cnt']or 0 )
                    e_only_cnt =int (df .iloc [0 ]['e_only_cnt']or 0 )
                    b_only_cnt =int (df .iloc [0 ]['b_only_cnt']or 0 )
                else :
                    dual_cnt =0
                    e_only_cnt =0
                    b_only_cnt =cnt

                def fmt_d (d ):
                    if not d :return None
                    d_str =str (d )
                    return f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"if len (d_str )==8 else d_str

                return self._annotate_sqlite_read_mode({
                'latest_date':fmt_d (max_d ),
                'total_records':cnt ,
                'broker_count':broker_cnt ,
                'date_count':date_cnt ,
                'e_only_count':e_only_cnt ,
                'b_only_count':b_only_cnt ,
                'dual_count':dual_cnt ,
                'date_range':{'start_date':fmt_d (min_d ),'end_date':fmt_d (max_d )},
                'status':'ok'if cnt >0 else 'empty'
                }, db)
            return self._annotate_sqlite_read_mode(
                {'latest_date':None ,'total_records':0 ,'broker_count':0 ,'date_count':0 ,'status':'empty'},
                db,
            )
        except Exception as e :
            import logging
            logging .getLogger (__name__ ).warning (f"[UpdateService] 從 SQLite 獲取券商分點狀態失敗: {e}")
            return {'latest_date':None ,'total_records':0 ,'broker_count':0 ,'date_count':0 ,'status':f'error: {e}'}

    def _technical_status_from_sqlite (self )->Dict [str ,Any ]:
        """從 SQLite 資料庫極速獲取技術指標的狀態"""
        if not self._sqlite_status_db_exists():
            return self._sqlite_unavailable_status()
        try :
            db =self ._sqlite_status_manager ()
            columns =db .get_table_columns ("technical_indicators")
            date_column =self ._first_existing_column (columns ,['日期','日期','date','Date'])
            stock_column =self ._first_existing_column (
            columns ,
            ['證券代號','證券代號','股票代號','stock_id','stock_code'],
            )
            date_sql =self ._quote_sql_identifier (date_column )if date_column else "NULL"
            stock_sql =self ._quote_sql_identifier (stock_column )if stock_column else "NULL"
            if date_column :
                valid_date_filter =(
                f"{date_sql} IS NOT NULL "
                f"AND lower(CAST({date_sql} AS TEXT)) NOT IN ('', 'nan', 'nat', 'none') "
                f"AND (CAST({date_sql} AS TEXT) GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]' "
                f"OR CAST({date_sql} AS TEXT) GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]')"
                )
                df =db .execute_query (f"""
                    SELECT
                        COUNT(*) as count,
                        (SELECT MAX({date_sql}) FROM technical_indicators WHERE {valid_date_filter}) as max_date,
                        COUNT(DISTINCT {stock_sql}) as stock_count,
                        (SELECT MIN({date_sql}) FROM technical_indicators WHERE {valid_date_filter}) as min_date
                    FROM technical_indicators;
                """)
            else :
                df =db .execute_query (f"""
                    SELECT
                        COUNT(*) as count,
                        NULL as max_date,
                        COUNT(DISTINCT {stock_sql}) as stock_count,
                        NULL as min_date
                    FROM technical_indicators;
                """)
            if not df .empty :
                cnt =int (df .iloc [0 ]['count'])
                max_d =df .iloc [0 ]['max_date']
                min_d =df .iloc [0 ]['min_date']
                stock_cnt =int (df .iloc [0 ]['stock_count'])

                def fmt_d (d ):
                    if not d :return None
                    d_str =str (d )
                    return f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"if len (d_str )==8 else d_str

                return self._annotate_sqlite_read_mode({
                'latest_date':fmt_d (max_d ),
                'total_records':cnt ,
                'file_count':stock_cnt ,
                'date_range':{'start_date':fmt_d (min_d ),'end_date':fmt_d (max_d )},
                'status':'ok'if cnt >0 else 'empty'
                }, db)
            return self._annotate_sqlite_read_mode(
                {'latest_date':None ,'total_records':0 ,'file_count':0 ,'status':'empty'}, db
            )
        except Exception as e :
            import logging
            logging .getLogger (__name__ ).warning (f"[UpdateService] 從 SQLite 獲取技術指標狀態失敗: {e}")
            return {'latest_date':None ,'total_records':0 ,'file_count':0 ,'status':f'error: {e}'}

    def check_technical_indicator_latest_coverage (self )->Dict [str ,Any ]:
        """Check whether the latest daily price date has matching technical coverage."""
        if not getattr (self .config ,'use_sqlite',False ):
            return {'success':False ,'status':'unavailable','message':'SQLite disabled'}
        if not self._sqlite_status_db_exists():
            return {
                'success':False,
                'status':'unavailable',
                'message':f'SQLite 資料庫不存在：{getattr(self.config, "db_file", "")}',
            }
        try :
            db =self ._sqlite_status_manager ()
            min_days =int (getattr (self .config ,'min_data_days',30 )or 30 )
            query ="""
                WITH latest AS (
                    SELECT MAX("日期") AS latest_date FROM daily_prices
                ),
                eligible(stock_code) AS (
                    SELECT p."證券代號"
                    FROM daily_prices p
                    GROUP BY p."證券代號"
                    HAVING COUNT(*) >= ?
                       AND MAX(p."日期") = (SELECT latest_date FROM latest)
                ),
                covered(stock_code) AS (
                    SELECT DISTINCT t."證券代號"
                    FROM technical_indicators t
                    WHERE t."日期" = (SELECT latest_date FROM latest)
                )
                SELECT
                    (SELECT latest_date FROM latest) AS daily_latest_date,
                    (SELECT MAX("日期") FROM technical_indicators) AS technical_latest_date,
                    (SELECT COUNT(*) FROM daily_prices WHERE "日期" = (SELECT latest_date FROM latest)) AS daily_latest_rows,
                    (SELECT COUNT(*) FROM eligible) AS eligible_stock_count,
                    (SELECT COUNT(*) FROM eligible e JOIN covered c ON c.stock_code = e.stock_code) AS covered_stock_count;
            """
            df =db .execute_query (query ,params =(min_days ,))
            if df .empty :
                return {'success':False ,'status':'empty','message':'technical coverage query returned no rows'}
            row =df .iloc [0 ]
            daily_latest =row ['daily_latest_date']
            technical_latest =row ['technical_latest_date']
            eligible_count =int (row ['eligible_stock_count']or 0 )
            covered_count =int (row ['covered_stock_count']or 0 )
            is_current =bool (
            daily_latest
            and technical_latest
            and str (technical_latest )>=str (daily_latest )
            and covered_count >=eligible_count
            )
            return self._annotate_sqlite_read_mode({
                'success':True ,
                'status':'ok'if is_current else 'lagging',
            'is_current':is_current ,
            'daily_latest_date':daily_latest ,
            'technical_latest_date':technical_latest ,
            'daily_latest_rows':int (row ['daily_latest_rows']or 0 ),
            'eligible_stock_count':eligible_count ,
                'covered_stock_count':covered_count ,
                'missing_stock_count':max (eligible_count -covered_count ,0 ),
            }, db)
        except Exception as e :
            import logging
            logging .getLogger (__name__ ).warning (f"[UpdateService] 技術指標最新日覆蓋檢查失敗: {e}")
            return {'success':False ,'status':f'error: {e}','message':str (e )}

    def check_data_status (self )->Dict [str ,Any ]:
        """檢查數據狀態"""
        import pandas as pd
        from datetime import datetime
        import logging

        logger =logging .getLogger (__name__ )
        logger .info ("[UpdateService] 開始檢查數據狀態")

        # 🌟 如果啟用 SQLite，直接從資料庫極速統計！
        if getattr (self .config ,'use_sqlite',False ):
            try :
                result =compose_sqlite_status_read_model ({
                'daily_data':self ._status_from_sqlite ('daily_prices'),
                'market_index':self ._status_from_sqlite ('market_indices'),
                'industry_index':self ._status_from_sqlite ('industry_indices'),
                'broker_branch':self ._broker_status_from_sqlite (),
                'technical_indicators':self ._technical_status_from_sqlite (),
                'monthly_revenue':self ._monthly_revenue_status_from_sqlite (),
                }, apply_freshness=True, include_contract=True,
                   freshness_receipt=self._read_freshness_receipt(),
                   freshness_binding=self._freshness_receipt_binding())
                logger .info ("[UpdateService] 成功從 SQLite 資料庫極速獲取數據狀態！")
                return result
            except Exception as sql_err :
                logger .warning (f"[UpdateService] 從 SQLite 檢查數據狀態失敗: {sql_err}，將降級為 CSV 檢查...")

        result ={
        'daily_data':{
        'latest_date':None ,
        'total_records':0 ,
        'status':'unknown'
        },
        'market_index':{
        'latest_date':None ,
        'total_records':0 ,
        'status':'unknown'
        },
        'industry_index':{
        'latest_date':None ,
        'total_records':0 ,
        'status':'unknown'
        }
        }

        try :
            result ['daily_data']=self ._status_from_csv_file (self .config .stock_data_file ,'日期')
            result ['market_index']=self ._status_from_csv_file (self .config .market_index_file ,'日期')
            result ['industry_index']=self ._status_from_csv_file (self .config .industry_index_file ,'日期')
            result ['broker_branch']=self .check_broker_branch_data_status ()
            result ['technical_indicators']=self ._check_technical_indicator_status ()
            return result
        except Exception as fast_error :
            logger .warning (f"[UpdateService] 快速狀態檢查失敗，改用舊路徑: {fast_error}")

            # 檢查每日股票數據（stock_data_whole.csv）
        stock_file =self .config .stock_data_file
        logger .debug (f"[UpdateService] 檢查每日股票數據文件: {stock_file}")
        if stock_file .exists ():
            try :
                logger .debug (f"[UpdateService] 文件存在，開始讀取")
                with open (stock_file ,'r',encoding ='utf-8-sig')as f :
                    total_records =sum (1 for _ in f )-1 # 減去標題行
                result ['daily_data']['total_records']=total_records
                logger .debug (f"[UpdateService] 每日股票數據總記錄數: {total_records:,}")

                try :
                    header_df =pd .read_csv (stock_file ,encoding ='utf-8-sig',nrows =0 )
                    if '日期'not in header_df .columns :
                        result ['daily_data']['status']='ok'
                    else :
                        df_dates =pd .read_csv (
                        stock_file ,
                        encoding ='utf-8-sig',
                        on_bad_lines ='skip',
                        engine ='python',
                        usecols =['日期']
                        )
                        df_tail =df_dates
                except Exception as e :
                    try :
                        if total_records >10000 :
                            skip_rows =list (range (1 ,total_records -10000 +1 ))
                            df_tail =pd .read_csv (
                            stock_file ,
                            encoding ='utf-8-sig',
                            on_bad_lines ='skip',
                            engine ='python',
                            skiprows =skip_rows
                            )
                        else :
                            df_tail =pd .read_csv (
                            stock_file ,
                            encoding ='utf-8-sig',
                            on_bad_lines ='skip',
                            engine ='python'
                            )
                    except :
                        df_tail =pd .DataFrame ()

                if '日期'in df_tail .columns and len (df_tail )>0 :
                    df_tail ['日期']=df_tail ['日期'].astype (str )
                    valid_dates =df_tail [df_tail ['日期'].notna ()&(df_tail ['日期']!='nan')&(df_tail ['日期']!='')]['日期']
                    if len (valid_dates )>0 :
                        latest_date_str =valid_dates .max ()
                        try :
                            if len (latest_date_str )==8 and latest_date_str .isdigit ():
                                latest_date =datetime .strptime (latest_date_str ,'%Y%m%d').strftime ('%Y-%m-%d')
                            else :
                                latest_date =pd .to_datetime (latest_date_str ,errors ='coerce')
                                if pd .notna (latest_date ):
                                    latest_date =latest_date .strftime ('%Y-%m-%d')
                                else :
                                    latest_date =latest_date_str
                            result ['daily_data']['latest_date']=latest_date
                            result ['daily_data']['status']='ok'
                        except :
                            result ['daily_data']['latest_date']=latest_date_str
                            result ['daily_data']['status']='ok'
                    else :
                        result ['daily_data']['status']='ok'
                else :
                    result ['daily_data']['status']='ok'
            except Exception as e :
                result ['daily_data']['status']=f'error: {str(e)}'

                # 檢查大盤指數數據
        market_file =self .config .market_index_file
        logger .debug (f"[UpdateService] 檢查大盤指數文件: {market_file}")
        if market_file .exists ():
            try :
                df =pd .read_csv (
                market_file ,
                encoding ='utf-8-sig',
                on_bad_lines ='skip',
                engine ='python'
                )
                result ['market_index']['total_records']=len (df )

                if '日期'in df .columns :
                    df ['日期']=df ['日期'].astype (str )
                    valid_dates =df [df ['日期'].notna ()&(df ['日期']!='nan')&(df ['日期']!='')]['日期']
                    if len (valid_dates )>0 :
                        latest_date =pd .to_datetime (valid_dates ,errors ='coerce').max ()
                        if pd .notna (latest_date ):
                            result ['market_index']['latest_date']=latest_date .strftime ('%Y-%m-%d')
                            result ['market_index']['status']='ok'
                            logger .debug (f"[UpdateService] 大盤指數最新日期: {latest_date.strftime('%Y-%m-%d')}")
            except Exception as e :
                result ['market_index']['status']=f'error: {str(e)}'
                logger .warning (f"[UpdateService] 檢查大盤指數時發生錯誤: {str(e)}")
        else :
            logger .debug (f"[UpdateService] 大盤指數文件不存在: {market_file}")

            # 檢查產業指數數據
        industry_file =self .config .industry_index_file
        logger .debug (f"[UpdateService] 檢查產業指數文件: {industry_file}")
        if industry_file .exists ():
            try :
                df =pd .read_csv (
                industry_file ,
                encoding ='utf-8-sig',
                on_bad_lines ='skip',
                engine ='python'
                )
                result ['industry_index']['total_records']=len (df )

                if '日期'in df .columns :
                    df ['日期']=df ['日期'].astype (str )
                    valid_dates =df [df ['日期'].notna ()&(df ['日期']!='nan')&(df ['日期']!='')]['日期']
                    if len (valid_dates )>0 :
                        parsed_dates =[]
                        for date_str in valid_dates :
                            try :
                                if len (date_str )==8 and date_str .isdigit ():
                                    parsed_date =datetime .strptime (date_str ,'%Y%m%d')
                                else :
                                    parsed_date =pd .to_datetime (date_str ,errors ='coerce')
                                if pd .notna (parsed_date ):
                                    parsed_dates .append (parsed_date )
                            except :
                                continue

                        if parsed_dates :
                            latest_industry_date =max (parsed_dates )
                            result ['industry_index']['latest_date']=latest_industry_date .strftime ('%Y-%m-%d')
                            result ['industry_index']['status']='ok'
                        else :
                            latest_date_str =valid_dates .max ()
                            result ['industry_index']['latest_date']=latest_date_str
                            result ['industry_index']['status']='ok'
            except Exception as e :
                result ['industry_index']['status']=f'error: {str(e)}'

        result ['broker_branch']=self .check_broker_branch_data_status ()
        result ['technical_indicators']=self ._check_technical_indicator_status ()

        return enrich_status_mapping(result)

    def check_data_status_dto(self) -> UpdateStatusSnapshotDTO:
        """以明確 DTO 取得整體更新狀態；保留舊 dict 入口供相容呼叫端使用。"""

        return UpdateStatusSnapshotDTO.from_mapping(self.check_data_status())

    def check_data_overview (self )->Dict [str ,Any ]:
        """取得全部資料頁使用的輕量狀態摘要，不執行深度檢查或自動修復"""
        # 🌟 如果啟用 SQLite，直接從資料庫極速統計！
        if getattr (self .config ,'use_sqlite',False ):
            try :
                overview =compose_sqlite_status_read_model ({
                'daily_data':self ._status_from_sqlite ('daily_prices'),
                'market_index':self ._status_from_sqlite ('market_indices'),
                'industry_index':self ._status_from_sqlite ('industry_indices'),
                'broker_branch':self ._broker_status_from_sqlite (),
                'technical_indicators':self ._technical_status_from_sqlite (),
                'monthly_revenue':self ._monthly_revenue_status_from_sqlite (),
                },is_overview =True ,apply_freshness =True ,include_contract =True,
                   freshness_receipt=self._read_freshness_receipt(),
                   freshness_binding=self._freshness_receipt_binding())
                return overview
            except Exception as sql_err :
                import logging
                logging .getLogger (__name__ ).warning (f"[UpdateService] 從 SQLite check_data_overview 失敗: {sql_err}")

        manifest =self ._read_data_status_manifest ()
        sources =manifest .get ('sources',{})

        overview ={
        'daily_data':self ._overview_csv_status ('daily_data',self .config .stock_data_file ,'日期',sources ),
        'market_index':self ._overview_csv_status ('market_index',self .config .market_index_file ,'日期',sources ),
        'industry_index':self ._overview_csv_status ('industry_index',self .config .industry_index_file ,'日期',sources ),
        'broker_branch':self ._overview_broker_branch_status (sources ),
        'technical_indicators':self ._overview_technical_status (sources ),
        'monthly_revenue':sources .get ('monthly_revenue',{
        'latest_date':None ,
        'total_records':0 ,
        'status':'sqlite only',
        }),
        }
        return enrich_status_mapping(overview)

    def check_data_overview_dto(self) -> UpdateStatusSnapshotDTO:
        """以明確 DTO 取得更新頁輕量狀態摘要。"""

        return UpdateStatusSnapshotDTO.from_mapping(self.check_data_overview())

    def _scheduler_status_from_artifacts(self) -> Dict[str, Any]:
        """以唯讀方式彙整排程 latest_status artifacts，供 Update 分頁下鑽。"""

        scheduled_root = Path(
            getattr(self.config, "output_root", Path("."))
        ) / "scheduled"
        try:
            from app_module.runtime_services.scheduled_operations_service import (
                ScheduledOperationsStatusService,
            )

            snapshot = ScheduledOperationsStatusService(scheduled_root).get_snapshot()
            operations: list[dict[str, Any]] = []
            diagnostics: list[str] = []
            counts = {
                "operational": 0,
                "guarded": 0,
                "attention": 0,
                "unavailable": 0,
            }
            for operation in snapshot.operations:
                state = str(operation.state or "unavailable").strip().lower()
                if state in counts:
                    counts[state] += 1
                if operation.diagnostic:
                    diagnostics.append(
                        f"{operation.job_id}:{operation.diagnostic}"
                    )
                operations.append(
                    {
                        "job_id": operation.job_id,
                        "label": operation.label,
                        "raw_status": operation.raw_status,
                        "state": state,
                        "updated_at": (
                            operation.updated_at.isoformat()
                            if operation.updated_at is not None
                            else None
                        ),
                        "lane": operation.lane,
                        "observed_at_source": operation.observed_at_source,
                        "source_path": operation.source_path,
                        "read_state": operation.read_state,
                        "diagnostic": operation.diagnostic,
                    }
                )
            status = "ok" if snapshot.overall_state == "operational" else "attention"
            return {
                "status": status,
                "scheduler_state": snapshot.overall_state,
                "latest_date": snapshot.observed_at.isoformat(),
                "total_records": len(operations),
                "operation_count": len(operations),
                "core_ready_count": int(snapshot.core_ready_count),
                "core_job_count": int(snapshot.core_job_count),
                "operational_count": counts["operational"],
                "guarded_count": counts["guarded"],
                "attention_count": counts["attention"],
                "unavailable_count": counts["unavailable"],
                "operations": operations,
                "scheduled_root": snapshot.scheduled_root,
                "read_only": True,
                "warnings": list(dict.fromkeys(diagnostics[:12])),
            }
        except Exception as exc:
            # 分頁狀態讀取失敗仍要顯示可排錯的 fail-closed 結果，且不建立
            # 任何 output 目錄／狀態檔。
            return {
                "status": "error",
                "scheduler_state": "attention",
                "latest_date": None,
                "total_records": 0,
                "operation_count": 0,
                "core_ready_count": 0,
                "core_job_count": 0,
                "operational_count": 0,
                "guarded_count": 0,
                "attention_count": 0,
                "unavailable_count": 0,
                "operations": [],
                "scheduled_root": str(scheduled_root),
                "read_only": True,
                "warnings": [
                    f"scheduled_operations_read_failed:{type(exc).__name__}:{exc}"
                ],
            }

    def check_source_detail (self ,source :str )->Dict [str ,Any ]:
        """取得單一資料來源的詳細狀態，供切入 subtab 或手動檢查使用"""
        source_map ={
        'daily':'daily_data',
        'daily_data':'daily_data',
        'market':'market_index',
        'market_index':'market_index',
        'industry':'industry_index',
        'industry_index':'industry_index',
        'broker_branch':'broker_branch',
        'technical':'technical_indicators',
        'technical_indicators':'technical_indicators',
        'monthly_revenue':'monthly_revenue',
        # 候選資料域與排程頁也共用同一個詳細狀態入口。此前這三類
        # 會直接落入 unknown source，導致分頁的「檢查」按鈕顯示錯誤，
        # 即使總覽已能讀到 candidate／scheduled artifact。
        'institutional_flow':'institutional_flow',
        'credit_transaction':'credit_transaction',
        'tdcc_shareholding':'tdcc_shareholding',
        'scheduler_status':'scheduler_status',
        }
        normalized =source_map .get (source )
        if normalized is None :
            return {'latest_date':None ,'total_records':0 ,'status':f'unknown source: {source}'}

        # Candidate DB 與 scheduler artifact 必須維持唯讀邊界，不能走
        # 下面的正式 SQLite／CSV manifest 更新路徑。
        if normalized in {
            'institutional_flow',
            'credit_transaction',
            'tdcc_shareholding',
        }:
            return self.check_decision_data_status().get(
                normalized,
                {
                    'latest_date': '無',
                    'total_records': 0,
                    'status': 'MISSING',
                    'disclaimer': '候選研究資料，不參與評分或投資決策',
                },
            )
        if normalized == 'scheduler_status':
            return self._scheduler_status_from_artifacts()

            # 🌟 如果啟用 SQLite，直接從資料庫極速統計！
        if getattr (self .config ,'use_sqlite',False ):
            try :
                if normalized =='daily_data':
                    detail =self ._status_from_sqlite ('daily_prices')
                elif normalized =='market_index':
                    detail =self ._status_from_sqlite ('market_indices')
                elif normalized =='industry_index':
                    detail =self ._status_from_sqlite ('industry_indices')
                elif normalized =='broker_branch':
                    detail =self ._broker_status_from_sqlite ()
                elif normalized =='technical_indicators':
                    detail =self ._technical_status_from_sqlite ()
                else :
                    detail =self ._monthly_revenue_status_from_sqlite ()
                if normalized in {"market_index", "industry_index", "technical_indicators"}:
                    # 單一詳情也必須以同一份 daily reference 判定落後，
                    # 避免 overview 與下鑽頁出現 split-brain 狀態。
                    reference = self ._status_from_sqlite ("daily_prices")
                    detail = compose_sqlite_status_read_model(
                        {"daily_data": reference, normalized: detail},
                        apply_freshness=True,
                        include_contract=True,
                        freshness_receipt=self._read_freshness_receipt(),
                        freshness_binding=self._freshness_receipt_binding(),
                    ).get(normalized, detail)
                return enrich_status_mapping({normalized: detail}).get(normalized, detail)
            except Exception as sql_err :
                import logging
                logging .getLogger (__name__ ).warning (f"[UpdateService] 從 SQLite check_source_detail 失敗: {sql_err}")

        if normalized =='daily_data':
            detail =self ._status_from_csv_file (self .config .stock_data_file ,'日期')
        elif normalized =='market_index':
            detail =self ._status_from_csv_file (self .config .market_index_file ,'日期')
        elif normalized =='industry_index':
            detail =self ._status_from_csv_file (self .config .industry_index_file ,'日期')
        elif normalized =='broker_branch':
            detail =self .check_broker_branch_data_status ()
        elif normalized =='technical_indicators':
            detail =self ._check_technical_indicator_status ()
        else :
            detail ={'latest_date':None ,'total_records':0 ,'status':'sqlite only'}

        return enrich_status_mapping({normalized: detail}).get(normalized, detail)

    def _read_data_status_manifest (self )->Dict [str ,Any ]:
        """讀取資料狀態 manifest，格式錯誤時回傳空 manifest"""
        import json

        if not self .status_manifest_file .exists ():
            return {'sources':{}}
        try :
            with open (self .status_manifest_file ,'r',encoding ='utf-8')as f :
                data =json .load (f )
            if not isinstance (data ,dict ):
                return {'sources':{}}
            data .setdefault ('sources',{})
            return data
        except Exception :
            return {'sources':{}}

    def _write_data_status_manifest (self ,manifest :Dict [str ,Any ])->None :
        """寫入資料狀態 manifest"""
        import json

        self .status_manifest_file .parent .mkdir (parents =True ,exist_ok =True )
        with open (self .status_manifest_file ,'w',encoding ='utf-8')as f :
            json .dump (manifest ,f ,ensure_ascii =False ,indent =2 )

    def _update_data_status_manifest (self ,source :str ,status :Dict [str ,Any ])->None :
        """更新單一資料來源的 manifest 摘要"""
        from datetime import datetime

        manifest =self ._read_data_status_manifest ()
        manifest .setdefault ('sources',{})
        manifest ['sources'][source ]={
        **status ,
        'checked_at':datetime .now ().isoformat (timespec ='seconds'),
        }
        manifest ['updated_at']=datetime .now ().isoformat (timespec ='seconds')
        self ._write_data_status_manifest (manifest )

    def _overview_csv_status (
    self ,
    source :str ,
    path :Path ,
    date_column :str ,
    manifest_sources :Dict [str ,Any ],
    )->Dict [str ,Any ]:
        """取得單一 CSV 的輕量 overview，避免完整掃描大檔"""
        from datetime import datetime

        cached =manifest_sources .get (source ,{})
        status ={
        'latest_date':cached .get ('latest_date'),
        'total_records':cached .get ('total_records',0 ),
        'status':cached .get ('status','unknown'),
        'file_size_mb':0.0 ,
        'modified_at':None ,
        'checked_at':cached .get ('checked_at'),
        'is_overview':True ,
        }
        if not path .exists ():
            status ['status']='missing'
            return status

        stat =path .stat ()
        status ['file_size_mb']=round (stat .st_size /1024 /1024 ,2 )
        status ['modified_at']=datetime .fromtimestamp (stat .st_mtime ).isoformat (timespec ='seconds')

        summary =self ._tail_csv_date_summary (path ,date_column )
        if summary .get ('latest_date'):
            status ['latest_date']=summary ['latest_date']
        if status ['status']in {'unknown','missing'}:
            status ['status']='summary'
        return status

    def _overview_broker_branch_status (self ,manifest_sources :Dict [str ,Any ])->Dict [str ,Any ]:
        """取得券商分點輕量 overview，不載入 BrokerBranchUpdateService"""
        import pandas as pd

        cached =manifest_sources .get ('broker_branch',{})
        status ={
        'latest_date':cached .get ('latest_date'),
        'total_records':cached .get ('total_records',0 ),
        'broker_count':cached .get ('broker_count',0 ),
        'status':cached .get ('status','unknown'),
        'checked_at':cached .get ('checked_at'),
        'is_overview':True ,
        }

        registry_file =self .config .broker_branch_registry_file
        if not registry_file .exists ():
            status ['status']='missing'
            return status

        try :
            registry =pd .read_csv (registry_file ,encoding ='utf-8-sig')
            if 'is_active'in registry .columns :
                registry =registry [registry ['is_active']==True ]
            status ['broker_count']=len (registry )
        except Exception :
            status ['status']='registry_error'
            return status

        latest_dates =[]
        for branch_dir in self .config .broker_flow_dir .glob ('*'):
            merged_file =branch_dir /'meta'/'merged.csv'
            if not merged_file .exists ():
                continue
            summary =self ._tail_csv_date_summary (merged_file ,'date')
            if summary .get ('latest_date'):
                latest_dates .append (summary ['latest_date'])

        if latest_dates :
            status ['latest_date']=max (latest_dates )
            status ['status']='summary'
        elif status ['status']=='unknown':
            status ['status']='empty'
        return status

    def _overview_technical_status (self ,manifest_sources :Dict [str ,Any ])->Dict [str ,Any ]:
        """取得技術指標輕量 overview"""
        cached =manifest_sources .get ('technical_indicators',{})
        status ={
        'latest_date':cached .get ('latest_date'),
        'total_records':cached .get ('total_records',0 ),
        'file_count':0 ,
        'status':cached .get ('status','unknown'),
        'checked_at':cached .get ('checked_at'),
        'is_overview':True ,
        }
        tech_dir =self .config .technical_dir
        status ['file_count']=len (list (tech_dir .glob ('*_indicators.csv')))if tech_dir .exists ()else 0
        if self .config .all_stocks_data_file .exists ():
            summary =self ._tail_csv_date_summary (self .config .all_stocks_data_file ,'日期')
            if summary .get ('latest_date'):
                status ['latest_date']=summary ['latest_date']
            if status ['status']in {'unknown','missing'}:
                status ['status']='summary'
        elif status ['file_count']:
            status ['status']='summary'
        else :
            status ['status']='missing'
        return status

    def _tail_csv_date_summary (self ,path :Path ,date_column :str ,tail_rows :int =300 )->Dict [str ,Any ]:
        """只讀取 CSV 尾端少量日期欄位，供 overview 使用"""
        from collections import deque
        import csv
        import pandas as pd

        latest_date =None
        if not path .exists ():
            return {'latest_date':None }

        tail :deque [str ]=deque (maxlen =tail_rows )
        try :
            with open (path ,'r',encoding ='utf-8-sig',newline ='')as f :
                reader =csv .reader (f )
                header =next (reader ,None )
                if not header or date_column not in header :
                    return {'latest_date':None }
                date_idx =header .index (date_column )
                for row in reader :
                    if len (row )>date_idx and row [date_idx ]:
                        tail .append (row [date_idx ])
            dates =[date for date in tail if date and date !='nan']
            if dates :
                parsed =pd .to_datetime (dates ,errors ='coerce')
                parsed =parsed [pd .notna (parsed )]
                if len (parsed )>0 :
                    latest_date =parsed .max ().strftime ('%Y-%m-%d')
                else :
                    latest_date =max (dates )
            return {'latest_date':latest_date }
        except Exception :
            return {'latest_date':None }

    def _check_technical_indicator_status (self )->Dict [str ,Any ]:
        """快速檢查技術指標彙整檔與個股指標檔狀態"""
        import logging

        logger =logging .getLogger (__name__ )
        status :Dict [str ,Any ]={
        'latest_date':None ,
        'total_records':0 ,
        'file_count':0 ,
        'date_range':{'start_date':None ,'end_date':None },
        'status':'unknown'
        }

        try :
            tech_dir =self .config .technical_dir
            tech_files =list (tech_dir .glob ('*_indicators.csv'))if tech_dir .exists ()else []
            status ['file_count']=len (tech_files )

            all_file =self .config .all_stocks_data_file
            dates =[]
            if all_file .exists ():
                summary =self ._summarize_csv_file (all_file ,'日期')
                status ['total_records']=summary ['total_records']
                if summary ['latest_date']:
                    dates .append (summary ['latest_date'])
                if summary ['start_date']:
                    status ['date_range']['start_date']=summary ['start_date']

            if not dates and tech_files :
                for file in tech_files [:20 ]:
                    summary =self ._summarize_csv_file (file ,'日期')
                    if summary ['latest_date']:
                        dates .append (summary ['latest_date'])

            valid_dates =[d for d in dates if d and d !='nan']
            if valid_dates :
                import pandas as pd

                parsed =pd .to_datetime (valid_dates ,errors ='coerce')
                parsed =parsed [pd .notna (parsed )]
                if len (parsed )>0 :
                    start_date =status ['date_range']['start_date']or parsed .min ().strftime ('%Y-%m-%d')
                    end_date =parsed .max ().strftime ('%Y-%m-%d')
                    status ['latest_date']=end_date
                    status ['date_range']={'start_date':start_date ,'end_date':end_date }
                    status ['status']='ok'
                else :
                    status ['latest_date']=max (valid_dates )
                    status ['status']='ok'
            elif tech_files or all_file .exists ():
                status ['status']='empty'
            else :
                status ['status']='missing'

            return status
        except Exception as e :
            logger .warning (f"[UpdateService] 檢查技術指標狀態失敗: {e}")
            status ['status']=f'error: {str(e)}'
            return status

    def _status_from_csv_file (self ,path :Path ,date_column :str )->Dict [str ,Any ]:
        """以快速摘要產生一般 CSV 資料狀態"""
        summary =self ._summarize_csv_file (path ,date_column )
        status ={
        'latest_date':summary ['latest_date'],
        'total_records':summary ['total_records'],
        'status':'unknown'
        }
        if not path .exists ():
            status ['status']='missing'
        elif summary ['total_records']==0 :
            status ['status']='empty'
        else :
            status ['status']='ok'
        return status

    def _summarize_csv_file (self ,path :Path ,date_column :str ,tail_rows :int =5000 )->Dict [str ,Any ]:
        """以低記憶體方式取得 CSV 行數與尾端日期摘要"""
        from collections import deque
        import csv
        import pandas as pd

        summary ={
        'total_records':0 ,
        'start_date':None ,
        'latest_date':None ,
        }
        if not path .exists ():
            return summary

        tail :deque [str ]=deque (maxlen =tail_rows )
        total_records =0
        start_date =None
        latest_date =None
        try :
            with open (path ,'r',encoding ='utf-8-sig',newline ='')as f :
                reader =csv .reader (f )
                header =next (reader ,None )
                if not header or date_column not in header :
                    return {
                    'total_records':0 ,
                    'start_date':None ,
                    'latest_date':None ,
                    }
                date_idx =header .index (date_column )
                for row in reader :
                    total_records +=1
                    if len (row )>date_idx and row [date_idx ]:
                        if start_date is None :
                            start_date =row [date_idx ]
                        tail .append (row [date_idx ])

            dates =[date for date in tail if date and date !='nan']
            if dates :
                parsed =pd .to_datetime (dates ,errors ='coerce')
                parsed =parsed [pd .notna (parsed )]
                if len (parsed )>0 :
                    latest_date =parsed .max ().strftime ('%Y-%m-%d')
                    if start_date :
                        start =pd .to_datetime (start_date ,errors ='coerce')
                        if pd .notna (start ):
                            start_date =start .strftime ('%Y-%m-%d')
                else :
                    latest_date =max (dates )
            return {
            'total_records':total_records ,
            'start_date':start_date ,
            'latest_date':latest_date ,
            }
        except Exception :
            return summary

    def merge_daily_data (
    self ,
    force_all :bool =False ,
    cancel_callback :Optional [Callable[[],bool ]]=None,
    progress_callback :Optional [Callable[[str, int], None]]=None
    )->Dict [str ,Any ]:
        """合併每日股票數據

        將 daily_price/ 目錄中的 CSV 文件合併到 stock_data_whole.csv

        Args:
            force_all: 是否強制重新合併所有數據（忽略現有數據）
            cancel_callback: 合作式取消回調；在檔案／讀取批次／寫入批次邊界停止
            progress_callback: 可選的 (訊息, 百分比) 回調；只報告安全操作進度

        Returns:
            dict: {
                'success': bool,
                'message': str,
                'merged_files': int,
                'total_records': int,
                'cancelled': optional bool indicating cooperative cancellation
            }
        """
        import pandas as pd
        import shutil
        from datetime import datetime
        import logging
        import traceback

        logger =logging .getLogger (__name__ )

        _emit_update_progress(progress_callback, "準備合併每日資料", 0)

        # ✅ 記錄輸入參數
        logger .info (
        f"[UpdateService] 開始合併每日股票數據: "
        f"force_all={force_all}"
        )

        if _is_cancel_requested(cancel_callback):
            return {
            'success':False ,
            'cancelled':True ,
            'message':'每日資料合併已取消（尚未開始）',
            'merged_files':0 ,
            'total_records':0
            }

        try :
        # 直接調用 merge 腳本的函數
            import os
            import sys
            import importlib .util

            merge_script =self .project_root /'scripts'/'merge_daily_data.py'
            logger .debug (f"[UpdateService] 合併腳本路徑: {merge_script}")

            if not merge_script .exists ():
                logger .error (f"[UpdateService] 找不到合併腳本: {merge_script}")
                return {
                'success':False ,
                'message':f'找不到合併腳本: {merge_script}',
                'merged_files':0 ,
                'total_records':0
                }

                # 動態導入 merge 函數
            logger .debug (f"[UpdateService] 開始動態導入合併模組")
            try :
                spec =importlib .util .spec_from_file_location ("merge_daily_data",merge_script )
                if spec is None or spec .loader is None :
                    error_msg =f"無法創建模組規格: {merge_script}"
                    logger .error (f"[UpdateService] {error_msg}")
                    return {
                    'success':False ,
                    'message':error_msg ,
                    'merged_files':0 ,
                    'total_records':0
                    }

                merge_module =importlib .util .module_from_spec (spec )
                spec .loader .exec_module (merge_module )
                logger .debug (f"[UpdateService] 模組導入成功")
            except Exception as e :
                error_msg =f"導入合併模組時發生錯誤: {str(e)}"
                logger .error (f"[UpdateService] {error_msg}")
                logger .error (traceback .format_exc ())
                return {
                'success':False ,
                'message':error_msg ,
                'merged_files':0 ,
                'total_records':0
                }

                # 檢查函數是否存在
            if not hasattr (merge_module ,'merge_daily_data'):
                error_msg =f"合併模組中找不到 merge_daily_data 函數"
                logger .error (f"[UpdateService] {error_msg}")
                return {
                'success':False ,
                'message':error_msg ,
                'merged_files':0 ,
                'total_records':0
                }

                # 執行合併函數（傳遞 force_all 參數）
            logger .info (f"[UpdateService] 開始執行合併函數: force_all={force_all}")
            try :
            # ✅ 傳遞 config 給合併函數（如果它支持的話）
            # 先嘗試傳遞 config，如果不支持則只傳 force_all
                import inspect
                merge_func =merge_module .merge_daily_data
                sig =inspect .signature (merge_func )
                params =list (sig .parameters .keys ())
                merge_kwargs: dict[str, Any] ={'force_all':force_all}
                if 'config'in params :
                    merge_kwargs ['config']=self .config
                if 'cancel_callback'in params and cancel_callback is not None:
                    merge_kwargs ['cancel_callback']=cancel_callback
                if (
                    progress_callback is not None
                    and (
                        'progress_callback' in params
                        or any(
                            parameter.kind is inspect.Parameter.VAR_KEYWORD
                            for parameter in sig.parameters.values()
                        )
                    )
                ):
                    merge_kwargs['progress_callback'] = progress_callback

                if 'config'in params :
                    logger .debug (f"[UpdateService] 合併函數支持 config 參數，傳遞配置")
                    merge_result =merge_func (**merge_kwargs )
                else :
                    logger .debug (f"[UpdateService] 合併函數不支持 config 參數，只傳遞 force_all")
                    merge_result =merge_func (**merge_kwargs )

                if isinstance (merge_result ,dict )and merge_result .get ('cancelled'):
                    return merge_result

                # 目前合併腳本已回傳原子提交後的統計；直接沿用可避免
                # 再次完整掃描輸出檔，並讓取消旗標不必等待 line-count。
                if (
                    isinstance(merge_result, dict)
                    and merge_result.get("success") is True
                    and "total_records" in merge_result
                ):
                    return merge_result

                logger .info (f"[UpdateService] 合併函數執行完成")
            except Exception as e :
                error_msg =f"執行合併函數時發生錯誤: {str(e)}"
                logger .error (f"[UpdateService] {error_msg}")
                logger .error (traceback .format_exc ())
                return {
                'success':False ,
                'message':error_msg ,
                'merged_files':0 ,
                'total_records':0
                }

                # 讀取合併後的數據統計
            stock_file =self .config .stock_data_file
            if stock_file .exists ():
            # 計算總記錄數（使用更高效的方式）
                try :
                    df =pd .read_csv (stock_file ,encoding ='utf-8-sig',nrows =1000 )
                    # 讀取文件總行數
                    with open (stock_file ,'r',encoding ='utf-8-sig')as f :
                        total_records =sum (1 for _ in f )-1 # 減去標題行

                        # 獲取最新日期（讀取文件最後幾行，因為最新日期通常在文件末尾）
                    if '日期'in df .columns :
                        try :
                        # 方法1：讀取最後 10000 行來獲取最新日期
                        # 先獲取總行數
                            with open (stock_file ,'r',encoding ='utf-8-sig')as f :
                                total_lines =sum (1 for _ in f )-1 # 減去標題行

                            if total_lines >0 :
                            # 讀取最後 10000 行（或全部，如果總行數少於 10000）
                                skip_rows =max (0 ,total_lines -10000 )
                                df_tail =pd .read_csv (
                                stock_file ,
                                encoding ='utf-8-sig',
                                usecols =['日期'],
                                skiprows =range (1 ,skip_rows +1 )# 跳過前面的行，保留標題行
                                )

                                if len (df_tail )>0 :
                                # 轉換日期格式
                                    df_tail ['日期']=df_tail ['日期'].astype (str )
                                    valid_dates =df_tail [
                                    df_tail ['日期'].notna ()&
                                    (df_tail ['日期']!='nan')&
                                    (df_tail ['日期']!='')&
                                    (df_tail ['日期']!='None')
                                    ]['日期']

                                    if len (valid_dates )>0 :
                                    # 嘗試解析日期並找到最大值
                                        parsed_dates =[]
                                        for date_str in valid_dates :
                                            try :
                                            # 嘗試 YYYYMMDD 格式
                                                if len (date_str )==8 and date_str .isdigit ():
                                                    parsed_dates .append (datetime .strptime (date_str ,'%Y%m%d'))
                                                    # 嘗試 YYYY-MM-DD 格式
                                                elif len (date_str )==10 and '-'in date_str :
                                                    parsed_dates .append (datetime .strptime (date_str ,'%Y-%m-%d'))
                                                else :
                                                # 嘗試自動解析
                                                    parsed =pd .to_datetime (date_str ,errors ='coerce')
                                                    if pd .notna (parsed ):
                                                        parsed_dates .append (parsed .to_pydatetime ())
                                            except :
                                                continue

                                        if parsed_dates :
                                            latest_date =max (parsed_dates ).strftime ('%Y-%m-%d')
                                            message =f'數據合併成功，最新日期：{latest_date}'
                                        else :
                                        # 如果解析失敗，使用字符串比較（降級方案）
                                            latest_date_str =valid_dates .max ()
                                            if len (latest_date_str )==8 and latest_date_str .isdigit ():
                                                latest_date =datetime .strptime (latest_date_str ,'%Y%m%d').strftime ('%Y-%m-%d')
                                            else :
                                                latest_date =latest_date_str
                                            message =f'數據合併成功，最新日期：{latest_date}'
                                    else :
                                        message ='數據合併成功'
                                else :
                                    message ='數據合併成功'
                            else :
                                message ='數據合併成功'
                        except Exception as e :
                            logger .warning (f"[UpdateService] 讀取最新日期時出錯: {str(e)}")
                            message ='數據合併成功'
                    else :
                        message ='數據合併成功'

                        # ✅ 記錄結果
                    logger .info (
                    f"[UpdateService] 合併完成: "
                    f"總記錄數={total_records:,}, 訊息={message}"
                    )
                    return {
                    'success':True ,
                    'message':message ,
                    'merged_files':0 ,# merge 函數內部會處理，這裡不統計
                    'total_records':total_records
                    }
                except Exception as e :
                    logger .warning (f"[UpdateService] 讀取統計信息時出錯: {str(e)}")
                    return {
                    'success':True ,
                    'message':f'數據合併完成（讀取統計信息時出錯：{str(e)}）',
                    'merged_files':0 ,
                    'total_records':0
                    }
            else :
                logger .error (f"[UpdateService] 合併完成但找不到輸出文件: {stock_file}")
                return {
                'success':False ,
                'message':'合併完成但找不到輸出文件',
                'merged_files':0 ,
                'total_records':0
                }

        except Exception as e :
            import traceback
            logger .error (f"[UpdateService] 合併過程出錯: {str(e)}")
            logger .error (traceback .format_exc ())
            return {
            'success':False ,
            'message':f'合併過程出錯：{str(e)}\n{traceback.format_exc()}',
            'merged_files':0 ,
            'total_records':0
            }

    def update_broker_branch (
    self ,
    start_date :str ,
    end_date :str ,
    branch_system_keys :Optional [List [str ]]=None ,
    delay_seconds :float =0.5 ,
    force_all :bool =False ,
    progress_callback =None ,
    cancel_callback :Optional [Callable[[],bool ]]=None
    )->Dict [str ,Any ]:
        """更新券商分點資料

        Args:
            start_date: 開始日期（YYYY-MM-DD）
            end_date: 結束日期（YYYY-MM-DD）
            branch_system_keys: 要更新的分點列表（None=全部）
            delay_seconds: 請求間隔（秒）
            force_all: 是否強制重新抓取
            progress_callback: 進度回調函數

        Returns:
            dict: 更新結果
        """
        import logging
        logger =logging .getLogger (__name__ )

        logger .info (
        f"[UpdateService] 開始更新券商分點資料: "
        f"start_date={start_date}, end_date={end_date}, "
        f"branch_system_keys={branch_system_keys}, force_all={force_all}"
        )

        try :
            from app_module .broker_branch_update_service import BrokerBranchUpdateService

            service =BrokerBranchUpdateService (self .config )
            result =service .update_broker_branch_data (
            start_date =start_date ,
            end_date =end_date ,
            branch_system_keys =branch_system_keys ,
            delay_seconds =delay_seconds ,
            force_all =force_all ,
            progress_callback =progress_callback ,
            cancel_callback =cancel_callback
            )

            logger .info (f"[UpdateService] 券商分點資料更新完成: success={result.get('success', False)}")
            return result

        except Exception as e :
            import traceback
            error_msg =f"更新券商分點資料時發生錯誤: {str(e)}"
            logger .error (f"[UpdateService] {error_msg}")
            logger .error (traceback .format_exc ())
            return {
            'success':False ,
            'message':error_msg ,
            'updated_dates':[],
            'failed_dates':[],
            'skipped_dates':[],
            'non_trading_dates':[],
            'updated_branches':[],
            'failed_branches':[],
            'total_processed':0 ,
            'total_records':0
            }

    def merge_broker_branch_data (
    self ,
    branch_system_keys :Optional [List [str ]]=None ,
    force_all :bool =False ,
    cancel_callback :Optional [Callable[[],bool ]]=None,
    progress_callback :Optional [Callable[[str, int], None]]=None
    )->Dict [str ,Any ]:
        """合併券商分點資料

        Args:
            branch_system_keys: 要合併的分點列表（None=全部）
            force_all: 是否強制重新合併
            progress_callback: 可選的 (訊息, 百分比) 回調
            cancel_callback: 合作式取消回調；在分點／檔案邊界停止

        Returns:
            dict: 合併結果
        """
        import logging
        logger =logging .getLogger (__name__ )

        logger .info (
        f"[UpdateService] 開始合併券商分點資料: "
        f"branch_system_keys={branch_system_keys}, force_all={force_all}"
        )

        try :
            from app_module .broker_branch_update_service import BrokerBranchUpdateService

            service =BrokerBranchUpdateService (self .config )
            result =service .merge_broker_branch_data (
            branch_system_keys =branch_system_keys ,
            force_all =force_all ,
            progress_callback =progress_callback ,
            cancel_callback =cancel_callback
            )

            logger .info (f"[UpdateService] 券商分點資料合併完成: success={result.get('success', False)}")
            return result

        except Exception as e :
            import traceback
            error_msg =f"合併券商分點資料時發生錯誤: {str(e)}"
            logger .error (f"[UpdateService] {error_msg}")
            logger .error (traceback .format_exc ())
            return {
            'success':False ,
            'message':error_msg ,
            'merged_branches':[],
            'merged_files':0 ,
            'new_records':0 ,
            'total_records':0 ,
            'date_range':{'start_date':'','end_date':''},
            'duplicate_records':0
            }

    def check_broker_branch_data_status (
    self ,
    branch_system_keys :Optional [List [str ]]=None
    )->Dict [str ,Any ]:
        """檢查券商分點資料狀態

        Args:
            branch_system_keys: 要檢查的分點列表（None=全部）

        Returns:
            dict: 狀態字典
        """
        import logging
        logger =logging .getLogger (__name__ )

        logger .info (f"[UpdateService] 檢查券商分點資料狀態: branch_system_keys={branch_system_keys}")

        try :
            from app_module .broker_branch_update_service import BrokerBranchUpdateService

            service =BrokerBranchUpdateService (self .config )
            result =service .check_broker_branch_data_status (
            branch_system_keys =branch_system_keys
            )

            logger .info (f"[UpdateService] 券商分點資料狀態檢查完成: status={result.get('status', 'unknown')}")
            return result

        except Exception as e :
            import traceback
            error_msg =f"檢查券商分點資料狀態時發生錯誤: {str(e)}"
            logger .error (f"[UpdateService] {error_msg}")
            logger .error (traceback .format_exc ())
            return {
            'latest_date':None ,
            'total_records':0 ,
            'date_count':0 ,
            'broker_count':0 ,
            'date_range':{'start_date':None ,'end_date':None },
            'status':'error'
            }

    def _get_indicator_latest_date (self ,indicator_file :Path )->Optional [str ]:
        """取得單一技術指標檔的最新日期"""
        if not indicator_file .exists ():
            return None

        try :
            import pandas as pd

            df_dates =pd .read_csv (
            indicator_file ,
            encoding ='utf-8-sig',
            usecols =['日期'],
            on_bad_lines ='skip',
            engine ='python'
            )
            if df_dates .empty :
                return None

            parsed =pd .to_datetime (df_dates ['日期'],errors ='coerce')
            parsed =parsed [pd .notna (parsed )]
            if len (parsed )==0 :
                return None

            return parsed .max ().strftime ('%Y-%m-%d')
        except Exception :
            return None

    def _run_technical_indicator_process_pool(
        self,
        *,
        calculator,
        tasks: List[tuple[str, Any]],
        publication_rows: Dict[str, List[int]],
        ignore_existing: bool,
        max_workers: int,
        max_in_flight: Optional[int],
        max_retries: int,
        cancel_callback: Optional[Callable[[], bool]],
        progress_callback,
        logger,
        raw_alias_active: bool = False,
        publication_phase_port: Optional[Callable[[str], int]] = None,
    ) -> Dict[str, Any]:
        """執行受控技術指標 worker，並由父程序逐股保存結果。

        ``tasks`` 保留完整 OHLC prefix；worker 用相同 causal kernel 計算後，
        父程序才依 publication rows 裁切，CSV／SQLite 寫入仍只在父程序完成。
        """
        from app_module.technical_indicator_process_pool import (
            run_bounded_indicator_pool,
        )
        import pandas as pd

        pool = run_bounded_indicator_pool(
            tasks,
            max_workers=max_workers,
            max_in_flight=max_in_flight,
            max_retries=max_retries,
            cancel_callback=cancel_callback,
            logger=logger,
        )
        raw_results = pool.get("results", {})
        successful: List[str] = []
        failed: List[str] = list(pool.get("failed_ids", []))
        stored: List[Any] = []
        publications: List[Any] = []

        total = len(tasks)
        for index, (stock_id, group_df) in enumerate(tasks, start=1):
            if _is_cancel_requested(cancel_callback):
                break
            precomputed = raw_results.get(stock_id)
            if not isinstance(precomputed, pd.DataFrame) or precomputed.empty:
                if stock_id not in failed:
                    failed.append(stock_id)
                continue
            row_positions = publication_rows.get(str(stock_id), [])
            if not row_positions:
                continue
            publish_frame = group_df.iloc[row_positions].copy()
            publish_result = precomputed.iloc[row_positions].copy()
            if raw_alias_active:
                _assert_technical_raw_aliases_unchanged(publish_frame, publish_result)
            if progress_callback:
                progress_callback(
                    f"process-pool 父程序寫入 {stock_id} ({index}/{total})...",
                    20 + int((index / max(total, 1)) * 70),
                )
            if publication_phase_port is not None:
                publication_phase_port("stock_file_write_started")
            try:
                result = calculator.calculate_and_store_indicators(
                    publish_frame,
                    stock_id,
                    output_dir=self.config.technical_dir,
                    ignore_existing=ignore_existing,
                    precomputed_result=publish_result,
                )
            except Exception as exc:  # noqa: BLE001
                if publication_phase_port is not None:
                    publication_phase_port("stock_file_write_failed")
                logger.error("process-pool 父程序保存股票 %s 失敗: %s", stock_id, exc)
                result = None
            else:
                if publication_phase_port is not None:
                    publication_phase_port("stock_file_write_returned")
            if isinstance(result, pd.DataFrame):
                stored.append(result)
                publications.append(publish_result)
                successful.append(stock_id)
            elif stock_id not in failed:
                failed.append(stock_id)

        cancelled = _is_cancel_requested(cancel_callback) or pool.get("status") == "cancelled"
        unique_failed = list(dict.fromkeys(str(stock_id) for stock_id in failed))
        summary = {
            key: value
            for key, value in pool.items()
            if key != "results"
        }
        summary["parent_single_writer"] = True
        summary["parent_written_stock_count"] = len(stored)
        summary["parent_write_failed_count"] = len(unique_failed)
        summary["cancelled"] = cancelled
        summary["production_worker_enabled"] = True
        return {
            "report": summary,
            "all_data": stored,
            "publications": publications,
            "success_count": len(successful),
            "updated_stocks": successful,
            "fail_count": len(unique_failed),
            "failed_stocks": unique_failed,
            "cancelled": cancelled,
        }

    def calculate_technical_indicators (
    self ,
    target_stock :Optional [str ]=None ,
    force_all :bool =False ,
    start_date :Optional [str ]=None ,
    progress_callback =None ,
    cancel_callback :Optional [Callable[[],bool ]]=None ,
    ignore_existing_files :bool =False ,
    incremental_lookback_days :int =120 ,
    technical_process_pool :Optional [bool ]=None ,
    technical_process_pool_workers :Optional [int ]=None ,
    technical_process_pool_max_in_flight :Optional [int ]=None ,
    technical_process_pool_max_retries :Optional [int ]=None ,
    recompute_currentity :bool =False,
    publication_phase_port: Optional[Callable[[str], int]] = None,
    )->Dict [str ,Any ]:
        """計算技術指標

        Args:
            target_stock: 要處理的特定股票代號，如為None則處理所有股票
            force_all: 是否強制更新所有數據（忽略日期檢查）
            start_date: 指定開始更新的日期，如為None則自動檢測
            progress_callback: 進度回調函數 (message: str, progress: int) -> None
            cancel_callback: 合作式取消回調；只在安全邊界停止後續計算／寫入
            ignore_existing_files: 是否忽略現有指標文件，直接覆蓋（用於修復有問題的文件）
            incremental_lookback_days: 增量更新時往前回補的交易日數，避免技術指標缺少歷史序列
            recompute_currentity: 已 current 的 technical table 仍需重新計算時，
                只對 bounded lookback window 重算，不清空全量 technical table
            technical_process_pool: 明確覆寫 process-pool feature flag；預設讀取 config，且預設關閉
            technical_process_pool_workers: process-pool worker 上限；僅在 feature flag 開啟時使用
            technical_process_pool_max_in_flight: parent queue 的最大 in-flight 任務數
            technical_process_pool_max_retries: 單一股票 worker 失敗時的有限重試次數

        Returns:
            dict: {
                'success': bool,
                'message': str,
                'total_stocks': int,
                'success_count': int,
                'fail_count': int,
                'insufficient_data_count': int,
                'updated_stocks': list[str],
                'failed_stocks': list[str],
                'start_date': str,
                'end_date': str
            }
        """

        from app_module.technical_indicator_job import (
            TechnicalIndicatorJob,
            TechnicalIndicatorJobPorts,
        )

        ports = TechnicalIndicatorJobPorts(
            config=self.config,
            get_indicator_latest_date=self._get_indicator_latest_date,
            run_process_pool=self._run_technical_indicator_process_pool,
        )
        return TechnicalIndicatorJob(ports).run(
            target_stock=target_stock,
            force_all=force_all,
            start_date=start_date,
            progress_callback=progress_callback,
            cancel_callback=cancel_callback,
            ignore_existing_files=ignore_existing_files,
            incremental_lookback_days=incremental_lookback_days,
            technical_process_pool=technical_process_pool,
            technical_process_pool_workers=technical_process_pool_workers,
            technical_process_pool_max_in_flight=technical_process_pool_max_in_flight,
            technical_process_pool_max_retries=technical_process_pool_max_retries,
            recompute_currentity=recompute_currentity,
            publication_phase_port=publication_phase_port,
        )

    def export_table_to_csv (
    self ,
    table_name :str ,
    target_path :Path ,
    start_date :Optional [str ]=None ,
    end_date :Optional [str ]=None ,
    cancel_callback :Optional [Callable[[],bool ]]=None,
    progress_callback :Optional [Callable[[str, int], None]]=None
    )->Dict [str ,Any ]:
        """從 SQLite 匯出指定表和日期範圍的資料至 CSV

        Args:
            table_name: SQLite 表名
            target_path: 匯出的 CSV 檔案路徑
            start_date: 開始日期（YYYYMMDD 或 YYYY-MM-DD）
            end_date: 結束日期（YYYYMMDD 或 YYYY-MM-DD）
            cancel_callback: 合作式取消回調；在查詢／寫檔安全邊界停止
            progress_callback: 可選的 (訊息, 百分比) 回調；以查詢總筆數估算進度
        """
        import logging
        import os
        import re
        import tempfile

        logger = logging.getLogger(__name__)
        destination = Path(target_path)

        _emit_update_progress(progress_callback, f"準備匯出 {table_name}", 0)

        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name or ""):
            return {
                "success": False,
                "message": f"不允許匯出未知或不安全的 SQLite table：{table_name!r}",
            }

        if _is_cancel_requested(cancel_callback):
            return {
            'success':False ,
            'cancelled':True ,
            'message':f'{table_name} 匯出已取消（尚未開始）'
            }

        try:
            # 匯出屬於讀取既有資料後建立新檔，不能因查詢而建構可寫
            # DBManager（那會初始化 schema／WAL）。
            db = ReadOnlySQLiteManager(self.config.db_file)

            query = f'SELECT * FROM "{table_name}"'
            conditions: list[str] = []
            params: list[Any] = []

            if start_date:
                s_date = self._date_key(start_date)
                if s_date:
                    conditions.append('"日期" >= ?')
                    params.append(s_date)
            if end_date:
                e_date = self._date_key(end_date)
                if e_date:
                    conditions.append('"日期" <= ?')
                    params.append(e_date)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += ' ORDER BY "日期" ASC;'

            logger.info(
                "[UpdateService] 開始從 SQLite 匯出 %s 到 %s，查詢: %s，參數: %s",
                table_name,
                destination,
                query,
                params,
            )

            total_expected: int | None = None
            try:
                count_query = f'SELECT COUNT(*) AS "_total" FROM "{table_name}"'
                if conditions:
                    count_query += " WHERE " + " AND ".join(conditions)
                count_df = db.execute_query(count_query, tuple(params))
                if not count_df.empty:
                    total_expected = max(0, int(count_df.iloc[0]["_total"]))
            except Exception:
                logger.debug("無法取得匯出總筆數，改用無總數進度", exc_info=True)
            _emit_update_progress(
                progress_callback,
                f"開始讀取 {table_name}（預估 {total_expected:,} 筆）"
                if total_expected is not None
                else f"開始讀取 {table_name}（總筆數待讀取）",
                5,
            )

            chunks = db.iter_query(query, tuple(params), chunksize=10_000)
            total_records = 0
            chunk_index = 0
            temp_path: Path | None = None
            temp_fd: int | None = None
            temp_stream: Any = None
            try:
                for chunk in chunks:
                    if _is_cancel_requested(cancel_callback):
                        return {
                            "success": False,
                            "cancelled": True,
                            "processed_records": total_records,
                            "target_preserved": True,
                            "message": f"{table_name} 匯出已取消（停在資料批次邊界，原目標檔保留）",
                        }
                    if chunk.empty:
                        continue

                    chunk_index += 1

                    if "日期" in chunk.columns:
                        chunk = chunk.copy()
                        chunk["日期"] = chunk["日期"].apply(
                            lambda value: (
                                f"{str(value)[:4]}-{str(value)[4:6]}-{str(value)[6:]}"
                                if len(str(value)) == 8
                                else str(value)
                            )
                        )

                    if temp_path is None:
                        if _is_cancel_requested(cancel_callback):
                            return {
                                "success": False,
                                "cancelled": True,
                                "processed_records": total_records,
                                "target_preserved": True,
                                "message": f"{table_name} 匯出已取消（尚未建立暫存檔）",
                            }
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        temp_fd, temp_name = tempfile.mkstemp(
                            prefix=f".{destination.name}.",
                            suffix=".part",
                            dir=str(destination.parent),
                        )
                        temp_path = Path(temp_name)
                        temp_stream = os.fdopen(
                            temp_fd,
                            "w",
                            encoding="utf-8-sig",
                            newline="",
                        )
                        temp_fd = None

                    chunk.to_csv(
                        temp_stream,
                        index=False,
                        header=total_records == 0,
                    )
                    total_records += len(chunk)
                    temp_stream.flush()
                    if total_expected and total_expected > 0:
                        percentage = min(95, 10 + (total_records * 85 // total_expected))
                    else:
                        percentage = min(90, 10 + chunk_index * 5)
                    _emit_update_progress(
                        progress_callback,
                        f"匯出 {table_name}：已處理 {total_records:,} 筆",
                        percentage,
                    )
                    if _is_cancel_requested(cancel_callback):
                        return {
                            "success": False,
                            "cancelled": True,
                            "processed_records": total_records,
                            "target_preserved": True,
                            "message": f"{table_name} 匯出已取消（已完成一批，原目標檔保留）",
                        }

                if total_records == 0:
                    return {
                        "success": False,
                        "message": "沒有符合條件的資料可供匯出",
                        "read_mode": db.last_read_mode,
                    }
                if _is_cancel_requested(cancel_callback):
                    return {
                        "success": False,
                        "cancelled": True,
                        "processed_records": total_records,
                        "target_preserved": True,
                        "message": f"{table_name} 匯出已取消（尚未提交目標檔）",
                    }

                if temp_stream is not None:
                    temp_stream.flush()
                    temp_stream.close()
                    temp_stream = None
                if temp_path is None:
                    raise RuntimeError("匯出未建立暫存檔")
                os.replace(str(temp_path), str(destination))
                temp_path = None
                logger.info("[UpdateService] 成功匯出 %s 筆資料至 %s", total_records, destination)
                _emit_update_progress(progress_callback, f"{table_name} 匯出完成", 100)
                return {
                    "success": True,
                    "message": f"成功匯出 {total_records:,} 筆資料至 {destination.name}",
                    "total_records": total_records,
                    "file_path": str(destination),
                    "read_mode": db.last_read_mode,
                }
            finally:
                if temp_stream is not None:
                    temp_stream.close()
                if temp_fd is not None:
                    os.close(temp_fd)
                if temp_path is not None and temp_path.exists():
                    temp_path.unlink()

        except Exception as e:
            logger .exception (f"[UpdateService] 匯出 {table_name} 失敗")
            return {
            'success':False ,
            'message':f'匯出失敗：{str(e)}'
            }

    def check_decision_data_status(self) -> Dict[str, Any]:
        """分開列出正式入庫與隔離候選資料，不能把正式筆數固定顯示為零。"""
        candidate_db = configured_candidate_db_path()
        formal_reference_date: str | None = None
        if getattr(self.config, "use_sqlite", False):
            try:
                formal_reference_date = self._status_from_sqlite("daily_prices").get(
                    "latest_date"
                )
            except Exception:
                # Candidate status 仍可讀取；正式日價 reference 只是新鮮度提示。
                formal_reference_date = None
        tables = {
            "institutional_flow": ("institutional_flows", "institutional"),
            "credit_transaction": ("credit_transactions", "credit"),
            "tdcc_shareholding": ("tdcc_shareholding", "tdcc"),
        }

        def empty_info() -> Dict[str, Any]:
            return {
                "total_records": 0,
                "earliest_date": "無",
                "latest_date": "無",
                "coverage_pct": "無 checkpoint",
                "distinct_dates": 0,
            }

        def inspect_candidate(table_name: str, source: str) -> Dict[str, Any]:
            if candidate_db is None:
                return {**empty_info(), "candidate_read_status": "not_configured"}
            if not candidate_db.exists():
                return {**empty_info(), "candidate_read_status": "missing"}
            try:
                import sqlite3
                read_only_uri = (
                    f"file:{candidate_db.resolve().as_posix()}?mode=ro"
                )
                with sqlite3.connect(read_only_uri, uri=True) as conn:
                    conn.execute("PRAGMA query_only=ON")
                    row = conn.execute(
                        f"SELECT COUNT(*), MIN(decision_date), MAX(decision_date), "
                        f"COUNT(DISTINCT decision_date) FROM {table_name}"
                    ).fetchone()
                    if row is None or int(row[0]) == 0:
                        return {**empty_info(), "candidate_read_status": "available"}
                    try:
                        success_count, attempted_count = conn.execute(
                            """
                            SELECT
                                COUNT(DISTINCT CASE WHEN status = 'SUCCESS' THEN decision_date END),
                                COUNT(DISTINCT CASE WHEN status IN ('SUCCESS', 'FAILED_RETRYABLE') THEN decision_date END)
                            FROM phase3c_backfill_checkpoints WHERE source = ?
                            """,
                            (source,),
                        ).fetchone()
                    except sqlite3.OperationalError:
                        success_count, attempted_count = 0, 0
                    coverage = (
                        f"{(int(success_count) / int(attempted_count) * 100):.1f}%"
                        if attempted_count
                        else "無 checkpoint"
                    )
                    return {
                        "total_records": int(row[0]),
                        "earliest_date": row[1] or "無",
                        "latest_date": row[2] or "無",
                        "coverage_pct": coverage,
                        "distinct_dates": int(row[3]),
                        "candidate_read_status": "available",
                    }
            except Exception as exc:
                return {
                    **empty_info(),
                    "candidate_read_status": "error",
                    "candidate_read_error": f"{type(exc).__name__}: {exc}",
                }

        result: Dict[str, Any] = {}
        for key, (table_name, source) in tables.items():
            info = inspect_candidate(table_name, source)
            has_candidate = info["total_records"] > 0
            result[key] = {
                "candidate_db_exists": candidate_db is not None and candidate_db.exists(),
                "candidate_db_path": str(candidate_db) if candidate_db else "未設定 PHASE3C_CANDIDATE_DB_PATH",
                **info,
                "quality_pit_status": "PROVENANCE_TRACKED" if has_candidate else "UNAVAILABLE",
                "status": (
                    "CANDIDATE_AVAILABLE"
                    if has_candidate
                    else "BLOCKED_NO_HISTORICAL_ENDPOINT"
                    if source == "tdcc"
                    else "MISSING"
                ),
                "disclaimer": "候選研究資料，不參與評分或投資決策",
                "formal_records": 0,
                "candidate_records": info["total_records"],
                "candidate_earliest_date": info["earliest_date"],
                "candidate_latest_date": info["latest_date"],
                "formal_latest_date": None,
                "formal_earliest_date": None,
                "candidate_status": (
                    "CANDIDATE_AVAILABLE" if has_candidate else info["candidate_read_status"].upper()
                ),
                "formal_status": "MISSING",
            }
            if formal_reference_date:
                result[key]["freshness_reference_date"] = formal_reference_date
                if (
                    source in {"institutional", "credit"}
                    and info["latest_date"] not in {None, "無"}
                    and str(info["latest_date"]) < str(formal_reference_date)
                ):
                    result[key]["freshness_status"] = "lagging"
                    result[key]["warnings"] = [
                        (
                            f"候選資料落後正式日價基準日：候選 {info['latest_date']}；"
                            f"日價 {formal_reference_date}"
                        )
                    ]
        formal_db = getattr(self.config, "db_file", None)
        if formal_db and Path(formal_db).is_file():
            import sqlite3
            from contextlib import closing
            try:
                with closing(sqlite3.connect(Path(formal_db).resolve().as_uri() + "?mode=ro", uri=True)) as conn:
                    for key, (table_name, _) in tables.items():
                        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone()
                        if not exists:
                            continue
                        row = conn.execute(f"SELECT COUNT(*), MIN(decision_date), MAX(decision_date), COUNT(DISTINCT decision_date) FROM {table_name}").fetchone()
                        result[key]["formal_records"] = int(row[0])
                        result[key]["formal_latest_date"] = row[2]
                        result[key]["formal_earliest_date"] = row[1]
                        result[key]["formal_status"] = "FORMAL_AVAILABLE" if row[0] else "MISSING"
                        if row[0]:
                            result[key].update(
                                total_records=int(row[0]), earliest_date=row[1], latest_date=row[2],
                                distinct_dates=int(row[3]), status="FORMAL_AVAILABLE",
                                quality_pit_status="OBSERVED_SOURCE", formal_db_path=str(formal_db),
                                disclaimer="官方來源已入庫；歷史可得時間與研究資格須另行驗證",
                                coverage_pct="見來源日期與逐日覆蓋報告",
                            )
                            result[key]["freshness_status"] = (
                                "lagging" if formal_reference_date and str(row[2]) < str(formal_reference_date) else "unknown"
                            )
                            result[key]["warnings"] = ["已入庫不代表逐市場完整覆蓋，請查看來源驗收。"]
            except sqlite3.Error as exc:
                for info in result.values():
                    info["formal_read_error"] = str(exc)
                    info["formal_status"] = "READ_ERROR"
        return result
