"""在既有 Windows venv 建置可攜資料夾，不自動安裝或下載依賴。"""
from pathlib import Path
import os
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
if sys.platform != 'win32':
    raise SystemExit('請使用 Windows x64／Python 3.11 建置')
env=dict(os.environ, PYTHONUTF8='1',PYTHONNOUSERSITE='1',
    PYTHONUSERBASE=str(root/'output/packaging/empty-userbase'))
windows=Path(os.environ.get('WINDIR',r'C:\Windows'))
# 限定既有 Python 與系統工具，避免 Poppler／其他應用的 DLL 污染分析。
env['PATH']=';'.join(map(str,(Path(sys.executable).parent,windows/'System32',windows,
                              Path(sys.base_prefix),Path(sys.base_prefix)/'DLLs')))
raise SystemExit(subprocess.call([sys.executable,'-m','PyInstaller',str(root/'packaging/baldr.spec'),
    '--distpath',str(root/'dist'),'--workpath',str(root/'output/packaging/build'),'--noconfirm'],cwd=root,env=env))
