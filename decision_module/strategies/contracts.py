"""
策略規格與每日訊號契約
定義 StrategySpec、StrategyExecutor、StrategyMeta 與 DailySignalFrame
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Protocol, runtime_checkable
from datetime import datetime
import pandas as pd


@dataclass
class StrategySpec:
    """策略規格（純資料，可序列化為 JSON/YAML）"""
    strategy_id: str  # 固定 ID，例如 "breakout_momentum_v1"
    strategy_version: str  # 例如 "1.0.0"
    data_version: Optional[str] = None  # 對應技術指標版本/資料修復版本
    name: str = ""  # 顯示名稱
    description: str = ""  # 策略說明
    regime: List[str] = field(default_factory=list)  # 適用 Regime: ['Trend', 'Reversion', 'Breakout']
    risk_level: str = "medium"  # 'low', 'medium', 'high'
    target_type: str = "stock"  # 'stock', 'industry', 'both'
    default_params: Dict[str, Any] = field(default_factory=dict)  # 預設參數
    config: Dict[str, Any] = field(default_factory=dict)  # 完整策略配置（technical, patterns, signals, filters）
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典（可序列化）"""
        return {
            'strategy_id': self.strategy_id,
            'strategy_version': self.strategy_version,
            'data_version': self.data_version,
            'name': self.name,
            'description': self.description,
            'regime': self.regime,
            'risk_level': self.risk_level,
            'target_type': self.target_type,
            'default_params': self.default_params,
            'config': self.config
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StrategySpec':
        """從字典創建（反序列化）"""
        return cls(**data)


@dataclass
class StrategyMeta:
    """策略元數據（適用/不適用 Regime、風險屬性）"""
    strategy_id: str
    strategy_version: str
    name: str
    description: str  # 策略說明（Why，不是 How）
    regime: List[str]  # 適用 Regime: ['Trend', 'Reversion', 'Breakout']
    risk_level: str  # 'low', 'medium', 'high'
    not_suitable_regime: List[str] = field(default_factory=list)  # 不適用 Regime
    risk_description: str = ""  # 風險敘述
    target_type: str = "stock"  # 'stock', 'industry', 'both'
    default_params: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        """初始化後處理"""
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return {
            'strategy_id': self.strategy_id,
            'strategy_version': self.strategy_version,
            'name': self.name,
            'description': self.description,
            'regime': self.regime,
            'risk_level': self.risk_level,
            'target_type': self.target_type,
            'default_params': self.default_params,
            'risk_description': self.risk_description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


@runtime_checkable
class StrategyExecutor(Protocol):
    """策略執行器介面（Protocol）"""

    def __init__(self, spec: StrategySpec) -> None:
        ...
    
    def generate_signals(
        self, 
        df: pd.DataFrame, 
        spec: StrategySpec,
        execution_start_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        生成每日信號
        
        Args:
            df: 股票數據 DataFrame（必須包含日期索引和技術指標）
            spec: 策略規格
            execution_start_date: 交易狀態開始日；更早資料只供指標與門檻歷史使用
        
        Returns:
            DailySignalFrame: index=date，欄位含 signal, score breakdown, reason tags
                - signal: int (1=買入, 0=持有, -1=賣出)
                - score: float (總分 0-100)
                - indicator_score: float
                - pattern_score: float
                - volume_score: float
                - reason_tags: List[str] (可序列化為字符串)
                - regime_match: bool
                - ... (其他技術指標欄位)
        """
        ...


def create_daily_signal_frame(
    df: pd.DataFrame,
    signals: pd.Series,
    scores: Dict[str, pd.Series],
    reason_tags: pd.Series,
    regime_match: pd.Series
) -> pd.DataFrame:
    """
    創建 DailySignalFrame（統一輸出格式）
    
    Args:
        df: 原始數據 DataFrame（必須有日期索引）
        signals: 信號序列（1=買入, 0=持有, -1=賣出）
        scores: 分數字典 {'score': Series, 'indicator_score': Series, ...}
        reason_tags: 理由標籤序列（每個元素是 List[str]）
        regime_match: Regime 匹配序列（bool）
    
    Returns:
        DailySignalFrame: 統一的信號輸出格式
    """
    result = df.copy()
    
    # 確保日期索引
    if '日期' in result.columns:
        result = result.set_index('日期')
    
    # 添加信號和分數
    result['signal'] = signals
    for key, value in scores.items():
        result[key] = value
    
    # 添加理由標籤（轉換為字符串以便序列化）
    result['reason_tags'] = reason_tags.apply(lambda x: ','.join(x) if isinstance(x, list) else str(x))
    result['regime_match'] = regime_match
    
    return result


class DailySignalFrame:
    """每日信號框架（統一輸出格式）"""
    
    @staticmethod
    def create(
        df: pd.DataFrame,
        signals: pd.Series,
        scores: Dict[str, pd.Series],
        reason_tags: pd.Series,
        regime_match: Optional[pd.Series] = None
    ) -> pd.DataFrame:
        """
        創建 DailySignalFrame
        
        Args:
            df: 原始數據 DataFrame（必須有日期索引或日期欄位）
            signals: 信號序列（1=買入, 0=持有, -1=賣出）
            scores: 分數字典 {'score': Series, 'indicator_score': Series, 'pattern_score': Series, 'volume_score': Series}
            reason_tags: 理由標籤序列（每個元素是 List[str] 或 str）
            regime_match: Regime 匹配序列（bool，可選）
        
        Returns:
            DailySignalFrame: index=date，欄位含 signal, score breakdown, reason tags
        """
        result = df.copy()
        
        # 確保日期索引
        date_index = None
        if isinstance(result.index, pd.DatetimeIndex):
            date_index = result.index
        elif '日期' in result.columns:
            result['日期'] = pd.to_datetime(result['日期'])
            date_index = result['日期']
            result = result.set_index('日期')
        else:
            raise ValueError("DataFrame 必須有日期索引或日期欄位")
        
        # 確保 signals 和 scores 的索引匹配
        if not signals.index.equals(date_index):
            signals = signals.reindex(date_index, fill_value=0)
        for key in scores:
            if not scores[key].index.equals(date_index):
                scores[key] = scores[key].reindex(date_index, fill_value=0.0)
        
        # 添加信號
        result['signal'] = signals
        
        # 添加分數
        for key, value in scores.items():
            result[key] = value
        
        # 添加理由標籤（轉換為字符串以便序列化）
        if reason_tags is not None:
            if not reason_tags.index.equals(date_index):
                reason_tags = reason_tags.reindex(date_index, fill_value=[])
            
            def format_reason_tags(x):
                if isinstance(x, list):
                    return ','.join(x)
                elif isinstance(x, str):
                    return x
                else:
                    return ''
            
            result['reason_tags'] = reason_tags.apply(format_reason_tags)
        else:
            result['reason_tags'] = ''
        
        # 添加 Regime 匹配
        if regime_match is not None:
            if not regime_match.index.equals(date_index):
                regime_match = regime_match.reindex(date_index, fill_value=False)
            result['regime_match'] = regime_match
        else:
            result['regime_match'] = False
        
        return result
    
    @staticmethod
    def get_latest_signals(signal_frame: pd.DataFrame, days: int = 1) -> pd.DataFrame:
        """
        獲取最新的信號（用於推薦）
        
        Args:
            signal_frame: DailySignalFrame
            days: 獲取最近幾天（預設1天）
        
        Returns:
            最新的信號 DataFrame
        """
        return signal_frame.tail(days)
    
    @staticmethod
    def parse_reason_tags(reason_tags_str: str) -> List[str]:
        """
        解析理由標籤字符串為列表
        
        Args:
            reason_tags_str: 理由標籤字符串（逗號分隔）
        
        Returns:
            理由標籤列表
        """
        if not reason_tags_str or reason_tags_str == '':
            return []
        return [tag.strip() for tag in reason_tags_str.split(',') if tag.strip()]

