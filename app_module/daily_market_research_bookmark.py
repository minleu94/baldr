"""每日市場研究收藏的不可變儲存契約。

收藏保留使用者按下收藏時已驗證的快照與查詢身份，不建立 Advice 結果，也不重算市場特徵。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Literal, NoReturn

from app_module.daily_market_method_contract import method_contracts_sha256
from app_module.daily_market_research_screener import (
    DAILY_MARKET_RESEARCH_SCOPE_LABEL,
    DAILY_MARKET_RESEARCH_SOURCE_KIND,
    DailyMarketResearchConditionResult,
    DailyMarketResearchScreenRow,
    evaluate_daily_market_conditions,
)
from app_module.daily_market_snapshot_repository import (
    DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA,
    DailyMarketSnapshotRepository,
    VerifiedDailyMarketSnapshot,
    canonical_snapshot_sha256,
    snapshot_manifest_identity_sha256,
)
from app_module.research_session.session_dtos import ResearchStockContextDTO


DAILY_MARKET_RESEARCH_BOOKMARK_SCHEMA = "daily-market-research-bookmark.v1"
ORIGINAL_STOCK_RANKING_BOOKMARK_SCHEMA = "daily-market-research-bookmark.v2"
DAILY_MARKET_RESEARCH_BOOKMARK_SOURCE = "daily_market_research_bookmark"
ORIGINAL_STOCK_RANKING_BOOKMARK_SOURCE = "original_stock_ranking_bookmark"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SORT_KEYS = frozenset({"stock_code", "data_date", "close", "ma20", "ma60"})
_CONDITION_KEYS = frozenset({"close_above_ma20", "close_above_ma60"})
_V1_CONTEXT_KEYS = (
    "stock_code",
    "stock_name",
    "decision_date",
    "data_date",
    "result_id",
    "identity_status",
    "source_snapshot_id",
    "source_snapshot_hash",
    "profile_id",
    "profile_version",
    "source_id",
    "source_version",
    "mapping_source_id",
    "mapping_version",
    "mapping_observed_date",
    "source_kind",
    "source_label",
    "source_workspace",
    "ml_scope_mode",
    "daily_snapshot_root",
    "daily_snapshot_cohort_id",
    "daily_snapshot_condition_keys",
    "daily_snapshot_combine_mode",
)
_PAYLOAD_KEYS = frozenset(
    {
        "schema_version",
        "bookmark_id",
        "payload_sha256",
        "query_sha256",
        "stock_code",
        "stock_name",
        "source",
        "source_workspace",
        "source_id",
        "result_id",
        "source_snapshot_id",
        "source_snapshot_hash",
        "snapshot_identity_sha256",
        "input_fingerprint_sha256",
        "decision_date",
        "data_date",
        "snapshot_root",
        "cohort_id",
        "declared_stock_codes",
        "condition_keys",
        "combine_mode",
        "filter_state",
        "method_contracts",
        "method_contracts_sha256",
        "conditions",
        "combined_state",
        "why",
        "why_not",
        "completeness",
        "manifest_schema_version",
        "sort_key",
        "descending",
        "context",
    }
)
_RANK_PAYLOAD_KEYS = frozenset(
    {
        "schema_version",
        "bookmark_id",
        "payload_sha256",
        "query_sha256",
        "stock_code",
        "stock_name",
        "source",
        "source_workspace",
        "source_id",
        "result_id",
        "context",
    }
)
_RANK_CONTEXT_KEYS = frozenset({*_V1_CONTEXT_KEYS, "rank_context"})


class DailyMarketResearchBookmarkError(ValueError):
    """研究收藏驗證錯誤，附帶穩定的機器可讀代碼。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class DailyMarketResearchBookmark:
    """已驗證的列身份與收藏當下捕獲的不可變查詢上下文。"""

    bookmark_id: str
    stock_code: str
    stock_name: str
    source_snapshot_id: str
    source_snapshot_hash: str
    snapshot_identity_sha256: str
    input_fingerprint_sha256: str
    decision_date: str
    data_date: str
    snapshot_root: str
    cohort_id: str
    declared_stock_codes: tuple[str, ...]
    condition_keys: tuple[str, ...]
    combine_mode: Literal["AND", "OR"]
    filter_state: Literal["all", "match", "no_match", "unknown"]
    method_contracts_json: str
    method_contracts_sha256: str
    conditions_json: str
    combined_state: Literal["match", "no_match", "unknown"]
    why: tuple[str, ...]
    why_not: tuple[str, ...]
    completeness: str
    manifest_schema_version: str
    sort_key: str
    descending: bool
    _query_sha256: str
    _payload_sha256: str

    @property
    def query_sha256(self) -> str:
        return self._query_sha256

    @property
    def payload_sha256(self) -> str:
        return self._payload_sha256

    @property
    def method_contracts(self) -> dict[str, Any]:
        return json.loads(self.method_contracts_json)

    @property
    def conditions(self) -> list[dict[str, Any]]:
        return json.loads(self.conditions_json)

    @property
    def context(self) -> ResearchStockContextDTO:
        """重建研究上下文，不虛構推薦 result_id。"""

        return ResearchStockContextDTO(
            stock_code=self.stock_code,
            stock_name=self.stock_name,
            decision_date=self.decision_date,
            data_date=self.data_date,
            result_id="",
            source_snapshot_id=self.source_snapshot_id,
            source_snapshot_hash=self.source_snapshot_hash,
            source_kind=DAILY_MARKET_RESEARCH_SOURCE_KIND,
            source_label="每日市場研究收藏",
            source_workspace="watchlist",
            source_id=self.bookmark_id,
            daily_snapshot_root=self.snapshot_root,
            daily_snapshot_cohort_id=self.cohort_id,
            daily_snapshot_condition_keys=",".join(self.condition_keys),
            daily_snapshot_combine_mode=self.combine_mode,
        )

    def _body(self) -> dict[str, Any]:
        context = _v1_context_payload(self.context)
        return {
            "schema_version": DAILY_MARKET_RESEARCH_BOOKMARK_SCHEMA,
            "bookmark_id": self.bookmark_id,
            "payload_sha256": self._payload_sha256,
            "query_sha256": self._query_sha256,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "source": DAILY_MARKET_RESEARCH_BOOKMARK_SOURCE,
            "source_workspace": "watchlist",
            "source_id": self.bookmark_id,
            "result_id": "",
            "source_snapshot_id": self.source_snapshot_id,
            "source_snapshot_hash": self.source_snapshot_hash,
            "snapshot_identity_sha256": self.snapshot_identity_sha256,
            "input_fingerprint_sha256": self.input_fingerprint_sha256,
            "decision_date": self.decision_date,
            "data_date": self.data_date,
            "snapshot_root": self.snapshot_root,
            "cohort_id": self.cohort_id,
            "declared_stock_codes": list(self.declared_stock_codes),
            "condition_keys": list(self.condition_keys),
            "combine_mode": self.combine_mode,
            "filter_state": self.filter_state,
            "method_contracts": self.method_contracts,
            "method_contracts_sha256": self.method_contracts_sha256,
            "conditions": self.conditions,
            "combined_state": self.combined_state,
            "why": list(self.why),
            "why_not": list(self.why_not),
            "completeness": self.completeness,
            "manifest_schema_version": self.manifest_schema_version,
            "sort_key": self.sort_key,
            "descending": self.descending,
            "context": context,
        }

    def to_dict(self) -> dict[str, Any]:
        """回傳固定 v1 payload 的獨立 JSON-safe 複本。"""

        return self._body()


