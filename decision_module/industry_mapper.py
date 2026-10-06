"""
產業映射模組
處理 companies.csv 和 industry_index.csv 的關聯
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from decision_module.market_frame_contracts import normalize_market_dates

class IndustryMapper:
    """產業映射器"""
    
    def __init__(
        self,
        config,
        industry_index_provider: Optional[Callable[[], Optional[pd.DataFrame]]] = None,
        *,
        companies_provider: Optional[Callable[[], Optional[pd.DataFrame]]] = None,
    ):
        """初始化產業映射器；資料讀取由 application 明確注入。
        
        Args:
            config: TWStockConfig 實例
            companies_provider: 讀取 companies frame 的明確 provider。
            industry_index_provider: 讀取產業指數 frame 的明確 provider。
        """
        if companies_provider is None or industry_index_provider is None:
            missing = []
            if companies_provider is None:
                missing.append("companies_provider")
            if industry_index_provider is None:
                missing.append("industry_index_provider")
            raise ValueError(
                "IndustryMapper requires explicit "
                + " and ".join(missing)
                + "; use app_module.decision_service_composition.build_industry_mapper"
            )
        if not callable(companies_provider) or not callable(industry_index_provider):
            raise TypeError("IndustryMapper data providers must be callable")

        self.config = config
        self.companies_provider = companies_provider
        self.industry_index_provider = industry_index_provider
        self.companies_df = None
        self.industry_index_df = None
        self.stock_to_industries: Dict[str, List[str]] = {}
        self.industry_normalization: Dict[str, str] = {}
        self._latest_industry_performance_by_index_name: Dict[str, Any] = {}
        self._industry_performance_cache: Dict[str, Any] = {}
        
        # 載入數據
        self._load_companies()
        self._load_industry_index()
        self._build_mappings()
        self._build_latest_industry_performance_cache()
    
    def _load_companies(self):
        """消費 application 注入的公司資料，不執行檔案 I/O。"""
        assert self.companies_provider is not None
        frame = self.companies_provider()
        self.companies_df = None if frame is None else frame.copy()
    
    def _load_industry_index(self):
        """消費 application 注入的產業指數，不執行 DB／檔案 I/O。"""
        assert self.industry_index_provider is not None
        frame = self.industry_index_provider()
        if frame is not None:
            self.industry_index_df = frame.copy()
            if '日期' in self.industry_index_df.columns:
                self.industry_index_df['日期'] = normalize_market_dates(
                    self.industry_index_df['日期']
                )
        else:
            self.industry_index_df = None
    
    def _build_mappings(self):
        """建立股票到產業的映射關係"""
        if self.companies_df is None:
            return
        
        # 建立股票代號 -> 產業類別列表的映射
        for _, row in self.companies_df.iterrows():
            stock_id = str(row['stock_id']).strip()
            industry = str(row['industry_category']).strip()
            
            if stock_id not in self.stock_to_industries:
                self.stock_to_industries[stock_id] = []
            
            if industry not in self.stock_to_industries[stock_id]:
                self.stock_to_industries[stock_id].append(industry)
        
        # 建立產業類別標準化映射
        # companies.csv 中的產業類別 -> industry_index.csv 中的指數名稱
        industry_index_df = self.industry_index_df
        if (
            industry_index_df is None
            or industry_index_df.empty
            or '指數名稱' not in industry_index_df.columns
        ):
            # 缺少產業指數資料時仍保留 companies.csv 的股票產業分類；
            # 不從缺欄或空表推造指數名稱。
            return

        index_names = set(industry_index_df['指數名稱'].unique())

        # 提取產業類別（去除「類指數」、「類報酬指數」等後綴）
        for index_name in index_names:
            if pd.notna(index_name):
                # 去除後綴
                normalized = str(index_name).replace('類指數', '').replace('類報酬指數', '').replace('類', '')
                self.industry_normalization[normalized] = index_name

    def _build_latest_industry_performance_cache(self):
        """預先快取每個產業指數最新表現，避免個股篩選時逐檔掃 DataFrame。"""
        self._latest_industry_performance_by_index_name = {}
        self._industry_performance_cache = {}

        if self.industry_index_df is None or '指數名稱' not in self.industry_index_df.columns:
            return

        df = self.industry_index_df.dropna(subset=['指數名稱']).copy()
        if len(df) == 0:
            return

        if '日期' in df.columns:
            df = df.sort_values('日期')

        latest_rows = df.groupby('指數名稱', sort=False).tail(1)
        for _, latest in latest_rows.iterrows():
            index_name = str(latest['指數名稱'])
            self._latest_industry_performance_by_index_name[index_name] = self._row_to_performance(latest)

    @staticmethod
    def _row_to_performance(row) -> Dict:
        return {
            '指數名稱': row['指數名稱'],
            '收盤指數': row.get('收盤指數', 0),
            '漲跌': row.get('漲跌', ''),
            '漲跌點數': row.get('漲跌點數', 0),
            '漲跌百分比': row.get('漲跌百分比', 0),
            '日期': row.get('日期')
        }
    
    def get_stock_industries(self, stock_id: str) -> List[str]:
        """獲取股票所屬的產業類別列表
        
        Args:
            stock_id: 股票代號
            
        Returns:
            List[str]: 產業類別列表
        """
        stock_id = str(stock_id).strip()
        return self.stock_to_industries.get(stock_id, [])
    
    def get_industry_index_name(self, industry_category: str) -> Optional[str]:
        """獲取產業類別對應的指數名稱
        
        Args:
            industry_category: 產業類別（來自 companies.csv）
            
        Returns:
            str: 指數名稱（來自 industry_index.csv），如果找不到則返回 None
        """
        # 直接匹配
        if industry_category in self.industry_normalization:
            return self.industry_normalization[industry_category]
        
        # 嘗試部分匹配
        for normalized, index_name in self.industry_normalization.items():
            if normalized in industry_category or industry_category in normalized:
                return index_name
        
        # 特殊映射規則
        mapping_rules = {
            '半導體業': '半導體',
            '光電業': '光電',
            '電子工業': '電子零組件',  # 可能需要調整
            '生技醫療業': '生技醫療',
            '化學生技醫療': '化學生技醫療',
            '電機機械': '電機機械',
            '建材營造': '建材營造',
            '金融保險': '金融保險',
            '紡織纖維': '紡織纖維',
            '觀光餐旅': '觀光',
            '貿易百貨': '貿易百貨',
        }
        
        if industry_category in mapping_rules:
            normalized = mapping_rules[industry_category]
            return self.industry_normalization.get(normalized)
        
        return None
    
    def get_industry_performance(self, industry_category: str, date: str = None) -> Optional[Dict]:
        """獲取產業指數表現
        
        Args:
            industry_category: 產業類別
            date: 日期（YYYY-MM-DD），如果為None則使用最新日期
            
        Returns:
            Dict: 包含收盤指數、漲跌、漲跌百分比等信息，如果找不到則返回 None
        """
        if self.industry_index_df is None:
            return None

        cache_key: Tuple[str, Optional[str]] = (str(industry_category), date)
        if cache_key in self._industry_performance_cache:
            cached = self._industry_performance_cache[cache_key]
            return dict(cached) if cached is not None else None
        
        # 獲取對應的指數名稱
        index_name = self.get_industry_index_name(industry_category)
        if index_name is None:
            self._industry_performance_cache[cache_key] = None
            return None

        if date is None and index_name in self._latest_industry_performance_by_index_name:
            performance = dict(self._latest_industry_performance_by_index_name[index_name])
            self._industry_performance_cache[cache_key] = performance
            return dict(performance)
        
        # 篩選數據
        df = self.industry_index_df[
            self.industry_index_df['指數名稱'] == index_name
        ].copy()
        
        if len(df) == 0:
            self._industry_performance_cache[cache_key] = None
            return None
        
        # 如果指定日期，篩選該日期；否則使用最新日期
        if date:
            target_date = pd.to_datetime(date)
            df = df[df['日期'] <= target_date]
        
        if len(df) == 0:
            self._industry_performance_cache[cache_key] = None
            return None
        
        # 獲取最新一筆
        latest = df.iloc[-1]
        performance = self._row_to_performance(latest)
        self._industry_performance_cache[cache_key] = performance
        return dict(performance)
    
    def get_all_industries(self) -> List[str]:
        """獲取所有產業類別列表
        
        Returns:
            List[str]: 產業類別列表
        """
        if self.companies_df is None:
            return []
        
        industries = sorted(self.companies_df['industry_category'].unique())
        # 過濾掉 NaN
        industries = [ind for ind in industries if pd.notna(ind)]
        return industries
    
    def filter_stocks_by_industry(self, stock_ids: List[str], industry_category: str) -> List[str]:
        """根據產業類別篩選股票
        
        Args:
            stock_ids: 股票代號列表
            industry_category: 產業類別
            
        Returns:
            List[str]: 符合條件的股票代號列表
        """
        result = []
        # 標準化產業名稱（去除「業」後綴，統一格式）
        normalized_filter = self._normalize_industry_name(industry_category)
        
        for stock_id in stock_ids:
            industries = self.get_stock_industries(stock_id)
            # 嘗試精確匹配
            if industry_category in industries:
                result.append(stock_id)
                continue
            
            # 嘗試標準化匹配
            for stock_industry in industries:
                normalized_stock = self._normalize_industry_name(stock_industry)
                if normalized_filter == normalized_stock:
                    result.append(stock_id)
                    break
                
                # 嘗試部分匹配（例如「半導體業」匹配「半導體」）
                if normalized_filter in normalized_stock or normalized_stock in normalized_filter:
                    result.append(stock_id)
                    break
        return result
    
    def _normalize_industry_name(self, industry_name: str) -> str:
        """標準化產業名稱（去除後綴，統一格式）
        
        Args:
            industry_name: 原始產業名稱
            
        Returns:
            str: 標準化後的產業名稱
        """
        if not industry_name or pd.isna(industry_name):
            return ""
        
        normalized = str(industry_name).strip()
        # 去除常見後綴
        suffixes = ['業', '類', '類指數', '類報酬指數']
        for suffix in suffixes:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)]
        
        return normalized
    
    def get_stocks_in_industry(self, industry_category: str) -> pd.DataFrame:
        """獲取屬於指定產業的所有股票
        
        Args:
            industry_category: 產業類別
            
        Returns:
            DataFrame: 股票列表，包含 stock_id, stock_name, type
        """
        if self.companies_df is None:
            return pd.DataFrame()
        
        df = self.companies_df[
            self.companies_df['industry_category'] == industry_category
        ].copy()
        
        # 去重（因為有些股票可能屬於多個產業）
        df = df[['stock_id', 'stock_name', 'type']].drop_duplicates(subset=['stock_id'])
        
        return df

__all__ = ['IndustryMapper']
