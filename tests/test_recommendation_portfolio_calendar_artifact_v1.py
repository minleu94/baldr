"""期間行事曆單檔候選 artifact 的離線安全契約測試。"""

from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Callable

import pytest

from app_module.recommendation_portfolio_calendar_artifact_v1 import (
    RecommendationPortfolioCalendarArtifactV1Error,
    read_portfolio_period_calendar_evidence_v1,
    write_portfolio_period_calendar_evidence_create_only_v1,
)
from app_module.recommendation_portfolio_calendar_evidence_v1 import (
    PortfolioPeriodCalendarEvidenceV1,
)
from data_module.official_calendar_bundle import (
    CapturedCalendarResponse,
    hash_response_bytes,
)


def _response(
    *, kind: str, key: str, source: str, payload: object
) -> CapturedCalendarResponse:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return CapturedCalendarResponse(
        kind=kind,
        key=key,
        source=source,
        source_hash=hash_response_bytes(raw),
        payload=payload,
        raw_bytes=raw,
        metadata={"fixture": "offline"},
    )


def _evidence() -> PortfolioPeriodCalendarEvidenceV1:
    twse = _response(
        kind="twse",
        key="2026",
        source=(
            "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule"
            "?queryYear=115"
        ),
        payload=[
            {"Name": "中秋節", "Date": "1150925", "Description": "依規定放假一日。"},
            {"Name": "國慶日前最後交易日", "Date": "1151009", "Description": "最後交易。"},
        ],
    )
    tpex = _response(
        kind="tpex",
        key="202609",
        source="https://info.tpex.org.tw/api/mktCalendar?ym=202609&lang=zh-tw",
        payload={
            "calendar": {
                "total": 2,
                "data": {
                    "20260901": {"holiday": False, "holidayList": []},
                    "20260902": {"holiday": False, "holidayList": []},
                },
                "status": "success",
            }
        },
    )
    return PortfolioPeriodCalendarEvidenceV1.build(
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 2),
        twse_responses={2026: twse},
        tpex_responses={"202609": tpex},
        captured_at=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
        capture_mode="fixture_only",
    )


def _roots(tmp_path: Path) -> tuple[Path, tuple[Path, Path, Path]]:
    protected = (
        tmp_path / "formal-data",
        tmp_path / "output",
        tmp_path / "personal-data",
    )
    for root in protected:
        root.mkdir()
    research = tmp_path / "research-candidates"
    research.mkdir()
    return research, protected


def _write(
    path: Path, evidence: PortfolioPeriodCalendarEvidenceV1, roots: tuple[Path, ...]
) -> str:
    return write_portfolio_period_calendar_evidence_create_only_v1(
        path, evidence, protected_roots=roots
    )


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def test_writer_and_fresh_reader_round_trip_full_raw_candidate_evidence(
    tmp_path: Path,
) -> None:
    research, protected = _roots(tmp_path)
    evidence = _evidence()
    path = research / "period-calendar.v1.json"

    external_sha = _write(path, evidence, protected)

    assert len(external_sha) == 64
    assert external_sha == hashlib.sha256(path.read_bytes()).hexdigest()
    restored = read_portfolio_period_calendar_evidence_v1(
        path, expected_sha256=external_sha, protected_roots=protected
    )
    artifact_text = path.read_text(encoding="utf-8")
    assert restored.to_json() == evidence.to_json()
    assert restored.evidence_sha256 == evidence.evidence_sha256
    assert json.loads(artifact_text)["evidence"] == json.loads(evidence.to_json())
    assert "raw_response_base64" in artifact_text
    assert restored.candidate_only is True
    assert restored.historical_pit_eligible is False
    assert restored.performance_eligible is False
    assert restored.formal_clock_eligible is False


def test_reader_requires_matching_external_sha_and_detects_changed_bytes(
    tmp_path: Path,
) -> None:
    research, protected = _roots(tmp_path)
    path = research / "period-calendar.v1.json"
    external_sha = _write(path, _evidence(), protected)

    with pytest.raises(RecommendationPortfolioCalendarArtifactV1Error, match="expected_sha256_invalid"):
        read_portfolio_period_calendar_evidence_v1(
            path, expected_sha256="sha256:" + external_sha, protected_roots=protected
        )

    changed = path.read_bytes() + b" "
    path.write_bytes(changed)
    with pytest.raises(RecommendationPortfolioCalendarArtifactV1Error, match="external_sha256_mismatch"):
        read_portfolio_period_calendar_evidence_v1(
            path, expected_sha256=external_sha, protected_roots=protected
        )


@pytest.mark.parametrize(
    ("replacement", "reason"),
    [
        ('{"schema_version":"recommendation-portfolio-period-calendar-artifact.v1"}', "artifact_fields_invalid"),
        ('{"evidence":{},"extra":true,"schema_version":"recommendation-portfolio-period-calendar-artifact.v1"}', "artifact_fields_invalid"),
        (
            '{"evidence":{},"schema_version":"recommendation-portfolio-period-calendar-artifact.v1",'
            '"schema_version":"recommendation-portfolio-period-calendar-artifact.v1"}',
            "duplicate_json_key",
        ),
    ],
)
def test_reader_rejects_malformed_or_nonexact_envelope_even_with_new_matching_sha(
    tmp_path: Path, replacement: str, reason: str
) -> None:
    research, protected = _roots(tmp_path)
    path = research / "period-calendar.v1.json"
    _write(path, _evidence(), protected)
    raw = replacement.encode("utf-8")
    path.write_bytes(raw)

    with pytest.raises(RecommendationPortfolioCalendarArtifactV1Error, match=reason):
        read_portfolio_period_calendar_evidence_v1(
            path,
            expected_sha256=hashlib.sha256(raw).hexdigest(),
            protected_roots=protected,
        )


