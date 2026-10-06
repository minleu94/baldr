import pandas as pd
import numpy as np
import talib
import logging
import traceback
from pathlib import Path
import os
import sys
from collections.abc import Callable, Mapping

from analysis_module.technical_analysis.technical_column_support import (
    resolve_technical_column,
)
from analysis_module.technical_analysis.technical_date_support import (
    safe_convert_technical_dates,
)
from analysis_module.technical_analysis.indicator_kernels import clean_price_values


CAUSAL_INDICATOR_COLUMNS = (
    "SMA30",
    "DEMA30",
    "EMA30",
    "MA5",
    "MA10",
    "MA20",
    "MA60",
    "RSI",
    "MACD",
    "MACD_signal",
    "MACD_hist",
    "slowk",
    "slowd",
    "middleband",
    "upperband",
    "lowerband",
    "SAR",
    "TSF",
    "ATR",
    "ADX",
)

_CAUSAL_OHLC_COLUMNS = {
    "Open": ("開盤價", "Open", "open"),
    "High": ("最高價", "High", "high"),
    "Low": ("最低價", "Low", "low"),
    "Close": ("收盤價", "Close", "close"),
}

_CAUSAL_DATE_COLUMNS = ("日期", "Date", "date", "trade_date", "trading_date")
_CAUSAL_STOCK_COLUMNS = ("證券代號", "股票代號", "stock_id", "stock_code", "symbol")


def _segmented_calculation(
    inputs: Mapping[str, np.ndarray],
    calculate: Callable[[Mapping[str, np.ndarray]], Mapping[str, np.ndarray]],
) -> dict[str, np.ndarray]:
    """讓一般 indicator API 在每段連續有效輸入上重算暖機期。"""
    length = len(next(iter(inputs.values()))) if inputs else 0
    output: dict[str, np.ndarray] = {}
    if not inputs:
        return output
    valid = np.logical_and.reduce([np.isfinite(values) for values in inputs.values()])
    index = 0
    while index < length:
        if not valid[index]:
            index += 1
            continue
        end = index + 1
        while end < length and valid[end]:
            end += 1
        segment_inputs = {
            name: np.ascontiguousarray(values[index:end], dtype=np.float64)
            for name, values in inputs.items()
        }
        segment_output = calculate(segment_inputs)
        for name, values in segment_output.items():
            values = np.asarray(values, dtype=np.float64)
            if values.shape != (end - index,):
                raise ValueError(f"指標 {name} 回傳長度與輸入不符")
            if name not in output:
                output[name] = np.full(length, np.nan, dtype=np.float64)
            output[name][index:end] = values
        index = end
    return output


