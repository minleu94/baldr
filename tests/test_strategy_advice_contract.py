"""驗證 Advice contract 的 canonical hash 與版本 create-only round-trip。"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from app_module.strategy_advice_contract import StrategyAdviceContract
from app_module.strategy_version_service import StrategyVersion, StrategyVersionService


class _Config:
    def __init__(self, root: Path) -> None:
        self.root = root

    def resolve_output_path(self, relative_path: str) -> Path:
        return self.root / relative_path


def _contract() -> StrategyAdviceContract:
    return StrategyAdviceContract(
        thesis="突破整理區後，趨勢延續條件仍成立",
        invalidation_conditions=("收盤跌破整理區下緣", "策略 regime 不再符合"),
        holding_horizon="20 個交易日",
        review_cadence="每 5 個交易日",
    )


def test_contract_hash_is_canonical_and_round_trips() -> None:
    contract = _contract()
    payload = contract.to_dict()

    assert payload["contract_sha256"] == contract.canonical_sha256
    assert StrategyAdviceContract.from_dict(payload) == contract
    assert StrategyAdviceContract.from_dict(dict(reversed(tuple(payload.items())))) == contract


@pytest.mark.parametrize(
    "mutation",
    (
        {"thesis": "改寫論點"},
        {"holding_horizon": "10 個交易日"},
        {"review_cadence": "每日"},
        {"invalidation_conditions": ["不同失效條件"]},
    ),
)
def test_contract_hash_rejects_changed_content(mutation: dict[str, object]) -> None:
    payload = _contract().to_dict()
    payload.update(mutation)

    with pytest.raises(ValueError, match="canonical contract bytes"):
        StrategyAdviceContract.from_dict(payload)


def test_contract_hash_rejects_unknown_or_missing_fields() -> None:
    payload = _contract().to_dict()

    with pytest.raises(ValueError, match="欄位必須完全符合"):
        StrategyAdviceContract.from_dict({**payload, "extra": "unknown"})
    payload.pop("review_cadence")
    with pytest.raises(ValueError, match="欄位必須完全符合"):
        StrategyAdviceContract.from_dict(payload)


def test_contract_hash_rejects_unsupported_schema_and_bad_hash_shape() -> None:
    payload = _contract().to_dict()
    payload["schema_version"] = "strategy-advice-contract.v2"
    with pytest.raises(ValueError, match="schema_version 不支援"):
        StrategyAdviceContract.from_dict(payload)

    payload = _contract().to_dict()
    payload["contract_sha256"] = "sha256:" + "A" * 64
    with pytest.raises(ValueError, match="小寫 sha256 digest"):
        StrategyAdviceContract.from_dict(payload)

    payload = _contract().to_dict()
    payload["contract_sha256"] = ""
    with pytest.raises(ValueError, match="小寫 sha256 digest"):
        StrategyAdviceContract.from_dict(payload)


@pytest.mark.parametrize(
    "values",
    (
        {"thesis": " "},
        {"holding_horizon": ""},
        {"review_cadence": " 每週"},
        {"invalidation_conditions": ()},
        {"invalidation_conditions": ("條件一", "條件一")},
        {"invalidation_conditions": ("條件一", " ")},
    ),
)
def test_contract_rejects_incomplete_or_noncanonical_values(values: dict[str, object]) -> None:
    args: dict[str, object] = {
        "thesis": "有效論點",
        "invalidation_conditions": ("收盤跌破明確門檻",),
        "holding_horizon": "20 個交易日",
        "review_cadence": "每 5 個交易日",
    }
    args.update(values)
    with pytest.raises((TypeError, ValueError)):
        StrategyAdviceContract(**args)  # type: ignore[arg-type]


def test_strategy_version_create_only_json_round_trip(tmp_path: Path) -> None:
    service = StrategyVersionService(_Config(tmp_path))
    contract = _contract()
    version_id = service.create_version(
        strategy_id="fixture-strategy",
        source_run_id="fixture-run",
        version_id="version-with-advice",
        advice_contract=contract,
    )
    path = service.versions_dir / f"{version_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["advice_contract"] == contract.to_dict()
    loaded = service.get_version(version_id)
    assert loaded is not None
    assert loaded.advice_contract == contract
    assert service.list_versions("fixture-strategy")[0]["advice_contract"] == contract.to_dict()

    before = path.read_bytes()
    different_contract = StrategyAdviceContract(
        thesis="方向改變時不再保留原進場論點",
        invalidation_conditions=("原始突破條件不成立",),
        holding_horizon="10 個交易日",
        review_cadence="每 2 個交易日",
    )
    with pytest.raises(FileExistsError):
        service.create_version(
            strategy_id="fixture-strategy",
            source_run_id="different-run",
            version_id=version_id,
            advice_contract=different_contract,
        )
    assert path.read_bytes() == before
    with pytest.raises(ValueError, match="create-only"):
        service.update_version(version_id, advice_contract=_contract())
    assert path.read_bytes() == before
    assert service.update_version(version_id, notes="只更新版本附註")
    assert service.get_version(version_id).advice_contract == contract


def test_legacy_strategy_version_json_omits_absent_contract_and_reads(tmp_path: Path) -> None:
    service = StrategyVersionService(_Config(tmp_path))
    version_id = service.create_version(
        strategy_id="legacy-strategy",
        source_run_id="legacy-run",
        version_id="legacy-version",
    )
    path = service.versions_dir / f"{version_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "advice_contract" not in payload

    legacy_payload = deepcopy(payload)
    legacy_payload.pop("advice_contract", None)
    legacy = StrategyVersion.from_dict(legacy_payload)
    assert legacy.advice_contract is None
    assert "advice_contract" not in legacy.to_dict()
    assert service.get_version(version_id).advice_contract is None


def test_strategy_version_reader_rejects_tampered_contract_hash(tmp_path: Path) -> None:
    service = StrategyVersionService(_Config(tmp_path))
    version_id = service.create_version(
        strategy_id="fixture-strategy",
        source_run_id="fixture-run",
        version_id="tampered-contract",
        advice_contract=_contract(),
    )
    path = service.versions_dir / f"{version_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["advice_contract"]["thesis"] = "未更新 hash 的篡改內容"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    assert service.get_version(version_id) is None
    assert service.list_versions("fixture-strategy") == []
