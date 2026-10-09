from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest

from data_module.ml_storage_capacity import (
    CANONICAL_HEAVY_CHAIN_SAFETY_RESERVE_BYTES,
    MLStorageCapacityBudget,
    acquire_heavy_chain_reservation,
    release_heavy_chain_reservation,
)
from app_module.ml_allocation_shadow_evidence import (
    _read_paper_preopen_coverage_receipt,
    load_t_minus_one_paper_ledger,
)
from app_module.paper_daily_status_contract import (
    PAPER_DAILY_ISOLATED_SCOPE_SCHEMA_VERSION,
    PAPER_DAILY_STATUS_SCHEMA_VERSION,
)
from app_module.paper_portfolio_snapshot_repository import (
    PaperPortfolioPositionSnapshot,
    PaperPortfolioSnapshot,
    PaperPortfolioSnapshotRepository,
)
from app_module.paper_trade_ledger import PaperTradeLedgerRepository
from data_module.pit_sector_machine_publisher import (
    consume_machine_pit_operational_candidate,
    publish_machine_pit_operational_candidate,
)
from data_module.pit_sector_membership_machine import (
    build_machine_pit_publication,
    write_machine_pit_receipt,
)
from scripts import run_daily_ml_allocation_derived_shadow as shadow
from scripts.scheduled import run_paper_portfolio_daily_isolated as preopen_adapter


TAIPEI = ZoneInfo("Asia/Taipei")
DECISION_AT = datetime(2026, 7, 31, 8, 30, tzinfo=TAIPEI)
MACHINE_DECISION_AT = DECISION_AT.astimezone(ZoneInfo("UTC"))


class _Calendar:
    def __init__(self, states: dict[date, tuple[bool | None, str]]) -> None:
        self.states = states

    def is_official_trading_day(
        self,
        target_date: date,
    ) -> tuple[bool | None, str]:
        return self.states.get(target_date, (None, "calendar_missing"))


class _RangeCalendar:
    def __init__(self, sessions: set[date]) -> None:
        self.sessions = sessions

    def is_official_trading_day(
        self,
        target_date: date,
    ) -> tuple[bool, str]:
        return (
            target_date in self.sessions,
            "test_official_session"
            if target_date in self.sessions
            else "test_non_trading_day",
        )

    def get_trading_days_in_range(
        self,
        start_date: date,
        end_date: date,
        *,
        allow_online_probe: bool = False,
    ) -> list[dict[str, object]]:
        del allow_online_probe
        rows: list[dict[str, object]] = []
        cursor = start_date
        while cursor <= end_date:
            rows.append(
                {
                    "date_str": cursor.isoformat(),
                    "is_trading_day": cursor in self.sessions,
                    "reason_code": (
                        "test_official_session"
                        if cursor in self.sessions
                        else "test_non_trading_day"
                    ),
                }
            )
            cursor = cursor.fromordinal(cursor.toordinal() + 1)
        return rows


def _preflight() -> SimpleNamespace:
    return SimpleNamespace(
        as_dict=lambda: {
            "within_budget": True,
            "stage": "test",
            "free_bytes": 500 * 1024**3,
        }
    )


def _release_fixture(tmp_path: Path) -> SimpleNamespace:
    release_root = tmp_path / "release"
    release_root.mkdir()
    files = {
        "release_manifest.json": b"release-manifest",
        "training_manifest_v2.json": json.dumps(
            {"training_as_of": "2026-07-30T08:30:00+08:00"}
        ).encode("utf-8"),
        "model.joblib": b"model",
        "preprocessor.json": b"preprocessor",
        "calibrator.json": b"calibrator",
    }
    for name, content in files.items():
        (release_root / name).write_bytes(content)
    identity = f"sha256:{'a' * 64}"
    manifest = SimpleNamespace(
        release_identity_hash=identity,
        artifact_file="model.joblib",
        preprocessor=SimpleNamespace(artifact_file="preprocessor.json"),
        calibration=SimpleNamespace(artifact_file="calibrator.json"),
        missing_policy=SimpleNamespace(
            policy_hash=f"sha256:{'b' * 64}",
            policy_id="balanced-v4-operational",
        ),
    )
    return SimpleNamespace(
        release_root=release_root,
        manifest_path=release_root / "release_manifest.json",
        manifest=manifest,
        release_manifest_file_hash=f"sha256:{'c' * 64}",
        release_id="release-test",
        model_id="model-test",
        dataset_id="dataset-test",
        artifact_hash=f"sha256:{'d' * 64}",
    )


def _release_evidence_fixture(release: SimpleNamespace) -> dict[str, object]:
    paths = [
        release.manifest_path,
        release.release_root / "training_manifest_v2.json",
        release.release_root / "model.joblib",
        release.release_root / "preprocessor.json",
        release.release_root / "calibrator.json",
    ]
    required: list[dict[str, object]] = []
    for path in paths:
        item = shadow._stat_evidence(path)
        item["sha256"] = shadow._file_hash(path)
        required.append(item)
    first_observed = "2026-07-31T00:30:00Z"
    return {
        "release_root": str(release.release_root),
        "release_id": release.release_id,
        "release_manifest_file_hash": release.release_manifest_file_hash,
        "release_identity_hash": release.manifest.release_identity_hash,
        "model_id": release.model_id,
        "dataset_id": release.dataset_id,
        "artifact_hash": release.artifact_hash,
        "training_as_of": "2026-07-30T08:30:00+08:00",
        "observed_at": "2026-07-31T08:30:00+08:00",
        "first_observed_at": first_observed,
        "observation_receipt_path": "test-receipt.json",
        "observation_receipt_file_hash": f"sha256:{'e' * 64}",
        "published_at": None,
        "published_time_basis": "not_inferred_from_mtime; use_first_observed_receipt_only",
        "required_file_mtime_diagnostics": [],
        "required_files": required,
    }


