from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from data_module.selection_market_assignments import (
    CurrentMarketAssignmentError,
    CurrentMarketAssignmentReader,
    CurrentMarketAssignmentSourcePinV1,
)
from scripts.refresh_current_market_status_observation import SourceSpec, capture_sources


_SOURCE_URLS = {
    "twse.current_roster": "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
    "tpex.current_otc_roster": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O",
    "tpex.current_emerging_roster": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_R",
}
_MARKETS = {
    "twse.current_roster": "twse",
    "tpex.current_otc_roster": "tpex",
    "tpex.current_emerging_roster": "emerging",
}


def _spec(source_id: str) -> SourceSpec:
    return SourceSpec(
        source_id=source_id,
        url=_SOURCE_URLS[source_id],
        evidence_type="current_roster",
        market=_MARKETS[source_id],
        description="合成現況名錄來源",
        source_date_aliases=("Date",) if source_id.startswith("tpex.") else (),
    )


def _roster_rows(*, twse: tuple[str, ...] = ("1101",), tpex: tuple[str, ...] = ("2330",), emerging: tuple[str, ...] = ("9101",)) -> dict[str, list[dict[str, str]]]:
    return {
        "twse.current_roster": [
            {"出表日期": "20261006", "公司代號": code, "公司名稱": f"TWSE {code}"}
            for code in twse
        ],
        "tpex.current_otc_roster": [
            {"Date": "20261006", "SecuritiesCompanyCode": code, "CompanyAbbreviation": f"TPEx {code}"}
            for code in tpex
        ],
        "tpex.current_emerging_roster": [
            {"Date": "20261006", "SecuritiesCompanyCode": code, "CompanyAbbreviation": f"Emerging {code}"}
            for code in emerging
        ],
    }


