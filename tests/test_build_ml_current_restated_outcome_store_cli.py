from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from data_module.portfolio_ml_current_restated_outcome_store import (
    CurrentRestatedOutcomeStoreError,
    CurrentRestatedOutcomeStoreRequest,
)
from scripts import build_ml_current_restated_outcome_store as cli


def test_cli_passes_explicit_raw_pins_and_reports_research_only_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    publication = SimpleNamespace(
        run_id="run-test",
        manifest_path=tmp_path / "manifest.json",
        latest_manifest_path=tmp_path / "latest.json",
        manifest_sha256="a" * 64,
        raw_publication_manifest_sha256="b" * 64,
        raw_dataset_manifest_sha256="c" * 64,
        feature_registry_sha256="d" * 64,
        observation_count=1_000,
        feature_count=52,
        fold_count=4,
        artifact_available_at=datetime(2026, 10, 3, 3, 0, tzinfo=timezone.utc),
    )
    received: list[CurrentRestatedOutcomeStoreRequest] = []

    class Builder:
        def build(self, request: CurrentRestatedOutcomeStoreRequest) -> SimpleNamespace:
            received.append(request)
            return publication

    monkeypatch.setattr(cli, "PortfolioMLCurrentRestatedOutcomeStoreBuilder", Builder)
    result = cli.main(
        [
            "--raw-publication-manifest", str(tmp_path / "raw.json"),
            "--expected-raw-publication-manifest-sha256", "1" * 64,
            "--expected-core-dataset-manifest-sha256", "2" * 64,
            "--output-dir", str(tmp_path / "output"),
            "--target-symbols", "2317", "2330",
            "--repository-root", str(tmp_path),
        ]
    )

    assert result == 0
    assert len(received) == 1
    request = received[0]
    assert request.target_symbols == ("2317", "2330")
    assert request.minimum_train_dates == 125
    assert request.test_date_count == 63
    assert request.purge_trading_days == 60
    assert request.embargo_trading_days == 5
    assert request.expected_raw_publication_manifest_sha256 == "1" * 64
    assert request.expected_raw_dataset_manifest_sha256 == "2" * 64
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "completed_research_only"
    assert output["fold_count"] == 4
    assert output["raw_publication_manifest_sha256"] == "b" * 64
    assert output["raw_dataset_manifest_sha256"] == "c" * 64
    assert output["formal_training_eligible"] is False
    assert output["historical_pit_eligible"] is False


def test_cli_returns_typed_block_without_claiming_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class Builder:
        def build(self, request: CurrentRestatedOutcomeStoreRequest) -> None:
            raise CurrentRestatedOutcomeStoreError("fixture pin rejected")

    monkeypatch.setattr(cli, "PortfolioMLCurrentRestatedOutcomeStoreBuilder", Builder)
    result = cli.main(
        [
            "--raw-publication-manifest", str(tmp_path / "raw.json"),
            "--expected-raw-publication-manifest-sha256", "1" * 64,
            "--expected-core-dataset-manifest-sha256", "2" * 64,
            "--output-dir", str(tmp_path / "output"),
            "--target-symbols", "2317", "2330",
            "--repository-root", str(tmp_path),
        ]
    )

    assert result == 2
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "blocked"
    assert output["error"] == "fixture pin rejected"
    assert output["formal_training_eligible"] is False
    assert output["historical_pit_eligible"] is False