def _run_shadow_with_paper_state_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    include_coordination_contract: bool,
    receipt_variant: str = "valid",
) -> dict[str, Any]:
    """Run the complete outer wrapper while a fake preopen writer changes state."""

    release = _release_fixture(tmp_path)
    database = tmp_path / "twstock.db"
    paper = tmp_path / "paper.sqlite"
    ledger = tmp_path / "paper-trade-ledger.sqlite"
    output_root = tmp_path / "output"
    database.write_bytes(b"readonly-db")
    paper.write_bytes(b"paper-before")
    ledger.write_bytes(b"ledger-before")
    receipt_path = tmp_path / "preopen-receipt.json"
    real_file_hash = shadow._file_hash

    monkeypatch.setattr(shadow, "preflight_capacity", lambda **_: _preflight())
    monkeypatch.setattr(
        shadow.AllocationReleaseAdapter,
        "load",
        lambda _self, _root: release,
    )
    monkeypatch.setattr(
        shadow,
        "_release_evidence",
        lambda **_: _release_evidence_fixture(release),
    )
    monkeypatch.setattr(
        shadow,
        "_source_date_evidence",
        lambda **_: {
            "status": "completed",
            "latest_date_by_table": {},
            "symbol_latest_date": {},
            "strict_t_minus_one_rows_by_symbol": {},
        },
    )

    def fake_daily_run(**_kwargs: Any) -> dict[str, object]:
        state_hash = real_file_hash(paper)
        ledger_hash = real_file_hash(ledger)
        paper.write_bytes(b"paper-after-preopen-writer")
        state_after_hash = shadow._file_hash(paper)
        daily_status: dict[str, object] = {
            "status": "passed_rule_only",
            "orchestration_status": "completed",
            "shadow_observation_recorded": True,
            "decision_at": "2026-07-31T08:30:00+08:00",
            "strict_t_minus_one": "2026-07-30",
            "production_blend_alpha_bp": 0,
            "formal_oos_allowed": False,
            "broker_order_allowed": False,
        }
        if include_coordination_contract:
            write_contract = {
                "schema_version": "paper-state-write-contract.v1",
                "writer": "scripts.run_paper_portfolio_daily.run",
                "write_scope": "repository_paper_snapshot_append_only",
                "state_db": str(paper.resolve()),
                "snapshot_id": "paper-main-20260731",
                "decision_date": "2026-07-31",
                "snapshot_appended": True,
                "append_only": True,
                "research_only": True,
                "formal_credit": False,
                "broker_execution": False,
            }
            coverage = {
                "schema_version": "paper-preopen-coverage.v1",
                "status": "passed",
                "portfolio_id": "paper-main",
                "snapshot_id": "paper-main-20260731",
                "decision_date": "2026-07-31",
                "snapshot_relation": "current_decision_date_producer_receipt",
                "snapshot_appended": True,
                "snapshot_semantics": "preopen_t_minus_one_mark_to_market",
                "trading_calendar_validated": True,
                "trading_calendar_is_open": True,
                "state_db": str(paper.resolve()),
                "ledger_db": str(ledger.resolve()),
                "state_head": {"target_file_sha256": state_after_hash},
                "write_scope": "repository_paper_snapshot_append_only",
                "writer": "scripts.run_paper_portfolio_daily.run",
            }
            receipt_document = {
                "schema_version": PAPER_DAILY_STATUS_SCHEMA_VERSION,
                "isolated_scope_schema_version": (
                    PAPER_DAILY_ISOLATED_SCOPE_SCHEMA_VERSION
                ),
                "status": "passed",
                "portfolio_id": "paper-main",
                "snapshot_id": "paper-main-20260731",
                "decision_date": "2026-07-31",
                "state_db": str(paper.resolve()),
                "paper_ledger_db": str(ledger.resolve()),
                "writes_D_source": False,
                "writes_market_database": False,
                "formal_credit": False,
                "broker_execution": False,
                "snapshot_relation": "current_decision_date_producer_receipt",
                "preopen_coverage": coverage,
                "paper_state_write_contract": write_contract,
                "isolated_scope": {
                    "repository_state_db": str(paper.resolve()),
                    "ledger_db": str(ledger.resolve()),
                    "repository_state_scope": "repository_output_only",
                    "source_state_read_mode": (
                        "sqlite_uri_mode_ro_and_query_only"
                    ),
                    "writes_D_source": False,
                    "writes_market_database": False,
                    "formal_credit": False,
                    "broker_execution": False,
                    "state_head": {"target_file_sha256": state_after_hash},
                },
            }
            document_to_write: object = receipt_document
            if receipt_variant == "empty":
                document_to_write = {}
            elif receipt_variant == "inline_mismatch":
                document_to_write = {
                    **receipt_document,
                    "preopen_coverage": {
                        **coverage,
                        "ledger_db": str(tmp_path / "wrong-ledger.sqlite"),
                    },
                }
            elif receipt_variant == "stale":
                stale_date = "2026-07-30"
                document_to_write = {
                    **receipt_document,
                    "snapshot_id": "paper-main-20260730",
                    "decision_date": stale_date,
                    "preopen_coverage": {
                        **coverage,
                        "snapshot_id": "paper-main-20260730",
                        "decision_date": stale_date,
                    },
                    "paper_state_write_contract": {
                        **write_contract,
                        "snapshot_id": "paper-main-20260730",
                        "decision_date": stale_date,
                    },
                }
            elif receipt_variant == "scope":
                wrong_state = tmp_path / "wrong-paper.sqlite"
                wrong_state.write_bytes(b"wrong-state")
                document_to_write = {
                    **receipt_document,
                    "state_db": str(wrong_state.resolve()),
                    "preopen_coverage": {
                        **coverage,
                        "state_db": str(wrong_state.resolve()),
                    },
                    "paper_state_write_contract": {
                        **write_contract,
                        "state_db": str(wrong_state.resolve()),
                    },
                    "isolated_scope": {
                        **cast(dict[str, object], receipt_document["isolated_scope"]),
                        "repository_state_db": str(wrong_state.resolve()),
                    },
                }
            elif receipt_variant == "unowned_root_schema":
                document_to_write = {
                    **receipt_document,
                    "schema_version": "paper-portfolio-daily-unowned.v1",
                }
            elif receipt_variant == "unowned_scope_schema":
                document_to_write = {
                    **receipt_document,
                    "isolated_scope_schema_version": (
                        "paper-portfolio-daily-unowned-scope.v1"
                    ),
                }
            elif receipt_variant == "unowned_coverage_schema":
                document_to_write = {
                    **receipt_document,
                    "preopen_coverage": {
                        **coverage,
                        "schema_version": "paper-preopen-coverage-unowned.v1",
                    },
                }
            elif receipt_variant == "unsafe_credit":
                document_to_write = {
                    **receipt_document,
                    "formal_credit": True,
                }
            elif receipt_variant in {
                "bounded_legacy",
                "unbounded_legacy",
                "legacy_with_scope_schema",
            }:
                legacy_document = {
                    **receipt_document,
                    "schema_version": PAPER_DAILY_ISOLATED_SCOPE_SCHEMA_VERSION,
                }
                legacy_document.pop("isolated_scope_schema_version", None)
                if receipt_variant == "legacy_with_scope_schema":
                    legacy_document["isolated_scope_schema_version"] = (
                        PAPER_DAILY_ISOLATED_SCOPE_SCHEMA_VERSION
                    )
                if receipt_variant == "bounded_legacy":
                    legacy_document.update(
                        {
                            "producer": (
                                "scripts.scheduled.run_paper_portfolio_daily_isolated"
                            ),
                            "candidate_only": True,
                        }
                    )
                document_to_write = legacy_document
            elif receipt_variant == "stale_same_day":
                pass
            elif receipt_variant == "receipt_race":
                pass
            elif receipt_variant != "valid":
                raise AssertionError(f"unsupported receipt variant: {receipt_variant}")
            receipt_path.write_text(
                json.dumps(document_to_write, sort_keys=True),
                encoding="utf-8",
            )
            receipt_fields = (
                cast(dict[str, object], document_to_write)
                if receipt_variant in {
                    "bounded_legacy",
                    "unbounded_legacy",
                    "legacy_with_scope_schema",
                    "unsafe_credit",
                }
                else receipt_document
            )
            receipt = {
                **receipt_fields,
                "path": str(receipt_path.resolve()),
                "file_hash": real_file_hash(receipt_path),
                "schema_compatibility": (
                    "bounded_legacy"
                    if receipt_variant == "bounded_legacy"
                    else "canonical"
                ),
            }
            daily_status.update(
                {
                    "paper_read_consistency": {
                        "state_db": {
                            "path": str(paper.resolve()),
                            "mode": "ro/query_only",
                            "hash_before": state_hash,
                            "hash_after": state_hash,
                            "unchanged": True,
                        },
                        "trade_ledger_db": {
                            "path": str(ledger.resolve()),
                            "mode": "ro/query_only",
                            "hash_before": ledger_hash,
                            "hash_after": ledger_hash,
                            "unchanged": True,
                        },
                        "preopen_coverage_receipt": receipt,
                    },
                    "paper_preopen_coverage_receipt_path": str(
                        receipt_path.resolve()
                    ),
                    "paper_preopen_coverage_receipt_file_hash": receipt[
                        "file_hash"
                    ],
                }
            )
            if receipt_variant == "stale_same_day":
                paper.write_bytes(b"paper-after-unaccounted-modification")
        return daily_status

    monkeypatch.setattr(shadow.daily, "run", fake_daily_run)
    if receipt_variant == "receipt_race":
        race_state = {"triggered": False}

        def racing_file_hash(path: Path) -> str:
            result = real_file_hash(path)
            if path.resolve() == receipt_path.resolve() and not race_state[
                "triggered"
            ]:
                race_state["triggered"] = True
                receipt_path.write_text("{}", encoding="utf-8")
            return result

        monkeypatch.setattr(shadow, "_file_hash", racing_file_hash)
    result = shadow.run(
        database_path=database,
        output_root=output_root,
        release_root=release.release_root,
        paper_state_db_path=paper,
        paper_trade_ledger_db_path=ledger,
        mode=shadow.RESEARCH_MODE,
        now=datetime(2026, 7, 31, 10, 0, tzinfo=TAIPEI),
        calendar=_Calendar({date(2026, 7, 31): (True, "open")}),
        lock_path=tmp_path / "shared.lock",
    )
    return cast(dict[str, Any], result)


