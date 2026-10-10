"""隔離 P08 候選測試；只建立 pytest 暫存 JSON，不建立或開啟 SQLite。"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import pytest

import app_module.strategy_paper_account_service as account_module
from app_module.paper_portfolio_policy import PaperPortfolioPolicyConfig
from app_module.paper_portfolio_weekly_evidence_service import (
    PaperPortfolioWeeklyEvidenceService,
)
from app_module.personal_data_paths import PersonalDataPaths
from app_module.personal_paper_store_paths import PersonalPaperStorePaths
from app_module.personal_store_routes import (
    PersonalStoreDomain,
    PersonalStoreMode,
    PersonalStoreRouteError,
    StoreIdentity,
    select_personal_store_route,
)
from app_module.strategy_version_service import StrategyVersion
from app_module.strategy_paper_account_service import (
    AccountBindingStatus,
    StrategyPaperAccountBinding,
    StrategyPaperAccountService,
    canonical_sha256,
    file_sha256,
)


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
    strategy_root = tmp_path / "strategy-versions"
    contract_root = tmp_path / "account-contracts"
    return personal_paths, strategy_root, contract_root


def _write_contract_artifacts(contract_root: Path) -> dict[str, str]:
    config = PaperPortfolioPolicyConfig()
    policy_snapshot = asdict(config)
    policy_snapshot["initial_capital"] = str(config.initial_capital)
    cost_snapshot = {
        "commission_bp_per_side": config.commission_bp_per_side,
        "slippage_bp_per_side": config.slippage_bp_per_side,
        "sell_tax_bp": config.sell_tax_bp,
    }
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
                "cost_model": cost_snapshot,
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
    strategy_id: str,
    strategy_version_id: str,
    roots: tuple[PersonalDataPaths, Path, Path] | None = None,
) -> tuple[StrategyPaperAccountService, object]:
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
        "start_date": "2026-10-01",
        "initial_capital": "500000",
        "max_positions": 8,
    }
    manifest = StrategyPaperAccountBinding.create_manifest_payload(**fields)
    account_root = (
        personal_paths.personal_root
        / "paper_portfolio"
        / "accounts"
        / manifest["account_namespace"]
    )
    _write_json(account_root / "account_binding.json", manifest)
    service = StrategyPaperAccountService(
        personal_paths=personal_paths,
        strategy_versions_root=strategy_root,
        contract_artifacts_root=contract_root,
    )
    return service, manifest


def _manifest_fields(manifest: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in manifest.items()
        if key
        not in {
            "schema_version",
            "account_namespace",
            "portfolio_id",
            "binding_sha256",
        }
    }


def _write_rebound_manifest(
    service: StrategyPaperAccountService,
    fields: dict[str, object],
) -> dict[str, object]:
    manifest = StrategyPaperAccountBinding.create_manifest_payload(**fields)
    _write_json(
        service.accounts_root / manifest["account_namespace"] / "account_binding.json",
        manifest,
    )
    return manifest


def test_two_strategy_bindings_route_same_stock_date_to_distinct_full_roots(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    tmp_path = tmp_path_factory.mktemp("p08")
    roots = _fixture_roots(tmp_path)
    service_a, manifest_a = _create_account(
        tmp_path,
        strategy_id="strategy-a",
        strategy_version_id="version-a",
        roots=roots,
    )
    service_b, manifest_b = _create_account(
        tmp_path,
        strategy_id="strategy-b",
        strategy_version_id="version-b",
        roots=roots,
    )
    selected_a = service_a.select_account(manifest_a["account_namespace"])
    selected_b = service_b.select_account(manifest_b["account_namespace"])

    assert selected_a.status is AccountBindingStatus.READY
    assert selected_b.status is AccountBindingStatus.READY
    assert selected_a.performance_eligible is False
    assert selected_b.performance_eligible is False
    assert selected_a.route is not None and selected_b.route is not None

    observation_a = {"stock_code": "2330", "decision_date": "2026-10-02"}
    observation_b = {"stock_code": "2330", "decision_date": "2026-10-02"}
    assert observation_a == observation_b
    paths_a = PersonalPaperStorePaths.from_route(
        selected_a.route, portfolio_id=selected_a.binding.portfolio_id
    )
    paths_b = PersonalPaperStorePaths.from_route(
        selected_b.route, portfolio_id=selected_b.binding.portfolio_id
    )
    for field_name in (
        "state_db",
        "benchmark_db",
        "cost_ledger_db",
        "baseline",
        "status",
        "binding_manifest",
    ):
        assert getattr(paths_a, field_name) != getattr(paths_b, field_name)
    assert paths_a.status.is_relative_to(paths_a.cost_ledger_db.parent)
    assert paths_b.status.is_relative_to(paths_b.cost_ledger_db.parent)
    assert paths_a.cost_ledger_db.parent.parent == paths_b.cost_ledger_db.parent.parent


def test_legacy_paper_main_flat_layout_is_unchanged(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    tmp_path = tmp_path_factory.mktemp("p08")
    personal_paths, _, _ = _fixture_roots(tmp_path)
    route = select_personal_store_route(
        domain=PersonalStoreDomain.PAPER,
        mode=PersonalStoreMode.PERSONAL,
        identity=StoreIdentity("paper-main"),
        personal_paths=personal_paths,
    )
    paths = PersonalPaperStorePaths.from_route(route, portfolio_id="paper-main")

    assert route.paper_account_namespace is None
    assert route.read_source == (
        personal_paths.personal_root / "paper_portfolio" / "paper_trade_ledger.sqlite"
    )
    assert paths.state_db == personal_paths.personal_root / "paper_portfolio" / "paper_portfolio.sqlite"
    assert paths.benchmark_db == personal_paths.personal_root / "paper_portfolio" / "paper_equal_weight_benchmark.sqlite"
    assert paths.baseline.name == "baseline_20260712.json"
    assert paths.status == personal_paths.personal_root / "scheduled" / "paper_portfolio_daily" / "latest_status.json"
    assert paths.binding_manifest is None


def test_account_route_rejects_namespace_escape_and_wrong_identity(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    tmp_path = tmp_path_factory.mktemp("p08")
    personal_paths, _, _ = _fixture_roots(tmp_path)
    with pytest.raises(PersonalStoreRouteError, match="paper_account_namespace_invalid"):
        select_personal_store_route(
            domain=PersonalStoreDomain.PAPER,
            mode=PersonalStoreMode.PERSONAL,
            identity=StoreIdentity("acct-../escape"),
            personal_paths=personal_paths,
            paper_account_namespace="acct-../escape",
        )

    namespace = "acct-" + "1" * 64
    with pytest.raises(PersonalStoreRouteError, match="paper_account_namespace_identity_mismatch"):
        select_personal_store_route(
            domain=PersonalStoreDomain.PAPER,
            mode=PersonalStoreMode.PERSONAL,
            identity=StoreIdentity("acct-" + "2" * 64),
            personal_paths=personal_paths,
            paper_account_namespace=namespace,
        )


def test_binding_and_exact_strategy_artifact_mismatches_are_rejected(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    tmp_path = tmp_path_factory.mktemp("p08")
    service, manifest = _create_account(
        tmp_path, strategy_id="strategy-a", strategy_version_id="version-a"
    )
    account_manifest_path = (
        service.accounts_root / manifest["account_namespace"] / "account_binding.json"
    )
    tampered = dict(manifest)
    tampered["policy_version"] = "v2"
    _write_json(account_manifest_path, tampered)
    selected = service.select_account(manifest["account_namespace"])
    assert selected.status is AccountBindingStatus.REJECTED
    assert "binding_sha256_mismatch" in selected.blockers[0]

    _write_json(account_manifest_path, manifest)
    artifact_path = service.strategy_versions_root / "version-a.json"
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    payload["params"]["entry_threshold"] = "0.80"
    _write_json(artifact_path, payload)
    selected = service.select_account(manifest["account_namespace"])
    assert selected.status is AccountBindingStatus.REJECTED
    assert "bound_artifact_sha256_mismatch" in selected.blockers[0]


def test_exact_version_requires_explicit_account_when_bindings_are_ambiguous(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    tmp_path = tmp_path_factory.mktemp("p08")
    service, first = _create_account(
        tmp_path, strategy_id="strategy-a", strategy_version_id="version-a"
    )
    second_fields = _manifest_fields(first)
    second_fields["start_date"] = "2026-10-02"
    second = _write_rebound_manifest(service, second_fields)

    ambiguous = service.select_exact_version(
        strategy_id="strategy-a", strategy_version_id="version-a"
    )
    assert ambiguous.status is AccountBindingStatus.UNKNOWN
    assert ambiguous.blockers == ("strategy_account_binding_ambiguous",)
    wrong_version = service.select_exact_version(
        strategy_id="strategy-b",
        strategy_version_id="version-a",
        account_namespace=first["account_namespace"],
    )
    assert wrong_version.status is AccountBindingStatus.REJECTED
    assert wrong_version.blockers == ("strategy_account_exact_version_mismatch",)
    exact = service.select_exact_version(
        strategy_id="strategy-a",
        strategy_version_id="version-a",
        account_namespace=second["account_namespace"],
    )
    assert exact.status is AccountBindingStatus.READY
    assert exact.binding is not None and exact.binding.start_date == "2026-10-02"


@pytest.mark.parametrize("missing_field", ["params", "config"])
def test_missing_strategy_params_or_config_remains_unknown(
    tmp_path_factory: pytest.TempPathFactory,
    missing_field: str,
) -> None:
    tmp_path = tmp_path_factory.mktemp("p08")
    service, manifest = _create_account(
        tmp_path, strategy_id="strategy-a", strategy_version_id="version-a"
    )
    strategy_path = service.strategy_versions_root / "version-a.json"
    payload = json.loads(strategy_path.read_text(encoding="utf-8"))
    del payload[missing_field]
    raw = _write_json(strategy_path, payload)
    fields = _manifest_fields(manifest)
    fields["strategy_artifact_sha256"] = file_sha256(raw)
    rebound = _write_rebound_manifest(service, fields)

    selected = service.select_account(rebound["account_namespace"])
    assert selected.status is AccountBindingStatus.UNKNOWN
    assert selected.blockers == (f"strategy_{missing_field}_missing",)


@pytest.mark.parametrize("invalid_field", ["params", "config"])
def test_non_object_strategy_params_or_config_are_rejected(
    tmp_path_factory: pytest.TempPathFactory,
    invalid_field: str,
) -> None:
    tmp_path = tmp_path_factory.mktemp("p08")
    service, manifest = _create_account(
        tmp_path, strategy_id="strategy-a", strategy_version_id="version-a"
    )
    strategy_path = service.strategy_versions_root / "version-a.json"
    payload = json.loads(strategy_path.read_text(encoding="utf-8"))
    payload[invalid_field] = ["unexpected", "array"]
    raw = _write_json(strategy_path, payload)
    fields = _manifest_fields(manifest)
    fields["strategy_artifact_sha256"] = file_sha256(raw)
    rebound = _write_rebound_manifest(service, fields)

    selected = service.select_account(rebound["account_namespace"])
    assert selected.status is AccountBindingStatus.REJECTED
    assert selected.blockers == (f"strategy_{invalid_field}_must_be_object",)


def test_policy_cost_and_benchmark_artifact_identity_content_are_pinned(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    artifact_cases = (
        (
            "paper_policies",
            "paper_policy_default__v1.json",
            "policy",
            lambda value: value.update(max_positions=7),
            "paper_policy_snapshot_mismatch",
            "policy_sha256",
        ),
        (
            "cost_models",
            "taiwan_paper_cost__v1.json",
            "cost_model",
            lambda value: value.update(commission_bp_per_side=16),
            "paper_cost_model_snapshot_mismatch",
            "cost_model_sha256",
        ),
        (
            "benchmarks",
            "equal_weight_frozen__v1.json",
            None,
            lambda value: value.update(artifact_id="other_benchmark"),
            "benchmarks_artifact_identity_mismatch",
            "benchmark_sha256",
        ),
    )
    for index, (
        directory,
        filename,
        snapshot_key,
        mutate,
        expected_blocker,
        hash_field,
    ) in enumerate(artifact_cases):
        tmp_path = tmp_path_factory.mktemp(f"p08-{index}")
        service, original = _create_account(
            tmp_path, strategy_id="strategy-a", strategy_version_id="version-a"
        )
        artifact_path = service.contract_artifacts_root / directory / filename
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        if snapshot_key is None:
            mutate(artifact)
        else:
            mutate(artifact[snapshot_key])
        raw = _write_json(artifact_path, artifact)
        fields = _manifest_fields(original)
        fields[hash_field] = file_sha256(raw)
        rebound = _write_rebound_manifest(service, fields)

        selected = service.select_account(rebound["account_namespace"])
        assert selected.status is AccountBindingStatus.REJECTED
        assert selected.blockers == (expected_blocker,)


def test_verified_artifact_hash_and_json_parse_use_one_stable_byte_snapshot(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_path = tmp_path_factory.mktemp("p08")
    service, manifest = _create_account(
        tmp_path, strategy_id="strategy-a", strategy_version_id="version-a"
    )
    artifact_path = service.strategy_versions_root / "version-a.json"
    original_bytes = artifact_path.read_bytes()
    original_hash = account_module.file_sha256
    swapped = False

    def swap_path_after_hash(raw: bytes) -> str:
        nonlocal swapped
        digest = original_hash(raw)
        if not swapped and raw == original_bytes:
            swapped = True
            changed = json.loads(original_bytes.decode("utf-8"))
            changed["notes"] = "changed after the verified snapshot"
            _write_json(artifact_path, changed)
        return digest

    monkeypatch.setattr(account_module, "file_sha256", swap_path_after_hash)
    selected = service.select_account(manifest["account_namespace"])
    assert swapped
    assert selected.status is AccountBindingStatus.UNKNOWN
    assert selected.blockers == ("bound_artifact_changed_during_read",)


@pytest.mark.parametrize("invalid_value", [float("nan"), float("inf")])
def test_nonfinite_strategy_config_values_are_rejected(
    tmp_path_factory: pytest.TempPathFactory,
    invalid_value: float,
) -> None:
    tmp_path = tmp_path_factory.mktemp("p08")
    service, manifest = _create_account(
        tmp_path, strategy_id="strategy-a", strategy_version_id="version-a"
    )
    strategy_path = service.strategy_versions_root / "version-a.json"
    payload = json.loads(strategy_path.read_text(encoding="utf-8"))
    payload["config"]["unstable"] = invalid_value
    raw = _write_json(strategy_path, payload)
    fields = _manifest_fields(manifest)
    fields["strategy_artifact_sha256"] = file_sha256(raw)
    rebound = _write_rebound_manifest(service, fields)

    selected = service.select_account(rebound["account_namespace"])
    assert selected.status is AccountBindingStatus.REJECTED
    assert selected.blockers == ("strategy_params_config_not_canonical",)


def test_missing_binding_or_bound_artifact_remains_unknown(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    tmp_path = tmp_path_factory.mktemp("p08")
    personal_paths, strategy_root, contract_root = _fixture_roots(tmp_path)
    service = StrategyPaperAccountService(
        personal_paths=personal_paths,
        strategy_versions_root=strategy_root,
        contract_artifacts_root=contract_root,
    )
    missing = service.select_account("acct-" + "0" * 64)
    assert missing.status is AccountBindingStatus.UNKNOWN
    assert missing.blockers == ("strategy_account_binding_missing",)

    bound_tmp_path = tmp_path_factory.mktemp("p08bound")
    _, manifest = _create_account(
        bound_tmp_path,
        strategy_id="strategy-a",
        strategy_version_id="version-a",
    )
    roots = _fixture_roots(bound_tmp_path)
    service_missing_contract = StrategyPaperAccountService(
        personal_paths=roots[0],
        strategy_versions_root=roots[1],
        contract_artifacts_root=roots[2],
    )
    (roots[2] / "benchmarks" / "equal_weight_frozen__v1.json").unlink()
    selected = service_missing_contract.select_account(manifest["account_namespace"])
    assert selected.status is AccountBindingStatus.UNKNOWN
    assert selected.blockers == ("bound_artifact_missing",)


def test_empty_map_is_unknown_and_exact_lookup_preserves_candidate_failure(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    tmp_path = tmp_path_factory.mktemp("p08")
    personal_paths, strategy_root, contract_root = _fixture_roots(tmp_path)
    service = StrategyPaperAccountService(
        personal_paths=personal_paths,
        strategy_versions_root=strategy_root,
        contract_artifacts_root=contract_root,
    )
    service.accounts_root.mkdir(parents=True)
    empty = service.select_exact_version(
        strategy_id="strategy-a", strategy_version_id="version-a"
    )
    assert empty.status is AccountBindingStatus.UNKNOWN
    assert empty.blockers == ("strategy_account_map_empty",)

    _, valid_manifest = _create_account(
        tmp_path_factory.mktemp("p08bound"),
        strategy_id="strategy-a",
        strategy_version_id="version-a",
    )
    rejected_namespace = valid_manifest["account_namespace"]
    invalid_schema = dict(valid_manifest)
    invalid_schema["schema_version"] = "unexpected"
    _write_json(
        service.accounts_root / rejected_namespace / "account_binding.json",
        invalid_schema,
    )
    unresolved = service.select_exact_version(
        strategy_id="strategy-a", strategy_version_id="version-a"
    )
    assert unresolved.status is AccountBindingStatus.REJECTED
    assert unresolved.blockers == ("binding_schema_version_mismatch",)


def test_namespaced_reparse_entry_is_reported_as_rejected_not_omitted(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    tmp_path = tmp_path_factory.mktemp("p08")
    personal_paths, strategy_root, contract_root = _fixture_roots(tmp_path)
    service = StrategyPaperAccountService(
        personal_paths=personal_paths,
        strategy_versions_root=strategy_root,
        contract_artifacts_root=contract_root,
    )
    service.accounts_root.mkdir(parents=True)
    target = tmp_path / "outside-account"
    target.mkdir()
    namespace = "acct-" + "8" * 64
    link_path = service.accounts_root / namespace
    try:
        link_path.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Windows link/reparse setup unavailable: {type(exc).__name__}")

    account_map = service.list_accounts()
    assert len(account_map.entries) == 1
    assert account_map.entries[0].status is AccountBindingStatus.REJECTED
    assert account_map.entries[0].blockers == ("strategy_account_path_invalid:linked_path",)


def test_existing_weekly_consumer_constructor_and_build_fail_closed_for_strategy_route(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_path = tmp_path_factory.mktemp("p08")
    service, manifest = _create_account(
        tmp_path, strategy_id="strategy-a", strategy_version_id="version-a"
    )
    selected = service.select_account(manifest["account_namespace"])
    assert selected.route is not None
    reader = PaperPortfolioWeeklyEvidenceService(
        output_root=tmp_path / "output",
        portfolio_id=selected.binding.portfolio_id,
        benchmark_id=selected.binding.benchmark_id,
        route=selected.route,
        personal_paths=service.personal_paths,
    )

    def unexpected_read(*args: object, **kwargs: object) -> object:
        raise AssertionError("unverified strategy route must short-circuit before reads/metrics")

    monkeypatch.setattr(reader, "_read_snapshots", unexpected_read)
    monkeypatch.setattr(reader, "_read_benchmarks", unexpected_read)
    monkeypatch.setattr(reader, "_read_costs", unexpected_read)
    monkeypatch.setattr(reader._report_service, "build", unexpected_read)
    result = reader.build(
        period_start="2026-10-01",
        period_end="2026-10-02",
        expected_trading_days=2,
    )
    assert result.status == "not_computable"
    assert result.report is None
    assert result.blockers == ("strategy_account_row_provenance_unverified",)

    latest = reader.build_latest(expected_trading_days=5)
    assert latest.status == "not_computable"
    assert latest.report is None
    assert latest.blockers == ("strategy_account_row_provenance_unverified",)

