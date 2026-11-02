"""只將已載入研究 DTO 投影為原值圖卡，不查詢或產生金融指標。"""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from collections.abc import Sequence
import json

from app_module.research_result_presentation import build_shareholding_tier_table

from app_module.stock_research_report_dtos import (
    StockFlowObservationDTO, StockFundamentalObservationDTO,
    StockMetricDTO, StockResearchReportDTO,
)
from ui_qt.widgets.research_metric_chart import ResearchMetricBar


@dataclass(frozen=True)
class ResearchVisualGroup:
    title: str
    unit: str
    points: tuple[ResearchMetricBar, ...]
    note: str
    chart_kind: str = "bar"
    semantic: str = "generic"
    detail_note: str = ""


def _number(value: Decimal | None) -> Decimal | None:
    return value if isinstance(value, Decimal) and value.is_finite() else None


def _known_unit(unit: str) -> bool:
    return unit.strip() in {
        "TWD", "TWD/share", "元", "千元", "百萬元", "新台幣元", "新台幣千元",
        "%", "percent", "percentage_point", "百分比", "百分點", "基點", "bp",
        "股", "張", "交易單位", "人", "戶", "家", "倍",
    }


def fundamental_visuals(report: StockResearchReportDTO) -> tuple[ResearchVisualGroup, ...]:
    groups: list[ResearchVisualGroup] = []
    for comparison in report.fundamental_comparisons:
        groups.append(ResearchVisualGroup(
            comparison.label, comparison.value_unit,
            (ResearchMetricBar(comparison.prior_period, comparison.prior_value, "原比較前期"),
             ResearchMetricBar(comparison.current_period, comparison.current_value, "原比較當期")),
            f"原值前期／當期比較｜可用時間 {comparison.available_at or '未知'}｜目前研究；不是歷史 PIT 或成長預測。缺值不補零。",
            "paired_column",
            detail_note=(
                f"比較來源 {comparison.source_id}／{comparison.source_version}｜"
                f"當期來源 {comparison.current_source_id}／{comparison.current_source_version}｜"
                f"原比較說明：{comparison.note or '未提供'}"
            ),
        ))
    series: dict[tuple[str, ...], list[StockFundamentalObservationDTO]] = defaultdict(list)
    represented = {(c.current_source_id, c.current_source_version, c.metric_name, c.current_period)
                   for c in report.fundamental_comparisons}
    for item in report.fundamentals:
        if (item.source_id, item.source_version, item.metric_name, item.period) in represented:
            continue
        if not item.source_id or not item.metric_name or not item.period or not _known_unit(item.unit):
            continue
        # 不把期間基礎未核的數字畫成可比較序列；原表仍完整保留。
        if not item.basis_verified or item.period_basis == "unknown":
            continue
        key = (item.kind, item.source_id, item.source_version, item.metric_name, item.unit, item.period_basis, item.market)
        series[key].append(item)
    for key, items in series.items():
        if len({item.period for item in items}) != len(items):
            continue
        if not any(_number(item.value) is not None for item in items):
            continue
        ordered = sorted(items, key=lambda item: item.period)
        group = ResearchVisualGroup(
            ordered[0].label, key[4],
            tuple(ResearchMetricBar(item.period, _number(item.value),
                  f"資料日 {item.as_of_date or '未提供'}｜可用 {item.available_at or '未知'}｜品質 {item.quality}")
                  for item in ordered),
            f"原觀測 {len(items)} 筆｜"
            + ("單一期間，不能判定趨勢。" if len(items) == 1 else "只呈現已提供期間；不補缺月、不推算同比或累計。")
            + "缺值不補零。",
            "column" if key[0] == "monthly_revenue" else "bar",
            detail_note=(
                f"市場 {key[6] or '未提供'}｜來源 {key[1]}／{key[2] or '版本未提供'}｜"
                f"期間基礎 {key[5]}｜品質及每筆資料日／可用時間見逐筆明細。"
            ),
        )
        if key[0] == "monthly_revenue":
            groups.insert(0, group)
        else:
            groups.append(group)
    return tuple(groups)


