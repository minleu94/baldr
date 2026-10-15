"""年度daily沿原public reader／Registry controller，所有接受與clock均為合成。"""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from PySide6.QtCore import QEventLoop, QTimer, Qt

from app_module import recommendation_portfolio_full_period_pair_v1 as pair_module
from app_module.official_calendar_daily_snapshot_v1 import (
    OfficialCalendarDailySnapshotCancelled,
    calendar_annual_daily_use_scope_v1,
    write_official_calendar_annual_daily_snapshot_v1,
)
from app_module.recommendation_portfolio_full_period_pair_v1 import (
    FullPeriodPairReadCancelledV1, FullPeriodPairReadErrorV1, FullPeriodPairReadV1,
    RecommendationPortfolioFullPeriodPairReadServiceV1,
)
from app_module.recommendation_portfolio_period_calendar_read_pin_v1 import PortfolioPeriodCalendarDailyReadPinV1
from app_module.saved_strategy_rule_card import metadata_sha256
from data_module.daily_source_snapshot import DailySourceUseAcceptance
from data_module.official_calendar_bundle import TPEX_ANNUAL_TRADING_DATE_URL, TWSE_HOLIDAY_SCHEDULE_URL
import test_official_calendar_daily_snapshot_v1 as monthly_fixture
import test_recommendation_portfolio_annual_calendar_evidence_v1 as annual_fixture
import test_recommendation_portfolio_daily_calendar_pair_v1 as daily_pair_fixture
import test_recommendation_portfolio_full_period_pair_v1 as pair_fixture
from test_registry_period_pair_controller import _wait_until
from ui_qt.views.research_lab.registry_period_pair_controller import RegistryPeriodPairController
from ui_qt.views.research_lab.run_registry_compare_widget import RunRegistryCompareWidget


pytest_plugins = ("test_registry_period_pair_controller",)
_PAST = datetime(2026, 10, 14, 0, 0, tzinfo=timezone.utc)


def _anchors():
    values = {}
    for market, endpoint in (("twse", TWSE_HOLIDAY_SCHEDULE_URL), ("tpex", TPEX_ANNUAL_TRADING_DATE_URL)):
        scope = calendar_annual_daily_use_scope_v1(market)
        values[market] = DailySourceUseAcceptance(
            scope=scope, acceptance_id=f"synthetic-annual-{market}",
            accepted_at=_PAST + timedelta(minutes=1), official_source_endpoint=endpoint,
            document_chain=("synthetic-test-only", endpoint),
            acceptance_evidence_ref=f"synthetic-annual-test:{market}", authorization_scope=scope.intended_use,
        )
    return values


def _case(tmp_path: Path):
    config, service, reader, _calendar, left, right, *_ = pair_fixture._saved_pair(tmp_path)
    base = tmp_path / "annual-daily"
    base.mkdir()
    root, protected = monthly_fixture._roots(base)
    twse, tpex = annual_fixture._transports()
    # 原raw保留；clock為明示合成測試，不能冒稱真原件成功批次。
    transports = tuple(replace(item, started_at=_PAST, body_completed_at=_PAST + timedelta(seconds=1))
                       for item in (twse, tpex))
    clock, _ = monthly_fixture._clock(_PAST + timedelta(minutes=minute) for minute in (2, 3, 4, 5))
    anchors = _anchors()
    snapshot = write_official_calendar_annual_daily_snapshot_v1(
        root, batch_id="synthetic-annual-pair-001", start_date=date.fromisoformat(pair_fixture._START),
        end_date=date.fromisoformat(pair_fixture._END), transports=transports,
        trusted_acceptances=anchors, protected_roots=protected, clock=clock,
    )
    pin = PortfolioPeriodCalendarDailyReadPinV1(
        snapshot.batch_directory, snapshot.manifest_sha256, snapshot.receipt_sha256,
        "twse", protected + (Path(config.data_root), Path(config.output_root)),
        (anchors["twse"], anchors["tpex"]), snapshot.available_hour,
    )
    case = RecommendationPortfolioFullPeriodPairReadServiceV1(service, reader), pin, left, right, service
    return case, config


@pytest.mark.parametrize("market", ["twse", "tpex"])
def test_annual_daily_pair_uses_original_public_reader_without_monthly_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, market: str,
) -> None:
    case, _ = _case(tmp_path)
    pair, pin, left, right, _ = case
    pin = replace(pin, market=market)
    assert pin.source_version == "annual_v1"
    before = daily_pair_fixture._inventory(case)
    calls = []
    original = pair._reader.read

    def observed(run_id, **kwargs):
        calls.append(run_id)
        return original(run_id, **kwargs)

    monkeypatch.setattr(pair._reader, "read", observed)
    monkeypatch.setattr(pair_module, "read_official_calendar_daily_snapshot_v1",
                        lambda *args, **kwargs: pytest.fail("annual不可走monthly reader"))
    monkeypatch.setattr(pair_fixture, "_produce", lambda **kwargs: pytest.fail("讀回不可重產producer"))
    result = daily_pair_fixture._read(case, pin)
    assert calls == [left.run_id, right.run_id]
    assert result.expected_session_dates == pair_fixture._DATES and result.coverage_complete
    assert result.status == "blocked" and result.metrics is None
    assert not result.performance_eligible and not result.historical_pit_eligible
    assert "calendar_candidate_only" in result.reasons
    assert result.daily_calendar_source is not None
    assert result.daily_calendar_source.manifest_sha256 == pin.expected_manifest_sha256
    assert result.daily_calendar_source.receipt_sha256 == pin.expected_receipt_sha256
    assert daily_pair_fixture._inventory(case) == before


