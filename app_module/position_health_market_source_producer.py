"""建立每日 position-health 的 PIT condition 與 Decimal metrics 來源。

這個 producer 只讀取已由 data-update quick／freshness receipt 證明完成的
``technical_indicators`` 與 ``daily_prices``。它把同一個決策日、可得時間、
來源 receipt、SQLite selected rows 與 health baseline 綁在不可變的 derived
JSON；不寫市場 SQLite、不回寫 Paper／Formal，也不使用 UI cache。

這條來源是給 05:15 Pacific health/evidence lane 使用的 post-close
``decision_at``。它不是 08:30 Asia/Taipei 的 forward prediction source；
呼叫者必須把實際 health cutoff 傳入，provider 仍會拒絕未來的
``available_at``。沒有已驗證 stable position identity 的 row 會保留在
``unresolved_identity_codes``，不把 stock code 猜成 position identity。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any
from zoneinfo import ZoneInfo

from app_module.portfolio_condition_monitor import (
    PortfolioConditionResult,
    PortfolioCurrentSnapshot,
)
from app_module.position_health_source_providers import (
    CONDITION_SOURCE_SCHEMA_VERSION,
    METRICS_SOURCE_SCHEMA_VERSION,
    OfficialCalendarSourceProvider,
)


UTC = timezone.utc
SOURCE_VERSION = "position-health-market-source.v1"
HEALTH_BASELINE_V1 = "position-health-daily-refresh.v1"
HEALTH_BASELINE_V2 = "position-health-daily-refresh.v2"
TAIPEI = ZoneInfo("Asia/Taipei")
SOURCE_ID_PREFIX = "twstock:technical_indicators_daily_prices"
_DECIMAL_COLUMNS: tuple[tuple[str, str], ...] = (
    ("close_price", "close_price"),
    ("open_price", "open_price"),
    ("high_price", "high_price"),
    ("low_price", "low_price"),
    ("volume", "volume"),
    ("rsi", "rsi"),
    ("macd", "macd"),
    ("macd_signal", "macd_signal"),
    ("macd_hist", "macd_hist"),
    ("ma5", "ma5"),
    ("ma10", "ma10"),
    ("ma20", "ma20"),
    ("ma60", "ma60"),
    ("atr", "atr"),
    ("adx", "adx"),
)
_QUICK_MARKET_REQUIRED_STEPS = frozenset(
    {
        "update_twse_daily_prices",
        "update_tpex_daily_prices",
        "sync_daily_prices_to_sqlite",
        "calculate_technical_indicators",
    }
)
_FRESHNESS_MARKET_REQUIRED_SOURCES = frozenset(
    {
        "twse.daily_prices.raw",
        "tpex.daily_prices.raw",
        "sqlite.daily_prices",
        "sqlite.technical_indicators",
    }
)


class PositionHealthMarketSourceError(ValueError):
    """Input custody or selected market rows cannot be trusted."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _sha256_json(value: object) -> str:
    return _sha256_bytes(_canonical(value))


def _is_sha256(value: object) -> bool:
    text = str(value or "")
    return (
        len(text) == 71
        and text.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in text[7:])
    )


def _parse_date(value: object, field_name: str) -> date:
    text = str(value or "").strip()
    try:
        if len(text) == 8 and text.isdigit():
            parsed = date(int(text[:4]), int(text[4:6]), int(text[6:8]))
        else:
            parsed = date.fromisoformat(text[:10])
    except ValueError as exc:
        raise PositionHealthMarketSourceError(f"{field_name}_invalid") from exc
    if text.isdigit() and len(text) == 8:
        normalised = parsed.strftime("%Y%m%d")
    else:
        normalised = parsed.isoformat()
    if normalised != text[:10] and normalised != text:
        raise PositionHealthMarketSourceError(f"{field_name}_invalid")
    return parsed


