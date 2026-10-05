"""已驗證每日市場 cohort 的唯讀共用投影。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, NoReturn

from app_module.daily_market_feature_snapshot import (
    DAILY_MARKET_CONDITION_KEYS,
    DAILY_MARKET_FEATURE_KEYS,
)
from app_module.daily_market_method_contract import (
    method_contracts_payload,
    method_contracts_sha256,
)
from app_module.daily_market_research_screener import (
    DailyMarketResearchConditionResult,
    DailyMarketResearchScreenRow,
    evaluate_daily_market_conditions,
)
from app_module.daily_market_snapshot_repository import (
    DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA,
    VerifiedDailyMarketSnapshot,
    canonical_snapshot_sha256,
    snapshot_manifest_identity_sha256,
)


DailyMarketCohortConditionState = Literal["match", "no_match", "unknown"]
DailyMarketCohortSortKey = Literal[
    "stock_code", "data_date", "close", "ma20", "ma60"
]
_EXPECTED_CONDITION_KEYS = tuple(DAILY_MARKET_CONDITION_KEYS)
_FEATURE_KEYS = tuple(DAILY_MARKET_FEATURE_KEYS)


class DailyMarketCohortProjectionError(ValueError):
    """每日市場 cohort 投影的輸入驗證錯誤。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class DailyMarketCohortMethodCount:
    """單一既有方法在明示 cohort 中的三態人數。"""

    key: str
    method_id: str
    family: str
    version: str
    parameters: tuple[tuple[str, int | str], ...]
    match_count: int
    no_match_count: int
    unknown_count: int
    denominator: int


@dataclass(frozen=True, slots=True)
class DailyMarketCohortMember:
    """一檔 cohort 成員的已保存市場值與既有條件結果。"""

    stock_code: str
    data_date: str | None
    close: Decimal | None
    ma20: Decimal | None
    ma60: Decimal | None
    conditions: tuple[DailyMarketResearchConditionResult, ...]
    source_refs: tuple[tuple[str, str], ...]
    snapshot_missing: bool = False

    def condition(self, key: str) -> DailyMarketResearchConditionResult:
        """依既有方法 key 取得這檔股票的條件結果。"""

        for item in self.conditions:
            if item.key == key:
                return item
        raise KeyError(key)


@dataclass(frozen=True, slots=True)
class DailyMarketCohortProjection:
    """供每日市場名單與摘要面板共用的 immutable readmodel。"""

    cohort_id: str
    decision_date: str
    manifest_schema_version: str
    source_snapshot_id: str
    source_snapshot_hash: str
    method_contracts_sha256: str
    completeness: str
    declared_stock_codes: tuple[str, ...]
    published_stock_codes: tuple[str, ...]
    missing_stock_codes: tuple[str, ...]
    published_count: int
    method_counts: tuple[DailyMarketCohortMethodCount, ...]
    members: tuple[DailyMarketCohortMember, ...]
    original_rank_state: Literal["unknown"] = "unknown"


