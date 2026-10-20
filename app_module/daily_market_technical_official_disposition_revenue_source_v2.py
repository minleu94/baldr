"""以固定 F17 bundle 與 daily monthly cohort 建立可 exact-reopen 的 V2 查詢。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import stat
from threading import get_ident
from typing import TYPE_CHECKING, Any, Literal, NoReturn, cast

from app_module.daily_market_monthly_revenue_reference_artifact_v3 import (
    DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3,
    UnverifiedDailyMarketMonthlyRevenueReferenceArtifactV3,
    publish_daily_market_monthly_revenue_reference_artifact_v3,
    read_daily_market_monthly_revenue_reference_artifact_v3,
)
from app_module.daily_market_monthly_revenue_yoy_index_v2 import (
    MAX_CODES_PER_BATCH,
    DailyMarketMonthlyRevenueYoyIndexCancelled,
    DailyMarketMonthlyRevenueYoyIndexError,
    DailyMarketMonthlyRevenueYoyIndexSessionV2,
)
from app_module.daily_market_technical_official_disposition_revenue_query_v2 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_SORT_CLAUSES_V2,
    DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2,
    DailyMarketTechnicalOfficialDispositionRevenueQueryPageV2,
    DailyMarketTechnicalOfficialDispositionRevenueQueryV2,
    DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV2,
    DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2,
)
from data_module.daily_market_monthly_revenue_cohort_v2 import (
    DailyMarketMonthlyRevenueSourceReferenceV3,
    decode_daily_market_monthly_revenue_source_reference_v3,
)
from data_module.daily_monthly_revenue_cohort import (
    DailyMonthlyRevenueCohortPin,
    DailyMonthlyRevenueCohortReader,
)
from data_module.recommendation_current_fundamental_provider import (
    RecommendationCurrentFundamentalProvider,
)
from data_module.selection_fact_readers import MAX_STOCK_CODES

if TYPE_CHECKING:
    from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
        DailyMarketTechnicalOfficialDispositionReadSessionV1,
    )
    from app_module.daily_market_technical_official_disposition_query_v1 import (
        DailyMarketTechnicalOfficialDispositionQueryV1,
    )


DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_SOURCE_SCHEMA_V2 = (
    "daily-market-technical-official-disposition-revenue-source.v2"
)
DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_RECIPE_SCHEMA_V2 = (
    "daily-market-technical-official-disposition-revenue-saved-recipe.v2"
)
_ISSUER = object()
_REPARSE_POINT = 0x400
_MAX_RECIPE_BYTES = 64 * 1024 * 1024
_MAX_RECIPE_DEPTH = 32
_HEX = frozenset("0123456789abcdef")


class DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error(ValueError):
    """雙來源 V2 exact open 的穩定拒絕錯誤。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"technical_official_revenue_source_v2_{code}")


class DailyMarketTechnicalOfficialDispositionRevenueSourceV2Cancelled(
    DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error
):
    """V2 source open 或 query 收到 cooperative cancellation。"""


def _fail(code: str) -> NoReturn:
    raise DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error(code)


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error(
            "canonical_json_invalid"
        ) from exc


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_sha256(value: object) -> str:
    return _sha256(_canonical_bytes(value))


def _require_sha(value: object, code: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in _HEX for character in value)
    ):
        _fail(code)
    return cast(str, value)


def _datetime_text(value: datetime) -> str:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        _fail("aware_datetime_required")
    return value.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: object, code: str) -> datetime:
    if type(value) is not str or len(value) > 128:
        _fail(code)
    try:
        result = datetime.fromisoformat(cast(str, value))
    except ValueError as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error(code) from exc
    if result.tzinfo is None or result.utcoffset() is None:
        _fail(code)
    normalized = result.astimezone(timezone.utc)
    if normalized.isoformat() != value:
        _fail(f"{code}_noncanonical")
    return normalized


def _poll_cancel(callback: Callable[[], object] | None) -> None:
    if callback is None:
        return
    if not callable(callback):
        _fail("cancel_callback_invalid")
    try:
        value = callback()
    except Exception as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error(
            "cancel_check_failed"
        ) from exc
    if type(value) is not bool:
        _fail("cancel_callback_invalid")
    if value:
        raise DailyMarketTechnicalOfficialDispositionRevenueSourceV2Cancelled("cancelled")


def _depth_preflight(text: str) -> None:
    depth = 0
    quoted = False
    escaped = False
    for character in text:
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character in "[{":
            depth += 1
            if depth > _MAX_RECIPE_DEPTH:
                _fail("recipe_json_depth_limit")
        elif character in "]}":
            depth -= 1
            if depth < 0:
                _fail("recipe_json_invalid")
    if quoted or escaped or depth != 0:
        _fail("recipe_json_invalid")


