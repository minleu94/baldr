"""
參數最佳化服務 (Optimizer Service)
支援 Grid Search 參數掃描和最佳化
"""

import itertools
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
import pandas as pd
import os
from concurrent.futures import CancelledError, ThreadPoolExecutor, wait, FIRST_COMPLETED
from app_module.exceptions import BacktestCancelledError
from app_module.registered_strategy_spec import registered_strategy_spec
from app_module.backtest_contracts import profit_factor_projection
from app_module.single_backtest_metrics_contract import (
    decode_single_backtest_metrics_contract,
)
import logging

logger = logging.getLogger(__name__)


@dataclass
class ParamRange:
    """參數範圍定義"""
    name: str
    type: str  # 'int', 'float', 'list'
    values: List[Any]  # 固定值列表
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None


@dataclass
class OptimizationResult:
    """最佳化結果"""
    params: Dict[str, Any]
    metrics: Dict[str, Any]
    rank: int = 0
    run_id: Optional[str] = None
    metric_status: Dict[str, str] = field(default_factory=dict)


class OptimizerService:
    """參數最佳化服務"""

    def __init__(self, backtest_service, run_repository=None, max_workers: Optional[int] = None):
        """
        初始化最佳化服務

        Args:
            backtest_service: BacktestService 實例
            run_repository: BacktestRunRepository 實例（可選，用於保存結果）
            max_workers: 最大並行工作線程數（None 表示使用 CPU 核心數，但限制最大為 8）
        """
        self.backtest_service = backtest_service
        # 預設使用 CPU 核心數，但限制最大為 8 以避免過載
        if max_workers is None:
            max_workers = min(os.cpu_count() or 4, 8)
        self.max_workers = max_workers
        logger.info(f"[OptimizerService] 初始化，最大並行線程數: {self.max_workers}")
        self.run_repository = run_repository

    def param_values_for_range(self, param_range: ParamRange) -> List[Any]:
        """
        依 ParamRange 產生單一參數的候選值清單。

        這個 helper 讓組合數預估與實際 grid 生成共用同一套規則，避免 UI
        預估和實際執行量不一致。
        """
        if param_range.type == 'list':
            return list(param_range.values)

        if param_range.type == 'int':
            if param_range.min is not None and param_range.max is not None:
                step = int(param_range.step or 1)
                if step <= 0:
                    raise ValueError(f"參數 {param_range.name} 的步長必須大於 0")
                if int(param_range.max) < int(param_range.min):
                    return []
                return list(
                    range(int(param_range.min), int(param_range.max) + 1, step)
                )
            return list(param_range.values)

        if param_range.type == 'float':
            if param_range.min is not None and param_range.max is not None:
                float_step = Decimal(str(param_range.step or 1))
                if float_step <= 0:
                    raise ValueError(f"參數 {param_range.name} 的步長必須大於 0")
                current = Decimal(str(param_range.min))
                max_value = Decimal(str(param_range.max))
                if max_value < current:
                    return []
                values = []
                while current <= max_value:
                    values.append(float(current.quantize(Decimal("0.01"))))
                    current += float_step
                return values
            return list(param_range.values)

        return list(param_range.values)

    def estimate_param_grid_size(self, param_ranges: Dict[str, ParamRange]) -> int:
        """估算參數組合數，不 materialize 每一組參數字典。"""
        if not param_ranges:
            return 1

        total = 1
        for param_range in param_ranges.values():
            total *= len(self.param_values_for_range(param_range))
        return total

    def generate_param_grid(self, param_ranges: Dict[str, ParamRange]) -> List[Dict[str, Any]]:
        """
        生成參數網格

        Args:
            param_ranges: 參數範圍字典 {param_name: ParamRange}

        Returns:
            參數組合列表
        """
        # 為每個參數生成值列表
        param_value_lists = {}
        for param_name, param_range in param_ranges.items():
            param_value_lists[param_name] = self.param_values_for_range(param_range)

        # 生成所有組合
        param_names = list(param_value_lists.keys())
        param_values = [param_value_lists[name] for name in param_names]

        return [
            dict(zip(param_names, combination))
            for combination in itertools.product(*param_values)
        ]

    def grid_search(
        self,
        stock_code: str,
        start_date: str,
        end_date: str,
        strategy_id: str,
        base_params: Dict[str, Any],
        param_ranges: Dict[str, ParamRange],
        capital: float = 1000000.0,
        fee_bps: float = 14.25,
        slippage_bps: float = 5.0,
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
        objective: str = 'sharpe_ratio',  # 'sharpe_ratio', 'cagr', 'cagr_mdd'
        top_n: int = 20,
        progress_callback: Optional[Callable] = None,
        check_cancel: Optional[Callable[[], bool]] = None
    ) -> List[OptimizationResult]:
        """
        執行 Grid Search 參數掃描

        Args:
            stock_code: 股票代號
            start_date: 開始日期
            end_date: 結束日期
            strategy_id: 策略ID
            base_params: 基礎參數（固定參數）
            param_ranges: 要掃描的參數範圍
            capital: 初始資金
            fee_bps: 手續費
            slippage_bps: 滑價
            stop_loss_pct: 停損百分比
            take_profit_pct: 停利百分比
            objective: 目標指標
            top_n: 返回前N名結果
            progress_callback: 進度回調函數 (current, total, message)

        Returns:
            最佳化結果列表（已排序）
        """

        if strategy_id == "baldr_vcp_three_contractions_v1":
            raise ValueError("三段轉折收縮目前僅支持正常單股研究，參數掃描保存契約尚未接受")
        if strategy_id == "baldr_bollinger_squeeze_v1":
            raise ValueError("布林帶寬低點突破目前僅支持正常單股研究，參數掃描契約尚未接受")
        # 生成參數網格
        param_combinations = self.generate_param_grid(param_ranges)
        total_combinations = len(param_combinations)

        if progress_callback:
            progress_callback(0, total_combinations, f"開始掃描 {total_combinations} 組參數（使用 {self.max_workers} 個線程）...")

        logger.info(f"[OptimizerService] 開始 Grid Search，共 {total_combinations} 組參數，使用 {self.max_workers} 個並行線程")

        # 在讀取行情與啟動組合前固定此輪登記版本，不能在不同組合間換版。
        registered_spec = registered_strategy_spec(strategy_id, config={})

        # ✅ 優化：預先載入數據一次，所有參數組合共用
        logger.info(f"[OptimizerService] 預先載入數據（股票 {stock_code}，日期範圍 {start_date} 到 {end_date}）...")
        preloaded_data, actual_start_date, actual_end_date = self.backtest_service._load_stock_data(
            stock_code, start_date, end_date
        )

        if preloaded_data is None or len(preloaded_data) == 0:
            logger.error(f"[OptimizerService] 無法載入數據，參數掃描終止")
            return []

        # 記錄日期調整信息（只在第一次顯示）
        if actual_start_date != start_date or actual_end_date != end_date:
            logger.warning(
                f"[OptimizerService] ⚠️ 日期範圍已自動調整: "
                f"請求 {start_date}~{end_date} → 實際 {actual_start_date}~{actual_end_date}"
            )

        logger.info(f"[OptimizerService] 數據載入完成，共 {len(preloaded_data)} 筆數據，開始參數掃描...")

        results = []
        completed_count = 0

        # 定義單個參數組合的回測函數
        def run_single_backtest(param_combo, idx):
            """執行單個參數組合的回測"""
            try:
                # 合併基礎參數和掃描參數
                full_params = {**base_params, **param_combo}

                # 創建策略規格
                strategy_spec = replace(registered_spec, config={'params': full_params})

                # 執行回測（使用預載入的數據）
                report = self.backtest_service.run_backtest(
                    stock_code=stock_code,
                    start_date=start_date,
                    end_date=end_date,
                    strategy_spec=strategy_spec,
                    capital=capital,
                    fee_bps=fee_bps,
                    slippage_bps=slippage_bps,
                    stop_loss_pct=stop_loss_pct,
                    take_profit_pct=take_profit_pct,
                    preloaded_data=preloaded_data,  # ✅ 使用預載入的數據
                    actual_start_date=actual_start_date,  # ✅ 傳遞實際日期範圍
                    actual_end_date=actual_end_date
                )

                if report.details.get('error'):
                    raise ValueError("原回測未完成，不得將錯誤報告的零值列入排名")

                # 計算目標分數
                manifest = report.details.get('data_manifest')
                if not isinstance(manifest, dict):
                    manifest = {}
                raw_metrics = {
                    'total_return': report.total_return,
                    'annual_return': report.annual_return,
                    'sharpe_ratio': report.sharpe_ratio,
                    'max_drawdown': report.max_drawdown,
                    'win_rate': report.win_rate,
                    'total_trades': report.total_trades,
                    'expectancy': report.expectancy,
                }
                projection = decode_single_backtest_metrics_contract(
                    manifest,
                    raw_metrics,
                    run_type='single_backtest',
                    universe=[report.details.get('stock_code', stock_code)],
                )
                metric_names = tuple(raw_metrics)
                if projection is None:
                    # 舊 fake／保存報告維持排序相容性，但其數值不升級為已觀測。
                    metric_status = {name: 'legacy_unverified' for name in metric_names}
                    metric_values = dict(raw_metrics)
                else:
                    projected_values = {
                        'total_return': projection['total_return'],
                        'annual_return': projection['annual_return'],
                        'sharpe_ratio': projection['sharpe_ratio'],
                        'max_drawdown': projection['max_drawdown'],
                        'win_rate': projection['win_rate'],
                        'total_trades': projection['completed_trades'],
                        'expectancy': projection['expectancy'],
                    }
                    metric_status = {
                        name: 'observed' if projected_values[name] is not None else 'unavailable'
                        for name in metric_names
                    }
                    metric_values = projected_values

                if objective == 'sharpe_ratio':
                    objective_metric = 'sharpe_ratio'
                elif objective == 'cagr':
                    objective_metric = 'annual_return'
                elif objective == 'cagr_mdd':
                    objective_metric = 'cagr_mdd'
                else:
                    objective_metric = 'sharpe_ratio'

                if projection is not None:
                    required = ('annual_return', 'max_drawdown') if objective_metric == 'cagr_mdd' else (
                        'annual_return' if objective_metric == 'cagr' else 'sharpe_ratio',
                    )
                    if any(metric_status[name] != 'observed' for name in required):
                        raise ValueError(f"目標指標 {objective} 明示不可用，略過此參數組合")
                    if objective_metric == 'cagr_mdd':
                        # 沿用既有 CAGR + 負值 MDD 權衡；只組合同份報告的已保存值。
                        score = metric_values['annual_return'] + metric_values['max_drawdown']
                    else:
                        score = metric_values[required[0]]
                    metric_status['objective'] = 'observed'
                else:
                    # Legacy 相容排序；狀態會明示未經契約驗證。
                    annual = Decimal(str(report.annual_return))
                    drawdown = Decimal(str(report.max_drawdown))
                    if objective_metric == 'cagr_mdd':
                        score = annual + drawdown
                    elif objective_metric == 'cagr':
                        score = report.annual_return
                    else:
                        score = report.sharpe_ratio
                    metric_status['objective'] = 'legacy_unverified'

                try:
                    finite_score = Decimal(str(score))
                except (InvalidOperation, TypeError, ValueError) as exc:
                    raise ValueError("目標分數不是有限原值") from exc
                if not finite_score.is_finite():
                    raise ValueError("目標分數不是有限原值")

                # 構建結果
                result = OptimizationResult(
                    params=full_params,
                    metrics={
                        **metric_values,
                        **profit_factor_projection(report.details),
                        'score': score  # 目標分數
                    },
                    metric_status=metric_status,
                )
                return (idx, result, None)

            except Exception as e:
                # 記錄錯誤但繼續
                error_msg = f"參數組合 {param_combo} 回測或指標契約驗證失敗: {e}"
                logger.warning(f"[OptimizerService] {error_msg}")
                return (idx, None, error_msg)

        # 使用線程池並行執行，手動初始化以利安全軟取消
        executor = ThreadPoolExecutor(max_workers=self.max_workers)

        future_to_idx = {}
        pending: set[Any] = set()
        next_submit_idx = 0
        max_in_flight = max(1, self.max_workers * 2)
        completed_results = {}
        cancellation_requested = False

        def request_cancel(message: Optional[str] = None):
            nonlocal cancellation_requested
            if cancellation_requested:
                return
            cancellation_requested = True
            for fut in pending:
                fut.cancel()
            if progress_callback:
                progress_callback(
                    completed_count,
                    total_combinations,
                    message or f"取消已送出，正在清理已啟動的 {len(pending)} 個子任務..."
                )
            executor.shutdown(wait=False, cancel_futures=True)

        def submit_next_batch():
            nonlocal next_submit_idx
            while (
                next_submit_idx < total_combinations
                and len(pending) < max_in_flight
                and not cancellation_requested
            ):
                if check_cancel and check_cancel():
                    remaining = total_combinations - completed_count
                    request_cancel(f"取消已送出，剩餘 {remaining} 組參數將不再提交，正在清理已啟動子任務...")
                    return

                param_combo = param_combinations[next_submit_idx]
                future = executor.submit(run_single_backtest, param_combo, next_submit_idx)
                future_to_idx[future] = next_submit_idx
                pending.add(future)
                next_submit_idx += 1

        try:
            submit_next_batch()

            while pending:
                # 輪詢檢查取消旗標
                if not cancellation_requested and check_cancel and check_cancel():
                    remaining = total_combinations - completed_count
                    request_cancel(f"取消已送出，剩餘 {remaining} 組參數將不再提交，正在清理已啟動子任務...")

                done, pending = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)

                for future in done:
                    idx = future_to_idx[future]
                    try:
                        idx_res, result, error = future.result()
                        if not cancellation_requested:
                            completed_results[idx] = (result, error)
                            completed_count += 1

                            # 更新進度
                            if progress_callback:
                                progress_callback(
                                    completed_count,
                                    total_combinations,
                                    f"已完成 {completed_count}/{total_combinations} ({completed_count/total_combinations*100:.1f}%)"
                                )
                    except CancelledError:
                        if not cancellation_requested:
                            logger.error(f"最佳化子任務 {idx} 被取消")
                    except Exception as e:
                        if cancellation_requested and not str(e):
                            continue
                        logger.error(f"最佳化子任務 {idx} 異常: {e}")

                if not cancellation_requested:
                    submit_next_batch()

            if cancellation_requested:
                raise BacktestCancelledError("參數最佳化任務已被使用者取消")
        finally:
            if not cancellation_requested:
                executor.shutdown(wait=True)

        # 按原始順序整理結果
        for idx in range(total_combinations):
            if idx in completed_results:
                result, error = completed_results[idx]
                if result is not None:
                    results.append(result)

        # 按目標分數排序
        results.sort(key=lambda x: x.metrics.get('score', 0), reverse=True)

        # 設置排名
        for rank, result in enumerate(results, 1):
            result.rank = rank

        # 返回前N名
        return results[:top_n]

    def create_optimization_summary(self, results: List[OptimizationResult]) -> pd.DataFrame:
        """
        創建最佳化結果摘要表格

        Args:
            results: 最佳化結果列表

        Returns:
            DataFrame
        """
        summary_data = []

        for result in results:
            pf = profit_factor_projection(result.metrics)
            statuses = result.metric_status or {}
            def display_metric(name):
                status = statuses.get(name, 'legacy_unverified')
                if status != 'observed':
                    return None
                return result.metrics.get(name)

            row = {
                '排名': result.rank,
                **{f'參數_{k}': v for k, v in result.params.items()},
                '總報酬率%': None if display_metric('total_return') is None else display_metric('total_return') * 100,
                '年化報酬率%': None if display_metric('annual_return') is None else display_metric('annual_return') * 100,
                '夏普比率': display_metric('sharpe_ratio'),
                '最大回撤%': None if display_metric('max_drawdown') is None else display_metric('max_drawdown') * 100,
                '勝率%': None if display_metric('win_rate') is None else display_metric('win_rate') * 100,
                '交易次數': display_metric('total_trades'),
                '期望值%': None if display_metric('expectancy') is None else display_metric('expectancy') * 100,
                '獲利因子': pf['profit_factor'],
                '獲利因子狀態': pf['profit_factor_status'],
                '獲利因子語意': pf['profit_factor_semantics'],
                '目標分數': result.metrics.get('score'),
                '目標指標狀態': statuses.get('objective', 'legacy_unverified'),
                '總報酬率狀態': statuses.get('total_return', 'legacy_unverified'),
                '年化報酬率狀態': statuses.get('annual_return', 'legacy_unverified'),
                '夏普比率狀態': statuses.get('sharpe_ratio', 'legacy_unverified'),
                '最大回撤狀態': statuses.get('max_drawdown', 'legacy_unverified'),
                '勝率狀態': statuses.get('win_rate', 'legacy_unverified'),
                '交易次數狀態': statuses.get('total_trades', 'legacy_unverified'),
                '期望值狀態': statuses.get('expectancy', 'legacy_unverified'),
            }
            summary_data.append(row)

        summary = pd.DataFrame(summary_data)
        if '交易次數' in summary:
            # 觀測零配對保持整數顯示；缺值使用 pandas nullable integer 保留空格。
            summary['交易次數'] = pd.array(summary['交易次數'], dtype='Int64')
        return summary

