from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AdviceContractBacktestNavigation:
    """將目前 Daily Advice 的精確身分帶到回測頁，只供導覽提示使用。"""

    candidate_result_id: str
    source_snapshot_id: str
    stock_code: str
    decision_date: str
    data_as_of_date: str
    strategy_version: str
    missing_author_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "candidate_result_id",
            "source_snapshot_id",
            "stock_code",
            "decision_date",
            "data_as_of_date",
            "strategy_version",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if type(self.missing_author_fields) is not tuple or not self.missing_author_fields:
            raise ValueError("missing_author_fields must be a non-empty tuple")
        if any(not isinstance(item, str) or not item.strip() for item in self.missing_author_fields):
            raise ValueError("missing_author_fields must contain non-empty labels")

    def banner_text(self) -> str:
        fields = "、".join(self.missing_author_fields)
        return (
            "導覽來源（僅供核對，不是回測輸入）\n"
            f"每日候選：{self.stock_code}｜策略版本：{self.strategy_version}\n"
            f"決策日：{self.decision_date}｜資料日：{self.data_as_of_date}\n"
            f"result_id：{self.candidate_result_id}｜snapshot_id：{self.source_snapshot_id}\n"
            f"待作者填寫：{fields}。請自行選取策略、檢查期間與資料後決定是否建立新版本；"
            "此導覽不會載入回測設定、執行回測或升版。"
        )


__all__ = ("AdviceContractBacktestNavigation",)