def project_daily_market_cohort(
    snapshot: VerifiedDailyMarketSnapshot,
    rows: Sequence[DailyMarketResearchScreenRow],
    *,
    expected_snapshot_root: str | Path | None = None,
) -> DailyMarketCohortProjection:
    """將 verified v2 snapshot 與全 cohort screener rows 投影成共用 readmodel。

    ``rows`` 必須是對同一 snapshot 呼叫 screener，並同時帶入固定兩個
    condition key 的完整結果。部分快照中 manifest 已宣告但沒有 artifact
    的股票會以 unknown placeholder 保留於分母與 members。
    """

    manifest, declared_codes, contracts = _validate_snapshot(snapshot)
    payload_codes = tuple(sorted(snapshot.stock_snapshots))
    row_by_code, snapshot_root = _validate_rows(
        snapshot,
        rows,
        payload_codes,
        contracts,
        expected_snapshot_root=expected_snapshot_root,
    )
    records = _manifest_stock_records(manifest)
    missing_codes = tuple(code for code in declared_codes if code not in snapshot.stock_snapshots)
    members: list[DailyMarketCohortMember] = []
    counts = {
        key: {"match": 0, "no_match": 0, "unknown": 0}
        for key in _EXPECTED_CONDITION_KEYS
    }

    for code in declared_codes:
        payload = snapshot.stock_snapshots.get(code)
        if payload is None:
            condition_results = tuple(
                _missing_condition(key, contracts[key], snapshot.decision_date)
                for key in _EXPECTED_CONDITION_KEYS
            )
            member = DailyMarketCohortMember(
                stock_code=code,
                data_date=None,
                close=None,
                ma20=None,
                ma60=None,
                conditions=condition_results,
                source_refs=(),
                snapshot_missing=True,
            )
        else:
            row = row_by_code[code]
            feature_values = _feature_values(payload)
            condition_results = tuple(
                _validated_row_condition(
                    _row_condition(row, key),
                    key,
                    contracts[key],
                    snapshot.decision_date,
                )
                for key in _EXPECTED_CONDITION_KEYS
            )
            member = DailyMarketCohortMember(
                stock_code=code,
                data_date=_normalize_data_date(row.data_date),
                close=feature_values["close"],
                ma20=feature_values["MA20"],
                ma60=feature_values["MA60"],
                conditions=condition_results,
                source_refs=_source_refs(records[code]),
            )

        for condition in member.conditions:
            counts[condition.key][condition.state] += 1
        members.append(member)

    denominator = len(declared_codes)
    method_counts = tuple(
        _method_count(key, contracts[key], counts[key], denominator)
        for key in _EXPECTED_CONDITION_KEYS
    )
    # 根目錄用於確認 rows 的來源一致；readmodel 不讀取或回寫該路徑。
    del snapshot_root
    return DailyMarketCohortProjection(
        cohort_id=snapshot.cohort_id,
        decision_date=snapshot.decision_date.isoformat(),
        manifest_schema_version=str(manifest["schema_version"]),
        source_snapshot_id=snapshot.manifest_identity_sha256,
        source_snapshot_hash=snapshot.manifest_sha256,
        method_contracts_sha256=str(manifest["method_contracts_sha256"]),
        completeness=snapshot.completeness,
        declared_stock_codes=declared_codes,
        published_stock_codes=payload_codes,
        missing_stock_codes=missing_codes,
        published_count=len(payload_codes),
        method_counts=method_counts,
        members=tuple(members),
    )


def sort_daily_market_cohort_members(
    members: Sequence[DailyMarketCohortMember],
    key: DailyMarketCohortSortKey,
    *,
    descending: bool = False,
) -> tuple[DailyMarketCohortMember, ...]:
    """回傳 client-side 排序副本，未知數值固定置尾且不改變輸入。"""

    if key not in {"stock_code", "data_date", "close", "ma20", "ma60"}:
        raise ValueError(f"不支援的 cohort 排序欄位：{key!r}")
    if not isinstance(descending, bool):
        raise TypeError("descending 必須是 bool")
    if isinstance(members, (str, bytes)) or not isinstance(members, Sequence):
        raise TypeError("members 必須是 cohort 成員序列")
    values = tuple(members)
    if any(not isinstance(item, DailyMarketCohortMember) for item in values):
        raise TypeError("members 僅能包含 DailyMarketCohortMember")

    known = [item for item in values if getattr(item, key) is not None]
    unknown = [item for item in values if getattr(item, key) is None]
    known.sort(key=lambda item: item.stock_code)
    known.sort(key=lambda item: getattr(item, key), reverse=descending)
    unknown.sort(key=lambda item: item.stock_code)
    return tuple((*known, *unknown))


