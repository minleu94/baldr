"""合成資料驗證解析、保存、來源及時間守衛；不取代真原件用途接受。"""
from datetime import datetime, timedelta, timezone
from contextlib import closing
from decimal import Decimal
from hashlib import sha256
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

import app_module.quanta_monthly_sales_snapshot as snapshot
from app_module.quanta_monthly_sales_report_provider import QuantaMonthlySalesReportProvider
from app_module.stock_research_report_service import StockResearchReportReadService

NOW = datetime(2026, 10, 17, 18, 1, tzinfo=timezone.utc)
AVAILABLE = datetime(2026, 10, 17, 19, tzinfo=timezone.utc)


def raw_table() -> bytes:
    months = "January February March April May June July August September October November December".split()
    rows = ['<tr><th>2026 Monthly Sales (Unit: NT $ Million)</th></tr>',
        '<tr><th>Month</th><th>2026<br>Adjusted  Consolidated</th><th>2025<br>Adjusted Consolidated</th><th>MoM</th><th>YoY</th><th>YTD YoY</th></tr>']
    for index, month in enumerate(months):
        cells = [month, "1,000", "1,000", "0.0%", "0.0%", "0.0%"] if index < 9 else [month, "", "", "", "", ""]
        if index == 7:
            cells.append("")
        rows.append('<tr>' + ''.join('<td>' + cell + '</td>' for cell in cells) + '</tr>')
    rows.append('<tr><td>Total</td><td>9,001</td><td>9,001</td><td></td><td></td><td></td></tr>')
    return ('<html><div id="2026"><table>' + ''.join(rows) + '</table></div></html>').encode()


def test_same_table_money_and_reported_rates_keep_source_precision():
    period, values = snapshot._latest_values(raw_table())
    assert period == "2026-09"
    assert values == (Decimal(1000), Decimal(1000), Decimal(1000), Decimal("0.0"), Decimal("0.0"))
    # 刻意不一致的總計不被搬成推算指標，也不拼另一年度表。
    assert len(values) == 5


@pytest.mark.parametrize("before,after", [
    (b"NT $ Million", b"NT $ Thousand"),
    (b"2025<br>Adjusted Consolidated", b"2025<br>Consolidated"),
    (b"<td>March</td><td>1,000", b"<td>March</td><td>"),
    (b"<td>October</td><td></td><td></td>", b"<td>October</td><td>1,000</td><td></td>"),
    (b"<td>August</td>", b"<td>September</td>"),
    (b"<td>September</td><td>1,000", b"<td>September</td><td>NaN"),
    (b"<td>September</td><td>1,000", b"<td>September</td><td>9,000"),
    (b"<td>September</td><td>1,000", b"<td>September</td><td>-1,000"),
])
def test_wrong_unit_basis_missing_month_or_false_rate_is_rejected(before, after):
    with pytest.raises(ValueError):
        snapshot._latest_values(raw_table().replace(before, after, 1))


@pytest.fixture
def sources(tmp_path, monkeypatch):
    for name in ("QUANTA_MONTHLY_SALES_DIRECTORY", "QUANTA_MONTHLY_SALES_MANIFEST_SHA256", "QUANTA_MONTHLY_SALES_RECEIPT_SHA256"):
        monkeypatch.delenv(name, raising=False)
    root = tmp_path / "sources"
    root.mkdir()
    files = {"monthly.raw": raw_table()}
    files["monthly-http.json"] = snapshot._bytes({"official_url": snapshot.SOURCE_URL, "response_url": snapshot.SOURCE_URL,
        "response_status": 200, "response_body_complete": True, "response_body_eof": True,
        "raw_bytes": len(files["monthly.raw"]), "raw_sha256": sha256(files["monthly.raw"]).hexdigest(),
        "started_at": "2026-10-17T17:28:27+00:00", "ended_at": "2026-10-17T17:28:28+00:00"})
    files["twse-company.raw.json"] = snapshot._bytes([{"公司代號": "2382", "公司名稱": "廣達電腦股份有限公司", "網址": "www.quantatw.com"}])
    files["identity-publication.json"] = snapshot._bytes({"raw_inputs": [{"path": "twse_t187ap03.raw.json",
        "content_sha256": "sha256:" + sha256(files["twse-company.raw.json"]).hexdigest(),
        "http": {"http_status": 200, "requested_url": snapshot.IDENTITY_URL, "final_url": snapshot.IDENTITY_URL,
            "captured_at": "2026-10-16T07:01:48+08:00"}}], "license_scope": {"allowed_use_cases": ["research_shadow"]}})
    files["identity-receipt.json"] = snapshot._bytes({"source_custody_verified": True, "candidate_only": True})
    mapping = {"twse_t187ap03.raw.json": "twse-company.raw.json", "pit-sector-membership-machine.json": "identity-publication.json", "receipt.json": "identity-receipt.json"}
    files["identity-archive.json"] = snapshot._bytes({"status": "archived_candidate", "files": [
        {"relative_path": original, "archive_file_hash": "sha256:" + sha256(files[name]).hexdigest(), "byte_count": len(files[name])}
        for original, name in mapping.items()]})
    monkeypatch.setattr(snapshot, "_FILES", {name: sha256(raw).hexdigest() for name, raw in files.items()})
    for name, raw in files.items():
        (root / name).write_bytes(raw)
    return {name: root / name for name in files}


