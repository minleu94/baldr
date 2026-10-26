"""策略版本綁定且不可變更的 Advice 契約。"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, ClassVar, Mapping, cast


_HASH_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _require_text(name: str, value: object) -> None:
    if (
        type(value) is not str
        or not value
        or value.strip() != value
        or "\x00" in value
    ):
        raise ValueError(f"{name} 必須是無空白邊界的非空字串")


@dataclass(frozen=True, slots=True)
class StrategyAdviceContract:
    """保存策略作者明確聲明的論點、失效條件與檢視節奏。"""

    thesis: str
    invalidation_conditions: tuple[str, ...]
    holding_horizon: str
    review_cadence: str
    contract_sha256: str = ""

    SCHEMA_VERSION: ClassVar[str] = "strategy-advice-contract.v1"

    def __post_init__(self) -> None:
        _require_text("thesis", self.thesis)
        _require_text("holding_horizon", self.holding_horizon)
        _require_text("review_cadence", self.review_cadence)
        if type(self.invalidation_conditions) is not tuple:
            raise TypeError("invalidation_conditions 必須是 tuple[str, ...]")
        if not self.invalidation_conditions:
            raise ValueError("invalidation_conditions 不可為空")
        for index, condition in enumerate(self.invalidation_conditions):
            _require_text(f"invalidation_conditions[{index}]", condition)
        if len(set(self.invalidation_conditions)) != len(self.invalidation_conditions):
            raise ValueError("invalidation_conditions 不可重複")

        if type(self.contract_sha256) is not str:
            raise TypeError("contract_sha256 必須是字串")
        expected_hash = self.canonical_sha256
        if self.contract_sha256:
            if (
                type(self.contract_sha256) is not str
                or _HASH_PATTERN.fullmatch(self.contract_sha256) is None
                or self.contract_sha256 != expected_hash
            ):
                raise ValueError("contract_sha256 不符合 canonical contract bytes")
        else:
            object.__setattr__(self, "contract_sha256", expected_hash)

    @property
    def canonical_sha256(self) -> str:
        digest = hashlib.sha256(_canonical_json(self.hash_payload()).encode("utf-8"))
        return f"sha256:{digest.hexdigest()}"

    def hash_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "thesis": self.thesis,
            "invalidation_conditions": list(self.invalidation_conditions),
            "holding_horizon": self.holding_horizon,
            "review_cadence": self.review_cadence,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self.hash_payload()
        payload["contract_sha256"] = self.contract_sha256
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> StrategyAdviceContract:
        if not isinstance(payload, Mapping):
            raise TypeError("advice_contract 必須是 JSON object")
        expected_fields = {
            "schema_version",
            "thesis",
            "invalidation_conditions",
            "holding_horizon",
            "review_cadence",
            "contract_sha256",
        }
        if set(payload) != expected_fields:
            raise ValueError("advice_contract 欄位必須完全符合 strategy-advice-contract.v1")
        if payload.get("schema_version") != cls.SCHEMA_VERSION:
            raise ValueError("advice_contract schema_version 不支援")
        conditions = payload.get("invalidation_conditions")
        if type(conditions) is not list or any(type(item) is not str for item in conditions):
            raise TypeError("invalidation_conditions 必須是 JSON 字串陣列")
        contract_hash = payload.get("contract_sha256")
        if (
            type(contract_hash) is not str
            or _HASH_PATTERN.fullmatch(contract_hash) is None
        ):
            raise ValueError("contract_sha256 必須是小寫 sha256 digest")
        return cls(
            thesis=cast(str, payload.get("thesis")),
            invalidation_conditions=tuple(conditions),
            holding_horizon=cast(str, payload.get("holding_horizon")),
            review_cadence=cast(str, payload.get("review_cadence")),
            contract_sha256=contract_hash,
        )


__all__ = ("StrategyAdviceContract",)
