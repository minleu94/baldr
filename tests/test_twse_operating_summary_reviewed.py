"""合成原件只驗新外層／原report port，不授官方用途或真來源接受。"""
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from io import StringIO
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import csv
import json

import pytest

from app_module import twse_operating_summary_snapshot as base
from app_module import twse_operating_summary_reviewed as reviewed
from app_module.twse_operating_summary_report_provider import OperatingSummaryReportProvider

NOW = datetime(2026, 10, 17, 16, 15, tzinfo=ZoneInfo("Asia/Taipei"))


def raw_csv():
    stream = StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(base._FIELDS)
    for code, name, values in (
        ("2330", "台積電", ("2404483.69", "67.03", "59.29", "64.47", "53.22")),
        ("2317", "鴻海", ("4645427.82", "6.15", "3.67", "3.64", "2.73")),
        ("2454", "聯發科", ("301333.12", "46.25", "15.19", "18.25", "16.25")),
    ):
        writer.writerow(("1151017", "115", "2", code, name, *values))
    for number in range(1052):
        writer.writerow(("1151017", "115", "2", str(100000 + number), "合成隔離", "", "", "", "", ""))
    return stream.getvalue().encode("utf-8-sig")


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    # 假原v1 reader代表已核base的前置條件；真原件／真時鐘另由Root具名QA。
    files = {name: b"synthetic" for name in base._FILES}
    files["response.raw"] = raw_csv()
    monkeypatch.setattr(base, "_FILES", {name: (len(raw), sha256(raw).hexdigest()) for name, raw in files.items()})
    files.update({"manifest.json": b'{}', "receipt.json": b'{}'})
    original = tmp_path / "original"
    original.mkdir()
    for name, value in files.items():
        (original / name).write_bytes(value)
    pin = base.OperatingSummaryPin(original, sha256(b'{}').hexdigest(), sha256(b'{}').hexdigest())
    monkeypatch.setattr(base, "read_operating_summary_snapshot", lambda child, *, cutoff_at:
        base.OperatingSummaryRead(child, base._acceptance(NOW - timedelta(hours=2)), NOW - timedelta(hours=1), base._values(raw_csv())))
    monkeypatch.setattr(reviewed, "DOCUMENTS_NOT_BEFORE", NOW - timedelta(hours=1))
    output = tmp_path / "reviewed"
    selected = reviewed.seal_reviewed_operating_summary_snapshot(pin, output_directory=output, clock=lambda: NOW)
    return SimpleNamespace(pin=selected, original=pin, files=files, output=output)


@pytest.mark.parametrize("code,revenue,net", [("2317", "4645427820000.00", "2.73"),
    ("2330", "2404483690000.00", "53.22"), ("2454", "301333120000.00", "16.25")])
def test_new_exact_issuer_values_and_original_source_unchanged(snapshot, code, revenue, net):
    result = reviewed.read_reviewed_operating_summary_snapshot(snapshot.pin, stock_code=code, cutoff_at=NOW + timedelta(hours=1))
    assert result.values[0][2:] == (Decimal(revenue), "TWD") and result.values[-1][2] == Decimal(net)
    assert result.acceptance.scope.intended_use == "current_research"
    assert result.available_hour == NOW.replace(hour=17, minute=0)
    assert all((snapshot.original.directory / name).read_bytes() == raw for name, raw in snapshot.files.items())
    assert all((snapshot.output / "base" / name).read_bytes() == raw for name, raw in snapshot.files.items())


def repin(snapshot, *, manifest=None, receipt=None):
    if manifest is not None:
        (snapshot.output / "manifest.json").write_bytes(base._bytes(manifest))
    manifest_sha = sha256((snapshot.output / "manifest.json").read_bytes()).hexdigest()
    if receipt is None:
        receipt = json.loads((snapshot.output / "receipt.json").read_bytes())
    receipt["manifest_sha256"] = manifest_sha
    (snapshot.output / "receipt.json").write_bytes(base._bytes(receipt))
    return reviewed.ReviewedOperatingSummaryPin(snapshot.output, manifest_sha, sha256(base._bytes(receipt)).hexdigest())


@pytest.mark.parametrize("change", ["company", "profit_basis", "intended_use", "child_path", "available_hour", "clock_order"])
def test_rehashing_cannot_expand_purpose_or_rebind_time_and_base(snapshot, change):
    manifest = json.loads((snapshot.output / "manifest.json").read_bytes())
    receipt = json.loads((snapshot.output / "receipt.json").read_bytes())
    if change == "company":
        manifest["evidence"]["reviewed_issuers"]["2382"] = deepcopy(manifest["evidence"]["reviewed_issuers"]["2317"])
    elif change == "profit_basis":
        manifest["evidence"]["profit_basis"] = "parent_attributable"
    elif change == "intended_use":
        manifest["source_use"]["scope"]["intended_use"] = "historical_pit"
    elif change == "child_path":
        manifest["base_snapshot"]["directory"] = "../original"
    elif change == "available_hour":
        receipt["available_hour"] = NOW.replace(hour=16, minute=0).isoformat()
    else:
        receipt["successful_batch_completed_at"] = (NOW - timedelta(minutes=1)).isoformat()
    changed = repin(snapshot, manifest=manifest, receipt=receipt)
    with pytest.raises(ValueError):
        reviewed.read_reviewed_operating_summary_snapshot(changed, stock_code="2317", cutoff_at=NOW + timedelta(hours=1))


