"""Research Lab Paper 唯讀組裝；不建立帳戶或資料庫。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from data_module.config import _paper_contract_artifacts_root_path_error

from app_module.personal_data_paths import PersonalDataPaths
from app_module.personal_store_routes import PersonalStoreMode


@dataclass(frozen=True, slots=True)
class PaperCheckpointAccountInputs:
    """只攜帶 Main 已選 PERSONAL 路由與外部合約根。"""

    personal_paths: PersonalDataPaths
    contract_artifacts_root: Path

    def __post_init__(self) -> None:
        if not isinstance(self.personal_paths, PersonalDataPaths):
            raise TypeError("paper_personal_paths_required")
        root = Path(self.contract_artifacts_root)
        blocker = _paper_contract_artifacts_root_path_error(
            root, require_existing_directory=True
        )
        if blocker is not None:
            raise ValueError(blocker)
        object.__setattr__(self, "contract_artifacts_root", root)

    @classmethod
    def from_selection(
        cls,
        selection: Any,
        *,
        contract_artifacts_root: str | Path | None,
        disabled_reason: str | None = None,
    ) -> tuple[PaperCheckpointAccountInputs | None, str | None]:
        """缺任一明示條件就停用，不掃描路徑或回退 legacy store。"""

        if getattr(selection, "mode", None) is not PersonalStoreMode.PERSONAL:
            return None, "Paper 策略帳戶只在 PERSONAL store 模式提供。"
        personal_paths = getattr(selection, "paths", None)
        if not isinstance(personal_paths, PersonalDataPaths):
            return None, "PERSONAL store 尚未提供有效 PersonalDataPaths。"
        if disabled_reason:
            return None, disabled_reason
        if contract_artifacts_root is None:
            return None, "請明示 PAPER_CONTRACT_ARTIFACTS_ROOT 外部絕對路徑。"
        raw_root = (
            contract_artifacts_root.strip()
            if isinstance(contract_artifacts_root, str)
            else contract_artifacts_root
        )
        root = Path(raw_root)
        if not root.is_absolute():
            return None, "PAPER_CONTRACT_ARTIFACTS_ROOT 必須是明示絕對路徑。"
        blocker = _paper_contract_artifacts_root_path_error(
            root, require_existing_directory=True
        )
        if blocker is not None:
            return None, blocker
        package_root = Path(__file__).resolve().parents[1]
        try:
            resolved_root = root.resolve(strict=True)
        except (OSError, RuntimeError):
            return None, "PAPER_CONTRACT_ARTIFACTS_ROOT 無法安全解析；Paper 快照查找已停用。"
        if (
            resolved_root == package_root
            or resolved_root.is_relative_to(package_root)
            or package_root.is_relative_to(resolved_root)
        ):
            return None, "PAPER_CONTRACT_ARTIFACTS_ROOT 必須位於應用程式套件外部。"
        try:
            return cls(personal_paths, resolved_root), None
        except ValueError as exc:
            return None, str(exc)

    def build_account_service(self, strategy_version_service: Any) -> Any:
        """沿用 BacktestView 同一個 StrategyVersionService 的版本根。"""

        versions_root = getattr(strategy_version_service, "versions_dir", None)
        if versions_root is None:
            raise ValueError("shared_strategy_version_service_unavailable")
        versions_path = Path(versions_root)
        if not versions_path.is_absolute():
            raise ValueError("strategy_versions_root_must_be_absolute")
        from app_module.strategy_paper_account_service import StrategyPaperAccountService

        return StrategyPaperAccountService(
            personal_paths=self.personal_paths,
            strategy_versions_root=versions_path,
            contract_artifacts_root=self.contract_artifacts_root,
        )