def test_annual_daily_pair_rechecks_receipt_after_both_run_reads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    case, _ = _case(tmp_path)
    pair, pin, *_ = case
    original = pair._read_run
    calls = []

    def changed(run_id, metadata, **kwargs):
        value = original(run_id, metadata, **kwargs)
        calls.append(run_id)
        if len(calls) == 2:
            (pin.batch_directory / "receipt.json").write_bytes(b"{}")
        return value

    monkeypatch.setattr(pair, "_read_run", changed)
    with pytest.raises(FullPeriodPairReadErrorV1):
        daily_pair_fixture._read(case)
    assert len(calls) == 2


def test_annual_daily_reader_cancel_is_typed_without_monthly_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    case, _ = _case(tmp_path)

    def cancelled(*args, **kwargs):
        raise OfficialCalendarDailySnapshotCancelled("calendar_batch_cancelled")

    monkeypatch.setattr(pair_module, "read_official_calendar_annual_daily_snapshot_v1", cancelled)
    monkeypatch.setattr(pair_module, "read_official_calendar_daily_snapshot_v1",
                        lambda *args, **kwargs: pytest.fail("取消不可fallback monthly"))
    with pytest.raises(FullPeriodPairReadCancelledV1):
        daily_pair_fixture._read(case)


def test_daily_pin_rejects_mixed_annual_and_monthly_acceptances(tmp_path: Path) -> None:
    case, _ = _case(tmp_path)
    pin = case[1]
    monthly = monthly_fixture._acceptances()
    for anchors in ((pin.trusted_acceptances[0], monthly["tpex"]),
                    (monthly["twse"], pin.trusted_acceptances[1]),
                    tuple(reversed(pin.trusted_acceptances))):
        with pytest.raises(ValueError):
            replace(pin, trusted_acceptances=anchors)


def test_normal_registry_controller_reads_actual_annual_batch_and_saved_runs(
    tmp_path: Path, qt_app,
) -> None:
    case, config = _case(tmp_path)
    _, pin, left, right, service = case
    before = daily_pair_fixture._inventory(case)
    widget = RunRegistryCompareWidget(service, page_size=10)
    widget.refresh_runs()
    for index in range(widget.run_list.count()):
        item = widget.run_list.item(index)
        item.setSelected(item.data(Qt.ItemDataRole.UserRole) in (left.run_id, right.run_id))
    controller = RegistryPeriodPairController(service, config, widget, lambda: 1, parent=widget)
    try:
        controller.source_mode.setCurrentIndex(controller.source_mode.findData("daily"))
        controller.artifact_path.setText(str(pin.batch_directory))
        controller.external_sha.setText(pin.expected_manifest_sha256)
        controller.receipt_sha.setText(pin.expected_receipt_sha256)
        controller.market.setCurrentIndex(controller.market.findData("twse"))
        controller.set_daily_acceptances(pin.trusted_acceptances)
        controller.apply_button.click()
        assert controller._pin is not None and controller._pin.source_version == "annual_v1"
        assert widget.compare_period_pair_button.isEnabled()
        widget.compare_period_pair_button.click()
        assert controller.worker is not None
        # 真檔案reader會釋放GIL作stat；Qt event loop讓背景執行緒在原5秒內推進。
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        controller.worker.native_thread_finished.connect(loop.quit, Qt.ConnectionType.QueuedConnection)
        timer.start(5000)
        loop.exec()
        finished_in_time = timer.isActive()
        timer.stop()
        qt_app.processEvents()
        assert finished_in_time and controller.worker is None
        assert controller._error == ""
        result = widget._period_pair_result
        assert isinstance(result, FullPeriodPairReadV1)
        assert result.expected_session_dates == pair_fixture._DATES
        assert result.daily_calendar_source.manifest_sha256 == pin.expected_manifest_sha256
        assert "已阻擋" in widget.period_pair_status_label.text()
        assert pin.expected_manifest_sha256 in widget.period_pair_result_label.text()
        assert daily_pair_fixture._inventory(case) == before
    finally:
        controller.begin_shutdown()
        if controller.worker is not None:
            assert controller.worker.wait(5000)
            assert _wait_until(qt_app, lambda: controller.worker is None)
        widget.close()
        widget.deleteLater()
        qt_app.processEvents()
