"""隔離來源／私人 writer 與新程序讀回；不改評分或財務公式。"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from app_module.decision_quality_service import DecisionQualityService
from app_module.journal_service import JournalService
from app_module.personal_data_paths import PersonalDataPathError
from app_module.personal_journal_paths import resolve_journal_storage_selection
from app_module.personal_store_selection import resolve_personal_store_selection
from app_module.personal_store_routes import PersonalStoreDomain, PersonalStoreMode, PersonalStoreRouteError, StoreIdentity
from data_module.config import TWStockConfig
from test_decision_quality_service import _seed_portfolio_alert, _seed_live_gap, _seed_signal_decay


class EmptyPortfolio:
    def __init__(self, config):
        self.store = SimpleNamespace(route=resolve_personal_store_selection(config).route(
            PersonalStoreDomain.TRADES, StoreIdentity("default")))

    def list_trades(self, portfolio_id):
        return []

    def list_positions(self, portfolio_id):
        return []


def config_at(tmp_path, *, personal=True):
    kwargs = dict(data_root=tmp_path / "data", output_root=tmp_path / "output")
    if personal:
        kwargs.update(personal_store_root=tmp_path / "data" / "personal", personal_store_mode="personal",
                      personal_journal_root=tmp_path / "data" / "personal", personal_journal_mode="personal")
    return TWStockConfig(**kwargs)


def test_personal_review_reads_market_refs_but_only_writes_private(tmp_path):
    config = config_at(tmp_path)
    _seed_portfolio_alert(config)
    _seed_live_gap(config)
    _seed_signal_decay(config)
    before = config.db_file.read_bytes()
    service = DecisionQualityService(config, portfolio_service=EmptyPortfolio(config))
    assert service.db_path == config.personal_store_root / "reviews" / "decision_quality.sqlite"
    assert service.source_db_path == config.db_file
    assert all(repo.read_only for repo in (service.evidence_repository, service.live_gap_repository, service.signal_decay_repository))
    review, items = service.build_review(review_type="weekly", start_date="2026-06-01", end_date="2026-06-30")
    assert review.evidence_event_count == 1
    assert review.metadata_json["evidence_source_refs"] == [{"source_db": str(config.db_file), "event_id": "evt-alert", "event_hash": "hash:evt-alert"}]
    assert review.metadata_json["gap_source_refs"] and review.metadata_json["decay_source_refs"]
    assert service.save_review(review, items=items, confirm=True).saved
    assert config.db_file.read_bytes() == before
    assert service.get_review(review.review_id).metadata_json == review.metadata_json
    script = """
