"""CLI must use the verified current-monthly materialization path."""

from __future__ import annotations

from typing import NamedTuple
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

import pytest

from scripts import apply_current_monthly_snapshot as command
from data_module.monthly_revenue_snapshot_harvester import (
    _snapshot_source_version,
    parse_mops_monthly_revenue_snapshot_html,
    write_mops_snapshot_csv,
)


class _DiskUsage(NamedTuple):
    total: int
    used: int
    free: int


def _write_capture(root: Path, *, raw_html_dir: Path | None = None) -> tuple[Path, Path]:
    raw_dir = raw_html_dir or root / "raw_html"
    raw_dir.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now(timezone.utc).isoformat()
    headers = [
        "公司代號",
        "公司名稱",
        "當月營收",
        "上月營收",
        "去年當月營收",
        "當月累計營收",
        "去年累計營收",
    ]
    rows: list[dict[str, str]] = []
    for market, code, market_title in (
        ("twse", "2330", "上市"),
        ("tpex", "6488", "上櫃"),
    ):
        html = (
            f"<h1>{market_title}公司115年8月份</h1><p>單位：千元</p>"
            "<table><tr>"
            + "".join(f"<th>{header}</th>" for header in headers)
            + "</tr><tr>"
            + "".join(
                f"<td>{value}</td>"
                for value in (code, "公司", "1,234.5", "1,000", "900", "10,000", "9,000")
            )
            + "</tr></table>"
        )
        (raw_dir / f"{market}_2026-08.html").write_text(html, encoding="utf-8-sig")
        version = _snapshot_source_version(
            market=market,
            period="2026-08",
            html=html,
            captured_at=captured_at,
        )
        parsed, diagnostics = parse_mops_monthly_revenue_snapshot_html(
            html,
            market=market,
            period="2026-08",
            fetched_at=captured_at,
            source_version=version,
        )
        assert not diagnostics
        rows.extend(parsed)

    snapshot = root / "snapshot.csv"
    write_mops_snapshot_csv(snapshot, rows)
    return snapshot, raw_dir


def _args(snapshot: Path, root: Path, *, apply: bool = False) -> list[str]:
    values = [
        "--snapshot",
        str(snapshot),
        "--db-file",
        str(root / "data.sqlite"),
        "--backup-dir",
        str(root / "backups"),
        "--lock-path",
        str(root / "heavy.lock"),
        "--evidence-file",
        str(root / "evidence.json"),
    ]
    return values + (["--apply"] if apply else [])


def test_apply_cli_blocks_when_verified_raw_html_is_missing(tmp_path: Path) -> None:
    snapshot, raw_dir = _write_capture(tmp_path / "capture")
    (raw_dir / "twse_2026-08.html").unlink()
    args = _args(snapshot, tmp_path, apply=True)

    assert command.main(args) == 2
    evidence = json.loads((tmp_path / "evidence.json").read_text(encoding="utf-8"))
    assert evidence["status"] == "blocked"
    assert evidence["database_written"] is False
    assert evidence["formal_pit_eligible"] is False
    assert "twse_2026-08.html" in evidence["reason"]
    assert not (tmp_path / "data.sqlite").exists()
    assert not (tmp_path / "backups").exists()


def test_preview_accepts_explicit_raw_directory_and_reports_comparators(
    tmp_path: Path,
) -> None:
    raw_dir = tmp_path / "separate-source-custody"
    snapshot, raw_dir = _write_capture(tmp_path / "capture", raw_html_dir=raw_dir)
    raw_before = {
        path.name: path.read_bytes() for path in raw_dir.glob("*.html")
    }
    args = _args(snapshot, tmp_path)
    args.extend(["--raw-html-dir", str(raw_dir)])

    assert command.main(args) == 0
    evidence = json.loads((tmp_path / "evidence.json").read_text(encoding="utf-8"))
    assert evidence["status"] == "preview"
    assert evidence["rows"] == 2
    assert evidence["normalized_record_count"] == 4
    assert evidence["same_report_yoy_comparator_count"] == 2
    assert evidence["formal_pit_eligible"] is False
    assert evidence["formal_monthly_table_written"] is False
    assert evidence["database_written"] is False
    assert {path.name: path.read_bytes() for path in raw_dir.glob("*.html")} == raw_before
    assert not (tmp_path / "data.sqlite").exists()


