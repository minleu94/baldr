"""策略帳 Position Health v2 封存的 exact-source 邊界測試。"""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

import app_module.position_health_strategy_archive as strategy_archive
from app_module.portfolio_research_account_reader import (
    StrategyPaperPortfolioResearchAccountReader,
)
from app_module.position_health_saved_archive import (
    PositionHealthAccountScope,
    PositionHealthExactScope,
    PositionHealthPositionScope,
    SavedHealthArchiveError,
    SavedHealthReceiptSelector,
    read_saved_health_receipt,
)
from app_module.position_health_strategy_archive import (
    prepare_strategy_health_baseline,
    publish_strategy_saved_health_receipt,
    read_strategy_saved_health_exact,
)
from app_module.position_health_transition_evaluator import evaluate_baseline_file
from app_module.position_health_transition_read_service import (
    PositionHealthTransitionReadService,
)
from app_module.position_health_source_providers import PositionThesisRegistryWriter
from data_module.official_trading_calendar_cache import build_twse_calendar_cache
from test_portfolio_research_health_source import _prepared
from test_position_health_transition_read_service import _contract as _fixture_contract


def _canonical_write(path, payload):
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )


def _canonical_hash(payload):
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _write_hashed_source(path, payload):
    content = dict(payload)
    content["content_sha256"] = _canonical_hash(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(content, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_strategy_governed_sources(case, tmp_path):
    """只建立此帳戶的明示合成 QA thesis／條件／指標／日曆來源。"""
    source = case["account_reader"].read_health_source(
        portfolio_id=case["binding"].portfolio_id,
        snapshot_id=case["operation"].snapshot_id,
    )
    baseline_positions = case["baseline"]["positions"]
    mark_by_code = {row.stock_code: row for row in source.mark_prices}
    entry_id_by_code = dict(source.entry_lineage_ids)
    decision_date = case["baseline"]["decision_date"]
    created_at = datetime.now(timezone.utc)

    source_dir = tmp_path / "strategy-governed-sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    registry_path = source_dir / "thesis.json"
    condition_path = source_dir / "condition.json"
    metrics_path = source_dir / "metrics.json"
    condition_rows = []
    metric_rows = []
    for baseline_position in baseline_positions:
        code = baseline_position["stock_code"]
        position_id = baseline_position["position_id"]
        entry_lineage_id = baseline_position["entry_lineage_id"]
        mark = mark_by_code[code]
        assert entry_lineage_id == entry_id_by_code[code]
        assert position_id == entry_lineage_id
        assert mark.source_date == "2026-08-03"

        original_contract = _fixture_contract(action="exit")
        contract = replace(
            original_contract,
            position_id=position_id,
            stock_code=code,
            # 此 fixture 的原開倉日是 2026-08-03，不改用較晚 snapshot 或 Health 日期。
            entry_date="2026-08-03",
            decision_date=decision_date,
            available_date=decision_date,
            next_review_date=(date.fromisoformat(decision_date) + timedelta(days=30)).isoformat(),
            source_trace=(f"human:synthetic-qa:{decision_date}",),
        )
        PositionThesisRegistryWriter(registry_path).append(
            contract=contract,
            entry_lineage_id=entry_lineage_id,
            version_id=f"strategy-health-qa-{case['selection'].operation_id}-{code}",
            authored_by="reviewer:synthetic-qa",
            authored_at=created_at,
            available_at=created_at,
        )

        condition_rows.append({
            "position_id": position_id,
            "entry_lineage_id": entry_lineage_id,
            "stock_code": code,
            "quality": "verified",
            "result": {
                "status": "valid",
                "label": "合成 QA 條件已核對",
                "source_label": "strategy-position-health-test-fixture",
                "entry_regime": "Trend",
                "current_regime": "Trend",
                "entry_total_score": "12.0",
                "current_total_score": "12.0",
                "reasons": ["synthetic_qa_fixture"],
                "details": {"fixture_scope": "test_only"},
            },
            "current_snapshot": {
                "current_regime": "Trend",
                "current_total_score": "12.0",
                "current_price": str(mark.scalar_value),
            },
        })
        metric_rows.append({
            "position_id": position_id,
            "entry_lineage_id": entry_lineage_id,
            "stock_code": code,
            "metric_id": "drawdown_bp",
            "value": "1200",
            "available_date": decision_date,
            "available_at": created_at.isoformat(),
        })

    condition_path.parent.mkdir(parents=True, exist_ok=True)
    _write_hashed_source(condition_path, {
        "schema_version": "position-health-condition-source.v1",
        "source_id": f"strategy-health-qa-condition:{source.source_hash}",
        "source_snapshot_hash": _canonical_hash({
            "source": source.source_hash,
            "positions": condition_rows,
            "as_of_date": decision_date,
        }),
        "as_of_date": decision_date,
        "available_at": created_at.isoformat(),
        "positions": condition_rows,
    })
    _write_hashed_source(metrics_path, {
        "schema_version": "position-health-metrics-source.v1",
        "source_id": f"strategy-health-qa-metrics:{source.source_hash}",
        "source_snapshot_hash": _canonical_hash({
            "source": source.source_hash,
            "metrics": metric_rows,
            "as_of_date": decision_date,
        }),
        "available_at": created_at.isoformat(),
        "metrics": metric_rows,
    })

    observed_at = datetime.now(timezone.utc)
    captured_at = observed_at - timedelta(minutes=1)
    calendar_year = date.fromisoformat(decision_date).year
    weekday_names = ("一", "二", "三", "四", "五", "六", "日")
    raw_calendar = json.dumps(
        [{
            "Date": f"{calendar_year - 1911:03d}0101",
            "Description": "策略 Health 同決策日期 QA 合成年度日曆",
            "Name": "測試年度休市",
            "Weekday": weekday_names[date(calendar_year, 1, 1).weekday()],
        }],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    calendar_payload = build_twse_calendar_cache(
        calendar_year=calendar_year,
        raw_response=raw_calendar,
        requested_at=captured_at,
        captured_at=captured_at,
        response_status=200,
        max_age=timedelta(days=7),
    )
    calendar_dir = source_dir / "calendar_cache"
    calendar_dir.mkdir(parents=True, exist_ok=True)
    calendar_path = calendar_dir / f"twse_holiday_schedule_{calendar_year}_strategy_fixture.json"
    calendar_path.write_text(
        json.dumps(calendar_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    calendar_db_path = source_dir / "market.sqlite3"
    with sqlite3.connect(calendar_db_path):
        pass

    return {
        "source": source,
        "registry_path": registry_path,
        "condition_path": condition_path,
        "metrics_path": metrics_path,
        "calendar_path": calendar_dir,
        "calendar_db_path": calendar_db_path,
        "observed_at": observed_at,
    }


def test_strategy_v2_projects_governed_exit_for_same_checkpoint(tmp_path, monkeypatch):
    case = _prepared_pipeline(tmp_path, monkeypatch)
    sources = _write_strategy_governed_sources(case, tmp_path)
    entry_date = min(mark.source_date for mark in sources["source"].mark_prices)
    evaluated = evaluate_baseline_file(
        baseline_path=case["baseline_path"],
        output_dir=case["archive_root"],
        observed_at=sources["observed_at"],
        decision_date=case["baseline"]["decision_date"],
        thesis_registry_path=sources["registry_path"],
        condition_source_path=sources["condition_path"],
        metrics_source_path=sources["metrics_path"],
        calendar_cache_path=sources["calendar_path"],
        calendar_db_path=sources["calendar_db_path"],
        calendar_start_date=entry_date,
    )
    case["evaluated"] = evaluated

    reference = _publish(case)
    saved = _read(case, reference)

    assert evaluated["status"] == "passed", evaluated.get("blockers")
    assert saved.health.status == "passed"
    assert len(saved.health.positions) == len(case["baseline"]["positions"])
    assert all(row.proposed_state == "EXIT_CANDIDATE" for row in saved.health.positions)
    assert saved.source == sources["source"]
    assert {mark.source_date for mark in saved.source.mark_prices} == {"2026-08-03"}
    assert saved.decision_date.isoformat() == case["baseline"]["decision_date"]


def _prepared_pipeline(tmp_path, monkeypatch):
    service, stores, binding, operation, selection = _prepared(
        tmp_path, monkeypatch, filled=True
    )
    account_reader = StrategyPaperPortfolioResearchAccountReader(
        service,
        selection,
        decision_cutoff=datetime.now(timezone.utc),
    )
    archive_root = tmp_path / "strategy-health"
    baseline_path = prepare_strategy_health_baseline(
        account_reader=account_reader,
        portfolio_id=binding.portfolio_id,
        snapshot_id=operation.snapshot_id,
        output_dir=archive_root,
    )
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    evaluated = evaluate_baseline_file(
        baseline_path=baseline_path,
        output_dir=archive_root,
        observed_at=datetime.now(timezone.utc),
        decision_date=baseline["decision_date"],
    )
    transition_reader = PositionHealthTransitionReadService(
        archive_root,
        now_provider=lambda: datetime.now(timezone.utc),
    )
    return {
        "service": service,
        "stores": stores,
        "binding": binding,
        "operation": operation,
        "selection": selection,
        "account_reader": account_reader,
        "archive_root": archive_root,
        "baseline_path": baseline_path,
        "baseline": baseline,
        "evaluated": evaluated,
        "transition_reader": transition_reader,
    }


def _publish(case):
    return publish_strategy_saved_health_receipt(
        output_dir=case["archive_root"],
        result_path=case["evaluated"]["result_path"],
        account_reader=case["account_reader"],
        portfolio_id=case["binding"].portfolio_id,
        snapshot_id=case["operation"].snapshot_id,
    )


def _read(case, reference, *, account_reader=None, portfolio_id=None, snapshot_id=None, cutoff=None):
    return read_strategy_saved_health_exact(
        reader=case["transition_reader"],
        reference=reference,
        account_reader=account_reader or case["account_reader"],
        portfolio_id=portfolio_id or case["binding"].portfolio_id,
        snapshot_id=snapshot_id or case["operation"].snapshot_id,
        decision_cutoff=cutoff or datetime.now(timezone.utc),
    )


def test_strategy_v2_reuses_exact_account_and_keeps_missing_health_degraded(
    tmp_path, monkeypatch
):
    case = _prepared_pipeline(tmp_path, monkeypatch)
    database_paths = (case["stores"].state_db, case["stores"].cost_ledger_db)
    database_before = {path: path.read_bytes() for path in database_paths}

    reference = _publish(case)
    saved = _read(case, reference)
    fresh_source = case["account_reader"].read_health_source(
        portfolio_id=case["binding"].portfolio_id,
        snapshot_id=case["operation"].snapshot_id,
    )

    assert case["baseline"]["warnings"] == [
        "strategy_health_requires_original_governed_sources"
    ]
    assert case["evaluated"]["status"] == "degraded"
    assert saved.health.status == "degraded"
    assert saved.source == fresh_source
    assert saved.source.account.portfolio_id == case["binding"].portfolio_id
    assert saved.source.account.snapshot_id == case["operation"].snapshot_id
    assert saved.source.source_hash != saved.source.account.source_hash
    assert saved.baseline_sha256 == case["evaluated"]["baseline_sha256"]
    assert saved.result_sha256 == (
        "sha256:" + reference.receipt_id.removeprefix("phsr-v2-")
    )
    assert saved.decision_date.isoformat() == case["baseline"]["decision_date"]
    assert all(row.proposed_state == "WATCH" for row in saved.health.positions)

    # Price evidence keeps its independently published quote date and row receipts;
    # the Health decision date and account snapshot date are not substitutes.
    assert saved.source.mark_prices
    assert {mark.source_date for mark in saved.source.mark_prices} == {"2026-08-03"}
    assert all(mark.raw_response_sha256.startswith("sha256:") for mark in saved.source.mark_prices)
    assert all(mark.projection_row_sha256 == mark.sqlite_projection_row_sha256
               for mark in saved.source.mark_prices)
    assert all(mark.source_date != saved.decision_date.isoformat()
               for mark in saved.source.mark_prices)
    assert {path: path.read_bytes() for path in database_paths} == database_before


def test_strategy_v2_rejects_wrong_account_snapshot_future_cutoff_and_cross_account(
    tmp_path, monkeypatch
):
    case = _prepared_pipeline(tmp_path, monkeypatch)
    reference = _publish(case)

    with pytest.raises(ValueError):
        _read(case, reference, portfolio_id="another-account")
    with pytest.raises(ValueError):
        _read(case, reference, snapshot_id="another-snapshot")
    with pytest.raises(SavedHealthArchiveError, match="strategy_health_cutoff_invalid_or_future"):
        _read(case, reference, cutoff=datetime.now(timezone.utc) + timedelta(seconds=30))

    other_root = tmp_path / "other-account"
    other_root.mkdir()
    other_service, _, other_binding, other_operation, other_selection = _prepared(
        other_root, monkeypatch, filled=True
    )
    other_reader = StrategyPaperPortfolioResearchAccountReader(
        other_service,
        other_selection,
        decision_cutoff=datetime.now(timezone.utc),
    )
    with pytest.raises(SavedHealthArchiveError, match="strategy_health_archive_source_mismatch"):
        _read(
            case,
            reference,
            account_reader=other_reader,
            portfolio_id=other_binding.portfolio_id,
            snapshot_id=other_operation.snapshot_id,
        )


def test_strategy_v2_rejects_evaluator_and_baseline_cross_binding(tmp_path, monkeypatch):
    case = _prepared_pipeline(tmp_path, monkeypatch)
    result = json.loads(
        Path(case["evaluated"]["result_path"]).read_text(encoding="utf-8")
    )
    result["provenance"]["strategy_health_source_sha256"] = "sha256:" + "f" * 64
    mismatched_result = case["archive_root"] / "mismatched-evaluator.json"
    _canonical_write(mismatched_result, result)
    with pytest.raises(SavedHealthArchiveError, match="strategy_health_evaluator_source_mismatch"):
        publish_strategy_saved_health_receipt(
            output_dir=case["archive_root"],
            result_path=mismatched_result,
            account_reader=case["account_reader"],
            portfolio_id=case["binding"].portfolio_id,
            snapshot_id=case["operation"].snapshot_id,
        )

    baseline = json.loads(case["baseline_path"].read_text(encoding="utf-8"))
    baseline["source_snapshot_rows_sha256"] = "sha256:" + "e" * 64
    _canonical_write(case["baseline_path"], baseline)
    with pytest.raises(SavedHealthArchiveError, match="strategy_health_baseline_checkpoint_mismatch"):
        _publish(case)


def test_strategy_v2_external_sha_is_required_and_retry_keeps_original_clock(
    tmp_path, monkeypatch
):
    case = _prepared_pipeline(tmp_path, monkeypatch)
    clock_base = datetime.now(timezone.utc) + timedelta(seconds=1)

    class _AdvancingClock(datetime):
        calls = 0

        @classmethod
        def now(cls, tz=None):
            cls.calls += 1
            value = clock_base + timedelta(seconds=cls.calls)
            return value.replace(tzinfo=None) if tz is None else value.astimezone(tz)

    monkeypatch.setattr(strategy_archive, "datetime", _AdvancingClock)
    case["transition_reader"] = PositionHealthTransitionReadService(
        case["archive_root"],
        now_provider=lambda: _AdvancingClock.now(timezone.utc),
    )
    reference = _publish(case)
    first = _read(case, reference, cutoff=_AdvancingClock.now(timezone.utc))

    with pytest.raises(SavedHealthArchiveError, match="strategy_health_external_receipt_hash_mismatch"):
        _read(
            case,
            replace(reference, receipt_sha256="sha256:" + "0" * 64),
            cutoff=_AdvancingClock.now(timezone.utc),
        )

    retry_reference = _publish(case)
    retried = _read(case, retry_reference, cutoff=_AdvancingClock.now(timezone.utc))
    assert retry_reference == reference
    assert retried.available_at == first.available_at
    assert retried.available_at.tzinfo is not None
    assert retried.available_at.utcoffset() is not None


def test_v1_saved_health_reader_still_rejects_strategy_namespace(tmp_path, monkeypatch):
    case = _prepared_pipeline(tmp_path, monkeypatch)
    source = case["account_reader"].read_health_source(
        portfolio_id=case["binding"].portfolio_id,
        snapshot_id=case["operation"].snapshot_id,
    )
    entry_ids = dict(source.entry_lineage_ids)
    positions = tuple(
        PositionHealthPositionScope(
            position_id=entry_ids[row.stock_code],
            stock_code=row.stock_code,
            shares=row.shares,
        )
        for row in source.positions
        if row.shares > 0
    )
    scope = PositionHealthExactScope(
        portfolio_id=case["binding"].portfolio_id,
        snapshot_id=case["operation"].snapshot_id,
        decision_date=date.fromisoformat(case["baseline"]["decision_date"]),
        decision_cutoff=datetime.now(timezone.utc),
        positions=positions,
        expected_source_snapshot_rows_sha256=source.source_snapshot_rows_sha256,
        account_scope=PositionHealthAccountScope(
            "strategy", source.selection.account_namespace
        ),
    )

    model = read_saved_health_receipt(
        reader=case["transition_reader"],
        selector=SavedHealthReceiptSelector(case["evaluated"]["saved_receipt_id"]),
        scope=scope,
    )

    assert model.status == "blocked"
    assert "saved_health_strategy_namespace_v1_unsupported" in model.blockers
