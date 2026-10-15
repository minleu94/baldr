"""P02 V3 四路 projection 的 exact multiparent callback regression。"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import hashlib
import json
from threading import Event
from typing import Any

import pytest

from pathlib import Path
import sys

_REPO = next(
    path for path in Path(__file__).resolve().parents
    if (path / "tests").is_dir() and (path / "app_module").is_dir()
)
if str(_REPO / "tests") not in sys.path:
    sys.path.insert(0, str(_REPO / "tests"))

pytest_plugins = ("test_daily_market_technical_official_disposition_composite_reader_v1",)

import app_module.daily_market_technical_official_disposition_query_reader_v1 as reader
import app_module.daily_market_technical_universe_projection_group_session_v3 as group_session_v3
import app_module.daily_market_technical_universe_projection_group_v3 as group_v3
import app_module.daily_market_technical_universe_price_query_v1 as price_v1
from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DailyMarketTechnicalOfficialDispositionBundleReaderV1,
)
from app_module.daily_market_technical_universe_v4_store import (
    DailyMarketTechnicalUniverseV4StoreReader,
)


def test_v3_exact_opener_builds_four_members_from_one_real_two_parent_read(
    monkeypatch: pytest.MonkeyPatch,
    bundle_fixture: Any,
    exact_query: Any,
) -> None:
    bundle_reads: list[object] = []
    store_reads: list[object] = []
    parent_callbacks: list[int] = []
    fact_inputs: list[tuple[object, object]] = []

    original_bundle_read = DailyMarketTechnicalOfficialDispositionBundleReaderV1.read_exact

    def observe_bundle_read(instance: Any, *args: Any, **kwargs: Any) -> Any:
        bundle_reads.append(kwargs.get("technical_read_session_builder"))
        return original_bundle_read(instance, *args, **kwargs)

    original_store_read = DailyMarketTechnicalUniverseV4StoreReader.read_exact_with_verified_parent_callback

    def observe_store_read(instance: Any, *args: Any, **kwargs: Any) -> Any:
        callback = kwargs["parent_verified_callback"]

        def observe_parent(segment_index: int, parent_read: Any) -> Any:
            parent_callbacks.append(segment_index)
            return callback(segment_index, parent_read)

        kwargs["parent_verified_callback"] = observe_parent
        store_reads.append(instance)
        return original_store_read(instance, *args, **kwargs)

    original_fact_builder = group_v3.build_daily_market_technical_universe_price_fact_from_verified_parent_v1

    def observe_fact_builder(snapshot: Any, parent_row: Any, *, decision_date: Any) -> Any:
        fact_inputs.append((snapshot, parent_row))
        return original_fact_builder(snapshot, parent_row, decision_date=decision_date)

    monkeypatch.setattr(
        DailyMarketTechnicalOfficialDispositionBundleReaderV1,
        "read_exact",
        observe_bundle_read,
    )
    monkeypatch.setattr(
        DailyMarketTechnicalUniverseV4StoreReader,
        "read_exact_with_verified_parent_callback",
        observe_store_read,
    )
    monkeypatch.setattr(
        group_v3,
        "build_daily_market_technical_universe_price_fact_from_verified_parent_v1",
        observe_fact_builder,
    )

    session = reader.open_daily_market_technical_official_disposition_projection_group_session_v3(
        exact_query,
    )

    assert len(bundle_reads) == 1 and bundle_reads[0] is not None
    assert len(store_reads) == 1
    assert tuple(parent_callbacks) == (0, 1)
    assert session.reader_issued is True
    assert session.parent_segment_indexes == (0, 1)
    facts = session.price_facts
    assert tuple(fact.stock_code for fact in facts) == bundle_fixture.included_codes
    assert len(facts) == len(bundle_fixture.included_codes) == len(fact_inputs)
    for fact, (snapshot, parent_row) in zip(facts, fact_inputs, strict=True):
        expected = original_fact_builder(
            snapshot,
            parent_row,
            decision_date=snapshot.decision_date,
        )
        assert fact.to_dict() == expected.to_dict()
        assert fact.stock_code == snapshot.stock_code == parent_row.stock_code
        assert fact.snapshot_identity_sha256 == snapshot.snapshot_identity_sha256 == parent_row.snapshot_identity_sha256
        assert fact.source_identity == snapshot.source_identity == parent_row.source_identity
        assert fact.observation_date == parent_row.latest_feature_date
        assert fact.observation_date is None or fact.observation_date <= parent_row.decision_date
        if fact.status == "unknown":
            assert fact.reason_codes

    digest, size = price_v1.digest_daily_market_technical_universe_price_facts_v1(facts)
    assert session.price_index_identity_sha256 == digest
    assert session.price_index_bytes == size
    payload = session.to_dict()
    group_identity = payload.pop("group_session_identity_sha256")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == group_identity == session.identity_sha256
    changed_payload = json.loads(canonical)
    changed_payload["member_views"]["price"]["index_identity_sha256"] = "0" * 64
    changed_canonical = json.dumps(
        changed_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    )
    assert hashlib.sha256(changed_canonical.encode("utf-8")).hexdigest() != group_identity

    changed_facts = list(facts)
    known_position = next(index for index, fact in enumerate(changed_facts) if fact.status == "known")
    known_fact = changed_facts[known_position]
    assert known_fact.close_price is not None
    changed_facts[known_position] = replace(
        known_fact,
        close_price=known_fact.close_price + Decimal("0.01"),
    )
    changed_digest, _ = price_v1.digest_daily_market_technical_universe_price_facts_v1(tuple(changed_facts))
    assert changed_digest != digest


def test_v3_mismatched_fact_is_poisoned_before_any_session_is_issued(
    monkeypatch: pytest.MonkeyPatch,
    exact_query: Any,
) -> None:
    original_fact_builder = group_v3.build_daily_market_technical_universe_price_fact_from_verified_parent_v1
    fact_calls = 0

    def mismatched_fact(snapshot: Any, parent_row: Any, *, decision_date: Any) -> Any:
        nonlocal fact_calls
        fact_calls += 1
        fact = original_fact_builder(snapshot, parent_row, decision_date=decision_date)
        if fact_calls == 1:
            changed = "0" * 64 if fact.snapshot_identity_sha256 != "0" * 64 else "1" * 64
            return replace(fact, snapshot_identity_sha256=changed)
        return fact

    issue_calls: list[object] = []
    original_issue = group_session_v3._prepare_and_issue_projection_group_session_v3

    def observe_issue(*args: Any, **kwargs: Any) -> Any:
        issue_calls.append(args[0])
        return original_issue(*args, **kwargs)

    poison_states: list[tuple[str, int, int]] = []
    original_poison = group_v3.DailyMarketTechnicalUniverseProjectionGroupV3._poison

    def observe_poison(group: group_v3.DailyMarketTechnicalUniverseProjectionGroupV3) -> None:
        original_poison(group)
        poison_states.append((group.status, group.processed_snapshot_count, len(group._price_facts_by_code)))

    monkeypatch.setattr(group_v3, "build_daily_market_technical_universe_price_fact_from_verified_parent_v1", mismatched_fact)
    monkeypatch.setattr(group_session_v3, "_prepare_and_issue_projection_group_session_v3", observe_issue)
    monkeypatch.setattr(group_v3.DailyMarketTechnicalUniverseProjectionGroupV3, "_poison", observe_poison)

    with pytest.raises(reader.DailyMarketTechnicalOfficialDispositionQueryReaderV1Error) as failure:
        reader.open_daily_market_technical_official_disposition_projection_group_session_v3(exact_query)

    assert failure.value.code.endswith("technical_universe_v4_parent_verified_callback_failed")
    assert fact_calls == 1
    assert issue_calls == []
    assert poison_states and all(state == ("failed", 0, 0) for state in poison_states)


def test_v3_cancel_after_first_fact_clears_all_partial_members_and_does_not_issue(
    monkeypatch: pytest.MonkeyPatch,
    exact_query: Any,
) -> None:
    cancel_event = Event()
    original_fact_builder = group_v3.build_daily_market_technical_universe_price_fact_from_verified_parent_v1
    fact_calls = 0

    def cancel_after_fact(snapshot: Any, parent_row: Any, *, decision_date: Any) -> Any:
        nonlocal fact_calls
        fact_calls += 1
        fact = original_fact_builder(snapshot, parent_row, decision_date=decision_date)
        cancel_event.set()
        return fact

    issue_calls: list[object] = []
    original_issue = group_session_v3._prepare_and_issue_projection_group_session_v3

    def observe_issue(*args: Any, **kwargs: Any) -> Any:
        issue_calls.append(args[0])
        return original_issue(*args, **kwargs)

    poison_states: list[tuple[str, int, int]] = []
    original_poison = group_v3.DailyMarketTechnicalUniverseProjectionGroupV3._poison

    def observe_poison(group: group_v3.DailyMarketTechnicalUniverseProjectionGroupV3) -> None:
        original_poison(group)
        poison_states.append((group.status, group.processed_snapshot_count, len(group._price_facts_by_code)))

    monkeypatch.setattr(group_v3, "build_daily_market_technical_universe_price_fact_from_verified_parent_v1", cancel_after_fact)
    monkeypatch.setattr(group_session_v3, "_prepare_and_issue_projection_group_session_v3", observe_issue)
    monkeypatch.setattr(group_v3.DailyMarketTechnicalUniverseProjectionGroupV3, "_poison", observe_poison)

    with pytest.raises(reader.DailyMarketTechnicalOfficialDispositionQueryReaderV1Cancelled):
        reader.open_daily_market_technical_official_disposition_projection_group_session_v3(
            exact_query,
            cancel_callback=cancel_event.is_set,
        )

    assert fact_calls == 1
    assert issue_calls == []
    assert poison_states and all(state == ("failed", 0, 0) for state in poison_states)
