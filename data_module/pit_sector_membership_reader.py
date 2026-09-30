"""Read-only PIT sector membership consumer boundary.

這個模組只讀取既有的 PIT sidecar／machine publication，不下載來源、不寫入
SQLite、不修改 raw 或 sidecar，也不把 ``companies.csv`` 當成歷史分類。它把
manifest 宣告的狀態與 caller 真正可以消費的狀態分開，並在放行前重新驗證：

* envelope、manifest、rows、canonical hash 與 universe hash；
* source registry 的 license、market、available/effective interval 與 hash；
* registry 宣告的 raw bytes、官方 raw 的 canonical parse 與 canonical rows hash；
* decision cutoff、coverage window、同日內容衝突、taxonomy 與特殊證券欄位。

``PITMembershipReadResult.usable`` 只有在所有必要 custody gate 通過、且
artifact 不是 candidate-only 時才為真。prospective accepted 仍不代表
historical backfill、Formal OOS 或 promotion eligibility。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
import gzip
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo

from data_module.prospective_formal_clock import (
    canonical_json,
    load_clock_manifest_for_capture,
)
from data_module.prospective_official_pit_source import (
    OFFICIAL_COMPANY_SOURCE_DEFINITIONS,
    OFFICIAL_PROSPECTIVE_PIT_SOURCE_SCHEMA_VERSION,
)
from data_module.pit_taxonomy_definition_adapter import (
    PIT_TAXONOMY_TWSE_B1212_COMPOSITE_SOURCE_KIND,
    OfficialTaxonomyDefinitionError,
    parse_official_classification_definition,
    parse_official_twse_b1212_composite_classification_definition,
)
from data_module.pit_taxonomy_security_adapter import (
    OfficialSecurityTypingError,
    build_security_evidence_map,
    parse_official_isin_security_source,
)


PIT_MEMBERSHIP_READER_SCHEMA_VERSION = "pit-sector-membership-reader.v1"
PIT_SIDECAR_SCHEMA_VERSION = "pit-sector-membership-sidecar-v1"
PIT_SPLIT_SIDECAR_SCHEMA_VERSION = "pit-sector-membership-sidecar-v2"
PIT_PROSPECTIVE_MANIFEST_SCHEMA_VERSION = "pit-sector-membership-prospective-manifest-v1"
PIT_FORMAL_MANIFEST_SCHEMA_VERSION = "pit-sector-membership-manifest-v1"
PIT_SPLIT_MANIFEST_SCHEMA_VERSION = "pit-sector-membership-manifest-v2"
PIT_MACHINE_PUBLICATION_SCHEMA_VERSION = "pit-sector-membership-machine-publication.v1"
PIT_TAXONOMY_IDENTITY_SCHEMA_VERSION = "pit-industry-taxonomy-identity.v2"
PIT_TAXONOMY_SOURCE_SCHEMA_VERSION = "pit-industry-taxonomy-source.v1"
PIT_TAXONOMY_IDENTITY_V3_SCHEMA_VERSION = "pit-industry-taxonomy-identity.v3"
PIT_TAXONOMY_SOURCE_V2_SCHEMA_VERSION = "pit-industry-taxonomy-source.v2"
PIT_TAXONOMY_IDENTITY_V4_SCHEMA_VERSION = "pit-industry-taxonomy-identity.v4"
PIT_TAXONOMY_SOURCE_V3_SCHEMA_VERSION = "pit-industry-taxonomy-source.v3"
PIT_TAXONOMY_SCOPE_BINDING_SCHEMA_VERSION = "pit-industry-taxonomy-scope-binding.v1"
PIT_TAXONOMY_RAW_MANIFEST_SCHEMA_VERSION = "pit-industry-taxonomy-raw-manifest.v1"
PIT_UNIVERSE_IDENTITY_SCHEMA_VERSION = "manual-rule-only-universe.v1"
TAIPEI_TIMEZONE = ZoneInfo("Asia/Taipei")

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SYMBOL_RE = re.compile(r"^[0-9]{4,6}$")
_SECTOR_RE = re.compile(r"^[0-9]{2}$")
_SUPPORTED_MARKETS = frozenset({"twse_listed", "tpex_otc", "tpex_emerging"})
_TWSE_B1212_COMPOSITE_COMPONENTS = (
    "base_definition",
    "change_notice",
    "revision_history",
    "current_regulation",
)
_ROW_REQUIRED_FIELDS = frozenset(
    {
        "symbol",
        "sector_id",
        "available_at",
        "effective_from",
        "status",
        "source_id",
        "license_id",
        "source_hash",
    }
)
_ROW_OPTIONAL_FIELDS = frozenset(
    {"effective_to", "classification_version", "security_type", "market_scope"}
)
_TAXONOMY_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "classification_version",
        "source_id",
        "source_version",
        "source_hash",
        "source_path",
        "available_at",
        "effective_from",
        "classification_source_id",
        "classification_source_version",
        "security_source_id",
        "security_source_version",
        "universe_hash",
        "symbols",
        "mapping",
        "security_type_by_symbol",
        "mapping_hash",
    }
)
_TAXONOMY_SOURCE_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "classification_version",
        "source_id",
        "source_version",
        "available_at",
        "effective_from",
        "classification_source_id",
        "classification_source_version",
        "security_source_id",
        "security_source_version",
        "mapping",
        "security_type_by_symbol",
    }
)
_TAXONOMY_V3_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "classification_version_by_market",
        "source_id",
        "source_version",
        "source_hash",
        "source_path",
        "available_at",
        "effective_from",
        "universe_hash",
        "symbols",
        "universe_hash_symbols",
        "scores_bp",
        "rank_order",
        "mapping_by_market",
        "classification_sources_by_market",
        "security_sources_by_market",
        "market_by_symbol",
        "security_type_by_symbol",
        "security_eligibility_by_symbol",
        "eligible_symbols",
        "excluded_by_security",
        "unknown_symbols",
        "license_scope",
        "raw_manifest_path",
        "raw_manifest_hash",
        "mapping_hash",
    }
)
_TAXONOMY_SOURCE_V2_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "producer_version",
        "capture_date",
        "source_id",
        "source_version",
        "available_at",
        "effective_from",
        "universe_hash",
        "symbols",
        "universe_hash_symbols",
        "scores_bp",
        "rank_order",
        "mapping_by_market",
        "classification_sources_by_market",
        "security_sources_by_market",
        "market_by_symbol",
        "security_type_by_symbol",
        "security_eligibility_by_symbol",
        "eligible_symbols",
        "excluded_by_security",
        "unknown_symbols",
        "license_scope",
        "raw_manifest_path",
        "raw_manifest_hash",
    }
)
_SCOPE_BINDING_FIELDS = frozenset(
    {
        "scope_binding_schema_version",
        "denominator_binding",
        "rule_candidate_binding",
        "scope_diff",
        "taxonomy_coverage_complete",
        "rule_scope_compatible",
    }
)
_TAXONOMY_V4_REQUIRED_FIELDS = (
    _TAXONOMY_V3_REQUIRED_FIELDS
    | _SCOPE_BINDING_FIELDS
    | frozenset({"capture_attempt_binding", "inactive_security_overlay_by_symbol"})
)
_TAXONOMY_SOURCE_V3_REQUIRED_FIELDS = (
    _TAXONOMY_SOURCE_V2_REQUIRED_FIELDS
    | _SCOPE_BINDING_FIELDS
    | frozenset({"capture_attempt_binding", "inactive_security_overlay_by_symbol"})
)
_MANIFEST_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "formal_source_only",
        "research_only",
        "formal_consumer_compatible",
        "promotion_eligible",
        "scope",
        "historical_backfill_claimed",
        "clock_id",
        "clock_manifest_hash",
        "coverage_start",
        "coverage_end",
        "universe_hash",
        "row_count",
        "rows_hash",
        "source_registry",
        "canonical_hash",
    }
)
_COMMON_EQUITY_SECURITY_TYPES = frozenset(
    {"common_equity", "common_stock", "ordinary_share", "ordinary_stock", "普通股"}
)
_SUPPORTED_PIT_CLASSIFICATION_VERSIONS = frozenset(
    {
        "tw-industry-code-map.v1",
        "tw-industry-explicit-map.v1",
        "twse-industry-definition.v1",
    }
)
_KNOWN_SPECIAL_SECURITY_TOKENS = (
    "etf",
    "etn",
    "warrant",
    "tdr",
    "preferred",
    "inverse",
    "leveraged",
    "權證",
    "存託",
    "特別股",
    "槓桿",
    "反向",
)


class PITMembershipReaderError(ValueError):
    """PIT artifact 結構或來源契約無法解析。"""


@dataclass(frozen=True)
class PITMembershipRow:
    symbol: str
    sector_id: str
    market_scope: str
    available_at: datetime
    effective_from: date
    effective_to: date | None
    status: str
    source_id: str
    source_version: str
    license_id: str
    source_hash: str
    classification_version: str | None = None
    security_type: str | None = None
    industry_category: str | None = None
    security_eligible: bool = True
    security_exclusion_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "symbol": self.symbol,
            "sector_id": self.sector_id,
            "market_scope": self.market_scope,
            "available_at": self.available_at.isoformat(),
            "effective_from": self.effective_from.isoformat(),
            "effective_to": self.effective_to.isoformat() if self.effective_to else None,
            "status": self.status,
            "source_id": self.source_id,
            "source_version": self.source_version,
            "license_id": self.license_id,
            "source_hash": self.source_hash,
            "classification_version": self.classification_version,
            "security_type": self.security_type,
            "industry_category": self.industry_category,
            "security_eligible": self.security_eligible,
            "security_exclusion_reason": self.security_exclusion_reason,
        }
        return payload


@dataclass(frozen=True)
class PITMembershipArtifact:
    path: Path
    artifact_schema_version: str
    manifest_schema_version: str
    artifact_status: str
    scope: str
    coverage_start: date
    coverage_end: date
    formal_consumer_compatible: bool
    historical_backfill_claimed: bool
    promotion_eligible: bool
    row_count: int
    rows_hash: str
    canonical_hash: str
    universe_hash: str
    source_ids: tuple[str, ...]
    source_versions: tuple[str, ...]
    source_hashes: tuple[str, ...]
    market_scopes: tuple[str, ...]
    raw_custody_verified: bool
    universe_verified: bool
    hash_verified: bool
    taxonomy_verified: bool = False
    taxonomy_version: str | None = None


@dataclass(frozen=True)
class PITMembershipReadResult:
    as_of_date: date
    decision_at: datetime
    status: str
    quality: str
    rows: tuple[PITMembershipRow, ...]
    warnings: tuple[str, ...]
    lineage: dict[str, object]
    artifact: PITMembershipArtifact | None = None

    @property
    def usable(self) -> bool:
        return self.status == "accepted" and bool(self.rows)

    @property
    def industry_filter_usable(self) -> bool:
        """是否具備可證明的 taxonomy，足以做產業篩選。"""

        return self.usable and self.lineage.get("taxonomy_verified") is True

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": PIT_MEMBERSHIP_READER_SCHEMA_VERSION,
            "as_of_date": self.as_of_date.isoformat(),
            "decision_at": self.decision_at.isoformat(),
            "status": self.status,
            "quality": self.quality,
            "industry_filter_usable": self.industry_filter_usable,
            "row_count": len(self.rows),
            "rows": [row.to_dict() for row in self.rows],
            "warnings": list(self.warnings),
            "lineage": dict(self.lineage),
        }


@dataclass(frozen=True)
class PITUniverseReadResult:
    """Reader 對 producer universe identity 的唯讀重驗結果。"""

    symbols: tuple[str, ...]
    warnings: tuple[str, ...]
    verified: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": PIT_MEMBERSHIP_READER_SCHEMA_VERSION,
            "symbols": list(self.symbols),
            "warnings": list(self.warnings),
            "verified": self.verified,
        }


@dataclass(frozen=True)
class _ParsedArtifact:
    artifact: PITMembershipArtifact
    rows: tuple[PITMembershipRow, ...]
    warnings: tuple[str, ...]
    blocking_warnings: tuple[str, ...]
    source_lineage: tuple[dict[str, object], ...]
    taxonomy_lineage: dict[str, object]


@dataclass(frozen=True)
class _TaxonomyVerification:
    """v2/v3 taxonomy verification 的共同輸出形狀。"""

    mapping: dict[str, str]
    mapping_by_market: dict[str, dict[str, str]]
    security_by_symbol: dict[str, str]
    security_eligibility_by_symbol: dict[str, bool]
    security_exclusion_reason_by_symbol: dict[str, str]
    taxonomy_version: str | None
    taxonomy_version_by_market: dict[str, str]
    lineage: dict[str, object]
    warnings: list[str]
    verified: bool


class PITSectorMembershipReader:
    """以固定 cutoff 讀取 PIT sector membership 的唯讀 reader。"""

    def __init__(
        self,
        artifact_paths: Sequence[str | Path],
        *,
        raw_roots: Sequence[str | Path] = (),
        universe_symbols_paths: Sequence[str | Path] = (),
        universe_identity_paths: Sequence[str | Path] = (),
        clock_manifest_paths: Sequence[str | Path] = (),
        taxonomy_identity_paths: Sequence[str | Path] = (),
        expected_classification_version: str | None = None,
    ) -> None:
        self.artifact_paths = _normalize_paths(artifact_paths)
        self.raw_roots = _normalize_paths(raw_roots)
        self.universe_symbols_paths = _normalize_paths(universe_symbols_paths)
        self.universe_identity_paths = _normalize_paths(universe_identity_paths)
        self.clock_manifest_paths = _normalize_paths(clock_manifest_paths)
        self.taxonomy_identity_paths = _normalize_paths(taxonomy_identity_paths)
        self.expected_classification_version = (
            expected_classification_version.strip()
            if isinstance(expected_classification_version, str)
            and expected_classification_version.strip()
            else None
        )

    @classmethod
    def from_config(
        cls,
        config: Any,
        *,
        artifact_paths: Sequence[str | Path] = (),
        raw_roots: Sequence[str | Path] = (),
        universe_symbols_paths: Sequence[str | Path] = (),
        universe_identity_paths: Sequence[str | Path] = (),
        clock_manifest_paths: Sequence[str | Path] = (),
        taxonomy_identity_paths: Sequence[str | Path] = (),
        expected_classification_version: str | None = None,
    ) -> "PITSectorMembershipReader":
        """只從 config 已明確提供的 path 建立 reader；不掃描或創建資料。"""

        selected = tuple(artifact_paths)
        if not selected:
            configured = getattr(config, "pit_sector_membership_paths", ())
            if isinstance(configured, (str, Path)):
                selected = (configured,)
            elif isinstance(configured, Sequence):
                selected = tuple(configured)
        if not selected:
            configured_path = getattr(config, "pit_sector_membership_path", None)
            if configured_path:
                selected = (configured_path,)
        configured_raw_roots = tuple(raw_roots) or _config_paths(
            config,
            "pit_sector_membership_raw_roots",
            "pit_sector_membership_raw_root",
        )
        configured_symbols = tuple(universe_symbols_paths) or _config_paths(
            config,
            "pit_sector_membership_universe_symbols_paths",
            "pit_sector_membership_universe_symbols_path",
        )
        configured_identities = tuple(universe_identity_paths) or _config_paths(
            config,
            "pit_sector_membership_universe_identity_paths",
            "pit_sector_membership_universe_identity_path",
        )
        configured_clocks = tuple(clock_manifest_paths) or _config_paths(
            config,
            "pit_sector_membership_clock_manifest_paths",
            "pit_sector_membership_clock_manifest_path",
        )
        configured_taxonomies = tuple(taxonomy_identity_paths) or _config_paths(
            config,
            "pit_sector_membership_taxonomy_identity_paths",
            "pit_sector_membership_taxonomy_identity_path",
        )
        configured_classification = (
            expected_classification_version
            or getattr(config, "pit_membership_expected_classification_version", None)
        )
        return cls(
            selected,
            raw_roots=configured_raw_roots,
            universe_symbols_paths=configured_symbols,
            universe_identity_paths=configured_identities,
            clock_manifest_paths=configured_clocks,
            taxonomy_identity_paths=configured_taxonomies,
            expected_classification_version=configured_classification,
        )

    @staticmethod
    def default_decision_at(as_of_date: date) -> datetime:
        """Industry／Recommendation 共用的台北 08:30 PIT cutoff。"""

        return datetime.fromisoformat(
            f"{as_of_date.isoformat()}T08:30:00+08:00"
        ).astimezone(TAIPEI_TIMEZONE)

    def verify_universe_identity(
        self,
        identity_path: str | Path,
        *,
        universe_hash: str,
        row_symbols: Sequence[str],
    ) -> PITUniverseReadResult:
        """重新計算 producer 保存的 score-bound universe identity。

        這個小型唯讀入口讓 machine source producer 的返回 artifact 可以在
        不升格 candidate-only 的前提下直接交給同一 reader 重驗；它不會把
        identity 當成 PIT membership，也不會寫入任何資料。
        """

        path = Path(identity_path).expanduser().resolve()
        symbols, warnings = self._load_and_verify_universe(
            path,
            universe_hash=universe_hash,
            row_symbols=tuple(str(item) for item in row_symbols),
            inline_symbols=None,
        )
        if not _is_sha256(universe_hash):
            warnings.append("universe_hash_invalid")
        normalized_warnings = tuple(dict.fromkeys(warnings))
        return PITUniverseReadResult(
            symbols=tuple(symbols),
            warnings=normalized_warnings,
            verified=not normalized_warnings and bool(symbols),
        )

    def read(
        self,
        *,
        as_of_date: date,
        decision_at: datetime | str,
        market_scope: str | None = None,
    ) -> PITMembershipReadResult:
        decision = _parse_aware_datetime(decision_at, "decision_at")
        if not isinstance(as_of_date, date):
            raise TypeError("as_of_date must be a date")
        if market_scope is not None and market_scope not in _SUPPORTED_MARKETS:
            raise ValueError(f"unsupported PIT market_scope: {market_scope}")
        if as_of_date > decision.date():
            return self._result(
                as_of_date,
                decision,
                status="unavailable",
                quality="missing",
                rows=(),
                warnings=["pit_as_of_after_decision_date"],
                lineage={
                    "reader_schema_version": PIT_MEMBERSHIP_READER_SCHEMA_VERSION,
                    "as_of_date": as_of_date.isoformat(),
                    "decision_date": decision.date().isoformat(),
                    "market_scope_requested": market_scope,
                },
            )

        parsed: list[_ParsedArtifact] = []
        warnings: list[str] = []
        for path in self._expanded_artifact_paths():
            try:
                parsed.append(self._parse_artifact(path, decision_at=decision))
            except PITMembershipReaderError as error:
                warnings.append(f"pit_artifact_invalid:{path.name}:{_one_line(error)}")

        if not parsed:
            warnings.append("pit_membership_artifact_missing")
            return self._result(
                as_of_date,
                decision,
                status="unavailable",
                quality="missing",
                rows=(),
                warnings=warnings,
                lineage={"reader_schema_version": PIT_MEMBERSHIP_READER_SCHEMA_VERSION},
            )

        in_window = [
            item
            for item in parsed
            if item.artifact.coverage_start <= as_of_date <= item.artifact.coverage_end
        ]
        if not in_window:
            if any(item.artifact.coverage_start > as_of_date for item in parsed):
                warnings.append("membership_coverage_future_or_missing")
            if any(item.artifact.coverage_end < as_of_date for item in parsed):
                warnings.append("membership_coverage_stale_or_missing")
            if not warnings:
                warnings.append("membership_coverage_missing")
            return self._result(
                as_of_date,
                decision,
                status="unavailable",
                quality="missing",
                rows=(),
                warnings=warnings,
                lineage={
                    "reader_schema_version": PIT_MEMBERSHIP_READER_SCHEMA_VERSION,
                    "candidate_artifact_count": len(parsed),
                    "available_artifact_paths": [str(item.artifact.path) for item in parsed],
                },
            )

        scoped = (
            [item for item in in_window if market_scope in item.artifact.market_scopes]
            if market_scope is not None
            else list(in_window)
        )
        if not scoped:
            return self._result(
                as_of_date,
                decision,
                status="unavailable",
                quality="missing",
                rows=(),
                warnings=warnings + [f"membership_market_scope_missing:{market_scope}"],
                lineage={
                    "reader_schema_version": PIT_MEMBERSHIP_READER_SCHEMA_VERSION,
                    "market_scope_requested": market_scope,
                    "candidate_artifact_count": len(in_window),
                },
            )

        accepted = [item for item in scoped if item.artifact.artifact_status == "accepted"]
        candidate_only = [item for item in scoped if item.artifact.artifact_status == "candidate_only"]
        # A candidate or a broken artifact must not shadow a verified artifact
        # for the requested market.  Conflicts are evaluated only among
        # verified accepted artifacts with overlapping market scope.
        conflict_candidates = accepted or scoped
        selected_items: list[_ParsedArtifact] = []
        conflict = False
        if market_scope is not None:
            selected_items = self._select_scope_artifacts(
                conflict_candidates,
                market_scope=market_scope,
            )
            conflict = len(selected_items) == 0
        else:
            selected_items, conflict = self._select_all_market_artifacts(conflict_candidates)
        if conflict:
            conflict_warnings = [
                "membership_same_date_conflict",
                *[
                    f"membership_conflict_artifact:{item.artifact.path}"
                    for item in conflict_candidates
                ],
            ]
            return self._result(
                as_of_date,
                decision,
                status="unavailable",
                quality="missing",
                rows=(),
                warnings=warnings + conflict_warnings,
                lineage={
                    "reader_schema_version": PIT_MEMBERSHIP_READER_SCHEMA_VERSION,
                    "conflict_artifacts": [str(item.artifact.path) for item in conflict_candidates],
                },
            )

        if not accepted:
            selected = sorted(scoped, key=lambda item: str(item.artifact.path))[0]
            candidate_warnings = list(selected.warnings)
            candidate_warnings.extend(warnings)
            if candidate_only:
                candidate_warnings.append("pit_candidate_only_not_consumable")
            return self._result(
                as_of_date,
                decision,
                status="candidate_only" if candidate_only else "unavailable",
                quality="degraded" if candidate_only else "missing",
                rows=(),
                warnings=candidate_warnings,
                lineage=self._lineage_many(
                    selected_items or [selected], (), market_scope, as_of_date=as_of_date
                ),
                artifact=selected.artifact,
            )

        selected_warnings: list[str] = []
        for selected_item in selected_items:
            selected_warnings.extend(selected_item.warnings)
        selected_warnings.extend(warnings)
        if candidate_only:
            selected_warnings.append("pit_candidate_artifact_ignored_for_available_scope")
        rows = tuple(
            row
            for item in selected_items
            for row in item.rows
            if market_scope is None or row.market_scope == market_scope
        )
        if len({row.symbol for row in rows}) != len(rows):
            selected_warnings.append("membership_cross_market_symbol_conflict")
            return self._result(
                as_of_date,
                decision,
                status="unavailable",
                quality="missing",
                rows=(),
                warnings=selected_warnings,
                lineage=self._lineage_many(
                    selected_items, (), market_scope, as_of_date=as_of_date
                ),
                artifact=selected_items[0].artifact,
            )
        if market_scope is not None and not rows:
            selected_warnings.append(f"membership_market_scope_missing:{market_scope}")

        available_rows = tuple(
            row
            for row in rows
            if row.available_at <= decision
            and row.effective_from <= as_of_date
            and (row.effective_to is None or as_of_date <= row.effective_to)
        )
        if not available_rows:
            selected_warnings.append("membership_effective_interval_missing")
            return self._result(
                as_of_date,
                decision,
                status="unavailable",
                quality="missing",
                rows=(),
                warnings=selected_warnings,
                lineage=self._lineage_many(
                    selected_items, (), market_scope, as_of_date=as_of_date
                ),
                artifact=selected_items[0].artifact,
            )
        if len(available_rows) != len(rows):
            selected_warnings.append("membership_rows_filtered_by_cutoff_or_effective_interval")
        status = "accepted"
        quality = "observed" if not selected_warnings else "degraded"
        return self._result(
            as_of_date,
            decision,
            status=status,
            quality=quality,
            rows=available_rows,
            warnings=selected_warnings,
            lineage=self._lineage_many(
                selected_items, available_rows, market_scope, as_of_date=as_of_date
            ),
            artifact=selected_items[0].artifact,
        )

    def _expanded_artifact_paths(self) -> tuple[Path, ...]:
        result: list[Path] = []
        seen: set[Path] = set()
        for configured in self.artifact_paths:
            candidates: list[Path]
            if configured.is_dir():
                candidates = [configured / "manifest.json"]
                if not candidates[0].is_file():
                    candidates = sorted(
                        item
                        for item in configured.rglob("manifest.json")
                        if item.is_file()
                    )
            else:
                candidates = [configured]
            for candidate in candidates:
                resolved = candidate.expanduser().resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    result.append(resolved)
        return tuple(result)

    def _parse_artifact(self, path: Path, *, decision_at: datetime) -> _ParsedArtifact:
        payload = _read_json_payload(path)
        if payload.get("schema_version") == PIT_MACHINE_PUBLICATION_SCHEMA_VERSION:
            return self._parse_machine_publication(path, payload, decision_at=decision_at)
        if set(payload) != {"schema_version", "manifest", "rows"}:
            raise PITMembershipReaderError("PIT sidecar envelope fields are invalid")
        sidecar_schema = payload.get("schema_version")
        if sidecar_schema not in {
            PIT_SIDECAR_SCHEMA_VERSION,
            PIT_SPLIT_SIDECAR_SCHEMA_VERSION,
        }:
            raise PITMembershipReaderError("PIT sidecar schema_version is unsupported")
        manifest_value = payload.get("manifest")
        rows_value = payload.get("rows")
        if not isinstance(manifest_value, Mapping):
            raise PITMembershipReaderError("PIT sidecar manifest is invalid")
        if not isinstance(rows_value, list) or not rows_value:
            raise PITMembershipReaderError("PIT sidecar rows are required")
        return self._parse_sidecar(
            path,
            dict(manifest_value),
            rows_value,
            decision_at=decision_at,
            sidecar_schema_version=str(sidecar_schema),
        )

    def _parse_sidecar(
        self,
        path: Path,
        manifest: dict[str, object],
        rows_value: list[object],
        *,
        decision_at: datetime,
        sidecar_schema_version: str = PIT_SIDECAR_SCHEMA_VERSION,
    ) -> _ParsedArtifact:
        missing = sorted(_MANIFEST_REQUIRED_FIELDS - set(manifest))
        if missing:
            raise PITMembershipReaderError(
                "PIT manifest missing fields: " + ",".join(missing)
            )
        manifest_schema = _required_text(manifest.get("schema_version"), "manifest.schema_version")
        allowed_manifest_schemas = {
            PIT_PROSPECTIVE_MANIFEST_SCHEMA_VERSION,
            PIT_FORMAL_MANIFEST_SCHEMA_VERSION,
        }
        if sidecar_schema_version == PIT_SPLIT_SIDECAR_SCHEMA_VERSION:
            allowed_manifest_schemas.add(PIT_SPLIT_MANIFEST_SCHEMA_VERSION)
            missing_scope = sorted(_SCOPE_BINDING_FIELDS - set(manifest))
            if missing_scope:
                raise PITMembershipReaderError(
                    "PIT split manifest missing scope fields: " + ",".join(missing_scope)
                )
            if manifest_schema != PIT_SPLIT_MANIFEST_SCHEMA_VERSION:
                raise PITMembershipReaderError("PIT split manifest schema_version is unsupported")
            if manifest.get("scope_binding_schema_version") != PIT_TAXONOMY_SCOPE_BINDING_SCHEMA_VERSION:
                raise PITMembershipReaderError("PIT split scope-binding schema is unsupported")
            if manifest.get("taxonomy_coverage_complete") is not True:
                raise PITMembershipReaderError("PIT split taxonomy coverage is not complete")
            if manifest.get("formal_consumer_compatible") is not False:
                raise PITMembershipReaderError("PIT split candidate cannot claim formal compatibility")
            if not isinstance(manifest.get("denominator_binding"), Mapping) or not isinstance(
                manifest.get("rule_candidate_binding"), Mapping
            ) or not isinstance(manifest.get("scope_diff"), Mapping):
                raise PITMembershipReaderError("PIT split source bindings are invalid")
        elif sidecar_schema_version != PIT_SIDECAR_SCHEMA_VERSION:
            raise PITMembershipReaderError("PIT sidecar schema_version is unsupported")
        if manifest_schema not in allowed_manifest_schemas:
            raise PITMembershipReaderError("PIT manifest schema_version is unsupported")
        status = _required_text(manifest.get("status"), "manifest.status")
        if status not in {"complete", "formal_source_publication", "accepted"}:
            raise PITMembershipReaderError("PIT manifest status is not consumable")
        scope = _required_text(manifest.get("scope"), "manifest.scope")
        coverage_start = _required_date(manifest.get("coverage_start"), "manifest.coverage_start")
        coverage_end = _required_date(manifest.get("coverage_end"), "manifest.coverage_end")
        if coverage_end < coverage_start:
            raise PITMembershipReaderError("PIT manifest coverage interval is invalid")
        row_count = manifest.get("row_count")
        if not isinstance(row_count, int) or isinstance(row_count, bool) or row_count < 1:
            raise PITMembershipReaderError("manifest.row_count is invalid")
        rows_hash = _required_sha256(manifest.get("rows_hash"), "manifest.rows_hash")
        canonical_hash = _required_sha256(manifest.get("canonical_hash"), "manifest.canonical_hash")
        universe_hash = _required_sha256(manifest.get("universe_hash"), "manifest.universe_hash")

        canonical_manifest = dict(manifest)
        canonical_manifest.pop("canonical_hash", None)
        expected_canonical_hash = _sha256_json(
            {"sidecar_schema_version": sidecar_schema_version, "manifest": canonical_manifest}
        )
        blocking: list[str] = []
        warnings: list[str] = []
        hash_verified = canonical_hash == expected_canonical_hash
        if not hash_verified:
            blocking.append(
                f"membership_canonical_hash_mismatch:expected={canonical_hash}:actual={expected_canonical_hash}"
            )

        source_registry_value = manifest.get("source_registry")
        sources = self._normalize_sources(source_registry_value)
        source_map: dict[tuple[str, str, str], dict[str, object]] = {
            (str(item["source_id"]), str(item["license_id"]), str(item["source_hash"])): item
            for item in sources
        }
        normalized_rows, row_warnings, row_blocking = self._normalize_rows(
            rows_value,
            source_map,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            decision_at=decision_at,
        )
        warnings.extend(row_warnings)
        blocking.extend(row_blocking)
        actual_rows_hash = _sha256_json(normalized_rows)
        if actual_rows_hash != rows_hash:
            blocking.append(
                f"membership_rows_hash_mismatch:expected={rows_hash}:actual={actual_rows_hash}"
            )
        if row_count != len(normalized_rows):
            blocking.append(
                f"membership_row_count_mismatch:expected={row_count}:actual={len(normalized_rows)}"
            )

        declared_flags = {
            "formal_source_only": manifest.get("formal_source_only"),
            "research_only": manifest.get("research_only"),
            "formal_consumer_compatible": manifest.get("formal_consumer_compatible"),
            "promotion_eligible": manifest.get("promotion_eligible"),
            "historical_backfill_claimed": manifest.get("historical_backfill_claimed"),
        }
        if declared_flags["formal_source_only"] is not True:
            blocking.append("membership_formal_source_only_required")
        if declared_flags["research_only"] is not False:
            blocking.append("membership_research_only_not_consumable")
        if declared_flags["formal_consumer_compatible"] is not True:
            blocking.append("membership_formal_consumer_compatible_required")
        if (
            sidecar_schema_version == PIT_SPLIT_SIDECAR_SCHEMA_VERSION
            and manifest.get("rule_scope_compatible") is not True
        ):
            blocking.append("membership_rule_scope_incompatible")
        if declared_flags["promotion_eligible"] is not False:
            blocking.append("membership_promotion_eligibility_must_remain_false")
        if declared_flags["historical_backfill_claimed"] is not False:
            blocking.append("membership_historical_backfill_claimed_not_allowed")
        if scope not in {"prospective_only", "prospective_pit_sector_membership"}:
            blocking.append(f"membership_scope_not_consumable:{scope}")

        source_binding_warnings = self._verify_source_clock_bindings(
            sources,
            manifest=manifest,
        )
        warnings.extend(source_binding_warnings)
        blocking.extend(source_binding_warnings)

        clock_warnings = self._verify_clock_binding(
            path,
            manifest,
            decision_at=decision_at,
        )
        warnings.extend(clock_warnings)
        blocking.extend(clock_warnings)

        if sidecar_schema_version == PIT_SPLIT_SIDECAR_SCHEMA_VERSION:
            # v4 taxonomy validation rechecks both raw bindings.  v1 retains
            # the historical score-universe == row-universe equality reader.
            universe_warnings: list[str] = []
        else:
            universe_symbols, universe_warnings = self._load_and_verify_universe(
                path,
                universe_hash=universe_hash,
                row_symbols=tuple(str(row["symbol"]) for row in normalized_rows),
                inline_symbols=None,
            )
            del universe_symbols
        warnings.extend(universe_warnings)
        if universe_warnings:
            blocking.extend(universe_warnings)

        taxonomy = self._load_and_verify_taxonomy(
            path,
            universe_hash=universe_hash,
            rows=normalized_rows,
            as_of_date=coverage_start,
            decision_at=decision_at,
        )
        warnings.extend(taxonomy.warnings)
        taxonomy_mapping = taxonomy.mapping
        taxonomy_mapping_by_market = taxonomy.mapping_by_market
        taxonomy_security_by_symbol = taxonomy.security_by_symbol
        taxonomy_eligibility_by_symbol = taxonomy.security_eligibility_by_symbol
        taxonomy_exclusion_reasons = taxonomy.security_exclusion_reason_by_symbol
        taxonomy_version = taxonomy.taxonomy_version
        taxonomy_version_by_market = taxonomy.taxonomy_version_by_market
        taxonomy_lineage = taxonomy.lineage
        taxonomy_verified = taxonomy.verified

        source_raw_lineage, raw_warnings = self._verify_raw_sources(
            path,
            sources,
            rows=normalized_rows,
        )
        warnings.extend(raw_warnings)
        blocking.extend(raw_warnings)

        source_ids = tuple(sorted({str(item["source_id"]) for item in sources}))
        source_versions = tuple(sorted({str(item["source_version"]) for item in sources}))
        source_hashes = tuple(sorted({str(item["source_hash"]) for item in sources}))
        market_scopes = tuple(sorted({str(item["market"]) for item in sources}))
        artifact_status = "accepted" if not blocking else "unavailable"
        artifact = PITMembershipArtifact(
            path=path,
            artifact_schema_version=sidecar_schema_version,
            manifest_schema_version=manifest_schema,
            artifact_status=artifact_status,
            scope=scope,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            formal_consumer_compatible=declared_flags["formal_consumer_compatible"] is True,
            historical_backfill_claimed=declared_flags["historical_backfill_claimed"] is True,
            promotion_eligible=declared_flags["promotion_eligible"] is True,
            row_count=row_count,
            rows_hash=rows_hash,
            canonical_hash=canonical_hash,
            universe_hash=universe_hash,
            source_ids=source_ids,
            source_versions=source_versions,
            source_hashes=source_hashes,
            market_scopes=market_scopes,
            raw_custody_verified=not any(item.startswith("source_raw_") for item in raw_warnings),
            universe_verified=not any(item.startswith("universe_") for item in universe_warnings),
            hash_verified=hash_verified and actual_rows_hash == rows_hash,
            taxonomy_verified=taxonomy_verified,
            taxonomy_version=taxonomy_version,
        )
        source_lineage = tuple(source_raw_lineage)
        typed_rows = _materialize_rows(
            normalized_rows,
            source_map,
            taxonomy_mapping=taxonomy_mapping,
            taxonomy_mapping_by_market=taxonomy_mapping_by_market,
            taxonomy_security_by_symbol=taxonomy_security_by_symbol,
            taxonomy_eligibility_by_symbol=taxonomy_eligibility_by_symbol,
            taxonomy_exclusion_reason_by_symbol=taxonomy_exclusion_reasons,
            taxonomy_version=taxonomy_version,
            taxonomy_version_by_market=taxonomy_version_by_market,
        )
        return _ParsedArtifact(
            artifact=artifact,
            rows=typed_rows,
            warnings=tuple(dict.fromkeys(warnings)),
            blocking_warnings=tuple(dict.fromkeys(blocking)),
            source_lineage=source_lineage,
            taxonomy_lineage=taxonomy_lineage,
        )

    def _parse_machine_publication(
        self,
        path: Path,
        payload: dict[str, object],
        *,
        decision_at: datetime,
    ) -> _ParsedArtifact:
        required = {
            "schema_version",
            "status",
            "candidate_only",
            "formal_consumer_compatible",
            "historical_backfill_claimed",
            "promotion_eligible",
            "scope",
            "effective_from",
            "universe",
            "source_registry",
            "raw_inputs",
            "rows",
            "row_count",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise PITMembershipReaderError("machine publication missing fields: " + ",".join(missing))
        if payload.get("status") != "complete" or payload.get("candidate_only") is not True:
            raise PITMembershipReaderError("machine publication must remain candidate_only")
        universe = payload.get("universe")
        if not isinstance(universe, Mapping):
            raise PITMembershipReaderError("machine publication universe is invalid")
        symbols = universe.get("symbols")
        if not isinstance(symbols, list) or any(not isinstance(item, str) for item in symbols):
            raise PITMembershipReaderError("machine publication universe symbols are invalid")
        universe_hash = _required_sha256(universe.get("hash"), "universe.hash")
        if universe_hash != _sha256_json(symbols):
            raise PITMembershipReaderError("machine publication universe hash mismatch")
        rows_value = payload.get("rows")
        if not isinstance(rows_value, list) or not rows_value:
            raise PITMembershipReaderError("machine publication rows are required")
        effective_from = _required_date(payload.get("effective_from"), "effective_from")
        source_registry = self._normalize_machine_sources(payload.get("source_registry"))
        source_map: dict[tuple[str, str, str], dict[str, object]] = {
            (str(item["source_id"]), str(item["license_id"]), str(item["source_hash"])): item
            for item in source_registry
        }
        normalized_rows, warnings, blocking = self._normalize_rows(
            rows_value,
            source_map,
            coverage_start=effective_from,
            coverage_end=effective_from,
            decision_at=decision_at,
        )
        if tuple(sorted(str(row["symbol"]) for row in normalized_rows)) != tuple(sorted(symbols)):
            blocking.append("membership_universe_row_symbol_mismatch")
        raw_lineage, raw_warnings = self._verify_machine_raw_inputs(path, payload, source_registry)
        warnings.extend(raw_warnings)
        blocking.extend(raw_warnings)
        rows_hash = _sha256_json(normalized_rows)
        content_hash = payload.get("content_sha256")
        hash_verified = _is_sha256(content_hash) and _sha256_json(
            {key: value for key, value in payload.items() if key != "content_sha256"}
        ) == content_hash
        if not hash_verified:
            blocking.append("membership_machine_content_hash_mismatch")
        row_count_value = payload.get("row_count")
        if (
            not isinstance(row_count_value, int)
            or isinstance(row_count_value, bool)
            or row_count_value < 1
        ):
            raise PITMembershipReaderError("machine publication row_count is invalid")
        # Candidate publications never become accepted, even if every custody check passes.
        warnings.append("pit_candidate_only_not_consumable")
        artifact = PITMembershipArtifact(
            path=path,
            artifact_schema_version=str(payload["schema_version"]),
            manifest_schema_version="machine-publication",
            artifact_status="candidate_only",
            scope=str(payload["scope"]),
            coverage_start=effective_from,
            coverage_end=effective_from,
            formal_consumer_compatible=payload.get("formal_consumer_compatible") is True,
            historical_backfill_claimed=payload.get("historical_backfill_claimed") is True,
            promotion_eligible=payload.get("promotion_eligible") is True,
            row_count=row_count_value,
            rows_hash=rows_hash,
            canonical_hash=str(content_hash or ""),
            universe_hash=universe_hash,
            source_ids=tuple(sorted(str(item["source_id"]) for item in source_registry)),
            source_versions=tuple(sorted(str(item["source_version"]) for item in source_registry)),
            source_hashes=tuple(sorted(str(item["source_hash"]) for item in source_registry)),
            market_scopes=tuple(sorted(str(item["market"]) for item in source_registry)),
            raw_custody_verified=not raw_warnings,
            universe_verified=True,
            hash_verified=hash_verified,
        )
        typed_rows = _materialize_rows(normalized_rows, source_map)
        return _ParsedArtifact(
            artifact=artifact,
            rows=typed_rows,
            warnings=tuple(dict.fromkeys(warnings)),
            blocking_warnings=tuple(dict.fromkeys(blocking)),
            source_lineage=tuple(raw_lineage),
            taxonomy_lineage={
                "taxonomy_status": "not_applicable_candidate_only",
                "taxonomy_verified": False,
            },
        )

    def _normalize_machine_sources(self, value: object) -> list[dict[str, object]]:
        """Normalize machine source rows whose hash predates machine-only fields.

        ``build_machine_pit_publication`` appends ``raw_path``, precision, and
        capture-scope metadata after the shared official source registry entry
        has been hashed.  The machine contract validates those additions as
        part of its own publication; this reader must preserve the producer's
        hash semantics instead of recomputing the hash over the augmented row.
        """

        if not isinstance(value, list) or not value:
            raise PITMembershipReaderError("machine PIT source_registry is invalid")
        base_rows: list[dict[str, object]] = []
        extensions: dict[tuple[str, str, str], dict[str, object]] = {}
        for raw in value:
            if not isinstance(raw, Mapping):
                raise PITMembershipReaderError("machine PIT source_registry entry is invalid")
            base = dict(raw)
            extra = {
                field: raw[field]
                for field in ("raw_path", "publication_time_precision", "capture_scope")
                if field in raw
            }
            for field in extra:
                base.pop(field, None)
            source_id = base.get("source_id")
            license_id = base.get("license_id")
            source_hash = base.get("source_hash")
            if (
                not isinstance(source_id, str)
                or not isinstance(license_id, str)
                or not isinstance(source_hash, str)
            ):
                raise PITMembershipReaderError("machine PIT source_registry identity is invalid")
            extensions[(source_id, license_id, source_hash)] = extra
            base_rows.append(base)
        normalized = self._normalize_sources(base_rows)
        for entry in normalized:
            key = (
                str(entry["source_id"]),
                str(entry["license_id"]),
                str(entry["source_hash"]),
            )
            entry.update(extensions.get(key, {}))
        return normalized

    def _normalize_sources(self, value: object) -> list[dict[str, object]]:
        if not isinstance(value, list) or not value:
            raise PITMembershipReaderError("PIT source_registry must be a non-empty array")
        normalized: list[dict[str, object]] = []
        seen: set[tuple[str, str, str]] = set()
        for raw in value:
            if not isinstance(raw, Mapping):
                raise PITMembershipReaderError("PIT source_registry entry is invalid")
            source_id = _required_text(raw.get("source_id"), "source_registry.source_id")
            license_id = _required_text(raw.get("license_id"), "source_registry.license_id")
            source_hash = _required_sha256(raw.get("source_hash"), "source_registry.source_hash")
            source_version = _required_text(raw.get("source_version"), "source_registry.source_version")
            publication_at = _parse_aware_datetime(
                raw.get("publication_at"), "source_registry.publication_at"
            )
            allowed_use = raw.get("allowed_use")
            if not isinstance(allowed_use, list) or "prospective_pit_sector_membership" not in allowed_use:
                raise PITMembershipReaderError("source_registry.allowed_use does not authorize PIT membership")
            market = _required_text(raw.get("market"), "source_registry.market")
            if market not in _SUPPORTED_MARKETS:
                raise PITMembershipReaderError(f"source_registry.market is unsupported: {market}")
            raw_hash = _required_sha256(raw.get("raw_hash"), "source_registry.raw_hash")
            if raw_hash != source_hash:
                raise PITMembershipReaderError(f"source_registry.raw_hash mismatch: {source_id}")
            canonical_rows_hash = _required_sha256(
                raw.get("canonical_rows_hash"), "source_registry.canonical_rows_hash"
            )
            available_at = _parse_aware_datetime(raw.get("available_at"), "source_registry.available_at")
            effective_from = _required_date(raw.get("effective_from"), "source_registry.effective_from")
            source_registry_hash = _required_sha256(
                raw.get("source_registry_hash"), "source_registry.source_registry_hash"
            )
            source_without_hash = dict(raw)
            source_without_hash.pop("source_registry_hash", None)
            expected_source_registry_hash = _sha256_json(source_without_hash)
            if source_registry_hash != expected_source_registry_hash:
                raise PITMembershipReaderError(
                    f"source_registry.source_registry_hash mismatch: {source_id}"
                )
            if publication_at > available_at:
                raise PITMembershipReaderError(f"source publication is after available_at: {source_id}")
            key = (source_id, license_id, source_hash)
            if key in seen:
                raise PITMembershipReaderError("source_registry entries must be unique")
            seen.add(key)
            entry = dict(raw)
            entry.update(
                {
                    "source_id": source_id,
                    "license_id": license_id,
                    "source_hash": source_hash,
                    "source_version": source_version,
                    "publication_at": publication_at.isoformat(),
                    "market": market,
                    "raw_hash": raw_hash,
                    "canonical_rows_hash": canonical_rows_hash,
                    "available_at": available_at.isoformat(),
                    "effective_from": effective_from.isoformat(),
                    "source_registry_hash": source_registry_hash,
                }
            )
            normalized.append(entry)
        return sorted(normalized, key=lambda item: str(item["source_id"]))

    def _verify_source_clock_bindings(
        self,
        sources: Sequence[Mapping[str, object]],
        *,
        manifest: Mapping[str, object],
    ) -> list[str]:
        warnings: list[str] = []
        expected_clock_id = str(manifest.get("clock_id", ""))
        expected_clock_hash = str(manifest.get("clock_manifest_hash", ""))
        expected_universe_hash = str(manifest.get("universe_hash", ""))
        for source in sources:
            source_id = str(source.get("source_id", ""))
            for field_name, expected, warning_name in (
                ("clock_id", expected_clock_id, "source_clock_id_mismatch"),
                (
                    "clock_manifest_hash",
                    expected_clock_hash,
                    "source_clock_manifest_hash_mismatch",
                ),
                ("universe_hash", expected_universe_hash, "source_universe_hash_mismatch"),
            ):
                actual = source.get(field_name)
                if not isinstance(actual, str) or not actual.strip():
                    warnings.append(f"source_{field_name}_missing:{source_id}")
                elif actual != expected:
                    warnings.append(f"{warning_name}:{source_id}")
            effective_from = source.get("effective_from")
            coverage_start = manifest.get("coverage_start")
            if (
                isinstance(effective_from, str)
                and isinstance(coverage_start, str)
                and effective_from != coverage_start
            ):
                warnings.append(f"source_effective_from_manifest_mismatch:{source_id}")
        return list(dict.fromkeys(warnings))

    def _verify_clock_binding(
        self,
        artifact_path: Path,
        manifest: Mapping[str, object],
        *,
        decision_at: datetime,
    ) -> list[str]:
        candidates = list(self.clock_manifest_paths)
        auto = artifact_path.parent.parent / "clock" / "manifest.json"
        if auto not in candidates:
            candidates.append(auto)
        selected = next((path for path in candidates if path.is_file()), None)
        if selected is None:
            return ["clock_manifest_missing"]
        try:
            clock = load_clock_manifest_for_capture(selected, now=decision_at)
        except Exception as error:  # noqa: BLE001 - this is a fail-closed gate
            return [f"clock_manifest_invalid:{selected}:{_one_line(error)}"]

        warnings: list[str] = []
        if clock.clock_id != manifest.get("clock_id"):
            warnings.append("clock_id_mismatch")
        if clock.manifest_hash != manifest.get("clock_manifest_hash"):
            warnings.append("clock_manifest_hash_mismatch")
        if clock.payload.get("universe_hash") != manifest.get("universe_hash"):
            warnings.append("clock_universe_hash_mismatch")
        return warnings

    def _normalize_rows(
        self,
        rows_value: list[object],
        source_map: Mapping[tuple[str, str, str], Mapping[str, object]],
        *,
        coverage_start: date,
        coverage_end: date,
        decision_at: datetime,
    ) -> tuple[list[dict[str, object]], list[str], list[str]]:
        normalized: list[dict[str, object]] = []
        warnings: list[str] = []
        blocking: list[str] = []
        natural_keys: set[tuple[str, str, str, str]] = set()
        for raw in rows_value:
            if not isinstance(raw, Mapping):
                raise PITMembershipReaderError("PIT membership row is invalid")
            allowed = _ROW_REQUIRED_FIELDS | _ROW_OPTIONAL_FIELDS
            if _ROW_REQUIRED_FIELDS - set(raw) or set(raw) - allowed:
                raise PITMembershipReaderError("PIT membership row fields are invalid")
            symbol = _required_text(raw.get("symbol"), "row.symbol")
            if _SYMBOL_RE.fullmatch(symbol) is None:
                raise PITMembershipReaderError(f"row.symbol is invalid: {symbol}")
            sector_id = _required_text(raw.get("sector_id"), "row.sector_id")
            if _SECTOR_RE.fullmatch(sector_id) is None or sector_id == "00":
                raise PITMembershipReaderError(f"row.sector_id is invalid: {sector_id}")
            status = _required_text(raw.get("status"), "row.status")
            if status != "accepted":
                blocking.append(f"membership_row_status_not_accepted:{symbol}:{status}")
            available_at = _parse_aware_datetime(raw.get("available_at"), "row.available_at")
            effective_from = _required_date(raw.get("effective_from"), "row.effective_from")
            effective_to_value = raw.get("effective_to")
            effective_to = (
                None
                if effective_to_value in (None, "")
                else _required_date(effective_to_value, "row.effective_to")
            )
            if effective_from < coverage_start or effective_from > coverage_end:
                blocking.append(f"membership_effective_from_outside_coverage:{symbol}")
            if effective_to is not None and effective_to < effective_from:
                blocking.append(f"membership_effective_interval_invalid:{symbol}")
            if effective_to is not None and effective_to < coverage_end:
                blocking.append(f"membership_effective_interval_does_not_cover_coverage_end:{symbol}")
            source_id = _required_text(raw.get("source_id"), "row.source_id")
            license_id = _required_text(raw.get("license_id"), "row.license_id")
            source_hash = _required_sha256(raw.get("source_hash"), "row.source_hash")
            source = source_map.get((source_id, license_id, source_hash))
            if source is None:
                blocking.append(f"membership_source_lineage_missing:{symbol}")
                source = {
                    "source_version": "",
                    "market": "",
                    "available_at": available_at.isoformat(),
                    "effective_from": effective_from.isoformat(),
                }
            source_available_at = _parse_aware_datetime(source["available_at"], "source.available_at")
            source_effective_from = _required_date(source["effective_from"], "source.effective_from")
            if available_at != source_available_at:
                blocking.append(f"membership_available_at_source_mismatch:{symbol}")
            if effective_from != source_effective_from:
                blocking.append(f"membership_effective_from_source_mismatch:{symbol}")
            if source_available_at > decision_at:
                warnings.append(f"membership_available_after_decision:{symbol}")
            if source_effective_from > coverage_end:
                blocking.append(f"membership_source_effective_after_coverage:{symbol}")
            classification = raw.get("classification_version")
            classification_text = None
            if classification not in (None, ""):
                classification_text = _required_text(classification, "row.classification_version")
                if (
                    self.expected_classification_version is not None
                    and classification_text != self.expected_classification_version
                ):
                    blocking.append(
                        f"membership_classification_version_mismatch:{symbol}:"
                        f"expected={self.expected_classification_version}:actual={classification_text}"
                    )
            else:
                warnings.append("membership_classification_version_missing")
            security = raw.get("security_type")
            security_text = None
            if security not in (None, ""):
                security_text = _required_text(security, "row.security_type")
                security_normalized = security_text.casefold()
                if security_text not in _COMMON_EQUITY_SECURITY_TYPES:
                    if any(token in security_normalized for token in _KNOWN_SPECIAL_SECURITY_TOKENS):
                        blocking.append(f"membership_special_security_rejected:{symbol}:{security_text}")
                    else:
                        blocking.append(f"membership_security_type_unrecognized:{symbol}:{security_text}")
            else:
                warnings.append("membership_security_type_unrecorded")
            market_scope = str(source.get("market", ""))
            declared_market_scope = raw.get("market_scope")
            if declared_market_scope not in (None, ""):
                declared_market = _required_text(declared_market_scope, "row.market_scope")
                if declared_market != market_scope:
                    blocking.append(f"membership_market_scope_mismatch:{symbol}")
            if not market_scope:
                blocking.append(f"membership_market_scope_missing:{symbol}")
            key = (symbol, available_at.isoformat(), effective_from.isoformat(), sector_id)
            if key in natural_keys:
                blocking.append(f"membership_duplicate_natural_key:{symbol}")
            natural_keys.add(key)
            normalized_row: dict[str, object] = {
                "symbol": symbol,
                "sector_id": sector_id,
                "available_at": available_at.isoformat(),
                "effective_from": effective_from.isoformat(),
                "effective_to": effective_to.isoformat() if effective_to else None,
                "status": status,
                "source_id": source_id,
                "license_id": license_id,
                "source_hash": source_hash,
            }
            if classification_text is not None:
                normalized_row["classification_version"] = classification_text
            if security_text is not None:
                normalized_row["security_type"] = security_text
            if declared_market_scope not in (None, ""):
                normalized_row["market_scope"] = str(declared_market_scope)
            normalized.append(normalized_row)
        normalized.sort(
            key=lambda item: (
                str(item["symbol"]),
                str(item["effective_from"]),
                str(item["available_at"]),
                str(item["sector_id"]),
            )
        )
        return normalized, warnings, blocking

    def _load_and_verify_universe(
        self,
        artifact_path: Path,
        *,
        universe_hash: str,
        row_symbols: Sequence[str],
        inline_symbols: Sequence[str] | None,
    ) -> tuple[tuple[str, ...], list[str]]:
        """驗證與 clock 綁定的 score-bearing universe identity。

        ``universe_symbols.json`` 只提供集合的可讀投影，不能單獨重建
        ``manual-rule-only-universe.v1`` 的 hash；該 hash 還包含每個候選的
        integer score。若 identity 沒有 scores，這裡明確阻擋 accepted artifact。
        """

        warnings: list[str] = []
        symbols: tuple[str, ...] | None = None
        identity_symbols: tuple[str, ...] | None = None
        identity: Mapping[str, object] | None = None
        identity_path: Path | None = None

        if inline_symbols is not None:
            symbols = tuple(str(item) for item in inline_symbols)
        else:
            candidates = list(self.universe_symbols_paths)
            auto = artifact_path.parent.parent / "metadata" / "universe_symbols.json"
            if auto not in candidates:
                candidates.append(auto)
            for candidate in candidates:
                if not candidate.is_file():
                    continue
                try:
                    raw = _loads_no_duplicate_keys(candidate.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                    warnings.append(f"universe_symbols_unreadable:{candidate}")
                    continue
                values = raw.get("symbols") if isinstance(raw, Mapping) else raw
                if isinstance(values, list) and all(isinstance(item, str) for item in values):
                    symbols = tuple(values)
                    break
            if symbols is None:
                warnings.append("universe_symbols_missing")

        identity_candidates = list(self.universe_identity_paths)
        auto_identity = artifact_path.parent.parent / "metadata" / "universe_identity.json"
        if auto_identity not in identity_candidates:
            identity_candidates.append(auto_identity)
        for candidate in identity_candidates:
            if not candidate.is_file():
                continue
            identity_path = candidate
            try:
                raw_identity = _loads_no_duplicate_keys(
                    candidate.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                warnings.append(f"universe_identity_unreadable:{candidate}")
                break
            if not isinstance(raw_identity, Mapping):
                warnings.append("universe_identity_schema_invalid")
                break
            identity = raw_identity
            break
        if identity_path is None and inline_symbols is None:
            warnings.append("universe_identity_missing")

        if identity is not None:
            if identity.get("schema_version") != PIT_UNIVERSE_IDENTITY_SCHEMA_VERSION:
                warnings.append("universe_identity_schema_invalid")

            raw_identity_symbols = identity.get("symbols")
            if not isinstance(raw_identity_symbols, list) or any(
                not isinstance(item, str) for item in raw_identity_symbols
            ):
                warnings.append("universe_identity_symbols_invalid")
            else:
                identity_symbols = tuple(raw_identity_symbols)
                if identity_symbols != tuple(sorted(set(identity_symbols))):
                    warnings.append("universe_identity_symbols_not_sorted_unique")

            identity_hash = identity.get("universe_hash")
            if not _is_sha256(identity_hash):
                warnings.append("universe_identity_hash_invalid")
            elif identity_hash != universe_hash:
                warnings.append("universe_identity_hash_mismatch")

            candidate_count = identity.get("candidate_count")
            if identity_symbols is not None and (
                not isinstance(candidate_count, int)
                or isinstance(candidate_count, bool)
                or candidate_count != len(identity_symbols)
            ):
                warnings.append("universe_identity_candidate_count_mismatch")

            raw_scores = identity.get("scores_bp")
            raw_hash_symbols = identity.get("universe_hash_symbols")
            hash_symbols = identity_symbols
            if raw_hash_symbols is not None:
                if not isinstance(raw_hash_symbols, list) or any(
                    not isinstance(item, str) for item in raw_hash_symbols
                ):
                    warnings.append("universe_identity_hash_symbols_invalid")
                    hash_symbols = None
                else:
                    hash_symbols = tuple(raw_hash_symbols)
                    if hash_symbols != tuple(dict.fromkeys(hash_symbols)):
                        warnings.append("universe_identity_hash_symbols_not_unique")
                    if identity_symbols is not None and set(hash_symbols) != set(identity_symbols):
                        warnings.append("universe_identity_hash_symbols_mismatch")
            scores: list[int] | None = None
            if isinstance(raw_scores, list) and all(
                isinstance(item, int)
                and not isinstance(item, bool)
                and 0 <= item <= 10000
                for item in raw_scores
            ):
                scores = list(raw_scores)
            if raw_scores is None:
                warnings.append("universe_identity_scores_missing_for_hash_reconstruction")
            elif scores is None:
                warnings.append("universe_identity_scores_invalid")
            elif hash_symbols is None or len(scores) != len(hash_symbols):
                warnings.append("universe_identity_scores_symbols_length_mismatch")
            elif _sha256_json(
                {
                    "schema_version": PIT_UNIVERSE_IDENTITY_SCHEMA_VERSION,
                    "symbols": list(hash_symbols),
                    "scores_bp": scores,
                }
            ) != identity_hash:
                warnings.append("universe_identity_hash_reconstruction_mismatch")

            if identity.get("source_id") != "daily_prices":
                warnings.append("universe_identity_source_unsupported")

        if symbols is None and identity_symbols is not None:
            symbols = identity_symbols
        if symbols is None:
            return (), list(dict.fromkeys(warnings))
        if identity_symbols is not None and symbols != identity_symbols:
            warnings.append("universe_identity_symbols_mismatch")
        if inline_symbols is not None and _sha256_json(list(symbols)) != universe_hash:
            warnings.append("universe_hash_mismatch")
        if symbols != tuple(sorted(set(symbols))):
            warnings.append("universe_symbols_not_sorted_unique")
        if set(symbols) != set(row_symbols):
            warnings.append("universe_symbols_row_coverage_mismatch")
        return symbols, list(dict.fromkeys(warnings))

    def _load_and_verify_taxonomy(
        self,
        artifact_path: Path,
        *,
        universe_hash: str,
        rows: Sequence[Mapping[str, object]],
        as_of_date: date,
        decision_at: datetime,
    ) -> _TaxonomyVerification:
        """依 schema dispatch v2 相容路徑或 market-scoped v3 路徑。"""

        candidates = list(self.taxonomy_identity_paths)
        auto = artifact_path.parent.parent / "metadata" / "taxonomy_identity.json"
        if auto not in candidates:
            candidates.append(auto)
        identity_path = next((path for path in candidates if path.is_file()), None)
        if identity_path is None:
            return _TaxonomyVerification(
                mapping={},
                mapping_by_market={},
                security_by_symbol={},
                security_eligibility_by_symbol={},
                security_exclusion_reason_by_symbol={},
                taxonomy_version=None,
                taxonomy_version_by_market={},
                lineage={
                    "taxonomy_identity_path": None,
                    "taxonomy_status": "missing",
                    "taxonomy_verified": False,
                },
                warnings=["membership_taxonomy_identity_missing"],
                verified=False,
            )
        try:
            raw_identity = _loads_no_duplicate_keys(
                identity_path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            return _TaxonomyVerification(
                mapping={},
                mapping_by_market={},
                security_by_symbol={},
                security_eligibility_by_symbol={},
                security_exclusion_reason_by_symbol={},
                taxonomy_version=None,
                taxonomy_version_by_market={},
                lineage={
                    "taxonomy_identity_path": str(identity_path),
                    "taxonomy_status": "missing",
                    "taxonomy_verified": False,
                },
                warnings=[f"membership_taxonomy_identity_unreadable:{identity_path}"],
                verified=False,
            )
        if isinstance(raw_identity, Mapping) and raw_identity.get(
            "schema_version"
        ) in {
            PIT_TAXONOMY_IDENTITY_V3_SCHEMA_VERSION,
            PIT_TAXONOMY_IDENTITY_V4_SCHEMA_VERSION,
        }:
            return self._load_and_verify_taxonomy_v3(
                artifact_path,
                identity_path=identity_path,
                identity=dict(raw_identity),
                universe_hash=universe_hash,
                rows=rows,
                as_of_date=as_of_date,
                decision_at=decision_at,
                split_contract=(
                    raw_identity.get("schema_version")
                    == PIT_TAXONOMY_IDENTITY_V4_SCHEMA_VERSION
                ),
            )
        return self._legacy_taxonomy_verification(
            self._load_and_verify_taxonomy_v2(
                artifact_path,
                universe_hash=universe_hash,
                rows=rows,
                as_of_date=as_of_date,
                decision_at=decision_at,
            )
        )

    def _legacy_taxonomy_verification(
        self,
        value: tuple[
            dict[str, str],
            dict[str, str],
            str | None,
            dict[str, object],
            list[str],
            bool,
        ],
    ) -> _TaxonomyVerification:
        mapping, security, version, lineage, warnings, verified = value
        eligible = {
            symbol: security.get(symbol) in _COMMON_EQUITY_SECURITY_TYPES
            for symbol in security
        }
        reasons = {
            symbol: "official_security_type_unsupported"
            for symbol, is_eligible in eligible.items()
            if not is_eligible
        }
        return _TaxonomyVerification(
            mapping=mapping,
            mapping_by_market={"*": dict(mapping)},
            security_by_symbol=security,
            security_eligibility_by_symbol=eligible,
            security_exclusion_reason_by_symbol=reasons,
            taxonomy_version=version,
            taxonomy_version_by_market={"*": version} if version else {},
            lineage=lineage,
            warnings=warnings,
            verified=verified,
        )

    def _load_and_verify_taxonomy_v2(
        self,
        artifact_path: Path,
        *,
        universe_hash: str,
        rows: Sequence[Mapping[str, object]],
        as_of_date: date,
        decision_at: datetime,
    ) -> tuple[
        dict[str, str],
        dict[str, str],
        str | None,
        dict[str, object],
        list[str],
        bool,
    ]:
        """讀取獨立、版本化 taxonomy identity；不以 current map 補歷史。

        Identity 不能只靠自報的 ``source_hash`` 或 ``mapping_hash`` 通過。
        它必須指向一份可讀的、版本固定的 taxonomy source bytes，reader 會
        重新計算 bytes hash，並把 classification／security 的來源識別一併
        帶入 lineage。``available_at`` 也和 ``effective_from`` 分開驗證，
        避免事後產生的分類檔被回填成當時已知。
        """

        candidates = list(self.taxonomy_identity_paths)
        auto = artifact_path.parent.parent / "metadata" / "taxonomy_identity.json"
        if auto not in candidates:
            candidates.append(auto)
        identity_path = next((path for path in candidates if path.is_file()), None)
        base_lineage: dict[str, object] = {
            "taxonomy_identity_path": str(identity_path) if identity_path else None,
            "taxonomy_status": "missing",
            "taxonomy_verified": False,
        }
        if identity_path is None:
            return {}, {}, None, base_lineage, ["membership_taxonomy_identity_missing"], False

        warnings: list[str] = []
        try:
            raw_identity = _loads_no_duplicate_keys(
                identity_path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            return (
                {},
                {},
                None,
                {**base_lineage, "taxonomy_status": "missing"},
                [f"membership_taxonomy_identity_unreadable:{identity_path}"],
                False,
            )
        if not isinstance(raw_identity, Mapping):
            return (
                {},
                {},
                None,
                {**base_lineage, "taxonomy_status": "missing"},
                ["membership_taxonomy_identity_schema_invalid"],
                False,
            )
        identity = dict(raw_identity)
        if (
            set(identity) != _TAXONOMY_REQUIRED_FIELDS
            or identity.get("schema_version") != PIT_TAXONOMY_IDENTITY_SCHEMA_VERSION
        ):
            warnings.append("membership_taxonomy_identity_schema_invalid")

        classification_version = identity.get("classification_version")
        if not isinstance(classification_version, str) or not classification_version.strip():
            warnings.append("membership_taxonomy_classification_version_missing")
            classification_text: str | None = None
        else:
            classification_text = classification_version.strip()
            if classification_text not in _SUPPORTED_PIT_CLASSIFICATION_VERSIONS:
                warnings.append(
                    "membership_taxonomy_classification_version_unsupported"
                )
            if (
                self.expected_classification_version is not None
                and classification_text != self.expected_classification_version
            ):
                warnings.append(
                    "membership_taxonomy_classification_version_mismatch:"
                    f"expected={self.expected_classification_version}:actual={classification_text}"
                )

        source_hash = identity.get("source_hash")
        if not _is_sha256(source_hash):
            warnings.append("membership_taxonomy_source_hash_invalid")
        source_id = identity.get("source_id")
        source_version = identity.get("source_version")
        if not isinstance(source_id, str) or not source_id.strip():
            warnings.append("membership_taxonomy_source_id_missing")
            source_id_text: str | None = None
        else:
            source_id_text = source_id.strip()
        if not isinstance(source_version, str) or not source_version.strip():
            warnings.append("membership_taxonomy_source_version_missing")
            source_version_text: str | None = None
        else:
            source_version_text = source_version.strip()

        source_path_value = identity.get("source_path")
        taxonomy_source_path: Path | None = None
        if not isinstance(source_path_value, str) or not source_path_value.strip():
            warnings.append("membership_taxonomy_source_path_missing")
        else:
            taxonomy_source_path = Path(source_path_value.strip()).expanduser()
            if not taxonomy_source_path.is_absolute():
                taxonomy_source_path = identity_path.parent / taxonomy_source_path
            taxonomy_source_path = taxonomy_source_path.resolve()

        available_at: datetime | None = None
        try:
            available_at = _parse_aware_datetime(
                identity.get("available_at"), "taxonomy.available_at"
            )
        except PITMembershipReaderError:
            warnings.append("membership_taxonomy_available_at_invalid")
        if available_at is not None and available_at > decision_at:
            warnings.append("membership_taxonomy_available_at_after_decision")

        source_roles: dict[str, str | None] = {}
        for field_name in (
            "classification_source_id",
            "classification_source_version",
            "security_source_id",
            "security_source_version",
        ):
            value = identity.get(field_name)
            if not isinstance(value, str) or not value.strip():
                warnings.append(f"membership_taxonomy_{field_name}_missing")
                source_roles[field_name] = None
            else:
                source_roles[field_name] = value.strip()

        effective_from: date | None = None
        try:
            effective_from = _required_date(identity.get("effective_from"), "taxonomy.effective_from")
        except PITMembershipReaderError:
            warnings.append("membership_taxonomy_effective_from_invalid")
        if effective_from is not None and effective_from > as_of_date:
            warnings.append("membership_taxonomy_not_effective_at_as_of")

        if identity.get("universe_hash") != universe_hash:
            warnings.append("membership_taxonomy_universe_hash_mismatch")

        raw_symbols = identity.get("symbols")
        identity_symbols: tuple[str, ...] | None = None
        if not isinstance(raw_symbols, list) or any(not isinstance(item, str) for item in raw_symbols):
            warnings.append("membership_taxonomy_symbols_invalid")
        else:
            identity_symbols = tuple(raw_symbols)
            if identity_symbols != tuple(sorted(set(identity_symbols))):
                warnings.append("membership_taxonomy_symbols_not_sorted_unique")
            row_symbols = tuple(sorted(str(row["symbol"]) for row in rows))
            if identity_symbols != row_symbols:
                warnings.append("membership_taxonomy_partial_denominator")

        raw_mapping = identity.get("mapping")
        mapping: dict[str, str] = {}
        if not isinstance(raw_mapping, Mapping) or any(
            not isinstance(key, str)
            or _SECTOR_RE.fullmatch(key) is None
            or not isinstance(value, str)
            or not value.strip()
            for key, value in (raw_mapping.items() if isinstance(raw_mapping, Mapping) else ())
        ):
            warnings.append("membership_taxonomy_mapping_invalid")
        else:
            mapping = {str(key): str(value).strip() for key, value in raw_mapping.items()}

        raw_security = identity.get("security_type_by_symbol")
        security_by_symbol: dict[str, str] = {}
        if not isinstance(raw_security, Mapping) or any(
            not isinstance(key, str) or not isinstance(value, str) or not value.strip()
            for key, value in (raw_security.items() if isinstance(raw_security, Mapping) else ())
        ):
            warnings.append("membership_taxonomy_security_type_mapping_invalid")
        else:
            security_by_symbol = {
                str(key): str(value).strip() for key, value in raw_security.items()
            }

        source_payload: Mapping[str, object] | None = None
        source_actual_hash: str | None = None
        if taxonomy_source_path is None or not taxonomy_source_path.is_file():
            warnings.append("membership_taxonomy_source_missing")
        else:
            source_actual_hash = _sha256_file(taxonomy_source_path)
            if _is_sha256(source_hash) and source_actual_hash != source_hash:
                warnings.append("membership_taxonomy_source_hash_mismatch")
            try:
                raw_source = _loads_no_duplicate_keys(
                    taxonomy_source_path.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                warnings.append("membership_taxonomy_source_unreadable")
            else:
                if not isinstance(raw_source, Mapping):
                    warnings.append("membership_taxonomy_source_schema_invalid")
                else:
                    source_payload = raw_source
                    if (
                        set(source_payload) != _TAXONOMY_SOURCE_REQUIRED_FIELDS
                        or source_payload.get("schema_version")
                        != PIT_TAXONOMY_SOURCE_SCHEMA_VERSION
                    ):
                        warnings.append("membership_taxonomy_source_schema_invalid")

        source_compare_fields = (
            "classification_version",
            "source_id",
            "source_version",
            "available_at",
            "effective_from",
            "classification_source_id",
            "classification_source_version",
            "security_source_id",
            "security_source_version",
        )
        if source_payload is not None:
            for field_name in source_compare_fields:
                if source_payload.get(field_name) != identity.get(field_name):
                    warnings.append(
                        f"membership_taxonomy_source_{field_name}_mismatch"
                    )
            if source_payload.get("mapping") != raw_mapping:
                warnings.append("membership_taxonomy_source_mapping_mismatch")
            if source_payload.get("security_type_by_symbol") != raw_security:
                warnings.append("membership_taxonomy_source_security_mapping_mismatch")

            source_classification = source_payload.get("classification_version")
            if not isinstance(source_classification, str) or not source_classification.strip():
                warnings.append("membership_taxonomy_classification_source_untraceable")
            source_security_id = source_payload.get("security_source_id")
            source_security_version = source_payload.get("security_source_version")
            if not (
                isinstance(source_security_id, str)
                and source_security_id.strip()
                and isinstance(source_security_version, str)
                and source_security_version.strip()
            ):
                warnings.append("membership_taxonomy_security_source_untraceable")

        row_symbols_set = {str(row["symbol"]) for row in rows}
        security_missing = sorted(row_symbols_set - set(security_by_symbol))
        if security_missing:
            warnings.append("membership_taxonomy_security_type_missing")
        unsupported_security = sorted(
            symbol
            for symbol in row_symbols_set & set(security_by_symbol)
            if security_by_symbol[symbol] not in _COMMON_EQUITY_SECURITY_TYPES
        )
        if unsupported_security:
            warnings.append("membership_taxonomy_security_type_unsupported")
        if security_missing or unsupported_security:
            warnings.append("membership_taxonomy_partial_denominator")

        mapping_hash = identity.get("mapping_hash")
        body = dict(identity)
        body.pop("mapping_hash", None)
        if not _is_sha256(mapping_hash):
            warnings.append("membership_taxonomy_mapping_hash_invalid")
        elif _sha256_json(body) != mapping_hash:
            warnings.append("membership_taxonomy_mapping_hash_mismatch")

        unsupported_codes = sorted(
            {
                str(row["sector_id"])
                for row in rows
                if str(row["sector_id"]) not in mapping
            }
        )
        if unsupported_codes:
            warnings.extend(
                f"membership_taxonomy_code_unsupported:{code}"
                for code in unsupported_codes
            )

        row_classifications = {
            str(row["classification_version"])
            for row in rows
            if row.get("classification_version") not in (None, "")
        }
        if classification_text is not None and any(
            value != classification_text for value in row_classifications
        ):
            warnings.append("membership_taxonomy_row_classification_version_mismatch")

        warnings = list(dict.fromkeys(warnings))
        verified = not warnings and bool(mapping) and bool(security_by_symbol)
        lineage = {
            **base_lineage,
            "taxonomy_status": "verified" if verified else "partial",
            "taxonomy_verified": verified,
            "classification_version": classification_text,
            "taxonomy_source_id": source_id if isinstance(source_id, str) else None,
            "taxonomy_source_version": (
                source_version_text
            ),
            "taxonomy_source_hash": source_hash if isinstance(source_hash, str) else None,
            "taxonomy_source_actual_hash": source_actual_hash,
            "taxonomy_source_path": str(taxonomy_source_path) if taxonomy_source_path else None,
            "taxonomy_available_at": (
                available_at.isoformat() if available_at is not None else None
            ),
            "taxonomy_effective_from": (
                effective_from.isoformat() if effective_from is not None else None
            ),
            "taxonomy_mapping_hash": mapping_hash if isinstance(mapping_hash, str) else None,
            "classification_source_id": source_roles["classification_source_id"],
            "classification_source_version": source_roles["classification_source_version"],
            "security_source_id": source_roles["security_source_id"],
            "security_source_version": source_roles["security_source_version"],
            "taxonomy_covered_symbol_count": len(
                set(identity_symbols or ()) & row_symbols_set
            ),
            "taxonomy_row_symbol_count": len(row_symbols_set),
        }
        return (
            mapping,
            security_by_symbol,
            classification_text,
            lineage,
            warnings,
            verified,
        )

    def _load_and_verify_taxonomy_v3(
        self,
        artifact_path: Path,
        *,
        identity_path: Path,
        identity: Mapping[str, object],
        universe_hash: str,
        rows: Sequence[Mapping[str, object]],
        as_of_date: date,
        decision_at: datetime,
        split_contract: bool = False,
    ) -> _TaxonomyVerification:
        """重新驗證 market-scoped v3 identity 及每個官方 raw component。"""

        warnings: list[str] = []
        row_symbols = tuple(sorted(str(row["symbol"]) for row in rows))
        row_symbol_set = set(row_symbols)
        base_lineage: dict[str, object] = {
            "taxonomy_identity_path": str(identity_path),
            "taxonomy_schema_version": (
                PIT_TAXONOMY_IDENTITY_V4_SCHEMA_VERSION
                if split_contract
                else PIT_TAXONOMY_IDENTITY_V3_SCHEMA_VERSION
            ),
            "taxonomy_status": "partial",
            "taxonomy_verified": False,
        }
        required_identity_fields = (
            _TAXONOMY_V4_REQUIRED_FIELDS
            if split_contract
            else _TAXONOMY_V3_REQUIRED_FIELDS
        )
        if set(identity) != required_identity_fields:
            warnings.append("membership_taxonomy_identity_schema_invalid")

        split_validation: Mapping[str, object] = {}
        if split_contract:
            try:
                from data_module.pit_taxonomy_source_producer import (
                    validate_daily_pit_taxonomy_bundle,
                )

                split_validation = validate_daily_pit_taxonomy_bundle(
                    identity_path.parent.parent / "bundle_manifest.json",
                    decision_at=decision_at,
                    now=decision_at,
                )
            except Exception as error:  # noqa: BLE001 - source bytes remain fail-closed
                warnings.append(
                    "membership_split_scope_source_binding_invalid:"
                    + _one_line(error)
                )
            if (
                identity.get("scope_binding_schema_version")
                != PIT_TAXONOMY_SCOPE_BINDING_SCHEMA_VERSION
                or identity.get("taxonomy_coverage_complete") is not True
            ):
                warnings.append("membership_split_scope_taxonomy_coverage_invalid")
            if identity.get("inactive_security_overlay_by_symbol") != split_validation.get(
                "inactive_security_overlay_by_symbol"
            ):
                warnings.append("membership_split_inactive_security_overlay_binding_mismatch")

        source_id = _text_or_none(identity.get("source_id"), warnings, "membership_taxonomy_source_id_missing")
        source_version = _text_or_none(
            identity.get("source_version"), warnings, "membership_taxonomy_source_version_missing"
        )
        source_hash = identity.get("source_hash")
        if not _is_sha256(source_hash):
            warnings.append("membership_taxonomy_source_hash_invalid")
        available_at = _datetime_or_none(
            identity.get("available_at"), warnings, "membership_taxonomy_available_at_invalid"
        )
        if available_at is not None and available_at > decision_at:
            warnings.append("membership_taxonomy_available_at_after_decision")
        effective_from = _date_or_none(
            identity.get("effective_from"), warnings, "membership_taxonomy_effective_from_invalid"
        )
        if effective_from is not None and effective_from > as_of_date:
            warnings.append("membership_taxonomy_not_effective_at_as_of")
        if identity.get("universe_hash") != universe_hash:
            warnings.append("membership_taxonomy_universe_hash_mismatch")

        identity_symbols = _v3_symbol_list(identity.get("symbols"), warnings, "membership_taxonomy_symbols_invalid")
        if identity_symbols is not None:
            if identity_symbols != tuple(sorted(set(identity_symbols))):
                warnings.append("membership_taxonomy_symbols_not_sorted_unique")
            if identity_symbols != row_symbols:
                warnings.append("membership_taxonomy_partial_denominator")
        hash_symbols = _v3_symbol_list(
            identity.get("universe_hash_symbols"),
            warnings,
            "membership_taxonomy_universe_hash_symbols_invalid",
            require_sorted=False,
        )
        scores = identity.get("scores_bp")
        if not isinstance(scores, list) or any(
            isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 10000
            for item in scores
        ):
            warnings.append("membership_taxonomy_scores_invalid")
            score_values: list[int] = []
        else:
            score_values = [int(item) for item in scores]
        if hash_symbols is None or len(score_values) != len(hash_symbols):
            warnings.append("membership_taxonomy_scores_symbols_length_mismatch")
        elif _sha256_json(
            {
                "schema_version": PIT_UNIVERSE_IDENTITY_SCHEMA_VERSION,
                "symbols": list(hash_symbols),
                "scores_bp": score_values,
            }
        ) != universe_hash:
            warnings.append("membership_taxonomy_universe_hash_reconstruction_mismatch")
        if hash_symbols is not None and not split_contract and set(hash_symbols) != row_symbol_set:
            warnings.append("membership_taxonomy_universe_hash_symbols_mismatch")

        rank_order = _v3_symbol_list(
            identity.get("rank_order"), warnings, "membership_taxonomy_rank_order_invalid", require_sorted=False
        )
        if rank_order is not None and set(rank_order) != (
            set(hash_symbols) if split_contract and hash_symbols is not None else row_symbol_set
        ):
            warnings.append("membership_taxonomy_rank_order_partial_denominator")

        versions_value = identity.get("classification_version_by_market")
        versions = _v3_text_mapping(
            versions_value, warnings, "membership_taxonomy_classification_versions_invalid"
        )
        for version in versions.values():
            if version not in _SUPPORTED_PIT_CLASSIFICATION_VERSIONS and not version.startswith(
                "tw-industry-"
            ):
                warnings.append("membership_taxonomy_classification_version_unsupported")
            if self.expected_classification_version is not None and version != self.expected_classification_version:
                warnings.append(
                    "membership_taxonomy_classification_version_mismatch:"
                    f"expected={self.expected_classification_version}:actual={version}"
                )

        mapping_by_market = _v3_mapping_by_market(
            identity.get("mapping_by_market"), warnings
        )
        market_by_symbol = _v3_text_mapping(
            identity.get("market_by_symbol"), warnings, "membership_taxonomy_market_mapping_invalid"
        )
        if set(market_by_symbol) != row_symbol_set:
            warnings.append("membership_taxonomy_market_mapping_partial_denominator")
        if any(value not in _SUPPORTED_MARKETS for value in market_by_symbol.values()):
            warnings.append("membership_taxonomy_market_mapping_unsupported")

        security_by_symbol = _v3_text_mapping(
            identity.get("security_type_by_symbol"),
            warnings,
            "membership_taxonomy_security_type_mapping_invalid",
        )
        if set(security_by_symbol) != row_symbol_set:
            warnings.append("membership_taxonomy_security_type_partial_denominator")
        # v3 carries an explicit full-denominator eligibility projection.  A
        # known non-common instrument (for example TDR/ETF/warrant) is a
        # verified exclusion, not a missing denominator row; only an
        # unrecognised type remains a taxonomy blocker.
        known_excluded_security_types = frozenset(
            {
                "tdr",
                "etf",
                "etn",
                "warrant",
                "preferred_equity",
                "bond",
                "inactive_common_stock",
            }
        )
        unsupported_security = sorted(
            symbol
            for symbol in row_symbol_set & set(security_by_symbol)
            if security_by_symbol[symbol] not in _COMMON_EQUITY_SECURITY_TYPES
            and security_by_symbol[symbol] not in known_excluded_security_types
        )
        if unsupported_security:
            warnings.append("membership_taxonomy_security_type_unsupported")
            warnings.append("membership_taxonomy_partial_denominator")
        eligibility_value = identity.get("security_eligibility_by_symbol")
        eligibility_details = (
            {str(key): dict(value) for key, value in eligibility_value.items() if isinstance(value, Mapping)}
            if isinstance(eligibility_value, Mapping)
            else {}
        )
        if set(eligibility_details) != row_symbol_set:
            warnings.append("membership_taxonomy_security_eligibility_partial_denominator")
        eligibility_by_symbol: dict[str, bool] = {
            symbol: value.get("eligible") is True
            for symbol, value in eligibility_details.items()
        }
        exclusion_reasons: dict[str, str] = {}
        for symbol, value in eligibility_details.items():
            if value.get("eligible") is not True:
                reason = value.get("reason")
                if not isinstance(reason, str) or not reason.strip():
                    warnings.append(f"membership_taxonomy_exclusion_reason_missing:{symbol}")
                else:
                    exclusion_reasons[symbol] = reason.strip()
                    if reason.strip().startswith("unknown"):
                        warnings.append(f"membership_taxonomy_unknown_security:{symbol}")

        eligible_symbols = _v3_string_array(identity.get("eligible_symbols"), warnings, "membership_taxonomy_eligible_symbols_invalid")
        excluded_symbols = _v3_string_array(identity.get("excluded_by_security"), warnings, "membership_taxonomy_excluded_symbols_invalid")
        unknown_symbols = _v3_string_array(identity.get("unknown_symbols"), warnings, "membership_taxonomy_unknown_symbols_invalid")
        eligibility_sets = (set(eligible_symbols), set(excluded_symbols), set(unknown_symbols))
        if set().union(*eligibility_sets) != row_symbol_set:
            warnings.append("membership_taxonomy_security_projection_incomplete")
        if any(eligibility_sets[index] & eligibility_sets[other] for index in range(3) for other in range(index + 1, 3)):
            warnings.append("membership_taxonomy_security_projection_overlap")
        if set(eligible_symbols) != {symbol for symbol, value in eligibility_by_symbol.items() if value}:
            warnings.append("membership_taxonomy_eligible_projection_mismatch")
        if set(excluded_symbols) != {
            symbol for symbol, value in eligibility_by_symbol.items() if not value
        } - set(unknown_symbols):
            warnings.append("membership_taxonomy_excluded_projection_mismatch")
        if unknown_symbols:
            warnings.append("membership_taxonomy_unknown_security_present")

        license_scope = identity.get("license_scope")
        if not isinstance(license_scope, Mapping):
            warnings.append("membership_taxonomy_license_scope_missing")
        else:
            if license_scope.get("formal_acceptance_granted") is not True:
                warnings.append("membership_taxonomy_license_not_formally_accepted")

        # v3 source bytes and raw manifest are independently re-read.  The
        # identity cannot pass by merely self-declaring source_hashes.
        taxonomy_source_path = _v3_resolve_file(
            identity_path.parent, identity.get("source_path"), warnings, "membership_taxonomy_source_missing"
        )
        taxonomy_source_payload: Mapping[str, object] | None = None
        source_actual_hash = _sha256_file(taxonomy_source_path) if taxonomy_source_path else None
        if source_actual_hash != source_hash:
            warnings.append("membership_taxonomy_source_hash_mismatch")
        if taxonomy_source_path is not None:
            try:
                source_value = _loads_no_duplicate_keys(
                    taxonomy_source_path.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                warnings.append("membership_taxonomy_source_unreadable")
            else:
                if isinstance(source_value, Mapping):
                    taxonomy_source_payload = dict(source_value)
                else:
                    warnings.append("membership_taxonomy_source_schema_invalid")
        if taxonomy_source_payload is not None:
            expected_source_fields = (
                _TAXONOMY_SOURCE_V3_REQUIRED_FIELDS
                if split_contract
                else _TAXONOMY_SOURCE_V2_REQUIRED_FIELDS
            )
            expected_source_schema = (
                PIT_TAXONOMY_SOURCE_V3_SCHEMA_VERSION
                if split_contract
                else PIT_TAXONOMY_SOURCE_V2_SCHEMA_VERSION
            )
            if set(taxonomy_source_payload) != expected_source_fields or taxonomy_source_payload.get(
                "schema_version"
            ) != expected_source_schema:
                warnings.append("membership_taxonomy_source_schema_invalid")
            compare_fields: tuple[str, ...] = (
                "source_id",
                "source_version",
                "available_at",
                "effective_from",
                "universe_hash",
                "symbols",
                "universe_hash_symbols",
                "scores_bp",
                "rank_order",
                "mapping_by_market",
                "classification_sources_by_market",
                "security_sources_by_market",
                "market_by_symbol",
                "security_type_by_symbol",
                "security_eligibility_by_symbol",
                "eligible_symbols",
                "excluded_by_security",
                "unknown_symbols",
                "license_scope",
                "raw_manifest_path",
                "raw_manifest_hash",
            )
            if split_contract:
                compare_fields = (
                    *compare_fields,
                    *_SCOPE_BINDING_FIELDS,
                    "inactive_security_overlay_by_symbol",
                )
            for field_name in compare_fields:
                if taxonomy_source_payload.get(field_name) != identity.get(field_name):
                    warnings.append(f"membership_taxonomy_source_{field_name}_mismatch")

        raw_manifest_path = _v3_resolve_file(
            identity_path.parent, identity.get("raw_manifest_path"), warnings, "membership_taxonomy_raw_manifest_missing"
        )
        raw_manifest_payload: Mapping[str, object] | None = None
        raw_manifest_actual_hash = _sha256_file(raw_manifest_path) if raw_manifest_path else None
        if raw_manifest_actual_hash != identity.get("raw_manifest_hash"):
            warnings.append("membership_taxonomy_raw_manifest_hash_mismatch")
        raw_files_by_key: dict[tuple[str, str], dict[str, object]] = {}
        if raw_manifest_path is not None:
            try:
                raw_manifest_value = _loads_no_duplicate_keys(
                    raw_manifest_path.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                warnings.append("membership_taxonomy_raw_manifest_unreadable")
            else:
                if isinstance(raw_manifest_value, Mapping):
                    raw_manifest_payload = dict(raw_manifest_value)
                else:
                    warnings.append("membership_taxonomy_raw_manifest_schema_invalid")
        if raw_manifest_payload is not None:
            raw_body = dict(raw_manifest_payload)
            logical_hash = raw_body.pop("manifest_hash", None)
            if raw_manifest_payload.get("schema_version") != PIT_TAXONOMY_RAW_MANIFEST_SCHEMA_VERSION:
                warnings.append("membership_taxonomy_raw_manifest_schema_invalid")
            if not _is_sha256(logical_hash) or _sha256_json(raw_body) != logical_hash:
                warnings.append("membership_taxonomy_raw_manifest_logical_hash_mismatch")
            files_value = raw_manifest_payload.get("files")
            if not isinstance(files_value, list):
                warnings.append("membership_taxonomy_raw_manifest_files_invalid")
            else:
                bundle_root = identity_path.parent.parent
                for raw_file in files_value:
                    if not isinstance(raw_file, Mapping):
                        warnings.append("membership_taxonomy_raw_manifest_file_invalid")
                        continue
                    source_key = (
                        str(raw_file.get("source_id", "")),
                        str(raw_file.get("market_scope", "")),
                    )
                    path_value = raw_file.get("path")
                    candidate = _v3_resolve_file(bundle_root, path_value, warnings, "membership_taxonomy_raw_file_missing")
                    expected_raw_hash = raw_file.get("source_file_hash")
                    if candidate is None or not _is_sha256(expected_raw_hash) or _sha256_file(candidate) != expected_raw_hash:
                        warnings.append(f"membership_taxonomy_raw_file_hash_mismatch:{path_value}")
                    elif raw_file.get("content_bytes") != candidate.stat().st_size:
                        warnings.append(f"membership_taxonomy_raw_file_byte_count_mismatch:{path_value}")
                    raw_available = _datetime_or_none(
                        raw_file.get("available_at"), warnings, "membership_taxonomy_raw_available_at_invalid"
                    )
                    if raw_available is not None and (
                        raw_available > decision_at
                        or raw_available
                        >= datetime.combine(
                            as_of_date, time(8, 30), tzinfo=TAIPEI_TIMEZONE
                        )
                    ):
                        warnings.append(f"membership_taxonomy_raw_available_at_after_cutoff:{path_value}")
                    if source_key in raw_files_by_key:
                        warnings.append(f"membership_taxonomy_raw_manifest_duplicate:{source_key[0]}")
                    raw_files_by_key[source_key] = dict(raw_file)

        classification_sources = _v3_source_mapping(
            identity.get("classification_sources_by_market"), warnings, "membership_taxonomy_classification_sources_invalid"
        )
        security_sources = _v3_source_mapping(
            identity.get("security_sources_by_market"), warnings, "membership_taxonomy_security_sources_invalid"
        )
        mapping_flat: dict[str, str] = {}
        for market_mapping in mapping_by_market.values():
            for code, name in market_mapping.items():
                mapping_flat.setdefault(code, name)

        for market, source in classification_sources.items():
            component = raw_files_by_key.get((str(source.get("source_id", "")), market))
            if component is None:
                warnings.append(f"membership_taxonomy_classification_raw_missing:{market}")
                continue
            if source.get("source_file_hash") != component.get("source_file_hash") or source.get("path") != component.get("path"):
                warnings.append(f"membership_taxonomy_classification_raw_binding_mismatch:{market}")
            for field_name in (
                "source_version",
                "effective_from",
                "parser_version",
                "effective_date_basis",
                "effective_date_evidence",
            ):
                if field_name in source or field_name in component:
                    if source.get(field_name) != component.get(field_name):
                        warnings.append(
                            f"membership_taxonomy_classification_{field_name}_binding_mismatch:{market}"
                        )
            component_path = _v3_component_path(identity_path.parent.parent, component.get("path"))
            if component_path is None:
                continue
            try:
                component_payload = component_path.read_bytes()
            except OSError as error:
                warnings.append(
                    f"membership_taxonomy_classification_parse_failed:{market}:{_one_line(error)}"
                )
                continue
            effective_date_basis_value = source.get("effective_date_basis")
            effective_date_basis = (
                effective_date_basis_value
                if isinstance(effective_date_basis_value, str)
                else None
            )
            effective_date_evidence_value = source.get("effective_date_evidence")
            effective_date_evidence = (
                dict(effective_date_evidence_value)
                if isinstance(effective_date_evidence_value, Mapping)
                else None
            )
            classification_effective_from = _date_or_none(
                source.get("effective_from"),
                warnings,
                "membership_taxonomy_classification_effective_invalid",
            )
            if classification_effective_from is not None and classification_effective_from > as_of_date:
                warnings.append(
                    f"membership_taxonomy_classification_not_effective_at_as_of:{market}"
                )
            try:
                source_kind = source.get("source_kind")
                if source_kind == PIT_TAXONOMY_TWSE_B1212_COMPOSITE_SOURCE_KIND:
                    composite_payloads = _load_composite_classification_components(
                        bundle_root=identity_path.parent.parent,
                        market=market,
                        source=source,
                        raw_files_by_key=raw_files_by_key,
                        warnings=warnings,
                    )
                    if composite_payloads is None:
                        continue
                    parsed_definition = parse_official_twse_b1212_composite_classification_definition(
                        base_raw_payload=composite_payloads["base_definition"],
                        change_raw_payload=composite_payloads["change_notice"],
                        revision_history_raw_payload=composite_payloads["revision_history"],
                        current_regulation_raw_payload=composite_payloads["current_regulation"],
                        classification_version=str(versions.get(market, "")),
                        source_id=str(source.get("source_id", "")),
                        source_version=str(source.get("source_version", "")),
                        effective_from=classification_effective_from or as_of_date,
                        effective_date_basis=effective_date_basis,
                        effective_date_evidence=effective_date_evidence,
                        mapping=mapping_by_market.get(market, {}),
                        require_effective_date_evidence=True,
                    )
                else:
                    parsed_definition = parse_official_classification_definition(
                        component_payload,
                        market_scope=market,
                        classification_version=str(versions.get(market, "")),
                        source_id=str(source.get("source_id", "")),
                        source_version=str(source.get("source_version", "")),
                        effective_from=classification_effective_from or as_of_date,
                        effective_date_basis=effective_date_basis,
                        effective_date_evidence=effective_date_evidence,
                        require_effective_date_evidence=component_payload.startswith(b"%PDF"),
                    )
            except (OSError, OfficialTaxonomyDefinitionError, ValueError) as error:
                warnings.append(f"membership_taxonomy_classification_parse_failed:{market}:{_one_line(error)}")
            else:
                if parsed_definition.mapping != mapping_by_market.get(market, {}):
                    warnings.append(f"membership_taxonomy_classification_mapping_mismatch:{market}")
                if parsed_definition.source_id != source.get("source_id") or parsed_definition.source_version != source.get("source_version"):
                    warnings.append(f"membership_taxonomy_classification_identity_mismatch:{market}")
                if parsed_definition.parser_version != source.get("parser_version"):
                    warnings.append(f"membership_taxonomy_classification_parser_mismatch:{market}")

        records = []
        seen_security_rows: set[str] = set()
        for market, source in security_sources.items():
            component = raw_files_by_key.get((str(source.get("source_id", "")), market))
            if component is None:
                warnings.append(f"membership_taxonomy_security_raw_missing:{market}")
                continue
            if source.get("source_file_hash") != component.get("source_file_hash") or source.get("path") != component.get("path"):
                warnings.append(f"membership_taxonomy_security_raw_binding_mismatch:{market}")
            component_path = _v3_component_path(identity_path.parent.parent, component.get("path"))
            if component_path is None:
                continue
            try:
                parsed_records = parse_official_isin_security_source(
                    component_path.read_bytes(),
                    default_market_scope=market,
                )
            except (OSError, OfficialSecurityTypingError, ValueError) as error:
                warnings.append(f"membership_taxonomy_security_parse_failed:{market}:{_one_line(error)}")
                continue
            for record in parsed_records:
                if record.row_hash not in seen_security_rows:
                    records.append(record)
                    seen_security_rows.add(record.row_hash)
        inactive_overlay_value = (
            split_validation.get("inactive_security_overlay_by_symbol")
            if split_contract
            else None
        )
        inactive_overlay = (
            {
                str(key): dict(value)
                for key, value in inactive_overlay_value.items()
                if isinstance(value, Mapping)
            }
            if isinstance(inactive_overlay_value, Mapping)
            else {}
        )
        active_row_symbols = row_symbol_set - set(inactive_overlay)
        if active_row_symbols:
            try:
                expected_types, expected_eligibility, _ = build_security_evidence_map(
                    records,
                    expected_symbols=tuple(sorted(active_row_symbols)),
                    market_by_symbol={
                        symbol: market_by_symbol[symbol]
                        for symbol in sorted(active_row_symbols)
                        if symbol in market_by_symbol
                    },
                )
            except (OfficialSecurityTypingError, ValueError) as error:
                warnings.append(f"membership_taxonomy_security_revalidation_failed:{_one_line(error)}")
                expected_types = {}
                expected_eligibility = {}
        else:
            expected_types, expected_eligibility = {}, {}
        for symbol, overlay_binding in inactive_overlay.items():
            proof_value = overlay_binding.get("proof")
            if not isinstance(proof_value, Mapping):
                warnings.append(f"membership_taxonomy_inactive_security_proof_missing:{symbol}")
                continue
            expected_types[symbol] = "inactive_common_stock"
            expected_eligibility[symbol] = {
                "eligible": False,
                "reason": "official_security_termination_inactive_research_only",
                "security_type": "inactive_common_stock",
                "market_scope": market_by_symbol.get(symbol),
                "state": proof_value.get("state"),
                "proof_sha256": _sha256_json(dict(proof_value)),
            }
        if expected_types != security_by_symbol:
            warnings.append("membership_taxonomy_security_type_reverification_mismatch")
        for symbol, detail in expected_eligibility.items():
            actual = eligibility_details.get(symbol, {})
            if actual.get("eligible") is not detail.get("eligible"):
                warnings.append(f"membership_taxonomy_security_eligibility_mismatch:{symbol}")
            if actual.get("reason") != detail.get("reason"):
                warnings.append(f"membership_taxonomy_security_reason_mismatch:{symbol}")

        for row in rows:
            symbol = str(row["symbol"])
            market = str(row.get("market_scope") or "")
            if not market:
                # _normalize_rows already binds source market; the raw row does
                # not necessarily repeat it, so recover it from source registry
                # below through the declared market mapping when possible.
                market = market_by_symbol.get(symbol, "")
            if market_by_symbol.get(symbol) not in (None, market):
                warnings.append(f"membership_taxonomy_row_market_mismatch:{symbol}")
            if market not in mapping_by_market or str(row["sector_id"]) not in mapping_by_market.get(market, {}):
                warnings.append(f"membership_taxonomy_code_unsupported:{row['sector_id']}:{market}")
            row_version = row.get("classification_version")
            if row_version not in (None, "") and row_version != versions.get(market):
                warnings.append(f"membership_taxonomy_row_classification_version_mismatch:{symbol}")

        warnings = list(dict.fromkeys(warnings))
        verified = not warnings and bool(mapping_by_market) and bool(security_by_symbol)
        taxonomy_version_values = sorted(set(versions.values()))
        taxonomy_version = taxonomy_version_values[0] if len(taxonomy_version_values) == 1 else (
            "market-scoped:v4" if split_contract and versions else "market-scoped:v3" if versions else None
        )
        lineage = {
            **base_lineage,
            "taxonomy_status": "verified" if verified else "partial",
            "taxonomy_verified": verified,
            "classification_version": taxonomy_version,
            "classification_version_by_market": dict(versions),
            "taxonomy_source_id": source_id,
            "taxonomy_source_version": source_version,
            "taxonomy_source_hash": source_hash if isinstance(source_hash, str) else None,
            "taxonomy_source_actual_hash": source_actual_hash,
            "taxonomy_source_path": str(taxonomy_source_path) if taxonomy_source_path else None,
            "taxonomy_available_at": available_at.isoformat() if available_at else None,
            "taxonomy_effective_from": effective_from.isoformat() if effective_from else None,
            "taxonomy_mapping_hash": identity.get("mapping_hash"),
            "mapping_by_market": dict(mapping_by_market),
            "market_by_symbol": dict(market_by_symbol),
            "security_type_by_symbol": dict(security_by_symbol),
            "security_eligibility_by_symbol": dict(eligibility_by_symbol),
            "eligible_symbols": list(eligible_symbols),
            "excluded_by_security": list(excluded_symbols),
            "unknown_symbols": list(unknown_symbols),
            "raw_manifest_path": str(raw_manifest_path) if raw_manifest_path else None,
            "raw_manifest_hash": identity.get("raw_manifest_hash"),
            "license_scope": dict(license_scope) if isinstance(license_scope, Mapping) else None,
            "taxonomy_covered_symbol_count": len(row_symbol_set & set(identity_symbols or ())),
            "taxonomy_row_symbol_count": len(row_symbol_set),
        }
        if split_contract:
            lineage.update(
                {
                    "taxonomy_coverage_complete": split_validation.get(
                        "taxonomy_coverage_complete"
                    ) is True,
                    "rule_scope_compatible": split_validation.get(
                        "rule_scope_compatible"
                    ) is True,
                    "scope_diff": split_validation.get("scope_diff"),
                    "denominator_binding_verified": split_validation.get(
                        "denominator_binding_verified"
                    ) is True,
                    "rule_candidate_binding_verified": split_validation.get(
                        "rule_candidate_binding_verified"
                    ) is True,
                    "denominator_symbols_hash": split_validation.get(
                        "denominator_symbols_hash"
                    ),
                    "rule_candidate_symbols_hash": split_validation.get(
                        "rule_candidate_symbols_hash"
                    ),
                }
            )
        return _TaxonomyVerification(
            mapping=mapping_flat,
            mapping_by_market=dict(mapping_by_market),
            security_by_symbol=dict(security_by_symbol),
            security_eligibility_by_symbol=eligibility_by_symbol,
            security_exclusion_reason_by_symbol=exclusion_reasons,
            taxonomy_version=taxonomy_version,
            taxonomy_version_by_market=dict(versions),
            lineage=lineage,
            warnings=warnings,
            verified=verified,
        )

    def _verify_raw_sources(
        self,
        artifact_path: Path,
        sources: Sequence[Mapping[str, object]],
        *,
        rows: Sequence[Mapping[str, object]],
    ) -> tuple[list[dict[str, object]], list[str]]:
        roots = list(self.raw_roots)
        auto_root = artifact_path.parent.parent
        if auto_root.is_dir() and auto_root not in roots:
            roots.append(auto_root)
        files = _candidate_files(roots)
        lineage: list[dict[str, object]] = []
        warnings: list[str] = []
        rows_by_source: dict[str, list[Mapping[str, object]]] = {}
        for row in rows:
            rows_by_source.setdefault(str(row["source_id"]), []).append(row)
        for source in sources:
            source_id = str(source["source_id"])
            expected_hash = str(source["raw_hash"]).lower()
            matching_path: Path | None = None
            actual_hash: str | None = None
            for candidate in files:
                actual = _sha256_file(candidate)
                if actual == expected_hash:
                    matching_path = candidate
                    actual_hash = actual
                    break
            source_entry: dict[str, object] = {
                "source_id": source_id,
                "source_version": str(source["source_version"]),
                "market_scope": str(source["market"]),
                "license_id": str(source["license_id"]),
                "source_hash": str(source["source_hash"]),
                "raw_hash": expected_hash,
                "canonical_rows_hash": str(source["canonical_rows_hash"]),
                "source_registry_hash": str(source["source_registry_hash"]),
                "available_at": str(source["available_at"]),
                "effective_from": str(source["effective_from"]),
            }
            if matching_path is None:
                warnings.append(f"source_raw_hash_not_found:{source_id}")
                source_entry["raw_custody_path"] = None
                lineage.append(source_entry)
                continue
            try:
                raw = matching_path.read_bytes()
                canonical_hash, raw_rows = _canonical_official_rows_hash(raw, source_id)
            except (OSError, UnicodeError, json.JSONDecodeError, PITMembershipReaderError) as error:
                warnings.append(f"source_raw_parse_failed:{source_id}:{_one_line(error)}")
                source_entry["raw_custody_path"] = str(matching_path)
                lineage.append(source_entry)
                continue
            source_entry["raw_custody_path"] = str(matching_path)
            source_entry["raw_file_hash"] = actual_hash
            source_entry["raw_canonical_rows_hash"] = canonical_hash
            if canonical_hash != str(source["canonical_rows_hash"]):
                warnings.append(
                    f"source_canonical_rows_hash_mismatch:{source_id}:"
                    f"expected={source['canonical_rows_hash']}:actual={canonical_hash}"
                )
            raw_by_symbol = {symbol: sector for symbol, sector, _ in raw_rows}
            for row in rows_by_source.get(source_id, ()):
                symbol = str(row["symbol"])
                if symbol not in raw_by_symbol:
                    warnings.append(f"source_raw_symbol_missing:{source_id}:{symbol}")
                elif raw_by_symbol[symbol] != str(row["sector_id"]):
                    warnings.append(
                        f"source_raw_sector_mismatch:{source_id}:{symbol}:"
                        f"expected={row['sector_id']}:actual={raw_by_symbol[symbol]}"
                    )
            lineage.append(source_entry)
        return lineage, warnings

    def _verify_machine_raw_inputs(
        self,
        publication_path: Path,
        payload: Mapping[str, object],
        sources: Sequence[Mapping[str, object]],
    ) -> tuple[list[dict[str, object]], list[str]]:
        raw_inputs_value = payload.get("raw_inputs")
        if not isinstance(raw_inputs_value, list):
            return [], ["source_raw_inputs_missing"]
        by_source = {
            str(item.get("source_id")): item
            for item in raw_inputs_value
            if isinstance(item, Mapping)
        }
        lineage: list[dict[str, object]] = []
        warnings: list[str] = []
        for source in sources:
            source_id = str(source["source_id"])
            raw_input = by_source.get(source_id)
            if raw_input is None:
                warnings.append(f"source_raw_input_missing:{source_id}")
                continue
            relative = raw_input.get("path")
            if not isinstance(relative, str) or not relative.strip():
                warnings.append(f"source_raw_path_missing:{source_id}")
                continue
            candidate = (publication_path.parent / relative).resolve()
            expected = str(raw_input.get("content_sha256", "")).lower()
            actual = _sha256_file(candidate) if candidate.is_file() else None
            entry: dict[str, object] = {
                "source_id": source_id,
                "raw_custody_path": str(candidate),
                "raw_hash": expected,
                "raw_file_hash": actual,
                "source_hash": str(source["source_hash"]),
            }
            lineage.append(entry)
            if actual != expected:
                warnings.append(f"source_raw_hash_mismatch:{source_id}:expected={expected}:actual={actual}")
        return lineage, warnings

    def _select_scope_artifacts(
        self,
        candidates: Sequence[_ParsedArtifact],
        *,
        market_scope: str,
    ) -> list[_ParsedArtifact]:
        matching = [
            item
            for item in candidates
            if market_scope in item.artifact.market_scopes
        ]
        if not matching:
            return []
        identities: dict[str, list[_ParsedArtifact]] = {}
        for item in matching:
            scoped_rows = sorted(
                (
                    row.to_dict()
                    for row in item.rows
                    if row.market_scope == market_scope
                ),
                key=lambda value: (
                    str(value["symbol"]),
                    str(value["effective_from"]),
                    str(value["sector_id"]),
                ),
            )
            identities.setdefault(_sha256_json(scoped_rows), []).append(item)
        if len(identities) > 1:
            return []
        return [
            sorted(items, key=lambda item: str(item.artifact.path))[0]
            for items in identities.values()
        ]

    def _select_all_market_artifacts(
        self,
        candidates: Sequence[_ParsedArtifact],
    ) -> tuple[list[_ParsedArtifact], bool]:
        markets = sorted(
            {
                market
                for item in candidates
                for market in item.artifact.market_scopes
            }
        )
        selected: list[_ParsedArtifact] = []
        for market in markets:
            scoped = self._select_scope_artifacts(candidates, market_scope=market)
            if not scoped:
                return [], True
            selected.extend(scoped)
        unique: dict[Path, _ParsedArtifact] = {
            item.artifact.path: item for item in selected
        }
        return sorted(unique.values(), key=lambda item: str(item.artifact.path)), False

    def _lineage_many(
        self,
        selected_items: Sequence[_ParsedArtifact],
        rows: Sequence[PITMembershipRow],
        market_scope: str | None,
        *,
        as_of_date: date,
    ) -> dict[str, object]:
        if not selected_items:
            return {
                "reader_schema_version": PIT_MEMBERSHIP_READER_SCHEMA_VERSION,
                "as_of_date": as_of_date.isoformat(),
                "market_scope_requested": market_scope,
            }
        lineage = self._lineage(selected_items[0], rows, market_scope)
        artifacts = [item.artifact for item in selected_items]
        lineage.update(
            {
                "as_of_date": as_of_date.isoformat(),
                "artifact_count": len(artifacts),
                "artifact_paths": [str(item.path) for item in sorted(artifacts, key=lambda value: str(value.path))],
                "source_ids": sorted({source_id for item in artifacts for source_id in item.source_ids}),
                "source_versions": sorted({version for item in artifacts for version in item.source_versions}),
                "source_hashes": sorted({source_hash for item in artifacts for source_hash in item.source_hashes}),
                "market_scopes": sorted({market for item in artifacts for market in item.market_scopes}),
                "raw_custody_verified": all(item.raw_custody_verified for item in artifacts),
                "universe_verified": all(item.universe_verified for item in artifacts),
                "hash_verified": all(item.hash_verified for item in artifacts),
                "source_registry": [
                    dict(source)
                    for item in selected_items
                    for source in item.source_lineage
                ],
                "taxonomy_verified": all(
                    item.artifact.taxonomy_verified for item in selected_items
                ),
                "taxonomy_status": (
                    "verified"
                    if all(item.artifact.taxonomy_verified for item in selected_items)
                    else "partial"
                ),
                "taxonomy_identities": [
                    dict(item.taxonomy_lineage)
                    for item in selected_items
                    if item.taxonomy_lineage
                ],
                "classification_versions": sorted(
                    {
                        str(item.taxonomy_lineage.get("classification_version"))
                        for item in selected_items
                        if item.taxonomy_lineage.get("classification_version")
                    }
                    | {
                        row.classification_version
                        for row in rows
                        if row.classification_version
                    }
                ),
            }
        )
        if selected_items and selected_items[0].taxonomy_lineage:
            # Preserve the full per-market taxonomy list while exposing the
            # single-artifact path aliases expected by read-side callers.
            for key in (
                "taxonomy_identity_path",
                "taxonomy_source_path",
                "raw_manifest_path",
            ):
                value = selected_items[0].taxonomy_lineage.get(key)
                if value is not None:
                    lineage[key] = value
        return lineage

    def _lineage(
        self,
        selected: _ParsedArtifact,
        rows: Sequence[PITMembershipRow],
        market_scope: str | None,
    ) -> dict[str, object]:
        artifact = selected.artifact
        return {
            "reader_schema_version": PIT_MEMBERSHIP_READER_SCHEMA_VERSION,
            "artifact_path": str(artifact.path),
            "artifact_schema_version": artifact.artifact_schema_version,
            "manifest_schema_version": artifact.manifest_schema_version,
            "artifact_status": artifact.artifact_status,
            "status": "accepted" if artifact.artifact_status == "accepted" else "unavailable",
            "scope": artifact.scope,
            "coverage_start": artifact.coverage_start.isoformat(),
            "coverage_end": artifact.coverage_end.isoformat(),
            "as_of_date": rows[0].effective_from.isoformat() if rows else None,
            "market_scope_requested": market_scope,
            "market_scopes": list(artifact.market_scopes),
            "row_count": len(rows),
            "artifact_row_count": artifact.row_count,
            "rows_hash": artifact.rows_hash,
            "canonical_hash": artifact.canonical_hash,
            "universe_hash": artifact.universe_hash,
            "source_ids": list(artifact.source_ids),
            "source_versions": list(artifact.source_versions),
            "source_hashes": list(artifact.source_hashes),
            "raw_custody_verified": artifact.raw_custody_verified,
            "universe_verified": artifact.universe_verified,
            "hash_verified": artifact.hash_verified,
            "taxonomy_verified": artifact.taxonomy_verified,
            "taxonomy_status": (
                "verified" if artifact.taxonomy_verified else "partial"
            ),
            "taxonomy_identity": dict(selected.taxonomy_lineage),
            "classification_version": (
                selected.taxonomy_lineage.get("classification_version")
                or next(
                    (
                        row.classification_version
                        for row in rows
                        if row.classification_version
                    ),
                    None,
                )
            ),
            "available_at": sorted({row.available_at.isoformat() for row in rows}),
            "effective_from": sorted({row.effective_from.isoformat() for row in rows}),
            "effective_to": sorted(
                {row.effective_to.isoformat() for row in rows if row.effective_to is not None}
            ),
            "source_registry": [dict(item) for item in selected.source_lineage],
            "classification_versions": sorted(
                {row.classification_version for row in rows if row.classification_version}
            ),
            "security_types": sorted({row.security_type for row in rows if row.security_type}),
        }

    @staticmethod
    def _result(
        as_of_date: date,
        decision_at: datetime,
        *,
        status: str,
        quality: str,
        rows: Sequence[PITMembershipRow],
        warnings: Sequence[str],
        lineage: dict[str, object],
        artifact: PITMembershipArtifact | None = None,
    ) -> PITMembershipReadResult:
        return PITMembershipReadResult(
            as_of_date=as_of_date,
            decision_at=decision_at,
            status=status,
            quality=quality,
            rows=tuple(rows),
            warnings=tuple(dict.fromkeys(str(item) for item in warnings)),
            lineage=dict(lineage),
            artifact=artifact,
        )


def _read_json_payload(path: Path) -> dict[str, object]:
    try:
        if path.name.casefold().endswith(".jsonl.gz"):
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                records = [_loads_no_duplicate_keys(line) for line in stream if line.strip()]
            return _jsonl_to_envelope(records)
        if path.name.casefold().endswith(".jsonl"):
            records = [
                _loads_no_duplicate_keys(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            return _jsonl_to_envelope(records)
        value = _loads_no_duplicate_keys(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise PITMembershipReaderError("PIT artifact is unreadable") from error
    if not isinstance(value, dict):
        raise PITMembershipReaderError("PIT artifact must be an object")
    return value


def _jsonl_to_envelope(records: list[object]) -> dict[str, object]:
    if not records or not isinstance(records[0], Mapping):
        raise PITMembershipReaderError("PIT JSONL manifest header is invalid")
    header = records[0]
    if header.get("record_type") != "manifest":
        raise PITMembershipReaderError("PIT JSONL manifest header is invalid")
    rows: list[object] = []
    for record in records[1:]:
        if not isinstance(record, Mapping) or record.get("record_type") != "membership":
            raise PITMembershipReaderError("PIT JSONL membership record is invalid")
        rows.append(record.get("row"))
    return {
        "schema_version": header.get("schema_version"),
        "manifest": header.get("manifest"),
        "rows": rows,
    }


def _loads_no_duplicate_keys(raw: str) -> object:
    return json.loads(raw, object_pairs_hook=_reject_duplicate_keys)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _normalize_paths(value: Sequence[str | Path]) -> tuple[Path, ...]:
    if isinstance(value, (str, Path)):
        value = (value,)
    return tuple(Path(item).expanduser().resolve() for item in value)


def _config_paths(config: Any, plural_name: str, singular_name: str) -> tuple[str | Path, ...]:
    value = getattr(config, plural_name, None)
    if isinstance(value, (str, Path)):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(item for item in value if isinstance(item, (str, Path)))
    value = getattr(config, singular_name, None)
    return (value,) if isinstance(value, (str, Path)) else ()


def _candidate_files(roots: Sequence[Path]) -> tuple[Path, ...]:
    files: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if root.is_file():
            candidates: tuple[Path, ...] = (root,)
        elif root.is_dir():
            candidates = tuple(item for item in root.rglob("*") if item.is_file())
        else:
            candidates = ()
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved not in seen:
                seen.add(resolved)
                files.append(resolved)
    return tuple(sorted(files, key=str))


def _canonical_official_rows_hash(
    raw: bytes,
    source_id: str,
) -> tuple[str, tuple[tuple[str, str, date], ...]]:
    definition = next(
        (item for item in OFFICIAL_COMPANY_SOURCE_DEFINITIONS.values() if item.source_id == source_id),
        None,
    )
    if definition is None:
        raise PITMembershipReaderError(f"official source definition missing: {source_id}")
    try:
        payload = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise PITMembershipReaderError("official raw JSON parse failed") from error
    if not isinstance(payload, list) or not payload or any(not isinstance(item, Mapping) for item in payload):
        raise PITMembershipReaderError("official raw JSON must be a non-empty object array")
    first = payload[0]
    fields = tuple(sorted(str(key) for key in first))
    required = {definition.symbol_field, definition.sector_field, definition.publication_field}
    if not required.issubset(fields):
        raise PITMembershipReaderError("official raw schema is missing required fields")
    normalized: list[tuple[str, str, date]] = []
    seen: set[str] = set()
    for item in payload:
        item_fields = tuple(sorted(str(key) for key in item))
        if item_fields != fields:
            raise PITMembershipReaderError("official raw rows do not share one schema")
        symbol = _raw_symbol(item.get(definition.symbol_field))
        sector = _raw_sector(item.get(definition.sector_field))
        publication = _raw_official_date(item.get(definition.publication_field))
        if symbol in seen:
            raise PITMembershipReaderError(f"official raw duplicate symbol: {symbol}")
        seen.add(symbol)
        normalized.append((symbol, sector, publication))
    publication_dates = {item[2] for item in normalized}
    if len(publication_dates) != 1:
        raise PITMembershipReaderError("official raw publication dates are inconsistent")
    normalized.sort()
    canonical_hash = _sha256_json(
        {
            "schema_version": OFFICIAL_PROSPECTIVE_PIT_SOURCE_SCHEMA_VERSION,
            "dataset_id": definition.dataset_id,
            "rows": [
                {
                    "symbol": symbol,
                    "sector_id": sector,
                    "publication_date": publication.isoformat(),
                }
                for symbol, sector, publication in normalized
            ],
        }
    )
    return canonical_hash, tuple(normalized)


def _raw_symbol(value: object) -> str:
    if not isinstance(value, str):
        raise PITMembershipReaderError("official raw symbol must be text")
    symbol = value.strip()
    if _SYMBOL_RE.fullmatch(symbol) is None:
        raise PITMembershipReaderError(f"official raw symbol is invalid: {symbol}")
    return symbol


def _raw_sector(value: object) -> str:
    if not isinstance(value, str):
        raise PITMembershipReaderError("official raw sector must be text")
    sector = value.strip()
    if _SECTOR_RE.fullmatch(sector) is None or sector == "00":
        raise PITMembershipReaderError(f"official raw sector is invalid: {sector}")
    return sector


def _raw_official_date(value: object) -> date:
    if not isinstance(value, str):
        raise PITMembershipReaderError("official raw publication date must be text")
    text = value.strip().replace("/", "-")
    if re.fullmatch(r"[0-9]{7}", text):
        text = f"{int(text[:3]) + 1911:04d}-{text[3:5]}-{text[5:7]}"
    elif re.fullmatch(r"[0-9]{3}-[0-9]{2}-[0-9]{2}", text):
        text = f"{int(text[:3]) + 1911:04d}-{text[4:6]}-{text[7:9]}"
    elif re.fullmatch(r"[0-9]{8}", text):
        text = f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise PITMembershipReaderError("official raw publication date is invalid") from error


def _parse_aware_datetime(value: object, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise PITMembershipReaderError(f"{field_name} is invalid") from error
    else:
        raise PITMembershipReaderError(f"{field_name} must be a timezone-aware ISO timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PITMembershipReaderError(f"{field_name} must include timezone")
    return parsed.astimezone(TAIPEI_TIMEZONE)


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PITMembershipReaderError(f"{field_name} must be non-empty text")
    return value.strip()


def _required_date(value: object, field_name: str) -> date:
    if not isinstance(value, str):
        raise PITMembershipReaderError(f"{field_name} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise PITMembershipReaderError(f"{field_name} must be YYYY-MM-DD") from error
    if parsed.isoformat() != value:
        raise PITMembershipReaderError(f"{field_name} must be YYYY-MM-DD")
    return parsed


def _required_sha256(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise PITMembershipReaderError(f"{field_name} must be sha256")
    return value


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _sha256_json(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1_048_576), b""):
                digest.update(chunk)
    except OSError:
        return None
    return "sha256:" + digest.hexdigest()


def _materialize_rows(
    rows: Sequence[Mapping[str, object]],
    source_map: Mapping[tuple[str, str, str], Mapping[str, object]],
    *,
    taxonomy_mapping: Mapping[str, str] | None = None,
    taxonomy_mapping_by_market: Mapping[str, Mapping[str, str]] | None = None,
    taxonomy_security_by_symbol: Mapping[str, str] | None = None,
    taxonomy_eligibility_by_symbol: Mapping[str, bool] | None = None,
    taxonomy_exclusion_reason_by_symbol: Mapping[str, str] | None = None,
    taxonomy_version: str | None = None,
    taxonomy_version_by_market: Mapping[str, str] | None = None,
) -> tuple[PITMembershipRow, ...]:
    materialized: list[PITMembershipRow] = []
    taxonomy_mapping = taxonomy_mapping or {}
    taxonomy_mapping_by_market = taxonomy_mapping_by_market or {}
    taxonomy_security_by_symbol = taxonomy_security_by_symbol or {}
    taxonomy_eligibility_by_symbol = taxonomy_eligibility_by_symbol or {}
    taxonomy_exclusion_reason_by_symbol = taxonomy_exclusion_reason_by_symbol or {}
    taxonomy_version_by_market = taxonomy_version_by_market or {}
    for row in rows:
        key = (str(row["source_id"]), str(row["license_id"]), str(row["source_hash"]))
        source = source_map.get(key, {})
        available_at = _parse_aware_datetime(row["available_at"], "row.available_at")
        effective_from = _required_date(row["effective_from"], "row.effective_from")
        effective_to_value = row.get("effective_to")
        effective_to = (
            None
            if effective_to_value in (None, "")
            else _required_date(effective_to_value, "row.effective_to")
        )
        market_scope = str(source.get("market", row.get("market_scope", "")))
        symbol = str(row["symbol"])
        market_mapping = taxonomy_mapping_by_market.get(market_scope)
        if market_mapping is None:
            market_mapping = taxonomy_mapping_by_market.get("*")
        if market_mapping is None:
            market_mapping = taxonomy_mapping
        security_type = (
            str(row["security_type"])
            if row.get("security_type") not in (None, "")
            else taxonomy_security_by_symbol.get(symbol)
        )
        eligible = taxonomy_eligibility_by_symbol.get(symbol, True)
        version = taxonomy_version_by_market.get(market_scope, taxonomy_version)
        materialized.append(
            PITMembershipRow(
                symbol=symbol,
                sector_id=str(row["sector_id"]),
                market_scope=market_scope,
                available_at=available_at,
                effective_from=effective_from,
                effective_to=effective_to,
                status=str(row["status"]),
                source_id=str(row["source_id"]),
                source_version=str(source.get("source_version", "")),
                license_id=str(row["license_id"]),
                source_hash=str(row["source_hash"]),
                classification_version=(
                    str(row["classification_version"])
                    if row.get("classification_version") not in (None, "")
                    else version
                ),
                security_type=security_type,
                industry_category=market_mapping.get(str(row["sector_id"])),
                security_eligible=bool(eligible),
                security_exclusion_reason=taxonomy_exclusion_reason_by_symbol.get(symbol),
            )
        )
    return tuple(materialized)


def _text_or_none(value: object, warnings: list[str], warning_name: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        warnings.append(warning_name)
        return None
    return value.strip()


def _datetime_or_none(
    value: object,
    warnings: list[str],
    warning_name: str,
) -> datetime | None:
    try:
        return _parse_aware_datetime(value, warning_name)
    except PITMembershipReaderError:
        warnings.append(warning_name)
        return None


def _date_or_none(
    value: object,
    warnings: list[str],
    warning_name: str,
) -> date | None:
    try:
        return _required_date(value, warning_name)
    except PITMembershipReaderError:
        warnings.append(warning_name)
        return None


def _v3_symbol_list(
    value: object,
    warnings: list[str],
    warning_name: str,
    *,
    require_sorted: bool = True,
) -> tuple[str, ...] | None:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or _SYMBOL_RE.fullmatch(item) is None for item in value
    ):
        warnings.append(warning_name)
        return None
    result = tuple(str(item) for item in value)
    if len(result) != len(set(result)):
        warnings.append(warning_name + ":duplicate")
    if require_sorted and result != tuple(sorted(result)):
        warnings.append(warning_name + ":not_sorted")
    return result


def _v3_string_array(value: object, warnings: list[str], warning_name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        warnings.append(warning_name)
        return []
    result = [str(item) for item in value]
    if result != sorted(set(result)):
        warnings.append(warning_name + ":not_sorted_unique")
    return result


def _v3_text_mapping(
    value: object,
    warnings: list[str],
    warning_name: str,
) -> dict[str, str]:
    if not isinstance(value, Mapping) or any(
        not isinstance(key, str) or not isinstance(item, str) or not item.strip()
        for key, item in (value.items() if isinstance(value, Mapping) else ())
    ):
        warnings.append(warning_name)
        return {}
    return {str(key): str(item).strip() for key, item in value.items()}


def _v3_mapping_by_market(
    value: object,
    warnings: list[str],
) -> dict[str, dict[str, str]]:
    if not isinstance(value, Mapping):
        warnings.append("membership_taxonomy_mapping_by_market_invalid")
        return {}
    result: dict[str, dict[str, str]] = {}
    for market, mapping in value.items():
        if not isinstance(market, str) or market not in _SUPPORTED_MARKETS:
            warnings.append("membership_taxonomy_mapping_market_invalid")
            continue
        if not isinstance(mapping, Mapping) or any(
            not isinstance(code, str)
            or _SECTOR_RE.fullmatch(code) is None
            or code == "00"
            or not isinstance(name, str)
            or not name.strip()
            for code, name in (mapping.items() if isinstance(mapping, Mapping) else ())
        ):
            warnings.append(f"membership_taxonomy_mapping_invalid:{market}")
            continue
        result[market] = {
            str(code): str(name).strip() for code, name in sorted(mapping.items())
        }
    return result


def _v3_source_mapping(
    value: object,
    warnings: list[str],
    warning_name: str,
) -> dict[str, dict[str, object]]:
    if not isinstance(value, Mapping):
        warnings.append(warning_name)
        return {}
    result: dict[str, dict[str, object]] = {}
    for market, item in value.items():
        if not isinstance(market, str) or not isinstance(item, Mapping):
            warnings.append(warning_name)
            continue
        result[market] = {str(key): value for key, value in item.items()}
    return result


def _v3_resolve_file(
    base: Path,
    value: object,
    warnings: list[str],
    warning_name: str,
) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        warnings.append(warning_name)
        return None
    candidate = Path(value.strip()).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    try:
        candidate = candidate.resolve()
        candidate.relative_to(base.resolve())
    except (OSError, ValueError):
        warnings.append(warning_name)
        return None
    if not candidate.is_file():
        warnings.append(warning_name)
        return None
    return candidate


def _v3_component_path(base: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = Path(value.strip())
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (base / candidate).resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError:
        return None
    return resolved if resolved.is_file() else None


def _load_composite_classification_components(
    *,
    bundle_root: Path,
    market: str,
    source: Mapping[str, object],
    raw_files_by_key: Mapping[tuple[str, str], Mapping[str, object]],
    warnings: list[str],
) -> dict[str, bytes] | None:
    """從 manifest 的四個真實 raw component 重新組合 TWSE definition。

    Composite 的 primary classification entry 是 B12.00 base PDF；其餘三個
    component 以獨立 raw-manifest entry 保存。這裡不接受 source lineage
    自稱的 hash 或 derived aggregate，而是逐一找 entry、讀檔、驗 hash，
    再交給 composite adapter 解析。
    """

    component_paths = source.get("component_raw_paths")
    if not isinstance(component_paths, Mapping) or set(component_paths) != set(
        _TWSE_B1212_COMPOSITE_COMPONENTS
    ):
        warnings.append(f"membership_taxonomy_classification_component_paths_invalid:{market}")
        return None
    lineage = source.get("source_lineage")
    lineage_components = lineage.get("components") if isinstance(lineage, Mapping) else None
    if not isinstance(lineage_components, Mapping) or set(lineage_components) != set(
        _TWSE_B1212_COMPOSITE_COMPONENTS
    ):
        warnings.append(f"membership_taxonomy_classification_component_lineage_invalid:{market}")
        return None

    source_id = str(source.get("source_id", ""))
    result: dict[str, bytes] = {}
    actual_component_times: dict[str, datetime] = {}
    for component_name in _TWSE_B1212_COMPOSITE_COMPONENTS:
        component_source_id = (
            source_id
            if component_name == "base_definition"
            else f"{source_id}:component:{component_name}"
        )
        entry = raw_files_by_key.get((component_source_id, market))
        if entry is None:
            warnings.append(
                f"membership_taxonomy_classification_component_raw_missing:{market}:{component_name}"
            )
            continue
        expected_path = component_paths.get(component_name)
        actual_path = entry.get("path")
        if not isinstance(expected_path, str) or actual_path != expected_path:
            warnings.append(
                f"membership_taxonomy_classification_component_path_mismatch:{market}:{component_name}"
            )
            continue
        if component_name == "base_definition" and actual_path != source.get("path"):
            warnings.append(
                f"membership_taxonomy_classification_component_base_path_mismatch:{market}"
            )
        if component_name == "base_definition" and (
            entry.get("source_file_hash") != source.get("source_file_hash")
            or entry.get("content_bytes") != source.get("content_bytes")
            or entry.get("http") != source.get("http")
        ):
            warnings.append(
                f"membership_taxonomy_classification_component_base_binding_mismatch:{market}"
            )
        expected_role = (
            "classification_definition"
            if component_name == "base_definition"
            else "classification_definition_component"
        )
        if entry.get("role") != expected_role:
            warnings.append(
                f"membership_taxonomy_classification_component_role_mismatch:{market}:{component_name}"
            )
        candidate = _v3_component_path(bundle_root, expected_path)
        if candidate is None:
            warnings.append(
                f"membership_taxonomy_classification_component_file_missing:{market}:{component_name}"
            )
            continue
        try:
            payload = candidate.read_bytes()
        except OSError:
            warnings.append(
                f"membership_taxonomy_classification_component_read_failed:{market}:{component_name}"
            )
            continue
        actual_hash = _sha256_file(candidate)
        if not _is_sha256(entry.get("source_file_hash")) or actual_hash != entry.get(
            "source_file_hash"
        ):
            warnings.append(
                f"membership_taxonomy_classification_component_hash_mismatch:{market}:{component_name}"
            )
        if entry.get("content_bytes") != len(payload):
            warnings.append(
                f"membership_taxonomy_classification_component_byte_count_mismatch:{market}:{component_name}"
            )
        lineage_item = lineage_components.get(component_name)
        if not isinstance(lineage_item, Mapping):
            warnings.append(
                f"membership_taxonomy_classification_component_lineage_missing:{market}:{component_name}"
            )
        else:
            lineage_hash = lineage_item.get("sha256")
            if not _is_sha256(lineage_hash) or actual_hash != lineage_hash:
                warnings.append(
                    f"membership_taxonomy_classification_component_lineage_hash_mismatch:{market}:{component_name}"
                )
            if lineage_item.get("content_bytes") != len(payload):
                warnings.append(
                    f"membership_taxonomy_classification_component_lineage_byte_count_mismatch:{market}:{component_name}"
                )
        captured_at = _verify_composite_raw_http(
            entry,
            market,
            component_name,
            warnings,
            allow_derived_available=(component_name == "base_definition"),
        )
        if captured_at is not None:
            actual_component_times[component_name] = captured_at
        result[component_name] = payload

    derived_metadata = source.get("derived_metadata")
    if not isinstance(derived_metadata, Mapping) or derived_metadata.get(
        "metadata_kind"
    ) != "derived_composite":
        warnings.append(
            f"membership_taxonomy_classification_derived_metadata_invalid:{market}"
        )
    elif any(
        field in derived_metadata
        for field in ("requested_url", "final_url", "http_status", "content_type")
    ):
        warnings.append(
            f"membership_taxonomy_classification_derived_metadata_http_shape:{market}"
        )
    else:
        base_entry = raw_files_by_key.get((source_id, market))
        if not isinstance(base_entry, Mapping) or base_entry.get(
            "derived_metadata"
        ) != derived_metadata:
            warnings.append(
                f"membership_taxonomy_classification_derived_metadata_binding_mismatch:{market}"
            )
        component_captured_at = derived_metadata.get("component_captured_at")
        if not isinstance(component_captured_at, Mapping) or set(
            component_captured_at
        ) != set(_TWSE_B1212_COMPOSITE_COMPONENTS):
            warnings.append(
                f"membership_taxonomy_classification_component_completion_invalid:{market}"
            )
        else:
            declared_times: dict[str, datetime] = {}
            for component_name in _TWSE_B1212_COMPOSITE_COMPONENTS:
                declared = _datetime_or_none(
                    component_captured_at.get(component_name),
                    warnings,
                    f"membership_taxonomy_classification_component_completion_invalid:{market}:{component_name}",
                )
                if declared is not None:
                    declared_times[component_name] = declared
                actual = actual_component_times.get(component_name)
                if actual is not None and declared != actual:
                    warnings.append(
                        f"membership_taxonomy_classification_component_completion_mismatch:{market}:{component_name}"
                    )
            derived_at = _datetime_or_none(
                derived_metadata.get("derived_at"),
                warnings,
                f"membership_taxonomy_classification_derived_at_invalid:{market}",
            )
            if derived_at is not None:
                if actual_component_times and derived_at != max(actual_component_times.values()):
                    warnings.append(
                        f"membership_taxonomy_classification_derived_completion_mismatch:{market}"
                    )
                if declared_times and derived_at != max(declared_times.values()):
                    warnings.append(
                        f"membership_taxonomy_classification_declared_completion_mismatch:{market}"
                    )
    return (
        result
        if set(result) == set(_TWSE_B1212_COMPOSITE_COMPONENTS)
        else None
    )


def _verify_composite_raw_http(
    entry: Mapping[str, object],
    market: str,
    component_name: str,
    warnings: list[str],
    *,
    allow_derived_available: bool = False,
) -> datetime | None:
    http = entry.get("http")
    prefix = f"membership_taxonomy_classification_component_http:{market}:{component_name}"
    if not isinstance(http, Mapping):
        warnings.append(prefix + ":missing")
        return None
    if not isinstance(http.get("requested_url"), str) or not str(
        http.get("requested_url")
    ).strip():
        warnings.append(prefix + ":requested_url_invalid")
    if not isinstance(http.get("final_url"), str) or not str(http.get("final_url")).strip():
        warnings.append(prefix + ":final_url_invalid")
    status = http.get("http_status")
    if isinstance(status, bool) or status != 200:
        warnings.append(prefix + ":status_invalid")
    if not isinstance(http.get("content_type"), str) or not str(
        http.get("content_type")
    ).strip():
        warnings.append(prefix + ":content_type_invalid")
    captured_at = _datetime_or_none(http.get("captured_at"), warnings, prefix + ":captured_at_invalid")
    available_at = _datetime_or_none(entry.get("available_at"), warnings, prefix + ":available_at_invalid")
    if captured_at is not None and available_at is not None:
        if not allow_derived_available and captured_at != available_at:
            warnings.append(prefix + ":completion_mismatch")
        if allow_derived_available:
            derived_metadata = entry.get("derived_metadata")
            derived_at = (
                _datetime_or_none(
                    derived_metadata.get("derived_at"),
                    warnings,
                    prefix + ":derived_at_invalid",
                )
                if isinstance(derived_metadata, Mapping)
                else None
            )
            if derived_at is None or derived_at != available_at:
                warnings.append(prefix + ":derived_completion_mismatch")
            elif captured_at > derived_at:
                warnings.append(prefix + ":captured_after_derived")
    return captured_at


def _one_line(error: Exception) -> str:
    return (str(error).splitlines()[0].strip() or type(error).__name__)[:240]


__all__ = [
    "PIT_FORMAL_MANIFEST_SCHEMA_VERSION",
    "PIT_MACHINE_PUBLICATION_SCHEMA_VERSION",
    "PIT_MEMBERSHIP_READER_SCHEMA_VERSION",
    "PIT_PROSPECTIVE_MANIFEST_SCHEMA_VERSION",
    "PIT_SIDECAR_SCHEMA_VERSION",
    "PIT_SPLIT_SIDECAR_SCHEMA_VERSION",
    "PIT_SPLIT_MANIFEST_SCHEMA_VERSION",
    "PIT_TAXONOMY_IDENTITY_SCHEMA_VERSION",
    "PIT_TAXONOMY_IDENTITY_V3_SCHEMA_VERSION",
    "PIT_TAXONOMY_IDENTITY_V4_SCHEMA_VERSION",
    "PIT_TAXONOMY_SOURCE_SCHEMA_VERSION",
    "PIT_TAXONOMY_SOURCE_V2_SCHEMA_VERSION",
    "PIT_TAXONOMY_SOURCE_V3_SCHEMA_VERSION",
    "PIT_TAXONOMY_SCOPE_BINDING_SCHEMA_VERSION",
    "PIT_TAXONOMY_RAW_MANIFEST_SCHEMA_VERSION",
    "PITMembershipArtifact",
    "PITMembershipReadResult",
    "PITMembershipReaderError",
    "PITMembershipRow",
    "PITUniverseReadResult",
    "PITSectorMembershipReader",
]