def test_apply_cli_persists_verified_current_and_comparator_rows_only(
    tmp_path: Path, monkeypatch,
) -> None:
    snapshot, raw_dir = _write_capture(tmp_path / "capture")
    raw_before = {path.name: path.read_bytes() for path in raw_dir.glob("*.html")}
    database = tmp_path / "data.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE fundamental_monthly_revenues (sentinel TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO fundamental_monthly_revenues VALUES ('existing-formal-row')"
        )

    monkeypatch.setattr(
        command.shutil,
        "disk_usage",
        lambda _path: _DiskUsage(500 * 1024**3, 1, 400 * 1024**3),
    )
    reservations: list[object] = []
    monkeypatch.setattr(command, "acquire_heavy_chain_reservation", lambda _path: "held")
    monkeypatch.setattr(
        command,
        "release_heavy_chain_reservation",
        lambda token: reservations.append(token),
    )

    assert command.main(_args(snapshot, tmp_path, apply=True)) == 0
    evidence = json.loads((tmp_path / "evidence.json").read_text(encoding="utf-8"))
    assert evidence["status"] == "applied"
    assert evidence["inserted_count"] == 4
    assert evidence["same_report_yoy_comparator_count"] == 2
    assert evidence["formal_pit_eligible"] is False
    assert evidence["formal_monthly_table_written"] is False
    assert Path(evidence["backup_file"]).is_file()
    assert Path(evidence["receipt_file"]).is_file()
    assert reservations == ["held"]
    assert {path.name: path.read_bytes() for path in raw_dir.glob("*.html")} == raw_before

    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT * FROM fundamental_monthly_revenues"
        ).fetchall() == [("existing-formal-row",)]
        rows = connection.execute(
            "SELECT item_code,period,value,unit,period_basis,basis_verified,"
            "aggregate_feature_eligible,source_available_at "
            "FROM fundamental_current_observations ORDER BY item_code,stock_code"
        ).fetchall()
    assert len(rows) == 4
    assert sum(row[0] == "revenue" for row in rows) == 2
    assert sum(row[0] == "revenue_yoy_comparator" for row in rows) == 2
    assert all(row[3:7] == ("TWD", "monthly_flow", 1, 0) for row in rows)
    assert all(row[7] is not None for row in rows)


def test_apply_exception_does_not_claim_database_was_unchanged(
    tmp_path: Path, monkeypatch,
) -> None:
    snapshot, _raw_dir = _write_capture(tmp_path / "capture")
    database = tmp_path / "data.sqlite"
    sqlite3.connect(database).close()
    monkeypatch.setattr(
        command.shutil,
        "disk_usage",
        lambda _path: _DiskUsage(500 * 1024**3, 1, 400 * 1024**3),
    )
    released: list[object] = []
    monkeypatch.setattr(command, "acquire_heavy_chain_reservation", lambda _path: "held")
    monkeypatch.setattr(
        command,
        "release_heavy_chain_reservation",
        lambda token: released.append(token),
    )

    def fail_after_entering_apply(*_args, **_kwargs):
        raise RuntimeError("synthetic uncertain apply failure")

    monkeypatch.setattr(command, "apply_current_revenue", fail_after_entering_apply)
    assert command.main(_args(snapshot, tmp_path, apply=True)) == 2
    evidence = json.loads((tmp_path / "evidence.json").read_text(encoding="utf-8"))
    assert evidence["status"] == "apply_failed_readback_required"
    assert evidence["database_written"] is None
    assert "unknown" in evidence["database_write_outcome"]
    assert released == ["held"]


@pytest.mark.parametrize(
    "collision_target", ("snapshot", "raw_html", "database", "raw_dir", "raw_child")
)
def test_evidence_path_collision_is_rejected_before_any_write_and_preserves_inputs(
    tmp_path: Path,
    monkeypatch,
    capsys,
    collision_target: str,
) -> None:
    snapshot, raw_dir = _write_capture(tmp_path / "capture")
    database = tmp_path / "data.sqlite"
    database.write_bytes(b"protected database bytes\x00\x01")
    raw_html = raw_dir / "twse_2026-08.html"
    original_bytes = {
        snapshot: snapshot.read_bytes(),
        raw_html: raw_html.read_bytes(),
        database: database.read_bytes(),
    }
    target = {
        "snapshot": snapshot,
        "raw_html": raw_html,
        "database": database,
        "raw_dir": raw_dir,
        "raw_child": raw_dir / "would-overwrite-custody.json",
    }[collision_target]
    args = _args(snapshot, tmp_path)
    args[args.index("--db-file") + 1] = str(database)
    args[args.index("--evidence-file") + 1] = str(target)

    def forbidden_plan(*_args, **_kwargs):
        raise AssertionError("collision guard must run before source planning")

    monkeypatch.setattr(command, "plan_current_revenue", forbidden_plan)

    assert command.main(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "blocked"
    assert result["database_written"] is False
    assert result["evidence_written"] is False
    assert "evidence destination" in result["reason"]
    assert {path: path.read_bytes() for path in original_bytes} == original_bytes
    if collision_target == "raw_child":
        assert not target.exists()
