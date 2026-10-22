from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
from io import BytesIO
import json

import pytest

from data_module.daily_source_snapshot import DailySourceTransportCapture
import data_module.mops_monthly_revenue_history as mops_history
from data_module.mops_monthly_revenue_history import MopsMonthlyRevenueHistoricalCapture
from data_module.opendata_monthly_revenue import (
    OPENAPI_MONTHLY_REVENUE_ENDPOINTS,
    OpenApiMonthlyRevenueCapture,
    prepare_openapi_monthly_revenue_batch,
)
from data_module.monthly_revenue_revision_archive import (
    MonthlyRevenueRawBatchEvidenceV1,
    MonthlyRevenueRevisionArchiveError,
    append_monthly_revenue_batch,
    raw_batch_from_openapi,
    read_monthly_revenue_revision_archive,
    select_monthly_revenue_observation_as_of,
)
import data_module.monthly_revenue_revision_archive as revision_archive


def _batch(
    *,
    market: str = "twse",
    amount: str = "1.250",
    completed_at: datetime = datetime(2026, 10, 21, 7, 15, tzinfo=timezone.utc),
):
    source_row = {
        "資料年月": "11509",
        "公司代號": "2330",
        "公司名稱": "隔離測試公司",
        "營業收入-當月營收": amount,
        "營業收入-上月營收": "10",
        "營業收入-去年當月營收": "8",
        "營業收入-上月比較增減(%)": "",
        "營業收入-去年同月增減(%)": "",
        "累計營業收入-當月累計營收": "20",
        "累計營業收入-去年累計營收": "16",
        "累計營業收入-前期比較增減(%)": "",
        "出表日期": "1151010",
        "備註": "隔離測試",
        "產業別": "測試業",
    }
    payload = json.dumps(
        [source_row], ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    endpoint = OPENAPI_MONTHLY_REVENUE_ENDPOINTS[market]
    capture = OpenApiMonthlyRevenueCapture(
        market=market,
        requested_url=endpoint,
        response_url=endpoint,
        response_status=200,
        content_type_original_text="application/json; charset=utf-8",
        content_encoding_original_text="identity",
        content_length_original_text=str(len(payload)),
        response_body_complete=True,
        eof_observed=True,
        received_body_bytes=len(payload),
        body_observation_ended_at=completed_at,
        body_completed_at=completed_at,
        raw_response_bytes=payload,
    )
    return prepare_openapi_monthly_revenue_batch(
        capture=capture,
        successful_batch_completed_at=completed_at,
    )


def _append(root, batch, *, parent_hash=None, monkeypatch):
    monkeypatch.setattr(
        revision_archive,
        "_utc_now",
        lambda: batch.available_hour.astimezone(timezone.utc),
    )
    return append_monthly_revenue_batch(
        root,
        raw_batch_from_openapi(batch),
        archive_sha256=parent_hash,
        expected_archive_sha256=parent_hash,
    )


def _mops_evidence():
    body = (
        "<!doctype html><html><head><meta charset=\"utf-8\"></head><body>"
        "<h1>上市公司115年9月份月營業收入彙總表</h1>"
        "<p>出表日期：115/10/11</p><p>單位：新臺幣仟元</p>"
        "<table><tr><th>公司代號</th><th>公司名稱</th><th>當月營收</th>"
        "<th>上月營收</th><th>去年當月營收</th><th>上月比較增減(%)</th>"
        "<th>去年同月增減(%)</th><th>當月累計營收</th><th>去年累計營收</th>"
        "<th>前期比較增減(%)</th><th>備註</th></tr>"
        "<tr><td>2330</td><td>隔離測試公司</td><td>1,234</td><td>1,100</td>"
        "<td>900</td><td>12.2</td><td>37.1</td><td>11,000</td>"
        "<td>8,000</td><td>20</td><td>測試資料</td></tr></table></body></html>"
    ).encode("utf-8")
    captured_at = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    url = mops_history._official_history_url("twse", "2026-09")
    transport = DailySourceTransportCapture(
        raw_response_bytes=body,
        official_source_url=url,
        response_status=200,
        content_type="text/html; charset=utf-8",
        declared_decoding_encoding="utf-8",
        decoding_basis="http_content_type_charset",
        body_completed_at=captured_at,
        transport_sha256=hashlib.sha256(body).hexdigest(),
        response_body_complete=True,
        received_body_bytes=len(body),
        content_length_original_text=str(len(body)),
        body_completion_evidence_ref="eof:isolated-archive-test",
        response_url=url,
        content_encoding_original_text="identity",
        eof_observed=True,
        body_observation_ended_at=captured_at,
    )
    capture = MopsMonthlyRevenueHistoricalCapture(
        market="twse",
        period="2026-09",
        requested_url=url,
        response_url=url,
        request_started_at=captured_at,
        transport_capture=transport,
    )
    return capture.to_monthly_revenue_raw_batch_evidence()


class _ArchiveSocket:
    def settimeout(self, _seconds):
        pass


class _ArchiveReader:
    def __init__(self, body):
        self._body = body
        self.fp = self
        self.raw = self
        self._sock = _ArchiveSocket()

    def read1(self, size=-1):
        return self._body.read1(size)


class _ArchiveResponse:
    def __init__(self, url, body, content_type):
        self._url = url
        self.status = 200
        self.code = 200
        self.headers = {
            "Content-Type": content_type,
            "Content-Encoding": "identity",
            "Content-Length": str(len(body)),
        }
        self._body = BytesIO(body)
        self.fp = _ArchiveReader(self._body)

    def geturl(self):
        return self._url

    def read1(self, size=-1):
        return self._body.read1(size)

    def close(self):
        pass


def _redirect_mops_evidence(monkeypatch):
    popup_url = "https://mopsov.twse.com.tw/mops/web/t21sc04_ifrs"
    static_path = "/nas/t21/sii/t21sc03_115_9_0.html"
    static_url = "https://mopsov.twse.com.tw" + static_path
    redirect_body = json.dumps(
        {"result": {"url": popup_url}}, separators=(",", ":")
    ).encode("utf-8")
    popup_body = (
        f"<html><body><script>window.open('{static_path}','')</script></body></html>"
    ).encode("utf-8")
    static_bytes = _mops_evidence().raw_source_bytes
    responses = {
        mops_history.MOPS_REDIRECT_API_URL: _ArchiveResponse(
            mops_history.MOPS_REDIRECT_API_URL,
            redirect_body,
            "application/json; charset=utf-8",
        ),
        popup_url: _ArchiveResponse(popup_url, popup_body, "text/html; charset=utf-8"),
        static_url: _ArchiveResponse(static_url, static_bytes, "text/html; charset=utf-8"),
    }

    class _Opener:
        def open(self, request, *, timeout):
            assert timeout == 8.0
            return responses[request.full_url]

    monkeypatch.setattr(mops_history, "build_opener", lambda *_args: _Opener())
    capture = mops_history.capture_mops_monthly_revenue_history_period(
        market="twse", period="2026-09", transport_mode="redirect_chain_v1"
    )
    return capture.to_monthly_revenue_raw_batch_evidence()


def test_archive_reopens_exact_raw_and_selects_only_after_capture_time(tmp_path, monkeypatch):
    first = _batch()
    saved = _append(tmp_path / "archive", first, monkeypatch=monkeypatch)
    archive = read_monthly_revenue_revision_archive(
        tmp_path / "archive",
        saved.archive_sha256,
        expected_archive_sha256=saved.archive_sha256,
    )

    before = select_monthly_revenue_observation_as_of(
        archive,
        market="twse",
        stock_code="2330",
        period="2026-09",
        cutoff_at=datetime(2026, 10, 21, 7, 59, tzinfo=timezone.utc),
    )
    after = select_monthly_revenue_observation_as_of(
        archive,
        market="twse",
        stock_code="2330",
        period="2026-09",
        cutoff_at=datetime(2026, 10, 21, 8, 0, tzinfo=timezone.utc),
    )

    assert before.observation is None
    assert before.observation_as_of_verified is False
    assert after.observation is not None
    assert after.observation_as_of_verified is True
    assert after.formal_pit_eligible is False
    assert after.observation.unit_status == "unknown"
    assert after.observation.source_values


def test_mops_capture_reopens_as_observation_only_after_archive_persist(tmp_path, monkeypatch):
    batch = _mops_evidence()
    persisted_at = datetime(2026, 10, 21, 12, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(revision_archive, "_utc_now", lambda: persisted_at)
    saved = append_monthly_revenue_batch(
        tmp_path / "mops-archive",
        batch,
        archive_sha256=None,
        expected_archive_sha256=None,
    )
    archive = read_monthly_revenue_revision_archive(
        tmp_path / "mops-archive",
        saved.archive_sha256,
        expected_archive_sha256=saved.archive_sha256,
    )
    before_persist = select_monthly_revenue_observation_as_of(
        archive,
        market="twse",
        stock_code="2330",
        period="2026-09",
        cutoff_at=datetime(2026, 10, 21, 12, 59, tzinfo=timezone.utc),
    )
    after_persist = select_monthly_revenue_observation_as_of(
        archive,
        market="twse",
        stock_code="2330",
        period="2026-09",
        cutoff_at=datetime(2026, 10, 21, 13, 0, tzinfo=timezone.utc),
    )
    assert before_persist.observation is None
    assert after_persist.observation is not None
    assert after_persist.observation.captured_at == batch.captured_at
    assert after_persist.observation.available_at == datetime(
        2026, 10, 21, 13, 0, tzinfo=timezone.utc
    )
    assert after_persist.observation.availability_basis == "retrospective_capture_observation"
    assert after_persist.observation.unit_status == "unknown"
    assert after_persist.observation.source_unit_text == "仟元"
    assert dict(after_persist.observation.source_values)["當月營收"] == "1,234"
    assert after_persist.observation.official_announcement_at is None
    assert after_persist.formal_pit_eligible is False


def test_redirect_chain_archive_reopens_and_reparses_every_hop(tmp_path, monkeypatch):
    batch = _redirect_mops_evidence(monkeypatch)
    provenance = dict(batch.transport_provenance)
    assert provenance["transport_mode"] == "redirect_chain_v1"
    persisted_at = batch.available_at + timedelta(hours=2)
    monkeypatch.setattr(revision_archive, "_utc_now", lambda: persisted_at)
    saved = append_monthly_revenue_batch(
        tmp_path / "redirect-archive",
        batch,
        archive_sha256=None,
        expected_archive_sha256=None,
    )
    archive = read_monthly_revenue_revision_archive(
        tmp_path / "redirect-archive",
        saved.archive_sha256,
        expected_archive_sha256=saved.archive_sha256,
    )
    observation = select_monthly_revenue_observation_as_of(
        archive,
        market="twse",
        stock_code="2330",
        period="2026-09",
        cutoff_at=persisted_at + timedelta(hours=1),
    )
    assert observation.observation is not None
    assert observation.observation.unit_status == "unknown"
    assert observation.formal_pit_eligible is False


def test_late_archival_never_makes_old_capture_visible_before_archive_persist(tmp_path, monkeypatch):
    batch = raw_batch_from_openapi(_batch())
    persisted_at = datetime(2026, 10, 24, 3, 15, tzinfo=timezone.utc)
    monkeypatch.setattr(revision_archive, "_utc_now", lambda: persisted_at)
    saved = append_monthly_revenue_batch(
        tmp_path / "archive",
        batch,
        archive_sha256=None,
        expected_archive_sha256=None,
    )
    archive = read_monthly_revenue_revision_archive(
        tmp_path / "archive",
        saved.archive_sha256,
        expected_archive_sha256=saved.archive_sha256,
    )
    before_archive = select_monthly_revenue_observation_as_of(
        archive,
        market="twse",
        stock_code="2330",
        period="2026-09",
        cutoff_at=datetime(2026, 10, 23, 23, 59, tzinfo=timezone.utc),
    )
    after_archive = select_monthly_revenue_observation_as_of(
        archive,
        market="twse",
        stock_code="2330",
        period="2026-09",
        cutoff_at=datetime(2026, 10, 24, 4, 0, tzinfo=timezone.utc),
    )
    assert before_archive.observation is None
    assert after_archive.observation is not None
    assert after_archive.observation.captured_at < after_archive.observation.available_at
    assert after_archive.observation.captured_batch_available_at == batch.available_at
    assert after_archive.observation.archive_persisted_at == persisted_at


def test_archive_appends_parented_revision_and_preserves_old_index(tmp_path, monkeypatch):
    root = tmp_path / "archive"
    first = _append(root, _batch(), monkeypatch=monkeypatch)
    old_bytes = first.archive_path.read_bytes()
    first_archive = read_monthly_revenue_revision_archive(
        root,
        first.archive_sha256,
        expected_archive_sha256=first.archive_sha256,
    )
    first_observation = select_monthly_revenue_observation_as_of(
        first_archive,
        market="twse",
        stock_code="2330",
        period="2026-09",
        cutoff_at=datetime(2026, 10, 21, 8, 0, tzinfo=timezone.utc),
    ).observation
    assert first_observation is not None

    later_batch = raw_batch_from_openapi(
        _batch(
            amount="2.250",
            completed_at=datetime(2026, 10, 22, 7, 15, tzinfo=timezone.utc),
        )
    )
    later_batch = replace(
        later_batch,
        parent_revision_ids=(
            (
                first_observation.stock_code,
                first_observation.period,
                first_observation.row_sha256,
                first_observation.revision_id,
            ),
        ),
    )
    monkeypatch.setattr(
        revision_archive,
        "_utc_now",
        lambda: later_batch.available_at.astimezone(timezone.utc),
    )
    second = append_monthly_revenue_batch(
        root,
        later_batch,
        archive_sha256=first.archive_sha256,
        expected_archive_sha256=first.archive_sha256,
    )
    assert first.archive_path.read_bytes() == old_bytes
    first.archive_path.unlink()
    reopened = read_monthly_revenue_revision_archive(
        root,
        second.archive_sha256,
        expected_archive_sha256=second.archive_sha256,
    )
    selected = select_monthly_revenue_observation_as_of(
        reopened,
        market="twse",
        stock_code="2330",
        period="2026-09",
        cutoff_at=datetime(2026, 10, 22, 8, 0, tzinfo=timezone.utc),
    )
    assert selected.observation is not None
    assert selected.observation.parent_revision_id == first_observation.revision_id
    assert selected.observation.row_sha256 != first_observation.row_sha256


def test_archive_rejects_tampered_same_stock_parent_row_hash(tmp_path, monkeypatch):
    root = tmp_path / "archive"
    first = _append(root, _batch(), monkeypatch=monkeypatch)
    first_archive = read_monthly_revenue_revision_archive(
        root,
        first.archive_sha256,
        expected_archive_sha256=first.archive_sha256,
    )
    first_observation = select_monthly_revenue_observation_as_of(
        first_archive,
        market="twse",
        stock_code="2330",
        period="2026-09",
        cutoff_at=datetime(2026, 10, 21, 8, 0, tzinfo=timezone.utc),
    ).observation
    assert first_observation is not None
    second_batch = raw_batch_from_openapi(
        _batch(
            amount="2.250",
            completed_at=datetime(2026, 10, 22, 7, 15, tzinfo=timezone.utc),
        )
    )
    second_batch = replace(
        second_batch,
        parent_revision_ids=(
            (
                first_observation.stock_code,
                first_observation.period,
                first_observation.row_sha256,
                first_observation.revision_id,
            ),
        ),
    )
    monkeypatch.setattr(
        revision_archive,
        "_utc_now",
        lambda: second_batch.available_at.astimezone(timezone.utc),
    )
    second = append_monthly_revenue_batch(
        root,
        second_batch,
        archive_sha256=first.archive_sha256,
        expected_archive_sha256=first.archive_sha256,
    )
    tampered = json.loads(second.archive_path.read_text(encoding="utf-8"))
    parent_ref = tampered["batches"][1]["parent_revision_ids"][0]
    assert parent_ref[0] == "2330"
    assert parent_ref[3] == first_observation.revision_id
    parent_ref[2] = "0" * 64
    tampered_payload = revision_archive._canonical_json_bytes(tampered)
    tampered_sha256 = hashlib.sha256(tampered_payload).hexdigest()
    tampered_path = root / "indexes" / f"{tampered_sha256}.json"
    tampered_path.write_bytes(tampered_payload)

    with pytest.raises(
        MonthlyRevenueRevisionArchiveError,
        match="archive_parent_row_hash_mismatch",
    ):
        read_monthly_revenue_revision_archive(
            root,
            tampered_sha256,
            expected_archive_sha256=tampered_sha256,
        )


def test_archive_keeps_markets_separate_and_rejects_same_time_content_conflict(
    tmp_path, monkeypatch
):
    root = tmp_path / "archive"
    first = _append(root, _batch(), monkeypatch=monkeypatch)
    second = _append(
        root,
        _batch(market="tpex"),
        parent_hash=first.archive_sha256,
        monkeypatch=monkeypatch,
    )
    third = _append(
        root,
        _batch(amount="9.999"),
        parent_hash=second.archive_sha256,
        monkeypatch=monkeypatch,
    )
    archive = read_monthly_revenue_revision_archive(
        root,
        third.archive_sha256,
        expected_archive_sha256=third.archive_sha256,
    )
    twse = select_monthly_revenue_observation_as_of(
        archive,
        market="twse",
        stock_code="2330",
        period="2026-09",
        cutoff_at=datetime(2026, 10, 21, 8, 0, tzinfo=timezone.utc),
    )
    tpex = select_monthly_revenue_observation_as_of(
        archive,
        market="tpex",
        stock_code="2330",
        period="2026-09",
        cutoff_at=datetime(2026, 10, 21, 8, 0, tzinfo=timezone.utc),
    )
    assert twse.status == "ambiguous_same_time_content"
    assert twse.observation is None
    assert tpex.observation is not None
    assert tpex.observation.market == "tpex"


def test_archive_requires_external_index_hash_and_detects_raw_tampering(
    tmp_path, monkeypatch
):
    saved = _append(tmp_path / "archive", _batch(), monkeypatch=monkeypatch)
    with pytest.raises(MonthlyRevenueRevisionArchiveError, match="external_hash_mismatch"):
        read_monthly_revenue_revision_archive(
            tmp_path / "archive",
            saved.archive_sha256,
            expected_archive_sha256="0" * 64,
        )

    blob = tmp_path / "archive" / "raw" / "sha256" / f"{saved.raw_blob_sha256}.bin"
    payload = blob.read_bytes()
    blob.write_bytes(payload + b" ")
    with pytest.raises(MonthlyRevenueRevisionArchiveError, match="raw_hash_mismatch"):
        read_monthly_revenue_revision_archive(
            tmp_path / "archive",
            saved.archive_sha256,
            expected_archive_sha256=saved.archive_sha256,
        )


def test_batch_evidence_rejects_naive_clocks_and_fake_raw_hash():
    evidence = raw_batch_from_openapi(_batch())
    with pytest.raises(MonthlyRevenueRevisionArchiveError, match="captured_at_must_be_aware"):
        replace(evidence, captured_at=datetime(2026, 10, 21, 7, 15))
    with pytest.raises(MonthlyRevenueRevisionArchiveError, match="batch_raw_hash_mismatch"):
        replace(evidence, raw_source_sha256="0" * 64)