@dataclass(frozen=True, slots=True)
class OriginalStockRankingBookmark:
    """保存原始強弱排名 manifest 身份與選取股票，不複製或重算數值分數。"""

    bookmark_id: str
    stock_code: str
    stock_name: str
    context_json: str
    _query_sha256: str
    _payload_sha256: str

    @property
    def context(self) -> ResearchStockContextDTO:
        value = json.loads(self.context_json)
        if not isinstance(value, Mapping):
            _fail("bookmark_context_invalid", "rank bookmark context 必須是 object")
        return ResearchStockContextDTO(**dict(value))

    @property
    def rank_context(self):
        return self.context.rank_context

    @property
    def query_sha256(self) -> str:
        return self._query_sha256

    @property
    def payload_sha256(self) -> str:
        return self._payload_sha256

    def _body(self) -> dict[str, Any]:
        return {
            "schema_version": ORIGINAL_STOCK_RANKING_BOOKMARK_SCHEMA,
            "bookmark_id": self.bookmark_id,
            "payload_sha256": self._payload_sha256,
            "query_sha256": self._query_sha256,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "source": ORIGINAL_STOCK_RANKING_BOOKMARK_SOURCE,
            "source_workspace": "watchlist",
            "source_id": self.bookmark_id,
            "result_id": "",
            "context": json.loads(self.context_json),
        }

    def to_dict(self) -> dict[str, Any]:
        """回傳 rank bookmark v2 payload 的獨立 JSON-safe 複本。"""

        return self._body()


@dataclass(frozen=True, slots=True)
class DailyMarketResearchBookmarkRestoreToken:
    """精確移除一筆收藏後，用來回復原項目的不透明快照。"""

    watchlist_id: str
    bookmark_id: str
    item_payload_json: str
    item_index: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "watchlist_id": self.watchlist_id,
            "bookmark_id": self.bookmark_id,
            "item_payload": json.loads(self.item_payload_json),
            "item_index": self.item_index,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketResearchBookmarkMutationResult:
    """供 UI 顯示的新增、移除與回復結果。"""

    status: str
    code: str
    message: str
    bookmark_id: str
    watchlist_id: str
    revision: int | None = None
    restore_token: DailyMarketResearchBookmarkRestoreToken | None = None

    @property
    def succeeded(self) -> bool:
        return self.status in {"added", "already_present", "removed", "restored"}

    @property
    def source_id(self) -> str:
        """Watchlist item source_id 與精確 bookmark_id 相同。"""

        return self.bookmark_id


