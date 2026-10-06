"""Candidate-only bounded feature rebuild from the verified daily-price source."""

from __future__ import annotations

from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from analysis_module.technical_analysis.technical_indicators import (
    CAUSAL_INDICATOR_COLUMNS,
    calculate_causal_indicators,
)
from data_module import excluded_daily_price_revision
from data_module.bounded_allocation_full_feature_restatement import (
    PRICE_FAMILY,
    QUALITY_FEATURE_IDS,
    QUALITY_SOURCE_ID,
    TECHNICAL_FEATURE_IDS,
    TECHNICAL_SOURCE_ID,
    _OHLC_FIELDS,
    _source_decimal,
)
from data_module.ml_restatement_research_dataset import (
    _feature_eligibility,
    expected_feature_contract,
)
from data_module.ml_restatement_research_candidate_source import (
    CandidateSourceProfile,
    FORMAL_DATABASE,
    candidate_profile_reference,
    verify_candidate_source_profile,
)
from data_module.bounded_allocation_label_restatement import _sha256_json


BRIDGE_SCHEMA = "bounded-candidate-daily-source-bridge.v1"
DAILY_RAW_FIELD_MAP: dict[str, str] = {
    "daily_prices.成交筆數": "成交筆數",
    "daily_prices.成交股數": "成交股數",
    "daily_prices.成交金額": "成交金額",
    "daily_prices.收盤價": "收盤價",
    "daily_prices.最低價": "最低價",
    "daily_prices.最後揭示買價": "最後揭示買價",
    "daily_prices.最後揭示買量": "最後揭示買量",
    "daily_prices.最後揭示賣價": "最後揭示賣價",
    "daily_prices.最後揭示賣量": "最後揭示賣量",
    "daily_prices.最高價": "最高價",
    "daily_prices.本益比": "本益比",
    "daily_prices.漲跌價差": "漲跌價差",
    "daily_prices.開盤價": "開盤價",
}
# These frozen ABI slots historically read a duplicated technical table whose
# post-processing could forward/back-fill quote values.  The candidate bridge
# projects verified daily_prices values and preserves source NULLs as missing.
TECHNICAL_ALIAS_FIELD_MAP: dict[str, str] = {
    "technical_indicators.最後揭示買價": "最後揭示買價",
    "technical_indicators.最後揭示買量": "最後揭示買量",
    "technical_indicators.最後揭示賣價": "最後揭示賣價",
    "technical_indicators.最後揭示賣量": "最後揭示賣量",
    "technical_indicators.本益比": "本益比",
    "technical_indicators.涨跌": "涨跌",
    "technical_indicators.漲跌(+/-)": "漲跌(+/-)",
    "technical_indicators.漲跌價差": "漲跌價差",
}
CANDIDATE_RAW_FIELD_MAP = {**DAILY_RAW_FIELD_MAP, **TECHNICAL_ALIAS_FIELD_MAP}
CANDIDATE_RAW_FEATURE_IDS = frozenset(CANDIDATE_RAW_FIELD_MAP)
CANDIDATE_STOCK_FEATURE_IDS = frozenset(
    {*CANDIDATE_RAW_FEATURE_IDS, *TECHNICAL_FEATURE_IDS, *QUALITY_FEATURE_IDS}
)
_DAILY_SOURCE_ID = "sqlite.daily_prices"
_TAIPEI = ZoneInfo("Asia/Taipei")
_DATE_FIELD = "日期"
_SYMBOL_FIELD = "證券代號"
_SOURCE_FIELDS = tuple(sorted(set(CANDIDATE_RAW_FIELD_MAP.values()) | set(_OHLC_FIELDS)))
_FEATURE_IDS, _FEATURE_SCALES = expected_feature_contract()
_FEATURE_INDEX = {feature_id: index for index, feature_id in enumerate(_FEATURE_IDS)}


@dataclass(frozen=True)
class CandidateStockSourceIndex:
    profile: CandidateSourceProfile
    profile_reference: dict[str, str]
    snapshot_path: Path
    snapshot_sha256: str
    revision_observed_at: str
    bridge_payload: dict[str, Any]
    bridge_hash: str
    daily_rows_by_symbol: dict[str, list[dict[str, Any]]]
    date_keys_by_symbol: dict[str, list[str]]
    indicator_values_by_symbol_date: dict[str, dict[str, dict[str, int | None]]]
    audit: dict[str, Any]


