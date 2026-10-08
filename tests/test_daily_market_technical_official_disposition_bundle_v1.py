"""完整 synthetic full-N store 與兩個真 exact source reader 的 F17 bundle 驗收。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone, tzinfo
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
from typing import Any, Callable, Iterator, cast
from zoneinfo import ZoneInfo

import pytest

from app_module.daily_market_technical_official_disposition_bundle_v1 import (
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_MANIFEST_BYTES,
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_ROW_BYTES,
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_ROWS_PER_SHARD,
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_SHARD_BYTES,
    DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_SHARDS,
    DailyMarketTechnicalOfficialDispositionBundleCancelled,
    DailyMarketTechnicalOfficialDispositionBundleError,
    DailyMarketTechnicalOfficialDispositionBundleReaderV1,
    DailyMarketTechnicalOfficialDispositionBundleReferenceV1,
    DailyMarketTechnicalOfficialDispositionBundleSelectedRowsV1,
    DailyMarketTechnicalOfficialDispositionBundleWriterV1,
    DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
)
from app_module.daily_market_technical_universe_v4_producer import (
    DailyMarketTechnicalUniverseV4ProductionRequest,
    produce_daily_market_technical_universe_v4,
)
from app_module.daily_market_technical_universe_v4_store import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS,
    DailyMarketTechnicalUniverseV4Cohort,
    DailyMarketTechnicalUniverseV4StoreReader,
)
from app_module.personal_data_paths import to_internal_io_path
from app_module.rule_research_sample_capture import ResearchCaptureWriteScope, RuleSampleCaptureError
from data_module.selection_market_assignments import (
    CurrentMarketAssignmentReader,
    CurrentMarketAssignmentSourcePinV1,
)
from data_module.selection_official_events import (
    CurrentOfficialDisposalReader,
    CurrentOfficialDisposalSourcePinV1,
)
import scripts.refresh_current_market_status_observation as capture_module
from scripts.refresh_current_market_status_observation import SourceSpec, capture_sources


_TAIPEI = ZoneInfo("Asia/Taipei")
_DECISION_DATE = date(2026, 10, 7)
_CUTOFF = datetime.combine(_DECISION_DATE, time(16, 0), tzinfo=_TAIPEI)
_CAPTURED_AT = datetime(2026, 10, 7, 7, 53, tzinfo=timezone.utc)
_PUBLISHED_AT = datetime(2026, 10, 7, 7, 55, tzinfo=timezone.utc)
_TWSE_ROSTER_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
_TPEX_OTC_ROSTER_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
_TPEX_EMERGING_ROSTER_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_R"
_TWSE_DISPOSAL_URL = "https://openapi.twse.com.tw/v1/announcement/punish"
_TPEX_DISPOSAL_URL = "https://www.tpex.org.tw/openapi/v1/tpex_disposal_information"
_TWSE_DISPOSAL_FIELDS = [
    "編號", "公布日期", "證券代號", "證券名稱", "累計", "處置條件",
    "處置起迄時間", "處置措施", "處置內容", "備註",
]


class _FrozenDateTime(datetime):
    fixed_now: datetime = _PUBLISHED_AT

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> _FrozenDateTime:
        current = cls.fixed_now
        if tz is None:
            return cast(_FrozenDateTime, current.replace(tzinfo=None))
        return cast(_FrozenDateTime, current.astimezone(tz))


@dataclass(frozen=True, slots=True)
class _BundleFixture:
    qa_root: Path
    database: Path
    scope: ResearchCaptureWriteScope
    store_root: Path
    generation_identity_sha256: str
    plan_identity_sha256: str
    expected_plan_sha256: str
    receipt_identity_sha256: str
    expected_receipt_sha256: str
    cohort: DailyMarketTechnicalUniverseV4Cohort
    included_codes: tuple[str, ...]
    excluded_code: str
    parent_roots: tuple[Path, ...]
    source_roots: tuple[Path, ...]
    market_pointer: Path
    disposal_pointer: Path
    market_pin: Any
    disposal_pin: Any
    bundle_root: Path
    reference: DailyMarketTechnicalOfficialDispositionBundleReferenceV1
    verified_state: DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1
    writer: DailyMarketTechnicalOfficialDispositionBundleWriterV1
    original_signatures: tuple[tuple[str, tuple[tuple[str, int, int, str], ...]], ...]


@pytest.fixture(scope="module")
def bundle_fixture() -> Iterator[_BundleFixture]:
    repo_root = Path(__file__).resolve().parents[1]
    qa_parent = repo_root / "output" / "qa"
    qa_parent.mkdir(parents=True, exist_ok=True)
    qa_root = Path(tempfile.mkdtemp(prefix="f17-bundle-v1-synthetic-", dir=to_internal_io_path(qa_parent)))
    database = qa_root / "synthetic_prices.sqlite"
    included_codes = tuple(f"{1000 + index:04d}" for index in range(257))
    excluded_code = "9999"
    cohort = DailyMarketTechnicalUniverseV4Cohort.create(
        universe_id="synthetic-f17-bundle-v1",
        population_version="synthetic-2026-10-07-v1",
        decision_date=_DECISION_DATE,
        raw_stock_codes=(*included_codes, excluded_code),
        excluded_stock_codes=(excluded_code,),
        exclusion_reasons={excluded_code: "合成母體明示排除，保留於 declared 分母"},
    )
    _write_prices(database, included_codes)
    scope = ResearchCaptureWriteScope(qa_root / "technical-output", database)
    store_root = scope.root / "full-technical-store"
    request = DailyMarketTechnicalUniverseV4ProductionRequest(
        source_database=database,
        cohort=cohort,
        decision_cutoff=_CUTOFF,
        store_output_root=store_root,
        research_scope=scope,
    )
    technical_result = produce_daily_market_technical_universe_v4(request)
    assert technical_result.status == "complete", technical_result.to_dict()
    assert technical_result.plan is not None and technical_result.receipt is not None
    assert len(technical_result.plan.segments) == 2
    assert technical_result.completed_segment_indices == (0, 1)
    assert technical_result.receipt.status == "complete"

    included_twse = included_codes[:-1]
    included_tpex = included_codes[-1]
    market_root = qa_root / "market-capture"
    disposal_root = qa_root / "disposal-capture"
    monkeypatch = pytest.MonkeyPatch()
    try:
        _FrozenDateTime.fixed_now = _PUBLISHED_AT
        monkeypatch.setattr(capture_module, "datetime", _FrozenDateTime)
        market_pointer = _capture_market_sources(market_root, included_twse, included_tpex)
        disposal_pointer = _capture_disposal_sources(disposal_root, included_twse[0], included_tpex)
    finally:
        monkeypatch.undo()
    market_reader = CurrentMarketAssignmentReader.from_pointer(market_pointer, cutoff_at=_CUTOFF)
    disposal_reader = CurrentOfficialDisposalReader.from_pointer(disposal_pointer, cutoff_at=_CUTOFF)
    market_pin = market_reader.source_pin
    disposal_pin = disposal_reader.source_pin

    verified_store = DailyMarketTechnicalUniverseV4StoreReader(store_root).read_exact(
        technical_result.generation_identity_sha256 or "",
        technical_result.plan_identity_sha256 or "",
        technical_result.receipt_identity_sha256 or "",
        expected_receipt_sha256=technical_result.receipt_content_sha256 or "",
        expected_plan_sha256=technical_result.plan_sha256,
    )
    parent_roots = tuple(Path(reference.parent_root) for _, reference in verified_store.segment_parent_references)
    source_roots = (
        store_root,
        *parent_roots,
        Path(market_pin.output_root),
        Path(disposal_pin.output_root),
    )
    source_paths = (database, *source_roots)
    original_signatures = tuple(
        (str(path), _tree_signature(path)) for path in source_paths
    )

    bundle_root = scope.root / "daily_market_technical_official_disposition_v1"
    writer = DailyMarketTechnicalOfficialDispositionBundleWriterV1(
        bundle_root,
        research_scope=scope,
    )
    reference = writer.create_from_pins(
        store_output_root=store_root,
        generation_identity_sha256=technical_result.generation_identity_sha256 or "",
        plan_identity_sha256=technical_result.plan_identity_sha256 or "",
        expected_plan_sha256=technical_result.plan_sha256 or "",
        receipt_identity_sha256=technical_result.receipt_identity_sha256 or "",
        expected_receipt_sha256=technical_result.receipt_content_sha256 or "",
        market_assignment_source_pin=market_pin,
        official_disposal_source_pin=disposal_pin,
    )
    reopened = DailyMarketTechnicalOfficialDispositionBundleReaderV1(bundle_root).read_exact(
        reference.bundle_identity_sha256,
        expected_manifest_sha256=reference.manifest_sha256,
    )
    assert len(tuple(reopened.iter_verified_rows())) == 258
    after_signatures = tuple((str(path), _tree_signature(path)) for path in source_paths)
    assert original_signatures == after_signatures
    yield _BundleFixture(
        qa_root=qa_root,
        database=database,
        scope=scope,
        store_root=store_root,
        generation_identity_sha256=cast(str, technical_result.generation_identity_sha256),
        plan_identity_sha256=cast(str, technical_result.plan_identity_sha256),
        expected_plan_sha256=cast(str, technical_result.plan_sha256),
        receipt_identity_sha256=cast(str, technical_result.receipt_identity_sha256),
        expected_receipt_sha256=cast(str, technical_result.receipt_content_sha256),
        cohort=cohort,
        included_codes=included_codes,
        excluded_code=excluded_code,
        parent_roots=parent_roots,
        source_roots=source_roots,
        market_pointer=market_pointer,
        disposal_pointer=disposal_pointer,
        market_pin=market_pin,
        disposal_pin=disposal_pin,
        bundle_root=bundle_root,
        reference=reference,
        verified_state=reopened,
        writer=writer,
        original_signatures=original_signatures,
    )


def test_real_257_store_and_actual_source_readers_roundtrip_in_fresh_process(
    bundle_fixture: _BundleFixture,
) -> None:
    fixture = bundle_fixture
    reader = DailyMarketTechnicalOfficialDispositionBundleReaderV1(fixture.bundle_root)
    state = reader.read_exact(
        fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=fixture.reference.manifest_sha256,
    )
    rows = tuple(state.iter_verified_rows())
    assert len(rows) == 258
    manifest_path = fixture.bundle_root / fixture.reference.manifest_relative_path
    assert manifest_path.stat().st_nlink == 1
    for shard in cast(list[object], state.manifest["row_shards"]):
        shard_reference = cast(dict[str, object], shard)
        object_path = fixture.bundle_root / cast(str, shard_reference["relative_path"])
        assert object_path.stat().st_nlink == 1
    assert tuple(row.stock_code for row in rows) == tuple(sorted((*fixture.included_codes, fixture.excluded_code)))
    assert sum(row.cohort_role == "included" for row in rows) == 257
    assert sum(row.cohort_role == "excluded" for row in rows) == 1
    by_code = {row.stock_code: row.to_dict() for row in rows}

    twse = by_code[fixture.included_codes[0]]
    assert twse["technical_status"] == "processed"
    assert twse["technical_missing_data"] is False
    twse_market = cast(dict[str, object], twse["market_assignment"])
    twse_disposal = cast(dict[str, object], twse["official_disposal"])
    assert twse_market["state"] == "assigned_twse"
    assert twse_disposal["state"] == "reported_upcoming"
    assert twse_disposal["official_available_at"] is None
    assert twse_disposal["historical_pit_eligible"] is False

    tpex = by_code[fixture.included_codes[-1]]
    tpex_market = cast(dict[str, object], tpex["market_assignment"])
    tpex_disposal = cast(dict[str, object], tpex["official_disposal"])
    assert tpex_market["state"] == "assigned_tpex"
    assert tpex_disposal["state"] == "reported_active"

    excluded = by_code[fixture.excluded_code]
    assert excluded["cohort_role"] == "excluded"
    assert excluded["exclusion_reason"] == "合成母體明示排除，保留於 declared 分母"
    excluded_market = cast(dict[str, object], excluded["market_assignment"])
    assert excluded_market["state"] == "unknown"
    assert excluded_market["reason_code"] == "no_positive_roster_evidence"

    manifest = state.manifest
    assert manifest["projection_status"] == "complete"
    assert manifest["source_coverage_status"] == "partial"
    assert manifest["scope"] == "current_only"
    assert manifest["historical_pit_eligible"] is False
    assert manifest["official_available_at"] is None
    technical = cast(dict[str, object], manifest["technical_store"])
    assert technical["receipt_status"] == "complete"
    assert technical["declared_count"] == 258
    assert technical["included_count"] == 257
    assert technical["excluded_count"] == 1
    coverage = cast(dict[str, object], manifest["source_coverage"])
    assert cast(dict[str, int], coverage["market_assignment_counts"])["assigned_twse"] == 256
    assert cast(dict[str, int], coverage["market_assignment_counts"])["assigned_tpex"] == 1
    assert cast(dict[str, int], coverage["official_disposal_counts"])["reported_upcoming"] == 1
    assert cast(dict[str, int], coverage["official_disposal_counts"])["reported_active"] == 1
    assert cast(dict[str, int], coverage["official_disposal_counts"])["unknown"] == 256
    assert fixture.writer.cancel() == "already_published"
    assert fixture.original_signatures == tuple(
        (path, _tree_signature(Path(path))) for path, _ in fixture.original_signatures
    )

    script = """
