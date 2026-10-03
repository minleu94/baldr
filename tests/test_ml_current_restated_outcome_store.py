from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from data_module import ml_daily_price_revision_gate as revision_gate
from data_module import ml_pit_year_shard_exporter as raw_exporter
from data_module.ml_research_output_boundary import resolve_ml_research_output_path
from data_module.portfolio_ml_current_restated_outcome_store import (
    CurrentRestatedOutcomeStoreError,
    CurrentRestatedOutcomeStoreRequest,
    PortfolioMLCurrentRestatedOutcomeStoreBuilder,
    _assert_outcome_cost_difference,
    _build_research_folds,
    _fold_payload,
    _is_reviewed_daily_technical_derivation,
    _outcome_cost_contract_payload,
    _parse_outcome_cost_contract,
    _parse_folds,
    load_verified_current_restated_outcome_artifact,
)
from data_module.ml_pit_year_shard_exporter import (
    PITYearShardBuildRequest,
    PITYearShardExporter,
)
from tests.ml_research_test_support import (
    install_test_revision_gate,
    write_snapshot_context_receipt,
)


pytestmark = pytest.mark.usefixtures("synthetic_ml_capacity")


def _calendar(start: date, count: int) -> tuple[date, ...]:
    days: list[date] = []
    candidate = start
    while len(days) < count:
        if candidate.weekday() < 5:
            days.append(candidate)
        candidate += timedelta(days=1)
    return tuple(days)


