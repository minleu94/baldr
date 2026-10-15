"""由穩定外部 binding 載入每次呼叫更新的月營收 cohort catalog。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, cast

from data_module.daily_monthly_revenue_cohort import (
    DAILY_MONTHLY_REVENUE_COHORT_ENVELOPE_BYTES,
    DailyMonthlyRevenueCohortError,
    DailyMonthlyRevenueCohortPin,
    DailyMonthlyRevenueCohortReader,
)
from data_module.daily_monthly_revenue_cohort_binding import (
    DailyMonthlyRevenueCohortBindingError,
    _parse_acceptance,
    _require_absolute_nonsymlink_path,
)
from data_module.daily_monthly_revenue_series import (
    DAILY_MONTHLY_REVENUE_SERIES_MAX_CANDIDATES,
    DailyMonthlyRevenueSeriesError,
    DailyMonthlyRevenueSeriesMarketTrustV1,
    DailyMonthlyRevenueSeriesSelectionV1,
    DailyMonthlyRevenueSeriesTrustV1,
    select_daily_monthly_revenue_series_v1,
)
from data_module.daily_source_snapshot import DailySourceSnapshotError


DAILY_MONTHLY_REVENUE_SERIES_BINDING_SCHEMA_V1 = (
    "daily-monthly-revenue-series-binding.v1"
)
DAILY_MONTHLY_REVENUE_SERIES_CATALOG_SCHEMA_V1 = (
    "daily-monthly-revenue-series-catalog.v1"
)
DAILY_MONTHLY_REVENUE_SERIES_CATALOG_POINTER_SCHEMA_V1 = (
    "daily-monthly-revenue-series-catalog-pointer.v1"
)
DAILY_MONTHLY_REVENUE_SERIES_BINDING_MAX_BYTES = 64 * 1024
DAILY_MONTHLY_REVENUE_SERIES_POINTER_MAX_BYTES = 4 * 1024
DAILY_MONTHLY_REVENUE_SERIES_CATALOG_MAX_BYTES = 64 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PERIOD_RE = re.compile(r"^(\d{4})-(\d{2})$")
_MARKETS = ("twse", "tpex")
_FILE_ATTRIBUTE_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
_BOUND_SELECTION_ISSUER = object()

_BINDING_FIELDS = {"schema_version", "trust", "catalog_root", "pointer_path"}
_TRUST_FIELDS = {
    "schema_version",
    "cohort_pin_root",
    "required_markets",
    "market_sources",
    "configuration_sha256",
}
_MARKET_FIELDS = {"market", "snapshot_root", "trusted_acceptance"}
_POINTER_FIELDS = {"schema_version", "catalog_sha256"}
_CATALOG_FIELDS = {"schema_version", "report_period", "cohort_sha256s"}


class DailyMonthlyRevenueSeriesBindingError(ValueError):
    """每日月營收 binding 或其指向的 bounded catalog 未通過契約。"""

    def __init__(self, code: str, *, diagnostics: tuple[str, ...] = ()) -> None:
        self.code = code
        self.diagnostics = tuple(diagnostics[:DAILY_MONTHLY_REVENUE_SERIES_MAX_CANDIDATES])
        super().__init__(code)


@dataclass(frozen=True, slots=True, init=False)
class DailyMonthlyRevenueSeriesBoundSelectionV1:
    """單次 invocation 的選擇結果；後續 pointer 更新不會改寫此物件。"""

    selection: DailyMonthlyRevenueSeriesSelectionV1
    binding_sha256: str
    pointer_sha256: str
    catalog_sha256: str
    report_period: str
    cutoff_at: datetime
    candidate_diagnostics: tuple[str, ...]
    _anchor: tuple[object, ...] = field(init=False, repr=False, compare=False)

    def __init__(
        self,
        *,
        selection: DailyMonthlyRevenueSeriesSelectionV1,
        binding_sha256: str,
        pointer_sha256: str,
        catalog_sha256: str,
        report_period: str,
        cutoff_at: datetime,
        candidate_diagnostics: tuple[str, ...],
        _issuer: object,
    ) -> None:
        if _issuer is not _BOUND_SELECTION_ISSUER:
            raise DailyMonthlyRevenueSeriesBindingError(
                "series_bound_selection_not_issued_by_loader"
            )
        if type(selection) is not DailyMonthlyRevenueSeriesSelectionV1:
            raise DailyMonthlyRevenueSeriesBindingError(
                "series_bound_selection_type_invalid"
            )
        _require_sha256(binding_sha256, "binding_sha256")
        _require_sha256(pointer_sha256, "pointer_sha256")
        _require_sha256(catalog_sha256, "catalog_sha256")
        _validate_period(report_period)
        cutoff = _require_aware_datetime(cutoff_at, "cutoff_at")
        if selection.report_period != report_period or selection.cutoff_at != cutoff:
            raise DailyMonthlyRevenueSeriesBindingError(
                "series_bound_selection_scope_mismatch"
            )
        diagnostics = _require_diagnostics(candidate_diagnostics)
        object.__setattr__(self, "selection", selection)
        object.__setattr__(self, "binding_sha256", binding_sha256)
        object.__setattr__(self, "pointer_sha256", pointer_sha256)
        object.__setattr__(self, "catalog_sha256", catalog_sha256)
        object.__setattr__(self, "report_period", report_period)
        object.__setattr__(self, "cutoff_at", cutoff)
        object.__setattr__(self, "candidate_diagnostics", diagnostics)
        object.__setattr__(
            self,
            "_anchor",
            (
                selection,
                binding_sha256,
                pointer_sha256,
                catalog_sha256,
                report_period,
                cutoff,
                diagnostics,
            ),
        )

    @property
    def pin(self) -> DailyMonthlyRevenueCohortPin:
        """回傳本次選定的完整 immutable cohort pin。"""

        return self.selection.pin

    @property
    def reader(self) -> DailyMonthlyRevenueCohortReader:
        """回傳本次固定的全市場 source reader。"""

        return self.selection.reader

    @property
    def source_qualification(self) -> str:
        """Catalog 只選版本，不替來源授予正式資格。"""

        return "not_granted"

    @property
    def historical_pit_eligible(self) -> bool:
        """現行每日 cohort 不構成歷史 PIT 資格。"""

        return False

    @property
    def formal_pit_eligible(self) -> bool:
        """現行每日 cohort 不構成正式 PIT 資格。"""

        return False

    def verify_integrity(self) -> DailyMonthlyRevenueCohortPin:
        """檢查發行時身份並重驗已選批次，不追讀 mutable pointer。"""

        current = (
            self.selection,
            self.binding_sha256,
            self.pointer_sha256,
            self.catalog_sha256,
            self.report_period,
            self.cutoff_at,
            self.candidate_diagnostics,
        )
        if any(
            left is not right if index == 0 else left != right
            for index, (left, right) in enumerate(zip(current, self._anchor))
        ):
            raise DailyMonthlyRevenueSeriesBindingError(
                "series_bound_selection_anchor_mismatch"
            )
        try:
            return self.selection.verify_integrity()
        except (DailyMonthlyRevenueSeriesError, DailySourceSnapshotError) as exc:
            raise DailyMonthlyRevenueSeriesBindingError(
                f"series_bound_selection_source_recheck_failed:{exc}"
            ) from exc


def serialize_daily_monthly_revenue_series_binding_v1(
    *,
    trust: DailyMonthlyRevenueSeriesTrustV1,
    catalog_root: Path | str,
    pointer_path: Path | str,
) -> bytes:
    """序列化外部固定的 trust、catalog root 與唯一 mutable pointer 路徑。"""

    if type(trust) is not DailyMonthlyRevenueSeriesTrustV1:
        raise DailyMonthlyRevenueSeriesBindingError("series_binding_trust_type_invalid")
    catalog = _checked_directory_path(catalog_root, "catalog_root", must_exist=False)
    pointer = _resolved(_checked_absolute_path(pointer_path, "pointer_path"))
    if pointer.suffix.lower() != ".json" or _resolved(pointer.parent) != _resolved(catalog):
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_pointer_must_be_json_child_of_catalog_root"
        )
    _validate_data_roots(trust, catalog)
    try:
        trust_document = trust.to_dict()
        trust_core = {
            key: value
            for key, value in trust_document.items()
            if key != "configuration_sha256"
        }
        trust_digest = hashlib.sha256(_canonical_json_bytes(trust_core)).hexdigest()
        if trust_digest != trust.configuration_sha256:
            raise DailyMonthlyRevenueSeriesBindingError(
                "series_binding_trust_internal_hash_mismatch"
            )
    except (DailyMonthlyRevenueSeriesError, TypeError, ValueError) as exc:
        if isinstance(exc, DailyMonthlyRevenueSeriesBindingError):
            raise
        raise DailyMonthlyRevenueSeriesBindingError(
            f"series_binding_trust_invalid:{exc}"
        ) from exc
    payload = _canonical_json_bytes(
        {
            "schema_version": DAILY_MONTHLY_REVENUE_SERIES_BINDING_SCHEMA_V1,
            "trust": trust_document,
            "catalog_root": str(catalog),
            "pointer_path": str(pointer),
        }
    )
    if len(payload) > DAILY_MONTHLY_REVENUE_SERIES_BINDING_MAX_BYTES:
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_binding_exceeds_size_limit"
        )
    return payload


def serialize_daily_monthly_revenue_series_catalog_v1(
    *, report_period: str, cohort_sha256s: Sequence[str]
) -> bytes:
    """序列化一個明示期間、有限且排序唯一的 pin hash catalog。"""

    _validate_period(report_period)
    hashes = _validate_catalog_hashes(cohort_sha256s, require_sorted=False)
    payload = _canonical_json_bytes(
        {
            "schema_version": DAILY_MONTHLY_REVENUE_SERIES_CATALOG_SCHEMA_V1,
            "report_period": report_period,
            "cohort_sha256s": list(hashes),
        }
    )
    if len(payload) > DAILY_MONTHLY_REVENUE_SERIES_CATALOG_MAX_BYTES:
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_catalog_exceeds_size_limit"
        )
    return payload


def serialize_daily_monthly_revenue_series_catalog_pointer_v1(
    *, catalog_sha256: str
) -> bytes:
    """序列化只指向 immutable catalog 原始 bytes SHA 的 mutable pointer。"""

    digest = _require_sha256(catalog_sha256, "catalog_sha256")
    payload = _canonical_json_bytes(
        {
            "schema_version": DAILY_MONTHLY_REVENUE_SERIES_CATALOG_POINTER_SCHEMA_V1,
            "catalog_sha256": digest,
        }
    )
    if len(payload) > DAILY_MONTHLY_REVENUE_SERIES_POINTER_MAX_BYTES:
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_pointer_exceeds_size_limit"
        )
    return payload


def write_daily_monthly_revenue_series_catalog_create_only(
    catalog_root: Path | str,
    *,
    report_period: str,
    cohort_sha256s: Sequence[str],
) -> tuple[Path, str]:
    """建立測試或候選用 create-only catalog；不更新正式 pointer。"""

    root = _checked_directory_path(catalog_root, "catalog_root", must_exist=False)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_catalog_root_create_failed"
        ) from exc
    root = _checked_directory_path(root, "catalog_root", must_exist=True)
    payload = serialize_daily_monthly_revenue_series_catalog_v1(
        report_period=report_period, cohort_sha256s=cohort_sha256s
    )
    digest = hashlib.sha256(payload).hexdigest()
    target = root / f"{digest}.json"
    _write_create_only(target, payload, DAILY_MONTHLY_REVENUE_SERIES_CATALOG_MAX_BYTES)
    return target, digest


def write_daily_monthly_revenue_series_pointer_create_only(
    pointer_path: Path | str, *, catalog_sha256: str
) -> Path:
    """建立測試或首次候選 pointer；不覆寫既有 mutable pointer。"""

    pointer = _checked_absolute_path(pointer_path, "pointer_path")
    if pointer.suffix.lower() != ".json":
        raise DailyMonthlyRevenueSeriesBindingError("series_pointer_extension_invalid")
    payload = serialize_daily_monthly_revenue_series_catalog_pointer_v1(
        catalog_sha256=catalog_sha256
    )
    _write_create_only(pointer, payload, DAILY_MONTHLY_REVENUE_SERIES_POINTER_MAX_BYTES)
    return pointer


def read_daily_monthly_revenue_series_binding_v1(
    path: Path | str,
    *,
    expected_binding_sha256: str,
    cutoff_at: datetime,
    report_period: str | None = None,
    forbidden_roots: Sequence[Path] = (),
) -> DailyMonthlyRevenueSeriesBoundSelectionV1:
    """每次讀取 mutable pointer，沿 exact catalog/pins 選一次截止可用版本。"""

    expected_binding = _require_sha256(
        expected_binding_sha256, "expected_binding_sha256"
    )
    cutoff = _require_aware_datetime(cutoff_at, "cutoff_at")
    if report_period is not None:
        _validate_period(report_period)
    forbidden = _normalize_forbidden_roots(forbidden_roots)
    binding_path = _checked_absolute_path(path, "binding_path")
    if binding_path != _resolved(binding_path):
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_binding_path_not_canonical"
        )
    _reject_overlaps(binding_path, forbidden, "binding_path")
    raw_binding, binding_signature = _read_regular_file(
        binding_path,
        max_bytes=DAILY_MONTHLY_REVENUE_SERIES_BINDING_MAX_BYTES,
        label="binding",
    )
    if hashlib.sha256(raw_binding).hexdigest() != expected_binding:
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_binding_external_hash_mismatch"
        )
    binding = _decode_canonical_object(
        raw_binding, "binding", DAILY_MONTHLY_REVENUE_SERIES_BINDING_MAX_BYTES
    )
    if set(binding) != _BINDING_FIELDS:
        raise DailyMonthlyRevenueSeriesBindingError("series_binding_fields_invalid")
    if binding.get("schema_version") != DAILY_MONTHLY_REVENUE_SERIES_BINDING_SCHEMA_V1:
        raise DailyMonthlyRevenueSeriesBindingError("series_binding_schema_unsupported")

    trust = _parse_trust(binding.get("trust"))
    catalog_root = _checked_directory_path(
        binding.get("catalog_root"), "catalog_root", must_exist=True
    )
    pointer_path = _checked_absolute_path(binding.get("pointer_path"), "pointer_path")
    if str(catalog_root) != binding.get("catalog_root"):
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_catalog_root_not_canonical"
        )
    if str(pointer_path) != binding.get("pointer_path"):
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_pointer_path_not_canonical"
        )
    if pointer_path != _resolved(pointer_path):
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_pointer_path_alias_rejected"
        )
    if pointer_path.suffix.lower() != ".json" or _resolved(pointer_path.parent) != catalog_root:
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_pointer_must_be_json_child_of_catalog_root"
        )
    _validate_data_roots(trust, catalog_root)
    _reject_all_configured_paths(binding_path, pointer_path, catalog_root, trust, forbidden)

    raw_pointer, pointer_signature = _read_regular_file(
        pointer_path,
        max_bytes=DAILY_MONTHLY_REVENUE_SERIES_POINTER_MAX_BYTES,
        label="pointer",
    )
    pointer = _decode_canonical_object(
        raw_pointer, "pointer", DAILY_MONTHLY_REVENUE_SERIES_POINTER_MAX_BYTES
    )
    if set(pointer) != _POINTER_FIELDS:
        raise DailyMonthlyRevenueSeriesBindingError("series_pointer_fields_invalid")
    if pointer.get("schema_version") != DAILY_MONTHLY_REVENUE_SERIES_CATALOG_POINTER_SCHEMA_V1:
        raise DailyMonthlyRevenueSeriesBindingError("series_pointer_schema_unsupported")
    catalog_digest = _require_sha256(pointer.get("catalog_sha256"), "catalog_sha256")
    catalog_path = catalog_root / f"{catalog_digest}.json"
    _reject_overlaps(catalog_path, forbidden, "catalog_path")
    raw_catalog, catalog_signature = _read_regular_file(
        catalog_path,
        max_bytes=DAILY_MONTHLY_REVENUE_SERIES_CATALOG_MAX_BYTES,
        label="catalog",
        expected_sha256=catalog_digest,
    )
    catalog = _decode_canonical_object(
        raw_catalog, "catalog", DAILY_MONTHLY_REVENUE_SERIES_CATALOG_MAX_BYTES
    )
    if set(catalog) != _CATALOG_FIELDS:
        raise DailyMonthlyRevenueSeriesBindingError("series_catalog_fields_invalid")
    if catalog.get("schema_version") != DAILY_MONTHLY_REVENUE_SERIES_CATALOG_SCHEMA_V1:
        raise DailyMonthlyRevenueSeriesBindingError("series_catalog_schema_unsupported")
    selected_period = _require_text(catalog.get("report_period"), "report_period")
    _validate_period(selected_period)
    if report_period is not None and selected_period != report_period:
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_catalog_report_period_mismatch"
        )
    catalog_hashes = _validate_catalog_hashes(catalog.get("cohort_sha256s"))

    candidates: list[DailyMonthlyRevenueCohortPin] = []
    diagnostics: list[str] = []
    pin_root = _checked_directory_path(
        trust.cohort_pin_root, "cohort_pin_root", must_exist=True
    )
    for cohort_hash in catalog_hashes:
        pin_path = pin_root / f"{cohort_hash}.json"
        try:
            _reject_overlaps(pin_path, forbidden, f"cohort_pin:{cohort_hash}")
            raw_pin, _ = _read_regular_file(
                pin_path,
                max_bytes=DAILY_MONTHLY_REVENUE_COHORT_ENVELOPE_BYTES,
                label=f"cohort_pin:{cohort_hash}",
            )
            pin = DailyMonthlyRevenueCohortPin.from_json(raw_pin)
            if pin.cohort_sha256 != cohort_hash:
                raise DailyMonthlyRevenueSeriesBindingError(
                    "series_catalog_pin_hash_mismatch"
                )
            if raw_pin != pin.to_json().encode("utf-8"):
                raise DailyMonthlyRevenueSeriesBindingError(
                    "series_catalog_pin_not_canonical"
                )
            candidates.append(pin)
        except (
            DailyMonthlyRevenueCohortError,
            DailyMonthlyRevenueSeriesBindingError,
            OSError,
            TypeError,
            UnicodeError,
            ValueError,
        ) as exc:
            diagnostics.append(f"{cohort_hash}:{_safe_reason(exc)}")

    if not candidates:
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_catalog_has_no_readable_exact_pin",
            diagnostics=tuple(sorted(diagnostics)),
        )
    try:
        selection = select_daily_monthly_revenue_series_v1(
            trust=trust,
            expected_trust_configuration_sha256=trust.configuration_sha256,
            report_period=selected_period,
            candidate_pins=tuple(candidates),
            cutoff_at=cutoff,
        )
    except DailyMonthlyRevenueSeriesError as exc:
        merged = tuple(sorted(set(diagnostics).union(exc.diagnostics)))
        raise DailyMonthlyRevenueSeriesBindingError(
            f"series_catalog_selection_failed:{exc.code}", diagnostics=merged
        ) from exc

    # 確認讀取期間 binding、pointer 與 immutable catalog 沒有被替換或原地改寫。
    _verify_file_signature(binding_path, binding_signature, "binding")
    _verify_file_signature(pointer_path, pointer_signature, "pointer")
    _verify_file_signature(catalog_path, catalog_signature, "catalog")
    all_diagnostics = tuple(
        sorted(set(diagnostics).union(selection.candidate_diagnostics))[
            :DAILY_MONTHLY_REVENUE_SERIES_MAX_CANDIDATES
        ]
    )
    try:
        return DailyMonthlyRevenueSeriesBoundSelectionV1(
            selection=selection,
            binding_sha256=expected_binding,
            pointer_sha256=hashlib.sha256(raw_pointer).hexdigest(),
            catalog_sha256=catalog_digest,
            report_period=selected_period,
            cutoff_at=cutoff,
            candidate_diagnostics=all_diagnostics,
            _issuer=_BOUND_SELECTION_ISSUER,
        )
    except (TypeError, ValueError) as exc:
        if isinstance(exc, DailyMonthlyRevenueSeriesBindingError):
            raise
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_bound_selection_issue_failed"
        ) from exc


def read_daily_monthly_revenue_series_exact_pin_v1(
    path: Path | str, *, expected_binding_sha256: str,
    cohort_pin: DailyMonthlyRevenueCohortPin, expected_cohort_sha256: str,
    cutoff_at: datetime, forbidden_roots: Sequence[Path] = (),
) -> DailyMonthlyRevenueSeriesSelectionV1:
    """沿固定 trust 精確重開保存 pin；不讀 mutable pointer 或 catalog。"""
    expected_binding = _require_sha256(expected_binding_sha256, "expected_binding_sha256")
    expected_cohort = _require_sha256(expected_cohort_sha256, "expected_cohort_sha256")
    cutoff = _require_aware_datetime(cutoff_at, "cutoff_at")
    if type(cohort_pin) is not DailyMonthlyRevenueCohortPin:
        raise DailyMonthlyRevenueSeriesBindingError("series_exact_pin_type_invalid")
    checked_pin = DailyMonthlyRevenueCohortPin.from_dict(cohort_pin.to_dict())
    if checked_pin != cohort_pin or checked_pin.cohort_sha256 != expected_cohort:
        raise DailyMonthlyRevenueSeriesBindingError("series_exact_pin_external_hash_mismatch")
    forbidden = _normalize_forbidden_roots(forbidden_roots)
    binding_path = _checked_absolute_path(path, "binding_path")
    if binding_path != _resolved(binding_path):
        raise DailyMonthlyRevenueSeriesBindingError("series_binding_path_not_canonical")
    _reject_overlaps(binding_path, forbidden, "binding_path")
    raw_binding, signature = _read_regular_file(binding_path,
        max_bytes=DAILY_MONTHLY_REVENUE_SERIES_BINDING_MAX_BYTES, label="binding")
    if hashlib.sha256(raw_binding).hexdigest() != expected_binding:
        raise DailyMonthlyRevenueSeriesBindingError("series_binding_external_hash_mismatch")
    binding = _decode_canonical_object(raw_binding, "binding", DAILY_MONTHLY_REVENUE_SERIES_BINDING_MAX_BYTES)
    if set(binding) != _BINDING_FIELDS or binding.get("schema_version") != DAILY_MONTHLY_REVENUE_SERIES_BINDING_SCHEMA_V1:
        raise DailyMonthlyRevenueSeriesBindingError("series_binding_fields_or_schema_invalid")
    trust = _parse_trust(binding.get("trust"))
    # Validate configured path boundaries without using mutable selection files.
    catalog_root = _checked_directory_path(binding.get("catalog_root"), "catalog_root", must_exist=False)
    pointer_path = _checked_absolute_path(binding.get("pointer_path"), "pointer_path")
    if str(catalog_root) != binding.get("catalog_root") or str(pointer_path) != binding.get("pointer_path"):
        raise DailyMonthlyRevenueSeriesBindingError("series_exact_configured_paths_not_canonical")
    if pointer_path != _resolved(pointer_path) or pointer_path.suffix.lower() != ".json" or _resolved(pointer_path.parent) != catalog_root:
        raise DailyMonthlyRevenueSeriesBindingError("series_pointer_must_be_json_child_of_catalog_root")
    _validate_data_roots(trust, catalog_root)
    _reject_all_configured_paths(binding_path, pointer_path, catalog_root, trust, forbidden)
    pin_path = Path(trust.cohort_pin_root) / f"{expected_cohort}.json"
    _reject_overlaps(pin_path, forbidden, "exact_cohort_pin")
    raw_pin, pin_signature = _read_regular_file(pin_path,
        max_bytes=DAILY_MONTHLY_REVENUE_COHORT_ENVELOPE_BYTES, label="exact_cohort_pin")
    persisted_pin = DailyMonthlyRevenueCohortPin.from_json(raw_pin)
    if persisted_pin != checked_pin or raw_pin != persisted_pin.to_json().encode("utf-8"):
        raise DailyMonthlyRevenueSeriesBindingError("series_exact_persisted_pin_mismatch")
    selected = select_daily_monthly_revenue_series_v1(
        trust=trust, expected_trust_configuration_sha256=trust.configuration_sha256,
        report_period=checked_pin.period, candidate_pins=(persisted_pin,), cutoff_at=cutoff,
    )
    _verify_file_signature(binding_path, signature, "binding")
    _verify_file_signature(pin_path, pin_signature, "exact_cohort_pin")
    selected.verify_integrity()
    return selected


def _parse_trust(value: object) -> DailyMonthlyRevenueSeriesTrustV1:
    if not isinstance(value, dict) or set(value) != _TRUST_FIELDS:
        raise DailyMonthlyRevenueSeriesBindingError("series_trust_fields_invalid")
    if value.get("schema_version") != "daily-monthly-revenue-series-trust.v1":
        raise DailyMonthlyRevenueSeriesBindingError("series_trust_schema_unsupported")
    if value.get("required_markets") != list(_MARKETS):
        raise DailyMonthlyRevenueSeriesBindingError("series_trust_markets_invalid")
    raw_markets = value.get("market_sources")
    if not isinstance(raw_markets, list) or len(raw_markets) != len(_MARKETS):
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_trust_market_sources_incomplete"
        )
    sources: list[DailyMonthlyRevenueSeriesMarketTrustV1] = []
    for expected_market, raw_source in zip(_MARKETS, raw_markets):
        if not isinstance(raw_source, dict) or set(raw_source) != _MARKET_FIELDS:
            raise DailyMonthlyRevenueSeriesBindingError(
                f"series_trust_market_fields_invalid:{expected_market}"
            )
        market = _require_text(raw_source.get("market"), "market")
        if market != expected_market:
            raise DailyMonthlyRevenueSeriesBindingError(
                f"series_trust_market_order_invalid:{expected_market}"
            )
        try:
            acceptance = _parse_acceptance(
                raw_source.get("trusted_acceptance"), expected_market=expected_market
            )
        except DailyMonthlyRevenueCohortBindingError as exc:
            raise DailyMonthlyRevenueSeriesBindingError(
                f"series_trust_acceptance_invalid:{expected_market}:{exc}"
            ) from exc
        snapshot_root = _checked_directory_path(
            raw_source.get("snapshot_root"),
            f"snapshot_root:{expected_market}",
            must_exist=True,
        )
        if str(snapshot_root) != raw_source.get("snapshot_root"):
            raise DailyMonthlyRevenueSeriesBindingError(
                f"series_snapshot_root_not_canonical:{expected_market}"
            )
        sources.append(
            DailyMonthlyRevenueSeriesMarketTrustV1(
                expected_market, snapshot_root, acceptance
            )
        )
    pin_root = _checked_directory_path(
        value.get("cohort_pin_root"), "cohort_pin_root", must_exist=True
    )
    if str(pin_root) != value.get("cohort_pin_root"):
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_cohort_pin_root_not_canonical"
        )
    try:
        trust = DailyMonthlyRevenueSeriesTrustV1(
            cohort_pin_root=pin_root,
            market_sources=tuple(sources),
        )
        supplied_hash = _require_sha256(
            value.get("configuration_sha256"), "configuration_sha256"
        )
        if supplied_hash != trust.configuration_sha256 or value != trust.to_dict():
            raise DailyMonthlyRevenueSeriesBindingError(
                "series_trust_configuration_sha256_mismatch"
            )
        trust.verify_external_anchor(supplied_hash)
        return trust
    except DailyMonthlyRevenueSeriesBindingError:
        raise
    except (DailyMonthlyRevenueSeriesError, TypeError, ValueError) as exc:
        raise DailyMonthlyRevenueSeriesBindingError(
            f"series_trust_invalid:{exc}"
        ) from exc


def _validate_data_roots(
    trust: DailyMonthlyRevenueSeriesTrustV1, catalog_root: Path
) -> None:
    roots = [
        _checked_directory_path(trust.cohort_pin_root, "cohort_pin_root", must_exist=False),
        _checked_directory_path(catalog_root, "catalog_root", must_exist=False),
        *(
            _checked_directory_path(
                source.snapshot_root,
                f"snapshot_root:{source.market}",
                must_exist=False,
            )
            for source in trust.market_sources
        ),
    ]
    resolved = [_resolved(root) for root in roots]
    for index, left in enumerate(resolved):
        for right in resolved[index + 1 :]:
            if _paths_overlap(left, right):
                raise DailyMonthlyRevenueSeriesBindingError(
                    "series_data_roots_overlap"
                )


def _reject_all_configured_paths(
    binding_path: Path,
    pointer_path: Path,
    catalog_root: Path,
    trust: DailyMonthlyRevenueSeriesTrustV1,
    forbidden: tuple[Path, ...],
) -> None:
    configured = (
        (binding_path, "binding_path"),
        (pointer_path, "pointer_path"),
        (catalog_root, "catalog_root"),
        (trust.cohort_pin_root, "cohort_pin_root"),
        *(
            (source.snapshot_root, f"snapshot_root:{source.market}")
            for source in trust.market_sources
        ),
    )
    for value, label in configured:
        path = _resolved(_checked_absolute_path(value, label))
        _reject_overlaps(path, forbidden, label)
    binding_resolved = _resolved(binding_path)
    data_roots = (
        _resolved(catalog_root),
        _resolved(_checked_absolute_path(trust.cohort_pin_root, "cohort_pin_root")),
        *(
            _resolved(
                _checked_absolute_path(
                    source.snapshot_root, f"snapshot_root:{source.market}"
                )
            )
            for source in trust.market_sources
        ),
    )
    if any(_paths_overlap(binding_resolved, root) for root in data_roots):
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_binding_path_overlaps_data_root"
        )


def _normalize_forbidden_roots(values: Sequence[Path]) -> tuple[Path, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_forbidden_roots_invalid"
        )
    roots: list[Path] = []
    for index, item in enumerate(values):
        root = _checked_directory_path(item, f"forbidden_root:{index}", must_exist=True)
        roots.append(_resolved(root))
    return tuple(roots)


def _reject_overlaps(path: Path, roots: Sequence[Path], label: str) -> None:
    resolved_path = _resolved(path)
    for root in roots:
        if _paths_overlap(resolved_path, root):
            raise DailyMonthlyRevenueSeriesBindingError(
                f"series_{label}_overlaps_forbidden_root"
            )


def _paths_overlap(left: Path, right: Path) -> bool:
    try:
        left.relative_to(right)
        return True
    except ValueError:
        pass
    try:
        right.relative_to(left)
        return True
    except ValueError:
        return False


def _checked_directory_path(
    value: object, label: str, *, must_exist: bool
) -> Path:
    checked = _checked_absolute_path(value, label)
    try:
        resolved = checked.resolve(strict=must_exist)
    except (OSError, RuntimeError, ValueError) as exc:
        raise DailyMonthlyRevenueSeriesBindingError(
            f"series_{label}_resolve_failed"
        ) from exc
    _checked_absolute_path(resolved, label)
    try:
        info = resolved.stat()
    except FileNotFoundError as exc:
        if must_exist:
            raise DailyMonthlyRevenueSeriesBindingError(
                f"series_{label}_not_found"
            ) from exc
        return resolved
    except OSError as exc:
        raise DailyMonthlyRevenueSeriesBindingError(
            f"series_{label}_path_stat_failed"
        ) from exc
    else:
        if not stat.S_ISDIR(info.st_mode):
            raise DailyMonthlyRevenueSeriesBindingError(
                f"series_{label}_not_directory"
            )
    return resolved


def _checked_absolute_path(value: object, label: str) -> Path:
    try:
        return _require_absolute_nonsymlink_path(value, label)
    except (DailyMonthlyRevenueCohortBindingError, OSError, TypeError, ValueError) as exc:
        if isinstance(exc, DailyMonthlyRevenueSeriesBindingError):
            raise
        raise DailyMonthlyRevenueSeriesBindingError(
            f"series_{label}_path_invalid:{exc}"
        ) from exc


def _resolved(value: Path) -> Path:
    try:
        return value.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_path_resolve_failed"
        ) from exc


def _read_regular_file(
    path: Path,
    *,
    max_bytes: int,
    label: str,
    expected_sha256: str | None = None,
) -> tuple[bytes, tuple[int, ...]]:
    checked = _checked_absolute_path(path, label)
    try:
        before = checked.lstat()
    except OSError as exc:
        raise DailyMonthlyRevenueSeriesBindingError(
            f"series_{label}_not_found"
        ) from exc
    _require_regular_single_link(before, label)
    if before.st_size > max_bytes:
        raise DailyMonthlyRevenueSeriesBindingError(
            f"series_{label}_exceeds_size_limit"
        )
    signature = _stat_signature(before)
    try:
        with checked.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            _require_regular_single_link(opened, label)
            if _stat_signature(opened) != signature:
                raise DailyMonthlyRevenueSeriesBindingError(
                    f"series_{label}_changed_before_read"
                )
            raw = handle.read(max_bytes + 1)
            after_handle = os.fstat(handle.fileno())
        after_path = checked.lstat()
    except DailyMonthlyRevenueSeriesBindingError:
        raise
    except OSError as exc:
        raise DailyMonthlyRevenueSeriesBindingError(
            f"series_{label}_unreadable"
        ) from exc
    _require_regular_single_link(after_handle, label)
    _require_regular_single_link(after_path, label)
    if (
        _stat_signature(after_handle) != signature
        or _stat_signature(after_path) != signature
    ):
        raise DailyMonthlyRevenueSeriesBindingError(
            f"series_{label}_changed_during_read"
        )
    if len(raw) > max_bytes:
        raise DailyMonthlyRevenueSeriesBindingError(
            f"series_{label}_exceeds_size_limit"
        )
    if len(raw) != before.st_size:
        raise DailyMonthlyRevenueSeriesBindingError(
            f"series_{label}_short_read"
        )
    if expected_sha256 is not None and hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise DailyMonthlyRevenueSeriesBindingError(
            f"series_{label}_sha256_mismatch"
        )
    return raw, signature


def _verify_file_signature(path: Path, expected: tuple[int, ...], label: str) -> None:
    try:
        current = path.lstat()
    except OSError as exc:
        raise DailyMonthlyRevenueSeriesBindingError(
            f"series_{label}_disappeared_after_read"
        ) from exc
    _require_regular_single_link(current, label)
    if _stat_signature(current) != expected:
        raise DailyMonthlyRevenueSeriesBindingError(
            f"series_{label}_changed_after_read"
        )


def _require_regular_single_link(info: os.stat_result, label: str) -> None:
    attributes = getattr(info, "st_file_attributes", 0)
    if stat.S_ISLNK(info.st_mode) or attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
        raise DailyMonthlyRevenueSeriesBindingError(f"series_{label}_is_reparse_point")
    if not stat.S_ISREG(info.st_mode):
        raise DailyMonthlyRevenueSeriesBindingError(f"series_{label}_not_regular")
    if getattr(info, "st_nlink", 1) != 1:
        raise DailyMonthlyRevenueSeriesBindingError(f"series_{label}_has_hardlinks")


def _stat_signature(info: os.stat_result) -> tuple[int, ...]:
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_mode),
        int(info.st_size),
        int(getattr(info, "st_mtime_ns", int(info.st_mtime * 1_000_000_000))),
        int(getattr(info, "st_ctime_ns", int(info.st_ctime * 1_000_000_000))),
        int(getattr(info, "st_nlink", 1)),
        int(getattr(info, "st_file_attributes", 0)),
    )


def _decode_canonical_object(raw: bytes, label: str, max_bytes: int) -> dict[str, Any]:
    if len(raw) > max_bytes:
        raise DailyMonthlyRevenueSeriesBindingError(
            f"series_{label}_exceeds_size_limit"
        )
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except DailyMonthlyRevenueSeriesBindingError:
        raise
    except RecursionError as exc:
        raise DailyMonthlyRevenueSeriesBindingError(
            f"series_{label}_json_nesting_exceeds_parser_limit"
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise DailyMonthlyRevenueSeriesBindingError(
            f"series_{label}_json_invalid"
        ) from exc
    if not isinstance(value, dict):
        raise DailyMonthlyRevenueSeriesBindingError(
            f"series_{label}_json_object_required"
        )
    _enforce_json_depth(value, label=label, max_depth=12)
    if _canonical_json_bytes(value) != raw:
        raise DailyMonthlyRevenueSeriesBindingError(
            f"series_{label}_json_not_canonical"
        )
    return value


def _enforce_json_depth(value: object, *, label: str, max_depth: int) -> None:
    pending: list[tuple[object, int]] = [(value, 1)]
    while pending:
        current, depth = pending.pop()
        if depth > max_depth:
            raise DailyMonthlyRevenueSeriesBindingError(
                f"series_{label}_json_depth_exceeded"
            )
        if isinstance(current, dict):
            pending.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            pending.extend((item, depth + 1) for item in current)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DailyMonthlyRevenueSeriesBindingError(
                f"series_json_duplicate_key:{key}"
            )
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise DailyMonthlyRevenueSeriesBindingError(
        f"series_json_constant_invalid:{value}"
    )


def _write_create_only(path: Path, payload: bytes, max_bytes: int) -> None:
    if len(payload) > max_bytes:
        raise DailyMonthlyRevenueSeriesBindingError("series_create_only_size_limit")
    checked = _checked_absolute_path(path, "create_only_path")
    try:
        descriptor = os.open(
            checked,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError as exc:
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_create_only_target_exists"
        ) from exc
    except OSError as exc:
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_create_only_open_failed"
        ) from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            written = handle.write(payload)
            if written != len(payload):
                raise DailyMonthlyRevenueSeriesBindingError(
                    "series_create_only_short_write"
                )
            handle.flush()
            os.fsync(handle.fileno())
    except DailyMonthlyRevenueSeriesBindingError:
        try:
            checked.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    except OSError as exc:
        try:
            checked.unlink(missing_ok=True)
        except OSError:
            pass
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_create_only_write_failed"
        ) from exc


def _canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_json_serialization_failed"
        ) from exc


def _validate_catalog_hashes(
    value: object, *, require_sorted: bool = True
) -> tuple[str, ...]:
    if type(value) not in (list, tuple):
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_catalog_hashes_invalid"
        )
    raw_hashes = cast(Sequence[object], value)
    if not 1 <= len(raw_hashes) <= DAILY_MONTHLY_REVENUE_SERIES_MAX_CANDIDATES:
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_catalog_candidate_count_out_of_bounds"
        )
    hashes = tuple(_require_sha256(item, "cohort_sha256") for item in raw_hashes)
    if len(set(hashes)) != len(hashes):
        raise DailyMonthlyRevenueSeriesBindingError("series_catalog_duplicate_hash")
    sorted_hashes = tuple(sorted(hashes))
    if require_sorted and hashes != sorted_hashes:
        raise DailyMonthlyRevenueSeriesBindingError("series_catalog_hashes_not_sorted")
    return hashes if require_sorted else sorted_hashes


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise DailyMonthlyRevenueSeriesBindingError(f"series_{label}_invalid")
    return value


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise DailyMonthlyRevenueSeriesBindingError(f"series_{label}_invalid")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise DailyMonthlyRevenueSeriesBindingError(
            f"series_{label}_invalid_encoding"
        ) from exc
    return value


def _validate_period(value: object) -> str:
    if not isinstance(value, str):
        raise DailyMonthlyRevenueSeriesBindingError("series_report_period_invalid")
    match = _PERIOD_RE.fullmatch(value)
    if match is None or not 1 <= int(match.group(2)) <= 12:
        raise DailyMonthlyRevenueSeriesBindingError("series_report_period_invalid")
    return value


def _require_aware_datetime(value: object, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DailyMonthlyRevenueSeriesBindingError(
            f"series_{label}_must_be_aware"
        )
    return value


def _require_diagnostics(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple) or type(value) is not tuple:
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_candidate_diagnostics_invalid"
        )
    diagnostics = cast(tuple[object, ...], value)
    if len(diagnostics) > DAILY_MONTHLY_REVENUE_SERIES_MAX_CANDIDATES:
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_candidate_diagnostics_invalid"
        )
    if any(
        not isinstance(item, str) or not item or len(item) > 240
        for item in diagnostics
    ):
        raise DailyMonthlyRevenueSeriesBindingError(
            "series_candidate_diagnostics_invalid"
        )
    return cast(tuple[str, ...], diagnostics)


def _safe_reason(exc: Exception) -> str:
    reason = str(exc).replace("\r", " ").replace("\n", " ")
    if not reason:
        reason = type(exc).__name__
    return reason[:160]


__all__ = (
    "DAILY_MONTHLY_REVENUE_SERIES_BINDING_MAX_BYTES",
    "DAILY_MONTHLY_REVENUE_SERIES_BINDING_SCHEMA_V1",
    "DAILY_MONTHLY_REVENUE_SERIES_CATALOG_MAX_BYTES",
    "DAILY_MONTHLY_REVENUE_SERIES_CATALOG_POINTER_SCHEMA_V1",
    "DAILY_MONTHLY_REVENUE_SERIES_CATALOG_SCHEMA_V1",
    "DAILY_MONTHLY_REVENUE_SERIES_POINTER_MAX_BYTES",
    "DailyMonthlyRevenueSeriesBindingError",
    "DailyMonthlyRevenueSeriesBoundSelectionV1",
    "read_daily_monthly_revenue_series_binding_v1",
    "serialize_daily_monthly_revenue_series_binding_v1",
    "serialize_daily_monthly_revenue_series_catalog_pointer_v1",
    "serialize_daily_monthly_revenue_series_catalog_v1",
    "write_daily_monthly_revenue_series_catalog_create_only",
    "write_daily_monthly_revenue_series_pointer_create_only",
)