def _parse_bounded_object(raw: bytes | str, *, maximum: int, label: str) -> dict[str, object]:
    try:
        encoded = raw.encode("utf-8", errors="strict") if type(raw) is str else raw
        if type(encoded) is not bytes or not encoded or len(encoded) > maximum:
            _fail(f"{label}_byte_limit")
        text = encoded.decode("utf-8", errors="strict")
        _depth_preflight(text)

        def unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in pairs:
                if key in result:
                    _fail(f"{label}_duplicate_key")
                result[key] = value
            return result

        value = json.loads(
            text,
            object_pairs_hook=unique_pairs,
            parse_float=lambda _text: _fail(f"{label}_float_forbidden"),
            parse_constant=lambda _text: _fail(f"{label}_constant_invalid"),
        )
        if type(value) is not dict:
            _fail(f"{label}_object_required")
        if _canonical_bytes(value) != encoded:
            _fail(f"{label}_noncanonical")
        return cast(dict[str, object], value)
    except DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error(
            f"{label}_json_invalid"
        ) from exc


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if type(value) is not Decimal or not value.is_finite():
        _fail("minimum_yoy_percent_invalid")
    parts = value.as_tuple()
    if type(parts.exponent) is not int or len(parts.digits) > 64 or abs(parts.exponent) > 128:
        _fail("minimum_yoy_percent_bounds_invalid")
    if value == 0:
        return "0"
    rendered = format(value, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _recipe_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if type(value) is not str or len(value) > 256:
        _fail("recipe_decimal_invalid")
    try:
        parsed = Decimal(cast(str, value))
    except InvalidOperation as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error(
            "recipe_decimal_invalid"
        ) from exc
    if not parsed.is_finite() or _decimal_text(parsed) != value:
        _fail("recipe_decimal_noncanonical")
    return parsed


def _require_plain_string(value: object, code: str, *, maximum: int = 16 * 1024 * 1024) -> str:
    if type(value) is not str or not value or len(value.encode("utf-8", errors="strict")) > maximum:
        _fail(code)
    return cast(str, value)


def _overlaps(left: Path, right: Path) -> bool:
    left_text = os.path.normcase(os.path.abspath(str(left))).rstrip("\\/").casefold()
    right_text = os.path.normcase(os.path.abspath(str(right))).rstrip("\\/").casefold()
    separator = os.sep.casefold()
    return (
        left_text == right_text
        or left_text.startswith(right_text + separator)
        or right_text.startswith(left_text + separator)
    )


def _check_reparse_path(path: Path, *, final_may_not_exist: bool) -> None:
    absolute = Path(os.path.abspath(str(path)))
    if not absolute.is_absolute() or ".." in absolute.parts or "\x00" in str(absolute):
        _fail("path_must_be_absolute_normal")
    components: list[Path] = []
    current = absolute
    while current != current.parent:
        components.append(current)
        current = current.parent
    for component in reversed(components):
        try:
            info = component.lstat()
        except FileNotFoundError:
            if final_may_not_exist and component == absolute:
                continue
            _fail("path_component_missing")
        except OSError as exc:
            raise DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error(
                "path_component_unavailable"
            ) from exc
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
            _fail("path_reparse_component_refused")


def _guard_operation_root(
    operation_root: Path | str,
    *,
    f17_query: Any,
    reader: DailyMonthlyRevenueCohortReader,
    provider: RecommendationCurrentFundamentalProvider,
    artifact_root: Path,
    protected_roots: Sequence[Path],
) -> Path:
    if not isinstance(operation_root, Path) and type(operation_root) is not str:
        _fail("operation_root_invalid")
    raw = Path(operation_root).expanduser()
    if not raw.is_absolute() or ".." in raw.parts:
        _fail("operation_root_must_be_absolute_and_normalized")
    root = Path(os.path.abspath(str(raw)))
    if root.exists() or root.is_symlink():
        _fail("operation_root_must_be_new")
    if not root.parent.is_dir():
        _fail("operation_root_parent_missing")
    _check_reparse_path(root, final_may_not_exist=True)
    if not isinstance(protected_roots, (tuple, list)) or not protected_roots:
        _fail("protected_roots_required")
    protected: list[Path] = []
    for candidate in protected_roots:
        if not isinstance(candidate, Path) or not candidate.is_absolute() or ".." in candidate.parts:
            _fail("protected_root_invalid")
        protected.append(Path(os.path.abspath(str(candidate))))
    bundle_root = getattr(f17_query, "bundle_output_root", None)
    if type(bundle_root) is not str or not bundle_root:
        _fail("f17_bundle_root_missing")
    protected.append(Path(bundle_root))
    for field_name in ("db_file", "output_root", "monthly_source_root", "calendar_cache_path", "temporary_closure_path"):
        value = getattr(provider, field_name, None)
        if isinstance(value, Path):
            protected.append(value)
    roots = getattr(reader, "_roots", None)
    if not isinstance(roots, Mapping):
        _fail("daily_reader_roots_unavailable")
    for value in roots.values():
        if not isinstance(value, Path):
            _fail("daily_reader_root_invalid")
        protected.append(value)
    protected.append(artifact_root)
    data_root = os.environ.get("DATA_ROOT", "F:/Min/Python/Project/FA_Data")
    output_root = os.environ.get("OUTPUT_ROOT", str(Path(data_root) / "output"))
    for value in (data_root, output_root, os.environ.get("PERSONAL_DATA_ROOT"), os.environ.get("PERSONAL_STORE_ROOT")):
        if value:
            path = Path(value)
            if not path.is_absolute() or ".." in path.parts:
                _fail("configured_protected_root_invalid")
            protected.append(path)
    if any(_overlaps(root, candidate) for candidate in protected):
        _fail("operation_root_overlaps_source_or_protected_root")
    try:
        root.mkdir(exist_ok=False)
    except FileExistsError as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error(
            "operation_root_must_be_new"
        ) from exc
    except OSError as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error(
            "operation_root_create_failed"
        ) from exc
    _check_reparse_path(root, final_may_not_exist=False)
    return root


def _validate_reader_and_provider(
    *,
    provider: RecommendationCurrentFundamentalProvider,
    reader: DailyMonthlyRevenueCohortReader,
) -> DailyMonthlyRevenueCohortPin:
    if type(reader) is not DailyMonthlyRevenueCohortReader:
        _fail("daily_monthly_cohort_reader_invalid")
    if type(provider) is not RecommendationCurrentFundamentalProvider:
        _fail("monthly_provider_invalid")
    if provider.daily_source_snapshot_reader is not reader:
        _fail("monthly_provider_reader_port_mismatch")
    pin = reader.pin
    if type(pin) is not DailyMonthlyRevenueCohortPin:
        _fail("daily_monthly_cohort_pin_invalid")
    return pin


def _validate_cutoff_and_pin(f17_query: Any, pin: DailyMonthlyRevenueCohortPin) -> datetime:
    cutoff_value = getattr(f17_query, "decision_cutoff", None)
    if type(cutoff_value) is not datetime or cutoff_value.tzinfo is None or cutoff_value.utcoffset() is None:
        _fail("f17_cutoff_not_aware")
    cutoff = cutoff_value.astimezone(timezone.utc)
    if pin.available_hour.astimezone(timezone.utc) > cutoff:
        _fail("daily_cohort_available_after_f17_cutoff")
    if pin.time_basis_policy != "daily-hour.v1":
        _fail("daily_cohort_time_policy_unsupported")
    return cutoff


@dataclass(slots=True)
class _ExactReadStateV2:
    owner_thread_id: int
    f17_session: object | None
    monthly_index_session: DailyMarketMonthlyRevenueYoyIndexSessionV2 | None
    combined_session: object | None
    result: DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV2 | None
    request: DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2 | None
    page: DailyMarketTechnicalOfficialDispositionRevenueQueryPageV2 | None
    closed: bool = False
    monthly_connection_closed: bool = False


class _ExactAnchorV2:
    __slots__ = (
        "identity_sha256", "query", "result", "reference_identity_sha256",
        "reference_external_sha256", "descriptor_external_sha256", "subject", "locked",
    )
    identity_sha256: str
    query: DailyMarketTechnicalOfficialDispositionRevenueQueryV2
    result: DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV2
    reference_identity_sha256: str
    reference_external_sha256: str
    descriptor_external_sha256: str
    subject: DailyMarketTechnicalOfficialDispositionRevenueExactReadV2 | None
    locked: bool

    def __init__(
        self,
        identity_sha256: str,
        *,
        query: DailyMarketTechnicalOfficialDispositionRevenueQueryV2,
        result: DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV2,
        reference: DailyMarketMonthlyRevenueSourceReferenceV3,
        descriptor: DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3,
        issuer: object,
    ) -> None:
        if issuer is not _ISSUER:
            _fail("exact_anchor_issuer_invalid")
        object.__setattr__(self, "identity_sha256", identity_sha256)
        object.__setattr__(self, "query", query)
        object.__setattr__(self, "result", result)
        object.__setattr__(self, "reference_identity_sha256", reference.identity_sha256)
        object.__setattr__(self, "reference_external_sha256", reference.external_reference_sha256)
        object.__setattr__(self, "descriptor_external_sha256", descriptor.external_descriptor_sha256)
        object.__setattr__(self, "subject", None)
        object.__setattr__(self, "locked", True)

    def claim(self, subject: object) -> None:
        if self.subject is None:
            object.__setattr__(self, "subject", subject)
        elif self.subject is not subject:
            _fail("exact_anchor_subject_mismatch")

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "locked", False):
            raise AttributeError("exact source anchor is immutable")
        object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2:
    """V2 完整 recipe；canonical/hash 只固定輸入，不自授來源信任。"""

    f17_query_json: str
    revenue_query_json: str
    page_request_json: str
    monthly_source_reference_json: str
    monthly_source_reference_external_sha256: str
    monthly_source_content_identity_sha256: str
    monthly_cohort_sha256: str
    monthly_availability_status: Literal["cohort_hour_bound"]
    monthly_cohort_pin_json: str
    artifact_descriptor_json: str
    artifact_descriptor_external_sha256: str
    condition_combine_mode: Literal["AND", "OR"]
    unknown_policy: Literal["include", "exclude", "only"]
    minimum_yoy_percent: Decimal | None
    sort_clauses: tuple[DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2, ...]
    page_index: int
    page_size: int
    recipe_identity_sha256: str

    @classmethod
    def from_exact_read(
        cls,
        exact_read: DailyMarketTechnicalOfficialDispositionRevenueExactReadV2,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2:
        if type(exact_read) is not DailyMarketTechnicalOfficialDispositionRevenueExactReadV2:
            _fail("saved_recipe_exact_read_invalid")
        exact_read._validate_open()
        query = exact_read.query
        request = exact_read.request
        reference = exact_read.monthly_reference
        descriptor = exact_read.artifact_descriptor
        return cls._from_parts(
            f17_query=exact_read.f17_query,
            query=query,
            request=request,
            reference=reference,
            artifact_descriptor=descriptor,
        )

    @classmethod
    def _from_parts(
        cls,
        *,
        f17_query: Any,
        query: DailyMarketTechnicalOfficialDispositionRevenueQueryV2,
        request: DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2,
        reference: DailyMarketMonthlyRevenueSourceReferenceV3,
        artifact_descriptor: DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2:
        pin = reference.cohort_pin
        body: dict[str, object] = {
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_RECIPE_SCHEMA_V2,
            "f17_query_json": f17_query.to_json(),
            "revenue_query_json": query.to_json(),
            "page_request_json": request.to_json(),
            "monthly_source_reference_json": reference.to_json(),
            "monthly_source_reference_external_sha256": reference.external_reference_sha256,
            "monthly_source_content_identity_sha256": reference.source_content_identity_sha256,
            "monthly_cohort_sha256": reference.cohort_pin.cohort_sha256,
            "monthly_availability_status": reference.availability_status,
            "monthly_cohort_pin_json": _canonical_bytes(pin.to_dict()).decode("utf-8"),
            "artifact_descriptor_json": artifact_descriptor.to_json(),
            "artifact_descriptor_external_sha256": artifact_descriptor.external_descriptor_sha256,
            "condition_combine_mode": query.condition_combine_mode,
            "unknown_policy": query.unknown_policy,
            "minimum_yoy_percent": _decimal_text(query.minimum_yoy_percent),
            "sort_clauses": [item.to_dict() for item in query.sort_clauses],
            "page_index": request.page_index,
            "page_size": request.page_size,
        }
        return cls.from_dict({**body, "recipe_identity_sha256": _json_sha256(body)})

    def to_dict(self) -> dict[str, object]:
        body = _recipe_body_v2(self)
        if _json_sha256(body) != self.recipe_identity_sha256:
            _fail("saved_recipe_identity_mismatch")
        _validate_recipe_v2(self)
        return {**body, "recipe_identity_sha256": self.recipe_identity_sha256}

    def to_json(self) -> str:
        raw = _canonical_bytes(self.to_dict())
        if len(raw) > _MAX_RECIPE_BYTES:
            _fail("saved_recipe_byte_limit")
        return raw.decode("utf-8")

    @classmethod
    def from_dict(
        cls,
        value: object,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2:
        expected = {
            "schema_version", "f17_query_json", "revenue_query_json", "page_request_json",
            "monthly_source_reference_json", "monthly_source_reference_external_sha256",
            "monthly_source_content_identity_sha256", "monthly_cohort_sha256",
            "monthly_availability_status", "monthly_cohort_pin_json", "artifact_descriptor_json",
            "artifact_descriptor_external_sha256", "condition_combine_mode", "unknown_policy",
            "minimum_yoy_percent", "sort_clauses", "page_index", "page_size",
            "recipe_identity_sha256",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            _fail("saved_recipe_fields_invalid")
        payload = dict(value)
        if payload.get("schema_version") != DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_RECIPE_SCHEMA_V2:
            _fail("saved_recipe_schema_unsupported")
        sort_raw = payload.get("sort_clauses")
        if (
            type(sort_raw) is not list
            or not sort_raw
            or len(sort_raw) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_MAX_SORT_CLAUSES_V2
        ):
            _fail("saved_recipe_sort_invalid")
        clauses = tuple(DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2.from_dict(item) for item in sort_raw)
        combine_mode = payload.get("condition_combine_mode")
        unknown_policy = payload.get("unknown_policy")
        if (
            type(combine_mode) is not str
            or combine_mode not in {"AND", "OR"}
            or type(unknown_policy) is not str
            or unknown_policy not in {"include", "exclude", "only"}
        ):
            _fail("saved_recipe_policy_invalid")
        if type(payload.get("page_index")) is not int or type(payload.get("page_size")) is not int:
            _fail("saved_recipe_page_invalid")
        recipe = cls(
            f17_query_json=_require_plain_string(payload.get("f17_query_json"), "saved_recipe_f17_query_invalid"),
            revenue_query_json=_require_plain_string(payload.get("revenue_query_json"), "saved_recipe_query_invalid"),
            page_request_json=_require_plain_string(payload.get("page_request_json"), "saved_recipe_request_invalid"),
            monthly_source_reference_json=_require_plain_string(
                payload.get("monthly_source_reference_json"),
                "saved_recipe_reference_invalid",
                maximum=32 * 1024 * 1024,
            ),
            monthly_source_reference_external_sha256=_require_sha(payload.get("monthly_source_reference_external_sha256"), "saved_recipe_reference_sha_invalid"),
            monthly_source_content_identity_sha256=_require_sha(payload.get("monthly_source_content_identity_sha256"), "saved_recipe_content_sha_invalid"),
            monthly_cohort_sha256=_require_sha(payload.get("monthly_cohort_sha256"), "saved_recipe_cohort_sha_invalid"),
            monthly_availability_status=cast(Literal["cohort_hour_bound"], payload.get("monthly_availability_status")),
            monthly_cohort_pin_json=_require_plain_string(payload.get("monthly_cohort_pin_json"), "saved_recipe_pin_invalid"),
            artifact_descriptor_json=_require_plain_string(payload.get("artifact_descriptor_json"), "saved_recipe_descriptor_invalid"),
            artifact_descriptor_external_sha256=_require_sha(payload.get("artifact_descriptor_external_sha256"), "saved_recipe_descriptor_sha_invalid"),
            condition_combine_mode=cast(Literal["AND", "OR"], combine_mode),
            unknown_policy=cast(Literal["include", "exclude", "only"], unknown_policy),
            minimum_yoy_percent=_recipe_decimal(payload.get("minimum_yoy_percent")),
            sort_clauses=clauses,
            page_index=cast(int, payload.get("page_index")),
            page_size=cast(int, payload.get("page_size")),
            recipe_identity_sha256=_require_sha(payload.get("recipe_identity_sha256"), "saved_recipe_identity_invalid"),
        )
        _validate_recipe_v2(recipe)
        body = _recipe_body_v2(recipe)
        if _json_sha256(body) != recipe.recipe_identity_sha256:
            _fail("saved_recipe_identity_mismatch")
        return recipe

    @classmethod
    def from_json(
        cls,
        raw: bytes | str,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2:
        payload = _parse_bounded_object(raw, maximum=_MAX_RECIPE_BYTES, label="saved_recipe")
        return cls.from_dict(payload)


def _recipe_body_v2(recipe: DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2) -> dict[str, object]:
    return {
        "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_RECIPE_SCHEMA_V2,
        "f17_query_json": recipe.f17_query_json,
        "revenue_query_json": recipe.revenue_query_json,
        "page_request_json": recipe.page_request_json,
        "monthly_source_reference_json": recipe.monthly_source_reference_json,
        "monthly_source_reference_external_sha256": recipe.monthly_source_reference_external_sha256,
        "monthly_source_content_identity_sha256": recipe.monthly_source_content_identity_sha256,
        "monthly_cohort_sha256": recipe.monthly_cohort_sha256,
        "monthly_availability_status": recipe.monthly_availability_status,
        "monthly_cohort_pin_json": recipe.monthly_cohort_pin_json,
        "artifact_descriptor_json": recipe.artifact_descriptor_json,
        "artifact_descriptor_external_sha256": recipe.artifact_descriptor_external_sha256,
        "condition_combine_mode": recipe.condition_combine_mode,
        "unknown_policy": recipe.unknown_policy,
        "minimum_yoy_percent": _decimal_text(recipe.minimum_yoy_percent),
        "sort_clauses": [item.to_dict() for item in recipe.sort_clauses],
        "page_index": recipe.page_index,
        "page_size": recipe.page_size,
    }


def _validate_recipe_v2(recipe: DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2) -> None:
    if type(recipe.monthly_availability_status) is not str or recipe.monthly_availability_status != "cohort_hour_bound":
        _fail("saved_recipe_availability_invalid")
    try:
        from app_module.daily_market_technical_official_disposition_query_v1 import (
            DailyMarketTechnicalOfficialDispositionQueryV1,
        )
        f17 = DailyMarketTechnicalOfficialDispositionQueryV1.from_json(recipe.f17_query_json)
        query = DailyMarketTechnicalOfficialDispositionRevenueQueryV2.from_json(recipe.revenue_query_json)
        request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2.from_json(recipe.page_request_json)
        reference_wrapper = decode_daily_market_monthly_revenue_source_reference_v3(
            recipe.monthly_source_reference_json,
            expected_reference_sha256=recipe.monthly_source_reference_external_sha256,
        )
    except (TypeError, ValueError) as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error("saved_recipe_nested_payload_invalid") from exc
    reference = reference_wrapper.reference
    descriptor_raw = recipe.artifact_descriptor_json.encode("utf-8", errors="strict")
    descriptor_value = _parse_bounded_object(descriptor_raw, maximum=4 * 1024 * 1024, label="saved_recipe_descriptor")
    descriptor_fields = {
        "schema_version", "artifact_schema_version", "artifact_id", "reference_relative_path",
        "descriptor_relative_path", "reference_size_bytes", "reference_sha256",
        "source_reference_identity_sha256", "index_identity_sha256", "read_session_identity_sha256",
        "source_clock_identity_sha256", "source_content_identity_sha256",
        "finished_cohort_identity_sha256", "cohort_sha256", "decision_cutoff",
        "declared_stock_codes", "declared_stock_codes_sha256", "result_ledger_sha256",
        "fact_ledger_sha256", "reader_result_status_counts", "fact_state_counts",
        "projected_state_counts", "source_scope", "availability_status", "complete",
        "historical_pit_eligible", "formal_pit_eligible",
    }
    if (
        set(descriptor_value) != descriptor_fields
        or query.to_json() != recipe.revenue_query_json
        or request.to_json() != recipe.page_request_json
        or query.f17_query.to_json() != f17.to_json()
        or request.query.query_identity_sha256 != query.query_identity_sha256
        or query.condition_combine_mode != recipe.condition_combine_mode
        or query.unknown_policy != recipe.unknown_policy
        or query.minimum_yoy_percent != recipe.minimum_yoy_percent
        or query.sort_clauses != recipe.sort_clauses
        or request.page_index != recipe.page_index
        or request.page_size != recipe.page_size
        or reference.external_reference_sha256 != recipe.monthly_source_reference_external_sha256
        or reference.source_content_identity_sha256 != recipe.monthly_source_content_identity_sha256
        or reference.cohort_pin.cohort_sha256 != recipe.monthly_cohort_sha256
        or reference.availability_status != recipe.monthly_availability_status
        or query.monthly_source_reference_external_sha256 != recipe.monthly_source_reference_external_sha256
        or query.monthly_source_content_identity_sha256 != recipe.monthly_source_content_identity_sha256
        or query.monthly_cohort_sha256 != recipe.monthly_cohort_sha256
        or query.monthly_availability_status != "cohort_hour_bound"
        or _canonical_bytes(reference.cohort_pin.to_dict()).decode("utf-8") != recipe.monthly_cohort_pin_json
        or _sha256(descriptor_raw) != recipe.artifact_descriptor_external_sha256
        or descriptor_value.get("schema_version") != "daily-market-monthly-revenue-reference-artifact-descriptor.v3"
        or descriptor_value.get("artifact_schema_version") != "daily-market-monthly-revenue-reference-artifact.v3"
        or descriptor_value.get("reference_sha256") != recipe.monthly_source_reference_external_sha256
        or descriptor_value.get("source_reference_identity_sha256") != reference.identity_sha256
        or descriptor_value.get("source_content_identity_sha256") != reference.source_content_identity_sha256
        or descriptor_value.get("cohort_sha256") != reference.cohort_pin.cohort_sha256
        or descriptor_value.get("decision_cutoff") != reference.decision_cutoff
        or descriptor_value.get("declared_stock_codes") != list(reference.declared_stock_codes)
        or descriptor_value.get("source_scope") != "current_observed_only"
        or descriptor_value.get("availability_status") != "cohort_hour_bound"
        or descriptor_value.get("complete") is not True
        or descriptor_value.get("historical_pit_eligible") is not False
        or descriptor_value.get("formal_pit_eligible") is not False
    ):
        _fail("saved_recipe_monthly_source_mismatch")


class DailyMarketTechnicalOfficialDispositionRevenueExactReadV2:
    """同次 F17 與月營收 V2 query 的 reader-issued、可翻頁快照。"""

    __slots__ = ("_f17_query", "_monthly_reference", "_descriptor", "_query", "_identity", "_state", "_anchor", "_locked")
    _f17_query: DailyMarketTechnicalOfficialDispositionQueryV1
    _monthly_reference: DailyMarketMonthlyRevenueSourceReferenceV3
    _descriptor: DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3
    _query: DailyMarketTechnicalOfficialDispositionRevenueQueryV2
    _identity: str
    _state: _ExactReadStateV2
    _anchor: _ExactAnchorV2 | None
    _locked: bool

    def __init__(
        self,
        *,
        f17_query: DailyMarketTechnicalOfficialDispositionQueryV1,
        monthly_reference: DailyMarketMonthlyRevenueSourceReferenceV3,
        artifact_descriptor: DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3,
        query: DailyMarketTechnicalOfficialDispositionRevenueQueryV2,
        identity: str,
        state: _ExactReadStateV2,
        issuer: object,
    ) -> None:
        if issuer is not _ISSUER:
            _fail("exact_read_not_reader_issued")
        object.__setattr__(self, "_locked", False)
        object.__setattr__(self, "_f17_query", f17_query)
        object.__setattr__(self, "_monthly_reference", monthly_reference)
        object.__setattr__(self, "_descriptor", artifact_descriptor)
        object.__setattr__(self, "_query", query)
        object.__setattr__(self, "_identity", identity)
        object.__setattr__(self, "_state", state)
        result = state.result
        if result is None:
            _fail("exact_read_result_unavailable")
        anchor = _ExactAnchorV2(
            identity,
            query=query,
            result=result,
            reference=monthly_reference,
            descriptor=artifact_descriptor,
            issuer=_ISSUER,
        )
        object.__setattr__(self, "_anchor", anchor)
        anchor.claim(self)
        self._validate_open()
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_locked", False):
            raise AttributeError("exact read is immutable")
        object.__setattr__(self, name, value)

    @property
    def closed(self) -> bool:
        return self._state.closed

    @property
    def query(self) -> DailyMarketTechnicalOfficialDispositionRevenueQueryV2:
        self._validate_open()
        return self._query

    @property
    def result(self) -> DailyMarketTechnicalOfficialDispositionRevenueVerifiedQueryResultV2:
        self._validate_open()
        result = self._state.result
        if result is None:
            _fail("source_result_closed")
        return result

    @property
    def request(self) -> DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2:
        self._validate_open()
        request = self._state.request
        if request is None:
            _fail("source_request_unavailable")
        return request

    @property
    def page_request(self) -> DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2:
        return self.request

    @property
    def page(self) -> DailyMarketTechnicalOfficialDispositionRevenueQueryPageV2:
        self._validate_open()
        page = self._state.page
        if page is None:
            _fail("source_page_unavailable")
        return page

    @property
    def f17_query(self) -> DailyMarketTechnicalOfficialDispositionQueryV1:
        self._validate_open()
        return self._f17_query

    @property
    def monthly_reference(self) -> DailyMarketMonthlyRevenueSourceReferenceV3:
        self._validate_open()
        return self._monthly_reference

    @property
    def monthly_source_reference(self) -> DailyMarketMonthlyRevenueSourceReferenceV3:
        return self.monthly_reference

    @property
    def monthly_cohort_pin(self) -> DailyMonthlyRevenueCohortPin:
        self._validate_open()
        return self._monthly_reference.cohort_pin

    @property
    def artifact_descriptor(self) -> DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3:
        self._validate_open()
        return self._descriptor

    @property
    def source_pair_identity_sha256(self) -> str:
        self._validate_open()
        return self._identity

    @property
    def monthly_source_reference_external_sha256(self) -> str:
        self._validate_open()
        return self._monthly_reference.external_reference_sha256

    @property
    def source_scope(self) -> Literal["current_only"]:
        self._validate_open()
        return "current_only"

    @property
    def availability_status(self) -> Literal["unknown"]:
        self._validate_open()
        return "unknown"

    @property
    def monthly_availability_status(self) -> Literal["cohort_hour_bound"]:
        self._validate_open()
        return "cohort_hour_bound"

    @property
    def official_available_at(self) -> None:
        self._validate_open()
        return None

    @property
    def monthly_official_available_at(self) -> None:
        self._validate_open()
        return None

    @property
    def historical_pit_eligible(self) -> Literal[False]:
        self._validate_open()
        return False

    @property
    def formal_pit_eligible(self) -> Literal[False]:
        self._validate_open()
        return False

    @property
    def monthly_sqlite_connection_closed(self) -> bool:
        return self._state.monthly_connection_closed

    @property
    def saved_recipe(self) -> DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2:
        self._validate_open()
        return DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2.from_exact_read(self)

    def read_page(
        self,
        page_index: int,
        page_size: int,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueQueryPageV2:
        _poll_cancel(cancel_callback)
        self._validate_open()
        request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2.create(
            self.query,
            page_index=page_index,
            page_size=page_size,
        )
        return self.read_page_request(request, cancel_callback=cancel_callback)

    def read_page_request(
        self,
        request: DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2 | bytes | str,
        *,
        cancel_callback: Callable[[], object] | None = None,
    ) -> DailyMarketTechnicalOfficialDispositionRevenueQueryPageV2:
        _poll_cancel(cancel_callback)
        self._validate_open()
        if type(request) in {str, bytes}:
            request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2.from_json(cast(bytes | str, request))
        if type(request) is not DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2:
            _fail("page_request_invalid")
        if request.query.query_identity_sha256 != self.query.query_identity_sha256:
            _fail("page_request_query_mismatch")
        result = self.result
        page = result.read_page_request(request, cancel_callback=cancel_callback)
        _poll_cancel(cancel_callback)
        page.to_dict()
        self._state.request = request
        self._state.page = page
        return page

    def close(self) -> None:
        state = self._state
        if state.closed:
            return
        if get_ident() != state.owner_thread_id:
            _fail("wrong_owner_thread")
        session = state.monthly_index_session
        cleanup_error: BaseException | None = None
        try:
            if session is not None:
                session.close()
                if not session.closed:
                    _fail("monthly_connection_not_closed")
        except BaseException as exc:
            cleanup_error = exc
        finally:
            state.monthly_connection_closed = session is None or session.closed
            state.closed = True
            state.f17_session = None
            state.combined_session = None
            state.monthly_index_session = None
            state.result = None
            state.request = None
            state.page = None
        if cleanup_error is not None:
            raise cleanup_error

    def __enter__(self) -> DailyMarketTechnicalOfficialDispositionRevenueExactReadV2:
        self._validate_open()
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: object) -> Literal[False]:
        try:
            self.close()
        except BaseException as close_error:
            if exc is not None:
                raise DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error("context_close_failed") from BaseExceptionGroup(
                    "primary exact read failure and close failure", [exc, close_error]
                )
            raise
        return False

    def _validate_open(self) -> None:
        if self._state.closed:
            _fail("source_operation_closed")
        if get_ident() != self._state.owner_thread_id:
            _fail("wrong_owner_thread")
        result = self._state.result
        if (
            type(self._anchor) is not _ExactAnchorV2
            or self._anchor.subject is not self
            or self._anchor.identity_sha256 != self._identity
            or result is None
            or self._anchor.query is not self._query
            or self._anchor.result is not result
            or result.query is not self._query
            or type(self._monthly_reference) is not DailyMarketMonthlyRevenueSourceReferenceV3
            or type(self._descriptor) is not DailyMarketMonthlyRevenueReferenceArtifactDescriptorV3
            or self._anchor.reference_identity_sha256 != self._monthly_reference.identity_sha256
            or self._anchor.reference_external_sha256 != self._monthly_reference.external_reference_sha256
            or self._anchor.descriptor_external_sha256 != self._descriptor.external_descriptor_sha256
        ):
            _fail("source_operation_not_reader_issued")
        request = self._state.request
        page = self._state.page
        if (
            request is None
            or page is None
            or request.query.query_identity_sha256 != self._query.query_identity_sha256
            or page._result is not result
            or page.query is not self._query
            or page.request_identity_sha256 != request.request_identity_sha256
        ):
            _fail("source_operation_page_binding_mismatch")
        page.to_dict()


def _provider_for_reader(
    monthly_provider: RecommendationCurrentFundamentalProvider,
    reader: DailyMonthlyRevenueCohortReader,
    *,
    factory_mode: bool,
) -> RecommendationCurrentFundamentalProvider:
    if type(monthly_provider) is not RecommendationCurrentFundamentalProvider:
        _fail("monthly_provider_invalid")
    if factory_mode:
        if monthly_provider.daily_source_snapshot_reader is not None:
            _fail("monthly_provider_factory_base_must_have_no_reader")
        try:
            provider = monthly_provider.with_daily_source_snapshot_reader(reader)
        except (TypeError, ValueError) as exc:
            raise DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error("monthly_provider_clone_failed") from exc
        if type(provider) is not RecommendationCurrentFundamentalProvider:
            _fail("monthly_provider_clone_type_invalid")
    else:
        provider = monthly_provider
    _validate_reader_and_provider(provider=provider, reader=reader)
    return provider


def open_daily_market_technical_official_disposition_revenue_bundle_source_v2(
    *,
    bundle_output_root: str | Path,
    bundle_identity_sha256: str,
    expected_manifest_sha256: str,
    row_scope_filter: Sequence[Any],
    operation_root: Path | str,
    monthly_provider: RecommendationCurrentFundamentalProvider,
    monthly_reference_artifact_root: Path,
    artifact_id: str,
    protected_roots: Sequence[Path],
    daily_monthly_cohort_reader: DailyMonthlyRevenueCohortReader | None = None,
    daily_monthly_cohort_reader_factory: Callable[[datetime], DailyMonthlyRevenueCohortReader] | None = None,
    rule_state_filters: Sequence[Any] = (),
    combine_mode: Literal["AND", "OR"] = "AND",
    market_assignment_states: Sequence[str] = (),
    official_disposal_states: Sequence[str] = (),
    outer_stock_filter_mode: Literal["all", "explicit_codes"] = "all",
    outer_stock_codes: Sequence[str] = (),
    f17_sort_clauses: Sequence[Any] = (),
    ma_states: Sequence[str] | None = None,
    minimum_yoy_percent: Decimal | None = None,
    condition_combine_mode: Literal["AND", "OR"] = "AND",
    unknown_policy: Literal["include", "exclude", "only"] = "include",
    sort_clauses: Sequence[DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2] = (),
    page_index: int = 0,
    page_size: int = 50,
    cancel_callback: Callable[[], object] | None = None,
) -> DailyMarketTechnicalOfficialDispositionRevenueExactReadV2:
    """先 exact-open F17，再以同一 cutoff 選定並驗證完整 daily cohort。"""

    _poll_cancel(cancel_callback)
    if type(monthly_provider) is not RecommendationCurrentFundamentalProvider:
        _fail("monthly_provider_invalid")
    if (daily_monthly_cohort_reader is None) == (daily_monthly_cohort_reader_factory is None):
        _fail("daily_reader_or_factory_required_exclusively")
    reader_factory = daily_monthly_cohort_reader_factory
    if reader_factory is not None and not callable(reader_factory):
        _fail("daily_reader_factory_invalid")
    from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
        open_daily_market_technical_official_disposition_bundle_session_v1,
    )
    f17_session: DailyMarketTechnicalOfficialDispositionReadSessionV1 | None = open_daily_market_technical_official_disposition_bundle_session_v1(
        bundle_output_root=bundle_output_root,
        bundle_identity_sha256=bundle_identity_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        row_scope_filter=row_scope_filter,
        rule_state_filters=rule_state_filters,
        combine_mode=combine_mode,
        market_assignment_states=market_assignment_states,
        official_disposal_states=official_disposal_states,
        outer_stock_filter_mode=outer_stock_filter_mode,
        outer_stock_codes=outer_stock_codes,
        sort_clauses=f17_sort_clauses,
        cancel_callback=cancel_callback,
    )
    if f17_session is None:
        _fail("f17_source_session_unavailable")
    try:
        f17_query = f17_session.query
        declared_codes = f17_session.verified_declared_stock_codes(cancel_callback=cancel_callback)
        if (
            not declared_codes
            or len(declared_codes) > MAX_STOCK_CODES
            or len(set(declared_codes)) != len(declared_codes)
            or tuple(sorted(declared_codes)) != declared_codes
        ):
            _fail("f17_declared_cohort_invalid")
        cutoff = f17_query.decision_cutoff
        _poll_cancel(cancel_callback)
        factory_mode = reader_factory is not None
        if reader_factory is not None:
            if monthly_provider.daily_source_snapshot_reader is not None:
                _fail("monthly_provider_factory_base_must_have_no_reader")
            try:
                reader = reader_factory(cutoff)
            except Exception as exc:
                raise DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error("daily_reader_factory_failed") from exc
            if type(reader) is not DailyMonthlyRevenueCohortReader:
                _fail("daily_reader_factory_returned_invalid_type")
            provider = _provider_for_reader(monthly_provider, reader, factory_mode=True)
        else:
            reader = cast(DailyMonthlyRevenueCohortReader, daily_monthly_cohort_reader)
            provider = _provider_for_reader(monthly_provider, reader, factory_mode=False)
        _poll_cancel(cancel_callback)
        pin = reader.pin
        normalized_cutoff = _validate_cutoff_and_pin(f17_query, pin)
        if len(reader.verify_cohort()) != len(pin.required_markets):
            _fail("daily_cohort_verification_empty")
        _poll_cancel(cancel_callback)
        root = _guard_operation_root(
            operation_root,
            f17_query=f17_query,
            reader=reader,
            provider=provider,
            artifact_root=monthly_reference_artifact_root,
            protected_roots=protected_roots,
        )
        return _open_and_publish_v2(
            f17_query=f17_query,
            f17_session=f17_session,
            provider=provider,
            daily_reader=reader,
            pin=pin,
            cutoff=normalized_cutoff,
            declared_codes=declared_codes,
            operation_root=root,
            monthly_reference_artifact_root=monthly_reference_artifact_root,
            artifact_id=artifact_id,
            protected_roots=protected_roots,
            expected_reference=None,
            expected_reference_sha256=None,
            recipe_inputs=(
                ma_states,
                minimum_yoy_percent,
                condition_combine_mode,
                unknown_policy,
                tuple(sort_clauses),
            ),
            saved_query=None,
            saved_request=None,
            cancel_callback=cancel_callback,
            page_index=page_index,
            page_size=page_size,
        )
    except BaseException:
        f17_session = None
        raise


def reopen_daily_market_technical_official_disposition_revenue_from_recipe_v2(
    saved_recipe: DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2 | bytes | str,
    *,
    operation_root: Path | str,
    monthly_provider: RecommendationCurrentFundamentalProvider,
    daily_monthly_cohort_reader: DailyMonthlyRevenueCohortReader,
    monthly_reference_artifact_root: Path,
    artifact_id: str,
    expected_descriptor_sha256: str,
    expected_monthly_source_reference_sha256: str,
    protected_roots: Sequence[Path],
    cancel_callback: Callable[[], object] | None = None,
) -> DailyMarketTechnicalOfficialDispositionRevenueExactReadV2:
    """由外部固定的 descriptor/reference SHA exact reopen，不重選批次。"""

    _poll_cancel(cancel_callback)
    recipe = _parse_recipe_v2(saved_recipe)
    descriptor_sha = _require_sha(expected_descriptor_sha256, "external_descriptor_sha_invalid")
    reference_sha = _require_sha(expected_monthly_source_reference_sha256, "external_reference_sha_invalid")
    if (
        descriptor_sha != recipe.artifact_descriptor_external_sha256
        or reference_sha != recipe.monthly_source_reference_external_sha256
    ):
        _fail("recipe_external_anchor_mismatch")
    artifact_raw = recipe.artifact_descriptor_json.encode("utf-8", errors="strict")
    try:
        artifact = read_daily_market_monthly_revenue_reference_artifact_v3(
            monthly_reference_artifact_root,
            descriptor=artifact_raw,
            expected_descriptor_sha256=descriptor_sha,
            protected_roots=protected_roots,
        )
    except (TypeError, ValueError, OSError) as exc:
        raise DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error(
            f"monthly_artifact_exact_read_failed:{type(exc).__name__}"
        ) from exc
    if type(artifact) is not UnverifiedDailyMarketMonthlyRevenueReferenceArtifactV3:
        _fail("monthly_artifact_reader_type_invalid")
    reference_wrapper = artifact.source_reference
    reference = reference_wrapper.reference
    if (
        reference_wrapper.external_reference_sha256 != reference_sha
        or reference.to_json() != recipe.monthly_source_reference_json
        or _canonical_bytes(reference.cohort_pin.to_dict()).decode("utf-8") != recipe.monthly_cohort_pin_json
    ):
        _fail("monthly_artifact_recipe_reference_mismatch")
    if _validate_reader_and_provider(
        provider=monthly_provider,
        reader=daily_monthly_cohort_reader,
    ) != reference.cohort_pin:
        _fail("daily_reader_does_not_match_saved_pin")
    from app_module.daily_market_technical_official_disposition_query_v1 import (
        DailyMarketTechnicalOfficialDispositionQueryV1,
    )
    from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
        open_daily_market_technical_official_disposition_read_session_v1,
    )

    f17_query = DailyMarketTechnicalOfficialDispositionQueryV1.from_json(recipe.f17_query_json)
    _validate_cutoff_and_pin(f17_query, reference.cohort_pin)
    if reference.declared_stock_codes != tuple(sorted(reference.declared_stock_codes)):
        _fail("saved_reference_code_order_invalid")
    f17_session: DailyMarketTechnicalOfficialDispositionReadSessionV1 | None = open_daily_market_technical_official_disposition_read_session_v1(
        f17_query,
        cancel_callback=cancel_callback,
    )
    if f17_session is None:
        _fail("f17_source_session_unavailable")
    try:
        declared_codes = f17_session.verified_declared_stock_codes(cancel_callback=cancel_callback)
        if declared_codes != reference.declared_stock_codes:
            _fail("saved_reference_f17_cohort_mismatch")
        pin = daily_monthly_cohort_reader.pin
        cutoff = _validate_cutoff_and_pin(f17_query, pin)
        if pin != reference.cohort_pin:
            _fail("daily_reader_saved_pin_mismatch")
        root = _guard_operation_root(
            operation_root,
            f17_query=f17_query,
            reader=daily_monthly_cohort_reader,
            provider=monthly_provider,
            artifact_root=monthly_reference_artifact_root,
            protected_roots=protected_roots,
        )
        saved_query = DailyMarketTechnicalOfficialDispositionRevenueQueryV2.from_json(recipe.revenue_query_json)
        saved_request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2.from_json(recipe.page_request_json)
        return _open_and_publish_v2(
            f17_query=f17_query,
            f17_session=f17_session,
            provider=monthly_provider,
            daily_reader=daily_monthly_cohort_reader,
            pin=pin,
            cutoff=cutoff,
            declared_codes=declared_codes,
            operation_root=root,
            monthly_reference_artifact_root=monthly_reference_artifact_root,
            artifact_id=artifact_id,
            protected_roots=protected_roots,
            expected_reference=reference,
            expected_reference_sha256=reference_sha,
            recipe_inputs=(
                saved_query.ma_query.ma_states,
                saved_query.minimum_yoy_percent,
                saved_query.condition_combine_mode,
                saved_query.unknown_policy,
                saved_query.sort_clauses,
            ),
            saved_query=saved_query,
            saved_request=saved_request,
            cancel_callback=cancel_callback,
            page_index=saved_request.page_index,
            page_size=saved_request.page_size,
            saved_recipe=recipe,
        )
    except BaseException:
        f17_session = None
        raise


def _parse_recipe_v2(
    value: DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2 | bytes | str,
) -> DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2:
    if type(value) is DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2:
        recipe = cast(DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2, value)
        recipe.to_json()
        return recipe
    if type(value) in {bytes, str}:
        return DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2.from_json(cast(bytes | str, value))
    _fail("saved_recipe_invalid")


def _stable_reference_matches(
    actual: DailyMarketMonthlyRevenueSourceReferenceV3,
    expected: DailyMarketMonthlyRevenueSourceReferenceV3,
) -> bool:
    return (
        actual.source_content_identity_sha256 == expected.source_content_identity_sha256
        and actual.declared_stock_codes == expected.declared_stock_codes
        and actual.decision_cutoff == expected.decision_cutoff
        and actual.cohort_pin == expected.cohort_pin
        and actual.result_identity_by_stock == expected.result_identity_by_stock
        and actual.fact_identity_by_stock == expected.fact_identity_by_stock
        and actual.reader_result_status_counts == expected.reader_result_status_counts
        and actual.fact_state_counts == expected.fact_state_counts
        and actual.availability_status == "cohort_hour_bound"
        and actual.historical_pit_eligible is False
        and actual.formal_pit_eligible is False
    )


def _verify_saved_query_conditions(
    saved: DailyMarketTechnicalOfficialDispositionRevenueQueryV2,
    reopened: DailyMarketTechnicalOfficialDispositionRevenueQueryV2,
    *,
    f17_query: DailyMarketTechnicalOfficialDispositionQueryV1,
) -> None:
    if (
        saved.f17_query.to_json() != f17_query.to_json()
        or reopened.f17_query.to_json() != f17_query.to_json()
        or saved.ma_query.ma_states != reopened.ma_query.ma_states
        or saved.minimum_yoy_percent != reopened.minimum_yoy_percent
        or saved.condition_combine_mode != reopened.condition_combine_mode
        or saved.unknown_policy != reopened.unknown_policy
        or saved.sort_clauses != reopened.sort_clauses
    ):
        _fail("saved_query_conditions_changed")


def _open_and_publish_v2(
    *,
    f17_query: Any,
    f17_session: Any,
    provider: RecommendationCurrentFundamentalProvider,
    daily_reader: DailyMonthlyRevenueCohortReader,
    pin: DailyMonthlyRevenueCohortPin,
    cutoff: datetime,
    declared_codes: tuple[str, ...],
    operation_root: Path,
    monthly_reference_artifact_root: Path,
    artifact_id: str,
    protected_roots: Sequence[Path],
    expected_reference: DailyMarketMonthlyRevenueSourceReferenceV3 | None,
    expected_reference_sha256: str | None,
    recipe_inputs: tuple[Sequence[str] | None, Decimal | None, Literal["AND", "OR"], Literal["include", "exclude", "only"], Sequence[DailyMarketTechnicalOfficialDispositionRevenueSortClauseV2]],
    saved_query: DailyMarketTechnicalOfficialDispositionRevenueQueryV2 | None,
    saved_request: DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2 | None,
    cancel_callback: Callable[[], object] | None,
    page_index: int,
    page_size: int,
    saved_recipe: DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2 | None = None,
    archived_reference: object | None = None,
    expected_archive_reference_sha256: str | None = None,
) -> DailyMarketTechnicalOfficialDispositionRevenueExactReadV2:
    from app_module.daily_market_technical_official_disposition_query_reader_v1 import (
        DailyMarketTechnicalOfficialDispositionReadSessionV1,
        DailyMarketTechnicalOfficialDispositionQueryReaderV1Error,
    )

    _poll_cancel(cancel_callback)
    index_session: DailyMarketMonthlyRevenueYoyIndexSessionV2 | None = None
    try:
        if type(f17_session) is not DailyMarketTechnicalOfficialDispositionReadSessionV1:
            _fail("f17_session_type_invalid")
        if f17_session.query.to_json() != f17_query.to_json():
            _fail("f17_query_changed")
        actual_codes = f17_session.verified_declared_stock_codes(cancel_callback=cancel_callback)
        if actual_codes != declared_codes or actual_codes != tuple(sorted(actual_codes)):
            _fail("f17_declared_cohort_changed")
        if not actual_codes or len(actual_codes) > MAX_STOCK_CODES:
            _fail("f17_declared_cohort_bounds")
        if type(pin) is not DailyMonthlyRevenueCohortPin or pin != daily_reader.pin:
            _fail("daily_pin_changed_before_open")
        _validate_cutoff_and_pin(f17_query, pin)
        daily_reader.verify_cohort()
        _poll_cancel(cancel_callback)
        snapshot_root = operation_root / "monthly_snapshot_operations"
        if archived_reference is not None:
            from data_module.fundamental_read_snapshot_raw_archive_v2 import FundamentalReadSnapshotRawArchiveReferenceV2
            if (type(archived_reference) is not FundamentalReadSnapshotRawArchiveReferenceV2
                    or expected_reference is None or expected_reference_sha256 is None
                    or expected_archive_reference_sha256 is None):
                _fail("archive_requires_crossbound_original_reference_and_external_sha")
            index_session = DailyMarketMonthlyRevenueYoyIndexSessionV2.open_exact_archived(
                provider, daily_monthly_cohort_reader=daily_reader, snapshot_root=snapshot_root,
                source_reference=expected_reference, expected_reference_sha256=expected_reference_sha256,
                raw_archive_reference=archived_reference,
                expected_archive_reference_sha256=expected_archive_reference_sha256,
                stock_codes=actual_codes, cutoff_at=cutoff,
                cancel_callback=cast(Callable[[], bool] | None, cancel_callback))
        elif expected_archive_reference_sha256 is not None:
            _fail("archive_reference_missing_for_external_sha")
        elif expected_reference is None:
            index_session = DailyMarketMonthlyRevenueYoyIndexSessionV2.open(
                provider,
                daily_monthly_cohort_reader=daily_reader,
                snapshot_root=snapshot_root,
                stock_codes=actual_codes,
                cutoff_at=cutoff,
                cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
            )
        else:
            if expected_reference_sha256 is None:
                _fail("expected_reference_external_sha_required")
            index_session = DailyMarketMonthlyRevenueYoyIndexSessionV2.open_exact(
                provider,
                daily_monthly_cohort_reader=daily_reader,
                snapshot_root=snapshot_root,
                source_reference=expected_reference,
                expected_reference_sha256=expected_reference_sha256,
                stock_codes=actual_codes,
                cutoff_at=cutoff,
                cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
            )
        if (
            index_session.declared_stock_codes != actual_codes
            or index_session.decision_cutoff.astimezone(timezone.utc) != cutoff.astimezone(timezone.utc)
            or index_session.closed
        ):
            _fail("monthly_index_open_scope_mismatch")
        for offset in range(0, len(actual_codes), MAX_CODES_PER_BATCH):
            _poll_cancel(cancel_callback)
            index_session.load_batch(actual_codes[offset:offset + MAX_CODES_PER_BATCH])
        index = index_session.finish()
        if not index_session.closed:
            _fail("monthly_source_not_closed_after_finish")
        if (
            not index.is_reader_issued
            or index.declared_stock_codes != actual_codes
            or index.cohort_pin != pin
            or index.decision_cutoff.astimezone(timezone.utc) != cutoff.astimezone(timezone.utc)
            or index.availability_status != "cohort_hour_bound"
            or index.source_scope != "current_observed_only"
            or index.historical_pit_eligible is not False
            or index.formal_pit_eligible is not False
        ):
            _fail("monthly_index_identity_scope_or_time_mismatch")
        entries = index_session.validated_entries()
        reference = index_session.source_reference
        if (
            type(reference) is not DailyMarketMonthlyRevenueSourceReferenceV3
            or reference.cohort_pin != pin
            or reference.declared_stock_codes != actual_codes
            or reference.decision_cutoff != cutoff.astimezone(timezone.utc).isoformat()
            or reference.source_content_identity_sha256 != index.source_content_identity_sha256
            or reference.result_identity_by_stock != index.result_identity_by_stock
            or reference.fact_identity_by_stock != index.fact_identity_by_stock
            or reference.reader_result_status_counts != index.reader_result_status_counts
            or reference.fact_state_counts != index.fact_state_counts
            or reference.availability_status != "cohort_hour_bound"
            or reference.source_scope != "current_observed_only"
            or reference.historical_pit_eligible is not False
            or reference.formal_pit_eligible is not False
            or tuple(entry.stock_code for entry in entries) != actual_codes
        ):
            _fail("monthly_source_reference_scope_or_ledger_mismatch")
        if expected_reference is not None and not _stable_reference_matches(reference, expected_reference):
            _fail("monthly_source_reference_reissue_mismatch")
        raw_reference = reference.to_json().encode("utf-8", errors="strict")
        if _sha256(raw_reference) != reference.external_reference_sha256:
            _fail("monthly_reference_canonical_hash_mismatch")
        _poll_cancel(cancel_callback)
        bound_session = f17_session.with_monthly_revenue_yoy_index_v2(
            index_session,
            cancel_callback=cancel_callback,
        )
        ma_states, minimum_yoy, combine_mode, policy, clauses = recipe_inputs
        query = bound_session.create_revenue_query_v2(
            ma_states=ma_states,
            minimum_yoy_percent=minimum_yoy,
            condition_combine_mode=combine_mode,
            unknown_policy=policy,
            sort_clauses=clauses,
        )
        if query.f17_query.to_json() != f17_query.to_json():
            _fail("revenue_query_f17_binding_mismatch")
        if saved_query is not None:
            _verify_saved_query_conditions(saved_query, query, f17_query=f17_query)
        if saved_recipe is not None:
            if (
                saved_recipe.f17_query_json != f17_query.to_json()
                or saved_recipe.condition_combine_mode != query.condition_combine_mode
                or saved_recipe.unknown_policy != query.unknown_policy
                or saved_recipe.minimum_yoy_percent != query.minimum_yoy_percent
                or saved_recipe.sort_clauses != query.sort_clauses
            ):
                _fail("saved_recipe_query_conditions_mismatch")
        result = bound_session.execute_revenue_query_v2(query, cancel_callback=cancel_callback)
        if result.query.query_identity_sha256 != query.query_identity_sha256:
            _fail("revenue_result_query_mismatch")
        request = DailyMarketTechnicalOfficialDispositionRevenuePageRequestV2.create(
            query,
            page_index=page_index if saved_request is None else saved_request.page_index,
            page_size=page_size if saved_request is None else saved_request.page_size,
        )
        page = result.read_page_request(request, cancel_callback=cancel_callback)
        if (
            page.operation_identity_sha256 != result.operation_identity_sha256
            or page.query.query_identity_sha256 != query.query_identity_sha256
            or page.request_identity_sha256 != request.request_identity_sha256
            or page.source_pins != result.source_pins
            or page.scope != "current_only"
            or page.availability_status != "unknown"
            or page.historical_pit_eligible is not False
        ):
            _fail("initial_page_identity_or_scope_mismatch")
        _poll_cancel(cancel_callback)
        descriptor = publish_daily_market_monthly_revenue_reference_artifact_v3(
            monthly_reference_artifact_root,
            artifact_id=artifact_id,
            index_session=index_session,
            protected_roots=protected_roots,
            cancel_callback=cast(Callable[[], bool] | None, cancel_callback),
        )
        if (
            descriptor.reference_sha256 != reference.external_reference_sha256
            or descriptor.source_reference_identity_sha256 != reference.identity_sha256
            or descriptor.source_content_identity_sha256 != reference.source_content_identity_sha256
            or descriptor.cohort_sha256 != pin.cohort_sha256
            or descriptor.availability_status != "cohort_hour_bound"
            or descriptor.complete is not True
            or descriptor.historical_pit_eligible is not False
            or descriptor.formal_pit_eligible is not False
        ):
            _fail("monthly_artifact_descriptor_mismatch")
        pair_identity = _json_sha256({
            "schema_version": DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_SOURCE_SCHEMA_V2,
            "f17_query_identity_sha256": f17_query.query_identity_sha256,
            "bundle_identity_sha256": f17_query.bundle_identity_sha256,
            "bundle_manifest_sha256": f17_query.expected_manifest_sha256,
            "monthly_reference_sha256": reference.external_reference_sha256,
            "monthly_reference_identity_sha256": reference.identity_sha256,
            "monthly_cohort_sha256": pin.cohort_sha256,
            "monthly_index_identity_sha256": index.index_identity_sha256,
            "monthly_read_session_identity_sha256": index_session.read_session_identity_sha256,
            "revenue_query_identity_sha256": query.query_identity_sha256,
            "operation_identity_sha256": result.operation_identity_sha256,
            "initial_page_identity_sha256": page.page_identity_sha256,
            "artifact_descriptor_sha256": descriptor.external_descriptor_sha256,
        })
        state = _ExactReadStateV2(
            owner_thread_id=get_ident(),
            f17_session=f17_session,
            monthly_index_session=index_session,
            combined_session=bound_session,
            result=result,
            request=request,
            page=page,
            monthly_connection_closed=index_session.closed,
        )
        return DailyMarketTechnicalOfficialDispositionRevenueExactReadV2(
            f17_query=f17_query,
            monthly_reference=reference,
            artifact_descriptor=descriptor,
            query=query,
            identity=pair_identity,
            state=state,
            issuer=_ISSUER,
        )
    except BaseException as exc:
        cleanup_errors: list[BaseException] = []
        if index_session is not None:
            try:
                index_session.close()
                if not index_session.closed:
                    _fail("monthly_reader_connection_not_closed_during_cleanup")
            except BaseException as cleanup_error:
                cleanup_errors.append(cleanup_error)
        if cleanup_errors:
            raise DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error(
                "operation_failed_and_monthly_cleanup_failed"
            ) from BaseExceptionGroup(
                "primary V2 source failure and cleanup failure", [exc, *cleanup_errors]
            )
        if isinstance(exc, DailyMarketMonthlyRevenueYoyIndexCancelled):
            raise DailyMarketTechnicalOfficialDispositionRevenueSourceV2Cancelled("monthly_source_cancelled") from exc
        if isinstance(exc, DailyMarketTechnicalOfficialDispositionQueryReaderV1Error):
            if "cancelled" in str(getattr(exc, "code", "")):
                raise DailyMarketTechnicalOfficialDispositionRevenueSourceV2Cancelled("f17_source_cancelled") from exc
        raise


__all__ = [
    "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_RECIPE_SCHEMA_V2",
    "DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_REVENUE_SOURCE_SCHEMA_V2",
    "DailyMarketTechnicalOfficialDispositionRevenueExactReadV2",
    "DailyMarketTechnicalOfficialDispositionRevenueSavedRecipeV2",
    "DailyMarketTechnicalOfficialDispositionRevenueSourceV2Cancelled",
    "DailyMarketTechnicalOfficialDispositionRevenueSourceV2Error",
    "open_daily_market_technical_official_disposition_revenue_bundle_source_v2",
    "reopen_daily_market_technical_official_disposition_revenue_from_recipe_v2",
]
