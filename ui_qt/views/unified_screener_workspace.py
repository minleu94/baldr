"""整理既有選股研究來源，並唯讀呈現來源回傳的母體漏斗。"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any, Callable, cast

from PySide6.QtCore import QEvent, QObject, QSignalBlocker, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QBoxLayout,
    QGridLayout,
    QGroupBox,
    QAbstractButton,
    QLabel,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QWidget,
    QScrollArea,
)
from ui_qt.widgets.theme_widgets import CollapsibleSectionPanel
from ui_qt.theme import MIDNIGHT_ANALYST


@dataclass(frozen=True, slots=True)
class FunnelMetric:
    """保存一個結果所附的母體計數；缺值維持未提供。"""

    domain: str
    denominator: int | None
    match: int | None = None
    no_match: int | None = None
    unknown: int | None = None
    not_evaluated: int | None = None
    not_applicable: int | None = None


@dataclass(frozen=True, slots=True)
class FunnelProjection:
    """呈現所選查詢結果攜帶的來源計數。"""

    schema: str | None
    data_date: str | None
    source_identity: str | None
    query_identity: str | None
    metrics: tuple[FunnelMetric, ...]
    available: bool


_FUNNEL_DISTRIBUTION_STATES = (
    ("match", "符合", "#60A5FA"),
    ("no_match", "不符合", "#52677E"),
    ("unknown", "未知", "#E1A94B"),
    ("not_evaluated", "未評估", "#71839A"),
    ("not_applicable", "不適用", "#927BC6"),
)
_FUNNEL_DISTRIBUTION_LIMIT = 6


class _ResizeCallbackFilter(QObject):
    """在宿主寬度變更時更新局部響應式控制排列。"""

    def __init__(self, callback: Callable[[int], None], parent: QWidget) -> None:
        super().__init__(parent)
        self._callback = callback

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if isinstance(watched, QWidget) and event.type() == QEvent.Type.Resize:
            self._callback(watched.width())
        return False


def _complete_funnel_distribution(
    metric: FunnelMetric,
) -> tuple[int, int, int, int, int] | None:
    """只接受五態完整、非負，且分母與原值總和相等的計數。"""

    denominator = metric.denominator
    counts = (
        metric.match,
        metric.no_match,
        metric.unknown,
        metric.not_evaluated,
        metric.not_applicable,
    )
    if (
        type(denominator) is not int
        or denominator < 0
        or any(type(count) is not int or count < 0 for count in counts)
        or sum(counts) != denominator
    ):
        return None
    return cast(tuple[int, int, int, int, int], counts)


class _FunnelDistributionBar(QWidget):
    """單一母體條件的五態相對分布；不比較或累加不同條件。"""

    def __init__(
        self,
        metric: FunnelMetric,
        counts: tuple[int, int, int, int, int],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._denominator = metric.denominator
        self._counts = counts
        self.setMinimumWidth(100)
        self.setMinimumHeight(14)
        self.setMaximumHeight(18)
        self.setAccessibleName(f"{metric.domain}五態狀態分布")
        details = "；".join(
            f"{label} {count}"
            for (_key, label, _color), count in zip(
                _FUNNEL_DISTRIBUTION_STATES, counts
            )
        )
        description = f"{metric.domain}；分母 {metric.denominator}；{details}"
        self.setAccessibleDescription(description)
        self.setToolTip(description)

    def paintEvent(self, _event: object) -> None:  # noqa: N802 - Qt callback name.
        denominator = self._denominator
        if type(denominator) is not int or denominator <= 0:
            return
        bounds = self.rect().adjusted(0, 1, -1, -1)
        if bounds.width() <= 2 or bounds.height() <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#263549"))
        painter.drawRoundedRect(bounds, 4, 4)
        inner = bounds.adjusted(1, 1, -1, -1)
        available_width = inner.width()
        previous_edge = 0
        accumulated = 0
        for (_key, _label, color), count in zip(
            _FUNNEL_DISTRIBUTION_STATES, self._counts
        ):
            accumulated += count
            edge = accumulated * available_width // denominator
            segment_width = edge - previous_edge
            if count > 0 and segment_width > 0:
                painter.fillRect(
                    inner.left() + previous_edge,
                    inner.top(),
                    segment_width,
                    inner.height(),
                    QColor(color),
                )
            previous_edge = edge
        painter.end()


@dataclass(frozen=True, slots=True)
class _Source:
    key: str
    label: str
    widget: QWidget
    outer_widget: QWidget
    inner_tabs: Any | None = None
    ml: bool = False


_DOMAIN_FIELDS = (
    ("技術", "technical_truth_counts"),
    ("均線", "ma_truth_counts"),
    ("KDJ", "kdj_truth_counts"),
    ("波動", "volatility_truth_counts"),
    ("官方＋技術條件", "composite_truth_counts"),
    ("硬性資格", "hard_eligible_truth_counts"),
    ("可評估", "active_evaluable_truth_counts"),
    ("價格條件", "price_truth_counts"),
    ("最終條件", "final_truth_counts"),
)


def _truth_map(value: object) -> dict[str, int] | None:
    if isinstance(value, Mapping):
        result = value
    elif isinstance(value, tuple):
        try:
            keys = [item[0] for item in value if isinstance(item, tuple) and len(item) == 2]
            if (
                len(keys) != len(value)
                or any(type(key) is not str for key in keys)
                or len(keys) != len(set(keys))
            ):
                return None
            result = dict(value)
        except (TypeError, ValueError):
            return None
    else:
        return None
    states = ("match", "no_match", "unknown", "not_evaluated", "not_applicable")
    if any(state not in result for state in states):
        return None
    picked: dict[str, int] = {}
    for state in states:
        count = result[state]
        if type(count) is not int or count < 0:
            return None
        picked[state] = count
    return picked


def _identity_text(value: object) -> str | None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        return None
    return value[:12]


def _date_text(value: object) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        rendered = isoformat()
        return rendered if isinstance(rendered, str) and rendered else None
    return value if isinstance(value, str) and value else None


def project_result_funnel(view: object) -> FunnelProjection:
    """只讀公開結果計數，不以列資料或頁面長度推估母體。"""

    result = getattr(view, "current_result", None)
    page = getattr(view, "current_page", None)
    owner = result if result is not None else page
    if owner is None:
        return FunnelProjection(None, None, None, None, (), False)

    query = getattr(owner, "query", None)
    schema = getattr(query, "schema_version", None)
    if not isinstance(schema, str) or not schema:
        schema = getattr(owner, "schema_version", None) or (
            type(query).__name__ if query is not None else None
        )
    if not isinstance(schema, str) or not schema:
        schema = None

    source = getattr(query, "source", None)
    if source is None:
        source = getattr(getattr(query, "f17_query", None), "source", None)
    date_value = getattr(source, "decision_date", None)
    if date_value is None:
        date_value = getattr(query, "decision_date", None)
    if date_value is None:
        date_value = getattr(getattr(query, "f17_query", None), "decision_date", None)
    source_identity = getattr(source, "source_identity_sha256", None)
    if source_identity is None:
        source_identity = getattr(owner, "source_identity_sha256", None)
    if source_identity is None:
        pins = getattr(owner, "source_pins", None)
        if isinstance(pins, tuple):
            pin_map = dict(pins)
            source_identity = pin_map.get("projection_group_session_identity_sha256")
            if source_identity is None:
                source_identity = pin_map.get("price_index_identity_sha256")
    query_identity = getattr(query, "query_identity_sha256", None)
    if query_identity is None:
        query_identity = getattr(owner, "query_identity_sha256", None)

    counts = getattr(owner, "counts", None)
    source_counts = getattr(owner, "source_counts", None)
    price_counts = getattr(owner, "price_counts", None)
    metrics: list[FunnelMetric] = []
    population = getattr(source_counts, "population", None)
    if population is None:
        population = source_counts
    if population is None:
        population = getattr(counts, "population", None)
    if population is None:
        base = getattr(counts, "base_f17_counts", None)
        population = getattr(base, "population", None)
    # v4 頁面直接攜帶已核驗的扁平母體計數，不能以可見列數替代。
    flat_population = population is None and hasattr(counts, "declared_count")
    if flat_population:
        population = counts
    declared = getattr(population, "declared_count", None)
    processed = getattr(population, "processed_count", None)
    if type(declared) is int and declared >= 0:
        metrics.append(FunnelMetric("來源母體", declared))
    elif population is not None:
        metrics.append(FunnelMetric("來源母體", None))
    if type(processed) is int and processed >= 0:
        metrics.append(FunnelMetric("來源已處理", processed))
    elif population is not None:
        metrics.append(FunnelMetric("來源已處理", None))
    pending = getattr(counts, "pending_count", getattr(population, "pending_count", None))
    excluded = getattr(counts, "excluded_count", getattr(population, "excluded_count", None))
    if type(pending) is int and pending >= 0:
        metrics.append(FunnelMetric("尚待處理", pending))
    if type(excluded) is int and excluded >= 0:
        metrics.append(FunnelMetric("來源排除", excluded))
    if flat_population:
        for domain, field in (
            ("來源納入", "included_count"),
            ("已處理但缺資料", "missing_data_count"),
            ("待處理且缺資料", "missing_data_pending_count"),
        ):
            value = getattr(population, field, None)
            metrics.append(FunnelMetric(domain, value if type(value) is int and value >= 0 else None))

    # F07 結果與頁面都帶有經核驗的來源計數及價格三態計數。
    if price_counts is None and page is not None:
        price_counts = getattr(page, "price_counts", None)
    if price_counts is not None:
        base_n = getattr(price_counts, "base_matching_count", None)
        match = getattr(price_counts, "pass_count", None)
        no_match = getattr(price_counts, "fail_count", None)
        unknown = getattr(price_counts, "unknown_count", None)
        if all(type(value) is int and value >= 0 for value in (base_n, match, no_match, unknown)):
            metrics.append(FunnelMetric("價格條件", base_n, match, no_match, unknown))
        else:
            metrics.append(FunnelMetric("價格條件", None))

    composite_counts = getattr(counts, "base_composite_counts", None)
    for domain, field in _DOMAIN_FIELDS:
        raw_truth = getattr(counts, field, None)
        if raw_truth is None and composite_counts is not None:
            raw_truth = getattr(composite_counts, field, None)
        truth = _truth_map(raw_truth)
        if truth is None:
            if raw_truth is not None:
                metrics.append(FunnelMetric(domain, None))
            continue
        denominator = sum(truth.values())
        metrics.append(
            FunnelMetric(
                domain,
                denominator,
                truth.get("match"),
                truth.get("no_match"),
                truth.get("unknown"),
                truth.get("not_evaluated"),
                truth.get("not_applicable"),
            )
        )

    # 官方條件 reader 以名稱成對保存完整三態及未評估計數。
    truth_counts = getattr(counts, "truth_counts", None)
    if isinstance(truth_counts, tuple):
        for name, state_counts in truth_counts:
            truth = _truth_map(
                {
                    "match": getattr(state_counts, "match", None),
                    "no_match": getattr(state_counts, "no_match", None),
                    "unknown": getattr(state_counts, "unknown", None),
                    "not_evaluated": getattr(state_counts, "not_evaluated", None),
                    "not_applicable": getattr(state_counts, "not_applicable", None),
                }
            )
            if truth is not None:
                metrics.append(
                    FunnelMetric(
                        str(name),
                        sum(truth.values()),
                        truth.get("match"),
                        truth.get("no_match"),
                        truth.get("unknown"),
                        truth.get("not_evaluated"),
                        truth.get("not_applicable"),
                    )
                )
            else:
                metrics.append(FunnelMetric(str(name), None))

    return FunnelProjection(
        schema,
        _date_text(date_value),
        _identity_text(source_identity),
        _identity_text(query_identity),
        tuple(metrics),
        bool(metrics),
    )


class UnifiedScreenerWorkspace:
    """在既有 RecommendationView 外提供來源選擇器。"""

    def __init__(self, recommendation_view: object) -> None:
        self.recommendation_view = recommendation_view
        self.tabs = getattr(recommendation_view, "result_source_tabs")
        self.scroll = getattr(recommendation_view, "result_scroll")
        self.splitter: QSplitter = getattr(recommendation_view, "main_splitter")
        self.combo = QComboBox()
        self.combo.setObjectName("unifiedScreenerSourceSelector")
        self.combo.setAccessibleName("研究線索篩選來源")
        self.banner = QLabel(
            "研究用｜查詢截至：未提供｜來源識別：未提供｜查詢識別：未提供｜格式：未提供"
        )
        self.banner.setObjectName("unifiedScreenerResearchNotice")
        self.banner.setWordWrap(True)
        self.funnel = QLabel("母體漏斗：未提供")
        self.funnel.setObjectName("unifiedScreenerFunnel")
        self.funnel.setWordWrap(True)
        self.funnel.setStyleSheet(f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 12px;")
        self.funnel_details = CollapsibleSectionPanel("母體漏斗明細（可展開）", collapsed=True)
        self.funnel_details.setObjectName("unifiedScreenerFunnelDetails")
        self._compact_disclosure(self.funnel_details)
        self.funnel_distribution_notice = QLabel("")
        self.funnel_distribution_notice.setObjectName("unifiedScreenerDistributionNotice")
        self.funnel_distribution_notice.setWordWrap(True)
        self.funnel_distribution_notice.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 11px;"
        )
        self.funnel_details.content_layout.addWidget(self.funnel_distribution_notice)
        self.funnel_distribution_legend = QWidget()
        self.funnel_distribution_legend.setObjectName("unifiedScreenerDistributionLegend")
        legend_layout = QHBoxLayout(self.funnel_distribution_legend)
        legend_layout.setContentsMargins(0, 0, 0, 0)
        legend_layout.setSpacing(8)
        self._distribution_rows: dict[str, QWidget] = {}
        self._distribution_layout = QVBoxLayout()
        self._distribution_layout.setContentsMargins(0, 0, 0, 0)
        self._distribution_layout.setSpacing(2)
        self.funnel_distribution_rows = QWidget()
        self.funnel_distribution_rows.setObjectName("unifiedScreenerDistributionRows")
        self.funnel_distribution_rows.setLayout(self._distribution_layout)
        self.funnel_distribution_rows.setMaximumHeight(
            _FUNNEL_DISTRIBUTION_LIMIT * 20 + 2
        )
        self.funnel_distribution_legend.setVisible(False)
        self.funnel_distribution_rows.setVisible(False)
        self._distribution_signature: object | None = None
        for _key, label, color in _FUNNEL_DISTRIBUTION_STATES:
            legend_item = QLabel(f"■ {label}")
            legend_item.setStyleSheet(f"color: {color}; font-size: 10px;")
            legend_layout.addWidget(legend_item)
        legend_layout.addStretch(1)
        self.funnel_details.content_layout.addWidget(self.funnel_distribution_legend)
        self.funnel_details.content_layout.addWidget(self.funnel_distribution_rows)
        self.funnel_detail_text = QLabel("")
        self.funnel_detail_text.setObjectName("unifiedScreenerFunnelDetailText")
        self.funnel_detail_text.setWordWrap(True)
        self.funnel_detail_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.funnel_details.content_layout.addWidget(self.funnel_detail_text)
        self.disabled_note = QLabel(
            "先核對所選來源與資料日期；條件變更後，在該來源頁按「套用全域查詢」更新結果。"
        )
        self.disabled_note.setObjectName("unifiedScreenerUsageHint")
        self.disabled_note.setWordWrap(True)
        self.quick_routes = QVBoxLayout()
        self.quick_routes.setContentsMargins(0, 0, 0, 0)
        self.quick_routes.setSpacing(4)
        self.source_routes = QHBoxLayout()
        self.source_route_group_label = QLabel("來源")
        self.source_route_group_label.setObjectName("unifiedScreenerSourceGroupLabel")
        self.source_routes.addWidget(self.source_route_group_label)
        self.quick_route_buttons: dict[str, QPushButton] = {}
        for key, label in (
            ("official_technical_revenue", "官方＋技術＋月營收"),
            ("official_technical_price", "官方＋技術＋價格"),
            ("price_universe", "價格母體"),
        ):
            button = QPushButton(label)
            button.setObjectName(f"unifiedScreenerRoute_{key}")
            button.setToolTip("開啟既有來源條件頁；不會自動執行查詢。")
            self.quick_route_buttons[key] = button
            self.source_routes.addWidget(button)
        quick_routes_header = QHBoxLayout()
        self.condition_recipe_group_label = QLabel("研究線索篩選")
        self.condition_recipe_group_label.setObjectName("unifiedScreenerConditionGroupLabel")
        self.condition_recipe_group_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_primary}; font-weight: 700;"
        )
        quick_routes_header.addWidget(self.condition_recipe_group_label)
        quick_routes_header.addStretch(1)
        self.quick_routes.addLayout(quick_routes_header)
        self.condition_recipe_layout = QGridLayout()
        self.condition_recipe_layout.setContentsMargins(0, 0, 0, 0)
        self.condition_recipe_layout.setHorizontalSpacing(6)
        self.condition_recipe_layout.setVerticalSpacing(4)
        self.condition_recipe_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.condition_recipe_buttons: dict[str, QPushButton] = {}
        for key, label in (
            ("ma5_20_golden_cross", "MA5／MA20 金叉符合"),
            ("kd_golden_cross", "K／D 金叉符合"),
            ("macd_golden_cross", "MACD 金叉符合"),
        ):
            button = QPushButton(label)
            button.setObjectName(f"unifiedScreenerCondition_{key}")
            button.setMinimumHeight(28)
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            button.setToolTip(
                "只替換已保存技術來源的規則篩選；其他條件保留。"
                "需再按來源頁「套用全域查詢」；不代表資料資格或投資建議。"
            )
            self.condition_recipe_buttons[key] = button
            self.condition_recipe_layout.addWidget(button, 0, len(self.condition_recipe_buttons) - 1)
        self.condition_recipe_hint = QLabel(
            "捷徑只替換技術規則，不會改變來源、其他條件或自動查詢。"
        )
        self.condition_recipe_hint.setObjectName("unifiedScreenerConditionRecipeHint")
        self.condition_recipe_hint.setWordWrap(True)
        self.condition_recipe_hint.setAccessibleName("研究線索篩選的下一步")
        self.condition_recipe_hint.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; padding-left: 4px;"
        )
        self.save_filter_button = QPushButton("儲存篩選條件")
        self.save_filter_button.setObjectName("unifiedScreenerSaveFilter")
        self.save_filter_button.setMinimumHeight(28)
        self.save_filter_button.setEnabled(False)
        self.save_filter_button.setAccessibleName("儲存目前的研究篩選條件")
        self.save_filter_button.setToolTip(
            "目前來源沒有可用的原生收藏流程。"
        )
        self.save_filter_button.clicked.connect(self.save_current_filter)
        quick_routes_header.addWidget(self.save_filter_button)
        self.quick_routes.addLayout(self.condition_recipe_layout)
        self.quick_routes.addWidget(self.condition_recipe_hint)
        self.unavailable_conditions = QLabel(
            "尚未接通：題材條件、財報條件、法人條件。月營收可由「官方＋技術＋月營收」來源頁使用。"
        )
        self.unavailable_conditions.setObjectName("unifiedScreenerUnavailableConditionDetails")
        self.unavailable_conditions.setWordWrap(True)

        self.host = QWidget(self.tabs.parentWidget())
        self.host.setObjectName("unifiedScreenerSourceHost")
        layout = QVBoxLayout(self.host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self.combo)
        layout.addLayout(self.quick_routes)
        self.research_scope = QLabel("研究用｜查詢截至：未提供；逐筆資料日依原表。")
        self.research_scope.setWordWrap(True)
        layout.addWidget(self.research_scope)
        layout.addWidget(self.funnel)
        layout.addWidget(self.funnel_details)
        layout.addWidget(self.disabled_note)
        self.source_details = CollapsibleSectionPanel(
            "資料日期、來源版本與可用條件", collapsed=True
        )
        self._compact_disclosure(self.source_details)
        self.source_details.content_layout.addLayout(self.source_routes)
        self.source_details.content_layout.addWidget(self.banner)
        self.source_details.content_layout.addWidget(self.unavailable_conditions)
        layout.addWidget(self.source_details)
        # 保留原結果捲動區與分頁物件；選擇器放在捲動區上方，不另包捲動區。
        index = self.splitter.indexOf(self.scroll)
        if index < 0:
            raise ValueError("RecommendationView.result_scroll is not in main_splitter")
        self.splitter.replaceWidget(index, self.host)
        layout.addWidget(self.scroll, 1)
        self.tabs.tabBar().hide()

        self._sources: list[_Source] = []
        self._source_by_key: dict[str, _Source] = {}
        self._connected_inner_tabs: set[int] = set()
        self._active_key: str | None = None
        self._connected_operation_signals: set[int] = set()
        self._invalidated_source_widgets: set[int] = set()
        self._ml_mode = False
        self._explicit_mode_transition = False
        self._last_key_by_mode: dict[bool, str | None] = {False: None, True: None}
        self._previous_splitter_sizes: list[int] | None = None
        self._timer = QTimer(self.host)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self.refresh_funnel)
        self.combo.currentIndexChanged.connect(self._on_combo_changed)
        for key, button in self.quick_route_buttons.items():
            button.clicked.connect(lambda _checked=False, route=key: self.select_recipe(route))
        for key, button in self.condition_recipe_buttons.items():
            button.clicked.connect(
                lambda _checked=False, recipe=key: self.apply_condition_recipe(recipe)
            )
        self.tabs.currentChanged.connect(self._on_outer_changed)
        self._quick_routes_resize_filter = _ResizeCallbackFilter(
            self._arrange_condition_recipe_buttons,
            self.host,
        )
        self.host.installEventFilter(self._quick_routes_resize_filter)
        self._condition_recipe_columns: int | None = None
        self._arrange_condition_recipe_buttons(self.host.width())
        self.sync_sources()
        self._timer.start()

    def _arrange_condition_recipe_buttons(self, width: int) -> None:
        """依來源工作區寬度換列，保持研究捷徑緊湊並靠左排列。"""

        columns = 3 if width >= 1080 else 2 if width >= 620 else 1
        if columns == self._condition_recipe_columns:
            return
        layout = self.condition_recipe_layout
        while layout.count():
            layout.takeAt(0)
        for index, button in enumerate(self.condition_recipe_buttons.values()):
            row, column = divmod(index, columns)
            layout.addWidget(button, row, column)
        self._condition_recipe_columns = columns

    @staticmethod
    def _is_ml_widget(widget: QWidget, label: str) -> bool:
        explicit = widget.property("v2_screener_ml_route")
        if explicit is not None:
            return bool(explicit)
        identity = f"{widget.objectName()} {type(widget).__name__} {label}".casefold()
        return "h20" in identity or "machinelearning" in identity or "ml route" in identity

    @staticmethod
    def _source_label(label: str, widget: QWidget) -> str:
        qualified = (type(widget).__module__, type(widget).__name__)
        exact_labels = {
            ("ui_qt.views.daily_market_technical_official_disposition_revenue_view", "DailyMarketTechnicalOfficialDispositionRevenueView"): "官方＋技術＋月營收",
            ("ui_qt.views.daily_market_technical_official_disposition_composite_view_v2", "DailyMarketTechnicalOfficialDispositionCompositeViewV2"): "官方＋技術＋價格",
            ("ui_qt.views.daily_market_technical_universe_price_view_v1", "DailyMarketTechnicalUniversePriceV1View"): "價格母體",
        }
        if qualified in exact_labels:
            return exact_labels[qualified]
        normalized = label.strip()
        mapping = {
            "已保存推薦／策略研究": "保存策略研究",
            "每日研究條件": "每日研究",
            "官方市場／處置研究": "官方條件",
            "四均線／官方對照研究": "均線＋官方條件",
            "均線／月營收／官方對照研究": "官方＋技術＋月營收",
            "官方市場與技術條件研究": "官方＋技術研究",
            "官方條件與價格研究": "官方＋技術＋價格",
        }
        if normalized in mapping:
            return mapping[normalized]
        object_name = widget.objectName().casefold()
        if "price" in object_name or "價格選股" in normalized:
            return "技術價量／" + (normalized or "價格選股")
        if "technical" in object_name and "universe" in object_name:
            return "技術母體／" + (normalized or type(widget).__name__)
        return normalized or type(widget).__name__

    def _enumerate_sources(self) -> list[_Source]:
        found: list[_Source] = []
        used: set[str] = set()
        for outer_index in range(self.tabs.count()):
            outer_widget = self.tabs.widget(outer_index)
            if outer_widget is None:
                continue
            outer_label = self.tabs.tabText(outer_index)
            inner_tabs = getattr(outer_widget, "research_sections", None)
            if inner_tabs is not None and callable(getattr(inner_tabs, "count", None)):
                inner_tabs.tabBar().hide()
                if id(inner_tabs) not in self._connected_inner_tabs:
                    inner_tabs.currentChanged.connect(self._on_inner_changed)
                    self._connected_inner_tabs.add(id(inner_tabs))
                for inner_index in range(inner_tabs.count()):
                    widget = inner_tabs.widget(inner_index)
                    if widget is None:
                        continue
                    inner_label = inner_tabs.tabText(inner_index)
                    label = self._source_label(inner_label, widget)
                    source_label = f"每日研究／{label}"
                    key = self._key_for(widget, outer_widget, inner_tabs, source_label)
                    if key not in used:
                        used.add(key)
                        found.append(_Source(key, source_label, widget, outer_widget, inner_tabs))
            else:
                label = self._source_label(outer_label, outer_widget)
                key = self._key_for(outer_widget, outer_widget, None, label)
                if key not in used:
                    used.add(key)
                    found.append(
                        _Source(
                            key,
                            label,
                            outer_widget,
                            outer_widget,
                            None,
                            self._is_ml_widget(outer_widget, label),
                        )
                    )
        return found

    @staticmethod
    def _key_for(widget: QWidget, outer: QWidget, inner_tabs: Any | None, label: str) -> str:
        explicit = widget.property("v2_screener_source_key")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip()
        object_name = widget.objectName().strip()
        stable = object_name or type(widget).__name__
        return f"{outer.objectName() or type(outer).__name__}:{stable}:{label}"

    def sync_sources(self) -> None:
        """Main 掛載來源頁後，更新來源選擇器與最近頁面。"""

        old_key = self._active_key
        current_outer = self.tabs.currentWidget()
        current_inner = getattr(current_outer, "research_sections", None)
        current_widget = current_inner.currentWidget() if current_inner is not None else current_outer
        self._sources = self._enumerate_sources()
        self._source_by_key = {source.key: source for source in self._sources}
        current_widget_ids = {id(source.widget) for source in self._sources}
        self._connected_operation_signals.intersection_update(current_widget_ids)
        self._invalidated_source_widgets.intersection_update(current_widget_ids)
        for source in self._sources:
            self._connect_source_operation_status(source.widget)
        self._refresh_quick_routes()
        if not self._explicit_mode_transition and not self._ml_mode and any(
            source.widget is current_widget and source.ml for source in self._sources
        ):
            self._ml_mode = True
        with QSignalBlocker(self.combo):
            self.combo.clear()
            visible = [source for source in self._sources if source.ml == self._ml_mode]
            for source in visible:
                self.combo.addItem(source.label, source.key)
            if visible and not self._ml_mode:
                self.combo.insertSeparator(self.combo.count())
                for label, key in (
                    ("法人條件（共用篩選未接線）", "__unwired_institutional__"),
                ):
                    self.combo.addItem(label, key)
                    self._disable_combo_item(
                        self.combo.count() - 1,
                        "此條件尚未接入共用篩選。請使用其來源研究頁，避免套用未核驗條件。",
                    )
            if not visible and self._ml_mode:
                self.combo.addItem("ML H20 尚未掛載", "__ml_unavailable__")
                self._disable_combo_item(0, "ML H20 來源尚未掛載。")
            wanted = next(
                (source for source in visible if source.widget is current_widget),
                next(
                    (
                        source for source in visible
                        if source.key == self._last_key_by_mode[self._ml_mode]
                    ),
                    next((source for source in visible if source.key == old_key), None),
                ),
            )
            if wanted is not None:
                self.combo.setCurrentIndex(self.combo.findData(wanted.key))
                self._active_key = wanted.key
            elif visible:
                self.combo.setCurrentIndex(0)
                self._active_key = visible[0].key
            else:
                self._active_key = None
        if self._active_key is not None:
            self._show_source(self._source_by_key[self._active_key], update_outer=True)
        else:
            self.refresh_funnel()

    _RECIPE_CLASSES = {
        "official_technical_revenue": ("ui_qt.views.daily_market_technical_official_disposition_revenue_view", "DailyMarketTechnicalOfficialDispositionRevenueView"),
        "official_technical_price": ("ui_qt.views.daily_market_technical_official_disposition_composite_view_v2", "DailyMarketTechnicalOfficialDispositionCompositeViewV2"),
        "price_universe": ("ui_qt.views.daily_market_technical_universe_price_view_v1", "DailyMarketTechnicalUniversePriceV1View"),
    }
    _RECIPE_LABELS = {
        "official_technical_revenue": "官方＋技術＋月營收",
        "official_technical_price": "官方＋技術＋價格",
        "price_universe": "價格母體",
    }
    _CONDITION_RECIPE_SOURCE = (
        "ui_qt.views.daily_market_technical_universe_v4_view",
        "DailyMarketTechnicalUniverseV4View",
    )
    _CONDITION_RECIPE_LABELS = {
        "ma5_20_golden_cross": "MA5／MA20 金叉符合",
        "kd_golden_cross": "K／D 金叉符合",
        "macd_golden_cross": "MACD 金叉符合",
    }

    def _refresh_quick_routes(self) -> None:
        for key, (module, class_name) in self._RECIPE_CLASSES.items():
            matches = [
                source for source in self._sources
                if type(source.widget).__module__ == module
                and type(source.widget).__name__ == class_name
            ]
            button = self.quick_route_buttons[key]
            button.setEnabled(len(matches) == 1 and not matches[0].ml)
            button.setToolTip(
                "開啟既有來源條件頁；不會自動執行查詢。"
                if len(matches) == 1
                else f"此來源尚未掛載：{self._RECIPE_LABELS[key]}。"
            )
        recipe_sources = [
            source for source in self._sources
            if (type(source.widget).__module__, type(source.widget).__name__)
            == self._CONDITION_RECIPE_SOURCE
            and not source.ml
        ]
        for key, button in self.condition_recipe_buttons.items():
            button.setEnabled(len(recipe_sources) == 1)
            button.setToolTip(
                "只替換已保存技術來源的規則篩選；其他條件保留。"
                "需再按來源頁「套用全域查詢」；不代表資料資格或投資建議。"
                if len(recipe_sources) == 1
                else "此技術規則範本需要唯一掛載的每日技術規則研究來源。"
            )
        self._refresh_save_filter_action()

    _BOOKMARK_BUTTON_SOURCES = {
        ("ui_qt.views.daily_market_technical_universe_v4_view", "DailyMarketTechnicalUniverseV4View"): "bookmark_button",
        ("ui_qt.views.daily_market_technical_universe_price_view_v1", "DailyMarketTechnicalUniversePriceV1View"): "bookmark_button",
        ("ui_qt.views.daily_market_technical_official_disposition_view", "DailyMarketTechnicalOfficialDispositionView"): "bookmark_button",
        ("ui_qt.views.daily_market_technical_official_disposition_ma_view", "DailyMarketTechnicalOfficialDispositionMaView"): "bookmark_button",
        ("ui_qt.views.daily_market_technical_official_disposition_revenue_view", "DailyMarketTechnicalOfficialDispositionRevenueView"): "bookmark_button",
        ("ui_qt.views.daily_market_technical_official_disposition_composite_view", "DailyMarketTechnicalOfficialDispositionCompositeView"): "bookmark_button",
        ("ui_qt.views.daily_market_technical_official_disposition_composite_view_v2", "DailyMarketTechnicalOfficialDispositionCompositeViewV2"): "bookmark_button",
    }

    def _bookmark_button_for(self, source: _Source | None) -> QPushButton | None:
        if source is None or source.ml:
            return None
        qualified = (type(source.widget).__module__, type(source.widget).__name__)
        attribute = self._BOOKMARK_BUTTON_SOURCES.get(qualified)
        button = getattr(source.widget, attribute, None) if attribute else None
        return button if isinstance(button, QPushButton) else None

    def _refresh_save_filter_action(self) -> QPushButton | None:
        source = self._source_by_key.get(self._active_key or "")
        native_button = self._bookmark_button_for(source)
        if native_button is None:
            self.save_filter_button.setEnabled(False)
            self.save_filter_button.setText("此來源未提供收藏")
            self.save_filter_button.setToolTip(
                "此來源尚未提供已接通的原生收藏流程；無法由共用選股頁保存。"
            )
            return None
        enabled = native_button.isEnabled()
        self.save_filter_button.setEnabled(enabled)
        native_hint = native_button.toolTip().strip()
        if enabled:
            self.save_filter_button.setText("儲存篩選條件")
            detail = native_button.text().strip() or "來源頁收藏"
            self.save_filter_button.setToolTip(
                f"沿用目前來源的「{detail}」流程；不另建或改寫收藏內容。"
            )
        else:
            self.save_filter_button.setText("目前無法收藏")
            self.save_filter_button.setToolTip(
                native_hint or "來源頁尚未滿足收藏條件；請核對來源狀態與查詢結果。"
            )
        return native_button

    def save_current_filter(self) -> bool:
        """只點擊目前精確來源已接通的收藏按鈕，沿用原有保存管線。"""
        native_button = self._refresh_save_filter_action()
        if native_button is None or not native_button.isEnabled():
            return False
        native_button.click()
        return True

    def apply_condition_recipe(self, key: str) -> bool:
        """定位既有技術來源並只套條件；明確保留查詢由使用者啟動。"""
        if key not in self._CONDITION_RECIPE_LABELS:
            return False
        matches = [
            source for source in self._sources
            if (type(source.widget).__module__, type(source.widget).__name__)
            == self._CONDITION_RECIPE_SOURCE
            and source.ml == self._ml_mode
            and not source.ml
        ]
        if len(matches) != 1 or not self.select_source(matches[0].key):
            return False
        apply_recipe = getattr(matches[0].widget, "apply_condition_recipe", None)
        if not callable(apply_recipe) or not apply_recipe(key):
            self.disabled_note.setText(
                "請先在每日技術規則研究頁嚴格核驗並載入保存來源，並等待背景工作完成。"
                "範本只替換規則條件；其他條件與來源保留，尚未查詢。"
            )
            return False
        self.disabled_note.setText(
            f"已套用條件：{self._CONDITION_RECIPE_LABELS[key]}。"
            "其他條件與保存來源保留；尚未查詢。請按來源頁「套用全域查詢」。"
            "此條件不代表資料資格或投資建議。"
        )
        return True

    def select_recipe(self, key: str) -> bool:
        """以來源的精確類別定位來源捷徑，不使用顯示名稱猜測路由。"""
        if key not in self._RECIPE_CLASSES:
            return False
        module, class_name = self._RECIPE_CLASSES[key]
        matches = [
            source for source in self._sources
            if type(source.widget).__module__ == module
            and type(source.widget).__name__ == class_name
            and source.ml == self._ml_mode
        ]
        return len(matches) == 1 and self.select_source(matches[0].key)

    def _disable_combo_item(self, index: int, tooltip: str) -> None:
        model = self.combo.model()
        if isinstance(model, QStandardItemModel):
            item = model.item(index)
            if item is not None:
                item.setEnabled(False)
                item.setToolTip(tooltip)

    def select_source(self, key_or_index: str | int) -> bool:
        source: _Source | None = None
        if type(key_or_index) is int:
            if 0 <= key_or_index < self.combo.count():
                key = self.combo.itemData(key_or_index)
                source = self._source_by_key.get(key)
        elif isinstance(key_or_index, str):
            source = self._source_by_key.get(key_or_index)
            if source is not None and source.ml != self._ml_mode:
                return False
        if source is None:
            return False
        self._show_source(source, update_outer=True)
        with QSignalBlocker(self.combo):
            self.combo.setCurrentIndex(self.combo.findData(source.key))
        return True

    def select_widget(self, widget: QWidget) -> bool:
        """以既有頁面實體定位來源；不執行查詢或重建來源身份。"""
        source = next((item for item in self._sources if item.widget is widget), None)
        return source is not None and self.select_source(source.key)

    def set_ml_mode(self, enabled: bool) -> bool:
        self._ml_mode = bool(enabled)
        self._explicit_mode_transition = True
        try:
            self.sync_sources()
        finally:
            self._explicit_mode_transition = False
        if not self._ml_mode:
            return True
        return any(source.ml for source in self._sources)

    def _on_combo_changed(self, index: int) -> None:
        if index < 0:
            return
        key = self.combo.itemData(index)
        source = self._source_by_key.get(key)
        if source is not None:
            self._show_source(source, update_outer=True)

    def _on_outer_changed(self, _index: int) -> None:
        current = self.tabs.currentWidget()
        inner = getattr(current, "research_sections", None)
        widget = inner.currentWidget() if inner is not None else current
        source = next((item for item in self._sources if item.widget is widget), None)
        if source is None:
            self.sync_sources()
            return
        if source.ml != self._ml_mode:
            self._ml_mode = source.ml
            self.sync_sources()
            return
        self.select_source(source.key)

    def _on_inner_changed(self, _index: int) -> None:
        outer = self.tabs.currentWidget()
        inner = getattr(outer, "research_sections", None)
        widget = inner.currentWidget() if inner is not None else None
        source = next(
            (item for item in self._sources if item.outer_widget is outer and item.widget is widget),
            None,
        )
        if source is None:
            return
        if source.ml != self._ml_mode:
            self._ml_mode = source.ml
            self.sync_sources()
            return
        self.select_source(source.key)

    def _show_source(self, source: _Source, *, update_outer: bool) -> None:
        self._adapt_source_preparation(source.widget)
        if update_outer and self.tabs.currentWidget() is not source.outer_widget:
            self.tabs.setCurrentWidget(source.outer_widget)
        if source.inner_tabs is not None and source.inner_tabs.currentWidget() is not source.widget:
            source.inner_tabs.setCurrentWidget(source.widget)
        self._active_key = source.key
        self._last_key_by_mode[source.ml] = source.key
        is_saved = source.outer_widget is getattr(self.recommendation_view, "result_panel", None)
        config_scroll = getattr(self.recommendation_view, "config_scroll", None)
        if config_scroll is not None:
            if is_saved:
                config_scroll.show()
                if self._previous_splitter_sizes is not None:
                    self.splitter.setSizes(self._previous_splitter_sizes)
                else:
                    self.splitter.setSizes([420, max(600, self.splitter.width() - 420)])
            else:
                if config_scroll.isVisible():
                    self._previous_splitter_sizes = self.splitter.sizes()
                config_scroll.hide()
        self.combo.setToolTip("切換已掛載研究來源；選擇本身不會執行查詢。")
        self._set_outer_scroll_policy(source)
        self.refresh_funnel()

    @staticmethod
    def _compact_disclosure(panel: CollapsibleSectionPanel) -> None:
        """工具設定用緊湊展開列，把可視高度留給研究結果。"""
        panel.layout.setContentsMargins(6, 2, 6, 2)
        panel.layout.setSpacing(2)
        panel.title_label.setStyleSheet(
            f"color: {MIDNIGHT_ANALYST.text_secondary}; font-size: 12px; "
            "font-weight: 700; padding: 0; border: none; background: transparent;"
        )
        panel.toggle_button.setStyleSheet("min-height: 0px; padding: 2px 6px;")
        panel.toggle_button.setFixedSize(48, 28)

    @staticmethod
    def _adapt_source_preparation(widget: QWidget) -> None:
        """收合明示標記的既有來源控制；不重接訊號或自動核驗來源。"""
        if widget.property("v2_source_preparation_adapted"):
            return
        group = widget.findChild(QGroupBox, "screenerSourcePreparation")
        if group is None:
            return
        owner = group.parentWidget()
        layout = owner.layout() if owner is not None else None
        if not isinstance(layout, QBoxLayout):
            return
        index = layout.indexOf(group)
        if index < 0:
            return
        panel = CollapsibleSectionPanel("研究來源與資料準備", collapsed=True, parent=owner)
        UnifiedScreenerWorkspace._compact_disclosure(panel)
        panel.setObjectName("screenerSourcePreparationDisclosure")
        layout.removeWidget(group)
        layout.insertWidget(index, panel)
        panel.content_layout.addWidget(group)
        for name in ("source_pins", "verified_pins"):
            pins = getattr(widget, name, None)
            if isinstance(pins, QWidget) and pins.parentWidget() is owner:
                layout.removeWidget(pins)
                panel.content_layout.addWidget(pins)
        filters = widget.findChild(QGroupBox, "screenerAdvancedConditions")
        filter_owner = filters.parentWidget() if filters is not None else None
        filter_layout = filter_owner.layout() if filter_owner is not None else None
        if filters is not None and isinstance(filter_layout, QBoxLayout):
            filter_index = filter_layout.indexOf(filters)
            if filter_index >= 0:
                advanced = CollapsibleSectionPanel("進階條件與排序", collapsed=True, parent=filter_owner)
                UnifiedScreenerWorkspace._compact_disclosure(advanced)
                advanced.setObjectName("screenerAdvancedConditionsDisclosure")
                filter_layout.removeWidget(filters)
                filter_layout.insertWidget(filter_index, advanced)
                advanced.content_layout.addWidget(filters)
                apply_button = getattr(widget, "apply_button", None)
                if isinstance(apply_button, QPushButton) and apply_button.parentWidget() is filters:
                    original_layout = filters.layout()
                    if original_layout is not None:
                        original_layout.removeWidget(apply_button)
                    filter_layout.insertWidget(filter_index + 1, apply_button)
        toggle = getattr(widget, "query_controls_toggle", None)
        if isinstance(toggle, QAbstractButton):
            toggle.setChecked(False)
        widget.setProperty("v2_source_preparation_adapted", True)

    def _set_outer_scroll_policy(self, source: _Source) -> None:
        widget = source.widget
        # 收合的來源追溯面板也可能含 QScrollArea；只有目前頁面實際可見的
        # 內層捲動區才能取代外層捲動，否則保存結果的下半部會被裁掉。
        nested = isinstance(widget, QScrollArea) or any(
            area.isVisibleTo(widget) for area in widget.findChildren(QScrollArea)
        )
        self.scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            if nested
            else Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        # 隱藏外層垂直捲軸時，讓 tab 頁縮到可視區，交由頁內 QScrollArea 捲動。
        tab_policy = self.tabs.sizePolicy()
        tab_policy.setVerticalPolicy(
            QSizePolicy.Policy.Ignored if nested else QSizePolicy.Policy.Preferred
        )
        self.tabs.setSizePolicy(tab_policy)

    def _connect_source_operation_status(self, widget: QWidget) -> None:
        if id(widget) in self._connected_operation_signals:
            return
        signal = getattr(widget, "operationSettled", None)
        connect = getattr(signal, "connect", None)
        if callable(connect):
            connect(
                lambda kind, success, owner=widget: self._on_source_operation_settled(
                    owner, kind, success
                )
            )
            self._connected_operation_signals.add(id(widget))

    def _on_source_operation_settled(
        self, widget: QWidget, _kind: object, success: object
    ) -> None:
        if type(success) is bool:
            if success:
                self._invalidated_source_widgets.discard(id(widget))
            else:
                self._invalidated_source_widgets.add(id(widget))
        if any(
            source.widget is widget and source.key == self._active_key
            for source in self._sources
        ):
            self.refresh_funnel()

    def _source_operation_state(self, widget: QWidget) -> str:
        if id(widget) in self._invalidated_source_widgets:
            return "failed"
        for name in ("busy", "_v2_busy"):
            value = getattr(widget, name, None)
            if type(value) is bool and value:
                return "busy"
        for name in ("active_worker", "_busy_worker", "_worker"):
            if getattr(widget, name, None) is not None:
                return "busy"
        for name in ("status", "status_label"):
            label = getattr(widget, name, None)
            text_reader = getattr(label, "text", None)
            text = text_reader() if callable(text_reader) else ""
            normalized = text.casefold() if isinstance(text, str) else ""
            failure_tokens = (
                "失敗", "錯誤", "取消", "failed", "error", "cancelled", "canceled"
            )
            if any(token in normalized for token in failure_tokens):
                return "failed"
        return "ready"

    def _render_funnel_distributions(
        self,
        metrics: tuple[FunnelMetric, ...],
        *,
        identity: tuple[object, ...],
        state: str = "ready",
    ) -> None:
        raw_signature = tuple(
            (
                metric.domain,
                metric.denominator,
                metric.match,
                metric.no_match,
                metric.unknown,
                metric.not_evaluated,
                metric.not_applicable,
            )
            for metric in metrics
        )
        full_signature = (identity, state, raw_signature)
        if self._distribution_signature != full_signature:
            while self._distribution_layout.count():
                item = self._distribution_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.hide()
                    widget.setParent(None)
                    widget.deleteLater()
            self._distribution_rows.clear()

            complete = [
                (metric, counts)
                for metric in metrics
                if (counts := _complete_funnel_distribution(metric)) is not None
            ]
            nonzero = [
                (metric, counts)
                for metric, counts in complete
                if metric.denominator is not None and metric.denominator > 0
            ]
            for metric, counts in nonzero[:_FUNNEL_DISTRIBUTION_LIMIT]:
                row = QWidget(self.funnel_distribution_rows)
                row.setObjectName("unifiedScreenerDistributionRow")
                row.setMaximumHeight(18)
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(6)
                label = QLabel(metric.domain, row)
                label.setObjectName("unifiedScreenerDistributionDomain")
                label.setMinimumWidth(112)
                label.setMaximumWidth(170)
                label.setToolTip(metric.domain)
                bar = _FunnelDistributionBar(metric, counts, row)
                bar.setObjectName("unifiedScreenerDistributionBar")
                row_layout.addWidget(label)
                row_layout.addWidget(bar, 1)
                self._distribution_layout.addWidget(row)
                self._distribution_rows[metric.domain] = row

            self._distribution_signature = full_signature

        complete = [
            metric
            for metric in metrics
            if _complete_funnel_distribution(metric) is not None
        ]
        nonzero_count = sum(
            1 for metric in complete
            if metric.denominator is not None and metric.denominator > 0
        )
        zero_count = len(complete) - nonzero_count
        shown_count = min(nonzero_count, _FUNNEL_DISTRIBUTION_LIMIT)
        self.funnel_distribution_rows.setVisible(shown_count > 0)
        self.funnel_distribution_legend.setVisible(shown_count > 0)

        if state == "busy":
            notice = "來源操作進行中；暫清上一輪圖條，原結果表保留。"
        elif state == "failed":
            notice = "來源操作失敗或取消；已清除圖條，原結果與明細保留。"
        elif shown_count == 0 and zero_count:
            notice = (
                f"{zero_count} 項完整計數的分母為 0；原明細保留其 0 計數，不繪比例條。"
            )
        elif shown_count == 0:
            notice = "沒有完整且分母一致的五態計數可繪；缺值維持未提供，原明細保留。"
        else:
            notice = (
                "各條依自己的分母呈現，條件間可能重疊；不代表逐步淘汰、跨條件排名或資格。"
            )
            if zero_count:
                notice += f" 分母為 0 的 {zero_count} 項保留原始 0 計數，不繪比例條。"
            if nonzero_count > shown_count:
                notice += (
                    f" 圖條顯示 {shown_count}／{nonzero_count} 項；另有 "
                    f"{nonzero_count - shown_count} 項圖條省略，精確計數仍見下方明細。"
                )
            notice += " 五態計數或分母不完整／不一致者不繪條，數值仍按原文呈現。"
        self.funnel_distribution_notice.setText(notice)

    def refresh_funnel(self) -> None:
        self._refresh_save_filter_action()
        source = self._source_by_key.get(self._active_key or "")
        if source is None:
            self.research_scope.setText("研究用｜查詢截至：未提供；逐筆資料日依原表。")
            self.funnel.setText("母體漏斗：未提供")
            self.funnel_detail_text.setText("")
            self._render_funnel_distributions(
                (), identity=(None,), state="unavailable"
            )
            self.banner.setText(
                "研究用｜查詢截至：未提供｜來源識別：未提供｜查詢識別：未提供｜格式：未提供"
            )
            return
        view = source.widget
        projection = project_result_funnel(view)
        self.research_scope.setText(
            f"研究用｜查詢截至：{projection.data_date or '未提供'}；逐筆資料日依原表。"
        )
        self.banner.setText(
            "研究用｜查詢截至：{}（逐筆資料日依原表）｜來源識別：{}｜查詢識別：{}｜格式：{}".format(
                projection.data_date or "未提供",
                projection.source_identity or "未提供",
                projection.query_identity or "未提供",
                projection.schema or "未提供",
            )
        )
        identity = (
            source.key,
            projection.schema,
            projection.data_date,
            projection.source_identity,
            projection.query_identity,
        )
        operation_state = self._source_operation_state(view)
        if operation_state in {"busy", "failed"}:
            self._render_funnel_distributions(
                (), identity=identity, state=operation_state
            )
            self.funnel.setText(
                "母體漏斗：來源操作進行中；上一輪圖條已清除，原結果表保留。"
                if operation_state == "busy"
                else "母體漏斗：來源操作失敗或取消；圖條已清除，原結果保留。"
            )
            return
        if not projection.available:
            unavailable = "母體漏斗：未提供（此來源尚無已核結果計數）"
            self.funnel.setText("母體漏斗：未提供")
            self.funnel_detail_text.setText(unavailable)
            self._render_funnel_distributions(
                projection.metrics, identity=identity, state="unavailable"
            )
            return
        lines = ["母體漏斗（目前查詢來源，不跨來源合併；各項可能重疊）："]
        population_pieces: list[str] = []
        for metric in projection.metrics:
            pieces = [f"{metric.domain} {self._format_count(metric.denominator)}"]
            if all(value is None for value in (
                metric.match, metric.no_match, metric.unknown,
                metric.not_evaluated, metric.not_applicable,
            )):
                population_pieces.extend(pieces)
                continue
            if metric.match is not None or metric.no_match is not None or metric.unknown is not None:
                pieces.append(
                    "符合／不符合／未知 "
                    f"{self._format_count(metric.match)}／"
                    f"{self._format_count(metric.no_match)}／"
                    f"{self._format_count(metric.unknown)}"
                )
                if metric.not_evaluated is not None or metric.not_applicable is not None:
                    pieces.append(
                        "未評估／不適用 "
                        f"{self._format_count(metric.not_evaluated)}／"
                        f"{self._format_count(metric.not_applicable)}"
                    )
            lines.append(" · ".join(pieces))
        if population_pieces:
            lines.insert(1, " · ".join(population_pieces))
        detail_text = "\n".join(lines)
        self.funnel_detail_text.setText(detail_text)
        self._render_funnel_distributions(
            projection.metrics, identity=identity, state="ready"
        )
        summary = ["母體漏斗"]
        for metric in projection.metrics:
            if metric.domain in {"來源母體", "來源已處理", "尚待處理", "來源排除"}:
                summary.append(f"{metric.domain} {self._format_count(metric.denominator)}")
            elif metric.match is not None or metric.no_match is not None or metric.unknown is not None:
                summary.append(
                    f"{metric.domain} 符合／不符合／未知 "
                    f"{self._format_count(metric.match)}／{self._format_count(metric.no_match)}／"
                    f"{self._format_count(metric.unknown)}"
                )
            if len(summary) >= 4:
                break
        summary.append("更多計數可展開")
        self.funnel.setText("｜".join(summary))

    @staticmethod
    def _format_count(value: int | None) -> str:
        return "未提供" if value is None else str(value)
