"""A03 個人模型 daily CLI 的 request pin 與隔離執行邊界。"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import stat
import sys
import tempfile
from collections.abc import Iterator
from types import SimpleNamespace

import pytest

from app_module.recommendation.personal_natural_outcome_daily import (
    PersonalNaturalOutcomeDailyError,
    run_personal_model_daily,
)
from scripts.scheduled import run_personal_model_daily as daily_cli
from tests import test_personal_recommendation_outcome_daily as outcome_fixture
import app_module.recommendation.personal_natural_outcome_daily as daily_module
import app_module.recommendation.personal_prediction_capture as capture_module


def _write_request(tmp_path: Path, value: object | None = None) -> tuple[Path, str]:
    request_path = tmp_path / "request.json"
    body = (
        {"schema_version": "personal-model-daily-request.v1"}
        if value is None
        else value
    )
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")
    request_path.write_bytes(raw)
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    return request_path, digest


@pytest.mark.parametrize("mode", ["success", "cancel", "timeout"])
def test_fixed_producer_port_uses_same_runtime_and_stops_its_actual_child(
    qa_tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str,
) -> None:
    """實際啟動隔離 child 驗 process 控制；此 fixture 不執行模型或正式 producer。"""
    real_popen = subprocess.Popen
    children = []
    captured = {}
    source = (
        "import os,sys,json; print(json.dumps({'ok':True,'actual_pid':os.getpid(),'prefix':sys.prefix}))"
        if mode == "success" else "import time; time.sleep(30)"
    )

    def synthetic_child(command, **kwargs):
        captured["command"] = command
        process = real_popen([command[0], "-c", source], **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr(daily_module.subprocess, "Popen", synthetic_child)
    process_receipt = {}
    if mode == "success":
        result = daily_module._daily_produce(["--result-id", "synthetic"], 5, lambda: False, process_receipt)
        assert result["receipt"]["prefix"] == sys.prefix
        assert result["exit_code"] == 0
        if os.name == "nt":
            assert result["launcher_pid"] == result["receipt"]["actual_pid"]
    else:
        expected = InterruptedError if mode == "cancel" else TimeoutError
        with pytest.raises(expected):
            daily_module._daily_produce([], 1, lambda: mode == "cancel", process_receipt)
        assert children[0].poll() is not None
        assert process_receipt["exit_code"] is not None
    assert captured["command"][1:3] == ["-m", "scripts.run_personalization_recommendation"]
    assert process_receipt["status"] == "exited"


@pytest.mark.parametrize("changed", [None, "version", "probability_only", "future_model", "future_model_clock", "wrong_price_basis"])
def test_gross_saved_projection_distinguishes_versions_and_never_derives_probability(
    qa_tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: str | None,
) -> None:
    """純結構 adapter oracle；canonical 真保存 ingress 由相鄰 capture tests 驗證。"""
    root = qa_tmp_path / "gross-model"
    root.mkdir()
    learning = qa_tmp_path / "learning"
    learning.mkdir()
    schema = (("momentum", "bp", "v1"),)
    digest = "sha256:" + "a" * 64
    contract = SimpleNamespace(
        artifact_root=str(root), lineage_path=str(root / "lineage.json"),
        contract_hash=digest, contract_version="personal-h20-gross.v1",
        adapter_version="recommendation-calibration-return-head.v1",
        target="absolute_forward_stock_return_bp", horizon_trading_days=20,
        price_basis="close_to_close_event_date", cost_basis="no_cost_gross",
        candidate_id="capture-candidate-version", model_id="persisted-model-id",
        model_version="metadata-model-version", dataset_id="dataset", dataset_hash=digest,
        model_family="family", feature_registry_hash=digest, label_registry_hash=digest,
        manifest_hash=digest, artifact_hash=digest, lineage_hash=digest,
        training_source_hash=digest, training_pit_hash=digest, training_as_of="2025-01-01",
        feature_schema=schema, installed_library_versions={"synthetic": "fixture"},
    )
    manifest = {name: getattr(contract, name) for name in (
        "model_id", "dataset_id", "model_family", "feature_registry_hash", "label_registry_hash",
        "manifest_hash", "artifact_hash", "training_as_of", "feature_schema",
    )}
    manifest["library_versions"] = dict(contract.installed_library_versions)
    manifest["created_at"] = "2025-01-01T00:00:00+00:00"
    candidate = {name: getattr(contract, name) for name in (
        "model_id", "candidate_id", "model_version", "dataset_id", "dataset_hash", "model_family",
        "feature_registry_hash", "label_registry_hash", "manifest_hash", "artifact_hash", "training_as_of",
    )}
    candidate.update(schema_version="recommendation-calibration-candidate.v1", horizon_trading_days=20,
                     return_basis=contract.price_basis, feature_schema=[list(row) for row in schema],
                     feature_names=[row[0] for row in schema], shadow_only=True, production_eligible=False,
                     production_action_allowed=False, candidate_frozen_at=manifest["created_at"],
                     label_contract_id="recommendation-absolute-labels-v1", target_definitions={
                         "upside": "absolute forward stock return over 20 trading days > 0 bp"})
    if changed == "future_model_clock":
        manifest["created_at"] = "2025-05-01T09:00:00+00:00"
        candidate["candidate_frozen_at"] = manifest["created_at"]
    if changed == "wrong_price_basis":
        candidate["return_basis"] = "next_open_after_cost"
    lineage = {name: getattr(contract, name) for name in (
        "training_source_hash", "training_pit_hash", "training_as_of", "feature_registry_hash",
    )}
    lineage.update(feature_schema=[list(row) for row in schema], return_basis=contract.price_basis,
                   training_context={"semantics": "decision_time", "decision_time_eligible": True})
    for filename, value, field in (
        ("manifest.json", manifest, "manifest_raw_sha256"),
        ("candidate.json", candidate, "candidate_raw_sha256"),
        ("lineage.json", lineage, "lineage_raw_sha256"),
    ):
        raw = json.dumps(value).encode("utf-8")
        (root / filename).write_bytes(raw)
        setattr(contract, field, "sha256:" + hashlib.sha256(raw).hexdigest())
    training = {"status": "verified", "manifest_hash": contract.lineage_hash,
                "training_source_hash": digest, "training_pit_hash": digest,
                "dataset_id": contract.dataset_id, "feature_registry_hash": digest}
    receipt = {"training_provenance": training, "inference_provenance": {
        "feature_registry_hash": digest, "feature_transform_contract": {"canonical_schema": schema},
    }}
    receipt_path = learning / "original.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    row = {"status": "active_candidate", "model_version": contract.candidate_id,
           "ranking_score_bp": -1250, "calibrated_probability_bp": 9000,
           "after_cost_profit_probability_bp": 8000}
    if changed == "version":
        row["model_version"] = contract.model_version
    if changed == "probability_only":
        row.pop("ranking_score_bp")
    if changed == "future_model":
        contract.training_as_of = "2025-06-01"
    capture = {"capture_id": digest, "result_id": "synthetic-original", "decision_at": "2025-05-01T08:00:00+00:00", "receipt_binding": {
        "path": str(receipt_path), "learning_root": str(learning), "decision_date": "2025-05-01",
        "candidate_identity": {"candidate_id": contract.candidate_id, "candidate_root": str(root),
            "candidate_manifest_hash": digest, "candidate_artifact_hash": digest, "dataset_hash": digest},
    }, "delivered_rows": [{"stock_code": "SYNTHETIC", "projection": row}]}
    monkeypatch.setattr(capture_module, "read_personal_prediction_capture", lambda *a, **k: capture)
    before = {path: path.read_bytes() for path in root.iterdir()}
    result = capture_module.project_personal_capture_h20_gross(
        qa_tmp_path / "capture.json", None, qa_tmp_path,
        contract=contract, lineage_reader=lambda *a, **k: SimpleNamespace(manifest_hash=digest, payload=lineage),
    )
    if changed is None:
        assert result["status"] == "h20_gross_available"
        assert result["rows"][0]["predicted_gross_return_bp"] == -1250
        assert result["capture_model_version"] != result["model_version"]
    else:
        assert result["status"] == "h20_gross_unavailable"
        assert result["rows"] == []
        assert result["blockers"]
    assert result["formal_eligible"] is False
    assert result["natural_evidence_eligible"] is False
    assert {path: path.read_bytes() for path in root.iterdir()} == before


def _argv(request_path: Path, digest: str, receipt_root: Path) -> list[str]:
    return [
        "--request-json",
        str(request_path),
        "--request-sha256",
        digest,
        "--receipt-root",
        str(receipt_root),
    ]


def _stdout_receipt(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    output = capsys.readouterr().out
    assert output.endswith("\n")
    return json.loads(output)


def _daily_request(case: dict[str, object], *, isolated_root: Path | None = None) -> dict[str, object]:
    capture_path = Path(case["capture_path"])
    market_db = Path(case["market_db"])
    calendar_root = Path(case["calendar_root"])
    source_paths = [capture_path, market_db]
    if calendar_root.is_file():
        source_paths.append(calendar_root)
    elif calendar_root.is_dir():
        source_paths.extend(
            path for path in calendar_root.rglob("*") if path.is_file()
        )
    source_pins = []
    seen: set[str] = set()
    for path in source_paths:
        absolute = path.absolute()
        normalized = os.path.normcase(str(absolute))
        if normalized in seen:
            continue
        seen.add(normalized)
        source_pins.append(
            {
                "path": str(absolute),
                "sha256": "sha256:" + hashlib.sha256(absolute.read_bytes()).hexdigest(),
            }
        )
    return {
        "schema_version": "personal-model-daily-request.v1",
        "canonical_recommendation_output_root": str(
            Path(case["canonical_root"]).absolute()
        ),
        "personal_capture_root": str(Path(case["personal_root"]).absolute()),
        "isolated_outcome_root": str(
            (isolated_root or Path(case["isolated_root"])).absolute()
        ),
        "market_source_db": str(market_db.absolute()),
        "calendar_cache_path": str(calendar_root.absolute()),
        "evaluation_at": case["evaluation_at"].isoformat(),
        "result_ids": [],
        "capture_paths": [str(capture_path.absolute())],
        "source_pins": source_pins,
    }


def _invoke_cli_process(
    request_path: Path, digest: str, receipt_root: Path
) -> tuple[int, int, dict[str, object], str]:
    cli_path = str(Path(daily_cli.__file__).resolve())
    wrapper = (
        "import os,runpy,sys;"
        "print('A03_PROCESS_PID='+str(os.getpid()),file=sys.stderr,flush=True);"
        "script,*args=sys.argv[1:];"
        "sys.argv=[script,*args];"
        "runpy.run_path(script,run_name='__main__')"
    )
    command = [
        sys.executable,
        "-c",
        wrapper,
        cli_path,
        *_argv(request_path, digest, receipt_root),
    ]
    with subprocess.Popen(
        command,
        cwd=Path(daily_cli.ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    ) as process:
        stdout, stderr = process.communicate(timeout=90)
        return_code = process.returncode
    assert return_code is not None
    try:
        receipt = json.loads(stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(f"CLI stdout 不是唯一 JSON receipt；stderr={stderr!r}，stdout={stdout!r}")
        raise AssertionError from exc
    assert isinstance(receipt, dict)
    marker = next(
        (line.partition("=")[2] for line in stderr.splitlines() if line.startswith("A03_PROCESS_PID=")),
        None,
    )
    assert marker is not None, stderr
    process_id = int(marker)
    return process_id, return_code, receipt, stderr


@pytest.fixture
def qa_tmp_path() -> Iterator[Path]:
    """使用短 workspace QA 路徑保存 synthetic fixtures 與 SQLite 讀取痕跡。"""

    parent = Path(daily_cli.ROOT).parents[2] / "output" / "qa" / "a03"
    parent.mkdir(parents=True, exist_ok=True)
    yield Path(tempfile.mkdtemp(prefix="a03-", dir=parent))


def test_request_bytes_are_pinned_before_the_api_is_called(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    request_path, digest = _write_request(tmp_path, {"request": "original"})
    request_path.write_text('{"request":"tampered"}', encoding="utf-8")
    called = False

    def should_not_run(**_kwargs: object) -> dict[str, object]:
        nonlocal called
        called = True
        raise AssertionError("request bytes 未通過 pin 檢查")

    monkeypatch.setattr(daily_cli, "_load_api_runner", lambda: should_not_run)

    exit_code = daily_cli.main(_argv(request_path, digest, tmp_path / "receipts"))

    assert exit_code == 2
    assert not called
    assert _stdout_receipt(capsys)["status"] == "failed"
    assert not (tmp_path / "receipts").exists()


def test_request_file_must_be_regular_and_within_the_size_limit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (daily_cli.MAX_REQUEST_BYTES + 1))
    digest = "sha256:" + hashlib.sha256(oversized.read_bytes()).hexdigest()

    exit_code = daily_cli.main(_argv(oversized, digest, tmp_path / "receipts"))

    assert exit_code == 2
    result = _stdout_receipt(capsys)
    assert result["status"] == "failed"
    assert result["error_type"] == "_RequestError"
    assert not (tmp_path / "receipts").exists()


def test_request_json_must_have_a_json_object_top_level(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request_path, digest = _write_request(tmp_path, ["not", "an", "object"])
    monkeypatch.setattr(
        daily_cli,
        "_load_api_runner",
        lambda: pytest.fail("非 object request 不得呼叫 daily API"),
    )

    exit_code = daily_cli.main(_argv(request_path, digest, tmp_path / "receipts"))

    assert exit_code == 2
    assert _stdout_receipt(capsys)["status"] == "failed"


@pytest.mark.parametrize(
    ("status", "expected_exit"),
    [
        ("completed", 0),
        ("completed_with_pending", 0),
        ("completed_with_unknown", 2),
        ("failed", 2),
        ("cancelled", 130),
    ],
)
def test_receipt_status_maps_to_scheduled_task_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    status: str,
    expected_exit: int,
) -> None:
    request = {"schema_version": "personal-model-daily-request.v1"}
    request_path, digest = _write_request(tmp_path, request)
    receipt = {"status": status, "receipt_path": str(tmp_path / "receipt.json")}
    observed: dict[str, object] = {}

    def return_receipt(**kwargs: object) -> dict[str, object]:
        observed.update(kwargs)
        return receipt

    monkeypatch.setattr(daily_cli, "_load_api_runner", lambda: return_receipt)

    exit_code = daily_cli.main(_argv(request_path, digest, tmp_path / "receipts"))

    assert exit_code == expected_exit
    assert observed["request"] == request
    assert observed["receipt_root"] == tmp_path / "receipts"
    assert _stdout_receipt(capsys) == receipt


def test_relative_request_and_receipt_paths_fail_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request_path, digest = _write_request(tmp_path)

    exit_code = daily_cli.main(
        [
            "--request-json",
            request_path.name,
            "--request-sha256",
            digest,
            "--receipt-root",
            str(tmp_path / "receipts"),
        ]
    )

    assert exit_code == 2
    assert _stdout_receipt(capsys)["status"] == "failed"


def test_absolute_path_with_parent_traversal_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request_path, digest = _write_request(tmp_path)
    nested = tmp_path / "nested"
    nested.mkdir()
    traversal_path = nested / ".." / request_path.name

    exit_code = daily_cli.main(
        _argv(traversal_path, digest, tmp_path / "receipts")
    )

    assert exit_code == 2
    assert _stdout_receipt(capsys)["status"] == "failed"


def test_help_only_displays_usage_and_creates_no_receipt_root(tmp_path: Path) -> None:
    receipt_root = tmp_path / "must-not-be-created"
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(daily_cli.__file__).resolve()),
            "--help",
            "--receipt-root",
            str(receipt_root),
        ],
        cwd=Path(daily_cli.ROOT),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert completed.returncode == 0
    assert "--request-json" in completed.stdout
    assert not receipt_root.exists()


def test_missing_cli_arguments_emit_json_failure_on_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as caught:
        daily_cli.main([])

    assert caught.value.code == 2
    result = _stdout_receipt(capsys)
    assert result["status"] == "failed"
    assert result["error_type"] == "CLIArgumentError"


@pytest.mark.parametrize(
    ("mode", "attributes"),
    [
        (stat.S_IFLNK | 0o777, 0),
        (stat.S_IFREG | 0o600, daily_cli._REPARSE_POINT),
    ],
)
def test_request_link_metadata_is_rejected_before_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mode: int,
    attributes: int,
) -> None:
    request_path, digest = _write_request(tmp_path)
    real_lstat = Path.lstat
    link_metadata = SimpleNamespace(
        st_mode=mode,
        st_file_attributes=attributes,
        st_size=request_path.stat().st_size,
        st_dev=request_path.stat().st_dev,
        st_ino=request_path.stat().st_ino,
        st_mtime_ns=request_path.stat().st_mtime_ns,
    )

    def lstat_with_link_metadata(path: Path):
        if path == request_path:
            return link_metadata
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", lstat_with_link_metadata)
    monkeypatch.setattr(
        daily_cli,
        "_load_api_runner",
        lambda: pytest.fail("request link metadata 不得呼叫 daily API"),
    )

    exit_code = daily_cli.main(_argv(request_path, digest, tmp_path / "receipts"))

    assert exit_code == 2
    assert _stdout_receipt(capsys)["status"] == "failed"


def test_request_ancestor_reparse_metadata_is_rejected_before_open(
    qa_tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request_path, digest = _write_request(qa_tmp_path)
    real_lstat = Path.lstat
    parent_metadata = SimpleNamespace(
        st_mode=stat.S_IFDIR | 0o700,
        st_file_attributes=daily_cli._REPARSE_POINT,
        st_size=0,
        st_nlink=1,
        st_dev=1,
        st_ino=1,
        st_mtime_ns=0,
    )

    def lstat_with_reparse_parent(path: Path):
        if path == request_path.parent:
            return parent_metadata
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", lstat_with_reparse_parent)
    monkeypatch.setattr(
        daily_cli,
        "_load_api_runner",
        lambda: pytest.fail("request ancestor reparse point 不得呼叫 daily API"),
    )

    exit_code = daily_cli.main(
        _argv(request_path, digest, qa_tmp_path / "receipts")
    )

    assert exit_code == 2
    assert _stdout_receipt(capsys)["status"] == "failed"


def test_request_hard_link_is_rejected_by_link_count(
    qa_tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request_path, digest = _write_request(qa_tmp_path)
    hardlink_path = qa_tmp_path / "request-hardlink.json"
    try:
        os.link(request_path, hardlink_path)
    except OSError as exc:
        pytest.skip(f"此檔案系統不支援建立硬連結：{type(exc).__name__}")
    monkeypatch.setattr(
        daily_cli,
        "_load_api_runner",
        lambda: pytest.fail("hard-linked request 不得呼叫 daily API"),
    )

    exit_code = daily_cli.main(
        _argv(hardlink_path, digest, qa_tmp_path / "receipts")
    )

    assert exit_code == 2
    assert _stdout_receipt(capsys)["status"] == "failed"


def test_tampered_source_pin_fails_before_any_receipt_or_outcome_write(
    qa_tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    case = outcome_fixture._case(qa_tmp_path)
    request_path, digest = _write_request(qa_tmp_path, _daily_request(case))
    market_db = Path(case["market_db"])
    original = market_db.read_bytes()
    market_db.write_bytes(original + b"source pin tamper")
    receipt_root = qa_tmp_path / "daily-receipts"

    exit_code = daily_cli.main(_argv(request_path, digest, receipt_root))

    result = _stdout_receipt(capsys)
    assert exit_code == 2
    assert result["status"] == "failed"
    assert "pin" in str(result.get("message", "")).lower()
    assert not receipt_root.exists()
    assert not (Path(case["isolated_root"]) / "personal_natural_outcomes").exists()


@pytest.mark.parametrize("overlap", ["isolated_outcome_root", "receipt_root"])
def test_preflight_rejects_output_roots_that_overlap_inputs(
    qa_tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    overlap: str,
) -> None:
    case = outcome_fixture._case(qa_tmp_path)
    canonical_root = Path(case["canonical_root"])
    canonical_db = canonical_root / "recommendation" / "runs" / "recommendation_runs.db"
    canonical_bytes = canonical_db.read_bytes()
    request = _daily_request(
        case,
        isolated_root=canonical_root
        if overlap == "isolated_outcome_root"
        else None,
    )
    request_path, digest = _write_request(qa_tmp_path, request)
    receipt_root = (
        canonical_root if overlap == "receipt_root" else qa_tmp_path / "daily-receipts"
    )

    exit_code = daily_cli.main(_argv(request_path, digest, receipt_root))

    result = _stdout_receipt(capsys)
    assert exit_code == 2
    assert result["status"] == "failed"
    assert canonical_db.read_bytes() == canonical_bytes
    if overlap == "isolated_outcome_root":
        assert not (canonical_root / "personal_natural_outcomes").exists()
        assert not (qa_tmp_path / "daily-receipts").exists()
    else:
        assert not (canonical_root / "runs").exists()


def test_cancelled_api_attempt_publishes_an_immutable_cancellation_receipt(
    qa_tmp_path: Path,
) -> None:
    case = outcome_fixture._case(qa_tmp_path)
    request = _daily_request(case)

    result = run_personal_model_daily(
        request=request,
        receipt_root=qa_tmp_path / "daily-receipts",
        cancelled=lambda: True,
    )

    assert result["status"] == "cancelled"
    assert result["reason"] == "personal_daily_cancelled"
    assert result["receipt_path"]
    receipt_path = Path(result["receipt_path"])
    assert receipt_path.parent.name == "attempts"
    stored = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert stored["payload_sha256"] == result["payload_sha256"]
    assert stored["process_identity"] == result["process_identity"]
    assert stored["global_natural_evidence_created"] is False
    assert stored["promotion_credit_created"] is False
    assert not Path(case["isolated_root"], "personal_natural_outcomes").exists()


def test_missing_gross_contract_keeps_gross_projection_unavailable(
    qa_tmp_path: Path,
) -> None:
    case = outcome_fixture._case(qa_tmp_path)
    result = run_personal_model_daily(
        request=_daily_request(case),
        receipt_root=qa_tmp_path / "daily-receipts",
    )

    assert result["status"] in {"completed", "completed_with_pending", "completed_with_unknown"}
    prediction = result["predictions"][0]
    gross_view = prediction["gross_view"]  # type: ignore[index]
    assert gross_view["status"] == "h20_gross_unavailable"  # type: ignore[index]
    assert gross_view["rows"] == []  # type: ignore[index]
    assert "controlled_gross_contract_not_injected" in gross_view["blockers"]  # type: ignore[index]
    assert result["global_natural_evidence_created"] is False
    assert result["promotion_credit_created"] is False


def test_gross_contract_hash_mismatch_fails_preflight_without_receipt(
    qa_tmp_path: Path,
) -> None:
    case = outcome_fixture._case(qa_tmp_path)
    request = _daily_request(case)
    request["gross_model_contract_hash"] = "sha256:" + "1" * 64
    receipt_root = qa_tmp_path / "daily-receipts"

    with pytest.raises(PersonalNaturalOutcomeDailyError, match="gross contract hash"):
        run_personal_model_daily(
            request=request,
            receipt_root=receipt_root,
            gross_contract=SimpleNamespace(contract_hash="sha256:" + "2" * 64),
        )

    assert not receipt_root.exists()


def _generation_argv(
    case: dict[str, object],
    qa_tmp_path: Path,
    *,
    data_root: Path | None = None,
    include_fundamental_root: bool = True,
) -> tuple[list[str], Path]:
    config_path = qa_tmp_path / "producer-config.json"
    config_path.write_text("{}", encoding="utf-8")
    argv = [
        "--data-root",
        str(data_root or Path(case["market_db"]).parent.parent),
        "--output-root",
        str(Path(case["canonical_root"]).absolute()),
        "--config-json",
        str(config_path.absolute()),
        "--result-id",
        "daily-result",
        "--result-name",
        "daily fixture",
        "--as-of-date",
        "2025-01-02",
        "--scope-id",
        "scope-a03",
        "--scope-type",
        "local",
        "--delivery-id",
        "delivery-a03",
        "--request-id",
        "request-a03",
        "--journal-path",
        str((qa_tmp_path / "producer-journal.jsonl").absolute()),
    ]
    if include_fundamental_root:
        argv.extend(
            ["--current-fundamental-source-root", str((qa_tmp_path / "fundamental").absolute())]
        )
    return argv, config_path


@pytest.mark.parametrize("bad_preflight", ["missing_fundamental_root", "wrong_data_root"])
def test_generation_argv_requires_explicit_fundamental_root_and_matching_market_db(
    qa_tmp_path: Path,
    bad_preflight: str,
) -> None:
    case = outcome_fixture._case(qa_tmp_path)
    wrong_data_root = qa_tmp_path / "wrong-data-root"
    argv, config_path = _generation_argv(
        case,
        qa_tmp_path,
        data_root=wrong_data_root if bad_preflight == "wrong_data_root" else None,
        include_fundamental_root=bad_preflight != "missing_fundamental_root",
    )
    request = _daily_request(case)
    request["result_ids"] = ["daily-result"]
    request["generation_argv"] = argv
    request["source_pins"].append(  # type: ignore[union-attr]
        {
            "path": str(config_path.absolute()),
            "sha256": "sha256:" + hashlib.sha256(config_path.read_bytes()).hexdigest(),
        }
    )
    receipt_root = qa_tmp_path / "daily-receipts"

    with pytest.raises(PersonalNaturalOutcomeDailyError):
        run_personal_model_daily(request=request, receipt_root=receipt_root)

    assert not receipt_root.exists()
    assert not (Path(case["isolated_root"]) / "personal_natural_outcomes").exists()


def test_busy_lock_fails_without_replacing_the_existing_lock(
    qa_tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    case = outcome_fixture._case(qa_tmp_path)
    request_path, digest = _write_request(qa_tmp_path, _daily_request(case))
    receipt_root = qa_tmp_path / "daily-receipts"
    receipt_root.mkdir()
    lock_path = receipt_root / ".personal-model-daily.lock"
    original_lock = b"another writer owns this lock"
    lock_path.write_bytes(original_lock)

    exit_code = daily_cli.main(_argv(request_path, digest, receipt_root))

    result = _stdout_receipt(capsys)
    assert exit_code == 2
    assert result["status"] == "failed"
    assert "busy" in str(result["message"]).lower()
    assert lock_path.read_bytes() == original_lock
    assert not (receipt_root / "attempts").exists()


def test_runtime_failure_publishes_attempt_receipt_with_negative_capability_flags(
    qa_tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = outcome_fixture._case(qa_tmp_path)
    receipt_root = qa_tmp_path / "daily-receipts"

    def fail_outcome(**_kwargs: object) -> object:
        raise RuntimeError("synthetic outcome failure")

    monkeypatch.setattr(
        "app_module.recommendation.personal_natural_outcome_daily.run_personal_natural_outcome_daily",
        fail_outcome,
    )
    result = run_personal_model_daily(
        request=_daily_request(case),
        receipt_root=receipt_root,
    )

    assert result["status"] == "failed"
    assert result["reason"] == "synthetic outcome failure"
    assert result["receipt_path"]
    assert Path(str(result["receipt_path"])).parent.name == "attempts"
    stored = json.loads(Path(str(result["receipt_path"])).read_text(encoding="utf-8"))
    assert stored["payload_sha256"] == result["payload_sha256"]
    assert stored["global_natural_evidence_created"] is False
    assert stored["promotion_credit_created"] is False


def test_synthetic_fixture_reuses_existing_capture_and_outcome_across_process_retry(
    qa_tmp_path: Path,
) -> None:
    """用合成 capture/market fixture 驗證重試，不代表正式生產資料驗收。"""

    case = outcome_fixture._case(qa_tmp_path)
    existing_outcome = outcome_fixture._run(case)
    assert existing_outcome.status == "completed"
    existing_summary_bytes = existing_outcome.summary_path.read_bytes()
    existing_outcome_bytes = {
        path: path.read_bytes() for path in existing_outcome.outcome_paths
    }
    request_path, digest = _write_request(qa_tmp_path, _daily_request(case))
    receipt_root = qa_tmp_path / "daily-receipts"

    first_pid, first_exit, first, first_stderr = _invoke_cli_process(
        request_path, digest, receipt_root
    )
    receipt_path = Path(str(first["receipt_path"]))
    receipt_bytes = receipt_path.read_bytes()
    second_pid, second_exit, second, second_stderr = _invoke_cli_process(
        request_path, digest, receipt_root
    )

    assert first_exit == 0, first_stderr
    assert second_exit == 0, second_stderr
    assert first_pid != second_pid
    assert first["status"] == "completed"
    assert first["idempotent"] is False
    assert second["idempotent"] is True
    assert first["payload_sha256"] == second["payload_sha256"]
    assert first["request_sha256"] == second["request_sha256"]
    assert first["process_identity"]["pid"] == first_pid  # type: ignore[index]
    assert second["process_identity"] == first["process_identity"]
    assert second["readback_process_identity"]["pid"] == second_pid  # type: ignore[index]
    assert second["readback_process_identity"]["pid"] != first["process_identity"]["pid"]  # type: ignore[index]
    assert second["receipt_path"] == first["receipt_path"]
    assert json.loads(receipt_bytes)["payload_sha256"] == first["payload_sha256"]
    assert "readback_process_identity" not in json.loads(receipt_bytes)
    assert receipt_path.read_bytes() == receipt_bytes
    assert first["global_natural_evidence_created"] is False
    assert first["promotion_credit_created"] is False
    assert first["auto_fit_performed"] is False
    assert first["formal_order_allowed"] is False
    assert first["outcome"]["summary_sha256"] == existing_outcome.summary_sha256  # type: ignore[index]
    assert first["outcome"]["summary_path"] == str(existing_outcome.summary_path)  # type: ignore[index]
    assert existing_outcome.summary_path.read_bytes() == existing_summary_bytes
    assert {
        path: path.read_bytes() for path in existing_outcome.outcome_paths
    } == existing_outcome_bytes