def _compact_date(value: object) -> str:
    text = str(value).strip()
    if len(text) == 10 and text[4] == "-":
        text = text.replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid candidate source date: {value!r}")
    return text


def _taipei_decision_date(value: object) -> date:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("candidate decision_at must be a non-empty ISO datetime")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("candidate decision_at must be an ISO datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("candidate decision_at must include a timezone")
    return parsed.astimezone(_TAIPEI).date()


def _candidate_price_quality_stats(
    *,
    features: Sequence[Mapping[str, Any]],
    definitions: Mapping[str, Mapping[str, Any]],
    decision_date: date,
    quality_blocked_feature_ids: frozenset[str] = frozenset(),
) -> dict[str, int]:
    """Use source-event dates for the frozen 41-field coverage/staleness formula.

    Candidate feature revisions are available only now, so their publication
    clock cannot also be used as the historical source age.  In the original
    producer these daily source aliases shared the same event and availability
    day; this retains that original stale/null meaning while keeping the late
    candidate clock on the serialized research feature.
    """
    by_id = {str(feature["feature_id"]): feature for feature in features}
    total = len(definitions)
    if total != 41:
        raise ValueError("candidate quality calculation requires the frozen 41 price-family slots")
    observed = missing = stale_count = max_lag = quality_blocked_count = 0
    for feature_id, definition in definitions.items():
        feature = by_id.get(feature_id)
        if feature is None:
            raise ValueError(f"candidate price quality feature is missing: {feature_id}")
        event_clock = datetime.fromisoformat(str(feature["event_at"]).replace("Z", "+00:00"))
        lag = max(0, (decision_date - event_clock.date()).days)
        stale_after = definition.get("stale_after_days")
        if type(stale_after) is not int or stale_after != 7:
            raise ValueError(f"candidate price stale threshold is invalid: {feature_id}")
        stale = lag > stale_after
        max_lag = max(max_lag, lag)
        stale_count += int(stale)
        quality_blocked_count += int(
            feature_id in quality_blocked_feature_ids
            or bool(feature.get("quality_blocked_mask", False))
        )
        is_observed = bool(feature.get("observed")) and feature.get("value_int") is not None and not stale
        observed += int(is_observed)
        missing += int(not is_observed)
    return {
        "coverage_bp": observed * 10_000 // total,
        "missing_count": missing,
        "stale_count": stale_count,
        "quality_blocked_count": quality_blocked_count,
        "max_available_lag_days": max_lag,
    }


def _candidate_eligible_value(
    *,
    feature_id: str,
    source_value: object,
    scale: int,
    event_day: str,
    decision_day: date,
    definition: Mapping[str, Any],
) -> tuple[int | None, bool, bool]:
    if feature_id in {"technical_indicators.涨跌", "technical_indicators.漲跌(+/-)"}:
        # The frozen 62-slot producer deliberately set direction text to null.
        return None, False, False
    stale_after = definition.get("stale_after_days")
    if type(stale_after) is not int or stale_after != 7:
        raise ValueError("candidate source feature stale threshold is invalid")
    source_day = date.fromisoformat(f"{event_day[:4]}-{event_day[4:6]}-{event_day[6:]}")
    if feature_id not in _FEATURE_INDEX or _FEATURE_SCALES[_FEATURE_INDEX[feature_id]] != scale:
        raise ValueError(f"candidate feature does not match the frozen bounded slot: {feature_id}")
    return _feature_eligibility(
        source_value,
        _FEATURE_INDEX[feature_id],
        scale,
        (decision_day - source_day).days,
    )


def _source_revision_clocks(profile: CandidateSourceProfile) -> list[datetime]:
    clocks: list[datetime] = []
    evidence = profile.payload.get("repair_evidence")
    if not isinstance(evidence, dict):
        raise ValueError("candidate profile is missing receipt-bound repair evidence")
    for item in evidence.values():
        if not isinstance(item, dict):
            raise ValueError("candidate profile repair evidence is malformed")
        for key in ("acquired_at", "applied_at", "observed_at", "completed_at"):
            raw = item.get(key)
            if raw is None:
                continue
            if not isinstance(raw, str):
                raise ValueError(f"candidate profile clock is malformed: {key}")
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"candidate profile clock lacks timezone: {key}")
            clocks.append(value.astimezone(timezone.utc))
    market_clock = profile.market_capture.available_at
    if market_clock.tzinfo is None or market_clock.utcoffset() is None:
        raise ValueError("candidate official market capture clock is timezone-naive")
    clocks.append(market_clock.astimezone(timezone.utc))
    source_manifest_path = Path(str(profile.payload["snapshot"]["source_manifest_path"]))
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    raw_created = source_manifest.get("created_at") or source_manifest.get("captured_at")
    if isinstance(raw_created, str):
        created = datetime.fromisoformat(raw_created.replace("Z", "+00:00"))
        if created.tzinfo is None or created.utcoffset() is None:
            raise ValueError("candidate source manifest clock lacks timezone")
        clocks.append(created.astimezone(timezone.utc))
    return clocks


