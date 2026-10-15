"""原完整Portfolio文件加執行輸入封套；不提升來源或績效資格。"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import hashlib
from typing import ClassVar

import pandas as pd

from app_module.recommendation_portfolio_dtos import RecommendationPortfolioBacktestResultDTO
from app_module.recommendation_portfolio_execution_inputs_v1 import RecommendationPortfolioExecutionInputsV1
from app_module.recommendation_portfolio_result_artifact import (
    PortfolioResultArtifactCodecError, RecommendationPortfolioResultArtifactV1,
    decode_portfolio_result_artifact, encode_portfolio_result_artifact,
)
from app_module.recommendation_portfolio_result_artifact_v2 import (
    RecommendationPortfolioResultArtifactV2, decode_portfolio_result_artifact_v2,
    encode_portfolio_result_artifact_v2, _canonical_json_bytes, _strict_json_load,
    _require_object, _require_identity, _require_sha256, _optional_metadata_identity,
)

RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_VERSION_V3 = "recommendation-portfolio-result.v3"
RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_REVISION_V3 = 3
_MAX_BYTES = 16 * 1024**2
_ENVELOPE_KEYS = {
    "schema_version", "schema_revision", "registry_run_id", "portfolio_parent_id",
    "equity_parquet_sha256", "trades_parquet_sha256", "payload", "payload_hash",
}
_PAYLOAD_KEYS = {
    "base_schema_version", "base_schema_revision", "base_document", "execution_inputs",
    "execution_inputs_identity_sha256", "metadata_strategy_id", "metadata_strategy_version",
}
BasePortfolioArtifact = RecommendationPortfolioResultArtifactV1 | RecommendationPortfolioResultArtifactV2


class PortfolioResultArtifactV3CodecError(PortfolioResultArtifactCodecError):
    """V3輸入、原文件或外層身份不一致。"""


def _fail(reason: str) -> PortfolioResultArtifactV3CodecError:
    return PortfolioResultArtifactV3CodecError(reason)


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _same_bps(actual: object, expected: str) -> bool:
    if type(actual) is not str or not 1 <= len(actual) <= 128:
        return False
    try:
        parsed = Decimal(actual)
        return parsed.is_finite() and parsed == Decimal(expected)
    except InvalidOperation:
        return False


def _crossbind(base: BasePortfolioArtifact, inputs: RecommendationPortfolioExecutionInputsV1) -> None:
    # 只重用原公開codec還原原保存欄位；不把展示金額拿來重造捕獲。
    result = base.materialize_result(
        equity_curve=pd.DataFrame(), trades=pd.DataFrame(),
        expected_registry_run_id=base.registry_run_id,
        expected_portfolio_parent_id=base.portfolio_parent_id,
        equity_parquet_sha256=base.equity_parquet_sha256,
        trades_parquet_sha256=base.trades_parquet_sha256,
    )
    credibility = result.details.get("portfolio_credibility")
    if (type(credibility) is not dict
            or result.summary.get("execution_contract") != inputs.execution_contract
            or result.details.get("execution_contract") != inputs.execution_contract
            or credibility.get("execution_contract") != inputs.execution_contract):
        raise _fail("execution_inputs_contract_crossbind_mismatch")
    sizing = credibility.get("share_sizing")
    if (type(sizing) is not dict or type(sizing.get("lot_size")) is not int
            or sizing["lot_size"] != inputs.effective_lot_size):
        raise _fail("execution_inputs_lot_crossbind_mismatch")
    costs = credibility.get("execution_costs")
    if inputs.cost_route == "configured_bps":
        if type(costs) is not dict or inputs.effective_bps is None:
            raise _fail("execution_inputs_cost_crossbind_mismatch")
        for name, expected in zip(("fee_bps", "slippage_bps", "tax_bps"), inputs.effective_bps):
            if not _same_bps(costs.get(name), expected):
                raise _fail("execution_inputs_cost_crossbind_mismatch")
        warnings = credibility.get("warnings")
        if (type(warnings) is not list or
                ("unspecified_cost_assumptions" in warnings) != any(value is None for value in inputs.submitted_bps)):
            raise _fail("execution_inputs_unspecified_cost_crossbind_mismatch")
    else:
        metadata = inputs.to_dict()["cost_policy_metadata"]
        if (type(metadata) is not dict or costs != metadata
                or result.details.get("execution_cost_policy") != metadata):
            raise _fail("execution_inputs_policy_crossbind_mismatch")
    if type(base) is RecommendationPortfolioResultArtifactV2:
        capture = base.period_precision_capture
        if f"{capture.execution_contract_id}.{capture.execution_contract_version}" != inputs.execution_contract:
            raise _fail("execution_inputs_capture_contract_mismatch")
        if inputs.cost_route == "banktaiwan_policy":
            metadata = inputs.to_dict()["cost_policy_metadata"]
            if (type(metadata) is not dict or capture.cost_model_status != "identified"
                    or (capture.cost_model_id, capture.cost_model_version)
                    != (metadata.get("policy_id"), metadata.get("policy_version"))):
                raise _fail("execution_inputs_capture_policy_mismatch")
        elif capture.cost_model_status != "unknown":
            raise _fail("execution_inputs_capture_route_mismatch")


@dataclass(frozen=True, slots=True)
class RecommendationPortfolioResultArtifactV3:
    """單次解碼衍生不可變欄位；原V1/V2仍由其原codec負責。"""

    raw_payload: bytes
    registry_run_id: str = field(init=False)
    portfolio_parent_id: str = field(init=False)
    equity_parquet_sha256: str = field(init=False)
    trades_parquet_sha256: str = field(init=False)
    payload_hash: str = field(init=False)
    raw_payload_sha256: str = field(init=False)
    base_artifact: BasePortfolioArtifact = field(init=False, repr=False, compare=False)
    execution_inputs: RecommendationPortfolioExecutionInputsV1 = field(init=False, compare=False)
    metadata_strategy_id: str | None = field(init=False)
    metadata_strategy_version: str | None = field(init=False)
    schema_version: ClassVar[str] = RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_VERSION_V3
    schema_revision: ClassVar[int] = RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_REVISION_V3

    def __post_init__(self) -> None:
        raw = self.raw_payload
        if type(raw) is not bytes or not 0 < len(raw) <= _MAX_BYTES:
            raise _fail("V3 JSON超過16MiB或型別錯誤")
        document = _require_object(_strict_json_load(raw), keys=_ENVELOPE_KEYS, field_name="v3")
        if (document["schema_version"] != self.schema_version
                or type(document["schema_revision"]) is not int or document["schema_revision"] != self.schema_revision):
            raise _fail("V3 schema/revision不支援")
        run = _require_identity(document["registry_run_id"], "registry_run_id")
        parent = _require_identity(document["portfolio_parent_id"], "portfolio_parent_id")
        if run == parent:
            raise _fail("V3 run與parent必須分離")
        equity = _require_sha256(document["equity_parquet_sha256"], "equity_parquet_sha256")
        trades = _require_sha256(document["trades_parquet_sha256"], "trades_parquet_sha256")
        payload_hash = _require_sha256(document["payload_hash"], "payload_hash")
        if _sha(_canonical_json_bytes({key: value for key, value in document.items() if key != "payload_hash"})) != payload_hash:
            raise _fail("V3 canonical payload_hash不符")
        if _canonical_json_bytes(document) != raw:
            raise _fail("V3 bytes非canonical UTF-8 JSON")
        payload = _require_object(document["payload"], keys=_PAYLOAD_KEYS, field_name="v3.payload")
        revision = payload["base_schema_revision"]
        if type(revision) is not int:
            raise _fail("V3 base schema/revision不支援")
        identity = (payload["base_schema_version"], revision)
        base_raw = _canonical_json_bytes(payload["base_document"])
        if identity == ("recommendation-portfolio-result.v1", 1):
            base: BasePortfolioArtifact = decode_portfolio_result_artifact(base_raw)
        elif identity == ("recommendation-portfolio-result.v2", 2):
            base = decode_portfolio_result_artifact_v2(base_raw)
        else:
            raise _fail("V3 base schema/revision不支援")
        if (base.registry_run_id, base.portfolio_parent_id, base.equity_parquet_sha256,
                base.trades_parquet_sha256) != (run, parent, equity, trades):
            raise _fail("V3 outer/base identity或Parquet不一致")
        strategy = _optional_metadata_identity(payload["metadata_strategy_id"], "metadata_strategy_id")
        version = _optional_metadata_identity(payload["metadata_strategy_version"], "metadata_strategy_version")
        if type(base) is RecommendationPortfolioResultArtifactV2 and (
                base.metadata_strategy_id, base.metadata_strategy_version) != (strategy, version):
            raise _fail("V3 outer/base strategy不一致")
        inputs = RecommendationPortfolioExecutionInputsV1.from_json(
            _canonical_json_bytes(payload["execution_inputs"]).decode("utf-8"))
        if inputs.input_identity_sha256 != payload["execution_inputs_identity_sha256"]:
            raise _fail("V3 execution inputs identity不符")
        _crossbind(base, inputs)
        for key, value in {
            "registry_run_id": run, "portfolio_parent_id": parent,
            "equity_parquet_sha256": equity, "trades_parquet_sha256": trades,
            "payload_hash": payload_hash, "raw_payload_sha256": _sha(raw),
            "base_artifact": base, "execution_inputs": inputs,
            "metadata_strategy_id": strategy, "metadata_strategy_version": version,
        }.items():
            object.__setattr__(self, key, value)

    @property
    def canonical_payload_hash(self) -> str:
        return self.payload_hash

    def materialize_result(
        self, *, equity_curve: pd.DataFrame, trades: pd.DataFrame,
        expected_registry_run_id: str, expected_portfolio_parent_id: str,
        equity_parquet_sha256: str, trades_parquet_sha256: str,
    ) -> RecommendationPortfolioBacktestResultDTO:
        result = self.base_artifact.materialize_result(
            equity_curve=equity_curve, trades=trades,
            expected_registry_run_id=expected_registry_run_id,
            expected_portfolio_parent_id=expected_portfolio_parent_id,
            equity_parquet_sha256=equity_parquet_sha256, trades_parquet_sha256=trades_parquet_sha256,
        )
        result.execution_input_capture = self.execution_inputs
        return result


def encode_portfolio_result_artifact_v3(
    result: RecommendationPortfolioBacktestResultDTO, *,
    registry_run_id: str, portfolio_parent_id: str, equity_parquet_sha256: str,
    trades_parquet_sha256: str, metadata_strategy_id: str | None,
    metadata_strategy_version: str | None, execution_inputs: RecommendationPortfolioExecutionInputsV1,
) -> RecommendationPortfolioResultArtifactV3:
    if (type(result) is not RecommendationPortfolioBacktestResultDTO
            or type(execution_inputs) is not RecommendationPortfolioExecutionInputsV1
            or result.execution_input_capture != execution_inputs):
        raise _fail("V3必須明示同一原producer execution inputs")
    kwargs = dict(registry_run_id=registry_run_id, portfolio_parent_id=portfolio_parent_id,
                  equity_parquet_sha256=equity_parquet_sha256, trades_parquet_sha256=trades_parquet_sha256)
    if result.period_precision_capture is not None:
        base: BasePortfolioArtifact = encode_portfolio_result_artifact_v2(
            result, **kwargs, metadata_strategy_id=metadata_strategy_id,
            metadata_strategy_version=metadata_strategy_version)
    else:
        if result.period_precision_observations or result.period_precision_capture_status in {"captured_unqualified", "partial"}:
            raise _fail("V3精確觀察缺capture不得降為V1")
        base = encode_portfolio_result_artifact(result, **kwargs)
    document: dict[str, object] = {
        "schema_version": RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_VERSION_V3,
        "schema_revision": RECOMMENDATION_PORTFOLIO_RESULT_SCHEMA_REVISION_V3,
        **kwargs,
        "payload": {
            "base_schema_version": base.schema_version, "base_schema_revision": base.schema_revision,
            "base_document": _strict_json_load(base.raw_payload),
            "execution_inputs": execution_inputs.to_dict(),
            "execution_inputs_identity_sha256": execution_inputs.input_identity_sha256,
            "metadata_strategy_id": metadata_strategy_id, "metadata_strategy_version": metadata_strategy_version,
        },
    }
    document["payload_hash"] = _sha(_canonical_json_bytes(document))
    return RecommendationPortfolioResultArtifactV3(_canonical_json_bytes(document))


def decode_portfolio_result_artifact_v3(raw_payload: bytes) -> RecommendationPortfolioResultArtifactV3:
    return RecommendationPortfolioResultArtifactV3(raw_payload)
