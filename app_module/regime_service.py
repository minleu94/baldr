"""
市場狀態服務 (Regime Service)
提供市場狀態檢測的業務邏輯
"""

from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Dict

import pandas as pd

# 方案 A：不搬檔案，service 層內部 import ui_app 模組
# from ui_app.market_regime_detector import MarketRegimeDetector
from decision_module.market_regime_detector import MarketRegimeDetector
from decision_module.market_regime_policy import (
    RegimeAssessment,
    RegimeTransition,
)
from app_module.dtos import RegimeResultDTO
from app_module.dtos.market_loop_dtos import MarketRegimeDTO
from app_module.regime_history_store import RegimeHistoryStore


class RegimeService:
    """市場狀態服務類"""
    
    def __init__(
        self,
        config,
        regime_detector: Any | None = None,
        *,
        use_persistent_history: bool = False,
        market_frame_provider: Callable[[], pd.DataFrame] | None = None,
    ):
        """初始化市場狀態服務
        
        Args:
            config: TWStockConfig 實例
        """
        self.config = config
        self.regime_detector = regime_detector or MarketRegimeDetector()
        self.use_persistent_history = use_persistent_history
        self._isolated_history: dict[str, object] = {}
        self._isolated_state_lock = RLock()
        self._regime_history_store: RegimeHistoryStore | None = None
        self.market_frame_provider = market_frame_provider
        if isinstance(self.regime_detector, MarketRegimeDetector):
            if self.market_frame_provider is None:
                from app_module.decision_data_providers import (
                    market_index_frame_provider,
                )

                self.market_frame_provider = market_index_frame_provider(config)
            if use_persistent_history:
                history_path = Path(config.resolve_output_path("")) / "regime_history.json"
                self._regime_history_store = RegimeHistoryStore(history_path)
    
    def detect_regime(
        self,
        date: str = None,
        *,
        as_of_date: str = None,
    ) -> RegimeResultDTO:
        """檢測市場狀態
        
        Args:
            date: 日期（YYYY-MM-DD格式），如果為None則使用最新日期
            
        Returns:
            RegimeResultDTO: 市場狀態檢測結果
        """
        if date is None:
            date = as_of_date
        if isinstance(self.regime_detector, MarketRegimeDetector):
            assessment = self._detect_with_state(date)
            regime = assessment.regime
            confidence = assessment.confidence
            details = dict(assessment.details)
        else:
            # 保留測試/custom service 注入器的既有 adapter seam；production
            # MarketRegimeDetector 一律走 explicit-frame/pure-transition 路徑。
            regime_result = self.regime_detector.detect_regime(date=date)
            regime = regime_result.get('regime', 'Trend')
            confidence = regime_result.get('confidence', 0.5)
            details = regime_result.get('details', {})
        
        regime_name_map = {
            'Trend': '趨勢追蹤',
            'Reversion': '均值回歸',
            'Breakout': '突破準備'
        }
        regime_name_cn = regime_name_map.get(regime, regime)
        
        return RegimeResultDTO(
            regime=regime,
            confidence=confidence,
            details=details,
            regime_name_cn=regime_name_cn
        )

    def _detect_with_state(self, decision_date: str | None) -> RegimeAssessment:
        provider = self.market_frame_provider
        if provider is None:
            raise RuntimeError("RegimeService 缺少 market frame provider")
        try:
            frame = provider()
        except Exception as exc:  # noqa: BLE001 - 保留舊 detector 的來源降級契約
            return self._source_failure_assessment(exc)

        expected_fingerprint: str | None = None
        if self.use_persistent_history:
            store = self._regime_history_store
            if store is None:
                raise RuntimeError("persistent regime history store 未初始化")
            prior_history, expected_fingerprint = store.read_snapshot()
        else:
            with self._isolated_state_lock:
                prior_history = deepcopy(self._isolated_history)

        assessment = self.regime_detector.detect_regime(
            frame,
            date=decision_date,
            prior_history=prior_history,
        )
        transition = assessment.transition
        if not transition.persist_candidate:
            if self.use_persistent_history:
                assert self._regime_history_store is not None
                self._regime_history_store.assert_unchanged(expected_fingerprint)
            return assessment

        transition_date = transition.transition_date
        if transition_date is None:
            return assessment

        entry = {
            "regime": transition.candidate_regime,
            "timestamp": datetime.now().isoformat(),
        }
        if self.use_persistent_history:
            assert self._regime_history_store is not None
            self._regime_history_store.commit_candidate(
                date=transition_date,
                regime=transition.candidate_regime,
                timestamp=str(entry["timestamp"]),
                expected_fingerprint=expected_fingerprint,
            )
        else:
            with self._isolated_state_lock:
                self._isolated_history[transition_date] = entry
        return assessment

    @staticmethod
    def _source_failure_assessment(error: Exception) -> RegimeAssessment:
        """把 market source 讀取失敗映成舊有 Trend/error 結果，不碰 state。"""
        return RegimeAssessment(
            regime="Trend",
            confidence=0.5,
            details={"error": str(error)},
            transition=RegimeTransition(
                transition_date=None,
                candidate_regime="Trend",
                effective_regime="Trend",
                prior_regime=None,
                persist_candidate=False,
                outcome="source_unavailable",
            ),
        )

    def detect_regime_dto(
        self,
        as_of_date: date | datetime | str | None = None,
        *,
        decision_date: date | datetime | str | None = None,
    ) -> MarketRegimeDTO:
        """以明確決策日建立市場狀態 DTO。

        舊的 ``detect_regime`` 保留給既有 UI 與服務使用；本方法把有效資料日、
        品質與 fallback 警告提升到應用層契約，讓呼叫端不必猜測來源日期。
        """

        requested = self._coerce_date(decision_date if decision_date is not None else as_of_date)
        requested_text = requested.isoformat() if requested is not None else None
        try:
            result = self.detect_regime(date=requested_text)
        except Exception as exc:  # noqa: BLE001
            return MarketRegimeDTO(
                decision_date=requested,
                effective_date=None,
                regime=None,
                regime_name_cn=None,
                match_score_bp=None,
                quality="degraded",
                warnings=(f"market_regime_error:{exc}",),
                details={"error": str(exc)},
            )

        details = dict(result.details or {})
        effective = self._coerce_date(details.get("date"))
        warnings: list[str] = []
        if requested is not None and effective is None:
            warnings.append("market_regime_effective_date_unknown")
        elif requested is not None and effective is not None and effective != requested:
            warnings.append(f"market_regime_as_of_fallback:{effective.isoformat()}")
        if "error" in details:
            warnings.append("market_regime_detector_degraded")
        quality = "observed" if effective is not None and "error" not in details else "degraded"
        dto = MarketRegimeDTO.from_legacy(
            result,
            decision_date=requested,
            effective_date=effective,
            quality=quality,
            warnings=tuple(warnings),
        )
        return dto

    @staticmethod
    def _coerce_date(value: object) -> date | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value).strip().replace("/", "-")
        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None
    
    def get_strategy_config(self, regime: str) -> Dict[str, Any]:
        """獲取指定市場狀態的策略配置
        
        Args:
            regime: 'Trend' | 'Reversion' | 'Breakout'
            
        Returns:
            dict: 策略配置字典
        """
        return self.regime_detector.get_strategy_config(regime)

