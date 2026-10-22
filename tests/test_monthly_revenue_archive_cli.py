"""研究 CLI 的路徑、外部 pin 與無網路長期規劃驗證。"""

import json
from pathlib import Path

import pytest

from scripts import monthly_revenue_archive as cli


def test_write_destination_cannot_escape_repository_output(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    (tmp_path / "output").mkdir()
    assert cli._output_path(str(tmp_path / "output" / "new")) == tmp_path / "output" / "new"
    with pytest.raises(ValueError, match="under_repository_output"):
        cli._output_path(str(tmp_path / "formal"))
    with pytest.raises(ValueError, match="under_repository_output"):
        cli._output_path(str(tmp_path / "output"))


def test_wrong_external_receipt_hash_rejected_before_archive_creation(tmp_path, capsys):
    captured = tmp_path / "capture"
    captured.mkdir()
    (captured / "receipt.json").write_text('{"sources":[]}', encoding="utf-8")
    archive = tmp_path / "should-not-exist"
    code = cli.main(["import-opendata-capture", "--capture-directory", str(captured),
                     "--receipt-sha256", "0" * 64, "--archive-root", str(archive)])
    assert code == 2
    assert not archive.exists()
    assert json.loads(capsys.readouterr().out)["error"] == "capture_receipt_external_sha256_mismatch"


def test_twenty_year_plan_uses_explicit_small_resumable_chunks(capsys):
    assert cli.main(["plan-history", "--start-period", "2007-01", "--end-period", "2026-09"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["network_enabled"] is False
    assert plan["requested_period_count"] == 237
    assert len(plan["requested_pairs"]) == 474
    assert all(len(chunk) <= 4 for chunk in plan["chunks"])
    assert plan["writes_formal_data"] is False


def test_history_plan_hash_mismatch_performs_no_capture(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "capture_mops_monthly_revenue_history_plan_chunk",
                        lambda *args, **kwargs: pytest.fail("不應發出HTTP請求"))
    assert cli.main(["capture-history-chunk", "--start-period", "2026-07", "--end-period", "2026-08",
                     "--plan-sha256", "f" * 64, "--capture-root", str(tmp_path / "unused")]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "history_plan_external_sha256_mismatch"


@pytest.mark.parametrize("bindings", [
    [["twse", "unused", "0" * 64]],
    [["twse", "unused", "0" * 64], ["twse", "unused", "1" * 64]],
])
def test_research_requires_two_distinct_market_pins_before_reading_capture(bindings, monkeypatch, capsys):
    monkeypatch.setattr(cli, "read_openapi_capture_batches",
                        lambda *args: pytest.fail("不應讀取未指定雙市場資格的原件"))
    argv = ["research-current", "--capture-directory", "unused", "--receipt-sha256", "0" * 64]
    for binding in bindings:
        argv.extend(["--binding", *binding])
    assert cli.main(argv) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "research_requires_exact_market_binding_pair"


@pytest.mark.parametrize("extra,reason", [
    (["--cutoff-at", "2026-10-21T00:00:00"], "research_cutoff_must_be_timezone_aware"),
    (["--minimum", "NaN"], "research_minimum_must_be_finite"),
])
def test_research_rejects_unsafe_clock_or_threshold_before_projection(extra, reason, capsys):
    assert cli.main(["research-current", "--capture-directory", "unused", "--receipt-sha256", "0" * 64,
                     "--binding", "twse", "unused", "0" * 64, *extra]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == reason


def test_capture_reader_rejects_oversized_and_hardlinked_inputs(tmp_path):
    original = tmp_path / "original.json"
    original.write_bytes(b"12345")
    with pytest.raises(ValueError, match="exceeds_limit"):
        cli._read_bounded(original, 4)
    linked = tmp_path / "linked.json"
    linked.hardlink_to(original)
    with pytest.raises(ValueError, match="missing_or_exceeds_limit"):
        cli._read_bounded(linked, 8)


def test_history_import_wrong_pin_cannot_create_archive(tmp_path, capsys):
    capture = tmp_path / "capture.json"
    capture.write_bytes(b"{}")
    destination = tmp_path / "must-not-exist"
    assert cli.main(["import-history-capture", "--capture-file", str(capture),
                     "--capture-sha256", "0" * 64, "--archive-root", str(destination)]) == 2
    assert not destination.exists()
    assert json.loads(capsys.readouterr().out)["error"] == "artifact_sha256_mismatch"