def _parse_aware(value: object, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise PositionHealthMarketSourceError(f"{field_name}_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PositionHealthMarketSourceError(f"{field_name}_must_be_timezone_aware")
    return parsed.astimezone(UTC)


def _validate_daily_health_baseline_v2(
    payload: Mapping[str, Any],
    *,
    decision: date,
    cutoff: datetime,
    observed: datetime,
) -> dict[str, Any]:
    """驗證具名 v2 Paper baseline，並回傳實際來源事實供輸出封存。"""

    if payload.get("producer") != "app_module.position_health_daily_refresh_service":
        raise PositionHealthMarketSourceError("health_baseline_producer_invalid")
    if payload.get("status") != "fresh":
        raise PositionHealthMarketSourceError("health_baseline_not_fresh")
    if payload.get("source_type") != "paper_snapshot_read_only":
        raise PositionHealthMarketSourceError("health_baseline_source_type_invalid")
    if payload.get("source_read_mode") != "sqlite_uri_mode_ro_and_query_only":
        raise PositionHealthMarketSourceError("health_baseline_source_read_mode_invalid")
    if payload.get("portfolio_id") != "paper-main":
        raise PositionHealthMarketSourceError("health_baseline_portfolio_invalid")
    if payload.get("research_only") is not True:
        raise PositionHealthMarketSourceError("health_baseline_boundary_invalid")
    for field in (
        "writes_positions_db",
        "auto_action_allowed",
        "broker_execution",
        "formal_credit",
    ):
        if payload.get(field) is not False:
            raise PositionHealthMarketSourceError(
                f"health_baseline_boundary_invalid:{field}"
            )

    snapshot_id = str(payload.get("source_snapshot_id") or "").strip()
    source_result_id = str(payload.get("source_result_id") or "").strip()
    if not snapshot_id or not source_result_id:
        raise PositionHealthMarketSourceError("health_baseline_snapshot_identity_invalid")
    rows_hash = payload.get("source_snapshot_rows_sha256")
    if not _is_sha256(rows_hash):
        raise PositionHealthMarketSourceError("health_baseline_snapshot_rows_hash_invalid")

    baseline_date = _parse_date(
        payload.get("decision_date"), "health_baseline_decision_date"
    )
    snapshot_date = _parse_date(
        payload.get("source_snapshot_date"), "health_baseline_source_snapshot_date"
    )
    as_of_date = _parse_date(payload.get("as_of_date"), "health_baseline_as_of_date")
    if (
        snapshot_date != baseline_date
        or snapshot_date > decision
        or as_of_date != decision
    ):
        raise PositionHealthMarketSourceError("health_baseline_date_mismatch")

    source_observed = _parse_aware(
        payload.get("source_observed_at"), "health_baseline_source_observed_at"
    )
    if source_observed > cutoff or source_observed > observed:
        raise PositionHealthMarketSourceError(
            "health_baseline_source_observed_after_cutoff"
        )
    source_available_value = payload.get("source_available_at")
    if source_available_value is not None:
        source_available = _parse_aware(
            source_available_value, "health_baseline_source_available_at"
        )
        if source_available > source_observed or source_available > cutoff:
            raise PositionHealthMarketSourceError(
                "health_baseline_source_available_after_observed"
            )

    identity_source = payload.get("position_identity_source")
    if identity_source is not None:
        if not isinstance(identity_source, Mapping):
            raise PositionHealthMarketSourceError(
                "health_baseline_identity_source_invalid"
            )
        if (
            identity_source.get("schema_version")
            != "paper-position-identity-source.v1"
            or identity_source.get("provider") != "PaperPositionIdentityProvider"
            or identity_source.get("portfolio_id") != "paper-main"
            or identity_source.get("requested_snapshot_id") != snapshot_id
            or identity_source.get("requested_snapshot_date")
            != snapshot_date.isoformat()
            or identity_source.get("status") not in {"verified", "degraded", "blocked"}
        ):
            raise PositionHealthMarketSourceError(
                "health_baseline_identity_source_snapshot_invalid"
            )
        identity_source_observed = _parse_aware(
            identity_source.get("observed_at"),
            "health_baseline_identity_source_observed_at",
        )
        if (
            identity_source_observed > source_observed
            or identity_source_observed > cutoff
            or identity_source_observed > observed
        ):
            raise PositionHealthMarketSourceError(
                "health_baseline_identity_source_observed_after_cutoff"
            )
        resolved_codes = identity_source.get("resolved_codes", [])
        if not isinstance(resolved_codes, list) or not all(
            isinstance(code, str) and code.strip() == code for code in resolved_codes
        ):
            raise PositionHealthMarketSourceError(
                "health_baseline_identity_source_codes_invalid"
            )
        if len(set(resolved_codes)) != len(resolved_codes):
            raise PositionHealthMarketSourceError(
                "health_baseline_identity_source_codes_invalid"
            )
        if identity_source.get("status") in {"verified", "degraded"}:
            identity_count = identity_source.get("identity_count")
            if (
                isinstance(identity_count, bool)
                or not isinstance(identity_count, int)
                or identity_count != len(resolved_codes)
            ):
                raise PositionHealthMarketSourceError(
                    "health_baseline_identity_source_count_invalid"
                )

    boundary = payload.get("source_decision_boundary")
    source_decision_at_value = payload.get("source_decision_at")
    if boundary is None:
        if source_decision_at_value is not None:
            raise PositionHealthMarketSourceError(
                "health_baseline_decision_clock_invalid"
            )
        preopen_qualified = False
    elif boundary == "paper-main-preopen":
        source_decision_at = _parse_aware(
            source_decision_at_value, "health_baseline_source_decision_at"
        )
        source_decision_taipei = source_decision_at.astimezone(TAIPEI)
        if (
            source_decision_taipei.date() != snapshot_date
            or source_decision_taipei.time().replace(tzinfo=None) >= time(9, 0)
            or source_decision_at > source_observed
        ):
            raise PositionHealthMarketSourceError(
                "health_baseline_preopen_clock_invalid"
            )
        preopen_qualified = True
    else:
        raise PositionHealthMarketSourceError(
            "health_baseline_decision_boundary_invalid"
        )

    positions = payload.get("positions")
    if not isinstance(positions, list):
        raise PositionHealthMarketSourceError("health_baseline_positions_invalid")
    seen_stock_codes: set[str] = set()
    seen_position_ids: set[str] = set()
    for row in positions:
        if not isinstance(row, Mapping):
            raise PositionHealthMarketSourceError("health_baseline_position_not_object")
        code = str(row.get("stock_code") or "").strip()
        shares = row.get("paper_shares")
        if (
            not code
            or isinstance(shares, bool)
            or not isinstance(shares, int)
            or shares <= 0
        ):
            raise PositionHealthMarketSourceError(
                "health_baseline_position_shares_invalid"
            )
        if code in seen_stock_codes:
            raise PositionHealthMarketSourceError(
                f"health_baseline_duplicate_stock_code:{code}"
            )
        seen_stock_codes.add(code)
        position_id = row.get("position_id")
        lineage_id = row.get("entry_lineage_id")
        identity = row.get("position_identity_source")
        has_identity = (
            position_id is not None
            or lineage_id is not None
            or identity not in (None, {})
        )
        if not preopen_qualified and (has_identity or identity not in (None, {})):
            raise PositionHealthMarketSourceError(
                "health_baseline_identity_without_preopen_boundary"
            )
        if has_identity:
            if identity_source is None:
                raise PositionHealthMarketSourceError(
                    "health_baseline_identity_source_missing"
                )
            if not isinstance(identity, Mapping):
                raise PositionHealthMarketSourceError(
                    "health_baseline_identity_unverified"
                )
            if identity.get("status") not in {
                "natural_entry_verified",
                "carried_verified",
                "same_snapshot_verified",
                "ledger_continuous_no_trade",
            }:
                raise PositionHealthMarketSourceError(
                    "health_baseline_identity_unverified"
                )
            position_id = str(position_id or "").strip()
            lineage_id = str(lineage_id or "").strip()
            if not position_id or not lineage_id:
                raise PositionHealthMarketSourceError(
                    "health_baseline_identity_unverified"
                )
            if (
                identity.get("stock_code") != code
                or identity.get("position_id") != position_id
                or identity.get("entry_lineage_id") != lineage_id
                or identity.get("current_snapshot_id") != snapshot_id
                or identity.get("current_snapshot_date") != snapshot_date.isoformat()
            ):
                raise PositionHealthMarketSourceError(
                    "health_baseline_identity_snapshot_mismatch"
                )
            resolved_codes = identity_source.get("resolved_codes", [])
            if code not in resolved_codes:
                raise PositionHealthMarketSourceError(
                    "health_baseline_identity_source_code_mismatch"
                )
            if position_id in seen_position_ids:
                raise PositionHealthMarketSourceError(
                    "health_baseline_duplicate_position_identity"
                )
            seen_position_ids.add(position_id)
            entry_date = _parse_date(
                identity.get("entry_date"), "health_baseline_identity_entry_date"
            )
            if entry_date >= snapshot_date:
                raise PositionHealthMarketSourceError(
                    "health_baseline_identity_entry_not_preopen"
                )
            identity_available = _parse_aware(
                identity.get("available_at"),
                "health_baseline_identity_available_at",
            )
            if identity_available > source_observed or identity_available > cutoff:
                raise PositionHealthMarketSourceError(
                    "health_baseline_identity_available_after_observed"
                )

    return {
        "schema_version": HEALTH_BASELINE_V2,
        "producer": payload.get("producer"),
        "portfolio_id": payload.get("portfolio_id"),
        "source_result_id": source_result_id,
        "source_snapshot_id": snapshot_id,
        "source_snapshot_date": snapshot_date.isoformat(),
        "source_snapshot_rows_sha256": rows_hash,
        "source_observed_at": source_observed.isoformat(),
        "source_available_at": (
            None
            if source_available_value is None
            else _parse_aware(
                source_available_value, "health_baseline_source_available_at"
            ).isoformat()
        ),
        "source_decision_boundary": boundary,
        "source_decision_at": source_decision_at_value,
        "decision_date": baseline_date.isoformat(),
        "as_of_date": as_of_date.isoformat(),
        "observation_semantics": "paper_holdings_snapshot_observation_only",
        "same_day_paper_producer_success_proven": False,
        "is_stale_as_of": snapshot_date < decision,
    }


def _decimal(value: object, field_name: str) -> Decimal:
    if value is None or value == "":
        raise PositionHealthMarketSourceError(f"{field_name}_missing")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PositionHealthMarketSourceError(f"{field_name}_invalid") from exc
    if not parsed.is_finite():
        raise PositionHealthMarketSourceError(f"{field_name}_non_finite")
    return parsed


def _read_json(path: Path, field_name: str) -> tuple[dict[str, Any], str]:
    try:
        before = path.read_bytes()
        payload = json.loads(before.decode("utf-8-sig"))
        after = path.read_bytes()
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PositionHealthMarketSourceError(f"{field_name}_unreadable") from exc
    if before != after:
        raise PositionHealthMarketSourceError(f"{field_name}_changed_during_read")
    if not isinstance(payload, Mapping):
        raise PositionHealthMarketSourceError(f"{field_name}_must_be_object")
    return dict(payload), _sha256_bytes(before)


def _quick_market_lane_ready(payload: Mapping[str, Any]) -> bool:
    status = str(payload.get("status") or "")
    if status == "passed":
        return True
    if status != "passed_with_warnings":
        return False
    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list):
        return False
    steps = {
        str(item.get("name") or ""): item
        for item in raw_steps
        if isinstance(item, Mapping) and str(item.get("name") or "")
    }
    for name in _QUICK_MARKET_REQUIRED_STEPS:
        step = steps.get(name)
        if step is None or str(step.get("status") or "") not in {"passed", "skipped"}:
            return False
        result = step.get("result")
        if not isinstance(result, Mapping) or result.get("success") is not True:
            return False
    warning_steps = [
        item
        for item in raw_steps
        if isinstance(item, Mapping) and item.get("status") == "warning"
    ]
    if not warning_steps:
        return False
    allowed_messages: set[str] = set()
    for step in warning_steps:
        result = step.get("result")
        if (
            step.get("name") != "update_phase3c_candidate_sources"
            or not isinstance(result, Mapping)
            or result.get("candidate_only") is not True
        ):
            return False
        message = str(step.get("message") or "").strip()
        if message:
            allowed_messages.add(message)
    warnings = {
        str(item).strip()
        for item in (payload.get("warnings") or [])
        if str(item).strip()
    }
    return bool(warnings) and warnings.issubset(allowed_messages)


def _freshness_market_lane_ready(payload: Mapping[str, Any]) -> bool:
    status = str(payload.get("status") or "")
    if status == "passed":
        return True
    if status != "degraded" or payload.get("errors") not in (None, [], ()):
        return False
    raw_statuses = payload.get("source_statuses")
    if not isinstance(raw_statuses, list):
        return False
    statuses = {
        str(item.get("source_id") or ""): item
        for item in raw_statuses
        if isinstance(item, Mapping) and str(item.get("source_id") or "")
    }
    for source_id in _FRESHNESS_MARKET_REQUIRED_SOURCES:
        item = statuses.get(source_id)
        if item is None or item.get("freshness_status") != "current":
            return False
    for raw_warning in payload.get("warnings") or []:
        warning = str(raw_warning).strip()
        if warning in {
            "monthly_revenue_expected_period_not_available",
            "quarterly_statement_expected_period_not_available",
        }:
            continue
        prefix = "source_freshness_degraded:"
        if warning.startswith(prefix) and warning[len(prefix):] not in _FRESHNESS_MARKET_REQUIRED_SOURCES:
            continue
        return False
    return True


def _stat_token(path: Path) -> dict[str, int]:
    try:
        stat = path.stat()
    except OSError as exc:
        raise PositionHealthMarketSourceError("market_db_stat_failed") from exc
    return {"size": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns)}


