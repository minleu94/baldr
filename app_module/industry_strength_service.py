"""唯讀、可比的當日產業強弱服務。

本模組把目前可取得的公司分類、產業指數、TAIEX 與日價資料組成一個
明確標示日期／來源／覆蓋率的研究 read model。它不建立新的資料庫、不寫回
watchlist，也不把目前公司分類冒充成歷史 PIT 分類。
"""

from __future__ import annotations

from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import sqlite3
from typing import Any, Protocol

import pandas as pd

from app_module.decision_desk_dtos import (
    DecisionDeskQuality,
    IndustryRepresentativeStock,
    IndustryStrengthRow,
    IndustryStrengthSummary,
    SectorRotationSummary,
)
from app_module.dtos.market_loop_dtos import ScreeningResultDTO
from data_module.pit_sector_membership_reader import (
    PITMembershipReadResult,
    PITMembershipRow,
    PITSectorMembershipReader,
)


# 這份表是刻意維護的 exact mapping；不使用模糊字串猜配，避免把父層、
# 子層、存託憑證或 TPEx 獨有類別混成同一個產業。
INDUSTRY_CATEGORY_TO_INDEX: dict[str, str] = {
    "光電業": "光電類指數",
    "其他": "其他類指數",
    "其他電子業": "其他電子類指數",
    "化學生技醫療": "化學生技醫療類指數",
    "半導體業": "半導體類指數",
    "塑膠工業": "塑膠類指數",
    "居家生活": "居家生活類指數",
    "建材營造": "建材營造類指數",
    "數位雲端": "數位雲端類指數",
    "橡膠工業": "橡膠類指數",
    "水泥工業": "水泥類指數",
    "汽車工業": "汽車類指數",
    "油電燃氣業": "油電燃氣類指數",
    "玻璃陶瓷": "玻璃陶瓷類指數",
    "生技醫療業": "生技醫療類指數",
    "紡織纖維": "紡織纖維類指數",
    "綠能環保": "綠能環保類指數",
    "航運業": "航運類指數",
    "觀光餐旅": "觀光餐旅類指數",
    "貿易百貨": "貿易百貨類指數",
    "資訊服務業": "資訊服務類指數",
    "通信網路業": "通信網路類指數",
    "造紙工業": "造紙類指數",
    "運動休閒": "運動休閒類指數",
    "金融保險": "金融保險類指數",
    "鋼鐵工業": "鋼鐵類指數",
    "電器電纜": "電器電纜類指數",
    "電子通路業": "電子通路類指數",
    "電子零組件業": "電子零組件類指數",
    "電機機械": "電機機械類指數",
    "電腦及週邊設備業": "電腦及週邊設備類指數",
    "食品工業": "食品類指數",
}


INDUSTRY_CATEGORY_MARKET_SCOPE: dict[str, str] = {
    category: "twse" for category in INDUSTRY_CATEGORY_TO_INDEX
}


PURE_INDUSTRY_INDEX_NAMES = frozenset(
    {
        "光電類指數",
        "其他電子類指數",
        "其他類指數",
        "化學生技醫療類指數",
        "化學類指數",
        "半導體類指數",
        "塑膠化工類指數",
        "塑膠類指數",
        "居家生活類指數",
        "建材營造類指數",
        "數位雲端類指數",
        "機電類指數",
        "橡膠類指數",
        "水泥窯製類指數",
        "水泥類指數",
        "汽車類指數",
        "油電燃氣類指數",
        "玻璃陶瓷類指數",
        "生技醫療類指數",
        "紡織纖維類指數",
        "綠能環保類指數",
        "航運類指數",
        "觀光餐旅類指數",
        "貿易百貨類指數",
        "資訊服務類指數",
        "通信網路類指數",
        "造紙類指數",
        "運動休閒類指數",
        "金融保險類指數",
        "鋼鐵類指數",
        "電器電纜類指數",
        "電子工業類指數",
        "電子通路類指數",
        "電子零組件類指數",
        "電機機械類指數",
        "電腦及週邊設備類指數",
        "食品類指數",
    }
)


AGGREGATE_INDUSTRY_INDEX_NAMES = frozenset(
    {
        "電子工業類指數",
        "化學生技醫療類指數",
        "塑膠化工類指數",
        "機電類指數",
        "水泥窯製類指數",
    }
)


EXCLUDED_INDUSTRY_INDEX_NAMES = frozenset(
    {
        "金融類日報酬兩倍指數",
        "金融類日報酬反向一倍指數",
        "電子類兩倍槓桿指數",
        "電子類反向指數",
    }
)


@dataclass(frozen=True)
class IndustryStrengthData:
    """Provider 回傳的唯讀資料包；DataFrame 只在 service 邊界內使用。"""

    industry_indices: pd.DataFrame
    market_indices: pd.DataFrame
    daily_prices: pd.DataFrame
    companies: pd.DataFrame
    mapping_observed_date: date | None = None
    mapping_available_at: str | None = None
    provider_warnings: tuple[str, ...] = ()


