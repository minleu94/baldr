"""
Pandas DataFrame 的 Qt Model
提供排序、欄位隱藏、filter/search 等功能
"""

from collections.abc import Mapping
from decimal import Decimal
from PySide6.QtCore import QAbstractTableModel, Qt, QModelIndex, Signal
from PySide6.QtGui import QColor
import pandas as pd
import numpy as np
from typing import Optional, List, Dict, Any


class PandasTableModel(QAbstractTableModel):
    """Pandas DataFrame 的 Qt Model"""
    
    # 自定義信號
    dataChanged = Signal(QModelIndex, QModelIndex)  # 數據改變信號
    
    def __init__(
        self,
        dataframe: pd.DataFrame,
        parent=None,
        red_positive_columns: Optional[set[str]] = None,
        decimal_places_by_column: Optional[Mapping[str, int]] = None,
    ):
        """初始化 Model
        
        Args:
            dataframe: 要顯示的 DataFrame
            parent: 父對象
            red_positive_columns: 數值為正但語意代表跌幅 / 風險時，需用紅色顯示的欄位
        """
        super().__init__(parent)
        self._dataframe = dataframe.copy()
        self._original_dataframe = dataframe.copy()  # 保存原始數據用於重置
        self._sort_column = -1
        self._sort_order = Qt.AscendingOrder
        self._visible_columns = list(dataframe.columns)  # 可見欄位列表
        self._red_positive_columns = set(red_positive_columns or ())
        self._decimal_places_by_column = self._validated_decimal_places(
            dataframe,
            decimal_places_by_column,
        )

    @staticmethod
    def _validated_decimal_places(
        dataframe: pd.DataFrame,
        options: Optional[Mapping[str, int]],
    ) -> dict[str, int]:
        """驗證 opt-in 顯示精度；不接受 bool 精度或過長格式。"""

        if options is None:
            return {}
        if not isinstance(options, Mapping):
            raise TypeError("decimal_places_by_column 必須是欄名到精度的 mapping")

        validated: dict[str, int] = {}
        for column, places in options.items():
            if type(column) is not str or not column:
                raise TypeError("Decimal 顯示欄名必須是非空字串")
            if column not in dataframe.columns:
                raise ValueError(f"Decimal 顯示欄位不存在：{column}")
            if type(places) is not int:
                raise TypeError("Decimal 顯示精度必須是 int，且不可為 bool")
            if not 0 <= places <= 8:
                raise ValueError("Decimal 顯示精度必須介於 0 到 8")
            validated[column] = places
        return validated

    @staticmethod
    def _format_configured_decimal(value: object, places: int) -> str:
        """只將合法有限 Decimal／整數轉為顯示文字，不改變底層數值。"""

        if type(value) is Decimal:
            if not value.is_finite():
                return "未知"
            return format(value, f".{places}f")
        if type(value) is bool or isinstance(value, np.bool_):
            return "未知"
        if type(value) is int:
            return format(Decimal(value), f".{places}f")
        if isinstance(value, np.integer):
            return format(Decimal(int(value)), f".{places}f")
        return "未知"
    
    def rowCount(self, parent=QModelIndex()) -> int:
        """返回行數"""
        return len(self._dataframe)
    
    def columnCount(self, parent=QModelIndex()) -> int:
        """返回列數（只計算可見欄位）"""
        return len(self._visible_columns)
    
    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        """返回指定索引的數據"""
        if not index.isValid():
            return None
        
        row = index.row()
        col = index.column()
        
        # 檢查索引範圍
        if row < 0 or row >= len(self._dataframe):
            return None
        if col < 0 or col >= len(self._visible_columns):
            return None
        
        try:
            col_name = self._visible_columns[col]
            
            # 檢查欄位是否存在
            if col_name not in self._dataframe.columns:
                return None
            
            # 可見欄位可能只是原始 DataFrame 的子集；必須依欄名取值，
            # 不能把可見欄位位置誤當成原始欄位位置，否則表頭與內容會錯位。
            # 同名欄位則依 visible occurrence 對應回原始 occurrence，避免
            # pandas get_loc 回傳 slice／Series。
            source_positions = [
                position
                for position, name in enumerate(self._dataframe.columns)
                if name == col_name
            ]
            visible_occurrence = sum(
                1 for name in self._visible_columns[:col] if name == col_name
            )
            source_column = source_positions[
                min(visible_occurrence, len(source_positions) - 1)
            ]
            value = self._dataframe.iloc[row, source_column]
            
            if role in (Qt.DisplayRole, Qt.ToolTipRole):
                decimal_places = self._decimal_places_by_column.get(col_name)
                if decimal_places is not None:
                    if role == Qt.ToolTipRole:
                        return "" if value is None else str(value)
                    return self._format_configured_decimal(value, decimal_places)

                # 處理列表/數組類型（如 tags）
                if isinstance(value, (list, tuple, np.ndarray)):
                    if len(value) == 0:
                        return ""
                    # 將列表轉換為字符串
                    return ", ".join(str(v) for v in value)
                
                # 處理 NaN
                if pd.isna(value):
                    return ""
                
                # 格式化數值
                if isinstance(value, (int, float)):
                    # 如果是小數，保留2位
                    if isinstance(value, float) and abs(value) < 1000:
                        return f"{value:.2f}"
                    else:
                        return str(value)
                
                return str(value)
            
            elif role == Qt.TextAlignmentRole:
                # 對齊方式
                # 跳過列表/數組類型，避免布爾判斷錯誤
                if isinstance(value, (list, tuple, np.ndarray)):
                    return Qt.AlignLeft | Qt.AlignVCenter
                
                if isinstance(value, (int, float)):
                    try:
                        if not pd.isna(value):
                            return Qt.AlignRight | Qt.AlignVCenter
                    except (ValueError, TypeError):
                        pass
                return Qt.AlignLeft | Qt.AlignVCenter
            
            elif role == Qt.ForegroundRole:
                # 文字顏色（可根據數值正負設置顏色）
                # 跳過列表/數組類型，避免布爾判斷錯誤
                if isinstance(value, (list, tuple, np.ndarray)):
                    return None
                
                if isinstance(value, (int, float)):
                    try:
                        if not pd.isna(value):
                            if col_name in self._red_positive_columns and value != 0:
                                return QColor(255, 68, 68)
                            if value > 0:
                                return QColor(0, 255, 136)  # 綠色（正數）
                            elif value < 0:
                                return QColor(255, 68, 68)   # 紅色（負數）
                    except (ValueError, TypeError):
                        pass
                
                return None
        except Exception as e:
            # 捕獲所有異常，避免程式崩潰
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"PandasTableModel.data 錯誤: {e}, row={row}, col={col}")
            return None
        
        return None
    
    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:
        """返回表頭數據"""
        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            if orientation == Qt.Horizontal:
                # 表頭懸停也回傳同一個可見欄名，包含被截斷的長欄名。
                if 0 <= section < len(self._visible_columns):
                    return self._visible_columns[section]
            elif section >= 0:
                # 返回行號（從1開始）
                return str(section + 1)
        
        return None
    
    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder):
        """排序"""
        if column < 0 or column >= len(self._visible_columns):
            return
        
        col_name = self._visible_columns[column]
        
        # 檢查欄位是否存在
        if col_name not in self._dataframe.columns:
            return
        
        self._sort_column = column
        self._sort_order = order
        
        # 執行排序
        ascending = (order == Qt.AscendingOrder)
        self._dataframe = self._dataframe.sort_values(
            by=col_name,
            ascending=ascending,
            na_position='last'
        ).reset_index(drop=True)
        
        # 發送數據改變信號
        self.layoutChanged.emit()
    
    def setDataFrame(self, dataframe: pd.DataFrame):
        """更新 DataFrame"""
        self.beginResetModel()
        self._dataframe = dataframe.copy()
        self._original_dataframe = dataframe.copy()
        # 保持可見欄位（如果新 DataFrame 有這些欄位）
        self._visible_columns = [col for col in self._visible_columns if col in dataframe.columns]
        if not self._visible_columns:
            self._visible_columns = list(dataframe.columns)
        self.endResetModel()
    
    def getDataFrame(self) -> pd.DataFrame:
        """獲取當前 DataFrame"""
        return self._dataframe.copy()
    
    def setVisibleColumns(self, columns: List[str]):
        """設置可見欄位"""
        # 只保留 DataFrame 中存在的欄位
        valid_columns = [col for col in columns if col in self._dataframe.columns]
        if valid_columns:
            self.beginResetModel()
            self._visible_columns = valid_columns
            self.endResetModel()
    
    def getVisibleColumns(self) -> List[str]:
        """獲取可見欄位列表"""
        return self._visible_columns.copy()
    
    def filter(self, column: str, value: str):
        """過濾數據（簡單的字符串匹配）"""
        if column not in self._dataframe.columns:
            return
        
        if not value:
            # 重置為原始數據
            self.setDataFrame(self._original_dataframe)
            return
        
        # 過濾
        mask = self._dataframe[column].astype(str).str.contains(value, case=False, na=False)
        filtered_df = self._original_dataframe[mask].copy()
        self.setDataFrame(filtered_df)
    
    def resetFilter(self):
        """重置過濾"""
        self.setDataFrame(self._original_dataframe)


