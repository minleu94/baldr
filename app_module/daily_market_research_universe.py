"""有界研究母體設定與原檔身份；不授予PIT資格或建立排名。"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
from collections.abc import Mapping
from typing import Any

RESEARCH_UNIVERSE_SCHEMA = "daily-market-research-universe.v1"
RESEARCH_UNIVERSE_METHOD = "daily-market-close-ma.v1"
RESEARCH_UNIVERSE_SCOPE = "bounded_research_cohort"
_KEYS = {"schema_version", "universe_id", "version", "as_of_date", "method", "included_stock_codes", "excluded_stock_codes", "population_count", "scope", "research_only", "complete_fixed_cohort"}
_BINDING_KEYS = (_KEYS - {"schema_version"}) | {"source_ref", "source_sha256"}
_LIMIT = 32 * 1024

class ResearchUniverseContractError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code

def _fail(message: str, code: str = "universe_config_schema_invalid") -> None:
    raise ResearchUniverseContractError(code, message)

def _read(path: Path) -> bytes:
    try:
        with path.open("rb") as handle:
            raw = handle.read(_LIMIT + 1)
    except OSError as exc:
        raise ResearchUniverseContractError("universe_source_missing", "母體設定來源無法讀取") from exc
    if len(raw) > _LIMIT:
        _fail("母體設定超過32KiB")
    return raw

def _text(value: Any, name: str, limit: int = 128) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > limit:
        _fail(f"{name} 必須為有界非空字串")
    return value

def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("設定含重複JSON欄位")
        result[key] = value
    return result

def _canonical(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ResearchUniverseContractError("universe_binding_invalid", "母體綁定不是嚴格JSON") from exc

@dataclass(frozen=True, slots=True)
class ResearchUniverseSpec:
    universe_id: str
    version: str
    as_of_date: date
    method: str
    included_stock_codes: tuple[str, ...]
    excluded_stock_codes: tuple[tuple[str, str], ...]
    population_count: int | None
    scope: str
    research_only: bool
    complete_fixed_cohort: bool
    source_ref: str
    source_sha256: str

    def to_manifest_binding(self) -> dict[str, Any]:
        return {"universe_id": self.universe_id, "version": self.version,
                "as_of_date": self.as_of_date.isoformat(), "method": self.method,
                "source_ref": self.source_ref, "source_sha256": self.source_sha256,
                "included_stock_codes": list(self.included_stock_codes),
                "excluded_stock_codes": [{"stock_code": code, "reason": reason} for code, reason in self.excluded_stock_codes],
                "population_count": self.population_count, "scope": self.scope,
                "research_only": self.research_only, "complete_fixed_cohort": self.complete_fixed_cohort}

    def to_dict(self) -> dict[str, Any]:
        value = {"schema_version": RESEARCH_UNIVERSE_SCHEMA, **self.to_manifest_binding()}
        value["identity_sha256"] = hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        return value

    def assert_source_stable(self) -> None:
        if hashlib.sha256(_read(Path(self.source_ref))).hexdigest() != self.source_sha256:
            _fail("母體設定來源已變更", "universe_source_changed")
        current = load_research_universe_spec(self.source_ref)
        if _canonical(self.to_manifest_binding()) != _canonical(current.to_manifest_binding()):
            _fail("母體物件與原設定不一致", "universe_binding_mismatch")

    @property
    def original_rank_status(self) -> dict[str, str]:
        return {"status": "unknown", "reason": "original_rank_immutable_source_missing"}

def load_research_universe_spec(path: str | Path) -> ResearchUniverseSpec:
    source = Path(path).expanduser().resolve()
    raw = _read(source)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ResearchUniverseContractError("universe_config_schema_invalid", "母體設定不是有效UTF-8 JSON") from exc
    if not isinstance(value, dict) or set(value) != _KEYS:
        _fail("母體設定欄位必須精確符合契約；不接受排名或資格欄位")
    if value["schema_version"] != RESEARCH_UNIVERSE_SCHEMA:
        _fail("母體設定版本不相容")
    universe_id = _text(value["universe_id"], "universe_id")
    version = _text(value["version"], "version")
    day_text = _text(value["as_of_date"], "as_of_date", 10)
    try:
        day = date.fromisoformat(day_text)
    except ValueError as exc:
        raise ResearchUniverseContractError("universe_config_schema_invalid", "母體截至日無效") from exc
    if day.isoformat() != day_text:
        _fail("母體截至日須ISO日期")
    if value["method"] != RESEARCH_UNIVERSE_METHOD or value["scope"] != RESEARCH_UNIVERSE_SCOPE:
        _fail("母體方法／範圍不相容")
    included = value["included_stock_codes"]
    excluded = value["excluded_stock_codes"]
    if not isinstance(included, list) or not 1 <= len(included) <= 16 or not isinstance(excluded, list) or len(included) + len(excluded) > 32:
        _fail("母體納入須1–16股，納入與排除合計最多32股")
    codes = tuple(_text(code, "stock_code", 32) for code in included)
    exclusions: list[tuple[str, str]] = []
    for item in excluded:
        if not isinstance(item, dict) or set(item) != {"stock_code", "reason"}:
            _fail("排除須提供代碼與理由")
        exclusions.append((_text(item["stock_code"], "stock_code", 32), _text(item["reason"], "reason", 512)))
    all_codes = codes + tuple(code for code, _ in exclusions)
    if len(set(all_codes)) != len(all_codes):
        _fail("母體成員重複或納入排除重疊")
    population = value["population_count"]
    if population is not None and (type(population) is not int or population != len(all_codes)):
        _fail("已知設定分母須等於納入與排除合計")
    if value["research_only"] is not True or type(value["complete_fixed_cohort"]) is not bool:
        _fail("母體必須明示研究用途及完整性")
    if value["complete_fixed_cohort"] and population is None:
        _fail("完整固定母體不能缺少分母")
    return ResearchUniverseSpec(universe_id, version, day, value["method"], tuple(sorted(codes)), tuple(sorted(exclusions)), population, value["scope"], True, value["complete_fixed_cohort"], str(source), hashlib.sha256(raw).hexdigest())

def validate_research_universe_manifest_binding(spec: ResearchUniverseSpec, binding: Mapping[str, Any]) -> None:
    if not isinstance(binding, Mapping) or set(binding) != _BINDING_KEYS:
        _fail("母體manifest欄位不相容", "universe_binding_invalid")
    if _canonical(binding) != _canonical(spec.to_manifest_binding()):
        _fail("母體manifest與原設定身份不一致", "universe_binding_mismatch")
    spec.assert_source_stable()