def _validate_snapshot(
    snapshot: VerifiedDailyMarketSnapshot,
) -> tuple[Mapping[str, Any], tuple[str, ...], Mapping[str, Mapping[str, Any]]]:
    if not isinstance(snapshot, VerifiedDailyMarketSnapshot):
        raise DailyMarketCohortProjectionError(
            "cohort_snapshot_unverified",
            "snapshot 必須由 DailyMarketSnapshotRepository 驗證後取得",
        )
    manifest = snapshot.manifest
    if not isinstance(manifest, Mapping):
        _fail("cohort_manifest_invalid", "已驗證 snapshot 的 manifest 格式錯誤")
    if manifest.get("schema_version") != DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA:
        _fail("cohort_manifest_schema_invalid", "投影僅接受 manifest v2")
    if canonical_snapshot_sha256(manifest) != snapshot.manifest_sha256:
        _fail("cohort_manifest_hash_mismatch", "manifest hash 與 snapshot 不符")
    if snapshot_manifest_identity_sha256(manifest) != snapshot.manifest_identity_sha256:
        _fail("cohort_manifest_identity_mismatch", "manifest identity 與 snapshot 不符")
    if (
        manifest.get("cohort_id") != snapshot.cohort_id
        or manifest.get("decision_date") != snapshot.decision_date.isoformat()
        or manifest.get("completeness") != snapshot.completeness
    ):
        _fail("cohort_snapshot_metadata_mismatch", "snapshot 中繼資料與 manifest 不符")

    raw_codes = manifest.get("declared_stock_codes")
    if (
        not isinstance(raw_codes, list)
        or not raw_codes
        or any(not isinstance(code, str) or not code for code in raw_codes)
    ):
        _fail("cohort_stock_scope_invalid", "manifest 宣告的股票代碼無效")
    declared_codes = tuple(raw_codes)
    if declared_codes != tuple(sorted(set(declared_codes))):
        _fail("cohort_stock_scope_invalid", "manifest 股票代碼順序或重複狀態無效")
    if not isinstance(snapshot.stock_snapshots, Mapping):
        _fail("cohort_payloads_invalid", "已驗證的股票 snapshot 格式錯誤")
    payload_codes = set(snapshot.stock_snapshots)
    if not payload_codes.issubset(set(declared_codes)):
        _fail("cohort_payload_scope_mismatch", "snapshot payload 包含未宣告的股票代碼")

    raw_contracts = manifest.get("method_contracts")
    if not isinstance(raw_contracts, Mapping) or set(raw_contracts) != set(_EXPECTED_CONDITION_KEYS):
        _fail("cohort_method_contracts_invalid", "manifest 方法與既有固定方法不符")
    raw_contract_hash = manifest.get("method_contracts_sha256")
    if (
        not isinstance(raw_contract_hash, str)
        or method_contracts_sha256(raw_contracts) != raw_contract_hash
        or dict(raw_contracts) != method_contracts_payload()
    ):
        _fail("cohort_method_contract_hash_mismatch", "方法契約雜湊無效")
    contracts: dict[str, Mapping[str, Any]] = {}
    for key in _EXPECTED_CONDITION_KEYS:
        item = raw_contracts.get(key)
        if not isinstance(item, Mapping):
            _fail("cohort_method_contracts_invalid", f"manifest 缺少方法契約：{key}")
        contracts[key] = item

    records = _manifest_stock_records(manifest)
    if set(records) != payload_codes:
        _fail("cohort_payload_scope_mismatch", "manifest 記錄與已發布 payload 不一致")
    for code, payload in snapshot.stock_snapshots.items():
        if not isinstance(payload, Mapping):
            _fail("cohort_payload_invalid", f"股票 snapshot payload 無效：{code}")
        expected_hash = records[code].get("artifact_sha256")
        if canonical_snapshot_sha256(payload) != expected_hash:
            _fail("cohort_payload_hash_mismatch", f"股票 snapshot payload 雜湊不符：{code}")
        if (
            payload.get("stock_code") != code
            or payload.get("method_contracts") != raw_contracts
            or payload.get("method_contracts_sha256") != raw_contract_hash
        ):
            _fail("cohort_payload_binding_mismatch", f"股票 snapshot 方法綁定不符：{code}")
    return manifest, declared_codes, contracts


