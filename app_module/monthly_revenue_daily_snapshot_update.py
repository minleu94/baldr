"""以已保存的 MOPS response 建立並重讀每日月營收來源快照。"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from data_module.current_fundamental_snapshots import (
    MONTHLY_NORMALIZER_VERSION,
    MONTHLY_SNAPSHOT_SOURCE,
    MONTHLY_YOY_COMPARATOR_ITEM_CODE,
    _derived_monthly_source_version,
    _derived_monthly_yoy_comparator_version,
    _monthly_source_available_at,
    normalize_current_observation,
)
from data_module.daily_source_snapshot import (
    DAILY_SOURCE_SNAPSHOT_DATASET_ID,
    DAILY_SOURCE_SNAPSHOT_SOURCE_ID,
    DailySourceBatchValidation,
    DailySourceRecordAvailability,
    DailySourceSnapshot,
    DailySourceSnapshotError,
    DailySourceSnapshotFileReader,
    DailySourceSnapshotRecord,
    DailySourceTransportCapture,
    DailySourceUseAcceptance,
    DailySourceUseScope,
    write_daily_source_quarantine_candidate,
    write_daily_source_snapshot,
)
from data_module.monthly_revenue_daily_snapshot_preparation import (
    PreparedDailyMonthlyRevenue,
    prepare_daily_monthly_revenue_capture,
)


_TAIPEI = ZoneInfo("Asia/Taipei")


class DailyMonthlyRevenueSnapshotUpdateError(ValueError):
    """daily producer 的具名拒絕原因。"""


class _DailySnapshotCancelled(DailyMonthlyRevenueSnapshotUpdateError):
    """在不可撤回發布前觀測到取消。"""


@dataclass(frozen=True, slots=True)
class DailyMonthlyRevenueSnapshotReadStatus:
    """對 caller 指定 batch 的唯讀、可信錨點狀態。"""

    status: str
    batch_id: str
    period: str
    scope: DailySourceUseScope
    record_count: int = 0
    raw_source_sha256: str | None = None
    transport_sha256: str | None = None
    manifest_sha256: str | None = None
    receipt_sha256: str | None = None
    first_persisted_at: datetime | None = None
    successful_batch_completed_at: datetime | None = None
    record_availability: tuple[DailySourceRecordAvailability, ...] = ()
    diagnostics: tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        """只有新 contract 的完整 transport batch 才算 available。"""

        return self.status == "ready"


@dataclass(frozen=True, slots=True)
class DailyMonthlyRevenueSnapshotUpdateResult:
    """每日快照發布結果；失敗時仍回報隔離路徑與具名原因。"""

    status: str
    batch_id: str
    period: str
    scope: DailySourceUseScope
    snapshot_status: DailyMonthlyRevenueSnapshotReadStatus | None = None
    raw_source_sha256: str | None = None
    transport_sha256: str | None = None
    normalized_observation_count: int = 0
    quarantine_path: str | None = None
    diagnostics: tuple[str, ...] = ()

    @property
    def success(self) -> bool:
        """讀回 public manifest/receipt 成功才回報發布成功。"""

        return (
            self.status == "ready"
            and self.snapshot_status is not None
            and self.snapshot_status.available
        )


def publish_daily_monthly_revenue_snapshot(
    *,
    root: Path | str,
    capture: DailySourceTransportCapture,
    period: str,
    batch_id: str,
    source_batch_started_at: datetime,
    use_acceptance: DailySourceUseAcceptance,
    scope: DailySourceUseScope,
    clock: Callable[[], datetime],
    check_cancel: Callable[[], bool],
) -> DailyMonthlyRevenueSnapshotUpdateResult:
    """驗證已保存 response、create-only 發布，再以新 reader instance 精確讀回。

    此入口不抓取網路、不建立用途接受、不挑 latest，也不寫入 SQLite。
    `root` 是 caller 明確選擇的 snapshot/quarantine 根目錄。取消檢查交由
    control callback，clock 僅提供實際 aware datetime；進入 writer commit 後，
    writer 的最後 pre-rename 檢查是此 cooperative cancel 的發布邊界。
    """

    raw_hash: str | None = None
    transport_hash: str | None = None
    prepared: PreparedDailyMonthlyRevenue | None = None
    normalized_count = 0
    started: datetime | None = None
    selected_scope = scope if isinstance(scope, DailySourceUseScope) else _fallback_scope()

    try:
        if not isinstance(capture, DailySourceTransportCapture):
            raise DailyMonthlyRevenueSnapshotUpdateError(
                "daily_monthly_capture_type_invalid"
            )
        raw_hash = hashlib.sha256(capture.canonical_source_bytes).hexdigest()
        transport_hash = capture.transport_sha256
        if not isinstance(scope, DailySourceUseScope):
            raise DailyMonthlyRevenueSnapshotUpdateError(
                "daily_monthly_scope_type_invalid"
            )
        if not isinstance(use_acceptance, DailySourceUseAcceptance):
            raise DailyMonthlyRevenueSnapshotUpdateError(
                "daily_monthly_trusted_acceptance_type_invalid"
            )
        if use_acceptance.scope != scope:
            raise DailyMonthlyRevenueSnapshotUpdateError(
                "daily_monthly_acceptance_scope_mismatch"
            )
        started = _require_aware_taipei(
            source_batch_started_at, "source_batch_started_at"
        )
        if use_acceptance.accepted_at > started:
            raise DailyMonthlyRevenueSnapshotUpdateError(
                "daily_monthly_acceptance_after_batch_start"
            )
        _raise_if_cancelled(check_cancel, "before_preparation")

        prepared = prepare_daily_monthly_revenue_capture(
            capture=capture,
            scope=scope,
            period=period,
            validation_id=f"daily-monthly:{batch_id}",
        )
        if prepared.canonical_source_bytes != capture.canonical_source_bytes:
            raise DailyMonthlyRevenueSnapshotUpdateError(
                "daily_monthly_canonical_payload_mismatch"
            )
        _raise_if_cancelled(check_cancel, "after_preparation")

        observed_at = _call_clock(clock, "normalization_observed_at")
        normalized_rows = _normalize_prepared_rows(
            prepared,
            scope=scope,
            period=period,
            observed_at=observed_at,
        )
        normalized_count = len(normalized_rows)
        _raise_if_cancelled(check_cancel, "before_snapshot_writer")

        def writer_cancel_check() -> None:
            _raise_if_cancelled(check_cancel, "snapshot_writer_pre_publish")

        write_daily_source_snapshot(
            root,
            batch_id=batch_id,
            scope=scope,
            use_acceptance=use_acceptance,
            source_batch_started_at=started,
            raw_source_bytes=prepared.canonical_source_bytes,
            records=prepared.records,
            validation=prepared.validation,
            transport_capture=capture,
            clock=lambda: _call_clock(clock, "snapshot_writer_clock"),
            quarantine_root=root,
            check_cancel=writer_cancel_check,
        )

        read_status = read_daily_monthly_revenue_snapshot_status(
            root,
            batch_id=batch_id,
            period=period,
            expected_scope=scope,
            trusted_acceptance=use_acceptance,
        )
        if not read_status.available:
            reason = (
                "daily_monthly_public_reader_rejected_after_publish:"
                + ";".join(read_status.diagnostics)
            )
            quarantine_path = _quarantine_failure(
                root=root,
                batch_id=batch_id,
                canonical_bytes=prepared.canonical_source_bytes,
                capture=capture,
                reason=reason,
                scope=scope,
                started=started,
                validation=prepared.validation,
            )
            return DailyMonthlyRevenueSnapshotUpdateResult(
                status="quarantined",
                batch_id=batch_id,
                period=period,
                scope=scope,
                snapshot_status=read_status,
                raw_source_sha256=raw_hash,
                transport_sha256=transport_hash,
                normalized_observation_count=normalized_count,
                quarantine_path=str(quarantine_path) if quarantine_path else None,
                diagnostics=(reason,),
            )

        return DailyMonthlyRevenueSnapshotUpdateResult(
            status="ready",
            batch_id=batch_id,
            period=period,
            scope=scope,
            snapshot_status=read_status,
            raw_source_sha256=raw_hash,
            transport_sha256=transport_hash,
            normalized_observation_count=normalized_count,
            diagnostics=(),
        )
    except Exception as exc:
        reason = _named_failure_reason(exc)
        quarantine_path = None
        if isinstance(capture, DailySourceTransportCapture):
            try:
                canonical_bytes = capture.canonical_source_bytes
            except (LookupError, UnicodeDecodeError, ValueError):
                canonical_bytes = b""
            if canonical_bytes:
                quarantine_path = _quarantine_failure(
                    root=root,
                    batch_id=batch_id,
                    canonical_bytes=canonical_bytes,
                    capture=capture,
                    reason=reason,
                    scope=(scope if isinstance(scope, DailySourceUseScope) else None),
                    started=started,
                    validation=(prepared.validation if prepared is not None else None),
                )
        return DailyMonthlyRevenueSnapshotUpdateResult(
            status=(
                "cancelled"
                if isinstance(exc, _DailySnapshotCancelled)
                else "quarantined"
                if quarantine_path is not None
                else "unavailable"
            ),
            batch_id=batch_id if isinstance(batch_id, str) else "",
            period=period if isinstance(period, str) else "",
            scope=selected_scope,
            raw_source_sha256=raw_hash,
            transport_sha256=transport_hash,
            normalized_observation_count=normalized_count,
            quarantine_path=str(quarantine_path) if quarantine_path else None,
            diagnostics=(reason,),
        )


def read_daily_monthly_revenue_snapshot_status(
    root: Path | str,
    *,
    batch_id: str,
    period: str,
    expected_scope: DailySourceUseScope,
    trusted_acceptance: DailySourceUseAcceptance,
) -> DailyMonthlyRevenueSnapshotReadStatus:
    """建立新的 file reader，讀 caller 精確指定的 batch，絕不選 latest。"""

    try:
        if not isinstance(expected_scope, DailySourceUseScope):
            raise DailyMonthlyRevenueSnapshotUpdateError(
                "daily_monthly_expected_scope_type_invalid"
            )
        if not isinstance(trusted_acceptance, DailySourceUseAcceptance):
            raise DailyMonthlyRevenueSnapshotUpdateError(
                "daily_monthly_trusted_acceptance_type_invalid"
            )
        if trusted_acceptance.scope != expected_scope:
            raise DailyMonthlyRevenueSnapshotUpdateError(
                "daily_monthly_trusted_acceptance_scope_mismatch"
            )
        reader = DailySourceSnapshotFileReader(
            root,
            trusted_acceptance=trusted_acceptance,
        )
        snapshot = reader.read_snapshot(
            batch_id,
            expected_scope=expected_scope,
        )
        _validate_read_snapshot(snapshot, batch_id=batch_id, period=period)
    except Exception as exc:
        return DailyMonthlyRevenueSnapshotReadStatus(
            status="unavailable",
            batch_id=batch_id if isinstance(batch_id, str) else "",
            period=period if isinstance(period, str) else "",
            scope=(expected_scope if isinstance(expected_scope, DailySourceUseScope) else _fallback_scope()),
            diagnostics=(_named_failure_reason(exc, prefix="daily_monthly_snapshot_read_rejected"),),
        )
    capture = snapshot.transport_capture
    assert capture is not None
    return DailyMonthlyRevenueSnapshotReadStatus(
        status="ready",
        batch_id=snapshot.batch_id,
        period=period,
        scope=snapshot.scope,
        record_count=len(snapshot.records),
        raw_source_sha256=snapshot.raw_source_sha256,
        transport_sha256=capture.transport_sha256,
        manifest_sha256=snapshot.manifest_sha256,
        receipt_sha256=snapshot.receipt_sha256,
        first_persisted_at=snapshot.first_persisted_at,
        successful_batch_completed_at=snapshot.successful_batch_completed_at,
        record_availability=snapshot.record_availability,
        diagnostics=(),
    )


def _validate_read_snapshot(
    snapshot: DailySourceSnapshot,
    *,
    batch_id: str,
    period: str,
) -> None:
    if snapshot.batch_id != batch_id:
        raise DailyMonthlyRevenueSnapshotUpdateError(
            "daily_monthly_snapshot_batch_id_mismatch"
        )
    if not snapshot.records or any(record.period != period for record in snapshot.records):
        raise DailyMonthlyRevenueSnapshotUpdateError(
            "daily_monthly_snapshot_period_mismatch"
        )
    if snapshot.transport_capture is None:
        raise DailyMonthlyRevenueSnapshotUpdateError(
            "daily_monthly_snapshot_transport_capture_missing"
        )
    if snapshot.validation.quality_status != "pass":
        raise DailyMonthlyRevenueSnapshotUpdateError(
            "daily_monthly_snapshot_validation_not_pass"
        )
    if len(snapshot.records) != len(snapshot.record_availability):
        raise DailyMonthlyRevenueSnapshotUpdateError(
            "daily_monthly_snapshot_availability_count_mismatch"
        )


def _normalize_prepared_rows(
    prepared: PreparedDailyMonthlyRevenue,
    *,
    scope: DailySourceUseScope,
    period: str,
    observed_at: datetime,
) -> tuple[dict[str, str], ...]:
    year, month = (int(part) for part in period.split("-"))
    period_end = date(year, month, monthrange(year, month)[1]).isoformat()
    source_available_at = _monthly_source_available_at(
        prepared.source_version,
        market=scope.market,
        period=period,
    )
    observed_text = observed_at.astimezone(timezone.utc).isoformat()
    normalized: list[dict[str, str]] = []
    record_by_code = {record.stock_code: record for record in prepared.records}
    for source_row in prepared.rows:
        stock_code = source_row["stock_code"]
        source_record = record_by_code.get(stock_code)
        if (
            source_record is None
            or source_record.market != scope.market
            or source_record.period != period
            or source_record.source_version != prepared.source_version
            or source_record.raw_source_sha256
            != hashlib.sha256(prepared.canonical_source_bytes).hexdigest()
            or source_record.unit != "TWD"
        ):
            raise DailyMonthlyRevenueSnapshotUpdateError(
                f"daily_monthly_prepared_record_identity_mismatch:{stock_code}"
            )
        amount = _finite_decimal(source_row.get("current_month_revenue"), "revenue")
        if amount is None:
            raise DailyMonthlyRevenueSnapshotUpdateError(
                f"daily_monthly_revenue_missing:{stock_code}"
            )
        twd_value = str(amount * Decimal(1000))
        current_source_version = _derived_monthly_source_version(
            prepared.source_version,
            stock_code=stock_code,
            period=period,
            value=twd_value,
            unit="TWD",
            source_available_at=source_available_at,
        )
        current_input = _current_observation_payload(
            stock_code=stock_code,
            market=scope.market,
            period=period,
            period_end=period_end,
            item_code="revenue",
            item_name="月營收:單月",
            value=twd_value,
            source_version=current_source_version,
            observed_at=observed_text,
            source_available_at=source_available_at,
        )
        current_normalized = normalize_current_observation(current_input)
        if (
            current_normalized["value"] != twd_value
            or current_normalized["unit"] != "TWD"
            or current_normalized["period_basis"] != "monthly_flow"
            or current_normalized["basis_verified"] != "1"
            or current_normalized["aggregate_feature_eligible"] != "0"
        ):
            raise DailyMonthlyRevenueSnapshotUpdateError(
                f"daily_monthly_current_value_normalization_mismatch:{stock_code}"
            )
        normalized.append(current_normalized)

        prior_amount = _finite_decimal(
            source_row.get("previous_year_month_revenue"),
            "previous_year_comparator",
            allow_empty=True,
        )
        if prior_amount is not None and prior_amount > 0:
            prior_period = f"{year - 1:04d}-{month:02d}"
            prior_end = date(
                year - 1,
                month,
                monthrange(year - 1, month)[1],
            ).isoformat()
            prior_value = str(prior_amount * Decimal(1000))
            comparator_source_version = _derived_monthly_yoy_comparator_version(
                prepared.source_version,
                stock_code=stock_code,
                source_period=period,
                comparator_period=prior_period,
                value=prior_value,
                unit="TWD",
                source_available_at=source_available_at,
            )
            comparator_input = _current_observation_payload(
                stock_code=stock_code,
                market=scope.market,
                period=prior_period,
                period_end=prior_end,
                item_code=MONTHLY_YOY_COMPARATOR_ITEM_CODE,
                item_name="same-report prior-year monthly revenue comparator",
                value=prior_value,
                source_version=comparator_source_version,
                observed_at=observed_text,
                source_available_at=source_available_at,
            )
            comparator_normalized = normalize_current_observation(comparator_input)
            if (
                comparator_normalized["value"] != prior_value
                or comparator_normalized["unit"] != "TWD"
                or comparator_normalized["period_basis"] != "monthly_flow"
                or comparator_normalized["basis_verified"] != "1"
                or comparator_normalized["aggregate_feature_eligible"] != "0"
            ):
                raise DailyMonthlyRevenueSnapshotUpdateError(
                    f"daily_monthly_comparator_normalization_mismatch:{stock_code}"
                )
            normalized.append(comparator_normalized)
    if len(normalized) < len(prepared.records):
        raise DailyMonthlyRevenueSnapshotUpdateError(
            "daily_monthly_normalized_record_count_below_source_rows"
        )
    return tuple(normalized)


def _current_observation_payload(
    *,
    stock_code: str,
    market: str,
    period: str,
    period_end: str,
    item_code: str,
    item_name: str,
    value: str,
    source_version: str,
    observed_at: str,
    source_available_at: str,
) -> dict[str, str]:
    return {
        "stock_code": stock_code,
        "kind": "monthly_revenue",
        "period": period,
        "as_of_date": period_end,
        "item_code": item_code,
        "item_name": item_name,
        "value": value,
        "unit": "TWD",
        "observed_at": observed_at,
        "source": MONTHLY_SNAPSHOT_SOURCE,
        "source_version": source_version,
        "market": market,
        "period_basis": "monthly_flow",
        "basis_verified": "1",
        "aggregate_feature_eligible": "0",
        "source_available_at": source_available_at,
    }


def _finite_decimal(
    value: object,
    label: str,
    *,
    allow_empty: bool = False,
) -> Decimal | None:
    text = str(value or "").strip().replace(",", "")
    if not text and allow_empty:
        return None
    try:
        amount = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise DailyMonthlyRevenueSnapshotUpdateError(
            f"daily_monthly_{label}_missing_or_invalid"
        ) from exc
    if not amount.is_finite():
        raise DailyMonthlyRevenueSnapshotUpdateError(
            f"daily_monthly_{label}_not_finite"
        )
    return amount


def _quarantine_failure(
    *,
    root: Path | str,
    batch_id: str,
    canonical_bytes: bytes,
    capture: DailySourceTransportCapture,
    reason: str,
    scope: DailySourceUseScope | None,
    started: datetime | None,
    validation: DailySourceBatchValidation | None,
) -> Path | None:
    quarantine_path = Path(root) / "quarantine" / f"{batch_id}.json"
    try:
        if quarantine_path.is_file() and not quarantine_path.is_symlink():
            return quarantine_path
        return write_daily_source_quarantine_candidate(
            root,
            batch_id=batch_id,
            raw_source_bytes=canonical_bytes,
            failure_reason_code=reason,
            scope=scope,
            source_batch_started_at=started,
            validation=validation,
            failed_partition_ids=(
                (f"{scope.market}:failed_daily_monthly_snapshot",) if scope else ()
            ),
            transport_capture=capture,
        )
    except Exception:
        return None


def _raise_if_cancelled(
    check_cancel: Callable[[], bool],
    phase: str,
) -> None:
    try:
        value = check_cancel()
    except Exception as exc:
        raise DailyMonthlyRevenueSnapshotUpdateError(
            f"daily_monthly_cancel_check_failed:{phase}:{type(exc).__name__}:{exc}"
        ) from exc
    if type(value) is not bool:
        raise DailyMonthlyRevenueSnapshotUpdateError(
            f"daily_monthly_cancel_check_not_bool:{phase}"
        )
    if value:
        raise _DailySnapshotCancelled(
            f"daily_monthly_cancelled_before_publish:{phase}"
        )


def _call_clock(clock: Callable[[], datetime], label: str) -> datetime:
    try:
        value = clock()
    except Exception as exc:
        raise DailyMonthlyRevenueSnapshotUpdateError(
            f"daily_monthly_clock_failed:{label}:{type(exc).__name__}:{exc}"
        ) from exc
    return _require_aware_taipei(value, label)


def _require_aware_taipei(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DailyMonthlyRevenueSnapshotUpdateError(
            f"daily_monthly_{label}_must_be_aware"
        )
    return value.astimezone(_TAIPEI)


def _named_failure_reason(exc: Exception, *, prefix: str = "daily_monthly_snapshot_update_rejected") -> str:
    if isinstance(exc, DailyMonthlyRevenueSnapshotUpdateError):
        return str(exc)
    if isinstance(exc, DailySourceSnapshotError):
        return f"{prefix}:{exc}"
    return f"{prefix}:{type(exc).__name__}:{exc}"


def _fallback_scope() -> DailySourceUseScope:
    return DailySourceUseScope(
        dataset_id=DAILY_SOURCE_SNAPSHOT_DATASET_ID,
        source_id=DAILY_SOURCE_SNAPSHOT_SOURCE_ID,
        market="twse",
        parser_version=MONTHLY_NORMALIZER_VERSION,
        source_schema_version="mops-static-snapshot.v2",
        unit="TWD",
        intended_use="recommendation_current_fundamental",
    )


__all__ = [
    "DailyMonthlyRevenueSnapshotReadStatus",
    "DailyMonthlyRevenueSnapshotUpdateError",
    "DailyMonthlyRevenueSnapshotUpdateResult",
    "publish_daily_monthly_revenue_snapshot",
    "read_daily_monthly_revenue_snapshot_status",
]
