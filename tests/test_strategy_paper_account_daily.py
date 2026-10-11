"""策略 Paper 帳戶 daily checkpoint 的隔離契約測試。"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, ROUND_HALF_UP, localcontext
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

import app_module.strategy_paper_account_availability as availability_module
import app_module.strategy_paper_account_cash_seed_writer as seed_writer_module
from app_module.paper_portfolio_policy import PaperPortfolioPolicyConfig
from app_module.paper_portfolio_snapshot_repository import (
    PaperPortfolioPositionSnapshot,
    PaperPortfolioSnapshot,
    PaperPortfolioSnapshotRepository,
)
from app_module.paper_trade_ledger import (
    PaperTradeFill,
    PaperTradeLedgerRepository,
    PaperTradeTransition,
)
from app_module.personal_data_paths import PersonalDataPaths
from app_module.personal_paper_store_paths import (
    PersonalPaperStorePaths,
    PersonalStoreCustody,
)
from app_module.strategy_paper_account_cash_seed_writer import (
    StrategyPaperAccountCashSeedWriter,
)
from app_module.strategy_paper_account_daily import (
    DailyPriceScalarEvidence,
    DailyQuoteEventReceipt,
    StrategyPaperAccountDailyError,
    StrategyPaperAccountDailyWriter,
)
from app_module.strategy_paper_account_availability import (
    StrategyPaperAccountAvailabilityError,
    read_exact_strategy_paper_account_checkpoint,
    read_exact_strategy_paper_account_availability,
)
from app_module.strategy_paper_account_service import (
    StrategyPaperAccountBinding,
    StrategyPaperAccountService,
    canonical_sha256,
    file_sha256,
)
from app_module.strategy_version_service import StrategyVersion


class _RecommendationQueries:
    def __init__(self, rows: dict[str, object]) -> None:
        self.rows = rows

    def get(self, result_id: str) -> object | None:
        return self.rows.get(result_id)


def _write_json(path: Path, payload: object) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    path.write_bytes(raw)
    return raw


def _create_account(tmp_path: Path) -> tuple[
    StrategyPaperAccountService, PersonalDataPaths, dict[str, object]
]:
    market_root = tmp_path / "m"
    paths = PersonalDataPaths(
        market_root=market_root,
        legacy_output_root=tmp_path / "l",
        personal_root=tmp_path / "p",
    )
    strategy_root = tmp_path / "strategy-versions-copy"
    contract_root = tmp_path / "contracts-copy"
    policy = PaperPortfolioPolicyConfig()
    policy_payload = asdict(policy)
    policy_payload["initial_capital"] = str(policy.initial_capital)
    contract_artifacts = (
        (
            "paper_policies",
            "paper_policy_default",
            "v1",
            {
                "artifact_type": "paper_policies",
                "artifact_id": "paper_policy_default",
                "version": "v1",
                "policy": policy_payload,
            },
        ),
        (
            "cost_models",
            "taiwan_paper_cost",
            "v1",
            {
                "artifact_type": "cost_models",
                "artifact_id": "taiwan_paper_cost",
                "version": "v1",
                "cost_model": {
                    "commission_bp_per_side": policy.commission_bp_per_side,
                    "slippage_bp_per_side": policy.slippage_bp_per_side,
                    "sell_tax_bp": policy.sell_tax_bp,
                },
            },
        ),
        (
            "benchmarks",
            "equal_weight_frozen",
            "v1",
            {
                "artifact_type": "benchmarks",
                "artifact_id": "equal_weight_frozen",
                "version": "v1",
                "method": "equal_weight_frozen_constituents.v1",
                "source_sha256": "sha256:" + "a" * 64,
            },
        ),
    )
    hashes: dict[str, str] = {}
    for directory, artifact_id, version, payload in contract_artifacts:
        raw = _write_json(
            contract_root / directory / f"{artifact_id}__{version}.json", payload
        )
        hashes[directory] = file_sha256(raw)

    params = {"entry_threshold": 0.75, "confirm_days": 3}
    config = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}
    strategy = StrategyVersion(
        version_id="version-daily",
        strategy_id="strategy-daily",
        strategy_version="1.0.0",
        source_run_id="run-version-daily",
        promoted_at="2026-08-01T00:00:00+00:00",
        params=params,
        config=config,
        backtest_summary={},
        regime=["Trend"],
        profile_id=None,
        profile_version=None,
        validation_status="validated",
        validation_metrics={},
        notes=None,
    )
    strategy_raw = _write_json(strategy_root / "version-daily.json", strategy.to_dict())
    manifest = StrategyPaperAccountBinding.create_manifest_payload(
        strategy_version_id="version-daily",
        strategy_id="strategy-daily",
        strategy_version="1.0.0",
        strategy_artifact_sha256=file_sha256(strategy_raw),
        params_sha256=canonical_sha256(params),
        config_sha256=canonical_sha256(config),
        source_run_id="run-version-daily",
        policy_id="paper_policy_default",
        policy_version="v1",
        policy_sha256=hashes["paper_policies"],
        cost_model_id="taiwan_paper_cost",
        cost_model_version="v1",
        cost_model_sha256=hashes["cost_models"],
        benchmark_id="equal_weight_frozen",
        benchmark_version="v1",
        benchmark_sha256=hashes["benchmarks"],
        start_date="2026-08-01",
        initial_capital="500000",
        max_positions=8,
    )
    account_dir = (
        paths.personal_root
        / "paper_portfolio"
        / "accounts"
        / str(manifest["account_namespace"])
    )
    _write_json(account_dir / "account_binding.json", manifest)
    service = StrategyPaperAccountService(
        personal_paths=paths,
        strategy_versions_root=strategy_root,
        contract_artifacts_root=contract_root,
    )
    return service, paths, manifest


def _seed_account(
    service: StrategyPaperAccountService,
    paths: PersonalDataPaths,
    manifest: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    *,
    created_at: datetime = datetime(2026, 8, 1, 8, 10, tzinfo=timezone.utc),
) -> tuple[PaperPortfolioSnapshot, PersonalPaperStorePaths, object]:
    monkeypatch.setattr(
        seed_writer_module,
        "_utc_now",
        lambda: created_at,
    )
    seed = StrategyPaperAccountCashSeedWriter(
        account_service=service,
        personal_paths=paths,
    ).create_cash_seed(
        strategy_id=str(manifest["strategy_id"]),
        strategy_version_id=str(manifest["strategy_version_id"]),
        account_namespace=str(manifest["account_namespace"]),
    )
    selected = service.select_exact_version(
        strategy_id=str(manifest["strategy_id"]),
        strategy_version_id=str(manifest["strategy_version_id"]),
        account_namespace=str(manifest["account_namespace"]),
    )
    assert selected.route is not None and selected.binding is not None
    store_paths = PersonalPaperStorePaths.from_route(
        selected.route, portfolio_id=selected.binding.portfolio_id
    )
    PaperTradeLedgerRepository(
        store_paths.cost_ledger_db,
        route=selected.route,
        personal_paths=paths,
        portfolio_id=selected.binding.portfolio_id,
    )
    return seed.snapshot, store_paths, selected.binding


def _saved_execution(
    *,
    result_id: str,
    strategy_version_id: str,
    config: dict[str, object],
    decision_at: datetime | None = None,
) -> object:
    spec = {
        "schema": "strategy-config.v1",
        "max_stocks": 10,
        "top_n": 8,
        "config": config,
    }
    config_hash = canonical_sha256(spec)
    identity = SimpleNamespace(
        strategy_version_id=strategy_version_id,
        strategy_config_hash=config_hash,
        strategy_config_id=(
            "recommendation-strategy-config-v1:" + config_hash.removeprefix("sha256:")
        ),
        strategy_config_spec_json=json.dumps(
            spec, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ),
    )
    decision = decision_at or datetime(2026, 8, 2, 8, 20, tzinfo=timezone.utc)
    execution = SimpleNamespace(
        result_id=result_id,
        status=SimpleNamespace(value="completed"),
        context=SimpleNamespace(
            strategy_identity=identity,
            decision_at=decision,
            created_at=datetime(2026, 8, 2, 8, 15, tzinfo=timezone.utc),
            available_at=datetime(2026, 8, 2, 8, 18, tzinfo=timezone.utc),
        ),
    )
    return SimpleNamespace(
        execution=execution,
        result_id=result_id,
        integrity_basis="canonical_payload_and_index_verified",
        persisted_at=datetime(2026, 8, 2, 8, 25, tzinfo=timezone.utc),
        raw_artifact_sha256="sha256:" + "1" * 64,
        payload_hash="sha256:" + "2" * 64,
        artifact_location=f"isolated://{result_id}",
    )


@pytest.mark.parametrize("config_spec_json", [None, "{"])
def test_saved_execution_rejects_missing_or_malformed_config_spec(
    config_spec_json: object,
) -> None:
    read_model = _saved_execution(
        result_id="result-invalid-config-spec",
        strategy_version_id="version-daily",
        config={"entry": {"type": "breakout"}},
    )
    read_model.execution.context.strategy_identity.strategy_config_spec_json = (
        config_spec_json
    )
    binding = SimpleNamespace(
        strategy_version_id="version-daily",
        config_sha256=canonical_sha256({"entry": {"type": "breakout"}}),
    )

    with pytest.raises(
        StrategyPaperAccountDailyError,
        match="strategy_account_execution_config_spec_missing",
    ):
        StrategyPaperAccountDailyWriter._validate_saved_execution(
            read_model,
            result_id="result-invalid-config-spec",
            binding=binding,
            decision_cutoff=datetime(2026, 8, 2, 9, 0, tzinfo=timezone.utc),
        )


def _price_evidence(
    *,
    source_date: str,
    stock_code: str,
    column: str,
    value: Decimal | int,
    row_hash: str = "sha256:" + "3" * 64,
    observed_at: datetime = datetime(2026, 8, 3, 6, 0, tzinfo=timezone.utc),
    written_at: datetime = datetime(2026, 8, 3, 6, 30, tzinfo=timezone.utc),
) -> DailyPriceScalarEvidence:
    return DailyPriceScalarEvidence(
        source_date=source_date,
        stock_code=stock_code,
        scalar_column=column,
        scalar_value=value,
        source_id="isolated-publication",
        parser_id="test-parser-v1",
        first_observed_at=observed_at,
        written_at=written_at,
        raw_response_sha256="sha256:" + "4" * 64,
        custody_receipt_sha256="sha256:" + "5" * 64,
        observation_receipt_sha256="sha256:" + "6" * 64,
        csv_sha256="sha256:" + "7" * 64,
        projection_row_sha256=row_hash,
        sqlite_projection_row_sha256=row_hash,
        projection_columns=("開盤價", "收盤價", "成交股數"),
    )


def _writer(
    service: StrategyPaperAccountService,
    paths: PersonalDataPaths,
    result_id: str,
    config: dict[str, object],
    *,
    strategy_version_id: str = "version-daily",
) -> StrategyPaperAccountDailyWriter:
    read_model = _saved_execution(
        result_id=result_id,
        strategy_version_id=strategy_version_id,
        config=config,
    )
    return StrategyPaperAccountDailyWriter(
        account_service=service,
        recommendation_queries=_RecommendationQueries({result_id: read_model}),
        personal_paths=paths,
    )


def _zero_fill_call(
    writer: StrategyPaperAccountDailyWriter,
    binding: object,
    prior: PaperPortfolioSnapshot,
    *,
    result_id: str,
    low_precision: bool = False,
    execution_date: str = "2026-08-03",
    snapshot_date: str = "2026-08-04",
    decision_cutoff: datetime = datetime(2026, 8, 2, 8, 30, tzinfo=timezone.utc),
) -> object:
    snapshot = PaperPortfolioSnapshot(
        snapshot_id=f"{binding.portfolio_id}-{snapshot_date.replace('-', '')}",
        portfolio_id=binding.portfolio_id,
        decision_date=snapshot_date,
        source_result_id=result_id,
        cash=prior.cash,
        total_value=prior.cash,
        positions=(),
    )
    def write_checkpoint() -> object:
        return writer.write_checkpoint(
            strategy_id=binding.strategy_id,
            strategy_version_id=binding.strategy_version_id,
            account_namespace=binding.account_namespace,
            result_id=result_id,
            decision_cutoff=decision_cutoff,
            execution_date=execution_date,
            mark_cutoff=datetime.fromisoformat(execution_date).replace(
                hour=7, tzinfo=timezone.utc
            ),
            prior_snapshot_id=prior.snapshot_id,
            snapshot=snapshot,
            fills=(),
            transition=None,
            mark_prices=(),
            execution_prices=(),
            quote_event_receipts=(),
        )

    if low_precision:
        with localcontext(Context(prec=3)):
            return write_checkpoint()
    return write_checkpoint()


def _fill_call(
    writer: StrategyPaperAccountDailyWriter,
    binding: object,
    prior: PaperPortfolioSnapshot,
    *,
    result_id: str,
    quote_receipts: tuple[DailyQuoteEventReceipt, ...] | None = None,
    low_precision: bool = False,
    weight_offset: int = 0,
) -> object:
    execution_date = "2026-08-03"
    snapshot_date = "2026-08-04"
    fill_price = Decimal("100.10")
    quantity = 1000
    gross = fill_price * quantity
    commission = Decimal("15.02")
    post_cash = (prior.cash - gross - commission).quantize(Decimal("0.01"))
    mark_price = Decimal("102.00")
    market_value = mark_price * quantity
    total_value = post_cash + market_value
    weight_bp = int(
        (market_value / total_value * Decimal("10000")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    snapshot = PaperPortfolioSnapshot(
        snapshot_id=f"{binding.portfolio_id}-20260804",
        portfolio_id=binding.portfolio_id,
        decision_date=snapshot_date,
        source_result_id=result_id,
        cash=post_cash,
        total_value=total_value,
        positions=(
            PaperPortfolioPositionSnapshot(
                stock_code="2330",
                quantity=quantity,
                mark_price=mark_price,
                market_value=market_value,
                weight_bp=weight_bp + weight_offset,
            ),
        ),
    )
    fill = PaperTradeFill(
        fill_id="daily-fill-20260803-2330",
        order_id="daily-order-20260803-2330",
        portfolio_id=binding.portfolio_id,
        event_date=execution_date,
        stock_code="2330",
        side="buy",
        requested_quantity=quantity,
        filled_quantity=quantity,
        reference_price=Decimal("100.00"),
        fill_price=fill_price,
        commission=commission,
        tax=Decimal("0.00"),
        slippage_cost=Decimal("100.00"),
        turnover_bp=2002,
        execution_gap_bp=10,
        status="filled",
        source_event_id="daily-event-20260803-2330",
    )
    transition = PaperTradeTransition(
        transition_id="daily-transition-20260803",
        batch_id="daily-batch-20260803",
        portfolio_id=binding.portfolio_id,
        event_date=execution_date,
        fill_ids=(fill.fill_id,),
        pre_cash=prior.cash,
        pre_total_value=Decimal("500000.00"),
        post_cash=post_cash,
        post_total_value=post_cash + Decimal("100000.00"),
        common_nav=Decimal("500000.00"),
        common_prices={"2330": Decimal("100.00")},
        pre_positions={},
        post_positions={"2330": quantity},
    )
    execution_open = _price_evidence(
        source_date=execution_date,
        stock_code="2330",
        column="開盤價",
        value=Decimal("100.00"),
    )
    execution_volume = _price_evidence(
        source_date=execution_date,
        stock_code="2330",
        column="成交股數",
        value=100000,
    )
    mark_close = _price_evidence(
        source_date=execution_date,
        stock_code="2330",
        column="收盤價",
        value=mark_price,
    )
    quote = DailyQuoteEventReceipt.create(
        receipt_id="quote-event-20260803-2330",
        stock_code="2330",
        source_date=execution_date,
        projection_row_sha256=execution_open.projection_row_sha256,
        event_at=datetime(2026, 8, 3, 1, 30, tzinfo=timezone.utc),
    )
    def write_checkpoint() -> object:
        return writer.write_checkpoint(
            strategy_id=binding.strategy_id,
            strategy_version_id=binding.strategy_version_id,
            account_namespace=binding.account_namespace,
            result_id=result_id,
            decision_cutoff=datetime(2026, 8, 2, 8, 30, tzinfo=timezone.utc),
            execution_date=execution_date,
            mark_cutoff=datetime(2026, 8, 3, 7, 0, tzinfo=timezone.utc),
            prior_snapshot_id=prior.snapshot_id,
            snapshot=snapshot,
            fills=(fill,),
            transition=transition,
            mark_prices=(mark_close,),
            execution_prices=(execution_open, execution_volume),
            quote_event_receipts=(quote,) if quote_receipts is None else quote_receipts,
        )

    if low_precision:
        with localcontext(Context(prec=3)):
            return write_checkpoint()
    return write_checkpoint()


def test_zero_fill_checkpoint_has_explicit_ledger_marker_and_exact_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    prior, store_paths, binding = _seed_account(service, paths, manifest, monkeypatch)
    config = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}
    writer = _writer(service, paths, "result-zero", config)

    result = _zero_fill_call(writer, binding, prior, result_id="result-zero")
    retry = _zero_fill_call(writer, binding, prior, result_id="result-zero")

    assert result.status == "appended"
    assert retry.status == "already_committed"
    assert result.operation_id == retry.operation_id
    assert result.performance_eligible is False
    assert result.availability_sha256 is not None
    assert result.persisted_at is not None
    assert result.available_at is not None
    assert result.available_at >= result.persisted_at
    route = service.select_exact_version(
        strategy_id=binding.strategy_id,
        strategy_version_id=binding.strategy_version_id,
        account_namespace=binding.account_namespace,
    ).route
    assert route is not None
    ledger = PaperTradeLedgerRepository(
        store_paths.cost_ledger_db,
        route=route,
        personal_paths=paths,
        portfolio_id=binding.portfolio_id,
        read_only=True,
    )
    marker = ledger.get_daily_operation(result.operation_id, portfolio_id=binding.portfolio_id)
    assert marker is not None and marker.zero_fill is True
    assert marker.ordered_fill_ids == ()
    state = PaperPortfolioSnapshotRepository(
        store_paths.state_db,
        portfolio_id=binding.portfolio_id,
        personal_paths=paths,
    )
    saved = state.get(result.snapshot_id)
    assert saved is not None
    assert saved.cash == Decimal("500000.00")
    assert saved.positions == ()
    with PersonalStoreCustody(route, paths).read_sqlite(store_paths.state_db) as connection:
        receipt = connection.execute(
            "SELECT receipt_json, receipt_sha256 FROM strategy_paper_account_daily_receipts "
            "WHERE snapshot_id = ?",
            (result.snapshot_id,),
        ).fetchone()
    payload = json.loads(receipt[0])
    assert payload["ordered_fill_ids"] == []
    assert payload["zero_fill"] is True
    assert payload["snapshot_id"] == result.snapshot_id
    assert receipt[1] == result.receipt_sha256
    availability_before = _read_availability(
        store_paths.state_db, paths, route, result, binding
    )
    availability_after = _read_availability(
        store_paths.state_db, paths, route, retry, binding
    )
    assert availability_before.receipt_sha256 == availability_after.receipt_sha256
    assert availability_before.available_at == availability_after.available_at
    assert availability_before.receipt_sha256 == result.availability_sha256

def test_fill_checkpoint_binds_quote_row_and_replays_cash_and_holdings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    prior, store_paths, binding = _seed_account(service, paths, manifest, monkeypatch)
    config = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}
    writer = _writer(service, paths, "result-fill", config)

    result = _fill_call(writer, binding, prior, result_id="result-fill")

    assert result.status == "appended"
    assert result.performance_eligible is False
    route = service.select_exact_version(
        strategy_id=binding.strategy_id,
        strategy_version_id=binding.strategy_version_id,
        account_namespace=binding.account_namespace,
    ).route
    assert route is not None
    ledger = PaperTradeLedgerRepository(
        store_paths.cost_ledger_db,
        route=route,
        personal_paths=paths,
        portfolio_id=binding.portfolio_id,
        read_only=True,
    )
    fills = ledger.list(portfolio_id=binding.portfolio_id)
    assert tuple(item.fill_id for item in fills) == ("daily-fill-20260803-2330",)
    assert fills[0].cash_settlement_cost == Decimal("15.02")
    assert fills[0].total_cost == Decimal("115.02")
    transition = ledger.list_transitions(portfolio_id=binding.portfolio_id)[0]
    assert transition.fill_ids == (fills[0].fill_id,)
    assert transition.pre_cash == Decimal("500000.00")
    assert transition.post_cash == Decimal("399884.98")
    state = PaperPortfolioSnapshotRepository(
        store_paths.state_db,
        portfolio_id=binding.portfolio_id,
        personal_paths=paths,
    )
    saved = state.get(result.snapshot_id)
    assert saved is not None
    assert saved.cash == Decimal("399884.98")
    assert tuple((item.stock_code, item.quantity) for item in saved.positions) == (
        ("2330", 1000),
    )
    assert saved.total_value == Decimal("501884.98")
    assert result.blockers == (
        "governed_quote_event_clock_not_available_for_performance_qualification",
        "official_trading_calendar_and_session_gate_unverified",
        "bound_cost_policy_not_recomputed_by_shared_fill_engine",
    )


@pytest.mark.parametrize("fill_mode", ["zero", "buy"])
def test_low_decimal_precision_context_accepts_zero_or_buy_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fill_mode: str,
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    prior, _, binding = _seed_account(service, paths, manifest, monkeypatch)
    config = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}
    result_id = f"result-low-context-{fill_mode}"
    writer = _writer(service, paths, result_id, config)

    if fill_mode == "zero":
        result = _zero_fill_call(
            writer,
            binding,
            prior,
            result_id=result_id,
            low_precision=True,
        )
    else:
        result = _fill_call(
            writer,
            binding,
            prior,
            result_id=result_id,
            low_precision=True,
        )

    assert result.status == "appended"


def test_daily_writer_rejects_snapshot_weight_that_is_one_bp_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    prior, store_paths, binding = _seed_account(service, paths, manifest, monkeypatch)
    config = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}
    writer = _writer(service, paths, "result-wrong-weight-bp", config)
    before = PaperTradeLedgerRepository(store_paths.cost_ledger_db).rowset_hash()

    with pytest.raises(
        StrategyPaperAccountDailyError,
        match="strategy_account_snapshot_position_weight_mismatch",
    ):
        _fill_call(
            writer,
            binding,
            prior,
            result_id="result-wrong-weight-bp",
            weight_offset=1,
        )

    assert PaperTradeLedgerRepository(store_paths.cost_ledger_db).rowset_hash() == before


def test_low_decimal_precision_context_accepts_sell_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    seed, store_paths, binding = _seed_account(service, paths, manifest, monkeypatch)
    monkeypatch.setattr(
        availability_module,
        "_utc_now",
        lambda: datetime(2026, 8, 4, 8, 25, tzinfo=timezone.utc),
    )
    config = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}
    buy_result_id = "result-sell-setup-buy"
    buy_result = _fill_call(
        _writer(service, paths, buy_result_id, config),
        binding,
        seed,
        result_id=buy_result_id,
    )
    selected = service.select_exact_version(
        strategy_id=binding.strategy_id,
        strategy_version_id=binding.strategy_version_id,
        account_namespace=binding.account_namespace,
    )
    assert selected.route is not None
    prior_repository = PaperPortfolioSnapshotRepository(
        store_paths.state_db,
        route=selected.route,
        portfolio_id=binding.portfolio_id,
        personal_paths=paths,
    )
    prior = prior_repository.get(buy_result.snapshot_id)
    assert prior is not None
    monkeypatch.setattr(
        availability_module,
        "_utc_now",
        lambda: datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc),
    )

    result_id = "result-low-context-sell"
    writer = _writer(service, paths, result_id, config)
    execution_date = "2026-08-05"
    snapshot_date = "2026-08-06"
    fill_price = Decimal("101.90")
    gross = Decimal("101900.00")
    commission = Decimal("152.85")
    tax = Decimal("305.70")
    post_cash = prior.cash + gross - commission - tax
    snapshot = PaperPortfolioSnapshot(
        snapshot_id=f"{binding.portfolio_id}-20260806",
        portfolio_id=binding.portfolio_id,
        decision_date=snapshot_date,
        source_result_id=result_id,
        cash=post_cash,
        total_value=post_cash,
        positions=(),
    )
    fill = PaperTradeFill(
        fill_id="daily-sell-fill-20260805-2330",
        order_id="daily-sell-order-20260805-2330",
        portfolio_id=binding.portfolio_id,
        event_date=execution_date,
        stock_code="2330",
        side="sell",
        requested_quantity=1000,
        filled_quantity=1000,
        reference_price=Decimal("102.00"),
        fill_price=fill_price,
        commission=commission,
        tax=tax,
        slippage_cost=Decimal("100.00"),
        turnover_bp=2032,
        execution_gap_bp=-10,
        status="filled",
        source_event_id="daily-sell-event-20260805-2330",
    )
    transition = PaperTradeTransition(
        transition_id="daily-sell-transition-20260805",
        batch_id="daily-sell-batch-20260805",
        portfolio_id=binding.portfolio_id,
        event_date=execution_date,
        fill_ids=(fill.fill_id,),
        pre_cash=prior.cash,
        pre_total_value=prior.total_value,
        post_cash=post_cash,
        post_total_value=post_cash,
        common_nav=prior.total_value,
        common_prices={"2330": Decimal("102.00")},
        pre_positions={"2330": 1000},
        post_positions={},
    )
    observed_at = datetime(2026, 8, 5, 1, 0, tzinfo=timezone.utc)
    written_at = datetime(2026, 8, 5, 1, 30, tzinfo=timezone.utc)
    execution_open = _price_evidence(
        source_date=execution_date,
        stock_code="2330",
        column="開盤價",
        value=Decimal("102.00"),
        observed_at=observed_at,
        written_at=written_at,
    )
    execution_volume = _price_evidence(
        source_date=execution_date,
        stock_code="2330",
        column="成交股數",
        value=100000,
        observed_at=observed_at,
        written_at=written_at,
    )
    quote = DailyQuoteEventReceipt.create(
        receipt_id="quote-event-low-context-sell-2330",
        stock_code="2330",
        source_date=execution_date,
        projection_row_sha256=execution_open.projection_row_sha256,
        event_at=observed_at,
    )

    with localcontext(Context(prec=3)):
        result = writer.write_checkpoint(
            strategy_id=binding.strategy_id,
            strategy_version_id=binding.strategy_version_id,
            account_namespace=binding.account_namespace,
            result_id=result_id,
            decision_cutoff=datetime(2026, 8, 4, 8, 30, tzinfo=timezone.utc),
            execution_date=execution_date,
            mark_cutoff=datetime(2026, 8, 5, 7, 0, tzinfo=timezone.utc),
            prior_snapshot_id=prior.snapshot_id,
            snapshot=snapshot,
            fills=(fill,),
            transition=transition,
            mark_prices=(),
            execution_prices=(execution_open, execution_volume),
            quote_event_receipts=(quote,),
        )

    assert result.status == "appended"

    # Later append checkpoints advance the ledger rowset.  Historical exact
    # reads must still verify each operation's own rowset prefix and payload.
    monkeypatch.setattr(
        availability_module,
        "_utc_now",
        lambda: datetime(2026, 8, 7, 8, 25, tzinfo=timezone.utc),
    )
    after_sale = prior_repository.get(result.snapshot_id)
    assert after_sale is not None
    zero_one_id = "result-history-zero-one"
    zero_one = _zero_fill_call(
        _writer(service, paths, zero_one_id, config),
        binding,
        after_sale,
        result_id=zero_one_id,
        execution_date="2026-08-07",
        snapshot_date="2026-08-08",
        decision_cutoff=datetime(2026, 8, 6, 8, 30, tzinfo=timezone.utc),
    )
    zero_one_prior = prior_repository.get(zero_one.snapshot_id)
    assert zero_one_prior is not None
    monkeypatch.setattr(
        availability_module,
        "_utc_now",
        lambda: datetime(2026, 8, 9, 8, 25, tzinfo=timezone.utc),
    )
    zero_two_id = "result-history-zero-two"
    zero_two = _zero_fill_call(
        _writer(service, paths, zero_two_id, config),
        binding,
        zero_one_prior,
        result_id=zero_two_id,
        execution_date="2026-08-09",
        snapshot_date="2026-08-10",
        decision_cutoff=datetime(2026, 8, 8, 8, 30, tzinfo=timezone.utc),
    )
    assert zero_two.status == "appended"

    monkeypatch.setattr(
        availability_module,
        "_utc_now",
        lambda: datetime(2026, 8, 9, 8, 35, tzinfo=timezone.utc),
    )
    for historical in (buy_result, result, zero_one, zero_two):
        value = read_exact_strategy_paper_account_checkpoint(
            service,
            strategy_id=binding.strategy_id,
            strategy_version_id=binding.strategy_version_id,
            account_namespace=binding.account_namespace,
            operation_id=historical.operation_id,
            snapshot_id=historical.snapshot_id,
            decision_cutoff=datetime(2026, 8, 9, 8, 30, tzinfo=timezone.utc),
        )
        assert value.snapshot.snapshot_id == historical.snapshot_id


def _read_availability(
    state_path: Path,
    paths: PersonalDataPaths,
    route: object,
    result: object,
    binding: object,
    *,
    decision_cutoff: datetime | None = None,
) -> object:
    with PersonalStoreCustody(route, paths).read_sqlite(state_path) as connection:  # type: ignore[arg-type]
        row = connection.execute(
            "SELECT receipt_json FROM strategy_paper_account_daily_receipts "
            "WHERE snapshot_id = ?",
            (result.snapshot_id,),
        ).fetchone()
    assert row is not None
    payload = json.loads(str(row[0]))
    return read_exact_strategy_paper_account_availability(
        PersonalStoreCustody(route, paths),  # type: ignore[arg-type]
        state_path,
        operation_id=result.operation_id,
        snapshot_id=result.snapshot_id,
        portfolio_id=binding.portfolio_id,
        account_namespace=binding.account_namespace,
        binding_sha256=binding.binding_sha256,
        snapshot_sha256=payload["snapshot_sha256"],
        base_receipt_sha256=result.receipt_sha256,
        decision_cutoff=decision_cutoff or datetime.now(timezone.utc),
    )


def test_seed_created_after_intent_cutoff_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    prior, store_paths, binding = _seed_account(
        service,
        paths,
        manifest,
        monkeypatch,
        created_at=datetime(2026, 8, 2, 8, 40, tzinfo=timezone.utc),
    )
    config = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}
    writer = _writer(service, paths, "result-late-seed", config)
    before = PaperTradeLedgerRepository(store_paths.cost_ledger_db).rowset_hash()

    with pytest.raises(
        StrategyPaperAccountDailyError,
        match="prior_seed_after_decision_cutoff",
    ):
        _zero_fill_call(writer, binding, prior, result_id="result-late-seed")

    assert PaperTradeLedgerRepository(store_paths.cost_ledger_db).rowset_hash() == before
    if store_paths.state_db.exists():
        connection = sqlite3.connect(store_paths.state_db)
        try:
            assert connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='strategy_paper_account_daily_operations'"
            ).fetchone() is None
        finally:
            connection.close()


def test_quote_event_taipei_date_must_equal_execution_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    prior, store_paths, binding = _seed_account(service, paths, manifest, monkeypatch)
    config = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}
    writer = _writer(service, paths, "result-wrong-event-date", config)
    wrong_date_quote = DailyQuoteEventReceipt.create(
        receipt_id="quote-event-prior-taipei-day",
        stock_code="2330",
        source_date="2026-08-03",
        projection_row_sha256="sha256:" + "3" * 64,
        event_at=datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc),
    )
    before = PaperTradeLedgerRepository(store_paths.cost_ledger_db).rowset_hash()

    with pytest.raises(
        StrategyPaperAccountDailyError,
        match="quote_event_taipei_date_mismatch",
    ):
        _fill_call(
            writer,
            binding,
            prior,
            result_id="result-wrong-event-date",
            quote_receipts=(wrong_date_quote,),
        )

    assert PaperTradeLedgerRepository(store_paths.cost_ledger_db).rowset_hash() == before


def test_daily_prior_without_availability_clock_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    seed, store_paths, binding = _seed_account(service, paths, manifest, monkeypatch)
    config = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}
    writer = _writer(service, paths, "result-prior-clock", config)
    result = _zero_fill_call(writer, binding, seed, result_id="result-prior-clock")
    route = service.select_exact_version(
        strategy_id=binding.strategy_id,
        strategy_version_id=binding.strategy_version_id,
        account_namespace=binding.account_namespace,
    ).route
    assert route is not None
    state = PaperPortfolioSnapshotRepository(
        store_paths.state_db,
        route=route,
        portfolio_id=binding.portfolio_id,
        personal_paths=paths,
    )
    prior = state.get(result.snapshot_id)
    assert prior is not None
    connection = sqlite3.connect(store_paths.state_db)
    try:
        connection.execute(
            "DELETE FROM strategy_paper_account_availability_v1 WHERE snapshot_id = ?",
            (result.snapshot_id,),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        StrategyPaperAccountDailyError,
        match="prior_daily_availability_unknown:availability_clock_unknown",
    ):
        writer._validate_prior_receipt(
            custody=PersonalStoreCustody(route, paths),
            state_path=store_paths.state_db,
            repository=state,
            prior=prior,
            binding=binding,
            decision_cutoff=datetime(2026, 8, 4, 8, 30, tzinfo=timezone.utc),
        )


def test_availability_reader_rejects_future_intent_cutoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    prior, store_paths, binding = _seed_account(service, paths, manifest, monkeypatch)
    config = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}
    writer = _writer(service, paths, "result-future-cutoff", config)
    result = _zero_fill_call(writer, binding, prior, result_id="result-future-cutoff")
    route = service.select_exact_version(
        strategy_id=binding.strategy_id,
        strategy_version_id=binding.strategy_version_id,
        account_namespace=binding.account_namespace,
    ).route
    assert route is not None

    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="decision_cutoff_in_future",
    ):
        _read_availability(
            store_paths.state_db,
            paths,
            route,
            result,
            binding,
            decision_cutoff=datetime.now(timezone.utc) + timedelta(hours=1),
        )


def test_partial_availability_recovers_without_backdating_first_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    prior, store_paths, binding = _seed_account(service, paths, manifest, monkeypatch)
    config = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}
    writer = _writer(service, paths, "result-partial-availability", config)
    result = _zero_fill_call(writer, binding, prior, result_id="result-partial-availability")
    route = service.select_exact_version(
        strategy_id=binding.strategy_id,
        strategy_version_id=binding.strategy_version_id,
        account_namespace=binding.account_namespace,
    ).route
    assert route is not None
    first = _read_availability(store_paths.state_db, paths, route, result, binding)

    identity = availability_module._identity(
        operation_id=result.operation_id,
        snapshot_id=result.snapshot_id,
        portfolio_id=binding.portfolio_id,
        account_namespace=binding.account_namespace,
        binding_sha256=binding.binding_sha256,
        snapshot_sha256=first.snapshot_sha256,
        base_receipt_sha256=result.receipt_sha256,
    )
    partial_payload = availability_module._payload(identity, first.persisted_at, None)
    connection = sqlite3.connect(store_paths.state_db)
    try:
        connection.execute(
            "UPDATE strategy_paper_account_availability_v1 "
            "SET available_at_utc=NULL, receipt_json=?, receipt_sha256=? "
            "WHERE snapshot_id=?",
            (
                availability_module._canonical_json(partial_payload),
                availability_module._sha256(partial_payload),
                result.snapshot_id,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="availability_clock_unknown",
    ):
        _read_availability(store_paths.state_db, paths, route, result, binding)

    recovered = _zero_fill_call(
        writer, binding, prior, result_id="result-partial-availability"
    )
    after = _read_availability(store_paths.state_db, paths, route, recovered, binding)
    assert after.persisted_at == first.persisted_at
    assert after.available_at >= after.persisted_at


def test_availability_reader_rejects_reversed_writer_clocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    prior, store_paths, binding = _seed_account(service, paths, manifest, monkeypatch)
    config = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}
    writer = _writer(service, paths, "result-reversed-clock", config)
    result = _zero_fill_call(writer, binding, prior, result_id="result-reversed-clock")
    route = service.select_exact_version(
        strategy_id=binding.strategy_id,
        strategy_version_id=binding.strategy_version_id,
        account_namespace=binding.account_namespace,
    ).route
    assert route is not None
    first = _read_availability(store_paths.state_db, paths, route, result, binding)
    persisted_at = first.persisted_at - timedelta(seconds=1)
    available_at = persisted_at - timedelta(seconds=1)
    identity = availability_module._identity(
        operation_id=result.operation_id,
        snapshot_id=result.snapshot_id,
        portfolio_id=binding.portfolio_id,
        account_namespace=binding.account_namespace,
        binding_sha256=binding.binding_sha256,
        snapshot_sha256=first.snapshot_sha256,
        base_receipt_sha256=result.receipt_sha256,
    )
    payload = availability_module._payload(identity, persisted_at, available_at)
    connection = sqlite3.connect(store_paths.state_db)
    try:
        connection.execute(
            "UPDATE strategy_paper_account_availability_v1 "
            "SET persisted_at_utc=?, available_at_utc=?, receipt_json=?, receipt_sha256=? "
            "WHERE snapshot_id=?",
            (
                persisted_at.isoformat(),
                available_at.isoformat(),
                availability_module._canonical_json(payload),
                availability_module._sha256(payload),
                result.snapshot_id,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="clock_order_invalid",
    ):
        _read_availability(store_paths.state_db, paths, route, result, binding)


def test_availability_reader_rejects_future_available_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    prior, store_paths, binding = _seed_account(service, paths, manifest, monkeypatch)
    config = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}
    writer = _writer(service, paths, "result-future-availability", config)
    result = _zero_fill_call(writer, binding, prior, result_id="result-future-availability")
    route = service.select_exact_version(
        strategy_id=binding.strategy_id,
        strategy_version_id=binding.strategy_version_id,
        account_namespace=binding.account_namespace,
    ).route
    assert route is not None
    first = _read_availability(store_paths.state_db, paths, route, result, binding)
    available_at = datetime.now(timezone.utc) + timedelta(hours=1)
    identity = availability_module._identity(
        operation_id=result.operation_id,
        snapshot_id=result.snapshot_id,
        portfolio_id=binding.portfolio_id,
        account_namespace=binding.account_namespace,
        binding_sha256=binding.binding_sha256,
        snapshot_sha256=first.snapshot_sha256,
        base_receipt_sha256=result.receipt_sha256,
    )
    payload = availability_module._payload(identity, first.persisted_at, available_at)
    connection = sqlite3.connect(store_paths.state_db)
    try:
        connection.execute(
            "UPDATE strategy_paper_account_availability_v1 SET available_at_utc=?, "
            "receipt_json=?, receipt_sha256=? WHERE snapshot_id=?",
            (
                available_at.isoformat(),
                availability_module._canonical_json(payload),
                availability_module._sha256(payload),
                result.snapshot_id,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="availability_after_decision_cutoff",
    ):
        _read_availability(store_paths.state_db, paths, route, result, binding)


def test_availability_reader_recomputes_full_snapshot_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    prior, store_paths, binding = _seed_account(service, paths, manifest, monkeypatch)
    config = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}
    writer = _writer(service, paths, "result-snapshot-tamper", config)
    result = _zero_fill_call(writer, binding, prior, result_id="result-snapshot-tamper")
    route = service.select_exact_version(
        strategy_id=binding.strategy_id,
        strategy_version_id=binding.strategy_version_id,
        account_namespace=binding.account_namespace,
    ).route
    assert route is not None
    connection = sqlite3.connect(store_paths.state_db)
    try:
        connection.execute(
            "UPDATE paper_portfolio_snapshots SET cash=? WHERE snapshot_id=?",
            ("499999.99", result.snapshot_id),
        )
        connection.execute(
            "UPDATE paper_portfolio_snapshots SET total_value=? WHERE snapshot_id=?",
            ("499999.99", result.snapshot_id),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        StrategyPaperAccountAvailabilityError,
        match="availability_snapshot_hash_mismatch",
    ):
        _read_availability(store_paths.state_db, paths, route, result, binding)


@pytest.mark.parametrize("crash_point", ["ledger", "snapshot"])
def test_exact_operation_recovers_across_each_database_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_point: str,
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    prior, store_paths, binding = _seed_account(service, paths, manifest, monkeypatch)
    config = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}
    writer = _writer(service, paths, f"result-crash-{crash_point}", config)
    original = (
        StrategyPaperAccountDailyWriter._record_ledger_commit
        if crash_point == "ledger"
        else StrategyPaperAccountDailyWriter._finalize_operation
    )
    raised = False

    def crash_once(self: StrategyPaperAccountDailyWriter, **kwargs: object) -> None:
        nonlocal raised
        if not raised:
            raised = True
            raise RuntimeError("isolated crash injection")
        original(self, **kwargs)  # type: ignore[arg-type]

    method_name = "_record_ledger_commit" if crash_point == "ledger" else "_finalize_operation"
    monkeypatch.setattr(StrategyPaperAccountDailyWriter, method_name, crash_once)
    with pytest.raises(RuntimeError, match="isolated crash injection"):
        _zero_fill_call(writer, binding, prior, result_id=f"result-crash-{crash_point}")

    monkeypatch.setattr(StrategyPaperAccountDailyWriter, method_name, original)
    recovered = _zero_fill_call(
        writer, binding, prior, result_id=f"result-crash-{crash_point}"
    )

    assert raised is True
    assert recovered.status == "already_committed"
    assert recovered.performance_eligible is False
    assert PaperTradeLedgerRepository(store_paths.cost_ledger_db).get_daily_operation(
        recovered.operation_id, portfolio_id=binding.portfolio_id
    ) is not None


def test_foreign_ledger_change_after_commit_blocks_exact_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    prior, store_paths, binding = _seed_account(service, paths, manifest, monkeypatch)
    config = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}
    result_id = "result-foreign-recovery"
    writer = _writer(service, paths, result_id, config)
    original = StrategyPaperAccountDailyWriter._record_ledger_commit

    def crash_after_ledger(
        self: StrategyPaperAccountDailyWriter, **kwargs: object
    ) -> None:
        raise RuntimeError("isolated crash after ledger commit")

    monkeypatch.setattr(
        StrategyPaperAccountDailyWriter, "_record_ledger_commit", crash_after_ledger
    )
    with pytest.raises(RuntimeError, match="after ledger commit"):
        _zero_fill_call(writer, binding, prior, result_id=result_id)
    monkeypatch.setattr(StrategyPaperAccountDailyWriter, "_record_ledger_commit", original)

    foreign_fill = PaperTradeFill(
        fill_id="foreign-fill",
        order_id="foreign-order",
        portfolio_id=binding.portfolio_id,
        event_date="2026-08-03",
        stock_code="2330",
        side="buy",
        requested_quantity=1,
        filled_quantity=1,
        reference_price=Decimal("100.00"),
        fill_price=Decimal("100.00"),
        commission=Decimal("0.15"),
        tax=Decimal("0.00"),
        slippage_cost=Decimal("0.00"),
        turnover_bp=2,
        execution_gap_bp=0,
        status="filled",
        source_event_id="foreign-event",
    )
    PaperTradeLedgerRepository(store_paths.cost_ledger_db).append(foreign_fill)

    with pytest.raises(StrategyPaperAccountDailyError, match="rowset changed after commit"):
        _zero_fill_call(writer, binding, prior, result_id=result_id)
    assert PaperPortfolioSnapshotRepository(
        store_paths.state_db,
        portfolio_id=binding.portfolio_id,
        personal_paths=paths,
    ).get(f"{binding.portfolio_id}-20260804") is None


def test_wrong_execution_config_fails_before_companion_or_ledger_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    prior, store_paths, binding = _seed_account(service, paths, manifest, monkeypatch)
    changed_config = {"entry": {"type": "mean_reversion"}, "exit": {"type": "time_stop"}}
    writer = _writer(service, paths, "result-wrong-config", changed_config)
    before = PaperTradeLedgerRepository(store_paths.cost_ledger_db).rowset_hash()

    with pytest.raises(StrategyPaperAccountDailyError, match="config_binding_mismatch"):
        _zero_fill_call(writer, binding, prior, result_id="result-wrong-config")

    assert PaperTradeLedgerRepository(store_paths.cost_ledger_db).rowset_hash() == before
    connection = sqlite3.connect(store_paths.state_db)
    try:
        daily_tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name LIKE 'strategy_paper_account_daily_%'"
        ).fetchall()
    finally:
        connection.close()
    assert daily_tables == []


def test_fill_without_bound_quote_event_receipt_fails_before_ledger_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    prior, store_paths, binding = _seed_account(service, paths, manifest, monkeypatch)
    config = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}
    writer = _writer(service, paths, "result-no-quote", config)
    before = PaperTradeLedgerRepository(store_paths.cost_ledger_db).rowset_hash()

    with pytest.raises(StrategyPaperAccountDailyError, match="quote_receipt_missing"):
        _fill_call(
            writer,
            binding,
            prior,
            result_id="result-no-quote",
            quote_receipts=(),
        )

    assert PaperTradeLedgerRepository(store_paths.cost_ledger_db).rowset_hash() == before


def test_fill_rejects_quote_receipt_for_a_different_source_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    prior, store_paths, binding = _seed_account(service, paths, manifest, monkeypatch)
    config = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}
    writer = _writer(service, paths, "result-wrong-quote-row", config)
    before = PaperTradeLedgerRepository(store_paths.cost_ledger_db).rowset_hash()
    wrong_quote = DailyQuoteEventReceipt.create(
        receipt_id="quote-event-wrong-row",
        stock_code="2330",
        source_date="2026-08-03",
        projection_row_sha256="sha256:" + "9" * 64,
        event_at=datetime(2026, 8, 3, 1, 30, tzinfo=timezone.utc),
    )

    with pytest.raises(StrategyPaperAccountDailyError, match="quote_receipt_row_mismatch"):
        _fill_call(
            writer,
            binding,
            prior,
            result_id="result-wrong-quote-row",
            quote_receipts=(wrong_quote,),
        )

    assert PaperTradeLedgerRepository(store_paths.cost_ledger_db).rowset_hash() == before


def test_state_schema_drift_blocks_without_adding_daily_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    prior, store_paths, binding = _seed_account(service, paths, manifest, monkeypatch)
    connection = sqlite3.connect(store_paths.state_db)
    try:
        connection.execute(
            "ALTER TABLE paper_portfolio_snapshots ADD COLUMN foreign_note TEXT"
        )
        connection.commit()
    finally:
        connection.close()
    config = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}
    writer = _writer(service, paths, "result-schema-drift", config)
    before = PaperTradeLedgerRepository(store_paths.cost_ledger_db).rowset_hash()

    with pytest.raises(StrategyPaperAccountDailyError, match="state_columns_mismatch"):
        _zero_fill_call(writer, binding, prior, result_id="result-schema-drift")

    assert PaperTradeLedgerRepository(store_paths.cost_ledger_db).rowset_hash() == before
    connection = sqlite3.connect(store_paths.state_db)
    try:
        daily_tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name LIKE 'strategy_paper_account_daily_%'"
        ).fetchall()
    finally:
        connection.close()
    assert daily_tables == []
