"""ML release 的中立載入器註冊契約。

ML producer 只能依賴這個窄契約，不能反向 import ``app_module``。實際的
hash 驗證與 inference service 仍由 application release adapter 提供；adapter
在載入時註冊自己的 callable。若 application boundary 尚未啟動，這裡會
fail-closed，而不是猜測或略過 artifact readback。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, cast

from ml_module.allocation_contracts import PortfolioMLDatasetRow
from ml_module.allocation_release_contract import AllocationReleaseManifest


class ResearchShadowInferenceResult(Protocol):
    """Runner smoke 所需的唯讀 inference 結果介面。"""

    @property
    def formal_oos_allowed(self) -> bool: ...

    @property
    def production_action_allowed(self) -> bool: ...

    @property
    def production_blend_alpha_bp(self) -> int: ...

    def audit_payload(self) -> Mapping[str, Any]: ...


class VerifiedAllocationRelease(Protocol):
    """通過 application adapter 驗證的 allocation release 載入結果。"""

    @property
    def manifest(self) -> AllocationReleaseManifest: ...

    @property
    def release_id(self) -> str: ...

    def infer_research_shadow(
        self,
        *,
        rows: Sequence[PortfolioMLDatasetRow],
        universe_id: str,
        policy_id: str,
        policy_hash: str,
    ) -> ResearchShadowInferenceResult: ...


class AllocationReleaseLoader(Protocol):
    """application release adapter 必須實作的唯讀 loader 形狀。"""

    def __call__(
        self,
        release_root: str | Path,
        *,
        expected_release_identity_hash: str | None = None,
        manifest_name: str = "release_manifest.json",
    ) -> Any: ...


_registered_loader: AllocationReleaseLoader | None = None
_registered_output_type: type[VerifiedAllocationRelease] | None = None


def register_release_loader(
    loader: AllocationReleaseLoader,
    *,
    output_type: type[VerifiedAllocationRelease] | None = None,
) -> None:
    """註冊 application adapter；相同設定冪等，不能替換或降級驗證型別。"""

    if not callable(loader):
        raise TypeError("allocation release loader must be callable")
    if output_type is not None and not isinstance(output_type, type):
        raise TypeError("allocation release output_type must be a class")

    global _registered_loader, _registered_output_type
    if _registered_loader is not None:
        if _registered_loader is not loader:
            raise RuntimeError("allocation release loader is already registered")
        if (
            output_type is not None
            and _registered_output_type is not output_type
        ):
            raise RuntimeError(
                "allocation release loader output type is already registered"
            )
        return
    if (
        _registered_output_type is not None
        and output_type is not _registered_output_type
    ):
        raise RuntimeError(
            "allocation release loader output type cannot be replaced"
        )
    _registered_loader = loader
    _registered_output_type = output_type


def _registered_loader_or_raise() -> AllocationReleaseLoader:
    loader = _registered_loader
    if loader is None:
        raise RuntimeError(
            "allocation release loader is not registered; "
            "bootstrap the application release adapter before readback"
        )
    return loader


def ensure_verified_allocation_release_loader_registered() -> None:
    """在訓練或輸出建立前確認 application readback 已完成註冊。"""

    _registered_loader_or_raise()
    if _registered_output_type is None:
        raise RuntimeError(
            "verified allocation release output type is not registered; "
            "bootstrap the application release adapter before readback"
        )


def load_allocation_release(
    release_root: str | Path,
    *,
    expected_release_identity_hash: str | None = None,
    manifest_name: str = "release_manifest.json",
) -> Any:
    """以中立 contract 轉送至已註冊的 application release loader。

    保留原 general loader 的回傳與呼叫語意；未提供 verified output type 的
    舊註冊仍可使用此入口，但不能通過下方的 verified readback。
    """

    loader = _registered_loader_or_raise()
    return loader(
        release_root,
        expected_release_identity_hash=expected_release_identity_hash,
        manifest_name=manifest_name,
    )


def load_verified_allocation_release(
    release_root: str | Path,
    *,
    expected_release_identity_hash: str | None = None,
    manifest_name: str = "release_manifest.json",
) -> VerifiedAllocationRelease:
    """載入並精確驗證 adapter 註冊的 readback 類別。"""

    ensure_verified_allocation_release_loader_registered()
    loader = _registered_loader_or_raise()
    loaded = loader(
        release_root,
        expected_release_identity_hash=expected_release_identity_hash,
        manifest_name=manifest_name,
    )
    return require_verified_allocation_release(loaded)


def require_verified_allocation_release(
    loaded: object,
) -> VerifiedAllocationRelease:
    """除非物件精確符合已註冊的 adapter 類別，否則拒絕繼續。"""

    ensure_verified_allocation_release_loader_registered()
    output_type = _registered_output_type
    assert output_type is not None
    if type(loaded) is not output_type:
        raise TypeError(
            "allocation release loader returned an unregistered output type"
        )
    return cast(VerifiedAllocationRelease, loaded)


__all__ = [
    "AllocationReleaseLoader",
    "ResearchShadowInferenceResult",
    "VerifiedAllocationRelease",
    "ensure_verified_allocation_release_loader_registered",
    "load_allocation_release",
    "load_verified_allocation_release",
    "register_release_loader",
    "require_verified_allocation_release",
]