def calculate_causal_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """依完整、按日期排序的 OHLC prefix 計算既有 20 個技術指標。

    函式只複製輸入並在記憶體計算；它不建立設定、logger 或檔案，也不
    填補原始 OHLC。任一 OHLC 欄缺值或非有限值時，該列指標保留 NaN，
    後續連續有效區段重新暖機。呼叫端必須先提供完整歷史 prefix，並在
    計算完成後才裁切要發布的日期範圍。
    """
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame 必須是 pandas DataFrame")

    source_columns = {
        canonical: next(
            (candidate for candidate in candidates if candidate in frame.columns),
            None,
        )
        for canonical, candidates in _CAUSAL_OHLC_COLUMNS.items()
    }
    missing_columns = [name for name, source in source_columns.items() if source is None]
    if missing_columns:
        raise ValueError(f"缺少 OHLC 欄位：{', '.join(missing_columns)}")

    for stock_column in _CAUSAL_STOCK_COLUMNS:
        if stock_column in frame.columns and frame[stock_column].nunique(dropna=True) > 1:
            raise ValueError("技術指標計算 frame 只能包含單一股票")

    date_column = next(
        (candidate for candidate in _CAUSAL_DATE_COLUMNS if candidate in frame.columns),
        None,
    )
    if date_column is not None:
        normalized_dates = safe_convert_technical_dates(frame[date_column])
        if normalized_dates.isna().any():
            raise ValueError("技術指標計算 frame 含無效日期")
        date_values = normalized_dates.to_list()
        if date_values != sorted(date_values):
            raise ValueError("技術指標計算 frame 必須依日期遞增排序")
        if len(set(date_values)) != len(date_values):
            raise ValueError("技術指標計算 frame 不得含重複日期")

    result = frame.copy()
    numeric = {}
    for canonical, source in source_columns.items():
        if source is None:
            continue
        numeric[canonical] = clean_price_values(frame[source])
    for values in numeric.values():
        values[~np.isfinite(values)] = np.nan

    complete_rows = np.logical_and.reduce(
        [np.isfinite(numeric[name]) for name in ("Open", "High", "Low", "Close")]
    )
    if complete_rows.any():
        prices = np.column_stack(
            [numeric[name][complete_rows] for name in ("Open", "High", "Low", "Close")]
        )
        open_values, high_values, low_values, close_values = prices.T
        invalid_prices = (
            (prices <= 0).any(axis=1)
            | (low_values > np.minimum(open_values, close_values))
            | (high_values < np.maximum(open_values, close_values))
        )
        if invalid_prices.any():
            raise ValueError("OHLC 含非正價格或高低價區間不包含開收盤價")

    length = len(frame)
    output = {
        column: np.full(length, np.nan, dtype=np.float64)
        for column in CAUSAL_INDICATOR_COLUMNS
    }
    valid_ohlc = complete_rows

    def compute_segment(start: int, end: int) -> None:
        """只把連續有效 OHLC 區段交給 TA-Lib，並保留原始暖機 NaN。"""
        close = np.ascontiguousarray(numeric["Close"][start:end], dtype=np.float64)
        high = np.ascontiguousarray(numeric["High"][start:end], dtype=np.float64)
        low = np.ascontiguousarray(numeric["Low"][start:end], dtype=np.float64)
        segment_values: dict[str, np.ndarray] = {
            "SMA30": talib.SMA(close, timeperiod=30),
            "DEMA30": talib.DEMA(close, timeperiod=30),
            "EMA30": talib.EMA(close, timeperiod=30),
            "MA5": talib.SMA(close, timeperiod=5),
            "MA10": talib.SMA(close, timeperiod=10),
            "MA20": talib.SMA(close, timeperiod=20),
            "MA60": talib.SMA(close, timeperiod=60),
            "RSI": talib.RSI(close, timeperiod=14),
            "MACD": np.asarray([], dtype=np.float64),
            "MACD_signal": np.asarray([], dtype=np.float64),
            "MACD_hist": np.asarray([], dtype=np.float64),
            "slowk": np.asarray([], dtype=np.float64),
            "slowd": np.asarray([], dtype=np.float64),
            "middleband": np.asarray([], dtype=np.float64),
            "upperband": np.asarray([], dtype=np.float64),
            "lowerband": np.asarray([], dtype=np.float64),
            "SAR": talib.SAR(high, low, acceleration=0.02, maximum=0.2),
            "TSF": talib.TSF(close, timeperiod=14),
            "ATR": talib.ATR(high, low, close, timeperiod=14),
            "ADX": talib.ADX(high, low, close, timeperiod=14),
        }
        macd, macd_signal, macd_hist = talib.MACD(
            close, fastperiod=12, slowperiod=26, signalperiod=9
        )
        segment_values["MACD"] = macd
        segment_values["MACD_signal"] = macd_signal
        segment_values["MACD_hist"] = macd_hist
        slowk, slowd = talib.STOCH(
            high,
            low,
            close,
            fastk_period=5,
            slowk_period=3,
            slowk_matype=talib.MA_Type.SMA,
            slowd_period=3,
            slowd_matype=talib.MA_Type.SMA,
        )
        segment_values["slowk"] = slowk
        segment_values["slowd"] = slowd
        upper, middle, lower = talib.BBANDS(
            close, timeperiod=30, nbdevup=2.0, nbdevdn=2.0, matype=talib.MA_Type.SMA
        )
        segment_values["middleband"] = middle
        segment_values["upperband"] = upper
        segment_values["lowerband"] = lower
        for column in ("RSI", "slowk", "slowd"):
            segment_values[column] = np.clip(segment_values[column], 0.0, 100.0)
        for column, values in segment_values.items():
            output[column][start:end] = values

    index = 0
    while index < length:
        if not valid_ohlc[index]:
            index += 1
            continue
        end = index + 1
        while end < length and valid_ohlc[end]:
            end += 1
        compute_segment(index, end)
        index = end

    for column in CAUSAL_INDICATOR_COLUMNS:
        result[column] = output[column]
    return result