import sys
from pathlib import Path
from data_module.config import TWStockConfig
from app_module.decision_quality_service import DecisionQualityService
base = Path(sys.argv[1])
c = TWStockConfig(data_root=base/'data', output_root=base/'output', personal_store_root=base/'data/personal', personal_store_mode='personal', personal_journal_root=base/'data/personal', personal_journal_mode='personal')
s = DecisionQualityService(c, read_only=True)
r = s.get_review(sys.argv[2])
assert r is not None and r.metadata_json['evidence_source_refs'][0]['event_id']=='evt-alert'
assert r.metadata_json['market_source_db'] == str(c.db_file)
assert s.repository.read_only and s.evidence_repository.read_only
"""
    result = subprocess.run([sys.executable, "-X", "utf8", "-B", "-c", script, str(tmp_path), review.review_id],
                            capture_output=True, text=True, timeout=30,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    assert result.returncode == 0, result.stdout + result.stderr
    assert config.db_file.read_bytes() == before


def test_quality_uses_existing_explicit_notes_selector(tmp_path):
    config = config_at(tmp_path, personal=False)
    config.personal_journal_root = config.data_root / "personal"
    config.personal_journal_mode = "personal"
    selection = resolve_journal_storage_selection(config)
    notes = JournalService(config, journal_paths=selection.paths)
    notes.add_journal_entry(stock_code="2330", body="synthetic")
    service = DecisionQualityService(config)
    assert service.journal_service.store.journal_file == notes.store.journal_file
    assert len(service.journal_service.list_journal_entries()) == 1


def test_missing_personal_portfolio_fails_before_private_db_created(tmp_path):
    config = config_at(tmp_path)
    with pytest.raises(ValueError, match="personal_portfolio_selection_required"):
        DecisionQualityService(config)
    assert not (config.personal_store_root / "reviews").exists()


def test_missing_personal_notes_does_not_borrow_legacy(tmp_path):
    config = config_at(tmp_path)
    config.personal_journal_root = None
    config.personal_journal_mode = None
    with pytest.raises(ValueError, match="personal_journal_selection_required"):
        DecisionQualityService(config, portfolio_service=EmptyPortfolio(config))
    assert not (config.personal_store_root / "reviews").exists()


def test_private_store_cannot_be_market_source(tmp_path):
    config = config_at(tmp_path)
    route = resolve_personal_store_selection(config).route(PersonalStoreDomain.REVIEW, StoreIdentity("reviews"))
    with pytest.raises(ValueError, match="source_writer_overlap"):
        DecisionQualityService(config, review_route=route, source_db_path=route.read_source, portfolio_service=EmptyPortfolio(config))
    assert not route.read_source.exists()


def test_hardlinked_private_db_rejected_on_next_operation(tmp_path):
    config = config_at(tmp_path)
    service = DecisionQualityService(config, portfolio_service=EmptyPortfolio(config))
    os.link(service.db_path, tmp_path / "alias.sqlite")
    with pytest.raises(PersonalDataPathError, match="alias_or_type"):
        service.list_reviews()


def test_hardlinked_private_sqlite_sidecar_rejected_before_connection(tmp_path):
    config = config_at(tmp_path)
    service = DecisionQualityService(config, portfolio_service=EmptyPortfolio(config))
    source = tmp_path / "unrelated.bin"
    source.write_bytes(b"synthetic sidecar alias")
    os.link(source, Path(str(service.db_path) + "-wal"))
    with pytest.raises(PersonalDataPathError, match="alias_or_type"):
        service.list_reviews()
    assert source.read_bytes() == b"synthetic sidecar alias"


@pytest.mark.parametrize("root,mode", [(None,"personal"),("selected",None),("selected","invented")])
def test_store_selection_rejects_partial_or_unknown_mode(tmp_path, root, mode):
    config = SimpleNamespace(data_root=tmp_path / "data", output_root=tmp_path / "output",
                             personal_store_root=tmp_path / root if root else None, personal_store_mode=mode)
    with pytest.raises(PersonalStoreRouteError):
        resolve_personal_store_selection(config)
    assert not (tmp_path / "selected").exists()


def test_unconfigured_selector_preserves_legacy_path_without_io(tmp_path):
    config = SimpleNamespace(data_root=tmp_path / "data", output_root=tmp_path / "output")
    selection = resolve_personal_store_selection(config)
    assert selection.mode is PersonalStoreMode.LEGACY_COMPAT
    assert selection.route(PersonalStoreDomain.TRADES, StoreIdentity("known-account")).read_source == config.output_root / "portfolio/trades.jsonl"
    assert not config.output_root.exists()


def test_private_review_rejects_unbound_or_wrong_account_before_read(tmp_path):
    config = config_at(tmp_path)
    with pytest.raises(ValueError, match="portfolio_route_mismatch"):
        DecisionQualityService(config, portfolio_service=SimpleNamespace())
    assert not (config.personal_store_root / "reviews").exists()
    service = DecisionQualityService(config, portfolio_service=EmptyPortfolio(config))
    with pytest.raises(ValueError, match="portfolio_identity_mismatch"):
        service.build_review(review_type="weekly", start_date="2026-06-01", end_date="2026-06-30", portfolio_id="other")


def test_private_review_does_not_mix_notes_roots(tmp_path):
    config = config_at(tmp_path)
    config.personal_journal_root = tmp_path / "other-personal"
    with pytest.raises(ValueError, match="journal_root_mismatch"):
        DecisionQualityService(config, portfolio_service=EmptyPortfolio(config))
    assert not (config.personal_store_root / "reviews").exists()


def test_equal_counts_with_different_saved_sources_have_different_hash(tmp_path):
    from dataclasses import replace
    from app_module.evidence_event_repository import EvidenceEventRepository
    from test_decision_quality_service import _event
    config = config_at(tmp_path)
    _seed_portfolio_alert(config)
    _seed_live_gap(config)
    _seed_signal_decay(config)
    service = DecisionQualityService(config, portfolio_service=EmptyPortfolio(config))
    kwargs = dict(review_type="weekly", start_date="2026-06-01", end_date="2026-06-30")
    first, _ = service.build_review(**kwargs)
    source = replace(_event("other-alert", symbol="2330", event_type="portfolio_alert_condition_invalid"), event_hash="hash:different")
    # Isolate an independently saved source with the same counts and warnings.
    other_db = tmp_path / "other-market.sqlite"
    repository = EvidenceEventRepository(config, db_path=other_db)
    repository.insert_event(source)
    other_config = config_at(tmp_path / "other")
    other_config.db_file = other_db
    _seed_live_gap(other_config)
    _seed_signal_decay(other_config)
    other_service = DecisionQualityService(config, source_db_path=other_db, portfolio_service=EmptyPortfolio(config))
    second, _ = other_service.build_review(**kwargs)
    assert first.evidence_event_count == second.evidence_event_count == 1
    assert first.warnings_json == second.warnings_json
    assert first.review_hash != second.review_hash
    assert first.review_id == second.review_id  # Existing period identity remains unchanged.
    assert second.metadata_json["evidence_source_refs"][0]["source_db"] == str(other_db)
