"""
數據傳輸對象 (Data Transfer Objects)
定義服務層的輸入輸出結構
"""

from dataclasses import dataclass, field
from typing import List, Mapping, Optional, Dict, Any, cast
from enum import Enum
from copy import deepcopy
from decimal import Decimal
import pandas as pd

from app_module.dtos.portfolio_dtos import (
    JournalEntryDTO,
    PortfolioDTO,
    PositionDTO,
    TradeDTO,
)
from app_module.dtos.decision_continuity_dtos import (
    ACTION_ACCEPTED,
    ACTION_ADDED,
    ACTION_CLEARED,
    ACTION_NOTE,
    ACTION_REMOVED,
    ACTION_REVIEW_SCHEDULED,
    ACTION_SKIPPED,
    ACTION_UPDATED,
    DECISION_CONTINUITY_RECORD_TYPE,
    DECISION_CONTINUITY_SCHEMA_VERSION,
    DECISION_CONTINUITY_TOMBSTONE_ACTIONS,
    DECISION_IDENTITY_SCHEMA_VERSION,
    DecisionContinuityRevision,
    DecisionIdentity,
    IDENTITY_STATUS_CONFLICT,
    IDENTITY_STATUS_LINKED,
    IDENTITY_STATUS_UNKNOWN,
    IDENTITY_STATUS_UNLINKED,
)


class ValidationStatus(Enum):
    """驗證狀態（Phase 3.5 SOP 護欄）"""
    PASS = "PASS"  # 符合 SOP，無問題
    WARNING = "WARNING"  # 有警告但不阻擋
    FAIL = "FAIL"  # 不符合 SOP，禁止 Promote


from app_module.recommendation.legacy_dtos import (
    RecommendationDTO,
    RecommendationResultDTO,
)


@dataclass
class RegimeResultDTO:
    """市場狀態檢測結果"""
    regime: str  # 'Trend', 'Reversion', 'Breakout'
    confidence: float  # 0-1
    details: Dict[str, Any]
    regime_name_cn: str  # 中文名稱
    
    def to_dict(self) -> dict:
        """轉換為字典"""
        return {
            'regime': self.regime,
            'regime_name_cn': self.regime_name_cn,
            'confidence': self.confidence,
            'details': self.details
        }


@dataclass
class BacktestReportDTO:
    """回測報告數據傳輸對象"""
    total_return: float
    annual_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    expectancy: float  # 期望值（平均報酬）
    details: Dict[str, Any]
    baseline_comparison: Optional[Dict[str, Any]] = None  # Baseline 對比結果
    overfitting_risk: Optional[Dict[str, Any]] = None  # 過擬合風險評估結果
    
    # ========== Phase 3.5 SOP 護欄欄位 ==========
    changed_layers: List[str] = field(default_factory=list)  # 記錄本次研究中被修改的層級
    validation_status: ValidationStatus = ValidationStatus.PASS  # 驗證狀態
    sample_insufficient_flags: Dict[str, bool] = field(default_factory=dict)  # 樣本不足標記
    validation_messages: List[str] = field(default_factory=list)  # 驗證訊息（用於 UI 顯示）
    
    def to_dict(self) -> dict:
        """轉換為字典"""
        result = {
            '總報酬率': self.total_return,
            '年化報酬率': self.annual_return,
            '夏普比率': self.sharpe_ratio,
            '最大回撤': self.max_drawdown,
            '勝率': self.win_rate,
            '總交易次數': self.total_trades,
            '期望值': self.expectancy,
            '詳細信息': self.details
        }
        if self.baseline_comparison:
            result['Baseline對比'] = self.baseline_comparison
        if self.overfitting_risk:
            result['過擬合風險'] = self.overfitting_risk
        
        # Phase 3.5 SOP 護欄欄位
        result['changed_layers'] = self.changed_layers
        result['validation_status'] = self.validation_status.value
        result['sample_insufficient_flags'] = self.sample_insufficient_flags
        result['validation_messages'] = self.validation_messages
        
        return result

