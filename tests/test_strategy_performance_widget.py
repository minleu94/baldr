"""P08a 私有 UI 候選隔離測試（STATIC / NOT_RUN）；只直接建立 DTO fixture。"""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from typing import cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from app_module.strategy_performance_read_service import (
    AccountBindingRead,
    AccountBindingStatus,
    CheckpointAvailabilityRead,
    LedgerMarkerRead,
    MetricCell,
    PaperCheckpointCard,
    PaperCheckpointSelector,
    PaperFillRead,
    PaperPositionRead,
    QualificationStatus,
    ReadStatus,
    RowProvenance,
    SourceAvailabilityStatus,
)
from ui_qt.widgets.strategy_performance_widget import StrategyPerformanceWidget


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = cast(QApplication | None, QApplication.instance())
    if instance is None:
        instance = QApplication([])
    return instance


def _selector(tag: str = "A") -> PaperCheckpointSelector:
    return PaperCheckpointSelector(
        strategy_id=f"strategy-{tag}",
        strategy_version_id=f"version-{tag}",
        account_namespace=f"acct-{tag}",
        operation_id=f"operation-{tag}",
        snapshot_id=f"snapshot-{tag}",
        decision_cutoff=datetime(2026, 10, 13, 9, 0, tzinfo=timezone.utc),
    )