def create_daily_market_research_bookmark(
    verified_snapshot: VerifiedDailyMarketSnapshot,
    row: DailyMarketResearchScreenRow,
    sort_key: str = "stock_code",
    descending: bool = False,
    stock_name: str = "",
    filter_state: str = "all",
) -> DailyMarketResearchBookmark:
    """只有畫面列與已驗證 v2 來源完全相符時才建立收藏。"""

    if not isinstance(verified_snapshot, VerifiedDailyMarketSnapshot):
        _fail("snapshot_unverified", "收藏需要 reader 驗證過的每日市場快照")
    if not isinstance(row, DailyMarketResearchScreenRow):
        _fail("row_invalid", "收藏來源必須是原始 DailyMarketResearchScreenRow")
    if sort_key not in _SORT_KEYS:
        _fail("query_sort_invalid", "收藏排序欄位不在固定研究欄位內")
    if not isinstance(descending, bool):
        _fail("query_sort_invalid", "descending 必須是布林值")
    if filter_state not in {"all", "match", "no_match", "unknown"}:
        _fail("query_filter_invalid", "filter_state 必須是 all/match/no_match/unknown")

    snapshot = verified_snapshot
    manifest = snapshot.manifest
    if not isinstance(manifest, Mapping):
        _fail("snapshot_manifest_invalid", "verified snapshot 缺少 manifest")
    if manifest.get("schema_version") != DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA:
        _fail("snapshot_schema_mismatch", "每日研究 bookmark 只接受已驗證的 v2 manifest")
    if canonical_snapshot_sha256(manifest) != snapshot.manifest_sha256:
        _fail("snapshot_hash_mismatch", "manifest 內容與 verified snapshot hash 不符")
    if snapshot_manifest_identity_sha256(manifest) != snapshot.manifest_identity_sha256:
        _fail("snapshot_identity_mismatch", "manifest identity 與 verified snapshot 不符")
    if (
        str(manifest.get("cohort_id") or "") != snapshot.cohort_id
        or str(manifest.get("decision_date") or "") != snapshot.decision_date.isoformat()
    ):
        _fail("snapshot_date_or_cohort_mismatch", "manifest 與 verified snapshot 日期或 cohort 不符")

    raw_declared = manifest.get("declared_stock_codes")
    declared_codes = _normalize_stock_codes(raw_declared, "declared_stock_codes")
    code = str(row.stock_code or "").strip()
    if code not in declared_codes or code not in snapshot.stock_snapshots:
        _fail("row_outside_snapshot", "收藏股票不在 verified snapshot 的已發布 cohort 內")

    payload = snapshot.stock_snapshots[code]
    if not isinstance(payload, Mapping):
        _fail("snapshot_artifact_invalid", "股票快照 artifact 不是 object")
    if (
        row.cohort_id != snapshot.cohort_id
        or row.decision_date != snapshot.decision_date.isoformat()
        or row.source_snapshot_id != snapshot.manifest_identity_sha256
        or row.source_snapshot_hash != snapshot.manifest_sha256
        or row.snapshot_identity_sha256 != payload.get("snapshot_identity_sha256")
        or row.input_fingerprint_sha256 != payload.get("input_fingerprint_sha256")
        or row.data_date != str(payload.get("market_date") or "")
        or row.completeness != snapshot.completeness
    ):
        _fail("row_source_mismatch", "畫面列的日期、來源或 hash 與 verified snapshot 不符")
    if row.research_only is not True or row.historical_pit_eligible is not False:
        _fail("row_policy_invalid", "每日市場收藏必須保留 research-only 與 PIT=false 邊界")
    if row.research_scope_label != DAILY_MARKET_RESEARCH_SCOPE_LABEL:
        _fail("row_scope_invalid", "畫面列的研究 scope 不符合每日市場研究契約")

    snapshot_root = _normalize_root(row.snapshot_root)
    _verify_snapshot_root(snapshot, snapshot_root, declared_codes)
    conditions_payload = payload.get("conditions")
    keys = tuple(str(value).strip() for value in row.condition_keys)
    if (
        not keys
        or len(keys) != len(set(keys))
        or any(key not in _CONDITION_KEYS for key in keys)
        or row.combine_mode not in {"AND", "OR"}
    ):
        _fail("query_filter_invalid", "收藏條件或 AND/OR 組合方式無效")
    evaluation = evaluate_daily_market_conditions(
        conditions_payload if isinstance(conditions_payload, Mapping) else {},
        keys,
        row.combine_mode,
        expected_decision_date=snapshot.decision_date,
    )
    if (
        row.conditions != evaluation.conditions
        or row.combined_state != evaluation.combined_state
        or row.why != evaluation.why
        or row.why_not != evaluation.why_not
    ):
        _fail("row_condition_mismatch", "畫面條件結果與 verified artifact 不符")
    if filter_state != "all" and evaluation.combined_state != filter_state:
        _fail("row_hidden_by_filter", "畫面列狀態不符合當下顯示 filter_state")

    raw_contracts = manifest.get("method_contracts")
    if not isinstance(raw_contracts, Mapping):
        _fail("method_contract_invalid", "manifest 缺少已捕獲的方法契約")
    contracts = json.loads(_canonical_json(raw_contracts))
    contract_hash = str(manifest.get("method_contracts_sha256") or "")
    _validate_method_contracts(contracts, contract_hash)
    if (
        payload.get("method_contracts") != contracts
        or payload.get("method_contracts_sha256") != contract_hash
    ):
        _fail("method_contract_mismatch", "股票 artifact 與 manifest 方法契約不一致")
    for condition in evaluation.conditions:
        _validate_condition_contract(condition, contracts, snapshot.decision_date.isoformat())

    data_date = _normalize_optional_date(row.data_date, "data_date")
    decision_date = snapshot.decision_date.isoformat()
    if data_date and data_date > decision_date:
        _fail("snapshot_date_invalid", "data_date 不可晚於 decision_date")

    context_fields = {
        "stock_code": code,
        "stock_name": str(stock_name or code).strip() or code,
        "source_snapshot_id": snapshot.manifest_identity_sha256,
        "source_snapshot_hash": snapshot.manifest_sha256,
        "snapshot_identity_sha256": row.snapshot_identity_sha256,
        "input_fingerprint_sha256": row.input_fingerprint_sha256,
        "decision_date": decision_date,
        "data_date": data_date,
        "snapshot_root": snapshot_root,
        "cohort_id": snapshot.cohort_id,
        "declared_stock_codes": list(declared_codes),
        "condition_keys": list(keys),
        "combine_mode": row.combine_mode,
        "filter_state": filter_state,
        "method_contracts": contracts,
        "method_contracts_sha256": contract_hash,
        "conditions": [condition.to_dict() for condition in evaluation.conditions],
        "combined_state": evaluation.combined_state,
        "why": list(evaluation.why),
        "why_not": list(evaluation.why_not),
        "completeness": snapshot.completeness,
        "manifest_schema_version": str(manifest["schema_version"]),
        "sort_key": sort_key,
        "descending": descending,
    }
    query_payload = {
        "source_snapshot_id": context_fields["source_snapshot_id"],
        "source_snapshot_hash": context_fields["source_snapshot_hash"],
        "snapshot_root": snapshot_root,
        "cohort_id": snapshot.cohort_id,
        "decision_date": decision_date,
        "declared_stock_codes": list(declared_codes),
        "condition_keys": list(keys),
        "combine_mode": row.combine_mode,
        "filter_state": filter_state,
        "sort_key": sort_key,
        "descending": descending,
    }
    query_sha = _sha256(query_payload)
    identity_payload = {
        "schema_version": DAILY_MARKET_RESEARCH_BOOKMARK_SCHEMA,
        "stock_code": code,
        "source_snapshot_id": context_fields["source_snapshot_id"],
        "source_snapshot_hash": context_fields["source_snapshot_hash"],
        "decision_date": decision_date,
        "cohort_id": snapshot.cohort_id,
        "filter_state": filter_state,
        "query_sha256": query_sha,
    }
    bookmark_id = f"dmarket-{_sha256(identity_payload)}"
    body = _build_payload_body(bookmark_id, query_sha, context_fields)
    body.pop("payload_sha256", None)
    payload_sha = _sha256(body)
    return _from_payload_fields({**body, "payload_sha256": payload_sha})


