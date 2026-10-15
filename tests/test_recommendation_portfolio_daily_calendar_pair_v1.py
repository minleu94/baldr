"""每日日曆版本沿原雙 Registry run reader；合成錨點不授真來源資格。"""

from dataclasses import replace
from datetime import timedelta
import hashlib
from pathlib import Path

import pytest

from app_module import recommendation_portfolio_full_period_pair_v1 as pair_module
from app_module.official_calendar_daily_snapshot_v1 import OfficialCalendarDailySnapshotCancelled
from app_module.recommendation_portfolio_full_period_pair_v1 import (
    FullPeriodPairReadCancelledV1, FullPeriodPairReadErrorV1,
    RecommendationPortfolioFullPeriodPairReadServiceV1,
)
from app_module.recommendation_portfolio_period_calendar_read_pin_v1 import (
    PortfolioPeriodCalendarDailyReadPinV1,
)
from app_module.saved_strategy_rule_card import metadata_sha256
import test_official_calendar_daily_snapshot_v1 as daily_fixture
import test_recommendation_portfolio_full_period_pair_v1 as pair_fixture


def _case(tmp_path: Path):
    config, service, reader, _calendar, left, right, *_ = pair_fixture._saved_pair(tmp_path)
    daily_root = tmp_path / "daily"
    daily_root.mkdir()
    root, protected = daily_fixture._roots(daily_root)
    snapshot, _ = daily_fixture._write(root, protected)
    anchors = daily_fixture._acceptances()
    pin = PortfolioPeriodCalendarDailyReadPinV1(
        snapshot.batch_directory, snapshot.manifest_sha256, snapshot.receipt_sha256,
        "twse", protected + (Path(config.data_root), Path(config.output_root)),
        (anchors["twse"], anchors["tpex"]), snapshot.available_hour,
    )
    return RecommendationPortfolioFullPeriodPairReadServiceV1(service, reader), pin, left, right, service


def _read(case, pin=None):
    pair, original, left, right, _ = case
    return pair.read_daily(
        left.run_id, right.run_id, calendar_pin=original if pin is None else pin,
        expected_left_metadata_sha256=metadata_sha256(left),
        expected_right_metadata_sha256=metadata_sha256(right),
    )


def _inventory(case):
    _, pin, left, right, service = case
    paths = list(pin.batch_directory.iterdir()) + [service.repository.db_path]
    for run in (left, right):
        paths.extend(service._paths_for(run.run_id)[key] for key in (
            "equity_final", "trades_final", "portfolio_result_final",
        ))
    result = []
    for path in sorted(paths):
        stamp = path.stat()
        # 讀取本身可更新 access time；來源身份沿原守衛核對 inode／bytes／寫入時鐘。
        result.append((str(path), (stamp.st_dev, stamp.st_ino, stamp.st_nlink,
                                  stamp.st_size, stamp.st_mtime_ns, stamp.st_ctime_ns),
                       hashlib.sha256(path.read_bytes()).hexdigest()))
    return result


@pytest.mark.parametrize("market", ["twse", "tpex"])
def test_daily_exact_pair_uses_original_public_reader_and_retains_qualification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, market: str,
) -> None:
    case = _case(tmp_path)
    pair, pin, left, right, _ = case
    pin = replace(pin, market=market)
    before = _inventory(case)
    calls = []
    original = pair._reader.read

    def observed(run_id, **kwargs):
        calls.append(run_id)
        return original(run_id, **kwargs)

    monkeypatch.setattr(pair._reader, "read", observed)
    monkeypatch.setattr(pair_fixture, "_produce", lambda **kwargs: pytest.fail("不可重跑producer"))
    result = _read(case, pin)
    assert calls == [left.run_id, right.run_id]
    assert result.market == market and result.coverage_complete
    assert result.expected_session_dates == pair_fixture._DATES
    assert result.status == "blocked" and result.metrics is None
    assert not result.performance_eligible and not result.historical_pit_eligible and not result.broker_eligible
    assert "calendar_candidate_only" in result.reasons
    assert "left_source_evidence_unknown" in result.reasons
    assert "left_currency_evidence_unknown" in result.reasons
    assert "left_cost_evidence_unknown" in result.reasons
    identity = result.daily_calendar_source
    assert identity is not None
    assert identity.batch_id == pin.batch_directory.name
    assert identity.manifest_sha256 == result.calendar_external_sha256 == pin.expected_manifest_sha256
    assert identity.receipt_sha256 == pin.expected_receipt_sha256
    assert identity.decision_cutoff == pin.decision_cutoff.isoformat()
    assert identity.acceptance_ids == tuple(item.acceptance_id for item in pin.trusted_acceptances)
    assert _inventory(case) == before


