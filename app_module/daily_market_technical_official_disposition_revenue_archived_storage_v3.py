"""準備月營收 V3 封存研究資料夾的固定子路徑。"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any, NoReturn, Sequence

from data_module.daily_monthly_revenue_cohort_binding import (
    DAILY_MONTHLY_REVENUE_COHORT_BINDING_MAX_BYTES,
    DAILY_MONTHLY_REVENUE_COHORT_BINDING_SCHEMA,
    DailyMonthlyRevenueCohortBindingError,
    _parse_acceptance,
    _require_sha256 as _cohort_require_sha256,
)
from data_module.daily_monthly_revenue_cohort import (
    DAILY_MONTHLY_REVENUE_COHORT_ENVELOPE_BYTES,
    DailyMonthlyRevenueCohortError,
    DailyMonthlyRevenueCohortPin,
)
from data_module.daily_monthly_revenue_series import DailyMonthlyRevenueSeriesTrustV1
from data_module.daily_monthly_revenue_series_binding import (
    DAILY_MONTHLY_REVENUE_SERIES_BINDING_MAX_BYTES,
    DAILY_MONTHLY_REVENUE_SERIES_BINDING_SCHEMA_V1,
    DailyMonthlyRevenueSeriesBindingError,
    _checked_directory_path as _series_checked_directory_path,
    _decode_canonical_object as _series_decode_canonical_object,
    _parse_trust as _series_parse_trust,
    _read_regular_file as _read_series_regular_file,
    _validate_data_roots as _series_validate_data_roots,
)
from data_module.daily_source_snapshot import DailySourceUseAcceptance
from data_module.fundamental_read_snapshot import (
    FundamentalReadSnapshotError,
    _paths_overlap,
    _reject_reparse_components,
)


_DEFAULT_DATA_ROOT = "F:/Min/Python/Project/FA_Data"
_CHILD_NAMES = (
    "monthly-references.v3",
    "raw-archives.v2",
    "archive-references.v4",
)
_MAX_ROOTS = 128
_SERIES_TRUST_SCHEMA_V1 = "daily-monthly-revenue-series-trust.v1"
_SERIES_BINDING_FIELDS = {"schema_version", "trust", "catalog_root", "pointer_path"}
_COHORT_BINDING_FIELDS = {
    "schema_version",
    "cohort_pin_root",
    "cohort_sha256",
    "markets",
}
_COHORT_MARKET_FIELDS = {"market", "snapshot_root", "trusted_acceptance"}
_MARKET_ORDER = ("twse", "tpex")
_SHA256_HEX = frozenset("0123456789abcdef")


class ArchivedRevenueResearchStorageV3Error(ValueError):
    """封存研究資料夾或其保護範圍不符合固定 layout。"""


def _fail(reason: str) -> NoReturn:
    raise ArchivedRevenueResearchStorageV3Error(f"revenue_archive_storage_v3_{reason}")


def _canonical_absolute_path(value: object, label: str, *, allow_missing: bool) -> Path:
    if value is None:
        _fail(f"{label}_missing")
    if isinstance(value, Path):
        raw = value
    elif type(value) is str:
        if not value or not value.strip():
            _fail(f"{label}_empty")
        raw = Path(value)
        if str(raw) != value:
            _fail(f"{label}_not_canonical")
    else:
        _fail(f"{label}_type_invalid")
    if not raw.is_absolute() or ".." in raw.parts or "\x00" in str(raw):
        _fail(f"{label}_must_be_absolute_normal")
    canonical = Path(os.path.abspath(str(raw)))
    if raw != canonical:
        _fail(f"{label}_not_canonical")
    try:
        _reject_reparse_components(canonical, allow_missing=allow_missing)
    except FundamentalReadSnapshotError as exc:
        raise ArchivedRevenueResearchStorageV3Error(
            f"revenue_archive_storage_v3_{label}_reparse_or_component_invalid"
        ) from exc
    except OSError as exc:
        raise ArchivedRevenueResearchStorageV3Error(
            f"revenue_archive_storage_v3_{label}_unavailable"
        ) from exc
    return canonical


def _validate_directory(path: Path, label: str, *, required: bool) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        if required:
            _fail(f"{label}_missing")
        return False
    except OSError as exc:
        raise ArchivedRevenueResearchStorageV3Error(
            f"revenue_archive_storage_v3_{label}_unavailable"
        ) from exc
    if not stat.S_ISDIR(metadata.st_mode):
        _fail(f"{label}_must_be_directory")
    return True


def _normalize_root_sequence(value: object, label: str, *, allow_empty: bool) -> tuple[Path, ...]:
    if type(value) is tuple:
        candidates: Sequence[object] = value
    elif type(value) is list:
        candidates = value
    else:
        _fail(f"{label}_must_be_bounded_path_sequence")
    if len(candidates) > _MAX_ROOTS or (not allow_empty and not candidates):
        _fail(f"{label}_count_invalid")
    roots: list[Path] = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Path):
            _fail(f"{label}_{index}_must_be_path")
        roots.append(_canonical_absolute_path(candidate, f"{label}_{index}", allow_missing=True))
    return tuple(roots)


def _configured_protected_roots() -> tuple[Path, ...]:
    data_value = os.environ.get("DATA_ROOT", _DEFAULT_DATA_ROOT)
    data_root = _canonical_absolute_path(data_value, "configured_data_root", allow_missing=True)
    output_value = os.environ.get("OUTPUT_ROOT")
    output_root = (
        _canonical_absolute_path(output_value, "configured_output_root", allow_missing=True)
        if output_value is not None
        else data_root / "output"
    )
    values: list[Path] = [data_root, output_root]
    for name in ("PERSONAL_DATA_ROOT", "PERSONAL_STORE_ROOT"):
        value = os.environ.get(name)
        if value:
            values.append(_canonical_absolute_path(value, f"configured_{name.lower()}", allow_missing=True))
    if len(values) > _MAX_ROOTS:
        _fail("configured_root_count_invalid")
    return tuple(values)


@dataclass(frozen=True, slots=True)
class ArchivedRevenueResearchStorageV3:
    """三個互斥的 V3 reference／raw archive／V4 artifact 子目錄。"""

    root: Path
    monthly_reference_artifact_root: Path
    raw_archive_parent: Path
    archived_reference_artifact_root: Path

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, Path)
            for value in (
                self.root,
                self.monthly_reference_artifact_root,
                self.raw_archive_parent,
                self.archived_reference_artifact_root,
            )
        ):
            _fail("layout_path_type_invalid")
        root = Path(os.path.abspath(str(self.root)))
        if (
            not self.root.is_absolute()
            or ".." in self.root.parts
            or self.root != root
            or self.monthly_reference_artifact_root != root / _CHILD_NAMES[0]
            or self.raw_archive_parent != root / _CHILD_NAMES[1]
            or self.archived_reference_artifact_root != root / _CHILD_NAMES[2]
        ):
            _fail("layout_not_canonical_fixed_children")


def prepare_archived_revenue_research_storage_v3(
    storage_root: Path | str,
    *,
    protected_roots: Sequence[Path],
    source_roots: Sequence[Path] = (),
    operation_root_parent: Path | str | None = None,
) -> ArchivedRevenueResearchStorageV3:
    """在既有研究資料夾安全重用或建立三個固定封存子目錄。"""

    root = _canonical_absolute_path(storage_root, "storage_root", allow_missing=False)
    if not _validate_directory(root, "storage_root", required=True):
        _fail("storage_root_missing")

    protected = _normalize_root_sequence(protected_roots, "protected_root", allow_empty=False)
    sources = _normalize_root_sequence(source_roots, "source_root", allow_empty=True)
    configured = _configured_protected_roots()
    operation_parent: Path | None = None
    if operation_root_parent is not None:
        operation_parent = _canonical_absolute_path(
            operation_root_parent, "operation_root_parent", allow_missing=False
        )
        if not _validate_directory(operation_parent, "operation_root_parent", required=True):
            _fail("operation_root_parent_missing")

    all_protected = (*protected, *configured)
    all_sources = sources
    for protected_root in all_protected:
        if _paths_overlap(root, protected_root):
            _fail("storage_root_overlaps_protected_root")
    for source_root in all_sources:
        if _paths_overlap(root, source_root):
            _fail("storage_root_overlaps_source_root")
    if operation_parent is not None:
        if _paths_overlap(root, operation_parent):
            _fail("storage_root_overlaps_operation_root_parent")
        if any(_paths_overlap(operation_parent, candidate) for candidate in (*all_protected, *all_sources)):
            _fail("operation_root_parent_overlaps_source_or_protected_root")

    children = tuple(root / name for name in _CHILD_NAMES)
    for index, child in enumerate(children):
        child = _canonical_absolute_path(child, f"child_{index}", allow_missing=True)
        exists = _validate_directory(child, f"child_{index}", required=False)
        if not exists and child.exists():
            _fail(f"child_{index}_collision")
        if any(_paths_overlap(child, candidate) for candidate in (*all_protected, *all_sources)):
            _fail(f"child_{index}_overlaps_source_or_protected_root")
        if operation_parent is not None and _paths_overlap(child, operation_parent):
            _fail(f"child_{index}_overlaps_operation_root_parent")
        if any(_paths_overlap(child, other) for other in children if other != child):
            _fail("fixed_children_alias_or_overlap")

    # 所有 caller root、正式 root、layout、collision 與 reparse 檢查均先於第一個 mkdir。
    for index, child in enumerate(children):
        try:
            child.mkdir(exist_ok=True)
        except OSError as exc:
            raise ArchivedRevenueResearchStorageV3Error(
                f"revenue_archive_storage_v3_child_{index}_create_failed"
            ) from exc
        _canonical_absolute_path(child, f"created_child_{index}", allow_missing=False)
        _validate_directory(child, f"created_child_{index}", required=True)

    return ArchivedRevenueResearchStorageV3(
        root=root,
        monthly_reference_artifact_root=children[0],
        raw_archive_parent=children[1],
        archived_reference_artifact_root=children[2],
    )


def read_archived_revenue_binding_source_roots_v3(
    binding_path: Path | str,
    *,
    expected_binding_sha256: str,
) -> tuple[Path, ...]:
    """只讀外部 hash 固定的 binding 與 exact cohort pin metadata。

    不讀 mutable pointer/catalog 或每日快照檔；回傳值僅供保存目錄重疊守衛，
    不授予來源接受、品質或 PIT 資格。
    """

    expected = _require_lower_sha256(expected_binding_sha256)
    path = _canonical_absolute_path(
        binding_path, "binding_path", allow_missing=False
    )
    try:
        resolved_binding_path = path.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ArchivedRevenueResearchStorageV3Error(
            "revenue_archive_storage_v3_binding_path_resolve_failed"
        ) from exc
    if path != resolved_binding_path:
        _fail("binding_path_not_canonical")
    try:
        max_bytes = max(
            DAILY_MONTHLY_REVENUE_COHORT_BINDING_MAX_BYTES,
            DAILY_MONTHLY_REVENUE_SERIES_BINDING_MAX_BYTES,
        )
        raw, _ = _read_series_regular_file(
            path,
            max_bytes=max_bytes,
            label="archived_binding_metadata",
        )
    except (DailyMonthlyRevenueSeriesBindingError, OSError, TypeError, ValueError) as exc:
        if isinstance(exc, ArchivedRevenueResearchStorageV3Error):
            raise
        raise ArchivedRevenueResearchStorageV3Error(
            f"revenue_archive_storage_v3_binding_file_rejected:{exc}"
        ) from exc
    if hashlib.sha256(raw).hexdigest() != expected:
        _fail("binding_external_hash_mismatch")

    try:
        document = _series_decode_canonical_object(
            raw, "archived_binding_metadata", max_bytes
        )
    except DailyMonthlyRevenueSeriesBindingError as exc:
        raise ArchivedRevenueResearchStorageV3Error(
            f"revenue_archive_storage_v3_binding_json_rejected:{exc}"
        ) from exc
    schema = document.get("schema_version")
    try:
        if schema == DAILY_MONTHLY_REVENUE_COHORT_BINDING_SCHEMA:
            roots = _cohort_binding_roots(document)
        elif schema == DAILY_MONTHLY_REVENUE_SERIES_BINDING_SCHEMA_V1:
            roots = _series_binding_roots(document)
        else:
            _fail("binding_schema_unsupported")
    except ArchivedRevenueResearchStorageV3Error:
        raise
    except (
        DailyMonthlyRevenueCohortBindingError,
        DailyMonthlyRevenueSeriesBindingError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise ArchivedRevenueResearchStorageV3Error(
            f"revenue_archive_storage_v3_binding_metadata_invalid:{exc}"
        ) from exc

    return _deduplicate_source_roots(roots)


def _cohort_binding_roots(document: dict[str, Any]) -> tuple[Path, ...]:
    if set(document) != _COHORT_BINDING_FIELDS:
        _fail("cohort_binding_fields_invalid")
    pin_hash = _cohort_require_sha256(document.get("cohort_sha256"), "cohort_sha256")
    pin_root = _binding_source_root(document.get("cohort_pin_root"), "cohort_pin_root")
    raw_markets = document.get("markets")
    if type(raw_markets) is not list or not 1 <= len(raw_markets) <= len(_MARKET_ORDER):
        _fail("cohort_binding_required_markets_invalid")

    market_roots: list[Path] = []
    markets: list[str] = []
    acceptance_by_market: dict[str, DailySourceUseAcceptance] = {}
    for index, raw_market in enumerate(raw_markets):
        if type(raw_market) is not dict or set(raw_market) != _COHORT_MARKET_FIELDS:
            _fail(f"cohort_binding_market_{index}_fields_invalid")
        market = raw_market.get("market")
        if type(market) is not str or market not in _MARKET_ORDER or market in markets:
            _fail(f"cohort_binding_market_{index}_identity_invalid")
        markets.append(market)
        market_root = _binding_source_root(
            raw_market.get("snapshot_root"), f"snapshot_root_{market}"
        )
        acceptance = _parse_acceptance(
            raw_market.get("trusted_acceptance"), expected_market=market
        )
        acceptance_by_market[market] = acceptance
        market_roots.append(market_root)
    if tuple(markets) != tuple(item for item in _MARKET_ORDER if item in markets):
        _fail("cohort_binding_required_markets_order_invalid")
    pin = _read_exact_cohort_pin(pin_root, pin_hash)
    if pin.required_markets != tuple(markets):
        _fail("cohort_binding_required_markets_do_not_match_pin")
    for market in pin.required_markets:
        market_pin = pin.for_market(market)
        acceptance = acceptance_by_market[market]
        if (
            market_pin.scope != acceptance.scope
            or market_pin.acceptance_id != acceptance.acceptance_id
            or market_pin.acceptance_sha256
            != hashlib.sha256(_canonical_acceptance_bytes(acceptance)).hexdigest()
        ):
            _fail(f"cohort_binding_acceptance_does_not_match_pin:{market}")
    return (pin_root, *market_roots)


def _read_exact_cohort_pin(
    pin_root: Path,
    expected_cohort_sha256: str,
) -> DailyMonthlyRevenueCohortPin:
    """讀取綁定明示的 immutable pin manifest，不開啟任何每日 snapshot 檔。"""

    pin_path = pin_root / f"{expected_cohort_sha256}.json"
    try:
        raw, _ = _read_series_regular_file(
            pin_path,
            max_bytes=DAILY_MONTHLY_REVENUE_COHORT_ENVELOPE_BYTES,
            label="cohort_pin_metadata",
        )
        pin = DailyMonthlyRevenueCohortPin.from_json(raw)
    except (
        DailyMonthlyRevenueCohortError,
        DailyMonthlyRevenueSeriesBindingError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise ArchivedRevenueResearchStorageV3Error(
            f"revenue_archive_storage_v3_cohort_pin_metadata_rejected:{exc}"
        ) from exc
    if pin.cohort_sha256 != expected_cohort_sha256:
        _fail("cohort_pin_metadata_hash_mismatch")
    if pin.to_json().encode("utf-8") != raw:
        _fail("cohort_pin_metadata_not_canonical")
    return pin


def _canonical_acceptance_bytes(acceptance: DailySourceUseAcceptance) -> bytes:
    value = acceptance.to_dict()
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ArchivedRevenueResearchStorageV3Error(
            "revenue_archive_storage_v3_cohort_binding_acceptance_serialization_failed"
        ) from exc


def _series_binding_roots(document: dict[str, Any]) -> tuple[Path, ...]:
    if set(document) != _SERIES_BINDING_FIELDS:
        _fail("series_binding_fields_invalid")
    trust_value = document.get("trust")
    if type(trust_value) is not dict:
        _fail("series_binding_trust_invalid")
    if trust_value.get("schema_version") != _SERIES_TRUST_SCHEMA_V1:
        _fail("series_binding_trust_schema_unsupported")
    trust = _series_parse_trust(trust_value)
    if type(trust) is not DailyMonthlyRevenueSeriesTrustV1:
        _fail("series_binding_trust_type_invalid")

    catalog_root = _series_checked_directory_path(
        document.get("catalog_root"), "catalog_root", must_exist=True
    )
    raw_pointer_path = document.get("pointer_path")
    if type(raw_pointer_path) is not str or not raw_pointer_path.strip():
        _fail("series_binding_pointer_metadata_invalid")
    pointer_path = Path(raw_pointer_path)
    if (
        not pointer_path.is_absolute()
        or ".." in pointer_path.parts
        or "\x00" in raw_pointer_path
        or str(pointer_path) != raw_pointer_path
    ):
        _fail("series_binding_pointer_metadata_invalid")
    if (
        str(catalog_root) != document.get("catalog_root")
        or str(pointer_path) != document.get("pointer_path")
        or pointer_path.suffix.lower() != ".json"
        or pointer_path.parent != catalog_root
    ):
        _fail("series_binding_pointer_metadata_invalid")
    _series_validate_data_roots(trust, catalog_root)
    return (
        Path(trust.cohort_pin_root),
        catalog_root,
        *(Path(source.snapshot_root) for source in trust.market_sources),
    )


def _binding_source_root(value: object, label: str) -> Path:
    root = _canonical_absolute_path(value, label, allow_missing=True)
    if type(value) is not str or str(root) != value:
        _fail(f"{label}_not_canonical_absolute_path")
    _validate_directory(root, label, required=False)
    return root


def _deduplicate_source_roots(roots: tuple[Path, ...]) -> tuple[Path, ...]:
    if not roots or len(roots) > _MAX_ROOTS:
        _fail("binding_source_root_count_invalid")
    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return tuple(unique)


def _require_lower_sha256(value: object) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in _SHA256_HEX for character in value)
    ):
        _fail("binding_expected_sha256_invalid")
    return value


__all__ = (
    "ArchivedRevenueResearchStorageV3",
    "ArchivedRevenueResearchStorageV3Error",
    "prepare_archived_revenue_research_storage_v3",
    "read_archived_revenue_binding_source_roots_v3",
)