def _card(
    selector: PaperCheckpointSelector,
    *,
    zero_fill: bool = False,
    cash: Decimal = Decimal("499000.487654321"),
    nav: Decimal = Decimal("500000.987654321"),
    read_status: ReadStatus = ReadStatus.VERIFIED,
    reason: str | None = None,
    metric_value: Decimal | None = None,
) -> PaperCheckpointCard:
    fills = () if zero_fill else (
        PaperFillRead(
            fill_id=f"fill-{selector.strategy_id}",
            order_id=f"order-{selector.strategy_id}",
            portfolio_id=selector.account_namespace,
            event_date="2026-10-13",
            stock_code="2330",
            side="buy",
            requested_quantity=1,
            filled_quantity=1,
            reference_price=Decimal("1000.25"),
            fill_price=Decimal("1000.50"),
            commission=Decimal("1.0000"),
            tax=Decimal("0"),
            slippage_cost=Decimal("0.2500"),
            turnover_bp=20,
            execution_gap_bp=2,
            status="filled",
            source_event_id=f"event-{selector.strategy_id}",
            override_reason=None,
            source_type="isolated_fixture",
            research_only=True,
            broker_order_allowed=False,
            auto_rebalance_allowed=False,
        ),
    )
    fill_ids = tuple(item.fill_id for item in fills)
    event_ids = tuple(item.source_event_id for item in fills)
    binding = AccountBindingRead(
        strategy_id=selector.strategy_id,
        strategy_version_id=selector.strategy_version_id,
        strategy_version="fixture-version",
        strategy_artifact_sha256="a" * 64,
        params_sha256="b" * 64,
        config_sha256="c" * 64,
        source_run_id="fixture-run",
        account_namespace=selector.account_namespace,
        portfolio_id=selector.account_namespace,
        binding_sha256="d" * 64,
        policy_id="fixture-policy",
        policy_version="1",
        policy_sha256="e" * 64,
        cost_model_id="fixture-cost",
        cost_model_version="1",
        cost_model_sha256="f" * 64,
        benchmark_id="fixture-benchmark",
        benchmark_version="1",
        benchmark_sha256="0" * 64,
        start_date="2026-01-01",
        initial_capital="500000",
        max_positions=8,
    )
    marker = LedgerMarkerRead(
        operation_id=selector.operation_id,
        portfolio_id=selector.account_namespace,
        event_date="2026-10-13",
        expected_rowset_hash="1" * 64,
        rowset_hash_after="2" * 64,
        ordered_fill_ids=fill_ids,
        fill_batch_sha256="3" * 64,
        transition_id=None,
        transition_sha256=None,
        operation_sha256="sha256:" + ("4" * 64),
        marker_sha256="5" * 64,
        zero_fill=zero_fill,
    )
    availability = CheckpointAvailabilityRead(
        schema_version="fixture-v1",
        operation_id=selector.operation_id,
        snapshot_id=selector.snapshot_id,
        portfolio_id=selector.account_namespace,
        account_namespace=selector.account_namespace,
        binding_sha256=binding.binding_sha256,
        snapshot_sha256="6" * 64,
        base_receipt_sha256="7" * 64,
        persisted_at=datetime(2026, 10, 13, 8, 1, tzinfo=timezone.utc),
        available_at=datetime(2026, 10, 13, 8, 2, tzinfo=timezone.utc),
        receipt_sha256="8" * 64,
    )
    provenance = RowProvenance(
        strategy_id=selector.strategy_id,
        strategy_version_id=selector.strategy_version_id,
        account_namespace=selector.account_namespace,
        portfolio_id=selector.account_namespace,
        binding_sha256=binding.binding_sha256,
        policy_id=binding.policy_id,
        policy_version=binding.policy_version,
        policy_sha256=binding.policy_sha256,
        cost_model_id=binding.cost_model_id,
        cost_model_version=binding.cost_model_version,
        cost_model_sha256=binding.cost_model_sha256,
        benchmark_id=binding.benchmark_id,
        benchmark_version=binding.benchmark_version,
        benchmark_sha256=binding.benchmark_sha256,
        source_result_id="fixture-result",
        operation_id=selector.operation_id,
        operation_sha256="sha256:" + ("9" * 64),
        ledger_operation_sha256=marker.operation_sha256,
        snapshot_id=selector.snapshot_id,
        snapshot_sha256=availability.snapshot_sha256,
        availability_receipt_sha256=availability.receipt_sha256,
        availability_base_receipt_sha256=availability.base_receipt_sha256,
        persisted_at=availability.persisted_at,
        available_at=availability.available_at,
        ledger_marker_sha256=marker.marker_sha256,
        ledger_fill_batch_sha256=marker.fill_batch_sha256,
        rowset_hash_before=marker.expected_rowset_hash,
        rowset_hash_after=marker.rowset_hash_after,
        ordered_fill_ids=fill_ids,
        source_event_ids=event_ids,
        transition_id=marker.transition_id,
        transition_sha256=marker.transition_sha256,
    )
    metric_names = (
        "period_return",
        "net_return",
        "cagr",
        "max_drawdown",
        "win_rate",
    )
    metrics = tuple(
        (
            name,
            MetricCell(
                value=metric_value,
                unit="not_available_from_single_checkpoint",
                reason="single_checkpoint_has_no_public_source_availability_or_period_curve",
                source_key=None,
            ),
        )
        for name in metric_names
    )
    positions = (
        PaperPositionRead(
            stock_code="2330",
            quantity=1,
            mark_price=Decimal("1000.50"),
            market_value=Decimal("1000.50"),
            weight_bp=20,
        ),
    )
    return PaperCheckpointCard(
        account_status=AccountBindingStatus.READY,
        read_status=read_status,
        qualification=QualificationStatus.NOT_QUALIFIED,
        strategy_id=selector.strategy_id,
        strategy_version_id=selector.strategy_version_id,
        account_namespace=selector.account_namespace,
        operation_id=selector.operation_id,
        operation_sha256=(
            "sha256:" + ("9" * 64)
            if read_status is ReadStatus.VERIFIED
            else None
        ),
        snapshot_id=selector.snapshot_id,
        decision_cutoff=selector.decision_cutoff,
        binding=binding,
        decision_date="2026-10-13",
        cash=cash,
        nav=nav,
        positions=positions,
        fills=fills,
        zero_fill=zero_fill,
        ledger_marker=marker,
        availability=availability,
        row_provenance=provenance,
        source_availability_status=SourceAvailabilityStatus.UNVERIFIED,
        source_available_at=None,
        official_session=None,
        period_curve_status="unavailable",
        metrics=metrics,
        qualification_reasons=(
            "public_checkpoint_availability_is_not_underlying_source_availability",
            "official_session_and_market_source_clock_are_unverified",
            "period_curve_and_qualified_cost_window_are_unavailable",
            "read_verified_does_not_grant_performance_qualification",
        ),
        reason=reason,
    )


