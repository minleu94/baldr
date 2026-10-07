"""固定技術研究母體與跨批保存收據 v4。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Literal, Protocol, TYPE_CHECKING, cast
from uuid import uuid4

from app_module.daily_market_technical_feature_snapshot_v4 import (
    DailyMarketTechnicalFeatureSnapshotV4,
    build_daily_market_technical_feature_snapshot_v4,
    _validate_source_clock_payload,
)
from app_module.daily_market_technical_method_contract_v4 import (
    daily_market_technical_method_contract_v4_payload,
    daily_market_technical_method_contract_v4_sha256,
    validate_daily_market_technical_method_contract_v4,
)
from app_module.daily_market_technical_read_session import DailyMarketTechnicalSourceClockV4
from app_module.daily_market_technical_source import DailyMarketTechnicalSourceWindow
from app_module.personal_data_paths import to_internal_io_path
from app_module.rule_research_sample_capture import (
    ResearchCaptureWriteScope,
    RuleSampleCaptureError,
    _directory_names,
    _path_exists,
    _path_is_dir,
    _path_mkdir,
    _path_open,
    _path_rename,
    _path_stat,
    _path_unlink,
    _read_file,
    _resolve_path,
    _safe_path,
    _write_file,
)

if TYPE_CHECKING:
    from app_module.daily_market_technical_snapshot_v4_repository import (
            DailyMarketTechnicalBatchArtifactV4,
    )


class _FcntlAPI(Protocol):
    LOCK_EX: int
    LOCK_NB: int
    LOCK_UN: int

    def flock(self, fd: int, operation: int) -> None: ...


COHORT_SCHEMA_V4 = "daily-market-technical-cohort.v4"
PARENT_PLAN_SCHEMA_V4 = "rule-research-technical-parent-plan.v4"
PARENT_RECEIPT_SCHEMA_V4 = "rule-research-technical-parent-receipt.v4"
GENERATION_IDENTITY_SCHEMA_V4 = "daily-market-technical-snapshot-v4-generation-identity.v1"
PARENT_CAPTURE_MAX_BYTES_V4 = 256 * 1024
PARENT_RECEIPT_MAX_BYTES_V4 = 256 * 1024
PARENT_CAPTURE_MAX_RETAINED_BYTES_V4 = 64 * 1024 * 1024
PARENT_CAPTURE_MAX_RETAINED_ENTRIES_V4 = 8192
MAX_INCLUDED_STOCKS_V4 = 256
MAX_EXCLUDED_STOCKS_V4 = 256
MAX_STOCKS_PER_BATCH_V4 = 16
MAX_BATCHES_V4 = 16
MAX_UNIVERSE_ID_CHARS_V4 = 96
MAX_POPULATION_VERSION_CHARS_V4 = 128
MAX_STOCK_CODE_CHARS_V4 = 16
MAX_EXCLUSION_REASON_CHARS_V4 = 512
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Za-z0-9]{1,16}$")
_PLAN_KEYS = {
    "schema_version",
    "cohort",
    "population_state",
    "source_clock",
    "source_clock_identity_sha256",
    "method_contracts",
    "method_contracts_sha256",
    "generation_identity_sha256",
    "source_stock_evidence",
    "batches",
    "policy",
    "parent_plan_identity_sha256",
}
_COHORT_KEYS = {
    "schema_version",
    "universe_id",
    "population_version",
    "decision_date",
    "included_stock_codes",
    "excluded_stock_codes",
    "exclusion_reasons",
    "declared_count",
    "cohort_identity_sha256",
}
_RECEIPT_KEYS = {
    "schema_version",
    "parent_plan_identity_sha256",
    "generation_identity_sha256",
    "source_clock_identity_sha256",
    "sequence",
    "previous_receipt_identity_sha256",
    "status",
    "batch_artifacts",
    "repository_output_root",
    "writer_version",
    "error_code",
    "observed_at",
    "receipt_identity_sha256",
}
_POLICY_V4 = {
    "research_only": True,
    "historical_pit_eligible": False,
    "source_available_at": None,
    "availability_status": "unknown",
    "natural_authority": False,
    "formal_eligible": False,
    "training_eligible": False,
    "advice_eligible": False,
    "allocation_eligible": False,
    "selection_policy": "fixed_cohort_rule_facts_only",
}
_POPULATION_STATES = {"included", "all_excluded", "empty"}
_RECEIPT_STATUSES = {"partial", "failed", "cancelled", "complete"}


class TechnicalParentCaptureV4Error(ValueError):
    """v4 parent 保存層的穩定錯誤碼。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise TechnicalParentCaptureV4Error(code)


