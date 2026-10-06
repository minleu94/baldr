"""週報私人覆盤與市場來源的隔離 consumer；只使用合成資料。"""
from dataclasses import replace
from pathlib import Path
import os
import subprocess
import sys

import pytest

from app_module.decision_quality_repository import DecisionQualityRepository
from app_module.decision_quality_service import DecisionQualityService
from app_module.evidence_operations_service import EvidenceOperationsService
from app_module.evidence_operations_history_repository import EvidenceOperationsHistoryRepository, EvidenceOperationsHistoryReadOnlyError
from app_module.personal_store_routes import PersonalStoreDomain, StoreIdentity
from app_module.personal_store_selection import resolve_personal_store_selection
from test_baldr_b10_private_review import config_at
from test_decision_quality_service import _seed_portfolio_alert, _seed_live_gap, _seed_signal_decay
from test_evidence_operations_service import _review, _item


def seeded_config(tmp_path):
    config = config_at(tmp_path)
    _seed_portfolio_alert(config)
    _seed_live_gap(config)
    _seed_signal_decay(config)
    # A market-stored historical review must not satisfy an empty private reader.
    DecisionQualityRepository(config).save_review(replace(_review(), review_id="market-only"))
    return config


def readiness(config, **kwargs):
    config.db_file = Path(kwargs["db_path"])
    return {"scheduler_readiness": "not_ready", "production_scheduler_allowed": False,
            "blocking_gaps": [], "warnings": []}


def test_empty_private_review_does_not_borrow_market_or_create_store(tmp_path):
    config = seeded_config(tmp_path)
    before = config.db_file.read_bytes()
    service = EvidenceOperationsService(config, readiness_evaluator=readiness)
    report = service.build_weekly_review(start_date="2026-06-01", end_date="2026-06-30")
    assert report.decision_quality.reviews_count == 0
    assert "selected_review_store_missing" in report.warnings
    assert report.signal_decay.observations_count == 1
    assert not report.write_performed
    assert service.plan_action_items(start_date="2026-06-01", end_date="2026-06-30").write_performed is False
    with pytest.raises(RuntimeError, match="selected_review_store_missing"):
        service.plan_action_items(start_date="2026-06-01", end_date="2026-06-30", confirm=True)
    assert not (config.personal_store_root / "reviews").exists()
    assert config.db_file.read_bytes() == before


def test_saved_private_reviews_and_market_decay_stay_separate(tmp_path):
    config = seeded_config(tmp_path)
    selection = resolve_personal_store_selection(config)
    route = selection.route(PersonalStoreDomain.REVIEW, StoreIdentity("decision-quality-reviews"))
    repository = DecisionQualityRepository(config, db_path=route.read_source, personal_paths=selection.paths)
    repository.save_review(_review(), items=[_item()])
    before_market = config.db_file.read_bytes()
    before_private = route.read_source.read_bytes()
    service = EvidenceOperationsService(config, readiness_evaluator=readiness)
    report = service.build_weekly_review(start_date="2026-06-01", end_date="2026-06-30")
    assert report.decision_quality.reviews_count == 1
    assert report.decision_quality.open_item_count == 1
    assert report.signal_decay.observations_count == 1
    assert not report.write_performed
    assert service.decision_quality_service.repository.read_only
    assert service.source_lineage["review_store_path"] == str(route.read_source)
    assert service.source_lineage["review_refs"] == [{"review_id": "dqr-weekly", "review_hash": "sha256:dqr-weekly"}]
    assert service.source_lineage["decay_refs"][0]["source_db"] == str(config.db_file)
    assert service.source_lineage["source_snapshot_qualification"] == "unknown"
    changed = service.source_lineage
    changed["review_refs"].clear()
    assert service.source_lineage["review_refs"]  # Detached lineage cannot retarget the saved report.
    assert all(repo.read_only for repo in (service.signal_decay_service.evidence_repository,
        service.signal_decay_service.gap_repository, service.signal_decay_service.decay_repository))
    assert config.db_file.read_bytes() == before_market
    assert route.read_source.read_bytes() == before_private


def test_selected_readiness_evaluator_cannot_retarget_shared_config(tmp_path):
    config = seeded_config(tmp_path)
    expected = config.db_file
    def changing_readiness(clone, **kwargs):
        clone.db_file = tmp_path / "unrelated.sqlite"
        return readiness(clone, **kwargs)
    service = EvidenceOperationsService(config, readiness_evaluator=changing_readiness)
    service.build_weekly_review(start_date="2026-06-01", end_date="2026-06-30")
    assert config.db_file == expected


