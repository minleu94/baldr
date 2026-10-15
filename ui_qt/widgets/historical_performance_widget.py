"""只呈現已驗證的歷史 Registry DTO；不讀取資料或計算績效。"""

from __future__ import annotations

from dataclasses import fields
from decimal import Decimal
import hashlib
import json
import math
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QToolButton, QVBoxLayout, QWidget

from app_module.research_history_lookup import REGISTRY_RESULT_TYPES, ResearchHistoryEntry
from app_module.strategy_historical_performance_read_service import (
    HistoricalComparabilityState,
    HistoricalMetricsState,
    HistoricalPerformanceSummary,
    HistoricalQualificationState,
    HistoricalReadState,
    HistoricalRunCard,
    HistoricalRunDetails,
    HistoricalRunIdentity,
    HistoricalRunProvenance,
    HistoricalTableReference,
)
from app_module.single_backtest_metrics_contract import (
    SINGLE_BACKTEST_METRICS_KEY,
    decode_single_backtest_metrics_contract,
)


_SUMMARY_LABELS = (
    ("stock_count", "股票數"),
    ("signal_count", "訊號數"),
    ("completed_trades", "已完成交易"),
    ("average_trade_return", "平均單筆報酬"),
    ("total_return", "總報酬"),
    ("annual_return", "年化報酬"),
    ("cagr", "CAGR"),
    ("max_drawdown", "最大回撤"),
    ("win_rate", "勝率"),
    ("sharpe_ratio", "Sharpe"),
    ("expectancy", "期望值"),
    ("profit_factor", "獲利因子"),
)
_MAX_METADATA_DISPLAY_BYTES = 64 * 1024
_MAX_PREVIEW_ROWS = 20
_MAX_PREVIEW_COLUMNS = 32
_MAX_TEXT = 512
_METRICS_REASON = "historical_metrics_schema_unversioned"
_DECLARED_METRICS_REASON = "saved_original_analytics_not_performance_qualification"
_METADATA_KEYS = frozenset(
    {
        "run_id",
        "run_name",
        "run_type",
        "strategy_id",
        "strategy_version",
        "parameter_contract_version",
        "original_input",
        "normalized_params",
        "fallback_reason",
        "universe",
        "start_date",
        "end_date",
        "data_cutoff_date",
        "data_fingerprint",
        "fingerprint_algorithm",
        "data_manifest",
        "capital_cents",
        "fee_bp_x100",
        "slippage_bp_x100",
        "stop_loss_bp",
        "take_profit_bp",
        "execution_price",
        "sizing_mode",
        "metrics",
        "regime_breakdown",
        "benchmark_results",
        "payload_hash",
        "equity_path",
        "equity_parquet_hash",
        "trades_path",
        "trades_parquet_hash",
        "is_archived",
        "promoted_version_id",
        "promotion_reconciliation_status",
        "created_at",
    }
)


def _plain_label(text: str = "", parent: QWidget | None = None) -> QLabel:
    label = QLabel(text, parent)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


def _bounded_display_text(value: object) -> str:
    """限制短欄位的可見字元數，不改動供驗證的來源值。"""
    text = "未提供" if value is None else str(value)
    if len(text) <= _MAX_TEXT:
        return text
    return text[: _MAX_TEXT - 1] + "…"


def _bounded_display_line(label: str, value: object) -> str:
    """連同固定標籤一起計算上限，截斷時明示省略號。"""
    value_text = "未提供" if value is None else str(value)
    return _bounded_display_text(f"{label}{value_text}")


