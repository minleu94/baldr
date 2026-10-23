from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app_module.scheduled_forward_outcome_service import run_scheduled_forward_outcomes
from scripts.scheduled.run_scheduled_forward_outcomes import main


def test_partial_qualification_configuration_fails_before_source_or_db_work(tmp_path: Path):
    data_root = tmp_path / "data"
    output_root = tmp_path / "output"
    data_root.mkdir()
    output_root.mkdir()
    db_path = data_root / "evidence.sqlite"
    config = SimpleNamespace(
        data_root=data_root,
        db_file=db_path,
        output_root=output_root,
    )

    result = run_scheduled_forward_outcomes(
        config=config,
        db_path=db_path,
        output_root=output_root,
        now=datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc),
        daily_price_qualification_binding_path=tmp_path / "binding.json",
    )

    assert result["status"] == "blocked"
    assert result["exit_code"] == 2
    assert result["writes_evidence_db"] is False
    assert "daily_price_qualification_requires_binding_role_cutoff_and_exact_bundle" in (
        result["blockers"][0]
    )
    assert "source_observation" not in result


def test_cli_rejects_partial_bundle_and_qualification_pins():
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--daily-price-qualification-binding-path",
                "qualification.json",
                "--daily-price-qualification-binding-sha256",
                "sha256:" + "a" * 64,
                "--daily-price-qualification-role",
                "outcome_realization",
                "--daily-price-qualification-cutoff-at",
                "2026-10-22T16:00:00+08:00",
            ]
        )
    assert exc_info.value.code == 2


def test_cli_rejects_partial_exact_bundle_descriptor():
    with pytest.raises(SystemExit) as exc_info:
        main(["--price-source-bundle-run-id", "quick-20261022"])
    assert exc_info.value.code == 2


def test_scheduled_service_rejects_unsupported_qualification_role(tmp_path: Path):
    data_root = tmp_path / "data"
    output_root = tmp_path / "output"
    data_root.mkdir()
    output_root.mkdir()
    config = SimpleNamespace(
        data_root=data_root,
        db_file=data_root / "evidence.sqlite",
        output_root=output_root,
    )
    exact_bundle = {
        "status": "captured",
        "schema_version": "daily-price-source-bundle.v1",
        "quick_run_id": "quick-run",
        "reference": {
            "relative_path": "scheduled/daily_price_source_bundles/runs/quick-run/"
            + "a" * 64
            + ".json",
            "sha256": "sha256:" + "a" * 64,
        },
    }

    result = run_scheduled_forward_outcomes(
        config=config,
        now=datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc),
        price_source_bundle_descriptor=exact_bundle,
        daily_price_qualification_binding_path=tmp_path / "binding.json",
        daily_price_qualification_binding_sha256="sha256:" + "b" * 64,
        daily_price_qualification_role="unsupported_role",
        daily_price_qualification_cutoff_at="2026-10-22T10:00:00+00:00",
    )

    assert result["status"] == "blocked"
    assert result["exit_code"] == 2
    assert "daily_price_qualification_role_invalid" in result["blockers"][0]


def test_scheduled_service_rejects_qualification_cutoff_after_checked_at(tmp_path: Path):
    data_root = tmp_path / "data"
    output_root = tmp_path / "output"
    data_root.mkdir()
    output_root.mkdir()
    config = SimpleNamespace(
        data_root=data_root,
        db_file=data_root / "evidence.sqlite",
        output_root=output_root,
    )
    exact_bundle = {
        "status": "captured",
        "schema_version": "daily-price-source-bundle.v1",
        "quick_run_id": "quick-run",
        "reference": {
            "relative_path": "scheduled/daily_price_source_bundles/runs/quick-run/"
            + "a" * 64
            + ".json",
            "sha256": "sha256:" + "a" * 64,
        },
    }

    result = run_scheduled_forward_outcomes(
        config=config,
        now=datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc),
        price_source_bundle_descriptor=exact_bundle,
        daily_price_qualification_binding_path=tmp_path / "binding.json",
        daily_price_qualification_binding_sha256="sha256:" + "b" * 64,
        daily_price_qualification_role="outcome_realization",
        daily_price_qualification_cutoff_at="2026-10-22T13:00:00+00:00",
    )

    assert result["status"] == "blocked"
    assert result["exit_code"] == 2
    assert "daily_price_qualification_cutoff_after_checked_at" in result["blockers"][0]
    assert "source_preflight" not in result


def test_extract_event_decision_cutoff_contract():
    from app_module.evidence_event_dtos import EvidenceEvent, EvidenceEventType
    from app_module.forward_performance_service import extract_event_decision_cutoff

    # 零散 metadata 的 aware 時間不是獨立決策時鐘證據。
    ev1 = EvidenceEvent(
        event_id="e1",
        event_hash="h1",
        event_date="2026-10-20",
        decision_date="2026-10-20",
        symbol="2330",
        event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
        event_family="recommendation",
        source_type="test",
        metadata={"decision_cutoff": "2026-10-20T14:30:00+08:00"},
    )
    cutoff = extract_event_decision_cutoff(ev1)
    assert cutoff is None

    # 2. Bare date without timezone/time must NOT be assumed as midnight
    ev_bare = EvidenceEvent(
        event_id="e2",
        event_hash="h2",
        event_date="2026-10-20",
        decision_date="2026-10-20",
        symbol="2330",
        event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
        event_family="recommendation",
        source_type="test",
        metadata={"decision_cutoff": "2026-10-20"},
    )
    assert extract_event_decision_cutoff(ev_bare) is None

    # 3. Missing cutoff must remain None (unknown)
    ev_missing = EvidenceEvent(
        event_id="e3",
        event_hash="h3",
        event_date="2026-10-20",
        decision_date="2026-10-20",
        symbol="2330",
        event_type=EvidenceEventType.RECOMMENDATION_INCLUDED,
        event_family="recommendation",
        source_type="test",
        metadata={},
    )
    assert extract_event_decision_cutoff(ev_missing) is None


def test_contextless_baseline_policy_is_rejected(tmp_path: Path):
    from app_module.forward_daily_price_source_binding import ForwardDailyPriceSourceBinder

    class MockResolver:
        def build_policy(self, **kwargs):
            return SimpleNamespace(**kwargs)

    binder = ForwardDailyPriceSourceBinder(
        output_root=tmp_path,
        data_root=tmp_path,
        database_path=tmp_path / "twstock.db",
        bundle={"status": "captured", "descriptors": {}},
        qualification_policy=SimpleNamespace(temporal_role="decision_baseline"),
        qualification_resolver=MockResolver(),
    )

    # Event with missing decision cutoff binds as unknown
    rows = [{"status": "source_identity_bound"}]
    bound_missing = binder.bind_rows(rows, qualification_policy="decision_cutoff_missing_or_unverifiable")
    assert bound_missing[0]["status"] == "unknown"
    assert bound_missing[0]["reason_code"] == "decision_cutoff_missing_or_unverifiable"

    # 即使時間有時區，沒有事件身份與上下文也不建立政策。
    policy = binder.build_event_policy(
        temporal_role="decision_baseline",
        cutoff_at=datetime(2026, 10, 20, 6, 30, tzinfo=timezone.utc),
    )
    assert policy == "decision_context_missing_or_outside_evaluation_cutoff"

