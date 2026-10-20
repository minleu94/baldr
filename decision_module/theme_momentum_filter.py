"""三階段題材動量研究濾網的純規則評估。

本模組只評估呼叫端提供的單筆證據是否符合研究篩選門檻。它不讀取資料、
不計算排名，也不驗證來源原件、母體完整性、映射可得性或排名唯一性；
這些證據仍須由上游 reader 綁定。qualified 只代表此純規則濾網通過，
不得解讀為買進建議、正式策略接受、真資料接受或歷史 PIT 資格。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import cast
from zoneinfo import ZoneInfo


_TAIPEI = ZoneInfo("Asia/Taipei")
_EXPECTED_INFLOW_METRIC = "institutional_net_twd"
_VALID_STATES = frozenset({"qualified", "not_qualified", "unavailable"})


@dataclass(frozen=True)
class ThemeMomentumInput:
    """單筆題材動量輸入；布林欄位是上游聲明，並非來源驗證收據。"""

    stock_code: str
    decision_at: datetime
    data_date: date
    available_at: datetime | None
    mapping_available_at: datetime | None
    historical_mapping_eligible: bool
    stock_in_theme: bool
    institutional_buy_count: int | None
    member_count: int | None
    institutional_coverage_complete: bool
    net_inflow_twd: Decimal | None
    inflow_rank: int | None
    ranked_theme_count: int | None
    inflow_universe_complete: bool
    inflow_metric: str = _EXPECTED_INFLOW_METRIC


@dataclass(frozen=True)
class ThemeMomentumDecision:
    """純研究濾網結果，不代表交易或正式策略接受。"""

    state: str
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.state) is not str or self.state not in _VALID_STATES:
            raise ValueError("題材動量結果狀態不受支援")
        if type(self.reasons) is not tuple or any(
            type(reason) is not str for reason in self.reasons
        ):
            raise TypeError("題材動量原因須為字串tuple")


def _utc_instant(value: object, label: str, reasons: list[str]) -> datetime | None:
    """只接受可轉成UTC的aware datetime，將壞時區資料安全降為缺件。"""
    if value is None:
        reasons.append(f"{label}缺失")
        return None
    if type(value) is not datetime:
        reasons.append(f"{label}須為datetime")
        return None
    try:
        if value.utcoffset() is None:
            reasons.append(f"{label}必須包含有效時區")
            return None
        return value.astimezone(timezone.utc)
    except Exception:
        reasons.append(f"{label}時區無效")
        return None


def evaluate_theme_momentum(
    input: ThemeMomentumInput,
) -> ThemeMomentumDecision:
    """依嚴格整數比例與上游序位評估題材動量研究濾網。

    不重算指標或排名，也不自行接受來源。輸入的可得時間須為aware時間；
    不同合法時區依同一UTC瞬間比較。資料日依Asia/Taipei決策日核對。
    正式使用前，上游仍須證明來源、金額單位、同一完整排名母體與唯一序位，
    並驗證當日映射、可得時間及歷史PIT資格。
    """
    if type(input) is not ThemeMomentumInput:
        return ThemeMomentumDecision("unavailable", ("輸入型別須為ThemeMomentumInput",))

    unavailable: list[str] = []

    if type(input.stock_code) is not str or not input.stock_code.strip():
        unavailable.append("股票代碼缺失或型別錯誤")

    decision_utc = _utc_instant(input.decision_at, "決策時間", unavailable)
    available_utc = _utc_instant(input.available_at, "資料可得時間", unavailable)
    mapping_utc = _utc_instant(input.mapping_available_at, "題材映射可得時間", unavailable)

    if type(input.data_date) is not date:
        unavailable.append("資料日須為date")
    elif decision_utc is not None:
        try:
            decision_date_taipei = decision_utc.astimezone(_TAIPEI).date()
        except (OverflowError, ValueError, OSError):
            unavailable.append("決策時間無法換算台北資料日")
        else:
            if input.data_date != decision_date_taipei:
                unavailable.append("資料日與台北決策日不一致")

    if decision_utc is not None and available_utc is not None and available_utc > decision_utc:
        unavailable.append("資料可得時間晚於決策時間")
    if decision_utc is not None and mapping_utc is not None and mapping_utc > decision_utc:
        unavailable.append("題材映射可得時間晚於決策時間")

    for field_name, value, label in (
        ("historical_mapping_eligible", input.historical_mapping_eligible, "歷史題材映射資格"),
        ("stock_in_theme", input.stock_in_theme, "股票題材成員資格"),
        ("institutional_coverage_complete", input.institutional_coverage_complete, "法人家數覆蓋"),
        ("inflow_universe_complete", input.inflow_universe_complete, "資金排名母體完整性"),
    ):
        if type(value) is not bool:
            unavailable.append(f"{label}旗標型別須為bool（{field_name}）")
        elif not value:
            unavailable.append(f"{label}未獲上游確認")

    member_count_valid = type(input.member_count) is int and input.member_count > 0
    if type(input.member_count) is not int:
        unavailable.append("題材成員數須為整數且不可為bool")
    elif input.member_count <= 0:
        unavailable.append("題材成員數須大於零")

    buy_count_valid = type(input.institutional_buy_count) is int
    if not buy_count_valid:
        unavailable.append("法人買超家數須為整數且不可為bool")
    elif cast(int, input.institutional_buy_count) < 0:
        unavailable.append("法人買超家數不可為負數")
    elif member_count_valid and cast(int, input.institutional_buy_count) > cast(int, input.member_count):
        unavailable.append("法人買超家數不可大於題材成員數")

    if type(input.inflow_metric) is not str or input.inflow_metric != _EXPECTED_INFLOW_METRIC:
        unavailable.append("資金排名指標須為institutional_net_twd，不接受股數或其他單位")

    if input.net_inflow_twd is None:
        unavailable.append("法人淨流入金額缺失")
    elif type(input.net_inflow_twd) is not Decimal:
        unavailable.append("法人淨流入金額須為Decimal")
    elif not input.net_inflow_twd.is_finite():
        unavailable.append("法人淨流入金額須為有限Decimal")

    rank_valid = type(input.inflow_rank) is int and input.inflow_rank > 0
    if type(input.inflow_rank) is not int:
        unavailable.append("資金流入序位須為正整數且不可為bool")
    elif input.inflow_rank <= 0:
        unavailable.append("資金流入序位須大於零")

    universe_count_valid = type(input.ranked_theme_count) is int and input.ranked_theme_count > 0
    if type(input.ranked_theme_count) is not int:
        unavailable.append("排序母體題材數須為正整數且不可為bool")
    elif input.ranked_theme_count <= 0:
        unavailable.append("排序母體題材數須大於零")
    if rank_valid and universe_count_valid and cast(int, input.inflow_rank) > cast(int, input.ranked_theme_count):
        unavailable.append("資金流入序位超出排序母體")

    if unavailable:
        return ThemeMomentumDecision("unavailable", tuple(unavailable))

    # 上方完整驗證後，以下欄位已收斂為精確整數與有限Decimal；不做浮點比例。
    buy_count = cast(int, input.institutional_buy_count)
    member_count = cast(int, input.member_count)
    inflow_twd = cast(Decimal, input.net_inflow_twd)
    inflow_rank = cast(int, input.inflow_rank)
    ranked_theme_count = cast(int, input.ranked_theme_count)
    buyers_pass = buy_count * 10 > member_count * 7
    positive_inflow = inflow_twd > Decimal(0)
    top_twenty_percent = inflow_rank * 5 <= ranked_theme_count

    failed_gates: list[str] = []
    if not buyers_pass:
        failed_gates.append("法人買超家數比例未嚴格超過70%")
    if not positive_inflow:
        failed_gates.append("法人淨流入金額未大於零")
    if not top_twenty_percent:
        failed_gates.append("同一完整母體的上游序位未達前20%")
    if failed_gates:
        return ThemeMomentumDecision("not_qualified", tuple(failed_gates))

    return ThemeMomentumDecision(
        "qualified",
        (
            "法人買超家數比例嚴格超過70%",
            "正法人淨流入且上游同母體序位符合rank×5≤N",
            "此結果只表示研究濾網通過；來源、PIT與唯一序位仍須上游驗證",
        ),
    )
