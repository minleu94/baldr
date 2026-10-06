from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.continue_ml_direct_ooc_after_store as ooc_continuation
import scripts.continue_ml_direct_v3_refresh_chain as refresh_chain
import scripts.maintain_ml_direct_v3_refresh_chain as chain_maintenance


def _configured_repository(tmp_path: Path) -> tuple[Path, Path, Path]:
    repository = tmp_path / "repository"
    repository.mkdir()
    active_root = tmp_path / "active_ml_research"
    storage_config = repository / "output" / "ml_research_storage.json"
    storage_config.parent.mkdir(parents=True)
    storage_config.write_text(
        json.dumps(
            {
                "schema_version": "ml-research-storage.v1",
                "active_root": str(active_root),
            }
        ),
        encoding="utf-8",
    )
    legacy_root = repository / "output" / "ml_research"
    return repository, active_root, legacy_root


def test_ooc_research_rejects_legacy_training_output_before_status_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, active_root, legacy_root = _configured_repository(tmp_path)
    monkeypatch.setattr(ooc_continuation, "ROOT", repository)
    training_output_dir = legacy_root / "training"
    status_path = training_output_dir / "continuation_status.json"

    with pytest.raises(ValueError, match="configured active ML research root"):
        ooc_continuation.main(
            [
                "--resume-after-direct-store",
                "--store-output-dir",
                str(legacy_root / "store"),
                "--training-output-dir",
                str(training_output_dir),
                "--output-root",
                str(active_root),
                "--allow-research",
            ]
        )

    assert not status_path.exists()
    assert not training_output_dir.exists()
    assert not active_root.exists()


def test_ooc_research_reads_legacy_store_and_writes_status_to_active_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, active_root, legacy_root = _configured_repository(tmp_path)
    monkeypatch.setattr(ooc_continuation, "ROOT", repository)
    store_output_dir = legacy_root / "completed_store"
    store_output_dir.mkdir(parents=True)
    training_output_dir = active_root / "training"

    result = ooc_continuation.main(
        [
            "--resume-after-direct-store",
            "--store-output-dir",
            str(store_output_dir),
            "--training-output-dir",
            str(training_output_dir),
            "--output-root",
            str(active_root),
            "--allow-research",
        ]
    )

    status_path = training_output_dir / "continuation_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert result == 2
    assert (
        status["classification"]
        == "current_restated_training_consumer_not_connected"
    )
    assert Path(status["store_output_dir"]) == store_output_dir.resolve()
    assert status["formal_oos_allowed"] is False
    assert status_path.is_file()
    assert not (legacy_root / "completed_store" / "continuation_status.json").exists()


@pytest.mark.parametrize(
    "legacy_target",
    (
        "store_output_dir",
        "training_output_dir",
        "output_root",
        "status_path",
        "operational_log_dir",
    ),
)
def test_refresh_chain_rejects_each_legacy_write_root_before_any_output(
    legacy_target: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, active_root, legacy_root = _configured_repository(tmp_path)
    monkeypatch.setattr(refresh_chain, "ROOT", repository)
    store_output_dir = active_root / "store"
    training_output_dir = active_root / "training"
    output_root = active_root / "output"
    status_path = active_root / "status.json"
    operational_log_dir = active_root / "logs"
    if legacy_target == "store_output_dir":
        store_output_dir = legacy_root / "store"
    elif legacy_target == "training_output_dir":
        training_output_dir = legacy_root / "training"
    elif legacy_target == "output_root":
        output_root = legacy_root / "output"
    elif legacy_target == "status_path":
        status_path = legacy_root / "status.json"
    elif legacy_target == "operational_log_dir":
        operational_log_dir = legacy_root / "logs"

    monkeypatch.setattr(
        refresh_chain,
        "_atomic_write_json",
        lambda *_args, **_kwargs: pytest.fail("status write must not start"),
    )
    monkeypatch.setattr(
        refresh_chain,
        "_start_logged",
        lambda *_args, **_kwargs: pytest.fail("child process must not start"),
    )
    argv = [
        "--legacy-direct-process-id",
        "0",
        "--legacy-ooc-helper-process-id",
        "0",
        "--legacy-release-process-id",
        "0",
        "--resume-after-legacy-chain",
        "--raw-manifest",
        str(repository / "inputs" / "raw.json"),
        "--store-output-dir",
        str(store_output_dir),
        "--training-output-dir",
        str(training_output_dir),
        "--output-root",
        str(output_root),
        "--database",
        str(repository / "inputs" / "twstock.db"),
        "--training-as-of",
        "2026-10-03T08:30:00+08:00",
        "--benchmark-entity",
        "TAIEX",
        "--status-path",
        str(status_path),
        "--operational-log-dir",
        str(operational_log_dir),
        "--allow-research",
    ]

    with pytest.raises(ValueError, match="research writes must be inside"):
        refresh_chain.main(argv)

    assert not active_root.exists()
    assert not legacy_root.exists()


@pytest.mark.parametrize(
    "legacy_target",
    ("store_output_dir", "training_output_dir", "output_root"),
)
def test_maintenance_rejects_legacy_write_roots_before_reservation_or_log(
    legacy_target: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, active_root, legacy_root = _configured_repository(tmp_path)
    monkeypatch.setattr(chain_maintenance, "ROOT", repository)
    store_output_dir = active_root / "store"
    training_output_dir = active_root / "training"
    output_root = active_root / "output"
    if legacy_target == "store_output_dir":
        store_output_dir = legacy_root / "store"
    elif legacy_target == "training_output_dir":
        training_output_dir = legacy_root / "training"
    elif legacy_target == "output_root":
        output_root = legacy_root / "output"

    args = SimpleNamespace(
        poll_seconds=5,
        retry_delay_seconds=0,
        max_restarts=0,
        store_output_dir=store_output_dir,
        training_output_dir=training_output_dir,
        output_root=output_root,
        allow_research=True,
    )
    monkeypatch.setattr(
        chain_maintenance,
        "_parser",
        lambda: SimpleNamespace(parse_args=lambda _argv: args),
    )
    monkeypatch.setattr(
        chain_maintenance,
        "acquire_heavy_chain_reservation",
        lambda *_args, **_kwargs: pytest.fail("reservation must not start"),
    )
    monkeypatch.setattr(
        chain_maintenance,
        "_log",
        lambda *_args, **_kwargs: pytest.fail("log write must not start"),
    )

    with pytest.raises(ValueError, match="research writes must be inside"):
        chain_maintenance.main([])

    assert not active_root.exists()
    assert not legacy_root.exists()
    log_path = training_output_dir / "logs" / "ml_direct_chain_maintenance.log"
    assert not log_path.exists()
