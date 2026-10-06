import json
import sys
from types import SimpleNamespace

from scripts.run_tpex_full_refresh_and_technical import (
    _cancel_requested,
    _run_tpex_parallel,
    _should_skip_technical_indicators,
)


def test_background_refresh_skips_technical_when_indicator_is_current():
    status = {
        "daily_data": {"latest_date": "2026-06-18"},
        "technical_indicators": {"latest_date": "2026-06-18"},
    }

    should_skip, message = _should_skip_technical_indicators(status, force_all=False)

    assert should_skip is True
    assert "2026-06-18" in message


def test_background_refresh_calculates_technical_when_indicator_is_stale():
    status = {
        "daily_data": {"latest_date": "2026-06-18"},
        "technical_indicators": {"latest_date": "2026-06-17"},
    }

    should_skip, _message = _should_skip_technical_indicators(status, force_all=False)

    assert should_skip is False


def test_background_refresh_force_all_disables_technical_skip():
    status = {
        "daily_data": {"latest_date": "2026-06-18"},
        "technical_indicators": {"latest_date": "2026-06-18"},
    }

    should_skip, _message = _should_skip_technical_indicators(status, force_all=True)

    assert should_skip is False


def test_background_refresh_does_not_skip_when_technical_coverage_lags():
    status = {
        "daily_data": {"latest_date": "2026-07-06"},
        "technical_indicators": {"latest_date": "2026-07-06"},
    }

    should_skip, message = _should_skip_technical_indicators(
        status,
        force_all=False,
        technical_coverage={
            "success": True,
            "is_current": False,
            "daily_latest_date": "20260706",
            "eligible_stock_count": 2,
            "covered_stock_count": 1,
        },
    )

    assert should_skip is False
    assert "1/2" in message


def test_parallel_tpex_refresh_fails_when_pending_date_is_missing(tmp_path):
    (tmp_path / "20260703.csv").write_text(
        "日期,證券代號,證券名稱,收盤價\n20260703,3207,耀勝,42.5\n",
        encoding="utf-8-sig",
    )

    class FailingSource:
        def update_for_date(self, date_key):
            assert date_key == "20260706"
            return SimpleNamespace(
                success=False,
                source_date=None,
                row_count=0,
                skipped_count=0,
                message="remote disconnected",
            )

    class FakeService:
        def _iter_weekday_date_keys(self, start_date, end_date):
            return ["20260703", "20260706"]

        def _create_tpex_daily_price_source(self):
            return FailingSource()

    state = {"steps": {}}
    result = _run_tpex_parallel(
        FakeService(),
        SimpleNamespace(tpex_daily_price_dir=tmp_path),
        tmp_path / "state.json",
        state,
        start_date="2026-07-03",
        end_date="2026-07-06",
        workers=1,
    )

    assert result["success"] is False
    assert result["failed_dates"] == ["20260706"]
    assert result["warnings"] == ["TPEX 每日股價缺少日期：20260706"]


def test_tpex_backend_reads_cancel_marker_and_writes_completion_receipt(
    tmp_path,
    monkeypatch,
):
    import scripts.run_tpex_full_refresh_and_technical as module

    state_file = tmp_path / "state.json"
    cancel_file = tmp_path / "state.json.cancel"
    cancel_file.write_text("requested", encoding="ascii")

    class FakeService:
        def update_tpex_daily_price_range(self, *args, cancel_callback=None, **kwargs):
            assert cancel_callback is not None
            assert cancel_callback() is True
            return {
                "success": False,
                "cancelled": True,
                "message": "cancelled at safe boundary",
                "requested_dates": [],
                "updated_dates": [],
                "fallback_dates": [],
                "skipped_dates": [],
                "failed_dates": [],
                "warnings": [],
            }

    monkeypatch.setattr(module, "TWStockConfig", lambda: object())
    monkeypatch.setattr(module, "UpdateService", lambda _config: FakeService())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_tpex_full_refresh_and_technical.py",
            "--start-date",
            "2026-07-01",
            "--end-date",
            "2026-07-06",
            "--state-file",
            str(state_file),
            "--cancel-file",
            str(cancel_file),
        ],
    )

    assert module.main() == 0
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["status"] == "cancelled"
    assert state["cancel_requested"] is True
    assert state["cancel_completed"] is True
    assert _cancel_requested(cancel_file) is True


