"""固定決策時點的唯讀 OHLCV 窗口與因果技術觀測來源。

本 adapter 只讀 ``daily_prices``，不讀 ``technical_indicators``。它保存
最多 120 列原始 OHLCV、逐列指紋與計算版本，並在明確隔離的 float 邊界呼叫
既有 ``calculate_causal_indicators``。所有進入選股規則的數值都轉為
``Decimal``；來源沒有明確 available-at 時維持 unknown，不宣稱歷史 PIT。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
import hashlib
import inspect
import json
import math
from pathlib import Path
import sqlite3
import sys
from typing import Any, Callable, Mapping, Sequence, SupportsFloat, cast
from zoneinfo import ZoneInfo

from app_module.build_identity import detect_build_identity
from app_module.daily_market_technical_read_session import (
    DAILY_MARKET_TECHNICAL_CUTOFF_GUARD_VERSION,
    DAILY_MARKET_TECHNICAL_SOURCE_MAX_ROWS,
    DailyMarketTechnicalReadSession,
)
from decision_module.factors.selection_technical_rules import (
    CAUSAL_INDICATOR_LINEAGE_METHOD_ID,
    CAUSAL_INDICATOR_LINEAGE_VERSION,
    RAW_VOLUME_LINEAGE_METHOD_ID,
    RAW_VOLUME_LINEAGE_VERSION,
    TECHNICAL_SOURCE_ID,
    VOLUME_SOURCE_ID,
    VOLUME_UNIT,
    PRICE_UNIT,
    STOCH_UNIT,
    TechnicalFeatureEvidence,
    TechnicalObservedSession,
    TechnicalObservationWindow,
    TechnicalRuleResult,
    ParameterValue,
    _KD_PARAMETERS,
    _MACD_PARAMETERS,
    _MA5_PARAMETERS,
    _MA20_PARAMETERS,
    _VOLUME_PARAMETERS,
    evaluate_daily_technical_rules,
    technical_observation_window_fingerprint_sha256,
    technical_session_fingerprint_sha256,
)


DAILY_MARKET_TECHNICAL_SOURCE_SCHEMA = "daily-market-technical-source.v1"
_TAIPEI = ZoneInfo("Asia/Taipei")
_MINIMUM_TAIPEI_RESEARCH_CUTOFF = time(16, 0)
_SOURCE_FIELDS = ("date", "stock_code", "open", "high", "low", "close", "volume_shares")
_FROZEN_BUILD_METADATA_MAX_BYTES = 64 * 1024
_FROZEN_KERNEL_RESOURCE_PATHS = (
    "analysis_module/technical_analysis/technical_indicators.py",
    "analysis_module/technical_analysis/indicator_kernels.py",
)
_OHLC_KEYS = ("open", "high", "low", "close")
_INDICATOR_FEATURES = (
    ("MA5", PRICE_UNIT, _MA5_PARAMETERS, 5),
    ("MA20", PRICE_UNIT, _MA20_PARAMETERS, 20),
    ("slowk", STOCH_UNIT, _KD_PARAMETERS, 9),
    ("slowd", STOCH_UNIT, _KD_PARAMETERS, 9),
    ("MACD", PRICE_UNIT, _MACD_PARAMETERS, 34),
    ("MACD_signal", PRICE_UNIT, _MACD_PARAMETERS, 34),
)


class DailyMarketTechnicalSourceError(ValueError):
    """來源 schema、pin 或計算契約不成立。"""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalSourceRow:
    """一列保留原始來源 token 的 OHLCV 證據。"""

    raw_date: str
    feature_date: date | None
    stock_code: str
    open_price: Decimal | None
    high_price: Decimal | None
    low_price: Decimal | None
    close_price: Decimal | None
    volume_shares: Decimal | None
    raw_values: tuple[tuple[str, str], ...]
    row_fingerprint_sha256: str
    ohlc_valid: bool
    volume_valid: bool
    invalid_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "raw_date": self.raw_date,
            "feature_date": self.feature_date.isoformat() if self.feature_date else None,
            "stock_code": self.stock_code,
            "open_price": _decimal_text(self.open_price),
            "high_price": _decimal_text(self.high_price),
            "low_price": _decimal_text(self.low_price),
            "close_price": _decimal_text(self.close_price),
            "volume_shares": _decimal_text(self.volume_shares),
            "raw_values": {name: value for name, value in self.raw_values},
            "row_fingerprint_sha256": self.row_fingerprint_sha256,
            "ohlc_valid": self.ohlc_valid,
            "volume_valid": self.volume_valid,
            "invalid_reasons": list(self.invalid_reasons),
        }


@dataclass(frozen=True, slots=True)
class DailyMarketTechnicalSourceWindow:
    """完整、有界且可核對的原始窗口與衍生規則輸入。"""

    stock_code: str
    decision_date: date
    decision_cutoff: datetime
    database_path: str
    source_id: str
    source_identity: str
    schema_identity_sha256: str
    source_file_pin: tuple[tuple[str, int, int, int, int] | tuple[str], ...]
    source_pin_sha256: str
    raw_source_window_fingerprint_sha256: str
    source_window_fingerprint_sha256: str
    calculation_identity_sha256: str
    calculation_version: str
    talib_version: str
    source_available_at: datetime | None
    availability_status: str
    observed_prefix_contiguous: bool
    rows: tuple[DailyMarketTechnicalSourceRow, ...]
    sessions: tuple[TechnicalObservedSession, ...]
    observation_window: TechnicalObservationWindow
    # 新保存版可封存計算身份原件；舊 public to_dict 保持原欄位。
    calculation_binding_json: str | None = None

    def __post_init__(self) -> None:
        if self.calculation_binding_json is not None:
            if len(self.calculation_binding_json.encode("utf-8")) > 8192:
                raise ValueError("daily_technical_calculation_binding_limit")
            binding = json.loads(self.calculation_binding_json,
                                 object_pairs_hook=_unique_json_object,
                                 parse_constant=_reject_json_constant)
            validate_daily_market_technical_calculation_binding(
                binding, expected_identity=self.calculation_identity_sha256,
                expected_talib_version=self.talib_version,
            )
            if _canonical_json(binding) != self.calculation_binding_json:
                raise ValueError("daily_technical_calculation_binding_noncanonical")
        if isinstance(self.decision_date, datetime) or not isinstance(self.decision_date, date):
            raise TypeError("decision_date 必須是 date")
        if self.decision_cutoff.utcoffset() is None:
            raise ValueError("decision_cutoff 必須是 timezone-aware datetime")
        if self.decision_cutoff.astimezone(_TAIPEI).time() < _MINIMUM_TAIPEI_RESEARCH_CUTOFF:
            raise ValueError("日線研究 cutoff 必須為台北時間 16:00 或之後")
        if not self.database_path.strip():
            raise ValueError("database_path 不可為空")
        if len(self.rows) > DAILY_MARKET_TECHNICAL_SOURCE_MAX_ROWS:
            raise ValueError("OHLCV source window 超過 120 列")
        if any(not isinstance(row, DailyMarketTechnicalSourceRow) for row in self.rows):
            raise TypeError("rows 僅能包含 DailyMarketTechnicalSourceRow")
        if any(not isinstance(item, TechnicalObservedSession) for item in self.sessions):
            raise TypeError("sessions 僅能包含 TechnicalObservedSession")
        if any(row.stock_code != self.stock_code for row in self.rows):
            raise ValueError("source rows 含其他股票")
        if any(
            row.feature_date is not None and row.feature_date > self.decision_date
            for row in self.rows
        ):
            raise ValueError("source rows 含 cutoff 之後日期")
        if self.source_id != "sqlite.daily_prices":
            raise ValueError("source_id 必須綁定 sqlite.daily_prices")
        if self.availability_status != "unknown" or self.source_available_at is not None:
            raise ValueError("此 adapter 未持有 source available-at 證據")
        if self.source_pin_sha256 != _sha256_json(_source_pin_payload(self.source_file_pin)):
            raise ValueError("source_file_pin 指紋不符")
        expected_raw_window = _sha256_json({
            "schema_version": DAILY_MARKET_TECHNICAL_SOURCE_SCHEMA,
            "schema_identity_sha256": self.schema_identity_sha256,
            "stock_code": self.stock_code,
            "decision_date": self.decision_date.isoformat(),
            "decision_cutoff": self.decision_cutoff.isoformat(),
            "cutoff_guard_version": DAILY_MARKET_TECHNICAL_CUTOFF_GUARD_VERSION,
            "rows": [row.to_dict() for row in self.rows],
        })
        if expected_raw_window != self.raw_source_window_fingerprint_sha256:
            raise ValueError("raw_source_window_fingerprint_sha256 不符")
        identity_payload = {
            "database": self.database_path,
            "source_pin_sha256": self.source_pin_sha256,
            "schema_identity_sha256": self.schema_identity_sha256,
            "stock_code": self.stock_code,
            "decision_date": self.decision_date.isoformat(),
            "decision_cutoff": self.decision_cutoff.isoformat(),
            "cutoff_guard_version": DAILY_MARKET_TECHNICAL_CUTOFF_GUARD_VERSION,
            "raw_source_window_fingerprint_sha256": self.raw_source_window_fingerprint_sha256,
            "calculation_identity_sha256": self.calculation_identity_sha256,
        }
        if self.source_identity != f"{TECHNICAL_SOURCE_ID}:{_sha256_json(identity_payload)}":
            raise ValueError("source_identity 未綁定來源、cutoff、window 與計算版本")
        if self.observation_window.stock_code != self.stock_code:
            raise ValueError("observation_window stock_code 不符")
        if (
            self.observation_window.decision_date != self.decision_date
            or self.observation_window.decision_cutoff != self.decision_cutoff
            or self.observation_window.source_identity != self.source_identity
            or self.observation_window.sessions != self.sessions
            or self.observation_window.source_window_fingerprint_sha256
            != self.source_window_fingerprint_sha256
            or self.observation_window.observed_prefix_contiguous
            != self.observed_prefix_contiguous
        ):
            raise ValueError("observation_window 與 typed source window 不一致")
        expected_rule_window = technical_observation_window_fingerprint_sha256(
            stock_code=self.stock_code,
            decision_date=self.decision_date,
            source_identity=self.source_identity,
            sessions=self.sessions,
        )
        if expected_rule_window != self.source_window_fingerprint_sha256:
            raise ValueError("source_window_fingerprint_sha256 不符")

    def evaluate(self) -> tuple[TechnicalRuleResult, ...]:
        """沿用 pure Decimal rules 對已計算的觀測窗口做三態投影。"""

        return evaluate_daily_technical_rules(self.observation_window)

    def to_dict(self) -> dict[str, object]:
        """輸出完整、有界、JSON-ready 的計算重現證據，不含裸 float。"""

        return {
            "schema_version": DAILY_MARKET_TECHNICAL_SOURCE_SCHEMA,
            "stock_code": self.stock_code,
            "decision_date": self.decision_date.isoformat(),
            "decision_cutoff": self.decision_cutoff.isoformat(),
            "cutoff_guard_version": DAILY_MARKET_TECHNICAL_CUTOFF_GUARD_VERSION,
            "database_path": self.database_path,
            "source_id": self.source_id,
            "source_identity": self.source_identity,
            "schema_identity_sha256": self.schema_identity_sha256,
            "source_file_pin": [list(item) for item in self.source_file_pin],
            "source_pin_sha256": self.source_pin_sha256,
            "raw_source_window_fingerprint_sha256": self.raw_source_window_fingerprint_sha256,
            "source_window_fingerprint_sha256": self.source_window_fingerprint_sha256,
            "calculation_identity_sha256": self.calculation_identity_sha256,
            "calculation_version": self.calculation_version,
            "talib_version": self.talib_version,
            "source_available_at": (
                self.source_available_at.isoformat() if self.source_available_at else None
            ),
            "availability_status": self.availability_status,
            "observed_prefix_contiguous": self.observed_prefix_contiguous,
            "rows": [row.to_dict() for row in self.rows],
            "sessions": [
                {
                    "stock_code": item.stock_code,
                    "feature_date": item.feature_date.isoformat(),
                    "source_identity": item.source_identity,
                    "source_fingerprint_sha256": item.source_fingerprint_sha256,
                    "pin_verified": item.pin_verified,
                    "features": [
                        _feature_json(item_feature) for item_feature in item.features
                    ],
                    "session_fingerprint_sha256": technical_session_fingerprint_sha256(item),
                }
                for item in self.sessions
            ],
            "rules": [item.to_dict() for item in self.evaluate()],
        }


def load_daily_market_technical_window(
    db_path: str | Path,
    stock_code: str,
    decision_cutoff: datetime,
    *,
    cancel_callback: Callable[[], bool] | None = None,
) -> DailyMarketTechnicalSourceWindow:
    """唯讀載入截止日 OHLCV，計算因果指標並建立 typed rule window。

    此來源只使用 ``daily_prices``。若來源未提供可驗證的發布時間，
    ``source_available_at`` 保持 None、availability 為 unknown。只接受台北時間
    16:00 或之後的日線研究 cutoff；此契約門檻不是官方收盤或來源發布證據。
    """

    if not isinstance(decision_cutoff, datetime) or decision_cutoff.utcoffset() is None:
        raise ValueError("decision_cutoff 必須是 timezone-aware datetime")
    code = str(stock_code).strip()
    if not code or not code.isalnum() or len(code) > 16:
        raise DailyMarketTechnicalSourceError("daily_technical_source_invalid_stock")
    local_cutoff = decision_cutoff.astimezone(_TAIPEI)
    if local_cutoff.time() < _MINIMUM_TAIPEI_RESEARCH_CUTOFF:
        raise DailyMarketTechnicalSourceError("daily_technical_requires_after_close_cutoff")

    with DailyMarketTechnicalReadSession(
        db_path,
        decision_cutoff,
        cancel_callback=cancel_callback,
    ) as session:
        session.load_batch((code,))
        windows = session.finish()
    if len(windows) != 1:
        raise DailyMarketTechnicalSourceError("daily_technical_read_session_result_count_invalid")
    return windows[0]


def _build_window_from_snapshot(
    *,
    database: Path,
    stock_code: str,
    decision_cutoff: datetime,
    decision_date: date,
    source_file_pin: tuple[tuple[str, int, int, int, int] | tuple[str], ...],
    source_pin_sha256: str,
    schema_identity_sha256: str,
    selected: Mapping[str, str | None],
    raw_rows: Sequence[sqlite3.Row],
    calculation_identity: tuple[str, str, str],
    calculation_binding_json: str,
) -> DailyMarketTechnicalSourceWindow:
    """由完成最終來源 pin 驗證的 SQLite 列建立不可變窗口。"""

    code = stock_code
    cutoff = decision_cutoff
    rows = _normalize_rows(raw_rows, selected, code)
    # SQLite 排序先縮到最近 120 列，再在 Python 以正規日期和原始 token
    # 排升序；重複日期仍保留，絕不去重後跨過資料缺口計算。
    rows = tuple(sorted(rows, key=lambda item: (
        item.feature_date or date.min,
        item.raw_date,
        item.raw_values,
    )))
    raw_window_fingerprint = _sha256_json({
        "schema_version": DAILY_MARKET_TECHNICAL_SOURCE_SCHEMA,
        "schema_identity_sha256": schema_identity_sha256,
        "stock_code": code,
        "decision_date": decision_date.isoformat(),
        "decision_cutoff": cutoff.isoformat(),
        "cutoff_guard_version": DAILY_MARKET_TECHNICAL_CUTOFF_GUARD_VERSION,
        "rows": [row.to_dict() for row in rows],
    })
    calculation_sha256, calculation_version, talib_version = calculation_identity
    source_identity_payload = {
        'database': str(database),
        'source_pin_sha256': source_pin_sha256,
        'schema_identity_sha256': schema_identity_sha256,
        'stock_code': code,
        'decision_date': decision_date.isoformat(),
        'decision_cutoff': cutoff.isoformat(),
        'cutoff_guard_version': DAILY_MARKET_TECHNICAL_CUTOFF_GUARD_VERSION,
        'raw_source_window_fingerprint_sha256': raw_window_fingerprint,
        'calculation_identity_sha256': calculation_sha256,
    }
    source_identity = f"{TECHNICAL_SOURCE_ID}:{_sha256_json(source_identity_payload)}"

    has_invalid_date = any(row.feature_date is None for row in rows)
    has_duplicate_date = len([row.feature_date for row in rows if row.feature_date]) != len(
        {row.feature_date for row in rows if row.feature_date}
    )
    sessions, contiguous = _calculate_sessions(
        rows,
        stock_code=code,
        source_identity=source_identity,
        source_stable=True,
        has_invalid_date=has_invalid_date,
        has_duplicate_date=has_duplicate_date,
    )
    window_fingerprint = technical_observation_window_fingerprint_sha256(
        stock_code=code,
        decision_date=decision_date,
        source_identity=source_identity,
        sessions=sessions,
    )
    observation_window = TechnicalObservationWindow(
        stock_code=code,
        decision_date=decision_date,
        decision_cutoff=cutoff,
        source_identity=source_identity,
        source_window_fingerprint_sha256=window_fingerprint,
        source_available_at=None,
        availability_status="unknown",
        sessions=sessions,
        observed_prefix_contiguous=contiguous,
    )
    return DailyMarketTechnicalSourceWindow(
        stock_code=code,
        decision_date=decision_date,
        decision_cutoff=cutoff,
        database_path=str(database),
        source_id="sqlite.daily_prices",
        source_identity=source_identity,
        schema_identity_sha256=schema_identity_sha256,
        source_file_pin=source_file_pin,
        source_pin_sha256=source_pin_sha256,
        raw_source_window_fingerprint_sha256=raw_window_fingerprint,
        source_window_fingerprint_sha256=window_fingerprint,
        calculation_identity_sha256=calculation_sha256,
        calculation_version=calculation_version,
        talib_version=talib_version,
        source_available_at=None,
        availability_status="unknown",
        observed_prefix_contiguous=contiguous,
        rows=rows,
        sessions=sessions,
        observation_window=observation_window,
        calculation_binding_json=calculation_binding_json,
    )


def _resolve_source_columns(columns: Sequence[str]) -> dict[str, str | None]:
    candidates = {
        "date": ("日期", "Date", "date", "trade_date", "trading_date"),
        "stock_code": ("證券代號", "股票代號", "stock_code", "Code", "symbol"),
        "open": ("開盤價", "Open", "open"),
        "high": ("最高價", "High", "high"),
        "low": ("最低價", "Low", "low"),
        "close": ("收盤價", "Close", "close"),
        # 不接受模糊的「成交量」alias，避免把張數當成股數。
        "volume_shares": ("成交股數", "volume_shares", "shares"),
    }
    resolved = {
        key: next((candidate for candidate in names if candidate in columns), None)
        for key, names in candidates.items()
    }
    required = ("date", "stock_code", "open", "high", "low", "close")
    missing = [key for key in required if resolved[key] is None]
    if missing:
        raise DailyMarketTechnicalSourceError(
            "daily_technical_source_schema_incompatible",
            f"daily_prices 缺少必要欄位：{', '.join(missing)}",
        )
    return resolved


def _required_column(selected: Mapping[str, str | None], key: str) -> str:
    value = selected.get(key)
    if value is None:
        raise DailyMarketTechnicalSourceError(
            "daily_technical_source_schema_incompatible",
            f"daily_prices 缺少必要欄位：{key}",
        )
    return value


def _normalize_rows(
    raw_rows: Sequence[sqlite3.Row],
    selected: Mapping[str, str | None],
    expected_stock_code: str,
) -> tuple[DailyMarketTechnicalSourceRow, ...]:
    result: list[DailyMarketTechnicalSourceRow] = []
    date_column = _required_column(selected, "date")
    stock_column = _required_column(selected, "stock_code")
    for raw in raw_rows:
        raw_map = {name: raw[name] for name in raw.keys()}
        feature_date = _parse_date(raw_map[date_column])
        raw_date_value = raw_map[date_column]
        raw_date = str(raw_date_value).strip() if raw_date_value is not None else ""
        stock_code = str(raw_map[stock_column]).strip()
        if stock_code != expected_stock_code:
            raise DailyMarketTechnicalSourceError("daily_technical_source_stock_mismatch")
        raw_values = tuple(
            (key, _raw_token(raw_map[column]) if column is not None else _raw_token(None))
            for key, column in ((key, selected.get(key)) for key in _SOURCE_FIELDS)
        )
        raw_by_key = {
            key: raw_map[column] if column is not None else None
            for key, column in selected.items()
        }
        open_price = _source_decimal(raw_by_key.get("open"))
        high_price = _source_decimal(raw_by_key.get("high"))
        low_price = _source_decimal(raw_by_key.get("low"))
        close_price = _source_decimal(raw_by_key.get("close"))
        volume = _source_volume(raw_by_key.get("volume_shares"))
        reasons: list[str] = []
        if feature_date is None:
            reasons.append("source_date_invalid")
        values = (open_price, high_price, low_price, close_price)
        if any(value is None for value in values):
            reasons.append("ohlc_value_missing_or_invalid")
        ohlc_valid = all(value is not None and value.is_finite() and value > 0 for value in values)
        if ohlc_valid:
            assert open_price is not None and high_price is not None
            assert low_price is not None and close_price is not None
            ohlc_valid = (
                low_price <= min(open_price, close_price)
                and high_price >= max(open_price, close_price)
            )
            if not ohlc_valid:
                reasons.append("ohlc_range_invalid")
        if raw_by_key.get("volume_shares") is None or volume is None:
            reasons.append("volume_shares_missing_or_invalid")
        row_payload = {
            "stock_code": stock_code,
            "feature_date": feature_date.isoformat() if feature_date else None,
            "raw_values": {key: value for key, value in raw_values},
        }
        result.append(DailyMarketTechnicalSourceRow(
            raw_date=raw_date,
            feature_date=feature_date,
            stock_code=stock_code,
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            close_price=close_price,
            volume_shares=volume,
            raw_values=raw_values,
            row_fingerprint_sha256=_sha256_json(row_payload),
            ohlc_valid=bool(ohlc_valid),
            volume_valid=volume is not None,
            invalid_reasons=tuple(dict.fromkeys(reasons)),
        ))
    return tuple(result)


def _calculate_sessions(
    rows: tuple[DailyMarketTechnicalSourceRow, ...],
    *,
    stock_code: str,
    source_identity: str,
    source_stable: bool,
    has_invalid_date: bool,
    has_duplicate_date: bool,
) -> tuple[tuple[TechnicalObservedSession, ...], bool]:
    if not rows:
        return (), False
    dates = [row.feature_date for row in rows]
    valid_dates = [item for item in dates if item is not None]
    if (
        has_invalid_date
        or has_duplicate_date
        or len(valid_dates) != len(dates)
        or valid_dates != sorted(valid_dates)
    ):
        return _unknown_sessions(rows, stock_code, source_identity, source_stable), False

    import numpy as np
    import pandas as pd

    frame_rows: list[dict[str, object]] = []
    for row in rows:
        frame_row: dict[str, object] = {
            "日期": row.feature_date.isoformat() if row.feature_date else "",
            "證券代號": stock_code,
        }
        ohlc_values = (
            ("開盤價", row.open_price),
            ("最高價", row.high_price),
            ("最低價", row.low_price),
            ("收盤價", row.close_price),
        )
        for field_name, value in ohlc_values:
            if not row.ohlc_valid or value is None:
                frame_row[field_name] = np.nan
                continue
            try:
                numeric_value = float(value)
            except (OverflowError, ValueError):
                numeric_value = math.nan
            if not math.isfinite(numeric_value) or numeric_value <= 0:
                frame_row[field_name] = np.nan
            else:
                frame_row[field_name] = numeric_value
        frame_rows.append(frame_row)
    frame = pd.DataFrame.from_records(frame_rows)
    calculation_ok = all(row.feature_date is not None for row in rows)
    calculated: Any = None
    if calculation_ok:
        try:
            calculated = _run_causal_calculation(frame)
        except Exception as exc:
            raise DailyMarketTechnicalSourceError(
                "daily_technical_causal_calculation_failed", str(exc)
            ) from exc
    if calculated is None or len(calculated) != len(rows):
        raise DailyMarketTechnicalSourceError("daily_technical_causal_output_invalid")
    required_columns = {item[0] for item in _INDICATOR_FEATURES}
    if not required_columns <= set(calculated.columns):
        raise DailyMarketTechnicalSourceError("daily_technical_causal_columns_missing")

    # 完整原始窗口保留在 ``rows``；只有連續有效的 OHLC 尾段會成為 sessions。
    # 無效列仍以 NaN 傳入 kernel 並重設暖機區段，不會直接略過。
    suffix_start = len(rows)
    for index in range(len(rows) - 1, -1, -1):
        if not rows[index].ohlc_valid:
            break
        suffix_start = index
    suffix_rows = rows[suffix_start:]
    suffix_indices = range(suffix_start, len(rows))
    observations: list[TechnicalObservedSession] = []
    for index, row in zip(suffix_indices, suffix_rows, strict=True):
        if row.feature_date is None:
            continue
        valid_count = index - suffix_start + 1
        feature_values = calculated.iloc[index]
        features = tuple(
            _indicator_evidence(
                key=key,
                unit=unit,
                parameters=parameters,
                required_warmup=required_warmup,
                warmup_observed=valid_count,
                row=row,
                raw_value=feature_values[key],
                source_stable=source_stable,
                calculation_valid=row.ohlc_valid,
            )
            for key, unit, parameters, required_warmup in _INDICATOR_FEATURES
        ) + (_volume_evidence(row, source_stable=source_stable),)
        observations.append(TechnicalObservedSession(
            stock_code=stock_code,
            feature_date=row.feature_date,
            source_identity=source_identity,
            source_fingerprint_sha256=row.row_fingerprint_sha256,
            features=features,
            pin_verified=source_stable,
        ))
    contiguous = bool(observations) and all(row.ohlc_valid for row in suffix_rows)
    return tuple(observations), contiguous


def _unknown_sessions(
    rows: tuple[DailyMarketTechnicalSourceRow, ...],
    stock_code: str,
    source_identity: str,
    source_stable: bool,
) -> tuple[TechnicalObservedSession, ...]:
    sessions: list[TechnicalObservedSession] = []
    for row in rows:
        if row.feature_date is None:
            continue
        features = tuple(
            _unknown_indicator_evidence(
                key=key,
                unit=unit,
                parameters=parameters,
                required_warmup=required_warmup,
                row=row,
                source_stable=source_stable,
            )
            for key, unit, parameters, required_warmup in _INDICATOR_FEATURES
        ) + (_volume_evidence(row, source_stable=source_stable),)
        sessions.append(TechnicalObservedSession(
            stock_code=stock_code,
            feature_date=row.feature_date,
            source_identity=source_identity,
            source_fingerprint_sha256=row.row_fingerprint_sha256,
            features=features,
            pin_verified=source_stable,
        ))
    return tuple(sessions)


def _indicator_evidence(
    *,
    key: str,
    unit: str,
    parameters: tuple[tuple[str, ParameterValue], ...],
    required_warmup: int,
    warmup_observed: int,
    row: DailyMarketTechnicalSourceRow,
    raw_value: object,
    source_stable: bool,
    calculation_valid: bool,
) -> TechnicalFeatureEvidence:
    value = _finite_decimal(raw_value)
    observed = value is not None and calculation_valid
    return TechnicalFeatureEvidence(
        key=key,
        value=value if observed else None,
        unit=unit,
        state="observed" if observed else "unknown",
        source_id=TECHNICAL_SOURCE_ID,
        source_fingerprint_sha256=row.row_fingerprint_sha256,
        method_id=CAUSAL_INDICATOR_LINEAGE_METHOD_ID,
        method_version=CAUSAL_INDICATOR_LINEAGE_VERSION,
        parameters=parameters,
        lineage_verified=bool(source_stable and calculation_valid),
        warmup_required_sessions=required_warmup,
        warmup_observed_sessions=warmup_observed,
        warmup_contiguous=bool(calculation_valid and warmup_observed >= required_warmup),
    )


def _unknown_indicator_evidence(
    *,
    key: str,
    unit: str,
    parameters: tuple[tuple[str, ParameterValue], ...],
    required_warmup: int,
    row: DailyMarketTechnicalSourceRow,
    source_stable: bool,
) -> TechnicalFeatureEvidence:
    return TechnicalFeatureEvidence(
        key=key,
        value=None,
        unit=unit,
        state="unknown",
        source_id=TECHNICAL_SOURCE_ID,
        source_fingerprint_sha256=row.row_fingerprint_sha256,
        method_id=CAUSAL_INDICATOR_LINEAGE_METHOD_ID,
        method_version=CAUSAL_INDICATOR_LINEAGE_VERSION,
        parameters=parameters,
        lineage_verified=False,
        warmup_required_sessions=required_warmup,
        warmup_observed_sessions=0,
        warmup_contiguous=False,
    )


def _volume_evidence(
    row: DailyMarketTechnicalSourceRow, *, source_stable: bool
) -> TechnicalFeatureEvidence:
    return TechnicalFeatureEvidence(
        key="volume_shares",
        value=row.volume_shares if row.volume_valid else None,
        unit=VOLUME_UNIT,
        state="observed" if row.volume_valid else "unknown",
        source_id=VOLUME_SOURCE_ID,
        source_fingerprint_sha256=row.row_fingerprint_sha256,
        method_id=RAW_VOLUME_LINEAGE_METHOD_ID,
        method_version=RAW_VOLUME_LINEAGE_VERSION,
        parameters=_VOLUME_PARAMETERS,
        lineage_verified=bool(source_stable and row.volume_valid),
    )


def _run_causal_calculation(frame: Any) -> Any:
    """直接呼叫純記憶體 kernel，不修改程序環境或建立額外輸出。"""

    from analysis_module.technical_analysis.technical_indicators import (
        calculate_causal_indicators,
    )

    return calculate_causal_indicators(frame)


def _calculation_identity() -> tuple[str, str, str]:
    payload = _calculation_binding_payload()
    return _sha256_json(payload), CAUSAL_INDICATOR_LINEAGE_VERSION, str(payload["talib_version"])


def _calculation_binding_payload() -> dict[str, Any]:
    """取得本次計算身份的原 payload，不替舊來源補推版本。"""
    import numpy as np
    import pandas as pd
    import talib

    if bool(getattr(sys, "frozen", False)):
        module_sha, helper_sha = _frozen_calculation_source_hashes()
    else:
        from analysis_module.technical_analysis import technical_indicators

        module_path = Path(inspect.getfile(technical_indicators.calculate_causal_indicators))
        helper_path = module_path.parent / "indicator_kernels.py"
        try:
            module_sha = _sha256_bytes(module_path.read_bytes())
            helper_sha = _sha256_bytes(helper_path.read_bytes())
        except OSError as exc:
            raise DailyMarketTechnicalSourceError(
                "daily_technical_kernel_source_unavailable", str(exc)
            ) from exc
    talib_version = str(getattr(talib, "__version__", "unknown"))
    calculation_payload = {
        "method_id": CAUSAL_INDICATOR_LINEAGE_METHOD_ID,
        "method_version": CAUSAL_INDICATOR_LINEAGE_VERSION,
        "technical_indicators_module_sha256": module_sha,
        "indicator_kernels_module_sha256": helper_sha,
        "talib_version": talib_version,
        "numpy_version": str(np.__version__),
        "pandas_version": str(pd.__version__),
        "parameters": {
            "MA5": _parameter_dict(_MA5_PARAMETERS),
            "MA20": _parameter_dict(_MA20_PARAMETERS),
            "STOCH_5_3_3": _parameter_dict(_KD_PARAMETERS),
            "MACD_12_26_9": _parameter_dict(_MACD_PARAMETERS),
        },
    }
    return calculation_payload


def validate_daily_market_technical_calculation_binding(
    value: object, *, expected_identity: str, expected_talib_version: str,
) -> dict[str, Any]:
    """只核保存的計算契約與 SHA；讀回時不重讀現行 kernel 或套件。"""
    keys = {"method_id", "method_version", "technical_indicators_module_sha256",
            "indicator_kernels_module_sha256", "talib_version", "numpy_version",
            "pandas_version", "parameters"}
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("daily_technical_calculation_binding_invalid")
    if (value["method_id"] != CAUSAL_INDICATOR_LINEAGE_METHOD_ID
            or value["method_version"] != CAUSAL_INDICATOR_LINEAGE_VERSION):
        raise ValueError("daily_technical_calculation_binding_method_mismatch")
    for key in ("technical_indicators_module_sha256", "indicator_kernels_module_sha256"):
        token = value[key]
        if (not isinstance(token, str) or len(token) != 64
                or any(char not in "0123456789abcdef" for char in token)):
            raise ValueError("daily_technical_calculation_binding_kernel_invalid")
    for key in ("talib_version", "numpy_version", "pandas_version"):
        token = value[key]
        if (not isinstance(token, str) or not token or token != token.strip()
                or len(token.encode("utf-8")) > 128 or token.casefold() == "unknown"):
            raise ValueError("daily_technical_calculation_binding_version_invalid")
    expected_parameters = {
        "MA5": _parameter_dict(_MA5_PARAMETERS), "MA20": _parameter_dict(_MA20_PARAMETERS),
        "STOCH_5_3_3": _parameter_dict(_KD_PARAMETERS),
        "MACD_12_26_9": _parameter_dict(_MACD_PARAMETERS),
    }
    # JSON 正規字串比較同時拒絕 bool/float 冒用同值整數參數。
    if _canonical_json(value["parameters"]) != _canonical_json(expected_parameters):
        raise ValueError("daily_technical_calculation_binding_parameters_mismatch")
    if value["talib_version"] != expected_talib_version or _sha256_json(value) != expected_identity:
        raise ValueError("daily_technical_calculation_binding_identity_mismatch")
    return value


def _frozen_calculation_source_hashes() -> tuple[str, str]:
    """以 frozen bundle 的 metadata 和原始 kernel bytes 建立計算來源身分。"""

    frozen_root_value = getattr(sys, "_MEIPASS", None)
    if frozen_root_value is None:
        raise DailyMarketTechnicalSourceError("daily_technical_frozen_root_unavailable")
    try:
        frozen_root = Path(frozen_root_value)
        if not frozen_root.is_absolute():
            raise ValueError("_MEIPASS 必須是絕對路徑")
        frozen_root = frozen_root.resolve()
        if not frozen_root.is_dir():
            raise ValueError("_MEIPASS 必須是目錄")
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalSourceError(
            "daily_technical_frozen_root_unavailable", str(exc)
        ) from exc

    metadata_path = frozen_root / "application_build.json"
    try:
        resolved_metadata_path = metadata_path.resolve()
        resolved_metadata_path.relative_to(frozen_root)
        if not resolved_metadata_path.is_file():
            raise ValueError("application_build.json 必須是檔案")
        if resolved_metadata_path.stat().st_size > _FROZEN_BUILD_METADATA_MAX_BYTES:
            raise ValueError("application_build.json 超過大小上限")
        metadata_bytes = resolved_metadata_path.read_bytes()
        if len(metadata_bytes) > _FROZEN_BUILD_METADATA_MAX_BYTES:
            raise ValueError("application_build.json 超過大小上限")
        metadata_payload = json.loads(
            metadata_bytes.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, RuntimeError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalSourceError(
            "daily_technical_frozen_build_identity_unverified", str(exc)
        ) from exc

    if not isinstance(metadata_payload, dict):
        raise DailyMarketTechnicalSourceError(
            "daily_technical_frozen_build_identity_unverified"
        )
    resource_manifest = metadata_payload.get("resource_sha256")
    if not isinstance(resource_manifest, dict):
        raise DailyMarketTechnicalSourceError(
            "daily_technical_frozen_build_identity_unverified"
        )
    expected_hashes: list[str] = []
    for relative_path in _FROZEN_KERNEL_RESOURCE_PATHS:
        expected_hash = resource_manifest.get(relative_path)
        if not _is_lowercase_sha256(expected_hash):
            raise DailyMarketTechnicalSourceError(
                "daily_technical_frozen_kernel_hash_missing"
            )
        expected_hashes.append(cast(str, expected_hash))

    try:
        build_identity = detect_build_identity(
            repository_root=frozen_root,
            metadata_path=resolved_metadata_path,
            frozen=True,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise DailyMarketTechnicalSourceError(
            "daily_technical_frozen_build_identity_unverified", str(exc)
        ) from exc
    if (
        build_identity.channel != "release"
        or build_identity.dirty is not False
        or build_identity.source_commit == "unknown"
    ):
        raise DailyMarketTechnicalSourceError(
            "daily_technical_frozen_build_identity_unverified"
        )

    actual_hashes: list[str] = []
    for relative_path, expected_hash in zip(
        _FROZEN_KERNEL_RESOURCE_PATHS, expected_hashes, strict=True
    ):
        source_path = frozen_root / Path(relative_path)
        try:
            resolved_source_path = source_path.resolve()
            resolved_source_path.relative_to(frozen_root)
            if not resolved_source_path.is_file():
                raise ValueError("frozen kernel source 必須是檔案")
            source_bytes = resolved_source_path.read_bytes()
        except (OSError, RuntimeError, ValueError) as exc:
            raise DailyMarketTechnicalSourceError(
                "daily_technical_frozen_kernel_source_unverified", str(exc)
            ) from exc
        actual_hash = _sha256_bytes(source_bytes)
        if actual_hash != expected_hash:
            raise DailyMarketTechnicalSourceError(
                "daily_technical_frozen_kernel_hash_mismatch"
            )
        actual_hashes.append(actual_hash)

    try:
        if resolved_metadata_path.read_bytes() != metadata_bytes:
            raise ValueError("application_build.json 在驗證期間已變更")
    except (OSError, ValueError) as exc:
        raise DailyMarketTechnicalSourceError(
            "daily_technical_frozen_build_identity_unverified", str(exc)
        ) from exc

    return actual_hashes[0], actual_hashes[1]


def _is_lowercase_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("application_build.json 不可包含重複鍵")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"application_build.json 不支援 JSON 常數：{value}")


def _source_pin(path: Path) -> tuple[tuple[str, int, int, int, int] | tuple[str], ...] | None:
    pins: list[tuple[str, int, int, int, int] | tuple[str]] = []
    for candidate in (path, Path(str(path) + "-wal")):
        try:
            stat = candidate.stat()
        except FileNotFoundError:
            pins.append((str(candidate),))
        except OSError:
            return None
        else:
            pins.append((str(candidate), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns))
    return tuple(pins)


def _source_pin_payload(
    value: tuple[tuple[str, int, int, int, int] | tuple[str], ...]
) -> list[list[object]]:
    return [list(item) for item in value]


def _parse_date(value: object) -> date | None:
    if isinstance(value, datetime):
        if value.utcoffset() is not None:
            return value.astimezone(_TAIPEI).date()
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value or "").strip()
    if not raw:
        return None

    if len(raw) == 8 and raw.isascii() and raw.isdigit():
        try:
            return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
        except ValueError:
            return None

    if len(raw) < 10 or raw[4] not in ("-", "/") or raw[7] != raw[4]:
        return None
    date_token = raw[:10]
    if not (
        date_token[:4].isascii()
        and date_token[:4].isdigit()
        and date_token[5:7].isascii()
        and date_token[5:7].isdigit()
        and date_token[8:10].isascii()
        and date_token[8:10].isdigit()
    ):
        return None
    normalized_date = date_token.replace("/", "-")
    if len(raw) == 10:
        try:
            return date.fromisoformat(normalized_date)
        except ValueError:
            return None
    if raw[10] not in ("T", " "):
        return None
    try:
        parsed = datetime.fromisoformat(
            normalized_date + raw[10:].replace("Z", "+00:00")
        )
    except ValueError:
        return None
    if parsed.utcoffset() is not None:
        return parsed.astimezone(_TAIPEI).date()
    return parsed.date()


def _sqlite_date_key(value: object) -> str | None:
    parsed = _parse_date(value)
    return parsed.strftime("%Y%m%d") if parsed is not None else None


def _source_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        result = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _source_volume(value: object) -> Decimal | None:
    # SQLite INTEGER 與整數文字代表精確股數。REAL 值直接拒絕，避免四捨五入後
    # 被當成整數成交量觀測。
    if isinstance(value, bool) or isinstance(value, float):
        return None
    decimal_value = _source_decimal(value)
    if (
        decimal_value is None
        or decimal_value < 0
        or decimal_value != decimal_value.to_integral_value()
    ):
        return None
    return decimal_value


def _finite_decimal(value: object) -> Decimal | None:
    try:
        # 既有 TA-Lib/pandas kernel 會回傳 numpy scalar；此處是隔離的輸出邊界。
        # 先轉成有限文字再建立 Decimal，Decimal 規則層不會接收 float。
        numeric = float(cast(SupportsFloat, value))
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(numeric):
        return None
    try:
        result = Decimal(str(numeric))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _raw_token(value: object) -> str:
    if value is None:
        payload: object = {"type": "null", "value": None}
    elif isinstance(value, bytes):
        payload = {"type": "bytes", "hex": value.hex()}
    elif isinstance(value, float):
        payload = {"type": "float", "value": repr(value)}
    elif isinstance(value, (int, str)):
        payload = {"type": type(value).__name__, "value": value}
    else:
        payload = {"type": type(value).__name__, "value": str(value)}
    return _canonical_json(payload)


def _feature_json(feature: TechnicalFeatureEvidence) -> dict[str, object]:
    return {
        "key": feature.key,
        "value": _decimal_text(feature.value),
        "unit": feature.unit,
        "state": feature.state,
        "source_id": feature.source_id,
        "source_fingerprint_sha256": feature.source_fingerprint_sha256,
        "method_id": feature.method_id,
        "method_version": feature.method_version,
        "parameters": _parameter_dict(feature.parameters),
        "lineage_verified": feature.lineage_verified,
        "warmup_required_sessions": feature.warmup_required_sessions,
        "warmup_observed_sessions": feature.warmup_observed_sessions,
        "warmup_contiguous": feature.warmup_contiguous,
    }


def _parameter_dict(parameters: Sequence[tuple[str, object]]) -> dict[str, object]:
    return {
        key: _decimal_text(value) if isinstance(value, Decimal) else value
        for key, value in parameters
    }


def _decimal_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_json(value: object) -> str:
    return _sha256_bytes(_canonical_json(value).encode("utf-8"))


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
