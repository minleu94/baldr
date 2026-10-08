"""可明確套用的 Qt 頁面捲動與清單可視列配置。"""

from __future__ import annotations

from weakref import ReferenceType, ref

from PySide6.QtCore import QEvent, QObject, QRect, QTimer, Qt, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QApplication,
    QLayout,
    QScrollArea,
    QSizePolicy,
    QListView,
    QTableView,
    QWidget,
)
from shiboken6 import getCppPointer


_CONTROLLER_ATTRIBUTE = "_layout_helpers_visible_rows_controller"
_DISPATCHER_ATTRIBUTE = "_layout_helpers_visible_rows_dispatcher"


def bounded_initial_window_geometry(available: QRect | None) -> QRect:
    """讓預設 1400×800 視窗置中，並保留視窗框與標題列的螢幕空間。"""

    default = QRect(100, 100, 1400, 800)
    if available is None or available.width() <= 0 or available.height() <= 0:
        return default

    # QScreen.availableGeometry 不扣除 Windows 標題列／邊框；留 16px 側邊與
    # 24px 上下緩衝，避免視窗可用幾何貼齊時外框落到螢幕外。
    safe_width = max(1, available.width() - 32)
    safe_height = max(1, available.height() - 48)
    width = min(default.width(), safe_width)
    height = min(default.height(), safe_height)
    x = available.x() + (available.width() - width) // 2
    y = available.y() + (available.height() - height) // 2
    return QRect(x, y, width, height)


def create_scroll_area(
    content: QWidget,
    *,
    object_name: str = "contentScrollArea",
    horizontal_scroll: bool = False,
) -> QScrollArea:
    """將完整內容包在可垂直捲動區，並讓內容 layout 的最小高度保留下來。

    此 helper 不替呼叫端改動任何子元件的 size policy。呼叫端需自行建立
    ``content`` 及其 layout，再將回傳的 scroll area 放進頁面 layout。
    """

    set_scroll_content_constraints(content, horizontal_scroll=horizontal_scroll)

    content.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Preferred,
    )

    scroll_area = QScrollArea()
    scroll_area.setObjectName(object_name)
    scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll_area.setWidgetResizable(True)
    scroll_area.setHorizontalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAsNeeded
        if horizontal_scroll
        else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll_area.setMinimumSize(0, 0)
    scroll_area.setWidget(content)
    return scroll_area


def set_scroll_content_constraints(
    content: QWidget,
    *,
    horizontal_scroll: bool = False,
) -> None:
    """為既有 QScrollArea 內容設定不會撐寬視窗的 layout 下限。

    垂直軸保留內容的自然最小高度，讓外層 scroll area 可完整捲動；水平軸預設
    不把內容最小寬度回傳到主視窗。只有呼叫端明確使用水平捲動時才保留水平
    minimum，避免把狹窄頁面內容裁掉。
    """

    layout = content.layout()
    if layout is not None:
        set_vertical_constraint = getattr(layout, "setVerticalSizeConstraint", None)
        set_horizontal_constraint = getattr(layout, "setHorizontalSizeConstraint", None)
        if callable(set_vertical_constraint) and callable(set_horizontal_constraint):
            set_vertical_constraint(QLayout.SizeConstraint.SetMinimumSize)
            set_horizontal_constraint(
                QLayout.SizeConstraint.SetMinimumSize
                if horizontal_scroll
                else QLayout.SizeConstraint.SetNoConstraint
            )
        elif layout.sizeConstraint() == QLayout.SizeConstraint.SetDefaultConstraint:
            # 舊版 Qt 沒有單軸 constraint 時仍保留可捲動的垂直內容高度。
            layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

    if not horizontal_scroll:
        content.setMinimumWidth(0)


