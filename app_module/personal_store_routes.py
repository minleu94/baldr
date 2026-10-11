"""私人資料儲存路由的純型別契約。

本模組只選出既有 store caller 可使用的來源與目標 Path；不檢查檔案是否存在、
不建立目錄、不開啟資料庫，也不搬動或複製來源資料。PERSONAL 模式的來源就是
私人目標本身；檔案尚不存在時，caller 應將其視為空庫，不得退回 legacy 資料。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re

from app_module.personal_data_paths import PersonalDataPaths


class PersonalStoreRouteError(ValueError):
    """具名拒絕不完整或不相容的儲存路由。"""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        message = f"{code}: {detail}" if detail else code
        super().__init__(message)


class PersonalStoreDomain(str, Enum):
    TRADES = "trades"
    DECLARED_HOLDINGS = "declared_holdings"
    PAPER = "paper"
    PORTFOLIO_LEDGER = "portfolio_ledger"
    PORTFOLIO_RESEARCH = "portfolio_research"
    REVIEW = "review"
    EVIDENCE = "evidence"


class PersonalStoreMode(str, Enum):
    PERSONAL = "personal"
    LEGACY_COMPAT = "legacy_compat"
    LEGACY_READ_ONLY = "legacy_read_only"
    MARKET_READ_ONLY = "market_read_only"


class StoreSourceKind(str, Enum):
    PERSONAL = "personal"
    LEGACY = "legacy"
    MARKET = "market"


@dataclass(frozen=True)
class StoreIdentity:
    """Caller 已解析的 store/portfolio 身分，不能由 route 猜測。"""

    key: str


@dataclass(frozen=True)
class EvidenceSourceRef:
    """既有 Evidence 來源的精確引用；只保存引用，不複製市場資料庫。"""

    source_db: Path
    event_id: str


@dataclass(frozen=True)
class PersonalStoreRoute:
    """某一領域的唯一路由結果；不代表資料庫已存在或已完成啟用。"""

    domain: PersonalStoreDomain
    mode: PersonalStoreMode
    identity: StoreIdentity
    source_kind: StoreSourceKind
    read_source: Path
    write_target: Path | None
    evidence_refs: tuple[EvidenceSourceRef, ...] = ()
    paper_account_namespace: str | None = None

    def __post_init__(self) -> None:
        if self.paper_account_namespace is not None:
            if self.domain is not PersonalStoreDomain.PAPER:
                raise PersonalStoreRouteError("paper_account_namespace_domain_mismatch")
            if self.mode is not PersonalStoreMode.PERSONAL:
                raise PersonalStoreRouteError("paper_account_namespace_requires_personal_mode")
            _validate_paper_account_namespace(self.paper_account_namespace)
            if self.identity.key != self.paper_account_namespace:
                raise PersonalStoreRouteError("paper_account_namespace_identity_mismatch")
            if not self.read_source.is_absolute() or ".." in self.read_source.parts:
                raise PersonalStoreRouteError("paper_account_path_invalid", str(self.read_source))
            expected_suffix = (
                "paper_portfolio",
                "accounts",
                self.paper_account_namespace,
                "paper_trade_ledger.sqlite",
            )
            if tuple(self.read_source.parts[-4:]) != expected_suffix:
                raise PersonalStoreRouteError("paper_account_path_namespace_mismatch")
        if self.domain is PersonalStoreDomain.EVIDENCE:
            if self.mode is not PersonalStoreMode.MARKET_READ_ONLY:
                raise PersonalStoreRouteError("evidence_market_reader_required")
            if self.source_kind is not StoreSourceKind.MARKET or self.write_target is not None:
                raise PersonalStoreRouteError("evidence_route_must_be_read_only")
        elif self.mode is PersonalStoreMode.MARKET_READ_ONLY:
            raise PersonalStoreRouteError("market_read_only_evidence_only")

        if self.mode is PersonalStoreMode.LEGACY_READ_ONLY and self.write_target is not None:
            raise PersonalStoreRouteError("legacy_read_only_writer_forbidden")
        if self.mode in (PersonalStoreMode.PERSONAL, PersonalStoreMode.LEGACY_COMPAT):
            if self.write_target != self.read_source:
                raise PersonalStoreRouteError("selected_store_read_write_mismatch")


_PAPER_ACCOUNT_NAMESPACE = re.compile(r"^acct-[0-9a-f]{64}$")


def _validate_paper_account_namespace(value: str) -> str:
    if not isinstance(value, str) or not _PAPER_ACCOUNT_NAMESPACE.fullmatch(value):
        raise PersonalStoreRouteError("paper_account_namespace_invalid")
    return value


def _required_identity(
    domain: PersonalStoreDomain, identity: StoreIdentity | None
) -> StoreIdentity:
    if identity is None or not isinstance(identity.key, str) or not identity.key.strip():
        raise PersonalStoreRouteError(f"{domain.value}_identity_unknown")
    return identity


def _required_absolute(path: Path | None, code: str) -> Path:
    if path is None:
        raise PersonalStoreRouteError(code)
    if not path.is_absolute():
        raise PersonalStoreRouteError("absolute_path_required", str(path))
    if ".." in path.parts:
        raise PersonalStoreRouteError("path_traversal", str(path))
    return path


def _personal_root(personal_paths: PersonalDataPaths | None) -> Path:
    if personal_paths is None:
        raise PersonalStoreRouteError("personal_root_unconfigured")
    return _required_absolute(personal_paths.personal_root, "personal_root_unconfigured")


def _legacy_root(
    legacy_output_root: Path | None,
    personal_paths: PersonalDataPaths | None,
) -> Path:
    selected = legacy_output_root
    if selected is None and personal_paths is not None:
        selected = personal_paths.legacy_output_root
    return _required_absolute(selected, "legacy_output_root_unconfigured")


def _domain_relative_path(domain: PersonalStoreDomain) -> Path:
    if domain is PersonalStoreDomain.TRADES:
        return Path("portfolio") / "trades.jsonl"
    if domain is PersonalStoreDomain.DECLARED_HOLDINGS:
        return Path("portfolio") / "user_declared_holdings.jsonl"
    if domain is PersonalStoreDomain.PAPER:
        return Path("paper_portfolio") / "paper_trade_ledger.sqlite"
    if domain is PersonalStoreDomain.REVIEW:
        return Path("reviews") / "decision_quality.sqlite"
    if domain is PersonalStoreDomain.PORTFOLIO_RESEARCH:
        return Path("portfolio") / "research_scenarios.sqlite"
    raise PersonalStoreRouteError("domain_has_no_derived_path", domain.value)


def _route_path(
    *,
    domain: PersonalStoreDomain,
    mode: PersonalStoreMode,
    personal_paths: PersonalDataPaths | None,
    legacy_output_root: Path | None,
    market_db_path: Path | None,
    portfolio_ledger_path: Path | None,
    paper_account_namespace: str | None,
) -> tuple[Path, StoreSourceKind, Path | None]:
    if paper_account_namespace is not None:
        _validate_paper_account_namespace(paper_account_namespace)
        if domain is not PersonalStoreDomain.PAPER:
            raise PersonalStoreRouteError("paper_account_namespace_domain_mismatch")
        if mode is not PersonalStoreMode.PERSONAL:
            raise PersonalStoreRouteError("paper_account_namespace_requires_personal_mode")
        root = _personal_root(personal_paths)
        source = (
            root
            / "paper_portfolio"
            / "accounts"
            / paper_account_namespace
            / "paper_trade_ledger.sqlite"
        )
        return source, StoreSourceKind.PERSONAL, source

    if domain is PersonalStoreDomain.EVIDENCE:
        if mode is not PersonalStoreMode.MARKET_READ_ONLY:
            raise PersonalStoreRouteError("evidence_market_reader_required")
        source = _required_absolute(market_db_path, "market_db_path_unconfigured")
        return source, StoreSourceKind.MARKET, None

    if mode is PersonalStoreMode.MARKET_READ_ONLY:
        raise PersonalStoreRouteError("market_read_only_evidence_only")

    if domain is PersonalStoreDomain.PORTFOLIO_LEDGER:
        selected = _required_absolute(
            portfolio_ledger_path, "portfolio_ledger_path_unconfigured"
        )
        if mode is PersonalStoreMode.PERSONAL:
            root = _personal_root(personal_paths)
            if not selected.is_relative_to(root) or selected == root:
                raise PersonalStoreRouteError("portfolio_ledger_path_outside_personal")
            source_kind = StoreSourceKind.PERSONAL
        else:
            source_kind = StoreSourceKind.LEGACY
        target = None if mode is PersonalStoreMode.LEGACY_READ_ONLY else selected
        return selected, source_kind, target

    if domain is PersonalStoreDomain.REVIEW and mode is not PersonalStoreMode.PERSONAL:
        source = _required_absolute(market_db_path, "market_db_path_unconfigured")
        target = None if mode is PersonalStoreMode.LEGACY_READ_ONLY else source
        return source, StoreSourceKind.LEGACY, target

    if mode is PersonalStoreMode.PERSONAL:
        source = _personal_root(personal_paths) / _domain_relative_path(domain)
        return source, StoreSourceKind.PERSONAL, source

    root = _legacy_root(legacy_output_root, personal_paths)
    source = root / _domain_relative_path(domain)
    target = None if mode is PersonalStoreMode.LEGACY_READ_ONLY else source
    return source, StoreSourceKind.LEGACY, target


def select_personal_store_route(
    *,
    domain: PersonalStoreDomain,
    mode: PersonalStoreMode,
    identity: StoreIdentity | None,
    personal_paths: PersonalDataPaths | None = None,
    legacy_output_root: Path | None = None,
    market_db_path: Path | None = None,
    portfolio_ledger_path: Path | None = None,
    paper_account_namespace: str | None = None,
    evidence_refs: tuple[EvidenceSourceRef, ...] = (),
) -> PersonalStoreRoute:
    """回傳一項 store 的 typed Path 契約，不碰檔案系統或資料庫。

    `identity` 必須由 caller 先解析。Portfolio ledger 沒有 repository 既定檔名，
    因此必須提供其精確 `portfolio_ledger_path`；不完整時以具名錯誤拒絕。
    Evidence 固定使用明確的市場 DB read path，且沒有 writer。Review 的 market
    Evidence 關聯只保留在 `evidence_refs`，不影響私人 Review 的 DB 路由。
    """
    if not isinstance(domain, PersonalStoreDomain):
        raise PersonalStoreRouteError("store_domain_invalid", str(domain))
    if not isinstance(mode, PersonalStoreMode):
        raise PersonalStoreRouteError("store_mode_invalid", str(mode))
    selected_identity = _required_identity(domain, identity)
    if domain is not PersonalStoreDomain.REVIEW and evidence_refs:
        raise PersonalStoreRouteError("evidence_refs_review_only")

    read_source, source_kind, write_target = _route_path(
        domain=domain,
        mode=mode,
        personal_paths=personal_paths,
        legacy_output_root=legacy_output_root,
        market_db_path=market_db_path,
        portfolio_ledger_path=portfolio_ledger_path,
        paper_account_namespace=paper_account_namespace,
    )
    return PersonalStoreRoute(
        domain=domain,
        mode=mode,
        identity=selected_identity,
        source_kind=source_kind,
        read_source=read_source,
        write_target=write_target,
        evidence_refs=evidence_refs,
        paper_account_namespace=paper_account_namespace,
    )