class IndustryStrengthDataProvider(Protocol):
    def fetch(self, as_of_date: date, *, session_limit: int = 25) -> IndustryStrengthData: ...


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _as_text_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return []
    return [str(item) for item in value]


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    original = _as_text(value)
    if not original:
        return None
    try:
        return datetime.fromisoformat(original.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    text = original.replace("/", "-")
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            continue
    return None


def _date_key(value: date) -> str:
    return value.strftime("%Y%m%d")


def _to_decimal(value: Any) -> Decimal | None:
    text = _as_text(value)
    if not text:
        return None
    try:
        result = Decimal(text.replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    if not result.is_finite():
        return None
    return result


def _return_bp(start: Decimal | None, end: Decimal | None) -> int | None:
    if start is None or end is None or start <= Decimal("0"):
        return None
    value = ((end - start) / start * Decimal("10000")).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return int(value)


def _format_percent_bp(value: int | None) -> str | None:
    if value is None:
        return None
    percent = (Decimal(value) / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return format(percent, "f")


def _format_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.normalize(), "f")


def is_usable_industry_index_name(name: Any) -> bool:
    """只允許已盤點的純價格產業指數；報酬／槓桿／反向不得進排名。"""

    value = _as_text(name)
    if not value or value in EXCLUDED_INDUSTRY_INDEX_NAMES:
        return False
    if value not in PURE_INDUSTRY_INDEX_NAMES:
        return False
    return not any(token in value for token in ("報酬", "槓桿", "反向", "兩倍", "二倍"))


def industry_level(index_name: Any) -> str:
    return "aggregate" if _as_text(index_name) in AGGREGATE_INDUSTRY_INDEX_NAMES else "leaf"


class SQLiteIndustryStrengthDataProvider:
    """直接以 SQLite mode=ro 取得產業、TAIEX、日價與 current registry。"""

    def __init__(self, db_path: str | Path, companies_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path).resolve()
        self.companies_path = (
            Path(companies_path).resolve() if companies_path is not None else None
        )

    def latest_available_date(self) -> date | None:
        if not self.db_path.is_file():
            return None
        try:
            with closing(self._connect()) as connection:
                keys = _recent_date_keys(connection, "market_indices", date.max, 1)
        except (OSError, sqlite3.Error):
            return None
        return _parse_date(keys[0]) if keys else None

    def fetch(self, as_of_date: date, *, session_limit: int = 25) -> IndustryStrengthData:
        warnings: list[str] = []
        industry = pd.DataFrame(columns=["日期", "指數名稱", "收盤指數"])
        market = pd.DataFrame(columns=["日期", "指數名稱", "收盤指數"])
        prices = pd.DataFrame(columns=["日期", "證券代號", "證券名稱", "收盤價"])
        if not self.db_path.is_file():
            warnings.append("industry_strength_sqlite_missing")
        else:
            try:
                with closing(self._connect()) as connection:
                    # TAIEX 是明確的市場 session 錨點；不能用「有資料的產業日」
                    # 重新拼出一個看似 5／20 日的延長窗口。
                    date_keys = _recent_date_keys(
                        connection, "market_indices", as_of_date, session_limit
                    )
                    if not date_keys:
                        warnings.append("industry_strength_market_session_dates_missing")
                        date_keys = _recent_date_keys(
                            connection, "industry_indices", as_of_date, session_limit
                        )
                    if date_keys:
                        industry = _read_date_rows(
                            connection,
                            "industry_indices",
                            ("日期", "指數名稱", "收盤指數"),
                            date_keys,
                        )
                        market = _read_date_rows(
                            connection,
                            "market_indices",
                            ("日期", "指數名稱", "收盤指數"),
                            date_keys,
                        )
                        prices = _read_date_rows(
                            connection,
                            "daily_prices",
                            ("日期", "證券代號", "證券名稱", "收盤價"),
                            date_keys,
                        )
            except (OSError, sqlite3.Error, pd.errors.DatabaseError) as exc:
                warnings.append(f"industry_strength_sqlite_read_error:{type(exc).__name__}")

        companies, mapping_observed_date, mapping_available_at = self._read_companies(warnings)
        return IndustryStrengthData(
            industry_indices=industry,
            market_indices=market,
            daily_prices=prices,
            companies=companies,
            mapping_observed_date=mapping_observed_date,
            mapping_available_at=mapping_available_at,
            provider_warnings=tuple(warnings),
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"{self.db_path.as_uri()}?mode=ro", uri=True)
        connection.execute("PRAGMA query_only=ON")
        return connection

    def _read_companies(
        self, warnings: list[str]
    ) -> tuple[pd.DataFrame, date | None, str | None]:
        path = self.companies_path
        if path is None:
            warnings.append("industry_mapping_path_unconfigured")
            return pd.DataFrame(), None, None
        if not path.is_file():
            warnings.append("industry_mapping_registry_missing")
            return pd.DataFrame(), None, None
        try:
            frame = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
        except (OSError, UnicodeError, pd.errors.ParserError) as exc:
            warnings.append(f"industry_mapping_registry_read_error:{type(exc).__name__}")
            return pd.DataFrame(), None, None
        if "date" not in frame.columns:
            warnings.append("industry_mapping_observed_date_unrecorded")
        observed_dates = [
            parsed
            for parsed in (_parse_date(item) for item in frame.get("date", ()))
            if parsed is not None
        ]
        available_values = sorted(
            _as_text(item) for item in frame.get("download_time", ()) if _as_text(item)
        )
        available_at = available_values[-1] if available_values else None
        if available_at is None:
            warnings.append("industry_mapping_available_at_unrecorded")
        return frame, max(observed_dates) if observed_dates else None, available_at


def _recent_date_keys(
    connection: sqlite3.Connection, table: str, as_of_date: date, limit: int
) -> list[str]:
    cutoff = _date_key(as_of_date)
    cutoffs = (cutoff, f"{cutoff[:4]}-{cutoff[4:6]}-{cutoff[6:]}", f"{cutoff[:4]}/{cutoff[4:6]}/{cutoff[6:]}")
    values: set[str] = set()
    for raw_cutoff in cutoffs:
        try:
            rows = connection.execute(
                f"SELECT DISTINCT 日期 FROM {table} WHERE 日期 <= ? ORDER BY 日期 DESC LIMIT ?",
                (raw_cutoff, max(1, int(limit))),
            ).fetchall()
        except sqlite3.Error:
            continue
        for row in rows:
            parsed = _parse_date(row[0] if row else None)
            if parsed is not None and parsed <= as_of_date:
                values.add(_date_key(parsed))
        if len(values) >= max(1, int(limit)):
            break
    return sorted(values, reverse=True)[: max(1, int(limit))]


def _read_date_rows(
    connection: sqlite3.Connection,
    table: str,
    columns: tuple[str, ...],
    date_keys: list[str],
) -> pd.DataFrame:
    values: list[str] = []
    for key in date_keys:
        values.extend(
            (
                key,
                f"{key[:4]}-{key[4:6]}-{key[6:]}",
                f"{key[:4]}/{key[4:6]}/{key[6:]}",
            )
        )
    placeholders = ",".join("?" for _ in values)
    sql = (
        f"SELECT {', '.join(columns)} FROM {table} "
        f"WHERE 日期 IN ({placeholders})"
    )
    return pd.read_sql_query(sql, connection, params=values)


class IndustryStrengthService:
    """產出可比產業排名、代表股與 Decision Desk sector snapshot。"""

    source_id = "industry_strength.sqlite_current_research"
    source_version = "industry-strength.current-research.v1"
    mapping_source_id = "meta_data.companies.csv"
    mapping_version = "tw-industry-explicit-map.v1"
    benchmark_source_id = "sqlite.market_indices"

    def __init__(
        self,
        config: Any | None = None,
        *,
        provider: IndustryStrengthDataProvider | None = None,
        companies_path: str | Path | None = None,
        representative_limit: int = 3,
        pit_membership_reader: PITSectorMembershipReader | None = None,
        pit_market_scope: str | None = None,
    ) -> None:
        self.config = config
        if provider is None:
            if config is None or not getattr(config, "db_file", None):
                raise ValueError("IndustryStrengthService 需要 config.db_file 或 provider")
            registry_path = companies_path or getattr(config, "companies_file", None)
            if registry_path is None:
                registry_path = Path(config.meta_data_dir) / "companies.csv"
            provider = SQLiteIndustryStrengthDataProvider(config.db_file, registry_path)
        self.provider = provider
        self.representative_limit = max(1, int(representative_limit))
        self.pit_membership_reader = pit_membership_reader
        self.pit_market_scope = pit_market_scope

    def latest_available_date(self) -> date | None:
        latest = getattr(self.provider, "latest_available_date", None)
        if callable(latest):
            try:
                value = latest()
            except Exception:  # noqa: BLE001
                return None
            return value if isinstance(value, date) else _parse_date(value)
        return None

    def build_snapshot(
        self,
        as_of_date: date,
        *,
        decision_at: datetime | str | None = None,
    ) -> SectorRotationSummary:
        summary = self.build_industry_strength(as_of_date, decision_at=decision_at)
        leading, trailing, intensity = self._rotation_headlines(summary)
        meta: dict[str, object] = {
            "source": self.source_id,
            "source_version": self.source_version,
            "mapping_source_id": summary.mapping_source_id,
            "mapping_version": summary.mapping_version,
            "mapping_observed_date": (
                summary.mapping_observed_date.isoformat()
                if summary.mapping_observed_date
                else None
            ),
            "mapping_available_at": summary.mapping_available_at,
            "mapping_effective_from": (
                summary.mapping_effective_from.isoformat()
                if summary.mapping_effective_from
                else None
            ),
            "historical_pit_eligible": summary.historical_pit_eligible,
            "benchmark_name": summary.benchmark_name,
            "benchmark_source_id": summary.benchmark_source_id,
            "benchmark_observed_date": (
                summary.benchmark_observed_date.isoformat()
                if summary.benchmark_observed_date
                else None
            ),
            "ranking_scope": "within_industry_level",
            "windows": list(summary.windows),
        }
        if "pit_membership" in summary.coverage:
            meta["pit_membership"] = dict(summary.coverage["pit_membership"])
            meta["pit_membership_status"] = summary.coverage.get("pit_membership_status")
            meta["pit_membership_quality"] = summary.coverage.get("pit_membership_quality")
            meta["pit_membership_source_ids"] = list(
                summary.coverage.get("pit_membership_source_ids", ())
            )
            meta["pit_membership_source_hashes"] = list(
                summary.coverage.get("pit_membership_source_hashes", ())
            )
            meta["pit_membership_universe_hash"] = summary.coverage.get(
                "pit_membership_universe_hash"
            )
            meta["pit_membership_rows_hash"] = summary.coverage.get(
                "pit_membership_rows_hash"
            )
            meta["pit_membership_canonical_hash"] = summary.coverage.get(
                "pit_membership_canonical_hash"
            )
        return SectorRotationSummary(
            as_of_date=summary.as_of_date,
            quality=summary.quality,
            warnings=summary.warnings,
            leading_sector=leading,
            trailing_sector=trailing,
            rotation_intensity_bp=intensity,
            meta=meta,
            industry_strength=summary,
        )

    def build_industry_strength(
        self,
        as_of_date: date | None,
        *,
        decision_at: datetime | str | None = None,
    ) -> IndustryStrengthSummary:
        requested = as_of_date or self.latest_available_date()
        if requested is None:
            return IndustryStrengthSummary(
                as_of_date=None,
                quality=DecisionDeskQuality.MISSING,
                warnings=("industry_strength_as_of_unavailable",),
                source_id=self.source_id,
                source_version=self.source_version,
                mapping_source_id=self.mapping_source_id,
                mapping_version=self.mapping_version,
            )
        current_source_date = self.latest_available_date()
        try:
            try:
                data = self.provider.fetch(requested, session_limit=25)
            except TypeError:
                data = self.provider.fetch(requested)  # type: ignore[call-arg]
        except Exception as exc:  # noqa: BLE001
            return IndustryStrengthSummary(
                as_of_date=None,
                quality=DecisionDeskQuality.DEGRADED,
                warnings=(f"industry_strength_provider_error:{type(exc).__name__}",),
                source_id=self.source_id,
                source_version=self.source_version,
                mapping_source_id=self.mapping_source_id,
                mapping_version=self.mapping_version,
            )
        pit_membership = self._read_pit_membership(requested, decision_at=decision_at)
        return self._build_from_data(
            requested,
            data,
            current_source_date=current_source_date,
            pit_membership=pit_membership,
        )

    def build_screening_result(
        self,
        *,
        direction: str,
        period: str,
        top_n: int,
        decision_date: date | None = None,
    ) -> ScreeningResultDTO:
        summary = self.build_industry_strength(decision_date)
        window = 5 if period == "day" else 20
        metric_name = f"excess_{window}d_bp"
        return self._to_screening_result(summary, direction, period, top_n, metric_name, decision_date)

    def _read_pit_membership(
        self,
        requested: date,
        *,
        decision_at: datetime | str | None,
    ) -> PITMembershipReadResult | None:
        reader = self.pit_membership_reader
        if reader is None:
            return None
        cutoff = decision_at or reader.default_decision_at(requested)
        try:
            return reader.read(
                as_of_date=requested,
                decision_at=cutoff,
                market_scope=self.pit_market_scope,
            )
        except Exception as exc:  # noqa: BLE001 - caller remains fail closed
            return PITMembershipReadResult(
                as_of_date=requested,
                decision_at=reader.default_decision_at(requested),
                status="unavailable",
                quality="missing",
                rows=(),
                warnings=(f"pit_membership_reader_error:{type(exc).__name__}",),
                lineage={
                    "reader_schema_version": "pit-sector-membership-reader.v1",
                    "status": "unavailable",
                    "market_scope_requested": self.pit_market_scope,
                    "error": str(exc),
                },
            )

    def _build_from_data(
        self,
        requested: date,
        data: IndustryStrengthData,
        *,
        current_source_date: date | None = None,
        pit_membership: PITMembershipReadResult | None = None,
    ) -> IndustryStrengthSummary:
        warnings = list(data.provider_warnings)
        if pit_membership is None:
            warnings.extend(
                (
                    "industry_mapping_current_research_only",
                    "industry_mapping_historical_pit_unavailable",
                    "industry_mapping_not_for_ml_or_formal_clock",
                    "benchmark_available_at_unrecorded",
                )
            )
        else:
            warnings.extend(pit_membership.warnings)

        clean_index_rows, index_dates, duplicate_index_names = _index_series(data.industry_indices)
        market_series, market_dates, market_warnings = _market_series(data.market_indices)
        warnings.extend(market_warnings)
        # market_indices/TAIEX 定義官方 session；不能因產業資料缺一整日而
        # 將更早的一日重新標成「20 日前」。
        effective = max((item for item in market_dates if item <= requested), default=None)
        if effective is None:
            warnings.append("industry_strength_comparable_date_missing")
            return self._summary_without_rows(
                data,
                warnings,
                mapping_observed_date=data.mapping_observed_date,
                mapping_available_at=data.mapping_available_at,
                pit_membership=pit_membership,
            )
        if effective != requested:
            warnings.append(f"industry_strength_as_of_fallback:{effective.isoformat()}")
        if effective not in index_dates:
            warnings.append("industry_strength_index_effective_date_missing")

        if pit_membership is None:
            mapping = _build_membership_mapping(data.companies)
        else:
            mapping = _build_pit_membership_mapping(
                pit_membership.rows,
                market_scope=self.pit_market_scope,
            )
        warnings.extend(mapping["warnings"])
        mapped_index_names = set(INDUSTRY_CATEGORY_TO_INDEX.values())
        observed_clean_names = set(clean_index_rows)
        unmapped_indices = tuple(sorted(observed_clean_names - mapped_index_names))
        unmapped_categories = tuple(mapping["unmapped_categories"])
        if unmapped_categories:
            warnings.append(f"industry_mapping_unmapped_categories:{len(unmapped_categories)}")
        if unmapped_indices:
            warnings.append(f"industry_mapping_unmapped_indices:{len(unmapped_indices)}")

        mapping_allowed = (
            pit_membership.industry_filter_usable
            if pit_membership is not None
            else _mapping_is_available_at(
                effective,
                data.mapping_observed_date,
                data.mapping_available_at,
                current_source_date=current_source_date,
            )
        )
        if not mapping_allowed:
            warnings.append(
                (
                    "industry_mapping_pit_taxonomy_unverified"
                    if pit_membership is not None and pit_membership.usable
                    else "industry_mapping_pit_not_available_at_as_of"
                )
                if pit_membership is not None
                else "industry_mapping_not_available_at_as_of"
            )
            return self._summary_without_rows(
                data,
                warnings,
                as_of_date=effective,
                mapping_observed_date=(
                    pit_membership.as_of_date
                    if pit_membership is not None
                    else data.mapping_observed_date
                ),
                mapping_available_at=(
                    _pit_available_at_text(pit_membership)
                    if pit_membership is not None
                    else data.mapping_available_at
                ),
                unmapped_industry_categories=unmapped_categories,
                unmapped_index_names=unmapped_indices,
                duplicate_membership_codes=tuple(mapping["duplicate_codes"]),
                ambiguous_membership_codes=tuple(mapping["ambiguous_codes"]),
                pit_membership=pit_membership,
            )

        session_dates = sorted(item for item in market_dates if item <= effective)
        market_returns: dict[int, int | None] = {}
        endpoints: dict[int, tuple[date, date] | None] = {}
        for window in (5, 20):
            if len(session_dates) > window:
                start_date = session_dates[-(window + 1)]
                endpoints[window] = (start_date, effective)
                market_returns[window] = _return_bp(
                    market_series.get(start_date), market_series.get(effective)
                )
            else:
                endpoints[window] = None
                market_returns[window] = None
                warnings.append(f"industry_strength_insufficient_common_window:{window}d")

        price_series, _, duplicate_price_codes = _price_series(data.daily_prices)
        stock_names = mapping["stock_names"]
        price_dates = set(item for series in price_series.values() for item in series)
        if effective not in price_dates:
            warnings.append("industry_strength_price_effective_date_missing")

        rows: list[IndustryStrengthRow] = []
        price_missing_counts = {5: 0, 20: 0}
        for category, index_name in INDUSTRY_CATEGORY_TO_INDEX.items():
            members = tuple(mapping["members"].get(category, ())) if mapping_allowed else ()
            row_warnings: list[str] = []
            excluded_members = tuple(
                mapping["market_excluded_members"].get(category, ())
            )
            if excluded_members:
                row_warnings.append(
                    f"industry_stock_market_scope_gap:{len(excluded_members)}"
                )
            if not mapping_allowed:
                row_warnings.append(
                    "industry_mapping_pit_not_applicable"
                    if pit_membership is not None
                    else "industry_mapping_current_registry_not_applicable"
                )
            if index_name not in observed_clean_names:
                row_warnings.append("industry_index_observation_missing")
            index_values = clean_index_rows.get(index_name, {})
            returns: dict[int, int | None] = {}
            excess: dict[int, int | None] = {}
            eligible_counts: dict[int, int] = {}
            coverage: dict[int, int | None] = {}
            for window in (5, 20):
                endpoint = endpoints[window]
                if endpoint is None:
                    returns[window] = None
                    excess[window] = None
                    row_warnings.append(f"industry_index_insufficient_window:{window}d")
                else:
                    start_date, end_date = endpoint
                    returns[window] = _return_bp(
                        index_values.get(start_date), index_values.get(end_date)
                    )
                    if returns[window] is None:
                        row_warnings.append(f"industry_index_insufficient_window:{window}d")
                    market_return = market_returns[window]
                    industry_return = returns[window]
                    excess[window] = (
                        industry_return - market_return
                        if industry_return is not None and market_return is not None
                        else None
                    )
                    if market_return is None:
                        row_warnings.append(f"benchmark_return_missing:{window}d")

                eligible = 0
                for code in members:
                    if endpoint is not None and _return_bp(
                        price_series.get(code, {}).get(endpoint[0]),
                        price_series.get(code, {}).get(endpoint[1]),
                    ) is not None:
                        eligible += 1
                    else:
                        price_missing_counts[window] += 1
                eligible_counts[window] = eligible
                coverage[window] = (
                    eligible * 10000 // len(members) if members else None
                )
                if members and coverage[window] != 10000:
                    row_warnings.append(
                        f"industry_stock_coverage_partial:{window}d:{eligible}/{len(members)}"
                    )
                if not members:
                    row_warnings.append("industry_stock_membership_missing")

            representatives = self._representatives(
                category=category,
                members=members,
                price_series=price_series,
                stock_names=stock_names,
                endpoints=endpoints,
                market_returns=market_returns,
            )
            if not representatives and members:
                row_warnings.append("industry_representative_stock_missing")
            index_close = _format_decimal(index_values.get(effective))
            row_quality = (
                DecisionDeskQuality.OBSERVED
                if returns[5] is not None
                and returns[20] is not None
                and members
                and coverage[5] == 10000
                and coverage[20] == 10000
                else DecisionDeskQuality.DEGRADED
                if index_name in observed_clean_names
                else DecisionDeskQuality.MISSING
            )
            rows.append(
                IndustryStrengthRow(
                    industry_name=category,
                    index_name=index_name,
                    industry_level=industry_level(index_name),
                    market_scope=str(mapping.get("market_scope", "twse")),
                    index_close=index_close,
                    return_5d_bp=returns[5],
                    return_20d_bp=returns[20],
                    market_return_5d_bp=market_returns[5],
                    market_return_20d_bp=market_returns[20],
                    excess_5d_bp=excess[5],
                    excess_20d_bp=excess[20],
                    constituent_count=len(members),
                    eligible_stock_count_5d=eligible_counts[5],
                    eligible_stock_count_20d=eligible_counts[20],
                    coverage_5d_bp=coverage[5],
                    coverage_20d_bp=coverage[20],
                    quality=row_quality,
                    warnings=tuple(row_warnings),
                    representative_stocks=representatives,
                )
            )

        rows = _assign_ranks(rows)
        rankable_5 = sum(1 for row in rows if row.excess_5d_bp is not None)
        rankable_20 = sum(1 for row in rows if row.excess_20d_bp is not None)
        if rankable_5 == 0 and rankable_20 == 0:
            warnings.append("industry_strength_no_rankable_rows")
        if duplicate_index_names:
            warnings.append(f"industry_index_duplicate_observations:{len(duplicate_index_names)}")
        if duplicate_price_codes:
            warnings.append(f"industry_stock_duplicate_price_observations:{len(duplicate_price_codes)}")

        coverage_summary: dict[str, object] = {
            "mapping_registry_row_count": mapping["row_count"],
            "mapping_unique_code_count": mapping["unique_code_count"],
            "mapping_unambiguous_mapped_code_count": mapping["mapped_code_count"],
            "current_research_market_aligned_mapped_code_count": (
                mapping["mapped_code_count"] if pit_membership is None else 0
            ),
            "historical_pit_eligible_code_count": 0,
            "mapping_mode": (
                "current_research_only"
                if pit_membership is None
                else "pit_accepted_prospective"
            ),
            "mapping_unmapped_category_count": len(unmapped_categories),
            "mapping_duplicate_membership_count": len(mapping["duplicate_codes"]),
            "mapping_ambiguous_membership_count": len(mapping["ambiguous_codes"]),
            "observed_pure_index_count": len(observed_clean_names),
            "mapped_industry_row_count": len(rows),
            "rankable_industry_row_count_5d": rankable_5,
            "rankable_industry_row_count_20d": rankable_20,
            "price_missing_or_suspended_count_5d": price_missing_counts[5],
            "price_missing_or_suspended_count_20d": price_missing_counts[20],
            "market_scope_excluded_code_count": mapping["market_excluded_code_count"],
            "market_scope_ambiguous_code_count": len(mapping["ambiguous_market_codes"]),
            "coverage_denominator": (
                "current_unambiguous_company_registry"
                if pit_membership is None
                else "accepted_pit_membership_rows"
            ),
            "market_scope": mapping.get("market_scope", "twse"),
            "market_scope_source_id": (
                "meta_data.companies.csv:type"
                if pit_membership is None
                else "pit_sector_membership_reader"
            ),
            "ranking_scope": "within_industry_level",
            "session_source": "sqlite.market_indices:TAIEX",
            "benchmark_available_at_status": "not_recorded",
            "pit_history_status": (
                "unavailable_current_research_only"
                if pit_membership is None
                else "prospective_accepted_not_historical"
            ),
            "data_window_end": effective.isoformat(),
        }
        if pit_membership is not None:
            coverage_summary["pit_membership"] = dict(pit_membership.lineage)
            coverage_summary["pit_membership_status"] = pit_membership.status
            coverage_summary["pit_membership_quality"] = pit_membership.quality
            coverage_summary["pit_membership_as_of_date"] = pit_membership.as_of_date.isoformat()
            coverage_summary["pit_membership_decision_at"] = pit_membership.decision_at.isoformat()
            coverage_summary["pit_membership_source_ids"] = _as_text_list(
                pit_membership.lineage.get("source_ids", ())
            )
            coverage_summary["pit_membership_source_hashes"] = _as_text_list(
                pit_membership.lineage.get("source_hashes", ())
            )
            coverage_summary["pit_membership_universe_hash"] = pit_membership.lineage.get(
                "universe_hash"
            )
            coverage_summary["pit_membership_rows_hash"] = pit_membership.lineage.get(
                "rows_hash"
            )
            coverage_summary["pit_membership_canonical_hash"] = pit_membership.lineage.get(
                "canonical_hash"
            )
            coverage_summary["pit_membership_available_at"] = pit_membership.lineage.get(
                "available_at", []
            )
            coverage_summary["pit_membership_effective_from"] = pit_membership.lineage.get(
                "effective_from", []
            )
            coverage_summary["pit_membership_effective_to"] = pit_membership.lineage.get(
                "effective_to", []
            )
            coverage_summary["pit_membership_market_scopes"] = pit_membership.lineage.get(
                "market_scopes", []
            )
        return IndustryStrengthSummary(
            as_of_date=effective,
            quality=DecisionDeskQuality.DEGRADED,
            warnings=tuple(dict.fromkeys(warnings)),
            windows=(5, 20),
            source_id=self.source_id,
            source_version=self.source_version,
            mapping_source_id=(
                self.mapping_source_id
                if pit_membership is None
                else "data_module.pit_sector_membership_reader"
            ),
            mapping_version=(
                self.mapping_version
                if pit_membership is None
                else "pit-sector-membership-reader.v1"
            ),
            mapping_observed_date=(
                data.mapping_observed_date
                if pit_membership is None
                else pit_membership.as_of_date
            ),
            mapping_available_at=(
                data.mapping_available_at
                if pit_membership is None
                else _pit_available_at_text(pit_membership)
            ),
            mapping_effective_from=(
                data.mapping_observed_date
                if pit_membership is None
                else _pit_effective_from(pit_membership)
            ),
            historical_pit_eligible=False,
            benchmark_name="TAIEX" if market_series else None,
            benchmark_source_id=self.benchmark_source_id,
            benchmark_observed_date=effective if market_series else None,
            benchmark_available_at=None,
            rows=tuple(rows),
            unmapped_industry_categories=unmapped_categories,
            unmapped_index_names=unmapped_indices,
            duplicate_membership_codes=tuple(mapping["duplicate_codes"]),
            ambiguous_membership_codes=tuple(mapping["ambiguous_codes"]),
            coverage=coverage_summary,
        )

    def _summary_without_rows(
        self,
        data: IndustryStrengthData,
        warnings: list[str],
        *,
        as_of_date: date | None = None,
        mapping_observed_date: date | None,
        mapping_available_at: str | None,
        unmapped_industry_categories: tuple[str, ...] = (),
        unmapped_index_names: tuple[str, ...] = (),
        duplicate_membership_codes: tuple[str, ...] = (),
        ambiguous_membership_codes: tuple[str, ...] = (),
        pit_membership: PITMembershipReadResult | None = None,
    ) -> IndustryStrengthSummary:
        pit_mode = pit_membership is not None
        coverage: dict[str, Any] = {
            "coverage_denominator": (
                "accepted_pit_membership_rows"
                if pit_mode
                else "current_unambiguous_company_registry"
            ),
            "current_research_market_aligned_mapped_code_count": 0,
            "historical_pit_eligible_code_count": 0,
            "mapping_mode": (
                "pit_unavailable_fail_closed" if pit_mode else "current_research_only"
            ),
            "ranking_scope": "within_industry_level",
            "pit_history_status": (
                "prospective_unavailable"
                if pit_mode
                else "unavailable_current_research_only"
            ),
            "mapping_applicable_at_as_of": False if as_of_date is not None else None,
        }
        pit_as_of_date = (
            pit_membership.as_of_date if pit_membership is not None else None
        )
        if pit_membership is not None:
            coverage["pit_membership"] = dict(pit_membership.lineage)
            coverage["pit_membership_status"] = pit_membership.status
            coverage["pit_membership_quality"] = pit_membership.quality
            coverage["pit_membership_source_ids"] = _as_text_list(
                pit_membership.lineage.get("source_ids", ())
            )
            coverage["pit_membership_source_hashes"] = _as_text_list(
                pit_membership.lineage.get("source_hashes", ())
            )
            coverage["pit_membership_universe_hash"] = pit_membership.lineage.get(
                "universe_hash"
            )
            coverage["pit_membership_rows_hash"] = pit_membership.lineage.get("rows_hash")
            coverage["pit_membership_canonical_hash"] = pit_membership.lineage.get(
                "canonical_hash"
            )
        return IndustryStrengthSummary(
            as_of_date=as_of_date,
            quality=DecisionDeskQuality.MISSING,
            warnings=tuple(dict.fromkeys(warnings)),
            source_id=self.source_id,
            source_version=self.source_version,
            mapping_source_id=(
                self.mapping_source_id
                if not pit_mode
                else "data_module.pit_sector_membership_reader"
            ),
            mapping_version=(
                self.mapping_version
                if not pit_mode
                else "pit-sector-membership-reader.v1"
            ),
            mapping_observed_date=(
                mapping_observed_date
                if not pit_mode
                else pit_as_of_date
            ),
            mapping_available_at=(
                mapping_available_at
                if not pit_mode
                else _pit_available_at_text(pit_membership)
            ),
            mapping_effective_from=(
                mapping_observed_date
                if not pit_mode
                else _pit_effective_from(pit_membership)
            ),
            historical_pit_eligible=False,
            benchmark_name=None,
            benchmark_source_id=self.benchmark_source_id,
            rows=(),
            unmapped_industry_categories=unmapped_industry_categories,
            unmapped_index_names=unmapped_index_names,
            duplicate_membership_codes=duplicate_membership_codes,
            ambiguous_membership_codes=ambiguous_membership_codes,
            coverage=coverage,
        )

    def _representatives(
        self,
        *,
        category: str,
        members: tuple[str, ...],
        price_series: dict[str, dict[date, Decimal]],
        stock_names: dict[str, str],
        endpoints: dict[int, tuple[date, date] | None],
        market_returns: dict[int, int | None],
    ) -> tuple[IndustryRepresentativeStock, ...]:
        candidates: list[IndustryRepresentativeStock] = []
        for code in members:
            series = price_series.get(code, {})
            returns: dict[int, int | None] = {}
            excess: dict[int, int | None] = {}
            for window in (5, 20):
                endpoint = endpoints[window]
                returns[window] = (
                    _return_bp(series.get(endpoint[0]), series.get(endpoint[1]))
                    if endpoint is not None
                    else None
                )
                stock_return = returns[window]
                benchmark_return = market_returns[window]
                excess[window] = (
                    stock_return - benchmark_return
                    if stock_return is not None and benchmark_return is not None
                    else None
                )
            if returns[5] is None and returns[20] is None:
                continue
            candidates.append(
                IndustryRepresentativeStock(
                    stock_code=code,
                    stock_name=stock_names.get(code, code),
                    industry_name=category,
                    return_5d_bp=returns[5],
                    return_20d_bp=returns[20],
                    excess_5d_bp=excess[5],
                    excess_20d_bp=excess[20],
                    quality=(
                        DecisionDeskQuality.OBSERVED
                        if returns[5] is not None and returns[20] is not None
                        else DecisionDeskQuality.DEGRADED
                    ),
                    warnings=(
                        ()
                        if returns[5] is not None and returns[20] is not None
                        else ("industry_stock_insufficient_window",)
                    ),
                )
            )
        candidates.sort(
            key=lambda item: (
                -(item.excess_20d_bp if item.excess_20d_bp is not None else item.return_20d_bp or -10**12),
                item.stock_code,
            )
        )
        return tuple(candidates[: self.representative_limit])

    @staticmethod
    def _rotation_headlines(
        summary: IndustryStrengthSummary,
    ) -> tuple[str | None, str | None, int | None]:
        for level in ("leaf", "aggregate"):
            candidates = [
                row
                for row in summary.rows
                if row.industry_level == level and row.excess_20d_bp is not None
            ]
            if not candidates:
                continue
            ordered = sorted(
                candidates,
                key=lambda row: (-int(row.excess_20d_bp or 0), row.industry_name),
            )
            leading = ordered[0].industry_name
            trailing = ordered[-1].industry_name if len(ordered) > 1 else None
            intensity = (
                int(ordered[0].excess_20d_bp or 0) - int(ordered[-1].excess_20d_bp or 0)
                if len(ordered) > 1
                else None
            )
            return leading, trailing, intensity
        return None, None, None

    @staticmethod
    def _to_screening_result(
        summary: IndustryStrengthSummary,
        direction: str,
        period: str,
        top_n: int,
        metric_name: str,
        decision_date: date | None,
    ) -> ScreeningResultDTO:
        metric = metric_name
        selected: list[IndustryStrengthRow] = []
        for level in ("aggregate", "leaf"):
            level_rows = [
                row for row in summary.rows if row.industry_level == level and getattr(row, metric) is not None
            ]
            level_rows.sort(
                key=lambda row: (
                    int(getattr(row, metric) or 0)
                    if direction == "weak"
                    else -int(getattr(row, metric) or 0),
                    row.industry_name,
                )
            )
            selected.extend(level_rows[: max(0, int(top_n))])

        records: list[dict[str, Any]] = []
        level_ranks: dict[str, int] = defaultdict(int)
        for row in selected:
            level_ranks[row.industry_level] += 1
            representatives = row.representative_stocks
            records.append(
                {
                    "排名": level_ranks[row.industry_level],
                    "產業名稱": row.industry_name,
                    "指數名稱": row.index_name,
                    "產業層級": row.industry_level,
                    "市場範圍": row.market_scope,
                    "收盤指數": row.index_close,
                    "漲幅%": _format_percent_bp(row.return_5d_bp if period == "day" else row.return_20d_bp),
                    "5日漲幅%": _format_percent_bp(row.return_5d_bp),
                    "20日漲幅%": _format_percent_bp(row.return_20d_bp),
                    "5日超額%": _format_percent_bp(row.excess_5d_bp),
                    "20日超額%": _format_percent_bp(row.excess_20d_bp),
                    "5日漲幅BP": row.return_5d_bp,
                    "20日漲幅BP": row.return_20d_bp,
                    "5日超額BP": row.excess_5d_bp,
                    "20日超額BP": row.excess_20d_bp,
                    "相對大盤超額BP": getattr(row, metric),
                    "成分數": row.constituent_count,
                    "5日有效成分": row.eligible_stock_count_5d,
                    "20日有效成分": row.eligible_stock_count_20d,
                    "5日覆蓋率BP": row.coverage_5d_bp,
                    "20日覆蓋率BP": row.coverage_20d_bp,
                    "5日覆蓋率%": _format_percent_bp(row.coverage_5d_bp),
                    "20日覆蓋率%": _format_percent_bp(row.coverage_20d_bp),
                    "代表股票代號": ", ".join(item.stock_code for item in representatives),
                    "代表股票名稱": ", ".join(item.stock_name for item in representatives),
                    "代表股票": ", ".join(
                        f"{item.stock_code} {item.stock_name}" for item in representatives
                    ),
                    "資料日": summary.as_of_date.isoformat() if summary.as_of_date else None,
                    "資料來源": summary.source_id,
                    "資料版本": summary.source_version,
                    "映射來源": summary.mapping_source_id,
                    "映射版本": summary.mapping_version,
                    "映射觀測日": (
                        summary.mapping_observed_date.isoformat()
                        if summary.mapping_observed_date
                        else None
                    ),
                    "映射可得時間": summary.mapping_available_at,
                    "資料品質": row.quality.value,
                }
            )
        warnings = list(summary.warnings)
        if not records:
            warnings.append("industry_strength_no_rankable_industries")
        return ScreeningResultDTO(
            result_kind="industries",
            direction=direction,
            period=period,
            decision_date=decision_date,
            effective_date=summary.as_of_date,
            quality=summary.quality,
            eligible_universe_size=len(summary.rows),
            rows=tuple(records),
            warnings=tuple(dict.fromkeys(warnings)),
            source_id=summary.source_id,
            source_version=summary.source_version,
            ranking_method="industry-strength-relative-to-taiex-within-level",
        )


def _index_series(
    frame: pd.DataFrame,
) -> tuple[dict[str, dict[date, Decimal]], set[date], set[str]]:
    result: dict[str, dict[date, Decimal]] = defaultdict(dict)
    seen: dict[tuple[str, date], int] = defaultdict(int)
    dates: set[date] = set()
    duplicate_names: set[str] = set()
    for record in frame.to_dict(orient="records") if isinstance(frame, pd.DataFrame) else ():
        observation_date = _parse_date(record.get("日期") or record.get("date"))
        name = _as_text(record.get("指數名稱") or record.get("sector"))
        if observation_date is None or not is_usable_industry_index_name(name):
            continue
        value = _to_decimal(record.get("收盤指數") or record.get("close"))
        if value is None:
            continue
        dates.add(observation_date)
        key = (name, observation_date)
        seen[key] += 1
        if seen[key] > 1:
            duplicate_names.add(name)
            result[name].pop(observation_date, None)
            continue
        result[name][observation_date] = value
    return dict(result), dates, duplicate_names


def _market_series(
    frame: pd.DataFrame,
) -> tuple[dict[date, Decimal], set[date], list[str]]:
    candidates: dict[str, dict[date, Decimal]] = defaultdict(dict)
    seen: dict[tuple[str, date], int] = defaultdict(int)
    warnings: list[str] = []
    duplicate_keys: set[tuple[str, date]] = set()
    for record in frame.to_dict(orient="records") if isinstance(frame, pd.DataFrame) else ():
        observation_date = _parse_date(record.get("日期") or record.get("date"))
        name = _as_text(record.get("指數名稱") or record.get("index"))
        value = _to_decimal(record.get("收盤指數") or record.get("close"))
        if observation_date is None or value is None:
            continue
        key = (name, observation_date)
        seen[key] += 1
        if seen[key] > 1:
            warnings.append(f"benchmark_duplicate_observation:{name}:{observation_date.isoformat()}")
            duplicate_keys.add(key)
            candidates[name].pop(observation_date, None)
            continue
        candidates[name][observation_date] = value
    # 只接受已驗證的 TAIEX 名稱；不能把任意市場／策略指數冒充 benchmark。
    preferred = "TAIEX" if "TAIEX" in candidates else None
    if preferred is None:
        available = ",".join(sorted(candidates)) or "none"
        warnings.append(f"benchmark_name_missing:TAIEX:available={available}")
        return {}, set(), warnings
    series = {
        observation_date: value
        for observation_date, value in candidates[preferred].items()
        if (preferred, observation_date) not in duplicate_keys
    }
    return dict(series), set(series), warnings


def _price_series(
    frame: pd.DataFrame,
) -> tuple[dict[str, dict[date, Decimal]], dict[str, str], set[str]]:
    result: dict[str, dict[date, Decimal]] = defaultdict(dict)
    names: dict[str, str] = {}
    seen: dict[tuple[str, date], int] = defaultdict(int)
    duplicate_codes: set[str] = set()
    for record in frame.to_dict(orient="records") if isinstance(frame, pd.DataFrame) else ():
        observation_date = _parse_date(record.get("日期") or record.get("date"))
        code = _as_text(record.get("證券代號") or record.get("stock_id"))
        if observation_date is None or not code:
            continue
        value = _to_decimal(record.get("收盤價") or record.get("close"))
        if value is None or value <= Decimal("0"):
            continue
        name = _as_text(record.get("證券名稱") or record.get("stock_name"))
        names.setdefault(code, name or code)
        key = (code, observation_date)
        seen[key] += 1
        if seen[key] > 1:
            duplicate_codes.add(code)
            continue
        result[code][observation_date] = value
    for code in duplicate_codes:
        result.pop(code, None)
    return dict(result), names, duplicate_codes


def _build_membership_mapping(frame: pd.DataFrame) -> dict[str, Any]:
    members: dict[str, set[str]] = defaultdict(set)
    market_excluded_members: dict[str, set[str]] = defaultdict(set)
    stock_names: dict[str, str] = {}
    code_categories: dict[str, set[str]] = defaultdict(set)
    code_market_types: dict[str, set[str]] = defaultdict(set)
    duplicate_codes: set[str] = set()
    row_count = 0
    for record in frame.to_dict(orient="records") if isinstance(frame, pd.DataFrame) else ():
        code = _as_text(record.get("stock_id") or record.get("證券代號"))
        category = _as_text(record.get("industry_category") or record.get("產業別"))
        if not code or not category:
            continue
        row_count += 1
        code_categories[code].add(category)
        market_type = _as_text(record.get("type") or record.get("market_type")).lower()
        code_market_types[code].add(market_type)
        stock_names.setdefault(code, _as_text(record.get("stock_name") or record.get("證券名稱")) or code)
    for code, categories in code_categories.items():
        if len(categories) > 1:
            continue
        category = next(iter(categories))
        market_types = code_market_types.get(code, set())
        if (
            category in INDUSTRY_CATEGORY_TO_INDEX
            and market_types == {INDUSTRY_CATEGORY_MARKET_SCOPE[category]}
        ):
            members[category].add(code)
        elif category in INDUSTRY_CATEGORY_TO_INDEX:
            market_excluded_members[category].add(code)
    category_occurrences: dict[tuple[str, str], int] = defaultdict(int)
    for record in frame.to_dict(orient="records") if isinstance(frame, pd.DataFrame) else ():
        code = _as_text(record.get("stock_id") or record.get("證券代號"))
        category = _as_text(record.get("industry_category") or record.get("產業別"))
        if code and category:
            category_occurrences[(code, category)] += 1
            if category_occurrences[(code, category)] > 1:
                duplicate_codes.add(code)
    ambiguous_codes = sorted(code for code, categories in code_categories.items() if len(categories) > 1)
    ambiguous_market_codes = sorted(
        code for code, market_types in code_market_types.items() if len(market_types) != 1
    )
    unmapped_categories = sorted(
        category for categories in code_categories.values() for category in categories
        if category not in INDUSTRY_CATEGORY_TO_INDEX
    )
    return {
        "members": {key: tuple(sorted(value)) for key, value in members.items()},
        "stock_names": stock_names,
        "duplicate_codes": tuple(sorted(duplicate_codes)),
        "ambiguous_codes": tuple(ambiguous_codes),
        "unmapped_categories": tuple(sorted(set(unmapped_categories))),
        "row_count": row_count,
        "unique_code_count": len(code_categories),
        "mapped_code_count": sum(
            1
            for code, categories in code_categories.items()
            if len(categories) == 1 and next(iter(categories)) in INDUSTRY_CATEGORY_TO_INDEX
            and code_market_types.get(code) == {
                INDUSTRY_CATEGORY_MARKET_SCOPE[next(iter(categories))]
            }
        ),
        "market_excluded_members": {
            key: tuple(sorted(value)) for key, value in market_excluded_members.items()
        },
        "market_excluded_code_count": sum(len(value) for value in market_excluded_members.values()),
        "ambiguous_market_codes": tuple(ambiguous_market_codes),
        "warnings": tuple(
            item
            for item in (
                f"industry_mapping_duplicate_memberships:{len(duplicate_codes)}"
                if duplicate_codes
                else "",
                f"industry_mapping_ambiguous_memberships:{len(ambiguous_codes)}"
                if ambiguous_codes
                else "",
                f"industry_mapping_market_scope_exclusions:{sum(len(value) for value in market_excluded_members.values())}"
                if market_excluded_members
                else "",
                f"industry_mapping_ambiguous_market_types:{len(ambiguous_market_codes)}"
                if ambiguous_market_codes
                else "",
            )
            if item
        ),
    }


def _build_pit_membership_mapping(
    rows: tuple[PITMembershipRow, ...],
    *,
    market_scope: str | None,
) -> dict[str, Any]:
    """把 reader 已驗證的 PIT rows 轉成 service 既有的 in-memory mapping。"""

    members: dict[str, set[str]] = defaultdict(set)
    market_excluded_members: dict[str, set[str]] = defaultdict(set)
    stock_names: dict[str, str] = {}
    code_categories: dict[str, set[str]] = defaultdict(set)
    code_markets: dict[str, set[str]] = defaultdict(set)
    duplicate_codes: set[str] = set()
    unmapped_categories: set[str] = set()
    seen_natural_keys: set[tuple[str, str, str, str]] = set()
    row_count = 0
    for row in rows:
        if market_scope is not None and row.market_scope != market_scope:
            continue
        row_count += 1
        code = str(row.symbol).strip()
        category = (row.industry_category or "").strip()
        category_key = category or f"sector_id:{row.sector_id}"
        if not category or category not in INDUSTRY_CATEGORY_TO_INDEX:
            unmapped_categories.add(category_key)
        code_categories[code].add(category_key)
        code_markets[code].add(row.market_scope)
        stock_names.setdefault(code, code)
        natural_key = (
            code,
            row.available_at.isoformat(),
            row.effective_from.isoformat(),
            row.sector_id,
        )
        if natural_key in seen_natural_keys:
            duplicate_codes.add(code)
        seen_natural_keys.add(natural_key)

    for code, categories in code_categories.items():
        if len(categories) != 1:
            continue
        category = next(iter(categories))
        markets = code_markets.get(code, set())
        if category in INDUSTRY_CATEGORY_TO_INDEX and len(markets) == 1:
            members[category].add(code)

    ambiguous_codes = sorted(
        code for code, categories in code_categories.items() if len(categories) > 1
    )
    ambiguous_market_codes = sorted(
        code for code, markets in code_markets.items() if len(markets) != 1
    )
    mapped_code_count = sum(
        1
        for code, categories in code_categories.items()
        if len(categories) == 1
        and next(iter(categories)) in INDUSTRY_CATEGORY_TO_INDEX
        and len(code_markets.get(code, set())) == 1
    )
    scopes = sorted({row.market_scope for row in rows if market_scope is None or row.market_scope == market_scope})
    resolved_scope = market_scope or "+".join(scopes) or "none"
    warnings = tuple(
        item
        for item in (
            f"industry_mapping_duplicate_memberships:{len(duplicate_codes)}"
            if duplicate_codes
            else "",
            f"industry_mapping_ambiguous_memberships:{len(ambiguous_codes)}"
            if ambiguous_codes
            else "",
            f"industry_mapping_unmapped_categories:{len(unmapped_categories)}"
            if unmapped_categories
            else "",
            f"industry_mapping_ambiguous_market_types:{len(ambiguous_market_codes)}"
            if ambiguous_market_codes
            else "",
        )
        if item
    )
    return {
        "members": {key: tuple(sorted(value)) for key, value in members.items()},
        "stock_names": stock_names,
        "duplicate_codes": tuple(sorted(duplicate_codes)),
        "ambiguous_codes": tuple(ambiguous_codes),
        "unmapped_categories": tuple(sorted(unmapped_categories)),
        "row_count": row_count,
        "unique_code_count": len(code_categories),
        "mapped_code_count": mapped_code_count,
        "market_excluded_members": {
            key: tuple(sorted(value)) for key, value in market_excluded_members.items()
        },
        "market_excluded_code_count": 0,
        "ambiguous_market_codes": tuple(ambiguous_market_codes),
        "market_scope": resolved_scope,
        "warnings": warnings,
    }


def _pit_available_at_text(result: PITMembershipReadResult | None) -> str | None:
    if result is None:
        return None
    values = result.lineage.get("available_at", ())
    if isinstance(values, (list, tuple)):
        normalized = sorted(str(item) for item in values if str(item).strip())
        return ",".join(normalized) if normalized else None
    return str(values) if values else None


def _pit_effective_from(result: PITMembershipReadResult | None) -> date | None:
    if result is None:
        return None
    values = [row.effective_from for row in result.rows]
    if values:
        return min(values)
    raw_values = result.lineage.get("effective_from", ())
    parsed = [_parse_date(item) for item in raw_values] if isinstance(raw_values, (list, tuple)) else []
    return min(item for item in parsed if item is not None) if any(parsed) else None


def _mapping_is_available_at(
    effective: date,
    observed_date: date | None,
    available_at: str | None,
    *,
    current_source_date: date | None,
) -> bool:
    # available/effective 證據不完整時，只能在 provider 明確指出的最新
    # current research session 使用；不得放行成歷史映射。
    if observed_date is None:
        return current_source_date is not None and effective == current_source_date
    if effective < observed_date:
        return False
    available_date = _parse_date(available_at)
    if available_at and available_date is None:
        return current_source_date is not None and effective == current_source_date
    if not available_at:
        return current_source_date is not None and effective == current_source_date
    if available_date is not None and effective < available_date:
        return False
    return True


def _assign_ranks(rows: list[IndustryStrengthRow]) -> list[IndustryStrengthRow]:
    rank_maps: dict[tuple[str, int], dict[str, int]] = {}
    for level in ("aggregate", "leaf"):
        for window in (5, 20):
            ordered = sorted(
                (
                    row
                    for row in rows
                    if row.industry_level == level and getattr(row, f"excess_{window}d_bp") is not None
                ),
                key=lambda row: (-int(getattr(row, f"excess_{window}d_bp") or 0), row.industry_name),
            )
            rank_maps[(level, window)] = {
                row.industry_name: index for index, row in enumerate(ordered, start=1)
            }
    ranked: list[IndustryStrengthRow] = []
    for row in rows:
        ranked.append(
            IndustryStrengthRow(
                industry_name=row.industry_name,
                index_name=row.index_name,
                industry_level=row.industry_level,
                market_scope=row.market_scope,
                index_close=row.index_close,
                return_5d_bp=row.return_5d_bp,
                return_20d_bp=row.return_20d_bp,
                market_return_5d_bp=row.market_return_5d_bp,
                market_return_20d_bp=row.market_return_20d_bp,
                excess_5d_bp=row.excess_5d_bp,
                excess_20d_bp=row.excess_20d_bp,
                rank_5d=rank_maps[(row.industry_level, 5)].get(row.industry_name),
                rank_20d=rank_maps[(row.industry_level, 20)].get(row.industry_name),
                constituent_count=row.constituent_count,
                eligible_stock_count_5d=row.eligible_stock_count_5d,
                eligible_stock_count_20d=row.eligible_stock_count_20d,
                coverage_5d_bp=row.coverage_5d_bp,
                coverage_20d_bp=row.coverage_20d_bp,
                quality=row.quality,
                warnings=row.warnings,
                representative_stocks=row.representative_stocks,
            )
        )
    return ranked
