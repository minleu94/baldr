"""策略版本至私人 Paper account 的唯讀 binding map 候選。

本模組只讀 immutable binding 與其明示版本 artifacts，不建立帳戶、目錄、DB
或 ledger。Binding 可證明 account map 指向哪個版本；它本身不證明任何 snapshot、
fill 或 benchmark row 的來源歸屬，因此此候選永遠不授予績效 qualification。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from enum import Enum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

from app_module.paper_portfolio_policy import PaperPortfolioPolicyConfig
from app_module.personal_data_paths import (
    PersonalDataPaths,
    PersonalDataPathError,
    _absolute,
    _reject_links,
    to_internal_io_path,
)
from app_module.personal_store_routes import (
    PersonalStoreDomain,
    PersonalStoreMode,
    PersonalStoreRoute,
    PersonalStoreRouteError,
    StoreIdentity,
    select_personal_store_route,
)
from app_module.personal_store_selection import assert_personal_store_path


BINDING_SCHEMA_VERSION = "strategy-paper-account-binding.v1"
_NAMESPACE_PATTERN = re.compile(r"^acct-[0-9a-f]{64}$")
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_ARTIFACT_COMPONENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_BINDING_FIELDS = (
    "schema_version",
    "strategy_version_id",
    "strategy_id",
    "strategy_version",
    "strategy_artifact_sha256",
    "params_sha256",
    "config_sha256",
    "source_run_id",
    "policy_id",
    "policy_version",
    "policy_sha256",
    "cost_model_id",
    "cost_model_version",
    "cost_model_sha256",
    "benchmark_id",
    "benchmark_version",
    "benchmark_sha256",
    "start_date",
    "initial_capital",
    "max_positions",
)
_DERIVED_FIELDS = frozenset(
    {"account_namespace", "portfolio_id", "binding_sha256"}
)
_MAX_STRATEGY_ARTIFACT_BYTES = 2 * 1024 * 1024
_MAX_CONTRACT_ARTIFACT_BYTES = 512 * 1024
_MAX_BINDING_MANIFEST_BYTES = 65_536


class _ArtifactTooLarge(ValueError):
    pass


class _ArtifactChanged(ValueError):
    pass


class _HashMismatch(ValueError):
    pass


def _file_signature(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_nlink,
    )


def _read_bounded_regular_file(
    path: Path, *, max_bytes: int, expected_sha256: str | None = None
) -> bytes:
    """Read one bounded byte snapshot and reject replacement or mutation during read."""

    _reject_links(path)
    _absolute(path)
    io_path = to_internal_io_path(path)
    before = os.stat(io_path, follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise _RejectedBinding("bound_artifact_alias_or_type")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(io_path, flags)
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or _file_signature(opened) != _file_signature(before)
        ):
            raise _ArtifactChanged("bound_artifact_changed_during_read")
        chunks: list[bytes] = []
        total = 0
        while total <= max_bytes:
            chunk = os.read(descriptor, min(65_536, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        if total > max_bytes:
            raise _ArtifactTooLarge("bound_artifact_too_large")
        after_fd = os.fstat(descriptor)
    finally:
        os.close(descriptor)

    after_path = os.stat(io_path, follow_symlinks=False)
    if (
        _file_signature(opened) != _file_signature(after_fd)
        or _file_signature(after_fd) != _file_signature(after_path)
    ):
        raise _ArtifactChanged("bound_artifact_changed_during_read")
    raw = b"".join(chunks)
    if expected_sha256 is not None:
        if file_sha256(raw) != expected_sha256:
            raise _HashMismatch("bound_artifact_sha256_mismatch")
        _reject_links(path)
        after_hash = os.stat(io_path, follow_symlinks=False)
        if _file_signature(after_fd) != _file_signature(after_hash):
            raise _ArtifactChanged("bound_artifact_changed_during_read")
    return raw


class AccountBindingStatus(str, Enum):
    READY = "ready"
    UNKNOWN = "unknown"
    REJECTED = "rejected"


class _UnknownBinding(ValueError):
    pass


class _RejectedBinding(ValueError):
    pass


def canonical_sha256(value: Any) -> str:
    """以穩定 JSON 身分 hash；不進行金融數值運算。"""

    try:
        canonical = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("canonical_json_invalid") from exc
    return "sha256:" + sha256(canonical.encode("utf-8")).hexdigest()


def file_sha256(raw: bytes) -> str:
    return "sha256:" + sha256(raw).hexdigest()


def _required_text(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise _UnknownBinding(f"binding_field_missing:{field_name}")
    return value


def _require_hash(payload: dict[str, Any], field_name: str) -> str:
    value = _required_text(payload, field_name)
    if not _HASH_PATTERN.fullmatch(value):
        raise _RejectedBinding(f"binding_hash_format_invalid:{field_name}")
    return value


def _require_component(value: str, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not _ARTIFACT_COMPONENT_PATTERN.fullmatch(value)
        or value in {".", ".."}
    ):
        raise _RejectedBinding(f"artifact_identity_invalid:{field_name}")
    return value


@dataclass(frozen=True)
class StrategyPaperAccountBinding:
    """已 hash 綁定策略、policy、cost 與 benchmark artifact 的唯讀契約。"""

    strategy_version_id: str
    strategy_id: str
    strategy_version: str
    strategy_artifact_sha256: str
    params_sha256: str
    config_sha256: str
    source_run_id: str
    policy_id: str
    policy_version: str
    policy_sha256: str
    cost_model_id: str
    cost_model_version: str
    cost_model_sha256: str
    benchmark_id: str
    benchmark_version: str
    benchmark_sha256: str
    start_date: str
    initial_capital: str
    max_positions: int
    account_namespace: str
    portfolio_id: str
    binding_sha256: str

    @classmethod
    def from_manifest(cls, value: object) -> "StrategyPaperAccountBinding":
        if not isinstance(value, dict):
            raise _RejectedBinding("binding_manifest_must_be_object")
        expected = set(_BINDING_FIELDS) | _DERIVED_FIELDS
        missing = sorted(expected - set(value))
        if missing:
            raise _UnknownBinding("binding_fields_missing:" + ",".join(missing))
        extra = sorted(set(value) - expected)
        if extra:
            raise _RejectedBinding("binding_fields_unknown:" + ",".join(extra))

        if value.get("schema_version") != BINDING_SCHEMA_VERSION:
            raise _RejectedBinding("binding_schema_version_mismatch")
        text_fields = (
            "strategy_version_id",
            "strategy_id",
            "strategy_version",
            "source_run_id",
            "policy_id",
            "policy_version",
            "cost_model_id",
            "cost_model_version",
            "benchmark_id",
            "benchmark_version",
            "start_date",
            "initial_capital",
        )
        for field_name in text_fields:
            _required_text(value, field_name)
        hash_fields = (
            "strategy_artifact_sha256",
            "params_sha256",
            "config_sha256",
            "policy_sha256",
            "cost_model_sha256",
            "benchmark_sha256",
            "binding_sha256",
        )
        for field_name in hash_fields:
            _require_hash(value, field_name)
        for field_name in (
            "strategy_version_id",
            "policy_id",
            "policy_version",
            "cost_model_id",
            "cost_model_version",
            "benchmark_id",
            "benchmark_version",
        ):
            _require_component(str(value[field_name]), field_name)

        if value["initial_capital"] != "500000":
            raise _RejectedBinding("strategy_paper_initial_capital_must_remain_500000")
        if type(value["max_positions"]) is not int or value["max_positions"] != 8:
            raise _RejectedBinding("strategy_paper_max_positions_must_remain_8")
        try:
            parsed_date = date.fromisoformat(value["start_date"])
        except ValueError as exc:
            raise _RejectedBinding("binding_start_date_invalid") from exc
        if parsed_date.isoformat() != value["start_date"]:
            raise _RejectedBinding("binding_start_date_not_canonical")

        payload = {field_name: value[field_name] for field_name in _BINDING_FIELDS}
        expected_hash = canonical_sha256(payload)
        expected_namespace = "acct-" + expected_hash.removeprefix("sha256:")
        if value["binding_sha256"] != expected_hash:
            raise _RejectedBinding("binding_sha256_mismatch")
        if value["account_namespace"] != expected_namespace:
            raise _RejectedBinding("account_namespace_binding_mismatch")
        if value["portfolio_id"] != expected_namespace:
            raise _RejectedBinding("portfolio_id_binding_mismatch")

        return cls(
            **{
                field_name: value[field_name]
                for field_name in _BINDING_FIELDS
                if field_name != "schema_version"
            },
            account_namespace=expected_namespace,
            portfolio_id=expected_namespace,
            binding_sha256=expected_hash,
        )

    @classmethod
    def create_manifest_payload(cls, **fields: Any) -> dict[str, Any]:
        """純函式產生候選 manifest；不寫檔或建立帳戶。"""

        payload = {"schema_version": BINDING_SCHEMA_VERSION, **fields}
        if set(payload) != set(_BINDING_FIELDS):
            missing = sorted(set(_BINDING_FIELDS) - set(payload))
            extra = sorted(set(payload) - set(_BINDING_FIELDS))
            raise ValueError(
                "binding_payload_fields_invalid:"
                + f"missing={','.join(missing)};extra={','.join(extra)}"
            )
        digest = canonical_sha256(payload)
        namespace = "acct-" + digest.removeprefix("sha256:")
        return {
            **payload,
            "account_namespace": namespace,
            "portfolio_id": namespace,
            "binding_sha256": digest,
        }


@dataclass(frozen=True)
class StrategyPaperAccountSelection:
    status: AccountBindingStatus
    binding: StrategyPaperAccountBinding | None = None
    route: PersonalStoreRoute | None = None
    blockers: tuple[str, ...] = ()
    performance_eligible: bool = False


@dataclass(frozen=True)
class StrategyPaperAccountMap:
    status: AccountBindingStatus
    entries: tuple[StrategyPaperAccountSelection, ...] = ()
    blockers: tuple[str, ...] = ()


class StrategyPaperAccountService:
    """只讀解析明示 account manifest 並驗證其 exact artifacts。"""

    def __init__(
        self,
        *,
        personal_paths: PersonalDataPaths,
        strategy_versions_root: str | Path,
        contract_artifacts_root: str | Path,
    ) -> None:
        self.personal_paths = personal_paths
        self.strategy_versions_root = Path(strategy_versions_root)
        self.contract_artifacts_root = Path(contract_artifacts_root)
        if not self.strategy_versions_root.is_absolute() or not self.contract_artifacts_root.is_absolute():
            raise ValueError("account_artifact_roots_must_be_absolute")

    @property
    def accounts_root(self) -> Path:
        return self.personal_paths.personal_root / "paper_portfolio" / "accounts"

    def select_account(self, account_namespace: str) -> StrategyPaperAccountSelection:
        if not isinstance(account_namespace, str) or not _NAMESPACE_PATTERN.fullmatch(account_namespace):
            return self._rejected("paper_account_namespace_invalid")
        account_root = self.accounts_root / account_namespace
        manifest_path = account_root / "account_binding.json"
        path_status = self._check_path_chain(
            manifest_path,
            root=self.personal_paths.personal_root,
            final_is_directory=False,
        )
        if path_status is not None:
            status, reason = path_status
            return (
                self._unknown(reason)
                if status is AccountBindingStatus.UNKNOWN
                else self._rejected(reason)
            )
        try:
            assert_personal_store_path(self.personal_paths, manifest_path)
            raw = _read_bounded_regular_file(
                manifest_path, max_bytes=_MAX_BINDING_MANIFEST_BYTES
            )
            manifest = json.loads(raw.decode("utf-8"))
            binding = StrategyPaperAccountBinding.from_manifest(manifest)
        except FileNotFoundError:
            return self._unknown("strategy_account_binding_missing")
        except PersonalDataPathError:
            return self._rejected("strategy_account_binding_path_invalid")
        except OSError:
            return self._unknown("strategy_account_binding_unavailable")
        except _ArtifactTooLarge:
            return self._rejected("strategy_account_binding_too_large")
        except _ArtifactChanged:
            return self._unknown("strategy_account_binding_changed_during_read")
        except _RejectedBinding as exc:
            return self._rejected(str(exc))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._rejected("strategy_account_binding_json_invalid")
        except _UnknownBinding as exc:
            return self._unknown(str(exc))
        except (_RejectedBinding, TypeError, ValueError) as exc:
            return self._rejected(str(exc))

        if binding.account_namespace != account_namespace:
            return self._rejected("strategy_account_namespace_mismatch")
        artifact_status = self._verify_bound_artifacts(binding)
        if artifact_status is not None:
            status, reason = artifact_status
            return (
                self._unknown(reason)
                if status is AccountBindingStatus.UNKNOWN
                else self._rejected(reason)
            )
        try:
            route = select_personal_store_route(
                domain=PersonalStoreDomain.PAPER,
                mode=PersonalStoreMode.PERSONAL,
                identity=StoreIdentity(binding.portfolio_id),
                personal_paths=self.personal_paths,
                paper_account_namespace=binding.account_namespace,
            )
        except (PersonalDataPathError, PersonalStoreRouteError, ValueError):
            return self._rejected("strategy_account_route_invalid")
        return StrategyPaperAccountSelection(
            status=AccountBindingStatus.READY,
            binding=binding,
            route=route,
            blockers=("strategy_account_row_provenance_unverified",),
            performance_eligible=False,
        )

    def list_accounts(self) -> StrategyPaperAccountMap:
        path_status = self._check_path_chain(
            self.accounts_root,
            root=self.personal_paths.personal_root,
            final_is_directory=True,
        )
        if path_status is not None:
            status, reason = path_status
            return StrategyPaperAccountMap(
                status=status,
                blockers=(reason,),
            )
        entries: list[StrategyPaperAccountSelection] = []
        try:
            children = sorted(self.accounts_root.iterdir(), key=lambda item: item.name)
        except OSError:
            return StrategyPaperAccountMap(
                status=AccountBindingStatus.UNKNOWN,
                blockers=("strategy_account_map_unavailable",),
            )
        for child in children:
            if _NAMESPACE_PATTERN.fullmatch(child.name):
                # Let the full-chain guard report symlink/junction/reparse entries.
                entries.append(self.select_account(child.name))
            elif child.is_symlink() or not child.is_dir():
                continue
        if any(item.status is AccountBindingStatus.READY for item in entries):
            status = AccountBindingStatus.READY
        elif any(item.status is AccountBindingStatus.UNKNOWN for item in entries):
            status = AccountBindingStatus.UNKNOWN
        elif not entries:
            status = AccountBindingStatus.UNKNOWN
            return StrategyPaperAccountMap(
                status=status,
                entries=(),
                blockers=("strategy_account_map_empty",),
            )
        else:
            status = AccountBindingStatus.REJECTED
        return StrategyPaperAccountMap(status=status, entries=tuple(entries))

    def select_exact_version(
        self,
        *,
        strategy_id: str,
        strategy_version_id: str,
        account_namespace: str | None = None,
    ) -> StrategyPaperAccountSelection:
        """只接受 exact version；沒有 binding 或存在多個 account 時不猜 latest。"""

        if account_namespace is not None:
            result = self.select_account(account_namespace)
            binding = result.binding
            if binding is None:
                return result
            if (binding.strategy_id, binding.strategy_version_id) != (
                strategy_id,
                strategy_version_id,
            ):
                return self._rejected("strategy_account_exact_version_mismatch")
            return result
        mapped = self.list_accounts()
        matches = tuple(
            item
            for item in mapped.entries
            if item.binding is not None
            and (item.binding.strategy_id, item.binding.strategy_version_id)
            == (strategy_id, strategy_version_id)
        )
        if len(matches) == 1:
            return matches[0]
        if not matches:
            if mapped.blockers:
                return StrategyPaperAccountSelection(
                    status=mapped.status,
                    blockers=mapped.blockers,
                    performance_eligible=False,
                )
            unresolved = tuple(item for item in mapped.entries if item.binding is None)
            if unresolved:
                blockers = tuple(
                    dict.fromkeys(
                        blocker
                        for item in unresolved
                        for blocker in item.blockers
                    )
                )
                status = (
                    AccountBindingStatus.UNKNOWN
                    if any(item.status is AccountBindingStatus.UNKNOWN for item in unresolved)
                    else AccountBindingStatus.REJECTED
                )
                return StrategyPaperAccountSelection(
                    status=status,
                    blockers=blockers or ("strategy_account_candidate_unresolved",),
                    performance_eligible=False,
                )
            if not mapped.entries:
                return self._unknown("strategy_account_map_empty")
            return self._unknown("strategy_account_binding_missing")
        return self._unknown("strategy_account_binding_ambiguous")

    def _verify_bound_artifacts(
        self, binding: StrategyPaperAccountBinding
    ) -> tuple[AccountBindingStatus, str] | None:
        strategy_path = self.strategy_versions_root / f"{binding.strategy_version_id}.json"
        raw, status = self._read_verified_artifact(
            strategy_path,
            binding.strategy_artifact_sha256,
            root=self.strategy_versions_root,
            max_bytes=_MAX_STRATEGY_ARTIFACT_BYTES,
        )
        if status is not None:
            return status
        try:
            assert raw is not None
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return AccountBindingStatus.UNKNOWN, "strategy_version_artifact_unavailable"
        if not isinstance(payload, dict):
            return AccountBindingStatus.REJECTED, "strategy_version_artifact_invalid"
        expected_identity = {
            "version_id": binding.strategy_version_id,
            "strategy_id": binding.strategy_id,
            "strategy_version": binding.strategy_version,
            "source_run_id": binding.source_run_id,
        }
        if any(payload.get(key) != value for key, value in expected_identity.items()):
            return AccountBindingStatus.REJECTED, "strategy_version_artifact_identity_mismatch"
        if "params" not in payload:
            return AccountBindingStatus.UNKNOWN, "strategy_params_missing"
        if "config" not in payload:
            return AccountBindingStatus.UNKNOWN, "strategy_config_missing"
        if not isinstance(payload["params"], dict):
            return AccountBindingStatus.REJECTED, "strategy_params_must_be_object"
        if not isinstance(payload["config"], dict):
            return AccountBindingStatus.REJECTED, "strategy_config_must_be_object"
        try:
            params_hash = canonical_sha256(payload["params"])
            config_hash = canonical_sha256(payload["config"])
        except (TypeError, ValueError):
            return AccountBindingStatus.REJECTED, "strategy_params_config_not_canonical"
        if params_hash != binding.params_sha256:
            return AccountBindingStatus.REJECTED, "strategy_params_sha256_mismatch"
        if config_hash != binding.config_sha256:
            return AccountBindingStatus.REJECTED, "strategy_config_sha256_mismatch"

        artifacts = (
            ("paper_policies", binding.policy_id, binding.policy_version, binding.policy_sha256),
            ("cost_models", binding.cost_model_id, binding.cost_model_version, binding.cost_model_sha256),
            ("benchmarks", binding.benchmark_id, binding.benchmark_version, binding.benchmark_sha256),
        )
        for kind, artifact_id, version, expected_hash in artifacts:
            artifact_path = (
                self.contract_artifacts_root
                / kind
                / f"{artifact_id}__{version}.json"
            )
            raw, status = self._read_verified_artifact(
                artifact_path,
                expected_hash,
                root=self.contract_artifacts_root,
                max_bytes=_MAX_CONTRACT_ARTIFACT_BYTES,
            )
            if status is not None:
                return status
            try:
                assert raw is not None
                artifact = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return AccountBindingStatus.UNKNOWN, f"{kind}_artifact_unavailable"
            if not isinstance(artifact, dict) or (
                artifact.get("artifact_type") != kind
                or artifact.get("artifact_id") != artifact_id
                or artifact.get("version") != version
            ):
                return AccountBindingStatus.REJECTED, f"{kind}_artifact_identity_mismatch"
            if kind == "paper_policies":
                policy_snapshot = artifact.get("policy")
                policy_config = PaperPortfolioPolicyConfig()
                expected_policy = asdict(policy_config)
                expected_policy["initial_capital"] = str(policy_config.initial_capital)
                if policy_snapshot != expected_policy:
                    return (
                        AccountBindingStatus.REJECTED,
                        "paper_policy_snapshot_mismatch",
                    )
            elif kind == "cost_models":
                cost_snapshot = artifact.get("cost_model")
                expected_cost = {
                    "commission_bp_per_side": 15,
                    "slippage_bp_per_side": 10,
                    "sell_tax_bp": 30,
                }
                if cost_snapshot != expected_cost:
                    return (
                        AccountBindingStatus.REJECTED,
                        "paper_cost_model_snapshot_mismatch",
                    )
        return None

    @staticmethod
    def _read_verified_artifact(
        path: Path,
        expected_hash: str,
        *,
        root: Path,
        max_bytes: int,
    ) -> tuple[bytes | None, tuple[AccountBindingStatus, str] | None]:
        path_status = StrategyPaperAccountService._check_path_chain(
            path,
            root=root,
            final_is_directory=False,
        )
        if path_status is not None:
            status, reason = path_status
            mapped = (
                AccountBindingStatus.UNKNOWN
                if status is AccountBindingStatus.UNKNOWN
                else AccountBindingStatus.REJECTED
            )
            return None, (
                mapped,
                "bound_artifact_missing" if status is AccountBindingStatus.UNKNOWN else reason,
            )
        try:
            raw = _read_bounded_regular_file(
                path, max_bytes=max_bytes, expected_sha256=expected_hash
            )
        except FileNotFoundError:
            return None, (AccountBindingStatus.UNKNOWN, "bound_artifact_missing")
        except _ArtifactTooLarge:
            return None, (AccountBindingStatus.REJECTED, "bound_artifact_too_large")
        except _HashMismatch:
            return None, (AccountBindingStatus.REJECTED, "bound_artifact_sha256_mismatch")
        except _ArtifactChanged:
            return None, (AccountBindingStatus.UNKNOWN, "bound_artifact_changed_during_read")
        except _RejectedBinding as exc:
            return None, (AccountBindingStatus.REJECTED, str(exc))
        except PersonalDataPathError:
            return None, (AccountBindingStatus.REJECTED, "bound_artifact_path_invalid")
        except OSError:
            return None, (AccountBindingStatus.UNKNOWN, "bound_artifact_unavailable")
        return raw, None

    @staticmethod
    def _check_path_chain(
        path: Path,
        *,
        root: Path,
        final_is_directory: bool,
    ) -> tuple[AccountBindingStatus, str] | None:
        if not path.is_absolute() or not root.is_absolute() or ".." in path.parts:
            return AccountBindingStatus.REJECTED, "strategy_account_path_invalid"
        try:
            path.relative_to(root)
            _reject_links(root)
            _reject_links(path)
            safe_root = _absolute(root)
            safe_path = _absolute(path)
            relative = safe_path.relative_to(safe_root)
        except PersonalDataPathError as exc:
            return AccountBindingStatus.REJECTED, f"strategy_account_path_invalid:{exc.code}"
        except ValueError:
            return AccountBindingStatus.REJECTED, "strategy_account_path_outside_root"
        current = safe_root
        try:
            root_info = os.stat(to_internal_io_path(current), follow_symlinks=False)
        except FileNotFoundError:
            return (
                AccountBindingStatus.UNKNOWN,
                "strategy_account_map_missing"
                if final_is_directory
                else "strategy_account_binding_missing",
            )
        except OSError:
            return AccountBindingStatus.UNKNOWN, "strategy_account_map_unavailable"
        if not stat.S_ISDIR(root_info.st_mode):
            return AccountBindingStatus.REJECTED, "strategy_account_root_alias_or_type"
        for index, part in enumerate(relative.parts):
            current = current / part
            is_final = index == len(relative.parts) - 1
            try:
                info = os.stat(to_internal_io_path(current), follow_symlinks=False)
            except FileNotFoundError:
                return AccountBindingStatus.UNKNOWN, "strategy_account_binding_missing"
            except OSError:
                return AccountBindingStatus.UNKNOWN, "strategy_account_path_unavailable"
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                return AccountBindingStatus.REJECTED, "strategy_account_path_link_or_reparse"
            if is_final and final_is_directory:
                if not stat.S_ISDIR(info.st_mode):
                    return AccountBindingStatus.REJECTED, "strategy_account_directory_invalid"
            elif is_final:
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    return AccountBindingStatus.REJECTED, "strategy_account_binding_file_alias_or_type"
            elif not stat.S_ISDIR(info.st_mode):
                return AccountBindingStatus.REJECTED, "strategy_account_parent_not_directory"
        return None

    @staticmethod
    def _unknown(reason: str) -> StrategyPaperAccountSelection:
        return StrategyPaperAccountSelection(
            status=AccountBindingStatus.UNKNOWN,
            blockers=(reason,),
            performance_eligible=False,
        )

    @staticmethod
    def _rejected(reason: str) -> StrategyPaperAccountSelection:
        return StrategyPaperAccountSelection(
            status=AccountBindingStatus.REJECTED,
            blockers=(reason,),
            performance_eligible=False,
        )
