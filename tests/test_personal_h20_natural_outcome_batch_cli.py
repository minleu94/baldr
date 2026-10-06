"""exact request codec 與 CLI 原 ports 接線；全用 synthetic。"""
import json
from pathlib import Path
import subprocess
import sys

import pytest
from test_personal_h20_natural_outcome_batch import cohort, attach
from app_module.recommendation.personal_current_observed_h20_capture import H20CaptureError, digest, encoded
from app_module.recommendation.persistence import ExecutionArtifactIntegrityError
import scripts.scheduled.run_personal_h20_natural_outcome_batch as cli


def request_file(tmp_path):
    args, _, entry, outcome = cohort(tmp_path)
    attach(args, entry, outcome)
    request = {k: str(v) for k, v in args.items() if k.endswith("path") or k.endswith("sha256") or k == "root"}
    request["schema_version"] = cli.REQUEST_SCHEMA
    file = tmp_path / "request.json"
    file.write_bytes(encoded(request))
    return args, request, file


@pytest.mark.parametrize("key,value", [("observed_at", "2026-10-07"), ("latest", True),
    ("schema_version", "wrong"), ("manifest_path", "relative.json"),
    ("manifest_path", "C:/a/*.json"), ("outcome_sha256", None)])
def test_exact_codec_rejects_unknown_clock_paths_and_pairs(tmp_path, key, value):
    _, request, file = request_file(tmp_path)
    request[key] = value
    file.write_bytes(encoded(request))
    with pytest.raises(H20CaptureError):
        cli.decode_request(file, digest(file.read_bytes()))


def test_codec_raw_pin_duplicate_key_and_budget(tmp_path):
    _, _, file = request_file(tmp_path)
    with pytest.raises(H20CaptureError, match="raw_pin"):
        cli.decode_request(file, "sha256:" + "b" * 64)
    file.write_bytes(b'{"schema_version":"a","schema_version":"b"}')
    with pytest.raises(H20CaptureError, match="duplicate_json"):
        cli.decode_request(file, digest(file.read_bytes()))
    file.write_bytes(b" " * (64 * 1024 + 1))
    with pytest.raises(ExecutionArtifactIntegrityError, match="大小上限"):
        cli.decode_request(file, digest(file.read_bytes()))


def test_main_injects_original_read_ports_and_returns_complete_result(tmp_path, monkeypatch, capsys):
    args, _, file = request_file(tmp_path)
    calls = []
    def ports():
        calls.append(True)
        return {k: args[k] for k in ("source_verifier", "contract_verifier", "input_capture_verifier", "outcome_verifier")}
    monkeypatch.setattr(cli, "personal_current_observed_h20_read_ports", ports)
    code = cli.main(["--request-json", str(file), "--request-sha256", digest(file.read_bytes())])
    result = json.loads(capsys.readouterr().out)
    assert code == 0 and result["matured_count"] == 2 and calls == [True]
    assert result["symbols"] == ["2330", "2454"]


def test_invalid_request_never_composes_ports(tmp_path, monkeypatch, capsys):
    _, request, file = request_file(tmp_path)
    request["observed_at"] = "invented"
    file.write_bytes(encoded(request))
    def forbidden():
        raise AssertionError("非法 request 不進 composition")
    monkeypatch.setattr(cli, "personal_current_observed_h20_read_ports", forbidden)
    assert cli.main(["--request-json", str(file), "--request-sha256", digest(file.read_bytes())]) == 2
    assert "exact_request_schema" in json.loads(capsys.readouterr().out)["reason"]


def test_fresh_cli_pin_failure_and_app_cold_import_no_ml(tmp_path):
    _, _, file = request_file(tmp_path)
    result = subprocess.run([sys.executable, str(Path(cli.__file__)), "--request-json", str(file),
        "--request-sha256", "sha256:" + "b" * 64], capture_output=True, text=True)
    assert result.returncode == 2 and "raw_pin" in json.loads(result.stdout)["reason"]
    result = subprocess.run([sys.executable, "-c", "import sys; import app_module.recommendation.personal_h20_natural_outcome_batch; assert not any(k.startswith('ml_module') for k in sys.modules)"],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
