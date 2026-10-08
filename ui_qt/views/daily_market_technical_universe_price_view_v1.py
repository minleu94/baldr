"""保存 full-N 技術來源的價格區間研究視圖（F07 v1）。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
from typing import Literal, cast

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QAbstractItemView,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app_module.daily_market_technical_parent_v4_query import (
    DailyMarketTechnicalRuleStateFilterV4,
    RuleState,
)
from app_module.daily_market_technical_universe_v4_catalog import (
    DailyMarketTechnicalUniverseV4Catalog,
    DailyMarketTechnicalUniverseV4CatalogEntry,
    DailyMarketTechnicalUniverseV4CatalogPage,
)
from app_module.daily_market_technical_universe_price_bookmark_v1 import (
    DailyMarketTechnicalUniversePriceBookmarkStateV1,
    DailyMarketTechnicalUniversePriceBookmarkV1,
    create_daily_market_technical_universe_price_bookmark_v1,
    read_daily_market_technical_universe_price_bookmark_v1,
)
from app_module.daily_market_technical_universe_price_comparison_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_COMPARISON_MAX_ITEMS,
    DailyMarketTechnicalUniversePriceComparisonV1,
    DailyMarketTechnicalUniversePriceComparisonV1Error,
    DailyMarketTechnicalUniversePriceSelectionV1,
    read_daily_market_technical_universe_price_comparison_v1,
)
from app_module.daily_market_technical_universe_price_query_v1 import (
    DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_PAGE_SIZE,
    DailyMarketTechnicalUniversePricePageRequestV1,
    DailyMarketTechnicalUniversePricePageV1,
    DailyMarketTechnicalUniversePriceQueryV1,
    DailyMarketTechnicalUniversePriceQueryV1Error,
    DailyMarketTechnicalUniversePriceReadSessionV1,
    DailyMarketTechnicalUniversePriceResultV1,
    DailyMarketTechnicalUniversePriceRowV1,
    DailyMarketTechnicalUniversePriceStockV1,
    open_daily_market_technical_universe_price_read_session_v1,
    open_daily_market_technical_universe_price_session_for_query_v1,
)
from ui_qt.models.saved_research_page_table_model import (
    SavedResearchPageTableModel,
    SavedResearchTableRow,
)
from ui_qt.workers.task_worker import TaskWorker


_STATE_LABELS: dict[str, str] = {
    "match": "符合",
    "no_match": "不符合",
    "unknown": "未知",
}
_STATE_ORDER: tuple[RuleState, ...] = ("match", "no_match", "unknown")
_FILTER_OPTIONS: tuple[tuple[str, str], ...] = (
    ("不限制", "all"),
    ("符合", "match"),
    ("不符合", "no_match"),
    ("符合／不符合", "match|no_match"),
    ("未知", "unknown"),
    ("符合／未知", "match|unknown"),
    ("不符合／未知", "no_match|unknown"),
    ("全部狀態", "match|no_match|unknown"),
)
_FILTER_STATES: dict[str, tuple[RuleState, ...] | None] = {
    "all": None,
    "match": ("match",),
    "no_match": ("no_match",),
    "match|no_match": ("match", "no_match"),
    "unknown": ("unknown",),
    "match|unknown": ("match", "unknown"),
    "no_match|unknown": ("no_match", "unknown"),
    "match|no_match|unknown": ("match", "no_match", "unknown"),
}
_FILTER_STATES_TO_ID = {
    states: key for key, states in _FILTER_STATES.items() if states is not None
}
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
_MAX_STOCK_FILTER_CODES = 100_000
_MAX_STOCK_FILTER_CHARS = _MAX_STOCK_FILTER_CODES * 16 + (_MAX_STOCK_FILTER_CODES - 1) * 2
_RULE_LABELS: dict[str, str] = {
    "ma5_20_golden_cross": "MA5／MA20 金叉",
    "kd_golden_cross": "K／D 金叉",
    "macd_golden_cross": "MACD 金叉",
    "volume_ratio_20_including_current": "量能比 20（含當日）",
    "volume_ratio_5_including_current": "量能比 5（含當日）",
}
_CATALOG_PAGE_SIZE = 50
_DEFAULT_PAGE_SIZE = 50
_PAGE_SIZE_OPTIONS = (50, 100, DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_PAGE_SIZE)


@dataclass(frozen=True, slots=True)
class _PriceViewState:
    session: DailyMarketTechnicalUniversePriceReadSessionV1
    query: DailyMarketTechnicalUniversePriceQueryV1
    result: DailyMarketTechnicalUniversePriceResultV1
    request: DailyMarketTechnicalUniversePricePageRequestV1
    page: DailyMarketTechnicalUniversePricePageV1


@dataclass(frozen=True, slots=True)
class _PriceQueryInputs:
    rule_state_filters: tuple[DailyMarketTechnicalRuleStateFilterV4, ...]
    combine_mode: Literal["AND", "OR"]
    stock_filter: tuple[str, ...]
    eligible_stock_codes: tuple[str, ...] | None
    minimum: Decimal | None
    minimum_inclusive: bool
    maximum: Decimal | None
    maximum_inclusive: bool
    unknown_policy: Literal["include", "exclude", "only"]
    descending: bool


@dataclass(frozen=True, slots=True)
class _QueuedOperation:
    name: str
    operation: Callable[..., object]
    apply: Callable[[object], None]
    kind: str


def _cancelled(cancel_callback: Callable[[], object] | None) -> bool:
    return cancel_callback is not None and bool(cancel_callback())


def _check_cancel(cancel_callback: Callable[[], object] | None) -> None:
    if _cancelled(cancel_callback):
        raise InterruptedError("technical_universe_price_view_cancelled")


def _parse_bound(value: str, *, field_name: str) -> Decimal | None:
    text = value.strip()
    if not text:
        return None
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"價格{field_name}必須是十進位數字。") from exc
    parts = parsed.as_tuple()
    if (
        not parsed.is_finite()
        or parsed <= 0
        or len(parts.digits) > 64
        or not isinstance(parts.exponent, int)
        or abs(parts.exponent) > 64
    ):
        raise ValueError(f"價格{field_name}必須是有限正數。")
    return parsed


def _parse_stock_filter(value: str) -> tuple[str, ...]:
    text = value.strip()
    if not text:
        return ()
    if len(text) > _MAX_STOCK_FILTER_CHARS:
        raise ValueError("股票代碼清單超過長度上限。")
    tokens = text.split(",")
    if len(tokens) > _MAX_STOCK_FILTER_CODES:
        raise ValueError("股票代碼清單超過 100,000 檔上限。")
    result: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        code = token.strip()
        if not code or _STOCK_CODE_RE.fullmatch(code) is None:
            raise ValueError("股票代碼格式錯誤；請用逗號分隔完整代碼。")
        if code in seen:
            raise ValueError(f"股票代碼重複：{code}。")
        seen.add(code)
        result.append(code)
    return tuple(result)


def _read_catalog_page(
    output_root: Path,
    cursor: str | None,
    cancel_callback: Callable[[], object] | None,
) -> DailyMarketTechnicalUniverseV4CatalogPage:
    _check_cancel(cancel_callback)
    page = DailyMarketTechnicalUniverseV4Catalog(output_root).list_page(
        limit=_CATALOG_PAGE_SIZE,
        cursor=cursor,
    )
    _check_cancel(cancel_callback)
    return page


def _entry_open_kwargs(
    output_root: Path,
    entry: DailyMarketTechnicalUniverseV4CatalogEntry,
) -> dict[str, object]:
    if not entry.is_selectable:
        raise ValueError("technical_universe_price_catalog_entry_not_selectable")
    pins = {
        "generation_identity_sha256": entry.generation_identity_sha256,
        "plan_identity_sha256": entry.plan_identity_sha256,
        "plan_sha256": entry.plan_bytes_sha256,
        "receipt_identity_sha256": entry.receipt_identity_sha256,
        "receipt_sha256": entry.receipt_bytes_sha256,
    }
    if any(not isinstance(value, str) for value in pins.values()):
        raise ValueError("technical_universe_price_catalog_pins_missing")
    return {"store_output_root": output_root, **pins}


def _source_matches_entry(
    query: DailyMarketTechnicalUniversePriceQueryV1,
    entry: DailyMarketTechnicalUniverseV4CatalogEntry,
) -> bool:
    source = query.source
    return (
        source.generation_identity_sha256 == entry.generation_identity_sha256
        and source.plan_identity_sha256 == entry.plan_identity_sha256
        and source.plan_sha256 == entry.plan_bytes_sha256
        and source.receipt_identity_sha256 == entry.receipt_identity_sha256
        and source.receipt_sha256 == entry.receipt_bytes_sha256
        and source.cohort_identity_sha256 == entry.cohort_identity_sha256
        and source.source_clock_identity_sha256 == entry.source_clock_identity_sha256
        and source.method_contracts_sha256 == entry.method_contracts_sha256
        and source.decision_date == entry.decision_date
        and source.universe_id == entry.universe_id
        and source.population_version == entry.population_version
        and source.receipt_status == entry.source_status
        and source.counts == entry.counts
    )


def _read_entry(
    output_root: Path,
    entry: DailyMarketTechnicalUniverseV4CatalogEntry,
    inputs: _PriceQueryInputs,
    page_size: int,
    cancel_callback: Callable[[], object] | None,
) -> _PriceViewState:
    _check_cancel(cancel_callback)
    session = open_daily_market_technical_universe_price_read_session_v1(
        **_entry_open_kwargs(output_root, entry),
        cancel_callback=cancel_callback,
    )
    query = session.create_query(
        rule_state_filters=inputs.rule_state_filters,
        combine_mode=inputs.combine_mode,
        technical_stock_filter=inputs.stock_filter,
        # 換到另一個來源時不沿用前一來源可能含有的內部 eligible 子集。
        eligible_stock_codes=None,
        min_close_price=inputs.minimum,
        min_inclusive=inputs.minimum_inclusive,
        max_close_price=inputs.maximum,
        max_inclusive=inputs.maximum_inclusive,
        unknown_price_policy=inputs.unknown_policy,
        descending=inputs.descending,
    )
    if not _source_matches_entry(query, entry):
        raise ValueError("technical_universe_price_catalog_source_mismatch")
    _check_cancel(cancel_callback)
    result = session.execute(query, cancel_callback=cancel_callback)
    _check_cancel(cancel_callback)
    request = result.create_page_request(0, page_size=page_size)
    page = result.read_page(request, cancel_callback=cancel_callback)
    page.to_dict()
    _check_cancel(cancel_callback)
    return _PriceViewState(session, query, result, request, page)


def _read_query(
    session: DailyMarketTechnicalUniversePriceReadSessionV1,
    inputs: _PriceQueryInputs,
    page_size: int,
    cancel_callback: Callable[[], object] | None,
) -> _PriceViewState:
    _check_cancel(cancel_callback)
    query = session.create_query(
        rule_state_filters=inputs.rule_state_filters,
        combine_mode=inputs.combine_mode,
        technical_stock_filter=inputs.stock_filter,
        eligible_stock_codes=inputs.eligible_stock_codes,
        min_close_price=inputs.minimum,
        min_inclusive=inputs.minimum_inclusive,
        max_close_price=inputs.maximum,
        max_inclusive=inputs.maximum_inclusive,
        unknown_price_policy=inputs.unknown_policy,
        descending=inputs.descending,
    )
    result = session.execute(query, cancel_callback=cancel_callback)
    _check_cancel(cancel_callback)
    request = result.create_page_request(0, page_size=page_size)
    page = result.read_page(request, cancel_callback=cancel_callback)
    page.to_dict()
    _check_cancel(cancel_callback)
    return _PriceViewState(session, query, result, request, page)


def _read_page(
    result: DailyMarketTechnicalUniversePriceResultV1,
    page_index: int,
    page_size: int,
    cancel_callback: Callable[[], object] | None,
) -> tuple[DailyMarketTechnicalUniversePricePageRequestV1, DailyMarketTechnicalUniversePricePageV1]:
    _check_cancel(cancel_callback)
    request = result.create_page_request(page_index, page_size=page_size)
    page = result.read_page(request, cancel_callback=cancel_callback)
    page.to_dict()
    _check_cancel(cancel_callback)
    return request, page


def _read_stock(
    result: DailyMarketTechnicalUniversePriceResultV1,
    request: DailyMarketTechnicalUniversePricePageRequestV1,
    stock_code: str,
    cancel_callback: Callable[[], object] | None,
) -> DailyMarketTechnicalUniversePriceStockV1:
    _check_cancel(cancel_callback)
    stock = result.read_stock_snapshot(request, stock_code, cancel_callback=cancel_callback)
    stock.to_dict()
    _check_cancel(cancel_callback)
    return stock


def _restore_selection(
    selection: DailyMarketTechnicalUniversePriceSelectionV1,
    cancel_callback: Callable[[], object] | None,
) -> _PriceViewState:
    _check_cancel(cancel_callback)
    query = selection.query
    session, reopened = open_daily_market_technical_universe_price_session_for_query_v1(
        query,
        cancel_callback=cancel_callback,
    )
    if reopened.to_json() != selection.query_json:
        raise ValueError("technical_universe_price_origin_query_mismatch")
    result = session.execute(reopened, cancel_callback=cancel_callback)
    request = result.create_page_request(
        selection.page_request.page_index,
        page_size=selection.page_request.page_size,
    )
    page = result.read_page(request, cancel_callback=cancel_callback)
    page.to_dict()
    actual = DailyMarketTechnicalUniversePriceSelectionV1.from_page(
        reopened,
        page,
        selection.stock_code,
    )
    if actual.to_dict() != selection.to_dict():
        raise ValueError("technical_universe_price_origin_pin_mismatch")
    _check_cancel(cancel_callback)
    return _PriceViewState(session, reopened, result, request, page)


class DailyMarketTechnicalUniversePriceV1View(QWidget):
    """F07 價格範圍、三態篩選、全域排序與 exact drill-down。"""

    stockSelected = Signal(object, object)
    comparisonReady = Signal(object)
    bookmarkPrepared = Signal(object)
    cancelRequested = Signal()

    @property
    def current_query(self) -> DailyMarketTechnicalUniversePriceQueryV1 | None:
        return self._state.query if self._state is not None else None

    @property
    def current_page(self) -> DailyMarketTechnicalUniversePricePageV1 | None:
        return self._state.page if self._state is not None else None

    @property
    def current_result(self) -> DailyMarketTechnicalUniversePriceResultV1 | None:
        return self._state.result if self._state is not None else None

    @property
    def selected_source(self) -> DailyMarketTechnicalUniverseV4CatalogEntry | None:
        item = self.sources.currentData()
        return item if isinstance(item, DailyMarketTechnicalUniverseV4CatalogEntry) else None

    @property
    def busy(self) -> bool:
        return self._worker is not None

    @property
    def workers_remaining(self) -> int:
        return int(self._worker is not None and self._worker.isRunning())

    def __init__(self, store_output_root: str | Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store_output_root = Path(store_output_root).absolute()
        self._worker: TaskWorker | None = None
        self._worker_kind = ""
        self._generation = 0
        self._closing = False
        self._pending: _QueuedOperation | None = None
        self._state: _PriceViewState | None = None
        self._catalog_page: DailyMarketTechnicalUniverseV4CatalogPage | None = None
        self._catalog_cursor: str | None = None
        self._rule_filters: dict[str, QComboBox] = {}
        self._basket: list[DailyMarketTechnicalUniversePriceSelectionV1] = []
        self._stock_filter_rejected_text: str | None = None
        self._drill_selection_code = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(7)
        title = QLabel("保存技術研究的收盤價範圍（F07 v1）")
        title.setObjectName("dailyMarketTechnicalPriceV1Title")
        root.addWidget(title)
        self.disclaimer = QLabel(
            "只讀已保存 full-N v4 來源中的收盤價；不查最新行情。資料可得時間未知，"
            "僅供當下重述研究，不授歷史 PIT／可交易資格；未知價格與排除、待處理分開顯示。"
        )
        self.disclaimer.setObjectName("dailyMarketTechnicalPriceV1Disclaimer")
        self.disclaimer.setWordWrap(True)
        self.disclaimer.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self.disclaimer)

        source_group = QGroupBox("已保存的 full-N 技術來源")
        source_layout = QGridLayout(source_group)
        self.sources = QComboBox()
        self.sources.setObjectName("dailyMarketTechnicalPriceV1Sources")
        self.refresh_sources_button = QPushButton("查詢版本")
        self.refresh_sources_button.setObjectName("dailyMarketTechnicalPriceV1RefreshSources")
        self.more_sources_button = QPushButton("更多版本")
        self.more_sources_button.setObjectName("dailyMarketTechnicalPriceV1MoreSources")
        self.more_sources_button.setEnabled(False)
        self.load_source_button = QPushButton("嚴格核驗並載入")
        self.load_source_button.setObjectName("dailyMarketTechnicalPriceV1LoadSource")
        self.cancel_button = QPushButton("取消目前工作")
        self.cancel_button.setObjectName("dailyMarketTechnicalPriceV1Cancel")
        self.cancel_button.setEnabled(False)
        source_layout.addWidget(self.sources, 0, 0, 1, 3)
        source_layout.addWidget(self.refresh_sources_button, 0, 3)
        source_layout.addWidget(self.more_sources_button, 0, 4)
        source_layout.addWidget(self.load_source_button, 1, 0)
        source_layout.addWidget(self.cancel_button, 1, 1)
        root.addWidget(source_group)

        self.source_pins = QLabel("尚未選取保存來源。")
        self.source_pins.setObjectName("dailyMarketTechnicalPriceV1SourcePins")
        self.source_pins.setWordWrap(True)
        self.source_pins.setTextFormat(Qt.TextFormat.PlainText)
        self.source_pins.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.source_pins)
        self.verified_pins = QLabel("尚未嚴格核驗價格來源。")
        self.verified_pins.setObjectName("dailyMarketTechnicalPriceV1VerifiedPins")
        self.verified_pins.setWordWrap(True)
        self.verified_pins.setTextFormat(Qt.TextFormat.PlainText)
        self.verified_pins.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.verified_pins)

        controls_group = QGroupBox("全母體條件與價格範圍")
        controls = QGridLayout(controls_group)
        self.combine_mode = QComboBox()
        self.combine_mode.setObjectName("dailyMarketTechnicalPriceV1CombineMode")
        self.combine_mode.addItem("全部符合（AND）", "AND")
        self.combine_mode.addItem("至少一項符合（OR）", "OR")
        self.stock_filter = QLineEdit()
        self.stock_filter.setObjectName("dailyMarketTechnicalPriceV1StockFilter")
        self.stock_filter.setMaxLength(_MAX_STOCK_FILTER_CHARS)
        self.stock_filter.setPlaceholderText("股票代碼，可逗號分隔；完整母體，不限 segment")
        self.eligible_stock_filter = QLineEdit()
        self.eligible_stock_filter.setObjectName("dailyMarketTechnicalPriceV1EligibleStockFilter")
        self.eligible_stock_filter.setMaxLength(_MAX_STOCK_FILTER_CHARS)
        self.eligible_stock_filter.setPlaceholderText("明示的可查股票代碼子集")
        self.eligible_stock_filter_enabled = QCheckBox("套用子集")
        self.eligible_stock_filter_enabled.setObjectName(
            "dailyMarketTechnicalPriceV1EligibleStockFilterEnabled"
        )
        self.minimum = QLineEdit()
        self.minimum.setObjectName("dailyMarketTechnicalPriceV1Minimum")
        self.minimum.setPlaceholderText("不限")
        self.minimum_inclusive = QCheckBox("含下限")
        self.minimum_inclusive.setObjectName("dailyMarketTechnicalPriceV1MinimumInclusive")
        self.minimum_inclusive.setChecked(True)
        self.maximum = QLineEdit()
        self.maximum.setObjectName("dailyMarketTechnicalPriceV1Maximum")
        self.maximum.setPlaceholderText("不限")
        self.maximum_inclusive = QCheckBox("含上限")
        self.maximum_inclusive.setObjectName("dailyMarketTechnicalPriceV1MaximumInclusive")
        self.maximum_inclusive.setChecked(True)
        self.unknown_policy = QComboBox()
        self.unknown_policy.setObjectName("dailyMarketTechnicalPriceV1UnknownPolicy")
        self.unknown_policy.addItem("未知價格也列入", "include")
        self.unknown_policy.addItem("排除未知價格", "exclude")
        self.unknown_policy.addItem("只看未知價格", "only")
        self.descending = QCheckBox("收盤價由高到低")
        self.descending.setObjectName("dailyMarketTechnicalPriceV1Descending")
        self.page_size = QComboBox()
        self.page_size.setObjectName("dailyMarketTechnicalPriceV1PageSize")
        for value in _PAGE_SIZE_OPTIONS:
            self.page_size.addItem(str(value), value)
        self.apply_query_button = QPushButton("套用條件")
        self.apply_query_button.setObjectName("dailyMarketTechnicalPriceV1ApplyQuery")
        controls.addWidget(QLabel("技術規則組合"), 0, 0)
        controls.addWidget(self.combine_mode, 0, 1)
        controls.addWidget(QLabel("股票篩選"), 0, 2)
        controls.addWidget(self.stock_filter, 0, 3, 1, 3)
        controls.addWidget(QLabel("收盤價下限（TWD／股）"), 1, 0)
        controls.addWidget(self.minimum, 1, 1)
        controls.addWidget(self.minimum_inclusive, 1, 2)
        controls.addWidget(QLabel("收盤價上限（TWD／股）"), 1, 3)
        controls.addWidget(self.maximum, 1, 4)
        controls.addWidget(self.maximum_inclusive, 1, 5)
        controls.addWidget(QLabel("未知價格"), 2, 0)
        controls.addWidget(self.unknown_policy, 2, 1)
        controls.addWidget(self.descending, 2, 2)
        controls.addWidget(QLabel("每頁"), 2, 3)
        controls.addWidget(self.page_size, 2, 4)
        controls.addWidget(self.apply_query_button, 2, 5)
        controls.addWidget(QLabel("可查股票子集"), 3, 0)
        controls.addWidget(self.eligible_stock_filter, 3, 1, 1, 4)
        controls.addWidget(self.eligible_stock_filter_enabled, 3, 5)
        self.rule_filter_host = QWidget()
        self.rule_filter_layout = QGridLayout(self.rule_filter_host)
        self.rule_filter_layout.setContentsMargins(0, 0, 0, 0)
        controls.addWidget(self.rule_filter_host, 4, 0, 1, 6)
        root.addWidget(controls_group)

        page_controls = QHBoxLayout()
        self.previous_page_button = QPushButton("上一頁")
        self.previous_page_button.setObjectName("dailyMarketTechnicalPriceV1PreviousPage")
        self.next_page_button = QPushButton("下一頁")
        self.next_page_button.setObjectName("dailyMarketTechnicalPriceV1NextPage")
        self.page_label = QLabel("尚無頁面")
        self.page_label.setObjectName("dailyMarketTechnicalPriceV1PageLabel")
        page_controls.addWidget(self.previous_page_button)
        page_controls.addWidget(self.page_label, 1)
        page_controls.addWidget(self.next_page_button)
        root.addLayout(page_controls)

        basket_controls = QHBoxLayout()
        self.add_comparison_button = QPushButton("加入比較籃")
        self.add_comparison_button.setObjectName("dailyMarketTechnicalPriceV1AddComparison")
        self.run_comparison_button = QPushButton("重驗並比較")
        self.run_comparison_button.setObjectName("dailyMarketTechnicalPriceV1RunComparison")
        self.clear_comparison_button = QPushButton("清空比較籃")
        self.clear_comparison_button.setObjectName("dailyMarketTechnicalPriceV1ClearComparison")
        self.bookmark_button = QPushButton("準備價格研究收藏")
        self.bookmark_button.setObjectName("dailyMarketTechnicalPriceV1Bookmark")
        self.basket_label = QLabel("比較籃：0 檔")
        self.basket_label.setObjectName("dailyMarketTechnicalPriceV1BasketLabel")
        basket_controls.addWidget(self.add_comparison_button)
        basket_controls.addWidget(self.run_comparison_button)
        basket_controls.addWidget(self.clear_comparison_button)
        basket_controls.addWidget(self.bookmark_button)
        basket_controls.addWidget(self.basket_label, 1)
        root.addLayout(basket_controls)

        self.summary = QLabel("尚未載入已保存來源。")
        self.summary.setObjectName("dailyMarketTechnicalPriceV1Summary")
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self.summary)
        self.table = QTableView()
        self.table.setObjectName("dailyMarketTechnicalPriceV1Table")
        self.table.setAccessibleName("全域價格排序後的已保存技術研究頁面")
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(False)
        self.results_model: SavedResearchPageTableModel[DailyMarketTechnicalUniversePriceRowV1] = (
            SavedResearchPageTableModel(
                ("股票", "收盤價（TWD／股）", "價格日期", "價格狀態", "MA5／MA20 金叉", "K／D 金叉", "MACD 金叉", "量能比 20", "量能比 5"),
                maximum_page_size=DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_MAX_PAGE_SIZE,
                parent=None,
            )
        )
        self.table.setModel(self.results_model)
        self.table.selectionModel().selectionChanged.connect(self._set_enabled_state)
        self.table.selectionModel().currentChanged.connect(self._on_table_current_changed)
        self.table.doubleClicked.connect(self._on_row_activated)
        root.addWidget(self.table, 1)
        self.status = QLabel("尚未載入已保存來源。")
        self.status.setObjectName("dailyMarketTechnicalPriceV1Status")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self.status)

        self.refresh_sources_button.clicked.connect(self.refresh_sources)
        self.more_sources_button.clicked.connect(self.load_more_sources)
        self.load_source_button.clicked.connect(self.load_selected_source)
        self.apply_query_button.clicked.connect(self.apply_query)
        self.previous_page_button.clicked.connect(self.previous_page)
        self.next_page_button.clicked.connect(self.next_page)
        self.cancel_button.clicked.connect(self.cancel)
        self.add_comparison_button.clicked.connect(self.add_selected_to_comparison)
        self.run_comparison_button.clicked.connect(self.run_comparison)
        self.clear_comparison_button.clicked.connect(self.clear_comparison)
        self.bookmark_button.clicked.connect(self.prepare_bookmark)
        self.sources.currentIndexChanged.connect(self._show_selected_metadata)
        self._set_enabled_state()

    def refresh_sources(self) -> None:
        self._catalog_cursor = None
        self._start(
            "查詢保存價格來源",
            lambda cancel_callback=None: _read_catalog_page(
                self.store_output_root,
                None,
                cancel_callback,
            ),
            self._apply_catalog_page,
            kind="catalog",
        )

    def load_more_sources(self) -> None:
        cursor = self._catalog_cursor
        if cursor is None:
            return
        self._start(
            "讀取更多保存來源",
            lambda cancel_callback=None: _read_catalog_page(
                self.store_output_root,
                cursor,
                cancel_callback,
            ),
            self._append_catalog_page,
            kind="catalog",
        )

    def load_selected_source(self) -> None:
        entry = self.selected_source
        if entry is None or not entry.is_selectable:
            self.status.setText("所選列尚未完成 metadata 核驗，不能讀取。")
            return
        try:
            inputs = self._query_inputs()
            page_size = self._selected_page_size()
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self._start(
            "嚴格核驗並載入價格來源",
            lambda cancel_callback=None: _read_entry(
                self.store_output_root,
                entry,
                inputs,
                page_size,
                cancel_callback,
            ),
            self._apply_state,
            kind="source_read",
        )

    def apply_query(self) -> None:
        state = self._state
        if state is None:
            self.status.setText("請先嚴格核驗並載入一個保存來源。")
            return
        try:
            inputs = self._query_inputs()
            page_size = self._selected_page_size()
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self._start(
            "套用全母體價格條件",
            lambda cancel_callback=None: _read_query(
                state.session,
                inputs,
                page_size,
                cancel_callback,
            ),
            self._apply_state,
            kind="query",
        )

    def previous_page(self) -> None:
        self._move_page(-1)

    def next_page(self) -> None:
        self._move_page(1)

    def _move_page(self, offset: int) -> None:
        state = self._state
        if state is None:
            return
        target = state.request.page_index + offset
        if target < 0 or target >= state.page.page_count:
            return
        size = self._selected_page_size()
        self._start(
            "讀取價格研究頁面",
            lambda cancel_callback=None: (
                state,
                *_read_page(state.result, target, size, cancel_callback),
            ),
            self._apply_page_state,
            kind="page",
        )

    def add_selected_to_comparison(self) -> None:
        state = self._state
        row = self._selected_row()
        if state is None or row is None:
            self.status.setText("請先選取目前已核驗頁面中的股票。")
            return
        try:
            selection = DailyMarketTechnicalUniversePriceSelectionV1.from_page(
                state.query,
                state.page,
                row.technical_row.stock_code,
            )
        except ValueError as exc:
            self.status.setText(f"比較選取未建立：{getattr(exc, 'code', str(exc))}。")
            return
        if any(item.key == selection.key for item in self._basket):
            self.status.setText("比較籃已有相同來源、查詢、頁面與股票。")
            return
        if len(self._basket) >= DAILY_MARKET_TECHNICAL_UNIVERSE_PRICE_COMPARISON_MAX_ITEMS:
            self.status.setText("比較籃已達 256 欄上限。")
            return
        self._basket.append(selection)
        self._render_basket_label()
        self.status.setText(
            f"已保留 {selection.stock_code} 的原價格查詢與頁面來源；切換查詢不會改寫此選取。"
        )

    def clear_comparison(self) -> None:
        self._basket.clear()
        self._render_basket_label()
        self.status.setText("比較籃已清空。")

    def run_comparison(self) -> None:
        if len(self._basket) < 2:
            self.status.setText("至少加入 2 檔，才能重驗並比較。")
            return
        selections = tuple(self._basket)
        self._start(
            "重驗價格比較來源",
            lambda cancel_callback=None: read_daily_market_technical_universe_price_comparison_v1(
                selections,
                cancel_callback=cancel_callback,
            ),
            self._apply_comparison,
            kind="comparison",
        )

    def prepare_bookmark(self) -> None:
        state = self._state
        row = self._selected_row()
        if state is None or row is None:
            self.status.setText("請先選取目前已核驗頁面中的股票，再準備收藏。")
            return
        if len(self._basket) == 1:
            self.status.setText("比較籃只有 1 檔；請清空或補足至少 2 檔後再收藏。")
            return
        current_state = state
        code = row.technical_row.stock_code
        scroll_position = int(self.table.verticalScrollBar().value())
        selections = tuple(self._basket)
        self._start(
            "準備價格研究收藏",
            lambda cancel_callback=None: (
                _check_cancel(cancel_callback),
                create_daily_market_technical_universe_price_bookmark_v1(
                    current_state.query,
                    current_state.page,
                    code,
                    scroll_position=scroll_position,
                    comparison_selections=selections,
                ),
                _check_cancel(cancel_callback),
            )[1],
            self._apply_bookmark,
            kind="bookmark_prepare",
        )

    def restore_bookmark(self, bookmark: DailyMarketTechnicalUniversePriceBookmarkV1) -> bool:
        if not isinstance(bookmark, DailyMarketTechnicalUniversePriceBookmarkV1):
            self.status.setText("收藏格式不符；未接受重開要求。")
            return False
        return self._start(
            "重驗價格研究收藏",
            lambda cancel_callback=None: read_daily_market_technical_universe_price_bookmark_v1(
                bookmark,
                cancel_callback=cancel_callback,
            ),
            self._apply_bookmark_state,
            kind="bookmark_restore",
        )

    def restore_bookmark_state(self, state: DailyMarketTechnicalUniversePriceBookmarkStateV1) -> bool:
        """套用控制項同次 fresh read 的 issued 結果，不重新開來源。"""

        if self._closing:
            self.status.setText("價格研究視圖正在關閉；未套用收藏。")
            return False
        if self._worker is not None or self._pending is not None:
            self.status.setText("價格研究視圖仍有背景工作；收藏保持未套用。")
            return False
        return self._apply_bookmark_state_value(state)

    def restore_selection(self, selection: DailyMarketTechnicalUniversePriceSelectionV1) -> bool:
        """fresh 重開明示的原 query/page/code；成功前保留目前表格。"""

        if not isinstance(selection, DailyMarketTechnicalUniversePriceSelectionV1):
            self.status.setText("返回來源格式不符；未接受重開要求。")
            return False
        return self._start(
            f"返回 {selection.stock_code} 原價格查詢",
            lambda cancel_callback=None: _restore_selection(selection, cancel_callback),
            lambda value: self._apply_state(value, selected_code=selection.stock_code),
            kind="origin_restore",
        )

    def restore_origin(self, selection: DailyMarketTechnicalUniversePriceSelectionV1) -> bool:
        """按明示的 F07 原 selection 重開來源；True 只表示已接受或排隊。"""

        return self.restore_selection(selection)

    def select_stock_code(self, stock_code: str) -> bool:
        index = self.results_model.index_for_stock(stock_code)
        if not index.isValid():
            return False
        self.table.setCurrentIndex(index)
        return True

    def cancel(self) -> None:
        if self._worker is None:
            return
        self._generation += 1
        self._pending = None
        self._worker.cancel(cooperative=True, wait=False)
        self.status.setText("已要求目前工作取消；等待安全停止後保留原核驗結果。")
        self.cancelRequested.emit()

    def begin_shutdown(self) -> bool:
        """非阻塞地取消工作；True 僅表示 native worker 已停止。"""

        self._closing = True
        self._generation += 1
        self._pending = None
        worker = self._worker
        if worker is None:
            self._set_enabled_state()
            return True
        if worker.isRunning():
            worker.cancel(cooperative=True, wait=False)
            self.cancelRequested.emit()
        self._set_enabled_state()
        return not worker.isRunning()

    def _query_inputs(self) -> _PriceQueryInputs:
        minimum = _parse_bound(self.minimum.text(), field_name="下限")
        maximum = _parse_bound(self.maximum.text(), field_name="上限")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("價格下限不可高於上限。")
        stock_codes = _parse_stock_filter(self.stock_filter.text())
        parsed_eligible_codes = _parse_stock_filter(self.eligible_stock_filter.text())
        eligible_codes = (
            parsed_eligible_codes if self.eligible_stock_filter_enabled.isChecked() else None
        )
        filters: list[DailyMarketTechnicalRuleStateFilterV4] = []
        for key, combo in self._rule_filters.items():
            selected = cast(str, combo.currentData())
            states = _FILTER_STATES.get(selected)
            if selected not in _FILTER_STATES:
                raise ValueError("規則狀態篩選值無效。")
            if states is not None:
                filters.append(DailyMarketTechnicalRuleStateFilterV4.create(key, states))
        policy = cast(str, self.unknown_policy.currentData())
        if policy not in {"include", "exclude", "only"}:
            raise ValueError("未知價格政策無效。")
        mode = cast(str, self.combine_mode.currentData())
        if mode not in {"AND", "OR"}:
            raise ValueError("規則組合方式無效。")
        return _PriceQueryInputs(
            rule_state_filters=tuple(filters),
            combine_mode=cast(Literal["AND", "OR"], mode),
            stock_filter=stock_codes,
            eligible_stock_codes=eligible_codes,
            minimum=minimum,
            minimum_inclusive=self.minimum_inclusive.isChecked(),
            maximum=maximum,
            maximum_inclusive=self.maximum_inclusive.isChecked(),
            unknown_policy=cast(Literal["include", "exclude", "only"], policy),
            descending=self.descending.isChecked(),
        )

    def _selected_page_size(self) -> int:
        value = self.page_size.currentData()
        if type(value) is not int or value not in _PAGE_SIZE_OPTIONS:
            return _DEFAULT_PAGE_SIZE
        return value

    def _apply_catalog_page(self, value: object) -> None:
        if not isinstance(value, DailyMarketTechnicalUniverseV4CatalogPage):
            self.status.setText("來源清單格式不符；目前表格保留。")
            return
        self._catalog_page = value
        self._catalog_cursor = value.next_cursor
        self.sources.clear()
        for entry in value.rows:
            self.sources.addItem(self._catalog_label(entry), entry)
        self.more_sources_button.setEnabled(value.next_cursor is not None and not self._closing)
        if not value.scan_complete:
            self.status.setText("來源清單掃描尚未完成；目前只顯示有界診斷列，不能宣稱完整。")
        elif value.source_inventory_state == "no_saved_generations":
            self.status.setText("尚無保存來源；沒有可查詢的價格研究版本。")
        else:
            self.status.setText(f"讀得 {len(value.rows)} 列 catalog metadata；尚未完成個別來源 strict 核驗。")
        self._show_selected_metadata()

    def _append_catalog_page(self, value: object) -> None:
        if not isinstance(value, DailyMarketTechnicalUniverseV4CatalogPage):
            self.status.setText("來源續頁格式不符；目前表格保留。")
            return
        previous = self._catalog_page
        if previous is None or not previous.scan_complete or not value.scan_complete:
            self.status.setText("來源續頁沒有完整 inventory 證據；未併入清單。")
            return
        if previous.inventory_sha256 != value.inventory_sha256:
            self.status.setText("來源清單在續頁期間改變；請重新查詢來源。")
            return
        self._catalog_page = value
        self._catalog_cursor = value.next_cursor
        for entry in value.rows:
            self.sources.addItem(self._catalog_label(entry), entry)
        self.more_sources_button.setEnabled(value.next_cursor is not None and not self._closing)
        self.status.setText(f"再讀得 {len(value.rows)} 列 metadata；每列仍須 strict 核驗後才能查詢。")

    @staticmethod
    def _catalog_label(entry: DailyMarketTechnicalUniverseV4CatalogEntry) -> str:
        if entry.metadata_state == "diagnostic":
            return f"診斷｜{entry.relative_path}｜{entry.diagnostic_code or 'metadata_invalid'}"
        counts = entry.counts
        declared = counts.declared_count if counts is not None else 0
        processed = counts.processed_count if counts is not None else 0
        pending = counts.pending_count if counts is not None else 0
        return (
            f"{entry.decision_date}｜{entry.universe_id}｜{entry.population_version}｜"
            f"宣告 {declared}／已處理 {processed}／待處理 {pending}｜metadata 未核"
        )

    def _show_selected_metadata(self, *_args: object) -> None:
        entry = self.selected_source
        if entry is None:
            self.source_pins.setText("尚未選取 catalog metadata；目前表格來源另列於下方。")
            self._set_enabled_state()
            return
        if entry.metadata_state == "diagnostic" or not entry.is_selectable:
            self.source_pins.setText(
                f"所選列不能作為 strict 價格來源：{entry.diagnostic_code or 'metadata_unverified_or_invalid'}。"
            )
            self._set_enabled_state()
            return
        self.source_pins.setText(
            "選取列目前只是 metadata，尚未 strict 核驗；表格若已有內容仍屬原來源。\n"
            f"日期：{entry.decision_date}；狀態：{entry.source_status}；母體：{entry.population_state}\n"
            f"generation：{entry.generation_identity_sha256}\n"
            f"plan identity／bytes：{entry.plan_identity_sha256}／{entry.plan_bytes_sha256}\n"
            f"receipt identity／bytes：{entry.receipt_identity_sha256}／{entry.receipt_bytes_sha256}"
        )
        self._set_enabled_state()

    def _apply_state(self, value: object, *, selected_code: str | None = None) -> bool:
        if not isinstance(value, _PriceViewState):
            self.status.setText("價格查詢回傳格式不符；目前已核驗表格保留。")
            return False
        if (
            not isinstance(value.session, DailyMarketTechnicalUniversePriceReadSessionV1)
            or not isinstance(value.query, DailyMarketTechnicalUniversePriceQueryV1)
            or not isinstance(value.result, DailyMarketTechnicalUniversePriceResultV1)
            or not isinstance(value.page, DailyMarketTechnicalUniversePricePageV1)
            or value.result.query != value.query
            or not value.session.matches_query(value.query)
            or value.request != value.page.request
            or value.request.query_identity_sha256 != value.query.query_identity_sha256
            or value.page.result_identity_sha256 != value.result.result_identity_sha256
            or value.page.request.operation_identity_sha256 != value.result.operation_identity_sha256
        ):
            self.status.setText("價格來源或頁面 pins 不符；目前已核驗表格保留。")
            return False
        value.page.to_dict()
        self._state = value
        self._ensure_rule_filters(value.query.source.method_rule_keys)
        self._set_controls(value.query)
        self._render_page(value.page, selected_code=selected_code)
        self._show_verified_pins(value.query)
        self._set_enabled_state()
        population_state = "完整" if value.page.full_population_complete else "未完整"
        self.status.setText(
            f"來源與價格索引已 strict 核驗；完整母體狀態：{population_state}。"
            "未知價格仍按所選政策呈現。"
        )
        return True

    def _apply_page_state(self, value: object) -> None:
        if (
            not isinstance(value, tuple)
            or len(value) != 3
            or not isinstance(value[0], _PriceViewState)
            or not isinstance(value[1], DailyMarketTechnicalUniversePricePageRequestV1)
            or not isinstance(value[2], DailyMarketTechnicalUniversePricePageV1)
        ):
            self.status.setText("頁面回傳格式不符；目前表格保留。")
            return
        old_state, request, page = value
        if (
            self._state is None
            or old_state.query.to_json() != self._state.query.to_json()
            or old_state.result.result_identity_sha256 != self._state.result.result_identity_sha256
            or page.request != request
        ):
            self.status.setText("頁面來源已變更；晚到頁面未套用。")
            return
        updated = _PriceViewState(old_state.session, old_state.query, old_state.result, request, page)
        self._apply_state(updated)

    def _render_page(self, page: DailyMarketTechnicalUniversePricePageV1, *, selected_code: str | None) -> None:
        source = self._state.query.source if self._state is not None else None
        if source is None:
            self.results_model.replace_page(())
            return
        expected_keys = source.method_rule_keys
        rows: list[SavedResearchTableRow[DailyMarketTechnicalUniversePriceRowV1]] = []
        for row in page.rows:
            rule_keys = tuple(rule.key for rule in row.technical_row.rules)
            if rule_keys != expected_keys:
                raise ValueError("technical_universe_price_view_rule_set_mismatch")
            fact = row.price_fact
            close_text = format(fact.close_price, "f") if fact.close_price is not None else "未知"
            date_text = fact.observation_date.isoformat() if fact.observation_date is not None else "未知"
            state_text = "符合價格條件" if row.price_state == "pass" else "價格未知"
            cells = [row.technical_row.stock_code, close_text, date_text, state_text]
            tooltip_lines = [
                f"股票：{row.technical_row.stock_code}",
                f"收盤價：{close_text} TWD／股；日期：{date_text}",
                f"價格狀態：{state_text}",
                f"保存來源 identity：{fact.source_identity}",
                f"保存 snapshot：{fact.snapshot_identity_sha256}",
                f"原始列 fingerprint：{fact.raw_row_fingerprint_sha256 or '未知'}",
                "資料可得時間未知；只供當下重述研究；不授歷史 PIT／可交易資格。",
            ]
            if fact.reason_codes:
                tooltip_lines.append("價格未知原因：" + "；".join(fact.reason_codes))
            for rule in row.technical_row.rules:
                status = _STATE_LABELS.get(rule.state, "未知")
                if rule.ratio is not None:
                    status += f"｜比率 {rule.ratio}"
                cells.append(status)
                detail = [
                    f"{_RULE_LABELS.get(rule.key, rule.key)}：{_STATE_LABELS.get(rule.state, '未知')}",
                    f"方法：{rule.method_id} {rule.version}",
                    f"決策截止：{rule.decision_cutoff.isoformat()}；特徵日：{rule.feature_date or '未知'}；前一特徵日：{rule.previous_feature_date or '未知'}",
                    f"來源：{rule.source_identity}；lookahead：{rule.lookahead_check}；可得性：{rule.availability_result}",
                ]
                if rule.unknown_reasons:
                    detail.append("規則未知原因：" + "；".join(rule.unknown_reasons))
                tooltip_lines.extend(detail)
            full_tooltip = "\n".join(tooltip_lines)
            rows.append(SavedResearchTableRow(row.technical_row.stock_code, row, tuple(cells), (full_tooltip,) * len(cells)))
        self.results_model.replace_page(tuple(rows))
        if selected_code is not None:
            self.select_stock_code(selected_code)
        counts = page.source_counts
        prices = page.price_counts
        query = self._state.query if self._state is not None else None
        if query is None:
            return
        completion = "完整" if page.full_population_complete else "未完整"
        messages = [
            f"{query.source.universe_id}｜{query.source.population_version}｜決策日 {query.source.decision_date.isoformat()}",
            f"來源母體：{completion}；宣告 {counts.declared_count}、納入 {counts.included_count}、排除 {counts.excluded_count}、已處理 {counts.processed_count}、待處理 {counts.pending_count}、缺資料 {counts.missing_data_count}",
            f"技術／股票條件符合已處理分母 {prices.base_matching_count}；價格符合 {prices.pass_count}、不符合 {prices.fail_count}、未知 {prices.unknown_count}；目前政策結果 {page.matching_count}",
            f"目前第 {page.request.page_index + 1}/{page.page_count} 頁，每頁 {page.request.page_size}；全域排序為收盤價{'由高到低' if query.descending else '由低到高'}，未知價格固定置尾，同價以股票代碼升序。",
            "收盤價來自此保存來源的對應觀測日；可得時間未知，不代表目前行情或 PIT 資格。",
        ]
        if query.eligible_stock_codes is not None:
            messages.append(f"明示可查股票子集：{len(query.eligible_stock_codes)} 檔。")
        if self._state.result.exclusion_reasons:
            messages.append("排除理由：" + "；".join(f"{code}：{reason}" for code, reason in self._state.result.exclusion_reasons))
        self.summary.setText("\n".join(messages))
        if page.matching_count == 0:
            self.page_label.setText("0 筆符合｜0 頁")
        else:
            self.page_label.setText(
                f"第 {page.request.page_index + 1}/{page.page_count} 頁｜符合 {page.matching_count} 筆"
            )

    def _show_verified_pins(self, query: DailyMarketTechnicalUniversePriceQueryV1) -> None:
        source = query.source
        self.verified_pins.setText(
            "本頁由一次 strict full-N source session 與價格索引產生；catalog metadata 不作可用資格。\n"
            f"store：{source.store_output_root}\n"
            f"generation：{source.generation_identity_sha256}\n"
            f"plan：{source.plan_identity_sha256}／{source.plan_sha256}\n"
            f"receipt：{source.receipt_identity_sha256}／{source.receipt_sha256}（{source.receipt_status}）\n"
            f"cohort／clock／methods：{source.cohort_identity_sha256}／{source.source_clock_identity_sha256}／{source.method_contracts_sha256}\n"
            f"價格索引：{source.price_index_identity_sha256}；{source.price_index_bytes} bytes；可得時間未知，PIT=false。"
        )

    def _ensure_rule_filters(self, keys: Sequence[str]) -> None:
        while self.rule_filter_layout.count():
            item = self.rule_filter_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._rule_filters.clear()
        for index, key in enumerate(keys):
            label = QLabel(_RULE_LABELS.get(key, key))
            combo = QComboBox()
            combo.setObjectName(f"dailyMarketTechnicalPriceV1Filter_{key}")
            for option_label, option in _FILTER_OPTIONS:
                combo.addItem(option_label, option)
            row, column = divmod(index, 3)
            self.rule_filter_layout.addWidget(label, row, column * 2)
            self.rule_filter_layout.addWidget(combo, row, column * 2 + 1)
            self._rule_filters[key] = combo

    def _set_controls(self, query: DailyMarketTechnicalUniversePriceQueryV1) -> None:
        self.combine_mode.setCurrentIndex(self.combine_mode.findData(query.combine_mode))
        self.stock_filter.setText(", ".join(query.technical_stock_filter))
        self.eligible_stock_filter_enabled.setChecked(query.eligible_stock_codes is not None)
        self.eligible_stock_filter.setText(", ".join(query.eligible_stock_codes or ()))
        self.minimum.setText(format(query.min_close_price, "f") if query.min_close_price is not None else "")
        self.maximum.setText(format(query.max_close_price, "f") if query.max_close_price is not None else "")
        self.minimum_inclusive.setChecked(query.min_inclusive)
        self.maximum_inclusive.setChecked(query.max_inclusive)
        self.unknown_policy.setCurrentIndex(self.unknown_policy.findData(query.unknown_price_policy))
        self.descending.setChecked(query.descending)
        states_by_key = {item.rule_key: item.states for item in query.rule_state_filters}
        for key, combo in self._rule_filters.items():
            states = states_by_key.get(key)
            option = "all" if states is None else _FILTER_STATES_TO_ID.get(states, "")
            selected_index = combo.findData(option)
            if selected_index < 0:
                raise ValueError("technical_universe_price_view_filter_state_invalid")
            combo.setCurrentIndex(selected_index)

    def _selected_row(self) -> DailyMarketTechnicalUniversePriceRowV1 | None:
        index = self.table.currentIndex()
        if not index.isValid():
            return None
        row = self.results_model.row_at(index.row())
        return row if isinstance(row, DailyMarketTechnicalUniversePriceRowV1) else None

    def _on_row_activated(self, index: QModelIndex) -> None:
        state = self._state
        if state is None or not index.isValid():
            return
        row = self.results_model.row_at(index.row())
        if not isinstance(row, DailyMarketTechnicalUniversePriceRowV1):
            return
        code = row.technical_row.stock_code
        try:
            selection = DailyMarketTechnicalUniversePriceSelectionV1.from_page(
                state.query,
                state.page,
                code,
            )
        except ValueError as exc:
            self.status.setText(
                f"個股來源錨點無法建立：{getattr(exc, 'code', str(exc))}。"
            )
            return
        self._drill_selection_code = code
        self._start(
            f"讀取 {code} 價格來源個股",
            lambda cancel_callback=None: _read_stock(
                state.result,
                state.request,
                code,
                cancel_callback,
            ),
            lambda value: self._apply_stock(value, state, selection),
            kind="stock",
        )

    def _apply_stock(
        self,
        value: object,
        origin: _PriceViewState,
        selection: DailyMarketTechnicalUniversePriceSelectionV1,
    ) -> None:
        if not isinstance(value, DailyMarketTechnicalUniversePriceStockV1):
            self.status.setText("個股重開回傳格式不符；目前表格保留。")
            return
        current_row = self._selected_row()
        if self._state is not origin or current_row is None or (
            current_row.technical_row.stock_code != selection.stock_code
            or value.request != origin.request
            or value.result_identity_sha256 != origin.result.result_identity_sha256
            or value.row.row_identity_sha256 != next(
                (row.row_identity_sha256 for row in origin.page.rows if row.technical_row.stock_code == value.stock_code),
                None,
            )
            or value.stock_code != selection.stock_code
            or value.row.price_fact.snapshot_identity_sha256 != selection.snapshot_identity_sha256
            or value.row.price_fact.source_identity != selection.row_source_identity
        ):
            self.status.setText("個股來源已變更；晚到結果未送出。")
            return
        try:
            value.to_dict()
            page_selection = DailyMarketTechnicalUniversePriceSelectionV1.from_page(
                origin.query,
                origin.page,
                selection.stock_code,
            )
        except ValueError as exc:
            self.status.setText(
                f"個股來源錨點核驗失敗；晚到結果未送出（{getattr(exc, 'code', str(exc))}）。"
            )
            return
        if page_selection.to_dict() != selection.to_dict():
            self.status.setText("個股來源 selection 已變更；晚到結果未送出。")
            return
        self.stockSelected.emit(value, selection)
        self.status.setText(f"已核驗 {value.stock_code} 的原價格來源 snapshot，可供外層開啟個股研究。")

    def _on_table_current_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        worker = self._worker
        if worker is None or self._worker_kind != "stock" or self._closing:
            return
        current_row = self.results_model.row_at(current.row()) if current.isValid() else None
        current_code = (
            current_row.technical_row.stock_code
            if isinstance(current_row, DailyMarketTechnicalUniversePriceRowV1)
            else ""
        )
        if current_code == self._drill_selection_code:
            return
        self._generation += 1
        self._pending = None
        worker.cancel(cooperative=True, wait=False)
        self._drill_selection_code = ""
        self.status.setText("個股選取已變更；正在取消舊來源讀取，晚到結果不會送出。")

    def _apply_comparison(self, value: object) -> None:
        if not isinstance(value, DailyMarketTechnicalUniversePriceComparisonV1):
            self.status.setText("比較結果格式不符；未發布部分比較。")
            return
        value.to_json()
        self.comparisonReady.emit(value)
        self.status.setText(f"已 fresh 重驗 {len(value.columns)} 個比較欄；各欄日期與來源各自列明。")

    def _apply_bookmark(self, value: object) -> None:
        if not isinstance(value, DailyMarketTechnicalUniversePriceBookmarkV1):
            self.status.setText("收藏準備格式不符；尚未送出保存。")
            return
        value.to_json()
        self.status.setText("已準備價格查詢、頁面、所選股票與比較籃收藏；尚未寫入觀察清單。")
        self.bookmarkPrepared.emit(value)

    def _apply_bookmark_state(self, value: object) -> None:
        self._apply_bookmark_state_value(value)

    def _apply_bookmark_state_value(self, value: object) -> bool:
        if not isinstance(value, DailyMarketTechnicalUniversePriceBookmarkStateV1):
            self.status.setText("收藏重開回傳格式不符；目前表格保留。")
            return False
        try:
            bookmark = value.bookmark
            bookmark.to_json()
            verified = value.selected
            session = verified.session
            query = verified.query
            result = verified.result
            request = verified.request
            page = verified.page
            selection = verified.selection
            session._validate_issued()
            result.to_dict()
            page.to_dict()
            request.to_dict()
            selection.to_dict()
            if (
                result._session is not session
                or not session.matches_query(query)
                or result.query.to_json() != query.to_json()
                or request != page.request
                or request.operation_identity_sha256 != result.operation_identity_sha256
                or page.result_identity_sha256 != result.result_identity_sha256
                or selection.stock_code != bookmark.stock_code
                or selection.to_dict() != bookmark.selected.to_dict()
            ):
                raise ValueError("technical_universe_price_bookmark_issued_anchors_mismatch")
            exact_selection = DailyMarketTechnicalUniversePriceSelectionV1.from_page(
                query,
                page,
                bookmark.stock_code,
            )
            if exact_selection.to_dict() != selection.to_dict():
                raise ValueError("technical_universe_price_bookmark_selection_mismatch")
            comparison_columns = (
                tuple(column.selection.to_dict() for column in value.comparison.columns)
                if value.comparison is not None
                else ()
            )
            expected_comparisons = tuple(
                item.to_dict() for item in bookmark.comparison_selections
            )
            if comparison_columns != expected_comparisons:
                raise ValueError("technical_universe_price_bookmark_comparison_mismatch")
            if value.comparison is not None:
                value.comparison.to_json()
            for row in page.rows:
                if tuple(rule.key for rule in row.technical_row.rules) != query.source.method_rule_keys:
                    raise ValueError("technical_universe_price_bookmark_rule_set_mismatch")
        except (AttributeError, TypeError, ValueError) as exc:
            self.status.setText(
                f"收藏的 exact source anchors 無效；目前已核驗表格保留（{getattr(exc, 'code', str(exc))}）。"
            )
            return False

        next_view_state = _PriceViewState(session, query, result, request, page)
        if not self._apply_state(next_view_state, selected_code=bookmark.stock_code):
            return False
        self.sources.setCurrentIndex(-1)
        self._basket = list(bookmark.comparison_selections)
        self._render_basket_label()
        self.table.verticalScrollBar().setValue(bookmark.scroll_position)
        self.status.setText("已套用同次 fresh exact 收藏結果與原比較錨點；沒有重新開來源，也沒有讀取 latest。")
        return True

    def _render_basket_label(self) -> None:
        self.basket_label.setText(f"比較籃：{len(self._basket)} 欄（保留各自原 query/page/source）")

    def _set_enabled_state(self) -> None:
        idle = self._worker is None and not self._closing
        has_page = self._state is not None
        self.cancel_button.setEnabled(self._worker is not None and not self._closing)
        self.refresh_sources_button.setEnabled(idle)
        self.more_sources_button.setEnabled(idle and self._catalog_cursor is not None)
        self.load_source_button.setEnabled(idle and self.selected_source is not None and bool(self.selected_source.is_selectable))
        self.apply_query_button.setEnabled(idle and has_page)
        self.previous_page_button.setEnabled(idle and has_page and self._state is not None and self._state.request.page_index > 0)
        self.next_page_button.setEnabled(idle and has_page and self._state is not None and self._state.request.page_index + 1 < self._state.page.page_count)
        self.add_comparison_button.setEnabled(idle and has_page and self._selected_row() is not None)
        self.run_comparison_button.setEnabled(idle and len(self._basket) >= 2)
        self.clear_comparison_button.setEnabled(idle and bool(self._basket))
        self.bookmark_button.setEnabled(idle and has_page and self._selected_row() is not None and len(self._basket) != 1)

    def _start(
        self,
        name: str,
        operation: Callable[..., object],
        apply: Callable[[object], None],
        *,
        kind: str,
    ) -> bool:
        if self._closing:
            return False
        self._generation += 1
        generation = self._generation
        pending = _QueuedOperation(name, operation, apply, kind)
        if self._worker is not None:
            self._pending = pending
            self._worker.cancel(cooperative=True, wait=False)
            self.status.setText(f"已要求目前工作安全停止；完成後開始：{name}。")
            return True
        self._launch(pending, generation)
        return True

    def _launch(self, pending: _QueuedOperation, generation: int) -> None:
        if self._closing:
            return
        worker = TaskWorker(pending.operation)
        self._worker = worker
        self._worker_kind = pending.kind
        worker.finished.connect(
            lambda value: self._apply_worker_value(pending, value, generation, worker)
            if generation == self._generation and not self._closing and self._worker is worker
            else None
        )
        worker.error.connect(
            lambda message: self._show_worker_error(pending, message, generation, worker)
            if generation == self._generation and not self._closing and self._worker is worker
            else None
        )
        worker.cancelled.connect(
            lambda: self._show_worker_cancelled(pending, generation, worker)
            if generation == self._generation and not self._closing and self._worker is worker
            else None
        )
        worker.native_thread_finished.connect(lambda: self._release(worker))
        self._set_enabled_state()
        self.status.setText(f"背景工作中：{pending.name}。")
        worker.start()

    def _apply_worker_value(
        self,
        pending: _QueuedOperation,
        value: object,
        generation: int,
        worker: TaskWorker,
    ) -> None:
        if self._closing or self._worker is not worker or self._generation != generation:
            return
        pending.apply(value)
        self._set_enabled_state()

    def _show_worker_error(
        self,
        pending: _QueuedOperation,
        message: str,
        generation: int,
        worker: TaskWorker,
    ) -> None:
        if self._closing or self._worker is not worker or self._generation != generation:
            return
        first_line = message.splitlines()[0] if message.splitlines() else "worker_error"
        self.status.setText(f"{pending.name}失敗：{first_line}；原已核驗結果保留。")
        if pending.kind == "query":
            self._restore_controls_from_state()
        self._set_enabled_state()

    def _show_worker_cancelled(
        self,
        pending: _QueuedOperation,
        generation: int,
        worker: TaskWorker,
    ) -> None:
        if self._closing or self._worker is not worker or self._generation != generation:
            return
        self.status.setText(f"{pending.name}已取消；原已核驗結果保留。")
        if pending.kind == "query":
            self._restore_controls_from_state()
        self._set_enabled_state()

    def _restore_controls_from_state(self) -> None:
        if self._state is not None:
            self._ensure_rule_filters(self._state.query.source.method_rule_keys)
            self._set_controls(self._state.query)

    def _release(self, worker: TaskWorker) -> None:
        if self._worker is worker:
            self._worker = None
            self._worker_kind = ""
        worker.deleteLater()
        if self._pending is not None and not self._closing:
            pending = self._pending
            self._pending = None
            self._launch(pending, self._generation)
        else:
            self._set_enabled_state()

    def closeEvent(self, event: object) -> None:  # noqa: N802 - Qt callback name.
        self.begin_shutdown()
        super().closeEvent(event)  # type: ignore[arg-type]
