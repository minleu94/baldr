"""Versioned identity contracts for V4 research evidence.

推薦證據同時需要兩個不同的 universe 身份：跨日比較用的政策身份，以及
保留決策日實際成分的每日快照身份。兩者不可互相取代；政策身份不能包含
當日日期或當日選出的代號，快照身份則必須保留這些內容的雜湊與追溯來源。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from typing import Any


SCHEDULED_RECOMMENDATION_STRATEGY_VERSION_ID = "scheduled-recommendation-default-v1"
SCHEDULED_RECOMMENDATION_COST_MODEL_ID = "gross-close-to-close-no-cost-v1"
SCHEDULED_RECOMMENDATION_BENCHMARK_ID = "TAIEX"
SCHEDULED_RECOMMENDATION_PRIMARY_HORIZON_DAYS = 20

UNIVERSE_POLICY_SCHEMA = "recommendation-universe-policy.v1"
UNIVERSE_SNAPSHOT_SCHEMA = "recommendation-universe-snapshot.v1"
STRATEGY_CONFIG_SCHEMA = "recommendation-strategy-config.v1"
UNIVERSE_SELECTION_ALGORITHM = "ordered-candidate-frame-v1"
DEFAULT_RETURN_BASIS = "close_to_close_event_date"

# Forward outcome storage evaluates every declared window.  The primary
# horizon is kept separately in the event identity for cohort reporting.
SCHEDULED_RECOMMENDATION_OUTCOME_WINDOWS = (5, 10, 20, 60)

UNMODELED_COST_MODEL_IDS = frozenset({SCHEDULED_RECOMMENDATION_COST_MODEL_ID})


def build_recommendation_universe_identity(
    *,
    decision_date: str | None,
    selection_mode: str,
    industry_filter: str,
    max_stocks: int,
    requested_codes: list[str] | tuple[str, ...] | None,
    selected_codes: list[str] | tuple[str, ...],
    source_provider_id: str,
) -> dict[str, Any]:
    """建立穩定政策身份與不可變每日快照身份。

    ``universe_policy_*`` 只描述跨日不變的選股政策；``universe_snapshot_*``
    另外保存決策日、當日實際成分與內容 hash。顯式 universe 的請求代號是
    政策的一部分，動態市場 universe 則不把當日選出代號放入政策 hash。
    """

    normalized_requested = _normalized_codes(requested_codes)
    normalized_selected = _normalized_codes(selected_codes)
    policy_payload: dict[str, Any] = {
        "schema": UNIVERSE_POLICY_SCHEMA,
        "selection_algorithm": UNIVERSE_SELECTION_ALGORITHM,
        "selection_mode": str(selection_mode).strip(),
        "industry_filter": str(industry_filter or "全部").strip(),
        "max_stocks": int(max_stocks),
        "source_provider_id": str(source_provider_id).strip(),
    }
    if requested_codes is not None:
        policy_payload["requested_codes"] = list(normalized_requested)

    policy_digest = _sha256_digest(policy_payload)
    policy_hash = f"sha256:{policy_digest}"
    policy_id = f"recommendation-universe-policy-v1:{policy_digest}"

    selected_codes_digest = _sha256_digest(
        {"selected_codes": list(normalized_selected)}
    )

    snapshot_payload = {
        "schema": UNIVERSE_SNAPSHOT_SCHEMA,
        "universe_policy_id": policy_id,
        "source_provider_id": str(source_provider_id).strip(),
        "decision_date": str(decision_date or "").strip(),
        "selection_mode": str(selection_mode).strip(),
        "selected_codes": list(normalized_selected),
        "selected_count": len(normalized_selected),
        "selected_codes_hash": f"sha256:{selected_codes_digest}",
        "requested_codes": list(normalized_requested) if requested_codes is not None else None,
    }
    snapshot_digest = _sha256_digest(snapshot_payload)
    snapshot_hash = f"sha256:{snapshot_digest}"
    snapshot_id = f"recommendation-universe-snapshot-v1:{snapshot_digest}"

    return {
        "universe_policy_id": policy_id,
        "universe_policy_hash": policy_hash,
        "universe_policy_schema": UNIVERSE_POLICY_SCHEMA,
        "universe_policy_spec": policy_payload,
        "universe_snapshot_id": snapshot_id,
        "universe_snapshot_hash": snapshot_hash,
        "universe_snapshot_schema": UNIVERSE_SNAPSHOT_SCHEMA,
        "universe_snapshot_source_provider_id": str(source_provider_id).strip(),
        "universe_snapshot_spec": snapshot_payload,
        "universe_snapshot_selected_codes_hash": f"sha256:{selected_codes_digest}",
        # 舊 caller 的欄位別名保留原 namespace，但內容改為每日快照 digest；
        # 新的 evaluator 不再使用它作為跨日 cohort key。
        "universe_id": f"recommendation-universe-v1:{snapshot_digest}",
        "universe_hash": snapshot_hash,
        "universe_identity_schema": UNIVERSE_SNAPSHOT_SCHEMA,
    }


def build_strategy_config_identity(
    config: Mapping[str, Any],
    *,
    max_stocks: int,
    top_n: int,
) -> dict[str, Any]:
    """建立策略重要設定的可重現身份。

    決策日、資料 fingerprint、觀測時間等執行期欄位會排除；策略版本、篩選、
    排名與處理上限仍會進入 hash。這避免只靠顯示名稱把重要設定變更混入舊 cohort。
    """

    stable_config = _strip_runtime_fields(config)
    payload = {
        "schema": STRATEGY_CONFIG_SCHEMA,
        "max_stocks": int(max_stocks),
        "top_n": int(top_n),
        "config": stable_config,
    }
    digest = _sha256_digest(payload)
    return {
        "strategy_config_id": f"recommendation-strategy-config-v1:{digest}",
        "strategy_config_hash": f"sha256:{digest}",
        "strategy_config_schema": STRATEGY_CONFIG_SCHEMA,
        "strategy_config_spec": payload,
    }


def _normalized_codes(values: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    return tuple(sorted({str(value).strip() for value in values if str(value).strip()}))


def _sha256_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _canonicalize(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonicalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(child)
            for key, child in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalize(child) for child in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


_RUNTIME_IDENTITY_FIELDS = frozenset(
    {
        "as_of_date",
        "decision_date",
        "data_date",
        "created_at",
        "detected_at",
        "observed_at",
        "checked_at",
        "source_created_at",
        "market_data_fingerprint",
        "data_fingerprint",
        "fundamental_inputs",
        "warnings",
        "universe_id",
        "universe_hash",
        "universe_snapshot_id",
        "universe_snapshot_hash",
        "universe_snapshot_spec",
        "universe_policy_id",
        "universe_policy_hash",
        "universe_policy_spec",
        "strategy_config_id",
        "strategy_config_hash",
        "strategy_config_spec",
    }
)


def _strip_runtime_fields(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _strip_runtime_fields(child)
            for key, child in value.items()
            if str(key) not in _RUNTIME_IDENTITY_FIELDS
        }
    if isinstance(value, (list, tuple)):
        return [_strip_runtime_fields(child) for child in value]
    return _canonicalize(value)


__all__ = [
    "DEFAULT_RETURN_BASIS",
    "SCHEDULED_RECOMMENDATION_BENCHMARK_ID",
    "SCHEDULED_RECOMMENDATION_COST_MODEL_ID",
    "SCHEDULED_RECOMMENDATION_OUTCOME_WINDOWS",
    "SCHEDULED_RECOMMENDATION_PRIMARY_HORIZON_DAYS",
    "SCHEDULED_RECOMMENDATION_STRATEGY_VERSION_ID",
    "STRATEGY_CONFIG_SCHEMA",
    "UNIVERSE_POLICY_SCHEMA",
    "UNIVERSE_SELECTION_ALGORITHM",
    "UNIVERSE_SNAPSHOT_SCHEMA",
    "UNMODELED_COST_MODEL_IDS",
    "build_recommendation_universe_identity",
    "build_strategy_config_identity",
]
