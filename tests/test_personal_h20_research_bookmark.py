"""H20 原來源收藏的 exact manifest 重開契約；只使用隔離合成 capture。"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from app_module.recommendation.personal_h20_activation import (
    PersonalH20Activation,
    publish_personal_h20_activation,
)
from app_module.recommendation.personal_h20_product_evidence import (
    publish_personal_h20_product_reference,
    read_personal_h20_product_reference,
)
from app_module.recommendation.personal_h20_research_bookmark import (
    PERSONAL_H20_RESEARCH_BOOKMARK_SCHEMA,
    PersonalH20ResearchBookmark,
    PersonalH20ResearchBookmarkError,
    create_personal_h20_research_bookmark,
    read_personal_h20_research_bookmark,
)
from app_module.recommendation.personal_h20_research_cohort import (
    PersonalH20ResearchSelection,
    read_personal_h20_research_cohort,
)
from tests.test_personal_h20_research_cohort import public_reader, saved_cohort


def _fixture(tmp_path: Path):
    private_root, manifest_path, manifest_sha256, _manifest = saved_cohort(
        tmp_path,
        symbols=("1101", "2330", "2454"),
        values=(120, 684, -50),
    )
    market_root = tmp_path / "data"
    market_root.mkdir()
    contract_hash = "sha256:" + "a" * 64
    activation = PersonalH20Activation(
        revision=1,
        enabled=True,
        scope_id="research.h20.test",
        market_root=str(market_root),
        personal_root=str(private_root),
        fit_receipt=str(tmp_path / "fit.json"),
        fit_receipt_sha256="sha256:" + "f" * 64,
        candidate_id="candidate-1",
        model_id="model-1",
        model_contract_hash=contract_hash,
        history_start_date="2014-01-01",
    )
    publish_personal_h20_activation(activation, expected_revision=0, execute=True)
    manifest_body = json.loads(manifest_path.read_bytes())
    publish_personal_h20_product_reference(
        activation,
        receipt_path=str(manifest_path),
        receipt_sha256=manifest_sha256,
        decision_date=manifest_body["decision_date"],
        cycle_id=manifest_body["cycle_id"],
    )
    reference = read_personal_h20_product_reference(
        activation.config_path,
        market_root=market_root,
    )
    cohort = read_personal_h20_research_cohort(
        reference.manifest_path,
        root=private_root,
        expected_sha256=reference.manifest_sha256,
        prediction_reader=public_reader,
    )
    selected_row = next(row for row in cohort.rows if row.symbol == "2330")
    selection = PersonalH20ResearchSelection(
        manifest_sha256=cohort.manifest_sha256,
        candidate_id=cohort.candidate_id,
        contract_hash=cohort.contract_hash,
        cycle_id=cohort.cycle_id,
        symbol=selected_row.symbol,
        sample_id=selected_row.sample_id,
        prediction_id=selected_row.prediction_id,
        capture_sha256=selected_row.capture_sha256,
    )
    bookmark = create_personal_h20_research_bookmark(
        reference,
        cohort,
        selection,
        sort_descending=False,
        scroll_position=17,
    )
    return {
        "private_root": private_root,
        "market_root": market_root,
        "manifest_path": manifest_path,
        "manifest_sha256": manifest_sha256,
        "activation": activation,
        "reference": reference,
        "cohort": cohort,
        "selection": selection,
        "bookmark": bookmark,
    }


def _read(fixture, bookmark=None, *, cancel_callback=None):
    return read_personal_h20_research_bookmark(
        bookmark or fixture["bookmark"],
        config_path=fixture["activation"].config_path,
        market_root=fixture["market_root"],
        prediction_reader=public_reader,
        cancel_callback=cancel_callback,
    )


def _file_snapshot(root: Path) -> dict[Path, tuple[bytes, int]]:
    return {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }


def test_bookmark_is_immutable_exact_h20_descriptor_without_prediction_or_path(tmp_path):
    fixture = _fixture(tmp_path)
    bookmark = fixture["bookmark"]
    payload = bookmark.to_dict()

    assert bookmark.to_json() == PersonalH20ResearchBookmark.from_json(bookmark.to_json()).to_json()
    assert payload["schema_version"] == PERSONAL_H20_RESEARCH_BOOKMARK_SCHEMA
    assert payload["source"] == "personal_h20_research_bookmark"
    assert payload["manifest_sha256"] == fixture["manifest_sha256"]
    assert payload["selected_row"]["symbol"] == "2330"
    assert payload["sort_descending"] is False
    assert payload["scroll_position"] == 17
    serialized = bookmark.to_json()
    assert str(tmp_path) not in serialized
    assert "gross_return_bp" not in serialized and "684" not in serialized
    assert "prediction_id" in serialized and "predicted_gross_return_bp" not in serialized


def test_exact_reopen_uses_manifest_pin_and_preserves_original_files(tmp_path):
    fixture = _fixture(tmp_path)
    before = _file_snapshot(fixture["private_root"])

    state = _read(fixture, fixture["bookmark"].to_json().encode("utf-8"))

    assert state.cohort == fixture["cohort"]
    assert state.selected_row.symbol == "2330"
    assert state.selected_row.status == "available"
    assert state.bookmark.sort_descending is False
    assert state.bookmark.scroll_position == 17
    assert state.current_model_binding_status == "enabled_same_contract"
    assert _file_snapshot(fixture["private_root"]) == before


def test_unknown_selected_capture_restores_original_list_but_never_research_value(tmp_path):
    fixture = _fixture(tmp_path)
    selected = fixture["selection"]
    capture = next(row for row in fixture["cohort"].rows if row.symbol == selected.symbol)
    Path(capture.capture_path).unlink()

    state = _read(fixture)

    assert state.cohort.symbols == fixture["cohort"].symbols
    assert state.selected_row.symbol == "2330"
    assert state.selected_row.status == "unknown"
    assert state.selected_row.gross_return_bp is None
    assert "cannot find the file specified" in state.selected_row.reason.lower()


def test_unknown_row_cannot_create_actionable_h20_bookmark(tmp_path):
    fixture = _fixture(tmp_path)
    selected = fixture["selection"]

    def unknown_reader(path, *, root, expected_sha256):
        if Path(path).name == Path(
            next(row.capture_path for row in fixture["cohort"].rows if row.symbol == selected.symbol)
        ).name:
            raise ValueError("synthetic_selected_capture_unavailable")
        return public_reader(path, root=root, expected_sha256=expected_sha256)

    unknown_cohort = read_personal_h20_research_cohort(
        fixture["reference"].manifest_path,
        root=fixture["private_root"],
        expected_sha256=fixture["reference"].manifest_sha256,
        prediction_reader=unknown_reader,
    )
    with pytest.raises(PersonalH20ResearchBookmarkError, match="selected_row_not_available"):
        create_personal_h20_research_bookmark(
            fixture["reference"],
            unknown_cohort,
            selected,
            sort_descending=True,
            scroll_position=0,
        )


def test_new_revision_and_new_reference_pointer_still_reopen_old_exact_manifest(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    activation = fixture["activation"]
    pointer = Path(activation.personal_root) / "h20_product_reference.json"
    pointer_before = pointer.read_bytes()
    newer_activation = replace(
        activation,
        revision=2,
        candidate_id="candidate-2",
        model_contract_hash="sha256:" + "b" * 64,
    )
    publish_personal_h20_activation(newer_activation, expected_revision=1, execute=True)
    publish_personal_h20_product_reference(
        newer_activation,
        receipt_path=str(fixture["manifest_path"]),
        receipt_sha256=fixture["manifest_sha256"],
        decision_date=fixture["cohort"].decision_date,
        cycle_id=fixture["cohort"].cycle_id,
    )
    assert pointer.read_bytes() != pointer_before

    def forbidden_latest(*args, **kwargs):
        pytest.fail("收藏重開不得讀取 current product reference")

    monkeypatch.setattr(
        "app_module.recommendation.personal_h20_product_evidence.read_personal_h20_product_reference",
        forbidden_latest,
    )
    state = _read(fixture)

    assert state.cohort.manifest_sha256 == fixture["manifest_sha256"]
    assert state.selected_row.gross_return_bp == 684
    assert state.current_model_binding_status == "enabled_other_contract"


def test_disabled_activation_is_typed_and_does_not_block_historical_read(tmp_path):
    fixture = _fixture(tmp_path)
    disabled = replace(fixture["activation"], revision=2, enabled=False)
    publish_personal_h20_activation(disabled, expected_revision=1, execute=True)

    state = _read(fixture)

    assert state.cohort.manifest_sha256 == fixture["manifest_sha256"]
    assert state.current_model_binding_status == "disabled"
    assert state.selected_row.status == "available"


def test_wrong_scope_and_wrong_personal_root_are_refused(tmp_path):
    fixture = _fixture(tmp_path)
    changed_scope = replace(fixture["activation"], revision=2, scope_id="other.scope")
    publish_personal_h20_activation(changed_scope, expected_revision=1, execute=True)
    with pytest.raises(PersonalH20ResearchBookmarkError, match="activation_scope_mismatch"):
        _read(fixture)

    other_root = tmp_path / "other-private"
    other_activation = replace(
        fixture["activation"],
        personal_root=str(other_root),
    )
    publish_personal_h20_activation(other_activation, expected_revision=0, execute=True)
    with pytest.raises(PersonalH20ResearchBookmarkError, match="personal_root_mismatch"):
        read_personal_h20_research_bookmark(
            fixture["bookmark"],
            config_path=other_activation.config_path,
            market_root=fixture["market_root"],
            prediction_reader=public_reader,
        )


def test_wrong_market_root_is_refused(tmp_path):
    fixture = _fixture(tmp_path)
    other_market = tmp_path / "other-data"
    other_market.mkdir()
    with pytest.raises(PersonalH20ResearchBookmarkError, match="market_root_mismatch"):
        read_personal_h20_research_bookmark(
            fixture["bookmark"],
            config_path=fixture["activation"].config_path,
            market_root=other_market,
            prediction_reader=public_reader,
        )


def test_capture_reader_interruption_propagates_instead_of_becoming_unknown(tmp_path):
    fixture = _fixture(tmp_path)
    calls = 0

    def cancel_after_first_capture():
        nonlocal calls
        calls += 1
        return calls == 4

    before = _file_snapshot(fixture["private_root"])
    with pytest.raises(InterruptedError, match="personal_h20_bookmark_cancelled"):
        _read(fixture, cancel_callback=cancel_after_first_capture)
    assert calls >= 4
    assert _file_snapshot(fixture["private_root"]) == before


def test_activation_bytes_changed_during_capture_read_are_rejected(tmp_path):
    fixture = _fixture(tmp_path)
    changed_activation = replace(fixture["activation"], revision=2)
    calls = 0

    def change_activation_during_read(path, *, root, expected_sha256):
        nonlocal calls
        calls += 1
        if calls == 1:
            publish_personal_h20_activation(
                changed_activation,
                expected_revision=1,
                execute=True,
            )
        return public_reader(path, root=root, expected_sha256=expected_sha256)

    with pytest.raises(PersonalH20ResearchBookmarkError, match="activation_changed_during_read"):
        read_personal_h20_research_bookmark(
            fixture["bookmark"],
            config_path=fixture["activation"].config_path,
            market_root=fixture["market_root"],
            prediction_reader=change_activation_during_read,
        )


def test_payload_tamper_duplicate_keys_and_noncanonical_json_fail_closed(tmp_path):
    fixture = _fixture(tmp_path)
    bookmark = fixture["bookmark"]
    body = bookmark.to_dict()
    body["selected_row"]["symbol"] = "9999"
    identity_body = {key: value for key, value in body.items() if key != "bookmark_identity_sha256"}
    body["bookmark_identity_sha256"] = hashlib.sha256(
        json.dumps(identity_body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    altered = PersonalH20ResearchBookmark.from_dict(body)
    with pytest.raises(PersonalH20ResearchBookmarkError, match="original_selection_mismatch"):
        _read(fixture, altered)

    with pytest.raises(PersonalH20ResearchBookmarkError, match="duplicate_json_key"):
        PersonalH20ResearchBookmark.from_json(
            b'{"schema_version":"personal-h20-research-bookmark.v1",'
            b'"schema_version":"personal-h20-research-bookmark.v1"}'
        )
    with pytest.raises(PersonalH20ResearchBookmarkError, match="json_noncanonical"):
        PersonalH20ResearchBookmark.from_json(bookmark.to_json().replace(":", ": ", 1))


def test_fresh_process_reopens_same_original_manifest_and_restored_view_state(tmp_path):
    fixture = _fixture(tmp_path)
    code = """
import sys
from pathlib import Path
from tests.test_personal_h20_research_cohort import public_reader
from app_module.recommendation.personal_h20_research_bookmark import read_personal_h20_research_bookmark
state = read_personal_h20_research_bookmark(
    sys.argv[3], config_path=Path(sys.argv[1]), market_root=Path(sys.argv[2]),
    prediction_reader=public_reader,
)
assert state.cohort.symbols == ('1101', '2330', '2454')
assert state.selected_row.symbol == '2330'
assert state.selected_row.gross_return_bp == 684
assert state.bookmark.sort_descending is False
assert state.bookmark.scroll_position == 17
assert state.current_model_binding_status == 'enabled_same_contract'
print('exact_h20_bookmark_reopened')
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(fixture["activation"].config_path),
            str(fixture["market_root"]),
            fixture["bookmark"].to_json(),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "exact_h20_bookmark_reopened" in result.stdout
