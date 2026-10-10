"""可移植的策略帳戶 cash-only seed 契約測試。"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
from threading import Barrier

import pytest

import app_module.strategy_paper_account_cash_seed_writer as seed_writer_module
from app_module.paper_portfolio_policy import PaperPortfolioPolicyConfig
from app_module.paper_portfolio_snapshot_repository import (
    PaperPortfolioPositionSnapshot,
    PaperPortfolioSnapshot,
    PaperPortfolioSnapshotReceipt,
    PaperPortfolioSnapshotRepository,
)
from app_module.personal_data_paths import PersonalDataPaths
from app_module.personal_paper_store_paths import PersonalPaperStorePaths
from app_module.strategy_paper_account_cash_seed_writer import (
    StrategyPaperAccountCashSeedWriter,
    StrategyPaperAccountSeedError,
)
from app_module.strategy_paper_account_service import (
    StrategyPaperAccountBinding,
    StrategyPaperAccountService,
    canonical_sha256,
    file_sha256,
)
from app_module.strategy_version_service import StrategyVersion


def _write_json(path: Path, payload: object) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    path.write_bytes(raw)
    return raw


def _fixture_roots(tmp_path: Path) -> tuple[PersonalDataPaths, Path, Path]:
    market_root = tmp_path / "market"
    personal_paths = PersonalDataPaths(
        market_root=market_root,
        legacy_output_root=tmp_path / "legacy-output",
        personal_root=market_root / "personal",
    )
    return personal_paths, tmp_path / "strategy-versions", tmp_path / "account-contracts"


def _write_contract_artifacts(contract_root: Path) -> dict[str, str]:
    config = PaperPortfolioPolicyConfig()
    policy_snapshot = asdict(config)
    policy_snapshot["initial_capital"] = str(config.initial_capital)
    artifacts = {
        "policy_sha256": (
            "paper_policies",
            "paper_policy_default",
            "v1",
            {
                "artifact_type": "paper_policies",
                "artifact_id": "paper_policy_default",
                "version": "v1",
                "policy": policy_snapshot,
            },
        ),
        "cost_model_sha256": (
            "cost_models",
            "taiwan_paper_cost",
            "v1",
            {
                "artifact_type": "cost_models",
                "artifact_id": "taiwan_paper_cost",
                "version": "v1",
                "cost_model": {
                    "commission_bp_per_side": config.commission_bp_per_side,
                    "slippage_bp_per_side": config.slippage_bp_per_side,
                    "sell_tax_bp": config.sell_tax_bp,
                },
            },
        ),
        "benchmark_sha256": (
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
    }
    result: dict[str, str] = {}
    for field_name, (directory, artifact_id, version, payload) in artifacts.items():
        path = contract_root / directory / f"{artifact_id}__{version}.json"
        result[field_name] = file_sha256(_write_json(path, payload))
    return result


def _create_account(
    tmp_path: Path,
    *,
    strategy_id: str = "strategy-a",
    strategy_version_id: str = "version-a",
    start_date: str = "2026-10-01",
    roots: tuple[PersonalDataPaths, Path, Path] | None = None,
) -> tuple[StrategyPaperAccountService, PersonalDataPaths, dict[str, object]]:
    personal_paths, strategy_root, contract_root = roots or _fixture_roots(tmp_path)
    contract_hashes = _write_contract_artifacts(contract_root)
    params = {"entry_threshold": 0.75, "confirm_days": 3}
    config = {"entry": {"type": "breakout"}, "exit": {"type": "time_stop"}}
    source_run_id = f"run-{strategy_version_id}"
    strategy_payload = StrategyVersion(
        version_id=strategy_version_id,
        strategy_id=strategy_id,
        strategy_version="1.0.0",
        source_run_id=source_run_id,
        promoted_at="2026-10-01T00:00:00+00:00",
        params=params,
        config=config,
        backtest_summary={},
        regime=["Trend"],
        profile_id=None,
        profile_version=None,
        validation_status="validated",
        validation_metrics={},
        notes=None,
    ).to_dict()
    strategy_raw = _write_json(strategy_root / f"{strategy_version_id}.json", strategy_payload)
    fields = {
        "strategy_version_id": strategy_version_id,
        "strategy_id": strategy_id,
        "strategy_version": "1.0.0",
        "strategy_artifact_sha256": file_sha256(strategy_raw),
        "params_sha256": canonical_sha256(params),
        "config_sha256": canonical_sha256(config),
        "source_run_id": source_run_id,
        "policy_id": "paper_policy_default",
        "policy_version": "v1",
        "policy_sha256": contract_hashes["policy_sha256"],
        "cost_model_id": "taiwan_paper_cost",
        "cost_model_version": "v1",
        "cost_model_sha256": contract_hashes["cost_model_sha256"],
        "benchmark_id": "equal_weight_frozen",
        "benchmark_version": "v1",
        "benchmark_sha256": contract_hashes["benchmark_sha256"],
        "start_date": start_date,
        "initial_capital": "500000",
        "max_positions": 8,
    }
    manifest = StrategyPaperAccountBinding.create_manifest_payload(**fields)
    account_root = (
        personal_paths.personal_root
        / "paper_portfolio"
        / "accounts"
        / str(manifest["account_namespace"])
    )
    _write_json(account_root / "account_binding.json", manifest)
    service = StrategyPaperAccountService(
        personal_paths=personal_paths,
        strategy_versions_root=strategy_root,
        contract_artifacts_root=contract_root,
    )
    return service, personal_paths, manifest


def _writer(
    service: StrategyPaperAccountService, paths: PersonalDataPaths
) -> StrategyPaperAccountCashSeedWriter:
    return StrategyPaperAccountCashSeedWriter(
        account_service=service,
        personal_paths=paths,
    )


def _create_seed(
    service: StrategyPaperAccountService,
    paths: PersonalDataPaths,
    manifest: dict[str, object],
) -> object:
    return _writer(service, paths).create_cash_seed(
        strategy_id=str(manifest["strategy_id"]),
        strategy_version_id=str(manifest["strategy_version_id"]),
        account_namespace=str(manifest["account_namespace"]),
    )


def test_real_cash_seed_is_forward_empty_and_bound_to_exact_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    monkeypatch.setattr(
        seed_writer_module,
        "_utc_now",
        lambda: datetime(2026, 10, 10, 8, 10, tzinfo=timezone.utc),
    )

    result = _create_seed(service, paths, manifest)

    assert result.snapshot.portfolio_id == manifest["portfolio_id"]
    assert result.snapshot.decision_date == "2026-10-10"
    assert result.snapshot.source_result_id == (
        "strategy-account-cash-seed:" + str(manifest["binding_sha256"]).removeprefix("sha256:")
    )
    assert result.snapshot.cash == Decimal("500000")
    assert result.snapshot.total_value == Decimal("500000")
    assert result.snapshot.positions == ()
    assert result.receipt.receipt_kind == "account_cash_seed"
    assert result.receipt.schema_version == "paper-portfolio-snapshot-receipt.v2"
    assert result.receipt.seed_source_id == "strategy_paper_account_binding.v1"
    assert result.receipt.seed_source_sha256 == manifest["binding_sha256"]
    assert result.receipt.seed_created_at == "2026-10-10T08:10:00+00:00"
    assert not result.receipt.seed_source_id.startswith("synthetic:")

    selected = service.select_account(str(manifest["account_namespace"]))
    assert selected.binding is not None
    assert selected.binding.binding_sha256 == manifest["binding_sha256"]
    assert selected.performance_eligible is False
    store_paths = PersonalPaperStorePaths.from_route(
        selected.route, portfolio_id=selected.binding.portfolio_id
    )
    reader = PaperPortfolioSnapshotRepository(
        store_paths.state_db,
        route=selected.route,
        portfolio_id=selected.binding.portfolio_id,
        personal_paths=paths,
    )
    assert reader.get(result.snapshot.snapshot_id) == result.snapshot
    assert reader.get_receipt(result.snapshot.snapshot_id) == result.receipt


def test_seed_date_uses_saved_clock_in_taiwan_timezone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, paths, manifest = _create_account(tmp_path, start_date="2026-10-11")
    monkeypatch.setattr(
        seed_writer_module,
        "_utc_now",
        lambda: datetime(2026, 10, 10, 16, 10, tzinfo=timezone.utc),
    )

    result = _create_seed(service, paths, manifest)

    assert result.snapshot.decision_date == "2026-10-11"
    assert result.receipt.seed_created_at == "2026-10-10T16:10:00+00:00"


def test_two_strategy_cash_seeds_on_same_date_use_distinct_state_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roots = _fixture_roots(tmp_path)
    service_a, paths, manifest_a = _create_account(
        tmp_path, strategy_id="strategy-a", strategy_version_id="version-a", roots=roots
    )
    service_b, _, manifest_b = _create_account(
        tmp_path, strategy_id="strategy-b", strategy_version_id="version-b", roots=roots
    )
    monkeypatch.setattr(
        seed_writer_module,
        "_utc_now",
        lambda: datetime(2026, 10, 10, 8, 10, tzinfo=timezone.utc),
    )

    seed_a = _create_seed(service_a, paths, manifest_a)
    seed_b = _create_seed(service_b, paths, manifest_b)

    selected_a = service_a.select_account(str(manifest_a["account_namespace"]))
    selected_b = service_b.select_account(str(manifest_b["account_namespace"]))
    assert selected_a.binding is not None and selected_b.binding is not None
    state_a = PersonalPaperStorePaths.from_route(
        selected_a.route, portfolio_id=selected_a.binding.portfolio_id
    ).state_db
    state_b = PersonalPaperStorePaths.from_route(
        selected_b.route, portfolio_id=selected_b.binding.portfolio_id
    ).state_db
    assert seed_a.snapshot.decision_date == seed_b.snapshot.decision_date == "2026-10-10"
    assert seed_a.snapshot.snapshot_id != seed_b.snapshot.snapshot_id
    assert state_a != state_b
    assert state_a.is_file() and state_b.is_file()
    assert selected_a.binding.account_namespace != selected_b.binding.account_namespace


def test_wrong_exact_version_fails_before_creating_account_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    monkeypatch.setattr(
        seed_writer_module,
        "_utc_now",
        lambda: datetime(2026, 10, 10, 8, 10, tzinfo=timezone.utc),
    )
    writer = _writer(service, paths)

    with pytest.raises(StrategyPaperAccountSeedError, match="exact_version_mismatch"):
        writer.create_cash_seed(
            strategy_id=str(manifest["strategy_id"]),
            strategy_version_id="version-other",
            account_namespace=str(manifest["account_namespace"]),
        )

    state_path = (
        paths.personal_root
        / "paper_portfolio"
        / "accounts"
        / str(manifest["account_namespace"])
        / "paper_portfolio.sqlite"
    )
    assert not state_path.exists()


def test_missing_or_tampered_pinned_policy_does_not_create_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    policy_path = service.contract_artifacts_root / "paper_policies" / "paper_policy_default__v1.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["policy"]["max_positions"] = 7
    _write_json(policy_path, policy)
    monkeypatch.setattr(
        seed_writer_module,
        "_utc_now",
        lambda: datetime(2026, 10, 10, 8, 10, tzinfo=timezone.utc),
    )

    with pytest.raises(StrategyPaperAccountSeedError):
        _create_seed(service, paths, manifest)

    state_path = (
        paths.personal_root
        / "paper_portfolio"
        / "accounts"
        / str(manifest["account_namespace"])
        / "paper_portfolio.sqlite"
    )
    assert not state_path.exists()


@pytest.mark.parametrize(
    "clock, expected_reason",
    (
        (datetime(2026, 10, 10, 8, 10), "clock_unknown"),
        (datetime(2026, 10, 9, 8, 10, tzinfo=timezone.utc), "start_date_in_future"),
    ),
)
def test_naive_or_pre_start_clock_cannot_backdate_seed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    clock: datetime,
    expected_reason: str,
) -> None:
    service, paths, manifest = _create_account(
        tmp_path,
        start_date="2026-10-10" if expected_reason == "start_date_in_future" else "2026-10-01",
    )
    monkeypatch.setattr(seed_writer_module, "_utc_now", lambda: clock)

    with pytest.raises(StrategyPaperAccountSeedError, match=expected_reason):
        _create_seed(service, paths, manifest)

    state_path = (
        paths.personal_root
        / "paper_portfolio"
        / "accounts"
        / str(manifest["account_namespace"])
        / "paper_portfolio.sqlite"
    )
    assert not state_path.exists()


def test_cash_seed_receipt_rejects_nonempty_position_claim() -> None:
    namespace = "acct-" + "1" * 64
    binding_hash = "sha256:" + "1" * 64
    snapshot = PaperPortfolioSnapshot(
        snapshot_id=f"{namespace}-cash-seed-20261010",
        portfolio_id=namespace,
        decision_date="2026-10-10",
        source_result_id="strategy-account-cash-seed:" + "1" * 64,
        cash=Decimal("499000"),
        total_value=Decimal("500000"),
        positions=(
            PaperPortfolioPositionSnapshot(
                stock_code="2330",
                quantity=100,
                mark_price=Decimal("10"),
                market_value=Decimal("1000"),
                weight_bp=20,
            ),
        ),
    )

    with pytest.raises(ValueError, match="500000 cash NAV|empty positions"):
        PaperPortfolioSnapshotReceipt.account_cash_seed_for(
            snapshot,
            account_namespace=namespace,
            binding_sha256=binding_hash,
            seed_created_at="2026-10-10T08:10:00+00:00",
        )


@pytest.mark.parametrize("schema_version", ([], {}, None, 1))
def test_receipt_schema_version_non_string_is_rejected_as_value_error(
    schema_version: object,
) -> None:
    snapshot = PaperPortfolioSnapshot(
        snapshot_id="paper-main-unknown-20261010",
        portfolio_id="paper-main",
        decision_date="2026-10-10",
        source_result_id="existing-research-run",
        cash=Decimal("500000"),
        total_value=Decimal("500000"),
        positions=(),
    )
    receipt = PaperPortfolioSnapshotReceipt.unknown_for(
        snapshot, reason="legacy provenance is unknown"
    )
    payload = json.loads(receipt.to_json())
    payload["schema_version"] = schema_version
    raw = json.dumps(payload)

    with pytest.raises(ValueError, match="schema version"):
        PaperPortfolioSnapshotReceipt.from_json(raw)
    with pytest.raises(ValueError, match="schema version"):
        PaperPortfolioSnapshotReceipt(**payload)  # type: ignore[arg-type]


def test_cash_seed_duplicate_does_not_overwrite_original_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    clock = datetime(2026, 10, 10, 8, 10, tzinfo=timezone.utc)
    monkeypatch.setattr(seed_writer_module, "_utc_now", lambda: clock)
    first = _create_seed(service, paths, manifest)
    monkeypatch.setattr(
        seed_writer_module,
        "_utc_now",
        lambda: datetime(2026, 10, 10, 9, 10, tzinfo=timezone.utc),
    )

    with pytest.raises(StrategyPaperAccountSeedError, match="seed_already_exists"):
        _create_seed(service, paths, manifest)

    selected = service.select_account(str(manifest["account_namespace"]))
    assert selected.binding is not None
    store_paths = PersonalPaperStorePaths.from_route(
        selected.route, portfolio_id=selected.binding.portfolio_id
    )
    reader = PaperPortfolioSnapshotRepository(
        store_paths.state_db,
        route=selected.route,
        portfolio_id=selected.binding.portfolio_id,
        personal_paths=paths,
    )
    assert reader.get_receipt(first.snapshot.snapshot_id) == first.receipt


def test_cash_seed_rejects_any_prior_snapshot_from_another_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    selected = service.select_account(str(manifest["account_namespace"]))
    assert selected.binding is not None and selected.route is not None
    store_paths = PersonalPaperStorePaths.from_route(
        selected.route, portfolio_id=selected.binding.portfolio_id
    )
    repository = PaperPortfolioSnapshotRepository(
        store_paths.state_db,
        route=selected.route,
        portfolio_id=selected.binding.portfolio_id,
        personal_paths=paths,
    )
    prior = PaperPortfolioSnapshot(
        snapshot_id=f"{selected.binding.portfolio_id}-prior-20261009",
        portfolio_id=selected.binding.portfolio_id,
        decision_date="2026-10-09",
        source_result_id="prior-unknown-result",
        cash=Decimal("500000"),
        total_value=Decimal("500000"),
        positions=(),
    )
    repository.append(prior)
    monkeypatch.setattr(
        seed_writer_module,
        "_utc_now",
        lambda: datetime(2026, 10, 10, 8, 10, tzinfo=timezone.utc),
    )

    with pytest.raises(StrategyPaperAccountSeedError, match="seed_already_exists"):
        _create_seed(service, paths, manifest)

    assert tuple(row.snapshot_id for row in repository.list_for_portfolio(prior.portfolio_id)) == (
        prior.snapshot_id,
    )
    assert repository.get_receipt(prior.snapshot_id) is None


def test_cash_seed_cannot_be_appended_to_unrouted_flat_store(tmp_path: Path) -> None:
    service, _paths, manifest = _create_account(tmp_path)
    selected = service.select_account(str(manifest["account_namespace"]))
    assert selected.binding is not None
    decision_date = "2026-10-10"
    snapshot = PaperPortfolioSnapshot(
        snapshot_id=f"{selected.binding.portfolio_id}-cash-seed-20261010",
        portfolio_id=selected.binding.portfolio_id,
        decision_date=decision_date,
        source_result_id=(
            "strategy-account-cash-seed:"
            + selected.binding.binding_sha256.removeprefix("sha256:")
        ),
        cash=Decimal("500000"),
        total_value=Decimal("500000"),
        positions=(),
    )
    receipt = PaperPortfolioSnapshotReceipt.account_cash_seed_for(
        snapshot,
        account_namespace=selected.binding.account_namespace,
        binding_sha256=selected.binding.binding_sha256,
        seed_created_at="2026-10-10T08:10:00+00:00",
    )
    flat_repository = PaperPortfolioSnapshotRepository(
        tmp_path / "unrouted-paper.sqlite",
        portfolio_id=selected.binding.portfolio_id,
    )

    with pytest.raises(ValueError, match="requires_namespaced_route"):
        flat_repository.append(snapshot, receipt)

    assert flat_repository.list_for_portfolio(snapshot.portfolio_id) == ()


def test_concurrent_different_date_cash_seeds_allow_only_one_append(
    tmp_path: Path,
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    selected = service.select_account(str(manifest["account_namespace"]))
    assert selected.binding is not None and selected.route is not None
    store_paths = PersonalPaperStorePaths.from_route(
        selected.route, portfolio_id=selected.binding.portfolio_id
    )
    repository = PaperPortfolioSnapshotRepository(
        store_paths.state_db,
        route=selected.route,
        portfolio_id=selected.binding.portfolio_id,
        personal_paths=paths,
    )
    source_result_id = (
        "strategy-account-cash-seed:"
        + selected.binding.binding_sha256.removeprefix("sha256:")
    )
    candidates = (
        (
            "2026-10-10",
            "2026-10-10T08:10:00+00:00",
        ),
        (
            "2026-10-11",
            "2026-10-10T16:10:00+00:00",
        ),
    )
    snapshot_receipt_pairs = []
    for decision_date, seed_created_at in candidates:
        snapshot = PaperPortfolioSnapshot(
            snapshot_id=(
                f"{selected.binding.portfolio_id}-cash-seed-"
                f"{decision_date.replace('-', '')}"
            ),
            portfolio_id=selected.binding.portfolio_id,
            decision_date=decision_date,
            source_result_id=source_result_id,
            cash=Decimal("500000"),
            total_value=Decimal("500000"),
            positions=(),
        )
        receipt = PaperPortfolioSnapshotReceipt.account_cash_seed_for(
            snapshot,
            account_namespace=selected.binding.account_namespace,
            binding_sha256=selected.binding.binding_sha256,
            seed_created_at=seed_created_at,
        )
        snapshot_receipt_pairs.append((snapshot, receipt))

    barrier = Barrier(2)

    def append_after_barrier(
        snapshot: PaperPortfolioSnapshot, receipt: PaperPortfolioSnapshotReceipt
    ) -> str:
        barrier.wait()
        try:
            repository.append(snapshot, receipt)
        except ValueError as exc:
            if str(exc) == "strategy_account_seed_already_exists":
                return "rejected_existing_account_state"
            raise
        return "saved"

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = tuple(
            executor.submit(append_after_barrier, snapshot, receipt)
            for snapshot, receipt in snapshot_receipt_pairs
        )
        outcomes = tuple(future.result() for future in futures)

    assert sorted(outcomes) == ["rejected_existing_account_state", "saved"]
    saved = repository.list_for_portfolio(selected.binding.portfolio_id)
    assert len(saved) == 1
    assert repository.get_receipt(saved[0].snapshot_id) is not None


def test_seed_snapshot_and_receipt_are_atomic_on_receipt_insert_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, paths, manifest = _create_account(tmp_path)
    selected = service.select_account(str(manifest["account_namespace"]))
    assert selected.binding is not None and selected.route is not None
    store_paths = PersonalPaperStorePaths.from_route(
        selected.route, portfolio_id=selected.binding.portfolio_id
    )
    PaperPortfolioSnapshotRepository(
        store_paths.state_db,
        route=selected.route,
        portfolio_id=selected.binding.portfolio_id,
        personal_paths=paths,
    )
    with sqlite3.connect(store_paths.state_db) as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_account_cash_seed_receipt
            BEFORE INSERT ON paper_portfolio_snapshot_receipts
            BEGIN SELECT RAISE(ABORT, 'test receipt insert failure'); END
            """
        )
    monkeypatch.setattr(
        seed_writer_module,
        "_utc_now",
        lambda: datetime(2026, 10, 10, 8, 10, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="snapshot append failed"):
        _create_seed(service, paths, manifest)

    uri = store_paths.state_db.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM paper_portfolio_snapshots").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM paper_portfolio_positions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM paper_portfolio_snapshot_receipts").fetchone()[0] == 0
