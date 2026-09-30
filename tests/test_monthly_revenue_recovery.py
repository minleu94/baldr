from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import data_module.monthly_revenue_recovery as recovery_module
from data_module import monthly_revenue_research_candidate as candidate_module
from data_module.fundamental_schema import apply_fundamental_schema
from data_module.monthly_revenue_recovery import apply_monthly_revenue_recovery
from data_module.monthly_revenue_availability_history import OFFICIAL_OPENAPI_URLS
from scripts import apply_monthly_revenue_recovery as recovery_cli


_HEADER = (
    "stock_code,period,as_of_date,announced_date,available_date,source,source_version,"
    "availability_contract_version,evidence_class,source_hash,revision,parent_revision\n"
)


def _write_mapping(path) -> None:
    path.write_text(
        _HEADER
        + (
            "2330,2026-05,2026-05-31,2026-06-10,2026-06-11,"
            "manual.twse_monthly_revenue_announcement_log,announcement-v1,"
            "formal-availability.v2,official_announcement,sha256:"
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,1,\n"
        ),
        encoding="utf-8-sig",
    )


def _write_snapshot(path) -> None:
    path.write_text(
        "market,period,stock_code,company_name,current_month_revenue,"
        "previous_month_revenue,previous_year_month_revenue,mom_pct,yoy_pct,"
        "cumulative_revenue,previous_year_cumulative_revenue,cumulative_yoy_pct,"
        "note,fetched_at,source,source_version\n"
        "twse,2026-05,2330,測試公司,320000000000,300000000000,250000000000,"
        "6.67,28.0,1500000000000,1200000000000,25.0,,"
        "2026-06-10T08:00:00Z,mops.monthly_revenue_static_snapshot,"
        "mops-static-twse-2026-05-sha256-"
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n",
        encoding="utf-8-sig",
    )


def _write_partial_manifest(path, *, candidate_file, accepted_file) -> None:
    accepted_keys = {"2330|2026-05"}
    excluded_keys = ["2317|2026-05"]
    candidate_keys = accepted_keys | set(excluded_keys)
    key_digest = lambda keys: hashlib.sha256(
        "\n".join(sorted(keys)).encode("utf-8")
    ).hexdigest()
    path.write_text(
        json.dumps(
            {
                "candidate_file": str(candidate_file),
                "candidate_rows": 2,
                "mapping_rows": 1,
                "accepted_rows": 1,
                "excluded_rows": 1,
                "excluded_keys": excluded_keys,
                "candidate_file_sha256": hashlib.sha256(
                    candidate_file.read_bytes()
                ).hexdigest(),
                "accepted_file_sha256": hashlib.sha256(
                    accepted_file.read_bytes()
                ).hexdigest(),
                "candidate_key_sha256": key_digest(candidate_keys),
                "accepted_key_sha256": key_digest(accepted_keys),
                "excluded_key_sha256": key_digest(set(excluded_keys)),
            }
        ),
        encoding="utf-8",
    )


def _prepare(tmp_path):
    candidate_mapping = tmp_path / "candidate_mapping.csv"
    _write_mapping(candidate_mapping)
    target_mapping = tmp_path / "monthly_revenue_availability.csv"
    target_mapping.write_text(_HEADER, encoding="utf-8-sig")
    snapshot = tmp_path / "accepted_scope.csv"
    _write_snapshot(snapshot)
    candidate = tmp_path / "full_candidate.csv"
    candidate.write_bytes(snapshot.read_bytes())
    with candidate.open("a", encoding="utf-8") as handle:
        handle.write(
            "twse,2026-05,2317,鴻海,100,90,80,1.0,2.0,500,450,3.0,,"
            "2026-06-11T00:00:00Z,mops.monthly_revenue_static_snapshot,"
            "mops-static-twse-2026-05-sha256-"
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        )
    manifest = tmp_path / "scope_manifest.json"
    _write_partial_manifest(
        manifest,
        candidate_file=candidate,
        accepted_file=snapshot,
    )
    db_file = tmp_path / "twstock.db"
    with closing(sqlite3.connect(db_file)) as conn:
        apply_fundamental_schema(conn)
    return candidate_mapping, target_mapping, snapshot, manifest, db_file


