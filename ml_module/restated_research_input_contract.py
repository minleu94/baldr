"""修訂資料研究推論的不可變輸入身分；不取得資料、不授予正式權限。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from typing import Sequence

from ml_module.allocation_contracts import PortfolioMLDatasetRow


RESTATED_RESEARCH_PROFILE = "sealed_restated_linear_shadow_v1"


def _hash(payload: object) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


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


def research_rows_hash(rows: Sequence[PortfolioMLDatasetRow]) -> str:
    """綁定實際消費的完整列，包含值、缺值、時鐘與投組狀態。"""
    return _hash([asdict(row) for row in sorted(rows, key=lambda item: item.symbol)])


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