def _rank_context_payload(context: ResearchStockContextDTO) -> dict[str, Any]:
    if context.rank_context is None:
        _fail("bookmark_rank_context_missing", "rank bookmark 缺少 typed rank context")
    payload = {key: getattr(context, key) for key in _V1_CONTEXT_KEYS}
    payload["rank_context"] = context.rank_context.to_dict()
    return payload


def _rank_query_payload(context: ResearchStockContextDTO) -> dict[str, Any]:
    rank_context = context.rank_context
    if rank_context is None:
        _fail("bookmark_rank_context_missing", "rank bookmark 缺少 typed rank context")
    return {
        "rank_context": rank_context.to_dict(),
        "daily_snapshot_root": context.daily_snapshot_root,
        "daily_snapshot_cohort_id": context.daily_snapshot_cohort_id,
        "daily_snapshot_condition_keys": context.daily_snapshot_condition_keys,
        "daily_snapshot_combine_mode": context.daily_snapshot_combine_mode,
    }


def create_original_stock_ranking_bookmark(
    snapshot: VerifiedDailyMarketSnapshot,
    ranking: Any,
    *,
    ranking_root: str | Path,
    stock_code: str,
    stock_name: str = "",
    source_context: ResearchStockContextDTO | None = None,
    filter_state: str | None = None,
    sort_key: str | None = None,
    descending: bool | None = None,
) -> OriginalStockRankingBookmark:
    """將已驗證 publisher row 與外層研究查詢保存為 rank bookmark v2。"""

    from app_module.original_stock_ranking import (
        research_context_for_original_stock_ranking,
    )

    previous_rank = source_context.rank_context if source_context is not None else None
    selected_filter = filter_state or (previous_rank.filter_state if previous_rank else "all")
    selected_sort = sort_key or (previous_rank.sort_key if previous_rank else "rank")
    selected_descending = (
        descending if descending is not None else (previous_rank.descending if previous_rank else False)
    )
    publisher_context = research_context_for_original_stock_ranking(
        snapshot,
        ranking,
        ranking_root=ranking_root,
        stock_code=stock_code,
        stock_name=stock_name,
        inherited_context=source_context,
        filter_state=selected_filter,
        sort_key=selected_sort,
        descending=selected_descending,
    )
    rank_context = publisher_context.rank_context
    if rank_context is None:
        _fail("bookmark_rank_context_missing", "已驗證排名未建立 typed rank context")
    if previous_rank is not None and (
        previous_rank.rank_snapshot_id != rank_context.rank_snapshot_id
        or previous_rank.source_hash != rank_context.source_hash
        or previous_rank.selected_stock_code != rank_context.selected_stock_code
        or previous_rank.selected_rank != rank_context.selected_rank
    ):
        _fail("bookmark_rank_context_mismatch", "來源 context 與 pinned ranking identity/selected row 不一致")
    if source_context is not None:
        if (
            source_context.daily_snapshot_root
            and str(Path(source_context.daily_snapshot_root).expanduser().resolve()) != rank_context.snapshot_root
        ):
            _fail("bookmark_snapshot_root_mismatch", "外層每日查詢 root 與 pinned parent snapshot 不一致")
        if (
            source_context.daily_snapshot_cohort_id
            and source_context.daily_snapshot_cohort_id != rank_context.parent_cohort_id
        ):
            _fail("bookmark_snapshot_cohort_mismatch", "外層每日查詢 cohort 與 pinned parent snapshot 不一致")
    context = ResearchStockContextDTO(
        stock_code=publisher_context.stock_code,
        stock_name=publisher_context.stock_name,
        decision_date=publisher_context.decision_date,
        data_date=publisher_context.data_date,
        result_id="",
        source_snapshot_id=publisher_context.source_snapshot_id,
        source_snapshot_hash=publisher_context.source_snapshot_hash,
        source_kind=ORIGINAL_STOCK_RANKING_BOOKMARK_SOURCE,
        source_label="原始強弱排名收藏",
        source_workspace="watchlist",
        source_id="pending",
        daily_snapshot_root=publisher_context.daily_snapshot_root,
        daily_snapshot_cohort_id=publisher_context.daily_snapshot_cohort_id,
        daily_snapshot_condition_keys=publisher_context.daily_snapshot_condition_keys,
        daily_snapshot_combine_mode=publisher_context.daily_snapshot_combine_mode,
        rank_context=rank_context,
    )
    query_payload = _rank_query_payload(context)
    query_sha = _sha256(query_payload)
    identity_payload = {
        "schema_version": ORIGINAL_STOCK_RANKING_BOOKMARK_SCHEMA,
        "stock_code": context.stock_code,
        "source_hash": rank_context.source_hash,
        "rank_snapshot_id": rank_context.rank_snapshot_id,
        "period": rank_context.period,
        "direction": rank_context.direction,
        "filter_state": rank_context.filter_state,
        "sort_key": rank_context.sort_key,
        "descending": rank_context.descending,
        "daily_snapshot_condition_keys": context.daily_snapshot_condition_keys,
        "daily_snapshot_combine_mode": context.daily_snapshot_combine_mode,
        "query_sha256": query_sha,
    }
    bookmark_id = f"rank-{_sha256(identity_payload)}"
    context = ResearchStockContextDTO(
        stock_code=context.stock_code,
        stock_name=context.stock_name,
        decision_date=context.decision_date,
        data_date=context.data_date,
        result_id="",
        source_snapshot_id=context.source_snapshot_id,
        source_snapshot_hash=context.source_snapshot_hash,
        source_kind=ORIGINAL_STOCK_RANKING_BOOKMARK_SOURCE,
        source_label="原始強弱排名收藏",
        source_workspace="watchlist",
        source_id=bookmark_id,
        daily_snapshot_root=context.daily_snapshot_root,
        daily_snapshot_cohort_id=context.daily_snapshot_cohort_id,
        daily_snapshot_condition_keys=context.daily_snapshot_condition_keys,
        daily_snapshot_combine_mode=context.daily_snapshot_combine_mode,
        rank_context=rank_context,
    )
    context_payload = _rank_context_payload(context)
    provisional = OriginalStockRankingBookmark(
        bookmark_id=bookmark_id,
        stock_code=context.stock_code,
        stock_name=context.stock_name,
        context_json=_canonical_json(context_payload),
        _query_sha256=query_sha,
        _payload_sha256="",
    )
    body = provisional.to_dict()
    body.pop("payload_sha256", None)
    decoded = decode_daily_market_research_bookmark(
        {**body, "payload_sha256": _sha256(body)}
    )
    if not isinstance(decoded, OriginalStockRankingBookmark):
        _fail("bookmark_schema_mismatch", "rank bookmark factory 未產生 v2 收藏")
    return decoded


