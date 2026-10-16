"""既有策略版本到原Registry研究的唯讀接點；版本聲明不授金融或升級資格。"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Callable

from app_module.research_history_lookup import ResearchHistoryEntry, ResearchHistoryLookup, ResearchHistoryResult
from app_module.research_run_dtos import ResearchRunMetadataDTO, normalize_research_run_json_value
from app_module.research_run_service import ResearchRunData
from app_module.saved_strategy_rule_card import SavedStrategyRuleCard, load_saved_strategy_rule_card
from app_module.strategy_version_service import StrategyVersion, StrategyVersionService


def _json(value: object) -> str:
    return json.dumps(normalize_research_run_json_value(value), ensure_ascii=False,
                      sort_keys=True, separators=(",", ":"), allow_nan=False)


def _cancel(callback: Callable[[], bool] | None) -> None:
    if callback is not None and callback():
        raise ValueError("saved_strategy_version_read_cancelled")


@dataclass(frozen=True)
class SavedStrategyVersionEntry:
    version_id: str
    strategy_id: str
    strategy_version: str
    source_run_id: str
    promoted_at: str
    validation_status: str
    version_json: str
    source_entry: ResearchHistoryEntry | None
    diagnostics: tuple[str, ...] = ()

    @property
    def version_sha256(self) -> str:
        return sha256(self.version_json.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SavedStrategyVersionPage:
    entries: tuple[SavedStrategyVersionEntry, ...]
    diagnostics: tuple[str, ...]
    total_catalog_count: int
    limit: int
    offset: int = 0


@dataclass(frozen=True)
class SavedStrategyVersionSource:
    selection: SavedStrategyVersionEntry
    history_result: ResearchHistoryResult
    rule_card: SavedStrategyRuleCard


def _version_json(version: StrategyVersion) -> str:
    if type(version) is not StrategyVersion:
        raise ValueError("saved_strategy_version_type_invalid")
    for value in (version.version_id, version.strategy_id, version.strategy_version,
                  version.source_run_id, version.promoted_at, version.validation_status):
        if type(value) is not str or not value or value != value.strip():
            raise ValueError("saved_strategy_version_identity_invalid")
    if not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,199}", version.version_id):
        raise ValueError("saved_strategy_version_id_invalid")
    if type(version.params) is not dict or type(version.config) is not dict:
        raise ValueError("saved_strategy_version_config_invalid")
    if version.validation_metrics is not None and type(version.validation_metrics) is not dict:
        raise ValueError("saved_strategy_version_validation_invalid")
    return _json(version.to_dict())


def _check_source(version: StrategyVersion, metadata: ResearchRunMetadataDTO) -> None:
    if (version.source_run_id != metadata.run_id or version.strategy_id != metadata.strategy_id
            or _json(version.params) != _json(metadata.normalized_params)):
        raise ValueError("saved_strategy_version_source_mismatch")
    expected = {"source": "research_run_registry", "run_type": metadata.run_type,
                "parameter_contract_version": metadata.parameter_contract_version,
                "data_fingerprint": metadata.data_fingerprint,
                "execution_price": metadata.execution_price, "sizing_mode": metadata.sizing_mode}
    if any(key not in version.config or _json(version.config[key]) != _json(value)
           for key, value in expected.items()):
        raise ValueError("saved_strategy_version_source_config_mismatch")
    if metadata.promoted_version_id and metadata.promoted_version_id != version.version_id:
        raise ValueError("saved_strategy_version_source_backlink_mismatch")
    declared = (version.validation_metrics or {}).get("data_fingerprint")
    if declared is not None and declared != metadata.data_fingerprint:
        raise ValueError("saved_strategy_version_validation_source_mismatch")
    # 保存版本號是生命週期標籤；不要求它等於原run的執行器版號。


class SavedStrategyVersionReader:
    def __init__(self, service: StrategyVersionService | None, lookup: ResearchHistoryLookup):
        self.service = service
        self.lookup = lookup

    def list_versions(self, *, limit: int = 200, offset: int = 0,
                      check_cancel: Callable[[], bool] | None = None) -> SavedStrategyVersionPage:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("saved_strategy_version_limit_invalid")
        if type(offset) is not int or offset < 0:
            raise ValueError("saved_strategy_version_offset_invalid")
        _cancel(check_cancel)
        if self.service is None:
            return SavedStrategyVersionPage((), ("saved_strategy_version_service_unavailable",), 0, limit, offset)
        records = self.service.list_versions()
        entries: list[SavedStrategyVersionEntry] = []
        diagnostics: list[str] = []
        ids = [row.get("version_id") for row in records]
        for row in records[offset:offset + limit]:
            _cancel(check_cancel)
            try:
                version = StrategyVersion.from_dict(row)
                snapshot = _version_json(version)
                if ids.count(version.version_id) != 1:
                    raise ValueError("saved_strategy_version_duplicate_id")
                current = self.service.get_version(version.version_id)
                if current is None or _version_json(current) != snapshot:
                    raise ValueError("saved_strategy_version_changed")
                source = None
                reasons: tuple[str, ...] = ()
                try:
                    if version.config.get("source") != "research_run_registry":
                        raise ValueError("saved_strategy_version_source_kind_unsupported")
                    source = self.lookup.select_registry_run(version.source_run_id, check_cancel=check_cancel)
                    if not source.result_supported:
                        raise ValueError(source.unsupported_reason or "saved_strategy_version_source_result_unsupported")
                    metadata = ResearchRunMetadataDTO(**json.loads(source.metadata_json))
                    _check_source(version, metadata)
                except (ValueError, OSError, TypeError) as exc:
                    source = None
                    reasons = (str(exc),)
                entries.append(SavedStrategyVersionEntry(
                    version.version_id, version.strategy_id, version.strategy_version, version.source_run_id,
                    version.promoted_at, version.validation_status, snapshot, source, reasons))
            except (ValueError, TypeError) as exc:
                diagnostics.append(str(exc))
        _cancel(check_cancel)
        return SavedStrategyVersionPage(tuple(entries), tuple(diagnostics), len(records), limit, offset)

    def read_source(self, selected: SavedStrategyVersionEntry, *,
                    check_cancel: Callable[[], bool] | None = None) -> SavedStrategyVersionSource:
        _cancel(check_cancel)
        if self.service is None or selected.source_entry is None or selected.diagnostics:
            raise ValueError("saved_strategy_version_source_unavailable")
        current = self.service.get_version(selected.version_id)
        if current is None or _version_json(current) != selected.version_json:
            raise ValueError("saved_strategy_version_changed")
        if any(getattr(current, key) != getattr(selected, key) for key in (
                "version_id", "strategy_id", "strategy_version", "source_run_id", "promoted_at", "validation_status")):
            raise ValueError("saved_strategy_version_selection_mismatch")
        history = self.lookup.resolve(selected.source_entry, check_cancel=check_cancel)
        if (self.lookup.registry is None or history.entry.source_kind != "registry"
                or not isinstance(history.result, ResearchRunData)):
            raise ValueError("saved_strategy_version_source_kind_unsupported")
        metadata = history.result.metadata
        _check_source(current, metadata)
        budget = self.lookup.read_budget
        rule = load_saved_strategy_rule_card(self.lookup.registry, metadata,
            max_artifact_bytes=budget.max_artifact_bytes if budget else None,
            max_total_bytes=budget.max_total_bytes if budget else None, check_cancel=check_cancel)
        _cancel(check_cancel)
        after = self.service.get_version(selected.version_id)
        if after is None or _version_json(after) != selected.version_json:
            raise ValueError("saved_strategy_version_changed")
        return SavedStrategyVersionSource(selected, history, rule)
