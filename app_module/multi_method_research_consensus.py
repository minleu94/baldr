"""UX10：既有 MA 方法結果的有界唯讀共同符合投影。"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
import hashlib
import json
import re
from typing import Literal

from app_module.daily_market_method_contract import method_contracts_payload, method_contracts_sha256
from app_module.daily_market_feature_snapshot import (
    DAILY_MARKET_FEATURE_CONTRACT_VERSION,
    DAILY_MARKET_FEATURE_CONTRACT_VERSION_BBANDS30_UPPER,
    feature_contract_for_version,
)
from app_module.daily_market_research_screener import evaluate_daily_market_conditions
from app_module.daily_market_snapshot_repository import (
    DailyMarketSnapshotRepository, VerifiedDailyMarketSnapshot,
    canonical_snapshot_sha256, snapshot_manifest_identity_sha256, cohort_identity_sha256,
)

State = Literal["selected", "not_selected", "unknown"]
MAX_SOURCES = 8
MAX_STOCKS = 16
MAX_OBSERVATIONS = 32
MAX_EXCLUSIONS = 31
_SHA = re.compile(r"^[0-9a-f]{64}$")


class ConsensusContractError(ValueError):
    """拒絕混源、修訂與不完整契約；錯誤碼可供 consumer 顯示。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise ConsensusContractError(code)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha(value: object) -> bool:
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _text(value: object, limit: int = 256) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip() and len(value) <= limit


def _aware(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value)
        _require(dt.tzinfo is not None and dt.utcoffset() is not None, "clock_identity_missing")
        return dt
    except (TypeError, ValueError) as exc:
        raise ConsensusContractError("clock_identity_missing") from exc


@dataclass(frozen=True, slots=True)
class MethodObservation:
    """單股三態與逐股 artifact／輸入身份；缺件仍有完整分母列。"""

    stock_code: str
    state: State
    reason: str
    unknown_reason: str
    data_date: str | None
    artifact_sha256: str | None
    stock_snapshot_sha256: str | None
    input_sha256: str | None
    relation: str = "unknown"


@dataclass(frozen=True, slots=True)
class MethodResultSource:
    """獨立 lane DTO；只承接已驗證研究結果，不代表正式推薦資格。"""

    snapshot_id: str
    snapshot_sha256: str
    cohort_id: str
    cohort_sha256: str
    decision_date: str
    decision_cutoff: str
    published_at: str
    universe_json: str
    universe_sha256: str
    declared_stock_codes: tuple[str, ...]
    excluded_stock_codes: tuple[tuple[str, str], ...]
    population_count: int | None
    completeness: str
    method_key: str
    method_id: str
    family: str
    version: str
    parameters_json: str
    contracts_sha256: str
    observations: tuple[MethodObservation, ...]
    source_refs_json: str = "[]"
    research_only: bool = True
    historical_pit_eligible: bool = False


@dataclass(frozen=True, slots=True)
class StockConsensusRow:
    """描述已符合方法與家族；unknown 不產生退出或負樣本。"""

    stock_code: str
    methods: tuple[tuple[str, MethodObservation], ...]
    selected_method_ids: tuple[str, ...]
    selected_families: tuple[str, ...]
    family_states: tuple[tuple[str, State], ...]
    all_methods_state: State
    multi_family_state: State
    multi_family_reason: str

    @property
    def selected_method_count(self) -> int:
        return len(self.selected_method_ids)

    @property
    def selected_family_count(self) -> int:
        return len(self.selected_families)

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "selected_method_count": self.selected_method_count,
                "selected_family_count": self.selected_family_count}


@dataclass(frozen=True, slots=True)
class MultiMethodResearchConsensus:
    """完整 included 分母、方法狀態計數與來源；不使用命中數排序。"""

    sources: tuple[MethodResultSource, ...]
    rows: tuple[StockConsensusRow, ...]
    method_counts: tuple[tuple[str, int, int, int], ...]
    denominator: int
    excluded_stock_codes: tuple[tuple[str, str], ...]
    population_count: int | None
    warnings: tuple[str, ...]
    research_only: bool = True
    historical_pit_eligible: bool = False

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "rows": [row.to_dict() for row in self.rows]}


