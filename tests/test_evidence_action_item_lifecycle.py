from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import app_module.evidence_action_item_lifecycle as lifecycle_module
from app_module.decision_quality_dtos import DecisionQualityItem, DecisionQualityReview
from app_module.decision_quality_repository import DecisionQualityRepository
from app_module.evidence_action_item_lifecycle import (
    EvidenceActionItemLifecycleError,
    EvidenceActionItemLifecycleService,
)
from data_module.config import TWStockConfig


def _config(tmp_path: Path) -> TWStockConfig:
    config = TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output")
    config.db_file = tmp_path / "weekly-working-copy.db"
    config.use_sqlite = True
    return config


def _seed_working_copy(config: TWStockConfig) -> str:
    repository = DecisionQualityRepository(config)
    review = DecisionQualityReview(
        review_id="review-2026-10-19",
        review_hash="sha256:" + "a" * 64,
        review_period_start="2026-10-19",
        review_period_end="2026-10-25",
        review_type="weekly",
        review_status="incomplete",
        quality="degraded",
    )
    repository.save_review(
        review,
        items=[
            DecisionQualityItem(
                item_id="item-1",
                review_id=review.review_id,
                item_type="missing_source_trace",
                status="open",
            )
        ],
    )
    action = repository.create_action_item(
        review_id=review.review_id,
        item_id="item-1",
        description="核對本週缺少的來源證據",
        owner="Owner",
    )
    return action.action_item_id


def _service(tmp_path: Path, config: TWStockConfig, projection: str = "action-lifecycle.json"):
    return EvidenceActionItemLifecycleService(
        config,
        db_path=config.db_file,
        projection_path=tmp_path / projection,
    )


def _record(service: EvidenceActionItemLifecycleService, action_id: str, status: str):
    return service.record_transition(
        action_id,
        new_status=status,
        actor_name="owner-name",
        actor_role="owner",
        note=f"人工確認為 {status}",
        recorded_at="2026-10-26T20:00:00Z",
    )


def test_action_item_lifecycle_appends_chain_without_mutating_source_db(tmp_path: Path) -> None:
    config = _config(tmp_path)
    action_id = _seed_working_copy(config)
    source_before = config.db_file.read_bytes()
    service = _service(tmp_path, config)

    assert service.list_action_items()[0]["lifecycle_status"] == "open"
    reviewed = _record(service, action_id, "reviewed")
    follow_up = _record(service, action_id, "follow_up")
    dismissed = _record(service, action_id, "dismissed")

    rows = service.list_action_items()
    assert rows[0]["lifecycle_status"] == "dismissed"
    assert rows[0]["latest_event"]["event_sha256"] == dismissed["event_sha256"]
    assert [reviewed["to_status"], follow_up["to_status"], dismissed["to_status"]] == [
        "reviewed",
        "follow_up",
        "dismissed",
    ]
    payload = json.loads((tmp_path / "action-lifecycle.json").read_text(encoding="utf-8"))
    assert len(payload["events"]) == 3
    assert all(event["formal_credit_authorized"] is False for event in payload["events"])
    assert all(event["production_scheduler_allowed"] is False for event in payload["events"])
    assert config.db_file.read_bytes() == source_before


def test_duplicate_or_skipped_lifecycle_transition_is_rejected(tmp_path: Path) -> None:
    config = _config(tmp_path)
    action_id = _seed_working_copy(config)
    service = _service(tmp_path, config)
    _record(service, action_id, "reviewed")

    with pytest.raises(EvidenceActionItemLifecycleError, match="invalid action-item transition"):
        _record(service, action_id, "reviewed")
    with pytest.raises(EvidenceActionItemLifecycleError, match="exactly one source row"):
        _record(service, "missing-action", "dismissed")


def test_changed_source_action_payload_is_rejected_after_first_event(tmp_path: Path) -> None:
    config = _config(tmp_path)
    action_id = _seed_working_copy(config)
    service = _service(tmp_path, config)
    _record(service, action_id, "reviewed")

    connection = sqlite3.connect(config.db_file)
    connection.execute(
        "UPDATE decision_quality_action_items SET description = ? WHERE action_item_id = ?",
        ("source row changed", action_id),
    )
    connection.commit()
    connection.close()

    with pytest.raises(EvidenceActionItemLifecycleError, match="source row changed"):
        service.list_action_items()