@pytest.mark.parametrize("marker", [".pending.json", "failure.json", "base/.pending.json", "base/failure.json"])
def test_uncommitted_outer_or_original_child_never_reads(snapshot, marker):
    (snapshot.output / marker).write_text("{}")
    with pytest.raises(base.OperatingSummaryError):
        reviewed.read_reviewed_operating_summary_snapshot(snapshot.pin, stock_code="2330", cutoff_at=NOW + timedelta(hours=1))


def test_before_new_hour_future_cutoff_and_unqualified_company_refused(snapshot):
    with pytest.raises(base.OperatingSummaryError, match="尚未到"):
        reviewed.read_reviewed_operating_summary_snapshot(snapshot.pin, stock_code="2317", cutoff_at=NOW)
    with pytest.raises(base.OperatingSummaryError, match="實際現在"):
        reviewed.read_reviewed_operating_summary_snapshot(snapshot.pin, stock_code="2317", cutoff_at=datetime.now(NOW.tzinfo) + timedelta(minutes=1))
    with pytest.raises(base.OperatingSummaryError):
        reviewed.read_reviewed_operating_summary_snapshot(snapshot.pin, stock_code="2382", cutoff_at=NOW + timedelta(hours=1))
    with pytest.raises(base.OperatingSummaryError):
        reviewed.read_reviewed_operating_summary_snapshot(snapshot.original, stock_code="2317", cutoff_at=NOW + timedelta(hours=1))


def test_child_mutation_during_outer_projection_refused(snapshot, monkeypatch):
    original = reviewed._values
    def changed(raw, stock_code):
        result = original(raw, stock_code)
        (snapshot.output / "base/license.raw").write_bytes(b"changed")
        return result
    monkeypatch.setattr(reviewed, "_values", changed)
    with pytest.raises(base.OperatingSummaryError, match="改變"):
        reviewed.read_reviewed_operating_summary_snapshot(snapshot.pin, stock_code="2317", cutoff_at=NOW + timedelta(hours=1))


def test_publisher_cannot_overwrite_or_write_within_protected_root(snapshot, monkeypatch):
    with pytest.raises(base.OperatingSummaryError, match="不可覆寫"):
        reviewed.seal_reviewed_operating_summary_snapshot(snapshot.original, output_directory=snapshot.output, clock=lambda: NOW)
    monkeypatch.setenv("DATA_ROOT", str(snapshot.output.parent / "protected"))
    with pytest.raises(base.OperatingSummaryError, match="正式／私人根"):
        reviewed.seal_reviewed_operating_summary_snapshot(snapshot.original, output_directory=snapshot.output.parent / "protected/new", clock=lambda: NOW)


def test_original_report_port_keeps_correct_issuer_and_quanta_unavailable(snapshot):
    provider = OperatingSummaryReportProvider(snapshot.pin)
    for code in reviewed.REVIEWED_COMPANIES:
        rows, sources = provider.read(code, observed_at=NOW + timedelta(hours=1))
        assert len(rows) == 5 and sources[0].row_count == 5
        assert all(row.source_id == "official.twse.operating_summary." + code + ".2026h1" for row in rows)
        assert all(not row.formal_pit_eligible and not row.aggregate_feature_eligible and row.announced_date == "" for row in rows)
        assert any("母公司" in text for text in sources[0].limitations)
    rows, sources = provider.read("2382", observed_at=NOW + timedelta(hours=1))
    assert not rows and sources[0].status == "unavailable" and "驗證頁" in sources[0].limitations[0]
    assert provider.read("1101", observed_at=NOW + timedelta(hours=1)) == ((), ())


def test_four_part_explicit_environment_selects_new_schema(snapshot, monkeypatch):
    monkeypatch.setenv("OPERATING_SUMMARY_POLICY_SCHEMA", reviewed.SCHEMA)
    monkeypatch.setenv("OPERATING_SUMMARY_SNAPSHOT_DIRECTORY", str(snapshot.pin.directory))
    monkeypatch.setenv("OPERATING_SUMMARY_MANIFEST_SHA256", snapshot.pin.manifest_sha256)
    monkeypatch.setenv("OPERATING_SUMMARY_RECEIPT_SHA256", snapshot.pin.receipt_sha256)
    selected = OperatingSummaryReportProvider.from_environment()
    assert type(selected.pin) is reviewed.ReviewedOperatingSummaryPin
    monkeypatch.setenv("OPERATING_SUMMARY_POLICY_SCHEMA", "unknown-schema")
    broken = OperatingSummaryReportProvider.from_environment()
    assert broken.pin is None and broken.configuration_error
