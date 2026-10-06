"""Verified current-only market-status evidence for live recommendations.

This module is deliberately separate from historical replay and PIT source
selection.  A status observation can exclude a symbol only when a fixed
current-status pointer, its snapshot/manifest, the exact official raw capture,
the notice effective date, and the invocation clock all agree.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType
from typing import Literal, Mapping, cast
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from data_module.current_market_status_observation import (
    CurrentMarketStatusError,
    CurrentMarketStatusReader,
)

CURRENT_MARKET_STATUS_EVIDENCE_SCHEMA = "current-market-status-preflight.v1"
CURRENT_MARKET_STATUS_POINTER_RELATIVE = Path(
    "release_v4", "current_market_status", "current_market_status_pointer.json"
)
_TAIPEI = ZoneInfo("Asia/Taipei")
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_MAX_PINNED_JSON_BYTES = 16 * 1024 * 1024
_MAX_PINNED_RAW_BYTES = 32 * 1024 * 1024
_OFFICIAL_HOSTS = {
    "twse": frozenset({"www.twse.com.tw"}),
    "tpex": frozenset({"www.tpex.org.tw"}),
}
_DISPOSITIONS = frozenset({"verified_delisted", "not_delisted", "unavailable"})


@dataclass(frozen=True, slots=True)
class CurrentMarketStatusPreflightResult:
    """One symbol's current-only market-status preflight result."""

    symbol: str
    disposition: Literal["verified_delisted", "not_delisted", "unavailable"]
    reason_code: str
    evidence: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if type(self.symbol) is not str or not self.symbol.strip():
            raise ValueError("symbol must be a non-empty string")
        if type(self.disposition) is not str or self.disposition not in _DISPOSITIONS:
            raise ValueError("unsupported current market-status disposition")
        if type(self.reason_code) is not str or not self.reason_code.strip():
            raise ValueError("reason_code must be a non-empty string")
        if self.evidence is not None:
            if not isinstance(self.evidence, Mapping):
                raise TypeError("evidence must be a mapping or None")
            object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))
        if (self.disposition == "verified_delisted") != (self.evidence is not None):
            raise ValueError("only verified delisted results carry evidence")


@dataclass(frozen=True, slots=True)
class _VerifiedPointer:
    reader: CurrentMarketStatusReader
    source_root: Path
    pointer_path: Path
    pointer_payload_json: str
    pointer_sha256: str
    run_id: str
    snapshot_path: Path
    snapshot_sha256: str
    manifest_path: Path
    manifest_sha256: str
    snapshot_observed_at: str
    snapshot_partial_failure: bool


def _aware_datetime(value: object) -> datetime | None:
    if type(value) is not str or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _canonical_date(value: object) -> date | None:
    if type(value) is not str or not value.strip():
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _is_sha256(value: object) -> bool:
    return type(value) is str and _SHA256_RE.fullmatch(value) is not None


def _is_reparse_or_symlink(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return True
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    attributes = int(getattr(info, "st_file_attributes", 0))
    return stat.S_ISLNK(info.st_mode) or bool(attributes & reparse_flag)


def _read_bound_file(path: Path, *, root: Path, max_bytes: int) -> bytes | None:
    """Read one immutable artifact with path, size and hash-race checks."""

    try:
        lexical_path = Path(path)
        lexical_root = Path(root)
        if not lexical_path.is_absolute() or not lexical_root.is_absolute():
            return None
        resolved_root = lexical_root.resolve(strict=True)
        current = Path(lexical_path.anchor)
        for component in lexical_path.parts[1:]:
            current = current / component
            if _is_reparse_or_symlink(current):
                return None
        resolved_path = lexical_path.resolve(strict=True)
        if not resolved_path.is_relative_to(resolved_root):
            return None
        before_path = resolved_path.stat()
        if not stat.S_ISREG(before_path.st_mode) or before_path.st_size < 0 or before_path.st_size > max_bytes:
            return None
        with resolved_path.open("rb") as stream:
            before_fd = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(before_fd.st_mode)
                or before_fd.st_size != before_path.st_size
                or before_fd.st_size > max_bytes
            ):
                return None
            data = stream.read(max_bytes + 1)
            after_fd = os.fstat(stream.fileno())
        after_path = resolved_path.stat()
        if len(data) > max_bytes:
            return None
        before_signature = (before_fd.st_size, before_fd.st_mtime_ns, before_fd.st_ino)
        after_fd_signature = (after_fd.st_size, after_fd.st_mtime_ns, after_fd.st_ino)
        after_path_signature = (after_path.st_size, after_path.st_mtime_ns, after_path.st_ino)
        if before_signature != after_fd_signature or before_signature != after_path_signature:
            return None
        if len(data) != after_fd.st_size:
            return None
        return data
    except (OSError, RuntimeError, ValueError):
        return None


