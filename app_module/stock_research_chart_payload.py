"""個股研究報告的唯讀原生圖表投影契約。

此模組只投影傳入的 report，不讀取行情、不推導指標，也不授予歷史 PIT
資格。價格列、圖表與數值表共用同一組 Decimal DTO。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from zoneinfo import ZoneInfo
import json
from app_module.saved_stock_technical_chart import read_saved_technical_chart
from app_module.stock_research_chart_markers import (
    StockChartMarkerDTO, StockChartMarkerIdentityDTO, verified_stock_chart_markers,
)

from app_module.stock_research_report_dtos import (
    StockEvidenceEventDTO,
    StockPricePointDTO,
    StockResearchReportDTO,
    StockTechnicalHistoryRowDTO,
    StockTechnicalSnapshotDTO,
    stock_technical_history_row_fingerprint_sha256,
    technical_history_saved_scope_limitation,
)
from app_module.stock_research_report_provider_adapters import (
    stock_price_row_fingerprint_sha256,
)


_TAIPEI = ZoneInfo("Asia/Taipei")


class StockChartProjectionStatus(str, Enum):
    READY = "ready"
    UNKNOWN = "unknown"
    REJECTED = "rejected"


@dataclass(frozen=True)
class StockChartTechnicalPointDTO:
    data_date: str
    value: Decimal | None
    source_id: str = ""
    source_row_hash: str = ""
    available_at: str = ""


@dataclass(frozen=True)
class StockChartTechnicalLineDTO:
    key: str
    label: str
    points: tuple[StockChartTechnicalPointDTO, ...] = ()


@dataclass(frozen=True)
class StockChartPayloadDTO:
    stock_code: str
    cutoff_date: str
    report_as_of: str
    source_context: tuple[tuple[str, str], ...] = ()
    source_context_status: str = "unknown"
    price_source_status: str = "unknown"
    price_hash_status: str = "unknown"
    price_availability_status: str = "unknown"
    price_points: tuple[StockPricePointDTO, ...] = ()
    technical_snapshot: StockTechnicalSnapshotDTO | None = None
    technical_status: str = "unknown"
    technical_lines: tuple[StockChartTechnicalLineDTO, ...] = ()
    evidence_markers: tuple[StockEvidenceEventDTO, ...] = ()
    unverified_marker_candidates: tuple[StockEvidenceEventDTO, ...] = ()
    marker_status: str = "unknown"
    historical_pit_eligible: bool = False
    limitations: tuple[str, ...] = ()
    technical_history_status: str = "unknown"
    technical_history_limitations: tuple[str, ...] = ()
    verified_markers: tuple[StockChartMarkerDTO, ...] = ()

    @property
    def table_rows(self) -> tuple[StockPricePointDTO, ...]:
        """表格直接使用圖表相同的原始價格 DTO 與精確數值。"""

        return self.price_points


@dataclass(frozen=True)
class StockChartProjectionResult:
    status: StockChartProjectionStatus
    reason: str
    payload: StockChartPayloadDTO | None = None


def project_stock_chart_payload(
    report: StockResearchReportDTO,
    *,
    cutoff_date: date | str | None = None,
    expected_stock_code: str | None = None,
    expected_source_context: Mapping[str, str] | None = None,
    expected_price_row_date: str | None = None,
    expected_price_row_hash: str | None = None,
    marker_candidates: tuple[StockChartMarkerDTO, ...] = (),
    marker_identities: tuple[StockChartMarkerIdentityDTO, ...] = (),
) -> StockChartProjectionResult:
    """把一份既有研究報告投影成同源圖表／數值表 payload。

    ``expected_source_context`` 是保存來源 envelope 的身份 pin；其中的
    ``source_snapshot_hash`` 只比對 report context，絕不與價格 row hash 比較。
    ``expected_price_row_date`` 與 ``expected_price_row_hash`` 則屬於價格列
    fingerprint 域，必須成對提供。
    """

    stock_code = str(getattr(report, "stock_code", "") or "").strip()
    if not stock_code:
        return _rejected("invalid_stock_code")
    if expected_stock_code is not None and stock_code != str(expected_stock_code).strip():
        return _rejected("stock_code_mismatch")

    report_as_of_text = str(getattr(report, "as_of", "") or "").strip()
    report_as_of = _strict_date(report_as_of_text) if report_as_of_text else None
    if report_as_of_text and report_as_of is None:
        return _rejected("invalid_report_as_of")

    requested_cutoff = cutoff_date if cutoff_date is not None else report_as_of_text
    cutoff = _strict_date(requested_cutoff)
    if cutoff is None:
        return _rejected("cutoff_missing_or_invalid")
    if cutoff_date is not None and report_as_of is not None and cutoff != report_as_of:
        return _rejected("report_as_of_mismatch")

    report_context = getattr(report, "research_context", {})
    context = _string_context(report_context)
    saved_chart_text = getattr(report, "saved_technical_chart_json", "")
    if saved_chart_text:
        try:
            envelope = json.loads(saved_chart_text)
            chart_day = cutoff
            if context.get("source_kind") == "recommendation":
                saved_cutoff = context.get("saved_chart_cutoff", "")
                if (saved_cutoff != envelope["decision_cutoff"]
                        or context.get("saved_chart_scope_identity") != envelope["scope_identity"]):
                    return _rejected("recommendation_chart_source_cutoff_pin_mismatch")
                chart_day = date.fromisoformat(saved_cutoff[:10])
                if chart_day > cutoff:
                    return _rejected("recommendation_chart_future_cutoff")
            chart = read_saved_technical_chart(
                envelope, stock_code=stock_code, decision_date=chart_day,
                scope_identity=envelope["scope_identity"],
                input_fingerprint_sha256=envelope["input_fingerprint_sha256"],
            )
            if chart.price_points != report.price_points or chart.technical_history != report.technical_history:
                return _rejected("saved_chart_report_rows_mismatch")
        except (ValueError, TypeError, KeyError) as exc:
            return _rejected("saved_chart_invalid:" + str(exc))
    context_pin_status = "unknown"
    pinned_context = _nonempty_context(expected_source_context)
    if pinned_context:
        for key, expected_value in pinned_context.items():
            actual_value = context.get(key)
            if actual_value is None:
                return _rejected("source_context_pin_missing")
            if actual_value != expected_value:
                return _rejected("source_context_pin_mismatch")
        context_pin_status = "verified"

    if (expected_price_row_date is None) != (expected_price_row_hash is None):
        return _rejected("incomplete_price_row_pin")
    pinned_price_date: date | None = None
    pinned_price_hash: str | None = None
    if expected_price_row_date is not None and expected_price_row_hash is not None:
        pinned_price_date = _strict_date(expected_price_row_date)
        pinned_price_hash = _normalized_sha256(expected_price_row_hash)
        if pinned_price_date is None or pinned_price_hash is None:
            return _rejected("invalid_price_row_pin")
        if pinned_price_date > cutoff:
            return _rejected("price_row_pin_after_cutoff")

    sources = tuple(getattr(report, "sources", ()) or ())
    source_by_id = {
        str(getattr(source, "source_id", "") or "").strip(): source
        for source in sources
        if str(getattr(source, "source_id", "") or "").strip()
    }
    included: list[tuple[date, StockPricePointDTO, str | None]] = []
    has_unknown_price_source = not bool(source_by_id)
    has_unknown_price_hash = False
    has_unknown_price_availability = False
    for point in tuple(getattr(report, "price_points", ()) or ()):
        point_date = _strict_date(getattr(point, "data_date", ""))
        if point_date is None:
            return _rejected("invalid_price_date")
        if point_date > cutoff:
            continue

        if not _valid_price_values(point):
            return _rejected("invalid_price_numeric")

        point_source_id = str(getattr(point, "source_id", "") or "").strip()
        if point_source_id:
            if source_by_id and point_source_id not in source_by_id:
                return _rejected("price_source_mismatch")
            source = source_by_id.get(point_source_id)
            if source is None or str(getattr(source, "status", "") or "").lower() != "available":
                has_unknown_price_source = True
        else:
            has_unknown_price_source = True

        point_available_date, point_clock_status = _availability_date(
            getattr(point, "available_at", "")
        )
        if point_clock_status == "invalid":
            return _rejected("invalid_price_available_at")
        if point_clock_status == "unknown":
            has_unknown_price_availability = True
        elif point_available_date is not None and point_available_date > cutoff:
            continue

        source = source_by_id.get(point_source_id) if point_source_id else None
        if source is not None:
            source_available_date, source_clock_status = _availability_date(
                getattr(source, "available_at", "")
            )
            if source_clock_status == "invalid":
                has_unknown_price_availability = True
            elif source_clock_status == "unknown":
                has_unknown_price_availability = True
            elif source_available_date is not None and source_available_date > cutoff:
                continue

        row_hash = str(getattr(point, "source_snapshot_hash", "") or "").strip()
        fingerprint = _price_fingerprint(stock_code, point)
        if row_hash:
            if _normalized_sha256(row_hash) is None:
                return _rejected("invalid_price_row_hash")
            if fingerprint is None:
                return _rejected("price_row_hash_unverifiable")
            if _normalized_sha256(row_hash) != fingerprint:
                return _rejected("price_row_hash_mismatch")
        else:
            has_unknown_price_hash = True
        included.append((point_date, point, fingerprint))

    included.sort(key=lambda item: item[0])
    if len({item[0] for item in included}) != len(included):
        return _rejected("duplicate_price_date")
    price_points = tuple(item[1] for item in included)

    if pinned_price_date is not None and pinned_price_hash is not None:
        matches = [item for item in included if item[0] == pinned_price_date]
        if not matches:
            return _rejected("price_row_pin_date_missing")
        if len(matches) != 1:
            return _rejected("price_row_pin_date_ambiguous")
        if matches[0][2] is None:
            return _rejected("price_row_pin_unverifiable")
        if matches[0][2] != pinned_price_hash:
            return _rejected("price_row_pin_hash_mismatch")

    price_dates = tuple(point.data_date for point in price_points)
    technical_lines, technical_history_status, technical_history_limitations, history_error = (
        _project_technical_history(
            report,
            stock_code=stock_code,
            cutoff=cutoff,
            price_dates=price_dates,
            source_by_id=source_by_id,
        )
    )
    if history_error:
        return _rejected(history_error)

    technical_snapshot = getattr(report, "technical", None)
    technical_status = "unknown"
    snapshot_clock_status = "unknown"
    if technical_snapshot is not None:
        technical_date_text = str(technical_snapshot.data_date or "").strip()
        technical_date = _strict_date(technical_date_text)
        if technical_date is None:
            if technical_date_text:
                return _rejected("invalid_technical_date")
            # 可選技術快照缺資料日時不猜測；仍保留已核對的價格。
            technical_snapshot = None
            technical_status = "unknown"
        elif technical_date > cutoff:
            technical_snapshot = None
            technical_status = "future_excluded"
        else:
            snapshot_available_date, snapshot_clock_status = _availability_date(
                getattr(technical_snapshot, "available_at", "")
            )
            if snapshot_clock_status == "invalid":
                return _rejected("invalid_technical_available_at")
            if (
                snapshot_clock_status == "verified"
                and snapshot_available_date is not None
                and snapshot_available_date > cutoff
            ):
                technical_snapshot = None
                technical_status = "future_excluded"
        if technical_snapshot is not None:
            filtered_indicators = []
            unknown_technical_clock = snapshot_clock_status == "unknown"
            for indicator in tuple(getattr(technical_snapshot, "indicators", ()) or ()):
                value = getattr(indicator, "value", None)
                if value is not None and (
                    not isinstance(value, Decimal) or not value.is_finite()
                ):
                    return _rejected("invalid_technical_numeric")
                metric_date_text = str(getattr(indicator, "data_as_of", "") or "").strip()
                metric_date = _strict_date(metric_date_text) if metric_date_text else None
                if metric_date_text and metric_date is None:
                    return _rejected("invalid_technical_data_date")
                metric_available_date, metric_clock_status = _availability_date(
                    getattr(indicator, "available_at", "")
                )
                if metric_clock_status == "invalid":
                    return _rejected("invalid_technical_available_at")
                if metric_date is not None and metric_date > cutoff:
                    continue
                if (
                    metric_clock_status == "verified"
                    and metric_available_date is not None
                    and metric_available_date > cutoff
                ):
                    continue
                if metric_clock_status == "unknown" or metric_date is None:
                    unknown_technical_clock = True
                filtered_indicators.append(indicator)
            technical_snapshot = replace(
                technical_snapshot,
                indicators=tuple(filtered_indicators),
            )
            technical_status = (
                "unknown" if unknown_technical_clock else "snapshot_only"
            )

    has_unknown_price_hash = has_unknown_price_hash or not price_points
    price_source_status = "unknown" if has_unknown_price_source else "verified"
    price_hash_status = "unknown" if has_unknown_price_hash else "verified"
    price_availability_status = (
        "unknown"
        if has_unknown_price_availability or not price_points
        else "verified"
    )
    limitations: list[str] = []
    if context_pin_status == "unknown":
        limitations.append("沒有保存來源 context pin；來源身份維持 unknown。")
    if price_source_status == "unknown":
        limitations.append("價格列來源未能由報告來源清單完整核對。")
    if price_hash_status == "unknown":
        limitations.append("至少一筆價格列缺少可驗證 fingerprint；價格來源身份維持 unknown。")
    if price_availability_status == "unknown":
        limitations.append("價格列可得時鐘缺少或無法核驗時區；不宣稱 PIT。")
    if technical_status == "snapshot_only":
        limitations.append("報告只有單日技術指標 snapshot；沒有歷史技術線資料。")
    elif technical_status == "unknown":
        limitations.append("技術指標至少缺少資料日或可得時鐘；PIT 未建立。")
    elif technical_status == "future_excluded":
        limitations.append("技術指標資料日或可得時間晚於 cutoff，已排除。")

    limitations.extend(technical_history_limitations)
    events = tuple(getattr(report, "events", ()) or ())
    event_marker_candidates, marker_status = _project_marker_candidates(
        events,
        source_by_id,
        cutoff,
    )
    if events:
        limitations.append(
            "事件已依報告來源與可得日過濾；事件 DTO 缺少列級 stock/hash，marker 身份維持 unknown。"
        )
    else:
        limitations.append("報告沒有可驗證的事件 marker；PIT 未建立。")

    typed_markers = verified_stock_chart_markers(
        marker_candidates, marker_identities, stock_code=stock_code,
        cutoff_date=cutoff.isoformat(), source_context=tuple(sorted(context.items())),
        price_points=price_points,
    )
    if marker_candidates:
        limitations.append("標記只代表同來源已核身份記錄；推薦確認是研究，實際交易另核帳本，不授 PIT。")

    payload = StockChartPayloadDTO(
        stock_code=stock_code,
        cutoff_date=cutoff.isoformat(),
        report_as_of=report_as_of.isoformat() if report_as_of else "",
        source_context=tuple(sorted(context.items())),
        source_context_status=context_pin_status,
        price_source_status=price_source_status,
        price_hash_status=price_hash_status,
        price_availability_status=price_availability_status,
        price_points=price_points,
        technical_snapshot=technical_snapshot,
        technical_status=technical_status,
        # 現行 report 沒有歷史技術序列，不能把 snapshot 拉成整條線。
        technical_lines=technical_lines,
        technical_history_status=technical_history_status,
        technical_history_limitations=technical_history_limitations,
        # 事件缺列級身份，候選只供診斷；UI 不得把候選當 marker 繪製。
        evidence_markers=(),
        unverified_marker_candidates=event_marker_candidates,
        marker_status="verified" if typed_markers else marker_status,
        verified_markers=typed_markers,
        historical_pit_eligible=False,
        limitations=tuple(limitations),
    )

    if (
        context_pin_status == "verified"
        and price_source_status == "verified"
        and price_hash_status == "verified"
        and price_availability_status == "verified"
    ):
        return StockChartProjectionResult(
            status=StockChartProjectionStatus.READY,
            reason="verified",
            payload=payload,
        )

    reason = (
        "source_context_unknown"
        if context_pin_status == "unknown"
        else "price_source_unknown"
        if price_source_status == "unknown"
        else "price_hash_unknown"
        if price_hash_status == "unknown"
        else "price_availability_unknown"
    )
    return StockChartProjectionResult(
        status=StockChartProjectionStatus.UNKNOWN,
        reason=reason,
        payload=payload,
    )


def _rejected(reason: str) -> StockChartProjectionResult:
    return StockChartProjectionResult(
        status=StockChartProjectionStatus.REJECTED,
        reason=reason,
    )


def _strict_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return None
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == text else None


def _availability_date(value: object) -> tuple[date | None, str]:
    """將來源可得時間換算為台北日曆日；naive 時鐘保持 unknown。"""

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        return value, "verified"
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        parsed_date = _strict_date(text)
        if parsed_date is not None:
            return parsed_date, "verified"
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None, "invalid"
    else:
        return None, "unknown"
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, "unknown"
    return parsed.astimezone(_TAIPEI).date(), "verified"


def _string_context(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): str(item).strip()
        for key, item in value.items()
        if item is not None
    }


def _nonempty_context(value: Mapping[str, str] | None) -> dict[str, str]:
    if value is None:
        return {}
    return {
        str(key): str(item).strip()
        for key, item in value.items()
        if item is not None and str(item).strip()
    }


def _valid_price_values(point: StockPricePointDTO) -> bool:
    for name in (
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "turnover",
        "change",
    ):
        value = getattr(point, name, None)
        if value is not None and (not isinstance(value, Decimal) or not value.is_finite()):
            return False
    volume = getattr(point, "volume", None)
    return volume is None or (type(volume) is int and volume >= 0)


def _price_fingerprint(
    stock_code: str,
    point: StockPricePointDTO,
) -> str | None:
    try:
        return stock_price_row_fingerprint_sha256(
            stock_code=stock_code,
            data_date=point.data_date,
            open_price=point.open_price,
            high_price=point.high_price,
            low_price=point.low_price,
            close_price=point.close_price,
            volume=point.volume,
            turnover=point.turnover,
        )
    except ValueError:
        # 缺少 OHLC 時不能重算已知 fingerprint。
        return None


def _project_technical_history(
    report: StockResearchReportDTO,
    *,
    stock_code: str,
    cutoff: date,
    price_dates: tuple[str, ...],
    source_by_id: Mapping[str, object],
) -> tuple[
    tuple[StockChartTechnicalLineDTO, ...],
    str,
    tuple[str, ...],
    str | None,
]:
    """驗證既有 MA 列，依價格日期輸出可由 None 中斷的折線點。"""

    saved_scope_limitation = technical_history_saved_scope_limitation(
        getattr(report, "research_context", {})
    )
    if saved_scope_limitation is not None and not getattr(report, "saved_technical_chart_json", ""):
        return (), "unavailable", (
            "這筆舊保存來源沒有同版價格／MA20／MA60圖表；不借目前資料補圖。可使用「另開最新研究」獨立查看現況。",
            saved_scope_limitation,
        ), None
    if not price_dates:
        return (), "unknown", ("沒有價格日期可供 MA20/MA60 對齊。",), None

    history_rows = tuple(getattr(report, "technical_history", ()) or ())
    if not history_rows:
        return (), "unknown", (
            "沒有與目前價格日期對齊的既有 MA20/MA60 歷史列。",
            "缺值可能來自來源缺列或暖機未知；不補前值，也不宣稱 PIT 資格。",
        ), None

    expected_source_id = ("recommendation.market_frame.indicators"
                          if getattr(report, "saved_technical_chart_json", "")
                          and _string_context(getattr(report, "research_context", {})).get("source_kind") == "recommendation"
                          else "sqlite.technical_indicators")
    source = source_by_id.get(expected_source_id)
    if source is None:
        return (), "unknown", (), "technical_history_source_missing"
    source_status = str(getattr(source, "status", "") or "").strip().lower()
    if source_status not in {"available", "partial", "stale"}:
        return (), "unknown", (), "technical_history_source_unavailable"

    price_date_set = set(price_dates)
    history_by_date: dict[str, StockTechnicalHistoryRowDTO] = {}
    has_unknown_clock = source_status != "available"
    has_excluded_rows = False
    source_date_text = str(getattr(source, "data_as_of", "") or "").strip()
    source_date = _strict_date(source_date_text) if source_date_text else None
    if source_date_text and source_date is None:
        return (), "unknown", (), "invalid_technical_history_source_date"
    if source_date is not None and source_date > cutoff:
        return (), "future_excluded", (
            "技術來源 data_as_of 晚於 cutoff，整段 MA20/MA60 歷史已排除。",
        ), None
    if source_date is None:
        has_unknown_clock = True
    source_available_date, source_clock_status = _availability_date(
        getattr(source, "available_at", "")
    )
    if source_clock_status == "invalid":
        return (), "unknown", (), "invalid_technical_history_source_available_at"
    if source_clock_status == "verified" and source_available_date is not None:
        if source_available_date > cutoff:
            return (), "future_excluded", (
                "技術來源 available_at 晚於 cutoff，整段 MA20/MA60 歷史已排除。",
            ), None
    else:
        has_unknown_clock = True
    for row in history_rows:
        data_date_text = str(getattr(row, "data_date", "") or "").strip()
        data_date = _strict_date(data_date_text)
        if data_date is None:
            return (), "unknown", (), "invalid_technical_history_date"
        if data_date > cutoff or data_date_text not in price_date_set:
            has_excluded_rows = True
            continue

        row_stock = str(getattr(row, "stock_code", "") or "").strip()
        if row_stock != stock_code:
            return (), "unknown", (), "technical_history_stock_mismatch"
        row_source_id = str(getattr(row, "source_id", "") or "").strip()
        if row_source_id != expected_source_id:
            return (), "unknown", (), "technical_history_source_mismatch"

        ma20 = getattr(row, "ma20", None)
        ma60 = getattr(row, "ma60", None)
        for value in (ma20, ma60):
            if value is not None and (
                not isinstance(value, Decimal) or not value.is_finite()
            ):
                return (), "unknown", (), "invalid_technical_history_numeric"

        available_at = str(getattr(row, "available_at", "") or "").strip()
        available_date, clock_status = _availability_date(available_at)
        if clock_status == "invalid":
            return (), "unknown", (), "invalid_technical_history_available_at"
        if clock_status == "verified" and available_date is not None and available_date > cutoff:
            has_excluded_rows = True
            continue
        if clock_status == "unknown":
            has_unknown_clock = True

        row_hash = str(getattr(row, "source_row_hash", "") or "").strip()
        normalized_hash = _normalized_sha256(row_hash)
        if normalized_hash is None:
            return (), "unknown", (), "invalid_technical_history_hash"
        try:
            expected_hash = stock_technical_history_row_fingerprint_sha256(
                stock_code=row_stock,
                source_id=row_source_id,
                data_date=data_date_text,
                ma20=ma20,
                ma60=ma60,
                available_at=available_at,
            )
        except ValueError:
            return (), "unknown", (), "invalid_technical_history_numeric"
        if normalized_hash != expected_hash:
            return (), "unknown", (), "technical_history_hash_mismatch"
        if data_date_text in history_by_date:
            return (), "unknown", (), "duplicate_technical_history_date"
        history_by_date[data_date_text] = row

    if not history_by_date:
        reason = (
            "cutoff 後或價格日期以外的 MA20/MA60 列已排除。"
            if has_excluded_rows
            else "沒有通過來源檢核的 MA20/MA60 歷史列。"
        )
        return (), "unknown", (reason, "暖機狀態未知；歷史 PIT 資格維持 false。"), None

    lines: list[StockChartTechnicalLineDTO] = []
    has_missing_value = False
    has_any_value = False
    for key, label, attribute in (
        ("MA20", "MA20", "ma20"),
        ("MA60", "MA60", "ma60"),
    ):
        points: list[StockChartTechnicalPointDTO] = []
        for price_date_text in price_dates:
            row = history_by_date.get(price_date_text)
            value = getattr(row, attribute, None) if row is not None else None
            if value is None:
                has_missing_value = True
            else:
                has_any_value = True
            points.append(
                StockChartTechnicalPointDTO(
                    data_date=price_date_text,
                    value=value,
                    source_id=(row.source_id if row is not None else ""),
                    source_row_hash=(row.source_row_hash if row is not None else ""),
                    available_at=(row.available_at if row is not None else ""),
                )
            )
        lines.append(StockChartTechnicalLineDTO(key=key, label=label, points=tuple(points)))

    limitations = [
        "僅投影既有 technical_indicators 的 MA20/MA60 stored rows；不重算指標。",
        "缺列或空值代表缺值／暖機未知；不補末值，且不授予歷史 PIT 或暖機充分資格。",
    ]
    if has_unknown_clock:
        limitations.append("技術列或來源 availability 未核實，歷史時間資格為 unknown。")
    if has_excluded_rows:
        limitations.append("cutoff 後或價格日期以外的技術列已排除。")

    if not has_any_value or has_unknown_clock:
        status = "unknown"
    elif has_missing_value:
        status = "partial"
    else:
        status = "observed_only"
    return tuple(lines), status, tuple(limitations), None


def _normalized_sha256(value: object) -> str | None:
    text = str(value or "").strip().lower()
    if text.startswith("sha256:"):
        text = text[7:]
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        return None
    return text


def _project_marker_candidates(
    events: tuple[StockEvidenceEventDTO, ...],
    source_by_id: Mapping[str, object],
    cutoff: date,
) -> tuple[tuple[StockEvidenceEventDTO, ...], str]:
    if not events:
        return (), "unavailable"
    eligible: list[StockEvidenceEventDTO] = []
    for event in events:
        event_id = str(getattr(event, "event_id", "") or "").strip()
        source_id = str(getattr(event, "source_id", "") or "").strip()
        source = source_by_id.get(source_id)
        if (
            not event_id
            or source is None
            or str(getattr(source, "status", "") or "").lower() != "available"
        ):
            continue
        event_dates: list[date] = []
        invalid_date = False
        for field_name in ("event_date", "decision_date", "as_of_date"):
            text = str(getattr(event, field_name, "") or "").strip()
            parsed = _strict_date(text) if text else None
            if parsed is None:
                invalid_date = True
                break
            event_dates.append(parsed)
        if invalid_date or any(value > cutoff for value in event_dates):
            continue
        event_available, event_clock_status = _availability_date(
            getattr(event, "available_at", "")
        )
        source_available, source_clock_status = _availability_date(
            getattr(source, "available_at", "")
        )
        source_data_as_of_text = str(getattr(source, "data_as_of", "") or "").strip()
        source_data_as_of = (
            _strict_date(source_data_as_of_text) if source_data_as_of_text else None
        )
        if (
            event_clock_status != "verified"
            or event_available is None
            or source_clock_status != "verified"
            or source_available is None
            or source_data_as_of is None
        ):
            continue
        if event_available > cutoff or source_available > cutoff or source_data_as_of > cutoff:
            continue
        eligible.append(event)
    # 候選事件已核對來源與台北截止日，但缺 row-level stock/hash，不能繪製。
    return tuple(eligible), "unknown"
