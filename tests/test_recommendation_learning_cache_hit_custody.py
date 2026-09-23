"""Bounded QA for cache-hit custody in the daily learning update lane.

The fixture deliberately runs the real technical calculator before invoking the
quick runner.  Only network-facing source refreshes, the trading-calendar
resolver, and the capacity gate are isolated.  This keeps the assertion useful:
the runner must retain a verifiable computation witness when it skips because
the formal technical table is already current.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
import logging
from pathlib import Path
import tempfile
from types import SimpleNamespace

import pandas as pd
import pytest

from app_module.update_service import UpdateService
from data_module.config import TWStockConfig
from data_module.db_manager import DBManager
from data_module.official_daily_price_custody import (
    persist_official_daily_price_response,
)
from data_module.recommendation_calibration_source_contract import (
    build_technical_computation_evidence,
    capture_technical_input_snapshot,
    inspect_source_contract,
    publish_technical_indicator_receipt,
)
from scripts.scheduled import run_daily_data_update_quick as runner


SOURCE_DATES = ("2026-09-08", "2026-09-09", "2026-09-10")
SYMBOLS = ("1101", "2330")


@pytest.fixture
def _short_tmp_root():
    """Keep immutable custody paths below Windows' legacy path-length limit."""

    with tempfile.TemporaryDirectory(
        prefix="qa-cache-",
        dir=Path.cwd(),
        ignore_cleanup_errors=True,
    ) as root:
        try:
            yield Path(root)
        finally:
            # Config/DBManager intentionally cache process-wide file handlers;
            # close fixture-root handlers before TemporaryDirectory cleanup.
            for logger_name in (
                "data_module.config",
                "data_module.db_manager",
            ):
                logger = logging.getLogger(logger_name)
                for handler in logger.handlers[:]:
                    if isinstance(handler, logging.FileHandler):
                        handler.close()
                        logger.removeHandler(handler)


def _fixture_raw_response() -> bytes:
    return json.dumps(
        {
            "tables": [
                {
                    "fields": ["證券代號", "收盤價"],
                    "data": [[symbol, "100"] for symbol in SYMBOLS],
                }
            ]
        },
        ensure_ascii=False,
    ).encode("utf-8")


def _seed_actual_technical_db(
    data_root: Path,
    output_root: Path,
    source_date: str,
) -> tuple[TWStockConfig, dict[str, object]]:
    """Create enough price history for the production calculator to run."""

    config = TWStockConfig(data_root=data_root, output_root=output_root, profile="prod")
    db = DBManager(config)
    end_day = date.fromisoformat(source_date)
    history = [end_day - timedelta(days=34 - offset) for offset in range(35)]
    rows: list[dict[str, object]] = []
    for offset, trading_day in enumerate(history):
        date_key = trading_day.strftime("%Y%m%d")
        for symbol_index, symbol in enumerate(SYMBOLS):
            close = 100 + offset + symbol_index
            rows.append(
                {
                    "日期": date_key,
                    "證券代號": symbol,
                    "證券名稱": f"fixture-{symbol}",
                    "成交股數": 100_000 + offset,
                    "成交筆數": 1_000 + offset,
                    "成交金額": close * 100_000,
                    "開盤價": close - 1,
                    "最高價": close + 2,
                    "最低價": close - 2,
                    "收盤價": close,
                    "漲跌價差": 1,
                    "最後揭示買價": close - 1,
                    "最後揭示買量": 100,
                    "最後揭示賣價": close + 1,
                    "最後揭示賣量": 100,
                    "本益比": 10,
                }
            )
    assert db.write_dataframe("daily_prices", pd.DataFrame(rows)) is True

    # This is the real UpdateService/TechnicalIndicatorCalculator path.  It
    # intentionally does not stub readiness, coverage, or the calculator.
    calculation = UpdateService(config).calculate_technical_indicators(
        force_all=True,
        technical_process_pool=False,
    )
    assert calculation.get("success") is True, calculation
    assert set(calculation.get("updated_stocks", [])) == set(SYMBOLS)
    technical_rows = db.execute_query(
        'SELECT "證券代號", "日期", "ADX" FROM technical_indicators '
        'WHERE "日期" BETWEEN ? AND ?;',
        params=(
            history[0].strftime("%Y%m%d"),
            history[-1].strftime("%Y%m%d"),
        ),
    )
    assert not technical_rows.empty
    # Causal TA-Lib warm-up remains NULL; after its 27-observation ADX
    # lookback, values must recover and remain available for both stocks.
    for _stock_id, stock_rows in technical_rows.groupby("證券代號", sort=False):
        stock_rows = stock_rows.sort_values("日期", kind="stable").reset_index(drop=True)
        assert stock_rows.loc[:26, "ADX"].isna().all()
        assert stock_rows.loc[27:, "ADX"].notna().all()
        assert (stock_rows.loc[27:, "ADX"] != 0).any()
    return config, dict(calculation)


