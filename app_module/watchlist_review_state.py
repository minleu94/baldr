"""原 Watchlist payload 的私人查看狀態；不改研究或推薦證據。"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from typing import Any, Literal, Mapping
from app_module.dtos.decision_continuity_dtos import DecisionIdentity

REVIEW_EXTENSION = "baldr_watchlist_review"
REVIEW_SCHEMA = "baldr.watchlist-review.v1"
ReviewState = Literal["pending", "confirmed", "deferred"]


class WatchlistReviewStateError(ValueError):
    """來源、版本、狀態或 writer 不符時停止。"""


@dataclass(frozen=True, slots=True)
class WatchlistReviewSourceIdentity:
    stock_code: str
    item_sha256: str


@dataclass(frozen=True, slots=True)
class WatchlistReviewState:
    source_identity: WatchlistReviewSourceIdentity
    reason: str
    state: ReviewState
    revision: int | None
    writable: bool


@dataclass(frozen=True, slots=True)
class WatchlistSavedChange:
    status: Literal["changed", "unchanged", "unknown"]
    before_revision: int | None
    after_revision: int | None
    fields: tuple[str, ...] = ()
    message: str = "沒有可核對的兩份同來源／帳戶保存快照。"


def review_source_identity(item: Mapping[str, Any]) -> WatchlistReviewSourceIdentity:
    """全部原 item 欄位綁來源；只有私人可編輯的兩欄排除。"""
    code = item.get("stock_code", item.get("證券代號"))
    if type(code) is not str or not code.strip():
        raise WatchlistReviewStateError("review_stock_identity_missing")
    immutable = {key: value for key, value in item.items()
                 if key not in {"notes", REVIEW_EXTENSION, "stock_name", "tags"}}
    # 原 service 會補 typed defaults；來源身份按同一 DTO 語義核對，不回寫 raw。
    raw_identity = item.get("decision_identity")
    identity = deepcopy(dict(raw_identity)) if isinstance(raw_identity, Mapping) else {}
    identity.update(DecisionIdentity.from_mapping(item, default_stock_code=code.strip()).to_dict())
    immutable.update(stock_code=code.strip(), source=item.get("source", "manual"),
                     source_id=item.get("source_id", ""), decision_identity=identity)
    raw = json.dumps(immutable, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return WatchlistReviewSourceIdentity(code.strip(), hashlib.sha256(raw.encode("utf-8")).hexdigest())


def read_review_state(item: Mapping[str, Any], *, revision: int | None, writable: bool) -> WatchlistReviewState:
    identity = review_source_identity(item)
    reason = item.get("notes", "")
    if type(reason) is not str:
        raise WatchlistReviewStateError("review_reason_invalid")
    extension = item.get(REVIEW_EXTENSION)
    state: ReviewState = "pending"
    if extension is not None:
        if (not isinstance(extension, Mapping) or extension.get("schema_version") != REVIEW_SCHEMA
                or extension.get("state") not in {"pending", "confirmed", "deferred"}
                or extension.get("source_identity_sha256") != identity.item_sha256):
            raise WatchlistReviewStateError("review_extension_identity_or_schema_mismatch")
        state = extension["state"]
    return WatchlistReviewState(identity, reason, state, revision, writable)


def with_review_state(item: Mapping[str, Any], reason: str, state: ReviewState) -> dict[str, Any]:
    if type(reason) is not str or len(reason) > 4096 or "\x00" in reason:
        raise WatchlistReviewStateError("review_reason_invalid")
    if state not in {"pending", "confirmed", "deferred"}:
        raise WatchlistReviewStateError("review_state_invalid")
    # 先核對既有 extension，不用一次私人操作覆寫未知 schema／錯身份。
    current = read_review_state(item, revision=None, writable=False)
    result = deepcopy(dict(item))
    extension = deepcopy(dict(result.get(REVIEW_EXTENSION) or {}))
    extension.update(schema_version=REVIEW_SCHEMA, state=state,
                     source_identity_sha256=current.source_identity.item_sha256)
    result["notes"] = reason
    result[REVIEW_EXTENSION] = extension
    return result


def compare_saved_items(before: Mapping[str, Any], after: Mapping[str, Any], *,
                        before_revision: int, after_revision: int) -> WatchlistSavedChange:
    """只比較呼叫端從原 repository 核驗的兩份保存 item，不讀行情。"""
    keys = ("stock_code", "source", "source_id", "account_id")
    if (before_revision >= after_revision or any(type(before.get(key)) is not str
            or not before[key].strip() or before[key] != after.get(key) for key in keys)):
        return WatchlistSavedChange("unknown", before_revision, after_revision)
    prior = read_review_state(before, revision=before_revision, writable=False)
    current = read_review_state(after, revision=after_revision, writable=False)
    fields = []
    if prior.reason != current.reason:
        fields.append("收藏理由")
    if prior.state != current.state:
        fields.append("查看狀態")
    immutable_changed = review_source_identity(before) != review_source_identity(after)
    if immutable_changed:
        fields.append("原保存來源欄位")
    return WatchlistSavedChange(
        "changed" if fields else "unchanged", before_revision, after_revision, tuple(fields),
        "已保存差異：" + ("、".join(fields) if fields else "沒有差異") + "；非今日行情變化。",
    )
