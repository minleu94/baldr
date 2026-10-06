import traceback
import psutil
try:
    import numpy, scipy, sklearn, talib, joblib
    from PySide6 import QtCore
    print('CORE',QtCore.qVersion())
    from PySide6 import QtGui
    print('GUI OK')
    from PySide6.QtWidgets import QApplication
    print('OK')
except Exception:
    traceback.print_exc()
finally:
    print('\n'.join(sorted({m.path for m in psutil.Process().memory_maps()
        if any(s in m.path.lower() for s in ('qt6','pyside','shiboken','vcruntime','msvcp'))})))
