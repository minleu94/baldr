"""沿原營益版本封存具名三公司用途；發行人文件只作勾稽，不供產品值。"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, DecimalException, ROUND_HALF_UP, localcontext
from io import StringIO
import os
from pathlib import Path
from typing import Callable
from hashlib import sha256

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


COMPARATIVE_SCHEMA = "twse-operating-summary-comparative-2026h1.v1"
COMPARATIVE_FACTS_SHA256 = "745f6fd1f739e7b5772923009e4e32422a7de1bb96a6a6efcb70155c2184e0e0"
COMPARATIVE_NOT_BEFORE = datetime.fromisoformat("2026-10-17T14:29:49.200150+00:00")
COMPARATIVE_LIMITATIONS = (
    "前期取同一份2026半年財報中的2025半年比較欄，只供目前研究，不代表2025當時可得。",
    "營收同比按保存原值計算；利潤率差為兩期顯示率的百分點差。披露精度不足時不填值。",
    "來源為發行人數值事實；PDF不隨包散布，不授歷史PIT、聚合特徵、策略或ML資格。",
)
_COMPARATIVE_EVIDENCE = {
    "facts_sha256": COMPARATIVE_FACTS_SHA256,
    "source_audit_sha256": "f2c0820dfa8f40c87063c33d0f77a2e03651e5f62941e49fd27cf7f2f064bda9",
    "period": "2026-H1", "prior_period": "2025-H1",
    "method_version": "issuer-comparative-display-precision.v1",
    "profit_basis": "consolidated_total_profit_not_parent_attributable",
    "pdf_redistributed": False, "historical_pit_eligible": False,
}


@dataclass(frozen=True, slots=True)
class ComparativeOperatingSummaryPin(base.OperatingSummaryPin):
    """明選前期比較新版本；原兩種pin與reader的用途不變。"""


@dataclass(frozen=True, slots=True)
class OperatingSummaryComparisonValue:
    metric_name: str
    label: str
    current_value: Decimal
    prior_value: Decimal | None
    unit: str
    change_value: Decimal | None
    change_unit: str
    note: str


@dataclass(frozen=True, slots=True)
class ComparativeOperatingSummaryRead:
    current: base.OperatingSummaryRead
    available_hour: datetime
    values: tuple[OperatingSummaryComparisonValue, ...]
    status: str
    facts_sha256: str


def _comparison_facts(raw: bytes) -> dict[str, object]:
    facts = _decode_object(raw, label="issuer_comparative_facts", maximum=64 * 1024)
    if (facts.get("schema_version") != "issuer-half-year-comparative-facts.2026h1.v1"
            or facts.get("period") != "2026-H1" or facts.get("prior_period") != "2025-H1"
            or facts.get("pdf_redistributed") is not False or facts.get("historical_pit_eligible") is not False
            or facts.get("metrics") != ["net_revenue", "gross_profit", "operating_profit", "pretax_profit", "net_profit"]):
        raise base.OperatingSummaryError("財報比較期間／事實用途不符")
    issuers = facts.get("issuers")
    if not isinstance(issuers, dict) or set(issuers) != set(REVIEWED_COMPANIES):
        raise base.OperatingSummaryError("財報比較須明選三公司")
    for code, item in issuers.items():
        if (not isinstance(item, dict) or item.get("stock_name") != REVIEWED_COMPANIES[code]
                or item.get("pdf_sha256") != _REVIEWS[code]["pdf_sha256"]
                or item.get("unit_twd") != ("1000000" if code == "2330" else "1000")
                or item.get("profit_basis") != "consolidated_total_profit_not_parent_attributable"
                or item.get("official_announcement_time_verified") is not False):
            raise base.OperatingSummaryError("財報比較公司／單位／損益口徑不符")
        for key in ("current_amounts", "prior_amounts"):
            amounts = item.get(key)
            if (not isinstance(amounts, list) or len(amounts) != 5
                    or any(type(value) is not str or not value.isascii() or not value.isdigit() for value in amounts)):
                raise base.OperatingSummaryError("財報比較數值事實不可解析")
    return facts


def _comparison_acceptance(facts: dict[str, object], code: str, accepted: datetime) -> DailySourceUseAcceptance:
    issuers = facts["issuers"]
    assert isinstance(issuers, dict)
    item = issuers[code]
    identity = sha256(base._bytes(_COMPARATIVE_EVIDENCE)).hexdigest()
    scope = DailySourceUseScope(dataset_id="issuer:" + code + ":2026H1-vs-2025H1:" + COMPARATIVE_FACTS_SHA256,
        source_id="issuer." + code + ".comparative_statement", market="TWSE", parser_version=COMPARATIVE_SCHEMA,
        source_schema_version="sha256:" + item["pdf_sha256"], unit="TWD,percent,percentage_point", intended_use="current_research")
    return DailySourceUseAcceptance(scope=scope, acceptance_id="root:issuer-comparative:" + code + ":" + identity,
        accepted_at=accepted, official_source_endpoint=item["official_url"], document_chain=(item["official_url"],),
        acceptance_evidence_ref="sha256:" + identity, authorization_scope="current_research")


def _comparison_manifest(current: ReviewedOperatingSummaryPin, facts: dict[str, object], accepted: datetime) -> dict[str, object]:
    return {"schema_version": COMPARATIVE_SCHEMA, "evidence": _COMPARATIVE_EVIDENCE,
        "current_snapshot": {"directory": "current", "manifest_sha256": current.manifest_sha256, "receipt_sha256": current.receipt_sha256},
        "facts": {"path": "comparative_facts.json", "sha256": COMPARATIVE_FACTS_SHA256},
        "source_uses": {code: _comparison_acceptance(facts, code, accepted).to_dict() for code in REVIEWED_COMPANIES}}


def _comparison_receipt(manifest_sha: str, first: datetime, completed: datetime) -> dict[str, str]:
    return dict(_receipt(manifest_sha, first, completed), schema_version=COMPARATIVE_SCHEMA)


def _stable_ratio(numerator: Decimal, numerator_precision: Decimal, denominator: Decimal,
                  denominator_precision: Decimal, *, growth: bool = False) -> Decimal | None:
    """兩個披露誤差界線的所有端點必須四捨五入一致，才顯示0.01%。"""
    with localcontext() as context:
        context.prec = 80
        if denominator - denominator_precision / Decimal(2) <= 0:
            return None
        corners = [(n / d - (Decimal(1) if growth else Decimal(0))) * Decimal(100)
            for n in (numerator - numerator_precision / Decimal(2), numerator + numerator_precision / Decimal(2))
            for d in (denominator - denominator_precision / Decimal(2), denominator + denominator_precision / Decimal(2))]
        rounded = {value.quantize(Decimal(".01"), rounding=ROUND_HALF_UP) for value in corners}
        return next(iter(rounded)) if len(rounded) == 1 else None


def _comparison_values(current: base.OperatingSummaryRead, facts: dict[str, object], code: str) -> tuple[OperatingSummaryComparisonValue, ...]:
    issuers = facts["issuers"]
    assert isinstance(issuers, dict)
    item = issuers[code]
    with localcontext() as context:
        context.prec = 80
        unit = Decimal(item["unit_twd"])
        prior = tuple(Decimal(value) * unit for value in item["prior_amounts"])
        this_report = tuple(Decimal(value) * unit for value in item["current_amounts"])
        if abs(current.values[0][2] - this_report[0]) > max(unit, Decimal(10000)) / Decimal(2):
            raise base.OperatingSummaryError("當期CSV與財報比較原值超出披露精度")
        if this_report[0] <= 0:
            raise base.OperatingSummaryError("當期財報營收無法勾稽")
        if any((value / this_report[0] * Decimal(100)).quantize(Decimal(".01"), rounding=ROUND_HALF_UP) != metric[2]
               for value, metric in zip(this_report[1:], current.values[1:])):
            raise base.OperatingSummaryError("當期財報比率與已接受CSV不同")
        values: list[OperatingSummaryComparisonValue] = []
        previous: Decimal | None
        change: Decimal | None
        for index, (metric, label, value, value_unit) in enumerate(current.values):
            if index == 0:
                previous = prior[0]
                change = _stable_ratio(value, Decimal(10000), previous, unit, growth=True)
                note = "營收同比按保存CSV當期值及財報去年同期值計算；披露精度界線須穩定至0.01%。"
                change_unit = "percent"
            else:
                previous = _stable_ratio(prior[index], unit, prior[0], unit)
                change = value - previous if previous is not None else None
                note = "前期率由同表合併金額計算至0.01%；差異為兩期顯示率之百分點差。"
                change_unit = "percentage_point"
            if change is None:
                note += "去年同期營收不為正，本項比率不可用。" if prior[0] <= 0 else "披露精度界線跨越0.01%四捨五入點，本項差異不可用。"
            values.append(OperatingSummaryComparisonValue(metric, label, value, previous, value_unit, change, change_unit,
                note + " 前期金額披露單位為" + str(unit) + " TWD；不是額外的元級精度。"))
        return tuple(values)


def seal_comparative_operating_summary_snapshot(original: ReviewedOperatingSummaryPin, *, facts_path: Path,
    output_directory: Path, clock: Callable[[], datetime] | None = None) -> ComparativeOperatingSummaryPin:
    """沿原具名版本另存比較外層；不修改當期值、原版本或首次可用時間。"""
    if type(original) is not ReviewedOperatingSummaryPin:
        raise base.OperatingSummaryError("比較須明選原具名三公司版本")
    get_clock = clock or (lambda: datetime.now(base._TAIPEI))
    accepted = base._local(get_clock())
    if not COMPARATIVE_NOT_BEFORE <= accepted <= datetime.now(base._TAIPEI):
        raise base.OperatingSummaryError("比較用途接受早於核對或晚於實際現在")
    pins: list[tuple[Path, tuple[int, ...], str]] = []
    facts_path = _canonical_path(facts_path, "operating_comparative_facts", allow_missing=False)
    raw = base._read(facts_path, COMPARATIVE_FACTS_SHA256, pins)
    facts = _comparison_facts(raw)
    for code in REVIEWED_COMPANIES:
        _comparison_values(read_reviewed_operating_summary_snapshot(original, stock_code=code, cutoff_at=accepted), facts, code)
    manifest = _decode_object(base._read(original.directory / "manifest.json", original.manifest_sha256, pins), label="current_manifest", maximum=64 * 1024)
    child = manifest["base_snapshot"]
    assert isinstance(child, dict)
    hashes = {"manifest.json": original.manifest_sha256, "receipt.json": original.receipt_sha256,
        **{"base/" + name: digest for name, (_, digest) in base._FILES.items()},
        "base/manifest.json": child["manifest_sha256"], "base/receipt.json": child["receipt_sha256"]}
    files = {name: base._read(original.directory / name, digest, pins) for name, digest in hashes.items()}
    output = _canonical_path(output_directory, "operating_comparative", allow_missing=True)
    for text in (os.getenv("DATA_ROOT", "D:/Min/Python/Project/FA_Data"), os.getenv("OUTPUT_ROOT"), os.getenv("PERSONAL_DATA_ROOT"), os.getenv("PERSONAL_STORE_ROOT")):
        if text:
            protected = Path(text).absolute()
            if output.is_relative_to(protected) or protected.is_relative_to(output):
                raise base.OperatingSummaryError("比較版本不得寫入或包含正式／私人根")
    if (os.path.lexists(output) or output.is_relative_to(original.directory) or original.directory.is_relative_to(output)
            or output == facts_path or facts_path.is_relative_to(output)):
        raise base.OperatingSummaryError("比較目的根已存在或與來源重疊")
    base._finish(pins)
    output.mkdir(exist_ok=False)
    try:
        base._write(output / ".pending.json", base._bytes({"schema_version": COMPARATIVE_SCHEMA}))
        (output / "current/base").mkdir(parents=True, exist_ok=False)
        saved: list[tuple[Path, tuple[int, ...], str]] = []
        for name, content in files.items():
            digest = base._write(output / "current" / name, content)
            base._read(output / "current" / name, digest, saved)
        base._write(output / "comparative_facts.json", raw)
        base._read(output / "comparative_facts.json", COMPARATIVE_FACTS_SHA256, saved)
        manifest_sha = base._write(output / "manifest.json", base._bytes(_comparison_manifest(original, facts, accepted)))
        base._read(output / "manifest.json", manifest_sha, saved)
        first = base._local(get_clock())
        base._finish(pins)
        base._finish(saved)
        completed = base._local(get_clock())
        if not accepted <= first <= completed or first.date() != completed.date() or first.hour != completed.hour:
            raise base.OperatingSummaryError("比較批次時鐘倒退或跨小時")
        receipt_sha = base._write(output / "receipt.json", base._bytes(_comparison_receipt(manifest_sha, first, completed)))
        base._read(output / "receipt.json", receipt_sha, saved)
        base._finish(pins)
        base._finish(saved)
        if not completed <= base._local(get_clock()) < _batch_publish_guard_hour(completed):
            raise base.OperatingSummaryError("比較收據未在可用小時前保存")
        (output / ".pending.json").unlink()
        return ComparativeOperatingSummaryPin(output, manifest_sha, receipt_sha)
    except Exception as error:
        try:
            base._write(output / "failure.json", base._bytes({"reason": str(error)[:1024]}))
        except Exception as preserved:
            error.add_note("比較失敗收據另有錯誤：" + str(preserved))
        raise


def read_comparative_operating_summary_snapshot(pin: ComparativeOperatingSummaryPin, *, stock_code: str,
    cutoff_at: datetime) -> ComparativeOperatingSummaryRead:
    if type(pin) is not ComparativeOperatingSummaryPin or stock_code not in REVIEWED_COMPANIES:
        raise base.OperatingSummaryError("請明選已接受公司的比較版本")
    cutoff = base._local(cutoff_at)
    if cutoff > datetime.now(base._TAIPEI):
        raise base.OperatingSummaryError("比較時鐘不得晚於實際現在")
    directory = _canonical_path(pin.directory, "operating_comparative", allow_missing=False)
    base._barrier(directory)
    pins: list[tuple[Path, tuple[int, ...], str]] = []
    manifest = _decode_object(base._read(directory / "manifest.json", pin.manifest_sha256, pins), label="comparison_manifest", maximum=64 * 1024)
    receipt = _decode_object(base._read(directory / "receipt.json", pin.receipt_sha256, pins), label="comparison_receipt", maximum=64 * 1024)
    child = manifest["current_snapshot"]
    if not isinstance(child, dict) or child.get("directory") != "current":
        raise base.OperatingSummaryError("比較當期原件目錄不可改綁")
    current_pin = ReviewedOperatingSummaryPin(directory / "current", child["manifest_sha256"], child["receipt_sha256"])
    current = read_reviewed_operating_summary_snapshot(current_pin, stock_code=stock_code, cutoff_at=cutoff)
    facts = _comparison_facts(base._read(directory / "comparative_facts.json", COMPARATIVE_FACTS_SHA256, pins))
    uses = manifest["source_uses"]
    if not isinstance(uses, dict) or set(uses) != set(REVIEWED_COMPANIES):
        raise base.OperatingSummaryError("比較公司接受用途缺件")
    accepted = DailySourceUseAcceptance.from_dict(uses[stock_code]).accepted_at
    if manifest != _comparison_manifest(current_pin, facts, accepted):
        raise base.OperatingSummaryError("比較原值／用途／文件證據不符")
    first, completed = (base._local(receipt[key]) for key in ("first_persisted_at", "successful_batch_completed_at"))
    available = _batch_publish_guard_hour(completed)
    if (receipt != _comparison_receipt(pin.manifest_sha256, first, completed)
            or not max(COMPARATIVE_NOT_BEFORE, current.available_hour) <= accepted <= first <= completed
            or first.date() != completed.date() or first.hour != completed.hour):
        raise base.OperatingSummaryError("比較版本成功批次／可用小時不符")
    values = _comparison_values(current, facts, stock_code) if cutoff >= available else ()
    base._finish(pins)
    base._barrier(directory)
    return ComparativeOperatingSummaryRead(current, available, values, "available" if cutoff >= available else "waiting_actual_available_hour", COMPARATIVE_FACTS_SHA256)
