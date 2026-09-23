"""將已核驗的日價來源修訂套用到 derived CSV 合併結果。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json

import pandas as pd

from data_module.daily_price_revision_write_guard import (
    _date_key,
    _load_revision_scope,
    _symbol_key,
    _values_equal,
)
from data_module.historical_session_revision import (
    RECEIPT_DIR as SESSION_RECEIPT_DIR,
    _plan as _load_session_plan,
)


class DailyPriceSourceRevisionOverlayError(ValueError):
    """來源修訂證據無效或無法對齊時停止 derived CSV 發布。"""


_PRICE_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "漲跌": ("涨跌", "漲跌(+/-)"),
    "涨跌": ("漲跌", "漲跌(+/-)"),
    "漲跌(+/-)": ("漲跌", "涨跌"),
}
_SESSION_DATA_COLUMNS = (
    "證券名稱",
    "成交股數",
    "成交筆數",
    "成交金額",
    "開盤價",
    "最高價",
    "最低價",
    "收盤價",
    "漲跌(+/-)",
    "漲跌",
    "涨跌",
    "漲跌價差",
    "最後揭示買價",
    "最後揭示買量",
    "最後揭示賣價",
    "最後揭示賣量",
    "本益比",
)
_SESSION_REQUIRED_COLUMNS = (
    "證券名稱",
    "成交股數",
    "成交筆數",
    "成交金額",
    "開盤價",
    "最高價",
    "最低價",
    "收盤價",
    "漲跌價差",
    "最後揭示買價",
    "最後揭示買量",
    "最後揭示賣價",
    "最後揭示賣量",
    "本益比",
)
_SESSION_SIGN_COLUMNS = ("漲跌(+/-)", "漲跌", "涨跌")


@dataclass(frozen=True)
class DailyPriceSourceRevisionSet:
    """一輪 merge 已驗證的價格 receipt 與官方歷史交易日 plan。"""

    database_path: Path
    price_rows: Mapping[tuple[str, str], Mapping[str, object]]
    price_update_columns: tuple[str, ...]
    session_rows: Mapping[tuple[str, str], Mapping[str, object]]
    excluded_keys: frozenset[tuple[str, str]]
    excluded_dates: frozenset[str]
    exclusion_evidence: tuple[Mapping[str, object], ...]
    evidence_identities: tuple[Mapping[str, object], ...]
    has_revision_evidence: bool

    @property
    def has_applied_revisions(self) -> bool:
        return bool(
            self.price_rows
            or self.session_rows
            or self.excluded_keys
            or self.excluded_dates
        )

    def apply(self, frame: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
        """套用已核驗來源修訂，回傳新 frame、變更值數與排除列數。"""

        if not isinstance(frame, pd.DataFrame):
            raise DailyPriceSourceRevisionOverlayError(
                "每日整合已停止：無法讀取合併資料，derived CSV 未發布。"
            )
        if not self.has_revision_evidence:
            return frame, 0, 0
        try:
            return self._apply_verified(frame)
        except DailyPriceSourceRevisionOverlayError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DailyPriceSourceRevisionOverlayError(
                "每日整合已停止：來源修訂證據缺漏或無法驗證，derived CSV 未發布。"
            ) from exc

    def _apply_verified(self, frame: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
        required_keys = {"日期", "證券代號"}
        if not required_keys.issubset(frame.columns):
            raise DailyPriceSourceRevisionOverlayError(
                "每日整合已停止：合併資料缺少日期或證券代號，derived CSV 未發布。"
            )
        if frame.columns.has_duplicates:
            raise DailyPriceSourceRevisionOverlayError(
                "每日整合已停止：合併資料欄位重複，derived CSV 未發布。"
            )

        overlays: dict[tuple[str, str], dict[str, object]] = {}
        for key, canonical in self.price_rows.items():
            updates = overlays.setdefault(key, {})
            for source_column in self.price_update_columns:
                target_column = _resolve_output_column(source_column, frame.columns)
                if target_column is None:
                    raise DailyPriceSourceRevisionOverlayError(
                        "每日整合已停止：derived CSV 缺少已修訂欄位，derived CSV 未發布。"
                    )
                value = canonical.get(source_column)
                _add_update(updates, target_column, value)

        for key, canonical in self.session_rows.items():
            updates = overlays.setdefault(key, {})
            for target_column in _SESSION_DATA_COLUMNS:
                if target_column not in frame.columns:
                    continue
                source_column = target_column
                if target_column == "漲跌(+/-)" and source_column not in canonical:
                    source_column = "漲跌"
                if source_column in canonical:
                    _add_update(updates, target_column, canonical[source_column])

        if self.session_rows:
            missing_columns = set(_SESSION_REQUIRED_COLUMNS).difference(frame.columns)
            if missing_columns or not any(
                column in frame.columns for column in _SESSION_SIGN_COLUMNS
            ):
                raise DailyPriceSourceRevisionOverlayError(
                    "每日整合已停止：derived CSV 缺少歷史交易日必要價量欄位，derived CSV 未發布。"
                )

        target_dates = {day for day, _ in overlays}
        result = frame
        candidate_positions = (
            _candidate_row_positions(result, target_dates) if overlays else []
        )
        candidate_rows = result.iloc[candidate_positions][["日期", "證券代號"]]
        candidate_days = candidate_rows["日期"].map(_date_key).tolist()
        candidate_symbols = candidate_rows["證券代號"].map(_symbol_key).tolist()
        candidate_keys = list(zip(candidate_days, candidate_symbols, strict=True))
        if len(candidate_keys) != len(set(candidate_keys)):
            raise DailyPriceSourceRevisionOverlayError(
                "每日整合已停止：修訂日期出現重複股票鍵，derived CSV 未發布。"
            )
        positions = dict(zip(candidate_keys, candidate_positions, strict=True))

        additions: list[dict[str, object]] = []
        changed_cells = 0
        session_keys = set(self.session_rows)
        existing_overlay_positions: list[tuple[int, dict[str, object]]] = []
        for key, values in overlays.items():
            position = positions.get(key)
            if position is None:
                if key not in session_keys:
                    raise DailyPriceSourceRevisionOverlayError(
                        "每日整合已停止：缺少已修訂原始股票列，無法安全補造，derived CSV 未發布。"
                    )
                new_row: dict[str, object] = {
                    str(column): pd.NA for column in result.columns
                }
                new_row["日期"] = key[0]
                new_row["證券代號"] = key[1]
                for column, value in values.items():
                    new_row[column] = value
                additions.append(new_row)
                changed_cells += len(values)
                continue
            existing_overlay_positions.append((position, values))

        overlay_columns = {
            column
            for _, values in existing_overlay_positions
            for column in values
        }
        for column in overlay_columns:
            column_index = result.columns.get_loc(column)
            column_rows = [
                (position, values[column])
                for position, values in existing_overlay_positions
                if column in values
            ]
            positions_for_column = [position for position, _ in column_rows]
            canonical_values = [value for _, value in column_rows]
            current_values = result.iloc[
                positions_for_column, column_index
            ].tolist()
            changed = [
                index
                for index, (current, canonical) in enumerate(
                    zip(current_values, canonical_values, strict=True)
                )
                if not _values_equal(current, canonical)
            ]
            if changed:
                target_positions = [positions_for_column[index] for index in changed]
                target_values = [canonical_values[index] for index in changed]
                result.iloc[target_positions, column_index] = target_values
                changed_cells += len(changed)
        if additions:
            result = pd.concat(
                [result, pd.DataFrame.from_records(additions, columns=result.columns)],
                ignore_index=True,
            )

        removed_positions = _excluded_row_positions(
            result, self.excluded_keys, self.excluded_dates
        )
        if removed_positions:
            if not result.index.is_unique:
                raise DailyPriceSourceRevisionOverlayError(
                    "每日整合已停止：排除來源日期含重複資料索引，derived CSV 未發布。"
                )
            result = result.drop(index=result.index[removed_positions])
        return result, changed_cells, len(removed_positions)


def load_daily_price_source_revisions(
    database_path: Path | str,
) -> DailyPriceSourceRevisionSet:
    """以既有 receipt loaders 驗證來源，且只載入 applied session rows。"""

    resolved_database = Path(database_path).resolve()
    try:
        price_scope = _load_revision_scope(resolved_database)
        data_root = _data_root(resolved_database)
        price_rows: Mapping[tuple[str, str], Mapping[str, object]] = {}
        price_columns: tuple[str, ...] = ()
        if price_scope is not None:
            # 既有驗證 loader 在 applied 時回傳 receipt.after；只有匹配的回復
            # receipt 存在時才回傳 receipt.before，兩者都是正式 canonical 值。
            price_rows = price_scope.canonical_rows
            price_columns = price_scope.update_columns

        session_rows: dict[tuple[str, str], Mapping[str, object]] = {}
        evidence_identities: list[Mapping[str, object]] = []
        session_evidence = False
        session_root = data_root / SESSION_RECEIPT_DIR
        if session_root.exists() or session_root.is_symlink():
            if session_root.is_symlink() or not session_root.is_dir():
                raise ValueError("歷史交易日 receipt 根目錄不是可信目錄")
            for run_dir in sorted(session_root.iterdir()):
                if run_dir.is_symlink() or not run_dir.is_dir():
                    raise ValueError("歷史交易日 receipt 目錄含未知項目")
                marker_path = run_dir / "revision.json"
                if marker_path.is_symlink() or not marker_path.is_file():
                    raise ValueError("歷史交易日 revision marker 缺失")
                marker, plan = _load_session_plan(marker_path, resolved_database)
                state = marker.get("state")
                session_evidence = True
                if state == "pending":
                    raise ValueError("歷史交易日來源修訂仍在進行")
                if state == "rolled_back":
                    continue
                if state != "applied":
                    raise ValueError("歷史交易日來源修訂狀態無效")
                evidence_identities.append(
                    {
                        "kind": "historical_session_revision",
                        "plan_sha256": marker.get("plan_sha256"),
                        "receipt_sha256": marker.get("receipt_sha256"),
                        "receipt_path": str(run_dir / "receipt.json"),
                    }
                )
                rows = plan.get("rows")
                dates = plan.get("dates")
                if not isinstance(rows, list) or not rows or not isinstance(dates, list):
                    raise ValueError("歷史交易日來源 plan 列或日期無效")
                allowed_dates = {_date_key(day) for day in dates}
                for raw_row in rows:
                    if not isinstance(raw_row, Mapping):
                        raise ValueError("歷史交易日來源 plan 含無效列")
                    key = (
                        _date_key(raw_row.get("日期")),
                        _symbol_key(raw_row.get("證券代號")),
                    )
                    if not key[1] or key[0] not in allowed_dates or key in session_rows:
                        raise ValueError("歷史交易日來源 plan 日期或股票鍵重複／越界")
                    session_rows[key] = raw_row
        from data_module.excluded_daily_price_revision import load_exclusion_evidence

        raw_exclusion_evidence = load_exclusion_evidence(resolved_database)
        excluded_keys, excluded_dates, exclusion_evidence = (
            _normalize_exclusion_evidence(raw_exclusion_evidence)
        )
        evidence_identities.extend(exclusion_evidence)
        if price_scope is not None:
            canonical_bytes = json.dumps(
                {
                    "source_date": price_scope.source_date,
                    "update_columns": price_scope.update_columns,
                    "rows": [
                        [day, symbol, dict(price_scope.canonical_rows[(day, symbol)])]
                        for day, symbol in sorted(price_scope.canonical_rows)
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
            evidence_identities.append(
                {
                    "kind": "historical_price_revision",
                    "source_date": price_scope.source_date,
                    "row_count": len(price_scope.canonical_rows),
                    "canonical_scope_sha256": hashlib.sha256(canonical_bytes).hexdigest(),
                }
            )
        return DailyPriceSourceRevisionSet(
            database_path=resolved_database,
            price_rows=price_rows,
            price_update_columns=price_columns,
            session_rows=session_rows,
            excluded_keys=frozenset(excluded_keys),
            excluded_dates=frozenset(excluded_dates),
            exclusion_evidence=tuple(exclusion_evidence),
            evidence_identities=tuple(evidence_identities),
            has_revision_evidence=(
                price_scope is not None
                or session_evidence
                or bool(exclusion_evidence)
            ),
        )
    except Exception as exc:  # noqa: BLE001 - 來源證據錯誤一律 fail closed
        raise DailyPriceSourceRevisionOverlayError(
            "每日整合已停止：來源修訂證據缺漏或無法驗證，derived CSV 未發布。"
        ) from exc


def _data_root(database_path: Path) -> Path:
    parent = database_path.parent
    return parent.parent if parent.name.casefold() == "sqlite" else parent


def _candidate_row_positions(
    frame: pd.DataFrame,
    target_dates: set[str],
) -> list[int]:
    """以常見日期 scalar 做單次 mask；未知格式會因缺少修訂 key 而 fail closed。"""

    variants: set[object] = set()
    for day in target_dates:
        year, month, date_day = int(day[:4]), day[4:6], day[6:8]
        roc_year = year - 1911
        variants.update(
            {
                day,
                int(day),
                float(day),
                f"{year:04d}-{month}-{date_day}",
                f"{year:04d}/{month}/{date_day}",
                f"{roc_year:03d}{month}{date_day}",
                int(f"{roc_year:03d}{month}{date_day}"),
            }
        )
    date_values = frame["日期"]
    candidate_mask = date_values.isin(variants)
    return candidate_mask.to_numpy().nonzero()[0].tolist()


def _normalize_exclusion_evidence(
    evidence_rows: object,
) -> tuple[
    set[tuple[str, str]],
    set[str],
    tuple[Mapping[str, object], ...],
]:
    if not isinstance(evidence_rows, list):
        raise ValueError("錯日排除來源證據格式無效")
    excluded_keys: set[tuple[str, str]] = set()
    excluded_dates: set[str] = set()
    identities: list[Mapping[str, object]] = []
    for evidence in evidence_rows:
        if not isinstance(evidence, Mapping):
            raise ValueError("錯日排除來源證據列格式無效")
        raw_keys = evidence.get("keys")
        raw_dates = evidence.get("closed_dates")
        if not isinstance(raw_keys, (list, tuple, set, frozenset)) or not isinstance(
            raw_dates, (list, tuple, set, frozenset)
        ):
            raise ValueError("錯日排除來源證據範圍無效")
        if not raw_keys and not raw_dates:
            raise ValueError("錯日排除來源證據範圍不可為空")
        for raw_date in raw_dates:
            excluded_dates.add(_date_key(raw_date))
        for raw_key in raw_keys:
            if isinstance(raw_key, Mapping):
                raw_date = raw_key.get("date", raw_key.get("日期"))
                raw_symbol = raw_key.get("symbol", raw_key.get("證券代號"))
            elif isinstance(raw_key, (list, tuple)) and len(raw_key) == 2:
                raw_date, raw_symbol = raw_key
            else:
                raise ValueError("錯日排除來源股票鍵格式無效")
            key = (_date_key(raw_date), _symbol_key(raw_symbol))
            if not key[1] or key in excluded_keys:
                raise ValueError("錯日排除來源股票鍵缺漏或重複")
            excluded_keys.add(key)
        plan_sha256 = evidence.get("plan_sha256")
        receipt_sha256 = evidence.get("receipt_sha256")
        receipt_path = evidence.get("receipt_path")
        if not all(isinstance(value, str) and value.strip() for value in (
            plan_sha256, receipt_sha256, receipt_path
        )):
            raise ValueError("錯日排除來源 receipt identity 缺漏")
        identities.append(
            {
                "kind": "excluded_daily_price_revision",
                "plan_sha256": plan_sha256,
                "receipt_sha256": receipt_sha256,
                "receipt_path": receipt_path,
                "closed_dates": sorted({_date_key(day) for day in raw_dates}),
                "key_count": len(raw_keys),
                "acquired_at": evidence.get("acquired_at"),
                "source_start_date": evidence.get("source_start_date"),
                "evidence_archive_relative": evidence.get("evidence_archive_relative"),
                "market_plan_sha256": evidence.get("market_plan_sha256"),
            }
        )
    return excluded_keys, excluded_dates, tuple(identities)


def _excluded_row_positions(
    frame: pd.DataFrame,
    excluded_keys: frozenset[tuple[str, str]],
    excluded_dates: frozenset[str],
) -> list[int]:
    if not excluded_keys and not excluded_dates:
        return []
    target_dates = set(excluded_dates)
    target_dates.update(day for day, _ in excluded_keys)
    candidate_positions = _candidate_row_positions(frame, target_dates)
    if not candidate_positions:
        return []
    candidate_rows = frame.iloc[candidate_positions][["日期", "證券代號"]]
    days = candidate_rows["日期"].map(_date_key).tolist()
    symbols = candidate_rows["證券代號"].map(_symbol_key).tolist()
    return [
        position
        for position, day, symbol in zip(
            candidate_positions, days, symbols, strict=True
        )
        if day in excluded_dates or (day, symbol) in excluded_keys
    ]


def _resolve_output_column(source_column: str, columns: pd.Index) -> str | None:
    if source_column in columns:
        return source_column
    return next(
        (
            candidate
            for candidate in _PRICE_COLUMN_ALIASES.get(source_column, ())
            if candidate in columns
        ),
        None,
    )


def _add_update(
    updates: dict[str, object], column: str, value: object
) -> None:
    if column in updates and not _values_equal(updates[column], value):
        raise DailyPriceSourceRevisionOverlayError(
            "每日整合已停止：不同來源修訂對同一欄位給出衝突值，derived CSV 未發布。"
        )
    updates[column] = value
