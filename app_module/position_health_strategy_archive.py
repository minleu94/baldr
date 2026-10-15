"""策略帳 Health 的 additive v2 封存；共用原 custody 與 Health projector。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path
import os
import re
from typing import Any, TYPE_CHECKING
from zoneinfo import ZoneInfo

from app_module.decision_presentation import PositionHealthReadModel
from app_module.portfolio_research_account_reader import (
    StrategyPaperPortfolioResearchAccountReader, StrategyPaperResearchCheckpointSelection,
    StrategyPaperResearchHealthSource,
)
from app_module.position_health_baseline_service import PositionHealthBaselineService
from app_module.position_health_saved_archive import (
    SavedHealthArchiveError, MAX_RECEIPT_BYTES, MAX_RESULT_BYTES, MAX_SOURCE_WITNESS_BYTES,
    _canonical_bytes, _contained_regular_path, _create_immutable_bytes, _ensure_directory,
    _parse_aware_text, _parse_date_text, _path_from_receipt, _read_stable_regular, _reject_reparse_components,
    _sha256, _strict_json_object, _validate_evaluator_result_shape, _valid_hash,
    _lexists,
)
from app_module.personal_data_paths import to_internal_io_path

if TYPE_CHECKING:
    from app_module.position_health_transition_read_service import PositionHealthTransitionReadService

_TAIPEI = ZoneInfo("Asia/Taipei")
STRATEGY_HEALTH_BASELINE_SCHEMA = "strategy-position-health-baseline.v1"
STRATEGY_HEALTH_RECEIPT_SCHEMA = "position-health-strategy-saved-receipt.v2"
_PRODUCER = "app_module.position_health_strategy_archive"
_RECEIPT_ID = re.compile(r"^phsr-v2-[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class StrategyHealthArchiveReference:
    receipt_id: str
    receipt_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.receipt_id, str) or not _RECEIPT_ID.fullmatch(self.receipt_id):
            raise SavedHealthArchiveError("strategy_health_receipt_id_invalid")
        if not _valid_hash(self.receipt_sha256):
            raise SavedHealthArchiveError("strategy_health_receipt_hash_invalid")


@dataclass(frozen=True, slots=True)
class StrategySavedHealthRead:
    source: StrategyPaperResearchHealthSource
    health: PositionHealthReadModel
    reference: StrategyHealthArchiveReference
    available_at: datetime
    decision_date: date
    result_sha256: str
    baseline_sha256: str


@dataclass(frozen=True, slots=True)
class StrategyHealthArchiveCandidate:
    selection: StrategyPaperResearchCheckpointSelection
    reference: StrategyHealthArchiveReference
    decision_date: str
    available_at: str


def _safe_directories(root: Path) -> None:
    ancestor = root
    while not ancestor.exists():
        ancestor = ancestor.parent
    _reject_reparse_components(ancestor, ancestor)
    for relative in ("strategy_health/sources", "strategy_health/baselines", "strategy_health/results", "strategy_health/receipts"):
        _ensure_directory(root, root / relative)
    _reject_reparse_components(root, root)


def _positions(source: StrategyPaperResearchHealthSource) -> list[dict[str, Any]]:
    entries = dict(source.entry_lineage_ids)
    missing = [row.stock_code for row in source.positions if row.shares > 0 and not entries.get(row.stock_code)]
    if missing:
        raise SavedHealthArchiveError("strategy_health_entry_lineage_unavailable:" + ",".join(missing))
    payload = PositionHealthBaselineService().build_from_paper_snapshot(
        decision_date=source.account.as_of_date, source_result_id=source.snapshot_source_result_id,
        allocations=[{"stock_code": row.stock_code, "executable_shares": row.shares,
                      "constrained_weight_bp": row.weight_bp} for row in source.positions],
        source_path=Path("strategy-checkpoint-source.json"),
    )
    positions = payload["positions"]
    for row in positions:
        identity = entries[row["stock_code"]]
        row.update(position_id=identity, entry_lineage_id=identity,
                   entry_lineage_status="same_snapshot_verified")
    return positions


def prepare_strategy_health_baseline(
    *, account_reader: StrategyPaperPortfolioResearchAccountReader,
    portfolio_id: str, snapshot_id: str, output_dir: str | Path,
    decision_date: str | None = None,
) -> Path:
    """由真 checkpoint 另存評估基線；人工作業缺件仍由原 evaluator 處理。"""
    now = datetime.now(timezone.utc)
    selected_date = now.astimezone(_TAIPEI).date() if decision_date is None else _parse_date_text(decision_date, "decision_date")
    source = account_reader.read_health_source(portfolio_id=portfolio_id, snapshot_id=snapshot_id,
                                             allocation_decision_date=selected_date.isoformat())
    if (selected_date > now.astimezone(_TAIPEI).date()
            or source.account.available_at.astimezone(_TAIPEI).date() > selected_date
            or source.account.as_of_date > selected_date.isoformat()):
        raise SavedHealthArchiveError("strategy_health_baseline_source_after_decision")
    root = Path(output_dir).expanduser().absolute()
    positions = _positions(source)
    if not positions:
        raise SavedHealthArchiveError("strategy_health_baseline_requires_positions")
    _safe_directories(root)
    source_path = root / "strategy_health/sources" / f"{source.source_hash.removeprefix('sha256:')}.json"
    source_raw = _canonical_bytes(source.to_dict())
    _create_immutable_bytes(source_path, source_raw)
    if _read_stable_regular(source_path, root=root, max_bytes=MAX_SOURCE_WITNESS_BYTES) != source_raw:
        raise SavedHealthArchiveError("strategy_health_source_readback_mismatch")
    baseline = {
        "schema_version": STRATEGY_HEALTH_BASELINE_SCHEMA, "producer": _PRODUCER,
        "source_type": "strategy_checkpoint_exact_read_only", "source_scope": "paper_research",
        "source_path": str(source_path), "source_observed_at": now.isoformat(),
        "source_available_at": source.account.available_at.isoformat(),
        "source_snapshot_date": source.account.as_of_date,
        "source_snapshot_id": snapshot_id, "source_snapshot_rows_sha256": source.source_snapshot_rows_sha256,
        "source_result_id": source.snapshot_source_result_id, "portfolio_id": portfolio_id,
        "account_namespace": source.selection.account_namespace, "strategy_health_source": source.to_dict(),
        "strategy_health_source_sha256": source.source_hash,
        "decision_date": selected_date.isoformat(), "as_of_date": selected_date.isoformat(),
        "research_only": True, "writes_positions_db": False, "auto_action_allowed": False,
        "broker_execution": False, "formal_credit": False, "positions": positions,
        "warnings": ["strategy_health_requires_original_governed_sources"],
    }
    raw = _canonical_bytes(baseline)
    path = root / "strategy_health/baselines" / f"{_sha256(raw).removeprefix('sha256:')}.json"
    _create_immutable_bytes(path, raw)
    if _read_stable_regular(path, root=root, max_bytes=MAX_SOURCE_WITNESS_BYTES) != raw:
        raise SavedHealthArchiveError("strategy_health_baseline_readback_mismatch")
    if account_reader.read_health_source(portfolio_id=portfolio_id, snapshot_id=snapshot_id,
                                         allocation_decision_date=selected_date.isoformat()) != source:
        raise SavedHealthArchiveError("strategy_health_checkpoint_changed_during_prepare")
    return path


def _validate_pair(
    baseline: dict[str, Any], result: dict[str, Any], *, source: StrategyPaperResearchHealthSource,
    baseline_sha256: str, now: datetime,
) -> None:
    _validate_evaluator_result_shape(result)
    if (baseline.get("schema_version") != STRATEGY_HEALTH_BASELINE_SCHEMA
            or baseline.get("producer") != _PRODUCER
            or baseline.get("source_type") != "strategy_checkpoint_exact_read_only"
            or baseline.get("strategy_health_source") != source.to_dict()
            or baseline.get("strategy_health_source_sha256") != source.source_hash
            or baseline.get("portfolio_id") != source.account.portfolio_id
            or baseline.get("account_namespace") != source.selection.account_namespace
            or baseline.get("source_snapshot_id") != source.account.snapshot_id
            or baseline.get("source_snapshot_rows_sha256") != source.source_snapshot_rows_sha256
            or baseline.get("source_snapshot_date") != source.account.as_of_date
            or baseline.get("source_available_at") != source.account.available_at.isoformat()
            or baseline.get("source_result_id") != source.snapshot_source_result_id
            or baseline.get("decision_date") != source.allocation_decision_date
            or baseline.get("positions") != _positions(source)):
        raise SavedHealthArchiveError("strategy_health_baseline_checkpoint_mismatch")
    for key in ("research_only", "writes_positions_db", "auto_action_allowed", "broker_execution", "formal_credit"):
        if baseline.get(key) is not (key == "research_only"):
            raise SavedHealthArchiveError("strategy_health_baseline_boundary_invalid")
    decision = _parse_date_text(baseline.get("decision_date"), "decision_date")
    observed = _parse_aware_text(result.get("observed_at"), "observed_at")
    source_observed = _parse_aware_text(baseline.get("source_observed_at"), "source_observed_at")
    if (source.account.available_at > source_observed or source_observed > observed or observed > now
            or source_observed.astimezone(_TAIPEI).date() > decision
            or source.account.as_of_date > decision.isoformat()
            or result.get("decision_date") != decision.isoformat()
            or baseline.get("as_of_date") != decision.isoformat()):
        raise SavedHealthArchiveError("strategy_health_pair_clock_mismatch")
    provenance = result.get("provenance")
    from app_module.position_health_source_providers import SCHEMA_VERSION as SOURCE_BUNDLE_SCHEMA

    # 原 evaluator 合併 source bundle 時只以其 schema_version 蓋過基線版本。
    expected_provenance = {key: value for key, value in baseline.items() if key != "schema_version"}
    if (result.get("baseline_sha256") != baseline_sha256 or not isinstance(provenance, dict)
            or provenance.get("baseline_sha256") != baseline_sha256
            or provenance.get("schema_version") not in {STRATEGY_HEALTH_BASELINE_SCHEMA, SOURCE_BUNDLE_SCHEMA}
            or any(provenance.get(key) != value for key, value in expected_provenance.items())):
        raise SavedHealthArchiveError("strategy_health_evaluator_source_mismatch")
    expected = {row["position_id"]: row["stock_code"] for row in baseline["positions"]}
    actual = {row.get("position_id"): row.get("stock_code") for row in result["positions"]}
    if actual != expected or len(actual) != len(result["positions"]):
        raise SavedHealthArchiveError("strategy_health_evaluator_positions_mismatch")


_RECEIPT_FIELDS = {
    "schema_version", "producer", "receipt_id", "source_selection", "source_sha256",
    "baseline_path", "baseline_sha256", "result_path", "result_sha256", "available_at",
    "observed_at", "decision_date", "status", "research_only", "apply_transition",
    "auto_action_allowed", "broker_execution", "formal_credit",
}


def _receipt_path(root: Path, receipt_id: str) -> Path:
    if not isinstance(receipt_id, str) or not _RECEIPT_ID.fullmatch(receipt_id):
        raise SavedHealthArchiveError("strategy_health_receipt_id_invalid")
    return root / "strategy_health/receipts" / f"{receipt_id}.json"


def _receipt(raw: bytes, receipt_id: str) -> dict[str, Any]:
    payload = _strict_json_object(raw, "strategy_health_receipt")
    if (_canonical_bytes(payload) != raw or set(payload) != _RECEIPT_FIELDS
            or payload.get("schema_version") != STRATEGY_HEALTH_RECEIPT_SCHEMA
            or payload.get("producer") != _PRODUCER or payload.get("receipt_id") != receipt_id
            or receipt_id != "phsr-v2-" + str(payload.get("result_sha256", "")).removeprefix("sha256:")):
        raise SavedHealthArchiveError("strategy_health_receipt_identity_invalid")
    for key in ("source_sha256", "baseline_sha256", "result_sha256"):
        if not _valid_hash(payload[key]):
            raise SavedHealthArchiveError("strategy_health_receipt_hash_invalid")
    for key in ("research_only", "apply_transition", "auto_action_allowed", "broker_execution", "formal_credit"):
        if payload[key] is not (key == "research_only"):
            raise SavedHealthArchiveError("strategy_health_receipt_boundary_invalid")
    selection = payload["source_selection"]
    if not isinstance(selection, dict) or set(selection) != set(StrategyPaperResearchCheckpointSelection.__dataclass_fields__):
        raise SavedHealthArchiveError("strategy_health_receipt_selection_invalid")
    StrategyPaperResearchCheckpointSelection(**selection)
    _parse_aware_text(payload["available_at"], "available_at")
    _parse_aware_text(payload["observed_at"], "observed_at")
    _parse_date_text(payload["decision_date"], "decision_date")
    return payload


def list_strategy_saved_health_receipts(
    *, reader: PositionHealthTransitionReadService, strategy_id: str,
    strategy_version_id: str, account_namespace: str, decision_cutoff: datetime,
    cancel_callback: Any | None = None,
) -> tuple[tuple[StrategyHealthArchiveCandidate, ...], bool]:
    """有界列出指定帳戶的 v2 候選；真正來源仍須 exact 重驗。"""
    if decision_cutoff.tzinfo is None or decision_cutoff.utcoffset() is None or decision_cutoff > reader.current_clock():
        raise SavedHealthArchiveError("strategy_health_cutoff_invalid_or_future")
    root = Path(getattr(reader, "_requested_output_dir", reader.output_dir)).absolute()
    directory = root / "strategy_health/receipts"
    if not _lexists(directory):
        return (), False
    _reject_reparse_components(root, directory)
    candidates: list[StrategyHealthArchiveCandidate] = []
    scanned = count = total = 0
    truncated = False
    with os.scandir(to_internal_io_path(directory)) as entries:
        for entry in entries:
            if cancel_callback is not None and cancel_callback():
                raise InterruptedError("研究操作已取消")
            scanned += 1
            if scanned > 512:
                truncated = True
                break
            if not entry.name.startswith("phsr-v2-") or not entry.name.endswith(".json"):
                continue
            count += 1
            if count > 128:
                truncated = True
                break
            raw = _read_stable_regular(directory / entry.name, root=root, max_bytes=MAX_RECEIPT_BYTES)
            total += len(raw)
            if total > 2 * 1024 * 1024:
                truncated = True
                break
            payload = _receipt(raw, entry.name[:-5])
            selection = StrategyPaperResearchCheckpointSelection(**payload["source_selection"])
            if (selection.strategy_id, selection.strategy_version_id, selection.account_namespace) != (
                strategy_id, strategy_version_id, account_namespace,
            ):
                continue
            available = _parse_aware_text(payload["available_at"], "available_at")
            if available > decision_cutoff:
                continue
            if _parse_aware_text(payload["observed_at"], "observed_at") > available:
                raise SavedHealthArchiveError("strategy_health_receipt_clock_invalid")
            candidates.append(StrategyHealthArchiveCandidate(
                selection, StrategyHealthArchiveReference(entry.name[:-5], _sha256(raw)),
                payload["decision_date"], available.isoformat(),
            ))
    return tuple(sorted(candidates, key=lambda row: (row.decision_date, row.reference.receipt_id), reverse=True)), truncated


def publish_strategy_saved_health_receipt(
    *, output_dir: str | Path, result_path: str | Path,
    account_reader: StrategyPaperPortfolioResearchAccountReader, portfolio_id: str, snapshot_id: str,
) -> StrategyHealthArchiveReference:
    """核真帳戶與原 evaluator 結果後另存 v2；舊 v1 原件及拒絕規則不變。"""
    root = Path(output_dir).expanduser().absolute()
    result_path = _contained_regular_path(Path(result_path).expanduser().absolute(), root)
    result_raw = _read_stable_regular(result_path, root=root, max_bytes=MAX_RESULT_BYTES)
    result = _strict_json_object(result_raw, "strategy_health_result")
    if _canonical_bytes(result) != result_raw:
        raise SavedHealthArchiveError("strategy_health_result_not_canonical")
    baseline_path = _contained_regular_path(Path(result["baseline_path"]), root)
    baseline_raw = _read_stable_regular(baseline_path, root=root, max_bytes=MAX_SOURCE_WITNESS_BYTES)
    baseline = _strict_json_object(baseline_raw, "strategy_health_baseline")
    if _canonical_bytes(baseline) != baseline_raw:
        raise SavedHealthArchiveError("strategy_health_baseline_not_canonical")
    source = account_reader.read_health_source(portfolio_id=portfolio_id, snapshot_id=snapshot_id,
                                             allocation_decision_date=baseline.get("decision_date"))
    _validate_pair(baseline, result, source=source, baseline_sha256=_sha256(baseline_raw), now=datetime.now(timezone.utc))
    _safe_directories(root)
    result_hash, baseline_hash = _sha256(result_raw), _sha256(baseline_raw)
    result_target = root / "strategy_health/results" / f"{result_hash.removeprefix('sha256:')}.json"
    baseline_target = root / "strategy_health/baselines" / f"{baseline_hash.removeprefix('sha256:')}.json"
    for path, raw, limit in ((result_target, result_raw, MAX_RESULT_BYTES), (baseline_target, baseline_raw, MAX_SOURCE_WITNESS_BYTES)):
        _create_immutable_bytes(path, raw)
        if _read_stable_regular(path, root=root, max_bytes=limit) != raw:
            raise SavedHealthArchiveError("strategy_health_publish_readback_mismatch")
    if (_read_stable_regular(result_path, root=root, max_bytes=MAX_RESULT_BYTES) != result_raw
            or _read_stable_regular(baseline_path, root=root, max_bytes=MAX_SOURCE_WITNESS_BYTES) != baseline_raw
            or account_reader.read_health_source(portfolio_id=portfolio_id, snapshot_id=snapshot_id,
                                                allocation_decision_date=source.allocation_decision_date) != source):
        raise SavedHealthArchiveError("strategy_health_source_changed_during_publish")
    identity = "phsr-v2-" + result_hash.removeprefix("sha256:")
    path = _receipt_path(root, identity)
    if path.exists():
        prior_raw = _read_stable_regular(path, root=root, max_bytes=MAX_RECEIPT_BYTES)
        prior = _receipt(prior_raw, identity)
        if prior["source_sha256"] != source.source_hash or prior["baseline_sha256"] != baseline_hash:
            raise SavedHealthArchiveError("strategy_health_retry_source_mismatch")
        return StrategyHealthArchiveReference(identity, _sha256(prior_raw))
    receipt = {
        "schema_version": STRATEGY_HEALTH_RECEIPT_SCHEMA, "producer": _PRODUCER, "receipt_id": identity,
        "source_selection": {name: getattr(source.selection, name) for name in source.selection.__dataclass_fields__},
        "source_sha256": source.source_hash, "baseline_path": baseline_target.relative_to(root).as_posix(),
        "baseline_sha256": baseline_hash, "result_path": result_target.relative_to(root).as_posix(),
        "result_sha256": result_hash, "observed_at": result["observed_at"],
        "decision_date": result["decision_date"], "status": result["status"],
        "research_only": True, "apply_transition": False, "auto_action_allowed": False,
        "broker_execution": False, "formal_credit": False,
        "available_at": datetime.now(timezone.utc).isoformat(),
    }
    raw = _canonical_bytes(receipt)
    _create_immutable_bytes(path, raw)
    if _read_stable_regular(path, root=root, max_bytes=MAX_RECEIPT_BYTES) != raw:
        raise SavedHealthArchiveError("strategy_health_receipt_readback_mismatch")
    _receipt(raw, identity)
    return StrategyHealthArchiveReference(identity, _sha256(raw))


def read_strategy_saved_health_exact(
    *, reader: PositionHealthTransitionReadService, reference: StrategyHealthArchiveReference,
    account_reader: StrategyPaperPortfolioResearchAccountReader, portfolio_id: str, snapshot_id: str,
    decision_cutoff: datetime,
) -> StrategySavedHealthRead:
    """v2 成對重核 namespace／帳戶／行情／Health；不借用 v1 strategy scope。"""
    now = reader.current_clock()
    if decision_cutoff.tzinfo is None or decision_cutoff.utcoffset() is None or decision_cutoff > now:
        raise SavedHealthArchiveError("strategy_health_cutoff_invalid_or_future")
    root = Path(getattr(reader, "_requested_output_dir", reader.output_dir)).absolute()
    path = _receipt_path(root, reference.receipt_id)
    raw = _read_stable_regular(path, root=root, max_bytes=MAX_RECEIPT_BYTES)
    if _sha256(raw) != reference.receipt_sha256:
        raise SavedHealthArchiveError("strategy_health_external_receipt_hash_mismatch")
    receipt = _receipt(raw, reference.receipt_id)
    available = _parse_aware_text(receipt["available_at"], "available_at")
    if available > decision_cutoff or _parse_aware_text(receipt["observed_at"], "observed_at") > available:
        raise SavedHealthArchiveError("strategy_health_receipt_after_cutoff")
    baseline_path = _path_from_receipt(root, receipt["baseline_path"], "baseline_path")
    result_path = _path_from_receipt(root, receipt["result_path"], "result_path")
    baseline_raw = _read_stable_regular(baseline_path, root=root, max_bytes=MAX_SOURCE_WITNESS_BYTES)
    result_raw = _read_stable_regular(result_path, root=root, max_bytes=MAX_RESULT_BYTES)
    if _sha256(baseline_raw) != receipt["baseline_sha256"] or _sha256(result_raw) != receipt["result_sha256"]:
        raise SavedHealthArchiveError("strategy_health_archive_hash_mismatch")
    baseline, result = _strict_json_object(baseline_raw, "strategy_health_baseline"), _strict_json_object(result_raw, "strategy_health_result")
    if _canonical_bytes(baseline) != baseline_raw or _canonical_bytes(result) != result_raw:
        raise SavedHealthArchiveError("strategy_health_archive_not_canonical")
    source = account_reader.read_health_source(portfolio_id=portfolio_id, snapshot_id=snapshot_id,
                                             allocation_decision_date=receipt["decision_date"])
    if (receipt["source_sha256"] != source.source_hash
            or receipt["source_selection"] != {name: getattr(source.selection, name) for name in source.selection.__dataclass_fields__}
            or receipt["decision_date"] != result["decision_date"] or receipt["observed_at"] != result["observed_at"]
            or receipt["status"] != result["status"]):
        raise SavedHealthArchiveError("strategy_health_archive_source_mismatch")
    _validate_pair(baseline, result, source=source, baseline_sha256=receipt["baseline_sha256"], now=now)
    health = reader._project(
        receipt={**receipt, "warnings": result["warnings"], "blockers": result["blockers"]},
        receipt_sha256=reference.receipt_sha256, result=result, result_path=result_path,
        expected_date=_parse_date_text(receipt["decision_date"], "decision_date"),
        expected_position_ids=tuple(row["position_id"] for row in baseline["positions"]),
        expected_cohort_key=None, max_age_days=None,
    )
    health = replace(health, receipt_path=str(path))
    if (_read_stable_regular(path, root=root, max_bytes=MAX_RECEIPT_BYTES) != raw
            or _read_stable_regular(baseline_path, root=root, max_bytes=MAX_SOURCE_WITNESS_BYTES) != baseline_raw
            or _read_stable_regular(result_path, root=root, max_bytes=MAX_RESULT_BYTES) != result_raw
            or account_reader.read_health_source(portfolio_id=portfolio_id, snapshot_id=snapshot_id,
                                                allocation_decision_date=receipt["decision_date"]) != source):
        raise SavedHealthArchiveError("strategy_health_changed_during_read")
    return StrategySavedHealthRead(source, health, reference, available,
                                  _parse_date_text(receipt["decision_date"], "decision_date"),
                                  receipt["result_sha256"], receipt["baseline_sha256"])