def _make_database(path: Path, calendar: tuple[date, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE daily_prices (
                日期 TEXT NOT NULL,
                證券代號 TEXT NOT NULL,
                證券名稱 TEXT,
                成交股數 INTEGER,
                開盤價 TEXT,
                最高價 TEXT,
                最低價 TEXT,
                收盤價 TEXT,
                成交金額 INTEGER,
                本益比 TEXT
            );
            CREATE TABLE technical_indicators (
                日期 TEXT NOT NULL,
                證券代號 TEXT NOT NULL,
                最高價 TEXT,
                最低價 TEXT,
                收盤價 TEXT,
                ATR TEXT,
                ADX TEXT
            );
            CREATE TABLE market_indices (
                日期 TEXT NOT NULL,
                指數名稱 TEXT NOT NULL,
                開盤價 TEXT,
                最高價 TEXT,
                最低價 TEXT,
                收盤價 TEXT
            );
            """
        )
        stock_rows: list[tuple[object, ...]] = []
        technical_rows: list[tuple[object, ...]] = []
        benchmark_rows: list[tuple[object, ...]] = []
        for index, event_day in enumerate(calendar):
            date_text = event_day.strftime("%Y%m%d")
            for symbol, base, name in (
                ("2317", 300, "鴻海"),
                ("2330", 100, "台積電"),
            ):
                opened = base + index
                stock_rows.append(
                    (
                        date_text,
                        symbol,
                        name,
                        10_000_000 + index,
                        str(opened),
                        str(opened + 3),
                        str(opened - 2),
                        str(opened + 1),
                        7_654_181_137 + index,
                        "20.5",
                    )
                )
                technical_rows.append(
                    (
                        date_text,
                        symbol,
                        str(opened + 3),
                        str(opened - 2),
                        str(opened + 1),
                        None,
                        None,
                    )
                )
            market_open = 1_000 + index
            benchmark_rows.append(
                (
                    date_text,
                    "TAIEX",
                    str(market_open),
                    str(market_open + 4),
                    str(market_open - 3),
                    str(market_open + 2),
                )
            )
        connection.executemany(
            "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            stock_rows,
        )
        connection.executemany(
            "INSERT INTO technical_indicators VALUES (?, ?, ?, ?, ?, ?, ?)",
            technical_rows,
        )
        connection.executemany(
            "INSERT INTO market_indices VALUES (?, ?, ?, ?, ?, ?)",
            benchmark_rows,
        )


def _label_row(end_day: date, horizon: int) -> SimpleNamespace:
    return SimpleNamespace(horizon=horizon, horizon_end_date=end_day)


def _fold_observations(
    calendar: tuple[date, ...],
) -> tuple[SimpleNamespace, ...]:
    rows: list[SimpleNamespace] = []
    last_mature_index = len(calendar) - 61
    for event_index, event_day in enumerate(calendar):
        if event_index > last_mature_index or event_index == 300:
            continue
        for symbol in ("2317", "2330"):
            if event_index == 220 and symbol == "2317":
                continue
            labels = tuple(
                _label_row(calendar[event_index + horizon], horizon)
                for horizon in (5, 10, 20, 60)
            )
            rows.append(
                SimpleNamespace(
                    sample_id=f"{symbol}-{event_day.isoformat()}",
                    symbol=symbol,
                    event_date=event_day,
                    labels=labels,
                )
            )
    return tuple(rows)


def test_global_calendar_fold_indices_preserve_missing_sessions_and_revalidate() -> None:
    calendar = _calendar(date(2023, 1, 2), 700)
    observations = _fold_observations(calendar)
    published_calendar, folds = _build_research_folds(
        observations=observations,  # type: ignore[arg-type]
        minimum_train_dates=125,
        test_date_count=63,
        purge_trading_days=60,
        embargo_trading_days=5,
        benchmark_event_calendar=calendar,
        target_symbols=("2317", "2330"),
    )

    assert published_calendar == calendar
    assert calendar[300] not in {
        row.event_date for row in observations
    }
    assert len(folds) >= 4
    for fold in folds:
        assert fold.train_date_count >= 125
        assert fold.test_date_count == 63
        assert fold.test_date_indices[0] - fold.train_date_indices[-1] - 1 == 60
        assert fold.max_train_label_end_date < fold.test_start_date
        assert calendar[fold.test_date_indices[0]] == fold.test_start_date

    policy = {
        "label_end_must_be_strictly_before_test_start": True,
        "minimum_train_dates_after_purge": 125,
        "test_date_count": 63,
        "purge_trading_days": 60,
        "embargo_trading_days": 5,
        "minimum_fold_count": 4,
        "folds": [_fold_payload(fold) for fold in folds],
    }
    assert _parse_folds(
        policy,
        observations,  # type: ignore[arg-type]
        event_date_calendar=calendar,
        benchmark_event_calendar=calendar,
        target_symbols=("2317", "2330"),
    ) == folds

    with pytest.raises(CurrentRestatedOutcomeStoreError, match="complete pinned benchmark calendar"):
        _parse_folds(
            policy,
            observations,  # type: ignore[arg-type]
            event_date_calendar=calendar[:300] + calendar[301:],
            benchmark_event_calendar=calendar,
            target_symbols=("2317", "2330"),
        )

    wrong_purge = dict(policy)
    wrong_purge["purge_trading_days"] = 5
    with pytest.raises(CurrentRestatedOutcomeStoreError, match="below the research minimum"):
        _parse_folds(
            wrong_purge,
            observations,  # type: ignore[arg-type]
            event_date_calendar=calendar,
            benchmark_event_calendar=calendar,
            target_symbols=("2317", "2330"),
        )


def test_only_pinned_causal_daily_atr_adx_can_cross_registry_table_boundary() -> None:
    available = datetime(2026, 10, 3, 2, 47, 8, tzinfo=timezone.utc)
    row = {
        "source_id": "derived:daily_prices.ohlc",
        "family": "price_liquidity_technical",
    }
    value = {
        "derivation": {
            "method": "causal_wilder_prefix",
            "causal_prefix_only": True,
            "raw_feature_value_ignored": True,
            "input_columns": ["最高價", "最低價", "收盤價"],
            "period": 14,
            "derivation_hash": "a" * 64,
            "usable_from": available.isoformat(),
            "blocker": None,
        }
    }
    assert _is_reviewed_daily_technical_derivation(
        row=row,
        value=value,
        feature_id="technical_indicators.ATR",
        expected_table="technical_indicators",
        source_table="daily_prices",
        current_value_available_at=available,
    ) is True
    for row_patch, value_patch, feature_id in (
        ({"source_id": "daily_prices"}, {}, "technical_indicators.ATR"),
        ({"family": "other"}, {}, "technical_indicators.ATR"),
        ({}, {"method": "noncausal"}, "technical_indicators.ATR"),
        ({}, {"input_columns": ["收盤價", "最高價", "最低價"]}, "technical_indicators.ATR"),
        ({}, {"period": True}, "technical_indicators.ATR"),
        ({}, {"raw_feature_value_ignored": False}, "technical_indicators.ATR"),
        ({}, {}, "technical_indicators.RSI"),
    ):
        candidate_row = {**row, **row_patch}
        candidate_derivation = {**value["derivation"], **value_patch}
        candidate_value = {"derivation": candidate_derivation}
        assert (
            _is_reviewed_daily_technical_derivation(
                row=candidate_row,
                value=candidate_value,
                feature_id=feature_id,
                expected_table="technical_indicators",
                source_table="daily_prices",
                current_value_available_at=available,
            )
            is False
        )


def test_outcome_cost_contract_pins_net_excess_semantics() -> None:
    payload = _outcome_cost_contract_payload()
    contract = _parse_outcome_cost_contract(payload)
    assert contract.buy_side_cost_bp == 25
    assert contract.sell_side_cost_bp == 55
    assert contract.total_round_trip_cost_bp == 80
    assert contract.gross_stock_return_metric == "stock_return_bp"
    assert contract.gross_benchmark_return_metric == "benchmark_return_bp"
    assert contract.net_excess_metric == "benchmark_excess_return_bp"

    _assert_outcome_cost_difference(
        stock_return_bp=120,
        benchmark_return_bp=50,
        benchmark_excess_return_bp=-10,
    )
    with pytest.raises(CurrentRestatedOutcomeStoreError, match="pinned 80bp"):
        _assert_outcome_cost_difference(
            stock_return_bp=120,
            benchmark_return_bp=50,
            benchmark_excess_return_bp=-9,
        )

    wrong_cost = dict(payload)
    wrong_cost["sell_side_cost_bp"] = 54
    with pytest.raises(CurrentRestatedOutcomeStoreError, match="pinned standard"):
        _parse_outcome_cost_contract(wrong_cost)
    bool_cost = dict(payload)
    bool_cost["buy_side_cost_bp"] = True
    with pytest.raises(CurrentRestatedOutcomeStoreError, match="exact integer"):
        _parse_outcome_cost_contract(bool_cost)


def test_current_restated_annual_raw_to_outcome_loader_positive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calendar = _calendar(date(2024, 1, 1), 700)
    snapshot = tmp_path / "snapshot.sqlite"
    _make_database(snapshot, calendar)
    install_test_revision_gate(monkeypatch)

    now = datetime.now(timezone.utc).replace(microsecond=0)
    source_observed_at = now - timedelta(seconds=30)
    decision_at = now - timedelta(seconds=20)
    training_as_of = now - timedelta(seconds=10)
    context_receipt, context_receipt_sha = write_snapshot_context_receipt(
        snapshot,
        tmp_path,
        completed_at=source_observed_at.isoformat(),
    )
    snapshot_sha = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    original_database = (
        tmp_path / "source_context" / "original_source.sqlite"
    )
    context = revision_gate.load_verified_current_restated_source_context(
        snapshot,
        context_receipt,
        expected_snapshot_database_sha256=snapshot_sha,
        expected_snapshot_receipt_sha256=context_receipt_sha,
        original_database_path=original_database,
        decision_at=decision_at,
        training_as_of=training_as_of,
    )

    def research_root(path: Path, *, repository_root: Path | None = None) -> Path:
        return resolve_ml_research_output_path(
            path,
            repository_root=repository_root or tmp_path,
        )

    monkeypatch.setattr(raw_exporter, "resolve_ml_research_output_path", research_root)
    raw_root = tmp_path / "output" / "ml_research" / "raw"
    years = tuple(sorted({item.year for item in calendar}))
    raw_publication = PITYearShardExporter().build(
        PITYearShardBuildRequest(
            database_path=snapshot,
            output_root=raw_root,
            decision_at=decision_at.isoformat(),
            history_start_date=calendar[0].isoformat(),
            symbols=("2317", "2330"),
            years=years,
            allow_source_revision_research=True,
            current_restated_source_context=context,
            batch_size=512,
        )
    )
    raw_manifest_path = raw_publication.manifest_path
    raw_manifest = json.loads(raw_manifest_path.read_text(encoding="utf-8"))
    raw_child_path = Path(raw_manifest["datasets"]["core_long_history"]["manifest_path"])
    if not raw_child_path.is_absolute():
        raw_child_path = raw_manifest_path.parent / raw_child_path
    raw_child = json.loads(raw_child_path.read_text(encoding="utf-8"))
    publication_sha = hashlib.sha256(raw_manifest_path.read_bytes()).hexdigest()
    child_sha = hashlib.sha256(raw_child_path.read_bytes()).hexdigest()

    monkeypatch.setattr(
        raw_exporter,
        "resolve_ml_research_output_path",
        research_root,
    )
    from data_module import portfolio_ml_current_restated_outcome_store as outcome_module

    monkeypatch.setattr(outcome_module, "resolve_ml_research_output_path", research_root)
    outcome_publication = PortfolioMLCurrentRestatedOutcomeStoreBuilder().build(
        CurrentRestatedOutcomeStoreRequest(
            raw_publication_manifest_path=raw_manifest_path,
            expected_raw_publication_manifest_sha256=publication_sha,
            expected_raw_dataset_manifest_sha256=child_sha,
            output_root=tmp_path / "output" / "ml_research" / "outcomes",
            benchmark_entity_id="TAIEX",
            target_symbols=("2317", "2330"),
            minimum_train_dates=125,
            test_date_count=63,
            purge_trading_days=60,
            embargo_trading_days=5,
            repository_root=tmp_path,
        )
    )
    assert outcome_publication.fold_count >= 4
    outcome_manifest = json.loads(
        outcome_publication.manifest_path.read_text(encoding="utf-8")
    )
    assert outcome_manifest["event_date_calendar"] == [
        item.isoformat() for item in calendar
    ]
    assert outcome_manifest["safety"]["formal_training_allowed"] is False
    assert outcome_manifest["source_pins"]["raw_publication_manifest"]["sha256"] == publication_sha
    assert outcome_manifest["outcome_cost_contract"] == _outcome_cost_contract_payload()

    fit_freeze = datetime.now(timezone.utc) + timedelta(seconds=5)
    verified = load_verified_current_restated_outcome_artifact(
        outcome_publication.manifest_path,
        expected_artifact_receipt_sha256=outcome_publication.manifest_sha256,
        expected_raw_publication_manifest_sha256=publication_sha,
        expected_raw_dataset_manifest_sha256=child_sha,
        expected_feature_registry_sha256=outcome_publication.feature_registry_sha256,
        available_at_or_before=fit_freeze,
        repository_root=tmp_path,
    )
    assert verified.status == "current_restated_outcome_numeric_ready"
    assert verified.historical_pit_eligible is False
    assert verified.formal_training_eligible is False
    assert verified.full_teacher_qualified is False
    assert verified.teacher_targets_present is False
    assert verified.outcome_cost_contract.buy_side_cost_bp == 25
    assert verified.outcome_cost_contract.sell_side_cost_bp == 55
    assert verified.outcome_cost_contract.total_round_trip_cost_bp == 80
    assert verified.event_date_calendar == calendar
    assert len(verified.folds) >= 4

    registry_index = {
        item.feature_id: index
        for index, item in enumerate(verified.feature_registry)
    }
    amount_index = registry_index["stock/daily_prices.成交金額"]
    amount_feature = verified.feature_registry[amount_index]
    assert amount_feature.unit == "TWD"
    assert amount_feature.decimal_exponent == 0
    first_stock = next(
        row
        for row in verified.observations
        if row.symbol == "2330" and row.event_date == calendar[0]
    )
    mature_stock = next(
        row
        for row in verified.observations
        if row.symbol == "2317" and row.event_date == calendar[35]
    )
    mature_source_identities = {
        (source.source_table, source.source_id)
        for source in mature_stock.source_rows
    }
    assert ("daily_prices", "sqlite.daily_prices") in mature_source_identities
    assert ("daily_prices", "derived:daily_prices.ohlc") in mature_source_identities
    atr_index = next(
        index
        for index, item in enumerate(verified.feature_registry)
        if item.source_feature_id == "technical_indicators.ATR"
    )
    adx_index = next(
        index
        for index, item in enumerate(verified.feature_registry)
        if item.source_feature_id == "technical_indicators.ADX"
    )
    assert mature_stock.missing_mask[atr_index] is False
    assert mature_stock.missing_mask[adx_index] is False
    assert mature_stock.feature_values[atr_index] > 0
    assert mature_stock.feature_values[adx_index] > 0
    assert first_stock.feature_values[amount_index] == 7_654_181_137
    assert first_stock.missing_mask[amount_index] is False
    label_60 = next(label for label in first_stock.labels if label.horizon == 60)
    assert label_60.benchmark_excess_return_bp == (
        label_60.stock_return_bp - label_60.benchmark_return_bp - 80
    )
    assert label_60.next_entry_date == calendar[1]
    assert label_60.horizon_end_date == calendar[60]
    assert label_60.stock_next_entry_open_value_int == 1_010_000
    assert label_60.stock_next_entry_open_decimal_exponent == 4
    assert label_60.stock_exit_close_value_int == 1_610_000
    assert label_60.stock_exit_close_decimal_exponent == 4
    assert label_60.stock_path_source_hashes
    assert label_60.benchmark_path_source_hashes

    with pytest.raises(CurrentRestatedOutcomeStoreError, match="caller-pinned bytes"):
        PortfolioMLCurrentRestatedOutcomeStoreBuilder().build(
            CurrentRestatedOutcomeStoreRequest(
                raw_publication_manifest_path=raw_manifest_path,
                expected_raw_publication_manifest_sha256="0" * 64,
                expected_raw_dataset_manifest_sha256=child_sha,
                output_root=tmp_path / "output" / "ml_research" / "wrong_pin",
                benchmark_entity_id="TAIEX",
                target_symbols=("2317", "2330"),
                repository_root=tmp_path,
            )
        )