import sys
from app_module.daily_market_technical_official_disposition_bundle_v1 import DailyMarketTechnicalOfficialDispositionBundleReaderV1
state = DailyMarketTechnicalOfficialDispositionBundleReaderV1(sys.argv[1]).read_exact(
    sys.argv[2], expected_manifest_sha256=sys.argv[3]
)
rows = tuple(state.iter_verified_rows())
print(f"{state.reference.row_count}|{rows[0].stock_code}|{rows[-1].stock_code}|{state.reference.source_coverage_status}")
"""
    reopened = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(fixture.bundle_root),
            fixture.reference.bundle_identity_sha256,
            fixture.reference.manifest_sha256,
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert reopened.stdout.strip() == "258|1000|9999|partial"


def test_selected_rows_uses_locator_index_for_descending_cross_shard_page(
    bundle_fixture: _BundleFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = bundle_fixture
    state = DailyMarketTechnicalOfficialDispositionBundleReaderV1(fixture.bundle_root).read_exact(
        fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=fixture.reference.manifest_sha256,
    )
    import app_module.daily_market_technical_official_disposition_bundle_v1 as bundle_module

    decoded_codes: list[str] = []
    original_decoder = bundle_module._row_from_payload

    def counted_decoder(payload: Any) -> Any:
        decoded = original_decoder(payload)
        decoded_codes.append(decoded.stock_code)
        return decoded

    monkeypatch.setattr(bundle_module, "_row_from_payload", counted_decoder)
    codes = (fixture.excluded_code, *reversed(fixture.included_codes[-19:]))
    selected = state.read_selected_rows(codes)

    assert type(selected) is DailyMarketTechnicalOfficialDispositionBundleSelectedRowsV1
    assert selected.requested_stock_codes == codes
    assert tuple(row.stock_code for row in selected.rows) == codes
    assert decoded_codes == list(codes)
    payload = selected.to_dict()
    assert payload["bundle_identity_sha256"] == fixture.reference.bundle_identity_sha256
    assert payload["manifest_sha256"] == fixture.reference.manifest_sha256
    assert len(cast(list[object], payload["rows"])) == len(codes)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError, match="selected_rows_shape_invalid"):
        replace(selected, requested_stock_codes=tuple(reversed(codes)))


def test_selected_rows_empty_request_rechecks_manifest_without_decoding_rows(
    bundle_fixture: _BundleFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = bundle_fixture
    state = DailyMarketTechnicalOfficialDispositionBundleReaderV1(fixture.bundle_root).read_exact(
        fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=fixture.reference.manifest_sha256,
    )
    import app_module.daily_market_technical_official_disposition_bundle_v1 as bundle_module

    def unexpected_decode(_payload: Any) -> Any:
        raise AssertionError("empty selection must not decode a row")

    monkeypatch.setattr(bundle_module, "_row_from_payload", unexpected_decode)
    selected = state.read_selected_rows(())
    assert selected.requested_stock_codes == ()
    assert selected.rows == ()
    assert selected.rows_identity_sha256 == hashlib.sha256(b"[]").hexdigest()


@pytest.mark.parametrize(
    ("codes", "expected_code"),
    (
        ("1000", "selected_stock_codes_invalid"),
        (b"1000", "selected_stock_codes_invalid"),
        (("1000", "1000"), "selected_stock_code_duplicate"),
        (("bad/code",), "selected_stock_code_invalid"),
        (("8888",), "selected_stock_code_not_in_bundle"),
    ),
)
def test_selected_rows_rejects_invalid_or_nonmember_requests(
    bundle_fixture: _BundleFixture,
    codes: object,
    expected_code: str,
) -> None:
    fixture = bundle_fixture
    state = DailyMarketTechnicalOfficialDispositionBundleReaderV1(fixture.bundle_root).read_exact(
        fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=fixture.reference.manifest_sha256,
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError, match=expected_code):
        state.read_selected_rows(cast(Any, codes))


def test_selected_rows_rejects_more_than_256_even_if_sequence_length_lies(
    bundle_fixture: _BundleFixture,
) -> None:
    fixture = bundle_fixture
    state = DailyMarketTechnicalOfficialDispositionBundleReaderV1(fixture.bundle_root).read_exact(
        fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=fixture.reference.manifest_sha256,
    )

    class LyingList(list[str]):
        def __len__(self) -> int:
            return 1

    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError, match="selected_stock_codes_limit"):
        state.read_selected_rows(LyingList(f"{1000 + index:04d}" for index in range(257)))


def test_selected_rows_strict_cancel_and_state_replace_seals(
    bundle_fixture: _BundleFixture,
) -> None:
    fixture = bundle_fixture
    state = DailyMarketTechnicalOfficialDispositionBundleReaderV1(fixture.bundle_root).read_exact(
        fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=fixture.reference.manifest_sha256,
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleCancelled):
        state.read_selected_rows((fixture.included_codes[0],), cancel_callback=lambda: True)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError, match="cancel_callback_invalid"):
        state.read_selected_rows((fixture.included_codes[0],), cancel_callback=cast(Any, lambda: 1))

    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError, match="verified_storage_reference_mismatch"):
        replace(state, reference=replace(state.reference, output_root=str(fixture.qa_root)))
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError, match="verified_state_manifest_digest_mismatch"):
        replace(state, manifest_json=state.manifest_json + " ")
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError, match="verified_state_not_reader_issued"):
        replace(state, _storage=cast(Any, object()))
    with pytest.raises(AttributeError, match="immutable"):
        state._storage.row_locators = ()  # type: ignore[misc]


def test_selected_rows_cancels_between_real_shards_without_partial_result(
    bundle_fixture: _BundleFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = bundle_fixture
    state = DailyMarketTechnicalOfficialDispositionBundleReaderV1(fixture.bundle_root).read_exact(
        fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=fixture.reference.manifest_sha256,
    )
    read_shards: list[int] = []
    original_reader = state._read_selected_shard

    def cancel_after_first_shard(
        _state: DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
        shard_index: int,
        reference: object,
        cancel_callback: Callable[[], bool] | None,
    ) -> bytes:
        raw = original_reader(shard_index, reference, cancel_callback)
        read_shards.append(shard_index)
        return raw

    monkeypatch.setattr(
        DailyMarketTechnicalOfficialDispositionBundleVerifiedStateV1,
        "_read_selected_shard",
        cancel_after_first_shard,
    )
    def cancel_after_hit_shard() -> bool:
        return bool(read_shards)

    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleCancelled):
        state.read_selected_rows(
            (fixture.excluded_code, fixture.included_codes[0]),
            cancel_callback=cancel_after_hit_shard,
        )
    assert len(read_shards) == 1


@pytest.mark.parametrize("empty_request", (False, True))
def test_selected_rows_final_result_gate_polls_cancellation(
    bundle_fixture: _BundleFixture,
    monkeypatch: pytest.MonkeyPatch,
    empty_request: bool,
) -> None:
    fixture = bundle_fixture
    state = DailyMarketTechnicalOfficialDispositionBundleReaderV1(fixture.bundle_root).read_exact(
        fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=fixture.reference.manifest_sha256,
    )
    import app_module.daily_market_technical_official_disposition_bundle_v1 as bundle_module

    cancelled = False
    original_result_builder = bundle_module._selected_rows_result

    def build_then_cancel(*args: Any, **kwargs: Any) -> Any:
        nonlocal cancelled
        result = original_result_builder(*args, **kwargs)
        cancelled = True
        return result

    monkeypatch.setattr(bundle_module, "_selected_rows_result", build_then_cancel)
    requested = () if empty_request else (fixture.included_codes[0],)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleCancelled):
        state.read_selected_rows(requested, cancel_callback=lambda: cancelled)


@pytest.mark.parametrize(
    ("final_callback_mode", "expected_code"),
    (
        ("cancel", "cancelled_before_publish"),
        ("invalid", "cancel_callback_invalid"),
        ("failed", "cancel_callback_failed"),
    ),
)
def test_exact_read_storage_build_final_gate_preserves_callback_codes(
    bundle_fixture: _BundleFixture,
    monkeypatch: pytest.MonkeyPatch,
    final_callback_mode: str,
    expected_code: str,
) -> None:
    fixture = bundle_fixture
    import app_module.daily_market_technical_official_disposition_bundle_v1 as bundle_module

    state: dict[str, str] = {"mode": "normal"}
    original_init = bundle_module._VerifiedBundleStorageV1.__init__

    def build_then_change_callback(self: Any, **kwargs: Any) -> None:
        original_init(self, **kwargs)
        state["mode"] = final_callback_mode

    def callback() -> object:
        mode = state["mode"]
        if mode == "cancel":
            return True
        if mode == "invalid":
            return 1
        if mode == "failed":
            raise RuntimeError("synthetic callback failure")
        return False

    monkeypatch.setattr(bundle_module._VerifiedBundleStorageV1, "__init__", build_then_change_callback)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError) as error:
        DailyMarketTechnicalOfficialDispositionBundleReaderV1(fixture.bundle_root).read_exact(
            fixture.reference.bundle_identity_sha256,
            expected_manifest_sha256=fixture.reference.manifest_sha256,
            cancel_callback=cast(Any, callback),
        )
    assert error.value.code == expected_code


def test_selected_rows_revalidates_manifest_and_only_selected_shards(
    bundle_fixture: _BundleFixture,
) -> None:
    fixture = bundle_fixture
    valid_attempt = fixture.qa_root / "selected-manifest-state"
    valid_root = valid_attempt / "bundle"
    shutil.copytree(fixture.bundle_root, valid_root)
    state = DailyMarketTechnicalOfficialDispositionBundleReaderV1(valid_root).read_exact(
        fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=fixture.reference.manifest_sha256,
    )
    manifest_path = valid_root / fixture.reference.manifest_relative_path
    manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError):
        state.read_selected_rows((fixture.included_codes[0],))

    shard_attempt = fixture.qa_root / "selected-shard-tamper"
    shard_root = shard_attempt / "bundle"
    shutil.copytree(fixture.bundle_root, shard_root)
    shard_state = DailyMarketTechnicalOfficialDispositionBundleReaderV1(shard_root).read_exact(
        fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=fixture.reference.manifest_sha256,
    )
    first_shard = cast(dict[str, object], cast(list[object], shard_state.manifest["row_shards"])[0])
    shard_path = shard_root / cast(str, first_shard["relative_path"])
    raw = bytearray(shard_path.read_bytes())
    raw[-2] = ord(" ") if raw[-2] != ord(" ") else ord("\t")
    shard_path.write_bytes(raw)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError, match="selected_shard_bytes_sha_mismatch"):
        shard_state.read_selected_rows((fixture.included_codes[0],))

    other_shard_attempt = fixture.qa_root / "unselected-shard-drift"
    other_shard_root = other_shard_attempt / "bundle"
    shutil.copytree(fixture.bundle_root, other_shard_root)
    other_shard_state = DailyMarketTechnicalOfficialDispositionBundleReaderV1(other_shard_root).read_exact(
        fixture.reference.bundle_identity_sha256,
        expected_manifest_sha256=fixture.reference.manifest_sha256,
    )
    shard_refs = cast(list[object], other_shard_state.manifest["row_shards"])
    other_shard = cast(dict[str, object], shard_refs[1])
    other_path = other_shard_root / cast(str, other_shard["relative_path"])
    other_raw = bytearray(other_path.read_bytes())
    other_raw[-2] = ord(" ") if other_raw[-2] != ord(" ") else ord("\t")
    other_path.write_bytes(other_raw)
    selected = other_shard_state.read_selected_rows((fixture.included_codes[0],))
    assert tuple(row.stock_code for row in selected.rows) == (fixture.included_codes[0],)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError, match="shard_bytes_sha_mismatch"):
        DailyMarketTechnicalOfficialDispositionBundleReaderV1(other_shard_root).read_exact(
            fixture.reference.bundle_identity_sha256,
            expected_manifest_sha256=fixture.reference.manifest_sha256,
        )


def test_selected_rows_fresh_process_reads_exact_cross_shard_codes(
    bundle_fixture: _BundleFixture,
) -> None:
    fixture = bundle_fixture
    codes = (fixture.excluded_code, *reversed(fixture.included_codes[-19:]))
    script = r"""