def ensure_visible_rows(view: QAbstractItemView, rows: int = 5) -> int:
    """確保表格或清單最少容納指定列數。

    高度依目前前 ``rows`` 筆的列高提示與實際列高、表頭、frame 及可能出現的
    水平捲軸計算。資料尚未載入時以 view 的預設列高、字體高度補足。此函式只
    提高 minimum height，不設定 maximum height，也不覆寫 view 的 size policy。
    對 model、表頭、水平捲軸與 view 幾何變動會合併排程重新量測。
    """

    if rows < 1:
        raise ValueError("rows 必須至少為 1")
    if not isinstance(view, (QTableView, QListView)):
        raise TypeError("view 必須是 QTableView／QListView")

    controller = getattr(view, _CONTROLLER_ATTRIBUTE, None)
    if not isinstance(controller, _VisibleRowsState) or controller.disposed:
        controller = _VisibleRowsState(view, rows)
        # 先公開完整狀態再安裝 event filter；連接期間 Qt 可能同步送出事件。
        setattr(view, _CONTROLLER_ATTRIBUTE, controller)
        controller.attach(_get_dispatcher())
    else:
        controller.set_rows(rows)
    return controller.measure_and_apply()


def _get_dispatcher() -> _VisibleRowsDispatcher:
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("ensure_visible_rows 必須在 QApplication 建立後呼叫")

    dispatcher = getattr(app, _DISPATCHER_ATTRIBUTE, None)
    if not isinstance(dispatcher, _VisibleRowsDispatcher):
        dispatcher = _VisibleRowsDispatcher()
        # dispatcher 只由該 QApplication 持有，不用可能跨 QApplication 殘留的模組全域參照。
        setattr(app, _DISPATCHER_ATTRIBUTE, dispatcher)
        dispatcher.setParent(app)
    return dispatcher


class _VisibleRowsDispatcher(QObject):
    """單一 app-owned Qt event filter 與合併量測排程器。"""

    def __init__(self) -> None:
        # 先無 parent 建立並初始化；setParent 時應用程式可能同步收到 ChildAdded。
        super().__init__()
        self._pending: list[ReferenceType[_VisibleRowsState]] = []
        self._draining = False
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._drain_pending)
        self._timer.setParent(self)

    def watch(self, view: QAbstractItemView) -> None:
        view.installEventFilter(self)

    def enqueue(self, state: _VisibleRowsState) -> None:
        if state.disposed or state._scheduled:
            return
        state._scheduled = True
        self._pending.append(ref(state))
        if not self._timer.isActive() and not self._draining:
            self._timer.start(0)

    def cancel(self, state: _VisibleRowsState) -> None:
        self._pending = [
            pending_ref
            for pending_ref in self._pending
            if pending_ref() is not None and pending_ref() is not state
        ]
        state._scheduled = False
        if not self._pending and self._timer.isActive():
            self._timer.stop()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        try:
            state = getattr(watched, _CONTROLLER_ATTRIBUTE, None)
        except RuntimeError:
            return False
        if not isinstance(state, _VisibleRowsState):
            return False

        if event.type() == QEvent.Type.DeferredDelete:
            state.dispose(watched)
            return False

        state.handle_view_event(watched, event)
        return False

    @Slot()
    def _drain_pending(self) -> None:
        if self._draining:
            return
        self._draining = True
        pending, self._pending = self._pending, []
        try:
            for state_ref in pending:
                state = state_ref()
                if state is None:
                    continue
                state._scheduled = False
                state.run_scheduled_measure()
        finally:
            self._draining = False
        if self._pending and not self._timer.isActive():
            self._timer.start(0)


