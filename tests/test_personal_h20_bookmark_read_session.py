"""H20 原收藏 operation-session：只讀合成來源的定向驗證。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import pytest

from app_module.recommendation.personal_h20_activation import publish_personal_h20_activation
from app_module.recommendation.personal_h20_product_evidence import (
    publish_personal_h20_product_reference,
)
from app_module.recommendation.personal_h20_read_session import (
    PersonalH20ReadSessionError,
)
from app_module.recommendation.personal_h20_research_bookmark import (
    PersonalH20ResearchBookmarkError,
)
from scripts.scheduled.personal_h20_bookmark_read_session import (
    read_personal_h20_research_bookmark_with_session,
)
from tests.test_personal_h20_research_bookmark import _file_snapshot, _fixture


def _install_ports(monkeypatch, *, source_verifier=None, contract_verifier=None):
    from scripts.scheduled import run_personal_current_observed_h20_daily as runner

    source = source_verifier or deepcopy
    contract = contract_verifier or deepcopy
    monkeypatch.setattr(
        runner,
        "personal_current_observed_h20_read_ports",
        lambda: {"source_verifier": source, "contract_verifier": contract},
    )


def _read(fixture, *, bookmark=None, cancel_callback=None, progress_callback=None):
    return read_personal_h20_research_bookmark_with_session(
        bookmark or fixture["bookmark"],
        config_path=fixture["activation"].config_path,
        market_root=fixture["market_root"],
        cancel_callback=cancel_callback,
        progress_callback=progress_callback,
    )


def test_session_reopens_exact_bookmark_and_rechecks_each_shared_binding(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    calls = {"source": 0, "contract": 0}

    def source_verifier(binding):
        calls["source"] += 1
        return deepcopy(binding)

    def contract_verifier(binding):
        calls["contract"] += 1
        return deepcopy(binding)

    _install_ports(
        monkeypatch,
        source_verifier=source_verifier,
        contract_verifier=contract_verifier,
    )
    before = _file_snapshot(fixture["private_root"])
    progress: list[str] = []

    state = _read(
        fixture,
        bookmark=fixture["bookmark"].to_json().encode("utf-8"),
        progress_callback=progress.append,
    )

    assert state.cohort.manifest_sha256 == fixture["manifest_sha256"]
    assert state.cohort.symbols == ("1101", "2330", "2454")
    assert state.selected_row.symbol == "2330"
    assert state.selected_row.status == "available"
    assert state.selected_row.gross_return_bp == 684
    assert state.bookmark.sort_descending is False
    assert state.bookmark.scroll_position == 17
    # 合成 captures 含三組不同 source binding、共用一組 contract；
    # 初讀逐組核驗，終態只對每組各新鮮核一次。
    assert calls == {"source": 6, "contract": 2}
    assert any("沿收藏固定的原 manifest" in item for item in progress)
    assert any("收藏終態重讀原 manifest 與全部 capture pins" in item for item in progress)
    assert any("終態重驗來源第 1 組／共 3 組" in item for item in progress)
    assert any("activation 原始內容未變" in item for item in progress)
    assert _file_snapshot(fixture["private_root"]) == before


def test_session_is_operation_local_and_old_bookmark_ignores_new_pointer(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    _install_ports(monkeypatch)
    activation = fixture["activation"]
    newer = replace(
        activation,
        revision=2,
        candidate_id="candidate-newer",
        model_contract_hash="sha256:" + "b" * 64,
    )
    publish_personal_h20_activation(newer, expected_revision=1, execute=True)
    publish_personal_h20_product_reference(
        newer,
        receipt_path=str(fixture["manifest_path"]),
        receipt_sha256=fixture["manifest_sha256"],
        decision_date=fixture["cohort"].decision_date,
        cycle_id=fixture["cohort"].cycle_id,
    )
    pointer = Path(newer.personal_root) / "h20_product_reference.json"
    pointer.write_text("deliberately not a product pointer", encoding="utf-8")

    first = _read(fixture)
    second = _read(fixture)

    assert first == second
    assert first.cohort.manifest_sha256 == fixture["manifest_sha256"]
    assert first.selected_row.gross_return_bp == 684
    assert first.current_model_binding_status == "enabled_other_contract"


@pytest.mark.parametrize("capture_state", ["missing", "corrupt"])
def test_selected_capture_failure_is_restored_as_unknown_not_replaced(tmp_path, monkeypatch, capture_state):
    fixture = _fixture(tmp_path)
    _install_ports(monkeypatch)
    selected = next(row for row in fixture["cohort"].rows if row.symbol == "2330")
    capture_path = Path(selected.capture_path)
    if capture_state == "missing":
        capture_path.unlink()
    else:
        capture_path.write_bytes(capture_path.read_bytes() + b" ")

    state = _read(fixture)

    assert state.cohort.manifest_sha256 == fixture["manifest_sha256"]
    assert state.cohort.symbols == fixture["cohort"].symbols
    assert state.selected_row.status == "unknown"
    assert state.selected_row.gross_return_bp is None
    assert state.selected_row.capture_sha256 == selected.capture_sha256


@pytest.mark.parametrize("kind", ["source", "contract"])
def test_fresh_verifier_drift_rejects_without_returning_a_partial_state(tmp_path, monkeypatch, kind):
    fixture = _fixture(tmp_path)
    calls = 0
    recheck_call = 4 if kind == "source" else 2

    def verifier(binding):
        nonlocal calls
        calls += 1
        result = deepcopy(binding)
        if calls == recheck_call:
            result["synthetic_terminal_change"] = True
        return result

    kwargs = {f"{kind}_verifier": verifier}
    _install_ports(monkeypatch, **kwargs)

    with pytest.raises(PersonalH20ReadSessionError, match=f"{kind}_changed_during_read"):
        _read(fixture)
    assert calls == recheck_call


def test_capture_pin_changed_before_terminal_read_rejects_state(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    selected = next(row for row in fixture["cohort"].rows if row.symbol == "2330")
    calls = 0

    def source_verifier(binding):
        nonlocal calls
        calls += 1
        if calls == 4:
            capture = Path(selected.capture_path)
            capture.write_bytes(capture.read_bytes() + b" ")
        return deepcopy(binding)

    _install_ports(monkeypatch, source_verifier=source_verifier)

    with pytest.raises(PersonalH20ResearchBookmarkError, match="state_changed_during_read"):
        _read(fixture)
    assert calls == 6


def test_initial_source_rejection_remains_visible_when_terminal_state_differs(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    before = _file_snapshot(fixture["private_root"])

    def reject_source(_binding):
        raise ValueError("synthetic_original_source_clock_rejected")

    _install_ports(monkeypatch, source_verifier=reject_source)
    with pytest.raises(PersonalH20ResearchBookmarkError) as failure:
        _read(fixture)
    message = str(failure.value)
    assert "state_changed_during_read" in message
    assert "initial_selected_reason=" in message
    assert "synthetic_original_source_clock_rejected" in message
    assert "terminal_selected_reason=" in message
    assert _file_snapshot(fixture["private_root"]) == before


def test_activation_bytes_changed_during_terminal_verification_rejects(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    activation = fixture["activation"]
    calls = 0

    def source_verifier(binding):
        nonlocal calls
        calls += 1
        if calls == 2:
            publish_personal_h20_activation(
                replace(activation, revision=2),
                expected_revision=1,
                execute=True,
            )
        return deepcopy(binding)

    _install_ports(monkeypatch, source_verifier=source_verifier)

    with pytest.raises(PersonalH20ResearchBookmarkError, match="activation_changed_during_read"):
        _read(fixture)


def test_cancel_during_terminal_capture_read_propagates(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    _install_ports(monkeypatch)
    cancelled = False

    def progress(message):
        nonlocal cancelled
        if "收藏終態重讀第 1 列" in message and "完成" in message:
            cancelled = True

    with pytest.raises(InterruptedError, match="personal_h20_read_cancelled"):
        _read(
            fixture,
            cancel_callback=lambda: cancelled,
            progress_callback=progress,
        )


def test_progress_failure_cannot_publish_unknown_bookmark_state(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    _install_ports(monkeypatch)

    def broken_progress(message):
        if "收藏原來源讀取第 1 列" in message:
            raise RuntimeError("synthetic progress channel failure")

    with pytest.raises(PersonalH20ReadSessionError, match="progress_callback_failed"):
        _read(fixture, progress_callback=broken_progress)


def test_fresh_process_reopens_the_same_original_bookmark_and_view_state(tmp_path):
    fixture = _fixture(tmp_path)
    code = r'''
import json, sys
from copy import deepcopy
from pathlib import Path
from scripts.scheduled import run_personal_current_observed_h20_daily as runner
runner.personal_current_observed_h20_read_ports = lambda: {
    "source_verifier": deepcopy,
    "contract_verifier": deepcopy,
}
from scripts.scheduled.personal_h20_bookmark_read_session import read_personal_h20_research_bookmark_with_session
state = read_personal_h20_research_bookmark_with_session(
    sys.argv[3], config_path=Path(sys.argv[1]), market_root=Path(sys.argv[2]),
)
print(json.dumps({
    "manifest": state.cohort.manifest_sha256,
    "symbols": state.cohort.symbols,
    "selected": state.selected_row.symbol,
    "gross_return_bp": state.selected_row.gross_return_bp,
    "sort_descending": state.bookmark.sort_descending,
    "scroll_position": state.bookmark.scroll_position,
    "model_status": state.current_model_binding_status,
}))
'''
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
        check=False,
    )

    assert result.returncode == 0, result.stderr
    body = json.loads(result.stdout)
    assert body == {
        "manifest": fixture["manifest_sha256"],
        "symbols": ["1101", "2330", "2454"],
        "selected": "2330",
        "gross_return_bp": 684,
        "sort_descending": False,
        "scroll_position": 17,
        "model_status": "enabled_same_contract",
    }