import json
import sys
from app_module.daily_market_technical_official_disposition_bundle_v1 import DailyMarketTechnicalOfficialDispositionBundleReaderV1
state = DailyMarketTechnicalOfficialDispositionBundleReaderV1(sys.argv[1]).read_exact(
    sys.argv[2], expected_manifest_sha256=sys.argv[3]
)
selected = state.read_selected_rows(tuple(json.loads(sys.argv[4])))
print(json.dumps({
    "codes": list(selected.requested_stock_codes),
    "bundle": selected.bundle_identity_sha256,
    "manifest": selected.manifest_sha256,
    "identity": selected.materialization_identity_sha256,
}, sort_keys=True))
"""
    reopened = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(fixture.bundle_root),
            fixture.reference.bundle_identity_sha256,
            fixture.reference.manifest_sha256,
            json.dumps(list(codes)),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    payload = json.loads(reopened.stdout.strip())
    assert payload["codes"] == list(codes)
    assert payload["bundle"] == fixture.reference.bundle_identity_sha256
    assert payload["manifest"] == fixture.reference.manifest_sha256
    assert len(payload["identity"]) == 64


def test_later_market_capture_is_rejected_without_changing_technical_cutoff(
    bundle_fixture: _BundleFixture,
) -> None:
    fixture = bundle_fixture
    later_publication = _PUBLISHED_AT + timedelta(minutes=10)
    late_root = fixture.qa_root / "market-capture-later-than-technical-cutoff"
    _FrozenDateTime.fixed_now = later_publication
    late_monkeypatch = pytest.MonkeyPatch()
    try:
        late_monkeypatch.setattr(capture_module, "datetime", _FrozenDateTime)
        late_pointer = _capture_market_sources(late_root, fixture.included_codes[:-1], fixture.included_codes[-1])
    finally:
        late_monkeypatch.undo()
    late_cutoff = _CUTOFF + timedelta(minutes=10)
    late_pin = CurrentMarketAssignmentReader.from_pointer(late_pointer, cutoff_at=late_cutoff).source_pin
    output_root = fixture.scope.root / "rejected-later-source-bundle"
    writer = DailyMarketTechnicalOfficialDispositionBundleWriterV1(
        output_root,
        research_scope=fixture.scope,
    )
    technical_ids = _technical_ids(fixture)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError) as error:
        writer.create_from_pins(
            store_output_root=fixture.store_root,
            generation_identity_sha256=technical_ids[0],
            plan_identity_sha256=technical_ids[1],
            expected_plan_sha256=technical_ids[3],
            receipt_identity_sha256=technical_ids[2],
            expected_receipt_sha256=technical_ids[4],
            market_assignment_source_pin=late_pin,
            official_disposal_source_pin=fixture.disposal_pin,
        )
    assert error.value.code == "market_assignment_cutoff_mismatch"
    assert not output_root.exists()
    assert fixture.reference.source_coverage_status == "partial"


def test_reader_rejects_tampered_shard_bytes_and_resigned_false_projection(
    bundle_fixture: _BundleFixture,
) -> None:
    fixture = bundle_fixture
    byte_tamper_root = fixture.qa_root / "tampered-shard-bytes-copy"
    shutil.copytree(to_internal_io_path(fixture.bundle_root), to_internal_io_path(byte_tamper_root))
    byte_manifest = byte_tamper_root / fixture.reference.manifest_relative_path
    byte_payload = json.loads(byte_manifest.read_text(encoding="utf-8"))
    byte_ref = cast(dict[str, object], cast(list[object], byte_payload["row_shards"])[0])
    byte_object = byte_tamper_root / str(byte_ref["relative_path"])
    original = byte_object.read_bytes()
    byte_object.write_bytes(original[:-1] + (b"X" if original[-1:] != b"X" else b"Y"))
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError) as error:
        DailyMarketTechnicalOfficialDispositionBundleReaderV1(byte_tamper_root).read_exact(
            fixture.reference.bundle_identity_sha256,
            expected_manifest_sha256=fixture.reference.manifest_sha256,
        )
    assert error.value.code == "shard_bytes_sha_mismatch"

    semantic_root = fixture.qa_root / "tampered-resigned-projection-copy"
    shutil.copytree(to_internal_io_path(fixture.bundle_root), to_internal_io_path(semantic_root))
    manifest_path = semantic_root / fixture.reference.manifest_relative_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    shard_ref = cast(dict[str, object], cast(list[object], manifest["row_shards"])[0])
    shard_path = semantic_root / str(shard_ref["relative_path"])
    lines = shard_path.read_bytes().splitlines()
    first = json.loads(lines[0].decode("utf-8"))
    cast(dict[str, object], first["market_assignment"])["reason_code"] = "合成惡意重簽投影"
    lines[0] = _canonical_json_for_test(first).encode("utf-8")
    changed_shard = b"\n".join(lines) + b"\n"
    changed_sha = hashlib.sha256(changed_shard).hexdigest()
    changed_object_relative = f"objects/{changed_sha}.jsonl"
    changed_object = semantic_root / changed_object_relative
    changed_object.write_bytes(changed_shard)
    shard_ref.update({
        "relative_path": changed_object_relative,
        "sha256": changed_sha,
        "size_bytes": len(changed_shard),
    })
    manifest.pop("bundle_identity_sha256")
    manifest["bundle_identity_sha256"] = _canonical_sha_for_test(manifest)
    changed_identity = cast(str, manifest["bundle_identity_sha256"])
    manifest_raw = _canonical_json_for_test(manifest).encode("utf-8")
    manifest_path = semantic_root / "manifests" / f"{changed_identity}.json"
    manifest_path.write_bytes(manifest_raw)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError) as semantic_error:
        DailyMarketTechnicalOfficialDispositionBundleReaderV1(semantic_root).read_exact(
            changed_identity,
            expected_manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(),
        )
    assert semantic_error.value.code == "row_exact_source_projection_mismatch"


def test_cancel_gate_is_reproducible_and_never_publishes_complete_manifest(
    bundle_fixture: _BundleFixture,
) -> None:
    fixture = bundle_fixture
    cancelled_root = fixture.scope.root / "cancelled-publication-bundle"
    writer = DailyMarketTechnicalOfficialDispositionBundleWriterV1(
        cancelled_root,
        research_scope=fixture.scope,
    )
    technical = DailyMarketTechnicalUniverseV4StoreReader(fixture.store_root).read_exact(
        _technical_ids(fixture)[0],
        _technical_ids(fixture)[1],
        _technical_ids(fixture)[2],
        expected_receipt_sha256=_technical_ids(fixture)[4],
        expected_plan_sha256=_technical_ids(fixture)[3],
    )
    entered_final_check = threading.Event()
    release_final_check = threading.Event()
    errors: list[BaseException] = []

    def cancel_callback() -> bool:
        attempts = cancelled_root / ".attempts"
        if attempts.exists() and any(attempts.glob("attempt-*/manifest.json.tmp")):
            entered_final_check.set()
            if not release_final_check.wait(timeout=60):
                raise TimeoutError("final publication barrier timeout")
        return False

    def run() -> None:
        try:
            writer.create_from_pins(
                store_output_root=fixture.store_root,
                generation_identity_sha256=technical.plan.generation_identity_sha256,
                plan_identity_sha256=technical.plan.identity_sha256,
                expected_plan_sha256=_technical_ids(fixture)[3],
                receipt_identity_sha256=technical.receipt.identity_sha256,
                expected_receipt_sha256=_technical_ids(fixture)[4],
                market_assignment_source_pin=fixture.market_pin,
                official_disposal_source_pin=fixture.disposal_pin,
                cancel_callback=cancel_callback,
            )
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=run, name="f17-bundle-cancel-test", daemon=True)
    thread.start()
    try:
        assert entered_final_check.wait(timeout=180)
        assert writer.cancel() == "cancel_requested"
    finally:
        release_final_check.set()
        thread.join(timeout=180)
    assert not thread.is_alive()
    assert len(errors) == 1
    assert isinstance(errors[0], DailyMarketTechnicalOfficialDispositionBundleCancelled)
    manifests = cancelled_root / "manifests"
    assert not manifests.exists() or not tuple(manifests.glob("*.json"))
    attempts = cancelled_root / ".attempts"
    assert attempts.exists()
    assert tuple(attempts.glob("attempt-*/manifest.json.tmp"))

    early_root = fixture.scope.root / "cancelled-before-preflight"
    early_writer = DailyMarketTechnicalOfficialDispositionBundleWriterV1(
        early_root,
        research_scope=fixture.scope,
    )
    assert early_writer.cancel() == "cancel_requested"
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleCancelled):
        early_writer.create_from_pins(
            store_output_root=fixture.store_root,
            generation_identity_sha256=_technical_ids(fixture)[0],
            plan_identity_sha256=_technical_ids(fixture)[1],
            expected_plan_sha256=_technical_ids(fixture)[3],
            receipt_identity_sha256=_technical_ids(fixture)[2],
            expected_receipt_sha256=_technical_ids(fixture)[4],
            market_assignment_source_pin=fixture.market_pin,
            official_disposal_source_pin=fixture.disposal_pin,
        )
    assert not early_root.exists()


@pytest.mark.parametrize("source_index", range(5))
def test_writer_rejects_output_inside_each_exact_source_root(
    bundle_fixture: _BundleFixture,
    source_index: int,
) -> None:
    fixture = bundle_fixture
    assert len(fixture.source_roots) == 5
    source_root = fixture.source_roots[source_index]
    scope = ResearchCaptureWriteScope(source_root, fixture.database)
    output_root = scope.root / "forbidden-f17-bundle"
    writer = DailyMarketTechnicalOfficialDispositionBundleWriterV1(output_root, research_scope=scope)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError) as error:
        _create_from_fixture(writer, fixture)
    assert error.value.code == "bundle_root_overlaps_source"
    assert not output_root.exists()


def test_research_scope_rejects_database_parent_as_output_root(
    bundle_fixture: _BundleFixture,
) -> None:
    fixture = bundle_fixture
    with pytest.raises(RuleSampleCaptureError) as error:
        ResearchCaptureWriteScope(fixture.database.parent, fixture.database)
    assert error.value.code == "source_output_overlap"


@pytest.mark.parametrize("wrong_identity", ("plan", "receipt"))
def test_writer_rejects_wrong_exact_plan_or_receipt_without_publication(
    bundle_fixture: _BundleFixture,
    wrong_identity: str,
) -> None:
    fixture = bundle_fixture
    output_root = fixture.scope.root / f"wrong-exact-{wrong_identity}"
    writer = DailyMarketTechnicalOfficialDispositionBundleWriterV1(output_root, research_scope=fixture.scope)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError) as error:
        if wrong_identity == "plan":
            _create_from_fixture(writer, fixture, plan_identity_sha256="0" * 64)
        else:
            _create_from_fixture(writer, fixture, receipt_identity_sha256="0" * 64)
    assert error.value.code == "technical_store_exact_read_failed"
    assert not output_root.exists()


def test_writer_rejects_wrong_source_pin_type_and_cutoff(
    bundle_fixture: _BundleFixture,
) -> None:
    fixture = bundle_fixture
    wrong_type_root = fixture.scope.root / "wrong-source-pin-type"
    wrong_type_writer = DailyMarketTechnicalOfficialDispositionBundleWriterV1(
        wrong_type_root,
        research_scope=fixture.scope,
    )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError) as type_error:
        _create_from_fixture(
            wrong_type_writer,
            fixture,
            disposal_pin=cast(CurrentOfficialDisposalSourcePinV1, fixture.market_pin),
        )
    assert type_error.value.code == "official_disposal_typed_pin_required"
    assert not wrong_type_root.exists()

    wrong_clock_root = fixture.scope.root / "wrong-source-pin-cutoff"
    wrong_clock_writer = DailyMarketTechnicalOfficialDispositionBundleWriterV1(
        wrong_clock_root,
        research_scope=fixture.scope,
    )
    wrong_pin = replace(fixture.market_pin, cutoff_at=(_CUTOFF + timedelta(minutes=1)).isoformat())
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError) as cutoff_error:
        _create_from_fixture(wrong_clock_writer, fixture, market_pin=wrong_pin)
    assert cutoff_error.value.code == "market_assignment_cutoff_mismatch"
    assert not wrong_clock_root.exists()


def test_cancel_callback_exception_does_not_publish_or_complete(
    bundle_fixture: _BundleFixture,
) -> None:
    fixture = bundle_fixture
    output_root = fixture.scope.root / "cancel-callback-exception"
    writer = DailyMarketTechnicalOfficialDispositionBundleWriterV1(output_root, research_scope=fixture.scope)

    def fail_callback() -> bool:
        raise RuntimeError("synthetic callback failure")

    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError) as error:
        _create_from_fixture(writer, fixture, cancel_callback=fail_callback)
    assert error.value.code == "cancel_callback_failed"
    assert not output_root.exists()


@pytest.mark.parametrize(
    ("boundary", "expected_code"),
    (
        ("shard_count", "shard_reference_list_invalid"),
        ("shard_rows", "shard_row_count_invalid"),
        ("shard_bytes", "shard_size_invalid"),
        ("declared_count", "manifest_row_count_invalid"),
        ("row_count_mismatch", "manifest_row_count_mismatch"),
    ),
)
def test_reader_rejects_resigned_count_and_shard_boundary_violations(
    bundle_fixture: _BundleFixture,
    boundary: str,
    expected_code: str,
) -> None:
    fixture = bundle_fixture
    root = _copy_bundle(fixture, f"boundary-{boundary}")
    manifest_path = root / fixture.reference.manifest_relative_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    references = cast(list[object], manifest["row_shards"])
    if boundary == "shard_count":
        first = cast(dict[str, object], references[0])
        references.extend(dict(first) for _ in range(DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_SHARDS + 1 - len(references)))
    elif boundary == "shard_rows":
        cast(dict[str, object], references[0])["row_count"] = DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_ROWS_PER_SHARD + 1
    elif boundary == "shard_bytes":
        reference = cast(dict[str, object], references[0])
        oversized = b"x" * (DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_SHARD_BYTES + 1)
        oversized_sha = hashlib.sha256(oversized).hexdigest()
        oversized_path = root / "objects" / f"{oversized_sha}.jsonl"
        oversized_path.write_bytes(oversized)
        reference.update({
            "relative_path": f"objects/{oversized_sha}.jsonl",
            "sha256": oversized_sha,
            "size_bytes": len(oversized),
        })
        assert oversized_path.stat().st_size > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_SHARD_BYTES
    elif boundary == "declared_count":
        manifest["row_count"] = DAILY_MARKET_TECHNICAL_UNIVERSE_V4_MAX_DECLARED_STOCKS + 1
    else:
        manifest["row_count"] = fixture.reference.row_count - 1

    identity, manifest_sha = _resign_manifest(root, manifest)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError) as error:
        DailyMarketTechnicalOfficialDispositionBundleReaderV1(root).read_exact(
            identity,
            expected_manifest_sha256=manifest_sha,
        )
    assert error.value.code == expected_code


def test_reader_rejects_actual_overlong_row_and_oversized_manifest(
    bundle_fixture: _BundleFixture,
) -> None:
    fixture = bundle_fixture
    row_root = _copy_bundle(fixture, "boundary-row-bytes")
    row_manifest_path = row_root / fixture.reference.manifest_relative_path
    row_manifest = json.loads(row_manifest_path.read_text(encoding="utf-8"))
    row_refs = cast(list[object], row_manifest["row_shards"])
    row_ref = cast(dict[str, object], row_refs[0])
    old_object = row_root / cast(str, row_ref["relative_path"])
    lines = old_object.read_bytes().splitlines()
    first_row = json.loads(lines[0].decode("utf-8"))
    cast(dict[str, object], first_row["market_assignment"])["reason_code"] = "x" * (
        DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_ROW_BYTES + 64
    )
    lines[0] = _canonical_json_for_test(first_row).encode("utf-8")
    assert len(lines[0]) > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_ROW_BYTES
    changed_shard = b"\n".join(lines) + b"\n"
    assert len(changed_shard) <= DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_SHARD_BYTES
    changed_sha = hashlib.sha256(changed_shard).hexdigest()
    changed_path = row_root / "objects" / f"{changed_sha}.jsonl"
    changed_path.write_bytes(changed_shard)
    row_ref.update({
        "relative_path": f"objects/{changed_sha}.jsonl",
        "sha256": changed_sha,
        "size_bytes": len(changed_shard),
    })
    row_identity, row_manifest_sha = _resign_manifest(row_root, row_manifest)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError) as row_error:
        DailyMarketTechnicalOfficialDispositionBundleReaderV1(row_root).read_exact(
            row_identity,
            expected_manifest_sha256=row_manifest_sha,
        )
    assert row_error.value.code == "row_line_bound_or_terminator_invalid"

    manifest_root = _copy_bundle(fixture, "boundary-manifest-bytes")
    manifest_path = manifest_root / fixture.reference.manifest_relative_path
    oversized_manifest = b" " * (DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_MANIFEST_BYTES + 1)
    manifest_path.write_bytes(oversized_manifest)
    assert manifest_path.stat().st_size > DAILY_MARKET_TECHNICAL_OFFICIAL_DISPOSITION_BUNDLE_MAX_MANIFEST_BYTES
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError) as manifest_error:
        DailyMarketTechnicalOfficialDispositionBundleReaderV1(manifest_root).read_exact(
            fixture.reference.bundle_identity_sha256,
            expected_manifest_sha256=hashlib.sha256(oversized_manifest).hexdigest(),
        )
    assert manifest_error.value.code == "manifest_missing_or_invalid"


def test_reader_rejects_hardlinked_shard_object(
    bundle_fixture: _BundleFixture,
) -> None:
    fixture = bundle_fixture
    hardlink_root = _copy_bundle(fixture, "rejected-hardlink")
    hardlink_manifest = json.loads(
        (hardlink_root / fixture.reference.manifest_relative_path).read_text(encoding="utf-8")
    )
    hardlink_ref = cast(dict[str, object], cast(list[object], hardlink_manifest["row_shards"])[0])
    hardlink_object = hardlink_root / cast(str, hardlink_ref["relative_path"])
    hardlink_probe = hardlink_root / "hardlink-probe.jsonl"
    try:
        os.link(to_internal_io_path(hardlink_object), to_internal_io_path(hardlink_probe))
    except OSError as error:
        pytest.skip(f"目前平台無法建立合成 hardlink：{type(error).__name__}")
    assert hardlink_object.stat().st_nlink == 2
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError) as hardlink_error:
        DailyMarketTechnicalOfficialDispositionBundleReaderV1(hardlink_root).read_exact(
            fixture.reference.bundle_identity_sha256,
            expected_manifest_sha256=fixture.reference.manifest_sha256,
        )
    assert hardlink_error.value.code == "shard_missing_or_invalid"


def test_reader_rejects_reparse_shard_object_when_platform_supports_it(
    bundle_fixture: _BundleFixture,
) -> None:
    fixture = bundle_fixture
    reparse_root = _copy_bundle(fixture, "rejected-reparse")
    reparse_manifest = json.loads(
        (reparse_root / fixture.reference.manifest_relative_path).read_text(encoding="utf-8")
    )
    reparse_ref = cast(dict[str, object], cast(list[object], reparse_manifest["row_shards"])[0])
    reparse_object = reparse_root / cast(str, reparse_ref["relative_path"])
    reparse_target = fixture.bundle_root / cast(str, reparse_ref["relative_path"])
    reparse_object.unlink()
    try:
        os.symlink(
            to_internal_io_path(reparse_target),
            to_internal_io_path(reparse_object),
            target_is_directory=False,
        )
    except OSError as error:
        pytest.skip(
            "目前執行環境無法建立合成 reparse link："
            f"{type(error).__name__}，winerror={getattr(error, 'winerror', None)}，{error}"
        )
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError) as reparse_error:
        DailyMarketTechnicalOfficialDispositionBundleReaderV1(reparse_root).read_exact(
            fixture.reference.bundle_identity_sha256,
            expected_manifest_sha256=fixture.reference.manifest_sha256,
        )
    assert reparse_error.value.code == "path_component_link_or_reparse"


def test_writer_does_not_replace_existing_conflicting_manifest(
    bundle_fixture: _BundleFixture,
) -> None:
    fixture = bundle_fixture
    output_root = fixture.scope.root / "no-replace-manifest-collision"
    manifest_directory = output_root / "manifests"
    manifest_directory.mkdir(parents=True)
    conflicting_manifest = manifest_directory / f"{fixture.reference.bundle_identity_sha256}.json"
    original_bytes = b"pre-existing immutable collision\n"
    conflicting_manifest.write_bytes(original_bytes)
    writer = DailyMarketTechnicalOfficialDispositionBundleWriterV1(output_root, research_scope=fixture.scope)
    with pytest.raises(DailyMarketTechnicalOfficialDispositionBundleError) as error:
        _create_from_fixture(writer, fixture)
    assert error.value.code == "identity_collision_or_existing_manifest_conflict"
    assert conflicting_manifest.read_bytes() == original_bytes


def _technical_ids(fixture: _BundleFixture) -> tuple[str, str, str, str, str]:
    return (
        fixture.generation_identity_sha256,
        fixture.plan_identity_sha256,
        fixture.receipt_identity_sha256,
        fixture.expected_plan_sha256,
        fixture.expected_receipt_sha256,
    )


def _create_from_fixture(
    writer: DailyMarketTechnicalOfficialDispositionBundleWriterV1,
    fixture: _BundleFixture,
    *,
    generation_identity_sha256: str | None = None,
    plan_identity_sha256: str | None = None,
    expected_plan_sha256: str | None = None,
    receipt_identity_sha256: str | None = None,
    expected_receipt_sha256: str | None = None,
    market_pin: CurrentMarketAssignmentSourcePinV1 | None = None,
    disposal_pin: CurrentOfficialDisposalSourcePinV1 | None = None,
    cancel_callback: Callable[[], bool] | None = None,
) -> DailyMarketTechnicalOfficialDispositionBundleReferenceV1:
    return writer.create_from_pins(
        store_output_root=fixture.store_root,
        generation_identity_sha256=generation_identity_sha256 or fixture.generation_identity_sha256,
        plan_identity_sha256=plan_identity_sha256 or fixture.plan_identity_sha256,
        expected_plan_sha256=expected_plan_sha256 or fixture.expected_plan_sha256,
        receipt_identity_sha256=receipt_identity_sha256 or fixture.receipt_identity_sha256,
        expected_receipt_sha256=expected_receipt_sha256 or fixture.expected_receipt_sha256,
        market_assignment_source_pin=market_pin or fixture.market_pin,
        official_disposal_source_pin=disposal_pin or fixture.disposal_pin,
        cancel_callback=cancel_callback,
    )


def _copy_bundle(fixture: _BundleFixture, suffix: str) -> Path:
    target = fixture.qa_root / f"bundle-copy-{suffix}"
    shutil.copytree(to_internal_io_path(fixture.bundle_root), to_internal_io_path(target))
    return target


def _resign_manifest(root: Path, manifest: dict[str, object]) -> tuple[str, str]:
    manifest.pop("bundle_identity_sha256", None)
    identity = _canonical_sha_for_test(manifest)
    manifest["bundle_identity_sha256"] = identity
    raw = _canonical_json_for_test(manifest).encode("utf-8")
    path = root / "manifests" / f"{identity}.json"
    path.write_bytes(raw)
    return identity, hashlib.sha256(raw).hexdigest()


def _write_prices(database: Path, stock_codes: tuple[str, ...]) -> None:
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(to_internal_io_path(database))
    start_date = _DECISION_DATE - timedelta(days=39)
    try:
        with connection:
            connection.execute(
                "CREATE TABLE daily_prices ("
                "日期 TEXT, 證券代號 TEXT, 開盤價 TEXT, 最高價 TEXT, 最低價 TEXT, "
                "收盤價 TEXT, 成交股數 INTEGER)"
            )
            rows: list[tuple[str, str, str, str, str, str, int]] = []
            for stock_code in stock_codes:
                for offset in range(40):
                    closing = 100 + offset
                    observed_date = start_date + timedelta(days=offset)
                    rows.append((
                        observed_date.isoformat(),
                        stock_code,
                        str(closing),
                        str(closing + 1),
                        str(closing - 1),
                        str(closing),
                        1000 + offset,
                    ))
            connection.executemany("INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)", rows)
    finally:
        connection.close()


def _capture_market_sources(
    output_root: Path,
    twse_codes: tuple[str, ...],
    tpex_code: str,
) -> Path:
    sources = (
        SourceSpec(
            "twse.current_roster", _TWSE_ROSTER_URL, "current_roster", "twse",
            "合成 TWSE 現況名錄",
        ),
        SourceSpec(
            "tpex.current_otc_roster", _TPEX_OTC_ROSTER_URL, "current_roster", "tpex",
            "合成 TPEx OTC 現況名錄",
            source_date_aliases=("Date",),
        ),
        SourceSpec(
            "tpex.current_emerging_roster", _TPEX_EMERGING_ROSTER_URL, "current_roster", "emerging",
            "合成 TPEx 興櫃現況名錄",
            source_date_aliases=("Date",),
        ),
    )
    raw_by_url = {
        _TWSE_ROSTER_URL: json.dumps(
            [
                {"出表日期": "20261007", "公司代號": code, "公司名稱": f"合成 TWSE {code}"}
                for code in twse_codes
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8"),
        _TPEX_OTC_ROSTER_URL: json.dumps(
            [{"Date": "20261007", "SecuritiesCompanyCode": tpex_code, "CompanyAbbreviation": "合成 TPEx"}],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8"),
        _TPEX_EMERGING_ROSTER_URL: json.dumps(
            [{"Date": "20261007", "SecuritiesCompanyCode": "9101", "CompanyAbbreviation": "合成興櫃"}],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8"),
    }

    def fetcher(url: str, **_: object) -> tuple[bytes, int, str, str, datetime, dict[str, str]]:
        return raw_by_url[url], 200, "application/json", url, _CAPTURED_AT, {}

    capture_sources(output_dir=output_root, specs=sources, fetcher=fetcher)
    return output_root / "current_market_status_pointer.json"


def _capture_disposal_sources(
    output_root: Path,
    twse_code: str,
    tpex_code: str,
) -> Path:
    sources = (
        SourceSpec(
            "twse.disposition_current", _TWSE_DISPOSAL_URL, "trading_restriction", "twse",
            "合成 TWSE current-only 處置原件",
        ),
        SourceSpec(
            "tpex.disposition_current", _TPEX_DISPOSAL_URL, "trading_restriction", "tpex",
            "合成 TPEx current-only 處置原件",
        ),
    )
    announcement = _roc(_DECISION_DATE)
    twse_raw = json.dumps(
        {
            "title": "公布處置有價證券資訊",
            "fields": _TWSE_DISPOSAL_FIELDS,
            "data": [[
                1,
                announcement,
                twse_code,
                "合成測試公司",
                1,
                "合成測試條件",
                f"{_roc(_DECISION_DATE + timedelta(days=1))}～{_roc(_DECISION_DATE + timedelta(days=10))}",
                "第一次處置",
                "合成處置內容",
                "",
            ]],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    tpex_raw = json.dumps(
        [{
            "CompanyName": "合成 TPEx 公司",
            "Date": announcement,
            "DisposalCondition": "合成處置條件",
            "DispositionPeriod": f"{announcement}~{_roc(_DECISION_DATE + timedelta(days=5))}",
            "DispositionReasons": "合成處置原因",
            "SecuritiesCompanyCode": tpex_code,
        }],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    raw_by_url = {_TWSE_DISPOSAL_URL: twse_raw, _TPEX_DISPOSAL_URL: tpex_raw}

    def fetcher(url: str, **_: object) -> tuple[bytes, int, str, str, datetime, dict[str, str]]:
        return raw_by_url[url], 200, "application/json", url, _CAPTURED_AT, {}

    capture_sources(output_dir=output_root, specs=sources, fetcher=fetcher)
    return output_root / "current_market_status_pointer.json"


def _roc(value: date) -> str:
    return f"{value.year - 1911:03d}/{value.month:02d}/{value.day:02d}"


def _tree_signature(path: Path) -> tuple[tuple[str, int, int, str], ...]:
    io_path = to_internal_io_path(path)
    root_info = os.lstat(io_path)
    assert not _is_test_reparse(root_info)
    if stat.S_ISREG(root_info.st_mode):
        return (_file_signature_io(io_path, path.name),)
    assert stat.S_ISDIR(root_info.st_mode)
    entries: list[tuple[str, int, int, str]] = []
    for directory, directory_names, file_names in os.walk(io_path, followlinks=False):
        for name in tuple(directory_names):
            child_io = os.path.join(directory, name)
            info = os.lstat(child_io)
            assert not _is_test_reparse(info)
            assert stat.S_ISDIR(info.st_mode)
        for name in file_names:
            child_io = os.path.join(directory, name)
            info = os.lstat(child_io)
            assert not _is_test_reparse(info)
            assert stat.S_ISREG(info.st_mode)
            relative = os.path.relpath(child_io, io_path).replace("\\", "/")
            entries.append(_file_signature_io(child_io, relative))
    return tuple(sorted(entries))


def _file_signature_io(io_path: str, relative: str) -> tuple[str, int, int, str]:
    info = os.stat(io_path)
    digest = hashlib.sha256()
    with open(io_path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return relative, info.st_size, info.st_mtime_ns, digest.hexdigest()


def _is_test_reparse(info: os.stat_result) -> bool:
    if stat.S_ISLNK(info.st_mode):
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(info, "st_file_attributes", 0) & reparse_flag)


def _canonical_json_for_test(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _canonical_sha_for_test(value: dict[str, object]) -> str:
    return hashlib.sha256(_canonical_json_for_test(value).encode("utf-8")).hexdigest()
