from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app_module.dtos.decision_continuity_dtos import (
    ACTION_NOTE,
    IDENTITY_STATUS_UNKNOWN,
    DecisionIdentity,
)
from app_module.journal_service import JournalService
from app_module.personal_journal_paths import resolve_personal_journal_paths
from app_module.stock_research_report_notes import (
    STOCK_RESEARCH_REPORT_NOTE_SOURCE_TYPE,
    StockResearchReportNoteConflict,
    StockResearchReportNoteError,
    StockResearchReportNoteNotFound,
    StockResearchReportNoteService,
)
from app_module.stock_research_report_snapshot_codec import (
    STOCK_RESEARCH_REPORT_PROJECTION_SNAPSHOT_SCHEMA_V1,
    create_stock_research_report_projection_snapshot,
)
from tests.test_stock_research_report_snapshot_codec import _report


def _snapshot():
    report, context = _report()
    return create_stock_research_report_projection_snapshot(report, context)


def _variant_snapshot():
    report, context = _report()
    features = dict(report.shared_daily_features)
    features["qa83_variant"] = "another exact report"
    return create_stock_research_report_projection_snapshot(
        replace(report, shared_daily_features=features), context
    )


def _journal_service(tmp_path: Path) -> tuple[JournalService, Any]:
    data_root = tmp_path / "FA_Data"
    paths = resolve_personal_journal_paths(
        data_root,
        personal_root=data_root / "personal",
    )
    config = SimpleNamespace(output_root=paths.personal_paths.legacy_output_root)
    return JournalService(config, journal_paths=paths), paths


def _reopen_journal(paths: Any, *, legacy_read_only: bool = False) -> JournalService:
    config = SimpleNamespace(output_root=paths.personal_paths.legacy_output_root)
    return JournalService(
        config,
        journal_paths=paths,
        legacy_read_only=legacy_read_only,
    )


def test_saved_report_note_reopens_with_full_canonical_report_context_and_original_text(
    tmp_path: Path,
) -> None:
    journal, paths = _journal_service(tmp_path)
    service = StockResearchReportNoteService(journal)
    report, context = _report()
    snapshot = create_stock_research_report_projection_snapshot(report, context)

    # 公開 DTO 的巢狀欄位可變；保存只能採信固定 canonical bytes 與 SHA。
    cast(dict[str, Any], snapshot.report.shared_daily_features)[
        "caller_mutation"
    ] = "must not be saved"
    original_text = "  保留首尾空白與原換行\n下一行照原文保存  "
    saved = service.save(
        snapshot,
        original_text,
        revision_id="report-note-first",
    )

    assert saved.text == original_text
    assert saved.revision_of is None
    assert saved.snapshot.identity_sha256 == snapshot.identity_sha256
    assert saved.snapshot.canonical_json == snapshot.canonical_json
    assert saved.snapshot.report == report
    assert saved.snapshot.context == context
    assert "caller_mutation" not in saved.snapshot.report.shared_daily_features

    revision = journal.list_decision_revisions()[0]
    identity = revision.decision_identity
    payload = revision.payload
    snapshot_payload = payload["stock_research_report_snapshot"]
    assert identity.stock_code == report.stock_code
    assert identity.result_id == ""
    assert identity.decision_date == ""
    assert identity.identity_status == IDENTITY_STATUS_UNKNOWN
    assert identity.source_snapshot_id == snapshot.identity_sha256
    assert identity.source_snapshot_hash == snapshot.identity_sha256
    assert payload["source_type"] == STOCK_RESEARCH_REPORT_NOTE_SOURCE_TYPE
    assert payload["source_id"] == snapshot.identity_sha256
    assert payload["source_snapshot_id"] == snapshot.identity_sha256
    assert payload["source_snapshot_hash"] == snapshot.identity_sha256
    assert payload["linked_type"] == "stock_research_report_projection"
    assert payload["linked_id"] == snapshot.identity_sha256
    assert payload["tags"] == ()
    assert set(snapshot_payload) == {
        "schema_version",
        "identity_sha256",
        "canonical_json",
    }
    assert snapshot_payload["schema_version"] == (
        STOCK_RESEARCH_REPORT_PROJECTION_SNAPSHOT_SCHEMA_V1
    )
    assert snapshot_payload["identity_sha256"] == snapshot.identity_sha256
    assert snapshot_payload["canonical_json"] == snapshot.canonical_json
    assert payload["body"] == original_text
    assert revision.note == original_text.strip()
    assert saved.recorded_at == revision.created_at
    assert payload["created_at"] == payload["updated_at"] == revision.created_at

    reopened = StockResearchReportNoteService(_reopen_journal(paths))
    assert reopened.get_note(saved.revision_id) == saved
    assert reopened.list_notes() == (saved,)
    assert reopened.read_exact(snapshot.identity_sha256).canonical_json == (
        snapshot.canonical_json
    )
    with pytest.raises(StockResearchReportNoteNotFound):
        reopened.read_exact("f" * 64)
    assert not list(tmp_path.rglob("trades.jsonl"))


