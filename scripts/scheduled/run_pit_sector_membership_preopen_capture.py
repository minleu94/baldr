"""在台北 08:30 前保存官方 PIT current-day archive。

此排程是 PIT 日常鏈的 capture half：它只在台北 08:30 前啟動官方
TWSE／TPEx read-only source，並把 response completion、raw custody、machine
consumer readback 與 durable archive 一起保存。盤後 publisher 只讀這份
archive，不會用新的同日 HTTP response 取代盤前 evidence。
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Mapping, Sequence, TypedDict
import uuid
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_module.formal_daily_input_producer import (  # noqa: E402
    FormalDailyInputProducerError,
    capture_pit_candidate_before_cutoff,
    reuse_pit_candidate_archive_before_cutoff,
)
from data_module.pit_prospective_denominator import (  # noqa: E402
    validate_prospective_pit_denominator,
)
from data_module.formal_runtime_config import (  # noqa: E402
    FORMAL_RUNTIME_CONFIG_ENV,
    FormalRuntimeConfigError,
    load_optional_formal_runtime_config,
)
from data_module.pit_taxonomy_source_producer import (  # noqa: E402
    OFFICIAL_COMPANY_SOURCE_DEFINITIONS,
    PIT_TAXONOMY_LATE_CONFIG_SOURCE_RELATIVE_PATH,
    PIT_TAXONOMY_LIVE_CONFIG_SOURCE_RELATIVE_PATH,
    PIT_TAXONOMY_MAX_SOURCE_BYTES,
    PIT_TAXONOMY_SOURCE_CONFIG_ENV,
    PITTaxonomySourceError,
    _decode_json_object_no_duplicates,
    _proof_child,
    _plan_configured_components,
    _assert_no_link_path,
    capture_configured_daily_pit_taxonomy_bundle,
    load_pit_taxonomy_source_config,
    materialize_existing_split_source_config_proof,
    read_existing_split_source_config_proof,
    read_pit_taxonomy_capture_attempt,
    _proof_file_bytes,
    validate_daily_pit_taxonomy_bundle,
)
from data_module.prospective_formal_clock import canonical_json  # noqa: E402
from scripts.capture_pit_prospective_denominator import (  # noqa: E402
    capture_live_denominator,
)
from data_module.formal_schedule_gate import (  # noqa: E402
    formal_schedule_day_state,
)


TASK_NAME = "baldr-pit-sector-membership-preopen-capture-daily"
DEFAULT_PUBLICATION_ROOT = ROOT / "output" / "formal_daily_publications"
TAIPEI = ZoneInfo("Asia/Taipei")
PIT_CUTOFF = time(8, 30)
RULE_SOURCE_ROOT_ENV = "FORMAL_DAILY_RULE_SOURCE_ROOT"
PIT_TAXONOMY_PREOPEN_ROOT_ENV = "PIT_TAXONOMY_PREOPEN_ROOT"
SPLIT_DENOMINATOR_PROOF_MAX_BYTES = 16 * 1024 * 1024
SPLIT_RULE_METADATA_PROOF_MAX_BYTES = 16 * 1024 * 1024
SPLIT_RULE_SOURCE_WINDOW_PROOF_MAX_BYTES = 128 * 1024 * 1024


class _RuleSourceParent(TypedDict):
    bundle_root: str
    identity_path: str
    symbols_path: str
    clock_path: str
    identity: dict[str, object]
    symbols_payload: object
    clock: dict[str, object]
    expected_symbols: tuple[str, ...]
    universe_hash_symbols: tuple[str, ...]
    scores_bp: tuple[int, ...]
    rank_order: tuple[str, ...]
    rank_order_source: str
    universe_hash: str
    clock_id: str
    clock_manifest_hash: str


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--publication-root",
        type=Path,
        help="持久 publication root；只能是 repository output 或隔離 TEMP",
    )
    parser.add_argument(
        "--status-root",
        type=Path,
        help="狀態輸出目錄；預設為 publication root/scheduler/pit_preopen_capture",
    )
    parser.add_argument(
        "--split-denominator-contract",
        action="store_true",
        help=(
            "明確 opt-in 建立獨立 v2 taxonomy-only candidate；不代表 Rule/formal acceptance，"
            "也不覆寫 v1 archive"
        ),
    )
    parser.add_argument(
        "--materialize-existing-split-config-proof",
        action="store_true",
        help="僅為指定既有 split candidate 建立獨立晚綁定 config proof；不抓網路、不改 candidate",
    )
    parser.add_argument(
        "--source-config-proof-source",
        type=Path,
        help="既有 2026-10-01 saved-notice source config bytes；只供明確 materialization 子命令使用",
    )
    return parser


def _publication_root(override: Path | None) -> Path:
    configured = override or _env_path("FORMAL_DAILY_PUBLICATION_ROOT")
    return (configured or DEFAULT_PUBLICATION_ROOT).expanduser().resolve()


def _status_root(publication_root: Path, override: Path | None) -> Path:
    configured = override or _env_path("FORMAL_DAILY_PIT_CAPTURE_STATUS_ROOT")
    root = (configured or publication_root / "scheduler" / "pit_preopen_capture").expanduser().resolve()
    try:
        root.relative_to(publication_root)
    except ValueError as error:
        raise ValueError("PIT capture status root must be under publication root") from error
    return root


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(value.strip())


def _write_status(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _find_verified_denominator(
    publication_root: Path,
    *,
    target_date: datetime,
) -> tuple[Path | None, str | None]:
    """找出當日已驗證的獨立分母；只接受同一台北自然日的封套。"""

    local_date = target_date.astimezone(TAIPEI).date().isoformat()
    candidates = sorted(
        (
            publication_root.expanduser().resolve() / "pit_denominator"
        ).glob(local_date + "*/denominator.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    failures: list[str] = []
    for candidate in candidates:
        try:
            payload = validate_prospective_pit_denominator(
                candidate,
                now=target_date,
            )
            if payload.get("coverage_start") != local_date:
                failures.append(f"{candidate.name}:coverage_start_mismatch")
                continue
            return candidate.resolve(), "existing_verified"
        except Exception as error:  # noqa: BLE001 - try next immutable run
            failures.append(f"{candidate.name}:{type(error).__name__}")
    detail = ";".join(failures[:3])
    return None, "missing" + (":" + detail if detail else "")


def _refresh_pit_denominator(
    *,
    publication_root: Path,
    observed: datetime,
    allow_network: bool,
) -> dict[str, object]:
    """在 PIT 盤前 task 內自動建立當日獨立 denominator。"""

    root = publication_root.expanduser().resolve()
    existing, existing_reason = _find_verified_denominator(
        root,
        target_date=observed,
    )
    if existing is not None:
        return {
            "status": "existing_verified",
            "path": str(existing),
            "coverage_start": observed.astimezone(TAIPEI).date().isoformat(),
            "network_attempted": False,
        }
    if not allow_network:
        return {
            "status": "skipped_injected_clock",
            "reason": "operational denominator refresh is disabled for an injected test clock",
            "existing_lookup": existing_reason,
            "network_attempted": False,
        }
    target_date = observed.astimezone(TAIPEI).date()
    output_dir = (
        root
        / "pit_denominator"
        / f"{target_date.isoformat()}-run-{uuid.uuid4().hex[:16]}"
    )
    try:
        result = capture_live_denominator(
            output_dir=output_dir,
            coverage_start=target_date,
        )
        path = Path(str(result["path"])).expanduser().resolve()
        validated = validate_prospective_pit_denominator(path)
    except Exception as error:  # noqa: BLE001 - source failure stays observable
        return {
            "status": "blocked",
            "reason": f"pit_denominator_refresh_failed:{type(error).__name__}:{str(error).splitlines()[0][:220]}",
            "existing_lookup": existing_reason,
            "network_attempted": True,
        }
    license_scope = validated.get("license_scope")
    license_status = (
        license_scope.get("status")
        if isinstance(license_scope, Mapping)
        else None
    )
    return {
        "status": "captured_verified",
        "path": str(path),
        "file_sha256": result.get("file_sha256"),
        "content_sha256": validated.get("content_sha256"),
        "coverage_start": validated.get("coverage_start"),
        "symbol_count": validated.get("symbol_count"),
        "license_scope_status": license_status,
        "network_attempted": True,
    }


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_json(value: object) -> str:
    return _sha256_bytes(canonical_json(value).encode("utf-8"))


def _read_json_object(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PITTaxonomySourceError(f"{label} is unreadable") from error
    if not isinstance(value, Mapping):
        raise PITTaxonomySourceError(f"{label} must be an object")
    return {str(key): item for key, item in value.items()}


def _read_json_value(path: Path, label: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PITTaxonomySourceError(f"{label} is unreadable") from error


def _bounded_child(root: Path, relative_value: object, label: str) -> Path:
    if not isinstance(relative_value, str) or not relative_value.strip():
        raise PITTaxonomySourceError(f"{label} path is missing")
    relative = Path(relative_value)
    if relative.is_absolute() or str(relative) in {"", "."}:
        raise PITTaxonomySourceError(f"{label} path must be relative")
    target = (root / relative).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as error:
        raise PITTaxonomySourceError(f"{label} path escapes root") from error
    return target


def _load_archived_company_sources(
    archive_manifest_path: Path,
) -> tuple[dict[str, bytes], dict[str, Mapping[str, object]], dict[str, object]]:
    """從已驗證 PIT archive 取出原始 L/O bytes，不重新抓取。"""

    manifest_path = archive_manifest_path.expanduser().resolve()
    if not manifest_path.is_file():
        raise PITTaxonomySourceError("PIT candidate archive manifest is missing")
    manifest = _read_json_object(manifest_path, "PIT candidate archive manifest")
    declared_hash = manifest.get("manifest_hash")
    if not isinstance(declared_hash, str) or _sha256_json(
        {key: value for key, value in manifest.items() if key != "manifest_hash"}
    ) != declared_hash:
        raise PITTaxonomySourceError("PIT candidate archive manifest hash mismatch")
    files_value = manifest.get("files")
    if not isinstance(files_value, list):
        raise PITTaxonomySourceError("PIT candidate archive files are missing")
    archive_root = manifest_path.parent
    file_by_relative: dict[str, tuple[Path, Mapping[str, object]]] = {}
    publication_path: Path | None = None
    for raw_file in files_value:
        if not isinstance(raw_file, Mapping):
            raise PITTaxonomySourceError("PIT candidate archive file entry is invalid")
        relative_value = raw_file.get("relative_path")
        target = _bounded_child(archive_root, relative_value, "PIT archive file")
        relative = Path(str(relative_value)).as_posix()
        if relative in file_by_relative:
            raise PITTaxonomySourceError("PIT candidate archive paths are duplicated")
        try:
            raw = target.read_bytes()
        except OSError as error:
            raise PITTaxonomySourceError("PIT candidate archive file is unreadable") from error
        expected_hash = raw_file.get("archive_file_hash")
        source_hash = raw_file.get("source_file_hash")
        if not isinstance(expected_hash, str) or expected_hash != source_hash:
            raise PITTaxonomySourceError("PIT candidate archive file hash declaration is invalid")
        if _sha256_bytes(raw) != expected_hash:
            raise PITTaxonomySourceError("PIT candidate archive file hash mismatch")
        if raw_file.get("byte_count") != len(raw):
            raise PITTaxonomySourceError("PIT candidate archive file byte count mismatch")
        file_by_relative[relative] = (target, raw_file)
        if raw_file.get("role") == "publication":
            publication_path = target
    if publication_path is None:
        raise PITTaxonomySourceError("PIT candidate archive publication is missing")
    publication = _read_json_object(
        publication_path,
        "PIT candidate archive publication",
    )
    content_hash = publication.get("content_sha256")
    if not isinstance(content_hash, str) or _sha256_json(
        {key: value for key, value in publication.items() if key != "content_sha256"}
    ) != content_hash:
        raise PITTaxonomySourceError("PIT candidate publication content hash mismatch")
    raw_inputs = publication.get("raw_inputs")
    if not isinstance(raw_inputs, list):
        raise PITTaxonomySourceError("PIT candidate publication raw_inputs are missing")
    raw_payloads: dict[str, bytes] = {}
    raw_http: dict[str, Mapping[str, object]] = {}
    for raw_input in raw_inputs:
        if not isinstance(raw_input, Mapping):
            raise PITTaxonomySourceError("PIT candidate raw input entry is invalid")
        market = raw_input.get("market")
        if market not in {"twse", "tpex"}:
            raise PITTaxonomySourceError("PIT candidate raw input market is unsupported")
        if market in raw_payloads:
            raise PITTaxonomySourceError("PIT candidate raw input market is duplicated")
        relative = Path(str(raw_input.get("path"))).as_posix()
        target_entry = file_by_relative.get(relative)
        if target_entry is None:
            raise PITTaxonomySourceError(
                f"PIT candidate raw input is not in immutable archive: {market}"
            )
        target, _archive_entry = target_entry
        raw = target.read_bytes()
        expected_hash = raw_input.get("content_sha256")
        if not isinstance(expected_hash, str) or _sha256_bytes(raw) != expected_hash:
            raise PITTaxonomySourceError(
                f"PIT candidate raw input hash mismatch: {market}"
            )
        http = raw_input.get("http")
        if not isinstance(http, Mapping):
            raise PITTaxonomySourceError(
                f"PIT candidate raw input HTTP metadata is missing: {market}"
            )
        raw_payloads[str(market)] = raw
        raw_http[str(market)] = {str(key): item for key, item in http.items()}
    if set(raw_payloads) != {"twse", "tpex"}:
        raise PITTaxonomySourceError("PIT candidate archive must contain TWSE and TPEx raw inputs")
    return raw_payloads, raw_http, {
        "manifest_path": str(manifest_path),
        "manifest_hash": declared_hash,
        "publication_path": str(publication_path),
        "publication_content_hash": content_hash,
        "captured_at": publication.get("captured_at"),
        "raw_input_count": len(raw_payloads),
    }


def _find_rule_source_parent(
    publication_root: Path,
    *,
    target_date: date,
) -> _RuleSourceParent:
    """找同日 score-bearing rule parent；缺 hash inputs 時明確阻擋。"""

    configured = _env_path(RULE_SOURCE_ROOT_ENV)
    source_root = (configured or publication_root / "rule_source").expanduser().resolve()
    if source_root.is_dir() and (source_root / "metadata" / "universe_identity.json").is_file():
        candidates = [source_root]
    else:
        candidates = [
            item
            for item in source_root.glob(f"clock-{target_date.strftime('%Y%m%d')}*")
            if item.is_dir()
        ]
    if not candidates:
        raise PITTaxonomySourceError(
            f"score-bearing rule source parent is missing: {target_date.isoformat()}"
        )
    failures: list[str] = []
    for candidate in sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            identity_path = candidate / "metadata" / "universe_identity.json"
            symbols_path = candidate / "metadata" / "universe_symbols.json"
            clock_path = candidate / "clock" / "manifest.json"
            identity = _read_json_object(identity_path, "rule parent universe identity")
            symbols_value = _read_json_value(symbols_path, "rule parent universe symbols")
            clock = _read_json_object(clock_path, "rule parent clock manifest")
            symbols = _strict_symbol_list(identity.get("symbols"), "rule parent identity symbols")
            if symbols_value != list(symbols):
                raise PITTaxonomySourceError("rule parent universe_symbols differs from identity")
            if identity.get("candidate_count") != len(symbols):
                raise PITTaxonomySourceError("rule parent candidate_count differs from symbols")
            if identity.get("source_id") != "daily_prices":
                raise PITTaxonomySourceError("rule parent source_id is unsupported")
            hash_symbols = _strict_symbol_list(
                identity.get("universe_hash_symbols"),
                "rule parent universe_hash_symbols",
                allow_unsorted=True,
            )
            scores_value = identity.get("scores_bp")
            if not isinstance(scores_value, list) or len(scores_value) != len(hash_symbols):
                raise PITTaxonomySourceError("rule parent scores_bp are missing or incomplete")
            if any(
                isinstance(item, bool)
                or not isinstance(item, int)
                or not 0 <= item <= 10000
                for item in scores_value
            ):
                raise PITTaxonomySourceError("rule parent scores_bp are invalid")
            scores = [int(item) for item in scores_value]
            universe_hash = identity.get("universe_hash")
            if not isinstance(universe_hash, str) or _sha256_json(
                {
                    "schema_version": "manual-rule-only-universe.v1",
                    "symbols": list(hash_symbols),
                    "scores_bp": scores,
                }
            ) != universe_hash:
                raise PITTaxonomySourceError("rule parent universe hash cannot be reconstructed")
            if set(hash_symbols) != set(symbols):
                raise PITTaxonomySourceError("rule parent hash symbols do not cover full symbols")
            rank_order_value = identity.get("rank_order")
            if rank_order_value is None:
                # formal_rule_source_producer.v3 does not persist a separate
                # rank_order field.  Its score-bearing order is the ordered
                # universe_hash_symbols sequence, with scores_bp aligned to
                # that sequence and bound by universe_hash.  Reuse that
                # producer-defined order; never invent a sorted fallback.
                rank_order = hash_symbols
                rank_order_source = "parent.universe_hash_symbols"
            else:
                rank_order = _strict_symbol_list(
                    rank_order_value,
                    "rule parent rank_order",
                    allow_unsorted=True,
                )
                rank_order_source = "parent.rank_order"
            if set(rank_order) != set(symbols):
                raise PITTaxonomySourceError("rule parent rank_order does not cover full symbols")
            if clock.get("activation_trading_day") != target_date.isoformat():
                raise PITTaxonomySourceError("rule parent clock activation date differs")
            if clock.get("universe_hash") != universe_hash:
                raise PITTaxonomySourceError("rule parent clock universe hash differs")
            clock_id = clock.get("clock_id")
            clock_hash = clock.get("manifest_hash")
            if not isinstance(clock_id, str) or not isinstance(clock_hash, str):
                raise PITTaxonomySourceError("rule parent clock identity is incomplete")
            clock_body = {key: value for key, value in clock.items() if key != "manifest_hash"}
            if _sha256_json(clock_body) != clock_hash:
                raise PITTaxonomySourceError("rule parent clock manifest hash mismatch")
            identity_hash = identity.get("identity_hash")
            if identity_hash is not None:
                if not isinstance(identity_hash, str) or _sha256_json(
                    {key: value for key, value in identity.items() if key != "identity_hash"}
                ) != identity_hash:
                    raise PITTaxonomySourceError("rule parent identity hash mismatch")
            return {
                "bundle_root": str(candidate.resolve()),
                "identity_path": str(identity_path.resolve()),
                "symbols_path": str(symbols_path.resolve()),
                "clock_path": str(clock_path.resolve()),
                "identity": identity,
                "symbols_payload": symbols_value,
                "clock": clock,
                "expected_symbols": symbols,
                "universe_hash_symbols": hash_symbols,
                "scores_bp": tuple(scores),
                "rank_order": rank_order,
                "rank_order_source": rank_order_source,
                "universe_hash": str(universe_hash),
                "clock_id": clock_id,
                "clock_manifest_hash": clock_hash,
            }
        except (OSError, PITTaxonomySourceError, TypeError, ValueError) as error:
            failures.append(f"{candidate.name}:{type(error).__name__}:{str(error).splitlines()[0][:160]}")
    detail = ";".join(failures[:3])
    raise PITTaxonomySourceError(
        "no valid score-bearing rule source parent"
        + (":" + detail if detail else "")
    )


def _strict_symbol_list(
    value: object,
    label: str,
    *,
    allow_unsorted: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise PITTaxonomySourceError(f"{label} is invalid")
    values = tuple(item.strip() for item in value)
    if len(set(values)) != len(values):
        raise PITTaxonomySourceError(f"{label} contains duplicates")
    if not allow_unsorted and values != tuple(sorted(values)):
        raise PITTaxonomySourceError(f"{label} is not sorted")
    return values


def _build_split_scope_binding(
    *,
    publication_root: Path,
    denominator_path: Path,
    denominator_payload: Mapping[str, object],
    parent: _RuleSourceParent,
    capture_date: date,
    decision_at: datetime,
    denominator_symbols: Sequence[str],
) -> dict[str, object]:
    """Build explicit, byte-pinned official-denominator / Rule-candidate proof."""

    root_input = publication_root.expanduser()
    _assert_no_link_path(root_input, allow_missing=False)
    root = root_input.resolve(strict=True)
    denominator_file, denominator_raw = _read_split_scope_proof_file(
        root,
        denominator_path.expanduser(),
        label="split-scope denominator",
        max_bytes=SPLIT_DENOMINATOR_PROOF_MAX_BYTES,
    )
    rule_root_input = Path(parent["bundle_root"]).expanduser()
    _assert_no_link_path(rule_root_input, allow_missing=False, confine_to=root)
    rule_root = rule_root_input.resolve(strict=True)
    try:
        denominator_relative = denominator_file.relative_to(root).as_posix()
        rule_relative = rule_root.relative_to(root).as_posix()
    except ValueError as error:
        raise PITTaxonomySourceError(
            "split-scope proof inputs must be under the publication root"
        ) from error
    if not denominator_relative.startswith("pit_denominator/"):
        raise PITTaxonomySourceError("split-scope denominator is outside pit_denominator")
    if not rule_relative.startswith("rule_source/"):
        raise PITTaxonomySourceError("split-scope Rule parent is outside rule_source")

    identity_path = rule_root / "metadata" / "universe_identity.json"
    symbols_path = rule_root / "metadata" / "universe_symbols.json"
    clock_path = rule_root / "clock" / "manifest.json"
    source_window_path = rule_root / "source" / "daily_price_window.json"
    proof_inputs = {
        "identity": (identity_path, SPLIT_RULE_METADATA_PROOF_MAX_BYTES),
        "symbols": (symbols_path, SPLIT_RULE_METADATA_PROOF_MAX_BYTES),
        "clock": (clock_path, SPLIT_RULE_METADATA_PROOF_MAX_BYTES),
        "source_window": (source_window_path, SPLIT_RULE_SOURCE_WINDOW_PROOF_MAX_BYTES),
    }
    proof_raw: dict[str, bytes] = {}
    file_hashes: dict[str, str] = {}
    for key, (proof_path, max_bytes) in proof_inputs.items():
        _resolved_path, raw = _read_split_scope_proof_file(
            root,
            proof_path,
            label=f"split-scope Rule {key}",
            max_bytes=max_bytes,
        )
        proof_raw[key] = raw
        file_hashes[key] = _sha256_bytes(raw)

    try:
        denominator_from_bytes = json.loads(denominator_raw.decode("utf-8"))
        identity_from_bytes = json.loads(proof_raw["identity"].decode("utf-8"))
        symbols_from_bytes = json.loads(proof_raw["symbols"].decode("utf-8"))
        clock_from_bytes = json.loads(proof_raw["clock"].decode("utf-8"))
        source_window_from_bytes = json.loads(proof_raw["source_window"].decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PITTaxonomySourceError("split-scope proof input JSON is invalid") from error
    if not isinstance(denominator_from_bytes, Mapping) or dict(denominator_from_bytes) != dict(denominator_payload):
        raise PITTaxonomySourceError("split-scope denominator bytes differ from validated payload")
    if not isinstance(identity_from_bytes, Mapping) or dict(identity_from_bytes) != parent["identity"]:
        raise PITTaxonomySourceError("split-scope Rule identity bytes changed after validation")
    if symbols_from_bytes != parent["symbols_payload"]:
        raise PITTaxonomySourceError("split-scope Rule symbols bytes changed after validation")
    if not isinstance(clock_from_bytes, Mapping) or dict(clock_from_bytes) != parent["clock"]:
        raise PITTaxonomySourceError("split-scope Rule clock bytes changed after validation")
    if not isinstance(source_window_from_bytes, Mapping):
        raise PITTaxonomySourceError("split-scope Rule source-window payload is invalid")
    source_window_payload = source_window_from_bytes.get("source_payload")
    source_window_hash = source_window_from_bytes.get("source_window_hash")
    if (
        not isinstance(source_window_payload, Mapping)
        or not isinstance(source_window_hash, str)
        or _sha256_json(dict(source_window_payload)) != source_window_hash
        or parent["identity"].get("source_window_hash") != source_window_hash
        or parent["identity"].get("source_window_file_hash") != file_hashes["source_window"]
    ):
        raise PITTaxonomySourceError("split-scope Rule source-window bytes changed or are invalid")

    identity = parent["identity"]
    candidate_symbols = tuple(parent["expected_symbols"])
    denominator_set = set(denominator_symbols)
    candidate_set = set(candidate_symbols)
    intersection = sorted(denominator_set & candidate_set)
    denominator_only = sorted(denominator_set - candidate_set)
    rule_only = sorted(candidate_set - denominator_set)
    diff = {
        "denominator_count": len(denominator_set),
        "candidate_count": len(candidate_set),
        "intersection_count": len(intersection),
        "denominator_only_count": len(denominator_only),
        "rule_only_count": len(rule_only),
        "intersection_symbols": intersection,
        "intersection_symbols_hash": _sha256_json(intersection),
        "denominator_only_symbols": denominator_only,
        "denominator_only_symbols_hash": _sha256_json(denominator_only),
        "rule_only_symbols": rule_only,
        "rule_only_symbols_hash": _sha256_json(rule_only),
    }
    return {
        "scope_binding_schema_version": "pit-industry-taxonomy-scope-binding.v1",
        "denominator_binding": {
            "schema_version": "pit-prospective-pit-denominator-binding.v1",
            "path": denominator_relative,
            "file_sha256": _sha256_bytes(denominator_raw),
            "content_sha256": denominator_payload.get("content_sha256"),
            "symbols_hash": denominator_payload.get("symbols_hash"),
            "symbol_count": len(denominator_symbols),
            "scope": denominator_payload.get("scope"),
            "coverage_start": denominator_payload.get("coverage_start"),
            "observed_at": denominator_payload.get("observed_at"),
        },
        "rule_candidate_binding": {
            "schema_version": "pit-rule-candidate-binding.v1",
            "bundle_path": rule_relative,
            "file_hashes": file_hashes,
            "identity_hash": identity.get("identity_hash"),
            "clock_id": parent["clock_id"],
            "clock_manifest_hash": parent["clock_manifest_hash"],
            "universe_hash": parent["universe_hash"],
            "candidate_count": len(candidate_symbols),
            "candidate_symbols_hash": _sha256_json(list(candidate_symbols)),
            "activation_trading_day": capture_date.isoformat(),
            "decision_at": decision_at.isoformat(),
            "data_as_of_date": identity.get("data_as_of_date"),
            "max_available_timestamp": identity.get("max_available_timestamp"),
            "source_window_hash": identity.get("source_window_hash"),
        },
        "scope_diff": diff,
        "taxonomy_coverage_complete": True,
        "rule_scope_compatible": not rule_only,
    }


def _read_split_scope_proof_file(
    publication_root: Path,
    proof_path: Path,
    *,
    label: str,
    max_bytes: int,
) -> tuple[Path, bytes]:
    """Read one confined split proof file once, with its existing byte limit."""

    root = publication_root.expanduser()
    path = proof_path.expanduser()
    _assert_no_link_path(root, allow_missing=False)
    root = root.resolve(strict=True)
    _assert_no_link_path(path, allow_missing=False, confine_to=root)
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise PITTaxonomySourceError(f"{label} proof path escapes or is missing") from error
    raw = _proof_file_bytes(path, label, max_bytes)
    return resolved, raw


def _taxonomy_bundle_root(publication_root: Path, target_date: date) -> Path:
    configured = _env_path(PIT_TAXONOMY_PREOPEN_ROOT_ENV)
    root = (configured or publication_root / "pit_taxonomy_preopen").expanduser().resolve()
    try:
        root.relative_to(publication_root.expanduser().resolve())
    except ValueError as error:
        raise PITTaxonomySourceError(
            "PIT taxonomy preopen root must be under publication root"
        ) from error
    return root / target_date.isoformat()


def _split_taxonomy_bundle_root(publication_root: Path, target_date: date) -> Path:
    root = publication_root.expanduser().resolve() / "pit_taxonomy_preopen_split_v2"
    configured = _env_path(PIT_TAXONOMY_PREOPEN_ROOT_ENV)
    if configured is not None and configured.resolve() != root:
        raise PITTaxonomySourceError(
            "split-denominator contract requires its separate immutable v2 output root"
        )
    return root / target_date.isoformat()


def _config_contains_url(config: Mapping[str, object]) -> bool:
    for section_name in ("classification", "security"):
        section = config.get(section_name)
        if not isinstance(section, Mapping):
            continue
        for spec in section.values():
            if isinstance(spec, Mapping) and isinstance(spec.get("url"), str) and spec.get("url", "").strip():
                return True
    return False


def _capture_taxonomy_for_run(
    *,
    publication_root: Path,
    observed: datetime,
    denominator: Mapping[str, object],
    archive_manifest_path: object,
    injected_clock: bool,
    split_denominator_contract: bool = False,
    capture_attempt_id: str | None = None,
    config_path: Path | None = None,
    fetch_source: Callable[[str], object] | None = None,
    now_provider: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """把既有 archive／denominator 接到獨立 taxonomy producer。"""

    if denominator.get("status") not in {"existing_verified", "captured_verified"}:
        return {
            "status": "skipped_injected_clock" if injected_clock else "blocked",
            "blockers": ["pit_taxonomy_waiting_for_verified_denominator"],
            "industry_filter_usable": False,
            "post_cutoff_refetch_forbidden": True,
        }
    denominator_path_value = denominator.get("path")
    if not isinstance(denominator_path_value, str) or not denominator_path_value.strip():
        return {
            "status": "blocked",
            "blockers": ["pit_taxonomy_denominator_path_missing"],
            "industry_filter_usable": False,
            "post_cutoff_refetch_forbidden": True,
        }
    try:
        denominator_payload = validate_prospective_pit_denominator(
            Path(denominator_path_value),
            now=observed,
        )
        denominator_symbols_value = denominator_payload.get("symbols")
        if not isinstance(denominator_symbols_value, list):
            raise PITTaxonomySourceError("verified denominator does not expose symbols")
        denominator_symbols = tuple(str(item) for item in denominator_symbols_value)
        target_date = observed.astimezone(TAIPEI).date()
        parent = _find_rule_source_parent(
            publication_root,
            target_date=target_date,
        )
        if not split_denominator_contract and tuple(parent["expected_symbols"]) != denominator_symbols:
            raise PITTaxonomySourceError(
                "rule parent full symbols differ from verified denominator"
            )
        raw_payloads, company_http, archive_lineage = _load_archived_company_sources(
            Path(str(archive_manifest_path))
        )
        if config_path is None and not os.environ.get(PIT_TAXONOMY_SOURCE_CONFIG_ENV, "").strip():
            raise PITTaxonomySourceError(
                f"{PIT_TAXONOMY_SOURCE_CONFIG_ENV} is not configured"
            )
        config = load_pit_taxonomy_source_config(config_path)
        if injected_clock and fetch_source is None and _config_contains_url(config):
            return {
                "status": "skipped_injected_clock",
                "reason": "network taxonomy source fetch is disabled for an injected test clock",
                "source_config_path": str(config_path.resolve()) if config_path else os.environ.get(PIT_TAXONOMY_SOURCE_CONFIG_ENV),
                "archive": archive_lineage,
                "post_cutoff_refetch_forbidden": True,
                "industry_filter_usable": False,
            }
        scope_binding = (
            _build_split_scope_binding(
                publication_root=publication_root,
                denominator_path=Path(denominator_path_value),
                denominator_payload=denominator_payload,
                parent=parent,
                capture_date=target_date,
                decision_at=datetime.combine(target_date, PIT_CUTOFF, tzinfo=TAIPEI),
                denominator_symbols=denominator_symbols,
            )
            if split_denominator_contract
            else None
        )
        result = capture_configured_daily_pit_taxonomy_bundle(
            config=config,
            bundle_root=(
                _split_taxonomy_bundle_root(publication_root, target_date)
                if split_denominator_contract
                else _taxonomy_bundle_root(publication_root, target_date)
            ),
            capture_date=target_date,
            decision_at=datetime.combine(target_date, PIT_CUTOFF, tzinfo=TAIPEI),
            now=observed,
            expected_symbols=(
                denominator_symbols
                if split_denominator_contract
                else parent["expected_symbols"]
            ),
            universe_hash=str(parent["universe_hash"]),
            universe_hash_symbols=parent["universe_hash_symbols"],
            scores_bp=parent["scores_bp"],
            rank_order=parent["rank_order"],
            clock_id=str(parent["clock_id"]),
            clock_manifest_hash=str(parent["clock_manifest_hash"]),
            clock_payload=parent["clock"],
            universe_identity_payload=parent["identity"],
            company_raw_payloads=raw_payloads,
            company_http=company_http,
            universe_symbols_payload=parent["symbols_payload"],
            scope_binding=scope_binding,
            fetch_source=fetch_source,
            now_provider=now_provider,
            capture_attempt_id=capture_attempt_id,
        )
        result_payload = result.to_dict()
        proof_source = config_path or _env_path(PIT_TAXONOMY_SOURCE_CONFIG_ENV)
        if (
            split_denominator_contract and not injected_clock
            and proof_source is not None
            and proof_source.resolve() == (ROOT / PIT_TAXONOMY_LIVE_CONFIG_SOURCE_RELATIVE_PATH).resolve()
        ):
            proof_observed = (now_provider or (lambda: datetime.now(timezone.utc)))()
            result_payload["source_config_proof"] = _ensure_live_split_source_config_proof(
                publication_root=publication_root,
                bundle_path=Path(str(result_payload["bundle_manifest_path"])),
                config=config, config_path=proof_source, observed=proof_observed,
                now_provider=now_provider,
            )
        return {
            **result_payload,
            "status": "preopen_captured",
            "source_config_path": str(config_path.resolve()) if config_path else os.environ.get(PIT_TAXONOMY_SOURCE_CONFIG_ENV),
            "archive": archive_lineage,
            "parent_rule_source": {
                "bundle_root": parent["bundle_root"],
                "identity_path": parent["identity_path"],
                "clock_path": parent["clock_path"],
                "universe_hash": parent["universe_hash"],
                "universe_hash_symbols_count": len(parent["universe_hash_symbols"]),
                "scores_bp_count": len(parent["scores_bp"]),
                "rank_order_count": len(parent["rank_order"]),
                "rank_order_source": parent["rank_order_source"],
            },
            "post_cutoff_refetch_forbidden": True,
            "industry_filter_usable": False,
            "taxonomy_coverage_complete": (
                result.schema_version
                == "pit-industry-taxonomy-daily-bundle.v2"
            ),
            "rule_scope_compatible": (
                bool((scope_binding or {}).get("rule_scope_compatible"))
                if split_denominator_contract
                else None
            ),
            "candidate_only": True,
            "formal_consumer_compatible": False,
        }
    except (OSError, PITTaxonomySourceError, TypeError, ValueError) as error:
        attempt_value = getattr(error, "capture_attempt", None)
        return {
            "status": "blocked",
            "blockers": [
                "pit_taxonomy_preopen_capture_failed:"
                f"{type(error).__name__}:{str(error).splitlines()[0][:220]}"
            ],
            "post_cutoff_refetch_forbidden": True,
            "industry_filter_usable": False,
            **(
                {"capture_attempt": dict(attempt_value)}
                if isinstance(attempt_value, Mapping)
                else {}
            ),
        }


def _read_split_candidate_json(
    publication_root: Path,
    path: Path,
    *,
    label: str,
    max_bytes: int,
) -> tuple[dict[str, object], bytes]:
    _resolved, raw = _read_split_scope_proof_file(
        publication_root,
        path,
        label=label,
        max_bytes=max_bytes,
    )
    return _decode_json_object_no_duplicates(raw, label), raw


def _verify_split_candidate_company_archive(
    *,
    publication_root: Path,
    bundle_root: Path,
    archive_raw: Mapping[str, bytes],
    archive_http: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """將 bundle 實際使用的公司原始 bytes/HTTP 對回當日已驗 archive。"""

    raw_manifest, _ = _read_split_candidate_json(
        publication_root,
        bundle_root / "metadata" / "raw_manifest.json",
        label="reused split taxonomy raw manifest",
        max_bytes=16 * 1024 * 1024,
    )
    rows = raw_manifest.get("files")
    if not isinstance(rows, list):
        raise PITTaxonomySourceError("reused split taxonomy raw manifest has no files")
    by_source: dict[str, Mapping[str, object]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise PITTaxonomySourceError("reused split taxonomy raw manifest entry is invalid")
        source_id = row.get("source_id")
        if isinstance(source_id, str) and source_id in by_source:
            raise PITTaxonomySourceError("reused split taxonomy raw source id is duplicated")
        if isinstance(source_id, str):
            by_source[source_id] = row
    checked: dict[str, object] = {}
    for market, archive_bytes in archive_raw.items():
        definition = OFFICIAL_COMPANY_SOURCE_DEFINITIONS.get(market)
        if definition is None:
            raise PITTaxonomySourceError(f"reused archive market is unsupported: {market}")
        row = by_source.get(definition.source_id)
        if row is None:
            raise PITTaxonomySourceError(
                f"reused split taxonomy omits archived company source: {definition.source_id}"
            )
        relative = row.get("path")
        if not isinstance(relative, str) or not relative:
            raise PITTaxonomySourceError("reused split company raw path is invalid")
        _resolved, bundle_bytes = _read_split_scope_proof_file(
            publication_root,
            bundle_root / Path(relative),
            label=f"reused split company raw {market}",
            max_bytes=64 * 1024 * 1024,
        )
        expected_hash = _sha256_bytes(archive_bytes)
        if (
            bundle_bytes != archive_bytes
            or row.get("source_file_hash") != expected_hash
            or row.get("content_bytes") != len(archive_bytes)
            or row.get("http") != dict(archive_http.get(market, {}))
        ):
            raise PITTaxonomySourceError(
                f"reused split company raw/HTTP differs from verified archive: {market}"
            )
        checked[market] = {
            "source_id": definition.source_id,
            "source_file_hash": expected_hash,
            "content_bytes": len(archive_bytes),
            "requested_url": archive_http.get(market, {}).get("requested_url"),
        }
    if set(archive_raw) != {"twse", "tpex"}:
        raise PITTaxonomySourceError("reused PIT archive must contain both TWSE and TPEx")
    return checked


def _config_expected_urls(config: Mapping[str, object]) -> dict[str, str]:
    urls: dict[str, str] = {}
    classification = config.get("classification")
    security = config.get("security")
    inactive = config.get("inactive_security", {})
    if not isinstance(classification, Mapping) or not isinstance(security, Mapping):
        raise PITTaxonomySourceError("reused source config sections are invalid")
    if not isinstance(inactive, Mapping):
        raise PITTaxonomySourceError("reused inactive source config is invalid")
    for market, spec in classification.items():
        if not isinstance(spec, Mapping):
            raise PITTaxonomySourceError("reused classification source spec is invalid")
        components = spec.get("components")
        if isinstance(components, Mapping):
            for component_name, component in components.items():
                if not isinstance(component, Mapping):
                    raise PITTaxonomySourceError("reused classification component is invalid")
                source_name = f"classification:{market}:{component_name}"
                url = component.get("url")
                http = component.get("http")
                if not isinstance(url, str) and isinstance(http, Mapping):
                    url = http.get("requested_url")
                if isinstance(url, str):
                    urls[source_name] = url
        else:
            url = spec.get("url")
            http = spec.get("http")
            if not isinstance(url, str) and isinstance(http, Mapping):
                url = http.get("requested_url")
            if isinstance(url, str):
                urls[f"classification:{market}"] = url
    for key, spec in security.items():
        if not isinstance(spec, Mapping):
            raise PITTaxonomySourceError("reused security source spec is invalid")
        url = spec.get("url")
        http = spec.get("http")
        if not isinstance(url, str) and isinstance(http, Mapping):
            url = http.get("requested_url")
        if isinstance(url, str):
            urls[f"security:{key}"] = url
    for key, spec in inactive.items():
        if not isinstance(spec, Mapping):
            raise PITTaxonomySourceError("reused inactive security spec is invalid")
        url = spec.get("source_url")
        if isinstance(url, str):
            urls[f"inactive_security:{key}"] = url
            urls[f"inactive_security:{key}:capture_metadata"] = url
    return urls


def _verify_reused_attempt_source_config(
    *,
    attempt: Mapping[str, object],
    descriptor: Mapping[str, object],
    config: Mapping[str, object],
    company_raw: Mapping[str, bytes],
    capture_date: date,
) -> None:
    expected_plan = _plan_configured_components(config, company_raw, capture_date)
    if descriptor.get("planned_sources") != expected_plan:
        raise PITTaxonomySourceError("reused split attempt source plan differs from current config")
    components = attempt.get("components")
    if not isinstance(components, list) or len(components) != len(expected_plan):
        raise PITTaxonomySourceError("reused split attempt components differ from current source plan")
    expected_urls = _config_expected_urls(config)
    for plan_item, component in zip(expected_plan, components):
        if not isinstance(plan_item, Mapping) or not isinstance(component, Mapping):
            raise PITTaxonomySourceError("reused split attempt component is invalid")
        source_name = str(plan_item.get("source_name"))
        if component.get("source_name") != source_name:
            raise PITTaxonomySourceError("reused split attempt component order/name differs")
        metadata = component.get("http_metadata")
        if not isinstance(metadata, Mapping):
            raise PITTaxonomySourceError("reused split attempt HTTP metadata is missing")
        expected_url = expected_urls.get(source_name)
        if expected_url is not None and metadata.get("requested_url") != expected_url:
            raise PITTaxonomySourceError(
                f"reused split attempt URL differs from source config: {source_name}"
            )
        if plan_item.get("mode") == "url" and expected_url is None:
            raise PITTaxonomySourceError(
                f"reused configured URL is absent from current config: {source_name}"
            )


def _ensure_live_split_source_config_proof(
    *, publication_root: Path, bundle_path: Path,
    config: Mapping[str, object], config_path: Path | None,
    observed: datetime, now_provider: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """只為正式 live 設定補同日 hash-matched proof；其他錯誤不重建。"""
    try:
        return read_existing_split_source_config_proof(
            publication_root=publication_root, bundle_manifest_path=bundle_path,
            repository_root=ROOT, current_config=config, now=observed,
        )
    except PITTaxonomySourceError as error:
        source = config_path or _env_path(PIT_TAXONOMY_SOURCE_CONFIG_ENV)
        if (
            str(error) != "late source config proof is missing"
            or source is None
            or source.resolve() != (ROOT / PIT_TAXONOMY_LIVE_CONFIG_SOURCE_RELATIVE_PATH).resolve()
        ):
            raise
        materialize_existing_split_source_config_proof(
            publication_root=publication_root, bundle_manifest_path=bundle_path,
            source_config_path=source, repository_root=ROOT,
            materialized_at=observed, now_provider=now_provider,
        )
        completed = (now_provider or (lambda: datetime.now(timezone.utc)))()
        return read_existing_split_source_config_proof(
            publication_root=publication_root, bundle_manifest_path=bundle_path,
            repository_root=ROOT, current_config=config, now=completed,
        )


def _reuse_existing_split_taxonomy_candidate(
    *,
    publication_root: Path,
    observed: datetime,
    config_path: Path | None,
    now_provider: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """完整重驗當日既有 split candidate；此分支絕不擷取或覆寫 source。"""

    local_date = observed.astimezone(TAIPEI).date()
    cutoff = datetime.combine(local_date, PIT_CUTOFF, tzinfo=TAIPEI)
    if observed >= cutoff:
        raise PITTaxonomySourceError(
            "same-day split candidate reuse is only allowed before Taipei 08:30"
        )
    root = publication_root.expanduser().resolve(strict=True)
    bundle_root = _split_taxonomy_bundle_root(root, local_date)
    _assert_no_link_path(bundle_root, allow_missing=False, confine_to=root)
    bundle_path = bundle_root / "bundle_manifest.json"
    config = load_pit_taxonomy_source_config(config_path, bounded_read=True)
    config_proof = _ensure_live_split_source_config_proof(
        publication_root=root, bundle_path=bundle_path,
        config=config, config_path=config_path, observed=observed,
        now_provider=now_provider,
    )
    proof_config = config_proof.get("config")
    if not isinstance(proof_config, Mapping):
        raise PITTaxonomySourceError("late-bound source config proof has no config body")

    # Existing archive readback is read-only. Missing or invalid inputs fail
    # here; this branch never falls through to a new archive or HTTP request.
    archive_result = reuse_pit_candidate_archive_before_cutoff(
        publication_root=root,
        now=observed,
    )
    archive_value = archive_result.get("durable_archive")
    if not isinstance(archive_value, Mapping) or archive_result.get("durable_archive_verified") is not True:
        raise PITTaxonomySourceError("same-day PIT archive is not an existing verified archive")
    archive_path = Path(str(archive_value.get("archive_manifest_path"))).expanduser()
    archive_raw, archive_http, archive_lineage = _load_archived_company_sources(archive_path)
    company_binding = _verify_split_candidate_company_archive(
        publication_root=root,
        bundle_root=bundle_root,
        archive_raw=archive_raw,
        archive_http=archive_http,
    )

    denominator_path, denominator_lookup = _find_verified_denominator(
        root,
        target_date=observed,
    )
    if denominator_path is None:
        raise PITTaxonomySourceError(
            f"same-day verified PIT denominator is missing: {denominator_lookup}"
        )
    denominator = validate_prospective_pit_denominator(denominator_path, now=observed)
    denominator_symbols = denominator.get("symbols")
    if not isinstance(denominator_symbols, list):
        raise PITTaxonomySourceError("same-day verified denominator symbols are missing")
    parent = _find_rule_source_parent(root, target_date=local_date)
    current_binding = _build_split_scope_binding(
        publication_root=root,
        denominator_path=denominator_path,
        denominator_payload=denominator,
        parent=parent,
        capture_date=local_date,
        decision_at=cutoff,
        denominator_symbols=tuple(str(item) for item in denominator_symbols),
    )
    validated = validate_daily_pit_taxonomy_bundle(
        bundle_path,
        decision_at=cutoff,
        now=observed,
    )
    bundle, _ = _read_split_candidate_json(
        root,
        bundle_path,
        label="reused split taxonomy bundle manifest",
        max_bytes=16 * 1024 * 1024,
    )
    for key in (
        "scope_binding_schema_version",
        "denominator_binding",
        "rule_candidate_binding",
        "scope_diff",
        "taxonomy_coverage_complete",
        "rule_scope_compatible",
    ):
        if bundle.get(key) != current_binding.get(key):
            raise PITTaxonomySourceError(f"current split binding differs from candidate: {key}")
    if (
        bundle.get("symbols") != list(denominator_symbols)
        or bundle.get("universe_hash") != parent["universe_hash"]
        or bundle.get("universe_hash_symbols") != list(parent["universe_hash_symbols"])
        or bundle.get("scores_bp") != list(parent["scores_bp"])
        or bundle.get("rank_order") != list(parent["rank_order"])
        or bundle.get("clock_id") != parent["clock_id"]
        or bundle.get("clock_manifest_hash") != parent["clock_manifest_hash"]
    ):
        raise PITTaxonomySourceError(
            "current full Rule score/clock tuple differs from split candidate"
        )
    binding = bundle.get("capture_attempt_binding")
    if not isinstance(binding, Mapping):
        raise PITTaxonomySourceError("reused split candidate attempt binding is missing")
    attempt_path = _proof_child(
        root,
        binding.get("path"),
        required_prefix=f"pit_taxonomy_capture_attempts/{local_date.isoformat()}/",
        label="reused split candidate attempt",
    )
    attempt = read_pit_taxonomy_capture_attempt(attempt_path, verify_complete=True)
    attempt_descriptor_path = attempt_path / "attempt_descriptor.json"
    descriptor_raw = _proof_file_bytes(
        attempt_descriptor_path,
        "reused split attempt descriptor",
        1024 * 1024,
    )
    descriptor = _decode_json_object_no_duplicates(
        descriptor_raw,
        "reused split attempt descriptor",
    )
    _verify_reused_attempt_source_config(
        attempt=attempt,
        descriptor=descriptor,
        config=proof_config,
        company_raw=archive_raw,
        capture_date=local_date,
    )
    refreshed = (now_provider or (lambda: datetime.now(timezone.utc)))()
    if refreshed.astimezone(TAIPEI).date() != local_date or refreshed >= cutoff:
        raise PITTaxonomySourceError(
            "same-day split validation finished outside Taipei 08:30 cutoff"
        )
    return {
        "status": "verified_reused_existing_split_candidate",
        "taxonomy_bundle_path": str(bundle_path),
        "validation_completed_at": refreshed.isoformat(),
        "bundle_hash": bundle.get("bundle_hash"),
        "capture_date": local_date.isoformat(),
        "archive": archive_lineage,
        "company_archive_binding": company_binding,
        "denominator_path": str(denominator_path),
        "rule_parent_root": parent["bundle_root"],
        "rule_universe_hash": parent["universe_hash"],
        "capture_attempt_id": attempt.get("attempt_id"),
        "capture_attempt_status": attempt.get("status"),
        "source_config_proof_sha256": config_proof.get("proof_sha256"),
        "source_config_proof_materialized_at": config_proof.get("materialized_at"),
        "taxonomy_coverage_complete": validated.get("taxonomy_coverage_complete") is True,
        "rule_scope_compatible": validated.get("rule_scope_compatible") is True,
        "formal_consumer_compatible": False,
        "formal_credit": False,
        "research_only": True,
        "candidate_only": True,
        "network_attempted": False,
        "new_attempt_created": False,
    }


def run_capture(
    *,
    publication_root: Path,
    status_root: Path,
    now: datetime | None = None,
    taxonomy_config_path: Path | None = None,
    split_denominator_contract: bool = False,
    taxonomy_fetch_source: Callable[[str], object] | None = None,
    taxonomy_now_provider: Callable[[], datetime] | None = None,
) -> tuple[dict[str, object], int]:
    injected_clock = now is not None
    observed = now or datetime.now(timezone.utc)
    split_bundle_root = (
        _split_taxonomy_bundle_root(
            publication_root,
            observed.astimezone(TAIPEI).date(),
        )
        if split_denominator_contract
        else None
    )
    split_candidate_exists = False
    split_candidate_precheck_error: str | None = None
    if split_bundle_root is not None:
        try:
            _assert_no_link_path(
                split_bundle_root,
                allow_missing=True,
                confine_to=publication_root.expanduser().resolve(),
            )
            split_candidate_exists = (
                split_bundle_root.exists() or split_bundle_root.is_symlink()
            )
        except (OSError, TypeError, ValueError, PITTaxonomySourceError) as error:
            split_candidate_precheck_error = (
                f"{type(error).__name__}:{str(error).splitlines()[0][:220]}"
            )
            split_candidate_exists = True
    capture_attempt_id = (
        uuid.uuid4().hex
        if split_denominator_contract and not split_candidate_exists
        else None
    )
    # Operational consumers are pinned to this stable readback path for both
    # legacy and split-contract runs.  One-off validation runs can isolate the
    # whole status root with --status-root instead of changing this contract.
    status_path = status_root / "latest_status.json"
    calendar_state, calendar_reason = formal_schedule_day_state(
        observed=observed,
        market_db=_env_path("FORMAL_DAILY_MARKET_DB"),
        calendar_cache_root=(
            _env_path("FORMAL_DAILY_CALENDAR_CACHE_ROOT")
            or ROOT / "output" / "paper_execution_eod_replay" / "calendar_cache"
        ),
    )
    runtime_config: dict[str, object] | None = None
    runtime_config_error: str | None = None
    if calendar_state is True:
        try:
            runtime_config = load_optional_formal_runtime_config(
                role="pit_preopen_wrapper",
                observed=observed,
            )
        except FormalRuntimeConfigError as error:
            runtime_config_error = str(error)
    base: dict[str, object] = {
        "schema_version": "pit-preopen-capture-scheduled-status.v1",
        "task": TASK_NAME,
        "producer": "data_module.formal_daily_input_producer.capture_pit_candidate_before_cutoff",
        "observed_at": observed.isoformat(),
        "publication_root": str(publication_root),
        "status_path": str(status_path),
        **(
            {"capture_attempt_id": capture_attempt_id}
            if capture_attempt_id is not None
            else {}
        ),
        "capture_policy": "capture_before_taipei_0830_then_read_archive_after_cutoff",
        "post_cutoff_refetch_forbidden": True,
        "candidate_only": True,
        "formal_ready": False,
        "formal_consumer_compatible": False,
        "formal_oos_allowed": False,
        "promotion_eligible": False,
        "production_action_allowed": False,
        "broker_order_allowed": False,
        "writes_source_database": False,
        "writes_formal_controlled_paths": False,
        "training_started": False,
        "broker_execution": False,
        "historical_backfill_claimed": False,
        "calendar": {
            "date": observed.astimezone(TAIPEI).date().isoformat(),
            "is_official_trading_day": calendar_state,
            "reason": calendar_reason,
        },
        "formal_runtime_config": (
            runtime_config
            if runtime_config is not None
            else {
                "status": "absent" if runtime_config_error is None else "invalid",
                "environment_variable": FORMAL_RUNTIME_CONFIG_ENV,
                "error": runtime_config_error,
            }
        ),
    }
    if calendar_state is False:
        payload = {
            **base,
            "status": "skipped_non_trading_day",
            "reason": calendar_reason,
            "blockers": [],
        }
        _write_status(status_path, payload)
        return payload, 0
    if calendar_state is None:
        payload = {
            **base,
            "status": "blocked",
            "blockers": [f"official_calendar_unresolved:{calendar_reason}"],
        }
        _write_status(status_path, payload)
        return payload, 2
    if runtime_config_error is not None:
        payload = {
            **base,
            "status": "blocked",
            "blockers": [f"runtime_config_invalid:{runtime_config_error}"],
        }
        _write_status(status_path, payload)
        return payload, 2
    if runtime_config is not None and runtime_config.get("activation_status") != "active":
        payload = {
            **base,
            "status": "waiting_for_runtime_config",
            "blockers": [
                "runtime_config_waiting_for_activation:"
                f"{runtime_config.get('activation_trading_day')}"
            ],
        }
        _write_status(status_path, payload)
        return payload, 2
    if split_denominator_contract and split_candidate_exists:
        if injected_clock:
            payload = {
                **base,
                "status": "blocked",
                "capture_mode": "reused_existing_split_candidate_blocked",
                "blockers": [
                    "existing_split_candidate_reuse_requires_actual_operational_clock"
                ],
                "capture": {},
                "network_attempted": False,
                "new_attempt_created": False,
            }
            _write_status(status_path, payload)
            return payload, 2
        try:
            if split_candidate_precheck_error is not None:
                raise PITTaxonomySourceError(
                    f"existing split candidate root failed path validation: {split_candidate_precheck_error}"
                )
            taxonomy = _reuse_existing_split_taxonomy_candidate(
                publication_root=publication_root,
                observed=observed,
                config_path=taxonomy_config_path,
                now_provider=taxonomy_now_provider or (lambda: datetime.now(timezone.utc)),
            )
            taxonomy_archive = taxonomy.get("archive")
            archive_manifest_path = (
                taxonomy_archive.get("manifest_path")
                if isinstance(taxonomy_archive, Mapping)
                else None
            )
            payload = {
                **base,
                "status": "machine_verified_candidate",
                "capture_mode": "reused_existing_split_candidate",
                "capture": {"status": "existing_verified_archive_readback"},
                "archive_manifest_path": archive_manifest_path,
                "archive_readback_verified": True,
                "denominator_refresh": {
                    "status": "existing_verified",
                    "path": taxonomy.get("denominator_path"),
                    "network_attempted": False,
                },
                "taxonomy": taxonomy,
                "taxonomy_observed_at": str(
                    taxonomy.get("validation_completed_at") or observed.isoformat()
                ),
                "taxonomy_bundle_path": taxonomy.get("taxonomy_bundle_path"),
                "taxonomy_industry_filter_usable": False,
                "blockers": [],
            }
            _write_status(status_path, payload)
            return payload, 0
        except Exception as error:  # noqa: BLE001 - present candidate never falls through
            payload = {
                **base,
                "status": "blocked",
                "capture_mode": "reused_existing_split_candidate_blocked",
                "blockers": [
                    "existing_split_candidate_reuse_rejected:"
                    f"{type(error).__name__}:{str(error).splitlines()[0][:220]}"
                ],
                "capture": {},
                "network_attempted": False,
                "new_attempt_created": False,
            }
            _write_status(status_path, payload)
            return payload, 2
    try:
        try:
            result = reuse_pit_candidate_archive_before_cutoff(
                publication_root=publication_root,
                now=observed,
            )
            capture_mode = "reused_existing_verified_archive"
        except FormalDailyInputProducerError as error:
            # A missing current-day archive is the only condition that permits
            # the one live preopen capture.  A present but invalid archive must
            # remain fail-closed instead of being hidden by a second capture.
            if not str(error).startswith("PIT preopen archive is missing for "):
                raise
            result = capture_pit_candidate_before_cutoff(
                publication_root=publication_root,
                now=observed,
            )
            capture_mode = "new_live_capture"
        denominator = _refresh_pit_denominator(
            publication_root=publication_root,
            observed=observed,
            allow_network=not injected_clock,
        )
        archive_value = result.get("durable_archive")
        archive_info = (
            {str(key): value for key, value in archive_value.items()}
            if isinstance(archive_value, Mapping)
            else None
        )
        # denominator／archive 含本次 HTTP 完成時間，不能拿啟動前的時鐘驗證。
        # 真實執行重讀時鐘；fixture 保留注入時鐘，cutoff 仍由 producer 強制。
        taxonomy_observed = observed if injected_clock else datetime.now(timezone.utc)
        taxonomy = _capture_taxonomy_for_run(
            publication_root=publication_root,
            observed=taxonomy_observed,
            denominator=denominator,
            archive_manifest_path=(
                archive_info.get("archive_manifest_path")
                if archive_info is not None
                else None
            ),
            injected_clock=injected_clock,
            split_denominator_contract=split_denominator_contract,
            capture_attempt_id=capture_attempt_id,
            config_path=taxonomy_config_path,
            fetch_source=taxonomy_fetch_source,
            now_provider=taxonomy_now_provider,
        )
        component_blocked = denominator.get("status") == "blocked" or taxonomy.get("status") == "blocked"
        taxonomy_blockers = taxonomy.get("blockers")
        blockers = (
            [str(value) for value in taxonomy_blockers]
            if isinstance(taxonomy_blockers, (list, tuple)) else []
        )
        payload = {
            **base,
            "status": "degraded" if component_blocked else "machine_verified_candidate",
            "capture": result,
            "archive_manifest_path": archive_info.get("archive_manifest_path")
            if archive_info is not None
            else None,
            "archive_readback_verified": result.get("durable_archive_verified") is True,
            "capture_mode": capture_mode,
            "denominator_refresh": denominator,
            "taxonomy": taxonomy,
            "taxonomy_observed_at": taxonomy_observed.isoformat(),
            "blockers": blockers + (
                [str(denominator.get("reason") or "pit_denominator_blocked")]
                if denominator.get("status") == "blocked" else []
            ),
            "taxonomy_bundle_path": taxonomy.get("bundle_manifest_path"),
            "taxonomy_industry_filter_usable": taxonomy.get(
                "industry_filter_usable"
            ) is True,
        }
        _write_status(status_path, payload)
        return payload, 2 if component_blocked else 0
    except Exception as error:  # noqa: BLE001 - scheduled boundary is fail closed
        payload = {
            **base,
            "status": "blocked",
            "blockers": [
                f"pit_preopen_capture_failed:{type(error).__name__}:{str(error).splitlines()[0][:220]}"
            ],
            "capture": {},
        }
        _write_status(status_path, payload)
        return payload, 2


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        publication_root = _publication_root(args.publication_root)
        if args.materialize_existing_split_config_proof:
            if args.split_denominator_contract or args.status_root is not None:
                raise ValueError(
                    "late source config proof mode cannot be combined with capture/status options"
                )
            source_config_path = (
                args.source_config_proof_source
                or ROOT / Path(PIT_TAXONOMY_LATE_CONFIG_SOURCE_RELATIVE_PATH)
            )
            materialization_started_at = datetime.now(timezone.utc)
            payload = materialize_existing_split_source_config_proof(
                publication_root=publication_root,
                bundle_manifest_path=(
                    publication_root
                    / "pit_taxonomy_preopen_split_v2"
                    / materialization_started_at.astimezone(TAIPEI).date().isoformat()
                    / "bundle_manifest.json"
                ),
                source_config_path=source_config_path,
                repository_root=ROOT,
                materialized_at=materialization_started_at,
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.source_config_proof_source is not None:
            raise ValueError(
                "--source-config-proof-source requires --materialize-existing-split-config-proof"
            )
        status_root = _status_root(publication_root, args.status_root)
        payload, exit_code = run_capture(
            publication_root=publication_root,
            status_root=status_root,
            split_denominator_contract=args.split_denominator_contract,
        )
    except (OSError, TypeError, ValueError, FormalDailyInputProducerError) as error:
        payload = {
            "schema_version": "pit-preopen-capture-scheduled-status.v1",
            "task": TASK_NAME,
            "status": "blocked",
            "blockers": [
                f"pit_preopen_capture_configuration_failed:{type(error).__name__}:{str(error).splitlines()[0][:220]}"
            ],
            "candidate_only": True,
            "formal_ready": False,
            "formal_oos_allowed": False,
            "production_action_allowed": False,
        }
        exit_code = 2
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