def _make_research_candidate(tmp_path, monkeypatch):
    monkeypatch.setattr(candidate_module, "REPO_ROOT", tmp_path)
    taipei_now = datetime.now(ZoneInfo("Asia/Taipei"))
    if taipei_now.month == 1:
        period_year, period_month = taipei_now.year - 1, 12
    else:
        period_year, period_month = taipei_now.year, taipei_now.month - 1
    period = f"{period_year - 1911:03d}{period_month:02d}"
    announcement_date = taipei_now.date() - timedelta(days=1)
    announcement = (
        f"{announcement_date.year - 1911:03d}"
        f"{announcement_date.month:02d}{announcement_date.day:02d}"
    )

    def source_row(stock_code):
        return {
            "出表日期": announcement,
            "資料年月": period,
            "公司代號": stock_code,
            "公司名稱": f"測試公司{stock_code}",
            "營業收入-當月營收": "1000",
            "營業收入-上月營收": "900",
            "營業收入-去年當月營收": "800",
            "營業收入-上月比較增減(%)": "11.11",
            "營業收入-去年同月增減(%)": "25.00",
            "累計營業收入-當月累計營收": "7000",
            "累計營業收入-去年累計營收": "6000",
            "累計營業收入-前期比較增減(%)": "16.66",
            "備註": "-",
        }

    class Response:
        def __init__(self, url, body):
            self._url = url
            self._body = BytesIO(body)
            self.status = 200
            self.headers = {"Content-Type": "application/json; charset=utf-8"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self._body.close()

        def geturl(self):
            return self._url

        def read(self, size=-1):
            return self._body.read(size)

    def opener(request, *, timeout):
        assert timeout == candidate_module.REQUEST_TIMEOUT_SECONDS
        venue = next(
            name
            for name, url in OFFICIAL_OPENAPI_URLS.items()
            if url == request.full_url
        )
        code = "2330" if venue == "twse" else "6488"
        body = json.dumps([source_row(code)], ensure_ascii=False).encode("utf-8")
        return Response(request.full_url, body)

    result = candidate_module._capture_monthly_revenue_research_candidate(
        candidate_parent=tmp_path / "research_candidates",
        opener=opener,
        disk_usage=lambda _path: SimpleNamespace(free=64 * 1024 * 1024),
    )
    assert result["status"] == "captured"
    run_root = Path(result["run_root"])
    candidate_manifest = json.loads(
        (run_root / "candidate_manifest.json").read_text(encoding="utf-8")
    )
    return (
        run_root / candidate_manifest["availability_file"],
        run_root / candidate_manifest["candidate_file"],
        run_root / candidate_manifest["scope_manifest_file"],
    )


def test_monthly_revenue_recovery_applies_explicit_partial_scope_atomically(
    tmp_path,
):
    (
        candidate_mapping,
        target_mapping,
        snapshot,
        manifest,
        db_file,
    ) = _prepare(tmp_path)
    backup_dir = tmp_path / "task_backup"
    backup_dir.mkdir()
    sentinel = backup_dir / "keep-existing.backup"
    sentinel.write_text("keep", encoding="utf-8")
    evidence_file = tmp_path / "recovery_evidence.json"

    result = apply_monthly_revenue_recovery(
        candidate_mapping_file=candidate_mapping,
        snapshot_file=snapshot,
        scope_manifest_file=manifest,
        target_mapping_file=target_mapping,
        db_file=db_file,
        backup_dir=backup_dir,
        evidence_file=evidence_file,
        source_version="mops-static-capture-2026-09-07T07:17:53Z",
    )

    assert result.applied is True
    assert result.rolled_back is False
    assert result.plan.backfill_plan.snapshot_scope == "partial"
    assert result.plan.backfill_plan.full_snapshot_row_count == 2
    assert result.plan.backfill_plan.raw_row_count == 1
    assert sentinel.exists()
    assert result.mapping_backup_file is not None
    assert result.db_backup_file is not None
    with closing(sqlite3.connect(db_file)) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM fundamental_monthly_revenues"
        ).fetchone() == (1,)
    assert json.loads(evidence_file.read_text(encoding="utf-8"))["status"] == "applied"
    assert len(list(backup_dir.glob("*.db"))) == 1
    assert len(list(backup_dir.glob("*.csv"))) == 1


