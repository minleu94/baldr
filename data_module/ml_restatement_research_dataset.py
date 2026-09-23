"""建立價格修訂後、僅供研究的 portfolio-ML 數值資料集。

Direct OOC 的 row key 與目標矩陣是唯讀基線；特徵及四個 horizon 標籤從
修訂後 SQLite 完整重算。產物明確標為 restated research，不能冒充 historical
PIT 或 formal OOS。金融標籤使用 Decimal 與整數 bp。
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from time import perf_counter
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

SUPPORTED_HORIZONS = (5, 10, 20, 60)
LABEL_FIELDS = (
    "benchmark_excess_return_bp", "sector_excess_return_bp",
    "downside_observed", "mae_bp", "mfe_bp", "realized_volatility_bp",
    "max_drawdown_bp", "tail_loss_bp", "fill_feasible_observed",
)
TARGET_FIELDS = (
    "target_weight_bp", "delta_weight_bp", "risk_contribution_bp",
    "risky_budget_bp", "cash_bp", "rebalance_worthwhile",
)
TECHNICAL_FIELDS = (
    "SMA30", "DEMA30", "EMA30", "MA5", "MA10", "MA20", "MA60", "RSI",
    "MACD", "MACD_signal", "MACD_hist", "slowk", "slowd", "middleband",
    "upperband", "lowerband", "SAR", "TSF", "ATR", "ADX",
)
_TAIPEI = ZoneInfo("Asia/Taipei")
_DECISION_TIME = time(8, 30)
_CLOSE_TIME = time(14, 30)
_BUY_COST_BP = 25
_SELL_COST_BP = 55
_COST_LANE = "tw-equity-roundtrip-v1:buy=25bp;sell=55bp"
_SOURCE_DB = Path(r"D:\Min\Python\Project\FA_Data\output\research_only\non_release\price_revision_rebuild_20260922_luna\revision_20260922_run02\inputs\twstock_snapshot_run02.db")
_DIRECT_MANIFEST = Path(r"D:\Min\Python\Project\FA_Data\output\release_v4\portfolio_ml_direct_numeric_production_v4_v2\runs\direct-ooc-505c6adaf3f71a0c8f0a274e\manifest.json")
_CA_MANIFEST = Path(r"D:\Min\Python\Project\FA_Data\output\release_v4\corporate_action_adjustments\runs\corporate-action-adjustments-1f167a302bb6acd17349502f\manifest.json")
_DEFAULT_OUTPUT = Path(r"E:\codex_model_repair_20260923\dataset")
_TRANSFER_RECEIPT = Path(r"D:\Min\Python\Project\FA_Data\output\research_only\non_release\price_revision_rebuild_20260922_luna\transfer_receipt.json")
_EXPECTED_SNAPSHOT_SHA = "sha256:38ab1d1dfd201285ed817c8e94f689f91a50b39dc30cdbb8a90a49b7ce898771"
_EXPECTED_DIRECT_MANIFEST_SHA = "sha256:61d806ef005d0881911201104079c1acc92826a26bd8a331b9bd79156983ffe8"
_EXPECTED_TRANSFER_RECEIPT_SHA = "sha256:c0e0cb823d172c052db201351d7db0dc3d170f6b436003d37d4815ce28015fe4"


def expected_feature_contract() -> tuple[tuple[str, ...], tuple[int, ...]]:
    quality = tuple(
        f"data_quality.{family}.{metric}"
        for family in ("market_sector_cross_section", "price_liquidity_technical")
        for metric in ("coverage_bp", "max_available_lag_days", "missing_count", "quality_blocked_count", "stale_count")
    )
    features = quality + (
        "industry_indices.收盤指數", "industry_indices.漲跌百分比", "industry_indices.漲跌點數",
        "market_indices.成交量", "market_indices.收盤價", "market_indices.收盤指數",
        "market_indices.最低價", "market_indices.最高價", "market_indices.漲跌百分比",
        "market_indices.漲跌點數", "market_indices.開盤價",
        "daily_prices.成交筆數", "daily_prices.成交股數", "daily_prices.成交金額",
        "daily_prices.收盤價", "daily_prices.最低價", "daily_prices.最後揭示買價",
        "daily_prices.最後揭示買量", "daily_prices.最後揭示賣價", "daily_prices.最後揭示賣量",
        "daily_prices.最高價", "daily_prices.本益比", "daily_prices.漲跌價差", "daily_prices.開盤價",
        *(f"technical_indicators.{name}" for name in (
            "ADX", "ATR", "DEMA30", "EMA30", "MA10", "MA20", "MA5", "MA60",
            "MACD", "MACD_hist", "MACD_signal", "RSI", "SAR", "SMA30", "TSF",
            "lowerband", "middleband", "slowd", "slowk", "upperband",
        )),
        "technical_indicators.最後揭示買價", "technical_indicators.最後揭示買量",
        "technical_indicators.最後揭示賣價", "technical_indicators.最後揭示賣量",
        "technical_indicators.本益比", "technical_indicators.涨跌",
        "technical_indicators.漲跌(+/-)", "technical_indicators.漲跌價差",
    )
    scales = (
        (1,) * 10
        + (10_000, 10_000, 10_000, 1, 10_000, 10_000, 10_000, 10_000, 10_000, 10_000, 10_000)
        + (1, 1, 1, 10_000, 10_000, 10_000, 1, 10_000, 1, 10_000, 10_000, 10_000, 10_000)
        + (10_000,) * 20
        + (10_000, 1, 10_000, 1, 10_000, 10_000, 10_000, 10_000)
    )
    return features, scales


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _iso_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").date()
    return date.fromisoformat(text[:10])


def _get(row: Mapping[str, Any], name: str, default: Any = None) -> Any:
    try:
        return row[name]
    except (KeyError, IndexError):
        return default


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value).strip())
    except Exception:
        return None
    return result if result.is_finite() else None


def _scaled(value: Any, scale: int) -> int | None:
    number = _decimal(value)
    if number is None:
        return None
    return int((number * Decimal(scale)).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))


_POSITIVE_PRICE_FEATURES = frozenset({
    14, 15, 16, 17, 20, 24, 25, 28, 30, 33,
    36, 37, 38, 39, 40, 41, 46, 47, 48, 49, 50, 53, 56, 58,
})


def _feature_eligibility(value: Any, index: int, scale: int, age_days: int) -> tuple[int | None, bool, bool]:
    """Return scaled value, stale flag and quality-blocked flag for one base feature."""
    if value is None:
        return None, False, False
    number = _scaled(value, scale)
    if number is None or (index in _POSITIVE_PRICE_FEATURES and number <= 0):
        return None, False, True
    if age_days > 7:
        return None, True, False
    return number, False, False


def _aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("revision_observed_at must include an offset")
    return parsed.astimezone(_TAIPEI)


def _scaled_price(value: Any) -> int | None:
    return _scaled(value, 10_000)


def _bp_return(entry: Decimal, exit_value: Decimal) -> int:
    if entry <= 0:
        raise ValueError("entry price must be positive")
    value = ((exit_value / entry) - Decimal(1)) * Decimal(10_000)
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))


def _series_metrics(entry: Decimal, path: Sequence[Mapping[str, Any]]) -> tuple[int, int, int, int, int]:
    closes = [row["close"] for row in path]
    mae = max(0, -_bp_return(entry, min(row["low"] for row in path)))
    mfe = min(10_000, max(0, _bp_return(entry, max(row["high"] for row in path))))
    close_returns = [_bp_return(left, right) for left, right in zip(closes, closes[1:])]
    if len(close_returns) < 2:
        volatility = 0
    else:
        count = Decimal(len(close_returns))
        mean = sum((Decimal(value) for value in close_returns), Decimal(0)) / count
        variance = sum(((Decimal(value) - mean) ** 2 for value in close_returns), Decimal(0)) / count
        volatility = min(10_000, max(0, int(variance.sqrt().quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))))
    peak = closes[0]
    max_drawdown = 0
    for close in closes:
        peak = max(peak, close)
        if peak > 0:
            value = ((peak - close) / peak) * Decimal(10_000)
            max_drawdown = max(max_drawdown, int(value.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)))
    if close_returns:
        ordered = sorted(close_returns)
        count = max(1, (len(ordered) + 4) // 5)
        tail_mean = sum((Decimal(value) for value in ordered[:count]), Decimal(0)) / Decimal(count)
        tail_loss = min(10_000, max(0, int((-tail_mean).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))))
    else:
        tail_loss = 10_000
    return mae, mfe, volatility, min(10_000, max_drawdown), tail_loss


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class DatasetContract:
    feature_ids: tuple[str, ...]
    feature_scales: tuple[int, ...]
    feature_packs: tuple[Mapping[str, Any], ...]
    folds: tuple[Mapping[str, Any], ...]
    years: tuple[Mapping[str, Any], ...]
    direct_manifest_hash: str
    direct_manifest_file_hash: str
    feature_registry_hash: str
    discovery_cache_hash: str
    row_count: int


def load_contract(manifest_path: Path) -> DatasetContract:
    manifest = _read_json(manifest_path)
    ids = tuple(str(value) for value in manifest["feature_ids"])
    scales = tuple(int(value) for value in manifest["feature_scales"])
    if len(ids) != 62 or len(scales) != 62 or len(set(ids)) != 62:
        raise ValueError("Direct manifest must define exactly 62 unique ordered features")
    expected_ids, expected_scales = expected_feature_contract()
    if ids != expected_ids or scales != expected_scales:
        raise ValueError("Direct wire feature order/scales do not match the audited 62-slot ABI")
    discovery_path = manifest_path.parent / "discovery_cache.json"
    discovery = _read_json(discovery_path)
    definitions = discovery["discovery"]["definitions"]
    stale = [int(row["stale_after_days"]) for row in definitions]
    if len(stale) != 52 or any(value != 7 for value in stale):
        raise ValueError("Direct discovery cache stale-after contract changed")
    packs = tuple(manifest.get("feature_packs", ()))
    covered = [feature for pack in packs for feature in pack.get("feature_ids", ())]
    if packs and (len(covered) != 62 or set(covered) != set(ids)):
        raise ValueError("feature_packs do not uniquely cover all 62 features")
    return DatasetContract(
        ids, scales, packs, tuple(manifest["folds"]), tuple(manifest["years"]),
        str(manifest.get("manifest_hash", "")), sha256_file(manifest_path),
        str(manifest.get("feature_registry_hash", "")), sha256_file(discovery_path),
        int(manifest["row_count"]),
    )


def arrow_schema(feature_count: int = 62):
    import pyarrow as pa

    fields = [
        pa.field("row_id", pa.string(), nullable=False),
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("decision_date", pa.date32(), nullable=False),
        pa.field("decision_at", pa.string(), nullable=False),
        pa.field("local_row_index", pa.int32()),
        pa.field("fold_role", pa.string(), nullable=False),
        pa.field("fold_ids", pa.list_(pa.string()), nullable=False),
        pa.field("calendar_basis", pa.string(), nullable=False),
        pa.field("stock_event_date", pa.date32()),
        pa.field("market_event_date", pa.date32()),
        pa.field("feature_event_asof_at", pa.string()),
        pa.field("feature_available_at", pa.string(), nullable=False),
        pa.field("revision_observed_at", pa.string(), nullable=False),
        pa.field("source_revision_id", pa.string(), nullable=False),
        pa.field("feature_lineage_hash", pa.string(), nullable=False),
        pa.field("features_scaled_i64", pa.list_(pa.int64(), feature_count), nullable=False),
        pa.field("feature_missing_mask", pa.list_(pa.uint8(), feature_count), nullable=False),
        pa.field("target_values_i32", pa.list_(pa.int32(), len(TARGET_FIELDS)), nullable=False),
        pa.field("target_missing_mask", pa.list_(pa.uint8(), len(TARGET_FIELDS)), nullable=False),
    ]
    for horizon in SUPPORTED_HORIZONS:
        fields.extend([
            pa.field(f"label_end_date_h{horizon}", pa.date32()),
            pa.field(f"maturity_at_h{horizon}", pa.string()),
            pa.field(f"labels_h{horizon}_i64", pa.list_(pa.int64(), len(LABEL_FIELDS)), nullable=False),
            pa.field(f"labels_h{horizon}_missing_mask", pa.list_(pa.uint8(), len(LABEL_FIELDS)), nullable=False),
            pa.field(f"label_basis_h{horizon}", pa.string()),
        ])
    return pa.schema(fields)


def _fixed_array(values: np.ndarray, masks: np.ndarray, width: int, value_type: Any):
    import pyarrow as pa

    flat_values = np.asarray(values).reshape(-1)
    flat_masks = np.asarray(masks).reshape(-1).astype(bool, copy=False)
    child = pa.array(flat_values, type=value_type, mask=flat_masks)
    return pa.FixedSizeListArray.from_arrays(child, width)


def _rss_bytes() -> int | None:
    try:
        import psutil
        return int(psutil.Process().memory_info().rss)
    except Exception:
        return None


def build_restated_feature_values(
    *, decision: date, stock: pd.DataFrame, dates: Sequence[date],
    raw_rows: Sequence[Mapping[str, Any]], market_dates: Sequence[date],
    market_rows: Mapping[date, Mapping[str, Any]], feature_scales: Sequence[int],
) -> tuple[list[int], list[int], date | None, date | None]:
    """只消費已固定的歷史前綴，以原 62 欄尺度計算當次特徵；無 I/O。"""
    if tuple(feature_scales) != expected_feature_contract()[1]:
        raise ValueError("restated feature scales differ from the fixed contract")
    stock_idx = bisect_left(dates, decision) - 1
    stock_day = dates[stock_idx] if stock_idx >= 0 else None
    market_idx = bisect_left(market_dates, decision) - 1
    market_day = market_dates[market_idx] if market_idx >= 0 else None
    values: list[Any] = [None] * 62
    # 缺少歷史產業歸屬證據，三個產業特徵保持缺值。
    if market_day is not None:
        market = market_rows[market_day]
        values[13:21] = [
            market.get("成交量"), market.get("收盤價"), market.get("收盤指數"),
            market.get("最低價"), market.get("最高價"), market.get("漲跌百分比"),
            market.get("漲跌點數"), market.get("開盤價"),
        ]
    if stock_idx >= 0:
        raw = raw_rows[stock_idx]
        technical = stock.iloc[stock_idx]
        values[21:34] = [
            raw.get("成交筆數"), raw.get("成交股數"), raw.get("成交金額"),
            raw.get("收盤價"), raw.get("最低價"), raw.get("最後揭示買價"),
            raw.get("最後揭示買量"), raw.get("最後揭示賣價"), raw.get("最後揭示賣量"),
            raw.get("最高價"), raw.get("本益比"), raw.get("漲跌價差"), raw.get("開盤價"),
        ]
        values[34:54] = [technical.get(name) for name in tuple(name.split(".", 1)[1] for name in expected_feature_contract()[0][34:54])]
        values[54:59] = [
            raw.get("最後揭示買價"), raw.get("最後揭示買量"), raw.get("最後揭示賣價"),
            raw.get("最後揭示賣量"), raw.get("本益比"),
        ]
        values[59] = None  # 來源為自由文字，不改造為 numeric label
        values[60] = None  # 正負方向欄位不是可驗證數值
        values[61] = raw.get("漲跌價差")
    scales = feature_scales
    scaled: list[int | None] = [None] * 62
    invalid = [0] * 52
    stale = [0] * 52
    observed = [0] * 52
    event_dates: list[date | None] = [market_day] * 11 + [stock_day] * 41
    for index in range(10, 62):
        source_value = values[index]
        event_day = event_dates[index - 10]
        if source_value is None or event_day is None:
            continue
        number, is_stale, is_blocked = _feature_eligibility(
            source_value, index, scales[index], (decision - event_day).days
        )
        stale[index - 10] = int(is_stale)
        invalid[index - 10] = int(is_blocked)
        if number is not None:
            scaled[index] = number
            observed[index - 10] = 1
    market_observed = sum(observed[:11])
    stock_observed = sum(observed[11:])
    market_lags = [(decision - day).days for day in event_dates[:11] if day is not None]
    stock_lags = [(decision - day).days for day in event_dates[11:] if day is not None]
    scaled[:10] = [
        (market_observed * 10_000) // 11, max(market_lags, default=0),
        11 - market_observed, sum(invalid[:11]), sum(stale[:11]),
        (stock_observed * 10_000) // 41, max(stock_lags, default=0),
        41 - stock_observed, sum(invalid[11:]), sum(stale[11:]),
    ]
    masks = [1 if value is None else 0 for value in scaled]
    return [int(value) if value is not None else 0 for value in scaled], masks, stock_day, market_day



class RestatedDatasetBuilder:
    """以按年、按 symbol bounded 記憶體重算研究特徵與標籤。"""

    def __init__(
        self, *, snapshot_db: Path = _SOURCE_DB, direct_manifest: Path = _DIRECT_MANIFEST,
        corporate_action_manifest: Path = _CA_MANIFEST, output_dir: Path = _DEFAULT_OUTPUT,
        kernel_root: Path | None = None, revision_observed_at: str | None = None,
        batch_size: int = 8_192, decision_date_start: date | None = None,
        decision_date_end: date | None = None, limit_rows: int | None = None,
        include_appends: bool = True, symbols: Sequence[str] = (),
    ) -> None:
        self.snapshot_db = snapshot_db
        self.direct_manifest_path = direct_manifest
        self.ca_manifest_path = corporate_action_manifest
        self.output_dir = output_dir
        self.kernel_root = kernel_root
        self.revision_observed_at = revision_observed_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.observed_clock = _aware_datetime(self.revision_observed_at)
        self.batch_size = batch_size
        self.date_start = decision_date_start
        self.date_end = decision_date_end
        self.limit_rows = limit_rows
        self.include_appends = include_appends
        self.symbol_filter = frozenset(str(value).strip() for value in symbols if str(value).strip())
        if batch_size <= 0 or batch_size > 100_000:
            raise ValueError("batch_size must be within 1..100000")
        if limit_rows is not None and limit_rows <= 0:
            raise ValueError("limit_rows must be positive")
        self.contract = load_contract(direct_manifest)
        self._verified_years: set[int] = set()
        self.snapshot_sha = sha256_file(snapshot_db)
        if self.snapshot_sha != _EXPECTED_SNAPSHOT_SHA:
            raise ValueError("input snapshot hash differs from the authorized immutable source")
        if self.contract.direct_manifest_file_hash != _EXPECTED_DIRECT_MANIFEST_SHA:
            raise ValueError("Direct source manifest hash differs from the audited baseline")
        self.transfer_receipt_sha = sha256_file(_TRANSFER_RECEIPT)
        if self.transfer_receipt_sha != _EXPECTED_TRANSFER_RECEIPT_SHA:
            raise ValueError("transfer receipt hash differs from the authorized custody receipt")
        self.connection = sqlite3.connect(f"file:{snapshot_db.as_posix()}?mode=ro", uri=True)
        self.connection.execute("PRAGMA query_only=ON")
        self.connection.row_factory = sqlite3.Row
        self.market = self._load_market()
        self.calendar = sorted(self.market)
        self.calendar_index = {day: index for index, day in enumerate(self.calendar)}
        self.market_ohlc = {day: _decimal_ohlc(row) for day, row in self.market.items()}
        self.latest_observed_market_date = max(self.calendar)
        self.corporate_actions, self.ca_manifest_sha = self._load_corporate_actions()
        if kernel_root is not None:
            sys.path.insert(0, str(kernel_root))
        from analysis_module.technical_analysis.technical_indicators import calculate_causal_indicators
        self.calculate_causal_indicators = calculate_causal_indicators
        self.kernel_path = Path(calculate_causal_indicators.__code__.co_filename)
        self.kernel_sha = sha256_file(self.kernel_path)

    def close(self) -> None:
        self.connection.close()

    def _load_market(self) -> dict[date, dict[str, Any]]:
        result: dict[date, dict[str, Any]] = {}
        cursor = self.connection.execute(
            "SELECT 日期,指數名稱,收盤指數,漲跌點數,漲跌百分比,開盤價,最高價,最低價,收盤價,成交量 "
            "FROM market_indices WHERE 指數名稱='TAIEX' ORDER BY 日期"
        )
        for row in cursor:
            day = _iso_date(row["日期"])
            if day is not None:
                result[day] = dict(row)
        if not result:
            raise ValueError("snapshot has no observed TAIEX rows")
        return result

    def _load_corporate_actions(self) -> tuple[dict[str, list[dict[str, Any]]], str]:
        if not self.ca_manifest_path.exists():
            raise FileNotFoundError(f"corporate action custody manifest is required: {self.ca_manifest_path}")
        manifest = _read_json(self.ca_manifest_path)
        if manifest.get("prospective_only") is not True or manifest.get("historical_pit_eligible") is not False:
            raise ValueError("corporate action custody eligibility changed")
        artifact = self.ca_manifest_path.parent / str(manifest["adjustments"]["path"])
        if sha256_file(artifact) != manifest["adjustments"]["file_hash"]:
            raise ValueError("corporate action adjustment hash mismatch")
        result: dict[str, list[dict[str, Any]]] = {}
        with artifact.open("r", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                symbol = str(row.get("symbol") or row.get("security_id") or row.get("security_code") or "")
                effective = _iso_date(row.get("effective_from"))
                if symbol and effective is not None:
                    row["_effective_date"] = effective
                    result.setdefault(symbol, []).append(row)
        return result, sha256_file(self.ca_manifest_path)

    def _stock_frame(self, symbol: str) -> tuple[pd.DataFrame, list[date], list[dict[str, Any]]]:
        cursor = self.connection.execute(
            "SELECT 日期,證券代號,成交股數,成交筆數,成交金額,開盤價,最高價,最低價,收盤價,涨跌,漲跌價差,"
            "最後揭示買價,最後揭示買量,最後揭示賣價,最後揭示賣量,本益比 "
            "FROM daily_prices WHERE 證券代號=? ORDER BY 日期", (symbol,)
        )
        rows = [dict(row) for row in cursor]
        dates = [_iso_date(row["日期"]) for row in rows]
        if any(day is None for day in dates) or dates != sorted(dates) or len(set(dates)) != len(dates):
            raise ValueError(f"{symbol}: source OHLC dates must be valid, unique, ordered")
        frame = pd.DataFrame(rows)
        # kernel receives the full symbol history; the publication date is sliced only after calculation.
        calculated = self.calculate_causal_indicators(frame)
        if len(calculated) != len(rows) or any(name not in calculated.columns for name in TECHNICAL_FIELDS):
            raise ValueError("causal kernel violated the 20-indicator output contract")
        return calculated, [day for day in dates if day is not None], rows

    def _baseline_rows(self, year: Mapping[str, Any]) -> list[dict[str, Any]]:
        year_dir = self.direct_manifest_path.parent / f"year={int(year['year'])}"
        self._verify_year_sources(year, year_dir)
        path = year_dir / "rows.sqlite"
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        result: list[dict[str, Any]] = []
        cursor = conn.execute("SELECT local_row_index,row_id,decision_at,decision_date,symbol FROM rows ORDER BY local_row_index")
        try:
            for row in cursor:
                decision = _iso_date(row["decision_date"])
                if self.symbol_filter and str(row["symbol"]) not in self.symbol_filter:
                    continue
                if decision is None or (self.date_start and decision < self.date_start) or (self.date_end and decision > self.date_end):
                    continue
                expected_row_id = f"row:{decision.isoformat()}:{row['symbol']}"
                expected_decision_at = datetime.combine(decision, _DECISION_TIME, _TAIPEI).isoformat()
                if str(row["row_id"]) != expected_row_id or str(row["decision_at"]) != expected_decision_at:
                    raise ValueError(f"Direct row identity mismatch at {year['year']}:{row['local_row_index']}")
                result.append(dict(row) | {
                    "_decision": decision, "_append": False,
                    "_calendar_basis": "direct_observed_market_row_keys",
                })
                if self.limit_rows is not None and len(result) >= self.limit_rows:
                    break
        finally:
            conn.close()
        return result

    def _verify_year_sources(self, year: Mapping[str, Any], year_dir: Path) -> None:
        year_value = int(year["year"])
        if year_value in self._verified_years:
            return
        artifacts = {Path(item["path"]).name: item for item in year.get("artifacts", ())}
        for name in ("rows.sqlite", "targets.i32"):
            record = artifacts.get(name)
            path = year_dir / name
            if record is None or not path.is_file():
                raise ValueError(f"Direct shard is missing manifest-bound {name}: {year_value}")
            actual = sha256_file(path)
            if actual != record.get("file_sha256") or path.stat().st_size != int(record.get("byte_count", -1)):
                raise ValueError(f"Direct {name} hash/size mismatch: {year_value}")
        conn = sqlite3.connect(f"file:{(year_dir / 'rows.sqlite').as_posix()}?mode=ro", uri=True)
        try:
            conn.execute("PRAGMA query_only=ON")
            count = int(conn.execute("SELECT COUNT(*) FROM rows").fetchone()[0])
            integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        finally:
            conn.close()
        if count != int(year["row_count"]) or integrity != "ok":
            raise ValueError(f"Direct row shard integrity/count mismatch: {year_value}")
        self._verified_years.add(year_value)

    def _append_rows(self, baseline_end: date) -> list[dict[str, Any]]:
        # Each appended universe is selected only from that date's causal T-1 rows.
        candidates = [day for day in self.calendar if day > baseline_end]
        inferred_current = self.latest_observed_market_date + timedelta(days=1)
        if inferred_current.weekday() < 5 and inferred_current not in self.market:
            candidates.append(inferred_current)
        result: list[dict[str, Any]] = []
        for decision in sorted(set(candidates)):
            prior_pos = bisect_left(self.calendar, decision) - 1
            if prior_pos < 0:
                continue
            source_day = self.calendar[prior_pos]
            rows = self.connection.execute(
                "SELECT 證券代號,開盤價,最高價,最低價,收盤價 FROM daily_prices WHERE 日期=? ORDER BY 證券代號",
                (source_day.strftime("%Y%m%d"),),
            )
            for source in rows:
                if _complete_ohlc(dict(source)) and (not self.symbol_filter or str(source["證券代號"]) in self.symbol_filter):
                    symbol = str(source["證券代號"])
                    result.append({
                        "local_row_index": None, "row_id": f"row:{decision.isoformat()}:{symbol}",
                        "decision_at": datetime.combine(decision, _DECISION_TIME, _TAIPEI).isoformat(),
                        "decision_date": decision.isoformat(), "symbol": symbol,
                        "_decision": decision, "_append": True,
                        "_calendar_basis": "observed_TAIEX_calendar" if decision in self.market else "research_weekday_inferred_from_current_snapshot",
                    })
        return result

    def _fold_metadata(self, decision: date, revision_purge_start: date) -> tuple[str, list[str]]:
        if decision >= date(2026, 5, 20):
            role = "revision_heldout"
        elif revision_purge_start <= decision < date(2026, 5, 20):
            role = "revision_purged"
        else:
            role = "walk_forward_fit_candidate"
        fold_ids = []
        for fold in self.contract.folds:
            if str(fold.get("test_start", "")) <= decision.isoformat() <= str(fold.get("test_end", "")):
                fold_ids.append(str(fold["fold_id"]))
        return role, fold_ids

    @staticmethod
    def _technical_order() -> tuple[str, ...]:
        return (
            "ADX", "ATR", "DEMA30", "EMA30", "MA10", "MA20", "MA5", "MA60",
            "MACD", "MACD_hist", "MACD_signal", "RSI", "SAR", "SMA30", "TSF",
            "lowerband", "middleband", "slowd", "slowk", "upperband",
        )

    def _source_values(self, row: dict[str, Any], stock: pd.DataFrame, dates: list[date], raw_rows: list[dict[str, Any]]) -> tuple[list[int], list[int], date | None, date | None]:
        return build_restated_feature_values(
            decision=row["_decision"], stock=stock, dates=dates, raw_rows=raw_rows,
            market_dates=self.calendar, market_rows=self.market,
            feature_scales=self.contract.feature_scales,
        )

    def _label_horizon(self, row: dict[str, Any], stock_dates: list[date], stock_by_date: dict[date, dict[str, Decimal] | None], horizon: int) -> tuple[dict[int, int], dict[int, int], date | None, str | None, str | None]:
        decision = row["_decision"]
        calendar_idx = self.calendar_index.get(decision)
        if calendar_idx is None:
            evidence = {"status": "missing", "reason": "decision_not_in_observed_TAIEX_calendar"}
            return {}, {}, None, None, json.dumps(evidence, separators=(",", ":"))
        end_idx = calendar_idx + horizon - 1
        if end_idx >= len(self.calendar):
            evidence = {"status": "immature", "reason": "horizon_end_not_observed"}
            return {}, {}, None, None, json.dumps(evidence, separators=(",", ":"))
        path_dates = self.calendar[calendar_idx:end_idx + 1]
        end_date = path_dates[-1]
        maturity_text = datetime.combine(end_date, _CLOSE_TIME, _TAIPEI).isoformat()
        stock_path: list[dict[str, Decimal]] = []
        market_path: list[dict[str, Decimal]] = []
        missing_reason: str | None = None
        for path_day in path_dates:
            stock_price = stock_by_date.get(path_day)
            market_price = self.market_ohlc.get(path_day)
            if stock_price is None:
                missing_reason = "stock_path_gap_or_invalid_ohlc"
                break
            if market_price is None:
                missing_reason = "benchmark_path_gap_or_invalid_ohlc"
                break
            stock_path.append(stock_price)
            market_path.append(market_price)
        ca_events = [
            event for event in self.corporate_actions.get(str(row["symbol"]), [])
            if decision <= event["_effective_date"] <= end_date
        ]
        if datetime.fromisoformat(maturity_text) > self.observed_clock:
            missing_reason = "label_not_matured_by_revision_observed_at"
        if ca_events:
            missing_reason = "corporate_action_effective_within_label_horizon"
        if missing_reason:
            evidence = {
                "status": "missing", "reason": missing_reason, "entry_date": decision.isoformat(),
                "label_end_date": end_date.isoformat(), "maturity_at": maturity_text,
                "cost_lane": _COST_LANE,
                "corporate_action_event_ids": [str(event.get("source_event_id", "")) for event in ca_events],
            }
            return {}, {}, end_date, maturity_text, json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        entry, exit_row = stock_path[0], stock_path[-1]
        market_entry, market_exit = market_path[0], market_path[-1]
        stock_return = _bp_return(entry["open"], exit_row["close"])
        benchmark_return = _bp_return(market_entry["open"], market_exit["close"])
        excess = stock_return - benchmark_return - _BUY_COST_BP - _SELL_COST_BP
        mae, mfe, volatility, drawdown, tail_loss = _series_metrics(entry["open"], stock_path)
        feasible = int(entry["high"] > entry["low"] and entry["low"] <= entry["open"] <= entry["high"])
        labels = {0: excess, 1: 0, 2: int(excess < 0), 3: mae, 4: mfe, 5: volatility, 6: drawdown, 7: tail_loss, 8: feasible}
        masks = {index: 0 for index in range(9)}
        masks[1] = 1  # no accepted historical sector-membership sidecar
        path_payload = [
            [
                day.isoformat(),
                *(_scaled_price(stock_path[path_index][key]) for key in ("open", "high", "low", "close")),
            ]
            for path_index, day in enumerate(path_dates)
        ]
        evidence = {
            "status": "observed_except_sector_excess", "entry_date": decision.isoformat(),
            "exit_date": end_date.isoformat(), "stock_entry_open": str(entry["open"]),
            "stock_exit_close": str(exit_row["close"]), "benchmark_entry_open": str(market_entry["open"]),
            "benchmark_exit_close": str(market_exit["close"]), "gross_stock_return_bp": stock_return,
            "gross_benchmark_return_bp": benchmark_return, "cost_lane": _COST_LANE,
            "cost_buy_bp": _BUY_COST_BP, "cost_sell_bp": _SELL_COST_BP,
            "corporate_action_basis": "prospective_only_events_excluded_by_effective_date",
            "corporate_action_event_ids": [], "path_sha256": canonical_hash(path_payload),
        }
        return labels, masks, end_date, maturity_text, json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def _year_arrays(self, rows: list[dict[str, Any]], year: Mapping[str, Any], revision_purge_start: date) -> dict[str, Any]:
        started = perf_counter()
        count = len(rows)
        features = np.zeros((count, 62), dtype=np.int64)
        feature_mask = np.ones((count, 62), dtype=np.uint8)
        labels = {h: np.zeros((count, 9), dtype=np.int64) for h in SUPPORTED_HORIZONS}
        label_mask = {h: np.ones((count, 9), dtype=np.uint8) for h in SUPPORTED_HORIZONS}
        label_end = {h: [None] * count for h in SUPPORTED_HORIZONS}
        maturity = {h: [None] * count for h in SUPPORTED_HORIZONS}
        basis = {h: [None] * count for h in SUPPORTED_HORIZONS}
        stock_event_dates: list[date | None] = [None] * count
        market_event_dates: list[date | None] = [None] * count
        roles: list[str] = ["" for _ in rows]
        fold_ids: list[list[str]] = [[] for _ in rows]
        for index, row in enumerate(rows):
            roles[index], fold_ids[index] = self._fold_metadata(row["_decision"], revision_purge_start)
        by_symbol: dict[str, list[int]] = {}
        for index, row in enumerate(rows):
            by_symbol.setdefault(str(row["symbol"]), []).append(index)
        completed_symbol_rows = 0
        last_progress_at = started
        for symbol_index, (symbol, indices) in enumerate(by_symbol.items(), start=1):
            calculated, dates, raw_rows = self._stock_frame(symbol)
            stock_by_date = {day: _decimal_ohlc(source) for day, source in zip(dates, raw_rows)}
            for index in indices:
                row = rows[index]
                values, masks, stock_day, market_day = self._source_values(row, calculated, dates, raw_rows)
                features[index] = values
                feature_mask[index] = masks
                stock_event_dates[index] = stock_day
                market_event_dates[index] = market_day
                for horizon in SUPPORTED_HORIZONS:
                    result, missing, end_day, mature_at, evidence = self._label_horizon(
                        row, dates, stock_by_date, horizon
                    )
                    label_end[horizon][index] = end_day
                    maturity[horizon][index] = mature_at
                    basis[horizon][index] = evidence
                    for field_index, value in result.items():
                        labels[horizon][index, field_index] = value
                    for field_index, value in missing.items():
                        label_mask[horizon][index, field_index] = value
            completed_symbol_rows += len(indices)
            progress_at = perf_counter()
            if symbol_index % 50 == 0 or progress_at - last_progress_at >= 30:
                elapsed = max(perf_counter() - started, 0.001)
                print(
                    f"year={year['year']} completed_symbols={symbol_index}/{len(by_symbol)} "
                    f"completed_rows={completed_symbol_rows}/{count} elapsed_seconds={elapsed:.1f} "
                    f"rows_per_second={completed_symbol_rows / elapsed:.1f} rss_bytes={_rss_bytes()}",
                    flush=True,
                )
                last_progress_at = progress_at
        target_values = np.zeros((count, 6), dtype=np.int32)
        target_mask = np.ones((count, 6), dtype=np.uint8)
        if rows and not rows[0]["_append"]:
            year_dir = self.direct_manifest_path.parent / f"year={int(year['year'])}"
            direct_year = next(item for item in self.contract.years if int(item["year"]) == int(year["year"]))
            self._verify_year_sources(direct_year, year_dir)
            raw_targets = np.memmap(year_dir / "targets.i32", dtype=np.int32, mode="r", shape=(int(direct_year["row_count"]), 6))
            for index, row in enumerate(rows):
                if not row["_append"]:
                    target_values[index] = raw_targets[int(row["local_row_index"])]
                    target_mask[index] = 0
            del raw_targets
        enriched_rows: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            lineage = canonical_hash({
                "row_id": row["row_id"], "source_revision_id": self.snapshot_sha,
                "stock_event_date": stock_event_dates[index].isoformat() if stock_event_dates[index] else None,
                "market_event_date": market_event_dates[index].isoformat() if market_event_dates[index] else None,
                "features_i64": features[index].tolist(), "feature_missing_mask": feature_mask[index].tolist(),
            })
            enriched_rows.append({
                **row, "_stock_event_date": stock_event_dates[index],
                "_market_event_date": market_event_dates[index], "_role": roles[index],
                "_fold_ids": fold_ids[index], "_lineage": lineage,
            })
        elapsed = max(perf_counter() - started, 0.001)
        print(
            f"year={year['year']} complete rows={count} symbols={len(by_symbol)} "
            f"elapsed_seconds={elapsed:.2f} rows_per_second={count / elapsed:.1f} rss_bytes={_rss_bytes()}",
            flush=True,
        )
        return {
            "rows": enriched_rows, "features": features, "feature_mask": feature_mask,
            "labels": labels, "label_mask": label_mask, "label_end": label_end,
            "maturity": maturity, "basis": basis, "targets": target_values,
            "target_mask": target_mask,
        }

    def _table_batches(self, arrays: dict[str, Any]):
        import pyarrow as pa

        rows = arrays["rows"]
        schema = arrow_schema()
        for start in range(0, len(rows), self.batch_size):
            end = min(len(rows), start + self.batch_size)
            selected = rows[start:end]
            columns: dict[str, Any] = {
                "row_id": pa.array([r["row_id"] for r in selected], type=pa.string()),
                "symbol": pa.array([str(r["symbol"]) for r in selected], type=pa.string()),
                "decision_date": pa.array([r["_decision"] for r in selected], type=pa.date32()),
                "decision_at": pa.array([r["decision_at"] for r in selected], type=pa.string()),
                "local_row_index": pa.array([r.get("local_row_index") for r in selected], type=pa.int32()),
                "fold_role": pa.array([r["_role"] for r in selected], type=pa.string()),
                "fold_ids": pa.array([r["_fold_ids"] for r in selected], type=pa.list_(pa.string())),
                "calendar_basis": pa.array([r["_calendar_basis"] for r in selected], type=pa.string()),
                "stock_event_date": pa.array([r["_stock_event_date"] for r in selected], type=pa.date32()),
                "market_event_date": pa.array([r["_market_event_date"] for r in selected], type=pa.date32()),
                "feature_event_asof_at": pa.array([
                    datetime.combine(r["_stock_event_date"], _CLOSE_TIME, _TAIPEI).isoformat() if r["_stock_event_date"] else None
                    for r in selected
                ], type=pa.string()),
                "feature_available_at": pa.array([self.revision_observed_at] * len(selected), type=pa.string()),
                "revision_observed_at": pa.array([self.revision_observed_at] * len(selected), type=pa.string()),
                "source_revision_id": pa.array([self.snapshot_sha] * len(selected), type=pa.string()),
                "feature_lineage_hash": pa.array([r["_lineage"] for r in selected], type=pa.string()),
            }
            fvalues, fmasks = arrays["features"][start:end], arrays["feature_mask"][start:end]
            columns["features_scaled_i64"] = _fixed_array(fvalues, fmasks, 62, pa.int64())
            columns["feature_missing_mask"] = pa.FixedSizeListArray.from_arrays(pa.array(fmasks.reshape(-1), type=pa.uint8()), 62)
            tvalues, tmasks = arrays["targets"][start:end], arrays["target_mask"][start:end]
            columns["target_values_i32"] = _fixed_array(tvalues, tmasks, 6, pa.int32())
            columns["target_missing_mask"] = pa.FixedSizeListArray.from_arrays(pa.array(tmasks.reshape(-1), type=pa.uint8()), 6)
            for horizon in SUPPORTED_HORIZONS:
                columns[f"label_end_date_h{horizon}"] = pa.array(arrays["label_end"][horizon][start:end], type=pa.date32())
                columns[f"maturity_at_h{horizon}"] = pa.array(arrays["maturity"][horizon][start:end], type=pa.string())
                values, masks = arrays["labels"][horizon][start:end], arrays["label_mask"][horizon][start:end]
                columns[f"labels_h{horizon}_i64"] = _fixed_array(values, masks, 9, pa.int64())
                columns[f"labels_h{horizon}_missing_mask"] = pa.FixedSizeListArray.from_arrays(pa.array(masks.reshape(-1), type=pa.uint8()), 9)
                columns[f"label_basis_h{horizon}"] = pa.array(arrays["basis"][horizon][start:end], type=pa.string())
            yield pa.Table.from_pydict(columns, schema=schema)

    def _write_year(self, arrays: dict[str, Any], writer: Any) -> None:
        for table in self._table_batches(arrays):
            writer.write_table(table, row_group_size=self.batch_size)

    def build(self) -> Path:
        import pyarrow.parquet as pq

        if self.output_dir.exists():
            raise FileExistsError(f"refusing to overwrite dataset output: {self.output_dir}")
        self.output_dir.mkdir(parents=True, exist_ok=False)
        heldout_index = bisect_left(self.calendar, date(2026, 5, 20))
        purge_index = max(0, heldout_index - 65)
        purge_start = self.calendar[purge_index]
        files: list[dict[str, Any]] = []
        remaining = self.limit_rows
        for year_item in self.contract.years:
            year = int(year_item["year"])
            if self.date_start and year < self.date_start.year:
                continue
            if self.date_end and year > self.date_end.year:
                continue
            selected = self._baseline_rows(year_item)
            if remaining is not None:
                selected = selected[:remaining]
                remaining -= len(selected)
            if not selected:
                continue
            arrays = self._year_arrays(selected, year_item, purge_start)
            year_dir = self.output_dir / f"year={year}"
            year_dir.mkdir(parents=True, exist_ok=True)
            final_path = year_dir / "research_dataset.parquet"
            temp_path = year_dir / "research_dataset.parquet.tmp"
            if final_path.exists() or temp_path.exists():
                raise FileExistsError(final_path)
            writer = pq.ParquetWriter(temp_path, arrow_schema(), compression="zstd", compression_level=6, use_dictionary=["symbol", "fold_role", "source_revision_id"])
            self._write_year(arrays, writer)
            appended = 0
            if year == 2026 and self.include_appends and self.limit_rows is None:
                latest_baseline = max((row["_decision"] for row in selected), default=date(2026, 7, 14))
                new_rows = self._append_rows(latest_baseline)
                for start in range(0, len(new_rows), 25_000):
                    group = new_rows[start:start + 25_000]
                    self._write_year(self._year_arrays(group, year_item, purge_start), writer)
                appended = len(new_rows)
            writer.close()
            os.replace(temp_path, final_path)
            files.append({
                "year": year, "path": str(final_path.relative_to(self.output_dir)),
                "row_count": len(selected) + appended, "baseline_row_count": len(selected),
                "appended_row_count": appended, "file_sha256": sha256_file(final_path),
                "byte_count": final_path.stat().st_size,
            })
            if remaining == 0:
                break
        if not files:
            raise ValueError("date filter selected no Direct rows")
        total_rows = sum(int(item["row_count"]) for item in files)
        kernel = {
            "path": str(self.kernel_path), "sha256": self.kernel_sha,
            "technical_indicator_columns": list(TECHNICAL_FIELDS),
            "recipe_version": "causal-indicators.full-prefix.gap-reset.v1",
        }
        source_hashes = {
            "snapshot_db": {"path": str(self.snapshot_db), "sha256": self.snapshot_sha},
            "direct_manifest": {"path": str(self.direct_manifest_path), "file_sha256": self.contract.direct_manifest_file_hash, "manifest_hash": self.contract.direct_manifest_hash},
            "discovery_cache": {"path": str(self.direct_manifest_path.parent / "discovery_cache.json"), "sha256": self.contract.discovery_cache_hash},
            "corporate_action_manifest": {"path": str(self.ca_manifest_path), "sha256": self.ca_manifest_sha},
            "transfer_receipt": {"path": str(_TRANSFER_RECEIPT), "sha256": self.transfer_receipt_sha},
        }
        code_sha = sha256_file(Path(__file__))
        recipe = {
            "label_fields": list(LABEL_FIELDS), "label_scales": [1] * 9,
            "cost_lane": _COST_LANE, "label_recipe_version": "open-to-horizon-close.decimal-bp.v1",
            "quality_recipe_version": "event-age-7d.family-coverage-bp.v1",
            "fold_recipe_version": "legacy-60purge-5embargo.revision-heldout-2026-05-20.v1",
        }
        feature_order_hash = canonical_hash(list(zip(self.contract.feature_ids, self.contract.feature_scales)))
        identity = {
            "schema_version": "portfolio-ml-restated-research-dataset.v1",
            "source_hashes": source_hashes, "feature_ids": list(self.contract.feature_ids),
            "feature_scales": list(self.contract.feature_scales), "feature_order_hash": feature_order_hash,
            "kernel": kernel, "builder_code_sha256": code_sha, "label_quality_recipe": recipe,
            "restated_research": True, "formal_historical_PIT": False,
            "training_as_of": self.revision_observed_at, "revision_observed_at": self.revision_observed_at,
            "row_count": total_rows, "partition_files": files,
            "date_filter": {"start": self.date_start.isoformat() if self.date_start else None, "end": self.date_end.isoformat() if self.date_end else None, "limit_rows": self.limit_rows},
            "symbol_filter": sorted(self.symbol_filter),
        }
        identity_hash = canonical_hash(identity)
        manifest = {
            **identity, "dataset_id": "ml-restated-research-" + identity_hash.split(":", 1)[1][:24],
            "dataset_identity_hash": identity_hash, "manifest_hash": identity_hash,
            "feature_count": 62, "feature_ids": list(self.contract.feature_ids),
            "feature_scales": list(self.contract.feature_scales), "feature_packs": list(self.contract.feature_packs),
            "feature_registry_hash": self.contract.feature_registry_hash,
            "feature_value_dtype": "nullable int64 fixed-size list[62]; missing values are Arrow null",
            "feature_missing_mask_semantics": "0=observed, 1=missing; null feature value iff mask is 1",
            "label_fields": list(LABEL_FIELDS), "label_scales": [1] * 9,
            "horizons": list(SUPPORTED_HORIZONS), "horizon_dates_are_independent": True,
            "label_missing_mask_semantics": "0=observed, 1=missing; independent per field and horizon",
            "target_fields": list(TARGET_FIELDS),
            "target_missing_mask_semantics": "0=original Direct target present, 1=missing; new rows are null",
            "original_row_target_audit": {
                "artifact": "output/qa/model_repair_review/original_target_values_audit.json",
                "join": "Direct OOC year shards/targets.i32 by local_row_index",
                "appended_targets": "missing; never teacher-filled",
            },
            "feature_event_semantics": "decision_at=08:30 Asia/Taipei; market and stock feature events are strictly before decision_date; complete symbol OHLC prefix goes through the causal kernel before T-1 slice",
            "feature_available_at_semantics": "actual revision verification time; not historical PIT availability",
            "calendar_basis": "observed TAIEX dates; not represented as complete official calendar",
            "latest_inference_row_policy": "universe is sourced from each causal T-1 daily_prices date; next weekday row is explicitly research-inferred",
            "fold_policy": {
                "source_fold_windows": list(self.contract.folds), "purge_trading_days": 60,
                "embargo_trading_days": 5, "revision_heldout_start": "2026-05-20",
                "revision_purge_start": purge_start.isoformat(),
                "revision_heldout_end": self.latest_observed_market_date.isoformat(),
                "maturity_rule": "per horizon, maturity_at_hN must precede the relevant boundary; other horizon masks never imply maturity",
                "formal_oos": False,
            },
            "fold_boundaries": list(self.contract.folds),
            "observed_session_dates": [day.isoformat() for day in self.calendar],
            "source_hashes": source_hashes,
            "source_manifest_hashes": [
                ["sqlite.daily_prices", self.snapshot_sha],
                ["direct.manifest", self.contract.direct_manifest_file_hash],
                ["direct.discovery_cache", self.contract.discovery_cache_hash],
                ["custody.transfer_receipt", self.transfer_receipt_sha],
                ["derived.causal_kernel", self.kernel_sha],
                ["derived.label_quality_builder", code_sha],
                ["sidecar.corporate_action_adjustments", self.ca_manifest_sha],
            ],
            "corporate_action_basis": {
                "manifest_hash": self.ca_manifest_sha, "prospective_only": True,
                "formal_source_contract_eligible": False, "historical_pit_eligible": False,
                "effective_in_horizon_labels_masked": True,
            },
            "status": "complete_research_build", "research_only": True,
            "promotion_eligible": False, "formal_historical_PIT": False, "formal_oos": False,
        }
        manifest_path = self.output_dir / "manifest.json"
        temporary = self.output_dir / "manifest.json.tmp"
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, manifest_path)
        return manifest_path


def _complete_ohlc(row: Mapping[str, Any]) -> bool:
    return _decimal_ohlc(row) is not None


def _decimal_ohlc(row: Mapping[str, Any] | None) -> dict[str, Decimal] | None:
    if row is None:
        return None
    values = {
        "open": _decimal(_get(row, "開盤價", _get(row, "開盤"))),
        "high": _decimal(_get(row, "最高價", _get(row, "最高"))),
        "low": _decimal(_get(row, "最低價", _get(row, "最低"))),
        "close": _decimal(_get(row, "收盤價", _get(row, "收盤指數", _get(row, "收盤")))),
    }
    if any(value is None or value <= 0 for value in values.values()):
        return None
    if values["low"] > min(values["open"], values["close"]) or values["high"] < max(values["open"], values["close"]):
        return None
    return {name: value for name, value in values.items() if value is not None}


def build_parser():
    import argparse

    parser = argparse.ArgumentParser(description="Build a restated, non-PIT price-revision research dataset")
    parser.add_argument("--snapshot-db", type=Path, default=_SOURCE_DB)
    parser.add_argument("--direct-manifest", type=Path, default=_DIRECT_MANIFEST)
    parser.add_argument("--corporate-action-manifest", type=Path, default=_CA_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--kernel-root", type=Path)
    parser.add_argument("--revision-observed-at")
    parser.add_argument("--batch-size", type=int, default=8192)
    parser.add_argument("--decision-date-start", type=date.fromisoformat)
    parser.add_argument("--decision-date-end", type=date.fromisoformat)
    parser.add_argument("--limit-rows", type=int)
    parser.add_argument("--symbols", help="comma-separated symbol filter for bounded real-source runs")
    parser.add_argument("--no-appends", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    builder = RestatedDatasetBuilder(
        snapshot_db=args.snapshot_db, direct_manifest=args.direct_manifest,
        corporate_action_manifest=args.corporate_action_manifest, output_dir=args.output_dir,
        kernel_root=args.kernel_root, revision_observed_at=args.revision_observed_at,
        batch_size=args.batch_size, decision_date_start=args.decision_date_start,
        decision_date_end=args.decision_date_end, limit_rows=args.limit_rows,
        include_appends=not args.no_appends,
        symbols=tuple(args.symbols.split(",")) if args.symbols else (),
    )
    try:
        print(builder.build())
    finally:
        builder.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
