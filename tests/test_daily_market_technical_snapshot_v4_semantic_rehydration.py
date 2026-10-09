"""驗證 P01 同一 reader-issued proof 的私有 DTO 重建界線。"""

from __future__ import annotations

from dataclasses import replace as dataclass_replace
import gc
import json
import os
from pathlib import Path
from typing import Any
import weakref

import pytest

pytest_plugins = ("tests.test_daily_market_technical_universe_v4_read_session",)

from app_module import daily_market_technical_snapshot_v4_repository as repository_module
from app_module import daily_market_technical_universe_v4_query as query_module
from app_module import daily_market_technical_feature_snapshot_v4 as feature_module
from app_module.daily_market_technical_feature_snapshot_v4 import (
    DailyMarketTechnicalFeatureSnapshotV4,
)
from app_module.daily_market_technical_snapshot_v4_repository import (
    DailyMarketTechnicalSnapshotV4Repository,
    DailyMarketTechnicalSnapshotV4RepositoryError,
)
from app_module.daily_market_technical_universe_v4_query import (
    DailyMarketTechnicalUniverseV4QueryError,
    DailyMarketTechnicalUniverseV4ReadSession,
    open_daily_market_technical_universe_v4_read_session,
)
from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalRuleStateFilterV4,
)
from app_module.personal_data_paths import to_internal_io_path


def _open_session(
    fixture: dict[str, Any],
) -> DailyMarketTechnicalUniverseV4ReadSession:
    plan = fixture["plan"]
    receipt = fixture["complete"]
    return open_daily_market_technical_universe_v4_read_session(
        store_output_root=fixture["store_root"],
        generation_identity_sha256=plan.generation_identity_sha256,
        plan_identity_sha256=plan.identity_sha256,
        plan_sha256=fixture["plan_sha256"],
        receipt_identity_sha256=receipt.identity_sha256,
        receipt_sha256=receipt.content_sha256,
    )


def _artifact_path(reference: Any, stock_code: str) -> Path:
    proof = reference.semantic_proof
    assert proof is not None
    artifact_ref = next(
        item for item in proof.manifest.artifact_refs if item.stock_code == stock_code
    )
    return Path(to_internal_io_path(
        proof.manifest.manifest_path.parent.joinpath(
            *artifact_ref.relative_path.split("/")
        )
    ))


