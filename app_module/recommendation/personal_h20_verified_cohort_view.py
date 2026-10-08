"""同次完整 H20 讀取完成後的程序內唯讀檢視。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import hashlib
import hmac
import json
import re
import secrets
from pathlib import Path
from typing import NoReturn, SupportsIndex
import uuid

from app_module.recommendation.personal_h20_product_evidence import (
    PersonalH20ProductEvidence,
    PersonalH20ProductReference,
)
from app_module.recommendation.personal_h20_research_cohort import (
    PersonalH20ResearchCohort,
    PersonalH20ResearchRow,
    PersonalH20ResearchSelection,
)


_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_CAPTURE_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_VIEW_SEAL_KEY = secrets.token_bytes(32)


@dataclass(frozen=True, slots=True)
class PersonalH20VerifiedRowPin:
    """固定列表中單列的可選取身分，不包含 capture 內容。"""

    symbol: str
    sample_id: str
    prediction_id: str
    capture_sha256: str
    row_identity_sha256: str

    def __post_init__(self) -> None:
        if any(type(value) is not str or not value for value in (
            self.symbol, self.sample_id, self.prediction_id,
        )):
            raise ValueError("personal_h20_verified_row_identity_required")
        if type(self.capture_sha256) is not str or _CAPTURE_DIGEST.fullmatch(self.capture_sha256) is None:
            raise ValueError("personal_h20_verified_row_capture_pin_required")
        if type(self.row_identity_sha256) is not str or _DIGEST.fullmatch(self.row_identity_sha256) is None:
            raise ValueError("personal_h20_verified_row_identity_digest_required")


@dataclass(frozen=True, slots=True, init=False)
class PersonalH20VerifiedCohortView:
    """不可序列化、只在完成同次 H20 讀取的程序內有效。"""

    view_id: str
    completed_at_utc: datetime
    reference: PersonalH20ProductReference
    cohort: PersonalH20ResearchCohort
    row_pins: tuple[PersonalH20VerifiedRowPin, ...]
    source_binding_identity_sha256: tuple[str, ...]
    contract_binding_identity_sha256: tuple[str, ...]
    sqlite_binding_identity_sha256: tuple[str, ...]
    config_path_identity_sha256: str
    market_root_identity_sha256: str
    personal_root_identity_sha256: str
    sqlite_read_root_identity_sha256: str
    _seal: bytes = field(repr=False, compare=False)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("personal_h20_verified_view_must_come_from_reader")

    def __reduce__(self) -> NoReturn:
        raise TypeError("personal_h20_verified_view_cannot_be_serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("personal_h20_verified_view_cannot_be_serialized")


def assert_personal_h20_verified_cohort_view(
    view: PersonalH20VerifiedCohortView,
) -> None:
    """重核程序內 seal 與所有列、來源、根目錄身分。"""

    if type(view) is not PersonalH20VerifiedCohortView:
        raise ValueError("personal_h20_verified_view_type_required")
    if (type(view.view_id) is not str or re.fullmatch(r"[0-9a-f]{32}", view.view_id) is None
            or type(view.completed_at_utc) is not datetime
            or view.completed_at_utc.tzinfo is None
            or view.completed_at_utc.utcoffset() != timezone.utc.utcoffset(view.completed_at_utc)):
        raise ValueError("personal_h20_verified_view_completion_identity_invalid")
    if type(view.reference) is not PersonalH20ProductReference:
        raise ValueError("personal_h20_verified_view_reference_type_required")
    if type(view.cohort) is not PersonalH20ResearchCohort:
        raise ValueError("personal_h20_verified_view_cohort_type_required")
    if type(view.row_pins) is not tuple:
        raise ValueError("personal_h20_verified_view_row_pins_tuple_required")
    if type(view.source_binding_identity_sha256) is not tuple:
        raise ValueError("personal_h20_verified_view_source_bindings_tuple_required")
    if type(view.contract_binding_identity_sha256) is not tuple:
        raise ValueError("personal_h20_verified_view_contract_bindings_tuple_required")
    if type(view.sqlite_binding_identity_sha256) is not tuple:
        raise ValueError("personal_h20_verified_view_sqlite_bindings_tuple_required")
    for values in (
        view.source_binding_identity_sha256,
        view.contract_binding_identity_sha256,
        view.sqlite_binding_identity_sha256,
    ):
        _validate_digest_tuple(values, field_name="personal_h20_verified_view_binding")
    for value in (
        view.config_path_identity_sha256,
        view.market_root_identity_sha256,
        view.personal_root_identity_sha256,
        view.sqlite_read_root_identity_sha256,
    ):
        _require_digest(value, field_name="personal_h20_verified_view_context")
    if view.row_pins != _row_pins(view.cohort):
        raise ValueError("personal_h20_verified_view_row_pins_mismatch")
    _validate_reference_and_cohort(view.reference, view.cohort)
    expected = _view_seal(view)
    if not isinstance(view._seal, bytes) or not hmac.compare_digest(view._seal, expected):
        raise ValueError("personal_h20_verified_view_seal_mismatch")


def project_personal_h20_verified_cohort_selection(
    view: PersonalH20VerifiedCohortView,
    selection: PersonalH20ResearchSelection,
) -> PersonalH20ProductEvidence:
    """純記憶體投影；不讀 manifest、capture、SQLite 或模型。"""

    assert_personal_h20_verified_cohort_view(view)
    if type(selection) is not PersonalH20ResearchSelection:
        raise ValueError("personal_h20_verified_selection_type_required")
    _validate_selection_context(view.cohort, selection)
    matches = tuple(row for row in view.cohort.rows if row.symbol == selection.symbol)
    if len(matches) != 1:
        raise ValueError("personal_h20_verified_selection_not_unique")
    row = matches[0]
    if row.status != "available":
        raise ValueError("personal_h20_verified_selection_not_available")
    row_pin_matches = tuple(pin for pin in view.row_pins if pin.symbol == row.symbol)
    if (len(row_pin_matches) != 1
            or row_pin_matches[0].sample_id != selection.sample_id
            or row_pin_matches[0].prediction_id != selection.prediction_id
            or row_pin_matches[0].capture_sha256 != selection.capture_sha256
            or row.sample_id != selection.sample_id
            or row.prediction_id != selection.prediction_id
            or row.capture_sha256 != selection.capture_sha256):
        raise ValueError("personal_h20_verified_selection_row_pin_mismatch")
    return _evidence_from_row(view.cohort, row)


def _issue_personal_h20_verified_cohort_view(
    *,
    reference: PersonalH20ProductReference,
    cohort: PersonalH20ResearchCohort,
    source_binding_identity_sha256: tuple[str, ...],
    contract_binding_identity_sha256: tuple[str, ...],
    sqlite_binding_identity_sha256: tuple[str, ...],
    config_path_identity_sha256: str,
    market_root_identity_sha256: str,
    personal_root_identity_sha256: str,
    sqlite_read_root_identity_sha256: str,
) -> PersonalH20VerifiedCohortView:
    """只供 scheduled reader 在所有終態守衛成功後簽發。"""

    _validate_reference_and_cohort(reference, cohort)
    if any(type(values) is not tuple for values in (
        source_binding_identity_sha256,
        contract_binding_identity_sha256,
        sqlite_binding_identity_sha256,
    )):
        raise ValueError("personal_h20_verified_view_binding_tuple_required")
    for binding_values in (
        source_binding_identity_sha256,
        contract_binding_identity_sha256,
        sqlite_binding_identity_sha256,
    ):
        _validate_digest_tuple(binding_values, field_name="personal_h20_verified_view_binding")
    for context_digest in (
        config_path_identity_sha256,
        market_root_identity_sha256,
        personal_root_identity_sha256,
        sqlite_read_root_identity_sha256,
    ):
        _require_digest(context_digest, field_name="personal_h20_verified_view_context")
    if any(row.status == "available" for row in cohort.rows) and any(
        not values for values in (
            source_binding_identity_sha256,
            contract_binding_identity_sha256,
            sqlite_binding_identity_sha256,
        )
    ):
        raise ValueError("personal_h20_verified_view_available_bindings_required")

    view = object.__new__(PersonalH20VerifiedCohortView)
    attributes: dict[str, object] = {
        "view_id": uuid.uuid4().hex,
        "completed_at_utc": datetime.now(timezone.utc),
        "reference": reference,
        "cohort": cohort,
        "row_pins": _row_pins(cohort),
        "source_binding_identity_sha256": tuple(sorted(source_binding_identity_sha256)),
        "contract_binding_identity_sha256": tuple(sorted(contract_binding_identity_sha256)),
        "sqlite_binding_identity_sha256": tuple(sorted(sqlite_binding_identity_sha256)),
        "config_path_identity_sha256": config_path_identity_sha256,
        "market_root_identity_sha256": market_root_identity_sha256,
        "personal_root_identity_sha256": personal_root_identity_sha256,
        "sqlite_read_root_identity_sha256": sqlite_read_root_identity_sha256,
    }
    for name, attribute_value in attributes.items():
        object.__setattr__(view, name, attribute_value)
    object.__setattr__(view, "_seal", _view_seal(view))
    assert_personal_h20_verified_cohort_view(view)
    return view


def _view_seal(view: PersonalH20VerifiedCohortView) -> bytes:
    raw = json.dumps(
        _view_payload(view),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hmac.new(_VIEW_SEAL_KEY, raw, hashlib.sha256).digest()


def _view_payload(view: PersonalH20VerifiedCohortView) -> dict[str, object]:
    return {
        "schema": "personal-h20-verified-cohort-view.v1",
        "view_id": view.view_id,
        "completed_at_utc": view.completed_at_utc.isoformat(),
        "reference": {
            "activation": view.reference.activation.to_dict(),
            "manifest_path": str(view.reference.manifest_path),
            "manifest_sha256": view.reference.manifest_sha256,
            "cycle_id": view.reference.cycle_id,
            "decision_date": view.reference.decision_date,
            "reference_sha256": view.reference.reference_sha256,
        },
        "cohort": _cohort_payload(view.cohort),
        "row_pins": [
            {
                "symbol": pin.symbol,
                "sample_id": pin.sample_id,
                "prediction_id": pin.prediction_id,
                "capture_sha256": pin.capture_sha256,
                "row_identity_sha256": pin.row_identity_sha256,
            }
            for pin in view.row_pins
        ],
        "source_binding_identity_sha256": list(view.source_binding_identity_sha256),
        "contract_binding_identity_sha256": list(view.contract_binding_identity_sha256),
        "sqlite_binding_identity_sha256": list(view.sqlite_binding_identity_sha256),
        "config_path_identity_sha256": view.config_path_identity_sha256,
        "market_root_identity_sha256": view.market_root_identity_sha256,
        "personal_root_identity_sha256": view.personal_root_identity_sha256,
        "sqlite_read_root_identity_sha256": view.sqlite_read_root_identity_sha256,
    }


def _cohort_payload(cohort: PersonalH20ResearchCohort) -> dict[str, object]:
    return {
        "manifest_path": cohort.manifest_path,
        "manifest_sha256": cohort.manifest_sha256,
        "candidate_id": cohort.candidate_id,
        "contract_hash": cohort.contract_hash,
        "cycle_id": cohort.cycle_id,
        "decision_date": cohort.decision_date,
        "symbols": list(cohort.symbols),
        "rows": [_row_payload(row) for row in cohort.rows],
    }


def _row_payload(row: PersonalH20ResearchRow) -> dict[str, object]:
    return {
        "symbol": row.symbol,
        "status": row.status,
        "reason": row.reason,
        "gross_return_bp": row.gross_return_bp,
        "decision_date": row.decision_date,
        "source_date": row.source_date,
        "feature_as_of_date": row.feature_as_of_date,
        "sample_id": row.sample_id,
        "prediction_id": row.prediction_id,
        "capture_path": row.capture_path,
        "capture_sha256": row.capture_sha256,
        "observed_at": row.observed_at,
    }


def _row_pins(cohort: PersonalH20ResearchCohort) -> tuple[PersonalH20VerifiedRowPin, ...]:
    return tuple(
        PersonalH20VerifiedRowPin(
            symbol=row.symbol,
            sample_id=row.sample_id,
            prediction_id=row.prediction_id,
            capture_sha256=row.capture_sha256,
            row_identity_sha256=hashlib.sha256(
                json.dumps(
                    _row_payload(row),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest(),
        )
        for row in cohort.rows
    )


def _validate_reference_and_cohort(
    reference: PersonalH20ProductReference,
    cohort: PersonalH20ResearchCohort,
) -> None:
    if type(reference) is not PersonalH20ProductReference:
        raise ValueError("personal_h20_verified_view_reference_type_required")
    if type(cohort) is not PersonalH20ResearchCohort:
        raise ValueError("personal_h20_verified_view_cohort_type_required")
    if (_CAPTURE_DIGEST.fullmatch(reference.manifest_sha256) is None
            or _CAPTURE_DIGEST.fullmatch(cohort.manifest_sha256) is None
            or Path(cohort.manifest_path) != reference.manifest_path
            or cohort.manifest_sha256 != reference.manifest_sha256
            or cohort.cycle_id != reference.cycle_id
            or cohort.decision_date != reference.decision_date
            or cohort.candidate_id != reference.activation.candidate_id
            or cohort.contract_hash != reference.activation.model_contract_hash):
        raise ValueError("personal_h20_verified_view_reference_cohort_mismatch")
    if (type(cohort.symbols) is not tuple or not 1 <= len(cohort.symbols) <= 50
            or cohort.symbols != tuple(sorted(set(cohort.symbols)))
            or type(cohort.rows) is not tuple
            or tuple(row.symbol for row in cohort.rows) != cohort.symbols
            or any(type(row) is not PersonalH20ResearchRow for row in cohort.rows)):
        raise ValueError("personal_h20_verified_view_full_cohort_required")
    if not cohort.rows:
        raise ValueError("personal_h20_verified_view_rows_required")
    for row in cohort.rows:
        if (not row.symbol or row.status not in {"available", "unknown"}
                or type(row.reason) is not str
                or type(row.capture_sha256) is not str
                or _CAPTURE_DIGEST.fullmatch(row.capture_sha256) is None):
            raise ValueError("personal_h20_verified_view_row_pin_invalid")
        if row.status == "available":
            _evidence_from_row(cohort, row)
        elif row.gross_return_bp is not None:
            raise ValueError("personal_h20_verified_view_unknown_row_has_value")


def _validate_selection_context(
    cohort: PersonalH20ResearchCohort,
    selection: PersonalH20ResearchSelection,
) -> None:
    if (selection.manifest_sha256 != cohort.manifest_sha256
            or selection.candidate_id != cohort.candidate_id
            or selection.contract_hash != cohort.contract_hash
            or selection.cycle_id != cohort.cycle_id):
        raise ValueError("personal_h20_verified_selection_context_mismatch")


def _evidence_from_row(
    cohort: PersonalH20ResearchCohort,
    row: PersonalH20ResearchRow,
) -> PersonalH20ProductEvidence:
    if row.status != "available":
        raise ValueError("personal_h20_verified_selection_not_available")
    return PersonalH20ProductEvidence(
        stock_code=row.symbol,
        status="available",
        reason=row.reason,
        gross_return_bp=row.gross_return_bp,
        decision_date=row.decision_date,
        source_date=row.source_date,
        feature_date=row.feature_as_of_date,
        observed_at=row.observed_at,
        candidate_id=cohort.candidate_id,
        sample_id=row.sample_id,
        prediction_id=row.prediction_id,
    )


def _validate_digest_tuple(values: tuple[str, ...], *, field_name: str) -> None:
    if any(type(value) is not str or _DIGEST.fullmatch(value) is None for value in values):
        raise ValueError(field_name + "_digest_invalid")
    if values != tuple(sorted(set(values))):
        raise ValueError(field_name + "_digest_tuple_not_canonical")


def _require_digest(value: str, *, field_name: str) -> None:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise ValueError(field_name + "_digest_invalid")


__all__ = [
    "PersonalH20VerifiedCohortView",
    "PersonalH20VerifiedRowPin",
    "assert_personal_h20_verified_cohort_view",
    "project_personal_h20_verified_cohort_selection",
]
