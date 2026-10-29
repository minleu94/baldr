"""驗證月營收 degraded／缺值／缺公告時間清楚顯示，且該股票不參與建議推薦。

覆蓋：
1. UI 報告層：StockResearchReportView 與輔助函數對月營收缺值明確顯示「缺值」，
   對缺公告時間明確顯示「缺公告時間」，並於 tooltip 完整註記。
2. 存取提供者層：FundamentalSQLiteProvider 在 PIT 查詢時排除未映射或 degraded 無公告日列，
   確保歷史特徵不會洩漏不合規資料。
3. 推薦服務層：RecommendationService 在啟用月營收 YoY 篩選時，
   僅具 degraded 舊快照或缺月營收之股票以 fundamental_revenue_yoy_missing 排除，
   絕不進入推薦名單。
4. 產品契約邊界：當推薦模式為純技術指標（不要求月營收門檻）時，依既有契約
   不強制請求月營收，正常評估技術分數。
5. 推薦呈現層：RecommendationView 篩選清單與 presenter 明確將
   fundamental_revenue_yoy_missing 翻譯為「月營收缺值或缺公告時間」並詳細說明排除理由。
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication, QTableView

from app_module.recommendation_service import RecommendationService
from app_module.stock_research_report_dtos import (
    StockFundamentalObservationDTO,
    StockResearchReportDTO,
)
from data_module.fundamental_schema import apply_fundamental_schema
from data_module.fundamental_sqlite_provider import FundamentalSQLiteProvider
from tests.test_recommendation_fundamental_filters import (
    _FakeMarketFrameProvider,
    _write_formal_mapping,
    build_recommendation_test_preparer,
)
from ui_qt.views.recommendation.presenter import screening_research_summary
from ui_qt.views.recommendation_view import (
    _SCREENING_REASON_DISPLAY_LABELS,
    _screening_code_display,
)
from ui_qt.views.stock_research_report_view import (
    StockResearchReportView,
    _fundamental_basis_tooltip,
    _metric_text,
)


def test_ui_monthly_revenue_displays_missing_value_and_missing_announcement_date():
    """驗證 UI 對缺值顯示「缺值」，對缺公告時間顯示「缺公告時間」，並在 tooltip 正確標註。"""
    app = QApplication.instance() or QApplication([])

    obs_missing_both = StockFundamentalObservationDTO(
        kind="monthly_revenue",
        label="月營收",
        metric_name="revenue",
        market="TWSE",
        period="2026-08",
        as_of_date="2026-08-31",
        announced_date="",
        available_at="2026-10-30T00:00:00+08:00",
        value=None,
        unit="千元",
        quality="degraded",
        period_basis="single_month",
        basis_verified=False,
    )

    obs_normal = StockFundamentalObservationDTO(
        kind="monthly_revenue",
        label="月營收",
        metric_name="revenue",
        market="TWSE",
        period="2026-07",
        as_of_date="2026-07-31",
        announced_date="2026-08-10",
        available_at="2026-10-30T00:00:00+08:00",
        value=Decimal("1500"),
        unit="千元",
        quality="observed",
        period_basis="single_month",
        basis_verified=True,
    )

    # 1. 驗證 helper 函數
    assert _metric_text(obs_missing_both) == "缺值"
    assert "1,500" in _metric_text(obs_normal)

    tooltip_missing = _fundamental_basis_tooltip(obs_missing_both)
    assert "數值狀態：缺值" in tooltip_missing
    assert "公告時間：缺公告時間" in tooltip_missing

    tooltip_normal = _fundamental_basis_tooltip(obs_normal)
    assert "數值狀態：缺值" not in tooltip_normal
    assert "公告時間：2026-08-10" in tooltip_normal

    # 2. 驗證表格渲染與欄位
    view = StockResearchReportView(SimpleNamespace())
    report = StockResearchReportDTO(stock_code="6884", fundamentals=(obs_missing_both, obs_normal))
    view._render_fundamental(report)

    table = view.findChild(QTableView, "fundamentalMonthlyRevenueTable")
    assert table is not None
    model = table.model()
    assert model.rowCount() == 2
    assert model.columnCount() == 5

    # 驗證標頭包含「公告日」
    headers = [model.headerData(col, table.horizontalHeader().orientation()) for col in range(5)]
    assert headers == ["項目", "值／原披露單位", "期間", "公告日", "資料可得時間"]

    # 驗證第 0 列 (缺值與缺公告日)
    assert model.index(0, 1).data() == "缺值"
    assert model.index(0, 2).data() == "2026-08"
    assert model.index(0, 3).data() == "缺公告時間"

    # 驗證第 1 列 (正常有值有公告日)
    assert "1,500" in model.index(1, 1).data()
    assert model.index(1, 2).data() == "2026-07"
    assert model.index(1, 3).data() == "2026-08-10"

    view.close()


def test_fundamental_sqlite_provider_excludes_degraded_unmapped_rows(tmp_path: Path):
    """驗證 FundamentalSQLiteProvider 在 PIT reader 下會排除 unmapped 或 degraded 缺公告列。"""
    db_file = tmp_path / "test.db"
    mapping_file = tmp_path / "availability.csv"

    with sqlite3.connect(db_file) as conn:
        apply_fundamental_schema(conn)

        # 2330: observed, 具公告日, 且已 mapping
        conn.execute(
            """
            INSERT INTO fundamental_monthly_revenues (
                stock_code, period, as_of_date, announced_date, available_date,
                revenue, source, source_version, quality
            ) VALUES
            ('2330', '2026-06', '2026-06-30', '2026-07-10', '2026-07-10', '100.0', 'twse.monthly_revenue_announcement', 'v1', 'observed')
            """
        )

        # 4130: degraded, announced_date 為 NULL, 無 mapping
        conn.execute(
            """
            INSERT INTO fundamental_monthly_revenues (
                stock_code, period, as_of_date, announced_date, available_date,
                revenue, source, source_version, quality
            ) VALUES
            ('4130', '2026-04', '2026-04-30', NULL, '2026-06-18', '50.0', 'mops-static-snapshot', 'v1', 'degraded')
            """
        )

        # 6806: 1 筆 observed (有 mapping)，1 筆 degraded (無 mapping, NULL announced_date)
        conn.execute(
            """
            INSERT INTO fundamental_monthly_revenues (
                stock_code, period, as_of_date, announced_date, available_date,
                revenue, source, source_version, quality
            ) VALUES
            ('6806', '2026-04', '2026-04-30', '2026-05-15', '2026-06-18', '1052473.0', 'twse.monthly_revenue_announcement', 'v1', 'observed'),
            ('6806', '2026-02', '2026-02-28', NULL, '2026-06-18', '800000.0', 'mops-static-snapshot', 'v1', 'degraded')
            """
        )

    # 僅為 2330 與 6806/2026-04 提供 availability mapping
    _write_formal_mapping(
        mapping_file,
        [
            ("2330", "2026-06", "2026-06-30", "2026-07-10", "2026-07-10", "twse.monthly_revenue_announcement", "v1", "formal-availability.v2", "official_announcement", "a" * 64, "1", ""),
            ("6806", "2026-04", "2026-04-30", "2026-05-15", "2026-06-18", "twse.monthly_revenue_announcement", "v1", "formal-availability.v2", "official_announcement", "b" * 64, "1", ""),
        ],
    )

    provider = FundamentalSQLiteProvider(db_file, monthly_revenue_availability_file=mapping_file)

    # 4130 全部 degraded 且 unmapped，應回傳 0 筆
    res_4130 = provider.load_monthly_revenues(stock_code="4130", decision_date=datetime.date(2026, 7, 1))
    assert len(res_4130) == 0

    # 6806 degraded 列被排除，僅回傳 mapped observed 的 2026-04 1 筆
    res_6806 = provider.load_monthly_revenues(stock_code="6806", decision_date=datetime.date(2026, 7, 1))
    assert len(res_6806) == 1
    assert res_6806[0].period == "2026-04"
    assert res_6806[0].revenue == Decimal("1052473.0")

    # 2330 回傳 1 筆
    res_2330 = provider.load_monthly_revenues(stock_code="2330", decision_date=datetime.date(2026, 7, 15))
    assert len(res_2330) == 1
    assert res_2330[0].period == "2026-06"


def test_recommendation_service_excludes_degraded_and_missing_revenue_stocks(test_config):
    """驗證 RecommendationService 在啟用月營收 YoY 門檻時，缺資料或 degraded 股票被完全排除且不推薦。"""
    with sqlite3.connect(test_config.db_file) as conn:
        apply_fundamental_schema(conn)

        # 插入 PE 測試資料：2330 PE=12, 4130 PE=10, 9999 PE=10 (門檻設 15，均非因 PE 排除)
        for code, pe_val in (("2330", "12.0"), ("4130", "10.0"), ("9999", "10.0")):
            conn.execute(
                """
                INSERT INTO fundamental_valuation_metrics(
                    stock_code, as_of_date, available_date, metric_name, value,
                    industry, industry_percentile_bp, source, source_version, quality
                ) VALUES (?, '2026-06-30', '2026-07-01', 'pe', ?, NULL, NULL, 'test', 'v1', 'observed')
                """,
                (code, pe_val),
            )

        # 2330: 合格月營收 (今年 108，去年 100，YoY = 8% > 5%)
        conn.execute(
            """
            INSERT INTO fundamental_monthly_revenues(
                stock_code, period, as_of_date, announced_date, available_date,
                revenue, source, source_version, quality
            ) VALUES
            ('2330', '2026-06', '2026-06-30', '2026-07-10', '2026-07-10', '108.0', 'mops.monthly_revenue_static_snapshot', 'test-snapshot', 'observed'),
            ('2330', '2025-06', '2025-06-30', '2025-07-10', '2025-07-10', '100.0', 'mops.monthly_revenue_static_snapshot', 'test-snapshot', 'observed')
            """
        )

        # 4130: 只有 degraded 舊快照列，無 announced_date，且不在 mapping 中
        conn.execute(
            """
            INSERT INTO fundamental_monthly_revenues(
                stock_code, period, as_of_date, announced_date, available_date,
                revenue, source, source_version, quality
            ) VALUES
            ('4130', '2026-06', '2026-06-30', NULL, '2026-06-18', '50.0', 'mops-static-snapshot', 'v1', 'degraded'),
            ('4130', '2025-06', '2025-06-30', NULL, '2026-06-18', '50.0', 'mops-static-snapshot', 'v1', 'degraded')
            """
        )
        # 9999: 完全無月營收紀錄

    _write_formal_mapping(
        test_config.monthly_revenue_availability_file,
        [
            ("2330", "2026-06", "2026-06-30", "2026-07-10", "2026-07-10", "twse.monthly_revenue_announcement", "test-formal-v2", "formal-availability.v2", "official_announcement", "a" * 64, "1", ""),
            ("2330", "2025-06", "2025-06-30", "2025-07-10", "2025-07-10", "twse.monthly_revenue_announcement", "test-formal-v2", "formal-availability.v2", "official_announcement", "b" * 64, "1", ""),
        ],
    )

    # 模擬 20 天市場行情 (漲幅% 1.5, 成交量變化率% 10.0，使 2330 通過技術過濾)
    rows = []
    codes = [("2330", "台積電"), ("4130", "健亞"), ("9999", "無資料股")]
    for code, name in codes:
        for i in range(20):
            date_val = pd.Timestamp("2026-07-16") - pd.Timedelta(days=(19 - i))
            rows.append({
                "日期": date_val,
                "證券代號": code,
                "證券名稱": name,
                "漲幅%": 1.5,
                "成交量": 50000,
                "收盤價": 100.0,
                "成交量變化率%": 10.0,
            })
    mock_df = pd.DataFrame(rows)

    config = {
        "filters": {
            "pe_ratio_max": 15.0,
            "monthly_revenue_yoy_min": 5.0,
            "volume_change_min_percent": 0.0,
        },
        "ranking": {
            "weights": {"漲幅%": 100},
        },
    }

    provider = _FakeMarketFrameProvider(mock_df)
    service = RecommendationService(
        config=test_config,
        market_data_provider=provider,
        input_preparer=build_recommendation_test_preparer(test_config, market_data_provider=provider),
    )

    result = service.run_recommendation(config=config, as_of_date="2026-07-16")

    # 驗證只有 2330 進入推薦結果
    recommended_codes = {rec.stock_code for rec in result}
    assert recommended_codes == {"2330"}

    # 驗證 screening matrix 紀錄
    matrix = service.last_screening_matrix
    rows_by_stock = {row["stock_code"]: row for row in matrix}

    # 4130 (只有 degraded 數據，PIT 回傳空) 應因營收 YoY 缺失被排除
    assert "4130" in rows_by_stock
    row_4130 = rows_by_stock["4130"]
    assert row_4130["status"] == "skipped"
    assert "fundamental_revenue_yoy_missing" in row_4130["reason_codes"]
    assert row_4130["quality"] == "missing"

    # 9999 (完全無數據) 亦因營收 YoY 缺失被排除
    assert "9999" in rows_by_stock
    row_9999 = rows_by_stock["9999"]
    assert row_9999["status"] == "skipped"
    assert "fundamental_revenue_yoy_missing" in row_9999["reason_codes"]
    assert row_9999["quality"] == "missing"


def test_recommendation_pure_technical_mode_without_monthly_revenue_filter_allows_stocks(test_config):
    """驗證產品契約邊界：當推薦模式為純技術/量能（未啟用 monthly_revenue_yoy_min）時，不要求月營收。"""
    rows = []
    codes = [("2330", "台積電"), ("4130", "健亞")]
    for code, name in codes:
        for i in range(20):
            date_val = pd.Timestamp("2026-07-16") - pd.Timedelta(days=(19 - i))
            rows.append({
                "日期": date_val,
                "證券代號": code,
                "證券名稱": name,
                "漲幅%": 2.0,
                "成交量": 50000,
                "收盤價": 100.0,
                "成交量變化率%": 10.0,
            })
    mock_df = pd.DataFrame(rows)

    # 不指定 monthly_revenue_yoy_min (純技術模式)
    technical_only_config = {
        "filters": {
            "volume_change_min_percent": 0.0,
        },
        "ranking": {
            "weights": {"漲幅%": 100},
        },
    }

    provider = _FakeMarketFrameProvider(mock_df)
    service = RecommendationService(
        config=test_config,
        market_data_provider=provider,
        input_preparer=build_recommendation_test_preparer(test_config, market_data_provider=provider),
    )

    result = service.run_recommendation(config=technical_only_config, as_of_date="2026-07-16")

    # 在純技術模式下，兩檔皆滿足技術條件，均可入選（月營收不介入阻擋）
    recommended_codes = {rec.stock_code for rec in result}
    assert "2330" in recommended_codes
    assert "4130" in recommended_codes


def test_screening_matrix_and_presenter_display_fundamental_revenue_exclusion_reason():
    """驗證畫面呈現層：screening matrix 與 presenter 清楚顯示月營收缺漏排除原因與說明。"""
    # 1. 驗證 RecommendationView 之原因代碼翻譯
    label_missing = _screening_code_display(
        "fundamental_revenue_yoy_missing", _SCREENING_REASON_DISPLAY_LABELS
    )
    assert label_missing == "月營收缺值或缺公告時間（fundamental_revenue_yoy_missing）"

    label_below = _screening_code_display(
        "fundamental_revenue_yoy_below_min", _SCREENING_REASON_DISPLAY_LABELS
    )
    assert label_below == "月營收年增率未達門檻（fundamental_revenue_yoy_below_min）"

    # 2. 驗證 presenter screening_research_summary 詳細解說
    summary_missing = screening_research_summary({
        "原因代碼": "fundamental_revenue_yoy_missing",
        "原篩選狀態": "skipped",
        "觀測值": "missing",
        "要求值": "5.0",
    })
    assert "本次未入選：月營收缺值或缺少可驗證之官方公告時間" in summary_missing
    assert "該股票不參與推薦" in summary_missing
    assert "個人 H20" in summary_missing

    summary_below = screening_research_summary({
        "原因代碼": "月營收年增率未達門檻（fundamental_revenue_yoy_below_min）",
        "原篩選狀態": "skipped",
        "觀測值": "3.50",
        "要求值": "5.0",
    })
    assert "本次未入選：月營收年增率（YoY）未達策略門檻" in summary_below
    assert "3.50%" in summary_below
    assert "5.00%" in summary_below