@pytest.mark.parametrize("field", ["expected_manifest_sha256", "expected_receipt_sha256"])
def test_daily_pair_rejects_wrong_external_sha(tmp_path: Path, field: str) -> None:
    case = _case(tmp_path)
    with pytest.raises(FullPeriodPairReadErrorV1):
        _read(case, replace(case[1], **{field: "0" * 64}))


def test_daily_pair_rejects_earlier_cutoff_and_different_independent_anchors(tmp_path: Path) -> None:
    case = _case(tmp_path)
    with pytest.raises(FullPeriodPairReadErrorV1):
        _read(case, replace(case[1], decision_cutoff=case[1].decision_cutoff - timedelta(microseconds=1)))
    anchors = daily_fixture._acceptances(suffix="-other")
    with pytest.raises(FullPeriodPairReadErrorV1):
        _read(case, replace(case[1], trusted_acceptances=(anchors["twse"], anchors["tpex"])))


def test_daily_pair_revalidates_same_batch_after_both_run_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _case(tmp_path)
    pair, pin, *_ = case
    original = pair._read_run
    calls = []

    def changed(run_id, metadata, **kwargs):
        result = original(run_id, metadata, **kwargs)
        calls.append(run_id)
        if len(calls) == 2:
            (pin.batch_directory / "receipt.json").write_bytes(b"{}")
        return result

    monkeypatch.setattr(pair, "_read_run", changed)
    with pytest.raises(FullPeriodPairReadErrorV1):
        _read(case)
    assert len(calls) == 2


def test_daily_pair_rejects_metadata_before_reading_calendar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pair, pin, left, right, _ = _case(tmp_path)
    monkeypatch.setattr(pair_module, "read_official_calendar_daily_snapshot_v1",
                        lambda *args, **kwargs: pytest.fail("錯 metadata 不可開日曆"))
    with pytest.raises(FullPeriodPairReadErrorV1, match="left 所選 metadata"):
        pair.read_daily(left.run_id, right.run_id, calendar_pin=pin,
                        expected_left_metadata_sha256="0" * 64)


def test_daily_reader_cancel_is_preserved_as_pair_cancel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _case(tmp_path)

    def cancelled(*args, **kwargs):
        raise OfficialCalendarDailySnapshotCancelled("calendar_batch_cancelled")

    monkeypatch.setattr(pair_module, "read_official_calendar_daily_snapshot_v1", cancelled)
    with pytest.raises(FullPeriodPairReadCancelledV1, match="read_cancelled"):
        _read(case)


@pytest.mark.parametrize("change", ["no_anchors", "wrong_order", "wrong_endpoint", "naive_cutoff", "bad_sha"])
def test_daily_pin_rejects_untrusted_or_invalid_fields(tmp_path: Path, change: str) -> None:
    case = _case(tmp_path)
    pin = case[1]
    kwargs = {
        "no_anchors": {"trusted_acceptances": ()},
        "wrong_order": {"trusted_acceptances": tuple(reversed(pin.trusted_acceptances))},
        "wrong_endpoint": {"trusted_acceptances": (
            replace(pin.trusted_acceptances[0], official_source_endpoint="https://example.invalid"),
            pin.trusted_acceptances[1],
        )},
        "naive_cutoff": {"decision_cutoff": pin.decision_cutoff.replace(tzinfo=None)},
        "bad_sha": {"expected_receipt_sha256": "A" * 64},
    }[change]
    with pytest.raises(ValueError):
        replace(pin, **kwargs)