def _date_key(value: object) -> str:
    return _parse_date(value, "date").strftime("%Y%m%d")


def _source_row_code(value: object) -> str:
    return str(value or "").strip()


def _write_atomic(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_create_only(path: Path, raw: bytes) -> str:
    """Atomically create a file without ever replacing an existing payload.

    A temporary file plus a same-volume hard-link gives us an atomic
    create-only claim on Windows/NTFS.  The caller can distinguish a race that
    wrote identical bytes from a conflict that must receive a new immutable
    filename.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            try:
                existing = path.read_bytes()
            except OSError as exc:
                raise PositionHealthMarketSourceError(
                    "immutable_artifact_existing_read_failed"
                ) from exc
            return "same" if existing == raw else "conflict"
        return "created"
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_hashed(path: Path, body: Mapping[str, Any]) -> tuple[Path, str, str]:
    encoded_body = _canonical(dict(body))
    payload = {**dict(body), "content_sha256": _sha256_bytes(encoded_body)}
    encoded = _canonical(payload) + b"\n"
    dated = path
    outcome = _write_create_only(dated, encoded)
    if outcome == "conflict":
        suffix = hashlib.sha256(encoded).hexdigest()[:16]
        dated = dated.with_name(f"{dated.stem}_{suffix}{dated.suffix}")
        outcome = _write_create_only(dated, encoded)
        if outcome == "conflict":
            raise PositionHealthMarketSourceError("immutable_artifact_hash_path_conflict")
    return dated, _sha256_bytes(encoded), payload["content_sha256"]


def _normalise_positions(payload: Mapping[str, Any]) -> tuple[list[dict[str, str]], list[str]]:
    raw_positions = payload.get("positions")
    if not isinstance(raw_positions, list):
        raise PositionHealthMarketSourceError("health_baseline_positions_invalid")
    positions: list[dict[str, str]] = []
    unresolved: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in raw_positions:
        if not isinstance(raw, Mapping):
            raise PositionHealthMarketSourceError("health_baseline_position_not_object")
        code = _source_row_code(raw.get("stock_code"))
        if not code:
            raise PositionHealthMarketSourceError("health_baseline_stock_code_missing")
        shares_raw = raw.get("paper_shares")
        if shares_raw is None:
            raise PositionHealthMarketSourceError("health_baseline_shares_invalid")
        try:
            shares = int(str(shares_raw))
        except (TypeError, ValueError) as exc:
            raise PositionHealthMarketSourceError("health_baseline_shares_invalid") from exc
        if shares <= 0:
            continue
        position_id = _source_row_code(raw.get("position_id"))
        lineage_id = _source_row_code(raw.get("entry_lineage_id"))
        if not position_id or not lineage_id:
            unresolved.append(code)
            continue
        key = (position_id, lineage_id, code)
        if key in seen:
            raise PositionHealthMarketSourceError(f"health_baseline_position_duplicate:{code}")
        seen.add(key)
        positions.append(
            {
                "position_id": position_id,
                "entry_lineage_id": lineage_id,
                "stock_code": code,
            }
        )
    return positions, sorted(set(unresolved))


class PositionHealthMarketSourceProducer:
    """Produce condition and metrics artifacts from a verified daily market read."""

    def __init__(
        self,
        *,
        market_db_path: str | Path,
        quick_status_path: str | Path,
        freshness_status_path: str | Path,
        now_provider: Callable[[], datetime] | None = None,
        calendar_cache_path: str | Path | None = None,
        temporary_closure_path: str | Path | None = None,
    ) -> None:
        self.market_db_path = Path(market_db_path).expanduser().resolve()
        self.quick_status_path = Path(quick_status_path).expanduser().resolve()
        self.freshness_status_path = Path(freshness_status_path).expanduser().resolve()
        self.now_provider = now_provider or (lambda: datetime.now(UTC))
        self.calendar_cache_path = calendar_cache_path
        self.temporary_closure_path = temporary_closure_path

    def produce(
        self,
        *,
        baseline_path: str | Path,
        output_dir: str | Path,
        decision_date: str,
        decision_at: datetime | str | None = None,
        observed_at: datetime | str | None = None,
    ) -> dict[str, Any]:
        baseline = Path(baseline_path).expanduser().resolve()
        output = Path(output_dir).expanduser().resolve()
        decision = _parse_date(decision_date, "decision_date")
        requested_cutoff = (
            None if decision_at is None else _parse_aware(decision_at, "decision_at")
        )
        requested_observed = (
            None if observed_at is None else _parse_aware(observed_at, "observed_at")
        )
        if (
            requested_cutoff is not None
            and requested_observed is not None
            and requested_cutoff > requested_observed
        ):
            raise PositionHealthMarketSourceError("decision_at_after_observed_at")

        run_started = _parse_aware(
            self.now_provider(), "market_capture_started_at"
        )
        receipt_cutoff = requested_cutoff or requested_observed or run_started
        receipt_observed = requested_observed or run_started

        baseline_payload, baseline_hash = _read_json(baseline, "health_baseline")
        baseline_schema = baseline_payload.get("schema_version")
        if baseline_schema == HEALTH_BASELINE_V1:
            baseline_date = _parse_date(
                baseline_payload.get("decision_date"),
                "health_baseline_decision_date",
            )
            as_of_value = baseline_payload.get("as_of_date")
            baseline_as_of_date = (
                None
                if as_of_value in (None, "")
                else _parse_date(as_of_value, "health_baseline_as_of_date")
            )
            snapshot_date_value = baseline_payload.get("source_snapshot_date")
            baseline_snapshot_date = (
                None
                if snapshot_date_value in (None, "")
                else _parse_date(
                    snapshot_date_value,
                    "health_baseline_source_snapshot_date",
                )
            )
            if (
                baseline_date > decision
                or (baseline_as_of_date is not None and baseline_as_of_date != decision)
                or (baseline_date < decision and baseline_as_of_date is None)
            ):
                raise PositionHealthMarketSourceError("health_baseline_date_mismatch")
            if baseline_snapshot_date is not None and baseline_snapshot_date != baseline_date:
                raise PositionHealthMarketSourceError("health_baseline_date_mismatch")
            is_stale_snapshot = baseline_date < decision
            snapshot_id_value = baseline_payload.get("source_snapshot_id")
            rows_hash_value = baseline_payload.get("source_snapshot_rows_sha256")
            snapshot_id = str(snapshot_id_value or "").strip()
            rows_hash = str(rows_hash_value or "").strip()
            if is_stale_snapshot:
                if baseline_snapshot_date is None or baseline_as_of_date is None:
                    raise PositionHealthMarketSourceError("health_baseline_date_mismatch")
                if not snapshot_id or not _is_sha256(rows_hash):
                    raise PositionHealthMarketSourceError(
                        "health_baseline_snapshot_identity_invalid"
                    )
                if (
                    baseline_payload.get("status") != "fresh"
                    or baseline_payload.get("source_type") != "paper_snapshot_read_only"
                    or baseline_payload.get("source_read_mode")
                    != "sqlite_uri_mode_ro_and_query_only"
                ):
                    raise PositionHealthMarketSourceError(
                        "health_baseline_source_contract_invalid"
                    )
                if (
                    baseline_payload.get("research_only") is not True
                    or baseline_payload.get("writes_positions_db") is not False
                    or baseline_payload.get("auto_action_allowed") is not False
                    or baseline_payload.get("broker_execution") is not False
                    or baseline_payload.get("formal_credit") is not False
                ):
                    raise PositionHealthMarketSourceError(
                        "health_baseline_boundary_invalid"
                    )
            position_snapshot_observation = {
                "schema_version": HEALTH_BASELINE_V1,
                "source_snapshot_id": snapshot_id or None,
                "source_snapshot_date": (
                    baseline_date.isoformat()
                    if baseline_snapshot_date is None
                    else baseline_snapshot_date.isoformat()
                ),
                "source_snapshot_rows_sha256": rows_hash or None,
                "decision_date": baseline_date.isoformat(),
                "as_of_date": (
                    decision.isoformat()
                    if baseline_as_of_date is None
                    else baseline_as_of_date.isoformat()
                ),
                "observation_semantics": "paper_holdings_snapshot_observation_only",
                "same_day_paper_producer_success_proven": False,
                "is_stale_as_of": is_stale_snapshot,
            }
        elif baseline_schema == HEALTH_BASELINE_V2:
            position_snapshot_observation = _validate_daily_health_baseline_v2(
                baseline_payload,
                decision=decision,
                cutoff=receipt_cutoff,
                observed=receipt_observed,
            )
        else:
            baseline_date = _parse_date(
                baseline_payload.get("decision_date") or baseline_payload.get("as_of_date"),
                "health_baseline_decision_date",
            )
            if baseline_date != decision:
                raise PositionHealthMarketSourceError("health_baseline_date_mismatch")
            position_snapshot_observation = {
                "schema_version": baseline_payload.get("schema_version"),
                "decision_date": baseline_date.isoformat(),
                "as_of_date": baseline_date.isoformat(),
                "observation_semantics": "legacy_baseline_decision_date_match",
                "same_day_paper_producer_success_proven": False,
                "is_stale_as_of": False,
            }
        positions, unresolved = _normalise_positions(baseline_payload)

        quick, quick_hash = _read_json(self.quick_status_path, "quick_status")
        freshness, freshness_hash = _read_json(self.freshness_status_path, "freshness_status")
        checks = freshness.get("checks")
        market_date = decision
        calendar_provenance: dict[str, Any] = {}
        if isinstance(checks, Mapping) and checks.get("expected_official_session"):
            market_date = _parse_date(checks["expected_official_session"], "expected_official_session")
        if market_date > decision:
            raise PositionHealthMarketSourceError("market_data_date_future")
        if market_date < decision:
            if self.calendar_cache_path is None:
                raise PositionHealthMarketSourceError("market_date_calendar_evidence_missing")
            calendar = OfficialCalendarSourceProvider(
                calendar_cache_path=self.calendar_cache_path,
                temporary_closure_path=self.temporary_closure_path,
            ).read_range(
                start_date=market_date.isoformat(), end_date=decision.isoformat(),
                decision_at=receipt_cutoff, observed_at=receipt_observed,
            )
            if calendar.blockers or calendar.values.get("trading_dates") != (market_date.isoformat(),):
                raise PositionHealthMarketSourceError("market_date_not_latest_verified_session")
            calendar_provenance = dict(calendar.provenance)
        available_at, status_warnings = self._validate_receipts(
            quick,
            freshness,
            decision=decision,
            market_date=market_date,
            closed_date_range_verified=bool(calendar_provenance),
            cutoff=receipt_cutoff,
            observed=receipt_observed,
        )

        # The upstream receipts are checked first.  Only then do we capture
        # the selected SQLite rows, so the derived source cannot bind a
        # pre-receipt or later replacement to an earlier cutoff.
        capture_started = _parse_aware(
            self.now_provider(), "market_capture_started_at"
        )
        if requested_cutoff is not None and capture_started > requested_cutoff:
            raise PositionHealthMarketSourceError(
                "market_capture_started_after_decision_cutoff"
            )
        if requested_observed is not None and capture_started > requested_observed:
            raise PositionHealthMarketSourceError(
                "market_capture_started_after_observed_at"
            )

        rows, db_binding = self._read_market_rows(
            codes=tuple(item["stock_code"] for item in positions),
            decision=market_date,
        )
        capture_completed = _parse_aware(
            self.now_provider(), "market_capture_completed_at"
        )
        if requested_cutoff is not None and capture_completed > requested_cutoff:
            raise PositionHealthMarketSourceError(
                "market_capture_completed_after_decision_cutoff"
            )
        if requested_observed is not None and capture_completed > requested_observed:
            raise PositionHealthMarketSourceError(
                "market_capture_completed_after_observed_at"
            )
        cutoff = requested_cutoff or requested_observed or capture_completed
        observed = requested_observed or capture_completed
        selected_codes = {str(row["stock_code"]) for row in rows}
        missing_codes = sorted(
            {item["stock_code"] for item in positions} - selected_codes
        )
        source_id = f"{SOURCE_ID_PREFIX}:{decision.strftime('%Y%m%d')}"
        # ``source_snapshot_hash`` identifies the selected market observations,
        # not this invocation's receipt clock.  Capture timestamps, baseline
        # receipt bytes and whole-database stat tokens remain in the immutable
        # artifacts below, but must not turn a same-day scheduler retry over the
        # same rows into a different market snapshot.
        source_binding = {
            "schema_version": SOURCE_VERSION,
            "source_id": source_id,
            "decision_date": decision.isoformat(),
            "market_data_date": market_date.isoformat(),
            "selected_rows": rows,
        }
        source_hash = _sha256_json(source_binding)

        rows_by_code = {str(row["stock_code"]): row for row in rows}
        condition_rows: list[dict[str, Any]] = []
        metric_rows: list[dict[str, Any]] = []
        for identity in positions:
            row = rows_by_code.get(identity["stock_code"])
            if row is None:
                continue
            condition_rows.append(
                self._condition_row(
                    identity=identity,
                    row=row,
                    source_id=source_id,
                    source_hash=source_hash,
                    decision=decision,
                    position_snapshot_observation=position_snapshot_observation,
                )
            )
            metric_rows.extend(
                {
                    **identity,
                    "metric_id": metric_id,
                    "value": value,
                    "available_date": decision.isoformat(),
                    "available_at": capture_completed.isoformat(),
                }
                for metric_id, value in row["metrics"].items()
            )

        common = {
            "source_version": SOURCE_VERSION,
            "source_id": source_id,
            "source_snapshot_hash": source_hash,
            "as_of_date": decision.isoformat(),
            "market_data_date": market_date.isoformat(),
            "market_calendar": calendar_provenance,
            "upstream_receipt_available_at": available_at.isoformat(),
            "available_at": capture_completed.isoformat(),
            "decision_cutoff_at": cutoff.isoformat(),
            "source_semantics": (
                "daily technical_indicators and daily_prices read after quick receipt; "
                "condition is observation-only until a governed entry thesis exists"
            ),
            "market_db_path": str(self.market_db_path),
            "quick_status_path": str(self.quick_status_path),
            "freshness_status_path": str(self.freshness_status_path),
            "baseline_path": str(baseline),
            "baseline_sha256": baseline_hash,
            "position_snapshot_observation": position_snapshot_observation,
            "unresolved_identity_codes": unresolved,
            "missing_market_codes": missing_codes,
        }
        condition_body = {
            "schema_version": CONDITION_SOURCE_SCHEMA_VERSION,
            **common,
            "condition_evaluation": "observation_only_without_entry_thesis",
            "positions": condition_rows,
        }
        metrics_body = {
            "schema_version": METRICS_SOURCE_SCHEMA_VERSION,
            **common,
            "metric_definitions": {
                metric_id: f"technical_indicators/daily_prices.{column}"
                for metric_id, column in _DECIMAL_COLUMNS
            },
            "metrics": metric_rows,
        }
        condition_path, condition_file_hash, _ = _write_hashed(
            output / f"condition_{decision.strftime('%Y%m%d')}.json", condition_body
        )
        metrics_path, metrics_file_hash, _ = _write_hashed(
            output / f"metrics_{decision.strftime('%Y%m%d')}.json", metrics_body
        )
        warnings = [*status_warnings]
        if position_snapshot_observation["is_stale_as_of"]:
            warnings.append(
                "paper_holdings_snapshot_older_than_health_as_of:"
                + str(position_snapshot_observation["source_snapshot_date"])
            )
        warnings.extend(f"position_health_source_identity_missing:{code}" for code in unresolved)
        warnings.extend(f"position_health_source_market_missing:{code}" for code in missing_codes)
        if not positions:
            warnings.append("position_health_source_no_verified_position_id")
        status = "passed" if not warnings else "degraded"
        receipt_body: dict[str, Any] = {
            "schema_version": SOURCE_VERSION,
            "producer": f"{type(self).__module__}.{type(self).__name__}",
            "status": status,
            "decision_date": decision.isoformat(),
            "market_data_date": market_date.isoformat(),
            "market_calendar": calendar_provenance,
            "decision_cutoff_at": cutoff.isoformat(),
            "available_at": capture_completed.isoformat(),
            "observed_at": observed.isoformat(),
            "market_capture_started_at": capture_started.isoformat(),
            "market_capture_completed_at": capture_completed.isoformat(),
            "source_id": source_id,
            "source_snapshot_hash": source_hash,
            "position_snapshot_observation": position_snapshot_observation,
            "source_custody": {
                "baseline_sha256": baseline_hash,
                "quick_status_sha256": quick_hash,
                "freshness_status_sha256": freshness_hash,
                "market_db": db_binding,
            },
            "upstream_receipt_available_at": available_at.isoformat(),
            "condition_source_path": str(condition_path),
            "condition_source_file_sha256": condition_file_hash,
            "metrics_source_path": str(metrics_path),
            "metrics_source_file_sha256": metrics_file_hash,
            "verified_position_count": len(positions),
            "condition_row_count": len(condition_rows),
            "metric_row_count": len(metric_rows),
            "unresolved_identity_codes": unresolved,
            "missing_market_codes": missing_codes,
            "warnings": list(dict.fromkeys(warnings)),
            "blockers": [],
            "read_only": True,
            "writes_market_database": False,
            "writes_paper_state": False,
            "writes_formal_state": False,
            "research_only": True,
            "formal_credit": False,
            "broker_execution": False,
        }
        receipt_path, receipt_file_hash, _ = _write_hashed(
            output / f"source_receipt_{decision.strftime('%Y%m%d')}.json", receipt_body
        )
        latest = output / "latest_status.json"
        _write_atomic(latest, (json.dumps({**receipt_body, "receipt_path": str(receipt_path), "receipt_file_sha256": receipt_file_hash}, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))
        return {
            **receipt_body,
            "receipt_path": str(receipt_path),
            "latest_status_path": str(latest),
        }

    @staticmethod
    def _validate_receipts(
        quick: Mapping[str, Any],
        freshness: Mapping[str, Any],
        *,
        decision: date,
        cutoff: datetime,
        observed: datetime,
        market_date: date | None = None,
        closed_date_range_verified: bool = False,
    ) -> tuple[datetime, list[str]]:
        if not _quick_market_lane_ready(quick):
            raise PositionHealthMarketSourceError("quick_status_not_passed")
        if quick.get("writes_market_data_db") is not True:
            raise PositionHealthMarketSourceError("quick_status_market_write_receipt_missing")
        if quick.get("errors") not in (None, [], ()):
            raise PositionHealthMarketSourceError("quick_status_errors_present")
        quick_date = _parse_date(quick.get("end_date"), "quick_status_end_date")
        target_date = market_date or decision
        if quick_date != target_date and not (
            closed_date_range_verified and target_date < quick_date <= decision
        ):
            raise PositionHealthMarketSourceError("quick_status_date_mismatch")
        completed = _parse_aware(quick.get("completed_at"), "quick_status_completed_at")
        if completed > cutoff or completed > observed:
            raise PositionHealthMarketSourceError("quick_status_completed_at_future")
        if not _freshness_market_lane_ready(freshness):
            raise PositionHealthMarketSourceError("freshness_status_not_passed")
        checks = freshness.get("checks")
        if not isinstance(checks, Mapping):
            raise PositionHealthMarketSourceError("freshness_checks_missing")
        target_key = target_date.strftime("%Y%m%d")
        # The long-running updater has emitted both singular and plural key
        # spellings across existing receipt versions.  Accept only those two
        # explicit canonical names; never infer freshness from the SQLite
        # max(date) while the receipt is missing.
        daily_latest_key = checks.get("daily_prices_latest_date_key")
        if daily_latest_key is None:
            daily_latest_key = checks.get("daily_price_latest_date_key")
        if str(daily_latest_key or "") != target_key:
            raise PositionHealthMarketSourceError("freshness_daily_prices_date_mismatch")
        if str(checks.get("technical_indicators_latest_date") or "") != target_key:
            raise PositionHealthMarketSourceError("freshness_technical_date_mismatch")
        checked = _parse_aware(freshness.get("checked_at"), "freshness_checked_at")
        if checked > cutoff or checked > observed:
            raise PositionHealthMarketSourceError("freshness_checked_at_future")
        warnings = [
            str(item)
            for item in (quick.get("warnings") or [])
            if str(item).strip()
        ] + [
            str(item)
            for item in (freshness.get("warnings") or [])
            if str(item).strip()
        ]
        return completed, list(dict.fromkeys(warnings))

    def _read_market_rows(
        self,
        *,
        codes: Sequence[str],
        decision: date,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if not self.market_db_path.is_file():
            raise PositionHealthMarketSourceError("market_db_missing")
        before = _stat_token(self.market_db_path)
        target = decision.strftime("%Y%m%d")
        requested = {str(code) for code in codes if str(code).strip()}
        if not requested:
            # There is no safe stock-code fallback when the health baseline
            # has not proved a position identity.  Avoid scanning a large,
            # possibly active database just to discard every row.
            after = _stat_token(self.market_db_path)
            if before != after:
                raise PositionHealthMarketSourceError("market_db_changed_during_read")
            return [], {
                "path": str(self.market_db_path),
                "stat_before": before,
                "stat_after": after,
                "data_version": None,
                "table_scope": ["technical_indicators", "daily_prices"],
                "decision_date": decision.isoformat(),
                "selected_code_count": 0,
                "query_skipped": "no_verified_position_identity",
            }
        rows: list[dict[str, Any]] = []
        try:
            uri = f"file:{self.market_db_path.as_posix()}?mode=ro"
            with sqlite3.connect(uri, uri=True) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA query_only=ON")
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                if not {"technical_indicators", "daily_prices"}.issubset(tables):
                    raise PositionHealthMarketSourceError("market_db_required_tables_missing")
                data_version = int(connection.execute("PRAGMA data_version").fetchone()[0])
                query = """
                    SELECT
                        t.證券代號 AS technical_code,
                        t.日期 AS technical_date,
                        t.RSI AS rsi,
                        t.MACD AS macd,
                        t.MACD_signal AS macd_signal,
                        t.MACD_hist AS macd_hist,
                        t.MA5 AS ma5,
                        t.MA10 AS ma10,
                        t.MA20 AS ma20,
                        t.MA60 AS ma60,
                        t.ATR AS atr,
                        t.ADX AS adx,
                        p.證券代號 AS price_code,
                        p.日期 AS price_date,
                        p.收盤價 AS close_price,
                        p.開盤價 AS open_price,
                        p.最高價 AS high_price,
                        p.最低價 AS low_price,
                        p.成交股數 AS volume
                    FROM technical_indicators AS t
                    JOIN daily_prices AS p
                      ON p.證券代號 = t.證券代號 AND p.日期 = t.日期
                    WHERE t.日期 = ?
                """
                selected = connection.execute(query, (target,)).fetchall()
                for raw in selected:
                    code = _source_row_code(raw["technical_code"])
                    if code not in requested:
                        continue
                    if _source_row_code(raw["price_code"]) != code:
                        raise PositionHealthMarketSourceError(
                            f"market_row_identity_mismatch:{code}"
                        )
                    if _date_key(raw["technical_date"]) != target or _date_key(raw["price_date"]) != target:
                        raise PositionHealthMarketSourceError(
                            f"market_row_date_mismatch:{code}"
                        )
                    metrics: dict[str, str] = {}
                    for metric_id, _column in _DECIMAL_COLUMNS:
                        value = raw[metric_id]
                        if value is None or value == "":
                            continue
                        metrics[metric_id] = str(_decimal(value, f"{code}:{metric_id}"))
                    if "close_price" not in metrics:
                        raise PositionHealthMarketSourceError(f"market_close_missing:{code}")
                    rows.append({"stock_code": code, "metrics": dict(sorted(metrics.items()))})
                if len({str(row["stock_code"]) for row in rows}) != len(rows):
                    raise PositionHealthMarketSourceError("market_duplicate_code_date")
                after_version = int(connection.execute("PRAGMA data_version").fetchone()[0])
        except PositionHealthMarketSourceError:
            raise
        except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
            raise PositionHealthMarketSourceError(
                f"market_db_read_failed:{type(exc).__name__}"
            ) from exc
        after = _stat_token(self.market_db_path)
        if before != after or data_version != after_version:
            raise PositionHealthMarketSourceError("market_db_changed_during_read")
        return sorted(rows, key=lambda item: str(item["stock_code"])), {
            "path": str(self.market_db_path),
            "stat_before": before,
            "stat_after": after,
            "data_version": data_version,
            "table_scope": ["technical_indicators", "daily_prices"],
            "decision_date": decision.isoformat(),
            "selected_code_count": len(rows),
        }

    @staticmethod
    def _condition_row(
        *,
        identity: Mapping[str, str],
        row: Mapping[str, Any],
        source_id: str,
        source_hash: str,
        decision: date,
        position_snapshot_observation: Mapping[str, Any],
    ) -> dict[str, Any]:
        metrics = row.get("metrics")
        if not isinstance(metrics, Mapping):
            raise PositionHealthMarketSourceError("condition_metrics_invalid")
        close_price = str(metrics.get("close_price") or "")
        result = PortfolioConditionResult(
            stock_code=str(identity["stock_code"]),
            status="warning",
            label="PIT 市場快照已取得，等待進場論點",
            source_label="technical_indicators_pit",
            reasons=[
                "current_market_snapshot_observed",
                "entry_thesis_or_entry_condition_source_required",
            ],
            details={
                "condition_semantics": "observation_only_without_entry_thesis",
                "as_of_date": decision.isoformat(),
                "paper_position_snapshot_date": position_snapshot_observation.get(
                    "source_snapshot_date", position_snapshot_observation.get("as_of_date")
                ),
                "paper_position_snapshot_id": position_snapshot_observation.get(
                    "source_snapshot_id"
                ),
                "paper_position_observation_semantics": position_snapshot_observation[
                    "observation_semantics"
                ],
                "current_price": close_price,
                "current_snapshot_source": source_id,
            },
        )
        snapshot = PortfolioCurrentSnapshot(
            current_regime="",
            current_total_score=None,
            # The legacy monitor DTO is float-typed; keep Decimal as the
            # canonical metric representation and cross this DTO boundary
            # explicitly for its existing consumer contract.
            current_price=float(Decimal(close_price)),
        )
        return {
            **dict(identity),
            "quality": "observed",
            "result": {
                "stock_code": result.stock_code,
                "status": result.status,
                "label": result.label,
                "source_label": result.source_label,
                "entry_regime": result.entry_regime,
                "current_regime": result.current_regime,
                "entry_total_score": result.entry_total_score,
                "current_total_score": result.current_total_score,
                "reasons": list(result.reasons),
                "details": dict(result.details),
            },
            "current_snapshot": {
                "current_regime": snapshot.current_regime,
                "current_total_score": None,
                "current_price": str(snapshot.current_price),
            },
            "source_trace": [
                f"market_source:{source_id}",
                f"market_source_hash:{source_hash}",
            ],
        }


def produce_position_health_market_sources(**kwargs: Any) -> dict[str, Any]:
    """Convenience wrapper used by the scheduled caller and the CLI."""

    producer = PositionHealthMarketSourceProducer(
        market_db_path=kwargs.pop("market_db_path"),
        quick_status_path=kwargs.pop("quick_status_path"),
        freshness_status_path=kwargs.pop("freshness_status_path"),
    )
    return producer.produce(**kwargs)