def _validate_rows(
    snapshot: VerifiedDailyMarketSnapshot,
    rows: Sequence[DailyMarketResearchScreenRow],
    payload_codes: tuple[str, ...],
    contracts: Mapping[str, Mapping[str, Any]],
    *,
    expected_snapshot_root: str | Path | None,
) -> tuple[dict[str, DailyMarketResearchScreenRow], str]:
    if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
        raise TypeError("rows 必須是 filter_rows 回傳的序列")
    by_code: dict[str, DailyMarketResearchScreenRow] = {}
    normalized_roots: set[str] = set()
    expected_root = _normalize_root(expected_snapshot_root) if expected_snapshot_root is not None else None
    for row in rows:
        if not isinstance(row, DailyMarketResearchScreenRow):
            _fail("cohort_row_type_invalid", "rows 僅能包含 DailyMarketResearchScreenRow")
        if row.stock_code in by_code:
            _fail("cohort_rows_duplicate", f"screen row 有重複股票：{row.stock_code}")
        by_code[row.stock_code] = row
        row_root = _normalize_root(row.snapshot_root)
        normalized_roots.add(row_root)
        if expected_root is not None and row_root != expected_root:
            _fail("cohort_row_root_mismatch", "screen row 的來源目錄與已接受 snapshot 不符")
    if set(by_code) != set(payload_codes):
        _fail("cohort_rows_scope_mismatch", "screen rows 必須完整且只包含已發布 snapshot 各一次")
    if len(normalized_roots) > 1:
        _fail("cohort_row_root_mismatch", "screen rows 使用了不同的 snapshot 來源目錄")
    if not normalized_roots:
        if expected_root is None:
            _fail("cohort_row_root_missing", "沒有已發布 artifact 時必須提供 expected_snapshot_root")
        snapshot_root = expected_root
    else:
        snapshot_root = next(iter(normalized_roots))

    for code, row in by_code.items():
        payload = snapshot.stock_snapshots[code]
        if (
            row.cohort_id != snapshot.cohort_id
            or row.decision_date != snapshot.decision_date.isoformat()
            or row.completeness != snapshot.completeness
        ):
            _fail("cohort_row_scope_mismatch", f"screen row 的 cohort 或決策日期不符：{code}")
        if (
            row.source_snapshot_id != snapshot.manifest_identity_sha256
            or row.source_snapshot_hash != snapshot.manifest_sha256
            or row.snapshot_identity_sha256 != payload.get("snapshot_identity_sha256")
            or row.input_fingerprint_sha256 != payload.get("input_fingerprint_sha256")
        ):
            _fail("cohort_row_source_mismatch", f"screen row 的來源或雜湊不符：{code}")
        if row.data_date != str(payload.get("market_date") or ""):
            _fail("cohort_row_date_mismatch", f"screen row 的市場資料日期不符：{code}")
        if row.condition_keys != _EXPECTED_CONDITION_KEYS or row.combine_mode != "AND":
            _fail("cohort_row_conditions_incomplete", "filter_rows 必須以 AND 傳入兩個固定方法")
        if not row.research_only or row.historical_pit_eligible:
            _fail("cohort_row_policy_mismatch", f"screen row 的研究用途政策不符：{code}")
        raw_conditions = tuple(row.conditions)
        if len(raw_conditions) != len(_EXPECTED_CONDITION_KEYS):
            _fail("cohort_row_conditions_incomplete", f"screen row 的方法結果不完整：{code}")
        keys = tuple(item.key for item in raw_conditions)
        if set(keys) != set(_EXPECTED_CONDITION_KEYS) or len(set(keys)) != len(keys):
            _fail("cohort_row_conditions_incomplete", f"screen row 的方法結果重複或缺漏：{code}")
        for key in _EXPECTED_CONDITION_KEYS:
            _validated_row_condition(
                _row_condition(row, key), key, contracts[key], snapshot.decision_date
            )
        raw_snapshot_conditions = payload.get("conditions")
        if not isinstance(raw_snapshot_conditions, Mapping):
            _fail("cohort_row_evaluation_mismatch", f"verified 條件 payload 格式錯誤：{code}")
        expected_evaluation = evaluate_daily_market_conditions(
            raw_snapshot_conditions,
            _EXPECTED_CONDITION_KEYS,
            "AND",
            expected_decision_date=snapshot.decision_date,
        )
        actual_conditions = tuple(
            _row_condition(row, key).to_dict() for key in _EXPECTED_CONDITION_KEYS
        )
        expected_conditions = tuple(item.to_dict() for item in expected_evaluation.conditions)
        if (
            actual_conditions != expected_conditions
            or row.combined_state != expected_evaluation.combined_state
            or row.why != expected_evaluation.why
            or row.why_not != expected_evaluation.why_not
        ):
            _fail("cohort_row_evaluation_mismatch", f"screen row 的條件結果與 verified payload 不符：{code}")
    return by_code, snapshot_root


def _validated_row_condition(
    result: DailyMarketResearchConditionResult,
    key: str,
    contract: Mapping[str, Any],
    decision_date: date,
) -> DailyMarketResearchConditionResult:
    parameters = _parameters_tuple(result.parameters)
    expected_parameters = _parameters_tuple(contract.get("parameters"))
    if (
        result.key != key
        or result.method_id != contract.get("method_id")
        or result.family != contract.get("family")
        or result.version != contract.get("version")
        or parameters != expected_parameters
        or result.decision_date != decision_date.isoformat()
        or result.eligibility not in {"eligible", "unknown"}
        or result.state not in {"match", "no_match", "unknown"}
        or result.relation not in {"above", "below", "equal", "unknown"}
    ):
        _fail("cohort_row_method_binding_mismatch", f"screen row 方法契約綁定不符：{key}")
    return result


def _row_condition(
    row: DailyMarketResearchScreenRow,
    key: str,
) -> DailyMarketResearchConditionResult:
    for item in row.conditions:
        if item.key == key:
            return item
    _fail("cohort_row_conditions_incomplete", f"screen row 缺少方法結果：{key}")