def sealed(sources, tmp_path):
    return snapshot.seal_quanta_monthly_sales(sources, output_directory=tmp_path / "snapshot", clock=lambda: NOW)


def test_save_and_reader_keep_raw_and_enforce_natural_hour(sources, tmp_path):
    pin = sealed(sources, tmp_path)
    original = {name: path.read_bytes() for name, path in sources.items()}
    with pytest.raises(ValueError, match="未到"):
        snapshot.read_quanta_monthly_sales(pin, cutoff_at=AVAILABLE - timedelta(microseconds=1))
    period, values, available = snapshot.read_quanta_monthly_sales(pin, cutoff_at=AVAILABLE)
    assert period == "2026-09" and values[0] == Decimal(1000) and available == AVAILABLE
    assert all((pin.directory / name).read_bytes() == raw for name, raw in original.items())
    with pytest.raises(ValueError, match="全新"):
        sealed(sources, tmp_path)
    assert all(path.read_bytes() == original[name] for name, path in sources.items())


def test_empty_or_isolated_data_root_does_not_remove_default_formal_write_guard(sources, tmp_path, monkeypatch):
    for configured in ("", str(tmp_path / "isolated-market")):
        monkeypatch.setenv("DATA_ROOT", configured)
        with pytest.raises(ValueError, match="正式／私人根"):
            snapshot.seal_quanta_monthly_sales(sources,
                output_directory=snapshot._DEFAULT_FORMAL_ROOT / "must-not-create-quanta-trial",
                clock=lambda: NOW)


@pytest.mark.parametrize("name,field,value", [
    ("monthly-http.json", "response_body_eof", False),
    ("monthly-http.json", "response_url", "https://validate.example/"),
    ("identity-receipt.json", "source_custody_verified", False),
])
def test_transport_or_custody_failure_is_rejected_before_target(sources, tmp_path, monkeypatch, name, field, value):
    files = {key: path.read_bytes() for key, path in sources.items()}
    body = json.loads(files[name])
    body[field] = value
    files[name] = snapshot._bytes(body)
    monkeypatch.setattr(snapshot, "_FILES", {key: sha256(raw).hexdigest() for key, raw in files.items()})
    sources[name].write_bytes(files[name])
    with pytest.raises(ValueError):
        sealed(sources, tmp_path)
    assert not (tmp_path / "snapshot").exists()


@pytest.mark.parametrize("code,website", [("2330", "www.quantatw.com"), ("2382", "www.quantatw.com.evil.test"), ("2382", "www.quantatw.com@evil.test")])
def test_issuer_and_domain_binding_cannot_be_replaced(sources, tmp_path, monkeypatch, code, website):
    raw = snapshot._bytes([{"公司代號": code, "公司名稱": "廣達電腦股份有限公司", "網址": website}])
    sources["twse-company.raw.json"].write_bytes(raw)
    monkeypatch.setitem(snapshot._FILES, "twse-company.raw.json", sha256(raw).hexdigest())
    with pytest.raises(ValueError, match="身分|網域"):
        sealed(sources, tmp_path)


def test_tampered_copy_and_partial_state_remain_unavailable(sources, tmp_path):
    pin = sealed(sources, tmp_path)
    (pin.directory / ".pending.json").write_text("{}")
    with pytest.raises(ValueError, match="pending"):
        snapshot.read_quanta_monthly_sales(pin, cutoff_at=AVAILABLE)
    (pin.directory / ".pending.json").unlink()
    (pin.directory / "monthly.raw").write_bytes(raw_table() + b" ")
    with pytest.raises(ValueError, match="SHA"):
        snapshot.read_quanta_monthly_sales(pin, cutoff_at=AVAILABLE)


def test_future_cutoff_cannot_bypass_real_availability(sources, tmp_path):
    pin = sealed(sources, tmp_path)
    with pytest.raises(ValueError, match="實際現在"):
        snapshot.read_quanta_monthly_sales(pin, cutoff_at=datetime.now(timezone.utc) + timedelta(days=1))