def create_original_stock_ranking_bookmark_from_context(
    context: ResearchStockContextDTO,
    *,
    db_path: str | Path,
    sort_key: str | None = None,
    descending: bool | None = None,
    filter_state: str | None = None,
) -> OriginalStockRankingBookmark:
    """從報表 context 的 pinned rank manifest 讀回原列後建立 bookmark。"""

    if not isinstance(context, ResearchStockContextDTO) or context.rank_context is None:
        _fail("bookmark_rank_context_missing", "收藏需要包含 typed rank context 的研究 context")
    from app_module.original_stock_ranking import load_original_stock_ranking_from_context

    snapshot, ranking = load_original_stock_ranking_from_context(
        context.rank_context,
        db_path=db_path,
    )
    return create_original_stock_ranking_bookmark(
        snapshot,
        ranking,
        ranking_root=context.rank_context.ranking_root,
        stock_code=context.stock_code,
        stock_name=context.stock_name,
        source_context=context,
        filter_state=filter_state,
        sort_key=sort_key,
        descending=descending,
    )


def decode_daily_market_research_bookmark(
    value: Mapping[str, Any] | Any,
) -> DailyMarketResearchBookmark | OriginalStockRankingBookmark:
    """嚴格解碼已保存的 payload，並跨版本保留收藏當時捕獲的方法契約。"""

    if not isinstance(value, Mapping):
        _fail("bookmark_payload_invalid", "研究收藏 payload 必須是 object")
    if value.get("schema_version") == ORIGINAL_STOCK_RANKING_BOOKMARK_SCHEMA:
        return _decode_original_stock_ranking_bookmark(value)
    payload = dict(value)
    if set(payload) != _PAYLOAD_KEYS:
        _fail("bookmark_schema_mismatch", "研究收藏欄位不符合固定 v1 schema")
    if payload.get("schema_version") != DAILY_MARKET_RESEARCH_BOOKMARK_SCHEMA:
        _fail("bookmark_schema_mismatch", "研究收藏 schema version 不支援")
    claimed_payload_hash = _require_sha256(payload.get("payload_sha256"), "payload_sha256")
    body = {key: value for key, value in payload.items() if key != "payload_sha256"}
    if _sha256(body) != claimed_payload_hash:
        _fail("bookmark_payload_hash_mismatch", "研究收藏 payload SHA-256 不符")

    contracts = payload.get("method_contracts")
    contract_hash = _require_sha256(payload.get("method_contracts_sha256"), "method_contracts_sha256")
    if not isinstance(contracts, Mapping):
        _fail("method_contract_invalid", "method_contracts 必須是 object")
    _validate_method_contracts(contracts, contract_hash)
    if payload.get("manifest_schema_version") != DAILY_MARKET_SNAPSHOT_MANIFEST_SCHEMA:
        _fail("bookmark_source_schema_mismatch", "研究收藏來源 manifest schema 不支援")

    source_snapshot_id = _require_sha256(payload.get("source_snapshot_id"), "source_snapshot_id")
    source_snapshot_hash = _require_sha256(payload.get("source_snapshot_hash"), "source_snapshot_hash")
    snapshot_identity = _require_sha256(payload.get("snapshot_identity_sha256"), "snapshot_identity_sha256")
    input_fingerprint = _require_sha256(payload.get("input_fingerprint_sha256"), "input_fingerprint_sha256")
    decision_date = _normalize_required_date(payload.get("decision_date"), "decision_date")
    data_date = _normalize_optional_date(payload.get("data_date"), "data_date")
    if data_date and data_date > decision_date:
        _fail("bookmark_date_invalid", "研究收藏 data_date 不可晚於 decision_date")
    root = _normalize_root(payload.get("snapshot_root"))
    code = _require_text(payload.get("stock_code"), "stock_code")
    name = _require_text(payload.get("stock_name"), "stock_name")
    cohort_id = _require_text(payload.get("cohort_id"), "cohort_id")
    declared = _normalize_stock_codes(payload.get("declared_stock_codes"), "declared_stock_codes")
    if code not in declared:
        _fail("bookmark_cohort_invalid", "研究收藏股票不在 declared cohort")
    keys = payload.get("condition_keys")
    if (
        not isinstance(keys, list)
        or not keys
        or any(not isinstance(key, str) or key not in _CONDITION_KEYS for key in keys)
        or len(keys) != len(set(keys))
    ):
        _fail("bookmark_query_invalid", "研究收藏 condition_keys 無效")
    if payload.get("combine_mode") not in {"AND", "OR"}:
        _fail("bookmark_query_invalid", "研究收藏 combine_mode 無效")
    filter_state = payload.get("filter_state")
    if filter_state not in {"all", "match", "no_match", "unknown"}:
        _fail("bookmark_query_invalid", "研究收藏 filter_state 無效")
    sort_key = payload.get("sort_key")
    if not isinstance(sort_key, str) or sort_key not in _SORT_KEYS:
        _fail("bookmark_query_invalid", "研究收藏 sort_key 無效")
    descending = payload.get("descending")
    if not isinstance(descending, bool):
        _fail("bookmark_query_invalid", "研究收藏 descending 必須是布林值")

    conditions = payload.get("conditions")
    if not isinstance(conditions, list) or len(conditions) != len(keys):
        _fail("bookmark_condition_invalid", "研究收藏 conditions 數量不符")
    for condition, key in zip(conditions, keys):
        _validate_condition_payload(condition, key, contracts, decision_date)
    combined_state = payload.get("combined_state")
    if combined_state not in {"match", "no_match", "unknown"}:
        _fail("bookmark_condition_invalid", "研究收藏 combined_state 無效")
    why = _normalize_text_sequence(payload.get("why"), "why")
    why_not = _normalize_text_sequence(payload.get("why_not"), "why_not")
    completeness = _require_text(payload.get("completeness"), "completeness")
    bookmark_id = _require_text(payload.get("bookmark_id"), "bookmark_id")
    query_sha = _require_sha256(payload.get("query_sha256"), "query_sha256")

    expected_query = {
        "source_snapshot_id": source_snapshot_id,
        "source_snapshot_hash": source_snapshot_hash,
        "snapshot_root": root,
        "cohort_id": cohort_id,
        "decision_date": decision_date,
        "declared_stock_codes": list(declared),
        "condition_keys": list(keys),
        "combine_mode": payload["combine_mode"],
        "filter_state": filter_state,
        "sort_key": sort_key,
        "descending": descending,
    }
    if _sha256(expected_query) != query_sha:
        _fail("bookmark_query_hash_mismatch", "研究收藏 query SHA-256 不符")
    expected_identity = {
        "schema_version": DAILY_MARKET_RESEARCH_BOOKMARK_SCHEMA,
        "stock_code": code,
        "source_snapshot_id": source_snapshot_id,
        "source_snapshot_hash": source_snapshot_hash,
        "decision_date": decision_date,
        "cohort_id": cohort_id,
        "filter_state": filter_state,
        "query_sha256": query_sha,
    }
    if bookmark_id != f"dmarket-{_sha256(expected_identity)}":
        _fail("bookmark_identity_mismatch", "研究收藏 bookmark_id 與來源/query identity 不符")

    context = payload.get("context")
    if not isinstance(context, Mapping):
        _fail("bookmark_context_invalid", "研究收藏缺少 typed context")
    expected_context = _v1_context_payload(
        ResearchStockContextDTO(
            stock_code=code,
            stock_name=name,
            decision_date=decision_date,
            data_date=data_date,
            result_id="",
            source_snapshot_id=source_snapshot_id,
            source_snapshot_hash=source_snapshot_hash,
            source_kind=DAILY_MARKET_RESEARCH_SOURCE_KIND,
            source_label="每日市場研究收藏",
            source_workspace="watchlist",
            source_id=bookmark_id,
            daily_snapshot_root=root,
            daily_snapshot_cohort_id=cohort_id,
            daily_snapshot_condition_keys=",".join(keys),
            daily_snapshot_combine_mode=payload["combine_mode"],
        )
    )
    if dict(context) != expected_context:
        _fail("bookmark_context_invalid", "研究收藏 context identity 不一致或帶有推薦身份")
    if (
        payload.get("source") != DAILY_MARKET_RESEARCH_BOOKMARK_SOURCE
        or payload.get("source_workspace") != "watchlist"
        or payload.get("source_id") != bookmark_id
        or payload.get("result_id") != ""
    ):
        _fail("bookmark_context_invalid", "研究收藏不可帶入 manual 或 Advice 身份")

    result = DailyMarketResearchBookmark(
        bookmark_id=bookmark_id,
        stock_code=code,
        stock_name=name,
        source_snapshot_id=source_snapshot_id,
        source_snapshot_hash=source_snapshot_hash,
        snapshot_identity_sha256=snapshot_identity,
        input_fingerprint_sha256=input_fingerprint,
        decision_date=decision_date,
        data_date=data_date,
        snapshot_root=root,
        cohort_id=cohort_id,
        declared_stock_codes=declared,
        condition_keys=tuple(keys),
        combine_mode=payload["combine_mode"],
        filter_state=filter_state,
        method_contracts_json=_canonical_json(contracts),
        method_contracts_sha256=contract_hash,
        conditions_json=_canonical_json(conditions),
        combined_state=combined_state,
        why=why,
        why_not=why_not,
        completeness=completeness,
        manifest_schema_version=str(payload["manifest_schema_version"]),
        sort_key=sort_key,
        descending=descending,
        _query_sha256=query_sha,
        _payload_sha256=claimed_payload_hash,
    )
    if result.to_dict() != payload:
        _fail("bookmark_payload_noncanonical", "研究收藏 payload 不是 canonical v1 表示")
    return result


