from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from data_module.open_data_quarterly_announcement_crosswalk import (
    QuarterlyAnnouncementCrosswalkError,
    build_quarterly_announcement_crosswalk,
)


_MOPS_CSV_FIELDS = (
    "stock_code",
    "statement_type",
    "period",
    "as_of_date",
    "announced_date",
    "available_date",
    "source",
    "source_version",
    "availability_contract_version",
    "evidence_class",
    "source_hash",
    "revision",
    "parent_revision",
)


def _quarterly_audit(
    profiles: list[dict[str, str]],
    *,
    market: str = "TWSE",
    statement: str = "balance_sheet",
) -> dict[str, object]:
    return {
        "schema_version": "baldr.open_data_quarterly_candidate_audit.v1",
        "candidate_only": True,
        "formal_db_write": False,
        "source_acceptance": False,
        "gate_credit": False,
        "downstream_eligibility": "none",
        "resources": [
            {
                "dataset_id": "94831",
                "market": market,
                "statement": statement,
                "industry": "general",
                "artifact": "quarterly.csv",
                "sha256": "c" * 64,
                "state": "available",
                "row_profiles_complete": True,
                "row_profiles": profiles,
            }
        ],
    }


def _event(
    *,
    code: str = "2330",
    market: str = "sii",
    item: str = "F26",
    statement: str = "balance_sheet",
    period: str = "2026-Q2",
    announced: str = "2026-08-12",
    source_sha: str = "a" * 64,
) -> dict[str, str]:
    return {
        "stock_code": code,
        "statement_type": statement,
        "period": period,
        "as_of_date": "2026-06-30",
        "announced_date": announced,
        "available_date": "2026-08-13",
        "source": "mops.ezsearch.statement_publication",
        "source_version": "mops-ezsearch-statement-publication.v1",
        "availability_contract_version": "formal-availability.v2",
        "evidence_class": "official_announcement",
        "source_hash": f"sha256:{source_sha}",
        "revision": "1",
        "parent_revision": "",
        "market": market,
        "announcement_item": item,
        "announcement_at": f"{announced}T12:34:56+08:00",
        "event_hash": hashlib.sha256(
            f"{market}|{code}|{statement}|{period}|{announced}".encode("utf-8")
        ).hexdigest(),
    }