def test_repinned_manifest_cannot_upgrade_scope(sources, tmp_path):
    pin = sealed(sources, tmp_path)
    body = json.loads((pin.directory / "manifest.json").read_bytes())
    body["source_use"]["authorization_scope"] = "current_stock_research historical_pit"
    changed = snapshot._bytes(body)
    (pin.directory / "manifest.json").write_bytes(changed)
    other = snapshot.QuantaMonthlySalesPin(pin.directory, sha256(changed).hexdigest(), pin.receipt_sha256)
    with pytest.raises(ValueError):
        snapshot.read_quanta_monthly_sales(other, cutoff_at=AVAILABLE)


def test_provider_observed_rows_do_not_claim_historical_or_feature_eligibility(sources, tmp_path):
    provider = QuantaMonthlySalesReportProvider(sealed(sources, tmp_path))
    rows, evidence = provider.read("2382", observed_at=AVAILABLE)
    assert len(rows) == 5 and len(evidence) == 1
    assert [item.value for item in rows] == [Decimal(1000), Decimal(1000), Decimal(1000), Decimal("0.0"), Decimal("0.0")]
    assert [item.period for item in rows] == ["2026-09", "2026-08", "2025-09", "2026-09", "2026-09"]
    assert rows[1].as_of_date == "2026-08-31" and rows[2].as_of_date == "2025-09-30"
    assert rows[0].unit == "百萬元（TWD）"
    assert all(not item.announced_date and item.basis_verified and not item.formal_pit_eligible and not item.aggregate_feature_eligible for item in rows)
    assert evidence[0].current_observed_only and evidence[0].historical_pit_eligible is False
    assert provider.read("2330", observed_at=AVAILABLE) == ((), ())
    early, unavailable = provider.read("2382", observed_at=AVAILABLE - timedelta(seconds=1))
    assert not early and unavailable[0].status == "unavailable"


def test_explicit_history_or_saved_context_does_not_call_current_provider(sources, tmp_path):
    provider = QuantaMonthlySalesReportProvider(sealed(sources, tmp_path))
    with closing(sqlite3.connect(tmp_path / "empty.db")) as connection:
        connection.execute("PRAGMA user_version=1")
    service = StockResearchReportReadService(SimpleNamespace(db_file=tmp_path / "empty.db"),
        quanta_monthly_sales_provider=provider, clock=lambda: AVAILABLE)
    today = AVAILABLE.astimezone(snapshot._TAIPEI).date()
    rows, _, _ = service._read_fundamentals("2382", today, include_current=True)
    assert len([row for row in rows if row.source_id.startswith("official.issuer.quanta.")]) == 5
    def forbidden(*args, **kwargs):
        raise AssertionError("歷史／保存context不得讀目前月營收")
    provider.read = forbidden
    assert not service._read_fundamentals("2382", today, include_current=False)[0]
    assert not service._read_fundamentals("2382", today - timedelta(days=1), include_current=True)[0]


def test_missing_environment_is_idle_and_partial_configuration_unavailable(monkeypatch):
    for name in ("QUANTA_MONTHLY_SALES_DIRECTORY", "QUANTA_MONTHLY_SALES_MANIFEST_SHA256", "QUANTA_MONTHLY_SALES_RECEIPT_SHA256"):
        monkeypatch.delenv(name, raising=False)
    assert QuantaMonthlySalesReportProvider.from_environment().read("2382", observed_at=AVAILABLE) == ((), ())
    monkeypatch.setenv("QUANTA_MONTHLY_SALES_MANIFEST_SHA256", "a" * 64)
    rows, sources = QuantaMonthlySalesReportProvider.from_environment().read("2382", observed_at=AVAILABLE)
    assert not rows and sources[0].status == "unavailable"


def test_monthly_display_keeps_million_integer_and_reported_one_decimal_rate():
    from app_module.stock_research_report_dtos import StockFundamentalObservationDTO
    from ui_qt.views.stock_research_report_view import _metric_text
    def item(value, unit, source="official.issuer.quanta.monthly_sales.2382.2026"):
        return StockFundamentalObservationDTO(kind="monthly_revenue", label="合成披露", value=Decimal(value), unit=unit, source_id=source)
    assert _metric_text(item("325300", "百萬元（TWD）")) == "325,300 百萬元（TWD）"
    assert _metric_text(item("76.7", "%")) == "76.7 %"
    assert _metric_text(item("-23.3", "%")) == "-23.3 %"
    assert _metric_text(item("325300", "TWD", "sqlite.other")) == "325,300.00 TWD"
