"""保存已核驗的完整 v4 技術研究母體與 parent 收據引用。

此模組只保存/重開固定 full-cohort 計畫及已完成 parent 引用；不讀行情資料庫、
不呼叫 producer、不推論規則，也不選擇 latest。來源可得性仍為 unknown、PIT eligibility
仍為 false。Look-ahead 自查：全母體與來源時計在首次保存前固定；重開只核驗計畫、收據與
各段完整 parent，不查目前行情或回填決策日後資料。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Literal, NoReturn, cast
from uuid import uuid4

from app_module.daily_market_technical_method_contract_v4 import (
    daily_market_technical_method_contract_v4_payload,
    daily_market_technical_method_contract_v4_sha256,
    validate_daily_market_technical_method_contract_v4,
)
from app_module.daily_market_technical_read_session import DailyMarketTechnicalSourceClockV4
from app_module.daily_market_technical_snapshot_v4_repository import (
    DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_RETAINED_BYTES,
    DailyMarketTechnicalSnapshotV4RepositoryError,
    _canonical_directory,
    _canonical_realpath,
    _ensure_directory,
    _is_link_or_reparse,
    _lstat_optional,
    _publish_temp_no_replace,
    _read_bounded_file,
    _source_clock_from_payload,
)
from app_module.personal_data_paths import to_internal_io_path
from app_module.rule_research_sample_capture import (
    BoundedRuleResearchCaptureWriter,
    ResearchCaptureWriteScope,
    RuleSampleCaptureError,
    _safe_path,
)
from app_module.rule_research_technical_parent_capture_v4 import (
    BoundedDailyMarketTechnicalParentCaptureWriterV4,
    DailyMarketTechnicalCohortV4,
    DailyMarketTechnicalParentCaptureV4VerifiedRead,
    TechnicalParentCaptureV4Error,
    _FileLockV4,
    read_daily_market_technical_parent_capture_v4,
)


DAILY_MARKET_TECHNICAL_UNIVERSE_V4_STORE_DIRECTORY = (
    "daily_market_technical_universe_v4"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_PLAN_SCHEMA = (
    "daily-market-technical-universe-v4-plan.v1"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_GENERATION_SCHEMA = (
    "daily-market-technical-universe-v4-generation-identity.v1"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_RECEIPT_SCHEMA = (
    "daily-market-technical-universe-v4-receipt.v1"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_PARENT_REFERENCE_SCHEMA = (
    "daily-market-technical-universe-v4-parent-reference.v1"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_COHORT_SCHEMA = (
    "daily-market-technical-universe-v4-cohort.v1"
)
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS = 100_000
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_SEGMENT_STOCKS = 256
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_PLAN_BYTES = 56 * 1024 * 1024
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_RECEIPT_BYTES = 4 * 1024 * 1024
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_RETAINED_BYTES = (
    DAILY_MARKET_TECHNICAL_SNAPSHOT_V4_MAX_RETAINED_BYTES
)
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_STORE_ENTRIES = 100_000
DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_SEGMENTS = 391

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_PLAN_KEYS = frozenset({
    "schema_version",
    "cohort",
    "source_clock",
    "source_clock_identity_sha256",
    "method_contracts",
    "method_contracts_sha256",
    "generation_identity_sha256",
    "segments",
    "plan_identity_sha256",
})
_COHORT_KEYS = frozenset({
    "schema_version",
    "universe_id",
    "population_version",
    "decision_date",
    "raw_stock_code_count",
    "declared_stock_codes",
    "duplicate_stock_codes",
    "included_stock_codes",
    "excluded_stock_codes",
    "exclusion_reasons",
    "cohort_identity_sha256",
})
_RECEIPT_KEYS = frozenset({
    "schema_version",
    "generation_identity_sha256",
    "plan_identity_sha256",
    "sequence",
    "previous_receipt_identity_sha256",
    "previous_receipt_sha256",
    "status",
    "counts",
    "segment_reference",
    "last_parent_reference",
    "error_code",
    "receipt_identity_sha256",
})
_COUNT_KEYS = frozenset({
    "declared_count",
    "included_count",
    "excluded_count",
    "processed_count",
    "pending_count",
    "missing_data_count",
    "missing_data_pending_count",
})
_STATUS_VALUES = frozenset({"partial", "cancelled", "failed", "complete"})


class DailyMarketTechnicalUniverseV4StoreError(ValueError):
    """完整技術研究 store 的穩定錯誤碼。"""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


def _fail(code: str, message: str | None = None) -> NoReturn:
    raise DailyMarketTechnicalUniverseV4StoreError(code, message)


def _check_universe_read_cancelled(
    cancel_callback: Callable[[], bool] | None,
) -> None:
    if cancel_callback is None:
        return
    try:
        cancelled = cancel_callback()
    except Exception as exc:
        raise DailyMarketTechnicalUniverseV4StoreError(
            "technical_universe_v4_read_cancel_check_failed", str(exc)
        ) from exc
    if type(cancelled) is not bool:
        _fail("technical_universe_v4_read_cancel_callback_invalid")
    if cancelled:
        _fail("technical_universe_v4_read_cancelled")


def _reject_float_tree(value: object) -> None:
    if isinstance(value, float):
        _fail("technical_universe_v4_float_forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("technical_universe_v4_json_key_invalid")
            _reject_float_tree(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_float_tree(item)


def _canonical_json(value: object) -> str:
    _reject_float_tree(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise DailyMarketTechnicalUniverseV4StoreError(
            "technical_universe_v4_json_invalid"
        ) from exc


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
            _fail("technical_universe_v4_byte_limit")

        def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, item in pairs:
                if key in result:
                    _fail("technical_universe_v4_duplicate_json_key")
                result[key] = item
            return result

        def reject_constant(value: str) -> NoReturn:
            _fail("technical_universe_v4_json_constant_invalid", value)

        def reject_float(value: str) -> NoReturn:
            _fail("technical_universe_v4_float_forbidden", value)

        value = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
            parse_float=reject_float,
        )
        _reject_float_tree(value)
        if _canonical_json(value).encode("utf-8") != encoded:
            _fail("technical_universe_v4_json_noncanonical")
        return value
    except DailyMarketTechnicalUniverseV4StoreError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalUniverseV4StoreError(code) from exc


def _text(value: object, *, limit: int, code: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        _fail(code)
    return value


def _date(value: object, code: str) -> date:
    if not isinstance(value, str):
        _fail(code)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise DailyMarketTechnicalUniverseV4StoreError(code) from exc
    if parsed.isoformat() != value:
        _fail(code)
    return parsed


def _normalize_stock_code(value: object) -> str:
    if not isinstance(value, str):
        _fail("technical_universe_v4_stock_code_invalid")
    normalized = value.strip().upper()
    if _STOCK_CODE_RE.fullmatch(normalized) is None:
        _fail("technical_universe_v4_stock_code_invalid")
    return normalized


def _sorted_codes(value: object, *, maximum: int, code: str) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        _fail(code)
    codes = tuple(_text(item, limit=16, code=code) for item in value)
    if any(_STOCK_CODE_RE.fullmatch(item) is None for item in codes):
        _fail(code)
    if codes != tuple(sorted(set(codes))):
        _fail(code)
    return codes


def _source_clock_from_typed_or_payload(
    value: DailyMarketTechnicalSourceClockV4 | object,
) -> DailyMarketTechnicalSourceClockV4:
    if isinstance(value, DailyMarketTechnicalSourceClockV4):
        payload = value.to_dict()
        try:
            verified = _source_clock_from_payload(payload)
        except (DailyMarketTechnicalSnapshotV4RepositoryError, TypeError, ValueError) as exc:
            raise DailyMarketTechnicalUniverseV4StoreError(
                "technical_universe_v4_source_clock_invalid"
            ) from exc
        if verified.identity_sha256 != value.identity_sha256:
            _fail("technical_universe_v4_source_clock_identity_mismatch")
        return verified
    try:
        return _source_clock_from_payload(value)
    except (DailyMarketTechnicalSnapshotV4RepositoryError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalUniverseV4StoreError(
            "technical_universe_v4_source_clock_invalid"
        ) from exc


def daily_market_technical_source_clock_v4_from_dict(
    payload: object,
) -> DailyMarketTechnicalSourceClockV4:
    """嚴格將已保存的 v4 時鐘 payload 轉回 typed DTO；不開啟來源資料庫。"""

    return _source_clock_from_typed_or_payload(payload)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseV4Cohort:
    """由原始代碼和明示排除形成完整、去重的固定母體。"""

    universe_id: str
    population_version: str
    decision_date: date
    raw_stock_code_count: int
    declared_stock_codes: tuple[str, ...]
    duplicate_stock_codes: tuple[tuple[str, int], ...]
    included_stock_codes: tuple[str, ...]
    excluded_stock_codes: tuple[str, ...]
    exclusion_reasons: tuple[tuple[str, str], ...]
    cohort_identity_sha256: str

    def __post_init__(self) -> None:
        _validate_cohort_payload(self.to_dict())

    @classmethod
    def create(
        cls,
        *,
        universe_id: str,
        population_version: str,
        decision_date: date,
        raw_stock_codes: Sequence[str],
        excluded_stock_codes: Sequence[str] = (),
        exclusion_reasons: Mapping[str, str] | Sequence[tuple[str, str]] = (),
    ) -> DailyMarketTechnicalUniverseV4Cohort:
        if not isinstance(raw_stock_codes, Sequence) or isinstance(raw_stock_codes, (str, bytes)):
            raise TypeError("raw_stock_codes 必須是股票代碼序列")
        if not isinstance(excluded_stock_codes, Sequence) or isinstance(excluded_stock_codes, (str, bytes)):
            raise TypeError("excluded_stock_codes 必須是股票代碼序列")
        if isinstance(decision_date, datetime) or not isinstance(decision_date, date):
            _fail("technical_universe_v4_decision_date_invalid")
        normalized = tuple(_normalize_stock_code(item) for item in raw_stock_codes)
        counts: dict[str, int] = {}
        for code in normalized:
            counts[code] = counts.get(code, 0) + 1
        declared = tuple(sorted(counts))
        if len(declared) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS:
            _fail("technical_universe_v4_declared_stock_limit")
        duplicates = tuple(sorted(
            (code, occurrences)
            for code, occurrences in counts.items()
            if occurrences > 1
        ))
        excluded = tuple(sorted(_normalize_stock_code(item) for item in excluded_stock_codes))
        if len(set(excluded)) != len(excluded):
            _fail("technical_universe_v4_duplicate_exclusion")
        if not set(excluded).issubset(declared):
            _fail("technical_universe_v4_exclusion_outside_population")
        if isinstance(exclusion_reasons, Mapping):
            reason_items = tuple(exclusion_reasons.items())
        elif isinstance(exclusion_reasons, Sequence) and not isinstance(exclusion_reasons, (str, bytes)):
            reason_items = tuple(exclusion_reasons)
        else:
            raise TypeError("exclusion_reasons 必須是代碼理由 mapping 或 pair 序列")
        reasons_by_code: dict[str, str] = {}
        for item in reason_items:
            if not isinstance(item, Sequence) or isinstance(item, (str, bytes)) or len(item) != 2:
                _fail("technical_universe_v4_exclusion_reason_invalid")
            code = _normalize_stock_code(item[0])
            reason = _text(item[1], limit=512, code="technical_universe_v4_exclusion_reason_invalid")
            if code in reasons_by_code:
                _fail("technical_universe_v4_duplicate_exclusion_reason")
            reasons_by_code[code] = reason
        if set(reasons_by_code) != set(excluded):
            _fail("technical_universe_v4_exclusion_reasons_mismatch")
        included = tuple(code for code in declared if code not in set(excluded))
        body: dict[str, object] = {
            "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_V4_COHORT_SCHEMA,
            "universe_id": _text(universe_id, limit=96, code="technical_universe_v4_universe_id_invalid"),
            "population_version": _text(population_version, limit=128, code="technical_universe_v4_population_version_invalid"),
            "decision_date": decision_date.isoformat(),
            "raw_stock_code_count": len(normalized),
            "declared_stock_codes": list(declared),
            "duplicate_stock_codes": [
                {"stock_code": code, "occurrences": occurrences}
                for code, occurrences in duplicates
            ],
            "included_stock_codes": list(included),
            "excluded_stock_codes": list(excluded),
            "exclusion_reasons": {code: reason for code, reason in sorted(reasons_by_code.items())},
        }
        identity = _sha256_json(body)
        return cls(
            universe_id=cast(str, body["universe_id"]),
            population_version=cast(str, body["population_version"]),
            decision_date=decision_date,
            raw_stock_code_count=len(normalized),
            declared_stock_codes=declared,
            duplicate_stock_codes=duplicates,
            included_stock_codes=included,
            excluded_stock_codes=excluded,
            exclusion_reasons=tuple(sorted(reasons_by_code.items())),
            cohort_identity_sha256=identity,
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_V4_COHORT_SCHEMA,
            "universe_id": self.universe_id,
            "population_version": self.population_version,
            "decision_date": self.decision_date.isoformat(),
            "raw_stock_code_count": self.raw_stock_code_count,
            "declared_stock_codes": list(self.declared_stock_codes),
            "duplicate_stock_codes": [
                {"stock_code": code, "occurrences": count}
                for code, count in self.duplicate_stock_codes
            ],
            "included_stock_codes": list(self.included_stock_codes),
            "excluded_stock_codes": list(self.excluded_stock_codes),
            "exclusion_reasons": {code: reason for code, reason in self.exclusion_reasons},
            "cohort_identity_sha256": self.cohort_identity_sha256,
        }
        _validate_cohort_payload(payload)
        return payload

    @classmethod
    def from_dict(cls, payload: object) -> DailyMarketTechnicalUniverseV4Cohort:
        parsed = _validate_cohort_payload(payload)
        return cls(
            universe_id=parsed["universe_id"],
            population_version=parsed["population_version"],
            decision_date=parsed["decision_date"],
            raw_stock_code_count=parsed["raw_stock_code_count"],
            declared_stock_codes=parsed["declared_stock_codes"],
            duplicate_stock_codes=parsed["duplicate_stock_codes"],
            included_stock_codes=parsed["included_stock_codes"],
            excluded_stock_codes=parsed["excluded_stock_codes"],
            exclusion_reasons=parsed["exclusion_reasons"],
            cohort_identity_sha256=parsed["cohort_identity_sha256"],
        )

    @property
    def population_state(self) -> Literal["included", "all_excluded", "empty"]:
        if self.included_stock_codes:
            return "included"
        if self.excluded_stock_codes:
            return "all_excluded"
        return "empty"


def _validate_cohort_payload(payload: object) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or set(payload) != _COHORT_KEYS:
        _fail("technical_universe_v4_cohort_fields_invalid")
    value = dict(payload)
    if value["schema_version"] != DAILY_MARKET_TECHNICAL_UNIVERSE_V4_COHORT_SCHEMA:
        _fail("technical_universe_v4_cohort_schema_invalid")
    universe_id = _text(value["universe_id"], limit=96, code="technical_universe_v4_universe_id_invalid")
    population_version = _text(value["population_version"], limit=128, code="technical_universe_v4_population_version_invalid")
    parsed_date = _date(value["decision_date"], "technical_universe_v4_decision_date_invalid")
    declared = _sorted_codes(value["declared_stock_codes"], maximum=DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS, code="technical_universe_v4_declared_stock_codes_invalid")
    included = _sorted_codes(value["included_stock_codes"], maximum=DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS, code="technical_universe_v4_included_stock_codes_invalid")
    excluded = _sorted_codes(value["excluded_stock_codes"], maximum=DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS, code="technical_universe_v4_excluded_stock_codes_invalid")
    if set(included).intersection(excluded) or tuple(sorted((*included, *excluded))) != declared:
        _fail("technical_universe_v4_cohort_membership_invalid")
    raw_count = value["raw_stock_code_count"]
    if type(raw_count) is not int or raw_count < len(declared):
        _fail("technical_universe_v4_raw_stock_code_count_invalid")
    duplicates_value = value["duplicate_stock_codes"]
    if not isinstance(duplicates_value, list):
        _fail("technical_universe_v4_duplicate_codes_invalid")
    duplicates: list[tuple[str, int]] = []
    for item in duplicates_value:
        if not isinstance(item, Mapping) or set(item) != {"stock_code", "occurrences"}:
            _fail("technical_universe_v4_duplicate_codes_invalid")
        code = _text(item["stock_code"], limit=16, code="technical_universe_v4_duplicate_codes_invalid")
        count = item["occurrences"]
        if _STOCK_CODE_RE.fullmatch(code) is None or code not in declared or type(count) is not int or count < 2:
            _fail("technical_universe_v4_duplicate_codes_invalid")
        duplicates.append((code, count))
    if duplicates != sorted(duplicates) or len({code for code, _count in duplicates}) != len(duplicates):
        _fail("technical_universe_v4_duplicate_codes_invalid")
    if raw_count != len(declared) + sum(count - 1 for _code, count in duplicates):
        _fail("technical_universe_v4_raw_stock_code_count_mismatch")
    reasons_value = value["exclusion_reasons"]
    if not isinstance(reasons_value, Mapping) or set(reasons_value) != set(excluded):
        _fail("technical_universe_v4_exclusion_reasons_mismatch")
    reasons = tuple(sorted(
        (
            _text(code, limit=16, code="technical_universe_v4_exclusion_reason_invalid"),
            _text(reason, limit=512, code="technical_universe_v4_exclusion_reason_invalid"),
        )
        for code, reason in reasons_value.items()
    ))
    if any(_STOCK_CODE_RE.fullmatch(code) is None for code, _reason in reasons):
        _fail("technical_universe_v4_exclusion_reason_invalid")
    identity = value["cohort_identity_sha256"]
    if not _is_sha256(identity):
        _fail("technical_universe_v4_cohort_identity_invalid")
    identity_body = {key: item for key, item in value.items() if key != "cohort_identity_sha256"}
    if _sha256_json(identity_body) != identity:
        _fail("technical_universe_v4_cohort_identity_mismatch")
    return {
        "universe_id": universe_id,
        "population_version": population_version,
        "decision_date": parsed_date,
        "raw_stock_code_count": raw_count,
        "declared_stock_codes": declared,
        "duplicate_stock_codes": tuple(duplicates),
        "included_stock_codes": included,
        "excluded_stock_codes": excluded,
        "exclusion_reasons": reasons,
        "cohort_identity_sha256": identity,
    }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseV4Segment:
    """以完整納入/排除清單索引描述單一有界 parent cohort。"""

    segment_index: int
    segment_id: str
    included_start: int
    included_stop: int
    excluded_start: int
    excluded_stop: int
    cohort_identity_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "segment_index": self.segment_index,
            "segment_id": self.segment_id,
            "included_start": self.included_start,
            "included_stop": self.included_stop,
            "excluded_start": self.excluded_start,
            "excluded_stop": self.excluded_stop,
            "cohort_identity_sha256": self.cohort_identity_sha256,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseV4Plan:
    """canonical immutable full-N plan，含完整母體及 v4 source/method pins。"""

    body_json: str

    @classmethod
    def build(
        cls,
        cohort: DailyMarketTechnicalUniverseV4Cohort,
        *,
        source_clock: DailyMarketTechnicalSourceClockV4,
    ) -> DailyMarketTechnicalUniverseV4Plan:
        if not isinstance(cohort, DailyMarketTechnicalUniverseV4Cohort):
            raise TypeError("cohort 必須是 DailyMarketTechnicalUniverseV4Cohort")
        clock = _source_clock_from_typed_or_payload(source_clock)
        if clock.decision_date != cohort.decision_date:
            _fail("technical_universe_v4_source_clock_date_mismatch")
        method = daily_market_technical_method_contract_v4_payload()
        method_sha = daily_market_technical_method_contract_v4_sha256(method)
        segments: list[dict[str, object]] = []
        include_count = len(cohort.included_stock_codes)
        exclude_count = len(cohort.excluded_stock_codes)
        segment_count = max(
            (include_count + DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_SEGMENT_STOCKS - 1)
            // DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_SEGMENT_STOCKS,
            (exclude_count + DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_SEGMENT_STOCKS - 1)
            // DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_SEGMENT_STOCKS,
        )
        if segment_count > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_SEGMENTS:
            _fail("technical_universe_v4_segment_limit")
        for index in range(segment_count):
            include_start = min(include_count, index * DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_SEGMENT_STOCKS)
            include_stop = min(include_count, include_start + DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_SEGMENT_STOCKS)
            exclude_start = min(exclude_count, index * DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_SEGMENT_STOCKS)
            exclude_stop = min(exclude_count, exclude_start + DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_SEGMENT_STOCKS)
            segment_cohort = _segment_cohort(
                cohort,
                index=index,
                included_start=include_start,
                included_stop=include_stop,
                excluded_start=exclude_start,
                excluded_stop=exclude_stop,
            )
            segments.append({
                "segment_index": index,
                "segment_id": f"segment-{index + 1:06d}",
                "included_start": include_start,
                "included_stop": include_stop,
                "excluded_start": exclude_start,
                "excluded_stop": exclude_stop,
                "cohort_identity_sha256": segment_cohort.cohort_identity_sha256,
            })
        body: dict[str, object] = {
            "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_V4_PLAN_SCHEMA,
            "cohort": cohort.to_dict(),
            "source_clock": clock.to_dict(),
            "source_clock_identity_sha256": clock.identity_sha256,
            "method_contracts": method,
            "method_contracts_sha256": method_sha,
            "generation_identity_sha256": _generation_identity(
                cohort.cohort_identity_sha256,
                clock.identity_sha256,
                method_sha,
            ),
            "segments": segments,
        }
        body["plan_identity_sha256"] = _sha256_json(body)
        result = cls(_canonical_json(body))
        result.to_dict()
        if len(result.body_json.encode("utf-8")) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_PLAN_BYTES:
            _fail("technical_universe_v4_plan_byte_limit")
        return result

    @classmethod
    def from_dict(cls, payload: object) -> DailyMarketTechnicalUniverseV4Plan:
        _validate_plan_payload(payload)
        result = cls(_canonical_json(payload))
        if len(result.body_json.encode("utf-8")) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_PLAN_BYTES:
            _fail("technical_universe_v4_plan_byte_limit")
        return result

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalUniverseV4Plan:
        return cls.from_dict(_parse_json(
            raw,
            limit=DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_PLAN_BYTES,
            code="technical_universe_v4_plan_json_invalid",
        ))

    def to_dict(self) -> dict[str, Any]:
        raw = self.body_json.encode("utf-8")
        if len(raw) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_PLAN_BYTES:
            _fail("technical_universe_v4_plan_byte_limit")
        value = _parse_json(raw, limit=DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_PLAN_BYTES, code="technical_universe_v4_plan_json_invalid")
        _validate_plan_payload(value)
        if not isinstance(value, dict):
            _fail("technical_universe_v4_plan_invalid")
        return value

    def to_json(self) -> str:
        self.to_dict()
        return self.body_json

    @property
    def identity_sha256(self) -> str:
        return cast(str, self.to_dict()["plan_identity_sha256"])

    @property
    def generation_identity_sha256(self) -> str:
        return cast(str, self.to_dict()["generation_identity_sha256"])

    @property
    def cohort(self) -> DailyMarketTechnicalUniverseV4Cohort:
        return DailyMarketTechnicalUniverseV4Cohort.from_dict(self.to_dict()["cohort"])

    @property
    def source_clock(self) -> DailyMarketTechnicalSourceClockV4:
        return daily_market_technical_source_clock_v4_from_dict(self.to_dict()["source_clock"])

    @property
    def segments(self) -> tuple[DailyMarketTechnicalUniverseV4Segment, ...]:
        return tuple(
            DailyMarketTechnicalUniverseV4Segment(
                segment_index=item["segment_index"],
                segment_id=item["segment_id"],
                included_start=item["included_start"],
                included_stop=item["included_stop"],
                excluded_start=item["excluded_start"],
                excluded_stop=item["excluded_stop"],
                cohort_identity_sha256=item["cohort_identity_sha256"],
            )
            for item in self.to_dict()["segments"]
        )

    def segment_cohort(self, segment_index: int) -> DailyMarketTechnicalCohortV4:
        if type(segment_index) is not int or not 0 <= segment_index < len(self.segments):
            _fail("technical_universe_v4_segment_index_invalid")
        item = self.to_dict()["segments"][segment_index]
        return _segment_cohort(
            self.cohort,
            index=segment_index,
            included_start=item["included_start"],
            included_stop=item["included_stop"],
            excluded_start=item["excluded_start"],
            excluded_stop=item["excluded_stop"],
        )


def _segment_cohort(
    cohort: DailyMarketTechnicalUniverseV4Cohort,
    *,
    index: int,
    included_start: int,
    included_stop: int,
    excluded_start: int,
    excluded_stop: int,
) -> DailyMarketTechnicalCohortV4:
    included = cohort.included_stock_codes[included_start:included_stop]
    excluded = cohort.excluded_stock_codes[excluded_start:excluded_stop]
    reason_map = dict(cohort.exclusion_reasons)
    reasons = {code: reason_map[code] for code in excluded}
    try:
        return DailyMarketTechnicalCohortV4.create(
            universe_id=cohort.universe_id,
            population_version=cohort.population_version,
            decision_date=cohort.decision_date,
            included_stock_codes=included,
            excluded_stock_codes=excluded,
            exclusion_reasons=reasons,
        )
    except (TypeError, ValueError) as exc:
        raise DailyMarketTechnicalUniverseV4StoreError(
            f"technical_universe_v4_segment_cohort_invalid_{index + 1}"
        ) from exc


def _generation_identity(
    cohort_identity_sha256: str,
    source_clock_identity_sha256: str,
    method_contract_sha256: str,
) -> str:
    for value in (cohort_identity_sha256, source_clock_identity_sha256, method_contract_sha256):
        if not _is_sha256(value):
            _fail("technical_universe_v4_generation_identity_invalid")
    return _sha256_json({
        "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_V4_GENERATION_SCHEMA,
        "cohort_identity_sha256": cohort_identity_sha256,
        "source_clock_identity_sha256": source_clock_identity_sha256,
        "method_contract_sha256": method_contract_sha256,
    })


def _validate_plan_payload(payload: object) -> None:
    if not isinstance(payload, Mapping) or set(payload) != _PLAN_KEYS:
        _fail("technical_universe_v4_plan_fields_invalid")
    body = dict(payload)
    if body["schema_version"] != DAILY_MARKET_TECHNICAL_UNIVERSE_V4_PLAN_SCHEMA:
        _fail("technical_universe_v4_plan_schema_invalid")
    cohort = DailyMarketTechnicalUniverseV4Cohort.from_dict(body["cohort"])
    clock = _source_clock_from_typed_or_payload(body["source_clock"])
    if clock.decision_date != cohort.decision_date:
        _fail("technical_universe_v4_source_clock_date_mismatch")
    clock_sha = body["source_clock_identity_sha256"]
    if not _is_sha256(clock_sha) or clock_sha != clock.identity_sha256:
        _fail("technical_universe_v4_source_clock_identity_mismatch")
    method = body["method_contracts"]
    method_sha = body["method_contracts_sha256"]
    if not isinstance(method, Mapping) or not _is_sha256(method_sha):
        _fail("technical_universe_v4_method_contract_invalid")
    try:
        validate_daily_market_technical_method_contract_v4(method, expected_sha256=method_sha)
    except (TypeError, ValueError) as exc:
        raise DailyMarketTechnicalUniverseV4StoreError(
            "technical_universe_v4_method_contract_invalid"
        ) from exc
    generation = _generation_identity(cohort.cohort_identity_sha256, clock_sha, method_sha)
    if body["generation_identity_sha256"] != generation:
        _fail("technical_universe_v4_generation_identity_mismatch")
    segments = body["segments"]
    if not isinstance(segments, list):
        _fail("technical_universe_v4_segments_invalid")
    include_count = len(cohort.included_stock_codes)
    exclude_count = len(cohort.excluded_stock_codes)
    expected_count = max(
        (include_count + DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_SEGMENT_STOCKS - 1)
        // DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_SEGMENT_STOCKS,
        (exclude_count + DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_SEGMENT_STOCKS - 1)
        // DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_SEGMENT_STOCKS,
    )
    if len(segments) != expected_count or len(segments) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_SEGMENTS:
        _fail("technical_universe_v4_segment_count_mismatch")
    for index, item in enumerate(segments):
        if not isinstance(item, Mapping) or set(item) != {
            "segment_index", "segment_id", "included_start", "included_stop",
            "excluded_start", "excluded_stop", "cohort_identity_sha256",
        }:
            _fail("technical_universe_v4_segment_invalid")
        inc_start = min(include_count, index * DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_SEGMENT_STOCKS)
        inc_stop = min(include_count, inc_start + DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_SEGMENT_STOCKS)
        exc_start = min(exclude_count, index * DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_SEGMENT_STOCKS)
        exc_stop = min(exclude_count, exc_start + DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_SEGMENT_STOCKS)
        if (
            type(item["segment_index"]) is not int
            or item["segment_index"] != index
            or item["segment_id"] != f"segment-{index + 1:06d}"
            or type(item["included_start"]) is not int
            or type(item["included_stop"]) is not int
            or type(item["excluded_start"]) is not int
            or type(item["excluded_stop"]) is not int
            or (item["included_start"], item["included_stop"]) != (inc_start, inc_stop)
            or (item["excluded_start"], item["excluded_stop"]) != (exc_start, exc_stop)
            or not _is_sha256(item["cohort_identity_sha256"])
        ):
            _fail("technical_universe_v4_segment_invalid")
        expected_segment = _segment_cohort(
            cohort,
            index=index,
            included_start=inc_start,
            included_stop=inc_stop,
            excluded_start=exc_start,
            excluded_stop=exc_stop,
        )
        if item["cohort_identity_sha256"] != expected_segment.cohort_identity_sha256:
            _fail("technical_universe_v4_segment_cohort_identity_mismatch")
    plan_id = body["plan_identity_sha256"]
    if not _is_sha256(plan_id):
        _fail("technical_universe_v4_plan_identity_invalid")
    identity_body = {key: item for key, item in body.items() if key != "plan_identity_sha256"}
    if _sha256_json(identity_body) != plan_id:
        _fail("technical_universe_v4_plan_identity_mismatch")


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseV4Counts:
    declared_count: int
    included_count: int
    excluded_count: int
    processed_count: int
    pending_count: int
    missing_data_count: int
    missing_data_pending_count: int

    def to_dict(self) -> dict[str, int]:
        return {
            "declared_count": self.declared_count,
            "included_count": self.included_count,
            "excluded_count": self.excluded_count,
            "processed_count": self.processed_count,
            "pending_count": self.pending_count,
            "missing_data_count": self.missing_data_count,
            "missing_data_pending_count": self.missing_data_pending_count,
        }

    @classmethod
    def from_dict(cls, payload: object) -> DailyMarketTechnicalUniverseV4Counts:
        if not isinstance(payload, Mapping) or set(payload) != _COUNT_KEYS:
            _fail("technical_universe_v4_counts_invalid")
        values: dict[str, int] = {}
        for key in _COUNT_KEYS:
            item = payload[key]
            if type(item) is not int or item < 0:
                _fail("technical_universe_v4_counts_invalid")
            values[key] = item
        if (
            values["declared_count"] != values["included_count"] + values["excluded_count"]
            or values["processed_count"] + values["pending_count"] != values["included_count"]
            or values["missing_data_count"] > values["processed_count"]
            or values["missing_data_pending_count"] != values["pending_count"]
        ):
            _fail("technical_universe_v4_counts_inconsistent")
        return cls(**values)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseV4ParentReceiptReference:
    """一個明示 complete parent 的路徑、plan/receipt identity 與 bytes SHA。"""

    parent_root: str
    parent_plan_identity_sha256: str
    parent_plan_sha256: str
    parent_receipt_identity_sha256: str
    parent_receipt_sha256: str

    @classmethod
    def create(
        cls,
        parent_root: str | Path,
        *,
        parent_plan_identity_sha256: str,
        parent_plan_sha256: str,
        parent_receipt_identity_sha256: str,
        parent_receipt_sha256: str,
    ) -> DailyMarketTechnicalUniverseV4ParentReceiptReference:
        try:
            canonical = _canonical_directory(parent_root, must_exist=True)
        except (DailyMarketTechnicalSnapshotV4RepositoryError, OSError, ValueError) as exc:
            raise DailyMarketTechnicalUniverseV4StoreError(
                "technical_universe_v4_parent_root_invalid"
            ) from exc
        result = cls(
            parent_root=str(canonical),
            parent_plan_identity_sha256=parent_plan_identity_sha256,
            parent_plan_sha256=parent_plan_sha256,
            parent_receipt_identity_sha256=parent_receipt_identity_sha256,
            parent_receipt_sha256=parent_receipt_sha256,
        )
        result.to_dict()
        return result

    @classmethod
    def from_dict(cls, payload: object) -> DailyMarketTechnicalUniverseV4ParentReceiptReference:
        if not isinstance(payload, Mapping) or set(payload) != {
            "schema_version", "parent_root", "parent_plan_identity_sha256",
            "parent_plan_sha256", "parent_receipt_identity_sha256",
            "parent_receipt_sha256",
        }:
            _fail("technical_universe_v4_parent_reference_fields_invalid")
        if payload["schema_version"] != DAILY_MARKET_TECHNICAL_UNIVERSE_V4_PARENT_REFERENCE_SCHEMA:
            _fail("technical_universe_v4_parent_reference_schema_invalid")
        root = _text(payload["parent_root"], limit=32767, code="technical_universe_v4_parent_root_invalid")
        path = Path(root)
        if not path.is_absolute() or ".." in path.parts:
            _fail("technical_universe_v4_parent_root_invalid")
        values = (
            payload["parent_plan_identity_sha256"],
            payload["parent_plan_sha256"],
            payload["parent_receipt_identity_sha256"],
            payload["parent_receipt_sha256"],
        )
        if any(not _is_sha256(value) for value in values):
            _fail("technical_universe_v4_parent_reference_hash_invalid")
        return cls(root, cast(str, values[0]), cast(str, values[1]), cast(str, values[2]), cast(str, values[3]))

    def to_dict(self) -> dict[str, str]:
        payload = {
            "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_V4_PARENT_REFERENCE_SCHEMA,
            "parent_root": self.parent_root,
            "parent_plan_identity_sha256": self.parent_plan_identity_sha256,
            "parent_plan_sha256": self.parent_plan_sha256,
            "parent_receipt_identity_sha256": self.parent_receipt_identity_sha256,
            "parent_receipt_sha256": self.parent_receipt_sha256,
        }
        parsed = DailyMarketTechnicalUniverseV4ParentReceiptReference.from_dict(payload)
        if parsed is not self and parsed != self:
            _fail("technical_universe_v4_parent_reference_invalid")
        return payload


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseV4Receipt:
    """每次進度都是有明確前一收據 pin 的不可變 append-only receipt。"""

    body_json: str

    @classmethod
    def from_dict(cls, payload: object) -> DailyMarketTechnicalUniverseV4Receipt:
        _validate_receipt_payload(payload)
        return cls(_canonical_json(payload))

    @classmethod
    def from_json(cls, raw: bytes | str) -> DailyMarketTechnicalUniverseV4Receipt:
        return cls.from_dict(_parse_json(
            raw,
            limit=DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_RECEIPT_BYTES,
            code="technical_universe_v4_receipt_json_invalid",
        ))

    def to_dict(self) -> dict[str, Any]:
        raw = self.body_json.encode("utf-8")
        value = _parse_json(raw, limit=DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_RECEIPT_BYTES, code="technical_universe_v4_receipt_json_invalid")
        _validate_receipt_payload(value)
        if not isinstance(value, dict):
            _fail("technical_universe_v4_receipt_invalid")
        return value

    def to_json(self) -> str:
        self.to_dict()
        return self.body_json

    @property
    def identity_sha256(self) -> str:
        return cast(str, self.to_dict()["receipt_identity_sha256"])

    @property
    def status(self) -> str:
        return cast(str, self.to_dict()["status"])

    @property
    def content_sha256(self) -> str:
        return _sha256_bytes(self.to_json().encode("utf-8"))


def _validate_receipt_payload(payload: object) -> None:
    if not isinstance(payload, Mapping) or set(payload) != _RECEIPT_KEYS:
        _fail("technical_universe_v4_receipt_fields_invalid")
    body = dict(payload)
    if body["schema_version"] != DAILY_MARKET_TECHNICAL_UNIVERSE_V4_RECEIPT_SCHEMA:
        _fail("technical_universe_v4_receipt_schema_invalid")
    for key in ("generation_identity_sha256", "plan_identity_sha256"):
        if not _is_sha256(body[key]):
            _fail("technical_universe_v4_receipt_identity_invalid")
    if type(body["sequence"]) is not int or body["sequence"] < 1:
        _fail("technical_universe_v4_receipt_sequence_invalid")
    previous_id = body["previous_receipt_identity_sha256"]
    previous_sha = body["previous_receipt_sha256"]
    if body["sequence"] == 1:
        if previous_id is not None or previous_sha is not None:
            _fail("technical_universe_v4_receipt_previous_invalid")
    elif not _is_sha256(previous_id) or not _is_sha256(previous_sha):
        _fail("technical_universe_v4_receipt_previous_invalid")
    if body["status"] not in _STATUS_VALUES:
        _fail("technical_universe_v4_receipt_status_invalid")
    DailyMarketTechnicalUniverseV4Counts.from_dict(body["counts"])
    new_reference = body["segment_reference"]
    if new_reference is not None:
        if not isinstance(new_reference, Mapping) or set(new_reference) != {"segment_index", "parent_reference"}:
            _fail("technical_universe_v4_receipt_segment_reference_invalid")
        if type(new_reference["segment_index"]) is not int or new_reference["segment_index"] < 0:
            _fail("technical_universe_v4_receipt_segment_reference_invalid")
        DailyMarketTechnicalUniverseV4ParentReceiptReference.from_dict(new_reference["parent_reference"])
    last_reference = body["last_parent_reference"]
    if last_reference is not None:
        DailyMarketTechnicalUniverseV4ParentReceiptReference.from_dict(last_reference)
    error_code = body["error_code"]
    if error_code is not None and (
        not isinstance(error_code, str) or not error_code.strip() or len(error_code) > 160
    ):
        _fail("technical_universe_v4_receipt_error_code_invalid")
    identity = body["receipt_identity_sha256"]
    if not _is_sha256(identity):
        _fail("technical_universe_v4_receipt_identity_invalid")
    identity_body = {key: item for key, item in body.items() if key != "receipt_identity_sha256"}
    if _sha256_json(identity_body) != identity:
        _fail("technical_universe_v4_receipt_identity_mismatch")


def _make_receipt(
    *,
    plan: DailyMarketTechnicalUniverseV4Plan,
    sequence: int,
    previous: DailyMarketTechnicalUniverseV4Receipt | None,
    status: Literal["partial", "cancelled", "failed", "complete"],
    counts: DailyMarketTechnicalUniverseV4Counts,
    segment_index: int | None = None,
    parent_reference: DailyMarketTechnicalUniverseV4ParentReceiptReference | None = None,
    last_parent_reference: DailyMarketTechnicalUniverseV4ParentReceiptReference | None = None,
    error_code: str | None = None,
) -> DailyMarketTechnicalUniverseV4Receipt:
    payload: dict[str, object] = {
        "schema_version": DAILY_MARKET_TECHNICAL_UNIVERSE_V4_RECEIPT_SCHEMA,
        "generation_identity_sha256": plan.generation_identity_sha256,
        "plan_identity_sha256": plan.identity_sha256,
        "sequence": sequence,
        "previous_receipt_identity_sha256": previous.identity_sha256 if previous else None,
        "previous_receipt_sha256": previous.content_sha256 if previous else None,
        "status": status,
        "counts": counts.to_dict(),
        "segment_reference": (
            {"segment_index": segment_index, "parent_reference": parent_reference.to_dict()}
            if segment_index is not None and parent_reference is not None
            else None
        ),
        "last_parent_reference": last_parent_reference.to_dict() if last_parent_reference else None,
        "error_code": error_code,
    }
    payload["receipt_identity_sha256"] = _sha256_json(payload)
    return DailyMarketTechnicalUniverseV4Receipt.from_dict(payload)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalUniverseV4VerifiedState:
    plan: DailyMarketTechnicalUniverseV4Plan
    receipt: DailyMarketTechnicalUniverseV4Receipt
    segment_parent_references: tuple[tuple[int, DailyMarketTechnicalUniverseV4ParentReceiptReference], ...]
    counts: DailyMarketTechnicalUniverseV4Counts
    missing_data_stock_codes: tuple[str, ...]
    calculation_identity_sha256: str | None = None


def _validate_store_root(
    output_root: Path,
    store_root: Path,
    research_scope: ResearchCaptureWriteScope | None,
    *,
    writing: bool,
) -> None:
    try:
        _safe_path(output_root)
        if _canonical_realpath(output_root) != output_root:
            _fail("technical_universe_v4_root_changed")
        _safe_path(store_root)
        if research_scope is not None:
            if writing:
                research_scope.validate()
            scope_root = _canonical_realpath(Path(research_scope.root))
            if output_root == scope_root or not output_root.is_relative_to(scope_root):
                _fail("technical_universe_v4_scope_escape")
    except DailyMarketTechnicalUniverseV4StoreError:
        raise
    except (RuleSampleCaptureError, OSError, RuntimeError, ValueError) as exc:
        raise DailyMarketTechnicalUniverseV4StoreError(
            "technical_universe_v4_root_invalid"
        ) from exc


def _directory_exists(path: Path) -> bool:
    return _lstat_optional(path) is not None


def _store_inventory(root: Path) -> tuple[int, int]:
    if not _directory_exists(root):
        return 0, 0
    _safe_path(root)
    total = entries_seen = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        info = _lstat_optional(directory)
        if info is None or not stat.S_ISDIR(info.st_mode) or _is_link_or_reparse(info):
            _fail("technical_universe_v4_store_directory_invalid")
        try:
            with os.scandir(to_internal_io_path(directory)) as scan:
                entries = list(scan)
        except OSError as exc:
            raise DailyMarketTechnicalUniverseV4StoreError(
                "technical_universe_v4_store_scan_failed"
            ) from exc
        for entry in entries:
            entries_seen += 1
            if entries_seen > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_STORE_ENTRIES:
                _fail("technical_universe_v4_store_entry_limit")
            path = directory / entry.name
            item = _lstat_optional(path)
            if item is None or _is_link_or_reparse(item):
                _fail("technical_universe_v4_store_link_or_race")
            if stat.S_ISDIR(item.st_mode):
                pending.append(path)
            elif stat.S_ISREG(item.st_mode) and item.st_nlink == 1:
                if entry.name != ".writer.lock":
                    total += item.st_size
                    if total > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_RETAINED_BYTES:
                        _fail("technical_universe_v4_retention_byte_limit")
            else:
                _fail("technical_universe_v4_store_file_type_invalid")
    return total, entries_seen


def _directory_names(path: Path, *, maximum: int) -> tuple[str, ...]:
    info = _lstat_optional(path)
    if info is None or not stat.S_ISDIR(info.st_mode) or _is_link_or_reparse(info):
        _fail("technical_universe_v4_store_directory_invalid")
    _safe_path(path)
    try:
        with os.scandir(to_internal_io_path(path)) as scan:
            names = tuple(entry.name for entry in scan)
    except OSError as exc:
        raise DailyMarketTechnicalUniverseV4StoreError(
            "technical_universe_v4_store_scan_failed"
        ) from exc
    if len(names) > maximum:
        _fail("technical_universe_v4_store_entry_limit")
    return names


def _validate_exact_store_layout(
    store_root: Path,
    generation_dir: Path,
    selected_prefix: Sequence[tuple[DailyMarketTechnicalUniverseV4Receipt, str]],
    *,
    generation_identity_sha256: str,
    plan_identity_sha256: str,
) -> list[tuple[DailyMarketTechnicalUniverseV4Receipt, str]]:
    root_names = set(_directory_names(store_root, maximum=DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_STORE_ENTRIES))
    if "generations" not in root_names or root_names - {"generations", ".writer.lock"}:
        _fail("technical_universe_v4_store_layout_invalid")
    lock_path = store_root / ".writer.lock"
    lock_info = _lstat_optional(lock_path)
    if lock_info is not None and (
        not stat.S_ISREG(lock_info.st_mode)
        or _is_link_or_reparse(lock_info)
        or lock_info.st_nlink != 1
    ):
        _fail("technical_universe_v4_store_lock_invalid")
    generations_root = store_root / "generations"
    names = _directory_names(
        generations_root,
        maximum=DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_STORE_ENTRIES,
    )
    for name in names:
        if not _is_sha256(name):
            _fail("technical_universe_v4_generation_directory_invalid")
        child = generations_root / name
        child_info = _lstat_optional(child)
        if child_info is None or not stat.S_ISDIR(child_info.st_mode) or _is_link_or_reparse(child_info):
            _fail("technical_universe_v4_generation_directory_invalid")
    generation_names = set(_directory_names(generation_dir, maximum=4))
    if generation_names != {"plan.json", "receipts"}:
        _fail("technical_universe_v4_generation_layout_invalid")
    receipts_dir = generation_dir / "receipts"
    receipt_names = set(
        _directory_names(
            receipts_dir,
            maximum=DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_STORE_ENTRIES,
        )
    )
    if not receipt_names:
        _fail("technical_universe_v4_receipt_history_fork_or_orphan")

    by_sequence: dict[
        int, tuple[DailyMarketTechnicalUniverseV4Receipt, str]
    ] = {}
    identities: set[str] = set()
    for name in receipt_names:
        if not name.endswith(".json") or not _is_sha256(name[:-5]):
            _fail("technical_universe_v4_receipt_history_fork_or_orphan")
        receipt_path = receipts_dir / name
        info = _lstat_optional(receipt_path)
        if (
            info is None
            or not stat.S_ISREG(info.st_mode)
            or _is_link_or_reparse(info)
            or info.st_nlink != 1
        ):
            _fail("technical_universe_v4_receipt_file_invalid")
        raw = _read_canonical_file(
            receipt_path,
            DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_RECEIPT_BYTES,
            "technical_universe_v4_receipt_read_failed",
        )
        item = DailyMarketTechnicalUniverseV4Receipt.from_json(raw)
        if item.to_json().encode("utf-8") != raw:
            _fail("technical_universe_v4_receipt_bytes_not_canonical")
        identity = item.identity_sha256
        if identity != name[:-5] or identity in identities:
            _fail("technical_universe_v4_receipt_path_identity_mismatch")
        identities.add(identity)
        body = item.to_dict()
        if (
            body["generation_identity_sha256"] != generation_identity_sha256
            or body["plan_identity_sha256"] != plan_identity_sha256
        ):
            _fail("technical_universe_v4_receipt_plan_link_mismatch")
        sequence = int(body["sequence"])
        if sequence in by_sequence:
            _fail("technical_universe_v4_receipt_history_fork_or_orphan")
        by_sequence[sequence] = (item, _sha256_bytes(raw))

    ordered_sequences = sorted(by_sequence)
    if ordered_sequences != list(range(1, len(ordered_sequences) + 1)):
        _fail("technical_universe_v4_receipt_history_fork_or_orphan")
    ordered = [by_sequence[sequence] for sequence in ordered_sequences]
    if len(selected_prefix) > len(ordered):
        _fail("technical_universe_v4_receipt_history_fork_or_orphan")
    for selected, found in zip(selected_prefix, ordered):
        if selected[0].identity_sha256 != found[0].identity_sha256 or selected[1] != found[1]:
            _fail("technical_universe_v4_receipt_history_fork_or_orphan")

    children_by_previous: dict[str, int] = {}
    for index, (item, item_sha) in enumerate(ordered):
        body = item.to_dict()
        if index == 0:
            if (
                body["sequence"] != 1
                or body["previous_receipt_identity_sha256"] is not None
                or body["previous_receipt_sha256"] is not None
            ):
                _fail("technical_universe_v4_initial_receipt_invalid")
            continue
        previous, previous_sha = ordered[index - 1]
        if body["sequence"] != index + 1 or body["previous_receipt_identity_sha256"] != previous.identity_sha256:
            _fail("technical_universe_v4_receipt_chain_invalid")
        if body["previous_receipt_sha256"] != previous_sha:
            _fail("technical_universe_v4_previous_receipt_sha_mismatch")
        previous_id = previous.identity_sha256
        children_by_previous[previous_id] = children_by_previous.get(previous_id, 0) + 1
        if children_by_previous[previous_id] > 1:
            _fail("technical_universe_v4_receipt_history_fork_or_orphan")
        _validate_transition(previous.to_dict(), body)

    root_count = sum(
        1
        for item, _sha in ordered
        if item.to_dict()["previous_receipt_identity_sha256"] is None
    )
    parent_identities = {
        cast(str, item.to_dict()["previous_receipt_identity_sha256"])
        for item, _sha in ordered
        if item.to_dict()["previous_receipt_identity_sha256"] is not None
    }
    head_count = sum(1 for item, _sha in ordered if item.identity_sha256 not in parent_identities)
    if root_count != 1 or head_count != 1:
        _fail("technical_universe_v4_receipt_history_fork_or_orphan")
    if set(_directory_names(receipts_dir, maximum=DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_STORE_ENTRIES)) != receipt_names:
        _fail("technical_universe_v4_receipt_history_changed_during_read")
    return ordered


def _write_immutable(path: Path, raw: bytes, *, maximum: int) -> None:
    if len(raw) > maximum:
        _fail("technical_universe_v4_file_byte_limit")
    _ensure_directory(path.parent)
    _safe_path(path)
    if _lstat_optional(path) is not None:
        _fail("technical_universe_v4_immutable_file_conflict")
    staging = path.with_name(f".partial-{uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(to_internal_io_path(staging), flags, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            view = memoryview(raw)
            written = 0
            while written < len(view):
                written += handle.write(view[written:])
            handle.flush()
            os.fsync(handle.fileno())
        staging_info = _lstat_optional(staging)
        if (
            staging_info is None
            or not stat.S_ISREG(staging_info.st_mode)
            or staging_info.st_nlink != 1
            or staging_info.st_size != len(raw)
        ):
            _fail("technical_universe_v4_staging_file_invalid")
        if _lstat_optional(path) is not None:
            _fail("technical_universe_v4_immutable_file_conflict")
        _publish_temp_no_replace(staging, path)
        published = _lstat_optional(path)
        if published is None or not stat.S_ISREG(published.st_mode) or published.st_nlink != 1:
            _fail("technical_universe_v4_published_file_invalid")
        if _read_bounded_file(path, maximum) != raw:
            _fail("technical_universe_v4_staging_readback_mismatch")
    except DailyMarketTechnicalUniverseV4StoreError:
        raise
    except OSError as exc:
        raise DailyMarketTechnicalUniverseV4StoreError(
            "technical_universe_v4_atomic_write_failed"
        ) from exc


def _read_canonical_file(path: Path, maximum: int, code: str) -> bytes:
    try:
        return _read_bounded_file(path, maximum)
    except DailyMarketTechnicalSnapshotV4RepositoryError as exc:
        raise DailyMarketTechnicalUniverseV4StoreError(code, str(exc)) from exc


def _counts_for(
    plan: DailyMarketTechnicalUniverseV4Plan,
    references: Sequence[tuple[int, DailyMarketTechnicalUniverseV4ParentReceiptReference]],
    missing_data_stock_codes: Sequence[str],
) -> DailyMarketTechnicalUniverseV4Counts:
    cohort = plan.cohort
    processed = sum(len(plan.segment_cohort(index).included_stock_codes) for index, _ref in references)
    pending = len(cohort.included_stock_codes) - processed
    return DailyMarketTechnicalUniverseV4Counts(
        declared_count=len(cohort.declared_stock_codes),
        included_count=len(cohort.included_stock_codes),
        excluded_count=len(cohort.excluded_stock_codes),
        processed_count=processed,
        pending_count=pending,
        missing_data_count=len(missing_data_stock_codes),
        missing_data_pending_count=pending,
    )


def _verify_parent_reference(
    plan: DailyMarketTechnicalUniverseV4Plan,
    segment_index: int,
    reference: DailyMarketTechnicalUniverseV4ParentReceiptReference,
    *,
    store_output_root: Path,
    include_verified_read: bool = False,
    cancel_callback: Callable[[], bool] | None = None,
) -> tuple[
    tuple[str, ...],
    int,
    str | None,
    DailyMarketTechnicalParentCaptureV4VerifiedRead | None,
]:
    segment_cohort = plan.segment_cohort(segment_index)
    parent_root = Path(reference.parent_root)
    if parent_root == store_output_root or parent_root.is_relative_to(store_output_root) or store_output_root.is_relative_to(parent_root):
        _fail("technical_universe_v4_parent_store_overlap")
    verified_parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead | None = None
    try:
        if include_verified_read or cancel_callback is not None:
            parent_reader = BoundedDailyMarketTechnicalParentCaptureWriterV4(
                parent_root,
                read_only=True,
            )
            verified_parent_read = parent_reader.read_verified(
                reference.parent_plan_identity_sha256,
                reference.parent_receipt_identity_sha256,
                expected_receipt_sha256=reference.parent_receipt_sha256,
                expected_plan_sha256=reference.parent_plan_sha256,
                cancel_callback=cancel_callback,
            )
            package = verified_parent_read.package
        else:
            package = read_daily_market_technical_parent_capture_v4(
                parent_root,
                reference.parent_plan_identity_sha256,
                reference.parent_receipt_identity_sha256,
                expected_receipt_sha256=reference.parent_receipt_sha256,
                expected_plan_sha256=reference.parent_plan_sha256,
            )
    except (TechnicalParentCaptureV4Error, OSError, ValueError) as exc:
        code = getattr(exc, "code", "technical_universe_v4_parent_reference_invalid")
        raise DailyMarketTechnicalUniverseV4StoreError(
            f"technical_universe_v4_{code}", str(exc)
        ) from exc
    parent_plan = package["plan"]
    parent_receipt = package["receipt"]
    if package["plan_sha256"] != reference.parent_plan_sha256 or package["receipt_sha256"] != reference.parent_receipt_sha256:
        _fail("technical_universe_v4_parent_bytes_sha_mismatch")
    if parent_receipt.get("status") != "complete":
        _fail("technical_universe_v4_parent_not_complete")
    if parent_plan.get("cohort") != segment_cohort.to_dict():
        _fail("technical_universe_v4_parent_segment_cohort_mismatch")
    expected_clock = plan.to_dict()["source_clock"]
    expected_clock_sha = plan.to_dict()["source_clock_identity_sha256"]
    if (
        parent_plan.get("source_clock") != expected_clock
        or parent_plan.get("source_clock_identity_sha256") != expected_clock_sha
        or parent_receipt.get("source_clock_identity_sha256") != expected_clock_sha
    ):
        _fail("technical_universe_v4_parent_source_clock_mismatch")
    expected_method = plan.to_dict()["method_contracts"]
    expected_method_sha = plan.to_dict()["method_contracts_sha256"]
    if (
        parent_plan.get("method_contracts") != expected_method
        or parent_plan.get("method_contracts_sha256") != expected_method_sha
    ):
        _fail("technical_universe_v4_parent_method_contract_mismatch")
    evidence = parent_plan.get("source_stock_evidence")
    if not isinstance(evidence, list) or len(evidence) != len(segment_cohort.included_stock_codes):
        _fail("technical_universe_v4_parent_source_evidence_invalid")
    missing: list[str] = []
    calculation_identities: set[str] = set()
    for stock_code, item in zip(segment_cohort.included_stock_codes, evidence):
        if not isinstance(item, Mapping) or item.get("stock_code") != stock_code:
            _fail("technical_universe_v4_parent_source_evidence_invalid")
        calculation_identity = item.get("calculation_identity_sha256")
        if not _is_sha256(calculation_identity):
            _fail("technical_universe_v4_parent_source_evidence_invalid")
        calculation_identities.add(cast(str, calculation_identity))
        row_count = item.get("row_count")
        if type(row_count) is not int or not 0 <= row_count <= 120:
            _fail("technical_universe_v4_parent_source_evidence_invalid")
        if row_count == 0:
            missing.append(stock_code)
    if len(calculation_identities) > 1:
        _fail("technical_universe_v4_parent_calculation_identity_mixed")
    calculation_identity_sha256 = next(iter(calculation_identities), None)
    return (
        tuple(missing),
        len(segment_cohort.included_stock_codes),
        calculation_identity_sha256,
        verified_parent_read if include_verified_read else None,
    )


class DailyMarketTechnicalUniverseV4StoreWriter:
    """在隔離 root append 完整母體進度與已核驗 parent reference。"""

    def __init__(
        self,
        output_root: str | Path,
        *,
        research_scope: ResearchCaptureWriteScope | None = None,
    ) -> None:
        try:
            base = BoundedRuleResearchCaptureWriter(
                output_root,
                research_scope=research_scope,
            )
        except (RuleSampleCaptureError, OSError, ValueError) as exc:
            code = getattr(exc, "code", "technical_universe_v4_output_root_invalid")
            raise DailyMarketTechnicalUniverseV4StoreError(code, str(exc)) from exc
        self.output_root = base.output_root
        self.store_root = self.output_root / DAILY_MARKET_TECHNICAL_UNIVERSE_V4_STORE_DIRECTORY
        self._research_scope = research_scope

    def _validate_path(self, *, writing: bool) -> None:
        _validate_store_root(self.output_root, self.store_root, self._research_scope, writing=writing)

    def start(self, plan: DailyMarketTechnicalUniverseV4Plan) -> DailyMarketTechnicalUniverseV4Receipt:
        if not isinstance(plan, DailyMarketTechnicalUniverseV4Plan):
            raise TypeError("plan 必須是 DailyMarketTechnicalUniverseV4Plan")
        plan.to_dict()
        raw_plan = plan.to_json().encode("utf-8")
        initial_counts = _counts_for(plan, (), ())
        initial = _make_receipt(
            plan=plan,
            sequence=1,
            previous=None,
            status="partial",
            counts=initial_counts,
        )
        self._validate_path(writing=True)
        _ensure_directory(self.store_root)
        self._validate_path(writing=True)
        with _FileLockV4(self.store_root / ".writer.lock"):
            self._validate_path(writing=True)
            generation_dir = self._generation_dir(plan.generation_identity_sha256)
            if _lstat_optional(generation_dir) is not None:
                _fail("technical_universe_v4_generation_already_exists_use_explicit_resume")
            new_bytes = len(raw_plan) + len(initial.to_json().encode("utf-8"))
            current_bytes, _entry_count = _store_inventory(self.store_root)
            if current_bytes + new_bytes > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_RETAINED_BYTES:
                _fail("technical_universe_v4_retention_byte_limit")
            self._validate_path(writing=True)
            _write_immutable(generation_dir / "plan.json", raw_plan, maximum=DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_PLAN_BYTES)
            self._validate_path(writing=True)
            _write_immutable(self._receipt_path(plan.generation_identity_sha256, initial.identity_sha256), initial.to_json().encode("utf-8"), maximum=DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_RECEIPT_BYTES)
            _store_inventory(self.store_root)
        return initial

    def read_exact(
        self,
        generation_identity_sha256: str,
        plan_identity_sha256: str,
        receipt_identity_sha256: str,
        *,
        expected_receipt_sha256: str,
        expected_plan_sha256: str | None = None,
    ) -> DailyMarketTechnicalUniverseV4VerifiedState:
        return DailyMarketTechnicalUniverseV4StoreReader(self.output_root).read_exact(
            generation_identity_sha256,
            plan_identity_sha256,
            receipt_identity_sha256,
            expected_receipt_sha256=expected_receipt_sha256,
            expected_plan_sha256=expected_plan_sha256,
        )

    def _read_exact_append_base(
        self,
        generation_identity_sha256: str,
        plan_identity_sha256: str,
        previous_receipt_identity_sha256: str,
        *,
        expected_previous_receipt_sha256: str,
    ) -> DailyMarketTechnicalUniverseV4VerifiedState:
        state, history_head_identity = DailyMarketTechnicalUniverseV4StoreReader(
            self.output_root
        )._read_exact_with_head(
            generation_identity_sha256,
            plan_identity_sha256,
            previous_receipt_identity_sha256,
            expected_receipt_sha256=expected_previous_receipt_sha256,
        )
        if previous_receipt_identity_sha256 != history_head_identity:
            _fail("technical_universe_v4_append_previous_receipt_not_history_head")
        return state

    def record_segment_parent(
        self,
        generation_identity_sha256: str,
        plan_identity_sha256: str,
        previous_receipt_identity_sha256: str,
        *,
        expected_previous_receipt_sha256: str,
        segment_index: int,
        parent_reference: DailyMarketTechnicalUniverseV4ParentReceiptReference,
    ) -> DailyMarketTechnicalUniverseV4Receipt:
        if not isinstance(parent_reference, DailyMarketTechnicalUniverseV4ParentReceiptReference):
            raise TypeError("parent_reference 必須是 DailyMarketTechnicalUniverseV4ParentReceiptReference")
        with self._writer_lock():
            state = self._read_exact_append_base(
                generation_identity_sha256,
                plan_identity_sha256,
                previous_receipt_identity_sha256,
                expected_previous_receipt_sha256=expected_previous_receipt_sha256,
            )
            if state.receipt.status != "partial":
                _fail("technical_universe_v4_receipt_not_partial")
            plan = state.plan
            if type(segment_index) is not int or segment_index != len(state.segment_parent_references):
                existing = dict(state.segment_parent_references).get(segment_index)
                if existing == parent_reference:
                    return state.receipt
                _fail("technical_universe_v4_segment_order_or_duplicate_invalid")
            if not 0 <= segment_index < len(plan.segments):
                _fail("technical_universe_v4_segment_index_invalid")
            missing, _included_count, parent_calculation_identity, _verified_parent_read = _verify_parent_reference(
                plan,
                segment_index,
                parent_reference,
                store_output_root=self.output_root,
            )
            if (
                parent_calculation_identity is not None
                and state.calculation_identity_sha256 is not None
                and parent_calculation_identity != state.calculation_identity_sha256
            ):
                _fail("technical_universe_v4_parent_calculation_identity_mismatch")
            all_refs = (*state.segment_parent_references, (segment_index, parent_reference))
            all_missing = (*state.missing_data_stock_codes, *missing)
            counts = _counts_for(plan, all_refs, all_missing)
            receipt = _make_receipt(
                plan=plan,
                sequence=state.receipt.to_dict()["sequence"] + 1,
                previous=state.receipt,
                status="partial",
                counts=counts,
                segment_index=segment_index,
                parent_reference=parent_reference,
                last_parent_reference=parent_reference,
            )
            return self._append(plan, receipt)

    def mark_terminal(
        self,
        generation_identity_sha256: str,
        plan_identity_sha256: str,
        previous_receipt_identity_sha256: str,
        *,
        expected_previous_receipt_sha256: str,
        status: Literal["cancelled", "failed"],
        error_code: str,
    ) -> DailyMarketTechnicalUniverseV4Receipt:
        if status not in {"cancelled", "failed"}:
            _fail("technical_universe_v4_terminal_status_invalid")
        normalized_error = _text(error_code, limit=160, code="technical_universe_v4_error_code_invalid")
        with self._writer_lock():
            state = self._read_exact_append_base(
                generation_identity_sha256,
                plan_identity_sha256,
                previous_receipt_identity_sha256,
                expected_previous_receipt_sha256=expected_previous_receipt_sha256,
            )
            if state.receipt.status != "partial":
                _fail("technical_universe_v4_receipt_not_partial")
            last = state.segment_parent_references[-1][1] if state.segment_parent_references else None
            receipt = _make_receipt(
                plan=state.plan,
                sequence=state.receipt.to_dict()["sequence"] + 1,
                previous=state.receipt,
                status=status,
                counts=state.counts,
                last_parent_reference=last,
                error_code=normalized_error,
            )
            return self._append(state.plan, receipt)

    def resume(
        self,
        generation_identity_sha256: str,
        plan_identity_sha256: str,
        previous_receipt_identity_sha256: str,
        *,
        expected_previous_receipt_sha256: str,
    ) -> DailyMarketTechnicalUniverseV4Receipt:
        with self._writer_lock():
            state = self._read_exact_append_base(
                generation_identity_sha256,
                plan_identity_sha256,
                previous_receipt_identity_sha256,
                expected_previous_receipt_sha256=expected_previous_receipt_sha256,
            )
            if state.receipt.status not in {"cancelled", "failed"}:
                _fail("technical_universe_v4_receipt_not_resumable")
            last = state.segment_parent_references[-1][1] if state.segment_parent_references else None
            receipt = _make_receipt(
                plan=state.plan,
                sequence=state.receipt.to_dict()["sequence"] + 1,
                previous=state.receipt,
                status="partial",
                counts=state.counts,
                last_parent_reference=last,
            )
            return self._append(state.plan, receipt)

    def complete(
        self,
        generation_identity_sha256: str,
        plan_identity_sha256: str,
        previous_receipt_identity_sha256: str,
        *,
        expected_previous_receipt_sha256: str,
    ) -> DailyMarketTechnicalUniverseV4Receipt:
        with self._writer_lock():
            state = self._read_exact_append_base(
                generation_identity_sha256,
                plan_identity_sha256,
                previous_receipt_identity_sha256,
                expected_previous_receipt_sha256=expected_previous_receipt_sha256,
            )
            if state.receipt.status != "partial":
                _fail("technical_universe_v4_receipt_not_partial")
            if len(state.segment_parent_references) != len(state.plan.segments):
                _fail("technical_universe_v4_parent_segments_incomplete")
            if state.counts.processed_count != state.counts.included_count or state.counts.pending_count != 0:
                _fail("technical_universe_v4_included_members_pending")
            last = state.segment_parent_references[-1][1] if state.segment_parent_references else None
            receipt = _make_receipt(
                plan=state.plan,
                sequence=state.receipt.to_dict()["sequence"] + 1,
                previous=state.receipt,
                status="complete",
                counts=state.counts,
                last_parent_reference=last,
            )
            return self._append(state.plan, receipt)

    def _writer_lock(self) -> Any:
        self._validate_path(writing=True)
        info = _lstat_optional(self.store_root)
        if info is None or not stat.S_ISDIR(info.st_mode) or _is_link_or_reparse(info):
            _fail("technical_universe_v4_store_root_missing")
        self._validate_path(writing=True)
        return _WriterLockContext(self, self.store_root / ".writer.lock")

    def _generation_dir(self, generation_id: str) -> Path:
        if not _is_sha256(generation_id):
            _fail("technical_universe_v4_generation_pin_invalid")
        return self.store_root / "generations" / generation_id

    def _receipt_path(self, generation_id: str, receipt_id: str) -> Path:
        if not _is_sha256(receipt_id):
            _fail("technical_universe_v4_receipt_pin_invalid")
        return self._generation_dir(generation_id) / "receipts" / f"{receipt_id}.json"

    def _append(
        self,
        plan: DailyMarketTechnicalUniverseV4Plan,
        receipt: DailyMarketTechnicalUniverseV4Receipt,
    ) -> DailyMarketTechnicalUniverseV4Receipt:
        self._validate_path(writing=True)
        raw = receipt.to_json().encode("utf-8")
        current, _entries = _store_inventory(self.store_root)
        if current + len(raw) > DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_RETAINED_BYTES:
            _fail("technical_universe_v4_retention_byte_limit")
        self._validate_path(writing=True)
        _write_immutable(
            self._receipt_path(plan.generation_identity_sha256, receipt.identity_sha256),
            raw,
            maximum=DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_RECEIPT_BYTES,
        )
        _store_inventory(self.store_root)
        return receipt


class _WriterLockContext:
    def __init__(self, writer: DailyMarketTechnicalUniverseV4StoreWriter, path: Path) -> None:
        self.writer = writer
        self.path = path
        self.lock: _FileLockV4 | None = None

    def __enter__(self) -> _WriterLockContext:
        self.writer._validate_path(writing=True)
        self.lock = _FileLockV4(self.path)
        self.lock.__enter__()
        self.writer._validate_path(writing=True)
        return self

    def __exit__(self, *args: object) -> None:
        if self.lock is not None:
            self.lock.__exit__(*args)
            self.lock = None


class DailyMarketTechnicalUniverseV4StoreReader:
    """只讀 exact full-N reader；不建立目錄、不開來源 DB、不查 latest。"""

    def __init__(self, output_root: str | Path) -> None:
        try:
            base = BoundedRuleResearchCaptureWriter(output_root, read_only=True)
        except (RuleSampleCaptureError, OSError, ValueError) as exc:
            code = getattr(exc, "code", "technical_universe_v4_readonly_root_invalid")
            raise DailyMarketTechnicalUniverseV4StoreError(code, str(exc)) from exc
        self.output_root = base.output_root
        self.store_root = self.output_root / DAILY_MARKET_TECHNICAL_UNIVERSE_V4_STORE_DIRECTORY

    def read_exact(
        self,
        generation_identity_sha256: str,
        plan_identity_sha256: str,
        receipt_identity_sha256: str,
        *,
        expected_receipt_sha256: str,
        expected_plan_sha256: str | None = None,
    ) -> DailyMarketTechnicalUniverseV4VerifiedState:
        state, _history_head_identity = self._read_exact_with_head(
            generation_identity_sha256,
            plan_identity_sha256,
            receipt_identity_sha256,
            expected_receipt_sha256=expected_receipt_sha256,
            expected_plan_sha256=expected_plan_sha256,
        )
        return state

    def read_exact_with_verified_parent_callback(
        self,
        generation_identity_sha256: str,
        plan_identity_sha256: str,
        receipt_identity_sha256: str,
        *,
        expected_receipt_sha256: str,
        expected_plan_sha256: str | None = None,
        parent_verified_callback: Callable[
            [int, DailyMarketTechnicalParentCaptureV4VerifiedRead], None
        ] | None = None,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> DailyMarketTechnicalUniverseV4VerifiedState:
        """精確讀回 store，逐段交付同次 parent 核驗結果供同步消費。"""

        if parent_verified_callback is not None and not callable(parent_verified_callback):
            _fail("technical_universe_v4_parent_verified_callback_invalid")
        state, _history_head_identity = self._read_exact_with_head(
            generation_identity_sha256,
            plan_identity_sha256,
            receipt_identity_sha256,
            expected_receipt_sha256=expected_receipt_sha256,
            expected_plan_sha256=expected_plan_sha256,
            parent_verified_callback=parent_verified_callback,
            cancel_callback=cancel_callback,
        )
        return state

    def _read_exact_with_head(
        self,
        generation_identity_sha256: str,
        plan_identity_sha256: str,
        receipt_identity_sha256: str,
        *,
        expected_receipt_sha256: str,
        expected_plan_sha256: str | None = None,
        parent_verified_callback: Callable[
            [int, DailyMarketTechnicalParentCaptureV4VerifiedRead], None
        ] | None = None,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> tuple[DailyMarketTechnicalUniverseV4VerifiedState, str]:
        """核完整 receipt graph，同時只回傳所選 prefix 與 graph head pin。"""

        _check_universe_read_cancelled(cancel_callback)
        _validate_store_root(self.output_root, self.store_root, None, writing=False)
        if not _is_sha256(generation_identity_sha256) or not _is_sha256(plan_identity_sha256) or not _is_sha256(receipt_identity_sha256):
            _fail("technical_universe_v4_read_pin_invalid")
        try:
            store = _canonical_directory(self.store_root, must_exist=True)
        except (DailyMarketTechnicalSnapshotV4RepositoryError, OSError, ValueError) as exc:
            raise DailyMarketTechnicalUniverseV4StoreError(
                "technical_universe_v4_store_root_missing"
            ) from exc
        if store != self.store_root:
            _fail("technical_universe_v4_store_root_not_canonical")
        _store_inventory(store)
        generation_dir = store / "generations" / generation_identity_sha256
        plan_path = generation_dir / "plan.json"
        plan_raw = _read_canonical_file(
            plan_path,
            DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_PLAN_BYTES,
            "technical_universe_v4_plan_read_failed",
        )
        if expected_plan_sha256 is not None:
            if not _is_sha256(expected_plan_sha256) or _sha256_bytes(plan_raw) != expected_plan_sha256:
                _fail("technical_universe_v4_plan_sha_mismatch")
        plan = DailyMarketTechnicalUniverseV4Plan.from_json(plan_raw)
        if plan.identity_sha256 != plan_identity_sha256 or plan.generation_identity_sha256 != generation_identity_sha256:
            _fail("technical_universe_v4_plan_path_identity_mismatch")
        current_receipt_path = store / "generations" / generation_identity_sha256 / "receipts" / f"{receipt_identity_sha256}.json"
        current_raw = _read_canonical_file(
            current_receipt_path,
            DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_RECEIPT_BYTES,
            "technical_universe_v4_receipt_read_failed",
        )
        if not _is_sha256(expected_receipt_sha256) or _sha256_bytes(current_raw) != expected_receipt_sha256:
            _fail("technical_universe_v4_receipt_sha_mismatch")
        current = DailyMarketTechnicalUniverseV4Receipt.from_json(current_raw)
        if current.identity_sha256 != receipt_identity_sha256:
            _fail("technical_universe_v4_receipt_path_identity_mismatch")

        chain_reverse: list[tuple[DailyMarketTechnicalUniverseV4Receipt, str]] = []
        seen: set[str] = set()
        receipt = current
        raw = current_raw
        while True:
            receipt_id = receipt.identity_sha256
            if receipt_id in seen or len(chain_reverse) >= DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_STORE_ENTRIES:
                _fail("technical_universe_v4_receipt_chain_cycle_or_limit")
            seen.add(receipt_id)
            body = receipt.to_dict()
            if body["generation_identity_sha256"] != generation_identity_sha256 or body["plan_identity_sha256"] != plan_identity_sha256:
                _fail("technical_universe_v4_receipt_plan_link_mismatch")
            chain_reverse.append((receipt, _sha256_bytes(raw)))
            if body["sequence"] == 1:
                if body["previous_receipt_identity_sha256"] is not None or body["previous_receipt_sha256"] is not None:
                    _fail("technical_universe_v4_initial_receipt_invalid")
                break
            previous_id = cast(str, body["previous_receipt_identity_sha256"])
            previous_chain_sha = cast(str, body["previous_receipt_sha256"])
            previous_path = store / "generations" / generation_identity_sha256 / "receipts" / f"{previous_id}.json"
            raw = _read_canonical_file(
                previous_path,
                DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_RECEIPT_BYTES,
                "technical_universe_v4_previous_receipt_read_failed",
            )
            if _sha256_bytes(raw) != previous_chain_sha:
                _fail("technical_universe_v4_previous_receipt_sha_mismatch")
            receipt = DailyMarketTechnicalUniverseV4Receipt.from_json(raw)
            if receipt.identity_sha256 != previous_id or receipt.to_dict()["sequence"] + 1 != body["sequence"]:
                _fail("technical_universe_v4_receipt_chain_invalid")

        chain = list(reversed(chain_reverse))
        full_chain = _validate_exact_store_layout(
            store,
            generation_dir,
            chain,
            generation_identity_sha256=generation_identity_sha256,
            plan_identity_sha256=plan_identity_sha256,
        )
        references: list[tuple[int, DailyMarketTechnicalUniverseV4ParentReceiptReference]] = []
        missing_data_codes: list[str] = []
        previous: DailyMarketTechnicalUniverseV4Receipt | None = None
        previous_sha: str | None = None
        calculation_identity_sha256: str | None = None
        for index, (item, item_sha) in enumerate(chain):
            _check_universe_read_cancelled(cancel_callback)
            body = item.to_dict()
            if index == 0:
                if body["status"] != "partial" or body["segment_reference"] is not None:
                    _fail("technical_universe_v4_initial_receipt_invalid")
            else:
                assert previous is not None and previous_sha is not None
                if (
                    body["sequence"] != index + 1
                    or body["previous_receipt_identity_sha256"] != previous.identity_sha256
                    or body["previous_receipt_sha256"] != previous_sha
                ):
                    _fail("technical_universe_v4_receipt_chain_invalid")
                _validate_transition(previous.to_dict(), body)
            segment_ref = body["segment_reference"]
            verified_parent_read: DailyMarketTechnicalParentCaptureV4VerifiedRead | None = None
            segment_index: int | None = None
            if segment_ref is not None:
                if body["status"] != "partial" or int(segment_ref["segment_index"]) != len(references):
                    _fail("technical_universe_v4_segment_progress_order_invalid")
                segment_index = int(segment_ref["segment_index"])
                parent_ref = DailyMarketTechnicalUniverseV4ParentReceiptReference.from_dict(segment_ref["parent_reference"])
                missing, _processed, segment_calculation_identity, verified_parent_read = _verify_parent_reference(
                    plan,
                    segment_index,
                    parent_ref,
                    store_output_root=self.output_root,
                    include_verified_read=parent_verified_callback is not None,
                    cancel_callback=cancel_callback,
                )
                _check_universe_read_cancelled(cancel_callback)
                if segment_calculation_identity is not None:
                    if (
                        calculation_identity_sha256 is not None
                        and segment_calculation_identity != calculation_identity_sha256
                    ):
                        _fail("technical_universe_v4_parent_calculation_identity_mismatch")
                    calculation_identity_sha256 = segment_calculation_identity
                references.append((segment_index, parent_ref))
                missing_data_codes.extend(missing)
            expected_last = references[-1][1] if references else None
            stored_last = (
                DailyMarketTechnicalUniverseV4ParentReceiptReference.from_dict(body["last_parent_reference"])
                if body["last_parent_reference"] is not None
                else None
            )
            if stored_last != expected_last:
                _fail("technical_universe_v4_last_parent_pin_mismatch")
            expected_counts = _counts_for(plan, references, missing_data_codes)
            actual_counts = DailyMarketTechnicalUniverseV4Counts.from_dict(body["counts"])
            if actual_counts != expected_counts:
                _fail("technical_universe_v4_receipt_counts_mismatch")
            if body["status"] == "complete":
                if len(references) != len(plan.segments) or expected_counts.pending_count != 0:
                    _fail("technical_universe_v4_false_complete")
            if verified_parent_read is not None:
                assert (
                    segment_ref is not None
                    and segment_index is not None
                    and parent_verified_callback is not None
                )
                _check_universe_read_cancelled(cancel_callback)
                try:
                    parent_verified_callback(segment_index, verified_parent_read)
                except DailyMarketTechnicalUniverseV4StoreError:
                    raise
                except Exception as exc:
                    raise DailyMarketTechnicalUniverseV4StoreError(
                        "technical_universe_v4_parent_verified_callback_failed",
                        str(exc),
                    ) from exc
                _check_universe_read_cancelled(cancel_callback)
                del verified_parent_read
            previous = item
            previous_sha = item_sha

        final_body = current.to_dict()
        if final_body["status"] == "complete" and len(references) != len(plan.segments):
            _fail("technical_universe_v4_false_complete")
        return (
            DailyMarketTechnicalUniverseV4VerifiedState(
                plan=plan,
                receipt=current,
                segment_parent_references=tuple(references),
                counts=DailyMarketTechnicalUniverseV4Counts.from_dict(final_body["counts"]),
                missing_data_stock_codes=tuple(sorted(missing_data_codes)),
                calculation_identity_sha256=calculation_identity_sha256,
            ),
            full_chain[-1][0].identity_sha256,
        )


def _validate_transition(previous: Mapping[str, Any], current: Mapping[str, Any]) -> None:
    prior_status = previous["status"]
    status = current["status"]
    segment = current["segment_reference"]
    if prior_status == "complete":
        _fail("technical_universe_v4_receipt_after_complete")
    if prior_status in {"cancelled", "failed"}:
        if status != "partial" or segment is not None:
            _fail("technical_universe_v4_resume_transition_invalid")
        if current["error_code"] is not None:
            _fail("technical_universe_v4_resume_error_code_invalid")
        return
    if prior_status != "partial":
        _fail("technical_universe_v4_receipt_transition_invalid")
    if status == "partial":
        if segment is None:
            _fail("technical_universe_v4_empty_progress_transition_invalid")
        if current["error_code"] is not None:
            _fail("technical_universe_v4_partial_error_code_invalid")
    elif status in {"cancelled", "failed"}:
        if segment is not None or current["error_code"] is None:
            _fail("technical_universe_v4_terminal_transition_invalid")
    elif status == "complete":
        if segment is not None or current["error_code"] is not None:
            _fail("technical_universe_v4_complete_transition_invalid")
    else:
        _fail("technical_universe_v4_receipt_transition_invalid")
