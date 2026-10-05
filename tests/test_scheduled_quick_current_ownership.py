from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from data_module.tdcc_shareholding_candidate import TDCC_FIELDS
from scripts import capture_tdcc_shareholding_candidate as capture_cli
from scripts.scheduled import run_daily_data_update_quick as runner


def _tdcc_payload() -> bytes:
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(TDCC_FIELDS)
    values = ["2.00", "3.00", *(["1.00"] * 12), "83.00", "0.00"]
    for tier, ratio in enumerate(values, 1):
        writer.writerow(["20261002", "2330", str(tier), "10", "100", ratio])
    writer.writerow(["20261002", "2330", "17", "10", "1000", "100.00"])
    return output.getvalue().encode("utf-8-sig")


def _write_capture_fixture(output_root: Path, capture_id: str, scheduled_run_id: str) -> dict[str, object]:
    capture_dir = capture_cli._canonical_capture_directory(output_root, capture_id, create=True)
    now = datetime.now(timezone.utc) - timedelta(seconds=2)
    request_started = (now - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    body_completed = now.isoformat().replace("+00:00", "Z")
    raw_bytes = _tdcc_payload()
    raw_path = capture_dir / f"tdcc_1-5_raw_{now.strftime('%Y%m%dT%H%M%SZ')}.csv"
    with raw_path.open("xb") as handle:
        handle.write(raw_bytes)
    raw_sha = sha256(raw_bytes).hexdigest()
    metadata = {
        "url": capture_cli.TDCC_URL,
        "http_status": 200,
        "content_type": "text/csv",
        "request_started_at_utc": request_started,
        "body_completed_at_utc": body_completed,
        "captured_at_utc": body_completed,
        "metadataclock_semantics": "body_read_completed",
        "sha256": raw_sha,
        "content_length": len(raw_bytes),
        "raw_file": raw_path.name,
        "capture_id": capture_id,
        "scheduled_run_id": scheduled_run_id,
    }
    capture_cli._write_json_exclusive(raw_path.with_name(raw_path.name + ".meta.json"), metadata)
    manifest = capture_cli.build_artifacts(
        raw_path,
        capture_dir,
        datetime.fromisoformat(body_completed.replace("Z", "+00:00")),
        metadata,
        capture_id=capture_id,
        scheduled_run_id=scheduled_run_id,
        create_only=True,
    )
    return manifest


def test_candidate_tdcc_gate_requires_same_run_verified_tdcc_row() -> None:
    @dataclass
    class Summary:
        sources: tuple[str, ...] = ("tdcc",)

    assert not runner._candidate_tdcc_capture_ready([
        {"name": "update_phase3c_candidate_sources", "status": "passed",
         "result": {"success": True, "summary": Summary}},
    ])
    assert not runner._candidate_tdcc_capture_ready([])
    assert not runner._candidate_tdcc_capture_ready([
        {"name": "update_phase3c_candidate_sources", "status": "warning", "result": {"success": False}}
    ])
    assert not runner._candidate_tdcc_capture_ready([
        {
            "name": "update_phase3c_candidate_sources",
            "status": "passed",
            "result": {
                "success": True,
                "summary": {"sources": ["institutional", "credit", "tdcc"], "daily_results": []},
            },
        }
    ])
    assert runner._candidate_tdcc_capture_ready([
        {
            "name": "update_phase3c_candidate_sources",
            "status": "passed",
            "result": {
                "success": True,
                "summary": {
                    "sources": ["institutional", "credit", "tdcc"],
                    "daily_results": [{"source": "tdcc", "status": "SUCCESS"}],
                },
            },
        }
    ])
    assert runner._candidate_tdcc_capture_ready([
        {
            "name": "update_phase3c_candidate_sources",
            "status": "passed",
            "result": {
                "success": True,
                "summary": {
                    "sources": ["institutional", "credit", "tdcc"],
                    "daily_results": [{"source": "tdcc", "status": "SKIPPED_ALREADY_EXISTS"}],
                },
            },
        }
    ])


def test_quick_tdcc_dry_run_does_not_start_child_or_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_root = tmp_path / "canonical-output"
    output_root.mkdir()
    monkeypatch.setattr(runner.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("dry-run started child"))
    result = runner._run_tdcc_current_ownership_capture(
        output_root=output_root,
        run_id="20261005-1234",
        capture_id="20261005T010203000000Z-quick-20261005-1234-token",
        dry_run=True,
    )
    assert result["success"] is True
    assert result["status"] == "planned"
    assert result["network_requested"] is False
    assert result["writes_performed"] is False
    assert not (output_root / "current_observed_market_ownership").exists()


def test_quick_capture_readback_pins_manifest_raw_and_parent_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_root = tmp_path / "canonical-output"
    output_root.mkdir()
    run_id = "20261005-1234"
    capture_id = "20261005T010203000000Z-quick-20261005-1234-token"
    manifest = _write_capture_fixture(output_root, capture_id, run_id)
    stdout = json.dumps(manifest, ensure_ascii=False) + "\nlegacy informational line\n"
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):
        observed["command"] = list(command)
        observed["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    result = runner._run_tdcc_current_ownership_capture(
        output_root=output_root,
        run_id=run_id,
        capture_id=capture_id,
    )
    assert result["success"] is True
    assert result["status"] == "captured"
    assert result["current_only"] is True
    assert result["publication_at"] is None
    assert result["available_at"] is None
    assert result["source_date"] == "2026-10-02"
    assert result["manifest_sha256"] == sha256(Path(str(result["manifest_path"])).read_bytes()).hexdigest()
    assert result["raw_sha256"] == manifest["source_payload_sha256"]
    assert result["request_started_at_utc"] == manifest["request_started_at_utc"]
    assert result["body_completed_at_utc"] == manifest["body_completed_at_utc"]
    assert "--scheduled-run-id" in observed["command"]
    assert run_id in observed["command"]
    assert observed["kwargs"]["timeout"] == 150


