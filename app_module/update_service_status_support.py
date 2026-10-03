from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from app_module.dtos.update_loop_dtos import enrich_status_mapping


_DATE_ALIGNED_SOURCES = {
    "market_index",
    "industry_index",
    "broker_branch",
    "technical_indicators",
}

_FRESHNESS_SOURCE_TO_STATUS = {
    "twse.daily_prices.raw": "daily_data",
    "tpex.daily_prices.raw": "daily_data",
    "sqlite.daily_prices": "daily_data",
    "sqlite.market_indices": "market_index",
    "sqlite.industry_indices": "industry_index",
    "sqlite.broker_flows": "broker_branch",
    "sqlite.technical_indicators": "technical_indicators",
    "fundamental.monthly_revenues": "monthly_revenue",
    "fundamental.quarterly_statements": "quarterly_statements",
    "institutional_flows": "institutional_flow",
    "credit_transactions": "credit_transaction",
    "tdcc_shareholding": "tdcc_shareholding",
}

_FRESHNESS_SEVERITY = {
    "current": 0,
    "not_applicable": 0,
    "expected_wait": 1,
    "partial": 2,
    "stale": 2,
    "failed": 3,
    "unknown": 3,
}

_TAIPEI = ZoneInfo("Asia/Taipei")


@dataclass(frozen=True)
class FreshnessReceiptBinding:
    """將 freshness receipt 綁定到目前唯讀狀態查詢的資料邊界。"""

    data_root: str
    db_path: str
    output_root: str
    evaluated_at: datetime
    candidate_db_path: str | None = None
    calendar_cutoff_local: str = "04:30"


def _normalized_path(value: Any) -> str | None:
    if not isinstance(value, (str, Path)) or not str(value).strip():
        return None
    try:
        return str(Path(value).expanduser().resolve()).casefold()
    except (OSError, RuntimeError, ValueError):
        return None


def _parse_aware_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _parse_cutoff_local(value: Any) -> time | None:
    """只接受固定 HH:MM 格式的本地 freshness cutoff。"""
    if (
        not isinstance(value, str)
        or len(value) != 5
        or value[2] != ":"
        or not value[:2].isdigit()
        or not value[3:].isdigit()
    ):
        return None
    try:
        return time(int(value[:2]), int(value[3:]))
    except ValueError:
        return None


def _canonical_period(value: Any) -> str | None:
    """只正規化完整日期、年月或季度，不接受前綴相符的髒字串。"""
    if value is None:
        return None
    raw = str(value).strip()
    if len(raw) == 8 and raw.isdigit():
        try:
            return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8])).isoformat()
        except ValueError:
            return None
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        try:
            return date.fromisoformat(raw).isoformat()
        except ValueError:
            return None
    if len(raw) == 6 and raw.isdigit():
        year, month = int(raw[:4]), int(raw[4:])
        if 1 <= month <= 12:
            return f"{year:04d}-{month:02d}"
        return None
    if len(raw) == 7 and raw[4] == "-":
        try:
            year, month = int(raw[:4]), int(raw[5:])
        except ValueError:
            return None
        return f"{year:04d}-{month:02d}" if 1 <= month <= 12 else None
    if len(raw) == 7 and raw[:4].isdigit() and raw[4:6] == "-Q" and raw[6] in "1234":
        return raw
    if len(raw) == 6 and raw[:4].isdigit() and raw[4] == "Q" and raw[5] in "1234":
        return f"{raw[:4]}-Q{raw[5]}"
    return None


