"""Position Health 不可變結果封存與 exact public reader。

此候選只封存 evaluator 已寫入並讀回的結果，不重跑 evaluator，也不以
latest.json 或 latest_status.json 決定歷史內容。封存時鐘由 writer 在
result／source witness 完整持久化並讀回後自行取用。Source hash 只證明位元組
一致；它不單獨證明 Paper snapshot 的來源權威，P06 必須再與同一帳本 snapshot 配對。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Mapping, TYPE_CHECKING
from zoneinfo import ZoneInfo

from app_module.decision_presentation import PositionHealthReadModel
from app_module.personal_data_paths import to_internal_io_path

if TYPE_CHECKING:
    from app_module.position_health_transition_read_service import (
        PositionHealthTransitionReadService,
    )


SAVED_HEALTH_RECEIPT_SCHEMA = "position-health-saved-receipt.v1"
SAVED_HEALTH_PRODUCER = "app_module.position_health_saved_archive"
EVALUATOR_SCHEMA = "position-health-transition-evaluation.v1"
EVALUATOR_PRODUCER = "app_module.position_health_transition_evaluator"
DAILY_BASELINE_SCHEMA = "position-health-daily-refresh.v2"
DAILY_BASELINE_PRODUCER = "app_module.position_health_daily_refresh_service"
SAVED_BASELINE_WITNESS_SCHEMA = "position-health-daily-baseline-witness.v2"
SAVED_BASELINE_WITNESS_PRODUCER = "app_module.position_health_daily_refresh_service"
COMPOSITE_SOURCE_WITNESS_SCHEMA = "position-health-exact-source-witness.v2"
LEGACY_BASELINE_SCHEMA = "position-health-baseline.v1"
MAX_RECEIPT_BYTES = 64 * 1024
MAX_RESULT_BYTES = 16 * 1024 * 1024
MAX_SOURCE_WITNESS_BYTES = 8 * 1024 * 1024
_RECEIPT_ID_RE = re.compile(r"^phsr-v1-[0-9a-f]{64}$")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_TAIPEI = ZoneInfo("Asia/Taipei")


class SavedHealthArchiveError(ValueError):
    """精確 archive／scope 驗證失敗，錯誤名稱可供 UI 與 QA 診斷。"""


@dataclass(frozen=True)
class SavedHealthReceiptSelector:
    """只選 receipt identity；不接受 caller SHA、path 或 source clock。"""

    receipt_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.receipt_id, str) or not _RECEIPT_ID_RE.fullmatch(
            self.receipt_id
        ):
            raise ValueError("saved_health_receipt_id_invalid")


@dataclass(frozen=True)
class PositionHealthPositionScope:
    """由同次 P06 帳本 snapshot 提供的 position identity。"""

    position_id: str
    stock_code: str
    shares: int

    def __post_init__(self) -> None:
        if not isinstance(self.position_id, str) or not self.position_id.strip():
            raise ValueError("saved_health_scope_position_id_invalid")
        if not isinstance(self.stock_code, str) or not self.stock_code.strip():
            raise ValueError("saved_health_scope_stock_code_invalid")
        if isinstance(self.shares, bool) or not isinstance(self.shares, int):
            raise ValueError("saved_health_scope_shares_invalid")
        # P06 帳本列代表實際持倉；空倉不在精確持倉範圍內，因此零股不能代替一列持倉。
        if self.shares <= 0:
            raise ValueError("saved_health_scope_shares_invalid")


@dataclass(frozen=True)
class PositionHealthExactScope:
    """P06 exact account 範圍；cutoff 只是時間上限，不是來源證據。"""

    portfolio_id: str
    snapshot_id: str
    decision_date: date
    decision_cutoff: datetime
    positions: tuple[PositionHealthPositionScope, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.portfolio_id, str) or not self.portfolio_id.strip():
            raise ValueError("saved_health_scope_portfolio_invalid")
        if not isinstance(self.snapshot_id, str) or not self.snapshot_id.strip():
            raise ValueError("saved_health_scope_snapshot_invalid")
        if not isinstance(self.decision_date, date) or isinstance(
            self.decision_date, datetime
        ):
            raise ValueError("saved_health_scope_decision_date_invalid")
        if not isinstance(self.positions, tuple) or any(
            not isinstance(item, PositionHealthPositionScope) for item in self.positions
        ):
            raise ValueError("saved_health_scope_positions_must_be_typed_tuple")
        keys = [item.position_id for item in self.positions]
        if len(keys) != len(set(keys)):
            raise ValueError("saved_health_scope_duplicate_position_id")


@dataclass(frozen=True)
class SavedPositionHealthReadModel:
    """包含實際 archive identity 的凍結 exact read model。"""

    status: str
    receipt_id: str | None
    receipt_path: str | None
    receipt_sha256: str | None
    saved_receipt_available_at: str | None
    source_available_at: str | None
    source_observed_at: str | None
    baseline_saved_available_at: str | None
    health_source_available_at: str | None
    source_witness_status: str
    health: PositionHealthReadModel | None
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]

    @property
    def positions(self) -> tuple[Any, ...]:
        return () if self.health is None else self.health.positions

    @property
    def result_path(self) -> str | None:
        return None if self.health is None else self.health.result_path

    @property
    def result_sha256(self) -> str | None:
        return None if self.health is None else self.health.result_sha256

    @property
    def source_snapshot_id(self) -> str | None:
        return None if self.health is None else self.health.source_snapshot_id

    @property
    def portfolio_id(self) -> str | None:
        return None if self.health is None else self.health.portfolio_id

    @property
    def decision_date(self) -> str | None:
        return None if self.health is None else self.health.decision_date

    @property
    def source_snapshot_rows_sha256(self) -> str | None:
        return None if self.health is None else self.health.source_snapshot_rows_sha256

    @property
    def observed_at(self) -> str | None:
        return None if self.health is None else self.health.observed_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "receipt_id": self.receipt_id,
            "receipt_path": self.receipt_path,
            "receipt_sha256": self.receipt_sha256,
            "saved_receipt_available_at": self.saved_receipt_available_at,
            "source_available_at": self.source_available_at,
            "source_observed_at": self.source_observed_at,
            "baseline_saved_available_at": self.baseline_saved_available_at,
            "health_source_available_at": self.health_source_available_at,
            "portfolio_id": self.portfolio_id,
            "source_snapshot_id": self.source_snapshot_id,
            "source_snapshot_rows_sha256": self.source_snapshot_rows_sha256,
            "decision_date": self.decision_date,
            "observed_at": self.observed_at,
            "result_path": self.result_path,
            "result_sha256": self.result_sha256,
            "source_witness_status": self.source_witness_status,
            "health": None if self.health is None else self.health.to_dict(),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
        }


def publish_saved_health_receipt(
    *,
    output_dir: str | Path,
    result_path: str | Path,
) -> dict[str, str]:
    """確認完整 evaluator result bytes 後，以 create-only 方式封存。

    已存在且有效的 receipt 會原樣返回，包含首次由 writer 取得的 available
    clock。格式錯誤或 identity 衝突時 fail closed，不會就地修補。
    """

    root = Path(output_dir).expanduser().absolute()
    result_candidate = Path(result_path).expanduser().absolute()
    result_resolved = _contained_regular_path(result_candidate, root)
    result_raw = _read_stable_regular(
        result_resolved, root=root, max_bytes=MAX_RESULT_BYTES
    )
    decoded_result = _strict_json_object(result_raw, "saved_health_result")
    if _canonical_bytes(decoded_result) != result_raw:
        raise SavedHealthArchiveError("saved_health_result_not_canonical")
    _validate_evaluator_result_shape(decoded_result)
    result_sha256 = _sha256(raw=result_raw)
    result_hex = result_sha256.removeprefix("sha256:")
    receipt_id = f"phsr-v1-{result_hex}"
    archive_root = root / "saved_health"
    receipt_dir = archive_root / "receipts"
    source_dir = archive_root / "sources"
    receipt_path = receipt_dir / f"{receipt_id}.json"

    _ensure_directory(root, archive_root)
    _ensure_directory(root, receipt_dir)
    _ensure_directory(root, source_dir)

    if _lexists(receipt_path):
        prior_raw = _read_stable_regular(
            receipt_path, root=root, max_bytes=MAX_RECEIPT_BYTES
        )
        receipt = _strict_json_object(prior_raw, "saved_health_receipt")
        if _canonical_bytes(receipt) != prior_raw:
            raise SavedHealthArchiveError("saved_health_receipt_not_canonical")
        _validate_receipt(receipt, receipt_id=receipt_id, result_sha256=result_sha256)
        prior_result_path = _path_from_receipt(
            root, receipt.get("result_path"), "result_path"
        )
        prior_result_raw = _read_stable_regular(
            prior_result_path, root=root, max_bytes=MAX_RESULT_BYTES
        )
        if _sha256(prior_result_raw) != result_sha256:
            raise SavedHealthArchiveError("saved_health_retry_result_hash_mismatch")
        _read_source_witness(root=root, receipt=receipt)
        return _writer_receipt_metadata(receipt_path, prior_raw, receipt)

    source_relative: str | None = None
    source_sha256: str | None = None
    source_witness_status = "missing"
    source_witness_reason = "health_baseline_source_missing"
    result_observed_at = _optional_text(decoded_result.get("observed_at"))
    result_observed = _parse_aware_text(result_observed_at, "observed_at")
    decision_date = _optional_text(decoded_result.get("decision_date"))
    result_provenance = decoded_result.get("provenance")
    if not isinstance(result_provenance, Mapping):
        result_provenance = {}
    portfolio_id = _first_text(
        result_provenance.get("portfolio_id"),
        result_provenance.get("paper_portfolio_id"),
        result_provenance.get("source_portfolio_id"),
    )
    snapshot_id = _first_text(
        result_provenance.get("source_snapshot_id"),
        result_provenance.get("snapshot_id"),
    )
    rows_hash = _first_text(
        result_provenance.get("source_snapshot_rows_sha256"),
        result_provenance.get("snapshot_rows_sha256"),
    )
    source_path_raw = decoded_result.get("baseline_path")
    if not source_path_raw:
        source_path_raw = result_provenance.get("baseline_path")
    source_hash_raw = decoded_result.get("baseline_sha256")
    if not source_hash_raw:
        source_hash_raw = result_provenance.get("baseline_sha256")

    if isinstance(source_path_raw, str) and source_path_raw.strip():
        try:
            source_path = Path(source_path_raw).expanduser().absolute()
            source_raw = _read_stable_regular(
                source_path,
                root=source_path.parent,
                max_bytes=MAX_SOURCE_WITNESS_BYTES,
            )
            source_payload = _strict_json_object(source_raw, "saved_health_source")
            if _canonical_bytes(source_payload) != source_raw:
                raise SavedHealthArchiveError("saved_health_baseline_not_canonical")
            actual_source_hash = _sha256(source_raw)
            if source_hash_raw != actual_source_hash:
                source_witness_status = "invalid"
                source_witness_reason = "health_baseline_hash_mismatch"
            else:
                assessment = _assess_daily_baseline(source_payload)
                source_witness_status = assessment
                if assessment == "structurally_valid":
                    _validate_baseline_result_identity(
                        baseline=source_payload,
                        portfolio_id=portfolio_id,
                        snapshot_id=snapshot_id,
                        rows_hash=rows_hash,
                        decision_date=decision_date,
                    )
                    baseline_witness_path = (
                        source_path.parent
                        / "saved_baseline_witnesses"
                        / f"{actual_source_hash.removeprefix('sha256:')}.json"
                    )
                    baseline_witness_raw = _read_stable_regular(
                        baseline_witness_path,
                        root=source_path.parent,
                        max_bytes=MAX_RECEIPT_BYTES,
                    )
                    baseline_witness = _strict_json_object(
                        baseline_witness_raw, "saved_health_baseline_witness"
                    )
                    if _canonical_bytes(baseline_witness) != baseline_witness_raw:
                        raise SavedHealthArchiveError(
                            "saved_health_baseline_witness_not_canonical"
                        )
                    source_observed, baseline_saved = _validate_baseline_witness_pair(
                        baseline=source_payload,
                        baseline_raw=source_raw,
                        baseline_name=source_path.name,
                        baseline_witness=baseline_witness,
                    )
                    if baseline_saved > result_observed:
                        raise SavedHealthArchiveError(
                            "saved_health_baseline_saved_after_evaluation"
                        )
                    composite = {
                        "schema_version": COMPOSITE_SOURCE_WITNESS_SCHEMA,
                        "baseline_name": source_path.name,
                        "baseline": source_payload,
                        "baseline_sha256": actual_source_hash,
                        "baseline_witness": baseline_witness,
                        "baseline_witness_sha256": _sha256(baseline_witness_raw),
                    }
                    composite_raw = _canonical_bytes(composite)
                    composite_hash = _sha256(composite_raw)
                    source_name = f"{composite_hash.removeprefix('sha256:')}.json"
                    source_target = source_dir / source_name
                    _create_immutable_bytes(source_target, composite_raw)
                    copied_raw = _read_stable_regular(
                        source_target,
                        root=root,
                        max_bytes=MAX_SOURCE_WITNESS_BYTES,
                    )
                    if copied_raw != composite_raw:
                        raise SavedHealthArchiveError(
                            "saved_health_source_archive_readback_mismatch"
                        )
                    source_relative = source_target.relative_to(root).as_posix()
                    source_sha256 = composite_hash
                    source_witness_reason = ""
                elif assessment == "unqualified":
                    source_witness_reason = "health_baseline_formal_identity_missing"
                else:
                    source_witness_reason = "health_baseline_source_contract_invalid"
        except FileNotFoundError:
            # 例如 evaluator 讀到可變 latest.json；沒有與該 exact bytes
            # 綁定的 baseline witness 時只回報未具來源資格，不升成可信快照。
            source_witness_status = "unqualified"
            source_witness_reason = "health_baseline_immutable_witness_missing"
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            source_witness_status = "invalid"
            detail = str(exc) or type(exc).__name__
            source_witness_reason = f"health_baseline_witness_unavailable:{detail}"

    result_relative = result_resolved.relative_to(root.resolve()).as_posix()
    receipt = {
        "schema_version": SAVED_HEALTH_RECEIPT_SCHEMA,
        "producer": SAVED_HEALTH_PRODUCER,
        "receipt_id": receipt_id,
        "result_path": result_relative,
        "result_sha256": result_sha256,
        "source_witness_path": source_relative,
        "source_witness_sha256": source_sha256,
        "source_witness_status": source_witness_status,
        "source_witness_reason": source_witness_reason,
        "decision_date": decision_date,
        "observed_at": result_observed_at,
        "portfolio_id": portfolio_id,
        "source_snapshot_id": snapshot_id,
        "source_snapshot_rows_sha256": rows_hash,
        "status": _required_text(decoded_result.get("status")),
        "research_only": True,
        "apply_transition": False,
        "auto_action_allowed": False,
        "broker_execution": False,
        "formal_credit": False,
        "available_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
    }
    receipt_raw = _canonical_bytes(receipt)
    _create_immutable_bytes(receipt_path, receipt_raw)
    persisted = _read_stable_regular(
        receipt_path, root=root, max_bytes=MAX_RECEIPT_BYTES
    )
    if persisted != receipt_raw:
        raise SavedHealthArchiveError("saved_health_receipt_readback_mismatch")
    persisted_receipt = _strict_json_object(persisted, "saved_health_receipt")
    _validate_receipt(
        persisted_receipt,
        receipt_id=receipt_id,
        result_sha256=result_sha256,
    )
    return _writer_receipt_metadata(receipt_path, persisted, persisted_receipt)


def read_saved_health_receipt(
    *,
    reader: "PositionHealthTransitionReadService",
    selector: SavedHealthReceiptSelector,
    scope: PositionHealthExactScope,
) -> SavedPositionHealthReadModel:
    """讀取一份不可變結果；不查詢可變 latest pointers。"""

    if not isinstance(selector, SavedHealthReceiptSelector):
        return _blocked_model(None, "saved_health_selector_type_invalid")
    if not isinstance(scope, PositionHealthExactScope):
        return _blocked_model(None, "saved_health_scope_type_invalid")
    root = getattr(reader, "_requested_output_dir", reader.output_dir)
    root = Path(root).expanduser().absolute()
    receipt_path = root / "saved_health" / "receipts" / f"{selector.receipt_id}.json"
    receipt_sha256: str | None = None
    saved_available_at: str | None = None
    try:
        now_value = reader._read_now()
        cutoff = _parse_aware_datetime(scope.decision_cutoff, "decision_cutoff")
        if cutoff > now_value:
            raise SavedHealthArchiveError("saved_health_decision_cutoff_future")
        receipt_raw = _read_stable_regular(
            receipt_path, root=root, max_bytes=MAX_RECEIPT_BYTES
        )
        receipt = _strict_json_object(receipt_raw, "saved_health_receipt")
        receipt_sha256 = _sha256(receipt_raw)
        if _canonical_bytes(receipt) != receipt_raw:
            raise SavedHealthArchiveError("saved_health_receipt_not_canonical")
        _validate_receipt(
            receipt,
            receipt_id=selector.receipt_id,
            result_sha256=_required_hash(receipt.get("result_sha256")),
        )
        available_at = _parse_aware_text(receipt.get("available_at"), "available_at")
        saved_available_at = available_at.isoformat()
        observed_at = _parse_aware_text(receipt.get("observed_at"), "observed_at")
        if available_at > cutoff:
            raise SavedHealthArchiveError("saved_health_receipt_after_requested_cutoff")
        if observed_at > available_at:
            raise SavedHealthArchiveError("saved_health_result_observed_after_archive")
        if receipt.get("decision_date") != scope.decision_date.isoformat():
            raise SavedHealthArchiveError("saved_health_scope_decision_date_mismatch")
        receipt_portfolio = receipt.get("portfolio_id")
        if receipt_portfolio is not None and receipt_portfolio != scope.portfolio_id:
            raise SavedHealthArchiveError("saved_health_scope_portfolio_mismatch")
        portfolio_identity_missing = not receipt_portfolio
        if receipt.get("source_snapshot_id") != scope.snapshot_id:
            raise SavedHealthArchiveError("saved_health_scope_snapshot_mismatch")

        result_path = _path_from_receipt(root, receipt.get("result_path"), "result_path")
        result_raw = _read_stable_regular(
            result_path, root=root, max_bytes=MAX_RESULT_BYTES
        )
        if _sha256(result_raw) != receipt.get("result_sha256"):
            raise SavedHealthArchiveError("saved_health_result_hash_mismatch")
        result = _strict_json_object(result_raw, "saved_health_result")
        if _canonical_bytes(result) != result_raw:
            raise SavedHealthArchiveError("saved_health_result_not_canonical")
        _validate_evaluator_result_shape(result)

        witness_status, witness_payload, baseline_witness = _read_source_witness(
            root=root, receipt=receipt
        )
        _validate_result_archive_identity(result, receipt)
        if portfolio_identity_missing and witness_status == "structurally_valid":
            witness_status = "unqualified"
        scope_witness_complete = _validate_scope_positions(
            result, witness_payload, scope
        )
        if not scope_witness_complete and witness_status == "structurally_valid":
            witness_status = "unqualified"

        synthetic_receipt = {
            "schema_version": EVALUATOR_SCHEMA,
            "producer": EVALUATOR_PRODUCER,
            "status": receipt.get("status"),
            "decision_date": receipt.get("decision_date"),
            "result_path": str(result_path),
            "latest_path": str(root / "latest.json"),
            "result_sha256": receipt.get("result_sha256"),
            "warnings": list(result.get("warnings") or []),
            "blockers": list(result.get("blockers") or []),
            "research_only": True,
            "apply_transition": False,
            "auto_action_allowed": False,
            "broker_execution": False,
            "formal_credit": False,
        }
        health = reader._project(
            receipt=synthetic_receipt,
            receipt_sha256=receipt_sha256,
            result=result,
            result_path=result_path,
            expected_date=scope.decision_date,
            expected_position_ids=tuple(
                item.position_id for item in scope.positions
            ),
            expected_cohort_key=None,
            max_age_days=None,
        )
        health = replace(
            health,
            receipt_path=str(receipt_path),
            receipt_sha256=receipt_sha256,
        )

        warnings = list(health.warnings)
        status = health.status
        if witness_status != "structurally_valid":
            status = "degraded" if health.status in {"passed", "degraded"} else health.status
            warnings.append(f"saved_health_source_witness_{witness_status}")
            health = _revoke_positive_health(health, witness_status)
        if health.source_snapshot_rows_sha256 and not _valid_hash(
            health.source_snapshot_rows_sha256
        ):
            raise SavedHealthArchiveError("saved_health_snapshot_rows_hash_invalid")
        return SavedPositionHealthReadModel(
            status=status,
            receipt_id=selector.receipt_id,
            receipt_path=str(receipt_path),
            receipt_sha256=receipt_sha256,
            saved_receipt_available_at=available_at.isoformat(),
            source_available_at=(
                None
                if witness_payload is None
                else _optional_text(witness_payload.get("source_available_at"))
            ),
            source_observed_at=(
                None
                if baseline_witness is None
                else _parse_aware_text(
                    baseline_witness.get("source_observed_at"), "source_observed_at"
                ).isoformat()
            ),
            baseline_saved_available_at=(
                None
                if baseline_witness is None
                else _parse_aware_text(
                    baseline_witness.get("saved_available_at"),
                    "baseline_saved_available_at",
                ).isoformat()
            ),
            health_source_available_at=health.available_at,
            source_witness_status=witness_status,
            health=health,
            warnings=tuple(dict.fromkeys(warnings)),
            blockers=health.blockers,
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
        AttributeError,
    ) as exc:
        reason = str(exc) or type(exc).__name__
        return _blocked_model(
            selector.receipt_id,
            reason,
            receipt_path=receipt_path,
            receipt_sha256=receipt_sha256,
            saved_available_at=saved_available_at,
        )


def _blocked_model(
    receipt_id: str | None,
    blocker: str,
    *,
    receipt_path: Path | None = None,
    receipt_sha256: str | None = None,
    saved_available_at: str | None = None,
) -> SavedPositionHealthReadModel:
    return SavedPositionHealthReadModel(
        status="blocked",
        receipt_id=receipt_id,
        receipt_path=None if receipt_path is None else str(receipt_path),
        receipt_sha256=receipt_sha256,
        saved_receipt_available_at=saved_available_at,
        source_available_at=None,
        source_observed_at=None,
        baseline_saved_available_at=None,
        health_source_available_at=None,
        source_witness_status="unavailable",
        health=None,
        warnings=(),
        blockers=(blocker,),
    )


def _revoke_positive_health(
    health: PositionHealthReadModel,
    witness_status: str,
) -> PositionHealthReadModel:
    blocker = f"saved_health_source_witness_{witness_status}"
    positions = tuple(
        replace(
            item,
            proposed_state="WATCH",
            action_suitability="WATCH",
            source_status="degraded",
            quality="degraded",
            review_required=True,
            why="歷史 Health 缺少可核的正式 Paper snapshot witness；保留未知狀態。",
            why_not=tuple(dict.fromkeys((*item.why_not, blocker))),
            warnings=tuple(dict.fromkeys((*item.warnings, blocker))),
        )
        for item in health.positions
    )
    return replace(
        health,
        status="degraded",
        source_status="degraded",
        quality="degraded",
        warnings=tuple(dict.fromkeys((*health.warnings, blocker))),
        positions=positions,
    )


def _validate_scope_positions(
    result: Mapping[str, Any],
    witness: Mapping[str, Any] | None,
    scope: PositionHealthExactScope,
) -> bool:
    rows = result.get("positions")
    if not isinstance(rows, list):
        raise SavedHealthArchiveError("saved_health_result_positions_invalid")
    expected = {item.position_id: item for item in scope.positions}
    actual: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise SavedHealthArchiveError("saved_health_result_position_invalid")
        position_id = row.get("position_id")
        if not isinstance(position_id, str) or not position_id:
            raise SavedHealthArchiveError("saved_health_result_position_identity_missing")
        if position_id in actual:
            raise SavedHealthArchiveError("saved_health_result_position_identity_duplicate")
        actual[position_id] = row
    if set(actual) != set(expected):
        raise SavedHealthArchiveError("saved_health_scope_position_identity_mismatch")
    for position_id, expected_row in expected.items():
        if actual[position_id].get("stock_code") != expected_row.stock_code:
            raise SavedHealthArchiveError("saved_health_scope_stock_code_mismatch")

    if witness is None:
        return False
    source_positions = witness.get("positions")
    if not isinstance(source_positions, list):
        raise SavedHealthArchiveError("saved_health_source_positions_invalid")
    source_by_id: dict[str, Mapping[str, Any]] = {}
    source_identity_missing = False
    for row in source_positions:
        if not isinstance(row, Mapping):
            raise SavedHealthArchiveError("saved_health_source_position_invalid")
        position_id = row.get("position_id")
        if not isinstance(position_id, str) or not position_id:
            source_identity_missing = True
            continue
        if position_id in source_by_id:
            raise SavedHealthArchiveError("saved_health_source_position_identity_duplicate")
        source_by_id[position_id] = row
    if source_identity_missing:
        return False
    if set(source_by_id) != set(expected):
        raise SavedHealthArchiveError("saved_health_source_scope_position_mismatch")
    complete = True
    for position_id, expected_row in expected.items():
        source = source_by_id[position_id]
        source_code = source.get("stock_code")
        if not source_code:
            complete = False
        elif source_code != expected_row.stock_code:
            raise SavedHealthArchiveError("saved_health_source_scope_stock_code_mismatch")
        quantity = source.get("paper_shares")
        if quantity is None:
            complete = False
            continue
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise SavedHealthArchiveError("saved_health_source_scope_shares_invalid")
        if quantity != expected_row.shares:
            raise SavedHealthArchiveError("saved_health_source_scope_shares_mismatch")
    return complete


def _read_source_witness(
    *, root: Path, receipt: Mapping[str, Any]
) -> tuple[str, Mapping[str, Any] | None, Mapping[str, Any] | None]:
    status = receipt.get("source_witness_status")
    if status == "invalid":
        raise SavedHealthArchiveError("saved_health_source_witness_invalid")
    if status in {"missing", "unqualified"}:
        return str(status), None, None
    if status != "structurally_valid":
        raise SavedHealthArchiveError("saved_health_source_witness_status_invalid")
    path = _path_from_receipt(
        root, receipt.get("source_witness_path"), "source_witness_path"
    )
    raw = _read_stable_regular(path, root=root, max_bytes=MAX_SOURCE_WITNESS_BYTES)
    expected_hash = _required_hash(receipt.get("source_witness_sha256"))
    if _sha256(raw) != expected_hash:
        raise SavedHealthArchiveError("saved_health_source_witness_hash_mismatch")
    payload = _strict_json_object(raw, "saved_health_source")
    if _canonical_bytes(payload) != raw:
        raise SavedHealthArchiveError("saved_health_source_not_canonical")
    if set(payload) != {
        "schema_version",
        "baseline_name",
        "baseline",
        "baseline_sha256",
        "baseline_witness",
        "baseline_witness_sha256",
    } or payload.get("schema_version") != COMPOSITE_SOURCE_WITNESS_SCHEMA:
        raise SavedHealthArchiveError("saved_health_source_witness_schema_invalid")
    baseline = payload.get("baseline")
    baseline_witness = payload.get("baseline_witness")
    if not isinstance(baseline, Mapping) or not isinstance(baseline_witness, Mapping):
        raise SavedHealthArchiveError("saved_health_source_witness_pair_invalid")
    baseline_raw = _canonical_bytes(baseline)
    baseline_witness_raw = _canonical_bytes(baseline_witness)
    if _sha256(baseline_raw) != payload.get("baseline_sha256"):
        raise SavedHealthArchiveError("saved_health_baseline_hash_mismatch")
    if _sha256(baseline_witness_raw) != payload.get("baseline_witness_sha256"):
        raise SavedHealthArchiveError("saved_health_baseline_witness_hash_mismatch")
    if _assess_daily_baseline(baseline) != "structurally_valid":
        raise SavedHealthArchiveError("saved_health_source_witness_schema_invalid")
    _validate_baseline_witness_pair(
        baseline=baseline,
        baseline_raw=baseline_raw,
        baseline_name=str(payload.get("baseline_name") or ""),
        baseline_witness=baseline_witness,
    )
    if baseline.get("source_snapshot_id") != receipt.get("source_snapshot_id"):
        raise SavedHealthArchiveError("saved_health_source_snapshot_mismatch")
    if baseline.get("source_snapshot_rows_sha256") != receipt.get(
        "source_snapshot_rows_sha256"
    ):
        raise SavedHealthArchiveError("saved_health_source_snapshot_rows_hash_mismatch")
    if baseline.get("decision_date") != receipt.get("decision_date"):
        raise SavedHealthArchiveError("saved_health_source_decision_date_mismatch")
    witness_portfolio = baseline.get("portfolio_id")
    receipt_portfolio = receipt.get("portfolio_id")
    if witness_portfolio and receipt_portfolio and witness_portfolio != receipt_portfolio:
        raise SavedHealthArchiveError("saved_health_source_portfolio_mismatch")
    source_observed = _parse_aware_text(
        baseline_witness.get("source_observed_at"), "source_observed_at"
    )
    baseline_saved = _parse_aware_text(
        baseline_witness.get("saved_available_at"), "baseline_saved_available_at"
    )
    evaluator_observed = _parse_aware_text(receipt.get("observed_at"), "observed_at")
    archive_available = _parse_aware_text(receipt.get("available_at"), "available_at")
    if source_observed > baseline_saved:
        raise SavedHealthArchiveError("saved_health_baseline_saved_before_source_observed")
    if baseline_saved > evaluator_observed:
        raise SavedHealthArchiveError("saved_health_baseline_saved_after_evaluation")
    if evaluator_observed > archive_available:
        raise SavedHealthArchiveError("saved_health_result_observed_after_archive")
    return "structurally_valid", baseline, baseline_witness


def _validate_baseline_result_identity(
    *,
    baseline: Mapping[str, Any],
    portfolio_id: str | None,
    snapshot_id: str | None,
    rows_hash: str | None,
    decision_date: str | None,
) -> None:
    if baseline.get("portfolio_id") != portfolio_id:
        raise SavedHealthArchiveError("saved_health_baseline_result_portfolio_mismatch")
    if baseline.get("source_snapshot_id") != snapshot_id:
        raise SavedHealthArchiveError("saved_health_baseline_result_snapshot_mismatch")
    if baseline.get("source_snapshot_rows_sha256") != rows_hash:
        raise SavedHealthArchiveError("saved_health_baseline_result_rows_hash_mismatch")
    if baseline.get("decision_date") != decision_date:
        raise SavedHealthArchiveError("saved_health_baseline_result_decision_date_mismatch")


def _validate_baseline_witness_pair(
    *,
    baseline: Mapping[str, Any],
    baseline_raw: bytes,
    baseline_name: str,
    baseline_witness: Mapping[str, Any],
) -> tuple[datetime, datetime]:
    expected_fields = {
        "schema_version",
        "producer",
        "status",
        "reason",
        "baseline_name",
        "baseline_sha256",
        "portfolio_id",
        "snapshot_id",
        "snapshot_date",
        "source_result_id",
        "source_decision_boundary",
        "source_decision_at",
        "source_snapshot_rows_sha256",
        "source_observed_at",
        "source_available_at",
        "positions",
        "research_only",
        "writes_positions_db",
        "auto_action_allowed",
        "broker_execution",
        "formal_credit",
        "saved_available_at",
    }
    if set(baseline_witness) != expected_fields:
        raise SavedHealthArchiveError("saved_health_baseline_witness_fields_invalid")
    if (
        not baseline_name
        or Path(baseline_name).name != baseline_name
        or "/" in baseline_name
        or "\\" in baseline_name
    ):
        raise SavedHealthArchiveError("saved_health_baseline_name_invalid")
    if baseline_witness.get("schema_version") != SAVED_BASELINE_WITNESS_SCHEMA:
        raise SavedHealthArchiveError("saved_health_baseline_witness_schema_invalid")
    if baseline_witness.get("producer") != SAVED_BASELINE_WITNESS_PRODUCER:
        raise SavedHealthArchiveError("saved_health_baseline_witness_producer_invalid")
    if baseline_witness.get("status") != "structurally_valid":
        raise SavedHealthArchiveError("saved_health_baseline_witness_unqualified")
    if baseline_witness.get("reason") != "":
        raise SavedHealthArchiveError("saved_health_baseline_witness_reason_invalid")
    if baseline_witness.get("research_only") is not True or any(
        baseline_witness.get(name) is not False
        for name in (
            "writes_positions_db",
            "auto_action_allowed",
            "broker_execution",
            "formal_credit",
        )
    ):
        raise SavedHealthArchiveError("saved_health_baseline_witness_boundary_invalid")
    expected_hash = _sha256(baseline_raw)
    expected_identity = {
        "baseline_name": baseline_name,
        "baseline_sha256": expected_hash,
        "portfolio_id": baseline.get("portfolio_id"),
        "snapshot_id": baseline.get("source_snapshot_id"),
        "snapshot_date": baseline.get("source_snapshot_date"),
        "source_result_id": baseline.get("source_result_id"),
        "source_decision_boundary": baseline.get("source_decision_boundary"),
        "source_decision_at": baseline.get("source_decision_at"),
        "source_snapshot_rows_sha256": baseline.get("source_snapshot_rows_sha256"),
        "source_observed_at": baseline.get("source_observed_at"),
        "source_available_at": baseline.get("source_available_at"),
    }
    for name, expected in expected_identity.items():
        if baseline_witness.get(name) != expected:
            raise SavedHealthArchiveError(f"saved_health_baseline_witness_{name}_mismatch")
    source_observed = _parse_aware_text(
        baseline.get("source_observed_at"), "source_observed_at"
    )
    witness_source_observed = _parse_aware_text(
        baseline_witness.get("source_observed_at"), "source_observed_at"
    )
    baseline_saved = _parse_aware_text(
        baseline_witness.get("saved_available_at"), "baseline_saved_available_at"
    )
    if source_observed != witness_source_observed:
        raise SavedHealthArchiveError("saved_health_baseline_witness_observed_mismatch")
    if baseline_saved < source_observed:
        raise SavedHealthArchiveError("saved_health_baseline_saved_before_source_observed")
    source_available_text = baseline.get("source_available_at")
    if source_available_text is not None:
        source_available = _parse_aware_text(
            source_available_text, "source_available_at"
        )
        if source_available > source_observed:
            raise SavedHealthArchiveError(
                "saved_health_source_available_after_source_observed"
            )
    if baseline.get("portfolio_id") != "paper-main":
        raise SavedHealthArchiveError("saved_health_preopen_portfolio_scope_invalid")
    if baseline.get("source_decision_boundary") != "paper-main-preopen":
        raise SavedHealthArchiveError("saved_health_preopen_boundary_missing")
    source_decision_at = _parse_aware_text(
        baseline.get("source_decision_at"), "source_decision_at"
    ).astimezone(_TAIPEI)
    if (
        source_decision_at.date().isoformat() != baseline.get("source_snapshot_date")
        or source_decision_at.hour >= 9
        or source_decision_at.astimezone(timezone.utc) > source_observed
    ):
        raise SavedHealthArchiveError("saved_health_preopen_clock_invalid")
    positions = baseline.get("positions")
    if not isinstance(positions, list):
        raise SavedHealthArchiveError("saved_health_baseline_positions_invalid")
    expected_positions: list[dict[str, Any]] = []
    for row in positions:
        if not isinstance(row, Mapping):
            raise SavedHealthArchiveError("saved_health_baseline_position_invalid")
        position_id = row.get("position_id")
        stock_code = row.get("stock_code")
        shares = row.get("paper_shares")
        if (
            not isinstance(position_id, str)
            or not position_id.strip()
            or not isinstance(stock_code, str)
            or not stock_code.strip()
            or isinstance(shares, bool)
            or not isinstance(shares, int)
            or shares <= 0
        ):
            raise SavedHealthArchiveError("saved_health_baseline_position_identity_invalid")
        expected_positions.append(
            {"position_id": position_id, "stock_code": stock_code, "paper_shares": shares}
        )
    if baseline_witness.get("positions") != expected_positions:
        raise SavedHealthArchiveError("saved_health_baseline_witness_positions_mismatch")
    return source_observed, baseline_saved


def _validate_result_archive_identity(
    result: Mapping[str, Any], receipt: Mapping[str, Any]
) -> None:
    if result.get("schema_version") != EVALUATOR_SCHEMA:
        raise SavedHealthArchiveError("saved_health_result_schema_invalid")
    if result.get("decision_date") != receipt.get("decision_date"):
        raise SavedHealthArchiveError("saved_health_result_decision_date_mismatch")
    if result.get("observed_at") != receipt.get("observed_at"):
        raise SavedHealthArchiveError("saved_health_result_observed_at_mismatch")
    if result.get("status") != receipt.get("status"):
        raise SavedHealthArchiveError("saved_health_result_status_mismatch")
    provenance = result.get("provenance")
    if not isinstance(provenance, Mapping):
        provenance = {}
    portfolio_id = _first_text(
        provenance.get("portfolio_id"),
        provenance.get("paper_portfolio_id"),
        provenance.get("source_portfolio_id"),
    )
    snapshot_id = _first_text(
        provenance.get("source_snapshot_id"), provenance.get("snapshot_id")
    )
    rows_hash = _first_text(
        provenance.get("source_snapshot_rows_sha256"),
        provenance.get("snapshot_rows_sha256"),
    )
    if portfolio_id != receipt.get("portfolio_id"):
        raise SavedHealthArchiveError("saved_health_result_portfolio_mismatch")
    if snapshot_id != receipt.get("source_snapshot_id"):
        raise SavedHealthArchiveError("saved_health_result_snapshot_mismatch")
    if rows_hash != receipt.get("source_snapshot_rows_sha256"):
        raise SavedHealthArchiveError("saved_health_result_snapshot_rows_hash_mismatch")
    for field_name in (
        "research_only",
        "apply_transition",
        "auto_action_allowed",
        "broker_execution",
        "formal_credit",
    ):
        expected = field_name == "research_only"
        if result.get(field_name) is not expected:
            raise SavedHealthArchiveError(f"saved_health_result_{field_name}_invalid")


def _validate_evaluator_result_shape(result: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "status",
        "decision_date",
        "observed_at",
        "policy_hash",
        "positions_count",
        "transition_proposals_count",
        "research_only",
        "apply_transition",
        "auto_action_allowed",
        "broker_execution",
        "formal_credit",
        "provenance",
        "warnings",
        "blockers",
        "positions",
    }
    optional = {
        "manual_action_required",
        "research_qualification_required",
        "baseline_path",
        "baseline_sha256",
    }
    if not required.issubset(result) or set(result) - required - optional:
        raise SavedHealthArchiveError("saved_health_result_fields_invalid")
    if result.get("schema_version") != EVALUATOR_SCHEMA:
        raise SavedHealthArchiveError("saved_health_result_schema_invalid")
    if result.get("status") not in {"passed", "degraded", "blocked"}:
        raise SavedHealthArchiveError("saved_health_result_status_invalid")
    for name in ("positions_count", "transition_proposals_count"):
        value = result.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise SavedHealthArchiveError(f"saved_health_result_{name}_invalid")
    if not isinstance(result.get("decision_date"), str):
        raise SavedHealthArchiveError("saved_health_result_decision_date_invalid")
    if not isinstance(result.get("observed_at"), str):
        raise SavedHealthArchiveError("saved_health_result_observed_at_invalid")
    if not isinstance(result.get("policy_hash"), str) or not result.get("policy_hash"):
        raise SavedHealthArchiveError("saved_health_result_policy_hash_invalid")
    if not isinstance(result.get("provenance"), Mapping):
        raise SavedHealthArchiveError("saved_health_result_provenance_invalid")
    for name in ("warnings", "blockers"):
        value = result.get(name)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise SavedHealthArchiveError(f"saved_health_result_{name}_invalid")
    positions = result.get("positions")
    if not isinstance(positions, list) or any(not isinstance(row, Mapping) for row in positions):
        raise SavedHealthArchiveError("saved_health_result_positions_invalid")
    if result["positions_count"] != len(positions):
        raise SavedHealthArchiveError("saved_health_result_positions_count_mismatch")
    for name in ("manual_action_required", "research_qualification_required"):
        if name in result and not isinstance(result[name], bool):
            raise SavedHealthArchiveError(f"saved_health_result_{name}_invalid")
    baseline_path = result.get("baseline_path")
    if baseline_path is not None and not isinstance(baseline_path, str):
        raise SavedHealthArchiveError("saved_health_result_baseline_path_invalid")
    baseline_hash = result.get("baseline_sha256")
    if baseline_hash is not None and not _valid_hash(baseline_hash):
        raise SavedHealthArchiveError("saved_health_result_baseline_hash_invalid")
    for field_name in (
        "research_only",
        "apply_transition",
        "auto_action_allowed",
        "broker_execution",
        "formal_credit",
    ):
        expected = field_name == "research_only"
        if result.get(field_name) is not expected:
            raise SavedHealthArchiveError(f"saved_health_result_{field_name}_invalid")


def _validate_receipt(
    receipt: Mapping[str, Any], *, receipt_id: str, result_sha256: str
) -> None:
    expected_fields = {
        "schema_version",
        "producer",
        "receipt_id",
        "result_path",
        "result_sha256",
        "source_witness_path",
        "source_witness_sha256",
        "source_witness_status",
        "source_witness_reason",
        "decision_date",
        "observed_at",
        "portfolio_id",
        "source_snapshot_id",
        "source_snapshot_rows_sha256",
        "status",
        "research_only",
        "apply_transition",
        "auto_action_allowed",
        "broker_execution",
        "formal_credit",
        "available_at",
    }
    if set(receipt) != expected_fields:
        raise SavedHealthArchiveError("saved_health_receipt_fields_invalid")
    if receipt.get("schema_version") != SAVED_HEALTH_RECEIPT_SCHEMA:
        raise SavedHealthArchiveError("saved_health_receipt_schema_invalid")
    if receipt.get("producer") != SAVED_HEALTH_PRODUCER:
        raise SavedHealthArchiveError("saved_health_receipt_producer_invalid")
    if receipt.get("receipt_id") != receipt_id or not _RECEIPT_ID_RE.fullmatch(
        receipt_id
    ):
        raise SavedHealthArchiveError("saved_health_receipt_identity_mismatch")
    if receipt.get("result_sha256") != result_sha256 or not _valid_hash(result_sha256):
        raise SavedHealthArchiveError("saved_health_receipt_result_hash_invalid")
    if receipt_id != f"phsr-v1-{result_sha256.removeprefix('sha256:')}":
        raise SavedHealthArchiveError("saved_health_receipt_hash_identity_mismatch")
    if receipt.get("status") not in {"passed", "degraded", "blocked"}:
        raise SavedHealthArchiveError("saved_health_receipt_status_invalid")
    if receipt.get("source_witness_status") not in {
        "structurally_valid",
        "missing",
        "unqualified",
        "invalid",
    }:
        raise SavedHealthArchiveError("saved_health_receipt_source_status_invalid")
    if not _text(receipt.get("result_path")):
        raise SavedHealthArchiveError("saved_health_receipt_result_path_missing")
    if not isinstance(receipt.get("source_witness_reason"), str):
        raise SavedHealthArchiveError("saved_health_receipt_source_reason_invalid")
    if receipt.get("observed_at") is not None and not isinstance(
        receipt.get("observed_at"), str
    ):
        raise SavedHealthArchiveError("saved_health_receipt_observed_at_invalid")
    _parse_aware_text(receipt.get("available_at"), "available_at")
    for field_name in (
        "research_only",
        "apply_transition",
        "auto_action_allowed",
        "broker_execution",
        "formal_credit",
    ):
        expected = field_name == "research_only"
        if receipt.get(field_name) is not expected:
            raise SavedHealthArchiveError(f"saved_health_receipt_{field_name}_invalid")
    for field_name in (
        "decision_date",
        "portfolio_id",
        "source_snapshot_id",
        "source_snapshot_rows_sha256",
    ):
        value = receipt.get(field_name)
        if value is not None and not isinstance(value, str):
            raise SavedHealthArchiveError(f"saved_health_receipt_{field_name}_invalid")
    if receipt.get("source_snapshot_rows_sha256") is not None and not _valid_hash(
        receipt.get("source_snapshot_rows_sha256")
    ):
        raise SavedHealthArchiveError("saved_health_receipt_snapshot_rows_hash_invalid")
    source_hash = receipt.get("source_witness_sha256")
    source_path = receipt.get("source_witness_path")
    if receipt.get("source_witness_status") == "structurally_valid":
        if not _valid_hash(source_hash) or not _text(source_path):
            raise SavedHealthArchiveError("saved_health_receipt_source_link_invalid")
    elif source_hash is not None or source_path is not None:
        raise SavedHealthArchiveError("saved_health_receipt_unqualified_source_link_invalid")


def _assess_daily_baseline(payload: Mapping[str, Any]) -> str:
    if payload.get("schema_version") != DAILY_BASELINE_SCHEMA:
        # 舊版 baseline 只能以降級歷史顯示，不能證明 Paper snapshot 具有不可變來源見證。
        return (
            "unqualified"
            if payload.get("schema_version") == LEGACY_BASELINE_SCHEMA
            else "invalid"
        )
    allowed_fields = {
        "schema_version",
        "status",
        "producer",
        "decision_date",
        "as_of_date",
        "source_path",
        "source_type",
        "source_snapshot_id",
        "source_snapshot_date",
        "source_result_id",
        "source_decision_boundary",
        "source_decision_at",
        "source_snapshot_rows_sha256",
        "source_observed_at",
        "source_available_at",
        "source_data_version",
        "paper_status_path",
        "paper_status_sha256",
        "previous_health_baseline_sha256",
        "previous_source_snapshot_id",
        "previous_source_snapshot_date",
        "entry_lineage_policy",
        "entry_lineage_verified",
        "entry_lineage_verified_codes",
        "entry_lineage_unproven_codes",
        "entry_lineage_historical_prior_codes",
        "entry_lineage_closed_prior_codes",
        "entry_lineage_source",
        "position_identity_source",
        "position_identity_verified_codes",
        "source_read_mode",
        "research_only",
        "source_scope",
        "manual_action_required",
        "writes_positions_db",
        "auto_action_allowed",
        "broker_execution",
        "formal_credit",
        "positions",
        "diagnostics",
        "warnings",
        "portfolio_id",
    }
    if set(payload) - allowed_fields:
        return "invalid"
    producer = payload.get("producer")
    if producer is not None and producer != DAILY_BASELINE_PRODUCER:
        return "invalid"
    if producer is None:
        return "unqualified"
    if payload.get("status") != "fresh":
        return "invalid"
    if payload.get("source_type") != "paper_snapshot_read_only":
        return "invalid"
    if payload.get("source_read_mode") != "sqlite_uri_mode_ro_and_query_only":
        return "invalid"
    if not (
        payload.get("research_only") is True
        and payload.get("writes_positions_db") is False
        and payload.get("auto_action_allowed") is False
        and payload.get("broker_execution") is False
        and payload.get("formal_credit") is False
    ):
        return "invalid"
    positions = payload.get("positions")
    if not isinstance(positions, list) or any(not isinstance(row, Mapping) for row in positions):
        return "invalid"
    allowed_position_fields = {
        "stock_code",
        "stock_name",
        "paper_shares",
        "paper_weight_bp",
        "state",
        "entry_thesis",
        "invalidation",
        "holding_horizon",
        "review_date",
        "source_scope",
        "required_human_fields",
        "required_governance_fields",
        "user_action_required",
        "reasons",
        "source_trace",
        "auto_action_allowed",
        "position_id",
        "entry_lineage_id",
        "position_identity_source",
        "entry_lineage_status",
        "historical_prior_state",
        "historical_prior_reasons",
        "historical_prior_source_snapshot_id",
        "historical_prior_health_fields",
        "state_projection_blocked",
    }
    if any(set(row) - allowed_position_fields for row in positions):
        return "invalid"
    position_ids: list[str] = []
    stock_codes: list[str] = []
    for row in positions:
        position_id = row.get("position_id")
        stock_code = row.get("stock_code")
        if not isinstance(position_id, str) or not position_id.strip():
            return "unqualified"
        if not isinstance(stock_code, str) or not stock_code.strip():
            return "unqualified"
        position_ids.append(position_id)
        stock_codes.append(stock_code)
    if len(position_ids) != len(set(position_ids)) or len(stock_codes) != len(set(stock_codes)):
        return "invalid"
    if not isinstance(payload.get("source_snapshot_id"), str) or not payload.get(
        "source_snapshot_id"
    ):
        return "unqualified"
    snapshot_date = payload.get("source_snapshot_date")
    decision_date = payload.get("decision_date")
    if not isinstance(snapshot_date, str) or not snapshot_date:
        return "unqualified"
    if snapshot_date != decision_date:
        return "invalid"
    try:
        parsed_snapshot_date = date.fromisoformat(snapshot_date)
    except ValueError:
        return "invalid"
    if parsed_snapshot_date.isoformat() != snapshot_date:
        return "invalid"
    if not _valid_hash(payload.get("source_snapshot_rows_sha256")):
        return "unqualified"
    if not isinstance(payload.get("portfolio_id"), str) or not payload.get(
        "portfolio_id"
    ):
        return "unqualified"
    source_result_id = payload.get("source_result_id")
    if not isinstance(source_result_id, str) or not source_result_id.strip():
        return "unqualified"
    if not isinstance(payload.get("source_observed_at"), str):
        return "unqualified"
    try:
        source_observed = _parse_aware_text(
            payload.get("source_observed_at"), "source_observed_at"
        )
    except ValueError:
        return "invalid"
    source_available_text = payload.get("source_available_at")
    if source_available_text is not None:
        try:
            source_available = _parse_aware_text(
                source_available_text, "source_available_at"
            )
        except ValueError:
            return "invalid"
        if source_available > source_observed:
            return "invalid"
    if payload.get("portfolio_id") != "paper-main":
        return "unqualified"
    if payload.get("source_decision_boundary") != "paper-main-preopen":
        return "unqualified"
    try:
        source_decision_at = _parse_aware_text(
            payload.get("source_decision_at"), "source_decision_at"
        ).astimezone(_TAIPEI)
    except ValueError:
        return "invalid"
    if (
        source_decision_at.date().isoformat() != snapshot_date
        or source_decision_at.hour >= 9
        or source_decision_at.astimezone(timezone.utc) > source_observed
    ):
        return "invalid"
    for row in positions:
        shares = row.get("paper_shares")
        if shares is None:
            return "unqualified"
        if isinstance(shares, bool) or not isinstance(shares, int):
            return "invalid"
        if shares <= 0:
            return "invalid"
        weight = row.get("paper_weight_bp")
        if weight is not None and (
            isinstance(weight, bool) or not isinstance(weight, int) or weight < 0
        ):
            return "invalid"
    return "structurally_valid"


def _path_from_receipt(root: Path, value: object, field_name: str) -> Path:
    if not isinstance(value, str) or not value:
        raise SavedHealthArchiveError(f"saved_health_{field_name}_missing")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise SavedHealthArchiveError(f"saved_health_{field_name}_invalid")
    if "\\" in value or ":" in value or "\x00" in value:
        raise SavedHealthArchiveError(f"saved_health_{field_name}_invalid")
    candidate = root.joinpath(*path.parts)
    return _contained_regular_path(candidate, root)


def _contained_regular_path(candidate: Path, root: Path) -> Path:
    root_abs = root.absolute()
    resolved_root = root_abs.resolve(strict=True)
    resolved = candidate.absolute().resolve(strict=True)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise SavedHealthArchiveError("saved_health_artifact_outside_root") from exc
    _reject_reparse_components(root_abs, candidate.absolute())
    return resolved


def _reject_reparse_components(root: Path, candidate: Path) -> None:
    root_abs = root.absolute()
    candidate_abs = candidate.absolute()
    try:
        relative = candidate_abs.relative_to(root_abs)
    except ValueError as exc:
        raise SavedHealthArchiveError("saved_health_artifact_outside_root") from exc
    current = Path(root_abs.anchor)
    absolute_parts = root_abs.parts[1:] + relative.parts
    for component in absolute_parts:
        current = current / component
        try:
            info = os.lstat(to_internal_io_path(current.absolute()))
        except FileNotFoundError as exc:
            raise SavedHealthArchiveError("saved_health_artifact_missing") from exc
        attributes = int(getattr(info, "st_file_attributes", 0))
        if stat.S_ISLNK(info.st_mode) or attributes & 0x400:
            raise SavedHealthArchiveError("saved_health_reparse_point_rejected")


def _read_stable_regular(path: Path, *, root: Path, max_bytes: int) -> bytes:
    _reject_reparse_components(root.absolute(), path.absolute())
    io_path = to_internal_io_path(path.absolute())
    before = os.lstat(io_path)
    _require_regular_single_link(before, max_bytes)
    with open(io_path, "rb") as stream:
        opened = os.fstat(stream.fileno())
        _require_same_file(before, opened)
        raw = stream.read(max_bytes + 1)
        after_open = os.fstat(stream.fileno())
    after = os.lstat(io_path)
    if len(raw) > max_bytes:
        raise SavedHealthArchiveError("saved_health_artifact_size_limit")
    _require_regular_single_link(after_open, max_bytes)
    _require_regular_single_link(after, max_bytes)
    if not (_same_stat(before, opened) and _same_stat(opened, after_open) and _same_stat(after_open, after)):
        raise SavedHealthArchiveError("saved_health_artifact_changed_during_read")
    if len(raw) != after.st_size:
        raise SavedHealthArchiveError("saved_health_artifact_size_changed")
    return raw


def _ensure_directory(root: Path, directory: Path) -> None:
    try:
        directory.relative_to(root)
    except ValueError as exc:
        raise SavedHealthArchiveError("saved_health_archive_directory_outside_root") from exc
    current = root
    root_io = to_internal_io_path(current.absolute())
    if not os.path.exists(root_io):
        os.makedirs(root_io, exist_ok=True)
    for component in directory.relative_to(root).parts:
        current = current / component
        io_current = to_internal_io_path(current.absolute())
        try:
            info = os.lstat(io_current)
        except FileNotFoundError:
            os.mkdir(io_current)
            info = os.lstat(io_current)
        attributes = int(getattr(info, "st_file_attributes", 0))
        if stat.S_ISLNK(info.st_mode) or attributes & 0x400 or not stat.S_ISDIR(info.st_mode):
            raise SavedHealthArchiveError("saved_health_archive_directory_unsafe")


def _create_immutable_bytes(path: Path, raw: bytes) -> None:
    os.makedirs(to_internal_io_path(path.parent.absolute()), exist_ok=True)
    if _lexists(path):
        existing = _read_stable_regular(path, root=path.parent.parent, max_bytes=max(len(raw), 1))
        if existing != raw:
            raise SavedHealthArchiveError("saved_health_immutable_identity_conflict")
        return
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{os.urandom(8).hex()}.tmp")
    temporary_io = to_internal_io_path(temporary.absolute())
    path_io = to_internal_io_path(path.absolute())
    descriptor = os.open(temporary_io, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            if os.name == "nt":
                # Windows 目的檔已存在時 rename 會失敗；發布仍具原子性且只能建立一次。
                os.rename(temporary_io, path_io)
            else:
                # POSIX 以 hard link 原子發布；identity 已存在時會直接失敗。
                os.link(temporary_io, path_io)
                os.unlink(temporary_io)
        except FileExistsError:
            existing = _read_stable_regular(
                path, root=path.parent.parent, max_bytes=max(len(raw), 1)
            )
            if existing != raw:
                raise SavedHealthArchiveError("saved_health_immutable_identity_conflict")
    finally:
        if os.path.lexists(temporary_io):
            os.unlink(temporary_io)


def _lexists(path: Path) -> bool:
    try:
        os.lstat(to_internal_io_path(path.absolute()))
    except FileNotFoundError:
        return False
    return True


def _require_regular_single_link(info: os.stat_result, max_bytes: int) -> None:
    attributes = int(getattr(info, "st_file_attributes", 0))
    if stat.S_ISLNK(info.st_mode) or attributes & 0x400:
        raise SavedHealthArchiveError("saved_health_reparse_point_rejected")
    if not stat.S_ISREG(info.st_mode):
        raise SavedHealthArchiveError("saved_health_artifact_not_regular")
    if int(getattr(info, "st_nlink", 1)) != 1:
        raise SavedHealthArchiveError("saved_health_hardlink_rejected")
    if info.st_size < 0 or info.st_size > max_bytes:
        raise SavedHealthArchiveError("saved_health_artifact_size_limit")


def _same_stat(left: os.stat_result, right: os.stat_result) -> bool:
    return _stat_signature(left) == _stat_signature(right)


def _require_same_file(left: os.stat_result, right: os.stat_result) -> None:
    if not _same_stat(left, right):
        raise SavedHealthArchiveError("saved_health_artifact_replaced_during_open")


def _stat_signature(info: os.stat_result) -> tuple[int, ...]:
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_mode),
        int(info.st_size),
        int(getattr(info, "st_mtime_ns", int(info.st_mtime * 1_000_000_000))),
        int(getattr(info, "st_ctime_ns", int(info.st_ctime * 1_000_000_000))),
        int(getattr(info, "st_nlink", 1)),
    )


def _strict_json_object(raw: bytes, field_name: str) -> dict[str, Any]:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise SavedHealthArchiveError(f"{field_name}_duplicate_json_key")
            output[key] = value
        return output

    def no_constant(value: str) -> None:
        raise SavedHealthArchiveError(f"{field_name}_nonstandard_json_constant")

    def no_float(value: str) -> None:
        raise SavedHealthArchiveError(f"{field_name}_floating_json_number_rejected")

    value = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=no_duplicates,
        parse_constant=no_constant,
        parse_float=no_float,
    )
    if not isinstance(value, dict):
        raise SavedHealthArchiveError(f"{field_name}_not_object")
    return value


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _valid_hash(value: object) -> bool:
    return isinstance(value, str) and bool(_HASH_RE.fullmatch(value))


def _required_hash(value: object) -> str:
    if not _valid_hash(value):
        raise SavedHealthArchiveError("saved_health_hash_invalid")
    return str(value)


def _parse_aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise SavedHealthArchiveError(f"saved_health_{field_name}_invalid_or_naive")
    return value.astimezone(timezone.utc)


def _parse_aware_text(value: object, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise SavedHealthArchiveError(f"saved_health_{field_name}_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SavedHealthArchiveError(f"saved_health_{field_name}_invalid") from exc
    return _parse_aware_datetime(parsed, field_name)


def _required_text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SavedHealthArchiveError("saved_health_required_text_missing")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SavedHealthArchiveError("saved_health_optional_text_invalid")
    return value


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _first_text(*values: object) -> str | None:
    for value in values:
        text = _text(value)
        if text:
            return text
    return None


def _writer_receipt_metadata(
    path: Path, raw: bytes, receipt: Mapping[str, Any]
) -> dict[str, str]:
    return {
        "receipt_id": str(receipt["receipt_id"]),
        "receipt_path": str(path),
        "receipt_sha256": _sha256(raw),
        "available_at": str(receipt["available_at"]),
        "source_witness_status": str(receipt["source_witness_status"]),
    }
