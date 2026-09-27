"""純值型別與序列化契約，供 Restated ML 與 app 邊界共同使用。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from typing import Mapping, Sequence


RESTATED_RESEARCH_PROFILE = "sealed_restated_linear_shadow_v1"


def _hash(payload: object) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def hash_canonical_research_row_payloads(
    payloads: Sequence[Mapping[str, object]],
) -> str:
    """雜湊呼叫端已依 symbol 排序的完整研究列 payload。"""
    return _hash(list(payloads))


OFFICIAL_MARKET_CONTRACT_HASH = _hash({"market_source_contract": "twse-fmtqik-shares-mi5mins-ohlc.v1"})


def require_compatible_market_sources(
    training_sources: Sequence[tuple[str, str]], current_sources: Sequence[tuple[str, str]],
) -> None:
    """官方市場模型不能消費舊混合單位市場輸入；來源批次仍可更新。"""
    if "official.twse_market" not in dict(training_sources):
        return
    current = dict(current_sources)
    if (
        "official.twse_market" not in current
        or current.get("contract.official_twse_market") != OFFICIAL_MARKET_CONTRACT_HASH
    ):
        raise ValueError("official-market model requires verified official-market current inputs")


def _require_hash(value: str) -> None:
    if (
        not isinstance(value, str) or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError("research input requires lowercase sha256 hashes")


@dataclass(frozen=True)
class RestatedResearchInputBinding:
    """明確分離此次推論來源與模型訓練來源，不改寫原 artifact metadata。"""

    dataset_id: str
    dataset_identity_hash: str
    dataset_manifest_file_hash: str
    feature_registry_hash: str
    source_manifest_hashes: tuple[tuple[str, str], ...]
    ordered_features: tuple[tuple[str, int], ...]
    prepared_rows_hash: str
    captured_at: str

    def __post_init__(self) -> None:
        if not isinstance(self.dataset_id, str) or not self.dataset_id.strip():
            raise ValueError("research dataset id is required")
        for value in (
            self.dataset_identity_hash, self.dataset_manifest_file_hash,
            self.feature_registry_hash, self.prepared_rows_hash,
        ):
            _require_hash(value)
        if not isinstance(self.source_manifest_hashes, tuple) or not self.source_manifest_hashes:
            raise ValueError("research sources must be a nonempty immutable tuple")
        source_ids: set[str] = set()
        for pair in self.source_manifest_hashes:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError("research source pairs must be immutable")
            name, value = pair
            if not isinstance(name, str) or not name.strip() or name in source_ids:
                raise ValueError("research source names must be nonempty and unique")
            source_ids.add(name)
            _require_hash(value)
        if not isinstance(self.ordered_features, tuple) or not self.ordered_features:
            raise ValueError("research feature contract is required")
        feature_ids: set[str] = set()
        for feature_pair in self.ordered_features:
            if not isinstance(feature_pair, tuple) or len(feature_pair) != 2:
                raise ValueError("research feature pairs must be immutable")
            feature_id, scale = feature_pair
            if not isinstance(feature_id, str) or not feature_id.strip() or feature_id in feature_ids:
                raise ValueError("research feature ids must be nonempty and unique")
            if isinstance(scale, bool) or not isinstance(scale, int) or scale <= 0:
                raise ValueError("research feature scales must be positive integers")
            feature_ids.add(feature_id)
        clock = datetime.fromisoformat(self.captured_at)
        if clock.tzinfo is None or clock.utcoffset() is None:
            raise ValueError("research capture must include timezone")

    def require_compatible_training_sources(
        self,
        training_sources: Sequence[tuple[str, str]],
    ) -> None:
        """驗證封存訓練來源可搭配這份當前研究輸入。"""

        require_compatible_market_sources(
            training_sources,
            self.source_manifest_hashes,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            **asdict(self),
            "schema_version": "restated-research-input-binding.v1",
            "historical_pit": False,
            "formal_oos_allowed": False,
            "production_action_allowed": False,
            "production_blend_alpha_bp": 0,
            "broker_order_allowed": False,
        }

    @property
    def binding_hash(self) -> str:
        return _hash(self.to_dict())


_LEGACY_MODULE = "ml_module.restated_research_input_contract"

# Keep legacy import, pickle, and introspection identities while this pure leaf
# owns the definitions.
RestatedResearchInputBinding.__module__ = _LEGACY_MODULE
for _method_name in (
    "__init__",
    "__repr__",
    "__eq__",
    "__hash__",
    "__setattr__",
    "__delattr__",
    "__post_init__",
    "require_compatible_training_sources",
    "to_dict",
):
    _method = getattr(RestatedResearchInputBinding, _method_name)
    _method.__module__ = _LEGACY_MODULE
    _method.__qualname__ = f"RestatedResearchInputBinding.{_method_name}"
    _wrapped = getattr(_method, "__wrapped__", None)
    if _wrapped is not None:
        _wrapped.__module__ = _LEGACY_MODULE
_binding_hash_property = RestatedResearchInputBinding.__dict__["binding_hash"]
_binding_hash_getter = _binding_hash_property.fget
if _binding_hash_getter is not None:
    _binding_hash_getter.__module__ = _LEGACY_MODULE
    _binding_hash_getter.__qualname__ = "RestatedResearchInputBinding.binding_hash"

_hash.__module__ = _LEGACY_MODULE
require_compatible_market_sources.__module__ = _LEGACY_MODULE
_require_hash.__module__ = _LEGACY_MODULE
