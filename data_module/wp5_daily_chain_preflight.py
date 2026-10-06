"""Read-only path and seed preflight for an isolated WP5 daily QA run.

This module deliberately does not import ``TWStockConfig`` or either scheduled
runner.  It never creates directories, status files, logs, receipts, or SQLite
tables.  A successful seed-integrity result only attests the pinned QA copy;
day execution remains blocked until official temporary-closure coverage and a
supported same-day official source-time receipt are available.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from typing import Any
from zoneinfo import ZoneInfo


BOOTSTRAP_SCHEMA = "wp5-isolated-qa-sqlite-bootstrap.v1"
UPSTREAM_SNAPSHOT_SCHEMA = "formal-sqlite-source-snapshot.v1"
PREFLIGHT_SCHEMA = "wp5-qa-root-read-only-preflight.v1"
PERSONAL_ACTIVITY_SCHEMA = "wp5-personal-current-observed-activity.v1"
REPARSE_POINT_ATTRIBUTE = 0x400
MAX_RECEIPT_BYTES = 2 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PIT_PATH_ENV_NAMES = (
    "PIT_SECTOR_MEMBERSHIP_PATH",
    "PIT_SECTOR_MEMBERSHIP_RAW_ROOT",
    "PIT_SECTOR_MEMBERSHIP_CLOCK_MANIFEST_PATH",
    "PIT_SECTOR_MEMBERSHIP_UNIVERSE_SYMBOLS_PATH",
    "PIT_SECTOR_MEMBERSHIP_UNIVERSE_IDENTITY_PATH",
    "PIT_SECTOR_MEMBERSHIP_TAXONOMY_IDENTITY_PATH",
)
SQLITE_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")
TAIPEI = ZoneInfo("Asia/Taipei")
OBSERVED_CLOCK_SKEW_SECONDS = 30
MAX_OBSERVED_AGE_SECONDS = 300


@dataclass(frozen=True)
class PreflightConfig:
    """Explicit inputs needed to inspect one QA root without mutating it."""

    qa_root: Path
    decision_date: date
    observed_at: datetime
    expected_bootstrap_receipt_sha256: str
    expected_working_db_sha256: str
    expected_snapshot_receipt_sha256: str
    calendar_cache_path: Path | None = None
    temporary_closure_path: Path | None = None
    source_time_receipt_path: Path | None = None
    skip_candidate_update: bool = False
    repo_root: Path | None = None


class _PreflightError(ValueError):
    """A local validation error converted into a stable JSON blocker."""


def _is_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    attributes = int(getattr(info, "st_file_attributes", 0))
    return stat.S_ISLNK(info.st_mode) or bool(
        attributes & REPARSE_POINT_ATTRIBUTE
    )


def _assert_no_reparse_chain(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    chain: list[Path] = []
    cursor = absolute
    while True:
        chain.append(cursor)
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    for component in reversed(chain):
        if _is_reparse_point(component):
            raise _PreflightError(f"reparse_component:{component}")


def _contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _reject_parent_traversal(path: Path) -> None:
    if ".." in path.parts:
        raise _PreflightError("path_contains_parent_traversal")


def _existing_path(
    value: str | Path,
    *,
    label: str,
    allowed_root: Path | None = None,
    expect_file: bool | None = None,
) -> Path:
    path = Path(value).expanduser()
    _reject_parent_traversal(path)
    if not path.is_absolute():
        raise _PreflightError(f"{label}_must_be_absolute")
    _assert_no_reparse_chain(path)
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise _PreflightError(f"{label}_missing_or_unresolvable") from error
    if allowed_root is not None:
        root = allowed_root.resolve(strict=True)
        if not _contains(root, resolved):
            raise _PreflightError(f"{label}_outside_allowed_root")
    if expect_file is True and not resolved.is_file():
        raise _PreflightError(f"{label}_not_regular_file")
    if expect_file is False and not resolved.is_dir():
        raise _PreflightError(f"{label}_not_directory")
    return resolved


def _single_link_identity_from_stat(
    info: os.stat_result,
    *,
    label: str,
) -> tuple[int, int, int, int, int]:
    device = getattr(info, "st_dev", None)
    inode = getattr(info, "st_ino", None)
    link_count = getattr(info, "st_nlink", None)
    size = getattr(info, "st_size", None)
    mtime_ns = getattr(info, "st_mtime_ns", None)
    if (
        type(device) is not int
        or device < 0
        or type(inode) is not int
        or inode <= 0
        or type(link_count) is not int
        or link_count <= 0
        or type(size) is not int
        or size < 0
        or type(mtime_ns) is not int
    ):
        raise _PreflightError(f"{label}_file_identity_missing_or_invalid")
    if link_count != 1:
        raise _PreflightError(f"{label}_link_count_not_one:{link_count}")
    return device, inode, link_count, size, mtime_ns


def _single_link_identity(path: Path, *, label: str) -> tuple[int, int, int, int, int]:
    info = path.lstat()
    if _is_reparse_point(path) or not stat.S_ISREG(info.st_mode):
        raise _PreflightError(f"{label}_not_regular_non_reparse_file")
    return _single_link_identity_from_stat(info, label=label)


def _sha256_file(
    path: Path,
    *,
    require_single_link_label: str | None = None,
) -> tuple[str, int, int]:
    before = path.lstat()
    if _is_reparse_point(path) or not stat.S_ISREG(before.st_mode):
        raise _PreflightError("sha256_input_not_regular_file")
    before_identity = (
        None
        if require_single_link_label is None
        else _single_link_identity_from_stat(
            before,
            label=require_single_link_label,
        )
    )
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        opened_identity = (
            None
            if require_single_link_label is None
            else _single_link_identity_from_stat(
                os.fstat(stream.fileno()),
                label=require_single_link_label,
            )
        )
        if before_identity is not None and opened_identity != before_identity:
            raise _PreflightError(f"{require_single_link_label}_identity_changed_before_hash")
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
        opened_after_identity = (
            None
            if require_single_link_label is None
            else _single_link_identity_from_stat(
                os.fstat(stream.fileno()),
                label=require_single_link_label,
            )
        )
    after = path.lstat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise _PreflightError("file_changed_during_hash")
    after_identity = (
        None
        if require_single_link_label is None
        else _single_link_identity_from_stat(
            after,
            label=require_single_link_label,
        )
    )
    if before_identity is not None and not (
        before_identity == opened_identity == opened_after_identity == after_identity
    ):
        raise _PreflightError(f"{require_single_link_label}_identity_changed_during_hash")
    return digest.hexdigest(), after.st_size, after.st_mtime_ns


def _read_json(path: Path) -> dict[str, Any]:
    size = path.stat().st_size
    if size > MAX_RECEIPT_BYTES:
        raise _PreflightError("receipt_exceeds_size_limit")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise _PreflightError("receipt_not_valid_utf8_json") from error
    if not isinstance(value, dict):
        raise _PreflightError("receipt_must_be_json_object")
    return value


def _normalise_pin(value: str, label: str) -> str:
    pin = value.strip().lower()
    if not SHA256_RE.fullmatch(pin):
        raise _PreflightError(f"{label}_must_be_sha256")
    return pin


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_aware_datetime(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise _PreflightError(f"{label}_missing_or_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise _PreflightError(f"{label}_invalid_iso_datetime") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _PreflightError(f"{label}_must_include_timezone")
    return parsed.astimezone(timezone.utc)


def _path_value_matches_env(
    name: str,
    expected: Path,
    *,
    environ: Mapping[str, str],
) -> tuple[bool, str | None]:
    raw = environ.get(name)
    if not isinstance(raw, str) or not raw.strip():
        return False, f"{name.lower()}_missing"
    if raw != raw.strip():
        return False, f"{name.lower()}_has_surrounding_whitespace"
    try:
        observed = _existing_path(raw, label=name.lower())
        expected_path = _existing_path(expected, label=f"expected_{name.lower()}")
    except _PreflightError as error:
        return False, str(error)
    if observed != expected_path:
        return False, f"{name.lower()}_does_not_match_qa_root"
    return True, None


def _verify_environment_and_paths(
    config: PreflightConfig,
    *,
    environ: Mapping[str, str],
    repo_root: Path,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    blockers: list[dict[str, str]] = []
    checks: dict[str, Any] = {}

    def block(code: str, detail: str = "") -> None:
        blockers.append({"scope": "isolation", "code": code, "detail": detail})

    qa_parent = repo_root / "output" / "qa"
    try:
        resolved_qa_parent = _existing_path(
            qa_parent, label="repo_qa_parent", expect_file=False
        )
        resolved_qa = _existing_path(
            config.qa_root,
            label="qa_root",
            allowed_root=resolved_qa_parent,
            expect_file=False,
        )
        if resolved_qa.parent != resolved_qa_parent:
            raise _PreflightError("qa_root_must_be_direct_child_of_repo_output_qa")
    except _PreflightError as error:
        resolved_qa = None
        block(str(error))

    profile = environ.get("PROFILE")
    checks["PROFILE"] = profile
    if profile != "prod":
        block("profile_must_be_prod", f"observed={profile!r}")

    if resolved_qa is not None:
        expected_paths = {
            "DATA_ROOT": resolved_qa / "data",
            "OUTPUT_ROOT": resolved_qa / "output",
            "DB_PATH": resolved_qa / "data" / "sqlite" / "twstock.db",
            "RECOMMENDATION_LEARNING_OUTPUT_ROOT": resolved_qa / "output",
        }
        for name, expected in expected_paths.items():
            ok, issue = _path_value_matches_env(
                name,
                expected,
                environ=environ,
            )
            checks[name] = {"matches_qa_root": ok, "expected": str(expected)}
            if issue:
                block(issue)

        derived_paths = {
            "data_root": resolved_qa / "data",
            "output_root": resolved_qa / "output",
            "technical_output_root": resolved_qa / "data" / "output",
            "working_db": resolved_qa / "data" / "sqlite" / "twstock.db",
        }
        for name, path in derived_paths.items():
            try:
                resolved = _existing_path(
                    path,
                    label=name,
                    allowed_root=resolved_qa,
                    expect_file=(name == "working_db"),
                )
                checks[name] = {"path": str(resolved), "exists": True}
            except _PreflightError as error:
                checks[name] = {"path": str(path), "exists": False}
                block(str(error))

        pit_checks: dict[str, Any] = {}
        for name in PIT_PATH_ENV_NAMES:
            raw = environ.get(name)
            if not isinstance(raw, str) or not raw.strip():
                pit_checks[name] = {"state": "not_configured"}
                continue
            try:
                path = _existing_path(
                    raw,
                    label=name.lower(),
                    allowed_root=resolved_qa,
                )
                pit_checks[name] = {"state": "qa_contained", "path": str(path)}
            except _PreflightError as error:
                pit_checks[name] = {"state": "blocked", "reason": str(error)}
                block(f"{name.lower()}_unsafe", str(error))
        checks["pit_paths"] = pit_checks

    checks["candidate_update"] = {
        "explicit_skip": config.skip_candidate_update,
        "candidate_db_environment_read": False,
        "windows_registry_read": False,
    }
    if not config.skip_candidate_update:
        block("candidate_update_must_be_explicitly_skipped_for_qa_preflight")
    return checks, blockers


def _verify_seed(
    config: PreflightConfig,
    *,
    repo_root: Path,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    blockers: list[dict[str, str]] = []
    result: dict[str, Any] = {}

    def block(code: str, detail: str = "") -> None:
        blockers.append({"scope": "seed_integrity", "code": code, "detail": detail})

    try:
        expected_bootstrap_hash = _normalise_pin(
            config.expected_bootstrap_receipt_sha256,
            "expected_bootstrap_receipt_sha256",
        )
        expected_db_hash = _normalise_pin(
            config.expected_working_db_sha256,
            "expected_working_db_sha256",
        )
        expected_snapshot_receipt_hash = _normalise_pin(
            config.expected_snapshot_receipt_sha256,
            "expected_snapshot_receipt_sha256",
        )
        qa_root = _existing_path(
            config.qa_root,
            label="qa_root",
            allowed_root=repo_root / "output" / "qa",
            expect_file=False,
        )
        bootstrap_path = _existing_path(
            qa_root / "bootstrap_receipt.json",
            label="bootstrap_receipt",
            allowed_root=qa_root,
            expect_file=True,
        )
        bootstrap_hash, _, _ = _sha256_file(bootstrap_path)
        result["bootstrap_receipt_sha256"] = bootstrap_hash
        if bootstrap_hash != expected_bootstrap_hash:
            raise _PreflightError("bootstrap_receipt_sha256_pin_mismatch")
        receipt = _read_json(bootstrap_path)
        if (
            receipt.get("schema_version") != BOOTSTRAP_SCHEMA
            or receipt.get("status") != "database_seed_created"
        ):
            raise _PreflightError("bootstrap_receipt_schema_or_status_invalid")

        paths = receipt.get("paths")
        if not isinstance(paths, Mapping):
            raise _PreflightError("bootstrap_receipt_paths_missing")
        expected_paths = {
            "qa_root": qa_root,
            "data_root": qa_root / "data",
            "output_root": qa_root / "output",
            "technical_output_root": qa_root / "data" / "output",
            "working_db": qa_root / "data" / "sqlite" / "twstock.db",
        }
        for key, expected in expected_paths.items():
            raw = paths.get(key)
            if not isinstance(raw, str):
                raise _PreflightError(f"bootstrap_receipt_{key}_missing")
            actual = _existing_path(
                raw,
                label=f"receipt_{key}",
                allowed_root=qa_root,
                expect_file=(key == "working_db"),
            )
            if actual != expected.resolve(strict=True):
                raise _PreflightError(f"bootstrap_receipt_{key}_mismatch")

        lineage = receipt.get("lineage")
        destination = receipt.get("destination")
        if not isinstance(lineage, Mapping) or not isinstance(destination, Mapping):
            raise _PreflightError("bootstrap_receipt_lineage_missing")
        copy_observation = destination.get("copy")
        if not isinstance(copy_observation, Mapping):
            raise _PreflightError("bootstrap_receipt_copy_observation_missing")
        for label, value in (
            ("lineage_copy_source_sha256", lineage.get("copy_source_sha256")),
            ("lineage_working_copy_sha256", lineage.get("working_copy_sha256")),
            ("lineage_snapshot_sha256", lineage.get("snapshot_sha256")),
            ("destination_sha256_readback", copy_observation.get("destination_sha256_readback")),
            ("destination_source_sha256_during_copy", copy_observation.get("source_sha256_during_copy")),
        ):
            if value != expected_db_hash:
                raise _PreflightError(f"{label}_does_not_match_db_pin")
        if lineage.get("upstream_receipt_sha256") != expected_snapshot_receipt_hash:
            raise _PreflightError("bootstrap_upstream_snapshot_receipt_pin_mismatch")
        created_at = _parse_aware_datetime(
            receipt.get("created_at_utc"),
            "bootstrap_created_at_utc",
        )
        if created_at > config.observed_at:
            raise _PreflightError("bootstrap_receipt_created_after_observed_cutoff")

        db_path = expected_paths["working_db"].resolve(strict=True)
        for suffix in SQLITE_SIDECAR_SUFFIXES:
            if os.path.lexists(Path(str(db_path) + suffix)):
                _assert_no_reparse_chain(Path(str(db_path) + suffix))
                raise _PreflightError(f"sqlite_sidecar_present:{suffix}")
        db_identity_before_hash = _single_link_identity(
            db_path,
            label="working_db",
        )
        db_hash, db_size, db_mtime_ns = _sha256_file(
            db_path,
            require_single_link_label="working_db",
        )
        db_identity_after_hash = _single_link_identity(
            db_path,
            label="working_db",
        )
        if db_identity_after_hash != db_identity_before_hash:
            raise _PreflightError("working_db_identity_changed_after_hash")
        result["working_db"] = {
            "path": str(db_path),
            "sha256": db_hash,
            "size_bytes": db_size,
            "mtime_ns_at_hash": db_mtime_ns,
            "filesystem_identity": {
                "device": db_identity_after_hash[0],
                "inode": db_identity_after_hash[1],
                "link_count": db_identity_after_hash[2],
            },
            "sha256_is_full_file": True,
        }
        if db_hash != expected_db_hash:
            raise _PreflightError("working_db_sha256_pin_mismatch")

        source_receipt_raw = paths.get("source_snapshot_receipt")
        source_db_raw = paths.get("source_snapshot_db")
        if not isinstance(source_receipt_raw, str) or not isinstance(source_db_raw, str):
            raise _PreflightError("upstream_snapshot_receipt_path_missing")
        repo_qa = _existing_path(
            repo_root / "output" / "qa",
            label="repo_output_qa",
            expect_file=False,
        )
        source_receipt_path = _existing_path(
            source_receipt_raw,
            label="upstream_snapshot_receipt",
            allowed_root=repo_qa,
            expect_file=True,
        )
        source_db_path = _existing_path(
            source_db_raw,
            label="upstream_snapshot_db",
            allowed_root=repo_qa,
            expect_file=True,
        )
        snapshot_receipt_hash, _, _ = _sha256_file(source_receipt_path)
        result["upstream_snapshot_receipt_sha256"] = snapshot_receipt_hash
        if snapshot_receipt_hash != expected_snapshot_receipt_hash:
            raise _PreflightError("upstream_snapshot_receipt_sha256_pin_mismatch")
        snapshot_receipt = _read_json(source_receipt_path)
        if snapshot_receipt.get("schema_version") != UPSTREAM_SNAPSHOT_SCHEMA:
            raise _PreflightError("upstream_snapshot_receipt_schema_invalid")
        if Path(str(snapshot_receipt.get("snapshot_path", ""))).resolve() != source_db_path:
            raise _PreflightError("upstream_snapshot_receipt_database_path_mismatch")
        if snapshot_receipt.get("snapshot_sha256") != expected_db_hash:
            raise _PreflightError("upstream_snapshot_sha256_pin_mismatch")
        if snapshot_receipt.get("snapshot_integrity_check") != ["ok"]:
            raise _PreflightError("upstream_snapshot_integrity_not_verified")
        if snapshot_receipt.get("snapshot_journal_mode") != "delete":
            raise _PreflightError("upstream_snapshot_journal_mode_not_delete")
        if snapshot_receipt.get("snapshot_data_version_stable") is not True:
            raise _PreflightError("upstream_snapshot_data_version_not_stable")
        snapshot_completed_at = _parse_aware_datetime(
            snapshot_receipt.get("completed_at"),
            "upstream_snapshot_completed_at",
        )
        if snapshot_completed_at > config.observed_at:
            raise _PreflightError("upstream_snapshot_completed_after_observed_cutoff")
        result["upstream_snapshot"] = {
            "receipt_path": str(source_receipt_path),
            "database_path": str(source_db_path),
            "snapshot_sha256": expected_db_hash,
            "integrity_check": "ok",
            "journal_mode": "delete",
            "formal_source_paths_opened": False,
        }

        db_identity_before_open = _single_link_identity(
            db_path,
            label="working_db",
        )
        if db_identity_before_open != db_identity_after_hash:
            raise _PreflightError("working_db_identity_changed_before_sqlite_open")
        with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True) as connection:
            connection.execute("PRAGMA query_only=ON")
            query_only = int(connection.execute("PRAGMA query_only").fetchone()[0])
            if query_only != 1:
                raise _PreflightError("sqlite_query_only_not_enabled")
            schema_version = int(connection.execute("PRAGMA schema_version").fetchone()[0])
            journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()
            if journal_mode != "delete":
                raise _PreflightError("working_db_journal_mode_not_delete")
        db_identity_after_open = _single_link_identity(
            db_path,
            label="working_db",
        )
        if db_identity_after_open != db_identity_before_open:
            raise _PreflightError("working_db_identity_changed_after_sqlite_open")
        after_db = db_path.lstat()
        if (db_size, db_mtime_ns) != (after_db.st_size, after_db.st_mtime_ns):
            raise _PreflightError("working_db_changed_during_read_only_check")
        for suffix in SQLITE_SIDECAR_SUFFIXES:
            if os.path.lexists(Path(str(db_path) + suffix)):
                raise _PreflightError(f"sqlite_sidecar_created_or_present:{suffix}")
        result["sqlite"] = {
            "open_mode": "ro",
            "query_only": query_only,
            "schema_version": schema_version,
            "journal_mode": journal_mode,
            "integrity_basis": "working_db_full_sha256_matches_pinned_verified_snapshot_receipt",
            "db_mtime_unchanged_through_read_only_open": True,
            "db_sidecars_absent_before_and_after_read_only_open": True,
            "db_single_link_checked_before_hash_and_sqlite_open": True,
            "db_identity_stable_across_hash_and_sqlite_open": True,
        }
        result["bootstrap_claims"] = {
            "ready_for_daily_pipeline": receipt.get("ready_for_daily_pipeline"),
            "daily_chain_preflight_complete": receipt.get("daily_chain_preflight_complete"),
            "official_point_in_time_eligibility": receipt.get(
                "official_point_in_time_eligibility"
            ),
            "research_use_only": receipt.get("research_use_only"),
            "interpretation": "seed integrity is reported separately from current-day readiness",
        }
    except (_PreflightError, OSError, sqlite3.Error) as error:
        block(str(error))
    status = "verified" if not blockers else "blocked"
    result["status"] = status
    result["blockers"] = blockers
    return result, blockers


def _verify_day_evidence(
    config: PreflightConfig,
    *,
    repo_root: Path,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    blockers: list[dict[str, str]] = []
    result: dict[str, Any] = {
        "decision_date": config.decision_date.isoformat(),
        "calendar": {"status": "unverified"},
        "temporary_closure": {"status": "unverified"},
        "official_source_time": {"status": "unverified"},
    }

    def block(code: str, detail: str = "") -> None:
        blockers.append({"scope": "day_execution_readiness", "code": code, "detail": detail})

    repo_qa = repo_root / "output" / "qa"
    annual_cache = config.calendar_cache_path
    if annual_cache is None:
        block("annual_calendar_cache_missing")
    else:
        try:
            cache_path = _existing_path(
                annual_cache,
                label="annual_calendar_cache",
                allowed_root=repo_qa,
                expect_file=True,
            )
            from data_module.official_trading_calendar_cache import (
                load_verified_twse_calendar_cache,
            )

            verified = load_verified_twse_calendar_cache(
                cache_path,
                calendar_year=config.decision_date.year,
                observed_at=config.observed_at,
            )
            annual_open = (
                False
                if config.decision_date.weekday() >= 5
                else bool(verified.schedule.get(config.decision_date, True))
            )
            result["calendar"] = {
                "status": "verified",
                "path": str(cache_path),
                "cache_file_sha256": verified.evidence.get("cache_file_sha256"),
                "source_hash": verified.evidence.get("source_hash"),
                "captured_at": verified.evidence.get("captured_at"),
                "available_at": verified.evidence.get("available_at"),
                "expires_at": verified.evidence.get("expires_at"),
                "annual_schedule_scope": verified.evidence.get(
                    "annual_schedule_scope"
                ),
                "temporary_closure_coverage": verified.evidence.get(
                    "temporary_closure_coverage"
                ),
                "planned_open": annual_open,
            }
            if not annual_open:
                block("annual_calendar_says_closed")
        except Exception as error:
            block("annual_calendar_cache_invalid_or_expired", str(error))
            result["calendar"] = {"status": "blocked", "reason": str(error)}

    closure_path = config.temporary_closure_path
    if closure_path is None:
        block("temporary_closure_event_receipt_missing")
    else:
        try:
            safe_closure_path = _existing_path(
                closure_path,
                label="temporary_closure_receipt",
                allowed_root=repo_qa,
                expect_file=True,
            )
            from data_module.official_trading_calendar_cache import (
                load_verified_twse_temporary_closure_cache,
            )

            verified_closure = load_verified_twse_temporary_closure_cache(
                safe_closure_path,
                observed_at=config.observed_at,
            )
            closure_date = verified_closure.closure_date
            result["temporary_closure"] = {
                "status": "verified_event_only",
                "path": str(safe_closure_path),
                "closure_date": closure_date.isoformat(),
                "event_scope": "one_closure_event",
                "negative_coverage_for_decision_date": False,
            }
            if closure_date == config.decision_date:
                block("temporary_closure_event_closes_decision_date")
            else:
                block("temporary_closure_event_does_not_prove_no_closure_on_decision_date")
        except Exception as error:
            block("temporary_closure_receipt_invalid", str(error))
            result["temporary_closure"] = {"status": "blocked", "reason": str(error)}

    source_time_path = config.source_time_receipt_path
    if source_time_path is None:
        block("official_source_time_receipt_missing")
        result["official_source_time"] = {
            "status": "blocked",
            "reason": "no supported same-day official source-time receipt supplied",
        }
    else:
        try:
            safe_source_path = _existing_path(
                source_time_path,
                label="official_source_time_receipt",
                allowed_root=repo_qa,
                expect_file=True,
            )
            source_time_receipt = _read_json(safe_source_path)
            result["official_source_time"] = {
                "status": "blocked",
                "path": str(safe_source_path),
                "schema_version": source_time_receipt.get("schema_version"),
                "reason": "no approved WP5 official source-time receipt schema/validator is implemented",
            }
            block("official_source_time_receipt_schema_unimplemented")
        except _PreflightError as error:
            block("official_source_time_receipt_invalid", str(error))
            result["official_source_time"] = {"status": "blocked", "reason": str(error)}

    result["status"] = "ready" if not blockers else "blocked"
    result["blockers"] = blockers
    return result, blockers


def run_personal_current_observed_activity(
    config: PreflightConfig,
    *,
    capture_directory: str | Path | None,
    expected_capture_receipt_sha256: str | None,
    expected_capture_manifest_sha256: str | None,
    expected_calendar_cache_sha256: str | None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Qualify pinned same-day market activity for personal research only.

    The ordinary daily-chain preflight remains the source for seed integrity,
    bounded isolation, annual-calendar verification, and the unchanged strict
    ``day_execution_readiness`` result.  This separate branch accepts positive
    same-day market data as activity evidence, but never infers negative
    temporary-closure coverage or runner readiness.
    """

    blockers: list[dict[str, str]] = []

    def block(code: str, detail: str = "") -> None:
        blockers.append(
            {
                "scope": "personal_current_observed_activity",
                "code": code,
                "detail": detail,
            }
        )

    expected_calendar_pin: str | None = None
    try:
        expected_calendar_pin = _normalise_pin(
            expected_calendar_cache_sha256 or "",
            "expected_calendar_cache_sha256",
        )
    except _PreflightError as error:
        block("annual_calendar_pin_missing_or_invalid", str(error))

    try:
        strict = run_read_only_preflight(config, environ=environ)
    except Exception as error:
        strict = {
            "schema_version": PREFLIGHT_SCHEMA,
            "observed_at_utc": None,
            "decision_date": config.decision_date.isoformat(),
            "status": "blocked",
            "seed_integrity": {"status": "not_run", "blockers": []},
            "isolation": {"status": "not_run", "blockers": []},
            "day_execution_readiness": {"status": "not_run", "blockers": []},
            "blockers": [],
            "coverage_limits": [],
        }
        block("strict_preflight_failed", f"{type(error).__name__}:{error}")

    try:
        repo_root = (
            Path(config.repo_root).resolve(strict=True)
            if config.repo_root is not None
            else Path(__file__).resolve().parents[1]
        )
    except OSError as error:
        repo_root = Path(__file__).resolve().parents[1]
        block("repo_root_missing_or_unresolvable", str(error))

    clock_blockers = [
        item
        for item in strict.get("blockers", [])
        if isinstance(item, Mapping) and item.get("scope") == "preflight_clock"
    ]
    if clock_blockers:
        for item in clock_blockers:
            block(str(item.get("code", "preflight_clock_blocked")), str(item.get("detail", "")))

    seed = strict.get("seed_integrity", {})
    if not isinstance(seed, Mapping) or seed.get("status") != "verified":
        block("seed_integrity_not_verified")
    isolation = strict.get("isolation", {})
    if not isinstance(isolation, Mapping) or isolation.get("status") != "bounded_verified":
        block("bounded_isolation_not_verified")

    day = strict.get("day_execution_readiness", {})
    calendar = day.get("calendar", {}) if isinstance(day, Mapping) else {}
    if not isinstance(calendar, Mapping) or calendar.get("status") != "verified":
        block("annual_calendar_not_verified")
    elif calendar.get("planned_open") is not True:
        block("annual_calendar_not_planned_open")

    annual_calendar: dict[str, Any] = {
        "status": "blocked",
        "planned_open": False,
        "temporary_closure_negative_coverage": False,
    }
    calendar_hash: str | None = None
    if isinstance(calendar, Mapping) and calendar.get("status") == "verified":
        raw_path = calendar.get("path")
        try:
            if not isinstance(raw_path, str):
                raise _PreflightError("annual_calendar_path_missing")
            safe_path = _existing_path(
                raw_path,
                label="annual_calendar_cache",
                allowed_root=repo_root / "output" / "qa",
                expect_file=True,
            )
            calendar_identity_before = _single_link_identity(
                safe_path,
                label="annual_calendar_cache",
            )
            calendar_hash, calendar_size, calendar_mtime = _sha256_file(safe_path)
            calendar_identity_after = _single_link_identity(
                safe_path,
                label="annual_calendar_cache",
            )
            if calendar_identity_before != calendar_identity_after or (
                calendar_size,
                calendar_mtime,
            ) != (calendar_identity_after[3], calendar_identity_after[4]):
                raise _PreflightError("annual_calendar_identity_changed_during_read")
            calendar_pin_matches = (
                expected_calendar_pin is not None
                and calendar_hash == expected_calendar_pin
            )
            if expected_calendar_pin is not None and not calendar_pin_matches:
                block("annual_calendar_sha256_pin_mismatch")
            cache_evidence_hash = calendar.get("cache_file_sha256")
            cache_readback_matches = cache_evidence_hash == f"sha256:{calendar_hash}"
            if not cache_readback_matches:
                block("annual_calendar_readback_sha256_mismatch")
            annual_calendar = {
                "status": (
                    "verified"
                    if calendar_pin_matches and cache_readback_matches
                    else "blocked"
                ),
                "path": str(safe_path),
                "sha256": calendar_hash,
                "caller_pin_sha256": expected_calendar_pin,
                "caller_pin_matches": calendar_pin_matches,
                "cache_readback_matches": cache_readback_matches,
                "planned_open": calendar.get("planned_open") is True,
                "captured_at": calendar.get("captured_at"),
                "available_at": calendar.get("available_at"),
                "expires_at": calendar.get("expires_at"),
                "temporary_closure_negative_coverage": False,
            }
        except (_PreflightError, OSError) as error:
            block("annual_calendar_pin_readback_failed", str(error))
            annual_calendar = {"status": "blocked", "reason": str(error)}

    closure_evidence: dict[str, Any] = {
        "status": "unknown",
        "decision_date_closure_event": False,
        "negative_coverage": False,
        "interpretation": "missing_event_does_not_prove_no_temporary_closure",
    }
    if config.temporary_closure_path is not None and not clock_blockers:
        try:
            safe_closure_path = _existing_path(
                config.temporary_closure_path,
                label="temporary_closure_receipt",
                allowed_root=repo_root / "output" / "qa",
                expect_file=True,
            )
            closure_identity_before = _single_link_identity(
                safe_closure_path,
                label="temporary_closure_receipt",
            )
            from data_module.official_trading_calendar_cache import (
                load_verified_twse_temporary_closure_cache,
            )

            observed_at = datetime.fromisoformat(
                str(strict.get("observed_at_utc"))
            )
            verified_closure = load_verified_twse_temporary_closure_cache(
                safe_closure_path,
                observed_at=observed_at,
            )
            closure_identity_after = _single_link_identity(
                safe_closure_path,
                label="temporary_closure_receipt",
            )
            if closure_identity_before != closure_identity_after:
                raise _PreflightError(
                    "temporary_closure_identity_changed_during_read"
                )
            closure_on_decision_date = (
                verified_closure.closure_date == config.decision_date
            )
            closure_evidence = {
                "status": (
                    "same_day_closure_event"
                    if closure_on_decision_date
                    else "verified_other_date_event"
                ),
                "path": str(safe_closure_path),
                "closure_date": verified_closure.closure_date.isoformat(),
                "decision_date_closure_event": closure_on_decision_date,
                "negative_coverage": False,
                "interpretation": (
                    "verified_same_day_closure_blocks_personal_activity"
                    if closure_on_decision_date
                    else "event_for_another_date_does_not_prove_negative_coverage"
                ),
            }
            if closure_on_decision_date:
                block("verified_temporary_closure_event_on_decision_date")
        except Exception as error:
            closure_evidence = {
                "status": "blocked",
                "decision_date_closure_event": False,
                "negative_coverage": False,
                "reason": f"{type(error).__name__}:{error}",
            }
            block("temporary_closure_evidence_invalid", closure_evidence["reason"])

    capture_result: dict[str, Any] = {
        "status": "blocked",
        "temporary_closure_negative_coverage": False,
        "formal_pit": False,
        "official_published_at": "unknown",
        "official_published_at_utc": "unknown",
    }
    from data_module.wp5_official_daily_capture_validator import (
        CaptureValidationError,
        validate_official_daily_capture,
    )

    missing_capture_inputs = False
    for label, value in (
        ("capture_directory", capture_directory),
        ("capture_receipt_sha256", expected_capture_receipt_sha256),
        ("capture_manifest_sha256", expected_capture_manifest_sha256),
    ):
        if value is None or not str(value).strip():
            block(f"{label}_missing")
            missing_capture_inputs = True

    # Do not spend time reading the raw market body when the seed/isolation,
    # current cutoff, annual-open, or caller-pin prerequisites already fail.
    prerequisites_ok = not blockers
    if prerequisites_ok and not missing_capture_inputs:
        try:
            observed_at = datetime.fromisoformat(str(strict["observed_at_utc"]))
            if not isinstance(capture_directory, (str, Path)):
                raise ValueError("capture_directory must be a filesystem path")
            capture_result = validate_official_daily_capture(
                capture_directory,
                expected_receipt_sha256=str(expected_capture_receipt_sha256),
                expected_manifest_sha256=str(expected_capture_manifest_sha256),
                decision_date=config.decision_date,
                required_symbols_by_venue={"TWSE": "2330", "TPEx": "6488"},
                cutoff_utc=observed_at,
                repo_root=(
                    config.repo_root
                    if config.repo_root is not None
                    else Path(__file__).resolve().parents[1]
                ),
            )
            if capture_result.get("official_published_at_utc") != "unknown":
                block("official_published_at_must_remain_unknown")
            if capture_result.get("formal_pit") is not False:
                block("official_capture_must_not_claim_formal_pit")
            if capture_result.get("temporary_closure_negative_coverage") is not False:
                block("official_capture_must_not_claim_closure_negative_coverage")
        except CaptureValidationError as error:
            capture_result = {
                "status": "blocked",
                "blockers": [{"code": error.code, "detail": error.detail}],
                "official_published_at_utc": "unknown",
                "temporary_closure_negative_coverage": False,
                "formal_pit": False,
            }
            block(error.code, error.detail)
        except Exception as error:
            capture_result = {
                "status": "blocked",
                "blockers": [
                    {
                        "code": "official_capture_validation_error",
                        "detail": f"{type(error).__name__}:{error}",
                    }
                ],
                "official_published_at_utc": "unknown",
                "temporary_closure_negative_coverage": False,
                "formal_pit": False,
            }
            block(
                "official_capture_validation_error",
                f"{type(error).__name__}:{error}",
            )

    status = "eligible_personal_research" if not blockers else "blocked"
    return {
        "schema_version": PERSONAL_ACTIVITY_SCHEMA,
        "mode": "personal_current_observed_activity",
        "status": status,
        "decision_date": config.decision_date.isoformat(),
        "decision_at_utc": strict.get("observed_at_utc"),
        "observed_at_utc": capture_result.get("available_at_utc"),
        "cutoff_utc": strict.get("observed_at_utc"),
        "research_only": True,
        "formal_pit": False,
        "official_published_at": "unknown",
        "official_published_at_utc": "unknown",
        "temporary_closure_negative_coverage": False,
        "runner_executed": False,
        "seed_integrity": strict.get("seed_integrity"),
        "isolation": strict.get("isolation"),
        "day_execution_readiness": strict.get("day_execution_readiness"),
        "annual_calendar": annual_calendar,
        "capture_pins": {
            "capture_directory": capture_result.get("capture_directory")
            or (None if capture_directory is None else str(capture_directory)),
            "receipt_sha256": capture_result.get("receipt_sha256")
            or expected_capture_receipt_sha256,
            "manifest_sha256": capture_result.get("manifest_sha256")
            or expected_capture_manifest_sha256,
            "raw_sha256_by_market": {
                name: market.get("raw_sha256")
                for name, market in (
                    capture_result.get("markets", {}).items()
                    if isinstance(capture_result.get("markets"), Mapping)
                    else []
                )
                if isinstance(market, Mapping)
            },
        },
        "temporary_closure_evidence": closure_evidence,
        "official_same_day_market_activity": capture_result,
        "blockers": blockers,
        "coverage_limits": [
            "Eligible status is limited to personal research using same-day observed market activity; it is not a normal-full-day or generic runner authorization.",
            "Annual planned-open schedule and a same-day positive market response do not establish complete temporary-closure negative coverage.",
            "The official capture's local body-read completion time is a conservative availability upper bound, not an official publication timestamp or Formal PIT proof.",
            "The original day_execution_readiness value is preserved unchanged; this personal branch does not alter its strict blocked semantics.",
            "Bounded preflight filesystem checks retain the documented concurrent rename/junction TOCTOU limitation and do not authorize later runner access.",
        ],
    }


