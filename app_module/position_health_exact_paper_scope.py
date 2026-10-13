"""Paper-main route 綁定的 Position Health exact snapshot scope factory。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from app_module.personal_data_paths import PersonalDataPaths
from app_module.paper_portfolio_snapshot_repository import PaperPortfolioSnapshotRepository
from app_module.personal_paper_store_paths import PersonalPaperStorePaths
from app_module.personal_store_routes import PersonalStoreDomain, PersonalStoreRoute
from app_module.position_health_daily_refresh_service import (
    PaperHealthSnapshotBundle,
    PositionHealthDailyRefreshService,
)
from app_module.position_health_saved_archive import (
    PositionHealthAccountScope,
    PositionHealthExactScope,
    PositionHealthPositionScope,
    SavedHealthReceiptSelector,
    SavedHealthReceiptSource,
    SavedPositionHealthReadModel,
)
from app_module.position_health_transition_read_service import PositionHealthTransitionReadService


@dataclass(frozen=True)
class OpenSavedHealthSelection:
    """一次 exact reopen 的 receipt、Paper source bundle 與投影結果。"""

    source: SavedHealthReceiptSource
    snapshot: PaperHealthSnapshotBundle
    scope: PositionHealthExactScope
    read_model: SavedPositionHealthReadModel
    paper_snapshot_receipt_present: bool


class PositionHealthExactPaperScopeFactory:
    """只接受明示未命名 paper-main route，不把 strategy 當 Paper main。"""

    def __init__(
        self,
        *,
        reader: PositionHealthTransitionReadService,
        route: PersonalStoreRoute,
        personal_paths: PersonalDataPaths | None,
        state_db_path: str | Path,
        status_path: str | Path,
        ledger_db_path: str | Path,
        coverage_status_path: str | Path,
    ) -> None:
        if (
            route.domain is not PersonalStoreDomain.PAPER
            or route.identity.key != "paper-main"
            or route.paper_account_namespace is not None
        ):
            raise ValueError("health_exact_scope_requires_unnamespaced_paper_main_route")
        if personal_paths is None and route.mode.value == "personal":
            raise ValueError("health_exact_scope_personal_paths_required")
        paths = PersonalPaperStorePaths.from_route(route, portfolio_id="paper-main")
        if paths.state_db.resolve() != Path(state_db_path).expanduser().resolve():
            raise ValueError("health_exact_scope_state_db_route_mismatch")
        if paths.status.resolve() != Path(status_path).expanduser().resolve():
            raise ValueError("health_exact_scope_status_route_mismatch")
        if paths.cost_ledger_db.resolve() != Path(ledger_db_path).expanduser().resolve():
            raise ValueError("health_exact_scope_ledger_route_mismatch")
        self.reader = reader
        self.route = route
        self.personal_paths = personal_paths
        self.state_db_path = paths.state_db
        self.snapshot_reader = PositionHealthDailyRefreshService(
            state_db_path=paths.state_db,
            status_path=paths.status,
            ledger_db_path=paths.cost_ledger_db,
            coverage_status_path=coverage_status_path,
            portfolio_id="paper-main",
        )
        self.snapshot_repository = PaperPortfolioSnapshotRepository(
            paths.state_db,
            route=route,
            portfolio_id="paper-main",
            personal_paths=personal_paths,
            force_read_only=True,
        )

    def open_saved_selection(
        self,
        selector: SavedHealthReceiptSelector,
        *,
        cancel_callback: Callable[[], bool] | None = None,
        expected_receipt_sha256: str | None = None,
        expected_result_sha256: str | None = None,
        expected_snapshot_rows_sha256: str | None = None,
        expected_snapshot_id: str | None = None,
        expected_decision_date: str | None = None,
    ) -> OpenSavedHealthSelection:
        """重讀 selected receipt 與同 route 的 exact Paper snapshot，再做 exact projection。"""

        def check_cancel() -> None:
            if cancel_callback is not None and cancel_callback():
                raise RuntimeError("saved_health_exact_selection_cancelled")

        check_cancel()
        source = self.reader.read_saved_source(
            selector, cancel_callback=cancel_callback
        )
        if source.portfolio_id != "paper-main" or source.namespace is not None:
            raise ValueError("health_exact_receipt_not_unnamespaced_paper_main")
        if expected_receipt_sha256 is not None and source.receipt_sha256 != expected_receipt_sha256:
            raise ValueError("health_exact_selected_receipt_sha_changed")
        if expected_result_sha256 is not None and source.result_sha256 != expected_result_sha256:
            raise ValueError("health_exact_selected_result_sha_changed")
        if expected_snapshot_rows_sha256 is not None and source.source_snapshot_rows_sha256 != expected_snapshot_rows_sha256:
            raise ValueError("health_exact_selected_rows_sha_changed")
        if expected_snapshot_id is not None and source.snapshot_id != expected_snapshot_id:
            raise ValueError("health_exact_selected_snapshot_id_changed")
        if expected_decision_date is not None and source.decision_date.isoformat() != expected_decision_date:
            raise ValueError("health_exact_selected_decision_date_changed")

        check_cancel()
        snapshot = self.snapshot_reader.read_exact_snapshot_bundle(
            source.snapshot_id,
            route=self.route,
            personal_paths=self.personal_paths,
        )
        if (
            snapshot.account_kind != "paper-main"
            or snapshot.account_namespace is not None
            or snapshot.portfolio_id != source.portfolio_id
            or snapshot.snapshot_id != source.snapshot_id
            or snapshot.decision_date != source.decision_date
            or snapshot.source_snapshot_rows_sha256 != source.source_snapshot_rows_sha256
        ):
            raise ValueError("health_exact_paper_snapshot_source_mismatch")

        check_cancel()
        saved_snapshot = self.snapshot_repository.get(source.snapshot_id)
        if saved_snapshot is None:
            raise ValueError("health_exact_paper_snapshot_repository_row_missing")
        if (
            saved_snapshot.snapshot_id != snapshot.snapshot_id
            or saved_snapshot.portfolio_id != snapshot.portfolio_id
            or saved_snapshot.decision_date != snapshot.decision_date.isoformat()
            or saved_snapshot.source_result_id != snapshot.source_result_id
        ):
            raise ValueError("health_exact_public_snapshot_reader_identity_mismatch")
        repository_rows = tuple(
            (row.stock_code, row.quantity, row.weight_bp)
            for row in saved_snapshot.positions
        )
        exact_rows = tuple(
            (row.stock_code, row.shares, row.weight_bp)
            for row in snapshot.all_positions
        )
        if repository_rows != exact_rows:
            raise ValueError("health_exact_public_snapshot_reader_positions_mismatch")
        exact_positions = {row.stock_code: row.shares for row in snapshot.positions}
        paper_receipt = self.snapshot_repository.get_receipt(source.snapshot_id)
        if paper_receipt is not None:
            if (
                paper_receipt.account_namespace is not None
                or paper_receipt.portfolio_id != "paper-main"
                or paper_receipt.snapshot_id != source.snapshot_id
                or paper_receipt.decision_date != snapshot.decision_date.isoformat()
            ):
                raise ValueError("health_exact_paper_snapshot_receipt_account_mismatch")

        witness_by_code = {}
        for row in source.positions:
            if row.stock_code in witness_by_code:
                raise ValueError("health_exact_duplicate_source_stock_code")
            witness_by_code[row.stock_code] = row
        if set(witness_by_code) != set(exact_positions):
            raise ValueError("health_exact_source_position_set_mismatch")
        scoped_positions: list[PositionHealthPositionScope] = []
        for row in snapshot.positions:
            source_row = witness_by_code[row.stock_code]
            if source_row.shares != row.shares:
                raise ValueError("health_exact_source_position_shares_mismatch")
            # stock_code 只在同一 snapshot 內配對 witness；position_id 一律來自保存的正式 witness。
            scoped_positions.append(
                PositionHealthPositionScope(
                    position_id=source_row.position_id,
                    stock_code=source_row.stock_code,
                    shares=source_row.shares,
                )
            )

        scope = PositionHealthExactScope(
            portfolio_id="paper-main",
            snapshot_id=snapshot.snapshot_id,
            decision_date=snapshot.decision_date,
            decision_cutoff=self.reader.current_clock(),
            positions=tuple(scoped_positions),
            expected_source_snapshot_rows_sha256=snapshot.source_snapshot_rows_sha256,
            account_scope=PositionHealthAccountScope(
                account_kind="paper-main",
                namespace=None,
            ),
        )
        check_cancel()
        read_model = self.reader.read_saved_exact(selector, scope)
        if (
            read_model.receipt_id != source.receipt_id
            or read_model.receipt_sha256 != source.receipt_sha256
            or read_model.result_sha256 != source.result_sha256
            or read_model.portfolio_id != snapshot.portfolio_id
            or read_model.source_snapshot_id != snapshot.snapshot_id
            or read_model.source_snapshot_rows_sha256 != snapshot.source_snapshot_rows_sha256
            or read_model.decision_date != snapshot.decision_date.isoformat()
        ):
            raise ValueError("health_exact_read_model_reopen_identity_mismatch")
        if read_model.source_witness_status != "structurally_valid":
            raise ValueError("health_exact_read_model_witness_unqualified")
        return OpenSavedHealthSelection(
            source=source,
            snapshot=snapshot,
            scope=scope,
            read_model=read_model,
            paper_snapshot_receipt_present=paper_receipt is not None,
        )
