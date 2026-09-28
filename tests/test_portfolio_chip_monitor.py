"""Unit tests for PortfolioChipService.
"""

import unittest
import hashlib
import sqlite3
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch
import pandas as pd

from app_module.portfolio_chip_service import PortfolioChipService
from data_module.config import TWStockConfig
from decision_module.flow_contracts import BrokerFlowEvent


def _sqlite_state(db_path: Path) -> dict[str, object]:
    files: dict[str, object] = {}
    for name, path in (
        ("main", db_path),
        ("wal", Path(f"{db_path}-wal")),
        ("shm", Path(f"{db_path}-shm")),
    ):
        if path.is_file():
            raw = path.read_bytes()
            files[name] = {
                "exists": True,
                "size": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "mtime_ns": path.stat().st_mtime_ns,
                "header": raw[:16].hex(),
            }
        else:
            files[name] = {"exists": False}
    connection = sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True)
    try:
        journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0])
    finally:
        connection.close()
    return {"files": files, "journal_mode": journal_mode}


def _create_chip_database(db_path: Path, *, with_broker_rows: bool) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE broker_flows (
                日期 TEXT, 分點名稱 TEXT, 證券代號 TEXT,
                買進股數 INTEGER, 賣出股數 INTEGER, 買賣超股數 INTEGER,
                買進金額千元 INTEGER, 賣出金額千元 INTEGER, 買賣超金額千元 INTEGER,
                lots_observed INTEGER, amount_observed INTEGER,
                lots_rank INTEGER, amount_rank INTEGER
            )
            """
        )
        connection.execute(
            "CREATE TABLE daily_prices (日期 TEXT, 證券代號 TEXT, 收盤價 TEXT)"
        )
        if with_broker_rows:
            connection.execute(
                "INSERT INTO broker_flows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "20260611", "branch_a", "2330", 100000, 50000, 50000,
                    5000, 1000, 4000, 1, 1, 1, 1,
                ),
            )
            connection.execute(
                "INSERT INTO daily_prices VALUES (?, ?, ?)",
                ("20260611", "2330", "50.00"),
            )
        connection.commit()
    finally:
        connection.close()


class TestPortfolioChipService(unittest.TestCase):

    def setUp(self):
        self.config = MagicMock(spec=TWStockConfig)
        self.config.broker_branch_registry_file = MagicMock()
        self.config.broker_branch_registry_file.exists.return_value = False
        self.config.use_sqlite = False
        self._temp_dir = tempfile.TemporaryDirectory()
        self.temp_root = Path(self._temp_dir.name)

        self.broker_flow_service = MagicMock()
        self.service = PortfolioChipService(self.config, self.broker_flow_service)

    def tearDown(self):
        self._temp_dir.cleanup()

    def _set_csv_fallback(self):
        self.broker_flow_service._load_data.return_value = [
            BrokerFlowEvent(
                date="2026-06-11",
                branch_system_key="branch_a",
                branch_display_name="分點A",
                stock_code="2330",
                stock_name="台積電",
                buy_qty=100,
                sell_qty=20,
                net_qty=80,
                buy_amount_k_twd=5000,
                sell_amount_k_twd=1000,
                net_amount_k_twd=4000,
            )
        ]

    def test_empty_summary(self):
        # 測試在無交易數據時，返回正確的空摘要結構
        summary = self.service._empty_summary("2330", 5)
        self.assertEqual(summary['stock_code'], "2330")
        self.assertEqual(summary['accumulated_buy'], 0)
        self.assertEqual(summary['accumulated_sell'], 0)
        self.assertEqual(summary['accumulated_net'], 0)
        self.assertEqual(summary['concentration'], 0.0)
        self.assertEqual(summary['consecutive_days'], 0)
        self.assertEqual(summary['risk_level'], 'neutral')
        self.assertIn("無主力分點交易數據", summary['risk_reasons'])

    def test_aggregate_flow_dataframe_neutral(self):
        # 測試正常/溫和的買賣超聚合計算
        df = pd.DataFrame([
            {'日期': '20260611', '分點名稱': 'branch_a', '買進股數': 10000, '賣出股數': 5000, '買賣超股數': 5000},
            {'日期': '20260611', '分點名稱': 'branch_b', '買進股數': 20000, '賣出股數': 25000, '買賣超股數': -5000},
        ])

        summary = self.service._aggregate_flow_dataframe(df, "2330", 5, ["20260611"])

        self.assertEqual(summary['accumulated_buy'], 30000)
        self.assertEqual(summary['accumulated_sell'], 30000)
        self.assertEqual(summary['accumulated_net'], 0)
        self.assertEqual(summary['concentration'], 0.0)
        self.assertEqual(summary['risk_level'], 'neutral')
        self.assertEqual(len(summary['branch_details']), 2)

    def test_aggregate_flow_dataframe_bullish_large_buy(self):
        # 測試大額淨買超觸發 bullish 警示
        df = pd.DataFrame([
            {'日期': '20260611', '分點名稱': 'branch_a', '買進股數': 600000, '賣出股數': 50000, '買賣超股數': 550000},
        ])

        summary = self.service._aggregate_flow_dataframe(df, "2330", 5, ["20260611"])

        self.assertEqual(summary['accumulated_net'], 550000)
        self.assertEqual(summary['risk_level'], 'bullish')
        self.assertTrue(any("累計大額買進" in reason for reason in summary['risk_reasons']))

    def test_consecutive_selling_bearish(self):
        # 測試連續 3 天淨賣超觸發 bearish 警示
        df = pd.DataFrame([
            {'日期': '20260611', '分點名稱': 'branch_a', '買進股數': 1000, '賣出股數': 5000, '買賣超股數': -4000},
            {'日期': '20260610', '分點名稱': 'branch_a', '買進股數': 1000, '賣出股數': 6000, '買賣超股數': -5000},
            {'日期': '20260609', '分點名稱': 'branch_a', '買進股數': 1000, '賣出股數': 7000, '買賣超股數': -6000},
        ])

        summary = self.service._aggregate_flow_dataframe(df, "2330", 5, ["20260611", "20260610", "20260609"])

        self.assertEqual(summary['consecutive_days'], -3)
        self.assertEqual(summary['risk_level'], 'bearish')
        self.assertTrue(any("連續 3 日淨出貨" in reason for reason in summary['risk_reasons']))

    @patch('app_module.portfolio_chip_service.ReadOnlySQLiteManager')
    def test_sqlite_query_flow(self, mock_db_class):
        # 測試 SQLite 模式下的查詢流
        self.config.use_sqlite = True
        self.config.db_file = Path("unused.sqlite")
        mock_db = MagicMock()
        mock_db.last_read_mode = "normal"
        mock_db_class.return_value = mock_db

        # 模擬日期返回
        mock_db.execute_query.side_effect = [
            pd.DataFrame({'日期': ['20260611']}), # 交易日期
            pd.DataFrame([ # 明細數據
                {'日期': '20260611', '分點名稱': 'branch_a', '買進股數': 100000, '賣出股數': 50000, '買賣超股數': 50000}
            ])
        ]

        summary = self.service.get_stock_chip_summary("2330", 5)

        self.assertEqual(summary['stock_code'], "2330")
        self.assertEqual(summary['accumulated_net'], 50000)
        self.assertEqual(summary['concentration'], 50000 / 150000)

    def test_sqlite_rows_are_read_without_changing_database_or_sidecars(self):
        self.config.use_sqlite = True
        db_path = self.temp_root / "sqlite" / "twstock.db"
        _create_chip_database(db_path, with_broker_rows=True)
        self.config.db_file = db_path
        before = _sqlite_state(db_path)

        summary = self.service.get_stock_chip_summary("2330", 5)

        self.assertEqual(summary["accumulated_net"], 50000)
        self.assertEqual(summary["observed_event_count"], 1)
        self.assertEqual(_sqlite_state(db_path), before)

    def test_sqlite_empty_broker_table_does_not_fall_back_to_csv(self):
        self.config.use_sqlite = True
        db_path = self.temp_root / "sqlite" / "twstock.db"
        _create_chip_database(db_path, with_broker_rows=False)
        self.config.db_file = db_path
        self._set_csv_fallback()
        before = _sqlite_state(db_path)

        summary = self.service.get_stock_chip_summary("2330", 5)

        self.assertEqual(summary["accumulated_net"], 0)
        self.broker_flow_service._load_data.assert_not_called()
        self.assertEqual(_sqlite_state(db_path), before)

    def test_missing_sqlite_table_falls_back_to_csv_without_mutating_database(self):
        self.config.use_sqlite = True
        db_path = self.temp_root / "sqlite" / "twstock.db"
        db_path.parent.mkdir(parents=True)
        connection = sqlite3.connect(db_path)
        try:
            connection.execute("CREATE TABLE unrelated (value TEXT)")
            connection.commit()
        finally:
            connection.close()
        self.config.db_file = db_path
        self._set_csv_fallback()
        before = _sqlite_state(db_path)

        summary = self.service.get_stock_chip_summary("2330", 5)

        self.assertEqual(summary["accumulated_net"], 80000)
        self.broker_flow_service._load_data.assert_called_once_with()
        self.assertEqual(_sqlite_state(db_path), before)

    def test_missing_sqlite_database_falls_back_to_csv_without_creating_it(self):
        self.config.use_sqlite = True
        db_path = self.temp_root / "missing" / "sqlite" / "twstock.db"
        self.config.db_file = db_path
        self._set_csv_fallback()

        summary = self.service.get_stock_chip_summary("2330", 5)

        self.assertEqual(summary["accumulated_net"], 80000)
        self.assertFalse(db_path.exists())
        self.assertFalse(db_path.parent.exists())

    @patch('app_module.portfolio_chip_service.ReadOnlySQLiteManager')
    def test_immutable_broker_snapshot_is_visible_in_summary(self, mock_db_class):
        self.config.use_sqlite = True
        self.config.db_file = self.temp_root / "unused.sqlite"
        mock_db = MagicMock()
        mock_db.last_read_mode = "immutable_fallback"
        mock_db.execute_query.side_effect = [
            pd.DataFrame({'日期': ['20260611']}),
            pd.DataFrame([{
                '日期': '20260611',
                '分點名稱': 'branch_a',
                '買進股數': 100000,
                '賣出股數': 50000,
                '買賣超股數': 50000,
                '買進金額千元': 5000,
                '賣出金額千元': 1000,
                '買賣超金額千元': 4000,
            }]),
        ]
        mock_db_class.return_value = mock_db

        summary = self.service.get_stock_chip_summary("2330", 5)

        self.assertEqual(summary["accumulated_net"], 50000)
        self.assertIn(
            "⚠️ SQLite 使用 immutable 唯讀快照，可能只包含較舊的已提交資料。",
            summary["risk_reasons"],
        )

    @patch('app_module.portfolio_chip_service.ReadOnlySQLiteManager')
    def test_immutable_primary_snapshot_does_not_mix_normal_price_rows(self, mock_db_class):
        self.config.use_sqlite = True
        self.config.db_file = self.temp_root / "unused.sqlite"
        mock_db = MagicMock()
        mock_db.last_read_mode = "immutable_fallback"
        mock_db.execute_query.side_effect = [
            pd.DataFrame({'日期': ['20260611']}),
            pd.DataFrame([{
                '日期': '20260611',
                '分點名稱': 'branch_a',
                '買進股數': None,
                '賣出股數': None,
                '買賣超股數': None,
                '買進金額千元': 100,
                '賣出金額千元': 0,
                '買賣超金額千元': 100,
            }]),
        ]
        mock_db_class.return_value = mock_db

        summary = self.service.get_stock_chip_summary("2330", 5)

        self.assertEqual(mock_db_class.call_count, 1)
        self.assertEqual(mock_db.execute_query.call_count, 2)
        self.assertEqual(summary["accumulated_net"], 0)
        self.assertEqual(summary["estimated_event_count"], 0)
        self.assertEqual(summary["unavailable_event_count"], 1)
        self.assertIn(
            "⚠️ SQLite 使用 immutable 唯讀快照，可能只包含較舊的已提交資料。",
            summary["risk_reasons"],
        )

    def test_csv_fallback_flow(self):
        # 測試 CSV 降級模式下的數據查詢
        self.config.use_sqlite = False

        self.broker_flow_service._load_data.return_value = [
            BrokerFlowEvent(
                date='2026-06-11',
                branch_system_key='branch_a',
                branch_display_name='分點A',
                stock_code='2330',
                stock_name='台積電',
                buy_qty=100,  # 100張 = 100,000股
                sell_qty=20,   # 20張 = 20,000股
                net_qty=80,    # 80張 = 80,000股
                buy_amount_k_twd=5000,
                sell_amount_k_twd=1000,
                net_amount_k_twd=4000,
            )
        ]

        summary = self.service.get_stock_chip_summary("2330", 5)

        self.assertEqual(summary['stock_code'], "2330")
        self.assertEqual(summary['accumulated_buy'], 100000)
        self.assertEqual(summary['accumulated_sell'], 20000)
        self.assertEqual(summary['accumulated_net'], 80000)
        self.assertEqual(summary['concentration'], 80000 / 120000)

    def test_legacy_amount_event_is_not_treated_as_lots(self):
        self.config.use_sqlite = False
        self.broker_flow_service._load_data.return_value = []

        summary = self.service.get_stock_chip_summary("2330", 5)

        self.assertEqual(summary['accumulated_net'], 0)
        self.assertEqual(summary['risk_level'], 'neutral')

    @patch('app_module.portfolio_chip_service.ReadOnlySQLiteManager')
    def test_aggregate_flow_dataframe_estimates_lots(self, mock_db_class):
        # 測試 SQLite 缺失股數 (NULL) 且收盤價存在時，使用 Decimal ROUND_HALF_UP 折算股數
        self.config.use_sqlite = True
        self.config.db_file = Path("unused.sqlite")
        mock_db = MagicMock()
        mock_db.last_read_mode = "normal"
        mock_db_class.return_value = mock_db

        # 模擬 daily_prices 返回收盤價 50.0
        mock_db.execute_query.return_value = pd.DataFrame([
            {'日期': '20260611', '收盤價': 50.0}
        ])

        # 輸入 df 含有缺失 (None) 的股數
        df = pd.DataFrame([
            {
                '日期': '20260611',
                '分點名稱': 'branch_a',
                '買進股數': None,
                '賣出股數': None,
                '買賣超股數': None,
                '買進金額千元': 100,  # 100,000 元
                '賣出金額千元': 0,    # 0 元
                '買賣超金額千元': 100
            }
        ])

        summary = self.service._aggregate_flow_dataframe(df, "2330", 5, ["20260611"])

        # 100 * 1000 / 50.0 = 2000 股
        self.assertEqual(summary['accumulated_buy'], 2000)
        self.assertEqual(summary['accumulated_sell'], 0)
        self.assertEqual(summary['accumulated_net'], 2000)
        self.assertTrue(any("估計股數" in reason for reason in summary['risk_reasons']))

    @patch('app_module.portfolio_chip_service.ReadOnlySQLiteManager')
    def test_estimated_rows_use_standard_large_flow_threshold(self, mock_db_class):
        # Phase 3 改以 coverage 表達資料品質，不再用門檻加倍隱藏估算訊號。
        self.config.use_sqlite = True
        self.config.db_file = Path("unused.sqlite")
        mock_db = MagicMock()
        mock_db.last_read_mode = "normal"
        mock_db_class.return_value = mock_db

        # 模擬收盤價 10.0
        mock_db.execute_query.return_value = pd.DataFrame([
            {'日期': '20260611', '收盤價': 10.0}
        ])

        df = pd.DataFrame([
            {
                '日期': '20260611',
                '分點名稱': 'branch_a',
                '買進股數': None,
                '賣出股數': None,
                '買賣超股數': None,
                '買進金額千元': 6000,  # 6000 * 1000 = 6,000,000 元 -> / 10.0 = 600,000 股
                '賣出金額千元': 0,
                '買賣超金額千元': 6000
            }
        ])

        summary = self.service._aggregate_flow_dataframe(df, "2330", 5, ["20260611"])
        self.assertEqual(summary['accumulated_net'], 600000)
        self.assertEqual(summary['risk_level'], 'bullish')
        self.assertEqual(summary['estimated_event_count'], 1)
        self.assertEqual(summary['lots_coverage_ratio'], Decimal('1'))

        # 再測試買進 1,200,000 股 (超過 1,000,000)，應觸發大額買進警示 (bullish)
        df_large = pd.DataFrame([
            {
                '日期': '20260611',
                '分點名稱': 'branch_a',
                '買進股數': None,
                '賣出股數': None,
                '買賣超股數': None,
                '買進金額千元': 12000,  # 12,000,000 元 -> / 10.0 = 1,200,000 股
                '賣出金額千元': 0,
                '買賣超金額千元': 12000
            }
        ])

        summary_large = self.service._aggregate_flow_dataframe(df_large, "2330", 5, ["20260611"])
        self.assertEqual(summary_large['accumulated_net'], 1200000)
        self.assertEqual(summary_large['risk_level'], 'bullish')

    @patch('app_module.portfolio_chip_service.ReadOnlySQLiteManager')
    def test_no_price_keeps_lots_null(self, mock_db_class):
        # 測試無收盤價時不猜測 100.0 元，折算為 0，且 lots_available 設為 False
        self.config.use_sqlite = True
        self.config.db_file = Path("unused.sqlite")
        mock_db = MagicMock()
        mock_db.last_read_mode = "normal"
        mock_db_class.return_value = mock_db

        # 模擬 daily_prices 沒有任何資料 (價格缺失)
        mock_db.execute_query.return_value = pd.DataFrame()

        df = pd.DataFrame([
            {
                '日期': '20260611',
                '分點名稱': 'branch_a',
                '買進股數': None,
                '賣出股數': None,
                '買賣超股數': None,
                '買進金額千元': 100,
                '賣出金額千元': 0,
                '買賣超金額千元': 100
            }
        ])

        summary = self.service._aggregate_flow_dataframe(df, "2330", 5, ["20260611"])
        # 無價格，股數保持 0 (即 None fallback)
        self.assertEqual(summary['accumulated_net'], 0)

    @patch('app_module.portfolio_chip_service.ReadOnlySQLiteManager')
    def test_immutable_price_fallback_is_visible_and_never_estimates_lots(self, mock_db_class):
        self.config.use_sqlite = True
        self.config.db_file = self.temp_root / "unused.sqlite"
        main_db = MagicMock()
        main_db.last_read_mode = "normal"
        main_db.execute_query.side_effect = [
            pd.DataFrame({'日期': ['20260611']}),
            pd.DataFrame([{
                '日期': '20260611',
                '分點名稱': 'branch_a',
                '買進股數': None,
                '賣出股數': None,
                '買賣超股數': None,
                '買進金額千元': 100,
                '賣出金額千元': 0,
                '買賣超金額千元': 100,
            }]),
        ]
        price_db = MagicMock()
        price_db.last_read_mode = "immutable_fallback"
        price_db.execute_query.return_value = pd.DataFrame([{
            '日期': '20260611',
            '收盤價': '50.00',
        }])
        mock_db_class.side_effect = [main_db, price_db]

        summary = self.service.get_stock_chip_summary("2330", 5)

        self.assertEqual(summary['accumulated_net'], 0)
        self.assertEqual(summary['estimated_event_count'], 0)
        self.assertEqual(summary['unavailable_event_count'], 1)
        self.assertIn(
            "⚠️ SQLite 使用 immutable 唯讀快照，可能只包含較舊的已提交資料。",
            summary['risk_reasons'],
        )

    def test_unavailable_row_does_not_poison_observed_portfolio_flow(self):
        df = pd.DataFrame([
            {
                '日期': '20260611',
                '分點名稱': 'branch_observed',
                '買進股數': 600000,
                '賣出股數': 0,
                '買賣超股數': 600000,
                'lots_observed': True,
                'amount_observed': False,
            },
            {
                '日期': '20260611',
                '分點名稱': 'branch_unavailable',
                '買進股數': None,
                '賣出股數': None,
                '買賣超股數': None,
                '買進金額千元': None,
                '賣出金額千元': None,
                '買賣超金額千元': None,
                'lots_observed': False,
                'amount_observed': False,
            },
        ])

        summary = self.service._aggregate_flow_dataframe(
            df,
            "2330",
            5,
            ["20260611"],
        )

        self.assertEqual(summary['accumulated_net'], 600000)
        self.assertEqual(summary['risk_level'], 'bullish')
        self.assertTrue(summary['lots_available'])
        self.assertEqual(summary['observed_event_count'], 1)
        self.assertEqual(summary['estimated_event_count'], 0)
        self.assertEqual(summary['unavailable_event_count'], 1)
        self.assertEqual(summary['lots_coverage_ratio'], Decimal('0.5'))


if __name__ == '__main__':
    unittest.main()
