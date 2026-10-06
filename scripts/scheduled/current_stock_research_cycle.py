"""Run one bounded, same-run current-stock research cycle.

The cycle is research-only. It reads the canonical watchlist and holdings,
creates a physically verified current-restated SQLite snapshot, then delegates
raw publication, outcome construction, CORE19 fit, sidecar, and registry work to
the existing project producers and validators. Every request is create-only and
bound to one successful daily B receipt.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
from typing import Any, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

from portfolio_module import Trade, rebuild_positions

from data_module.ml_research_direct_ooc_adapter import DAILY_PRICE_FEATURE_IDS
from data_module.ml_daily_price_revision_gate import (
    CurrentRestatedContractNotConnectedError,
    _source_context_scan_revision_namespace_inventory,
    load_verified_current_restated_source_context,
)
from data_module.ml_research_output_boundary import (
    get_ml_research_root,
    resolve_ml_research_output_path,
)
from data_module.ml_storage_capacity import (
    BYTES_PER_GIB,
    CANONICAL_HEAVY_CHAIN_SAFETY_RESERVE_BYTES,
    MLStorageCapacityBudget,
    MLStorageChainReservation,
    StorageCapacityError,
    acquire_heavy_chain_reservation,
    build_heavy_chain_reservation_handoff_environment,
    heavy_chain_lock_path,
    preflight_capacity,
    release_heavy_chain_reservation,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESEARCH_OUTPUT_ROOT = REPOSITORY_ROOT / "output" / "ml_research"
RAW_SHARD_SCRIPT = REPOSITORY_ROOT / "scripts" / "build_ml_pit_year_shards.py"
OUTCOME_STORE_SCRIPT = (
    REPOSITORY_ROOT / "scripts" / "build_ml_current_restated_outcome_store.py"
)
FIT_SCRIPT = REPOSITORY_ROOT / "scripts" / "train_bounded_restated_research.py"
MAX_CHILD_OUTPUT_BYTES = 16 * 1024 * 1024
MAX_RECEIPT_BYTES = 8 * 1024 * 1024
MAX_LEDGER_BYTES = 32 * 1024 * 1024
MAX_LEDGER_ROWS = 100_000
MAX_B_SEMANTIC_SHARD_BYTES = 256 * 1024 * 1024
MAX_B_SEMANTIC_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_B_SEMANTIC_LINE_BYTES = 1024 * 1024
B_DAILY_FEATURE_IDS = DAILY_PRICE_FEATURE_IDS
CURRENT_CYCLE_PERSISTENT_BUDGET_BYTES = 2 * BYTES_PER_GIB
CURRENT_CYCLE_TEMPORARY_BUDGET_BYTES = 2 * BYTES_PER_GIB
CURRENT_CYCLE_SAFETY_RESERVE_BYTES = CANONICAL_HEAVY_CHAIN_SAFETY_RESERVE_BYTES
RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}\Z")
SYMBOL_RE = re.compile(r"\d{4}\Z")
SHA256_RE = re.compile(r"(?:sha256:)?[0-9a-fA-F]{64}\Z")
_TAIPEI = ZoneInfo("Asia/Taipei")
_GIB = BYTES_PER_GIB


class CurrentStockResearchCycleError(ValueError):
    """A current-stock research cycle could not be safely completed."""


class _WaitingForSource(CurrentStockResearchCycleError):
    """Required current inputs are absent, immature, or not yet connected."""


class _InvalidEvidence(CurrentStockResearchCycleError):
    """Pinned evidence failed a structural, identity, or hash check."""


class _ChildJsonObject(dict[str, Any]):
    """Parsed child JSON with custody hash of the child's exact stdout bytes."""

    def __init__(self, payload: Mapping[str, Any], *, stdout_sha256: str) -> None:
        super().__init__(payload)
        self.stdout_sha256 = stdout_sha256


def _cycle_storage_key(raw_run_id: str) -> str:
    """Keep immutable cycle output paths below classic Windows path limits."""

    if not isinstance(raw_run_id, str) or not RUN_ID_RE.fullmatch(raw_run_id):
        raise ValueError("raw_run_id is invalid")
    # The full raw run id remains in every receipt and index. A 128-bit directory
    # key shortens nested shard paths; create-only directory creation and a
    # terminal identity check make even a hash collision fail closed.
    return hashlib.sha256(raw_run_id.encode("utf-8")).hexdigest()[:32]


def _new_fit_output_path(cycle_root: Path) -> Path:
    """Return the create-only model leaf without pre-creating it.

    The fit CLI's verified model writer owns creation of this directory. A
    controller-created empty directory is still an occupied immutable output
    slot and would correctly be rejected by that writer.
    """

    fit_output = cycle_root / "model"
    if fit_output.exists() or fit_output.is_symlink():
        raise _InvalidEvidence(f"fit model output already exists: {fit_output}")
    return fit_output


def _known_maturity_block(payload: Mapping[str, Any]) -> bool:
    """Accept only explicit producer maturity failures as natural waiting."""

    if payload.get("error_type") == "InsufficientMatureCurrentRestatedHistoryError":
        return True
    reason = payload.get("reason")
    if not isinstance(reason, str):
        return False
    if reason.startswith("InsufficientMatureCurrentRestatedHistoryError:"):
        return True
    return re.fullmatch(
        r"CurrentRestatedResearchError: CORE19 projection leaves only [0-3] qualifying mature folds; at least four are required",
        reason,
    ) is not None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _context_fit_freeze(
    snapshot_completed_at: datetime,
    revision_dependencies_verified_at: datetime,
) -> datetime:
    """Use a real post-verification wall-clock cutoff without rewriting source clocks."""

    snapshot_completed = _aware_utc(snapshot_completed_at, "snapshot completed_at")
    dependencies_verified = _aware_utc(
        revision_dependencies_verified_at,
        "revision_dependencies_verified_at",
    )
    fit_freeze = _utc_now()
    if fit_freeze < snapshot_completed or fit_freeze < dependencies_verified:
        raise _WaitingForSource(
            "wall clock moved before the completed snapshot or verified revision dependencies"
        )
    return fit_freeze




def _canonical_sha256(payload: object) -> str:
    return _sha256(_canonical_json_bytes(payload))


def _without_field(payload: Mapping[str, Any], field: str) -> dict[str, Any]:
    result = dict(payload)
    result.pop(field, None)
    return result


