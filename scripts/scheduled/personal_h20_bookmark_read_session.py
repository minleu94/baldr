"""以單次驗證 session 重開固定 H20 收藏；不讀最新產品指標。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

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
from scripts.scheduled import run_personal_current_observed_h20_daily


ProgressCallback = Callable[[str], None]
BookmarkInput = PersonalH20ResearchBookmark | Mapping[str, object] | bytes | str


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


def _read_ports() -> tuple[Verifier, Verifier]:
    ports = run_personal_current_observed_h20_daily.personal_current_observed_h20_read_ports()
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
) -> PersonalH20ResearchBookmarkState:
    """重開收藏保存的 manifest 與 captures，並在同操作內終態重驗。

    每次呼叫建立獨立 session。初讀與終態重讀都走既有 bookmark public
    reader；session 只分組來源與合約 verifier，不保存任何跨操作快取。
    """
    saved_bookmark = _freeze_bookmark(bookmark)
    source_verifier, contract_verifier = _read_ports()
    session = PersonalH20ReadSession(
        source_verifier=source_verifier,
        contract_verifier=contract_verifier,
        cancel_callback=cancel_callback,
        progress_callback=(
            None if progress_callback is None
            else lambda event: progress_callback(_progress_message(event))
        ),
    )
    config = Path(config_path)
    market = Path(market_root)
    try:
        session.report(stage="activation_snapshot_started", pass_name="initial")
        activation_before, activation_bytes_before = _read_activation_snapshot(config)
        session.report(stage="activation_snapshot_verified", pass_name="initial")

        def read_pass(pass_name: str) -> PersonalH20ResearchBookmarkState:
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
        if terminal_state is None:
            raise PersonalH20ReadSessionError("personal_h20_bookmark_terminal_state_missing")
        return terminal_state
    finally:
        session.close()
