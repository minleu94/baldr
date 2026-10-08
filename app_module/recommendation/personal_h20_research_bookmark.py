"""固定原 H20 母體的研究收藏；不複製預測，也不讀取最新指標。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Literal, NoReturn, cast

from app_module.personal_data_paths import PersonalDataPaths, _absolute
from app_module.personal_store_selection import assert_personal_store_path
from app_module.recommendation.personal_h20_activation import (
    PersonalH20Activation,
    _activation_paths,
    read_personal_h20_activation,
)
from app_module.recommendation.personal_h20_product_evidence import (
    PersonalH20ProductReference,
)
from app_module.recommendation.personal_h20_research_cohort import (
    PersonalH20ResearchCohort,
    PersonalH20ResearchRow,
    PersonalH20ResearchSelection,
    read_personal_h20_research_cohort,
)
from app_module.recommendation.queries import _read_regular_file_no_follow


PERSONAL_H20_RESEARCH_BOOKMARK_SCHEMA = "personal-h20-research-bookmark.v1"
PERSONAL_H20_RESEARCH_BOOKMARK_SOURCE = "personal_h20_research_bookmark"
PERSONAL_H20_RESEARCH_BOOKMARK_MAX_BYTES = 64 * 1024
PERSONAL_H20_RESEARCH_BOOKMARK_MAX_SCROLL = 2**31 - 1
_ACTIVATION_MAX_BYTES = 64 * 1024
_SHA256_PREFIXED_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SCOPE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_TEXT_MAX_CHARS = 512

_SELECTION_KEYS = frozenset({
    "manifest_sha256",
    "candidate_id",
    "contract_hash",
    "cycle_id",
    "symbol",
    "sample_id",
    "prediction_id",
    "capture_sha256",
})
_BOOKMARK_BODY_KEYS = frozenset({
    "schema_version",
    "source",
    "manifest_sha256",
    "market_root_identity_sha256",
    "personal_root_identity_sha256",
    "activation_scope_id",
    "source_activation_revision",
    "source_candidate_id",
    "source_contract_hash",
    "cycle_id",
    "decision_date",
    "source_reference_sha256",
    "selected_row",
    "sort_descending",
    "scroll_position",
})
_BOOKMARK_KEYS = _BOOKMARK_BODY_KEYS | {"bookmark_identity_sha256"}


class PersonalH20ResearchBookmarkError(ValueError):
    """H20 收藏格式、原來源或目前核准路徑無法驗證。"""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


def _fail(code: str, message: str | None = None) -> NoReturn:
    raise PersonalH20ResearchBookmarkError(code, message)


def _reject_float_tree(value: object) -> None:
    if isinstance(value, float):
        _fail("personal_h20_bookmark_float_forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("personal_h20_bookmark_json_key_invalid")
            _reject_float_tree(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_float_tree(item)


def _canonical_json_bytes(value: object) -> bytes:
    _reject_float_tree(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PersonalH20ResearchBookmarkError(
            "personal_h20_bookmark_json_invalid"
        ) from exc


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _parse_json(raw: bytes | str) -> object:
    try:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if len(encoded) > PERSONAL_H20_RESEARCH_BOOKMARK_MAX_BYTES:
            _fail("personal_h20_bookmark_byte_limit")

        def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, item in pairs:
                if key in result:
                    _fail("personal_h20_bookmark_duplicate_json_key")
                result[key] = item
            return result

        def reject_constant(value: str) -> NoReturn:
            _fail("personal_h20_bookmark_json_constant_invalid", value)

        def reject_float(value: str) -> NoReturn:
            _fail("personal_h20_bookmark_float_forbidden", value)

        value = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
            parse_float=reject_float,
        )
        _reject_float_tree(value)
        if _canonical_json_bytes(value) != encoded:
            _fail("personal_h20_bookmark_json_noncanonical")
        return value
    except PersonalH20ResearchBookmarkError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise PersonalH20ResearchBookmarkError(
            "personal_h20_bookmark_json_invalid"
        ) from exc


def _text(value: object, code: str, *, max_chars: int = _TEXT_MAX_CHARS) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > max_chars
    ):
        _fail(code)
    return value


def _sha256_prefixed(value: object, code: str) -> str:
    if not isinstance(value, str) or _SHA256_PREFIXED_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _root_identity_sha256(value: str | Path) -> str:
    """雜湊 canonical approved root，不把私人絕對路徑寫入收藏。"""
    raw_path = Path(value)
    if not raw_path.is_absolute() or ".." in raw_path.parts:
        _fail("personal_h20_bookmark_absolute_root_required")
    try:
        canonical = _absolute(raw_path)
    except Exception as exc:
        raise PersonalH20ResearchBookmarkError(
            "personal_h20_bookmark_root_unavailable", str(exc)[:300]
        ) from exc
    if canonical != raw_path:
        _fail("personal_h20_bookmark_root_not_canonical")
    rendered = os.path.normcase(str(canonical)).replace("\\", "/")
    identity = {
        "schema_version": "personal-h20-approved-root-identity.v1",
        "canonical_root": rendered,
    }
    return "sha256:" + _sha256_json(identity)


def _selection_payload(selection: PersonalH20ResearchSelection) -> dict[str, str]:
    return {
        "manifest_sha256": selection.manifest_sha256,
        "candidate_id": selection.candidate_id,
        "contract_hash": selection.contract_hash,
        "cycle_id": selection.cycle_id,
        "symbol": selection.symbol,
        "sample_id": selection.sample_id,
        "prediction_id": selection.prediction_id,
        "capture_sha256": selection.capture_sha256,
    }


def _selection_from_payload(value: object) -> PersonalH20ResearchSelection:
    if not isinstance(value, Mapping) or set(value) != _SELECTION_KEYS:
        _fail("personal_h20_bookmark_selection_fields_invalid")
    manifest_sha256 = _sha256_prefixed(
        value["manifest_sha256"], "personal_h20_bookmark_manifest_sha256_invalid"
    )
    contract_hash = _sha256_prefixed(
        value["contract_hash"], "personal_h20_bookmark_contract_hash_invalid"
    )
    capture_sha256 = _sha256_prefixed(
        value["capture_sha256"], "personal_h20_bookmark_capture_sha256_invalid"
    )
    return PersonalH20ResearchSelection(
        manifest_sha256=manifest_sha256,
        candidate_id=_text(value["candidate_id"], "personal_h20_bookmark_candidate_invalid"),
        contract_hash=contract_hash,
        cycle_id=_text(value["cycle_id"], "personal_h20_bookmark_cycle_invalid"),
        symbol=_text(value["symbol"], "personal_h20_bookmark_symbol_invalid", max_chars=32),
        sample_id=_text(value["sample_id"], "personal_h20_bookmark_sample_invalid"),
        prediction_id=_text(value["prediction_id"], "personal_h20_bookmark_prediction_invalid"),
        capture_sha256=capture_sha256,
    )


def _bookmark_body(
    *,
    manifest_sha256: str,
    market_root_identity_sha256: str,
    personal_root_identity_sha256: str,
    activation_scope_id: str,
    source_activation_revision: int,
    source_candidate_id: str,
    source_contract_hash: str,
    cycle_id: str,
    decision_date: str,
    source_reference_sha256: str,
    selected_row: PersonalH20ResearchSelection,
    sort_descending: bool,
    scroll_position: int,
) -> dict[str, Any]:
    return {
        "schema_version": PERSONAL_H20_RESEARCH_BOOKMARK_SCHEMA,
        "source": PERSONAL_H20_RESEARCH_BOOKMARK_SOURCE,
        "manifest_sha256": manifest_sha256,
        "market_root_identity_sha256": market_root_identity_sha256,
        "personal_root_identity_sha256": personal_root_identity_sha256,
        "activation_scope_id": activation_scope_id,
        "source_activation_revision": source_activation_revision,
        "source_candidate_id": source_candidate_id,
        "source_contract_hash": source_contract_hash,
        "cycle_id": cycle_id,
        "decision_date": decision_date,
        "source_reference_sha256": source_reference_sha256,
        "selected_row": _selection_payload(selected_row),
        "sort_descending": sort_descending,
        "scroll_position": scroll_position,
    }


def _validate_bookmark_payload(payload: object) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or set(payload) != _BOOKMARK_KEYS:
        _fail("personal_h20_bookmark_fields_invalid")
    body = dict(payload)
    if body["schema_version"] != PERSONAL_H20_RESEARCH_BOOKMARK_SCHEMA:
        _fail("personal_h20_bookmark_schema_invalid")
    if body["source"] != PERSONAL_H20_RESEARCH_BOOKMARK_SOURCE:
        _fail("personal_h20_bookmark_source_invalid")

    manifest_sha256 = _sha256_prefixed(
        body["manifest_sha256"], "personal_h20_bookmark_manifest_sha256_invalid"
    )
    market_root_identity_sha256 = _sha256_prefixed(
        body["market_root_identity_sha256"], "personal_h20_bookmark_market_root_identity_invalid"
    )
    personal_root_identity_sha256 = _sha256_prefixed(
        body["personal_root_identity_sha256"], "personal_h20_bookmark_personal_root_identity_invalid"
    )
    activation_scope_id = _text(body["activation_scope_id"], "personal_h20_bookmark_scope_invalid", max_chars=100)
    if _SCOPE_RE.fullmatch(activation_scope_id) is None:
        _fail("personal_h20_bookmark_scope_invalid")
    source_activation_revision = body["source_activation_revision"]
    if type(source_activation_revision) is not int or source_activation_revision < 1:
        _fail("personal_h20_bookmark_activation_revision_invalid")
    source_candidate_id = _text(
        body["source_candidate_id"], "personal_h20_bookmark_candidate_invalid"
    )
    source_contract_hash = _sha256_prefixed(
        body["source_contract_hash"], "personal_h20_bookmark_contract_hash_invalid"
    )
    cycle_id = _text(body["cycle_id"], "personal_h20_bookmark_cycle_invalid")
    decision_date = _text(body["decision_date"], "personal_h20_bookmark_decision_date_invalid", max_chars=10)
    try:
        parsed_date = date.fromisoformat(decision_date)
    except ValueError as exc:
        raise PersonalH20ResearchBookmarkError(
            "personal_h20_bookmark_decision_date_invalid"
        ) from exc
    if parsed_date.isoformat() != decision_date:
        _fail("personal_h20_bookmark_decision_date_invalid")
    source_reference_sha256 = _sha256_prefixed(
        body["source_reference_sha256"], "personal_h20_bookmark_reference_sha256_invalid"
    )
    selected_row = _selection_from_payload(body["selected_row"])
    if (
        selected_row.manifest_sha256 != manifest_sha256
        or selected_row.candidate_id != source_candidate_id
        or selected_row.contract_hash != source_contract_hash
        or selected_row.cycle_id != cycle_id
    ):
        _fail("personal_h20_bookmark_selection_scope_mismatch")
    sort_descending = body["sort_descending"]
    if type(sort_descending) is not bool:
        _fail("personal_h20_bookmark_sort_direction_invalid")
    scroll_position = body["scroll_position"]
    if (
        type(scroll_position) is not int
        or not 0 <= scroll_position <= PERSONAL_H20_RESEARCH_BOOKMARK_MAX_SCROLL
    ):
        _fail("personal_h20_bookmark_scroll_invalid")

    identity = body["bookmark_identity_sha256"]
    if not isinstance(identity, str) or _SHA256_RE.fullmatch(identity) is None:
        _fail("personal_h20_bookmark_identity_invalid")
    identity_body = {key: value for key, value in body.items() if key != "bookmark_identity_sha256"}
    if _sha256_json(identity_body) != identity:
        _fail("personal_h20_bookmark_identity_mismatch")
    body["selected_row"] = selected_row
    return body


@dataclass(frozen=True, slots=True)
class PersonalH20ResearchBookmark:
    """固定原 manifest、單一 H20 股票與列表顯示位置的 immutable 收藏。"""

    manifest_sha256: str
    market_root_identity_sha256: str
    personal_root_identity_sha256: str
    activation_scope_id: str
    source_activation_revision: int
    source_candidate_id: str
    source_contract_hash: str
    cycle_id: str
    decision_date: str
    source_reference_sha256: str
    selected_row: PersonalH20ResearchSelection
    sort_descending: bool
    scroll_position: int
    bookmark_identity_sha256: str

    def __post_init__(self) -> None:
        payload = _bookmark_body(
            manifest_sha256=self.manifest_sha256,
            market_root_identity_sha256=self.market_root_identity_sha256,
            personal_root_identity_sha256=self.personal_root_identity_sha256,
            activation_scope_id=self.activation_scope_id,
            source_activation_revision=self.source_activation_revision,
            source_candidate_id=self.source_candidate_id,
            source_contract_hash=self.source_contract_hash,
            cycle_id=self.cycle_id,
            decision_date=self.decision_date,
            source_reference_sha256=self.source_reference_sha256,
            selected_row=self.selected_row,
            sort_descending=self.sort_descending,
            scroll_position=self.scroll_position,
        )
        payload["bookmark_identity_sha256"] = self.bookmark_identity_sha256
        _validate_bookmark_payload(payload)

    @classmethod
    def from_dict(cls, payload: object) -> PersonalH20ResearchBookmark:
        parsed = _validate_bookmark_payload(payload)
        return cls(
            manifest_sha256=cast(str, parsed["manifest_sha256"]),
            market_root_identity_sha256=cast(str, parsed["market_root_identity_sha256"]),
            personal_root_identity_sha256=cast(str, parsed["personal_root_identity_sha256"]),
            activation_scope_id=cast(str, parsed["activation_scope_id"]),
            source_activation_revision=cast(int, parsed["source_activation_revision"]),
            source_candidate_id=cast(str, parsed["source_candidate_id"]),
            source_contract_hash=cast(str, parsed["source_contract_hash"]),
            cycle_id=cast(str, parsed["cycle_id"]),
            decision_date=cast(str, parsed["decision_date"]),
            source_reference_sha256=cast(str, parsed["source_reference_sha256"]),
            selected_row=cast(PersonalH20ResearchSelection, parsed["selected_row"]),
            sort_descending=cast(bool, parsed["sort_descending"]),
            scroll_position=cast(int, parsed["scroll_position"]),
            bookmark_identity_sha256=cast(str, parsed["bookmark_identity_sha256"]),
        )

    @classmethod
    def from_json(cls, raw: bytes | str) -> PersonalH20ResearchBookmark:
        return cls.from_dict(_parse_json(raw))

    def to_dict(self) -> dict[str, Any]:
        body = _bookmark_body(
            manifest_sha256=self.manifest_sha256,
            market_root_identity_sha256=self.market_root_identity_sha256,
            personal_root_identity_sha256=self.personal_root_identity_sha256,
            activation_scope_id=self.activation_scope_id,
            source_activation_revision=self.source_activation_revision,
            source_candidate_id=self.source_candidate_id,
            source_contract_hash=self.source_contract_hash,
            cycle_id=self.cycle_id,
            decision_date=self.decision_date,
            source_reference_sha256=self.source_reference_sha256,
            selected_row=self.selected_row,
            sort_descending=self.sort_descending,
            scroll_position=self.scroll_position,
        )
        payload = {**body, "bookmark_identity_sha256": self.bookmark_identity_sha256}
        _validate_bookmark_payload(payload)
        if len(_canonical_json_bytes(payload)) > PERSONAL_H20_RESEARCH_BOOKMARK_MAX_BYTES:
            _fail("personal_h20_bookmark_byte_limit")
        return payload

    def to_json(self) -> str:
        return _canonical_json_bytes(self.to_dict()).decode("utf-8")

    @property
    def identity_sha256(self) -> str:
        return self.bookmark_identity_sha256

    @property
    def bookmark_id(self) -> str:
        return self.bookmark_identity_sha256

    @property
    def source_id(self) -> str:
        return self.bookmark_identity_sha256

    @property
    def stock_code(self) -> str:
        return self.selected_row.symbol

    @property
    def source(self) -> str:
        return PERSONAL_H20_RESEARCH_BOOKMARK_SOURCE


@dataclass(frozen=True, slots=True)
class PersonalH20ResearchBookmarkState:
    """精確重開後的 H20 名單；狀態不代表模型已載入或可執行。"""

    bookmark: PersonalH20ResearchBookmark
    cohort: PersonalH20ResearchCohort
    selected_row: PersonalH20ResearchRow
    current_model_binding_status: Literal[
        "enabled_same_contract", "disabled", "enabled_other_contract"
    ]


def _check_cancel(callback: Callable[[], bool] | None) -> None:
    if callback is None:
        return
    try:
        value = callback()
    except Exception as exc:
        raise PersonalH20ResearchBookmarkError(
            "personal_h20_bookmark_cancel_check_failed"
        ) from exc
    if type(value) is not bool:
        _fail("personal_h20_bookmark_cancel_callback_invalid")
    if value:
        raise InterruptedError("personal_h20_bookmark_cancelled")


def _coerce_bookmark(
    value: PersonalH20ResearchBookmark | Mapping[str, object] | bytes | str,
) -> PersonalH20ResearchBookmark:
    if isinstance(value, PersonalH20ResearchBookmark):
        return PersonalH20ResearchBookmark.from_dict(value.to_dict())
    if isinstance(value, (bytes, str)):
        return PersonalH20ResearchBookmark.from_json(value)
    return PersonalH20ResearchBookmark.from_dict(value)


def _selection_for_row(
    cohort: PersonalH20ResearchCohort,
    row: PersonalH20ResearchRow,
) -> PersonalH20ResearchSelection:
    return PersonalH20ResearchSelection(
        cohort.manifest_sha256,
        cohort.candidate_id,
        cohort.contract_hash,
        cohort.cycle_id,
        row.symbol,
        row.sample_id,
        row.prediction_id,
        row.capture_sha256,
    )


def create_personal_h20_research_bookmark(
    reference: PersonalH20ProductReference,
    cohort: PersonalH20ResearchCohort,
    selection: PersonalH20ResearchSelection,
    *,
    sort_descending: bool,
    scroll_position: int,
) -> PersonalH20ResearchBookmark:
    """建立只含已核 H20 原來源 pins 與列表位置的收藏，不存預測值。"""
    if not isinstance(reference, PersonalH20ProductReference):
        _fail("personal_h20_bookmark_verified_reference_required")
    if not isinstance(cohort, PersonalH20ResearchCohort):
        _fail("personal_h20_bookmark_verified_cohort_required")
    if not isinstance(selection, PersonalH20ResearchSelection):
        _fail("personal_h20_bookmark_selection_required")
    if type(sort_descending) is not bool:
        _fail("personal_h20_bookmark_sort_direction_invalid")
    if (
        type(scroll_position) is not int
        or not 0 <= scroll_position <= PERSONAL_H20_RESEARCH_BOOKMARK_MAX_SCROLL
    ):
        _fail("personal_h20_bookmark_scroll_invalid")

    activation = reference.activation
    if not isinstance(activation, PersonalH20Activation) or not activation.enabled:
        _fail("personal_h20_bookmark_enabled_source_activation_required")
    manifest_sha256 = _sha256_prefixed(
        reference.manifest_sha256, "personal_h20_bookmark_manifest_sha256_invalid"
    )
    reference_sha256 = _sha256_prefixed(
        reference.reference_sha256, "personal_h20_bookmark_reference_sha256_invalid"
    )
    root = Path(activation.personal_root)
    market_root = Path(activation.market_root)
    expected_manifest_path = root / "h20_daily_receipts" / (manifest_sha256[7:] + ".json")
    if (
        Path(reference.manifest_path) != expected_manifest_path
        or Path(cohort.manifest_path) != expected_manifest_path
        or cohort.manifest_sha256 != manifest_sha256
        or reference.cycle_id != cohort.cycle_id
        or reference.decision_date != cohort.decision_date
        or activation.candidate_id != cohort.candidate_id
        or activation.model_contract_hash != cohort.contract_hash
    ):
        _fail("personal_h20_bookmark_reference_cohort_mismatch")
    try:
        date.fromisoformat(cohort.decision_date)
        paths = _activation_paths(activation.market_root, activation.personal_root)
        assert_personal_store_path(paths, activation.config_path)
        assert_personal_store_path(paths, expected_manifest_path)
    except Exception as exc:
        if isinstance(exc, PersonalH20ResearchBookmarkError):
            raise
        raise PersonalH20ResearchBookmarkError(
            "personal_h20_bookmark_approved_source_path_rejected", str(exc)[:300]
        ) from exc

    rows = tuple(row for row in cohort.rows if row.symbol == selection.symbol)
    if len(rows) != 1:
        _fail("personal_h20_bookmark_selected_stock_not_in_cohort")
    row = rows[0]
    if row.status != "available" or type(row.gross_return_bp) is not int:
        _fail("personal_h20_bookmark_selected_row_not_available")
    if _selection_for_row(cohort, row) != selection:
        _fail("personal_h20_bookmark_selected_row_pin_mismatch")

    body = _bookmark_body(
        manifest_sha256=manifest_sha256,
        market_root_identity_sha256=_root_identity_sha256(market_root),
        personal_root_identity_sha256=_root_identity_sha256(root),
        activation_scope_id=activation.scope_id,
        source_activation_revision=activation.revision,
        source_candidate_id=cohort.candidate_id,
        source_contract_hash=cohort.contract_hash,
        cycle_id=cohort.cycle_id,
        decision_date=cohort.decision_date,
        source_reference_sha256=reference_sha256,
        selected_row=selection,
        sort_descending=sort_descending,
        scroll_position=scroll_position,
    )
    body["bookmark_identity_sha256"] = _sha256_json(body)
    if len(_canonical_json_bytes(body)) > PERSONAL_H20_RESEARCH_BOOKMARK_MAX_BYTES:
        _fail("personal_h20_bookmark_byte_limit")
    return PersonalH20ResearchBookmark.from_dict(body)


def _read_activation_snapshot(
    config_path: Path,
) -> tuple[PersonalH20Activation, bytes]:
    if not config_path.is_absolute() or config_path.name != "activation.json":
        _fail("personal_h20_bookmark_activation_path_invalid")
    try:
        raw_before = _read_regular_file_no_follow(
            config_path, config_path.parent, max_bytes=_ACTIVATION_MAX_BYTES
        )
        activation = read_personal_h20_activation(config_path)
        raw_after_parse = _read_regular_file_no_follow(
            config_path, config_path.parent, max_bytes=_ACTIVATION_MAX_BYTES
        )
    except Exception as exc:
        raise PersonalH20ResearchBookmarkError(
            "personal_h20_bookmark_activation_unavailable", str(exc)[:300]
        ) from exc
    if raw_before != raw_after_parse:
        _fail("personal_h20_bookmark_activation_changed_during_read")
    return activation, raw_before


def _check_approved_activation(
    activation: PersonalH20Activation,
    bookmark: PersonalH20ResearchBookmark,
    *,
    config_path: Path,
    market_root: Path,
) -> tuple[Path, PersonalDataPaths]:
    if activation.config_path != config_path:
        _fail("personal_h20_bookmark_activation_config_mismatch")
    if _root_identity_sha256(activation.market_root) != bookmark.market_root_identity_sha256:
        _fail("personal_h20_bookmark_market_root_mismatch")
    if _root_identity_sha256(market_root) != bookmark.market_root_identity_sha256:
        _fail("personal_h20_bookmark_market_root_mismatch")
    if activation.scope_id != bookmark.activation_scope_id:
        _fail("personal_h20_bookmark_activation_scope_mismatch")
    root = Path(activation.personal_root)
    if _root_identity_sha256(root) != bookmark.personal_root_identity_sha256:
        _fail("personal_h20_bookmark_personal_root_mismatch")
    try:
        paths = _activation_paths(activation.market_root, activation.personal_root)
        assert_personal_store_path(paths, config_path)
    except Exception as exc:
        raise PersonalH20ResearchBookmarkError(
            "personal_h20_bookmark_approved_root_rejected", str(exc)[:300]
        ) from exc
    manifest_path = root / "h20_daily_receipts" / (bookmark.manifest_sha256[7:] + ".json")
    try:
        assert_personal_store_path(paths, manifest_path)
    except Exception as exc:
        raise PersonalH20ResearchBookmarkError(
            "personal_h20_bookmark_manifest_path_rejected", str(exc)[:300]
        ) from exc
    return manifest_path, paths


def _row_matches_selection(
    row: PersonalH20ResearchRow,
    selection: PersonalH20ResearchSelection,
) -> bool:
    return (
        row.symbol == selection.symbol
        and row.sample_id == selection.sample_id
        and row.prediction_id == selection.prediction_id
        and row.capture_sha256 == selection.capture_sha256
    )


def read_personal_h20_research_bookmark(
    bookmark: PersonalH20ResearchBookmark | Mapping[str, object] | bytes | str,
    *,
    config_path: Path,
    market_root: Path,
    prediction_reader: Callable[..., Mapping[str, Any]],
    cancel_callback: Callable[[], bool] | None = None,
) -> PersonalH20ResearchBookmarkState:
    """沿收藏 manifest SHA 重開完整 H20 母體；完全不讀 current reference pointer。"""
    saved = _coerce_bookmark(bookmark)
    if not callable(prediction_reader):
        _fail("personal_h20_bookmark_public_prediction_reader_required")
    config = Path(config_path)
    expected_market_root = Path(market_root)
    _check_cancel(cancel_callback)
    activation, activation_bytes = _read_activation_snapshot(config)
    manifest_path, paths = _check_approved_activation(
        activation,
        saved,
        config_path=config,
        market_root=expected_market_root,
    )

    def checked_reader(
        path: str | Path,
        *,
        root: Path,
        expected_sha256: str,
    ) -> Mapping[str, Any]:
        _check_cancel(cancel_callback)
        try:
            assert_personal_store_path(paths, Path(path))
            value = prediction_reader(path, root=root, expected_sha256=expected_sha256)
        except InterruptedError:
            raise
        except Exception:
            _check_cancel(cancel_callback)
            raise
        _check_cancel(cancel_callback)
        return value

    _check_cancel(cancel_callback)
    try:
        cohort = read_personal_h20_research_cohort(
            manifest_path,
            root=Path(activation.personal_root),
            expected_sha256=saved.manifest_sha256,
            prediction_reader=checked_reader,
        )
    except InterruptedError:
        raise
    except Exception as exc:
        code = getattr(exc, "code", "personal_h20_original_cohort_rejected")
        raise PersonalH20ResearchBookmarkError(
            f"personal_h20_bookmark_source_rejected_{code}", str(exc)[:300]
        ) from exc
    _check_cancel(cancel_callback)

    if (
        cohort.manifest_sha256 != saved.manifest_sha256
        or Path(cohort.manifest_path) != manifest_path
        or cohort.candidate_id != saved.source_candidate_id
        or cohort.contract_hash != saved.source_contract_hash
        or cohort.cycle_id != saved.cycle_id
        or cohort.decision_date != saved.decision_date
    ):
        _fail("personal_h20_bookmark_original_cohort_mismatch")
    selected_rows = tuple(
        row for row in cohort.rows if row.symbol == saved.selected_row.symbol
    )
    if len(selected_rows) != 1 or not _row_matches_selection(selected_rows[0], saved.selected_row):
        _fail("personal_h20_bookmark_original_selection_mismatch")

    activation_after, activation_bytes_after = _read_activation_snapshot(config)
    if activation_bytes_after != activation_bytes or activation_after != activation:
        _fail("personal_h20_bookmark_activation_changed_during_read")
    _check_cancel(cancel_callback)

    if not activation.enabled:
        model_status: Literal[
            "enabled_same_contract", "disabled", "enabled_other_contract"
        ] = "disabled"
    elif (
        activation.candidate_id == saved.source_candidate_id
        and activation.model_contract_hash == saved.source_contract_hash
    ):
        model_status = "enabled_same_contract"
    else:
        model_status = "enabled_other_contract"
    return PersonalH20ResearchBookmarkState(
        bookmark=saved,
        cohort=cohort,
        selected_row=selected_rows[0],
        current_model_binding_status=model_status,
    )
