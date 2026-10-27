from pathlib import Path

import pytest
import json

from scripts.build_mops_quarterly_pit_artifact import build_artifact


def _listing() -> bytes:
    return b'''<!-- saved from url=(0097)https://doc.twse.com.tw/server-java/t57sb01?step=1&colorchg=1&mtype=A&co_id=2330&year=115 -->
<input type="hidden" name="co_id" value="2330"><input type="hidden" name="year" value="115">
<tr><td align="center">2330</td><td>115 \xa6~ \xb2\xc4\xa4@\xa9u</td><td>IFRSs\xa6X\xa8\xd6\xb0]\xb3\xf8</td><td><a href="javascript:readfile2(&quot;A&quot;,&quot;2330&quot;,&quot;202601_2330_AI1.pdf&quot;);">202601_2330_AI1.pdf</a></td><td>115/05/15 14:43:02</td><td align="center">\xb5L</td></tr>'''


def test_builds_traceable_chinese_consolidated_artifact(tmp_path: Path) -> None:
    listing = tmp_path / "listing.html"
    listing.write_bytes(_listing())
    report = tmp_path / "202601_2330_AI1.pdf"
    report.write_bytes(b"official-pdf")
    mops = tmp_path / "mops.json"
    mops.write_text(json.dumps({"source_id": "mops.ezsearch.statement_publication", "research_only": True,
        "formal_credit_authorized": False, "rows": [
        {"stock_code": "2330", "period": "2026-Q1", "announcement_item": item,
         "announcement_at": "2026-05-15T16:01:02+08:00", "event_hash": str(index) * 64}
        for index, item in enumerate(("F26", "F27", "F28", "F29"), start=1)
    ]}), encoding="utf-8")
    artifact = build_artifact(
        listing_html=listing,
        primary_pdf=report,
        captured_at="2026-07-19T18:22:14-07:00",
        mops_announcement_artifact=mops,
    )
    row = artifact["rows"][0]
    assert row["period"] == "2026-Q1"
    assert row["period_end"] == "2026-03-31"
    assert row["announcement_date"] == "2026-05-15T16:01:02+08:00"
    assert row["available_date"] == "2026-05-15T14:43:02+08:00"
    assert row["t57_upload_at"] == "2026-05-15T14:43:02+08:00"
    assert row["mops_announcement_evidence"]["matched_items"] == ["F26", "F27", "F28", "F29"]
    assert row["document_bytes_verification"] == "unverified"
    assert row["correction_status"] == "none"
    assert len(row["content_hash"]) == 64


def test_rejects_mismatched_primary_filename(tmp_path: Path) -> None:
    listing = tmp_path / "listing.html"
    listing.write_bytes(_listing())
    report = tmp_path / "wrong.pdf"
    report.write_bytes(b"official-pdf")
    with pytest.raises(ValueError, match="filename"):
        build_artifact(
            listing_html=listing,
            primary_pdf=report,
            captured_at="2026-07-19T18:22:14-07:00",
            mops_announcement_artifact=tmp_path / "missing.json",
        )


def test_rejects_t57_source_url_for_another_company(tmp_path: Path) -> None:
    listing = tmp_path / "listing.html"
    listing.write_bytes(_listing().replace(b"co_id=2330", b"co_id=2317"))
    report = tmp_path / "202601_2330_AI1.pdf"
    report.write_bytes(b"official-pdf")
    with pytest.raises(ValueError, match="source URL company"):
        build_artifact(
            listing_html=listing,
            primary_pdf=report,
            captured_at="2026-07-19T18:22:14-07:00",
            mops_announcement_artifact=tmp_path / "missing.json",
        )


def test_accepts_manifest_source_url_when_saved_html_has_no_browser_comment(tmp_path: Path) -> None:
    listing = tmp_path / "listing.html"
    listing.write_bytes(_listing().replace(
        b"<!-- saved from url=(0097)https://doc.twse.com.tw/server-java/t57sb01?step=1&colorchg=1&mtype=A&co_id=2330&year=115 -->\n",
        b"",
    ))
    report = tmp_path / "202601_2330_AI1.pdf"
    report.write_bytes(b"official-pdf")
    mops = tmp_path / "mops.json"
    mops.write_text(json.dumps({"source_id": "mops.ezsearch.statement_publication", "research_only": True,
        "formal_credit_authorized": False, "rows": [{
        "stock_code": "2330", "period": "2026-Q1", "announcement_item": "F27",
        "announcement_at": "2026-05-15T16:01:02+08:00", "event_hash": "a" * 64,
    }]}), encoding="utf-8")
    artifact = build_artifact(
        listing_html=listing,
        primary_pdf=report,
        captured_at="2026-07-19T18:22:14-07:00",
        mops_announcement_artifact=mops,
        source_url="https://doc.twse.com.tw/server-java/t57sb01?step=1&colorchg=1&mtype=A&co_id=2330&year=115",
    )
    assert artifact["source_url"].startswith("https://doc.twse.com.tw/server-java/t57sb01?")


