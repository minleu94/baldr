"""策略登記與保存版本的唯讀瀏覽頁。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


def _plain(value: Any) -> str:
    """將來源欄位轉成純文字；缺值保留為明確未知。"""
    if value is None or value == "":
        return "未提供"
    if isinstance(value, (dict, list, tuple)):
        return repr(value)
    return str(value)


def _metadata_dict(value: Any) -> dict[str, Any] | None:
    """只讀取 StrategyMeta 或明確字典，不猜測其他物件欄位。"""
    converter = getattr(value, "to_dict", None)
    if callable(converter):
        try:
            value = converter()
        except Exception:
            return None
    return dict(value) if isinstance(value, dict) else None


def _semantic_version(meta: dict[str, Any] | None) -> str | None:
    if not meta:
        return None
    values = [meta[key] for key in ("strategy_version", "version") if key in meta]
    if not values or any(not isinstance(item, str) or not item or item != item.strip() for item in values):
        return None
    return values[0] if all(item == values[0] for item in values) else None


@dataclass(frozen=True)
class _VersionChoice:
    strategy_id: str
    version: str
    metadata: dict[str, Any] | None
    saved: dict[str, Any] | None

    @property
    def selectable(self) -> bool:
        return bool(
            self.metadata
            and self.metadata.get("strategy_id") == self.strategy_id
            and _semantic_version(self.metadata) == self.version
        )


class StrategyLibraryView(QWidget):
    """唯讀展示登記策略及已保存版本，明確選取才發送策略身分。"""

    strategySelected = Signal(str, str)

    def __init__(self, registry=None, version_service=None, parent=None, *,
                 can_apply: Callable[[str, str], bool] | None = None) -> None:
        super().__init__(parent)
        if registry is None:
            from decision_module.strategies.registry import StrategyRegistry

            registry = StrategyRegistry
        self._registry = registry
        self._version_service = version_service
        self._can_apply = can_apply
        self._strategies: dict[str, dict[str, Any]] = {}
        self._choices: list[_VersionChoice] = []
        self._selected_strategy_id: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        self.boundary_banner = QLabel(
            "策略庫只顯示登記說明與保存版本；資格、資料與成本以各來源實際提供欄位為準。"
        )
        self.boundary_banner.setWordWrap(True)
        root.addWidget(self.boundary_banner)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜尋策略名稱、ID 或說明")
        self.strategy_list = QListWidget()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("已登記策略｜家族欄位未提供時不推定分類"))
        left_layout.addWidget(self.search_edit)
        left_layout.addWidget(self.strategy_list, stretch=1)
        self.research_catalog_label = QLabel("待證研究策略目錄：未提供")
        self.research_catalog_label.setWordWrap(True)
        left_layout.addWidget(self.research_catalog_label)
        split.addWidget(left)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(4, 0, 0, 0)
        self.strategy_title = QLabel("請選擇已登記策略")
        self.strategy_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.strategy_title.setWordWrap(True)
        detail_layout.addWidget(self.strategy_title)
        self.version_combo = QComboBox()
        self.version_combo.setEnabled(False)
        detail_layout.addWidget(self.version_combo)
        self.details = QFormLayout()
        self.detail_labels: dict[str, QLabel] = {}
        for key, title in (
            ("strategy_id", "策略 ID"),
            ("family", "策略家族"),
            ("description", "規則摘要"),
            ("entry", "入場條件"),
            ("exit", "出場條件"),
            ("regime", "適用情境"),
            ("risk_description", "風險與限制"),
            ("parameter_schema", "登記參數欄位"),
            ("saved_parameters", "保存版本參數"),
            ("saved_config", "保存版本設定"),
            ("required_features", "必要資料"),
            ("data_assumptions", "資料假設"),
            ("cost", "成本假設"),
            ("qualification", "來源資格欄位（原文，不代表核准）"),
            ("validation_status", "保存版驗證狀態（來源原值，不代表核准）"),
            ("metadata_source", "欄位來源"),
            ("source_identity", "保存來源身份"),
        ):
            label = QLabel("未提供")
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.detail_labels[key] = label
            self.details.addRow(title, label)
        detail_layout.addLayout(self.details)
        detail_layout.addStretch(1)
        self.select_button = QPushButton("以此設定回測")
        self.select_button.setEnabled(False)
        self.select_button.setToolTip("明確選取後只回傳策略 ID 與版本，不會執行回測或保存資料。")
        detail_layout.addWidget(self.select_button)
        split.addWidget(detail)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)
        root.addWidget(split, stretch=1)

        self.search_edit.textChanged.connect(self._filter_strategies)
        self.strategy_list.currentItemChanged.connect(self._on_strategy_changed)
        self.version_combo.currentIndexChanged.connect(self._on_version_changed)
        self.select_button.clicked.connect(self._emit_selected_strategy)
        self.reload()

    def reload(self) -> bool:
        """重讀策略登記與版本清單；任何來源錯誤都呈現安全空頁。"""
        previous = self._selected_strategy_id
        try:
            raw = self._registry.list_strategies()
            if not isinstance(raw, dict):
                raise TypeError("策略登記清單格式不符")
            strategies: dict[str, dict[str, Any]] = {}
            for strategy_id, item in raw.items():
                metadata = _metadata_dict(item)
                if isinstance(strategy_id, str) and strategy_id and metadata is not None:
                    if not metadata.get("strategy_id"):
                        metadata["strategy_id"] = strategy_id
                    if metadata["strategy_id"] == strategy_id:
                        strategies[strategy_id] = metadata
        except Exception:
            strategies = {}

        self._strategies = strategies
        self.strategy_list.blockSignals(True)
        self.strategy_list.clear()
        for strategy_id, meta in strategies.items():
            label = str(meta.get("name") or strategy_id)
            item = QListWidgetItem(f"{label}  ·  {strategy_id}")
            item.setData(Qt.ItemDataRole.UserRole, strategy_id)
            item.setToolTip(_plain(meta.get("description")))
            self.strategy_list.addItem(item)
        self.strategy_list.blockSignals(False)
        self._filter_strategies(self.search_edit.text())
        restore = self._find_strategy_item(previous)
        if restore is None and self.strategy_list.count():
            restore = self.strategy_list.item(0)
        self.strategy_list.setCurrentItem(restore)
        if restore is None:
            self._selected_strategy_id = None
            self._clear_details("策略來源目前不可用")
        return bool(strategies)

    def _find_strategy_item(self, strategy_id: str | None) -> QListWidgetItem | None:
        if not strategy_id:
            return None
        for index in range(self.strategy_list.count()):
            item = self.strategy_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == strategy_id:
                return item
        return None

    def _filter_strategies(self, text: str) -> None:
        query = text.strip().casefold()
        for index in range(self.strategy_list.count()):
            item = self.strategy_list.item(index)
            strategy_id = item.data(Qt.ItemDataRole.UserRole)
            meta = self._strategies.get(strategy_id, {})
            haystack = " ".join(
                str(meta.get(key, "")) for key in ("name", "strategy_id", "description", "family")
            ).casefold()
            item.setHidden(bool(query and query not in haystack))

    def _on_strategy_changed(self, current: QListWidgetItem | None, _previous) -> None:
        strategy_id = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        if not isinstance(strategy_id, str) or strategy_id not in self._strategies:
            self._selected_strategy_id = None
            self._clear_details("請選擇已登記策略")
            return
        self._selected_strategy_id = strategy_id
        choices = self._choices_for(strategy_id)
        self._choices = choices
        self.version_combo.blockSignals(True)
        self.version_combo.clear()
        for choice in choices:
            suffix = "" if choice.selectable else "（版本來源缺失，無法套用）"
            saved_id = (choice.saved or {}).get("version_id")
            if saved_id:
                suffix += f"｜保存 ID {saved_id}"
            self.version_combo.addItem(f"版本 {choice.version}{suffix}", choice)
        self.version_combo.blockSignals(False)
        self.version_combo.setEnabled(bool(choices))
        if choices:
            self.version_combo.setCurrentIndex(0)
            self._render_choice(choices[0])
        else:
            self._render_choice(None)

    def _choices_for(self, strategy_id: str) -> list[_VersionChoice]:
        saved_by_version: dict[str, dict[str, Any]] = {}
        service = self._version_service
        if service is not None:
            try:
                saved_rows = service.list_versions(strategy_id)
            except Exception:
                saved_rows = []
            if isinstance(saved_rows, list):
                for row in saved_rows:
                    if not isinstance(row, dict) or row.get("strategy_id") != strategy_id:
                        continue
                    version = row.get("strategy_version")
                    version_id = row.get("version_id")
                    if (isinstance(version, str) and version and version == version.strip()
                            and isinstance(version_id, str) and version_id):
                        saved_by_version.setdefault(version, row)

        versions: list[str] = []
        base_meta = self._strategies.get(strategy_id)
        current_version = _semantic_version(base_meta)
        if current_version:
            versions.append(current_version)
        for version in saved_by_version:
            if version not in versions:
                versions.append(version)

        choices: list[_VersionChoice] = []
        for version in versions:
            metadata = None
            try:
                metadata = _metadata_dict(self._registry.get_strategy_meta(strategy_id, version=version))
            except Exception:
                metadata = None
            saved = saved_by_version.get(version)
            choices.append(_VersionChoice(strategy_id, version, metadata, saved))
        return choices

    def _on_version_changed(self, index: int) -> None:
        choice = self.version_combo.itemData(index)
        self._render_choice(choice if isinstance(choice, _VersionChoice) else None)

    def _render_choice(self, choice: _VersionChoice | None) -> None:
        if choice is None:
            self._clear_details("此策略沒有可核對的語意版本")
            return
        meta = choice.metadata or {}
        saved = choice.saved or {}
        self.strategy_title.setText(str(meta.get("name") or self._strategies.get(choice.strategy_id, {}).get("name") or choice.strategy_id))
        values = {
            "strategy_id": choice.strategy_id,
            "family": meta.get("family"),
            "description": meta.get("description"),
            "entry": meta.get("entry"),
            "exit": meta.get("exit"),
            "regime": meta.get("regime"),
            "risk_description": meta.get("risk_description"),
            "parameter_schema": meta.get("params", meta.get("default_params")),
            "saved_parameters": saved.get("params"),
            "saved_config": saved.get("config"),
            "required_features": meta.get("required_features"),
            "data_assumptions": meta.get("data_assumptions"),
            "cost": meta.get("cost"),
            "qualification": meta.get("qualification"),
            "validation_status": saved.get("validation_status"),
            "metadata_source": (
                "策略登記 metadata（缺欄位顯示未提供）；保存驗證狀態取自 StrategyVersion"
                if saved else "策略登記 metadata（缺欄位顯示未提供）；無匹配保存版本"
            ),
            "source_identity": (
                f"策略 {choice.strategy_id}｜版本 {choice.version}｜"
                f"保存版本 ID {_plain(saved.get('version_id'))}｜來源回測 {_plain(saved.get('source_run_id'))}"
                if saved else f"策略 {choice.strategy_id}｜版本 {choice.version}｜未提供保存版本身份"
            ),
        }
        for key, value in values.items():
            self.detail_labels[key].setText(_plain(value))
        selectable = self._choice_can_apply(choice)
        self.select_button.setEnabled(selectable)
        self.select_button.setToolTip(
            "明確選取後只回傳策略 ID 與版本，不會執行回測或保存資料。"
            if selectable else "此版本沒有可用的精確執行設定，無法套用；保存紀錄仍可唯讀查看。"
        )

    def _clear_details(self, title: str) -> None:
        self.strategy_title.setText(title)
        self.select_button.setEnabled(False)
        self.version_combo.setEnabled(False)
        for label in self.detail_labels.values():
            label.setText("未提供")

    def _emit_selected_strategy(self) -> None:
        index = self.version_combo.currentIndex()
        choice = self.version_combo.itemData(index)
        if isinstance(choice, _VersionChoice) and self._choice_can_apply(choice):
            self.strategySelected.emit(choice.strategy_id, choice.version)

    def _choice_can_apply(self, choice: _VersionChoice) -> bool:
        return choice.selectable and (
            self._can_apply is None or self._can_apply(choice.strategy_id, choice.version)
        )
