from __future__ import annotations

from datetime import timedelta
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from types import SimpleNamespace

import pytest

from app_module.portfolio_research_registry import (
    MAX_REFERENCE_BYTES,
    PortfolioScenarioRegistryService,
    ScenarioRegistrySelection,
    decode_reference,
    encode_reference,
)
from app_module.portfolio_research_scenario_repository import PortfolioResearchScenarioRepository
from app_module.personal_store_routes import PersonalStoreMode
from app_module.research_run_repository import (
    ResearchRunConflictError,
    ResearchRunRepository,
    ResearchRunRepositoryError,
)
from app_module.sqlite_read_only import ReadOperationCancelled
from tests.test_portfolio_research_scenario_repository import SAVED, _comparison, _route


def _research_run_repository(path: Path) -> ResearchRunRepository:
    repository = ResearchRunRepository(SimpleNamespace(research_run_db_file=path))
    repository.ensure_schema()
    return repository


def _source_payload(source: PortfolioResearchScenarioRepository, artifact_id: str) -> bytes:
    with sqlite3.connect(source.db_path) as conn:
        row = conn.execute(
            "SELECT payload_json FROM scenario_archives WHERE artifact_id=?", (artifact_id,)
        ).fetchone()
    assert row is not None
    return row[0]


def _reference_hash(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


@pytest.fixture
def registry_case(tmp_path):
    from app_module.personal_data_paths import PersonalDataPaths

    paths = PersonalDataPaths(
        market_root=tmp_path / "market",
        legacy_output_root=tmp_path / "legacy",
        personal_root=tmp_path / "market" / "personal",
    )
    source = PortfolioResearchScenarioRepository(route=_route(paths), personal_paths=paths)
    saved = source.append(_comparison(), saved_at=SAVED)
    registry = _research_run_repository(tmp_path / "registry.sqlite")
    service = PortfolioScenarioRegistryService(registry, source)
    return paths, source, saved, registry, service


def test_saved_scenario_is_registered_as_exact_reference_without_backtest_metadata(registry_case):
    _, source, saved, registry, service = registry_case
    original_payload = _source_payload(source, saved.artifact_id)

    entry = service.register_saved(saved.artifact_id, account_kind="paper", portfolio_id="account-a")

    assert entry.record_id == "portfolio-scenario:" + saved.artifact_id.removeprefix("sha256:")
    assert entry.account_kind == "paper"
    assert entry.portfolio_id == "account-a"
    assert entry.artifact_id == saved.artifact_id
    assert entry.snapshot_id == saved.comparison.account.snapshot_id
    assert entry.decision_at == saved.comparison.decision_at
    assert entry.source_saved_at == saved.saved_at
    assert entry.registered_at >= entry.source_saved_at
    assert entry.input_hash == saved.comparison.input_hash
    assert entry.reference_sha256.startswith("sha256:")

    assert registry.get_portfolio_scenario_reference(entry.record_id) == entry
    assert registry.list_portfolio_scenario_references(
        account_kind="paper", portfolio_id="account-a"
    ) == (entry,)
    with sqlite3.connect(registry.db_path) as conn:
        assert conn.execute(
            "SELECT version FROM schema_version WHERE name='research_runs'"
        ).fetchone() == (2,)
        assert conn.execute(
            "SELECT version FROM schema_version WHERE name='portfolio_scenario_registry'"
        ).fetchone() == (1,)
        assert conn.execute("SELECT COUNT(*) FROM research_runs").fetchone() == (0,)
        assert conn.execute("SELECT COUNT(*) FROM portfolio_scenario_registry").fetchone() == (1,)
    assert _source_payload(source, saved.artifact_id) == original_payload


def test_reference_codec_is_canonical_and_rejects_duplicate_or_unknown_fields(registry_case):
    _, _, saved, _, service = registry_case
    entry = service.register_saved(saved.artifact_id, account_kind="paper", portfolio_id="account-a")

    payload = encode_reference(entry)
    assert len(payload) <= MAX_REFERENCE_BYTES
    assert decode_reference(payload, entry.reference_sha256) == entry
    with pytest.raises(ValueError, match="hash"):
        decode_reference(payload, "sha256:" + "f" * 64)

    duplicate_key = payload[:-1] + b',"record_id":"' + entry.record_id.encode("utf-8") + b'"}'
    with pytest.raises(ValueError, match="canonical"):
        decode_reference(duplicate_key, _reference_hash(duplicate_key))

    unknown_field = payload[:-1] + b',"unrecognized":1}'
    with pytest.raises(ValueError, match="schema"):
        decode_reference(unknown_field, _reference_hash(unknown_field))


def test_registration_is_idempotent_and_exact_open_does_not_recompute_or_append(registry_case, monkeypatch):
    _, source, saved, registry, service = registry_case
    original_payload = _source_payload(source, saved.artifact_id)
    first = service.register_saved(saved.artifact_id, account_kind="paper", portfolio_id="account-a")
    first_reference_bytes = encode_reference(first)

    second = service.register_saved(saved.artifact_id, account_kind="paper", portfolio_id="account-a")
    assert second == first
    assert second.registered_at == first.registered_at

    def unexpected_append(*args, **kwargs):
        pytest.fail("精確重開不得重算或另存情境")

    monkeypatch.setattr(source, "append", unexpected_append)
    fresh_service = PortfolioScenarioRegistryService(registry, source)
    opened = fresh_service.open_registered(first.selection())
    assert opened == saved
    assert encode_reference(registry.get_portfolio_scenario_reference(first.record_id)) == first_reference_bytes
    assert _source_payload(source, saved.artifact_id) == original_payload
    with sqlite3.connect(registry.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM research_runs").fetchone() == (0,)
        assert conn.execute("SELECT COUNT(*) FROM portfolio_scenario_registry").fetchone() == (1,)


def test_cross_account_and_stale_selection_are_rejected(registry_case):
    _, _, saved, _, service = registry_case
    entry = service.register_saved(saved.artifact_id, account_kind="paper", portfolio_id="account-a")

    with pytest.raises(ValueError, match="account"):
        service.register_saved(saved.artifact_id, account_kind="paper", portfolio_id="account-b")
    wrong_account = ScenarioRegistrySelection(
        entry.record_id, entry.reference_sha256, "paper", "account-b", entry.artifact_id
    )
    with pytest.raises(ValueError, match="stale or missing"):
        service.open_registered(wrong_account)
    stale_hash = ScenarioRegistrySelection(
        entry.record_id, "sha256:" + "f" * 64, entry.account_kind, entry.portfolio_id, entry.artifact_id
    )
    with pytest.raises(ValueError, match="stale or missing"):
        service.open_registered(stale_hash)


def test_registry_rejects_payload_hash_and_index_tampering(registry_case):
    _, _, saved, registry, service = registry_case
    entry = service.register_saved(saved.artifact_id, account_kind="paper", portfolio_id="account-a")
    with sqlite3.connect(registry.db_path) as conn:
        payload = conn.execute(
            "SELECT payload_json FROM portfolio_scenario_registry WHERE record_id=?", (entry.record_id,)
        ).fetchone()[0]
        conn.execute(
            "UPDATE portfolio_scenario_registry SET payload_json=? WHERE record_id=?",
            (b"[" + payload[1:], entry.record_id),
        )
    with pytest.raises((ValueError, ResearchRunRepositoryError)):
        registry.get_portfolio_scenario_reference(entry.record_id)

    # 以另一筆乾淨原件確認索引欄位與 payload 的交叉綁定。
    other_source = service.source
    second_saved = other_source.append(_comparison(account_id="account-b"), saved_at=SAVED)
    second = service.register_saved(second_saved.artifact_id, account_kind="paper", portfolio_id="account-b")
    with sqlite3.connect(registry.db_path) as conn:
        conn.execute(
            "UPDATE portfolio_scenario_registry SET portfolio_id='account-c' WHERE record_id=?",
            (second.record_id,),
        )
    with pytest.raises((ValueError, ResearchRunRepositoryError)):
        registry.get_portfolio_scenario_reference(second.record_id)


@pytest.mark.parametrize("field, value", [
    ("input_hash", "sha256:" + "f" * 64),
    ("source_saved_at", (SAVED + timedelta(minutes=2)).isoformat()),
])
def test_rehashed_reference_cannot_rebind_source_facts(registry_case, field, value):
    _, _, saved, registry, service = registry_case
    entry = service.register_saved(saved.artifact_id, account_kind="paper", portfolio_id="account-a")
    with sqlite3.connect(registry.db_path) as conn:
        payload = conn.execute(
            "SELECT payload_json FROM portfolio_scenario_registry WHERE record_id=?", (entry.record_id,)
        ).fetchone()[0]
        decoded = json.loads(payload)
        decoded[field] = value
        changed_payload = json.dumps(
            decoded, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        changed_hash = _reference_hash(changed_payload)
        conn.execute(
            "UPDATE portfolio_scenario_registry SET reference_sha256=?,payload_json=? WHERE record_id=?",
            (changed_hash, changed_payload, entry.record_id),
        )

    changed_entry = decode_reference(changed_payload, changed_hash)
    with pytest.raises(ValueError, match="differs from reference"):
        service.open_registered(changed_entry.selection())
    with pytest.raises((ValueError, ResearchRunConflictError)):
        service.register_saved(saved.artifact_id, account_kind="paper", portfolio_id="account-a")


def test_missing_source_artifact_and_read_only_source_fail_closed(registry_case):
    paths, source, saved, registry, service = registry_case
    entry = service.register_saved(saved.artifact_id, account_kind="paper", portfolio_id="account-a")
    with sqlite3.connect(source.db_path) as conn:
        conn.execute("DELETE FROM scenario_archives WHERE artifact_id=?", (saved.artifact_id,))
    with pytest.raises(ValueError, match="missing or differs"):
        service.open_registered(entry.selection())

    # 以真正的 legacy read-only 路由重開一份同一原件副本，只允許列出與精確讀回。
    personal_source = source.append(_comparison(), saved_at=SAVED)
    legacy_route = _route(paths, PersonalStoreMode.LEGACY_READ_ONLY)
    legacy_route.read_source.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source.db_path, legacy_route.read_source)
    readonly_source = PortfolioResearchScenarioRepository(route=legacy_route, personal_paths=paths)
    readonly_service = PortfolioScenarioRegistryService(registry, readonly_source)
    assert readonly_service.can_register is False
    assert readonly_service.list_registered(account_kind="paper", portfolio_id="account-a") == (entry,)
    with pytest.raises(ValueError, match="唯讀"):
        readonly_service.register_saved(
            personal_source.artifact_id, account_kind="paper", portfolio_id="account-a"
        )
    assert readonly_service.open_registered(entry.selection()).artifact_id == personal_source.artifact_id


def test_read_only_calls_do_not_create_database_or_registry_table(tmp_path):
    from app_module.personal_data_paths import PersonalDataPaths

    paths = PersonalDataPaths(
        market_root=tmp_path / "market",
        legacy_output_root=tmp_path / "legacy",
        personal_root=tmp_path / "market" / "personal",
    )
    source = PortfolioResearchScenarioRepository(route=_route(paths), personal_paths=paths)
    registry = ResearchRunRepository(SimpleNamespace(research_run_db_file=tmp_path / "not-created.sqlite"))
    service = PortfolioScenarioRegistryService(registry, source)

    assert registry.get_portfolio_scenario_reference("portfolio-scenario:" + "a" * 64) is None
    assert service.list_registered(account_kind="paper", portfolio_id="account-a") == ()
    selection = ScenarioRegistrySelection(
        "portfolio-scenario:" + "a" * 64,
        "sha256:" + "b" * 64,
        "paper",
        "account-a",
        "sha256:" + "a" * 64,
    )
    with pytest.raises(ValueError, match="missing"):
        service.open_registered(selection)
    with pytest.raises(ValueError, match="missing"):
        service.register_saved("sha256:" + "a" * 64, account_kind="paper", portfolio_id="account-a")
    assert not registry.db_path.exists()


@pytest.mark.parametrize("version", [1, 3])
def test_unknown_or_legacy_research_registry_version_is_not_migrated(tmp_path, registry_case, version):
    registry = _research_run_repository(tmp_path / f"registry-v{version}.sqlite")
    with sqlite3.connect(registry.db_path) as conn:
        conn.execute("UPDATE schema_version SET version=? WHERE name='research_runs'", (version,))
    before = registry.db_path.read_bytes()

    with pytest.raises(ResearchRunRepositoryError):
        registry.list_portfolio_scenario_references(account_kind="paper", portfolio_id="account-a")
    with pytest.raises(ResearchRunRepositoryError):
        registry.append_portfolio_scenario_reference(
            registry_case[4].register_saved(
                registry_case[2].artifact_id, account_kind="paper", portfolio_id="account-a"
            )
        )
    assert registry.db_path.read_bytes() == before
    with sqlite3.connect(registry.db_path) as conn:
        assert conn.execute(
            "SELECT version FROM schema_version WHERE name='portfolio_scenario_registry'"
        ).fetchone() is None


def test_cancellation_before_read_or_write_leaves_no_partial_reference(registry_case):
    _, source, saved, registry, service = registry_case
    original_payload = _source_payload(source, saved.artifact_id)

    with pytest.raises(ReadOperationCancelled):
        service.register_saved(
            saved.artifact_id, account_kind="paper", portfolio_id="account-a", cancel_callback=lambda: True
        )
    with pytest.raises(ReadOperationCancelled):
        service.list_registered(account_kind="paper", portfolio_id="account-a", cancel_callback=lambda: True)
    with sqlite3.connect(registry.db_path) as conn:
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='portfolio_scenario_registry'"
        ).fetchone() is None
        assert conn.execute("SELECT COUNT(*) FROM research_runs").fetchone() == (0,)
    assert _source_payload(source, saved.artifact_id) == original_payload


def test_reference_list_limits_reject_bool_and_oversize_is_checked_before_decode(registry_case, monkeypatch):
    _, _, saved, registry, service = registry_case
    entry = service.register_saved(saved.artifact_id, account_kind="paper", portfolio_id="account-a")
    for invalid in (True, False, 0, 201):
        with pytest.raises(ValueError, match="limit"):
            registry.list_portfolio_scenario_references(
                account_kind="paper", portfolio_id="account-a", limit=invalid
            )
    assert registry.list_portfolio_scenario_references(
        account_kind="paper", portfolio_id="account-a", limit=200
    ) == (entry,)

    with sqlite3.connect(registry.db_path) as conn:
        conn.execute(
            "UPDATE portfolio_scenario_registry SET payload_json=zeroblob(?) WHERE record_id=?",
            (MAX_REFERENCE_BYTES + 1, entry.record_id),
        )

    import app_module.portfolio_research_registry as codec_module

    def decoder_must_not_receive_oversize(*args, **kwargs):
        pytest.fail("oversized registry blob reached the JSON decoder")

    monkeypatch.setattr(codec_module, "decode_reference", decoder_must_not_receive_oversize)
    with pytest.raises(ResearchRunRepositoryError, match="size/type"):
        registry.get_portfolio_scenario_reference(entry.record_id)
