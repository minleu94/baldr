"""同一次 H20 讀取的來源與合約驗證分組；不跨操作保存快取。"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Any, Literal


Verifier = Callable[[Mapping[str, Any]], Mapping[str, Any]]
CancelCallback = Callable[[], bool]
ProgressCallback = Callable[["PersonalH20ReadProgress"], None]
VerifierKind = Literal["source", "contract"]


class PersonalH20ReadSessionError(ValueError):
    """H20 讀取 session 的輸入、狀態或終態重驗不符。"""


@dataclass(frozen=True, slots=True)
class PersonalH20ReadProgress:
    """不換算百分比的實際讀取階段、群組或列進度。"""

    stage: str
    verifier_kind: VerifierKind | None = None
    identity_sha256: str | None = None
    group_index: int | None = None
    group_total: int | None = None
    row_index: int | None = None
    row_total: int | None = None
    pass_name: str | None = None
    stock_code: str | None = None


@dataclass(frozen=True, slots=True)
class _VerifiedGroup:
    binding_json: bytes
    result_json: bytes
    identity_sha256: str


def _assert_json_value(value: Any, *, field: str) -> None:
    if value is None or type(value) in (str, bool, int, float):
        return
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise PersonalH20ReadSessionError(f"{field}_json_object_keys_must_be_text")
        for child in value.values():
            _assert_json_value(child, field=field)
        return
    if isinstance(value, (list, tuple)):
        for child in value:
            _assert_json_value(child, field=field)
        return
    raise PersonalH20ReadSessionError(f"{field}_must_be_json_value")


def _canonical_mapping(value: Mapping[str, Any], *, field: str) -> bytes:
    if not isinstance(value, Mapping):
        raise PersonalH20ReadSessionError(f"{field}_must_be_object")
    _assert_json_value(value, field=field)
    try:
        return json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise PersonalH20ReadSessionError(f"{field}_canonical_json_required") from exc


def _decode_mapping(raw: bytes, *, field: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise PersonalH20ReadSessionError(f"{field}_canonical_json_invalid") from exc
    if not isinstance(value, dict):
        raise PersonalH20ReadSessionError(f"{field}_must_be_object")
    return value


class PersonalH20ReadSession:
    """按完整 canonical binding 分組並在操作結束時新鮮重驗。"""

    def __init__(
        self,
        *,
        source_verifier: Verifier,
        contract_verifier: Verifier,
        cancel_callback: CancelCallback | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        if not callable(source_verifier) or not callable(contract_verifier):
            raise PersonalH20ReadSessionError("personal_h20_read_verifiers_required")
        if cancel_callback is not None and not callable(cancel_callback):
            raise PersonalH20ReadSessionError("personal_h20_cancel_callback_invalid")
        if progress_callback is not None and not callable(progress_callback):
            raise PersonalH20ReadSessionError("personal_h20_progress_callback_invalid")
        self._verifiers: dict[VerifierKind, Verifier] = {
            "source": source_verifier,
            "contract": contract_verifier,
        }
        self._cancel_callback = cancel_callback
        self._progress_callback = progress_callback
        self._groups: dict[VerifierKind, dict[bytes, _VerifiedGroup]] = {
            "source": {},
            "contract": {},
        }
        self._finishing = False
        self._finished = False
        self._closed = False
        self._progress_error: Exception | None = None

    @property
    def source_group_count(self) -> int:
        return len(self._groups["source"])

    @property
    def contract_group_count(self) -> int:
        return len(self._groups["contract"])

    def check_cancel(self) -> None:
        if self._cancel_callback is None:
            return
        cancelled = self._cancel_callback()
        if type(cancelled) is not bool:
            raise PersonalH20ReadSessionError("personal_h20_cancel_callback_must_return_bool")
        if cancelled:
            raise InterruptedError("personal_h20_read_cancelled")

    def report(
        self,
        *,
        stage: str,
        verifier_kind: VerifierKind | None = None,
        identity_sha256: str | None = None,
        group_index: int | None = None,
        group_total: int | None = None,
        row_index: int | None = None,
        row_total: int | None = None,
        pass_name: str | None = None,
        stock_code: str | None = None,
    ) -> None:
        self._ensure_open(allow_finishing=True)
        self.check_cancel()
        self._emit(
            stage=stage,
            verifier_kind=verifier_kind,
            identity_sha256=identity_sha256,
            group_index=group_index,
            group_total=group_total,
            row_index=row_index,
            row_total=row_total,
            pass_name=pass_name,
            stock_code=stock_code,
        )
        self.check_cancel()

    def _emit(
        self,
        *,
        stage: str,
        verifier_kind: VerifierKind | None = None,
        identity_sha256: str | None = None,
        group_index: int | None = None,
        group_total: int | None = None,
        row_index: int | None = None,
        row_total: int | None = None,
        pass_name: str | None = None,
        stock_code: str | None = None,
    ) -> None:
        if self._progress_callback is not None:
            try:
                self._progress_callback(PersonalH20ReadProgress(
                    stage=stage,
                    verifier_kind=verifier_kind,
                    identity_sha256=identity_sha256,
                    group_index=group_index,
                    group_total=group_total,
                    row_index=row_index,
                    row_total=row_total,
                    pass_name=pass_name,
                    stock_code=stock_code,
                ))
            except Exception as exc:
                self._progress_error = exc
                raise

    def raise_if_progress_failed(self) -> None:
        if self._progress_error is not None:
            raise PersonalH20ReadSessionError("personal_h20_progress_callback_failed") from self._progress_error

    def verify_source(self, binding: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._verify("source", binding)

    def verify_contract(self, binding: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._verify("contract", binding)

    def _verify(self, kind: VerifierKind, binding: Mapping[str, Any]) -> Mapping[str, Any]:
        self._ensure_open(allow_finishing=True)
        self.check_cancel()
        binding_json = _canonical_mapping(binding, field=f"personal_h20_{kind}_binding")
        group = self._groups[kind].get(binding_json)
        if group is not None:
            self.report(
                stage=f"{kind}_group_reused",
                verifier_kind=kind,
                identity_sha256=group.identity_sha256,
                group_index=self._group_index(kind, binding_json),
            )
            return _decode_mapping(group.result_json, field=f"personal_h20_{kind}_result")
        if self._finishing:
            raise PersonalH20ReadSessionError(
                f"personal_h20_{kind}_binding_changed_before_terminal_read"
            )

        index = len(self._groups[kind]) + 1
        identity_sha256 = hashlib.sha256(binding_json).hexdigest()
        self.report(
            stage=f"{kind}_group_started",
            verifier_kind=kind,
            identity_sha256=identity_sha256,
            group_index=index,
        )
        result = self._verifiers[kind](_decode_mapping(binding_json, field=f"personal_h20_{kind}_binding"))
        result_json = _canonical_mapping(result, field=f"personal_h20_{kind}_result")
        self.check_cancel()
        group = _VerifiedGroup(binding_json, result_json, identity_sha256)
        self._groups[kind][binding_json] = group
        self.report(
            stage=f"{kind}_group_verified",
            verifier_kind=kind,
            identity_sha256=identity_sha256,
            group_index=index,
        )
        return _decode_mapping(result_json, field=f"personal_h20_{kind}_result")

    def _group_index(self, kind: VerifierKind, binding_json: bytes) -> int:
        for index, stored in enumerate(self._groups[kind], start=1):
            if stored == binding_json:
                return index
        raise PersonalH20ReadSessionError("personal_h20_read_group_missing")

    def finish(self, *, finalizer: Callable[[], None] | None = None) -> None:
        if finalizer is not None and not callable(finalizer):
            raise PersonalH20ReadSessionError("personal_h20_read_finalizer_invalid")
        self._ensure_open()
        self.check_cancel()
        self._finishing = True
        try:
            for kind in ("source", "contract"):
                groups = tuple(self._groups[kind].values())
                total = len(groups)
                for index, group in enumerate(groups, start=1):
                    self.check_cancel()
                    self._emit(
                        stage=f"{kind}_group_recheck_started",
                        verifier_kind=kind,
                        identity_sha256=group.identity_sha256,
                        group_index=index,
                        group_total=total,
                    )
                    result = self._verifiers[kind](_decode_mapping(
                        group.binding_json, field=f"personal_h20_{kind}_binding"))
                    current_json = _canonical_mapping(result, field=f"personal_h20_{kind}_result")
                    self.check_cancel()
                    if current_json != group.result_json:
                        raise PersonalH20ReadSessionError(
                            f"personal_h20_{kind}_changed_during_read"
                        )
                    self._emit(
                        stage=f"{kind}_group_rechecked",
                        verifier_kind=kind,
                        identity_sha256=group.identity_sha256,
                        group_index=index,
                        group_total=total,
                    )
            self.check_cancel()
            if finalizer is not None:
                finalizer()
                self.check_cancel()
            self._finished = True
            self._finishing = False
            self._closed = True
        except BaseException:
            self._finishing = False
            self._closed = True
            raise

    def close(self) -> None:
        """丟棄操作快取；不執行成功終態重驗。"""
        self._closed = True
        self._groups["source"].clear()
        self._groups["contract"].clear()

    def _ensure_open(self, *, allow_finishing: bool = False) -> None:
        if self._closed or self._finished or (self._finishing and not allow_finishing):
            raise PersonalH20ReadSessionError("personal_h20_read_session_closed")