def test_parses_t57_page_dialect_and_selects_pdf_quarter(tmp_path: Path) -> None:
    listing = tmp_path / "listing.html"
    listing.write_bytes("""<input type='hidden' name='co_id'>
<tr><td align='center'>2330</td><td align='center'>115 年 第一季</td>
<td align='center'>財務報告書</td><td align='center'>IFRSs合併財報</td>
<td><a href='javascript:readfile2(\"A\",\"2330\",\"202601_2330_AI1.pdf\");'>202601_2330_AI1.pdf</a></td>
<td>115/05/15 14:43:02</td><td align='center'>無</td></tr>
<tr><td align='center'>2330</td><td align='center'>115 年 第二季</td>
<td align='center'>財務報告書</td><td align='center'>IFRSs合併財報</td>
<td><a href='javascript:readfile2(\"A\",\"2330\",\"202602_2330_AI1.pdf\");'>202602_2330_AI1.pdf</a></td>
<td>115/08/14 13:59:44</td><td align='center'>無</td></tr>""".encode("big5"))
    report = tmp_path / "202602_2330_AI1.pdf"
    report.write_bytes(b"candidate-pdf")
    mops = tmp_path / "mops.json"
    mops.write_text(json.dumps({"source_id": "mops.ezsearch.statement_publication", "research_only": True,
        "formal_credit_authorized": False, "rows": [{
        "stock_code": "2330", "period": "2026-Q2", "announcement_item": "F27",
        "announcement_at": "2026-08-14T13:46:30+08:00", "event_hash": "b" * 64,
    }]}), encoding="utf-8")
    artifact = build_artifact(
        listing_html=listing,
        primary_pdf=report,
        captured_at="2026-10-26T14:00:00-07:00",
        mops_announcement_artifact=mops,
        source_url="https://doc.twse.com.tw/server-java/t57sb01?step=1&colorchg=1&mtype=A&co_id=2330&year=115",
    )
    row = artifact["rows"][0]
    assert row["period"] == "2026-Q2"
    assert row["announcement_date"] == "2026-08-14T13:46:30+08:00"
    assert row["available_date"] == "2026-08-14T13:59:44+08:00"


def test_rejects_mops_announcement_for_another_period(tmp_path: Path) -> None:
    listing = tmp_path / "listing.html"
    listing.write_bytes(_listing())
    report = tmp_path / "202601_2330_AI1.pdf"
    report.write_bytes(b"official-pdf")
    mops = tmp_path / "mops.json"
    mops.write_text(json.dumps({"source_id": "mops.ezsearch.statement_publication", "research_only": True,
        "formal_credit_authorized": False, "rows": [{
        "stock_code": "2330", "period": "2026-Q2", "announcement_item": "F27",
        "announcement_at": "2026-08-14T13:46:30+08:00", "event_hash": "a" * 64,
    }]}), encoding="utf-8")
    with pytest.raises(ValueError, match="same-company, same-period"):
        build_artifact(
            listing_html=listing,
            primary_pdf=report,
            captured_at="2026-07-19T18:22:14-07:00",
            mops_announcement_artifact=mops,
        )


def test_rejects_mops_artifact_that_drops_research_only_boundary(tmp_path: Path) -> None:
    listing = tmp_path / "listing.html"
    listing.write_bytes(_listing())
    report = tmp_path / "202601_2330_AI1.pdf"
    report.write_bytes(b"official-pdf")
    mops = tmp_path / "mops.json"
    mops.write_text(json.dumps({"source_id": "not-mops", "rows": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="MOPS EZSearch publication source"):
        build_artifact(
            listing_html=listing,
            primary_pdf=report,
            captured_at="2026-07-19T18:22:14-07:00",
            mops_announcement_artifact=mops,
        )
