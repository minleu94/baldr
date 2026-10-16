"""具名台積電 IR 報表的期間、單位與前瞻讀取守衛。"""

from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
import json

import pytest

from data_module import tsmc_ir_condensed_statement as statement


def _page(body: str) -> str:
    return (
        "TAIWAN SEMICONDUCTOR MANUFACTURING COMPANY LIMITED AND SUBSIDIARIES\n"
        "(Expressed in Millions of New Taiwan Dollars (\"NTD\") and U.S. Dollars (\"USD\"))\n"
        "Unaudited\n" + body
    )


def _owned_receipt(tmp_path, monkeypatch, raw: bytes):
    raw_sha = sha256(raw).hexdigest()
    payload = {
        "source_page_url": "https://investor.tsmc.com/chinese/quarterly-results/2026/q2",
        "source_url": statement.SOURCE_PDF_URL,
        "response_url": statement.SOURCE_PDF_URL,
        "status": "complete_pdf_entity_for_research",
        "http_status": 200,
        "content_type": "application/pdf",
        "saved_sha256": raw_sha,
        "saved_bytes": len(raw),
        "retry_count": 0,
        "formal_data_write": False,
        "source_use_accepted": False,
        "historical_pit_eligible": False,
        "finished_at_utc": "2026-10-16T13:49:43+00:00",
    }
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    monkeypatch.setattr(statement, "SOURCE_PDF_SHA256", raw_sha)
    monkeypatch.setattr(statement, "SOURCE_RECEIPT_SHA256", sha256(path.read_bytes()).hexdigest())
    monkeypatch.setattr(statement, "SOURCE_PDF_BYTES", len(raw))
    monkeypatch.setattr(statement, "SOURCE_RECEIPT_BYTES", path.stat().st_size)
    return path


@pytest.fixture
def pages() -> tuple[str, ...]:
    return (
        _page(
            "Consolidated Condensed Balance Sheet\n"
            "June 30, 2026 March 31, 2026 June 30, 2025\n"
            "Total Assets $ 293,742 $ 9,375,655 100.0 $ 8,660,950 100.0 $ 7,006,350 100.0\n"
            "Total Liabilities 90,895 2,901,184 30.9 2,728,561 31.5 2,389,718 34.1\n"
            "Total Shareholders' Equity 202,847 6,474,471 69.1 5,932,389 68.5 4,616,632 65.9\n"
            "Total Liabilities & Shareholders' Equity 293,742 9,375,655 100.0\n"
        ),
        _page(
            "For the Three Months Ended June 30, 2026, March 31, 2026 and June 30, 2025\n"
            "2Q 2026 1Q 2026 2Q 2025\n"
            "Net Revenue $ 40,201 $ 1,270,381 100.0 $ 1,134,103 100.0 $ 933,792 100.0\n"
            "Net Income 22,366 706,781 55.6 572,801 50.5 397,493 42.6\n"
            "Net Income (Losses) Attributable to:\n"
        ),
        _page(
            "For the Six Months Ended June 30\n"
            "2026 2025 YoY\n"
            "Net Revenue $ 76,099 $ 2,404,484 100.0 $ 1,773,046 100.0\n"
            "Net Income 40,497 1,279,582 53.2 758,226 42.8\n"
        ),
        "Notes",
    )


def test_quarter_and_half_year_keep_distinct_basis_and_comparators(pages):
    values = statement.parse_q2_2026_pages(pages)
    assert len(values) == 13
    assert [(v.period, v.value_ntd_million, v.role) for v in values
            if v.metric == "net_revenue" and v.period_basis == "single_quarter"] == [
        ("2026-Q2", 1270381, "current"),
        ("2026-Q1", 1134103, "previous_quarter"),
        ("2025-Q2", 933792, "year_ago"),
    ]
    assert [(v.period, v.value_ntd_million) for v in values
            if v.metric == "net_revenue" and v.period_basis == "year_to_date_cumulative"] == [
        ("2026-H1", 2404484), ("2025-H1", 1773046),
    ]
    assert all(v.value_ntd_million > 0 for v in values)


@pytest.mark.parametrize("old,new", [
    ("Millions", "Thousands"),
    ("Three Months", "Six Months"),
    ("1,270,381", "1,270,380"),
    ("9,375,655", "9,375,654"),
    ("Unaudited", "Draft"),
])
def test_wrong_unit_period_crossfoot_or_review_state_fails_closed(pages, old, new):
    altered = tuple(page.replace(old, new) for page in pages)
    with pytest.raises(ValueError):
        statement.parse_q2_2026_pages(altered)


