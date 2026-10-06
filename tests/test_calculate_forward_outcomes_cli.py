from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import calculate_forward_outcomes


class _Summary:
    def to_dict(self) -> dict[str, object]:
        return {"dry_run": True, "events_scanned": 0}


def _config_pair(tmp_path: Path) -> tuple[SimpleNamespace, SimpleNamespace]:
    canonical = SimpleNamespace(
        data_root=tmp_path / "canonical-data",
        output_root=tmp_path / "canonical-output",
        db_file=tmp_path / "canonical-data" / "sqlite" / "twstock.db",
    )
    artifact = SimpleNamespace(
        data_root=canonical.data_root,
        output_root=tmp_path / "artifact-output",
        db_file=canonical.db_file,
    )
    return canonical, artifact


def test_manual_cli_uses_canonical_lock_root_when_artifact_output_is_overridden(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    canonical, artifact = _config_pair(tmp_path)
    repository_calls: list[bool] = []
    acquired: list[Path] = []
    released: list[object] = []
    service_calls: list[dict[str, object]] = []
    calendar_observations: list[datetime] = []
    lease = object()

    def config_factory(**kwargs: object) -> SimpleNamespace:
        return artifact if kwargs else canonical

    class Repository:
        def __init__(self, _config: object, *, read_only: bool = False) -> None:
            repository_calls.append(read_only)

    class Service:
        def __init__(self, _config: object, _repository: object, *, maturity_calendar: object) -> None:
            assert maturity_calendar is not None
            calendar_observations.append(maturity_calendar)

        def calculate(self, **kwargs: object) -> _Summary:
            service_calls.append(kwargs)
            return _Summary()

    monkeypatch.setattr(calculate_forward_outcomes, "TWStockConfig", config_factory)
    monkeypatch.setattr(calculate_forward_outcomes, "EvidenceEventRepository", Repository)
    monkeypatch.setattr(calculate_forward_outcomes, "ForwardPerformanceService", Service)
    monkeypatch.setattr(
        calculate_forward_outcomes,
        "build_official_maturity_calendar",
        lambda **kwargs: kwargs["observed_at"],
    )
    monkeypatch.setattr(
        calculate_forward_outcomes,
        "heavy_chain_lock_path",
        lambda root: Path(root) / "heavy.lock",
    )
    monkeypatch.setattr(
        calculate_forward_outcomes,
        "acquire_heavy_chain_reservation",
        lambda path: acquired.append(Path(path)) or lease,
    )
    monkeypatch.setattr(
        calculate_forward_outcomes,
        "release_heavy_chain_reservation",
        lambda reservation: released.append(reservation),
    )

    exit_code = calculate_forward_outcomes.main(
        ["--output-root", str(artifact.output_root), "--windows", "5"]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert '"events_scanned": 0' in output
    assert acquired == [canonical.output_root / "release_v4" / "heavy.lock"]
    assert released == [lease]
    assert repository_calls == [False]
    assert service_calls[0]["dry_run"] is False
    assert service_calls[0]["data_as_of_date"] == datetime.fromisoformat(
        str(service_calls[0]["data_as_of_date"])
    ).date().isoformat()
    assert service_calls[0]["invocation_at"] == calendar_observations[0]


def test_manual_cli_dry_run_opens_repository_read_only_without_writer_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    canonical, artifact = _config_pair(tmp_path)
    repository_calls: list[bool] = []

    class Repository:
        def __init__(self, _config: object, *, read_only: bool = False) -> None:
            repository_calls.append(read_only)

    class Service:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def calculate(self, **kwargs: object) -> _Summary:
            assert kwargs["dry_run"] is True
            return _Summary()

    monkeypatch.setattr(
        calculate_forward_outcomes,
        "TWStockConfig",
        lambda **kwargs: artifact if kwargs else canonical,
    )
    monkeypatch.setattr(calculate_forward_outcomes, "EvidenceEventRepository", Repository)
    monkeypatch.setattr(calculate_forward_outcomes, "ForwardPerformanceService", Service)
    monkeypatch.setattr(
        calculate_forward_outcomes,
        "build_official_maturity_calendar",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(
        calculate_forward_outcomes,
        "acquire_heavy_chain_reservation",
        lambda _path: pytest.fail("dry-run must not acquire a writer lock"),
    )

    exit_code = calculate_forward_outcomes.main(
        ["--output-root", str(artifact.output_root), "--dry-run"]
    )

    assert exit_code == 0
    assert '"dry_run": true' in capsys.readouterr().out
    assert repository_calls == [True]