def test_monthly_revenue_recovery_rejects_research_candidate_before_any_writes(
    tmp_path, monkeypatch, capsys
):
    candidate_mapping, snapshot, scope_manifest = _make_research_candidate(
        tmp_path,
        monkeypatch,
    )
    _legacy_candidate, target_mapping, _legacy_snapshot, _legacy_manifest, db_file = (
        _prepare(tmp_path)
    )
    backup_dir = tmp_path / "research_apply_backups"
    evidence_file = tmp_path / "research_apply_evidence.json"
    journal_file = tmp_path / "research_apply_journal.json"
    before_mapping = target_mapping.read_bytes()
    before_db = hashlib.sha256(db_file.read_bytes()).hexdigest()

    def forbidden_side_effect(*_args, **_kwargs):
        pytest.fail("research-only recovery must stop before apply-side effects")

    monkeypatch.setattr(recovery_module.sqlite3, "connect", forbidden_side_effect)
    monkeypatch.setattr(
        recovery_module,
        "reserve_monthly_revenue_mapping_backup_path",
        forbidden_side_effect,
    )
    monkeypatch.setattr(
        recovery_module,
        "reserve_monthly_revenue_sqlite_backup_path",
        forbidden_side_effect,
    )
    monkeypatch.setattr(
        recovery_module,
        "_write_recovery_journal",
        forbidden_side_effect,
    )
    monkeypatch.setattr(
        recovery_module,
        "_write_recovery_evidence",
        forbidden_side_effect,
    )

    exit_code = recovery_cli.main(
        [
            "--candidate-mapping",
            str(candidate_mapping),
            "--snapshot-file",
            str(snapshot),
            "--scope-manifest",
            str(scope_manifest),
            "--target-mapping",
            str(target_mapping),
            "--db-file",
            str(db_file),
            "--backup-dir",
            str(backup_dir),
            "--evidence-file",
            str(evidence_file),
            "--journal-file",
            str(journal_file),
            "--source-version",
            "research-candidate-test",
            "--apply",
            "--confirm",
            "apply-monthly-revenue-recovery",
            "--format",
            "json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["status"] == "failed"
    assert payload["ready_for_apply"] is True
    assert payload["formal_apply_eligible"] is False
    assert "hash-bound formal source/unit acceptance receipt" in (
        payload["formal_apply_blocked_reason"]
    )
    assert target_mapping.read_bytes() == before_mapping
    assert hashlib.sha256(db_file.read_bytes()).hexdigest() == before_db
    assert backup_dir.exists() is False
    assert evidence_file.exists() is False
    assert journal_file.exists() is False


def test_monthly_revenue_recovery_restores_mapping_when_db_stage_fails(
    tmp_path,
    monkeypatch,
):
    (
        candidate_mapping,
        target_mapping,
        snapshot,
        manifest,
        db_file,
    ) = _prepare(tmp_path)
    before_mapping = target_mapping.read_bytes()
    backup_dir = tmp_path / "task_backup"
    evidence_file = tmp_path / "recovery_evidence.json"

    def _fail_db_stage(**_kwargs):
        raise RuntimeError("injected database stage failure")

    monkeypatch.setattr(
        recovery_module,
        "apply_mops_snapshot_monthly_revenue_backfill",
        _fail_db_stage,
    )

    result = apply_monthly_revenue_recovery(
        candidate_mapping_file=candidate_mapping,
        snapshot_file=snapshot,
        scope_manifest_file=manifest,
        target_mapping_file=target_mapping,
        db_file=db_file,
        backup_dir=backup_dir,
        evidence_file=evidence_file,
        source_version="mops-static-capture-2026-09-07T07:17:53Z",
    )

    assert result.applied is False
    assert result.rolled_back is True
    assert result.error == (
        "RuntimeError: injected database stage failure"
    )
    assert target_mapping.read_bytes() == before_mapping
    with closing(sqlite3.connect(db_file)) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM fundamental_monthly_revenues"
        ).fetchone() == (0,)
    evidence = json.loads(evidence_file.read_text(encoding="utf-8"))
    assert evidence["status"] == "rolled_back"
    assert evidence["rollback"] == {"attempted": True, "succeeded": True}
    assert len(list(backup_dir.glob("*.csv"))) == 1


def test_monthly_revenue_recovery_crash_after_mapping_is_retryable(
    tmp_path,
    monkeypatch,
):
    candidate_mapping, target_mapping, snapshot, manifest, db_file = _prepare(tmp_path)
    backup_dir = tmp_path / "task_backup"
    evidence_file = tmp_path / "recovery_evidence.json"
    real_write_journal = recovery_module._write_recovery_journal

    def _crash_before_mapping_phase_journal(path, payload):
        if payload.get("state") == "mapping_applied":
            raise SystemExit("simulated process termination")
        real_write_journal(path, payload)

    monkeypatch.setattr(
        recovery_module,
        "_write_recovery_journal",
        _crash_before_mapping_phase_journal,
    )
    with pytest.raises(SystemExit, match="simulated process termination"):
        apply_monthly_revenue_recovery(
            candidate_mapping_file=candidate_mapping,
            snapshot_file=snapshot,
            scope_manifest_file=manifest,
            target_mapping_file=target_mapping,
            db_file=db_file,
            backup_dir=backup_dir,
            evidence_file=evidence_file,
            source_version="mops-static-capture-2026-09-07T07:17:53Z",
        )

    journal_file = evidence_file.with_suffix(".json.journal.json")
    journal = json.loads(journal_file.read_text(encoding="utf-8"))
    assert journal["state"] == "prepared"
    assert journal["mapping_backup_file"]
    assert "2330,2026-05" in target_mapping.read_text(encoding="utf-8-sig")
    with closing(sqlite3.connect(db_file)) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM fundamental_monthly_revenues"
        ).fetchone() == (0,)

    monkeypatch.setattr(recovery_module, "_write_recovery_journal", real_write_journal)
    result = apply_monthly_revenue_recovery(
        candidate_mapping_file=candidate_mapping,
        snapshot_file=snapshot,
        scope_manifest_file=manifest,
        target_mapping_file=target_mapping,
        db_file=db_file,
        backup_dir=backup_dir,
        evidence_file=evidence_file,
        source_version="mops-static-capture-2026-09-07T07:17:53Z",
    )

    assert result.applied is True
    assert result.rolled_back is False
    assert json.loads(journal_file.read_text(encoding="utf-8"))["state"] == "completed"
    with closing(sqlite3.connect(db_file)) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM fundamental_monthly_revenues"
        ).fetchone() == (1,)


