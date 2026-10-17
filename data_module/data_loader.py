from pathlib import Path
from typing import Any, Optional, Dict, List, Union
from datetime import datetime, timedelta, timezone
import pandas as pd
import numpy as np
import requests
import json
import logging
import re
import time
import random
import yfinance as yf

from .config import TWStockConfig
from .db_manager import DBManager
from .market_date_utils import (
    convert_date_format,
    convert_to_datetime,
    convert_roc_date,
    daily_price_file,
    date_range_days,
    default_market_start_date,
    normalize_market_date_range,
    recent_date_range,
    year_to_date_start,
)
from .official_daily_price_custody import (
    persist_official_daily_price_response,
)
from .official_market_daily import fetch_official_market_daily, update_market_index_csv
from .daily_price_source_revision_overlay import load_daily_price_source_revisions
from .price_change_direction import (
    CHANGE_SIGN_COLUMNS,
    TWSE_DIRECTION_PARSER_ID,
    normalize_twse_change_sign,
)


def _is_explicit_twse_no_data_status(status: object) -> bool:
    text = "".join(str(status or "").split()).replace("!", "！")
    return text == "很抱歉，沒有符合條件的資料！"

class MarketDateRange:
    """市場數據日期範圍控制"""
    def __init__(self, start_date: str = None, end_date: str = None):
        self.start_date, self.end_date = normalize_market_date_range(start_date, end_date)
    
    @staticmethod
    def _get_default_start_date() -> str:
        """獲取預設起始日期（前一個月）"""
        return default_market_start_date()
    
    @classmethod
    def last_n_days(cls, n: int) -> 'MarketDateRange':
        """創建最近 n 天的日期範圍"""
        start_date, end_date = recent_date_range(n)
        return cls(start_date=start_date, end_date=end_date)
    
    @classmethod
    def last_month(cls) -> 'MarketDateRange':
        """創建最近一個月的日期範圍"""
        return cls.last_n_days(30)
    
    @classmethod
    def last_quarter(cls) -> 'MarketDateRange':
        """創建最近一季的日期範圍"""
        return cls.last_n_days(90)
    
    @classmethod
    def last_year(cls) -> 'MarketDateRange':
        """創建最近一年的日期範圍"""
        return cls.last_n_days(365)
    
    @classmethod
    def year_to_date(cls) -> 'MarketDateRange':
        """創建今年至今的日期範圍"""
        return cls(start_date=year_to_date_start())
    
    @property
    def date_range_str(self) -> str:
        """返回日期範圍的字符串表示"""
        return f"從 {self.start_date or '最早'} 到 {self.end_date}"
    
    def get_date_list(self) -> List[datetime]:
        """獲取日期範圍內的所有日期"""
        return date_range_days(self.start_date, self.end_date)

