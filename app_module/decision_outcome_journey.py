"""把推薦決策、Evidence、Journal 與 Portfolio ledger 串成唯讀旅程。

這個模組是跨來源的 read model，不是新的資料庫或新的事件來源。它只接受
既有 repository／檔案 adapter 回傳的資料，使用來源已保存的 identity key
做精確連結；股票代號、日期或排序相同都不能單獨形成連結。

旅程的根是不可變的 recommendation result。Evidence event 只能以
``source_id``、``source_snapshot_id`` 或 importer 已明示保存的
``metadata.source_result_id`` 連入；outcome 只能以
``(event_id, window_days, return_basis)`` 連入。Journal 與 ledger 也必須帶
result identity 或已連入事件的明示 foreign key。缺少、重複或互相矛盾的 key
一律保留原始 payload 並標成 unknown／unlinked／conflict，不補造 identity。

本模組不執行推薦、outcome 計算、持倉投影、交易、排程或任何寫入。Evidence
的 close-to-close return 仍是研究 outcome；``is_execution_pnl`` 只保存來源
宣告，不能把它轉成個人實際損益。推薦結果、使用者 portfolio trade、paper
fill 與精確 event ledger 在 DTO 中保持不同集合。
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Protocol, Sequence, cast

from app_module.evidence_event_dtos import EvidenceEvent, EvidenceOutcome
from app_module.evidence_event_repository import EvidenceEventRepository
from app_module.dtos.decision_continuity_dtos import (
    IDENTITY_STATUS_CONFLICT,
    DecisionIdentity,
)
from data_module.portfolio_ledger_repository import (
    PortfolioLedgerEvent,
    PortfolioLedgerRepository,
)


JOURNEY_SCHEMA_VERSION = "decision-outcome-journey.v1"
OUTCOME_WINDOWS: tuple[int, ...] = (5, 10, 20, 60)
DEFAULT_MAX_EVIDENCE_EVENTS = 5_000
_MISSING_TIME = "9999-12-31T23:59:59.999999"
_TIMELINE_ORDER = {
    "recommendation_result": 0,
    "evidence_event": 1,
    "evidence_outcome": 2,
    "journal_entry": 3,
    "portfolio_ledger_event": 4,
    "portfolio_trade": 5,
}

FrozenPayload = Mapping[str, Any]


class JourneyLinkStatus(str, Enum):
    """單一來源列與旅程根的連結狀態。"""

    LINKED = "linked"
    UNKNOWN = "unknown"
    UNLINKED = "unlinked"
    CONFLICT = "conflict"
    AMBIGUOUS = "ambiguous"
    DEFERRED = "deferred"


class JourneyStatus(str, Enum):
    """整條旅程的 fail-closed 摘要狀態。"""

    LINKED = "linked"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class JourneyDiagnostic:
    """不改寫來源的可機讀診斷。"""

    code: str
    detail: str
    entity_type: str = ""
    entity_id: str = ""
    severity: str = "warning"

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("diagnostic code is required")
        if self.severity not in {"info", "warning", "error"}:
            raise ValueError("unsupported diagnostic severity")

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "detail": self.detail,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class RecommendationSourceIdentity:
    """推薦 result 本身保存的來源與 snapshot identity。

    ``source_snapshot_id``／``source_snapshot_hash`` 不會在缺資料時由
    result_id 或 universe snapshot 推導；若 importer 只在 Evidence 上保存
    result snapshot，則該事實會留在 Evidence DTO，而不污染推薦根 identity。
    """

    result_id: str
    decision_date: str | None = None
    source_provider_id: str | None = None
    source_snapshot_id: str | None = None
    source_snapshot_hash: str | None = None
    strategy_version_id: str | None = None
    strategy_config_id: str | None = None
    strategy_config_hash: str | None = None
    universe_policy_id: str | None = None
    universe_policy_hash: str | None = None
    universe_snapshot_id: str | None = None
    universe_snapshot_hash: str | None = None
    return_basis: str | None = None

    @property
    def result_key(self) -> tuple[str]:
        """推薦結果的唯一根 key。"""

        return (self.result_id,)

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "decision_date": self.decision_date,
            "source_provider_id": self.source_provider_id,
            "source_snapshot_id": self.source_snapshot_id,
            "source_snapshot_hash": self.source_snapshot_hash,
            "strategy_version_id": self.strategy_version_id,
            "strategy_config_id": self.strategy_config_id,
            "strategy_config_hash": self.strategy_config_hash,
            "universe_policy_id": self.universe_policy_id,
            "universe_policy_hash": self.universe_policy_hash,
            "universe_snapshot_id": self.universe_snapshot_id,
            "universe_snapshot_hash": self.universe_snapshot_hash,
            "return_basis": self.return_basis,
        }


@dataclass(frozen=True)
class RecommendationCandidateRecord:
    """推薦 result 中的一個候選；candidate key 是 ``(result_id, stock)``。"""

    candidate_key: tuple[str, str] | None
    stock_code: str | None
    stock_name: str | None
    recommendation_rank: int | None
    link_status: JourneyLinkStatus = JourneyLinkStatus.LINKED
    original_payload: FrozenPayload = field(default_factory=lambda: MappingProxyType({}))

    @property
    def candidate_id(self) -> str | None:
        if self.candidate_key is None:
            return None
        return ":".join(self.candidate_key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_key": None if self.candidate_key is None else list(self.candidate_key),
            "candidate_id": self.candidate_id,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "recommendation_rank": self.recommendation_rank,
            "link_status": self.link_status.value,
            "original_payload": _thaw(self.original_payload),
        }


@dataclass(frozen=True)
class RecommendationResultRecord:
    """凍結後的推薦 result 根。"""

    result_id: str
    decision_date: str | None
    created_at: str | None
    source_identity: RecommendationSourceIdentity
    candidates: tuple[RecommendationCandidateRecord, ...]
    link_status: JourneyLinkStatus = JourneyLinkStatus.LINKED
    result_path: str | None = None
    original_payload: FrozenPayload = field(default_factory=lambda: MappingProxyType({}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "decision_date": self.decision_date,
            "created_at": self.created_at,
            "source_identity": self.source_identity.to_dict(),
            "candidates": [item.to_dict() for item in self.candidates],
            "link_status": self.link_status.value,
            "result_path": self.result_path,
            "original_payload": _thaw(self.original_payload),
        }


@dataclass(frozen=True)
class EvidenceOutcomeRecord:
    """Evidence outcome 的研究 read model，不是 execution PnL。"""

    outcome_id: str
    event_id: str
    window_days: int | None
    return_basis: str
    outcome_status: str
    data_quality: str
    forward_return_bp: int | None
    event_price_date: str | None
    outcome_price_date: str | None
    data_as_of_date: str | None
    calculated_at: str | None
    is_execution_pnl: bool | None
    link_status: JourneyLinkStatus
    original_payload: FrozenPayload = field(default_factory=lambda: MappingProxyType({}))

    @property
    def performance_semantics(self) -> str:
        if self.is_execution_pnl is False:
            return "research_forward_return"
        if self.is_execution_pnl is True:
            return "source_declared_execution_pnl_not_personal_fill"
        return "unclassified_return"

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome_id": self.outcome_id,
            "event_id": self.event_id,
            "outcome_key": [self.event_id, self.window_days, self.return_basis],
            "window_days": self.window_days,
            "return_basis": self.return_basis,
            "outcome_status": self.outcome_status,
            "data_quality": self.data_quality,
            "forward_return_bp": self.forward_return_bp,
            "event_price_date": self.event_price_date,
            "outcome_price_date": self.outcome_price_date,
            "data_as_of_date": self.data_as_of_date,
            "calculated_at": self.calculated_at,
            "is_execution_pnl": self.is_execution_pnl,
            "performance_semantics": self.performance_semantics,
            "link_status": self.link_status.value,
            "original_payload": _thaw(self.original_payload),
        }


@dataclass(frozen=True)
class EvidenceEventRecord:
    """Evidence event 與其明示來源 key。"""

    event_id: str
    event_hash: str
    event_type: str
    event_family: str
    source_type: str
    source_id: str | None
    source_snapshot_id: str | None
    symbol: str | None
    decision_date: str | None
    event_date: str | None
    as_of_date: str | None
    available_date: str | None
    source_version: str | None
    created_at: str | None
    candidate_key: tuple[str, str] | None
    link_status: JourneyLinkStatus
    outcomes: tuple[EvidenceOutcomeRecord, ...] = ()
    original_payload: FrozenPayload = field(default_factory=lambda: MappingProxyType({}))

    @property
    def event_key(self) -> tuple[str]:
        return (self.event_id,)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_key": [self.event_id],
            "event_hash": self.event_hash,
            "event_type": self.event_type,
            "event_family": self.event_family,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "source_snapshot_id": self.source_snapshot_id,
            "symbol": self.symbol,
            "decision_date": self.decision_date,
            "event_date": self.event_date,
            "as_of_date": self.as_of_date,
            "available_date": self.available_date,
            "source_version": self.source_version,
            "created_at": self.created_at,
            "candidate_key": None if self.candidate_key is None else list(self.candidate_key),
            "link_status": self.link_status.value,
            "outcomes": [item.to_dict() for item in self.outcomes],
            "original_payload": _thaw(self.original_payload),
        }


@dataclass(frozen=True)
class OutcomeMaturityRecord:
    """每個推薦 candidate 的固定 maturity window 狀態。"""

    candidate_key: tuple[str, str] | None
    event_id: str | None
    window_days: int
    status: JourneyLinkStatus
    outcome_id: str | None = None
    outcome_status: str | None = None
    reason: str = ""

    @property
    def maturity_key(self) -> tuple[str | None, int]:
        return (self.event_id, self.window_days)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_key": None if self.candidate_key is None else list(self.candidate_key),
            "event_id": self.event_id,
            "window_days": self.window_days,
            "status": self.status.value,
            "outcome_id": self.outcome_id,
            "outcome_status": self.outcome_status,
            "reason": self.reason,
        }


def project_outcome_maturity(
    rows: Sequence[OutcomeMaturityRecord],
) -> tuple[OutcomeMaturityRecord, ...]:
    """穩定投影既有 maturity rows；不由 link status 推導成熟判定。"""

    return tuple(
        sorted(
            rows,
            key=lambda item: (
                ""
                if item.candidate_key is None
                else ":".join(item.candidate_key),
                item.window_days,
            ),
        )
    )


@dataclass(frozen=True)
class JournalEntryRecord:
    """只以 Journal 明示 key 連入的使用者筆記。"""

    journal_id: str
    linked_type: str | None
    linked_id: str | None
    thesis_id: str | None
    source_type: str | None
    source_id: str | None
    source_snapshot_hash: str | None
    created_at: str | None
    updated_at: str | None
    relationship_type: str | None
    relationship_target_id: str | None
    link_status: JourneyLinkStatus
    original_payload: FrozenPayload = field(default_factory=lambda: MappingProxyType({}))
    # 舊 Journal row 沒有這個欄位；保留 ``None`` 作為明示標記，讓 typed
    # ``unknown``／``conflict`` identity 不會落回 legacy result 層級規則。
    decision_identity: DecisionIdentity | None = None

    @property
    def journal_key(self) -> tuple[str]:
        return (self.journal_id,)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "journal_id": self.journal_id,
            "journal_key": [self.journal_id],
            "linked_type": self.linked_type,
            "linked_id": self.linked_id,
            "thesis_id": self.thesis_id,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "source_snapshot_hash": self.source_snapshot_hash,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "relationship_type": self.relationship_type,
            "relationship_target_id": self.relationship_target_id,
            "link_status": self.link_status.value,
            "original_payload": _thaw(self.original_payload),
        }
        if self.decision_identity is not None:
            result["decision_identity"] = self.decision_identity.to_dict()
        return result


@dataclass(frozen=True)
class PortfolioLedgerRecord:
    """精確 Portfolio event ledger 的分離 read model。"""

    record_id: str
    event_type: str
    source_namespace: str | None
    occurred_at: str | None
    created_at: str | None
    stock_code: str | None
    side: str | None
    quantity: int | None
    price: Decimal | None
    fees: Decimal | None
    taxes: Decimal | None
    source_id: str | None
    source_snapshot_hash: str | None
    thesis_id: str | None
    reverses_event_id: str | None
    reason: str | None
    research_only: bool | None
    broker_fill_proven: bool
    execution_semantics: str
    link_status: JourneyLinkStatus
    original_payload: FrozenPayload = field(default_factory=lambda: MappingProxyType({}))

    @property
    def ledger_key(self) -> tuple[str]:
        return (self.record_id,)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "ledger_key": [self.record_id],
            "event_type": self.event_type,
            "source_namespace": self.source_namespace,
            "occurred_at": self.occurred_at,
            "created_at": self.created_at,
            "stock_code": self.stock_code,
            "side": self.side,
            "quantity": self.quantity,
            "price": None if self.price is None else str(self.price),
            "fees": None if self.fees is None else str(self.fees),
            "taxes": None if self.taxes is None else str(self.taxes),
            "source_id": self.source_id,
            "source_snapshot_hash": self.source_snapshot_hash,
            "thesis_id": self.thesis_id,
            "reverses_event_id": self.reverses_event_id,
            "reason": self.reason,
            "research_only": self.research_only,
            "broker_fill_proven": self.broker_fill_proven,
            "execution_semantics": self.execution_semantics,
            "link_status": self.link_status.value,
            "original_payload": _thaw(self.original_payload),
        }


@dataclass(frozen=True)
class PortfolioTradeRecord:
    """舊 Portfolio JSONL 的使用者紀錄，與 recommendation／precise ledger 分開。"""

    record_id: str
    portfolio_id: str | None
    trade_date: str | None
    stock_code: str | None
    side: str | None
    quantity: int | None
    price: Decimal | None
    fees: Decimal | None
    taxes: Decimal | None
    source_id: str | None
    source_snapshot_hash: str | None
    created_at: str | None
    link_status: JourneyLinkStatus
    broker_fill_proven: bool
    execution_semantics: str = "user_recorded_trade_broker_fill_unproven"
    original_payload: FrozenPayload = field(default_factory=lambda: MappingProxyType({}))

    @property
    def trade_key(self) -> tuple[str]:
        return (self.record_id,)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "trade_key": [self.record_id],
            "portfolio_id": self.portfolio_id,
            "trade_date": self.trade_date,
            "stock_code": self.stock_code,
            "side": self.side,
            "quantity": self.quantity,
            "price": None if self.price is None else str(self.price),
            "fees": None if self.fees is None else str(self.fees),
            "taxes": None if self.taxes is None else str(self.taxes),
            "source_id": self.source_id,
            "source_snapshot_hash": self.source_snapshot_hash,
            "created_at": self.created_at,
            "link_status": self.link_status.value,
            "broker_fill_proven": self.broker_fill_proven,
            "execution_semantics": self.execution_semantics,
            "original_payload": _thaw(self.original_payload),
        }


@dataclass(frozen=True)
class JourneyTimelineItem:
    """跨來源時間線列，明示 source／available／query boundary。"""

    item_type: str
    item_id: str
    source_at: str | None
    occurred_at: str | None
    available_at: str | None
    query_boundary: str | None
    link_status: JourneyLinkStatus
    source_key: tuple[str, ...]
    original_payload: FrozenPayload = field(default_factory=lambda: MappingProxyType({}))

    @property
    def sort_key(self) -> tuple[str, int, str, str]:
        return (
            _sort_time(self.occurred_at or self.source_at),
            _TIMELINE_ORDER.get(self.item_type, 99),
            self.item_id,
            self.available_at or _MISSING_TIME,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_type": self.item_type,
            "item_id": self.item_id,
            "source_at": self.source_at,
            "occurred_at": self.occurred_at,
            "available_at": self.available_at,
            "query_boundary": self.query_boundary,
            "link_status": self.link_status.value,
            "source_key": list(self.source_key),
            "original_payload": _thaw(self.original_payload),
        }


@dataclass(frozen=True)
class JourneyCoverage:
    """各 read source 的讀取／連結計數，方便 CLI smoke 解釋缺口。"""

    evidence_read: int = 0
    evidence_linked: int = 0
    evidence_unlinked: int = 0
    evidence_unknown: int = 0
    evidence_conflict: int = 0
    journal_read: int = 0
    journal_linked: int = 0
    journal_unlinked: int = 0
    journal_unknown: int = 0
    journal_conflict: int = 0
    ledger_read: int = 0
    ledger_linked: int = 0
    ledger_unlinked: int = 0
    ledger_unknown: int = 0
    ledger_conflict: int = 0
    trade_read: int = 0
    trade_linked: int = 0
    trade_unlinked: int = 0
    trade_unknown: int = 0
    trade_conflict: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            name: int(getattr(self, name))
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True)
class DecisionOutcomeJourney:
    """Recommendation 根到後續 read sources 的唯讀、可追溯 DTO。"""

    requested_result_id: str
    status: JourneyStatus
    query_boundary: str | None
    recommendation_result: RecommendationResultRecord
    evidence_events: tuple[EvidenceEventRecord, ...] = ()
    outcomes: tuple[EvidenceOutcomeRecord, ...] = ()
    outcome_maturity: tuple[OutcomeMaturityRecord, ...] = ()
    journal_entries: tuple[JournalEntryRecord, ...] = ()
    portfolio_ledger_events: tuple[PortfolioLedgerRecord, ...] = ()
    portfolio_trades: tuple[PortfolioTradeRecord, ...] = ()
    timeline: tuple[JourneyTimelineItem, ...] = ()
    coverage: JourneyCoverage = field(default_factory=JourneyCoverage)
    diagnostics: tuple[JourneyDiagnostic, ...] = ()
    research_only: bool = True
    actual_personal_records_separate: bool = True
    investment_effectiveness_claim: bool = False
    read_only: bool = True
    writes_allowed: bool = False
    broker_execution: bool = False
    auto_rebalance_allowed: bool = False

    def __post_init__(self) -> None:
        if (
            self.research_only is not True
            or self.actual_personal_records_separate is not True
            or self.investment_effectiveness_claim is not False
            or self.read_only is not True
            or self.writes_allowed is not False
            or self.broker_execution is not False
            or self.auto_rebalance_allowed is not False
        ):
            raise ValueError("journey safety boundary must remain fail-closed")
        if self.timeline != tuple(sorted(self.timeline, key=lambda item: item.sort_key)):
            raise ValueError("journey timeline must be stably sorted")

    @property
    def recommendation_result_id(self) -> str:
        return self.recommendation_result.result_id

    @property
    def has_personal_trade_link(self) -> bool:
        return bool(self.portfolio_trades or any(
            item.source_namespace == "manual"
            for item in self.portfolio_ledger_events
        ))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": JOURNEY_SCHEMA_VERSION,
            "requested_result_id": self.requested_result_id,
            "status": self.status.value,
            "query_boundary": self.query_boundary,
            "recommendation_result": self.recommendation_result.to_dict(),
            "evidence_events": [item.to_dict() for item in self.evidence_events],
            "outcomes": [item.to_dict() for item in self.outcomes],
            "outcome_maturity": [item.to_dict() for item in self.outcome_maturity],
            "journal_entries": [item.to_dict() for item in self.journal_entries],
            "portfolio_ledger_events": [
                item.to_dict() for item in self.portfolio_ledger_events
            ],
            "portfolio_trades": [item.to_dict() for item in self.portfolio_trades],
            "timeline": [item.to_dict() for item in self.timeline],
            "coverage": self.coverage.to_dict(),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "research_only": self.research_only,
            "actual_personal_records_separate": self.actual_personal_records_separate,
            "investment_effectiveness_claim": self.investment_effectiveness_claim,
            "read_only": self.read_only,
            "writes_allowed": self.writes_allowed,
            "broker_execution": self.broker_execution,
            "auto_rebalance_allowed": self.auto_rebalance_allowed,
        }


class RecommendationReadPort(Protocol):
    """推薦 result 唯讀 port。"""

    def read_result(self, result_id: str) -> Mapping[str, Any] | None: ...


class EvidenceReadPort(Protocol):
    """Evidence event／outcome 唯讀 port。"""

    def list_events(
        self, *, decision_date: str | None = None
    ) -> Sequence[EvidenceEvent | Mapping[str, Any]]: ...

    def list_outcomes(
        self, *, event_id: str
    ) -> Sequence[EvidenceOutcome | Mapping[str, Any]]: ...


class EvidenceBatchReadPort(Protocol):
    """可選的 exact event id 批次 outcome 唯讀 port。"""

    def list_outcomes_for_event_ids(
        self,
        event_ids: Iterable[str],
    ) -> Sequence[EvidenceOutcome | Mapping[str, Any]]: ...


class JournalReadPort(Protocol):
    def list_entries(self) -> Sequence[Mapping[str, Any]]: ...


class JournalBoundaryReadPort(Protocol):
    def list_entries_as_of(self, boundary: str) -> Sequence[Mapping[str, Any]]: ...


class PortfolioLedgerReadPort(Protocol):
    def list_events(self) -> Sequence[PortfolioLedgerEvent | Mapping[str, Any]]: ...


class PortfolioTradeReadPort(Protocol):
    def list_trades(self) -> Sequence[Mapping[str, Any]]: ...


class JsonRecommendationReadAdapter:
    """只讀讀取 ``output/recommendation/runs/<result_id>.json``。"""

    def __init__(self, output_root: str | Path) -> None:
        self.output_root = Path(output_root).expanduser().resolve()

    def path_for(self, result_id: str) -> Path:
        _require_simple_id(result_id, "result_id")
        return self.output_root / "recommendation" / "runs" / f"{result_id}.json"

    def read_result(self, result_id: str) -> Mapping[str, Any] | None:
        path = self.path_for(result_id)
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError(f"recommendation result must be a JSON object: {path}")
        return cast(Mapping[str, Any], payload)

    def list_result_ids(self) -> tuple[str, ...]:
        directory = self.output_root / "recommendation" / "runs"
        if not directory.is_dir():
            return ()
        return tuple(sorted(item.stem for item in directory.glob("*.json")))


class EvidenceRepositoryReadAdapter:
    """以現有 ``EvidenceEventRepository`` 的 query-only API 讀取 evidence。

    ``decision_date`` 僅是降低讀取範圍的 query boundary，不是 identity join
    條件；service 仍會再次檢查 event 的 source key。
    """

    def __init__(
        self,
        db_path: str | Path,
        *,
        max_events: int = DEFAULT_MAX_EVIDENCE_EVENTS,
    ) -> None:
        if isinstance(max_events, bool) or max_events <= 0:
            raise ValueError("max_events must be positive")
        self.repository = EvidenceEventRepository(object(), db_path=db_path)
        self.max_events = max_events
        self.last_has_more = False
        self.last_read_count = 0

    def list_events(
        self, *, decision_date: str | None = None
    ) -> Sequence[EvidenceEvent]:
        rows = tuple(
            self.repository.list_events(
                decision_date=decision_date,
                limit=self.max_events + 1,
            )
        )
        self.last_has_more = len(rows) > self.max_events
        result = rows[: self.max_events]
        self.last_read_count = len(result)
        return result

    def list_outcomes(self, *, event_id: str) -> Sequence[EvidenceOutcome]:
        return tuple(self.repository.list_outcomes(event_id=event_id))

    def list_outcomes_for_event_ids(
        self,
        event_ids: Iterable[str],
    ) -> Sequence[EvidenceOutcome]:
        return tuple(self.repository.list_outcomes_for_event_ids(event_ids))


class JsonlJournalReadAdapter:
    """直接開啟既有 journal JSONL，不建目錄也不使用 writer。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()

    def list_entries(self) -> Sequence[Mapping[str, Any]]:
        records = _read_jsonl(self.path)
        # The backend writer may append continuity revisions/tombstones to the
        # same JSONL. Project only active journal notes here so research action
        # history cannot be mistaken for a mature outcome.
        from app_module.portfolio_store import project_journal_records

        return project_journal_records(records)

    def list_entries_as_of(self, boundary: str) -> Sequence[Mapping[str, Any]]:
        """Filter revision observation time before building the projection.

        Otherwise a later tombstone would erase an earlier note even when the
        journey is explicitly queried at an earlier boundary.
        """

        records = _read_jsonl(self.path)
        visible: list[Mapping[str, Any]] = []
        for record in records:
            if str(record.get("record_type", "")) == "decision_continuity_revision":
                if not _available_at_boundary(str(record.get("created_at", "")), boundary):
                    continue
            visible.append(record)
        from app_module.portfolio_store import project_journal_records

        return project_journal_records(visible)