def test_account_and_ledger_operation_hashes_are_distinct_and_presented(app):
    widget = StrategyPerformanceWidget()
    selector = _selector()
    generation = widget.begin_selection(selector)
    card = _card(selector)

    assert card.operation_sha256 == "sha256:" + ("9" * 64)
    assert card.row_provenance is not None
    assert card.ledger_marker is not None
    assert card.row_provenance.operation_sha256 == card.operation_sha256
    assert (
        card.row_provenance.ledger_operation_sha256
        == card.ledger_marker.operation_sha256
    )
    assert card.operation_sha256 != card.ledger_marker.operation_sha256
    assert widget.present_card(generation, card)
    assert not widget.summary_group.isHidden()


@pytest.mark.parametrize(
    ("surface", "field_name"),
    (
        ("card", "operation_sha256"),
        ("provenance", "operation_sha256"),
        ("marker", "operation_sha256"),
        ("provenance", "ledger_operation_sha256"),
    ),
)
def test_operation_hash_domain_mismatch_blocks_card(app, surface: str, field_name: str):
    widget = StrategyPerformanceWidget()
    selector = _selector()
    generation = widget.begin_selection(selector)
    card = _card(selector)

    if surface == "card":
        card = replace(card, **{field_name: "sha256:" + ("a" * 64)})
    elif surface == "provenance":
        assert card.row_provenance is not None
        changed = replace(
            card.row_provenance, **{field_name: "sha256:" + ("a" * 64)}
        )
        card = replace(card, row_provenance=changed)
    else:
        assert card.ledger_marker is not None
        changed = replace(
            card.ledger_marker, **{field_name: "sha256:" + ("a" * 64)}
        )
        card = replace(card, ledger_marker=changed)

    assert not widget.present_card(generation, card)
    assert widget.summary_group.isHidden()
    assert "回傳資料與唯讀快照契約不一致。" in widget.reason_label.text()


@pytest.mark.parametrize(
    ("surface", "field_name"),
    (
        ("card", "operation_sha256"),
        ("provenance", "operation_sha256"),
        ("marker", "operation_sha256"),
        ("provenance", "ledger_operation_sha256"),
    ),
)
def test_malformed_operation_hash_blocks_card(app, surface: str, field_name: str):
    widget = StrategyPerformanceWidget()
    selector = _selector()
    generation = widget.begin_selection(selector)
    card = _card(selector)

    if surface == "card":
        card = replace(card, **{field_name: "not-a-sha256"})
    elif surface == "provenance":
        assert card.row_provenance is not None
        changed = replace(card.row_provenance, **{field_name: "not-a-sha256"})
        card = replace(card, row_provenance=changed)
    else:
        assert card.ledger_marker is not None
        changed = replace(card.ledger_marker, **{field_name: "not-a-sha256"})
        card = replace(card, ledger_marker=changed)

    assert not widget.present_card(generation, card)
    assert widget.summary_group.isHidden()


@pytest.mark.parametrize(
    ("surface", "field_name"),
    (
        ("card", "operation_sha256"),
        ("provenance", "operation_sha256"),
        ("marker", "operation_sha256"),
        ("provenance", "ledger_operation_sha256"),
    ),
)
def test_missing_operation_hash_blocks_card(app, surface: str, field_name: str):
    widget = StrategyPerformanceWidget()
    selector = _selector()
    generation = widget.begin_selection(selector)
    card = _card(selector)

    if surface == "card":
        card = replace(card, **{field_name: None})
    elif surface == "provenance":
        assert card.row_provenance is not None
        changed = replace(card.row_provenance, **{field_name: None})
        card = replace(card, row_provenance=changed)
    else:
        assert card.ledger_marker is not None
        changed = replace(card.ledger_marker, **{field_name: None})
        card = replace(card, ledger_marker=changed)

    assert not widget.present_card(generation, card)
    assert widget.summary_group.isHidden()


