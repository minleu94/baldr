from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from data_module.config import TWStockConfig
from scripts import capture_evidence_events


class _Summary:
    def to_dict(self) -> dict[str, object]:
        return {"dry_run": self.dry_run, "events_inserted": 0}

    def __init__(self, dry_run: bool) -> None:
        self.dry_run = dry_run


def _configs(tmp_path: Path) -> tuple[SimpleNamespace, SimpleNamespace, Path]:
    canonical_data = tmp_path / "canonical-data"
    canonical_output = tmp_path / "canonical-output"
    canonical = SimpleNamespace(
        data_root=canonical_data,
        output_root=canonical_output,
        db_file=canonical_data / "sqlite" / "twstock.db",
    )
    artifact = SimpleNamespace(
        data_root=canonical_data,
        output_root=tmp_path / "artifact-output",
        db_file=canonical.db_file,
    )
    isolated_db = tmp_path / "isolated" / "evidence.sqlite"
    return canonical, artifact, isolated_db


def _install_fake_capture(
    monkeypatch: pytest.MonkeyPatch,
    *,
    repository_read_only: list[bool],
    requests: list[Any],
) -> None:
    class Repository:
        def __init__(self, _config: object, *, read_only: bool = False) -> None:
            repository_read_only.append(read_only)

    class EventService:
        def __init__(self, _repository: object) -> None:
            pass

    class CaptureService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def capture(self, request: Any) -> _Summary:
            requests.append(request)
            return _Summary(bool(request.dry_run))

    monkeypatch.setattr(capture_evidence_events, "EvidenceEventRepository", Repository)
    monkeypatch.setattr(capture_evidence_events, "EvidenceEventService", EventService)
    monkeypatch.setattr(capture_evidence_events, "EvidenceCaptureService", CaptureService)
    monkeypatch.setattr(
        capture_evidence_events,
        "build_recommendation_execution_queries",
        lambda _config: object(),
    )
    monkeypatch.setattr(
        capture_evidence_events,
        "_decision_desk_importers",
        lambda *_args, **_kwargs: {},
    )


