from __future__ import annotations

from pathlib import Path

import pytest

from app_module.personal_data_paths import PersonalDataPaths
from app_module.personal_store_routes import (
    EvidenceSourceRef,
    PersonalStoreDomain,
    PersonalStoreMode,
    PersonalStoreRouteError,
    StoreIdentity,
    StoreSourceKind,
    select_personal_store_route,
)


@pytest.fixture
def paths(tmp_path: Path) -> PersonalDataPaths:
    return PersonalDataPaths(
        market_root=tmp_path / "market",
        legacy_output_root=tmp_path / "output",
        personal_root=tmp_path / "market" / "personal",
    )


@pytest.mark.parametrize(
    ("domain", "relative"),
    [
        (PersonalStoreDomain.TRADES, Path("portfolio") / "trades.jsonl"),
        (PersonalStoreDomain.PORTFOLIO_RESEARCH, Path("portfolio") / "research_scenarios.sqlite"),
        (
            PersonalStoreDomain.DECLARED_HOLDINGS,
            Path("portfolio") / "user_declared_holdings.jsonl",
        ),
        (
            PersonalStoreDomain.PAPER,
            Path("paper_portfolio") / "paper_trade_ledger.sqlite",
        ),
        (
            PersonalStoreDomain.REVIEW,
            Path("reviews") / "decision_quality.sqlite",
        ),
    ],
)
def test_personal_routes_read_from_their_own_empty_target_without_fallback(
    paths: PersonalDataPaths,
    tmp_path: Path,
    domain: PersonalStoreDomain,
    relative: Path,
) -> None:
    legacy_file = paths.legacy_output_root / relative
    legacy_file.parent.mkdir(parents=True)
    legacy_file.write_text("legacy fixture\n", encoding="utf-8")

    route = select_personal_store_route(
        domain=domain,
        mode=PersonalStoreMode.PERSONAL,
        identity=StoreIdentity("account-1"),
        personal_paths=paths,
    )

    expected = paths.personal_root / relative
    assert route.read_source == expected
    assert route.write_target == expected
    assert route.read_source != legacy_file
    assert not expected.exists()
    assert not paths.personal_root.exists()
    assert not (tmp_path / "unused").exists()


@pytest.mark.parametrize(
    ("domain", "relative"),
    [
        (PersonalStoreDomain.TRADES, Path("portfolio") / "trades.jsonl"),
        (
            PersonalStoreDomain.DECLARED_HOLDINGS,
            Path("portfolio") / "user_declared_holdings.jsonl",
        ),
        (
            PersonalStoreDomain.PAPER,
            Path("paper_portfolio") / "paper_trade_ledger.sqlite",
        ),
    ],
)
def test_legacy_compat_and_read_only_routes_are_explicit(
    paths: PersonalDataPaths,
    domain: PersonalStoreDomain,
    relative: Path,
) -> None:
    compat = select_personal_store_route(
        domain=domain,
        mode=PersonalStoreMode.LEGACY_COMPAT,
        identity=StoreIdentity("account-1"),
        legacy_output_root=paths.legacy_output_root,
    )
    read_only = select_personal_store_route(
        domain=domain,
        mode=PersonalStoreMode.LEGACY_READ_ONLY,
        identity=StoreIdentity("account-1"),
        legacy_output_root=paths.legacy_output_root,
    )

    expected = paths.legacy_output_root / relative
    assert compat.read_source == expected
    assert compat.write_target == expected
    assert compat.source_kind is StoreSourceKind.LEGACY
    assert read_only.read_source == expected
    assert read_only.write_target is None
    assert read_only.source_kind is StoreSourceKind.LEGACY


def test_review_private_writer_and_market_evidence_refs_remain_separate(
    paths: PersonalDataPaths, tmp_path: Path
) -> None:
    market_db = paths.market_root / "sqlite" / "twstock.db"
    refs = (
        EvidenceSourceRef(market_db, "evidence-event-17"),
        EvidenceSourceRef(market_db, "evidence-event-22"),
    )

    route = select_personal_store_route(
        domain=PersonalStoreDomain.REVIEW,
        mode=PersonalStoreMode.PERSONAL,
        identity=StoreIdentity("decision-review"),
        personal_paths=paths,
        market_db_path=market_db,
        evidence_refs=refs,
    )

    private_db = paths.personal_root / "reviews" / "decision_quality.sqlite"
    assert route.read_source == private_db
    assert route.write_target == private_db
    assert route.read_source != market_db
    assert route.evidence_refs is refs
    assert tuple((item.source_db, item.event_id) for item in route.evidence_refs) == (
        (market_db, "evidence-event-17"),
        (market_db, "evidence-event-22"),
    )
    assert not tmp_path.joinpath("market", "personal").exists()


def test_evidence_is_market_read_only_and_has_no_writer(
    paths: PersonalDataPaths,
) -> None:
    market_db = paths.market_root / "sqlite" / "twstock.db"
    route = select_personal_store_route(
        domain=PersonalStoreDomain.EVIDENCE,
        mode=PersonalStoreMode.MARKET_READ_ONLY,
        identity=StoreIdentity("market-evidence"),
        market_db_path=market_db,
    )

    assert route.read_source == market_db
    assert route.write_target is None
    assert route.source_kind is StoreSourceKind.MARKET


