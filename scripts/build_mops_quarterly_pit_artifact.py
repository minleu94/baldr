"""Build a research-only PIT source artifact from a saved MOPS document listing."""
from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit


SOURCE_ID = "mops.statement.publication"
SOURCE_VERSION = "mops-electronic-document-listing.v1"
LISTING_URL_PREFIX = "https://doc.twse.com.tw/server-java/t57sb01"


def build_artifact(
    *,
    listing_html: Path,
    primary_pdf: Path,
    captured_at: str,
    mops_announcement_artifact: Path,
    source_url: str | None = None,
) -> dict[str, Any]:
    """Parse one Chinese consolidated MOPS listing row; fail closed on ambiguity."""
    _parse_iso_timestamp(captured_at)
    text = listing_html.read_bytes().decode("big5")
    source_url = _extract_source_url(text, fallback=source_url)
    stock_codes = re.findall(r"name=['\"]co_id['\"]\s+value=['\"](\d+)['\"]", text)
    if not stock_codes:
        stock_codes = parse_qs(urlsplit(source_url).query).get("co_id", [])
    stock_code = _one(stock_codes, "stock code")
    query_stock_code = _one(parse_qs(urlsplit(source_url).query).get("co_id", []), "stock code in T57 source URL")
    if query_stock_code != stock_code:
        raise ValueError("T57 source URL company does not match listing company")
    company_rows = re.findall(
        r"<tr\b[^>]*>\s*<td\s+align=['\"]center['\"]>" + re.escape(stock_code) + r"</td>(.*?)</tr>",
        text,
        re.DOTALL,
    )
    chinese_consolidated_rows = [
        candidate for candidate in company_rows
        if "IFRSs合併財報" in candidate and "IFRSs英文版" not in candidate
    ]
    rows_for_primary_pdf = [
        candidate for candidate in chinese_consolidated_rows
        if primary_pdf.name in re.findall(
            r'readfile2\([^)]*(?:&quot;|\")([^&\"]+\.pdf)(?:&quot;|\")', candidate
        )
    ]
    row = _one(rows_for_primary_pdf, "Chinese IFRSs consolidated report row matching primary filename")
    year = int(_one(re.findall(r"(\d{3})\s*年\s*第?\s*[一二三四]季", row), "ROC year in report row"))
    filename = _one(re.findall(r'readfile2\([^)]*(?:&quot;|\")([^&\"]+\.pdf)(?:&quot;|\")', row), "primary document filename")
    if primary_pdf.name != filename:
        raise ValueError("primary PDF filename does not match MOPS listing")
    upload = _one(re.findall(r"(\d{3})/(\d{2})/(\d{2})\s+(\d{2}:\d{2}:\d{2})", row), "upload timestamp")
    t57_upload_at = _roc_timestamp_to_iso(upload)
    if not re.search(r">\s*無\s*</td>\s*$", row):
        raise ValueError("listing row is corrected or correction status is ambiguous")
    quarter_number = _one(re.findall(r"第?\s*([一二三四])季", row), "quarter")
    quarter = f"第{quarter_number}季"
    period, period_end = _period_for(year, quarter)
    mops_announcement_at, announcement_evidence = _match_mops_announcement(
        mops_announcement_artifact, stock_code=stock_code, period=period
    )
    listing_hash = _sha256_file(listing_html)
    document_hash = _sha256_file(primary_pdf)
    return {
        "source_id": SOURCE_ID,
        "source_version": SOURCE_VERSION,
        "captured_at": captured_at,
        "research_only": True,
        "formal_oos_allowed": False,
        "production_scheduler_allowed": False,
        "downstream_eligibility": "none",
        "source_url": source_url,
        "listing_sha256": listing_hash,
        "rows": [{
            "stock_code": stock_code,
            "statement_type": "financial_report",
            "statement_scope": "consolidated",
            "period": period,
            "period_end": period_end,
            "announcement_date": mops_announcement_at,
            "available_date": t57_upload_at,
            "t57_upload_at": t57_upload_at,
            "mops_announcement_evidence": announcement_evidence,
            "revision": 1,
            "content_hash": document_hash,
            "document_bytes_verification": "unverified",
            "document_filename": filename,
            "document_size_bytes": primary_pdf.stat().st_size,
            "listing_sha256": listing_hash,
            "correction_status": "none",
        }],
    }