def _decode_json_bytes(raw: bytes | None) -> Mapping[str, object] | None:
    if raw is None:
        return None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def _path_text(value: object) -> Path | None:
    if type(value) is not str or not value.strip():
        return None
    path = Path(value)
    return path if path.is_absolute() else None


def _verify_pinned_artifacts(value: Mapping[str, object], *, source_root: Path) -> bool:
    pointer_text = value.get("pointer_payload_json")
    if type(pointer_text) is not str or not pointer_text:
        return False
    try:
        pointer_bytes = pointer_text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    if len(pointer_bytes) > 1024 * 1024:
        return False
    if "sha256:" + hashlib.sha256(pointer_bytes).hexdigest() != value.get("pointer_sha256"):
        return False
    pointer = _decode_json_bytes(pointer_bytes)
    if pointer is None:
        return False
    run_id = value.get("run_id")
    if type(run_id) is not str or _RUN_ID_RE.fullmatch(run_id) is None:
        return False
    if (
        pointer.get("schema_version") != "current-market-status-pointer.v1"
        or pointer.get("scope") != "current_only"
        or pointer.get("pit_eligible") is not False
        or pointer.get("run_id") != run_id
        or pointer.get("snapshot_sha256") != value.get("snapshot_sha256")
        or pointer.get("manifest_sha256") != value.get("manifest_sha256")
    ):
        return False

    fixed_pointer = source_root / CURRENT_MARKET_STATUS_POINTER_RELATIVE
    recorded_pointer = _path_text(value.get("pointer_path"))
    if recorded_pointer is None or recorded_pointer != fixed_pointer:
        return False

    base = fixed_pointer.parent
    snapshot_rel = pointer.get("snapshot_path")
    manifest_rel = pointer.get("manifest_path")
    if type(snapshot_rel) is not str or type(manifest_rel) is not str:
        return False
    snapshot_rel_path = Path(snapshot_rel)
    manifest_rel_path = Path(manifest_rel)
    if snapshot_rel_path.is_absolute() or manifest_rel_path.is_absolute():
        return False
    if ".." in snapshot_rel_path.parts or ".." in manifest_rel_path.parts:
        return False
    expected_run_names = {run_id, f"cms_{run_id}"}
    if (
        snapshot_rel_path.name != "snapshot.json"
        or manifest_rel_path.name != "manifest.json"
        or snapshot_rel_path.parent != manifest_rel_path.parent
        or snapshot_rel_path.parent.as_posix() not in expected_run_names
    ):
        return False
    run_dir = base / snapshot_rel_path.parent
    snapshot_path = _path_text(value.get("snapshot_path"))
    manifest_path = _path_text(value.get("manifest_path"))
    if snapshot_path != run_dir / "snapshot.json" or manifest_path != run_dir / "manifest.json":
        return False

    snapshot_raw = _read_bound_file(snapshot_path, root=run_dir, max_bytes=_MAX_PINNED_JSON_BYTES)
    manifest_raw = _read_bound_file(manifest_path, root=run_dir, max_bytes=_MAX_PINNED_JSON_BYTES)
    raw_path = _path_text(value.get("raw_path"))
    if raw_path is None:
        return False
    raw_rel = raw_path.relative_to(run_dir) if raw_path.is_relative_to(run_dir) else None
    if (
        raw_rel is None
        or raw_rel.parent.as_posix() != "raw"
        or re.fullmatch(r"s[0-9]{4}\.bin", raw_rel.name) is None
    ):
        return False
    raw_bytes = _read_bound_file(raw_path, root=run_dir, max_bytes=_MAX_PINNED_RAW_BYTES)
    if snapshot_raw is None or manifest_raw is None or raw_bytes is None:
        return False
    if "sha256:" + hashlib.sha256(snapshot_raw).hexdigest() != value.get("snapshot_sha256"):
        return False
    if "sha256:" + hashlib.sha256(manifest_raw).hexdigest() != value.get("manifest_sha256"):
        return False
    if "sha256:" + hashlib.sha256(raw_bytes).hexdigest() != value.get("raw_sha256"):
        return False
    snapshot = _decode_json_bytes(snapshot_raw)
    manifest = _decode_json_bytes(manifest_raw)
    if snapshot is None or manifest is None:
        return False
    if (
        snapshot.get("schema_version") != "current-market-status-observation.v1"
        or snapshot.get("scope") != "current_only"
        or snapshot.get("pit_eligible") is not False
        or snapshot.get("run_id") != run_id
        or snapshot.get("observed_at") != value.get("snapshot_observed_at")
        or snapshot.get("partial_failure") is not value.get("snapshot_partial_failure")
        or manifest.get("schema_version") != "current-market-status-capture-manifest.v1"
        or manifest.get("run_id") != run_id
        or manifest.get("snapshot_path") != str(snapshot_path)
        or manifest.get("snapshot_sha256") != value.get("snapshot_sha256")
    ):
        return False

    symbol = value.get("symbol")
    securities = snapshot.get("securities")
    if not isinstance(securities, list):
        return False
    symbol_rows = [row for row in securities if isinstance(row, Mapping) and row.get("symbol") == symbol]
    if len(symbol_rows) != 1:
        return False
    security = symbol_rows[0]
    if (
        security.get("listing_status") != "delisted"
        or security.get("status_reason") != "explicit_official_termination_notice"
    ):
        return False
    status_evidence = security.get("evidence")
    if not isinstance(status_evidence, list):
        return False
    matching_evidence = [
        row for row in status_evidence
        if isinstance(row, Mapping)
        and row.get("evidence_type") == "terminated"
        and row.get("source_id") == value.get("source_id")
        and row.get("source_url") == value.get("source_url")
        and row.get("raw_sha256") == value.get("raw_sha256")
        and row.get("effective_from") == value.get("effective_date")
        and row.get("published_date") == value.get("published_date")
        and row.get("notice_reference") == value.get("notice_reference")
        and row.get("observed_at") == value.get("source_observed_at")
    ]
    if len(matching_evidence) != 1:
        return False

    captures = snapshot.get("source_captures")
    manifest_sources = manifest.get("raw_sources")
    if not isinstance(captures, list) or not isinstance(manifest_sources, list):
        return False
    capture_rows = [
        row for row in captures
        if isinstance(row, Mapping)
        and row.get("source_id") == value.get("source_id")
        and row.get("final_url") == value.get("source_url")
        and row.get("raw_path") == str(raw_path)
        and row.get("raw_sha256") == value.get("raw_sha256")
        and type(row.get("raw_bytes")) is int
        and row.get("raw_bytes") == len(raw_bytes)
        and row.get("captured_at") == value.get("source_captured_at")
        and row.get("status") == "captured"
        and row.get("parse_status") == "parsed"
        and type(row.get("http_status")) is int
        and row.get("http_status") == 200
    ]
    manifest_rows = [
        row for row in manifest_sources
        if isinstance(row, Mapping)
        and row.get("source_id") == value.get("source_id")
        and row.get("raw_path") == str(raw_path)
        and row.get("raw_sha256") == value.get("raw_sha256")
        and row.get("captured_at") == value.get("source_captured_at")
        and row.get("status") == "captured"
        and row.get("parse_status") == "parsed"
    ]
    return len(capture_rows) == 1 and len(manifest_rows) == 1


