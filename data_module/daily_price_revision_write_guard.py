"""保護已核准的個股日價格修訂，避免舊 CSV writer 將其覆蓋。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import pandas as pd

from data_module.ml_daily_price_revision_gate import (
    REPAIR_RECEIPT_RELATIVE_DIR,
    REPAIR_SCHEMA,
)


_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_DAILY_PRICE_COLUMNS = ("日期", "date")
_STOCK_CODE_COLUMNS = ("證券代號", "股票代號", "stock_code", "stock_id")
_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "漲跌": ("涨跌", "漲跌(+/-)"),
    "涨跌": ("漲跌", "漲跌(+/-)"),
    "漲跌(+/-)": ("漲跌", "涨跌"),
}


class DailyPriceRevisionWriteError(ValueError):
    """修訂 receipt 不可信或匯入內容會失去已核准列時使用。"""


@dataclass(frozen=True)
class _RevisionScope:
    source_date: str
    update_columns: tuple[str, ...]
    canonical_rows: Mapping[tuple[str, str], Mapping[str, object]]


class DailyPriceRevisionWriteGuard:
    """驗證修訂 receipt，拒絕會覆蓋已核准價格的重匯列。"""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path).resolve()
        self._scope = _load_revision_scope(self.database_path)
        self._seen: set[tuple[str, str]] = set()

    @property
    def has_revision(self) -> bool:
        return self._scope is not None

    def prepare_frame(
        self,
        frame: pd.DataFrame,
        *,
        replace_all: bool = False,
        replace_dates: Iterable[str] = (),
    ) -> pd.DataFrame:
        """回傳安全寫入副本；舊來源若改動受保護欄位就拒絕。"""

        if frame is None:
            raise DailyPriceRevisionWriteError("daily_prices 匯入資料不可為 None")
        result = frame.copy()
        replace_dates = tuple(replace_dates)
        validate_excluded_price_frame(self.database_path, result)
        _validate_session_replacement(
            self.database_path,
            result,
            replace_all=replace_all,
            replace_dates=bool(replace_dates),
        )
        scope = self._scope
        if scope is None:
            return result

        required_dates = {
            _date_key(value)
            for value in replace_dates
        }
        if replace_all:
            required_dates.add(scope.source_date)
        required_dates.intersection_update(
            date_key for date_key, _ in scope.canonical_rows
        )

        date_column = next(
            (column for column in _DAILY_PRICE_COLUMNS if column in result.columns),
            None,
        )
        code_column = next(
            (column for column in _STOCK_CODE_COLUMNS if column in result.columns),
            None,
        )
        if date_column is None or code_column is None:
            protected_columns = set(scope.update_columns)
            protected_columns.update(
                alias
                for column in scope.update_columns
                for alias in _COLUMN_ALIASES.get(column, ())
            )
            if replace_all or required_dates or protected_columns.intersection(result.columns):
                raise DailyPriceRevisionWriteError(
                    "daily_prices 替換缺少日期或證券代號，無法保留已修訂列"
                )
            return result

        key_positions: dict[tuple[str, str], list[Any]] = {}
        for index, row in result.iterrows():
            raw_date = row[date_column]
            if _is_missing(raw_date):
                if replace_all:
                    raise DailyPriceRevisionWriteError(
                        "daily_prices 整表替換含空日期"
                    )
                continue
            row_date = _date_key(raw_date)
            if row_date != scope.source_date:
                continue
            raw_symbol = row[code_column]
            symbol = _symbol_key(raw_symbol)
            if not symbol:
                raise DailyPriceRevisionWriteError(
                    f"修訂日期 {scope.source_date} 含空證券代號"
                )
            key = (row_date, symbol)
            if key in scope.canonical_rows:
                key_positions.setdefault(key, []).append(index)
                self._seen.add(key)

        must_preserve_rows = bool(replace_all or required_dates)
        if must_preserve_rows:
            missing_keys = sorted(
                key
                for key in scope.canonical_rows
                if key[0] in required_dates and key not in key_positions
            )
            if missing_keys:
                raise DailyPriceRevisionWriteError(
                    "daily_prices 替換缺少已修訂 key："
                    + ", ".join(f"{day}/{symbol}" for day, symbol in missing_keys[:5])
                )

        for key, positions in key_positions.items():
            canonical = scope.canonical_rows[key]
            for column in scope.update_columns:
                available_columns = tuple(
                    candidate
                    for candidate in (column, *_COLUMN_ALIASES.get(column, ()))
                    if candidate in result.columns
                )
                if not available_columns:
                    if must_preserve_rows:
                        raise DailyPriceRevisionWriteError(
                            f"daily_prices 替換缺少修訂欄位：{column}"
                        )
                    continue
                value = canonical[column]
                for position in positions:
                    for available_column in available_columns:
                        incoming = result.at[position, available_column]
                        expected = canonical.get(available_column, value)
                        if not _values_equal(incoming, expected):
                            raise DailyPriceRevisionWriteError(
                                "daily_prices 舊來源會覆蓋已核准價格："
                                f"{key[0]}/{key[1]}/{available_column}"
                            )

        return result

    def assert_full_replacement_complete(self) -> None:
        """確認整表替換來源包含 receipt 列出的每一個已修訂 key。"""

        self._assert_complete(
            required_keys=set(self._scope.canonical_rows) if self._scope else set(),
            label="整表替換",
        )

    def assert_dates_complete(self, dates: Iterable[str]) -> None:
        """確認會被 DELETE 的每個修訂日期仍包含完整修訂 key 範圍。"""

        scope = self._scope
        if scope is None:
            return
        required_dates = {_date_key(value) for value in dates}
        required_keys = {
            key for key in scope.canonical_rows if key[0] in required_dates
        }
        self._assert_complete(required_keys=required_keys, label="日期替換")

    def _assert_complete(
        self,
        *,
        required_keys: set[tuple[str, str]],
        label: str,
    ) -> None:
        missing = sorted(required_keys.difference(self._seen))
        if missing:
            raise DailyPriceRevisionWriteError(
                f"daily_prices {label}缺少已修訂 key："
                + ", ".join(f"{day}/{symbol}" for day, symbol in missing[:5])
            )


def prepare_daily_price_revision_frame(
    database_path: Path | str,
    frame: pd.DataFrame,
    *,
    replace_all: bool = False,
    replace_dates: Iterable[str] = (),
) -> pd.DataFrame:
    """建立一次性日價格修訂保護並回傳來源副本。"""

    replace_dates = tuple(replace_dates)
    guard = DailyPriceRevisionWriteGuard(database_path)
    prepared = guard.prepare_frame(
        frame,
        replace_all=replace_all,
        replace_dates=replace_dates,
    )
    if replace_all:
        guard.assert_full_replacement_complete()
    else:
        guard.assert_dates_complete(replace_dates)
    return prepared


def _load_revision_scope(database_path: Path) -> _RevisionScope | None:
    database_root = database_path.parent
    if database_root.name.casefold() == "sqlite":
        database_root = database_root.parent
    receipt_dir = database_root / REPAIR_RECEIPT_RELATIVE_DIR
    if not receipt_dir.exists() and not receipt_dir.is_symlink():
        return None
    if receipt_dir.is_symlink() or not receipt_dir.is_dir():
        raise DailyPriceRevisionWriteError(
            f"daily-price revision receipt directory is invalid: {receipt_dir}"
        )

    pending_path = receipt_dir / "pending.json"
    receipt_path = receipt_dir / "receipt.json"
    rollback_path = receipt_dir / "rollback_receipt.json"
    pending_exists = pending_path.exists() or pending_path.is_symlink()
    receipt_exists = receipt_path.exists() or receipt_path.is_symlink()
    rollback_exists = rollback_path.exists() or rollback_path.is_symlink()

    if not (pending_exists or receipt_exists or rollback_exists):
        if any(receipt_dir.iterdir()):
            raise DailyPriceRevisionWriteError(
                f"daily-price revision marker is unknown: {receipt_dir}"
            )
        return None
    if not receipt_exists:
        raise DailyPriceRevisionWriteError(
            f"daily-price revision receipt is missing: {receipt_path}"
        )

    receipt = _read_json_object(receipt_path, "daily-price revision receipt")
    _verify_payload_hash(receipt, receipt_path)
    scope = _scope_from_receipt(receipt, database_path, receipt_path)

    if pending_exists:
        pending = _read_json_object(pending_path, "daily-price pending marker")
        _validate_completed_pending(pending, receipt, database_path, pending_path)

    if rollback_exists:
        rollback = _read_json_object(rollback_path, "daily-price rollback receipt")
        _validate_rollback_receipt(
            rollback,
            receipt,
            receipt_path,
            database_path,
            rollback_path,
        )
        return _RevisionScope(
            source_date=scope.source_date,
            update_columns=scope.update_columns,
            canonical_rows={
                key: row["before"]
                for key, row in _raw_rows_by_key(receipt, receipt_path).items()
            },
        )
    return scope


def _scope_from_receipt(
    payload: Mapping[str, Any],
    database_path: Path,
    receipt_path: Path,
) -> _RevisionScope:
    if payload.get("schema_version") != REPAIR_SCHEMA:
        raise DailyPriceRevisionWriteError(
            f"daily-price revision receipt schema mismatch: {receipt_path}"
        )
    if payload.get("receipt_kind") != "historical_price_spike_repair":
        raise DailyPriceRevisionWriteError(
            f"daily-price revision receipt kind is unsupported: {receipt_path}"
        )
    if payload.get("status") != "applied":
        raise DailyPriceRevisionWriteError(
            f"daily-price revision receipt is not applied: {receipt_path}"
        )
    declared_db = payload.get("db_path")
    if not isinstance(declared_db, str) or Path(declared_db).resolve() != database_path:
        raise DailyPriceRevisionWriteError(
            f"daily-price revision receipt database path mismatch: {receipt_path}"
        )
    for field in ("allowlist_hash", "plan_hash", "canonical_sha256"):
        value = payload.get(field)
        if not isinstance(value, str) or _HASH_PATTERN.fullmatch(value) is None:
            raise DailyPriceRevisionWriteError(
                f"daily-price revision {field} is invalid: {receipt_path}"
            )
    source_date = _date_key(payload.get("source_date"))
    update_columns = payload.get("source_update_columns")
    if (
        not isinstance(update_columns, list)
        or not update_columns
        or any(not isinstance(column, str) or not column.strip() for column in update_columns)
        or len(set(update_columns)) != len(update_columns)
        or any(column in {"日期", "證券代號"} for column in update_columns)
    ):
        raise DailyPriceRevisionWriteError(
            f"daily-price revision source_update_columns is invalid: {receipt_path}"
        )
    raw_rows = _raw_rows_by_key(payload, receipt_path)
    if not raw_rows:
        raise DailyPriceRevisionWriteError(
            f"daily-price revision receipt has no affected rows: {receipt_path}"
        )
    raw_allowlist_count = payload.get("allowlist_count")
    if isinstance(raw_allowlist_count, bool) or not isinstance(raw_allowlist_count, (str, int)):
        raise DailyPriceRevisionWriteError(
            f"daily-price revision allowlist_count is invalid: {receipt_path}"
        )
    try:
        allowlist_count = int(raw_allowlist_count)
    except ValueError as exc:
        raise DailyPriceRevisionWriteError(
            f"daily-price revision allowlist_count is invalid: {receipt_path}"
        ) from exc
    if allowlist_count != len(raw_rows):
        raise DailyPriceRevisionWriteError(
            f"daily-price revision allowlist_count mismatch: {receipt_path}"
        )

    canonical_rows: dict[tuple[str, str], Mapping[str, object]] = {}
    for key, row in raw_rows.items():
        after = row["after"]
        before = row["before"]
        missing_after = [column for column in update_columns if column not in after]
        missing_before = [column for column in update_columns if column not in before]
        if missing_after or missing_before:
            raise DailyPriceRevisionWriteError(
                "daily-price revision before/after row lacks columns "
                f"{missing_before or missing_after}: {receipt_path}"
            )
        for evidence in (before, after):
            if "日期" in evidence and _date_key(evidence["日期"]) != key[0]:
                raise DailyPriceRevisionWriteError(
                    f"daily-price revision row date evidence mismatch: {receipt_path}"
                )
            if "證券代號" in evidence and _symbol_key(evidence["證券代號"]) != key[1]:
                raise DailyPriceRevisionWriteError(
                    f"daily-price revision row symbol evidence mismatch: {receipt_path}"
                )
        canonical_rows[key] = after
    return _RevisionScope(
        source_date=source_date,
        update_columns=tuple(update_columns),
        canonical_rows=canonical_rows,
    )


def _raw_rows_by_key(
    payload: Mapping[str, Any], receipt_path: Path
) -> dict[tuple[str, str], Mapping[str, Any]]:
    source_date = _date_key(payload.get("source_date"))
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise DailyPriceRevisionWriteError(
            f"daily-price revision rows are invalid: {receipt_path}"
        )
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    for index, raw_row in enumerate(rows):
        if not isinstance(raw_row, Mapping):
            raise DailyPriceRevisionWriteError(
                f"daily-price revision row {index} is invalid: {receipt_path}"
            )
        row_date = _date_key(raw_row.get("date"))
        symbol = _symbol_key(raw_row.get("symbol"))
        if row_date != source_date or not symbol:
            raise DailyPriceRevisionWriteError(
                f"daily-price revision row {index} is outside the receipt scope: {receipt_path}"
            )
        before = raw_row.get("before")
        after = raw_row.get("after")
        source = raw_row.get("source")
        differing_fields = raw_row.get("differing_fields")
        if (
            not isinstance(before, Mapping)
            or not isinstance(after, Mapping)
            or not isinstance(source, Mapping)
            or not isinstance(differing_fields, list)
        ):
            raise DailyPriceRevisionWriteError(
                f"daily-price revision row {index} lacks before/after/source evidence: {receipt_path}"
            )
        key = (row_date, symbol)
        if key in result:
            raise DailyPriceRevisionWriteError(
                f"daily-price revision has duplicate key {key}: {receipt_path}"
            )
        result[key] = {
            "before": before,
            "after": after,
            "source": source,
            "differing_fields": differing_fields,
        }
    return result


def _validate_completed_pending(
    pending: Mapping[str, Any],
    receipt: Mapping[str, Any],
    database_path: Path,
    pending_path: Path,
) -> None:
    if (
        pending.get("schema_version") != REPAIR_SCHEMA
        or pending.get("receipt_kind") != "historical_price_spike_repair_pending"
        or pending.get("status") != "applied_receipt_written"
    ):
        raise DailyPriceRevisionWriteError(
            f"daily-price pending marker is unresolved: {pending_path}"
        )
    if Path(str(pending.get("db_path", ""))).resolve() != database_path:
        raise DailyPriceRevisionWriteError(
            f"daily-price pending marker database path mismatch: {pending_path}"
        )
    for field in (
        "source_date",
        "allowlist_count",
        "allowlist_hash",
        "plan_hash",
        "canonical_sha256",
    ):
        if pending.get(field) != receipt.get(field):
            raise DailyPriceRevisionWriteError(
                f"daily-price pending/receipt {field} mismatch: {pending_path}"
            )


def _validate_rollback_receipt(
    rollback: Mapping[str, Any],
    receipt: Mapping[str, Any],
    receipt_path: Path,
    database_path: Path,
    rollback_path: Path,
) -> None:
    _verify_payload_hash(rollback, rollback_path)
    if (
        rollback.get("schema_version") != REPAIR_SCHEMA
        or rollback.get("receipt_kind") != "historical_price_spike_repair_rollback"
        or rollback.get("status") != "rolled_back"
        or rollback.get("backup_custody_only") is not True
        or rollback.get("row_bound") is not True
        or Path(str(rollback.get("db_path", ""))).resolve() != database_path
        or Path(str(rollback.get("source_receipt", ""))).resolve() != receipt_path.resolve()
        or rollback.get("source_receipt_sha256") != _file_sha256(receipt_path)
        or rollback.get("updated_rows") != receipt.get("allowlist_count")
        or rollback.get("restored_columns") != receipt.get("source_update_columns")
    ):
        raise DailyPriceRevisionWriteError(
            f"daily-price rollback receipt does not match applied receipt: {rollback_path}"
        )


def _read_json_object(path: Path, label: str) -> Mapping[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise DailyPriceRevisionWriteError(f"{label} is missing or linked: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DailyPriceRevisionWriteError(f"{label} is unreadable: {path}") from exc
    if not isinstance(payload, Mapping):
        raise DailyPriceRevisionWriteError(f"{label} must be a JSON object: {path}")
    return payload


def _verify_payload_hash(payload: Mapping[str, Any], path: Path) -> None:
    supplied = payload.get("receipt_sha256")
    body = dict(payload)
    body.pop("receipt_sha256", None)
    actual = "sha256:" + hashlib.sha256(_canonical_json_bytes(body)).hexdigest()
    if supplied != actual:
        raise DailyPriceRevisionWriteError(f"receipt payload hash mismatch: {path}")


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(64 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _date_key(value: object) -> str:
    if _is_missing(value):
        raise DailyPriceRevisionWriteError("daily-price receipt date is missing")
    text = str(value).strip()
    if len(text) == 7 and text.isdigit():
        return f"{int(text[:3]) + 1911:04d}{text[3:]}"
    compact = text.replace("-", "").replace("/", "")
    if len(compact) >= 8 and compact[:8].isdigit():
        date(int(compact[:4]), int(compact[4:6]), int(compact[6:8]))
        return compact[:8]
    if len(text) >= 10:
        parsed = date.fromisoformat(text[:10])
        return parsed.strftime("%Y%m%d")
    raise DailyPriceRevisionWriteError(f"daily-price date is invalid: {text!r}")


def _symbol_key(value: object) -> str:
    if _is_missing(value):
        return ""
    text = str(value).strip()
    if not text or text.casefold() == "nan":
        return ""
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text.zfill(4) if text.isdigit() and len(text) <= 4 else text


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False
    try:
        return bool(result)
    except (TypeError, ValueError):
        return False


def _values_equal(left: object, right: object) -> bool:
    """比較 SQLite／CSV 純量表示，不以目前資料庫欄值推斷正確值。"""

    left_missing = _is_missing(left)
    right_missing = _is_missing(right)
    if left_missing or right_missing:
        return left_missing and right_missing
    try:
        from decimal import Decimal, InvalidOperation

        left_decimal = Decimal(str(left).strip())
        right_decimal = Decimal(str(right).strip())
    except (InvalidOperation, TypeError, ValueError):
        return str(left).strip() == str(right).strip()
    return left_decimal.is_finite() and right_decimal.is_finite() and left_decimal == right_decimal


def _validate_session_replacement(
    database_path: Path,
    frame: pd.DataFrame,
    *,
    replace_all: bool,
    replace_dates: bool,
) -> None:
    """套用獨立維護的歷史交易日 insert-only 保護範圍。"""

    from data_module.historical_session_revision import RECEIPT_DIR, _plan, _root, validate_session_replacement

    days: set[str] = set()
    for path in sorted((_root(database_path) / RECEIPT_DIR).glob('*/revision.json')):
        _, plan = _plan(path, database_path)
        days.update(plan['dates'])
    if not days:
        return
    subset = _frame_for_dates(frame, days)

    validate_session_replacement(
        database_path,
        subset.to_dict(orient="records"),
        replace_all=replace_all,
        replace_dates=replace_dates,
    )


def _frame_for_dates(frame: pd.DataFrame, days: set[str]) -> pd.DataFrame:
    """僅物化受修訂日期，避免整份歷史資料轉成大量 Python 字典。"""
    name = next((column for column in _DAILY_PRICE_COLUMNS if column in frame.columns), None)
    if name is None:
        return frame.iloc[:0]
    compact = frame[name].astype('string').str.replace('-', '', regex=False).str.replace('/', '', regex=False).str[:8]
    roc = compact.str.len().eq(7) & compact.str.isdigit()
    if roc.any():
        compact.loc[roc] = frame.loc[roc, name].map(_date_key)
    return frame.loc[compact.isin(days)]


def validate_excluded_price_frame(database_path: Path, frame: pd.DataFrame) -> None:
    """價格與相依技指 writer 共用的錯日阻擋；不改動輸入 frame。"""
    from data_module.excluded_daily_price_revision import load_exclusion_evidence

    evidence = load_exclusion_evidence(database_path)
    excluded = {(str(day),str(symbol)) for item in evidence for day,symbol in item['keys']}
    closed_dates = {str(day) for item in evidence for day in item['closed_dates']}
    if not excluded and not closed_dates:
        return
    subset = _frame_for_dates(frame, closed_dates | {day for day, _ in excluded})
    if subset.empty:
        return
    date_column = next(column for column in _DAILY_PRICE_COLUMNS if column in subset.columns)
    code_column = next((column for column in _STOCK_CODE_COLUMNS if column in subset.columns), None)
    if code_column is None:
        raise DailyPriceRevisionWriteError('錯日修訂範圍缺少證券代號，已停止匯入')
    for raw_day, raw_symbol in subset[[date_column, code_column]].itertuples(index=False, name=None):
        if _date_key(raw_day) in closed_dates or (_date_key(raw_day), _symbol_key(raw_symbol)) in excluded:
            raise DailyPriceRevisionWriteError('匯入資料含已核驗排除的休市日／錯日紀錄，已停止重新匯入')