def _extract_source_url(text: str, *, fallback: str | None = None) -> str:
    embedded = re.findall(r"<!-- saved from url=\(\d+\)(https://[^ ]+) -->", text)
    value = _one(embedded, "saved source URL") if embedded else fallback
    if not isinstance(value, str):
        raise ValueError("listing HTML has no saved source URL; provide the manifest source URL")
    if not value.startswith(LISTING_URL_PREFIX):
        raise ValueError("unexpected MOPS listing URL")
    return value


def _one(values: list[Any], label: str) -> Any:
    unique = list(dict.fromkeys(values))
    if len(unique) != 1:
        raise ValueError(f"expected exactly one {label}")
    return unique[0]


def _roc_timestamp_to_iso(parts: tuple[str, str, str, str]) -> str:
    year, month, day, clock = parts
    return f"{int(year) + 1911:04d}-{month}-{day}T{clock}+08:00"


def _period_for(roc_year: int, quarter: str) -> tuple[str, str]:
    number = {"第一季": 1, "第二季": 2, "第三季": 3, "第四季": 4}.get(quarter)
    if number is None:
        raise ValueError("unsupported quarter")
    end_month = number * 3
    end_day = (31, 30, 30, 31)[number - 1]
    gregorian_year = roc_year + 1911
    return f"{gregorian_year}-Q{number}", f"{gregorian_year:04d}-{end_month:02d}-{end_day:02d}"


def _parse_iso_timestamp(value: str) -> None:
    if datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None:
        raise ValueError("captured_at must include a timezone")


def _match_mops_announcement(artifact_path: Path, *, stock_code: str, period: str) -> tuple[str, dict[str, Any]]:
    """Require same-company, same-quarter MOPS F26–F29 events with one timestamp."""
    payload = json.loads(artifact_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("source_id") != "mops.ezsearch.statement_publication":
        raise ValueError("announcement artifact must use the MOPS EZSearch publication source")
    if payload.get("research_only") is not True or payload.get("formal_credit_authorized") is not False:
        raise ValueError("MOPS announcement artifact must retain its research-only boundary")
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("MOPS announcement artifact must contain a rows list")
    matched = [
        row for row in rows
        if isinstance(row, dict)
        and str(row.get("stock_code", "")).zfill(4) == stock_code
        and row.get("period") == period
        and row.get("announcement_item") in {"F26", "F27", "F28", "F29"}
    ]
    if not matched:
        raise ValueError("no same-company, same-period MOPS quarterly announcement found")
    timestamps = {_validated_iso_timestamp(row.get("announcement_at")) for row in matched}
    if len(timestamps) != 1:
        raise ValueError("matched MOPS quarterly statements have conflicting announcement timestamps")
    hashes = sorted({str(row.get("event_hash", "")) for row in matched})
    if any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes):
        raise ValueError("matched MOPS announcement event is missing a valid event hash")
    artifact_hash = _sha256_file(artifact_path)
    return next(iter(timestamps)), {
        "source_id": "mops.ezsearch.statement_publication",
        "source_artifact_sha256": artifact_hash,
        "matched_event_hashes": hashes,
        "matched_items": sorted({str(row["announcement_item"]) for row in matched}),
    }


def _validated_iso_timestamp(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("MOPS announcement_at must be an ISO timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("MOPS announcement_at must include a timezone")
    return value


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listing-html", type=Path, required=True)
    parser.add_argument("--primary-pdf", type=Path, required=True)
    parser.add_argument("--captured-at", required=True)
    parser.add_argument(
        "--mops-announcement-artifact",
        type=Path,
        required=True,
        help="Saved MOPS announcement artifact used to match company and quarter",
    )
    parser.add_argument("--source-url", help="T57 listing URL from the source manifest, if absent from saved HTML")
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    artifact = build_artifact(
        listing_html=args.listing_html,
        primary_pdf=args.primary_pdf,
        captured_at=args.captured_at,
        mops_announcement_artifact=args.mops_announcement_artifact,
        source_url=args.source_url,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