class TechnicalIndicatorCalculator:
    """技術指標計算類別，基於02_technical_calculator.md中的功能"""
    
    def __init__(self, logger=None):
        """初始化技術指標計算器
        
        Args:
            logger: 日誌記錄器，如果為None則創建新的記錄器
        """
        self.logger = logger or self._setup_logging()
        
        # 定義列名映射，將中文列名映射到英文列名
        self.column_mapping = {
            # 中文列名 -> 英文列名
            '收盤價': 'Close',
            '開盤價': 'Open',
            '最高價': 'High',
            '最低價': 'Low',
            '成交量': 'Volume',
            '成交股數': 'Volume'
        }
        # 反向映射，將英文列名映射到中文列名
        self.reverse_mapping = {v: k for k, v in self.column_mapping.items()}
    
    def _safe_convert_date(self, series):
        """安全地將日期序列轉換為 YYYY-MM-DD 格式的字串，防範 int64/float64 被誤判為 UNIX 奈秒 1970-01-01"""
        return safe_convert_technical_dates(series)
    
    def _setup_logging(self):
        """設置日誌記錄"""
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)
        
        # 清除現有的處理器
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # 控制台處理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter('%(levelname)s: %(message)s')
        )
        console_handler.setLevel(logging.WARNING)
        logger.addHandler(console_handler)

        try:
            log_path = Path('technical_calculation.log')
            if getattr(sys, 'frozen', False):
                output_root = os.environ.get('OUTPUT_ROOT')
                if not output_root:
                    output_root = str(Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'baldr' / 'output')
                log_path = Path(output_root) / 'application_state' / 'logs' / 'technical_calculation.log'
                log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(
                log_path,
                encoding='utf-8',
            )
        except (OSError, ValueError) as exc:
            logger.warning(
                "無法建立 TechnicalIndicator 檔案日誌，改用 console-only: %s",
                exc,
            )
        else:
            file_handler.setFormatter(
                logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            )
            logger.addHandler(file_handler)
        return logger
    
    def _get_column_name(self, df, eng_name):
        """獲取對應的列名，優先使用中文列名，如果不存在則使用英文列名
        
        Args:
            df: 數據DataFrame
            eng_name: 英文列名
            
        Returns:
            str: 對應的列名
        """
        return resolve_technical_column(df.columns, self.reverse_mapping, eng_name)
    
    def process_price_data(self, df):
        """處理價格數據，包含資料清理和格式轉換
        
        Args:
            df: 原始價格數據DataFrame
            
        Returns:
            DataFrame: 處理後的價格數據
        """
        try:
            # 複製DataFrame避免修改原始資料
            df = df.copy()
            # 處理漲跌符號欄位中的 HTML 標籤
            if '漲跌(+/-)' in df.columns:
                replace_dict = {
                    '<p style= color:red>+</p>': '+',
                    '<p style= color:green>-</p>': '-',
                    '<p style =color:red>+</p>': '+',
                    '<p style =color:green>-</p>': '-'
                }
                df['漲跌(+/-)'] = df['漲跌(+/-)'].map(lambda x: replace_dict.get(x, x))
            
            # 處理價格欄位
            price_columns = ['開盤價', '最高價', '最低價', '收盤價', '最後揭示買價', '最後揭示賣價']
            for col in price_columns:
                if col in df.columns:
                    df[col] = df[col].apply(lambda x: str(x).replace(',', '') if isinstance(x, str) else x)
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 處理成交量欄位
            volume_columns = ['成交股數', '成交筆數', '成交金額']
            for col in volume_columns:
                if col in df.columns:
                    df[col] = df[col].apply(lambda x: str(x).replace(',', '') if isinstance(x, str) else x)
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 處理日期欄位
            if '日期' in df.columns:
                df['日期'] = self._safe_convert_date(df['日期'])
                
            # 處理特殊字符
            df = df.replace('--', np.nan)
            df = df.replace('', np.nan)
            
            return df
            
        except Exception as e:
            self.logger.error(f"處理價格數據時發生錯誤: {e}")
            self.logger.error(traceback.format_exc())
            return None
    
    def preprocess_stock_data(self, df, stock_id):
        """資料預處理與驗證
        
        Args:
            df: 原始股票數據DataFrame
            stock_id: 股票代號
            
        Returns:
            DataFrame: 預處理後的股票數據
        """
        try:
            df = df.copy()

            # 1. 基本資料處理
            if '證券代號' in df.columns:
                df['證券代號'] = df['證券代號'].astype(str)
                if df['證券代號'].nunique(dropna=True) > 1:
                    raise ValueError("單次指標計算只能包含一支股票")
            if '日期' in df.columns:
                df['日期'] = self._safe_convert_date(df['日期'])
                df = df.sort_values('日期', kind='stable').reset_index(drop=True)
            
            # 2. 處理價格欄位
            price_columns = ['開盤價', '最高價', '最低價', '收盤價']
            for col in price_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col].replace('--', np.nan), errors='coerce')
            
            # 3. 處理成交量
            volume_columns = ['成交股數', '成交筆數', '成交金額']
            for col in volume_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col].replace('--', 0), errors='coerce')
                    df[col] = df[col].fillna(0)
            
            # 4. 驗證數據完整性；缺價保留原值，由 causal kernel 切段暖機。
            if any(col in df.columns for col in price_columns):
                if df[list(col for col in price_columns if col in df.columns)].isnull().any().any():
                    self.logger.debug(f"股票 {stock_id} 存在缺失值")
                    
            return df
            
        except Exception as e:
            self.logger.error(f"預處理股票 {stock_id} 資料時發生錯誤: {str(e)}")
            return None
    
    def calculate_ma_series(self, df, params=None, full_config=None):
        """計算移動平均線系列
        
        Args:
            df: 股票數據DataFrame
            params: MA 參數字典
            full_config: 完整配置字典
            
        Returns:
            DataFrame: 添加移動平均線後的DataFrame
        """
        from .indicator_parameter_registry import IndicatorParameterRegistry, InvalidParameterError
        try:
            df_result = df.copy()
            close_col = self._get_column_name(df, 'Close')
            
            if close_col:
                # 若 params 不為 None，計算自訂 windows 均線
                if params is not None:
                    ma_clean = {k: v for k, v in params.items() if k != 'enabled'}
                    ma_sanitized = IndicatorParameterRegistry.validate_and_sanitize('ma', ma_clean, full_config)
                    windows = ma_sanitized['windows']
                else:
                    windows = []

                close_prices = clean_price_values(df[close_col])

                def calculate_segment(values):
                    close = values['Close']
                    output = {
                        'SMA30': talib.SMA(close, timeperiod=30),
                        'DEMA30': talib.DEMA(close, timeperiod=30),
                        'EMA30': talib.EMA(close, timeperiod=30),
                    }
                    output.update({
                        f'MA{window}': talib.SMA(close, timeperiod=window)
                        for window in windows
                    })
                    return output

                calculated = _segmented_calculation(
                    {'Close': close_prices}, calculate_segment
                )
                for column, values in calculated.items():
                    df_result[column] = values

            return df_result
            
        except InvalidParameterError as e:
            raise e
        except Exception as e:
            self.logger.error(f"計算移動平均線時發生錯誤: {str(e)}")
            return df.copy()
    
    def calculate_momentum_indicators(self, df, rsi_params=None, macd_params=None, full_config=None):
        """計算動量指標
        
        Args:
            df: 股票數據DataFrame
            rsi_params: RSI 參數字典
            macd_params: MACD 參數字典
            full_config: 完整配置字典
            
        Returns:
            Dict: 包含動量指標的字典
        """
        from .indicator_parameter_registry import IndicatorParameterRegistry, InvalidParameterError
        try:
            result = {}
            if rsi_params is None and macd_params is None:
                rsi_params = {}
                macd_params = {}
                
            close_col = self._get_column_name(df, 'Close')
            
            if close_col:
                close_prices = clean_price_values(df[close_col])
                sanitized_rsi = None
                if rsi_params is not None:
                    rsi_clean = {k: v for k, v in rsi_params.items() if k != 'enabled'}
                    sanitized_rsi = IndicatorParameterRegistry.validate_and_sanitize('rsi', rsi_clean, full_config)
                sanitized_macd = None
                if macd_params is not None:
                    macd_clean = {k: v for k, v in macd_params.items() if k != 'enabled'}
                    sanitized_macd = IndicatorParameterRegistry.validate_and_sanitize('macd', macd_clean, full_config)

                def calculate_segment(values):
                    close = values['Close']
                    output = {}
                    if sanitized_rsi is not None:
                        rsi = talib.RSI(close, timeperiod=sanitized_rsi['timeperiod'])
                        output['RSI'] = np.clip(rsi, 0, 100)
                    if sanitized_macd is not None:
                        macd, signal, hist = talib.MACD(
                            close,
                            fastperiod=sanitized_macd['fastperiod'],
                            slowperiod=sanitized_macd['slowperiod'],
                            signalperiod=sanitized_macd['signalperiod'],
                        )
                        output['MACD'] = macd
                        output['MACD_signal'] = signal
                        output['MACD_hist'] = hist
                    return output

                result = _segmented_calculation(
                    {'Close': close_prices}, calculate_segment
                )

            return result
            
        except InvalidParameterError as e:
            raise e
        except Exception as e:
            self.logger.error(f"計算動量指標時發生錯誤: {str(e)}")
            return {}
    
    def calculate_kd_indicator(self, df, params=None, full_config=None):
        """計算KD指標
        
        Args:
            df: 股票數據DataFrame
            params: KD 參數字典
            full_config: 完整配置字典
            
        Returns:
            Dict: 包含KD指標的字典
        """
        from .indicator_parameter_registry import IndicatorParameterRegistry, InvalidParameterError
        try:
            result = {}
            if params is None:
                return result
                
            high_col = self._get_column_name(df, 'High')
            low_col = self._get_column_name(df, 'Low')
            close_col = self._get_column_name(df, 'Close')
            
            if high_col and low_col and close_col:
                # 驗證 KD 參數
                kd_clean = {k: v for k, v in params.items() if k != 'enabled'}
                sanitized = IndicatorParameterRegistry.validate_and_sanitize('kd', kd_clean, full_config)
                
                # 清理價格序列（處理 '--' 和其他無效值）
                high_prices = clean_price_values(df[high_col])
                low_prices = clean_price_values(df[low_col])
                close_prices = clean_price_values(df[close_col])
                
                def calculate_segment(values):
                    slowk, slowd = talib.STOCH(
                        values['High'],
                        values['Low'],
                        values['Close'],
                        fastk_period=sanitized['fastk_period'],
                        slowk_period=sanitized['slowk_period'],
                        slowk_matype=sanitized['slowk_matype'],
                        slowd_period=sanitized['slowd_period'],
                        slowd_matype=sanitized['slowd_matype'],
                    )
                    return {
                        'slowk': np.clip(slowk, 0, 100),
                        'slowd': np.clip(slowd, 0, 100),
                    }

                result = _segmented_calculation(
                    {
                        'High': high_prices,
                        'Low': low_prices,
                        'Close': close_prices,
                    },
                    calculate_segment,
                )
                
            return result
            
        except InvalidParameterError as e:
            raise e
        except Exception as e:
            self.logger.error(f"計算KD指標時發生錯誤: {str(e)}")
            return {}
    
    def calculate_volatility_indicators(self, df, bollinger_params=None, sar_params=None, full_config=None):
        """計算波動指標
        
        Args:
            df: 股票數據DataFrame
            bollinger_params: 布林通道參數字典
            sar_params: SAR 參數字典
            full_config: 完整配置字典
            
        Returns:
            Dict: 包含波動指標的字典
        """
        from .indicator_parameter_registry import IndicatorParameterRegistry, InvalidParameterError
        try:
            result = {}
            if bollinger_params is None and sar_params is None:
                bollinger_params = {}
                sar_params = {}

            high_col = self._get_column_name(df, 'High')
            low_col = self._get_column_name(df, 'Low')
            close_col = self._get_column_name(df, 'Close')

            if close_col and bollinger_params is not None:
                boll_clean = {k: v for k, v in bollinger_params.items() if k != 'enabled'}
                boll_sanitized = IndicatorParameterRegistry.validate_and_sanitize(
                    'bollinger', boll_clean, full_config
                )

                def calculate_bollinger(values):
                    upper, middle, lower = talib.BBANDS(
                        values['Close'],
                        timeperiod=boll_sanitized['timeperiod'],
                        nbdevup=boll_sanitized['nbdevup'],
                        nbdevdn=boll_sanitized['nbdevdn'],
                        matype=boll_sanitized['matype'],
                    )
                    return {
                        'middleband': middle,
                        'upperband': upper,
                        'lowerband': lower,
                    }

                result.update(
                    _segmented_calculation(
                        {'Close': clean_price_values(df[close_col])},
                        calculate_bollinger,
                    )
                )

            if high_col and low_col and sar_params is not None:
                sar_clean = {k: v for k, v in sar_params.items() if k != 'enabled'}
                sar_sanitized = IndicatorParameterRegistry.validate_and_sanitize(
                    'sar', sar_clean, full_config
                )

                def calculate_sar(values):
                    return {
                        'SAR': talib.SAR(
                            values['High'],
                            values['Low'],
                            acceleration=sar_sanitized['acceleration'],
                            maximum=sar_sanitized['maximum'],
                        )
                    }

                result.update(
                    _segmented_calculation(
                        {
                            'High': clean_price_values(df[high_col]),
                            'Low': clean_price_values(df[low_col]),
                        },
                        calculate_sar,
                    )
                )

            return result

        except InvalidParameterError as e:
            raise e
        except Exception as e:
            self.logger.error(f"計算波動指標時發生錯誤: {str(e)}")
            return {}
    
    def calculate_trend_indicators(self, df, tsf_params=None, full_config=None):
        """計算趨勢指標
        
        Args:
            df: 股票數據DataFrame
            tsf_params: TSF 參數字典
            full_config: 完整配置字典
            
        Returns:
            Dict: 包含趨勢指標的字典
        """
        from .indicator_parameter_registry import IndicatorParameterRegistry, InvalidParameterError
        try:
            result = {}
            if tsf_params is None:
                return result
                
            close_col = self._get_column_name(df, 'Close')
            
            if close_col:
                tsf_clean = {k: v for k, v in tsf_params.items() if k != 'enabled'}
                tsf_sanitized = IndicatorParameterRegistry.validate_and_sanitize('tsf', tsf_clean, full_config)
                result = _segmented_calculation(
                    {'Close': clean_price_values(df[close_col])},
                    lambda values: {
                        'TSF': talib.TSF(
                            values['Close'],
                            timeperiod=tsf_sanitized['timeperiod'],
                        )
                    },
                )
                
            return result
            
        except InvalidParameterError as e:
            raise e
        except Exception as e:
            self.logger.error(f"計算趨勢指標時發生錯誤: {str(e)}")
            return {}

    def calculate_atr_indicator(self, df, params=None, full_config=None):
        """計算 ATR 指標
        
        Args:
            df: 股票數據DataFrame
            params: ATR 參數字典
            full_config: 完整配置字典
            
        Returns:
            Dict: 包含 ATR 指標的字典
        """
        from .indicator_parameter_registry import IndicatorParameterRegistry, InvalidParameterError
        try:
            result = {}
            if params is None:
                return result
                
            high_col = self._get_column_name(df, 'High')
            low_col = self._get_column_name(df, 'Low')
            close_col = self._get_column_name(df, 'Close')
            
            if high_col and low_col and close_col:
                # 驗證 ATR 參數
                atr_clean = {k: v for k, v in params.items() if k != 'enabled'}
                sanitized = IndicatorParameterRegistry.validate_and_sanitize('atr', atr_clean, full_config)
                result = _segmented_calculation(
                    {
                        'High': clean_price_values(df[high_col]),
                        'Low': clean_price_values(df[low_col]),
                        'Close': clean_price_values(df[close_col]),
                    },
                    lambda values: {
                        'ATR': talib.ATR(
                            values['High'],
                            values['Low'],
                            values['Close'],
                            timeperiod=sanitized['timeperiod'],
                        )
                    },
                )
                
            return result
            
        except InvalidParameterError as e:
            raise e
        except Exception as e:
            self.logger.error(f"計算 ATR 指標時發生錯誤: {str(e)}")
            return {}

    def calculate_adx_indicator(self, df, params=None, full_config=None):
        """計算 ADX 指標
        
        Args:
            df: 股票數據DataFrame
            params: ADX 參數字典
            full_config: 完整配置字典
            
        Returns:
            Dict: 包含 ADX 指標的字典
        """
        from .indicator_parameter_registry import IndicatorParameterRegistry, InvalidParameterError
        try:
            result = {}
            if params is None:
                return result
                
            high_col = self._get_column_name(df, 'High')
            low_col = self._get_column_name(df, 'Low')
            close_col = self._get_column_name(df, 'Close')
            
            if high_col and low_col and close_col:
                # 驗證 ADX 參數
                adx_clean = {k: v for k, v in params.items() if k != 'enabled'}
                sanitized = IndicatorParameterRegistry.validate_and_sanitize('adx', adx_clean, full_config)
                result = _segmented_calculation(
                    {
                        'High': clean_price_values(df[high_col]),
                        'Low': clean_price_values(df[low_col]),
                        'Close': clean_price_values(df[close_col]),
                    },
                    lambda values: {
                        'ADX': talib.ADX(
                            values['High'],
                            values['Low'],
                            values['Close'],
                            timeperiod=sanitized['timeperiod'],
                        )
                    },
                )
                
            return result
            
        except InvalidParameterError as e:
            raise e
        except Exception as e:
            self.logger.error(f"計算 ADX 指標時發生錯誤: {str(e)}")
            return {}
            
    def validate_indicator_results(self, df):
        """驗證指標計算結果
        
        Args:
            df: 含技術指標的DataFrame
            
        Returns:
            DataFrame: 驗證並修正後的DataFrame
        """
        try:
            df_result = df.copy()
            
            # 確保百分比指標在0-100範圍內
            percentage_columns = ['RSI', 'slowk', 'slowd']
            for col in percentage_columns:
                if col in df_result.columns:
                    df_result[col] = np.clip(df_result[col], 0, 100)
            
            # 處理無限值
            df_result = df_result.replace([np.inf, -np.inf], np.nan)
            
            return df_result
            
        except Exception as e:
            self.logger.error(f"驗證指標結果時發生錯誤: {str(e)}")
            return df.copy()
            
    def calculate_all_indicators(self, df, stock_id=None):
        """計算所有技術指標
        
        Args:
            df: 股票數據DataFrame
            stock_id: 股票代號，用於日誌記錄
            
        Returns:
            DataFrame: 添加所有技術指標後的DataFrame
        """
        try:
            normalized = self.preprocess_stock_data(df, stock_id)
            if normalized is None:
                return None
            return calculate_causal_indicators(normalized)
            
        except Exception as e:
            self.logger.error(f"計算股票 {stock_id} 的技術指標時發生錯誤: {str(e)}")
            self.logger.error(traceback.format_exc())
            return None
    
    def calculate_and_store_indicators(
        self,
        df,
        stock_id=None,
        output_dir=None,
        ignore_existing=False,
        precomputed_result=None,
    ):
        """計算技術指標並保存結果（會合併現有數據，避免覆蓋）
        
        Args:
            df: 股票數據DataFrame
            stock_id: 股票代號
            output_dir: 輸出目錄，如果為None則使用默認目錄
            ignore_existing: 如果為 True，忽略現有文件，直接覆蓋（用於修復有問題的文件）
            precomputed_result: 可選的 worker 計算結果；傳入時跳過重算，仍由父程序
                執行現有資料合併與單一寫入流程
            
        Returns:
            DataFrame: 計算好的技術指標DataFrame（包含合併後的完整數據）
        """
        try:
            # 計算所有指標；process-pool worker 已計算時由父程序傳入結果，
            # 仍由本方法統一負責合併與寫入，避免 worker 直接碰檔案／SQLite。
            result_df = (
                precomputed_result.copy()
                if isinstance(precomputed_result, pd.DataFrame)
                else self.calculate_all_indicators(df, stock_id)
            )
            if result_df is None:
                return None
                
            # 保存結果 - 使用傳入的 output_dir，避免硬編碼路徑
            if stock_id:
                if output_dir is None:
                    # 如果沒有指定 output_dir，使用當前工作目錄下的 technical_analysis
                    # 這應該由調用者確保傳入正確的 output_dir
                    raise ValueError(f"必須指定 output_dir 參數，不允許使用硬編碼路徑。股票: {stock_id}")
                else:
                    output_path = Path(output_dir) / f"{stock_id}_indicators.csv"
                
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                
                if '日期' not in result_df.columns and 'Date' in result_df.columns:
                    result_df = result_df.copy()
                    result_df['日期'] = self._safe_convert_date(result_df['Date'])

                # ✅ 修復：合併現有數據，避免覆蓋（添加數據驗證）
                if output_path.exists() and not ignore_existing:
                    try:
                        # 讀取現有數據
                        existing_df = pd.read_csv(output_path, encoding='utf-8-sig')
                        self.logger.info(f"讀取現有指標文件: {output_path}，包含 {len(existing_df)} 筆數據")
                        
                        # ✅ 數據驗證：檢查現有數據是否有效
                        if len(existing_df) == 0:
                            self.logger.warning(f"現有指標文件為空，將使用新數據覆蓋")
                        elif '日期' not in existing_df.columns:
                            self.logger.warning(f"現有指標文件缺少日期欄位，將使用新數據覆蓋")
                            existing_df = None  # 標記為無效，使用新數據
                        else:
                            # 檢查日期欄位是否有有效數據
                            date_col = pd.to_datetime(self._safe_convert_date(existing_df['日期']), errors='coerce')
                            valid_dates = date_col.notna().sum()
                            if valid_dates == 0:
                                self.logger.warning(f"現有指標文件的日期欄位無效，將使用新數據覆蓋")
                                existing_df = None  # 標記為無效，使用新數據
                        
                        # 如果現有數據有效，進行合併
                        if existing_df is not None and len(existing_df) > 0:
                            # 確保日期欄位存在且格式一致
                            if '日期' in existing_df.columns and '日期' in result_df.columns:
                                # 轉換日期為字符串格式以便比較
                                existing_df['日期'] = self._safe_convert_date(existing_df['日期'])
                                result_df['日期'] = self._safe_convert_date(result_df['日期'])
                                
                                # ✅ 數據驗證：檢查合併前的數據完整性
                                # 檢查是否有必要的欄位
                                required_cols = ['日期', '證券代號']
                                missing_cols = [col for col in required_cols if col not in existing_df.columns]
                                if missing_cols:
                                    self.logger.warning(f"現有指標文件缺少必要欄位 {missing_cols}，將使用新數據覆蓋")
                                    existing_df = None
                                else:
                                    # 合併數據（保留所有列）
                                    merged_df = pd.concat([existing_df, result_df], ignore_index=True)
                                    
                                    # 去重（基於日期，保留最後一條）
                                    merged_df = merged_df.drop_duplicates(subset=['日期'], keep='last')
                                    
                                    # 按日期排序
                                    merged_df['日期'] = pd.to_datetime(self._safe_convert_date(merged_df['日期']), errors='coerce')
                                    merged_df = merged_df.sort_values('日期')
                                    merged_df['日期'] = merged_df['日期'].dt.strftime('%Y-%m-%d')
                                    
                                    self.logger.info(f"合併後數據: {len(merged_df)} 筆（原有 {len(existing_df)} 筆，新增 {len(result_df)} 筆）")
                                    result_df = merged_df
                            else:
                                # 沒有日期欄位時不能安全判斷增量邊界；直接覆蓋，避免資料倍增。
                                self.logger.warning(f"指標文件缺少日期欄位，將使用新數據覆蓋，避免直接合併造成重複")
                            
                    except Exception as e:
                        self.logger.warning(f"讀取現有指標文件時發生錯誤，將覆蓋文件: {e}")
                        self.logger.debug(f"詳細錯誤信息: {traceback.format_exc()}")
                        # 如果讀取失敗，繼續使用新數據
                
                # 保存合併後的數據
                result_df.to_csv(output_path, index=False, encoding='utf-8-sig')
                self.logger.info(f"已保存 {stock_id} 的技術指標到 {output_path}（共 {len(result_df)} 筆數據）")
                
            return result_df
            
        except Exception as e:
            self.logger.error(f"處理並保存股票 {stock_id} 的技術指標時發生錯誤: {str(e)}")
            self.logger.error(traceback.format_exc())
            return None
    
    def process_stock_data_batch(
        self,
        stock_data_path=None,
        output_dir=None,
        merged_output_path=None,
        backup_dir=None,
    ):
        """批次處理股票資料
        
        Args:
            stock_data_path: 股票數據檔案路徑，必須由呼叫端明確提供
            output_dir: 單股技術指標輸出目錄，必須由呼叫端明確提供
            merged_output_path: 全市場整合技術指標輸出檔，必須由呼叫端明確提供
            backup_dir: merged_output_path 的備份目錄；未提供時使用 merged_output_path.parent / "backup"
            
        Returns:
            bool: 處理成功返回True，否則返回False
        """
        try:
            import shutil
            from datetime import datetime
            from tqdm import tqdm

            if stock_data_path is None or output_dir is None or merged_output_path is None:
                self.logger.error(
                    "process_stock_data_batch 必須明確指定 stock_data_path、output_dir、merged_output_path，"
                    "避免誤寫正式資料根目錄"
                )
                return False

            stock_data_path = Path(stock_data_path)
            output_dir = Path(output_dir)
            merged_output_path = Path(merged_output_path)
            backup_dir = Path(backup_dir) if backup_dir is not None else merged_output_path.parent / "backup"
            
            # 1. 讀取資料
            self.logger.info(f"開始批次處理股票技術指標，讀取數據從: {stock_data_path}")
            stock_data = pd.read_csv(
                stock_data_path,
                dtype={'證券代號': str}
            )
            
            # 2. 只保留4位數股票
            stock_data = stock_data[stock_data['證券代號'].str.match(r'^\d{4}$')]
            
            # 3. 批次處理
            all_data = []
            grouped = stock_data.groupby('證券代號')
            
            with tqdm(grouped, desc="處理進度") as pbar:
                for stock_id, group_df in pbar:
                    pbar.set_description(f"處理 {stock_id}")
                    
                    if len(group_df) < 30:
                        continue
                        
                    result = self.calculate_and_store_indicators(
                        group_df, 
                        stock_id, 
                        output_dir=output_dir
                    )
                    if isinstance(result, pd.DataFrame):
                        all_data.append(result)
            
            # 4. 合併並儲存結果
            if all_data:
                final_df = pd.concat(all_data, ignore_index=True)
                save_path = merged_output_path
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                final_df.to_csv(save_path, index=False, encoding='utf-8-sig')
                
                # 建立備份
                today = datetime.now().strftime('%Y%m%d')
                backup_path = backup_dir / f"all_stocks_data_{today}.csv"
                os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                shutil.copy2(save_path, backup_path)
                self.logger.info(f"已保存合併數據到 {save_path} 並備份到 {backup_path}")
                
                return True
                
            return False
            
        except Exception as e:
            self.logger.error(f"批次處理發生錯誤: {str(e)}")
            self.logger.error(traceback.format_exc())
            return False
    
    def main(self):
        """主程序
        
        Returns:
            bool: 執行成功返回True，否則返回False
        """
        try:
            self.logger.info("開始批次處理股票技術指標...")
            
            from data_module.config import TWStockConfig

            config = TWStockConfig()
            base_path = config.data_root
            required_dirs = [
                config.meta_data_dir,
                config.technical_dir,
                config.meta_data_dir / "backup",
            ]
            
            for dir_path in required_dirs:
                if not dir_path.exists():
                    dir_path.mkdir(parents=True)
                    self.logger.info(f"Created directory: {dir_path}")
            
            # 2. 開始批次處理
            if self.process_stock_data_batch(
                stock_data_path=config.stock_data_file,
                output_dir=config.technical_dir,
                merged_output_path=config.all_stocks_data_file,
                backup_dir=config.meta_data_dir / "backup",
            ):
                self.logger.info("批次處理完成")
                
                # 3. 檢查結果
                results_path = config.all_stocks_data_file
                if results_path.exists():
                    df = pd.read_csv(results_path)
                    self.logger.info(f"總處理筆數: {len(df):,}")
                    self.logger.info(f"股票數量: {df['證券代號'].nunique():,}")
                return True
            else:
                self.logger.error("批次處理失敗")
                return False
                
        except Exception as e:
            self.logger.error(f"主程序執行時發生錯誤: {e}")
            self.logger.error(traceback.format_exc())
            return False


# 如果直接運行該模塊，則執行主程序
if __name__ == "__main__":
    calculator = TechnicalIndicatorCalculator()
    if calculator.main():
        calculator.logger.info("程序執行完成")
        
        # 顯示範例結果
        try:
            example_stock = "2330"
            from data_module.config import TWStockConfig

            config = TWStockConfig()
            df = pd.read_csv(config.technical_dir / f"{example_stock}_indicators.csv")
            print(f"\n{example_stock} 技術指標計算結果範例:")
            print(df.tail())
        except Exception as e:
            calculator.logger.error(f"顯示範例結果時發生錯誤: {e}")
    else:
        calculator.logger.error("程序執行失敗")
