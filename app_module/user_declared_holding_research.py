"""使用者聲明持倉的研究專用 domain、保存與 read model。

這個模組刻意與 Paper／正式 Portfolio fill lane 分離。使用者輸入的是
「我目前宣稱持有」的研究上下文，不是券商成交、verified entry 或 observed
slippage。保存採 append-only JSONL，讓修訂與封存仍可追溯，且不另建 decision DB。

研究評估只消費呼叫者傳入的 point-in-time market／condition observation。若來源
缺漏、過期、未帶 source trace 或落在評估日期之後，read model 會維持
``WAIT_CONFIRMATION``／unknown，不會為了產生正向建議而補造資料或機率。
"""

from __future__ import annotations

from contextlib import closing, contextmanager
import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import inspect
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Callable, Iterator, Mapping, Sequence
from uuid import uuid4
from zoneinfo import ZoneInfo

from app_module.dtos.portfolio_dtos import PositionDTO


if os.name == "nt":
    import msvcrt

    _fcntl: Any = None
else:  # pragma: no cover - 僅供 POSIX 開發環境使用
    import fcntl

    _fcntl = fcntl


SCHEMA_VERSION = "user-declared-holding-research.v1"
RECORD_TYPE = "user_declared_holding_revision"

SOURCE_STATUS_USER_DECLARED = "user_declared"
ENTRY_LINEAGE_UNPROVEN = "unproven"
FILL_VERIFICATION_NOT_PROVIDED = "not_provided"

RESEARCH_ACTION_HOLD = "HOLD"
RESEARCH_ACTION_REDUCE = "REDUCE_CANDIDATE"
RESEARCH_ACTION_EXIT = "EXIT_CANDIDATE"
RESEARCH_ACTION_WAIT = "WAIT_CONFIRMATION"
_POSITIVE_RESEARCH_ACTIONS = frozenset(
    {RESEARCH_ACTION_HOLD, RESEARCH_ACTION_REDUCE, RESEARCH_ACTION_EXIT}
)
_ALLOWED_REVISION_ACTIONS = frozenset({"created", "revised", "archived"})
_ALLOWED_SOURCE_QUALITIES = frozenset(
    {"observed", "verified", "research", "available", "ready", "passed"}
)
_SHA256_RE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
_TAIPEI_TIMEZONE = ZoneInfo("Asia/Taipei")
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,19}$")
_MAX_NOTES_LENGTH = 4000
_MAX_THESIS_LENGTH = 8000


class UserDeclaredHoldingError(ValueError):
    """使用者聲明持倉的輸入或研究契約錯誤。"""


class UserDeclaredHoldingConflictError(UserDeclaredHoldingError):
    """寫入與既有 exact identity、revision 或 active stock scope 衝突。"""


class UserDeclaredHoldingStorageError(RuntimeError):
    """append-only 保存串流無法安全投影。"""


def _canonical_json(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise UserDeclaredHoldingStorageError("聲明持倉事件無法正規化") from exc


def _sha256_mapping(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, datetime):
        return _normalise_datetime(value).isoformat()
    if isinstance(value, float):
        # legacy DTO／monitor details 可能在呈現邊界帶回 float；hash 之前
        # 明確轉成有限 Decimal 文字，避免二進位 float 進入研究核心或
        # 造成同一 snapshot 因序列化器不同而得到不同 fingerprint。
        if not math.isfinite(value):
            raise UserDeclaredHoldingStorageError("研究 source details 含非有限數字")
        return format(Decimal(str(value)), "f")
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _normalise_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _datetime_text(value: datetime) -> str:
    return _normalise_datetime(value).isoformat()


def _parse_datetime(value: object, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise UserDeclaredHoldingError(f"{field_name} 必須包含時區")
        return value.astimezone(timezone.utc)
    if not isinstance(value, str) or not value.strip():
        raise UserDeclaredHoldingError(f"{field_name} 必須是帶時區的 ISO 時間")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise UserDeclaredHoldingError(f"{field_name} 不是有效 ISO 時間") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise UserDeclaredHoldingError(f"{field_name} 必須包含時區")
    return parsed.astimezone(timezone.utc)


def _parse_date(value: object, *, field_name: str) -> date:
    if isinstance(value, datetime):
        raise UserDeclaredHoldingError(f"{field_name} 必須是交易日，不接受 datetime")
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        raise UserDeclaredHoldingError(f"{field_name} 必須是 YYYY-MM-DD")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise UserDeclaredHoldingError(f"{field_name} 不是有效 YYYY-MM-DD") from exc


def _decimal(value: object, *, field_name: str, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise UserDeclaredHoldingError(f"{field_name} 必須使用 Decimal、整數或十進位文字，不接受 float")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, str):
        try:
            result = Decimal(value.strip())
        except (InvalidOperation, ValueError) as exc:
            raise UserDeclaredHoldingError(f"{field_name} 不是有效 Decimal") from exc
    else:
        raise UserDeclaredHoldingError(f"{field_name} 必須使用 Decimal、整數或十進位文字")
    if not result.is_finite():
        raise UserDeclaredHoldingError(f"{field_name} 不得是無限大或 NaN")
    if positive and result <= 0:
        raise UserDeclaredHoldingError(f"{field_name} 必須大於 0")
    return result


def _quantity(value: object, *, field_name: str = "quantity") -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise UserDeclaredHoldingError(f"{field_name} 必須是整數股數")
    if value <= 0:
        raise UserDeclaredHoldingError(f"{field_name} 必須大於 0")
    return value


def _text(value: object, *, field_name: str, max_length: int, required: bool = False) -> str:
    if not isinstance(value, str):
        raise UserDeclaredHoldingError(f"{field_name} 必須是文字")
    result = value.strip()
    if required and not result:
        raise UserDeclaredHoldingError(f"{field_name} 不得為空白")
    if len(result) > max_length:
        raise UserDeclaredHoldingError(f"{field_name} 超過 {max_length} 字限制")
    if "\x00" in result:
        raise UserDeclaredHoldingError(f"{field_name} 不得包含 NUL 字元")
    return result


def _scope(value: object, *, field_name: str = "portfolio_id") -> str:
    return _text(value, field_name=field_name, max_length=120, required=True)


def _stock_code(value: object) -> str:
    code = _text(value, field_name="stock_code", max_length=20, required=True).upper()
    if not _STOCK_CODE_RE.fullmatch(code):
        raise UserDeclaredHoldingError("stock_code 僅可包含英數、句點、底線或連字號")
    return code


def _invoke_with_optional_cancel(
    callback: Callable[..., Any],
    args: tuple[Any, ...],
    cancel_callback: Callable[[], bool] | None,
) -> Any:
    """只對明確支援的 source 傳入合作式取消 callback。"""

    if cancel_callback is None:
        return callback(*args)
    try:
        parameters = inspect.signature(callback).parameters.values()
        supports = "cancel_callback" in {
            parameter.name for parameter in parameters
        } or any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters)
    except (TypeError, ValueError):
        supports = False
    if supports:
        return callback(*args, cancel_callback=cancel_callback)
    return callback(*args)


def _stable_source_trace(holding_id: str, revision_id: str) -> tuple[str, ...]:
    return (
        f"user_declared_holding:{holding_id}",
        f"user_declared_revision:{revision_id}",
    )


def _source_trace_item(
    source_kind: str,
    source_id: str,
    source_snapshot_hash: str,
    as_of_date: date | None,
) -> str:
    date_text = as_of_date.isoformat() if as_of_date is not None else "unknown-date"
    hash_text = source_snapshot_hash or "hash-missing"
    return f"{source_kind}:{source_id or 'source-missing'}@{date_text}#{hash_text}"


@contextmanager
def _interprocess_lock(path: Path, *, timeout_seconds: float = 10.0) -> Iterator[None]:
    """以 sibling lock file 保護 JSONL 的讀取、投影與 append。"""

    lock_path = path.with_name(f".{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+b")
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:  # pragma: no cover - 僅供 POSIX 開發環境使用
                    _fcntl.flock(handle.fileno(), _fcntl.LOCK_EX | _fcntl.LOCK_NB)
                break
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"user_declared JSONL lock timeout: {path}")
                time.sleep(0.05)
        try:
            yield
        finally:
            try:
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:  # pragma: no cover - 僅供 POSIX 開發環境使用
                    _fcntl.flock(handle.fileno(), _fcntl.LOCK_UN)
            finally:
                handle.close()
    except Exception:
        handle.close()
        raise


def _raise_if_cancelled(cancel_callback: Callable[[], bool] | None) -> None:
    if callable(cancel_callback) and cancel_callback():
        raise RuntimeError("user_declared research refresh cancelled")


