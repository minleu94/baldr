"""三段收縮沿原request／BacktestService捕捉一次輸入，不另造撮合或保存器。"""
from copy import deepcopy
from dataclasses import asdict
import decimal
import hashlib
from io import BytesIO
import inspect
from pathlib import Path
import platform
from typing import Any

import numpy as np
import pandas as pd

from decision_module.strategies.baldr_vcp_contract import (
    CONTEXT_POLICY, EXECUTION_SCHEMA, LOOKBACK_CALENDAR_DAYS, MAX_PRIOR_ROWS,
    PARAMETER_CONTRACT, STRATEGY_ID, STRATEGY_VERSION, rule_definition,
)


def execute_vcp_backtest_with_rule_source(request: Any, service: Any, *, check_cancel: Any = None) -> Any:
    from app_module.vcp_rule_card import capture_vcp_observation
    from analysis_module.technical_analysis.technical_date_support import safe_convert_technical_dates
    from backtest_module.broker_simulator import BrokerConfig, BrokerSimulator, NEXT_OPEN_CONTRACT
    from backtest_module.conservative_fill_policy import ConservativeFillPolicy
    from decision_module.strategies.baldr_vcp_executor import BaldrVCPExecutor, _base, _observe_frame
    from decision_module.strategies.contracts import StrategyMeta
    from decision_module.strategies.registry import StrategyRegistry
    from financial_module.units import to_decimal
    from ui_qt.views.backtest.research_run_metadata import execute_single_backtest_with_rule_source, json_safe

    if ((request.strategy_id, request.strategy_spec.strategy_id, request.strategy_spec.strategy_version)
            != (STRATEGY_ID, STRATEGY_ID, STRATEGY_VERSION) or request.execution_price != "next_open"
            or request.allow_pyramid or request.stop_loss_atr_mult is not None or request.take_profit_atr_mult is not None
            or request.strategy_params != request.strategy_spec.config.get("params", {})):
        raise ValueError("三段轉折收縮僅支持原1.0.0單股規格、next_open、不加碼及百分比風控")
    rule_definition(request.strategy_params)

    class BoundExecution:
        def run_backtest(self, **kwargs: Any) -> Any:
            if check_cancel is not None and check_cancel():
                raise InterruptedError("回測已取消")
            context_start = (pd.Timestamp(kwargs["start_date"]) - pd.Timedelta(days=LOOKBACK_CALENDAR_DAYS)).strftime("%Y-%m-%d")
            frame, _, _ = service._load_stock_data(kwargs["stock_code"], context_start, kwargs["end_date"])
            if frame is None or frame.empty:
                return service._create_empty_report("三段收縮原輸入不存在，未生成當次保存來源")
            if (not isinstance(frame.index, pd.DatetimeIndex) or frame.index.hasnans or frame.index.tz is not None
                    or frame.index.has_duplicates or not frame.index.is_monotonic_increasing
                    or not frame.index.equals(frame.index.normalize())
                    or frame.index.min() < pd.Timestamp(context_start) or frame.index.max() > pd.Timestamp(kwargs["end_date"])):
                raise ValueError("三段收縮原輸入日期身分或期間不符")
            before = frame.index < pd.Timestamp(kwargs["start_date"])
            frame = pd.concat([frame.loc[before].tail(MAX_PRIOR_ROWS), frame.loc[~before]]).copy(deep=True)
            raw = BytesIO()
            frame.to_parquet(raw, index=True)
            fingerprint = "sha256:" + hashlib.sha256(raw.getvalue()).hexdigest()
            from app_module.strategy_signal_context import capture_strategy_signal_context
            signal_comparison_context = capture_strategy_signal_context(frame, stock_code=kwargs["stock_code"],
                start_date=kwargs["start_date"], end_date=kwargs["end_date"])
            spec = deepcopy(kwargs["strategy_spec"])
            if spec.data_version is not None and spec.data_version != fingerprint:
                raise ValueError("三段收縮宣告輸入版本與同次原輸入不符")
            spec.data_version = fingerprint
            executor = StrategyRegistry.get_executor(spec)
            if type(executor) is not BaldrVCPExecutor:
                raise ValueError("三段收縮typed executor不符")
            raw_meta = StrategyRegistry.get_strategy_meta(STRATEGY_ID, version=STRATEGY_VERSION)
            metadata = deepcopy(raw_meta.to_dict() if isinstance(raw_meta, StrategyMeta) else raw_meta)
            if (not isinstance(metadata, dict) or metadata.get("strategy_id") != STRATEGY_ID
                    or metadata.get("strategy_version") != STRATEGY_VERSION):
                raise ValueError("三段收縮原Registry metadata不符")
            context = {"lookback_calendar_days": LOOKBACK_CALENDAR_DAYS, "max_prior_rows": MAX_PRIOR_ROWS,
                       "start_date": frame.index[0].strftime("%Y-%m-%d"), "end_date": frame.index[-1].strftime("%Y-%m-%d"),
                       "prior_rows": int((frame.index < pd.Timestamp(kwargs["start_date"])).sum()), "state_policy": CONTEXT_POLICY}
            kwargs.update(strategy_spec=spec, strategy_executor=executor, preloaded_data=frame,
                          actual_start_date=context["start_date"], actual_end_date=context["end_date"],
                          signal_context_start_date=context_start)
            report = service.run_backtest(**kwargs)
            if check_cancel is not None and check_cancel():
                raise InterruptedError("回測已取消，不發布完整規則來源")
            details = dict(report.details or {})
            if details.get("execution_contract") != NEXT_OPEN_CONTRACT:
                return report
            broker = BrokerConfig(**{key: kwargs[key] for key in inspect.signature(BrokerConfig).parameters if key in kwargs})
            sources = {}
            for source in (BaldrVCPExecutor, _observe_frame, _base, rule_definition, safe_convert_technical_dates,
                           BrokerSimulator, type(service), ConservativeFillPolicy, to_decimal,
                           execute_vcp_backtest_with_rule_source, execute_single_backtest_with_rule_source, capture_vcp_observation):
                filename = inspect.getsourcefile(source)
                if filename is None:
                    raise ValueError("三段收縮執行來源缺失")
                sources[source.__module__ + "." + source.__name__] = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
            execution = json_safe({
                "schema": EXECUTION_SCHEMA, "strategy_spec": spec.to_dict(), "registry_metadata": metadata,
                "source_hashes": sources, "input_fingerprint": fingerprint, "executor": {},
                "broker_config": asdict(broker), "execution_contract": NEXT_OPEN_CONTRACT,
                "stock_code": kwargs["stock_code"], "start_date": details["start_date"], "end_date": details["end_date"],
                "required_features": list(frame.columns), "benchmark": details.get("benchmark_results") or None,
                "qualification": {"validation_status": getattr(report.validation_status, "value", "unknown"),
                                  "historical_pit_eligible": False, "performance_evaluable": False},
                "rules": rule_definition(spec.config.get("params", {})), "signals": details.get("rule_signal_observations"),
                "input_context": context,
                "analysis_runtime": {"python": platform.python_version(), "decimal": decimal.__libmpdec_version__,
                                     "pandas": pd.__version__, "numpy": np.__version__},
            })
            manifest = dict(details.get("data_manifest") or {})
            manifest.update(strategy_spec=json_safe(spec.to_dict()), single_backtest_rule_execution=execution)
            manifest["signal_comparison_context"] = signal_comparison_context
            execution["qualification"]["signal_context_schema"] = signal_comparison_context["schema"]
            execution["qualification"]["signal_context_sha256"] = signal_comparison_context["sha256"]
            details.update(strategy_version=STRATEGY_VERSION, parameter_contract_version=PARAMETER_CONTRACT,
                           data_version=fingerprint, data_as_of_date=details["end_date"], data_manifest=manifest,
                           can_promote=False, promotion_blocker="三段收縮為研究假說，來源／PIT與績效資格尚未接受")
            if check_cancel is not None and check_cancel():
                raise InterruptedError("回測已取消，不發布完整規則來源")
            report.details = details
            return report

    return request.execute(BoundExecution(), check_cancel=check_cancel)