def test_no_selection_clear_and_late_previous_generation_are_isolated(app):
    widget = StrategyPerformanceWidget()
    assert "尚未選取" in widget.status_label.text()
    assert widget.summary_group.isHidden()
    selector_a = _selector("A")
    generation_a = widget.begin_selection(selector_a)
    assert widget.present_card(generation_a, _card(selector_a))
    assert not widget.summary_group.isHidden()

    selector_b = _selector("B")
    generation_b = widget.begin_selection(selector_b)
    assert generation_b > generation_a
    assert widget.summary_group.isHidden()
    assert widget.nav_value.text() == ""
    assert widget.cash_value.text() == ""
    assert widget.source_label.text() == "來源策略：strategy-B｜版本：version-B"
    assert "等待" in widget.status_label.text()
    assert not widget.present_card(generation_a, _card(selector_a))
    assert widget.source_label.text() == "來源策略：strategy-B｜版本：version-B"
    assert widget.summary_group.isHidden()
    assert widget.nav_value.text() == ""
    assert widget.cash_value.text() == ""
    card_b = _card(
        selector_b,
        cash=Decimal("499020.487654321"),
        nav=Decimal("500020.987654321"),
    )
    assert widget.present_card(generation_b, card_b)
    assert widget.nav_value.text() == "500020.987654321"
    assert widget.cash_value.text() == "499020.487654321"
    assert "strategy-B" in widget.details_label.text()
    assert "fill-strategy-B" in widget.details_label.text()
    assert "strategy-A" not in widget.details_label.text()
    assert "fill-strategy-A" not in widget.details_label.text()
    assert "snapshot-A" not in widget.details_label.text()

    widget.clear_selection()
    assert widget.nav_value.text() == ""
    assert widget.summary_group.isHidden()
    assert "尚未選取" in widget.status_label.text()
    assert not widget.present_card(generation_b, _card(selector_b))


def test_verified_checkpoint_stays_unqualified_and_shows_exact_decimal(app):
    widget = StrategyPerformanceWidget()
    selector = _selector()
    generation = widget.begin_selection(selector)
    assert widget.present_card(generation, _card(selector))

    assert "研究帳戶快照已讀回" in widget.status_label.text()
    assert "未合格" in widget.status_label.text()
    assert "不是使用者的真實資產" in widget.account_notice_label.text()
    assert widget.nav_value.text() == "500000.987654321"
    assert widget.cash_value.text() == "499000.487654321"
    assert "未提供" in widget.metric_value.text()
    assert widget.metric_value.text().count("未提供") == 5
    assert "單一快照指標原因" in widget.details_label.text()
    assert "單一研究帳戶快照沒有來源可得性與完整期間曲線" in widget.details_label.text()
    assert "single_checkpoint_has_no_public_source_availability_or_period_curve" in widget.details_label.text()
    assert "已保存快照可讀，不代表底層資料來源的可得性已驗證。" in widget.details_label.text()
    assert "官方交易時段與市場來源時鐘尚未驗證。" in widget.details_label.text()
    assert "完整期間曲線與合格成本期間尚未提供。" in widget.details_label.text()
    assert "快照讀回驗證成功，不代表已取得績效合格資格。" in widget.details_label.text()
    assert "500000.987654321" not in widget.metric_value.text()
    assert "來源可得性：未驗證" in widget.details_label.text()
    assert "官方交易時段：未知" in widget.details_label.text()
    assert "完整期間曲線：不可用" in widget.details_label.text()


