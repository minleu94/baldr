"""Bind a successful daily source-row projection to the existing research B adapter.

This child stays inside the repository's approved ``output/ml_research`` tree.
It consumes exact path/hash pins from one raw-run projection receipt and creates
an immutable Direct-numeric research store. It never writes a formal database,
model registry, prediction, or outcome record.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any, Callable, Mapping

from data_module.ml_research_output_boundary import (
    get_ml_research_root,
    resolve_ml_research_output_path,
)
from data_module.ml_daily_source_row_research_projection import (
    MAX_PROJECTION_BYTES,
    MAX_PROJECTION_ROW_BYTES,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECTION_ROOT_RELATIVE = Path("daily_source_row_projections")
DEFAULT_RESEARCH_OUTPUT_ROOT = REPO_ROOT / "output" / "ml_research"
ADAPTER_SCRIPT = REPO_ROOT / "scripts" / "adapt_ml_research_direct_ooc.py"
ADAPTER_TIMEOUT_SECONDS = 900
MAX_RECEIPT_BYTES = 8 * 1024 * 1024
MAX_PROCESS_OUTPUT_BYTES = 2 * 1024 * 1024
RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}\Z")
SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")


class DailySourceRowResearchAdapterError(ValueError):
    """A source projection cannot be safely adapted or consumed."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_sha256(payload: object) -> str:
    return _sha256(_canonical_json_bytes(payload))


def _without_hash(payload: Mapping[str, Any], field: str) -> dict[str, Any]:
    body = dict(payload)
    body.pop(field, None)
    return body


