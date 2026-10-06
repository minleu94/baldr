"""保留 bounded 股票修訂，另以官方市場重建特徵與成熟標籤。"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import date, datetime, time, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

from data_module.bounded_allocation_full_feature_restatement import (
    FULL_RESTATEMENT_SCHEMA, RESEARCH_JSONL_SCHEMA, RESEARCH_PUBLICATION_SCHEMA,
    TECHNICAL_FEATURE_IDS, _restated_feature_registry,
)
from data_module.bounded_allocation_label_restatement import (
    BoundedRestatementError, _canonical_json, _file_sha256, _recompute_label,
    _scaled_bar, _sha256_json, _write_json,
)
from data_module.ml_restatement_official_market import load_official_market_capture
from data_module.ml_restatement_research_dataset import build_restated_feature_values, expected_feature_contract
from data_module.ml_restatement_research_dataset_v3 import MARKET_SOURCE_CONTRACT
from data_module.portfolio_ml_dataset_assembler import _load_corporate_action_custody
from ml_module.restated_research_input_contract import OFFICIAL_MARKET_CONTRACT_HASH


OFFICIAL_RESTATEMENT_SCHEMA = "bounded-allocation-official-market-restatement.v1"
OFFICIAL_FOLD_PROFILE = "restated_official_market_event_maturity.v1"
MARKET_SOURCE_ID = "official.twse_market"
MARKET_QUALITY_SOURCE_ID = "derived:official_market_quality"
_RUN02_CANDIDATE_SNAPSHOT_SHA256 = (
    "sha256:05658755b956680a614aa67fa481971abe83c649e2ea7b39202e3486e232cd65"
)
FEATURE_NAMES, FEATURE_SCALES = expected_feature_contract()
MARKET_FEATURE_IDS = frozenset(FEATURE_NAMES[:5] + FEATURE_NAMES[13:21])
MARKET_RAW_IDS = frozenset(FEATURE_NAMES[13:21])
_TAIPEI = ZoneInfo("Asia/Taipei")
_DEPENDENCIES = (
    "data_module/bounded_official_market_restatement.py",
    "data_module/bounded_allocation_label_restatement.py",
    "data_module/bounded_allocation_full_feature_restatement.py",
    "data_module/portfolio_ml_dataset_assembler.py",
    "data_module/ml_restatement_research_dataset.py",
    "data_module/ml_restatement_official_market.py",
    "utils/numeric_text.py",
)
_CANDIDATE_DEPENDENCIES = (
    "data_module/bounded_candidate_stock_source.py",
    "data_module/ml_restatement_research_candidate_source.py",
    "data_module/excluded_daily_price_revision.py",
    "analysis_module/technical_analysis/technical_indicators.py",
    "analysis_module/technical_analysis/indicator_kernels.py",
)


def _source_hashes(*, candidate_stock: bool = False) -> dict[str, str]:
    root = Path(__file__).resolve().parents[1]
    dependencies = _DEPENDENCIES + (_CANDIDATE_DEPENDENCIES if candidate_stock else ())
    return {relative: _file_sha256(root / relative) for relative in dependencies}


def _require_candidate_profile_for_snapshot(
    expected_snapshot_hash: str,
    *,
    candidate_stock: bool,
) -> None:
    """Prevent run02 from silently taking the older market-only route."""
    if expected_snapshot_hash == _RUN02_CANDIDATE_SNAPSHOT_SHA256 and not candidate_stock:
        raise ValueError(
            "run02 bounded candidate snapshot requires the verified daily-source profile"
        )


def official_feature_registry(parent: Mapping[str, Any], market_hash: str) -> dict[str, Any]:
    registry = deepcopy(parent["feature_registry"])
    for definition in registry["features"]:
        if definition["feature_id"] in MARKET_RAW_IDS:
            previous = definition["record_hash"]
            definition.update(source_id=MARKET_SOURCE_ID, table_name="official_twse_market")
            definition["record_hash"] = _sha256_json({
                "schema_version": OFFICIAL_RESTATEMENT_SCHEMA,
                "prior_record_hash": previous, "feature_id": definition["feature_id"],
                "source_id": MARKET_SOURCE_ID, "table_name": "official_twse_market",
                "scale": definition["scale"], "market_source_contract": MARKET_SOURCE_CONTRACT,
                "official_market_manifest_hash": market_hash,
            })
    registry["features"].sort(key=lambda item: str(item["feature_id"]))
    return registry


def _bound_parent(path: Path, expected_hash: str) -> dict[str, Any]:
    from ml_module.bounded_restated_research_consumer import _verify_manifest

    if _file_sha256(path) != expected_hash:
        raise ValueError("bounded parent manifest file hash mismatch")
    parent = json.loads(path.read_text(encoding="utf-8"))
    _verify_manifest(path.parent, parent)
    if parent["restatement"]["schema_version"] != FULL_RESTATEMENT_SCHEMA:
        raise ValueError("official market restatement requires the stock-restated parent")
    if parent["feature_registry_hash"] != _sha256_json(parent["feature_registry"]):
        raise ValueError("bounded parent registry hash mismatch")
    return parent


def validate_official_bounded_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """新研究範圍有自己的來源、registry 與時鐘契約，不放寬舊 H60 修訂。"""
    restatement = manifest["restatement"]
    body = dict(manifest)
    claimed_hash = body.pop("manifest_hash", None)
    if (claimed_hash != _sha256_json(body) or manifest.get("schema_version") != RESEARCH_PUBLICATION_SCHEMA
        or manifest.get("research_only") is not True or manifest.get("production_alpha_bp") != 0
        or manifest.get("dataset_temporality") != "restated_research"
        or any(manifest.get(key) is not False for key in ("historical_pit", "formal_oos_allowed", "production_action_allowed", "promotion_eligible", "direct_training_input", "formal_consumer_compatible"))):
        raise ValueError("official bounded publication identity or research restrictions mismatch")
    if restatement.get("schema_version") != OFFICIAL_RESTATEMENT_SCHEMA:
        raise ValueError("official bounded schema mismatch")
    identity = restatement.get("identity_payload")
    if not isinstance(identity, dict) or manifest.get("dataset_identity_hash") != _sha256_json(identity):
        raise ValueError("official bounded dataset identity mismatch")
    base_identity_keys = {"schema_version", "market_source_contract", "fold_profile", "started_at", "revision_observed_at", "parent_manifest_path",
        "parent_manifest_file_sha256", "parent_training_as_of", "source_snapshot_sha256", "source_snapshot_path", "official_market_manifest_path",
        "official_market_manifest_file_sha256", "producer_code_root", "computation_source_hashes", "selection_policy",
        "corporate_action_manifest_path", "corporate_action_manifest_file_sha256"}
    identity_candidate_stock = identity.get("candidate_stock_source")
    candidate_stock = restatement.get("candidate_stock_source")
    if set(identity) != base_identity_keys | ({"candidate_stock_source"} if identity_candidate_stock is not None else set()):
        raise ValueError("official bounded identity fields differ from the fixed contract")
    _require_candidate_profile_for_snapshot(
        str(identity["source_snapshot_sha256"]),
        candidate_stock=isinstance(candidate_stock, dict) and isinstance(identity_candidate_stock, dict),
    )
    parent = _bound_parent(Path(identity["parent_manifest_path"]), identity["parent_manifest_file_sha256"])
    source = load_official_market_capture(
        Path(identity["official_market_manifest_path"]),
        expected_file_sha256=identity["official_market_manifest_file_sha256"],
        as_of=datetime.fromisoformat(manifest["training_as_of"]),
    )
    actions = _load_corporate_action_custody(Path(identity["corporate_action_manifest_path"]), training_as_of=datetime.fromisoformat(manifest["training_as_of"]))
    if (actions.manifest_file_hash != identity["corporate_action_manifest_file_sha256"]
        or actions.manifest_file_hash != parent["corporate_action_custody"]["manifest_file_hash"]
        or actions.custody_payload() != manifest["corporate_action_custody"]):
        raise ValueError("official bounded corporate action custody mismatch")
    if (
        identity.get("schema_version") != OFFICIAL_RESTATEMENT_SCHEMA
        or identity.get("market_source_contract") != MARKET_SOURCE_CONTRACT
        or identity.get("fold_profile") != OFFICIAL_FOLD_PROFILE
        or manifest.get("fold_profile") != OFFICIAL_FOLD_PROFILE
        or manifest["folds"] != parent["folds"]
        or manifest["row_feature_ids"] != parent["row_feature_ids"]
        or manifest["feature_packs"] != parent["feature_packs"]
        or manifest["horizons"] != [5, 10, 20, 60]
        or manifest["training_as_of"] != identity["revision_observed_at"]
        or manifest["revision_observed_at"] != identity["revision_observed_at"]
        or identity["parent_training_as_of"] != parent["training_as_of"]
        or identity["source_snapshot_sha256"] != parent["restatement"]["source_snapshot_sha256"]
        or manifest["observed_session_dates"] != [day.isoformat() for day in sorted(source.rows)]
    ):
        raise ValueError("official bounded source, fold, feature or clock contract mismatch")
    if not datetime.fromisoformat(parent["training_as_of"]) <= datetime.fromisoformat(identity["started_at"]) <= datetime.fromisoformat(manifest["training_as_of"]) <= datetime.fromisoformat(manifest["dataset_created_at"]) <= datetime.now(timezone.utc):
        raise ValueError("official bounded clock sequence mismatch")
    if source.available_at > datetime.fromisoformat(identity["started_at"]):
        raise ValueError("official source was not available at bounded build start")
    expected_dependencies = set(_DEPENDENCIES) | (set(_CANDIDATE_DEPENDENCIES) if candidate_stock is not None else set())
    if set(identity["computation_source_hashes"]) != expected_dependencies:
        raise ValueError("official bounded producer dependencies incomplete")
    for relative, digest in identity["computation_source_hashes"].items():
        if _file_sha256(Path(identity["producer_code_root"]) / relative) != digest:
            raise ValueError("official bounded producer source changed")
    registry = official_feature_registry(parent, source.manifest_file_sha256)
    expected_sources = dict(parent["source_manifest_hashes"])
    expected_sources.update({MARKET_SOURCE_ID: source.manifest_file_sha256,
        MARKET_QUALITY_SOURCE_ID: OFFICIAL_MARKET_CONTRACT_HASH,
        "contract.official_twse_market": OFFICIAL_MARKET_CONTRACT_HASH,
        "parent.bounded_stock_restatement": identity["parent_manifest_file_sha256"]})
    if candidate_stock is not None:
        if not isinstance(candidate_stock, dict) or set(candidate_stock) != {"mode", "profile", "bridge", "bridge_sha256"}:
            raise ValueError("candidate bounded stock source metadata differs from the fixed contract")
        if candidate_stock.get("mode") != "daily_source_rehydration.v1" or restatement.get("candidate_stock_source") != candidate_stock:
            raise ValueError("candidate bounded stock source transition is missing or inconsistent")
        profile_reference = candidate_stock.get("profile")
        bridge = candidate_stock.get("bridge")
        if not isinstance(profile_reference, dict) or set(profile_reference) != {"path", "file_sha256"} or not isinstance(bridge, dict):
            raise ValueError("candidate bounded stock source profile or bridge is malformed")
        from data_module.bounded_candidate_stock_source import (
            candidate_stock_feature_registry,
            validate_candidate_stock_source_bridge,
        )
        from data_module.ml_restatement_research_candidate_source import verify_candidate_source_profile

        profile = verify_candidate_source_profile(
            Path(profile_reference["path"]),
            str(profile_reference["file_sha256"]),
            as_of=datetime.fromisoformat(manifest["training_as_of"]),
        )
        if (
            profile.snapshot_db.resolve() != Path(identity["source_snapshot_path"]).resolve()
            or profile.snapshot_sha256 != identity["source_snapshot_sha256"]
            or profile.market_manifest.resolve() != source.manifest_path.resolve()
            or profile.market_sha256 != source.manifest_file_sha256
            or identity_candidate_stock != candidate_stock
        ):
            raise ValueError("candidate stock profile is not bound to the official snapshot/capture")
        bridge_hash = validate_candidate_stock_source_bridge(
            bridge,
            profile=profile,
            profile_sha256=str(profile_reference["file_sha256"]),
            revision_observed_at=identity["revision_observed_at"],
        )
        if bridge_hash != candidate_stock.get("bridge_sha256"):
            raise ValueError("candidate stock source identity or bridge hash mismatch")
        registry = candidate_stock_feature_registry(
            registry,
            profile_sha256=profile.profile_file_sha256,
            bridge_hash=bridge_hash,
        )
        expected_sources.update({
            "candidate.stock_source_profile": profile.profile_file_sha256,
            "contract.candidate_daily_source_bridge": bridge_hash,
        })
    if registry != manifest["feature_registry"] or _sha256_json(registry) != manifest["feature_registry_hash"]:
        raise ValueError("official bounded registry differs from the fixed source-only revision")
    if manifest["source_manifest_hashes"] != [list(pair) for pair in sorted(expected_sources.items())]:
        raise ValueError("official bounded source aliases mismatch")
    excluded = restatement.get("excluded_rows")
    if not isinstance(excluded, list) or len({item["row_id"] for item in excluded}) != len(excluded):
        raise ValueError("official bounded excluded rows must be unique explicit records")
    if manifest["sample_count"] + len(excluded) != parent["sample_count"]:
        raise ValueError("official bounded retained and excluded row accounting mismatch")
    return parent


def validate_official_registry_bridge(manifest: Mapping[str, Any], current_registry_hash: str) -> dict[str, object]:
    parent = validate_official_bounded_manifest(manifest)
    original = parent["feature_registry_transition"]["original_registry"]
    if _sha256_json(original) != current_registry_hash:
        raise ValueError("official bounded current registry differs from original numeric ABI")
    expected_stock = _restated_feature_registry(original, kernel_hash=parent["restatement"]["kernel_source_hashes"])
    if expected_stock != parent["feature_registry"]:
        raise ValueError("official bounded parent technical registry transition mismatch")
    original_definitions = {item["feature_id"]: item for item in original["features"]}
    revised_source_definitions = sum(
        item != original_definitions[item["feature_id"]]
        for item in manifest["feature_registry"]["features"]
    )
    return {"status": "verified_stock_and_official_market_source_revision", "training": manifest["feature_registry_hash"],
            "current": current_registry_hash, "unchanged_numeric_slots": 62,
            "revised_source_definitions": revised_source_definitions}


def _rebuild_labels(sample: Mapping[str, Any], calendar: list[str], calendar_index: Mapping[str, int],
                    benchmark: Mapping[str, Mapping[str, int | None]], prices: Mapping[str, Mapping[str, int | None]],
                    corporate_action_dates: Sequence[str] = (), *,
                    taipei_local_decision: bool = False) -> list[dict[str, Any]]:
    decision = _decision_day(sample["row"]["decision_at"], taipei_local=taipei_local_decision).strftime("%Y%m%d")
    if decision not in calendar_index:
        raise BoundedRestatementError("decision_not_in_official_calendar")
    labels = []
    for old in sample["horizon_labels"]:
        horizon = old["horizon_trading_days"]
        end_index = calendar_index[decision] + horizon - 1
        if end_index >= len(calendar):
            raise BoundedRestatementError(f"incomplete_official_horizon_h{horizon}")
        end = calendar[end_index]
        if any(decision <= event.replace("-", "") <= end for event in corporate_action_dates):
            raise BoundedRestatementError(f"corporate_action_effective_within_label_horizon_h{horizon}")
        label = dict(old)
        if label["sector_excess_observed"] or label["sector_excess_return_bp"] is not None:
            raise ValueError("official market repair cannot silently retain an observed sector benchmark")
        label.update(_recompute_label(symbol=sample["row"]["symbol"], decision_date=decision, end_date=end,
                                     horizon=horizon, calendar=calendar, benchmark=benchmark, price_path=prices))
        end_day = date.fromisoformat(end)
        label.update(horizon_end_date=end_day.isoformat(), available_at=datetime.combine(end_day, time(14, 30), _TAIPEI).isoformat())
        labels.append(label)
    return labels


def _decision_day(value: str, *, taipei_local: bool) -> date:
    if not taipei_local:
        return date.fromisoformat(value[:10])
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("candidate decision_at must be an ISO datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("candidate decision_at must include a timezone")
    return parsed.astimezone(_TAIPEI).date()


def restate_bounded_official_market(*, parent_manifest_path: Path, expected_parent_hash: str,
    source_snapshot_path: Path, expected_snapshot_hash: str, official_market_manifest: Path,
    expected_official_market_hash: str, corporate_action_manifest: Path, output_directory: Path,
    candidate_source_profile_path: Path | None = None, expected_candidate_source_profile_hash: str | None = None) -> Path:
    """不補價；缺完整四個 horizon 的列保留明確排除證據，其餘原 targets 不改。"""
    from ml_module.bounded_restated_research_consumer import _publication_shards

    if (candidate_source_profile_path is None) != (expected_candidate_source_profile_hash is None):
        raise ValueError("candidate stock source profile path and SHA must be supplied together")
    candidate_stock = candidate_source_profile_path is not None
    _require_candidate_profile_for_snapshot(
        expected_snapshot_hash,
        candidate_stock=candidate_stock,
    )
    started = datetime.now(timezone.utc)
    code_hashes = _source_hashes(candidate_stock=candidate_stock)
    parent_path = parent_manifest_path.resolve(strict=True)
    parent = _bound_parent(parent_path, expected_parent_hash)
    source = load_official_market_capture(official_market_manifest, expected_file_sha256=expected_official_market_hash, as_of=started)
    snapshot = source_snapshot_path.resolve(strict=True)
    if _file_sha256(snapshot) != expected_snapshot_hash or expected_snapshot_hash != parent["restatement"]["source_snapshot_sha256"]:
        raise ValueError("official bounded stock snapshot differs from the verified parent")
    output = output_directory.resolve()
    if output.exists() or any(output == root or output.is_relative_to(root) for root in (parent_path.parent, snapshot.parent, official_market_manifest.resolve().parent)):
        raise ValueError("official bounded output must be new and outside immutable sources")
    shards = _publication_shards(parent_path.parent, parent)
    symbols = sorted(parent["restatement"]["full_prefix_kernel_audit"]["source_rows_by_symbol"])
    prices = {}
    with sqlite3.connect(snapshot.as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        for symbol in symbols:
            prices[symbol] = {str(row["日期"]): _scaled_bar(row) for row in connection.execute(
                "SELECT 日期,開盤價,最高價,最低價,收盤價 FROM daily_prices WHERE 證券代號=? ORDER BY 日期", (symbol,))}
    actions = _load_corporate_action_custody(corporate_action_manifest, training_as_of=datetime.now(timezone.utc))
    if actions.manifest_file_hash != parent["corporate_action_custody"]["manifest_file_hash"]:
        raise ValueError("corporate action manifest differs from the original bounded source")
    observed = datetime.now(timezone.utc).isoformat()
    candidate_source_index = None
    candidate_source_identity = None
    if candidate_stock:
        from data_module.bounded_candidate_stock_source import load_candidate_stock_source_index

        if candidate_source_profile_path is None or expected_candidate_source_profile_hash is None:
            raise ValueError("candidate source profile path and hash are required")
        candidate_source_index = load_candidate_stock_source_index(
            profile_path=candidate_source_profile_path,
            expected_profile_sha256=str(expected_candidate_source_profile_hash),
            snapshot_path=snapshot,
            expected_snapshot_sha256=expected_snapshot_hash,
            symbols=sorted(parent["restatement"]["full_prefix_kernel_audit"]["source_rows_by_symbol"]),
            revision_observed_at=observed,
        )
        candidate_source_identity = {
            "mode": "daily_source_rehydration.v1",
            "profile": candidate_source_index.profile_reference,
            "bridge": candidate_source_index.bridge_payload,
            "bridge_sha256": candidate_source_index.bridge_hash,
        }
    identity_payload = {
        "schema_version": OFFICIAL_RESTATEMENT_SCHEMA, "market_source_contract": MARKET_SOURCE_CONTRACT,
        "fold_profile": OFFICIAL_FOLD_PROFILE, "started_at": started.isoformat(), "revision_observed_at": observed,
        "parent_manifest_path": str(parent_path), "parent_manifest_file_sha256": expected_parent_hash,
        "parent_training_as_of": parent["training_as_of"], "source_snapshot_sha256": expected_snapshot_hash,
        "source_snapshot_path": str(snapshot), "official_market_manifest_path": str(source.manifest_path),
        "official_market_manifest_file_sha256": source.manifest_file_sha256,
        "producer_code_root": str(Path(__file__).resolve().parents[1]), "computation_source_hashes": code_hashes,
        "selection_policy": "retain parent rows only when all four official-calendar price paths are complete; excluded rows enumerated",
        "corporate_action_manifest_path": str(corporate_action_manifest.resolve()),
        "corporate_action_manifest_file_sha256": actions.manifest_file_hash,
    }
    if candidate_source_identity is not None:
        identity_payload["candidate_stock_source"] = candidate_source_identity
    identity = _sha256_json(identity_payload)
    registry = official_feature_registry(parent, source.manifest_file_sha256)
    if candidate_source_index is not None:
        from data_module.bounded_candidate_stock_source import candidate_stock_feature_registry

        registry = candidate_stock_feature_registry(
            registry,
            profile_sha256=candidate_source_index.profile.profile_file_sha256,
            bridge_hash=candidate_source_index.bridge_hash,
        )
    manifest = deepcopy(parent)
    source_pairs = dict(parent["source_manifest_hashes"])
    source_pairs.update({MARKET_SOURCE_ID: source.manifest_file_sha256, MARKET_QUALITY_SOURCE_ID: OFFICIAL_MARKET_CONTRACT_HASH,
        "contract.official_twse_market": OFFICIAL_MARKET_CONTRACT_HASH, "parent.bounded_stock_restatement": expected_parent_hash})
    if candidate_source_index is not None:
        source_pairs.update({
            "candidate.stock_source_profile": candidate_source_index.profile.profile_file_sha256,
            "contract.candidate_daily_source_bridge": candidate_source_index.bridge_hash,
        })
    manifest.update(dataset_id="bounded-official-market-" + identity[7:31], dataset_identity_hash=identity,
        publication_id="bounded-official-market-" + identity[7:31], feature_registry=registry,
        feature_registry_hash=_sha256_json(registry), source_manifest_hashes=[list(pair) for pair in sorted(source_pairs.items())],
        stage="bounded_official_market_restatement", training_as_of=observed, revision_observed_at=observed,
        observed_session_dates=[day.isoformat() for day in sorted(source.rows)], fold_profile=OFFICIAL_FOLD_PROFILE)
    manifest["corporate_action_custody"] = actions.custody_payload()
    manifest["safety"].update(available_at_lte_decision_at=False, source_revision_observed_at=observed,
        actual_revision_clock_retained=True, event_maturity_research_folds=True)
    manifest.pop("manifest_hash")
    # 舊 execution/CLI 是父產物的證據，不讓它冒充本次建置。
    for field in ("execution", "raw_dataset_manifest", "target_cli", "feature_registry_transition"):
        manifest.pop(field, None)
    calendar = [day.strftime("%Y%m%d") for day in sorted(source.rows)]
    calendar_index = {day: index for index, day in enumerate(calendar)}
    benchmark = {day.strftime("%Y%m%d"): _scaled_bar(row) for day, row in source.rows.items()}
    empty_frame = pd.DataFrame()
    feature_cache: dict[date, tuple[list[int], list[int], date | None, date | None]] = {}
    output.mkdir(parents=True, exist_ok=False)
    _write_json(output / "source_start.json", identity_payload)
    excluded, new_shards = [], []
    changes: Counter[str] = Counter()
    preservation_before, preservation_after = hashlib.sha256(), hashlib.sha256()
    all_ids: set[str] = set()
    for path, entry in shards:
        destination = output / str(entry["path"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        content_hash = hashlib.sha256()
        retained_dates: list[str] = []
        with gzip.open(path, "rt", encoding="utf-8") as old_stream, destination.open("xb") as binary:
            header = json.loads(next(old_stream))
            for field in ("dataset_id", "publication_id", "dataset_identity_hash", "feature_registry", "feature_registry_hash", "source_manifest_hashes", "training_as_of", "revision_observed_at"):
                header[field] = manifest[field]
            with gzip.GzipFile(fileobj=binary, mode="wb", mtime=0, filename="") as stream:
                def emit(value: Mapping[str, Any]) -> None:
                    encoded = (_canonical_json(value) + "\n").encode("utf-8")
                    stream.write(encoded)
                    content_hash.update(encoded)
                emit(header)
                scanned = 0
                for line in old_stream:
                    if not line.strip():
                        continue
                    scanned += 1
                    sample = json.loads(line)["sample"]
                    row = sample["row"]
                    row_id = row["row_id"]
                    if row_id in all_ids:
                        raise ValueError("duplicate bounded parent row")
                    all_ids.add(row_id)
                    try:
                        labels = _rebuild_labels(sample, calendar, calendar_index, benchmark, prices[row["symbol"]], actions.effective_dates_by_symbol.get(row["symbol"], ()),
                            taipei_local_decision=candidate_stock)
                    except BoundedRestatementError as exc:
                        excluded.append({"row_id": row_id, "reason": str(exc)})
                        continue
                    decision = _decision_day(row["decision_at"], taipei_local=candidate_stock)
                    if decision not in feature_cache:
                        feature_cache[decision] = build_restated_feature_values(decision=decision, stock=empty_frame, dates=[], raw_rows=[],
                            market_dates=sorted(source.rows), market_rows=source.rows, feature_scales=FEATURE_SCALES)
                    values, masks, _, market_day = feature_cache[decision]
                    if market_day is None:
                        raise ValueError("retained bounded row has no prior official market event")
                    candidate_stock_ids: frozenset[str] = frozenset()
                    if candidate_source_index is not None:
                        from data_module.bounded_candidate_stock_source import CANDIDATE_STOCK_FEATURE_IDS

                        candidate_stock_ids = CANDIDATE_STOCK_FEATURE_IDS
                    preserve = lambda item: {"row_id": item["row_id"], "decision_at": item["decision_at"], "symbol": item["symbol"],
                        "features": [feature for feature in item["features"] if feature["feature_id"] not in (MARKET_FEATURE_IDS | candidate_stock_ids)],
                        "targets": item["targets"], "portfolio_state": item["portfolio_state"]}
                    preservation_before.update(_canonical_json(preserve(row)).encode("utf-8"))
                    for feature in row["features"]:
                        name = feature["feature_id"]
                        if name.startswith("industry_indices.") and feature["observed"]:
                            raise ValueError("official market repair cannot fabricate sector quality dependencies")
                        if name not in MARKET_FEATURE_IDS:
                            continue
                        position = FEATURE_NAMES.index(name)
                        if feature["scale"] != FEATURE_SCALES[position]:
                            raise ValueError("bounded market numeric scale changed")
                        value = None if masks[position] else values[position]
                        changes["market_value_slots"] += int(feature["value_int"] != value)
                        event = datetime.combine(market_day, time(14, 30), _TAIPEI).isoformat()
                        feature.update(value_int=value, observed=value is not None, quality="observed" if value is not None else "missing",
                            source_id=MARKET_SOURCE_ID if name in MARKET_RAW_IDS else MARKET_QUALITY_SOURCE_ID,
                            available_at=observed, event_at=event)
                        feature["revision_id"] = _sha256_json({"dataset": identity, "row_id": row_id, "feature": name, "value": value})
                        feature["content_hash"] = _sha256_json({key: val for key, val in feature.items() if key != "content_hash"})
                    if candidate_source_index is not None:
                        from data_module.bounded_candidate_stock_source import rebuild_candidate_stock_features

                        stock_definitions = {
                            str(item["feature_id"]): item
                            for item in registry["features"]
                        }
                        old_stock_values = {
                            str(feature["feature_id"]): feature.get("value_int")
                            for feature in row["features"]
                        }
                        row["features"] = rebuild_candidate_stock_features(
                            source=candidate_source_index,
                            features=row["features"],
                            row_id=row_id,
                            symbol=str(row["symbol"]),
                            decision_at=str(row["decision_at"]),
                            definitions=stock_definitions,
                            identity_hash=identity,
                        )
                        changes["candidate_stock_feature_slots"] += len(candidate_stock_ids)
                        changes["candidate_stock_value_changes"] += sum(
                            int(old_stock_values[feature["feature_id"]] != feature.get("value_int"))
                            for feature in row["features"]
                            if feature["feature_id"] in candidate_stock_ids
                        )
                    preservation_after.update(_canonical_json(preserve(row)).encode("utf-8"))
                    row.update(dataset_identity_hash=identity, feature_registry_hash=manifest["feature_registry_hash"], source_manifest_hashes=manifest["source_manifest_hashes"])
                    row["missing_family_ids"] = sorted({feature["family_id"] for feature in row["features"] if feature["family_id"] != "data_quality" and not feature["observed"]})
                    for old, new in zip(sample["horizon_labels"], labels, strict=True):
                        changes["labels_h" + str(new["horizon_trading_days"])] += int(old != new)
                    sample["horizon_labels"] = labels
                    sample["restated_research_provenance"].update(feature_revision_observed_at=observed, label_revision_clocks=[{
                        "horizon_trading_days": label["horizon_trading_days"], "event_maturity_available_at": label["available_at"],
                        "revision_available_at": observed, "restated": True} for label in labels])
                    emit({"record_type": "sample", "sample": sample})
                    retained_dates.append(decision.isoformat())
        if scanned != entry["sample_count"] or _file_sha256(path) != entry["compressed_sha256"]:
            raise ValueError("bounded parent shard changed during restatement")
        if not retained_dates:
            raise ValueError("an entire bounded year lost eligible rows")
        new_shards.append({**entry, "compressed_sha256": _file_sha256(destination), "content_sha256": "sha256:" + content_hash.hexdigest(),
            "compressed_bytes": destination.stat().st_size, "sample_count": len(retained_dates),
            "min_decision_date": min(retained_dates), "max_decision_date": max(retained_dates)})
        print(f"year={entry['year']} retained={len(retained_dates)} scanned={scanned} cumulative_excluded={len(excluded)}", flush=True)
    if preservation_before.digest() != preservation_after.digest() or len(all_ids) != parent["sample_count"]:
        raise ValueError("bounded retained stock features, row keys, targets or state changed")
    if _file_sha256(snapshot) != expected_snapshot_hash or _file_sha256(parent_path) != expected_parent_hash or _source_hashes(candidate_stock=candidate_stock) != code_hashes:
        raise ValueError("bounded source or producer changed during build")
    load_official_market_capture(source.manifest_path, expected_file_sha256=source.manifest_file_sha256, as_of=datetime.now(timezone.utc))
    restatement_payload = {
        "schema_version": OFFICIAL_RESTATEMENT_SCHEMA,
        "identity_payload": identity_payload,
        "excluded_rows": excluded,
        "changes": dict(changes),
        "retained_nonmarket_preservation_hash": "sha256:" + preservation_after.hexdigest(),
        "retained_nonmarket_feature_slots_per_row": 3 if candidate_source_index is not None else 49,
        "market_feature_slots_per_row": 13,
        "kernel_source_hashes": parent["restatement"]["kernel_source_hashes"],
        "historical_pit": False,
        "formal_oos_allowed": False,
        "production_action_allowed": False,
    }
    if candidate_source_identity is not None:
        if candidate_source_index is None:
            raise ValueError("candidate source index is missing after candidate profile validation")
        restatement_payload.update(
            candidate_stock_source=candidate_source_identity,
            candidate_stock_feature_slots_per_row=46,
            candidate_stock_source_audit=candidate_source_index.audit,
            candidate_stock_quality_age_policy="source_event_day_to_Taipei_local_decision_day; revision availability remains the actual candidate rebuild clock",
        )
    manifest.update(shards=new_shards, sample_count=sum(item["sample_count"] for item in new_shards), dataset_created_at=datetime.now(timezone.utc).isoformat(),
        restatement=restatement_payload)
    manifest["manifest_hash"] = _sha256_json(manifest)
    validate_official_bounded_manifest(manifest)
    _write_json(output / "manifest.json", manifest)
    return output / "manifest.json"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("parent-manifest-path", "source-snapshot-path", "official-market-manifest", "corporate-action-manifest", "output-directory"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("expected-parent-hash", "expected-snapshot-hash", "expected-official-market-hash"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--candidate-source-profile-path", type=Path)
    parser.add_argument("--expected-candidate-source-profile-hash")
    args = parser.parse_args(argv)
    path = restate_bounded_official_market(**vars(args))
    print(json.dumps({"manifest": str(path), "file_sha256": _file_sha256(path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