def test_monthly_revenue_recovery_does_not_restore_mapping_after_db_commit_journal_error(
    tmp_path,
    monkeypatch,
):
    candidate_mapping, target_mapping, snapshot, manifest, db_file = _prepare(tmp_path)
    backup_dir = tmp_path / "task_backup"
    evidence_file = tmp_path / "recovery_evidence.json"
    real_write_journal = recovery_module._write_recovery_journal

    def _fail_db_committed_journal(path, payload):
        if payload.get("state") == "db_committed":
            raise RuntimeError("injected db committed journal failure")
        real_write_journal(path, payload)

    monkeypatch.setattr(
        recovery_module,
        "_write_recovery_journal",
        _fail_db_committed_journal,
    )
    result = apply_monthly_revenue_recovery(
        candidate_mapping_file=candidate_mapping,
        snapshot_file=snapshot,
        scope_manifest_file=manifest,
        target_mapping_file=target_mapping,
        db_file=db_file,
        backup_dir=backup_dir,
        evidence_file=evidence_file,
        source_version="mops-static-capture-2026-09-07T07:17:53Z",
    )

    assert result.applied is False
    assert result.rolled_back is False
    assert result.commit_observed_after_error is True
    assert "injected db committed journal failure" in (result.error or "")
    assert "2026-05-31" in target_mapping.read_text(encoding="utf-8-sig")
    with closing(sqlite3.connect(db_file)) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM fundamental_monthly_revenues"
        ).fetchone() == (1,)
    evidence = json.loads(evidence_file.read_text(encoding="utf-8"))
    assert evidence["status"] == "db_committed_needs_review"
    journal_file = evidence_file.with_suffix(".json.journal.json")
    assert json.loads(journal_file.read_text(encoding="utf-8"))["state"] == (
        "db_committed_needs_review"
    )