@pytest.mark.parametrize("mutation", ["missing_raw_bytes", "changed_raw_bytes"])
def test_reader_rebuilds_and_rehashes_embedded_source_capture(
    tmp_path: Path, mutation: str
) -> None:
    research, protected = _roots(tmp_path)
    path = research / "period-calendar.v1.json"
    _write(path, _evidence(), protected)
    artifact = json.loads(path.read_text(encoding="utf-8"))
    evidence = artifact["evidence"]
    if mutation == "missing_raw_bytes":
        evidence["twse_responses"][0].pop("raw_response_base64")
    else:
        evidence["twse_responses"][0]["raw_response_base64"] = "AAAA"
        evidence_without_digest = dict(evidence)
        evidence_without_digest.pop("evidence_sha256")
        evidence["evidence_sha256"] = hashlib.sha256(
            _canonical_json(evidence_without_digest)
        ).hexdigest()
    raw = _canonical_json(artifact)
    path.write_bytes(raw)

    with pytest.raises(RecommendationPortfolioCalendarArtifactV1Error, match="evidence_codec_rejected"):
        read_portfolio_period_calendar_evidence_v1(
            path,
            expected_sha256=hashlib.sha256(raw).hexdigest(),
            protected_roots=protected,
        )


def test_create_only_collision_preserves_original_bytes(tmp_path: Path) -> None:
    research, protected = _roots(tmp_path)
    path = research / "period-calendar.v1.json"
    original = b"preserve existing candidate bytes"
    path.write_bytes(original)

    with pytest.raises(RecommendationPortfolioCalendarArtifactV1Error, match="create_only_collision"):
        _write(path, _evidence(), protected)

    assert path.read_bytes() == original


def test_writer_does_not_create_missing_parent_or_any_partial_layout(tmp_path: Path) -> None:
    _, protected = _roots(tmp_path)
    missing_parent = tmp_path / "not-created" / "nested"
    path = missing_parent / "period-calendar.v1.json"

    with pytest.raises(RecommendationPortfolioCalendarArtifactV1Error, match="artifact_parent_component_missing"):
        _write(path, _evidence(), protected)

    assert not missing_parent.exists()
    assert not missing_parent.parent.exists()


def test_writer_rejects_protected_root_overlap_before_creating_artifact(
    tmp_path: Path,
) -> None:
    research, protected = _roots(tmp_path)
    path = protected[0] / "candidate.json"

    with pytest.raises(RecommendationPortfolioCalendarArtifactV1Error, match="overlaps_protected"):
        _write(path, _evidence(), protected)

    assert not path.exists()
    assert research.exists()


def test_writer_requires_external_protected_root_inventory(tmp_path: Path) -> None:
    research, _protected = _roots(tmp_path)
    path = research / "period-calendar.v1.json"

    with pytest.raises(RecommendationPortfolioCalendarArtifactV1Error, match="protected_roots_required"):
        write_portfolio_period_calendar_evidence_create_only_v1(
            path, _evidence(), protected_roots=()
        )

    assert not path.exists()


@pytest.mark.parametrize("basename", ["calendar.json:stream", "CON.json", "calendar.json."])
def test_writer_rejects_nonportable_or_aliasable_basename(
    tmp_path: Path, basename: str
) -> None:
    research, protected = _roots(tmp_path)

    with pytest.raises(RecommendationPortfolioCalendarArtifactV1Error, match="artifact_basename_invalid"):
        _write(research / basename, _evidence(), protected)

    assert not (research / basename).exists()


@pytest.mark.parametrize(
    "path_factory",
    [
        lambda _path: Path("relative-calendar.json"),
        lambda path: path / ".." / "research-candidates" / "calendar.json",
        lambda path: path / "one" / ".." / ".." / "research-candidates" / "calendar.json",
    ],
)
def test_writer_rejects_relative_or_parent_traversal_alias(
    tmp_path: Path, path_factory: Callable[[Path], Path]
) -> None:
    research, protected = _roots(tmp_path)
    path = path_factory(research)

    with pytest.raises(RecommendationPortfolioCalendarArtifactV1Error, match="canonical_absolute_path"):
        _write(path, _evidence(), protected)

    assert not (research / "calendar.json").exists()


def test_reader_rejects_hardlinked_artifact(tmp_path: Path) -> None:
    research, protected = _roots(tmp_path)
    path = research / "period-calendar.v1.json"
    external_sha = _write(path, _evidence(), protected)
    alias = research / "second-name.json"
    try:
        os.link(path, alias)
    except OSError as exc:
        pytest.skip(f"hardlink unavailable on this filesystem: {exc}")

    with pytest.raises(RecommendationPortfolioCalendarArtifactV1Error, match="hardlink_refused"):
        read_portfolio_period_calendar_evidence_v1(
            path, expected_sha256=external_sha, protected_roots=protected
        )


def test_reader_rejects_reparse_or_symlink_ancestor_when_supported(tmp_path: Path) -> None:
    research, protected = _roots(tmp_path)
    path = research / "period-calendar.v1.json"
    external_sha = _write(path, _evidence(), protected)
    linked = tmp_path / "research-alias"
    try:
        os.symlink(research, linked, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlink unavailable on this platform: {exc}")

    with pytest.raises(RecommendationPortfolioCalendarArtifactV1Error, match="reparse_component_refused"):
        read_portfolio_period_calendar_evidence_v1(
            linked / path.name, expected_sha256=external_sha, protected_roots=protected
        )
