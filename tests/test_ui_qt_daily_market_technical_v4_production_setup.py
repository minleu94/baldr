"""驗證 full-N v4 產製設定、固定來源續跑與嚴格母體 JSON。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta
import json
import logging
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app_module.daily_market_technical_universe_v4_catalog import (
    DailyMarketTechnicalUniverseV4Catalog,
    DailyMarketTechnicalUniverseV4CatalogEntry,
)
from app_module.daily_market_technical_universe_v4_producer import (
    DailyMarketTechnicalUniverseV4ProductionRequest,
    produce_daily_market_technical_universe_v4,
)
from app_module.daily_market_technical_universe_v4_store import (
    DailyMarketTechnicalUniverseV4VerifiedState,
)
from app_module.personal_data_paths import to_internal_io_path
from data_module.config import TWStockConfig
from ui_qt.widgets.daily_market_technical_v4_production_setup import (
    DAILY_MARKET_TECHNICAL_V4_POPULATION_SETTINGS_SCHEMA,
    DailyMarketTechnicalV4ProductionSetupCancelled,
    DailyMarketTechnicalV4ProductionSetupError,
    DailyMarketTechnicalV4DeferredProductionSetup,
    ProductionSetupSummary,
    load_daily_market_technical_v4_population_settings,
    make_daily_market_technical_v4_deferred_setup_factory,
    make_daily_market_technical_v4_production_request_factory,
    parse_daily_market_technical_v4_decision_cutoff,
)


_TAIPEI = ZoneInfo("Asia/Taipei")
_DECISION_DATE = date(2026, 10, 6)


@pytest.fixture(scope="session", autouse=True)
def _qt_application() -> Any:
    """以 offscreen QApplication 驗證 factory 只能從 GUI 執行緒呼叫。"""

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    application = QApplication.instance()
    if application is None:
        application = QApplication([])
    return application


@pytest.fixture
def isolated_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    """將 TWStockConfig 的所有資料與輸出位置限制在 pytest 暫存根。"""

    for name in (
        "DATA_ROOT",
        "OUTPUT_ROOT",
        "PROFILE",
        "PERSONAL_DATA_ROOT",
        "PERSONAL_WATCHLIST_SOURCE",
        "PERSONAL_JOURNAL_ROOT",
        "PERSONAL_JOURNAL_MODE",
        "PERSONAL_STORE_ROOT",
        "PERSONAL_STORE_MODE",
        "PERSONAL_MODEL_POLICY_PATH",
        "OFFICIAL_CALENDAR_CACHE_PATH",
        "PIT_SECTOR_MEMBERSHIP_PATH",
        "PIT_SECTOR_MEMBERSHIP_RAW_ROOT",
        "PIT_SECTOR_MEMBERSHIP_CLOCK_MANIFEST_PATH",
        "PIT_SECTOR_MEMBERSHIP_UNIVERSE_SYMBOLS_PATH",
        "PIT_SECTOR_MEMBERSHIP_UNIVERSE_IDENTITY_PATH",
        "PIT_SECTOR_MEMBERSHIP_TAXONOMY_IDENTITY_PATH",
        "PIT_MEMBERSHIP_EXPECTED_CLASSIFICATION_VERSION",
        "PIT_MARKET_SCOPE",
    ):
        monkeypatch.delenv(name, raising=False)
    logger = logging.getLogger("data_module.config")
    existing_handlers = set(logger.handlers)
    config = TWStockConfig(
        data_root=tmp_path / "market_data",
        output_root=tmp_path / "configured_output",
        profile="prod",
    )
    created_handlers = [
        handler for handler in logger.handlers if handler not in existing_handlers
    ]
    try:
        yield config
    finally:
        for handler in created_handlers:
            logger.removeHandler(handler)
            handler.close()


class _FakeDialogs:
    """記錄同步對話框呼叫並回傳測試指定的使用者選擇。"""

    def __init__(
        self,
        *,
        settings_path: Path | None = None,
        cutoff: str | datetime | None = None,
        source_confirmed: bool = True,
        summary_confirmed: bool = True,
    ) -> None:
        self.settings_path = settings_path
        self.cutoff = cutoff
        self.source_confirmed = source_confirmed
        self.summary_confirmed = summary_confirmed
        self.events: list[str] = []
        self.source_paths: list[Path] = []
        self.summaries: list[ProductionSetupSummary] = []

    def choose_population_settings_file(self, parent: object | None) -> Path | None:
        self.events.append("choose_settings")
        return self.settings_path

    def request_decision_cutoff(
        self,
        parent: object | None,
        *,
        decision_date: date,
    ) -> str | datetime | None:
        self.events.append("choose_cutoff")
        return self.cutoff

    def confirm_source_database(
        self,
        parent: object | None,
        *,
        source_database: Path,
    ) -> bool:
        self.events.append("confirm_source")
        self.source_paths.append(source_database)
        return self.source_confirmed

    def confirm_production(
        self,
        parent: object | None,
        *,
        summary: ProductionSetupSummary,
    ) -> bool:
        self.events.append("confirm_summary")
        self.summaries.append(summary)
        return self.summary_confirmed


def _population_payload() -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_V4_POPULATION_SETTINGS_SCHEMA,
        "universe_id": "synthetic-technical-universe",
        "population_version": "fixture-2026-10-06",
        "decision_date": _DECISION_DATE.isoformat(),
        "raw_stock_codes": ["2330", "2317", "2330"],
        "excluded_stock_codes": ["2317"],
        "exclusion_reasons": {"2317": "測試用明示排除"},
    }


def _write_settings(path: Path, payload: object | None = None) -> Path:
    os.makedirs(to_internal_io_path(path.parent), exist_ok=True)
    content = json.dumps(
        _population_payload() if payload is None else payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    with open(to_internal_io_path(path), "wb") as handle:
        handle.write(content)
    return path


def _write_source_database(database: Path, stock_code: str = "2330") -> None:
    start_date = _DECISION_DATE - timedelta(days=40)
    connection = sqlite3.connect(to_internal_io_path(database))
    try:
        with connection:
            connection.execute(
                "CREATE TABLE daily_prices ("
                "日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, "
                "收盤價 TEXT, 成交股數 INTEGER)"
            )
            rows = []
            for offset in range(40):
                close = 100 + offset
                rows.append((
                    (start_date + timedelta(days=offset)).isoformat(),
                    stock_code,
                    str(close),
                    str(close + 1),
                    str(close - 1),
                    str(close),
                    1000 + offset,
                ))
            connection.executemany(
                "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
                rows,
            )
    finally:
        connection.close()


def _source_signature(database: Path) -> tuple[tuple[bytes, int] | None, ...]:
    signatures: list[tuple[bytes, int] | None] = []
    for path in (database, Path(f"{database}-wal")):
        try:
            info = path.stat()
            signatures.append((path.read_bytes(), info.st_mtime_ns))
        except FileNotFoundError:
            signatures.append(None)
    return tuple(signatures)


def test_new_request_uses_configured_paths_and_displays_full_denominator(
    isolated_config: TWStockConfig,
    tmp_path: Path,
) -> None:
    database = Path(isolated_config.db_file)
    _write_source_database(database)
    settings_path = _write_settings(tmp_path / "population.json")
    cutoff = datetime(2026, 10, 6, 16, 30, tzinfo=_TAIPEI)
    dialogs = _FakeDialogs(settings_path=settings_path, cutoff=cutoff)
    factory = make_daily_market_technical_v4_production_request_factory(
        isolated_config,
        dialogs=dialogs,
    )

    request = factory(None)

    assert request.source_database == database.resolve(strict=True)
    assert request.store_output_root == (
        Path(isolated_config.output_root).resolve() / "research_snapshots" / "technical_universe"
    )
    assert request.research_scope is not None
    assert request.research_scope.source_database == request.source_database
    assert request.cohort.raw_stock_code_count == 3
    assert request.cohort.declared_stock_codes == ("2317", "2330")
    assert request.cohort.included_stock_codes == ("2330",)
    assert request.cohort.excluded_stock_codes == ("2317",)
    assert request.cohort.duplicate_stock_codes == (("2330", 2),)
    assert request.decision_cutoff == cutoff
    assert dialogs.events == [
        "choose_settings",
        "choose_cutoff",
        "confirm_source",
        "confirm_summary",
    ]
    assert dialogs.source_paths == [database.resolve(strict=True)]
    summary_text = dialogs.summaries[0].to_text()
    assert "完整分母：2" in summary_text
    assert "重複多列：1" in summary_text
    assert "2330（出現 2 次）" in summary_text
    assert "2317：測試用明示排除" in summary_text
    assert "完整分母股票代碼：\n2317、2330" in summary_text
    assert str(database.resolve(strict=True)) in summary_text
    assert str(request.store_output_root) in summary_text
    assert "2026-10-06T16:30:00+08:00" in summary_text
    assert not request.store_output_root.exists()


def test_deferred_new_setup_only_collects_input_on_gui_thread_then_builds_request_in_worker(
    isolated_config: TWStockConfig,
    tmp_path: Path,
) -> None:
    database = Path(isolated_config.db_file)
    _write_source_database(database)
    settings_path = _write_settings(tmp_path / "population.json")
    dialogs = _FakeDialogs(
        settings_path=settings_path,
        cutoff=datetime(2026, 10, 6, 16, 30, tzinfo=_TAIPEI),
    )
    setup_factory = make_daily_market_technical_v4_deferred_setup_factory(
        isolated_config,
        dialogs=dialogs,
    )

    setup = setup_factory(None)

    assert isinstance(setup, DailyMarketTechnicalV4DeferredProductionSetup)
    assert dialogs.events == [
        "choose_settings",
        "choose_cutoff",
        "confirm_source",
        "confirm_summary",
    ]
    assert "待背景來源核驗" in setup.summary.to_text()
    assert "尚未 canonical 核驗" in setup.summary.to_text()
    assert not setup.store_output_root.exists()

    cancel_callback = lambda: False
    results: list[DailyMarketTechnicalUniverseV4ProductionRequest] = []
    worker = threading.Thread(
        target=lambda: results.append(
            setup.prepare_request(cancel_callback=cancel_callback)
        ),
        name="technical-universe-setup-test-worker",
    )
    worker.start()
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert len(results) == 1
    request = results[0]
    assert request.source_database == database.resolve(strict=True)
    assert request.store_output_root == (
        Path(isolated_config.output_root).resolve()
        / "research_snapshots"
        / "technical_universe"
    )
    assert request.cohort.raw_stock_code_count == 3
    assert request.decision_cutoff == datetime(
        2026, 10, 6, 16, 30, tzinfo=_TAIPEI
    )
    assert request.cancel_callback is cancel_callback
    assert not request.store_output_root.exists()


@pytest.mark.parametrize(
    ("content", "expected_code"),
    [
        (
            '{"schema_version":"daily-market-technical-universe-v4-population-settings.v1",'
            '"universe_id":"one","universe_id":"two"}',
            "technical_universe_v4_settings_duplicate_key",
        ),
        (
            '{"schema_version":"daily-market-technical-universe-v4-population-settings.v1",'
            '"universe_id":"u","population_version":"v","decision_date":1.5,'
            '"raw_stock_codes":[],"excluded_stock_codes":[],"exclusion_reasons":{}}',
            "technical_universe_v4_settings_float_forbidden",
        ),
        (
            '{"schema_version":"daily-market-technical-universe-v4-population-settings.v1",'
            '"universe_id":"u","population_version":"v","decision_date":"2026-10-06",'
            '"raw_stock_codes":[NaN],"excluded_stock_codes":[],"exclusion_reasons":{}}',
            "technical_universe_v4_settings_json_invalid",
        ),
        (
            '{"schema_version":"daily-market-technical-universe-v4-population-settings.v0",'
            '"universe_id":"u","population_version":"v","decision_date":"2026-10-06",'
            '"raw_stock_codes":[],"excluded_stock_codes":[],"exclusion_reasons":{}}',
            "technical_universe_v4_settings_schema_version_invalid",
        ),
        (
            json.dumps({**_population_payload(), "unrecognized": True}),
            "technical_universe_v4_settings_schema_invalid",
        ),
        (
            json.dumps({**_population_payload(), "raw_stock_codes": [2330]}),
            "technical_universe_v4_settings_field_type_invalid",
        ),
    ],
)
def test_population_settings_rejects_invalid_json_and_schema(
    tmp_path: Path,
    content: str,
    expected_code: str,
) -> None:
    settings_path = tmp_path / "invalid.json"
    settings_path.write_text(content, encoding="utf-8")

    with pytest.raises(DailyMarketTechnicalV4ProductionSetupError) as error:
        load_daily_market_technical_v4_population_settings(settings_path)

    assert error.value.code == expected_code


def test_population_settings_rejects_files_over_the_bounded_size(
    tmp_path: Path,
) -> None:
    from app_module.daily_market_technical_universe_v4_store import (
        DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_PLAN_BYTES,
    )

    settings_path = tmp_path / "oversized.json"
    with open(to_internal_io_path(settings_path), "wb") as handle:
        handle.truncate(DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_PLAN_BYTES + 1)

    with pytest.raises(DailyMarketTechnicalV4ProductionSetupError) as error:
        load_daily_market_technical_v4_population_settings(settings_path)

    assert error.value.code == "technical_universe_v4_settings_file_too_large"


def test_population_settings_reads_a_native_long_path(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / f"population-settings-{'x' * 190}.json"
    _write_settings(settings_path)
    assert len(str(settings_path)) >= 248

    cohort = load_daily_market_technical_v4_population_settings(settings_path)

    assert cohort.universe_id == "synthetic-technical-universe"
    assert cohort.raw_stock_code_count == 3


@pytest.mark.parametrize(
    "value",
    [
        "2026-10-06T15:59:59+08:00",
        "2026-10-07T16:00:00+08:00",
        "2026-10-06T16:00:00",
        "2026-10-06T16:00:00Z",
        "not-a-date",
    ],
)
def test_cutoff_requires_taipei_date_and_minimum_close_time(value: str) -> None:
    with pytest.raises(DailyMarketTechnicalV4ProductionSetupError) as error:
        parse_daily_market_technical_v4_decision_cutoff(
            value,
            decision_date=_DECISION_DATE,
        )

    assert error.value.code == "technical_universe_v4_setup_cutoff_invalid"


def test_user_cancellation_does_not_create_a_production_request_or_store(
    isolated_config: TWStockConfig,
    tmp_path: Path,
) -> None:
    database = Path(isolated_config.db_file)
    _write_source_database(database)
    settings_path = _write_settings(tmp_path / "population.json")
    dialogs = _FakeDialogs(
        settings_path=settings_path,
        cutoff=datetime(2026, 10, 6, 16, 0, tzinfo=_TAIPEI),
        summary_confirmed=False,
    )
    factory = make_daily_market_technical_v4_production_request_factory(
        isolated_config,
        dialogs=dialogs,
    )

    with pytest.raises(DailyMarketTechnicalV4ProductionSetupCancelled) as error:
        factory(None)

    assert error.value.code == "technical_universe_v4_setup_cancelled"
    assert "尚未送出" in str(error.value)
    assert dialogs.events[-1] == "confirm_summary"
    assert not (
        Path(isolated_config.output_root)
        / "research_snapshots"
        / "technical_universe"
    ).exists()


def test_daily_research_view_wires_factory_for_a_real_twstock_config(
    isolated_config: TWStockConfig,
) -> None:
    from types import SimpleNamespace

    from PySide6.QtWidgets import QApplication

    from ui_qt.views.daily_market_research_view import DailyMarketResearchView

    daily = DailyMarketResearchView(
        SimpleNamespace(config=isolated_config, snapshot_root=None)
    )
    try:
        technical_view = daily.technical_universe_view
        assert technical_view is not None
        assert technical_view.production_request_factory is not None
        assert technical_view.store_output_root == (
            Path(isolated_config.output_root)
            / "research_snapshots"
            / "technical_universe"
        )
    finally:
        assert daily.begin_shutdown()
        daily.close()
        application = QApplication.instance()
        assert application is not None
        application.processEvents()


def test_real_new_request_cancelled_receipt_resumes_only_selected_exact_entry(
    isolated_config: TWStockConfig,
    tmp_path: Path,
) -> None:
    database = Path(isolated_config.db_file)
    _write_source_database(database)
    source_before = _source_signature(database)
    settings_path = _write_settings(tmp_path / "population.json")
    cutoff = datetime(2026, 10, 6, 16, 0, tzinfo=_TAIPEI)
    new_dialogs = _FakeDialogs(settings_path=settings_path, cutoff=cutoff)
    factory = make_daily_market_technical_v4_production_request_factory(
        isolated_config,
        dialogs=new_dialogs,
    )
    request = factory(None)

    cancelled = produce_daily_market_technical_universe_v4(
        replace(request, cancel_callback=lambda: True)
    )
    assert cancelled.status == "cancelled", cancelled.to_dict()
    assert cancelled.receipt is not None
    assert cancelled.receipt.status == "cancelled"
    assert source_before == _source_signature(database)

    catalog = DailyMarketTechnicalUniverseV4Catalog(request.store_output_root)
    page = catalog.list_page(limit=10)
    selected = next(
        entry
        for entry in page.rows
        if entry.receipt_identity_sha256 == cancelled.receipt_identity_sha256
    )
    assert selected.is_selectable

    resume_dialogs = _FakeDialogs()
    resume_factory = make_daily_market_technical_v4_production_request_factory(
        isolated_config,
        dialogs=resume_dialogs,
    )
    resumed_request = resume_factory(selected)

    assert resume_dialogs.events == ["confirm_source", "confirm_summary"]
    assert resumed_request.cohort == request.cohort
    assert resumed_request.decision_cutoff == request.decision_cutoff
    assert resumed_request.source_database == request.source_database
    assert resumed_request.store_output_root == request.store_output_root
    assert resumed_request.resume_receipt_identity_sha256 == selected.receipt_identity_sha256
    assert resumed_request.expected_resume_receipt_sha256 == selected.receipt_bytes_sha256
    assert resume_dialogs.summaries[0].selected_entry is selected
    assert "metadata_unverified" in resume_dialogs.summaries[0].to_text()
    assert "背景工作會對這一列呼叫 Catalog.read_exact" in (
        resume_dialogs.summaries[0].to_text()
    )

    completed = produce_daily_market_technical_universe_v4(resumed_request)

    assert completed.status == "complete", completed.to_dict()
    assert completed.resumed is True
    assert completed.plan is not None
    assert completed.plan.cohort == request.cohort
    assert completed.plan.source_clock.decision_cutoff == cutoff
    assert source_before == _source_signature(database)
    reopened = DailyMarketTechnicalUniverseV4Catalog(
        request.store_output_root
    ).read_exact(selected)
    assert reopened.receipt.status == "cancelled"
    assert reopened.receipt.content_sha256 == selected.receipt_bytes_sha256


def test_deferred_resume_rejects_changed_exact_pin_with_reader_reason(
    isolated_config: TWStockConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Path(isolated_config.db_file)
    _write_source_database(database)
    settings_path = _write_settings(tmp_path / "population.json")
    new_setup = make_daily_market_technical_v4_deferred_setup_factory(
        isolated_config,
        dialogs=_FakeDialogs(
            settings_path=settings_path,
            cutoff=datetime(2026, 10, 6, 16, 0, tzinfo=_TAIPEI),
        ),
    )(None)
    new_request = new_setup.prepare_request()
    cancelled = produce_daily_market_technical_universe_v4(
        replace(new_request, cancel_callback=lambda: True)
    )
    assert cancelled.receipt is not None
    catalog = DailyMarketTechnicalUniverseV4Catalog(new_request.store_output_root)
    selected = next(
        entry
        for entry in catalog.list_page(limit=10).rows
        if entry.receipt_identity_sha256 == cancelled.receipt_identity_sha256
    )
    wrong_pin = replace(selected, receipt_bytes_sha256="0" * 64)
    setup = make_daily_market_technical_v4_deferred_setup_factory(
        isolated_config,
        dialogs=_FakeDialogs(),
    )(wrong_pin)

    with pytest.raises(DailyMarketTechnicalV4ProductionSetupError) as error:
        setup.prepare_request()

    assert error.value.code == "technical_universe_v4_selected_receipt_read_failed"
    assert error.value.cause_code
    assert "metadata_unverified" in setup.summary.to_text()


def test_deferred_resume_checks_cancel_before_and_after_uninterruptible_exact_read(
    isolated_config: TWStockConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Path(isolated_config.db_file)
    _write_source_database(database)
    settings_path = _write_settings(tmp_path / "population.json")
    new_setup = make_daily_market_technical_v4_deferred_setup_factory(
        isolated_config,
        dialogs=_FakeDialogs(
            settings_path=settings_path,
            cutoff=datetime(2026, 10, 6, 16, 0, tzinfo=_TAIPEI),
        ),
    )(None)
    new_request = new_setup.prepare_request()
    cancelled = produce_daily_market_technical_universe_v4(
        replace(new_request, cancel_callback=lambda: True)
    )
    assert cancelled.receipt is not None
    catalog = DailyMarketTechnicalUniverseV4Catalog(new_request.store_output_root)
    selected = next(
        entry
        for entry in catalog.list_page(limit=10).rows
        if entry.receipt_identity_sha256 == cancelled.receipt_identity_sha256
    )
    setup = make_daily_market_technical_v4_deferred_setup_factory(
        isolated_config,
        dialogs=_FakeDialogs(),
    )(selected)

    read_count = 0
    original_read_exact = DailyMarketTechnicalUniverseV4Catalog.read_exact

    def count_read_exact(
        active_catalog: DailyMarketTechnicalUniverseV4Catalog,
        entry: DailyMarketTechnicalUniverseV4CatalogEntry,
    ) -> DailyMarketTechnicalUniverseV4VerifiedState:
        nonlocal read_count
        read_count += 1
        return original_read_exact(active_catalog, entry)

    monkeypatch.setattr(
        DailyMarketTechnicalUniverseV4Catalog,
        "read_exact",
        count_read_exact,
    )
    with pytest.raises(DailyMarketTechnicalV4ProductionSetupCancelled):
        setup.prepare_request(cancel_callback=lambda: True)
    assert read_count == 0

    cancellation_requested = False

    def read_then_request_cancel(
        active_catalog: DailyMarketTechnicalUniverseV4Catalog,
        entry: DailyMarketTechnicalUniverseV4CatalogEntry,
    ) -> DailyMarketTechnicalUniverseV4VerifiedState:
        nonlocal read_count, cancellation_requested
        read_count += 1
        saved = original_read_exact(active_catalog, entry)
        cancellation_requested = True
        return saved

    monkeypatch.setattr(
        DailyMarketTechnicalUniverseV4Catalog,
        "read_exact",
        read_then_request_cancel,
    )
    with pytest.raises(DailyMarketTechnicalV4ProductionSetupCancelled):
        setup.prepare_request(cancel_callback=lambda: cancellation_requested)
    assert read_count == 1


def test_deferred_resume_factory_does_not_run_strict_reader_on_gui_thread(
    isolated_config: TWStockConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Path(isolated_config.db_file)
    _write_source_database(database)
    settings_path = _write_settings(tmp_path / "population.json")
    new_request = make_daily_market_technical_v4_production_request_factory(
        isolated_config,
        dialogs=_FakeDialogs(
            settings_path=settings_path,
            cutoff=datetime(2026, 10, 6, 16, 0, tzinfo=_TAIPEI),
        ),
    )(None)
    cancelled = produce_daily_market_technical_universe_v4(
        replace(new_request, cancel_callback=lambda: True)
    )
    assert cancelled.receipt is not None
    selected = next(
        entry
        for entry in DailyMarketTechnicalUniverseV4Catalog(
            new_request.store_output_root
        ).list_page(limit=10).rows
        if entry.receipt_identity_sha256 == cancelled.receipt_identity_sha256
    )
    dialogs = _FakeDialogs()
    setup = make_daily_market_technical_v4_deferred_setup_factory(
        isolated_config,
        dialogs=dialogs,
    )(selected)
    assert setup.selected_receipt_identity_sha256 == selected.receipt_identity_sha256
    assert setup.selected_receipt_bytes_sha256 == selected.receipt_bytes_sha256
    assert dialogs.events == ["confirm_source", "confirm_summary"]
    gui_thread_id = threading.get_ident()
    reader_thread_ids: list[int] = []
    original_read_exact = DailyMarketTechnicalUniverseV4Catalog.read_exact

    def record_reader_thread(
        active_catalog: DailyMarketTechnicalUniverseV4Catalog,
        entry: DailyMarketTechnicalUniverseV4CatalogEntry,
    ) -> DailyMarketTechnicalUniverseV4VerifiedState:
        reader_thread_ids.append(threading.get_ident())
        return original_read_exact(active_catalog, entry)

    monkeypatch.setattr(
        DailyMarketTechnicalUniverseV4Catalog,
        "read_exact",
        record_reader_thread,
    )

    results: list[DailyMarketTechnicalUniverseV4ProductionRequest] = []
    worker = threading.Thread(
        target=lambda: results.append(setup.prepare_request()),
        name="technical-universe-resume-setup-test-worker",
    )
    worker.start()
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert len(results) == 1
    resumed_request = results[0]
    assert resumed_request.resume_receipt_identity_sha256 == (
        selected.receipt_identity_sha256
    )
    assert resumed_request.expected_resume_receipt_sha256 == (
        selected.receipt_bytes_sha256
    )
    assert reader_thread_ids and all(
        thread_id != gui_thread_id for thread_id in reader_thread_ids
    )
