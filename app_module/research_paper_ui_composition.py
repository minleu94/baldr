"""明選外部證據的研究 Paper UI 組裝；預覽不建立帳戶或帳本。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app_module.application_bootstrap import (
    ApplicationSettings, configured_research_paper_evidence_binding_selection,
)
from app_module.paper_trade_ledger import PaperTradeLedgerRepository
from app_module.personal_data_paths import PersonalDataPaths
from app_module.personal_paper_store_paths import PersonalPaperStorePaths
from app_module.research_paper_evidence_binding import ResearchPaperEvidenceBindingReader
from app_module.research_paper_producer import HumanConfirmedPaperIntent, ResearchPaperProducer
from app_module.research_timeline_dtos import ResearchTimelineEntry
from app_module.strategy_paper_account_service import AccountBindingStatus, StrategyPaperAccountService


@dataclass(frozen=True, slots=True)
class ResearchPaperSimulationComposition:
    provider: ResearchPaperEvidenceBindingReader
    producer_factory: Callable[[HumanConfirmedPaperIntent], ResearchPaperProducer]


def configured_research_paper_simulation(
    *, settings: ApplicationSettings, entry: ResearchTimelineEntry,
    timeline_service: object, account_service: StrategyPaperAccountService | None,
    personal_paths: PersonalDataPaths | None, protected_roots: tuple[Path, ...] = (),
) -> ResearchPaperSimulationComposition | None:
    """只依明選設定組裝；writer factory 必須留待使用者明確確認後呼叫。"""
    selected = configured_research_paper_evidence_binding_selection(settings)
    if selected is None:
        return None
    if account_service is None or personal_paths is None:
        raise ValueError("研究 Paper 尚未選定 PERSONAL 帳戶與版本契約。")
    provider = ResearchPaperEvidenceBindingReader(
        selected[0], "sha256:" + selected[1], timeline_service, account_service,
        personal_paths, protected_roots=(*protected_roots, personal_paths.personal_root),
    )

    def confirmed_producer(intent: HumanConfirmedPaperIntent) -> ResearchPaperProducer:
        # 確認後仍重讀原件；namespace 與路徑只取受信帳戶服務，不由 UI 指定檔名。
        context = provider.verify(entry, intent)
        selection = account_service.select_account(context.binding.account_namespace)
        if (
            selection.status is not AccountBindingStatus.READY
            or selection.binding != context.binding or selection.route is None
        ):
            raise ValueError("Paper 帳戶版本或來源已變更，請重新預覽。")
        paths = PersonalPaperStorePaths.from_route(
            selection.route, portfolio_id=context.binding.portfolio_id,
        )
        if not paths.cost_ledger_db.is_file():
            raise ValueError("明選 Paper 帳本缺件；本流程不建立帳戶或資金。")
        ledger = PaperTradeLedgerRepository(
            paths.cost_ledger_db, route=selection.route, personal_paths=personal_paths,
            portfolio_id=context.binding.portfolio_id,
        )
        return ResearchPaperProducer(evidence_provider=provider, ledger=ledger)

    return ResearchPaperSimulationComposition(provider, confirmed_producer)
