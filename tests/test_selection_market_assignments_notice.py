from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

import pytest

from data_module.selection_market_assignments import (
    CurrentMarketAssignmentError,
    CurrentMarketAssignmentReader,
)
from scripts.refresh_current_market_status_observation import (
    capture_sources,
    official_notice_source_spec,
)
from tests.test_current_market_status_observation import _tpex_notice_html
from tests.test_selection_market_assignments import (
    _SOURCE_URLS,
    _pointer_cutoff,
    _rewrite_bundle,
    _roster_rows,
    _spec,
)


_NOTICE_URL = "https://www.tpex.org.tw/storage/eb_data/11509/11500054131.html"


def _create_capture_with_notice(
    output_root: Path,
    *,
    notice_html: bytes,
    rows: dict[str, list[dict[str, str]]],
) -> Path:
    """以既有名錄規格與官方公告 parser 建立有界合成 CMS capture。"""
    roster_specs = tuple(_spec(source_id) for source_id in _SOURCE_URLS)
    notice_spec = official_notice_source_spec(_NOTICE_URL)
    specs = (*roster_specs, notice_spec)
    raw_by_url = {
        spec.url: json.dumps(
            rows[spec.source_id], ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        for spec in roster_specs
    }
    raw_by_url[_NOTICE_URL] = notice_html
    captured_at = datetime.now(timezone.utc) - timedelta(seconds=5)

    def fetcher(url: str, **_: object) -> tuple[bytes, int, str, str, datetime, dict[str, str]]:
        body = raw_by_url[url]
        content_type = "text/html; charset=utf-8" if url == _NOTICE_URL else "application/json"
        return body, 200, content_type, url, captured_at, {"content-length": str(len(body))}

    capture_sources(output_dir=output_root, specs=specs, fetcher=fetcher)
    return output_root / "current_market_status_pointer.json"


def test_from_pointer_and_exact_exclude_explicitly_terminated_roster_member(tmp_path: Path) -> None:
    notice = _tpex_notice_html(
        "公告乙公司股份有限公司股票（股票代號：8183）自115年9月23日起停止櫃檯買賣，並自115年10月1日起終止櫃檯買賣。",
        "本中心受理該公司115年8月17日終止上櫃申請書。",
    )
    pointer_path = _create_capture_with_notice(
        tmp_path / "terminated",
        notice_html=notice,
        rows=_roster_rows(tpex=("2330", "8183")),
    )
    cutoff = _pointer_cutoff(pointer_path)

    reader = CurrentMarketAssignmentReader.from_pointer(pointer_path, cutoff_at=cutoff)
    observation = reader.get("8183")
    assert observation.state == "unknown"
    assert observation.market is None
    assert observation.reason_code == "explicit_termination_evidence_conflict"
    assert observation.termination_evidence == "positive_current_conflict"

    exact_reader = CurrentMarketAssignmentReader.from_exact(reader.source_pin, cutoff_at=cutoff)
    exact_observation = exact_reader.get("8183")
    assert exact_observation.state == observation.state
    assert exact_observation.market == observation.market
    assert exact_observation.reason_code == observation.reason_code
    assert exact_observation.termination_evidence == observation.termination_evidence


def test_suspension_only_notice_does_not_become_termination_evidence(tmp_path: Path) -> None:
    notice = _tpex_notice_html(
        "公告甲公司股票（證券代號：5371）自115年8月24日起停止櫃檯買賣。",
        "本中心受理該公司115年8月17日終止上櫃申請書。",
    )
    pointer_path = _create_capture_with_notice(
        tmp_path / "suspension-only",
        notice_html=notice,
        rows=_roster_rows(tpex=("2330", "5371")),
    )

    reader = CurrentMarketAssignmentReader.from_pointer(
        pointer_path, cutoff_at=_pointer_cutoff(pointer_path)
    )
    observation = reader.get("5371")
    assert observation.state == "assigned_tpex"
    assert observation.reason_code == "unique_positive_current_roster_membership"
    assert observation.termination_evidence == "not_verified"


def test_rebound_snapshot_with_wrong_notice_termination_date_is_rejected(tmp_path: Path) -> None:
    notice = _tpex_notice_html(
        "公告乙公司股票（股票代號：8183）自115年9月23日起停止櫃檯買賣，並自115年10月1日起終止櫃檯買賣。",
        "",
    )
    pointer_path = _create_capture_with_notice(
        tmp_path / "wrong-termination-date",
        notice_html=notice,
        rows=_roster_rows(tpex=("2330", "8183")),
    )

    def mutate_snapshot(snapshot: dict[str, Any]) -> None:
        security = next(row for row in snapshot["securities"] if row["symbol"] == "8183")
        evidence = next(row for row in security["evidence"] if row["evidence_type"] == "terminated")
        evidence["effective_from"] = "2026-10-02"

    _rewrite_bundle(pointer_path, mutate_snapshot=mutate_snapshot)
    with pytest.raises(
        CurrentMarketAssignmentError,
        match="market_assignment_termination_source_evidence_mismatch",
    ):
        CurrentMarketAssignmentReader.from_pointer(
            pointer_path, cutoff_at=_pointer_cutoff(pointer_path)
        )
