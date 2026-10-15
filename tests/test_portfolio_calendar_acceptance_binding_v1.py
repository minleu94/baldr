"""明示合成用途接受的外部binding，不能由batch自授來源資格。"""
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from app_module import recommendation_portfolio_calendar_artifact_v1 as artifact
from app_module.recommendation_portfolio_calendar_acceptance_binding_v1 import (
    PortfolioCalendarAcceptanceBindingError,
    read_portfolio_calendar_acceptance_binding_v1,
    serialize_portfolio_calendar_acceptance_binding_v1,
)
from data_module.daily_source_snapshot import DailySourceUseAcceptance
from test_official_calendar_daily_snapshot_v1 import _acceptances as monthly_anchors
from test_official_calendar_annual_daily_snapshot_v1 import _annual_acceptances as annual_anchors


def _anchors(family="annual_v1"):
    if family == "annual_v1":
        return annual_anchors()
    values = monthly_anchors()
    return values["twse"], values["tpex"]


def _case(tmp_path, raw=None):
    protected = tmp_path / "formal"
    protected.mkdir()
    path = tmp_path / "accepted-source-binding.json"
    raw = serialize_portfolio_calendar_acceptance_binding_v1(_anchors()) if raw is None else raw
    path.write_bytes(raw)
    return path, sha256(raw).hexdigest(), (protected,)


def _read(case, **kwargs):
    path, digest, protected = case
    return read_portfolio_calendar_acceptance_binding_v1(
        path, expected_sha256=kwargs.get("expected_sha256", digest), protected_roots=protected,
    )


@pytest.mark.parametrize("family", ["monthly_v1", "annual_v1"])
def test_binding_keeps_independent_exact_anchors_and_family(tmp_path, family):
    anchors = _anchors(family)
    raw = serialize_portfolio_calendar_acceptance_binding_v1(anchors)
    case = _case(tmp_path, raw)
    before = case[0].read_bytes(), case[0].stat().st_mtime_ns
    value = _read(case)
    assert value.trusted_acceptances == anchors and value.source_version == family
    assert json.loads(raw) == {"schema_version": "portfolio-calendar-acceptance-binding.v1",
                               "trusted_acceptances": [item.to_dict() for item in anchors]}
    assert (case[0].read_bytes(), case[0].stat().st_mtime_ns) == before


def test_wrong_external_sha_is_never_replaced_by_file_self_hash(tmp_path):
    case = _case(tmp_path)
    with pytest.raises(PortfolioCalendarAcceptanceBindingError, match="external_sha256_mismatch"):
        _read(case, expected_sha256="0" * 64)


@pytest.mark.parametrize("case", ["mixed", "reversed", "endpoint"])
def test_serializer_rejects_mixed_or_unbound_acceptance_family(case):
    annual, monthly = _anchors(), _anchors("monthly_v1")
    anchors = {"mixed": (annual[0], monthly[1]), "reversed": tuple(reversed(annual)),
               "endpoint": (annual[0], replace(annual[1], official_source_endpoint=monthly[1].official_source_endpoint))}[case]
    with pytest.raises(ValueError):
        serialize_portfolio_calendar_acceptance_binding_v1(anchors)


@pytest.mark.parametrize("change", ["schema", "extra", "single_market", "reverse", "noncanonical", "duplicate", "noncanonical_time"])
def test_rehashed_invalid_binding_remains_rejected(tmp_path, change):
    raw = serialize_portfolio_calendar_acceptance_binding_v1(_anchors())
    value = json.loads(raw)
    if change == "schema": value["schema_version"] = "unknown.v1"
    elif change == "extra": value["sha256"] = sha256(raw).hexdigest()
    elif change == "single_market": value["trusted_acceptances"].pop()
    elif change == "reverse": value["trusted_acceptances"].reverse()
    elif change == "noncanonical_time": value["trusted_acceptances"][0]["accepted_at"] = "2026-01-02T05:45:00+00:00"
    if change == "duplicate":
        raw = b'{"schema_version":"unknown",' + raw[1:]
    elif change == "noncanonical":
        raw = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    else:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    with pytest.raises(ValueError):
        _read(_case(tmp_path, raw))


def test_64kib_limit_rejects_before_open_and_never_reads_unbounded(tmp_path, monkeypatch):
    case = _case(tmp_path, b"x" * (65536 + 1))
    monkeypatch.setattr(artifact.os, "read", lambda *_: pytest.fail("超界stat不可開啟讀body"))
    with pytest.raises(PortfolioCalendarAcceptanceBindingError, match="artifact_size_exceeded"):
        _read(case)


def test_growth_after_stat_is_bounded_and_rejected(tmp_path, monkeypatch):
    case = _case(tmp_path)
    path = case[0]
    original_read = os.read
    calls = []

    def grow(descriptor, size):
        calls.append(size)
        if len(calls) == 1:
            with path.open("ab") as stream:
                stream.write(b" " * 65536)
        return original_read(descriptor, size)

    monkeypatch.setattr(artifact.os, "read", grow)
    with pytest.raises(PortfolioCalendarAcceptanceBindingError, match="artifact_size_exceeded"):
        _read(case)
    assert calls and max(calls) <= 65537


def test_protected_root_is_still_rejected(tmp_path):
    case = _case(tmp_path)
    with pytest.raises(PortfolioCalendarAcceptanceBindingError, match="protected_or_formal_root"):
        _read((case[0], case[1], (tmp_path,)))


def test_hardlink_cannot_alias_binding(tmp_path):
    case = _case(tmp_path)
    alias = tmp_path / "second-link.json"
    os.link(case[0], alias)
    with pytest.raises(PortfolioCalendarAcceptanceBindingError, match="hardlink"):
        _read(case)


def test_parent_symlink_cannot_alias_binding(tmp_path):
    case = _case(tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    case[0].rename(source / case[0].name)
    alias = tmp_path / "directory-alias"
    try:
        alias.symlink_to(source, target_is_directory=True)
    except OSError as exc:
        pytest.skip("平台未授建立symlink，原reparse守衛不放寬：" + type(exc).__name__)
    with pytest.raises(PortfolioCalendarAcceptanceBindingError, match="reparse"):
        _read((alias / case[0].name, case[1], case[2]))


def test_acceptance_public_decoder_reuses_original_typed_contract():
    anchor = _anchors()[0]
    assert DailySourceUseAcceptance.from_dict(anchor.to_dict()) == anchor
    invalid = dict(anchor.to_dict(), document_chain=anchor.document_chain)
    with pytest.raises(ValueError):
        DailySourceUseAcceptance.from_dict(invalid)