def test_monthly_revenue_recovery_journals_evidence_failure_after_db_commit(
    tmp_path,
    monkeypatch,
):
    candidate_mapping, target_mapping, snapshot, manifest, db_file = _prepare(tmp_path)
    backup_dir = tmp_path / "task_backup"
    evidence_file = tmp_path / "recovery_evidence.json"

    def _fail_evidence(*_args, **_kwargs):
        raise RuntimeError("injected evidence failure")

    monkeypatch.setattr(recovery_module, "_write_recovery_evidence", _fail_evidence)
    with pytest.raises(RuntimeError, match="injected evidence failure"):
        apply_monthly_revenue_recovery(
            candidate_mapping_file=candidate_mapping,
            snapshot_file=snapshot,
            scope_manifest_file=manifest,
            target_mapping_file=target_mapping,
            db_file=db_file,
            backup_dir=backup_dir,
            evidence_file=evidence_file,
            source_version="mops-static-capture-2026-09-07T07:17:53Z",
        )

    journal_file = evidence_file.with_suffix(".json.journal.json")
    journal = json.loads(journal_file.read_text(encoding="utf-8"))
    assert journal["state"] == "db_committed_evidence_pending"
    with closing(sqlite3.connect(db_file)) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM fundamental_monthly_revenues"
        ).fetchone() == (1,)

    monkeypatch.setattr(recovery_module, "_write_recovery_evidence", recovery_module._write_json_atomic)
    result = apply_monthly_revenue_recovery(
        candidate_mapping_file=candidate_mapping,
        snapshot_file=snapshot,
        scope_manifest_file=manifest,
        target_mapping_file=target_mapping,
        db_file=db_file,
        backup_dir=backup_dir,
        evidence_file=evidence_file,
        source_version="mops-static-capture-2026-09-07T07:17:53Z",
    )
    assert result.applied is True
    assert json.loads(journal_file.read_text(encoding="utf-8"))["state"] == "completed"


def test_monthly_revenue_recovery_keeps_concurrent_mapping_writer_on_compensation(
    tmp_path,
    monkeypatch,
):
    candidate_mapping, target_mapping, snapshot, manifest, db_file = _prepare(tmp_path)
    backup_dir = tmp_path / "task_backup"
    evidence_file = tmp_path / "recovery_evidence.json"

    def _concurrent_writer_then_fail(**_kwargs):
        with target_mapping.open("a", encoding="utf-8") as handle:
            handle.write(
                "2317,2026-05,2026-05-31,2026-06-12,2026-06-13,"
                "manual.twse_monthly_revenue_announcement_log,concurrent-v1,"
                "formal-availability.v2,official_announcement,sha256:"
                "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb,1,\n"
            )
        raise RuntimeError("injected database stage failure")

    monkeypatch.setattr(
        recovery_module,
        "apply_mops_snapshot_monthly_revenue_backfill",
        _concurrent_writer_then_fail,
    )
    result = apply_monthly_revenue_recovery(
        candidate_mapping_file=candidate_mapping,
        snapshot_file=snapshot,
        scope_manifest_file=manifest,
        target_mapping_file=target_mapping,
        db_file=db_file,
        backup_dir=backup_dir,
        evidence_file=evidence_file,
        source_version="mops-static-capture-2026-09-07T07:17:53Z",
    )

    assert result.applied is False
    assert result.rolled_back is False
    assert "mapping restore failed" in (result.error or "")
    assert "2317,2026-05" in target_mapping.read_text(encoding="utf-8-sig")
    with closing(sqlite3.connect(db_file)) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM fundamental_monthly_revenues"
        ).fetchone() == (0,)


