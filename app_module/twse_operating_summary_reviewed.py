"""沿原營益版本封存具名三公司用途；發行人文件只作勾稽，不供產品值。"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, DecimalException, localcontext
from io import StringIO
import os
from pathlib import Path
from typing import Callable

from app_module import twse_operating_summary_snapshot as base
from app_module.recommendation_portfolio_calendar_artifact_v1 import _canonical_path, _decode_object
from data_module.daily_source_snapshot import (
    DAILY_SOURCE_TIME_BASIS_POLICY, DailySourceUseAcceptance, DailySourceUseScope, _batch_publish_guard_hour,
)

SCHEMA = "twse-operating-summary-reviewed-2026h1.v1"
REVIEWED_COMPANIES = {"2317": "鴻海", "2330": "台積電", "2454": "聯發科"}
LIMITATIONS = (
    "只接受2317、2330、2454的2026上半年與明選CSV版本，不代表全資料集或每日更新已核實。",
    "期間與TWD單位由各發行人半年合併財報勾稽；稅後率為合併本期損益，非母公司歸屬淨利率。",
    "原營收精度為0.01百萬元；利潤率沿CSV顯示精度，不用PDF增加精度或補前期值。",
    "前期與其他公司維持不可用；不授歷史PIT、篩選、策略、ML或交易資格。",
)
DOCUMENTS_NOT_BEFORE = datetime.fromisoformat("2026-10-17T10:36:15.088362+00:00")
_REVIEWS = {
    "2330": {"url": base._EVIDENCE["issuer_verification_url"], "pdf_sha256": base._EVIDENCE["issuer_pdf_sha256"]},
    "2317": {
        "url": "https://image.honhai.com/upload/202609/financy_by_quarterly/2026Q2_consolidared_report(e)_20260922_0036.pdf",
        "pdf_sha256": "bf4e184cf36e62f5112fa56a17927f47f67e29863f5074571f96382faa669709", "page_index": 5,
    },
    "2454": {
        "url": "https://www.mediatek.com/hubfs/MediaTek%20Assets/Pdfs/Financial%20Reports/2026/Q2%20Consolidated%20Report.pdf",
        "pdf_sha256": "b3f12e584a69d5e7fa1513f99d9b65e372874fab05cac4b527daeded39a38dd0", "page_index": 5,
    },
}
_EVIDENCE = {
    "policy": SCHEMA, "raw_sha256": base.RAW_SHA256, "reviewed_issuers": _REVIEWS,
    "additional_unit_proof_sha256": "a860a9fdb1203a3250176b49786b6da0c6c8ae0e128a38caa536c77246b4c193",
    "period": "2026-H1", "period_basis": "year_to_date_cumulative", "currency": "TWD",
    "profit_basis": "consolidated_total_profit_not_parent_attributable",
    "issuer_documents_role": "independent_verification_only_not_redistributed",
    "historical_pit_eligible": False,
}
SCOPE = DailySourceUseScope(
    dataset_id="data.gov.tw:20762:2317,2330,2454:2026-H1:" + base.RAW_SHA256,
    source_id="twse.t187ap17_L", market="TWSE", parser_version=SCHEMA,
    source_schema_version="sha256:" + base._FILES["metadata.raw"][1],
    unit="TWD,percent", intended_use="current_research",
)
_BASE_NAMES = (*base._FILES, "manifest.json", "receipt.json")


@dataclass(frozen=True, slots=True)
class ReviewedOperatingSummaryPin(base.OperatingSummaryPin):
    """型別明選新用途；原v1 reader仍只接受原pin，不自動擴scope。"""


def _acceptance(accepted_at: datetime) -> DailySourceUseAcceptance:
    from hashlib import sha256
    identity = sha256(base._bytes(_EVIDENCE)).hexdigest()
    return DailySourceUseAcceptance(
        scope=SCOPE, acceptance_id="root:twse-operating-summary-reviewed:" + identity,
        accepted_at=accepted_at, official_source_endpoint=base.SOURCE_URL,
        document_chain=tuple(str(base._EVIDENCE[key]) for key in ("dataset_url", "metadata_url", "license_url"))
                       + tuple(str(item["url"]) for item in _REVIEWS.values()),
        acceptance_evidence_ref="sha256:" + identity, authorization_scope="current_research",
    )


def _manifest(original: base.OperatingSummaryPin, acceptance: DailySourceUseAcceptance) -> dict[str, object]:
    return {"schema_version": SCHEMA, "evidence": _EVIDENCE, "attribution": base.ATTRIBUTION,
            "source_use": acceptance.to_dict(), "base_snapshot": {
                "directory": "base", "manifest_sha256": original.manifest_sha256,
                "receipt_sha256": original.receipt_sha256}}


def _values(raw: bytes, stock_code: str) -> tuple[tuple[str, str, Decimal, str], ...]:
    if stock_code not in REVIEWED_COMPANIES:
        raise base.OperatingSummaryError("該發行人的期間／單位用途尚未接受")
    # 保留原schema、1055唯一代碼與固定2330的既有防線。
    base._values(raw)
    rows = list(csv.DictReader(StringIO(raw.decode("utf-8-sig"))))
    selected = [row for row in rows if row["公司代號"] == stock_code]
    if len(selected) != 1:
        raise base.OperatingSummaryError("具名營益發行人不是唯一一列")
    row = selected[0]
    if tuple(row[key] for key in base._FIELDS[:5]) != ("1151017", "115", "2", stock_code, REVIEWED_COMPANIES[stock_code]):
        raise base.OperatingSummaryError("具名營益的發行人／半年／出表日不符")
    try:
        amounts = tuple(Decimal(row[field]) for field in base._FIELDS[5:])
    except DecimalException as error:
        raise base.OperatingSummaryError("具名營益數值不可解析") from error
    if any(not value.is_finite() for value in amounts):
        raise base.OperatingSummaryError("具名營益數值不可用")
    with localcontext() as context:
        context.prec = 80
        return tuple((metric, label, value * Decimal(1000000) if unit == "TWD" else value, unit)
                     for (metric, label, unit), value in zip(base._METRICS, amounts))


def _receipt(manifest_sha: str, first: datetime, completed: datetime) -> dict[str, str]:
    return {"schema_version": SCHEMA, "manifest_sha256": manifest_sha,
            "first_persisted_at": first.isoformat(), "successful_batch_completed_at": completed.isoformat(),
            "available_hour": _batch_publish_guard_hour(completed).isoformat(),
            "availability_basis": "successful_batch_completion_fallback", "time_basis_policy": DAILY_SOURCE_TIME_BASIS_POLICY}


def seal_reviewed_operating_summary_snapshot(
    original: base.OperatingSummaryPin, *, output_directory: Path, clock: Callable[[], datetime] | None = None,
) -> ReviewedOperatingSummaryPin:
    """逐SHA複製已驗原7檔；新外層另存用途／成功小時，不改寫原版本。"""
    get_clock = clock or (lambda: datetime.now(base._TAIPEI))
    accepted = base._local(get_clock())
    base.read_operating_summary_snapshot(original, cutoff_at=accepted)
    if accepted < DOCUMENTS_NOT_BEFORE:
        raise base.OperatingSummaryError("三公司用途接受早於必要勾稽文件")
    output = _canonical_path(output_directory, "operating_reviewed", allow_missing=True)
    for text in (os.getenv("DATA_ROOT", "D:/Min/Python/Project/FA_Data"), os.getenv("OUTPUT_ROOT"),
                 os.getenv("PERSONAL_DATA_ROOT"), os.getenv("PERSONAL_STORE_ROOT")):
        if text:
            protected = Path(text).absolute()
            if output.is_relative_to(protected) or protected.is_relative_to(output):
                raise base.OperatingSummaryError("具名營益版本不得寫入或包含正式／私人根")
    if os.path.lexists(output):
        raise base.OperatingSummaryError("具名營益版本不可覆寫")
    if output.is_relative_to(original.directory) or original.directory.is_relative_to(output):
        raise base.OperatingSummaryError("營益來源與目的根不得重疊")
    source_pins: list[tuple[Path, tuple[int, ...], str]] = []
    hashes = {**{name: digest for name, (_, digest) in base._FILES.items()},
              "manifest.json": original.manifest_sha256, "receipt.json": original.receipt_sha256}
    files = {name: base._read(original.directory / name, hashes[name], source_pins) for name in _BASE_NAMES}
    for code in REVIEWED_COMPANIES:
        _values(files["response.raw"], code)
    acceptance = _acceptance(accepted)
    base._finish(source_pins)
    output.mkdir(exist_ok=False)
    try:
        base._write(output / ".pending.json", base._bytes({"schema_version": SCHEMA}))
        destination = output / "base"
        destination.mkdir(exist_ok=False)
        saved: list[tuple[Path, tuple[int, ...], str]] = []
        for name, raw in files.items():
            digest = base._write(destination / name, raw)
            base._read(destination / name, digest, saved)
        base_pin = base.OperatingSummaryPin(destination, original.manifest_sha256, original.receipt_sha256)
        manifest_sha = base._write(output / "manifest.json", base._bytes(_manifest(base_pin, acceptance)))
        base._read(output / "manifest.json", manifest_sha, saved)
        first = base._local(get_clock())
        base._finish(source_pins)
        base._finish(saved)
        completed = base._local(get_clock())
        if not accepted <= first <= completed or first.date() != completed.date() or first.hour != completed.hour:
            raise base.OperatingSummaryError("具名營益批次時鐘倒退或跨小時")
        receipt_sha = base._write(output / "receipt.json", base._bytes(_receipt(manifest_sha, first, completed)))
        base._read(output / "receipt.json", receipt_sha, saved)
        base._finish(source_pins)
        base._finish(saved)
        if not completed <= base._local(get_clock()) < _batch_publish_guard_hour(completed):
            raise base.OperatingSummaryError("具名營益收據未在可用小時前保存")
        (output / ".pending.json").unlink()
        return ReviewedOperatingSummaryPin(output, manifest_sha, receipt_sha)
    except Exception as error:
        try:
            base._write(output / "failure.json", base._bytes({"reason": str(error)[:1024]}))
        except Exception as preserved:
            error.add_note("具名營益失敗收據另有錯誤：" + str(preserved))
        raise


def read_reviewed_operating_summary_snapshot(
    pin: ReviewedOperatingSummaryPin, *, stock_code: str, cutoff_at: datetime,
) -> base.OperatingSummaryRead:
    """原public reader核base，另核三公司用途及新批次小時，不找latest。"""
    if type(pin) is not ReviewedOperatingSummaryPin or stock_code not in REVIEWED_COMPANIES:
        raise base.OperatingSummaryError("請明選已接受公司的具型別營益版本")
    cutoff = base._local(cutoff_at)
    if cutoff > datetime.now(base._TAIPEI):
        raise base.OperatingSummaryError("具名營益時鐘不得晚於實際現在")
    directory = _canonical_path(pin.directory, "operating_reviewed", allow_missing=False)
    base._barrier(directory)
    pins: list[tuple[Path, tuple[int, ...], str]] = []
    manifest = _decode_object(base._read(directory / "manifest.json", pin.manifest_sha256, pins), label="operating_reviewed_manifest", maximum=64 * 1024)
    receipt = _decode_object(base._read(directory / "receipt.json", pin.receipt_sha256, pins), label="operating_reviewed_receipt", maximum=64 * 1024)
    child = manifest["base_snapshot"]
    if not isinstance(child, dict) or child.get("directory") != "base":
        raise base.OperatingSummaryError("具名營益原件目錄不可改綁")
    original = base.OperatingSummaryPin(directory / "base", child["manifest_sha256"], child["receipt_sha256"])
    base_result = base.read_operating_summary_snapshot(original, cutoff_at=cutoff)
    child_hashes = {**{name: digest for name, (_, digest) in base._FILES.items()},
                    "manifest.json": original.manifest_sha256, "receipt.json": original.receipt_sha256}
    child_files = {name: base._read(original.directory / name, child_hashes[name], pins) for name in _BASE_NAMES}
    acceptance = DailySourceUseAcceptance.from_dict(manifest["source_use"])
    if acceptance != _acceptance(acceptance.accepted_at) or manifest != _manifest(original, acceptance):
        raise base.OperatingSummaryError("具名營益的公司／用途／文件證據不符")
    first = base._local(receipt["first_persisted_at"])
    completed = base._local(receipt["successful_batch_completed_at"])
    available = _batch_publish_guard_hour(completed)
    if (receipt != _receipt(pin.manifest_sha256, first, completed)
            or not max(DOCUMENTS_NOT_BEFORE, base_result.available_hour) <= acceptance.accepted_at <= first <= completed
            or first.date() != completed.date() or first.hour != completed.hour):
        raise base.OperatingSummaryError("具名營益的成功批次／可用小時不符")
    if cutoff < available:
        raise base.OperatingSummaryError("尚未到具名營益成功批次台北可用小時：" + available.isoformat())
    values = _values(child_files["response.raw"], stock_code)
    base._finish(pins)
    base._barrier(original.directory)
    base._barrier(directory)
    return base.OperatingSummaryRead(pin, acceptance, available, values)
