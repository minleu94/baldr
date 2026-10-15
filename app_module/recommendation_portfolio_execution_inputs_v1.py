"""原producer執行輸入捕獲；內容身份不授來源、成本或績效資格。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Literal, Mapping, cast

from financial_module.units import to_decimal


EXECUTION_INPUTS_SCHEMA_V1 = "recommendation-portfolio-execution-inputs.v1"
_MAX_BYTES = 32 * 1024
_FIELDS = frozenset({
    "schema_version", "execution_contract", "cost_route", "submitted_bps", "effective_bps",
    "submitted_lot_size", "effective_lot_size", "cost_policy_metadata",
})


class RecommendationPortfolioExecutionInputsV1Error(ValueError):
    """輸入捕獲格式或原producer正規化結果不符。"""


def _fail(reason: str) -> RecommendationPortfolioExecutionInputsV1Error:
    return RecommendationPortfolioExecutionInputsV1Error(reason)


def _canonical(value: object) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise _fail("execution_inputs_json_invalid") from exc
    if len(text.encode("utf-8")) > _MAX_BYTES:
        raise _fail("execution_inputs_byte_limit")
    return text


def _pairs(values: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in values:
        if key in result:
            raise _fail("execution_inputs_duplicate_field")
        result[key] = value
    return result


def _reject_number(_value: str) -> None:
    raise _fail("execution_inputs_float_or_constant_refused")


def _decode(text: str) -> object:
    if type(text) is not str or not text or len(text.encode("utf-8")) > _MAX_BYTES:
        raise _fail("execution_inputs_byte_limit")
    try:
        return json.loads(text, object_pairs_hook=_pairs,
                          parse_float=_reject_number, parse_constant=_reject_number)
    except (TypeError, ValueError, RecursionError) as exc:
        raise _fail("execution_inputs_json_invalid") from exc


def _decimal_text(value: object) -> str:
    if type(value) is not str or not 1 <= len(value) <= 128:
        raise _fail("execution_inputs_decimal_text_required")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise _fail("execution_inputs_decimal_invalid") from exc
    if (not parsed.is_finite() or parsed < 0 or len(parsed.as_tuple().digits) > 80
            or format(parsed, "f") != value):
        raise _fail("execution_inputs_decimal_invalid")
    return value


def _submitted(value: object) -> str | None:
    # 沿既有to_decimal邊界轉換；不聲稱能復原caller先前已損失的精度。
    if value is None:
        return None
    try:
        return _decimal_text(format(to_decimal(value), "f"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise _fail("execution_inputs_submitted_bps_invalid") from exc


@dataclass(frozen=True, slots=True)
class RecommendationPortfolioExecutionInputsV1:
    """固定原輸入與實際route的不可變副本；非成本model／撮合程式的內容hash。"""

    execution_contract: str
    cost_route: Literal["configured_bps", "banktaiwan_policy"]
    submitted_bps: tuple[str | None, str | None, str | None]
    effective_bps: tuple[str, str, str] | None
    submitted_lot_size: int | None
    effective_lot_size: int
    cost_policy_metadata_json: str | None

    def __post_init__(self) -> None:
        if (type(self.execution_contract) is not str or not self.execution_contract
                or len(self.execution_contract) > 256 or self.execution_contract != self.execution_contract.strip()
                or any(ord(char) < 32 for char in self.execution_contract)):
            raise _fail("execution_inputs_contract_invalid")
        if self.cost_route not in ("configured_bps", "banktaiwan_policy"):
            raise _fail("execution_inputs_route_invalid")
        if type(self.submitted_bps) is not tuple or len(self.submitted_bps) != 3:
            raise _fail("execution_inputs_submitted_bps_invalid")
        for value in self.submitted_bps:
            if value is not None:
                _decimal_text(value)
        if (type(self.effective_lot_size) is not int or self.effective_lot_size <= 0
                or (self.submitted_lot_size is not None
                    and (type(self.submitted_lot_size) is not int or self.submitted_lot_size <= 0))):
            raise _fail("execution_inputs_lot_invalid")
        if self.cost_route == "configured_bps":
            if (self.cost_policy_metadata_json is not None or type(self.effective_bps) is not tuple
                    or len(self.effective_bps) != 3):
                raise _fail("execution_inputs_configured_route_invalid")
            for submitted, effective in zip(self.submitted_bps, self.effective_bps):
                _decimal_text(effective)
                if Decimal(effective) != Decimal(submitted if submitted is not None else "0"):
                    raise _fail("execution_inputs_effective_bps_mismatch")
            if self.effective_lot_size != (self.submitted_lot_size or 1):
                raise _fail("execution_inputs_effective_lot_mismatch")
        else:
            if self.effective_bps is not None or self.cost_policy_metadata_json is None:
                raise _fail("execution_inputs_policy_route_invalid")
            metadata = _decode(self.cost_policy_metadata_json)
            if type(metadata) is not dict or _canonical(metadata) != self.cost_policy_metadata_json:
                raise _fail("execution_inputs_policy_metadata_invalid")
            for name in ("policy_id", "policy_version", "lot_type", "instrument_type"):
                if type(metadata.get(name)) is not str or not metadata[name]:
                    raise _fail("execution_inputs_policy_identity_missing")
            if metadata["lot_type"] == "full_lot":
                lot = metadata.get("full_lot_size_shares")
                if type(lot) is not int or lot <= 0:
                    raise _fail("execution_inputs_policy_lot_invalid")
            elif metadata["lot_type"] == "odd_lot":
                lot = 1
            else:
                raise _fail("execution_inputs_policy_lot_invalid")
            if (self.effective_lot_size != lot or
                    (self.submitted_lot_size is not None and self.submitted_lot_size != lot)):
                raise _fail("execution_inputs_policy_effective_lot_mismatch")
        _canonical(self.to_dict())

    @classmethod
    def capture(
        cls, *, execution_contract: str, fee_bps: object, slippage_bps: object,
        tax_bps: object, submitted_lot_size: int | None, effective_lot_size: int,
        cost_policy_metadata: Mapping[str, object] | None,
    ) -> RecommendationPortfolioExecutionInputsV1:
        submitted = (_submitted(fee_bps), _submitted(slippage_bps), _submitted(tax_bps))
        if cost_policy_metadata is None:
            return cls(execution_contract, "configured_bps", submitted,
                       (submitted[0] if submitted[0] is not None else "0",
                        submitted[1] if submitted[1] is not None else "0",
                        submitted[2] if submitted[2] is not None else "0"),
                       submitted_lot_size, effective_lot_size, None)
        metadata_json = _canonical(dict(cost_policy_metadata))
        return cls(execution_contract, "banktaiwan_policy", submitted, None,
                   submitted_lot_size, effective_lot_size, metadata_json)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": EXECUTION_INPUTS_SCHEMA_V1,
            "execution_contract": self.execution_contract, "cost_route": self.cost_route,
            "submitted_bps": list(self.submitted_bps),
            "effective_bps": list(self.effective_bps) if self.effective_bps is not None else None,
            "submitted_lot_size": self.submitted_lot_size, "effective_lot_size": self.effective_lot_size,
            "cost_policy_metadata": _decode(self.cost_policy_metadata_json)
            if self.cost_policy_metadata_json is not None else None,
        }

    def to_json(self) -> str:
        return _canonical(self.to_dict())

    @property
    def input_identity_sha256(self) -> str:
        return "sha256:" + hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    @classmethod
    def from_json(cls, text: str) -> RecommendationPortfolioExecutionInputsV1:
        value = _decode(text)
        if type(value) is not dict or set(value) != _FIELDS or value["schema_version"] != EXECUTION_INPUTS_SCHEMA_V1:
            raise _fail("execution_inputs_fields_or_schema_invalid")
        submitted, effective = value["submitted_bps"], value["effective_bps"]
        if type(submitted) is not list or len(submitted) != 3:
            raise _fail("execution_inputs_submitted_bps_invalid")
        if effective is not None and (type(effective) is not list or len(effective) != 3):
            raise _fail("execution_inputs_effective_bps_invalid")
        result = cls(
            execution_contract=value["execution_contract"], cost_route=value["cost_route"],
            submitted_bps=cast(tuple[str | None, str | None, str | None], tuple(submitted)),
            effective_bps=cast(tuple[str, str, str] | None, tuple(effective) if effective is not None else None),
            submitted_lot_size=value["submitted_lot_size"], effective_lot_size=value["effective_lot_size"],
            cost_policy_metadata_json=_canonical(value["cost_policy_metadata"])
            if value["cost_policy_metadata"] is not None else None,
        )
        if result.to_json() != text:
            raise _fail("execution_inputs_noncanonical_json")
        return result