def _read_jsonl_unlocked(
    path: Path,
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            _raise_if_cancelled(cancel_callback)
            stripped = line.strip()
            if not stripped:
                continue
            try:
                raw = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise UserDeclaredHoldingStorageError(
                    f"聲明持倉 JSONL 第 {line_number} 行無法解析"
                ) from exc
            if not isinstance(raw, dict):
                raise UserDeclaredHoldingStorageError(
                    f"聲明持倉 JSONL 第 {line_number} 行不是 object"
                )
            records.append(raw)
    return records


def _event_payload(event: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        raise UserDeclaredHoldingStorageError("聲明持倉事件缺少 payload")
    return payload


def _event_canonical(event: Mapping[str, Any]) -> str:
    return _canonical_json(_json_safe(event))


def _event_identity(event: Mapping[str, Any]) -> tuple[str, str, str]:
    try:
        return (
            str(event["revision_id"]),
            str(event["request_id"]),
            str(event["command_fingerprint"]),
        )
    except KeyError as exc:
        raise UserDeclaredHoldingStorageError("聲明持倉事件缺少 identity 欄位") from exc


def _validate_event_shape(event: Mapping[str, Any]) -> None:
    if event.get("schema_version") != SCHEMA_VERSION or event.get("record_type") != RECORD_TYPE:
        raise UserDeclaredHoldingStorageError("聲明持倉事件 schema 不受支援")
    action = str(event.get("action", ""))
    if action not in _ALLOWED_REVISION_ACTIONS:
        raise UserDeclaredHoldingStorageError("聲明持倉事件 action 不受支援")
    revision_number = event.get("revision_number")
    if isinstance(revision_number, bool) or not isinstance(revision_number, int) or revision_number <= 0:
        raise UserDeclaredHoldingStorageError("聲明持倉 revision_number 無效")
    holding_id = _text(event.get("holding_id"), field_name="holding_id", max_length=120, required=True)
    _scope(event.get("portfolio_id"))
    _stock_code(event.get("stock_code"))
    _text(event.get("revision_id"), field_name="revision_id", max_length=160, required=True)
    _text(event.get("request_id"), field_name="request_id", max_length=200, required=True)
    fingerprint = str(event.get("command_fingerprint", ""))
    if not fingerprint.startswith("sha256:") or len(fingerprint) != 71:
        raise UserDeclaredHoldingStorageError("聲明持倉 command_fingerprint 無效")
    previous_revision_id = event.get("previous_revision_id", "")
    if not isinstance(previous_revision_id, str):
        raise UserDeclaredHoldingStorageError("聲明持倉 previous_revision_id 無效")
    created_at = _parse_datetime(event.get("created_at"), field_name="created_at")
    del created_at
    payload = _event_payload(event)
    payload_holding_id = _text(
        payload.get("holding_id"), field_name="payload.holding_id", max_length=120, required=True
    )
    if payload_holding_id != holding_id:
        raise UserDeclaredHoldingStorageError("聲明持倉 identity 與 payload 不一致")
    if _scope(payload.get("portfolio_id")) != str(event["portfolio_id"]):
        raise UserDeclaredHoldingStorageError("聲明持倉 portfolio scope 不一致")
    if _stock_code(payload.get("stock_code")) != str(event["stock_code"]):
        raise UserDeclaredHoldingStorageError("聲明持倉 stock scope 不一致")
    _quantity(payload.get("quantity"))
    _decimal(payload.get("declared_cost"), field_name="declared_cost", positive=True)
    _parse_date(payload.get("declared_date"), field_name="declared_date")
    _text(payload.get("notes", ""), field_name="notes", max_length=_MAX_NOTES_LENGTH)
    _text(payload.get("thesis", ""), field_name="thesis", max_length=_MAX_THESIS_LENGTH)
    if payload.get("source_status") != SOURCE_STATUS_USER_DECLARED:
        raise UserDeclaredHoldingStorageError("聲明持倉 source_status 被改寫")
    if payload.get("entry_lineage_status") != ENTRY_LINEAGE_UNPROVEN:
        raise UserDeclaredHoldingStorageError("聲明持倉 entry_lineage_status 被改寫")
    if payload.get("fill_verification") != FILL_VERIFICATION_NOT_PROVIDED:
        raise UserDeclaredHoldingStorageError("聲明持倉 fill_verification 被改寫")
    if payload.get("research_only") is not True:
        raise UserDeclaredHoldingStorageError("聲明持倉必須是 research_only")
    if payload.get("archived") is not (action == "archived"):
        raise UserDeclaredHoldingStorageError("聲明持倉 archived 狀態與 action 不一致")
    _parse_datetime(payload.get("created_at"), field_name="payload.created_at")
    _parse_datetime(payload.get("updated_at"), field_name="payload.updated_at")
    archived_at = payload.get("archived_at")
    if archived_at is not None:
        _parse_datetime(archived_at, field_name="payload.archived_at")


def _project_heads(
    records: Sequence[Mapping[str, Any]],
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> dict[str, Mapping[str, Any]]:
    heads: dict[str, Mapping[str, Any]] = {}
    seen_revision_ids: dict[str, str] = {}
    seen_request_ids: dict[str, str] = {}
    for index, event in enumerate(records):
        _raise_if_cancelled(cancel_callback)
        try:
            _validate_event_shape(event)
            revision_id, request_id, fingerprint = _event_identity(event)
        except (TypeError, UserDeclaredHoldingError, UserDeclaredHoldingStorageError) as exc:
            raise UserDeclaredHoldingStorageError(f"第 {index + 1} 筆聲明持倉事件無效") from exc
        canonical = _event_canonical(event)
        for key, seen, label in (
            (revision_id, seen_revision_ids, "revision_id"),
            (request_id, seen_request_ids, "request_id"),
        ):
            if key in seen:
                raise UserDeclaredHoldingStorageError(f"聲明持倉 {label} 重複")
            seen[key] = canonical

        holding_id = str(event["holding_id"])
        action = str(event["action"])
        previous = str(event.get("previous_revision_id", ""))
        revision_number = int(event["revision_number"])
        previous_head = heads.get(holding_id)
        if action == "created":
            if previous_head is not None or revision_number != 1 or previous:
                raise UserDeclaredHoldingStorageError("聲明持倉 created revision chain 無效")
        else:
            if previous_head is None:
                raise UserDeclaredHoldingStorageError("聲明持倉 revision 找不到前一版")
            if bool(_event_payload(previous_head).get("archived")):
                raise UserDeclaredHoldingStorageError("封存後不得再追加聲明持倉 revision")
            if revision_number != int(previous_head["revision_number"]) + 1:
                raise UserDeclaredHoldingStorageError("聲明持倉 revision_number 不連續")
            if previous != str(previous_head["revision_id"]):
                raise UserDeclaredHoldingStorageError("聲明持倉 previous_revision_id 不一致")
            if str(event["portfolio_id"]) != str(previous_head["portfolio_id"]):
                raise UserDeclaredHoldingStorageError("聲明持倉不可跨 portfolio scope 修訂")
            if str(event["stock_code"]) != str(previous_head["stock_code"]):
                raise UserDeclaredHoldingStorageError("聲明持倉 stock_code 不可在 revision 變更")
        heads[holding_id] = event

    active_keys: dict[tuple[str, str], str] = {}
    for holding_id, head_event in heads.items():
        _raise_if_cancelled(cancel_callback)
        if bool(_event_payload(head_event).get("archived")):
            continue
        active_key = (str(head_event["portfolio_id"]), str(head_event["stock_code"]))
        prior = active_keys.get(active_key)
        if prior is not None and prior != holding_id:
            raise UserDeclaredHoldingStorageError("同一 portfolio 的同股 active holding 發生歧義")
        active_keys[active_key] = holding_id
    return heads


@dataclass(frozen=True, slots=True)
class UserDeclaredHoldingDraft:
    """新增或修訂所需的使用者輸入；成本欄位不可用 float。"""

    stock_code: str
    quantity: int
    declared_cost: Decimal | int | str
    declared_date: date | str
    notes: str = ""
    thesis: str = ""
    portfolio_id: str = "default"


@dataclass(frozen=True, slots=True)
class UserDeclaredHoldingRecord:
    """目前某一 exact holding identity 的聲明 snapshot。"""

    holding_id: str
    portfolio_id: str
    stock_code: str
    quantity: int
    declared_cost: Decimal
    declared_date: date
    notes: str
    thesis: str
    revision_id: str
    revision_number: int
    action: str
    created_at: str
    updated_at: str
    archived: bool
    archived_at: str | None
    archive_reason: str
    source_status: str = SOURCE_STATUS_USER_DECLARED
    entry_lineage_status: str = ENTRY_LINEAGE_UNPROVEN
    fill_verification: str = FILL_VERIFICATION_NOT_PROVIDED
    research_only: bool = True

    @property
    def declared_cost_total(self) -> Decimal:
        return self.declared_cost * Decimal(self.quantity)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "holding_id": self.holding_id,
            "portfolio_id": self.portfolio_id,
            "stock_code": self.stock_code,
            "quantity": self.quantity,
            "declared_cost": format(self.declared_cost, "f"),
            "declared_date": self.declared_date.isoformat(),
            "notes": self.notes,
            "thesis": self.thesis,
            "revision_id": self.revision_id,
            "revision_number": self.revision_number,
            "action": self.action,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "archived": self.archived,
            "archived_at": self.archived_at,
            "archive_reason": self.archive_reason,
            "source_status": self.source_status,
            "entry_lineage_status": self.entry_lineage_status,
            "fill_verification": self.fill_verification,
            "research_only": self.research_only,
        }


@dataclass(frozen=True, slots=True)
class UserDeclaredHoldingHistoryItem:
    revision_id: str
    holding_id: str
    action: str
    revision_number: int
    previous_revision_id: str
    request_id: str
    command_fingerprint: str
    created_at: str
    snapshot: UserDeclaredHoldingRecord


@dataclass(frozen=True, slots=True)
class MarketObservation:
    """由既有市場資料 caller 提供的 PIT 現價 observation。"""

    stock_code: str
    price: Decimal | int | str
    as_of_date: date | str
    source_id: str
    source_snapshot_hash: str
    available_at: datetime | str | None = None
    quality: str = "observed"
    # True 代表來源本身具備可稽核的 capture／availability custody；
    # 檔案 mtime 等本機觀測只能維持 False。
    availability_custody: bool = False


@dataclass(frozen=True, slots=True)
class ConditionObservation:
    """由既有 condition／Advice caller 提供的 PIT 研究建議 observation。"""

    stock_code: str
    suggested_action: str
    as_of_date: date | str
    source_id: str
    source_snapshot_hash: str
    reasons: tuple[str, ...] = ()
    summary: str = ""
    available_at: datetime | str | None = None
    quality: str = "observed"
    availability_custody: bool = False


@dataclass(frozen=True, slots=True)
class ConditionRuleContext:
    """由既有 Advice／評分／condition producer 提供的可追溯規則上下文。"""

    source_id: str
    source_snapshot_hash: str
    as_of_date: date | str
    available_at: datetime | str | None
    source_summary: Mapping[str, Any]
    current_regime: str = ""
    current_total_score: Decimal | int | str | None = None
    reasons: tuple[str, ...] = ()
    quality: str = "observed"
    availability_custody: bool = False


class FilesystemDailyMarketObservationProvider:
    """以既有每日價格 CSV 建立唯讀、帶檔案 hash 的市場 observation。

    檔案修改時間只作為「本機看到此 snapshot 的時間」，不是官方公告時間；
    因此歷史 cutoff 若早於檔案 snapshot 時間，研究層會拒絕正向建議。
    """

    _STOCK_COLUMNS = ("證券代號", "股票代號", "stock_code", "symbol")
    _CLOSE_COLUMNS = ("收盤價", "close", "close_price", "Close")

    def __init__(
        self,
        daily_price_dir: Path | str,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ):
        self.daily_price_dir = Path(daily_price_dir)
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _file_date(path: Path) -> date | None:
        for pattern in ("%Y%m%d", "%Y-%m-%d"):
            try:
                return datetime.strptime(path.stem, pattern).date()
            except ValueError:
                continue
        return None

    @classmethod
    def _read_rows(cls, raw_bytes: bytes) -> list[dict[str, str]] | None:
        for encoding in ("utf-8-sig", "cp950"):
            try:
                text = raw_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue
            rows = list(csv.DictReader(io.StringIO(text)))
            if not rows:
                continue
            fieldnames = set(rows[0].keys())
            if any(column in fieldnames for column in cls._STOCK_COLUMNS) and any(
                column in fieldnames for column in cls._CLOSE_COLUMNS
            ):
                return rows
        return None

    @staticmethod
    def _row_value(row: Mapping[str, str], columns: Sequence[str]) -> str:
        for column in columns:
            value = row.get(column)
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""

    @staticmethod
    def _source_stock_code(value: object) -> str:
        text = str(value or "").strip()
        if text.endswith(".0") and text[:-2].isdigit():
            text = text[:-2]
        if text.isdigit():
            text = text.zfill(4)
        return _stock_code(text)

    def get_market_observation(
        self,
        stock_code: str,
        evaluation_date: date,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> MarketObservation | None:
        target = _stock_code(stock_code)
        _raise_if_cancelled(cancel_callback)
        if not self.daily_price_dir.is_dir():
            return None
        dated_files = sorted(
            (
                (path, self._file_date(path))
                for path in self.daily_price_dir.glob("*.csv")
            ),
            key=lambda item: (item[1] or date.min, item[0].name),
            reverse=True,
        )
        for path, file_date in dated_files:
            _raise_if_cancelled(cancel_callback)
            if file_date is None or file_date > evaluation_date:
                continue
            try:
                _raise_if_cancelled(cancel_callback)
                raw_bytes = path.read_bytes()
                rows = self._read_rows(raw_bytes)
                available_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            except (OSError, ValueError):
                continue
            if rows is None:
                continue
            matches: list[tuple[str, str]] = []
            for row in rows:
                _raise_if_cancelled(cancel_callback)
                try:
                    row_code = self._source_stock_code(self._row_value(row, self._STOCK_COLUMNS))
                except UserDeclaredHoldingError:
                    continue
                if row_code == target:
                    matches.append((row_code, self._row_value(row, self._CLOSE_COLUMNS)))
            if len(matches) != 1:
                continue
            try:
                _decimal(matches[0][1].replace(",", ""), field_name="market.price", positive=True)
            except UserDeclaredHoldingError:
                continue
            return MarketObservation(
                stock_code=target,
                price=matches[0][1].replace(",", ""),
                as_of_date=file_date,
                source_id=f"daily_price_file:{path.name}",
                source_snapshot_hash="sha256:" + hashlib.sha256(raw_bytes).hexdigest(),
                available_at=available_at,
                quality="observed",
                availability_custody=False,
            )
        return None

    def __call__(
        self,
        stock_code: str,
        evaluation_date: date,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> MarketObservation | None:
        return self.get_market_observation(
            stock_code,
            evaluation_date,
            cancel_callback=cancel_callback,
        )


class SavedRecommendationConditionContextProvider:
    """從既有已保存 RecommendationResultDTO 建立 condition 規則上下文。

    這個 provider 只讀 runs registry／JSON，不初始化 writer、不重新評分，
    也不把 user_declared holding 與正式成交 identity 綁在一起。它只在保存
    結果含有可比較的 regime／score 或明確停損停利欄位時提供 context；沒有
    規則時由下游維持 WAIT_CONFIRMATION。
    """

    def __init__(self, config_or_output_root: Any):
        raw_root = (
            getattr(config_or_output_root, "output_root", None)
            if not isinstance(config_or_output_root, (str, Path))
            else None
        )
        output_root = Path(raw_root if raw_root is not None else config_or_output_root)
        self.runs_dir = output_root / "recommendation" / "runs"

    @staticmethod
    def _nested_value(config: Mapping[str, Any], key: str) -> Any:
        candidates: list[Mapping[str, Any]] = [config]
        for candidate_key in ("params", "strategy_config", "risk"):
            candidate = config.get(candidate_key)
            if isinstance(candidate, Mapping):
                candidates.append(candidate)
        for candidate in candidates:
            value = candidate.get(key)
            if value is not None and value != "":
                return value
        return None

    @staticmethod
    def _result_date(result: Any) -> date | None:
        run_context = getattr(result, "run_context", {})
        run_context_mapping = run_context if isinstance(run_context, Mapping) else {}
        result_config = getattr(result, "config", {})
        result_config_mapping = result_config if isinstance(result_config, Mapping) else {}
        raw = str(
            run_context_mapping.get("as_of_date")
            or result_config_mapping.get("as_of_date")
            or ""
        ).strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None

    def _candidate_results(
        self,
        stock_code: str,
        evaluation_date: date,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> list[tuple[Any, Any, datetime]]:
        db_path = self.runs_dir / "recommendation_runs.db"
        _raise_if_cancelled(cancel_callback)
        if not db_path.is_file():
            return []
        try:
            with closing(
                sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
            ) as connection:
                connection.execute("PRAGMA query_only=ON")
                rows = connection.execute(
                    "SELECT data_path FROM runs ORDER BY created_at DESC, result_id"
                ).fetchall()
        except (OSError, sqlite3.Error):
            return []
        result_type: Any
        from app_module.recommendation.legacy_dtos import RecommendationResultDTO

        result_type = RecommendationResultDTO
        candidates: list[tuple[Any, Any, datetime]] = []
        runs_root = self.runs_dir.resolve()
        for (raw_path,) in rows:
            _raise_if_cancelled(cancel_callback)
            try:
                path = Path(str(raw_path)).resolve()
                if not path.is_relative_to(runs_root) or not path.is_file():
                    continue
                result = result_type.from_dict(json.loads(path.read_text(encoding="utf-8")))
                source_date = self._result_date(result)
                if source_date is None or source_date > evaluation_date:
                    continue
                matches = [
                    item
                    for item in (getattr(result, "recommendations", ()) or ())
                    if str(getattr(item, "stock_code", "")) == stock_code
                ]
                _raise_if_cancelled(cancel_callback)
                if len(matches) != 1:
                    continue
                available_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                candidates.append((result, matches[0], available_at))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
        candidates.sort(
            key=lambda item: (
                self._result_date(item[0]) or date.min,
                str(getattr(item[0], "created_at", "") or ""),
                str(getattr(item[0], "result_id", "") or ""),
            ),
            reverse=True,
        )
        return candidates

    def get_condition_context(
        self,
        record: UserDeclaredHoldingRecord,
        evaluation_date: date,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> ConditionRuleContext | None:
        candidates = self._candidate_results(
            record.stock_code,
            evaluation_date,
            cancel_callback=cancel_callback,
        )
        if not candidates:
            return None
        _raise_if_cancelled(cancel_callback)
        current = candidates[0]
        baseline_candidates = [
            item
            for item in candidates
            if (self._result_date(item[0]) or date.max) <= record.declared_date
        ]
        baseline = baseline_candidates[0] if baseline_candidates else None
        if baseline is None:
            return self._non_comparable_context(
                record,
                evaluation_date,
                current=current,
                reason="research_baseline_missing",
            )
        baseline_result, baseline_recommendation, baseline_available_at = baseline
        current_result, current_recommendation, current_available_at = current
        baseline_date = self._result_date(baseline_result)
        current_date = self._result_date(current_result)
        if baseline_date is None or current_date is None:
            return self._non_comparable_context(
                record,
                evaluation_date,
                current=current,
                reason="research_snapshot_date_missing",
                baseline=baseline,
            )
        if (
            str(getattr(baseline_result, "result_id", ""))
            == str(getattr(current_result, "result_id", ""))
            or current_available_at <= baseline_available_at
        ):
            return self._non_comparable_context(
                record,
                evaluation_date,
                current=current,
                reason="research_baseline_not_independent",
                baseline=baseline,
            )

        baseline_identity = self._analysis_identity(baseline_result)
        current_identity = self._analysis_identity(current_result)
        if baseline_identity is None or current_identity is None or baseline_identity != current_identity:
            return self._non_comparable_context(
                record,
                evaluation_date,
                current=current,
                reason="research_analysis_identity_mismatch",
                baseline=baseline,
            )

        baseline_context = dict(getattr(baseline_result, "run_context", {}) or {})
        baseline_config = dict(getattr(baseline_result, "config", {}) or {})
        current_context = dict(getattr(current_result, "run_context", {}) or {})
        current_config = dict(getattr(current_result, "config", {}) or {})
        baseline_regime = self._result_regime(baseline_result)
        current_regime = self._result_regime(current_result)
        source_summary: dict[str, Any] = {
            "baseline_result_id": str(getattr(baseline_result, "result_id", "") or ""),
            "current_result_id": str(getattr(current_result, "result_id", "") or ""),
            "baseline_result_date": baseline_date.isoformat(),
            "current_result_date": current_date.isoformat(),
            "entry_regime": baseline_regime,
            "entry_total_score": getattr(baseline_recommendation, "total_score", None),
            "regime": baseline_regime,
            "total_score": getattr(baseline_recommendation, "total_score", None),
            "recommendation_reasons": str(
                getattr(baseline_recommendation, "recommendation_reasons", "") or ""
            ),
            "regime_match": bool(getattr(baseline_recommendation, "regime_match", False)),
            "profile_id": str(
                baseline_context.get("profile_id") or baseline_config.get("profile_id") or ""
            ),
            "profile_version": str(
                baseline_context.get("profile_version")
                or baseline_config.get("profile_version")
                or ""
            ),
        }
        for key in ("stop_loss_pct", "take_profit_pct"):
            value = self._nested_value(baseline_config, key)
            if value is not None:
                source_summary[key] = value
        source_snapshot = {
            "stock_code": record.stock_code,
            "evaluation_date": evaluation_date.isoformat(),
            "baseline": {
                "result_id": source_summary["baseline_result_id"],
                "as_of_date": baseline_date.isoformat(),
                "recommendation": _json_safe(getattr(baseline_recommendation, "to_dict")()),
                "run_context": _json_safe(baseline_context),
                "config": _json_safe(baseline_config),
            },
            "current": {
                "result_id": source_summary["current_result_id"],
                "as_of_date": current_date.isoformat(),
                "recommendation": _json_safe(getattr(current_recommendation, "to_dict")()),
                "run_context": _json_safe(current_context),
                "config": _json_safe(current_config),
            },
            "rules": _json_safe(source_summary),
        }
        return ConditionRuleContext(
            source_id=(
                f"recommendation_condition:{source_summary['baseline_result_id']}"
                f":{source_summary['current_result_id']}:{record.stock_code}"
            ),
            source_snapshot_hash=_sha256_mapping(source_snapshot),
            as_of_date=current_date,
            available_at=current_available_at,
            source_summary=source_summary,
            current_regime=current_regime,
            current_total_score=getattr(current_recommendation, "total_score", None),
            reasons=("saved_recommendation_baseline_current_pair",),
            quality="observed",
            # JSON run file mtime 是本機觀測，不是官方 availability custody。
            availability_custody=False,
        )

    @staticmethod
    def _result_regime(result: Any) -> str:
        result_context = dict(getattr(result, "run_context", {}) or {})
        config = dict(getattr(result, "config", {}) or {})
        return str(
            getattr(result, "regime", None)
            or result_context.get("regime")
            or config.get("regime")
            or ""
        ).strip()

    @staticmethod
    def _analysis_identity(result: Any) -> tuple[str, str, str] | None:
        """取得可比較的 profile／version／計分配置 identity。"""

        context = dict(getattr(result, "run_context", {}) or {})
        config = dict(getattr(result, "config", {}) or {})
        profile_id = str(
            context.get("profile_id")
            or config.get("profile_id")
            or config.get("selected_profile")
            or ""
        ).strip()
        profile_version = str(
            context.get("profile_version")
            or config.get("profile_version")
            or ""
        ).strip()
        score_config_id = str(
            context.get("strategy_config_id")
            or context.get("strategy_config_hash")
            or config.get("strategy_config_id")
            or config.get("strategy_config_hash")
            or ""
        ).strip()
        if not profile_id or not profile_version or not score_config_id:
            return None
        return profile_id, profile_version, score_config_id

    def _non_comparable_context(
        self,
        record: UserDeclaredHoldingRecord,
        evaluation_date: date,
        *,
        current: tuple[Any, Any, datetime] | None,
        reason: str,
        baseline: tuple[Any, Any, datetime] | None = None,
    ) -> ConditionRuleContext:
        current_result_id = (
            str(getattr(current[0], "result_id", "") or "") if current is not None else ""
        )
        current_available_at = current[2] if current is not None else None
        payload = {
            "stock_code": record.stock_code,
            "evaluation_date": evaluation_date.isoformat(),
            "baseline_result_id": (
                str(getattr(baseline[0], "result_id", "") or "")
                if baseline is not None
                else ""
            ),
            "baseline_result_date": (
                (self._result_date(baseline[0]) or date.min).isoformat()
                if baseline is not None
                else ""
            ),
            "current_result_id": current_result_id,
            "reason": reason,
        }
        return ConditionRuleContext(
            source_id=(
                f"recommendation_condition:{reason}:"
                f"{payload['baseline_result_id'] or 'missing'}:"
                f"{current_result_id or 'missing'}"
            ),
            source_snapshot_hash=_sha256_mapping(_json_safe(payload)),
            as_of_date=evaluation_date,
            available_at=current_available_at,
            source_summary={},
            reasons=(reason,),
            quality="observed",
            availability_custody=False,
        )

    def __call__(
        self,
        record: UserDeclaredHoldingRecord,
        evaluation_date: date,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> ConditionRuleContext | None:
        return self.get_condition_context(
            record,
            evaluation_date,
            cancel_callback=cancel_callback,
        )


class PortfolioConditionResearchProvider:
    """以既有 monitor 與可追溯規則上下文產生 condition observation。

    ``PortfolioConditionMonitor`` 的 legacy valid 只代表它看到了某些
    position 欄位；對 user_declared lane 而言，只有價格／成本不能算研究
    規則。因此本 adapter 沒有 ``condition_context_source`` 時必定回傳
    WAIT，而不會把 monitor 的 fallback valid 映射成 HOLD。
    """

    def __init__(
        self,
        market_source: Any,
        *,
        condition_monitor: Any | None = None,
        condition_context_source: Any | None = None,
    ):
        self.market_source = market_source
        self.condition_context_source = condition_context_source
        if condition_monitor is None:
            from app_module.portfolio_condition_monitor import PortfolioConditionMonitor

            condition_monitor = PortfolioConditionMonitor()
        self.condition_monitor = condition_monitor

    def get_condition_observation(
        self,
        record: UserDeclaredHoldingRecord,
        evaluation_date: date,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> ConditionObservation | None:
        market_source = self.market_source
        if callable(market_source):
            market = _invoke_with_optional_cancel(
                market_source,
                (record.stock_code, evaluation_date),
                cancel_callback,
            )
        else:
            method = getattr(market_source, "get_market_observation", None)
            market = (
                _invoke_with_optional_cancel(
                    method,
                    (record.stock_code, evaluation_date),
                    cancel_callback,
                )
                if callable(method)
                else None
            )
        if market is None:
            return None
        _raise_if_cancelled(cancel_callback)
        context = self._call_condition_context(
            record,
            evaluation_date,
            cancel_callback=cancel_callback,
        )
        if context is None:
            return self._wait_observation(
                record,
                market,
                reason="condition_rule_missing",
                summary="沒有可追溯 Advice／評分／condition 規則；價格本身不產生 HOLD",
            )
        context_values = self._context_values(context)
        source_summary = dict(context_values.get("source_summary") or {})
        has_comparable_regime = bool(
            str(source_summary.get("entry_regime") or source_summary.get("regime") or "").strip()
            and str(context_values.get("current_regime") or "").strip()
        )
        has_comparable_score = (
            source_summary.get("entry_total_score", source_summary.get("total_score"))
            not in (None, "")
            and context_values.get("current_total_score") not in (None, "")
        )
        has_explicit_price_rule = any(
            source_summary.get(key) not in (None, "")
            for key in ("stop_loss_pct", "take_profit_pct")
        )
        if not (has_comparable_regime or has_comparable_score or has_explicit_price_rule):
            context_reasons = tuple(
                str(item)
                for item in (context_values.get("reasons") or ())
                if str(item).strip()
            )
            reason = (
                context_reasons[0]
                if context_reasons and context_reasons[0].startswith("research_")
                else "condition_rule_not_comparable"
            )
            return self._wait_observation(
                record,
                market,
                reason=reason,
                summary=(
                    "研究基準與目前快照不是獨立來源，不能自我比較"
                    if reason == "research_baseline_not_independent"
                    else "來源沒有可比較的 regime／score 或明確停損停利規則"
                ),
                context=context_values,
            )
        position = PositionDTO(
            position_id=record.holding_id,
            portfolio_id=record.portfolio_id,
            stock_code=record.stock_code,
            stock_name="",
            quantity=float(record.quantity),  # numeric-boundary: existing monitor DTO
            invested_amount=float(record.declared_cost_total),  # numeric-boundary: existing monitor DTO
            average_cost=float(record.declared_cost),  # numeric-boundary: existing monitor DTO
            source_type="user_declared_research",
            source_id=record.holding_id,
            source_summary={
                **source_summary,
                "declared_thesis": record.thesis,
            },
            current_price=float(market.price),  # numeric-boundary: existing monitor DTO
        )
        from app_module.portfolio_condition_monitor import PortfolioCurrentSnapshot

        result = self.condition_monitor.evaluate(
            position,
            PortfolioCurrentSnapshot(
                current_regime=str(context_values.get("current_regime") or ""),
                current_total_score=context_values.get("current_total_score"),
                current_price=market.price,
            ),
        )
        action = {
            "valid": RESEARCH_ACTION_HOLD,
            "warning": RESEARCH_ACTION_REDUCE,
            "invalid": RESEARCH_ACTION_EXIT,
        }.get(str(getattr(result, "status", "")).lower(), RESEARCH_ACTION_WAIT)
        payload = {
            "holding_id": record.holding_id,
            "stock_code": record.stock_code,
            "evaluation_date": evaluation_date.isoformat(),
            "market_source_hash": market.source_snapshot_hash,
            "condition_source_id": str(context_values.get("source_id") or ""),
            "condition_source_hash": str(context_values.get("source_snapshot_hash") or ""),
            "status": str(getattr(result, "status", "")),
            "label": str(getattr(result, "label", "")),
            "reasons": list(getattr(result, "reasons", ()) or ()),
            "details": dict(getattr(result, "details", {}) or {}),
        }
        return ConditionObservation(
            stock_code=record.stock_code,
            suggested_action=action,
            as_of_date=context_values.get("as_of_date") or market.as_of_date,
            source_id=(
                "portfolio_condition_monitor:"
                f"{context_values.get('source_id') or record.holding_id}"
            ),
            source_snapshot_hash=_sha256_mapping(_json_safe(payload)),
            reasons=tuple(str(item) for item in (getattr(result, "reasons", ()) or ())),
            summary=str(getattr(result, "label", "") or ""),
            available_at=context_values.get("available_at") or market.available_at,
            quality=str(context_values.get("quality") or market.quality),
            availability_custody=bool(context_values.get("availability_custody", False)),
        )

    @staticmethod
    def _context_values(context: Any) -> dict[str, Any]:
        if isinstance(context, ConditionRuleContext):
            return {
                "source_id": context.source_id,
                "source_snapshot_hash": context.source_snapshot_hash,
                "as_of_date": context.as_of_date,
                "available_at": context.available_at,
                "source_summary": dict(context.source_summary),
                "current_regime": context.current_regime,
                "current_total_score": context.current_total_score,
                "reasons": context.reasons,
                "quality": context.quality,
                "availability_custody": context.availability_custody,
            }
        if isinstance(context, Mapping):
            values = dict(context)
            source_summary = values.get("source_summary")
            if isinstance(source_summary, Mapping):
                values["source_summary"] = dict(source_summary)
            else:
                values["source_summary"] = {
                    key: value
                    for key, value in values.items()
                    if key
                    in {
                        "regime",
                        "entry_regime",
                        "total_score",
                        "entry_total_score",
                        "stop_loss_pct",
                        "take_profit_pct",
                    }
                }
            return values
        return {}

    def _call_condition_context(
        self,
        record: UserDeclaredHoldingRecord,
        evaluation_date: date,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> Any | None:
        source = self.condition_context_source
        if source is None:
            return None
        if callable(source):
            return _invoke_with_optional_cancel(
                source,
                (record, evaluation_date),
                cancel_callback,
            )
        method = getattr(source, "get_condition_context", None)
        if callable(method):
            return _invoke_with_optional_cancel(
                method,
                (record, evaluation_date),
                cancel_callback,
            )
        raise UserDeclaredHoldingError(
            "condition_context_source 必須是 callable 或 get_condition_context provider"
        )

    @staticmethod
    def _wait_observation(
        record: UserDeclaredHoldingRecord,
        market: MarketObservation,
        *,
        reason: str,
        summary: str,
        context: Mapping[str, Any] | None = None,
    ) -> ConditionObservation:
        context = context or {}
        payload = {
            "holding_id": record.holding_id,
            "stock_code": record.stock_code,
            "condition_as_of_date": _parse_date(
                context.get("as_of_date") or market.as_of_date,
                field_name="condition.as_of_date",
            ).isoformat(),
            "reason": reason,
            "context_source_id": str(context.get("source_id") or ""),
            "context_source_hash": str(context.get("source_snapshot_hash") or ""),
        }
        return ConditionObservation(
            stock_code=record.stock_code,
            suggested_action=RESEARCH_ACTION_WAIT,
            as_of_date=context.get("as_of_date") or market.as_of_date,
            source_id=(
                str(context.get("source_id") or "")
                or f"portfolio_condition_monitor:rule_missing:{record.holding_id}"
            ),
            source_snapshot_hash=_sha256_mapping(_json_safe(payload)),
            reasons=(reason,),
            summary=summary,
            available_at=context.get("available_at") or market.available_at,
            quality=str(context.get("quality") or market.quality),
            availability_custody=bool(context.get("availability_custody", False)),
        )

    def __call__(
        self,
        record: UserDeclaredHoldingRecord,
        evaluation_date: date,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> ConditionObservation | None:
        return self.get_condition_observation(
            record,
            evaluation_date,
            cancel_callback=cancel_callback,
        )


@dataclass(frozen=True, slots=True)
class UserDeclaredHoldingResearchRow:
    record: UserDeclaredHoldingRecord
    evaluation_date: date
    evaluated_at: str
    research_status: str
    advice_action: str
    advice_reason: str
    reason_codes: tuple[str, ...]
    market_price: Decimal | None
    market_as_of_date: date | None
    condition_as_of_date: date | None
    declared_cost_total: Decimal
    current_market_value: Decimal | None
    mark_to_declared_cost_delta: Decimal | None
    mark_to_declared_cost_pct: Decimal | None
    realized_pnl: Decimal | None
    realized_pnl_status: str
    source_trace: tuple[str, ...]
    source_status: str = SOURCE_STATUS_USER_DECLARED
    entry_lineage_status: str = ENTRY_LINEAGE_UNPROVEN
    fill_verification: str = FILL_VERIFICATION_NOT_PROVIDED
    research_only: bool = True
    formal_credit: bool = False
    broker_execution: bool = False
    auto_action_allowed: bool = False
    calibration_status: str = "excluded_user_declared"
    effectiveness_cohort: str = "excluded_user_declared"
    review_required: bool = True

    @property
    def holding_id(self) -> str:
        return self.record.holding_id

    @property
    def stock_code(self) -> str:
        return self.record.stock_code


@dataclass(frozen=True, slots=True)
class UserDeclaredHoldingResearchReadModel:
    evaluation_date: date
    evaluated_at: str
    status: str
    rows: tuple[UserDeclaredHoldingResearchRow, ...]
    blockers: tuple[str, ...] = ()
    source_status: str = SOURCE_STATUS_USER_DECLARED
    entry_lineage_status: str = ENTRY_LINEAGE_UNPROVEN
    fill_verification: str = FILL_VERIFICATION_NOT_PROVIDED
    research_only: bool = True
    formal_credit: bool = False
    broker_execution: bool = False
    auto_action_allowed: bool = False

    def for_holding(self, holding_id: str) -> UserDeclaredHoldingResearchRow | None:
        return next((row for row in self.rows if row.holding_id == holding_id), None)


class UserDeclaredHoldingResearchStore:
    """保存 user_declared revision stream 的 append-only JSONL adapter。"""

    def __init__(self, path: Path | str):
        self.path = Path(path)

    @classmethod
    def under_output_root(cls, output_root: Path | str) -> "UserDeclaredHoldingResearchStore":
        return cls(Path(output_root) / "portfolio" / "user_declared_holdings.jsonl")

    def read_history(
        self,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> tuple[dict[str, Any], ...]:
        # 空的 research lane 必須保持真正唯讀；Portfolio 初始化或首次
        # 背景 refresh 不應為了讀取不存在的 JSONL 建立資料夾／lock file。
        if not self.path.exists():
            _raise_if_cancelled(cancel_callback)
            return ()
        with _interprocess_lock(self.path):
            records = _read_jsonl_unlocked(self.path, cancel_callback=cancel_callback)
            _project_heads(records, cancel_callback=cancel_callback)
            return tuple(dict(record) for record in records)

    def read_heads(
        self,
        *,
        portfolio_id: str | None = None,
        include_archived: bool = False,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> tuple[dict[str, Any], ...]:
        return self.read_heads_as_of(
            datetime.max.replace(tzinfo=timezone.utc),
            portfolio_id=portfolio_id,
            include_archived=include_archived,
            cancel_callback=cancel_callback,
        )

    def read_heads_as_of(
        self,
        cutoff: datetime,
        *,
        portfolio_id: str | None = None,
        include_archived: bool = False,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> tuple[dict[str, Any], ...]:
        cutoff_utc = _normalise_datetime(cutoff)
        if not self.path.exists():
            _raise_if_cancelled(cancel_callback)
            return ()
        with _interprocess_lock(self.path):
            records = _read_jsonl_unlocked(self.path, cancel_callback=cancel_callback)
            _project_heads(records, cancel_callback=cancel_callback)
            visible_records: list[Mapping[str, Any]] = []
            for event in records:
                _raise_if_cancelled(cancel_callback)
                if _parse_datetime(event["created_at"], field_name="created_at") <= cutoff_utc:
                    visible_records.append(event)
            heads = _project_heads(visible_records, cancel_callback=cancel_callback)
            result: list[dict[str, Any]] = []
            for head_event in heads.values():
                _raise_if_cancelled(cancel_callback)
                if portfolio_id is not None and str(head_event["portfolio_id"]) != portfolio_id:
                    continue
                if not include_archived and bool(_event_payload(head_event).get("archived")):
                    continue
                result.append(dict(head_event))
            result.sort(key=lambda item: (str(item["portfolio_id"]), str(item["stock_code"]), str(item["holding_id"])))
            return tuple(result)

    def read_head(self, holding_id: str) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        with _interprocess_lock(self.path):
            records = _read_jsonl_unlocked(self.path)
            heads = _project_heads(records)
            event = heads.get(holding_id)
            return None if event is None else dict(event)

    def append_revision(self, event: Mapping[str, Any]) -> dict[str, Any]:
        candidate = dict(_json_safe(event))
        _validate_event_shape(candidate)
        with _interprocess_lock(self.path):
            records = _read_jsonl_unlocked(self.path)
            heads = _project_heads(records)
            candidate_canonical = _event_canonical(candidate)
            request_id = str(candidate["request_id"])
            fingerprint = str(candidate["command_fingerprint"])
            for existing in records:
                if str(existing["request_id"]) == request_id:
                    if str(existing["command_fingerprint"]) == fingerprint:
                        return dict(existing)
                    raise UserDeclaredHoldingConflictError("request_id 已用於不同聲明持倉操作")

            action = str(candidate["action"])
            holding_id = str(candidate["holding_id"])
            previous_head = heads.get(holding_id)
            if action == "created":
                active_key = (str(candidate["portfolio_id"]), str(candidate["stock_code"]))
                for existing_id, existing_head in heads.items():
                    if bool(_event_payload(existing_head).get("archived")):
                        continue
                    if (str(existing_head["portfolio_id"]), str(existing_head["stock_code"])) == active_key:
                        raise UserDeclaredHoldingConflictError(
                            "active_holding_already_exists: 同一 portfolio 的同股持倉必須使用既有 holding_id 修訂"
                        )
                if previous_head is not None:
                    raise UserDeclaredHoldingConflictError("holding_id 已存在")
                if int(candidate["revision_number"]) != 1 or candidate.get("previous_revision_id", ""):
                    raise UserDeclaredHoldingConflictError("新聲明持倉 revision 必須從 1 開始")
                if candidate.get("expected_revision_number") is not None:
                    raise UserDeclaredHoldingConflictError("新聲明持倉不得帶 expected_revision_number")
            else:
                if previous_head is None:
                    raise UserDeclaredHoldingConflictError("holding_id 不存在，不能修訂或封存")
                if bool(_event_payload(previous_head).get("archived")):
                    raise UserDeclaredHoldingConflictError("holding_id 已封存，不能再次修訂")
                expected = candidate.get("expected_revision_number")
                if expected != int(previous_head["revision_number"]):
                    raise UserDeclaredHoldingConflictError(
                        "revision_conflict: 目前 revision 已變更，請重新讀取後再修訂"
                    )
                if candidate.get("previous_revision_id") != previous_head["revision_id"]:
                    raise UserDeclaredHoldingConflictError("revision_chain_conflict")
                if int(candidate["revision_number"]) != int(previous_head["revision_number"]) + 1:
                    raise UserDeclaredHoldingConflictError("revision_number 不連續")

            resulting_records = [*records, candidate]
            _project_heads(resulting_records)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and self.path.stat().st_size:
                with open(self.path, "rb") as handle:
                    handle.seek(-1, os.SEEK_END)
                    if handle.read(1) != b"\n":
                        with open(self.path, "ab") as separator:
                            separator.write(b"\n")
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(candidate_canonical)
                handle.write("\n")
            return dict(candidate)

    def history_for(self, holding_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(
            event for event in self.read_history() if str(event.get("holding_id")) == holding_id
        )

    def find_idempotent(
        self,
        *,
        request_id: str | None,
        command_fingerprint: str,
    ) -> dict[str, Any] | None:
        """只依 request identity 找出安全可重送的相同操作。

        command fingerprint 用來確認同一 request 的 payload 沒被改寫；它不會
        跨不同 request 永久去重，否則封存後無法建立新的同股聲明 holding。
        """

        request_text = str(request_id) if request_id else None
        if request_text is None:
            return None
        if not self.path.exists():
            return None
        with _interprocess_lock(self.path):
            records = _read_jsonl_unlocked(self.path)
            _project_heads(records)
            for event in records:
                if str(event["request_id"]) == request_text:
                    if str(event["command_fingerprint"]) != command_fingerprint:
                        raise UserDeclaredHoldingConflictError(
                            "request_id 已用於不同聲明持倉操作"
                        )
                    return dict(event)
        return None


def _record_from_event(event: Mapping[str, Any]) -> UserDeclaredHoldingRecord:
    payload = _event_payload(event)
    return UserDeclaredHoldingRecord(
        holding_id=str(event["holding_id"]),
        portfolio_id=str(event["portfolio_id"]),
        stock_code=_stock_code(event["stock_code"]),
        quantity=_quantity(payload["quantity"]),
        declared_cost=_decimal(payload["declared_cost"], field_name="declared_cost", positive=True),
        declared_date=_parse_date(payload["declared_date"], field_name="declared_date"),
        notes=_text(payload.get("notes", ""), field_name="notes", max_length=_MAX_NOTES_LENGTH),
        thesis=_text(payload.get("thesis", ""), field_name="thesis", max_length=_MAX_THESIS_LENGTH),
        revision_id=str(event["revision_id"]),
        revision_number=int(event["revision_number"]),
        action=str(event["action"]),
        created_at=_datetime_text(_parse_datetime(payload["created_at"], field_name="created_at")),
        updated_at=_datetime_text(_parse_datetime(payload["updated_at"], field_name="updated_at")),
        archived=bool(payload.get("archived")),
        archived_at=(
            None
            if payload.get("archived_at") is None
            else _datetime_text(_parse_datetime(payload["archived_at"], field_name="archived_at"))
        ),
        archive_reason=_text(payload.get("archive_reason", ""), field_name="archive_reason", max_length=_MAX_NOTES_LENGTH),
    )


def _history_item_from_event(event: Mapping[str, Any]) -> UserDeclaredHoldingHistoryItem:
    return UserDeclaredHoldingHistoryItem(
        revision_id=str(event["revision_id"]),
        holding_id=str(event["holding_id"]),
        action=str(event["action"]),
        revision_number=int(event["revision_number"]),
        previous_revision_id=str(event.get("previous_revision_id", "")),
        request_id=str(event["request_id"]),
        command_fingerprint=str(event["command_fingerprint"]),
        created_at=_datetime_text(_parse_datetime(event["created_at"], field_name="created_at")),
        snapshot=_record_from_event(event),
    )


class UserDeclaredHoldingResearchService:
    """管理 user_declared holding 的 exact identity 與研究 read model。"""

    def __init__(
        self,
        store: UserDeclaredHoldingResearchStore,
        *,
        now_provider: Callable[[], datetime] | None = None,
        id_provider: Callable[[], str] | None = None,
    ):
        self.store = store
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._id_provider = id_provider or (lambda: uuid4().hex)

    @classmethod
    def under_output_root(
        cls,
        output_root: Path | str,
        *,
        now_provider: Callable[[], datetime] | None = None,
        id_provider: Callable[[], str] | None = None,
    ) -> "UserDeclaredHoldingResearchService":
        return cls(
            UserDeclaredHoldingResearchStore.under_output_root(output_root),
            now_provider=now_provider,
            id_provider=id_provider,
        )

    def _now(self) -> datetime:
        return _normalise_datetime(self._now_provider())

    def now(self) -> datetime:
        """提供 UI／caller 可重用的 timezone-aware 現在時間。"""

        return self._now()

    def _normalise_draft(
        self,
        draft: UserDeclaredHoldingDraft,
        *,
        existing: UserDeclaredHoldingRecord | None = None,
    ) -> dict[str, Any]:
        if not isinstance(draft, UserDeclaredHoldingDraft):
            raise UserDeclaredHoldingError("draft 必須是 UserDeclaredHoldingDraft")
        stock_code = _stock_code(draft.stock_code)
        portfolio_id = _scope(draft.portfolio_id)
        if existing is not None:
            if stock_code != existing.stock_code:
                raise UserDeclaredHoldingConflictError("stock_code 不可在同一 holding_id 的 revision 變更")
            if portfolio_id != existing.portfolio_id:
                raise UserDeclaredHoldingConflictError("portfolio_id 不可在同一 holding_id 的 revision 變更")
        quantity = _quantity(draft.quantity)
        declared_cost = _decimal(draft.declared_cost, field_name="declared_cost", positive=True)
        declared_date = _parse_date(draft.declared_date, field_name="declared_date")
        if declared_date > self._now().date():
            raise UserDeclaredHoldingError("declared_date 不得晚於目前日期")
        return {
            "portfolio_id": portfolio_id,
            "stock_code": stock_code,
            "quantity": quantity,
            "declared_cost": format(declared_cost, "f"),
            "declared_date": declared_date.isoformat(),
            "notes": _text(draft.notes, field_name="notes", max_length=_MAX_NOTES_LENGTH),
            "thesis": _text(draft.thesis, field_name="thesis", max_length=_MAX_THESIS_LENGTH),
        }

    def _build_event(
        self,
        *,
        action: str,
        holding_id: str,
        revision_number: int,
        previous_revision_id: str,
        expected_revision_number: int | None,
        request_id: str | None,
        command_fingerprint: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        revision_id = f"udhr_{self._id_provider()}"
        now_text = _datetime_text(self._now())
        full_payload = {
            **dict(payload),
            "holding_id": holding_id,
            "source_status": SOURCE_STATUS_USER_DECLARED,
            "entry_lineage_status": ENTRY_LINEAGE_UNPROVEN,
            "fill_verification": FILL_VERIFICATION_NOT_PROVIDED,
            "research_only": True,
            "created_at": str(payload.get("created_at") or now_text),
            "updated_at": now_text,
            "archived": action == "archived",
            "archived_at": now_text if action == "archived" else None,
            "archive_reason": str(payload.get("archive_reason", "")),
            "source_trace": list(_stable_source_trace(holding_id, revision_id)),
        }
        return {
            "schema_version": SCHEMA_VERSION,
            "record_type": RECORD_TYPE,
            "revision_id": revision_id,
            "holding_id": holding_id,
            "portfolio_id": str(full_payload["portfolio_id"]),
            "stock_code": str(full_payload["stock_code"]),
            "action": action,
            "revision_number": revision_number,
            "previous_revision_id": previous_revision_id,
            "expected_revision_number": expected_revision_number,
            "request_id": request_id or f"udhr_request_{self._id_provider()}",
            "command_fingerprint": command_fingerprint,
            "created_at": now_text,
            "payload": full_payload,
        }

    @staticmethod
    def _command_fingerprint(
        operation: str,
        *,
        holding_id: str,
        expected_revision_number: int | None,
        payload: Mapping[str, Any],
    ) -> str:
        return _sha256_mapping(
            {
                "schema_version": SCHEMA_VERSION,
                "operation": operation,
                "holding_id": holding_id,
                "expected_revision_number": expected_revision_number,
                "payload": dict(payload),
            }
        )

    def _record_for_event(self, event: Mapping[str, Any]) -> UserDeclaredHoldingRecord:
        return _record_from_event(event)

    def create_holding(
        self,
        draft: UserDeclaredHoldingDraft,
        *,
        request_id: str | None = None,
    ) -> UserDeclaredHoldingRecord:
        payload = self._normalise_draft(draft)
        command_fingerprint = self._command_fingerprint(
            "create",
            holding_id="create",
            expected_revision_number=None,
            payload=payload,
        )
        event = self._build_event(
            action="created",
            holding_id=f"user_declared:{self._id_provider()}",
            revision_number=1,
            previous_revision_id="",
            expected_revision_number=None,
            request_id=request_id,
            command_fingerprint=command_fingerprint,
            payload=payload,
        )
        return self._record_for_event(self.store.append_revision(event))

    def get_holding(self, holding_id: str, *, include_archived: bool = True) -> UserDeclaredHoldingRecord | None:
        event = self.store.read_head(holding_id)
        if event is None:
            return None
        record = self._record_for_event(event)
        if record.archived and not include_archived:
            return None
        return record

    def list_holdings(
        self,
        *,
        portfolio_id: str = "default",
        include_archived: bool = False,
        as_of: datetime | str | None = None,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> tuple[UserDeclaredHoldingRecord, ...]:
        _raise_if_cancelled(cancel_callback)
        cutoff = self._now() if as_of is None else _parse_datetime(as_of, field_name="as_of")
        if cutoff > self._now():
            raise UserDeclaredHoldingError("as_of 不得晚於目前時間")
        return tuple(
            self._record_for_event(event)
            for event in self.store.read_heads_as_of(
                cutoff,
                portfolio_id=_scope(portfolio_id),
                include_archived=include_archived,
                cancel_callback=cancel_callback,
            )
        )

    def history(self, holding_id: str) -> tuple[UserDeclaredHoldingHistoryItem, ...]:
        return tuple(_history_item_from_event(event) for event in self.store.history_for(holding_id))

    def revise_holding(
        self,
        holding_id: str,
        draft: UserDeclaredHoldingDraft,
        *,
        expected_revision_number: int,
        request_id: str | None = None,
    ) -> UserDeclaredHoldingRecord:
        if (
            isinstance(expected_revision_number, bool)
            or not isinstance(expected_revision_number, int)
            or expected_revision_number <= 0
        ):
            raise UserDeclaredHoldingError("expected_revision_number 必須是正整數")
        base_event = next(
            (
                event
                for event in self.store.history_for(holding_id)
                if int(event["revision_number"]) == expected_revision_number
            ),
            None,
        )
        if base_event is None:
            if self.get_holding(holding_id, include_archived=True) is None:
                raise UserDeclaredHoldingConflictError("holding_id 不存在")
            raise UserDeclaredHoldingConflictError("revision_conflict: 請先重新讀取持倉")
        base = self._record_for_event(base_event)
        if base.archived:
            raise UserDeclaredHoldingConflictError("已封存的 holding 不可修訂")
        payload = self._normalise_draft(draft, existing=base)
        payload["created_at"] = base.created_at
        command_fingerprint = self._command_fingerprint(
            "revise",
            holding_id=holding_id,
            expected_revision_number=expected_revision_number,
            payload=payload,
        )
        idempotent = self.store.find_idempotent(
            request_id=request_id,
            command_fingerprint=command_fingerprint,
        )
        if idempotent is not None:
            if str(idempotent["holding_id"]) != holding_id or str(idempotent["action"]) != "revised":
                raise UserDeclaredHoldingConflictError("request_id／fingerprint 與 holding scope 不一致")
            return self._record_for_event(idempotent)

        current = self.get_holding(holding_id, include_archived=True)
        if current is None:
            raise UserDeclaredHoldingConflictError("holding_id 不存在")
        if current.archived:
            raise UserDeclaredHoldingConflictError("已封存的 holding 不可修訂")
        if expected_revision_number != current.revision_number:
            raise UserDeclaredHoldingConflictError("revision_conflict: 請先重新讀取持倉")
        event = self._build_event(
            action="revised",
            holding_id=holding_id,
            revision_number=current.revision_number + 1,
            previous_revision_id=current.revision_id,
            expected_revision_number=expected_revision_number,
            request_id=request_id,
            command_fingerprint=command_fingerprint,
            payload=payload,
        )
        return self._record_for_event(self.store.append_revision(event))

    def archive_holding(
        self,
        holding_id: str,
        *,
        expected_revision_number: int,
        reason: str = "",
        request_id: str | None = None,
    ) -> UserDeclaredHoldingRecord:
        if (
            isinstance(expected_revision_number, bool)
            or not isinstance(expected_revision_number, int)
            or expected_revision_number <= 0
        ):
            raise UserDeclaredHoldingError("expected_revision_number 必須是正整數")
        base_event = next(
            (
                event
                for event in self.store.history_for(holding_id)
                if int(event["revision_number"]) == expected_revision_number
            ),
            None,
        )
        if base_event is None:
            if self.get_holding(holding_id, include_archived=True) is None:
                raise UserDeclaredHoldingConflictError("holding_id 不存在")
            raise UserDeclaredHoldingConflictError("revision_conflict: 請先重新讀取持倉")
        base = self._record_for_event(base_event)
        if base.archived:
            raise UserDeclaredHoldingConflictError("holding 已封存")
        archive_reason = _text(
            reason, field_name="archive_reason", max_length=_MAX_NOTES_LENGTH
        )
        payload = {
            "portfolio_id": base.portfolio_id,
            "stock_code": base.stock_code,
            "quantity": base.quantity,
            "declared_cost": format(base.declared_cost, "f"),
            "declared_date": base.declared_date.isoformat(),
            "notes": base.notes,
            "thesis": base.thesis,
            "created_at": base.created_at,
            "archive_reason": archive_reason,
        }
        command_fingerprint = self._command_fingerprint(
            "archive",
            holding_id=holding_id,
            expected_revision_number=expected_revision_number,
            payload=payload,
        )
        idempotent = self.store.find_idempotent(
            request_id=request_id,
            command_fingerprint=command_fingerprint,
        )
        if idempotent is not None:
            if str(idempotent["holding_id"]) != holding_id or str(idempotent["action"]) != "archived":
                raise UserDeclaredHoldingConflictError("request_id／fingerprint 與 holding scope 不一致")
            return self._record_for_event(idempotent)

        current = self.get_holding(holding_id, include_archived=True)
        if current is None:
            raise UserDeclaredHoldingConflictError("holding_id 不存在")
        if current.archived:
            raise UserDeclaredHoldingConflictError("holding 已封存")
        if expected_revision_number != current.revision_number:
            raise UserDeclaredHoldingConflictError("revision_conflict: 請先重新讀取持倉")
        event = self._build_event(
            action="archived",
            holding_id=holding_id,
            revision_number=current.revision_number + 1,
            previous_revision_id=current.revision_id,
            expected_revision_number=expected_revision_number,
            request_id=request_id,
            command_fingerprint=command_fingerprint,
            payload=payload,
        )
        return self._record_for_event(self.store.append_revision(event))

    def read_research(
        self,
        *,
        evaluation_date: date | str,
        evaluated_at: datetime | str | None = None,
        portfolio_id: str = "default",
        market_source: Callable[[str, date], MarketObservation | None] | Any | None = None,
        condition_source: Callable[[UserDeclaredHoldingRecord, date], ConditionObservation | None]
        | Any
        | None = None,
        max_age_days: int = 3,
        include_archived: bool = False,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> UserDeclaredHoldingResearchReadModel:
        _raise_if_cancelled(cancel_callback)
        decision_date = _parse_date(evaluation_date, field_name="evaluation_date")
        current_time = self._now()
        current_taipei_date = current_time.astimezone(_TAIPEI_TIMEZONE).date()
        if decision_date > current_taipei_date:
            raise UserDeclaredHoldingError("evaluation_date 不得晚於目前日期")
        if evaluated_at is None:
            if decision_date != current_taipei_date:
                raise UserDeclaredHoldingError(
                    "歷史 evaluation_date 必須明確提供同一台北日的 evaluated_at cutoff"
                )
            observed_at = current_time
        else:
            observed_at = _parse_datetime(evaluated_at, field_name="evaluated_at")
            if observed_at > current_time:
                raise UserDeclaredHoldingError("evaluated_at 不得晚於目前時間")
            if observed_at.astimezone(_TAIPEI_TIMEZONE).date() != decision_date:
                raise UserDeclaredHoldingError(
                    "evaluated_at 必須與 evaluation_date 落在同一台北日"
                )
        if max_age_days < 0:
            raise UserDeclaredHoldingError("max_age_days 不得小於 0")
        # 本機檔案 mtime 只能證明目前本機觀測；較早 evaluation date
        # 必須由 source 自己提供 capture／availability custody 才能作 PIT。
        availability_custody_required = decision_date < current_taipei_date
        records = self.list_holdings(
            portfolio_id=portfolio_id,
            include_archived=include_archived,
            as_of=observed_at,
            cancel_callback=cancel_callback,
        )
        rows: list[UserDeclaredHoldingResearchRow] = []
        for record in records:
            _raise_if_cancelled(cancel_callback)
            rows.append(
                self._evaluate_record(
                    record,
                    evaluation_date=decision_date,
                    evaluated_at=observed_at,
                    market_source=market_source,
                    condition_source=condition_source,
                    max_age_days=max_age_days,
                    availability_custody_required=availability_custody_required,
                    cancel_callback=cancel_callback,
                )
            )
        status = "empty" if not rows else ("ready" if any(row.research_status == "ready" for row in rows) else "unknown")
        blockers = tuple(
            f"{row.holding_id}:{reason}"
            for row in rows
            for reason in row.reason_codes
            if row.research_status != "ready"
        )
        return UserDeclaredHoldingResearchReadModel(
            evaluation_date=decision_date,
            evaluated_at=_datetime_text(observed_at),
            status=status,
            rows=tuple(rows),
            blockers=blockers,
        )

    @staticmethod
    def _call_market_source(
        market_source: Callable[[str, date], MarketObservation | None] | Any | None,
        stock_code: str,
        evaluation_date: date,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> MarketObservation | None:
        if market_source is None:
            return None
        if callable(market_source):
            return _invoke_with_optional_cancel(
                market_source,
                (stock_code, evaluation_date),
                cancel_callback,
            )
        method = getattr(market_source, "get_market_observation", None)
        if callable(method):
            return _invoke_with_optional_cancel(
                method,
                (stock_code, evaluation_date),
                cancel_callback,
            )
        raise UserDeclaredHoldingError("market_source 必須是 callable 或 get_market_observation provider")

    @staticmethod
    def _call_condition_source(
        condition_source: Callable[[UserDeclaredHoldingRecord, date], ConditionObservation | None]
        | Any
        | None,
        record: UserDeclaredHoldingRecord,
        evaluation_date: date,
        *,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> ConditionObservation | None:
        if condition_source is None:
            return None
        if callable(condition_source):
            return _invoke_with_optional_cancel(
                condition_source,
                (record, evaluation_date),
                cancel_callback,
            )
        method = getattr(condition_source, "get_condition_observation", None)
        if callable(method):
            return _invoke_with_optional_cancel(
                method,
                (record, evaluation_date),
                cancel_callback,
            )
        raise UserDeclaredHoldingError("condition_source 必須是 callable 或 get_condition_observation provider")

    @staticmethod
    def _source_checks(
        *,
        source_kind: str,
        stock_code: str,
        observed_stock_code: object,
        as_of_date: object,
        available_at: object,
        source_id: object,
        source_snapshot_hash: object,
        quality: object,
        availability_custody: object,
        evaluation_date: date,
        evaluated_at: datetime,
        max_age_days: int,
        availability_custody_required: bool,
    ) -> tuple[bool, tuple[str, ...], date | None, tuple[str, ...]]:
        reasons: list[str] = []
        trace: list[str] = []
        try:
            normalised_stock = _stock_code(observed_stock_code)
        except UserDeclaredHoldingError:
            normalised_stock = ""
        if normalised_stock != stock_code:
            reasons.append(f"{source_kind}_stock_mismatch")
        try:
            source_date = _parse_date(as_of_date, field_name=f"{source_kind}.as_of_date")
        except UserDeclaredHoldingError:
            source_date = None
            reasons.append(f"{source_kind}_as_of_date_missing")
        source_label = str(getattr(source_id, "value", source_id) or "").strip()
        source_hash = str(getattr(source_snapshot_hash, "value", source_snapshot_hash) or "").strip()
        if not source_label:
            reasons.append(f"{source_kind}_source_id_missing")
        if not _SHA256_RE.fullmatch(source_hash):
            reasons.append(f"{source_kind}_source_hash_invalid")
        quality_token = str(getattr(quality, "value", quality) or "").strip().lower()
        if quality_token not in _ALLOWED_SOURCE_QUALITIES:
            reasons.append(f"{source_kind}_quality_unknown")
        available_value: datetime | None = None
        if available_at is None:
            reasons.append(f"{source_kind}_available_at_missing")
        else:
            try:
                available_value = _parse_datetime(available_at, field_name=f"{source_kind}.available_at")
            except UserDeclaredHoldingError:
                reasons.append(f"{source_kind}_available_at_invalid")
            else:
                if available_value > evaluated_at:
                    reasons.append(f"{source_kind}_available_at_future")
        if source_date is not None:
            if source_date > evaluation_date:
                reasons.append(f"{source_kind}_as_of_date_future")
            elif (evaluation_date - source_date).days > max_age_days:
                reasons.append(f"{source_kind}_stale")
        if availability_custody_required and availability_custody is not True:
            reasons.append(f"{source_kind}_availability_custody_missing")
        trace.append(_source_trace_item(source_kind, source_label, source_hash, source_date))
        return not reasons, tuple(dict.fromkeys(reasons)), source_date, tuple(trace)

    def _evaluate_record(
        self,
        record: UserDeclaredHoldingRecord,
        *,
        evaluation_date: date,
        evaluated_at: datetime,
        market_source: Callable[[str, date], MarketObservation | None] | Any | None,
        condition_source: Callable[[UserDeclaredHoldingRecord, date], ConditionObservation | None]
        | Any
        | None,
        max_age_days: int,
        availability_custody_required: bool,
        cancel_callback: Callable[[], bool] | None = None,
    ) -> UserDeclaredHoldingResearchRow:
        source_trace = list(_stable_source_trace(record.holding_id, record.revision_id))
        reason_codes: list[str] = []
        _raise_if_cancelled(cancel_callback)
        try:
            revision_available_at = _parse_datetime(
                record.updated_at, field_name="holding_revision.updated_at"
            )
            source_trace.append(
                f"holding_revision_available_at:{revision_available_at.isoformat()}"
            )
            if revision_available_at > evaluated_at:
                reason_codes.append("holding_revision_available_at_future")
        except UserDeclaredHoldingError:
            revision_available_at = None
            reason_codes.append("holding_revision_available_at_invalid")
        market_price: Decimal | None = None
        market_as_of_date: date | None = None
        condition_as_of_date: date | None = None
        current_market_value: Decimal | None = None
        mark_delta: Decimal | None = None
        mark_pct: Decimal | None = None
        condition: ConditionObservation | None = None
        if record.archived:
            reason_codes.append("holding_archived")
        else:
            try:
                market = self._call_market_source(
                    market_source,
                    record.stock_code,
                    evaluation_date,
                    cancel_callback=cancel_callback,
                )
            except RuntimeError:
                if callable(cancel_callback) and cancel_callback():
                    raise
                market = None
                reason_codes.append("market_source_error")
            except Exception:
                market = None
                reason_codes.append("market_source_error")
            if market is None:
                reason_codes.append("market_data_missing")
            else:
                market_ok, market_reasons, market_as_of_date, market_trace = self._source_checks(
                    source_kind="market",
                    stock_code=record.stock_code,
                    observed_stock_code=market.stock_code,
                    as_of_date=market.as_of_date,
                    available_at=market.available_at,
                    source_id=market.source_id,
                    source_snapshot_hash=market.source_snapshot_hash,
                    quality=market.quality,
                    availability_custody=market.availability_custody,
                    evaluation_date=evaluation_date,
                    evaluated_at=evaluated_at,
                    max_age_days=max_age_days,
                    availability_custody_required=availability_custody_required,
                )
                source_trace.extend(market_trace)
                reason_codes.extend(market_reasons)
                try:
                    parsed_price = _decimal(market.price, field_name="market.price", positive=True)
                except UserDeclaredHoldingError:
                    parsed_price = None
                    reason_codes.append("market_price_invalid")
                if market_ok and parsed_price is not None:
                    market_price = parsed_price
                    current_market_value = parsed_price * Decimal(record.quantity)
                    mark_delta = current_market_value - record.declared_cost_total
                    mark_pct = (mark_delta / record.declared_cost_total * Decimal(100)).quantize(
                        Decimal("0.01")
                    )
            _raise_if_cancelled(cancel_callback)
            try:
                condition = self._call_condition_source(
                    condition_source,
                    record,
                    evaluation_date,
                    cancel_callback=cancel_callback,
                )
            except RuntimeError:
                if callable(cancel_callback) and cancel_callback():
                    raise
                condition = None
                reason_codes.append("condition_source_error")
            except Exception:
                condition = None
                reason_codes.append("condition_source_error")
            if condition is None:
                reason_codes.append("condition_data_missing")
            else:
                condition_ok, condition_reasons, condition_as_of_date, condition_trace = self._source_checks(
                    source_kind="condition",
                    stock_code=record.stock_code,
                    observed_stock_code=condition.stock_code,
                    as_of_date=condition.as_of_date,
                    available_at=condition.available_at,
                    source_id=condition.source_id,
                    source_snapshot_hash=condition.source_snapshot_hash,
                    quality=condition.quality,
                    availability_custody=condition.availability_custody,
                    evaluation_date=evaluation_date,
                    evaluated_at=evaluated_at,
                    max_age_days=max_age_days,
                    availability_custody_required=availability_custody_required,
                )
                source_trace.extend(condition_trace)
                reason_codes.extend(condition_reasons)
                action = str(
                    getattr(condition.suggested_action, "value", condition.suggested_action) or ""
                ).strip().upper()
                if action not in _POSITIVE_RESEARCH_ACTIONS:
                    reason_codes.append("condition_action_unknown")
                if not condition_ok:
                    reason_codes.append("condition_source_not_usable")
                reason_codes.extend(
                    str(item)
                    for item in (condition.reasons or ())
                    if str(item).strip().startswith(("research_", "condition_rule_"))
                )
            if not record.thesis:
                reason_codes.append("user_thesis_missing")
            _raise_if_cancelled(cancel_callback)

        reason_codes = list(dict.fromkeys(reason_codes))
        condition_action = (
            str(
                getattr(condition.suggested_action, "value", condition.suggested_action) or ""
            ).strip().upper()
            if condition is not None
            else ""
        )
        can_propose = (
            not record.archived
            and market_price is not None
            and condition is not None
            and condition_action in _POSITIVE_RESEARCH_ACTIONS
            and not any(
                reason.startswith(("market_", "condition_", "holding_revision_"))
                for reason in reason_codes
            )
            and bool(record.thesis)
        )
        if can_propose and condition is not None:
            advice_action = condition_action
            advice_reason = (condition.summary or "；".join(condition.reasons) or "condition_source_supplied").strip()
            research_status = "ready"
        else:
            advice_action = RESEARCH_ACTION_WAIT
            advice_reason = "；".join(reason_codes) or "需要補齊可追溯研究來源"
            research_status = "archived" if record.archived else "unknown"
            if not reason_codes:
                reason_codes.append("research_source_not_confirmed")
        if condition is not None and condition.reasons:
            source_trace.extend(f"condition_reason:{item}" for item in condition.reasons if str(item).strip())
        source_trace.append(f"evaluation_date:{evaluation_date.isoformat()}")
        return UserDeclaredHoldingResearchRow(
            record=record,
            evaluation_date=evaluation_date,
            evaluated_at=_datetime_text(evaluated_at),
            research_status=research_status,
            advice_action=advice_action,
            advice_reason=advice_reason,
            reason_codes=tuple(dict.fromkeys(reason_codes)),
            market_price=market_price,
            market_as_of_date=market_as_of_date,
            condition_as_of_date=condition_as_of_date,
            declared_cost_total=record.declared_cost_total,
            current_market_value=current_market_value,
            mark_to_declared_cost_delta=mark_delta,
            mark_to_declared_cost_pct=mark_pct,
            realized_pnl=None,
            realized_pnl_status="not_applicable_user_declared",
            source_trace=tuple(source_trace),
        )


def research_action_label(action: str) -> str:
    return {
        RESEARCH_ACTION_HOLD: "持有（研究建議）",
        RESEARCH_ACTION_REDUCE: "減碼候選（研究建議）",
        RESEARCH_ACTION_EXIT: "退出候選（研究建議）",
        RESEARCH_ACTION_WAIT: "待確認",
    }.get(action, "待確認")


def research_status_label(status: str) -> str:
    return {
        "ready": "可供研究檢視",
        "unknown": "資料不足／未知",
        "archived": "已封存",
        "empty": "尚無聲明持倉",
    }.get(status, "資料不足／未知")


def format_user_declared_research_summary(
    model: UserDeclaredHoldingResearchReadModel,
) -> str:
    ready_count = sum(row.research_status == "ready" for row in model.rows)
    return (
        f"使用者聲明持倉研究：{len(model.rows)} 筆；"
        f"可供研究檢視 {ready_count} 筆；"
        f"{research_status_label(model.status)}。"
        "所有建議均為 research-only，不代表成交、已實現績效或自動交易。"
    )


def format_user_declared_research_technical(
    row: UserDeclaredHoldingResearchRow,
) -> str:
    market_text = "未知" if row.market_price is None else format(row.market_price, "f")
    delta_text = "未知" if row.mark_to_declared_cost_delta is None else format(row.mark_to_declared_cost_delta, "f")
    return (
        f"holding_id={row.holding_id}\n"
        f"revision={row.record.revision_number} ({row.record.revision_id})\n"
        f"stock_code={row.stock_code}\n"
        f"quantity={row.record.quantity}\n"
        f"declared_cost={format(row.record.declared_cost, 'f')}\n"
        f"declared_date={row.record.declared_date.isoformat()}\n"
        f"evaluation_date={row.evaluation_date.isoformat()}\n"
        f"market_price={market_text}\n"
        f"mark_to_declared_cost_delta={delta_text}\n"
        f"advice_action={row.advice_action}\n"
        f"source_status={row.source_status}\n"
        f"entry_lineage_status={row.entry_lineage_status}\n"
        f"fill_verification={row.fill_verification}\n"
        f"research_only={row.research_only}\n"
        f"reason_codes={','.join(row.reason_codes) or 'none'}\n"
        f"source_trace={' | '.join(row.source_trace)}\n"
        "formal_credit=False；broker_execution=False；auto_action_allowed=False；"
        "calibration_status=excluded_user_declared"
    )


__all__ = [
    "ConditionRuleContext",
    "ConditionObservation",
    "ENTRY_LINEAGE_UNPROVEN",
    "FILL_VERIFICATION_NOT_PROVIDED",
    "FilesystemDailyMarketObservationProvider",
    "MarketObservation",
    "RESEARCH_ACTION_EXIT",
    "RESEARCH_ACTION_HOLD",
    "RESEARCH_ACTION_REDUCE",
    "RESEARCH_ACTION_WAIT",
    "SOURCE_STATUS_USER_DECLARED",
    "SavedRecommendationConditionContextProvider",
    "UserDeclaredHoldingConflictError",
    "UserDeclaredHoldingDraft",
    "UserDeclaredHoldingError",
    "UserDeclaredHoldingHistoryItem",
    "UserDeclaredHoldingRecord",
    "UserDeclaredHoldingResearchReadModel",
    "UserDeclaredHoldingResearchRow",
    "UserDeclaredHoldingResearchService",
    "UserDeclaredHoldingResearchStore",
    "UserDeclaredHoldingStorageError",
    "format_user_declared_research_summary",
    "format_user_declared_research_technical",
    "research_action_label",
    "research_status_label",
]
