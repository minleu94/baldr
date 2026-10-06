"""R020 portfolio result sidecar 的獨立版本化 codec。

此階段只編碼 legacy DTO 中不在 equity/trades Parquet 的欄位，並綁定
Registry run、portfolio parent 與兩個 Parquet 原始 bytes digest。它不發布
Registry artifact、不讀取 R012 child，也不改既有 DTO 的 to_dict/from_dict。
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
from dataclasses import dataclass, fields
from datetime import date
from decimal import Decimal
from typing import Any, ClassVar, cast

import numpy as np
import pandas as pd

from app_module.recommendation_portfolio_dtos import (
    PeriodHoldingDTO,
    RecommendationPortfolioBacktestResultDTO,
    RecommendationSnapshotDTO,
    StockContributionDTO,
)


RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_VERSION = "recommendation-portfolio-result.v1"
RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_REVISION = 1
_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ENVELOPE_KEYS = {
    "schema_version",
    "schema_revision",
    "registry_run_id",
    "portfolio_parent_id",
    "equity_parquet_sha256",
    "trades_parquet_sha256",
    "payload",
    "payload_hash",
}
_PAYLOAD_KEYS = {
    "summary",
    "snapshots",
    "period_holdings",
    "stock_contribution",
    "selection_diagnostics",
    "improvement_hints",
    "details",
}
_SNAPSHOT_KEYS = {
    "as_of_date",
    "profile_id",
    "strategy_config",
    "regime",
    "recommendations",
    "diagnostics",
    "replay_parent_id",
}


class PortfolioResultArtifactCodecError(ValueError):
    """Portfolio result sidecar 欄位、identity、schema 或 hash 無效。"""


def _fail(message: str) -> PortfolioResultArtifactCodecError:
    return PortfolioResultArtifactCodecError(message)


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise _fail("portfolio result sidecar 無法編成 canonical UTF-8 JSON") from exc


def _require_identity(value: object, field_name: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise _fail(f"{field_name} 必須是無空白邊界的非空字串")
    return cast(str, value)


def _require_sha256(value: object, field_name: str) -> str:
    if type(value) is not str or _SHA256_PATTERN.fullmatch(value) is None:
        raise _fail(f"{field_name} 必須是 sha256:<64 小寫 hex>")
    return cast(str, value)


def _require_object(
    value: object,
    *,
    keys: set[str],
    field_name: str,
) -> dict[str, object]:
    if type(value) is not dict:
        raise _fail(f"{field_name} 必須是 JSON object")
    mapping = cast(dict[str, object], value)
    if set(mapping) != keys:
        raise _fail(f"{field_name} 欄位不完整或含未知欄位")
    return mapping


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _fail(f"JSON object 含重複 key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise _fail(f"JSON 不允許非有限數值常數: {value}")


def _strict_json_load(raw_payload: bytes) -> object:
    if type(raw_payload) is not bytes:
        raise TypeError("raw_payload 必須是 bytes")
    try:
        return json.loads(
            raw_payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except PortfolioResultArtifactCodecError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise _fail("portfolio result sidecar 不是有效 UTF-8 JSON") from exc


def _numpy_dtype_is_lossless_supported(dtype: np.dtype[Any]) -> bool:
    if (
        dtype.hasobject
        or dtype.fields is not None
        or dtype.subdtype is not None
        or dtype.metadata is not None
    ):
        return False
    kind = dtype.kind
    itemsize = dtype.itemsize
    if kind in "iu":
        return itemsize in {1, 2, 4, 8}
    if kind == "f":
        return itemsize in {2, 4, 8}
    if kind == "c":
        return itemsize in {8, 16}
    if kind == "b":
        return itemsize == 1
    if kind in "mM":
        return itemsize == 8
    if kind == "S":
        return itemsize > 0
    if kind == "U":
        return itemsize > 0 and itemsize % 4 == 0
    return False


def _encode_value(value: object, *, field_name: str) -> dict[str, object]:
    """以 tagged tree 精確保留 DTO 值；不做型別轉換或數值運算。"""

    if value is None:
        return {"kind": "none"}
    if value is pd.NA:
        return {"kind": "pandas_na"}
    if value is pd.NaT:
        return {"kind": "pandas_nat"}
    if type(value) is bool:
        return {"kind": "bool", "value": value}
    if type(value) is int:
        return {"kind": "int", "value": str(value)}
    if type(value) is float:
        return {"kind": "float64", "bits": struct.pack(">d", value).hex()}
    if type(value) is Decimal:
        decimal_tuple = cast(Decimal, value).as_tuple()
        return {
            "kind": "decimal",
            "sign": decimal_tuple.sign,
            "digits": list(decimal_tuple.digits),
            "exponent": decimal_tuple.exponent,
        }
    if type(value) is str:
        return {"kind": "str", "value": value}
    if type(value) is bytes:
        return {"kind": "bytes", "hex": cast(bytes, value).hex()}
    if type(value) is date:
        return {"kind": "date", "value": cast(date, value).isoformat()}
    if isinstance(value, np.generic):
        scalar = cast(Any, value)
        dtype = scalar.dtype
        if not _numpy_dtype_is_lossless_supported(dtype):
            raise _fail(f"{field_name} 含不支援的 NumPy scalar dtype: {dtype!s}")
        return {
            "kind": "numpy_scalar",
            "dtype": dtype.str,
            "bytes": scalar.tobytes().hex(),
        }
    if type(value) is list:
        return {
            "kind": "list",
            "items": [
                _encode_value(item, field_name=f"{field_name}[{index}]")
                for index, item in enumerate(cast(list[object], value))
            ],
        }
    if type(value) is tuple:
        return {
            "kind": "tuple",
            "items": [
                _encode_value(item, field_name=f"{field_name}[{index}]")
                for index, item in enumerate(cast(tuple[object, ...], value))
            ],
        }
    if type(value) is dict:
        pairs: list[list[object]] = []
        for key, item in cast(dict[object, object], value).items():
            if type(key) is not str:
                raise _fail(f"{field_name} 含非字串 mapping key")
            pairs.append(
                [
                    key,
                    _encode_value(item, field_name=f"{field_name}.{key}"),
                ]
            )
        return {"kind": "mapping", "items": pairs}
    raise _fail(f"{field_name} 含不支援的值型別: {type(value).__name__}")


def _decode_value(value: object, *, field_name: str) -> object:
    if type(value) is not dict:
        raise _fail(f"{field_name} typed value 必須是 object")
    mapping = cast(dict[str, object], value)
    kind = mapping.get("kind")
    if type(kind) is not str:
        raise _fail(f"{field_name}.kind 必須是字串")

    if kind == "none":
        _require_object(value, keys={"kind"}, field_name=field_name)
        return None
    if kind == "pandas_na":
        _require_object(value, keys={"kind"}, field_name=field_name)
        return pd.NA
    if kind == "pandas_nat":
        _require_object(value, keys={"kind"}, field_name=field_name)
        return pd.NaT
    if kind == "bool":
        payload = _require_object(value, keys={"kind", "value"}, field_name=field_name)
        if type(payload["value"]) is not bool:
            raise _fail(f"{field_name}.value 必須是 bool")
        return payload["value"]
    if kind == "int":
        payload = _require_object(value, keys={"kind", "value"}, field_name=field_name)
        text = payload["value"]
        if type(text) is not str:
            raise _fail(f"{field_name}.value 必須是十進位整數字串")
        try:
            integer_value = int(text)
        except ValueError as exc:
            raise _fail(f"{field_name}.value 整數無效") from exc
        if str(integer_value) != text:
            raise _fail(f"{field_name}.value 整數格式非 canonical")
        return integer_value
    if kind == "float64":
        payload = _require_object(value, keys={"kind", "bits"}, field_name=field_name)
        bits = payload["bits"]
        if type(bits) is not str or re.fullmatch(r"[0-9a-f]{16}", bits) is None:
            raise _fail(f"{field_name}.bits 必須是 16 位小寫 hex")
        return struct.unpack(">d", bytes.fromhex(bits))[0]
    if kind == "decimal":
        payload = _require_object(
            value,
            keys={"kind", "sign", "digits", "exponent"},
            field_name=field_name,
        )
        sign = payload["sign"]
        digits = payload["digits"]
        exponent = payload["exponent"]
        if type(sign) is not int or sign not in {0, 1}:
            raise _fail(f"{field_name}.sign 必須是 0 或 1")
        if type(digits) is not list or any(
            type(digit) is not int or digit < 0 or digit > 9 for digit in digits
        ):
            raise _fail(f"{field_name}.digits 必須是 0 到 9 的整數陣列")
        if type(exponent) is int:
            decoded_exponent: int | str = exponent
        elif type(exponent) is str and exponent in {"F", "n", "N"}:
            decoded_exponent = exponent
        else:
            raise _fail(f"{field_name}.exponent 型別或內容無效")
        try:
            decimal_tuple = (sign, tuple(cast(list[int], digits)), decoded_exponent)
            return Decimal(cast(Any, decimal_tuple))
        except (TypeError, ValueError) as exc:
            raise _fail(f"{field_name} Decimal tuple 無效") from exc
    if kind == "str":
        payload = _require_object(value, keys={"kind", "value"}, field_name=field_name)
        if type(payload["value"]) is not str:
            raise _fail(f"{field_name}.value 必須是 str")
        return payload["value"]
    if kind == "bytes":
        payload = _require_object(value, keys={"kind", "hex"}, field_name=field_name)
        text = payload["hex"]
        if type(text) is not str or re.fullmatch(r"(?:[0-9a-f]{2})*", text) is None:
            raise _fail(f"{field_name}.hex 必須是偶數長度小寫 hex")
        return bytes.fromhex(text)
    if kind == "date":
        payload = _require_object(value, keys={"kind", "value"}, field_name=field_name)
        text = payload["value"]
        if type(text) is not str:
            raise _fail(f"{field_name}.value 必須是 ISO date 字串")
        try:
            decoded_date = date.fromisoformat(text)
        except ValueError as exc:
            raise _fail(f"{field_name}.value date 無效") from exc
        if decoded_date.isoformat() != text:
            raise _fail(f"{field_name}.value date 格式非 canonical")
        return decoded_date
    if kind == "numpy_scalar":
        payload = _require_object(
            value,
            keys={"kind", "dtype", "bytes"},
            field_name=field_name,
        )
        dtype_text = payload["dtype"]
        raw_hex = payload["bytes"]
        if type(dtype_text) is not str or type(raw_hex) is not str:
            raise _fail(f"{field_name} NumPy scalar 欄位型別錯誤")
        if re.fullmatch(r"(?:[0-9a-f]{2})*", raw_hex) is None:
            raise _fail(f"{field_name}.bytes 必須是偶數長度小寫 hex")
        try:
            dtype = np.dtype(dtype_text)
        except (TypeError, ValueError) as exc:
            raise _fail(f"{field_name}.dtype 無效") from exc
        if dtype_text != dtype.str:
            raise _fail(f"{field_name}.dtype 格式非 canonical")
        if not _numpy_dtype_is_lossless_supported(dtype):
            raise _fail(f"{field_name}.dtype 不支援: {dtype!s}")
        raw = bytes.fromhex(raw_hex)
        if len(raw) != dtype.itemsize:
            raise _fail(f"{field_name}.bytes 長度與 dtype 不符")
        try:
            return np.frombuffer(raw, dtype=dtype, count=1)[0]
        except (TypeError, ValueError) as exc:
            raise _fail(f"{field_name} NumPy scalar bytes 無效") from exc
    if kind in {"list", "tuple"}:
        payload = _require_object(value, keys={"kind", "items"}, field_name=field_name)
        items = payload["items"]
        if type(items) is not list:
            raise _fail(f"{field_name}.items 必須是 JSON array")
        decoded_items = [
            _decode_value(item, field_name=f"{field_name}[{index}]")
            for index, item in enumerate(items)
        ]
        return decoded_items if kind == "list" else tuple(decoded_items)
    if kind == "mapping":
        payload = _require_object(value, keys={"kind", "items"}, field_name=field_name)
        items = payload["items"]
        if type(items) is not list:
            raise _fail(f"{field_name}.items 必須是 JSON array")
        mapping_result: dict[str, object] = {}
        for index, pair in enumerate(items):
            if type(pair) is not list or len(pair) != 2:
                raise _fail(f"{field_name}.items[{index}] 必須是 key/value pair")
            key, item = pair
            if type(key) is not str:
                raise _fail(f"{field_name}.items[{index}] key 必須是 str")
            if key in mapping_result:
                raise _fail(f"{field_name} mapping 含重複 key: {key}")
            mapping_result[key] = _decode_value(item, field_name=f"{field_name}.{key}")
        return mapping_result
    raise _fail(f"{field_name}.kind 不支援: {kind!r}")


def _encode_string_list(value: object, *, field_name: str) -> list[dict[str, object]]:
    if type(value) is not list:
        raise _fail(f"{field_name} 必須是 list[str]")
    items = cast(list[object], value)
    if any(type(item) is not str for item in items):
        raise _fail(f"{field_name} 必須只包含 str")
    return [_encode_value(item, field_name=field_name) for item in items]


def _encode_dataclass_items(
    values: object,
    *,
    expected_type: type[Any],
    field_name: str,
) -> list[dict[str, object]]:
    if type(values) is not list:
        raise _fail(f"{field_name} 必須是 list")
    encoded: list[dict[str, object]] = []
    expected_fields = fields(expected_type)
    for index, item in enumerate(cast(list[object], values)):
        if type(item) is not expected_type:
            raise _fail(f"{field_name}[{index}] 型別錯誤")
        _validate_dataclass_values(
            {
                field.name: getattr(item, field.name)
                for field in expected_fields
            },
            expected_type=expected_type,
            field_name=f"{field_name}[{index}]",
        )
        encoded.append(
            {
                field.name: _encode_value(
                    getattr(item, field.name),
                    field_name=f"{field_name}[{index}].{field.name}",
                )
                for field in expected_fields
            }
        )
    return encoded


def _is_dto_integer(value: object) -> bool:
    return type(value) is int or (
        isinstance(value, np.integer) and not isinstance(value, np.bool_)
    )


def _is_dto_number(value: object) -> bool:
    if type(value) in {int, float, Decimal}:
        return True
    if isinstance(value, np.generic):
        return value.dtype.kind in "iuf"
    return False


def _validate_dataclass_values(
    values: dict[str, object],
    *,
    expected_type: type[Any],
    field_name: str,
) -> None:
    if expected_type is PeriodHoldingDTO:
        string_fields = {
            "rebalance_date",
            "stock_code",
            "stock_name",
            "entry_date",
            "planned_exit_date",
            "actual_exit_date",
            "exit_reason",
            "execution_contract",
            "position_status",
            "exit_signal_date",
        }
        integer_fields = {"rank", "holding_days"}
        optional_integer_fields = {"shares", "pnl_cents"}
        number_fields = {
            "total_score",
            "allocation_amount",
            "allocation_weight",
            "entry_price",
            "actual_exit_price",
            "return_pct",
        }
        optional_number_fields = {"actual_allocation_weight"}
        score_mapping_field = "factor_scores"
    elif expected_type is StockContributionDTO:
        string_fields = {"stock_code", "stock_name"}
        integer_fields = {"selected_count"}
        optional_integer_fields = set()
        number_fields = {
            "total_pnl",
            "avg_return_pct",
            "win_rate",
            "worst_return_pct",
        }
        optional_number_fields = set()
        score_mapping_field = None
    else:
        raise _fail(f"{field_name} dataclass schema 不支援")

    for name in string_fields:
        if type(values[name]) is not str:
            raise _fail(f"{field_name}.{name} 必須是 str")
    for name in integer_fields:
        if not _is_dto_integer(values[name]):
            raise _fail(f"{field_name}.{name} 必須是整數")
    for name in optional_integer_fields:
        value = values[name]
        if value is not None and not _is_dto_integer(value):
            raise _fail(f"{field_name}.{name} 必須是整數或 None")
    for name in number_fields:
        if not _is_dto_number(values[name]):
            raise _fail(f"{field_name}.{name} 必須是數值 scalar")
    for name in optional_number_fields:
        value = values[name]
        if value is not None and not _is_dto_number(value):
            raise _fail(f"{field_name}.{name} 必須是數值 scalar 或 None")
    if score_mapping_field is not None:
        score_values = values[score_mapping_field]
        if type(score_values) is not dict:
            raise _fail(f"{field_name}.{score_mapping_field} 必須是 dict[str, number]")
        for key, score in cast(dict[object, object], score_values).items():
            if type(key) is not str or not _is_dto_number(score):
                raise _fail(
                    f"{field_name}.{score_mapping_field} 必須是 dict[str, number]"
                )


def _encode_portfolio_payload(
    result: RecommendationPortfolioBacktestResultDTO,
    *,
    portfolio_parent_id: str,
) -> dict[str, object]:
    if type(result) is not RecommendationPortfolioBacktestResultDTO:
        raise _fail("result 必須是 RecommendationPortfolioBacktestResultDTO")
    if not isinstance(result.equity_curve, pd.DataFrame) or not isinstance(
        result.trades, pd.DataFrame
    ):
        raise _fail("equity_curve 與 trades 必須是 pandas DataFrame")
    try:
        current_parent = result.replay_parent_id
    except (TypeError, ValueError) as exc:
        raise _fail("DTO replay parent identity 不一致") from exc
    if current_parent != portfolio_parent_id:
        raise _fail("DTO replay parent 與 portfolio_parent_id 不一致")
    if type(result.snapshots) is not list:
        raise _fail("snapshots 必須是 list")

    snapshots: list[dict[str, object]] = []
    for index, snapshot in enumerate(result.snapshots):
        if type(snapshot) is not RecommendationSnapshotDTO:
            raise _fail(f"snapshots[{index}] 型別錯誤")
        if snapshot.replay_parent_id != portfolio_parent_id:
            raise _fail(f"snapshots[{index}] replay parent 與 portfolio 不一致")
        if type(snapshot.as_of_date) is not str:
            raise _fail(f"snapshots[{index}].as_of_date 必須是 str")
        if type(snapshot.profile_id) is not str or type(snapshot.regime) is not str:
            raise _fail(f"snapshots[{index}] profile_id/regime 必須是 str")
        if type(snapshot.strategy_config) is not dict:
            raise _fail(f"snapshots[{index}].strategy_config 必須是 dict")
        if type(snapshot.recommendations) is not list or any(
            type(row) is not dict for row in snapshot.recommendations
        ):
            raise _fail(f"snapshots[{index}].recommendations 必須是 list[dict]")
        snapshots.append(
            {
                "as_of_date": snapshot.as_of_date,
                "profile_id": snapshot.profile_id,
                "strategy_config": _encode_value(
                    snapshot.strategy_config,
                    field_name=f"snapshots[{index}].strategy_config",
                ),
                "regime": snapshot.regime,
                "recommendations": _encode_value(
                    snapshot.recommendations,
                    field_name=f"snapshots[{index}].recommendations",
                ),
                "diagnostics": _encode_string_list(
                    snapshot.diagnostics,
                    field_name=f"snapshots[{index}].diagnostics",
                ),
                "replay_parent_id": snapshot.replay_parent_id,
            }
        )

    if type(result.summary) is not dict or type(result.details) is not dict:
        raise _fail("summary 與 details 必須是 dict")
    return {
        "summary": _encode_value(result.summary, field_name="summary"),
        "snapshots": snapshots,
        "period_holdings": _encode_dataclass_items(
            result.period_holdings,
            expected_type=PeriodHoldingDTO,
            field_name="period_holdings",
        ),
        "stock_contribution": _encode_dataclass_items(
            result.stock_contribution,
            expected_type=StockContributionDTO,
            field_name="stock_contribution",
        ),
        "selection_diagnostics": _encode_string_list(
            result.selection_diagnostics,
            field_name="selection_diagnostics",
        ),
        "improvement_hints": _encode_string_list(
            result.improvement_hints,
            field_name="improvement_hints",
        ),
        "details": _encode_value(result.details, field_name="details"),
    }


def _decode_string_list(value: object, *, field_name: str) -> list[str]:
    if type(value) is not list:
        raise _fail(f"{field_name} 必須是 JSON array")
    decoded = [
        _decode_value(item, field_name=f"{field_name}[{index}]")
        for index, item in enumerate(cast(list[object], value))
    ]
    if any(type(item) is not str for item in decoded):
        raise _fail(f"{field_name} 必須只包含 str")
    return cast(list[str], decoded)


def _decode_dict(value: object, *, field_name: str) -> dict[str, object]:
    decoded = _decode_value(value, field_name=field_name)
    if type(decoded) is not dict:
        raise _fail(f"{field_name} 必須解碼為 dict")
    return cast(dict[str, object], decoded)


def _decode_dataclass_items(
    value: object,
    *,
    expected_type: type[Any],
    field_name: str,
) -> list[object]:
    if type(value) is not list:
        raise _fail(f"{field_name} 必須是 JSON array")
    expected_fields = fields(expected_type)
    expected_names = {item.name for item in expected_fields}
    decoded: list[object] = []
    for index, raw_item in enumerate(cast(list[object], value)):
        item_mapping = _require_object(
            raw_item,
            keys=expected_names,
            field_name=f"{field_name}[{index}]",
        )
        item_values = {
            item.name: _decode_value(
                item_mapping[item.name],
                field_name=f"{field_name}[{index}].{item.name}",
            )
            for item in expected_fields
        }
        _validate_dataclass_values(
            item_values,
            expected_type=expected_type,
            field_name=f"{field_name}[{index}]",
        )
        try:
            decoded.append(expected_type(**item_values))
        except (TypeError, ValueError) as exc:
            raise _fail(f"{field_name}[{index}] DTO 欄位無效") from exc
    return decoded


def _decode_payload(
    payload: object,
    *,
    portfolio_parent_id: str,
) -> dict[str, object]:
    mapping = _require_object(payload, keys=_PAYLOAD_KEYS, field_name="payload")
    summary = _decode_dict(mapping["summary"], field_name="summary")
    raw_snapshots = mapping["snapshots"]
    if type(raw_snapshots) is not list:
        raise _fail("snapshots 必須是 JSON array")
    snapshots: list[RecommendationSnapshotDTO] = []
    for index, raw_snapshot in enumerate(cast(list[object], raw_snapshots)):
        item = _require_object(
            raw_snapshot,
            keys=_SNAPSHOT_KEYS,
            field_name=f"snapshots[{index}]",
        )
        as_of_date = item["as_of_date"]
        profile_id = item["profile_id"]
        regime = item["regime"]
        replay_parent_id = item["replay_parent_id"]
        if any(
            type(value) is not str
            for value in (as_of_date, profile_id, regime, replay_parent_id)
        ):
            raise _fail(f"snapshots[{index}] string identity 欄位型別錯誤")
        if replay_parent_id != portfolio_parent_id:
            raise _fail(f"snapshots[{index}] parent identity 不符")
        strategy_config = _decode_dict(
            item["strategy_config"],
            field_name=f"snapshots[{index}].strategy_config",
        )
        recommendations_value = _decode_value(
            item["recommendations"],
            field_name=f"snapshots[{index}].recommendations",
        )
        if type(recommendations_value) is not list or any(
            type(row) is not dict for row in recommendations_value
        ):
            raise _fail(f"snapshots[{index}].recommendations 必須是 list[dict]")
        diagnostics = _decode_string_list(
            item["diagnostics"],
            field_name=f"snapshots[{index}].diagnostics",
        )
        try:
            snapshot = RecommendationSnapshotDTO(
                as_of_date=cast(str, as_of_date),
                profile_id=cast(str, profile_id),
                strategy_config=strategy_config,
                regime=cast(str, regime),
                recommendations=cast(list[dict[str, Any]], recommendations_value),
                diagnostics=diagnostics,
            )
            snapshot.attach_replay_parent_id(portfolio_parent_id)
        except (TypeError, ValueError) as exc:
            raise _fail(f"snapshots[{index}] DTO contract 無效") from exc
        snapshots.append(snapshot)

    holdings = _decode_dataclass_items(
        mapping["period_holdings"],
        expected_type=PeriodHoldingDTO,
        field_name="period_holdings",
    )
    contributions = _decode_dataclass_items(
        mapping["stock_contribution"],
        expected_type=StockContributionDTO,
        field_name="stock_contribution",
    )
    selection_diagnostics = _decode_string_list(
        mapping["selection_diagnostics"],
        field_name="selection_diagnostics",
    )
    improvement_hints = _decode_string_list(
        mapping["improvement_hints"],
        field_name="improvement_hints",
    )
    details = _decode_dict(mapping["details"], field_name="details")
    return {
        "summary": summary,
        "snapshots": snapshots,
        "period_holdings": cast(list[PeriodHoldingDTO], holdings),
        "stock_contribution": cast(list[StockContributionDTO], contributions),
        "selection_diagnostics": selection_diagnostics,
        "improvement_hints": improvement_hints,
        "details": details,
    }


def _parse_document(raw_payload: bytes) -> dict[str, object]:
    document = _require_object(
        _strict_json_load(raw_payload),
        keys=_ENVELOPE_KEYS,
        field_name="portfolio result envelope",
    )
    schema_version = document["schema_version"]
    schema_revision = document["schema_revision"]
    if type(schema_version) is not str or schema_version != RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_VERSION:
        raise _fail(f"不支援 schema_version: {schema_version!r}")
    if (
        type(schema_revision) is not int
        or schema_revision != RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_REVISION
    ):
        raise _fail(f"不支援 schema_revision: {schema_revision!r}")
    run_id = _require_identity(document["registry_run_id"], "registry_run_id")
    parent_id = _require_identity(document["portfolio_parent_id"], "portfolio_parent_id")
    if run_id == parent_id:
        raise _fail("registry_run_id 與 portfolio_parent_id 必須分離")
    equity_hash = _require_sha256(
        document["equity_parquet_sha256"], "equity_parquet_sha256"
    )
    trades_hash = _require_sha256(
        document["trades_parquet_sha256"], "trades_parquet_sha256"
    )
    payload_hash = _require_sha256(document["payload_hash"], "payload_hash")
    header = {key: document[key] for key in _ENVELOPE_KEYS if key != "payload_hash"}
    actual_payload_hash = "sha256:" + hashlib.sha256(
        _canonical_json_bytes(header)
    ).hexdigest()
    if actual_payload_hash != payload_hash:
        raise _fail("canonical payload_hash 不符")
    _decode_payload(document["payload"], portfolio_parent_id=parent_id)
    if _canonical_json_bytes(document) != raw_payload:
        raise _fail("sidecar bytes 不是 canonical UTF-8 JSON")
    return document


@dataclass(frozen=True, slots=True)
class RecommendationPortfolioResultArtifactV1:
    """已驗證的完整 sidecar envelope；原始 bytes 不可變。"""

    raw_payload: bytes
    registry_run_id: str
    portfolio_parent_id: str
    equity_parquet_sha256: str
    trades_parquet_sha256: str
    payload_hash: str
    raw_payload_sha256: str

    schema_version: ClassVar[str] = RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_VERSION
    schema_revision: ClassVar[int] = RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_REVISION

    @property
    def canonical_payload_hash(self) -> str:
        """明示 `payload_hash` 是 sidecar canonical content hash。"""

        return self.payload_hash

    def __post_init__(self) -> None:
        document = _parse_document(self.raw_payload)
        expected = {
            "registry_run_id": self.registry_run_id,
            "portfolio_parent_id": self.portfolio_parent_id,
            "equity_parquet_sha256": self.equity_parquet_sha256,
            "trades_parquet_sha256": self.trades_parquet_sha256,
            "payload_hash": self.payload_hash,
        }
        if any(document[key] != value for key, value in expected.items()):
            raise _fail("envelope fields 與 raw payload 不一致")
        actual_raw_hash = "sha256:" + hashlib.sha256(self.raw_payload).hexdigest()
        if self.raw_payload_sha256 != actual_raw_hash:
            raise _fail("raw_payload_sha256 不符")

    def materialize_result(
        self,
        *,
        equity_curve: pd.DataFrame,
        trades: pd.DataFrame,
        expected_registry_run_id: str,
        expected_portfolio_parent_id: str,
        equity_parquet_sha256: str,
        trades_parquet_sha256: str,
    ) -> RecommendationPortfolioBacktestResultDTO:
        """組回 DTO 非 Parquet 欄位；child execution 仍由 R012 lineage 驗證/附回。"""

        if not isinstance(equity_curve, pd.DataFrame) or not isinstance(trades, pd.DataFrame):
            raise _fail("讀回的 equity_curve 與 trades 必須是 pandas DataFrame")
        if _require_identity(expected_registry_run_id, "expected_registry_run_id") != self.registry_run_id:
            raise _fail("Registry run identity mismatch")
        if _require_identity(expected_portfolio_parent_id, "expected_portfolio_parent_id") != self.portfolio_parent_id:
            raise _fail("portfolio parent identity mismatch")
        if _require_sha256(equity_parquet_sha256, "equity_parquet_sha256") != self.equity_parquet_sha256:
            raise _fail("equity Parquet raw SHA-256 binding mismatch")
        if _require_sha256(trades_parquet_sha256, "trades_parquet_sha256") != self.trades_parquet_sha256:
            raise _fail("trades Parquet raw SHA-256 binding mismatch")
        document = _parse_document(self.raw_payload)
        decoded = _decode_payload(
            document["payload"],
            portfolio_parent_id=self.portfolio_parent_id,
        )
        result = RecommendationPortfolioBacktestResultDTO(
            summary=cast(dict[str, Any], decoded["summary"]),
            equity_curve=equity_curve,
            trades=trades,
            snapshots=cast(list[RecommendationSnapshotDTO], decoded["snapshots"]),
            period_holdings=cast(list[PeriodHoldingDTO], decoded["period_holdings"]),
            stock_contribution=cast(
                list[StockContributionDTO], decoded["stock_contribution"]
            ),
            selection_diagnostics=cast(
                list[str], decoded["selection_diagnostics"]
            ),
            improvement_hints=cast(list[str], decoded["improvement_hints"]),
            details=cast(dict[str, Any], decoded["details"]),
        )
        try:
            result.attach_replay_parent_id(self.portfolio_parent_id)
        except (TypeError, ValueError) as exc:
            raise _fail("portfolio parent 無法附加至讀回 DTO") from exc
        return result


def encode_portfolio_result_artifact(
    result: RecommendationPortfolioBacktestResultDTO,
    *,
    registry_run_id: str,
    portfolio_parent_id: str,
    equity_parquet_sha256: str,
    trades_parquet_sha256: str,
) -> RecommendationPortfolioResultArtifactV1:
    """編碼 sidecar；Parquet digest 必須由外層 raw artifact bytes 計算。"""

    run_id = _require_identity(registry_run_id, "registry_run_id")
    parent_id = _require_identity(portfolio_parent_id, "portfolio_parent_id")
    if run_id == parent_id:
        raise _fail("registry_run_id 與 portfolio_parent_id 必須分離")
    equity_hash = _require_sha256(equity_parquet_sha256, "equity_parquet_sha256")
    trades_hash = _require_sha256(trades_parquet_sha256, "trades_parquet_sha256")
    payload = _encode_portfolio_payload(result, portfolio_parent_id=parent_id)
    header: dict[str, object] = {
        "schema_version": RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_VERSION,
        "schema_revision": RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_REVISION,
        "registry_run_id": run_id,
        "portfolio_parent_id": parent_id,
        "equity_parquet_sha256": equity_hash,
        "trades_parquet_sha256": trades_hash,
        "payload": payload,
    }
    payload_hash = "sha256:" + hashlib.sha256(
        _canonical_json_bytes(header)
    ).hexdigest()
    document = dict(header)
    document["payload_hash"] = payload_hash
    raw_payload = _canonical_json_bytes(document)
    raw_payload_sha256 = "sha256:" + hashlib.sha256(raw_payload).hexdigest()
    return RecommendationPortfolioResultArtifactV1(
        raw_payload=raw_payload,
        registry_run_id=run_id,
        portfolio_parent_id=parent_id,
        equity_parquet_sha256=equity_hash,
        trades_parquet_sha256=trades_hash,
        payload_hash=payload_hash,
        raw_payload_sha256=raw_payload_sha256,
    )


def decode_portfolio_result_artifact(
    raw_payload: bytes,
) -> RecommendationPortfolioResultArtifactV1:
    """嚴格解碼 sidecar；只接受已知 schema 與 canonical bytes/hash。"""

    document = _parse_document(raw_payload)
    return RecommendationPortfolioResultArtifactV1(
        raw_payload=raw_payload,
        registry_run_id=cast(str, document["registry_run_id"]),
        portfolio_parent_id=cast(str, document["portfolio_parent_id"]),
        equity_parquet_sha256=cast(str, document["equity_parquet_sha256"]),
        trades_parquet_sha256=cast(str, document["trades_parquet_sha256"]),
        payload_hash=cast(str, document["payload_hash"]),
        raw_payload_sha256="sha256:" + hashlib.sha256(raw_payload).hexdigest(),
    )


__all__ = (
    "RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_REVISION",
    "RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_VERSION",
    "PortfolioResultArtifactCodecError",
    "RecommendationPortfolioResultArtifactV1",
    "decode_portfolio_result_artifact",
    "encode_portfolio_result_artifact",
)
