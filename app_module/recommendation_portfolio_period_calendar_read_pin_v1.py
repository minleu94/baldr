"""P08：由保存 owner 明示注入的日曆讀取 pin，不自行產生信任錨點。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from app_module.official_calendar_daily_snapshot_v1 import calendar_daily_acceptance_mode_v1
from data_module.daily_source_snapshot import DailySourceUseAcceptance


@dataclass(frozen=True, slots=True)
class PortfolioPeriodCalendarReadPinV1:
    """只固定路徑、外部 SHA、市場與保護根；來源資格仍由 evidence 判斷。"""

    artifact_path: Path
    expected_sha256: str
    market: Literal["twse", "tpex"]
    protected_roots: tuple[Path, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.artifact_path, Path)
            or not self.artifact_path.is_absolute()
            or ".." in self.artifact_path.parts
        ):
            raise ValueError("calendar artifact 必須是明示絕對路徑")
        if (
            type(self.expected_sha256) is not str
            or len(self.expected_sha256) != 64
            or any(char not in "0123456789abcdef" for char in self.expected_sha256)
        ):
            raise ValueError("calendar 外部 SHA 必須是 canonical 64hex")
        if type(self.market) is not str or self.market not in ("twse", "tpex"):
            raise ValueError("calendar market 必須明示 twse 或 tpex")
        if (
            type(self.protected_roots) is not tuple
            or not 1 <= len(self.protected_roots) <= 32
            or any(
                not isinstance(root, Path) or not root.is_absolute() or ".." in root.parts
                for root in self.protected_roots
            )
        ):
            raise ValueError("calendar protected_roots 必須是有界且明示的絕對路徑 tuple")


@dataclass(frozen=True, slots=True)
class PortfolioPeriodCalendarDailyReadPinV1:
    """明示完成批次與兩個外部 SHA；獨立接受錨點由 owner 提供。"""

    batch_directory: Path
    expected_manifest_sha256: str
    expected_receipt_sha256: str
    market: Literal["twse", "tpex"]
    protected_roots: tuple[Path, ...]
    trusted_acceptances: tuple[DailySourceUseAcceptance, DailySourceUseAcceptance]
    decision_cutoff: datetime

    def __post_init__(self) -> None:
        # 共用純欄位守衛；不讀批次或從其內容建立信任。
        PortfolioPeriodCalendarReadPinV1(
            self.batch_directory, self.expected_manifest_sha256, self.market, self.protected_roots
        )
        if (type(self.expected_receipt_sha256) is not str
                or len(self.expected_receipt_sha256) != 64
                or any(char not in "0123456789abcdef" for char in self.expected_receipt_sha256)):
            raise ValueError("daily receipt SHA 必須是 canonical 64hex")
        if (type(self.trusted_acceptances) is not tuple or len(self.trusted_acceptances) != 2
                or any(type(item) is not DailySourceUseAcceptance for item in self.trusted_acceptances)):
            raise ValueError("daily calendar 必須有兩市場獨立 typed 接受錨點")
        calendar_daily_acceptance_mode_v1(self.trusted_acceptances)
        if (not isinstance(self.decision_cutoff, datetime) or self.decision_cutoff.tzinfo is None
                or self.decision_cutoff.utcoffset() is None):
            raise ValueError("daily calendar cutoff 必須是 aware 時鐘")

    @property
    def source_version(self) -> Literal["monthly_v1", "annual_v1"]:
        return calendar_daily_acceptance_mode_v1(self.trusted_acceptances)


@dataclass(frozen=True, slots=True)
class PortfolioPeriodDailyCalendarIdentityV1:
    """隨配對結果傳遞已讀回的 exact daily 版本，不授績效資格。"""

    batch_id: str
    manifest_sha256: str
    receipt_sha256: str
    capture_sha256: str
    first_persisted_at: str
    successful_batch_completed_at: str
    available_hour: str
    availability_basis: str
    decision_cutoff: str
    acceptance_ids: tuple[str, str]