def _capture_official_fixture(output_root: Path, source_date: str) -> dict[str, object]:
    captured_at = datetime.fromisoformat(source_date + "T05:10:00+00:00")
    captures: list[dict[str, object]] = []
    for venue, source_id in (
        ("twse", "twse.mi_index.daily_price"),
        ("tpex", "tpex.daily_close_quotes"),
    ):
        captures.append(
            persist_official_daily_price_response(
                output_root=output_root,
                venue=venue,
                source_id=source_id,
                source_date=source_date,
                requested_url=f"https://fixture.invalid/{venue}",
                final_url=f"https://fixture.invalid/{venue}",
                request_parameters={"date": source_date.replace("-", "")},
                http_status=200,
                response_headers={"Content-Type": "application/json"},
                raw_response=_fixture_raw_response(),
                captured_at=captured_at,
                row_count=len(SYMBOLS),
                source_columns=("證券代號", "收盤價"),
                parser_id="cache-hit-custody-fixture.v1",
            )
        )
    return {"captures": captures}


def _publish_prior_real_computation(
    *,
    config: TWStockConfig,
    source_date: str,
    calculation: dict[str, object],
    custody: dict[str, object],
) -> dict[str, object]:
    """Publish the real pre-quick computation the cache hit must retain."""

    completed_at = source_date + "T05:30:00+00:00"
    computation = build_technical_computation_evidence(
        source_db=config.db_file,
        calculation_result=calculation,
        source_date_start=source_date,
        source_date_end=source_date,
        started_at=source_date + "T05:00:00+00:00",
        completed_at=completed_at,
        input_snapshot=capture_technical_input_snapshot(
            config.db_file,
            source_date_start=source_date,
            source_date_end=source_date,
        ),
    )
    result = dict(calculation)
    result["source_receipts"] = [
        {"receipt_path": str(item["receipt_path"])}
        for item in custody["captures"]
        if isinstance(item, dict) and item.get("receipt_path")
    ]
    result["technical_computation"] = computation
    publication = publish_technical_indicator_receipt(
        output_root=config.output_root,
        source_db=config.db_file,
        update_status={
            "status": "passed",
            "run_id": "fixture-pre-quick-" + source_date,
            "start_date": source_date,
            "end_date": source_date,
            "completed_at": completed_at,
            "steps": [
                {
                    "name": "calculate_technical_indicators",
                    "status": "passed",
                    "result": result,
                }
            ],
        },
    )
    assert publication["status"] == "published", publication
    receipt = json.loads(
        Path(str(publication["receipt_path"])).read_text(encoding="utf-8")
    )
    assert receipt["technical_computation_evidence_status"] == "verified"
    assert receipt["technical_computation_evidence"] == computation
    return receipt