def _validate_source(source: MethodResultSource) -> dict[str, MethodObservation]:
    _require(isinstance(source, MethodResultSource), "source_type_invalid")
    for value in (source.snapshot_id, source.snapshot_sha256, source.cohort_sha256,
                  source.universe_sha256, source.contracts_sha256):
        _require(_sha(value), "source_hash_missing")
    _require(_text(source.cohort_id), "cohort_identity_missing")
    try:
        day = date.fromisoformat(source.decision_date)
    except (TypeError, ValueError) as exc:
        raise ConsensusContractError("decision_date_invalid") from exc
    _require(day.isoformat() == source.decision_date, "decision_date_invalid")
    cutoff, published = _aware(source.decision_cutoff), _aware(source.published_at)
    _require(cutoff.date() == day and cutoff <= published, "source_clock_mismatch")
    _require(source.research_only is True and source.historical_pit_eligible is False, "unsupported_qualification")
    supported_contract = next((feature_contract_for_version(version) for version in (
        DAILY_MARKET_FEATURE_CONTRACT_VERSION, DAILY_MARKET_FEATURE_CONTRACT_VERSION_BBANDS30_UPPER,
    ) if feature_contract_for_version(version).method_contracts_sha256 == source.contracts_sha256), None)
    _require(supported_contract is not None, "method_version_or_contract_mismatch")
    assert supported_contract is not None
    expected = supported_contract.method_contracts.get(source.method_key)
    _require(expected is not None, "method_not_supported")
    assert expected is not None
    _require((source.method_id, source.family, source.version, source.parameters_json,
              source.contracts_sha256) == (expected["method_id"], expected["family"],
              expected["version"], _json(expected["parameters"]), supported_contract.method_contracts_sha256),
             "method_version_or_contract_mismatch")
    _require(source.completeness in {"complete_declared_cohort", "partial_research"}, "completeness_invalid")
    codes = source.declared_stock_codes
    _require(isinstance(codes, tuple) and 1 <= len(codes) <= MAX_STOCKS, "denominator_limit")
    _require(all(_text(c, 16) and c.isascii() and c.isalnum() for c in codes), "stock_identity_invalid")
    _require(codes == tuple(sorted(set(codes))), "denominator_duplicate_or_order")
    _require(cohort_identity_sha256(source.cohort_id, codes) == source.cohort_sha256, "cohort_identity_mismatch")
    _require(isinstance(source.excluded_stock_codes, tuple) and len(source.excluded_stock_codes) <= MAX_EXCLUSIONS, "exclusion_limit")
    _require(len(codes) + len(source.excluded_stock_codes) <= 32, "exclusion_limit")
    exclusions = source.excluded_stock_codes
    _require(all(isinstance(e, tuple) and len(e) == 2 and _text(e[0], 16) and _text(e[1], 1024) for e in exclusions), "exclusion_reason_missing")
    excluded_codes = tuple(e[0] for e in exclusions)
    _require(len(set(excluded_codes)) == len(excluded_codes) and not set(codes).intersection(excluded_codes), "exclusion_scope_invalid")
    _require(source.population_count is None or (type(source.population_count) is int
             and source.population_count == len(codes) + len(exclusions)), "population_count_mismatch")
    _require(isinstance(source.universe_json, str) and len(source.universe_json.encode("utf-8")) <= 32768, "universe_byte_limit")
    try:
        universe = json.loads(source.universe_json)
        _require(isinstance(universe, dict) and _json(universe) == source.universe_json, "universe_identity_invalid")
    except (TypeError, ValueError, RecursionError) as exc:
        raise ConsensusContractError("universe_identity_invalid") from exc
    _require(hashlib.sha256(source.universe_json.encode("utf-8")).hexdigest() == source.universe_sha256, "universe_hash_mismatch")
    if universe.get("scope") == "legacy_declared_research_only":
        _require(universe == {"scope": "legacy_declared_research_only", "cohort_identity": source.cohort_sha256,
                 "declared_stock_codes": list(codes)} and not exclusions and source.population_count is None,
                 "universe_denominator_mismatch")
    else:
        _require(universe.get("universe_id") == source.cohort_id
                 and universe.get("as_of_date") == source.decision_date
                 and universe.get("included_stock_codes") == list(codes)
                 and universe.get("excluded_stock_codes") == [{"stock_code": c, "reason": r} for c, r in exclusions]
                 and universe.get("population_count") == source.population_count
                 and universe.get("research_only") is True
                 and universe.get("scope") == "bounded_research_cohort"
                 and _text(universe.get("version")) and _sha(universe.get("source_sha256")),
                 "universe_denominator_mismatch")
    _require(isinstance(source.source_refs_json, str) and len(source.source_refs_json.encode("utf-8")) <= 65536, "source_refs_limit")
    try:
        refs = json.loads(source.source_refs_json)
        _require(isinstance(refs, list) and len(refs) <= MAX_STOCKS and _json(refs) == source.source_refs_json,
                 "source_refs_invalid")
        _require(all(isinstance(r, dict) and set(r) == {"stock_code", "source_refs"}
                 and r["stock_code"] in codes and isinstance(r["source_refs"], dict) and bool(r["source_refs"]) for r in refs),
                 "source_refs_invalid")
        ref_codes = tuple(r["stock_code"] for r in refs)
        _require(len(set(ref_codes)) == len(ref_codes), "source_refs_invalid")
    except (TypeError, ValueError, RecursionError) as exc:
        raise ConsensusContractError("source_refs_invalid") from exc
    _require(isinstance(source.observations, tuple) and len(source.observations) <= MAX_OBSERVATIONS, "observation_limit")
    rows: dict[str, MethodObservation] = {}
    for obs in source.observations:
        _require(isinstance(obs, MethodObservation) and obs.stock_code in codes, "observation_scope_invalid")
        _require(obs.state in {"selected", "not_selected", "unknown"}, "state_invalid")
        _require(obs.relation in {"above", "below", "equal", "unknown"}, "relation_invalid")
        _require(obs.state == "unknown" or (obs.state == "selected" and obs.relation == "above")
                 or (obs.state == "not_selected" and obs.relation in {"below", "equal"}), "state_relation_mismatch")
        _require(_text(obs.reason, 4096), "reason_missing")
        _require(isinstance(obs.unknown_reason, str) and len(obs.unknown_reason) <= 4096, "unknown_reason_invalid")
        _require(bool(obs.unknown_reason) == (obs.state == "unknown"), "unknown_qualification_mismatch")
        _require(obs.artifact_sha256 is None or obs.stock_code in ref_codes, "source_refs_missing")
        pins = (obs.artifact_sha256, obs.stock_snapshot_sha256, obs.input_sha256)
        _require(all(pin is None or _sha(pin) for pin in pins), "evidence_hash_invalid")
        _require(obs.state == "unknown" or (all(_sha(pin) for pin in pins) and obs.data_date is not None), "missing_evidence")
        if obs.data_date is not None:
            try:
                data_day = date.fromisoformat(obs.data_date)
            except (TypeError, ValueError) as exc:
                raise ConsensusContractError("data_date_invalid") from exc
            _require(data_day.isoformat() == obs.data_date and data_day <= day, "data_date_mismatch")
        _require(obs.stock_code not in rows or rows[obs.stock_code] == obs, "duplicate_stock_revision")
        rows[obs.stock_code] = obs
    return rows