def build_candidate_source_bridge(
    profile: CandidateSourceProfile,
    *,
    revision_observed_at: str,
) -> tuple[dict[str, Any], str]:
    observed = datetime.fromisoformat(revision_observed_at.replace("Z", "+00:00"))
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("candidate source revision clock lacks timezone")
    actual_clocks = _source_revision_clocks(profile)
    if any(observed.astimezone(timezone.utc) < clock for clock in actual_clocks):
        raise ValueError("candidate re-computation clock precedes an input source/receipt")
    evidence = profile.payload.get("repair_evidence")
    scope = profile.payload.get("verified_scope")
    if not isinstance(evidence, dict) or not isinstance(scope, dict):
        raise ValueError("candidate source profile is missing verified scope")
    daily_exclusion = evidence.get("excluded_daily_prices")
    session_evidence = evidence.get("historical_sessions")
    if not isinstance(daily_exclusion, dict) or not isinstance(session_evidence, dict):
        raise ValueError("candidate source profile is missing daily exclusion/session receipts")
    raw_scope = {
        "schema_version": BRIDGE_SCHEMA,
        "source_profile": candidate_profile_reference(profile),
        "snapshot_path": str(profile.snapshot_db),
        "snapshot_sha256": profile.snapshot_sha256,
        "official_market_capture_path": str(profile.market_manifest),
        "official_market_capture_sha256": profile.market_sha256,
        "raw_source_table": "daily_prices",
        "raw_feature_field_map": dict(sorted(CANDIDATE_RAW_FIELD_MAP.items())),
        "technical_alias_transition": {
            "feature_ids": sorted(TECHNICAL_ALIAS_FIELD_MAP),
            "prior_source_id": "sqlite.technical_indicators",
            "candidate_source_id": _DAILY_SOURCE_ID,
            "reason": "legacy technical-indicator post-processing forward/back-filled raw daily quote aliases; use verified daily source and preserve its NULLs",
        },
        "verified_closed_dates": list(scope.get("closed_dates", [])),
        "verified_excluded_key_count": daily_exclusion.get("key_count"),
        "verified_excluded_keys_sha256": daily_exclusion.get("keys_sha256"),
        "verified_exclusion_plan_sha256": daily_exclusion.get("plan_sha256"),
        "verified_exclusion_receipt_sha256": daily_exclusion.get("receipt_sha256"),
        "verified_session_dates": list(scope.get("historical_session_dates", [])),
        "verified_session_plan_sha256": session_evidence.get("plan_sha256"),
        "verified_session_receipt_sha256": session_evidence.get("receipt_sha256"),
        "revision_observed_at": observed.astimezone(timezone.utc).isoformat(),
        "source_availability_lower_bound": max(actual_clocks).isoformat(),
        "historical_pit": False,
    }
    return raw_scope, _sha256_json(raw_scope)


