"""日曆完整批次版本與前瞻小時讀回；沿既有日曆解析與檔案守衛。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Callable, Generic, Literal, Mapping, Sequence, TypeVar
from zoneinfo import ZoneInfo

from app_module.recommendation_portfolio_calendar_artifact_v1 import (
    _decode_object, _validate_target,
    read_calendar_version_bytes_exact_v1, write_calendar_version_bytes_create_only_v1,
)
from app_module.recommendation_portfolio_calendar_evidence_v1 import (
    PORTFOLIO_PERIOD_CALENDAR_EVIDENCE_SCHEMA_V1, PortfolioPeriodCalendarEvidenceV1,
    PortfolioPeriodCalendarEvidenceReadV1,
)
from app_module.recommendation_portfolio_annual_calendar_evidence_v1 import (
    PORTFOLIO_PERIOD_ANNUAL_CALENDAR_EVIDENCE_SCHEMA_V1, PortfolioPeriodAnnualCalendarEvidenceV1,
)
from data_module.tpex_annual_calendar_transport_v1 import (
    TPEX_ANNUAL_CALENDAR_TRANSPORT_SCHEMA_V1, OfficialCalendarTpexAnnualJsonTransportV1,
)
from data_module.daily_source_snapshot import (
    DAILY_SOURCE_TIME_BASIS_POLICY, DailySourceUseAcceptance, DailySourceUseScope,
)
from data_module.official_calendar_bundle import (
    MAX_CAPTURE_DAYS, TPEX_MARKET_CALENDAR_URL, TWSE_HOLIDAY_SCHEDULE_URL,
    TPEX_ANNUAL_TRADING_DATE_URL,
)
from data_module.official_calendar_transport_v1 import (
    CALENDAR_TRANSPORT_SCHEMA_V1, OfficialCalendarJsonTransportV1,
)

CALENDAR_DAILY_CAPTURE_SCHEMA_V1 = "official-calendar-daily-capture.v1"
CALENDAR_DAILY_MANIFEST_SCHEMA_V1 = "official-calendar-daily-manifest.v1"
CALENDAR_DAILY_RECEIPT_SCHEMA_V1 = "official-calendar-daily-receipt.v1"
CALENDAR_DAILY_PARSER_V1 = "portfolio-period-calendar-evidence.v1"
CALENDAR_DAILY_USE_V1 = "prospective_daily_calendar_research"
CALENDAR_ANNUAL_DAILY_CAPTURE_SCHEMA_V1 = "official-calendar-annual-daily-capture.v1"
CALENDAR_ANNUAL_DAILY_MANIFEST_SCHEMA_V1 = "official-calendar-annual-daily-manifest.v1"
CALENDAR_ANNUAL_DAILY_RECEIPT_SCHEMA_V1 = "official-calendar-annual-daily-receipt.v1"
CALENDAR_ANNUAL_DAILY_PARSER_V1 = "portfolio-period-annual-calendar-evidence.v1"
_CalendarTransportV1 = OfficialCalendarJsonTransportV1 | OfficialCalendarTpexAnnualJsonTransportV1
_EvidenceT = TypeVar("_EvidenceT", bound=PortfolioPeriodCalendarEvidenceReadV1)


@dataclass(frozen=True, slots=True)
class _DailyCalendarCodecV1:
    capture_schema: str
    manifest_schema: str
    receipt_schema: str
    parser_version: str
    evidence_schema: str
    annual: bool


_MONTHLY_CODEC = _DailyCalendarCodecV1(
    CALENDAR_DAILY_CAPTURE_SCHEMA_V1, CALENDAR_DAILY_MANIFEST_SCHEMA_V1,
    CALENDAR_DAILY_RECEIPT_SCHEMA_V1, CALENDAR_DAILY_PARSER_V1,
    PORTFOLIO_PERIOD_CALENDAR_EVIDENCE_SCHEMA_V1, False,
)
_ANNUAL_CODEC = _DailyCalendarCodecV1(
    CALENDAR_ANNUAL_DAILY_CAPTURE_SCHEMA_V1, CALENDAR_ANNUAL_DAILY_MANIFEST_SCHEMA_V1,
    CALENDAR_ANNUAL_DAILY_RECEIPT_SCHEMA_V1, CALENDAR_ANNUAL_DAILY_PARSER_V1,
    PORTFOLIO_PERIOD_ANNUAL_CALENDAR_EVIDENCE_SCHEMA_V1, True,
)
_TAIPEI = ZoneInfo("Asia/Taipei")
_MARKETS: tuple[Literal["twse", "tpex"], ...] = ("twse", "tpex")
_MAX_BYTES = 64 * 1024**2
_CAPTURE_FIELDS = frozenset({
    "schema_version", "batch_id", "start_date", "end_date", "parser_version",
    "use_acceptances", "transports",
})
_MANIFEST_FIELDS = frozenset({
    "schema_version", "batch_id", "start_date", "end_date", "parser_version",
    "capture_sha256", "calendar_evidence_sha256", "expected_session_dates",
    "partitions", "validation", "official_timestamp", "official_timestamp_original_text",
    "official_time_basis", "time_basis_policy",
})
_RECEIPT_FIELDS = frozenset({
    "schema_version", "batch_id", "manifest_sha256", "capture_sha256", "batch_status",
    "source_batch_started_at", "first_persisted_at", "successful_batch_completed_at",
    "completion_basis", "available_hour", "availability_basis", "time_basis_policy",
})


class OfficialCalendarDailySnapshotError(ValueError):
    """批次不完整、版本或外部信任錨點不符；不發行成功投影。"""


class OfficialCalendarDailySnapshotCancelled(OfficialCalendarDailySnapshotError):
    """明示合作取消；保留已擁有的原件與 pending barrier。"""


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _local(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise OfficialCalendarDailySnapshotError("calendar_batch_aware_clock_required")
    return value.astimezone(_TAIPEI)


def _time(value: object) -> datetime:
    if type(value) is not str:
        raise OfficialCalendarDailySnapshotError("calendar_batch_clock_text_required")
    try:
        result = _local(datetime.fromisoformat(value))
    except ValueError as exc:
        raise OfficialCalendarDailySnapshotError("calendar_batch_clock_invalid") from exc
    if result.isoformat() != value:
        raise OfficialCalendarDailySnapshotError("calendar_batch_clock_not_canonical_taipei")
    return result


def _availability(completed: datetime) -> tuple[datetime, str]:
    local = _local(completed)
    hour = local.replace(minute=0, second=0, microsecond=0)
    # 原成功樣本在整點，後面尚需發布：沿daily契約另列下一小時guard。
    return hour + timedelta(hours=1), (
        "successful_batch_hour_exact_boundary_publication_guard"
        if local == hour else "successful_batch_hour_only"
    )


def _cancel(check_cancel: Callable[[], bool] | None) -> None:
    if check_cancel is not None and check_cancel():
        raise OfficialCalendarDailySnapshotCancelled("calendar_batch_cancelled")


def _batch_id(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value) is None:
        raise OfficialCalendarDailySnapshotError("calendar_batch_id_invalid")
    return value


def calendar_daily_use_scope_v1(market: Literal["twse", "tpex"]) -> DailySourceUseScope:
    if market not in ("twse", "tpex"):
        raise OfficialCalendarDailySnapshotError("calendar_batch_market_invalid")
    return DailySourceUseScope(
        dataset_id="official_trading_calendar", source_id=f"{market}.official_calendar",
        market=market, parser_version=CALENDAR_DAILY_PARSER_V1,
        source_schema_version=("twse.holidaySchedule.v1" if market == "twse" else "tpex.mktCalendar.v1"),
        unit="trading_session_date", intended_use=CALENDAR_DAILY_USE_V1,
    )


def calendar_annual_daily_use_scope_v1(market: Literal["twse", "tpex"]) -> DailySourceUseScope:
    if type(market) is not str or market not in ("twse", "tpex"):
        raise OfficialCalendarDailySnapshotError("calendar_batch_market_invalid")
    return DailySourceUseScope(
        dataset_id="official_trading_calendar", source_id=f"{market}.official_calendar.annual",
        market=market, parser_version=CALENDAR_ANNUAL_DAILY_PARSER_V1,
        source_schema_version=("twse.holidaySchedule.stock_annual.v1" if market == "twse"
                               else "tpex.tradingDate.stock_annual.v1"),
        unit="trading_session_date", intended_use=CALENDAR_DAILY_USE_V1,
    )


def calendar_daily_acceptance_mode_v1(
    values: Sequence[DailySourceUseAcceptance],
) -> Literal["monthly_v1", "annual_v1"]:
    """只核caller明示的獨立錨點；不讀封套、自授接受或混搭來源版本。"""
    if (not isinstance(values, Sequence) or len(values) != 2
            or any(type(value) is not DailySourceUseAcceptance for value in values)):
        raise OfficialCalendarDailySnapshotError("calendar_batch_both_trusted_acceptances_required")
    for codec, mode in ((_MONTHLY_CODEC, "monthly_v1"), (_ANNUAL_CODEC, "annual_v1")):
        expected_scopes = tuple((calendar_annual_daily_use_scope_v1(market) if codec.annual
                                 else calendar_daily_use_scope_v1(market)) for market in _MARKETS)
        endpoints = (TWSE_HOLIDAY_SCHEDULE_URL,
                     TPEX_ANNUAL_TRADING_DATE_URL if codec.annual else TPEX_MARKET_CALENDAR_URL)
        if all(value.scope == scope and value.official_source_endpoint == endpoint
               for value, scope, endpoint in zip(values, expected_scopes, endpoints)):
            if mode == "annual_v1":
                return "annual_v1"
            return "monthly_v1"
    raise OfficialCalendarDailySnapshotError("calendar_batch_acceptance_scope_mismatch")


def _transport_type_allowed(value: object, *, codec: _DailyCalendarCodecV1) -> bool:
    if codec.annual:
        return ((type(value) is OfficialCalendarJsonTransportV1 and value.kind == "twse")
                or type(value) is OfficialCalendarTpexAnnualJsonTransportV1)
    return type(value) is OfficialCalendarJsonTransportV1


def _decode_transports(
    values: Sequence[object], *, codec: _DailyCalendarCodecV1,
) -> tuple[_CalendarTransportV1, ...]:
    result: list[_CalendarTransportV1] = []
    for value in values:
        if not codec.annual:
            result.append(OfficialCalendarJsonTransportV1.from_dict(value))
        elif type(value) is dict and value.get("schema_version") == TPEX_ANNUAL_CALENDAR_TRANSPORT_SCHEMA_V1:
            result.append(OfficialCalendarTpexAnnualJsonTransportV1.from_dict(value))
        elif type(value) is dict and value.get("schema_version") == CALENDAR_TRANSPORT_SCHEMA_V1:
            twse = OfficialCalendarJsonTransportV1.from_dict(value)
            if twse.kind != "twse":
                raise OfficialCalendarDailySnapshotError("calendar_batch_annual_typed_transports_required")
            result.append(twse)
        else:
            raise OfficialCalendarDailySnapshotError("calendar_batch_annual_transport_schema_invalid")
    return tuple(result)


def _acceptances(
    values: Mapping[str, DailySourceUseAcceptance], *, codec: _DailyCalendarCodecV1 = _MONTHLY_CODEC,
) -> tuple[DailySourceUseAcceptance, ...]:
    if not isinstance(values, Mapping) or set(values) != {"twse", "tpex"}:
        raise OfficialCalendarDailySnapshotError("calendar_batch_both_trusted_acceptances_required")
    result = []
    for market in _MARKETS:
        endpoint = TWSE_HOLIDAY_SCHEDULE_URL if market == "twse" else (
            TPEX_ANNUAL_TRADING_DATE_URL if codec.annual else TPEX_MARKET_CALENDAR_URL
        )
        value = values[market]
        if (type(value) is not DailySourceUseAcceptance
                or value.scope != (calendar_annual_daily_use_scope_v1(market) if codec.annual
                                   else calendar_daily_use_scope_v1(market))
                or value.official_source_endpoint != endpoint):
            raise OfficialCalendarDailySnapshotError("calendar_batch_acceptance_scope_mismatch")
        result.append(value)
    return tuple(result)


def _partitions(
    start: date, end: date, *, codec: _DailyCalendarCodecV1 = _MONTHLY_CODEC,
) -> tuple[str, ...]:
    if type(start) is not date or type(end) is not date or not 1 <= (end - start).days + 1 <= MAX_CAPTURE_DAYS:
        raise OfficialCalendarDailySnapshotError("calendar_batch_inclusive_93_day_limit")
    keys = [f"twse:{year}" for year in range(start.year, end.year + 1)]
    if codec.annual:
        keys.extend(f"tpex-annual:{year}" for year in range(start.year, end.year + 1))
        return tuple(sorted(keys))
    month = start.replace(day=1)
    while month <= end:
        keys.append(f"tpex:{month:%Y%m}")
        month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    return tuple(sorted(keys))


def _derive(
    start: date, end: date, transports: Sequence[_CalendarTransportV1], *,
    codec: _DailyCalendarCodecV1 = _MONTHLY_CODEC,
) -> tuple[PortfolioPeriodCalendarEvidenceReadV1, tuple[str, ...]]:
    expected = _partitions(start, end, codec=codec)
    if codec.annual:
        twse: list[OfficialCalendarJsonTransportV1] = []
        tpex: list[OfficialCalendarTpexAnnualJsonTransportV1] = []
        for item in transports:
            if type(item) is OfficialCalendarJsonTransportV1 and item.kind == "twse":
                twse.append(item)
            elif type(item) is OfficialCalendarTpexAnnualJsonTransportV1:
                tpex.append(item)
            else:
                raise OfficialCalendarDailySnapshotError("calendar_batch_annual_typed_transports_required")
        keys = tuple(sorted([f"twse:{item.key}" for item in twse]
                            + [f"tpex-annual:{item.year}" for item in tpex]))
        if keys != expected:
            raise OfficialCalendarDailySnapshotError("calendar_batch_missing_duplicate_or_unexpected_partition")
        annual = PortfolioPeriodAnnualCalendarEvidenceV1.build(
            start_date=start, end_date=end, twse_transports=twse, tpex_transports=tpex,
        )
        return annual, keys
    monthly: list[OfficialCalendarJsonTransportV1] = []
    if not 1 <= len(transports) <= 8:
        raise OfficialCalendarDailySnapshotError("calendar_batch_typed_complete_transports_required")
    for item in transports:
        if type(item) is not OfficialCalendarJsonTransportV1:
            raise OfficialCalendarDailySnapshotError("calendar_batch_typed_complete_transports_required")
        monthly.append(item)
    keys = tuple(sorted(f"{item.kind}:{item.key}" for item in monthly))
    if keys != expected:
        raise OfficialCalendarDailySnapshotError("calendar_batch_missing_duplicate_or_unexpected_partition")
    responses = [item.to_response() for item in monthly]
    evidence = PortfolioPeriodCalendarEvidenceV1.build(
        start_date=start, end_date=end,
        twse_responses={int(item.key): item for item in responses if item.kind == "twse"},
        tpex_responses={item.key: item for item in responses if item.kind == "tpex"},
        captured_at=max(item.body_completed_at for item in monthly), capture_mode="bounded_network",
    )
    return evidence, keys


def _manifest(
    batch_id: str, start: date, end: date, capture_sha: str,
    evidence: PortfolioPeriodCalendarEvidenceReadV1, partitions: tuple[str, ...],
    *, codec: _DailyCalendarCodecV1 = _MONTHLY_CODEC,
) -> dict[str, object]:
    return {
        "schema_version": codec.manifest_schema, "batch_id": batch_id,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "parser_version": codec.parser_version, "capture_sha256": capture_sha,
        "calendar_evidence_sha256": evidence.evidence_sha256,
        "expected_session_dates": {market: list(evidence.expected_session_dates(market)) for market in _MARKETS},
        "partitions": list(partitions),
        "validation": {
            "complete_http_body": "pass", "raw_sha256": "pass", "source_url": "pass",
            "schema": codec.evidence_schema,
            "calendar_rederived": "pass", "partition_coverage": "pass", "unit": "trading_session_date",
        },
        # 目前支援schema無經接受的版本timestamp；保留headers但不借作發布時間。
        "official_timestamp": None, "official_timestamp_original_text": "",
        "official_time_basis": "not_in_supported_source_schema",
        "time_basis_policy": DAILY_SOURCE_TIME_BASIS_POLICY,
    }


def _object(raw: bytes, fields: frozenset[str]) -> dict[str, object]:
    value = _decode_object(raw, label="calendar_daily_version", maximum=_MAX_BYTES)
    if set(value) != fields or _canonical(value) != raw:
        raise OfficialCalendarDailySnapshotError("calendar_batch_noncanonical_or_unknown_fields")
    return value


def _guarded_directory(path: Path, protected_roots: Sequence[Path]) -> Path:
    return _validate_target(path / "__calendar_guard__", protected_roots, reading=False).parent


def _pending(path: Path) -> bool:
    return any(os.path.lexists(path / name) for name in (".receipt.pending.json", "failure.json"))


@dataclass(frozen=True, slots=True)
class _OfficialCalendarDailySnapshotV1(Generic[_EvidenceT]):
    """外部錨點核對後的前瞻小時版本；原日曆candidate資格保持不變。"""

    batch_directory: Path
    batch_id: str
    manifest_sha256: str
    receipt_sha256: str
    capture_sha256: str
    evidence: _EvidenceT
    first_persisted_at: datetime
    successful_batch_completed_at: datetime
    available_hour: datetime
    availability_basis: str

    def is_available_at(self, decision_cutoff: datetime) -> bool:
        cutoff = _local(decision_cutoff)
        return self.first_persisted_at <= cutoff and self.available_hour <= cutoff

    @property
    def historical_pit_eligible(self) -> Literal[False]:
        return False

    @property
    def performance_eligible(self) -> Literal[False]:
        return False

    @property
    def formal_clock_eligible(self) -> Literal[False]:
        return False


@dataclass(frozen=True, slots=True)
class OfficialCalendarDailySnapshotV1(_OfficialCalendarDailySnapshotV1[PortfolioPeriodCalendarEvidenceV1]):
    """原月別來源的成功批次；公開欄位與V1 wire原義保持。"""


@dataclass(frozen=True, slots=True)
class OfficialCalendarAnnualDailySnapshotV1(_OfficialCalendarDailySnapshotV1[PortfolioPeriodAnnualCalendarEvidenceV1]):
    """具名年度來源成功批次，不共用月別用途接受。"""


_CalendarDailySnapshotV1 = OfficialCalendarDailySnapshotV1 | OfficialCalendarAnnualDailySnapshotV1


def _read_official_calendar_daily_snapshot_v1(
    batch_directory: Path, *, expected_manifest_sha256: str, expected_receipt_sha256: str,
    trusted_acceptances: Mapping[str, DailySourceUseAcceptance], protected_roots: Sequence[Path],
    decision_cutoff: datetime | None = None, check_cancel: Callable[[], bool] | None = None,
    codec: _DailyCalendarCodecV1,
) -> _CalendarDailySnapshotV1:
    """只讀指定完成批次；來源自述不能取代caller兩份接受錨點。"""
    accepted = _acceptances(trusted_acceptances, codec=codec)
    root = _guarded_directory(batch_directory, protected_roots)
    if root.parent.name != "batches" or root.name != _batch_id(root.name) or _pending(root):
        raise OfficialCalendarDailySnapshotError("calendar_batch_not_published_or_pending")
    _cancel(check_cancel)
    manifest_raw = read_calendar_version_bytes_exact_v1(
        root / "manifest.json", expected_sha256=expected_manifest_sha256, protected_roots=protected_roots,
    )
    receipt_raw = read_calendar_version_bytes_exact_v1(
        root / "receipt.json", expected_sha256=expected_receipt_sha256, protected_roots=protected_roots,
    )
    manifest = _object(manifest_raw, _MANIFEST_FIELDS)
    receipt = _object(receipt_raw, _RECEIPT_FIELDS)
    capture_sha = manifest["capture_sha256"]
    if type(capture_sha) is not str:
        raise OfficialCalendarDailySnapshotError("calendar_batch_capture_sha_invalid")
    capture_raw = read_calendar_version_bytes_exact_v1(
        root / "capture.json", expected_sha256=capture_sha, protected_roots=protected_roots,
    )
    capture = _object(capture_raw, _CAPTURE_FIELDS)
    if (capture["schema_version"] != codec.capture_schema
            or capture["batch_id"] != root.name or capture["parser_version"] != codec.parser_version
            or capture["use_acceptances"] != {value.scope.market: value.to_dict() for value in accepted}):
        raise OfficialCalendarDailySnapshotError("calendar_batch_capture_or_trusted_acceptance_mismatch")
    start_text, end_text = capture["start_date"], capture["end_date"]
    if type(start_text) is not str or type(end_text) is not str:
        raise OfficialCalendarDailySnapshotError("calendar_batch_dates_invalid")
    start, end = date.fromisoformat(start_text), date.fromisoformat(end_text)
    values = capture["transports"]
    if type(values) is not list or not 1 <= len(values) <= 8:
        raise OfficialCalendarDailySnapshotError("calendar_batch_transports_invalid")
    transports = _decode_transports(values, codec=codec)
    _cancel(check_cancel)
    evidence, partitions = _derive(start, end, transports, codec=codec)
    if manifest != _manifest(root.name, start, end, capture_sha, evidence, partitions, codec=codec):
        raise OfficialCalendarDailySnapshotError("calendar_batch_manifest_rederive_mismatch")
    first, completed = _time(receipt["first_persisted_at"]), _time(receipt["successful_batch_completed_at"])
    started = min(_local(item.started_at) for item in transports)
    if (first < max(_local(item.body_completed_at) for item in transports)
            or first < max(value.accepted_at for value in accepted) or completed < first
            or first.replace(minute=0, second=0, microsecond=0) != completed.replace(minute=0, second=0, microsecond=0)):
        raise OfficialCalendarDailySnapshotError("calendar_batch_clock_causality_or_hour_mismatch")
    available, basis = _availability(completed)
    expected_receipt = {
        "schema_version": codec.receipt_schema, "batch_id": root.name,
        "manifest_sha256": expected_manifest_sha256, "capture_sha256": capture_sha,
        "batch_status": "success", "source_batch_started_at": started.isoformat(),
        "first_persisted_at": first.isoformat(), "successful_batch_completed_at": completed.isoformat(),
        "completion_basis": "durable_pending_receipt_closed", "available_hour": available.isoformat(),
        "availability_basis": basis, "time_basis_policy": DAILY_SOURCE_TIME_BASIS_POLICY,
    }
    if receipt != expected_receipt:
        raise OfficialCalendarDailySnapshotError("calendar_batch_receipt_or_availability_mismatch")
    # 解碼及衍生完成後重驗同一組bytes與barrier，拒絕讀取期間更正。
    for name, expected_sha in (("capture.json", capture_sha), ("manifest.json", expected_manifest_sha256),
                               ("receipt.json", expected_receipt_sha256)):
        _cancel(check_cancel)
        read_calendar_version_bytes_exact_v1(root / name, expected_sha256=expected_sha, protected_roots=protected_roots)
    if _pending(root):
        raise OfficialCalendarDailySnapshotError("calendar_batch_pending_after_read")
    result: _CalendarDailySnapshotV1
    if codec.annual and type(evidence) is PortfolioPeriodAnnualCalendarEvidenceV1:
        result = OfficialCalendarAnnualDailySnapshotV1(
            root, root.name, expected_manifest_sha256, expected_receipt_sha256, capture_sha,
            evidence, first, completed, available, basis,
        )
    elif not codec.annual and type(evidence) is PortfolioPeriodCalendarEvidenceV1:
        result = OfficialCalendarDailySnapshotV1(
            root, root.name, expected_manifest_sha256, expected_receipt_sha256, capture_sha,
            evidence, first, completed, available, basis,
        )
    else:
        raise OfficialCalendarDailySnapshotError("calendar_batch_evidence_mode_mismatch")
    if decision_cutoff is not None and not result.is_available_at(decision_cutoff):
        raise OfficialCalendarDailySnapshotError("calendar_batch_not_available_at_cutoff")
    _cancel(check_cancel)
    return result


def _write_official_calendar_daily_snapshot_v1(
    root: Path, *, batch_id: str, start_date: date, end_date: date,
    transports: Sequence[_CalendarTransportV1],
    trusted_acceptances: Mapping[str, DailySourceUseAcceptance], protected_roots: Sequence[Path],
    clock: Callable[[], datetime] | None = None, check_cancel: Callable[[], bool] | None = None,
    codec: _DailyCalendarCodecV1,
) -> _CalendarDailySnapshotV1:
    """原件先create-only/fsync，再解析與收據；失敗保留staging及具名原因。"""
    name = _batch_id(batch_id)
    base = _guarded_directory(root, protected_roots)
    accepted = _acceptances(trusted_acceptances, codec=codec)
    frozen = tuple(transports)
    if (not 1 <= len(frozen) <= 8 or any(not _transport_type_allowed(value, codec=codec) for value in frozen)
            or type(start_date) is not date or type(end_date) is not date):
        raise OfficialCalendarDailySnapshotError("calendar_batch_input_invalid")
    get_clock = clock or (lambda: datetime.now(_TAIPEI))
    for directory in (base / ".staging", base / "batches"):
        directory.mkdir(exist_ok=True)
        _guarded_directory(directory, protected_roots)
    stage, final = base / ".staging" / name, base / "batches" / name
    if os.path.lexists(final) or os.path.lexists(stage):
        raise OfficialCalendarDailySnapshotError("calendar_batch_create_only_collision")
    stage.mkdir()
    _guarded_directory(stage, protected_roots)
    owned = stage
    try:
        _cancel(check_cancel)
        capture = {
            "schema_version": codec.capture_schema, "batch_id": name,
            "start_date": start_date.isoformat(), "end_date": end_date.isoformat(),
            "parser_version": codec.parser_version,
            "use_acceptances": {value.scope.market: value.to_dict() for value in accepted},
            "transports": [item.to_dict() for item in frozen],
        }
        capture_sha = write_calendar_version_bytes_create_only_v1(
            stage / "capture.json", _canonical(capture), protected_roots=protected_roots,
        )
        first = _local(get_clock())
        if first < max(_local(value.body_completed_at) for value in frozen) or first < max(value.accepted_at for value in accepted):
            raise OfficialCalendarDailySnapshotError("calendar_batch_first_persisted_clock_invalid")
        _cancel(check_cancel)
        evidence, partitions = _derive(start_date, end_date, frozen, codec=codec)
        manifest = _manifest(name, start_date, end_date, capture_sha, evidence, partitions, codec=codec)
        manifest_sha = write_calendar_version_bytes_create_only_v1(
            stage / "manifest.json", _canonical(manifest), protected_roots=protected_roots,
        )
        pending_raw = _canonical({"batch_id": name, "manifest_sha256": manifest_sha, "status": "prepared"})
        pending_sha = write_calendar_version_bytes_create_only_v1(
            stage / ".receipt.pending.json", pending_raw, protected_roots=protected_roots,
        )
        completed = _local(get_clock())
        if (completed < first
                or first.replace(minute=0, second=0, microsecond=0) != completed.replace(minute=0, second=0, microsecond=0)):
            raise OfficialCalendarDailySnapshotError("calendar_batch_persistence_crossed_hour_or_clock_reversed")
        available, basis = _availability(completed)
        receipt = {
            "schema_version": codec.receipt_schema, "batch_id": name,
            "manifest_sha256": manifest_sha, "capture_sha256": capture_sha, "batch_status": "success",
            "source_batch_started_at": min(_local(value.started_at) for value in frozen).isoformat(),
            "first_persisted_at": first.isoformat(), "successful_batch_completed_at": completed.isoformat(),
            "completion_basis": "durable_pending_receipt_closed", "available_hour": available.isoformat(),
            "availability_basis": basis, "time_basis_policy": DAILY_SOURCE_TIME_BASIS_POLICY,
        }
        receipt_sha = write_calendar_version_bytes_create_only_v1(
            stage / "receipt.json", _canonical(receipt), protected_roots=protected_roots,
        )
        persisted = _local(get_clock())
        if not completed <= persisted <= available:
            raise OfficialCalendarDailySnapshotError("calendar_batch_receipt_persisted_outside_guard")
        _cancel(check_cancel)
        if os.path.lexists(final):
            raise OfficialCalendarDailySnapshotError("calendar_batch_create_only_collision")
        os.rename(stage, final)
        owned = final
        published = _local(get_clock())
        if not persisted <= published <= available:
            raise OfficialCalendarDailySnapshotError("calendar_batch_published_outside_guard")
        _cancel(check_cancel)
        read_calendar_version_bytes_exact_v1(
            final / ".receipt.pending.json", expected_sha256=pending_sha, protected_roots=protected_roots,
        )
        _cancel(check_cancel)
        # 與既有daily writer相同：發布後時鐘通過，才解除自己擁有的barrier。
        (final / ".receipt.pending.json").unlink()
        return _read_official_calendar_daily_snapshot_v1(
            final, expected_manifest_sha256=manifest_sha, expected_receipt_sha256=receipt_sha,
            trusted_acceptances=trusted_acceptances, protected_roots=protected_roots, codec=codec,
        )
    except Exception as exc:
        try:
            write_calendar_version_bytes_create_only_v1(
                owned / "failure.json", _canonical({
                    "schema_version": ("official-calendar-annual-daily-failure.v1" if codec.annual
                                       else "official-calendar-daily-failure.v1"), "batch_id": name,
                    "reason": str(exc)[:1024], "successful": False,
                }), protected_roots=protected_roots,
            )
        except Exception as preservation_error:
            exc.add_note("calendar_batch_failure_preservation_failed:" + str(preservation_error))
        raise


def read_official_calendar_daily_snapshot_v1(
    batch_directory: Path, *, expected_manifest_sha256: str, expected_receipt_sha256: str,
    trusted_acceptances: Mapping[str, DailySourceUseAcceptance], protected_roots: Sequence[Path],
    decision_cutoff: datetime | None = None, check_cancel: Callable[[], bool] | None = None,
) -> OfficialCalendarDailySnapshotV1:
    result = _read_official_calendar_daily_snapshot_v1(
        batch_directory, expected_manifest_sha256=expected_manifest_sha256,
        expected_receipt_sha256=expected_receipt_sha256, trusted_acceptances=trusted_acceptances,
        protected_roots=protected_roots, decision_cutoff=decision_cutoff,
        check_cancel=check_cancel, codec=_MONTHLY_CODEC,
    )
    if type(result) is not OfficialCalendarDailySnapshotV1:
        raise OfficialCalendarDailySnapshotError("calendar_batch_snapshot_mode_mismatch")
    return result


def read_official_calendar_annual_daily_snapshot_v1(
    batch_directory: Path, *, expected_manifest_sha256: str, expected_receipt_sha256: str,
    trusted_acceptances: Mapping[str, DailySourceUseAcceptance], protected_roots: Sequence[Path],
    decision_cutoff: datetime | None = None, check_cancel: Callable[[], bool] | None = None,
) -> OfficialCalendarAnnualDailySnapshotV1:
    result = _read_official_calendar_daily_snapshot_v1(
        batch_directory, expected_manifest_sha256=expected_manifest_sha256,
        expected_receipt_sha256=expected_receipt_sha256, trusted_acceptances=trusted_acceptances,
        protected_roots=protected_roots, decision_cutoff=decision_cutoff,
        check_cancel=check_cancel, codec=_ANNUAL_CODEC,
    )
    if type(result) is not OfficialCalendarAnnualDailySnapshotV1:
        raise OfficialCalendarDailySnapshotError("calendar_batch_snapshot_mode_mismatch")
    return result


def write_official_calendar_daily_snapshot_v1(
    root: Path, *, batch_id: str, start_date: date, end_date: date,
    transports: Sequence[OfficialCalendarJsonTransportV1],
    trusted_acceptances: Mapping[str, DailySourceUseAcceptance], protected_roots: Sequence[Path],
    clock: Callable[[], datetime] | None = None, check_cancel: Callable[[], bool] | None = None,
) -> OfficialCalendarDailySnapshotV1:
    result = _write_official_calendar_daily_snapshot_v1(
        root, batch_id=batch_id, start_date=start_date, end_date=end_date, transports=transports,
        trusted_acceptances=trusted_acceptances, protected_roots=protected_roots,
        clock=clock, check_cancel=check_cancel, codec=_MONTHLY_CODEC,
    )
    if type(result) is not OfficialCalendarDailySnapshotV1:
        raise OfficialCalendarDailySnapshotError("calendar_batch_snapshot_mode_mismatch")
    return result


def write_official_calendar_annual_daily_snapshot_v1(
    root: Path, *, batch_id: str, start_date: date, end_date: date,
    transports: Sequence[_CalendarTransportV1],
    trusted_acceptances: Mapping[str, DailySourceUseAcceptance], protected_roots: Sequence[Path],
    clock: Callable[[], datetime] | None = None, check_cancel: Callable[[], bool] | None = None,
) -> OfficialCalendarAnnualDailySnapshotV1:
    result = _write_official_calendar_daily_snapshot_v1(
        root, batch_id=batch_id, start_date=start_date, end_date=end_date, transports=transports,
        trusted_acceptances=trusted_acceptances, protected_roots=protected_roots,
        clock=clock, check_cancel=check_cancel, codec=_ANNUAL_CODEC,
    )
    if type(result) is not OfficialCalendarAnnualDailySnapshotV1:
        raise OfficialCalendarDailySnapshotError("calendar_batch_snapshot_mode_mismatch")
    return result
