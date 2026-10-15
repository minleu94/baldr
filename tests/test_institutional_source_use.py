"""合成四文件證據只驗精確用途 pin 的保存、重開與拒絕條件。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Callable

import pytest

import app_module.institutional_source_use as source_use


_TAIPEI = timezone(timedelta(hours=8))
_ACCEPTED_AT = max(datetime(2026, 10, 16, 8, 0, tzinfo=_TAIPEI),
                   datetime.now(_TAIPEI) + timedelta(hours=1))


def test_writer_rejects_backdating_within_otherwise_valid_document_window(tmp_path, monkeypatch):
    evidence_files, _bodies, _source_state = _fixture_documents(tmp_path, monkeypatch)
    past = datetime.now(_TAIPEI) - timedelta(seconds=1)
    assert past >= source_use._NOT_BEFORE
    with pytest.raises(source_use.InstitutionalSourceUseError, match="不得回填早於本次真實保存開始"):
        source_use.write_tpex_institutional_source_use(
            evidence_files=evidence_files, output_directory=tmp_path / "backdated",
            clock=lambda: past,
        )
    assert (tmp_path / "backdated" / ".pending.json").exists()
    assert (tmp_path / "backdated" / "failure.json").exists()


def _fixture_documents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, Path], dict[str, bytes], dict[str, tuple[bytes, int]]]:
    source_directory = tmp_path / "synthetic_official_documents"
    source_directory.mkdir()
    evidence_files: dict[str, Path] = {}
    bodies: dict[str, bytes] = {}
    source_state: dict[str, tuple[bytes, int]] = {}
    synthetic_policy: list[dict[str, Any]] = []

    for index, item in enumerate(source_use._DOCUMENT_POLICY, start=1):
        role = str(item["role"])
        body = f"synthetic candidate evidence {index}: {role}\n".encode("utf-8")
        path = source_directory / f"{role}.source"
        path.write_bytes(body)
        evidence_files[role] = path
        bodies[role] = body
        source_state[role] = (body, path.stat().st_mtime_ns)
        synthetic_policy.append(
            {
                "role": role,
                "url": str(item["url"]),
                "bytes": len(body),
                "sha256": sha256(body).hexdigest(),
            }
        )

    monkeypatch.setattr(source_use, "_DOCUMENT_POLICY", tuple(synthetic_policy))
    for name in ("DATA_ROOT", "OUTPUT_ROOT", "PERSONAL_DATA_ROOT", "PERSONAL_STORE_ROOT"):
        monkeypatch.delenv(name, raising=False)
    return evidence_files, bodies, source_state


def _write_acceptance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    clock: Callable[[], datetime] | None = None,
) -> tuple[source_use.InstitutionalSourceUsePin, dict[str, Path], dict[str, bytes], dict[str, tuple[bytes, int]]]:
    evidence_files, bodies, source_state = _fixture_documents(tmp_path, monkeypatch)
    pin = source_use.write_tpex_institutional_source_use(
        evidence_files=evidence_files,
        output_directory=tmp_path / "accepted_source_use",
        clock=clock or (lambda: _ACCEPTED_AT),
    )
    return pin, evidence_files, bodies, source_state


def _assert_source_unchanged(
    evidence_files: dict[str, Path],
    source_state: dict[str, tuple[bytes, int]],
) -> None:
    for role, path in evidence_files.items():
        expected_bytes, expected_mtime = source_state[role]
        assert path.read_bytes() == expected_bytes
        assert path.stat().st_mtime_ns == expected_mtime


def _rewrite_acceptance(
    pin: source_use.InstitutionalSourceUsePin,
    change: Callable[[Any], Any],
) -> source_use.InstitutionalSourceUsePin:
    payload = json.loads(pin.path.read_text(encoding="utf-8"))
    acceptance = source_use.DailySourceUseAcceptance.from_dict(payload["acceptance"])
    payload["acceptance"] = change(acceptance).to_dict()
    raw = source_use._canonical(payload)
    pin.path.write_bytes(raw)
    return source_use.InstitutionalSourceUsePin(pin.path, sha256(raw).hexdigest())


def test_four_documents_are_copied_once_pinned_and_reopened_without_source_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pin, evidence_files, bodies, source_state = _write_acceptance(tmp_path, monkeypatch)
    output = pin.path.parent

    assert pin.path.name == "source_use.json"
    payload_bytes = pin.path.read_bytes()
    assert sha256(payload_bytes).hexdigest() == pin.sha256
    payload = json.loads(payload_bytes)
    assert payload_bytes == source_use._canonical(payload)
    assert payload["candidate_only"] is True
    assert payload["historical_pit_eligible"] is False
    assert payload["formal_oos_allowed"] is False
    assert payload["production_scheduler_allowed"] is False
    assert payload["legal_acceptance_inferred"] is False
    assert payload["acceptance"]["authorization_scope"] == "diagnostics"
    assert {path.name for path in output.iterdir() if path.is_file()} == {
        "source_use.json", "license.raw", "metadata.raw", "dataset.raw", "swagger.raw",
    }
    for role, body in bodies.items():
        assert (output / f"{role}.raw").read_bytes() == body

    reopened_pin = source_use.InstitutionalSourceUsePin(Path(str(pin.path)), pin.sha256)
    first = source_use.read_tpex_institutional_source_use(
        reopened_pin,
        decision_cutoff=_ACCEPTED_AT,
    )
    second = source_use.read_tpex_institutional_source_use(
        reopened_pin,
        decision_cutoff=_ACCEPTED_AT + timedelta(days=1),
    )

    assert first.acceptance == second.acceptance
    assert first.acceptance.scope == source_use.TPEX_INSTITUTIONAL_USE_SCOPE
    assert first.acceptance.scope.dataset_id == "data.gov.tw:11856"
    assert first.acceptance.scope.source_id == "tpex:openapi:3insti_daily_trading"
    assert first.acceptance.scope.market == "TPEx"
    assert first.acceptance.scope.parser_version == "tpex-openapi-3insti-daily.v1"
    assert first.acceptance.scope.unit == "shares"
    assert first.acceptance.scope.intended_use == "diagnostics"
    assert first.acceptance.accepted_at == _ACCEPTED_AT
    assert first.acceptance.authorization_scope == "diagnostics"
    assert first.attribution == second.attribution
    assert not (output / ".pending.json").exists()
    assert not (output / "failure.json").exists()
    _assert_source_unchanged(evidence_files, source_state)

    with pytest.raises(FileExistsError):
        source_use.write_tpex_institutional_source_use(
            evidence_files=evidence_files,
            output_directory=output,
            clock=lambda: _ACCEPTED_AT + timedelta(days=1),
        )
    assert pin.path.read_bytes() == payload_bytes
    _assert_source_unchanged(evidence_files, source_state)


def test_writer_requires_all_four_evidence_roles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_files, _bodies, _source_state = _fixture_documents(tmp_path, monkeypatch)
    missing = dict(evidence_files)
    missing.pop("metadata")

    with pytest.raises(source_use.InstitutionalSourceUseError, match="四份原件"):
        source_use.write_tpex_institutional_source_use(
            evidence_files=missing,
            output_directory=tmp_path / "missing_input",
            clock=lambda: _ACCEPTED_AT,
        )
    assert not (tmp_path / "missing_input").exists()


def test_acceptance_cannot_be_read_before_its_cutoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pin, _evidence_files, _bodies, _source_state = _write_acceptance(tmp_path, monkeypatch)

    with pytest.raises(source_use.InstitutionalSourceUseError, match="早於此來源用途接受"):
        source_use.read_tpex_institutional_source_use(
            pin,
            decision_cutoff=_ACCEPTED_AT - timedelta(microseconds=1),
        )


@pytest.mark.parametrize(
    "mutation",
    ["bad_external_sha", "tamper_artifact", "missing_document", "tamper_document", ".pending.json", "failure.json"],
)
def test_reader_rejects_bad_pin_missing_or_changed_document_and_barriers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    pin, _evidence_files, _bodies, _source_state = _write_acceptance(tmp_path, monkeypatch)
    checked_pin = pin

    if mutation == "bad_external_sha":
        checked_pin = source_use.InstitutionalSourceUsePin(pin.path, "0" * 64)
    elif mutation == "tamper_artifact":
        pin.path.write_bytes(pin.path.read_bytes() + b" ")
    elif mutation == "missing_document":
        (pin.path.parent / "metadata.raw").unlink()
    elif mutation == "tamper_document":
        target = pin.path.parent / "dataset.raw"
        target.write_bytes(target.read_bytes() + b" ")
    else:
        (pin.path.parent / mutation).write_text("{}", encoding="utf-8")

    with pytest.raises((source_use.InstitutionalSourceUseError, OSError, ValueError)):
        source_use.read_tpex_institutional_source_use(
            checked_pin,
            decision_cutoff=_ACCEPTED_AT,
        )


@pytest.mark.parametrize("invalid_kind", ["scope", "version", "use", "source", "unit"])
def test_reader_rejects_rebound_acceptance_outside_exact_tpex_diagnostics_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_kind: str,
) -> None:
    pin, _evidence_files, _bodies, _source_state = _write_acceptance(tmp_path, monkeypatch)

    def change(acceptance: Any) -> Any:
        if invalid_kind == "scope":
            return replace(acceptance, scope=replace(acceptance.scope, market="TWSE"))
        if invalid_kind == "version":
            return replace(acceptance, scope=replace(acceptance.scope, parser_version="old-parser"))
        if invalid_kind == "source":
            return replace(acceptance, official_source_endpoint="https://invalid.example/endpoint")
        return replace(acceptance, scope=replace(acceptance.scope, unit="lots"))

    if invalid_kind == "use":
        # 直接損壞wire，避免合成fixture先被共用DTO建構守衛擋下而未測到reader。
        payload = json.loads(pin.path.read_bytes())
        payload["acceptance"]["authorization_scope"] = "formal_strategy"
        raw = source_use._canonical(payload)
        pin.path.write_bytes(raw)
        rebound_pin = source_use.InstitutionalSourceUsePin(pin.path, sha256(raw).hexdigest())
    else:
        rebound_pin = _rewrite_acceptance(pin, change)
    with pytest.raises(source_use.InstitutionalSourceUseError, match="用途接受未綁"):
        source_use.read_tpex_institutional_source_use(
            rebound_pin,
            decision_cutoff=_ACCEPTED_AT,
        )


def test_reader_rejects_acceptance_rebound_before_last_document_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pin, _evidence_files, _bodies, _source_state = _write_acceptance(tmp_path, monkeypatch)
    too_early = datetime(2026, 10, 16, 7, 0, tzinfo=_TAIPEI)
    rebound_pin = _rewrite_acceptance(
        pin,
        lambda acceptance: replace(acceptance, accepted_at=too_early),
    )

    with pytest.raises(source_use.InstitutionalSourceUseError, match="早於必要官方文件原件保存"):
        source_use.read_tpex_institutional_source_use(
            rebound_pin,
            decision_cutoff=_ACCEPTED_AT + timedelta(hours=1),
        )


def test_reader_detects_document_changed_during_final_reverification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pin, _evidence_files, _bodies, _source_state = _write_acceptance(tmp_path, monkeypatch)
    changed_path = pin.path.parent / "license.raw"
    original_read = source_use._read_exact_file
    changed = False

    def read_then_mutate(path: Path, **kwargs: Any):
        nonlocal changed
        raw, signature = original_read(path, **kwargs)
        if Path(path) == changed_path and not changed:
            changed_path.write_bytes(raw + b"tamper")
            changed = True
        return raw, signature

    monkeypatch.setattr(source_use, "_read_exact_file", read_then_mutate)
    with pytest.raises(source_use.InstitutionalSourceUseError, match="文件在讀取期間改變"):
        source_use.read_tpex_institutional_source_use(
            pin,
            decision_cutoff=_ACCEPTED_AT,
        )
    assert changed


def test_cancellation_preserves_write_barriers_and_stops_reopen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_files, _bodies, _source_state = _fixture_documents(tmp_path, monkeypatch)
    output = tmp_path / "cancelled_source_use"
    checks = 0

    def cancel_while_copying() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 10

    with pytest.raises(source_use.InstitutionalSourceUseError, match="已取消"):
        source_use.write_tpex_institutional_source_use(
            evidence_files=evidence_files,
            output_directory=output,
            clock=lambda: _ACCEPTED_AT,
            check_cancel=cancel_while_copying,
        )

    assert (output / ".pending.json").exists()
    assert (output / "failure.json").exists()
    assert not (output / "source_use.json").exists()


def test_cancellation_during_read_is_observed_after_a_document_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pin, _evidence_files, _bodies, _source_state = _write_acceptance(tmp_path, monkeypatch)
    checks = 0

    def cancel_during_documents() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 3

    with pytest.raises(source_use.InstitutionalSourceUseError, match="已取消"):
        source_use.read_tpex_institutional_source_use(
            pin,
            decision_cutoff=_ACCEPTED_AT,
            check_cancel=cancel_during_documents,
        )