def test_create_only_read_pin_cutoff_and_raw_tamper(tmp_path, monkeypatch, pages):
    values = statement.parse_q2_2026_pages(pages)
    raw = b"%PDF-1.7\ntrial\n%%EOF"
    source = tmp_path / "original.pdf"
    source.write_bytes(raw)
    receipt = _owned_receipt(tmp_path, monkeypatch, raw)
    monkeypatch.setattr(statement, "parse_q2_2026_pdf", lambda _: values)
    root = tmp_path / "snapshots"
    saved = statement.save_research_snapshot(
        source, receipt, root,
    )
    assert saved.available_at.isoformat() == "2026-10-16T22:00:00+08:00"
    with pytest.raises(FileExistsError):
        statement.save_research_snapshot(
            source, receipt, root,
        )
    with pytest.raises(ValueError, match="尚未到"):
        statement.read_research_snapshot(
            root, saved.snapshot_id, expected_manifest_sha256=saved.manifest_sha256,
            decision_at=datetime.fromisoformat("2026-10-16T13:59:59+00:00"),
        )
    read = statement.read_research_snapshot(
        root, saved.snapshot_id, expected_manifest_sha256=saved.manifest_sha256,
        decision_at=datetime.fromisoformat("2026-10-16T14:00:00+00:00"),
    )
    assert read.values == values
    assert read.source_use_accepted is False
    assert read.historical_pit_eligible is False
    manifest = root / saved.snapshot_id / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["values"] == [asdict(value) for value in values]
    (root / saved.snapshot_id / "source.pdf").write_bytes(raw + b"tamper")
    with pytest.raises(ValueError, match="原件"):
        statement.read_research_snapshot(
            root, saved.snapshot_id, expected_manifest_sha256=saved.manifest_sha256,
            decision_at=datetime.fromisoformat("2026-10-16T14:01:00+00:00"),
        )


def test_changed_manifest_cannot_grant_source_use(tmp_path, monkeypatch, pages):
    values = statement.parse_q2_2026_pages(pages)
    monkeypatch.setattr(statement, "parse_q2_2026_pdf", lambda _: values)
    raw = b"%PDF-1.7\ntrial\n%%EOF"
    source = tmp_path / "original.pdf"
    source.write_bytes(raw)
    receipt = _owned_receipt(tmp_path, monkeypatch, raw)
    root = tmp_path / "snapshots"
    saved = statement.save_research_snapshot(
        source, receipt, root,
    )
    manifest = root / saved.snapshot_id / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["source_use_accepted"] = True
    changed = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    manifest.write_bytes(changed)
    with pytest.raises(ValueError, match="外部 SHA"):
        statement.read_research_snapshot(
            root, saved.snapshot_id, expected_manifest_sha256=saved.manifest_sha256,
            decision_at=datetime.fromisoformat("2026-10-16T14:00:00+00:00"),
        )
    with pytest.raises(ValueError, match="隔離旗標"):
        statement.read_research_snapshot(
            root, saved.snapshot_id, expected_manifest_sha256=sha256(changed).hexdigest(),
            decision_at=datetime.fromisoformat("2026-10-16T14:00:00+00:00"),
        )


def test_backdated_manifest_time_is_rejected_even_with_new_manifest_pin(
    tmp_path, monkeypatch, pages,
):
    monkeypatch.setattr(statement, "parse_q2_2026_pdf", lambda _: statement.parse_q2_2026_pages(pages))
    raw = b"%PDF-1.7\ntrial\n%%EOF"
    source = tmp_path / "original.pdf"
    source.write_bytes(raw)
    receipt = _owned_receipt(tmp_path, monkeypatch, raw)
    root = tmp_path / "snapshots"
    saved = statement.save_research_snapshot(source, receipt, root)
    manifest = root / saved.snapshot_id / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["successful_batch_completed_at"] = "2026-07-16T04:00:00+00:00"
    payload["available_at"] = "2026-07-16T12:00:00+08:00"
    changed = json.dumps(payload, sort_keys=True).encode()
    manifest.write_bytes(changed)
    with pytest.raises(ValueError, match="成功批次時間"):
        statement.read_research_snapshot(
            root, saved.snapshot_id,
            expected_manifest_sha256=sha256(changed).hexdigest(),
            decision_at=datetime.fromisoformat("2026-10-16T14:00:00+00:00"),
        )
