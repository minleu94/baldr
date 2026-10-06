"""在 frozen launcher 上驗證首次設定與正常結束，僅用隔離 fixture。"""
from pathlib import Path
import json
import os
import sys

case = Path(sys.argv[1])
def guard(event, args):
    if event in ('socket.connect', 'socket.getaddrinfo'):
        raise PermissionError('首次啟動 fixture 禁止 provider 網路')
sys.addaudithook(guard)
for key in ('DATA_ROOT', 'OUTPUT_ROOT'):
    os.environ.pop(key, None)
entry = sys._baldr_test_entry
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from ui_qt import main as qt_main
original = qt_main.MainWindow
result = {}
class FixtureWindow(original):
    def __init__(self, *args, **kwargs):
        kwargs['policy_config_path'] = case / 'policy.json'
        super().__init__(*args, **kwargs)
        QTimer.singleShot(800, self.check_and_close)
    def check_and_close(self):
        boxes = [widget for widget in QApplication.topLevelWidgets() if isinstance(widget, QMessageBox)]
        result['setup_dialogs'] = [box.text() for box in boxes]
        result['workspaces'] = len(self.workspace_widgets)
        for box in boxes:
            box.close()
        self.close()
qt_main.MainWindow = FixtureWindow
sys.argv = ['baldr.exe']
code = entry.main()
assert code == 0, code
assert result['workspaces'] == 9, result
assert len(result['setup_dialogs']) == 1, result
assert str(case / 'local' / 'baldr' / 'market') in result['setup_dialogs'][0], result
assert Path(os.environ['DATA_ROOT']).is_relative_to(case), os.environ['DATA_ROOT']
assert Path(os.environ['OUTPUT_ROOT']).is_relative_to(case), os.environ['OUTPUT_ROOT']
result.update(status='passed', exit=code, frozen=sys.frozen, native=False,
              data_root=os.environ['DATA_ROOT'], output_root=os.environ['OUTPUT_ROOT'])
(case / 'portable_entry_probe.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
