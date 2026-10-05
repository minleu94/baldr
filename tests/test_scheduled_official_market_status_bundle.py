from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import os

from scripts.refresh_current_market_status_observation import (
    SourceSpec,
    capture_sources,
)
import scripts.scheduled.run_official_market_status_bundle as bundle_module
from scripts.scheduled.run_official_market_status_bundle import run_bundle
from scripts.scheduled.run_official_market_status_bundle import _run_child


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_payload(payload: dict[str, object]) -> dict[str, object]:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {**payload, "content_sha256": "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()}


def _write_valuation_fixture(
    output_root: Path,
    wrapper_run_id: str,
    *,
    failure_market: str | None = None,
    prior_failure_market: str | None = None,
) -> dict[str, object]:
    valuation_root = output_root / "current_valuation"
    terminal_root = valuation_root / "runs" / wrapper_run_id
    terminal_root.mkdir(parents=True, exist_ok=True)
    terminal_markets: list[dict[str, object]] = []
    cli_markets: list[dict[str, object]] = []
    for market in ("twse", "tpex"):
        prior_failure_attempts: list[dict[str, object]] = []
        if market == prior_failure_market:
            attempt_id = "a1"
            attempt_dir = terminal_root / "markets" / market / "attempts" / attempt_id
            attempt_dir.mkdir(parents=True, exist_ok=True)
            attempt_raw = attempt_dir / "raw_response.bin"
            attempt_raw.write_bytes(f"legacy-{market}-http520".encode("ascii"))
            attempt_raw_digest = _sha256(attempt_raw)
            attempt_timestamp = "2026-10-04T02:00:00+00:00"
            attempt_receipt = _canonical_payload(
                {
                    "schema_version": "official-current-valuation-market-failure.v1",
                    "market": market,
                    "source_id": "tpex.website.peratio_analysis",
                    "attempt_id": attempt_id,
                    "requested_url": "https://www.tpex.org.tw/www/zh-tw/aftertrading/peratio_analysis",
                    "final_url": "https://www.tpex.org.tw/www/zh-tw/aftertrading/peratio_analysis",
                    "request_parameters": {},
                    "response": {"http_status": 520, "headers": {}},
                    "source_date": None,
                    "body_completed_at": attempt_timestamp,
                    "raw_response_path": "raw_response.bin",
                    "raw_response_sha256": attempt_raw_digest,
                    "raw_response_bytes": attempt_raw.stat().st_size,
                    "status": "failed",
                    "diagnostic": "CurrentOfficialValuationError:official response HTTP 520",
                    "formal_pit_eligible": False,
                    "historical_pit_eligible": False,
                }
            )
            attempt_receipt_path = attempt_dir / "receipt.json"
            attempt_receipt_path.write_text(
                json.dumps(attempt_receipt, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            attempt_receipt_digest = hashlib.sha256(
                attempt_receipt_path.read_bytes()
            ).hexdigest()
            prior_failure_attempts.append(
                {
                    "source_id": "tpex.website.peratio_analysis",
                    "requested_url": "https://www.tpex.org.tw/www/zh-tw/aftertrading/peratio_analysis",
                    "final_url": "https://www.tpex.org.tw/www/zh-tw/aftertrading/peratio_analysis",
                    "status": "failed",
                    "raw_response_path": str(attempt_raw.resolve()),
                    "raw_response_sha256": attempt_raw_digest,
                    "raw_response_bytes": attempt_raw.stat().st_size,
                    "receipt_path": str(attempt_receipt_path.resolve()),
                    "receipt_sha256": attempt_receipt_digest,
                    "diagnostic": "CurrentOfficialValuationError:official response HTTP 520",
                    "captured_at": attempt_timestamp,
                }
            )
        if market == failure_market:
            failure_dir = terminal_root / "markets" / market
            failure_dir.mkdir(parents=True, exist_ok=True)
            raw_path = failure_dir / "raw_response.bin"
            raw_path.write_bytes(f"official-{market}-http520".encode("ascii"))
            raw_digest = _sha256(raw_path)
            failure_body: dict[str, object] = {
                "schema_version": "official-current-valuation-market-failure.v1",
                "market": market,
                "raw_response_path": "raw_response.bin",
                "raw_response_sha256": raw_digest,
                "raw_response_bytes": raw_path.stat().st_size,
                "status": "failed",
                "diagnostic": "http_520",
            }
            failure_receipt = _canonical_payload(failure_body)
            failure_path = failure_dir / "receipt.json"
            failure_path.write_text(
                json.dumps(failure_receipt, sort_keys=True), encoding="utf-8"
            )
            failure_sha = hashlib.sha256(failure_path.read_bytes()).hexdigest()
            terminal_markets.append(
                {
                    "market": market,
                    "status": "failed",
                    "source_date": None,
                    "available_at": None,
                    "source_row_count": None,
                    "unique_stock_count": None,
                    "raw_response_path": str(raw_path.resolve()),
                    "raw_response_sha256": raw_digest,
                    "raw_response_bytes": raw_path.stat().st_size,
                    "receipt_path": None,
                    "receipt_sha256": None,
                    "failure_receipt_path": str(failure_path.resolve()),
                    "failure_receipt_sha256": failure_sha,
                    "diagnostic": "http_520",
                    "prior_failure_attempts": prior_failure_attempts,
                }
            )
            cli_markets.append(
                {
                    "market": market,
                    "status": "failed",
                    "source_date": None,
                    "available_at": None,
                    "raw_response_path": str(raw_path.resolve()),
                    "raw_response_sha256": raw_digest,
                    "receipt_path": None,
                    "receipt_sha256": None,
                    "failure_receipt_path": str(failure_path.resolve()),
                    "failure_receipt_sha256": failure_sha,
                    "prior_failure_attempts": prior_failure_attempts,
                }
            )
            continue
        capture_dir = valuation_root / market / "20261002" / f"fixture-{market}"
        capture_dir.mkdir(parents=True, exist_ok=True)
        raw_path = capture_dir / "raw_response.bin"
        raw_path.write_bytes(f"official-{market}-fixture".encode("ascii"))
        raw_digest = _sha256(raw_path)
        market_receipt_body: dict[str, object] = {
            "schema_version": "official-current-valuation-capture.v1",
            "source_authority": market,
            "source_date": "2026-10-02",
            "available_at": "2026-10-04T02:00:00+00:00",
            "run_id": wrapper_run_id,
            "wrapper_run_id": wrapper_run_id,
            "source_row_count": 10,
            "unique_stock_count": 10,
            "raw_response_path": "raw_response.bin",
            "raw_response_sha256": raw_digest,
        }
        market_receipt = _canonical_payload(market_receipt_body)
        receipt_path = capture_dir / "receipt.json"
        receipt_path.write_text(json.dumps(market_receipt, sort_keys=True), encoding="utf-8")
        receipt_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        terminal_markets.append(
            {
                "market": market,
                "status": "captured",
                "source_date": "2026-10-02",
                "available_at": "2026-10-04T02:00:00+00:00",
                "source_row_count": 10,
                "unique_stock_count": 10,
                "raw_response_path": str(raw_path.resolve()),
                "raw_response_sha256": raw_digest,
                "raw_response_bytes": raw_path.stat().st_size,
                "receipt_path": str(receipt_path.resolve()),
                "receipt_sha256": receipt_sha,
                "failure_receipt_path": None,
                "failure_receipt_sha256": None,
                "diagnostic": None,
                "prior_failure_attempts": prior_failure_attempts,
            }
        )
        cli_markets.append(
            {
                "market": market,
                "status": "captured",
                "source_date": "2026-10-02",
                "available_at": "2026-10-04T02:00:00+00:00",
                "raw_response_path": str(raw_path.resolve()),
                "raw_response_sha256": raw_digest,
                "receipt_path": str(receipt_path.resolve()),
                "receipt_sha256": receipt_sha,
                "failure_receipt_path": None,
                "failure_receipt_sha256": None,
                "prior_failure_attempts": prior_failure_attempts,
            }
        )
    terminal_status = "degraded" if failure_market else "captured"
    terminal = _canonical_payload(
        {
            "schema_version": "official-current-valuation-run.v1",
            "status": terminal_status,
            "run_id": wrapper_run_id,
            "wrapper_run_id": wrapper_run_id,
            "started_at": "2026-10-04T02:00:00+00:00",
            "completed_at": "2026-10-04T02:00:01+00:00",
            "formal_pit_eligible": False,
            "historical_pit_eligible": False,
            "markets": terminal_markets,
        }
    )
    terminal_path = terminal_root / "receipt.json"
    terminal_path.write_text(json.dumps(terminal, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return {
        "schema_version": "official-current-valuation-run.v1",
        "status": terminal_status,
        "run_id": wrapper_run_id,
        "wrapper_run_id": wrapper_run_id,
        "receipt_path": str(terminal_path.resolve()),
        "receipt_sha256": hashlib.sha256(terminal_path.read_bytes()).hexdigest(),
        "formal_pit_eligible": False,
        "historical_pit_eligible": False,
        "markets": cli_markets,
    }


def _fake_runner(
    output_root: Path,
    *,
    history_status: str = "published",
    history_return_code: int = 0,
    current_partial_failure: bool = False,
    valuation_return_code: int = 0,
    valuation_failure_market: str | None = None,
    valuation_prior_failure_market: str | None = None,
    tamper_prior_failure: bool = False,
):
    calls: list[list[str]] = []
    history_payload = {
        "status": history_status,
        "as_of_date": "2026-10-04",
        "publication_id": "history-run-1",
    }

    def runner(command, **kwargs):
        calls.append(command)
        if command[1].endswith("run_official_market_event_backfill.py"):
            manifest_path = output_root / "release_v4" / "official_market_events" / "fixture" / "manifest.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest = {"manifest_hash": "manifest-hash-1", "canonical_events": {"path": "events.json", "file_hash": "sha256:fixture"}}
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            manifest_sha = _sha256(manifest_path)
            status_root = output_root / "scheduled" / "official_market_events"
            status_root.mkdir(parents=True, exist_ok=True)
            history_payload["manifest_path"] = str(manifest_path.resolve())
            history_payload["manifest_hash"] = manifest["manifest_hash"]
            history_payload["manifest_file_hash"] = manifest_sha
            (status_root / "20261004T000000+0000-history.json").write_text(
                json.dumps(history_payload, ensure_ascii=False),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(
                command,
                history_return_code,
                stdout="" if history_return_code else json.dumps(history_payload),
                stderr=json.dumps(history_payload) if history_return_code else "",
            )

        if command[1].endswith("capture_current_official_valuation.py"):
            output_root_arg = Path(command[command.index("--output-root") + 1])
            wrapper_id = command[command.index("--wrapper-run-id") + 1]
            valuation_payload = _write_valuation_fixture(
                output_root_arg,
                wrapper_id,
                failure_market=valuation_failure_market,
                prior_failure_market=valuation_prior_failure_market,
            )
            if tamper_prior_failure:
                attempt_raw = next(
                    (
                        output_root_arg
                        / "current_valuation"
                        / "runs"
                        / wrapper_id
                        / "markets"
                        / "tpex"
                    ).glob("attempts/*/raw_response.bin")
                )
                attempt_raw.write_bytes(b"tampered prior official response")
            return subprocess.CompletedProcess(
                command,
                valuation_return_code,
                stdout=json.dumps(valuation_payload, ensure_ascii=False, indent=2),
                stderr="",
            )

        output_dir = Path(command[command.index("--output-dir") + 1])
        body = json.dumps(
            [{"證券代號": "2323", "公司名稱": "fixture"}],
            ensure_ascii=False,
        ).encode("utf-8")
        spec = SourceSpec(
            "fixture.roster",
            "https://official.example.test/roster",
            "current_roster",
            "twse",
        )

        def fetcher(url, *, timeout, method="GET", params=None):
            status_code = 500 if current_partial_failure else 200
            return (
                body,
                status_code,
                "application/json",
                url,
                datetime(2026, 10, 4, tzinfo=timezone.utc),
                {"content-length": str(len(body))},
            )

        snapshot, run_dir = capture_sources(
            output_dir=output_dir,
            specs=(spec,),
            fetcher=fetcher,
        )
        pointer_path = output_dir / "current_market_status_pointer.json"
        summary = {
            "status": (
                "partial_failure"
                if snapshot["partial_failure"]
                else "current_market_status_captured"
            ),
            "run_id": snapshot["run_id"],
            "run_dir": str(run_dir),
            "snapshot_path": str(run_dir / "snapshot.json"),
            "pointer_path": str(pointer_path),
            "source_count": snapshot["source_count"],
            "successful_source_count": snapshot["successful_source_count"],
            "security_count": len(snapshot["securities"]),
            "scope": snapshot["scope"],
            "pit_eligible": snapshot["pit_eligible"],
            "partial_failure": snapshot["partial_failure"],
        }
        return subprocess.CompletedProcess(
            command,
            2 if current_partial_failure else 0,
            stdout=json.dumps(summary),
            stderr="",
        )

    return runner, calls


def test_current_capture_runs_and_bundle_fails_when_history_fails(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "canonical-output"
    (output_root / "scheduled" / "official_market_events").mkdir(parents=True)
    old_latest = output_root / "scheduled" / "official_market_events" / "latest_status.json"
    old_latest.write_text('{"keep":"historical pointer"}', encoding="utf-8")
    runner, calls = _fake_runner(
        output_root,
        history_status="failed",
        history_return_code=2,
    )

    receipt, receipt_path = run_bundle(
        output_root=output_root,
        runner=runner,
        wrapper_run_id="wrapper-test-1",
    )

    assert len(calls) == 3
    assert calls[0][1].endswith("run_official_market_event_backfill.py")
    assert calls[1][1].endswith("refresh_current_market_status_observation.py")
    assert calls[2][1].endswith("capture_current_official_valuation.py")
    assert receipt["overall_status"] == "failed"
    historical = receipt["historical_official_market_events"]
    current = receipt["current_market_status_observation"]
    valuation = receipt["current_official_valuation"]
    assert historical["return_code"] == 2
    assert historical["wrapper_run_id"] == "wrapper-test-1"
    assert historical["receipt"]["path"].endswith("20261004T000000+0000-history.json")
    assert current["return_code"] == 0
    assert current["wrapper_run_id"] == "wrapper-test-1"
    assert current["capture_evidence"]["pointer_validation"] == "verified"
    assert current["capture_evidence"]["pointer_matches_child_run"] is True
    assert valuation["return_code"] == 0
    assert valuation["capture_evidence"]["validation"] == "verified"
    assert valuation["capture_evidence"]["wrapper_run_id"] == "wrapper-test-1"
    assert old_latest.read_text(encoding="utf-8") == '{"keep":"historical pointer"}'
    stored = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert stored["wrapper_run_id"] == "wrapper-test-1"
    pointer = json.loads(
        (output_root / "scheduled" / "official_market_events_wrapper" / "latest_status.json").read_text(encoding="utf-8")
    )
    assert pointer["status_sha256"] == _sha256(receipt_path)


def test_wrapper_fails_when_current_capture_is_partial_even_if_history_passes(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "canonical-output"
    runner, _ = _fake_runner(
        output_root,
        history_status="published",
        current_partial_failure=True,
    )

    receipt, _ = run_bundle(
        output_root=output_root,
        runner=runner,
        wrapper_run_id="wrapper-test-2",
    )

    assert receipt["historical_official_market_events"]["return_code"] == 0
    assert receipt["current_market_status_observation"]["return_code"] == 2
    assert receipt["current_market_status_observation"]["status"] == "partial_failure"
    assert receipt["overall_status"] == "failed"
    assert receipt["current_official_valuation"]["return_code"] == 0


def test_wrapper_succeeds_only_when_both_children_publish_complete_status(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "canonical-output"
    runner, _ = _fake_runner(
        output_root,
        valuation_prior_failure_market="tpex",
    )

    receipt, _ = run_bundle(
        output_root=output_root,
        runner=runner,
        wrapper_run_id="wrapper-test-3",
    )

    assert receipt["overall_status"] == "succeeded"
    assert receipt["overall_return_code"] == 0
    assert receipt["historical_official_market_events"]["status"] == "published"
    assert receipt["current_market_status_observation"]["status"] == "current_market_status_captured"
    assert receipt["current_market_status_observation"]["capture_evidence"]["snapshot_sha256"].startswith("sha256:")
    valuation = receipt["current_official_valuation"]
    assert valuation["capture_evidence"]["terminal_receipt_sha256"].startswith("sha256:")
    assert {row["market"] for row in valuation["capture_evidence"]["markets"]} == {"twse", "tpex"}
    tpex = next(
        row for row in valuation["capture_evidence"]["markets"] if row["market"] == "tpex"
    )
    assert tpex["prior_failure_attempts"][0]["source_id"] == "tpex.website.peratio_analysis"
    assert Path(tpex["prior_failure_attempts"][0]["raw_response_path"]).is_file()


def test_wrapper_rejects_tampered_prior_valuation_source_attempt(tmp_path: Path) -> None:
    output_root = tmp_path / "canonical-output"
    runner, _ = _fake_runner(
        output_root,
        valuation_prior_failure_market="tpex",
        tamper_prior_failure=True,
    )

    receipt, _ = run_bundle(
        output_root=output_root,
        runner=runner,
        wrapper_run_id="w1",
    )

    valuation = receipt["current_official_valuation"]
    assert valuation["capture_evidence"]["validation"] == "invalid_or_missing"
    assert "prior_failure_raw_or_receipt_hash_mismatch" in valuation["capture_evidence"]["validation_error"]
    assert receipt["overall_status"] == "failed"


def test_valuation_child_failure_is_recorded_and_makes_bundle_fail(tmp_path: Path) -> None:
    output_root = tmp_path / "canonical-output"
    runner, calls = _fake_runner(
        output_root,
        valuation_return_code=2,
        valuation_failure_market="tpex",
    )

    receipt, _ = run_bundle(
        output_root=output_root,
        runner=runner,
        wrapper_run_id="wrapper-test-4",
    )

    assert len(calls) == 3
    assert receipt["current_official_valuation"]["return_code"] == 2
    assert receipt["current_official_valuation"]["status"] == "degraded"
    assert receipt["current_official_valuation"]["capture_evidence"]["validation"] == "verified"
    assert any(
        row["status"] == "failed"
        and row["raw_response_path"] is not None
        and row["raw_response_sha256"] is not None
        for row in receipt["current_official_valuation"]["capture_evidence"]["markets"]
    )
    assert receipt["overall_status"] == "failed"


def test_wrapper_rejects_unsafe_run_identifier_before_launch(tmp_path: Path) -> None:
    runner, calls = _fake_runner(tmp_path / "output")
    try:
        run_bundle(output_root=tmp_path / "output", runner=runner, wrapper_run_id="../escape")
    except ValueError as error:
        assert "bounded ASCII" in str(error)
    else:
        raise AssertionError("unsafe wrapper run identifier was accepted")
    assert calls == []


def test_wrapper_rejects_existing_run_id_before_children_and_preserves_receipts(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    first_runner, _ = _fake_runner(output_root)
    first_receipt, receipt_path = run_bundle(
        output_root=output_root,
        runner=first_runner,
        wrapper_run_id="immutable-run-id",
    )
    assert first_receipt["wrapper_run_id"] == "immutable-run-id"
    original_receipt = receipt_path.read_bytes()
    pointer_path = (
        output_root
        / "scheduled"
        / "official_market_events_wrapper"
        / "latest_status.json"
    )
    original_pointer = pointer_path.read_bytes()
    original_receipt_sha = _sha256(receipt_path)

    second_runner, second_calls = _fake_runner(output_root)
    try:
        run_bundle(
            output_root=output_root,
            runner=second_runner,
            wrapper_run_id="immutable-run-id",
        )
    except FileExistsError:
        pass
    else:
        raise AssertionError("an existing wrapper run id was accepted")

    assert second_calls == []
    assert receipt_path.read_bytes() == original_receipt
    assert _sha256(receipt_path) == original_receipt_sha
    assert pointer_path.read_bytes() == original_pointer


def test_wrapper_final_receipt_create_only_rejects_publish_race(
    tmp_path: Path, monkeypatch
) -> None:
    output_root = tmp_path / "output"
    runner, calls = _fake_runner(output_root)
    run_path = (
        output_root
        / "scheduled"
        / "official_market_events_wrapper"
        / "runs"
        / "publish-race.json"
    )
    pointer_path = (
        output_root
        / "scheduled"
        / "official_market_events_wrapper"
        / "latest_status.json"
    )
    pointer_path.parent.mkdir(parents=True)
    pointer_before = b'{"preserve":"latest pointer"}'
    pointer_path.write_bytes(pointer_before)
    raced_receipt = b'{"preserve":"concurrent receipt"}'
    real_create_only_writer = bundle_module._write_json_create_only

    def create_collision_then_publish(path: Path, payload: object) -> None:
        if path == run_path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raced_receipt)
        real_create_only_writer(path, payload)

    monkeypatch.setattr(
        bundle_module, "_write_json_create_only", create_collision_then_publish
    )
    try:
        run_bundle(
            output_root=output_root,
            runner=runner,
            wrapper_run_id="publish-race",
        )
    except FileExistsError:
        pass
    else:
        raise AssertionError("a run receipt created after preflight was overwritten")

    assert len(calls) == 3
    assert run_path.read_bytes() == raced_receipt
    assert pointer_path.read_bytes() == pointer_before


def test_child_stdout_hash_is_over_original_binary_capture() -> None:
    stdout = b'{"status":"captured"}\n\xff'
    stderr = b'network warning\n\xfe'

    def runner(command, **kwargs):
        assert kwargs["capture_output"] is True
        assert "text" not in kwargs
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr=stderr)

    child = _run_child(
        ["fixture-child"],
        runner=runner,
        env=os.environ,
    )

    assert child["status"] == "captured"
    assert child["stdout_sha256"] == "sha256:" + hashlib.sha256(stdout).hexdigest()
    assert child["stdout_bytes"] == len(stdout)
    assert child["stderr_sha256"] == "sha256:" + hashlib.sha256(stderr).hexdigest()
    assert child["stderr_bytes"] == len(stderr)
    assert child["stderr_tail"].endswith("�")
