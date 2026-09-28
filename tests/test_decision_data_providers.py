import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from textwrap import dedent
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app_module.decision_data_providers import (
    SqliteFirstFrameProvider,
    industry_index_frame_provider,
    market_index_frame_provider,
)


def test_sqlite_first_provider_returns_query_snapshot_without_csv_access(tmp_path) -> None:
    expected = pd.DataFrame({"日期": [20260710], "收盤指數": [100]})
    db = MagicMock()
    db.execute_query.return_value = expected
    provider = SqliteFirstFrameProvider(
        SimpleNamespace(use_sqlite=True),
        table="market_indices",
        csv_paths=lambda _: (tmp_path / "must-not-exist.csv",),
        db_factory=MagicMock(return_value=db),
    )

    actual = provider()

    pd.testing.assert_frame_equal(actual, expected)
    assert actual is not expected
    db.execute_query.assert_called_once_with(
        "SELECT * FROM market_indices ORDER BY 日期 ASC;"
    )


def test_sqlite_first_provider_falls_back_to_first_existing_csv(tmp_path) -> None:
    fallback = tmp_path / "market.csv"
    pd.DataFrame({"日期": ["2026-07-10"], "收盤價": [100]}).to_csv(
        fallback, index=False, encoding="utf-8-sig"
    )
    db_factory = MagicMock(side_effect=RuntimeError("offline"))
    provider = SqliteFirstFrameProvider(
        SimpleNamespace(use_sqlite=True),
        table="market_indices",
        csv_paths=lambda _: (tmp_path / "missing.csv", fallback),
        db_factory=db_factory,
    )

    actual = provider()

    assert actual.to_dict("records") == [{"日期": "2026-07-10", "收盤價": 100}]


def _sqlite_disk_state(path: Path) -> dict[str, object]:
    sidecars = {}
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(f"{path}{suffix}")
        sidecars[suffix] = sidecar.read_bytes() if sidecar.exists() else None
    raw = path.read_bytes()
    return {
        "bytes": raw,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "header": raw[:100],
        "sidecars": sidecars,
    }


def _sqlite_state_for_receipt(path: Path) -> dict[str, object]:
    state = _sqlite_disk_state(path)
    sidecars = state["sidecars"]
    assert isinstance(sidecars, dict)
    return {
        "size_bytes": len(state["bytes"]),
        "sha256": state["sha256"],
        "header_hex": state["header"].hex(),
        "sidecars": {
            suffix: hashlib.sha256(content).hexdigest() if content is not None else None
            for suffix, content in sidecars.items()
        },
    }


