"""研究用 security lifecycle → PIT taxonomy → industry caller。\n\n這個 caller 把既有的 MOPS lifecycle contract、官方交易日曆、已發布的\nPIT taxonomy sidecar 與 ``IndustryStrengthService`` 接成一個唯讀 read model。\n它只允許 caller 自己提供、且逐日經交易日曆驗證的 successor 價格 lineage；\n不讀取 legacy parent 的價格或分數，也不授予 Formal／natural credit。\n\n這是研究範圍的接線，不是新的排程器、registry 或 Formal rule producer。\n"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from app_module.decision_desk_dtos import IndustryStrengthSummary
from app_module.industry_strength_service import IndustryStrengthService
from data_module.official_trading_calendar import (
    OfficialTradingCalendar,
    OfficialTradingCalendarError,
)
from data_module.pit_sector_membership_reader import PITMembershipReadResult
from data_module.security_lifecycle_contract import (
    SecurityLifecycleContractError,
    SecurityLifecycleEvent,
    SecurityLifecycleState,
    SuccessorSessionEvidence,
    read_security_lifecycle_contract,
    security_lifecycle_state_as_of,
)


_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SYMBOL_RE = re.compile(r"^[0-9]{4,6}$")
_TAIPEI = ZoneInfo("Asia/Taipei")


class SecurityLifecycleCallerError(ValueError):
    """Lifecycle caller 無法建立可重驗的研究 read model。"""


def _require_hash(value: object, field_name: str) -> str:
    text = str(value or "")
    if _SHA256_RE.fullmatch(text) is None:
        raise SecurityLifecycleCallerError(f"{field_name} must be sha256:<64 hex>")
    return text


def _require_symbol(value: object, field_name: str) -> str:
    text = str(value or "").strip()
    if _SYMBOL_RE.fullmatch(text) is None:
        raise SecurityLifecycleCallerError(f"{field_name} must be a stock symbol")
    return text


def _aware_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise SecurityLifecycleCallerError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _normalize_symbols(value: Sequence[str], field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise SecurityLifecycleCallerError(f"{field_name} must be a symbol sequence")
    try:
        normalized = tuple(sorted({_require_symbol(item, field_name) for item in value}))
    except TypeError as error:
        raise SecurityLifecycleCallerError(f"{field_name} must be a symbol sequence") from error
    if not normalized:
        raise SecurityLifecycleCallerError(f"{field_name} must not be empty")
    return normalized


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise SecurityLifecycleCallerError(
            f"legacy parent reference is unreadable: {path}"
        ) from error
    return "sha256:" + digest.hexdigest()


@dataclass(frozen=True)
class LegacyParentReference:
    """只保留舊 parent 的可驗證引用，不攜帶其價格或 score。"""

    parent_id: str
    predecessor_symbol: str
    parent_path: Path
    parent_file_hash: str
    parent_universe_hash: str

    def __post_init__(self) -> None:
        parent_id = str(self.parent_id).strip()
        if not parent_id:
            raise SecurityLifecycleCallerError("legacy parent_id must not be empty")
        predecessor = _require_symbol(
            self.predecessor_symbol,
            "legacy predecessor_symbol",
        )
        parent_path = Path(self.parent_path).expanduser().resolve()
        object.__setattr__(self, "parent_id", parent_id)
        object.__setattr__(self, "predecessor_symbol", predecessor)
        object.__setattr__(self, "parent_path", parent_path)
        object.__setattr__(
            self,
            "parent_file_hash",
            _require_hash(self.parent_file_hash, "legacy parent_file_hash"),
        )
        object.__setattr__(
            self,
            "parent_universe_hash",
            _require_hash(self.parent_universe_hash, "legacy parent_universe_hash"),
        )

    def to_payload(self) -> dict[str, str]:
        return {
            "parent_id": self.parent_id,
            "predecessor_symbol": self.predecessor_symbol,
            "parent_path": str(self.parent_path),
            "parent_file_hash": self.parent_file_hash,
            "parent_universe_hash": self.parent_universe_hash,
        }


@dataclass(frozen=True)
class SecurityLifecycleIndustryResult:
    """Lifecycle caller 的唯讀、可序列化研究結果。"""

    event: SecurityLifecycleEvent
    state: SecurityLifecycleState
    membership: PITMembershipReadResult
    industry_summary: IndustryStrengthSummary
    legacy_parent: LegacyParentReference
    new_cohort_symbols: tuple[str, ...]
    full_cohort_symbols: tuple[str, ...]
    eligible_symbols: tuple[str, ...]
    excluded_symbols: tuple[str, ...]
    unknown_symbols: tuple[str, ...]
    successor_sessions: tuple[SuccessorSessionEvidence, ...]
    calendar_evidence: tuple[dict[str, object], ...]
    warmup_required_sessions: int
    warnings: tuple[str, ...] = ()
    accepted: bool = True

    def __post_init__(self) -> None:
        if type(self.warmup_required_sessions) is not int or self.warmup_required_sessions <= 0:
            raise SecurityLifecycleCallerError("warmup_required_sessions must be positive int")
        if self.accepted is not True:
            raise SecurityLifecycleCallerError("accepted lifecycle result must be true")
        if self.event.research_only is not True:
            raise SecurityLifecycleCallerError("lifecycle result must remain research-only")
        if any(
            flag is not False
            for flag in (
                self.event.formal_credit_allowed,
                self.event.natural_credit_allowed,
                self.event.historical_price_score_carry_forward_allowed,
                self.state.formal_credit_allowed,
                self.state.natural_credit_allowed,
                self.state.historical_price_score_carry_forward_allowed,
            )
        ):
            raise SecurityLifecycleCallerError("lifecycle credit guards must remain false")
        object.__setattr__(self, "new_cohort_symbols", tuple(self.new_cohort_symbols))
        object.__setattr__(self, "full_cohort_symbols", tuple(self.full_cohort_symbols))
        object.__setattr__(self, "eligible_symbols", tuple(self.eligible_symbols))
        object.__setattr__(self, "excluded_symbols", tuple(self.excluded_symbols))
        object.__setattr__(self, "unknown_symbols", tuple(self.unknown_symbols))
        object.__setattr__(self, "successor_sessions", tuple(self.successor_sessions))
        object.__setattr__(
            self,
            "calendar_evidence",
            tuple(dict(item) for item in self.calendar_evidence),
        )
        object.__setattr__(
            self,
            "warnings",
            tuple(dict.fromkeys(str(item) for item in self.warnings if str(item))),
        )

    @property
    def full_cohort_row_count(self) -> int:
        return len(self.membership.rows)

    @property
    def eligible_row_count(self) -> int:
        return sum(1 for row in self.membership.rows if row.security_eligible)

    @property
    def excluded_row_count(self) -> int:
        return sum(1 for row in self.membership.rows if not row.security_eligible)

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": "security-lifecycle-industry-caller.v1",
            "accepted": self.accepted,
            "source_chain": [
                "security_lifecycle_contract",
                "official_trading_calendar",
                "pit_taxonomy_publisher_readback",
                "pit_sector_membership_reader",
                "industry_strength_service",
            ],
            "event": self.event.to_payload(),
            "state": {
                "decision_at": self.state.decision_at.isoformat(),
                "decision_date": self.state.decision_date.isoformat(),
                "visible": self.state.visible,
                "phase": self.state.phase.value,
                "identity_status": self.state.identity_status.value,
                "market_status": self.state.market_status.value,
                "current_symbol": self.state.current_symbol,
                "predecessor_symbol": self.state.predecessor_symbol,
                "successor_symbol": self.state.successor_symbol,
                "market_tradable": self.state.market_tradable,
                "history_warmup_complete": self.state.history_warmup_complete,
                "score_eligibility": self.state.score_eligibility.value,
                "reason_codes": list(self.state.reason_codes),
                "formal_credit_allowed": self.state.formal_credit_allowed,
                "natural_credit_allowed": self.state.natural_credit_allowed,
                "historical_price_score_carry_forward_allowed": (
                    self.state.historical_price_score_carry_forward_allowed
                ),
            },
            "legacy_parent_reference": self.legacy_parent.to_payload(),
            "cohort": {
                "new_cohort_symbols": list(self.new_cohort_symbols),
                "full_cohort_symbols": list(self.full_cohort_symbols),
                "full_cohort_row_count": self.full_cohort_row_count,
                "eligible_symbols": list(self.eligible_symbols),
                "eligible_row_count": self.eligible_row_count,
                "excluded_symbols": list(self.excluded_symbols),
                "excluded_row_count": self.excluded_row_count,
                "unknown_symbols": list(self.unknown_symbols),
                "unknown_row_count": len(self.unknown_symbols),
            },
            "warmup": {
                "required_sessions": self.warmup_required_sessions,
                "observed_sessions": len(self.successor_sessions),
                "history_warmup_complete": self.state.history_warmup_complete,
                "score_eligibility": self.state.score_eligibility.value,
                "successor_sessions": [
                    {
                        "session_date": item.session_date.isoformat(),
                        "symbol": item.symbol,
                        "official_trading_day_verified": item.official_trading_day_verified,
                        "price_source_id": item.price_source_id,
                        "price_lineage_sha256": item.price_lineage_sha256,
                    }
                    for item in self.successor_sessions
                ],
                "calendar_evidence": list(self.calendar_evidence),
            },
            "taxonomy": self.membership.to_dict(),
            "industry_strength": self.industry_summary.to_dict(),
            "quality": {
                "research_only": True,
                "formal_credit_allowed": False,
                "natural_credit_allowed": False,
                "historical_price_score_carry_forward_allowed": False,
            },
            "warnings": list(self.warnings),
        }


class SecurityLifecycleIndustryCaller:
    """把 lifecycle successor 研究 cohort 接到既有 PIT industry caller。"""

    source_chain_version = "security-lifecycle-industry-caller.v1"

    def __init__(
        self,
        *,
        calendar: OfficialTradingCalendar,
        industry_service: IndustryStrengthService,
        required_warmup_sessions: int = 20,
    ) -> None:
        if not isinstance(calendar, OfficialTradingCalendar):
            raise SecurityLifecycleCallerError(
                "calendar must be an OfficialTradingCalendar"
            )
        if not isinstance(industry_service, IndustryStrengthService):
            raise SecurityLifecycleCallerError(
                "industry_service must be an IndustryStrengthService"
            )
        if type(required_warmup_sessions) is not int or required_warmup_sessions <= 0:
            raise SecurityLifecycleCallerError(
                "required_warmup_sessions must be positive int"
            )
        if industry_service.pit_membership_reader is None:
            raise SecurityLifecycleCallerError(
                "industry_service must have a PIT membership reader"
            )
        self.calendar = calendar
        self.industry_service = industry_service
        self.required_warmup_sessions = required_warmup_sessions

    def evaluate(
        self,
        *,
        contract_path: Path,
        decision_at: datetime,
        as_of_date: date,
        new_cohort_symbols: Sequence[str],
        legacy_parent_reference: LegacyParentReference,
        successor_sessions: Sequence[SuccessorSessionEvidence],
        allow_online_probe: bool = False,
    ) -> SecurityLifecycleIndustryResult:
        """讀取 contract、驗證 successor session，再產出 industry read model。

        ``allow_online_probe`` 預設為 False。正式 caller 若要使用 live TWSE
        annual schedule，必須明確打開；無論哪一種模式，calendar 未解析都會
        fail closed。``successor_sessions`` 的第一個與最後一個日期之間，
        必須完整覆蓋官方 calendar 判定為開市的日期，避免用稀疏日期冒充
        warm-up session 數量。
        """

        if not isinstance(as_of_date, date) or isinstance(as_of_date, datetime):
            raise SecurityLifecycleCallerError("as_of_date must be a date")
        decision_utc = _aware_utc(decision_at, "decision_at")
        decision_date = decision_utc.astimezone(_TAIPEI).date()
        cohort = _normalize_symbols(new_cohort_symbols, "new_cohort_symbols")
        if not isinstance(legacy_parent_reference, LegacyParentReference):
            raise SecurityLifecycleCallerError("legacy_parent_reference type is invalid")
        if not isinstance(successor_sessions, Sequence) or isinstance(
            successor_sessions, (str, bytes)
        ):
            raise SecurityLifecycleCallerError("successor_sessions must be a sequence")
        sessions = tuple(successor_sessions)
        if not sessions:
            raise SecurityLifecycleCallerError("successor_sessions must not be empty")
        if not isinstance(allow_online_probe, bool):
            raise SecurityLifecycleCallerError("allow_online_probe must be bool")
        if as_of_date > decision_date:
            raise SecurityLifecycleCallerError("as_of_date is after decision cutoff")

        self._verify_legacy_parent(
            legacy_parent_reference,
        )
        try:
            event = read_security_lifecycle_contract(
                Path(contract_path).expanduser().resolve()
            )
        except (OSError, SecurityLifecycleContractError) as error:
            raise SecurityLifecycleCallerError(
                f"lifecycle contract readback failed: {error}"
            ) from error

        if event.predecessor.symbol != legacy_parent_reference.predecessor_symbol:
            raise SecurityLifecycleCallerError(
                "legacy parent predecessor does not match lifecycle event"
            )
        if event.successor.symbol not in cohort:
            raise SecurityLifecycleCallerError(
                "new cohort does not include lifecycle successor"
            )
        if as_of_date < event.successor_listed_date:
            raise SecurityLifecycleCallerError(
                "new cohort is not effective at the requested as_of_date"
            )

        ordered_sessions, calendar_evidence = self._verify_successor_sessions(
            event=event,
            decision_date=decision_date,
            sessions=sessions,
            allow_online_probe=allow_online_probe,
        )
        try:
            state = security_lifecycle_state_as_of(
                event,
                decision_at,
                observed_sessions=ordered_sessions,
                required_warmup_sessions=self.required_warmup_sessions,
            )
        except SecurityLifecycleContractError as error:
            raise SecurityLifecycleCallerError(
                f"lifecycle state projection failed: {error}"
            ) from error
        if not state.visible or state.current_symbol != event.successor.symbol:
            raise SecurityLifecycleCallerError(
                "lifecycle successor is not visible at decision cutoff"
            )

        membership = self._read_membership(
            as_of_date=as_of_date,
            decision_at=decision_at,
        )
        if membership.status != "accepted" or not membership.industry_filter_usable:
            raise SecurityLifecycleCallerError(
                "PIT taxonomy reader is not accepted: "
                + ",".join(membership.warnings)
            )
        full_symbols = tuple(sorted({row.symbol for row in membership.rows}))
        if full_symbols != cohort:
            raise SecurityLifecycleCallerError(
                "PIT taxonomy full denominator does not match new cohort"
            )
        eligible_symbols = tuple(
            sorted({row.symbol for row in membership.rows if row.security_eligible})
        )
        excluded_symbols = tuple(
            sorted({row.symbol for row in membership.rows if not row.security_eligible})
        )
        unknown_symbols = tuple(
            sorted(
                {
                    row.symbol
                    for row in membership.rows
                    if not row.security_eligible
                    and (row.security_exclusion_reason or "").startswith("unknown")
                }
            )
        )

        try:
            industry_summary = self.industry_service.build_industry_strength(
                as_of_date,
                decision_at=decision_at,
            )
        except Exception as error:  # noqa: BLE001 - read boundary remains fail closed
            raise SecurityLifecycleCallerError(
                f"industry caller failed: {type(error).__name__}"
            ) from error
        self._verify_industry_readback(
            summary=industry_summary,
            event=event,
            full_symbols=full_symbols,
            eligible_symbols=eligible_symbols,
            excluded_symbols=excluded_symbols,
        )

        warnings = tuple(
            dict.fromkeys(
                (
                    *membership.warnings,
                    *industry_summary.warnings,
                    *state.reason_codes,
                )
            )
        )
        return SecurityLifecycleIndustryResult(
            event=event,
            state=state,
            membership=membership,
            industry_summary=industry_summary,
            legacy_parent=legacy_parent_reference,
            new_cohort_symbols=cohort,
            full_cohort_symbols=full_symbols,
            eligible_symbols=eligible_symbols,
            excluded_symbols=excluded_symbols,
            unknown_symbols=unknown_symbols,
            successor_sessions=ordered_sessions,
            calendar_evidence=calendar_evidence,
            warmup_required_sessions=self.required_warmup_sessions,
            warnings=warnings,
        )

    @staticmethod
    def _verify_legacy_parent(reference: LegacyParentReference) -> None:
        path = reference.parent_path
        if path.is_symlink() or not path.is_file():
            raise SecurityLifecycleCallerError(
                f"legacy parent reference is missing: {path}"
            )
        if _file_sha256(path) != reference.parent_file_hash:
            raise SecurityLifecycleCallerError(
                "legacy parent reference file hash mismatch"
            )

    def _verify_successor_sessions(
        self,
        *,
        event: SecurityLifecycleEvent,
        decision_date: date,
        sessions: tuple[SuccessorSessionEvidence, ...],
        allow_online_probe: bool,
    ) -> tuple[tuple[SuccessorSessionEvidence, ...], tuple[dict[str, object], ...]]:
        if any(not isinstance(item, SuccessorSessionEvidence) for item in sessions):
            raise SecurityLifecycleCallerError(
                "successor_sessions must contain typed SuccessorSessionEvidence"
            )
        ordered = tuple(sorted(sessions, key=lambda item: item.session_date))
        dates = tuple(item.session_date for item in ordered)
        if len(dates) != len(set(dates)):
            raise SecurityLifecycleCallerError("successor_sessions contain duplicate dates")
        if any(item.symbol != event.successor.symbol for item in ordered):
            raise SecurityLifecycleCallerError(
                "successor_sessions contain a non-successor symbol"
            )
        if any(
            item.session_date < event.successor_listed_date
            or item.session_date >= decision_date
            for item in ordered
        ):
            raise SecurityLifecycleCallerError(
                "successor_sessions fall outside the successor decision window"
            )

        try:
            records = self.calendar.require_trading_days_in_range(
                dates[0],
                dates[-1],
                allow_online_probe=allow_online_probe,
            )
        except (OfficialTradingCalendarError, OSError, ValueError) as error:
            raise SecurityLifecycleCallerError(
                f"official successor calendar verification failed: {error}"
            ) from error

        official_open_dates: set[date] = set()
        evidence_by_date: dict[date, dict[str, object]] = {}
        for record in records:
            target = record.get("date")
            is_trading = record.get("is_trading_day")
            if not isinstance(target, date) or isinstance(target, datetime):
                raise SecurityLifecycleCallerError(
                    "official calendar returned an invalid date"
                )
            if is_trading is True:
                official_open_dates.add(target)
            raw_evidence = record.get("evidence")
            evidence_by_date[target] = {
                "date": target.isoformat(),
                "date_str": str(record.get("date_str") or target.isoformat()),
                "is_trading_day": is_trading,
                "reason_code": str(record.get("reason_code") or ""),
                "evidence": dict(raw_evidence) if isinstance(raw_evidence, Mapping) else {},
            }
        if official_open_dates != set(dates):
            raise SecurityLifecycleCallerError(
                "successor_sessions do not cover the full official calendar window"
            )
        return ordered, tuple(evidence_by_date[item] for item in sorted(evidence_by_date))

    def _read_membership(
        self,
        *,
        as_of_date: date,
        decision_at: datetime,
    ) -> PITMembershipReadResult:
        reader = self.industry_service.pit_membership_reader
        if reader is None:  # constructor already guards; keep the boundary typed
            raise SecurityLifecycleCallerError("PIT membership reader is unavailable")
        try:
            result = reader.read(
                as_of_date=as_of_date,
                decision_at=decision_at,
                market_scope=self.industry_service.pit_market_scope,
            )
        except Exception as error:  # noqa: BLE001 - reader failure is a hard gate
            raise SecurityLifecycleCallerError(
                f"PIT taxonomy reader failed: {type(error).__name__}"
            ) from error
        return result

    @staticmethod
    def _verify_industry_readback(
        *,
        summary: IndustryStrengthSummary,
        event: SecurityLifecycleEvent,
        full_symbols: tuple[str, ...],
        eligible_symbols: tuple[str, ...],
        excluded_symbols: tuple[str, ...],
    ) -> None:
        coverage = summary.coverage
        if coverage.get("mapping_mode") != "pit_accepted_prospective":
            raise SecurityLifecycleCallerError(
                "industry caller did not consume accepted PIT taxonomy"
            )
        if coverage.get("coverage_denominator") != "accepted_pit_membership_rows":
            raise SecurityLifecycleCallerError(
                "industry caller coverage denominator is not PIT membership rows"
            )
        expected_counts = {
            "pit_full_symbol_count": len(full_symbols),
            "pit_eligible_symbol_count": len(eligible_symbols),
            "pit_excluded_symbol_count": len(excluded_symbols),
        }
        for field_name, expected in expected_counts.items():
            if coverage.get(field_name) != expected:
                raise SecurityLifecycleCallerError(
                    f"industry caller {field_name} does not preserve cohort denominator"
                )
        if any(
            representative.stock_code == event.successor.symbol
            for row in summary.rows
            for representative in row.representative_stocks
        ) is not True:
            raise SecurityLifecycleCallerError(
                "industry caller did not expose the lifecycle successor"
            )


def run_security_lifecycle_industry_caller(
    *,
    calendar: OfficialTradingCalendar,
    industry_service: IndustryStrengthService,
    contract_path: Path,
    decision_at: datetime,
    as_of_date: date,
    new_cohort_symbols: Sequence[str],
    legacy_parent_reference: LegacyParentReference,
    successor_sessions: Sequence[SuccessorSessionEvidence],
    required_warmup_sessions: int = 20,
    allow_online_probe: bool = False,
) -> SecurityLifecycleIndustryResult:
    """Functional facade for callers that do not need to retain the service."""

    caller = SecurityLifecycleIndustryCaller(
        calendar=calendar,
        industry_service=industry_service,
        required_warmup_sessions=required_warmup_sessions,
    )
    return caller.evaluate(
        contract_path=contract_path,
        decision_at=decision_at,
        as_of_date=as_of_date,
        new_cohort_symbols=new_cohort_symbols,
        legacy_parent_reference=legacy_parent_reference,
        successor_sessions=successor_sessions,
        allow_online_probe=allow_online_probe,
    )


__all__ = [
    "LegacyParentReference",
    "SecurityLifecycleCallerError",
    "SecurityLifecycleIndustryCaller",
    "SecurityLifecycleIndustryResult",
    "run_security_lifecycle_industry_caller",
]
