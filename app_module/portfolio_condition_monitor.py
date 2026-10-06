"""Portfolio condition monitoring for append-only Phase 4.1 positions.

此模組只對照進場來源快照與目前狀態，提供決策支援標籤；
不做自動交易、不調整持倉，也不寫入儲存層。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Dict, List, Optional

from app_module.dtos.portfolio_dtos import PositionDTO


@dataclass(frozen=True)
class PortfolioCurrentSnapshot:
    """目前狀態快照，用於和持倉來源快照對照。"""

    current_regime: str = ""
    current_total_score: Optional[Any] = None
    current_price: Optional[Decimal | float] = None
    quote_data_date: date | None = None
    quote_source_id: str = ""
    quote_source_snapshot_hash: str = ""
    quote_freshness_status: str = "unverified"
    quote_expected_date: date | None = None


@dataclass(frozen=True)
class PortfolioConditionResult:
    """單一持倉的條件監控結果。"""

    stock_code: str
    status: str
    label: str
    source_label: str
    entry_regime: str = ""
    current_regime: str = ""
    entry_total_score: str = ""
    current_total_score: str = ""
    reasons: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


class PortfolioConditionMonitor:
    """Evaluate whether a derived position still matches its source thesis."""

    def __init__(self, score_warning_points: int | str | Decimal = 10):
        self.score_warning_points = self._to_decimal(score_warning_points) or Decimal("10")

    def evaluate(
        self,
        position: PositionDTO,
        current_snapshot: Optional[PortfolioCurrentSnapshot] = None,
    ) -> PortfolioConditionResult:
        source_summary = dict(position.source_summary or {})
        source_label = self._source_label(position, source_summary)

        if not position.source_type and not source_summary:
            return PortfolioConditionResult(
                stock_code=position.stock_code,
                status="warning",
                label="來源不足",
                source_label=source_label,
                reasons=["缺少推薦、回測或策略版本來源，無法對照進場假設"],
                details={
                    "source_type": position.source_type,
                    "source_id": position.source_id,
                    "source_summary_available": False,
                },
            )

        snapshot = current_snapshot or PortfolioCurrentSnapshot()
        entry_regime = str(
            source_summary.get("regime")
            or source_summary.get("entry_regime")
            or ""
        )
        current_regime = str(snapshot.current_regime or "")

        entry_score = self._to_decimal(
            source_summary.get("total_score", source_summary.get("entry_total_score"))
        )
        current_score = self._to_decimal(snapshot.current_total_score)

        reasons: List[str] = []
        details: Dict[str, Any] = {
            "source_type": position.source_type,
            "source_id": position.source_id,
            "profile_id": source_summary.get("profile_id", ""),
            "strategy_id": source_summary.get("strategy_id", ""),
            "entry_regime": entry_regime,
            "current_regime": current_regime,
            "regime_changed": False,
            "score_degraded": False,
        }

        if entry_regime and current_regime:
            if entry_regime != current_regime:
                details["regime_changed"] = True
                reasons.append(f"Regime 已由 {entry_regime} 轉為 {current_regime}")
            else:
                reasons.append(f"Regime 仍為 {entry_regime}")

        score_change: Optional[Decimal] = None
        if entry_score is not None and current_score is not None:
            score_change = current_score - entry_score
            details["score_change"] = self._format_decimal(score_change)
            details["entry_total_score"] = self._format_decimal(entry_score)
            details["current_total_score"] = self._format_decimal(current_score)
            if score_change <= -self.score_warning_points:
                details["score_degraded"] = True
                reasons.append(
                    f"評分下降 {self._format_decimal(abs(score_change))} 分"
                )
            else:
                reasons.append(
                    "評分變化 "
                    f"{self._format_decimal(score_change)} 分，"
                    f"未超過 {self._format_points(self.score_warning_points)} 分門檻"
                )

        # position.current_price 可以保留作損益觀察，但它沒有行情日期與新鮮度，
        # 不能單獨觸發停損／停利，也不能讓價格 thesis 顯示仍符合。
        quote_price_dec = self._positive_price(self._to_decimal(snapshot.current_price))
        price_dec = (
            quote_price_dec
            if quote_price_dec is not None
            else self._positive_price(self._to_decimal(position.current_price))
        )
        quote_is_current = self._has_current_quote_evidence(snapshot)
        rule_price_dec = quote_price_dec if quote_is_current else None
        cost_dec = self._positive_price(self._to_decimal(position.average_cost))
        
        stop_loss_val = self._to_decimal(source_summary.get("stop_loss_pct"))
        take_profit_val = self._to_decimal(source_summary.get("take_profit_pct"))
        
        stop_loss_triggered = False
        take_profit_triggered = False
        return_pct_val = None
        
        # 標準化停損停利門檻 (大於 1 則除以 100)
        if stop_loss_val is not None:
            if abs(stop_loss_val) > Decimal("1"):
                stop_loss_val = stop_loss_val / Decimal("100")
            stop_loss_val = abs(stop_loss_val)
            
        if take_profit_val is not None:
            if abs(take_profit_val) > Decimal("1"):
                take_profit_val = take_profit_val / Decimal("100")
            take_profit_val = abs(take_profit_val)

        details["stop_loss_pct"] = float(stop_loss_val) if stop_loss_val is not None else None  # numeric-boundary: dto
        details["take_profit_pct"] = float(take_profit_val) if take_profit_val is not None else None  # numeric-boundary: dto
        details["current_price"] = float(price_dec) if price_dec is not None else None  # numeric-boundary: dto
        details["average_cost"] = float(cost_dec) if cost_dec is not None else None  # numeric-boundary: dto
        details["quote_data_date"] = (
            snapshot.quote_data_date.isoformat()
            if isinstance(snapshot.quote_data_date, date)
            and not isinstance(snapshot.quote_data_date, datetime)
            else ""
        )
        details["quote_expected_date"] = (
            snapshot.quote_expected_date.isoformat()
            if isinstance(snapshot.quote_expected_date, date)
            and not isinstance(snapshot.quote_expected_date, datetime)
            else ""
        )
        details["quote_source_id"] = str(snapshot.quote_source_id or "")
        details["quote_source_snapshot_hash"] = str(snapshot.quote_source_snapshot_hash or "")
        details["quote_freshness_status"] = str(snapshot.quote_freshness_status or "unverified")
        details["quote_is_current"] = quote_is_current
        details["stop_loss_triggered"] = False
        details["take_profit_triggered"] = False
        
        if price_dec is not None and cost_dec is not None and cost_dec > 0:
            return_pct_val = (price_dec - cost_dec) / cost_dec
            details["return_pct"] = float(return_pct_val)  # numeric-boundary: dto

            if rule_price_dec is not None:
                rule_return_pct = (rule_price_dec - cost_dec) / cost_dec
                if stop_loss_val is not None:
                    if rule_return_pct <= -stop_loss_val:
                        stop_loss_triggered = True
                        details["stop_loss_triggered"] = True
                        reasons.append(
                            f"已觸發停損點 (目前報酬 {float(rule_return_pct * 100):.2f}% <= 停損點 -{float(stop_loss_val * 100):.1f}%)"  # numeric-boundary: dto
                        )
                if take_profit_val is not None:
                    if rule_return_pct >= take_profit_val:
                        take_profit_triggered = True
                        details["take_profit_triggered"] = True
                        reasons.append(
                            f"已觸發停利點 (目前報酬 {float(rule_return_pct * 100):.2f}% >= 停利點 {float(take_profit_val * 100):.1f}%)"  # numeric-boundary: dto
                        )

                if not stop_loss_triggered and stop_loss_val is not None:
                    reasons.append(f"未觸發停損點 (-{float(stop_loss_val * 100):.1f}%)")  # numeric-boundary: dto
                if not take_profit_triggered and take_profit_val is not None:
                    reasons.append(f"未觸發停利點 ({float(take_profit_val * 100):.1f}%)")  # numeric-boundary: dto

        has_configured_price_rule = stop_loss_val is not None or take_profit_val is not None
        if has_configured_price_rule and not quote_is_current:
            reasons.append(
                "行情日期或 freshness 未通過官方市場節奏核對；價格僅供損益觀察，暫不判定停損／停利"
            )

        # 價格與成本能計算損益，但只有來源實際記錄的 thesis 條件可判定
        # 「仍符合」；沒有可比 Regime／評分或可套用到目前價格的停損停利規則時，
        # 價格只作觀察資訊。
        has_regime_evaluation = bool(entry_regime and current_regime)
        has_score_evaluation = entry_score is not None and current_score is not None
        has_price_evaluation = (price_dec is not None and cost_dec is not None and cost_dec > 0)
        has_current_price_evaluation = (
            quote_is_current
            and rule_price_dec is not None
            and cost_dec is not None
            and cost_dec > 0
        )
        has_structured_price_rule = has_current_price_evaluation and (
            has_configured_price_rule
        )
        has_thesis_evaluation = (
            has_regime_evaluation
            or has_score_evaluation
            or has_structured_price_rule
        )
        details["has_price_evaluation"] = bool(has_price_evaluation)
        details["has_current_price_evaluation"] = bool(has_current_price_evaluation)
        details["has_configured_price_rule"] = bool(has_configured_price_rule)
        details["has_structured_price_rule"] = bool(has_structured_price_rule)
        details["price_rule_blocked_by_quote_freshness"] = bool(
            has_configured_price_rule and not quote_is_current
        )
        details["thesis_evaluable"] = bool(has_thesis_evaluation)

        if not has_thesis_evaluation:
            if has_price_evaluation:
                reason = (
                    "目前價格/成本僅供損益觀察；缺少可評估的進場 Regime、評分或停損停利條件，"
                    "無法判定假設是否仍符合"
                )
            elif has_configured_price_rule and not quote_is_current:
                reason = "已有停損停利條件，但行情日期或 freshness 尚未確認；保留損益觀察並等待更新行情"
            elif has_configured_price_rule:
                reason = "已有停損停利條件，但目前價格或成本不足，無法進行條件對照"
            else:
                reason = "尚無可對照的目前 Regime、評分或停損停利條件，無法判定進場假設"
            reasons.append(reason)
            return PortfolioConditionResult(
                stock_code=position.stock_code,
                status="warning",
                label="待更新",
                source_label=source_label,
                entry_regime=entry_regime,
                current_regime=current_regime,
                entry_total_score=self._format_decimal(entry_score),
                current_total_score=self._format_decimal(current_score),
                reasons=reasons,
                details=details,
            )

        is_invalid = (
            (details.get("regime_changed", False) and details.get("score_degraded", False)) or
            stop_loss_triggered or
            take_profit_triggered
        )
        is_warning = (
            (details.get("regime_changed", False) or details.get("score_degraded", False)) and not is_invalid
        ) or bool(details["price_rule_blocked_by_quote_freshness"])

        if is_invalid:
            status = "invalid"
            label = "假設失效"
        elif is_warning:
            status = "warning"
            label = "需要留意"
        else:
            status = "valid"
            label = "仍符合"

        return PortfolioConditionResult(
            stock_code=position.stock_code,
            status=status,
            label=label,
            source_label=source_label,
            entry_regime=entry_regime,
            current_regime=current_regime,
            entry_total_score=self._format_decimal(entry_score),
            current_total_score=self._format_decimal(current_score),
            reasons=reasons,
            details=details,
        )

    def _source_label(self, position: PositionDTO, source_summary: Dict[str, Any]) -> str:
        if position.source_type == "recommendation_result":
            profile_id = str(source_summary.get("profile_id") or "").strip()
            return f"推薦：{profile_id}" if profile_id else "推薦"
        if position.source_type == "backtest_run":
            strategy_id = str(source_summary.get("strategy_id") or "").strip()
            return f"回測：{strategy_id}" if strategy_id else "回測"
        if position.source_type:
            return position.source_type
        return "手動"

    def _has_current_quote_evidence(self, snapshot: PortfolioCurrentSnapshot) -> bool:
        quote_date = snapshot.quote_data_date
        expected_date = snapshot.quote_expected_date
        source_id = str(snapshot.quote_source_id or "").strip()
        source_hash = str(snapshot.quote_source_snapshot_hash or "").strip().lower()
        if source_hash.startswith("sha256:"):
            source_hash = source_hash[7:]
        known_source = (
            source_id in {"sqlite.daily_prices", "csv.daily_prices"}
            or bool(re.fullmatch(r"daily_price_file:\d{4}-?\d{2}-?\d{2}\.csv", source_id))
        )
        quote_price = self._positive_price(self._to_decimal(snapshot.current_price))
        return bool(
            quote_price is not None
            and isinstance(quote_date, date)
            and not isinstance(quote_date, datetime)
            and isinstance(expected_date, date)
            and not isinstance(expected_date, datetime)
            and quote_date == expected_date
            and str(snapshot.quote_freshness_status or "").strip().lower() == "current"
            and known_source
            and re.fullmatch(r"[0-9a-f]{64}", source_hash) is not None
        )

    def has_current_quote_evidence(self, snapshot: PortfolioCurrentSnapshot) -> bool:
        """公開目前報價證據檢查，供同版 UI 標示價格觀察範圍。"""
        return self._has_current_quote_evidence(snapshot)

    def _to_decimal(self, value: Any) -> Optional[Decimal]:
        if value is None or isinstance(value, bool) or value == "":
            return None
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
        return parsed if parsed.is_finite() else None

    @staticmethod
    def _positive_price(value: Optional[Decimal]) -> Optional[Decimal]:
        return value if value is not None and value > 0 else None

    def _format_decimal(self, value: Optional[Decimal]) -> str:
        if value is None:
            return ""
        normalized = value.quantize(Decimal("0.1"))
        return format(normalized, "f")

    def _format_points(self, value: Decimal) -> str:
        if value == value.to_integral_value():
            return format(value.quantize(Decimal("1")), "f")
        return self._format_decimal(value)
