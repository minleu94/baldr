"""以明確應用 ports 協調技術指標發布工作。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from data_module.config import TWStockConfig

from app_module.update_service import (
    _assert_technical_raw_aliases_unchanged,
    _can_replace_full_technical_market,
    _daily_price_symbol_universe,
    _is_cancel_requested,
    _merge_partial_technical_publications,
    _preflight_and_ensure_technical_indicator_schema,
    _validate_technical_raw_alias_frame,
    _write_technical_indicator_publications,
    update_data_normalization,
    validate_excluded_price_frame,
)


TECHNICAL_INDICATOR_JOB_PORT_NAMES = (
    "config",
    "get_indicator_latest_date",
    "run_process_pool",
)


@dataclass(frozen=True, slots=True)
class TechnicalIndicatorJobPorts:
    """技術指標 job 需要的三個明確應用 ports。"""

    config: TWStockConfig
    get_indicator_latest_date: Callable[[Path], Optional[str]]
    run_process_pool: Callable[..., Dict[str, Any]]

    def __post_init__(self) -> None:
        if not callable(self.get_indicator_latest_date):
            raise TypeError("get_indicator_latest_date 必須可呼叫")
        if not callable(self.run_process_pool):
            raise TypeError("run_process_pool 必須可呼叫")


class TechnicalIndicatorJob:
    """執行技術指標發布流程。"""

    def __init__(self, ports: TechnicalIndicatorJobPorts) -> None:
        if not isinstance(ports, TechnicalIndicatorJobPorts):
            raise TypeError("技術指標 job 需要 TechnicalIndicatorJobPorts")
        self._ports = ports

    def run (
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
        requested_start_date = start_date
        import os
        import sys
        import importlib .util
        import logging
        import traceback

        logger =logging .getLogger ("app_module.update_service" )

        def record_publication_phase(phase_name: str) -> None:
            """呼叫可選的來源階段 port，不寫入產品 artifact。"""

            if publication_phase_port is not None:
                publication_phase_port(phase_name)

        process_pool_enabled = (
            bool(getattr(self._ports.config, "technical_process_pool_enabled", False))
            if technical_process_pool is None
            else bool(technical_process_pool)
        )
        process_pool_workers = int(
            technical_process_pool_workers
            if technical_process_pool_workers is not None
            else getattr(self._ports.config, "technical_process_pool_workers", 2)
        )
        process_pool_max_in_flight = (
            technical_process_pool_max_in_flight
            if technical_process_pool_max_in_flight is not None
            else getattr(self._ports.config, "technical_process_pool_max_in_flight", 4)
        )
        process_pool_max_retries = int(
            technical_process_pool_max_retries
            if technical_process_pool_max_retries is not None
            else getattr(self._ports.config, "technical_process_pool_max_retries", 1)
        )

        logger .info (
        f"[UpdateService] 開始計算技術指標: "
        f"target_stock={target_stock}, force_all={force_all}, start_date={start_date}, "
        f"recompute_currentity={recompute_currentity}, "
        f"process_pool_enabled={process_pool_enabled}"
        )

        record_publication_phase("run_started")
        if _is_cancel_requested(cancel_callback):
            record_publication_phase("cancel_before_start")
            return {
            'success':False ,
            'cancelled':True ,
            'message':'技術指標計算已取消（尚未開始）',
            'total_stocks':0 ,
            'success_count':0 ,
            'fail_count':0 ,
            'insufficient_data_count':0 ,
            'updated_stocks':[] ,
            'failed_stocks':[] ,
            'start_date':'',
            'end_date':''
            }

        if progress_callback :
            progress_callback ("初始化技術指標計算器...",5 )

        try :
        # 導入技術指標計算模組
            from analysis_module .technical_analysis .technical_indicators import TechnicalIndicatorCalculator

            # 創建計算器
            calculator =TechnicalIndicatorCalculator (logger )

            if progress_callback :
                progress_callback ("讀取股票數據...",10 )

                # 讀取股票數據
            import pandas as pd
            if getattr (self._ports.config ,'use_sqlite',False ):
                try :
                    from data_module .db_manager import DBManager
                    db =DBManager (self._ports.config )
                    logger .info ("優先從 SQLite 載入價格數據進行技術指標計算...")
                    table_info_df =db .execute_query ("PRAGMA table_info(daily_prices);")
                    table_columns =[str (v ).strip ()for v in table_info_df ["name"]]if not table_info_df .empty else []
                    date_column ="日期"
                    stock_column ="股票代號"
                    for candidate in ("日期","date","trade_date","trading_date","Date"):
                        if candidate in table_columns :
                            date_column =candidate
                            break
                    for candidate in ("證券代號","股票代號","stock_code","stock_id"):
                        if candidate in table_columns :
                            stock_column =candidate
                            break
                    stock_data =db .execute_query (
                    f'SELECT * FROM daily_prices ORDER BY "{date_column}" ASC, "{stock_column}" ASC;'
                    )
                    if not stock_data .empty :
                    # 確保日期與代號為字串型態，與後續邏輯一致
                        if date_column in stock_data .columns :
                            stock_data [date_column ]=stock_data [date_column ].astype (str )
                        if stock_column in stock_data .columns :
                            stock_data [stock_column ]=stock_data [stock_column ].astype (str ).str .strip ()
                    else :
                        logger .warning ("SQLite daily_prices 表為空，降級讀取 CSV...")
                        stock_data =pd .read_csv (self._ports.config .stock_data_file ,dtype ={'證券代號':str },low_memory =False )
                except Exception as sql_err :
                    logger .warning (f"從 SQLite 載入價格數據失敗: {sql_err}，降級讀取 CSV...")
                    stock_data =pd .read_csv (self._ports.config .stock_data_file ,dtype ={'證券代號':str },low_memory =False )
            else :
                stock_data =pd .read_csv (self._ports.config .stock_data_file ,dtype ={'證券代號':str },low_memory =False )

            record_publication_phase("input_loaded")

            revision_database = Path(getattr(self._ports.config, 'db_file', Path(self._ports.config.stock_data_file).parent.parent / 'sqlite/twstock.db'))
            from data_module.formal_technical_raw_alias_repair import (
                create_raw_alias_writer_context,
                normalize_raw_alias_values_for_storage,
            )

            raw_alias_context = create_raw_alias_writer_context(revision_database)
            raw_alias_active = raw_alias_context is not None
            if raw_alias_active:
                # 僅在正式 alias marker 有效時，先用共用 Decimal parser 處理受保護欄位。
                # 此段在 SQLite 讀取 fallback 區塊之外，格式錯誤會 fail closed，不改讀 CSV。
                stock_data = normalize_raw_alias_values_for_storage(stock_data)

            # 其餘行情欄位維持既有轉型規則；六個受保護 alias 已先完成精確解析。
            numeric_cols = [
                '成交股數', '成交筆數', '成交金額', '開盤價', '最高價', '最低價', '收盤價',
                '漲跌價差', '最後揭示買價', '最後揭示買量', '最後揭示賣價', '最後揭示賣量', '本益比',
            ]
            for col in numeric_cols:
                if col in stock_data.columns:
                    stock_data[col] = pd.to_numeric(stock_data[col], errors='coerce')

            validate_excluded_price_frame(revision_database, stock_data)

            stock_code_column =next (
            (col for col in ('證券代號','股票代號','證券代號','stock_id','stock_code')if col in stock_data .columns ),
            None ,
            )
            if stock_code_column is None :
                stock_code_candidates =[c for c in stock_data .columns if '代號'in str (c )]
                stock_code_column =stock_code_candidates [0 ]if stock_code_candidates else None
            if stock_code_column is None :
                return {
                'success':False ,
                'message':'技術指標計算失敗：找不到可用的股票代碼文桩',
                'total_stocks':0 ,
                'success_count':0 ,
                'fail_count':1 ,
                'insufficient_data_count':0 ,
                'updated_stocks':[],
                'failed_stocks':[target_stock ]if target_stock else [],
                'start_date':'',
                'end_date':''
                }

            stock_data =stock_data .copy ()
            stock_data [stock_code_column ]=stock_data [stock_code_column ].astype (str ).str .strip ()
            if raw_alias_active:
                existing_symbols = _daily_price_symbol_universe(revision_database)
                stock_data[stock_code_column] = stock_data[stock_code_column].map(
                    update_data_normalization.stock_code_key
                )
                stock_data = stock_data[
                    stock_data[stock_code_column].isin(existing_symbols)
                ]
            else:
                stock_data =stock_data [stock_data [stock_code_column ].str .match (r'^\d{4}$')]

            # 如果指定了特定股票，只處理該股票
            if target_stock :
                if target_stock not in stock_data [stock_code_column ].unique ():
                    return {
                    'success':False ,
                    'message':f'指定的股票 {target_stock} 不存在於股票數據中',
                    'total_stocks':0 ,
                    'success_count':0 ,
                    'fail_count':1 ,
                    'insufficient_data_count':0 ,
                    'updated_stocks':[],
                    'failed_stocks':[target_stock ],
                    'start_date':'',
                    'end_date':''
                    }
                stock_data =stock_data [stock_data [stock_code_column ]==target_stock ]

            raw_alias_full_market_prevalidated = False
            if (
                raw_alias_active
                and force_all
                and target_stock is None
                and requested_start_date is None
                and not recompute_currentity
            ):
                _validate_technical_raw_alias_frame(
                    revision_database,
                    stock_data,
                    replace_all=True,
                    raw_alias_context=raw_alias_context,
                )
                raw_alias_full_market_prevalidated = True

            def validate_publication_raw_aliases(frame):
                if raw_alias_active and not raw_alias_full_market_prevalidated:
                    _validate_technical_raw_alias_frame(
                        revision_database,
                        frame,
                        raw_alias_context=raw_alias_context,
                    )

            auto_incremental =not force_all and start_date is None
            if auto_incremental :
                logger .info (
                f"使用智慧增量技術指標計算，回看 {incremental_lookback_days} 個交易日"
                )
                if progress_callback :
                    progress_callback (
                    f"使用智慧增量模式，回看 {incremental_lookback_days} 個交易日",
                    15
                    )
            elif force_all :
                start_date =None
                logger .info ("強制更新所有數據")
                if progress_callback :
                    progress_callback ("強制更新所有數據",15 )

                    # 批次處理
            grouped =stock_data .groupby (stock_code_column )
            total_stocks =len (grouped )

            if _is_cancel_requested(cancel_callback):
                record_publication_phase("cancel_after_input_load")
                return {
                'success':False ,
                'cancelled':True ,
                'message':'技術指標計算已取消（完成資料載入後）',
                'total_stocks':total_stocks ,
                'success_count':0 ,
                'fail_count':0 ,
                'insufficient_data_count':0 ,
                'updated_stocks':[] ,
                'failed_stocks':[] ,
                'start_date':'',
                'end_date':''
                }

            if progress_callback :
                progress_callback (f"開始處理 {total_stocks} 支股票的技術指標...",20 )

            results :Dict [str ,Any ]={
            'total_stocks':total_stocks ,
            'success_count':0 ,
            'fail_count':0 ,
            'insufficient_data_count':0 ,
            'updated_stocks':[],
            'failed_stocks':[],
            'insufficient_stocks':[],
            'start_date':'',
            'end_date':'',
            'technical_process_pool': {
                'enabled': process_pool_enabled,
                'production_worker_enabled': process_pool_enabled,
                'parent_single_writer': True,
            },
            'sqlite_write_failed': False,
            'recompute_currentity': bool(recompute_currentity),
            }

            all_data =[]
            sqlite_publications: List[pd.DataFrame] = []
            pending_process_pool_tasks :List [tuple[str ,pd .DataFrame ]]=[]
            pending_publication_rows: Dict[str, List[int]] = {}
            min_date ="9999-12-31"
            max_date ="1900-01-01"

            # 處理每檔股票
            for idx ,(stock_id ,group_df )in enumerate (grouped ):
                if _is_cancel_requested(cancel_callback):
                    record_publication_phase("cancel_before_stock")
                    results ['start_date']=min_date if min_date !="9999-12-31"else "未知"
                    results ['end_date']=max_date if max_date !="1900-01-01"else "未知"
                    return {
                    'success':False ,
                    'cancelled':True ,
                    'message':f'技術指標計算已取消（停止於 {stock_id} 前）',
                    **results
                    }
                progress =20 +int ((idx /total_stocks )*70 )# 20% 到 90%
                if progress_callback :
                    progress_callback (f"處理 {stock_id} ({idx+1}/{total_stocks})...",progress )

                group_df =group_df .copy ()
                for legacy_col ,canonical_col in (
                ('日期','日期'),
                ('證券代號','證券代號'),
                ):
                    if legacy_col ==canonical_col :
                        continue
                    if legacy_col in group_df .columns and canonical_col in group_df .columns :
                        group_df =group_df .drop (columns =[legacy_col ])
                    elif legacy_col in group_df .columns :
                        group_df =group_df .rename (columns ={legacy_col :canonical_col })

                        # 跳過數據量不足的股票
                if len (group_df )<self._ports.config .min_data_days :
                    logger .debug (f"股票 {stock_id} 數據量不足，跳過")
                    results ['insufficient_data_count']+=1
                    results ['insufficient_stocks'].append (stock_id )
                    continue

                group_date_column ='日期'if '日期'in group_df .columns else (
                '日期'if '日期'in group_df .columns else None
                )

                if group_date_column:
                    from analysis_module.technical_analysis.technical_date_support import (
                        safe_convert_technical_dates,
                    )

                    parsed_dates = pd.to_datetime(
                        safe_convert_technical_dates(group_df[group_date_column]),
                        errors="coerce",
                    )
                    group_df = (
                        group_df.assign(_causal_sort_date=parsed_dates)
                        .sort_values(
                            "_causal_sort_date", kind="stable", na_position="last"
                        )
                        .drop(columns=["_causal_sort_date"])
                        .reset_index(drop=True)
                    )
                    parsed_dates = pd.to_datetime(
                        safe_convert_technical_dates(group_df[group_date_column]),
                        errors="coerce",
                    ).reset_index(drop=True)
                else:
                    group_df = group_df.reset_index(drop=True)
                    parsed_dates = pd.Series(pd.NaT, index=group_df.index)

                # 記錄日期範圍
                if group_date_column :
                    valid_dates = parsed_dates.dropna()
                    group_min_date = (
                        valid_dates.min().strftime('%Y-%m-%d')
                        if not valid_dates.empty
                        else "未知"
                    )
                    group_max_date = (
                        valid_dates.max().strftime('%Y-%m-%d')
                        if not valid_dates.empty
                        else "未知"
                    )
                    min_date =min (min_date ,group_min_date )
                    max_date =max (max_date ,group_max_date )

                # 先判定發布列；計算仍保留整段排序後的 OHLC prefix。
                publish_mask = pd.Series(True, index=group_df.index)
                if recompute_currentity and group_date_column:
                    sorted_dates = (
                        pd.Series(parsed_dates.dropna().unique())
                        .sort_values()
                        .reset_index(drop=True)
                    )
                    if len(sorted_dates) == 0:
                        logger.debug(
                            f"股票 {stock_id} 沒有可用日期，跳過 currentity bounded 重算"
                        )
                        continue
                    warmup_index = max(
                        len(sorted_dates) - max(int(incremental_lookback_days), 1),
                        0,
                    )
                    warmup_start = sorted_dates.iloc[warmup_index]
                    publish_mask = parsed_dates >= warmup_start
                    logger.debug(
                        f"股票 {stock_id} currentity bounded 重算從 "
                        f"{warmup_start.strftime('%Y-%m-%d')} 開始"
                    )
                elif auto_incremental and group_date_column :
                    indicator_file =self._ports.config .technical_dir /f'{stock_id}_indicators.csv'
                    existing_latest_date =self._ports.get_indicator_latest_date (indicator_file )
                    if existing_latest_date and not ignore_existing_files :
                        latest_ts =pd .to_datetime (existing_latest_date ,errors ='coerce')
                        if pd .notna (latest_ts ):
                            has_new_data =(parsed_dates >latest_ts ).any ()
                            if not has_new_data :
                                logger .debug (f"股票 {stock_id} 沒有新數據需要更新")
                                continue

                            sorted_dates =(
                            pd .Series (parsed_dates .dropna ().unique ())
                            .sort_values ()
                            .reset_index (drop =True )
                            )
                            previous_dates =sorted_dates [sorted_dates <=latest_ts ]
                            if len (previous_dates )>0 :
                                warmup_index =max (len (previous_dates )-max(int(incremental_lookback_days), 1) ,0 )
                                warmup_start =previous_dates .iloc [warmup_index ]
                            else :
                                warmup_start =sorted_dates .iloc [0 ]
                            publish_mask = parsed_dates >= warmup_start
                            logger .debug (
                            f"股票 {stock_id} 智慧增量從 {warmup_start.strftime('%Y-%m-%d')} 重新計算"
                            )
                    else :
                        logger .debug (f"股票 {stock_id} 無既有指標檔，使用完整股價序列計算")
                elif start_date and group_date_column and not force_all :
                    cutoff = pd.to_datetime(
                        safe_convert_technical_dates(pd.Series([start_date])),
                        errors="coerce",
                    ).iloc[0]
                    publish_mask = parsed_dates > cutoff
                    if not publish_mask.any() :
                        logger .debug (f"股票 {stock_id} 沒有新數據需要更新")
                        continue

                if not publish_mask.any():
                    logger.debug(f"股票 {stock_id} 沒有可發布的技術指標列")
                    continue
                publication_rows = publish_mask.to_numpy().nonzero()[0].tolist()
                pending_publication_rows[str(stock_id)] = publication_rows

                    # 計算並保存指標
                if _is_cancel_requested(cancel_callback):
                    record_publication_phase("cancel_before_stock_compute")
                    results ['start_date']=min_date if min_date !="9999-12-31"else "未知"
                    results ['end_date']=max_date if max_date !="1900-01-01"else "未知"
                    return {
                    'success':False ,
                    'cancelled':True ,
                    'message':f'技術指標計算已取消（尚未處理 {stock_id}）',
                    **results
                    }
                if process_pool_enabled:
                    # worker 接收完整 prefix；父程序在計算後才裁切發布列。
                    validate_publication_raw_aliases(
                        group_df.iloc[publication_rows].copy()
                    )
                    pending_process_pool_tasks.append((str(stock_id), group_df.copy()))
                    continue
                try :
                    publish_frame = group_df.iloc[publication_rows].copy()
                    validate_publication_raw_aliases(publish_frame)
                    computed = calculator.calculate_all_indicators(group_df, stock_id)
                    if not isinstance(computed, pd.DataFrame):
                        raise ValueError(f"股票 {stock_id} 技術指標計算失敗")
                    publish_result = computed.iloc[publication_rows].copy()
                    if raw_alias_active:
                        _assert_technical_raw_aliases_unchanged(publish_frame, publish_result)
                    record_publication_phase("stock_file_write_started")
                    try:
                        result =calculator .calculate_and_store_indicators (
                        publish_frame ,
                        stock_id ,
                        output_dir =self._ports.config .technical_dir ,
                        ignore_existing =ignore_existing_files or force_all,
                        precomputed_result=publish_result,
                        )
                    except Exception:
                        record_publication_phase("stock_file_write_failed")
                        raise
                    record_publication_phase("stock_file_write_returned")

                    if isinstance (result ,pd .DataFrame ):
                        all_data .append (result )
                        sqlite_publications.append(publish_result.copy())
                        results ['success_count']+=1
                        results ['updated_stocks'].append (stock_id )
                        logger .debug (f"成功處理股票 {stock_id}")
                    else :
                        results ['fail_count']+=1
                        results ['failed_stocks'].append (stock_id )
                        logger .warning (f"處理股票 {stock_id} 失敗")
                    if _is_cancel_requested(cancel_callback):
                        record_publication_phase("cancel_after_stock_write")
                        results ['start_date']=min_date if min_date !="9999-12-31"else "未知"
                        results ['end_date']=max_date if max_date !="1900-01-01"else "未知"
                        return {
                        'success':False ,
                        'cancelled':True ,
                        'message':f'技術指標計算已取消（已完成 {stock_id}）',
                        **results
                        }
                except Exception as e :
                    record_publication_phase("stock_processing_failed")
                    logger .error (f"處理股票 {stock_id} 時發生錯誤: {str(e)}")
                    results ['fail_count']+=1
                    results ['failed_stocks'].append (stock_id )

                    if _is_cancel_requested(cancel_callback):
                        record_publication_phase("cancel_after_stock_failure")
                        results ['start_date']=min_date if min_date !="9999-12-31"else "未知"
                        results ['end_date']=max_date if max_date !="1900-01-01"else "未知"
                        return {
                        'success':False ,
                        'cancelled':True ,
                        'message':f'技術指標計算已取消（處理 {stock_id} 後）',
                        **results
                        }

                    # 更新結果日期範圍
            process_pool_report = None
            if process_pool_enabled and pending_process_pool_tasks:
                process_pool_result = self._ports.run_process_pool(
                    calculator=calculator,
                    tasks=pending_process_pool_tasks,
                    publication_rows=pending_publication_rows,
                    ignore_existing=ignore_existing_files or force_all,
                    max_workers=process_pool_workers,
                    max_in_flight=process_pool_max_in_flight,
                    max_retries=process_pool_max_retries,
                    cancel_callback=cancel_callback,
                    progress_callback=progress_callback,
                    logger=logger,
                    raw_alias_active=raw_alias_active,
                    publication_phase_port=publication_phase_port,
                )
                process_pool_report = process_pool_result["report"]
                results["technical_process_pool"] = process_pool_report
                all_data.extend(process_pool_result["all_data"])
                sqlite_publications.extend(process_pool_result["publications"])
                results["success_count"] += process_pool_result["success_count"]
                results["updated_stocks"].extend(process_pool_result["updated_stocks"])
                results["fail_count"] += process_pool_result["fail_count"]
                results["failed_stocks"].extend(process_pool_result["failed_stocks"])
                if process_pool_result["cancelled"]:
                    record_publication_phase("cancel_after_process_pool")
                    results ['start_date']=min_date if min_date !="9999-12-31"else "未知"
                    results ['end_date']=max_date if max_date !="1900-01-01"else "未知"
                    return {
                    'success':False ,
                    'cancelled':True ,
                    'message':'技術指標 process-pool 計算已取消（已停止後續合併）',
                    **results
                    }
            results ['start_date']=min_date if min_date !="9999-12-31"else "未知"
            results ['end_date']=max_date if max_date !="1900-01-01"else "未知"

            if _is_cancel_requested(cancel_callback):
                record_publication_phase("cancel_before_merge")
                return {
                'success':False ,
                'cancelled':True ,
                'message':'技術指標計算已取消（尚未合併輸出）',
                **results
                }

            full_market_replace = _can_replace_full_technical_market(
                force_all=force_all,
                target_stock=target_stock,
                requested_start_date=requested_start_date,
                recompute_currentity=recompute_currentity,
                cancelled=_is_cancel_requested(cancel_callback),
                success_count=results['success_count'],
                fail_count=results['fail_count'],
                insufficient_count=results['insufficient_data_count'],
                total_stocks=total_stocks,
                updated_stocks=results['updated_stocks'],
            )

            # 合併並儲存所有結果
            if all_data :
                if progress_callback :
                    progress_callback ("合併所有指標數據...",90 )

                logger .info ("合併所有指標數據...")

                if _is_cancel_requested(cancel_callback):
                    record_publication_phase("cancel_before_publication_merge")
                    return {
                    'success':False ,
                    'cancelled':True ,
                    'message':'技術指標計算已取消（合併前）',
                    **results
                    }

                # ✅ 數據驗證：檢查每個 DataFrame 的完整性
                valid_data =[]
                for idx ,df in enumerate (all_data ):
                    if df is None or len (df )==0 :
                        logger .warning (f"跳過空數據（索引 {idx}）")
                        continue

                    df =df .rename (columns ={
                    '日期':'日期',
                    '證券代號':'證券代號',
                    })
                    df =df .loc [:,~df .columns .duplicated (keep ='last')]

                    # 檢查必要欄位
                    required_cols =['日期','證券代號']
                    missing_cols =[col for col in required_cols if col not in df .columns ]
                    if missing_cols :
                        logger .warning (f"跳過缺少必要欄位 {missing_cols} 的數據（索引 {idx}）")
                        continue

                        # 檢查日期欄位是否有效
                    if '日期'in df .columns :
                        date_col =pd .to_datetime (df ['日期'],errors ='coerce')
                        valid_dates =date_col .notna ().sum ()
                        if valid_dates ==0 :
                            logger .warning (f"跳過日期欄位無效的數據（索引 {idx}）")
                            continue

                    valid_data .append (df )

                if not valid_data :
                    record_publication_phase("publication_merge_failed")
                    logger .error ("沒有有效的數據可以合併！")
                    return {
                    'success':False ,
                    'message':'沒有有效的數據可以合併，請檢查技術指標計算結果',
                    **results
                    }

                    # 合併有效數據
                final_df =pd .concat (valid_data ,ignore_index =True )

                # ✅ 數據驗證：檢查合併後的數據
                logger .info (f"合併前有效數據數量: {len(valid_data)}")
                logger .info (f"合併後總筆數: {len(final_df):,}")
                logger .info (f"合併後股票數量: {final_df['證券代號'].nunique() if '證券代號' in final_df.columns else 'N/A'}")

                # 檢查是否有重複數據
                if '日期'in final_df .columns and '證券代號'in final_df .columns :
                    duplicates =final_df .duplicated (subset =['日期','證券代號']).sum ()
                    if duplicates >0 :
                        logger .warning (f"發現 {duplicates} 筆重複數據（日期+證券代號），將去重")
                        final_df =final_df .drop_duplicates (subset =['日期','證券代號'],keep ='last')
                        logger .info (f"去重後總筆數: {len(final_df):,}")

                save_path =self._ports.config .all_stocks_data_file
                skip_csv_save =getattr (self._ports.config ,'use_sqlite',False )and auto_incremental

                if _is_cancel_requested(cancel_callback):
                    record_publication_phase("cancel_before_aggregate_csv")
                    return {
                    'success':False ,
                    'cancelled':True ,
                    'message':'技術指標計算已取消（寫入整合輸出前）',
                    **results
                    }

                if not skip_csv_save :
                    csv_publication = final_df
                    if not full_market_replace:
                        if save_path.exists():
                            existing_csv = pd.read_csv(
                                save_path,
                                encoding='utf-8-sig',
                                dtype={'證券代號': str},
                            )
                            csv_publication = _merge_partial_technical_publications(
                                existing_csv,
                                final_df,
                            )
                        else:
                            # 不建立內容只有本輪 subset 的 all-stocks 快取。
                            csv_publication = None
                            results['all_stocks_csv_skipped'] = True
                            logger.warning(
                                "本輪不是完整全市場替換且尚無 all_stocks_data.csv；略過建立 subset 彙總檔。"
                            )
                    if csv_publication is not None:
                        if save_path.exists():
                            logger .info (f"備份現有的整合指標文件: {save_path}")
                            self._ports.config .create_backup (save_path )
                        record_publication_phase("aggregate_csv_write_started")
                        try:
                            csv_publication.to_csv(
                                save_path,
                                index=False,
                                encoding='utf-8-sig',
                            )
                        except Exception:
                            record_publication_phase("aggregate_csv_write_failed")
                            raise
                        record_publication_phase("aggregate_csv_write_completed")
                        file_size_mb =save_path .stat ().st_size /1024 /1024
                        logger .info (f"已保存整合指標到: {save_path}（檔案大小: {file_size_mb:.2f} MB）")
                else :
                    logger .info ("智慧增量模式且啟用 SQLite，跳過大型 all_stocks_data.csv 合併重寫，直接使用增量寫入 SQLite。")

                    # 🌟 如果啟用 SQLite，同步將指標寫入 SQLite technical_indicators 表中
                if getattr (self._ports.config ,'use_sqlite',False ):
                    if _is_cancel_requested(cancel_callback):
                        record_publication_phase("cancel_before_sqlite_write")
                        return {
                        'success':False ,
                        'cancelled':True ,
                        'message':'技術指標計算已取消（尚未寫入 SQLite）',
                        **results
                        }
                    logger .info ("檢測到啟用 SQLite，開始同步寫入資料庫 technical_indicators 表...")
                    if progress_callback :
                        progress_callback ("正在將指標寫入 SQLite 資料庫...",95 )
                    sqlite_transaction_started = False
                    try :
                        from data_module .db_manager import DBManager
                        db =DBManager (self._ports.config )

                        if not sqlite_publications:
                            logger.warning("沒有已成功保存的技術指標發布列，SQLite 不做任何變更。")
                            df_db = pd.DataFrame()
                        else:
                            df_db = pd.concat(sqlite_publications, ignore_index=True)
                        df_db =df_db .rename (columns ={
                        '日期':'日期',
                        '證券代號':'證券代號',
                        })
                        df_db =df_db .loc [:,~df_db .columns .duplicated (keep ='last')]
                        if not df_db.empty:
                            from analysis_module.technical_analysis.technical_date_support import (
                                safe_convert_technical_dates,
                            )

                            normalized_dates = pd.to_datetime(
                                safe_convert_technical_dates(df_db['日期']),
                                errors='coerce',
                            )
                            if normalized_dates.isna().any():
                                raise ValueError("SQLite 技術指標發布列含無效日期")
                            df_db['日期'] = normalized_dates.dt.strftime('%Y%m%d')
                            df_db ['證券代號']=df_db ['證券代號'].astype (str ).str .zfill (4 )

                        # 剔除價格與重複欄位以防止重複儲存
                        cols_to_drop =[c for c in ['證券名稱','開盤價','最高價','最低價','收盤價','成交股數','成交量']if c in df_db .columns ]
                        if cols_to_drop :
                            df_db =df_db .drop (columns =cols_to_drop )

                            # 確保 non-PK 欄位為數值型
                        for col in df_db .columns :
                            if col not in ['日期','證券代號']:
                                df_db [col ]=pd .to_numeric (df_db [col ],errors ='coerce')

                        if not df_db.empty:
                            validate_excluded_price_frame(Path(db.db_path), df_db)
                            # 最終 SQL schema/delete/upsert mutation 前重新探測 marker。
                            # 計算期間若剛完成 formal apply，必須先套 guard 再升級 schema。
                            df_db, raw_alias_context = (
                                _preflight_and_ensure_technical_indicator_schema(
                                    db,
                                    df_db,
                                    replace_all=full_market_replace,
                                    raw_alias_context=raw_alias_context,
                                )
                            )
                            # DELETE（若符合完整全市場替換條件）與 UPSERT 必須同一連線、同一交易；
                            # 所有其他模式只 UPSERT 本輪成功計算且成功發布的 key。
                            sqlite_transaction_started = True
                            record_publication_phase("sqlite_transaction_started")
                            with db.connect() as conn:
                                written_rows = _write_technical_indicator_publications(
                                    conn,
                                    df_db,
                                    replace_market=full_market_replace,
                                    database_path=Path(db.db_path),
                                    raw_alias_prevalidated=True,
                                    raw_alias_context=raw_alias_context,
                                )
                            record_publication_phase("sqlite_transaction_committed")
                            if full_market_replace:
                                logger.info("完整全市場重算已在單一交易中替換 technical_indicators。")
                            else:
                                logger.info(
                                    "已在單一交易中更新 %s 筆已核實技術指標發布列。",
                                    written_rows,
                                )
                    except Exception as sql_err :
                        record_publication_phase(
                            "sqlite_transaction_failed"
                            if sqlite_transaction_started
                            else "sqlite_publication_failed_before_transaction"
                        )
                        logger .error (f"技術指標同步寫入 SQLite 時發生錯誤: {sql_err}")
                        results['sqlite_write_failed'] = True

                if progress_callback :
                    progress_callback ("技術指標計算完成",100 )

                    # 生成結果訊息
            message =(
            f"技術指標計算完成：\n"
            f"總處理股票數: {results['total_stocks']}\n"
            f"成功處理數: {results['success_count']}\n"
            f"失敗數: {results['fail_count']}\n"
            f"數據不足股票數: {results['insufficient_data_count']}\n"
            f"處理數據日期範圍: {results['start_date']} 至 {results['end_date']}"
            )

            process_pool_failed = bool(
                process_pool_report
                and process_pool_report.get("status") in {"failed", "partial"}
            )
            record_publication_phase(
                "run_completed_with_failures"
                if results['fail_count'] or results['sqlite_write_failed'] or process_pool_failed
                else "run_completed"
            )
            return {
            'success':not process_pool_failed and results['fail_count'] == 0 and not results['sqlite_write_failed'],
            'message':message ,
            **results
            }

        except Exception as e :
            record_publication_phase("run_failed")
            error_msg =f"計算技術指標時發生錯誤: {str(e)}"
            logger .error (error_msg )
            logger .error (traceback .format_exc ())
            return {
            'success':False ,
            'message':f"{error_msg}\n{traceback.format_exc()}",
            'total_stocks':0 ,
            'success_count':0 ,
            'fail_count':0 ,
            'insufficient_data_count':0 ,
            'updated_stocks':[],
            'failed_stocks':[],
            'start_date':'',
            'end_date':''
            }