def metric_visuals(title: str, metrics: Sequence[StockMetricDTO]) -> tuple[ResearchVisualGroup, ...]:
    buckets: dict[tuple[str, str, str, str], list[StockMetricDTO]] = defaultdict(list)
    for item in metrics:
        if item.source_id and item.data_as_of and _known_unit(item.unit):
            # 單位相同不代表金融意義相同；淨額可同圖，其餘每個指標各自呈現。
            family = "法人淨額" if item.key in {
                "foreign_investor_net", "investment_trust_net", "dealer_net",
            } else item.key
            buckets[(item.source_id, item.data_as_of, item.unit, family)].append(item)
    result = []
    for (source, day, unit, family), items in sorted(buckets.items(), key=lambda entry: entry[0][3] != "法人淨額"):
        if not any(_number(item.value) is not None for item in items):
            continue
        result.append(ResearchVisualGroup(
            f"{title}｜{family if family == '法人淨額' else items[0].label}", unit,
            tuple(ResearchMetricBar(item.label, _number(item.value),
                  f"可用 {item.available_at or '未知'}｜品質 {item.quality}") for item in items),
            f"資料日 {day}｜單日原觀測；各項意義依標籤，不代表連買、持股變化或買賣建議。缺值不補零。",
            "bar",
            "directional" if family == "法人淨額" else "generic",
            f"來源 {source}｜各筆可用時間與品質見逐筆明細。",
        ))
    return tuple(result)


def flow_visuals(flows: Sequence[StockFlowObservationDTO]) -> tuple[ResearchVisualGroup, ...]:
    buckets: dict[tuple[str, str, str], list[StockFlowObservationDTO]] = defaultdict(list)
    for item in flows:
        if item.source_id and item.data_date:
            buckets[(item.source_id, item.data_date, item.trade_type)].append(item)
    result = []
    for (source, day, trade_type), rows in buckets.items():
        if not any(row.net_shares is not None for row in rows):
            continue
        shown = rows[:12]
        result.append(ResearchVisualGroup(
            "分點淨買賣", "股",
            tuple(ResearchMetricBar(row.branch_name,
                  Decimal(row.net_shares) if row.net_shares is not None else None,
                  f"品質 {row.quality}｜可用 {row.available_at or '未知'}") for row in shown),
            f"資料日 {day}｜原順序顯示前 {len(shown)}／{len(rows)} 列；單日分點，不累計、不代表主力連買。缺值不補零。",
            "bar",
            "directional",
            f"來源 {source}｜類型 {trade_type or '未提供'}｜每筆品質及可用時間見逐筆明細。",
        ))
    return tuple(result)


def shareholding_tier_visuals(metrics: Sequence[StockMetricDTO]) -> tuple[ResearchVisualGroup, ...]:
    result = []
    for metric in metrics:
        if metric.key != "shareholding_tiers" or not metric.source_id or not metric.data_as_of:
            continue
        try:
            rows = json.loads(metric.value_text)
        except (ValueError, TypeError):
            continue
        if not isinstance(rows, list):
            continue
        tier_ids = [row.get("tier") for row in rows if isinstance(row, dict) and type(row.get("tier")) is int]
        if len(tier_ids) != len(set(tier_ids)):
            continue
        points = []
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            tier = row.get("tier")
            if type(tier) is not int or not 1 <= tier <= 15 or tier in seen:
                continue
            seen.add(tier)
            ratio = row.get("holding_ratio_bp")
            if type(ratio) is not int or not 0 <= ratio <= 10000:
                ratio = None
            presentation = build_shareholding_tier_table(json.dumps([row], ensure_ascii=False))
            if presentation.rows:
                points.append(ResearchMetricBar(presentation.rows[0][0],
                    Decimal(ratio) if ratio is not None else None,
                    f"可用 {metric.available_at or '未知'}｜品質 {metric.quality}"))
        if any(point.value is not None for point in points):
            result.append(ResearchVisualGroup(
                "集保持股級距分布", "基點", tuple(points),
                f"資料日 {metric.data_as_of}｜1–15級原比例；100基點為1%（散戶至大戶由左至右分布）。"
                "調整與合計列只留原表，不與級距混比；這是一個快照，不是大戶增減趨勢。缺值不補零。",
                chart_kind="column",
                detail_note=f"來源 {metric.source_id}｜品質及可用時間見逐筆明細。",
            ))
    return tuple(result)
