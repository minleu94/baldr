"""P08a 單一 Paper checkpoint 被動呈現候選（STATIC / NOT_RUN）。"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

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
from ui_qt.theme import MIDNIGHT_ANALYST


_SELECTOR_FIELDS = (
    "strategy_id",
    "strategy_version_id",
    "account_namespace",
    "operation_id",
    "snapshot_id",
    "decision_cutoff",
)
_CARD_FIELDS = (
    "account_status",
    "read_status",
    "qualification",
    "strategy_id",
    "strategy_version_id",
    "account_namespace",
    "operation_id",
    "operation_sha256",
    "snapshot_id",
    "decision_cutoff",
    "binding",
    "decision_date",
    "cash",
    "nav",
    "positions",
    "fills",
    "zero_fill",
    "ledger_marker",
    "availability",
    "row_provenance",
    "source_availability_status",
    "source_available_at",
    "official_session",
    "period_curve_status",
    "metrics",
    "qualification_reasons",
    "reason",
)
_BINDING_FIELDS = (
    "strategy_id",
    "strategy_version_id",
    "strategy_version",
    "strategy_artifact_sha256",
    "params_sha256",
    "config_sha256",
    "source_run_id",
    "account_namespace",
    "portfolio_id",
    "binding_sha256",
    "policy_id",
    "policy_version",
    "policy_sha256",
    "cost_model_id",
    "cost_model_version",
    "cost_model_sha256",
    "benchmark_id",
    "benchmark_version",
    "benchmark_sha256",
    "start_date",
    "initial_capital",
    "max_positions",
)
_POSITION_FIELDS = (
    "stock_code",
    "quantity",
    "mark_price",
    "market_value",
    "weight_bp",
)
_FILL_FIELDS = (
    "fill_id",
    "order_id",
    "portfolio_id",
    "event_date",
    "stock_code",
    "side",
    "requested_quantity",
    "filled_quantity",
    "reference_price",
    "fill_price",
    "commission",
    "tax",
    "slippage_cost",
    "turnover_bp",
    "execution_gap_bp",
    "status",
    "source_event_id",
    "override_reason",
    "source_type",
    "research_only",
    "broker_order_allowed",
    "auto_rebalance_allowed",
)
_MARKER_FIELDS = (
    "operation_id",
    "portfolio_id",
    "event_date",
    "expected_rowset_hash",
    "rowset_hash_after",
    "ordered_fill_ids",
    "fill_batch_sha256",
    "transition_id",
    "transition_sha256",
    "operation_sha256",
    "marker_sha256",
    "zero_fill",
)
_AVAILABILITY_FIELDS = (
    "schema_version",
    "operation_id",
    "snapshot_id",
    "portfolio_id",
    "account_namespace",
    "binding_sha256",
    "snapshot_sha256",
    "base_receipt_sha256",
    "persisted_at",
    "available_at",
    "receipt_sha256",
)
_PROVENANCE_FIELDS = (
    "strategy_id",
    "strategy_version_id",
    "account_namespace",
    "portfolio_id",
    "binding_sha256",
    "policy_id",
    "policy_version",
    "policy_sha256",
    "cost_model_id",
    "cost_model_version",
    "cost_model_sha256",
    "benchmark_id",
    "benchmark_version",
    "benchmark_sha256",
    "source_result_id",
    "operation_id",
    "operation_sha256",
    "ledger_operation_sha256",
    "snapshot_id",
    "snapshot_sha256",
    "availability_receipt_sha256",
    "availability_base_receipt_sha256",
    "persisted_at",
    "available_at",
    "ledger_marker_sha256",
    "ledger_fill_batch_sha256",
    "rowset_hash_before",
    "rowset_hash_after",
    "ordered_fill_ids",
    "source_event_ids",
    "transition_id",
    "transition_sha256",
)
_METRIC_FIELDS = ("value", "unit", "reason", "source_key")
_METRIC_NAMES = (
    "period_return",
    "net_return",
    "cagr",
    "max_drawdown",
    "win_rate",
)
_METRIC_LABELS = {
    "period_return": "期間報酬",
    "net_return": "淨報酬",
    "cagr": "年化報酬（CAGR）",
    "max_drawdown": "最大回撤",
    "win_rate": "勝率",
}
_REASON_LABELS = {
    "public_checkpoint_availability_is_not_underlying_source_availability": "已保存快照可讀，不代表底層資料來源的可得性已驗證。",
    "official_session_and_market_source_clock_are_unverified": "官方交易時段與市場來源時鐘尚未驗證。",
    "period_curve_and_qualified_cost_window_are_unavailable": "完整期間曲線與合格成本期間尚未提供。",
    "read_verified_does_not_grant_performance_qualification": "快照讀回驗證成功，不代表已取得績效合格資格。",
    "single_checkpoint_has_no_public_source_availability_or_period_curve": "單一研究帳戶快照沒有來源可得性與完整期間曲線，因此無法計算績效指標。",
    "single_checkpoint_has_no_period_curve": "只有單一研究帳戶快照，沒有完整期間曲線，因此無法計算績效指標。",
    "exact_checkpoint_read_failed": "研究帳戶快照讀取失敗，資料未呈現。",
}


def _plain_label(text: str = "", parent: QWidget | None = None) -> QLabel:
    label = QLabel(text, parent)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _has_exact_shape(value: Any, expected_type: type[Any], names: tuple[str, ...]) -> bool:
    if type(value) is not expected_type or not is_dataclass(value):
        return False
    return tuple(item.name for item in fields(value)) == names


def _text(value: Any, *, optional: bool = False, maximum: int = 4096) -> bool:
    if optional and value is None:
        return True
    return type(value) is str and bool(value.strip()) and len(value) <= maximum


def _sha256_hex(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _finite_decimal(value: Any, *, optional: bool = False) -> bool:
    if value is None:
        return optional
    return type(value) is Decimal and value.is_finite()


def _aware_datetime(value: Any) -> bool:
    return (
        type(value) is datetime
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _same_aware_datetime(left: Any, right: Any) -> bool:
    return (
        _aware_datetime(left)
        and _aware_datetime(right)
        and left == right
        and left.isoformat(timespec="microseconds")
        == right.isoformat(timespec="microseconds")
        and left.fold == right.fold
    )


def _selector_is_valid(value: Any) -> bool:
    if not _has_exact_shape(value, PaperCheckpointSelector, _SELECTOR_FIELDS):
        return False
    return all(_text(getattr(value, name)) for name in _SELECTOR_FIELDS[:-1]) and _aware_datetime(
        value.decision_cutoff
    )


def _safe_reason(value: Any, fallback: str) -> str:
    if _text(value, maximum=512):
        return value
    return fallback


def _reason_explanation(reason: str) -> str:
    return _REASON_LABELS.get(reason, reason)


def _reason_display(reason: str) -> str:
    explanation = _REASON_LABELS.get(reason)
    if explanation is None:
        return reason
    return f"{explanation}（診斷代碼：{reason}）"


def _validate_binding(binding: Any, selector: PaperCheckpointSelector) -> bool:
    if not _has_exact_shape(binding, AccountBindingRead, _BINDING_FIELDS):
        return False
    if not all(
        _text(getattr(binding, field_name))
        for field_name in _BINDING_FIELDS
        if field_name != "max_positions"
    ):
        return False
    if type(binding.max_positions) is not int:
        return False
    return (
        binding.strategy_id == selector.strategy_id
        and binding.strategy_version_id == selector.strategy_version_id
        and binding.account_namespace == selector.account_namespace
        and binding.portfolio_id == selector.account_namespace
    )


def _validate_position(value: Any) -> bool:
    return (
        _has_exact_shape(value, PaperPositionRead, _POSITION_FIELDS)
        and _text(value.stock_code)
        and type(value.quantity) is int
        and _finite_decimal(value.mark_price)
        and _finite_decimal(value.market_value)
        and type(value.weight_bp) is int
    )


def _validate_fill(value: Any) -> bool:
    if not _has_exact_shape(value, PaperFillRead, _FILL_FIELDS):
        return False
    text_fields = (
        "fill_id",
        "order_id",
        "portfolio_id",
        "event_date",
        "stock_code",
        "side",
        "status",
        "source_event_id",
        "source_type",
    )
    if not all(_text(getattr(value, name)) for name in text_fields):
        return False
    if not _text(value.override_reason, optional=True):
        return False
    if any(
        type(getattr(value, name)) is not int
        for name in ("requested_quantity", "filled_quantity")
    ):
        return False
    if any(
        not _finite_decimal(getattr(value, name))
        for name in ("reference_price", "commission", "tax", "slippage_cost")
    ) or not _finite_decimal(value.fill_price, optional=True):
        return False
    if any(
        getattr(value, name) is not None and type(getattr(value, name)) is not int
        for name in ("turnover_bp", "execution_gap_bp")
    ):
        return False
    return all(
        type(getattr(value, name)) is bool
        for name in ("research_only", "broker_order_allowed", "auto_rebalance_allowed")
    )


def _validate_metric_cells(value: Any) -> bool:
    if type(value) is not tuple or len(value) != len(_METRIC_NAMES):
        return False
    names: list[str] = []
    for pair in value:
        if type(pair) is not tuple or len(pair) != 2:
            return False
        name, cell = pair
        if type(name) is not str or not _has_exact_shape(cell, MetricCell, _METRIC_FIELDS):
            return False
        if cell.value is not None:
            return False
        if (
            type(cell.unit) is not str
            or cell.unit != "not_available_from_single_checkpoint"
        ):
            return False
        if not _text(cell.reason, maximum=512) or cell.source_key is not None:
            return False
        names.append(name)
    return tuple(names) == _METRIC_NAMES


def _validate_verified_card(
    card: PaperCheckpointCard, selector: PaperCheckpointSelector
) -> bool:
    if card.account_status is not AccountBindingStatus.READY:
        return False
    if card.qualification is not QualificationStatus.NOT_QUALIFIED:
        return False
    if card.reason is not None:
        return False
    if not _sha256_hex(card.operation_sha256):
        return False
    if not _text(card.decision_date):
        return False
    if not _finite_decimal(card.cash) or not _finite_decimal(card.nav):
        return False
    if not _validate_binding(cast(AccountBindingRead, card.binding), selector):
        return False
    if not _has_exact_shape(card.ledger_marker, LedgerMarkerRead, _MARKER_FIELDS):
        return False
    if not _has_exact_shape(
        card.availability, CheckpointAvailabilityRead, _AVAILABILITY_FIELDS
    ):
        return False
    if not _has_exact_shape(card.row_provenance, RowProvenance, _PROVENANCE_FIELDS):
        return False

    marker = cast(LedgerMarkerRead, card.ledger_marker)
    availability = cast(CheckpointAvailabilityRead, card.availability)
    provenance = cast(RowProvenance, card.row_provenance)
    binding = cast(AccountBindingRead, card.binding)
    if not all(
        _text(getattr(marker, field_name))
        for field_name in (
            "operation_id",
            "portfolio_id",
            "event_date",
            "expected_rowset_hash",
            "rowset_hash_after",
            "fill_batch_sha256",
            "operation_sha256",
            "marker_sha256",
        )
    ):
        return False
    if not _sha256_hex(marker.operation_sha256):
        return False
    if type(marker.ordered_fill_ids) is not tuple or not all(
        _text(item) for item in marker.ordered_fill_ids
    ):
        return False
    if type(marker.zero_fill) is not bool:
        return False
    if not _text(marker.transition_id, optional=True) or not _text(
        marker.transition_sha256, optional=True
    ):
        return False

    if not all(
        _text(getattr(availability, field_name))
        for field_name in (
            "schema_version",
            "operation_id",
            "snapshot_id",
            "portfolio_id",
            "account_namespace",
            "binding_sha256",
            "snapshot_sha256",
            "base_receipt_sha256",
            "receipt_sha256",
        )
    ) or not _aware_datetime(availability.persisted_at) or not _aware_datetime(
        availability.available_at
    ):
        return False

    if not all(
        _text(getattr(provenance, field_name))
        for field_name in (
            "strategy_id",
            "strategy_version_id",
            "account_namespace",
            "portfolio_id",
            "binding_sha256",
            "policy_id",
            "policy_version",
            "policy_sha256",
            "cost_model_id",
            "cost_model_version",
            "cost_model_sha256",
            "benchmark_id",
            "benchmark_version",
            "benchmark_sha256",
            "source_result_id",
            "operation_id",
            "operation_sha256",
            "ledger_operation_sha256",
            "snapshot_id",
            "snapshot_sha256",
            "availability_receipt_sha256",
            "availability_base_receipt_sha256",
            "ledger_marker_sha256",
            "ledger_fill_batch_sha256",
            "rowset_hash_before",
            "rowset_hash_after",
        )
    ):
        return False
    if not _sha256_hex(provenance.operation_sha256) or not _sha256_hex(
        provenance.ledger_operation_sha256
    ):
        return False
    if not _aware_datetime(provenance.persisted_at) or not _aware_datetime(
        provenance.available_at
    ):
        return False
    if type(provenance.ordered_fill_ids) is not tuple or not all(
        _text(item) for item in provenance.ordered_fill_ids
    ):
        return False
    if type(provenance.source_event_ids) is not tuple or not all(
        _text(item) for item in provenance.source_event_ids
    ):
        return False
    if not _text(provenance.transition_id, optional=True) or not _text(
        provenance.transition_sha256, optional=True
    ):
        return False

    if type(card.positions) is not tuple or not all(
        _validate_position(item) for item in card.positions
    ):
        return False
    if type(card.fills) is not tuple or not all(_validate_fill(item) for item in card.fills):
        return False
    if any(item.portfolio_id != binding.portfolio_id for item in card.fills):
        return False
    if type(card.zero_fill) is not bool or card.zero_fill is not marker.zero_fill:
        return False
    fill_ids = tuple(item.fill_id for item in card.fills)
    event_ids = tuple(item.source_event_id for item in card.fills)
    if fill_ids != marker.ordered_fill_ids or fill_ids != provenance.ordered_fill_ids:
        return False
    if event_ids != provenance.source_event_ids:
        return False
    if card.zero_fill is not (len(card.fills) == 0):
        return False

    if type(card.source_availability_status) is not SourceAvailabilityStatus:
        return False
    if card.source_availability_status is not SourceAvailabilityStatus.UNVERIFIED:
        return False
    if card.source_available_at is not None or card.official_session is not None:
        return False
    if (
        type(card.period_curve_status) is not str
        or card.period_curve_status != "unavailable"
    ):
        return False
    if not _validate_metric_cells(card.metrics):
        return False
    if type(card.qualification_reasons) is not tuple or not card.qualification_reasons:
        return False
    if not all(_text(item, maximum=512) for item in card.qualification_reasons):
        return False

    identity_match = (
        card.strategy_id == selector.strategy_id
        and card.strategy_version_id == selector.strategy_version_id
        and card.account_namespace == selector.account_namespace
        and card.operation_id == selector.operation_id
        and card.snapshot_id == selector.snapshot_id
        and _same_aware_datetime(card.decision_cutoff, selector.decision_cutoff)
    )
    lineage_match = (
        marker.operation_id == selector.operation_id
        and marker.portfolio_id == binding.portfolio_id
        and availability.operation_id == selector.operation_id
        and availability.snapshot_id == selector.snapshot_id
        and availability.portfolio_id == binding.portfolio_id
        and availability.account_namespace == selector.account_namespace
        and availability.binding_sha256 == binding.binding_sha256
        and provenance.strategy_id == selector.strategy_id
        and provenance.strategy_version_id == selector.strategy_version_id
        and provenance.account_namespace == selector.account_namespace
        and provenance.portfolio_id == binding.portfolio_id
        and provenance.binding_sha256 == binding.binding_sha256
        and provenance.policy_id == binding.policy_id
        and provenance.policy_version == binding.policy_version
        and provenance.policy_sha256 == binding.policy_sha256
        and provenance.cost_model_id == binding.cost_model_id
        and provenance.cost_model_version == binding.cost_model_version
        and provenance.cost_model_sha256 == binding.cost_model_sha256
        and provenance.benchmark_id == binding.benchmark_id
        and provenance.benchmark_version == binding.benchmark_version
        and provenance.benchmark_sha256 == binding.benchmark_sha256
        and provenance.operation_id == selector.operation_id
        and provenance.operation_sha256 == card.operation_sha256
        and provenance.ledger_operation_sha256 == marker.operation_sha256
        and provenance.snapshot_id == selector.snapshot_id
        and provenance.snapshot_sha256 == availability.snapshot_sha256
        and provenance.availability_receipt_sha256 == availability.receipt_sha256
        and provenance.availability_base_receipt_sha256 == availability.base_receipt_sha256
        and provenance.persisted_at == availability.persisted_at
        and provenance.available_at == availability.available_at
        and provenance.ledger_marker_sha256 == marker.marker_sha256
        and provenance.ledger_fill_batch_sha256 == marker.fill_batch_sha256
        and provenance.rowset_hash_before == marker.expected_rowset_hash
        and provenance.rowset_hash_after == marker.rowset_hash_after
        and provenance.transition_id == marker.transition_id
        and provenance.transition_sha256 == marker.transition_sha256
    )
    return identity_match and lineage_match


def _selector_summary(selector: PaperCheckpointSelector) -> str:
    return f"來源策略：{selector.strategy_id}｜版本：{selector.strategy_version_id}"


def _selector_details(selector: PaperCheckpointSelector) -> str:
    return (
        f"策略識別：{selector.strategy_id}\n"
        f"策略版本識別：{selector.strategy_version_id}\n"
        f"研究帳戶命名空間：{selector.account_namespace}\n"
        f"操作識別：{selector.operation_id}\n"
        f"已保存快照識別：{selector.snapshot_id}\n"
        f"決策截止時間：{selector.decision_cutoff.isoformat()}"
    )


class StrategyPerformanceWidget(QGroupBox):
    """只呈現呼叫端傳入的 exact Paper checkpoint，不自行讀取或計算。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("研究帳戶快照｜單筆保存資料", parent)
        self._generation = 0
        self._selector: PaperCheckpointSelector | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        self.account_notice_label = _plain_label(
            "研究帳戶；顯示資金不是使用者的真實資產。", self
        )
        self.account_notice_label.setAccessibleName("研究帳戶資金說明")
        self.account_notice_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.warning}; background: {MIDNIGHT_ANALYST.surface_2}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; border-radius: 6px; padding: 7px;"
        )
        layout.addWidget(self.account_notice_label)

        self.status_label = _plain_label("尚未選取研究帳戶快照。", self)
        self.status_label.setAccessibleName("策略研究帳戶讀取狀態")
        layout.addWidget(self.status_label)

        self.source_label = _plain_label("尚未選取來源。", self)
        self.source_label.setAccessibleName("目前選取來源")
        layout.addWidget(self.source_label)

        self.reason_label = _plain_label("", self)
        self.reason_label.setAccessibleName("阻擋原因")
        self.reason_label.setStyleSheet(f"color: {MIDNIGHT_ANALYST.warning};")
        self.reason_label.setVisible(False)
        layout.addWidget(self.reason_label)

        self.summary_group = QGroupBox("已保存研究帳戶快照", self)
        form = QFormLayout(self.summary_group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.decision_date_value = _plain_label(parent=self.summary_group)
        self.nav_value = _plain_label(parent=self.summary_group)
        self.cash_value = _plain_label(parent=self.summary_group)
        self.position_count_value = _plain_label(parent=self.summary_group)
        self.fill_count_value = _plain_label(parent=self.summary_group)
        self.zero_fill_value = _plain_label(parent=self.summary_group)
        self.metric_value = _plain_label(parent=self.summary_group)
        self.decision_date_value.setAccessibleName("決策日期")
        self.nav_value.setAccessibleName("研究帳戶淨值")
        self.cash_value.setAccessibleName("研究帳戶現金")
        self.position_count_value.setAccessibleName("持倉筆數")
        self.fill_count_value.setAccessibleName("成交筆數")
        self.zero_fill_value.setAccessibleName("零成交狀態")
        self.metric_value.setAccessibleName("未合格績效指標")
        for title, value_label in (
            ("決策日期", self.decision_date_value),
            ("淨值 NAV", self.nav_value),
            ("現金", self.cash_value),
            ("持倉列數", self.position_count_value),
            ("成交列數", self.fill_count_value),
            ("成交狀態", self.zero_fill_value),
            ("績效指標", self.metric_value),
        ):
            row = QWidget(self.summary_group)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 2, 0, 2)
            title_label = _plain_label(title, row)
            title_label.setMinimumWidth(92)
            row_layout.addWidget(title_label)
            row_layout.addWidget(value_label, 1)
            form.addRow(row)
        self.summary_group.setVisible(False)
        layout.addWidget(self.summary_group)

        self.details_toggle = QToolButton(self)
        self.details_toggle.setText("展開來源與快照明細")
        self.details_toggle.setCheckable(True)
        self.details_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.details_toggle.setAccessibleName("切換來源與快照明細")
        self.details_toggle.toggled.connect(self._set_details_visible)
        self.details_toggle.setVisible(False)
        layout.addWidget(self.details_toggle)

        self.details_label = _plain_label(parent=self)
        self.details_label.setAccessibleName("來源與快照明細")
        self.details_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; background: {MIDNIGHT_ANALYST.surface_1}; "
            f"border: 1px solid {MIDNIGHT_ANALYST.border}; border-radius: 6px; padding: 8px;"
        )
        self.details_label.setVisible(False)
        layout.addWidget(self.details_label)

    @property
    def generation(self) -> int:
        return self._generation

    def begin_selection(self, selector: PaperCheckpointSelector) -> int:
        """開始一次明確選取並先清除所有舊卡資料。"""

        self._generation += 1
        generation = self._generation
        self._selector = None
        self._clear_card_data()
        self.reason_label.setText("")
        self.reason_label.setVisible(False)
        self.details_toggle.setChecked(False)
        self.details_toggle.setVisible(False)
        if not _selector_is_valid(selector):
            self.source_label.setText("來源無法識別。")
            self.status_label.setText("選取資料格式不符合唯讀快照契約。")
            self.reason_label.setText("無法安全呈現此研究帳戶快照。")
            self.reason_label.setVisible(True)
            return generation

        self._selector = selector
        self.source_label.setText(_selector_summary(selector))
        self.status_label.setText("等待目前選取來源的已保存快照讀回。")
        self.details_label.setText(_selector_details(selector))
        self.details_toggle.setVisible(True)
        return generation

    def clear_selection(self) -> int:
        """清除選取並使所有在途 generation 失效。"""

        self._generation += 1
        self._selector = None
        self._clear_card_data()
        self.status_label.setText("尚未選取研究帳戶快照。")
        self.source_label.setText("尚未選取來源。")
        self.reason_label.setText("")
        self.reason_label.setVisible(False)
        self.details_label.setText("")
        self.details_toggle.setChecked(False)
        self.details_toggle.setVisible(False)
        return self._generation

    def present_card(self, generation: int, card: PaperCheckpointCard) -> bool:
        """只接受當前 generation 且與選取身份完全一致的回覆。"""

        if type(generation) is not int or generation != self._generation:
            return False
        selector = self._selector
        if selector is None:
            return False
        if not _has_exact_shape(card, PaperCheckpointCard, _CARD_FIELDS):
            self._block_current("回傳資料不是已知的快照資料格式。")
            return False
        if not all(
            _text(getattr(card, field_name))
            for field_name in (
                "strategy_id",
                "strategy_version_id",
                "account_namespace",
                "operation_id",
                "snapshot_id",
            )
        ) or not _aware_datetime(card.decision_cutoff):
            self._block_current("回傳快照身份欄位格式未知。")
            return False

        if not (
            card.strategy_id == selector.strategy_id
            and card.strategy_version_id == selector.strategy_version_id
            and card.account_namespace == selector.account_namespace
            and card.operation_id == selector.operation_id
            and card.snapshot_id == selector.snapshot_id
            and _same_aware_datetime(card.decision_cutoff, selector.decision_cutoff)
        ):
            self._block_current("回傳來源與目前選取的六項身份不相符。")
            return False

        if type(card.read_status) is not ReadStatus:
            self._block_current("回傳快照狀態未知，資料已清除。")
            return False
        if card.read_status is ReadStatus.BLOCKED:
            self._block_current(_safe_reason(card.reason, "快照讀取遭阻擋。"))
            return False
        if card.read_status is not ReadStatus.VERIFIED:
            self._block_current("回傳快照狀態未知，資料已清除。")
            return False
        if not _validate_verified_card(card, selector):
            self._block_current("回傳資料與唯讀快照契約不一致。")
            return False

        self._render_verified_card(card, selector)
        return True

    def _block_current(self, reason: str) -> None:
        selector = self._selector
        self._clear_card_data()
        self.status_label.setText("此研究帳戶快照讀取遭阻擋，帳戶資料未呈現。")
        self.source_label.setText(
            _selector_summary(selector) if selector is not None else "來源無法識別。"
        )
        self.reason_label.setText(
            _reason_explanation(_safe_reason(reason, "無法安全呈現此快照。"))
        )
        self.reason_label.setVisible(True)
        self.details_toggle.setChecked(False)
        self.details_toggle.setVisible(selector is not None)
        self.details_label.setText(_selector_details(selector) if selector is not None else "")

    def _clear_card_data(self) -> None:
        self.summary_group.setVisible(False)
        for label in (
            self.decision_date_value,
            self.nav_value,
            self.cash_value,
            self.position_count_value,
            self.fill_count_value,
            self.zero_fill_value,
            self.metric_value,
        ):
            label.setText("")
        self.details_label.setText("")

    def _render_verified_card(
        self, card: PaperCheckpointCard, selector: PaperCheckpointSelector
    ) -> None:
        metric_lines = [
            f"{_METRIC_LABELS[name]}：未提供"
            for name, cell in card.metrics
        ]
        if card.zero_fill:
            zero_fill_text = "此快照明確記錄零成交；這不代表報酬為 0。"
        else:
            zero_fill_text = "此快照有成交記錄。"

        detail_lines = [
            _selector_details(selector),
            "",
            "來源可得性：未驗證",
            "官方交易時段：未知",
            "完整期間曲線：不可用",
            "績效資格：未合格",
            "資格說明：",
            *[f"- {_reason_display(item)}" for item in card.qualification_reasons],
            "",
            "單一快照指標原因：",
            *[
                f"- {_METRIC_LABELS[name]}：{_reason_display(cast(str, cell.reason))}"
                for name, cell in card.metrics
            ],
            "",
            "持倉明細：",
        ]
        if card.positions:
            detail_lines.extend(
                f"- {item.stock_code}｜股數 {item.quantity}｜估值 {format(item.market_value, 'f')}｜"
                f"參考價 {format(item.mark_price, 'f')}｜權重 bp {item.weight_bp}"
                for item in card.positions
            )
        else:
            detail_lines.append("- 此快照沒有持倉列。")
        detail_lines.append("成交明細：")
        if card.fills:
            detail_lines.extend(
                f"- {item.event_date}｜{item.stock_code}｜{item.side}｜委託股數 {item.requested_quantity}｜"
                f"成交股數 {item.filled_quantity}｜參考價 {format(item.reference_price, 'f')}｜"
                f"成交價 {format(item.fill_price, 'f') if item.fill_price is not None else '未知'}｜"
                f"佣金 {format(item.commission, 'f')}｜稅額 {format(item.tax, 'f')}｜"
                f"滑價成本 {format(item.slippage_cost, 'f')}｜成交識別 {item.fill_id}｜"
                f"來源事件 {item.source_event_id}"
                for item in card.fills
            )
        else:
            detail_lines.append("- 無成交列。")

        self.source_label.setText(_selector_summary(selector))
        self.status_label.setText("研究帳戶快照已讀回；績效資格尚未合格。")
        self.reason_label.setText("")
        self.reason_label.setVisible(False)
        self.decision_date_value.setText(card.decision_date or "未知")
        self.nav_value.setText(format(cast(Decimal, card.nav), "f"))
        self.cash_value.setText(format(cast(Decimal, card.cash), "f"))
        self.position_count_value.setText(str(len(card.positions)))
        self.fill_count_value.setText(str(len(card.fills)))
        self.zero_fill_value.setText(zero_fill_text)
        self.metric_value.setText("\n".join(metric_lines))
        self.details_label.setText("\n".join(detail_lines))
        self.summary_group.setVisible(True)
        self.details_toggle.setVisible(True)

    def _set_details_visible(self, visible: bool) -> None:
        self.details_label.setVisible(visible)
        self.details_toggle.setArrowType(
            Qt.ArrowType.DownArrow if visible else Qt.ArrowType.RightArrow
        )
        self.details_toggle.setText(
            "收合來源與快照明細" if visible else "展開來源與快照明細"
        )