def test_background_refresh_publishes_technical_receipt_after_calculation(
    tmp_path,
    monkeypatch,
):
    """技術表被背景入口更新後，必須同步留下 prospective receipt。"""

    import scripts.run_tpex_full_refresh_and_technical as module

    state_file = tmp_path / "state.json"
    captured = {}

    class FakeConfig:
        db_file = tmp_path / "source.db"
        output_root = tmp_path / "output"
        tpex_daily_price_dir = tmp_path / "tpex"

    class FakeService:
        def update_tpex_daily_price_range(self, *args, **kwargs):
            return {
                "success": True,
                "message": "TPEX fixture complete",
                "requested_dates": ["20260706"],
                "updated_dates": ["20260706"],
                "fallback_dates": [],
                "skipped_dates": [],
                "failed_dates": [],
                "warnings": [],
                "tpex_rows": 1,
                "skipped_rows": 0,
                "diagnostic_count": 0,
                "source_dates": ["20260706"],
                "source_custody": [{"receipt_path": str(tmp_path / "tpex.json")}],
            }

        def check_data_overview(self):
            return {
                "daily_data": {"latest_date": "2026-07-06"},
                "technical_indicators": {"latest_date": "2026-07-05"},
            }

        def check_technical_indicator_latest_coverage(self):
            return {
                "success": True,
                "is_current": False,
                "daily_latest_date": "20260706",
                "eligible_stock_count": 1,
                "covered_stock_count": 0,
            }

        def calculate_technical_indicators(self, *args, **kwargs):
            return {
                "success": True,
                "message": "technical fixture complete",
                "updated_stocks": ["1101"],
            }

    monkeypatch.setattr(module, "TWStockConfig", lambda: FakeConfig())
    monkeypatch.setattr(module, "UpdateService", lambda _config: FakeService())
    monkeypatch.setattr(
        module,
        "capture_technical_input_snapshot",
        lambda *args, **kwargs: {"verified": True, "row_count": 1},
    )
    monkeypatch.setattr(
        module,
        "build_technical_computation_evidence",
        lambda **kwargs: {
            "evidence_sha256": "sha256:fixture",
            "calculation_result": {"success": True},
        },
    )

    def fake_publish(*, output_root, source_db, update_status, authorized_output_roots):
        captured["update_status"] = update_status
        captured["output_root"] = output_root
        captured["source_db"] = source_db
        captured["authorized_output_roots"] = authorized_output_roots
        return {"status": "published", "receipt_path": str(tmp_path / "receipt.json")}

    monkeypatch.setattr(module, "publish_technical_indicator_receipt", fake_publish)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_tpex_full_refresh_and_technical.py",
            "--start-date",
            "2026-07-06",
            "--end-date",
            "2026-07-06",
            "--state-file",
            str(state_file),
        ],
    )

    assert module.main() == 0

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["technical_publication_receipt"]["status"] == "published"
    assert captured["update_status"]["status"] == "passed"
    technical_steps = [
        step
        for step in captured["update_status"]["steps"]
        if step["name"] == "calculate_technical_indicators"
    ]
    assert len(technical_steps) == 1
    assert technical_steps[0]["status"] == "passed"
    assert technical_steps[0]["result"]["technical_computation"]["evidence_sha256"] == (
        "sha256:fixture"
    )
    assert captured["authorized_output_roots"] == (FakeConfig.output_root,)


def test_background_refresh_blocks_currentity_skip_without_reusable_witness(
    tmp_path,
    monkeypatch,
):
    """currentity skip 找不到既有 witness 時，不得建立新的 availability。"""

    import scripts.run_tpex_full_refresh_and_technical as module

    state_file = tmp_path / "state.json"

    class FakeConfig:
        db_file = tmp_path / "source.db"
        output_root = tmp_path / "output"
        tpex_daily_price_dir = tmp_path / "tpex"

    class FakeService:
        def update_tpex_daily_price_range(self, *args, **kwargs):
            return {
                "success": True,
                "message": "TPEX fixture complete",
                "requested_dates": ["20260706"],
                "updated_dates": [],
                "fallback_dates": [],
                "skipped_dates": ["20260706"],
                "failed_dates": [],
                "warnings": [],
                "source_dates": ["20260706"],
            }

        def check_data_overview(self):
            return {
                "daily_data": {"latest_date": "2026-07-06"},
                "technical_indicators": {"latest_date": "2026-07-06"},
            }

        def check_technical_indicator_latest_coverage(self):
            return {
                "success": True,
                "is_current": True,
                "daily_latest_date": "20260706",
                "eligible_stock_count": 1,
                "covered_stock_count": 1,
            }

    monkeypatch.setattr(module, "TWStockConfig", lambda: FakeConfig())
    monkeypatch.setattr(module, "UpdateService", lambda _config: FakeService())
    monkeypatch.setattr(
        module,
        "reuse_verified_technical_computation_receipt",
        lambda **kwargs: {
            "status": "not_found",
            "reason": "verified_technical_computation_receipt_not_reusable",
            "diagnostics": ["technical_computation_witness_missing"],
        },
    )

    def unexpected_publish(**kwargs):
        raise AssertionError("currentity skip without witness must not publish")

    monkeypatch.setattr(module, "publish_technical_indicator_receipt", unexpected_publish)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_tpex_full_refresh_and_technical.py",
            "--start-date",
            "2026-07-06",
            "--end-date",
            "2026-07-06",
            "--state-file",
            str(state_file),
        ],
    )

    assert module.main() == 0

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["technical_publication_receipt"] == {
        "status": "blocked",
        "reason": "technical_computation_reuse_missing",
        "reuse_reason": "verified_technical_computation_receipt_not_reusable",
        "reuse_diagnostics": ["technical_computation_witness_missing"],
    }
    assert any(
        "technical_computation_reuse_missing" in warning
        for warning in state["warnings"]
    )