def _and(states: tuple[State, ...]) -> State:
    return "not_selected" if "not_selected" in states else "selected" if states and all(s == "selected" for s in states) else "unknown"


def _or(states: tuple[State, ...]) -> State:
    return "selected" if "selected" in states else "not_selected" if states and all(s == "not_selected" for s in states) else "unknown"


def build_multi_method_consensus(sources: Sequence[MethodResultSource]) -> MultiMethodResearchConsensus:
    """同 pin、日期、母體與方法版本才比較；同來源重播冪等。"""
    _require(isinstance(sources, Sequence) and not isinstance(sources, (str, bytes))
             and 1 <= len(sources) <= MAX_SOURCES, "source_limit")
    unique: dict[str, MethodResultSource] = {}
    observations: dict[str, dict[str, MethodObservation]] = {}
    for source in sources:
        rows = _validate_source(source)
        normalized = replace(source, observations=tuple(rows[c] for c in sorted(rows)))
        prior = unique.get(source.method_id)
        _require(prior is None or prior == normalized, "same_method_source_revision")
        unique[source.method_id] = normalized
        observations[source.method_id] = rows
    ordered = tuple(unique[key] for key in sorted(unique))
    first = ordered[0]
    def identity(s: MethodResultSource) -> tuple[object, ...]:
        return (s.snapshot_id, s.snapshot_sha256, s.cohort_id, s.cohort_sha256,
                s.decision_date, s.decision_cutoff, s.published_at, s.universe_json,
                s.universe_sha256, s.declared_stock_codes, s.excluded_stock_codes,
                s.population_count, s.completeness, s.contracts_sha256, s.source_refs_json)
    _require(all(identity(s) == identity(first) for s in ordered), "incomparable_source_scope_or_revision")
    projected: list[StockConsensusRow] = []
    for code in first.declared_stock_codes:
        items: list[tuple[str, MethodObservation]] = []
        evidence: set[tuple[object, ...]] = set()
        for source in ordered:
            obs = observations[source.method_id].get(code)
            if obs is None:
                obs = MethodObservation(code, "unknown", "缺少此方法的股票觀測。", "method_observation_missing", None, None, None, None)
            if obs.artifact_sha256 is not None:
                evidence.add((obs.data_date, obs.artifact_sha256, obs.stock_snapshot_sha256, obs.input_sha256))
            if first.completeness != "complete_declared_cohort":
                obs = replace(obs, state="unknown", reason=obs.reason + "；母體快照不完整。",
                              unknown_reason="partial_snapshot|" + obs.unknown_reason)
            items.append((source.method_id, obs))
        _require(len(evidence) <= 1, "stock_evidence_revision_or_date_mismatch")
        families = tuple(sorted(set(s.family for s in ordered)))
        family_states = tuple((family, _or(tuple(obs.state for s, (_, obs) in zip(ordered, items) if s.family == family))) for family in families)
        selected_ids = tuple(mid for mid, obs in items if obs.state == "selected")
        selected_families = tuple(f for f, state in family_states if state == "selected")
        # 目前僅一個 MA 家族，不能冒稱跨策略家族支持。
        multi = _and(tuple(state for _, state in family_states)) if len(families) >= 2 else "unknown"
        projected.append(StockConsensusRow(code, tuple(items), selected_ids, selected_families,
                          family_states, _and(tuple(obs.state for _, obs in items)), multi,
                          "只有一個既有 MA 家族，跨家族共同入選尚不可判定。" if len(families) < 2 else "依完整可比較家族三態判定。"))
    result_rows = tuple(projected)
    counts_list: list[tuple[str, int, int, int]] = []
    for source in ordered:
        states = tuple(obs.state for row in result_rows for mid, obs in row.methods if mid == source.method_id)
        counts_list.append((source.method_id, states.count("selected"), states.count("not_selected"), states.count("unknown")))
    counts = tuple(counts_list)
    return MultiMethodResearchConsensus(ordered, result_rows, counts, len(first.declared_stock_codes),
                 first.excluded_stock_codes, first.population_count,
                 ("current_observed_research_only", "source_availability_unproven", "one_existing_ma_family",
                  "ranking_has_no_approved_entry_predicate"))


