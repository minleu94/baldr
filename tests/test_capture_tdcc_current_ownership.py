from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path

import pytest

from data_module.tdcc_shareholding_candidate import TDCC_FIELDS
from scripts import capture_tdcc_shareholding_candidate as capture


def _official_payload() -> bytes:
    values = ["1.00"] * 16
    values[0] = "2.00"
    values[1] = "3.00"
    values[14] = "83.00"
    values[15] = "0.00"
    rows = [
        ["20260904", "2330", str(tier), "10", "100", values[tier - 1]]
        for tier in range(1, 17)
    ]
    rows.append(["20260904", "2330", "17", "10", "1000", "100.00"])
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(TDCC_FIELDS)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def _manifest_from_stdout(text: str) -> dict[str, object]:
    marker = "\nAPPLY_CLI="
    assert marker in text
    value = json.loads(text.split(marker, 1)[0])
    assert isinstance(value, dict)
    return value


class _Response:
    status = 200
    headers = {"Content-Type": "text/csv; charset=utf-8"}

    def __init__(self, payload: bytes, events: list[str] | None = None) -> None:
        self._payload = payload
        self.events = events if events is not None else []

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        assert size == capture.MAX_RAW_BYTES + 1
        self.events.append("body_read")
        return self._payload


def _install_fake_http(
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
    *,
    events: list[str] | None = None,
) -> list[object]:
    calls: list[object] = []

    def fake_urlopen(request: object, timeout: int = 0) -> _Response:
        calls.append((request, timeout))
        if events is not None:
            events.append("urlopen")
        return _Response(payload, events)

    monkeypatch.setattr(capture, "urlopen", fake_urlopen)
    return calls