def _is_sha256(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _is_artifact_sha256(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def _entry_is_valid(entry: object) -> bool:
    if type(entry) is not ResearchHistoryEntry:
        return False
    text_fields = (
        "source_kind",
        "run_type",
        "run_id",
        "run_name",
        "stock_code",
        "start_date",
        "end_date",
        "created_at",
        "metadata_json",
        "unsupported_reason",
    )
    if any(type(getattr(entry, name)) is not str for name in text_fields):
        return False
    if not entry.run_id or type(entry.result_supported) is not bool:
        return False
    return _is_sha256(entry.metadata_sha256) and _is_sha256(entry.context_sha256)


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate metadata object key")
        result[key] = value
    return result


def _parse_selected_metadata(entry: ResearchHistoryEntry) -> dict[str, object] | None:
    def reject_non_finite_constant(value: str) -> None:
        raise ValueError(f"non-finite metadata constant: {value}")

    try:
        metadata_bytes = entry.metadata_json.encode("utf-8")
        if hashlib.sha256(metadata_bytes).hexdigest() != entry.metadata_sha256:
            return None
        metadata = json.loads(
            entry.metadata_json,
            object_pairs_hook=_unique_json_object,
            parse_float=Decimal,
            parse_constant=reject_non_finite_constant,
        )
    except (RecursionError, TypeError, UnicodeEncodeError, ValueError):
        return None
    if type(metadata) is not dict or frozenset(metadata) != _METADATA_KEYS:
        return None
    try:
        if _contains_non_finite(metadata):
            return None
        # 標準 float 解析只用來驗 canonical_json 的序列化形狀，不供卡片欄位投影。
        canonical_value = json.loads(
            entry.metadata_json,
            object_pairs_hook=_unique_json_object,
            parse_constant=reject_non_finite_constant,
        )
        if _contains_non_finite(canonical_value):
            return None
        canonical_text = json.dumps(
            canonical_value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        if canonical_text != entry.metadata_json:
            return None
    except RecursionError:
        return None
    except (TypeError, ValueError):
        return None
    return metadata


def _metadata_payload_hash(metadata: dict[str, object]) -> str | None:
    payload_hash = metadata.get("payload_hash")
    if type(payload_hash) is not str or not payload_hash:
        return None
    return payload_hash


def _top_level_json_value_raw(text: str, target: str) -> str | None:
    def reject_non_finite_constant(value: str) -> None:
        raise ValueError(f"non-finite metadata constant: {value}")

    decoder = json.JSONDecoder(
        object_pairs_hook=_unique_json_object,
        parse_float=Decimal,
        parse_constant=reject_non_finite_constant,
    )

    def skip_space(position: int) -> int:
        while position < len(text) and text[position] in " \t\r\n":
            position += 1
        return position

    position = skip_space(0)
    if position >= len(text) or text[position] != "{":
        return None
    position += 1
    while True:
        position = skip_space(position)
        if position >= len(text) or text[position] == "}":
            return None
        key, position = decoder.raw_decode(text, position)
        if type(key) is not str:
            return None
        position = skip_space(position)
        if position >= len(text) or text[position] != ":":
            return None
        value_start = skip_space(position + 1)
        _, value_end = decoder.raw_decode(text, value_start)
        if key == target:
            return text[value_start:value_end]
        position = skip_space(value_end)
        if position >= len(text):
            return None
        if text[position] == ",":
            position += 1
            continue
        if text[position] == "}":
            return None
        return None


def _identity_matches_selected_metadata(
    entry: ResearchHistoryEntry,
    identity: HistoricalRunIdentity,
    metadata: dict[str, object],
) -> bool:
    string_fields = (
        "run_id",
        "run_name",
        "run_type",
        "strategy_id",
        "strategy_version",
        "start_date",
        "end_date",
        "data_cutoff_date",
        "data_fingerprint",
        "fingerprint_algorithm",
        "execution_price",
        "sizing_mode",
        "equity_parquet_hash",
        "trades_parquet_hash",
        "created_at",
    )
    if any(type(metadata.get(name)) is not str for name in string_fields):
        return False
    if type(metadata.get("universe")) is not list or type(metadata.get("data_manifest")) is not dict:
        return False
    integer_fields = ("capital_cents", "fee_bp_x100", "slippage_bp_x100")
    if any(type(metadata.get(name)) is not int for name in integer_fields):
        return False
    for name in ("stop_loss_bp", "take_profit_bp"):
        value = metadata.get(name)
        if value is not None and type(value) is not int:
            return False

    universe = metadata["universe"]
    assert type(universe) is list
    if any(type(value) is not str for value in universe):
        expected_universe: tuple[str, ...] | None = None
    else:
        expected_universe = tuple(universe)
    expected_universe_json = _top_level_json_value_raw(entry.metadata_json, "universe")
    if expected_universe_json is None:
        return False
    manifest = metadata["data_manifest"]
    assert type(manifest) is dict
    declared_contract = manifest.get("execution_contract")
    execution_price = metadata["execution_price"]
    assert type(execution_price) is str
    expected_contract = (
        str(declared_contract)
        if declared_contract
        else execution_price if ".v" in execution_price else "unversioned"
    )
    expected_entry_stock = universe[0] if len(universe) == 1 else ""
    if type(expected_entry_stock) is not str:
        return False
    if (
        entry.run_id != metadata["run_id"]
        or entry.run_name != metadata["run_name"]
        or entry.run_type != metadata["run_type"]
        or entry.start_date != metadata["start_date"]
        or entry.end_date != metadata["end_date"]
        or entry.created_at != metadata["created_at"]
        or entry.stock_code != expected_entry_stock
    ):
        return False

    expected_identity = {
        "source_kind": entry.source_kind,
        "run_type": metadata["run_type"],
        "run_id": metadata["run_id"],
        "run_name": metadata["run_name"],
        "strategy_id": metadata["strategy_id"],
        "strategy_version": metadata["strategy_version"],
        "universe": expected_universe,
        "universe_json": expected_universe_json,
        "start_date": metadata["start_date"],
        "end_date": metadata["end_date"],
        "data_cutoff_date": metadata["data_cutoff_date"],
        "data_fingerprint": metadata["data_fingerprint"],
        "fingerprint_algorithm": metadata["fingerprint_algorithm"],
        "capital_cents": metadata["capital_cents"],
        "fee_bp_x100": metadata["fee_bp_x100"],
        "slippage_bp_x100": metadata["slippage_bp_x100"],
        "stop_loss_bp": metadata["stop_loss_bp"],
        "take_profit_bp": metadata["take_profit_bp"],
        "execution_price": metadata["execution_price"],
        "execution_contract": expected_contract,
        "sizing_mode": metadata["sizing_mode"],
    }
    return all(getattr(identity, name) == value for name, value in expected_identity.items())


def _contains_non_finite(value: object) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, Decimal):
        return not value.is_finite()
    if isinstance(value, dict):
        return any(
            _contains_non_finite(key) or _contains_non_finite(item)
            for key, item in value.items()
        )
    if isinstance(value, (tuple, list)):
        return any(_contains_non_finite(item) for item in value)
    return False


def _bounded_table_is_valid(
    table: object,
    *,
    artifact_name: str,
    artifact_sha256: str,
) -> bool:
    if type(table) is not HistoricalTableReference:
        return False
    if table.artifact_name != artifact_name or table.artifact_sha256 != artifact_sha256:
        return False
    if type(table.row_count) is not int or table.row_count < 0:
        return False
    if type(table.column_count) is not int or table.column_count < 0:
        return False
    if type(table.columns) is not tuple or type(table.preview_rows) is not tuple:
        return False
    if len(table.columns) != min(table.column_count, _MAX_PREVIEW_COLUMNS):
        return False
    if len(table.preview_rows) != min(table.row_count, _MAX_PREVIEW_ROWS):
        return False
    if any(type(column) is not str or len(column) > _MAX_TEXT for column in table.columns):
        return False
    if any(type(row) is not tuple or len(row) != len(table.columns) for row in table.preview_rows):
        return False
    if any(
        type(cell) is not str or len(cell) > _MAX_TEXT
        for row in table.preview_rows
        for cell in row
    ):
        return False
    flags = (
        table.rows_truncated,
        table.columns_truncated,
        table.column_text_truncated,
        table.cell_text_truncated,
    )
    if any(type(flag) is not bool for flag in flags):
        return False
    if table.rows_truncated is not (table.row_count > _MAX_PREVIEW_ROWS):
        return False
    if table.columns_truncated is not (table.column_count > _MAX_PREVIEW_COLUMNS):
        return False
    if table.column_text_truncated and not any(
        len(column) == _MAX_TEXT and column.endswith("…") for column in table.columns
    ):
        return False
    if table.cell_text_truncated and not any(
        len(cell) == _MAX_TEXT and cell.endswith("…")
        for row in table.preview_rows
        for cell in row
    ):
        return False
    return True


def _validate_card(entry: ResearchHistoryEntry, card: object) -> str | None:
    if type(card) is not HistoricalRunCard:
        return "historical_card_type_invalid"
    if card.read_state is not HistoricalReadState.VERIFIED:
        return card.reason or "historical_read_not_verified"
    if (
        entry.source_kind != "registry"
        or entry.result_supported is not True
        or entry.run_type not in REGISTRY_RESULT_TYPES
    ):
        return "historical_entry_not_supported"
    if card.metrics_state is HistoricalMetricsState.UNVERSIONED:
        if card.metrics_reason != _METRICS_REASON:
            return "historical_metrics_reason_changed"
    elif card.metrics_state is HistoricalMetricsState.DECLARED:
        if card.metrics_reason != _DECLARED_METRICS_REASON:
            return "historical_metrics_reason_changed"
    else:
        return "historical_metrics_state_unsupported"
    if card.comparability_state is not HistoricalComparabilityState.NOT_ASSESSED:
        return "historical_comparability_state_unsupported"
    if card.qualification_state is not HistoricalQualificationState.UNKNOWN:
        return "historical_qualification_state_unsupported"
    if type(card.summary) is not HistoricalPerformanceSummary:
        return "historical_summary_type_invalid"
    if (
        card.metrics_state is HistoricalMetricsState.UNVERSIONED
        and any(getattr(card.summary, item.name) is not None for item in fields(card.summary))
    ):
        return "historical_summary_contains_unversioned_values"
    if card.reason is not None:
        return "historical_verified_card_has_error_reason"
    if (
        type(card.identity) is not HistoricalRunIdentity
        or type(card.provenance) is not HistoricalRunProvenance
        or type(card.details) is not HistoricalRunDetails
    ):
        return "historical_card_payload_missing"
    metadata = _parse_selected_metadata(entry)
    if metadata is None:
        return "historical_selected_metadata_invalid_or_hash_changed"
    if card.metrics_state is HistoricalMetricsState.UNVERSIONED:
        manifest = metadata.get("data_manifest")
        if type(manifest) is not dict or SINGLE_BACKTEST_METRICS_KEY in manifest:
            return "historical_metrics_state_not_bound_to_selected_metadata"
    if card.metrics_state is HistoricalMetricsState.DECLARED:
        manifest = metadata.get("data_manifest")
        metrics = metadata.get("metrics")
        if type(manifest) is not dict or type(metrics) is not dict:
            return "historical_declared_metrics_metadata_invalid"
        try:
            declared_summary = decode_single_backtest_metrics_contract(
                manifest,
                metrics,
                run_type=entry.run_type,
                universe=metadata.get("universe"),
            )
        except (AttributeError, KeyError, RecursionError, TypeError, ValueError):
            return "historical_declared_metrics_contract_invalid"
        if declared_summary is None:
            return "historical_declared_metrics_contract_missing"
        if set(declared_summary) != {item.name for item in fields(card.summary)}:
            return "historical_declared_metrics_summary_shape_invalid"
        # DTO 必須逐欄保持 decoder 的型別和值，避免 bool/int 相等或卡片被單獨改寫。
        if any(
            type(getattr(card.summary, name)) is not type(value)
            or getattr(card.summary, name) != value
            for name, value in declared_summary.items()
        ):
            return "historical_summary_not_bound_to_saved_metrics"

    identity = card.identity
    identity_entry_fields = (
        ("source_kind", entry.source_kind),
        ("run_type", entry.run_type),
        ("run_id", entry.run_id),
        ("run_name", entry.run_name),
        ("start_date", entry.start_date),
        ("end_date", entry.end_date),
    )
    if any(type(getattr(identity, name)) is not str or getattr(identity, name) != expected for name, expected in identity_entry_fields):
        return "historical_identity_changed"
    identity_text_fields = (
        "strategy_id",
        "strategy_version",
        "universe_json",
        "data_cutoff_date",
        "data_fingerprint",
        "fingerprint_algorithm",
        "execution_price",
        "execution_contract",
        "sizing_mode",
    )
    if any(type(getattr(identity, name)) is not str for name in identity_text_fields):
        return "historical_identity_shape_invalid"
    if identity.universe is not None and (
        type(identity.universe) is not tuple
        or any(type(value) is not str for value in identity.universe)
    ):
        return "historical_universe_shape_invalid"
    for name in ("capital_cents", "fee_bp_x100", "slippage_bp_x100"):
        if type(getattr(identity, name)) is not int:
            return "historical_integer_units_invalid"
    for name in ("stop_loss_bp", "take_profit_bp"):
        value = getattr(identity, name)
        if value is not None and type(value) is not int:
            return "historical_optional_cost_invalid"
    try:
        if not _identity_matches_selected_metadata(entry, identity, metadata):
            return "historical_identity_not_bound_to_selected_metadata"
    except (RecursionError, TypeError, ValueError):
        return "historical_identity_not_bound_to_selected_metadata"

    provenance = card.provenance
    if (
        provenance.source_kind != entry.source_kind
        or provenance.metadata_sha256 != entry.metadata_sha256
        or provenance.context_sha256 != entry.context_sha256
        or provenance.integrity_state != "verified_by_exact_registry_read"
    ):
        return "historical_provenance_changed"
    if not _is_sha256(provenance.metadata_sha256) or not _is_sha256(provenance.context_sha256):
        return "historical_provenance_hash_invalid"
    if not _is_artifact_sha256(provenance.equity_parquet_sha256) or not _is_artifact_sha256(provenance.trades_parquet_sha256):
        return "historical_artifact_hash_invalid"
    if (
        provenance.equity_parquet_sha256 != metadata["equity_parquet_hash"]
        or provenance.trades_parquet_sha256 != metadata["trades_parquet_hash"]
    ):
        return "historical_artifact_hash_not_bound_to_selected_metadata"
    expected_payload_hash = _metadata_payload_hash(metadata)
    if expected_payload_hash is None or provenance.payload_hash != expected_payload_hash:
        return "historical_payload_hash_not_bound_to_selected_metadata"

    details = card.details
    if details.metadata_json_sha256 != entry.metadata_sha256:
        return "historical_metadata_detail_hash_changed"
    if type(details.metadata_json_byte_length) is not int or details.metadata_json_byte_length < 0:
        return "historical_metadata_detail_length_invalid"
    try:
        metadata_bytes = entry.metadata_json.encode("utf-8")
    except UnicodeEncodeError:
        return "historical_metadata_detail_encoding_invalid"
    if details.metadata_json_byte_length != len(metadata_bytes):
        return "historical_metadata_detail_length_changed"
    if len(metadata_bytes) <= _MAX_METADATA_DISPLAY_BYTES:
        if (
            details.metadata_json_state != "available_exact_saved_metadata"
            or details.metadata_json != entry.metadata_json
        ):
            return "historical_metadata_detail_changed"
    elif (
        details.metadata_json_state != "omitted_above_display_bound"
        or details.metadata_json is not None
    ):
        return "historical_metadata_display_bound_changed"
    if not _bounded_table_is_valid(
        details.equity,
        artifact_name="equity",
        artifact_sha256=provenance.equity_parquet_sha256,
    ):
        return "historical_equity_preview_invalid"
    if not _bounded_table_is_valid(
        details.trades,
        artifact_name="trades",
        artifact_sha256=provenance.trades_parquet_sha256,
    ):
        return "historical_trades_preview_invalid"
    return None


def _table_text(label: str, table: HistoricalTableReference) -> str:
    lines = [
        _bounded_display_line(f"{label}：SHA-256 ", table.artifact_sha256),
        _bounded_display_line("原始列數 ", f"{table.row_count}，欄數 {table.column_count}"),
        _bounded_display_line(
            "列截斷 ",
            f"{table.rows_truncated}；欄截斷 {table.columns_truncated}；"
            f"欄名文字截斷 {table.column_text_truncated}；儲存格文字截斷 {table.cell_text_truncated}",
        ),
    ]
    # 欄名和儲存格各自已受 512 字元守衛；保留原 20×32 預覽形狀。
    lines.append("欄名：" + " | ".join(table.columns))
    lines.extend(" | ".join(row) for row in table.preview_rows)
    return "\n".join(lines)


class HistoricalPerformanceWidget(QWidget):
    """接受 caller 已讀取的 DTO，執行 generation/identity 檢查後純文字呈現。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._generation = 0
        self._selected_entry: ResearchHistoryEntry | None = None
        layout = QVBoxLayout(self)
        self._selection_label = _plain_label(parent=self)
        self._status_label = _plain_label("未選擇歷史結果", self)
        self._identity_label = _plain_label(parent=self)
        self._metrics_label = _plain_label(parent=self)
        self._details_button = QToolButton(self)
        self._details_button.setText("展開原 metadata 與表格預覽")
        self._details_button.setCheckable(True)
        self._details_label = _plain_label(parent=self)
        self._details_label.setVisible(False)
        self._details_button.setVisible(False)
        self._details_button.toggled.connect(self._details_label.setVisible)
        for widget in (
            self._selection_label,
            self._status_label,
            self._identity_label,
            self._metrics_label,
            self._details_button,
            self._details_label,
        ):
            layout.addWidget(widget)

    @property
    def generation(self) -> int:
        return self._generation

    def begin_selection(self, entry: ResearchHistoryEntry) -> int:
        self._generation += 1
        self._selected_entry = None
        self._clear_card()
        if not _entry_is_valid(entry):
            self._selection_label.clear()
            self._status_label.setText("選取資料格式不完整；無法顯示歷史卡。")
            return self._generation
        self._selected_entry = entry
        selection_lines = (
            "目前選取：",
            _bounded_display_line("結果名稱：", entry.run_name),
            _bounded_display_line("結果類型：", entry.run_type),
            _bounded_display_line("Run ID：", entry.run_id),
        )
        self._selection_label.setText("\n".join(selection_lines))
        self._status_label.setText("等待此筆歷史結果的唯讀回覆。")
        return self._generation

    def clear_selection(self) -> int:
        self._generation += 1
        self._selected_entry = None
        self._selection_label.clear()
        self._clear_card()
        self._status_label.setText("未選擇歷史結果")
        return self._generation

    def present_card(
        self,
        generation: int,
        resolved_entry: ResearchHistoryEntry,
        card: HistoricalRunCard,
    ) -> bool:
        if type(generation) is not int or generation != self._generation:
            return False
        if (
            self._selected_entry is None
            or not _entry_is_valid(resolved_entry)
            or resolved_entry != self._selected_entry
        ):
            return self._reject("selected_entry_changed")
        reason = _validate_card(self._selected_entry, card)
        if reason is not None:
            return self._reject(reason)
        self._render(self._selected_entry, card)
        return True

    def _clear_card(self) -> None:
        self._identity_label.clear()
        self._metrics_label.clear()
        self._details_label.clear()
        self._details_button.setChecked(False)
        self._details_button.setVisible(False)
        self._details_label.setVisible(False)

    def _reject(self, reason: str) -> bool:
        self._clear_card()
        self._status_label.setText(_bounded_display_line("歷史卡已清除：", reason))
        return False

    def _render(self, entry: ResearchHistoryEntry, card: HistoricalRunCard) -> None:
        identity = card.identity
        provenance = card.provenance
        details = card.details
        assert identity is not None and provenance is not None and details is not None
        universe = identity.universe_json
        identity_lines = (
            "歷史研究結果（唯讀；不代表投資或績效資格）",
            _bounded_display_line("策略識別碼：", identity.strategy_id),
            _bounded_display_line("策略版本：", identity.strategy_version),
            _bounded_display_line("Run 名稱：", identity.run_name),
            _bounded_display_line("Run ID：", identity.run_id),
            _bounded_display_line("Run 類型：", identity.run_type),
            _bounded_display_line("來源種類：", identity.source_kind),
            _bounded_display_line("股票代碼：", entry.stock_code),
            _bounded_display_line("Universe JSON：", universe),
            _bounded_display_line(
                "回測請求開始日期：" if card.metrics_state is HistoricalMetricsState.DECLARED else "開始日期：",
                identity.start_date,
            ),
            _bounded_display_line(
                "回測請求結束日期：" if card.metrics_state is HistoricalMetricsState.DECLARED else "結束日期：",
                identity.end_date,
            ),
            _bounded_display_line("資料 cutoff：", identity.data_cutoff_date),
            _bounded_display_line("資料指紋：", identity.data_fingerprint),
            _bounded_display_line("指紋演算法：", identity.fingerprint_algorithm),
            _bounded_display_line("本金：", f"{identity.capital_cents} 分"),
            _bounded_display_line("手續費：", f"{identity.fee_bp_x100} bp×100"),
            _bounded_display_line("滑價：", f"{identity.slippage_bp_x100} bp×100"),
            _bounded_display_line(
                "停損：",
                None if identity.stop_loss_bp is None else f"{identity.stop_loss_bp} bp",
            ),
            _bounded_display_line(
                "停利：",
                None if identity.take_profit_bp is None else f"{identity.take_profit_bp} bp",
            ),
            _bounded_display_line("成交價：", identity.execution_price),
            _bounded_display_line("成交契約：", identity.execution_contract),
            _bounded_display_line("Sizing：", identity.sizing_mode),
        )
        if card.metrics_state is HistoricalMetricsState.UNVERSIONED:
            metrics_lines = [
                "績效指標未提供：原保存 metrics 沒有可驗證的共同 schema。",
                _bounded_display_line("指標狀態：", card.metrics_state.value),
                _bounded_display_line("指標原因：", card.metrics_reason),
                _bounded_display_line("資格：", card.qualification_state.value),
                _bounded_display_line("可比較性：", card.comparability_state.value),
            ]
            metrics_lines.extend(f"{label}：未提供" for _, label in _SUMMARY_LABELS)
        else:
            summary = card.summary
            saved_metadata = _parse_selected_metadata(entry)
            assert saved_metadata is not None
            saved_manifest = saved_metadata["data_manifest"]
            assert type(saved_manifest) is dict
            metrics_contract = saved_manifest[SINGLE_BACKTEST_METRICS_KEY]
            assert type(metrics_contract) is dict
            period_start = metrics_contract["period_start"]
            period_end = metrics_contract["period_end"]
            metrics_lines = [
                "以下為依已保存 schema 核對的原始 analytics；不是 Decimal 精度核心、合格績效或排名，不重算。",
                _bounded_display_line("原指標計算期間（manifest，不同於回測請求期間）：", (
                    f"{period_start or '未提供（原保存欄位為空）'} 至 "
                    f"{period_end or '未提供（原保存欄位為空）'}"
                )),
                _bounded_display_line("指標狀態：", card.metrics_state.value),
                _bounded_display_line("指標原因：", card.metrics_reason),
                _bounded_display_line("資格：", card.qualification_state.value),
                _bounded_display_line("可比較性：", card.comparability_state.value),
            ]
            completed_pairs = summary.completed_trades
            declared_metrics = (
                ("stock_count", "股票數（stocks）", "stocks"),
                ("signal_count", "訊號數（signals）", "signals"),
                ("completed_trades", "已完成交易配對（completed pairs）", "pairs"),
                ("average_trade_return", "平均單筆報酬", "ratio"),
                ("total_return", "總報酬", "ratio"),
                ("annual_return", "年化報酬", "ratio"),
                ("cagr", "CAGR", "ratio"),
                ("max_drawdown", "最大回撤", "ratio"),
                ("win_rate", "勝率", "ratio"),
                ("sharpe_ratio", "Sharpe", "sharpe"),
                ("expectancy", "期望值", "ratio"),
                ("profit_factor", "獲利因子", "multiple"),
            )
            for field_name, label, unit in declared_metrics:
                value = getattr(summary, field_name)
                if completed_pairs == 0 and field_name in {
                    "average_trade_return", "win_rate", "expectancy",
                }:
                    rendered_value = "未提供（尚無已完成交易）"
                elif value is None:
                    rendered_value = "未提供"
                elif unit == "ratio":
                    rendered_value = f"{value} ratio（轉為 % 數值需乘 100）"
                elif unit == "sharpe":
                    rendered_value = f"{value}（Sharpe ratio；非百分比）"
                elif unit == "multiple":
                    rendered_value = f"{value} 倍"
                elif unit == "stocks":
                    rendered_value = f"{value} 檔"
                elif unit == "signals":
                    rendered_value = f"{value} 個"
                elif unit == "pairs":
                    rendered_value = f"{value} 對"
                else:
                    rendered_value = f"{value}"
                metrics_lines.append(_bounded_display_line(f"{label}：", rendered_value))
        details_lines = [
            _bounded_display_line("Entry 建立時間：", entry.created_at),
            _bounded_display_line("Metadata SHA-256：", provenance.metadata_sha256),
            _bounded_display_line("Context SHA-256：", provenance.context_sha256),
            _bounded_display_line("Payload hash（原字串）：", provenance.payload_hash),
            _bounded_display_line("讀取完整性：", provenance.integrity_state),
            _bounded_display_line("Metadata 展示狀態：", details.metadata_json_state),
            _bounded_display_line("Metadata 原始 bytes：", details.metadata_json_byte_length),
            _bounded_display_line("Metadata SHA-256：", details.metadata_json_sha256),
        ]
        if details.metadata_json is not None:
            # 原始 JSON 是 64 KiB 詳情 blob，不套用短欄位顯示上限。
            details_lines.append("原始 Metadata JSON（PlainText）：\n" + details.metadata_json)
        details_lines.extend(
            (
                _table_text("Equity 預覽", details.equity),
                _table_text("Trades 預覽", details.trades),
            )
        )
        self._identity_label.setText("\n".join(identity_lines))
        self._metrics_label.setText("\n".join(metrics_lines))
        self._details_label.setText("\n\n".join(details_lines))
        self._details_button.setVisible(True)
        if card.metrics_state is HistoricalMetricsState.DECLARED:
            self._status_label.setText("已讀回此筆保存結果；原始 analytics schema 已核對，績效資格仍未知。")
        else:
            self._status_label.setText("已讀回此筆保存結果；績效指標仍未版本化。")

