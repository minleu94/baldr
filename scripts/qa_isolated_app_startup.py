"""在自有 offscreen 子程序核驗真實 MainWindow 接線與安全關閉。"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]


def _child(case: Path) -> int:
    """只允許隔離根的寫入；不連網、不啟動任何外部工作。"""
    (case/'owned_child.json').write_text(json.dumps({'pid':os.getpid(),'parent_pid':os.getppid(),'token':os.environ['ISOLATED_APP_QA_TOKEN']}),encoding='utf-8')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT))
    violations: list[dict[str, str]] = []
    writes: list[str] = []
    def within(value: object) -> bool:
        if isinstance(value, int):
            return True
        try:
            return Path(os.fsdecode(value)).resolve().is_relative_to(case)
        except (TypeError, ValueError):
            return False

    def refuse(event: str, value: object) -> None:
        violations.append({'event': event, 'target': str(value), 'caller': ''.join(traceback.format_stack(limit=8))})
        raise PermissionError('隔離啟動 QA 拒絕非隔離副作用：'+event)

    def audit(event: str, args: tuple) -> None:
        if event == 'open':
            path, mode, flags = args
            # Windows 的空裝置不保存檔案，不屬於正式或使用者配置寫入。
            if isinstance(path, str) and path.casefold() == os.devnull.casefold():
                return
            writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or bool(
                flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            )
            if writing:
                if not within(path):
                    refuse(event, path)
                writes.append(str(path))
        elif event in {'os.mkdir', 'os.remove', 'os.rmdir'}:
            if not within(args[0]):
                refuse(event, args[0])
        elif event in {'os.rename', 'os.replace'}:
            if not within(args[0]) or not within(args[1]):
                refuse(event, args[:2])
        elif event in {'socket.connect', 'subprocess.Popen'}:
            refuse(event, args[:2])
        elif event == 'sqlite3.connect':
            raw = str(args[0])
            if raw != ':memory:':
                if raw.startswith('file:'):
                    from urllib.parse import unquote
                    raw = unquote(raw[5:].split('?', 1)[0]).lstrip('/')
                if not within(raw):
                    refuse(event, raw)
    sys.addaudithook(audit)
    receipt: dict = {'pid': os.getpid(), 'case': str(case), 'scope': '真實 MainWindow／隔離配置／offscreen，不是正式資料或 Native'}
    app = None
    window = None
    started = time.monotonic()
    try:
        if sys.platform == 'win32':
            import platform
            def native_system_version(system='', release='', version='', supported_platforms=('win32',)):
                # 用 Windows 核心唯讀 API 取同一版本，避免標準庫透過 cmd /c ver 探測。
                value = sys.getwindowsversion()
                return system, release, f'{value.major}.{value.minor}.{value.build}'
            platform._syscmd_ver = native_system_version
            receipt['system_version_probe'] = 'sys.getwindowsversion；未啟動 shell'
        from PySide6.QtWidgets import QApplication, QLabel
        from PySide6.QtCore import QTimer
        import ui_qt.main as main_module
        from app_module.stock_research_report_provider_adapters import CurrentRestatedMLRunRegistry
        # 僅重定位可寫 runtime／研究 registry 的根，保留真實實作。
        main_module.project_root = case/'repository'
        main_module.CurrentRestatedMLRunRegistry = lambda: CurrentRestatedMLRunRegistry(repository_root=case/'repository')
        app = QApplication([])
        main_module.apply_app_theme(app)
        window = main_module.MainWindow(policy_config_path=case/'personal_policy.json')
        expected = {definition.key for definition in main_module.WORKSPACE_DEFINITIONS}
        assert set(window.workspace_widgets) == expected
        degraded = [key for key, view in window.workspace_widgets.items() if isinstance(view, QLabel)]
        assert not degraded, degraded
        assert Path(window.config.data_root).resolve().is_relative_to(case)
        assert Path(window.config.output_root).resolve().is_relative_to(case)
        receipt['workspace_types'] = {key:type(view).__name__ for key,view in window.workspace_widgets.items()}
        receipt['config'] = {'profile':window.config.profile,'data_root':str(window.config.data_root),'output_root':str(window.config.output_root),'db_file':str(window.config.db_file)}
        assert window.config.profile == 'test'
        assert window.watchlist_service is not None and window.daily_market_research_screener_service is not None
        def close_when_ready() -> None:
            window.close()
        QTimer.singleShot(750, close_when_ready)
        # 只等待本程序合作式關閉，不殺其他程序或任意 worker。
        def finish_if_closed() -> None:
            if window._shutdown_close_finalizing:
                app.quit()
        timer = QTimer()
        timer.setInterval(50)
        timer.timeout.connect(finish_if_closed)
        timer.start()
        deadline = QTimer()
        deadline.setSingleShot(True)
        deadline.timeout.connect(app.quit)
        deadline.start(25_000)
        assert app.exec() == 0
        assert window._shutdown_close_finalizing, '隔離 App 合作式關閉逾時'
        workers, background = main_module.MainWindow._request_shutdown_dependencies(window, send_cancel=False)
        assert not workers and not background
        receipt.update(status='passed', worker_count=0, background_process_running=False)
        main_module._drain_qt_deferred_deletes(app,(window,))
    except Exception:
        receipt.update(status='failed',error=traceback.format_exc())
    finally:
        if violations:
            receipt.update(status='failed',error='隔離 guard 曾拒絕非隔離副作用；不可算啟動驗證通過')
        receipt.update(elapsed_seconds=round(time.monotonic()-started,3),violations=violations,write_paths=sorted(set(writes)))
        (case/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({key:receipt.get(key) for key in ['pid','status','error','elapsed_seconds','worker_count','violations']},ensure_ascii=False),flush=True)
    return 0 if receipt.get('status')=='passed' and not violations else 1


def main() -> int:
    parser=argparse.ArgumentParser(description='真實 App 的隔離 offscreen 最小啟動／關閉 QA')
    parser.add_argument('--output-root',required=True,type=Path)
    parser.add_argument('--child',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    out=args.output_root.expanduser().resolve()
    if not out.is_relative_to(ROOT/'output') or out == ROOT/'output':
        parser.error('輸出必須是 repository output 的明示隔離子目錄')
    if args.child:
        return _child(out)
    case=out/('app_startup_'+str(time.time_ns()))
    case.mkdir(parents=True,exist_ok=False)
    token=uuid.uuid4().hex
    environment={**os.environ,'DATA_ROOT':str(case/'data'),'OUTPUT_ROOT':str(case/'output'),'PROFILE':'test','QT_QPA_PLATFORM':'offscreen','MPLCONFIGDIR':str(case/'matplotlib'),'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8','PYTHONUTF8':'1','ISOLATED_APP_QA_TOKEN':token}
    process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--child','--output-root',str(case)],cwd=case,env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    timeout_cleanup=None
    try:
        stdout,stderr=process.communicate(timeout=45)
        (case/'stdout.log').write_bytes(stdout+stderr)
        return_code=process.returncode
    except subprocess.TimeoutExpired as exc:
        # Windows venv 啟動器與實際 Python 可能是兩個 PID，僅處理匹配本次 token／親程序的自有 child。
        timeout_cleanup={'launcher_pid':process.pid,'worker_pid':None,'worker_signal_sent':False}
        marker=case/'owned_child.json'
        try:
            if marker.is_file() and marker.stat().st_size <= 4096:
                owned=json.loads(marker.read_text(encoding='utf-8'))
                worker_pid=owned.get('pid')
                if owned.get('token')==token and type(worker_pid) is int and worker_pid>0 and (worker_pid==process.pid or owned.get('parent_pid')==process.pid):
                    timeout_cleanup['worker_pid']=worker_pid
                    import signal
                    os.kill(worker_pid,signal.SIGTERM)
                    timeout_cleanup['worker_signal_sent']=True
        except ProcessLookupError:
            pass
        except (OSError,ValueError,AttributeError) as cleanup_error:
            timeout_cleanup['verification_error']=type(cleanup_error).__name__
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)
        (case/'stdout.log').write_bytes((exc.stdout or b'')+(exc.stderr or b''))
        return_code=124
    summary={'case':str(case),'launcher_pid':process.pid,'exit_code':return_code,'timeout_cleanup':timeout_cleanup,'receipt_path':str(case/'receipt.json'),'log_path':str(case/'stdout.log')}
    (out/'app_startup_process_receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))
    return return_code


if __name__=='__main__':
    raise SystemExit(main())