def test_public_current_capture_pins_body_clock_raw_and_derived_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = _official_payload()
    output_root = tmp_path / "canonical-output"
    output_root.mkdir()
    events: list[str] = []
    moments = [
        datetime(2026, 10, 5, 1, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 5, 1, 0, 2, tzinfo=timezone.utc),
    ]

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz: timezone | None = None) -> datetime:
            events.append("clock")
            value = moments.pop(0)
            return value if tz is None else value.astimezone(tz)

    monkeypatch.setattr(capture, "datetime", FixedDateTime)
    calls = _install_fake_http(monkeypatch, payload, events=events)

    result = capture.main(
        [
            "--output-root",
            str(output_root),
            "--capture-id",
            "20261005T010000000000Z-daily-a",
            "--scheduled-run-id",
            "quick-run-20261005-a",
        ]
    )

    assert result == 0
    assert events == ["clock", "urlopen", "body_read", "clock"]
    request, timeout = calls[0]
    assert request.full_url == capture.TDCC_URL  # type: ignore[attr-defined]
    assert timeout == 120

    manifest = _manifest_from_stdout(capsys.readouterr().out)
    capture_dir = (
        output_root
        / "current_observed_market_ownership"
        / "tdcc"
        / "20261005T010000000000Z-daily-a"
    )
    raw_path = capture_dir / "tdcc_1-5_raw_20261005T010002Z.csv"
    raw_meta_path = raw_path.with_name(raw_path.name + ".meta.json")
    manifest_path = capture_dir / "tdcc_1-5_20260904_manifest.json"

    assert raw_path.is_file() and raw_path.read_bytes() == payload
    assert raw_meta_path.is_file()
    assert manifest_path.is_file()
    assert manifest["schema_version"] == "tdcc-current-ownership-capture.v1"
    assert manifest["capture_id"] == "20261005T010000000000Z-daily-a"
    assert manifest["scheduled_run_id"] == "quick-run-20261005-a"
    assert manifest["raw_file"] == str(raw_path)
    assert manifest["endpoint"] == capture.TDCC_URL
    assert manifest["request_started_at_utc"] == "2026-10-05T01:00:00Z"
    assert manifest["body_completed_at_utc"] == "2026-10-05T01:00:02Z"
    assert manifest["metadataclock_semantics"] == "body_read_completed"
    assert manifest["publication_at"] is None
    assert manifest["availability_policy"] == "first_observed_only"
    assert manifest["candidate_only"] is True
    assert manifest["formal_db_written"] is False
    assert manifest["downstream_eligibility"] == "none"

    metadata = json.loads(raw_meta_path.read_text(encoding="utf-8"))
    assert metadata["capture_id"] == "20261005T010000000000Z-daily-a"
    assert metadata["scheduled_run_id"] == "quick-run-20261005-a"
    assert metadata["request_started_at_utc"] == "2026-10-05T01:00:00Z"
    assert metadata["body_completed_at_utc"] == "2026-10-05T01:00:02Z"
    assert metadata["captured_at_utc"] == metadata["body_completed_at_utc"]
    assert metadata["metadataclock_semantics"] == "body_read_completed"
    assert metadata["sha256"] == hashlib.sha256(payload).hexdigest()
    assert metadata["content_length"] == len(payload)
    assert metadata["raw_file"] == raw_path.name

    assert manifest["source_payload_sha256"] == metadata["sha256"]
    assert manifest["counts"]["raw_tier_rows"] == 17  # type: ignore[index]
    assert manifest["counts"]["symbols"] == 1  # type: ignore[index]
    artifact_hashes = manifest["artifact_hashes"]
    assert isinstance(artifact_hashes, dict)
    assert set(artifact_hashes) == {
        "tdcc_1-5_20260904_tiers.csv",
        "tdcc_1-5_20260904_aggregate.csv",
        "tdcc_1-5_20260904_ready_import.csv",
        "tdcc_1-5_20260904_quarantine.csv",
        "tdcc_1-5_20260904_p0_shadow.json",
    }
    for name, digest in artifact_hashes.items():
        artifact = capture_dir / name
        assert artifact.is_file()
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == digest
    with (capture_dir / "tdcc_1-5_20260904_tiers.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        assert len(list(csv.DictReader(handle))) == 17


def test_dry_run_does_not_call_network_or_create_namespace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    output_root = tmp_path / "canonical-output"
    output_root.mkdir()

    def forbidden_network(*_args: object, **_kwargs: object) -> None:
        pytest.fail("dry-run must not call urlopen")

    monkeypatch.setattr(capture, "urlopen", forbidden_network)
    result = capture.main(
        [
            "--output-root",
            str(output_root),
            "--capture-id",
            "20261005T010000000000Z-dryrun",
            "--scheduled-run-id",
            "quick-run-dry-1",
            "--dry-run",
        ]
    )

    plan = json.loads(capsys.readouterr().out)
    assert result == 0
    assert plan["status"] == "planned"
    assert plan["network_requested"] is False
    assert plan["writes_performed"] is False
    assert plan["endpoint"] == capture.TDCC_URL
    assert not (output_root / "current_observed_market_ownership").exists()
    assert list(output_root.iterdir()) == []


def test_current_capture_rejects_custom_endpoint_before_creating_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_root = tmp_path / "canonical-output"
    output_root.mkdir()

    def forbidden_network(*_args: object, **_kwargs: object) -> None:
        pytest.fail("a custom endpoint must be rejected before network access")

    monkeypatch.setattr(capture, "urlopen", forbidden_network)
    with pytest.raises(SystemExit):
        capture.main(
            [
                "--output-root",
                str(output_root),
                "--capture-id",
                "fixed-endpoint-check",
                "--scheduled-run-id",
                "quick-run-fixed-endpoint",
                "--url",
                "https://example.invalid/tdcc.csv",
            ]
        )
    assert list(output_root.iterdir()) == []


def test_capture_id_path_escape_is_rejected_before_namespace_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_root = tmp_path / "canonical-output"
    output_root.mkdir()
    outside = tmp_path / "escape-target"

    def forbidden_network(*_args: object, **_kwargs: object) -> None:
        pytest.fail("invalid capture_id must be rejected before network access")

    monkeypatch.setattr(capture, "urlopen", forbidden_network)
    with pytest.raises(ValueError):
        capture.main(
            [
                "--output-root",
                str(output_root),
                "--capture-id",
                "../escape-target",
                "--scheduled-run-id",
                "quick-run-escape",
            ]
        )
    assert not outside.exists()
    assert list(output_root.iterdir()) == []


@pytest.mark.parametrize("link_location", ["output_root", "namespace"])
def test_reparse_escape_is_rejected_without_creating_external_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    link_location: str,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    if link_location == "output_root":
        output_root = tmp_path / "linked-output"
        link = output_root
    else:
        output_root = tmp_path / "canonical-output"
        output_root.mkdir()
        link = output_root / "current_observed_market_ownership"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Windows symlink/reparse fixture unavailable: {type(exc).__name__}: {exc}")

    def forbidden_network(*_args: object, **_kwargs: object) -> None:
        pytest.fail("reparse path must be rejected before network access")

    monkeypatch.setattr(capture, "urlopen", forbidden_network)
    with pytest.raises(ValueError):
        capture.main(
            [
                "--output-root",
                str(output_root),
                "--capture-id",
                "20261005T010000000000Z-reparse",
                "--scheduled-run-id",
                "quick-run-reparse",
            ]
        )
    assert list(outside.iterdir()) == []
    assert not (outside / "tdcc").exists()


def test_repeated_capture_id_refuses_overwrite_before_second_http_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    output_root = tmp_path / "canonical-output"
    output_root.mkdir()
    calls = _install_fake_http(monkeypatch, _official_payload())
    argv = [
        "--output-root",
        str(output_root),
        "--capture-id",
        "20261005T010000000000Z-single-write",
        "--scheduled-run-id",
        "quick-run-single-write",
    ]

    assert capture.main(argv) == 0
    capsys.readouterr()
    capture_dir = (
        output_root
        / "current_observed_market_ownership"
        / "tdcc"
        / "20261005T010000000000Z-single-write"
    )
    before = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in capture_dir.iterdir()
        if p.is_file()
    }
    with pytest.raises(FileExistsError):
        capture.main(argv)
    after = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in capture_dir.iterdir()
        if p.is_file()
    }
    assert len(calls) == 1
    assert after == before