def _aware_utc(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise DailySourceRowResearchAdapterError(f"{field} is missing")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise DailySourceRowResearchAdapterError(f"{field} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DailySourceRowResearchAdapterError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _strict_sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DailySourceRowResearchAdapterError(f"{field} is missing")
    normalized = value.strip().lower()
    if not normalized.startswith("sha256:"):
        normalized = "sha256:" + normalized
    if not SHA256_PATTERN.fullmatch(normalized):
        raise DailySourceRowResearchAdapterError(f"{field} is not a SHA-256 pin")
    return normalized


def _reject_reparse_aliases(path: Path) -> None:
    absolute = Path(os.path.abspath(str(path)))
    current = Path(absolute.anchor)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

    for component in absolute.parts[1:]:
        current = current / component
        try:
            details = current.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise DailySourceRowResearchAdapterError(
                f"cannot inspect path component: {current}"
            ) from exc
        is_junction = getattr(current, "is_junction", None)
        if (
            stat.S_ISLNK(details.st_mode)
            or bool(getattr(details, "st_file_attributes", 0) & reparse_flag)
            or (callable(is_junction) and is_junction())
        ):
            raise DailySourceRowResearchAdapterError(
                f"path cannot traverse a symlink or junction: {current}"
            )


def _read_pinned_json(
    path: Path,
    *,
    root: Path,
    expected_sha256: object,
    label: str,
) -> tuple[dict[str, Any], bytes]:
    absolute = Path(os.path.abspath(str(path)))
    allowed_root = Path(os.path.abspath(str(root)))
    _reject_reparse_aliases(absolute)
    try:
        absolute.relative_to(allowed_root)
    except ValueError as exc:
        raise DailySourceRowResearchAdapterError(f"{label} is outside its pinned root") from exc
    if not absolute.is_file():
        raise DailySourceRowResearchAdapterError(f"{label} is not a regular file")
    data = absolute.read_bytes()
    if len(data) > MAX_RECEIPT_BYTES:
        raise DailySourceRowResearchAdapterError(f"{label} exceeds the receipt byte bound")
    if _sha256(data) != _strict_sha256(expected_sha256, f"{label}.sha256"):
        raise DailySourceRowResearchAdapterError(f"{label} bytes differ from the pinned SHA-256")
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DailySourceRowResearchAdapterError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise DailySourceRowResearchAdapterError(f"{label} JSON root must be an object")
    return payload, data


def _verify_file_pin(
    path: Path,
    *,
    root: Path,
    expected_sha256: str,
    expected_bytes: int,
    label: str,
) -> int:
    absolute = Path(os.path.abspath(str(path)))
    allowed_root = Path(os.path.abspath(str(root))).resolve(strict=True)
    _reject_reparse_aliases(absolute)
    try:
        actual = absolute.resolve(strict=True)
        actual.relative_to(allowed_root)
    except (OSError, ValueError) as exc:
        raise DailySourceRowResearchAdapterError(
            f"{label} is missing or outside its pinned root"
        ) from exc
    if not actual.is_file() or type(expected_bytes) is not int:
        raise DailySourceRowResearchAdapterError(f"{label} is not a regular pinned file")
    if expected_bytes < 0 or expected_bytes > MAX_PROJECTION_BYTES:
        raise DailySourceRowResearchAdapterError(f"{label} exceeds the projection byte bound")
    if actual.stat().st_size != expected_bytes:
        raise DailySourceRowResearchAdapterError(f"{label} size differs from its pin")
    digest = hashlib.sha256()
    observed_bytes = 0
    with actual.open("rb") as stream:
        while True:
            chunk = stream.read(1 << 20)
            if not chunk:
                break
            observed_bytes += len(chunk)
            if observed_bytes > expected_bytes:
                raise DailySourceRowResearchAdapterError(f"{label} grew beyond its pinned size")
            digest.update(chunk)
    if observed_bytes != expected_bytes or "sha256:" + digest.hexdigest() != expected_sha256:
        raise DailySourceRowResearchAdapterError(f"{label} bytes differ from their pin")
    return observed_bytes


def _validate_projection(
    projection_status: Mapping[str, Any],
    *,
    source_date: str,
    repository_root: Path,
    now: datetime,
) -> dict[str, Any]:
    if projection_status.get("status") != "projected_research_only":
        raise DailySourceRowResearchAdapterError("daily source-row projection is not complete")
    if projection_status.get("terminal_receipt_readback_verified") is not True:
        raise DailySourceRowResearchAdapterError("projection terminal receipt was not readback-verified")
    for key in (
        "formal_credit",
        "historical_pit_eligible",
        "formal_source_contract_eligible",
        "formal_oos_allowed",
        "features_included",
        "labels_included",
        "model_use_claimed",
    ):
        if projection_status.get(key) is not False:
            raise DailySourceRowResearchAdapterError(
                f"projection carries an unsafe eligibility flag: {key}"
            )

    try:
        normalized_date = date.fromisoformat(source_date).isoformat()
    except ValueError as exc:
        raise DailySourceRowResearchAdapterError("source_date is invalid") from exc
    if normalized_date != source_date or projection_status.get("source_date") != normalized_date:
        raise DailySourceRowResearchAdapterError("projection source date differs from raw run")
    projection_id = projection_status.get("projection_id")
    if not isinstance(projection_id, str) or not re.fullmatch(r"[0-9a-f]{64}", projection_id):
        raise DailySourceRowResearchAdapterError("projection_id is invalid")

    repo = Path(os.path.abspath(str(repository_root))).resolve(strict=True)
    active_research_root = get_ml_research_root(repository_root=repo)
    allowed_projection_root = resolve_ml_research_output_path(
        active_research_root / PROJECTION_ROOT_RELATIVE,
        repository_root=repo,
        access="read",
    )
    candidate_root_value = projection_status.get("projection_candidate_root")
    if not isinstance(candidate_root_value, str) or not candidate_root_value.strip():
        raise DailySourceRowResearchAdapterError("projection candidate root is missing")
    candidate_root = resolve_ml_research_output_path(
        Path(candidate_root_value), repository_root=repo, access="read"
    )
    _reject_reparse_aliases(candidate_root)
    try:
        candidate_root.relative_to(allowed_projection_root)
    except ValueError as exc:
        raise DailySourceRowResearchAdapterError(
            "projection candidate root is outside the dedicated research projection root"
        ) from exc
    if (
        candidate_root.name != projection_id
        or candidate_root.parent.name != normalized_date
    ):
        raise DailySourceRowResearchAdapterError("projection path/date/id identity differs")

    manifest_path = Path(str(projection_status.get("projection_manifest_path") or ""))
    observations_path = Path(str(projection_status.get("projection_observations_path") or ""))
    completion_path = Path(
        str(projection_status.get("projection_intermediate_completion_receipt_path") or "")
    )
    terminal_path = Path(str(projection_status.get("terminal_receipt_path") or ""))
    expected_paths = {
        "manifest": (manifest_path, candidate_root / "manifest.json"),
        "observations": (observations_path, candidate_root / "observations.jsonl"),
        "completion": (completion_path, candidate_root / "completion_receipt.json"),
        "terminal": (
            terminal_path,
            candidate_root / "runner_terminal_verification_receipt.json",
        ),
    }
    for label, (actual_path, expected_path) in expected_paths.items():
        if Path(os.path.abspath(str(actual_path))) != Path(os.path.abspath(str(expected_path))):
            raise DailySourceRowResearchAdapterError(f"projection {label} path drifted")

    manifest_sha = _strict_sha256(
        projection_status.get("projection_manifest_sha256"), "projection_manifest_sha256"
    )
    observations_sha = _strict_sha256(
        projection_status.get("projection_observations_sha256"),
        "projection_observations_sha256",
    )
    completion_sha = _strict_sha256(
        projection_status.get("projection_intermediate_completion_receipt_sha256"),
        "projection_intermediate_completion_receipt_sha256",
    )
    terminal_sha = _strict_sha256(
        projection_status.get("terminal_receipt_sha256"), "terminal_receipt_sha256"
    )
    manifest, manifest_bytes = _read_pinned_json(
        manifest_path,
        root=candidate_root,
        expected_sha256=manifest_sha,
        label="projection manifest",
    )
    if manifest.get("schema_version") != "ml-daily-source-row-research-projection.v1":
        raise DailySourceRowResearchAdapterError("projection manifest schema is unsupported")
    if manifest.get("projection_id") != projection_id or manifest.get("source_date") != normalized_date:
        raise DailySourceRowResearchAdapterError("projection manifest identity differs")
    if manifest.get("content_sha256") != _canonical_sha256(
        _without_hash(manifest, "content_sha256")
    ):
        raise DailySourceRowResearchAdapterError("projection manifest canonical hash mismatch")
    input_file_pins = manifest.get("input_files")
    if not isinstance(input_file_pins, Mapping) or not input_file_pins:
        raise DailySourceRowResearchAdapterError("projection input file pins are missing")
    verified_input_pins: list[dict[str, Any]] = []
    for relative, pin in sorted(input_file_pins.items()):
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or not isinstance(pin, Mapping)
        ):
            raise DailySourceRowResearchAdapterError("projection input file pin is invalid")
        input_path = candidate_root / Path(relative)
        expected_input_sha = _strict_sha256(
            pin.get("sha256"), f"projection.input_files.{relative}.sha256"
        )
        input_size = pin.get("bytes")
        if type(input_size) is not int:
            raise DailySourceRowResearchAdapterError(
                f"projection input file size is invalid: {relative}"
            )
        verified_input_bytes = _verify_file_pin(
            input_path,
            root=candidate_root,
            expected_sha256=expected_input_sha,
            expected_bytes=input_size,
            label=f"projection input file {relative}",
        )
        verified_input_pins.append(
            {
                "relative_path": relative,
                "path": str(input_path.resolve(strict=True)),
                "sha256": expected_input_sha,
                "bytes": verified_input_bytes,
            }
        )
    observations_meta = manifest.get("observations_file")
    if not isinstance(observations_meta, Mapping):
        raise DailySourceRowResearchAdapterError("projection observations pin is missing")
    if observations_meta.get("path") != "observations.jsonl":
        raise DailySourceRowResearchAdapterError("projection observations path is invalid")
    if _strict_sha256(observations_meta.get("sha256"), "manifest.observations_file.sha256") != observations_sha:
        raise DailySourceRowResearchAdapterError("projection observations pin differs")
    if type(observations_meta.get("bytes")) is not int or type(observations_meta.get("row_count")) is not int:
        raise DailySourceRowResearchAdapterError("projection observations sizes are invalid")
    if observations_meta["row_count"] < 1 or observations_meta["bytes"] < 1:
        raise DailySourceRowResearchAdapterError("projection observations are empty")
    if observations_meta["bytes"] > MAX_PROJECTION_BYTES:
        raise DailySourceRowResearchAdapterError(
            "projection observations exceed the configured projection byte bound"
        )
    if projection_status.get("projected_row_count") != observations_meta["row_count"]:
        raise DailySourceRowResearchAdapterError("projection row count differs from terminal pins")
    observations_absolute = Path(os.path.abspath(str(observations_path)))
    _reject_reparse_aliases(observations_absolute)
    try:
        observations_absolute.resolve(strict=True).relative_to(candidate_root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise DailySourceRowResearchAdapterError(
            "projection observations escaped candidate root"
        ) from exc
    observation_digest = hashlib.sha256()
    observation_byte_count = 0
    observation_count = 0
    symbol_values: set[str] = set()
    source_available_at_values: list[datetime] = []
    with observations_absolute.open("rb") as stream:
        while True:
            line = stream.readline(MAX_PROJECTION_ROW_BYTES + 1)
            if not line:
                break
            if len(line) > MAX_PROJECTION_ROW_BYTES:
                raise DailySourceRowResearchAdapterError(
                    "projection observation exceeds the configured row byte bound"
                )
            observation_byte_count += len(line)
            if observation_byte_count > observations_meta["bytes"]:
                raise DailySourceRowResearchAdapterError(
                    "projection observations grew beyond their pinned size"
                )
            observation_digest.update(line)
            try:
                row = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise DailySourceRowResearchAdapterError(
                    "projection observations JSONL is invalid"
                ) from exc
            if not isinstance(row, dict):
                raise DailySourceRowResearchAdapterError(
                    "projection observation must be an object"
                )
            symbol = row.get("symbol")
            if not isinstance(symbol, str) or not re.fullmatch(r"\d{4}", symbol):
                raise DailySourceRowResearchAdapterError("projection symbol is invalid")
            if row.get("source_date") != normalized_date:
                raise DailySourceRowResearchAdapterError("projection event date differs")
            symbol_values.add(symbol)
            source_available_at_values.append(
                _aware_utc(row.get("source_available_at"), "observation.source_available_at")
            )
            observation_count += 1
    if (
        observation_byte_count != observations_meta["bytes"]
        or "sha256:" + observation_digest.hexdigest() != observations_sha
        or observation_count != observations_meta["row_count"]
    ):
        raise DailySourceRowResearchAdapterError("projection observations bytes or count differ from pins")

    completion, _ = _read_pinned_json(
        completion_path,
        root=candidate_root,
        expected_sha256=completion_sha,
        label="projection intermediate completion receipt",
    )
    if (
        completion.get("schema_version") != "ml-daily-source-row-research-completion.v1"
        or completion.get("projection_id") != projection_id
        or completion.get("manifest_sha256") != manifest_sha
        or completion.get("observations_sha256") != observations_sha
        or completion.get("completion_status") != "awaiting_terminal_revision_validation"
        or completion.get("formal_credit") is not False
    ):
        raise DailySourceRowResearchAdapterError("projection intermediate receipt binding differs")
    if completion.get("content_sha256") != _canonical_sha256(
        _without_hash(completion, "content_sha256")
    ):
        raise DailySourceRowResearchAdapterError("projection completion receipt hash mismatch")

    terminal, _ = _read_pinned_json(
        terminal_path,
        root=candidate_root,
        expected_sha256=terminal_sha,
        label="projection runner terminal receipt",
    )
    terminal_projection = terminal.get("projection")
    if not isinstance(terminal_projection, Mapping):
        raise DailySourceRowResearchAdapterError("projection terminal details are missing")
    if (
        terminal.get("schema_version") != "ml-daily-source-row-runner-terminal-receipt.v1"
        or terminal.get("terminal_status") != "completed_research_only"
        or terminal.get("source_date") != normalized_date
        or terminal_projection.get("projection_id") != projection_id
        or terminal_projection.get("manifest_sha256") != manifest_sha
        or terminal_projection.get("observations_sha256") != observations_sha
        or terminal.get("formal_credit") is not False
        or terminal.get("historical_pit_eligible") is not False
        or terminal.get("formal_oos_allowed") is not False
    ):
        raise DailySourceRowResearchAdapterError("projection terminal receipt binding differs")
    if terminal.get("content_sha256") != _canonical_sha256(
        _without_hash(terminal, "content_sha256")
    ):
        raise DailySourceRowResearchAdapterError("projection terminal receipt canonical hash mismatch")
    training_as_of = _aware_utc(
        terminal_projection.get("verification_completed_at"),
        "projection.verification_completed_at",
    )
    now_utc = now.astimezone(timezone.utc)
    if training_as_of > now_utc:
        raise DailySourceRowResearchAdapterError("projection verification time is in the future")

    if not symbol_values or not source_available_at_values:
        raise DailySourceRowResearchAdapterError("projection has no verifiable symbols or availability")
    if any(available_at > training_as_of for available_at in source_available_at_values):
        raise DailySourceRowResearchAdapterError(
            "projection contains source availability later than its verified freeze"
        )

    return {
        "source_date": normalized_date,
        "projection_id": projection_id,
        "candidate_root": candidate_root,
        "manifest_path": manifest_path.resolve(strict=True),
        "manifest_sha256": manifest_sha,
        "manifest_bytes_sha256": _sha256(manifest_bytes),
        "observations_path": observations_path.resolve(strict=True),
        "observations_sha256": observations_sha,
        "observations_bytes": observation_byte_count,
        "row_count": observations_meta["row_count"],
        "terminal_path": terminal_path.resolve(strict=True),
        "terminal_sha256": terminal_sha,
        "completion_path": completion_path.resolve(strict=True),
        "completion_sha256": completion_sha,
        "training_as_of": training_as_of.isoformat(),
        "symbols": sorted(symbol_values),
        "source_available_at_min": min(source_available_at_values).isoformat(),
        "source_available_at_max": max(source_available_at_values).isoformat(),
        "verified_input_file_pins": verified_input_pins,
    }


def _write_create_only(
    path: Path, payload: Mapping[str, Any], *, repository_root: Path
) -> str:
    resolve_ml_research_output_path(
        path.parent, repository_root=repository_root, access="write"
    )
    raw = _canonical_json_bytes(payload)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    readback = path.read_bytes()
    if readback != raw:
        raise DailySourceRowResearchAdapterError(f"create-only receipt readback differs: {path}")
    return _sha256(readback)


def _parse_object(raw: bytes, label: str) -> dict[str, Any]:
    if len(raw) > MAX_PROCESS_OUTPUT_BYTES:
        raise DailySourceRowResearchAdapterError(f"adapter {label} exceeds output byte limit")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DailySourceRowResearchAdapterError(f"adapter {label} is not a JSON object") from exc
    if not isinstance(value, dict):
        raise DailySourceRowResearchAdapterError(f"adapter {label} JSON root must be an object")
    return value


def _verify_adapter_outputs(
    payload: Mapping[str, Any],
    *,
    projection: Mapping[str, Any],
    run_root: Path,
) -> dict[str, Any]:
    if (
        payload.get("status") != "verified_numeric_observations_ready"
        or payload.get("direct_ooc_status") != "blocked_insufficient_context_or_mature_history"
        or payload.get("formal_oos_allowed") is not False
        or payload.get("production_alpha_bp") != 0
        or payload.get("formal_release_v4_pointer_untouched") is not True
    ):
        raise DailySourceRowResearchAdapterError("B adapter did not return research-only success")
    adapter_root = run_root / "adapter"
    store_root = run_root / "direct_numeric_store"
    adapter_receipt_path = adapter_root / "adapter_receipt.json"
    adapted_manifest_path = adapter_root / "all_field_enriched" / "manifest.json"
    store_metadata_path = store_root / "store_metadata.json"
    store_receipt_path = store_root / "consumption_receipt.json"
    for path in (adapter_receipt_path, adapted_manifest_path, store_metadata_path, store_receipt_path):
        _reject_reparse_aliases(path)
        if not path.is_file():
            raise DailySourceRowResearchAdapterError(f"adapter output is missing: {path.name}")
    adapter_receipt_bytes = adapter_receipt_path.read_bytes()
    adapter_receipt = _parse_object(adapter_receipt_bytes, "receipt")
    adapter_receipt_sha = _sha256(adapter_receipt_bytes)
    if (
        adapter_receipt.get("schema_version") != "ml-research-direct-ooc-adapter-receipt.v1"
        or adapter_receipt.get("status") != "verified_numeric_observations_ready"
        or adapter_receipt.get("formal_credit") is not False
        or adapter_receipt.get("historical_pit_eligible") is not False
        or adapter_receipt.get("formal_d_root_untouched") is not True
        or adapter_receipt.get("formal_release_v4_pointer_untouched") is not True
        or adapter_receipt.get("candidate_manifest_bytes_sha256") != projection["manifest_sha256"]
        or Path(str(adapter_receipt.get("candidate_raw_manifest_path"))).resolve()
        != projection["manifest_path"]
        or adapter_receipt.get("training_as_of") != projection["training_as_of"]
        or Path(str(adapter_receipt.get("adapted_manifest_path"))).resolve()
        != adapted_manifest_path.resolve()
    ):
        raise DailySourceRowResearchAdapterError("B adapter receipt is not bound to the projection")
    adapted_manifest_bytes = adapted_manifest_path.read_bytes()
    adapted_manifest = _parse_object(adapted_manifest_bytes, "adapted manifest")
    if (
        _sha256(adapted_manifest_bytes) != adapter_receipt.get("adapted_manifest_bytes_sha256")
        or adapted_manifest.get("manifest_hash") != adapter_receipt.get("adapted_manifest_hash")
        or adapted_manifest.get("manifest_hash")
        != _canonical_sha256(_without_hash(adapted_manifest, "manifest_hash"))
        or adapter_receipt.get("row_count") != projection["row_count"]
        or payload.get("row_count") != projection["row_count"]
        or Path(str(payload.get("adapter_receipt_path"))).resolve()
        != adapter_receipt_path.resolve()
        or Path(str(payload.get("adapted_manifest_path"))).resolve()
        != adapted_manifest_path.resolve()
        or payload.get("adapted_manifest_hash") != adapter_receipt.get("adapted_manifest_hash")
    ):
        raise DailySourceRowResearchAdapterError("adapted manifest pins or row count differ")

    store_receipt_bytes = store_receipt_path.read_bytes()
    store_receipt = _parse_object(store_receipt_bytes, "consumption receipt")
    store_metadata_bytes = store_metadata_path.read_bytes()
    store_metadata = _parse_object(store_metadata_bytes, "store metadata")
    feature_registry_path = store_root / "feature_registry.json"
    _reject_reparse_aliases(feature_registry_path)
    if not feature_registry_path.is_file():
        raise DailySourceRowResearchAdapterError("Direct numeric store feature registry is missing")
    feature_registry_bytes = feature_registry_path.read_bytes()
    try:
        feature_registry = json.loads(feature_registry_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DailySourceRowResearchAdapterError("Direct feature registry is not valid JSON") from exc
    if (
        store_receipt.get("schema_version") != "ml-research-direct-numeric-receipt.v1"
        or store_receipt.get("status") != "verified_numeric_observations_ready"
        or store_receipt.get("adapter_receipt_bytes_sha256") != adapter_receipt_sha
        or store_receipt.get("candidate_manifest_bytes_sha256") != projection["manifest_sha256"]
        or store_receipt.get("current_observation_freeze") != projection["training_as_of"]
        or store_receipt.get("record_count") != projection["row_count"]
        or store_receipt.get("formal_release_v4_pointer_untouched") is not True
        or store_receipt.get("formal_d_root_untouched") is not True
        or store_receipt.get("formal_oos_allowed") is not False
        or store_receipt.get("historical_pit_eligible") is not False
        or store_receipt.get("production_alpha_bp") != 0
        or store_receipt.get("feature_registry_sha256")
        != adapter_receipt.get("feature_registry_sha256")
        or store_receipt.get("stored_shards") != store_metadata.get("stored_shards")
        or _canonical_sha256(feature_registry)
        != store_receipt.get("feature_registry_sha256")
        or _sha256(store_metadata_bytes) != store_receipt.get("store_metadata_sha256")
        or store_metadata.get("status") != "verified_numeric_observations_ready"
        or store_metadata.get("record_count") != projection["row_count"]
        or store_metadata.get("feature_value_count")
        != store_receipt.get("feature_value_count")
        or store_metadata.get("current_observation_freeze") != projection["training_as_of"]
        or store_metadata.get("historical_pit_eligible") is not False
        or store_metadata.get("formal_oos_allowed") is not False
        or store_metadata.get("production_alpha_bp") != 0
    ):
        raise DailySourceRowResearchAdapterError("Direct numeric store receipt or metadata differs")
    stored_shards_value = store_metadata.get("stored_shards")
    if not isinstance(stored_shards_value, list) or not stored_shards_value:
        raise DailySourceRowResearchAdapterError("Direct numeric store shard pins are missing")
    verified_stored_shards: list[dict[str, Any]] = []
    for index, shard_pin in enumerate(stored_shards_value):
        if not isinstance(shard_pin, Mapping):
            raise DailySourceRowResearchAdapterError("Direct numeric store shard pin is invalid")
        relative_value = shard_pin.get("path")
        if (
            not isinstance(relative_value, str)
            or not relative_value
            or Path(relative_value).is_absolute()
            or ".." in Path(relative_value).parts
        ):
            raise DailySourceRowResearchAdapterError("Direct numeric store shard path is invalid")
        shard_path = store_root / Path(relative_value)
        _reject_reparse_aliases(shard_path)
        try:
            shard_path.resolve(strict=True).relative_to(store_root.resolve(strict=True))
        except (OSError, ValueError) as exc:
            raise DailySourceRowResearchAdapterError(
                "Direct numeric store shard escaped its run root"
            ) from exc
        shard_sha = _strict_sha256(
            shard_pin.get("bytes_sha256"),
            f"store_metadata.stored_shards[{index}].bytes_sha256",
        )
        shard_size = shard_path.stat().st_size
        verified_size = _verify_file_pin(
            shard_path,
            root=store_root,
            expected_sha256=shard_sha,
            expected_bytes=shard_size,
            label=f"Direct numeric store shard {relative_value}",
        )
        if (
            shard_pin.get("compressed_sha256") != shard_sha
            or type(shard_pin.get("row_count")) is not int
            or shard_pin["row_count"] < 1
        ):
            raise DailySourceRowResearchAdapterError(
                "Direct numeric store shard descriptor differs from verified bytes"
            )
        verified_stored_shards.append(
            {
                "path": str(shard_path.resolve(strict=True)),
                "relative_path": relative_value,
                "bytes": verified_size,
                "bytes_sha256": shard_sha,
                "compressed_sha256": shard_pin["compressed_sha256"],
                "uncompressed_sha256": _strict_sha256(
                    shard_pin.get("uncompressed_sha256"),
                    f"store_metadata.stored_shards[{index}].uncompressed_sha256",
                ),
                "row_count": shard_pin["row_count"],
            }
        )
    reported_store_receipt = payload.get("direct_store_receipt")
    if not isinstance(reported_store_receipt, Mapping):
        raise DailySourceRowResearchAdapterError("B adapter omitted its Direct store receipt")
    if (
        dict(reported_store_receipt) != store_receipt
        or reported_store_receipt.get("adapter_receipt_bytes_sha256") != adapter_receipt_sha
    ):
        raise DailySourceRowResearchAdapterError("B adapter stdout store receipt differs")

    return {
        "adapter_root": str(adapter_root.resolve()),
        "adapter_output_root": str(adapter_root.resolve()),
        "adapter_receipt_path": str(adapter_receipt_path.resolve()),
        "adapter_receipt_sha256": adapter_receipt_sha,
        "adapted_manifest_path": str(adapted_manifest_path.resolve()),
        "adapted_manifest_sha256": _sha256(adapted_manifest_bytes),
        "adapted_manifest_canonical_sha256": adapter_receipt.get("adapted_manifest_hash"),
        "feature_registry_sha256": adapter_receipt.get("feature_registry_sha256"),
        "direct_numeric_store_root": str(store_root.resolve()),
        "direct_store_output_root": str(store_root.resolve()),
        "store_metadata_path": str(store_metadata_path.resolve()),
        "store_metadata_sha256": _sha256(store_metadata_bytes),
        "feature_registry_path": str(feature_registry_path.resolve()),
        "feature_registry_sha256": store_receipt.get("feature_registry_sha256"),
        "feature_registry_bytes_sha256": _sha256(feature_registry_bytes),
        "consumption_receipt_path": str(store_receipt_path.resolve()),
        "consumption_receipt_sha256": _sha256(store_receipt_bytes),
        "stored_shards": verified_stored_shards,
        "record_count": store_receipt.get("record_count"),
        "feature_value_count": store_receipt.get("feature_value_count"),
        "direct_ooc_status": store_receipt.get("direct_ooc_status"),
        "source_revision_qualification": adapter_receipt.get("source_revision_qualification"),
    }


def run_daily_source_row_research_adapter(
    *,
    raw_run_id: str,
    source_date: str,
    projection_status: Mapping[str, Any],
    repository_root: Path = REPO_ROOT,
    research_output_root: Path | None = None,
    now_provider: Callable[[], datetime] | None = None,
    adapter_script: Path | None = None,
    timeout_seconds: int = ADAPTER_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Adapt and consume one pinned successful source-row projection.

    The child request folder is keyed by the actual raw run and event date.
    Existing requests are never overwritten or reused.
    """

    base: dict[str, Any] = {
        "schema_version": "ml-daily-source-row-b-adapter-run.v1",
        "status": "blocked",
        "raw_run_id": raw_run_id,
        "source_date": source_date,
        "research_only": True,
        "formal_credit": False,
        "historical_pit_eligible": False,
        "formal_oos_allowed": False,
        "model_use_claimed": False,
        "production_alpha_bp": 0,
    }
    request_root: Path | None = None
    request_owned = False
    started_at = (now_provider or _utc_now)()
    try:
        if not isinstance(raw_run_id, str) or not RUN_ID_PATTERN.fullmatch(raw_run_id):
            raise DailySourceRowResearchAdapterError("raw run id is invalid")
        if timeout_seconds <= 0:
            raise DailySourceRowResearchAdapterError("adapter timeout must be positive")
        repo = Path(os.path.abspath(str(repository_root))).resolve(strict=True)
        projection = _validate_projection(
            projection_status,
            source_date=source_date,
            repository_root=repo,
            now=(now_provider or _utc_now)(),
        )
        request_name = raw_run_id
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
            raise DailySourceRowResearchAdapterError(
                "research output root differs from the configured active root"
            )
        request_parent = research_root / "daily_source_rows" / source_date
        request_parent = resolve_ml_research_output_path(
            request_parent, repository_root=repo, access="write"
        )
        request_parent.mkdir(parents=True, exist_ok=True)
        request_parent = resolve_ml_research_output_path(
            request_parent, repository_root=repo, access="write"
        )
        request_root = request_parent / request_name
        request_root = resolve_ml_research_output_path(
            request_root, repository_root=repo, access="write"
        )
        if request_root.exists():
            raise DailySourceRowResearchAdapterError(
                "adapter request path already exists; safe retry requires a new raw run id"
            )
        request_root.mkdir(parents=False, exist_ok=False)
        request_owned = True
        request_root = resolve_ml_research_output_path(
            request_root, repository_root=repo, access="write"
        )
        base.update(
            {
                "projection_id": projection["projection_id"],
                "projection_manifest_path": str(projection["manifest_path"]),
                "projection_manifest_sha256": projection["manifest_sha256"],
                "projection_observations_path": str(projection["observations_path"]),
                "projection_observations_sha256": projection["observations_sha256"],
                "projection_completion_receipt_path": str(projection["completion_path"]),
                "projection_completion_receipt_sha256": projection["completion_sha256"],
                "projection_terminal_receipt_path": str(projection["terminal_path"]),
                "projection_terminal_receipt_sha256": projection["terminal_sha256"],
                "training_as_of": projection["training_as_of"],
                "research_output_root": str(research_root.resolve()),
                "research_artifact_root": str(request_root),
                "output_root": str(request_root),
                "output_root_kind": "configured_active_ml_research_run",
                "symbols": projection["symbols"],
                "current_symbols": projection["symbols"],
                "event_date": projection["source_date"],
                "current_observation_freeze": projection["training_as_of"],
                "symbol_count": len(projection["symbols"]),
                "projected_row_count": projection["row_count"],
                "source_available_at_min": projection["source_available_at_min"],
                "source_available_at_max": projection["source_available_at_max"],
                "verified_source_input_file_pins": projection["verified_input_file_pins"],
            }
        )
        started_payload = {
            "schema_version": "ml-daily-source-row-b-adapter-start.v1",
            "status": "running",
            "raw_run_id": raw_run_id,
            "source_date": source_date,
            "projection_id": projection["projection_id"],
            "projection_manifest_path": str(projection["manifest_path"]),
            "projection_manifest_sha256": projection["manifest_sha256"],
            "projection_terminal_receipt_path": str(projection["terminal_path"]),
            "projection_terminal_receipt_sha256": projection["terminal_sha256"],
            "projection_observations_path": str(projection["observations_path"]),
            "projection_observations_sha256": projection["observations_sha256"],
            "verified_source_input_file_pins": projection["verified_input_file_pins"],
            "training_as_of": projection["training_as_of"],
            "current_observation_freeze": projection["training_as_of"],
            "event_date": projection["source_date"],
            "current_symbols": projection["symbols"],
            "started_at": started_at.astimezone(timezone.utc).isoformat(),
            "research_only": True,
            "formal_credit": False,
            "historical_pit_eligible": False,
            "formal_oos_allowed": False,
            "model_use_claimed": False,
        }
        started_path = request_root / "start_receipt.json"
        started_sha = _write_create_only(
            started_path, started_payload, repository_root=repo
        )

        adapter_dir = request_root / "adapter"
        store_dir = request_root / "direct_numeric_store"
        script = adapter_script or (repo / "scripts" / "adapt_ml_research_direct_ooc.py")
        script = Path(os.path.abspath(str(script)))
        if not script.is_file():
            raise DailySourceRowResearchAdapterError("existing B adapter CLI is missing")
        argv = [
            sys.executable,
            str(script),
            "--raw-candidate-manifest",
            str(projection["manifest_path"]),
            "--expected-candidate-manifest-bytes-sha256",
            projection["manifest_sha256"],
            "--training-as-of",
            projection["training_as_of"],
            "--output-dir",
            str(adapter_dir),
            "--consume-direct-store",
            str(store_dir),
        ]
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            completed = subprocess.run(
                argv,
                cwd=str(repo),
                env=env,
                capture_output=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, bytes) else b""
            stderr = exc.stderr if isinstance(exc.stderr, bytes) else b""
            base["adapter_process"] = {
                "exit_code": None,
                "timed_out": True,
                "stdout_bytes": len(stdout),
                "stdout_sha256": _sha256(stdout),
                "stderr_bytes": len(stderr),
                "stderr_sha256": _sha256(stderr),
            }
            raise DailySourceRowResearchAdapterError(
                "existing B adapter CLI exceeded its bounded timeout"
            ) from exc
        stdout = completed.stdout if isinstance(completed.stdout, bytes) else str(completed.stdout or "").encode()
        stderr = completed.stderr if isinstance(completed.stderr, bytes) else str(completed.stderr or "").encode()
        base["adapter_process"] = {
            "exit_code": completed.returncode,
            "stdout_bytes": len(stdout),
            "stdout_sha256": _sha256(stdout),
            "stderr_bytes": len(stderr),
            "stderr_sha256": _sha256(stderr),
        }
        if completed.returncode != 0:
            detail = stderr[-1024:].decode("utf-8", errors="replace").strip()
            raise DailySourceRowResearchAdapterError(
                f"existing B adapter CLI exited {completed.returncode}: {detail}"
            )
        adapter_payload = _parse_object(stdout, "stdout")
        child = _verify_adapter_outputs(adapter_payload, projection=projection, run_root=request_root)
        completed_at = (now_provider or _utc_now)()
        if completed_at.tzinfo is None or completed_at.utcoffset() is None:
            raise DailySourceRowResearchAdapterError("completion clock must be timezone-aware")
        if completed_at.astimezone(timezone.utc) < started_at.astimezone(timezone.utc):
            raise DailySourceRowResearchAdapterError("completion clock moved backwards")
        terminal_payload = {
            **base,
            **child,
            "schema_version": "ml-daily-source-row-b-adapter-terminal.v1",
            "status": "completed_research_only",
            "started_at": started_at.astimezone(timezone.utc).isoformat(),
            "completed_at": completed_at.astimezone(timezone.utc).isoformat(),
            "start_receipt_path": str(started_path.resolve()),
            "start_receipt_sha256": started_sha,
            "adapter_stdout_sha256": base["adapter_process"]["stdout_sha256"],
            "adapter_stderr_sha256": base["adapter_process"]["stderr_sha256"],
            "source_scope": "current daily source rows; event date is distinct from available_at",
            "core19_direct_fit_input": False,
            "core19_bridge_input_compatible": True,
            "core19_bridge_status": "not_run_missing_same_run_direct_prepared_core19",
            "core19_fit_readiness": {
                "status": "blocked_missing_same_run_direct_prepared_core19_and_fit_inputs",
                "daily_source_row_role": (
                    "B daily numeric store can be supplied to the existing same-stock/date "
                    "CORE19 bridge; it is not itself the complete CORE19 training vector"
                ),
                "missing_inputs": [
                    "same_run_direct_prepared_core19_vector_and_feature_registry_path_and_sha256",
                    "raw_publication_manifest_path_and_sha256",
                    "raw_dataset_manifest_path_and_sha256",
                    "outcome_artifact_receipt_path_and_sha256",
                    "outcome_feature_registry_path_and_sha256",
                    "verified_source_context_envelope_path_and_sha256",
                    "core19_feature_registry_and_complete_current_vector",
                ],
            },
            "current_restated_fit_evidence_not_provided": [
                "raw_publication_manifest_path_and_sha256",
                "raw_dataset_manifest_path_and_sha256",
                "outcome_artifact_receipt_path_and_sha256",
                "outcome_feature_registry_path_and_sha256",
                "verified_source_context_envelope_path_and_sha256",
            ],
            "source_revision_qualification": "unverified_requires_separate_strict_inspection",
            "direct_ooc_status": "blocked_insufficient_context_or_mature_history",
            "historical_pit_eligible": False,
            "formal_credit": False,
            "formal_oos_allowed": False,
            "model_use_claimed": False,
            "model_created": False,
            "prediction_created": False,
            "outcome_created": False,
            "formal_release_v4_pointer_untouched": True,
            "formal_d_root_untouched": True,
            "production_alpha_bp": 0,
        }
        terminal_path = request_root / "terminal_receipt.json"
        terminal_sha = _write_create_only(
            terminal_path, terminal_payload, repository_root=repo
        )
        base.update(
            {
                **terminal_payload,
                "terminal_receipt_path": str(terminal_path.resolve()),
                "terminal_receipt_sha256": terminal_sha,
            }
        )
        return base
    except Exception as exc:
        base["status"] = "failed_closed"
        base["error_type"] = type(exc).__name__
        base["error"] = str(exc)
        if request_owned and request_root is not None and request_root.is_dir():
            failure_payload = {
                **base,
                "schema_version": "ml-daily-source-row-b-adapter-terminal.v1",
                "status": "failed_closed",
                "started_at": started_at.isoformat(),
                "completed_at": (now_provider or _utc_now)().isoformat(),
                "research_only": True,
                "formal_credit": False,
                "historical_pit_eligible": False,
                "formal_oos_allowed": False,
                "model_use_claimed": False,
                "production_alpha_bp": 0,
            }
            failure_path = request_root / "terminal_receipt.json"
            try:
                failure_sha = _write_create_only(
                    failure_path,
                    failure_payload,
                    repository_root=Path(os.path.abspath(str(repository_root))).resolve(),
                )
            except (FileExistsError, OSError, DailySourceRowResearchAdapterError):
                pass
            else:
                base["terminal_receipt_path"] = str(failure_path.resolve())
                base["terminal_receipt_sha256"] = failure_sha
        return base


__all__ = [
    "DailySourceRowResearchAdapterError",
    "run_daily_source_row_research_adapter",
]
