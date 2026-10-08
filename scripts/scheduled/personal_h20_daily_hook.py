"""既有每日 invocation 的個人 H20 接線；不依賴 entry capture 或新訓練。"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
import importlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app_module.recommendation.personal_h20_activation import read_personal_h20_activation
from app_module.recommendation.personal_h20_read_session import (
    PersonalH20ReadProgress,
    PersonalH20ReadSession,
)

if TYPE_CHECKING:
    from data_module.pinned_sqlite_read_session import PinnedSQLiteReadSession
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
    from app_module.recommendation.personal_h20_product_evidence import read_personal_h20_product_reference
    from app_module.recommendation.personal_h20_research_cohort import read_personal_h20_research_cohort

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
        session.report(stage="reference_read_started")
        reference = read_personal_h20_product_reference(config_path, market_root=market_root)
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
            session.report(stage="reference_rechecked", pass_name="terminal")

        session.finish(finalizer=finalizer)
        if operation is not None:
            operation.finish()
        return reference, cohort
    finally:
        if session is not None:
            session.close()
        if operation is not None:
            operation.close()


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
