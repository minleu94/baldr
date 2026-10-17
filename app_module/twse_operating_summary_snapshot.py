"""具名 TWSE 營益版本的目前研究出口；接受範圍不外推到其他發行人或季度。"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
import re
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

from app_module.position_health_saved_archive import _create_immutable_bytes
from app_module.recommendation_portfolio_calendar_artifact_v1 import (
    _canonical_path, _decode_object, _read_exact_file,
)
from data_module.daily_source_snapshot import (
    DAILY_SOURCE_TIME_BASIS_POLICY, DailySourceUseAcceptance, DailySourceUseScope,
    _batch_publish_guard_hour,
)

_TAIPEI = ZoneInfo("Asia/Taipei")
_SCHEMA = "twse-operating-summary-2330-2026h1.v1"
_DOCUMENTS_NOT_BEFORE = datetime.fromisoformat("2026-10-16T17:56:49.954855+00:00")
SOURCE_URL = "https://mopsfin.twse.com.tw/opendata/t187ap17_L.csv"
RAW_SHA256 = "d9778530ceae60920d75d9eb1d27ba380be8589fc12eccf2aef352932c79b609"
_FILES: dict[str, tuple[int | None, str]] = {
    "response.raw": (84302, RAW_SHA256),
    "http-receipt.json": (None, "a026b3d22357776d1781cec2a708a1da16bcbbab6287736b0210e22a00508579"),
    "dataset.raw": (526797, "28442b377a63323e70f54786080f34878bf3f553eaf6cd079c40d623b62c1a87"),
    "license.raw": (484470, "3a75b82d1b4be2cbe87588103da1cd81bc29676e613e1fde5e973df0d4a4eb03"),
    "metadata.raw": (3678, "dd37232f4d5e6ac4928c82644fc5cf1478ab32ab40b94eba13e3043912bfa3e9"),
}
_FIELDS = (
    "出表日期", "年度", "季別", "公司代號", "公司名稱", "營業收入(百萬元)",
    "毛利率(%)(營業毛利)/(營業收入)", "營業利益率(%)(營業利益)/(營業收入)",
    "稅前純益率(%)(稅前純益)/(營業收入)", "稅後純益率(%)(稅後純益)/(營業收入)",
)
_METRICS = (
    ("net_revenue", "營業收入（半年累計）", "TWD"),
    ("gross_margin", "毛利率（半年累計）", "percent"),
    ("operating_margin", "營業利益率（半年累計）", "percent"),
    ("pretax_margin", "稅前純益率（半年累計）", "percent"),
    ("net_margin", "稅後純益率（半年累計）", "percent"),
)
ATTRIBUTION = (
    "資料提供：金融監督管理委員會證券期貨局／臺灣證券交易所，2026，"
    "上市公司營益分析查詢彙總表（資料集20762）；政府資料開放授權條款第1版："
    "https://data.gov.tw/license"
)
LIMITATIONS = (
    "只接受2330、2026上半年及明選CSV版本；不代表其他公司、季度或每日更新已核實。",
    "期間與幣別由同發行人官方半年財報交叉勾稽；不是資料集全文的通用單位契約。",
    "前期比較缺同用途來源，維持不可用；不從PDF搬入前期值或推算成長率。",
    "依成功保存批次的小時供目前研究；不授歷史PIT、篩選、策略、ML或交易資格。",
)
_EVIDENCE = {
    "policy": _SCHEMA,
    "dataset_url": "https://data.gov.tw/dataset/20762",
    "metadata_url": "https://data.gov.tw/api/v2/rest/dataset/20762",
    "license_url": "https://data.gov.tw/license",
    "issuer_verification_url": "https://investor.tsmc.com/english/quarterly-results/2026/q2",
    "issuer_pdf_sha256": "a55d6aca73ba6246385d885fbb41a4efa55c92033cb644b48fda671814e0754f",
    "issuer_pdf_role": "independent_viewing_verification_only_not_redistributed",
    "verification_method": "same_issuer_h1_ntd_million_revenue_and_four_margins_at_display_precision",
    "raw_sha256": RAW_SHA256,
    "stock_code": "2330", "period": "2026-H1", "currency": "TWD",
    "period_basis": "year_to_date_cumulative", "historical_pit_eligible": False,
}
SCOPE = DailySourceUseScope(
    dataset_id="data.gov.tw:20762:2330:2026-H1:" + RAW_SHA256,
    source_id="twse.t187ap17_L", market="TWSE", parser_version=_SCHEMA,
    source_schema_version="sha256:" + _FILES["metadata.raw"][1],
    unit="TWD,percent", intended_use="current_research",
)


class OperatingSummaryError(ValueError):
    """具名營益來源缺件、漂移或尚不可用。"""


def _bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _local(value: object) -> datetime:
    result = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(result, datetime) or result.tzinfo is None or result.utcoffset() is None:
        raise OperatingSummaryError("營益版本時鐘必須含時區")
    return result.astimezone(_TAIPEI)


@dataclass(frozen=True, slots=True)
class OperatingSummaryPin:
    directory: Path
    manifest_sha256: str
    receipt_sha256: str

    def __post_init__(self) -> None:
        _canonical_path(self.directory, "operating_summary", allow_missing=True)
        if any(re.fullmatch(r"[0-9a-f]{64}", item) is None for item in (self.manifest_sha256, self.receipt_sha256)):
            raise OperatingSummaryError("營益版本需要manifest／receipt雙外部SHA")


@dataclass(frozen=True, slots=True)
class OperatingSummaryRead:
    pin: OperatingSummaryPin
    acceptance: DailySourceUseAcceptance
    available_hour: datetime
    values: tuple[tuple[str, str, Decimal, str], ...]
    raw_sha256: str = RAW_SHA256
    period: str = "2026-H1"
    period_basis: str = "year_to_date_cumulative"


def _read(path: Path, expected: str, pins: list[tuple[Path, tuple[int, ...], str]]) -> bytes:
    target = _canonical_path(path, "operating_summary", allow_missing=False)
    raw, signature = _read_exact_file(target, maximum=1024 * 1024)
    if sha256(raw).hexdigest() != expected:
        raise OperatingSummaryError("營益來源SHA不符：" + path.name)
    pins.append((target, signature, expected))
    return raw


def _finish(pins: list[tuple[Path, tuple[int, ...], str]]) -> None:
    for path, signature, digest in pins:
        raw, actual = _read_exact_file(_canonical_path(path, "operating_summary", allow_missing=False), maximum=1024 * 1024)
        if actual != signature or sha256(raw).hexdigest() != digest:
            raise OperatingSummaryError("營益原件在讀取期間改變")


def _write(path: Path, raw: bytes) -> str:
    _canonical_path(path, "operating_summary", allow_missing=True)
    if os.path.lexists(path):
        raise OperatingSummaryError("營益版本不可覆寫")
    _create_immutable_bytes(path, raw)
    digest = sha256(raw).hexdigest()
    _read(path, digest, [])
    return digest


def _barrier(directory: Path) -> None:
    if any(os.path.lexists(directory / name) for name in (".pending.json", "failure.json")):
        raise OperatingSummaryError("營益版本仍pending或已失敗")


def _values(raw: bytes) -> tuple[tuple[str, str, Decimal, str], ...]:
    reader = csv.DictReader(StringIO(raw.decode("utf-8-sig"), newline=""))
    if tuple(reader.fieldnames or ()) != _FIELDS:
        raise OperatingSummaryError("營益欄位／單位schema不符")
    rows = list(reader)
    if len(rows) != 1055 or len({row["公司代號"] for row in rows}) != 1055:
        raise OperatingSummaryError("營益原件列數或唯一代碼不符")
    selected = [row for row in rows if row["公司代號"] == "2330"]
    if len(selected) != 1:
        raise OperatingSummaryError("營益版本缺唯一2330")
    row = selected[0]
    if tuple(row[key] for key in _FIELDS[:5]) != ("1151017", "115", "2", "2330", "台積電"):
        raise OperatingSummaryError("營益發行人、季度或出表日不符")
    amounts = tuple(Decimal(row[field]) for field in _FIELDS[5:])
    if any(not value.is_finite() for value in amounts):
        raise OperatingSummaryError("營益數值非有限Decimal")
    return tuple((metric, label, value * Decimal(1000000) if unit == "TWD" else value, unit)
                 for (metric, label, unit), value in zip(_METRICS, amounts))


def _validate_files(files: Mapping[str, bytes]) -> datetime:
    if set(files) != set(_FILES):
        raise OperatingSummaryError("營益原件／用途文件鏈缺件")
    for name, (size, digest) in _FILES.items():
        if sha256(files[name]).hexdigest() != digest or (size is not None and len(files[name]) != size):
            raise OperatingSummaryError("營益固定原件版本不符：" + name)
    transport = json.loads(files["http-receipt.json"])
    if (transport.get("official_url") != SOURCE_URL or transport.get("response_url") != SOURCE_URL
            or transport.get("response_status") != 200 or transport.get("response_body_complete") is not True
            or transport.get("response_body_eof") is not True or transport.get("raw_bytes") != len(files["response.raw"])
            or transport.get("raw_sha256") != RAW_SHA256):
        raise OperatingSummaryError("營益HTTP完整性或端點不符")
    metadata = json.loads(files["metadata.raw"])["result"]
    if (metadata["datasetId"] != 20762 or metadata["license"] != "1"
            or metadata["distribution"][0]["resourceDownloadUrl"] != SOURCE_URL):
        raise OperatingSummaryError("營益資料集／授權路徑不符")
    _values(files["response.raw"])
    return _local(transport["ended_at"])


def _acceptance(accepted_at: datetime) -> DailySourceUseAcceptance:
    identity = sha256(_bytes(_EVIDENCE)).hexdigest()
    return DailySourceUseAcceptance(
        scope=SCOPE, acceptance_id="root:twse-operating-summary:" + identity,
        accepted_at=accepted_at, official_source_endpoint=SOURCE_URL,
        document_chain=tuple(str(_EVIDENCE[key]) for key in ("dataset_url", "metadata_url", "license_url", "issuer_verification_url")),
        acceptance_evidence_ref="sha256:" + identity, authorization_scope="current_research",
    )


def _manifest(files: Mapping[str, bytes], acceptance: DailySourceUseAcceptance) -> dict[str, Any]:
    return {"schema_version": _SCHEMA, "evidence": _EVIDENCE, "attribution": ATTRIBUTION,
            "source_use": acceptance.to_dict(),
            "files": {name: {"bytes": len(raw), "sha256": sha256(raw).hexdigest()} for name, raw in files.items()}}


def seal_operating_summary_snapshot(
    sources: Mapping[str, Path], *, output_directory: Path,
    clock: Callable[[], datetime] | None = None,
) -> OperatingSummaryPin:
    """另存既有原件；不抓取、不寫正式庫，也不重用失敗或先前版本目錄。"""
    output = _canonical_path(output_directory, "operating_summary", allow_missing=True)
    for text in (os.getenv("DATA_ROOT", "D:/Min/Python/Project/FA_Data"), os.getenv("OUTPUT_ROOT"),
                 os.getenv("PERSONAL_DATA_ROOT"), os.getenv("PERSONAL_STORE_ROOT")):
        if text:
            protected = Path(text).absolute()
            if output.is_relative_to(protected) or protected.is_relative_to(output):
                raise OperatingSummaryError("營益版本不得寫入或包含正式／私人根")
    if set(sources) != set(_FILES):
        raise OperatingSummaryError("請明選五份營益原件／用途文件")
    pins: list[tuple[Path, tuple[int, ...], str]] = []
    files = {name: _read(path, _FILES[name][1], pins) for name, path in sources.items()}
    capture_completed = _validate_files(files)
    get_clock = clock or (lambda: datetime.now(_TAIPEI))
    accepted = _local(get_clock())
    # 文件原件在2026-10-16晚間已完整保存；接受時鐘不能倒填到抓取以前。
    if accepted < max(capture_completed, _DOCUMENTS_NOT_BEFORE):
        raise OperatingSummaryError("營益用途接受早於必要原件保存")
    acceptance = _acceptance(accepted)
    _finish(pins)
    output.mkdir(exist_ok=False)
    try:
        saved_pins: list[tuple[Path, tuple[int, ...], str]] = []
        _write(output / ".pending.json", _bytes({"schema_version": _SCHEMA}))
        for name, raw in files.items():
            digest = _write(output / name, raw)
            _read(output / name, digest, saved_pins)
        manifest_sha = _write(output / "manifest.json", _bytes(_manifest(files, acceptance)))
        _read(output / "manifest.json", manifest_sha, saved_pins)
        first = _local(get_clock())
        _finish(pins)
        _finish(saved_pins)
        completed = _local(get_clock())
        available = _batch_publish_guard_hour(completed)
        if not accepted <= first <= completed or first.hour != completed.hour or first.date() != completed.date():
            raise OperatingSummaryError("營益保存時鐘倒退或跨小時")
        receipt = {"schema_version": _SCHEMA, "manifest_sha256": manifest_sha,
                   "first_persisted_at": first.isoformat(), "successful_batch_completed_at": completed.isoformat(),
                   "available_hour": available.isoformat(), "availability_basis": "successful_batch_completion_fallback",
                   "time_basis_policy": DAILY_SOURCE_TIME_BASIS_POLICY}
        receipt_sha = _write(output / "receipt.json", _bytes(receipt))
        _read(output / "receipt.json", receipt_sha, saved_pins)
        _finish(pins)
        _finish(saved_pins)
        if not completed <= _local(get_clock()) < available:
            raise OperatingSummaryError("營益成功收據未在可用小時前保存")
        (output / ".pending.json").unlink()
        return OperatingSummaryPin(output, manifest_sha, receipt_sha)
    except Exception as error:
        try:
            _write(output / "failure.json", _bytes({"reason": str(error)[:1024]}))
        except Exception as preservation_error:
            error.add_note("營益失敗封存另有錯誤：" + str(preservation_error))
        raise


def read_operating_summary_snapshot(pin: OperatingSummaryPin, *, cutoff_at: datetime) -> OperatingSummaryRead:
    """外部雙SHA、用途範圍、逐件原件與批次小時均重驗；從不搜尋latest。"""
    if type(pin) is not OperatingSummaryPin:
        raise OperatingSummaryError("必須提供具型別的營益版本pin")
    cutoff = _local(cutoff_at)
    if cutoff > datetime.now(_TAIPEI):
        raise OperatingSummaryError("營益研究時鐘不得晚於實際現在")
    directory = _canonical_path(pin.directory, "operating_summary", allow_missing=False)
    _barrier(directory)
    pins: list[tuple[Path, tuple[int, ...], str]] = []
    manifest = _decode_object(_read(directory / "manifest.json", pin.manifest_sha256, pins), label="operating_manifest", maximum=64 * 1024)
    receipt = _decode_object(_read(directory / "receipt.json", pin.receipt_sha256, pins), label="operating_receipt", maximum=64 * 1024)
    files = {name: _read(directory / name, digest, pins) for name, (_, digest) in _FILES.items()}
    capture_completed = _validate_files(files)
    acceptance = DailySourceUseAcceptance.from_dict(manifest["source_use"])
    if acceptance != _acceptance(acceptance.accepted_at) or manifest != _manifest(files, acceptance):
        raise OperatingSummaryError("營益用途／來源manifest不符具名接受政策")
    first = _local(receipt["first_persisted_at"])
    completed = _local(receipt["successful_batch_completed_at"])
    available = _batch_publish_guard_hour(completed)
    expected = {"schema_version": _SCHEMA, "manifest_sha256": pin.manifest_sha256,
                "first_persisted_at": first.isoformat(), "successful_batch_completed_at": completed.isoformat(),
                "available_hour": available.isoformat(), "availability_basis": "successful_batch_completion_fallback",
                "time_basis_policy": DAILY_SOURCE_TIME_BASIS_POLICY}
    if (receipt != expected or not max(capture_completed, _DOCUMENTS_NOT_BEFORE) <= acceptance.accepted_at <= first <= completed
            or first.date() != completed.date() or first.hour != completed.hour):
        raise OperatingSummaryError("營益批次／可用小時不符")
    if cutoff < available:
        raise OperatingSummaryError("尚未到營益成功批次台北可用小時：" + available.isoformat())
    values = _values(files["response.raw"])
    _finish(pins)
    _barrier(directory)
    return OperatingSummaryRead(pin, acceptance, available, values)