def _official_source(source_id: object, source_url: object) -> bool:
    if type(source_id) is not str or type(source_url) is not str:
        return False
    market = source_id.partition(".")[0]
    if market not in _OFFICIAL_HOSTS or not source_id.startswith(f"{market}."):
        return False
    try:
        parsed = urlsplit(source_url)
        return (
            parsed.scheme == "https"
            and parsed.hostname in _OFFICIAL_HOSTS[market]
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


def validate_current_market_status_evidence(
    value: object,
    *,
    expected_symbol: str | None = None,
    decision_at: datetime | None = None,
) -> bool:
    """Validate the persisted typed evidence without reading a newer pointer.

    The caller must already hold the matching immutable recommendation
    execution.  This validator proves shape, official source identity, hashes,
    effective/published dates, current-only scope and the same aware decision
    clock; it never upgrades the observation to historical/PIT evidence.
    """

    if not isinstance(value, Mapping):
        return False
    required_strings = (
        "schema_version",
        "symbol",
        "listing_status",
        "status_reason",
        "evidence_type",
        "source_id",
        "source_url",
        "raw_sha256",
        "effective_date",
        "source_observed_at",
        "source_captured_at",
        "snapshot_observed_at",
        "decision_at",
        "decision_date",
        "source_root",
        "pointer_path",
        "pointer_payload_json",
        "pointer_sha256",
        "run_id",
        "snapshot_path",
        "snapshot_sha256",
        "manifest_path",
        "manifest_sha256",
        "raw_path",
        "capture_status",
        "capture_parse_status",
    )
    if any(type(value.get(name)) is not str or not str(value.get(name)).strip() for name in required_strings):
        return False
    if value.get("schema_version") != CURRENT_MARKET_STATUS_EVIDENCE_SCHEMA:
        return False
    if (
        value.get("listing_status") != "delisted"
        or value.get("status_reason") != "explicit_official_termination_notice"
        or value.get("evidence_type") != "terminated"
        or value.get("scope") != "current_only"
        or value.get("pit_eligible") is not False
        or value.get("capture_status") != "captured"
        or value.get("capture_parse_status") != "parsed"
        or type(value.get("source_http_status")) is not int
        or value.get("source_http_status") != 200
    ):
        return False
    symbol = value.get("symbol")
    if expected_symbol is not None and (type(expected_symbol) is not str or symbol != expected_symbol):
        return False
    if not _is_sha256(value.get("raw_sha256")) or not all(
        _is_sha256(value.get(name))
        for name in ("pointer_sha256", "snapshot_sha256", "manifest_sha256")
    ):
        return False
    if not _official_source(value.get("source_id"), value.get("source_url")):
        return False

    effective_date = _canonical_date(value.get("effective_date"))
    decision_date = _canonical_date(value.get("decision_date"))
    published_value = value.get("published_date")
    if published_value is not None and type(published_value) is not str:
        return False
    published_date = _canonical_date(published_value) if published_value is not None else None
    if effective_date is None or decision_date is None:
        return False
    if published_value is not None and published_date is None:
        return False
    if effective_date > decision_date or (published_date is not None and published_date > decision_date):
        return False
    notice_reference = value.get("notice_reference")
    if notice_reference is not None and type(notice_reference) is not str:
        return False

    source_observed = _aware_datetime(value.get("source_observed_at"))
    source_captured = _aware_datetime(value.get("source_captured_at"))
    snapshot_observed = _aware_datetime(value.get("snapshot_observed_at"))
    recorded_decision = _aware_datetime(value.get("decision_at"))
    if any(item is None for item in (source_observed, source_captured, snapshot_observed, recorded_decision)):
        return False
    assert source_observed is not None
    assert source_captured is not None
    assert snapshot_observed is not None
    assert recorded_decision is not None
    if source_observed != source_captured or not source_observed <= snapshot_observed <= recorded_decision:
        return False
    if recorded_decision.astimezone(_TAIPEI).date() != decision_date:
        return False
    if decision_at is not None:
        if (
            type(decision_at) is not datetime
            or decision_at.tzinfo is None
            or decision_at.utcoffset() is None
            or decision_at.astimezone(timezone.utc) != recorded_decision
        ):
            return False

    source_root = Path(str(value.get("source_root")))
    pointer_path = Path(str(value.get("pointer_path")))
    if not source_root.is_absolute() or not pointer_path.is_absolute():
        return False
    expected_pointer = source_root / CURRENT_MARKET_STATUS_POINTER_RELATIVE
    try:
        if pointer_path.resolve(strict=False) != expected_pointer.resolve(strict=False):
            return False
    except OSError:
        return False
    if type(value.get("snapshot_partial_failure")) is not bool:
        return False
    try:
        return _verify_pinned_artifacts(value, source_root=source_root)
    except (OSError, RuntimeError, TypeError, ValueError, UnicodeError):
        return False


class CurrentMarketStatusPreflight:
    """Invocation-local reader for one fixed current-status pointer."""

    def __init__(self, source_root: Path) -> None:
        if not isinstance(source_root, Path):
            raise TypeError("source_root must be a Path")
        self._source_root = source_root.expanduser().resolve()
        self._pointer: _VerifiedPointer | None = None
        self._pointer_error: str | None = None
        self._results: dict[tuple[str, str, str], CurrentMarketStatusPreflightResult] = {}

    def get(
        self,
        symbol: str,
        *,
        cutoff_at: datetime,
        decision_date: date,
    ) -> CurrentMarketStatusPreflightResult:
        if type(symbol) is not str or not re.fullmatch(r"\d{4,6}", symbol):
            return CurrentMarketStatusPreflightResult(
                str(symbol), "unavailable", "current_market_status_symbol_invalid"
            )
        if (
            type(cutoff_at) is not datetime
            or cutoff_at.tzinfo is None
            or cutoff_at.utcoffset() is None
            or type(decision_date) is not date
        ):
            return CurrentMarketStatusPreflightResult(
                symbol, "unavailable", "current_market_status_decision_clock_invalid"
            )
        cutoff_utc = cutoff_at.astimezone(timezone.utc)
        taipei_date = cutoff_utc.astimezone(_TAIPEI).date()
        if taipei_date != decision_date:
            return CurrentMarketStatusPreflightResult(
                symbol, "unavailable", "current_market_status_decision_date_mismatch"
            )
        key = (symbol, cutoff_utc.isoformat(), decision_date.isoformat())
        cached = self._results.get(key)
        if cached is not None:
            return cached

        pointer = self._load_pointer()
        if pointer is None:
            result = CurrentMarketStatusPreflightResult(
                symbol,
                "unavailable",
                self._pointer_error or "current_market_status_pointer_unavailable",
            )
            self._results[key] = result
            return result
        snapshot_observed = _aware_datetime(pointer.snapshot_observed_at)
        if snapshot_observed is None or snapshot_observed > cutoff_utc:
            result = CurrentMarketStatusPreflightResult(
                symbol, "unavailable", "current_market_status_snapshot_after_decision"
            )
            self._results[key] = result
            return result

        try:
            observation = pointer.reader.get(symbol)
        except (CurrentMarketStatusError, TypeError, ValueError) as exc:
            result = CurrentMarketStatusPreflightResult(
                symbol, "unavailable", f"current_market_status_read_failed:{type(exc).__name__}"
            )
            self._results[key] = result
            return result
        if observation.symbol != symbol or observation.scope != "current_only" or observation.pit_eligible is not False:
            result = CurrentMarketStatusPreflightResult(
                symbol, "unavailable", "current_market_status_scope_or_symbol_invalid"
            )
            self._results[key] = result
            return result
        if observation.listing_status != "delisted":
            disposition: Literal["not_delisted", "unavailable"]
            if observation.listing_status in {"listed", "suspended"}:
                disposition = "not_delisted"
                reason = "current_market_status_not_delisted"
            else:
                disposition = "unavailable"
                reason = "current_market_status_unknown_or_conflicted"
            result = CurrentMarketStatusPreflightResult(symbol, disposition, reason)
            self._results[key] = result
            return result

        evidence_rows = tuple(
            row
            for row in observation.status_evidence
            if isinstance(row, Mapping)
            and row.get("symbol") == symbol
            and row.get("evidence_type") == "terminated"
        )
        validated: list[dict[str, object]] = []
        captures = pointer.reader._payload.get("source_captures")
        if not isinstance(captures, list):
            result = CurrentMarketStatusPreflightResult(
                symbol, "unavailable", "current_market_status_capture_list_invalid"
            )
            self._results[key] = result
            return result
        for evidence_row in evidence_rows:
            if not self._effective_termination(evidence_row, cutoff_utc, decision_date):
                continue
            source_id = evidence_row.get("source_id")
            source_url = evidence_row.get("source_url")
            source_observed_at = evidence_row.get("observed_at")
            raw_sha256 = evidence_row.get("raw_sha256")
            if not _official_source(source_id, source_url) or not _is_sha256(raw_sha256):
                continue
            matches = [
                item
                for item in captures
                if isinstance(item, Mapping)
                and item.get("source_id") == source_id
                and item.get("final_url") == source_url
                and item.get("raw_sha256") == raw_sha256
                and item.get("captured_at") == source_observed_at
            ]
            if len(matches) != 1:
                continue
            capture = matches[0]
            if (
                capture.get("status") != "captured"
                or capture.get("parse_status") != "parsed"
                or type(capture.get("http_status")) is not int
                or capture.get("http_status") != 200
            ):
                continue
            source_capture_time = _aware_datetime(capture.get("captured_at"))
            source_evidence_time = _aware_datetime(source_observed_at)
            if (
                source_capture_time is None
                or source_evidence_time is None
                or source_capture_time > cutoff_utc
                or source_evidence_time > cutoff_utc
            ):
                continue
            evidence = {
                "schema_version": CURRENT_MARKET_STATUS_EVIDENCE_SCHEMA,
                "symbol": symbol,
                "listing_status": observation.listing_status,
                "status_reason": observation.status_reason,
                "evidence_type": "terminated",
                "source_id": source_id,
                "source_url": source_url,
                "raw_sha256": raw_sha256,
                "effective_date": evidence_row.get("effective_from"),
                "published_date": evidence_row.get("published_date"),
                "notice_reference": evidence_row.get("notice_reference"),
                "source_observed_at": source_observed_at,
                "source_captured_at": capture.get("captured_at"),
                "snapshot_observed_at": pointer.snapshot_observed_at,
                "decision_at": cutoff_utc.isoformat(timespec="microseconds"),
                "decision_date": decision_date.isoformat(),
                "source_root": str(pointer.source_root),
                "pointer_path": str(pointer.pointer_path),
                "pointer_payload_json": pointer.pointer_payload_json,
                "pointer_sha256": pointer.pointer_sha256,
                "run_id": pointer.run_id,
                "snapshot_path": str(pointer.snapshot_path),
                "snapshot_sha256": pointer.snapshot_sha256,
                "manifest_path": str(pointer.manifest_path),
                "manifest_sha256": pointer.manifest_sha256,
                "raw_path": str(capture.get("raw_path")),
                "scope": "current_only",
                "pit_eligible": False,
                "snapshot_partial_failure": pointer.snapshot_partial_failure,
                "capture_status": capture.get("status"),
                "capture_parse_status": capture.get("parse_status"),
                "source_http_status": capture.get("http_status"),
            }
            if validate_current_market_status_evidence(
                evidence, expected_symbol=symbol, decision_at=cutoff_utc
            ):
                validated.append(evidence)

        if len(validated) != 1 or observation.status_reason != "explicit_official_termination_notice":
            result = CurrentMarketStatusPreflightResult(
                symbol, "unavailable", "current_market_status_termination_evidence_unverified"
            )
        else:
            result = CurrentMarketStatusPreflightResult(
                symbol,
                "verified_delisted",
                "official_delisted",
                validated[0],
            )
        self._results[key] = result
        return result

    def _load_pointer(self) -> _VerifiedPointer | None:
        if self._pointer is not None:
            return self._pointer
        if self._pointer_error is not None:
            return None
        pointer_path = self._source_root / CURRENT_MARKET_STATUS_POINTER_RELATIVE
        try:
            if pointer_path.is_symlink() or not pointer_path.is_file():
                raise CurrentMarketStatusError("fixed_pointer_missing_or_symlink")
            if pointer_path.stat().st_size > 1024 * 1024:
                raise CurrentMarketStatusError("fixed_pointer_exceeds_size_limit")
            raw_before = pointer_path.read_bytes()
            if len(raw_before) > 1024 * 1024:
                raise CurrentMarketStatusError("fixed_pointer_exceeds_size_limit")
            pointer_payload = json.loads(raw_before.decode("utf-8"))
            if not isinstance(pointer_payload, Mapping):
                raise CurrentMarketStatusError("pointer_payload_not_object")
            reader = CurrentMarketStatusReader.from_pointer(pointer_path)
            raw_after = pointer_path.read_bytes()
            if len(raw_after) > 1024 * 1024:
                raise CurrentMarketStatusError("fixed_pointer_exceeds_size_limit")
            pointer_hash = "sha256:" + hashlib.sha256(raw_before).hexdigest()
            if raw_before != raw_after:
                raise CurrentMarketStatusError("pointer_changed_during_read")
            snapshot_sha = pointer_payload.get("snapshot_sha256")
            manifest_sha = pointer_payload.get("manifest_sha256")
            run_id = pointer_payload.get("run_id")
            if not _is_sha256(snapshot_sha) or not _is_sha256(manifest_sha):
                raise CurrentMarketStatusError("pointer_identity_invalid")
            if type(run_id) is not str or _RUN_ID_RE.fullmatch(run_id) is None:
                raise CurrentMarketStatusError("pointer_identity_invalid")
            snapshot_sha = cast(str, snapshot_sha)
            manifest_sha = cast(str, manifest_sha)
            run_id = cast(str, run_id)
            snapshot_rel = pointer_payload.get("snapshot_path")
            manifest_rel = pointer_payload.get("manifest_path")
            if type(snapshot_rel) is not str or type(manifest_rel) is not str:
                raise CurrentMarketStatusError("pointer_paths_invalid")
            snapshot_rel_path = Path(snapshot_rel)
            manifest_rel_path = Path(manifest_rel)
            expected_run_names = {run_id, f"cms_{run_id}"}
            if (
                snapshot_rel_path.is_absolute()
                or manifest_rel_path.is_absolute()
                or ".." in snapshot_rel_path.parts
                or ".." in manifest_rel_path.parts
                or snapshot_rel_path.name != "snapshot.json"
                or manifest_rel_path.name != "manifest.json"
                or snapshot_rel_path.parent != manifest_rel_path.parent
                or snapshot_rel_path.parent.as_posix() not in expected_run_names
            ):
                raise CurrentMarketStatusError("pointer_paths_invalid")
            run_dir = pointer_path.parent / snapshot_rel_path.parent
            snapshot_path = (pointer_path.parent / snapshot_rel_path).resolve(strict=True)
            manifest_path = (pointer_path.parent / manifest_rel_path).resolve(strict=True)
            if snapshot_path.parent != run_dir.resolve(strict=True) or manifest_path.parent != run_dir.resolve(strict=True):
                raise CurrentMarketStatusError("pointer_paths_escape_run")
            snapshot_observed = reader._payload.get("observed_at")
            if type(snapshot_observed) is not str or not snapshot_observed.strip():
                raise CurrentMarketStatusError("snapshot_observed_at_missing")
            partial_failure = reader._payload.get("partial_failure", False)
            if type(partial_failure) is not bool:
                raise CurrentMarketStatusError("snapshot_partial_failure_invalid")
            self._pointer = _VerifiedPointer(
                reader=reader,
                source_root=self._source_root,
                pointer_path=pointer_path,
                pointer_payload_json=raw_before.decode("utf-8"),
                pointer_sha256=pointer_hash,
                run_id=run_id,
                snapshot_path=snapshot_path,
                snapshot_sha256=snapshot_sha,
                manifest_path=manifest_path,
                manifest_sha256=manifest_sha,
                snapshot_observed_at=snapshot_observed,
                snapshot_partial_failure=partial_failure,
            )
            return self._pointer
        except (OSError, UnicodeError, json.JSONDecodeError, CurrentMarketStatusError, TypeError, ValueError) as exc:
            self._pointer_error = f"current_market_status_pointer_invalid:{type(exc).__name__}"
            return None

    @staticmethod
    def _effective_termination(
        evidence: Mapping[str, object], cutoff_utc: datetime, decision_date: date
    ) -> bool:
        if evidence.get("evidence_type") != "terminated":
            return False
        effective = _canonical_date(evidence.get("effective_from"))
        if effective is None or effective > decision_date:
            return False
        published_value = evidence.get("published_date")
        if published_value is not None:
            published = _canonical_date(published_value)
            if published is None or published > decision_date:
                return False
        observed = _aware_datetime(evidence.get("observed_at"))
        return observed is not None and observed <= cutoff_utc


__all__ = [
    "CURRENT_MARKET_STATUS_EVIDENCE_SCHEMA",
    "CURRENT_MARKET_STATUS_POINTER_RELATIVE",
    "CurrentMarketStatusPreflight",
    "CurrentMarketStatusPreflightResult",
    "validate_current_market_status_evidence",
]