def test_low_decimal_precision_does_not_round_display(app):
    widget = StrategyPerformanceWidget()
    selector = _selector()
    generation = widget.begin_selection(selector)
    card = _card(
        selector,
        cash=Decimal("12345678901234567890.12345678901234567890"),
        nav=Decimal("98765432109876543210.98765432109876543210"),
    )
    with localcontext() as context:
        context.prec = 2
        assert widget.present_card(generation, card)
        assert widget.cash_value.text() == "12345678901234567890.12345678901234567890"
        assert widget.nav_value.text() == "98765432109876543210.98765432109876543210"


@pytest.mark.parametrize(
    ("field_name", "mismatched_value"),
    (
        ("strategy_id", "other-strategy"),
        ("strategy_version_id", "other-version"),
        ("account_namespace", "other-account"),
        ("operation_id", "other-operation"),
        ("snapshot_id", "other-snapshot"),
        (
            "decision_cutoff",
            datetime(2026, 10, 13, 9, 1, tzinfo=timezone.utc),
        ),
    ),
)
def test_each_identity_mismatch_blocks_and_clears_all_account_data(
    app, field_name: str, mismatched_value: object
):
    widget = StrategyPerformanceWidget()
    selector = _selector("selected")
    generation = widget.begin_selection(selector)
    assert widget.present_card(generation, _card(selector))

    mismatched = replace(_card(selector), **{field_name: mismatched_value})
    assert not widget.present_card(generation, mismatched)
    assert widget.summary_group.isHidden()
    assert widget.nav_value.text() == ""
    assert widget.cash_value.text() == ""
    assert widget.position_count_value.text() == ""
    assert widget.fill_count_value.text() == ""
    assert widget.zero_fill_value.text() == ""
    assert widget.metric_value.text() == ""
    assert widget.details_label.text() == (
        "策略識別：strategy-selected\n"
        "策略版本識別：version-selected\n"
        "研究帳戶命名空間：acct-selected\n"
        "操作識別：operation-selected\n"
        "已保存快照識別：snapshot-selected\n"
        "決策截止時間：2026-10-13T09:00:00+00:00"
    )
    assert "不相符" in widget.reason_label.text()


def test_equivalent_instant_with_different_cutoff_offset_is_not_same_identity(app):
    widget = StrategyPerformanceWidget()
    selector = _selector()
    generation = widget.begin_selection(selector)
    assert widget.present_card(generation, _card(selector))
    assert not widget.summary_group.isHidden()
    same_instant_other_offset = selector.decision_cutoff.astimezone(
        timezone(timedelta(hours=8))
    )
    alternate = replace(_card(selector), decision_cutoff=same_instant_other_offset)

    assert not widget.present_card(generation, alternate)
    assert widget.summary_group.isHidden()
    assert "不相符" in widget.reason_label.text()


def test_blocked_card_with_residual_data_never_displays_payload(app):
    widget = StrategyPerformanceWidget()
    selector = _selector()
    generation = widget.begin_selection(selector)
    positive = _card(selector)
    assert widget.present_card(generation, positive)
    widget.details_toggle.setChecked(True)
    assert not widget.details_label.isHidden()
    assert "2330" in widget.details_label.text()
    assert "fill-strategy-A" in widget.details_label.text()
    assert widget.nav_value.text() == "500000.987654321"
    assert widget.cash_value.text() == "499000.487654321"
    assert widget.zero_fill_value.text()
    residual = _card(
        selector,
        read_status=ReadStatus.BLOCKED,
        reason="exact_checkpoint_read_failed",
    )

    assert not widget.present_card(generation, residual)
    assert widget.summary_group.isHidden()
    assert widget.nav_value.text() == ""
    assert widget.cash_value.text() == ""
    assert widget.position_count_value.text() == ""
    assert widget.fill_count_value.text() == ""
    assert widget.zero_fill_value.text() == ""
    assert widget.metric_value.text() == ""
    assert "研究帳戶快照讀取失敗" in widget.reason_label.text()
    assert "exact_checkpoint_read_failed" not in widget.reason_label.text()
    assert "strategy-A" in widget.details_label.text()
    assert "snapshot-A" in widget.details_label.text()
    assert "2330" not in widget.details_label.text()
    assert "fill-strategy-A" not in widget.details_label.text()
    assert "500000.987654321" not in widget.details_label.text()
    assert widget.details_label.text() == (
        "策略識別：strategy-A\n"
        "策略版本識別：version-A\n"
        "研究帳戶命名空間：acct-A\n"
        "操作識別：operation-A\n"
        "已保存快照識別：snapshot-A\n"
        "決策截止時間：2026-10-13T09:00:00+00:00"
    )
    assert not widget.details_toggle.isChecked()