def test_independent_roots_direct_parent_and_stale_or_cross_snapshot_parent_rejection(
    tmp_path: Path,
) -> None:
    journal, paths = _journal_service(tmp_path)
    service = StockResearchReportNoteService(journal)
    snapshot = _snapshot()
    other_snapshot = _variant_snapshot()

    first = service.save(snapshot, "第一篇原始判斷", revision_id="report-note-a1")
    direct_child = service.save(
        snapshot,
        "第一篇直接修訂",
        revision_id="report-note-a2",
        revision_of=first.revision_id,
    )
    independent = service.save(
        snapshot,
        "同報告的獨立根",
        revision_id="report-note-b1",
    )
    revisions = {item.revision_id: item for item in journal.list_decision_revisions()}
    assert revisions[first.revision_id].entity_id != revisions[independent.revision_id].entity_id
    assert revisions[direct_child.revision_id].entity_id == revisions[first.revision_id].entity_id
    assert revisions[direct_child.revision_id].revision_of == first.revision_id
    assert service.read_exact(snapshot.identity_sha256).canonical_json == snapshot.canonical_json
    before = paths.journal_file.read_bytes()

    with pytest.raises(StockResearchReportNoteConflict, match="current.*head"):
        service.save(
            snapshot,
            "不得沿舊父版分岔",
            revision_id="report-note-stale-child",
            revision_of=first.revision_id,
        )
    with pytest.raises(StockResearchReportNoteConflict, match="another exact report snapshot"):
        service.save(
            other_snapshot,
            "不得跨報告修訂",
            revision_id="report-note-cross-snapshot",
            revision_of=direct_child.revision_id,
        )
    with pytest.raises(StockResearchReportNoteConflict, match="differ"):
        service.save(
            snapshot,
            "不得自我當父版",
            revision_id="report-note-self-parent",
            revision_of="report-note-self-parent",
        )

    assert paths.journal_file.read_bytes() == before
    assert service.list_notes() == (first, direct_child, independent)
    assert StockResearchReportNoteService(_reopen_journal(paths)).get_note(
        direct_child.revision_id
    ).snapshot.context == snapshot.context


def test_idempotent_retry_does_not_append_and_same_id_different_text_is_refused(
    tmp_path: Path,
) -> None:
    journal, paths = _journal_service(tmp_path)
    service = StockResearchReportNoteService(journal)
    snapshot = _snapshot()
    saved = service.save(snapshot, "同一個精確請求", revision_id="report-note-retry")
    before = paths.journal_file.read_bytes()

    assert service.save(
        snapshot,
        "同一個精確請求",
        revision_id="report-note-retry",
    ) == saved
    assert paths.journal_file.read_bytes() == before
    with pytest.raises(StockResearchReportNoteConflict, match="different saved content"):
        service.save(
            snapshot,
            "改變原文不能覆寫",
            revision_id="report-note-retry",
        )
    with pytest.raises(StockResearchReportNoteConflict, match="different saved content"):
        service.save(
            _variant_snapshot(),
            "同 ID 不能換報告",
            revision_id="report-note-retry",
        )
    assert paths.journal_file.read_bytes() == before


