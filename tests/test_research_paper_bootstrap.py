"""研究 Paper 設定只接受明選外部 SHA，解析階段不建立金融狀態。"""
import json
from pathlib import Path

import pytest

from app_module.application_bootstrap import (
    configured_research_paper_evidence_binding_selection,
    resolve_application_settings,
)


def test_configured_composition_builds_writer_only_after_confirmed_verified_intent(tmp_path: Path, monkeypatch):
    from app_module import research_paper_ui_composition as module
    from tests.test_research_paper_evidence_binding import _build_paper_fixture, _confirmed_intent

    fixture = _build_paper_fixture(tmp_path)
    settings = resolve_application_settings(environ={
        "LOCALAPPDATA": str(tmp_path / "local"),
        "RESEARCH_PAPER_EVIDENCE_BINDING_PATH": str(fixture.binding_path),
        "RESEARCH_PAPER_EVIDENCE_BINDING_SHA256": fixture.expected_binding_sha256.removeprefix("sha256:"),
    }, resource_root=tmp_path / "bundle", frozen=False)
    real_repository = module.PaperTradeLedgerRepository
    writer_calls = []

    def counted_writer(*args, **kwargs):
        writer_calls.append((args, kwargs))
        return real_repository(*args, **kwargs)

    monkeypatch.setattr(module, "PaperTradeLedgerRepository", counted_writer)
    composition = module.configured_research_paper_simulation(
        settings=settings, entry=fixture.entry, timeline_service=fixture.timeline,
        account_service=fixture.account_service, personal_paths=fixture.personal_paths,
    )
    assert composition is not None
    context = composition.provider.preview(fixture.entry)
    assert writer_calls == []
    intent = _confirmed_intent(fixture.entry, context)
    producer = composition.producer_factory(intent)
    assert len(writer_calls) == 1
    result = producer.produce(fixture.entry, intent)
    assert result.return_entry is fixture.entry
    assert composition.producer_factory(intent).produce(fixture.entry, intent).fill == result.fill
    assert len(fixture.ledger.read_rowset_snapshot(portfolio_id=fixture.binding.portfolio_id).fills) == 1


def test_paper_evidence_selection_preserves_explicit_path_without_opening_it(tmp_path: Path):
    evidence = tmp_path / "not-created" / "evidence.json"
    settings = resolve_application_settings(environ={
        "LOCALAPPDATA": str(tmp_path / "local"),
        "RESEARCH_PAPER_EVIDENCE_BINDING_PATH": str(evidence),
        "RESEARCH_PAPER_EVIDENCE_BINDING_SHA256": "a" * 64,
    }, resource_root=tmp_path / "bundle", frozen=False)
    assert configured_research_paper_evidence_binding_selection(settings) == (evidence, "a" * 64)
    assert not evidence.parent.exists()


@pytest.mark.parametrize("values", [
    {"RESEARCH_PAPER_EVIDENCE_BINDING_PATH": "relative.json", "RESEARCH_PAPER_EVIDENCE_BINDING_SHA256": "a" * 64},
    {"RESEARCH_PAPER_EVIDENCE_BINDING_SHA256": "a" * 64},
    {"RESEARCH_PAPER_EVIDENCE_BINDING_PATH": ""},
    {"RESEARCH_PAPER_EVIDENCE_BINDING_SHA256": "A" * 64},
])
def test_incomplete_or_invalid_paper_trust_setting_is_rejected(tmp_path: Path, values):
    with pytest.raises(ValueError):
        resolve_application_settings(environ={"LOCALAPPDATA": str(tmp_path / "local"), **values})


def test_frozen_config_cannot_borrow_bundle_evidence(tmp_path: Path):
    bundle = tmp_path / "bundle"
    config = tmp_path / "config.json"
    config.write_text(json.dumps({
        "RESEARCH_PAPER_EVIDENCE_BINDING_PATH": str(bundle / "evidence.json"),
        "RESEARCH_PAPER_EVIDENCE_BINDING_SHA256": "a" * 64,
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="RESEARCH_PAPER_EVIDENCE_BINDING_PATH"):
        resolve_application_settings(
            environ={"LOCALAPPDATA": str(tmp_path / "local"), "BALDR_CONFIG": str(config)},
            resource_root=bundle, frozen=True,
        )
