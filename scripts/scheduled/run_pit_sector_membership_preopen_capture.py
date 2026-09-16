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
    PIT_TAXONOMY_SOURCE_CONFIG_ENV,
    PITTaxonomySourceError,
    capture_configured_daily_pit_taxonomy_bundle,
    load_pit_taxonomy_source_config,
)
from data_module.prospective_formal_clock import canonical_json  # noqa: E402
from scripts.capture_pit_prospective_denominator import (  # noqa: E402
    capture_live_denominator,
)


TASK_NAME = "baldr-pit-sector-membership-preopen-capture-daily"
DEFAULT_PUBLICATION_ROOT = ROOT / "output" / "formal_daily_publications"
TAIPEI = ZoneInfo("Asia/Taipei")
PIT_CUTOFF = time(8, 30)
RULE_SOURCE_ROOT_ENV = "FORMAL_DAILY_RULE_SOURCE_ROOT"
PIT_TAXONOMY_PREOPEN_ROOT_ENV = "PIT_TAXONOMY_PREOPEN_ROOT"


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
        if tuple(parent["expected_symbols"]) != denominator_symbols:
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
        result = capture_configured_daily_pit_taxonomy_bundle(
            config=config,
            bundle_root=_taxonomy_bundle_root(publication_root, target_date),
            capture_date=target_date,
            decision_at=datetime.combine(target_date, PIT_CUTOFF, tzinfo=TAIPEI),
            now=observed,
            expected_symbols=parent["expected_symbols"],
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
            fetch_source=fetch_source,
            now_provider=now_provider,
        )
        return {
            **result.to_dict(),
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
        }
    except (OSError, PITTaxonomySourceError, TypeError, ValueError) as error:
        return {
            "status": "blocked",
            "blockers": [
                "pit_taxonomy_preopen_capture_failed:"
                f"{type(error).__name__}:{str(error).splitlines()[0][:220]}"
            ],
            "post_cutoff_refetch_forbidden": True,
            "industry_filter_usable": False,
        }


def run_capture(
    *,
    publication_root: Path,
    status_root: Path,
    now: datetime | None = None,
    taxonomy_config_path: Path | None = None,
    taxonomy_fetch_source: Callable[[str], object] | None = None,
    taxonomy_now_provider: Callable[[], datetime] | None = None,
) -> tuple[dict[str, object], int]:
    injected_clock = now is not None
    observed = now or datetime.now(timezone.utc)
    status_path = status_root / "latest_status.json"
    runtime_config: dict[str, object] | None = None
    runtime_config_error: str | None = None
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
        taxonomy = _capture_taxonomy_for_run(
            publication_root=publication_root,
            observed=observed,
            denominator=denominator,
            archive_manifest_path=(
                archive_info.get("archive_manifest_path")
                if archive_info is not None
                else None
            ),
            injected_clock=injected_clock,
            config_path=taxonomy_config_path,
            fetch_source=taxonomy_fetch_source,
            now_provider=taxonomy_now_provider,
        )
        payload = {
            **base,
            "status": "machine_verified_candidate",
            "capture": result,
            "archive_manifest_path": archive_info.get("archive_manifest_path")
            if archive_info is not None
            else None,
            "archive_readback_verified": result.get("durable_archive_verified") is True,
            "capture_mode": capture_mode,
            "denominator_refresh": denominator,
            "taxonomy": taxonomy,
            "taxonomy_bundle_path": taxonomy.get("bundle_manifest_path"),
            "taxonomy_industry_filter_usable": taxonomy.get(
                "industry_filter_usable"
            ) is True,
        }
        _write_status(status_path, payload)
        return payload, 2 if denominator.get("status") == "blocked" else 0
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
        status_root = _status_root(publication_root, args.status_root)
        payload, exit_code = run_capture(
            publication_root=publication_root,
            status_root=status_root,
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