def _receipt_binding_error(
    receipt: Mapping[str, Any],
    binding: FreshnessReceiptBinding,
    statuses: Mapping[str, Mapping[str, Any]],
) -> str | None:
    if binding.evaluated_at.tzinfo is None or binding.evaluated_at.utcoffset() is None:
        return "狀態查詢時鐘不是含時區的時間"
    checks = receipt.get("checks")
    if not isinstance(checks, Mapping):
        return "receipt 缺少 checks 綁定資訊"
    cutoff = _parse_cutoff_local(binding.calendar_cutoff_local)
    if cutoff is None:
        return "目前 freshness cutoff 格式無效"
    for key, expected in (
        ("data_root", binding.data_root),
        ("output_root", binding.output_root),
    ):
        if _normalized_path(receipt.get(key)) != _normalized_path(expected):
            return f"receipt {key} 與目前設定不符"
    if _normalized_path(checks.get("db_path")) != _normalized_path(binding.db_path):
        return "receipt SQLite 路徑與目前資料庫不符"
    if checks.get("calendar_cutoff_local") != binding.calendar_cutoff_local:
        return "receipt 日曆 cutoff 與目前政策不符"
    checked_at = _parse_aware_timestamp(receipt.get("checked_at"))
    evaluated_at = binding.evaluated_at.astimezone(timezone.utc)
    if checked_at is None:
        return "receipt checked_at 缺少有效時區或格式錯誤"
    if checked_at > evaluated_at:
        return "receipt checked_at 晚於目前狀態查詢時間"
    checked_local = checked_at.astimezone(_TAIPEI)
    evaluated_local = evaluated_at.astimezone(_TAIPEI)
    if checked_local.date() != evaluated_local.date():
        return "receipt checked_at 已跨過台灣市場日"
    if checked_local.time() < cutoff <= evaluated_local.time():
        return "receipt checked_at 與查詢時間跨越 freshness cutoff，需重新驗證"
    candidate = checks.get("phase3c_candidate_db")
    if not isinstance(candidate, Mapping):
        return "receipt 缺少 Candidate DB 路徑狀態"
    expected_candidate = _normalized_path(binding.candidate_db_path)
    actual_candidate = _normalized_path(candidate.get("path"))
    if expected_candidate != actual_candidate:
        return "receipt Candidate DB 路徑與目前設定不符"
    candidate_status = str(candidate.get("status", "")).strip().lower()
    if binding.candidate_db_path is None:
        expected_status = "not_configured"
    else:
        try:
            expected_status = "available" if Path(binding.candidate_db_path).is_file() else "missing"
        except OSError:
            expected_status = "invalid"
    if candidate_status != expected_status:
        return "receipt Candidate DB 狀態與目前檔案狀態不符"
    for check_key, status_key in (
        ("daily_prices_latest_date", "daily_data"),
        ("technical_indicators_latest_date", "technical_indicators"),
    ):
        if check_key not in checks or status_key not in statuses:
            continue
        checked_period = _canonical_period(checks.get(check_key))
        current_payload = statuses.get(status_key, {})
        current_period = _canonical_period(
            current_payload.get("latest_period") or current_payload.get("latest_date")
        )
        if checked_period != current_period:
            return f"receipt {check_key} 與目前 SQLite 期別不符"
    return None


def _canonical_date(value: Any) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw or raw.lower() in {"nan", "nat", "none", "未知", "無"}:
        return None
    if len(raw) >= 8 and raw[:8].isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw[:10]