def test_exclusive_raw_and_artifact_writers_preserve_existing_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "capture"
    output_dir.mkdir()
    payload = _official_payload()
    completion = datetime(2026, 10, 5, 1, 0, 2, tzinfo=timezone.utc)
    raw_path = output_dir / "tdcc_1-5_raw_20261005T010002Z.csv"
    sentinel = b"do-not-replace"
    raw_path.write_bytes(sentinel)
    _install_fake_http(monkeypatch, payload)
    clock_values = iter(
        [
            datetime(2026, 10, 5, 1, 0, 0, tzinfo=timezone.utc),
            completion,
        ]
    )

    with pytest.raises(FileExistsError):
        capture._capture(
            capture.TDCC_URL,
            output_dir,
            5,
            capture_id="exclusive-check",
            create_only=True,
            clock=lambda: next(clock_values),
        )
    assert raw_path.read_bytes() == sentinel

    json_path = output_dir / "manifest.json"
    json_path.write_bytes(sentinel)
    with pytest.raises(FileExistsError):
        capture._write_json_exclusive(json_path, {"status": "new"})
    assert json_path.read_bytes() == sentinel

    csv_path = output_dir / "tiers.csv"
    csv_path.write_bytes(sentinel)
    with pytest.raises(FileExistsError):
        capture._write_csv_exclusive(csv_path, [{"tier": 1}], fieldnames=("tier",))
    assert csv_path.read_bytes() == sentinel


def test_raw_replay_keeps_legacy_output_names_and_does_not_call_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = _official_payload()
    raw_path = tmp_path / "official.csv"
    raw_path.write_bytes(payload)
    metadata = {
        "captured_at_utc": "2026-09-09T05:03:00Z",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "content_length": len(payload),
    }
    raw_path.with_name(raw_path.name + ".meta.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    repo_root = tmp_path / "legacy-repo"
    repo_root.mkdir()
    legacy_output = repo_root / "output" / "legacy-tdcc"
    monkeypatch.setattr(capture, "PROJECT_ROOT", repo_root)

    def forbidden_network(*_args: object, **_kwargs: object) -> None:
        pytest.fail("raw replay must not call urlopen")

    monkeypatch.setattr(capture, "urlopen", forbidden_network)
    result = capture.main(
        ["--raw-file", str(raw_path), "--output-dir", str(legacy_output)]
    )

    manifest = _manifest_from_stdout(capsys.readouterr().out)
    assert result == 0
    assert (legacy_output / "tdcc_1-5_20260904_manifest.json").is_file()
    assert (legacy_output / "tdcc_1-5_20260904_tiers.csv").is_file()
    assert "capture_id" not in manifest
    assert manifest["publication_at"] is None
    assert manifest["source_payload_sha256"] == metadata["sha256"]
    assert "scheduled_run_id" not in manifest


def test_legacy_manual_mode_rejects_a_scheduled_identity(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="scheduled --output-root"):
        capture.main([
            "--output-dir", str(tmp_path / "output"),
            "--scheduled-run-id", "quick-run-identity",
        ])
    assert not (tmp_path / "output").exists()


def test_scheduled_mode_requires_parent_identity_even_in_dry_run(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="scheduled-run-id"):
        capture.main([
            "--output-root", str(tmp_path),
            "--capture-id", "20261005T010000000000Z-identity",
            "--dry-run",
        ])
    assert list(tmp_path.iterdir()) == []