@pytest.mark.parametrize(
    "tamper", ["snapshot_sha", "decision_identity", "same_source_payload"]
)
def test_tampered_report_note_hash_identity_or_same_source_payload_fails_closed(
    tmp_path: Path,
    tamper: str,
) -> None:
    journal, paths = _journal_service(tmp_path)
    service = StockResearchReportNoteService(journal)
    snapshot = _snapshot()
    saved = service.save(snapshot, "原始判斷", revision_id="report-note-tamper")
    record = json.loads(paths.journal_file.read_text(encoding="utf-8").splitlines()[0])
    if tamper == "snapshot_sha":
        record["payload"]["stock_research_report_snapshot"]["identity_sha256"] = "0" * 64
    elif tamper == "decision_identity":
        record["decision_identity"]["source_snapshot_id"] = "0" * 64
        record["decision_identity"]["source_snapshot_hash"] = "0" * 64
        record["source_snapshot_id"] = "0" * 64
        record["source_snapshot_hash"] = "0" * 64
    else:
        record["payload"].pop("stock_research_report_snapshot")
    paths.journal_file.write_text(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tampered_bytes = paths.journal_file.read_bytes()

    with pytest.raises(StockResearchReportNoteConflict):
        service.get_note(saved.revision_id)
    with pytest.raises(StockResearchReportNoteConflict):
        service.read_exact(snapshot.identity_sha256)
    assert paths.journal_file.read_bytes() == tampered_bytes


def test_report_note_parent_cycle_is_rejected_on_reopen_without_rewriting_journal(
    tmp_path: Path,
) -> None:
    journal, paths = _journal_service(tmp_path)
    service = StockResearchReportNoteService(journal)
    snapshot = _snapshot()
    root = service.save(snapshot, "第一版", revision_id="report-note-cycle-a")
    child = service.save(
        snapshot,
        "第二版",
        revision_id="report-note-cycle-b",
        revision_of=root.revision_id,
    )
    records = [
        json.loads(line)
        for line in paths.journal_file.read_text(encoding="utf-8").splitlines()
    ]
    records[0]["revision_of"] = child.revision_id
    paths.journal_file.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in records)
        + "\n",
        encoding="utf-8",
    )
    tampered_bytes = paths.journal_file.read_bytes()

    with pytest.raises(StockResearchReportNoteConflict):
        service.list_notes()
    assert paths.journal_file.read_bytes() == tampered_bytes


def test_competing_journal_append_cas_and_private_legacy_read_only_never_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal, paths = _journal_service(tmp_path)
    competitor = _reopen_journal(paths)
    service = StockResearchReportNoteService(journal)
    competitor_service = StockResearchReportNoteService(competitor)
    snapshot = _snapshot()
    original_record = journal.record_research_action
    winning_bytes: list[bytes] = []

    def append_after_competing_write(*args, **kwargs):
        competitor_service.save(
            snapshot,
            "先完成的 Journal 寫入",
            revision_id="report-note-cas-winner",
        )
        winning_bytes.append(paths.journal_file.read_bytes())
        return original_record(*args, **kwargs)

    monkeypatch.setattr(journal, "record_research_action", append_after_competing_write)
    with pytest.raises(StockResearchReportNoteConflict, match="journal append conflict"):
        service.save(
            snapshot,
            "過時 history token 不可覆寫",
            revision_id="report-note-cas-loser",
        )
    assert len(winning_bytes) == 1
    assert paths.journal_file.read_bytes() == winning_bytes[0]
    assert [note.revision_id for note in competitor_service.list_notes()] == [
        "report-note-cas-winner"
    ]

    read_only_journal = _reopen_journal(paths, legacy_read_only=True)
    read_only = StockResearchReportNoteService(read_only_journal)
    read_only_path = read_only_journal.store.journal_file
    before = read_only_path.read_bytes() if read_only_path.exists() else None
    with pytest.raises(StockResearchReportNoteError, match="read-only"):
        read_only.save(
            snapshot,
            "legacy readonly 不可寫入",
            revision_id="report-note-read-only",
        )
    after = read_only_path.read_bytes() if read_only_path.exists() else None
    assert after == before
    assert paths.journal_file.read_bytes() == winning_bytes[0]


def test_other_source_types_are_ignored_and_invalid_inputs_never_write(
    tmp_path: Path,
) -> None:
    journal, paths = _journal_service(tmp_path)
    token_history, token = journal.store.load_journal_snapshot()
    assert token_history == []
    journal.record_research_action(
        ACTION_NOTE,
        DecisionIdentity(
            stock_code="2317",
            identity_status=IDENTITY_STATUS_UNKNOWN,
        ),
        body="其他功能自己的筆記",
        note="其他功能自己的筆記",
        title="其他功能筆記",
        entity_id="other-source-note-root",
        journal_id="other-source-note-root",
        revision_id="other-source-note-1",
        continuity_event_id="other-source-note-1",
        source_type="another_feature_note.v1",
        expected_history_token=token,
    )
    service = StockResearchReportNoteService(journal)
    snapshot = _snapshot()
    before = paths.journal_file.read_bytes()

    assert service.list_notes() == ()
    with pytest.raises(StockResearchReportNoteNotFound):
        service.get_note("other-source-note-1")
    with pytest.raises(StockResearchReportNoteError):
        service.list_notes(stock_code=" 2330 ")
    bad_ids: tuple[Any, ...] = ("", " padded ", "x" * 257, 7)
    for bad_id in bad_ids:
        with pytest.raises(StockResearchReportNoteError):
            service.save(snapshot, "valid text", revision_id=bad_id)
    for bad_text in (" \t\n ", "x" * 8001):
        with pytest.raises(StockResearchReportNoteError):
            service.save(snapshot, bad_text, revision_id="invalid-report-note")

    assert paths.journal_file.read_bytes() == before
