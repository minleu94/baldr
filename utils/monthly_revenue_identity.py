"""純月營收來源識別與版本摘要；不讀取檔案、資料庫或網路。"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re


MONTHLY_SNAPSHOT_SOURCE = "mops.monthly_revenue_static_snapshot"
MONTHLY_NORMALIZER_VERSION = "mops-current-revenue-normalizer.v2"
OPENAPI_MONTHLY_SOURCE_IDS: dict[str, str] = {
    "twse": "twse.openapi.t187ap05_L",
    "tpex": "tpex.openapi.mopsfin_t187ap05_O",
}
OPENAPI_MONTHLY_NORMALIZER_VERSION = "twse-tpex-openapi-monthly-revenue-parser.v1"
MONTHLY_YOY_COMPARATOR_VERSION = "mops-current-revenue-yoy-comparator.v1"


def is_monthly_source_version(version: str, *, market: str, period: str) -> bool:
    parts = monthly_source_version_parts(version)
    return parts is not None and parts[0] == market and parts[1] == period


def monthly_source_version_identity(version: str) -> tuple[str, str, str, str] | None:
    parsed = _raw_source_version_parts(version)
    if parsed is None:
        return None
    source_id, market, period, digest, _capture_text = parsed
    return source_id, market, period, digest


def monthly_source_available_at(version: str, *, market: str, period: str) -> str:
    """回傳新來源版本明確綁定的 body 完成時間；舊批次沒有則留空。"""
    parts = _raw_source_version_parts(version)
    if parts is None:
        return ""
    _source_id, version_market, version_period, _digest, capture_text = parts
    if version_market != market or version_period != period:
        raise ValueError("monthly source capture time does not match source identity")
    if capture_text is None:
        return ""
    return parse_utc_timestamp(capture_text, "monthly source capture time").isoformat()


def derived_monthly_source_version(
    raw_source_version: str,
    *,
    stock_code: str,
    period: str,
    value: str,
    unit: str,
    source_available_at: str,
) -> str:
    parts = monthly_source_version_parts(raw_source_version)
    if parts is None or parts[1] != period:
        raise ValueError("official monthly raw source version does not match period")
    market = parts[0]
    normalizer = (
        OPENAPI_MONTHLY_NORMALIZER_VERSION
        if raw_source_version.startswith(tuple(f"{item}.v1:" for item in OPENAPI_MONTHLY_SOURCE_IDS.values()))
        else MONTHLY_NORMALIZER_VERSION
    )
    payload = "\0".join(
        (
            normalizer,
            raw_source_version,
            stock_code,
            period,
            "revenue",
            value,
            unit,
            source_available_at,
            "monthly_flow",
            "basis_verified=1",
            "aggregate_feature_eligible=0",
        )
    ).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return f"{normalizer}:{market}:{period}:raw:{raw_source_version}:derived:sha256:{digest}"


def is_monthly_derived_source_version(
    version: str,
    *,
    market: str,
    period: str,
    stock_code: str,
    value: str,
    unit: str,
    source_available_at: str,
) -> bool:
    parts = monthly_derived_source_version_parts(version)
    if parts is None or parts[1] != market or parts[2] != period:
        return False
    normalizer, _, _, raw_source_version, _digest = parts
    if not is_monthly_source_version(raw_source_version, market=market, period=period):
        return False
    expected_normalizer = (
        OPENAPI_MONTHLY_NORMALIZER_VERSION
        if raw_source_version.startswith(tuple(f"{item}.v1:" for item in OPENAPI_MONTHLY_SOURCE_IDS.values()))
        else MONTHLY_NORMALIZER_VERSION
    )
    if normalizer != expected_normalizer:
        return False
    if monthly_source_available_at(
        raw_source_version, market=market, period=period
    ) != source_available_at:
        return False
    try:
        return version == derived_monthly_source_version(
            raw_source_version,
            stock_code=stock_code,
            period=period,
            value=value,
            unit=unit,
            source_available_at=source_available_at,
        )
    except ValueError:
        return False


def derived_monthly_yoy_comparator_version(
    raw_source_version: str,
    *,
    stock_code: str,
    source_period: str,
    comparator_period: str,
    value: str,
    unit: str,
    source_available_at: str,
) -> str:
    parts = monthly_source_version_parts(raw_source_version)
    expected_prior = f"{int(source_period[:4]) - 1:04d}-{source_period[5:]}"
    if parts is None or parts[1] != source_period or comparator_period != expected_prior:
        raise ValueError("monthly comparator period does not match its source report")
    payload = "\0".join(
        (
            MONTHLY_YOY_COMPARATOR_VERSION,
            raw_source_version,
            stock_code,
            source_period,
            comparator_period,
            value,
            unit,
            source_available_at,
            "monthly_flow",
            "basis_verified=1",
            "aggregate_feature_eligible=0",
            "availability_basis=current_report_local_observation",
        )
    ).encode("utf-8")
    return (
        f"{MONTHLY_YOY_COMPARATOR_VERSION}:{parts[0]}:{comparator_period}"
        f":from:{source_period}:raw:{raw_source_version}:derived:sha256:"
        f"{hashlib.sha256(payload).hexdigest()}"
    )


def is_monthly_yoy_comparator_source_version(
    version: str,
    *,
    market: str,
    comparator_period: str,
    stock_code: str,
    value: str,
    unit: str,
    source_available_at: str,
) -> bool:
    parts = monthly_yoy_comparator_source_version_parts(version)
    if parts is None or parts[0] != market or parts[1] != comparator_period:
        return False
    _market, _comparator_period, source_period, raw_source_version, _digest = parts
    if monthly_source_version_parts(raw_source_version) is None:
        return False
    raw_parts = monthly_source_version_parts(raw_source_version)
    if raw_parts is None or raw_parts[:2] != (market, source_period):
        return False
    if monthly_source_available_at(
        raw_source_version, market=market, period=source_period
    ) != source_available_at:
        return False
    try:
        return version == derived_monthly_yoy_comparator_version(
            raw_source_version,
            stock_code=stock_code,
            source_period=source_period,
            comparator_period=comparator_period,
            value=value,
            unit=unit,
            source_available_at=source_available_at,
        )
    except ValueError:
        return False


def parse_utc_timestamp(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def monthly_source_version_parts(version: str) -> tuple[str, str, str] | None:
    identity = monthly_source_version_identity(version)
    if identity is None:
        return None
    _source_id, market, period, digest = identity
    return market, period, digest


def monthly_derived_source_version_parts(
    version: str,
) -> tuple[str, str, str, str, str] | None:
    match = re.fullmatch(
        r"(mops-current-revenue-normalizer\.v2|twse-tpex-openapi-monthly-revenue-parser\.v1):"
        r"(twse|tpex):(\d{4}-\d{2}):raw:(.+):derived:sha256:([0-9a-f]{64})",
        version,
    )
    if match is None:
        return None
    normalizer, market, period, raw_source_version, digest = match.groups()
    return normalizer, market, period, raw_source_version, digest


def monthly_yoy_comparator_source_version_parts(
    version: str,
) -> tuple[str, str, str, str, str] | None:
    match = re.fullmatch(
        r"mops-current-revenue-yoy-comparator\.v1:(twse|tpex):"
        r"(\d{4}-\d{2}):from:(\d{4}-\d{2}):raw:(.+):derived:sha256:"
        r"([0-9a-f]{64})(?::verified-csv-sha256:([0-9a-f]{64}))?",
        version,
    )
    if match is None:
        return None
    market, comparator_period, source_period, raw_source_version, digest, _csv_sha = match.groups()
    return market, comparator_period, source_period, raw_source_version, digest


def _raw_source_version_parts(
    version: str,
) -> tuple[str, str, str, str, str | None] | None:
    legacy = re.fullmatch(
        r"mops-static-(twse|tpex)-(\d{4}-\d{2})-sha256-([0-9a-f]{64})",
        version,
    )
    if legacy is not None:
        market, period, digest = legacy.groups()
        return MONTHLY_SNAPSHOT_SOURCE, market, period, digest, None
    current = re.fullmatch(
        r"mops-static-snapshot\.v2:(twse|tpex):(\d{4}-\d{2}):"
        r"body_completed_at:(.+):sha256:([0-9a-f]{64})",
        version,
    )
    if current is not None:
        market, period, capture_text, digest = current.groups()
        parse_utc_timestamp(capture_text, "monthly source capture time")
        return MONTHLY_SNAPSHOT_SOURCE, market, period, digest, capture_text
    opendata = re.fullmatch(
        r"(twse\.openapi\.t187ap05_L|tpex\.openapi\.mopsfin_t187ap05_O)\.v1:"
        r"(twse|tpex):(\d{4}-\d{2}):body_completed_at:(.+):sha256:([0-9a-f]{64})",
        version,
    )
    if opendata is None:
        return None
    source_id, market, period, capture_text, digest = opendata.groups()
    if source_id != OPENAPI_MONTHLY_SOURCE_IDS.get(market):
        return None
    parse_utc_timestamp(capture_text, "monthly source capture time")
    return source_id, market, period, digest, capture_text