def _create_capture(
    output_root: Path,
    *,
    rows: dict[str, list[dict[str, str]]] | None = None,
    include_source_ids: tuple[str, ...] = tuple(_SOURCE_URLS),
    fail_unrelated_source: bool = False,
    fail_source_ids: tuple[str, ...] = (),
    termination: tuple[str, str] | None = None,
) -> Path:
    selected_rows = rows or _roster_rows()
    specs = [_spec(source_id) for source_id in include_source_ids]
    url_to_id = {spec.url: spec.source_id for spec in specs}
    raw_by_id = {
        source_id: json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        for source_id, payload in selected_rows.items()
    }
    if termination is not None:
        symbol, effective_date = termination
        termination_spec = SourceSpec(
            source_id="twse.terminated_listing",
            url="https://www.twse.com.tw/company/suspendListingCsvAndHtml?lang=en&selectYear=&type=html",
            evidence_type="terminated",
            market="twse",
            description="合成終止名錄正向證據",
        )
        specs.append(termination_spec)
        url_to_id[termination_spec.url] = termination_spec.source_id
        raw_by_id[termination_spec.source_id] = json.dumps(
            [{"公司代號": symbol, "終止上市日期": effective_date}],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    if fail_unrelated_source:
        unrelated = SourceSpec(
            source_id="twse.disposition_current",
            url="https://openapi.twse.com.tw/v1/announcement/punish",
            evidence_type="trading_restriction",
            market="twse",
            description="刻意失敗的非名錄來源",
        )
        specs.append(unrelated)
        url_to_id[unrelated.url] = unrelated.source_id
    failed_ids = set(fail_source_ids)
    if fail_unrelated_source:
        failed_ids.add("twse.disposition_current")

    captured_at = datetime.now(timezone.utc) - timedelta(seconds=5)

    def fetcher(url: str, **_: object) -> tuple[bytes, int, str, str, datetime, dict[str, str]]:
        source_id = url_to_id[url]
        if source_id in failed_ids:
            raise OSError("合成來源擷取失敗")
        return raw_by_id[source_id], 200, "application/json", url, captured_at, {}

    capture_sources(output_dir=output_root, specs=tuple(specs), fetcher=fetcher)
    return output_root / "current_market_status_pointer.json"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _rewrite_bundle(pointer_path: Path, *, mutate_snapshot: Any | None = None) -> None:
    pointer = _load_json(pointer_path)
    output_root = pointer_path.parent
    snapshot_path = output_root / pointer["snapshot_path"]
    manifest_path = output_root / pointer["manifest_path"]
    snapshot = _load_json(snapshot_path)
    manifest = _load_json(manifest_path)
    if mutate_snapshot is not None:
        mutate_snapshot(snapshot)
    manifest["raw_sources"] = [
        {
            key: capture.get(key)
            for key in ("source_id", "raw_path", "raw_sha256", "captured_at", "status", "parse_status")
        }
        for capture in snapshot["source_captures"]
    ]
    _write_json(snapshot_path, snapshot)
    snapshot_sha = "sha256:" + hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
    manifest["snapshot_sha256"] = snapshot_sha
    _write_json(manifest_path, manifest)
    pointer["snapshot_sha256"] = snapshot_sha
    pointer["manifest_sha256"] = "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    _write_json(pointer_path, pointer)


def _pointer_cutoff(pointer_path: Path) -> datetime:
    pointer = _load_json(pointer_path)
    return datetime.fromisoformat(pointer["published_at"].replace("Z", "+00:00"))


def _capture_by_id(snapshot: dict[str, Any], source_id: str) -> dict[str, Any]:
    return next(row for row in snapshot["source_captures"] if row["source_id"] == source_id)


def test_unique_membership_and_exact_reopen_ignore_advanced_pointer(tmp_path: Path) -> None:
    pointer_path = _create_capture(tmp_path / "cms-output", fail_unrelated_source=True)
    cutoff = _pointer_cutoff(pointer_path)
    reader = CurrentMarketAssignmentReader.from_pointer(pointer_path, cutoff_at=cutoff)
    pin = reader.source_pin

    assert pin.snapshot_partial_failure is True
    twse = reader.get("1101")
    assert twse.state == "assigned_twse"
    assert twse.market == "twse"
    assert twse.termination_evidence == "not_verified"
    assert twse.historical_pit_eligible is False
    assert twse.official_available_at is None
    assert twse.roster_source_ids == ("twse.current_roster",)
    assert reader.get("2330").state == "assigned_tpex"
    assert reader.get("9999").reason_code == "no_positive_roster_evidence"

    old_run_id = pin.run_id
    _create_capture(
        pointer_path.parent,
        rows=_roster_rows(twse=("2454",), tpex=("2881",), emerging=("9102",)),
    )
    current_pointer = _load_json(pointer_path)
    assert current_pointer["run_id"] != old_run_id

    reopened = CurrentMarketAssignmentReader.from_exact(pin, cutoff_at=cutoff)
    assert reopened.source_pin.run_id == old_run_id
    assert reopened.get("1101").state == "assigned_twse"
    assert reopened.get("2454").state == "unknown"
    as_dict = reopened.source_pin.to_dict()
    assert CurrentMarketAssignmentSourcePinV1.from_dict(as_dict) == pin
    assert CurrentMarketAssignmentReader.from_exact(as_dict, cutoff_at=cutoff).get("2330").state == "assigned_tpex"


def test_cross_market_emerging_duplicates_and_absence_are_unknown(tmp_path: Path) -> None:
    pointer_path = _create_capture(
        tmp_path / "cms-output",
        rows=_roster_rows(twse=("1101", "1101", "2330"), tpex=("2330",), emerging=("9101",)),
    )
    reader = CurrentMarketAssignmentReader.from_pointer(pointer_path, cutoff_at=_pointer_cutoff(pointer_path))

    duplicate = reader.get("1101")
    assert duplicate.state == "unknown"
    assert duplicate.reason_code == "duplicate_membership_within_source"
    collision = reader.get("2330")
    assert collision.state == "unknown"
    assert collision.reason_code == "cross_market_roster_conflict"
    emerging = reader.get("9101")
    assert emerging.state == "unknown"
    assert emerging.reason_code == "emerging_roster_membership_unsupported"
    assert reader.get("9999").state == "unknown"


def test_missing_roster_source_keeps_assignment_unknown(tmp_path: Path) -> None:
    pointer_path = _create_capture(
        tmp_path / "cms-output",
        include_source_ids=("twse.current_roster", "tpex.current_otc_roster"),
    )
    reader = CurrentMarketAssignmentReader.from_pointer(pointer_path, cutoff_at=_pointer_cutoff(pointer_path))

    result = reader.get("1101")
    assert result.state == "unknown"
    assert result.reason_code == "required_roster_source_incomplete"
    assert result.roster_source_ids == ("tpex.current_emerging_roster",)
    assert reader.source_pin.captures[-1].status == "missing"

    failed_pointer = _create_capture(
        tmp_path / "failed-source",
        fail_source_ids=("twse.current_roster",),
    )
    failed_reader = CurrentMarketAssignmentReader.from_pointer(
        failed_pointer,
        cutoff_at=_pointer_cutoff(failed_pointer),
    )
    assert failed_reader.get("1101").state == "unknown"
    assert failed_reader.get("1101").reason_code == "required_roster_source_incomplete"


def test_parsed_roster_without_capture_clock_is_rejected_after_hash_rebuild(tmp_path: Path) -> None:
    pointer_path = _create_capture(tmp_path / "missing-clock")

    def remove_clock(snapshot: dict[str, Any]) -> None:
        _capture_by_id(snapshot, "twse.current_roster")["captured_at"] = None

    _rewrite_bundle(pointer_path, mutate_snapshot=remove_clock)
    with pytest.raises(CurrentMarketAssignmentError, match="market_assignment_roster_capture_clock_missing"):
        CurrentMarketAssignmentReader.from_pointer(pointer_path, cutoff_at=_pointer_cutoff(pointer_path))


def test_empty_tpex_or_emerging_roster_cannot_certify_twse_assignment(tmp_path: Path) -> None:
    empty_tpex_pointer = _create_capture(
        tmp_path / "empty-tpex",
        rows=_roster_rows(twse=("1101",), tpex=(), emerging=("9101",)),
    )
    empty_tpex_reader = CurrentMarketAssignmentReader.from_pointer(
        empty_tpex_pointer,
        cutoff_at=_pointer_cutoff(empty_tpex_pointer),
    )
    empty_tpex_result = empty_tpex_reader.get("1101")
    assert empty_tpex_result.state == "unknown"
    assert empty_tpex_result.reason_code == "required_roster_source_empty"
    assert empty_tpex_result.roster_source_ids == ("tpex.current_otc_roster",)

    empty_emerging_pointer = _create_capture(
        tmp_path / "empty-emerging",
        rows=_roster_rows(twse=("1101",), tpex=("2330",), emerging=()),
    )
    empty_emerging_reader = CurrentMarketAssignmentReader.from_pointer(
        empty_emerging_pointer,
        cutoff_at=_pointer_cutoff(empty_emerging_pointer),
    )
    empty_emerging_result = empty_emerging_reader.get("1101")
    assert empty_emerging_result.state == "unknown"
    assert empty_emerging_result.reason_code == "required_roster_source_empty"
    assert empty_emerging_result.roster_source_ids == ("tpex.current_emerging_roster",)


def test_explicit_current_termination_conflict_and_future_effective_notice(tmp_path: Path) -> None:
    current_pointer = _create_capture(tmp_path / "current", termination=("1101", "20200101"))
    current_reader = CurrentMarketAssignmentReader.from_pointer(
        current_pointer,
        cutoff_at=_pointer_cutoff(current_pointer),
    )
    current = current_reader.get("1101")
    assert current.state == "unknown"
    assert current.reason_code == "explicit_termination_evidence_conflict"
    assert current.termination_evidence == "positive_current_conflict"

    future_pointer = _create_capture(tmp_path / "future", termination=("1101", "20990101"))
    future_reader = CurrentMarketAssignmentReader.from_pointer(
        future_pointer,
        cutoff_at=_pointer_cutoff(future_pointer),
    )
    future = future_reader.get("1101")
    assert future.state == "assigned_twse"
    assert future.termination_evidence == "future_effective_notice"


def test_source_schema_endpoint_and_bad_capture_bytes_fail_closed(tmp_path: Path) -> None:
    bad_schema = _roster_rows()
    bad_schema["twse.current_roster"] = [{"股票代號": "1101"}]
    pointer_path = _create_capture(tmp_path / "schema", rows=bad_schema)
    with pytest.raises(CurrentMarketAssignmentError, match="market_assignment_roster_code_field_missing"):
        CurrentMarketAssignmentReader.from_pointer(pointer_path, cutoff_at=_pointer_cutoff(pointer_path))

    good_pointer = _create_capture(tmp_path / "tamper")
    snapshot_path = good_pointer.parent / _load_json(good_pointer)["snapshot_path"]

    def wrong_endpoint(snapshot: dict[str, Any]) -> None:
        _capture_by_id(snapshot, "twse.current_roster")["requested_url"] = "https://example.invalid/list"

    _rewrite_bundle(good_pointer, mutate_snapshot=wrong_endpoint)
    with pytest.raises(CurrentMarketAssignmentError, match="market_assignment_roster_endpoint_mismatch"):
        CurrentMarketAssignmentReader.from_pointer(good_pointer, cutoff_at=_pointer_cutoff(good_pointer))

    tampered_pointer = _create_capture(tmp_path / "raw-tamper")
    snapshot = _load_json(tampered_pointer.parent / _load_json(tampered_pointer)["snapshot_path"])
    raw_path = Path(_capture_by_id(snapshot, "twse.current_roster")["raw_path"])
    raw_path.write_bytes(raw_path.read_bytes() + b" ")
    with pytest.raises(CurrentMarketAssignmentError, match="market_assignment_roster_raw_hash_mismatch"):
        CurrentMarketAssignmentReader.from_pointer(tampered_pointer, cutoff_at=_pointer_cutoff(tampered_pointer))


def test_duplicate_raw_json_keys_and_future_roster_date_are_rejected(tmp_path: Path) -> None:
    pointer_path = _create_capture(tmp_path / "duplicate-raw")
    pointer = _load_json(pointer_path)
    snapshot_path = pointer_path.parent / pointer["snapshot_path"]
    snapshot = _load_json(snapshot_path)
    capture = _capture_by_id(snapshot, "twse.current_roster")
    raw_path = Path(capture["raw_path"])
    raw = b'[{"\xe5\x87\xba\xe8\xa1\xa8\xe6\x97\xa5\xe6\x9c\x9f":"20261006","\xe5\x85\xac\xe5\x8f\xb8\xe4\xbb\xa3\xe8\x99\x9f":"1101","\xe5\x85\xac\xe5\x8f\xb8\xe4\xbb\xa3\xe8\x99\x9f":"1102"}]'
    raw_path.write_bytes(raw)
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    capture["raw_sha256"] = digest
    capture["raw_bytes"] = len(raw)
    for security in snapshot["securities"]:
        for evidence in security["evidence"]:
            if evidence["source_id"] == "twse.current_roster":
                evidence["raw_sha256"] = digest
    _write_json(snapshot_path, snapshot)
    manifest_path = pointer_path.parent / pointer["manifest_path"]
    manifest = _load_json(manifest_path)
    manifest["raw_sources"] = [
        {
            key: row.get(key)
            for key in ("source_id", "raw_path", "raw_sha256", "captured_at", "status", "parse_status")
        }
        for row in snapshot["source_captures"]
    ]
    snapshot_sha = "sha256:" + hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
    manifest["snapshot_sha256"] = snapshot_sha
    _write_json(manifest_path, manifest)
    pointer["snapshot_sha256"] = snapshot_sha
    pointer["manifest_sha256"] = "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    _write_json(pointer_path, pointer)
    with pytest.raises(CurrentMarketAssignmentError, match="market_assignment_roster_json_invalid"):
        CurrentMarketAssignmentReader.from_pointer(pointer_path, cutoff_at=_pointer_cutoff(pointer_path))

    future_rows = _roster_rows()
    future_rows["tpex.current_otc_roster"][0]["Date"] = "20990101"
    future_pointer = _create_capture(tmp_path / "future-date", rows=future_rows)
    with pytest.raises(CurrentMarketAssignmentError, match="market_assignment_roster_source_date_after_cutoff"):
        CurrentMarketAssignmentReader.from_pointer(future_pointer, cutoff_at=_pointer_cutoff(future_pointer))


def test_termination_snapshot_fact_must_match_pinned_raw(tmp_path: Path) -> None:
    pointer_path = _create_capture(tmp_path / "termination-mismatch", termination=("1101", "20200101"))

    def mutate(snapshot: dict[str, Any]) -> None:
        security = next(row for row in snapshot["securities"] if row["symbol"] == "1101")
        evidence = next(row for row in security["evidence"] if row["evidence_type"] == "terminated")
        evidence["effective_from"] = "20200102"

    _rewrite_bundle(pointer_path, mutate_snapshot=mutate)
    with pytest.raises(CurrentMarketAssignmentError, match="market_assignment_termination_source_evidence_mismatch"):
        CurrentMarketAssignmentReader.from_pointer(pointer_path, cutoff_at=_pointer_cutoff(pointer_path))


def test_cutoff_validation_and_exact_pin_identity(tmp_path: Path) -> None:
    pointer_path = _create_capture(tmp_path / "cms-output")
    published_at = _pointer_cutoff(pointer_path)
    reader = CurrentMarketAssignmentReader.from_pointer(pointer_path, cutoff_at=published_at)
    assert reader.get("1101").state == "assigned_twse"

    with pytest.raises(CurrentMarketAssignmentError, match="market_assignment_pointer_after_cutoff"):
        CurrentMarketAssignmentReader.from_pointer(pointer_path, cutoff_at=published_at - timedelta(microseconds=1))
    with pytest.raises(CurrentMarketAssignmentError, match="market_assignment_cutoff_must_be_aware"):
        CurrentMarketAssignmentReader.from_pointer(pointer_path, cutoff_at=datetime.now())
    with pytest.raises(CurrentMarketAssignmentError, match="market_assignment_cutoff_in_future"):
        CurrentMarketAssignmentReader.from_pointer(pointer_path, cutoff_at=datetime.now(timezone.utc) + timedelta(days=1))
    with pytest.raises(CurrentMarketAssignmentError, match="market_assignment_exact_cutoff_mismatch"):
        CurrentMarketAssignmentReader.from_exact(reader.source_pin, cutoff_at=published_at - timedelta(seconds=1))

    tampered_pin = reader.source_pin.to_dict()
    tampered_pin["snapshot_sha256"] = "sha256:" + "0" * 64
    with pytest.raises(CurrentMarketAssignmentError, match="market_assignment_pin_identity_mismatch"):
        CurrentMarketAssignmentReader.from_exact(tampered_pin)


def test_duplicate_json_key_and_unsafe_raw_path_are_rejected(tmp_path: Path) -> None:
    pointer_path = _create_capture(tmp_path / "duplicate-json")
    pointer_bytes = pointer_path.read_bytes()
    pointer_path.write_bytes(pointer_bytes[:-2] + b',"run_id":"other"}\n')
    with pytest.raises(CurrentMarketAssignmentError, match="market_assignment_pointer_json_invalid"):
        CurrentMarketAssignmentReader.from_pointer(pointer_path)

    unsafe_pointer = _create_capture(tmp_path / "unsafe-path")

    def unsafe_raw(snapshot: dict[str, Any]) -> None:
        _capture_by_id(snapshot, "twse.current_roster")["raw_path"] = str(unsafe_pointer.parent.parent / "outside.json")

    _rewrite_bundle(unsafe_pointer, mutate_snapshot=unsafe_raw)
    with pytest.raises(CurrentMarketAssignmentError, match="market_assignment_roster_raw_path_outside_root"):
        CurrentMarketAssignmentReader.from_pointer(unsafe_pointer, cutoff_at=_pointer_cutoff(unsafe_pointer))


def test_roster_raw_hardlink_is_rejected(tmp_path: Path) -> None:
    pointer_path = _create_capture(tmp_path / "hardlink")
    pointer = _load_json(pointer_path)
    snapshot_path = pointer_path.parent / pointer["snapshot_path"]
    snapshot = _load_json(snapshot_path)
    capture = _capture_by_id(snapshot, "twse.current_roster")
    raw_path = Path(capture["raw_path"])
    linked_path = raw_path.with_name("twse-linked.raw")
    try:
        os.link(raw_path, linked_path)
    except (OSError, NotImplementedError):
        pytest.skip("此測試環境不允許建立硬連結")
    capture["raw_path"] = str(linked_path)
    manifest_path = pointer_path.parent / pointer["manifest_path"]
    manifest = _load_json(manifest_path)
    next(row for row in manifest["raw_sources"] if row["source_id"] == "twse.current_roster")["raw_path"] = str(linked_path)
    _write_json(snapshot_path, snapshot)
    snapshot_sha = "sha256:" + hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
    manifest["snapshot_sha256"] = snapshot_sha
    _write_json(manifest_path, manifest)
    pointer["snapshot_sha256"] = snapshot_sha
    pointer["manifest_sha256"] = "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    _write_json(pointer_path, pointer)

    with pytest.raises(CurrentMarketAssignmentError, match="market_assignment_roster_raw_file_invalid_or_oversized"):
        CurrentMarketAssignmentReader.from_pointer(pointer_path, cutoff_at=_pointer_cutoff(pointer_path))