def _record_dashboard_readonly_gate(section: str, result: dict[str, object]) -> None:
    receipt_value = os.environ.get("QA_DASHBOARD_READONLY_GATE_RECEIPT")
    if not receipt_value:
        return
    receipt_path = Path(receipt_value)
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    else:
        receipt = {
            "schema_version": "dashboard-readonly-small-db-gate.v1",
            "focused_command": os.environ.get("QA_DASHBOARD_READONLY_GATE_COMMAND", "unspecified"),
            "sections": {},
        }
    sections = receipt.setdefault("sections", {})
    if section in sections:
        raise AssertionError(f"重複的唯讀 gate 收據區段：{section}")
    sections[section] = result
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _create_provider_sqlite(path: Path, *, include_indexes: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        if include_indexes:
            connection.execute(
                "CREATE TABLE market_indices (日期 TEXT, 收盤指數 REAL)"
            )
            connection.execute(
                "CREATE TABLE industry_indices (日期 TEXT, 產業名稱 TEXT, 指數 REAL)"
            )
            connection.execute(
                "INSERT INTO market_indices VALUES ('20260925', 22000.0)"
            )
            connection.execute(
                "INSERT INTO industry_indices VALUES ('20260925', '半導體', 1200.0)"
            )
        connection.execute(
            "CREATE TABLE daily_prices (日期 TEXT, 證券代號 TEXT, 收盤價 REAL)"
        )
        connection.execute(
            "CREATE TABLE technical_indicators (日期 TEXT, 證券代號 TEXT, RSI REAL)"
        )
        connection.execute(
            "INSERT INTO daily_prices VALUES ('20260925', '2330', 1000.0)"
        )
        connection.execute(
            "INSERT INTO technical_indicators VALUES ('20260925', '2330', 60.0)"
        )


def _provider_config(tmp_path: Path, db_path: Path) -> SimpleNamespace:
    meta_data_dir = tmp_path / "meta_data"
    return SimpleNamespace(
        use_sqlite=True,
        db_file=db_path,
        market_index_file=meta_data_dir / "market_index.csv",
        industry_index_file=meta_data_dir / "industry_index.csv",
        meta_data_dir=meta_data_dir,
        stock_data_file=meta_data_dir / "stock_data_whole.csv",
        all_stocks_data_file=meta_data_dir / "all_stocks_data.csv",
        monthly_revenue_availability_file=meta_data_dir / "monthly_revenue_availability.csv",
        pit_sector_membership_paths=None,
        pit_sector_membership_path=None,
        pit_market_scope=None,
    )


def test_default_index_providers_read_existing_sqlite_without_mutation(tmp_path) -> None:
    db_path = tmp_path / "sqlite" / "twstock.db"
    _create_provider_sqlite(db_path)
    config = _provider_config(tmp_path, db_path)
    before = _sqlite_disk_state(db_path)

    market = market_index_frame_provider(config)()
    industry = industry_index_frame_provider(config)()

    assert market.to_dict("records") == [{"日期": "20260925", "收盤指數": 22000.0}]
    assert industry.to_dict("records") == [
        {"日期": "20260925", "產業名稱": "半導體", "指數": 1200.0}
    ]
    assert _sqlite_disk_state(db_path) == before


def test_decision_index_providers_reject_immutable_fallback_and_keep_csv_unknown(
    tmp_path, monkeypatch, caplog
) -> None:
    from app_module.sqlite_read_only import ReadOnlySQLiteManager
    from data_module.industry_mapper_data_provider import (
        INDUSTRY_INDEX_SOURCE_OBSERVATION_ATTR,
    )

    db_path = tmp_path / "sqlite" / "twstock.db"
    _create_provider_sqlite(db_path)
    config = _provider_config(tmp_path, db_path)
    config.market_index_file.parent.mkdir(parents=True, exist_ok=True)
    config.market_index_file.write_text(
        "日期,收盤指數\n2026-09-26,22100\n", encoding="utf-8-sig"
    )
    config.industry_index_file.write_text(
        "日期,產業名稱,指數\n2026-09-26,半導體,1210\n", encoding="utf-8-sig"
    )
    before = _sqlite_disk_state(db_path)

    def immutable_query(self, query):
        self.last_read_mode = "immutable_fallback"
        if "market_indices" in query:
            return pd.DataFrame({"日期": ["20260925"], "收盤指數": [99999]})
        return pd.DataFrame(
            {"日期": ["20260925"], "產業名稱": ["半導體"], "指數": [99999]}
        )

    monkeypatch.setattr(ReadOnlySQLiteManager, "execute_query", immutable_query)

    market = market_index_frame_provider(config)()
    industry = industry_index_frame_provider(config)()

    assert market.to_dict("records") == [
        {"日期": "2026-09-26", "收盤指數": 22100}
    ]
    assert industry.to_dict("records") == [
        {"日期": "2026-09-26", "產業名稱": "半導體", "指數": 1210}
    ]
    observation = industry.attrs[INDUSTRY_INDEX_SOURCE_OBSERVATION_ATTR]
    assert observation["status"] == "unknown"
    assert observation["pit_eligible"] is False
    assert observation["available_at"] is None
    assert "immutable fallback" in caplog.text
    assert _sqlite_disk_state(db_path) == before


def test_decision_index_providers_return_empty_when_immutable_fallback_has_no_csv(
    tmp_path, monkeypatch
) -> None:
    from app_module.sqlite_read_only import ReadOnlySQLiteManager

    db_path = tmp_path / "sqlite" / "twstock.db"
    _create_provider_sqlite(db_path)
    config = _provider_config(tmp_path, db_path)
    before = _sqlite_disk_state(db_path)

    def immutable_query(self, _query):
        self.last_read_mode = "immutable_fallback"
        return pd.DataFrame({"日期": ["20260925"], "收盤指數": [22000]})

    monkeypatch.setattr(ReadOnlySQLiteManager, "execute_query", immutable_query)

    assert market_index_frame_provider(config)().empty
    assert industry_index_frame_provider(config)().empty
    assert _sqlite_disk_state(db_path) == before


def test_missing_index_tables_fall_back_to_csv_without_sqlite_mutation(tmp_path) -> None:
    db_path = tmp_path / "sqlite" / "twstock.db"
    _create_provider_sqlite(db_path, include_indexes=False)
    config = _provider_config(tmp_path, db_path)
    config.market_index_file.parent.mkdir(parents=True, exist_ok=True)
    config.market_index_file.write_text(
        "日期,收盤指數\n2026-09-25,22000\n", encoding="utf-8-sig"
    )
    config.industry_index_file.write_text(
        "日期,產業名稱,指數\n2026-09-25,半導體,1200\n", encoding="utf-8-sig"
    )
    before = _sqlite_disk_state(db_path)

    market = market_index_frame_provider(config)()
    industry = industry_index_frame_provider(config)()

    assert market.to_dict("records") == [
        {"日期": "2026-09-25", "收盤指數": 22000}
    ]
    assert industry.to_dict("records") == [
        {"日期": "2026-09-25", "產業名稱": "半導體", "指數": 1200}
    ]
    assert _sqlite_disk_state(db_path) == before


def test_default_composition_uses_read_only_index_and_recommendation_readers(
    tmp_path,
) -> None:
    from app_module.decision_service_composition import (
        build_decision_service_composition,
    )
    from app_module.recommendation_market_data_provider import (
        DefaultRecommendationMarketDataProvider,
    )

    db_path = tmp_path / "sqlite" / "twstock.db"
    _create_provider_sqlite(db_path)
    config = _provider_config(tmp_path, db_path)
    before_receipt = _sqlite_state_for_receipt(db_path)

    class Mapper:
        def __init__(self, _config, *, industry_index_provider, companies_provider):
            self.industry_frame = industry_index_provider()
            self.companies_frame = companies_provider()

    class StockScreener:
        def __init__(self, *_args, **_kwargs):
            pass

    class ScreeningService:
        def __init__(self, *_args, **_kwargs):
            pass

    class MarketRegimeDetector:
        pass

    class RegimeService:
        def __init__(self, _config, *, market_frame_provider, **_kwargs):
            self.market_frame_provider = market_frame_provider

    class RecommendationService:
        def __init__(self, _config, *, input_preparer, **_kwargs):
            self.input_preparer = input_preparer

    dependencies = {
        "IndustryMapper": Mapper,
        "StockScreener": StockScreener,
        "ScreeningService": ScreeningService,
        "MarketRegimeDetector": MarketRegimeDetector,
        "RegimeService": RegimeService,
        "RecommendationService": RecommendationService,
    }
    before = _sqlite_disk_state(db_path)

    composition = build_decision_service_composition(
        config=config,
        dependencies=dependencies,
    )
    market_index = composition.regime_service.market_frame_provider()
    input_session = composition.recommendation_service.input_preparer.begin(config)
    recommendation_market = input_session.load_market_frame(cutoff=None)

    assert composition.industry_mapper.industry_frame["產業名稱"].tolist() == ["半導體"]
    assert market_index["收盤指數"].tolist() == [22000.0]
    assert isinstance(
        composition.recommendation_service.input_preparer.market_data_provider,
        DefaultRecommendationMarketDataProvider,
    )
    assert recommendation_market[["日期", "證券代號"]].to_dict("records") == [
        {"日期": "20260925", "證券代號": "2330"}
    ]
    after = _sqlite_disk_state(db_path)
    assert after == before
    _record_dashboard_readonly_gate(
        "recommendation_input_and_index_providers",
        {
            "database_path": str(db_path.resolve()),
            "route": "decision_service_composition -> RecommendationInputSession.load_market_frame -> HistoricalRecommendationMarketFrameProvider",
            "result": "PASS",
            "before": before_receipt,
            "after": _sqlite_state_for_receipt(db_path),
        },
    )


def test_mainwindow_offscreen_startup_keeps_configured_sqlite_unchanged(
    tmp_path,
) -> None:
    db_path = tmp_path / "data_root" / "_test" / "sqlite" / "twstock.db"
    _create_provider_sqlite(db_path)
    companies_path = tmp_path / "data_root" / "_test" / "meta_data" / "companies.csv"
    companies_path.parent.mkdir(parents=True, exist_ok=True)
    companies_path.write_text(
        "stock_id,stock_name,industry_category\n2330,台積電,半導體\n",
        encoding="utf-8-sig",
    )
    before = _sqlite_disk_state(db_path)
    code = dedent(
        """
        import hashlib, json, os
        from pathlib import Path
        from PySide6.QtCore import QEventLoop, QTimer, Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from ui_qt.main import MainWindow
        from ui_qt.views.decision_quality_view import DecisionQualityView
        from ui_qt.views.live_research_gap_view import LiveResearchGapView
        from ui_qt.views.signal_decay_view import SignalDecayView
        from ui_qt.views.portfolio_view import PortfolioView
        from ui_qt.views.decision_desk_view import DecisionDeskView

        database = Path(os.environ['DATA_ROOT']) / '_test' / 'sqlite' / 'twstock.db'
        portfolio_directory = Path(os.environ['OUTPUT_ROOT']) / '_test' / 'portfolio'
        portfolio_directory.mkdir(parents=True, exist_ok=True)
        (portfolio_directory / 'trades.jsonl').write_text(
            json.dumps({
                'trade_id': 'readonly-gate-buy-2330',
                'portfolio_id': 'default',
                'stock_code': '2330',
                'stock_name': '台積電',
                'side': 'buy',
                'quantity': 100,
                'price': 900,
                'trade_date': '2026-09-25',
                'fees': 0,
                'taxes': 0,
                'currency': 'TWD',
                'schema_version': '4.1',
            }, ensure_ascii=False) + '\\n',
            encoding='utf-8',
        )
        def state(path):
            raw = path.read_bytes()
            sidecars = {}
            for suffix in ('-wal', '-shm', '-journal'):
                item = Path(f'{path}{suffix}')
                sidecars[suffix] = hashlib.sha256(item.read_bytes()).hexdigest() if item.exists() else None
            return {'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw), 'header': raw[:100].hex(), 'sidecars': sidecars}

        before = state(database)
        app = QApplication(['mainwindow-readonly-startup-test'])
        window = MainWindow(policy_config_path=str(Path(os.environ['OUTPUT_ROOT']) / '_test' / 'policy' / 'personal_use_policy.json'))
        refreshed = []
        for view_type in (DecisionQualityView, SignalDecayView, LiveResearchGapView):
            views = window.findChildren(view_type)
            if not views:
                raise AssertionError(f'MainWindow did not compose {view_type.__name__}')
            for view in views:
                view.async_refresh = False
                view.refresh_button.click()
                refreshed.append(view.__class__.__name__)
        portfolio_view = window.portfolio_view
        if not isinstance(portfolio_view, PortfolioView):
            raise AssertionError('MainWindow did not compose PortfolioView')
        if not portfolio_view.btn_refresh.isEnabled():
            wait_loop = QEventLoop()
            poll = QTimer()
            poll.setInterval(10)
            poll.timeout.connect(
                lambda: wait_loop.quit()
                if portfolio_view.btn_refresh.isEnabled()
                else None
            )
            timeout = QTimer()
            timeout.setSingleShot(True)
            timeout.timeout.connect(wait_loop.quit)
            poll.start()
            timeout.start(30000)
            wait_loop.exec()
            poll.stop()
            app.processEvents()
            if not portfolio_view.btn_refresh.isEnabled():
                raise TimeoutError('initial portfolio refresh action did not re-enable')
        portfolio_view.async_refresh = False
        portfolio_view.btn_refresh.click()
        if portfolio_view._last_portfolio_dto is None or len(portfolio_view._last_portfolio_dto.positions) != 1:
            raise AssertionError('isolated saved position was not read by PortfolioView')
        window.show()
        app.processEvents()
        row_index = portfolio_view.positions_model.index(0, 0)
        row_rect = portfolio_view.positions_table.visualRect(row_index)
        if not row_rect.isValid():
            raise AssertionError('saved holding row is not visible in PortfolioView')
        QTest.mouseClick(
            portfolio_view.positions_table.viewport(),
            Qt.MouseButton.LeftButton,
            pos=row_rect.center(),
        )
        app.processEvents()
        if portfolio_view.selected_stock_code != '2330':
            raise AssertionError('clicking the saved holding did not select its stock')
        window.market_tabs.setCurrentWidget(window.decision_desk_view)
        decision_desk_view = window.decision_desk_view
        if not isinstance(decision_desk_view, DecisionDeskView):
            raise AssertionError('MainWindow did not compose DecisionDeskView')
        decision_desk_view.async_refresh = False
        decision_desk_view.refresh_btn.click()
        refreshed.extend(['PortfolioView', 'DecisionDeskView'])
        app.processEvents()
        after = state(database)
        print('MAINWINDOW_SQLITE_GATE=' + json.dumps({'before': before, 'after': after, 'refreshed': refreshed, 'held_position_count': len(portfolio_view._last_portfolio_dto.positions), 'decision_desk_status': decision_desk_view.overall_status_label.text()}, sort_keys=True))
        window.setAttribute(__import__('PySide6.QtCore', fromlist=['Qt']).Qt.WidgetAttribute.WA_DeleteOnClose)
        window.close()
        app.processEvents()
        """
    )
    env = os.environ.copy()
    env.update(
        {
            "DATA_ROOT": str(tmp_path / "data_root"),
            "OUTPUT_ROOT": str(tmp_path / "output_root"),
            "PROFILE": "test",
            "QT_QPA_PLATFORM": "offscreen",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    for key in (
        "PIT_SECTOR_MEMBERSHIP_PATH",
        "PIT_SECTOR_MEMBERSHIP_RAW_ROOT",
        "PIT_SECTOR_MEMBERSHIP_CLOCK_MANIFEST_PATH",
        "PIT_SECTOR_MEMBERSHIP_UNIVERSE_SYMBOLS_PATH",
        "PIT_SECTOR_MEMBERSHIP_UNIVERSE_IDENTITY_PATH",
        "PIT_SECTOR_MEMBERSHIP_TAXONOMY_IDENTITY_PATH",
        "RESEARCH_CONSOLE_PROJECTION",
        "P0_SOURCE_CONTROL_CENTER_AUDIT",
        "P0_SOURCE_CONTROL_CENTER_DECISIONS",
    ):
        env.pop(key, None)

    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    result_lines = [
        line.removeprefix("MAINWINDOW_SQLITE_GATE=")
        for line in completed.stdout.splitlines()
        if line.startswith("MAINWINDOW_SQLITE_GATE=")
    ]
    assert len(result_lines) == 1, completed.stdout + completed.stderr
    observed = json.loads(result_lines[0])
    assert observed["before"] == observed["after"]
    assert set(observed["refreshed"]) == {
        "DecisionQualityView",
        "DecisionDeskView",
        "PortfolioView",
        "SignalDecayView",
        "LiveResearchGapView",
    }
    assert observed["held_position_count"] == 1
    assert _sqlite_disk_state(db_path) == before
    _record_dashboard_readonly_gate(
        "mainwindow_startup_and_evidence_refresh",
        {
            "database_path": str(db_path.resolve()),
            "result": "PASS",
            "before": observed["before"],
            "after": observed["after"],
            "refreshed_views": sorted(observed["refreshed"]),
            "held_position_count": observed["held_position_count"],
            "decision_desk_status": observed["decision_desk_status"],
            "environment": {
                "DATA_ROOT": env["DATA_ROOT"],
                "OUTPUT_ROOT": env["OUTPUT_ROOT"],
                "PROFILE": env["PROFILE"],
                "QT_QPA_PLATFORM": env["QT_QPA_PLATFORM"],
            },
            "child_argv": [sys.executable, "-c", code],
            "child_return_code": completed.returncode,
        },
    )


def test_dashboard_readonly_sources_report_missing_db_without_creating_it(tmp_path) -> None:
    from app_module.decision_quality_dashboard_dtos import DecisionQualityDashboardRequest
    from app_module.decision_quality_dashboard_service import create_decision_quality_dashboard_service
    from app_module.live_research_gap_dashboard_dtos import LiveResearchGapDashboardRequest
    from app_module.live_research_gap_dashboard_service import create_live_research_gap_dashboard_service
    from app_module.signal_decay_dashboard_dtos import SignalDecayDashboardRequest
    from app_module.signal_decay_dashboard_service import create_signal_decay_dashboard_service

    default_db_path = tmp_path / "default" / "sqlite" / "twstock.db"
    _create_provider_sqlite(default_db_path)
    default_before = _sqlite_disk_state(default_db_path)
    db_path = tmp_path / "missing" / "sqlite" / "twstock.db"
    output_root = tmp_path / "output"
    config = SimpleNamespace(db_file=default_db_path, output_root=output_root)
    checks = (
        (
            create_live_research_gap_dashboard_service(config, db_path=db_path),
            LiveResearchGapDashboardRequest(),
        ),
        (
            create_signal_decay_dashboard_service(config, db_path=db_path),
            SignalDecayDashboardRequest(),
        ),
        (
            create_decision_quality_dashboard_service(config, db_path=db_path),
            DecisionQualityDashboardRequest(),
        ),
    )

    for service, request in checks:
        result = service.load_dashboard(request)
        assert result.rows == ()
        assert result.diagnostics == ("sqlite_database_missing",)
        assert "不會建立資料庫或初始化 schema" in result.empty_state_message

    assert not db_path.exists()
    assert not db_path.parent.exists()
    assert not output_root.exists()
    assert _sqlite_disk_state(default_db_path) == default_before


def test_dashboard_readonly_sources_report_missing_tables_without_mutation(tmp_path) -> None:
    from app_module.decision_quality_dashboard_dtos import DecisionQualityDashboardRequest
    from app_module.decision_quality_dashboard_service import create_decision_quality_dashboard_service
    from app_module.live_research_gap_dashboard_dtos import LiveResearchGapDashboardRequest
    from app_module.live_research_gap_dashboard_service import create_live_research_gap_dashboard_service
    from app_module.signal_decay_dashboard_dtos import SignalDecayDashboardRequest
    from app_module.signal_decay_dashboard_service import create_signal_decay_dashboard_service

    db_path = tmp_path / "sqlite" / "twstock.db"
    _create_provider_sqlite(db_path)
    before = _sqlite_disk_state(db_path)
    config = SimpleNamespace(db_file=db_path, output_root=tmp_path / "output")
    checks = (
        (
            create_live_research_gap_dashboard_service(config, db_path=db_path),
            LiveResearchGapDashboardRequest(),
        ),
        (
            create_signal_decay_dashboard_service(config, db_path=db_path),
            SignalDecayDashboardRequest(),
        ),
        (
            create_decision_quality_dashboard_service(config, db_path=db_path),
            DecisionQualityDashboardRequest(),
        ),
    )

    for service, request in checks:
        result = service.load_dashboard(request)
        assert result.rows == ()
        assert result.diagnostics == ("sqlite_evidence_table_missing",)
        assert "不會建立資料庫或初始化 schema" in result.empty_state_message

    assert _sqlite_disk_state(db_path) == before


def test_readonly_evidence_repositories_reject_all_writes(tmp_path) -> None:
    from app_module.decision_quality_repository import DecisionQualityRepository
    from app_module.evidence_event_repository import EvidenceEventRepository
    from app_module.live_research_gap_repository import LiveResearchGapRepository
    from app_module.signal_decay_repository import SignalDecayRepository

    db_path = tmp_path / "existing.sqlite"
    _create_provider_sqlite(db_path)
    before = _sqlite_disk_state(db_path)
    config = SimpleNamespace(db_file=db_path)

    live = LiveResearchGapRepository(config, db_path=db_path, read_only=True)
    signal = SignalDecayRepository(config, db_path=db_path, read_only=True)
    quality = DecisionQualityRepository(config, db_path=db_path, read_only=True)
    events = EvidenceEventRepository(config, db_path=db_path, read_only=True)

    with pytest.raises(RuntimeError, match="read-only"):
        live.save_observation(None)
    with pytest.raises(RuntimeError, match="read-only"):
        signal.save_observation(None)
    with pytest.raises(RuntimeError, match="read-only"):
        quality.save_review(None)
    with pytest.raises(RuntimeError, match="read-only"):
        quality.create_action_item(review_id="", item_id="", description="")
    with pytest.raises(RuntimeError, match="read-only"):
        quality.mark_item_reviewed("missing")
    with pytest.raises(RuntimeError, match="read-only"):
        events.ensure_schema()
    with pytest.raises(RuntimeError, match="read-only"):
        events.insert_event(None)
    assert _sqlite_disk_state(db_path) == before


def test_dashboard_factories_preserve_existing_evidence_rows(tmp_path) -> None:
    from app_module.decision_quality_dashboard_dtos import DecisionQualityDashboardRequest
    from app_module.decision_quality_dashboard_service import create_decision_quality_dashboard_service
    from app_module.decision_quality_dtos import DecisionQualityItem, DecisionQualityReview
    from app_module.decision_quality_repository import DecisionQualityRepository
    from app_module.live_research_gap_dashboard_dtos import LiveResearchGapDashboardRequest
    from app_module.live_research_gap_dashboard_service import create_live_research_gap_dashboard_service
    from app_module.live_research_gap_dtos import LiveResearchGapObservation
    from app_module.live_research_gap_repository import LiveResearchGapRepository
    from app_module.signal_decay_dashboard_dtos import SignalDecayDashboardRequest
    from app_module.signal_decay_dashboard_service import create_signal_decay_dashboard_service
    from app_module.signal_decay_dtos import SignalDecayObservation
    from app_module.signal_decay_repository import SignalDecayRepository

    db_path = tmp_path / "sqlite" / "twstock.db"
    db_path.parent.mkdir(parents=True)
    config = SimpleNamespace(db_file=db_path, output_root=tmp_path / "output")
    LiveResearchGapRepository(config, db_path=db_path).save_observation(
        LiveResearchGapObservation(
            gap_id="gap-1", gap_hash="gap-hash-1", observation_date="2026-09-25",
            position_id="position-1", symbol="2330", portfolio_mode="simulated",
            source_type="recommendation", source_id="result-1",
        )
    )
    SignalDecayRepository(config, db_path=db_path).save_observation(
        SignalDecayObservation(
            decay_id="decay-1", decay_hash="decay-hash-1", observation_date="2026-09-25",
            signal_scope_type="event_type", signal_scope_id="breakout", decay_status="watch",
        )
    )
    DecisionQualityRepository(config, db_path=db_path).save_review(
        DecisionQualityReview(
            review_id="review-1", review_hash="review-hash-1", review_period_start="2026-09-01",
            review_period_end="2026-09-25", review_type="weekly",
        ),
        items=(DecisionQualityItem(item_id="item-1", review_id="review-1", item_type="missing_link"),),
    )
    before = _sqlite_disk_state(db_path)

    live = create_live_research_gap_dashboard_service(config, db_path=db_path).load_dashboard(
        LiveResearchGapDashboardRequest()
    )
    signal = create_signal_decay_dashboard_service(config, db_path=db_path).load_dashboard(
        SignalDecayDashboardRequest()
    )
    quality = create_decision_quality_dashboard_service(config, db_path=db_path).load_dashboard(
        DecisionQualityDashboardRequest()
    )

    assert [row.symbol for row in live.rows] == ["2330"]
    assert [row.signal_scope_id for row in signal.rows] == ["breakout"]
    assert [row.item_type for row in quality.rows] == ["missing_link"]
    assert _sqlite_disk_state(db_path) == before