def load_candidate_stock_source_index(
    *,
    profile_path: Path,
    expected_profile_sha256: str,
    snapshot_path: Path,
    expected_snapshot_sha256: str,
    symbols: Sequence[str],
    revision_observed_at: str,
) -> CandidateStockSourceIndex:
    profile = verify_candidate_source_profile(
        profile_path,
        expected_profile_sha256,
        as_of=datetime.now(timezone.utc),
    )
    snapshot = snapshot_path.resolve(strict=True)
    if profile.snapshot_db.resolve(strict=True) != snapshot or profile.snapshot_sha256 != expected_snapshot_sha256:
        raise ValueError("candidate source profile does not bind this bounded snapshot")
    bridge, bridge_hash = build_candidate_source_bridge(
        profile,
        revision_observed_at=revision_observed_at,
    )

    exclusion_rows = excluded_daily_price_revision.load_exclusion_evidence(FORMAL_DATABASE)
    if len(exclusion_rows) != 1:
        raise ValueError("candidate stock source expects exactly one exclusion receipt")
    evidence = exclusion_rows[0]
    excluded_keys = {(str(day), str(symbol)) for day, symbol in evidence["keys"]}
    excluded_dates = {str(day) for day in evidence["closed_dates"]}
    profile_exclusion = profile.payload["repair_evidence"]["excluded_daily_prices"]
    actual_key_hash = "sha256:" + hashlib.sha256(
        (json.dumps([list(key) for key in sorted(excluded_keys)], ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    ).hexdigest()
    if (
        actual_key_hash != profile_exclusion.get("keys_sha256")
        or sorted(excluded_dates) != profile_exclusion.get("closed_dates")
        or evidence.get("plan_sha256") != profile_exclusion.get("plan_sha256")
        or evidence.get("receipt_sha256") != profile_exclusion.get("receipt_sha256")
    ):
        raise ValueError("candidate exact daily exclusions drifted after profile verification")

    selected_symbols = tuple(sorted({str(symbol).strip() for symbol in symbols}))
    if not selected_symbols or any(not symbol for symbol in selected_symbols):
        raise ValueError("candidate bounded symbol universe is empty or malformed")
    fields = (_DATE_FIELD, _SYMBOL_FIELD, *_SOURCE_FIELDS)
    column_sql = ",".join('"' + field.replace('"', '""') + '"' for field in fields)
    placeholders = ",".join("?" for _ in selected_symbols)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    filtered_closed = filtered_exact = 0
    uri = snapshot.as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        cursor = connection.execute(
            f'SELECT {column_sql} FROM "daily_prices" WHERE "證券代號" IN ({placeholders}) ORDER BY "證券代號","日期"',
            selected_symbols,
        )
        for row in cursor:
            day = _compact_date(row[_DATE_FIELD])
            symbol = str(row[_SYMBOL_FIELD]).strip()
            key = (day, symbol)
            if key in seen:
                raise ValueError(f"candidate daily source contains duplicate key: {key}")
            seen.add(key)
            if day in excluded_dates:
                filtered_closed += 1
                continue
            if key in excluded_keys:
                filtered_exact += 1
                continue
            grouped[symbol].append({"date_key": day, **{field: row[field] for field in _SOURCE_FIELDS}})

    daily_rows_by_symbol: dict[str, list[dict[str, Any]]] = {}
    date_keys_by_symbol: dict[str, list[str]] = {}
    indicator_values_by_symbol_date: dict[str, dict[str, dict[str, int | None]]] = {}
    indicator_missing: Counter[str] = Counter()
    total_rows = 0
    rows_by_symbol: dict[str, int] = {}
    for symbol in selected_symbols:
        rows = grouped.get(symbol, [])
        if not rows:
            raise ValueError(f"candidate daily source has no effective history for {symbol}")
        keys = [str(row["date_key"]) for row in rows]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError(f"candidate daily source dates are not unique and ordered for {symbol}")
        frame_rows: list[dict[str, Any]] = []
        for row in rows:
            frame_row: dict[str, Any] = {"日期": f"{row['date_key'][:4]}-{row['date_key'][4:6]}-{row['date_key'][6:]}"}
            for field in _OHLC_FIELDS:
                number, _grouped = _source_decimal(row[field], symbol=symbol, date=str(row["date_key"]), field=field)
                frame_row[field] = np.nan if number is None else float(number)
            frame_rows.append(frame_row)
        frame = pd.DataFrame.from_records(frame_rows)
        calculated = calculate_causal_indicators(frame)
        if len(calculated) != len(rows) or not set(CAUSAL_INDICATOR_COLUMNS) <= set(calculated.columns):
            raise ValueError(f"causal kernel output contract failed for {symbol}")
        values_by_date: dict[str, dict[str, int | None]] = {}
        iter_values = calculated[list(CAUSAL_INDICATOR_COLUMNS)].itertuples(index=False, name=None)
        for source_row, values in zip(rows, iter_values, strict=True):
            values_for_day: dict[str, int | None] = {}
            for column, value in zip(CAUSAL_INDICATOR_COLUMNS, values, strict=True):
                indicator_number = float(value)
                if not math.isfinite(indicator_number):
                    values_for_day[column] = None
                    indicator_missing[column] += 1
                else:
                    scaled = Decimal(str(indicator_number)) * Decimal(10_000)
                    values_for_day[column] = int(scaled.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))
            values_by_date[str(source_row["date_key"])] = values_for_day
        daily_rows_by_symbol[symbol] = rows
        date_keys_by_symbol[symbol] = keys
        indicator_values_by_symbol_date[symbol] = values_by_date
        rows_by_symbol[symbol] = len(rows)
        total_rows += len(rows)
    audit = {
        "effective_rows_by_symbol": dict(sorted(rows_by_symbol.items())),
        "effective_daily_rows": total_rows,
        "filtered_closed_date_rows_for_bounded_symbols": filtered_closed,
        "filtered_exact_exclusion_rows_for_bounded_symbols": filtered_exact,
        "indicator_missing_values_by_column": dict(sorted(indicator_missing.items())),
        "raw_source_table": "daily_prices",
        "technical_indicators_table_read": False,
        "sqlite_mode": "mode=ro",
        "sqlite_query_only": True,
    }
    return CandidateStockSourceIndex(
        profile=profile,
        profile_reference=candidate_profile_reference(profile),
        snapshot_path=snapshot,
        snapshot_sha256=expected_snapshot_sha256,
        revision_observed_at=datetime.fromisoformat(revision_observed_at.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(),
        bridge_payload=bridge,
        bridge_hash=bridge_hash,
        daily_rows_by_symbol=daily_rows_by_symbol,
        date_keys_by_symbol=date_keys_by_symbol,
        indicator_values_by_symbol_date=indicator_values_by_symbol_date,
        audit=audit,
    )


def _source_event_at(day: str) -> str:
    return datetime.combine(
        date.fromisoformat(f"{day[:4]}-{day[4:6]}-{day[6:]}"),
        time(14, 30),
        _TAIPEI,
    ).isoformat()


def _candidate_payload(
    *,
    source: CandidateStockSourceIndex,
    identity_hash: str,
    row_id: str,
    feature_id: str,
    family_id: str,
    source_id: str,
    source_column: str,
    source_date: str,
    value_int: int | None,
    scale: int,
    event_at: str,
    quality: str,
) -> dict[str, Any]:
    available_at = source.revision_observed_at
    observed = value_int is not None
    revision_id = _sha256_json({
        "schema_version": BRIDGE_SCHEMA,
        "dataset_identity_hash": identity_hash,
        "candidate_source_profile_sha256": source.profile.profile_file_sha256,
        "bridge_hash": source.bridge_hash,
        "row_id": row_id,
        "feature_id": feature_id,
        "source_date": source_date,
        "source_column": source_column,
        "source_id": source_id,
        "value_int": value_int,
        "scale": scale,
    })
    content_hash = _sha256_json({
        "schema_version": BRIDGE_SCHEMA,
        "dataset_identity_hash": identity_hash,
        "candidate_snapshot_sha256": source.snapshot_sha256,
        "candidate_source_profile_sha256": source.profile.profile_file_sha256,
        "bridge_hash": source.bridge_hash,
        "feature_id": feature_id,
        "source_id": source_id,
        "source_table": "daily_prices",
        "source_column": source_column,
        "source_date": source_date,
        "event_at": event_at,
        "available_at": available_at,
        "value_int": value_int,
        "scale": scale,
    })
    return {
        "feature_id": feature_id,
        "family_id": family_id,
        "source_id": source_id,
        "value_int": value_int,
        "scale": scale,
        "event_at": event_at,
        "available_at": available_at,
        "revision_id": revision_id,
        "quality": quality if observed else "missing",
        "content_hash": content_hash,
        "observed": observed,
        "event_time_semantics": "realized_observation",
    }


def rebuild_candidate_stock_features(
    *,
    source: CandidateStockSourceIndex,
    features: Sequence[Mapping[str, Any]],
    row_id: str,
    symbol: str,
    decision_at: str,
    definitions: Mapping[str, Mapping[str, Any]],
    identity_hash: str,
) -> list[dict[str, Any]]:
    if len(features) != 62:
        raise ValueError("candidate bounded row must retain the 62-slot ABI")
    ids = tuple(str(feature.get("feature_id", "")) for feature in features)
    if len(set(ids)) != 62 or not CANDIDATE_STOCK_FEATURE_IDS <= set(ids):
        raise ValueError("candidate bounded row feature IDs differ from the frozen stock feature scope")
    decision_day = _taipei_decision_date(decision_at)
    compact_decision = decision_day.strftime("%Y%m%d")
    keys = source.date_keys_by_symbol.get(str(symbol))
    rows = source.daily_rows_by_symbol.get(str(symbol))
    if not keys or not rows:
        raise ValueError(f"candidate daily source missing symbol {symbol}")
    index = bisect_left(keys, compact_decision) - 1
    if index < 0:
        raise ValueError(f"candidate daily source has no T-1 prefix for {symbol}/{compact_decision}")
    source_row = rows[index]
    event_day = str(source_row["date_key"])
    event_at = _source_event_at(event_day)
    result: list[dict[str, Any]] = []
    raw_value_by_id: dict[str, dict[str, Any]] = {}
    quality_blocked_feature_ids: set[str] = set()
    for original in features:
        feature = dict(original)
        feature_id = str(feature["feature_id"])
        if feature_id not in CANDIDATE_RAW_FIELD_MAP:
            result.append(feature)
            continue
        definition = definitions.get(feature_id)
        if definition is None:
            raise ValueError(f"candidate raw feature is absent from frozen registry: {feature_id}")
        scale = definition.get("scale")
        if type(scale) is not int or scale <= 0 or feature.get("scale") != scale:
            raise ValueError(f"candidate raw feature scale changed: {feature_id}")
        source_column = CANDIDATE_RAW_FIELD_MAP[feature_id]
        value_int, _stale, blocked = _candidate_eligible_value(
            feature_id=feature_id,
            source_value=source_row.get(source_column),
            scale=scale,
            event_day=event_day,
            decision_day=decision_day,
            definition=definition,
        )
        if blocked:
            quality_blocked_feature_ids.add(feature_id)
        quality = "observed" if value_int is not None else "missing"
        feature.update(_candidate_payload(
            source=source,
            identity_hash=identity_hash,
            row_id=row_id,
            feature_id=feature_id,
            family_id=str(feature["family_id"]),
            source_id=_DAILY_SOURCE_ID,
            source_column=source_column,
            source_date=event_day,
            value_int=value_int,
            scale=scale,
            event_at=event_at,
            quality=quality,
        ))
        raw_value_by_id[feature_id] = {
            "field": source_column,
            "value_int": value_int,
            "event_date": event_day,
        }
        result.append(feature)

    indicator_values = source.indicator_values_by_symbol_date.get(str(symbol), {}).get(event_day)
    if indicator_values is None:
        raise ValueError(f"candidate causal indicators missing for {symbol}/{event_day}")
    technical_positions: dict[int, tuple[str, int | None]] = {}
    for position, feature in enumerate(result):
        feature_id = str(feature["feature_id"])
        if feature_id not in TECHNICAL_FEATURE_IDS:
            continue
        column = feature_id.removeprefix("technical_indicators.")
        definition = definitions.get(feature_id)
        if definition is None or definition.get("scale") != 10_000 or feature.get("scale") != 10_000:
            raise ValueError(f"candidate causal feature scale/registry mismatch: {feature_id}")
        indicator_value = indicator_values[column]
        value_int, _stale, blocked = _candidate_eligible_value(
            feature_id=feature_id,
            source_value=(
                None
                if indicator_value is None
                else Decimal(indicator_value) / Decimal(10_000)
            ),
            scale=10_000,
            event_day=event_day,
            decision_day=decision_day,
            definition=definition,
        )
        if blocked:
            quality_blocked_feature_ids.add(feature_id)
        feature.update(_candidate_payload(
            source=source,
            identity_hash=identity_hash,
            row_id=row_id,
            feature_id=feature_id,
            family_id=PRICE_FAMILY,
            source_id=TECHNICAL_SOURCE_ID,
            source_column=column,
            source_date=event_day,
            value_int=value_int,
            scale=10_000,
            event_at=event_at,
            quality="estimated" if value_int is not None else "missing",
        ))
        technical_positions[position] = (column, value_int)

    price_definitions = {
        feature_id: definition
        for feature_id, definition in definitions.items()
        if definition.get("family_id") == PRICE_FAMILY
    }
    quality_stats = _candidate_price_quality_stats(
        features=result,
        definitions=price_definitions,
        decision_date=decision_day,
        quality_blocked_feature_ids=frozenset(quality_blocked_feature_ids),
    )
    for position, feature in enumerate(result):
        feature_id = str(feature["feature_id"])
        if feature_id not in QUALITY_FEATURE_IDS:
            continue
        definition = definitions.get(feature_id)
        if feature.get("scale") != 1 or (definition is not None and definition.get("scale") != 1):
            raise ValueError(f"candidate quality feature scale/registry mismatch: {feature_id}")
        metric = feature_id.rsplit(".", 1)[-1]
        value_int = quality_stats[metric]
        feature.update(_candidate_payload(
            source=source,
            identity_hash=identity_hash,
            row_id=row_id,
            feature_id=feature_id,
            family_id="data_quality",
            source_id=QUALITY_SOURCE_ID,
            source_column=metric,
            source_date=event_day,
            value_int=value_int,
            scale=1,
            event_at=decision_at,
            quality="estimated",
        ))
    if tuple(str(feature["feature_id"]) for feature in result) != ids:
        raise ValueError("candidate stock feature rebuild changed slot order")
    if len(raw_value_by_id) != len(CANDIDATE_RAW_FEATURE_IDS) or len(technical_positions) != len(TECHNICAL_FEATURE_IDS):
        raise ValueError("candidate stock feature rebuild did not fill the complete approved slot set")
    return result


def candidate_stock_feature_registry(
    registry: Mapping[str, Any],
    *,
    profile_sha256: str,
    bridge_hash: str,
) -> dict[str, Any]:
    features = registry.get("features")
    if not isinstance(features, list):
        raise ValueError("candidate stock registry features are missing")
    copied = json.loads(json.dumps(registry))
    by_id = {str(item["feature_id"]): item for item in copied["features"] if isinstance(item, dict)}
    # 登錄表只登錄來源欄位；十個品質統計由 assembler 衍生，存在於
    # 62 欄模型列中，不是 source registry definitions。此處只驗來源欄位，
    # 完整股票 slots（含五個品質統計）仍由 row rebuild 驗證。
    required_source_ids = CANDIDATE_RAW_FEATURE_IDS | frozenset(TECHNICAL_FEATURE_IDS)
    if not required_source_ids <= set(by_id):
        raise ValueError("candidate stock registry lacks approved feature IDs")
    for feature_id, source_column in CANDIDATE_RAW_FIELD_MAP.items():
        item = by_id[feature_id]
        prior_source_id = str(item.get("source_id", ""))
        if feature_id in TECHNICAL_ALIAS_FIELD_MAP and prior_source_id != "sqlite.technical_indicators":
            raise ValueError(f"technical source bridge expected legacy source sqlite.technical_indicators: {feature_id}")
        if feature_id in DAILY_RAW_FIELD_MAP and prior_source_id != _DAILY_SOURCE_ID:
            raise ValueError(f"daily raw source is not the canonical daily table: {feature_id}")
        prior_record_hash = item.get("record_hash")
        item["source_id"] = _DAILY_SOURCE_ID
        item["table_name"] = "daily_prices"
        item["record_hash"] = _sha256_json({
            "schema_version": BRIDGE_SCHEMA,
            "prior_record_hash": prior_record_hash,
            "feature_id": feature_id,
            "source_id": _DAILY_SOURCE_ID,
            "table_name": "daily_prices",
            "source_column": source_column,
            "scale": item["scale"],
            "candidate_source_profile_sha256": profile_sha256,
            "candidate_source_bridge_hash": bridge_hash,
        })
    copied["features"].sort(key=lambda item: str(item["feature_id"]))
    return copied


def validate_candidate_stock_source_bridge(
    bridge: Mapping[str, Any],
    *,
    profile: CandidateSourceProfile,
    profile_sha256: str,
    revision_observed_at: str,
) -> str:
    expected, bridge_hash = build_candidate_source_bridge(
        profile,
        revision_observed_at=revision_observed_at,
    )
    if bridge_sha256(bridge) != bridge_hash or bridge != expected:
        raise ValueError("candidate bounded daily-source bridge differs from validated profile")
    if profile.profile_file_sha256 != profile_sha256:
        raise ValueError("candidate bounded profile SHA differs from validated profile")
    return bridge_hash


def bridge_sha256(bridge: Mapping[str, Any]) -> str:
    return _sha256_json(dict(bridge))
