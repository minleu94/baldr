"""Read-only current-observed ownership projections for stock reports.

This adapter is deliberately separate from the formal/PIT tables. Institutional
and credit rows are accepted only from the Phase 3C normalized observation
ledger after re-hashing its canonical payload and matching it to the candidate
table. TDCC rows are accepted only by replaying an exact raw capture under the
configured output root. None of these rows establishes historical availability.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import heapq
import json
from pathlib import Path
import re
import sqlite3
import stat
from typing import Any, Callable, Mapping


MAX_LATEST_TIE_OBSERVATIONS = 16
MAX_TDCC_CAPTURE_DIRS_TO_INSPECT = 32
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_TDCC_RAW_BYTES = 32 * 1024 * 1024
MAX_TDCC_ARTIFACT_BYTES = 64 * 1024 * 1024
_SHA256_RE = re.compile(r"(?:sha256:)?[0-9a-f]{64}\Z")
_OBSERVATION_SCHEMA = "phase3c-canonical-observation.v1"
_TDCC_SCHEMA = "tdcc-current-ownership-capture.v1"
_SUPPORTED_VERSIONS = {
    "institutional": frozenset({"twse-official-T86", "tpex-official-3itrade"}),
    "credit": frozenset({
        "twse-official-MI_MARGN",
        "tpex-official-margin_bal",
        "tpex-mainboard-margin-openapi.v1",
    }),
}
_TABLES = {"institutional": "institutional_flows", "credit": "credit_transactions"}
_FLOW_FIELDS = {
    "institutional": (
        "foreign_investor_buy", "foreign_investor_sell", "foreign_investor_net",
        "investment_trust_buy", "investment_trust_sell", "investment_trust_net",
        "dealer_buy", "dealer_sell", "dealer_net",
    ),
    "credit": (
        "margin_purchase", "margin_balance", "short_sale", "short_balance",
        "financing", "securities_lending",
    ),
}


@dataclass(frozen=True)
class CurrentOwnershipObservation:
    source_kind: str
    stock_code: str
    data_as_of: str
    values: Mapping[str, int | str]
    source_version: str
    custody_kind: str
    custody_sha256: str
    observed_at: str
    row_count: int
    limitations: tuple[str, ...]
    quantity_unit: str = ""


@dataclass(frozen=True)
class CurrentOwnershipReadResult:
    observations: Mapping[str, CurrentOwnershipObservation]
    diagnostics: Mapping[str, str]


def _aware(value: object, *, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a timezone-aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be a timezone-aware ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware ISO timestamp")
    return parsed


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _path_is_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError as exc:
        raise ValueError(f"source path cannot be inspected: {path}") from exc
    attributes = int(getattr(info, "st_file_attributes", 0))
    return stat.S_ISLNK(info.st_mode) or bool(attributes & 0x400)


def _require_plain_path(path: Path, *, directory: bool | None = None) -> Path:
    candidate = path.expanduser().absolute()
    # Reject reparse/symlink components, including the selected root, before
    # resolving it. This avoids silently following a redirected custody root.
    current = Path(candidate.anchor)
    for component in candidate.parts[1:]:
        current = current / component
        if current.exists() or current.is_symlink():
            if _path_is_reparse(current):
                raise ValueError(f"reparse/symlink source path is not accepted: {current}")
    resolved = candidate.resolve(strict=True)
    if directory is True and not resolved.is_dir():
        raise ValueError(f"source root is not a directory: {resolved}")
    if directory is False and not resolved.is_file():
        raise ValueError(f"source artifact is not a regular file: {resolved}")
    return resolved


def _read_bounded(path: Path, *, limit: int) -> bytes:
    resolved = _require_plain_path(path, directory=False)
    before = resolved.stat()
    if before.st_size < 0 or before.st_size > limit:
        raise ValueError(f"source artifact exceeds bounded size: {resolved}")
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"source artifact is not a regular file: {resolved}")
    flags = os_flags = getattr(__import__("os"), "O_RDONLY")
    flags |= getattr(__import__("os"), "O_BINARY", 0)
    flags |= getattr(__import__("os"), "O_NOFOLLOW", 0)
    fd = __import__("os").open(resolved, flags)
    try:
        opened = __import__("os").fstat(fd)
        attributes = int(getattr(opened, "st_file_attributes", 0))
        if not stat.S_ISREG(opened.st_mode) or attributes & 0x400:
            raise ValueError(f"source artifact changed to non-regular/reparse file: {resolved}")
        if (opened.st_size, opened.st_mtime_ns, opened.st_ino) != (
            before.st_size, before.st_mtime_ns, before.st_ino
        ):
            raise ValueError(f"source artifact changed before read: {resolved}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = __import__("os").read(fd, min(1024 * 1024, limit + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > limit:
                raise ValueError(f"source artifact exceeds bounded size: {resolved}")
        after = __import__("os").fstat(fd)
        if (after.st_size, after.st_mtime_ns, after.st_ino) != (
            opened.st_size, opened.st_mtime_ns, opened.st_ino
        ) or total != after.st_size:
            raise ValueError(f"source artifact changed during read: {resolved}")
        return b"".join(chunks)
    finally:
        __import__("os").close(fd)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_json_object(data: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} root must be an object")
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _is_int(value: object) -> bool:
    return type(value) is int


def _row_clock_fields(row: Mapping[str, Any], observation_at: datetime) -> None:
    for field in ("first_observed_at", "available_at"):
        stamp = _aware(row.get(field), name=field)
        if stamp > observation_at:
            raise ValueError(f"{field} is later than normalized observation")


def _verify_flow_observation(
    conn: sqlite3.Connection,
    *,
    source: str,
    source_row: Mapping[str, Any],
    stock_code: str,
    cutoff: date,
    read_clock: datetime,
) -> tuple[dict[str, Any], dict[str, Any], str] | None:
    day = str(source_row["decision_date"])
    parsed_day = date.fromisoformat(day)
    if parsed_day > cutoff:
        raise ValueError("observation data date is later than requested cutoff")
    observation_at = _aware(source_row["observed_at"], name="observation observed_at")
    if observation_at > read_clock:
        raise ValueError("normalized observation is from the future")
    payload_text = source_row["canonical_payload_json"]
    if not isinstance(payload_text, str) or not payload_text:
        raise ValueError("normalized canonical payload is missing")
    expected_hash = str(source_row["observation_hash"])
    if not _SHA256_RE.fullmatch(expected_hash) or expected_hash != "sha256:" + _digest(payload_text.encode("utf-8")):
        raise ValueError("normalized observation hash mismatch")
    payload = _parse_json_object(payload_text.encode("utf-8"), label="normalized observation")
    if payload.get("schema_version") != _OBSERVATION_SCHEMA or not isinstance(payload.get("rows"), list):
        raise ValueError("normalized observation schema mismatch")
    payload_clock = _aware(payload.get("observation_at"), name="payload observation_at")
    if payload_clock != observation_at:
        raise ValueError("normalized observation clock mismatch")
    if _canonical_json(payload) != payload_text:
        raise ValueError("normalized observation JSON is not canonical")
    diagnostic = _parse_json_object(
        str(source_row["diagnostic_json"] or "").encode("utf-8"),
        label="reconciliation diagnostic",
    )
    if (
        diagnostic.get("status") != "RECONCILED"
        or diagnostic.get("observation_hash") != expected_hash
        or diagnostic.get("decision_date") != day
        or int(diagnostic.get("expected_row_count", -1)) != int(source_row["row_count"])
        or diagnostic.get("observation_at") is None
        or _aware(diagnostic.get("observation_at"), name="diagnostic observation_at") != observation_at
    ):
        raise ValueError("normalized observation lacks matching successful reconciliation")
    observation_mode = str(source_row["observation_mode"])
    if observation_mode not in {"exact_replay", "new_observation_reconciled", "new_observation_insert"}:
        raise ValueError("normalized observation mode is not reconciled")
    records = payload["rows"]
    if len(records) != int(source_row["row_count"]) or len(records) != int(diagnostic["expected_row_count"]):
        raise ValueError("normalized observation row count mismatch")
    table = _TABLES[source]
    columns = tuple(str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall())
    if not columns:
        raise ValueError(f"candidate table is missing: {table}")
    versions_text = source_row["source_versions"]
    try:
        declared_versions = json.loads(str(versions_text))
    except json.JSONDecodeError as exc:
        raise ValueError("normalized source_versions is invalid JSON") from exc
    if not isinstance(declared_versions, list):
        raise ValueError("normalized source_versions is not a list")
    versions = _SUPPORTED_VERSIONS[source]
    rows_by_code: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict) or set(record) != set(columns):
            raise ValueError("normalized row columns do not match candidate table")
        code = str(record.get("stock_code") or "").strip()
        if not code or code in rows_by_code or record.get("decision_date") != day:
            raise ValueError("normalized row identity is invalid or duplicated")
        version = str(record.get("source_version") or "")
        if version not in versions:
            raise ValueError("normalized row source version is unsupported")
        _row_clock_fields(record, observation_at)
        if source == "institutional":
            fields = _FLOW_FIELDS[source]
            if any(not _is_int(record.get(field)) for field in fields):
                raise ValueError("institutional quantities must be integers")
            for group in ("foreign_investor", "investment_trust", "dealer"):
                if record[f"{group}_buy"] - record[f"{group}_sell"] != record[f"{group}_net"]:
                    raise ValueError("institutional buy/sell/net values do not reconcile")
        else:
            for field in ("margin_purchase", "margin_balance", "short_sale", "short_balance"):
                if not _is_int(record.get(field)):
                    raise ValueError("credit quantities must be integers")
            for field in ("financing", "securities_lending"):
                if record.get(field) is not None and not _is_int(record.get(field)):
                    raise ValueError("credit optional quantities must be integers")
        rows_by_code[code] = record
    actual_versions = sorted({str(row["source_version"]) for row in records})
    if sorted(set(str(item) for item in declared_versions)) != actual_versions:
        raise ValueError("normalized source_versions do not match payload rows")
    actual_cursor = conn.execute(
        f'SELECT * FROM "{table}" WHERE decision_date=? ORDER BY stock_code', (day,)
    )
    actual_rows = [dict(row) for row in actual_cursor.fetchall()]
    if len(actual_rows) != len(records):
        raise ValueError("candidate table row count differs from normalized observation")
    actual_by_code = {str(row.get("stock_code") or ""): row for row in actual_rows}
    if len(actual_by_code) != len(actual_rows) or set(actual_by_code) != set(rows_by_code):
        raise ValueError("candidate table keys differ from normalized observation")
    for code, expected in rows_by_code.items():
        if _canonical_json(actual_by_code[code]) != _canonical_json(expected):
            raise ValueError("candidate table row differs from normalized observation")
    if str(source_row["source"]) != source:
        raise ValueError("normalized source identity mismatch")
    target = rows_by_code.get(stock_code)
    if target is None:
        return None
    return target, payload, expected_hash


def _read_flow_observation(
    candidate_db_file: Path | None,
    *,
    source: str,
    stock_code: str,
    cutoff: date,
    read_clock: datetime,
) -> tuple[CurrentOwnershipObservation | None, str]:
    if candidate_db_file is None:
        return None, "Phase 3C candidate DB path is not configured"
    try:
        db_path = _require_plain_path(candidate_db_file, directory=False)
        uri = db_path.as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='phase3c_source_observations'"
            ).fetchone()
            if exists is None:
                return None, "normalized Phase 3C observation custody table is missing"
            info = conn.execute('PRAGMA table_info("phase3c_source_observations")').fetchall()
            required = {
                "source", "decision_date", "observation_hash", "observed_at", "row_count",
                "observation_mode", "source_versions", "canonical_payload_json", "diagnostic_json",
            }
            if not required.issubset({str(row[1]) for row in info}):
                return None, "normalized Phase 3C observation custody schema is incomplete"
            # Read only small metadata while selecting. Older payloads may be
            # large and are not relevant once the latest date/clock is known.
            # A corrupt newest payload must fail closed; it must never cause a
            # fallback to an older observation.
            latest = conn.execute(
                "SELECT rowid AS observation_rowid,source,decision_date,observation_hash,observed_at,"
                "row_count,observation_mode,source_versions,diagnostic_json "
                "FROM phase3c_source_observations WHERE source=? AND decision_date<=? "
                "ORDER BY decision_date DESC,observed_at DESC,observation_hash DESC LIMIT 1",
                (source, cutoff.isoformat()),
            ).fetchone()
            if latest is None:
                return None, f"no {source} normalized observation is available by the requested date"
            latest_date = str(latest["decision_date"])
            latest_at = str(latest["observed_at"])
            latest_group = conn.execute(
                "SELECT rowid AS observation_rowid,source,decision_date,observation_hash,observed_at,"
                "row_count,observation_mode,source_versions,diagnostic_json "
                "FROM phase3c_source_observations WHERE source=? AND decision_date=? AND observed_at=? "
                "ORDER BY observation_hash DESC LIMIT ?",
                (source, latest_date, latest_at, MAX_LATEST_TIE_OBSERVATIONS + 1),
            ).fetchall()
            if len(latest_group) > MAX_LATEST_TIE_OBSERVATIONS:
                return None, f"{source} latest same-clock observation group exceeds its bound"
            verified: list[tuple[dict[str, Any] | None, str, datetime]] = []
            for metadata in latest_group:
                payload_row = conn.execute(
                    "SELECT canonical_payload_json FROM phase3c_source_observations WHERE rowid=?",
                    (metadata["observation_rowid"],),
                ).fetchone()
                if payload_row is None:
                    raise ValueError("selected normalized observation disappeared during read")
                source_row = dict(metadata)
                source_row["canonical_payload_json"] = payload_row["canonical_payload_json"]
                checked = _verify_flow_observation(
                    conn, source=source, source_row=source_row, stock_code=stock_code,
                    cutoff=cutoff, read_clock=read_clock,
                )
                observed_clock = _aware(metadata["observed_at"], name="observation observed_at")
                verified.append((
                    checked[0] if checked is not None else None,
                    checked[2] if checked is not None else str(metadata["observation_hash"]),
                    observed_clock,
                ))
        target_rows = [item[0] for item in verified if item[0] is not None]
        if not target_rows:
            return None, f"latest verified {source} observation does not contain this stock"
        if len(target_rows) != len(verified):
            return None, f"conflicting {source} observations share the latest stock/date clock"
        reference = target_rows[0]
        compare_fields = tuple(reference)
        if any(any(item.get(field) != reference.get(field) for field in compare_fields) for item in target_rows[1:]):
            return None, f"conflicting {source} observations share the latest stock/date clock"
        selected_hash = max(item[1] for item in verified)
        row = reference
        values = {field: row[field] for field in _FLOW_FIELDS[source] if row.get(field) is not None}
        return CurrentOwnershipObservation(
            source_kind=source,
            stock_code=stock_code,
            data_as_of=latest_date,
            values=values,
            source_version=str(row["source_version"]),
            custody_kind="normalized_custody",
            custody_sha256=selected_hash,
            observed_at=_stamp(verified[0][2]),
            row_count=len(values),
            limitations=(
                "candidate normalized observation; original HTTP body is not claimed by this custody",
                "publication time/date is unknown; historical PIT and formal eligibility are false",
            ),
            quantity_unit=(
                "shares"
                if source == "institutional"
                or str(row["source_version"]) == "tpex-mainboard-margin-openapi.v1"
                else "lots"
                if str(row["source_version"]) == "tpex-official-margin_bal"
                else "trading_units"
            ),
        ), ""
    except (OSError, sqlite3.Error, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return None, f"{source} normalized custody rejected: {type(exc).__name__}: {exc}"


def _same_stable_tier_fields(row: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(str(row.get(field, "")) for field in (
        "symbol", "report_date", "tier", "holder_count", "shares", "holding_ratio_bp",
        "tier_role", "source_payload_sha256", "raw_row_sha256", "quality",
        "availability_evidence", "source_version",
    ))


def _tdcc_capture_order(path: Path) -> tuple[str, str]:
    """Return a stable UTC/date ordering key for new and legacy capture IDs."""
    timestamp_match = re.search(r"(?<!\d)(\d{8}T\d{12}Z)(?!\d)", path.name)
    if timestamp_match:
        return timestamp_match.group(1), path.name
    date_match = re.search(r"(?<!\d)(\d{8})(?!\d)", path.name)
    if date_match:
        return date_match.group(1) + "T000000000000Z", path.name
    return "00000000T000000000000Z", path.name


def _read_tdcc_manifest(
    manifest_path: Path,
    *,
    stock_code: str,
    cutoff: date,
    earliest_clock: datetime,
    readback_clock: Callable[[], datetime],
) -> CurrentOwnershipObservation | None:
    from data_module.tdcc_shareholding_candidate import (
        TDCC_SOURCE_VERSION,
        TDCC_URL,
        normalize_tdcc_payload,
    )

    manifest_path = _require_plain_path(manifest_path, directory=False)
    if not re.fullmatch(r"tdcc_1-5_\d{8}_manifest\.json", manifest_path.name):
        raise ValueError("TDCC manifest filename is not canonical")
    manifest_bytes = _read_bounded(manifest_path, limit=MAX_MANIFEST_BYTES)
    manifest = _parse_json_object(manifest_bytes, label="TDCC manifest")
    manifest_schema = manifest.get("schema_version")
    if manifest_schema not in (None, _TDCC_SCHEMA):
        raise ValueError("TDCC manifest schema is unsupported")
    if manifest.get("source_id") != "tdcc_shareholding" or manifest.get("source_version") != TDCC_SOURCE_VERSION:
        raise ValueError("TDCC source identity/version mismatch")
    if manifest.get("endpoint") != TDCC_URL or manifest.get("candidate_only") is not True:
        raise ValueError("TDCC manifest endpoint/candidate contract mismatch")
    if manifest.get("formal_db_written") is not False or manifest.get("downstream_eligibility") != "none":
        raise ValueError("TDCC manifest must remain candidate-only")
    if manifest.get("publication_at") is not None or manifest.get("availability_policy") != "first_observed_only":
        raise ValueError("TDCC manifest publication/availability contract mismatch")
    report_date = date.fromisoformat(str(manifest.get("report_date", "")))
    if report_date > cutoff:
        return None
    capture = manifest.get("capture_metadata")
    if not isinstance(capture, dict) or capture.get("http_status") != 200:
        raise ValueError("TDCC capture metadata missing or HTTP status is not 200")
    raw_name = manifest.get("raw_file")
    if not isinstance(raw_name, str) or not raw_name:
        raise ValueError("TDCC raw file path is missing")
    raw_path = Path(raw_name)
    if not raw_path.is_absolute():
        raw_path = manifest_path.parent / raw_path
    raw_path = _require_plain_path(raw_path, directory=False)
    if raw_path.parent != manifest_path.parent.resolve() or not raw_path.name.startswith("tdcc_1-5_raw_") or raw_path.suffix.lower() != ".csv":
        raise ValueError("TDCC raw file must be a direct capture-directory CSV sibling")
    raw_bytes = _read_bounded(raw_path, limit=MAX_TDCC_RAW_BYTES)
    raw_sha = _digest(raw_bytes)
    if (
        raw_sha != str(manifest.get("source_payload_sha256", "")).lower()
        or raw_sha != str(capture.get("sha256", "")).lower()
        or len(raw_bytes) != int(capture.get("content_length", -1))
        or capture.get("raw_file") != raw_path.name
        or capture.get("url") != TDCC_URL
    ):
        raise ValueError("TDCC raw bytes do not match manifest/metadata pins")
    request_start_value = (
        manifest.get("request_started_at_utc")
        if manifest_schema == _TDCC_SCHEMA
        else capture.get("captured_at_utc")
    )
    request_start = _aware(request_start_value, name="TDCC request-start clock")
    if manifest_schema == _TDCC_SCHEMA and manifest.get("capture_id") != manifest_path.parent.name:
        raise ValueError("TDCC capture id does not match its directory")
    artifacts = manifest.get("artifact_hashes")
    tier_name = manifest.get("full_tier_file")
    if not isinstance(artifacts, dict) or not isinstance(tier_name, str) or Path(tier_name).name != tier_name:
        raise ValueError("TDCC tier artifact manifest binding is missing")
    tier_path = manifest_path.parent / tier_name
    tier_bytes = _read_bounded(tier_path, limit=MAX_TDCC_ARTIFACT_BYTES)
    if _digest(tier_bytes) != str(artifacts.get(tier_name, "")).lower():
        raise ValueError("TDCC tier artifact hash mismatch")
    if not tier_name.endswith("_tiers.csv"):
        raise ValueError("TDCC full tier artifact name is invalid")
    aggregate_name = tier_name.removesuffix("_tiers.csv") + "_aggregate.csv"
    aggregate_path = manifest_path.parent / aggregate_name
    aggregate_bytes = _read_bounded(aggregate_path, limit=MAX_TDCC_ARTIFACT_BYTES)
    if _digest(aggregate_bytes) != str(artifacts.get(aggregate_name, "")).lower():
        raise ValueError("TDCC aggregate artifact hash mismatch")
    # Pin the readback clock after all source bytes have been read and hashed.
    read_at = readback_clock()
    if read_at.tzinfo is None or read_at.utcoffset() is None:
        raise ValueError("TDCC reader clock must be timezone-aware")
    if read_at < earliest_clock:
        raise ValueError("TDCC reader clock moved backwards during report")
    if request_start > read_at:
        raise ValueError("TDCC request-start timestamp is later than the local readback clock")
    if manifest_schema == _TDCC_SCHEMA:
        body_completed_at = _aware(manifest.get("body_completed_at_utc"), name="TDCC body_completed_at_utc")
        if body_completed_at < request_start:
            raise ValueError("TDCC body completion precedes request start")
        if body_completed_at > read_at:
            raise ValueError("TDCC body completion is later than the local readback clock")
        observed_clock = body_completed_at
    else:
        # Legacy captures only have a pre-request clock. It is never treated
        # as completion; observing the pinned artifact happens at local readback.
        observed_clock = read_at
    replay = normalize_tdcc_payload(raw_bytes, observed_at=observed_clock)
    if replay.source_payload_sha256 != raw_sha or replay.report_date != report_date.isoformat():
        raise ValueError("TDCC replay identity differs from manifest")
    try:
        artifact_tiers = list(csv.DictReader(tier_bytes.decode("utf-8-sig").splitlines()))
        artifact_aggregates = list(csv.DictReader(aggregate_bytes.decode("utf-8-sig").splitlines()))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("TDCC artifact CSV is invalid") from exc
    if len(artifact_tiers) != len(replay.tier_rows):
        raise ValueError("TDCC tier artifact row count differs from raw replay")
    replay_tier_map = { (str(row["symbol"]), str(row["tier"])): row for row in replay.tier_rows }
    artifact_tier_map = { (str(row.get("symbol", "")), str(row.get("tier", ""))): row for row in artifact_tiers }
    if len(artifact_tier_map) != len(artifact_tiers) or set(replay_tier_map) != set(artifact_tier_map):
        raise ValueError("TDCC tier artifact keys differ from raw replay")
    if any(_same_stable_tier_fields(replay_tier_map[key]) != _same_stable_tier_fields(artifact_tier_map[key]) for key in replay_tier_map):
        raise ValueError("TDCC tier artifact stable values differ from raw replay")
    aggregate_map = {str(row.get("symbol", "")): row for row in artifact_aggregates}
    if len(aggregate_map) != len(artifact_aggregates):
        raise ValueError("TDCC aggregate artifact contains duplicate symbols")
    replay_aggregate = {str(row["symbol"]): row for row in replay.aggregate_rows}
    if set(replay_aggregate) != set(aggregate_map):
        raise ValueError("TDCC aggregate artifact keys differ from raw replay")
    for symbol, expected in replay_aggregate.items():
        actual = aggregate_map[symbol]
        for field in ("report_date", "source_version", "source_payload_sha256", "large_holder_ratio_bp", "retail_holder_ratio_bp", "dispersion_index_bp", "candidate_status"):
            if str(actual.get(field, "")) != str(expected.get(field, "")):
                raise ValueError("TDCC aggregate artifact values differ from raw replay")
    row = replay_aggregate.get(stock_code)
    if row is None:
        return None
    if row.get("candidate_status") != "shadow_ready":
        raise ValueError("TDCC target stock is quarantined by source reconciliation")
    tiers = sorted(
        (item for item in replay.tier_rows if str(item["symbol"]) == stock_code),
        key=lambda item: int(item["tier"]),
    )
    if len(tiers) != 17 or [int(item["tier"]) for item in tiers] != list(range(1, 18)):
        raise ValueError("TDCC target stock lacks exact 17 source tiers")
    compact_tiers = [
        {key: item[key] for key in ("tier", "holder_count", "shares", "holding_ratio_bp", "tier_role", "raw_row_sha256")}
        for item in tiers
    ]
    return CurrentOwnershipObservation(
        source_kind="tdcc",
        stock_code=stock_code,
        data_as_of=report_date.isoformat(),
        values={
            "large_holder_ratio_bp": int(row["large_holder_ratio_bp"]),
            "retail_holder_ratio_bp": int(row["retail_holder_ratio_bp"]),
            "dispersion_index_bp": int(row["dispersion_index_bp"]),
            "shareholding_tiers": _canonical_json(compact_tiers),
        },
        source_version=TDCC_SOURCE_VERSION,
        custody_kind="raw_capture_replayed",
        custody_sha256=raw_sha,
        observed_at=_stamp(observed_clock),
        row_count=len(tiers),
        limitations=(
            "current raw capture replay only; TDCC publication timestamp is unknown",
            "manifest request-start clock is not used as completed/available time; historical PIT and formal eligibility are false",
        ),
    )


def _read_tdcc(
    capture_root: Path | None,
    *,
    stock_code: str,
    cutoff: date,
    earliest_clock: datetime,
    readback_clock: Callable[[], datetime],
) -> tuple[CurrentOwnershipObservation | None, str]:
    if capture_root is None:
        return None, "TDCC current raw capture root is not configured"
    try:
        root = _require_plain_path(capture_root, directory=True)
        tdcc_root = root / "tdcc"
        if not tdcc_root.exists():
            return None, "TDCC current raw capture directory is missing"
        tdcc_root = _require_plain_path(tdcc_root, directory=True)
        # Keep a bounded set of the newest capture directories rather than
        # making all current data unavailable once the history exceeds a fixed
        # count. Capture directory names are immutable sortable run IDs. The
        # newest candidate is authoritative: corruption never falls back to an
        # older capture.
        newest_dirs = heapq.nlargest(
            MAX_TDCC_CAPTURE_DIRS_TO_INSPECT,
            (path for path in tdcc_root.iterdir() if path.is_dir()),
            key=_tdcc_capture_order,
        )
        if not newest_dirs:
            return None, "TDCC current raw capture directory has no capture runs"
        selected_dir = _require_plain_path(newest_dirs[0], directory=True)
        selected_manifest = max(
            selected_dir.glob("tdcc_1-5_*_manifest.json"),
            key=lambda path: path.name,
            default=None,
        )
        if selected_manifest is None:
            return None, "newest TDCC capture directory has no canonical manifest"
        observation = _read_tdcc_manifest(
            selected_manifest, stock_code=stock_code, cutoff=cutoff,
            earliest_clock=earliest_clock, readback_clock=readback_clock,
        )
        if observation is None:
            return None, "newest TDCC capture is not eligible for this report cutoff or lacks the stock"
        return observation, ""
    except (OSError, ValueError, TypeError) as exc:
        return None, f"TDCC raw custody rejected: {type(exc).__name__}: {exc}"


def read_current_observed_market_ownership(
    *,
    stock_code: str,
    cutoff: date,
    observed_at: datetime,
    candidate_db_file: Path | str | None,
    capture_root: Path | str | None,
    readback_clock: Callable[[], datetime] | None = None,
) -> CurrentOwnershipReadResult:
    """Read candidate observations for one current report invocation only.

    ``observed_at`` is the report invocation clock used as the upper bound for
    Phase 3C normalized observations. TDCC records use ``readback_clock`` after
    the pinned raw/manifest/artifacts have been read; request-start and
    publication dates never become availability claims.
    """
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    code = str(stock_code).strip()
    if not re.fullmatch(r"\d{4,6}", code):
        raise ValueError("stock_code must be a normalized stock symbol")
    if not isinstance(cutoff, date):
        raise ValueError("cutoff must be a date")
    candidate_path = Path(candidate_db_file) if candidate_db_file is not None else None
    root_path = Path(capture_root) if capture_root is not None else None
    observations: dict[str, CurrentOwnershipObservation] = {}
    diagnostics: dict[str, str] = {}
    for source in ("institutional", "credit"):
        value, diagnostic = _read_flow_observation(
            candidate_path, source=source, stock_code=code, cutoff=cutoff, read_clock=observed_at,
        )
        if value is not None:
            observations[source] = value
        if diagnostic:
            diagnostics[source] = diagnostic
    value, diagnostic = _read_tdcc(
        root_path, stock_code=code, cutoff=cutoff, earliest_clock=observed_at,
        readback_clock=readback_clock or (lambda: datetime.now(timezone.utc)),
    )
    if value is not None:
        observations["tdcc"] = value
    if diagnostic:
        diagnostics["tdcc"] = diagnostic
    return CurrentOwnershipReadResult(observations=observations, diagnostics=diagnostics)