def _decode_original_stock_ranking_bookmark(
    value: Mapping[str, Any],
) -> OriginalStockRankingBookmark:
    """嚴格驗證 rank v2 payload、完整 context 與 typed extension。"""

    payload = dict(value)
    if set(payload) != _RANK_PAYLOAD_KEYS:
        _fail("bookmark_schema_mismatch", "rank bookmark 欄位不符合固定 v2 schema")
    if payload.get("schema_version") != ORIGINAL_STOCK_RANKING_BOOKMARK_SCHEMA:
        _fail("bookmark_schema_mismatch", "rank bookmark schema version 不支援")
    claimed_payload_hash = _require_sha256(payload.get("payload_sha256"), "payload_sha256")
    body = {key: item for key, item in payload.items() if key != "payload_sha256"}
    if _sha256(body) != claimed_payload_hash:
        _fail("bookmark_payload_hash_mismatch", "rank bookmark payload SHA-256 不符")
    code = _require_text(payload.get("stock_code"), "stock_code")
    name = _require_text(payload.get("stock_name"), "stock_name")
    bookmark_id = _require_text(payload.get("bookmark_id"), "bookmark_id")
    query_sha = _require_sha256(payload.get("query_sha256"), "query_sha256")
    context_value = payload.get("context")
    if not isinstance(context_value, Mapping) or set(context_value) != _RANK_CONTEXT_KEYS:
        _fail("bookmark_context_invalid", "rank bookmark context 欄位不符合固定 schema")
    context_payload = dict(context_value)
    if any(type(context_payload.get(key)) is not str for key in _V1_CONTEXT_KEYS):
        _fail("bookmark_context_invalid", "rank bookmark context 欄位必須是文字")
    forbidden_context_identity = {
        "identity_status", "profile_id", "profile_version", "source_version",
        "mapping_source_id", "mapping_version", "mapping_observed_date", "ml_scope_mode",
    }
    if any(context_payload.get(key) != "" for key in forbidden_context_identity):
        _fail("bookmark_context_invalid", "rank bookmark 不可攜帶 Advice、ML 或 mapping 身份")
    try:
        context = ResearchStockContextDTO(**context_payload)
    except (TypeError, ValueError) as exc:
        raise DailyMarketResearchBookmarkError(
            "bookmark_context_invalid", "rank bookmark context 日期、股票或 typed rank extension 無效"
        ) from exc
    rank_context = context.rank_context
    if rank_context is None or _rank_context_payload(context) != context_payload:
        _fail("bookmark_context_invalid", "rank bookmark context 不是完整 canonical typed payload")
    if (
        context.stock_code != code
        or context.stock_name != name
        or context.decision_date != rank_context.decision_date
        or context.data_date != rank_context.latest_date
        or context.source_snapshot_id != rank_context.parent_snapshot_id
        or context.source_snapshot_hash != rank_context.parent_snapshot_hash
        or context.daily_snapshot_root != rank_context.snapshot_root
        or context.daily_snapshot_cohort_id != rank_context.parent_cohort_id
        or context.source_kind != ORIGINAL_STOCK_RANKING_BOOKMARK_SOURCE
        or context.source_label != "原始強弱排名收藏"
        or context.source_workspace != "watchlist"
        or context.result_id != ""
        or context.source_id != bookmark_id
    ):
        _fail("bookmark_context_invalid", "rank bookmark context source/date/selected stock 不一致")
    condition_keys = context.daily_snapshot_condition_keys.split(",") if context.daily_snapshot_condition_keys else []
    if (
        len(condition_keys) != len(set(condition_keys))
        or any(not key or key not in _CONDITION_KEYS for key in condition_keys)
        or (condition_keys and context.daily_snapshot_combine_mode not in {"AND", "OR"})
        or (not condition_keys and context.daily_snapshot_combine_mode)
    ):
        _fail("bookmark_query_invalid", "rank bookmark 未保留有效的外層 daily condition query")
    if _sha256(_rank_query_payload(context)) != query_sha:
        _fail("bookmark_query_hash_mismatch", "rank bookmark query SHA-256 不符")
    expected_identity = {
        "schema_version": ORIGINAL_STOCK_RANKING_BOOKMARK_SCHEMA,
        "stock_code": code,
        "source_hash": rank_context.source_hash,
        "rank_snapshot_id": rank_context.rank_snapshot_id,
        "period": rank_context.period,
        "direction": rank_context.direction,
        "filter_state": rank_context.filter_state,
        "sort_key": rank_context.sort_key,
        "descending": rank_context.descending,
        "daily_snapshot_condition_keys": context.daily_snapshot_condition_keys,
        "daily_snapshot_combine_mode": context.daily_snapshot_combine_mode,
        "query_sha256": query_sha,
    }
    if bookmark_id != f"rank-{_sha256(expected_identity)}":
        _fail("bookmark_identity_mismatch", "rank bookmark_id 與 publisher/query identity 不符")
    if (
        payload.get("source") != ORIGINAL_STOCK_RANKING_BOOKMARK_SOURCE
        or payload.get("source_workspace") != "watchlist"
        or payload.get("source_id") != bookmark_id
        or payload.get("result_id") != ""
    ):
        _fail("bookmark_context_invalid", "rank bookmark 不可帶入 manual 或 Advice identity")
    result = OriginalStockRankingBookmark(
        bookmark_id=bookmark_id,
        stock_code=code,
        stock_name=name,
        context_json=_canonical_json(context_payload),
        _query_sha256=query_sha,
        _payload_sha256=claimed_payload_hash,
    )
    if result.to_dict() != payload:
        _fail("bookmark_payload_noncanonical", "rank bookmark payload 不是 canonical v2 表示")
    return result


