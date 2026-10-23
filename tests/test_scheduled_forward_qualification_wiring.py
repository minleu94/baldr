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


def test_scheduled_service_rejects_eventless_decision_baseline_qualification(tmp_path: Path):
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
        daily_price_qualification_role="decision_baseline",
        daily_price_qualification_cutoff_at="2026-10-23T00:00:00+00:00",
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
