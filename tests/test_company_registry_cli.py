from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
from types import SimpleNamespace

import scripts.update_company_registry as update_company_registry
from data_module.company_registry import company_registry_source_contract_path
from scripts.update_company_registry import main


def test_company_registry_cli_dry_run_does_not_write_output(tmp_path, capsys) -> None:
    output = tmp_path / "companies.csv"

    exit_code = main(
        [
            "--output",
            str(output),
            "--source-json-dir",
            str(_source_json_dir(tmp_path)),
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert "ready_for_apply: true" in capsys.readouterr().out
    assert not output.exists()


def test_company_registry_cli_reports_source_outage_without_writing(
    tmp_path,
    capsys,
    monkeypatch,
) -> None:
    output = tmp_path / "companies.csv"

    def fail_sources(_source_json_dir):
        raise RuntimeError("official registry endpoint returned HTTP 520")

    monkeypatch.setattr(update_company_registry, "_load_source_captures", fail_sources)

    assert main(["--output", str(output), "--dry-run"]) == 1

    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload == {
        "error": "official registry endpoint returned HTTP 520",
        "output": str(output),
        "reason": "official_company_registry_source_unavailable",
        "status": "blocked",
        "writes_allowed": False,
    }
    assert not output.exists()


def test_company_registry_sources_fall_back_to_official_csv(monkeypatch) -> None:
    calls = []

    def fake_json(url):
        calls.append(("json", url))
        if url == update_company_registry.TPEX_OTC_URL:
            raise RuntimeError("HTTP 520")
        return [{"source": url}]

    def fake_csv(url):
        calls.append(("csv", url))
        return [{"source": url}]

    monkeypatch.setattr(update_company_registry, "_fetch_json", fake_json)
    monkeypatch.setattr(update_company_registry, "_fetch_csv", fake_csv)

    sources = update_company_registry._load_sources(None)

    assert sources["twse_listed"] == [
        {"source": update_company_registry.TWSE_LISTED_URL}
    ]
    assert sources["tpex_otc"] == [
        {"source": update_company_registry.TPEX_OTC_CSV_URL}
    ]
    assert sources["tpex_emerging"] == [
        {"source": update_company_registry.TPEX_EMERGING_URL}
    ]
    assert ("csv", update_company_registry.TPEX_OTC_CSV_URL) in calls


def test_company_registry_cli_apply_requires_confirm(tmp_path) -> None:
    output = tmp_path / "companies.csv"

    assert (
        main(
            [
                "--output",
                str(output),
                "--source-json-dir",
                str(_source_json_dir(tmp_path)),
                "--apply",
            ]
        )
        == 2
    )


def test_company_registry_cli_apply_writes_after_confirm_and_backs_up(tmp_path) -> None:
    output = tmp_path / "companies.csv"
    output.write_text(
        "industry_category,stock_id,stock_name,type,date,download_time\n"
        "其他,9935,慶豐富,twse,2023-06-30,old\n",
        encoding="utf-8",
    )
    backup_dir = tmp_path / "backup"

    fixed_now = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
    exit_code = main(
        [
            "--output",
            str(output),
            "--backup-dir",
            str(backup_dir),
            "--source-json-dir",
            str(_source_json_dir(tmp_path)),
            "--apply",
            "--confirm",
            "apply-company-registry",
        ],
        now_utc=fixed_now,
    )

    assert exit_code == 0
    assert list(backup_dir.glob("companies_company_registry_*.csv"))
    with output.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows == [
        {
            "industry_category": "居家生活",
            "stock_id": "9935",
            "stock_name": "慶豐富",
            "type": "twse",
            "date": "2026-06-15",
            "download_time": fixed_now.astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        },
        {
            "industry_category": "電子零組件業",
            "stock_id": "3207",
            "stock_name": "耀勝",
            "type": "tpex",
            "date": "2026-06-16",
            "download_time": fixed_now.astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        },
    ]
    manifest_path = company_registry_source_contract_path(output)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    csv_bytes = output.read_bytes()
    assert manifest["status"] == "unknown"
    assert manifest["scope"] == "current_classification_only"
    assert manifest["pit_eligible"] is False
    assert manifest["artifact"] == {
        "name": output.name,
        "bytes": len(csv_bytes),
        "sha256": f"sha256:{hashlib.sha256(csv_bytes).hexdigest()}",
    }
    assert all(source["endpoint"] is None for source in manifest["sources"])
    assert all(source["requested_url"] is None for source in manifest["sources"])
    assert all(source["available_at"] is None for source in manifest["sources"])
    assert all(source["format"] == "local_json" for source in manifest["sources"])
    assert all(source["status"] == "unknown" for source in manifest["sources"])
    assert all(source["publication_date"] is None for source in manifest["sources"])
    assert "company_registry_source_capture_unknown" in manifest["warnings"]


def test_company_registry_cli_records_actual_fallback_capture_metadata(
    tmp_path, monkeypatch
) -> None:
    fixed_now = datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)

    class FakeResponse:
        def __init__(self, content: bytes, value=None, *, url: str):
            self.content = content
            self._value = value
            self.url = url

        def raise_for_status(self):
            return None

        def json(self):
            if self._value is None:
                raise ValueError("not a JSON response")
            return self._value

    twse_payload = [
        {"出表日期": "1150615", "公司代號": "9935", "公司簡稱": "慶豐富", "產業別": "38"}
    ]
    tpex_csv_bytes = (
        "Date,SecuritiesCompanyCode,CompanyAbbreviation,SecuritiesIndustryCode\r\n"
        "1150616,3207,耀勝,28\r\n"
    ).encode("utf-8-sig")
    tpex_emerging_bytes = b"[]"
    twse_bytes = json.dumps(twse_payload, ensure_ascii=False).encode("utf-8")
    calls = []
    response_times = iter(
        fixed_now.replace(minute=fixed_now.minute + offset) for offset in range(4)
    )

    def fake_get(url, **kwargs):
        calls.append(url)
        if url == update_company_registry.TWSE_LISTED_URL:
            return FakeResponse(twse_bytes, twse_payload, url=url)
        if url == update_company_registry.TPEX_OTC_URL:
            import requests

            raise requests.HTTPError("controlled JSON fallback")
        if url == update_company_registry.TPEX_OTC_CSV_URL:
            return FakeResponse(
                tpex_csv_bytes,
                url="https://redirect.example.invalid/official/otc.csv",
            )
        if url == update_company_registry.TPEX_EMERGING_URL:
            return FakeResponse(tpex_emerging_bytes, [], url=url)
        raise AssertionError(f"unexpected source endpoint: {url}")

    monkeypatch.setattr(update_company_registry.requests, "get", fake_get)
    monkeypatch.setattr(update_company_registry, "_utc_now", lambda: next(response_times))
    monkeypatch.setattr(
        update_company_registry,
        "TWStockConfig",
        lambda: SimpleNamespace(meta_data_dir=tmp_path, backup_dir=tmp_path / "backup"),
    )
    output = tmp_path / "companies.csv"
    backup_dir = tmp_path / "backup"

    assert main(
        [
            "--output",
            str(output),
            "--backup-dir",
            str(backup_dir),
            "--apply",
            "--confirm",
            "apply-company-registry",
        ]
    ) == 0

    manifest = json.loads(
        company_registry_source_contract_path(output).read_text(encoding="utf-8")
    )
    by_market = {source["market"]: source for source in manifest["sources"]}
    assert calls.count(update_company_registry.TPEX_OTC_URL) == 3
    assert update_company_registry.TPEX_OTC_CSV_URL in calls
    assert by_market["twse"]["endpoint"] == update_company_registry.TWSE_LISTED_URL
    assert by_market["twse"]["format"] == "json"
    assert by_market["twse"]["response_bytes"] == len(twse_bytes)
    assert by_market["twse"]["response_sha256"] == f"sha256:{hashlib.sha256(twse_bytes).hexdigest()}"
    assert by_market["twse"]["available_at"] == fixed_now.isoformat()
    assert by_market["twse"]["endpoint"] == update_company_registry.TWSE_LISTED_URL
    assert by_market["twse"]["requested_url"] == update_company_registry.TWSE_LISTED_URL
    assert by_market["tpex"]["endpoint"] == "https://redirect.example.invalid/official/otc.csv"
    assert by_market["tpex"]["requested_url"] == update_company_registry.TPEX_OTC_CSV_URL
    assert by_market["tpex"]["format"] == "csv"
    assert by_market["tpex"]["response_bytes"] == len(tpex_csv_bytes)
    assert by_market["tpex"]["response_sha256"] == f"sha256:{hashlib.sha256(tpex_csv_bytes).hexdigest()}"
    assert by_market["tpex"]["available_at"] == fixed_now.replace(minute=1).isoformat()
    assert by_market["emerging"]["endpoint"] == update_company_registry.TPEX_EMERGING_URL
    assert by_market["emerging"]["requested_url"] == update_company_registry.TPEX_EMERGING_URL
    assert by_market["emerging"]["available_at"] == fixed_now.replace(minute=2).isoformat()
    assert by_market["emerging"]["source_date"] is None
    assert manifest["generated_at"] == fixed_now.replace(minute=3).isoformat()
    assert datetime.fromisoformat(manifest["generated_at"]) > max(
        datetime.fromisoformat(source["available_at"]) for source in manifest["sources"]
    )
    assert all(source["status"] == "captured" for source in manifest["sources"])
    assert all(source["publication_date"] is None for source in manifest["sources"])


def test_company_registry_cli_does_not_bind_foreign_csv_replacement_to_capture(
    tmp_path, monkeypatch, capsys
) -> None:
    source_dir = _source_json_dir(tmp_path)
    output = tmp_path / "companies.csv"
    foreign_bytes = (
        "industry_category,stock_id,stock_name,type,date,download_time\n"
        "外部替換,9999,其他公司,twse,2026-06-15,foreign\n"
    ).encode("utf-8-sig")
    original_writer = update_company_registry.write_company_registry_csv

    def replace_after_write(path, rows):
        original_writer(path, rows)
        path.write_bytes(foreign_bytes)

    monkeypatch.setattr(update_company_registry, "write_company_registry_csv", replace_after_write)

    assert main(
        [
            "--output",
            str(output),
            "--source-json-dir",
            str(source_dir),
            "--apply",
            "--confirm",
            "apply-company-registry",
        ],
        now_utc=datetime(2026, 9, 27, 19, 0, tzinfo=timezone.utc),
    ) == 1

    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["reason"] == "company_registry_csv_changed_before_readback"
    assert payload["source_manifest_written"] is False
    assert output.read_bytes() == foreign_bytes
    assert not company_registry_source_contract_path(output).exists()


def _source_json_dir(tmp_path):
    source_dir = tmp_path / "sources"
    source_dir.mkdir(exist_ok=True)
    (source_dir / "twse_listed.json").write_text(
        '[{"出表日期":"1150615","公司代號":"9935","公司簡稱":"慶豐富","產業別":"38"}]',
        encoding="utf-8",
    )
    (source_dir / "tpex_otc.json").write_text(
        '[{"Date":"1150616","SecuritiesCompanyCode":"3207",'
        '"CompanyAbbreviation":"耀勝","SecuritiesIndustryCode":"28"}]',
        encoding="utf-8",
    )
    (source_dir / "tpex_emerging.json").write_text("[]", encoding="utf-8")
    return source_dir