def test_wrong_review_source_injection_rejected(tmp_path):
    config = seeded_config(tmp_path)
    wrong = DecisionQualityService(config, source_db_path=tmp_path / "wrong.sqlite", read_only=True)
    with pytest.raises(ValueError, match="review_source_route_mismatch"):
        EvidenceOperationsService(config, decision_quality_service=wrong)


def test_default_readiness_and_weekly_report_do_not_write_market(tmp_path):
    config = seeded_config(tmp_path)
    before = config.db_file.read_bytes()
    expected = config.db_file
    report = EvidenceOperationsService(config).build_weekly_review(
        start_date="2026-06-01", end_date="2026-06-30")
    assert not report.write_performed
    assert config.db_file == expected and config.db_file.read_bytes() == before


def test_absent_market_decay_is_unknown_without_creating_db(tmp_path):
    config = config_at(tmp_path)
    service = EvidenceOperationsService(config, readiness_evaluator=readiness)
    report = service.build_weekly_review(start_date="2026-06-01", end_date="2026-06-30")
    assert report.signal_decay.status_counts == {"unknown": 1}
    assert "market_decay_source_missing" in report.warnings
    assert "selected_review_store_missing" in report.warnings
    assert not config.db_file.exists() and not (config.personal_store_root / "reviews").exists()


def test_private_weekly_history_roundtrip_does_not_supply_missing_review_table(tmp_path):
    config = seeded_config(tmp_path)
    before = config.db_file.read_bytes()
    service = EvidenceOperationsService(config, readiness_evaluator=readiness)
    report = service.build_weekly_review(start_date="2026-06-01", end_date="2026-06-30")
    repository = EvidenceOperationsHistoryRepository(config)
    record = repository.save_weekly_review(report, payload_json={**report.to_dict(), "source_lineage": service.source_lineage})
    assert repository.db_path == config.personal_store_root / "reviews" / "decision_quality.sqlite"
    again = service.build_weekly_review(start_date="2026-06-01", end_date="2026-06-30")
    assert again.decision_quality.reviews_count == 0 and "selected_review_store_missing" in again.warnings
    private_before = repository.db_path.read_bytes()
    readonly = EvidenceOperationsHistoryRepository(config, read_only=True)
    assert readonly.get_weekly_review(record.review_id) == record
    with readonly._connect() as connection:
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
    code = """
import sys
from pathlib import Path
from data_module.config import TWStockConfig
from app_module.evidence_operations_history_repository import EvidenceOperationsHistoryRepository
p = Path(sys.argv[1])
c = TWStockConfig(data_root=p/'data', output_root=p/'output', personal_store_root=p/'data/personal', personal_store_mode='personal')
r = EvidenceOperationsHistoryRepository(c, read_only=True).get_weekly_review(sys.argv[2])
assert r.review_hash == sys.argv[3]
assert r.payload_json['source_lineage']['source_snapshot_qualification'] == 'unknown'
assert r.payload_json['source_lineage']['review_refs'] == []
"""
    result = subprocess.run([sys.executable, "-B", "-c", code, str(tmp_path), record.review_id, record.review_hash],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert config.db_file.read_bytes() == before and repository.db_path.read_bytes() == private_before


def test_private_history_empty_and_conflicting_db_fail_without_fallback(tmp_path):
    config = seeded_config(tmp_path)
    before = config.db_file.read_bytes()
    repository = EvidenceOperationsHistoryRepository(config, read_only=True)
    with pytest.raises(EvidenceOperationsHistoryReadOnlyError, match="db_missing"):
        repository.list_weekly_reviews()
    with pytest.raises(ValueError, match="db_path_conflict"):
        EvidenceOperationsHistoryRepository(config, db_path=config.db_file)
    assert not (config.personal_store_root / "reviews").exists()
    assert config.db_file.read_bytes() == before


def test_private_history_revalidates_sidecar_after_construction(tmp_path):
    config = seeded_config(tmp_path)
    repository = EvidenceOperationsHistoryRepository(config)
    sentinel = tmp_path / "sentinel.bin"
    sentinel.write_bytes(b"synthetic untouched sentinel")
    sidecar = Path(str(repository.db_path) + "-wal")
    os.link(sentinel, sidecar)
    with pytest.raises(ValueError):
        repository.list_weekly_reviews()
    assert sentinel.read_bytes() == b"synthetic untouched sentinel"
