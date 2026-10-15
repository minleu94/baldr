"""啟動階段 UI：原圖、真實階段進度與合作式取消。"""
from __future__ import annotations

import ctypes
import os
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtGui import QCloseEvent, QFont, QFontDatabase, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget

APP_USER_MODEL_ID = "Baldr.TechnicalAnalysis"
STAGES = (
    "正在讀取資料設定", "正在建立分析服務", "正在連接研究資料",
    "正在建立更新工作區", "正在建立市場工作區", "正在建立每日決策",
    "正在建立決策工作台", "正在建立回測工作區", "正在建立推薦工作區",
    "正在建立觀察清單", "正在建立持倉工作區", "正在建立執行監控",
    "正在建立個股研究", "正在完成介面配置",
)


def set_windows_app_identity() -> None:
    """在任何 Qt 視窗前設定 process identity；不修改 registry。"""
    if sys.platform == "win32":
        setter = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        setter.argtypes = [ctypes.c_wchar_p]
        setter.restype = ctypes.c_long
        result = setter(APP_USER_MODEL_ID)
        if result != 0:
            print(f"[Startup] AppUserModelID HRESULT={result}", file=sys.stderr)


class StartupCancelled(Exception):
    """使用者取消；只在安全初始化階段邊界中止。"""


class StartupView(QWidget):
    def __init__(self, asset_root: Path):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.cancel_requested = False
        self.background = QPixmap(str(asset_root / "loading_view.png"))
        self.setWindowIcon(QIcon(str(asset_root / "app_icon.png")))
        self.setWindowTitle("baldr")
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        width = min(640, int(available.width() * 0.8), int(available.height() * 0.8 * 4 / 3)) if available else 640
        self.resize(width, width * 3 // 4)
        if available:
            self.move(available.center() - self.rect().center())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addStretch()
        panel = QWidget(self)
        panel.setObjectName("startupPanel")
        panel.setStyleSheet("QWidget#startupPanel {background: rgba(25, 24, 28, 225); border-radius: 12px;}"
                            "QLabel {color: #fff3dc; background: transparent; font-size: 16px;}"
                            "QProgressBar {background: #48434a; border: 0; border-radius: 4px; height: 8px;}"
                            "QProgressBar::chunk {background: #eac283; border-radius: 4px;}")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 16, 18, 16)
        self.label = QLabel("正在載入程式元件", panel)
        # Windows offscreen 未提供系統 font database 時，讀取系統既有字型。
        # 不複製或散布 Windows 字型，也不下載字型。
        families = QFontDatabase.families()
        if not families and sys.platform == "win32":
            font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msjh.ttc"
            if font_path.is_file():
                font_id = QFontDatabase.addApplicationFont(str(font_path))
                families = QFontDatabase.applicationFontFamilies(font_id)
        preferred = [name for name in ("Microsoft JhengHei", "Noto Sans CJK TC", "Microsoft YaHei") if name in families]
        if preferred or families:
            self.label.setFont(QFont((preferred or families)[0]))
        self.label.setWordWrap(True)
        self.progress = QProgressBar(panel)
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 0)
        panel_layout.addWidget(self.label)
        panel_layout.addSpacing(8)
        panel_layout.addWidget(self.progress)
        layout.addWidget(panel)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        if not self.background.isNull():
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(self.rect(), self.background)
        else:
            painter.fillRect(self.rect(), Qt.GlobalColor.darkGray)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.cancel_requested = True
        self.hide()
        event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)


class StartupController:
    def __init__(self, app: QApplication, asset_root: Path):
        self.app = app
        self.window: QWidget | None = None
        self.completed = 0
        self._dismissed = False
        self.view = StartupView(asset_root)
        self.app.setQuitOnLastWindowClosed(False)
        self.view.show()
        self.app.processEvents()

    def check_cancel(self) -> None:
        self.app.processEvents()
        if self.view.cancel_requested:
            raise StartupCancelled()

    def preload(self) -> None:
        """純計算套件 import 在背景；Qt 物件仍只在主執行緒建立。"""
        self.check_cancel()
        errors: list[BaseException] = []
        def load() -> None:
            try:
                import importlib
                for name in ("numpy", "scipy", "sklearn", "talib", "pandas"):
                    importlib.import_module(name)
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=load, name="baldr-imports")
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(20)
        timer.timeout.connect(lambda: loop.quit() if not thread.is_alive() else None)
        thread.start()
        timer.start()
        loop.exec()
        timer.stop()
        thread.join()
        self.check_cancel()
        if errors:
            raise errors[0]
        self.view.label.setText("正在載入介面元件")
        self.check_cancel()

    def step(self, label: str) -> None:
        position = STAGES.index(label)
        if position < self.completed:
            raise ValueError("啟動階段不得倒退")
        self.completed = position
        self.view.label.setText(label)
        self.view.progress.setRange(0, len(STAGES))
        self.view.progress.setValue(position)
        self.check_cancel()

    def ready(self, window: QWidget) -> None:
        self.check_cancel()
        window.setEnabled(True)
        window.show()
        self.app.processEvents()
        if not window.isVisible():
            raise RuntimeError("主視窗尚未顯示")
        self.view.label.setText("已準備完成")
        self.view.progress.setValue(len(STAGES))
        self.dismiss()
        self.app.setQuitOnLastWindowClosed(True)

    def dismiss(self) -> None:
        # ready已排程刪除啟動畫面；launcher的finally可再次清理，不再碰失效wrapper。
        if self._dismissed:
            return
        self._dismissed = True
        self.view.hide()
        self.view.deleteLater()