def apply_freshness_receipt(
    statuses: Mapping[str, Mapping[str, Any]],
    receipt: Mapping[str, Any] | None,
    *,
    binding: FreshnessReceiptBinding | None = None,
) -> dict[str, dict[str, Any]]:
    """Project the read-only scheduled freshness receipt into update status DTO input.

    The probe remains the owner of source reconciliation.  This projection only
    copies its explicit state/reason/coverage into the existing update-page
    mapping; it never infers freshness from a newer ``MAX(date)``.
    """

    result = {source: dict(payload) for source, payload in statuses.items()}
    if not isinstance(receipt, Mapping):
        return result

    receipt_status = str(receipt.get("status", "unknown")).strip().lower()
    checked_at = receipt.get("checked_at")
    binding_error = (
        _receipt_binding_error(receipt, binding, result)
        if binding is not None
        else None
    )
    source_items = receipt.get("source_statuses")
    if not isinstance(source_items, list):
        source_items = []
    for payload in result.values():
        payload["freshness_probe_status"] = (
            "needs_revalidation" if binding_error else receipt_status
        )
        payload["freshness_probe_checked_at"] = checked_at
        if binding_error:
            payload["freshness_status"] = "unknown"
            payload["freshness_reason"] = f"receipt 未通過目前資料綁定：{binding_error}"
            if not str(payload.get("status", "")).lower().startswith(("error", "failed")):
                payload["status"] = "lagging"
        if receipt_status == "failed":
            payload.setdefault("freshness_probe_errors", list(receipt.get("errors", [])))

    if binding_error:
        return result

    selected: dict[str, tuple[int, Mapping[str, Any]]] = {}
    for item in source_items:
        if not isinstance(item, Mapping):
            continue
        status_key = _FRESHNESS_SOURCE_TO_STATUS.get(str(item.get("source_id", "")))
        if status_key is None or status_key not in result:
            continue
        freshness_status = str(item.get("freshness_status", "unknown")).strip().lower()
        severity = _FRESHNESS_SEVERITY.get(freshness_status, 3)
        previous = selected.get(status_key)
        if previous is None or severity > previous[0]:
            selected[status_key] = (severity, item)

    for status_key, (_severity, item) in selected.items():
        payload = result[status_key]
        freshness_status = str(item.get("freshness_status", "unknown")).strip().lower()
        if binding is not None:
            current_period = _canonical_period(
                payload.get("latest_period")
                or payload.get("latest_date")
                or payload.get("latest_available_period")
            )
            receipt_period = _canonical_period(item.get("actual_period"))
            # A receipt describes a particular observed period. If the live
            # database has moved since that observation, the old status cannot
            # label the new rows current or stale; a fresh probe is required.
            if current_period is None or receipt_period is None or current_period != receipt_period:
                payload["freshness_status"] = "unknown"
                payload["freshness_probe_status"] = "needs_revalidation"
                payload["freshness_reason"] = (
                    "receipt 的資料期別無法對應目前 SQLite 狀態，需重新驗證"
                    if current_period is None or receipt_period is None
                    else f"receipt 實際期別 {receipt_period} 與目前資料 {current_period} 不同，需重新驗證"
                )
                if not str(payload.get("status", "")).lower().startswith(("error", "failed")):
                    payload["status"] = "lagging"
                continue
        payload["freshness_status"] = freshness_status
        payload["freshness_reason"] = item.get("reason")
        payload["freshness_expected_period"] = item.get("expected_period")
        payload["freshness_actual_period"] = item.get("actual_period")
        payload["freshness_available_at"] = item.get("available_at")
        payload["freshness_coverage"] = dict(item.get("coverage", {})) if isinstance(item.get("coverage"), Mapping) else item.get("coverage")
        payload["freshness_missing_periods"] = list(item.get("missing_periods", []))
        # Keep the legacy status vocabulary usable by existing widgets/DTOs,
        # while exposing the precise status above for new consumers.
        if freshness_status in {"failed", "unknown"}:
            payload["status"] = "error"
        elif freshness_status in {"stale", "partial", "expected_wait"}:
            payload["status"] = "lagging"
    return result


def compose_sqlite_status_read_model(
    statuses: Mapping[str, Mapping[str, Any]],
    *,
    is_overview: bool = False,
    apply_freshness: bool = False,
    include_contract: bool = False,
    freshness_receipt: Mapping[str, Any] | None = None,
    freshness_binding: FreshnessReceiptBinding | None = None,
) -> dict[str, dict[str, Any]]:
    """以既有 SQLite status payload 組裝唯讀回傳模型。"""
    result = {source: dict(payload) for source, payload in statuses.items()}
    if is_overview:
        for payload in result.values():
            payload["is_overview"] = True
    if apply_freshness:
        reference_date = _canonical_date(
            result.get("daily_data", {}).get("latest_date")
            if isinstance(result.get("daily_data"), Mapping)
            else None
        )
        if reference_date:
            daily_payload = result.get("daily_data")
            if isinstance(daily_payload, dict):
                daily_payload["freshness_status"] = "reference"
                daily_payload["freshness_reference_date"] = reference_date
            for source in _DATE_ALIGNED_SOURCES:
                source_payload = result.get(source)
                if not isinstance(source_payload, dict):
                    continue
                raw_status = str(source_payload.get("status", "")).strip().lower()
                latest_date = _canonical_date(source_payload.get("latest_date"))
                if raw_status.startswith(("error", "failed", "failure", "exception")):
                    source_payload["freshness_status"] = "error"
                    continue
                if latest_date is None:
                    source_payload["freshness_status"] = "unknown"
                    continue
                source_payload["freshness_reference_date"] = reference_date
                if latest_date < reference_date:
                    source_payload["freshness_status"] = "lagging"
                    source_payload["status"] = "lagging"
                else:
                    source_payload["freshness_status"] = "current"
    if freshness_receipt is not None:
        result = apply_freshness_receipt(
            result,
            freshness_receipt,
            binding=freshness_binding,
        )
    if include_contract:
        return enrich_status_mapping(result)
    return result