def test_three_consecutive_cache_hits_retain_real_computation_receipts(
    _short_tmp_root: Path,
    monkeypatch,
) -> None:
    """Each 05:45 cache hit must remain capture-verifiable across three days."""

    shadow_root = _short_tmp_root / "FA_Data_Shadow"

    def _success(_service: UpdateService, *_args, **_kwargs) -> dict[str, object]:
        return {"success": True}

    # Isolate network and host-capacity side effects while preserving the real
    # UpdateService check_data_overview/coverage and technical calculator.
    for method_name in (
        "update_daily",
        "update_tpex_daily_price_range",
        "sync_source_to_sqlite",
        "update_market",
        "update_industry",
    ):
        monkeypatch.setattr(UpdateService, method_name, _success)
    monkeypatch.setattr(runner, "configured_candidate_db_path", lambda: None)
    monkeypatch.setattr(
        runner,
        "preflight_capacity",
        lambda **_kwargs: SimpleNamespace(
            as_dict=lambda: {
                "within_budget": True,
                "required_free_bytes": 0,
                "free_bytes": 0,
                "blockers": [],
            }
        ),
    )
    monkeypatch.setattr(
        runner,
        "acquire_heavy_chain_reservation",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        runner,
        "release_heavy_chain_reservation",
        lambda *_args, **_kwargs: None,
    )

    class _FixtureCalendar:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def require_trading_days_in_range(
            self,
            start_date: date,
            _end_date: date,
            *,
            allow_online_probe: bool,
        ) -> list[dict[str, object]]:
            assert allow_online_probe is True
            return [
                {
                    "date_str": start_date.isoformat(),
                    "date": start_date,
                    "is_trading_day": True,
                }
            ]

    monkeypatch.setattr(runner, "OfficialTradingCalendar", _FixtureCalendar)

    failures: list[str] = []
    cache_receipts: list[dict[str, object]] = []
    prior_receipts: list[dict[str, object]] = []
    for source_date in SOURCE_DATES:
        formal_root = _short_tmp_root / f"FA_Data_{source_date}"
        formal_output_root = formal_root / "output"
        config, calculation = _seed_actual_technical_db(
            formal_root,
            formal_output_root,
            source_date,
        )
        # The preceding data schedule owns the formal output root.  The quick
        # learning run is intentionally given only the sibling shadow root;
        # accepting a receipt created directly in shadow would miss the
        # cross-root custody defect this QA is meant to catch.
        custody = _capture_official_fixture(formal_output_root, source_date)
        prior_receipts.append(
            _publish_prior_real_computation(
                config=config,
                source_date=source_date,
                calculation=calculation,
                custody=custody,
            )
        )

        prior_audit = inspect_source_contract(
            data_root=formal_root,
            output_root=formal_output_root,
            source_db=config.db_file,
            decision_date=date.fromisoformat(source_date),
            symbols=SYMBOLS,
            history_start_date=(
                date.fromisoformat(source_date) - timedelta(days=34)
            ).isoformat(),
            availability_cutoff_at=source_date + "T06:00:00+00:00",
        )
        prior_inventory = (
            prior_audit["technical"].get("inventory")
            if isinstance(prior_audit.get("technical"), dict)
            else None
        )
        if not isinstance(prior_inventory, dict) or not all(
            prior_inventory.get(key) is True
            for key in (
                "technical_output_content_hash_verified",
                "technical_output_value_binding_verified",
                "technical_source_receipt_lineage_verified",
            )
        ):
            failures.append(
                f"{source_date}: formal prior receipt custody not ready: "
                f"{prior_audit.get('technical', {}).get('prospective_blockers')}"
            )

        monkeypatch.setattr(
            runner,
            "scheduled_now",
            lambda source_date=source_date: datetime.fromisoformat(
                source_date + "T05:45:00+00:00"
            ),
        )
        status_path = shadow_root / "scheduled" / f"quick-{source_date}.json"
        log_path = shadow_root / "scheduled" / f"quick-{source_date}.log"
        exit_code = runner.main(
            [
                "--data-root",
                str(formal_root),
                "--output-root",
                str(shadow_root),
                "--formal-output-root",
                str(formal_output_root),
                "--status-path",
                str(status_path),
                "--log-path",
                str(log_path),
                "--start-date",
                source_date,
                "--end-date",
                source_date,
                "--skip-broker-branch",
                "--daily-delay-seconds",
                "0",
                "--tpex-delay-seconds",
                "0",
                "--broker-delay-seconds",
                "0",
            ]
        )
        status = json.loads(status_path.read_text(encoding="utf-8"))
        assert exit_code == 0, status
        assert status["status"] in {"passed", "passed_with_warnings"}
        technical_step = next(
            step
            for step in status["steps"]
            if step["name"] == "calculate_technical_indicators"
        )
        assert technical_step["status"] in {"skipped", "passed"}
        if technical_step["status"] == "skipped":
            assert technical_step["result"]["skip_reason"] == "technical_indicators_current"
            assert isinstance(
                technical_step["result"].get("technical_computation_reuse"),
                dict,
            )
        else:
            # A bounded true recomputation is also acceptable when the runner
            # cannot safely reuse the prior witness across data roots.
            assert technical_step["result"]["success"] is True
            assert isinstance(technical_step["result"].get("technical_computation"), dict)

        publication = status["technical_publication_receipt"]
        if publication.get("status") != "published":
            failures.append(
                f"{source_date}: technical publication status="
                f"{publication.get('status')!r}, reason={publication.get('reason')!r}"
            )
            continue
        cache_receipt = json.loads(
            Path(str(publication["receipt_path"])).read_text(encoding="utf-8")
        )
        cache_receipts.append(cache_receipt)
        assert Path(str(publication["receipt_path"])).resolve().is_relative_to(
            shadow_root.resolve()
        )
        assert cache_receipt["technical_step_status"] == technical_step["status"]
        assert cache_receipt["source_date_start"] == source_date
        assert cache_receipt["source_date_end"] == source_date
        assert cache_receipt["source_receipts"]
        assert {
            item["source_date"] for item in cache_receipt["source_receipts"]
        } == {source_date}
        formal_raw_hashes = {
            str(item["raw_response_sha256"])
            for item in custody["captures"]
            if isinstance(item, dict) and item.get("raw_response_sha256")
        }
        assert {
            str(item["raw_response_sha256"])
            for item in cache_receipt["source_receipts"]
        } <= formal_raw_hashes
        assert all(
            Path(str(item["receipt_path"])).resolve().is_relative_to(
                formal_output_root.resolve()
            )
            for item in cache_receipt["source_receipts"]
        )
        assert cache_receipt["historical_pit_eligible"] is False
        assert cache_receipt["formal_source_contract_eligible"] is False

        audit = inspect_source_contract(
            data_root=formal_root,
            output_root=shadow_root,
            source_db=config.db_file,
            decision_date=date.fromisoformat(source_date),
            symbols=SYMBOLS,
            history_start_date=(
                date.fromisoformat(source_date) - timedelta(days=34)
            ).isoformat(),
            availability_cutoff_at=source_date + "T06:00:00+00:00",
        )
        technical_audit = audit["technical"]
        inventory = (
            technical_audit.get("inventory")
            if isinstance(technical_audit, dict)
            else None
        )
        if not isinstance(inventory, dict) or not all(
            inventory.get(key) is True
            for key in (
                "technical_output_content_hash_verified",
                "technical_output_value_binding_verified",
                "technical_source_receipt_lineage_verified",
            )
        ):
            failures.append(
                f"{source_date}: source audit technical custody not ready: "
                f"{technical_audit.get('prospective_blockers') if isinstance(technical_audit, dict) else technical_audit}"
            )

        # The prior receipt proves that this day had a real computation before
        # the quick runner.  The resulting publication must either reuse that
        # witness or carry a newly verified bounded recomputation witness so
        # downstream capture validation never has to guess.
        evidence = cache_receipt.get("technical_computation_evidence")
        if (
            cache_receipt.get("technical_computation_evidence_status") != "verified"
            or not isinstance(evidence, dict)
        ):
            failures.append(
                f"{source_date}: status="
                f"{cache_receipt.get('technical_computation_evidence_status')!r}, "
                f"evidence_present={isinstance(evidence, dict)}"
            )

    assert len(prior_receipts) == 3
    assert not failures, "cache-hit custody failures: " + "; ".join(failures)
    assert len(cache_receipts) == 3
