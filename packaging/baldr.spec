"""Windows x64 可攜資料夾；不收集資料、私人模型或 QA 輸出。"""
from pathlib import Path
import importlib.util
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, copy_metadata

root = Path(SPECPATH).parent
packages = ['ui_qt', 'app_module', 'data_module', 'analysis_module', 'backtest_module',
            'decision_module', 'portfolio_module', 'runtime', 'ml_module']
hidden = []
datas = []
for package in packages:
    for path in (root / package).rglob('*.py'):
        if '__pycache__' in path.parts or 'tests' in path.parts:
            continue
        relative = path.relative_to(root).with_suffix('')
        hidden.append('.'.join(relative.parts).removesuffix('.__init__'))
    for path in (root / package).rglob('*'):
        if path.suffix in ('.png', '.ico', '.qss', '.json') and 'tests' not in path.parts and 'outputs' not in path.parts:
            datas.append((str(path), str(path.parent.relative_to(root))))
# 原子程序仍核對腳本存在；保留正式 script source，不收 experiments／QA。
for path in (root / 'scripts').rglob('*'):
    if path.is_file() and path.suffix in ('.py', '.json') and 'experiments' not in path.parts and not path.name.startswith(('qa_', 'test_')) and not path.name.endswith('task_registration_plan.json'):
        datas.append((str(path), str(path.parent.relative_to(root))))
        if path.suffix == '.py':
            hidden.append('.'.join(path.relative_to(root).with_suffix('').parts))
for package in ('sklearn', 'scipy', 'talib'):
    hidden += collect_submodules(package, filter=lambda name: not any(part in ('tests', 'testing') for part in name.split('.')))
for package in ('sklearn', 'talib', 'matplotlib'):
    datas += collect_data_files(package)
for package in ('scikit-learn', 'TA-Lib', 'joblib'):
    datas += copy_metadata(package)
a = Analysis([str(root / 'baldr_launcher.py')], pathex=[str(root)], binaries=[], datas=datas,
             hiddenimports=hidden, hookspath=[], runtime_hooks=[], excludes=['PyQt5', 'PyQt6', 'PySide2', 'pytest', 'IPython', 'jupyter', 'notebook'], noarchive=False)
# Python 3.11 的 14.38 runtime 比 Qt 6.10 wheel 的 14.44 舊；
# Windows 會重用先載入 DLL，同名 C++ runtime 必須沿同份官方 wheel。
qt_dir = Path(importlib.util.find_spec('PySide6').origin).parent
crt = {path.name.lower(): path for path in qt_dir.glob('*.dll')
       if path.name.lower().startswith(('msvcp140', 'vcruntime140', 'concrt140'))}
a.binaries = [(dest, str(crt.get(Path(dest).name.lower(), Path(source))), kind)
              for dest, source, kind in a.binaries]
a.binaries += [(path.name, str(path), 'BINARY') for path in crt.values()
               if not any(dest.lower() == path.name.lower() for dest, source, kind in a.binaries)]
# Qt 6.10 使用 Windows 系統 ICU 的未加版本符號；不可打包 PATH 中
# Poppler 的 ICU78（符號帶 _78），否則遮蔽系統 DLL 並造成 Qt 載入失敗。
a.binaries = [(dest, source, kind) for dest, source, kind in a.binaries
              if Path(dest).name.lower() not in ('icuuc.dll', 'icudt78.dll')]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='baldr', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          icon=str(root / 'ui_qt/app_icon.png'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='baldr')