def adapt_daily_market_snapshot(snapshot: VerifiedDailyMarketSnapshot, *, as_of: datetime) -> tuple[MethodResultSource, ...]:
    """轉換既有 verified DTO；保留 captured 契約、缺件與排除，不補查 live。"""
    _require(isinstance(snapshot, VerifiedDailyMarketSnapshot), "snapshot_type_invalid")
    _require(isinstance(as_of, datetime) and as_of.tzinfo is not None and as_of.utcoffset() is not None, "as_of_invalid")
    manifest = snapshot.manifest
    _require(canonical_snapshot_sha256(manifest) == snapshot.manifest_sha256, "manifest_mutated")
    _require(snapshot_manifest_identity_sha256(manifest) == snapshot.manifest_identity_sha256
             and manifest.get("manifest_identity_sha256") == snapshot.manifest_identity_sha256
             and manifest.get("cohort_id") == snapshot.cohort_id
             and manifest.get("decision_date") == snapshot.decision_date.isoformat()
             and manifest.get("completeness") == snapshot.completeness, "verified_wrapper_mismatch")
    contract = feature_contract_for_version(str(manifest.get("feature_contract_version") or ""))
    _require(manifest.get("method_contracts") == contract.method_contracts
             and manifest.get("method_contracts_sha256") == contract.method_contracts_sha256, "captured_methods_missing_or_mixed")
    cutoff, published = str(manifest["decision_cutoff"]), str(manifest["published_at"])
    _require(_aware(cutoff) <= as_of and _aware(published) <= as_of, "source_after_as_of")
    codes = tuple(manifest["declared_stock_codes"])
    _require(len(codes) <= MAX_STOCKS and len(snapshot.stock_snapshots) <= MAX_STOCKS, "denominator_limit")
    universe = manifest.get("research_universe")
    universe_json = _json(universe if universe is not None else {"scope": "legacy_declared_research_only", "cohort_identity": manifest["cohort_identity"], "declared_stock_codes": list(codes)})
    excluded = tuple((e["stock_code"], e["reason"]) for e in universe["excluded_stock_codes"]) if universe is not None else ()
    population = universe["population_count"] if universe is not None else None
    records = {r["stock_code"]: r for r in manifest["stocks"]}
    missing = {r["stock_code"]: r["reason"] for r in manifest["missing_stocks"]}
    _require(set(records) == set(snapshot.stock_snapshots) and set(records) | set(missing) == set(codes)
             and not set(records).intersection(missing), "artifact_denominator_mismatch")
    sources: list[MethodResultSource] = []
    for key, method in contract.method_contracts.items():
        rows: list[MethodObservation] = []
        for code in codes:
            payload = snapshot.stock_snapshots.get(code)
            if payload is None:
                rows.append(MethodObservation(code, "unknown", "來源股票 artifact 缺件。", str(missing.get(code) or "stock_artifact_missing"), None, None, None, None))
                continue
            record = records[code]
            _require(canonical_snapshot_sha256(payload) == record["artifact_sha256"], "artifact_mutated")
            _require(payload.get("stock_code") == code and payload.get("decision_date") == snapshot.decision_date.isoformat(), "stock_payload_identity_mismatch")
            result = evaluate_daily_market_conditions(payload.get("conditions", {}), (key,), "AND", expected_decision_date=snapshot.decision_date).conditions[0]
            # 舊 snapshot 缺方法 metadata 時一律 unknown，不靠 live 方法補資格。
            qualified = result.eligibility == "eligible" and result.method_id == method["method_id"]
            state: State = "selected" if qualified and result.state == "match" else "not_selected" if qualified and result.state == "no_match" else "unknown"
            rows.append(MethodObservation(code, state, result.reason or ("符合既有 MA 條件。" if state == "selected" else "未符合既有 MA 條件。"),
                (result.unknown_reason or "condition_evidence_unknown") if state == "unknown" else "",
                payload.get("market_date"), record["artifact_sha256"], payload["snapshot_identity_sha256"], payload["input_fingerprint_sha256"], result.relation))
        sources.append(MethodResultSource(snapshot.manifest_identity_sha256, snapshot.manifest_sha256,
            snapshot.cohort_id, manifest["cohort_identity"], snapshot.decision_date.isoformat(), cutoff, published,
            universe_json, hashlib.sha256(universe_json.encode("utf-8")).hexdigest(), codes, excluded, population,
            snapshot.completeness, key, method["method_id"], method["family"], method["version"],
            _json(method["parameters"]), manifest["method_contracts_sha256"], tuple(rows),
            _json([{ "stock_code": code, "source_refs": records[code]["source_refs"] } for code in sorted(records)])))
    return tuple(sources)


def read_daily_market_consensus(repository: DailyMarketSnapshotRepository, *, manifest_sha256: str,
        cohort_id: str, decision_date: date, as_of: datetime) -> MultiMethodResearchConsensus:
    """固定 manifest 唯讀 adapter；不讀 latest、DB、producer、排名或個人資料。"""
    snapshot = repository.load_manifest(manifest_sha256, cohort_id, decision_date)
    return build_multi_method_consensus(adapt_daily_market_snapshot(snapshot, as_of=as_of))