def _reject_float_tree(value: object) -> None:
    if isinstance(value, float):
        raise TechnicalParentCaptureV4Error("parent_v4_float_forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TechnicalParentCaptureV4Error("parent_v4_json_key_invalid")
            _reject_float_tree(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_float_tree(item)


def _canonical_json(value: object) -> str:
    _reject_float_tree(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_json(value: object) -> str:
    return _sha256_bytes(_canonical_json(value).encode("utf-8"))


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _parse_json(raw: bytes | str, *, limit: int, code: str) -> object:
    try:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if len(encoded) > limit:
            raise TechnicalParentCaptureV4Error("parent_v4_byte_limit")

        def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in pairs:
                if key in result:
                    raise TechnicalParentCaptureV4Error("parent_v4_duplicate_json_key")
                result[key] = value
            return result

        def reject_constant(_value: str) -> None:
            raise TechnicalParentCaptureV4Error("parent_v4_json_constant_invalid")

        value = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
        _reject_float_tree(value)
        if _canonical_json(value).encode("utf-8") != encoded:
            raise TechnicalParentCaptureV4Error("parent_v4_json_noncanonical")
        return value
    except TechnicalParentCaptureV4Error:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise TechnicalParentCaptureV4Error(code) from exc


def _text(value: object, *, limit: int, code: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit or (not allow_empty and not value.strip()):
        raise TechnicalParentCaptureV4Error(code)
    return value


def _iso_date(value: object, code: str) -> date:
    if not isinstance(value, str):
        raise TechnicalParentCaptureV4Error(code)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise TechnicalParentCaptureV4Error(code) from exc
    if parsed.isoformat() != value:
        raise TechnicalParentCaptureV4Error(code)
    return parsed


def _aware_datetime(value: object, code: str) -> datetime:
    if not isinstance(value, str):
        raise TechnicalParentCaptureV4Error(code)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise TechnicalParentCaptureV4Error(code) from exc
    if parsed.utcoffset() is None or parsed.isoformat() != value:
        raise TechnicalParentCaptureV4Error(code)
    return parsed


def _identity_payload(value: Mapping[str, Any], identity_key: str) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != identity_key}


def _sorted_codes(value: object, *, maximum: int, code: str) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise TechnicalParentCaptureV4Error(code)
    codes: list[str] = []
    for item in value:
        stock_code = _text(item, limit=MAX_STOCK_CODE_CHARS_V4, code=code)
        if _STOCK_CODE_RE.fullmatch(stock_code) is None:
            raise TechnicalParentCaptureV4Error(code)
        codes.append(stock_code)
    if codes != sorted(codes) or len(codes) != len(set(codes)):
        raise TechnicalParentCaptureV4Error(code)
    return tuple(codes)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalCohortV4:
    """明示同一研究母體；排除理由保留原文字，不代換成規則結果。"""

    universe_id: str
    population_version: str
    decision_date: date
    included_stock_codes: tuple[str, ...]
    excluded_stock_codes: tuple[str, ...]
    exclusion_reasons: tuple[tuple[str, str], ...]
    declared_count: int
    cohort_identity_sha256: str

    def __post_init__(self) -> None:
        _validate_cohort_dict(self.to_dict())

    @classmethod
    def create(
        cls,
        *,
        universe_id: str,
        population_version: str,
        decision_date: date,
        included_stock_codes: Sequence[str],
        excluded_stock_codes: Sequence[str] = (),
        exclusion_reasons: Mapping[str, str] | Sequence[tuple[str, str]] = (),
    ) -> DailyMarketTechnicalCohortV4:
        if isinstance(included_stock_codes, (str, bytes)) or isinstance(excluded_stock_codes, (str, bytes)):
            raise TechnicalParentCaptureV4Error("technical_parent_v4_cohort_codes_invalid")
        included = tuple(sorted(included_stock_codes))
        excluded = tuple(sorted(excluded_stock_codes))
        reason_items = tuple(exclusion_reasons.items()) if isinstance(exclusion_reasons, Mapping) else tuple(exclusion_reasons)
        if len({key for key, _reason in reason_items}) != len(reason_items):
            raise TechnicalParentCaptureV4Error("technical_parent_v4_exclusion_reasons_invalid")
        reasons = tuple(sorted(reason_items))
        body: dict[str, object] = {
            "schema_version": COHORT_SCHEMA_V4,
            "universe_id": universe_id,
            "population_version": population_version,
            "decision_date": decision_date.isoformat(),
            "included_stock_codes": list(included),
            "excluded_stock_codes": list(excluded),
            "exclusion_reasons": {key: value for key, value in reasons},
            "declared_count": len(included) + len(excluded),
        }
        return cls(
            universe_id=universe_id,
            population_version=population_version,
            decision_date=decision_date,
            included_stock_codes=included,
            excluded_stock_codes=excluded,
            exclusion_reasons=reasons,
            declared_count=len(included) + len(excluded),
            cohort_identity_sha256=_sha256_json(body),
        )

    @classmethod
    def from_dict(cls, payload: object) -> DailyMarketTechnicalCohortV4:
        parsed = _validate_cohort_dict(payload)
        return cls(
            universe_id=parsed["universe_id"],
            population_version=parsed["population_version"],
            decision_date=parsed["decision_date"],
            included_stock_codes=parsed["included_stock_codes"],
            excluded_stock_codes=parsed["excluded_stock_codes"],
            exclusion_reasons=parsed["exclusion_reasons"],
            declared_count=parsed["declared_count"],
            cohort_identity_sha256=parsed["cohort_identity_sha256"],
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": COHORT_SCHEMA_V4,
            "universe_id": self.universe_id,
            "population_version": self.population_version,
            "decision_date": self.decision_date.isoformat(),
            "included_stock_codes": list(self.included_stock_codes),
            "excluded_stock_codes": list(self.excluded_stock_codes),
            "exclusion_reasons": {key: value for key, value in self.exclusion_reasons},
            "declared_count": self.declared_count,
            "cohort_identity_sha256": self.cohort_identity_sha256,
        }

    @property
    def population_state(self) -> Literal["included", "all_excluded", "empty"]:
        if self.included_stock_codes:
            return "included"
        if self.excluded_stock_codes:
            return "all_excluded"
        return "empty"


def _validate_cohort_dict(payload: object) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or set(payload) != _COHORT_KEYS:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_cohort_fields_invalid")
    value = dict(payload)
    if value["schema_version"] != COHORT_SCHEMA_V4:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_cohort_schema_invalid")
    _text(value["universe_id"], limit=MAX_UNIVERSE_ID_CHARS_V4, code="technical_parent_v4_universe_id_invalid")
    _text(value["population_version"], limit=MAX_POPULATION_VERSION_CHARS_V4, code="technical_parent_v4_population_version_invalid")
    parsed_date = _iso_date(value["decision_date"], "technical_parent_v4_decision_date_invalid")
    included = _sorted_codes(value["included_stock_codes"], maximum=MAX_INCLUDED_STOCKS_V4, code="technical_parent_v4_included_codes_invalid")
    excluded = _sorted_codes(value["excluded_stock_codes"], maximum=MAX_EXCLUDED_STOCKS_V4, code="technical_parent_v4_excluded_codes_invalid")
    if set(included).intersection(excluded):
        raise TechnicalParentCaptureV4Error("technical_parent_v4_cohort_overlap")
    reasons = value["exclusion_reasons"]
    if not isinstance(reasons, Mapping) or set(reasons) != set(excluded):
        raise TechnicalParentCaptureV4Error("technical_parent_v4_exclusion_reasons_invalid")
    parsed_reasons: tuple[tuple[str, str], ...] = tuple(sorted(
        (
            _text(key, limit=MAX_STOCK_CODE_CHARS_V4, code="technical_parent_v4_exclusion_reasons_invalid"),
            _text(reason, limit=MAX_EXCLUSION_REASON_CHARS_V4, code="technical_parent_v4_exclusion_reasons_invalid"),
        )
        for key, reason in reasons.items()
    ))
    if any(_STOCK_CODE_RE.fullmatch(code) is None for code, _reason in parsed_reasons):
        raise TechnicalParentCaptureV4Error("technical_parent_v4_exclusion_reasons_invalid")
    if type(value["declared_count"]) is not int or value["declared_count"] != len(included) + len(excluded):
        raise TechnicalParentCaptureV4Error("technical_parent_v4_declared_count_mismatch")
    if not _is_sha256(value["cohort_identity_sha256"]):
        raise TechnicalParentCaptureV4Error("technical_parent_v4_cohort_identity_invalid")
    stable = {key: item for key, item in value.items() if key != "cohort_identity_sha256"}
    if _sha256_json(stable) != value["cohort_identity_sha256"]:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_cohort_identity_mismatch")
    value["decision_date"] = parsed_date
    value["included_stock_codes"] = included
    value["excluded_stock_codes"] = excluded
    value["exclusion_reasons"] = parsed_reasons
    return value


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalParentPlanV4:
    """將固定cohort、source clock與所有完成窗口封成不可變計畫。"""

    body_json: str

    def to_dict(self) -> dict[str, Any]:
        raw = self.body_json.encode("utf-8")
        if len(raw) > PARENT_CAPTURE_MAX_BYTES_V4:
            raise TechnicalParentCaptureV4Error("technical_parent_v4_plan_byte_limit")
        body = _parse_json(raw, limit=PARENT_CAPTURE_MAX_BYTES_V4, code="technical_parent_v4_plan_json_invalid")
        _validate_plan_dict(body)
        if not isinstance(body, dict):
            raise TechnicalParentCaptureV4Error("technical_parent_v4_plan_invalid")
        return body

    @classmethod
    def from_dict(cls, payload: object) -> DailyMarketTechnicalParentPlanV4:
        _reject_float_tree(payload)
        _validate_plan_dict(payload)
        return cls(_canonical_json(payload))

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalParentPlanV4:
        return cls.from_dict(_parse_json(raw, limit=PARENT_CAPTURE_MAX_BYTES_V4, code="technical_parent_v4_plan_json_invalid"))

    def to_json(self) -> str:
        return self.body_json

    @property
    def identity_sha256(self) -> str:
        return str(self.to_dict()["parent_plan_identity_sha256"])

    @property
    def content_sha256(self) -> str:
        return _sha256_bytes(self.to_json().encode("utf-8"))

    @property
    def cohort(self) -> DailyMarketTechnicalCohortV4:
        return DailyMarketTechnicalCohortV4.from_dict(self.to_dict()["cohort"])

    @classmethod
    def from_finished_windows(
        cls,
        cohort: DailyMarketTechnicalCohortV4,
        source_clock: DailyMarketTechnicalSourceClockV4,
        finished_windows: Sequence[DailyMarketTechnicalSourceWindow],
    ) -> DailyMarketTechnicalParentPlanV4:
        return build_daily_market_technical_parent_plan_v4(
            cohort, source_clock=source_clock, finished_windows=finished_windows
        )


def build_daily_market_technical_parent_plan_v4(
    cohort: DailyMarketTechnicalCohortV4,
    *,
    source_clock: DailyMarketTechnicalSourceClockV4,
    finished_windows: Sequence[DailyMarketTechnicalSourceWindow],
) -> DailyMarketTechnicalParentPlanV4:
    """只接受同一 finished source-session 的完整 included windows。"""

    if not isinstance(cohort, DailyMarketTechnicalCohortV4):
        raise TypeError("cohort 必須是 DailyMarketTechnicalCohortV4")
    if not isinstance(source_clock, DailyMarketTechnicalSourceClockV4):
        raise TypeError("source_clock 必須是 DailyMarketTechnicalSourceClockV4")
    cohort_payload = cohort.to_dict()
    clock_payload = source_clock.to_dict()
    try:
        _validate_source_clock_payload(clock_payload)
    except ValueError as exc:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_source_clock_invalid") from exc
    if source_clock.identity_sha256 != _sha256_json(clock_payload):
        raise TechnicalParentCaptureV4Error("technical_parent_v4_source_clock_identity_mismatch")
    if source_clock.decision_date != cohort.decision_date:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_date_mismatch")
    if len(cohort.included_stock_codes) > MAX_STOCKS_PER_BATCH_V4 * MAX_BATCHES_V4:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_member_limit")
    if len(finished_windows) != len(cohort.included_stock_codes):
        raise TechnicalParentCaptureV4Error("technical_parent_v4_finished_window_count_mismatch")
    by_code: dict[str, DailyMarketTechnicalSourceWindow] = {}
    for window in finished_windows:
        if not isinstance(window, DailyMarketTechnicalSourceWindow):
            raise TypeError("finished_windows 僅能包含 DailyMarketTechnicalSourceWindow")
        if window.stock_code in by_code:
            raise TechnicalParentCaptureV4Error("technical_parent_v4_duplicate_window")
        if (
            window.database_path != clock_payload["database_path"]
            or window.source_id != clock_payload["source_id"]
            or window.schema_identity_sha256 != clock_payload["schema_identity_sha256"]
            or window.source_file_pin != tuple(tuple(item) for item in cast(Sequence[Sequence[object]], clock_payload["source_file_pin"]))
            or window.source_pin_sha256 != clock_payload["source_pin_sha256"]
            or window.decision_date.isoformat() != clock_payload["decision_date"]
            or window.decision_cutoff.isoformat() != clock_payload["decision_cutoff"]
            or window.availability_status != "unknown"
            or window.source_available_at is not None
        ):
            raise TechnicalParentCaptureV4Error("technical_parent_v4_window_source_clock_mismatch")
        by_code[window.stock_code] = window
    if set(by_code) != set(cohort.included_stock_codes):
        raise TechnicalParentCaptureV4Error("technical_parent_v4_finished_window_members_mismatch")

    snapshots: list[DailyMarketTechnicalFeatureSnapshotV4] = []
    for stock_code in cohort.included_stock_codes:
        snapshots.append(build_daily_market_technical_feature_snapshot_v4(
            by_code[stock_code], source_clock=source_clock
        ))
    method_sha = daily_market_technical_method_contract_v4_sha256()
    source_clock_sha = _sha256_json(clock_payload)
    generation_identity = _sha256_json({
        "schema_version": GENERATION_IDENTITY_SCHEMA_V4,
        "cohort_identity_sha256": cohort.cohort_identity_sha256,
        "source_clock_identity_sha256": source_clock_sha,
        "method_contract_sha256": method_sha,
    })
    source_stock_evidence = [
        {
            "stock_code": snapshot.stock_code,
            "snapshot_identity_sha256": snapshot.snapshot_identity_sha256,
            "source_identity": snapshot.source_identity,
            "raw_source_window_fingerprint_sha256": snapshot.raw_source_window_fingerprint_sha256,
            "source_window_fingerprint_sha256": snapshot.source_window_fingerprint_sha256,
            "calculation_identity_sha256": snapshot.calculation_identity_sha256,
            "row_count": len(snapshot.rows),
            "rule_states": {rule.key: rule.state for rule in snapshot.rules},
        }
        for snapshot in snapshots
    ]
    batches = _batch_layout(cohort.included_stock_codes)
    body: dict[str, object] = {
        "schema_version": PARENT_PLAN_SCHEMA_V4,
        "cohort": cohort_payload,
        "population_state": cohort.population_state,
        "source_clock": clock_payload,
        "source_clock_identity_sha256": source_clock_sha,
        "method_contracts": daily_market_technical_method_contract_v4_payload(),
        "method_contracts_sha256": method_sha,
        "generation_identity_sha256": generation_identity,
        "source_stock_evidence": source_stock_evidence,
        "batches": batches,
        "policy": dict(_POLICY_V4),
    }
    body["parent_plan_identity_sha256"] = _sha256_json(body)
    result = DailyMarketTechnicalParentPlanV4(_canonical_json(body))
    result.to_dict()
    return result


def _batch_layout(stock_codes: Sequence[str]) -> list[dict[str, object]]:
    return [
        {
            "batch_id": f"batch-{index // MAX_STOCKS_PER_BATCH_V4 + 1:02d}",
            "expected_stock_codes": list(stock_codes[index:index + MAX_STOCKS_PER_BATCH_V4]),
            "expected_stock_set_sha256": _sha256_json(list(stock_codes[index:index + MAX_STOCKS_PER_BATCH_V4])),
        }
        for index in range(0, len(stock_codes), MAX_STOCKS_PER_BATCH_V4)
    ]


def _validate_plan_dict(payload: object) -> None:
    if not isinstance(payload, Mapping) or set(payload) != _PLAN_KEYS:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_plan_fields_invalid")
    body = dict(payload)
    if body["schema_version"] != PARENT_PLAN_SCHEMA_V4:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_plan_schema_invalid")
    cohort = DailyMarketTechnicalCohortV4.from_dict(body["cohort"])
    if body["population_state"] != cohort.population_state:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_population_state_mismatch")
    clock = body["source_clock"]
    if not isinstance(clock, Mapping):
        raise TechnicalParentCaptureV4Error("technical_parent_v4_source_clock_invalid")
    try:
        _validate_source_clock_payload(clock)
    except ValueError as exc:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_source_clock_invalid") from exc
    clock_sha = _sha256_json(clock)
    if body["source_clock_identity_sha256"] != clock_sha:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_source_clock_identity_mismatch")
    if _iso_date(clock["decision_date"], "technical_parent_v4_source_clock_date_invalid") != cohort.decision_date:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_date_mismatch")
    method = body["method_contracts"]
    if not isinstance(method, Mapping):
        raise TechnicalParentCaptureV4Error("technical_parent_v4_method_contract_invalid")
    try:
        validate_daily_market_technical_method_contract_v4(
            method, expected_sha256=body["method_contracts_sha256"]
        )
    except ValueError as exc:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_method_contract_invalid") from exc
    generation_sha = _sha256_json({
        "schema_version": GENERATION_IDENTITY_SCHEMA_V4,
        "cohort_identity_sha256": cohort.cohort_identity_sha256,
        "source_clock_identity_sha256": clock_sha,
        "method_contract_sha256": body["method_contracts_sha256"],
    })
    if body["generation_identity_sha256"] != generation_sha:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_generation_identity_mismatch")
    evidence = body["source_stock_evidence"]
    if not isinstance(evidence, list) or len(evidence) != len(cohort.included_stock_codes):
        raise TechnicalParentCaptureV4Error("technical_parent_v4_stock_evidence_invalid")
    expected_rules = {"ma5_20_golden_cross", "kd_golden_cross", "macd_golden_cross", "volume_ratio_20_including_current", "volume_ratio_5_including_current"}
    for item, expected_code in zip(evidence, cohort.included_stock_codes):
        if not isinstance(item, Mapping) or set(item) != {
            "stock_code", "snapshot_identity_sha256", "source_identity",
            "raw_source_window_fingerprint_sha256", "source_window_fingerprint_sha256",
            "calculation_identity_sha256", "row_count", "rule_states",
        }:
            raise TechnicalParentCaptureV4Error("technical_parent_v4_stock_evidence_invalid")
        if item["stock_code"] != expected_code or any(
            not _is_sha256(item[key])
            for key in ("snapshot_identity_sha256", "raw_source_window_fingerprint_sha256", "source_window_fingerprint_sha256", "calculation_identity_sha256")
        ):
            raise TechnicalParentCaptureV4Error("technical_parent_v4_stock_evidence_invalid")
        if not isinstance(item["source_identity"], str) or len(item["source_identity"]) > 160:
            raise TechnicalParentCaptureV4Error("technical_parent_v4_stock_evidence_invalid")
        if type(item["row_count"]) is not int or not 0 <= item["row_count"] <= 120:
            raise TechnicalParentCaptureV4Error("technical_parent_v4_stock_evidence_invalid")
        rule_states = item["rule_states"]
        if not isinstance(rule_states, Mapping) or set(rule_states) != expected_rules or any(
            state not in {"match", "no_match", "unknown"} for state in rule_states.values()
        ):
            raise TechnicalParentCaptureV4Error("technical_parent_v4_stock_evidence_invalid")
    if body["batches"] != _batch_layout(cohort.included_stock_codes):
        raise TechnicalParentCaptureV4Error("technical_parent_v4_batch_layout_invalid")
    if len(body["batches"]) > MAX_BATCHES_V4:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_batch_limit")
    if body["policy"] != _POLICY_V4:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_policy_invalid")
    if not _is_sha256(body["parent_plan_identity_sha256"]):
        raise TechnicalParentCaptureV4Error("technical_parent_v4_plan_identity_invalid")
    if _sha256_json(_identity_payload(body, "parent_plan_identity_sha256")) != body["parent_plan_identity_sha256"]:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_plan_identity_mismatch")
    if len(_canonical_json(body).encode("utf-8")) > PARENT_CAPTURE_MAX_BYTES_V4:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_plan_byte_limit")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalParentReceiptV4:
    """不可變狀態收據；每次進度都新增一份，舊收據保留。"""

    body_json: str

    def to_dict(self) -> dict[str, Any]:
        value = _parse_json(self.body_json, limit=PARENT_RECEIPT_MAX_BYTES_V4, code="technical_parent_v4_receipt_json_invalid")
        _validate_receipt_dict(value)
        if not isinstance(value, dict):
            raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_invalid")
        return value

    @classmethod
    def from_dict(cls, payload: object) -> DailyMarketTechnicalParentReceiptV4:
        _reject_float_tree(payload)
        _validate_receipt_dict(payload)
        return cls(_canonical_json(payload))

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalParentReceiptV4:
        return cls.from_dict(_parse_json(raw, limit=PARENT_RECEIPT_MAX_BYTES_V4, code="technical_parent_v4_receipt_json_invalid"))

    def to_json(self) -> str:
        return self.body_json

    @property
    def identity_sha256(self) -> str:
        return str(self.to_dict()["receipt_identity_sha256"])

    @property
    def content_sha256(self) -> str:
        return _sha256_bytes(self.to_json().encode("utf-8"))

    @property
    def status(self) -> str:
        return str(self.to_dict()["status"])


def _validate_receipt_dict(payload: object) -> None:
    if not isinstance(payload, Mapping) or set(payload) != _RECEIPT_KEYS:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_fields_invalid")
    value = dict(payload)
    if value["schema_version"] != PARENT_RECEIPT_SCHEMA_V4:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_schema_invalid")
    for key in ("parent_plan_identity_sha256", "generation_identity_sha256", "source_clock_identity_sha256"):
        if not _is_sha256(value[key]):
            raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_identity_invalid")
    if type(value["sequence"]) is not int or value["sequence"] < 1:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_sequence_invalid")
    previous = value["previous_receipt_identity_sha256"]
    if previous is not None and not _is_sha256(previous):
        raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_previous_invalid")
    if value["status"] not in _RECEIPT_STATUSES:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_status_invalid")
    artifacts = value["batch_artifacts"]
    if not isinstance(artifacts, list) or len(artifacts) > MAX_BATCHES_V4:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_batch_limit")
    seen: set[str] = set()
    for item in artifacts:
        if not isinstance(item, Mapping) or set(item) != {
            "batch_id", "manifest_path", "manifest_sha256", "generation_identity_sha256",
            "cohort_identity_sha256", "source_clock_identity_sha256", "method_contract_sha256",
            "expected_stock_codes", "expected_stock_set_sha256", "artifact_refs",
        }:
            raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_batch_invalid")
        batch_id = _text(item["batch_id"], limit=16, code="technical_parent_v4_receipt_batch_invalid")
        if batch_id in seen:
            raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_duplicate_batch")
        seen.add(batch_id)
        _text(item["manifest_path"], limit=4096, code="technical_parent_v4_receipt_manifest_path_invalid")
        for key in ("manifest_sha256", "generation_identity_sha256", "cohort_identity_sha256", "source_clock_identity_sha256", "method_contract_sha256", "expected_stock_set_sha256"):
            if not _is_sha256(item[key]):
                raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_batch_hash_invalid")
        codes = _sorted_codes(item["expected_stock_codes"], maximum=MAX_STOCKS_PER_BATCH_V4, code="technical_parent_v4_receipt_batch_codes_invalid")
        if not codes or _sha256_json(list(codes)) != item["expected_stock_set_sha256"]:
            raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_batch_codes_invalid")
        refs = item["artifact_refs"]
        if not isinstance(refs, list) or len(refs) != len(codes):
            raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_artifact_refs_invalid")
        if [ref.get("stock_code") if isinstance(ref, Mapping) else None for ref in refs] != list(codes):
            raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_artifact_refs_invalid")
        for ref in refs:
            if not isinstance(ref, Mapping) or set(ref) != {
                "stock_code", "relative_path", "byte_size", "sha256", "snapshot_identity_sha256",
                "source_identity", "raw_source_window_fingerprint_sha256",
                "source_window_fingerprint_sha256", "calculation_identity_sha256",
            }:
                raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_artifact_ref_invalid")
            _text(ref["relative_path"], limit=256, code="technical_parent_v4_receipt_artifact_ref_invalid")
            if type(ref["byte_size"]) is not int or ref["byte_size"] < 1:
                raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_artifact_ref_invalid")
            for key in ("sha256", "snapshot_identity_sha256", "raw_source_window_fingerprint_sha256", "source_window_fingerprint_sha256", "calculation_identity_sha256"):
                if not _is_sha256(ref[key]):
                    raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_artifact_ref_invalid")
            _text(ref["source_identity"], limit=160, code="technical_parent_v4_receipt_artifact_ref_invalid")
    repository_root = value["repository_output_root"]
    if repository_root is not None:
        _text(repository_root, limit=4096, code="technical_parent_v4_receipt_repository_root_invalid")
        if not Path(repository_root).is_absolute():
            raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_repository_root_invalid")
    writer_version = value["writer_version"]
    if writer_version is not None:
        _text(writer_version, limit=128, code="technical_parent_v4_receipt_writer_version_invalid")
    error_code = value["error_code"]
    if error_code is not None:
        _text(error_code, limit=256, code="technical_parent_v4_receipt_error_code_invalid")
    if value["status"] in {"failed", "cancelled"} and not error_code:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_terminal_reason_required")
    if value["status"] in {"partial", "complete"} and error_code is not None:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_terminal_reason_invalid")
    if value["status"] == "complete" and repository_root is None and artifacts:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_complete_repository_missing")
    if artifacts and (repository_root is None or writer_version is None):
        raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_repository_missing")
    _aware_datetime(value["observed_at"], "technical_parent_v4_receipt_clock_invalid")
    if not _is_sha256(value["receipt_identity_sha256"]):
        raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_identity_invalid")
    if _sha256_json(_identity_payload(value, "receipt_identity_sha256")) != value["receipt_identity_sha256"]:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_identity_mismatch")
    if len(_canonical_json(value).encode("utf-8")) > PARENT_RECEIPT_MAX_BYTES_V4:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_byte_limit")


def _make_receipt(
    *,
    plan: DailyMarketTechnicalParentPlanV4,
    sequence: int,
    previous_receipt_identity_sha256: str | None,
    status: str,
    batch_artifacts: Sequence[Mapping[str, Any]],
    repository_output_root: str | None,
    writer_version: str | None,
    error_code: str | None,
    observed_at: datetime,
) -> DailyMarketTechnicalParentReceiptV4:
    if observed_at.utcoffset() is None:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_clock_invalid")
    body: dict[str, object] = {
        "schema_version": PARENT_RECEIPT_SCHEMA_V4,
        "parent_plan_identity_sha256": plan.identity_sha256,
        "generation_identity_sha256": plan.to_dict()["generation_identity_sha256"],
        "source_clock_identity_sha256": plan.to_dict()["source_clock_identity_sha256"],
        "sequence": sequence,
        "previous_receipt_identity_sha256": previous_receipt_identity_sha256,
        "status": status,
        "batch_artifacts": list(batch_artifacts),
        "repository_output_root": repository_output_root,
        "writer_version": writer_version,
        "error_code": error_code,
        "observed_at": observed_at.astimezone(timezone.utc).isoformat(),
    }
    body["receipt_identity_sha256"] = _sha256_json(body)
    return DailyMarketTechnicalParentReceiptV4.from_dict(body)


def _artifact_ref_to_dict(ref: object) -> dict[str, object]:
    required = (
        "stock_code", "relative_path", "byte_size", "sha256", "snapshot_identity_sha256",
        "source_identity", "raw_source_window_fingerprint_sha256",
        "source_window_fingerprint_sha256", "calculation_identity_sha256",
    )
    if any(not hasattr(ref, name) for name in required):
        raise TechnicalParentCaptureV4Error("technical_parent_v4_child_artifact_ref_invalid")
    return {key: getattr(ref, key) for key in required}


def _batch_artifact_to_dict(
    artifact: object, plan: DailyMarketTechnicalParentPlanV4, *,
    _already_read_exact: bool = False,
) -> dict[str, Any]:
    from app_module.daily_market_technical_snapshot_v4_repository import (
        DailyMarketTechnicalBatchArtifactV4,
        DailyMarketTechnicalSnapshotV4Repository,
    )

    if not isinstance(artifact, DailyMarketTechnicalBatchArtifactV4):
        raise TypeError("artifact 必須是 repository.read_exact() 驗證後的 DailyMarketTechnicalBatchArtifactV4")
    body = plan.to_dict()
    cohort = plan.cohort
    expected_attrs = {
        "generation_identity_sha256": body["generation_identity_sha256"],
        "cohort_identity_sha256": cohort.cohort_identity_sha256,
        "source_clock_identity_sha256": body["source_clock_identity_sha256"],
        "method_contract_sha256": body["method_contracts_sha256"],
        "decision_date": cohort.decision_date,
        "universe_id": cohort.universe_id,
        "population_version": cohort.population_version,
        "included_stock_codes": cohort.included_stock_codes,
        "excluded_stock_codes": cohort.excluded_stock_codes,
        "exclusion_reasons": cohort.exclusion_reasons,
    }
    if any(getattr(artifact, key) != expected for key, expected in expected_attrs.items()):
        raise TechnicalParentCaptureV4Error("technical_parent_v4_child_cohort_mismatch")
    expected_clock = body["source_clock"]
    if artifact.source_clock.identity_sha256 != body["source_clock_identity_sha256"] or artifact.source_clock.to_dict() != expected_clock:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_child_clock_mismatch")
    expected_codes = tuple(artifact.expected_stock_codes)
    batch_by_codes = {
        tuple(item["expected_stock_codes"]): item
        for item in body["batches"]
    }
    batch = batch_by_codes.get(expected_codes)
    if batch is None or artifact.expected_stock_set_sha256 != batch["expected_stock_set_sha256"]:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_child_batch_mismatch")
    if not _is_sha256(artifact.manifest_sha256):
        raise TechnicalParentCaptureV4Error("technical_parent_v4_child_manifest_hash_invalid")
    if not _is_sha256(artifact.generation_identity_sha256):
        raise TechnicalParentCaptureV4Error("technical_parent_v4_child_generation_invalid")
    manifest_path = Path(artifact.manifest_path)
    repository_root = Path(artifact.repository_output_root)
    if not manifest_path.is_absolute() or not repository_root.is_absolute():
        raise TechnicalParentCaptureV4Error("technical_parent_v4_child_path_invalid")
    try:
        canonical_manifest = _resolve_path(manifest_path, strict=True)
        canonical_root = _resolve_path(repository_root, strict=True)
    except (OSError, RuntimeError) as exc:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_child_path_invalid") from exc
    if str(canonical_manifest) != str(manifest_path) or str(canonical_root) != str(repository_root):
        raise TechnicalParentCaptureV4Error("technical_parent_v4_child_path_not_canonical")
    if _already_read_exact:
        # 僅供reader剛完成同次read_exact後投影；writer仍重新讀檔核capture變動。
        verified = artifact
    else:
        repository = DailyMarketTechnicalSnapshotV4Repository(canonical_root)
        verified = repository.read_exact(
            canonical_manifest,
            expected_manifest_sha256=artifact.manifest_sha256,
            expected_cohort_identity_sha256=cohort.cohort_identity_sha256,
            expected_source_clock_sha256=body["source_clock_identity_sha256"],
            expected_method_contract_sha256=body["method_contracts_sha256"],
            expected_decision_date=cohort.decision_date,
        )
    for key in (
        "manifest_path", "manifest_sha256", "generation_identity_sha256",
        "cohort_identity_sha256", "source_clock_identity_sha256", "method_contract_sha256",
        "decision_date", "universe_id", "population_version", "included_stock_codes",
        "excluded_stock_codes", "exclusion_reasons", "expected_stock_codes",
        "expected_stock_set_sha256", "writer_version", "repository_output_root",
    ):
        if getattr(verified, key) != getattr(artifact, key):
            raise TechnicalParentCaptureV4Error("technical_parent_v4_child_changed_during_capture")
    if verified.source_clock.identity_sha256 != artifact.source_clock.identity_sha256 or verified.source_clock.to_dict() != artifact.source_clock.to_dict():
        raise TechnicalParentCaptureV4Error("technical_parent_v4_child_changed_during_capture")
    expected_stock_evidence = {
        item["stock_code"]: item for item in body["source_stock_evidence"]
    }
    snapshots = tuple(verified.snapshots)
    if tuple(snapshot.stock_code for snapshot in snapshots) != expected_codes:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_child_snapshot_members_mismatch")
    for snapshot in snapshots:
        evidence = expected_stock_evidence[snapshot.stock_code]
        if any(getattr(snapshot, field) != evidence[key] for field, key in (
            ("snapshot_identity_sha256", "snapshot_identity_sha256"),
            ("source_identity", "source_identity"),
            ("raw_source_window_fingerprint_sha256", "raw_source_window_fingerprint_sha256"),
            ("source_window_fingerprint_sha256", "source_window_fingerprint_sha256"),
            ("calculation_identity_sha256", "calculation_identity_sha256"),
        )):
            raise TechnicalParentCaptureV4Error("technical_parent_v4_child_snapshot_source_mismatch")
        if (
            len(snapshot.rows) != evidence["row_count"]
            or {rule.key: rule.state for rule in snapshot.rules} != evidence["rule_states"]
        ):
            raise TechnicalParentCaptureV4Error("technical_parent_v4_child_snapshot_evidence_mismatch")
    refs = tuple(_artifact_ref_to_dict(ref) for ref in verified.artifact_refs)
    if tuple(ref["stock_code"] for ref in refs) != expected_codes:
        raise TechnicalParentCaptureV4Error("technical_parent_v4_child_artifact_members_mismatch")
    expected_refs = {
        snapshot.stock_code: snapshot.snapshot_identity_sha256 for snapshot in snapshots
    }
    if any(
        ref["snapshot_identity_sha256"]
        != expected_refs[cast(str, ref["stock_code"])]
        for ref in refs
    ):
        raise TechnicalParentCaptureV4Error("technical_parent_v4_child_artifact_snapshot_mismatch")
    return {
        "batch_id": batch["batch_id"],
        "manifest_path": str(canonical_manifest),
        "manifest_sha256": verified.manifest_sha256,
        "generation_identity_sha256": verified.generation_identity_sha256,
        "cohort_identity_sha256": verified.cohort_identity_sha256,
        "source_clock_identity_sha256": verified.source_clock_identity_sha256,
        "method_contract_sha256": verified.method_contract_sha256,
        "expected_stock_codes": list(expected_codes),
        "expected_stock_set_sha256": verified.expected_stock_set_sha256,
        "artifact_refs": list(refs),
    }


class BoundedDailyMarketTechnicalParentCaptureWriterV4:
    """以 immutable plan 與 append-only receipts 保存跨批進度。"""

    def __init__(
        self,
        output_root: str | Path,
        *,
        research_scope: ResearchCaptureWriteScope | None = None,
        read_only: bool = False,
    ) -> None:
        if type(read_only) is not bool or (read_only and research_scope is not None):
            raise TechnicalParentCaptureV4Error("technical_parent_v4_writer_mode_invalid")
        self._research_scope = research_scope
        self._read_only = read_only
        if research_scope is not None:
            _require(isinstance(research_scope, ResearchCaptureWriteScope), "technical_parent_v4_scope_invalid")
            root = Path(output_root)
            if not root.is_absolute():
                raise TechnicalParentCaptureV4Error("technical_parent_v4_scope_path_absolute_required")
            _safe_path(root)
            research_scope.validate()
            root = _resolve_path(root)
            scope_root = _resolve_path(research_scope.root)
            if root == scope_root or not root.is_relative_to(scope_root):
                raise TechnicalParentCaptureV4Error("technical_parent_v4_scope_escape")
            self.output_root = root
        elif read_only:
            root = Path(output_root)
            if not root.is_absolute():
                raise TechnicalParentCaptureV4Error("technical_parent_v4_readonly_path_absolute_required")
            _safe_path(root)
            self.output_root = _resolve_path(root)
        else:
            from app_module.rule_research_sample_capture import BoundedRuleResearchCaptureWriter

            base = BoundedRuleResearchCaptureWriter(output_root)
            self.output_root = base.output_root
        self.store_root = self.output_root / "technical_parents_v4"

    def _validate_path(self, *, writing: bool) -> None:
        if writing and self._read_only:
            raise TechnicalParentCaptureV4Error("technical_parent_v4_read_only_writer_forbidden")
        _safe_path(self.output_root)
        try:
            if _resolve_path(self.output_root) != self.output_root:
                raise TechnicalParentCaptureV4Error("technical_parent_v4_writer_root_changed")
        except (OSError, RuntimeError) as exc:
            raise TechnicalParentCaptureV4Error("technical_parent_v4_writer_root_changed") from exc
        if self._research_scope is not None:
            if writing:
                self._research_scope.validate()
            scope_root = _resolve_path(self._research_scope.root)
            if self.output_root == scope_root or not self.output_root.is_relative_to(scope_root):
                raise TechnicalParentCaptureV4Error("technical_parent_v4_scope_escape")
        _safe_path(self.store_root)

    def _plan_dir(self, plan_identity_sha256: str) -> Path:
        if not _is_sha256(plan_identity_sha256):
            raise TechnicalParentCaptureV4Error("technical_parent_v4_plan_pin_invalid")
        return self.store_root / "plans" / plan_identity_sha256

    def _receipt_path(self, plan_id: str, receipt_id: str) -> Path:
        if not _is_sha256(receipt_id):
            raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_pin_invalid")
        return self._plan_dir(plan_id) / "receipts" / f"{receipt_id}.json"

    def _read_plan(self, plan_id: str) -> DailyMarketTechnicalParentPlanV4:
        path = self._plan_dir(plan_id) / "plan.json"
        plan = DailyMarketTechnicalParentPlanV4.from_json(
            _read_file(path, PARENT_CAPTURE_MAX_BYTES_V4)
        )
        if plan.identity_sha256 != plan_id:
            raise TechnicalParentCaptureV4Error("technical_parent_v4_plan_pin_mismatch")
        return plan

    def read(
        self,
        plan_identity_sha256: str,
        receipt_identity_sha256: str,
        *,
        expected_receipt_sha256: str,
        expected_plan_sha256: str | None = None,
    ) -> dict[str, Any]:
        """依明示雙 pin 唯讀重開；不挑 latest、不建目錄、不開來源DB。"""

        self._validate_path(writing=False)
        plan = self._read_plan(plan_identity_sha256)
        plan_raw = _read_file(self._plan_dir(plan_identity_sha256) / "plan.json", PARENT_CAPTURE_MAX_BYTES_V4)
        plan_sha = _sha256_bytes(plan_raw)
        if expected_plan_sha256 is not None and plan_sha != expected_plan_sha256:
            raise TechnicalParentCaptureV4Error("technical_parent_v4_plan_hash_mismatch")
        receipt_path = self._receipt_path(plan_identity_sha256, receipt_identity_sha256)
        receipt_raw = _read_file(receipt_path, PARENT_RECEIPT_MAX_BYTES_V4)
        if not _is_sha256(expected_receipt_sha256) or _sha256_bytes(receipt_raw) != expected_receipt_sha256:
            raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_hash_mismatch")
        receipt = DailyMarketTechnicalParentReceiptV4.from_json(receipt_raw)
        body = receipt.to_dict()
        if (
            body["parent_plan_identity_sha256"] != plan_identity_sha256
            or body["generation_identity_sha256"] != plan.to_dict()["generation_identity_sha256"]
            or body["source_clock_identity_sha256"] != plan.to_dict()["source_clock_identity_sha256"]
            or body["receipt_identity_sha256"] != receipt_identity_sha256
        ):
            raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_plan_link_mismatch")
        self._verify_receipt_chain(plan, body)
        self._verify_receipt_semantics(plan, body)
        if body["batch_artifacts"]:
            self._reverify_all_child_batches(plan, body)
        return {
            "plan": plan.to_dict(),
            "plan_sha256": plan_sha,
            "receipt": body,
            "receipt_sha256": _sha256_bytes(receipt_raw),
        }

    def start(
        self,
        plan: DailyMarketTechnicalParentPlanV4,
        *,
        observed_at: datetime | None = None,
    ) -> DailyMarketTechnicalParentReceiptV4:
        self._validate_path(writing=True)
        body = plan.to_dict()
        self._validate_plan_scope(plan)
        plan_id = plan.identity_sha256
        now = observed_at or datetime.now(timezone.utc)
        receipt = _make_receipt(
            plan=plan,
            sequence=1,
            previous_receipt_identity_sha256=None,
            status="partial",
            batch_artifacts=(),
            repository_output_root=None,
            writer_version=None,
            error_code=None,
            observed_at=now,
        )
        receipt_path = self._receipt_path(plan_id, receipt.identity_sha256)

        def publish_start() -> None:
            self._validate_plan_scope(plan)
            receipts_dir = self._plan_dir(plan_id) / "receipts"
            if _path_exists(receipts_dir) and _directory_names(receipts_dir, 2):
                raise TechnicalParentCaptureV4Error("technical_parent_v4_plan_already_started")
            self._write_immutable(self._plan_dir(plan_id) / "plan.json", plan.to_json().encode("utf-8"))
            self._write_immutable(receipt_path, receipt.to_json().encode("utf-8"))

        self._with_lock(publish_start)
        return receipt

    def resume(
        self,
        plan_identity_sha256: str,
        previous_receipt_identity_sha256: str,
        *,
        expected_receipt_sha256: str,
        observed_at: datetime | None = None,
    ) -> DailyMarketTechnicalParentReceiptV4:
        package = self.read(
            plan_identity_sha256,
            previous_receipt_identity_sha256,
            expected_receipt_sha256=expected_receipt_sha256,
        )
        previous = DailyMarketTechnicalParentReceiptV4.from_dict(package["receipt"])
        if previous.status == "complete":
            raise TechnicalParentCaptureV4Error("technical_parent_v4_complete_cannot_resume")
        plan = DailyMarketTechnicalParentPlanV4.from_dict(package["plan"])
        receipt = _make_receipt(
            plan=plan,
            sequence=int(package["receipt"]["sequence"]) + 1,
            previous_receipt_identity_sha256=previous.identity_sha256,
            status="partial",
            batch_artifacts=package["receipt"]["batch_artifacts"],
            repository_output_root=package["receipt"]["repository_output_root"],
            writer_version=package["receipt"]["writer_version"],
            error_code=None,
            observed_at=observed_at or datetime.now(timezone.utc),
        )
        return self._append_receipt(plan, receipt)

    def record_verified_batch(
        self,
        plan_identity_sha256: str,
        previous_receipt_identity_sha256: str,
        *,
        expected_previous_receipt_sha256: str,
        artifact: DailyMarketTechnicalBatchArtifactV4,
        observed_at: datetime | None = None,
    ) -> DailyMarketTechnicalParentReceiptV4:
        package = self.read(
            plan_identity_sha256,
            previous_receipt_identity_sha256,
            expected_receipt_sha256=expected_previous_receipt_sha256,
        )
        plan = DailyMarketTechnicalParentPlanV4.from_dict(package["plan"])
        previous = DailyMarketTechnicalParentReceiptV4.from_dict(package["receipt"])
        if previous.status != "partial":
            raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_not_resumable")
        batch_ref = _batch_artifact_to_dict(artifact, plan)
        previous_refs = list(previous.to_dict()["batch_artifacts"])
        if any(item["batch_id"] == batch_ref["batch_id"] for item in previous_refs):
            existing = next(item for item in previous_refs if item["batch_id"] == batch_ref["batch_id"])
            if existing == batch_ref:
                return previous
            raise TechnicalParentCaptureV4Error("technical_parent_v4_batch_rewrite_refused")
        expected_ids = [item["batch_id"] for item in plan.to_dict()["batches"]]
        next_id = next((key for key in expected_ids if key not in {item["batch_id"] for item in previous_refs}), None)
        if batch_ref["batch_id"] != next_id:
            raise TechnicalParentCaptureV4Error("technical_parent_v4_batch_order_invalid")
        repository_root = str(Path(artifact.repository_output_root))
        writer_version = artifact.writer_version
        if previous_refs:
            if (
                previous.to_dict()["repository_output_root"] != repository_root
                or previous.to_dict()["writer_version"] != writer_version
            ):
                raise TechnicalParentCaptureV4Error("technical_parent_v4_child_root_or_writer_changed")
        if batch_ref["generation_identity_sha256"] != plan.to_dict()["generation_identity_sha256"]:
            raise TechnicalParentCaptureV4Error("technical_parent_v4_child_generation_mismatch")
        next_receipt = _make_receipt(
            plan=plan,
            sequence=int(previous.to_dict()["sequence"]) + 1,
            previous_receipt_identity_sha256=previous.identity_sha256,
            status="partial",
            batch_artifacts=(*previous_refs, batch_ref),
            repository_output_root=repository_root,
            writer_version=writer_version,
            error_code=None,
            observed_at=observed_at or datetime.now(timezone.utc),
        )
        self._verify_receipt_semantics(plan, next_receipt.to_dict())
        return self._append_receipt(plan, next_receipt)

    def mark_terminal(
        self,
        plan_identity_sha256: str,
        previous_receipt_identity_sha256: str,
        *,
        expected_previous_receipt_sha256: str,
        status: Literal["failed", "cancelled"],
        error_code: str,
        observed_at: datetime | None = None,
    ) -> DailyMarketTechnicalParentReceiptV4:
        if status not in {"failed", "cancelled"}:
            raise TechnicalParentCaptureV4Error("technical_parent_v4_terminal_status_invalid")
        package = self.read(
            plan_identity_sha256,
            previous_receipt_identity_sha256,
            expected_receipt_sha256=expected_previous_receipt_sha256,
        )
        plan = DailyMarketTechnicalParentPlanV4.from_dict(package["plan"])
        previous = DailyMarketTechnicalParentReceiptV4.from_dict(package["receipt"])
        if previous.status != "partial":
            raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_not_resumable")
        _text(error_code, limit=256, code="technical_parent_v4_terminal_reason_required")
        body = previous.to_dict()
        receipt = _make_receipt(
            plan=plan,
            sequence=int(body["sequence"]) + 1,
            previous_receipt_identity_sha256=previous.identity_sha256,
            status=status,
            batch_artifacts=body["batch_artifacts"],
            repository_output_root=body["repository_output_root"],
            writer_version=body["writer_version"],
            error_code=error_code,
            observed_at=observed_at or datetime.now(timezone.utc),
        )
        return self._append_receipt(plan, receipt)

    def complete(
        self,
        plan_identity_sha256: str,
        previous_receipt_identity_sha256: str,
        *,
        expected_previous_receipt_sha256: str,
        observed_at: datetime | None = None,
    ) -> DailyMarketTechnicalParentReceiptV4:
        package = self.read(
            plan_identity_sha256,
            previous_receipt_identity_sha256,
            expected_receipt_sha256=expected_previous_receipt_sha256,
        )
        plan = DailyMarketTechnicalParentPlanV4.from_dict(package["plan"])
        previous = DailyMarketTechnicalParentReceiptV4.from_dict(package["receipt"])
        if previous.status != "partial":
            raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_not_resumable")
        batch_items = previous.to_dict()["batch_artifacts"]
        if len(batch_items) != len(plan.to_dict()["batches"]):
            raise TechnicalParentCaptureV4Error("technical_parent_v4_parent_incomplete")
        if plan.to_dict()["batches"]:
            if previous.to_dict()["repository_output_root"] is None:
                raise TechnicalParentCaptureV4Error("technical_parent_v4_child_root_missing")
            self._reverify_all_child_batches(plan, previous.to_dict())
        receipt = _make_receipt(
            plan=plan,
            sequence=int(previous.to_dict()["sequence"]) + 1,
            previous_receipt_identity_sha256=previous.identity_sha256,
            status="complete",
            batch_artifacts=batch_items,
            repository_output_root=previous.to_dict()["repository_output_root"],
            writer_version=previous.to_dict()["writer_version"],
            error_code=None,
            observed_at=observed_at or datetime.now(timezone.utc),
        )
        self._verify_receipt_semantics(plan, receipt.to_dict())
        return self._append_receipt(plan, receipt)

    def _reverify_all_child_batches(self, plan: DailyMarketTechnicalParentPlanV4, receipt: Mapping[str, Any]) -> None:
        from app_module.daily_market_technical_snapshot_v4_repository import DailyMarketTechnicalSnapshotV4Repository

        if not receipt["batch_artifacts"]:
            if receipt["repository_output_root"] is not None:
                raise TechnicalParentCaptureV4Error("technical_parent_v4_empty_child_root_mismatch")
            return
        repository = DailyMarketTechnicalSnapshotV4Repository(receipt["repository_output_root"])
        for child in receipt["batch_artifacts"]:
            verified = repository.read_exact(
                child["manifest_path"],
                expected_manifest_sha256=child["manifest_sha256"],
                expected_cohort_identity_sha256=plan.cohort.cohort_identity_sha256,
                expected_source_clock_sha256=plan.to_dict()["source_clock_identity_sha256"],
                expected_method_contract_sha256=plan.to_dict()["method_contracts_sha256"],
                expected_decision_date=plan.cohort.decision_date,
            )
            actual = _batch_artifact_to_dict(verified, plan, _already_read_exact=True)
            if actual != child:
                raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_child_pin_mismatch")

    def _validate_plan_scope(self, plan: DailyMarketTechnicalParentPlanV4) -> None:
        if self._research_scope is None:
            return
        self._research_scope.validate()
        database_path = plan.to_dict()["source_clock"]["database_path"]
        if database_path != str(self._research_scope.source_database):
            raise TechnicalParentCaptureV4Error("technical_parent_v4_scope_source_mismatch")

    def _verify_receipt_chain(
        self, plan: DailyMarketTechnicalParentPlanV4, current: Mapping[str, Any]
    ) -> None:
        plan_id = plan.identity_sha256
        newer = current
        while newer["sequence"] > 1:
            previous_id = newer["previous_receipt_identity_sha256"]
            if previous_id is None:
                raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_chain_invalid")
            previous_raw = _read_file(self._receipt_path(plan_id, previous_id), PARENT_RECEIPT_MAX_BYTES_V4)
            previous = DailyMarketTechnicalParentReceiptV4.from_json(previous_raw).to_dict()
            if (
                previous["parent_plan_identity_sha256"] != plan_id
                or previous["generation_identity_sha256"] != current["generation_identity_sha256"]
                or previous["source_clock_identity_sha256"] != current["source_clock_identity_sha256"]
                or previous["sequence"] + 1 != newer["sequence"]
                or previous["receipt_identity_sha256"] != previous_id
            ):
                raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_chain_invalid")
            prior_artifacts = previous["batch_artifacts"]
            newer_artifacts = newer["batch_artifacts"]
            if newer_artifacts[:len(prior_artifacts)] != prior_artifacts:
                raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_history_changed")
            added = len(newer_artifacts) - len(prior_artifacts)
            if added not in {0, 1}:
                raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_transition_invalid")
            if previous["status"] == "complete":
                raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_after_complete")
            if previous["status"] in {"failed", "cancelled"}:
                if newer["status"] != "partial" or added != 0:
                    raise TechnicalParentCaptureV4Error("technical_parent_v4_resume_transition_invalid")
            elif newer["status"] in {"failed", "cancelled", "complete"} and added != 0:
                raise TechnicalParentCaptureV4Error("technical_parent_v4_terminal_transition_invalid")
            elif newer["status"] == "partial" and added == 0 and previous["status"] != "partial":
                raise TechnicalParentCaptureV4Error("technical_parent_v4_partial_transition_invalid")
            newer = previous
        if (
            newer["sequence"] != 1
            or newer["previous_receipt_identity_sha256"] is not None
            or newer["batch_artifacts"]
            or newer["status"] != "partial"
        ):
            raise TechnicalParentCaptureV4Error("technical_parent_v4_initial_receipt_invalid")

    def _verify_receipt_semantics(
        self, plan: DailyMarketTechnicalParentPlanV4, receipt: Mapping[str, Any]
    ) -> None:
        body = plan.to_dict()
        artifacts = receipt["batch_artifacts"]
        expected_batches = body["batches"]
        expected_by_id = {item["batch_id"]: item for item in expected_batches}
        if len(artifacts) > len(expected_batches):
            raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_has_extra_batches")
        expected_prefix = [item["batch_id"] for item in expected_batches[:len(artifacts)]]
        if [item["batch_id"] for item in artifacts] != expected_prefix:
            raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_batch_order_invalid")
        source_evidence = {item["stock_code"]: item for item in body["source_stock_evidence"]}
        for child in artifacts:
            batch = expected_by_id.get(child["batch_id"])
            if batch is None or child["expected_stock_codes"] != batch["expected_stock_codes"]:
                raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_batch_members_mismatch")
            if (
                child["generation_identity_sha256"] != body["generation_identity_sha256"]
                or child["cohort_identity_sha256"] != plan.cohort.cohort_identity_sha256
                or child["source_clock_identity_sha256"] != body["source_clock_identity_sha256"]
                or child["method_contract_sha256"] != body["method_contracts_sha256"]
            ):
                raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_batch_identity_mismatch")
            for ref in child["artifact_refs"]:
                evidence = source_evidence[ref["stock_code"]]
                for ref_key, evidence_key in (
                    ("snapshot_identity_sha256", "snapshot_identity_sha256"),
                    ("source_identity", "source_identity"),
                    ("raw_source_window_fingerprint_sha256", "raw_source_window_fingerprint_sha256"),
                    ("source_window_fingerprint_sha256", "source_window_fingerprint_sha256"),
                    ("calculation_identity_sha256", "calculation_identity_sha256"),
                ):
                    if ref[ref_key] != evidence[evidence_key]:
                        raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_stock_pin_mismatch")
        if receipt["status"] == "complete" and len(artifacts) != len(expected_batches):
            raise TechnicalParentCaptureV4Error("technical_parent_v4_false_complete")

    def _append_receipt(
        self,
        plan: DailyMarketTechnicalParentPlanV4,
        receipt: DailyMarketTechnicalParentReceiptV4,
    ) -> DailyMarketTechnicalParentReceiptV4:
        self._validate_path(writing=True)
        plan_id = plan.identity_sha256
        receipt_id = receipt.identity_sha256
        path = self._receipt_path(plan_id, receipt_id)
        raw = receipt.to_json().encode("utf-8")

        def append() -> None:
            self._validate_plan_scope(plan)
            self._read_plan(plan_id)
            body = receipt.to_dict()
            previous_id = body["previous_receipt_identity_sha256"]
            if previous_id is None:
                raise TechnicalParentCaptureV4Error("technical_parent_v4_initial_receipt_required")
            previous_path = self._receipt_path(plan_id, previous_id)
            prior_raw = _read_file(previous_path, PARENT_RECEIPT_MAX_BYTES_V4)
            prior = DailyMarketTechnicalParentReceiptV4.from_json(prior_raw).to_dict()
            if (
                prior["parent_plan_identity_sha256"] != plan_id
                or body["sequence"] != prior["sequence"] + 1
            ):
                raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_chain_invalid")
            receipts_dir = self._plan_dir(plan_id) / "receipts"
            if _path_exists(receipts_dir):
                for name in _directory_names(receipts_dir, PARENT_CAPTURE_MAX_RETAINED_ENTRIES_V4 + 1):
                    if name.endswith(".json") and name != path.name:
                        candidate_raw = _read_file(receipts_dir / name, PARENT_RECEIPT_MAX_BYTES_V4)
                        candidate = DailyMarketTechnicalParentReceiptV4.from_json(candidate_raw).to_dict()
                        if candidate["previous_receipt_identity_sha256"] == previous_id:
                            raise TechnicalParentCaptureV4Error("technical_parent_v4_receipt_branch_refused")
            self._write_immutable(path, raw)

        self._with_lock(append)
        return receipt

    def _with_lock(self, action: Any) -> None:
        self._validate_path(writing=True)
        _path_mkdir(self.store_root, parents=True, exist_ok=True)
        self._validate_path(writing=True)
        lock_path = self.store_root / ".writer.lock"
        with _FileLockV4(lock_path):
            self._validate_path(writing=True)
            action()
            self._enforce_store_budget()

    def _write_immutable(self, path: Path, raw: bytes) -> None:
        self._validate_path(writing=True)
        if _path_exists(path):
            if _read_file(path, max(len(raw), PARENT_CAPTURE_MAX_BYTES_V4)) != raw:
                raise TechnicalParentCaptureV4Error("technical_parent_v4_immutable_file_conflict")
            return
        _path_mkdir(path.parent, parents=True, exist_ok=True)
        self._validate_path(writing=True)
        staging = path.parent / f".partial-{uuid4().hex}.tmp"
        _write_file(staging, raw)
        if _read_file(staging, max(len(raw), PARENT_CAPTURE_MAX_BYTES_V4)) != raw:
            raise TechnicalParentCaptureV4Error("technical_parent_v4_staging_readback_mismatch")
        self._validate_path(writing=True)
        try:
            _path_rename(staging, path)
        except FileExistsError:
            _path_unlink(staging)
            if _read_file(path, max(len(raw), PARENT_CAPTURE_MAX_BYTES_V4)) != raw:
                raise TechnicalParentCaptureV4Error("technical_parent_v4_immutable_file_conflict")

    def _enforce_store_budget(self) -> None:
        if not _path_is_dir(self.store_root):
            return
        total = count = 0
        pending = [self.store_root]
        while pending:
            directory = pending.pop()
            _safe_path(directory)
            with os.scandir(to_internal_io_path(directory)) as entries:
                for entry in entries:
                    path = directory / entry.name
                    _safe_path(path)
                    if entry.name == ".writer.lock":
                        continue
                    count += 1
                    if count > PARENT_CAPTURE_MAX_RETAINED_ENTRIES_V4:
                        raise TechnicalParentCaptureV4Error("technical_parent_v4_retention_entry_limit")
                    info = os.stat(to_internal_io_path(path))
                    if stat.S_ISDIR(info.st_mode):
                        pending.append(path)
                    elif stat.S_ISREG(info.st_mode):
                        total += info.st_size
                        if total > PARENT_CAPTURE_MAX_RETAINED_BYTES_V4:
                            raise TechnicalParentCaptureV4Error("technical_parent_v4_retention_byte_limit")
                    else:
                        raise TechnicalParentCaptureV4Error("technical_parent_v4_store_entry_invalid")


class _FileLockV4:
    """跨程序可自動釋放的 v4 writer lock。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: Any = None

    def __enter__(self) -> _FileLockV4:
        _safe_path(self.path)
        self.handle = _path_open(self.path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt

                self.handle.seek(0, os.SEEK_END)
                if self.handle.tell() == 0:
                    self.handle.write(b"\0")
                    self.handle.flush()
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                lock_api = cast(_FcntlAPI, fcntl)
                lock_api.flock(self.handle.fileno(), lock_api.LOCK_EX | lock_api.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            self.handle = None
            raise TechnicalParentCaptureV4Error("technical_parent_v4_writer_busy") from exc
        return self

    def __exit__(self, *_args: object) -> None:
        handle = self.handle
        self.handle = None
        if handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                lock_api = cast(_FcntlAPI, fcntl)
                lock_api.flock(handle.fileno(), lock_api.LOCK_UN)
        finally:
            handle.close()


def read_daily_market_technical_parent_capture_v4(
    output_root: str | Path,
    plan_identity_sha256: str,
    receipt_identity_sha256: str,
    *,
    expected_receipt_sha256: str,
    expected_plan_sha256: str | None = None,
) -> dict[str, Any]:
    """新程序唯讀重開明示parent receipt；不查來源DB或latest。"""

    reader = BoundedDailyMarketTechnicalParentCaptureWriterV4(output_root, read_only=True)
    package = reader.read(
        plan_identity_sha256,
        receipt_identity_sha256,
        expected_plan_sha256=expected_plan_sha256,
        expected_receipt_sha256=expected_receipt_sha256,
    )
    # read 已核receipt chain／語義及每個原child；不再重讀同份已核包。
    return package