def test_evidence_rejects_private_or_legacy_modes(paths: PersonalDataPaths) -> None:
    for mode in (
        PersonalStoreMode.PERSONAL,
        PersonalStoreMode.LEGACY_COMPAT,
        PersonalStoreMode.LEGACY_READ_ONLY,
    ):
        with pytest.raises(PersonalStoreRouteError) as exc_info:
            select_personal_store_route(
                domain=PersonalStoreDomain.EVIDENCE,
                mode=mode,
                identity=StoreIdentity("market-evidence"),
                personal_paths=paths,
                legacy_output_root=paths.legacy_output_root,
                market_db_path=paths.market_root / "sqlite" / "twstock.db",
            )
        assert exc_info.value.code == "evidence_market_reader_required"


@pytest.mark.parametrize("domain", list(PersonalStoreDomain))
def test_unknown_identity_is_named_for_each_domain(
    paths: PersonalDataPaths, domain: PersonalStoreDomain
) -> None:
    kwargs: dict[str, object] = {
        "domain": domain,
        "mode": (
            PersonalStoreMode.MARKET_READ_ONLY
            if domain is PersonalStoreDomain.EVIDENCE
            else PersonalStoreMode.PERSONAL
        ),
        "identity": None,
        "personal_paths": paths,
        "market_db_path": paths.market_root / "sqlite" / "twstock.db",
    }
    if domain is PersonalStoreDomain.PORTFOLIO_LEDGER:
        kwargs["portfolio_ledger_path"] = paths.ledger_root / "caller-selected.sqlite"

    with pytest.raises(PersonalStoreRouteError) as exc_info:
        select_personal_store_route(**kwargs)  # type: ignore[arg-type]
    assert exc_info.value.code == f"{domain.value}_identity_unknown"


def test_portfolio_ledger_requires_explicit_path_and_never_aliases_paper(
    paths: PersonalDataPaths,
) -> None:
    identity = StoreIdentity("portfolio-7")
    with pytest.raises(PersonalStoreRouteError) as exc_info:
        select_personal_store_route(
            domain=PersonalStoreDomain.PORTFOLIO_LEDGER,
            mode=PersonalStoreMode.PERSONAL,
            identity=identity,
            personal_paths=paths,
        )
    assert exc_info.value.code == "portfolio_ledger_path_unconfigured"

    ledger_path = paths.ledger_root / "caller-selected.sqlite"
    ledger = select_personal_store_route(
        domain=PersonalStoreDomain.PORTFOLIO_LEDGER,
        mode=PersonalStoreMode.PERSONAL,
        identity=identity,
        personal_paths=paths,
        portfolio_ledger_path=ledger_path,
    )
    paper = select_personal_store_route(
        domain=PersonalStoreDomain.PAPER,
        mode=PersonalStoreMode.PERSONAL,
        identity=identity,
        personal_paths=paths,
    )

    assert ledger.read_source == ledger_path
    assert ledger.write_target == ledger_path
    assert ledger.read_source != paper.read_source
    assert not ledger_path.parent.exists()


def test_ledger_rejects_path_outside_personal_root(paths: PersonalDataPaths) -> None:
    with pytest.raises(PersonalStoreRouteError) as exc_info:
        select_personal_store_route(
            domain=PersonalStoreDomain.PORTFOLIO_LEDGER,
            mode=PersonalStoreMode.PERSONAL,
            identity=StoreIdentity("portfolio-7"),
            personal_paths=paths,
            portfolio_ledger_path=paths.legacy_output_root / "ledger.sqlite",
        )
    assert exc_info.value.code == "portfolio_ledger_path_outside_personal"


def test_ledger_rejects_parent_components_before_scope_check(
    paths: PersonalDataPaths,
) -> None:
    traversing_path = paths.personal_root / "ledgers" / ".." / "escape.sqlite"
    with pytest.raises(PersonalStoreRouteError) as exc_info:
        select_personal_store_route(
            domain=PersonalStoreDomain.PORTFOLIO_LEDGER,
            mode=PersonalStoreMode.PERSONAL,
            identity=StoreIdentity("portfolio-7"),
            personal_paths=paths,
            portfolio_ledger_path=traversing_path,
        )
    assert exc_info.value.code == "path_traversal"


def test_required_configuration_errors_are_named(paths: PersonalDataPaths) -> None:
    with pytest.raises(PersonalStoreRouteError) as personal_error:
        select_personal_store_route(
            domain=PersonalStoreDomain.TRADES,
            mode=PersonalStoreMode.PERSONAL,
            identity=StoreIdentity("account-1"),
        )
    assert personal_error.value.code == "personal_root_unconfigured"

    with pytest.raises(PersonalStoreRouteError) as legacy_error:
        select_personal_store_route(
            domain=PersonalStoreDomain.TRADES,
            mode=PersonalStoreMode.LEGACY_COMPAT,
            identity=StoreIdentity("account-1"),
        )
    assert legacy_error.value.code == "legacy_output_root_unconfigured"

    with pytest.raises(PersonalStoreRouteError) as market_error:
        select_personal_store_route(
            domain=PersonalStoreDomain.EVIDENCE,
            mode=PersonalStoreMode.MARKET_READ_ONLY,
            identity=StoreIdentity("market-evidence"),
        )
    assert market_error.value.code == "market_db_path_unconfigured"


def test_market_read_only_is_not_a_private_store_mode(paths: PersonalDataPaths) -> None:
    with pytest.raises(PersonalStoreRouteError) as exc_info:
        select_personal_store_route(
            domain=PersonalStoreDomain.PAPER,
            mode=PersonalStoreMode.MARKET_READ_ONLY,
            identity=StoreIdentity("paper-main"),
            personal_paths=paths,
        )
    assert exc_info.value.code == "market_read_only_evidence_only"
