"""由外部固定 hash 的設定載入月營收 cohort 與用途接受錨點。

外部 hash 只固定 caller 選擇的設定 bytes，不是官方品質簽章；用途接受仍來自
caller 明示的 typed acceptance 與其外部信任設定，每日批次品質由 snapshot reader 重驗。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import stat
from typing import Any

from data_module.daily_monthly_revenue_cohort import (
    DailyMonthlyRevenueCohortError,
    DailyMonthlyRevenueCohortPin,
    DailyMonthlyRevenueCohortReader,
    read_daily_monthly_revenue_cohort_pin,
)
from data_module.daily_source_snapshot import (
    DAILY_SOURCE_TIME_BASIS_POLICY,
    DailySourceSnapshotError,
    DailySourceSnapshotFileReader,
    DailySourceUseAcceptance,
    DailySourceUseScope,
)


DAILY_MONTHLY_REVENUE_COHORT_BINDING_SCHEMA = (
    "daily-monthly-revenue-cohort-binding.v1"
)
DAILY_MONTHLY_REVENUE_COHORT_BINDING_MAX_BYTES = 64 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FILE_ATTRIBUTE_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
_MARKET_ORDER = ("twse", "tpex")
_SCOPE_FIELDS = {
    "dataset_id",
    "source_id",
    "market",
    "parser_version",
    "source_schema_version",
    "unit",
    "intended_use",
}
_ACCEPTANCE_FIELDS = {
    "scope",
    "acceptance_id",
    "accepted_at",
    "official_source_endpoint",
    "document_chain",
    "acceptance_evidence_ref",
    "authorization_scope",
    "time_basis_policy",
}
_BINDING_FIELDS = {
    "schema_version",
    "cohort_pin_root",
    "cohort_sha256",
    "markets",
}
_MARKET_FIELDS = {"market", "snapshot_root", "trusted_acceptance"}


class DailyMonthlyRevenueCohortBindingError(ValueError):
    """明示月營收 cohort binding 未通過讀取或用途範圍驗證。"""


def serialize_daily_monthly_revenue_cohort_binding(
    *,
    cohort_pin_root: Path | str,
    pin: DailyMonthlyRevenueCohortPin,
    market_readers: Mapping[str, DailySourceSnapshotFileReader],
) -> bytes:
    """序列化既有 pin 與 typed acceptance；不建立接受紀錄或寫入檔案。"""

    if not isinstance(pin, DailyMonthlyRevenueCohortPin):
        raise DailyMonthlyRevenueCohortBindingError("binding_pin_type_invalid")
    pin_root = _require_absolute_nonsymlink_path(
        cohort_pin_root, "cohort_pin_root"
    )
    if not isinstance(market_readers, Mapping) or set(market_readers) != set(
        pin.required_markets
    ):
        raise DailyMonthlyRevenueCohortBindingError(
            "binding_market_readers_incomplete_or_extra"
        )
    try:
        persisted_pin = read_daily_monthly_revenue_cohort_pin(
            pin_root,
            pin.cohort_sha256,
            expected_cohort_sha256=pin.cohort_sha256,
        )
    except (DailyMonthlyRevenueCohortError, OSError, TypeError, ValueError) as exc:
        raise DailyMonthlyRevenueCohortBindingError(
            f"binding_pin_rejected:{exc}"
        ) from exc
    if persisted_pin != pin:
        raise DailyMonthlyRevenueCohortBindingError("binding_pin_object_mismatch")

    readers: dict[str, DailySourceSnapshotFileReader] = {}
    market_rows: list[dict[str, object]] = []
    for market in pin.required_markets:
        source_reader = market_readers[market]
        if not isinstance(source_reader, DailySourceSnapshotFileReader):
            raise DailyMonthlyRevenueCohortBindingError(
                f"binding_reader_type_invalid:{market}"
            )
        acceptance = source_reader.trusted_acceptance
        if not isinstance(acceptance, DailySourceUseAcceptance):
            raise DailyMonthlyRevenueCohortBindingError(
                f"binding_trusted_acceptance_missing:{market}"
            )
        _validate_current_scope(acceptance.scope, market)
        if acceptance.time_basis_policy != DAILY_SOURCE_TIME_BASIS_POLICY:
            raise DailyMonthlyRevenueCohortBindingError(
                f"binding_time_basis_policy_invalid:{market}"
            )
        root = _require_absolute_nonsymlink_path(
            source_reader.root, f"snapshot_root:{market}"
        )
        readers[market] = DailySourceSnapshotFileReader(
            root, trusted_acceptance=acceptance
        )
        market_rows.append(
            {
                "market": market,
                "snapshot_root": str(root),
                "trusted_acceptance": acceptance.to_dict(),
            }
        )

    try:
        cohort_reader = DailyMonthlyRevenueCohortReader(
            pin=pin,
            market_readers=readers,
            expected_cohort_sha256=pin.cohort_sha256,
        )
        cohort_reader.verify_cohort()
    except (
        DailyMonthlyRevenueCohortError,
        DailySourceSnapshotError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise DailyMonthlyRevenueCohortBindingError(
            f"binding_cohort_verification_failed:{exc}"
        ) from exc

    payload = _canonical_json_bytes(
        {
            "schema_version": DAILY_MONTHLY_REVENUE_COHORT_BINDING_SCHEMA,
            "cohort_pin_root": str(pin_root),
            "cohort_sha256": pin.cohort_sha256,
            "markets": market_rows,
        }
    )
    if len(payload) > DAILY_MONTHLY_REVENUE_COHORT_BINDING_MAX_BYTES:
        raise DailyMonthlyRevenueCohortBindingError(
            "binding_exceeds_size_limit"
        )
    return payload


def read_daily_monthly_revenue_cohort_binding(
    path: Path | str,
    *,
    expected_binding_sha256: str,
    forbidden_roots: Sequence[Path] = (),
) -> DailyMonthlyRevenueCohortReader:
    """讀取外部 hash 固定的 binding 並重驗 pin 與全部必要市場。"""

    expected_hash = _require_sha256(
        expected_binding_sha256, "expected_binding_sha256"
    )
    forbidden = _normalize_forbidden_roots(forbidden_roots)
    binding_path = _require_absolute_nonsymlink_path(path, "binding_path")
    _reject_forbidden_path(binding_path, forbidden, "binding_path")
    try:
        info = binding_path.lstat()
    except OSError as exc:
        raise DailyMonthlyRevenueCohortBindingError(
            "binding_file_not_found"
        ) from exc
    if stat.S_ISLNK(info.st_mode):
        raise DailyMonthlyRevenueCohortBindingError("binding_file_is_symlink")
    if not stat.S_ISREG(info.st_mode):
        raise DailyMonthlyRevenueCohortBindingError("binding_file_not_regular")
    if info.st_size > DAILY_MONTHLY_REVENUE_COHORT_BINDING_MAX_BYTES:
        raise DailyMonthlyRevenueCohortBindingError("binding_exceeds_size_limit")
    try:
        with binding_path.open("rb") as handle:
            raw = handle.read(DAILY_MONTHLY_REVENUE_COHORT_BINDING_MAX_BYTES + 1)
    except OSError as exc:
        raise DailyMonthlyRevenueCohortBindingError("binding_file_unreadable") from exc
    if len(raw) > DAILY_MONTHLY_REVENUE_COHORT_BINDING_MAX_BYTES:
        raise DailyMonthlyRevenueCohortBindingError("binding_exceeds_size_limit")
    if hashlib.sha256(raw).hexdigest() != expected_hash:
        raise DailyMonthlyRevenueCohortBindingError(
            "binding_external_hash_mismatch"
        )

    document = _decode_binding_json(raw)
    if set(document) != _BINDING_FIELDS:
        raise DailyMonthlyRevenueCohortBindingError("binding_fields_invalid")
    if document.get("schema_version") != DAILY_MONTHLY_REVENUE_COHORT_BINDING_SCHEMA:
        raise DailyMonthlyRevenueCohortBindingError("binding_schema_unsupported")
    cohort_sha256 = _require_sha256(
        document.get("cohort_sha256"), "cohort_sha256"
    )
    pin_root = _require_absolute_nonsymlink_path(
        document.get("cohort_pin_root"), "cohort_pin_root"
    )
    _reject_forbidden_path(pin_root, forbidden, "cohort_pin_root")
    try:
        pin = read_daily_monthly_revenue_cohort_pin(
            pin_root,
            cohort_sha256,
            expected_cohort_sha256=cohort_sha256,
        )
    except (DailyMonthlyRevenueCohortError, OSError, TypeError, ValueError) as exc:
        raise DailyMonthlyRevenueCohortBindingError(
            f"binding_pin_rejected:{exc}"
        ) from exc

    raw_markets = document.get("markets")
    if not isinstance(raw_markets, list):
        raise DailyMonthlyRevenueCohortBindingError("binding_markets_invalid")
    if len(raw_markets) != len(pin.required_markets):
        raise DailyMonthlyRevenueCohortBindingError(
            "binding_markets_incomplete_or_extra"
        )

    readers: dict[str, DailySourceSnapshotFileReader] = {}
    seen_markets: list[str] = []
    for raw_market in raw_markets:
        if not isinstance(raw_market, dict) or set(raw_market) != _MARKET_FIELDS:
            raise DailyMonthlyRevenueCohortBindingError(
                "binding_market_fields_invalid"
            )
        market = _require_text(raw_market.get("market"), "market")
        if market not in _MARKET_ORDER:
            raise DailyMonthlyRevenueCohortBindingError(
                f"binding_market_unsupported:{market}"
            )
        if market in seen_markets:
            raise DailyMonthlyRevenueCohortBindingError(
                f"binding_market_duplicate:{market}"
            )
        seen_markets.append(market)
        root = _require_absolute_nonsymlink_path(
            raw_market.get("snapshot_root"), f"snapshot_root:{market}"
        )
        _reject_forbidden_path(root, forbidden, f"snapshot_root:{market}")
        acceptance = _parse_acceptance(
            raw_market.get("trusted_acceptance"), expected_market=market
        )
        readers[market] = DailySourceSnapshotFileReader(
            root, trusted_acceptance=acceptance
        )
    if tuple(seen_markets) != pin.required_markets:
        raise DailyMonthlyRevenueCohortBindingError(
            "binding_markets_do_not_match_pinned_order"
        )

    try:
        reader = DailyMonthlyRevenueCohortReader(
            pin=pin,
            market_readers=readers,
            expected_cohort_sha256=cohort_sha256,
        )
        reader.verify_cohort()
    except (
        DailyMonthlyRevenueCohortError,
        DailySourceSnapshotError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise DailyMonthlyRevenueCohortBindingError(
            f"binding_cohort_verification_failed:{exc}"
        ) from exc
    return reader


def _parse_acceptance(
    value: object, *, expected_market: str
) -> DailySourceUseAcceptance:
    if not isinstance(value, dict) or set(value) != _ACCEPTANCE_FIELDS:
        raise DailyMonthlyRevenueCohortBindingError(
            f"binding_acceptance_fields_invalid:{expected_market}"
        )
    raw_scope = value.get("scope")
    if not isinstance(raw_scope, dict) or set(raw_scope) != _SCOPE_FIELDS:
        raise DailyMonthlyRevenueCohortBindingError(
            f"binding_acceptance_scope_fields_invalid:{expected_market}"
        )
    scope = DailySourceUseScope(
        dataset_id=_require_text(raw_scope.get("dataset_id"), "scope_dataset_id"),
        source_id=_require_text(raw_scope.get("source_id"), "scope_source_id"),
        market=_require_text(raw_scope.get("market"), "scope_market"),
        parser_version=_require_text(
            raw_scope.get("parser_version"), "scope_parser_version"
        ),
        source_schema_version=_require_text(
            raw_scope.get("source_schema_version"), "scope_source_schema_version"
        ),
        unit=_require_text(raw_scope.get("unit"), "scope_unit"),
        intended_use=_require_text(
            raw_scope.get("intended_use"), "scope_intended_use"
        ),
    )
    _validate_current_scope(scope, expected_market)

    accepted_at_text = _require_text(value.get("accepted_at"), "accepted_at")
    try:
        accepted_at = datetime.fromisoformat(accepted_at_text)
    except ValueError as exc:
        raise DailyMonthlyRevenueCohortBindingError(
            f"binding_acceptance_timestamp_invalid:{expected_market}"
        ) from exc
    raw_document_chain = value.get("document_chain")
    if not isinstance(raw_document_chain, list) or not raw_document_chain:
        raise DailyMonthlyRevenueCohortBindingError(
            f"binding_acceptance_document_chain_invalid:{expected_market}"
        )
    document_chain = tuple(
        _require_text(item, "document_chain_item") for item in raw_document_chain
    )
    try:
        return DailySourceUseAcceptance(
            scope=scope,
            acceptance_id=_require_text(value.get("acceptance_id"), "acceptance_id"),
            accepted_at=accepted_at,
            official_source_endpoint=_require_text(
                value.get("official_source_endpoint"), "official_source_endpoint"
            ),
            document_chain=document_chain,
            acceptance_evidence_ref=_require_text(
                value.get("acceptance_evidence_ref"), "acceptance_evidence_ref"
            ),
            authorization_scope=_require_text(
                value.get("authorization_scope"), "authorization_scope"
            ),
            time_basis_policy=_require_text(
                value.get("time_basis_policy"), "time_basis_policy"
            ),
        )
    except (DailySourceSnapshotError, TypeError, ValueError) as exc:
        raise DailyMonthlyRevenueCohortBindingError(
            f"binding_acceptance_invalid:{expected_market}:{exc}"
        ) from exc


def _validate_current_scope(scope: DailySourceUseScope, market: str) -> None:
    if not isinstance(scope, DailySourceUseScope):
        raise DailyMonthlyRevenueCohortBindingError(
            f"binding_scope_type_invalid:{market}"
        )
    expected = (
        "fundamental_current_observations.monthly_revenue",
        "mops.monthly_revenue_static_snapshot",
        market,
        "mops-current-revenue-normalizer.v2",
        "mops-static-snapshot.v2",
        "TWD",
        "recommendation_current_fundamental",
    )
    actual = (
        scope.dataset_id,
        scope.source_id,
        scope.market,
        scope.parser_version,
        scope.source_schema_version,
        scope.unit,
        scope.intended_use,
    )
    openapi_expected = (
        "fundamental_current_observations.monthly_revenue",
        {
            "twse": "twse.openapi.t187ap05_L",
            "tpex": "tpex.openapi.mopsfin_t187ap05_O",
        }.get(market),
        market,
        "twse-tpex-openapi-monthly-revenue-parser.v1",
        "twse-tpex-openapi-monthly-revenue-14-fields.v1",
        "TWD",
        "recommendation_current_fundamental",
    )
    if market not in _MARKET_ORDER or actual not in {expected, openapi_expected}:
        raise DailyMonthlyRevenueCohortBindingError(
            f"binding_scope_not_current_monthly_revenue:{market}"
        )


def _decode_binding_json(raw: bytes) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except DailyMonthlyRevenueCohortBindingError:
        raise
    except RecursionError as exc:
        raise DailyMonthlyRevenueCohortBindingError(
            "binding_json_nesting_exceeds_parser_limit"
        ) from exc
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        raise DailyMonthlyRevenueCohortBindingError(
            "binding_json_invalid"
        ) from exc
    if not isinstance(value, dict):
        raise DailyMonthlyRevenueCohortBindingError("binding_json_object_required")
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DailyMonthlyRevenueCohortBindingError(
                f"binding_duplicate_json_key:{key}"
            )
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise DailyMonthlyRevenueCohortBindingError(
        f"binding_json_constant_invalid:{value}"
    )


def _require_absolute_nonsymlink_path(value: object, label: str) -> Path:
    if (
        not isinstance(value, (str, Path))
        or not str(value).strip()
        or "\x00" in str(value)
    ):
        raise DailyMonthlyRevenueCohortBindingError(f"binding_{label}_missing")
    raw_path = str(value)
    try:
        raw_path.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise DailyMonthlyRevenueCohortBindingError(
            f"binding_{label}_invalid_encoding"
        ) from exc
    try:
        path = Path(value).expanduser()
    except (OSError, TypeError, ValueError) as exc:
        raise DailyMonthlyRevenueCohortBindingError(
            f"binding_{label}_invalid"
        ) from exc
    if not path.is_absolute():
        raise DailyMonthlyRevenueCohortBindingError(
            f"binding_{label}_must_be_absolute"
        )
    try:
        for component in (path, *path.parents):
            try:
                component_info = component.lstat()
            except FileNotFoundError:
                continue
            attributes = getattr(component_info, "st_file_attributes", 0)
            if stat.S_ISLNK(component_info.st_mode):
                raise DailyMonthlyRevenueCohortBindingError(
                    f"binding_{label}_is_symlink"
                )
            if attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
                raise DailyMonthlyRevenueCohortBindingError(
                    f"binding_{label}_is_reparse_point"
                )
    except OSError as exc:
        raise DailyMonthlyRevenueCohortBindingError(
            f"binding_{label}_path_check_failed"
        ) from exc
    return path


def _normalize_forbidden_roots(
    values: Sequence[Path],
) -> tuple[Path, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise DailyMonthlyRevenueCohortBindingError(
            "binding_forbidden_roots_invalid"
        )
    roots: list[Path] = []
    for index, value in enumerate(values):
        root = _require_absolute_nonsymlink_path(
            value, f"forbidden_root_{index}"
        )
        try:
            roots.append(root.resolve(strict=False))
        except (OSError, RuntimeError, ValueError) as exc:
            raise DailyMonthlyRevenueCohortBindingError(
                f"binding_forbidden_root_resolve_failed:{index}"
            ) from exc
    return tuple(roots)


def _reject_forbidden_path(
    path: Path,
    forbidden_roots: tuple[Path, ...],
    label: str,
) -> None:
    try:
        resolved = path.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise DailyMonthlyRevenueCohortBindingError(
            f"binding_{label}_resolve_failed"
        ) from exc
    for root in forbidden_roots:
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        raise DailyMonthlyRevenueCohortBindingError(
            f"binding_{label}_inside_forbidden_root"
        )


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise DailyMonthlyRevenueCohortBindingError(
            f"binding_{label}_invalid"
        )
    return value


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise DailyMonthlyRevenueCohortBindingError(
            f"binding_{label}_invalid"
        )
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise DailyMonthlyRevenueCohortBindingError(
            f"binding_{label}_invalid_encoding"
        ) from exc
    return value


def _canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DailyMonthlyRevenueCohortBindingError(
            "binding_serialization_failed"
        ) from exc


__all__ = (
    "DAILY_MONTHLY_REVENUE_COHORT_BINDING_MAX_BYTES",
    "DAILY_MONTHLY_REVENUE_COHORT_BINDING_SCHEMA",
    "DailyMonthlyRevenueCohortBindingError",
    "read_daily_monthly_revenue_cohort_binding",
    "serialize_daily_monthly_revenue_cohort_binding",
)