def run_read_only_preflight(
    config: PreflightConfig,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Inspect seed, path isolation and same-day evidence without writing."""

    env = os.environ if environ is None else environ
    repo_root = (
        Path(config.repo_root).resolve(strict=True)
        if config.repo_root is not None
        else Path(__file__).resolve().parents[1]
    )
    observed = config.observed_at
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("observed_at must include a timezone")
    observed = observed.astimezone(timezone.utc)
    now = _utc_now().astimezone(timezone.utc)
    clock_blockers: list[dict[str, str]] = []
    if (observed - now).total_seconds() > OBSERVED_CLOCK_SKEW_SECONDS:
        clock_blockers.append(
            {
                "scope": "preflight_clock",
                "code": "observed_at_is_in_the_future",
                "detail": "caller-supplied cutoff cannot be later than the current clock",
            }
        )
    if (now - observed).total_seconds() > MAX_OBSERVED_AGE_SECONDS:
        clock_blockers.append(
            {
                "scope": "preflight_clock",
                "code": "observed_at_is_stale",
                "detail": "observed cutoff must be within five minutes of the current clock",
            }
        )
    if observed.astimezone(TAIPEI).date() != config.decision_date:
        clock_blockers.append(
            {
                "scope": "preflight_clock",
                "code": "observed_taipei_date_must_match_decision_date",
                "detail": "decision date must be the current Taipei date at observation time",
            }
        )
    if clock_blockers:
        return {
            "schema_version": PREFLIGHT_SCHEMA,
            "observed_at_utc": observed.isoformat(),
            "decision_date": config.decision_date.isoformat(),
            "status": "blocked",
            "seed_integrity": {"status": "not_run", "blockers": []},
            "isolation": {
                "status": "not_run",
                "scope": "bounded_environment_and_path_checks",
                "checks": {},
                "blockers": [],
            },
            "day_execution_readiness": {"status": "not_run", "blockers": []},
            "blockers": clock_blockers,
            "coverage_limits": [
                "Invalid time/date cutoffs stop the preflight before reading QA inputs.",
            ],
        }
    normalized_config = PreflightConfig(
        qa_root=Path(config.qa_root),
        decision_date=config.decision_date,
        observed_at=observed,
        expected_bootstrap_receipt_sha256=config.expected_bootstrap_receipt_sha256,
        expected_working_db_sha256=config.expected_working_db_sha256,
        expected_snapshot_receipt_sha256=config.expected_snapshot_receipt_sha256,
        calendar_cache_path=(
            None if config.calendar_cache_path is None else Path(config.calendar_cache_path)
        ),
        temporary_closure_path=(
            None
            if config.temporary_closure_path is None
            else Path(config.temporary_closure_path)
        ),
        source_time_receipt_path=(
            None
            if config.source_time_receipt_path is None
            else Path(config.source_time_receipt_path)
        ),
        skip_candidate_update=config.skip_candidate_update,
        repo_root=repo_root,
    )

    isolation, isolation_blockers = _verify_environment_and_paths(
        normalized_config,
        environ=env,
        repo_root=repo_root,
    )
    seed, seed_blockers = _verify_seed(normalized_config, repo_root=repo_root)
    day, day_blockers = _verify_day_evidence(
        normalized_config,
        repo_root=repo_root,
    )
    blockers = isolation_blockers + seed_blockers + day_blockers
    return {
        "schema_version": PREFLIGHT_SCHEMA,
        "observed_at_utc": observed.isoformat(),
        "decision_date": config.decision_date.isoformat(),
        "status": "ready" if not blockers else "blocked",
        "seed_integrity": seed,
        "isolation": {
            "status": "bounded_verified" if not isolation_blockers else "blocked",
            "scope": "only explicit env paths checked here; not a complete child-process path inventory",
            "checks": isolation,
            "blockers": isolation_blockers,
        },
        "day_execution_readiness": day,
        "blockers": blockers,
        "coverage_limits": [
            "Only the pinned QA copy and its upstream QA snapshot receipt are inspected; formal D paths are not opened.",
            "The working DB must report st_nlink == 1 before/after hashing and around the SQLite read-only open; device/inode/size/mtime are compared at those path checks.",
            "Isolation covers PROFILE, the four bound output/data/DB env paths, and six PIT_SECTOR_MEMBERSHIP_* path envs; other child-specific or persisted path sources are outside this check.",
            "Path/reparse and link-count checks are not bound to the later runner's SQLite handle; a concurrent rename/junction/hardlink race between preflight and runner open remains outside this check.",
            "No complete historical PIT availability or full-database date scan is claimed.",
            "Event-only temporary-closure receipts cannot prove a negative closure for the decision date.",
            "No supported same-day WP5 official source-time receipt schema/validator is currently implemented; therefore day_execution_readiness cannot become ready until that contract is implemented and independently reviewed.",
            "This command does not invoke TWStockConfig, scheduled runner main, bootstrap main, network fetch, or candidate registry resolution.",
        ],
    }