def _parse_json_object(raw: bytes, label: str) -> dict[str, Any]:
    if len(raw) > MAX_RECEIPT_BYTES:
        raise _InvalidEvidence(f"{label} exceeds the metadata byte limit")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _InvalidEvidence(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise _InvalidEvidence(f"{label} root must be a JSON object")
    return payload


def _aware_utc(value: object, label: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise _InvalidEvidence(f"{label} is not an ISO datetime") from exc
    else:
        raise _InvalidEvidence(f"{label} is missing")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _InvalidEvidence(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _sha256_pin(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value.strip()):
        raise _InvalidEvidence(f"{label} is not a SHA-256 pin")
    clean = value.strip().lower()
    return clean if clean.startswith("sha256:") else "sha256:" + clean


def _verify_published_current_stock_registry_record(
    record: Mapping[str, Any],
    *,
    raw_run_id: str,
    published_run_id: str,
    source_date: str,
    symbols: Sequence[str],
    source_context_sha256: str,
    sidecar_receipt_sha256: str,
    model_manifest_sha256: str,
    model_bundle_sha256: str,
    current_price_fingerprints: Mapping[str, str],
    current_price_rows_source_path: Path,
    current_price_rows_source_sha256: str,
) -> None:
    """Verify the publisher's immutable record against this exact cycle."""

    if (
        record.get("schema_version") != "current-restated-stock-research-registry.v1"
        or record.get("status") != "verified_research_sidecar"
        or record.get("scope_mode") != "current_stock_research"
        or record.get("event_date") != source_date
        or record.get("symbols") != list(symbols)
        or record.get("cycle_id") != raw_run_id
        or record.get("run_id") != published_run_id
        or record.get("historical_pit_eligible") is not False
        or record.get("formal_calibration_performed") is not False
        or record.get("formal_qualified") is not False
        or record.get("production_action_allowed") is not False
    ):
        raise _InvalidEvidence("immutable ML registry record is not bound to this current-stock cycle")

    expected_digests = {
        "source_context_sha256": source_context_sha256,
        "sidecar_receipt_sha256": sidecar_receipt_sha256,
        "model_manifest_sha256": model_manifest_sha256,
        "model_bundle_sha256": model_bundle_sha256,
    }
    for field, expected in expected_digests.items():
        if _sha256_pin(record.get(field), f"registry record {field}") != _sha256_pin(
            expected, f"expected {field}"
        ):
            raise _InvalidEvidence(f"immutable ML registry record {field} differs from this cycle")

    raw_fingerprints = record.get("current_price_row_fingerprint_sha256_by_symbol")
    if not isinstance(raw_fingerprints, Mapping):
        raise _InvalidEvidence("registry record current-price fingerprints are missing")
    record_fingerprints = {
        str(symbol): _sha256_pin(digest, f"registry price fingerprint for {symbol}")
        for symbol, digest in raw_fingerprints.items()
    }
    expected_fingerprints = {
        str(symbol): _sha256_pin(digest, f"cycle price fingerprint for {symbol}")
        for symbol, digest in current_price_fingerprints.items()
    }
    if record_fingerprints != expected_fingerprints:
        raise _InvalidEvidence("registry current-price fingerprints differ from this cycle")

    expected_rows_path = str(current_price_rows_source_path.resolve(strict=True))
    if record.get("current_price_rows_source_path") != expected_rows_path:
        raise _InvalidEvidence("registry current-price rows path differs from this cycle")
    if _sha256_pin(
        record.get("current_price_rows_source_sha256"), "registry current-price rows SHA"
    ) != _sha256_pin(current_price_rows_source_sha256, "cycle current-price rows SHA"):
        raise _InvalidEvidence("registry current-price rows SHA differs from this cycle")


def _reject_reparse_components(path: Path, label: str) -> None:
    absolute = Path(os.path.abspath(str(path)))
    current = Path(absolute.anchor)
    reparse_flag = getattr(__import__("stat"), "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    for component in absolute.parts[1:]:
        current = current / component
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise _WaitingForSource(f"{label} path cannot be inspected: {current}") from exc
        is_junction = getattr(current, "is_junction", None)
        if (
            current.is_symlink()
            or bool(getattr(info, "st_file_attributes", 0) & reparse_flag)
            or (callable(is_junction) and is_junction())
        ):
            raise _WaitingForSource(f"{label} path traverses a link: {current}")


def _pin_regular_file(path: Path, *, label: str) -> dict[str, Any]:
    _reject_reparse_components(path, label)
    try:
        resolved = path.resolve(strict=True)
        before = resolved.stat()
        if not resolved.is_file():
            raise _WaitingForSource(f"{label} is not a regular file: {resolved}")
        digest = hashlib.sha256()
        byte_count = 0
        with resolved.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
                byte_count += len(chunk)
        after = resolved.stat()
    except OSError as exc:
        raise _WaitingForSource(f"{label} cannot be read: {path}") from exc
    if (
        byte_count != before.st_size
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise _InvalidEvidence(f"{label} changed while being pinned")
    return {
        "path": str(resolved),
        "bytes": byte_count,
        "mtime_ns": before.st_mtime_ns,
        "sha256": digest.hexdigest(),
    }


def _verify_file_pin(path: Path, expected: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    actual = _pin_regular_file(path, label=label)
    for field in ("path", "bytes", "mtime_ns", "sha256"):
        expected_value = expected.get(field)
        actual_value = actual.get(field)
        if field == "path" and isinstance(expected_value, str):
            if os.path.normcase(os.path.abspath(expected_value)) != os.path.normcase(
                os.path.abspath(str(actual_value))
            ):
                raise _InvalidEvidence(f"{label} path differs from its pin")
        elif expected_value != actual_value:
            raise _InvalidEvidence(f"{label} {field} differs from its pin")
    return actual


def _write_create_only(path: Path, payload: Mapping[str, Any]) -> str:
    raw = _canonical_json_bytes(payload)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise _InvalidEvidence(f"create-only artifact already exists: {path}") from exc
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    readback = path.read_bytes()
    if readback != raw:
        raise _InvalidEvidence(f"create-only readback differs: {path}")
    return _sha256(readback)


def _write_create_only_bytes(path: Path, raw: bytes) -> str:
    """Persist exact bounded child output without replacing prior evidence."""

    if type(raw) is not bytes or len(raw) > MAX_CHILD_OUTPUT_BYTES:
        raise _InvalidEvidence("child output bytes are invalid or exceed their bound")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise _InvalidEvidence(f"create-only child output already exists: {path}") from exc
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    readback = path.read_bytes()
    if readback != raw:
        raise _InvalidEvidence(f"create-only child output readback differs: {path}")
    return _sha256(readback)


def _append_event(event_path: Path, event: Mapping[str, Any], *, first: bool) -> str:
    raw = _canonical_json_bytes(event) + b"\n"
    mode = "xb" if first else "ab"
    with event_path.open(mode) as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return _sha256(event_path.read_bytes())


def _source_namespace_pins(source_db: Path) -> list[dict[str, Any]]:
    try:
        inventory = _source_context_scan_revision_namespace_inventory(source_db)
    except (OSError, RuntimeError, ValueError) as exc:
        raise _WaitingForSource(
            f"current-restated revision namespace inventory is unavailable: {exc}"
        ) from exc
    pins: list[dict[str, Any]] = []
    for path, namespace, digest in inventory:
        pin = _pin_regular_file(path, label=f"{namespace} revision evidence")
        if pin["sha256"] != digest:
            raise _InvalidEvidence(f"{namespace} revision evidence changed during inventory")
        pins.append({**pin, "namespace": namespace})
    return pins


def _sqlite_readonly(path: Path, *, immutable: bool = False) -> sqlite3.Connection:
    uri = path.resolve(strict=True).as_uri() + "?mode=ro"
    if immutable:
        uri += "&immutable=1"
    connection = sqlite3.connect(uri, uri=True, timeout=30.0)
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA busy_timeout=30000")
    return connection


def _sqlite_header_journal_mode(path: Path) -> str:
    """Read the durable SQLite journal-mode family without opening a writer."""

    try:
        with path.open("rb") as stream:
            header = stream.read(20)
    except OSError as exc:
        raise _WaitingForSource(f"source SQLite header cannot be read: {path}") from exc
    if len(header) < 20 or header[:16] != b"SQLite format 3\x00":
        raise _InvalidEvidence("source database has no valid SQLite format header")
    read_version, write_version = header[18], header[19]
    if (read_version, write_version) == (2, 2):
        return "wal"
    if (read_version, write_version) == (1, 1):
        return "rollback"
    raise _InvalidEvidence("source SQLite header has unsupported or transitional journal-mode bytes")


def _create_consistent_snapshot(
    *, source_database: Path, snapshot_database: Path, receipt_path: Path
) -> dict[str, Any]:
    """Create and physically pin a snapshot from one query-only read transaction."""

    source = source_database.resolve(strict=True)
    snapshot = snapshot_database.resolve(strict=False)
    wal_path = source.with_name(source.name + "-wal")
    started_at = _utc_now()
    database_before = _pin_regular_file(source, label="source SQLite database")
    wal_before = _optional_file_pin(wal_path, label="source SQLite WAL")
    shm_path = source.with_name(source.name + "-shm")
    shm_before = (
        _pin_regular_file(shm_path, label="source SQLite shared-memory file")
        if shm_path.exists()
        else None
    )
    namespace_before = _source_namespace_pins(source)
    try:
        # Opening a clean WAL-mode database through ordinary mode=ro may create
        # an empty -wal/-shm pair on Windows. When the WAL is genuinely absent,
        # immutable read-only mode prevents that filesystem side effect; the
        # before/after DB, WAL, generation, and namespace pins still reject any
        # concurrent writer or source change.
        source_connection = _sqlite_readonly(source, immutable=wal_before is None)
    except (OSError, sqlite3.Error) as exc:
        raise _WaitingForSource(f"source SQLite database cannot be opened read-only: {exc}") from exc
    destination_connection: sqlite3.Connection | None = None
    try:
        data_version_before = source_connection.execute("PRAGMA data_version").fetchone()
        if not data_version_before or type(data_version_before[0]) is not int:
            raise _InvalidEvidence("SQLite PRAGMA data_version did not return an integer")
        if wal_before is None:
            journal_mode_before = _sqlite_header_journal_mode(source)
            journal_mode_reader = "sqlite_file_header_read_write_version.v1"
        else:
            journal_mode_before_row = source_connection.execute("PRAGMA journal_mode").fetchone()
            if not journal_mode_before_row or not isinstance(journal_mode_before_row[0], str):
                raise _InvalidEvidence("SQLite journal_mode did not return text")
            journal_mode_before = str(journal_mode_before_row[0]).lower()
            journal_mode_reader = "sqlite_pragma"
        source_connection.execute("BEGIN")
        source_connection.execute("SELECT name FROM sqlite_master ORDER BY name LIMIT 1").fetchone()
        try:
            descriptor = os.open(snapshot, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise _InvalidEvidence("snapshot destination already exists") from exc
        os.close(descriptor)
        try:
            destination_connection = sqlite3.connect(str(snapshot), timeout=30.0)
            source_connection.backup(destination_connection, pages=256, sleep=0.05)
            destination_connection.commit()
        except (OSError, sqlite3.Error) as exc:
            raise _WaitingForSource(f"SQLite online backup did not finish: {exc}") from exc
        check_connection = sqlite3.connect(snapshot.as_uri() + "?mode=ro", uri=True)
        try:
            check_connection.execute("PRAGMA query_only=ON")
            check = check_connection.execute("PRAGMA quick_check").fetchone()
        finally:
            check_connection.close()
        if not check or check[0] != "ok":
            raise _InvalidEvidence("snapshot quick_check did not return ok")
        data_version_after = source_connection.execute("PRAGMA data_version").fetchone()
        if not data_version_after or type(data_version_after[0]) is not int:
            raise _InvalidEvidence("SQLite post-backup data_version is invalid")
        if wal_before is None:
            journal_mode_after = _sqlite_header_journal_mode(source)
        else:
            journal_mode_after_row = source_connection.execute("PRAGMA journal_mode").fetchone()
            if not journal_mode_after_row or not isinstance(journal_mode_after_row[0], str):
                raise _InvalidEvidence("SQLite post-backup journal_mode did not return text")
            journal_mode_after = str(journal_mode_after_row[0]).lower()
        source_connection.execute("COMMIT")
    finally:
        if destination_connection is not None:
            destination_connection.close()
        if source_connection.in_transaction:
            source_connection.rollback()
        source_connection.close()

    database_after = _pin_regular_file(source, label="source SQLite database")
    wal_after = _optional_file_pin(wal_path, label="source SQLite WAL")
    shm_after = (
        _pin_regular_file(shm_path, label="source SQLite shared-memory file")
        if shm_path.exists()
        else None
    )
    namespace_after = _source_namespace_pins(source)
    same_dependencies = (
        _snapshot_dependency_identity(database_before) == _snapshot_dependency_identity(database_after)
        and _snapshot_dependency_identity(wal_before) == _snapshot_dependency_identity(wal_after)
        and namespace_before == namespace_after
    )
    if (
        not same_dependencies
        or data_version_before[0] != data_version_after[0]
        or journal_mode_before != journal_mode_after
    ):
        _write_create_only(receipt_path.with_name("snapshot_failure.json"), {
            "schema_version": "integration-consistent-sqlite-snapshot-failure.v1",
            "status": "waiting_source",
            "started_at": started_at.isoformat(),
            "completed_at": _utc_now().isoformat(),
            "source_database_before": database_before,
            "source_database_after": database_after,
            "source_wal_before": wal_before,
            "source_wal_after": wal_after,
            "revision_namespace_before": namespace_before,
            "revision_namespace_after": namespace_after,
            "data_version_before": data_version_before[0],
            "data_version_after": data_version_after[0],
            "journal_mode_before": journal_mode_before,
            "journal_mode_after": journal_mode_after,
            "research_only": True,
            "formal_credit": False,
        })
        raise _WaitingForSource(
            "source database, WAL, data_version, or revision dependencies changed during snapshot: "
            + ",".join(name for name, changed in (
                ("database", _snapshot_dependency_identity(database_before) != _snapshot_dependency_identity(database_after)),
                ("wal", _snapshot_dependency_identity(wal_before) != _snapshot_dependency_identity(wal_after)),
                ("revision_namespace", namespace_before != namespace_after),
                ("data_version", data_version_before[0] != data_version_after[0]),
                ("journal_mode", journal_mode_before != journal_mode_after),
            ) if changed)
        )
    snapshot_pin = _pin_regular_file(snapshot, label="consistent SQLite snapshot")
    completed_at = _utc_now()
    if completed_at < started_at:
        raise _InvalidEvidence("snapshot completion clock moved backwards")
    wal_observation: dict[str, Any] = (
        {"status": "absent", "present": False, "path": str(wal_path.resolve(strict=False))}
        if wal_after is None
        else wal_after
    )
    receipt: dict[str, Any] = {
        "schema_version": (
            "integration-consistent-sqlite-snapshot.v2"
            if wal_after is None
            else "integration-consistent-sqlite-snapshot.v1"
        ),
        "status": "consistent_snapshot_created",
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "source_database_path": str(source),
        "source_observation": {
            "database": database_after,
            "wal": wal_observation,
            "revision_namespace_files": namespace_after,
            "shared_memory": shm_after,
        },
        "source_generation_before": data_version_before[0],
        "source_generation_after": data_version_after[0],
        "source_journal_mode_before": journal_mode_before,
        "source_journal_mode_after": journal_mode_after,
        "source_journal_mode_reader": journal_mode_reader,
        "snapshot": snapshot_pin,
        "snapshot_quick_check": "ok",
        "consistency": "sqlite_backup_from_single_query_only_read_transaction",
        "source_and_revision_bytes_unchanged": same_dependencies,
        "source_data_version_before": data_version_before[0],
        "source_data_version_after": data_version_after[0],
    }
    receipt_sha = _write_create_only(receipt_path, receipt)
    return {
        "snapshot_database_path": str(snapshot),
        "snapshot_database_sha256": snapshot_pin["sha256"],
        "snapshot_receipt_path": str(receipt_path.resolve()),
        "snapshot_receipt_sha256": receipt_sha,
        "snapshot_started_at": started_at.isoformat(),
        "snapshot_completed_at": completed_at.isoformat(),
        "source_observation": {
            "database": database_after,
            "wal": wal_observation,
            "revision_namespace_files": namespace_after,
            "shared_memory": shm_after,
        },
        "source_generation": data_version_after[0],
    }


def _json_file_pin(path: Path, *, label: str) -> tuple[dict[str, Any], dict[str, Any]]:
    pin = _pin_regular_file(path, label=label)
    raw = path.read_bytes()
    if _sha256(raw) != "sha256:" + str(pin["sha256"]):
        raise _InvalidEvidence(f"{label} changed during read")
    return _parse_json_object(raw, label), pin


def _readonly_watchlist_rows(repository_path: Path) -> list[tuple[str, str, int]]:
    connection = _sqlite_readonly(repository_path)
    try:
        connection.execute("BEGIN")
        columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(watchlists)")
        }
        if not {"watchlist_id", "payload_json"}.issubset(columns):
            raise _WaitingForSource("canonical watchlist database has no readable current projection")
        selected = ["watchlist_id", "payload_json"]
        selected.append("is_deleted" if "is_deleted" in columns else "0")
        selected.append("revision" if "revision" in columns else "0")
        query = f"SELECT {','.join(selected)} FROM watchlists ORDER BY watchlist_id"
        values = connection.execute(query).fetchall()
        rows: list[tuple[str, str, int]] = []
        for watchlist_id, payload_json, is_deleted, revision in values:
            if bool(is_deleted):
                continue
            if not isinstance(watchlist_id, str) or not watchlist_id.strip():
                raise _InvalidEvidence("watchlist identity is empty")
            if not isinstance(payload_json, str):
                raise _InvalidEvidence("watchlist payload is not text")
            if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
                raise _InvalidEvidence("watchlist revision is invalid")
            rows.append((watchlist_id, payload_json, revision))
        connection.execute("COMMIT")
        return rows
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()


def _symbols_from_watchlist_payload(payload: Mapping[str, Any], *, label: str) -> set[str]:
    items = payload.get("items")
    if not isinstance(items, list):
        raise _WaitingForSource(f"{label} has no readable items list")
    symbols: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise _WaitingForSource(f"{label} item {index} is not a record")
        value = item.get("stock_code", item.get("股票代號", item.get("股票代碼")))
        code = str(value or "").strip()
        if not SYMBOL_RE.fullmatch(code):
            raise _WaitingForSource(f"{label} item {index} has an invalid four-digit stock code")
        symbols.add(code)
    return symbols


def _read_current_holdings_from_trade_ledger(canonical_output_root: Path) -> tuple[set[str], list[dict[str, Any]]]:
    """Rebuild default-portfolio holdings from the same append-only source as PortfolioService."""

    trades_path = canonical_output_root.resolve(strict=True) / "portfolio" / "trades.jsonl"
    if not trades_path.exists():
        if trades_path.exists():
            raise _InvalidEvidence("portfolio trade ledger appeared during the read")
        return set(), [{"path": str(trades_path.resolve(strict=False)), "present": False}]
    pin = _pin_regular_file(trades_path, label="portfolio append-only trade ledger")
    if pin["bytes"] > MAX_LEDGER_BYTES:
        raise _WaitingForSource("portfolio trade ledger exceeds the bounded read size")
    trades: list[Trade] = []
    with trades_path.open("rb") as stream:
        for line_number, raw_line in enumerate(stream, 1):
            if line_number > MAX_LEDGER_ROWS:
                raise _WaitingForSource("portfolio trade ledger exceeds the bounded row count")
            if len(raw_line) > 256 * 1024:
                raise _InvalidEvidence(f"portfolio trade line {line_number} exceeds byte bound")
            if not raw_line.strip():
                continue
            try:
                payload = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise _WaitingForSource(
                    f"portfolio trade ledger line {line_number} is not valid UTF-8 JSON"
                ) from exc
            if not isinstance(payload, Mapping):
                raise _InvalidEvidence(f"portfolio trade ledger line {line_number} is not an object")
            string_key_payload: dict[str, Any] = {}
            for key, value in payload.items():
                if type(key) is not str:
                    raise _InvalidEvidence(
                        f"portfolio trade ledger line {line_number} contains a non-string key"
                    )
                string_key_payload[cast(str, key)] = value
            try:
                trade = Trade.from_mapping(string_key_payload)
            except (TypeError, ValueError, KeyError) as exc:
                raise _InvalidEvidence(
                    f"portfolio trade ledger line {line_number} cannot be parsed by the domain model"
                ) from exc
            # PortfolioService.list_positions defaults to the "default" ledger.
            if trade.portfolio_id == "default":
                trades.append(trade)
    _verify_file_pin(trades_path, pin, label="portfolio append-only trade ledger")
    positions = rebuild_positions(trades)
    codes: set[str] = set()
    for position in positions:
        if not position.is_holding:
            continue
        code = str(position.stock_code).strip()
        if not SYMBOL_RE.fullmatch(code):
            raise _InvalidEvidence("rebuilt portfolio holding has an invalid four-digit stock code")
        codes.add(code)
    return codes, [pin]


def _read_current_stock_scope(canonical_output_root: Path) -> dict[str, Any]:
    """Read all active watchlists and true holdings without service constructors."""

    root = canonical_output_root.resolve(strict=True)
    watchlist_dir = root / "watchlist"
    repository_path = watchlist_dir / "watchlists.db"
    legacy_files = tuple(sorted(watchlist_dir.glob("*.json"))) if watchlist_dir.is_dir() else ()
    watchlist_codes: set[str] = set()
    watchlist_pins: list[dict[str, Any]] = []
    watchlist_sources: list[dict[str, Any]] = []
    repository_active = False
    if repository_path.is_file():
        try:
            # This static discovery check is read-only; unlike WatchlistService's
            # constructor it does not create directories or initialize defaults.
            from app_module.watchlist_service import WatchlistService

            repository_active = WatchlistService._canonical_is_active(
                repository_path, legacy_files
            )
        except (OSError, sqlite3.Error, ValueError):
            repository_active = False
    if repository_active:
        db_pin = _pin_regular_file(repository_path, label="watchlist SQLite database")
        for sidecar_name in (repository_path.name + "-wal", repository_path.name + "-shm"):
            sidecar = repository_path.with_name(sidecar_name)
            if sidecar.exists():
                watchlist_pins.append(
                    _pin_regular_file(sidecar, label=f"watchlist SQLite {sidecar_name}")
                )
        rows = _readonly_watchlist_rows(repository_path)
        for watchlist_id, payload_raw, revision in rows:
            try:
                payload = json.loads(payload_raw)
            except json.JSONDecodeError as exc:
                raise _WaitingForSource(
                    f"watchlist {watchlist_id} payload is not valid JSON"
                ) from exc
            if not isinstance(payload, Mapping):
                raise _WaitingForSource(f"watchlist {watchlist_id} payload is not an object")
            current_codes = _symbols_from_watchlist_payload(
                payload, label=f"watchlist {watchlist_id}"
            )
            watchlist_codes.update(current_codes)
            watchlist_sources.append(
                {"watchlist_id": watchlist_id, "revision": revision, "symbol_count": len(current_codes)}
            )
        _verify_file_pin(repository_path, db_pin, label="watchlist SQLite database")
        watchlist_pins.insert(0, db_pin)
    elif legacy_files:
        for path in legacy_files:
            payload, pin = _json_file_pin(path, label=f"legacy watchlist {path.name}")
            watchlist_codes.update(
                _symbols_from_watchlist_payload(payload, label=f"legacy watchlist {path.stem}")
            )
            watchlist_sources.append(
                {"watchlist_id": path.stem, "revision": None, "symbol_count": len(payload.get("items", []))}
            )
            watchlist_pins.append(pin)
        for path, pin in zip(legacy_files, watchlist_pins):
            _verify_file_pin(path, pin, label=f"legacy watchlist {path.name}")
    else:
        raise _WaitingForSource("canonical watchlist source is missing or not activated")

    holding_codes, position_pins = _read_current_holdings_from_trade_ledger(root)

    symbols = tuple(sorted(watchlist_codes | holding_codes))
    if len(symbols) < 2:
        raise _WaitingForSource(
            f"current watchlist/holdings union has {len(symbols)} symbols; at least 2 are required"
        )
    if len(symbols) > 16:
        raise _WaitingForSource(
            f"current watchlist/holdings union has {len(symbols)} symbols; the bounded cycle supports at most 16"
        )
    return {
        "current_symbols": symbols,
        "watchlist_symbols": tuple(sorted(watchlist_codes)),
        "holding_symbols": tuple(sorted(holding_codes)),
        "watchlist_sources": watchlist_sources,
        "watchlist_input_pins": watchlist_pins,
        "position_input_pins": position_pins,
        "portfolio_holding_source": "append_only_trades_jsonl",
        "watchlist_storage": "canonical_sqlite" if repository_active else "legacy_json",
    }


def _verify_scope_input_pins(scope: Mapping[str, Any]) -> None:
    for category, label in (
        ("watchlist_input_pins", "watchlist input"),
        ("position_input_pins", "portfolio trade ledger"),
    ):
        pins = scope.get(category)
        if not isinstance(pins, list):
            raise _InvalidEvidence(f"{label} pins are missing")
        for index, raw_pin in enumerate(pins):
            if not isinstance(raw_pin, Mapping) or not isinstance(raw_pin.get("path"), str):
                raise _InvalidEvidence(f"{label} pin {index} is invalid")
            path = Path(str(raw_pin["path"]))
            if raw_pin.get("present") is False:
                if path.exists() or path.is_symlink():
                    raise _WaitingForSource(f"{label} appeared during cycle: {path}")
                continue
            _verify_file_pin(path, raw_pin, label=f"{label} pin {index}")


def _capacity_check(
    *,
    canonical_output_root: Path,
    research_output_root: Path,
    snapshot_upper_bound_bytes: int,
) -> dict[str, Any]:
    if isinstance(snapshot_upper_bound_bytes, bool) or not isinstance(snapshot_upper_bound_bytes, int) or snapshot_upper_bound_bytes < 0:
        raise ValueError("snapshot_upper_bound_bytes must be a non-negative integer")
    # Snapshot bytes are a one-time, separately measured copy. The remaining
    # persistent and temporary allowances match the existing bounded Direct
    # producer; neither the full-universe 35/40 budget nor the centrally configured reserve
    # is weakened.
    combined_persistent_estimate = (
        snapshot_upper_bound_bytes + CURRENT_CYCLE_PERSISTENT_BUDGET_BYTES
    )
    budget = MLStorageCapacityBudget(
        persistent_new_bytes_budget=combined_persistent_estimate,
        temporary_peak_bytes_budget=CURRENT_CYCLE_TEMPORARY_BUDGET_BYTES,
        safety_reserve_bytes=CURRENT_CYCLE_SAFETY_RESERVE_BYTES,
    )
    result = preflight_capacity(
        probe_path=research_output_root,
        budget=budget,
        stage="bounded_current_stock_research_cycle_before_snapshot",
        persistent_new_bytes_estimate=combined_persistent_estimate,
        temporary_peak_bytes_observed=CURRENT_CYCLE_TEMPORARY_BUDGET_BYTES,
    )
    return {
        "policy": "bounded_current_stock_cycle_persistent_2gib_plus_snapshot_upper_bound_temporary_2gib_reserve_20gib.v2",
        "budget": budget.as_dict(),
        "child_persistent_budget_bytes": CURRENT_CYCLE_PERSISTENT_BUDGET_BYTES,
        "temporary_peak_budget_bytes": CURRENT_CYCLE_TEMPORARY_BUDGET_BYTES,
        "safety_reserve_bytes": CURRENT_CYCLE_SAFETY_RESERVE_BYTES,
        "snapshot_upper_bound_bytes": snapshot_upper_bound_bytes,
        "combined_persistent_estimate_bytes": combined_persistent_estimate,
        "check": result.as_dict(),
        "within_budget": result.within_budget,
    }


def _cycle_non_snapshot_growth_bytes(cycle_root: Path) -> int:
    total = 0
    snapshot_root = cycle_root / "snapshot"
    for root_text, directories, file_names in os.walk(cycle_root, topdown=True, followlinks=False):
        root = Path(root_text)
        kept_directories: list[str] = []
        for name in directories:
            path = root / name
            if path == snapshot_root:
                continue
            if path.is_symlink():
                raise _InvalidEvidence(f"cycle output contains a linked directory: {path}")
            kept_directories.append(name)
        directories[:] = kept_directories
        for name in file_names:
            path = root / name
            if path.is_symlink():
                raise _InvalidEvidence(f"cycle output contains a linked file: {path}")
            try:
                info = path.stat()
            except OSError as exc:
                raise _WaitingForSource(f"cycle output size cannot be observed: {path}") from exc
            if not path.is_file():
                raise _InvalidEvidence(f"cycle output contains a non-regular file: {path}")
            total += info.st_size
    return total


def _borrow_or_acquire_reservation(
    lock_path: Path,
    caller_reservation: MLStorageChainReservation | None,
) -> tuple[MLStorageChainReservation | None, bool]:
    """Reuse an active caller-owned reservation or acquire this cycle's own.

    The boolean is true only when this function acquired the reservation. A
    borrowed reservation is never released by the cycle; the caller retains
    ownership through its wider raw/Direct execution chain.
    """

    expected_path = Path(lock_path).resolve()
    if caller_reservation is None:
        acquired = acquire_heavy_chain_reservation(expected_path)
        return acquired, acquired is not None
    if not isinstance(caller_reservation, MLStorageChainReservation):
        raise _InvalidEvidence("caller reservation is not an ML heavy-chain reservation")
    if (
        caller_reservation.owner_pid != os.getpid()
        or caller_reservation.path.resolve() != expected_path
        or bool(getattr(caller_reservation, "_released", True))
        or bool(getattr(getattr(caller_reservation, "_handle", None), "closed", True))
    ):
        raise _InvalidEvidence("caller reservation is not active for this canonical lock path")
    return caller_reservation, False


def _record_cycle_growth(state: dict[str, Any], cycle_root: Path) -> int:
    growth = _cycle_non_snapshot_growth_bytes(cycle_root)
    capacity = state.setdefault("capacity", {})
    if not isinstance(capacity, dict):
        raise _InvalidEvidence("cycle capacity status is not a mutable object")
    prior = capacity.get("measured_non_snapshot_persistent_growth_peak_bytes", 0)
    if isinstance(prior, bool) or not isinstance(prior, int) or prior < 0:
        prior = 0
    peak = max(prior, growth)
    capacity["measured_non_snapshot_persistent_growth_bytes"] = growth
    capacity["measured_non_snapshot_persistent_growth_peak_bytes"] = peak
    capacity["child_persistent_growth_budget_bytes"] = CURRENT_CYCLE_PERSISTENT_BUDGET_BYTES
    if peak > CURRENT_CYCLE_PERSISTENT_BUDGET_BYTES:
        raise StorageCapacityError(
            "bounded current-stock cycle exceeded its 2 GiB non-snapshot persistent growth cap",
            preflight={
                "stage": state.get("stage"),
                "observed_growth_bytes": growth,
                "peak_growth_bytes": peak,
                "persistent_growth_budget_bytes": CURRENT_CYCLE_PERSISTENT_BUDGET_BYTES,
            },
        )
    return growth


def _optional_file_pin(path: Path, *, label: str) -> dict[str, Any] | None:
    if not path.exists():
        if path.is_symlink():
            raise _InvalidEvidence(f"{label} is a dangling link")
        return None
    try:
        return _pin_regular_file(path, label=label)
    except FileNotFoundError as exc:
        raise _WaitingForSource(f"{label} changed while being pinned") from exc


def _source_observation_pins(source_database: Path) -> dict[str, Any]:
    """Pin a stable current source revision without creating a backup copy."""

    source = source_database.resolve(strict=True)
    wal_path = source.with_name(source.name + "-wal")
    shm_path = source.with_name(source.name + "-shm")
    database_before = _pin_regular_file(source, label="source SQLite database")
    wal_before = _optional_file_pin(wal_path, label="source SQLite WAL")
    shm_before = _optional_file_pin(shm_path, label="source SQLite shared-memory file")
    namespace_before = _source_namespace_pins(source)
    try:
        connection = _sqlite_readonly(source, immutable=wal_before is None)
        try:
            journal_row = connection.execute("PRAGMA journal_mode").fetchone()
            version_before = connection.execute("PRAGMA data_version").fetchone()
            if wal_before is None:
                journal_mode = _sqlite_header_journal_mode(source)
                journal_mode_reader = "sqlite_file_header_read_write_version.v1"
            else:
                if not journal_row or not isinstance(journal_row[0], str):
                    raise _InvalidEvidence("SQLite journal_mode did not return text")
                journal_mode = journal_row[0].lower()
                journal_mode_reader = "sqlite_pragma"
            if not version_before or type(version_before[0]) is not int:
                raise _InvalidEvidence("SQLite PRAGMA data_version did not return an integer")
            connection.execute("BEGIN")
            connection.execute("SELECT name FROM sqlite_master ORDER BY name LIMIT 1").fetchone()
            journal_after_row = connection.execute("PRAGMA journal_mode").fetchone()
            version_after = connection.execute("PRAGMA data_version").fetchone()
            if wal_before is None:
                journal_mode_after = _sqlite_header_journal_mode(source)
            else:
                if not journal_after_row or not isinstance(journal_after_row[0], str):
                    raise _InvalidEvidence("SQLite post-read journal_mode did not return text")
                journal_mode_after = journal_after_row[0].lower()
            connection.execute("COMMIT")
            if not version_after or type(version_after[0]) is not int:
                raise _InvalidEvidence("SQLite post-read data_version is invalid")
        finally:
            if connection.in_transaction:
                connection.rollback()
            connection.close()
    except (OSError, sqlite3.Error) as exc:
        raise _WaitingForSource(f"source SQLite database cannot be observed read-only: {exc}") from exc
    database_after = _pin_regular_file(source, label="source SQLite database")
    wal_after = _optional_file_pin(wal_path, label="source SQLite WAL")
    shm_after = _optional_file_pin(shm_path, label="source SQLite shared-memory file")
    namespace_after = _source_namespace_pins(source)
    if (
        _snapshot_dependency_identity(database_before) != _snapshot_dependency_identity(database_after)
        or _snapshot_dependency_identity(wal_before) != _snapshot_dependency_identity(wal_after)
        or namespace_before != namespace_after
        or version_before[0] != version_after[0]
        or journal_mode != journal_mode_after
    ):
        raise _WaitingForSource("source DB/WAL/revision pins changed during read-only source observation")
    return {
        "database": database_after,
        "wal": (
            {"status": "absent", "present": False, "path": str(wal_path.resolve(strict=False))}
            if wal_after is None
            else {"status": "present", "present": True, **wal_after}
        ),
        "revision_namespace_files": namespace_after,
        "shared_memory_before": shm_before,
        "shared_memory_after": shm_after,
        "source_generation": version_after[0],
        "journal_mode": journal_mode,
        "journal_mode_before": journal_mode,
        "journal_mode_after": journal_mode_after,
        "journal_mode_reader": journal_mode_reader,
    }


def _stable_pin_identity(value: object) -> object:
    if isinstance(value, Mapping):
        if value.get("present") is False and value.get("status") == "absent":
            return {"status": "absent", "path": value.get("path")}
        if {"path", "bytes", "sha256"}.issubset(value):
            return {
                "path": value.get("path"),
                "bytes": value.get("bytes"),
                **({"mtime_ns": value.get("mtime_ns")} if "mtime_ns" in value else {}),
                "sha256": value.get("sha256"),
                **({"namespace": value.get("namespace")} if "namespace" in value else {}),
            }
        return {str(key): _stable_pin_identity(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_stable_pin_identity(item) for item in value]
    return value


def _snapshot_dependency_identity(pin: object) -> object:
    """來源以實際內容驗證；空 WAL 與不存在皆沒有未併入的交易頁。"""
    if pin is None or (isinstance(pin, Mapping) and (
        pin.get("present") is False or (
            pin.get("bytes") == 0
            and pin.get("sha256") == hashlib.sha256(b"").hexdigest()
        )
    )):
        return None
    if isinstance(pin, Mapping):
        return {key: pin.get(key) for key in ("path", "bytes", "sha256")}
    return pin


def _stable_source_dependency_identity(source_observation: Mapping[str, Any]) -> object:
    return _stable_pin_identity(
        {
            "database": _snapshot_dependency_identity(source_observation.get("database")),
            "wal": _snapshot_dependency_identity(source_observation.get("wal")),
            "revision_namespace_files": source_observation.get("revision_namespace_files"),
        }
    )


def _current_b_semantic_identity(
    *,
    b_terminal: Mapping[str, Any],
    symbols: Sequence[str],
    source_date: str,
    repository_root: Path,
) -> dict[str, str]:
    """Hash stable B mapping and selected transformed vectors, excluding run clocks."""

    feature_registry_path_value = b_terminal.get("feature_registry_path")
    if not isinstance(feature_registry_path_value, str) or not feature_registry_path_value:
        raise _InvalidEvidence("B terminal feature registry path is missing")
    feature_registry_path = resolve_ml_research_output_path(
        Path(feature_registry_path_value), repository_root=repository_root
    )
    feature_registry_pin = _pin_regular_file(feature_registry_path, label="B feature registry")
    feature_registry_raw = feature_registry_path.read_bytes()
    if _sha256(feature_registry_raw) != "sha256:" + str(feature_registry_pin["sha256"]):
        raise _InvalidEvidence("B feature registry changed during read")
    try:
        feature_registry = json.loads(feature_registry_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _InvalidEvidence("B feature registry is invalid UTF-8 JSON") from exc
    _verify_file_pin(feature_registry_path, feature_registry_pin, label="B feature registry")
    feature_registry_sha = _sha256_pin(
        b_terminal.get("feature_registry_sha256"), "B feature registry canonical SHA"
    )
    feature_registry_bytes_sha = _sha256_pin(
        b_terminal.get("feature_registry_bytes_sha256"), "B feature registry bytes SHA"
    )
    if (
        "sha256:" + feature_registry_pin["sha256"] != feature_registry_bytes_sha
        or _canonical_sha256(feature_registry) != feature_registry_sha
        or not isinstance(feature_registry, list)
        or not feature_registry
        or any(not isinstance(item, Mapping) for item in feature_registry)
    ):
        raise _InvalidEvidence("B feature registry actual bytes or canonical content differ")
    feature_ids = [item.get("feature_id") for item in feature_registry]
    required_price_feature_ids = {
        B_DAILY_FEATURE_IDS[name]
        for name in ("open", "high", "low", "close", "volume", "amount")
    }
    if (
        any(not isinstance(item, str) or not item for item in feature_ids)
        or len(set(feature_ids)) != len(feature_ids)
        or not required_price_feature_ids.issubset(set(feature_ids))
    ):
        raise _InvalidEvidence("B feature registry identity or required OHLCV/turnover mapping is invalid")
    feature_specs = {str(item["feature_id"]): item for item in feature_registry}

    adapted_path_value = b_terminal.get("adapted_manifest_path")
    if not isinstance(adapted_path_value, str) or not adapted_path_value:
        raise _InvalidEvidence("B adapted manifest path is missing")
    adapted_path = resolve_ml_research_output_path(
        Path(adapted_path_value), repository_root=repository_root
    )
    adapted_manifest, adapted_pin = _json_file_pin(
        adapted_path, label="B adapted manifest"
    )
    adapted_bytes_sha = _sha256_pin(
        b_terminal.get("adapted_manifest_sha256"), "B adapted manifest bytes SHA"
    )
    adapted_canonical_sha = _sha256_pin(
        b_terminal.get("adapted_manifest_canonical_sha256"),
        "B adapted manifest canonical SHA",
    )
    if (
        "sha256:" + adapted_pin["sha256"] != adapted_bytes_sha
        or _sha256_pin(adapted_manifest.get("manifest_hash"), "adapted manifest self-hash")
        != adapted_canonical_sha
        or _canonical_sha256(_without_field(adapted_manifest, "manifest_hash"))
        != adapted_canonical_sha
        or _sha256_pin(
            adapted_manifest.get("feature_registry_sha256"),
            "adapted manifest feature registry SHA",
        )
        != feature_registry_sha
        or adapted_manifest.get("features") != feature_registry
    ):
        raise _InvalidEvidence("B adapted manifest actual bytes, mapping, or registry differs")
    temporal_semantics = adapted_manifest.get("temporal_semantics")
    if not isinstance(temporal_semantics, Mapping) or (
        temporal_semantics.get("event_date_distinct_from_available_at") is not True
        or temporal_semantics.get("current_restated") is not True
        or temporal_semantics.get("historical_pit_eligible") is not False
    ):
        raise _InvalidEvidence("B adapted temporal semantics are invalid")
    transform_contract = {
        "schema_version": adapted_manifest.get("schema_version"),
        "stage": adapted_manifest.get("stage"),
        "dataset_id": adapted_manifest.get("dataset_id"),
        "format": adapted_manifest.get("format"),
        "candidate_schema_version": adapted_manifest.get("candidate_schema_version"),
        "row_schema": adapted_manifest.get("row_schema"),
        "temporal_semantics": {
            "event_date_distinct_from_available_at": True,
            "current_restated": True,
            "historical_pit_eligible": False,
        },
        "feature_registry_sha256": feature_registry_sha,
    }
    if any(not isinstance(transform_contract[key], str) or not transform_contract[key] for key in (
        "schema_version", "stage", "dataset_id", "format", "candidate_schema_version", "row_schema"
    )):
        raise _InvalidEvidence("B adapted transform contract is incomplete")

    shard_values = b_terminal.get("stored_shards")
    if not isinstance(shard_values, list) or not shard_values:
        raise _InvalidEvidence("B terminal stored numeric shards are missing")
    wanted_symbols = set(symbols)
    if len(wanted_symbols) != len(symbols) or not wanted_symbols:
        raise _InvalidEvidence("B semantic scope symbols are empty or duplicated")
    selected_rows: dict[str, dict[str, Any]] = {}
    total_uncompressed = 0
    for index, descriptor in enumerate(shard_values):
        if not isinstance(descriptor, Mapping):
            raise _InvalidEvidence(f"B numeric shard descriptor {index} is invalid")
        path_value = descriptor.get("path")
        if not isinstance(path_value, str) or not path_value:
            raise _InvalidEvidence(f"B numeric shard descriptor {index} has no path")
        shard_path = resolve_ml_research_output_path(
            Path(path_value), repository_root=repository_root
        )
        shard_pin = _pin_regular_file(shard_path, label=f"B numeric shard {index}")
        bytes_sha = _sha256_pin(descriptor.get("bytes_sha256"), f"B numeric shard {index} bytes SHA")
        compressed_sha = _sha256_pin(
            descriptor.get("compressed_sha256"), f"B numeric shard {index} compressed SHA"
        )
        expected_uncompressed_sha = _sha256_pin(
            descriptor.get("uncompressed_sha256"), f"B numeric shard {index} uncompressed SHA"
        )
        row_count_expected = descriptor.get("row_count")
        if (
            "sha256:" + shard_pin["sha256"] != bytes_sha
            or bytes_sha != compressed_sha
            or shard_pin["bytes"] > MAX_B_SEMANTIC_SHARD_BYTES
            or type(row_count_expected) is not int
            or row_count_expected < 1
        ):
            raise _InvalidEvidence(f"B numeric shard {index} actual pin or size differs")
        uncompressed_digest = hashlib.sha256()
        shard_row_count = 0
        try:
            with gzip.open(shard_path, "rb") as stream:
                while True:
                    raw_line = stream.readline(MAX_B_SEMANTIC_LINE_BYTES + 1)
                    if not raw_line:
                        break
                    if (
                        len(raw_line) > MAX_B_SEMANTIC_LINE_BYTES
                        or not raw_line.endswith(b"\n")
                        or not raw_line.strip()
                    ):
                        raise _InvalidEvidence(f"B numeric shard {index} has an invalid JSONL line")
                    total_uncompressed += len(raw_line)
                    if total_uncompressed > MAX_B_SEMANTIC_UNCOMPRESSED_BYTES:
                        raise _InvalidEvidence("B numeric shards exceed the semantic verification byte bound")
                    uncompressed_digest.update(raw_line)
                    shard_row_count += 1
                    try:
                        row = json.loads(raw_line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise _InvalidEvidence(f"B numeric shard {index} contains invalid JSON") from exc
                    if not isinstance(row, Mapping):
                        raise _InvalidEvidence(f"B numeric shard {index} row is not an object")
                    symbol = row.get("symbol")
                    if symbol not in wanted_symbols or row.get("event_date") != source_date:
                        continue
                    if (
                        row.get("schema_version") != "ml-pit-observation.v1"
                        or row.get("dataset_id") != "all_field_enriched"
                        or row.get("source_table") != "daily_prices"
                        or row.get("source_id") != "daily_prices"
                        or row.get("family") != "daily_prices"
                        or row.get("historical_pit_eligible") is not False
                    ):
                        raise _InvalidEvidence(f"B current vector identity is invalid for {symbol}")
                    if str(symbol) in selected_rows:
                        raise _InvalidEvidence(f"B current numeric vector is duplicated for {symbol}")
                    values = row.get("values")
                    if not isinstance(values, list) or not values:
                        raise _InvalidEvidence(f"B current numeric vector is empty for {symbol}")
                    semantic_values: list[dict[str, Any]] = []
                    seen_feature_ids: set[str] = set()
                    for value in values:
                        if not isinstance(value, Mapping):
                            raise _InvalidEvidence(f"B current feature value is malformed for {symbol}")
                        feature_id = value.get("feature_id")
                        value_int = value.get("value_int")
                        scale = value.get("scale")
                        unit = value.get("unit")
                        if (
                            not isinstance(feature_id, str)
                            or feature_id not in set(feature_ids)
                            or feature_id in seen_feature_ids
                            or isinstance(value_int, bool)
                            or not isinstance(value_int, int)
                            or isinstance(scale, bool)
                            or not isinstance(scale, int)
                            or not 0 <= scale <= 12
                            or not isinstance(unit, str)
                            or not unit
                            or value.get("formal_training_eligible") is not False
                        ):
                            raise _InvalidEvidence(f"B current feature mapping/value is invalid for {symbol}")
                        registered = feature_specs[feature_id]
                        registered_scale = registered.get("scale")
                        registered_unit = registered.get("unit")
                        if (
                            type(registered_scale) is not int
                            or registered_scale != scale
                            or not isinstance(registered_unit, str)
                            or registered_unit != unit
                        ):
                            raise _InvalidEvidence(
                                f"B current value scale/unit differs from registry for {feature_id}"
                            )
                        seen_feature_ids.add(feature_id)
                        semantic_values.append(
                            {
                                "feature_id": feature_id,
                                "value_int": value_int,
                                "scale": scale,
                                "unit": unit,
                                "formal_training_eligible": False,
                            }
                        )
                    if not required_price_feature_ids.issubset(seen_feature_ids):
                        raise _InvalidEvidence(f"B current vector lacks mapped OHLCV/turnover values for {symbol}")
                    masks: dict[str, list[str]] = {}
                    for mask_name in ("missing_mask", "quality_blocked_mask", "staleness_mask"):
                        raw_mask = row.get(mask_name)
                        if not isinstance(raw_mask, list) or any(not isinstance(item, str) for item in raw_mask):
                            raise _InvalidEvidence(f"B current vector {mask_name} is invalid for {symbol}")
                        if len(raw_mask) != len(set(raw_mask)) or not set(raw_mask).issubset(set(feature_ids)):
                            raise _InvalidEvidence(f"B current vector {mask_name} does not match the registry for {symbol}")
                        masks[mask_name] = sorted(raw_mask)
                    if any(required_price_feature_ids.intersection(mask) for mask in masks.values()):
                        raise _InvalidEvidence(f"B current vector masks a required OHLCV/turnover value for {symbol}")
                    selected_rows[str(symbol)] = {
                        "symbol": str(symbol),
                        "event_date": source_date,
                        "values": sorted(semantic_values, key=lambda item: item["feature_id"]),
                        **masks,
                    }
        except (OSError, EOFError, gzip.BadGzipFile) as exc:
            raise _InvalidEvidence(f"B numeric shard {index} is unreadable or truncated") from exc
        if (
            shard_row_count != row_count_expected
            or "sha256:" + uncompressed_digest.hexdigest() != expected_uncompressed_sha
        ):
            raise _InvalidEvidence(f"B numeric shard {index} uncompressed bytes or row count differ")
        _verify_file_pin(shard_path, shard_pin, label=f"B numeric shard {index}")
    if set(selected_rows) != wanted_symbols:
        missing = sorted(wanted_symbols - set(selected_rows))
        raise _InvalidEvidence("B adapted numeric store lacks current rows for: " + ",".join(missing))
    current_vectors = [selected_rows[symbol] for symbol in symbols]
    return {
        "schema_version": "current-stock-research-b-semantic-identity.v1",
        "feature_registry_sha256": feature_registry_sha,
        "transform_contract_sha256": _canonical_sha256(transform_contract),
        "current_vector_semantic_sha256": _canonical_sha256(current_vectors),
    }


def _current_cycle_reuse_key(
    *,
    source_date: str,
    scope: Mapping[str, Any],
    source_observation: Mapping[str, Any],
    price_fingerprints: Mapping[str, str],
    official_raw_input_identity: Mapping[str, Any],
    b_semantic_identity: Mapping[str, str],
) -> str:
    scope_identity = {
        "current_symbols": list(scope["current_symbols"]),
        "watchlist_symbols": list(scope["watchlist_symbols"]),
        "holding_symbols": list(scope["holding_symbols"]),
        "watchlist_input_pins": _stable_pin_identity(
            scope.get("watchlist_input_pins", [])
        ),
        "position_input_pins": _stable_pin_identity(
            scope.get("position_input_pins", [])
        ),
    }
    payload = {
        "schema_version": "current-stock-research-reuse-key.v4",
        "source_date": source_date,
        "scope_identity_sha256": _canonical_sha256(scope_identity),
        "ordered_scope_symbols": list(scope["current_symbols"]),
        "source_observation": _stable_pin_identity(
            {
                "database": source_observation.get("database"),
                "wal": source_observation.get("wal"),
                "revision_namespace_files": source_observation.get("revision_namespace_files"),
            }
        ),
        "current_price_row_fingerprint_sha256_by_symbol": dict(price_fingerprints),
        "official_raw_input_identity": dict(official_raw_input_identity),
        "b_semantic_identity": dict(b_semantic_identity),
    }
    return _canonical_sha256(payload)


def _cycle_index_entry_digest(entry: Mapping[str, Any]) -> str:
    return _canonical_sha256(_without_field(entry, "entry_sha256"))


def _verify_public_ml_registry_index_binding(
    index_path: Path,
    *,
    repository_root: Path,
    expected_run_id: str,
    expected_record_path: Path,
    expected_record_sha256: str,
) -> str:
    """Verify the same index/record contract used by the public ML reader."""

    from app_module.stock_research_report_provider_adapters import (
        CurrentRestatedMLRunRegistry,
    )

    reader = CurrentRestatedMLRunRegistry(repository_root=repository_root)
    actual_index_path = resolve_ml_research_output_path(
        index_path,
        repository_root=repository_root,
        access="read",
    ).resolve(strict=True)
    matching_roots = [
        registry_root.resolve(strict=True)
        for registry_root in reader._registry_roots_for_read()
        if os.path.normcase(
            os.path.abspath(str((registry_root / "run_index.jsonl").resolve(strict=False)))
        )
        == os.path.normcase(os.path.abspath(str(actual_index_path)))
    ]
    if len(matching_roots) != 1:
        raise _InvalidEvidence(
            "reusable ML registry index is not an exact public reader index"
        )
    registry_root = matching_roots[0]
    expected_path = expected_record_path.resolve(strict=True)
    try:
        expected_path.relative_to(registry_root)
    except ValueError as exc:
        raise _InvalidEvidence("reusable ML registry record escaped its canonical registry root") from exc

    index_pin = _pin_regular_file(actual_index_path, label="reusable ML registry index")
    if index_pin["bytes"] > 32 * 1024 * 1024:
        raise _InvalidEvidence("reusable ML registry index exceeds the public reader byte bound")
    index_bytes = actual_index_path.read_bytes()
    if _sha256(index_bytes) != "sha256:" + str(index_pin["sha256"]):
        raise _InvalidEvidence("reusable ML registry index changed during read")
    lines = index_bytes.splitlines()
    if len(lines) > 100_000:
        raise _InvalidEvidence("reusable ML registry index exceeds the public reader row bound")

    seen_run_ids: set[str] = set()
    matching: list[tuple[Path, str]] = []
    for sequence, line in enumerate(lines, 1):
        if not line.strip():
            continue
        entry = _parse_json_object(line, f"reusable ML registry index entry {sequence}")
        run_id = entry.get("run_id")
        relative_value = entry.get("record_path")
        if (
            entry.get("schema_version") != "current-restated-stock-research-registry-index.v1"
            or not isinstance(run_id, str)
            or not run_id
            or not isinstance(relative_value, str)
            or not relative_value
        ):
            raise _InvalidEvidence(f"reusable ML registry index entry {sequence} has invalid schema or required fields")
        if run_id in seen_run_ids:
            raise _InvalidEvidence("reusable ML registry index contains a duplicate run id")
        seen_run_ids.add(run_id)
        relative_path = Path(relative_value)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise _InvalidEvidence(f"reusable ML registry index entry {sequence} has an unsafe record path")
        record_path = (registry_root / relative_path).resolve(strict=True)
        try:
            record_path.relative_to(registry_root)
        except ValueError as exc:
            raise _InvalidEvidence(f"reusable ML registry index entry {sequence} escaped its registry root") from exc
        record_pin = _pin_regular_file(record_path, label=f"reusable ML registry record {run_id}")
        if record_pin["bytes"] > 16 * 1024 * 1024:
            raise _InvalidEvidence(f"reusable ML registry record {run_id} exceeds the public reader byte bound")
        record, parsed_pin = _json_file_pin(record_path, label=f"reusable ML registry record {run_id}")
        if parsed_pin != record_pin:
            raise _InvalidEvidence(f"reusable ML registry record {run_id} changed during validation")
        indexed_sha = _sha256_pin(entry.get("record_sha256"), f"registry index record SHA for {run_id}")
        if "sha256:" + str(record_pin["sha256"]) != indexed_sha:
            raise _InvalidEvidence(f"reusable ML registry record {run_id} does not match its indexed hash")
        if (
            record.get("schema_version") != "current-restated-stock-research-registry.v1"
            or record.get("run_id") != run_id
            or record.get("status") != "verified_research_sidecar"
            or record.get("historical_pit_eligible") is not False
            or record.get("formal_calibration_performed") is not False
            or record.get("formal_qualified") is not False
            or record.get("production_action_allowed") is not False
        ):
            raise _InvalidEvidence(f"reusable ML registry record {run_id} violates the public reader contract")
        if run_id == expected_run_id:
            matching.append((record_path, indexed_sha))

    _verify_file_pin(actual_index_path, index_pin, label="reusable ML registry index")
    if len(matching) != 1:
        raise _InvalidEvidence("reusable ML registry index does not contain exactly one target run")
    matched_path, matched_sha = matching[0]
    expected_sha = _sha256_pin(expected_record_sha256, "reusable target registry record SHA")
    if (
        os.path.normcase(os.path.abspath(str(matched_path)))
        != os.path.normcase(os.path.abspath(str(expected_path)))
        or matched_sha != expected_sha
    ):
        raise _InvalidEvidence("reusable ML registry index does not bind the exact target record")
    return "sha256:" + str(index_pin["sha256"])


def _verify_public_registry_selects_reusable_run(
    *,
    repository_root: Path,
    run_id: str,
    cycle_id: str,
    source_date: str,
    symbols: Sequence[str],
    price_fingerprints: Mapping[str, str],
    model_manifest_sha256: str,
    model_bundle_sha256: str,
) -> None:
    """Require the public report reader to select this exact reusable run."""

    from app_module.stock_research_report_provider_adapters import (
        CurrentRestatedMLRunRegistry,
    )

    reader_now = _utc_now()
    reader = CurrentRestatedMLRunRegistry(
        repository_root=repository_root,
        now_provider=lambda: reader_now,
    )
    cutoff = reader_now.astimezone(_TAIPEI).date()
    for symbol in symbols:
        candidate = reader(
            symbol,
            cutoff,
            context={
                "stock_code": symbol,
                "ml_scope_mode": "current_stock_research",
                "current_event_date": source_date,
                "current_price_row_fingerprint_sha256": price_fingerprints[symbol],
            },
        )
        if not isinstance(candidate, Mapping):
            raise _InvalidEvidence(
                f"public ML registry reader cannot select the exact reusable run for {symbol}"
            )
        candidate_manifest_sha = _sha256_pin(
            candidate.get("model_manifest_sha256"),
            f"public reader model manifest SHA for {symbol}",
        )
        candidate_bundle_sha = _sha256_pin(
            candidate.get("model_bundle_sha256"),
            f"public reader model bundle SHA for {symbol}",
        )
        if (
            candidate.get("run_id") != run_id
            or candidate.get("cycle_id") != cycle_id
            or candidate.get("event_date") != source_date
            or candidate.get("current_price_row_fingerprint_sha256") != price_fingerprints[symbol]
            or candidate_manifest_sha != _sha256_pin(model_manifest_sha256, "expected model manifest SHA")
            or candidate_bundle_sha != _sha256_pin(model_bundle_sha256, "expected model bundle SHA")
        ):
            raise _InvalidEvidence(
                f"public ML registry reader cannot select the exact reusable run for {symbol}"
            )


def _verify_reusable_b_semantics(
    *,
    old_b_terminal: Mapping[str, Any],
    old_b_terminal_pins: Mapping[str, Any],
    expected_current_b_semantic_identity: Mapping[str, str],
    symbols: Sequence[str],
    source_date: str,
    repository_root: Path,
) -> dict[str, str]:
    pinned = old_b_terminal_pins.get("b_semantic_identity")
    if not isinstance(pinned, Mapping) or dict(pinned) != dict(expected_current_b_semantic_identity):
        raise _InvalidEvidence("reusable cycle B semantic identity differs from current B input")
    actual = _current_b_semantic_identity(
        b_terminal=old_b_terminal,
        symbols=symbols,
        source_date=source_date,
        repository_root=repository_root,
    )
    if actual != dict(expected_current_b_semantic_identity):
        raise _InvalidEvidence("reusable B mapping or current numeric vectors differ")
    return actual


def _read_cycle_reuse_index(index_path: Path, *, cycles_root: Path) -> list[dict[str, Any]]:
    if not index_path.exists():
        if index_path.is_symlink():
            raise _InvalidEvidence("current-stock cycle index is a dangling link")
        return []
    pin_before = _pin_regular_file(index_path, label="current-stock research cycle index")
    if pin_before["bytes"] > 32 * 1024 * 1024:
        raise _InvalidEvidence("current-stock research cycle index exceeds its byte bound")
    raw = index_path.read_bytes()
    entries: list[dict[str, Any]] = []
    run_ids: set[str] = set()
    terminal_paths: set[str] = set()
    for sequence, line in enumerate(raw.splitlines(), 1):
        if not line or len(line) > 32 * 1024:
            raise _InvalidEvidence("current-stock research cycle index line is empty or oversized")
        entry = _parse_json_object(line, "current-stock cycle index entry")
        if (
            entry.get("schema_version") != "current-stock-research-cycle-index.v1"
            or entry.get("sequence") != sequence
            or entry.get("entry_sha256") != _cycle_index_entry_digest(entry)
        ):
            raise _InvalidEvidence("current-stock research cycle index entry identity/hash is invalid")
        run_id = entry.get("raw_run_id")
        terminal_path_value = entry.get("terminal_receipt_path")
        if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
            raise _InvalidEvidence("current-stock research cycle index run id is invalid")
        if not isinstance(terminal_path_value, str) or not terminal_path_value:
            raise _InvalidEvidence("current-stock research cycle index terminal path is missing")
        terminal_path = Path(terminal_path_value).resolve(strict=False)
        cycles_root_resolved = cycles_root.resolve(strict=True)
        try:
            terminal_path.relative_to(cycles_root_resolved)
        except ValueError as exc:
            raise _InvalidEvidence("current-stock research cycle index path escaped its root") from exc
        canonical_terminal = os.path.normcase(os.path.abspath(str(terminal_path)))
        if run_id in run_ids or canonical_terminal in terminal_paths:
            raise _InvalidEvidence("current-stock research cycle index contains a duplicate run/path")
        run_ids.add(run_id)
        terminal_paths.add(canonical_terminal)
        if not isinstance(entry.get("reuse_key_sha256"), str) or not SHA256_RE.fullmatch(
            str(entry.get("reuse_key_sha256"))
        ):
            raise _InvalidEvidence("current-stock research cycle index reuse key is invalid")
        entries.append(entry)
    _verify_file_pin(index_path, pin_before, label="current-stock research cycle index")
    return entries


def _verify_cycle_reuse_target(
    entry: Mapping[str, Any],
    *,
    cycles_root: Path,
    expected_reuse_key_sha256: str,
    source_date: str,
    symbols: Sequence[str],
    price_fingerprints: Mapping[str, str],
    official_raw_input_identity: Mapping[str, Any],
    current_b_semantic_identity: Mapping[str, str],
    repository_root: Path,
) -> dict[str, Any]:
    terminal_path = Path(str(entry.get("terminal_receipt_path"))).resolve(strict=True)
    terminal_path = resolve_ml_research_output_path(
        terminal_path, repository_root=repository_root
    )
    try:
        terminal_path.relative_to(cycles_root.resolve(strict=True))
    except ValueError as exc:
        raise _InvalidEvidence("reusable cycle terminal escaped current-stock cycle root") from exc
    terminal, terminal_pin = _json_file_pin(terminal_path, label="reusable cycle terminal")
    terminal_sha = _sha256_pin(entry.get("terminal_receipt_sha256"), "indexed terminal SHA")
    if (
        "sha256:" + terminal_pin["sha256"] != terminal_sha
        or terminal.get("schema_version") != "current-stock-research-cycle-terminal.v1"
        or terminal.get("status") != "completed"
        or terminal.get("source_date") != source_date
        or terminal.get("current_symbols") != list(symbols)
        or terminal.get("same_run_pins", {}).get("reuse_key_sha256") != expected_reuse_key_sha256
    ):
        raise _InvalidEvidence("indexed completed cycle does not match the current exact input identity")
    registry = terminal.get("registry")
    if not isinstance(registry, Mapping):
        raise _InvalidEvidence("reusable cycle has no verified registry record pins")
    record_path_value = registry.get("record_path")
    if not isinstance(record_path_value, str) or not record_path_value:
        raise _InvalidEvidence("reusable cycle registry record path is missing")
    record_path = resolve_ml_research_output_path(
        Path(record_path_value), repository_root=repository_root
    )
    record, record_pin = _json_file_pin(record_path, label="reusable ML registry record")
    record_sha = _sha256_pin(registry.get("record_sha256"), "reusable registry record SHA")
    if (
        "sha256:" + record_pin["sha256"] != record_sha
        or record.get("schema_version") != "current-restated-stock-research-registry.v1"
        or record.get("run_id") != registry.get("run_id")
        or record.get("status") != "verified_research_sidecar"
        or record.get("scope_mode") != "current_stock_research"
        or record.get("cycle_id") != terminal.get("cycle_id")
        or record.get("event_date") != source_date
        or record.get("symbols") != list(symbols)
        or record.get("current_price_row_fingerprint_sha256_by_symbol") != dict(price_fingerprints)
    ):
        raise _InvalidEvidence("reusable ML registry record does not match the exact prior cycle")
    if record.get("current_price_row_fingerprint_sha256_by_symbol") != dict(price_fingerprints):
        raise _InvalidEvidence("reusable registry price fingerprints differ from the current B input")
    price_rows_path_value = record.get("current_price_rows_source_path")
    price_rows_sha = _sha256_pin(
        record.get("current_price_rows_source_sha256"),
        "reusable current price rows SHA",
    )
    if not isinstance(price_rows_path_value, str) or not price_rows_path_value:
        raise _InvalidEvidence("reusable current price rows source path is missing")
    price_rows_path = resolve_ml_research_output_path(
        Path(price_rows_path_value), repository_root=repository_root
    )
    price_rows_pin = _pin_regular_file(price_rows_path, label="reusable current price rows")
    if "sha256:" + price_rows_pin["sha256"] != price_rows_sha:
        raise _InvalidEvidence("reusable current price rows actual bytes differ from registry pin")
    old_price_fingerprints, old_raw_identity = _current_price_fingerprints(
        b_terminal={
            "projection_observations_path": str(price_rows_path),
            "projection_observations_sha256": price_rows_sha,
        },
        symbols=symbols,
        source_date=source_date,
    )
    if (
        old_price_fingerprints != dict(price_fingerprints)
        or old_raw_identity != dict(official_raw_input_identity)
    ):
        raise _InvalidEvidence("reusable B source rows do not match current official raw inputs")

    b_terminal_pins = terminal.get("same_run_pins")
    if not isinstance(b_terminal_pins, Mapping):
        raise _InvalidEvidence("reusable cycle has no exact B source pins")
    old_b_path_value = b_terminal_pins.get("b_terminal_receipt_path")
    old_b_sha = _sha256_pin(
        b_terminal_pins.get("b_terminal_receipt_sha256"), "reusable B terminal SHA"
    )
    if not isinstance(old_b_path_value, str) or not old_b_path_value:
        raise _InvalidEvidence("reusable B terminal path is missing")
    old_b_path = resolve_ml_research_output_path(
        Path(old_b_path_value), repository_root=repository_root
    )
    old_b, old_b_pin = _json_file_pin(old_b_path, label="reusable B terminal")
    if (
        "sha256:" + old_b_pin["sha256"] != old_b_sha
        or old_b.get("status") != "completed_research_only"
        or old_b.get("source_date") != source_date
    ):
        raise _InvalidEvidence("reusable B terminal no longer verifies")
    _verify_reusable_b_semantics(
        old_b_terminal=old_b,
        old_b_terminal_pins=b_terminal_pins,
        expected_current_b_semantic_identity=current_b_semantic_identity,
        symbols=symbols,
        source_date=source_date,
        repository_root=repository_root,
    )
    for terminal_key, b_key in (
        ("projection_manifest_path", "projection_manifest_path"),
        ("projection_manifest_sha256", "projection_manifest_sha256"),
        ("projection_observations_path", "projection_observations_path"),
        ("projection_observations_sha256", "projection_observations_sha256"),
    ):
        if b_terminal_pins.get(terminal_key) != old_b.get(b_key):
            raise _InvalidEvidence(f"reusable cycle B terminal pin differs: {terminal_key}")
    old_observations_path_value = old_b.get("projection_observations_path")
    old_observations_sha = _sha256_pin(
        old_b.get("projection_observations_sha256"),
        "reusable B projection observations SHA",
    )
    if not isinstance(old_observations_path_value, str) or not old_observations_path_value:
        raise _InvalidEvidence("reusable B projection observations path is missing")
    old_observations_path = resolve_ml_research_output_path(
        Path(old_observations_path_value), repository_root=repository_root
    )
    if (
        os.path.normcase(os.path.abspath(str(price_rows_path)))
        != os.path.normcase(os.path.abspath(str(old_observations_path)))
        or price_rows_sha != old_observations_sha
    ):
        raise _InvalidEvidence(
            "reusable registry price rows are not the exact rows pinned by its B terminal"
        )
    old_projection_manifest = resolve_ml_research_output_path(
        Path(str(old_b.get("projection_manifest_path") or "")),
        repository_root=repository_root,
    )
    old_manifest_pin = _pin_regular_file(old_projection_manifest, label="reusable B projection manifest")
    if "sha256:" + old_manifest_pin["sha256"] != _sha256_pin(
        old_b.get("projection_manifest_sha256"), "reusable B projection manifest SHA"
    ):
        raise _InvalidEvidence("reusable B projection manifest actual bytes differ")

    sidecar_path_value = record.get("sidecar_receipt_path")
    sidecar_sha = _sha256_pin(record.get("sidecar_receipt_sha256"), "reusable sidecar receipt SHA")
    if not isinstance(sidecar_path_value, str) or not sidecar_path_value:
        raise _InvalidEvidence("reusable sidecar receipt path is missing")
    sidecar_path = resolve_ml_research_output_path(
        Path(sidecar_path_value), repository_root=repository_root
    )
    sidecar_pin = _pin_regular_file(sidecar_path, label="reusable current-restated sidecar receipt")
    if "sha256:" + sidecar_pin["sha256"] != sidecar_sha:
        raise _InvalidEvidence("reusable sidecar receipt actual bytes differ")

    model_manifest_path_value = record.get("model_manifest_path")
    model_manifest_sha = _sha256_pin(
        record.get("model_manifest_sha256"), "reusable model manifest SHA"
    )
    model_bundle_sha = _sha256_pin(
        record.get("model_bundle_sha256"), "reusable model bundle SHA"
    )
    if not isinstance(model_manifest_path_value, str) or not model_manifest_path_value:
        raise _InvalidEvidence("reusable model manifest path is missing")
    model_manifest_path = resolve_ml_research_output_path(
        Path(model_manifest_path_value), repository_root=repository_root
    )
    model_manifest, model_manifest_pin = _json_file_pin(
        model_manifest_path, label="reusable CORE19 model manifest"
    )
    if (
        "sha256:" + model_manifest_pin["sha256"] != model_manifest_sha
        or model_manifest.get("historical_pit_eligible") is not False
        or model_manifest.get("formal_training_eligible") is not False
        or model_manifest.get("production_action_allowed") is not False
    ):
        raise _InvalidEvidence("reusable model manifest hash or safety qualification differs")
    bundle_metadata = model_manifest.get("model_bundle")
    bundle_name = (
        bundle_metadata.get("filename")
        if isinstance(bundle_metadata, Mapping)
        else None
    )
    if not isinstance(bundle_name, str) or not bundle_name or Path(bundle_name).name != bundle_name:
        raise _InvalidEvidence("reusable model bundle path is invalid")
    bundle_path = resolve_ml_research_output_path(
        model_manifest_path.parent / bundle_name, repository_root=repository_root
    )
    bundle_pin = _pin_regular_file(bundle_path, label="reusable CORE19 model bundle")
    if (
        "sha256:" + bundle_pin["sha256"] != model_bundle_sha
        or not isinstance(bundle_metadata, Mapping)
        or _sha256_pin(bundle_metadata.get("sha256"), "reusable manifest model bundle SHA")
        != model_bundle_sha
    ):
        raise _InvalidEvidence("reusable model bundle actual bytes differ from manifest")
    ml_index_value = registry.get("index_path")
    if not isinstance(ml_index_value, str) or not ml_index_value:
        raise _InvalidEvidence("reusable ML registry index path is missing")
    ml_index_path = resolve_ml_research_output_path(
        Path(ml_index_value), repository_root=repository_root
    )
    registry_run_id = registry.get("run_id")
    if not isinstance(registry_run_id, str) or not registry_run_id:
        raise _InvalidEvidence("reusable ML registry run id is missing")
    ml_index_sha256_at_reuse = _verify_public_ml_registry_index_binding(
        ml_index_path,
        repository_root=repository_root,
        expected_run_id=registry_run_id,
        expected_record_path=record_path,
        expected_record_sha256=record_sha,
    )
    _verify_public_registry_selects_reusable_run(
        repository_root=repository_root,
        run_id=registry_run_id,
        cycle_id=str(terminal.get("cycle_id") or ""),
        source_date=source_date,
        symbols=symbols,
        price_fingerprints=price_fingerprints,
        model_manifest_sha256=model_manifest_sha,
        model_bundle_sha256=model_bundle_sha,
    )
    return {
        "raw_run_id": terminal.get("raw_run_id"),
        "cycle_id": terminal.get("cycle_id"),
        "terminal_receipt_path": terminal.get("terminal_receipt_path", str(terminal_path)),
        "terminal_receipt_sha256": terminal_sha,
        "registry_record_path": str(record_path),
        "registry_record_sha256": record_sha,
        "registry_index_path": str(ml_index_path),
        "registry_index_sha256_at_reuse": ml_index_sha256_at_reuse,
        "last_success_at": terminal.get("last_success_at"),
    }


def _append_cycle_reuse_index(
    index_path: Path,
    *,
    entries_before: Sequence[Mapping[str, Any]],
    raw_run_id: str,
    source_date: str,
    reuse_key_sha256: str,
    terminal_receipt_path: Path,
    terminal_receipt_sha256: str,
    registry_record_path: Path,
    registry_record_sha256: str,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "schema_version": "current-stock-research-cycle-index.v1",
        "sequence": len(entries_before) + 1,
        "raw_run_id": raw_run_id,
        "source_date": source_date,
        "reuse_key_sha256": reuse_key_sha256,
        "terminal_receipt_path": str(terminal_receipt_path.resolve()),
        "terminal_receipt_sha256": terminal_receipt_sha256,
        "registry_record_path": str(registry_record_path.resolve()),
        "registry_record_sha256": registry_record_sha256,
        "indexed_at": _utc_now().isoformat(),
    }
    entry["entry_sha256"] = _cycle_index_entry_digest(entry)
    raw = _canonical_json_bytes(entry) + b"\n"
    try:
        if index_path.exists():
            with index_path.open("ab") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        else:
            with index_path.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
    except OSError as exc:
        raise CurrentStockResearchCycleError("current-stock reuse index could not be appended") from exc
    readback = _read_cycle_reuse_index(index_path, cycles_root=index_path.parent)
    if len(readback) != len(entries_before) + 1 or readback[-1] != entry:
        raise _InvalidEvidence("current-stock reuse index readback differs from its appended entry")
    return entry


def _run_reserved_child(
    command: Sequence[str],
    *,
    repository_root: Path,
    reservation: MLStorageChainReservation,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[Any]:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    environment = build_heavy_chain_reservation_handoff_environment(
        reservation,
        environment=environment,
        parent_pid=os.getpid(),
    )
    process = subprocess.Popen(
        list(command),
        cwd=str(repository_root),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
    )
    reservation.authorize_child(process.pid)
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
        raise TimeoutError(
            f"child timed out after {timeout_seconds}s: {Path(command[1]).name}"
        )
    if len(stdout) > MAX_CHILD_OUTPUT_BYTES:
        raise CurrentStockResearchCycleError("child stdout exceeded the bounded capture size")
    if len(stderr) > MAX_CHILD_OUTPUT_BYTES:
        raise CurrentStockResearchCycleError("child stderr exceeded the bounded capture size")
    return subprocess.CompletedProcess(list(command), process.returncode, stdout, stderr)


def _run_child(
    command: Sequence[str],
    *,
    repository_root: Path,
    reservation: MLStorageChainReservation,
    timeout_seconds: int,
    child_runner: Callable[..., subprocess.CompletedProcess[Any]] | None,
) -> subprocess.CompletedProcess[Any]:
    runner = child_runner or _run_reserved_child
    return runner(
        command,
        repository_root=repository_root,
        reservation=reservation,
        timeout_seconds=timeout_seconds,
    )


def _output_json_object(raw: bytes, *, label: str, stream_name: str) -> dict[str, Any] | None:
    if len(raw) > MAX_CHILD_OUTPUT_BYTES:
        raise _InvalidEvidence(f"{label} {stream_name} exceeded its byte limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None

    # Prefer one complete root object. This accepts the fit CLI's pretty JSON
    # receipt without trying to mine an arbitrary nested object from it.
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    else:
        # A successfully decoded non-object is the complete root value. Never
        # search inside a root array/scalar for a dictionary that looks like a
        # receipt.
        return payload if isinstance(payload, dict) else None

    # A broken structured root (including a pretty object/array) is not a log
    # stream. Reject it before looking at individual lines so a compact nested
    # object cannot be mistaken for the child receipt.
    first_content = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if (
        first_content.startswith("{")
        or first_content == "["
        or (first_content.startswith("[") and "]" not in first_content)
        or first_content.startswith(("[{", '["', "[["))
    ):
        return None

    # Preserve the log-plus-single-line-receipt contract used by other child
    # CLIs. Multiple standalone JSON objects are ambiguous; never guess that
    # the last one is the receipt.
    line_objects: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            line_payload = json.loads(line)
        except json.JSONDecodeError:
            # A standalone opening delimiter after ordinary log output marks
            # a malformed pretty JSON root; do not mine later nested objects.
            opening = line.strip()
            if (
                opening.startswith("{")
                or opening == "["
                or (opening.startswith("[") and "]" not in opening)
                or opening.startswith(("[{", '["', "[["))
            ):
                return None
            continue
        if isinstance(line_payload, dict):
            if line != line.lstrip():
                return None
            line_objects.append(line_payload)
            if len(line_objects) > 1:
                return None
        else:
            # A standalone JSON scalar/array alongside logs is ambiguous too.
            return None
    return line_objects[0] if len(line_objects) == 1 else None


def _stdout_object(result: subprocess.CompletedProcess[Any], *, label: str) -> dict[str, Any]:
    raw = result.stdout.encode("utf-8") if isinstance(result.stdout, str) else bytes(result.stdout or b"")
    payload = _output_json_object(raw, label=label, stream_name="stdout")
    if payload is None:
        raise _InvalidEvidence(f"{label} stdout has no JSON object")
    return payload


def _require_core19_fit_receipt(payload: _ChildJsonObject) -> _ChildJsonObject:
    if payload.get("schema_version") != "current-restated-core19-fit-receipt.v1":
        raise _InvalidEvidence("bounded CORE19 fit returned an unsupported receipt schema")
    return payload


def _verify_b_terminal(
    *,
    raw_run_id: str,
    source_date: str,
    terminal_path_value: object,
    terminal_sha_value: object,
    repository_root: Path,
) -> dict[str, Any]:
    if not isinstance(terminal_path_value, str) or not terminal_path_value.strip():
        raise _WaitingForSource("successful same-run B terminal receipt is missing")
    terminal_path = Path(terminal_path_value)
    terminal_sha = _sha256_pin(terminal_sha_value, "B terminal receipt SHA")
    path = resolve_ml_research_output_path(
        terminal_path, repository_root=repository_root, access="read"
    )
    pin = _pin_regular_file(path, label="B terminal receipt")
    if "sha256:" + pin["sha256"] != terminal_sha:
        raise _InvalidEvidence("B terminal receipt actual-byte SHA differs")
    terminal = _parse_json_object(path.read_bytes(), "B terminal receipt")
    if (
        terminal.get("schema_version") != "ml-daily-source-row-b-adapter-terminal.v1"
        or terminal.get("status") != "completed_research_only"
        or terminal.get("raw_run_id") != raw_run_id
        or terminal.get("source_date") != source_date
        or terminal.get("formal_credit") is not False
        or terminal.get("historical_pit_eligible") is not False
        or terminal.get("formal_oos_allowed") is not False
        or terminal.get("model_use_claimed") is not False
    ):
        raise _InvalidEvidence("B terminal status or raw-run/date binding differs")
    return {**terminal, "terminal_receipt_path": str(path), "terminal_receipt_sha256": terminal_sha}


def _projection_numeric_value(
    row: Mapping[str, Any], aliases: Sequence[str], *, required: bool, label: str
) -> Decimal | int | None:
    venue = row.get("venue")
    if venue not in {"twse", "tpex"}:
        raise _InvalidEvidence("B source projection venue is invalid")
    source_values = row.get("source_values")
    exact_values = row.get("exact_numeric_values")
    if not isinstance(source_values, Mapping) or not isinstance(exact_values, Mapping):
        raise _InvalidEvidence("B source projection omitted original or exact numeric values")
    normalize = lambda value: str(value).replace(" ", "").replace("<br>", "")
    wanted = {normalize(alias) for alias in aliases}
    matches = [
        key for key in source_values
        if isinstance(key, str) and normalize(key) in wanted
    ]
    if len(matches) != 1:
        if not matches and not required:
            return None
        raise _WaitingForSource(f"B source row has no unique {label} field")
    value = exact_values.get(matches[0])
    if not isinstance(value, Mapping) or value.get("state") != "numeric":
        if not required and isinstance(value, Mapping) and value.get("state") == "source_missing":
            return None
        raise _WaitingForSource(f"B source row {label} is missing or not numeric")
    raw = value.get("raw_value")
    if not isinstance(raw, str) or not raw.strip():
        raise _InvalidEvidence(f"B exact {label} omitted its preserved source token")
    try:
        decimal = Decimal(raw.replace(",", "").strip())
    except InvalidOperation as exc:
        raise _InvalidEvidence(f"B exact {label} source token is invalid") from exc
    if not decimal.is_finite():
        raise _InvalidEvidence(f"B exact {label} is not finite")
    if label == "volume":
        if decimal != decimal.to_integral_value():
            raise _InvalidEvidence("B volume is not an integer number of shares")
        return int(decimal)
    return decimal


def _current_price_fingerprints(
    *, b_terminal: Mapping[str, Any], symbols: Sequence[str], source_date: str
) -> tuple[dict[str, str], dict[str, Any]]:
    observations_path_value = b_terminal.get("projection_observations_path")
    observations_sha = _sha256_pin(
        b_terminal.get("projection_observations_sha256"),
        "B projection observations SHA",
    )
    if not isinstance(observations_path_value, str) or not observations_path_value:
        raise _WaitingForSource("B terminal does not provide source observations for exact current prices")
    observations_path = Path(observations_path_value).resolve(strict=True)
    pin = _pin_regular_file(observations_path, label="B projection observations")
    if "sha256:" + pin["sha256"] != observations_sha:
        raise _InvalidEvidence("B projection observation bytes differ from terminal pin")
    symbol_set = set(symbols)
    rows: dict[str, Mapping[str, Any]] = {}
    with observations_path.open("rb") as stream:
        for line_number, raw_line in enumerate(stream, 1):
            if len(raw_line) > 128 * 1024:
                raise _InvalidEvidence(f"B observation line {line_number} exceeds byte bound")
            try:
                row = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise _InvalidEvidence(f"B observation line {line_number} is invalid JSON") from exc
            if not isinstance(row, Mapping):
                raise _InvalidEvidence(f"B observation line {line_number} is not an object")
            symbol = row.get("symbol")
            if symbol not in symbol_set:
                continue
            if row.get("source_date") != source_date:
                raise _InvalidEvidence("B current price event date differs from the requested date")
            if symbol in rows:
                raise _InvalidEvidence(f"B current price row is duplicated for {symbol}")
            rows[str(symbol)] = row
    if set(rows) != symbol_set:
        missing = sorted(symbol_set - set(rows))
        raise _WaitingForSource(
            "B source projection has no same-date current row for: " + ",".join(missing)
        )

    from app_module.stock_research_report_provider_adapters import (
        stock_price_row_fingerprint_sha256,
    )

    fingerprints: dict[str, str] = {}
    official_raw_sources: dict[str, str] = {}
    for symbol in symbols:
        row = rows[symbol]
        venue = row.get("venue")
        if venue not in {"twse", "tpex"}:
            raise _InvalidEvidence(f"B source row venue is invalid for {symbol}")
        raw_sha = _sha256_pin(
            row.get("source_raw_response_sha256"),
            f"{symbol} official raw response SHA",
        ).removeprefix("sha256:")
        previous_raw_sha = official_raw_sources.get(str(venue))
        if previous_raw_sha is not None and previous_raw_sha != raw_sha:
            raise _InvalidEvidence(f"B source rows bind mixed official raw responses for {venue}")
        official_raw_sources[str(venue)] = raw_sha
        prices = {
            "open_price": _projection_numeric_value(row, ("開盤價", "開盤"), required=True, label="open"),
            "high_price": _projection_numeric_value(row, ("最高價", "最高"), required=True, label="high"),
            "low_price": _projection_numeric_value(row, ("最低價", "最低"), required=True, label="low"),
            "close_price": _projection_numeric_value(row, ("收盤價", "收盤"), required=True, label="close"),
            "volume": _projection_numeric_value(row, ("成交股數", "成交量"), required=False, label="volume"),
            "turnover": _projection_numeric_value(row, ("成交金額", "成交金額(元)"), required=False, label="turnover"),
        }
        try:
            digest = stock_price_row_fingerprint_sha256(
                stock_code=symbol,
                data_date=source_date,
                **prices,
            )
        except (TypeError, ValueError) as exc:
            raise _InvalidEvidence(f"current price fingerprint failed for {symbol}: {exc}") from exc
        fingerprints[symbol] = _sha256_pin(digest, f"price row fingerprint for {symbol}")
    # Detect replacement between our first hash and row parsing.
    _verify_file_pin(observations_path, pin, label="B projection observations")
    return (
        {
            symbol: value.removeprefix("sha256:").lower()
            for symbol, value in fingerprints.items()
        },
        {
            "source_date": source_date,
            "official_raw_response_sha256_by_venue": dict(
                sorted(official_raw_sources.items())
            ),
        },
    )


def _require_run_path(path_value: object, *, root: Path, label: str) -> Path:
    if not isinstance(path_value, str) or not path_value.strip():
        raise _InvalidEvidence(f"{label} path is missing")
    path = Path(path_value).resolve(strict=True)
    try:
        path.relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise _InvalidEvidence(f"{label} escaped this cycle output root") from exc
    if not path.is_file():
        raise _InvalidEvidence(f"{label} is not a regular file")
    return path


def _pin_outcome_cli_summary(
    outcome_cli: Mapping[str, Any],
    *,
    output_root: Path,
    symbols: Sequence[str],
    raw_publication_manifest_sha256: str,
    raw_dataset_manifest_sha256: str,
) -> dict[str, Any]:
    """Verify the producer's bounded summary and stream-pin its large manifest.

    Current-restated outcome manifests can exceed the generic 8 MiB receipt
    limit because their fold policy carries purged train/test sample IDs. The
    producer CLI returns a compact summary with the manifest's exact-byte SHA;
    this stage verifies that summary and pins the file by streaming. The later
    fit CLI consumes that same path and SHA through the outcome store's strict
    loader, which verifies the full canonical manifest, row hashes, folds, and
    arrays before any model can be accepted.
    """

    if (
        outcome_cli.get("schema_version") != "portfolio-ml-current-restated-outcome-cli.v1"
        or outcome_cli.get("status") != "completed_research_only"
        or outcome_cli.get("current_restated") is not True
        or outcome_cli.get("historical_pit_eligible") is not False
        or outcome_cli.get("formal_training_eligible") is not False
        or outcome_cli.get("full_teacher_qualified") is not False
    ):
        raise _InvalidEvidence("outcome Direct producer status or safety contract differs")
    target_symbols = outcome_cli.get("target_symbols", list(symbols))
    if target_symbols != list(symbols):
        raise _InvalidEvidence("outcome Direct producer target cohort differs")

    run_id = outcome_cli.get("run_id")
    if not isinstance(run_id, str) or not re.fullmatch(
        r"current-restated-outcome-[0-9a-f]{24}", run_id
    ):
        raise _InvalidEvidence("outcome Direct producer run identity is invalid")
    manifest_path = _require_run_path(
        outcome_cli.get("manifest_path"),
        root=output_root,
        label="outcome artifact receipt/manifest",
    )
    if (
        manifest_path.name != "manifest.json"
        or manifest_path.parent.name != run_id
        or manifest_path.parent.parent.name != "runs"
    ):
        raise _InvalidEvidence("outcome Direct manifest path differs from its exact run identity")
    manifest_pin = _pin_regular_file(
        manifest_path, label="outcome artifact receipt/manifest"
    )
    manifest_sha256 = _sha256_pin(
        outcome_cli.get("manifest_sha256"), "outcome producer manifest bytes SHA"
    )
    if "sha256:" + manifest_pin["sha256"] != manifest_sha256:
        raise _InvalidEvidence("outcome manifest bytes differ from producer summary SHA")

    expected_raw_manifest_sha = _sha256_pin(
        raw_publication_manifest_sha256, "expected raw publication manifest SHA"
    )
    expected_raw_dataset_sha = _sha256_pin(
        raw_dataset_manifest_sha256, "expected raw dataset manifest SHA"
    )
    if _sha256_pin(
        outcome_cli.get("raw_publication_manifest_sha256"),
        "outcome producer raw publication manifest SHA",
    ) != expected_raw_manifest_sha:
        raise _InvalidEvidence("outcome producer summary is bound to another raw manifest")
    if _sha256_pin(
        outcome_cli.get("raw_dataset_manifest_sha256"),
        "outcome producer raw dataset manifest SHA",
    ) != expected_raw_dataset_sha:
        raise _InvalidEvidence("outcome producer summary is bound to another raw dataset")

    feature_registry_sha256 = _sha256_pin(
        outcome_cli.get("feature_registry_sha256"),
        "outcome feature registry SHA",
    )
    counts: dict[str, int] = {}
    for field_name in ("observation_count", "feature_count", "fold_count"):
        value = outcome_cli.get(field_name)
        if type(value) is not int or value <= 0:
            raise _InvalidEvidence(f"outcome producer {field_name} is invalid")
        counts[field_name] = value
    if counts["fold_count"] < 4 or counts["fold_count"] > counts["observation_count"]:
        raise _InvalidEvidence("outcome producer fold count is outside the bounded observation scope")
    artifact_available_at = _aware_utc(
        outcome_cli.get("artifact_available_at"),
        "outcome producer artifact_available_at",
    )
    return {
        "manifest_path": str(manifest_path),
        "manifest_pin": manifest_pin,
        "manifest_sha256": manifest_sha256,
        "feature_registry_sha256": feature_registry_sha256,
        "run_id": run_id,
        "artifact_available_at": artifact_available_at.isoformat(),
        **counts,
    }


def _write_stage_event(
    *,
    cycle_root: Path,
    state: dict[str, Any],
    callback: Callable[[Mapping[str, Any]], None] | None,
    stage: str,
    status: str,
    next_action: str,
    pins: Mapping[str, Any] | None = None,
) -> None:
    events_path = cycle_root / "events.jsonl"
    event = {
        "schema_version": "current-stock-research-cycle-event.v1",
        "sequence": len(state["events"]) + 1,
        "occurred_at": _utc_now().isoformat(),
        "stage": stage,
        "status": status,
        "next_action": next_action,
        "pins": dict(pins or {}),
    }
    event["previous_event_sha256"] = state["events"][-1]["event_sha256"] if state["events"] else None
    event["event_sha256"] = _sha256(_canonical_json_bytes(event))
    _append_event(events_path, event, first=not state["events"])
    state["events"].append(event)
    state["status"] = status if status in {
        "blocked_capacity", "waiting_source", "failed", "completed", "skipped_same_inputs"
    } else "running"
    state["stage"] = stage
    state["next_action"] = next_action
    if pins:
        state["same_run_pins"].update(dict(pins))
    if callback is not None:
        callback(dict(state))


def _cycle_terminal(
    *,
    cycle_root: Path,
    state: Mapping[str, Any],
    status: str,
    reason: str | None,
    error_type: str | None,
    next_action: str,
    last_success_at: str | None = None,
    now_provider: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    completed_at = (now_provider or _utc_now)()
    if completed_at.tzinfo is None or completed_at.utcoffset() is None:
        raise CurrentStockResearchCycleError("cycle terminal clock must be timezone-aware")
    if status not in {
        "completed", "blocked_capacity", "waiting_source", "failed", "skipped_same_inputs"
    }:
        raise CurrentStockResearchCycleError(f"unsupported terminal status: {status}")
    event_path = cycle_root / "events.jsonl"
    event_pin = _pin_regular_file(event_path, label="cycle stage event log") if event_path.is_file() else None
    payload = {
        **dict(state),
        "schema_version": "current-stock-research-cycle-terminal.v1",
        "status": status,
        "reason": reason,
        "error_type": error_type,
        "next_action": next_action,
        "completed_at": completed_at.astimezone(timezone.utc).isoformat(),
        "last_success_at": last_success_at,
        "events_path": None if event_pin is None else event_pin["path"],
        "events_sha256": None if event_pin is None else event_pin["sha256"],
        "events_bytes": None if event_pin is None else event_pin["bytes"],
        "research_only": True,
        "historical_pit_eligible": False,
        "formal_training_eligible": False,
        "formal_oos_allowed": False,
        "formal_credit": False,
        "production_alpha_bp": 0,
        "production_action_allowed": False,
    }
    terminal_path = cycle_root / "terminal_receipt.json"
    terminal_sha = _write_create_only(terminal_path, payload)
    result = {
        **payload,
        "terminal_receipt_path": str(terminal_path.resolve()),
        "terminal_receipt_sha256": terminal_sha,
    }
    return result


def _completed_child_json(
    command: Sequence[str],
    *,
    repository_root: Path,
    reservation: MLStorageChainReservation,
    timeout_seconds: int,
    child_runner: Callable[..., subprocess.CompletedProcess[Any]] | None,
    label: str,
    result_observer: Callable[[subprocess.CompletedProcess[Any]], None] | None = None,
) -> _ChildJsonObject:
    result = _run_child(
        command,
        repository_root=repository_root,
        reservation=reservation,
        timeout_seconds=timeout_seconds,
        child_runner=child_runner,
    )
    if result_observer is not None:
        result_observer(result)
    if result.returncode != 0:
        stderr_raw = (
            result.stderr.encode("utf-8")
            if isinstance(result.stderr, str)
            else bytes(result.stderr or b"")
        )
        payload = _output_json_object(stderr_raw, label=label, stream_name="stderr")
        if payload is None:
            stdout_raw = (
                result.stdout.encode("utf-8")
                if isinstance(result.stdout, str)
                else bytes(result.stdout or b"")
            )
            payload = _output_json_object(stdout_raw, label=label, stream_name="stdout") or {}
        stderr_fallback = (
            result.stderr.decode("utf-8", errors="replace")[-1000:]
            if isinstance(result.stderr, (bytes, bytearray))
            else str(result.stderr or "")[-1000:]
        )
        error = payload.get("error") or payload.get("message") or payload.get("reason") or stderr_fallback
        if _known_maturity_block(payload):
            raise _WaitingForSource(f"{label} is waiting for verified mature outcomes: {error}")
        raise CurrentStockResearchCycleError(f"{label} exited {result.returncode}: {error}")
    stdout_raw = (
        result.stdout.encode("utf-8")
        if isinstance(result.stdout, str)
        else bytes(result.stdout or b"")
    )
    payload = _output_json_object(stdout_raw, label=label, stream_name="stdout")
    if payload is None:
        raise _InvalidEvidence(f"{label} stdout has no JSON object")
    return _ChildJsonObject(payload, stdout_sha256=_sha256(stdout_raw))


def _record_child_result(
    *,
    state: dict[str, Any],
    cycle_root: Path,
    stage: str,
    child_name: str,
    command: Sequence[str],
    result: subprocess.CompletedProcess[Any],
) -> None:
    """Save both exact output streams before child status or JSON validation."""

    if not re.fullmatch(r"[a-z0-9_]{1,64}", stage) or not re.fullmatch(
        r"[a-z0-9_]{1,64}", child_name
    ):
        raise ValueError("child evidence stage/name is invalid")
    if type(result.returncode) is not int:
        raise TypeError("child result returncode must be an int")

    def stream_bytes(value: object, name: str) -> bytes:
        if isinstance(value, str):
            raw = value.encode("utf-8")
        elif isinstance(value, (bytes, bytearray, memoryview)):
            raw = bytes(value)
        elif value is None:
            raw = b""
        else:
            raise TypeError(f"child {name} has an unsupported stream type")
        if len(raw) > MAX_CHILD_OUTPUT_BYTES:
            raise _InvalidEvidence(f"child {name} exceeded the bounded capture size")
        return raw

    evidence_root = cycle_root / "child_evidence"
    evidence_root.mkdir(exist_ok=True)
    if evidence_root.is_symlink():
        raise _InvalidEvidence("child evidence directory must not be a symlink")
    stream_pins: dict[str, dict[str, Any]] = {}
    for stream_name, raw in (
        ("stdout", stream_bytes(result.stdout, "stdout")),
        ("stderr", stream_bytes(result.stderr, "stderr")),
    ):
        output_path = evidence_root / f"{stage}_{child_name}.{stream_name}.bin"
        output_sha = _write_create_only_bytes(output_path, raw)
        stream_pins[stream_name] = {
            "path": str(output_path.resolve()),
            "sha256": output_sha,
            "bytes": len(raw),
        }

    stage_results = state.setdefault("stage_results", {})
    if not isinstance(stage_results, dict):
        raise _InvalidEvidence("stage_results must remain a mutable mapping")
    stage_result = stage_results.setdefault(stage, {})
    if not isinstance(stage_result, dict) or child_name in stage_result:
        raise _InvalidEvidence("child result evidence is duplicated or malformed")
    stage_result[child_name] = {
        "schema_version": "current-stock-research-child-result.v1",
        "returncode": result.returncode,
        "command": [str(part) for part in command],
        "stdout": stream_pins["stdout"],
        "stderr": stream_pins["stderr"],
    }

def run_current_stock_research_cycle(
    *,
    raw_run_id: str,
    source_date: str,
    b_adapter_terminal_path: str | Path | None,
    b_adapter_terminal_sha256: str | None,
    data_root: Path,
    canonical_output_root: Path,
    release_root: Path,
    repository_root: Path = REPOSITORY_ROOT,
    research_output_root: Path | None = None,
    now_provider: Callable[[], datetime] | None = None,
    status_callback: Callable[[Mapping[str, Any]], None] | None = None,
    child_runner: Callable[..., subprocess.CompletedProcess[Any]] | None = None,
    capacity_checker: Callable[..., Mapping[str, Any]] | None = None,
    reservation: MLStorageChainReservation | None = None,
) -> dict[str, Any]:
    """Run a complete bounded current-stock ML research cycle for one raw run.

    The public API is intentionally path-pinned and does not take symbols from
    a caller; the current cohort is read from the canonical watchlist and true
    portfolio holdings.
    """

    if not isinstance(raw_run_id, str) or not RUN_ID_RE.fullmatch(raw_run_id):
        raise ValueError("raw_run_id is invalid")
    try:
        normalized_date = date.fromisoformat(source_date).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError("source_date must be an ISO date") from exc
    if normalized_date != source_date:
        raise ValueError("source_date must be canonical ISO date text")

    repo = repository_root.resolve(strict=True)
    active_research_root = get_ml_research_root(repository_root=repo)
    requested_research_root = (
        active_research_root
        if research_output_root is None
        else Path(research_output_root).expanduser()
    )
    research_root = resolve_ml_research_output_path(
        requested_research_root,
        repository_root=repo,
        access="write",
    )
    if research_root != active_research_root:
        raise _InvalidEvidence("research output root differs from the pinned active storage root")
    storage_key = _cycle_storage_key(raw_run_id)
    cycle_root = resolve_ml_research_output_path(
        research_root / "current_stock_cycles" / normalized_date / storage_key,
        repository_root=repo,
        access="write",
    )
    if cycle_root.exists():
        existing_terminal = cycle_root / "terminal_receipt.json"
        existing: dict[str, Any] = {}
        terminal_sha: str | None = None
        if existing_terminal.is_file():
            raw_existing = existing_terminal.read_bytes()
            existing = _parse_json_object(raw_existing, "existing cycle terminal receipt")
            if existing.get("raw_run_id") != raw_run_id:
                raise _InvalidEvidence("cycle storage-key collision has a different raw_run_id")
            terminal_sha = _sha256(raw_existing)
        else:
            start_receipt_path = cycle_root / "start_receipt.json"
            if start_receipt_path.is_file():
                start_receipt = _parse_json_object(
                    start_receipt_path.read_bytes(), "existing cycle start receipt"
                )
                if start_receipt.get("raw_run_id") != raw_run_id:
                    raise _InvalidEvidence("cycle storage-key collision has a different raw_run_id")
        return {
            **existing,
            "status": existing.get("status", "failed"),
            "duplicate_request_blocked": True,
            "next_action": "use_a_new_raw_run_id_for_a_new_cycle",
            "terminal_receipt_path": str(existing_terminal.resolve()) if existing_terminal.exists() else None,
            "terminal_receipt_sha256": terminal_sha,
        }
    cycle_root.parent.mkdir(parents=True, exist_ok=True)
    cycle_root.mkdir(exist_ok=False)
    cycle_root = resolve_ml_research_output_path(
        cycle_root, repository_root=repo, access="write"
    )

    started_at = (now_provider or _utc_now)()
    if started_at.tzinfo is None or started_at.utcoffset() is None:
        raise ValueError("cycle clock must be timezone-aware")
    state: dict[str, Any] = {
        "cycle_id": raw_run_id,
        "raw_run_id": raw_run_id,
        "cycle_storage_key": storage_key,
        "source_date": normalized_date,
        "started_at": started_at.astimezone(timezone.utc).isoformat(),
        "research_output_root": str(research_root),
        "cycle_output_root": str(cycle_root.resolve()),
        "canonical_output_root": str(canonical_output_root.resolve()),
        "release_root": str(release_root.resolve()),
        "stage": "started",
        "status": "running",
        "next_action": "verify_same_run_b_terminal",
        "same_run_pins": {"research_output_root": str(research_root)},
        "events": [],
        "stage_results": {},
    }
    _write_create_only(
        cycle_root / "start_receipt.json",
        {
            "schema_version": "current-stock-research-cycle-start.v1",
            "cycle_id": raw_run_id,
            "raw_run_id": raw_run_id,
            "cycle_storage_key": storage_key,
            "source_date": normalized_date,
            "started_at": state["started_at"],
            "cycle_output_root": state["cycle_output_root"],
            "research_only": True,
            "formal_credit": False,
        },
    )

    def event(stage: str, status: str, next_action: str, pins: Mapping[str, Any] | None = None) -> None:
        current_root = get_ml_research_root(repository_root=repo)
        if current_root != research_root:
            raise _InvalidEvidence("active ML research storage root changed during the cycle")
        resolve_ml_research_output_path(
            research_root, repository_root=repo, access="write"
        )
        _write_stage_event(
            cycle_root=cycle_root,
            state=state,
            callback=status_callback,
            stage=stage,
            status=status,
            next_action=next_action,
            pins=pins,
        )

    def run_cycle_child_json(
        command: Sequence[str],
        *,
        stage: str,
        child_name: str,
        timeout_seconds: int,
        label: str,
    ) -> _ChildJsonObject:
        def observe(result: subprocess.CompletedProcess[Any]) -> None:
            _record_child_result(
                state=state,
                cycle_root=cycle_root,
                stage=stage,
                child_name=child_name,
                command=command,
                result=result,
            )

        try:
            child_reservation = reservation
            if child_reservation is None:
                raise _InvalidEvidence(
                    "child launch attempted without an active heavy-chain reservation"
                )
            return _completed_child_json(
                command,
                repository_root=repo,
                reservation=child_reservation,
                timeout_seconds=timeout_seconds,
                child_runner=child_runner,
                label=label,
                result_observer=observe,
            )
        except Exception as exc:
            stage_results = state.setdefault("stage_results", {})
            if not isinstance(stage_results, dict):
                raise _InvalidEvidence("stage_results must remain a mutable mapping") from exc
            stage_result = stage_results.setdefault(stage, {})
            if not isinstance(stage_result, dict):
                raise _InvalidEvidence("child stage result must remain a mutable mapping") from exc
            existing = stage_result.get(child_name)
            if isinstance(existing, dict):
                existing["wrapper_error"] = {
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:4000],
                }
            else:
                stage_result[child_name] = {
                    "schema_version": "current-stock-research-child-result.v1",
                    "status": "launch_or_capture_failed",
                    "command": [str(part) for part in command],
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:4000],
                }
            raise

    reservation_owned = False
    terminal_status = "failed"
    terminal_reason: str | None = None
    terminal_error_type: str | None = None
    next_action = "inspect_cycle_failure"
    last_success_at: str | None = None
    try:
        event("b_input", "running", "verify_same_run_b_terminal")
        b_terminal = _verify_b_terminal(
            raw_run_id=raw_run_id,
            source_date=normalized_date,
            terminal_path_value=(None if b_adapter_terminal_path is None else str(b_adapter_terminal_path)),
            terminal_sha_value=b_adapter_terminal_sha256,
            repository_root=repo,
        )
        state["b_terminal"] = {
            "path": b_terminal["terminal_receipt_path"],
            "sha256": b_terminal["terminal_receipt_sha256"],
            "status": b_terminal["status"],
        }
        state["same_run_pins"].update(
            {
                "b_terminal_receipt_path": b_terminal["terminal_receipt_path"],
                "b_terminal_receipt_sha256": b_terminal["terminal_receipt_sha256"],
                "projection_manifest_path": b_terminal.get("projection_manifest_path"),
                "projection_manifest_sha256": b_terminal.get("projection_manifest_sha256"),
                "projection_observations_path": b_terminal.get("projection_observations_path"),
                "projection_observations_sha256": b_terminal.get("projection_observations_sha256"),
                "b_consumption_receipt_path": b_terminal.get("consumption_receipt_path"),
                "b_consumption_receipt_sha256": b_terminal.get("consumption_receipt_sha256"),
                "b_adapted_manifest_path": b_terminal.get("adapted_manifest_path"),
                "b_adapted_manifest_sha256": b_terminal.get("adapted_manifest_canonical_sha256"),
                "b_feature_registry_sha256": b_terminal.get("feature_registry_sha256"),
                "b_current_observation_freeze": b_terminal.get("current_observation_freeze"),
            }
        )
        event("b_input", "running", "read_current_watchlist_and_holdings", state["same_run_pins"])

        scope = _read_current_stock_scope(canonical_output_root)
        symbols = tuple(scope["current_symbols"])
        state["current_symbols"] = list(symbols)
        state["scope_counts"] = {
            "watchlist_symbol_count": len(scope["watchlist_symbols"]),
            "holding_symbol_count": len(scope["holding_symbols"]),
            "union_symbol_count": len(symbols),
        }
        state["scope_sources"] = {
            "watchlist_storage": scope["watchlist_storage"],
            "watchlists": scope["watchlist_sources"],
            "portfolio_holding_source": scope["portfolio_holding_source"],
        }
        state["same_run_pins"].update(
            {
                "watchlist_input_pins": scope["watchlist_input_pins"],
                "position_input_pins": scope["position_input_pins"],
            }
        )
        scope_payload = {
            "schema_version": "current-stock-research-cycle-scope.v1",
            "raw_run_id": raw_run_id,
            "source_date": normalized_date,
            "current_symbols": list(symbols),
            "watchlist_symbols": list(scope["watchlist_symbols"]),
            "holding_symbols": list(scope["holding_symbols"]),
            "watchlist_input_pins": scope["watchlist_input_pins"],
            "position_input_pins": scope["position_input_pins"],
            "watchlist_storage": scope["watchlist_storage"],
            "research_only": True,
        }
        scope_sha = _write_create_only(cycle_root / "scope.json", scope_payload)
        state["same_run_pins"]["scope_manifest_path"] = str((cycle_root / "scope.json").resolve())
        state["same_run_pins"]["scope_manifest_sha256"] = scope_sha
        data_root_resolved = data_root.resolve(strict=True)
        source_database = data_root_resolved / "sqlite" / "twstock.db"
        if not source_database.is_file():
            raise _WaitingForSource(f"current source SQLite database is missing: {source_database}")
        source_observation = _source_observation_pins(source_database)
        source_wal = source_observation.get("wal")
        snapshot_upper_bound_bytes = int(source_observation["database"]["bytes"])
        if isinstance(source_wal, Mapping) and source_wal.get("present") is True:
            wal_bytes = source_wal.get("bytes")
            if isinstance(wal_bytes, bool) or not isinstance(wal_bytes, int) or wal_bytes < 0:
                raise _InvalidEvidence("source WAL byte pin is invalid")
            snapshot_upper_bound_bytes += wal_bytes
        state["same_run_pins"]["pre_snapshot_source_observation"] = source_observation
        state["snapshot_upper_bound_bytes"] = snapshot_upper_bound_bytes
        _verify_scope_input_pins(scope)
        current_price_fingerprints, official_raw_input_identity = _current_price_fingerprints(
            b_terminal=b_terminal, symbols=symbols, source_date=normalized_date
        )
        current_b_semantic_identity = _current_b_semantic_identity(
            b_terminal=b_terminal,
            symbols=symbols,
            source_date=normalized_date,
            repository_root=repo,
        )
        state["current_price_row_fingerprint_sha256_by_symbol"] = current_price_fingerprints
        state["official_raw_input_identity"] = official_raw_input_identity
        state["same_run_pins"]["b_semantic_identity"] = current_b_semantic_identity
        reuse_key_sha256 = _current_cycle_reuse_key(
            source_date=normalized_date,
            scope=scope,
            source_observation=source_observation,
            price_fingerprints=current_price_fingerprints,
            official_raw_input_identity=official_raw_input_identity,
            b_semantic_identity=current_b_semantic_identity,
        )
        state["same_run_pins"]["reuse_key_sha256"] = reuse_key_sha256
        state["same_run_pins"]["current_source_observation"] = source_observation
        state["same_run_pins"]["current_price_row_fingerprint_sha256_by_symbol"] = (
            current_price_fingerprints
        )
        state["same_run_pins"]["official_raw_input_identity"] = (
            official_raw_input_identity
        )
        event("scope", "running", "reuse_exact_completed_cycle_or_check_bounded_capacity", state["same_run_pins"])

        lock_path = heavy_chain_lock_path(release_root)
        reservation, reservation_owned = _borrow_or_acquire_reservation(
            lock_path, reservation
        )
        if reservation is None:
            raise _WaitingForSource("shared ML heavy-chain reservation is held by another active owner")
        state["same_run_pins"]["heavy_chain_lock_path"] = str(lock_path.resolve())

        cycle_index_path = research_root / "current_stock_cycles" / "cycle_index.jsonl"
        cycle_index_entries = _read_cycle_reuse_index(
            cycle_index_path, cycles_root=cycle_index_path.parent
        )
        matching_entries = [
            item for item in cycle_index_entries
            if item.get("reuse_key_sha256") == reuse_key_sha256
            and item.get("source_date") == normalized_date
        ]
        if matching_entries:
            reusable = _verify_cycle_reuse_target(
                matching_entries[-1],
                cycles_root=cycle_index_path.parent,
                expected_reuse_key_sha256=reuse_key_sha256,
                source_date=normalized_date,
                symbols=symbols,
                price_fingerprints=current_price_fingerprints,
                official_raw_input_identity=official_raw_input_identity,
                current_b_semantic_identity=current_b_semantic_identity,
                repository_root=repo,
            )
            _verify_scope_input_pins(scope)
            source_observation_after = _source_observation_pins(source_database)
            if _stable_source_dependency_identity(source_observation_after) != _stable_source_dependency_identity(source_observation):
                raise _WaitingForSource("current source revision changed while checking reuse")
            price_fingerprints_after, official_raw_input_identity_after = _current_price_fingerprints(
                b_terminal=b_terminal, symbols=symbols, source_date=normalized_date
            )
            if (
                price_fingerprints_after != current_price_fingerprints
                or official_raw_input_identity_after != official_raw_input_identity
            ):
                raise _WaitingForSource("official raw source or current prices changed while checking reuse")
            current_b_semantic_identity_after = _current_b_semantic_identity(
                b_terminal=b_terminal,
                symbols=symbols,
                source_date=normalized_date,
                repository_root=repo,
            )
            if current_b_semantic_identity_after != current_b_semantic_identity:
                raise _WaitingForSource("B feature mapping or transformed rows changed while checking reuse")
            state["reused_from"] = reusable
            state["last_success_at"] = reusable.get("last_success_at")
            next_action = "wait_for_a_new_current_source_revision_or_watchlist_or_holding_change"
            event("reuse", "skipped_same_inputs", next_action, {"reused_from": reusable})
            terminal = _cycle_terminal(
                cycle_root=cycle_root,
                state=state,
                status="skipped_same_inputs",
                reason="exact_source_scope_and_current_price_inputs_match_a_verified_completed_cycle",
                error_type=None,
                next_action=next_action,
                last_success_at=reusable.get("last_success_at"),
                now_provider=now_provider,
            )
            if status_callback is not None:
                status_callback(terminal)
            return terminal

        capacity_func = capacity_checker or _capacity_check
        capacity = dict(
            capacity_func(
                canonical_output_root=canonical_output_root,
                research_output_root=research_root,
                snapshot_upper_bound_bytes=snapshot_upper_bound_bytes,
            )
        )
        state["capacity"] = capacity
        if capacity.get("within_budget") is not True:
            terminal_status = "blocked_capacity"
            terminal_reason = "bounded_current_stock_research_cycle_capacity_policy_not_met"
            next_action = "free_or_provision_headroom_for_snapshot_plus_2gib_persistent_2gib_temporary_and_20gib_reserve"
            event("capacity", "blocked_capacity", next_action, {"capacity": capacity})
            terminal = _cycle_terminal(
                cycle_root=cycle_root,
                state=state,
                status=terminal_status,
                reason=terminal_reason,
                error_type="InsufficientFreeSpace",
                next_action=next_action,
                now_provider=now_provider,
            )
            if status_callback is not None:
                status_callback(terminal)
            return terminal
        event("capacity", "running", "create_snapshot_within_observed_upper_bound", {"capacity": capacity})
        snapshot_dir = cycle_root / "snapshot"
        snapshot_dir.mkdir(exist_ok=False)
        snapshot_database = snapshot_dir / "source.sqlite"
        snapshot_receipt_path = snapshot_dir / "snapshot_receipt.json"
        event("snapshot", "running", "create_readonly_consistent_sqlite_snapshot")
        snapshot = _create_consistent_snapshot(
            source_database=source_database,
            snapshot_database=snapshot_database,
            receipt_path=snapshot_receipt_path,
        )
        if _stable_source_dependency_identity(snapshot.get("source_observation", {})) != _stable_source_dependency_identity(
            source_observation
        ):
            raise _WaitingForSource("source revision differs from the preflight/reuse observation")
        snapshot_actual_bytes = int(Path(snapshot["snapshot_database_path"]).stat().st_size)
        if snapshot_actual_bytes > snapshot_upper_bound_bytes:
            raise _InvalidEvidence("SQLite snapshot exceeded the measured main-database plus WAL upper bound")
        state["capacity"]["snapshot_actual_bytes"] = snapshot_actual_bytes
        state["capacity"]["snapshot_upper_bound_bytes"] = snapshot_upper_bound_bytes
        state["capacity"]["snapshot_within_measured_upper_bound"] = True
        _record_cycle_growth(state, cycle_root)
        snapshot_completed = _aware_utc(snapshot["snapshot_completed_at"], "snapshot completed_at")
        verified_context = load_verified_current_restated_source_context(
            snapshot_database,
            snapshot_receipt_path,
            expected_snapshot_database_sha256=snapshot["snapshot_database_sha256"],
            expected_snapshot_receipt_sha256=snapshot["snapshot_receipt_sha256"],
            original_database_path=source_database,
            decision_at=snapshot_completed,
            training_as_of=snapshot_completed,
        )
        context_fit_freeze = _context_fit_freeze(
            snapshot_completed,
            verified_context.revision_dependencies_verified_at,
        )
        verified_context = replace(verified_context, training_as_of=context_fit_freeze)
        state["snapshot"] = snapshot
        state["same_run_pins"].update(
            {
                "source_database_path": str(source_database.resolve()),
                "snapshot_database_path": snapshot["snapshot_database_path"],
                "snapshot_database_sha256": snapshot["snapshot_database_sha256"],
                "snapshot_receipt_path": snapshot["snapshot_receipt_path"],
                "snapshot_receipt_sha256": snapshot["snapshot_receipt_sha256"],
                "source_generation": snapshot["source_generation"],
            }
        )
        context_dir = cycle_root / "context"
        context_dir.mkdir(exist_ok=False)
        from ml_module.current_restated_research_bridge import save_verified_current_restated_context_file

        context_path, context_sha = save_verified_current_restated_context_file(
            verified_context,
            output_path=context_dir / "source_context.json",
            fit_cutoff=context_fit_freeze.isoformat(),
        )
        state["same_run_pins"].update(
            {
                "source_context_envelope_path": str(context_path.resolve()),
                "source_context_envelope_sha256": context_sha,
                "snapshot_completed_at": snapshot_completed.isoformat(),
                "revision_dependencies_verified_at": verified_context.revision_dependencies_verified_at.isoformat(),
                "current_restated_training_as_of": context_fit_freeze.isoformat(),
            }
        )
        event(
            "snapshot",
            "running",
            "publish_exact_current_restated_raw_shards",
            {
                "snapshot_database_sha256": snapshot["snapshot_database_sha256"],
                "snapshot_receipt_sha256": snapshot["snapshot_receipt_sha256"],
                "source_context_envelope_sha256": context_sha,
            },
        )

        raw_output = cycle_root / "raw_publication"
        raw_output.mkdir(exist_ok=False)
        persistent_budget = CURRENT_CYCLE_PERSISTENT_BUDGET_BYTES
        temporary_budget = CURRENT_CYCLE_TEMPORARY_BUDGET_BYTES
        raw_command = [
            sys.executable,
            str(RAW_SHARD_SCRIPT),
            "--database",
            str(snapshot_database),
            "--output-dir",
            str(raw_output),
            "--decision-at",
            snapshot_completed.isoformat(),
            "--symbols",
            *symbols,
            "--current-restated-research",
            "--snapshot-database",
            str(snapshot_database),
            "--snapshot-receipt",
            str(snapshot_receipt_path),
            "--expected-snapshot-database-sha256",
            snapshot["snapshot_database_sha256"],
            "--expected-snapshot-receipt-sha256",
            snapshot["snapshot_receipt_sha256"],
            "--original-source-database",
            str(source_database),
            "--data-selection-as-of",
            context_fit_freeze.isoformat(),
            "--persistent-storage-budget-bytes",
            str(persistent_budget),
            "--temporary-storage-budget-bytes",
            str(temporary_budget),
            "--safety-reserve-bytes",
            str(CURRENT_CYCLE_SAFETY_RESERVE_BYTES),
            "--heavy-lock-path",
            str(lock_path),
        ]
        event("raw_publication", "running", "run_existing_current_restated_annual_raw_cli")
        raw_cli = run_cycle_child_json(
            raw_command,
            stage="raw_publication",
            child_name="annual_raw",
            timeout_seconds=6 * 60 * 60,
            label="current-restated annual raw producer",
        )
        if (
            raw_cli.get("research_only") is not True
            or raw_cli.get("data_temporality") != "current_restated_research"
            or raw_cli.get("formal_oos_allowed") is not False
            or raw_cli.get("production_alpha_bp") != 0
        ):
            raise _InvalidEvidence("annual raw CLI output is not a research-only current-restated publication")
        raw_manifest_path = _require_run_path(
            raw_cli.get("manifest_path"), root=raw_output, label="raw publication manifest"
        )
        raw_manifest_pin = _pin_regular_file(raw_manifest_path, label="raw publication manifest")
        raw_manifest = _parse_json_object(raw_manifest_path.read_bytes(), "raw publication manifest")
        raw_dataset_value = None
        dataset_paths = raw_cli.get("dataset_manifest_paths")
        if isinstance(dataset_paths, Mapping):
            raw_dataset_value = dataset_paths.get("core_long_history")
        if raw_dataset_value is None:
            raw_dataset_value = raw_manifest_path.parent / "core_long_history" / "manifest.json"
        raw_dataset_path = _require_run_path(
            str(raw_dataset_value), root=raw_output, label="core_long_history dataset manifest"
        )
        raw_dataset_pin = _pin_regular_file(raw_dataset_path, label="core_long_history dataset manifest")
        raw_dataset_manifest = _parse_json_object(raw_dataset_path.read_bytes(), "core_long_history dataset manifest")
        if (
            raw_manifest.get("manifest_hash") is None
            or raw_manifest.get("manifest_hash")
            != _canonical_sha256(_without_field(raw_manifest, "manifest_hash"))
            or raw_cli.get("manifest_path") != str(raw_manifest_path)
            or raw_cli.get("data_temporality") != "current_restated_research"
            or set(raw_manifest.get("symbols", symbols)) != set(symbols)
            or raw_dataset_manifest.get("dataset_id") not in {None, "core_long_history"}
        ):
            raise _InvalidEvidence("raw publication manifest identity or current scope differs")
        state["raw_publication"] = {
            "manifest_path": str(raw_manifest_path),
            "manifest_sha256": "sha256:" + raw_manifest_pin["sha256"],
            "dataset_manifest_path": str(raw_dataset_path),
            "dataset_manifest_sha256": "sha256:" + raw_dataset_pin["sha256"],
            "run_id": raw_manifest.get("run_id", raw_manifest.get("publication_id")),
        }
        state["same_run_pins"].update(
            {
                "raw_publication_manifest_path": str(raw_manifest_path),
                "raw_publication_manifest_sha256": state["raw_publication"]["manifest_sha256"],
                "raw_dataset_manifest_path": str(raw_dataset_path),
                "raw_dataset_manifest_sha256": state["raw_publication"]["dataset_manifest_sha256"],
            }
        )
        _record_cycle_growth(state, cycle_root)
        event(
            "raw_publication",
            "completed",
            "build_current_restated_outcome_artifact",
            state["same_run_pins"],
        )
        event(
            "outcome_artifact",
            "running",
            "build_current_restated_outcome_artifact",
            state["same_run_pins"],
        )

        outcome_output = cycle_root / "outcome_artifacts"
        outcome_output.mkdir(exist_ok=False)
        outcome_command = [
            sys.executable,
            str(OUTCOME_STORE_SCRIPT),
            "--raw-publication-manifest",
            str(raw_manifest_path),
            "--expected-raw-publication-manifest-sha256",
            state["raw_publication"]["manifest_sha256"],
            "--expected-core-dataset-manifest-sha256",
            state["raw_publication"]["dataset_manifest_sha256"],
            "--output-dir",
            str(outcome_output),
            "--target-symbols",
            *symbols,
            "--repository-root",
            str(repo),
        ]
        outcome_cli = run_cycle_child_json(
            outcome_command,
            stage="outcome_artifact",
            child_name="direct_outcome",
            timeout_seconds=6 * 60 * 60,
            label="current-restated outcome Direct producer",
        )
        outcome_summary = _pin_outcome_cli_summary(
            outcome_cli,
            output_root=outcome_output,
            symbols=symbols,
            raw_publication_manifest_sha256=state["raw_publication"]["manifest_sha256"],
            raw_dataset_manifest_sha256=state["raw_publication"]["dataset_manifest_sha256"],
        )
        outcome_path = Path(str(outcome_summary["manifest_path"]))
        outcome_pin = outcome_summary["manifest_pin"]
        registry_sha = str(outcome_summary["feature_registry_sha256"])
        state["outcome"] = {
            "receipt_path": str(outcome_path),
            "receipt_sha256": outcome_summary["manifest_sha256"],
            "feature_registry_sha256": registry_sha,
            "run_id": outcome_summary["run_id"],
            "artifact_available_at": outcome_summary["artifact_available_at"],
            "observation_count": outcome_summary["observation_count"],
            "feature_count": outcome_summary["feature_count"],
            "fold_count": outcome_summary["fold_count"],
            "summary_validation": "producer_summary_and_exact_manifest_bytes_pinned",
            "full_validation": "pending_exact_hash_fit_loader",
        }
        state["same_run_pins"].update(
            {
                "outcome_artifact_receipt_path": str(outcome_path),
                "outcome_artifact_receipt_sha256": state["outcome"]["receipt_sha256"],
                "outcome_feature_registry_sha256": registry_sha,
            }
        )
        _record_cycle_growth(state, cycle_root)
        event(
            "outcome_artifact",
            "completed",
            "fit_bounded_core19_current_restated_model",
            state["same_run_pins"],
        )
        event(
            "fit",
            "running",
            "fit_bounded_core19_current_restated_model",
            state["same_run_pins"],
        )

        current_price_fingerprints = state["current_price_row_fingerprint_sha256_by_symbol"]
        fit_output = _new_fit_output_path(cycle_root)
        b_freeze = b_terminal.get("current_observation_freeze")
        if not isinstance(b_freeze, str) or not b_freeze:
            raise _InvalidEvidence("B terminal current observation freeze is missing")
        fit_command = [
            sys.executable,
            str(FIT_SCRIPT),
            "--fit-current-restated-outcome-artifact",
            str(outcome_path),
            "--expected-outcome-artifact-sha256",
            state["outcome"]["receipt_sha256"],
            "--expected-raw-publication-manifest-sha256",
            state["raw_publication"]["manifest_sha256"],
            "--expected-raw-dataset-manifest-sha256",
            state["raw_publication"]["dataset_manifest_sha256"],
            "--expected-outcome-feature-registry-sha256",
            registry_sha,
            "--source-context-file",
            str(context_path),
            "--expected-source-context-sha256",
            context_sha,
            "--b-consumption-receipt",
            str(b_terminal["consumption_receipt_path"]),
            "--expected-b-consumption-receipt-sha256",
            str(b_terminal["consumption_receipt_sha256"]),
            "--expected-b-candidate-manifest-sha256",
            str(b_terminal["projection_manifest_sha256"]),
            "--expected-b-adapted-manifest-sha256",
            str(b_terminal["adapted_manifest_canonical_sha256"]),
            "--expected-b-feature-registry-sha256",
            str(b_terminal["feature_registry_sha256"]),
            "--b-current-observation-freeze",
            b_freeze,
            "--current-symbols",
            ",".join(symbols),
            "--current-event-date",
            normalized_date,
            "--output-directory",
            str(fit_output),
        ]
        fit_cli = _require_core19_fit_receipt(
            run_cycle_child_json(
                fit_command,
                stage="fit",
                child_name="bounded_core19",
                timeout_seconds=2 * 60 * 60,
                label="bounded CORE19 current-restated research fit",
            )
        )
        if (
            fit_cli.get("status") != "verified_base_outcome_only"
            or fit_cli.get("training_performed") is not True
            or fit_cli.get("verified_model_reused") is not False
            or fit_cli.get("historical_pit_eligible") is not False
            or fit_cli.get("formal_training_eligible") is not False
            or fit_cli.get("full_allocation_status") != "blocked_full_allocation_teacher_unavailable"
        ):
            detail = fit_cli.get("reason") or fit_cli.get("status") or "fit receipt contract mismatch"
            if _known_maturity_block(fit_cli):
                raise _WaitingForSource(f"bounded fit is waiting for verified mature outcomes: {detail}")
            raise _InvalidEvidence(f"bounded fit status or safety contract differs: {detail}")
        state["outcome"]["full_validation"] = "verified_by_exact_hash_fit_loader"
        model_manifest_path = _require_run_path(
            fit_cli.get("model_manifest_path"), root=fit_output, label="CORE19 model manifest"
        )
        model_manifest_pin = _pin_regular_file(model_manifest_path, label="CORE19 model manifest")
        model_manifest = _parse_json_object(model_manifest_path.read_bytes(), "CORE19 model manifest")
        model_manifest_sha = _sha256_pin(fit_cli.get("model_manifest_sha256"), "model manifest SHA")
        model_bundle_sha = _sha256_pin(fit_cli.get("model_bundle_sha256"), "model bundle SHA")
        if "sha256:" + model_manifest_pin["sha256"] != model_manifest_sha:
            raise _InvalidEvidence("CORE19 model manifest actual bytes differ from fit receipt")
        state["fit"] = {
            "receipt": fit_cli,
            "model_manifest_path": str(model_manifest_path),
            "model_manifest_sha256": model_manifest_sha,
            "model_bundle_sha256": model_bundle_sha,
            "fit_terminal_receipt_path": str((fit_output / "fit_receipt.json").resolve()),
            "current_price_row_fingerprint_sha256_by_symbol": current_price_fingerprints,
        }
        fit_receipt_path = fit_output / "fit_receipt.json"
        _write_create_only(
            fit_receipt_path,
            {
                "schema_version": "current-restated-core19-fit-terminal.v1",
                **fit_cli,
                "actual_stdout_sha256": fit_cli.stdout_sha256,
                "model_manifest_path": str(model_manifest_path),
                "model_manifest_bytes_sha256": model_manifest_sha,
                "model_bundle_sha256": model_bundle_sha,
                "raw_publication_manifest_sha256": state["raw_publication"]["manifest_sha256"],
                "raw_dataset_manifest_sha256": state["raw_publication"]["dataset_manifest_sha256"],
                "outcome_receipt_sha256": state["outcome"]["receipt_sha256"],
                "b_consumption_receipt_sha256": b_terminal["consumption_receipt_sha256"],
                "current_symbols": list(symbols),
                "current_event_date": normalized_date,
            },
        )
        state["same_run_pins"].update(
            {
                "fit_receipt_path": str(fit_receipt_path.resolve()),
                "model_manifest_path": str(model_manifest_path),
                "model_manifest_sha256": model_manifest_sha,
                "model_bundle_sha256": model_bundle_sha,
                "current_price_row_fingerprint_sha256_by_symbol": current_price_fingerprints,
            }
        )
        _record_cycle_growth(state, cycle_root)
        event("fit", "completed", "run_verified_current_restated_sidecar", state["same_run_pins"])
        event("sidecar", "running", "run_verified_current_restated_sidecar", state["same_run_pins"])

        from ml_module.current_restated_research_bridge import (
            CurrentRestatedResearchInvocation,
            run_current_restated_research_sidecar,
        )
        from ml_module.recommendation_cost_scenario import build_legacy_cost_scenario

        invocation = CurrentRestatedResearchInvocation(
            source_context_path=context_path,
            source_context_sha256=context_sha,
            outcome_receipt_path=outcome_path,
            outcome_receipt_sha256=state["outcome"]["receipt_sha256"],
            raw_publication_manifest_sha256=state["raw_publication"]["manifest_sha256"],
            raw_dataset_manifest_sha256=state["raw_publication"]["dataset_manifest_sha256"],
            outcome_feature_registry_sha256=registry_sha,
            b_consumption_receipt_path=Path(str(b_terminal["consumption_receipt_path"])),
            b_consumption_receipt_sha256=str(b_terminal["consumption_receipt_sha256"]),
            b_candidate_manifest_sha256=str(b_terminal["projection_manifest_sha256"]),
            b_adapted_manifest_sha256=str(b_terminal["adapted_manifest_canonical_sha256"]),
            b_feature_registry_sha256=str(b_terminal["feature_registry_sha256"]),
            model_manifest_path=model_manifest_path,
            model_manifest_sha256=model_manifest_sha,
            model_bundle_sha256=model_bundle_sha,
            current_symbols=symbols,
            current_event_date=normalized_date,
            b_current_observation_freeze=b_freeze,
            inference_at=None,
            output_root=cycle_root,
        )
        sidecar = run_current_restated_research_sidecar(
            invocation,
            lane="legacy",
            cost_scenario=build_legacy_cost_scenario(50),
            actual_invocation=invocation.child_arguments(),
            repository_root=repo,
        )
        sidecar_path = Path(sidecar.receipt_path).resolve(strict=True)
        sidecar_sha = _sha256_pin(sidecar.receipt_sha256, "sidecar receipt SHA")
        sidecar_pin = _pin_regular_file(sidecar_path, label="current-restated sidecar receipt")
        if "sha256:" + sidecar_pin["sha256"] != sidecar_sha:
            raise _InvalidEvidence("sidecar receipt actual bytes differ from its returned pin")
        state["sidecar"] = {
            "receipt_path": str(sidecar_path),
            "receipt_sha256": sidecar_sha,
        }
        state["same_run_pins"].update(
            {"sidecar_receipt_path": str(sidecar_path), "sidecar_receipt_sha256": sidecar_sha}
        )
        event(
            "sidecar",
            "completed",
            "publish_exact_current_stock_ml_registry_record",
            state["same_run_pins"],
        )
        event(
            "registry",
            "running",
            "publish_exact_current_stock_ml_registry_record",
            state["same_run_pins"],
        )

        from app_module.stock_research_report_provider_adapters import (
            publish_current_restated_stock_research_run,
        )

        from ml_module.current_restated_research_bridge import load_current_restated_outcome_model

        published = publish_current_restated_stock_research_run(
            model_loader=load_current_restated_outcome_model,
            repository_root=repo,
            research_output_root=research_root,
            sidecar_receipt_path=sidecar_path,
            expected_sidecar_receipt_sha256=sidecar_sha,
            model_manifest_path=model_manifest_path,
            expected_model_manifest_sha256=model_manifest_sha,
            expected_model_bundle_sha256=model_bundle_sha,
            cycle_id=raw_run_id,
            current_price_row_fingerprint_sha256_by_symbol=current_price_fingerprints,
            current_price_rows_source_path=Path(str(b_terminal["projection_observations_path"])),
            expected_current_price_rows_source_sha256=str(
                b_terminal["projection_observations_sha256"]
            ),
            scope_mode="current_stock_research",
        )
        if published.cycle_id != raw_run_id or published.indexed is not True:
            raise _InvalidEvidence("publisher result is not indexed to this exact current-stock cycle")
        record_path = Path(published.record_path).resolve(strict=True)
        record_pin = _pin_regular_file(record_path, label="immutable ML registry record")
        if "sha256:" + record_pin["sha256"] != _sha256_pin(
            published.record_sha256, "registry record SHA"
        ):
            raise _InvalidEvidence("ML registry record bytes differ from publisher result")
        record = _parse_json_object(record_path.read_bytes(), "ML registry record")
        current_price_rows_source_path = Path(
            str(b_terminal["projection_observations_path"])
        ).resolve(strict=True)
        _verify_published_current_stock_registry_record(
            record,
            raw_run_id=raw_run_id,
            published_run_id=published.run_id,
            source_date=normalized_date,
            symbols=symbols,
            source_context_sha256=context_sha,
            sidecar_receipt_sha256=sidecar_sha,
            model_manifest_sha256=model_manifest_sha,
            model_bundle_sha256=model_bundle_sha,
            current_price_fingerprints=current_price_fingerprints,
            current_price_rows_source_path=current_price_rows_source_path,
            current_price_rows_source_sha256=str(
                b_terminal["projection_observations_sha256"]
            ),
        )
        index_path = Path(published.index_path).resolve(strict=True)
        index_pin = _pin_regular_file(index_path, label="append-only ML registry index")
        index_rows = [
            _parse_json_object(line, "ML registry index entry")
            for line in index_path.read_bytes().splitlines()
            if line.strip()
        ]
        matching = [item for item in index_rows if item.get("run_id") == published.run_id]
        if (
            len(matching) != 1
            or matching[0].get("record_path") != f"runs/{published.run_id}/record.json"
            or _sha256_pin(matching[0].get("record_sha256"), "indexed registry record SHA")
            != _sha256_pin(published.record_sha256, "publisher registry record SHA")
        ):
            raise _InvalidEvidence("append-only registry index does not bind the immutable record")
        state["registry"] = {
            "run_id": published.run_id,
            "record_path": str(record_path),
            "record_sha256": published.record_sha256,
            "index_path": str(index_path),
            "index_sha256_at_completion": "sha256:" + index_pin["sha256"],
            "indexed": bool(published.indexed),
        }
        state["same_run_pins"].update(
            {
                "registry_record_path": str(record_path),
                "registry_record_sha256": published.record_sha256,
                "registry_index_path": str(index_path),
                "registry_index_sha256_at_completion": state["registry"]["index_sha256_at_completion"],
            }
        )
        _record_cycle_growth(state, cycle_root)
        terminal_status = "completed"
        terminal_reason = None
        terminal_error_type = None
        next_action = "continue_natural_current_stock_evidence_accumulation"
        last_success_at = _utc_now().isoformat()
        state["last_success_at"] = last_success_at
        event("registry", "completed", next_action, state["same_run_pins"])
    except _WaitingForSource as exc:
        terminal_status = "waiting_source"
        terminal_reason = str(exc)
        terminal_error_type = type(exc).__name__
        next_action = "restore_or_accumulate_the_named_current_source_input_then_run_a_new_raw_cycle"
        try:
            event(state.get("stage", "source"), "waiting_source", next_action)
        except OSError:
            pass
    except StorageCapacityError as exc:
        terminal_status = "blocked_capacity"
        terminal_reason = str(exc)
        terminal_error_type = type(exc).__name__
        next_action = "free_or_provision_snapshot_plus_2gib_persistent_2gib_temporary_and_20gib_reserve"
        state["capacity_error"] = dict(getattr(exc, "preflight", {}))
        try:
            event(state.get("stage", "capacity"), "blocked_capacity", next_action)
        except OSError:
            pass
    except Exception as exc:  # noqa: BLE001 - persist bounded stage failure for operations
        terminal_status = "failed"
        terminal_reason = str(exc)
        terminal_error_type = type(exc).__name__
        next_action = "inspect_exact_cycle_stage_receipt_and_retry_with_a_new_raw_run_id"
        stage_results = state.setdefault("stage_results", {})
        if isinstance(stage_results, dict):
            stage_result = stage_results.setdefault(str(state.get("stage") or "unknown"), {})
            if isinstance(stage_result, dict):
                stage_result["stage_error"] = {
                    "error_type": terminal_error_type,
                    "message": terminal_reason[:4000],
                }
        try:
            event(state.get("stage", "unknown"), "failed", next_action)
        except OSError:
            pass
    try:
        terminal = _cycle_terminal(
            cycle_root=cycle_root,
            state=state,
            status=terminal_status,
            reason=terminal_reason,
            error_type=terminal_error_type,
            next_action=next_action,
            last_success_at=last_success_at,
            now_provider=now_provider,
        )
        if terminal_status == "completed":
            registry = state.get("registry")
            if not isinstance(registry, Mapping):
                raise _InvalidEvidence("completed cycle did not retain exact registry pins")
            try:
                entry = _append_cycle_reuse_index(
                    cycle_index_path,
                    entries_before=cycle_index_entries,
                    raw_run_id=raw_run_id,
                    source_date=normalized_date,
                    reuse_key_sha256=reuse_key_sha256,
                    terminal_receipt_path=Path(terminal["terminal_receipt_path"]),
                    terminal_receipt_sha256=str(terminal["terminal_receipt_sha256"]),
                    registry_record_path=Path(str(registry["record_path"])),
                    registry_record_sha256=str(registry["record_sha256"]),
                )
                terminal["reuse_index"] = {
                    "path": str(cycle_index_path.resolve()),
                    "entry_sha256": entry["entry_sha256"],
                    "indexed": True,
                }
            except Exception as index_exc:  # noqa: BLE001 - do not invalidate completed pinned evidence
                terminal["reuse_index"] = {
                    "path": str(cycle_index_path.resolve()),
                    "indexed": False,
                    "error_type": type(index_exc).__name__,
                    "error": str(index_exc),
                }
        if status_callback is not None:
            status_callback(terminal)
        return terminal
    finally:
        if reservation_owned:
            release_heavy_chain_reservation(reservation)


__all__ = [
    "CurrentStockResearchCycleError",
    "run_current_stock_research_cycle",
]