def _announcement_root(
    root: Path,
    *,
    events: list[dict[str, str]] | None = None,
    query_groups: tuple[tuple[str, str], ...] = (
        ("sii", "F26"),
        ("sii", "F27"),
        ("sii", "F28"),
        ("otc", "F26"),
        ("otc", "F27"),
        ("otc", "F28"),
    ),
) -> Path:
    rows = list(events) if events is not None else [_event()]
    root.mkdir(parents=True, exist_ok=True)
    query_rows: list[dict[str, object]] = []
    sha_by_group: dict[tuple[str, str], str] = {}
    for index, (market, item) in enumerate(query_groups):
        sha = chr(ord("a") + index) * 64
        sha_by_group[(market, item)] = sha
        event_count = sum(
            1
            for event in rows
            if event.get("market") == market and event.get("announcement_item") == item
        )
        query_rows.append(
            {
                "market": market,
                "announcement_item": item,
                "response_sha256": sha,
                "source_status": "success" if event_count else "fail",
                "row_count": event_count,
                "error_code": "",
                "query_start_date": "2026-07-01",
                "query_end_date": "2026-09-30",
            }
        )
    projection: list[dict[str, str]] = []
    raw_rows: list[dict[str, str]] = []
    for item in rows:
        clean = {key: item[key] for key in _MOPS_CSV_FIELDS}
        group = (item["market"], item["announcement_item"])
        clean["source_hash"] = f"sha256:{sha_by_group[group]}"
        projection.append(clean)
        raw = dict(item)
        raw["source_hash"] = f"sha256:{sha_by_group[group]}"
        raw_rows.append(raw)

    payload = {
        "schema_version": "mops-ezsearch-statement-availability.v1",
        "source_id": "mops.ezsearch.statement_publication",
        "source_version": "mops-ezsearch-statement-publication.v1",
        "query_start_date": "2026-07-01",
        "query_end_date": "2026-09-30",
        "research_only": True,
        "read_only_source": True,
        "formal_oos_allowed": False,
        "formal_credit_authorized": False,
        "production_scheduler_allowed": False,
        "production_blend_alpha_bp": 0,
        "query_manifest": query_rows,
        "rows": raw_rows,
        "availability_projection": projection,
    }
    (root / "mops-statement-availability.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    with (root / "fundamental-statement-availability.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=_MOPS_CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(projection)
    return root


def test_crosswalk_matches_same_market_code_statement_and_period(tmp_path: Path) -> None:
    announcement_root = _announcement_root(tmp_path / "announcements")
    audit = build_quarterly_announcement_crosswalk(
        quarterly_audit=_quarterly_audit(
            [{"issuer_code": "2330", "fiscal_period": "115-Q2"}]
        ),
        announcement_candidate_roots=[announcement_root],
    )

    row = audit["resources"][0]["rows"][0]
    assert row["fiscal_period"] == "2026-Q2"
    assert row["status"] == "one_announcement_candidate"
    assert row["announcement_candidates"][0]["announced_date"] == "2026-08-12"
    assert row["announcement_candidates"][0]["announcement_at"] == "2026-08-12T12:34:56+08:00"
    assert row["announcement_candidates"][0]["event_sha256"]
    assert row["announcement_timestamp_resolution"] == "unique_candidate_timestamp"
    assert audit["unique_announcement_timestamp_match_count"] == 1
    assert audit["candidate_only"] is True
    assert audit["source_acceptance"] is False
    assert audit["gate_credit"] is False
    assert audit["downstream_eligibility"] == "none"
    assert audit["status"] == "available"


def test_missing_event_is_only_described_within_selected_query_window(tmp_path: Path) -> None:
    audit = build_quarterly_announcement_crosswalk(
        quarterly_audit=_quarterly_audit(
            [{"issuer_code": "2317", "fiscal_period": "115-Q2"}]
        ),
        announcement_candidate_roots=[_announcement_root(tmp_path / "announcements")],
    )

    row = audit["resources"][0]["rows"][0]
    assert row["status"] == "not_observed_in_selected_windows"
    assert "不等於未申報" in " ".join(audit["limitations"])


def test_missing_query_group_is_not_reported_as_no_announcement(tmp_path: Path) -> None:
    root = _announcement_root(
        tmp_path / "announcements",
        events=[],
        query_groups=(("sii", "F26"),),
    )
    audit = build_quarterly_announcement_crosswalk(
        quarterly_audit=_quarterly_audit(
            [{"issuer_code": "2330", "fiscal_period": "115-Q2"}], market="TPEx"
        ),
        announcement_candidate_roots=[root],
    )

    assert audit["resources"][0]["rows"][0]["status"] == "query_window_incomplete"
    assert audit["status"] == "partial"


def test_duplicate_announcement_candidates_are_kept_ambiguous(tmp_path: Path) -> None:
    first = _event(announced="2026-08-12", source_sha="a" * 64)
    second = _event(announced="2026-08-13", source_sha="a" * 64)
    root = _announcement_root(tmp_path / "announcements", events=[first, second])
    audit = build_quarterly_announcement_crosswalk(
        quarterly_audit=_quarterly_audit(
            [{"issuer_code": "2330", "fiscal_period": "2026-Q2"}]
        ),
        announcement_candidate_roots=[root],
    )

    row = audit["resources"][0]["rows"][0]
    assert row["status"] == "multiple_announcement_candidates"
    assert row["announcement_count"] == 2
    assert row["announcement_timestamp_resolution"] == "ambiguous_candidate_versions"


def test_candidate_boundary_and_projection_csv_are_enforced(tmp_path: Path) -> None:
    root = _announcement_root(tmp_path / "announcements")
    unsafe_audit = _quarterly_audit(
        [{"issuer_code": "2330", "fiscal_period": "115-Q2"}]
    )
    unsafe_audit["gate_credit"] = True
    with pytest.raises(QuarterlyAnnouncementCrosswalkError, match="boundary"):
        build_quarterly_announcement_crosswalk(
            quarterly_audit=unsafe_audit,
            announcement_candidate_roots=[root],
        )

    csv_path = root / "fundamental-statement-availability.csv"
    csv_path.write_text(csv_path.read_text(encoding="utf-8").replace("2026-08-12", "2026-08-14"), encoding="utf-8")
    with pytest.raises(QuarterlyAnnouncementCrosswalkError, match="projection_mismatch"):
        build_quarterly_announcement_crosswalk(
            quarterly_audit=_quarterly_audit(
                [{"issuer_code": "2330", "fiscal_period": "115-Q2"}]
            ),
            announcement_candidate_roots=[root],
        )