def test_monthly_revenue_recovery_does_not_reuse_journal_for_new_inputs(
    tmp_path,
    monkeypatch,
):
    candidate_mapping, target_mapping, snapshot, manifest, db_file = _prepare(tmp_path)
    backup_dir = tmp_path / "task_backup"
    evidence_file = tmp_path / "recovery_evidence.json"
    real_write_journal = recovery_module._write_recovery_journal

    def _crash_after_mapping(path, payload):
        if payload.get("state") == "mapping_applied":
            raise SystemExit("simulated process termination")
        real_write_journal(path, payload)

    monkeypatch.setattr(
        recovery_module,
        "_write_recovery_journal",
        _crash_after_mapping,
    )
    with pytest.raises(SystemExit, match="simulated process termination"):
        apply_monthly_revenue_recovery(
            candidate_mapping_file=candidate_mapping,
            snapshot_file=snapshot,
            scope_manifest_file=manifest,
            target_mapping_file=target_mapping,
            db_file=db_file,
            backup_dir=backup_dir,
            evidence_file=evidence_file,
            source_version="mops-static-capture-2026-09-07T07:17:53Z",
        )

    journal_file = evidence_file.with_suffix(".json.journal.json")
    first_journal = json.loads(journal_file.read_text(encoding="utf-8"))
    old_mapping_backup = first_journal["mapping_backup_file"]
    assert old_mapping_backup
    assert first_journal["state"] == "prepared"

    candidate_mapping_b = tmp_path / "candidate_mapping_b.csv"
    candidate_mapping_b.write_bytes(candidate_mapping.read_bytes())
    with candidate_mapping_b.open("a", encoding="utf-8") as handle:
        handle.write(
            "2317,2026-05,2026-05-31,2026-06-12,2026-06-13,"
            "manual.twse_monthly_revenue_announcement_log,candidate-b,"
            "formal-availability.v2,official_announcement,sha256:"
            "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc,1,\n"
        )
    snapshot_b = tmp_path / "accepted_scope_b.csv"
    snapshot_b.write_bytes(snapshot.read_bytes() + b"\n")
    manifest_b = tmp_path / "scope_manifest_b.json"
    _write_partial_manifest(
        manifest_b,
        candidate_file=tmp_path / "full_candidate.csv",
        accepted_file=snapshot_b,
    )
    db_file_b = tmp_path / "twstock_b.db"
    with closing(sqlite3.connect(db_file_b)) as conn:
        apply_fundamental_schema(conn)

    monkeypatch.setattr(recovery_module, "_write_recovery_journal", real_write_journal)

    def _fail_new_db_stage(**_kwargs):
        raise RuntimeError("new database stage failure")

    monkeypatch.setattr(
        recovery_module,
        "apply_mops_snapshot_monthly_revenue_backfill",
        _fail_new_db_stage,
    )
    result = apply_monthly_revenue_recovery(
        candidate_mapping_file=candidate_mapping_b,
        snapshot_file=snapshot_b,
        scope_manifest_file=manifest_b,
        target_mapping_file=target_mapping,
        db_file=db_file_b,
        backup_dir=backup_dir,
        evidence_file=evidence_file,
        source_version="mops-static-capture-2026-09-07T07:17:53Z",
    )

    assert result.applied is False
    assert result.rolled_back is True
    assert result.mapping_backup_file is not None
    assert str(result.mapping_backup_file) != old_mapping_backup
    target_text = target_mapping.read_text(encoding="utf-8-sig")
    assert "2330,2026-05" in target_text
    assert "2317,2026-05" not in target_text
    journal = json.loads(journal_file.read_text(encoding="utf-8"))
    assert journal["previous_journal_identity_match"] is False
    assert journal["previous_journal_ignored"] is True
    assert journal["recovery_of"] is None