def _feature_values(payload: Mapping[str, Any]) -> dict[str, Decimal | None]:
    features = payload.get("features")
    if not isinstance(features, Mapping) or set(features) != set(_FEATURE_KEYS):
        _fail("cohort_feature_schema_invalid", "snapshot feature 欄位格式錯誤")
    values: dict[str, Decimal | None] = {}
    for key in _FEATURE_KEYS:
        feature = features.get(key)
        if not isinstance(feature, Mapping):
            _fail("cohort_feature_schema_invalid", f"snapshot feature 格式錯誤：{key}")
        state = feature.get("state")
        raw_value = feature.get("value")
        if state == "unknown":
            if raw_value is not None:
                _fail("cohort_feature_state_invalid", f"unknown feature 不得帶有數值：{key}")
            values[key] = None
            continue
        if state != "observed" or not isinstance(raw_value, str):
            _fail("cohort_feature_state_invalid", f"observed feature 數值格式錯誤：{key}")
        try:
            number = Decimal(raw_value)
        except (InvalidOperation, ValueError) as exc:
            raise DailyMarketCohortProjectionError(
                "cohort_feature_value_invalid", f"snapshot feature 不是有效 Decimal：{key}"
            ) from exc
        if not number.is_finite():
            _fail("cohort_feature_value_invalid", f"snapshot feature 不是有限 Decimal：{key}")
        values[key] = number
    return values


def _method_count(
    key: str,
    contract: Mapping[str, Any],
    values: Mapping[str, int],
    denominator: int,
) -> DailyMarketCohortMethodCount:
    if sum(values.values()) != denominator:
        _fail("cohort_method_count_invalid", f"方法人數加總與分母不符：{key}")
    return DailyMarketCohortMethodCount(
        key=key,
        method_id=str(contract["method_id"]),
        family=str(contract["family"]),
        version=str(contract["version"]),
        parameters=_parameters_tuple(contract.get("parameters")),
        match_count=values["match"],
        no_match_count=values["no_match"],
        unknown_count=values["unknown"],
        denominator=denominator,
    )


def _missing_condition(
    key: str,
    contract: Mapping[str, Any],
    decision_date: date,
) -> DailyMarketResearchConditionResult:
    return DailyMarketResearchConditionResult(
        key=key,
        state="unknown",
        relation="unknown",
        reason="snapshot_missing",
        method_id=str(contract["method_id"]),
        family=str(contract["family"]),
        version=str(contract["version"]),
        parameters=MappingProxyType(dict(_parameters_tuple(contract.get("parameters")))),
        decision_date=decision_date.isoformat(),
        eligibility="unknown",
        unknown_reason="snapshot_missing",
    )


def _manifest_stock_records(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    records = manifest.get("stocks")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        _fail("cohort_manifest_stocks_invalid", "manifest 股票記錄格式錯誤")
    result: dict[str, Mapping[str, Any]] = {}
    for item in records:
        if not isinstance(item, Mapping):
            _fail("cohort_manifest_stocks_invalid", "manifest 股票記錄格式錯誤")
        code = item.get("stock_code")
        if not isinstance(code, str) or code in result:
            _fail("cohort_manifest_stocks_invalid", "manifest 股票記錄包含重複代碼")
        result[code] = item
    return result


def _source_refs(record: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    values = record.get("source_refs")
    if not isinstance(values, Mapping):
        _fail("cohort_source_refs_invalid", "manifest source_refs 格式錯誤")
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in values.items()):
        _fail("cohort_source_refs_invalid", "manifest source_refs 必須使用文字值")
    return tuple(sorted(values.items()))


def _parameters_tuple(value: Any) -> tuple[tuple[str, int | str], ...]:
    if not isinstance(value, Mapping):
        return ()
    if any(
        not isinstance(key, str)
        or not isinstance(item, (int, str))
        or isinstance(item, bool)
        for key, item in value.items()
    ):
        return ()
    return tuple(sorted(value.items()))


def _normalize_data_date(value: str) -> str | None:
    if value == "":
        return None
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise DailyMarketCohortProjectionError(
            "cohort_data_date_invalid", "screen row data_date 不是有效 ISO 日期"
        ) from exc
    if parsed.isoformat() != value:
        _fail("cohort_data_date_invalid", "screen row data_date 不是標準 ISO 日期格式")
    return value


def _normalize_root(value: str | Path) -> str:
    if not str(value).strip():
        _fail("cohort_row_root_missing", "snapshot 來源目錄不可為空")
    try:
        return str(Path(value).expanduser().resolve(strict=False))
    except (OSError, RuntimeError, ValueError) as exc:
        raise DailyMarketCohortProjectionError(
            "cohort_row_root_invalid", "snapshot 來源目錄無法正規化"
        ) from exc


def _fail(code: str, message: str) -> NoReturn:
    raise DailyMarketCohortProjectionError(code, message)
