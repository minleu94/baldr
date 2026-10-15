"""在既有 Registry 登錄配置研究原件的精確引用；不建立回測或績效。"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime, timezone
import hashlib
import json
from typing import TYPE_CHECKING, Callable

from app_module.portfolio_allocation_dtos import _validate_non_empty, _validate_sha256
from app_module.portfolio_research_scenario_artifact import encode_scenario_artifact, scenario_artifact_id
from app_module.portfolio_research_scenario_repository import (
    PortfolioResearchScenarioRepository, SavedPortfolioResearchScenario,
)
from app_module.sqlite_read_only import cooperative_read_cancellation

if TYPE_CHECKING:
    from app_module.research_run_repository import ResearchRunRepository

REFERENCE_SCHEMA = "portfolio-scenario-registry-reference.v1"
MAX_REFERENCE_BYTES = 8192


def _identity(account_kind: str, portfolio_id: str) -> None:
    if account_kind not in {"manual", "user_declared", "paper"}:
        raise ValueError("unsupported selected scenario account kind")
    if _validate_non_empty("portfolio_id", portfolio_id) != portfolio_id or len(portfolio_id) > 256:
        raise ValueError("selected scenario account id must be canonical and bounded")


def _clock(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo != timezone.utc:
        raise ValueError("Registry reference clock must be canonical UTC")
    return value.isoformat()


def _record_id(artifact_id: str) -> str:
    _digest("artifact_id", artifact_id)
    return "portfolio-scenario:" + artifact_id.removeprefix("sha256:")


def _digest(name: str, value: str) -> None:
    if _validate_sha256(name, value) != value:
        raise ValueError("Registry reference hash must be canonical")


@dataclass(frozen=True)
class ScenarioRegistrySelection:
    record_id: str
    reference_sha256: str
    account_kind: str
    portfolio_id: str
    artifact_id: str

    def __post_init__(self) -> None:
        _identity(self.account_kind, self.portfolio_id)
        _digest("reference_sha256", self.reference_sha256)
        if self.record_id != _record_id(self.artifact_id):
            raise ValueError("Registry selection record/artifact mismatch")


@dataclass(frozen=True)
class ScenarioRegistryEntry:
    record_id: str
    reference_sha256: str
    account_kind: str
    portfolio_id: str
    artifact_id: str
    snapshot_id: str
    decision_at: datetime
    source_saved_at: datetime
    registered_at: datetime
    input_hash: str

    def selection(self) -> ScenarioRegistrySelection:
        return ScenarioRegistrySelection(self.record_id, self.reference_sha256, self.account_kind,
                                         self.portfolio_id, self.artifact_id)


def encode_reference(entry: ScenarioRegistryEntry) -> bytes:
    if not isinstance(entry, ScenarioRegistryEntry):
        raise ValueError("Registry reference type mismatch")
    entry.selection()
    if _validate_non_empty("snapshot_id", entry.snapshot_id) != entry.snapshot_id or len(entry.snapshot_id) > 512:
        raise ValueError("Registry snapshot id must be canonical and bounded")
    _digest("input_hash", entry.input_hash)
    if entry.registered_at < entry.source_saved_at or entry.source_saved_at < entry.decision_at:
        raise ValueError("Registry reference clock precedes source")
    payload = {field.name: getattr(entry, field.name) for field in fields(entry)
               if field.name != "reference_sha256"}
    for name in ("decision_at", "source_saved_at", "registered_at"):
        payload[name] = _clock(payload[name])
    payload["schema_version"] = REFERENCE_SCHEMA
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_REFERENCE_BYTES:
        raise ValueError("Registry reference exceeds size limit")
    return encoded


def _hash(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def decode_reference(payload: bytes, reference_sha256: str) -> ScenarioRegistryEntry:
    _digest("reference_sha256", reference_sha256)
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_REFERENCE_BYTES or _hash(payload) != reference_sha256:
        raise ValueError("Registry reference size or hash mismatch")
    data = json.loads(payload)
    expected = {field.name for field in fields(ScenarioRegistryEntry)} - {"reference_sha256"}
    if type(data) is not dict or set(data) != expected | {"schema_version"} or data.pop("schema_version") != REFERENCE_SCHEMA:
        raise ValueError("Registry reference schema mismatch")
    if any(type(value) is not str for value in data.values()):
        raise ValueError("Registry reference field type mismatch")
    for name in ("decision_at", "source_saved_at", "registered_at"):
        data[name] = datetime.fromisoformat(data[name])
    entry = ScenarioRegistryEntry(reference_sha256=reference_sha256, **data)
    if encode_reference(entry) != payload:
        raise ValueError("Registry reference is not canonical")
    return entry


def create_entry(saved: SavedPortfolioResearchScenario, registered_at: datetime) -> ScenarioRegistryEntry:
    comparison = saved.comparison
    account = comparison.account
    if scenario_artifact_id(encode_scenario_artifact(comparison)) != saved.artifact_id:
        raise ValueError("Registry source artifact hash mismatch")
    # 先建立同欄位 payload，再填入其獨立引用 hash；hash 本身不進入 payload。
    entry = ScenarioRegistryEntry(_record_id(saved.artifact_id), "sha256:" + "0" * 64,
                                  account.account_kind, account.portfolio_id, saved.artifact_id,
                                  account.snapshot_id, comparison.decision_at, saved.saved_at,
                                  registered_at, comparison.input_hash)
    return decode_reference(encode_reference(entry), _hash(encode_reference(entry)))


def same_source(left: ScenarioRegistryEntry, right: ScenarioRegistryEntry) -> bool:
    return all(getattr(left, field.name) == getattr(right, field.name) for field in fields(left)
               if field.name not in {"reference_sha256", "registered_at"})


class PortfolioScenarioRegistryService:
    """兩份原件各自 create-only；登錄失敗保留原情境，可重試同一引用。"""

    def __init__(self, registry: ResearchRunRepository, source: PortfolioResearchScenarioRepository) -> None:
        self.registry = registry
        self.source = source

    @property
    def can_register(self) -> bool:
        return self.source.writable

    def register_saved(self, artifact_id: str, *, account_kind: str, portfolio_id: str,
                       cancel_callback: Callable[[], bool] | None = None) -> ScenarioRegistryEntry:
        if not self.can_register:
            raise ValueError("唯讀來源不可登錄研究紀錄")
        _identity(account_kind, portfolio_id)
        with cooperative_read_cancellation(cancel_callback):
            saved = self.source.get_exact(artifact_id, account_kind=account_kind, portfolio_id=portfolio_id)
            if saved is None:
                raise ValueError("Registry source artifact missing")
            candidate = create_entry(saved, datetime.now(timezone.utc))
            existing = self.registry.get_portfolio_scenario_reference(candidate.record_id)
            if existing is not None:
                if not same_source(existing, candidate):
                    raise ValueError("Registry reference conflicts with source")
                return existing
        # 寫入開始後不接受合作取消，避免已提交卻被標示取消。
        return self.registry.append_portfolio_scenario_reference(candidate)

    def list_registered(self, *, account_kind: str, portfolio_id: str,
                        cancel_callback: Callable[[], bool] | None = None) -> tuple[ScenarioRegistryEntry, ...]:
        with cooperative_read_cancellation(cancel_callback):
            return self.registry.list_portfolio_scenario_references(account_kind=account_kind, portfolio_id=portfolio_id, limit=25)

    def open_registered(self, selection: ScenarioRegistrySelection, *,
                        cancel_callback: Callable[[], bool] | None = None) -> SavedPortfolioResearchScenario:
        if not isinstance(selection, ScenarioRegistrySelection):
            raise ValueError("Registry selection type mismatch")
        with cooperative_read_cancellation(cancel_callback):
            entry = self.registry.get_portfolio_scenario_reference(selection.record_id)
            if entry is None or entry.selection() != selection:
                raise ValueError("Registry selection stale or missing")
            if entry.registered_at > datetime.now(timezone.utc):
                raise ValueError("Registry registration clock is in the future")
            saved = self.source.get_exact(entry.artifact_id, account_kind=entry.account_kind, portfolio_id=entry.portfolio_id)
            if saved is None or not same_source(entry, create_entry(saved, entry.registered_at)):
                raise ValueError("Registry source missing or differs from reference")
            return saved
