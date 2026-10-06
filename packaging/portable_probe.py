"""由 exe 執行的隔離 fixture；不 fit、不連 provider、不讀真帳。"""

def main() -> None:
    from pathlib import Path
    from dataclasses import replace
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
    wrong = SafeShadowModelArtifactLoader(data_root=case/'market').load_same_bytes_with_manifest_v1(
        model_root, expectation=replace(expectation, expected_model_family='wrong_fixture_family'))
    assert wrong.status == 'rule_only_fallback' and wrong.model is None
    assert np.isfinite(talib.SMA(np.arange(40,dtype=np.float64),timeperiod=20)[-1])

    if len(sys.argv) > 2 and sys.argv[2] == 'model-only':
        (case/'model_reopen.json').write_text(json.dumps({'status':loaded.status,
            'artifact_sha256':hashlib.sha256((model_root/'model.joblib').read_bytes()).hexdigest()}),encoding='utf-8')
    else:
        spawn_path = case / f'spawn_{os.getpid()}'
        child = multiprocessing.Process(target=os.mkdir,args=(str(spawn_path),))
        child.start(); child.join(20)
        assert child.exitcode == 0 and spawn_path.is_dir()
        resource_root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
        command = [sys.executable]
        if not getattr(sys, 'frozen', False):
            command.append(str(resource_root / 'baldr_launcher.py'))
        fresh = subprocess.run([*command, str(Path(__file__)), str(case), 'model-only'],timeout=30)
        assert fresh.returncode == 0 and (case/'model_reopen.json').is_file()
        from PySide6.QtWidgets import QApplication, QLabel, QMessageBox
        from PySide6.QtCore import QTimer
        from ui_qt import main as main_module
        from app_module.application_bootstrap import resolve_application_settings
        from app_module.build_identity import detect_build_identity
        settings = resolve_application_settings(resource_root=resource_root)
        identity = detect_build_identity(repository_root=resource_root)
        app=QApplication.instance() or QApplication([])
        main_module.apply_app_theme(app)
        dialogs=[]
        for kind in ('critical','warning','information'):
            setattr(QMessageBox,kind,lambda *args,k=kind,**kwargs: dialogs.append(k) or QMessageBox.Ok)
        window=main_module.MainWindow(policy_config_path=case/'policy.json',
            application_settings=settings, build_identity=identity)
        window.show(); app.processEvents()
        assert len(window.workspace_widgets) == 9
        degraded=[key for key,w in window.workspace_widgets.items() if isinstance(w,QLabel)]
        assert not degraded, degraded
        navigation=[]
        for key,widget in window.workspace_widgets.items():
            window.left_navigation._buttons[key].click(); app.processEvents()
            assert window.workspace_stack.currentWidget() is widget
            navigation.append(key)
        assert (resource_root/'ui_qt/app_icon.png').is_file()
        assert identity.display_text in window.windowTitle()
        assert identity.display_text == window.findChild(QLabel, 'baldrBuildIdentity').text()
        QTimer.singleShot(1000,window.close)
        QTimer.singleShot(20000,app.quit)
        assert app.exec()==0
        assert window._shutdown_close_finalizing
        workers,background=main_module.MainWindow._request_shutdown_dependencies(window,send_cancel=False)
        assert not workers and not background
        main_module._drain_qt_deferred_deletes(app,(window,))
        assert not (case/'technical_calculation.log').exists()
        assert (Path(os.environ['OUTPUT_ROOT'])/'application_state/logs/technical_calculation.log').is_file()
        (case/'probe.json').write_text(json.dumps({'status':'passed','navigation':navigation,'model':loaded.status,
            'spawn':child.exitcode,'dialogs':dialogs,'scipy':scipy.__version__,'native':False,
            'build':identity.to_dict(), 'settings':settings.to_dict(),
            'model_sha256':hashlib.sha256((model_root/'model.joblib').read_bytes()).hexdigest(),
            'model_error':{'status':wrong.status,'blockers':wrong.blockers},
            'fresh_model_readback':json.loads((case/'model_reopen.json').read_text(encoding='utf-8'))},ensure_ascii=False,indent=2),encoding='utf-8')


if __name__ == "__main__":
    main()