def _patch_real_preopen_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path, Path, Path, _RangeCalendar]:
    """Prepare the real isolated preopen producer with a bounded fixture."""

    data_root = tmp_path / "D-source"
    operation_root = tmp_path / "repo" / "output" / "paper_execution_eod_replay"
    source_state = data_root / "output" / "paper_portfolio" / "paper_portfolio.sqlite"
    baseline = data_root / "output" / "paper_portfolio" / "baseline_20260712.json"
    market = data_root / "sqlite" / "twstock.db"
    state = operation_root / "paper_portfolio" / "paper_portfolio.sqlite"
    manifest = operation_root / "paper_portfolio" / "state_seed_manifest.json"
    ledger = operation_root / "paper_trade_ledger.sqlite"
    source_repository = PaperPortfolioSnapshotRepository(source_state)
    source_repository.append(
        PaperPortfolioSnapshot(
            snapshot_id="paper-main-20260707",
            portfolio_id="paper-main",
            decision_date="2026-07-07",
            source_result_id="source-20260707",
            cash=Decimal("80000.00"),
            total_value=Decimal("100000.00"),
            positions=(
                PaperPortfolioPositionSnapshot(
                    stock_code="2330",
                    quantity=1000,
                    mark_price=Decimal("20.00"),
                    market_value=Decimal("20000.00"),
                    weight_bp=2000,
                ),
            ),
        )
    )
    source_repository.append(
        PaperPortfolioSnapshot(
            snapshot_id="paper-main-20260712-baseline",
            portfolio_id="paper-main",
            decision_date="2026-07-12",
            source_result_id="source-baseline-1",
            cash=Decimal("80000.00"),
            total_value=Decimal("100000.00"),
            positions=(
                PaperPortfolioPositionSnapshot(
                    stock_code="2330",
                    quantity=1000,
                    mark_price=Decimal("20.00"),
                    market_value=Decimal("20000.00"),
                    weight_bp=2000,
                ),
            ),
        )
    )
    source_repository.append(
        PaperPortfolioSnapshot(
            snapshot_id="paper-main-20260713",
            portfolio_id="paper-main",
            decision_date="2026-07-13",
            source_result_id="source-20260713",
            cash=Decimal("80000.00"),
            total_value=Decimal("101000.00"),
            positions=(
                PaperPortfolioPositionSnapshot(
                    stock_code="2330",
                    quantity=1000,
                    mark_price=Decimal("21.00"),
                    market_value=Decimal("21000.00"),
                    weight_bp=2079,
                ),
            ),
        )
    )
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(
        json.dumps(
            {
                "decision_date": "2026-07-12",
                "source_result_id": "source-baseline-1",
                "residual_cash": "80000.00",
                "allocations": [
                    {
                        "stock_code": "2330",
                        "executable_shares": 1000,
                        "reference_price": "20.00",
                        "executable_amount": "20000.00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    market.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(market) as connection:
        connection.execute(
            "CREATE TABLE daily_prices (日期 TEXT, 證券代號 TEXT, 收盤價 TEXT)"
        )
        connection.execute(
            "INSERT INTO daily_prices VALUES (?, ?, ?)",
            ("20260713", "2330", "21.00"),
        )
    PaperTradeLedgerRepository(ledger)
    monkeypatch.setattr(preopen_adapter, "ROOT", operation_root.parents[1])
    monkeypatch.setattr(preopen_adapter, "DEFAULT_DATA_ROOT", data_root)
    monkeypatch.setattr(preopen_adapter, "SOURCE_STATE_DB", source_state)
    monkeypatch.setattr(preopen_adapter, "SOURCE_BASELINE_PATH", baseline)
    monkeypatch.setattr(preopen_adapter, "OPERATIONAL_ROOT", operation_root)
    monkeypatch.setattr(preopen_adapter, "PAPER_STATE_ROOT", state.parent)
    monkeypatch.setattr(preopen_adapter, "STATE_DB", state)
    monkeypatch.setattr(preopen_adapter, "STATE_SEED_MANIFEST", manifest)
    monkeypatch.setattr(preopen_adapter, "MARKET_DB", market)
    monkeypatch.setattr(preopen_adapter, "LEDGER_DB", ledger)
    calendar = _RangeCalendar(
        {date(2026, 7, 7), date(2026, 7, 12), date(2026, 7, 13), date(2026, 7, 14)}
    )
    return source_state, baseline, market, state, ledger, calendar


def _machine_operational_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """建立真正由 controlled publisher 簽章的 current-day candidate。"""

    monkeypatch.setenv(
        "RULE_CHAMPION_CONTROLLED_STORE_HMAC_KEY",
        "test-controlled-key",
    )
    monkeypatch.setenv(
        "RULE_CHAMPION_CONTROLLED_STORE_ID",
        "machine-pit-wrapper-test-store",
    )
    machine_output = tmp_path / "machine"
    machine_output.mkdir()
    publication = build_machine_pit_publication(
        raw_payloads={
            "twse": json.dumps(
                [
                    {
                        "公司代號": "1101",
                        "產業別": "01",
                        "出表日期": "20260731",
                    }
                ],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
            "tpex": json.dumps(
                [
                    {
                        "SecuritiesCompanyCode": "5501",
                        "SecuritiesIndustryCode": "03",
                        "Date": "2026-07-31",
                    }
                ],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
        },
        output_dir=machine_output,
        captured_at=datetime(2026, 7, 31, 0, 0, tzinfo=ZoneInfo("UTC")),
        now=datetime(2026, 7, 31, 0, 10, tzinfo=ZoneInfo("UTC")),
    )
    receipt_path = tmp_path / "machine-receipt.json"
    write_machine_pit_receipt(
        publication.publication_path,
        receipt_path=receipt_path,
        now=datetime(2026, 7, 31, 0, 20, tzinfo=ZoneInfo("UTC")),
    )
    operational_path = tmp_path / "machine-operational.json"
    publish_machine_pit_operational_candidate(
        receipt_path,
        output_path=operational_path,
        decision_at=MACHINE_DECISION_AT,
        now=datetime(2026, 7, 31, 0, 40, tzinfo=ZoneInfo("UTC")),
    )
    return operational_path


def test_release_receipt_preserves_first_observation_across_capture_times(
    tmp_path: Path,
) -> None:
    release = _release_fixture(tmp_path)
    output_root = tmp_path / "output"

    first = shadow._release_evidence(
        release_root=release.release_root,
        release=cast(Any, release),
        output_root=output_root,
        capture_at=datetime(2026, 7, 31, 8, 20, tzinfo=TAIPEI),
    )
    second = shadow._release_evidence(
        release_root=release.release_root,
        release=cast(Any, release),
        output_root=output_root,
        capture_at=datetime(2026, 7, 31, 9, 0, tzinfo=TAIPEI),
    )

    assert first["first_observed_at"] == "2026-07-31T08:20:00.000000+08:00"
    assert second["first_observed_at"] == first["first_observed_at"]
    receipt_path = Path(str(second["observation_receipt_path"]))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["observed_at"] == first["first_observed_at"]
    assert shadow._file_hash(receipt_path) == second[
        "observation_receipt_file_hash"
    ]


def test_integrity_projection_reports_formal_stat_and_release_hash_changes(
    tmp_path: Path,
) -> None:
    database = tmp_path / "twstock.db"
    database.write_bytes(b"formal-before")
    database_before = shadow._stat_evidence(database)
    database.write_bytes(b"formal-after-with-different-size")
    database_after = shadow._stat_evidence(database)

    assert "size_bytes" in shadow._stat_changed_fields(
        database_before,
        database_after,
    )

    release = _release_fixture(tmp_path)
    release_evidence = _release_evidence_fixture(release)
    required_files = cast(list[object], release_evidence["required_files"])
    first = shadow._release_files_integrity(required_files)
    assert first["unchanged"] is True
    assert first["which_changed"] == []
    before_hashes = cast(dict[str, object], first["hashes_before"])
    after_hashes = cast(dict[str, object], first["hashes_after"])
    assert before_hashes == after_hashes

    changed_path = release.release_root / "model.joblib"
    changed_path.write_bytes(b"MODEL")
    second = shadow._release_files_integrity(required_files)
    assert second["unchanged"] is False
    changed_paths = cast(list[str], second["which_changed"])
    assert str(changed_path.resolve()) in changed_paths
    changed_hashes_before = cast(dict[str, object], second["hashes_before"])
    changed_hashes_after = cast(dict[str, object], second["hashes_after"])
    assert changed_hashes_before[str(changed_path.resolve())] != (
        changed_hashes_after[str(changed_path.resolve())]
    )
    changed_entry = next(
        item
        for item in cast(list[dict[str, object]], second["required_files"])
        if item.get("path") == str(changed_path.resolve())
    )
    assert "sha256" in cast(list[str], changed_entry["changed_fields"])

    legacy_expected = dict(
        cast(dict[str, object], required_files[0])
    )
    legacy_expected.pop("exists", None)
    legacy_expected["path"] = str(
        Path(legacy_expected["path"]).parent
        / ".."
        / Path(legacy_expected["path"]).parent.name
        / Path(legacy_expected["path"]).name
    )
    legacy = shadow._release_files_integrity([legacy_expected])
    assert legacy["unchanged"] is True


@pytest.mark.parametrize("receipt_variant", ("valid", "bounded_legacy"))
def test_outer_wrapper_accepts_only_receipted_preopen_state_writer_overlap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    receipt_variant: str,
) -> None:
    payload = _run_shadow_with_paper_state_change(
        tmp_path,
        monkeypatch,
        include_coordination_contract=True,
        receipt_variant=receipt_variant,
    )

    assert payload["status"] == "completed"
    coordination = cast(dict[str, Any], payload["paper_state_coordination"])
    assert coordination["status"] == "expected_preopen_producer_overlap"
    assert coordination["authorized"] is True
    checks = cast(dict[str, Any], coordination["contract_checks"])
    assert all(checks.values())
    source = cast(dict[str, Any], payload["source"])
    paper_source = cast(dict[str, Any], source["paper_state_db"])
    assert paper_source["unchanged"] is False
    assert paper_source["integrity_verified"] is True


def test_real_preopen_producer_and_inner_reader_authorize_current_state_overlap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive overlap path must consume real producer/reader evidence."""

    _source, _baseline, market, state, ledger, calendar = _patch_real_preopen_scope(
        tmp_path,
        monkeypatch,
    )
    seed = preopen_adapter.ensure_repo_state_from_readonly_source(
        source=preopen_adapter.SOURCE_STATE_DB,
        target=state,
        manifest_path=preopen_adapter.STATE_SEED_MANIFEST,
        observed_at=datetime(2026, 7, 14, 8, 20, tzinfo=TAIPEI),
    )
    assert seed["status"] == "seeded"
    release = _release_fixture(tmp_path)
    output_root = tmp_path / "derived-output"
    monkeypatch.setattr(shadow, "preflight_capacity", lambda **_: _preflight())
    monkeypatch.setattr(
        shadow.AllocationReleaseAdapter,
        "load",
        lambda _self, _root: release,
    )
    monkeypatch.setattr(
        shadow,
        "_release_evidence",
        lambda **_: _release_evidence_fixture(release),
    )
    monkeypatch.setattr(
        shadow,
        "_source_date_evidence",
        lambda **_: {
            "status": "completed",
            "latest_date_by_table": {},
            "symbol_latest_date": {},
            "strict_t_minus_one_rows_by_symbol": {},
        },
    )

    def fake_daily_run(**_kwargs: Any) -> dict[str, object]:
        producer_result = preopen_adapter.run_isolated(
            now=datetime(2026, 7, 14, 8, 31, tzinfo=TAIPEI),
            decision_at=datetime(2026, 7, 14, 8, 30, tzinfo=TAIPEI),
            calendar=calendar,  # type: ignore[arg-type]
        )
        assert producer_result["status"] == "passed"
        context = load_t_minus_one_paper_ledger(
            state_db_path=state,
            portfolio_id="paper-main",
            decision_date=date(2026, 7, 14),
            paper_trade_ledger_db_path=ledger,
            official_calendar=calendar,
        )
        consistency = context.paper_read_consistency
        assert consistency is not None
        return {
            "status": "passed_rule_only",
            "orchestration_status": "completed",
            "shadow_observation_recorded": True,
            "decision_at": "2026-07-14T08:30:00+08:00",
            "strict_t_minus_one": "2026-07-13",
            "production_blend_alpha_bp": 0,
            "formal_oos_allowed": False,
            "broker_order_allowed": False,
            "paper_read_consistency": dict(consistency),
            "paper_preopen_coverage_receipt_path": (
                context.paper_preopen_coverage_receipt_path
            ),
            "paper_preopen_coverage_receipt_file_hash": (
                context.paper_preopen_coverage_receipt_file_hash
            ),
        }

    monkeypatch.setattr(shadow.daily, "run", fake_daily_run)
    payload = cast(
        dict[str, Any],
        shadow.run(
            database_path=market,
            output_root=output_root,
            release_root=release.release_root,
            paper_state_db_path=state,
            paper_trade_ledger_db_path=ledger,
            mode=shadow.RESEARCH_MODE,
            now=datetime(2026, 7, 14, 10, 0, tzinfo=TAIPEI),
            calendar=calendar,
        ),
    )

    assert payload["status"] == "completed"
    coordination = cast(dict[str, Any], payload["paper_state_coordination"])
    assert coordination["status"] == "expected_preopen_producer_overlap"
    assert coordination["authorized"] is True
    checks = cast(dict[str, Any], coordination["contract_checks"])
    assert all(checks.values())
    assert Path(str(payload["record_path"])).is_file()


def test_outer_wrapper_blocks_unaccounted_paper_state_writer_overlap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _run_shadow_with_paper_state_change(
        tmp_path,
        monkeypatch,
        include_coordination_contract=False,
    )

    assert payload["status"] == "failed_read_only_integrity"
    coordination = cast(dict[str, Any], payload["paper_state_coordination"])
    assert coordination["status"] == "unaccounted_change"
    assert coordination["authorized"] is False
    assert cast(dict[str, Any], payload["production_boundaries"])[
        "production_action_allowed"
    ] is False
    source = cast(dict[str, Any], payload["source"])
    assert cast(dict[str, Any], source["database"])["unchanged"] is True
    assert cast(dict[str, Any], source["database"])["changed_fields"] == []
    paper_source = cast(dict[str, Any], source["paper_state_db"])
    assert paper_source["unchanged"] is False
    assert paper_source["integrity_verified"] is False
    assert paper_source["change_class"] == "unaccounted_change"
    release_source = cast(dict[str, Any], source["release_manifest"])
    assert release_source["unchanged"] is True
    assert cast(dict[str, Any], release_source["required_file_integrity"])[
        "which_changed"
    ] == []


@pytest.mark.parametrize(
    "receipt_variant",
    (
        "empty",
        "inline_mismatch",
        "stale",
        "stale_same_day",
        "scope",
        "unowned_root_schema",
        "unowned_scope_schema",
        "unowned_coverage_schema",
        "unbounded_legacy",
        "legacy_with_scope_schema",
        "unsafe_credit",
        "receipt_race",
    ),
)
def test_outer_wrapper_blocks_invalid_preopen_receipt_variants(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    receipt_variant: str,
) -> None:
    payload = _run_shadow_with_paper_state_change(
        tmp_path,
        monkeypatch,
        include_coordination_contract=True,
        receipt_variant=receipt_variant,
    )

    assert payload["status"] == "failed_read_only_integrity"
    coordination = cast(dict[str, Any], payload["paper_state_coordination"])
    assert coordination["authorized"] is False
    checks = cast(dict[str, Any], coordination["contract_checks"])
    assert checks["receipt_content_matches_inline"] is (
        receipt_variant == "stale_same_day"
    )
    if receipt_variant == "stale_same_day":
        assert checks["receipt_scope_and_current_state_bound"] is False
    if receipt_variant == "receipt_race":
        assert checks["preopen_receipt_valid"] is False


def test_frozen_canonical_preopen_receipt_preserves_exact_bytes_and_schema_layers(
    tmp_path: Path,
) -> None:
    fixture_path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "paper_preopen_coverage_receipts"
        / "canonical_20260922_latest_status.json"
    )
    fixture_bytes = fixture_path.read_bytes()
    fixture_sha256 = hashlib.sha256(fixture_bytes).hexdigest().upper()
    assert len(fixture_bytes) == 5416
    assert fixture_sha256 == (
        "8084250A3B2F738CD76E811A6636DB40DABD6A606F10F8FAFF1909FC54E5C795"
    )

    frozen_payload = json.loads(fixture_bytes.decode("utf-8"))
    assert isinstance(frozen_payload, dict)
    receipt_path = tmp_path / "frozen-paper-status.json"
    receipt_path.write_bytes(fixture_bytes)
    assert receipt_path.read_bytes() == fixture_bytes

    receipt_snapshot = cast(
        PaperPortfolioSnapshot,
        SimpleNamespace(
            portfolio_id=frozen_payload["portfolio_id"],
            snapshot_id=frozen_payload["snapshot_id"],
            decision_date=frozen_payload["decision_date"],
        ),
    )
    state_snapshot = cast(
        PaperPortfolioSnapshot,
        SimpleNamespace(
            portfolio_id=frozen_payload["portfolio_id"],
            snapshot_id="paper-main-20260921",
            decision_date="2026-09-21",
        ),
    )
    state_db_path = Path(str(frozen_payload["state_db"]))
    ledger_db_path = Path(str(frozen_payload["paper_ledger_db"]))
    result = _read_paper_preopen_coverage_receipt(
        state_db_path=state_db_path,
        state_snapshot=state_snapshot,
        available_snapshots=(receipt_snapshot,),
        ledger_db_path=ledger_db_path,
        decision_date=date.fromisoformat(
            str(frozen_payload["decision_date"])
        ),
        configured_path=receipt_path,
    )

    assert result is not None
    assert result["file_hash"] == "sha256:" + fixture_sha256.lower()
    assert result["schema_version"] == PAPER_DAILY_STATUS_SCHEMA_VERSION
    assert (
        result["isolated_scope_schema_version"]
        == PAPER_DAILY_ISOLATED_SCOPE_SCHEMA_VERSION
    )
    assert result["schema_compatibility"] == "canonical"
    assert cast(dict[str, Any], result["preopen_coverage"])["schema_version"] == (
        "paper-preopen-coverage.v1"
    )
    assert receipt_path.read_bytes() == fixture_bytes


def test_reader_rejects_legacy_root_with_separate_scope_schema(
    tmp_path: Path,
) -> None:
    """舊 root 相容路徑不得同時帶入另一個 scope schema。"""
    fixture_path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "paper_preopen_coverage_receipts"
        / "canonical_20260922_latest_status.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    payload["schema_version"] = PAPER_DAILY_ISOLATED_SCOPE_SCHEMA_VERSION
    payload["isolated_scope_schema_version"] = (
        PAPER_DAILY_ISOLATED_SCOPE_SCHEMA_VERSION
    )
    payload["producer"] = "scripts.scheduled.run_paper_portfolio_daily_isolated"
    payload["candidate_only"] = True
    receipt_path = tmp_path / "legacy-root-with-scope.json"
    receipt_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    receipt_snapshot = cast(
        PaperPortfolioSnapshot,
        SimpleNamespace(
            portfolio_id=payload["portfolio_id"],
            snapshot_id=payload["snapshot_id"],
            decision_date=payload["decision_date"],
        ),
    )
    state_snapshot = cast(
        PaperPortfolioSnapshot,
        SimpleNamespace(
            portfolio_id=payload["portfolio_id"],
            snapshot_id="paper-main-20260921",
            decision_date="2026-09-21",
        ),
    )

    with pytest.raises(
        ValueError,
        match="paper preopen coverage receipt root schema is not governed",
    ):
        _read_paper_preopen_coverage_receipt(
            state_db_path=Path(str(payload["state_db"])),
            state_snapshot=state_snapshot,
            available_snapshots=(receipt_snapshot,),
            ledger_db_path=Path(str(payload["paper_ledger_db"])),
            decision_date=date(2026, 9, 22),
            configured_path=receipt_path,
        )


def test_select_natural_decision_rejects_invalid_clock_and_unknown_calendar() -> None:
    invalid = shadow._select_natural_decision(
        calendar=_Calendar({date(2026, 7, 31): (True, "open")} ),
        now=datetime(2026, 7, 31, 9, 0, tzinfo=TAIPEI),
        requested_decision_at="2026-07-31T09:00:00+08:00",
    )
    assert invalid["status"] == "blocked_invalid_decision_at"

    unknown = shadow._select_natural_decision(
        calendar=_Calendar({}),
        now=datetime(2026, 7, 31, 9, 0, tzinfo=TAIPEI),
        requested_decision_at=None,
    )
    assert unknown["status"] == "blocked_calendar_unknown"


def test_forward_late_capture_is_blocked_before_daily_consumer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release_fixture(tmp_path)
    database = tmp_path / "twstock.db"
    paper = tmp_path / "paper.sqlite"
    late_machine_path = tmp_path / "late-machine-operational.json"
    database.write_bytes(b"readonly-db")
    paper.write_bytes(b"readonly-paper")
    late_machine_path.write_bytes(b"candidate-arrived-after-window")
    monkeypatch.setattr(shadow, "preflight_capacity", lambda **_: _preflight())
    monkeypatch.setattr(
        shadow.AllocationReleaseAdapter,
        "load",
        lambda _self, _root: release,
    )
    monkeypatch.setattr(
        shadow,
        "_release_evidence",
        lambda **_: _release_evidence_fixture(release),
    )
    monkeypatch.setattr(
        shadow.daily,
        "run",
        lambda **_: pytest.fail("forward-late capture must not call daily"),
    )

    result = shadow.run(
        database_path=database,
        output_root=tmp_path / "output",
        release_root=release.release_root,
        paper_state_db_path=paper,
        mode=shadow.FORWARD_MODE,
        decision_at="2026-07-31T08:30:00+08:00",
        now=datetime(2026, 7, 31, 10, 0, tzinfo=TAIPEI),
        calendar=_Calendar(
            {
                date(2026, 7, 31): (True, "open"),
                date(2026, 7, 30): (True, "open"),
            }
        ),
        pit_machine_operational_path=late_machine_path,
        lock_path=tmp_path / "shared.lock",
    )

    payload = cast(dict[str, Any], result)
    assert payload["status"] == "blocked_forward_decision_window"
    assert cast(dict[str, Any], payload["decision_clock"])[
        "within_forward_window"
    ] is False
    assert cast(dict[str, Any], payload["production_boundaries"])[
        "production_blend_alpha_bp"
    ] == 0


def test_research_capture_delegates_with_bounded_budget_and_rule_comparison(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release_fixture(tmp_path)
    database = tmp_path / "twstock.db"
    paper = tmp_path / "paper.sqlite"
    database.write_bytes(b"readonly-db")
    paper.write_bytes(b"readonly-paper")
    output_root = tmp_path / "output"
    machine_path = _machine_operational_candidate(tmp_path, monkeypatch)
    observation_path = (
        output_root
        / "scheduled"
        / "ml_allocation_copilot"
        / "shadow.json"
    )
    observation_path.parent.mkdir(parents=True)
    observation_path.write_text(
        json.dumps(
            {
                "record_hash": f"sha256:{'f' * 64}",
                "lanes": [
                    {
                        "alpha_bp": 0,
                        "lane_hash": f"sha256:{'1' * 64}",
                        "estimated_cost": "0",
                        "turnover_bp": 0,
                        "constraint_violation_count": 0,
                        "research_only": True,
                    },
                    {
                        "alpha_bp": 2000,
                        "lane_hash": f"sha256:{'2' * 64}",
                        "estimated_cost": "1.2",
                        "turnover_bp": 10,
                        "constraint_violation_count": 0,
                        "research_only": True,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(shadow, "preflight_capacity", lambda **_: _preflight())
    monkeypatch.setattr(
        shadow.AllocationReleaseAdapter,
        "load",
        lambda _self, _root: release,
    )
    monkeypatch.setattr(
        shadow,
        "_release_evidence",
        lambda **_: _release_evidence_fixture(release),
    )
    monkeypatch.setattr(
        shadow,
        "_source_date_evidence",
        lambda **_: {
            "status": "completed",
            "latest_date_by_table": {
                "daily_prices": "20260904",
                "technical_indicators": "20260904",
                "market_indices": "20260904",
                "industry_indices": "20260904",
            },
            "symbol_latest_date": {"1101": "20260904"},
            "strict_t_minus_one_rows_by_symbol": {"1101": 1},
        },
    )
    captured: dict[str, Any] = {}

    def fake_daily_run(**kwargs: Any) -> dict[str, object]:
        captured.update(kwargs)
        machine_readback = consume_machine_pit_operational_candidate(
            Path(kwargs["pit_machine_operational_path"]),
            decision_at=kwargs["decision_at"],
            now=kwargs["decision_at"],
        )
        captured["machine_readback"] = machine_readback
        return {
            "status": "passed_rule_only",
            "orchestration_status": "completed",
            "shadow_observation_recorded": True,
            "shadow_observation_path": str(observation_path),
            "strict_t_minus_one": "2026-07-30",
            "production_blend_alpha_bp": 0,
            "formal_oos_allowed": False,
            "broker_order_allowed": False,
        }

    monkeypatch.setattr(shadow.daily, "run", fake_daily_run)
    result = shadow.run(
        database_path=database,
        output_root=output_root,
        release_root=release.release_root,
        paper_state_db_path=paper,
        mode=shadow.RESEARCH_MODE,
        now=datetime(2026, 7, 31, 10, 0, tzinfo=TAIPEI),
        calendar=_Calendar(
            {
                date(2026, 7, 31): (True, "open"),
                date(2026, 7, 30): (True, "open"),
            }
        ),
        pit_machine_operational_path=machine_path,
        lock_path=tmp_path / "shared.lock",
    )

    payload = cast(dict[str, Any], result)
    assert payload["status"] == "completed"
    assert payload["mode"] == shadow.RESEARCH_MODE
    assert cast(dict[str, Any], payload["release"])[
        "available_before_decision"
    ] is True
    assert cast(dict[str, Any], payload["decision_clock"])[
        "research_late_capture"
    ] is True
    cost_performance = cast(dict[str, Any], payload["cost_performance"])
    rule_comparison = cast(dict[str, Any], cost_performance["rule_comparison"])
    rule_lane = cast(dict[str, Any], rule_comparison["rule_lane"])
    assert rule_lane["alpha_bp"] == 0
    assert cast(dict[str, Any], cost_performance["equal_weight_comparison"])[
        "status"
    ] == "deferred"
    assert captured["pit_machine_operational_path"] == machine_path.resolve()
    machine_readback = cast(dict[str, Any], captured["machine_readback"])
    assert machine_readback["status"] == "machine_verified"
    assert machine_readback["available_at"] == "2026-07-31T00:00:00+00:00"
    assert machine_readback["effective_from"] == "2026-07-31"
    assert machine_readback["candidate_only"] is True
    assert machine_readback["formal_oos_allowed"] is False
    assert machine_readback["production_action_allowed"] is False
    budget = captured["capacity_budget"]
    assert isinstance(budget, MLStorageCapacityBudget)
    assert budget.persistent_new_bytes_budget is not None
    assert budget.persistent_new_bytes_budget < 256 * 1024**2
    assert budget.temporary_peak_bytes_budget == 256 * 1024**2
    assert budget.safety_reserve_bytes == CANONICAL_HEAVY_CHAIN_SAFETY_RESERVE_BYTES
    source = cast(dict[str, Any], payload["source"])
    assert cast(dict[str, Any], source["database"])["unchanged"] is True
    assert cast(dict[str, Any], source["paper_state_db"])["unchanged"] is True
    assert cast(dict[str, Any], source["release_manifest"])["unchanged"] is True
    capacity = cast(dict[str, Any], payload["capacity"])
    assert capacity["temporary_peak_bytes_observed"] is None
    assert capacity["within_temporary_budget"] is None
    baseline = int(capacity["persistent_existing_bytes_before_run"])
    assert shadow.directory_size_bytes(output_root) - baseline == int(
        capacity["persistent_new_bytes_observed"]
    )

    recovered = acquire_heavy_chain_reservation(tmp_path / "shared.lock")
    assert recovered is not None
    release_heavy_chain_reservation(recovered)


def test_research_capture_forwards_exact_archive_contract_to_daily(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release_fixture(tmp_path)
    database = tmp_path / "twstock.db"
    paper = tmp_path / "paper.sqlite"
    database.write_bytes(b"readonly-db")
    paper.write_bytes(b"readonly-paper")
    output_root = tmp_path / "output"
    archive_root = tmp_path / "pit_candidate_archive"
    archive_root.mkdir()
    manifest = archive_root / "2026-07-30" / "archive-key" / "archive_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("frozen-manifest", encoding="utf-8")
    frozen_hash = shadow._file_hash(manifest)
    monkeypatch.setattr(shadow, "preflight_capacity", lambda **_: _preflight())
    monkeypatch.setattr(
        shadow.AllocationReleaseAdapter,
        "load",
        lambda _self, _root: release,
    )
    monkeypatch.setattr(
        shadow,
        "_release_evidence",
        lambda **_: _release_evidence_fixture(release),
    )
    monkeypatch.setattr(
        shadow,
        "_source_date_evidence",
        lambda **_: {"status": "completed", "strict_t_minus_one_rows_by_symbol": {}},
    )
    captured: dict[str, Any] = {}

    def fake_daily_run(**kwargs: Any) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "status": "passed_rule_only",
            "orchestration_status": "completed",
            "shadow_observation_recorded": True,
            "strict_t_minus_one": "2026-07-30",
            "production_blend_alpha_bp": 0,
            "formal_oos_allowed": False,
            "broker_order_allowed": False,
        }

    monkeypatch.setattr(shadow.daily, "run", fake_daily_run)
    result = shadow.run(
        database_path=database,
        output_root=output_root,
        release_root=release.release_root,
        paper_state_db_path=paper,
        mode=shadow.RESEARCH_MODE,
        now=datetime(2026, 7, 31, 10, 0, tzinfo=TAIPEI),
        calendar=_Calendar(
            {
                date(2026, 7, 31): (True, "open"),
                date(2026, 7, 30): (True, "open"),
            }
        ),
        pit_machine_archive_root=archive_root,
        pit_machine_archive_manifest=manifest,
        pit_machine_archive_manifest_file_hash=frozen_hash,
        lock_path=tmp_path / "shared.lock",
    )

    assert cast(dict[str, Any], result)["status"] == "completed"
    assert captured["pit_machine_operational_path"] is None
    assert captured["pit_machine_archive_root"] == archive_root.resolve()
    assert captured["pit_machine_archive_manifest"] == manifest.resolve()
    assert captured["pit_machine_archive_manifest_file_hash"] == frozen_hash


@pytest.mark.parametrize("revision_blocked", [False, True])
def test_release_load_failure_preserves_revision_blocker_without_daily_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, revision_blocked: bool,
) -> None:
    database = tmp_path / "twstock.db"
    paper = tmp_path / "paper.sqlite"
    database.write_bytes(b"readonly-db")
    paper.write_bytes(b"readonly-paper")
    monkeypatch.setattr(shadow, "preflight_capacity", lambda **_: _preflight())
    def reject(_self: object, _root: Path) -> None:
        if revision_blocked:
            raise shadow.DailyPriceSourceRevisionError("model artifact is quarantined")
        raise FileNotFoundError("release does not exist")
    monkeypatch.setattr(shadow.AllocationReleaseAdapter, "load", reject)
    monkeypatch.setattr(shadow.daily, "run", lambda **_: pytest.fail("invalid release must stop before daily"))
    result = shadow.run(
        database_path=database, paper_state_db_path=paper,
        output_root=tmp_path / "output", release_root=tmp_path / "release",
        now=datetime(2026, 7, 31, 10, 0, tzinfo=TAIPEI),
        calendar=_Calendar({date(2026, 7, 31): (True, "open"), date(2026, 7, 30): (True, "open")}),
        lock_path=tmp_path / "shared.lock",
    )
    payload = cast(dict[str, Any], result)
    assert payload["status"] == ("blocked_source_revision_release" if revision_blocked else "blocked_missing_release")
    if revision_blocked:
        assert payload["blocked_reason"] == "release_quarantined_by_daily_price_source_revision"
    assert Path(str(payload["record_path"])).is_file()
    assert database.read_bytes() == b"readonly-db"
    assert paper.read_bytes() == b"readonly-paper"


def test_missing_paper_input_is_persisted_without_daily_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release_fixture(tmp_path)
    database = tmp_path / "twstock.db"
    database.write_bytes(b"readonly-db")
    monkeypatch.setattr(shadow, "preflight_capacity", lambda **_: _preflight())
    monkeypatch.setattr(
        shadow.AllocationReleaseAdapter,
        "load",
        lambda _self, _root: release,
    )
    monkeypatch.setattr(
        shadow,
        "_release_evidence",
        lambda **_: _release_evidence_fixture(release),
    )
    monkeypatch.setattr(
        shadow.daily,
        "run",
        lambda **_: pytest.fail("missing input must stop before daily"),
    )

    result = shadow.run(
        database_path=database,
        output_root=tmp_path / "output",
        release_root=release.release_root,
        paper_state_db_path=tmp_path / "missing-paper.sqlite",
        now=datetime(2026, 7, 31, 10, 0, tzinfo=TAIPEI),
        calendar=_Calendar(
            {
                date(2026, 7, 31): (True, "open"),
                date(2026, 7, 30): (True, "open"),
            }
        ),
        lock_path=tmp_path / "shared.lock",
    )

    payload = cast(dict[str, Any], result)
    assert payload["status"] == "blocked_missing_input"
    assert "paper_state_db" in cast(list[str], payload["missing_inputs"])
    assert Path(str(payload["record_path"])).is_file()


def test_main_preserves_outer_block_when_inner_orchestration_completed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        shadow,
        "run",
        lambda **_: {
            "status": "blocked_capacity_post_run",
            "daily_orchestration": {
                "status": "passed_rule_only",
                "orchestration_status": "completed",
                "natural_forward_completion_clock": {
                    "within_forward_completion_window": True,
                },
            },
        },
    )

    assert shadow.main([]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocked_capacity_post_run"
    assert payload["daily_orchestration"]["orchestration_status"] == (
        "completed"
    )