def test_source_action_item_cannot_disappear_after_review(tmp_path: Path) -> None:
    config = _config(tmp_path)
    action_id = _seed_working_copy(config)
    service = _service(tmp_path, config)
    _record(service, action_id, "reviewed")
    connection = sqlite3.connect(config.db_file)
    connection.execute(
        "DELETE FROM decision_quality_action_items WHERE action_item_id = ?",
        (action_id,),
    )
    connection.commit()
    connection.close()

    with pytest.raises(EvidenceActionItemLifecycleError, match="missing a previously reviewed action item"):
        service.list_action_items()


def test_projection_rejects_tampered_chain_and_different_working_copy(tmp_path: Path) -> None:
    config = _config(tmp_path)
    action_id = _seed_working_copy(config)
    service = _service(tmp_path, config)
    _record(service, action_id, "reviewed")
    projection = tmp_path / "action-lifecycle.json"
    payload = json.loads(projection.read_text(encoding="utf-8"))
    payload["events"][0]["note"] = "tampered"
    projection.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EvidenceActionItemLifecycleError, match="event hash is invalid"):
        service.list_action_items()

    other_source = tmp_path / "other-working-copy.db"
    other_source.write_bytes(config.db_file.read_bytes())
    other = EvidenceActionItemLifecycleService(
        config,
        db_path=other_source,
        projection_path=projection,
    )
    with pytest.raises(EvidenceActionItemLifecycleError, match="another working copy"):
        other.list_action_items()


def test_missing_source_schema_is_read_only_and_not_created(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.db_file.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(config.db_file)
    connection.execute("CREATE TABLE unrelated (id INTEGER)")
    connection.commit()
    connection.close()
    before = config.db_file.read_bytes()
    service = _service(tmp_path, config)

    with pytest.raises(EvidenceActionItemLifecycleError, match="tables are missing"):
        service.list_action_items()
    assert config.db_file.read_bytes() == before
    connection = sqlite3.connect(config.db_file)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    connection.close()
    assert tables == {"unrelated"}


def test_concurrent_sqlite_sidecar_change_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config(tmp_path)
    _seed_working_copy(config)
    service = _service(tmp_path, config)
    original_stamps = lifecycle_module._sqlite_sidecar_stamps
    calls = 0

    def changing_sidecar_stamps(path: Path):
        nonlocal calls
        calls += 1
        if calls == 1:
            return original_stamps(path)
        return {"-wal": (1, 2, 1, 3, 4), "-journal": None}

    monkeypatch.setattr(lifecycle_module, "_sqlite_sidecar_stamps", changing_sidecar_stamps)
    with pytest.raises(EvidenceActionItemLifecycleError, match="changed while reading"):
        service.list_action_items()


def test_formal_database_and_projection_collision_are_rejected(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _seed_working_copy(config)
    formal_root = tmp_path / "formal"
    formal_path = formal_root / "sqlite" / "twstock.db"
    formal_path.parent.mkdir(parents=True)
    formal_path.write_bytes(b"do not open")
    config.data_root = formal_root
    with pytest.raises(ValueError, match="weekly_review_formal_db_forbidden"):
        EvidenceActionItemLifecycleService(
            config,
            db_path=formal_path,
            projection_path=tmp_path / "action-lifecycle.json",
        )
    with pytest.raises(EvidenceActionItemLifecycleError, match="separate from source DB"):
        EvidenceActionItemLifecycleService(
            config,
            db_path=config.db_file,
            projection_path=config.db_file,
        )
    with pytest.raises(EvidenceActionItemLifecycleError, match="formal data root"):
        EvidenceActionItemLifecycleService(
            config,
            db_path=config.db_file,
            projection_path=formal_root / "sqlite" / "action-lifecycle.json",
        )


def test_empty_required_fields_and_naive_timestamps_fail_closed(tmp_path: Path) -> None:
    config = _config(tmp_path)
    action_id = _seed_working_copy(config)
    service = _service(tmp_path, config)

    with pytest.raises(EvidenceActionItemLifecycleError, match="actor_name is required"):
        service.record_transition(
            action_id,
            new_status="reviewed",
            actor_name="",
            actor_role="owner",
            note="有紀錄",
        )
    with pytest.raises(EvidenceActionItemLifecycleError, match="include a timezone"):
        service.record_transition(
            action_id,
            new_status="reviewed",
            actor_name="owner-name",
            actor_role="owner",
            note="有紀錄",
            recorded_at="2026-10-26T20:00:00",
        )
