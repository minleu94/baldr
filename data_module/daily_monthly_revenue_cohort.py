"""雙市場月營收快照的不可變 cohort pin 與精確讀取 port。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

from data_module.daily_source_snapshot import (
    DAILY_SOURCE_TIME_BASIS_POLICY,
    DailySourceSnapshot,
    DailySourceSnapshotFileReader,
    DailySourceUseAcceptance,
    DailySourceUseScope,
)


DAILY_MONTHLY_REVENUE_COHORT_SCHEMA = "daily-monthly-revenue-cohort-pin.v1"
DAILY_MONTHLY_REVENUE_COHORT_ENVELOPE_BYTES = 64 * 1024
_TAIPEI = ZoneInfo("Asia/Taipei")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PERIOD_RE = re.compile(r"^(\d{4})-(\d{2})$")
_BATCH_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MARKET_ORDER = ("twse", "tpex")


class DailyMonthlyRevenueCohortError(ValueError):
    """每日月營收 cohort pin 或讀取未通過契約。"""


@dataclass(frozen=True, slots=True)
class DailyMonthlyRevenueMarketSnapshotPin:
    """一個市場已保存每日批次的完整 immutable identity。"""

    market: str
    period: str
    batch_id: str
    scope: DailySourceUseScope
    acceptance_id: str
    acceptance_sha256: str
    time_basis_policy: str
    manifest_sha256: str
    receipt_sha256: str
    raw_source_sha256: str
    transport_sha256: str
    record_count: int
    available_hour: datetime
    availability_basis: tuple[str, ...]
    source_batch_started_at: datetime
    first_persisted_at: datetime
    successful_batch_completed_at: datetime

    def __post_init__(self) -> None:
        if self.market not in _MARKET_ORDER:
            raise DailyMonthlyRevenueCohortError("cohort_market_unsupported")
        _validate_period(self.period)
        if not isinstance(self.scope, DailySourceUseScope):
            raise DailyMonthlyRevenueCohortError("cohort_market_scope_type_invalid")
        if self.scope.market != self.market:
            raise DailyMonthlyRevenueCohortError("cohort_market_scope_mismatch")
        _require_batch_id(self.batch_id)
        _require_text(self.acceptance_id, "acceptance_id")
        for label, value in (
            ("acceptance_sha256", self.acceptance_sha256),
            ("manifest_sha256", self.manifest_sha256),
            ("receipt_sha256", self.receipt_sha256),
            ("raw_source_sha256", self.raw_source_sha256),
            ("transport_sha256", self.transport_sha256),
        ):
            _require_hash(value, label)
        if self.time_basis_policy != DAILY_SOURCE_TIME_BASIS_POLICY:
            raise DailyMonthlyRevenueCohortError("cohort_time_basis_policy_unsupported")
        if type(self.record_count) is not int or self.record_count <= 0:
            raise DailyMonthlyRevenueCohortError("cohort_record_count_invalid")
        if self.record_count > 100_000:
            raise DailyMonthlyRevenueCohortError("cohort_record_count_exceeds_limit")
        basis = _require_string_tuple(self.availability_basis, "availability_basis")
        if not basis:
            raise DailyMonthlyRevenueCohortError("cohort_availability_basis_missing")
        if basis != tuple(sorted(basis)):
            raise DailyMonthlyRevenueCohortError("cohort_availability_basis_not_canonical")
        object.__setattr__(self, "availability_basis", basis)
        for label in (
            "available_hour",
            "source_batch_started_at",
            "first_persisted_at",
            "successful_batch_completed_at",
        ):
            object.__setattr__(self, label, _to_taipei(getattr(self, label), label))
        if self.available_hour != self.available_hour.replace(
            minute=0, second=0, microsecond=0
        ):
            raise DailyMonthlyRevenueCohortError("cohort_available_hour_not_exact_hour")
        if self.source_batch_started_at > self.first_persisted_at:
            raise DailyMonthlyRevenueCohortError("cohort_batch_started_after_persist")
        if self.first_persisted_at > self.successful_batch_completed_at:
            raise DailyMonthlyRevenueCohortError("cohort_persist_after_batch_completion")
        if self.available_hour < _ceil_hour(self.successful_batch_completed_at):
            raise DailyMonthlyRevenueCohortError("cohort_available_hour_before_batch_gate")

    def to_dict(self) -> dict[str, object]:
        return {
            "market": self.market,
            "period": self.period,
            "batch_id": self.batch_id,
            "scope": self.scope.to_dict(),
            "acceptance_id": self.acceptance_id,
            "acceptance_sha256": self.acceptance_sha256,
            "time_basis_policy": self.time_basis_policy,
            "manifest_sha256": self.manifest_sha256,
            "receipt_sha256": self.receipt_sha256,
            "raw_source_sha256": self.raw_source_sha256,
            "transport_sha256": self.transport_sha256,
            "record_count": self.record_count,
            "available_hour": _datetime_text(self.available_hour),
            "availability_basis": list(self.availability_basis),
            "source_batch_started_at": _datetime_text(self.source_batch_started_at),
            "first_persisted_at": _datetime_text(self.first_persisted_at),
            "successful_batch_completed_at": _datetime_text(
                self.successful_batch_completed_at
            ),
        }


@dataclass(frozen=True, slots=True)
class DailyMonthlyRevenueCohortPin:
    """綁定期間、用途與所需市場批次的 hash-addressed cohort。"""

    period: str
    required_markets: tuple[str, ...]
    market_pins: tuple[DailyMonthlyRevenueMarketSnapshotPin, ...]
    available_hour: datetime
    time_basis_policy: str = DAILY_SOURCE_TIME_BASIS_POLICY
    cohort_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _validate_period(self.period)
        markets = _require_string_tuple(self.required_markets, "required_markets")
        expected_market_order = tuple(
            market for market in _MARKET_ORDER if market in markets
        )
        if (
            not markets
            or markets != expected_market_order
            or any(market not in _MARKET_ORDER for market in markets)
        ):
            raise DailyMonthlyRevenueCohortError("cohort_required_markets_invalid")
        if not isinstance(self.market_pins, tuple) or not all(
            isinstance(item, DailyMonthlyRevenueMarketSnapshotPin)
            for item in self.market_pins
        ):
            raise DailyMonthlyRevenueCohortError("cohort_market_pins_invalid")
        pin_markets = tuple(item.market for item in self.market_pins)
        if pin_markets != markets:
            raise DailyMonthlyRevenueCohortError("cohort_market_pins_incomplete_or_unordered")
        for market_pin in self.market_pins:
            if market_pin.period != self.period:
                raise DailyMonthlyRevenueCohortError("cohort_period_market_pin_mismatch")
            if market_pin.time_basis_policy != self.time_basis_policy:
                raise DailyMonthlyRevenueCohortError("cohort_time_basis_market_pin_mismatch")
        if self.time_basis_policy != DAILY_SOURCE_TIME_BASIS_POLICY:
            raise DailyMonthlyRevenueCohortError("cohort_time_basis_policy_unsupported")
        shared_scopes = tuple(
            (
                item.scope.dataset_id,
                item.scope.source_id,
                item.scope.parser_version,
                item.scope.source_schema_version,
                item.scope.unit,
                item.scope.intended_use,
            )
            for item in self.market_pins
        )
        if len(set(shared_scopes)) != 1:
            raise DailyMonthlyRevenueCohortError("cohort_market_scopes_not_equivalent")
        object.__setattr__(self, "required_markets", markets)
        object.__setattr__(self, "available_hour", _to_taipei(self.available_hour, "available_hour"))
        expected_hour = max(item.available_hour for item in self.market_pins)
        if self.available_hour != expected_hour:
            raise DailyMonthlyRevenueCohortError("cohort_available_hour_not_market_max")
        if self.available_hour != self.available_hour.replace(
            minute=0, second=0, microsecond=0
        ):
            raise DailyMonthlyRevenueCohortError("cohort_available_hour_not_exact_hour")
        object.__setattr__(self, "cohort_sha256", _sha256(_canonical_json_bytes(self._core_dict())))
        if len(_canonical_json_bytes(self.to_dict())) > DAILY_MONTHLY_REVENUE_COHORT_ENVELOPE_BYTES:
            raise DailyMonthlyRevenueCohortError("cohort_pin_exceeds_size_limit")

    def for_market(self, market: str) -> DailyMonthlyRevenueMarketSnapshotPin:
        """只回傳 cohort 明示包含的市場 pin；不猜測或 fallback。"""

        if not isinstance(market, str):
            raise DailyMonthlyRevenueCohortError("cohort_market_key_invalid")
        for item in self.market_pins:
            if item.market == market:
                return item
        raise DailyMonthlyRevenueCohortError(f"cohort_market_not_required:{market}")

    def _core_dict(self) -> dict[str, object]:
        return {
            "schema_version": DAILY_MONTHLY_REVENUE_COHORT_SCHEMA,
            "period": self.period,
            "required_markets": list(self.required_markets),
            "market_pins": [item.to_dict() for item in self.market_pins],
            "available_hour": _datetime_text(self.available_hour),
            "time_basis_policy": self.time_basis_policy,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._core_dict(), "cohort_sha256": self.cohort_sha256}

    def to_json(self) -> str:
        return _canonical_json_bytes(self.to_dict()).decode("utf-8")

    @classmethod
    def from_dict(cls, value: object) -> DailyMonthlyRevenueCohortPin:
        if not isinstance(value, dict) or set(value) != {
            "schema_version",
            "period",
            "required_markets",
            "market_pins",
            "available_hour",
            "time_basis_policy",
            "cohort_sha256",
        }:
            raise DailyMonthlyRevenueCohortError("cohort_pin_fields_invalid")
        if value.get("schema_version") != DAILY_MONTHLY_REVENUE_COHORT_SCHEMA:
            raise DailyMonthlyRevenueCohortError("cohort_pin_schema_unsupported")
        supplied_hash = _require_hash(value.get("cohort_sha256"), "cohort_sha256")
        raw_markets = value.get("required_markets")
        raw_pins = value.get("market_pins")
        if not isinstance(raw_markets, list) or not isinstance(raw_pins, list):
            raise DailyMonthlyRevenueCohortError("cohort_pin_market_fields_invalid")
        pin = cls(
            period=_require_text(value.get("period"), "period"),
            required_markets=tuple(_require_text(item, "required_market") for item in raw_markets),
            market_pins=tuple(_market_pin_from_dict(item) for item in raw_pins),
            available_hour=_parse_datetime(value.get("available_hour"), "available_hour"),
            time_basis_policy=_require_text(
                value.get("time_basis_policy"), "time_basis_policy"
            ),
        )
        if pin.cohort_sha256 != supplied_hash:
            raise DailyMonthlyRevenueCohortError("cohort_pin_sha256_mismatch")
        return pin

    @classmethod
    def from_json(cls, value: str | bytes) -> DailyMonthlyRevenueCohortPin:
        if isinstance(value, bytes):
            if len(value) > DAILY_MONTHLY_REVENUE_COHORT_ENVELOPE_BYTES:
                raise DailyMonthlyRevenueCohortError("cohort_pin_exceeds_size_limit")
            try:
                text = value.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                raise DailyMonthlyRevenueCohortError("cohort_pin_not_utf8") from exc
        elif isinstance(value, str):
            try:
                encoded = value.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise DailyMonthlyRevenueCohortError("cohort_pin_not_utf8") from exc
            if len(encoded) > DAILY_MONTHLY_REVENUE_COHORT_ENVELOPE_BYTES:
                raise DailyMonthlyRevenueCohortError("cohort_pin_exceeds_size_limit")
            text = value
        else:
            raise DailyMonthlyRevenueCohortError("cohort_pin_json_type_invalid")
        try:
            decoded = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
        except (json.JSONDecodeError, DailyMonthlyRevenueCohortError, RecursionError) as exc:
            if isinstance(exc, DailyMonthlyRevenueCohortError):
                raise
            raise DailyMonthlyRevenueCohortError("cohort_pin_json_invalid") from exc
        pin = cls.from_dict(decoded)
        if pin.to_json() != text:
            raise DailyMonthlyRevenueCohortError("cohort_pin_json_not_canonical")
        return pin


def build_daily_monthly_revenue_cohort_pin(
    *,
    period: str,
    required_markets: Sequence[str],
    batch_ids: Mapping[str, str],
    readers: Mapping[str, DailySourceSnapshotFileReader],
) -> DailyMonthlyRevenueCohortPin:
    """只以 caller 明示的 trusted reader 與 exact batch 發行完整 cohort。"""

    _validate_period(period)
    markets = _canonical_required_markets(required_markets)
    if not isinstance(batch_ids, Mapping) or set(batch_ids) != set(markets):
        raise DailyMonthlyRevenueCohortError("cohort_batch_ids_incomplete_or_extra")
    if not isinstance(readers, Mapping) or set(readers) != set(markets):
        raise DailyMonthlyRevenueCohortError("cohort_readers_incomplete_or_extra")
    market_pins: list[DailyMonthlyRevenueMarketSnapshotPin] = []
    for market in markets:
        reader = readers[market]
        if not isinstance(reader, DailySourceSnapshotFileReader):
            raise DailyMonthlyRevenueCohortError(f"cohort_reader_type_invalid:{market}")
        root, acceptance = _capture_reader_configuration(reader, market)
        if acceptance.scope.market != market:
            raise DailyMonthlyRevenueCohortError(f"cohort_reader_market_mismatch:{market}")
        batch_id = _require_batch_id(batch_ids[market])
        pinned_reader = DailySourceSnapshotFileReader(
            root, trusted_acceptance=acceptance
        )
        snapshot = pinned_reader.read_snapshot(batch_id, expected_scope=acceptance.scope)
        market_pins.append(
            _market_pin_from_snapshot(
                snapshot=snapshot,
                market=market,
                period=period,
                expected_acceptance=acceptance,
            )
        )
    frozen_market_pins = tuple(market_pins)
    return DailyMonthlyRevenueCohortPin(
        period=period,
        required_markets=markets,
        market_pins=frozen_market_pins,
        available_hour=max(item.available_hour for item in frozen_market_pins),
    )


def write_daily_monthly_revenue_cohort_pin_create_only(
    root: Path | str,
    pin: DailyMonthlyRevenueCohortPin,
) -> Path:
    """在 caller 指定的目錄以 hash 檔名 create-only 保存小型 pin。"""

    base = _require_absolute_root(root)
    if not isinstance(pin, DailyMonthlyRevenueCohortPin):
        raise DailyMonthlyRevenueCohortError("cohort_pin_type_invalid")
    payload = pin.to_json().encode("utf-8")
    if len(payload) > DAILY_MONTHLY_REVENUE_COHORT_ENVELOPE_BYTES:
        raise DailyMonthlyRevenueCohortError("cohort_pin_exceeds_size_limit")
    base.mkdir(parents=True, exist_ok=True)
    try:
        resolved_base = base.resolve(strict=True)
    except OSError as exc:
        raise DailyMonthlyRevenueCohortError("cohort_root_unavailable") from exc
    if base.is_symlink():
        raise DailyMonthlyRevenueCohortError("cohort_root_is_symlink")
    target = resolved_base / f"{pin.cohort_sha256}.json"
    if target.is_symlink():
        raise DailyMonthlyRevenueCohortError("cohort_pin_file_is_symlink")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        descriptor = os.open(target, flags, 0o600)
    except FileExistsError as exc:
        raise DailyMonthlyRevenueCohortError("cohort_pin_create_only_conflict") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            written = handle.write(payload)
            if written != len(payload):
                raise DailyMonthlyRevenueCohortError("cohort_pin_short_write")
            handle.flush()
            os.fsync(handle.fileno())
    except DailyMonthlyRevenueCohortError:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    except OSError as exc:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise DailyMonthlyRevenueCohortError("cohort_pin_write_failed") from exc
    return target


def read_daily_monthly_revenue_cohort_pin(
    root: Path | str,
    cohort_sha256: str,
    *,
    expected_cohort_sha256: str,
) -> DailyMonthlyRevenueCohortPin:
    """只讀明確 hash 檔，並要求呼叫端另提供同一 hash 信任錨點。"""

    selected_hash = _require_hash(cohort_sha256, "cohort_sha256")
    expected_hash = _require_hash(expected_cohort_sha256, "expected_cohort_sha256")
    if selected_hash != expected_hash:
        raise DailyMonthlyRevenueCohortError("cohort_pin_external_hash_mismatch")
    base = _require_absolute_root(root)
    try:
        resolved_base = base.resolve(strict=True)
    except OSError as exc:
        raise DailyMonthlyRevenueCohortError("cohort_pin_root_not_found") from exc
    if base.is_symlink():
        raise DailyMonthlyRevenueCohortError("cohort_root_is_symlink")
    path = resolved_base / f"{selected_hash}.json"
    if path.is_symlink():
        raise DailyMonthlyRevenueCohortError("cohort_pin_file_is_symlink")
    try:
        if path.lstat().st_size > DAILY_MONTHLY_REVENUE_COHORT_ENVELOPE_BYTES:
            raise DailyMonthlyRevenueCohortError("cohort_pin_exceeds_size_limit")
        payload = path.read_bytes()
    except DailyMonthlyRevenueCohortError:
        raise
    except OSError as exc:
        raise DailyMonthlyRevenueCohortError("cohort_pin_not_found") from exc
    if len(payload) > DAILY_MONTHLY_REVENUE_COHORT_ENVELOPE_BYTES:
        raise DailyMonthlyRevenueCohortError("cohort_pin_exceeds_size_limit")
    pin = DailyMonthlyRevenueCohortPin.from_json(payload)
    if pin.cohort_sha256 != selected_hash:
        raise DailyMonthlyRevenueCohortError("cohort_pin_path_hash_mismatch")
    return pin


class DailyMonthlyRevenueCohortReader:
    """以固定 root/接受錨點重建底層 readers 的全市場重驗 port。"""

    __slots__ = (
        "_pin",
        "_expected_cohort_sha256",
        "_roots",
        "_acceptances",
        "_sealed",
    )

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("cohort reader configuration is immutable")
        object.__setattr__(self, name, value)

    def __init__(
        self,
        *,
        pin: DailyMonthlyRevenueCohortPin,
        market_readers: Mapping[str, DailySourceSnapshotFileReader],
        expected_cohort_sha256: str,
    ) -> None:
        if not isinstance(pin, DailyMonthlyRevenueCohortPin):
            raise DailyMonthlyRevenueCohortError("cohort_reader_pin_type_invalid")
        expected_hash = _require_hash(expected_cohort_sha256, "expected_cohort_sha256")
        if pin.cohort_sha256 != expected_hash:
            raise DailyMonthlyRevenueCohortError("cohort_reader_external_hash_mismatch")
        if not isinstance(market_readers, Mapping) or set(market_readers) != set(
            pin.required_markets
        ):
            raise DailyMonthlyRevenueCohortError("cohort_reader_markets_incomplete_or_extra")
        roots: dict[str, Path] = {}
        acceptances: dict[str, DailySourceUseAcceptance] = {}
        for market in pin.required_markets:
            reader = market_readers[market]
            if not isinstance(reader, DailySourceSnapshotFileReader):
                raise DailyMonthlyRevenueCohortError(f"cohort_reader_type_invalid:{market}")
            root, acceptance = _capture_reader_configuration(reader, market)
            market_pin = pin.for_market(market)
            if acceptance.scope != market_pin.scope:
                raise DailyMonthlyRevenueCohortError(f"cohort_trusted_scope_mismatch:{market}")
            if acceptance.acceptance_id != market_pin.acceptance_id:
                raise DailyMonthlyRevenueCohortError(f"cohort_trusted_acceptance_mismatch:{market}")
            if _sha256(_canonical_json_bytes(acceptance.to_dict())) != market_pin.acceptance_sha256:
                raise DailyMonthlyRevenueCohortError(f"cohort_trusted_acceptance_hash_mismatch:{market}")
            roots[market] = root
            acceptances[market] = acceptance
        self._pin = pin
        self._expected_cohort_sha256 = expected_hash
        self._roots = MappingProxyType(roots)
        self._acceptances = MappingProxyType(acceptances)
        self._sealed = True

    @property
    def pin(self) -> DailyMonthlyRevenueCohortPin:
        """回傳唯讀 cohort pin。"""

        return self._pin

    @property
    def available_hour(self) -> datetime:
        """回傳所有 required market 的共同可用小時。"""

        return self._pin.available_hour

    def verify_cohort(self) -> tuple[DailySourceSnapshot, ...]:
        """無論呼叫端要讀哪個市場，都重新讀驗所有 required batches。"""

        snapshots: list[DailySourceSnapshot] = []
        market_pins: list[DailyMonthlyRevenueMarketSnapshotPin] = []
        for market in self._pin.required_markets:
            market_pin = self._pin.for_market(market)
            reader = DailySourceSnapshotFileReader(
                self._roots[market], trusted_acceptance=self._acceptances[market]
            )
            snapshot = reader.read_snapshot(
                market_pin.batch_id,
                expected_scope=market_pin.scope,
            )
            actual_pin = _market_pin_from_snapshot(
                snapshot=snapshot,
                market=market,
                period=self._pin.period,
                expected_acceptance=self._acceptances[market],
            )
            if actual_pin != market_pin:
                raise DailyMonthlyRevenueCohortError(f"cohort_market_pin_mismatch:{market}")
            snapshots.append(snapshot)
            market_pins.append(actual_pin)
        recomputed_hour = max(item.available_hour for item in market_pins)
        recomputed_pin = DailyMonthlyRevenueCohortPin(
            period=self._pin.period,
            required_markets=self._pin.required_markets,
            market_pins=tuple(market_pins),
            available_hour=recomputed_hour,
        )
        if (
            recomputed_hour != self._pin.available_hour
            or recomputed_pin.cohort_sha256 != self._pin.cohort_sha256
            or recomputed_pin.cohort_sha256 != self._expected_cohort_sha256
        ):
            raise DailyMonthlyRevenueCohortError("cohort_recomputed_identity_mismatch")
        return tuple(snapshots)

    def read_snapshot(
        self,
        batch_id: str,
        *,
        expected_scope: DailySourceUseScope,
    ) -> DailySourceSnapshot:
        """依 expected scope.market 精確選 pin，並先重驗整組 cohort。"""

        if not isinstance(expected_scope, DailySourceUseScope):
            raise DailyMonthlyRevenueCohortError("cohort_expected_scope_type_invalid")
        market = expected_scope.market
        market_pin = self._pin.for_market(market)
        if batch_id != market_pin.batch_id:
            raise DailyMonthlyRevenueCohortError(f"cohort_batch_id_mismatch:{market}")
        if expected_scope != market_pin.scope:
            raise DailyMonthlyRevenueCohortError(f"cohort_expected_scope_mismatch:{market}")
        snapshots = self.verify_cohort()
        for snapshot in snapshots:
            if snapshot.scope.market == market:
                return snapshot
        raise DailyMonthlyRevenueCohortError(f"cohort_snapshot_missing_after_verify:{market}")


def _market_pin_from_snapshot(
    *,
    snapshot: DailySourceSnapshot,
    market: str,
    period: str,
    expected_acceptance: DailySourceUseAcceptance,
) -> DailyMonthlyRevenueMarketSnapshotPin:
    if not isinstance(snapshot, DailySourceSnapshot):
        raise DailyMonthlyRevenueCohortError(f"cohort_snapshot_type_invalid:{market}")
    if snapshot.scope != expected_acceptance.scope or snapshot.scope.market != market:
        raise DailyMonthlyRevenueCohortError(f"cohort_snapshot_scope_mismatch:{market}")
    if snapshot.use_acceptance != expected_acceptance:
        raise DailyMonthlyRevenueCohortError(f"cohort_snapshot_acceptance_mismatch:{market}")
    if snapshot.use_acceptance.time_basis_policy != DAILY_SOURCE_TIME_BASIS_POLICY:
        raise DailyMonthlyRevenueCohortError(f"cohort_snapshot_time_policy_mismatch:{market}")
    if snapshot.validation.quality_status != "pass":
        raise DailyMonthlyRevenueCohortError(f"cohort_snapshot_quality_not_pass:{market}")
    if not snapshot.records or any(
        record.market != market or record.period != period or record.unit != snapshot.scope.unit
        for record in snapshot.records
    ):
        raise DailyMonthlyRevenueCohortError(f"cohort_snapshot_record_identity_mismatch:{market}")
    capture = snapshot.transport_capture
    if capture is None:
        raise DailyMonthlyRevenueCohortError(f"cohort_snapshot_transport_missing:{market}")
    availability = tuple(snapshot.availability_for(record) for record in snapshot.records)
    available_hour = max(item[0] for item in availability)
    basis = tuple(sorted({item[1] for item in availability}))
    return DailyMonthlyRevenueMarketSnapshotPin(
        market=market,
        period=period,
        batch_id=snapshot.batch_id,
        scope=snapshot.scope,
        acceptance_id=snapshot.use_acceptance.acceptance_id,
        acceptance_sha256=_sha256(
            _canonical_json_bytes(snapshot.use_acceptance.to_dict())
        ),
        time_basis_policy=snapshot.use_acceptance.time_basis_policy,
        manifest_sha256=snapshot.manifest_sha256,
        receipt_sha256=snapshot.receipt_sha256,
        raw_source_sha256=snapshot.raw_source_sha256,
        transport_sha256=capture.transport_sha256,
        record_count=len(snapshot.records),
        available_hour=available_hour,
        availability_basis=basis,
        source_batch_started_at=snapshot.source_batch_started_at,
        first_persisted_at=snapshot.first_persisted_at,
        successful_batch_completed_at=snapshot.successful_batch_completed_at,
    )


def _market_pin_from_dict(value: object) -> DailyMonthlyRevenueMarketSnapshotPin:
    expected_keys = {
        "market",
        "period",
        "batch_id",
        "scope",
        "acceptance_id",
        "acceptance_sha256",
        "time_basis_policy",
        "manifest_sha256",
        "receipt_sha256",
        "raw_source_sha256",
        "transport_sha256",
        "record_count",
        "available_hour",
        "availability_basis",
        "source_batch_started_at",
        "first_persisted_at",
        "successful_batch_completed_at",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise DailyMonthlyRevenueCohortError("cohort_market_pin_fields_invalid")
    raw_basis = value.get("availability_basis")
    if not isinstance(raw_basis, list):
        raise DailyMonthlyRevenueCohortError("cohort_market_pin_basis_invalid")
    record_count = value.get("record_count")
    if type(record_count) is not int:
        raise DailyMonthlyRevenueCohortError("cohort_record_count_invalid")
    return DailyMonthlyRevenueMarketSnapshotPin(
        market=_require_text(value.get("market"), "market"),
        period=_require_text(value.get("period"), "period"),
        batch_id=_require_batch_id(value.get("batch_id")),
        scope=_scope_from_dict(value.get("scope")),
        acceptance_id=_require_text(value.get("acceptance_id"), "acceptance_id"),
        acceptance_sha256=_require_hash(value.get("acceptance_sha256"), "acceptance_sha256"),
        time_basis_policy=_require_text(value.get("time_basis_policy"), "time_basis_policy"),
        manifest_sha256=_require_hash(value.get("manifest_sha256"), "manifest_sha256"),
        receipt_sha256=_require_hash(value.get("receipt_sha256"), "receipt_sha256"),
        raw_source_sha256=_require_hash(value.get("raw_source_sha256"), "raw_source_sha256"),
        transport_sha256=_require_hash(value.get("transport_sha256"), "transport_sha256"),
        record_count=record_count,
        available_hour=_parse_datetime(value.get("available_hour"), "available_hour"),
        availability_basis=tuple(_require_text(item, "availability_basis") for item in raw_basis),
        source_batch_started_at=_parse_datetime(
            value.get("source_batch_started_at"), "source_batch_started_at"
        ),
        first_persisted_at=_parse_datetime(
            value.get("first_persisted_at"), "first_persisted_at"
        ),
        successful_batch_completed_at=_parse_datetime(
            value.get("successful_batch_completed_at"), "successful_batch_completed_at"
        ),
    )


def _scope_from_dict(value: object) -> DailySourceUseScope:
    fields = {
        "dataset_id",
        "source_id",
        "market",
        "parser_version",
        "source_schema_version",
        "unit",
        "intended_use",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise DailyMonthlyRevenueCohortError("cohort_scope_fields_invalid")
    return DailySourceUseScope(**value)


def _copy_acceptance(value: object) -> DailySourceUseAcceptance:
    if not isinstance(value, DailySourceUseAcceptance):
        raise DailyMonthlyRevenueCohortError("cohort_trusted_acceptance_required")
    return DailySourceUseAcceptance(
        scope=DailySourceUseScope(**value.scope.to_dict()),
        acceptance_id=value.acceptance_id,
        accepted_at=value.accepted_at,
        official_source_endpoint=value.official_source_endpoint,
        document_chain=tuple(value.document_chain),
        acceptance_evidence_ref=value.acceptance_evidence_ref,
        authorization_scope=value.authorization_scope,
        time_basis_policy=value.time_basis_policy,
    )


def _capture_reader_configuration(
    reader: DailySourceSnapshotFileReader,
    market: str,
) -> tuple[Path, DailySourceUseAcceptance]:
    acceptance = _copy_acceptance(getattr(reader, "trusted_acceptance", None))
    raw_root = getattr(reader, "root", None)
    if not isinstance(raw_root, Path) or not raw_root.is_absolute():
        raise DailyMonthlyRevenueCohortError(f"cohort_reader_root_invalid:{market}")
    try:
        fixed_root = raw_root.resolve(strict=False)
    except OSError as exc:
        raise DailyMonthlyRevenueCohortError(f"cohort_reader_root_invalid:{market}") from exc
    if not fixed_root.is_absolute():
        raise DailyMonthlyRevenueCohortError(f"cohort_reader_root_invalid:{market}")
    return fixed_root, acceptance


def _canonical_required_markets(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise DailyMonthlyRevenueCohortError("cohort_required_markets_invalid")
    received = tuple(_require_text(item, "required_market") for item in values)
    if not received or len(received) != len(set(received)):
        raise DailyMonthlyRevenueCohortError("cohort_required_markets_invalid")
    if any(market not in _MARKET_ORDER for market in received):
        raise DailyMonthlyRevenueCohortError("cohort_market_unsupported")
    return tuple(market for market in _MARKET_ORDER if market in received)


def _validate_period(value: object) -> None:
    if not isinstance(value, str):
        raise DailyMonthlyRevenueCohortError("cohort_period_invalid")
    match = _PERIOD_RE.fullmatch(value)
    if match is None or not 1 <= int(match.group(2)) <= 12:
        raise DailyMonthlyRevenueCohortError("cohort_period_invalid")


def _require_string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise DailyMonthlyRevenueCohortError(f"cohort_{label}_must_be_tuple")
    result = tuple(_require_text(item, label) for item in value)
    if len(result) != len(set(result)):
        raise DailyMonthlyRevenueCohortError(f"cohort_{label}_duplicate")
    return result


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise DailyMonthlyRevenueCohortError(f"cohort_{label}_missing")
    return value


def _require_batch_id(value: object) -> str:
    if not isinstance(value, str) or not _BATCH_ID_RE.fullmatch(value):
        raise DailyMonthlyRevenueCohortError("cohort_batch_id_invalid")
    return value


def _require_hash(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise DailyMonthlyRevenueCohortError(f"cohort_{label}_invalid")
    return value


def _to_taipei(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DailyMonthlyRevenueCohortError(f"cohort_{label}_must_be_aware")
    return value.astimezone(_TAIPEI)


def _datetime_text(value: datetime) -> str:
    return _to_taipei(value, "timestamp").isoformat(timespec="microseconds")


def _ceil_hour(value: datetime) -> datetime:
    local = _to_taipei(value, "available_hour_basis")
    exact_hour = local.replace(minute=0, second=0, microsecond=0)
    return exact_hour if local == exact_hour else exact_hour + timedelta(hours=1)


def _parse_datetime(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise DailyMonthlyRevenueCohortError(f"cohort_{label}_timestamp_missing")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise DailyMonthlyRevenueCohortError(f"cohort_{label}_timestamp_invalid") from exc
    taipei = _to_taipei(parsed, label)
    if _datetime_text(taipei) != value:
        raise DailyMonthlyRevenueCohortError(f"cohort_{label}_timestamp_not_canonical")
    return taipei


def _canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DailyMonthlyRevenueCohortError("cohort_pin_duplicate_json_key")
        result[key] = value
    return result


def _require_absolute_root(root: Path | str) -> Path:
    if not isinstance(root, (Path, str)) or not str(root).strip():
        raise DailyMonthlyRevenueCohortError("cohort_root_required")
    path = Path(root).expanduser()
    if not path.is_absolute():
        raise DailyMonthlyRevenueCohortError("cohort_root_must_be_absolute")
    return path


__all__ = (
    "DAILY_MONTHLY_REVENUE_COHORT_ENVELOPE_BYTES",
    "DAILY_MONTHLY_REVENUE_COHORT_SCHEMA",
    "DailyMonthlyRevenueCohortError",
    "DailyMonthlyRevenueCohortPin",
    "DailyMonthlyRevenueCohortReader",
    "DailyMonthlyRevenueMarketSnapshotPin",
    "build_daily_monthly_revenue_cohort_pin",
    "read_daily_monthly_revenue_cohort_pin",
    "write_daily_monthly_revenue_cohort_pin_create_only",
)