class DataLoader:
    """數據加載器，負責從各種來源加載股票數據"""
    
    def __init__(self, config: TWStockConfig):
        self.config = config
        self.last_daily_download_outcome = "failed"
        self.last_daily_download_diagnostics: Dict[str, Any] = {
            "outcome": "failed",
            "reason_code": "not_started",
            "request_attempts": [],
        }
        self._setup_logging()
        self.db = DBManager(self.config)
        
    def _setup_logging(self):
        """設置日誌"""
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        # 避免重複添加處理器，導致 I/O on closed file
        if not self.logger.handlers:
            # 創建控制台處理器
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            
            # 設置格式
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

            try:
                file_handler = logging.FileHandler(
                    self.config.log_dir / "data_loader.log",
                    encoding='utf-8'
                )
            except (OSError, ValueError) as exc:
                self.logger.warning(
                    "無法建立 DataLoader 檔案日誌，改用 console-only: %s",
                    exc,
                )
            else:
                file_handler.setLevel(logging.INFO)
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
    
    def load_daily_price(self, date: str) -> Optional[pd.DataFrame]:
        """加載指定日期的價格數據"""
        try:
            if getattr(self.config, 'use_sqlite', False):
                try:
                    date_str = self._convert_date_format(date)
                    df = self.db.execute_query("SELECT * FROM daily_prices WHERE 日期 = ?;", (date_str,))
                    if not df.empty:
                        self.logger.info(f"成功從 SQLite 加載日期 {date} 的價格數據")
                        return df
                    self.logger.warning(f"SQLite 中找不到日期 {date} 的價格數據，將降級讀取 CSV")
                except Exception as sql_err:
                    self.logger.warning(f"從 SQLite 加載日期 {date} 的價格數據失敗: {sql_err}，將降級讀取 CSV")
                
            file_path = self.config.get_daily_price_file(date)
            if not file_path.exists():
                self.logger.warning(f"找不到日期 {date} 的價格數據文件")
                return None
                
            df = pd.read_csv(file_path)
            self.logger.info(f"成功加載日期 {date} 的價格數據")
            return df
            
        except Exception as e:
            self.logger.error(f"加載日期 {date} 的價格數據時發生錯誤: {str(e)}")
            return None
    
    def load_stock_data(self) -> Optional[pd.DataFrame]:
        """加載股票基本資料"""
        try:
            if not self.config.stock_data_file.exists():
                self.logger.warning("找不到股票基本資料文件")
                return None
                
            df = pd.read_csv(self.config.stock_data_file)
            self.logger.info("成功加載股票基本資料")
            return df
            
        except Exception as e:
            self.logger.error(f"加載股票基本資料時發生錯誤: {str(e)}")
            return None
    
    def load_market_index(self) -> Optional[pd.DataFrame]:
        """加載市場指數數據"""
        try:
            if getattr(self.config, 'use_sqlite', False):
                try:
                    df = self.db.execute_query("SELECT * FROM market_indices ORDER BY 日期 ASC;")
                    if not df.empty:
                        # 將日期格式轉回 YYYY-MM-DD 保持與原 CSV 一致
                        df['日期'] = pd.to_datetime(df['日期'], format='%Y%m%d', errors='coerce').dt.strftime('%Y-%m-%d')
                        last_date = pd.to_datetime(df['日期'].max())
                        self.logger.info(f"成功從 SQLite 加載市場指數數據，最後更新日期: {last_date.strftime('%Y-%m-%d')}")
                        return df
                    self.logger.warning("SQLite 市場指數數據為空，將降級讀取 CSV")
                except Exception as sql_err:
                    self.logger.warning(f"從 SQLite 加載市場指數數據失敗: {sql_err}，將降級讀取 CSV")

            if not self.config.market_index_file.exists():
                self.logger.warning("找不到市場指數數據文件")
                return None
                
            df = pd.read_csv(self.config.market_index_file, encoding='utf-8-sig')
            if not df.empty:
                last_date = pd.to_datetime(df['日期'].max())
                self.logger.info(f"成功加載市場指數數據，最後更新日期: {last_date.strftime('%Y-%m-%d')}")
            else:
                self.logger.warning("市場指數數據文件為空")
            return df
            
        except Exception as e:
            self.logger.error(f"加載市場指數數據時發生錯誤: {str(e)}")
            return None
    
    def load_industry_index(self) -> Optional[pd.DataFrame]:
        """加載產業指數數據"""
        try:
            if getattr(self.config, 'use_sqlite', False):
                try:
                    df = self.db.execute_query("SELECT * FROM industry_indices ORDER BY 日期 ASC;")
                    if not df.empty:
                        df['日期'] = pd.to_datetime(df['日期'], format='%Y%m%d', errors='coerce').dt.strftime('%Y-%m-%d')
                        last_date = pd.to_datetime(df['日期'].max())
                        self.logger.info(f"成功從 SQLite 加載產業指數數據，最後更新日期: {last_date.strftime('%Y-%m-%d')}")
                        return df
                    self.logger.warning("SQLite 產業指數數據為空，將降級讀取 CSV")
                except Exception as sql_err:
                    self.logger.warning(f"從 SQLite 加載產業指數數據失敗: {sql_err}，將降級讀取 CSV")

            if not self.config.industry_index_file.exists():
                self.logger.warning("找不到產業指數數據文件")
                return None
                
            df = pd.read_csv(self.config.industry_index_file, encoding='utf-8-sig')
            if not df.empty:
                last_date = pd.to_datetime(df['日期'].max())
                self.logger.info(f"成功加載產業指數數據，最後更新日期: {last_date.strftime('%Y-%m-%d')}")
            else:
                self.logger.warning("產業指數數據文件為空")
            return df
            
        except Exception as e:
            self.logger.error(f"加載產業指數數據時發生錯誤: {str(e)}")
            return None
    
    def load_all_stocks_data(self) -> Optional[pd.DataFrame]:
        """加載整合性股票數據"""
        try:
            if getattr(self.config, 'use_sqlite', False):
                try:
                    df = self.db.execute_query("SELECT * FROM daily_prices ORDER BY 日期 ASC, 證券代號 ASC;")
                    if not df.empty:
                        self.logger.info("成功從 SQLite 加載整合性股票數據")
                        return df
                    self.logger.warning("SQLite 整合性股票數據為空，將降級讀取 CSV")
                except Exception as sql_err:
                    self.logger.warning(f"從 SQLite 加載整合性股票數據失敗: {sql_err}，將降級讀取 CSV")

            if not self.config.all_stocks_data_file.exists():
                self.logger.warning("找不到整合性股票數據文件")
                return None
                
            df = pd.read_csv(self.config.all_stocks_data_file)
            self.logger.info("成功加載整合性股票數據")
            return df
            
        except Exception as e:
            self.logger.error(f"加載整合性股票數據時發生錯誤: {str(e)}")
            return None
    
    def save_market_index(self, df: pd.DataFrame):
        """保存市場指數數據"""
        try:
            if getattr(self.config, 'use_sqlite', False):
                df_write = df.copy()
                df_write['日期'] = df_write['日期'].apply(lambda x: str(x).replace('-', '').replace('/', ''))
                # 使用 replace 直接覆寫 SQLite table 以保持與原本 to_csv(if_exists='replace') 行為一致
                self.db.write_dataframe('market_indices', df_write, if_exists='replace')
                self.logger.info(f"成功保存市場指數數據到 SQLite，共 {len(df)} 筆記錄")
                return

            # 創建備份
            if self.config.market_index_file.exists():
                backup_file = self.config.backup_dir / f'market_index_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
                self.config.create_backup(self.config.market_index_file, backup_file)
                self.logger.info(f"已創建備份文件: {backup_file}")
            
            # 保存新數據
            df.to_csv(self.config.market_index_file, index=False, encoding='utf-8-sig')
            self.logger.info(f"成功保存市場指數數據到 CSV，共 {len(df)} 筆記錄")
            
        except Exception as e:
            self.logger.error(f"保存市場指數數據時發生錯誤: {str(e)}")
            # 如果有備份，嘗試恢復
            if 'backup_file' in locals() and backup_file.exists() and not getattr(self.config, 'use_sqlite', False):
                self.config.restore_backup(backup_file, self.config.market_index_file)
                self.logger.info("已恢復備份文件")
    
    def save_industry_index(self, data: pd.DataFrame, date: str = None):
        """保存產業指數數據"""
        try:
            if data is None or data.empty:
                self.logger.warning("沒有數據需要保存")
                return
                
            if getattr(self.config, 'use_sqlite', False):
                df_write = data.copy()
                if date:
                    df_write['日期'] = date
                df_write['日期'] = df_write['日期'].apply(lambda x: str(x).replace('-', '').replace('/', ''))
                self.db.write_dataframe('industry_indices', df_write, if_exists='replace')
                self.logger.info("成功保存產業指數數據到 SQLite")
                return

            # 如果指定了日期，添加日期列
            if date:
                data['日期'] = date
                
            # 如果文件已存在，創建備份
            if self.config.industry_index_file.exists():
                self.config.create_backup(self.config.industry_index_file)
                
            # 保存數據
            data.to_csv(self.config.industry_index_file, index=False, encoding='utf-8')
            self.logger.info(f"已保存產業指數數據到: {self.config.industry_index_file}")
            
        except Exception as e:
            self.logger.error(f"保存產業指數數據時發生錯誤: {str(e)}")
    
    def save_all_stocks_data(self, df: pd.DataFrame):
        """保存整合性股票數據"""
        try:
            if getattr(self.config, 'use_sqlite', False):
                df_write = df.copy()
                df_write['日期'] = df_write['日期'].apply(lambda x: str(x).replace('-', '').replace('/', ''))
                self.db.write_dataframe('daily_prices', df_write, if_exists='replace')
                self.logger.info("成功保存整合性股票數據到 SQLite")
                return

            # 創建備份
            self.config.create_backup(self.config.all_stocks_data_file)
            
            # 保存新數據
            df.to_csv(self.config.all_stocks_data_file, index=False)
            self.logger.info("成功保存整合性股票數據到 CSV")
            
        except Exception as e:
            self.logger.error(f"保存整合性股票數據時發生錯誤: {str(e)}")
    
    def download_from_yahoo(self, stock_id: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """從Yahoo Finance下載股票數據"""
        try:
            # 添加.TW後綴
            yahoo_id = f"{stock_id}.TW"
            stock = yf.Ticker(yahoo_id)
            
            # 下載數據
            df = stock.history(start=start_date, end=end_date)
            
            if df.empty:
                self.logger.warning(f"無法從Yahoo Finance下載股票 {stock_id} 的數據")
                return None
                
            self.logger.info(f"成功從Yahoo Finance下載股票 {stock_id} 的數據")
            return df
            
        except Exception as e:
            self.logger.error(f"從Yahoo Finance下載股票 {stock_id} 的數據時發生錯誤: {str(e)}")
            return None
    
    def validate_stock_data(self, df: pd.DataFrame) -> bool:
        """驗證股票數據的完整性和正確性"""
        try:
            # 檢查必要的列是否存在
            required_columns = ['證券代號', '證券名稱']
            if not all(col in df.columns for col in required_columns):
                self.logger.error("數據缺少必要的列")
                return False
                
            # 檢查證券代號格式（只保留4位數的代號）
            if not df['證券代號'].str.len().eq(4).all():
                self.logger.error("存在不正確的證券代號格式")
                return False
                
            return True
            
        except Exception as e:
            self.logger.error(f"驗證數據時發生錯誤: {str(e)}")
            return False

    def download_from_api(self, date: str) -> Optional[pd.DataFrame]:
        """從證交所API下載個股交易資料 - 使用與 notebook 相同的邏輯
        
        API: MI_INDEX (type=ALL)
        - 端點: https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX
        - 參數: date (YYYYMMDD), type=ALL, response=json
        - 數據位置: data['tables'][8] (第9個表格)
        
        Args:
            date: 日期字串，格式為 YYYY-MM-DD
            
        Returns:
            DataFrame 包含個股交易資料，如果下載失敗則返回 None
        """
        try:
            self.last_daily_download_outcome = "failed"
            request_attempts: list[dict[str, Any]] = []
            self.last_daily_download_diagnostics = {
                "date": date,
                "outcome": "failed",
                "reason_code": "in_progress",
                "request_attempts": request_attempts,
            }
            # 轉換日期格式為 YYYYMMDD
            date_obj = datetime.strptime(date, '%Y-%m-%d')
            formatted_date = date_obj.strftime('%Y%m%d')
            
            # 使用 Session 維持 cookie（避免 307 重定向問題）
            session = requests.Session()
            
            # 先訪問主頁獲取 cookie（模擬真實瀏覽器行為）
            try:
                session.get("https://www.twse.com.tw/", timeout=self.config.request_timeout)
                self.logger.debug("已訪問主頁獲取 cookie")
            except Exception as e:
                self.logger.warning(f"訪問主頁時發生錯誤（繼續嘗試）: {str(e)}")
            
            # 添加延遲時間（避免請求過快被限制）
            delay_time = random.uniform(1.5, 2.5)  # 隨機延遲 1.5-2.5 秒
            self.logger.debug(f"等待 {delay_time:.1f} 秒後發送請求...")
            time.sleep(delay_time)
            
            # 構建 API URL - 先使用 type=ALL，失敗時 fallback 到 ALLBUT0999。
            url = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
            
            # 添加請求頭（模擬真實瀏覽器）
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
                'Referer': 'https://www.twse.com.tw/',
                'Connection': 'keep-alive'
            }
            
            data = None
            api_statuses: list[str] = []
            for request_type in ("ALL", "ALLBUT0999"):
                params = {
                    "date": formatted_date,
                    "type": request_type,
                    "response": "json",
                }

                # 發送請求（使用 session 和 headers）
                self.logger.info(f"正在從 MI_INDEX API 獲取 {formatted_date} 的數據，type={request_type}...")
                try:
                    response = session.get(
                        url,
                        params=params,
                        headers=headers,
                        timeout=self.config.request_timeout,
                    )
                except requests.RequestException as request_error:
                    request_attempts.append({
                        "request_type": request_type,
                        "http_status": None,
                        "api_status": None,
                        "error_type": type(request_error).__name__,
                        "error": str(request_error),
                    })
                    self.logger.warning(
                        "MI_INDEX transport error for %s, type=%s: %s",
                        formatted_date,
                        request_type,
                        request_error,
                    )
                    continue

                if response.status_code != 200:
                    request_attempts.append({
                        "request_type": request_type,
                        "http_status": response.status_code,
                        "api_status": None,
                    })
                    self.logger.warning(
                        f"無法獲取 {formatted_date} 的數據: HTTP {response.status_code}, type={request_type}"
                    )
                    if response.status_code == 307:
                        self.logger.warning("遇到 307 重定向，將嘗試備用 type")
                    api_statuses.append("")
                    continue

                # ``requests.Response.content`` reads the complete HTTP body.
                # Keep the completion timestamp immediately after that read so
                # the source receipt can prove when this process actually had
                # the official bytes.  Test doubles that only expose ``json``
                # receive a deterministic serialized fallback; production
                # requests always use the wire bytes.
                response_body = getattr(response, "content", None)
                response_completed_at = datetime.now(timezone.utc)

                # 解析 JSON 響應
                try:
                    candidate = response.json()
                    if not isinstance(candidate, dict):
                        raise TypeError(
                            f"unexpected JSON payload type: {type(candidate).__name__}"
                        )
                except (TypeError, ValueError) as parse_error:
                    request_attempts.append({
                        "request_type": request_type,
                        "http_status": response.status_code,
                        "api_status": None,
                        "error_type": type(parse_error).__name__,
                        "error": str(parse_error),
                    })
                    self.logger.warning(
                        "MI_INDEX JSON error for %s, type=%s: %s",
                        formatted_date,
                        request_type,
                        parse_error,
                    )
                    continue
                if not isinstance(response_body, bytes) or not response_body:
                    response_body = json.dumps(
                        candidate,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                    response_completed_at = datetime.now(timezone.utc)
                if not isinstance(response_body, bytes):
                    raise TypeError("TWSE response body was not captured as bytes")
                captured_raw_response: bytes = response_body
                api_status = str(candidate.get('stat') or "")
                api_statuses.append(api_status)
                request_attempts.append({
                    "request_type": request_type,
                    "http_status": response.status_code,
                    "api_status": api_status,
                })

                # 檢查響應狀態
                if candidate.get('stat') == 'OK':
                    data = candidate
                    break
                self.logger.warning(f"API返回錯誤狀態: {candidate.get('stat')}, type={request_type}")

            if data is None:
                has_official_no_data = any(
                    _is_explicit_twse_no_data_status(status)
                    for status in api_statuses
                )
                attempts_are_safe_no_data = bool(request_attempts) and all(
                    (
                        attempt["http_status"] == 307
                        and attempt["api_status"] is None
                        and "error_type" not in attempt
                    )
                    or (
                        attempt["http_status"] == 200
                        and _is_explicit_twse_no_data_status(attempt["api_status"])
                    )
                    for attempt in request_attempts
                )
                if has_official_no_data and attempts_are_safe_no_data:
                    self.last_daily_download_outcome = "no_data"
                    self.last_daily_download_diagnostics = {
                        "date": date,
                        "outcome": "no_data",
                        "reason_code": "twse_official_no_data",
                        "request_attempts": request_attempts,
                    }
                else:
                    self.last_daily_download_diagnostics = {
                        "date": date,
                        "outcome": "failed",
                        "reason_code": "twse_no_usable_response",
                        "request_attempts": request_attempts,
                    }
                return None
            
            # 檢查是否有資料表
            if 'tables' not in data:
                self.last_daily_download_diagnostics.update(
                    reason_code="twse_tables_missing",
                    request_attempts=request_attempts,
                )
                self.logger.warning("API響應中沒有資料表")
                return None
            
            stock_data = None
            for table in data['tables']:
                fields = table.get('fields') if isinstance(table, dict) else None
                if fields and '證券代號' in fields and '收盤價' in fields:
                    stock_data = table
                    break

            if stock_data is None:
                self.last_daily_download_diagnostics.update(
                    reason_code="twse_stock_table_missing",
                    request_attempts=request_attempts,
                )
                self.logger.warning("API響應中找不到個股交易資料表")
                return None
            
            if not stock_data.get('data'):
                self.last_daily_download_diagnostics.update(
                    reason_code="twse_stock_table_empty",
                    request_attempts=request_attempts,
                )
                self.logger.warning("股票交易資料為空")
                return None
            
            # 轉換為DataFrame（按照 notebook 的方式）
            df = pd.DataFrame(stock_data['data'], columns=stock_data['fields'])
            
            # 只保留4位數股票代號的資料
            df = df[df['證券代號'].str.len() == 4]
            
            # 處理數值欄位
            numeric_columns = ['成交股數', '成交筆數', '成交金額', '開盤價', '最高價', 
                             '最低價', '收盤價', '漲跌價差', '最後揭示買價', 
                             '最後揭示買量', '最後揭示賣價', '最後揭示賣量', '本益比']
            
            for col in numeric_columns:
                if col in df.columns:
                    # 移除逗號並轉換為數值
                    df[col] = df[col].replace({'--': np.nan, '': np.nan})
                    df[col] = df[col].apply(lambda x: str(x).replace(',', '') if pd.notnull(x) else x)
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 以原欄位的明確文字決定方向；非空未知標記不得退成缺值或零。
            for sign_column in CHANGE_SIGN_COLUMNS:
                if sign_column in df.columns:
                    df[sign_column] = df[sign_column].apply(normalize_twse_change_sign)

            source_custody = persist_official_daily_price_response(
                output_root=self.config.output_root,
                venue="twse",
                source_id="twse.mi_index.daily_price",
                source_date=formatted_date,
                requested_url=url,
                final_url=getattr(response, "url", None) or url,
                request_parameters=params,
                http_status=int(response.status_code),
                response_headers=getattr(response, "headers", None),
                raw_response=captured_raw_response,
                captured_at=response_completed_at,
                row_count=len(df),
                source_columns=stock_data.get("fields", []),
                parser_id=TWSE_DIRECTION_PARSER_ID,
                historical_backfill_claimed=False,
            )
            
            # 創建備份
            daily_price_file = self.config.get_daily_price_file(date)
            if daily_price_file.exists():
                backup_file = self.config.backup_dir / f'daily_price_{date}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
                self.config.create_backup(daily_price_file, backup_file)
                self.logger.info(f"已創建備份文件: {backup_file}")
            
            # 保存每日價格數據
            df.to_csv(daily_price_file, index=False, encoding='utf-8-sig')
            self.logger.info(f"成功保存 {date} 的個股交易資料，共 {len(df)} 筆記錄")
            try:
                from data_module.twse_daily_price_publication import (
                    create_download_projection_manifest,
                )

                row_projection_manifest = create_download_projection_manifest(
                    output_root=self.config.output_root,
                    data_root=self.config.data_root,
                    csv_path=daily_price_file,
                    source_date=formatted_date,
                    source_custody=source_custody,
                    source_payload=data,
                    parsed_frame=df,
                )
            except Exception as evidence_error:
                # CSV 是既有主輸出；新證據失敗只代表無法作嚴格 attestation，
                # 不回滾既有下載或讓舊消費者失敗。
                row_projection_manifest = {
                    "status": "unknown",
                    "reason_code": "projection_manifest_failed",
                    "error_type": type(evidence_error).__name__,
                }
            self.last_daily_download_outcome = "success"
            self.last_daily_download_diagnostics = {
                "date": date,
                "outcome": "success",
                "reason_code": "twse_data_available",
                "request_attempts": request_attempts,
                "source_custody": source_custody,
                "row_projection_manifest": row_projection_manifest,
            }
            
            return df
            
        except Exception as e:
            self.last_daily_download_outcome = "failed"
            self.last_daily_download_diagnostics = {
                "date": date,
                "outcome": "failed",
                "reason_code": "twse_download_exception",
                "error": str(e),
                "request_attempts": locals().get("request_attempts", []),
            }
            self.logger.error(f"下載個股交易資料時發生錯誤: {str(e)}")
            import traceback
            traceback.print_exc()
            # 如果有備份，嘗試恢復
            if 'backup_file' in locals() and backup_file.exists():
                self.config.restore_backup(backup_file, daily_price_file)
                self.logger.info("已恢復備份文件")
            return None

    def _convert_date_format(self, date_str: str, to_api: bool = False) -> Optional[str]:
        return convert_date_format(date_str, to_api)

    def _convert_to_datetime(self, date_str: str) -> Optional[datetime]:
        return convert_to_datetime(date_str)

    def get_daily_price_file(self, date: str) -> Path:
        """取得特定日期的價格檔案路徑"""
        return daily_price_file(self.config.daily_price_dir, date)

    def get_latest_date(self, file_path: Path, date_column: str = '日期') -> Optional[str]:
        """獲取指定文件的最新日期"""
        if not file_path.exists():
            return None
            
        try:
            df = pd.read_csv(file_path, encoding='utf-8-sig')
            if df.empty or date_column not in df.columns:
                return None
                
            # 轉換日期格式並獲取最大值
            df[date_column] = pd.to_datetime(df[date_column], format='mixed')
            latest_date = df[date_column].max()
            
            return latest_date.strftime('%Y-%m-%d')
        except Exception as e:
            self.logger.error(f"獲取最新日期時發生錯誤: {str(e)}")
            return None

    def update_daily_data(self, date: str) -> bool:
        """更新個股日成交資料 - 使用 download_from_api 方法（推薦）
        
        此方法會調用 download_from_api 來獲取數據，然後保存到 daily_price 目錄。
        這是主模組推薦的更新方式，使用成功驗證的 MI_INDEX API (type=ALL) 邏輯。
        
        Args:
            date: 日期字串，格式為 YYYY-MM-DD
            
        Returns:
            bool: 更新是否成功
        """
        try:
            self.logger.info(f"正在更新 {date} 的個股日成交資料（使用主模組方法）")
            
            # 使用 download_from_api 方法（已包含 delay time 和 Session 處理）
            df = self.download_from_api(date)
            
            if df is None or df.empty:
                self.logger.error(f"無法獲取 {date} 的個股日成交資料")
                return False
            
            self.logger.info(f"成功更新 {date} 的個股日成交資料，共 {len(df)} 筆記錄")
            return True
            
        except Exception as e:
            self.logger.error(f"更新個股日成交資料時發生錯誤: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def schedule_daily_update(self):
        """設置定時更新任務"""
        import schedule
        import time
        
        def job():
            self.update_daily_data()
        
        # 設置在每個工作日下午 2 點執行更新（台股收盤後）
        schedule.every().monday.at("14:00").do(job)
        schedule.every().tuesday.at("14:00").do(job)
        schedule.every().wednesday.at("14:00").do(job)
        schedule.every().thursday.at("14:00").do(job)
        schedule.every().friday.at("14:00").do(job)
        
        while True:
            schedule.run_pending()
            time.sleep(60)
    
    def merge_daily_data(self) -> Optional[pd.DataFrame]:
        """合併每日交易數據"""
        backup_file: Optional[Path] = None
        try:
            daily_price_dir = self.config.daily_price_dir
            configured_database_path = getattr(self.config, 'db_file', None)
            database_path = (
                Path(configured_database_path)
                if configured_database_path is not None
                else Path(daily_price_dir).parent / 'sqlite' / 'twstock.db'
            )
            # 在建立備份或輸出前驗證 receipt／plan，避免錯誤證據發布 derived CSV。
            source_revisions = load_daily_price_source_revisions(database_path)
            revision_changes = 0
            excluded_rows_removed = 0
            if not daily_price_dir.exists() and not self.config.all_stocks_data_file.exists():
                self.logger.error(f"找不到目錄：{daily_price_dir}")
                return None
            
            # 檢查現有的合併文件
            last_date = None
            if self.config.all_stocks_data_file.exists():
                # 讀取現有數據
                existing_df = pd.read_csv(self.config.all_stocks_data_file, encoding='utf-8-sig', low_memory=False)
                last_date = str(existing_df['日期'].max())
                self.logger.info(f"已讀取現有數據，最後更新日期為: {last_date}")
            
            # 獲取所有CSV文件
            all_csv_files = list(daily_price_dir.glob("*.csv")) if daily_price_dir.exists() else []
            if not all_csv_files:
                if not last_date:
                    self.logger.error(f"在 {daily_price_dir} 中找不到CSV文件")
                    return None
            
            # 如果有最後更新日期，只處理新的文件
            if last_date:
                csv_files = [f for f in all_csv_files if str(f.stem) > last_date]
                if not csv_files:
                    if source_revisions.has_revision_evidence:
                        existing_df, changed_cells, removed_rows = source_revisions.apply(existing_df)
                        revision_changes += changed_cells
                        excluded_rows_removed += removed_rows
                        if changed_cells or removed_rows:
                            self.logger.info(
                                "沒有新 raw 檔，已套用核驗來源修訂至既有整合檔（欄位值 %s、排除列 %s）",
                                changed_cells,
                                removed_rows,
                            )
                    if revision_changes == 0 and excluded_rows_removed == 0:
                        self.logger.info("沒有新的數據需要更新")
                        return existing_df
                self.logger.info(f"找到 {len(csv_files)} 個需要處理的新CSV文件")
            else:
                csv_files = all_csv_files
                self.logger.info(f"找到 {len(csv_files)} 個CSV文件")
            
            # 讀取並合併所有文件
            all_data = []
            if last_date:
                all_data.append(existing_df)
                
            for file in csv_files:
                try:
                    # 從文件名獲取日期
                    date = file.stem
                    
                    # 讀取CSV文件
                    df = pd.read_csv(file, encoding='utf-8-sig')
                    
                    # 添加日期列
                    df['日期'] = date
                    
                    # 確保證券代號是4位數的字符串
                    df['證券代號'] = df['證券代號'].astype(str).str.zfill(4)
                    
                    all_data.append(df)
                    self.logger.info(f"成功讀取 {file.name}")
                    
                except Exception as e:
                    self.logger.error(f"處理文件 {file.name} 時出錯: {str(e)}")
                    continue
            
            if not all_data:
                raise ValueError("沒有成功讀取任何數據")
            
            # 合併所有數據
            merged_data = pd.concat(all_data, ignore_index=True)
            merged_data['日期'] = merged_data['日期'].astype(str)
            
            # 重新排序列，把日期放在前面
            columns = ['日期', '證券代號', '證券名稱', '成交股數', '成交筆數', '成交金額', 
                      '開盤價', '最高價', '最低價', '收盤價', '漲跌(+/-)', '漲跌價差', 
                      '最後揭示買價', '最後揭示買量', '最後揭示賣價', '最後揭示賣量', '本益比']
            merged_data = merged_data[columns]
            
            # 按日期和證券代號排序
            merged_data = merged_data.sort_values(['日期', '證券代號'])
            
            # 移除重複數據
            merged_data = merged_data.drop_duplicates(subset=['日期', '證券代號'], keep='last')
            merged_data, changed_cells, removed_rows = source_revisions.apply(merged_data)
            revision_changes += changed_cells
            excluded_rows_removed += removed_rows
            if changed_cells or removed_rows:
                self.logger.info(
                    "已套用核驗來源修訂至每日整合檔（欄位值 %s、排除列 %s）",
                    changed_cells,
                    removed_rows,
                )
            merged_data = merged_data.sort_values(['日期', '證券代號'])
            
            # 保存合併後的數據
            if self.config.all_stocks_data_file.exists():
                backup_file = self.config.backup_dir / f'stock_data_whole_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
                self.config.create_backup(self.config.all_stocks_data_file, backup_file)
                self.logger.info(f"已創建備份文件: {backup_file}")
            merged_data.to_csv(self.config.all_stocks_data_file, index=False, encoding='utf-8-sig')
            self.logger.info(f"成功保存合併後的數據到 {self.config.all_stocks_data_file}")
            
            # 顯示數據統計
            self.logger.info(f"合併後的數據形狀: {merged_data.shape}")
            self.logger.info(f"日期範圍: {merged_data['日期'].min()} 到 {merged_data['日期'].max()}")
            self.logger.info(f"總共包含 {merged_data['證券代號'].nunique()} 個不同的證券代號")
            
            return merged_data
            
        except Exception as e:
            self.logger.error(f"合併每日交易數據時發生錯誤: {str(e)}", exc_info=True)
            # 如果有備份，嘗試恢復
            if backup_file is not None and backup_file.exists():
                self.config.restore_backup(backup_file, self.config.all_stocks_data_file)
                self.logger.info("已恢復備份文件")
            return None

    def update_industry_index(
        self,
        date: str,
        skip_backup: bool = False,
        *,
        capture_manifests: Optional[List[Path]] = None,
    ) -> bool:
        """Capture and atomically project one TWSE industry-index response."""
        from .twse_industry_index_capture import (
            TwseIndustryIndexCaptureError,
            assess_industry_name_completeness,
            atomic_write_csv_projection,
            parse_twse_industry_rows,
            persist_twse_industry_capture,
        )

        try:
            self.logger.info("正在更新 %s 的 TWSE 產業指數資料", date)
            requested_date = datetime.strptime(date, "%Y-%m-%d").date()
            normalized_date = requested_date.isoformat()
            formatted_date = requested_date.strftime("%Y%m%d")
            url = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
            params = {"date": formatted_date, "type": "IND", "response": "json"}
            response = self._make_request(url, params)
            if response is None:
                self.logger.error("無法取得 %s 的 TWSE 產業指數 response", normalized_date)
                return False

            # Accessing .content completes the body read before this local UTC clock is captured.
            raw_response = response.content
            captured_at = datetime.now(timezone.utc)
            if not isinstance(raw_response, bytes) or not raw_response:
                self.logger.error("TWSE response body 為空或不是 bytes：%s", normalized_date)
                return False

            status_code = int(getattr(response, "status_code", 200))
            rows: list[dict[str, str | None]] = []
            parse_status = "accepted"
            parse_reason: str | None = None
            response_date_status = "verified"
            completeness_status = "degraded"
            completeness_reason: str | None = "parse_not_completed"
            selected_titles: list[str] = []
            try:
                payload = json.loads(raw_response.decode("utf-8-sig"))
                if status_code != 200:
                    raise TwseIndustryIndexCaptureError(f"HTTP status {status_code}")
                rows = parse_twse_industry_rows(payload, normalized_date)
                if isinstance(payload, dict) and isinstance(payload.get("tables"), list):
                    selected_titles = sorted({
                        str(table.get("title", ""))
                        for table in payload["tables"]
                        if isinstance(table, dict)
                        and any(
                            token in str(table.get("title", ""))
                            for token in ("價格指數", "報酬指數", "類股指數")
                        )
                    })
                completeness_status, completeness_reason = assess_industry_name_completeness(
                    self.config.industry_index_file,
                    normalized_date,
                    rows,
                )
            except (UnicodeError, json.JSONDecodeError, TwseIndustryIndexCaptureError) as exc:
                parse_status = "rejected"
                parse_reason = str(exc)
                if "日期證據" in parse_reason:
                    response_date_status = "date_unverified"
                elif "日期與請求日期不一致" in parse_reason:
                    response_date_status = "mismatch"
                else:
                    response_date_status = "not_checked"

            capture = persist_twse_industry_capture(
                output_root=self.config.output_root,
                source_date=normalized_date,
                requested_url=url,
                final_url=getattr(response, "url", None),
                request_parameters=params,
                http_status=status_code,
                response_headers=getattr(response, "headers", None),
                raw_response=raw_response,
                captured_at=captured_at,
                parse_status=parse_status,
                parse_reason=parse_reason,
                response_date_status=response_date_status,
                completeness_status=completeness_status,
                completeness_reason=completeness_reason,
                selected_table_titles=selected_titles,
                rows=rows,
            )
            if parse_status != "accepted":
                self.logger.error("TWSE 產業 response 已留存，但解析失敗：%s", parse_reason)
                return False
            if completeness_status != "accepted":
                self.logger.warning(
                    "TWSE 產業 response 已留存為 degraded，等待人工確認：%s (%s)",
                    normalized_date,
                    completeness_reason,
                )
                return False

            _, csv_digest = atomic_write_csv_projection(
                self.config.industry_index_file,
                normalized_date,
                rows,
                skip_backup=skip_backup,
                config=self.config,
            )
            if capture_manifests is not None:
                capture_manifests.append(Path(str(capture["path"])))
            self.logger.info(
                "已原子更新 %s TWSE 產業六欄投影（rows=%s, csv_sha256=%s）",
                normalized_date,
                len(rows),
                csv_digest,
            )
            return True
        except Exception as exc:
            self.logger.error("更新 TWSE 產業指數失敗並保留可還原狀態：%s", exc, exc_info=True)
            return False

    def update_market_index(
        self,
        date: str,
        skip_backup: bool = False,
        *,
        capture_manifests: Optional[List[Path]] = None,
    ) -> bool:
        """以 TWSE 月報更新指定日大盤資料；任一來源缺件即拒絕發布。"""
        try:
            requested_date = datetime.strptime(date, "%Y-%m-%d").date()
            pending_captures: list[Path] = []
            rows = fetch_official_market_daily(
                requested_date,
                requested_date,
                requester=lambda url, params: self._make_request(url, dict(params)),
                source_dir=self.config.meta_data_dir,
                capture_manifests=pending_captures,
            )
            if len(rows) != 1 or rows[0]["日期"] != requested_date.isoformat():
                self.logger.error("TWSE 官方月報沒有指定交易日 %s，拒絕更新", date)
                return False
            if not update_market_index_csv(
                self.config, rows, skip_backup=skip_backup,
            ):
                self.logger.error("大盤 CSV 更新未完成（鎖定、備份或原子寫入失敗）")
                return False
            if capture_manifests is not None:
                capture_manifests.extend(pending_captures)
            self.logger.info("已使用 TWSE 官方來源更新 %s 大盤資料", date)
            return True
        except Exception as exc:
            self.logger.error("官方大盤資料更新失敗：%s", exc)
            return False

    def _make_request(self, url: str, params: Dict = None, retries: int = None) -> Optional[requests.Response]:
        """發送HTTP請求並處理重試邏輯（使用 Session 與高模擬防爬蟲 Headers）"""
        retries = retries or self.config.max_retries
        for attempt in range(retries):
            try:
                session = requests.Session()
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Referer': 'https://www.twse.com.tw/',
                    'Connection': 'keep-alive'
                }
                
                # 先訪問主頁獲取 cookie（模擬真實瀏覽器）
                try:
                    session.get("https://www.twse.com.tw/", headers=headers, timeout=self.config.request_timeout)
                except Exception as e:
                    self.logger.debug(f"訪問首頁獲取 cookie 失敗: {str(e)}")
                
                # 隨機延遲 1.5 - 2.5 秒，防範被拉黑
                time.sleep(random.uniform(1.5, 2.5))
                
                response = session.get(
                    url, 
                    params=params, 
                    headers=headers,
                    timeout=self.config.request_timeout
                )
                
                if response.status_code == 200:
                    return response
                elif response.status_code == 429:  # Too Many Requests
                    time.sleep(self.config.retry_delay * (attempt + 1))
                    continue
                else:
                    self.logger.warning(f"請求失敗 (HTTP {response.status_code}): {url}")
                    if attempt < retries - 1:
                        time.sleep(self.config.retry_delay)
                        continue
                    return None
            except requests.RequestException as e:
                if attempt < retries - 1:
                    time.sleep(self.config.retry_delay)
                    continue
                self.logger.error(f"請求異常: {str(e)}")
                return None
        return None

    def _convert_roc_date(self, date_str: str) -> str:
        return convert_roc_date(date_str)