def test_confirm_cli_locks_canonical_db_even_with_artifact_output_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    canonical, artifact, _isolated_db = _configs(tmp_path)
    repository_read_only: list[bool] = []
    requests: list[Any] = []
    acquired: list[Path] = []
    released: list[object] = []
    lease = object()

    def config_factory(**kwargs: object) -> SimpleNamespace:
        return artifact if "output_root" in kwargs else canonical

    monkeypatch.setattr(capture_evidence_events, "TWStockConfig", config_factory)
    _install_fake_capture(
        monkeypatch,
        repository_read_only=repository_read_only,
        requests=requests,
    )
    monkeypatch.setattr(
        capture_evidence_events,
        "heavy_chain_lock_path",
        lambda root: Path(root) / "heavy.lock",
    )

    def acquire(path: Path) -> object:
        acquired.append(Path(path))
        return lease

    monkeypatch.setattr(
        capture_evidence_events,
        "acquire_heavy_chain_reservation",
        acquire,
    )
    monkeypatch.setattr(
        capture_evidence_events,
        "release_heavy_chain_reservation",
        lambda reservation: released.append(reservation),
    )

    exit_code = capture_evidence_events.main(
        [
            "--data-root", str(canonical.data_root),
            "--output-root", str(artifact.output_root),
            "--db-path", str(canonical.db_file),
            "--source", "recommendation",
            "--confirm",
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is False
    assert acquired == [canonical.output_root / "release_v4" / "heavy.lock"]
    assert released == [lease]
    assert repository_read_only == [False]
    assert requests[0].confirm is True
    assert requests[0].dry_run is False


def test_confirm_releases_only_its_lease_when_capture_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical, artifact, _isolated_db = _configs(tmp_path)
    acquired: list[Path] = []
    released: list[object] = []
    lease = object()

    monkeypatch.setattr(
        capture_evidence_events,
        "TWStockConfig",
        lambda **kwargs: artifact if "output_root" in kwargs else canonical,
    )
    monkeypatch.setattr(
        capture_evidence_events,
        "build_recommendation_execution_queries",
        lambda _config: object(),
    )
    monkeypatch.setattr(
        capture_evidence_events,
        "_decision_desk_importers",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        capture_evidence_events,
        "EvidenceEventRepository",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        capture_evidence_events,
        "EvidenceEventService",
        lambda _repository: object(),
    )

    class FailingCaptureService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def capture(self, _request: object) -> None:
            raise RuntimeError("capture failed")

    monkeypatch.setattr(
        capture_evidence_events,
        "EvidenceCaptureService",
        FailingCaptureService,
    )
    monkeypatch.setattr(
        capture_evidence_events,
        "heavy_chain_lock_path",
        lambda root: Path(root) / "heavy.lock",
    )

    def acquire(path: Path) -> object:
        acquired.append(Path(path))
        return lease

    monkeypatch.setattr(
        capture_evidence_events,
        "acquire_heavy_chain_reservation",
        acquire,
    )
    monkeypatch.setattr(
        capture_evidence_events,
        "release_heavy_chain_reservation",
        lambda reservation: released.append(reservation),
    )

    with pytest.raises(RuntimeError, match="capture failed"):
        capture_evidence_events.main(
            [
                "--data-root", str(canonical.data_root),
                "--output-root", str(artifact.output_root),
                "--db-path", str(canonical.db_file),
                "--source", "recommendation",
                "--confirm",
            ]
        )

    assert acquired == [canonical.output_root / "release_v4" / "heavy.lock"]
    assert released == [lease]


def test_busy_canonical_confirm_fails_before_repository_or_importer_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    canonical, artifact, _isolated_db = _configs(tmp_path)
    repository_read_only: list[bool] = []
    requests: list[Any] = []
    lease_releases: list[object] = []

    monkeypatch.setattr(
        capture_evidence_events,
        "TWStockConfig",
        lambda **kwargs: artifact if "output_root" in kwargs else canonical,
    )
    _install_fake_capture(
        monkeypatch,
        repository_read_only=repository_read_only,
        requests=requests,
    )
    monkeypatch.setattr(
        capture_evidence_events,
        "heavy_chain_lock_path",
        lambda root: Path(root) / "heavy.lock",
    )
    monkeypatch.setattr(
        capture_evidence_events,
        "acquire_heavy_chain_reservation",
        lambda _path: None,
    )
    monkeypatch.setattr(
        capture_evidence_events,
        "release_heavy_chain_reservation",
        lambda lease: lease_releases.append(lease),
    )

    exit_code = capture_evidence_events.main(
        [
            "--data-root", str(canonical.data_root),
            "--output-root", str(artifact.output_root),
            "--db-path", str(canonical.db_file),
            "--source", "recommendation",
            "--confirm",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert json.loads(captured.err)["status"] == "blocked_writer_busy"
    assert repository_read_only == []
    assert requests == []
    assert lease_releases == []


@pytest.mark.parametrize("arguments", [[], ["--dry-run", "--confirm"]])
def test_dry_run_never_takes_writer_lock_and_opens_evidence_repo_read_only(
    arguments: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    canonical, artifact, _isolated_db = _configs(tmp_path)
    repository_read_only: list[bool] = []
    requests: list[Any] = []
    monkeypatch.setattr(
        capture_evidence_events,
        "TWStockConfig",
        lambda **kwargs: artifact if "output_root" in kwargs else canonical,
    )
    _install_fake_capture(
        monkeypatch,
        repository_read_only=repository_read_only,
        requests=requests,
    )
    monkeypatch.setattr(
        capture_evidence_events,
        "acquire_heavy_chain_reservation",
        lambda _path: pytest.fail("dry-run must not acquire a writer reservation"),
    )

    exit_code = capture_evidence_events.main(
        [
            "--data-root", str(canonical.data_root),
            "--output-root", str(artifact.output_root),
            "--db-path", str(canonical.db_file),
            "--source", "recommendation",
            *arguments,
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    assert repository_read_only == [True]
    assert requests[0].dry_run is True
    assert requests[0].confirm is ("--confirm" in arguments)


def test_confirm_isolated_database_does_not_take_canonical_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    canonical, artifact, isolated_db = _configs(tmp_path)
    repository_read_only: list[bool] = []
    requests: list[Any] = []
    monkeypatch.setattr(
        capture_evidence_events,
        "TWStockConfig",
        lambda **kwargs: artifact if "output_root" in kwargs else canonical,
    )
    _install_fake_capture(
        monkeypatch,
        repository_read_only=repository_read_only,
        requests=requests,
    )
    monkeypatch.setattr(
        capture_evidence_events,
        "acquire_heavy_chain_reservation",
        lambda _path: pytest.fail("isolated DB must not use the canonical lock"),
    )

    exit_code = capture_evidence_events.main(
        [
            "--data-root", str(canonical.data_root),
            "--output-root", str(artifact.output_root),
            "--db-path", str(isolated_db),
            "--source", "recommendation",
            "--confirm",
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is False
    assert repository_read_only == [False]
    assert requests[0].dry_run is False


def test_decision_desk_snapshot_source_is_always_opened_read_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed_read_only: list[bool] = []

    class SnapshotRepository:
        def __init__(self, _config: object, *, read_only: bool = False) -> None:
            observed_read_only.append(read_only)

        def latest_before_or_on(self, _decision_date: str) -> None:
            return None

    monkeypatch.setattr(
        capture_evidence_events,
        "DecisionDeskSnapshotRepository",
        SnapshotRepository,
    )

    importers = capture_evidence_events._decision_desk_importers(
        TWStockConfig(data_root=tmp_path / "data", output_root=tmp_path / "output"),
        "2026-10-04",
        read_only=True,
    )

    assert observed_read_only == [True]
    assert set(importers) == {"watchlist-trigger", "portfolio-alert", "risk-prompt"}