def _from_payload_fields(payload: Mapping[str, Any]) -> DailyMarketResearchBookmark:
    """由舊版 v1 factory 建立並收窄型別的已驗證 bookmark。"""

    decoded = decode_daily_market_research_bookmark(payload)
    if not isinstance(decoded, DailyMarketResearchBookmark):
        _fail("bookmark_schema_mismatch", "daily bookmark factory 未產生 v1 收藏")
    return decoded


def _build_payload_body(
    bookmark_id: str,
    query_sha: str,
    fields: Mapping[str, Any],
) -> dict[str, Any]:
    provisional = DailyMarketResearchBookmark(
        bookmark_id=bookmark_id,
        stock_code=str(fields["stock_code"]),
        stock_name=str(fields["stock_name"]),
        source_snapshot_id=str(fields["source_snapshot_id"]),
        source_snapshot_hash=str(fields["source_snapshot_hash"]),
        snapshot_identity_sha256=str(fields["snapshot_identity_sha256"]),
        input_fingerprint_sha256=str(fields["input_fingerprint_sha256"]),
        decision_date=str(fields["decision_date"]),
        data_date=str(fields["data_date"]),
        snapshot_root=str(fields["snapshot_root"]),
        cohort_id=str(fields["cohort_id"]),
        declared_stock_codes=tuple(fields["declared_stock_codes"]),
        condition_keys=tuple(fields["condition_keys"]),
        combine_mode=fields["combine_mode"],
        filter_state=fields["filter_state"],
        method_contracts_json=_canonical_json(fields["method_contracts"]),
        method_contracts_sha256=str(fields["method_contracts_sha256"]),
        conditions_json=_canonical_json(fields["conditions"]),
        combined_state=fields["combined_state"],
        why=tuple(fields["why"]),
        why_not=tuple(fields["why_not"]),
        completeness=str(fields["completeness"]),
        manifest_schema_version=str(fields["manifest_schema_version"]),
        sort_key=str(fields["sort_key"]),
        descending=fields["descending"],
        _query_sha256=query_sha,
        _payload_sha256="",
    )
    return provisional.to_dict()