class JsonlPortfolioTradeReadAdapter:
    """直接讀取 legacy Portfolio ``trades.jsonl``。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()

    def list_trades(self) -> Sequence[Mapping[str, Any]]:
        return _read_jsonl(self.path)


class PortfolioLedgerRepositoryReadAdapter:
    """以 ``PortfolioLedgerRepository.open_read_only`` 讀精確 event ledger。"""

    def __init__(self, path: str | Path) -> None:
        self.repository = PortfolioLedgerRepository.open_read_only(path)

    def list_events(self) -> Sequence[PortfolioLedgerEvent]:
        return self.repository.list_events()


class DecisionOutcomeJourneyService:
    """建立跨來源唯讀 journey；所有 join 都由 explicit identity 驅動。"""

    def __init__(
        self,
        *,
        recommendation_reader: RecommendationReadPort,
        evidence_reader: EvidenceReadPort | None = None,
        journal_reader: JournalReadPort | None = None,
        portfolio_ledger_reader: PortfolioLedgerReadPort | None = None,
        portfolio_trade_reader: PortfolioTradeReadPort | None = None,
    ) -> None:
        self.recommendation_reader = recommendation_reader
        self.evidence_reader = evidence_reader
        self.journal_reader = journal_reader
        self.portfolio_ledger_reader = portfolio_ledger_reader
        self.portfolio_trade_reader = portfolio_trade_reader

    @classmethod
    def from_paths(
        cls,
        *,
        output_root: str | Path,
        evidence_db_path: str | Path | None = None,
        journal_path: str | Path | None = None,
        portfolio_ledger_path: str | Path | None = None,
        portfolio_trades_path: str | Path | None = None,
        max_evidence_events: int = DEFAULT_MAX_EVIDENCE_EVENTS,
    ) -> "DecisionOutcomeJourneyService":
        """從正式 output／DB 路徑組合唯讀 adapters。

        省略的檔案不會被建立；呼叫端可先以 ``Path.is_file`` 決定是否傳入
        ledger，避免在沒有舊資料時誤觸 writer constructor。
        """

        output = Path(output_root).expanduser().resolve()
        return cls(
            recommendation_reader=JsonRecommendationReadAdapter(output),
            evidence_reader=(
                None
                if evidence_db_path is None
                else EvidenceRepositoryReadAdapter(
                    evidence_db_path,
                    max_events=max_evidence_events,
                )
            ),
            journal_reader=(
                JsonlJournalReadAdapter(journal_path)
                if journal_path is not None
                else None
            ),
            portfolio_ledger_reader=(
                PortfolioLedgerRepositoryReadAdapter(portfolio_ledger_path)
                if portfolio_ledger_path is not None
                else None
            ),
            portfolio_trade_reader=(
                JsonlPortfolioTradeReadAdapter(portfolio_trades_path)
                if portfolio_trades_path is not None
                else None
            ),
        )

    @classmethod
    def from_config(
        cls,
        config: Any,
        *,
        portfolio_ledger_path: str | Path | None = None,
        portfolio_trades_path: str | Path | None = None,
        journal_path: str | Path | None = None,
        max_evidence_events: int = DEFAULT_MAX_EVIDENCE_EVENTS,
    ) -> "DecisionOutcomeJourneyService":
        """使用已存在 config；本方法不建立 config 或資料目錄。"""

        return cls.from_paths(
            output_root=Path(config.output_root),
            evidence_db_path=Path(config.db_file),
            journal_path=journal_path,
            portfolio_ledger_path=portfolio_ledger_path,
            portfolio_trades_path=portfolio_trades_path,
            max_evidence_events=max_evidence_events,
        )

    def build(
        self,
        result_id: str,
        *,
        query_boundary: str | datetime | date | None = None,
    ) -> DecisionOutcomeJourney:
        """建立一條 result-rooted journey。

        ``query_boundary`` 是讀取當下可見的時間界線。根 result 即使後續
        source 尚未 available 仍會保留；較晚的 evidence／outcome 會標成
        deferred 或在 maturity 中保留 unknown，絕不把未來資料回灌成決策值。
        """

        requested_id = _required_text(result_id, "result_id")
        boundary = _time_text(query_boundary)
        diagnostics: list[JourneyDiagnostic] = []
        if boundary is not None and _parse_temporal(boundary) is None:
            _diag(
                diagnostics,
                "query_boundary_invalid_or_timezone_unknown",
                "query boundary 必須是 ISO date 或帶 timezone 的 datetime；不猜 naive timestamp 的時區",
                "journey",
                requested_id,
                severity="error",
            )

        raw_result: Mapping[str, Any] | None = None
        try:
            raw_result = self.recommendation_reader.read_result(requested_id)
        except Exception as exc:
            _diag(
                diagnostics,
                "recommendation_read_failure",
                f"{type(exc).__name__}: {exc}",
                "recommendation_result",
                requested_id,
                severity="error",
            )

        result_path = _adapter_path(self.recommendation_reader, requested_id)
        result_record = self._build_result(
            requested_id,
            raw_result,
            result_path=result_path,
            diagnostics=diagnostics,
        )

        candidate_map = {
            item.stock_code: item
            for item in result_record.candidates
            if item.stock_code
        }

        if result_record.link_status != JourneyLinkStatus.LINKED:
            _diag(
                diagnostics,
                "journey_root_identity_not_linkable",
                "Recommendation result identity 未通過 exact payload 檢查；停止所有跨來源 join",
                "recommendation_result",
                result_record.result_id,
                severity="error",
            )
            evidence_records: list[EvidenceEventRecord] = []
            outcome_records: list[EvidenceOutcomeRecord] = []
            maturity = self._missing_maturity(
                candidate_map,
                None,
                "journey_root_identity_not_linkable",
            )
            evidence_counts = (0, 0, 0, 0, 0)
            ledger_records: list[PortfolioLedgerRecord] = []
            ledger_counts = (0, 0, 0, 0, 0)
            trade_records: list[PortfolioTradeRecord] = []
            trade_counts = (0, 0, 0, 0, 0)
            journal_records: list[JournalEntryRecord] = []
            journal_counts = (0, 0, 0, 0, 0)
        else:
            evidence_records, outcome_records, maturity, evidence_counts = self._read_evidence(
                result_record,
                candidate_map,
                boundary,
                diagnostics,
            )
            ledger_records, ledger_counts = self._read_ledger(
                result_record,
                boundary,
                diagnostics,
            )
            trade_records, trade_counts = self._read_trades(
                result_record,
                boundary,
                diagnostics,
            )
            journal_records, journal_counts = self._read_journal(
                result_record,
                ledger_records,
                boundary,
                diagnostics,
            )

        timeline = self._timeline(
            result_record,
            evidence_records,
            outcome_records,
            journal_records,
            ledger_records,
            trade_records,
            boundary,
        )
        coverage = JourneyCoverage(
            evidence_read=evidence_counts[0],
            evidence_linked=evidence_counts[1],
            evidence_unlinked=evidence_counts[2],
            evidence_unknown=evidence_counts[3],
            evidence_conflict=evidence_counts[4],
            journal_read=journal_counts[0],
            journal_linked=journal_counts[1],
            journal_unlinked=journal_counts[2],
            journal_unknown=journal_counts[3],
            journal_conflict=journal_counts[4],
            ledger_read=ledger_counts[0],
            ledger_linked=ledger_counts[1],
            ledger_unlinked=ledger_counts[2],
            ledger_unknown=ledger_counts[3],
            ledger_conflict=ledger_counts[4],
            trade_read=trade_counts[0],
            trade_linked=trade_counts[1],
            trade_unlinked=trade_counts[2],
            trade_unknown=trade_counts[3],
            trade_conflict=trade_counts[4],
        )
        status = _overall_status(
            result_record,
            evidence_records,
            maturity,
            journal_records,
            ledger_records,
            trade_records,
            diagnostics,
        )
        return DecisionOutcomeJourney(
            requested_result_id=requested_id,
            status=status,
            query_boundary=boundary,
            recommendation_result=result_record,
            evidence_events=tuple(evidence_records),
            outcomes=tuple(outcome_records),
            outcome_maturity=tuple(maturity),
            journal_entries=tuple(journal_records),
            portfolio_ledger_events=tuple(ledger_records),
            portfolio_trades=tuple(trade_records),
            timeline=timeline,
            coverage=coverage,
            diagnostics=tuple(_unique_diagnostics(diagnostics)),
        )

    def _build_result(
        self,
        requested_id: str,
        payload: Mapping[str, Any] | None,
        *,
        result_path: str | None,
        diagnostics: list[JourneyDiagnostic],
    ) -> RecommendationResultRecord:
        if payload is None:
            _diag(
                diagnostics,
                "recommendation_result_key_missing",
                "找不到 exact result_id；保留 requested key，不能建立候選或後續連結",
                "recommendation_result",
                requested_id,
                severity="error",
            )
            identity = RecommendationSourceIdentity(result_id=requested_id)
            return RecommendationResultRecord(
                result_id=requested_id,
                decision_date=None,
                created_at=None,
                source_identity=identity,
                candidates=(),
                link_status=JourneyLinkStatus.UNKNOWN,
                result_path=result_path,
            )

        raw_id = _optional_text(payload.get("result_id"))
        result_key = raw_id or requested_id
        result_status = JourneyLinkStatus.LINKED
        if raw_id is None:
            _diag(
                diagnostics,
                "recommendation_result_id_missing",
                "result payload 沒有保存 result_id；不以檔名以外的日期／股票欄位補造 key",
                "recommendation_result",
                requested_id,
            )
            result_status = JourneyLinkStatus.UNKNOWN
        elif raw_id != requested_id:
            _diag(
                diagnostics,
                "recommendation_result_id_conflict",
                f"requested={requested_id}; payload={raw_id}",
                "recommendation_result",
                requested_id,
                severity="error",
            )
            result_status = JourneyLinkStatus.CONFLICT

        config = _mapping(payload.get("config"))
        run_context = _mapping(payload.get("run_context"))
        strategy_config = _mapping(run_context.get("strategy_config"))

        decision_date_value = _consistent_identity(
            (
                ("config.decision_date", _optional_text(config.get("decision_date"))),
                ("run_context.as_of_date", _optional_text(run_context.get("as_of_date"))),
            ),
            diagnostics,
            code="recommendation_decision_date_conflict",
            entity_id=result_key,
        )
        decision_date = _date_key(decision_date_value)
        if decision_date_value is not None and decision_date is None:
            _diag(
                diagnostics,
                "recommendation_decision_date_invalid",
                f"decision_date={decision_date_value} 不是有效 ISO date",
                "recommendation_result",
                result_key,
                severity="error",
            )
        source_provider_id = _consistent_identity(
            (
                ("run_context.source_id", _optional_text(run_context.get("source_id"))),
                ("config.source_id", _optional_text(config.get("source_id"))),
                ("result.source_id", _optional_text(payload.get("source_id"))),
            ),
            diagnostics,
            code="recommendation_source_id_conflict",
            entity_id=result_key,
        )
        source_snapshot_id = _consistent_identity(
            (
                ("result.source_snapshot_id", _optional_text(payload.get("source_snapshot_id"))),
                ("run_context.source_snapshot_id", _optional_text(run_context.get("source_snapshot_id"))),
                ("config.source_snapshot_id", _optional_text(config.get("source_snapshot_id"))),
            ),
            diagnostics,
            code="recommendation_source_snapshot_id_conflict",
            entity_id=result_key,
        )
        source_snapshot_hash = _consistent_identity(
            (
                ("result.source_snapshot_hash", _optional_text(payload.get("source_snapshot_hash"))),
                ("run_context.source_snapshot_hash", _optional_text(run_context.get("source_snapshot_hash"))),
                ("config.source_snapshot_hash", _optional_text(config.get("source_snapshot_hash"))),
            ),
            diagnostics,
            code="recommendation_source_snapshot_hash_conflict",
            entity_id=result_key,
        )

        identity = RecommendationSourceIdentity(
            result_id=result_key,
            decision_date=decision_date,
            source_provider_id=source_provider_id,
            source_snapshot_id=source_snapshot_id,
            source_snapshot_hash=source_snapshot_hash,
            strategy_version_id=_consistent_identity(
                (
                    ("run_context.strategy_version_id", _optional_text(run_context.get("strategy_version_id"))),
                    ("config.strategy_version_id", _optional_text(config.get("strategy_version_id"))),
                    ("strategy_config.strategy_version_id", _optional_text(strategy_config.get("strategy_version_id"))),
                ),
                diagnostics,
                code="recommendation_strategy_version_conflict",
                entity_id=result_key,
            ),
            strategy_config_id=_consistent_identity(
                (
                    ("run_context.strategy_config_id", _optional_text(run_context.get("strategy_config_id"))),
                    ("config.strategy_config_id", _optional_text(config.get("strategy_config_id"))),
                    ("strategy_config.strategy_config_id", _optional_text(strategy_config.get("strategy_config_id"))),
                ),
                diagnostics,
                code="recommendation_strategy_config_id_conflict",
                entity_id=result_key,
            ),
            strategy_config_hash=_consistent_identity(
                (
                    ("run_context.strategy_config_hash", _optional_text(run_context.get("strategy_config_hash"))),
                    ("config.strategy_config_hash", _optional_text(config.get("strategy_config_hash"))),
                    ("strategy_config.strategy_config_hash", _optional_text(strategy_config.get("strategy_config_hash"))),
                ),
                diagnostics,
                code="recommendation_strategy_config_hash_conflict",
                entity_id=result_key,
            ),
            universe_policy_id=_consistent_identity(
                (
                    ("run_context.universe_policy_id", _optional_text(run_context.get("universe_policy_id"))),
                    ("config.universe_policy_id", _optional_text(config.get("universe_policy_id"))),
                ),
                diagnostics,
                code="recommendation_universe_policy_id_conflict",
                entity_id=result_key,
            ),
            universe_policy_hash=_consistent_identity(
                (
                    ("run_context.universe_policy_hash", _optional_text(run_context.get("universe_policy_hash"))),
                    ("config.universe_policy_hash", _optional_text(config.get("universe_policy_hash"))),
                ),
                diagnostics,
                code="recommendation_universe_policy_hash_conflict",
                entity_id=result_key,
            ),
            universe_snapshot_id=_consistent_identity(
                (
                    ("run_context.universe_snapshot_id", _optional_text(run_context.get("universe_snapshot_id"))),
                    ("config.universe_snapshot_id", _optional_text(config.get("universe_snapshot_id"))),
                ),
                diagnostics,
                code="recommendation_universe_snapshot_id_conflict",
                entity_id=result_key,
            ),
            universe_snapshot_hash=_consistent_identity(
                (
                    ("run_context.universe_snapshot_hash", _optional_text(run_context.get("universe_snapshot_hash"))),
                    ("config.universe_snapshot_hash", _optional_text(config.get("universe_snapshot_hash"))),
                ),
                diagnostics,
                code="recommendation_universe_snapshot_hash_conflict",
                entity_id=result_key,
            ),
            return_basis=_consistent_identity(
                (
                    ("run_context.return_basis", _optional_text(run_context.get("return_basis"))),
                    ("config.return_basis", _optional_text(config.get("return_basis"))),
                ),
                diagnostics,
                code="recommendation_return_basis_conflict",
                entity_id=result_key,
            ),
        )
        candidate_payloads = payload.get("recommendations")
        candidates: list[RecommendationCandidateRecord] = []
        if not isinstance(candidate_payloads, Sequence) or isinstance(candidate_payloads, (str, bytes)):
            _diag(
                diagnostics,
                "recommendation_candidates_missing",
                "recommendations 不是可讀的 candidate list；不以 screening／日期／股票補造",
                "recommendation_result",
                result_key,
            )
            candidate_payloads = ()
        for index, item in enumerate(candidate_payloads):
            if not isinstance(item, Mapping):
                _diag(
                    diagnostics,
                    "recommendation_candidate_payload_invalid",
                    f"candidate index={index} 不是 object",
                    "recommendation_candidate",
                    f"{result_key}:{index}",
                )
                continue
            candidate = self._candidate_record(
                result_key,
                cast(Mapping[str, Any], item),
                diagnostics,
                index=index,
            )
            candidates.append(candidate)
        by_code: dict[str, list[int]] = {}
        for index, candidate in enumerate(candidates):
            if candidate.stock_code:
                by_code.setdefault(candidate.stock_code, []).append(index)
        for code, indexes in by_code.items():
            if len(indexes) <= 1:
                continue
            _diag(
                diagnostics,
                "recommendation_candidate_key_ambiguous",
                f"stock_code={code}; duplicate candidate rows={len(indexes)}",
                "recommendation_candidate",
                f"{result_key}:{code}",
                severity="error",
            )
            for index in indexes:
                candidates[index] = replace(
                    candidates[index],
                    link_status=JourneyLinkStatus.AMBIGUOUS,
                )

        if any(
            item.severity == "error"
            and item.entity_type == "recommendation_result"
            and item.entity_id == result_key
            for item in diagnostics
        ):
            result_status = JourneyLinkStatus.CONFLICT

        return RecommendationResultRecord(
            result_id=result_key,
            decision_date=identity.decision_date,
            created_at=_optional_text(payload.get("created_at")),
            source_identity=identity,
            candidates=tuple(candidates),
            link_status=result_status,
            result_path=result_path,
            original_payload=_freeze(payload),
        )

    def _candidate_record(
        self,
        result_id: str,
        payload: Mapping[str, Any],
        diagnostics: list[JourneyDiagnostic],
        *,
        index: int,
    ) -> RecommendationCandidateRecord:
        stock_code = _first_text(
            payload,
            "stock_code",
            "證券代號",
            "code",
        )
        stock_name = _first_text(payload, "stock_name", "證券名稱", "name")
        rank = _optional_int(
            _first_value(payload, "recommendation_rank", "推薦排序", "rank")
        )
        if stock_code is None:
            _diag(
                diagnostics,
                "recommendation_candidate_key_missing",
                "candidate 沒有明示 stock_code；不從日期或名稱猜代號",
                "recommendation_candidate",
                f"{result_id}:{index}",
            )
            return RecommendationCandidateRecord(
                candidate_key=None,
                stock_code=None,
                stock_name=stock_name,
                recommendation_rank=rank,
                link_status=JourneyLinkStatus.UNKNOWN,
                original_payload=_freeze(payload),
            )
        return RecommendationCandidateRecord(
            candidate_key=(result_id, stock_code),
            stock_code=stock_code,
            stock_name=stock_name,
            recommendation_rank=rank,
            original_payload=_freeze(payload),
        )

    def _read_evidence(
        self,
        result: RecommendationResultRecord,
        candidates: Mapping[str, RecommendationCandidateRecord],
        boundary: str | None,
        diagnostics: list[JourneyDiagnostic],
    ) -> tuple[
        list[EvidenceEventRecord],
        list[EvidenceOutcomeRecord],
        list[OutcomeMaturityRecord],
        tuple[int, int, int, int, int],
    ]:
        if self.evidence_reader is None:
            _diag(
                diagnostics,
                "evidence_reader_not_configured",
                "沒有 evidence read port；推薦 tracking 仍保留，但後續 outcome 為 unknown",
                "evidence",
                result.result_id,
            )
            return [], [], self._missing_maturity(candidates, None, "evidence_reader_not_configured"), (0, 0, 0, 0, 0)
        try:
            source_rows = tuple(
                self.evidence_reader.list_events(
                    decision_date=result.decision_date,
                )
            )
        except Exception as exc:
            _diag(
                diagnostics,
                "evidence_read_failure",
                f"{type(exc).__name__}: {exc}",
                "evidence",
                result.result_id,
                severity="error",
            )
            return [], [], self._missing_maturity(candidates, None, "evidence_read_failure"), (0, 0, 0, 0, 0)

        evidence_read_truncated = bool(
            getattr(self.evidence_reader, "last_has_more", False)
        )
        if evidence_read_truncated:
            _diag(
                diagnostics,
                "evidence_read_truncated",
                "bounded evidence read reached max_events；未讀到的 event 不能判定為 unlinked",
                "evidence",
                result.result_id,
            )

        normalized: list[EvidenceEventRecord] = []
        for item in source_rows:
            try:
                record = _normalize_evidence_event(item, result, candidates)
            except Exception as exc:
                _diag(
                    diagnostics,
                    "evidence_event_payload_invalid",
                    f"{type(exc).__name__}: {exc}",
                    "evidence_event",
                    result.result_id,
                )
                continue
            if record.link_status == JourneyLinkStatus.UNLINKED:
                continue
            if not _available_at_boundary(record.available_date, boundary):
                if boundary is not None:
                    _diag(
                        diagnostics,
                        "evidence_not_available_at_query_boundary",
                        f"available_date={record.available_date}; query_boundary={boundary}",
                        "evidence_event",
                        record.event_id,
                    )
                    record = replace(record, link_status=JourneyLinkStatus.DEFERRED)
            normalized.append(record)
        normalized = _deduplicate_evidence(normalized, diagnostics)

        outcome_records: list[EvidenceOutcomeRecord] = []
        with_outcomes: dict[str, list[EvidenceOutcomeRecord]] = {}
        deferred_outcome_keys: set[tuple[str, int | None, str]] = set()
        batch_reader: EvidenceBatchReadPort | None = None
        batch_method = getattr(
            self.evidence_reader,
            "list_outcomes_for_event_ids",
            None,
        )
        if callable(batch_method):
            batch_reader = cast(EvidenceBatchReadPort, self.evidence_reader)
        batch_outcomes_by_event: dict[
            str, tuple[EvidenceOutcome | Mapping[str, Any], ...]
        ] = {}
        if batch_reader is not None and normalized:
            requested_event_ids = tuple(event.event_id for event in normalized)
            requested_event_id_set = set(requested_event_ids)
            try:
                batch_rows = tuple(
                    batch_reader.list_outcomes_for_event_ids(requested_event_ids)
                )
            except Exception:
                # Keep compatibility with older/custom read ports; the existing
                # per-event path retains its diagnostics and fail-closed rules.
                batch_reader = None
            else:
                grouped_batch_rows: dict[
                    str, list[EvidenceOutcome | Mapping[str, Any]]
                ] = {}
                for row in batch_rows:
                    event_id = _outcome_event_id(row)
                    if event_id in requested_event_id_set:
                        grouped_batch_rows.setdefault(event_id, []).append(row)
                batch_outcomes_by_event = {
                    event_id: tuple(rows)
                    for event_id, rows in grouped_batch_rows.items()
                }
        for event in normalized:
            if batch_reader is not None:
                raw_outcomes = batch_outcomes_by_event.get(event.event_id, ())
            else:
                try:
                    raw_outcomes = tuple(
                        self.evidence_reader.list_outcomes(event_id=event.event_id)
                    )
                except Exception as exc:
                    _diag(
                        diagnostics,
                        "evidence_outcome_read_failure",
                        f"{type(exc).__name__}: {exc}",
                        "evidence_event",
                        event.event_id,
                        severity="error",
                    )
                    raw_outcomes = ()
            event_outcomes: list[EvidenceOutcomeRecord] = []
            for raw_outcome in raw_outcomes:
                try:
                    outcome = _normalize_evidence_outcome(
                        raw_outcome,
                        event,
                        boundary,
                        diagnostics,
                    )
                except Exception as exc:
                    _diag(
                        diagnostics,
                        "evidence_outcome_payload_invalid",
                        f"{type(exc).__name__}: {exc}",
                        "evidence_outcome",
                        event.event_id,
                    )
                    continue
                if outcome.link_status == JourneyLinkStatus.DEFERRED:
                    # Later outcome remains visible in maturity as deferred but
                    # does not become a current outcome value.
                    deferred_outcome_keys.add(
                        (outcome.event_id, outcome.window_days, outcome.return_basis)
                    )
                    _diag(
                        diagnostics,
                        "outcome_not_available_at_query_boundary",
                        f"outcome_id={outcome.outcome_id}; query_boundary={boundary}",
                        "evidence_outcome",
                        outcome.outcome_id,
                    )
                    continue
                event_outcomes.append(outcome)
                outcome_records.append(outcome)
            event_outcomes = _deduplicate_outcomes(event_outcomes, diagnostics)
            with_outcomes[event.event_id] = event_outcomes

        normalized = [
            replace(event, outcomes=tuple(with_outcomes.get(event.event_id, ())))
            for event in normalized
        ]
        outcome_records = _deduplicate_outcomes(outcome_records, diagnostics)
        maturity = self._build_maturity(
            result,
            candidates,
            normalized,
            outcome_records,
            boundary,
            deferred_outcome_keys,
            diagnostics,
        )
        counts = _coverage_counts(source_rows, normalized)
        if not normalized and not evidence_read_truncated:
            _diag(
                diagnostics,
                "evidence_link_missing",
                f"沒有 event 以 exact result identity={result.result_id} 連入",
                "evidence",
                result.result_id,
            )
        elif evidence_read_truncated and not normalized:
            _diag(
                diagnostics,
                "evidence_link_unknown_due_to_truncated_read",
                f"bounded read 未涵蓋 exact result identity={result.result_id}；不能宣稱無關聯",
                "evidence",
                result.result_id,
            )
        return normalized, outcome_records, maturity, counts

    def _missing_maturity(
        self,
        candidates: Mapping[str, RecommendationCandidateRecord],
        event_id: str | None,
        reason: str,
    ) -> list[OutcomeMaturityRecord]:
        return [
            OutcomeMaturityRecord(
                candidate_key=item.candidate_key,
                event_id=event_id,
                window_days=window,
                status=JourneyLinkStatus.UNKNOWN,
                reason=reason,
            )
            for item in candidates.values()
            for window in OUTCOME_WINDOWS
        ]

    def _build_maturity(
        self,
        result: RecommendationResultRecord,
        candidates: Mapping[str, RecommendationCandidateRecord],
        events: Sequence[EvidenceEventRecord],
        outcomes: Sequence[EvidenceOutcomeRecord],
        boundary: str | None,
        deferred_outcome_keys: set[tuple[str, int | None, str]],
        diagnostics: list[JourneyDiagnostic],
    ) -> list[OutcomeMaturityRecord]:
        by_event_key: dict[tuple[str, int, str], list[EvidenceOutcomeRecord]] = {}
        for outcome in outcomes:
            if outcome.window_days in OUTCOME_WINDOWS:
                by_event_key.setdefault(
                    (outcome.event_id, cast(int, outcome.window_days), outcome.return_basis),
                    [],
                ).append(outcome)
        expected_return_basis = (
            result.source_identity.return_basis or "close_to_close_event_date"
        )
        recommendation_events: dict[str, list[EvidenceEventRecord]] = {}
        for event in events:
            if event.event_type != "recommendation_included":
                continue
            if event.symbol:
                recommendation_events.setdefault(event.symbol, []).append(event)
        records: list[OutcomeMaturityRecord] = []
        for stock_code, candidate in candidates.items():
            candidate_events = recommendation_events.get(stock_code, [])
            if len(candidate_events) > 1:
                _diag(
                    diagnostics,
                    "evidence_event_key_ambiguous",
                    f"candidate={stock_code}; recommendation_included events={len(candidate_events)}",
                    "recommendation_candidate",
                    f"{result.result_id}:{stock_code}",
                    severity="error",
                )
            candidate_event: EvidenceEventRecord | None = (
                candidate_events[0] if len(candidate_events) == 1 else None
            )
            for window in OUTCOME_WINDOWS:
                if candidate_event is None:
                    records.append(
                        OutcomeMaturityRecord(
                            candidate_key=candidate.candidate_key,
                            event_id=None,
                            window_days=window,
                            status=JourneyLinkStatus.AMBIGUOUS
                            if len(candidate_events) > 1
                            else JourneyLinkStatus.UNKNOWN,
                            reason=(
                                "evidence_event_key_ambiguous"
                                if len(candidate_events) > 1
                                else "evidence_event_key_missing"
                            ),
                        )
                    )
                    continue
                key_outcomes = by_event_key.get(
                    (candidate_event.event_id, window, expected_return_basis),
                    [],
                )
                if len(key_outcomes) > 1:
                    records.append(
                        OutcomeMaturityRecord(
                            candidate_key=candidate.candidate_key,
                            event_id=candidate_event.event_id,
                            window_days=window,
                            status=JourneyLinkStatus.CONFLICT,
                            reason="conflicting_duplicate_outcome",
                        )
                    )
                    continue
                if not key_outcomes:
                    same_window = [
                        item
                        for item in outcomes
                        if item.event_id == candidate_event.event_id
                        and item.window_days == window
                    ]
                    deferred = any(
                        key[0] == candidate_event.event_id
                        and key[1] == window
                        for key in deferred_outcome_keys
                    )
                    records.append(
                        OutcomeMaturityRecord(
                            candidate_key=candidate.candidate_key,
                            event_id=candidate_event.event_id,
                            window_days=window,
                            status=JourneyLinkStatus.DEFERRED
                            if deferred
                            else JourneyLinkStatus.UNKNOWN,
                            reason=(
                                "outcome_not_available_at_query_boundary"
                                if deferred
                                else (
                                    "outcome_return_basis_mismatch"
                                    if same_window
                                    else "outcome_key_missing"
                                )
                            ),
                        )
                    )
                    if not deferred and same_window:
                        _diag(
                            diagnostics,
                            "outcome_return_basis_mismatch",
                            f"event_id={candidate_event.event_id}; window_days={window}; expected={expected_return_basis}",
                            "evidence_outcome",
                            f"{candidate_event.event_id}:{window}",
                        )
                    elif not deferred:
                        _diag(
                            diagnostics,
                            "outcome_key_missing",
                            f"event_id={candidate_event.event_id}; window_days={window}",
                            "evidence_outcome",
                            f"{candidate_event.event_id}:{window}",
                        )
                    continue
                outcome = key_outcomes[0]
                records.append(
                    OutcomeMaturityRecord(
                        candidate_key=candidate.candidate_key,
                        event_id=candidate_event.event_id,
                        window_days=window,
                        status=outcome.link_status,
                        outcome_id=outcome.outcome_id,
                        outcome_status=outcome.outcome_status,
                        reason=(
                            "outcome_available_at_query_boundary"
                            if boundary is None
                            else "outcome_visible_at_query_boundary"
                        ),
                    )
                )
        return records

    def _read_ledger(
        self,
        result: RecommendationResultRecord,
        boundary: str | None,
        diagnostics: list[JourneyDiagnostic],
    ) -> tuple[list[PortfolioLedgerRecord], tuple[int, int, int, int, int]]:
        if self.portfolio_ledger_reader is None:
            return [], (0, 0, 0, 0, 0)
        try:
            raw_rows = tuple(self.portfolio_ledger_reader.list_events())
        except Exception as exc:
            _diag(
                diagnostics,
                "portfolio_ledger_read_failure",
                f"{type(exc).__name__}: {exc}",
                "portfolio_ledger",
                result.result_id,
                severity="error",
            )
            return [], (0, 0, 0, 0, 0)
        records: list[PortfolioLedgerRecord] = []
        for item in raw_rows:
            try:
                record = _normalize_ledger_event(item, result, diagnostics)
            except Exception as exc:
                _diag(
                    diagnostics,
                    "portfolio_ledger_payload_invalid",
                    f"{type(exc).__name__}: {exc}",
                    "portfolio_ledger",
                    result.result_id,
                )
                continue
            if not _available_at_boundary(record.occurred_at, boundary):
                if boundary is not None:
                    _diag(
                        diagnostics,
                        "portfolio_ledger_not_available_at_query_boundary",
                        f"occurred_at={record.occurred_at}; query_boundary={boundary}",
                        "portfolio_ledger",
                        record.record_id,
                    )
                    record = replace(record, link_status=JourneyLinkStatus.DEFERRED)
            records.append(record)
        records = _deduplicate_ledger(records, diagnostics)
        direct_ids = {
            item.record_id
            for item in records
            if item.link_status == JourneyLinkStatus.LINKED
            and item.event_type != "compensation"
        }
        adjusted: list[PortfolioLedgerRecord] = []
        for record in records:
            if (
                record.event_type == "compensation"
                and record.reverses_event_id in direct_ids
                and record.link_status == JourneyLinkStatus.UNLINKED
            ):
                adjusted.append(
                    replace(record, link_status=JourneyLinkStatus.LINKED)
                )
                _diag(
                    diagnostics,
                    "portfolio_ledger_compensation_linked_by_reversal",
                    f"reverses_event_id={record.reverses_event_id}",
                    "portfolio_ledger",
                    record.record_id,
                )
            else:
                if record.link_status != JourneyLinkStatus.UNLINKED:
                    adjusted.append(record)
        records = adjusted
        if raw_rows and not records:
            _diag(
                diagnostics,
                "portfolio_ledger_link_missing",
                f"沒有 event 以 exact result identity={result.result_id} 連入",
                "portfolio_ledger",
                result.result_id,
            )
        return records, _coverage_counts(raw_rows, records)

    def _read_trades(
        self,
        result: RecommendationResultRecord,
        boundary: str | None,
        diagnostics: list[JourneyDiagnostic],
    ) -> tuple[list[PortfolioTradeRecord], tuple[int, int, int, int, int]]:
        if self.portfolio_trade_reader is None:
            return [], (0, 0, 0, 0, 0)
        try:
            raw_rows = tuple(self.portfolio_trade_reader.list_trades())
        except Exception as exc:
            _diag(
                diagnostics,
                "portfolio_trade_read_failure",
                f"{type(exc).__name__}: {exc}",
                "portfolio_trades",
                result.result_id,
                severity="error",
            )
            return [], (0, 0, 0, 0, 0)
        records: list[PortfolioTradeRecord] = []
        for item in raw_rows:
            try:
                record = _normalize_portfolio_trade(item, result, diagnostics)
            except Exception as exc:
                _diag(
                    diagnostics,
                    "portfolio_trade_payload_invalid",
                    f"{type(exc).__name__}: {exc}",
                    "portfolio_trades",
                    result.result_id,
                )
                continue
            if not _available_at_boundary(record.trade_date, boundary):
                if boundary is not None:
                    record = replace(record, link_status=JourneyLinkStatus.DEFERRED)
            if record.link_status != JourneyLinkStatus.UNLINKED:
                records.append(record)
        records = _deduplicate_trades(records, diagnostics)
        if raw_rows and not records:
            _diag(
                diagnostics,
                "portfolio_trade_link_missing",
                f"既有 user trade 沒有 exact result source key={result.result_id}；不阻擋 recommendation tracking",
                "portfolio_trades",
                result.result_id,
            )
        return records, _coverage_counts(raw_rows, records)

    def _read_journal(
        self,
        result: RecommendationResultRecord,
        ledger_records: Sequence[PortfolioLedgerRecord],
        boundary: str | None,
        diagnostics: list[JourneyDiagnostic],
    ) -> tuple[list[JournalEntryRecord], tuple[int, int, int, int, int]]:
        if self.journal_reader is None:
            return [], (0, 0, 0, 0, 0)
        try:
            boundary_reader = getattr(self.journal_reader, "list_entries_as_of", None)
            if boundary is not None and callable(boundary_reader):
                raw_rows = tuple(boundary_reader(boundary))
            else:
                raw_rows = tuple(self.journal_reader.list_entries())
        except Exception as exc:
            _diag(
                diagnostics,
                "journal_read_failure",
                f"{type(exc).__name__}: {exc}",
                "journal",
                result.result_id,
                severity="error",
            )
            return [], (0, 0, 0, 0, 0)
        ledger_ids = {item.record_id for item in ledger_records}
        records: list[JournalEntryRecord] = []
        for item in raw_rows:
            try:
                record = _normalize_journal_entry(item, result, ledger_ids)
            except Exception as exc:
                _diag(
                    diagnostics,
                    "journal_payload_invalid",
                    f"{type(exc).__name__}: {exc}",
                    "journal",
                    result.result_id,
                )
                continue
            if not _available_at_boundary(record.created_at or record.updated_at, boundary):
                if boundary is not None:
                    record = replace(record, link_status=JourneyLinkStatus.DEFERRED)
            if record.link_status != JourneyLinkStatus.UNLINKED:
                records.append(record)
        records = _deduplicate_journals(records, diagnostics)
        if raw_rows and not records:
            _diag(
                diagnostics,
                "journal_link_missing",
                f"既有 journal 沒有 exact result／ledger key={result.result_id}",
                "journal",
                result.result_id,
            )
        return records, _coverage_counts(raw_rows, records)

    def _timeline(
        self,
        result: RecommendationResultRecord,
        events: Sequence[EvidenceEventRecord],
        outcomes: Sequence[EvidenceOutcomeRecord],
        journals: Sequence[JournalEntryRecord],
        ledgers: Sequence[PortfolioLedgerRecord],
        trades: Sequence[PortfolioTradeRecord],
        boundary: str | None,
    ) -> tuple[JourneyTimelineItem, ...]:
        items: list[JourneyTimelineItem] = [
            JourneyTimelineItem(
                item_type="recommendation_result",
                item_id=result.result_id,
                source_at=result.created_at,
                occurred_at=result.decision_date,
                available_at=result.created_at,
                query_boundary=boundary,
                link_status=result.link_status,
                source_key=(result.result_id,),
                original_payload=result.original_payload,
            )
        ]
        items.extend(
            JourneyTimelineItem(
                item_type="evidence_event",
                item_id=event.event_id,
                source_at=event.created_at,
                occurred_at=event.event_date or event.decision_date,
                available_at=event.available_date,
                query_boundary=boundary,
                link_status=event.link_status,
                source_key=tuple(
                    value
                    for value in (event.source_id, event.source_snapshot_id)
                    if value
                ),
                original_payload=event.original_payload,
            )
            for event in events
        )
        items.extend(
            JourneyTimelineItem(
                item_type="evidence_outcome",
                item_id=outcome.outcome_id,
                source_at=outcome.calculated_at,
                occurred_at=outcome.outcome_price_date or outcome.data_as_of_date,
                available_at=outcome.calculated_at,
                query_boundary=boundary,
                link_status=outcome.link_status,
                source_key=(outcome.event_id, str(outcome.window_days or ""), outcome.return_basis),
                original_payload=outcome.original_payload,
            )
            for outcome in outcomes
        )
        items.extend(
            JourneyTimelineItem(
                item_type="journal_entry",
                item_id=entry.journal_id,
                source_at=entry.created_at,
                occurred_at=entry.created_at,
                available_at=entry.updated_at or entry.created_at,
                query_boundary=boundary,
                link_status=entry.link_status,
                source_key=tuple(
                    value for value in (entry.linked_id, entry.source_id, entry.thesis_id) if value
                ),
                original_payload=entry.original_payload,
            )
            for entry in journals
        )
        items.extend(
            JourneyTimelineItem(
                item_type="portfolio_ledger_event",
                item_id=ledger.record_id,
                source_at=ledger.created_at,
                occurred_at=ledger.occurred_at,
                available_at=ledger.occurred_at,
                query_boundary=boundary,
                link_status=ledger.link_status,
                source_key=tuple(
                    value
                    for value in (
                        ledger.source_id,
                        ledger.source_snapshot_hash,
                        ledger.thesis_id,
                        ledger.reverses_event_id,
                    )
                    if value
                ),
                original_payload=ledger.original_payload,
            )
            for ledger in ledgers
        )
        items.extend(
            JourneyTimelineItem(
                item_type="portfolio_trade",
                item_id=trade.record_id,
                source_at=trade.created_at,
                occurred_at=trade.trade_date,
                available_at=trade.created_at or trade.trade_date,
                query_boundary=boundary,
                link_status=trade.link_status,
                source_key=tuple(
                    value for value in (trade.source_id, trade.source_snapshot_hash) if value
                ),
                original_payload=trade.original_payload,
            )
            for trade in trades
        )
        return tuple(sorted(items, key=lambda item: item.sort_key))


def _normalize_evidence_event(
    item: EvidenceEvent | Mapping[str, Any],
    result: RecommendationResultRecord,
    candidates: Mapping[str, RecommendationCandidateRecord],
) -> EvidenceEventRecord:
    payload = _object_payload(item, "evidence_event")
    metadata = _mapping(_object_value(item, "metadata", payload.get("metadata")))
    source_id = _optional_text(_object_value(item, "source_id", payload.get("source_id")))
    source_snapshot_id = _optional_text(
        _object_value(item, "source_snapshot_id", payload.get("source_snapshot_id"))
    )
    metadata_result_id = _optional_text(metadata.get("source_result_id"))
    link_status = _identity_link_status(
        result.result_id,
        (
            ("source_id", source_id),
            ("source_snapshot_id", source_snapshot_id),
            ("metadata.source_result_id", metadata_result_id),
        ),
        conflict_when_other=True,
    )
    symbol = _optional_text(_object_value(item, "symbol", payload.get("symbol")))
    candidate_key = None
    if symbol and symbol in candidates:
        candidate_key = (result.result_id, symbol)
    return EvidenceEventRecord(
        event_id=_required_text(
            _object_value(item, "event_id", payload.get("event_id")),
            "evidence_event.event_id",
        ),
        event_hash=_optional_text(
            _object_value(item, "event_hash", payload.get("event_hash"))
        )
        or "",
        event_type=_text(
            _object_value(item, "event_type", payload.get("event_type")),
        ),
        event_family=_text(
            _object_value(item, "event_family", payload.get("event_family")),
        ),
        source_type=_text(
            _object_value(item, "source_type", payload.get("source_type")),
        ),
        source_id=source_id,
        source_snapshot_id=source_snapshot_id,
        symbol=symbol,
        decision_date=_date_key(
            _optional_text(_object_value(item, "decision_date", payload.get("decision_date")))
        ),
        event_date=_optional_text(
            _object_value(item, "event_date", payload.get("event_date"))
        ),
        as_of_date=_date_key(
            _optional_text(_object_value(item, "as_of_date", payload.get("as_of_date")))
        ),
        available_date=_optional_text(
            _object_value(item, "available_date", payload.get("available_date"))
        ),
        source_version=_optional_text(
            _object_value(item, "source_version", payload.get("source_version"))
        ),
        created_at=_optional_text(
            _object_value(item, "created_at", payload.get("created_at"))
        ),
        candidate_key=candidate_key,
        link_status=link_status,
        original_payload=_freeze(payload),
    )


def _normalize_evidence_outcome(
    item: EvidenceOutcome | Mapping[str, Any],
    event: EvidenceEventRecord,
    boundary: str | None,
    diagnostics: list[JourneyDiagnostic],
) -> EvidenceOutcomeRecord:
    payload = _object_payload(item, "evidence_outcome")
    metadata = _mapping(_object_value(item, "metadata", payload.get("metadata")))
    outcome_id = _required_text(
        _object_value(item, "outcome_id", payload.get("outcome_id")),
        "evidence_outcome.outcome_id",
    )
    event_id = _required_text(
        _object_value(item, "event_id", payload.get("event_id")),
        "evidence_outcome.event_id",
    )
    window_days = _optional_int(
        _object_value(item, "window_days", payload.get("window_days"))
    )
    return_basis = _text(
        _object_value(item, "return_basis", payload.get("return_basis"))
    )
    if event_id != event.event_id:
        link_status = JourneyLinkStatus.CONFLICT
        _diag(
            diagnostics,
            "outcome_event_key_conflict",
            f"outcome.event_id={event_id}; parent_event_id={event.event_id}",
            "evidence_outcome",
            outcome_id,
            severity="error",
        )
    else:
        link_status = event.link_status
    calculated_at = _optional_text(
        _object_value(item, "calculated_at", payload.get("calculated_at"))
    )
    if boundary is not None and not _available_at_boundary(calculated_at, boundary):
        link_status = JourneyLinkStatus.DEFERRED
    execution_flag = metadata.get("is_execution_pnl")
    if not isinstance(execution_flag, bool):
        execution_flag = None
        _diag(
            diagnostics,
            "outcome_execution_pnl_semantics_missing",
            "metadata.is_execution_pnl 未明示；不把 forward return 當作實際損益",
            "evidence_outcome",
            outcome_id,
        )
    return EvidenceOutcomeRecord(
        outcome_id=outcome_id,
        event_id=event_id,
        window_days=window_days,
        return_basis=return_basis,
        outcome_status=_text(
            _object_value(item, "outcome_status", payload.get("outcome_status"))
        ),
        data_quality=_text(
            _object_value(item, "data_quality", payload.get("data_quality"))
        ),
        forward_return_bp=_optional_int(
            _object_value(item, "forward_return_bp", payload.get("forward_return_bp"))
        ),
        event_price_date=_date_key(
            _optional_text(_object_value(item, "event_price_date", payload.get("event_price_date")))
        ),
        outcome_price_date=_date_key(
            _optional_text(_object_value(item, "outcome_price_date", payload.get("outcome_price_date")))
        ),
        data_as_of_date=_date_key(
            _optional_text(_object_value(item, "data_as_of_date", payload.get("data_as_of_date")))
        ),
        calculated_at=calculated_at,
        is_execution_pnl=execution_flag,
        link_status=link_status,
        original_payload=_freeze(payload),
    )


def _outcome_event_id(item: EvidenceOutcome | Mapping[str, Any]) -> str | None:
    value = (
        item.get("event_id")
        if isinstance(item, Mapping)
        else getattr(item, "event_id", None)
    )
    return None if value is None else str(value)


def _normalize_journal_entry(
    payload: Mapping[str, Any],
    result: RecommendationResultRecord,
    ledger_ids: set[str],
) -> JournalEntryRecord:
    linked_type = _optional_text(payload.get("linked_type"))
    linked_id = _optional_text(payload.get("linked_id"))
    source_id = _optional_text(payload.get("source_id"))
    snapshot_hash = _optional_text(payload.get("source_snapshot_hash"))
    thesis_id = _optional_text(payload.get("thesis_id"))
    if thesis_id is None and linked_type and linked_type.lower() == "thesis":
        thesis_id = linked_id
    relationship_target_id = _first_text(
        payload,
        "revision_of",
        "revises_id",
        "reverses_event_id",
        "relationship_target_id",
    )
    relationship_type = None
    if relationship_target_id:
        relationship_type = "revision_or_reversal"
    direct = _identity_link_status(
        result.result_id,
        (
            ("linked_id", linked_id),
            ("source_id", source_id),
            ("source_snapshot_hash", snapshot_hash),
        ),
        expected_snapshot_hash=result.source_identity.source_snapshot_hash,
        conflict_when_other=True,
    )
    if direct == JourneyLinkStatus.UNLINKED and linked_id in ledger_ids:
        direct = JourneyLinkStatus.LINKED
    if linked_type and linked_type.lower() == "thesis" and linked_id == result.result_id:
        direct = JourneyLinkStatus.CONFLICT
    typed_decision_identity: DecisionIdentity | None = None
    # 只要 identity key 出現就視為 typed metadata；即使值是 null、字串或
    # list，也必須明示 unknown／conflict，不能把 malformed row 當 legacy。
    has_typed_identity = (
        "decision_identity" in payload
        or "identity_status" in payload
        or "result_id" in payload
    )
    if has_typed_identity:
        try:
            # Parse the complete row so nested and top-level identity fields
            # are conflict-checked by the shared typed contract.
            typed_decision_identity = DecisionIdentity.from_mapping(payload)
        except (TypeError, ValueError):
            # Keep the row visible as a fail-closed diagnostic, but do not
            # allow malformed typed metadata to use the legacy shared scope.
            typed_decision_identity = DecisionIdentity(
                identity_status=IDENTITY_STATUS_CONFLICT
            )
        if not typed_decision_identity.is_linked:
            if typed_decision_identity.identity_status == IDENTITY_STATUS_CONFLICT:
                direct = JourneyLinkStatus.CONFLICT
            elif direct != JourneyLinkStatus.CONFLICT:
                direct = JourneyLinkStatus.UNKNOWN
        else:
            candidate_codes = {
                item.stock_code
                for item in result.candidates
                if item.link_status == JourneyLinkStatus.LINKED
            }
            if (
                typed_decision_identity.result_id != result.result_id
                or typed_decision_identity.stock_code not in candidate_codes
            ):
                direct = JourneyLinkStatus.CONFLICT
            elif direct == JourneyLinkStatus.UNLINKED:
                direct = JourneyLinkStatus.LINKED
    return JournalEntryRecord(
        journal_id=_required_text(
            _first_value(payload, "journal_id", "entry_id", "id"),
            "journal.journal_id",
        ),
        linked_type=linked_type,
        linked_id=linked_id,
        thesis_id=thesis_id,
        source_type=_optional_text(payload.get("source_type")),
        source_id=source_id,
        source_snapshot_hash=snapshot_hash,
        created_at=_optional_text(payload.get("created_at")),
        updated_at=_optional_text(payload.get("updated_at")),
        relationship_type=relationship_type,
        relationship_target_id=relationship_target_id,
        link_status=direct,
        original_payload=_freeze(payload),
        decision_identity=typed_decision_identity,
    )


def _normalize_ledger_event(
    item: PortfolioLedgerEvent | Mapping[str, Any],
    result: RecommendationResultRecord,
    diagnostics: list[JourneyDiagnostic],
) -> PortfolioLedgerRecord:
    payload = _object_payload(item, "portfolio_ledger")
    source_id = _optional_text(_object_value(item, "source_id", payload.get("source_id")))
    snapshot_hash = _optional_text(
        _object_value(item, "source_snapshot_hash", payload.get("source_snapshot_hash"))
    )
    event_type = _text(_object_value(item, "event_type", payload.get("event_type")))
    source_namespace = _optional_text(
        _object_value(item, "source_namespace", payload.get("source_namespace"))
    )
    link_status = _identity_link_status(
        result.result_id,
        (
            ("source_id", source_id),
            ("source_snapshot_hash", snapshot_hash),
        ),
        expected_snapshot_hash=result.source_identity.source_snapshot_hash,
        conflict_when_other=True,
    )
    research_only_value = _object_value(item, "research_only", payload.get("research_only"))
    research_only = research_only_value if isinstance(research_only_value, bool) else None
    if source_namespace == "paper" or source_namespace == "backtest" or source_namespace == "synthetic":
        research_only = True if research_only is None else research_only
    semantics = {
        "manual": "user_recorded_event_broker_fill_unproven",
        "paper": "paper_simulation_research_only",
        "backtest": "backtest_research_only",
        "synthetic": "synthetic_fixture_only",
    }.get(source_namespace or "", "unknown_ledger_namespace")
    quantity = _optional_int(
        _object_value(item, "quantity", payload.get("quantity"))
    )
    price = _optional_decimal(
        _object_value(item, "price", payload.get("price")),
        diagnostics,
        entity_id=_text(_object_value(item, "event_id", payload.get("event_id"))),
        field_name="price",
    )
    fees = _optional_decimal(
        _object_value(item, "fees", payload.get("fees")),
        diagnostics,
        entity_id=_text(_object_value(item, "event_id", payload.get("event_id"))),
        field_name="fees",
    )
    taxes = _optional_decimal(
        _object_value(item, "taxes", payload.get("taxes")),
        diagnostics,
        entity_id=_text(_object_value(item, "event_id", payload.get("event_id"))),
        field_name="taxes",
    )
    return PortfolioLedgerRecord(
        record_id=_required_text(
            _object_value(item, "event_id", payload.get("event_id")),
            "portfolio_ledger.event_id",
        ),
        event_type=event_type,
        source_namespace=source_namespace,
        occurred_at=_optional_text(
            _object_value(item, "occurred_at", payload.get("occurred_at"))
        ),
        created_at=_optional_text(
            _object_value(item, "created_at", payload.get("created_at"))
        ),
        stock_code=_optional_text(
            _object_value(item, "stock_code", payload.get("stock_code"))
        ),
        side=_optional_text(_object_value(item, "side", payload.get("side"))),
        quantity=quantity,
        price=price,
        fees=fees,
        taxes=taxes,
        source_id=source_id,
        source_snapshot_hash=snapshot_hash,
        thesis_id=_optional_text(
            _object_value(item, "thesis_id", payload.get("thesis_id"))
        ),
        reverses_event_id=_optional_text(
            _object_value(item, "reverses_event_id", payload.get("reverses_event_id"))
        ),
        reason=_optional_text(_object_value(item, "reason", payload.get("reason"))),
        research_only=research_only,
        broker_fill_proven=False,
        execution_semantics=semantics,
        link_status=link_status,
        original_payload=_freeze(payload),
    )


def _normalize_portfolio_trade(
    payload: Mapping[str, Any],
    result: RecommendationResultRecord,
    diagnostics: list[JourneyDiagnostic],
) -> PortfolioTradeRecord:
    record_id = _required_text(
        _first_value(payload, "trade_id", "id"),
        "portfolio_trade.trade_id",
    )
    source_id = _optional_text(payload.get("source_id"))
    snapshot_hash = _optional_text(payload.get("source_snapshot_hash"))
    link_status = _identity_link_status(
        result.result_id,
        (
            ("source_id", source_id),
            ("source_snapshot_hash", snapshot_hash),
        ),
        expected_snapshot_hash=result.source_identity.source_snapshot_hash,
        conflict_when_other=True,
    )
    quantity = _optional_int(payload.get("quantity"))
    price = _optional_decimal(
        payload.get("price"),
        diagnostics,
        entity_id=record_id,
        field_name="price",
    )
    fees = _optional_decimal(
        payload.get("fees"),
        diagnostics,
        entity_id=record_id,
        field_name="fees",
    )
    taxes = _optional_decimal(
        payload.get("taxes"),
        diagnostics,
        entity_id=record_id,
        field_name="taxes",
    )
    return PortfolioTradeRecord(
        record_id=record_id,
        portfolio_id=_optional_text(payload.get("portfolio_id")),
        trade_date=_date_key(_optional_text(payload.get("trade_date"))),
        stock_code=_optional_text(payload.get("stock_code")),
        side=_optional_text(payload.get("side")),
        quantity=quantity,
        price=price,
        fees=fees,
        taxes=taxes,
        source_id=source_id,
        source_snapshot_hash=snapshot_hash,
        created_at=_optional_text(payload.get("created_at")),
        link_status=link_status,
        broker_fill_proven=False,
        original_payload=_freeze(payload),
    )


def _deduplicate_evidence(
    records: Sequence[EvidenceEventRecord],
    diagnostics: list[JourneyDiagnostic],
) -> list[EvidenceEventRecord]:
    grouped: dict[str, list[EvidenceEventRecord]] = {}
    for record in records:
        grouped.setdefault(record.event_id, []).append(record)
    result: list[EvidenceEventRecord] = []
    for event_id, group in grouped.items():
        if len(group) == 1:
            result.append(group[0])
            continue
        fingerprints = {_fingerprint(item.original_payload) for item in group}
        if len(fingerprints) == 1:
            result.append(group[0])
            _diag(
                diagnostics,
                "duplicate_evidence_event_key",
                f"event_id={event_id}; identical duplicate rows collapsed",
                "evidence_event",
                event_id,
            )
        else:
            _diag(
                diagnostics,
                "conflicting_duplicate_evidence_event",
                f"event_id={event_id}; conflicting payloads retained fail-closed",
                "evidence_event",
                event_id,
                severity="error",
            )
            result.extend(replace(item, link_status=JourneyLinkStatus.CONFLICT) for item in group)
    return sorted(result, key=lambda item: (item.event_date or _MISSING_TIME, item.event_id))


def _deduplicate_outcomes(
    records: Sequence[EvidenceOutcomeRecord],
    diagnostics: list[JourneyDiagnostic],
) -> list[EvidenceOutcomeRecord]:
    grouped: dict[tuple[str, int | None, str], list[EvidenceOutcomeRecord]] = {}
    for record in records:
        grouped.setdefault(
            (record.event_id, record.window_days, record.return_basis),
            [],
        ).append(record)
    result: list[EvidenceOutcomeRecord] = []
    for key, group in grouped.items():
        if len(group) == 1:
            result.append(group[0])
            continue
        fingerprints = {_fingerprint(item.original_payload) for item in group}
        if len(fingerprints) == 1:
            result.append(group[0])
            _diag(
                diagnostics,
                "duplicate_outcome_key",
                f"outcome_key={key}; identical duplicate rows collapsed",
                "evidence_outcome",
                group[0].outcome_id,
            )
        else:
            _diag(
                diagnostics,
                "conflicting_duplicate_outcome",
                f"outcome_key={key}; conflicting payloads retained fail-closed",
                "evidence_outcome",
                ":".join(str(value) for value in key),
                severity="error",
            )
            result.extend(replace(item, link_status=JourneyLinkStatus.CONFLICT) for item in group)
    return sorted(
        result,
        key=lambda item: (
            item.event_id,
            item.window_days if item.window_days is not None else 0,
            item.return_basis,
            item.outcome_id,
        ),
    )


def _deduplicate_journals(
    records: Sequence[JournalEntryRecord],
    diagnostics: list[JourneyDiagnostic],
) -> list[JournalEntryRecord]:
    return _deduplicate_simple(
        records,
        key=lambda item: item.journal_id,
        payload=lambda item: item.original_payload,
        mark_conflict=lambda item: replace(item, link_status=JourneyLinkStatus.CONFLICT),
        diagnostics=diagnostics,
        duplicate_code="duplicate_journal_key",
        conflict_code="conflicting_duplicate_journal",
        entity_type="journal",
    )


def _deduplicate_ledger(
    records: Sequence[PortfolioLedgerRecord],
    diagnostics: list[JourneyDiagnostic],
) -> list[PortfolioLedgerRecord]:
    return _deduplicate_simple(
        records,
        key=lambda item: item.record_id,
        payload=lambda item: item.original_payload,
        mark_conflict=lambda item: replace(item, link_status=JourneyLinkStatus.CONFLICT),
        diagnostics=diagnostics,
        duplicate_code="duplicate_portfolio_ledger_key",
        conflict_code="conflicting_duplicate_portfolio_ledger",
        entity_type="portfolio_ledger",
    )


def _deduplicate_trades(
    records: Sequence[PortfolioTradeRecord],
    diagnostics: list[JourneyDiagnostic],
) -> list[PortfolioTradeRecord]:
    return _deduplicate_simple(
        records,
        key=lambda item: item.record_id,
        payload=lambda item: item.original_payload,
        mark_conflict=lambda item: replace(item, link_status=JourneyLinkStatus.CONFLICT),
        diagnostics=diagnostics,
        duplicate_code="duplicate_portfolio_trade_key",
        conflict_code="conflicting_duplicate_portfolio_trade",
        entity_type="portfolio_trades",
    )


def _deduplicate_simple(
    records: Sequence[Any],
    *,
    key: Any,
    payload: Any,
    mark_conflict: Any,
    diagnostics: list[JourneyDiagnostic],
    duplicate_code: str,
    conflict_code: str,
    entity_type: str,
) -> list[Any]:
    grouped: dict[str, list[Any]] = {}
    for record in records:
        grouped.setdefault(str(key(record)), []).append(record)
    output: list[Any] = []
    for record_id, group in grouped.items():
        if len(group) == 1:
            output.append(group[0])
            continue
        fingerprints = {_fingerprint(payload(item)) for item in group}
        if len(fingerprints) == 1:
            output.append(group[0])
            _diag(
                diagnostics,
                duplicate_code,
                f"{entity_type} key={record_id}; identical duplicate rows collapsed",
                entity_type,
                record_id,
            )
        else:
            output.extend(mark_conflict(item) for item in group)
            _diag(
                diagnostics,
                conflict_code,
                f"{entity_type} key={record_id}; conflicting payloads retained fail-closed",
                entity_type,
                record_id,
                severity="error",
            )
    return sorted(output, key=lambda item: _sort_time(_record_time(item)) + str(key(item)))


def _coverage_counts(
    raw_rows: Sequence[Any],
    linked_rows: Sequence[Any],
) -> tuple[int, int, int, int, int]:
    counts = {status: 0 for status in JourneyLinkStatus}
    for item in linked_rows:
        status = getattr(item, "link_status", JourneyLinkStatus.UNKNOWN)
        counts[status] += 1
    linked = counts[JourneyLinkStatus.LINKED]
    unknown = counts[JourneyLinkStatus.UNKNOWN] + counts[JourneyLinkStatus.DEFERRED]
    conflict = counts[JourneyLinkStatus.CONFLICT] + counts[JourneyLinkStatus.AMBIGUOUS]
    unlinked = max(0, len(raw_rows) - linked - unknown - conflict)
    return len(raw_rows), linked, unlinked, unknown, conflict


def _overall_status(
    result: RecommendationResultRecord,
    events: Sequence[EvidenceEventRecord],
    maturity: Sequence[OutcomeMaturityRecord],
    journals: Sequence[JournalEntryRecord],
    ledgers: Sequence[PortfolioLedgerRecord],
    trades: Sequence[PortfolioTradeRecord],
    diagnostics: Sequence[JourneyDiagnostic],
) -> JourneyStatus:
    if result.link_status in {JourneyLinkStatus.UNKNOWN, JourneyLinkStatus.UNLINKED}:
        return JourneyStatus.UNKNOWN
    if result.link_status in {JourneyLinkStatus.CONFLICT, JourneyLinkStatus.AMBIGUOUS}:
        return JourneyStatus.CONFLICT
    if any(
        item.link_status in {JourneyLinkStatus.CONFLICT, JourneyLinkStatus.AMBIGUOUS}
        for item in result.candidates
    ):
        return JourneyStatus.CONFLICT
    if not result.candidates or any(
        item.link_status in {JourneyLinkStatus.UNKNOWN, JourneyLinkStatus.DEFERRED}
        for item in result.candidates
    ):
        candidate_gap = True
    else:
        candidate_gap = False
    if any(
        item.link_status in {JourneyLinkStatus.CONFLICT, JourneyLinkStatus.AMBIGUOUS}
        for item in events
    ) or any(
        item.link_status in {JourneyLinkStatus.CONFLICT, JourneyLinkStatus.AMBIGUOUS}
        for item in journals
    ) or any(
        item.link_status in {JourneyLinkStatus.CONFLICT, JourneyLinkStatus.AMBIGUOUS}
        for item in ledgers
    ) or any(
        item.link_status in {JourneyLinkStatus.CONFLICT, JourneyLinkStatus.AMBIGUOUS}
        for item in trades
    ) or any(
        item.status in {JourneyLinkStatus.CONFLICT, JourneyLinkStatus.AMBIGUOUS}
        for item in maturity
    ) or any(item.severity == "error" for item in diagnostics):
        return JourneyStatus.CONFLICT
    if not events or any(
        item.status
        in {
            JourneyLinkStatus.UNKNOWN,
            JourneyLinkStatus.AMBIGUOUS,
            JourneyLinkStatus.CONFLICT,
        }
        for item in maturity
    ):
        return JourneyStatus.PARTIAL
    if candidate_gap:
        return JourneyStatus.PARTIAL
    if any(
        item.link_status in {JourneyLinkStatus.DEFERRED, JourneyLinkStatus.UNKNOWN}
        for item in events
    ) or any(
        item.link_status in {JourneyLinkStatus.DEFERRED, JourneyLinkStatus.UNKNOWN}
        for item in journals
    ) or any(
        item.link_status in {JourneyLinkStatus.DEFERRED, JourneyLinkStatus.UNKNOWN}
        for item in ledgers
    ) or any(
        item.link_status in {JourneyLinkStatus.DEFERRED, JourneyLinkStatus.UNKNOWN}
        for item in trades
    ) or any(
        item.status == JourneyLinkStatus.DEFERRED
        for item in maturity
    ) or any(
        item.code in {
            "evidence_read_truncated",
            "evidence_link_unknown_due_to_truncated_read",
        }
        for item in diagnostics
    ):
        return JourneyStatus.PARTIAL
    return JourneyStatus.LINKED


def _identity_link_status(
    expected_id: str,
    values: Sequence[tuple[str, str | None]],
    *,
    expected_snapshot_hash: str | None = None,
    conflict_when_other: bool,
) -> JourneyLinkStatus:
    exact = False
    other_nonempty: list[str] = []
    for label, value in values:
        if not value:
            continue
        if value == expected_id:
            exact = True
        elif expected_snapshot_hash is not None and label == "source_snapshot_hash" and value == expected_snapshot_hash:
            exact = True
        else:
            other_nonempty.append(f"{label}={value}")
    if exact and other_nonempty and conflict_when_other:
        return JourneyLinkStatus.CONFLICT
    if exact:
        return JourneyLinkStatus.LINKED
    if other_nonempty:
        return JourneyLinkStatus.UNLINKED
    return JourneyLinkStatus.UNLINKED


def _consistent_identity(
    values: Sequence[tuple[str, str | None]],
    diagnostics: list[JourneyDiagnostic],
    *,
    code: str,
    entity_id: str,
) -> str | None:
    nonempty = [(label, value) for label, value in values if value]
    distinct = {cast(str, value) for _, value in nonempty}
    if len(distinct) > 1:
        _diag(
            diagnostics,
            code,
            "; ".join(f"{label}={value}" for label, value in nonempty),
            "recommendation_result",
            entity_id,
            severity="error",
        )
        return None
    return next(iter(distinct), None)


def _object_payload(item: Any, kind: str) -> Mapping[str, Any]:
    if isinstance(item, Mapping):
        return cast(Mapping[str, Any], item)
    to_dict = getattr(item, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return cast(Mapping[str, Any], payload)
    if is_dataclass(item) and not isinstance(item, type):
        return cast(
            Mapping[str, Any],
            {
                field_info.name: getattr(item, field_info.name)
                for field_info in fields(item)
            },
        )
    raise ValueError(f"{kind} does not provide a mapping payload")


def _object_value(item: Any, name: str, fallback: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(name, fallback)
    return getattr(item, name, fallback)


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return cast(Mapping[str, Any], value)
    return {}


def _read_jsonl(path: Path) -> tuple[Mapping[str, Any], ...]:
    if not path.is_file():
        return ()
    records: list[Mapping[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if not isinstance(payload, Mapping):
                raise ValueError(f"JSONL row must be an object: {path}:{line_number}")
            records.append(cast(Mapping[str, Any], payload))
    return tuple(records)


def _freeze(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted(_freeze(item) for item in value))
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _fingerprint(value: Any) -> str:
    return json.dumps(_thaw(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Enum):
        return str(value.value).strip()
    return str(value).strip()


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _required_text(value: Any, field_name: str) -> str:
    text = _text(value)
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _first_value(payload: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in payload and payload[name] not in (None, ""):
            return payload[name]
    return None


def _first_text(payload: Mapping[str, Any], *names: str) -> str | None:
    return _optional_text(_first_value(payload, *names))


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or isinstance(value, float):
        return None
    if isinstance(value, int):
        return value
    text = _text(value)
    if text.startswith("-"):
        digits = text[1:]
    else:
        digits = text
    if not digits.isdigit():
        return None
    return int(text)


def _optional_decimal(
    value: Any,
    diagnostics: list[JourneyDiagnostic],
    *,
    entity_id: str,
    field_name: str,
) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or isinstance(value, float):
        _diag(
            diagnostics,
            "non_decimal_financial_value",
            f"{field_name} 使用 float 或布林；保留 raw payload，不進行金融計算",
            "portfolio_record",
            entity_id,
        )
        return None
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        _diag(
            diagnostics,
            "invalid_decimal_financial_value",
            f"{field_name} 無法轉為 Decimal；保留 raw payload",
            "portfolio_record",
            entity_id,
        )
        return None
    if not result.is_finite():
        _diag(
            diagnostics,
            "invalid_decimal_financial_value",
            f"{field_name} 不是 finite Decimal；保留 raw payload",
            "portfolio_record",
            entity_id,
        )
        return None
    return result


def _date_key(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if len(text) < 10:
        return None
    try:
        date.fromisoformat(text[:10])
    except ValueError:
        return None
    return text[:10]


def _time_text(value: str | datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = _optional_text(value)
    return text


def _sort_time(value: str | None) -> str:
    if not value or not value.strip():
        return _MISSING_TIME
    parsed = _parse_temporal(value)
    if parsed is None:
        # Naive／invalid時間不應與可比較的 aware instant 混排在前面；仍以
        # fixed sentinel 保留 deterministic 的 item_type／item_id tie-break。
        return _MISSING_TIME
    kind, normalized = parsed
    if kind == "date":
        return f"{cast(date, normalized).isoformat()}T00:00:00+00:00"
    return cast(datetime, normalized).isoformat()


def _available_at_boundary(available_at: str | None, boundary: str | None) -> bool:
    if boundary is None:
        return True
    if available_at is None:
        return False
    available = _parse_temporal(available_at)
    limit = _parse_temporal(boundary)
    if available is None or limit is None:
        return False
    available_kind, available_value = available
    limit_kind, limit_value = limit
    if available_kind == "date" and limit_kind == "date":
        return cast(date, available_value) <= cast(date, limit_value)
    # date-only 是來源宣告的 calendar-day boundary。只能比較 calendar
    # date，不能虛構它在某個 timezone 的午夜；aware datetime 仍先以其
    # 保存的來源 date 參與這個明示的 day-level 規則。
    if available_kind == "date":
        return cast(date, available_value) <= cast(datetime, limit_value).date()
    if limit_kind == "date":
        return cast(datetime, available_value).date() <= cast(date, limit_value)
    return cast(datetime, available_value) <= cast(datetime, limit_value)


def _parse_temporal(value: str | None) -> tuple[str, date | datetime] | None:
    """解析可比較時間；naive datetime 一律 unknown，不猜 UTC。"""

    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) == 10:
        try:
            return "date", date.fromisoformat(text)
        except ValueError:
            return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return "datetime", parsed.astimezone(timezone.utc)


def _require_simple_id(value: str, field_name: str) -> None:
    if not value.strip() or "/" in value or "\\" in value or value in {".", ".."}:
        raise ValueError(f"{field_name} must be a simple identity, not a path")


def _adapter_path(reader: Any, result_id: str) -> str | None:
    path_for = getattr(reader, "path_for", None)
    if not callable(path_for):
        return None
    try:
        return str(path_for(result_id))
    except Exception:
        return None


def _diag(
    diagnostics: list[JourneyDiagnostic],
    code: str,
    detail: str,
    entity_type: str,
    entity_id: str,
    *,
    severity: str = "warning",
) -> None:
    diagnostics.append(
        JourneyDiagnostic(
            code=code,
            detail=detail,
            entity_type=entity_type,
            entity_id=entity_id,
            severity=severity,
        )
    )


def _unique_diagnostics(items: Iterable[JourneyDiagnostic]) -> list[JourneyDiagnostic]:
    output: list[JourneyDiagnostic] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for item in items:
        key = (item.code, item.detail, item.entity_type, item.entity_id, item.severity)
        if key not in seen:
            seen.add(key)
            output.append(item)
    return output


def _record_time(item: Any) -> str | None:
    for name in ("occurred_at", "trade_date", "created_at", "event_date"):
        value = getattr(item, name, None)
        if value:
            return _text(value)
    return None


__all__ = [
    "DEFAULT_MAX_EVIDENCE_EVENTS",
    "DecisionOutcomeJourney",
    "DecisionOutcomeJourneyService",
    "EvidenceEventRecord",
    "EvidenceOutcomeRecord",
    "EvidenceRepositoryReadAdapter",
    "JourneyCoverage",
    "JourneyDiagnostic",
    "JourneyLinkStatus",
    "JourneyStatus",
    "JourneyTimelineItem",
    "JsonRecommendationReadAdapter",
    "JsonlJournalReadAdapter",
    "JsonlPortfolioTradeReadAdapter",
    "JOURNEY_SCHEMA_VERSION",
    "JournalEntryRecord",
    "OUTCOME_WINDOWS",
    "OutcomeMaturityRecord",
    "PortfolioLedgerRecord",
    "PortfolioLedgerRepositoryReadAdapter",
    "PortfolioTradeRecord",
    "RecommendationCandidateRecord",
    "RecommendationResultRecord",
    "RecommendationSourceIdentity",
]