def test_private_rehydration_matches_strict_reader_and_still_fresh_hashes_all_refs(
    synthetic_read_session_source: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _open_session(synthetic_read_session_source)
    strict_clone = dataclass_replace(session)
    query = session.create_query(
        sort_key="volume_ratio_20_including_current.ratio",
        descending=True,
        page_index=0,
        page_size=4,
    )
    assert strict_clone._source_metadata is None
    reference = next(
        item for item in session._artifact_references if item.semantic_proof is not None
    )
    proof = reference.semantic_proof
    capability = reference._rehydration_capability
    assert proof is not None and capability is not None

    original_from_json = DailyMarketTechnicalFeatureSnapshotV4.from_json
    decoded_stock_codes: list[str] = []
    artifact_paths: list[Path] = []
    rehydrated_stock_codes: list[str] = []
    original_read = repository_module._read_bounded_file
    original_rehydrate = repository_module._decode_reader_issued_snapshot
    artifact_names = {
        Path(item.relative_path).name
        for child in session._artifact_references
        if child.semantic_proof is not None
        for item in child.semantic_proof.manifest.artifact_refs
    }

    def expected_artifact_paths_for_page(page: Any) -> set[Path]:
        page_codes = {row.stock_code for row in page.rows}
        page_artifact_indexes = {
            candidate.artifact_index
            for candidate in session._candidates
            if candidate.stock_code in page_codes
        }
        return {
            child.semantic_proof.manifest.manifest_path.parent.joinpath(
                *artifact_ref.relative_path.split("/")
            )
            for artifact_index, child in enumerate(session._artifact_references)
            if artifact_index in page_artifact_indexes and child.semantic_proof is not None
            for artifact_ref in child.semantic_proof.manifest.artifact_refs
        }

    def assert_page_artifacts_fresh_once(start_index: int, page: Any) -> None:
        expected_paths = expected_artifact_paths_for_page(page)
        actual_paths = artifact_paths[start_index:]
        assert len(actual_paths) == len(expected_paths)
        assert set(actual_paths) == expected_paths

    def counted_from_json(
        cls: type[DailyMarketTechnicalFeatureSnapshotV4], raw: bytes | str
    ) -> DailyMarketTechnicalFeatureSnapshotV4:
        snapshot = original_from_json(raw)
        decoded_stock_codes.append(snapshot.stock_code)
        return snapshot

    def counted_read(path: Path, max_bytes: int) -> bytes:
        raw = original_read(path, max_bytes)
        if path.name in artifact_names:
            artifact_paths.append(path)
        return raw

    def counted_rehydrate(
        raw: bytes, ref: Any, manifest: Any
    ) -> DailyMarketTechnicalFeatureSnapshotV4:
        snapshot = original_rehydrate(raw, ref, manifest)
        rehydrated_stock_codes.append(snapshot.stock_code)
        return snapshot

    monkeypatch.setattr(
        DailyMarketTechnicalFeatureSnapshotV4,
        "from_json",
        classmethod(counted_from_json),
    )
    monkeypatch.setattr(repository_module, "_read_bounded_file", counted_read)
    monkeypatch.setattr(repository_module, "_decode_reader_issued_snapshot", counted_rehydrate)

    first_read_count = len(artifact_paths)
    fast_page = session.read_page(query)
    assert_page_artifacts_fresh_once(first_read_count, fast_page)
    assert len(fast_page.rows) == 4
    assert rehydrated_stock_codes
    assert tuple(rehydrated_stock_codes) == tuple(row.stock_code for row in fast_page.rows)

    second_read_count = len(artifact_paths)
    strict_page = strict_clone.read_page(query)
    assert_page_artifacts_fresh_once(second_read_count, strict_page)
    assert fast_page.to_dict() == strict_page.to_dict()
    assert tuple(decoded_stock_codes) == tuple(row.stock_code for row in strict_page.rows)

    selected_codes = tuple(row.stock_code for row in fast_page.rows)
    repository = DailyMarketTechnicalSnapshotV4Repository(
        reference.repository_output_root
    )
    fast_snapshots = repository._read_selected_exact_for_p01_session(
        proof,
        selected_stock_codes=proof.manifest.expected_stock_codes[:2],
        cancel_callback=None,
        session=session,
        reference=reference,
        capability=capability,
    )
    strict_snapshots = repository.read_selected_exact(
        proof,
        selected_stock_codes=proof.manifest.expected_stock_codes[:2],
    )
    assert tuple(item.to_dict() for item in fast_snapshots) == tuple(
        item.to_dict() for item in strict_snapshots
    )
    assert tuple(item.snapshot_identity_sha256 for item in fast_snapshots) == tuple(
        item.snapshot_identity_sha256 for item in strict_snapshots
    )

    # AND/OR、支援排序與跨頁結果也必須逐值等同 strict clone；OR 另核真值 oracle。
    method_keys = session.create_query().method_rule_keys
    volume_index = method_keys.index("volume_ratio_20_including_current")
    cross_index = method_keys.index("ma5_20_golden_cross")
    expected_and_codes = {
        candidate.stock_code
        for candidate in session._candidates
        if candidate.rules[volume_index].state == "match"
        and candidate.rules[cross_index].state == "match"
    }
    expected_or_codes = {
        candidate.stock_code
        for candidate in session._candidates
        if candidate.rules[volume_index].state == "match"
        or candidate.rules[cross_index].state == "match"
    }
    assert expected_or_codes
    filters = (
        DailyMarketTechnicalRuleStateFilterV4.create(
            "volume_ratio_20_including_current", ("match",)
        ),
        DailyMarketTechnicalRuleStateFilterV4.create(
            "ma5_20_golden_cross", ("match",)
        ),
    )
    and_query = session.create_query(
        rule_state_filters=filters,
        combine_mode="AND",
        sort_key="latest_feature_date",
        descending=True,
        page_index=0,
        page_size=4,
    )
    and_page = session.read_page(and_query)
    assert and_page.matching_count == len(expected_and_codes)
    assert and_page.to_dict() == strict_clone.read_page(and_query).to_dict()
    or_query = session.create_query(
        rule_state_filters=filters,
        combine_mode="OR",
        sort_key="latest_feature_date",
        descending=True,
        page_index=0,
        page_size=4,
    )
    or_page = session.read_page(or_query)
    assert or_page.rows
    assert or_page.matching_count == len(expected_or_codes)
    assert {row.stock_code for row in or_page.rows} <= expected_or_codes
    assert or_page.to_dict() == strict_clone.read_page(or_query).to_dict()
    cross_page_query = session.create_query(
        sort_key="latest_feature_date",
        descending=True,
        page_index=1,
        page_size=5,
    )
    cross_page = session.read_page(cross_page_query)
    assert cross_page.rows
    assert cross_page.to_dict() == strict_clone.read_page(cross_page_query).to_dict()


@pytest.mark.parametrize("selected", (True, False), ids=("selected", "unselected"))
def test_private_rehydration_rejects_fresh_selected_or_sibling_tamper_with_restored_mtime(
    synthetic_read_session_source: dict[str, Any],
    selected: bool,
) -> None:
    session = _open_session(synthetic_read_session_source)
    query = session.create_query(sort_key="stock_code", page_size=4)
    original_page = session.read_page(query)
    assert original_page.rows
    reference = next(
        item for item in session._artifact_references if item.semantic_proof is not None
    )
    all_codes = reference.semantic_proof.manifest.expected_stock_codes  # type: ignore[union-attr]
    selected_codes = {row.stock_code for row in original_page.rows}
    target_code = (
        next(code for code in all_codes if code in selected_codes)
        if selected
        else next(code for code in all_codes if code not in selected_codes)
    )
    path = _artifact_path(reference, target_code)
    original_bytes = path.read_bytes()
    original_stat = os.stat(path)
    try:
        path.write_bytes(bytes((original_bytes[0] ^ 1,)) + original_bytes[1:])
        os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as rejected:
            session.read_page(query)
        assert rejected.value.code == "technical_snapshot_v4_artifact_sha_mismatch"
    finally:
        path.write_bytes(original_bytes)
        os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    assert session.read_page(query).to_dict() == original_page.to_dict()


def test_capability_rejects_clone_foreign_reference_and_wrong_repository_root(
    synthetic_read_session_source: dict[str, Any],
) -> None:
    session = _open_session(synthetic_read_session_source)
    reference = next(
        item for item in session._artifact_references if item.semantic_proof is not None
    )
    proof = reference.semantic_proof
    capability = reference._rehydration_capability
    assert proof is not None and capability is not None
    selected = proof.manifest.expected_stock_codes[:1]
    repository = DailyMarketTechnicalSnapshotV4Repository(
        reference.repository_output_root
    )

    clone = dataclass_replace(session)
    with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as clone_rejected:
        repository._read_selected_exact_for_p01_session(
            proof,
            selected_stock_codes=selected,
            cancel_callback=None,
            session=clone,
            reference=reference,
            capability=capability,
        )
    assert clone_rejected.value.code == (
        "technical_snapshot_v4_p01_rehydration_capability_invalid"
    )

    forged_reference = dataclass_replace(
        reference,
        manifest_sha256="0" * 64,
        _rehydration_capability=capability,
    )
    with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as reference_rejected:
        repository._read_selected_exact_for_p01_session(
            proof,
            selected_stock_codes=selected,
            cancel_callback=None,
            session=session,
            reference=forged_reference,
            capability=capability,
        )
    assert reference_rejected.value.code == (
        "technical_snapshot_v4_p01_rehydration_capability_invalid"
    )

    foreign_repository = DailyMarketTechnicalSnapshotV4Repository(
        synthetic_read_session_source["empty"]["store_root"]
    )
    with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as root_rejected:
        foreign_repository._read_selected_exact_for_p01_session(
            proof,
            selected_stock_codes=selected,
            cancel_callback=None,
            session=session,
            reference=reference,
            capability=capability,
        )
    assert root_rejected.value.code == (
        "technical_snapshot_v4_semantic_proof_repository_mismatch"
    )


def test_capability_rejects_same_value_reference_clone_after_metadata_tuple_sync(
    synthetic_read_session_source: dict[str, Any],
) -> None:
    session = _open_session(synthetic_read_session_source)
    reference = next(
        item for item in session._artifact_references if item.semantic_proof is not None
    )
    proof = reference.semantic_proof
    capability = reference._rehydration_capability
    metadata = session._source_metadata
    assert proof is not None and capability is not None and metadata is not None
    clone = dataclass_replace(reference)
    assert clone is not reference
    assert clone == reference
    old_references = session._artifact_references
    old_metadata = metadata
    clone_references = tuple(clone if item is reference else item for item in old_references)
    synchronized_metadata = dataclass_replace(
        metadata, artifact_reference_tuple_owner=clone_references
    )
    object.__setattr__(session, "_artifact_references", clone_references)
    object.__setattr__(session, "_source_metadata", synchronized_metadata)
    try:
        repository = DailyMarketTechnicalSnapshotV4Repository(
            reference.repository_output_root
        )
        with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as rejected:
            repository._read_selected_exact_for_p01_session(
                proof,
                selected_stock_codes=proof.manifest.expected_stock_codes[:1],
                cancel_callback=None,
                session=session,
                reference=clone,
                capability=capability,
            )
        assert rejected.value.code == (
            "technical_snapshot_v4_p01_rehydration_capability_invalid"
        )
    finally:
        object.__setattr__(session, "_artifact_references", old_references)
        object.__setattr__(session, "_source_metadata", old_metadata)


def test_capability_requires_the_exact_registered_session_class(
    synthetic_read_session_source: dict[str, Any],
) -> None:
    session = _open_session(synthetic_read_session_source)
    reference = next(
        item for item in session._artifact_references if item.semantic_proof is not None
    )
    proof = reference.semantic_proof
    assert proof is not None
    def proxy_attribute(self: object, name: str) -> Any:
        return getattr(session, name)

    fake_type = type(
        "DailyMarketTechnicalUniverseV4ReadSession",
        (),
        {
            "__module__": query_module.__name__,
            "__getattr__": proxy_attribute,
        },
    )
    fake_same_name = fake_type()
    metadata = session._source_metadata
    assert metadata is not None and metadata.matches_session(fake_same_name)
    with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as rejected:
        repository_module._issue_p01_semantic_rehydration_capability(
            session=fake_same_name,
            reference=reference,
            proof=proof,
        )
    assert rejected.value.code == (
        "technical_snapshot_v4_p01_rehydration_session_not_issued"
    )


def test_capability_cannot_outlive_its_weakly_held_session(
    synthetic_read_session_source: dict[str, Any],
) -> None:
    session = _open_session(synthetic_read_session_source)
    reference = next(
        item for item in session._artifact_references if item.semantic_proof is not None
    )
    proof = reference.semantic_proof
    capability = reference._rehydration_capability
    assert proof is not None and capability is not None
    session_ref = weakref.ref(session)
    repository = DailyMarketTechnicalSnapshotV4Repository(
        reference.repository_output_root
    )
    session = None  # type: ignore[assignment]
    gc.collect()
    assert session_ref() is None
    with pytest.raises(DailyMarketTechnicalSnapshotV4RepositoryError) as rejected:
        repository._read_selected_exact_for_p01_session(
            proof,
            selected_stock_codes=proof.manifest.expected_stock_codes[:1],
            cancel_callback=None,
            session=object(),
            reference=reference,
            capability=capability,
        )
    assert rejected.value.code == (
        "technical_snapshot_v4_p01_rehydration_capability_invalid"
    )


def test_public_json_parser_rejects_self_rehashed_invalid_pit_semantics(
    synthetic_read_session_source: dict[str, Any],
) -> None:
    session = _open_session(synthetic_read_session_source)
    reference = next(
        item for item in session._artifact_references if item.semantic_proof is not None
    )
    proof = reference.semantic_proof
    assert proof is not None
    raw = _artifact_path(reference, proof.manifest.expected_stock_codes[0]).read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    payload["availability"]["historical_pit_eligible"] = True
    payload["snapshot_identity_sha256"] = feature_module._identity_sha256(payload)
    rehashed_raw = repository_module.canonical_v4_json_bytes(payload)
    with pytest.raises(ValueError, match="technical_snapshot_v4_availability_invalid"):
        DailyMarketTechnicalFeatureSnapshotV4.from_json(rehashed_raw)


def test_nested_rehydration_context_restores_outer_value_on_success_and_error(
    synthetic_read_session_source: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _open_session(synthetic_read_session_source)
    reference = next(
        item for item in session._artifact_references if item.semantic_proof is not None
    )
    selected = (reference.semantic_proof.manifest.expected_stock_codes[0],)  # type: ignore[union-attr]
    original_read = query_module._read_session_child_snapshots
    original_context = object()
    token = query_module._P01_REHYDRATION_CALL_CONTEXT.set(original_context)  # type: ignore[arg-type]
    depth = 0
    seen_contexts: list[object] = []

    def reentrant_read(
        current_reference: Any,
        *,
        selected_stock_codes: Any,
        cancel_callback: Any,
    ) -> Any:
        nonlocal depth
        active = query_module._P01_REHYDRATION_CALL_CONTEXT.get()
        assert active is not None
        seen_contexts.append(active)
        if depth == 0:
            depth += 1
            try:
                result = query_module._read_session_child_snapshots_for_session(
                    session,
                    reference,
                    selected_stock_codes=selected_stock_codes,
                    cancel_callback=cancel_callback,
                )
            finally:
                depth -= 1
            assert query_module._P01_REHYDRATION_CALL_CONTEXT.get() is active
            return result
        return original_read(
            current_reference,
            selected_stock_codes=selected_stock_codes,
            cancel_callback=cancel_callback,
        )

    monkeypatch.setattr(query_module, "_read_session_child_snapshots", reentrant_read)
    try:
        result = query_module._read_session_child_snapshots_for_session(
            session,
            reference,
            selected_stock_codes=selected,
            cancel_callback=None,
        )
        assert len(result) == 1
        assert len(seen_contexts) == 2
        assert seen_contexts[0] is not seen_contexts[1]
        assert query_module._P01_REHYDRATION_CALL_CONTEXT.get() is original_context

        def raise_read(*_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("synthetic_reentrant_read_failure")

        monkeypatch.setattr(query_module, "_read_session_child_snapshots", raise_read)
        with pytest.raises(RuntimeError, match="synthetic_reentrant_read_failure"):
            query_module._read_session_child_snapshots_for_session(
                session,
                reference,
                selected_stock_codes=selected,
                cancel_callback=None,
            )
        assert query_module._P01_REHYDRATION_CALL_CONTEXT.get() is original_context

        monkeypatch.setattr(
            query_module, "_read_session_child_snapshots", original_read
        )
        with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as cancelled:
            query_module._read_session_child_snapshots_for_session(
                session,
                reference,
                selected_stock_codes=selected,
                cancel_callback=lambda: True,
            )
        assert cancelled.value.code == "technical_universe_v4_query_cancelled"
        assert query_module._P01_REHYDRATION_CALL_CONTEXT.get() is original_context
    finally:
        query_module._P01_REHYDRATION_CALL_CONTEXT.reset(token)


def test_nested_dataclass_clone_uses_strict_decoder_without_outer_capability(
    synthetic_read_session_source: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _open_session(synthetic_read_session_source)
    clone = dataclass_replace(session)
    query = session.create_query(sort_key="stock_code", page_size=1)
    reference = next(
        item for item in session._artifact_references if item.semantic_proof is not None
    )
    selected = (reference.semantic_proof.manifest.expected_stock_codes[0],)  # type: ignore[union-attr]

    original_from_json = DailyMarketTechnicalFeatureSnapshotV4.from_json
    strict_decode_count = 0

    def counted_from_json(
        cls: type[DailyMarketTechnicalFeatureSnapshotV4], raw: bytes | str
    ) -> DailyMarketTechnicalFeatureSnapshotV4:
        nonlocal strict_decode_count
        strict_decode_count += 1
        return original_from_json(raw)

    monkeypatch.setattr(
        DailyMarketTechnicalFeatureSnapshotV4,
        "from_json",
        classmethod(counted_from_json),
    )
    previous_context = object()
    context_token = query_module._P01_REHYDRATION_CALL_CONTEXT.set(previous_context)  # type: ignore[arg-type]
    nested_pages: list[Any] = []
    callback_contexts: list[object | None] = []
    did_nested_read = False

    def nested_clone_read() -> bool:
        nonlocal did_nested_read
        if not did_nested_read:
            did_nested_read = True
            callback_contexts.append(query_module._P01_REHYDRATION_CALL_CONTEXT.get())
            nested_page = clone.read_page(query)
            nested_pages.append(nested_page)
            assert nested_page.rows
            assert query_module._P01_REHYDRATION_CALL_CONTEXT.get() is None
        return False

    try:
        fast_snapshots = query_module._read_session_child_snapshots_for_session(
            session,
            reference,
            selected_stock_codes=selected,
            cancel_callback=nested_clone_read,
        )
        assert len(fast_snapshots) == 1
        assert len(nested_pages) == 1
        assert callback_contexts == [None]
        assert strict_decode_count > 0
        assert query_module._P01_REHYDRATION_CALL_CONTEXT.get() is previous_context
    finally:
        query_module._P01_REHYDRATION_CALL_CONTEXT.reset(context_token)


def test_nested_second_reader_uses_its_own_scope_and_restores_outer_context(
    synthetic_read_session_source: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outer_session = _open_session(synthetic_read_session_source)
    nested_session = _open_session(synthetic_read_session_source)
    outer_reference = next(
        item
        for item in outer_session._artifact_references
        if item.semantic_proof is not None
    )
    nested_reference = next(
        item
        for item in nested_session._artifact_references
        if item.semantic_proof is not None
    )
    outer_selected = (
        outer_reference.semantic_proof.manifest.expected_stock_codes[0],  # type: ignore[union-attr]
    )
    nested_selected = (
        nested_reference.semantic_proof.manifest.expected_stock_codes[1],  # type: ignore[union-attr]
    )

    original_rehydrate = repository_module._decode_reader_issued_snapshot
    rehydrated_codes: list[str] = []

    def counted_rehydrate(raw: bytes, ref: Any, manifest: Any) -> Any:
        snapshot = original_rehydrate(raw, ref, manifest)
        rehydrated_codes.append(snapshot.stock_code)
        return snapshot

    monkeypatch.setattr(
        repository_module, "_decode_reader_issued_snapshot", counted_rehydrate
    )
    previous_context = object()
    context_token = query_module._P01_REHYDRATION_CALL_CONTEXT.set(previous_context)  # type: ignore[arg-type]
    nested_results: list[tuple[DailyMarketTechnicalFeatureSnapshotV4, ...]] = []
    callback_contexts: list[object | None] = []
    did_nested_read = False

    def nested_reader_read() -> bool:
        nonlocal did_nested_read
        if not did_nested_read:
            did_nested_read = True
            callback_contexts.append(query_module._P01_REHYDRATION_CALL_CONTEXT.get())
            nested_results.append(
                query_module._read_session_child_snapshots_for_session(
                    nested_session,
                    nested_reference,
                    selected_stock_codes=nested_selected,
                    cancel_callback=None,
                )
            )
            assert query_module._P01_REHYDRATION_CALL_CONTEXT.get() is None
        return False

    try:
        outer_result = query_module._read_session_child_snapshots_for_session(
            outer_session,
            outer_reference,
            selected_stock_codes=outer_selected,
            cancel_callback=nested_reader_read,
        )
        assert len(outer_result) == 1
        assert len(nested_results) == 1 and len(nested_results[0]) == 1
        assert callback_contexts == [None]
        assert len(rehydrated_codes) == 2
        assert rehydrated_codes == [nested_selected[0], outer_selected[0]]
        assert query_module._P01_REHYDRATION_CALL_CONTEXT.get() is previous_context
    finally:
        query_module._P01_REHYDRATION_CALL_CONTEXT.reset(context_token)


def test_general_repository_api_keeps_strict_from_json_path(
    synthetic_read_session_source: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _open_session(synthetic_read_session_source)
    reference = next(
        item for item in session._artifact_references if item.semantic_proof is not None
    )
    proof = reference.semantic_proof
    assert proof is not None
    original_from_json = DailyMarketTechnicalFeatureSnapshotV4.from_json
    decoded = 0

    def counted_from_json(
        cls: type[DailyMarketTechnicalFeatureSnapshotV4], raw: bytes | str
    ) -> DailyMarketTechnicalFeatureSnapshotV4:
        nonlocal decoded
        decoded += 1
        return original_from_json(raw)

    monkeypatch.setattr(
        DailyMarketTechnicalFeatureSnapshotV4,
        "from_json",
        classmethod(counted_from_json),
    )
    repository = DailyMarketTechnicalSnapshotV4Repository(
        reference.repository_output_root
    )
    snapshots = repository.read_selected_exact(
        proof,
        selected_stock_codes=proof.manifest.expected_stock_codes[:2],
    )
    assert len(snapshots) == 2
    assert decoded == 2


def test_cancel_before_during_and_after_private_rehydration_returns_no_page(
    synthetic_read_session_source: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _open_session(synthetic_read_session_source)
    query = session.create_query(sort_key="stock_code", page_size=4)
    original_read = repository_module._read_bounded_file
    artifact_reads = 0

    def counted_read(path: Path, max_bytes: int) -> bytes:
        nonlocal artifact_reads
        if path.parent.name == "artifacts":
            artifact_reads += 1
        return original_read(path, max_bytes)

    monkeypatch.setattr(repository_module, "_read_bounded_file", counted_read)
    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as before:
        session.read_page(query, cancel_callback=lambda: True)
    assert before.value.code == "technical_universe_v4_query_cancelled"
    assert artifact_reads == 0

    cancelled_during_read = False

    def cancel_after_first_artifact(path: Path, max_bytes: int) -> bytes:
        nonlocal artifact_reads, cancelled_during_read
        raw = original_read(path, max_bytes)
        if path.parent.name == "artifacts":
            artifact_reads += 1
            cancelled_during_read = True
        return raw

    monkeypatch.setattr(repository_module, "_read_bounded_file", cancel_after_first_artifact)
    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as during:
        session.read_page(query, cancel_callback=lambda: cancelled_during_read)
    assert during.value.code == "technical_universe_v4_query_cancelled"
    assert artifact_reads == 1

    monkeypatch.setattr(repository_module, "_read_bounded_file", original_read)
    original_child_read = query_module._read_session_child_snapshots
    child_read_completed = False

    def cancel_after_child_read(
        reference: Any,
        *,
        selected_stock_codes: Any,
        cancel_callback: Any,
    ) -> Any:
        nonlocal child_read_completed
        result = original_child_read(
            reference,
            selected_stock_codes=selected_stock_codes,
            cancel_callback=cancel_callback,
        )
        child_read_completed = True
        return result

    monkeypatch.setattr(
        query_module, "_read_session_child_snapshots", cancel_after_child_read
    )
    with pytest.raises(DailyMarketTechnicalUniverseV4QueryError) as after:
        session.read_page(query, cancel_callback=lambda: child_read_completed)
    assert after.value.code == "technical_universe_v4_query_cancelled"
    monkeypatch.setattr(
        query_module, "_read_session_child_snapshots", original_child_read
    )
    assert tuple(row.stock_code for row in session.read_page(query).rows) == (
        "S0000", "S0001", "S0002", "S0003"
    )
