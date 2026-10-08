"""以單次驗證 session 重開固定 H20 收藏；不讀最新產品指標。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal, TypeAlias, cast

from app_module.recommendation.personal_current_observed_h20_capture import (
    read_personal_current_observed_h20_capture,
)
from app_module.recommendation.personal_h20_read_session import (
    PersonalH20ReadProgress,
    PersonalH20ReadSession,
    PersonalH20ReadSessionError,
    Verifier,
)
from app_module.recommendation.personal_h20_research_bookmark import (
    PersonalH20ResearchBookmark,
    PersonalH20ResearchBookmarkError,
    PersonalH20ResearchBookmarkState,
    _read_activation_snapshot,
    read_personal_h20_research_bookmark,
)
from app_module.recommendation.personal_h20_price_chart import (
    PersonalH20BookmarkVerifiedViewV1,
    PersonalH20PriceChartCollector,
    RawCurrentObservedObserver,
    personal_h20_bookmark_identity_sha256,
)
from scripts.scheduled import run_personal_current_observed_h20_daily


ProgressCallback = Callable[[str], None]
BookmarkInput: TypeAlias = PersonalH20ResearchBookmark | Mapping[str, object] | bytes | str


def _freeze_bookmark(value: BookmarkInput) -> PersonalH20ResearchBookmark:
    if isinstance(value, PersonalH20ResearchBookmark):
        return PersonalH20ResearchBookmark.from_dict(value.to_dict())
    if isinstance(value, (bytes, str)):
        return PersonalH20ResearchBookmark.from_json(value)
    return PersonalH20ResearchBookmark.from_dict(value)


def _progress_message(event: PersonalH20ReadProgress) -> str:
    identity = "" if event.identity_sha256 is None else f"（{event.identity_sha256[:12]}）"
    if event.row_index is not None and event.stage in {
        "capture_read_started",
        "capture_read_verified",
        "capture_read_rejected",
    }:
        pass_text = "收藏終態重讀" if event.pass_name == "terminal" else "收藏原來源讀取"
        stock = "" if event.stock_code is None else f" {event.stock_code}"
        state = {
            "capture_read_started": "進行中",
            "capture_read_verified": "完成",
            "capture_read_rejected": "保留為未知並記錄原因",
        }[event.stage]
        return f"H20 {pass_text}第 {event.row_index} 列{stock}：{state}"
    if event.verifier_kind is not None:
        label = "來源" if event.verifier_kind == "source" else "模型合約"
        index = "" if event.group_index is None else f"第 {event.group_index} 組"
        total = "" if event.group_total is None else f"／共 {event.group_total} 組"
        if event.stage.endswith("reused"):
            return f"H20 本次重用已核驗的{label}{index}{identity}"
        if event.stage.endswith("recheck_started"):
            return f"H20 終態重驗{label}{index}{total}{identity}"
        if event.stage.endswith("rechecked"):
            return f"H20 已完成終態重驗{label}{index}{total}{identity}"
        if event.stage.endswith("started"):
            return f"H20 正在核驗{label}{index}{identity}"
        return f"H20 已核驗{label}{index}{identity}"
    if event.stage == "activation_snapshot_started":
        return "H20 正在核對目前核准路徑與 activation 原始內容"
    if event.stage == "activation_snapshot_verified":
        return "H20 已取得本次操作的 activation 原始 pin"
    if event.stage == "activation_snapshot_rechecked":
        return "H20 已確認本次操作期間 activation 原始內容未變"
    if event.stage == "bookmark_read_started":
        label = "收藏終態重讀原 manifest 與全部 capture pins" if event.pass_name == "terminal" else "沿收藏固定的原 manifest 與全部 capture pins 讀取"
        return f"H20 正在{label}"
    if event.stage == "bookmark_read_complete":
        label = "收藏終態重讀" if event.pass_name == "terminal" else "收藏原來源讀取"
        return f"H20 {label}完成，共核對 {event.row_index or 0} 列 capture pin"
    if event.stage == "bookmark_session_complete":
        return "H20 收藏來源與合約終態重驗完成"
    return "H20 正在完成收藏原來源重驗"


def _read_ports(
    *,
    read_session_resolver: Callable[..., Any] | None = None,
    raw_snapshot_observer: RawCurrentObservedObserver | None = None,
) -> tuple[Verifier, Verifier]:
    factory = run_personal_current_observed_h20_daily.personal_current_observed_h20_read_ports
    if read_session_resolver is not None and raw_snapshot_observer is not None:
        ports = run_personal_current_observed_h20_daily.personal_current_observed_h20_read_ports(
            read_session_resolver=read_session_resolver,
            raw_snapshot_observer=raw_snapshot_observer,
        )
    elif read_session_resolver is not None:
        ports = factory(read_session_resolver=read_session_resolver)
    elif raw_snapshot_observer is not None:
        ports = factory(raw_snapshot_observer=raw_snapshot_observer)
    else:
        ports = factory()
    if (not isinstance(ports, Mapping)
            or not callable(ports.get("source_verifier"))
            or not callable(ports.get("contract_verifier"))):
        raise PersonalH20ReadSessionError("personal_h20_public_read_ports_required")
    return cast(Verifier, ports["source_verifier"]), cast(Verifier, ports["contract_verifier"])


def read_personal_h20_research_bookmark_with_session(
    bookmark: BookmarkInput,
    *,
    config_path: Path,
    market_root: Path,
    cancel_callback: Callable[[], bool] | None = None,
    progress_callback: ProgressCallback | None = None,
    sqlite_read_root: Path | None = None,
    require_sqlite_copy: bool = False,
) -> PersonalH20ResearchBookmarkState:
    """重開收藏保存的 manifest 與 captures，並在同操作內終態重驗。

    每次呼叫建立獨立 session。初讀與終態重讀都走既有 bookmark public
    reader；session 只分組來源與合約 verifier，不保存任何跨操作快取。
    """
    result = _read_personal_h20_research_bookmark_operation(
        bookmark,
        config_path=config_path,
        market_root=market_root,
        cancel_callback=cancel_callback,
        progress_callback=progress_callback,
        sqlite_read_root=sqlite_read_root,
        require_sqlite_copy=require_sqlite_copy,
        issue_price_chart=False,
    )
    if type(result) is not PersonalH20ResearchBookmarkState:
        raise PersonalH20ReadSessionError("personal_h20_bookmark_state_result_invalid")
    return result


def read_personal_h20_research_bookmark_view_with_session(
    bookmark: BookmarkInput,
    *,
    config_path: Path,
    market_root: Path,
    sqlite_read_root: Path,
    cancel_callback: Callable[[], bool] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> PersonalH20BookmarkVerifiedViewV1:
    """以全新唯讀副本重讀精確收藏，並在同次終態後簽發圖表 view。"""

    result = _read_personal_h20_research_bookmark_operation(
        bookmark,
        config_path=config_path,
        market_root=market_root,
        cancel_callback=cancel_callback,
        progress_callback=progress_callback,
        sqlite_read_root=sqlite_read_root,
        require_sqlite_copy=True,
        issue_price_chart=True,
    )
    if type(result) is not PersonalH20BookmarkVerifiedViewV1:
        raise PersonalH20ReadSessionError("personal_h20_bookmark_view_result_invalid")
    return result


def _read_personal_h20_research_bookmark_operation(
    bookmark: BookmarkInput,
    *,
    config_path: Path,
    market_root: Path,
    cancel_callback: Callable[[], bool] | None,
    progress_callback: ProgressCallback | None,
    sqlite_read_root: Path | None,
    require_sqlite_copy: bool,
    issue_price_chart: bool,
) -> PersonalH20ResearchBookmarkState | PersonalH20BookmarkVerifiedViewV1:
    saved_bookmark = _freeze_bookmark(bookmark)
    config = Path(config_path)
    market = Path(market_root)
    from scripts.scheduled.personal_h20_daily_hook import (
        _open_personal_h20_sqlite_operation,
        _PersonalH20BindingProgressLedger,
    )

    if issue_price_chart and (not require_sqlite_copy or sqlite_read_root is None):
        raise PersonalH20ReadSessionError("personal_h20_bookmark_chart_requires_sqlite_copy")

    operation = _open_personal_h20_sqlite_operation(
        sqlite_read_root=sqlite_read_root,
        require_sqlite_copy=require_sqlite_copy,
        cancel_callback=cancel_callback,
        progress_callback=progress_callback,
    )
    session: PersonalH20ReadSession | None = None
    chart_collector = PersonalH20PriceChartCollector() if issue_price_chart else None
    try:
        source_verifier, contract_verifier = _read_ports(
            read_session_resolver=None if operation is None else operation.session_for,
            raw_snapshot_observer=chart_collector,
        )
        ledger = _PersonalH20BindingProgressLedger(None) if issue_price_chart else None

        def progress_event(event: PersonalH20ReadProgress) -> None:
            if ledger is not None:
                ledger(event)
            if progress_callback is not None:
                progress_callback(_progress_message(event))

        session = PersonalH20ReadSession(
            source_verifier=source_verifier,
            contract_verifier=contract_verifier,
            cancel_callback=cancel_callback,
            progress_callback=progress_event if ledger is not None or progress_callback is not None else None,
        )
        session.report(stage="activation_snapshot_started", pass_name="initial")
        activation_before, activation_bytes_before = _read_activation_snapshot(config)
        session.report(stage="activation_snapshot_verified", pass_name="initial")

        def read_pass(pass_name: Literal["initial", "terminal"]) -> PersonalH20ResearchBookmarkState:
            row_index = 0

            def prediction_reader(
                path: str | Path,
                *,
                root: Path,
                expected_sha256: str,
            ) -> Mapping[str, Any]:
                nonlocal row_index
                row_index += 1
                session.report(
                    stage="capture_read_started",
                    row_index=row_index,
                    pass_name=pass_name,
                )
                try:
                    capture = read_personal_current_observed_h20_capture(
                        path,
                        root=root,
                        expected_sha256=expected_sha256,
                        source_verifier=session.verify_source,
                        contract_verifier=session.verify_contract,
                    )
                except InterruptedError:
                    raise
                except Exception:
                    session.report(
                        stage="capture_read_rejected",
                        row_index=row_index,
                        pass_name=pass_name,
                    )
                    raise
                if chart_collector is not None:
                    chart_collector.link_capture(
                        capture,
                        expected_sha256=expected_sha256,
                        pass_name=pass_name,
                    )
                session.report(
                    stage="capture_read_verified",
                    row_index=row_index,
                    pass_name=pass_name,
                )
                return capture

            session.report(stage="bookmark_read_started", pass_name=pass_name)
            state = read_personal_h20_research_bookmark(
                saved_bookmark,
                config_path=config,
                market_root=market,
                prediction_reader=prediction_reader,
                cancel_callback=cancel_callback,
            )
            session.raise_if_progress_failed()
            session.report(
                stage="bookmark_read_complete",
                row_index=len(state.cohort.rows),
                row_total=len(state.cohort.rows),
                pass_name=pass_name,
                stock_code=state.selected_row.symbol,
            )
            return state

        first_state = read_pass("initial")
        terminal_state: PersonalH20ResearchBookmarkState | None = None

        def finalizer() -> None:
            nonlocal terminal_state
            terminal_state = read_pass("terminal")
            if terminal_state != first_state:
                raise PersonalH20ResearchBookmarkError(
                    "personal_h20_bookmark_state_changed_during_read"
                    f": initial_selected_reason={first_state.selected_row.reason[:300]}"
                    f"; terminal_selected_reason={terminal_state.selected_row.reason[:300]}"
                )
            activation_after, activation_bytes_after = _read_activation_snapshot(config)
            if activation_bytes_after != activation_bytes_before or activation_after != activation_before:
                raise PersonalH20ResearchBookmarkError(
                    "personal_h20_bookmark_activation_changed_during_read"
                )
            session.report(stage="activation_snapshot_rechecked", pass_name="terminal")
            session.raise_if_progress_failed()
            session.report(stage="bookmark_session_complete", pass_name="terminal")

        session.finish(finalizer=finalizer)
        sqlite_binding_ids: tuple[str, ...] = ()
        if operation is not None:
            bindings = operation.finish()
            if issue_price_chart:
                from data_module.pinned_sqlite_read_session import PinnedSQLiteReadBindingV1

                if len(bindings) != operation.source_group_count or any(
                    type(binding) is not PinnedSQLiteReadBindingV1 for binding in bindings
                ):
                    raise PersonalH20ReadSessionError(
                        "personal_h20_bookmark_sqlite_bindings_invalid"
                    )
                identities = tuple(binding.identity_sha256 for binding in bindings)
                if (not identities or any(type(value) is not str or len(value) != 64
                                          or any(char not in "0123456789abcdef" for char in value)
                                          for value in identities)
                        or len(set(identities)) != len(identities)):
                    raise PersonalH20ReadSessionError(
                        "personal_h20_bookmark_sqlite_binding_identity_invalid"
                    )
                sqlite_binding_ids = tuple(sorted(identities))
        if terminal_state is None:
            raise PersonalH20ReadSessionError("personal_h20_bookmark_terminal_state_missing")
        session.check_cancel()
        if not issue_price_chart:
            return terminal_state
        if ledger is None or chart_collector is None:
            raise PersonalH20ReadSessionError("personal_h20_bookmark_chart_collector_missing")
        source_binding_ids, contract_binding_ids = ledger.terminal_identities(session)
        price_chart = None
        chart_reason_code: str | None = None
        try:
            price_chart = chart_collector.issue(
                terminal_state.cohort,
                source_binding_identity_sha256=source_binding_ids,
                contract_binding_identity_sha256=contract_binding_ids,
                sqlite_binding_identity_sha256=sqlite_binding_ids,
                bookmark_identity_sha256=personal_h20_bookmark_identity_sha256(saved_bookmark),
            )
        except Exception as exc:
            # 價格圖是旁路投影；不能讓其容量或觀察失敗抹掉已核收藏 evidence。
            candidate_reason = str(exc).split(":", 1)[0].strip()
            chart_reason_code = (
                "chart_capacity_exceeded"
                if candidate_reason == "chart_capacity_exceeded"
                else "chart_observer_failed"
            )
        result = PersonalH20BookmarkVerifiedViewV1(
            state=terminal_state,
            price_chart=price_chart,
            price_chart_reason_code=chart_reason_code,
        )
        session.check_cancel()
        return result
    finally:
        if session is not None:
            session.close()
        if operation is not None:
            operation.close()
