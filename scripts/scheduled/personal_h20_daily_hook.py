"""既有每日 invocation 的個人 H20 接線；不依賴 entry capture 或新訓練。"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import stat
from typing import TYPE_CHECKING, Any

from app_module.recommendation.personal_h20_activation import read_personal_h20_activation
from app_module.recommendation.personal_h20_read_session import (
    PersonalH20ReadProgress,
    PersonalH20ReadSession,
)
from app_module.recommendation.personal_h20_verified_cohort_view import (
    PersonalH20VerifiedCohortView,
    _issue_personal_h20_verified_cohort_view,
    assert_personal_h20_verified_cohort_view,
    project_personal_h20_verified_cohort_selection,
)

if TYPE_CHECKING:
    from data_module.pinned_sqlite_read_session import PinnedSQLiteReadSession
    from app_module.recommendation.personal_h20_product_evidence import (
        PersonalH20ProductEvidence,
        PersonalH20ProductReference,
    )
    from app_module.recommendation.personal_h20_research_cohort import (
        PersonalH20ResearchCohort,
        PersonalH20ResearchSelection,
    )
    from scripts.scheduled.personal_h20_sqlite_read_operation import (
        PersonalH20SQLiteReadOperation,
    )

SQLiteReadSessionResolver = Callable[[Path, str], "PinnedSQLiteReadSession"]

SOURCE_PIN_KEYS = (
    "cycle_id", "raw_run_id", "cycle_source_date",
    "cycle_terminal_path", "cycle_terminal_sha256",
    "snapshot_database_path", "snapshot_database_sha256",
    "snapshot_receipt_path", "snapshot_receipt_sha256",
    "source_context_envelope_path", "source_context_envelope_sha256",
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def read_personal_h20_prediction(path: str | Path, *, root: Path, expected_sha256: str) -> Mapping[str, Any]:
    """公開CLI composition接原App reader；App/Qt不用import ML。"""
    ports = _personal_h20_read_ports()
    return _read_personal_h20_prediction_with_verifiers(
        path,
        root=root,
        expected_sha256=expected_sha256,
        source_verifier=ports["source_verifier"],
        contract_verifier=ports["contract_verifier"],
    )


def _personal_h20_read_ports(
    *,
    read_session_resolver: SQLiteReadSessionResolver | None = None,
) -> Mapping[str, Callable[..., Any]]:
    module = importlib.import_module("scripts.scheduled.run_personal_current_observed_h20_daily")
    factory = getattr(module, "personal_current_observed_h20_read_ports")
    ports = (
        factory()
        if read_session_resolver is None
        else factory(read_session_resolver=read_session_resolver)
    )
    if (not isinstance(ports, Mapping)
            or not callable(ports.get("source_verifier"))
            or not callable(ports.get("contract_verifier"))):
        raise ValueError("personal_h20_public_read_ports_required")
    return ports


def _open_personal_h20_sqlite_operation(
    *,
    sqlite_read_root: Path | None,
    require_sqlite_copy: bool,
    cancel_callback: Callable[[], bool] | None,
    progress_callback: Callable[[str], None] | None,
) -> "PersonalH20SQLiteReadOperation | None":
    """建立單次 H20 UI 操作的明示副本 operation；不推測或建立私有根。"""

    if type(require_sqlite_copy) is not bool:
        raise TypeError("personal_h20_sqlite_copy_requirement_must_be_bool")
    if sqlite_read_root is None and not require_sqlite_copy:
        return None
    if sqlite_read_root is None:
        raise ValueError("personal_h20_sqlite_read_root_required")

    from data_module.pinned_sqlite_read_session import MAX_COPY_BYTES_HARD_LIMIT
    from scripts.scheduled.personal_h20_sqlite_read_operation import (
        PersonalH20SQLiteReadOperation,
    )

    last_progress: tuple[str, int, int, int] | None = None

    def copy_progress(stage: str, current: int, total: int) -> None:
        nonlocal last_progress
        if progress_callback is not None:
            # 每個來源仍逐區塊核驗與檢查取消；只將顯示通知合併到整數百分比。
            # 階段切換、重新開始及最後位元組必須即時交付。
            percent = current * 100 // total if total > 0 else 0
            previous = last_progress
            last_progress = (stage, total, current, percent)
            if (previous is not None and previous[0] == stage and previous[1] == total
                    and current >= previous[2] and percent == previous[3]
                    and current != total):
                return
            labels = {
                "copy_snapshot_bytes": "建立安全副本",
                "verify_private_copy_bytes": "核驗副本內容",
                "open_private_reader": "準備讀取副本",
                "reader_transaction_ready": "唯讀來源已就緒",
            }
            is_bytes = stage in {"copy_snapshot_bytes", "verify_private_copy_bytes"}
            if stage.startswith("pin_source_file_group"):
                label = "核驗原封存資料"
                is_bytes = stage != "pin_source_file_group"
            elif stage.startswith("finish_source_revalidation"):
                label = "確認原封存資料未變"
                is_bytes = stage != "finish_source_revalidation"
            else:
                label = labels.get(stage, "核驗保存來源")
            detail = f"，已核對 {current}/{total} 位元組" if is_bytes else ""
            progress_callback(f"H20 正在核驗保存來源（唯讀 SQLite 副本）：{label}{detail}。")

    operation = PersonalH20SQLiteReadOperation(
        private_root=sqlite_read_root,
        max_source_groups=50,
        max_total_copy_bytes=MAX_COPY_BYTES_HARD_LIMIT,
        cancel_callback=cancel_callback,
        progress_callback=copy_progress,
    )
    operation.__enter__()
    try:
        if progress_callback is not None:
            progress_callback(
                "H20 正在準備安全讀取保存來源；後續會顯示目前階段與複製進度。"
            )
    except BaseException as original_error:
        try:
            operation.close()
        except BaseException as cleanup_error:
            raise original_error from cleanup_error
        raise
    return operation


def _read_personal_h20_prediction_with_verifiers(
    path: str | Path,
    *,
    root: Path,
    expected_sha256: str,
    source_verifier: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    contract_verifier: Callable[[Mapping[str, Any]], Mapping[str, Any]],
) -> Mapping[str, Any]:
    capture_module = importlib.import_module("app_module.recommendation.personal_current_observed_h20_capture")
    return getattr(capture_module, "read_personal_current_observed_h20_capture")(
        path, root=root, expected_sha256=expected_sha256,
        source_verifier=source_verifier, contract_verifier=contract_verifier)


def _progress_message(event: PersonalH20ReadProgress) -> str:
    identity = ("" if event.identity_sha256 is None
                else "（" + event.identity_sha256[:12] + "）")
    if event.row_index is not None and event.stage in {
        "capture_read_started",
        "capture_read_verified",
    }:
        pass_text = "終態重讀" if event.pass_name == "terminal" else "讀取"
        stock = "" if event.stock_code is None else f" {event.stock_code}"
        state = "完成" if event.stage == "capture_read_verified" else "進行中"
        return f"H20 {pass_text}已保存第 {event.row_index} 列{stock}：{state}"
    if event.verifier_kind is not None:
        label = "來源" if event.verifier_kind == "source" else "模型合約"
        index = "" if event.group_index is None else f"第 {event.group_index} 組"
        total = "" if event.group_total is None else f"／共 {event.group_total} 組"
        if event.stage.endswith("reused"):
            return f"H20 共用本次已核驗的{label}{index}{identity}"
        if event.stage.endswith("recheck_started"):
            return f"H20 終態重驗{label}{index}{total}{identity}"
        if event.stage.endswith("rechecked"):
            return f"H20 已完成終態重驗{label}{index}{total}{identity}"
        if event.stage.endswith("started"):
            return f"H20 正在核驗{label}{index}{identity}"
        return f"H20 已核驗{label}{index}{identity}"
    if event.stage == "reference_read_started":
        return "H20 正在讀取固定的個人研究來源"
    if event.stage == "reference_read_verified":
        return "H20 已核對固定來源指標與 manifest pin"
    if event.stage == "manifest_read_started":
        label = "終態重讀原 manifest 與全部 capture pins" if event.pass_name == "terminal" else "讀取原 manifest 與全部 capture pins"
        return f"H20 正在{label}"
    if event.stage == "manifest_read_complete":
        label = "終態重讀" if event.pass_name == "terminal" else "讀取"
        return f"H20 {label}完成，共驗證 {event.row_index or 0} 列 pin"
    if event.stage == "reference_rechecked":
        return "H20 已完成 activation/reference 終態重驗"
    return "H20 正在完成保存來源終態重驗"


def read_personal_h20_daily_receipt(path: str | Path, *, root: Path, expected_sha256: str,
                                   selected_stock: str | None = None) -> Mapping[str, Any]:
    from app_module.recommendation.personal_h20_product_evidence import read_personal_h20_daily_manifest

    return read_personal_h20_daily_manifest(path, root=root, expected_sha256=expected_sha256,
        selected_stock=selected_stock, prediction_reader=read_personal_h20_prediction)


def read_personal_h20_product_cohort(config_path: Path, *, market_root: Path,
    cancel_callback: Callable[[], bool] | None = None,
    progress_callback: Callable[[str], None] | None = None,
    sqlite_read_root: Path | None = None,
    require_sqlite_copy: bool = False) -> tuple[Any, Any]:
    """同一操作分組核驗，仍逐列讀原 capture 並重讀完整分母終態。"""
    result = _read_personal_h20_product_cohort_pipeline(
        config_path,
        market_root=market_root,
        cancel_callback=cancel_callback,
        progress_callback=progress_callback,
        sqlite_read_root=sqlite_read_root,
        require_sqlite_copy=require_sqlite_copy,
        issue_verified_view=False,
    )
    if type(result) is not tuple or len(result) != 2:
        raise RuntimeError("personal_h20_cohort_reader_result_invalid")
    return result


def read_personal_h20_verified_cohort_view(
    config_path: Path,
    *,
    market_root: Path,
    sqlite_read_root: Path,
    cancel_callback: Callable[[], bool] | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> PersonalH20VerifiedCohortView:
    """以唯讀副本完成完整母體後，簽發程序內 view。"""

    result = _read_personal_h20_product_cohort_pipeline(
        config_path,
        market_root=market_root,
        cancel_callback=cancel_callback,
        progress_callback=progress_callback,
        sqlite_read_root=sqlite_read_root,
        require_sqlite_copy=True,
        issue_verified_view=True,
    )
    if type(result) is not PersonalH20VerifiedCohortView:
        raise RuntimeError("personal_h20_verified_view_result_invalid")
    return result


def validate_personal_h20_verified_cohort_view_reference(
    view: PersonalH20VerifiedCohortView,
    *,
    config_path: Path,
    market_root: Path,
    sqlite_read_root: Path,
) -> None:
    """重讀小型 reference 並拒絕設定、根目錄或來源指標變更。"""

    from app_module.recommendation.personal_h20_product_evidence import (
        read_personal_h20_product_reference,
    )

    assert_personal_h20_verified_cohort_view(view)
    before_roots = _personal_h20_view_context_identities(
        config_path,
        market_root=market_root,
        personal_root=Path(view.reference.activation.personal_root),
        sqlite_read_root=sqlite_read_root,
    )
    if before_roots != _personal_h20_view_context_from_view(view):
        raise ValueError("personal_h20_verified_view_context_changed")
    current = read_personal_h20_product_reference(config_path, market_root=market_root)
    if current != view.reference:
        raise ValueError("personal_h20_verified_view_reference_changed")
    after_roots = _personal_h20_view_context_identities(
        config_path,
        market_root=market_root,
        personal_root=Path(current.activation.personal_root),
        sqlite_read_root=sqlite_read_root,
    )
    if after_roots != before_roots:
        raise ValueError("personal_h20_verified_view_context_changed_during_read")


def project_personal_h20_verified_cohort_selection_with_reference(
    view: PersonalH20VerifiedCohortView,
    selection: "PersonalH20ResearchSelection",
    *,
    config_path: Path,
    market_root: Path,
    sqlite_read_root: Path,
    cancel_callback: Callable[[], bool] | None = None,
) -> "PersonalH20ProductEvidence":
    """精確重讀 reference 後投影；不開 SQLite 或原 capture。"""

    _poll_personal_h20_cancel(cancel_callback)
    evidence = project_personal_h20_verified_cohort_selection(view, selection)
    validate_personal_h20_verified_cohort_view_reference(
        view,
        config_path=config_path,
        market_root=market_root,
        sqlite_read_root=sqlite_read_root,
    )
    _poll_personal_h20_cancel(cancel_callback)
    validate_personal_h20_verified_cohort_view_reference(
        view,
        config_path=config_path,
        market_root=market_root,
        sqlite_read_root=sqlite_read_root,
    )
    _poll_personal_h20_cancel(cancel_callback)
    return evidence


class _PersonalH20BindingProgressLedger:
    """只收集本 hook 建立的 typed verifier 終態事件。"""

    def __init__(self, consumer: Callable[[str], None] | None) -> None:
        self._consumer = consumer
        self._verified: dict[str, dict[int, str]] = {"source": {}, "contract": {}}
        self._rechecked: dict[str, dict[int, str]] = {"source": {}, "contract": {}}

    def __call__(self, event: PersonalH20ReadProgress) -> None:
        if type(event) is not PersonalH20ReadProgress:
            raise ValueError("personal_h20_progress_event_type_required")
        if event.stage in {"source_group_verified", "contract_group_verified"}:
            self._record(self._verified, event)
        elif event.stage in {"source_group_rechecked", "contract_group_rechecked"}:
            self._record(self._rechecked, event)
        if self._consumer is not None:
            self._consumer(_progress_message(event))

    def terminal_identities(self, session: PersonalH20ReadSession) -> tuple[tuple[str, ...], tuple[str, ...]]:
        results: dict[str, tuple[str, ...]] = {}
        for kind, count in (
            ("source", session.source_group_count),
            ("contract", session.contract_group_count),
        ):
            expected_indices = set(range(1, count + 1))
            verified = self._verified[kind]
            rechecked = self._rechecked[kind]
            if (set(verified) != expected_indices
                    or set(rechecked) != expected_indices
                    or verified != rechecked):
                raise ValueError("personal_h20_verified_view_binding_events_incomplete")
            identities = tuple(verified[index] for index in range(1, count + 1))
            if len(set(identities)) != len(identities):
                raise ValueError("personal_h20_verified_view_binding_event_duplicate")
            results[kind] = tuple(sorted(identities))
        return results["source"], results["contract"]

    @staticmethod
    def _record(
        destination: dict[str, dict[int, str]],
        event: PersonalH20ReadProgress,
    ) -> None:
        expected_kind = event.stage.split("_", 1)[0]
        if (event.verifier_kind != expected_kind
                or type(event.group_index) is not int
                or event.group_index < 1
                or type(event.identity_sha256) is not str
                or _SHA256.fullmatch(event.identity_sha256) is None):
            raise ValueError("personal_h20_verified_view_binding_event_invalid")
        bucket = destination[expected_kind]
        if event.group_index in bucket:
            raise ValueError("personal_h20_verified_view_binding_event_duplicate")
        bucket[event.group_index] = event.identity_sha256


def _read_personal_h20_product_cohort_pipeline(
    config_path: Path,
    *,
    market_root: Path,
    cancel_callback: Callable[[], bool] | None,
    progress_callback: Callable[[str], None] | None,
    sqlite_read_root: Path | None,
    require_sqlite_copy: bool,
    issue_verified_view: bool,
) -> Any:
    """兩個 public cohort API 共用單次讀取、終態與副本生命週期。"""
    from app_module.recommendation.personal_h20_product_evidence import read_personal_h20_product_reference
    from app_module.recommendation.personal_h20_research_cohort import read_personal_h20_research_cohort

    if issue_verified_view and (not require_sqlite_copy or sqlite_read_root is None):
        raise ValueError("personal_h20_verified_view_requires_sqlite_copy")

    operation = _open_personal_h20_sqlite_operation(
        sqlite_read_root=sqlite_read_root,
        require_sqlite_copy=require_sqlite_copy,
        cancel_callback=cancel_callback,
        progress_callback=progress_callback,
    )
    session: PersonalH20ReadSession | None = None
    initial_context: tuple[str, str, str, str] | None = None
    try:
        ports = _personal_h20_read_ports(
            read_session_resolver=None if operation is None else operation.session_for,
        )
        ledger = _PersonalH20BindingProgressLedger(progress_callback)
        session = PersonalH20ReadSession(
            source_verifier=ports["source_verifier"],
            contract_verifier=ports["contract_verifier"],
            cancel_callback=cancel_callback,
            progress_callback=ledger,
        )
        session.report(stage="reference_read_started")
        reference = read_personal_h20_product_reference(config_path, market_root=market_root)
        if issue_verified_view:
            if sqlite_read_root is None:
                raise ValueError("personal_h20_verified_view_requires_sqlite_copy")
            initial_context = _personal_h20_view_context_identities(
                config_path,
                market_root=market_root,
                personal_root=Path(reference.activation.personal_root),
                sqlite_read_root=sqlite_read_root,
            )
        session.report(stage="reference_read_verified")

        def read_pass(pass_name: str) -> Any:
            row_index = 0

            def reader(path: str | Path, *, root: Path, expected_sha256: str) -> Mapping[str, Any]:
                nonlocal row_index
                row_index += 1
                session.report(stage="capture_read_started", row_index=row_index, pass_name=pass_name)
                capture = _read_personal_h20_prediction_with_verifiers(
                    path,
                    root=root,
                    expected_sha256=expected_sha256,
                    source_verifier=session.verify_source,
                    contract_verifier=session.verify_contract,
                )
                session.report(stage="capture_read_verified", row_index=row_index, pass_name=pass_name)
                return capture

            session.report(stage="manifest_read_started", pass_name=pass_name)
            result = read_personal_h20_research_cohort(
                reference.manifest_path,
                root=Path(reference.activation.personal_root),
                expected_sha256=reference.manifest_sha256,
                prediction_reader=reader,
            )
            session.raise_if_progress_failed()
            session.report(
                stage="manifest_read_complete",
                row_index=row_index,
                pass_name=pass_name,
            )
            return result

        cohort = read_pass("initial")

        def finalizer() -> None:
            final_cohort = read_pass("terminal")
            if final_cohort != cohort:
                raise ValueError("personal_h20_cohort_changed_during_terminal_read")
            current_reference = read_personal_h20_product_reference(config_path, market_root=market_root)
            if current_reference != reference:
                raise ValueError("personal_h20_cohort_reference_changed")
            if issue_verified_view:
                if sqlite_read_root is None or initial_context is None:
                    raise ValueError("personal_h20_verified_view_context_required")
                final_context = _personal_h20_view_context_identities(
                    config_path,
                    market_root=market_root,
                    personal_root=Path(current_reference.activation.personal_root),
                    sqlite_read_root=sqlite_read_root,
                )
                if final_context != initial_context:
                    raise ValueError("personal_h20_verified_view_context_changed")
            session.report(stage="reference_rechecked", pass_name="terminal")

        session.finish(finalizer=finalizer)
        source_binding_ids: tuple[str, ...] = ()
        contract_binding_ids: tuple[str, ...] = ()
        if issue_verified_view:
            source_binding_ids, contract_binding_ids = ledger.terminal_identities(session)
        sqlite_binding_ids: tuple[str, ...] = ()
        if operation is not None:
            bindings = operation.finish()
            if issue_verified_view:
                from data_module.pinned_sqlite_read_session import PinnedSQLiteReadBindingV1

                if len(bindings) != operation.source_group_count or any(
                    type(binding) is not PinnedSQLiteReadBindingV1 for binding in bindings
                ):
                    raise ValueError("personal_h20_verified_view_sqlite_bindings_invalid")
                identities = tuple(binding.identity_sha256 for binding in bindings)
                if any(type(identity) is not str or _SHA256.fullmatch(identity) is None
                       for identity in identities):
                    raise ValueError("personal_h20_verified_view_sqlite_binding_identity_invalid")
                if len(set(identities)) != len(identities):
                    raise ValueError("personal_h20_verified_view_sqlite_binding_duplicate")
                sqlite_binding_ids = tuple(sorted(identities))
        session.check_cancel()
        if issue_verified_view:
            if sqlite_read_root is None or initial_context is None:
                raise ValueError("personal_h20_verified_view_context_required")
            current_reference = read_personal_h20_product_reference(config_path, market_root=market_root)
            if current_reference != reference:
                raise ValueError("personal_h20_verified_view_reference_changed_after_finish")
            final_context = _personal_h20_view_context_identities(
                config_path,
                market_root=market_root,
                personal_root=Path(current_reference.activation.personal_root),
                sqlite_read_root=sqlite_read_root,
            )
            if final_context != initial_context:
                raise ValueError("personal_h20_verified_view_context_changed_after_finish")
            view = _issue_personal_h20_verified_cohort_view(
                reference=reference,
                cohort=cohort,
                source_binding_identity_sha256=source_binding_ids,
                contract_binding_identity_sha256=contract_binding_ids,
                sqlite_binding_identity_sha256=sqlite_binding_ids,
                config_path_identity_sha256=initial_context[0],
                market_root_identity_sha256=initial_context[1],
                personal_root_identity_sha256=initial_context[2],
                sqlite_read_root_identity_sha256=initial_context[3],
            )
            # 簽章計算也可能耗時；最後一次取消檢查必須發生在 view 完成後。
            session.check_cancel()
            return view
        return reference, cohort
    finally:
        if session is not None:
            session.close()
        if operation is not None:
            operation.close()


def _personal_h20_view_context_identities(
    config_path: Path,
    *,
    market_root: Path,
    personal_root: Path,
    sqlite_read_root: Path,
) -> tuple[str, str, str, str]:
    return (
        _personal_h20_context_path_identity(config_path, directory=False),
        _personal_h20_context_path_identity(market_root, directory=True),
        _personal_h20_context_path_identity(personal_root, directory=True),
        _personal_h20_context_path_identity(sqlite_read_root, directory=True),
    )


def _personal_h20_context_path_identity(path: Path, *, directory: bool) -> str:
    requested = Path(path).expanduser()
    if not requested.is_absolute() or ".." in requested.parts:
        raise ValueError("personal_h20_verified_view_absolute_context_path_required")
    try:
        canonical = requested.resolve(strict=True)
        lexical = Path(os.path.abspath(requested))
        info = requested.lstat()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("personal_h20_verified_view_context_path_unavailable") from exc
    attributes = int(getattr(info, "st_file_attributes", 0))
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    if (os.path.normcase(str(lexical)) != os.path.normcase(str(canonical))
            or stat.S_ISLNK(info.st_mode)
            or attributes & reparse_flag
            or (directory and not stat.S_ISDIR(info.st_mode))
            or (not directory and not stat.S_ISREG(info.st_mode))
            or type(info.st_ino) is not int or info.st_ino <= 0
            or type(info.st_dev) is not int
            or (not directory and info.st_nlink != 1)):
        raise ValueError("personal_h20_verified_view_context_path_identity_invalid")
    identity = {
        "path": os.path.normcase(str(canonical)),
        "device": info.st_dev,
        "inode": info.st_ino,
        "mode": stat.S_IFMT(info.st_mode),
        "attributes": attributes,
        "nlink": None if directory else info.st_nlink,
    }
    raw = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _personal_h20_view_context_from_view(
    view: PersonalH20VerifiedCohortView,
) -> tuple[str, str, str, str]:
    return (
        view.config_path_identity_sha256,
        view.market_root_identity_sha256,
        view.personal_root_identity_sha256,
        view.sqlite_read_root_identity_sha256,
    )


def _poll_personal_h20_cancel(
    cancel_callback: Callable[[], bool] | None,
) -> None:
    if cancel_callback is None:
        return
    cancelled = cancel_callback()
    if type(cancelled) is not bool:
        raise ValueError("personal_h20_cancel_callback_must_return_bool")
    if cancelled:
        raise InterruptedError("personal_h20_verified_view_cancelled")


def read_personal_h20_product_for_stock_with_session(
    config_path: Path,
    *,
    stock_code: str,
    market_root: Path,
    expected_reference: Any | None = None,
    cancel_callback: Callable[[], bool] | None = None,
    progress_callback: Callable[[str], None] | None = None,
    sqlite_read_root: Path | None = None,
    require_sqlite_copy: bool = False,
) -> Any:
    """以單一 operation session 核原 manifest、選中 capture 與來源 pin。"""
    from app_module.recommendation.personal_h20_product_evidence import (
        read_personal_h20_daily_manifest,
        read_personal_h20_product_for_stock as read_product_for_stock,
        read_personal_h20_product_reference,
    )

    operation = _open_personal_h20_sqlite_operation(
        sqlite_read_root=sqlite_read_root,
        require_sqlite_copy=require_sqlite_copy,
        cancel_callback=cancel_callback,
        progress_callback=progress_callback,
    )
    session: PersonalH20ReadSession | None = None
    try:
        ports = _personal_h20_read_ports(
            read_session_resolver=None if operation is None else operation.session_for,
        )
        session = PersonalH20ReadSession(
            source_verifier=ports["source_verifier"],
            contract_verifier=ports["contract_verifier"],
            cancel_callback=cancel_callback,
            progress_callback=(
                None if progress_callback is None
                else lambda event: progress_callback(_progress_message(event))
            ),
        )
        session.report(stage="reference_read_started", stock_code=stock_code)
        reference = read_personal_h20_product_reference(config_path, market_root=market_root)
        if expected_reference is not None and reference != expected_reference:
            raise ValueError("personal_h20_selected_reference_changed")
        session.report(stage="reference_read_verified", stock_code=stock_code)

        row_index = 0

        def reader(path: str | Path, *, root: Path, expected_sha256: str) -> Mapping[str, Any]:
            nonlocal row_index
            row_index += 1
            session.report(
                stage="capture_read_started",
                row_index=row_index,
                pass_name="initial",
                stock_code=stock_code,
            )
            capture = _read_personal_h20_prediction_with_verifiers(
                path,
                root=root,
                expected_sha256=expected_sha256,
                source_verifier=session.verify_source,
                contract_verifier=session.verify_contract,
            )
            session.report(
                stage="capture_read_verified",
                row_index=row_index,
                pass_name="initial",
                stock_code=stock_code,
            )
            return capture

        first_manifest: Mapping[str, Any] | None = None

        def daily_reader(path: str | Path, *, root: Path, expected_sha256: str,
                         selected_stock: str | None = None) -> Mapping[str, Any]:
            nonlocal first_manifest
            body = read_personal_h20_daily_manifest(
                path,
                root=root,
                expected_sha256=expected_sha256,
                selected_stock=selected_stock,
                prediction_reader=reader,
            )
            if first_manifest is None:
                first_manifest = body
            return body

        evidence = read_product_for_stock(
            config_path,
            stock_code=stock_code,
            market_root=market_root,
            daily_reader=daily_reader,
            prediction_reader=reader,
            expected_reference=reference,
        )
        session.raise_if_progress_failed()

        def finalizer() -> None:
            session.report(
                stage="manifest_read_started",
                pass_name="terminal",
                stock_code=stock_code,
            )
            final_manifest = read_personal_h20_daily_manifest(
                reference.manifest_path,
                root=Path(reference.activation.personal_root),
                expected_sha256=reference.manifest_sha256,
                selected_stock=stock_code,
                prediction_reader=reader,
            )
            if first_manifest is not None and final_manifest != first_manifest:
                raise ValueError("personal_h20_selected_manifest_changed_during_read")
            session.report(
                stage="manifest_read_complete",
                row_index=row_index,
                pass_name="terminal",
                stock_code=stock_code,
            )
            current_reference = read_personal_h20_product_reference(config_path, market_root=market_root)
            if current_reference != reference:
                raise ValueError("personal_h20_selected_reference_changed")
            session.report(stage="reference_rechecked", pass_name="terminal", stock_code=stock_code)

        session.finish(finalizer=finalizer)
        if operation is not None:
            operation.finish()
        return evidence
    finally:
        if session is not None:
            session.close()
        if operation is not None:
            operation.close()


def run_personal_h20_for_current_cycle(
    config_path: Path | None, source_binding: Mapping[str, Any] | None, *,
    market_root: Path,
    expected_raw_run_id: str | None,
    runner: Callable[..., Any] | None = None,
    contract_verifier: Callable[..., Any] | None = None,
    daily_reader: Callable[..., Any] | None = None,
    prediction_reader: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """只在明示 enabled 時呼叫受驗 daily runner；它重驗原 terminal bytes。"""
    if config_path is None:
        return {"status": "not_configured", "effective_model_run": False}
    try:
        activation = read_personal_h20_activation(config_path)
        if not activation.enabled:
            return {"status": "disabled", "revision": activation.revision, "effective_model_run": False}
        if Path(activation.market_root) != market_root:
            raise ValueError("personal_h20_market_root_mismatch")
        if source_binding is None or source_binding.get("binding_mode") != "current_observed":
            return {"status": "pending_current_cycle", "effective_model_run": False}
        if not expected_raw_run_id or source_binding.get("raw_run_id") != expected_raw_run_id:
            raise ValueError("personal_h20_exact_raw_run_required")
        pins = {key: source_binding.get(key) for key in SOURCE_PIN_KEYS}
        if any(type(value) is not str or not value for value in pins.values()):
            raise ValueError("personal_h20_complete_source_pins_required")
        snapshot = source_binding.get("current_observed_feature_snapshot")
        if not isinstance(snapshot, Mapping):
            raise ValueError("personal_h20_feature_scope_required")
        symbols = snapshot.get("symbols")
        if (not isinstance(symbols, list) or not symbols
                or any(type(symbol) is not str or not symbol for symbol in symbols)
                or len(set(symbols)) != len(symbols)):
            raise ValueError("personal_h20_unique_feature_scope_required")
        if sorted(symbols) != sorted(source_binding.get("symbols", [])):
            raise ValueError("personal_h20_complete_feature_scope_required")
        feature_date = source_binding.get("feature_as_of_date")
        decision_date = source_binding.get("decision_date")
        if (type(feature_date) is not str or type(decision_date) is not str
                or date.fromisoformat(feature_date) >= date.fromisoformat(decision_date)):
            raise ValueError("personal_h20_feature_not_before_decision")
        if contract_verifier is None:
            from scripts.qa_prepare_personal_h20_gross_contract import prepare_contract

            contract_verifier = prepare_contract
        prepared = contract_verifier(Path(activation.fit_receipt), expected_fit_receipt_sha256=activation.fit_receipt_sha256)
        if (prepared["contract_hash"] != activation.model_contract_hash
                or prepared["contract"]["candidate_id"] != activation.candidate_id
                or prepared["contract"]["model_id"] != activation.model_id):
            raise ValueError("personal_h20_activation_contract_mismatch")
        request = {
            "schema_version": "personal-current-observed-h20-daily-request.v1",
            "data_root": activation.market_root, "source_pins": pins,
            "symbols": sorted(symbols), "history_start_date": activation.history_start_date,
            "expected_feature_as_of_date": feature_date,
        }
        if runner is None:
            module = importlib.import_module("scripts.scheduled.run_personal_current_observed_h20_daily")
            candidate = getattr(module, "run_personal_current_observed_h20_daily")
            if not callable(candidate):
                raise ValueError("personal_h20_runner_required")
            runner = candidate
        result = runner(request=request, receipt_root=Path(activation.personal_root),
                        gross_fit_receipt=Path(activation.fit_receipt),
                        expected_fit_receipt_sha256=activation.fit_receipt_sha256)
        if not isinstance(result, dict):
            raise ValueError("personal_h20_runner_receipt_required")
        result = dict(result)
        if result.get("status") == "completed":
            from app_module.recommendation.personal_h20_product_evidence import (
                publish_personal_h20_product_reference, save_personal_h20_daily_manifest,
            )

            receipt_path, receipt_pin, daily = save_personal_h20_daily_manifest(activation, result,
                expected_symbols=sorted(symbols), prediction_reader=prediction_reader or read_personal_h20_prediction)
            if daily_reader is None:
                daily_reader = read_personal_h20_daily_receipt
            daily = daily_reader(receipt_path, root=Path(activation.personal_root), expected_sha256=receipt_pin)
            if (daily["status"] != "completed" or daily["candidate_id"] != activation.candidate_id
                    or daily["contract_hash"] != activation.model_contract_hash
                    or daily["cycle_id"] != pins["cycle_id"]
                    or sorted(pin["symbol"] for pin in daily["captures"]) != sorted(symbols)):
                raise ValueError("personal_h20_completed_public_receipt_mismatch")
            publish_personal_h20_product_reference(activation, receipt_path=str(receipt_path),
                receipt_sha256=receipt_pin, decision_date=daily["decision_date"], cycle_id=daily["cycle_id"])
            result.update(receipt_path=str(receipt_path), receipt_sha256=receipt_pin)
            result["effective_model_run"] = True
        result.update(activation_revision=activation.revision, personal_scope_id=activation.scope_id,
                      expected_model_contract_hash=activation.model_contract_hash)
        return result
    except Exception as exc:
        # 不吞成成功，不提升原 formal/global 狀態；錯誤獨立留在 invocation 收據。
        return {"status": "blocked", "reason": str(exc)[:400], "effective_model_run": False}
