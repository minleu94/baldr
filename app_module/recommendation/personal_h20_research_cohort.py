"""原保存 H20 母體的唯讀研究列表；不推論、不保存預測副本。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Literal, Mapping

from app_module.recommendation.personal_current_observed_h20_capture import plain, require_digest
from app_module.recommendation.personal_h20_product_evidence import project_personal_h20_product_evidence
from app_module.recommendation.queries import _read_regular_file_no_follow, _stat_stability_key


@dataclass(frozen=True, slots=True)
class PersonalH20ResearchRow:
    symbol: str
    status: Literal["available", "unknown"]
    reason: str
    gross_return_bp: int | None
    decision_date: str
    source_date: str | None
    feature_as_of_date: str | None
    sample_id: str
    prediction_id: str
    capture_path: str
    capture_sha256: str
    observed_at: str | None = None


@dataclass(frozen=True, slots=True)
class PersonalH20ResearchCohort:
    manifest_path: str
    manifest_sha256: str
    candidate_id: str
    contract_hash: str
    cycle_id: str
    decision_date: str
    symbols: tuple[str, ...]
    rows: tuple[PersonalH20ResearchRow, ...]


@dataclass(frozen=True, slots=True)
class PersonalH20ResearchSelection:
    manifest_sha256: str
    candidate_id: str
    contract_hash: str
    cycle_id: str
    symbol: str
    sample_id: str
    prediction_id: str
    capture_sha256: str


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("personal_h20_research_exact_identity_required")
    return value


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    body: dict[str, Any] = {}
    for key, value in pairs:
        if key in body:
            raise ValueError("personal_h20_research_duplicate_json_key")
        body[key] = value
    return body


def _reject_constant(value: str) -> None:
    raise ValueError("personal_h20_research_nonfinite_json:" + value)


def _manifest_bytes(file: Path, root: Path, expected: str) -> bytes:
    require_digest(expected)
    if file.parent != root / "h20_daily_receipts" or file.name != expected[7:] + ".json":
        raise ValueError("personal_h20_research_manifest_outside_exact_store")
    plain(file, file=True)
    raw = _read_regular_file_no_follow(file, file.parent, max_bytes=64 * 1024)
    plain(file, file=True)
    if "sha256:" + hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("personal_h20_research_manifest_raw_pin_mismatch")
    return raw


def read_personal_h20_research_cohort(
    manifest_path: str | Path, *, root: str | Path, expected_sha256: str,
    prediction_reader: Callable[..., Mapping[str, Any]],
) -> PersonalH20ResearchCohort:
    """固定原 manifest 分母；逐列由注入的原 public reader 核原預測。"""
    if not callable(prediction_reader):
        raise ValueError("personal_h20_research_public_reader_required")
    store, file = Path(root), Path(manifest_path)
    raw = _manifest_bytes(file, store, expected_sha256)
    original_stat = _stat_stability_key(file.stat())
    body = json.loads(raw, object_pairs_hook=_unique, parse_constant=_reject_constant)
    if not isinstance(body, dict):
        raise ValueError("personal_h20_research_manifest_object_required")
    symbols, pins = body.get("symbols"), body.get("captures")
    if (body.get("schema_version") != "personal-h20-daily-manifest.v1"
            or body.get("status") != "completed" or not isinstance(symbols, list)
            or not 1 <= len(symbols) <= 50 or any(not isinstance(s, str) or not s for s in symbols)
            or symbols != sorted(set(symbols)) or not isinstance(pins, list)
            or len(pins) != len(symbols)
            or any(not isinstance(pin, dict) for pin in pins)
            or sorted(pin.get("symbol", "") for pin in pins) != symbols
            or any(body.get(k) is not False for k in
                   ("historical_pit_eligible", "formal_training_allowed", "production_action_allowed"))):
        raise ValueError("personal_h20_research_manifest_scope_mismatch")
    candidate, contract, cycle, decision = (_text(body[k]) for k in
                                           ("candidate_id", "contract_hash", "cycle_id", "decision_date"))
    require_digest(contract)
    date.fromisoformat(decision)
    # 先核全分母 pins；任何跨 store 或重複身分均拒絕整份 manifest。
    for pin in pins:
        for key in ("symbol", "sample_id", "prediction_id", "path", "raw_sha256"):
            _text(pin[key])
        require_digest(pin["raw_sha256"])
        path = Path(pin["path"])
        if (not path.is_absolute() or ".." in path.parts
                or path.parent != store / "h20_predictions" or path.suffix != ".json"):
            raise ValueError("personal_h20_research_capture_outside_exact_store")
    for key in ("sample_id", "prediction_id", "path"):
        if len({pin[key] for pin in pins}) != len(pins):
            raise ValueError("personal_h20_research_duplicate_capture_identity")
    rows: list[PersonalH20ResearchRow] = []
    for pin in pins:
        try:
            capture = prediction_reader(pin["path"], root=store, expected_sha256=pin["raw_sha256"])
        except InterruptedError:
            raise
        except Exception as exc:
            # 缺件／public reader 拒絕仍保留原成員與 pins，不拿舊值補未知。
            rows.append(PersonalH20ResearchRow(pin["symbol"], "unknown", str(exc)[:300], None,
                decision, None, None, pin["sample_id"], pin["prediction_id"], pin["path"], pin["raw_sha256"]))
            continue
        evidence = project_personal_h20_product_evidence(capture, stock_code=pin["symbol"],
            expected_candidate_id=candidate, expected_contract_hash=contract)
        if (capture["source_binding"]["cycle_id"] != cycle or evidence.decision_date != decision
                or evidence.sample_id != pin["sample_id"] or evidence.prediction_id != pin["prediction_id"]):
            raise ValueError("personal_h20_research_original_capture_scope_mismatch")
        rows.append(PersonalH20ResearchRow(pin["symbol"], "available", evidence.reason,
            evidence.gross_return_bp, decision, evidence.source_date, evidence.feature_date,
            pin["sample_id"], pin["prediction_id"], pin["path"], pin["raw_sha256"], evidence.observed_at))
    if (_manifest_bytes(file, store, expected_sha256) != raw
            or _stat_stability_key(file.stat()) != original_stat):
        raise ValueError("personal_h20_research_manifest_changed_during_read")
    return PersonalH20ResearchCohort(str(file), expected_sha256, candidate, contract, cycle,
                                    decision, tuple(symbols), tuple(rows))


def sort_personal_h20_research_rows(
    cohort: PersonalH20ResearchCohort, *, descending: bool = True,
) -> tuple[PersonalH20ResearchRow, ...]:
    """只排序本保存母體的 int bp；未知後置，同值按股票穩定排序。"""
    if type(descending) is not bool:
        raise ValueError("personal_h20_research_sort_direction_required")
    for row in cohort.rows:
        if ((row.status == "available" and type(row.gross_return_bp) is not int)
                or (row.status == "unknown" and row.gross_return_bp is not None)
                or row.status not in {"available", "unknown"}):
            raise ValueError("personal_h20_research_integer_gross_required")
    return tuple(sorted(cohort.rows, key=lambda row: (
        row.gross_return_bp is None,
        (-row.gross_return_bp if descending else row.gross_return_bp) if row.gross_return_bp is not None else 0,
        row.symbol,
    )))
