from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_evidence_pipeline


def _configs(tmp_path: Path) -> tuple[SimpleNamespace, SimpleNamespace]:
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


class _Summary:
    def to_dict(self) -> dict[str, bool]:
        return {"ok": True}


class _Runner:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def run(self, _request: object) -> _Summary:
        return _Summary()


def test_confirm_cli_locks_canonical_root_when_artifact_output_is_overridden(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    canonical, artifact = _configs(tmp_path)
    acquired: list[Path] = []
    released: list[object] = []
    lease = object()

    monkeypatch.setattr(
        run_evidence_pipeline,
        "TWStockConfig",
        lambda **kwargs: artifact if kwargs else canonical,
    )
    monkeypatch.setattr(run_evidence_pipeline, "EvidencePipelineRunner", _Runner)
    monkeypatch.setattr(
        run_evidence_pipeline,
        "heavy_chain_lock_path",
        lambda root: Path(root) / "heavy.lock",
    )
    monkeypatch.setattr(
        run_evidence_pipeline,
        "acquire_heavy_chain_reservation",
        lambda path: acquired.append(Path(path)) or lease,
    )
    monkeypatch.setattr(
        run_evidence_pipeline,
        "release_heavy_chain_reservation",
        lambda reservation: released.append(reservation),
    )

    exit_code = run_evidence_pipeline.main(
        [
            "--decision-date",
            "2026-10-04",
            "--db-path",
            str(canonical.db_file),
            "--data-root",
            str(canonical.data_root),
            "--output-root",
            str(artifact.output_root),
            "--confirm",
        ]
    )

    assert exit_code == 0
    assert '"ok": true' in capsys.readouterr().out
    assert acquired == [canonical.output_root / "release_v4" / "heavy.lock"]
    assert released == [lease]


def test_confirm_cli_skips_canonical_lock_for_isolated_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    canonical, artifact = _configs(tmp_path)
    monkeypatch.setattr(
        run_evidence_pipeline,
        "TWStockConfig",
        lambda **kwargs: artifact if kwargs else canonical,
    )
    monkeypatch.setattr(run_evidence_pipeline, "EvidencePipelineRunner", _Runner)
    monkeypatch.setattr(
        run_evidence_pipeline,
        "acquire_heavy_chain_reservation",
        lambda _path: pytest.fail("isolated working-copy DB must not take canonical lock"),
    )

    exit_code = run_evidence_pipeline.main(
        [
            "--decision-date",
            "2026-10-04",
            "--db-path",
            str(tmp_path / "working-copy" / "evidence.sqlite"),
            "--data-root",
            str(canonical.data_root),
            "--output-root",
            str(artifact.output_root),
            "--confirm",
        ]
    )

    assert exit_code == 0
    assert '"ok": true' in capsys.readouterr().out