def test_caller_supplied_metric_value_is_rejected_not_rendered(app):
    widget = StrategyPerformanceWidget()
    selector = _selector()
    generation = widget.begin_selection(selector)
    invalid = _card(selector, metric_value=Decimal("0"))

    assert not widget.present_card(generation, invalid)
    assert widget.summary_group.isHidden()
    assert widget.metric_value.text() == ""
    assert "不一致" in widget.reason_label.text()


def test_unknown_metric_shape_status_and_nonfinite_decimal_are_blocked(app):
    widget = StrategyPerformanceWidget()
    selector = _selector()
    generation = widget.begin_selection(selector)
    valid = _card(selector)
    unknown_metrics = (("future_metric", valid.metrics[0][1]),) + valid.metrics[1:]
    malformed = replace(valid, metrics=unknown_metrics)

    assert not widget.present_card(generation, malformed)
    assert widget.summary_group.isHidden()
    assert widget.metric_value.text() == ""

    generation = widget.begin_selection(selector)
    unknown_status = replace(valid, read_status="verified")
    assert not widget.present_card(generation, unknown_status)
    assert widget.summary_group.isHidden()

    generation = widget.begin_selection(selector)
    nonfinite = replace(valid, cash=Decimal("NaN"))
    assert not widget.present_card(generation, nonfinite)
    assert widget.summary_group.isHidden()
    assert widget.cash_value.text() == ""


def test_unknown_reason_is_preserved_as_plain_text_in_details(app):
    widget = StrategyPerformanceWidget()
    selector = _selector()
    generation = widget.begin_selection(selector)
    valid = _card(selector)
    unknown = "future_reason_<b>literal</b>"
    card = replace(valid, qualification_reasons=(unknown,))

    assert widget.present_card(generation, card)
    assert unknown in widget.details_label.text()
    assert widget.details_label.textFormat() == Qt.TextFormat.PlainText


def test_zero_fill_is_not_presented_as_zero_return_and_labels_are_plain_text(app):
    widget = StrategyPerformanceWidget()
    selector = replace(_selector(), strategy_id="<b>研究策略</b>")
    generation = widget.begin_selection(selector)
    card = _card(selector, zero_fill=True)

    assert widget.present_card(generation, card)
    assert "明確記錄零成交" in widget.zero_fill_value.text()
    assert "不代表報酬為 0" in widget.zero_fill_value.text()
    assert "0%" not in widget.metric_value.text()
    assert "<b>研究策略</b>" in widget.source_label.text()
    assert all(
        label.textFormat() == Qt.TextFormat.PlainText
        for label in widget.findChildren(QLabel)
    )


def test_bool_generation_and_unknown_dto_fail_closed(app):
    widget = StrategyPerformanceWidget()
    selector = _selector()
    generation = widget.begin_selection(selector)

    assert not widget.present_card(cast(int, True), _card(selector))
    assert widget.summary_group.isHidden()
    assert not widget.present_card(generation, object())
    assert widget.summary_group.isHidden()
    assert "快照資料格式" in widget.reason_label.text()
