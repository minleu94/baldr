"""H20 同次完整讀取檢視的合成驗證。"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import pickle
import sqlite3
from typing import Any, Mapping

import pytest


def _install_real_h20_ports(saved: Mapping[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.scheduled.run_personal_current_observed_h20_daily as runner

    actual_source_port = runner._source_port
    contract_verifier = saved["contract_fixture"]["verifier"]

    def public_ports(*, read_session_resolver=None, raw_snapshot_observer=None):
        if read_session_resolver is None and raw_snapshot_observer is None:
            source_verifier = actual_source_port
        else:
            def source_verifier(binding: Mapping[str, Any]) -> Mapping[str, Any]:
                return actual_source_port(
                    binding,
                    read_session_resolver=read_session_resolver,
                    raw_snapshot_observer=raw_snapshot_observer,
                )

        return {
            "source_verifier": source_verifier,
            "contract_verifier": contract_verifier,
        }

    monkeypatch.setattr(runner, "personal_current_observed_h20_read_ports", public_ports)


def _saved_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Mapping[str, Any], Path]:
    from tests.test_ui_qt_h20_saved_source_journey import _build_saved_h20_store

    saved = _build_saved_h20_store(tmp_path, monkeypatch)
    _install_real_h20_ports(saved, monkeypatch)
    private_root = tmp_path / "h20-private-read-root"
    private_root.mkdir()
    return saved, private_root


def _selection(cohort, row):
    from app_module.recommendation.personal_h20_research_cohort import (
        PersonalH20ResearchSelection,
    )

    return PersonalH20ResearchSelection(
        manifest_sha256=cohort.manifest_sha256,
        candidate_id=cohort.candidate_id,
        contract_hash=cohort.contract_hash,
        cycle_id=cohort.cycle_id,
        symbol=row.symbol,
        sample_id=row.sample_id,
        prediction_id=row.prediction_id,
        capture_sha256=row.capture_sha256,
    )


def test_verified_view_reuses_one_real_cohort_pipeline_and_projects_without_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.scheduled.personal_h20_daily_hook as hook
    import scripts.scheduled.personal_h20_sqlite_read_operation as operation_module
    from app_module.recommendation.personal_h20_verified_cohort_view import (
        PersonalH20VerifiedCohortView,
        project_personal_h20_verified_cohort_selection,
    )
    from app_module.recommendation.personal_h20_read_session import PersonalH20ReadSession

    saved, private_root = _saved_store(tmp_path, monkeypatch)
    operation_type = operation_module.PersonalH20SQLiteReadOperation
    real_operation_finish = operation_type.finish
    finishes: list[tuple[Any, ...]] = []
    copy_paths: list[str] = []
    semantic_finishes: list[bool] = []
    real_semantic_finish = PersonalH20ReadSession.finish

    def tracked_operation_finish(self):
        bindings = real_operation_finish(self)
        finishes.append(bindings)
        copy_paths.extend(binding.reader_database_path for binding in bindings)
        return bindings

    def tracked_semantic_finish(self, *, finalizer=None):
        real_semantic_finish(self, finalizer=finalizer)
        semantic_finishes.append(True)

    monkeypatch.setattr(operation_type, "finish", tracked_operation_finish)
    monkeypatch.setattr(PersonalH20ReadSession, "finish", tracked_semantic_finish)

    view = hook.read_personal_h20_verified_cohort_view(
        saved["activation"].config_path,
        market_root=Path(saved["market_root"]),
        sqlite_read_root=private_root,
    )

    assert type(view) is PersonalH20VerifiedCohortView
    assert len(view.cohort.rows) == 1
    row = view.cohort.rows[0]
    assert (row.symbol, row.status, row.gross_return_bp) == ("2382", "available", 1234)
    assert len(view.row_pins) == len(view.cohort.symbols) == len(view.cohort.rows)
    assert view.row_pins[0].symbol == row.symbol
    assert view.row_pins[0].capture_sha256 == row.capture_sha256
    assert len(view.source_binding_identity_sha256) == 1
    assert len(view.contract_binding_identity_sha256) == 1
    assert len(view.sqlite_binding_identity_sha256) == 1
    assert view.completed_at_utc.tzinfo is not None
    assert view.completed_at_utc.utcoffset().total_seconds() == 0
    assert len(finishes) == len(semantic_finishes) == 1
    assert not list(private_root.iterdir())
    assert copy_paths and all(path not in repr(view) for path in copy_paths)

    selection = _selection(view.cohort, row)
    open_calls: list[str] = []
    product_evidence_module = __import__(
        "app_module.recommendation.personal_h20_product_evidence",
        fromlist=["read_personal_h20_product_reference"],
    )
    real_reference_reader = product_evidence_module.read_personal_h20_product_reference
    reference_reads = 0

    def counted_reference_reader(*args: Any, **kwargs: Any):
        nonlocal reference_reads
        reference_reads += 1
        return real_reference_reader(*args, **kwargs)

    def forbidden_sqlite_connect(database: Any, *_args: Any, **_kwargs: Any):
        open_calls.append(str(database))
        raise AssertionError("已核 view 投影不得再開 SQLite")

    def forbidden_capture_read(*_args: Any, **_kwargs: Any):
        raise AssertionError("已核 view 投影不得重讀 capture")

    monkeypatch.setattr(product_evidence_module, "read_personal_h20_product_reference", counted_reference_reader)
    monkeypatch.setattr(sqlite3, "connect", forbidden_sqlite_connect)
    monkeypatch.setattr(hook, "_read_personal_h20_prediction_with_verifiers", forbidden_capture_read)

    pure_result = project_personal_h20_verified_cohort_selection(view, selection)
    checked_result = hook.project_personal_h20_verified_cohort_selection_with_reference(
        view,
        selection,
        config_path=saved["activation"].config_path,
        market_root=Path(saved["market_root"]),
        sqlite_read_root=private_root,
    )
    assert pure_result == checked_result
    assert checked_result.status == "available"
    assert checked_result.gross_return_bp == 1234
    assert checked_result.source_date == row.source_date
    assert checked_result.feature_date == row.feature_as_of_date
    assert reference_reads == 2
    assert open_calls == []
    assert len(finishes) == len(semantic_finishes) == 1


def test_verified_view_rejects_unknown_rows_and_allows_empty_binding_groups(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.scheduled.personal_h20_daily_hook as hook
    from app_module.recommendation.personal_h20_verified_cohort_view import (
        project_personal_h20_verified_cohort_selection,
    )

    saved, private_root = _saved_store(tmp_path, monkeypatch)

    def rejected_capture(*_args: Any, **_kwargs: Any) -> Mapping[str, Any]:
        raise ValueError("synthetic_capture_unavailable")

    monkeypatch.setattr(hook, "_read_personal_h20_prediction_with_verifiers", rejected_capture)
    view = hook.read_personal_h20_verified_cohort_view(
        saved["activation"].config_path,
        market_root=Path(saved["market_root"]),
        sqlite_read_root=private_root,
    )
    assert all(row.status == "unknown" and row.gross_return_bp is None for row in view.cohort.rows)
    assert view.source_binding_identity_sha256 == ()
    assert view.contract_binding_identity_sha256 == ()
    assert view.sqlite_binding_identity_sha256 == ()
    with pytest.raises(ValueError, match="not_available"):
        project_personal_h20_verified_cohort_selection(
            view,
            _selection(view.cohort, view.cohort.rows[0]),
        )


def test_verified_view_requires_terminal_finish_and_final_post_seal_cancel_poll(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.scheduled.personal_h20_daily_hook as hook
    import scripts.scheduled.personal_h20_sqlite_read_operation as operation_module

    saved, private_root = _saved_store(tmp_path, monkeypatch)
    operation_type = operation_module.PersonalH20SQLiteReadOperation
    real_finish = operation_type.finish

    def failed_finish(self):
        real_finish(self)
        raise RuntimeError("synthetic_terminal_failure")

    monkeypatch.setattr(operation_type, "finish", failed_finish)
    with pytest.raises(RuntimeError, match="synthetic_terminal_failure"):
        hook.read_personal_h20_verified_cohort_view(
            saved["activation"].config_path,
            market_root=Path(saved["market_root"]),
            sqlite_read_root=private_root,
        )

    monkeypatch.setattr(operation_type, "finish", real_finish)
    cancelled = {"value": False}
    real_issue = hook._issue_personal_h20_verified_cohort_view
    issued_ids: list[str] = []

    def cancel_after_seal(**kwargs: Any):
        view = real_issue(**kwargs)
        issued_ids.append(view.view_id)
        cancelled["value"] = True
        return view

    monkeypatch.setattr(hook, "_issue_personal_h20_verified_cohort_view", cancel_after_seal)
    with pytest.raises(InterruptedError, match="cancelled"):
        hook.read_personal_h20_verified_cohort_view(
            saved["activation"].config_path,
            market_root=Path(saved["market_root"]),
            sqlite_read_root=private_root,
            cancel_callback=lambda: cancelled["value"],
        )
    assert len(issued_ids) == 1


def test_verified_view_rejects_semantic_binding_terminal_event_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.scheduled.personal_h20_daily_hook as hook
    from app_module.recommendation.personal_h20_read_session import PersonalH20ReadSession

    saved, private_root = _saved_store(tmp_path, monkeypatch)
    real_emit = PersonalH20ReadSession._emit

    def mismatched_terminal_event(self, *args: Any, **kwargs: Any) -> None:
        if kwargs.get("stage") == "source_group_rechecked":
            kwargs["identity_sha256"] = "f" * 64
        real_emit(self, *args, **kwargs)

    monkeypatch.setattr(PersonalH20ReadSession, "_emit", mismatched_terminal_event)
    with pytest.raises(ValueError, match="binding_events_incomplete"):
        hook.read_personal_h20_verified_cohort_view(
            saved["activation"].config_path,
            market_root=Path(saved["market_root"]),
            sqlite_read_root=private_root,
        )


def test_legacy_cohort_api_keeps_reference_and_cohort_tuple(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.scheduled.personal_h20_daily_hook as hook
    from app_module.recommendation.personal_h20_product_evidence import PersonalH20ProductReference
    from app_module.recommendation.personal_h20_research_cohort import PersonalH20ResearchCohort

    saved, private_root = _saved_store(tmp_path, monkeypatch)
    result = hook.read_personal_h20_product_cohort(
        saved["activation"].config_path,
        market_root=Path(saved["market_root"]),
        sqlite_read_root=private_root,
        require_sqlite_copy=True,
    )
    assert type(result) is tuple and len(result) == 2
    assert type(result[0]) is PersonalH20ProductReference
    assert type(result[1]) is PersonalH20ResearchCohort
    assert result[1].rows[0].symbol == "2382"


def test_verified_view_seal_rejects_replacement_serialization_and_hash_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace
    import scripts.scheduled.personal_h20_daily_hook as hook
    from app_module.recommendation.personal_h20_verified_cohort_view import (
        PersonalH20VerifiedCohortView,
        assert_personal_h20_verified_cohort_view,
    )

    saved, private_root = _saved_store(tmp_path, monkeypatch)
    view = hook.read_personal_h20_verified_cohort_view(
        saved["activation"].config_path,
        market_root=Path(saved["market_root"]),
        sqlite_read_root=private_root,
    )
    with pytest.raises(TypeError, match="reader"):
        PersonalH20VerifiedCohortView()
    with pytest.raises(TypeError):
        replace(view, view_id="0" * 32)
    with pytest.raises(TypeError, match="serialized"):
        pickle.dumps(view)

    original = view.source_binding_identity_sha256
    object.__setattr__(view, "source_binding_identity_sha256", ("0" * 64,))
    with pytest.raises(ValueError, match="seal_mismatch"):
        assert_personal_h20_verified_cohort_view(view)
    object.__setattr__(view, "source_binding_identity_sha256", original)


def test_verified_view_rejects_pointer_selection_and_context_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.scheduled.personal_h20_daily_hook as hook
    from app_module.recommendation.personal_h20_product_evidence import (
        PersonalH20ProductReference,
    )

    saved, private_root = _saved_store(tmp_path, monkeypatch)
    view = hook.read_personal_h20_verified_cohort_view(
        saved["activation"].config_path,
        market_root=Path(saved["market_root"]),
        sqlite_read_root=private_root,
    )
    selection = _selection(view.cohort, view.cohort.rows[0])

    different_private_root = tmp_path / "different-private-root"
    different_private_root.mkdir()
    with pytest.raises(ValueError, match="context_changed"):
        hook.project_personal_h20_verified_cohort_selection_with_reference(
            view,
            selection,
            config_path=saved["activation"].config_path,
            market_root=Path(saved["market_root"]),
            sqlite_read_root=different_private_root,
        )

    module = __import__(
        "app_module.recommendation.personal_h20_product_evidence",
        fromlist=["read_personal_h20_product_reference"],
    )
    real_reader = module.read_personal_h20_product_reference
    reads = 0

    def drifting_reader(*args: Any, **kwargs: Any) -> PersonalH20ProductReference:
        nonlocal reads
        reads += 1
        reference = real_reader(*args, **kwargs)
        if reads == 2:
            return replace(reference, cycle_id=reference.cycle_id + "-changed")
        return reference

    monkeypatch.setattr(module, "read_personal_h20_product_reference", drifting_reader)
    with pytest.raises(ValueError, match="reference_changed"):
        hook.project_personal_h20_verified_cohort_selection_with_reference(
            view,
            selection,
            config_path=saved["activation"].config_path,
            market_root=Path(saved["market_root"]),
            sqlite_read_root=private_root,
        )
    assert reads == 2

    wrong_selection = replace(selection, capture_sha256="sha256:" + "0" * 64)
    from app_module.recommendation.personal_h20_verified_cohort_view import (
        project_personal_h20_verified_cohort_selection,
    )

    with pytest.raises(ValueError, match="selection"):
        project_personal_h20_verified_cohort_selection(view, wrong_selection)
