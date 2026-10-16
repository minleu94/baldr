"""台積電 2026 Q2 IR 簡明財報的有界研究讀取器。

此契約只辨認具名發行人、報告與版型；不推論 MOPS OpenAPI 的單位，
也不授予正式來源用途或歷史 PIT 資格。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any


SCHEMA_VERSION = "tsmc-ir-condensed-statement-q2-2026.v1"
STOCK_CODE = "2330"
REPORT_PERIOD = "2026-Q2"
SOURCE_PDF_URL = (
    "https://investor.tsmc.com/english/encrypt/files/encrypt_file/reports/"
    "2026-07/114aaca0fea2050e96b91fffbab9ed04ba09cd92/FS.pdf"
)
SOURCE_PDF_SHA256 = "a55d6aca73ba6246385d885fbb41a4efa55c92033cb644b48fda671814e0754f"
SOURCE_RECEIPT_SHA256 = "ffa03fef8a4dff69e152ee76b7a1ff74d7a3a1a14bb685c625e426be5affaab9"
SOURCE_PDF_BYTES = 127130
SOURCE_RECEIPT_BYTES = 1231
SOURCE_PAGE_URL = "https://investor.tsmc.com/english/quarterly-results/2026/q2"
ISSUER_IDENTITY_URL = "https://investor.tsmc.com/english/shareholder-services/stock-quotes"
_TAIPEI = timezone(timedelta(hours=8))
_ENTITY = "TAIWAN SEMICONDUCTOR MANUFACTURING COMPANY LIMITED AND SUBSIDIARIES"
_UNIT = 'Expressed in Millions of New Taiwan Dollars ("NTD")'
_NUMBER = re.compile(r"(?<![A-Za-z])[\(\-]?[\d,]+(?:\.\d+)?\)?")


@dataclass(frozen=True)
class CondensedStatementValue:
    metric: str
    period: str
    period_basis: str
    value_ntd_million: int
    source_page: int
    role: str


@dataclass(frozen=True)
class CondensedStatementSnapshot:
    snapshot_id: str
    raw_sha256: str
    manifest_sha256: str
    available_at: datetime
    values: tuple[CondensedStatementValue, ...]
    candidate_only: bool = True
    source_use_accepted: bool = False
    historical_pit_eligible: bool = False


def parse_q2_2026_pdf(raw: bytes) -> tuple[CondensedStatementValue, ...]:
    """嚴格擷取該版官方四頁表；任一單位、期間或勾稽失敗即拒讀。"""

    if not raw.startswith(b"%PDF-") or b"%%EOF" not in raw[-1024:]:
        raise ValueError("財報 PDF 原件不完整")
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise RuntimeError("缺少 pypdf，不能擷取官方財報") from error
    from io import BytesIO

    reader = PdfReader(BytesIO(raw), strict=True)
    if len(reader.pages) != 4:
        raise ValueError("台積電 2026 Q2 簡明財報頁數不符")
    pages = tuple(page.extract_text() or "" for page in reader.pages)
    return parse_q2_2026_pages(pages)


def parse_q2_2026_pages(pages: tuple[str, ...]) -> tuple[CondensedStatementValue, ...]:
    """僅接受已核版型；保留原 PDF 的百萬元整數顯示精度。"""

    if len(pages) != 4:
        raise ValueError("財報頁數不符")
    balance, quarter, half_year, _ = pages
    for page in pages[:3]:
        if _ENTITY not in page or _UNIT not in page or "Unaudited" not in page:
            raise ValueError("發行人、單位或審計狀態未核實")
    if not all(text in balance for text in (
        "Consolidated Condensed Balance Sheet", "June 30, 2026",
        "March 31, 2026", "June 30, 2025",
    )):
        raise ValueError("資產負債表日期或基礎不符")
    if not all(text in quarter for text in (
        "For the Three Months Ended June 30, 2026, March 31, 2026 and June 30, 2025",
        "2Q 2026 1Q 2026 2Q 2025",
    )):
        raise ValueError("單季損益期間不符")
    if not all(text in half_year for text in (
        "For the Six Months Ended June 30", "2026 2025 YoY",
    )):
        raise ValueError("半年累計期間不符")

    assets = _money_columns(balance, "Total Assets", count=3)
    liabilities = _money_columns(balance, "Total Liabilities", count=3)
    equity = _money_columns(balance, "Total Shareholders' Equity", count=3)
    quarter_revenue = _money_columns(quarter, "Net Revenue", count=3)
    quarter_income = _money_columns(quarter, "Net Income", count=3)
    half_revenue = _money_columns(half_year, "Net Revenue", count=2)
    half_income = _money_columns(half_year, "Net Income", count=2)
    if any(asset != debt + capital for asset, debt, capital in zip(assets, liabilities, equity)):
        raise ValueError("資產負債表未勾稽")
    if (quarter_revenue[0] + quarter_revenue[1] != half_revenue[0]
            or quarter_income[0] + quarter_income[1] != half_income[0]):
        raise ValueError("單季與半年累計未勾稽")

    values: list[CondensedStatementValue] = []
    for metric, amounts, page_number, basis, periods, roles in (
        ("total_assets", assets, 1, "period_end",
         ("2026-06-30", "2026-03-31", "2025-06-30"),
         ("current", "previous_quarter", "year_ago")),
        ("net_revenue", quarter_revenue, 2, "single_quarter",
         ("2026-Q2", "2026-Q1", "2025-Q2"),
         ("current", "previous_quarter", "year_ago")),
        ("net_income", quarter_income, 2, "single_quarter",
         ("2026-Q2", "2026-Q1", "2025-Q2"),
         ("current", "previous_quarter", "year_ago")),
        ("net_revenue", half_revenue, 3, "year_to_date_cumulative",
         ("2026-H1", "2025-H1"), ("current", "year_ago")),
        ("net_income", half_income, 3, "year_to_date_cumulative",
         ("2026-H1", "2025-H1"), ("current", "year_ago")),
    ):
        values.extend(
            CondensedStatementValue(metric, period, basis, amount, page_number, role)
            for amount, period, role in zip(amounts, periods, roles)
        )
    return tuple(values)


def _money_columns(page: str, label: str, *, count: int) -> tuple[int, ...]:
    row_start = re.compile(rf"^{re.escape(label)}\s+(?:\$|\d)")
    lines = [line.strip() for line in page.splitlines() if row_start.match(line.strip())]
    if len(lines) != 1:
        raise ValueError(f"財報欄位 {label} 缺失或重複")
    # 第一個金額是 USD 翻譯欄；其後 NTD 欄與百分比交替。
    numbers = [match.group() for match in _NUMBER.finditer(lines[0][len(label):])]
    indices = tuple(1 + 2 * index for index in range(count))
    if len(numbers) <= indices[-1]:
        raise ValueError(f"財報欄位 {label} 缺少 NTD 比較欄")
    amounts: list[int] = []
    for index in indices:
        value = numbers[index].replace(",", "")
        if not value.isdigit():
            raise ValueError(f"財報欄位 {label} 金額非正整數")
        amounts.append(int(value))
    return tuple(amounts)


def _available_hour(completed_at: datetime) -> datetime:
    if completed_at.tzinfo is None:
        raise ValueError("成功批次時間必須有時區")
    local = completed_at.astimezone(_TAIPEI)
    hour = local.replace(minute=0, second=0, microsecond=0)
    return hour if local == hour else hour + timedelta(hours=1)


def _verified_receipt(receipt_bytes: bytes, raw: bytes) -> datetime:
    if sha256(receipt_bytes).hexdigest() != SOURCE_RECEIPT_SHA256:
        raise ValueError("財報 HTTP 收據外部 SHA pin 不符")
    receipt = json.loads(receipt_bytes)
    if (
        receipt.get("source_url") != SOURCE_PDF_URL
        or receipt.get("response_url") != SOURCE_PDF_URL
        or receipt.get("source_page_url") not in {
            SOURCE_PAGE_URL,
            "https://investor.tsmc.com/chinese/quarterly-results/2026/q2",
        }
        or receipt.get("status") != "complete_pdf_entity_for_research"
        or receipt.get("http_status") != 200
        or receipt.get("content_type") != "application/pdf"
        or receipt.get("saved_sha256") != SOURCE_PDF_SHA256
        or receipt.get("saved_bytes") != len(raw)
        or receipt.get("retry_count") != 0
        or receipt.get("formal_data_write") is not False
        or receipt.get("source_use_accepted") is not False
        or receipt.get("historical_pit_eligible") is not False
    ):
        raise ValueError("財報 HTTP 收據與原件或隔離用途不符")
    completed_at = datetime.fromisoformat(receipt["finished_at_utc"])
    if completed_at.tzinfo is None:
        raise ValueError("財報取得完成時間沒有時區")
    return completed_at


def save_research_snapshot(
    raw_pdf: Path,
    source_receipt: Path,
    snapshot_root: Path,
) -> CondensedStatementSnapshot:
    """在隔離根 create-only 保存原件與衍生版；不修改正式來源庫。"""

    if raw_pdf.stat().st_size != SOURCE_PDF_BYTES or source_receipt.stat().st_size != SOURCE_RECEIPT_BYTES:
        raise ValueError("財報 PDF 或 HTTP 收據原件長度不符")
    raw = raw_pdf.read_bytes()
    digest = sha256(raw).hexdigest()
    if digest != SOURCE_PDF_SHA256:
        raise ValueError("財報 PDF 外部 SHA pin 不符")
    receipt_bytes = source_receipt.read_bytes()
    completed_at = _verified_receipt(receipt_bytes, raw)
    values = parse_q2_2026_pdf(raw)
    available_at = _available_hour(completed_at)
    snapshot_id = f"tsmc-2330-2026q2-{digest[:16]}"
    folder = snapshot_root / snapshot_id
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "source.pdf").write_bytes(raw)
    (folder / "receipt.json").write_bytes(receipt_bytes)
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "stock_code": STOCK_CODE,
        "report_period": REPORT_PERIOD,
        "source_page_url": SOURCE_PAGE_URL,
        "source_pdf_url": SOURCE_PDF_URL,
        "issuer_identity_url": ISSUER_IDENTITY_URL,
        "source_pdf_sha256": digest,
        "source_pdf_bytes": len(raw),
        "source_receipt_sha256": SOURCE_RECEIPT_SHA256,
        "successful_batch_completed_at": completed_at.isoformat(),
        "official_publication_timestamp_original": None,
        "available_at": available_at.isoformat(),
        "available_at_basis": "successful_batch_completion_fallback",
        "value_unit": "NTD_million_as_reported",
        "candidate_only": True,
        "source_use_accepted": False,
        "historical_pit_eligible": False,
        "values": [asdict(value) for value in values],
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    with (folder / "manifest.json").open("xb") as output:
        output.write(manifest_bytes)
    return CondensedStatementSnapshot(
        snapshot_id, digest, sha256(manifest_bytes).hexdigest(), available_at, values,
    )


def read_research_snapshot(
    snapshot_root: Path,
    snapshot_id: str,
    *,
    expected_manifest_sha256: str,
    decision_at: datetime,
) -> CondensedStatementSnapshot:
    """以外部 manifest pin 唯讀重驗原件、值與前瞻小時。"""

    if not re.fullmatch(r"tsmc-2330-2026q2-[0-9a-f]{16}", snapshot_id):
        raise ValueError("財報 snapshot ID 不符")
    if decision_at.tzinfo is None:
        raise ValueError("研究時間必須有時區")
    folder = snapshot_root / snapshot_id
    manifest_path = folder / "manifest.json"
    if manifest_path.stat().st_size > 65536:
        raise ValueError("財報 manifest 大小超出有界讀取")
    manifest_bytes = manifest_path.read_bytes()
    manifest_sha = sha256(manifest_bytes).hexdigest()
    if manifest_sha != expected_manifest_sha256:
        raise ValueError("財報 manifest 外部 SHA pin 不符")
    manifest = json.loads(manifest_bytes)
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("snapshot_id") != snapshot_id
        or manifest.get("stock_code") != STOCK_CODE
        or manifest.get("report_period") != REPORT_PERIOD
        or manifest.get("source_page_url") != SOURCE_PAGE_URL
        or manifest.get("source_pdf_url") != SOURCE_PDF_URL
        or manifest.get("issuer_identity_url") != ISSUER_IDENTITY_URL
        or manifest.get("available_at_basis") != "successful_batch_completion_fallback"
        or manifest.get("official_publication_timestamp_original") is not None
        or manifest.get("value_unit") != "NTD_million_as_reported"
        or manifest.get("candidate_only") is not True
        or manifest.get("source_use_accepted") is not False
        or manifest.get("historical_pit_eligible") is not False
    ):
        raise ValueError("財報來源契約或隔離旗標不符")
    raw_path = folder / "source.pdf"
    if raw_path.stat().st_size != SOURCE_PDF_BYTES:
        raise ValueError("財報原件長度不符")
    raw = raw_path.read_bytes()
    digest = sha256(raw).hexdigest()
    if (
        digest != SOURCE_PDF_SHA256
        or digest != manifest.get("source_pdf_sha256")
        or len(raw) != manifest.get("source_pdf_bytes")
    ):
        raise ValueError("財報原件 SHA 或長度不符")
    if snapshot_id != f"tsmc-2330-2026q2-{digest[:16]}":
        raise ValueError("財報 snapshot ID 與原件不符")
    receipt_path = folder / "receipt.json"
    if receipt_path.stat().st_size != SOURCE_RECEIPT_BYTES:
        raise ValueError("財報 HTTP 收據長度不符")
    receipt_bytes = receipt_path.read_bytes()
    if manifest.get("source_receipt_sha256") != SOURCE_RECEIPT_SHA256:
        raise ValueError("財報 HTTP 收據版本不符")
    completed_at = _verified_receipt(receipt_bytes, raw)
    if manifest.get("successful_batch_completed_at") != completed_at.isoformat():
        raise ValueError("財報成功批次時間與 HTTP 收據不符")
    available_at = _available_hour(completed_at)
    if manifest.get("available_at") != available_at.isoformat():
        raise ValueError("財報可用小時不符")
    if decision_at.astimezone(_TAIPEI) < available_at:
        raise ValueError("財報尚未到前瞻可用小時")
    values = parse_q2_2026_pdf(raw)
    if manifest.get("values") != [asdict(value) for value in values]:
        raise ValueError("財報衍生值與原 PDF 不符")
    return CondensedStatementSnapshot(snapshot_id, digest, manifest_sha, available_at, values)
