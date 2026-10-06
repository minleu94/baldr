"""目前使用者設定下的真正 launcher；禁止真根寫入與 provider 網路。"""
from pathlib import Path
import json, logging, os, sys
case=Path(sys.argv[1])
real_root=Path('D:/Min/Python/Project/FA_Data').resolve()
denied=[]
def guard(event,args):
    if event in ('socket.connect','socket.getaddrinfo'):
        raise PermissionError('configured probe 禁止 provider 網路')
    if event not in ('open','os.mkdir','os.remove','os.rename','os.rmdir') or not args:
        return
    if not isinstance(args[0],(str,bytes,os.PathLike)):
        return
    path=Path(os.fsdecode(args[0])).resolve()
    if not path.is_relative_to(real_root):
        return
    if event=='open':
        mode,flags=args[1:3]
        if not (isinstance(mode,str) and any(c in mode for c in 'wax+')) and not (isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):
            return
    elif event=='os.mkdir' and path.is_dir():
        return
    denied.append(dict(event=event,path=str(path)))
    raise PermissionError('configured probe 禁止真資料寫入: '+str(path))
sys.addaudithook(guard)
for key in ('DATA_ROOT','OUTPUT_ROOT','BALDR_CONFIG'):
    os.environ.pop(key,None)
os.environ['LOCALAPPDATA']=str(Path.home()/'AppData/Local')
os.environ['QT_QPA_PLATFORM']='offscreen'
entry=sys._baldr_test_entry
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QLabel
from ui_qt import main as qt_main
file_handler=logging.FileHandler
class FixtureLogHandler(file_handler):
    def __init__(self, filename,*args,**kwargs):
        path=Path(filename).resolve()
        if path.is_relative_to(real_root):
            target=case/'logs'/path.name
            target.parent.mkdir(parents=True,exist_ok=True)
            filename=target
        super().__init__(filename,*args,**kwargs)
logging.FileHandler=FixtureLogHandler
original_diag=qt_main.install_crash_diagnostics
def fixture_diag():
    previous=os.environ['DATA_ROOT']
    os.environ['DATA_ROOT']=str(case/'diagnostic_root')
    try:
        return original_diag()
    finally:
        os.environ['DATA_ROOT']=previous
qt_main.install_crash_diagnostics=fixture_diag
base=qt_main.MainWindow
result={}
class FixtureWindow(base):
    def __init__(self,*args,**kwargs):
        kwargs['policy_config_path']=case/'generic_policy.json'
        super().__init__(*args,**kwargs)
        result['workspace_count']=len(self.workspace_widgets)
        result['degraded']=[name for name,view in self.workspace_widgets.items() if isinstance(view,QLabel)]
        result['ml_registry']=str(self.stock_research_ml_registry.repository_root)
        QTimer.singleShot(1000,self.close)
qt_main.MainWindow=FixtureWindow
sys.argv=['baldr.exe']
code=entry.main()
result.update(exit=code,data_root=os.environ['DATA_ROOT'],output_root=os.environ['OUTPUT_ROOT'],
              denied_writes=denied,provider_network=False,native=False)
result['scope']='startup_only_under_readonly_guard'
result['true_root_writes_allowed']=False
result['status']='passed' if code==0 and result.get('workspace_count')==9 and not result.get('degraded') else 'failed'
(case/'portable_configured_probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
assert result['status']=='passed',result
