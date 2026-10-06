"""由 exe 執行的隔離 fixture；不 fit、不連 provider、不讀真帳。"""
from pathlib import Path
import hashlib
import json
import os
import sys
import time
import multiprocessing
import subprocess

case = Path(sys.argv[1])
def guard(event, args):
    if event in ('socket.connect', 'socket.getaddrinfo'):
        raise PermissionError('portable fixture 禁止 provider 網路')
sys.addaudithook(guard)

import numpy as np
import scipy
import talib
from sklearn.preprocessing import StandardScaler
import joblib
from ml_module.model_artifact_manifest import ModelArtifactManifest
from ml_module.model_artifact_loader import SafeShadowModelArtifactLoader, ArtifactCompatibilityExpectation

def sha(raw):
    return 'sha256:' + hashlib.sha256(raw).hexdigest()

model_root = case / 'model'
model_root.mkdir(exist_ok=True)
schema = (("score_bp", "int", "bp"),)
expectation = ArtifactCompatibilityExpectation(expected_model_family='fixture_family',
    expected_feature_registry_hash=sha(b'features'), expected_label_registry_hash=sha(b'labels'),
    expected_feature_schema=schema, installed_library_versions={'python':sys.version.split()[0]})
if not (model_root / 'manifest.json').exists():
    model = StandardScaler()
    for key, value in {'model_id':'model-1','dataset_id':'dataset-1','model_family':'fixture_family',
                       'shadow_only':True,'production_eligible':False,'production_action_allowed':False}.items():
        setattr(model, key, value)
    joblib.dump(model, model_root / 'model.joblib')
    manifest = ModelArtifactManifest.create(model_id='model-1', dataset_id='dataset-1',
        created_run_id='run-1', created_at='2026-07-13T12:00:00+00:00', model_family='fixture_family',
        feature_registry_hash=sha(b'features'), label_registry_hash=sha(b'labels'), feature_schema=schema,
        training_as_of='2024-12-31', hyperparameters_hash=sha(b'params'),
        library_versions={'python':sys.version.split()[0]}, serialization_format='joblib',
        artifact_filename='model.joblib', artifact_hash=sha((model_root/'model.joblib').read_bytes()))
    (model_root/'manifest.json').write_text(json.dumps(manifest.to_dict()),encoding='utf-8')
loaded = SafeShadowModelArtifactLoader(data_root=case/'market').load_same_bytes_with_manifest_v1(model_root,expectation=expectation)
assert loaded.status == 'shadow_model_ready', loaded
assert np.isfinite(talib.SMA(np.arange(40,dtype=np.float64),timeperiod=20)[-1])

if len(sys.argv) > 2 and sys.argv[2] == 'model-only':
    (case/'model_reopen.json').write_text(json.dumps({'status':loaded.status}),encoding='utf-8')
else:
    child = multiprocessing.Process(target=os.mkdir,args=(str(case/'spawn_ok'),))
    child.start(); child.join(20)
    assert child.exitcode == 0 and (case/'spawn_ok').is_dir()
    fresh = subprocess.run([sys.executable, str(Path(__file__)), str(case), 'model-only'],timeout=30)
    assert fresh.returncode == 0 and (case/'model_reopen.json').is_file()
    from PySide6.QtWidgets import QApplication, QLabel, QMessageBox
    from PySide6.QtCore import QTimer
    from ui_qt import main as main_module
    from app_module.stock_research_report_provider_adapters import CurrentRestatedMLRunRegistry
    main_module.project_root=case/'state'
    main_module.CurrentRestatedMLRunRegistry=lambda: CurrentRestatedMLRunRegistry(repository_root=case/'state')
    app=QApplication([])
    main_module.apply_app_theme(app)
    dialogs=[]
    for kind in ('critical','warning','information'):
        setattr(QMessageBox,kind,lambda *args,k=kind,**kwargs: dialogs.append(k) or QMessageBox.Ok)
    window=main_module.MainWindow(policy_config_path=case/'policy.json')
    window.show(); app.processEvents()
    assert len(window.workspace_widgets) == 9
    degraded=[key for key,w in window.workspace_widgets.items() if isinstance(w,QLabel)]
    assert not degraded, degraded
    navigation=[]
    for key,widget in window.workspace_widgets.items():
        window.left_navigation._buttons[key].click(); app.processEvents()
        assert window.workspace_stack.currentWidget() is widget
        navigation.append(key)
    assert (Path(sys._MEIPASS)/'ui_qt/app_icon.png').is_file()
    QTimer.singleShot(1000,window.close)
    QTimer.singleShot(20000,app.quit)
    assert app.exec()==0
    assert window._shutdown_close_finalizing
    workers,background=main_module.MainWindow._request_shutdown_dependencies(window,send_cancel=False)
    assert not workers and not background
    main_module._drain_qt_deferred_deletes(app,(window,))
    (case/'probe.json').write_text(json.dumps({'status':'passed','navigation':navigation,'model':loaded.status,
        'spawn':child.exitcode,'dialogs':dialogs,'scipy':scipy.__version__,'native':False},ensure_ascii=False,indent=2),encoding='utf-8')
