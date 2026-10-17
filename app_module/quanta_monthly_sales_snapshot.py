"""明選廣達2026月營收原件的目前研究版本；不供歷史PIT或策略。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from app_module.position_health_saved_archive import _create_immutable_bytes
from app_module.recommendation_portfolio_calendar_artifact_v1 import _canonical_path, _decode_object, _read_exact_file
from data_module.daily_source_snapshot import (
    DAILY_SOURCE_TIME_BASIS_POLICY, DailySourceUseAcceptance, DailySourceUseScope, _batch_publish_guard_hour,
)

SCHEMA = "quanta-monthly-sales-2382-2026.v1"
SOURCE_URL = "https://www.quantatw.com/quanta/english/investment/financials_ms.aspx"
IDENTITY_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
PARSER = "quanta-adjusted-consolidated-monthly-sales.v1"
_TAIPEI = ZoneInfo("Asia/Taipei")
_DEFAULT_FORMAL_ROOT = Path("D:/Min/Python/Project/FA_Data").absolute()
_HASH = re.compile(r"[0-9a-f]{64}")
_FILES = {
    "monthly.raw": "90399130663acffc144445118a393f134174baf8185653ca169ca0c0fb8b919b",
    "monthly-http.json": "5b23cf494502a4d5005cb214c75e89dc198e0f4dfe03c7c6be245f2271c5e1ff",
    "twse-company.raw.json": "a13c8f3a0990ed0b65f1b58961bf1548e87090364f1dc8a8449960c95fc053e6",
    "identity-publication.json": "68e6c89fbe5bcc5f2d47bfd478ccd39e5e1466230592da82889a4be47e0a3f26",
    "identity-receipt.json": "31fc9c72123fb553c443c990ce17de6c3d6eb64a3624d69ddf47aa892cd940d7",
    "identity-archive.json": "25471e473986897c7ce1bb3bc87236294883251a8902152a08c391b47aa6dd50",
}
SCOPE = DailySourceUseScope(SCHEMA, "issuer.quanta.monthly_sales", "twse", PARSER,
    SCHEMA, "TWD_million;percent", "current_stock_research")
ATTRIBUTION = "廣達電腦官方投資人月營收頁；公司代碼／網站依TWSE公司基本資料原件核對。"
LIMITATIONS = (
    "只供2382、明選2026固定版本的本機目前研究；金額為原披露百萬元整數，百分比為原披露0.1%。",
    "兩年均為同表Adjusted Consolidated口徑；不混入另張2025表或由月度加總推算累計。",
    "沒有原發布／更新timestamp；可得時間依本次完整保存批次台北小時，公告日保持未提供。",
    "不授歷史PIT、評分、篩選、聚合、策略、ML、Paper、交易或對外散布資格。",
    "2382半年財報缺件維持隔離；本頁月營收不能替代該財報或前期比較。",
)
_EVIDENCE = {"schema": SCHEMA, "parser": PARSER, "source_url": SOURCE_URL,
    "identity_url": IDENTITY_URL, "issuer": "廣達電腦股份有限公司", "stock_code": "2382",
    "unit_basis": "2026 Monthly Sales (Unit: NT $ Million)",
    "identity_use": "research_shadow_identity_only", "local_research_only": True,
    "redistribution_accepted": False, "historical_pit_accepted": False}


def _bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8")


def _object(raw: bytes) -> dict[str, Any]:
    return _decode_object(raw, label="quanta_monthly", maximum=2 * 1024 * 1024)


def _local(value: str | datetime) -> datetime:
    result = datetime.fromisoformat(value) if isinstance(value, str) else value
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("月營收時鐘須有時區")
    return result.astimezone(_TAIPEI)


def _read(path: Path, expected: str) -> bytes:
    raw, _ = _read_exact_file(_canonical_path(path, "quanta_monthly", allow_missing=False), maximum=2 * 1024 * 1024)
    if sha256(raw).hexdigest() != expected:
        raise ValueError("月營收原件SHA不符：" + path.name)
    return raw


def _money(text: str) -> Decimal:
    if not re.fullmatch(r"(?:0|[1-9][0-9]{0,13}|[1-9][0-9]{0,2}(?:,[0-9]{3}){1,4})", text):
        raise ValueError("月營收金額須為原披露非負整數百萬元")
    return Decimal(text.replace(",", ""))


def _rate(text: str) -> Decimal:
    if not re.fullmatch(r"-?[0-9]{1,6}\.[0-9]%", text):
        raise ValueError("月營收百分比須保留原披露0.1%")
    return Decimal(text[:-1])


def _latest_values(raw: bytes) -> tuple[str, tuple[Decimal, ...]]:
    soup = BeautifulSoup(raw.decode("utf-8-sig"), "html.parser")
    blocks = soup.find_all("div", id="2026")
    if len(blocks) != 1 or len(blocks[0].find_all("table")) != 1:
        raise ValueError("月營收年度表不唯一")
    table = blocks[0].find("table")
    if table is None:
        raise ValueError("月營收年度缺表")
    rows = table.find_all("tr")
    text = lambda cell: " ".join(cell.get_text(" ", strip=True).split())
    if text(rows[0]) != _EVIDENCE["unit_basis"]:
        raise ValueError("月營收原件年度／幣別／百萬元單位不符")
    headers = [text(cell) for cell in rows[1].find_all("th")]
    if headers != ["Month", "2026 Adjusted Consolidated", "2025 Adjusted Consolidated", "MoM", "YoY", "YTD YoY"]:
        raise ValueError("月營收同表兩年調整後合併口徑不符")
    months = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
    if len(rows) != 15:
        raise ValueError("月營收表月份／總計列不完整")
    populated: list[tuple[Decimal, Decimal, Decimal, Decimal]] = []
    empty_seen = False
    for month, row in zip(months, rows[2:14]):
        cells = [text(cell) for cell in row.find_all("td")]
        if len(cells) == 7 and cells[-1] == "":
            cells.pop()  # 原頁部分月份多一個空白儲存格；非空白不忽略。
        if len(cells) != 6 or cells[0] != month:
            raise ValueError("月營收月份／欄位錯位")
        if not any(cells[1:]):
            empty_seen = True
            continue
        if empty_seen or not all(cells[1:]):
            raise ValueError("月營收缺月或部分欄位缺失")
        populated.append((_money(cells[1]), _money(cells[2]), _rate(cells[3]), _rate(cells[4])))
        _rate(cells[5])
    if len(populated) < 2 or text(rows[14].find("td")) != "Total":
        raise ValueError("月營收缺同表前月或總計列")
    current, prior_year, mom, yoy = populated[-1]
    prior_month = populated[-2][0]
    # 只核原披露率與單位解析是否相容；不把推算值寫成展示指標。
    with localcontext() as context:
        context.prec = 50
        for base, reported in ((prior_month, mom), (prior_year, yoy)):
            if base <= 1:
                raise ValueError("月營收比較基期不可用")
            lower = ((max(Decimal(0), current - 1) / (base + 1)) - 1) * 100
            upper = (((current + 1) / (base - 1)) - 1) * 100
            if reported + Decimal("0.1") < lower or reported - Decimal("0.1") > upper:
                raise ValueError("月營收原披露率與同表基期不相容")
    return f"2026-{len(populated):02d}", (current, prior_month, prior_year, mom, yoy)


def _validate_files(files: Mapping[str, bytes]) -> datetime:
    if set(files) != set(_FILES) or any(sha256(files[name]).hexdigest() != digest for name, digest in _FILES.items()):
        raise ValueError("月營收原件集合／版本不符")
    transport = _object(files["monthly-http.json"])
    if (transport.get("official_url") != SOURCE_URL or transport.get("response_url") != SOURCE_URL
            or transport.get("response_status") != 200 or transport.get("response_body_complete") is not True
            or transport.get("response_body_eof") is not True or transport.get("raw_bytes") != len(files["monthly.raw"])
            or transport.get("raw_sha256") != _FILES["monthly.raw"]):
        raise ValueError("月營收HTTP端點／完整EOF不符")
    companies = json.loads(files["twse-company.raw.json"])
    issuer = [row for row in companies if row.get("公司代號") == "2382"]
    if len(issuer) != 1 or issuer[0].get("公司名稱") != _EVIDENCE["issuer"]:
        raise ValueError("TWSE公司代碼／法人身分不符")
    website = urlsplit("https://" + issuer[0].get("網址", ""))
    if website.hostname != "www.quantatw.com" or website.path not in ("", "/") or website.query or website.fragment or website.username or website.password or website.port:
        raise ValueError("TWSE公司網址不能綁定月營收官方網域")
    publication = _object(files["identity-publication.json"])
    identity = [item for item in publication["raw_inputs"] if item["path"] == "twse_t187ap03.raw.json"]
    if (len(identity) != 1 or identity[0]["content_sha256"] != "sha256:" + _FILES["twse-company.raw.json"]
            or identity[0]["http"]["http_status"] != 200
            or identity[0]["http"]["requested_url"] != IDENTITY_URL or identity[0]["http"]["final_url"] != IDENTITY_URL
            or "research_shadow" not in publication["license_scope"]["allowed_use_cases"]):
        raise ValueError("TWSE原件custody或身分審核用途不符")
    custody = _object(files["identity-receipt.json"])
    archive = _object(files["identity-archive.json"])
    required = {"twse_t187ap03.raw.json": "twse-company.raw.json", "pit-sector-membership-machine.json": "identity-publication.json", "receipt.json": "identity-receipt.json"}
    for original, name in required.items():
        entries = [entry for entry in archive["files"] if entry["relative_path"] == original]
        if len(entries) != 1 or entries[0]["archive_file_hash"] != "sha256:" + _FILES[name] or entries[0]["byte_count"] != len(files[name]):
            raise ValueError("TWSE身分原件封存鏈不符")
    if (custody.get("source_custody_verified") is not True or custody.get("candidate_only") is not True
            or archive.get("status") != "archived_candidate"):
        raise ValueError("TWSE身分審核原件資格不符")
    completed = _local(transport["ended_at"])
    if _local(transport["started_at"]) > completed:
        raise ValueError("月營收抓取時鐘倒退")
    period, _ = _latest_values(files["monthly.raw"])
    if period >= completed.strftime("%Y-%m"):
        raise ValueError("月營收包含尚未結束月份")
    return max(completed, _local(identity[0]["http"]["captured_at"]))


def _acceptance(at: datetime) -> DailySourceUseAcceptance:
    digest = sha256(_bytes(_EVIDENCE)).hexdigest()
    return DailySourceUseAcceptance(SCOPE, "root:quanta-monthly:" + digest, at, SOURCE_URL,
        (IDENTITY_URL, SOURCE_URL), "sha256:" + digest, "current_stock_research local_only")


@dataclass(frozen=True)
class QuantaMonthlySalesPin:
    directory: Path
    manifest_sha256: str
    receipt_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "directory", _canonical_path(self.directory, "quanta_monthly", allow_missing=False))
        if any(type(value) is not str or not _HASH.fullmatch(value) for value in (self.manifest_sha256, self.receipt_sha256)):
            raise ValueError("月營收需要外部manifest／receipt雙SHA")


def seal_quanta_monthly_sales(sources: Mapping[str, Path], *, output_directory: Path,
        clock: Callable[[], datetime] | None = None) -> QuantaMonthlySalesPin:
    """保存六份既存原件的新版本；不抓取，不寫正式／私人資料。"""
    target = _canonical_path(output_directory, "quanta_monthly", allow_missing=True)
    for value in (str(_DEFAULT_FORMAL_ROOT), os.getenv("DATA_ROOT"), os.getenv("OUTPUT_ROOT"), os.getenv("PERSONAL_DATA_ROOT"), os.getenv("PERSONAL_STORE_ROOT")):
        if value and (target.is_relative_to(Path(value).absolute()) or Path(value).absolute().is_relative_to(target)):
            raise ValueError("月營收版本不得寫入或包含正式／私人根")
    if set(sources) != set(_FILES) or os.path.lexists(target):
        raise ValueError("月營收須明選六份原件及全新目的目錄")
    files = {name: _read(Path(path), _FILES[name]) for name, path in sources.items()}
    original_complete = _validate_files(files)
    get_clock = clock or (lambda: datetime.now(timezone.utc))
    accepted = _local(get_clock())
    if accepted < original_complete:
        raise ValueError("月營收用途接受不能早於原件成功保存")
    target.mkdir(parents=True, exist_ok=False)
    pending = target / ".pending.json"
    _create_immutable_bytes(pending, _bytes({"schema": SCHEMA, "status": "pending"}))
    try:
        for name, raw in files.items():
            _create_immutable_bytes(target / name, raw)
        manifest = {"schema": SCHEMA, "evidence": _EVIDENCE, "source_use": _acceptance(accepted).to_dict(),
            "files": {name: {"bytes": len(raw), "sha256": _FILES[name]} for name, raw in files.items()}}
        raw_manifest = _bytes(manifest)
        _create_immutable_bytes(target / "manifest.json", raw_manifest)
        for name, path in sources.items():
            if _read(Path(path), _FILES[name]) != files[name] or _read(target / name, _FILES[name]) != files[name]:
                raise ValueError("月營收保存期間原件變更")
        completed = _local(get_clock())
        if completed < accepted:
            raise ValueError("月營收保存時鐘倒退")
        manifest_sha = sha256(raw_manifest).hexdigest()
        receipt = {"schema": SCHEMA, "manifest_sha256": manifest_sha, "original_capture_completed_at": original_complete.isoformat(),
            "first_persisted_at": accepted.isoformat(), "successful_batch_completed_at": completed.isoformat(),
            "available_hour": _batch_publish_guard_hour(completed).isoformat(), "availability_basis": "successful_batch_completion_fallback",
            "time_basis_policy": DAILY_SOURCE_TIME_BASIS_POLICY}
        raw_receipt = _bytes(receipt)
        _create_immutable_bytes(target / "receipt.json", raw_receipt)
        _read(target / "manifest.json", manifest_sha)
        receipt_sha = sha256(raw_receipt).hexdigest()
        _read(target / "receipt.json", receipt_sha)
        pending.unlink()
        return QuantaMonthlySalesPin(target, manifest_sha, receipt_sha)
    except Exception as error:
        _create_immutable_bytes(target / "failure.json", _bytes({"schema": SCHEMA, "reason": str(error)[:2048]}))
        raise


def read_quanta_monthly_sales(pin: QuantaMonthlySalesPin, *, cutoff_at: datetime) -> tuple[str, tuple[Decimal, ...], datetime]:
    """重驗固定原件、用途與真實可得時間；不把觀測版本倒填至過去。"""
    if type(pin) is not QuantaMonthlySalesPin:
        raise ValueError("月營收pin型別不符")
    if _local(cutoff_at) > datetime.now(_TAIPEI):
        raise ValueError("月營收研究截止不得晚於實際現在")
    if {entry.name for entry in pin.directory.iterdir()} != set(_FILES) | {"manifest.json", "receipt.json"}:
        raise ValueError("月營收集合有缺件／pending／failure")
    raw_manifest = _read(pin.directory / "manifest.json", pin.manifest_sha256)
    raw_receipt = _read(pin.directory / "receipt.json", pin.receipt_sha256)
    manifest = _object(raw_manifest)
    receipt = _object(raw_receipt)
    files = {name: _read(pin.directory / name, digest) for name, digest in _FILES.items()}
    original_complete = _validate_files(files)
    accepted = _local(manifest["source_use"]["accepted_at"])
    expected = {"schema": SCHEMA, "evidence": _EVIDENCE, "source_use": _acceptance(accepted).to_dict(),
        "files": {name: {"bytes": len(raw), "sha256": _FILES[name]} for name, raw in files.items()}}
    first, completed = _local(receipt["first_persisted_at"]), _local(receipt["successful_batch_completed_at"])
    available = _batch_publish_guard_hour(completed)
    if (manifest != expected or receipt != {"schema": SCHEMA, "manifest_sha256": pin.manifest_sha256,
            "original_capture_completed_at": original_complete.isoformat(), "first_persisted_at": first.isoformat(),
            "successful_batch_completed_at": completed.isoformat(), "available_hour": available.isoformat(),
            "availability_basis": "successful_batch_completion_fallback", "time_basis_policy": DAILY_SOURCE_TIME_BASIS_POLICY}
            or not original_complete <= accepted <= first <= completed):
        raise ValueError("月營收用途／保存／可得時間尚未核實")
    if _local(cutoff_at) < available:
        raise ValueError("尚未到月營收成功批次台北可用小時：" + available.isoformat())
    period, values = _latest_values(files["monthly.raw"])
    for name, digest in _FILES.items():
        _read(pin.directory / name, digest)
    _read(pin.directory / "manifest.json", pin.manifest_sha256)
    _read(pin.directory / "receipt.json", pin.receipt_sha256)
    if {entry.name for entry in pin.directory.iterdir()} != set(_FILES) | {"manifest.json", "receipt.json"}:
        raise ValueError("月營收讀取期間集合變更")
    return period, values, available