class _VisibleRowsState:
    """純 Python 的單 view 量測狀態；不持有 view/model 的強引用。"""

    _VIEW_EVENTS = (
        QEvent.Type.Show,
        QEvent.Type.Resize,
        QEvent.Type.FontChange,
        QEvent.Type.ApplicationFontChange,
        QEvent.Type.StyleChange,
        QEvent.Type.PolishRequest,
    )

    def __init__(self, view: QAbstractItemView, rows: int) -> None:
        self._view_ref: ReferenceType[QAbstractItemView] | None = ref(view)
        self._dispatcher_ref: ReferenceType[_VisibleRowsDispatcher] | None = None
        self._rows = rows
        self._base_minimum_height = view.minimumHeight()
        self._scheduled = False
        self._layout_dirty = True
        self._measuring = False
        self._disposed = False
        self._last_hscroll_visible: bool | None = None
        self._connected_model_ref: ReferenceType[QObject] | None = None
        self._connected_model_key: int | None = None
        self._model_connections: list[tuple[str, object]] = []
        self._view_signal_connections: list[
            tuple[ReferenceType[QObject], str, object]
        ] = []
        self._layout_callback = self._weak_callback("_on_layout_metrics_changed")
        self._horizontal_range_callback = self._weak_callback(
            "_on_horizontal_range_changed"
        )
        self._destroyed_callback = self._weak_callback("_on_view_destroyed")

    @property
    def disposed(self) -> bool:
        return self._disposed

    @property
    def _connected_model(self) -> QObject | None:
        return self._connected_model_ref() if self._connected_model_ref is not None else None

    def attach(self, dispatcher: _VisibleRowsDispatcher) -> None:
        view = self._view()
        if view is None or self._disposed:
            return
        self._dispatcher_ref = ref(dispatcher)
        dispatcher.watch(view)
        self._connect_view_signals(view)
        self._connect_model_signals(view)
        self._connect_signal(
            view,
            "destroyed",
            self._destroyed_callback,
            Qt.ConnectionType.DirectConnection,
        )
        self.schedule_measure()

    def _view(self) -> QAbstractItemView | None:
        return self._view_ref() if self._view_ref is not None else None

    def _weak_callback(self, method_name: str) -> object:
        state_ref = ref(self)

        def callback(*args: object) -> None:
            state = state_ref()
            if state is not None:
                getattr(state, method_name)(*args)

        return callback

    def set_rows(self, rows: int) -> None:
        self._rows = rows
        self.schedule_measure()

    def _connect_view_signals(self, view: QAbstractItemView) -> None:
        vertical_header_getter = getattr(view, "verticalHeader", None)
        horizontal_header_getter = getattr(view, "horizontalHeader", None)
        vertical_header = vertical_header_getter() if callable(vertical_header_getter) else None
        horizontal_header = (
            horizontal_header_getter() if callable(horizontal_header_getter) else None
        )
        if vertical_header is not None:
            self._connect_signal(
                vertical_header,
                "sectionResized",
                self._layout_callback,
                Qt.ConnectionType.DirectConnection,
            )
            self._connect_signal(
                vertical_header,
                "geometriesChanged",
                self._layout_callback,
                Qt.ConnectionType.DirectConnection,
            )
        if horizontal_header is not None:
            self._connect_signal(
                horizontal_header,
                "sectionResized",
                self._layout_callback,
                Qt.ConnectionType.DirectConnection,
            )
            self._connect_signal(
                horizontal_header,
                "geometriesChanged",
                self._layout_callback,
                Qt.ConnectionType.DirectConnection,
            )
        if view.horizontalScrollBarPolicy() != Qt.ScrollBarPolicy.ScrollBarAlwaysOff:
            self._connect_signal(
                view.horizontalScrollBar(),
                "rangeChanged",
                self._horizontal_range_callback,
                Qt.ConnectionType.DirectConnection,
            )

    def _connect_signal(
        self,
        owner: QObject,
        signal_name: str,
        callback: object,
        connection_type: Qt.ConnectionType = Qt.ConnectionType.AutoConnection,
    ) -> None:
        try:
            signal = getattr(owner, signal_name, None)
            if signal is None:
                return
            signal.connect(callback, connection_type)
            self._view_signal_connections.append((ref(owner), signal_name, callback))
        except (RuntimeError, TypeError):
            return

    def _disconnect_signals(
        self,
        connections: list[tuple[ReferenceType[QObject], str, object]],
        view: QAbstractItemView | None = None,
    ) -> None:
        fallback_owners: list[QObject] = []
        if view is not None:
            fallback_owners.append(view)
            for owner_name in (
                "horizontalScrollBar",
                "verticalHeader",
                "horizontalHeader",
            ):
                try:
                    getter = getattr(view, owner_name, None)
                    owner = getter() if callable(getter) else None
                    if owner is not None:
                        fallback_owners.append(owner)
                except (AttributeError, RuntimeError):
                    continue
        for owner_ref, signal_name, callback in connections:
            owner = owner_ref()
            if owner is not None:
                try:
                    getattr(owner, signal_name, None)
                except RuntimeError:
                    owner = None
            owners = (owner,) if owner is not None else tuple(fallback_owners)
            for candidate in owners:
                try:
                    signal = getattr(candidate, signal_name, None)
                    if signal is not None:
                        signal.disconnect(callback)
                except (RuntimeError, TypeError):
                    continue
        connections.clear()

    def _disconnect_model_signals(self) -> None:
        model = self._connected_model
        if model is not None:
            for signal_name, callback in self._model_connections:
                try:
                    signal = getattr(model, signal_name, None)
                    if signal is not None:
                        signal.disconnect(callback)
                except (RuntimeError, TypeError):
                    continue
        self._model_connections.clear()
        self._connected_model_ref = None
        self._connected_model_key = None

    def _connect_model_signals(self, view: QAbstractItemView) -> bool:
        try:
            model = view.model()
        except RuntimeError:
            return False
        model_key = getCppPointer(model)[0] if model is not None else None
        if model_key == self._connected_model_key:
            # PySide 可能替同一個存活中的 C++ model 重建 wrapper；更新弱參照，
            # 讓銷毀時仍可中斷它的 signal callbacks。
            self._connected_model_ref = ref(model) if model is not None else None
            return False

        self._disconnect_model_signals()
        self._connected_model_ref = ref(model) if model is not None else None
        self._connected_model_key = model_key
        if model is None:
            return True
        model_callback = self._weak_model_callback(model_key)
        for signal_name in (
            "modelReset",
            "rowsInserted",
            "rowsRemoved",
            "layoutChanged",
            "dataChanged",
        ):
            try:
                signal = getattr(model, signal_name, None)
                if signal is not None:
                    signal.connect(model_callback)
                    self._model_connections.append((signal_name, model_callback))
            except (RuntimeError, TypeError):
                # Qt 可能在 UI 正切換 model 時銷毀上一個 C++ model。
                continue
        destroyed_callback = self._weak_model_destroyed_callback(model_key)
        try:
            model.destroyed.connect(
                destroyed_callback, Qt.ConnectionType.DirectConnection
            )
            self._model_connections.append(("destroyed", destroyed_callback))
        except (RuntimeError, TypeError):
            pass
        return True

    def _weak_model_callback(self, model_key: int | None) -> object:
        state_ref = ref(self)

        def callback(*args: object) -> None:
            state = state_ref()
            if state is not None and state._connected_model_key == model_key:
                state._on_model_changed(*args)

        return callback

    def _weak_model_destroyed_callback(self, model_key: int | None) -> object:
        state_ref = ref(self)

        def callback(*_args: object) -> None:
            state = state_ref()
            if state is not None:
                state._on_model_destroyed(model_key)

        return callback

    def _on_model_changed(self, *_args: object) -> None:
        self.schedule_measure()

    def _on_model_destroyed(self, model_key: int | None) -> None:
        # setModel() 後舊 model 可能比 view 活得久。它的 callback 只帶 state 弱參照，
        # model 替換後就不再觸發排程。
        if model_key != self._connected_model_key:
            return
        self._connected_model_ref = None
        self._connected_model_key = None
        self._model_connections.clear()
        self.schedule_measure()

    def _on_layout_metrics_changed(self, *_args: object) -> None:
        # Header/scrollbar geometry notifications may be emitted as part of our
        # own item-layout pass. That pass already reads the resulting geometry.
        if not self._measuring:
            self.schedule_measure()

    def _on_horizontal_range_changed(self, *_args: object) -> None:
        if self._measuring or self._disposed:
            return
        view = self._view()
        if view is None:
            return
        try:
            visible = view.horizontalScrollBar().isVisible()
        except RuntimeError:
            return
        if self._last_hscroll_visible is None:
            self._last_hscroll_visible = visible
        elif visible != self._last_hscroll_visible:
            self._last_hscroll_visible = visible
            self.schedule_measure()

    def handle_view_event(self, view: QObject, event: QEvent) -> None:
        if self._disposed or not isinstance(view, QAbstractItemView):
            return
        try:
            model_changed = self._connect_model_signals(view)
            if event.type() in self._VIEW_EVENTS or model_changed:
                self.schedule_measure()
            elif (
                event.type() == QEvent.Type.LayoutRequest
                and self._layout_dirty
            ):
                # LayoutRequest is also posted by QListView.doItemsLayout().
                # It only needs another pass when a real input event has
                # already invalidated our measurement.
                self._schedule_pending_measure()
        except RuntimeError:
            self.dispose()

    def schedule_measure(self, *_args: object) -> None:
        if self._disposed:
            return
        self._layout_dirty = True
        self._schedule_pending_measure()

    def _schedule_pending_measure(self) -> None:
        dispatcher = self._dispatcher_ref() if self._dispatcher_ref is not None else None
        if dispatcher is None or self._disposed:
            return
        try:
            dispatcher.enqueue(self)
        except RuntimeError:
            self.dispose()

    def run_scheduled_measure(self) -> None:
        if self._disposed:
            return
        view = self._view()
        if view is None:
            self.dispose()
            return
        try:
            if self._connect_model_signals(view):
                self._layout_dirty = True
            self.measure_and_apply()
        except RuntimeError:
            # Qt 可能在排程中的 dispatcher callback 執行前使 wrapper 失效。
            self.dispose()

    def _on_view_destroyed(self, *_args: object) -> None:
        # 此時 sender 正發送 destroyed；Qt 可能已移除該連線，勿在清理時再斷一次。
        destroyed_callback = self._destroyed_callback
        self._view_signal_connections = [
            connection
            for connection in self._view_signal_connections
            if not (
                connection[1] == "destroyed"
                and connection[2] is destroyed_callback
            )
        ]
        self.dispose()

    def dispose(self, view_hint: QObject | None = None) -> None:
        if self._disposed:
            return
        self._disposed = True
        dispatcher = self._dispatcher_ref() if self._dispatcher_ref is not None else None
        if dispatcher is not None:
            try:
                dispatcher.cancel(self)
            except RuntimeError:
                # The QApplication may have destroyed its dispatcher already.
                pass

        view = view_hint if view_hint is not None else self._view()
        if view is not None:
            try:
                dispatcher = self._dispatcher_ref() if self._dispatcher_ref is not None else None
                if dispatcher is not None:
                    view.removeEventFilter(dispatcher)
            except RuntimeError:
                pass

        self._disconnect_model_signals()
        self._disconnect_signals(self._view_signal_connections, view)
        self._view_ref = None
        self._dispatcher_ref = None
        self._layout_callback = lambda *_args: None
        self._horizontal_range_callback = lambda *_args: None
        self._destroyed_callback = lambda *_args: None
        self._layout_dirty = False

    def measure_and_apply(self) -> int:
        view = self._view()
        if view is None or self._disposed:
            return self._base_minimum_height
        # Clear before reading geometry: genuine changes observed during the
        # measurement can set this again and queue a follow-up pass.
        refresh_list_layout = self._layout_dirty
        self._layout_dirty = False
        self._measuring = True
        try:
            required_height = self._required_height(
                view,
                refresh_list_layout=refresh_list_layout,
            )
        finally:
            self._measuring = False
        try:
            self._last_hscroll_visible = view.horizontalScrollBar().isVisible()
        except RuntimeError:
            self._last_hscroll_visible = None
        target_height = max(self._base_minimum_height, required_height)
        if view.minimumHeight() < target_height:
            view.setMinimumHeight(target_height)
            return target_height
        return view.minimumHeight()

    def _required_height(
        self,
        view: QAbstractItemView,
        *,
        refresh_list_layout: bool,
    ) -> int:
        try:
            model = view.model()
        except RuntimeError:
            return self._base_minimum_height
        try:
            item_count = model.rowCount(view.rootIndex()) if model is not None else 0
        except TypeError:
            item_count = model.rowCount() if model is not None else 0

        vertical_header_getter = getattr(view, "verticalHeader", None)
        horizontal_header_getter = getattr(view, "horizontalHeader", None)
        try:
            vertical_header = (
                vertical_header_getter()
                if callable(vertical_header_getter)
                else None
            )
            horizontal_header = (
                horizontal_header_getter()
                if callable(horizontal_header_getter)
                else None
            )
        except RuntimeError:
            vertical_header = None
            horizontal_header = None
        default_row_height = view.fontMetrics().height() + 8
        if vertical_header is not None:
            default_row_height = max(
                vertical_header.defaultSectionSize(),
                default_row_height,
            )
        spacing = 0
        if hasattr(view, "spacing"):
            try:
                spacing = max(0, int(view.spacing()))
            except (TypeError, ValueError):
                pass
        default_row_height += spacing

        if isinstance(view, QListView) and refresh_list_layout:
            try:
                # 換行清單的 sizeHintForRow 可能仍回傳未換行高度；在 dirty
                # 狀態下先更新目前寬度的 item layout，再以 visualRect 取列高。
                # doItemsLayout 會產生 Qt 的 LayoutRequest；eventFilter 僅處理
                # 已由外部內容／幾何事件標 dirty 的請求，避免自我排程循環。
                view.doItemsLayout()
            except RuntimeError:
                pass

        item_height = 0
        list_visual_rects: list[QRect | None] = []
        for row in range(min(self._rows, max(0, item_count))):
            actual_height = 0
            if vertical_header is not None and row < vertical_header.count():
                actual_height = vertical_header.sectionSize(row)
            try:
                hinted_height = view.sizeHintForRow(row)
            except RuntimeError:
                hinted_height = -1
            if isinstance(view, QListView):
                visual_height = -1
                try:
                    index = model.index(row, 0, view.rootIndex())
                    visual_rect = view.visualRect(index)
                    if visual_rect.isValid():
                        visual_height = visual_rect.height()
                        list_visual_rects.append(visual_rect)
                    else:
                        list_visual_rects.append(None)
                except (RuntimeError, TypeError):
                    list_visual_rects.append(None)
                item_height += (
                    max(
                        default_row_height - spacing,
                        actual_height,
                        hinted_height,
                        visual_height,
                        1,
                    )
                    + spacing
                )
            else:
                item_height += max(default_row_height, actual_height, hinted_height, 1)

        if (
            isinstance(view, QListView)
            and list_visual_rects
            and all(rect is not None for rect in list_visual_rects)
        ):
            first_rect = list_visual_rects[0]
            last_rect = list_visual_rects[-1]
            if first_rect is not None and last_rect is not None:
                # word-wrap 清單的 sizeHintForRow 可能低估實際換行高度；相鄰列
                # 的 visualRect 包含 layout 真正使用的列高與間距，直接量可視範圍。
                visual_extent = max(0, last_rect.bottom() - first_rect.top() + 1)
                top_inset = max(view.frameWidth(), spacing)
                item_height = max(item_height, visual_extent + top_inset)

        missing_rows = max(0, self._rows - max(0, item_count))
        item_height += missing_rows * default_row_height

        header_height = 0
        if horizontal_header is not None and not horizontal_header.isHidden():
            header_height = max(
                horizontal_header.height(),
                horizontal_header.sizeHint().height(),
            )

        frame_height = 2 * view.frameWidth()
        if isinstance(view, QAbstractScrollArea):
            bar_policy = view.horizontalScrollBarPolicy()
            if bar_policy != Qt.ScrollBarPolicy.ScrollBarAlwaysOff:
                frame_height += max(
                    view.horizontalScrollBar().sizeHint().height(),
                    view.horizontalScrollBar().minimumSizeHint().height(),
                )

        margins = view.contentsMargins()
        return max(
            self._base_minimum_height,
            item_height + header_height + frame_height + margins.top() + margins.bottom(),
        )