def _validate_method_contracts(value: Any, claimed_sha256: str) -> None:
    if not isinstance(value, Mapping) or set(value) != _CONDITION_KEYS:
        _fail("method_contract_invalid", "收藏 method_contracts 必須包含固定兩個每日 close/MA 方法")
    if method_contracts_sha256(value) != claimed_sha256:
        _fail("method_contract_hash_mismatch", "捕獲的 method_contracts hash 不符")
    for key in _CONDITION_KEYS:
        item = value.get(key)
        if not isinstance(item, Mapping):
            _fail("method_contract_invalid", f"方法契約 {key} 必須是 object")
        if not all(isinstance(item.get(name), str) and item[name] for name in ("method_id", "family", "version")):
            _fail("method_contract_invalid", f"方法契約 {key} 缺少固定身份欄位")
        if not isinstance(item.get("parameters"), Mapping) or not isinstance(item.get("required_fields"), list):
            _fail("method_contract_invalid", f"方法契約 {key} 的 parameters/required_fields 格式無效")


def _verify_snapshot_root(
    snapshot: VerifiedDailyMarketSnapshot,
    snapshot_root: str,
    declared_codes: tuple[str, ...],
) -> None:
    """以既有唯讀 reader 將 row root 綁定到 pinned manifest/artifact。"""

    input_hashes = {
        code: str(payload.get("input_fingerprint_sha256") or "")
        for code, payload in snapshot.stock_snapshots.items()
        if isinstance(payload, Mapping)
    }
    try:
        readback = DailyMarketSnapshotRepository(snapshot_root).load_manifest(
            snapshot.manifest_sha256,
            snapshot.cohort_id,
            snapshot.decision_date,
            expected_stock_codes=declared_codes,
            expected_input_hashes=input_hashes,
        )
    except Exception as exc:
        raise DailyMarketResearchBookmarkError(
            "bookmark_snapshot_root_mismatch",
            "snapshot_root 無法以現有唯讀 reader 還原相同 manifest/artifact。",
        ) from exc
    if (
        readback.manifest_sha256 != snapshot.manifest_sha256
        or readback.manifest_identity_sha256 != snapshot.manifest_identity_sha256
        or readback.cohort_id != snapshot.cohort_id
        or readback.decision_date != snapshot.decision_date
        or dict(readback.manifest) != dict(snapshot.manifest)
        or dict(readback.stock_snapshots) != dict(snapshot.stock_snapshots)
    ):
        _fail(
            "bookmark_snapshot_root_mismatch",
            "snapshot_root 的 pinned manifest/artifact 與已驗證來源不一致。",
        )


def _validate_condition_contract(
    condition: DailyMarketResearchConditionResult,
    contracts: Mapping[str, Any],
    decision_date: str,
) -> None:
    contract = contracts.get(condition.key)
    if not isinstance(contract, Mapping):
        _fail("method_contract_invalid", f"畫面條件 {condition.key} 缺少捕獲方法契約")
    if (
        condition.method_id != contract.get("method_id")
        or condition.family != contract.get("family")
        or condition.version != contract.get("version")
        or dict(condition.parameters or {}) != dict(contract.get("parameters") or {})
        or condition.decision_date != decision_date
    ):
        _fail("method_contract_mismatch", f"畫面條件 {condition.key} 與捕獲方法契約不符")


def _validate_condition_payload(
    value: Any,
    key: str,
    contracts: Mapping[str, Any],
    decision_date: str,
) -> None:
    if not isinstance(value, Mapping) or value.get("key") != key:
        _fail("bookmark_condition_invalid", "研究收藏 condition key 與 payload 不符")
    contract = contracts.get(key)
    if not isinstance(contract, Mapping):
        _fail("method_contract_invalid", f"研究收藏條件 {key} 缺少捕獲方法契約")
    if (
        value.get("method_id") != contract.get("method_id")
        or value.get("family") != contract.get("family")
        or value.get("version") != contract.get("version")
        or value.get("parameters") != contract.get("parameters")
        or value.get("decision_date") != decision_date
    ):
        _fail("method_contract_mismatch", f"研究收藏條件 {key} 與捕獲方法/date 不符")
    if value.get("state") not in {"match", "no_match", "unknown"}:
        _fail("bookmark_condition_invalid", f"研究收藏條件 {key} state 無效")
    if value.get("relation") not in {"above", "below", "equal", "unknown"}:
        _fail("bookmark_condition_invalid", f"研究收藏條件 {key} relation 無效")
    if not isinstance(value.get("reason"), str):
        _fail("bookmark_condition_invalid", f"研究收藏條件 {key} reason 無效")


def _normalize_stock_codes(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        _fail("bookmark_cohort_invalid", f"{field_name} 必須是非空股票代號序列")
    codes = tuple(str(item).strip() for item in value)
    if any(not code for code in codes) or len(codes) != len(set(codes)):
        _fail("bookmark_cohort_invalid", f"{field_name} 含空值或重複股票代號")
    return codes


def _normalize_root(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("bookmark_source_root_invalid", "snapshot_root 必須是非空路徑")
    return str(Path(value).expanduser().resolve())


def _normalize_required_date(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        _fail("bookmark_date_invalid", f"{field_name} 必須是 ISO 日期")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _fail("bookmark_date_invalid", f"{field_name} 必須是 ISO 日期")
    if parsed.isoformat() != value:
        _fail("bookmark_date_invalid", f"{field_name} 必須使用 canonical ISO 日期")
    return value


def _normalize_optional_date(value: Any, field_name: str) -> str:
    if value in (None, ""):
        return ""
    return _normalize_required_date(value, field_name)


def _normalize_text_sequence(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        _fail("bookmark_payload_invalid", f"{field_name} 必須是文字陣列")
    return tuple(value)


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("bookmark_payload_invalid", f"{field_name} 必須是非空文字")
    return value.strip()


def _require_sha256(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        _fail("bookmark_hash_invalid", f"{field_name} 必須是 64 位小寫 SHA-256")
    return value


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise DailyMarketResearchBookmarkError("bookmark_payload_invalid", "研究收藏包含非 JSON 欄位") from exc


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _fail(code: str, message: str) -> NoReturn:
    raise DailyMarketResearchBookmarkError(code, message)


def _v1_context_payload(context: ResearchStockContextDTO) -> dict[str, Any]:
    """保留 v1 原始 context 欄位投影，避免新增 DTO default 改寫舊 hash。"""

    values = asdict(context)
    return {key: values[key] for key in _V1_CONTEXT_KEYS}