def test_quick_capture_failure_stays_warning_and_never_reports_captured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_root = tmp_path / "canonical-output"
    output_root.mkdir()
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=2, stdout="", stderr="network failed"),
    )
    result = runner._run_tdcc_current_ownership_capture(
        output_root=output_root,
        run_id="20261005-1234",
        capture_id="20261005T010203000000Z-quick-20261005-1234-token",
    )
    steps: list[dict[str, object]] = []
    failed = runner._run_step(
        steps=steps,
        name="capture_tdcc_current_ownership",
        action=lambda: result,
        warning_only=True,
    )
    assert failed is None
    assert steps[0]["status"] == "warning"
    assert steps[0]["result"]["status"] == "failed"
    assert "not_captured" in steps[0]["result"]["reason"]
    assert steps[0]["message"]


@pytest.mark.parametrize("defect", ["parent_run", "aggregate_hash", "missing_aggregate"])
def test_quick_rejects_wrong_parent_or_changed_saved_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str,
) -> None:
    output_root = tmp_path / "canonical-output"
    output_root.mkdir()
    run_id = "quick-parent-a"
    capture_id = "20261005T010203000000Z-quick-parent-a"
    manifest = _write_capture_fixture(output_root, capture_id, run_id)
    if defect == "parent_run":
        manifest["scheduled_run_id"] = "quick-parent-b"
    else:
        aggregate = (
            output_root / "current_observed_market_ownership" / "tdcc" / capture_id
            / str(manifest["aggregate_file"])
        )
        if defect == "missing_aggregate":
            aggregate.rename(aggregate.with_suffix(".held"))
        else:
            with aggregate.open("ab") as handle:
                handle.write(b"changed")
    monkeypatch.setattr(
        runner.subprocess, "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout=json.dumps(manifest), stderr="",
        ),
    )
    result = runner._run_tdcc_current_ownership_capture(
        output_root=output_root, run_id=run_id, capture_id=capture_id,
    )
    assert result["success"] is False
    assert result["status"] == "failed"
